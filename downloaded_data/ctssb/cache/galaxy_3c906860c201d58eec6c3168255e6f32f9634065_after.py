"""
Contains the user interface in the Universe class
"""
from galaxy.web.framework.helpers import time_ago, grids
from galaxy.web.base.controller import *
from galaxy.model.orm import *
from galaxy import util, model
import logging, os, string, re, smtplib, socket, glob
from random import choice
from email.MIMEText import MIMEText
from galaxy.web.form_builder import * 
from galaxy.util.json import from_json_string, to_json_string
from galaxy.web.framework.helpers import iff

log = logging.getLogger( __name__ )

require_login_template = """
<h1>Welcome to Galaxy</h1>

<p>
    This installation of Galaxy has been configured such that only users who are logged in may use it.%s
</p>
<p/>
"""
require_login_nocreation_template = require_login_template % ""
require_login_creation_template = require_login_template % "  If you don't already have an account, <a href='%s'>you may create one</a>."

VALID_USERNAME_RE = re.compile( "^[a-z0-9\-]+$" )

OPENID_PROVIDERS = { 'Google' : 'https://www.google.com/accounts/o8/id',
                     'Yahoo!' : 'http://yahoo.com',
                     'AOL/AIM' : 'http://openid.aol.com',
                     'Flickr' : 'http://flickr.com',
                     'Launchpad' : 'http://login.launchpad.net',
                   }

class UserOpenIDGrid( grids.Grid ):
    use_panels = False
    title = "OpenIDs linked to your account"
    model_class = model.UserOpenID
    template = '/user/openid_manage.mako'
    default_filter = { "openid" : "All" }
    default_sort_key = "-create_time"
    columns = [
        grids.TextColumn( "OpenID URL", key="openid" ),
        grids.GridColumn( "Created", key="create_time", format=time_ago ),
    ]
    operations = [
        grids.GridOperation( "Delete", async_compatible=True ),
    ]
    def build_initial_query( self, trans, **kwd ):
        return trans.sa_session.query( self.model_class ).filter( self.model_class.user_id == trans.user.id )

class User( BaseController, UsesFormDefinitions ):
    user_openid_grid = UserOpenIDGrid()
    installed_len_files = None
    
    @web.expose
    def index( self, trans, cntrller, webapp='galaxy', **kwd ):
        return trans.fill_template( '/user/index.mako', cntrller=cntrller, webapp=webapp )
    @web.expose
    def openid_auth( self, trans, webapp='galaxy', **kwd ):
        if not trans.app.config.enable_openid:
            return trans.show_error_message( 'OpenID authentication is not enabled in this instance of Galaxy' )
        message = 'Unspecified failure authenticating via OpenID'
        status = kwd.get( 'status', 'done' )
        openid_url = kwd.get( 'openid_url', '' )
        openid_provider = kwd.get( 'openid_provider', '' )
        referer = kwd.get( 'referer', trans.request.referer )
        auto_associate = util.string_as_bool( kwd.get( 'auto_associate', False ) )
        use_panels = util.string_as_bool( kwd.get( 'use_panels', False ) )
        action = 'login'
        if auto_associate:
            action = 'openid_manage'
        if not referer:
            referer = url_for( '/' )
        consumer = trans.app.openid_manager.get_consumer( trans )
        process_url = trans.request.base.rstrip( '/' ) + url_for( controller='user', action='openid_process', referer=referer, auto_associate=auto_associate )
        if not openid_url and openid_provider and openid_provider in OPENID_PROVIDERS:
            openid_url = OPENID_PROVIDERS[openid_provider]
        if openid_url:
            request = None
            try:
                request = consumer.begin( openid_url )
                if request is None:
                    message = 'No OpenID services are available at %s' % openid_url
            except Exception, e:
                message = 'Failed to begin OpenID authentication: %s' % str( e )
            if request is not None:
                trans.app.openid_manager.add_sreg( trans, request, optional=[ 'nickname', 'email' ] )
                if request.shouldSendRedirect():
                    redirect_url = request.redirectURL(
                        trans.request.base, process_url )
                    trans.app.openid_manager.persist_session( trans, consumer )
                    trans.response.send_redirect( redirect_url )
                    return
                else:
                    form = request.htmlMarkup( trans.request.base, process_url, form_tag_attrs={'id':'openid_message','target':'_top'} )
                    trans.app.openid_manager.persist_session( trans, consumer )
                    return form
        return trans.response.send_redirect( url_for( controller='user',
                                                      action=action,
                                                      use_panels=use_panels,
                                                      message=message,
                                                      status='error' ) )
    @web.expose
    def openid_process( self, trans, webapp='galaxy', **kwd ):
        if not trans.app.config.enable_openid:
            return trans.show_error_message( 'OpenID authentication is not enabled in this instance of Galaxy' )
        auto_associate = util.string_as_bool( kwd.get( 'auto_associate', False ) )
        action = 'login'
        if auto_associate:
            action = 'openid_manage'
        if trans.app.config.bugs_email is not None:
            contact = '<a href="mailto:%s">contact support</a>' % trans.app.config.bugs_email
        else:
            contact = 'contact support'
        message = 'Verification failed for an unknown reason.  Please contact support for assistance.'
        status = 'error'
        consumer = trans.app.openid_manager.get_consumer( trans )
        info = consumer.complete( kwd, trans.request.url )
        display_identifier = info.getDisplayIdentifier()
        redirect_url = kwd.get( 'referer', url_for( '/' ) )
        if info.status == trans.app.openid_manager.FAILURE and display_identifier:
            message = "Login via OpenID failed.  The technical reason for this follows, please include this message in your email if you need to %s to resolve this problem: %s" % ( contact, info.message )
            return trans.response.send_redirect( url_for( controller='user',
                                                          action=action,
                                                          use_panels=True,
                                                          message=message,
                                                          status='error' ) )
        elif info.status == trans.app.openid_manager.SUCCESS:
            if info.endpoint.canonicalID:
                display_identifier = info.endpoint.canonicalID
            user_openid = trans.sa_session.query( trans.app.model.UserOpenID ).filter( trans.app.model.UserOpenID.table.c.openid == display_identifier ).first()
            if not user_openid:
                user_openid = trans.app.model.UserOpenID( session=trans.galaxy_session, openid=display_identifier )
            elif not user_openid.user and user_openid.session.id != trans.galaxy_session.id:
                user_openid.session = trans.galaxy_session
            elif user_openid.user and not auto_associate:
                trans.handle_user_login( user_openid.user, webapp )
                trans.log_event( "User logged in via OpenID: %s" % display_identifier )
                trans.response.send_redirect( redirect_url )
                return
            if auto_associate and trans.user:
                # The user is already logged in and requested association from
                # the user prefs as opposed to using the OpenID form on the
                # login page.
                if user_openid.user and user_openid.user.id != trans.user.id:
                    message = "The OpenID <strong>%s</strong> is already associated with another Galaxy account, <strong>%s</strong>.  Please disassociate it from that account before attempting to associate it with a new account." % ( display_identifier, user_openid.user.email )
                    status = "error"
                elif user_openid.user and user_openid.user.id == trans.user.id:
                    message = "The OpenID <strong>%s</strong> is already associated with your Galaxy account, <strong>%s</strong>." % ( display_identifier, trans.user.email )
                    status = "warning"
                else:
                    user_openid.user_id = trans.user.id
                    trans.sa_session.add( user_openid )
                    trans.sa_session.flush()
                    trans.log_event( "User associated OpenID: %s" % display_identifier )
                    message = "The OpenID <strong>%s</strong> has been associated with your Galaxy account, <strong>%s</strong>." % ( display_identifier, trans.user.email )
                    status = "done"
                trans.response.send_redirect( url_for( controller='user',
                                                       action='openid_manage',
                                                       use_panels=True,
                                                       message=message,
                                                       status=status ) )
                return
            trans.sa_session.add( user_openid )
            trans.sa_session.flush()
            message = "OpenID authentication was successful, but you need to associate your OpenID with a Galaxy account."
            sreg_resp = trans.app.openid_manager.get_sreg( info )
            try:
                username = sreg_resp.get( 'nickname', '' )
            except AttributeError:
                username = ''
            try:
                email = sreg_resp.get( 'email', '' )
            except AttributeError:
                email = ''
            trans.response.send_redirect( url_for( controller='user',
                                                   action='openid_associate',
                                                   use_panels=True,
                                                   username=username,
                                                   email=email,
                                                   message=message,
                                                   status='warning' ) )
        elif info.status == trans.app.openid_manager.CANCEL:
            message = "Login via OpenID was cancelled by an action at the OpenID provider's site."
            status = "warning"
        elif info.status == trans.app.openid_manager.SETUP_NEEDED:
            if info.setup_url:
                return trans.response.send_redirect( info.setup_url )
            else:
                message = "Unable to log in via OpenID.  Setup at the provider is required before this OpenID can be used.  Please visit your provider's site to complete this step."
        return trans.response.send_redirect( url_for( controller='user',
                                                      action=action,
                                                      use_panels=True,
                                                      message=message,
                                                      status=status ) )
    @web.expose
    def openid_associate( self, trans, cntrller, webapp='galaxy', **kwd ):
        if not trans.app.config.enable_openid:
            return trans.show_error_message( 'OpenID authentication is not enabled in this instance of Galaxy' )
        use_panels = util.string_as_bool( kwd.get( 'use_panels', False ) )
        message = kwd.get( 'message', '' )
        status = kwd.get( 'status', 'done' )
        email = kwd.get( 'email', '' )
        username = kwd.get( 'username', '' )
        referer = kwd.get( 'referer', trans.request.referer )
        params = util.Params( kwd )
        is_admin = cntrller == 'admin' and trans.user_is_admin()
        openids = trans.galaxy_session.openids
        user = None
        if not openids:
            return trans.show_error_message( 'You have not successfully completed an OpenID authentication in this session.  You can do so on the <a href="%s">login</a> page.' % url_for( controller='user', action='login', use_panels=use_panels ) )
        elif is_admin:
            return trans.show_error_message( 'Associating OpenIDs with accounts cannot be done by administrators.' )
        if kwd.get( 'login_button', False ):
            message, status, user, success = self.__validate_login( trans, webapp, **kwd )
            if success:
                for openid in openids:
                    openid.user = user
                    trans.sa_session.add( openid )
                trans.sa_session.flush()
                for openid in openids:
                    trans.log_event( "User associated OpenID: %s" % openid.openid )
                redirect_url = referer
                if not redirect_url:
                    redirect_url = url_for( '/' )
                trans.response.send_redirect( redirect_url )
                return
        if kwd.get( 'create_user_button', False ):
            password = kwd.get( 'password', '' )
            confirm = kwd.get( 'confirm', '' )
            subscribe = params.get( 'subscribe', '' )
            subscribe_checked = CheckboxField.is_checked( subscribe )
            error = ''
            if not trans.app.config.allow_user_creation and not trans.user_is_admin():
                error = 'User registration is disabled.  Please contact your Galaxy administrator for an account.'
            else:
                # Check email and password validity
                error = self.__validate( trans, params, email, password, confirm, username, webapp )
                if not error:
                    # all the values are valid
                    message, status, user, success = self.__register( trans,
                                                                      cntrller,
                                                                      subscribe_checked,
                                                                      **kwd )
                    if success:
                        trans.handle_user_login( user, webapp )
                        trans.log_event( "User created a new account" )
                        trans.log_event( "User logged in" )
                        for openid in openids:
                            openid.user = user
                            trans.sa_session.add( openid )
                        trans.sa_session.flush()
                        for openid in openids:
                            trans.log_event( "User associated OpenID: %s" % openid.openid )
                        redirect_url = referer
                        if not redirect_url:
                            redirect_url = url_for( '/' )
                        trans.response.send_redirect( redirect_url )
                else:
                    message = error
                    status = 'error'
        if webapp == 'galaxy':
            user_type_form_definition = self.__get_user_type_form_definition( trans, user=user, **kwd )
            user_type_fd_id = params.get( 'user_type_fd_id', 'none' )
            if user_type_fd_id == 'none' and user_type_form_definition is not None:
                user_type_fd_id = trans.security.encode_id( user_type_form_definition.id )
            user_type_fd_id_select_field = self.__build_user_type_fd_id_select_field( trans, selected_value=user_type_fd_id )
            widgets = self.__get_widgets( self, trans, user_type_form_definition, user=user, **kwd )
        else:
            user_type_fd_id_select_field = None
            user_type_form_definition = None
            widgets = []
        return trans.fill_template( '/user/openid_associate.mako',
                                    webapp=webapp,
                                    cntrller=cntrller,
                                    email=email,
                                    password='',
                                    confirm='',
                                    username=username,
                                    header='',
                                    use_panels=use_panels,
                                    redirect_url='',
                                    referer='',
                                    refresh_frames=[],
                                    message=message,
                                    status=status,
                                    active_view="user",
                                    subscribe_checked=False,
                                    user_type_fd_id_select_field=user_type_fd_id_select_field,
                                    user_type_form_definition=user_type_form_definition,
                                    widgets=widgets,
                                    openids=openids )
    @web.expose
    @web.require_login( 'manage OpenIDs' )
    def openid_disassociate( self, trans, webapp='galaxy', **kwd ):
        if not trans.app.config.enable_openid:
            return trans.show_error_message( 'OpenID authentication is not enabled in this instance of Galaxy' )
        params = util.Params( kwd )
        ids = params.get( 'id', None )
        message = params.get( 'message', None )
        status = params.get( 'status', None )
        use_panels = params.get( 'use_panels', False )
        user_openids = []
        if not ids:
            message = 'You must select at least one OpenID to disassociate from your Galaxy account.'
            status = 'error'
        else:
            ids = util.listify( params.id )
            for id in ids:
                id = trans.security.decode_id( id )
                user_openid = trans.sa_session.query( trans.app.model.UserOpenID ).get( int( id ) )
                if not user_openid or ( trans.user.id != user_openid.user_id ):
                    message = 'The selected OpenID(s) are not associated with your Galaxy account.'
                    status = 'error'
                    user_openids = []
                    break
                user_openids.append( user_openid )
            if user_openids:
                deleted_urls = []
                for user_openid in user_openids:
                    trans.sa_session.delete( user_openid )
                    deleted_urls.append( user_openid.openid )
                trans.sa_session.flush()
                for deleted_url in deleted_urls:
                    trans.log_event( "User disassociated OpenID: %s" % deleted_url )
                message = '%s OpenIDs were disassociated from your Galaxy account.' % len( ids )
                status = 'done'
        trans.response.send_redirect( url_for( controller='user',
                                               action='openid_manage',
                                               use_panels=use_panels,
                                               message=message,
                                               status=status ) )
    @web.expose
    @web.require_login( 'manage OpenIDs' )
    def openid_manage( self, trans, webapp='galaxy', **kwd ):
        if not trans.app.config.enable_openid:
            return trans.show_error_message( 'OpenID authentication is not enabled in this instance of Galaxy' )
        use_panels = kwd.get( 'use_panels', False )
        if 'operation' in kwd:
            operation = kwd['operation'].lower()
            if operation == "delete":
                trans.response.send_redirect( url_for( controller='user',
                                                       action='openid_disassociate',
                                                       use_panels=use_panels,
                                                       id=kwd['id'] ) )
        kwd['referer'] = url_for( controller='user', action='openid_manage', use_panels=True )
        kwd['openid_providers'] = OPENID_PROVIDERS
        return self.user_openid_grid( trans, **kwd )
    @web.expose
    def login( self, trans, webapp='galaxy', redirect_url='', refresh_frames=[], **kwd ):
        referer = kwd.get( 'referer', trans.request.referer )
        use_panels = util.string_as_bool( kwd.get( 'use_panels', False ) )
        message = kwd.get( 'message', '' )
        status = kwd.get( 'status', 'done' )
        header = ''
        user = None
        email = kwd.get( 'email', '' )
        if kwd.get( 'login_button', False ):
            if webapp == 'galaxy' and not refresh_frames:
                if trans.app.config.require_login:
                    refresh_frames = [ 'masthead', 'history', 'tools' ]
                else:
                    refresh_frames = [ 'masthead', 'history' ]
            message, status, user, success = self.__validate_login( trans, webapp, **kwd )
            if success and referer and referer != trans.request.base + url_for( controller='user', action='logout' ):
                redirect_url = referer
            elif success:
                redirect_url = url_for( '/' )
        if not user and trans.app.config.require_login:
            if trans.app.config.allow_user_creation:
                header = require_login_creation_template % web.url_for( action='create' )
            else:
                header = require_login_nocreation_template
        return trans.fill_template( '/user/login.mako',
                                    webapp=webapp,
                                    email=email,
                                    header=header,
                                    use_panels=use_panels,
                                    redirect_url=redirect_url,
                                    referer=referer,
                                    refresh_frames=refresh_frames,
                                    message=message,
                                    status=status,
                                    openid_providers=OPENID_PROVIDERS,
                                    active_view="user" )
    def __validate_login( self, trans, webapp='galaxy', **kwd ):
        message = kwd.get( 'message', '' )
        status = kwd.get( 'status', 'done' )
        email = kwd.get( 'email', '' )
        password = kwd.get( 'password', '' )
        referer = kwd.get( 'referer', trans.request.referer )
        success = False
        user = trans.sa_session.query( trans.app.model.User ).filter( trans.app.model.User.table.c.email==email ).first()
        if not user:
            message = "No such user"
            status = 'error'
        elif user.deleted:
            message = "This account has been marked deleted, contact your Galaxy administrator to restore the account."
            status = 'error'
        elif user.external:
            message = "This account was created for use with an external authentication method, contact your local Galaxy administrator to activate it."
            status = 'error'
        elif not user.check_password( password ):
            message = "Invalid password"
            status = 'error'
        else:
            trans.handle_user_login( user, webapp )
            trans.log_event( "User logged in" )
            message = 'You are now logged in as %s.<br>You can <a target="_top" href="%s">go back to the page you were visiting</a> or <a target="_top" href="%s">go to the home page</a>.' % \
                ( user.email, referer, url_for( '/' ) )
            if trans.app.config.require_login:
                message += '  <a target="_top" href="%s">Click here</a> to continue to the home page.' % web.url_for( '/static/welcome.html' )
            success = True
        return ( message, status, user, success )
    @web.expose
    def logout( self, trans, webapp='galaxy' ):
        if webapp == 'galaxy':
            if trans.app.config.require_login:
                refresh_frames = [ 'masthead', 'history', 'tools' ]
            else:
                refresh_frames = [ 'masthead', 'history' ]
        else:
            refresh_frames = [ 'masthead' ]
        # Since logging an event requires a session, we'll log prior to ending the session
        trans.log_event( "User logged out" )
        trans.handle_user_logout()
        message = 'You have been logged out.<br>You can log in again, <a target="_top" href="%s">go back to the page you were visiting</a> or <a target="_top" href="%s">go to the home page</a>.' % \
            ( trans.request.referer, url_for( '/' ) )
        return trans.fill_template( '/user/logout.mako',
                                    webapp=webapp,
                                    refresh_frames=refresh_frames,
                                    message=message,
                                    status='done',
                                    active_view="user" )
    @web.expose
    def create( self, trans, cntrller, redirect_url='', refresh_frames=[], **kwd ):
        params = util.Params( kwd )
        message = util.restore_text( params.get( 'message', ''  ) )
        status = params.get( 'status', 'done' )
        webapp = params.get( 'webapp', 'galaxy' )
        use_panels = util.string_as_bool( kwd.get( 'use_panels', True ) )
        email = util.restore_text( params.get( 'email', '' ) )
        # Do not sanitize passwords, so take from kwd
        # instead of params ( which were sanitized )
        password = kwd.get( 'password', '' )
        confirm = kwd.get( 'confirm', '' )
        username = util.restore_text( params.get( 'username', '' ) )
        subscribe = params.get( 'subscribe', '' )
        subscribe_checked = CheckboxField.is_checked( subscribe )
        referer = kwd.get( 'referer', trans.request.referer )
        is_admin = cntrller == 'admin' and trans.user_is_admin
        if not trans.app.config.allow_user_creation and not trans.user_is_admin():
            message = 'User registration is disabled.  Please contact your Galaxy administrator for an account.'
            status = 'error'
        else:
            if not refresh_frames:
                if webapp == 'galaxy':
                    if trans.app.config.require_login:
                        refresh_frames = [ 'masthead', 'history', 'tools' ]
                    else:
                        refresh_frames = [ 'masthead', 'history' ]
                else:
                    refresh_frames = [ 'masthead' ]
            # Create the user, save all the user info and login to Galaxy
            if params.get( 'create_user_button', False ):
                # Check email and password validity
                message = self.__validate( trans, params, email, password, confirm, username, webapp )
                if not message:
                    # All the values are valid
                    message, status, user, success = self.__register( trans,
                                                                      cntrller,
                                                                      subscribe_checked,
                                                                      **kwd )
                    if success and not is_admin and webapp != 'galaxy':
                        # Must be logging into the community space webapp
                        trans.handle_user_login( user, webapp )
                        redirect_url = referer
                    if success and not is_admin:
                        # The handle_user_login() method has a call to the history_set_default_permissions() method
                        # (needed when logging in with a history), user needs to have default permissions set before logging in
                        trans.handle_user_login( user, webapp )
                        trans.log_event( "User created a new account" )
                        trans.log_event( "User logged in" )
                    if success and is_admin:
                        message = 'Created new user account (%s)' % user.email
                        trans.response.send_redirect( web.url_for( controller='admin',
                                                                   action='users',
                                                                   cntrller=cntrller,
                                                                   message=message,
                                                                   status=status ) )
                else:
                    status = 'error'
        if webapp == 'galaxy':
            user_type_form_definition = self.__get_user_type_form_definition( trans, user=None, **kwd )
            user_type_fd_id = params.get( 'user_type_fd_id', 'none' )
            if user_type_fd_id == 'none' and user_type_form_definition is not None:
                user_type_fd_id = trans.security.encode_id( user_type_form_definition.id )
            user_type_fd_id_select_field = self.__build_user_type_fd_id_select_field( trans, selected_value=user_type_fd_id )
            widgets = self.__get_widgets( trans, user_type_form_definition, user=None, **kwd )
        else:
            user_type_fd_id_select_field = None
            user_type_form_definition = None
            widgets = []
        return trans.fill_template( '/user/register.mako',
                                    cntrller=cntrller,
                                    email=email,
                                    password=password,
                                    confirm=confirm,
                                    username=username,
                                    subscribe_checked=subscribe_checked,
                                    user_type_fd_id_select_field=user_type_fd_id_select_field,
                                    user_type_form_definition=user_type_form_definition,
                                    widgets=widgets,
                                    webapp=webapp,
                                    use_panels=use_panels,
                                    referer=referer,
                                    redirect_url=redirect_url,
                                    refresh_frames=refresh_frames,
                                    message=message,
                                    status=status )
    def __register( self, trans, cntrller, subscribe_checked, **kwd ):
        email = util.restore_text( kwd.get( 'email', '' ) )
        password = kwd.get( 'password', '' )
        username = util.restore_text( kwd.get( 'username', '' ) )
        webapp = kwd.get( 'webapp', 'galaxy' )
        status = kwd.get( 'status', 'done' )
        is_admin = cntrller == 'admin' and trans.user_is_admin()
        user = trans.app.model.User( email=email )
        user.set_password_cleartext( password )
        user.username = username
        trans.sa_session.add( user )
        trans.sa_session.flush()
        trans.app.security_agent.create_private_user_role( user )
        error = ''
        if webapp == 'galaxy':
            # We set default user permissions, before we log in and set the default history permissions
            trans.app.security_agent.user_set_default_permissions( user,
                                                                   default_access_private=trans.app.config.new_user_dataset_access_role_default_private )
            # Save other information associated with the user, if any
            user_info_forms = self.get_all_forms( trans,
                                                  filter=dict( deleted=False ),
                                                  form_type=trans.app.model.FormDefinition.types.USER_INFO )
            # If there are no user forms available then there is nothing to save
            if user_info_forms:
                user_type_fd_id = kwd.get( 'user_type_fd_id', 'none' )
                if user_type_fd_id not in [ 'none' ]:
                    user_type_form_definition = trans.sa_session.query( trans.app.model.FormDefinition ).get( trans.security.decode_id( user_type_fd_id ) )
                    values = self.get_form_values( trans, user, user_type_form_definition, **kwd )
                    form_values = trans.app.model.FormValues( user_type_form_definition, values )
                    trans.sa_session.add( form_values )
                    trans.sa_session.flush()
                    user.values = form_values
                    trans.sa_session.add( user )
                    trans.sa_session.flush()
            if subscribe_checked:
                # subscribe user to email list
                if trans.app.config.smtp_server is None:
                    error = "Now logged in as " + user.email + ". However, subscribing to the mailing list has failed because mail is not configured for this Galaxy instance."
                else:
                    msg = MIMEText( 'Join Mailing list.\n' )
                    to = msg[ 'To' ] = trans.app.config.mailing_join_addr
                    frm = msg[ 'From' ] = email
                    msg[ 'Subject' ] = 'Join Mailing List'
                    try:
                        s = smtplib.SMTP()
                        s.connect( trans.app.config.smtp_server )
                        s.sendmail( frm, [ to ], msg.as_string() )
                        s.close()
                    except:
                        error = "Now logged in as " + user.email + ". However, subscribing to the mailing list has failed."
            if not error and not is_admin:
                # The handle_user_login() method has a call to the history_set_default_permissions() method
                # (needed when logging in with a history), user needs to have default permissions set before logging in
                trans.handle_user_login( user, webapp )
                trans.log_event( "User created a new account" )
                trans.log_event( "User logged in" )
            elif not error:
                trans.response.send_redirect( web.url_for( controller='admin',
                                                           action='users',
                                                           message='Created new user account (%s)' % user.email,
                                                           status=status ) )
        if error:
            message = error
            status = 'error'
            success = False
        else:
            message = 'Now logged in as %s.<br><a target="_top" href="%s">Return to the home page.</a>' % ( user.email, url_for( '/' ) )
            success = True
        return ( message, status, user, success )
    def __validate_email( self, trans, email, user=None ):
        message = ''
        if user and user.email == email:
            return message 
        if len( email ) == 0 or "@" not in email or "." not in email:
            message = "Enter a real email address"
        elif len( email ) > 255:
            message = "Email address exceeds maximum allowable length"
        elif trans.sa_session.query( trans.app.model.User ).filter_by( email=email ).first():
            message = "User with that email already exists"
        return message
    def __validate_username( self, trans, username, user=None ):
        # User names must be at least four characters in length and contain only lower-case
        # letters, numbers, and the '-' character.
        if username in [ 'None', None, '' ]:
            return ''
        if user and user.username == username:
            return ''
        if len( username ) < 4:
            return "User name must be at least 4 characters in length"
        if len( username ) > 255:
            return "User name cannot be more than 255 characters in length"
        if not( VALID_USERNAME_RE.match( username ) ):
            return "User name must contain only lower-case letters, numbers and '-'"
        if trans.sa_session.query( trans.app.model.User ).filter_by( username=username ).first():
            return "This user name is not available"
        return ''
    def __validate_password( self, trans, password, confirm ):
        if len( password ) < 6:
            return "Use a password of at least 6 characters"
        elif password != confirm:
            return "Passwords do not match"
        return ''
    def __validate( self, trans, params, email, password, confirm, username, webapp ):
        # If coming from the community webapp, we'll require a public user name
        if webapp == 'community' and not username:
            return "A public user name is required"
        message = self.__validate_email( trans, email )
        if not message:
            message = self.__validate_password( trans, password, confirm )
        if not message and username:
            message = self.__validate_username( trans, username )
        if not message:
            if webapp == 'galaxy':
                if self.get_all_forms( trans, 
                                       filter=dict( deleted=False ),
                                       form_type=trans.app.model.FormDefinition.types.USER_INFO ):
                    user_type_fd_id = params.get( 'user_type_fd_id', 'none' )
                    if user_type_fd_id in [ 'none' ]:
                        return "Select the user's type and information"
        return message
    def __get_user_type_form_definition( self, trans, user=None, **kwd ):
        params = util.Params( kwd )
        if user and user.values:
            user_type_fd_id = trans.security.encode_id( user.values.form_definition.id )
        else:
            user_type_fd_id = params.get( 'user_type_fd_id', 'none' )
        if user_type_fd_id not in [ 'none' ]:
            user_type_form_definition = trans.sa_session.query( trans.app.model.FormDefinition ).get( trans.security.decode_id( user_type_fd_id ) )
        else:
            user_type_form_definition = None
        return user_type_form_definition
    def __get_widgets( self, trans, user_type_form_definition, user=None, **kwd ):
        widgets = []
        if user_type_form_definition:
            if user:
                if user.values:
                    widgets = user_type_form_definition.get_widgets( user=user, 
                                                                     contents=user.values.content, 
                                                                     **kwd )
                else:
                    widgets = user_type_form_definition.get_widgets( None, contents={}, **kwd )
            else:
                widgets = user_type_form_definition.get_widgets( None, contents={}, **kwd )
        return widgets
    @web.expose
    def manage_user_info( self, trans, cntrller, **kwd ):
        '''Manage a user's login, password, public username, type, addresses, etc.'''
        params = util.Params( kwd )
        user_id = params.get( 'id', None )
        if user_id:
            user = trans.sa_session.query( trans.app.model.User ).get( trans.security.decode_id( user_id ) )
        else:
            user = trans.user
        if not user:
            raise AssertionError, "The user id (%s) is not valid" % str( user_id )
        webapp = params.get( 'webapp', 'galaxy' )
        email = util.restore_text( params.get( 'email', user.email ) )
        # Do not sanitize passwords, so take from kwd
        # instead of params ( which were sanitized )
        current = kwd.get( 'current', '' )
        password = kwd.get( 'password', '' )
        confirm = kwd.get( 'confirm', '' )
        username = util.restore_text( params.get( 'username', '' ) )
        if not username:
            username = user.username
        message = util.restore_text( params.get( 'message', ''  ) )
        status = params.get( 'status', 'done' )
        if webapp == 'galaxy':
            user_type_form_definition = self.__get_user_type_form_definition( trans, user=user, **kwd )
            user_type_fd_id = params.get( 'user_type_fd_id', 'none' )
            if user_type_fd_id == 'none' and user_type_form_definition is not None:
                user_type_fd_id = trans.security.encode_id( user_type_form_definition.id )    
            user_type_fd_id_select_field = self.__build_user_type_fd_id_select_field( trans, selected_value=user_type_fd_id )
            widgets = self.__get_widgets( trans, user_type_form_definition, user=user, **kwd )
            # user's addresses
            show_filter = util.restore_text( params.get( 'show_filter', 'Active'  ) )
            if show_filter == 'All':
                addresses = [address for address in user.addresses]
            elif show_filter == 'Deleted':
                addresses = [address for address in user.addresses if address.deleted]
            else:
                addresses = [address for address in user.addresses if not address.deleted]
            user_info_forms = self.get_all_forms( trans,
                                                  filter=dict( deleted=False ),
                                                  form_type=trans.app.model.FormDefinition.types.USER_INFO )
            return trans.fill_template( '/webapps/galaxy/user/info.mako',
                                        cntrller=cntrller,
                                        user=user,
                                        email=email,
                                        current=current,
                                        password=password,
                                        confirm=confirm,
                                        username=username,
                                        user_type_fd_id_select_field=user_type_fd_id_select_field,
                                        user_info_forms=user_info_forms,
                                        user_type_form_definition=user_type_form_definition,
                                        widgets=widgets, 
                                        addresses=addresses,
                                        show_filter=show_filter,
                                        webapp=webapp,
                                        message=message,
                                        status=status )
        else:
            return trans.fill_template( '/webapps/community/user/info.mako',
                                        cntrller=cntrller,
                                        user=user,
                                        email=email,
                                        current=current,
                                        password=password,
                                        confirm=confirm,
                                        username=username,
                                        webapp=webapp,
                                        message=message,
                                        status=status )
    @web.expose
    def edit_info( self, trans, cntrller, **kwd ):
        params = util.Params( kwd )
        is_admin = cntrller == 'admin' and trans.user_is_admin()
        webapp = params.get( 'webapp', 'galaxy' )
        message = util.restore_text( params.get( 'message', ''  ) )
        status = params.get( 'status', 'done' )
        user_id = params.get( 'user_id', None )
        #new_kwd = dict( webapp=webapp )
        if user_id:
            user = trans.sa_session.query( trans.app.model.User ).get( trans.security.decode_id( user_id ) )
        else:
            user = trans.user
        if params.get( 'login_info_button', False ):
            # Editing email and username
            email = util.restore_text( params.get( 'email', '' ) )
            username = util.restore_text( params.get( 'username', '' ) ).lower()
            # Validate the new values for email and username
            message = self.__validate_email( trans, email, user )
            if not message and username:
                message = self.__validate_username( trans, username, user )
            if message:
                status = 'error'
            else:
                # The user's private role name must match the user's login ( email )
                private_role = trans.app.security_agent.get_private_user_role( user )
                private_role.name = email
                private_role.description = 'Private role for ' + email
                # Now change the user info
                user.email = email
                user.username = username
                trans.sa_session.add_all( ( user, private_role ) )
                trans.sa_session.flush()
                message = 'The login information has been updated with the changes.'
        elif params.get( 'change_password_button', False ):
            # Editing password.  Do not sanitize passwords, so get from kwd 
            # and not params (which were sanitized).
            password = kwd.get( 'password', '' )
            confirm = kwd.get( 'confirm', '' )
            ok = True
            if not webapp == 'galaxy' and not is_admin:
                # If the current user is changing their own password, validate their current password
                current = kwd.get( 'current', '' )
                if not trans.user.check_password( current ):
                    message = 'Invalid current password'
                    status = 'error'
                    ok = False
            if ok:
                # Validate the new password
                message = self.__validate_password( trans, password, confirm )
                if message:
                    status = 'error'
                else:
                    # Save new password
                    user.set_password_cleartext( password )
                    trans.sa_session.add( user )
                    trans.sa_session.flush()
                    trans.log_event( "User change password" )
                    message = 'The password has been changed.'
        elif params.get( 'edit_user_info_button', False ):
            # Edit user information - webapp MUST BE 'galaxy'
            user_type_fd_id = params.get( 'user_type_fd_id', 'none' )
            if user_type_fd_id not in [ 'none' ]:
                user_type_form_definition = trans.sa_session.query( trans.app.model.FormDefinition ).get( trans.security.decode_id( user_type_fd_id ) )   
            elif user.values:
                user_type_form_definition = user.values.form_definition
            else:
                # User was created before any of the user_info forms were created
                user_type_form_definition = None
            if user_type_form_definition:
                values = self.get_form_values( trans, user, user_type_form_definition, **kwd )
            else:
                values = {}
            flush_needed = False
            if user.values:  
                # Editing the user info of an existing user with existing user info
                user.values.content = values
                trans.sa_session.add( user.values )
                flush_needed = True
            elif values:
                form_values = trans.model.FormValues( user_type_form_definition, values )
                trans.sa_session.add( form_values )
                user.values = form_values
                flush_needed = True
            if flush_needed:
                trans.sa_session.add( user )
                trans.sa_session.flush()
            message = "The user information has been updated with the changes."
        if webapp == 'galaxy' and is_admin:
            kwd[ 'user_id' ] = trans.security.encode_id( user.id )
        kwd[ 'id' ] = user_id
        if message:
            kwd[ 'message' ] = util.sanitize_text( message )
        return trans.response.send_redirect( web.url_for( controller='user',
                                                          action='manage_user_info',
                                                          cntrller=cntrller,
                                                          **kwd ) )
    @web.expose
    def reset_password( self, trans, email=None, webapp='galaxy', **kwd ):
        if trans.app.config.smtp_server is None:
            return trans.show_error_message( "Mail is not configured for this Galaxy instance.  Please contact an administrator." )
        message = util.restore_text( kwd.get( 'message', '' ) )
        status = 'done'
        if kwd.get( 'reset_password_button', False ):
            reset_user = trans.sa_session.query( trans.app.model.User ).filter( trans.app.model.User.table.c.email==email ).first()
            user = trans.get_user()
            if reset_user:
                if user and user.id != reset_user.id:
                    message = "You may only reset your own password"
                    status = 'error'
                else:
                    chars = string.letters + string.digits
                    new_pass = ""
                    for i in range(15):
                        new_pass = new_pass + choice(chars)
                    host = trans.request.host.split(':')[0]
                    if host == 'localhost':
                        host = socket.getfqdn()
                    msg = MIMEText( 'Your password on %s has been reset to:\n\n  %s\n' % ( host, new_pass ) )
                    to = msg[ 'To' ] = email
                    frm = msg[ 'From' ] = 'galaxy-no-reply@' + host
                    msg[ 'Subject' ] = 'Galaxy Password Reset'
                    try:
                        s = smtplib.SMTP()
                        s.connect( trans.app.config.smtp_server )
                        s.sendmail( frm, [ to ], msg.as_string() )
                        s.close()
                        reset_user.set_password_cleartext( new_pass )
                        trans.sa_session.add( reset_user )
                        trans.sa_session.flush()
                        trans.log_event( "User reset password: %s" % email )
                        message = "Password has been reset and emailed to: %s.  <a href='%s'>Click here</a> to return to the login form." % ( email, web.url_for( action='login' ) )
                    except Exception, e:
                        message = 'Failed to reset password: %s' % str( e )
                        status = 'error'
                    return trans.response.send_redirect( web.url_for( controller='user',
                                                                      action='reset_password',
                                                                      message=message,
                                                                      status=status ) )
            elif email != None:
                message = "The specified user does not exist"
                status = 'error'
            elif email is None:
                email = ""
        return trans.fill_template( '/user/reset_password.mako',
                                    webapp=webapp,
                                    message=message,
                                    status=status )
    @web.expose
    def set_default_permissions( self, trans, cntrller, **kwd ):
        """Sets the user's default permissions for the new histories"""
        if trans.user:
            if 'update_roles_button' in kwd:
                p = util.Params( kwd )
                permissions = {}
                for k, v in trans.app.model.Dataset.permitted_actions.items():
                    in_roles = p.get( k + '_in', [] )
                    if not isinstance( in_roles, list ):
                        in_roles = [ in_roles ]
                    in_roles = [ trans.sa_session.query( trans.app.model.Role ).get( x ) for x in in_roles ]
                    action = trans.app.security_agent.get_action( v.action ).action
                    permissions[ action ] = in_roles
                trans.app.security_agent.user_set_default_permissions( trans.user, permissions )
                return trans.show_ok_message( 'Default new history permissions have been changed.' )
            return trans.fill_template( 'user/permissions.mako', cntrller=cntrller )
        else:
            # User not logged in, history group must be only public
            return trans.show_error_message( "You must be logged in to change your default permitted actions." )   
    @web.expose
    @web.require_login( "to get most recently used tool" )
    @web.json_pretty
    def get_most_recently_used_tool_async( self, trans ):
        """ Returns information about the most recently used tool. """
        
        # Get most recently used tool.
        query = trans.sa_session.query( self.app.model.Job.tool_id ).join( self.app.model.History ). \
                                        filter( self.app.model.History.user==trans.user ). \
                                        order_by( self.app.model.Job.create_time.desc() ).limit(1)
        tool_id = query[0][0] # Get first element in first row of query.
        tool = self.get_toolbox().tools_by_id[ tool_id ]
        
        # Return tool info.
        tool_info = { 
            "id" : tool.id, 
            "link" : url_for( controller='tool_runner', tool_id=tool.id ),
            "target" : tool.target,
            "name" : tool.name, ## TODO: translate this using _()
            "minsizehint" : tool.uihints.get( 'minwidth', -1 ),
            "description" : tool.description
        }
        return tool_info          
    @web.expose
    def manage_addresses(self, trans, **kwd):
        if trans.user:
            params = util.Params( kwd )
            message = util.restore_text( params.get( 'message', '' ) )
            status = params.get( 'status', 'done' )
            show_filter = util.restore_text( params.get( 'show_filter', 'Active' ) )
            if show_filter == 'All':
                addresses = [address for address in trans.user.addresses]
            elif show_filter == 'Deleted':
                addresses = [address for address in trans.user.addresses if address.deleted]
            else:
                addresses = [address for address in trans.user.addresses if not address.deleted]
            return trans.fill_template( 'user/address.mako', 
                                        addresses=addresses,
                                        show_filter=show_filter,
                                        message=message,
                                        status=status)
        else:
            # User not logged in, history group must be only public
            return trans.show_error_message( "You must be logged in to change your default permitted actions." )
    @web.expose
    def new_address( self, trans, cntrller, **kwd ):
        params = util.Params( kwd )
        message = util.restore_text( params.get( 'message', ''  ) )
        status = params.get( 'status', 'done' )
        is_admin = cntrller == 'admin' and trans.user_is_admin()
        user_id = params.get( 'user_id', False )
        if not user_id:
            # User must be logged in to create a new address
            return trans.show_error_message( "You must be logged in to create a new address." )
        user = trans.sa_session.query( trans.app.model.User ).get( trans.security.decode_id( user_id ) )
        short_desc = util.restore_text( params.get( 'short_desc', ''  ) )
        name = util.restore_text( params.get( 'name', ''  ) )
        institution = util.restore_text( params.get( 'institution', ''  ) )
        address = util.restore_text( params.get( 'address', ''  ) )
        city = util.restore_text( params.get( 'city', ''  ) )
        state = util.restore_text( params.get( 'state', ''  ) )
        postal_code = util.restore_text( params.get( 'postal_code', ''  ) )
        country = util.restore_text( params.get( 'country', ''  ) )
        phone = util.restore_text( params.get( 'phone', ''  ) )
        ok = True
        if not trans.app.config.allow_user_creation and not is_admin:
            return trans.show_error_message( 'User registration is disabled.  Please contact your Galaxy administrator for an account.' )
        if params.get( 'new_address_button', False ):
            if not short_desc:
                ok = False
                message = 'Enter a short description for this address'
            elif not name:
                ok = False
                message = 'Enter the name'
            elif not institution:
                ok = False
                message = 'Enter the institution associated with the user'
            elif not address:
                ok = False
                message = 'Enter the address'
            elif not city:
                ok = False
                message = 'Enter the city'
            elif not state:
                ok = False
                message = 'Enter the state/province/region'
            elif not postal_code:
                ok = False
                message = 'Enter the postal code'
            elif not country:
                ok = False
                message = 'Enter the country'
            if ok:
                user_address = trans.model.UserAddress( user=user,
                                                        desc=short_desc,
                                                        name=name,
                                                        institution=institution, 
                                                        address=address,
                                                        city=city,
                                                        state=state,
                                                        postal_code=postal_code, 
                                                        country=country,
                                                        phone=phone )
                trans.sa_session.add( user_address )
                trans.sa_session.flush()
                message = 'Address (%s) has been added' % user_address.desc
                new_kwd = dict( message=message, status=status )
                if is_admin:
                    new_kwd[ 'user_id' ] = trans.security.encode_id( user.id )
                return trans.response.send_redirect( web.url_for( controller='user',
                                                                  action='manage_user_info',
                                                                  cntrller=cntrller,
                                                                  **new_kwd ) )
        # Display the address form with the current values filled in
        return trans.fill_template( 'user/new_address.mako',
                                    cntrller=cntrller,
                                    user=user,
                                    short_desc=short_desc,
                                    name=name,
                                    institution=institution,
                                    address=address,
                                    city=city,
                                    state=state,
                                    postal_code=postal_code,
                                    country=country,
                                    phone=phone,
                                    message=message,
                                    status=status )
    @web.expose
    def edit_address( self, trans, cntrller, **kwd ):
        params = util.Params( kwd )
        message = util.restore_text( params.get( 'message', ''  ) )
        status = params.get( 'status', 'done' )
        is_admin = cntrller == 'admin' and trans.user_is_admin()
        user_id = params.get( 'user_id', False )
        if not user_id:
            # User must be logged in to create a new address
            return trans.show_error_message( "You must be logged in to create a new address." )
        user = trans.sa_session.query( trans.app.model.User ).get( trans.security.decode_id( user_id ) )
        address_id = params.get( 'address_id', None )
        if not address_id:
            return trans.show_error_message( "No address id received for editing." )
        address_obj = trans.sa_session.query( trans.app.model.UserAddress ).get( trans.security.decode_id( address_id ) )     
        if params.get( 'edit_address_button', False  ):
            short_desc = util.restore_text( params.get( 'short_desc', ''  ) )
            name = util.restore_text( params.get( 'name', ''  ) )
            institution = util.restore_text( params.get( 'institution', ''  ) )
            address = util.restore_text( params.get( 'address', ''  ) )
            city = util.restore_text( params.get( 'city', ''  ) )
            state = util.restore_text( params.get( 'state', ''  ) )
            postal_code = util.restore_text( params.get( 'postal_code', ''  ) )
            country = util.restore_text( params.get( 'country', ''  ) )
            phone = util.restore_text( params.get( 'phone', ''  ) )
            ok = True
            if not short_desc:
                ok = False
                message = 'Enter a short description for this address'
            elif not name:
                ok = False
                message = 'Enter the name'
            elif not institution:
                ok = False
                message = 'Enter the institution associated with the user'
            elif not address:
                ok = False
                message = 'Enter the address'
            elif not city:
                ok = False
                message = 'Enter the city'
            elif not state:
                ok = False
                message = 'Enter the state/province/region'
            elif not postal_code:
                ok = False
                message = 'Enter the postal code'
            elif not country:
                ok = False
                message = 'Enter the country'
            if ok:
                address_obj.desc = short_desc
                address_obj.name = name
                address_obj.institution = institution
                address_obj.address = address
                address_obj.city = city
                address_obj.state = state
                address_obj.postal_code = postal_code
                address_obj.country = country
                address_obj.phone = phone
                trans.sa_session.add( address_obj )
                trans.sa_session.flush()
                message = 'Address (%s) has been updated.' % address_obj.desc
                new_kwd = dict( message=message, status=status )
                if is_admin:
                    new_kwd[ 'user_id' ] = trans.security.encode_id( user.id )
                return trans.response.send_redirect( web.url_for( controller='user',
                                                                  action='manage_user_info',
                                                                  cntrller=cntrller,
                                                                  **new_kwd ) )
        # Display the address form with the current values filled in
        return trans.fill_template( 'user/edit_address.mako',
                                    cntrller=cntrller,
                                    user=user,
                                    address_obj=address_obj,
                                    message=message,
                                    status=status )
    @web.expose
    def delete_address( self, trans, cntrller, address_id=None, user_id=None ):
        try:
            user_address = trans.sa_session.query( trans.app.model.UserAddress ).get( trans.security.decod_id( address_id ) )
        except:
            user_adress = None
            message = 'Invalid address is (%s)' % address_id
            status = 'error'
        if user_address:
            user_address.deleted = True
            trans.sa_session.add( user_address )
            trans.sa_session.flush()
            'Address (%s) deleted' % user_address.desc
            status = 'done'
        return trans.response.send_redirect( web.url_for( controller='user',
                                                          action='manage_user_info',
                                                          cntrller=cntrller,
                                                          user_id=user_id,
                                                          message=message,
                                                          status=status ) )
    @web.expose
    def undelete_address( self, trans, cntrller, address_id=None, user_id=None ):
        try:
            user_address = trans.sa_session.query( trans.app.model.UserAddress ).get( trans.security.decode_id( address_id ) )
        except:
            user_adress = None
            message = 'Invalid address is (%s)' % address_id
            status = 'error'
        if user_address:
            user_address.deleted = False
            trans.sa_session.flush()
            message = 'Address (%s) undeleted' % user_address.desc
            status = 'done'
        return trans.response.send_redirect( web.url_for( controller='user',
                                                          action='manage_user_info',
                                                          cntrller=cntrller,
                                                          user_id=user_id,
                                                          message=message,
                                                          status=status ) )
    @web.expose
    def set_user_pref_async( self, trans, pref_name, pref_value ):
        """ Set a user preference asynchronously. If user is not logged in, do nothing. """
        if trans.user:
            trans.log_action( trans.get_user(), "set_user_pref", "", { pref_name : pref_value } )
            trans.user.preferences[pref_name] = pref_value
            trans.sa_session.flush()
    @web.expose
    def log_user_action_async( self, trans, action, context, params ):
        """ Log a user action asynchronously. If user is not logged in, do nothing. """
        if trans.user:
            trans.log_action( trans.get_user(), action, context, params )
    
    @web.expose
    @web.require_login()
    def dbkeys( self, trans, **kwds ):
        user = trans.user
        message = None
        lines_skipped = 0
        if self.installed_len_files is None:
            installed_builds = []
            for build in glob.glob( os.path.join(trans.app.config.len_file_path, "*.len") ):
                installed_builds.append( os.path.basename(build).split(".len")[0] )
            self.installed_len_files = ", ".join(installed_builds)
        if 'dbkeys' not in user.preferences:
            dbkeys = {}
        else:
            dbkeys = from_json_string(user.preferences['dbkeys'])
        if 'delete' in kwds:
            key = kwds.get('key', '')
            if key and key in dbkeys:
                del dbkeys[key]
        elif 'add' in kwds:
            name     = kwds.get('name', '')
            key      = kwds.get('key', '')
            len_file = kwds.get('len_file', None)
            if getattr(len_file, "file", None): # Check if it's a FieldStorage object
                len_text = len_file.file.read()
            else:
                len_text = kwds.get('len_text', '')
            if not name or not key or not len_text:
                message = "You must specify values for all the fields."
            elif key in dbkeys:
                message = "There is already a custom build with that key. Delete it first if you want to replace it."
            else:
                # Create new len file
                new_len = trans.app.model.HistoryDatasetAssociation( extension="len", create_dataset=True, sa_session=trans.sa_session )
                trans.sa_session.add( new_len )
                new_len.name = name
                new_len.visible = False
                new_len.state = trans.app.model.Job.states.OK
                new_len.info = "custom build .len file"
                trans.sa_session.flush()
                counter = 0
                f = open(new_len.file_name, "w")
                # LEN files have format:
                #   <chrom_name><tab><chrom_length>
                for line in len_text.split("\n"):
                    lst = line.strip().rsplit(None, 1) # Splits at the last whitespace in the line
                    if not lst or len(lst) < 2:
                        lines_skipped += 1
                        continue
                    chrom, length = lst[0], lst[1]
                    try:
                        length = int(length)
                    except ValueError:
                        lines_skipped += 1
                        continue
                    counter += 1
                    f.write("%s\t%s\n" % (chrom, length))
                f.close()
                dbkeys[key] = { "name": name, "len": new_len.id, "count": counter }
        user.preferences['dbkeys'] = to_json_string(dbkeys)
        trans.sa_session.flush()
        return trans.fill_template( 'user/dbkeys.mako',
                                    user=user,
                                    dbkeys=dbkeys,
                                    message=message,
                                    installed_len_files=self.installed_len_files,
                                    lines_skipped=lines_skipped,
                                    use_panels=kwds.get( 'use_panels', None ) )          
    @web.expose
    @web.require_login()
    def api_keys( self, trans, cntrller, **kwd ):
        params = util.Params( kwd )
        message = util.restore_text( params.get( 'message', ''  ) )
        status = params.get( 'status', 'done' )
        if params.get( 'new_api_key_button', False ):
            new_key = trans.app.model.APIKeys()
            new_key.user_id = trans.user.id
            new_key.key = trans.app.security.get_new_guid()
            trans.sa_session.add( new_key )
            trans.sa_session.flush()
            message = "Generated a new web API key"
            status = "done"
        return trans.fill_template( 'webapps/galaxy/user/api_keys.mako',
                                    cntrller=cntrller,
                                    user=trans.user,
                                    message=message,
                                    status=status )

    # ===== Methods for building SelectFields  ================================
    def __build_user_type_fd_id_select_field( self, trans, selected_value ):
        # Get all the user information forms
        user_info_forms = self.get_all_forms( trans,
                                              filter=dict( deleted=False ),
                                              form_type=trans.model.FormDefinition.types.USER_INFO )
        return build_select_field( trans,
                                   objs=user_info_forms,
                                   label_attr='name',
                                   select_field_name='user_type_fd_id',
                                   initial_value='none',
                                   selected_value=selected_value,
                                   refresh_on_change=True )
