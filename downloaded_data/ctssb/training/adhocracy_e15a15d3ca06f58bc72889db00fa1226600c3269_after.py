import urllib
from datetime import datetime

from pylons.i18n import _
from babel import Locale

import adhocracy.lib.text as text
from adhocracy.lib.base import *
import adhocracy.forms as forms
import adhocracy.i18n as i18n
import adhocracy.lib.util as libutil
import adhocracy.lib.mail as libmail


log = logging.getLogger(__name__)

        
class UserCreateForm(formencode.Schema):
    allow_extra_fields = True
    user_name = formencode.All(validators.PlainText(),
                              forms.UniqueUsername())
    email = formencode.All(validators.Email(),
                           forms.UniqueEmail())
    password = validators.UnicodeString(not_empty=True)
    password_confirm = validators.UnicodeString(not_empty=True)
    chained_validators = [validators.FieldsMatch(
         'password', 'password_confirm')]

         
class UserUpdateForm(formencode.Schema):
    allow_extra_fields = True
    display_name = validators.String(not_empty=False)
    email = validators.Email(not_empty=True)
    locale = validators.String(not_empty=False)
    password = validators.UnicodeString(not_empty=False)
    password_confirm = validators.UnicodeString(not_empty=False)
    chained_validators = [validators.FieldsMatch(
        'password', 'password_confirm')]
    bio = validators.String(max=1000, min=0, not_empty=False)
    email_priority = validators.Int(min=0, max=6, not_empty=False, if_missing=3)
    twitter_priority = validators.Int(min=0, max=6, not_empty=False, if_missing=3)

    
class UserCodeForm(formencode.Schema):
    allow_extra_fields = True
    c = validators.String(not_empty=False)

    
class UserManageForm(formencode.Schema):
    allow_extra_fields = True
    group = forms.ValidGroup()


class UserResetApplyForm(formencode.Schema):
    allow_extra_fields = True
    email = validators.Email(not_empty=True)

    
class UserGroupmodForm(formencode.Schema):
    allow_extra_fields = True
    to_group = forms.ValidGroup()

    
class UserFilterForm(formencode.Schema):
    allow_extra_fields = True
    users_q = validators.String(max=255, not_empty=False, if_empty=u'', if_missing=u'')
    users_group = validators.String(max=255, not_empty=False, if_empty=None, if_missing=None)


class UserController(BaseController):
    
    @RequireInstance
    @validate(schema=UserFilterForm(), post_only=False, on_get=True)
    def index(self, format='html'):
        require.user.index()
        #query = self.form_result.get('users_q')
        #c.users = libsearch.query.run(query + u"*", entity_type=model.User,
        #    instance_filter=True)
        
        c.users = model.User.all(c.instance if c.instance else None)
        
        if c.instance:
            c.tile = tiles.instance.InstanceTile(c.instance)
            
            #group = self.form_result.get('users_group')
            #if group:
            #    c.users = [u for u in c.users if \
            #               u.instance_membership(c.instance).group.code == group]
        
        if format == 'json':
            return render_json(c.users_pager)
        
        c.users_pager = pager.users(c.users) #, has_query=query is not None)
        return render("/user/index.html")
    
    
    def new(self):
        return render("/user/login.html")
    
    
    @RequireInternalRequest(methods=['POST'])
    @validate(schema=UserCreateForm(), form="new", post_only=True)
    def create(self):
        require.user.create()
        user = model.User.create(self.form_result.get("user_name"), 
                                 self.form_result.get("email").lower(), 
                                 password=self.form_result.get("password").encode('utf-8'), 
                                 locale=c.locale)
        model.meta.Session.commit()
            
        event.emit(event.T_USER_CREATE, user)
        libmail.send_activation_link(user)
        
        if c.instance:
            membership = model.Membership(user, c.instance, 
                                          c.instance.default_group)
            model.meta.Session.expunge(membership)
            model.meta.Session.add(membership)
            model.meta.Session.commit()
        redirect("/perform_login?%s" % urllib.urlencode({
                 'login': self.form_result.get("user_name").encode('utf-8'),
                 'password': self.form_result.get("password").encode('utf-8')
                }))
    
    
    @ActionProtector(has_permission("user.edit"))
    def edit(self, id):
        c.page_user = get_entity_or_abort(model.User, id, instance_filter=False)
        require.user.edit(c.page_user)
        c.locales = i18n.LOCALES
        return render("/user/edit.html")
    
    
    @RequireInternalRequest(methods=['POST'])
    @ActionProtector(has_permission("user.edit"))
    @validate(schema=UserUpdateForm(), form="edit", post_only=True)
    def update(self, id):
        c.page_user = get_entity_or_abort(model.User, id, instance_filter=False)
        require.user.edit(c.page_user)
        if self.form_result.get("password"):
            c.page_user.password = self.form_result.get("password").encode('utf-8')
        c.page_user.display_name = self.form_result.get("display_name")
        c.page_user.bio = text.cleanup(self.form_result.get("bio"))
        email = self.form_result.get("email").lower()
        email_changed = email != c.page_user.email
        c.page_user.email = email
        c.page_user.email_priority = self.form_result.get("email_priority")
        if c.page_user.twitter:
            c.page_user.twitter.priority = self.form_result.get("twitter_priority")
            model.meta.Session.add(c.page_user.twitter)
        locale = Locale(self.form_result.get("locale"))
        if locale and locale in i18n.LOCALES:
            c.page_user.locale = locale 
        model.meta.Session.add(c.page_user)
        model.meta.Session.commit()
        if email_changed:
            libmail.send_activation_link(c.page_user)       
        
        if c.page_user == c.user:
            event.emit(event.T_USER_EDIT, c.user)
        else:
            event.emit(event.T_USER_ADMIN_EDIT, c.page_user, admin=c.user)
        redirect(h.entity_url(c.page_user))
    
    
    def reset_form(self):
        return render("/user/reset_form.html")
    
    
    @validate(schema=UserResetApplyForm(), form="reset", post_only=True)
    def reset_request(self):
        c.page_user = model.User.find_by_email(self.form_result.get('email'))
        if c.page_user is None:
            msg = _("There is no user registered with that email address.")
            return htmlfill.render(self.reset_form(), errors=dict(email=msg))
        c.page_user.reset_code = libutil.random_token()
        model.meta.Session.add(c.page_user)
        model.meta.Session.commit()
        url = h.instance_url(c.instance, path="/user/%s/reset?c=%s" % (c.page_user.user_name, c.page_user.reset_code))
        body = _("you have requested that your password be reset. In order to" 
                 +  " confirm the validity of your claim, please open the link below in your"
                 +  " browser:") + "\r\n\r\n  " + url 
        libmail.to_user(c.page_user, _("Reset your password"), body)
        return render("/user/reset_pending.html")
    
    
    @validate(schema=UserCodeForm(), form="reset_form", post_only=False, on_get=True)
    def reset(self, id):
        c.page_user = get_entity_or_abort(model.User, id, instance_filter=False)
        try:
            if c.page_user.reset_code != self.form_result.get('c'):
                raise ValueError()
            new_password = libutil.random_token()
            c.page_user.password = new_password
            model.meta.Session.add(c.page_user)
            model.meta.Session.commit()
            body = _("your password has been reset. It is now:") + "\r\n\r\n  " + new_password + "\r\n\r\n" 
            body += _("Please login and change the password in your user settings.")     
            libmail.to_user(c.page_user, _("Your new password"), body)     
            h.flash(_("Success. You have been sent an email with your new password."))    
        except Exception:
            h.flash(_("The reset code is invalid. Please repeat the password recovery procedure."))
        redirect('/login')
    
    
    @validate(schema=UserCodeForm(), form="edit", post_only=False, on_get=True)
    def activate(self, id):
        c.page_user = get_entity_or_abort(model.User, id, instance_filter=False)
        require.user.edit(c.page_user)
        try:
            if c.page_user.activation_code != self.form_result.get('c'):
                raise ValueError()
            c.page_user.activation_code = None
            model.meta.Session.commit()
            h.flash(_("Your email has been confirmed."))
        except Exception:
            log.exception("Invalid activation code")
            h.flash(_("The activation code is invalid. Please have it resent."))
        redirect(h.entity_url(c.page_user, member='edit'))
    
    
    @RequireInternalRequest()
    def resend(self, id):
        c.page_user = get_entity_or_abort(model.User, id, instance_filter=False)
        require.user.edit(c.page_user)
        libmail.send_activation_link(c.page_user)
        h.flash(_("The activation link has been re-sent to your email address."))
        redirect(h.entity_url(c.page_user, member='edit'))
    
    
    def show(self, id, format='html'):
        c.page_user = get_entity_or_abort(model.User, id, instance_filter=False)
        require.user.show(c.page_user)
        
        if format == 'json':
            return render_json(c.page_user)
        
        query = model.meta.Session.query(model.Event)
        query = query.filter(model.Event.user==c.page_user)
        query = query.order_by(model.Event.time.desc())
        query = query.limit(50)  
        if format == 'rss':
            return event.rss_feed(query.all(), "%s Latest Actions" % c.page_user.name,
                                  h.instance_url(None, path='/user/%s' % c.page_user.user_name),
                                  c.page_user.bio)
        c.events_pager = pager.events(query.all())
        c.tile = tiles.user.UserTile(c.page_user)
        self._common_metadata(c.page_user, add_canonical=True)
        return render("/user/show.html")
    
    
    def delete(self, id):
        self.not_implemented()
    
    
    def login(self):
        session['came_from'] = request.params.get('came_from', 
                                                  h.instance_url(c.instance))
        session.save()
        return render('/user/login.html')
    
    
    def perform_login(self): 
        pass # managed by repoze.who
    
    
    def post_login(self):
        if c.user:
            url = h.instance_url(c.instance)
            if 'came_from' in session:
                url = session.get('came_from')
                del session['came_from']
                session.save()
            redirect(str(url))
        else:
            session.delete()
            return formencode.htmlfill.render(
                render("/user/login.html"), 
                errors = {"login": _("Invalid user name or password")})
    
    
    def logout(self): pass # managed by repoze.who


    def post_logout(self):
        session.delete()
        redirect(h.instance_url(c.instance))
    
    
    @ActionProtector(has_permission("user.view"))    
    def complete(self):
        prefix = unicode(request.params.get('q', u''))
        users = model.User.complete(prefix, 15)
        results = []
        for user in users:
            if user == c.user: continue
            display = "%s (%s)" % (user.user_name, user.name) if \
                      user.display_name else user.name
            results.append(dict(display=display, user=user.user_name))
        return render_json(results)
    
        
    @RequireInstance
    def votes(self, id, format='html'):
        c.page_user = get_entity_or_abort(model.User, id, instance_filter=False)
        require.user.show(c.page_user)
        decisions = democracy.Decision.for_user(c.page_user, c.instance)
                
        if format == 'json':
            return render_json(list(decisions))
        
        decisions = filter(lambda d: d.poll.action != model.Poll.RATE, decisions)
        c.decisions_pager = pager.user_decisions(decisions)
        self._common_metadata(c.page_user, member='votes')
        return render("/user/votes.html")
    
    
    @RequireInstance
    def delegations(self, id, format='html'):
        c.page_user = get_entity_or_abort(model.User, id, instance_filter=False)
        require.user.show(c.page_user)
        scope_id = request.params.get('scope', None)
        
        if format == 'json':
            delegations = model.Delegation.find_by_principal(c.page_user)
            scope = model.Delegateable.find(scope_id) if scope_id else None
            if scope is not None:
                delegations = [d for d in delegations if d.is_match(scope)]
            delegations_pager = pager.delegations(delegations)
            return render_json(delegations_pager)
        
        c.dgbs = []
        if scope_id:
            c.scope = forms.ValidDelegateable().to_python(scope_id)
            c.dgbs = [c.scope] + c.scope.children
        else:
            c.dgbs = model.Delegateable.all(instance=c.instance)  
        c.nodeClass = democracy.DelegationNode 
        self._common_metadata(c.page_user, member='delegations')
        return render("/user/delegations.html")
    
    
    def instances(self, id, format='html'):
        c.page_user = get_entity_or_abort(model.User, id, instance_filter=False)
        require.user.show(c.page_user)
        instances = [i for i in c.page_user.instances if i.is_shown()]
        c.instances_pager = pager.instances(instances)
        
        if format == 'json':
            return render_json(c.instances_pager)
        
        self._common_metadata(c.page_user, member='instances', add_canonical=True)
        return render("/user/instances.html")
    
        
    @RequireInstance
    def proposals(self, id, format='html'):
        c.page_user = get_entity_or_abort(model.User, id, instance_filter=False)
        require.user.show(c.page_user)
        proposals = model.Proposal.find_by_creator(c.page_user)
        c.proposals_pager = pager.proposals(proposals)
        
        if format == 'json':
            return render_json(c.proposals_pager)
        
        self._common_metadata(c.page_user, member='proposals')
        return render("/user/proposals.html")
    
        
    #@RequireInstance
    #@ActionProtector(has_permission("user.view")) 
    #def comments(self, id, format='html'):
    #    c.page_user = get_entity_or_abort(model.User, id, instance_filter=False)
    #    comments = filter(lambda cm: cm.topic.instance == c.instance and \
    #                      not cm.is_deleted(), c.page_user.comments)
    #    
    #    if format == 'json':
    #        return render_json(list(comments))
    #    
    #    c.comments_pager = pager.comments(comments)
    #    self._common_metadata(c.page_user, member='comments')
    #    return render("/user/comments.html")
      
    
    def watchlist(self, id, format='html'):
        require.watch.index()
        c.page_user = get_entity_or_abort(model.User, id, instance_filter=False)
        require.user.show(c.page_user)
        watches = model.Watch.all_by_user(c.page_user)
        entities = [w.entity for w in watches if not isinstance(w.entity, unicode)]
        c.entities_pager = NamedPager('watches', entities, tiles.dispatch_row, 
                                      sorts={_("oldest"): sorting.entity_oldest,
                                             _("newest"): sorting.entity_newest},
                                      default_sort=sorting.entity_newest)
        
        if format == 'json':
            return render_json(c.entities_pager)

        self._common_metadata(c.page_user, member='watchlist')
        return render("/user/watchlist.html")    
        
    
    @RequireInstance
    @RequireInternalRequest()
    @validate(schema=UserGroupmodForm(), form="edit", post_only=False, on_get=True)
    def groupmod(self, id):
        c.page_user = get_entity_or_abort(model.User, id)
        require.user.supervise(c.page_user)
        to_group = self.form_result.get("to_group")
        if not to_group.code in model.Group.INSTANCE_GROUPS:
            h.flash("Cannot make %(user)s a member of %(group)s" % {
                        'user': c.page_user.name, 
                        'group': group.group_name})
            redirect(h.entity_url(c.page_user))
        had_vote = c.page_user._has_permission("vote.cast")
        for membership in c.page_user.memberships:
            if not membership.is_expired() and membership.instance == c.instance:
                membership.expire()
        new_membership = model.Membership(c.page_user, c.instance, to_group)
        model.meta.Session.add(new_membership)
        model.meta.Session.commit()
        event.emit(event.T_INSTANCE_MEMBERSHIP_UPDATE, c.page_user, 
                   instance=c.instance, group=to_group, admin=c.user)
        if had_vote and not c.page_user._has_permission("vote.cast"):
            # user has lost voting privileges
            c.page_user.revoke_delegations(c.instance)
        model.meta.Session.commit()
        redirect(h.entity_url(c.page_user))
    
    
    @RequireInstance
    @RequireInternalRequest()
    def kick(self, id):
        c.page_user = get_entity_or_abort(model.User, id)
        require.user.supervise(c.page_user)
        for membership in c.page_user.memberships:
            if not membership.is_expired() and membership.instance == c.instance:
                membership.expire()
                model.meta.Session.add(membership)
        c.page_user.revoke_delegations(c.instance)
        model.meta.Session.commit()
        event.emit(event.T_INSTANCE_FORCE_LEAVE, c.page_user, instance=c.instance, 
                   admin=c.user)        
        h.flash(_("%(user)s was removed from %(instance)s") % {
                                        'user': c.page_user.name, 
                                        'instance': c.instance.label})
        redirect(h.entity_url(c.page_user))
    
    
    @validate(schema=UserFilterForm(), post_only=False, on_get=True)
    def filter(self):
        require.user.index()
        query = self.form_result.get('users_q')
        users = libsearch.query.run(query + u"*", entity_type=model.User,
                                    instance_filter=True)
        c.users_pager = pager.users(users, has_query=True)
        return c.users_pager.here()


    def _common_metadata(self, user, member=None, add_canonical=False):
        bio = user.bio
        if not bio:
            bio = _("%(user)s is using Adhocracy, a democratic decision-making tool.") % {
                    'user': c.page_user.name}
        description = h.text.truncate(text.meta_escape(bio), length=200, whole_word=True) 
        h.add_meta("description", description)
        h.add_meta("dc.title", text.meta_escape(user.name))
        h.add_meta("dc.date", user.access_time.strftime("%Y-%m-%d"))
        h.add_meta("dc.author", text.meta_escape(user.name))
        h.add_rss(_("%(user)ss Activity") % {'user': user.name}, 
                  h.entity_url(user, format='rss'))      
        canonical_url = h.entity_url(user, instance=None)
        if member is not None:
            canonical_url += u"/" + member
        h.canonical_url(canonical_url)                  
        if c.instance and not user.is_member(c.instance):
            h.flash(_("%s is not a member of %s") % (user.name, c.instance.label))  
        
