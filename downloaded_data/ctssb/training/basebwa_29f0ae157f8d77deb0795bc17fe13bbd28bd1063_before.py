# -*- coding: utf-8 -*-
import datetime
from pysmvt import redirect, session, ag, appimportauto, settings, modimportauto
from pysmvt import user as usr
from pysmvt.exceptions import ActionError
from pysmvt.routing import url_for, current_url
from pysmvt.htmltable import Col, YesNo, Link, Table

appimportauto('base', ('ProtectedPageView', 'ProtectedRespondingView',
    'PublicPageView', 'PublicTextSnippetView', 'ManageCommon', 'UpdateCommon',
    'DeleteCommon'))
modimportauto('users.actions', ('user_validate','load_session_user',
    'user_assigned_perm_ids', 'user_group_ids', 'user_get',
    'user_update_password', 'user_get_by_login', 'load_session_user',
    'user_kill_reset_key', 'user_lost_password', 'user_permission_map',
    'user_permission_map_groups', 'group_user_ids', 'group_assigned_perm_ids',
    'user_update'))
modimportauto('users.utils', ('after_login_url'))
modimportauto('users.forms', ('ChangePasswordForm', 'NewPasswordForm',
    'LostPasswordForm', 'LoginForm'))
_modname = 'users'

class UserUpdate(UpdateCommon):
    def prep(self):
        UpdateCommon.prep(self, _modname, 'user', 'User')

    def auth(self, id):
        UpdateCommon.auth(self)
        
        # prevent non-super users from editing super users
        if id:
            sess_user_obj = user_get(usr.get_attr('id'))
            edited_user_obj = user_get(id)
            if edited_user_obj.super_user and not sess_user_obj.super_user:
                self.is_authorized = False

    def post_auth_setup(self, id):
        self.determine_add_edit(id)
        self.form = self.formcls(self.isAdd)
        if not self.isAdd:
            self.dbobj = self.action_get(id)
            if self.dbobj is None:
                user.add_message('error', self.message_exists_not % {'objectname':self.objectname})
                self.on_edit_error()
            vals = self.dbobj.to_dict()
            vals['assigned_groups'] = user_group_ids(self.dbobj)
            vals['approved_permissions'], vals['denied_permissions'] = user_assigned_perm_ids(self.dbobj)
            self.form.set_defaults(vals)

class UserManage(ManageCommon):
    def prep(self):
        ManageCommon.prep(self, _modname, 'user', 'users', 'User')
        
    def create_table(self):
        def determine_inactive(user):
            return user.inactive
        
        ManageCommon.create_table(self)
        t = self.table
        t.login_id = Col('Login Id')
        t.name = Col('Name')
        t.super_user = YesNo('Super User')
        t.reset_required = YesNo('Reset Required')
        t.inactive = YesNo('Inactive', extractor=determine_inactive)
        t.permission_map = Link( 'Permission Map',
                 validate_url=False,
                 urlfrom=lambda uobj: url_for('users:PermissionMap', uid=uobj.id),
                 extractor = lambda row: 'view permission map'
            )

class UserDelete(DeleteCommon):
    def prep(self):
        DeleteCommon.prep(self, _modname, 'user', 'User')
    
    def auth(self, id):
        DeleteCommon.auth(self)
        
        # prevent non-super users from deleting super users
        if id:
            sess_user_obj = user_get(usr.get_attr('id'))
            edited_user_obj = user_get(id)
            if edited_user_obj.super_user and not sess_user_obj.super_user:
                self.is_authorized = False

    def default(self, id):
        if id == usr.get_attr('id'):
            usr.add_message('error', 'You cannot delete your own user account')
            self.on_complete()
        DeleteCommon.default(self, id)

class ChangePassword(ProtectedPageView):
    def prep(self):
        self.authenticated_only = True
    
    def post_auth_setup(self):
        self.form = ChangePasswordForm()

    def post(self):
        if self.form.is_valid():
            user_update_password(usr.get_attr('id'), **self.form.get_values())
            usr.add_message('notice', 'Your password has been changed successfully.')
            url = after_login_url()
            redirect(url)
        elif self.form.is_submitted():
            # form was submitted, but invalid
            self.form.assign_user_errors()
            
        self.default()

    def default(self):

        self.assign('formHtml', self.form.render())
        
class ResetPassword(PublicPageView):
    
    def setup(self, login_id, key):
        # this probably should never happen, but doesn't hurt to check
        if not key or not login_id:
            self.abort()
        user = user_get_by_login(login_id)
        if not user:
            self.abort()
        if key != user.pass_reset_key:
            self.abort()
        expires_on = user.pass_reset_ts + datetime.timedelta(hours=settings.modules.users.password_rest_expires_after)
        if datetime.datetime.utcnow() > expires_on:
            self.abort('password reset link expired')
    
        self.user = user
        self.form = NewPasswordForm()

    def post(self, login_id, key):
        if self.form.is_valid():
            user_update_password(self.user.id, **self.form.get_values())
            usr.add_message('notice', 'Your password has been reset successfully.')
            
            # at this point, the user has been verified, and we can setup the user
            # session and kill the reset 
            load_session_user(self.user)
            user_kill_reset_key(self.user)
            
            # redirect as if this was a login
            url = after_login_url()
            redirect(url)
        elif self.form.is_submitted():
            # form was submitted, but invalid
            self.form.assign_user_errors()
        self.assign_form()
        
    def get(self, login_id, key):
        usr.add_message('Notice', "Please choose a new password to complete the reset request.")
        self.assign_form()

    def assign_form(self):
        self.assign('form', self.form)

    def abort(self, msg='invalid reset request'):
        usr.add_message('error', '%s, use the form below to resend reset link' % msg)
        url = url_for('users:LostPassword')
        redirect(url)

class LostPassword(PublicPageView):
    def setup(self):
        self.form = LostPasswordForm()

    def post(self):
        if self.form.is_valid():
            em_address = self.form.email_address.value
            if user_lost_password(em_address):
                usr.add_message('notice', 'An email with a link to reset your password has been sent.')
                url = current_url(root_only=True)
                redirect(url)
            else:
                usr.add_message('error', 'Did not find a user with email address: %s' % em_address)
        elif self.form.is_submitted():
            # form was submitted, but invalid
            self.form.assign_user_errors()

        self.default()

    def default(self):

        self.assign('formHtml', self.form.render())

class UserProfile(UpdateCommon):
    def prep(self):
        UpdateCommon.prep(self, _modname, 'user', 'UserProfile')
        self.authenticated_only = True
        self.actionname = 'Update'
        self.objectname = 'Profile'
        
    def post_auth_setup(self):
        self.assign_form()
        self.user_id = usr.get_attr('id')
        dbobj = user_get(self.user_id)

        if dbobj is None:
            usr.add_message('error', self.message_exists_not % {'objectname':self.objectname})
            self.on_edit_error()

        self.form.set_defaults(dbobj.to_dict())        
        self.dbobj = dbobj
        
    def on_cancel(self):
        usr.add_message('notice', 'no changes made to your profile')
        redirect(current_url(root_only=True))
        
    def do_update(self, id):
        formvals = self.form.get_values()
        # assigned groups and permissions stay the same for profile submissions
        formvals['assigned_groups'] = user_group_ids(self.dbobj)
        formvals['approved_permissions'], formvals['denied_permissions'] = \
                user_assigned_perm_ids(self.dbobj)
        formvals['pass_reset_ok'] = False
        user_update(id, **formvals)
        usr.add_message('notice', 'profile updated succesfully')
        self.default()
    
    def post(self):        
        UpdateCommon.post(self, self.user_id)
    
    def default(self, id=None):
        UpdateCommon.default(self, self.user_id)
    
class PermissionMap(ProtectedPageView):
    def prep(self):
        self.require = ('users-manage')
    
    def default(self, uid):
        self.assign('user', user_get(uid))
        self.assign('result', user_permission_map(uid))
        self.assign('permgroups', user_permission_map_groups(uid))

class Login(PublicPageView):
    
    def setup(self):
        self.form = LoginForm()
    
    def post(self):        
        if self.form.is_valid():
            user = user_validate(**self.form.get_values())
            if user:
                if user.inactive:
                    usr.add_message('error', 'That user is inactive.')
                else:
                    load_session_user(user)
                    usr.add_message('notice', 'You logged in successfully!')
                    if user.reset_required:
                        url = url_for('users:ChangePassword')
                    else:
                        url = after_login_url()
                    redirect(url)
            else:
                usr.add_message('error', 'Login failed!  Please try again.')
        elif self.form.is_submitted():
            # form was submitted, but invalid
            self.form.assign_user_errors()
            
        self.default()
    
    def default(self):
        
        self.assign('formHtml', self.form.render())

class Logout(PublicPageView):
        
    def default(self):
        session.invalidate()
            
        url = url_for('users:Login')
        redirect(url)
        
class GroupUpdate(UpdateCommon):
    def prep(self):
        UpdateCommon.prep(self, _modname, 'group', 'Group')

    def post_auth_setup(self, id):
        self.determine_add_edit(id)
        self.form = self.formcls()
        if not self.isAdd:
            self.dbobj = self.action_get(id)
            if self.dbobj is None:
                usr.add_message('error', self.message_exists_not % {'objectname':self.objectname})
                self.on_edit_error()
            vals = self.dbobj.to_dict()
            vals['assigned_users'] = group_user_ids(self.dbobj)
            vals['approved_permissions'], vals['denied_permissions'] = group_assigned_perm_ids(self.dbobj)
            self.form.set_defaults(vals)

class GroupManage(ManageCommon):
    def prep(self):
        ManageCommon.prep(self, _modname, 'group', 'groups', 'Group')
        self.table = Table(class_='dataTable manage', style="width: 60%")
        
    def create_table(self):
        ManageCommon.create_table(self)
        t = self.table
        t.name = Col('Name')
        
class GroupDelete(DeleteCommon):
    def prep(self):
        DeleteCommon.prep(self, _modname, 'group', 'Group')

class PermissionUpdate(UpdateCommon):
    def prep(self):
        UpdateCommon.prep(self, _modname, 'permission', 'Permission')

class PermissionManage(ManageCommon):
    def prep(self):
        ManageCommon.prep(self, _modname, 'permission', 'permissions', 'Permission')
        self.delete_link_require = None
        self.template_name = 'permission_manage'
        
    def create_table(self):
        ManageCommon.create_table(self)
        t = self.table
        t.name = Col('Permission', width_td="35%")
        t.description = Col('Description')

class NewUserEmail(PublicTextSnippetView):
    def default(self, login_id, password):
        self.assign('login_id', login_id)
        self.assign('password', password)
        
        self.assign('login_url', url_for('users:Login', _external=True))
        self.assign('index_url', current_url(root_only=True))
        
class ChangePasswordEmail(PublicTextSnippetView):
    def default(self, login_id, password):
        self.assign('login_id', login_id)
        self.assign('password', password)

        self.assign('login_url', url_for('users:Login', _external=True))
        self.assign('index_url', current_url(root_only=True))

class PasswordResetEmail(PublicTextSnippetView):
    def default(self, user):
        self.assign('user', user)
