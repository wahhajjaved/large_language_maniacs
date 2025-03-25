#!/usr/bin/python
# -*- coding: utf-8 -*-

from django.db import models, connection
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.conf import settings
from django.shortcuts import get_object_or_404

from django.utils.translation import ugettext_lazy as _

from easy_thumbnails.fields import ThumbnailerImageField

from valuenetwork.valueaccounting.models import *
from fobi.models import FormEntry

from mptt.fields import TreeForeignKey

if "pinax.notifications" in settings.INSTALLED_APPS:
    from pinax.notifications import models as notification
else:
    notification = None


def get_site_name(request=None):
    if request:
        domain = request.get_host()
        try:
            obj = settings.PROJECTS_LOGIN
            for pro in obj:
                if obj[pro]['domains']:
                    if domain in obj[pro]['domains']:
                        proj = get_object_or_404(Project, fobi_slug=pro)
                        if proj:
                            return proj.agent.name
        except:
            pass
    return Site.objects.get_current().name



MEMBERSHIP_TYPE_CHOICES = (
    #('participant', _('project participant (no membership)')),
    ('individual', _('individual membership (min 1 share)')),
    ('collective', _('collective membership (min 2 shares)')),
)

REQUEST_STATE_CHOICES = (
    ('new', _('new')),
    ('accepted', _('accepted')),
    ('declined', _('declined')),
)

class MembershipRequest(models.Model):
    request_date = models.DateField(auto_now_add=True, blank=True, null=True, editable=False)
    name = models.CharField(_('Name'), max_length=255)
    surname = models.CharField(_('Surname (for individual memberships)'), max_length=255, blank=True)
    requested_username = models.CharField(_('Requested username'), max_length=32)
    email_address = models.EmailField(_('Email address'), max_length=96,)
    #    help_text=_("this field is optional, but we can't contact you via email without it"))
    phone_number = models.CharField(_('Phone number'), max_length=32, blank=True, null=True)
    address = models.CharField(_('Where do you live?'), max_length=255, blank=True)
    native_language = models.CharField(_('Languages'), max_length=255, blank=True)
    type_of_membership = models.CharField(_('Type of membership'),
        max_length=12, choices=MEMBERSHIP_TYPE_CHOICES,
        default="individual")
    #membership_for_services = models.BooleanField(_('Membership for services'), default=False,
    #    help_text=_('you have legal entity and want to offer services or products to the cooperative'))
    #autonomous_membership = models.BooleanField(_('Autonomous membership'), default=False,
    #    help_text=_("you don't have legal entity and want to use the cooperative to make invoices either from inside and to outside the cooperative"))
    #ocp_user_membership = models.BooleanField(_('OCP user membership'), default=False,
    #    help_text=_('for those that only want to use the OCP platform'))
    #consumer_membership = models.BooleanField(_('Consumer membership'), default=False,
    #    help_text=_("you don't offer any product or service but want to consume through it and support the cooperative"))
    number_of_shares = models.IntegerField(_('Number of shares'),
        default=1,
        help_text=_("How many shares would you like to underwrite? Each share is worth 30 Euros"))
    #work_for_shares = models.BooleanField(_('work for one share'), default=False,
    #    help_text=_("You can get 1 share for 6 hours of work. If you choose this option, we will send you a list of tasks and the deadline. You won't have full access before the tasks are accomplished."))
    description = models.TextField(_('Description'),
        help_text=_("Describe your project or collective and the skills or abilities you can offer the cooperative"))
    website = models.CharField(_('Website'), max_length=255, blank=True)
    fairnetwork = models.CharField(_('FairNetwork username'), max_length=255, blank=True,
        help_text = _("The username you use in the FairNetwork at <a href='https://fair.coop' target='_blank'>fair.coop</a>"))
    usefaircoin = models.CharField(_('UseFaircoin profile'), max_length=255, blank=True,
        help_text = _("If you are in the directory at <a href='https://use.fair-coin.org' target='_blank'>use.fair-coin.org</a> please add the URL to your profile."))
    fairmarket = models.CharField(_('FairMarket shop'), max_length=255, blank=True,
        help_text = _("If you have an online shop at <a href='https://market.fair.coop' target='_blank'>market.fair.coop</a> please add the URL to your fair shop."))
    #how_do_you_know_fc = models.TextField(_('How do you know Freedom Coop?'), blank=True,)
    known_member = models.CharField(_('Are there any FairCoop participant(s) who can give references about you? If so, who?'), max_length=255, blank=True)
    comments_and_questions = models.TextField(_('Comments and questions'), blank=True,)

    agent = models.ForeignKey(EconomicAgent,
        verbose_name=_('agent'), related_name='membership_requests',
        blank=True, null=True,
        help_text=_("this membership request became this EconomicAgent"))
    state = models.CharField(_('state'),
        max_length=12, choices=REQUEST_STATE_CHOICES,
        default='new', editable=False)

    def __unicode__(self):
        return self.name


JOINING_STYLE_CHOICES = (
    ('moderated', _('moderated')),
    ('autojoin', _('autojoin')),
)

VISIBILITY_CHOICES = (
    ('private', _('private')),
    ('FCmembers', _('only FC members')),
    ('public', _('public')),
)

SELECTION_CHOICES = (
    ('project', _('your project')),
    #('related', _('all related projects')),
    ('all', _('all platform')),
)

class Project(models.Model):
    agent = models.OneToOneField(EconomicAgent,
        verbose_name=_('agent'), related_name='project')
    joining_style = models.CharField(_('joining style'),
        max_length=12, choices=JOINING_STYLE_CHOICES,
        default="autojoin")
    visibility = models.CharField(_('visibility'),
        max_length=12, choices=VISIBILITY_CHOICES,
        default="FCmembers")
    resource_type_selection = models.CharField(_('resource type selection'),
        max_length=12, choices=SELECTION_CHOICES,
        default="all")
    fobi_slug = models.CharField(_('custom form slug'),
        max_length=255, blank=True)

    #fobi_form = models.OneToOneField(FormEntry,
    #    verbose_name=_('custom form'), related_name='project',
    #    blank=True, null=True,
    #    help_text=_("this Project use this custom form (fobi FormEntry)"))
    #join_request = models.ForeignKey(JoinRequest,
    #    verbose_name=_('join request'), related_name='project',
    #    blank=True, null=True,
    #    help_text=_("this Project is using this JoinRequest form"))

    def __unicode__(self):
        return _('Project: ') + self.agent.name

    def is_moderated(self):
        return self.joining_style == 'moderated'

    def is_public(self):
        return self.visibility == 'public'

    def fobi_form(self):
        if self.fobi_slug:
            try:
                entry = FormEntry.objects.get(slug=self.fobi_slug)
                return entry
            except:
                pass
        return False

    def rts_with_clas(self, clas=None):
        rts_with_clas = []
        rts = list(set([arr.resource.resource_type for arr in self.agent.resource_relationships()]))
        for rt in rts:
            if hasattr(rt, 'ocp_artwork_type') and rt.ocp_artwork_type and rt.ocp_artwork_type.clas:
                if clas:
                    if clas == rt.ocp_artwork_type.clas:
                        rts_with_clas = rt
                else:
                    rts_with_clas.append(rt)
        return rts_with_clas

    def share_types(self):
        shr_ts = []
        if self.is_moderated() and self.fobi_slug:
            form = self.fobi_form()
            if form:
              fields = form.formelemententry_set.all()
              for fi in fields:
                data = json.loads(fi.plugin_data)
                name = data.get('name')
                for rt in self.rts_with_clas():
                    if rt.ocp_artwork_type.clas == name: # matches the rt clas identifier with the fobi field name
                        choi = data.get('choices')
                        if choi:
                            opts = choi.split('\r\n')
                            for op in opts:
                                opa = op.split(',')
                                shr_ts.append(opa[1].strip())
                        else:
                            #import pdb; pdb.set_trace()
                            text = data.get('help_text')
                            opts = text.split('\r\n')
                            for op in opts:
                                shr_ts.append(op.strip(' /'))

            if len(shr_ts):
                return shr_ts
        return False

    def share_totals(self):
        shr_ts = self.share_types()
        shares_res = None
        total = 0
        self.holders = 0
        if shr_ts:
            rts = self.rts_with_clas()
            shr_rt = None
            for rt in rts:
                if rt.ocp_artwork_type.general_unit_type:
                    if rt.ocp_artwork_type.general_unit_type.clas == 'share':
                        shr_rt = rt
            if shr_rt:
                shares_res = EconomicResource.objects.filter(resource_type=shr_rt)
        if shares_res:
            for res in shares_res:
                if res.price_per_unit:
                    total += res.price_per_unit
                    self.holders += 1
        return total

    def share_holders(self):
        if self.share_totals():
            return self.holders

    def payment_options(self):
        pay_opts = []
        if self.is_moderated() and self.fobi_slug:
            form = self.fobi_form()
            if form:
              fields = form.formelemententry_set.all()
              for fi in fields:
                data = json.loads(fi.plugin_data)
                name = data.get('name')
                if name == "payment_mode": # name of the fobi field
                    choi = data.get('choices')
                    if choi:
                        opts = choi.split('\r\n')
                        for op in opts:
                            opa = op.split(',')
                            key = opa[0].strip()
                            val = opa[1].strip()
                            ok = '<span class="error">config pending!</span>'
                            gates = self.payment_gateways()
                            if gates:
                                try:
                                    gate = gates[key]
                                except:
                                    gate = None
                                if gate is not None:
                                    ok = '<span style="color:#090">ok:</span>'
                                    if gate['html']:
                                        ok += ' <ul><li>'+str(gate['html'])+'</li></ul>'
                            pay_opts.append(val+' &nbsp;'+ok)
              return pay_opts
        return False

    def background_url(self):
        back = False
        if settings.PROJECTS_LOGIN and self.fobi_slug:
            try:
                back = settings.PROJECTS_LOGIN[self.fobi_slug]['background_url']
            except:
                pass
        return back

    def custom_css(self):
        css = False
        if settings.PROJECTS_LOGIN and self.fobi_slug:
            try:
                css = settings.PROJECTS_LOGIN[self.fobi_slug]['css']
            except:
                pass
        return css

    def custom_js(self):
        js = False
        if settings.PROJECTS_LOGIN and self.fobi_slug:
            try:
                js = settings.PROJECTS_LOGIN[self.fobi_slug]['js']
            except:
                pass
        return js

    def custom_html(self):
        html = False
        if settings.PROJECTS_LOGIN and self.fobi_slug:
            try:
                html = settings.PROJECTS_LOGIN[self.fobi_slug]['html']
            except:
                pass
        return html

    def services(self):
        serv = False
        if settings.PROJECTS_LOGIN and self.fobi_slug:
            try:
                serv = settings.PROJECTS_LOGIN[self.fobi_slug]['services']
            except:
                pass
        return serv

    def custom_login(self):
        resp = False
        if settings.PROJECTS_LOGIN and self.fobi_slug:
            try:
                resp = settings.PROJECTS_LOGIN[self.fobi_slug]
            except:
                pass
        return resp

    def payment_gateways(self):
        gates = False
        if settings.PAYMENT_GATEWAYS and self.fobi_slug:
            try:
                gates = settings.PAYMENT_GATEWAYS[self.fobi_slug]
            except:
                pass
        return gates



class SkillSuggestion(models.Model):
    skill = models.CharField(_('skill'), max_length=128,
        help_text=_("A new skill that you want to offer that is not already listed"))
    suggested_by = models.ForeignKey(User, verbose_name=_('suggested by'),
        related_name='skill_suggestion', blank=True, null=True, editable=False)
    suggestion_date = models.DateField(auto_now_add=True, blank=True, null=True, editable=False)
    resource_type = models.ForeignKey(EconomicResourceType,
        verbose_name=_('resource_type'), related_name='skill_suggestions',
        blank=True, null=True,
        help_text=_("this skill suggestion became this ResourceType"))
    state = models.CharField(_('state'),
        max_length=12, choices=REQUEST_STATE_CHOICES,
        default='new', editable=False)


    def __unicode__(self):
        return self.skill

    def form_prefix(self):
        return "".join(["SS", str(self.id)])

    def resource_type_form(self):
        from valuenetwork.valueaccounting.forms import SkillSuggestionResourceTypeForm
        init = {
            "name": self.skill,
            }
        return SkillSuggestionResourceTypeForm(initial=init, prefix=self.form_prefix())


from nine.versions import DJANGO_LTE_1_5
from fobi.contrib.plugins.form_handlers.db_store.models import SavedFormDataEntry
import simplejson as json
import random
import hashlib

from django_comments.models import Comment

USER_TYPE_CHOICES = (
    #('participant', _('project participant (no membership)')),
    ('individual', _('individual')),
    ('collective', _('collective')),
)


class JoinRequest(models.Model):
    # common fields for all projects
    project = models.ForeignKey(Project,
        verbose_name=_('project'), related_name='join_requests',
        #blank=True, null=True,
        help_text=_("this join request is for joining this Project"))

    request_date = models.DateField(auto_now_add=True, blank=True, null=True, editable=False)
    type_of_user = models.CharField(_('Type of user *'),
        max_length=12, choices=USER_TYPE_CHOICES,
        default="individual",
        help_text=_("* Required fields"))
    name = models.CharField(_('Name *'), max_length=255)
    surname = models.CharField(_('Surname (for individual join requests)'), max_length=255, blank=True)
    requested_username = models.CharField(_('Username *'), max_length=32, help_text=_("If you have already an account in OCP, you can login before filling this form to have this project in the same account, or you can choose another username and email to have it separate."))
    email_address = models.EmailField(_('Email address *'), max_length=96,)
    #    help_text=_("this field is optional, but we can't contact you via email without it"))
    phone_number = models.CharField(_('Phone number'), max_length=32, blank=True, null=True)
    address = models.CharField(_('Town/Region where you are based'), max_length=255, blank=True, null=True)
    #native_language = models.CharField(_('Languages'), max_length=255, blank=True)

    #description = models.TextField(_('Description'),
    #    help_text=_("Describe your collective or the personal skills you can offer to the project"))

    agent = models.ForeignKey(EconomicAgent,
        verbose_name=_('agent'), related_name='project_join_requests',
        blank=True, null=True,
        help_text=_("this join request became this EconomicAgent"))

    fobi_data = models.OneToOneField(SavedFormDataEntry,
        verbose_name=_('custom fobi entry'), related_name='join_request',
        blank=True, null=True, on_delete=models.CASCADE,
        help_text=_("this join request is linked to this custom form (fobi SavedFormDataEntry)"))

    state = models.CharField(_('state'),
        max_length=12, choices=REQUEST_STATE_CHOICES,
        default='new', editable=False)

    exchange = models.OneToOneField(Exchange,
        verbose_name=_('exchange'), related_name='join_request',
        blank=True, null=True, on_delete=models.SET_NULL,
        help_text=_("this join request is linked to this Ocp Exchange"))

    """notes = models.CharField(_('request notes'),
        max_length=255, null=True, blank=True)"""

    def fobi_slug(self):
      if self.project.fobi_slug:
        return self.project.fobi_slug
      return False

    def __unicode__(self):
        return self.name

    def form_prefix(self):
        return "".join(["JR", str(self.id)])

    def full_name(self):
        if self.surname:
            answer = " ".join([self.name, self.surname])
        else:
            answer = self.name
        return answer

    def agent_type(self):
        if self.type_of_user == "individual":
            answer = AgentType.objects.individual_type()
        else:
            answer = None
        return answer

    def agent_form(self):
        from work.forms import ProjectAgentCreateForm
        init = {
            "name": self.full_name(),
            "nick": self.requested_username,
            "email": self.email_address,
            }
        agent_type = self.agent_type()
        if agent_type:
            init["agent_type"] = agent_type
        return ProjectAgentCreateForm(initial=init, prefix=self.form_prefix())

    def fobi_items_keys(self):
        fobi_headers = []
        fobi_keys = []
        if self.fobi_data and self.fobi_data.pk:
            self.entries = SavedFormDataEntry.objects.filter(pk=self.fobi_data.pk).select_related('form_entry')
            entry = self.entries[0]
            self.form_headers = json.loads(entry.form_data_headers)
            for val in self.form_headers:
                fobi_headers.append(self.form_headers[val])
                fobi_keys.append(val)
        return fobi_keys

    def fobi_items_data(self):
        self.items_data = None
        if self.fobi_data and self.fobi_data.pk:
            self.entries = SavedFormDataEntry.objects.filter(pk=self.fobi_data.pk).select_related('form_entry')
            entry = self.entries[0]
            self.data = json.loads(entry.saved_data)
            self.items = self.data.items()
            self.items_data = []
            for key in self.fobi_items_keys():
                self.items_data.append(self.data.get(key))
        return self.items_data

    def pending_shares(self):
        answer = ''
        account_type = self.payment_account_type()
        balance = 0
        amount = self.payment_amount()

        if self.agent and account_type:
            user_rts = list(set([arr.resource.resource_type for arr in self.agent.resource_relationships()]))
            for rt in user_rts:
                if rt == account_type: #.ocp_artwork_type:
                    rss = list(set([arr.resource for arr in self.agent.resource_relationships()]))
                    for rs in rss:
                        if rs.resource_type == rt:
                            balance = rs.price_per_unit # TODO: update the price_per_unit with wallet balance

        if amount:
            answer = amount - balance
            if answer > 0:
                #if self.payment_url and self.payment_secret and not self.payment_status:
                    #self.payment_status = 'pending'
                    #self.save()
                return int(answer)
            else:
                #import pdb; pdb.set_trace()
                return 0

        return False #'??'

    def total_shares(self):
        account_type = self.payment_account_type() #None
        balance = 0

        if self.agent and account_type:
            user_rts = list(set([arr.resource.resource_type for arr in self.agent.resource_relationships()]))
            for rt in user_rts:
                if rt == account_type: #.ocp_artwork_type:
                    rss = list(set([arr.resource for arr in self.agent.resource_relationships()]))
                    for rs in rss:
                        if rs.resource_type == rt:
                            balance = rs.price_per_unit # TODO: update the price_per_unit with wallet balance
        return balance

    def payment_option(self):
        answer = {}
        if self.project.joining_style == "moderated" and self.fobi_data:
            for key in self.fobi_items_keys():
                if key == "payment_mode": # fieldname specially defined in the fobi form
                    self.entries = SavedFormDataEntry.objects.filter(pk=self.fobi_data.pk).select_related('form_entry')
                    entry = self.entries[0]
                    self.data = json.loads(entry.saved_data)
                    val = self.data.get(key)
                    answer['val'] = val
                    for elem in self.fobi_data.form_entry.formelemententry_set.all():
                        data = json.loads(elem.plugin_data)
                        choi = data.get('choices') # works with radio or select
                        if choi:
                            opts = choi.split('\r\n')
                            for op in opts:
                                opa = op.split(',')
                                #import pdb; pdb.set_trace()
                                if val.strip() == opa[1].strip():
                                    answer['key'] = opa[0]
        return answer

    def payment_url(self):
        payopt = self.payment_option()
        obj = None
        if settings.PAYMENT_GATEWAYS and payopt:
            gates = settings.PAYMENT_GATEWAYS
            if self.project.fobi_slug and gates[self.project.fobi_slug]:
                try:
                    obj = gates[self.project.fobi_slug][payopt['key']]
                except:
                    pass
            if obj:
                return obj['url']
        return False

    def payment_gateway(self):
        url = self.payment_url()
        arr = url.split('/')
        if len(arr) > 2:
            return arr[2]
        return self.payment_option()['key']

    def payment_html(self):
        payopt = self.payment_option()
        obj = None
        if settings.PAYMENT_GATEWAYS and payopt:
            gates = settings.PAYMENT_GATEWAYS
            if self.project.fobi_slug and gates[self.project.fobi_slug]:
                try:
                    obj = gates[self.project.fobi_slug][payopt['key']]
                except:
                    pass
            if obj and obj['html']:
                return obj['html']
        return False

    def payment_amount(self):
        amount = 0
        if self.project.joining_style == "moderated" and self.fobi_data:
            rts = list(set([arr.resource.resource_type for arr in self.project.agent.resource_relationships()]))
            for rt in rts:
                if rt.ocp_artwork_type:
                    for key in self.fobi_items_keys():
                        if key == rt.ocp_artwork_type.clas: # fieldname is the artwork type clas, project has shares of this type
                            self.entries = SavedFormDataEntry.objects.filter(pk=self.fobi_data.pk).select_related('form_entry')
                            entry = self.entries[0]
                            self.data = json.loads(entry.saved_data)
                            val = self.data.get(key)
                            for elem in self.fobi_data.form_entry.formelemententry_set.all():
                                data = json.loads(elem.plugin_data)
                                choi = data.get('choices')
                                if choi:
                                    opts = choi.split('\r\n')
                                    for op in opts:
                                      opa = op.split(',')
                                      #import pdb; pdb.set_trace()
                                      if type(val) is str and opa[1].encode('utf-8').strip() == val.encode('utf-8').strip():
                                        amount = int(opa[0])
                                        break
                                elif type(val) is int and val:
                                    amount = val
                                    break
        return amount

    def payment_account_type(self):
        account_type = None
        if self.project.joining_style == "moderated" and self.fobi_data:
            rts = list(set([arr.resource.resource_type for arr in self.project.agent.resource_relationships()]))
            for rt in rts:
                if rt.ocp_artwork_type:
                    for key in self.fobi_items_keys():
                        if key == rt.ocp_artwork_type.clas: # fieldname is the artwork type clas, project has shares of this type
                            account_type = rt
        return account_type


    def payment_secret(self):
        payopt = self.payment_option()
        obj = None
        if settings.PAYMENT_GATEWAYS and payopt:
            gates = settings.PAYMENT_GATEWAYS
            if self.project.fobi_slug and gates[self.project.fobi_slug]:
                try:
                    obj = gates[self.project.fobi_slug][payopt['key']]
                except:
                    pass
            if obj and obj['secret']:
                return obj['secret']
        return False

    def payment_tokenorder(self):
        payopt = self.payment_option()
        obj = None
        if settings.PAYMENT_GATEWAYS and payopt:
            gates = settings.PAYMENT_GATEWAYS
            if self.project.fobi_slug and gates[self.project.fobi_slug]:
                try:
                    obj = gates[self.project.fobi_slug][payopt['key']]
                except:
                    pass
            if obj and obj['tokenorder']:
                return obj['tokenorder']
        return False

    def payment_algorithm(self):
        payopt = self.payment_option()
        obj = None
        if settings.PAYMENT_GATEWAYS and payopt:
            gates = settings.PAYMENT_GATEWAYS
            if self.project.fobi_slug and gates[self.project.fobi_slug]:
                try:
                    obj = gates[self.project.fobi_slug][payopt['key']]
                except:
                    pass
            if obj and obj['algorithm']:
                return obj['algorithm']
        return False

    def payment_token(self):
        secret = self.payment_secret()
        email = self.email_address
        amount = self.pending_shares()

        order = self.payment_tokenorder()
        algor = self.payment_algorithm()
        orderr = order.split('+')
        strin = ''
        token_obj = False
        if len(orderr) > 2:
            for fld in orderr:
                if fld == 'secret':
                    strin += secret
                elif fld == 'email':
                    strin += email
                elif fld == 'amount':
                    strin += str(amount)

            if algor == 'bcrypt':
                import bcrypt
                #from passlib.hash import bcrypt
                #if isinstance(strin, str):
                #    strin = bytes(strin, 'utf-8')
                self.salt = bcrypt.gensalt(prefix=b"2a")
                token_obj = bcrypt.hashpw(strin.encode('utf-8'), self.salt)#, 'utf8') #bcrypt.hash(strin)
            else:
                raise ValidationError("Token hashing algorithm not implemented or not understood: "+algor)
        else:
            raise ValidationError("Token fields order below 3: "+str(len(orderr))+"  "+('+'.join(orderr)))

        return token_obj #.hexdigest()

    def payment_fees(self):
        payopt = self.payment_option()
        amount = self.payment_amount()
        fees = 0
        obj = None
        if settings.PAYMENT_GATEWAYS and payopt:
            gates = settings.PAYMENT_GATEWAYS
            if self.project.fobi_slug and gates[self.project.fobi_slug]:
                try:
                    obj = gates[self.project.fobi_slug][payopt['key']]
                except:
                    pass
            if obj and obj['fees']:
                percent = float(obj['fees']['percent'])
                fixed = float(obj['fees']['fixed'])
                unit = obj['fees']['unit']
                payer = obj['fees']['payer']

                if percent:
                    fees += amount * percent / 100

                # TODO check unit type of payment

                if fixed:
                    fees += fixed

        return fees

    def payment_fees_payer(self):
        payopt = self.payment_option()
        obj = None
        if settings.PAYMENT_GATEWAYS and payopt:
            gates = settings.PAYMENT_GATEWAYS
            if self.project.fobi_slug and gates[self.project.fobi_slug]:
                try:
                    obj = gates[self.project.fobi_slug][payopt['key']]
                except:
                    pass
            if obj and obj['fees']:
                payer = obj['fees']['payer']
                if payer == 'user':
                    return self.agent
                elif payer == 'project':
                    return self.project.agent
        return None

    def payment_total_with_fees(self):
        return self.pending_shares() + self.payment_fees()

    def payment_unit(self):
        payopt = self.payment_option()
        unit = None
        obj = None
        if settings.PAYMENT_GATEWAYS and payopt:
            gates = settings.PAYMENT_GATEWAYS
            if self.project.fobi_slug and gates[self.project.fobi_slug]:
                try:
                    obj = gates[self.project.fobi_slug][payopt['key']]
                except:
                    pass
            if obj:
                try:
                    unit = Unit.objects.get(abbrev=obj['unit'].lower())
                except:
                    raise ValidationError("Can't find the payment Unit with abbrev = "+obj['unit'].lower())
        return unit

    def payment_unit_rt(self):
        unit = self.payment_unit()
        if not unit:
            return None
        elif not unit.gen_unit:
            raise ValidationError("The Unit has not any gen_unit: "+str(unit))
        unit_rts = EconomicResourceType.objects.filter(ocp_artwork_type__general_unit_type__id=unit.gen_unit.unit_type.id)
        if unit_rts:
            if len(unit_rts) > 1:
                try:
                    unit_rt = unit_rts.get(ocp_artwork_type__clas__contains='_digital')
                except:
                    raise ValidationError("None of the unit_rts is related an ocp_artwork_type with a clas that contains '_digital': "+str(unit_rts))
            else:
                unit_rt = unit_rts[0]
        else:
            raise ValidationError("The unit is not related any resource type: "+str(unit.gen_unit.unit_type))
        return unit_rt

    def exchange_type(self):
        et = None
        recs = []
        if self.exchange:
            return self.exchange.exchange_type

        rt = self.payment_account_type()
        if rt and rt.ocp_artwork_type:
            recordts = Ocp_Record_Type.objects.filter(ocpRecordType_ocp_artwork_type=rt.ocp_artwork_type, exchange_type__isnull=False)
            if len(recordts) > 1:
                payopt = self.payment_option()
                for rec in recordts:
                    ancs = rec.get_ancestors(True,True)
                    if payopt['key'] == 'faircoin':
                        for an in ancs:
                            if an.clas == 'fair_economy':
                                recs.append(rec)
                    elif payopt['key'] in ('transfer','ccard'):
                        for an in ancs:
                            if an.clas == 'fiat_economy':
                                recs.append(rec)
                    elif payopt['key'] == 'btc':
                        for an in ancs:
                            if an.clas == 'crypto_economy':
                                recs.append(rec)
                if len(recs) > 1:
                    for rec in recs:
                        ancs = rec.get_ancestors(True,True)
                        for an in ancs:
                            if 'buy' == an.clas:
                                et = rec.exchange_type
                elif recs:
                    et = recs[0].exchange_type

                if not et or not len(recs):
                    raise ValidationError("Can't find the exchange_type related the payment option: "+payopt['key']+" . The related account type ("+str(rt.ocp_artwork_type)+") has recordts: "+str(recordts))
            elif recordts:
                et = recordts[0].exchange_type

        return et


    def create_exchange(self, notes=None):
        ex = None
        et = self.exchange_type()
        pro = self.project.agent
        dt = self.request_date
        ag = self.agent

        if et and pro and dt:
            ex, created = Exchange.objects.get_or_create(
                exchange_type=et,
                context_agent=pro,
                start_date=dt,
                use_case=et.use_case,
            )
            if created:
                if ag:
                    ex.created_by = ag.user().user
                ex.created_date = dt
                #ex.name = str(ex)
            elif ag:
                ex.changed_by = ag.user().user

            if notes:
                ex.notes += notes

            ex.save()
            self.exchange = ex
            self.save()

            # create transfer types
            xt = ex.exchange_type
            tts = xt.transfer_types.all()
            if not tts:
                raise ValidationError("This exchange type has not transfer types: "+str(xt))
            elif len(tts) < 2:
                raise ValidationError("This exchange type has less than 2 transfer types: "+str(xt))

            #tt_share = tts.get(name__contains="Share")
            #tt_pay = tts.get(name__contains="Payment")

            xfers = ex.transfers.all()
            if len(xfers) < len(tts):
                for tt in tts:
                    try:
                        xfer = xfers.get(transfer_type=tt)
                    except:
                        xfer_name = tt.name
                        #if tt.is_reciprocal:
                        #    xfer_name = xfer_name + " from " + from_agent.nick
                        #else:
                        #    xfer_name = xfer_name + " of " + rt.name

                        xfer, created = Transfer.objects.get_or_create(
                            name=xfer_name,
                            transfer_type = tt,
                            exchange = ex,
                            context_agent = pro,
                            transfer_date = datetime.date.today(),
                        )
                        if created:
                            if ag:
                                xfer.created_by = ag.user().user
                        elif ag:
                            xfer.edited_by = ag.user().user
                        xfer.save()

        return ex


    def update_payment_status(self, status=None, gateref=None, notes=None):
        account_type = self.payment_account_type()
        balance = 0
        amount = self.payment_amount()
        unit = self.payment_unit()
        unit_rt = self.payment_unit_rt()
        if status:
            if self.agent:
                if not self.exchange:
                    ex = self.create_exchange(notes)
                    #raise ValidationError("The exchange has been created? "+str(ex))
                    #return HttpResponse('error')
                else:
                    ex = self.exchange


                et_give = EventType.objects.get(name="Give")
                et_receive = EventType.objects.get(name="Receive")

                xfers = ex.transfers.all()
                xfer_pay = None
                xfer_share = None
                try:
                    xfer_pay = xfers.get(transfer_type__is_currency=True)
                except:
                    raise ValidationError("Can't get a transfer type with is_currency in the exchange: "+str(ex)+" xfers:"+str(xfers))
                try:
                    xfer_share = xfers.get(transfer_type__inherit_types=True) #exchange_type__ocp_record_type__ocpRecordType_ocp_artwork_type__resource_type__isnull=False)
                except:
                    raise ValidationError("Can't get a transfer type related shares in the exchange: "+str(ex))

                if xfer_pay:
                    xfer_pay.notes += str(datetime.date.today())+' '+str(self.payment_gateway())+': '+status
                    xfer_pay.save()

                if amount and xfer_pay:
                    evts = xfer_pay.events.all()
                    coms = xfer_pay.commitments.all()
                    commit_pay = None
                    commit_pay2 = None
                    if len(coms):
                        # if has various commitments? TODO
                        commit_pay = coms[0]
                        if coms[1]:
                          commit_pay2 = coms[1]
                        if not commit_pay2:
                          commit_pay2 = commit_pay

                    if status == 'complete' or status == 'published':

                        if len(evts):
                            raise ValidationError("The payment transfer already has events! "+str(evts))
                        else:
                            evt, created = EconomicEvent.objects.get_or_create(
                                event_type = et_give,
                                #event_date = datetime.date.today(),
                                resource_type = unit_rt,
                                #resource=event_res,
                                transfer = xfer_pay,
                                exchange_stage = ex.exchange_type,
                                context_agent = self.project.agent,
                                quantity = amount,
                                unit_of_quantity = unit,
                                value = amount,
                                unit_of_value = unit,
                                from_agent = self.agent,
                                to_agent = self.project.agent,
                                is_contribution = xfer_pay.transfer_type.is_contribution,
                                is_to_distribute = xfer_pay.transfer_type.is_to_distribute,
                                event_reference = gateref,
                                created_by = self.agent.user().user,
                                commitment = commit_pay,
                            )
                            #evt.save()

                            evt2, created = EconomicEvent.objects.get_or_create(
                                event_type = et_receive,
                                event_date = datetime.date.today(),
                                resource_type = unit_rt,
                                #resource
                                transfer = xfer_pay,
                                exchange_stage = ex.exchange_type,
                                context_agent = self.project.agent,
                                quantity = amount,
                                unit_of_quantity = unit,
                                value = amount,
                                unit_of_value = unit,
                                from_agent = self.agent,
                                to_agent = self.project.agent,
                                is_contribution = xfer_pay.transfer_type.is_contribution,
                                is_to_distribute = xfer_pay.transfer_type.is_to_distribute,
                                event_reference = gateref,
                                created_by = self.agent.user().user,
                                commitment = commit_pay2,
                            )
                            #evt2.save()

                        # create commitments for shares
                        sh_com, created = Commitment.objects.get_or_create(
                            event_type = et_give,
                            commitment_date = datetime.date.today(),
                            due_date = datetime.date.today() + datetime.timedelta(days=1), # TODO custom process delaytime by project
                            resource_type = account_type,
                            exchange = ex,
                            transfer = xfer_share,
                            exchange_stage = ex.exchange_type,
                            context_agent = self.project.agent,
                            quantity = amount,
                            unit_of_quantity = account_type.unit,
                            value = amount,
                            unit_of_value = account_type.unit_of_price,
                            from_agent = self.project.agent,
                            to_agent = self.agent,
                            #description = description,
                            created_by = self.agent.user().user,
                        )

                        sh_com2, created = Commitment.objects.get_or_create(
                            event_type = et_receive,
                            commitment_date = datetime.date.today(),
                            due_date = datetime.date.today() + datetime.timedelta(days=1), # TODO custom process delaytime by project
                            resource_type = account_type,
                            exchange = ex,
                            transfer = xfer_share,
                            exchange_stage = ex.exchange_type,
                            context_agent = self.project.agent,
                            quantity = amount,
                            unit_of_quantity = account_type.unit,
                            value = amount,
                            unit_of_value = account_type.unit_of_price,
                            from_agent = self.project.agent,
                            to_agent = self.agent,
                            #description = description,
                            created_by = self.agent.user().user,
                        )
                        # create share events
                        """if not evts:
                            # transfer shares
                            user_rts = list(set([arr.resource.resource_type for arr in req.agent.resource_relationships()]))
                            for rt in user_rts:
                                if rt == account_type: # match the account type to update the value
                                    rss = list(set([arr.resource for arr in req.agent.resource_relationships()]))
                                    for rs in rss:
                                        if rs.resource_type == rt:
                                            rs.price_per_unit += amount # update the price_per_unit with payment amount
                                            rs.save()
                        sh_evt, created = EconomicEvent.objects.get_or_create(
                            event_type = et_give,
                            event_date = datetime.date.today(),
                            resource_type = account_type,
                            #resource=event_res,
                            transfer = xfer_share,
                            exchange_stage = ex.exchange_type,
                            context_agent = project.agent,
                            quantity = 1,
                            unit_of_quantity = account_type.unit,
                            value = amount,
                            unit_of_value = account_type.unit_of_price,
                            from_agent = project.agent,
                            to_agent = req.agent,
                            is_contribution = False, #xfer_pay.transfer_type.is_contribution,
                            is_to_distribute = False, #xfer_pay.transfer_type.is_to_distribute,
                            #event_reference = gateref,
                            created_by = req.agent.user().user,
                        )
                        sh_evt2, created = EconomicEvent.objects.get_or_create(
                            event_type = et_receive,
                            event_date = datetime.date.today(),
                            resource_type = account_type,
                            #resource=event_res,
                            transfer = xfer_share,
                            exchange_stage = ex.exchange_type,
                            context_agent = project.agent,
                            quantity = 1,
                            unit_of_quantity = account_type.unit,
                            value = amount,
                            unit_of_value = account_type.unit_of_price,
                            from_agent = project.agent,
                            to_agent = req.agent,
                            is_contribution = False, #xfer_pay.transfer_type.is_contribution,
                            is_to_distribute = False, #xfer_pay.transfer_type.is_to_distribute,
                            #event_reference = gateref,
                            created_by = req.agent.user().user,
                        )"""

                        return True

                    elif status == 'pending':
                        if not commit_pay:
                            commit_pay, created = Commitment.objects.get_or_create(
                                event_type = et_give,
                                commitment_date = datetime.date.today(),
                                due_date = datetime.date.today() + datetime.timedelta(days=2), # TODO custom process delaytime by project
                                resource_type = unit_rt,
                                exchange = ex,
                                transfer = xfer_pay,
                                exchange_stage = ex.exchange_type,
                                context_agent = self.project.agent,
                                quantity = amount,
                                unit_of_quantity = unit,
                                value = amount,
                                unit_of_value = unit,
                                from_agent = self.agent,
                                to_agent = self.project.agent,
                                #description = description,
                                created_by = self.agent.user().user,
                            )
                        if not commit_pay2:
                            commit_pay2, created = Commitment.objects.get_or_create(
                                event_type = et_receive,
                                commitment_date = datetime.date.today(),
                                due_date = datetime.date.today() + datetime.timedelta(days=2), # TODO custom process delaytime by project
                                resource_type = unit_rt,
                                exchange = ex,
                                transfer = xfer_pay,
                                exchange_stage = ex.exchange_type,
                                context_agent = self.project.agent,
                                quantity = amount,
                                unit_of_quantity = unit,
                                value = amount,
                                unit_of_value = unit,
                                from_agent = self.agent,
                                to_agent = self.project.agent,
                                #description = description,
                                created_by = self.agent.user().user,
                            )

                        if xfer_share:
                            evts = xfer_share.events.all()
                            coms = xfer_share.commitments.all()
                            commit_share = None
                            commit_share2 = None
                            if len(coms):
                                # if has various commitments? TODO
                                commit_share = coms[0]
                                if coms[1]:
                                  commit_share2 = coms[1]
                                if not commit_share2:
                                  commit_share2 = commit_share

                            # create commitments for shares
                            """if not commit_share:
                                commit_share, created = Commitment.objects.get_or_create(
                                    event_type = et_give,
                                    commitment_date = datetime.date.today(),
                                    due_date = datetime.date.today() + datetime.timedelta(days=1), # TODO custom process delaytime by project
                                    resource_type = account_type,
                                    exchange = ex,
                                    transfer = xfer_share,
                                    exchange_stage = ex.exchange_type,
                                    context_agent = self.project.agent,
                                    quantity = amount,
                                    unit_of_quantity = account_type.unit,
                                    value = amount,
                                    unit_of_value = account_type.unit_of_price,
                                    from_agent = self.project.agent,
                                    to_agent = self.agent,
                                    #description = description,
                                    created_by = self.agent.user().user,
                                )
                            if not commit_share2:
                                commit_share2, created = Commitment.objects.get_or_create(
                                    event_type = et_receive,
                                    commitment_date = datetime.date.today(),
                                    due_date = datetime.date.today() + datetime.timedelta(days=1), # TODO custom process delaytime by project
                                    resource_type = account_type,
                                    exchange = ex,
                                    transfer = xfer_share,
                                    exchange_stage = ex.exchange_type,
                                    context_agent = self.project.agent,
                                    quantity = amount,
                                    unit_of_quantity = account_type.unit,
                                    value = amount,
                                    unit_of_value = account_type.unit_of_price,
                                    from_agent = self.project.agent,
                                    to_agent = self.agent,
                                    #description = description,
                                    created_by = self.agent.user().user,
                                )"""

                        return True

                    else:
                        raise ValidationError("The status is not implemented: "+str(status))
                        #return False
                else:
                    raise ValidationError("There's not amount ("+str(amount)+") or xfer_pay? "+str(xfer_pay))
            else:
                raise ValidationError("The join request has no agent yet! ")
                #return False
        else:
            raise ValidationError("The update payment has no status! "+str(self))
            #return False

    def create_useragent_randompass(self, request=None, hash_func=hashlib.sha256):
        from work.forms import ProjectAgentCreateForm # if imported generally it breaks other imports, requires a deep imports rebuild TODO
        randpass = hash_func(str(random.SystemRandom().getrandbits(64))).hexdigest()[:settings.RANDOM_PASSWORD_LENGHT]

        at = None
        password = None
        if self.type_of_user == 'individual':
            at = get_object_or_404(AgentType, party_type='individual', is_context=False)
        elif self.type_of_user == 'collective':
            at = get_object_or_404(AgentType, party_type='team', is_context=True)
        else:
            raise ValidationError("The 'type_of_user' field is not understood for this request: "+str(self))

        reqdata = {'name':self.name,
                   'email':self.email_address,
                   'nick':self.requested_username,
                   'password':randpass,
                   'agent_type':at.id,
        }

        form = ProjectAgentCreateForm(data=reqdata) #prefix=jn_req.form_prefix())
        if form.is_valid():
            data = form.cleaned_data
            agent = form.save(commit=False)
            try:
                if request.user.agent.agent:
                    agent.created_by=request.user
            except:
                pass
            if not agent.is_individual():
                agent.is_context=True
            agent.save()
            self.agent = agent
            self.save()
            project = self.project
            # add relation candidate
            ass_type = get_object_or_404(AgentAssociationType, identifier="participant")
            ass = AgentAssociation.objects.filter(is_associate=self.agent, has_associate=self.project.agent)
            if ass_type and not ass:
                aa = AgentAssociation(
                    is_associate=agent,
                    has_associate=project.agent,
                    association_type=ass_type,
                    state="potential",
                    )
                aa.save()
            password = data["password"]
            if password:
                username = data["nick"]
                email = data["email"]
                if username:
                    user = User(
                        username=username,
                        email=email,
                        )
                    user.set_password(password)
                    user.save()
                    au = AgentUser(
                        agent = agent,
                        user = user)
                    au.save()

                    name = data["name"]

                    con_typ = ContentType.objects.get(model='joinrequest')

                    comm = Comment(
                        content_type=con_typ,
                        object_pk=self.pk,
                        user_name=self.project.agent.nick,
                        user_email=self.project.agent.email_address,
                        submit_date=datetime.date.today(),
                        comment=_("%(pass)s is the initial random password for user %(user)s, used to verify the email address %(mail)s") % {'pass': password, 'user': username, 'mail': email},
                        site=Site.objects.get_current()
                    )
                    comm.save()

                    if notification:
                        managers = project.agent.managers()
                        users = [agent.user().user,]
                        #for manager in managers:
                        #    if manager.user():
                        #        users.append(manager.user().user)
                        #users = User.objects.filter(is_staff=True)
                        if users:
                            site_name = get_site_name(request)
                            notification.send(
                                users,
                                "work_new_account",
                                {"name": name,
                                "username": username,
                                "password": password,
                                "site_name": site_name,
                                "context_agent": project.agent,
                                "request_host": request.get_host(),
                                }
                            )
                else:
                    raise ValidationError("There's a problem with the username: "+str(username))
            else:
                raise ValidationError("There's some problem with the random password: "+str(password))
        else:
            raise ValidationError("The form to autocreate user+agent from the join request is not valid. "+str(form.errors))
        return password

    def check_user_pass(self):
        con_typ = ContentType.objects.get(model='joinrequest')
        coms = Comment.objects.filter(content_type=con_typ, object_pk=self.pk)
        for c in coms:
            first = c.comment.split(' ')[0]
            if len(first) == settings.RANDOM_PASSWORD_LENGHT:
                if self.agent.user().user.check_password(first):
                    return _("WARNING!")
        return False

    def duplicated(self):
        if self.agent:
            reqs = JoinRequest.objects.filter(project=self.project, agent=self.agent)
            if len(reqs) > 1:
                for req in reqs:
                    if not req == self:
                        return req
            elif reqs:
                return False
            else:
                raise ValidationError("This join_request is wrong!")
        else:
            reqs = JoinRequest.objects.filter(project=self.project, requested_username=self.requested_username)
            if len(reqs) > 1:
                for req in reqs:
                    if not req == self:
                        return req
            elif reqs:
                return False
            else:
                raise ValidationError("This join_request is wrong!")


class NewFeature(models.Model):
    name = models.CharField(_('name'), max_length=24)
    deployment_date = models.DateField(_("deployment date"),)
    description = models.TextField(_('Description'),)
    permissions = models.TextField(_('permissions'), blank=True, null=True,)
    url = models.CharField(_('url'), max_length=255, blank=True,)
    screenshot = ThumbnailerImageField(_("screenshot"),
        upload_to='photos', blank=True, null=True,)

    class Meta:
        ordering = ('-deployment_date',)

    def __unicode__(self):
        return self.name


class InvoiceNumber(models.Model):
    invoice_number = models.CharField(_('invoice number'), max_length=128)
    invoice_date = models.DateField(_("invoice date"),)
    year = models.IntegerField(_("year"),)
    quarter = models.IntegerField(_("quarter"),)
    sequence = models.IntegerField(_("sequence"),)
    description = models.TextField(_('Description'), blank=True,null=True)
    member = models.ForeignKey(EconomicAgent, related_name="invoice_numbers",
        verbose_name=_('member'),)
    exchange = models.ForeignKey(Exchange,
        blank=True, null=True,
        verbose_name=_('exchange'), related_name='invoice_numbers')
    created_by = models.ForeignKey(User, verbose_name=_('created by'),
        related_name='invoice_numbers_created', editable=False)
    created_date = models.DateField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ('-invoice_date', "-sequence",)

    def __unicode__(self):
        return self.invoice_number

    def save(self, *args, **kwargs):
        if self.year:
            year = self.year
        else:
            year = self.invoice_date.year
            self.year = year
        if self.quarter:
            quarter = self.quarter
        else:
            month = self.invoice_date.month
            quarter = (month-1)//3 + 1
            self.quarter = quarter
        if self.sequence:
            sequence = self.sequence
        else:
            prevs = InvoiceNumber.objects.filter(
                year=year,
                quarter=quarter).order_by("-sequence")
            if prevs:
                sequence = prevs[0].sequence + 1
            else:
                sequence = 1
            self.sequence = sequence
        self.invoice_number = "/".join([
            unicode(year),
            unicode(quarter),
            unicode(sequence),
            unicode(self.member.id),
            ])
        super(InvoiceNumber, self).save(*args, **kwargs)


from general.models import Record_Type, Artwork_Type, Job, Unit_Type #, Material_Type, Nonmaterial_Type
from mptt.models import TreeManager


class Ocp_Artwork_TypeManager(TreeManager):

    def get_shares_type(self):
        shr_typs = Ocp_Artwork_Type.objects.filter(clas='shares')
        if shr_typs and len(shr_typs) > 1:
            raise ValidationError("There's more than one Ocp_Artwork_Type with the clas 'shares'!")
        elif shr_typs and shr_typs[0]:
            return shr_typs[0]
        else:
            raise ValidationError("The Ocp_Artwork_Type with clas 'shares' is not found!")

    def get_material_type(self):
        mat_typs = Ocp_Artwork_Type.objects.filter(clas='Material')
        if mat_typs and len(mat_typs) > 1:
            raise ValidationError("There's more than one Ocp_Artwork_Type with the clas 'Material'!")
        elif mat_typs and mat_typs[0]:
            return mat_typs[0]
        else:
            raise ValidationError("The Ocp_Artwork_Type with clas 'Material' is not found!")

    def get_nonmaterial_type(self):
        non_typs = Ocp_Artwork_Type.objects.filter(clas='Nonmaterial')
        if non_typs and len(non_typs) > 1:
            raise ValidationError("There's more than one Ocp_Artwork_Type with the clas 'Nonmaterial'!")
        elif non_typs and non_typs[0]:
            return non_typs[0]
        else:
            raise ValidationError("The Ocp_Artwork_Type with clas 'Nonmaterial' is not found!")

    def get_account_type(self):
        acc_typs = Ocp_Artwork_Type.objects.filter(clas='accounts')
        if acc_typs and len(acc_typs) > 1:
            raise ValidationError("There's more than one Ocp_Artwork_Type with the clas 'accounts'!")
        elif acc_typs and acc_typs[0]:
            return acc_typs[0]
        else:
            raise ValidationError("The Ocp_Artwork_Type with clas 'accounts' is not found!")

    def update_from_general(self): # TODO, if general.Artwork_Type (or Type) changes independently, update the subclass with new items
        return False

    """def update_to_general(self, table=None, ide=None): # update material and non-material general tables if not matching
        if table and ide:
            if table == 'Material_Type':
                try:
                    genm = Material_Type.objects.get(id=ide)
                except:
                    if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
                        with connection.cursor() as cursor:
                            cursor.execute("PRAGMA foreign_keys=OFF")
                            cursor.execute("INSERT INTO general_material_type (materialType_artwork_type_id) VALUES (%s)", [ide])
                            cursor.execute("PRAGMA foreign_keys=ON")
                            return Material_Type.objects.get(id=ide)
            elif table == 'Nonmaterial_Type':
                try:
                    genm = Nonmaterial_Type.objects.get(id=ide)
                except:
                    if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
                        with connection.cursor() as cursor:
                            cursor.execute("PRAGMA foreign_keys=OFF")
                            cursor.execute("INSERT INTO general_nonmaterial_type (nonmaterialType_artwork_type_id) VALUES (%s)", [ide])
                            cursor.execute("PRAGMA foreign_keys=ON")
                            return Nonmaterial_Type.objects.get(id=ide)
            else:
                raise ValidationError("Unknown table for update_to_general ! "+table)

        else: # update all
            pass
            ocp_mat = Ocp_Artwork_Type.objects.get(clas='Material')
            ocp_mats_c = ocp_mat.get_descendant_count() # self not included, like at general_material_type
            gen_mats_c = Material_Type.objects.count()
            if not ocp_mats_c == gen_mats_c:
                ocp_mats = ocp_mat.get_descendants()
                gen_mats = Material_Type.objects.all()
                for ocpm in ocp_mats:
                    try:
                        genm = Material_Type.objects.get(id=ocpm.id)
                    except:
                        if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
                            with connection.cursor() as cursor:
                                cursor.execute("PRAGMA foreign_keys=OFF")
                                cursor.execute("INSERT INTO general_material_type (materialType_artwork_type_id) VALUES (%s)", [ocpm.id])
                                cursor.execute("PRAGMA foreign_keys=ON")
    """


class Ocp_Artwork_Type(Artwork_Type):
    general_artwork_type = models.OneToOneField(
      Artwork_Type,
      on_delete=models.CASCADE,
      primary_key=True,
      parent_link=True
    )

    def get_Q_material_type():
        mat_typ = Ocp_Artwork_Type.objects.get_material_type()
        if mat_typ:
            return {'lft__gt':mat_typ.lft, 'rght__lt':mat_typ.rght, 'tree_id':mat_typ.tree_id}
        else:
            return {}

    rel_material_type = TreeForeignKey(
      'self',
      on_delete=models.SET_NULL,
      verbose_name=_('related material_type'),
      related_name='rel_types_material',
      blank=True, null=True,
      help_text=_("a related General Material Type"),
      limit_choices_to=get_Q_material_type
    )

    def get_Q_nonmaterial_type():
        non_typ = Ocp_Artwork_Type.objects.get_nonmaterial_type()
        if non_typ:
            return {'lft__gt':non_typ.lft, 'rght__lt':non_typ.rght, 'tree_id':non_typ.tree_id}
        else:
            return {}

    rel_nonmaterial_type = TreeForeignKey(
      'self',
      on_delete=models.SET_NULL,
      verbose_name=_('related nonmaterial_type'),
      related_name='rel_types_nonmaterial',
      blank=True, null=True,
      help_text=_("a related General Non-material Type"),
      limit_choices_to=get_Q_nonmaterial_type
    )
    facet = models.OneToOneField(
      Facet,
      on_delete=models.CASCADE,
      verbose_name=_('ocp facet'),
      related_name='ocp_artwork_type',
      blank=True, null=True,
      help_text=_("a related OCP Facet")
    )
    facet_value = models.ForeignKey(
      FacetValue,
      on_delete=models.CASCADE,
      verbose_name=_('ocp facet_value'),
      related_name='ocp_artwork_type',
      blank=True, null=True,
      help_text=_("a related OCP FacetValue")
    )
    resource_type = models.OneToOneField(
      EconomicResourceType,
      on_delete=models.CASCADE,
      verbose_name=_('ocp resource_type'),
      related_name='ocp_artwork_type',
      blank=True, null=True,
      help_text=_("a related OCP ResourceType")
    )
    context_agent = models.ForeignKey(EconomicAgent, # this field should be used only if there's no resource_type
      verbose_name=_('context agent'),               # and is needed to hide the category name by context
      on_delete=models.CASCADE,
      related_name='ocp_artwork_types',
      blank=True, null=True,
      help_text=_("a related OCP context EconomicAgent")
    )
    general_unit_type = TreeForeignKey(
        Unit_Type,
        on_delete=models.CASCADE,
        verbose_name=_('general unit_type'),
        related_name='ocp_artwork_types',
        blank=True, null=True,
        help_text=_("a related General Unit Type")
    )

    objects = Ocp_Artwork_TypeManager()

    class Meta:
      verbose_name= _(u'Type of General Artwork/Resource')
      verbose_name_plural= _(u'o-> Types of General Artworks/Resources')

    def __unicode__(self):
      try:
        if self.resource_type:
          return self.name+' <' #+'  ('+self.resource_type.name+')'
      except:
        return self.name+' !!'
      if self.facet_value:
          return self.name+':'#  ('+self.facet_value.value+')'
      elif self.facet:
          return self.name+'  ('+self.facet.name+')'
      else:
          return self.name


    def is_share(self):
        shr_typ = Ocp_Artwork_Type.objects.get_shares_type()
        shr_cur = Ocp_Unit_Type.objects.get_shares_currency()
        if shr_typ:
            # mptt: get_ancestors(ascending=False, include_self=False)
            ancs = self.get_ancestors(True, True)
            for an in ancs:
                if an.id == shr_typ.id:
                    return self
            if self.rel_nonmaterial_type:
                ancs = self.rel_nonmaterial_type.get_ancestors(True, True)
                for an in ancs:
                    if an.id == shr_typ.id:
                        return self.rel_nonmaterial_type #Ocp_Artwork_Type.objects.get(id=self.rel_nonmaterial_type.id)
            if self.general_unit_type and shr_cur:
                ancs = self.general_unit_type.get_ancestors(True, True)
                for an in ancs:
                    if an.id == shr_cur.id:
                        return self.general_unit_type #Ocp_Artwork_Type.objects.get(id=self.rel_nonmaterial_type.id)

        return False

    def is_account(self):
        acc_typ = Ocp_Artwork_Type.objects.get_account_type()
        if acc_typ:
            # mptt: get_ancestors(ascending=False, include_self=False)
            ancs = self.get_ancestors(True, True)
            for an in ancs:
                if an.id == acc_typ.id:
                    return self
        else:
            raise ValidationError("Can't get the ocp artwork type with clas 'accounts'")
        return False

    def is_currency(self):
        ancs = self.get_ancestors(True,True)
        cur = ancs.filter(clas__icontains='currency')
        if cur:
            return True
        return False




class Ocp_Skill_TypeManager(TreeManager):

    def update_from_general(self): # TODO, if general.Job changes independently, update the subclass with new items
        return False


class Ocp_Skill_Type(Job):
    general_job = models.OneToOneField(
      Job,
      on_delete=models.CASCADE,
      primary_key=True,
      parent_link=True
    )
    resource_type = models.OneToOneField(
      EconomicResourceType,
      on_delete=models.CASCADE,
      verbose_name=_('ocp resource_type'),
      related_name='ocp_skill_type',
      blank=True, null=True,
      help_text=_("a related OCP ResourceType")
    )
    facet = models.OneToOneField( # only root nodes can have unique facets
      Facet,
      on_delete=models.CASCADE,
      verbose_name=_('ocp facet'),
      related_name='ocp_skill_type',
      blank=True, null=True,
      help_text=_("a related OCP Facet")
    )
    facet_value = models.OneToOneField( # only some tree folders can have unique facet_values
      FacetValue,
      on_delete=models.CASCADE,
      verbose_name=_('ocp facet_value'),
      related_name='ocp_skill_type',
      blank=True, null=True,
      help_text=_("a related OCP FacetValue")
    )
    ocp_artwork_type = TreeForeignKey(
      Ocp_Artwork_Type,
      on_delete=models.SET_NULL,
      verbose_name=_('general artwork_type'),
      related_name='ocp_skill_types',
      blank=True, null=True,
      help_text=_("a related General Artwork Type")
    )
    '''event_type = models.ForeignKey( # only for verbs that are ocp event types
      EventType,
      on_delete=models.SET_NULL,
      verbose_name=_('ocp event_type'),
      related_name='ocp_skill_type',
      blank=True, null=True,
      help_text=_("a related OCP EventType")
    )'''

    objects = Ocp_Skill_TypeManager()

    class Meta:
      verbose_name= _(u'Type of General Skill Resources')
      verbose_name_plural= _(u'o-> Types of General Skill Resources')

    def __unicode__(self):
      if self.resource_type:
        if self.ocp_artwork_type and not self.ocp_artwork_type.name.lower() in self.get_gerund().lower():
          return self.get_gerund()+' - '+self.ocp_artwork_type.name.lower()+' <'
        else:
          return self.get_gerund()+' <' #name #+'  ('+self.resource_type.name+')'
      elif self.facet_value:
        return self.get_gerund() #+'  ('+self.facet_value.value+')'
      else:
        return self.get_gerund()

    def get_gerund(self):
      if self.gerund:
        return self.gerund.title()
      elif self.verb:
        return self.verb
      else:
        return self.name

    def opposite(self):
        rel = self.rel_jobs1.filter(relation__clas='oppose')
        if rel:
            return rel[0].job2
        #import pdb; pdb.set_trace()
        return False


class Ocp_Record_TypeManager(TreeManager):

    def update_from_general(self): # TODO, if general.Record_Type changes independently, update the subclass with new items
        return False


class Ocp_Record_Type(Record_Type):
    general_record_type = models.OneToOneField(
        Record_Type,
        on_delete=models.CASCADE,
        primary_key=True,
        parent_link=True
    )
    exchange_type = models.OneToOneField(
        ExchangeType,
        on_delete=models.CASCADE,
        blank=True, null=True,
        verbose_name=_('ocp exchange type'),
        related_name='ocp_record_type'
    )
    ocpRecordType_ocp_artwork_type = TreeForeignKey(
        Ocp_Artwork_Type,
        on_delete=models.CASCADE,
        verbose_name=_('general artwork_type'),
        related_name='ocp_record_types',
        blank=True, null=True,
        help_text=_("a related General Artwork Type")
    )
    ocp_skill_type = TreeForeignKey(
        Ocp_Skill_Type,
        on_delete=models.CASCADE,
        verbose_name=_('general skill_type'),
        related_name='ocp_record_types',
        blank=True, null=True,
        help_text=_("a related General Skill Type")
    )
    '''event_type = models.ForeignKey( # only for verbs that are ocp event types
      EventType,
      on_delete=models.SET_NULL,
      verbose_name=_('ocp event_type'),
      related_name='ocp_skill_type',
      blank=True, null=True,
      help_text=_("a related OCP EventType")
    )'''

    objects = Ocp_Record_TypeManager()

    class Meta:
        verbose_name= _(u'Type of General Record')
        verbose_name_plural= _(u'o-> Types of General Records')

    def __unicode__(self):
      if self.exchange_type:
        return self.name+' <' #+'  ('+self.resource_type.name+')'
      else:
        return self.name

    def context_agent(self):
      if self.exchange_type:
        if self.exchange_type.context_agent:
          return self.exchange_type.context_agent
      return None

    def get_ocp_resource_types(self, transfer_type=None):
        answer = None
        if transfer_type:
          if transfer_type.inherit_types:
            answer = Ocp_Artwork_Type.objects.filter(lft__gte=self.ocpRecordType_ocp_artwork_type.lft, rght__lte=self.ocpRecordType_ocp_artwork_type.rght, tree_id=self.ocpRecordType_ocp_artwork_type.tree_id).order_by('tree_id','lft')
          else:
            facetvalues = [ttfv.facet_value.value for ttfv in transfer_type.facet_values.all()]
            Mtyp = False
            Ntyp = False
            try:
                Mtyp = Artwork_Type.objects.get(clas="Material")
                Ntyp = Artwork_Type.objects.get(clas="Nonmaterial")
            except:
                pass

            Rids = []
            Sids = []
            for fv in facetvalues:
                try:
                    gtyps = Ocp_Artwork_Type.objects.filter(facet_value__value=fv)
                    for gtyp in gtyps:
                      subids = [typ.id for typ in Ocp_Artwork_Type.objects.filter(lft__gt=gtyp.lft, rght__lt=gtyp.rght, tree_id=gtyp.tree_id)]
                      Rids += subids+[gtyp.id]
                except:
                    pass

                try:
                    gtyp = Ocp_Skill_Type.objects.get(facet_value__value=fv)
                    subids = [typ.id for typ in Ocp_Skill_Type.objects.filter(lft__gt=gtyp.lft, rght__lt=gtyp.rght, tree_id=gtyp.tree_id)]
                    Sids += subids+[gtyp.id]
                except:
                    pass

            for facet in transfer_type.facets():
                if facet.clas == "Material_Type" or facet.clas == "Nonmaterial_Type" or facet.clas == "Currency_Type":
                    if Rids:
                        Rtys = Ocp_Artwork_Type.objects.filter(id__in=Rids).order_by('tree_id','lft') #.order_by('tree_id','lft')
                        #if Nids: # and Ntyp:
                        #    Mtys = Artwork_Type.objects.filter(id__in=Nids+Mids) #+[Ntyp.id, Mtyp.id])
                        answer = Rtys
                    else:
                        answer = Ocp_Artwork_Type.objects.all()

                elif facet.clas == "Skill_Type":
                    if Sids:
                        Stys = Ocp_Skill_Type.objects.filter(id__in=Sids).order_by('tree_id','lft')
                        #if Mids: # and Mtyp:
                        #    Ntys = Artwork_Type.objects.filter(id__in=Mids+Nids) #+[Ntyp.id, Mtyp.id])
                        answer = Stys
                    else:
                        answer = Ocp_Skill_Type.objects.all()

                #elif facet.clas == "Currency_Type":
                #    pass
                else:
                    pass

        if not answer:
          return Ocp_Artwork_Type.objects.none()

        return answer

    def x_actions(self):
        try:
            x_act = Ocp_Skill_Type.objects.get(clas='exchange')
            x_acts = Ocp_Skill_Type.objects.filter(lft__gt=x_act.lft, rght__lt=x_act.rght, tree_id=x_act.tree_id)
            return x_acts
        except:
            return []





from general.models import Unit as Gene_Unit
from general.models import Type

class Ocp_Unit_TypeManager(TreeManager):

    def get_shares_currency(self):
        shr_typs = Ocp_Unit_Type.objects.filter(clas='shares_currency')
        if shr_typs and len(shr_typs) > 1:
            raise ValidationError("There's more than one Ocp_Unit_Type with the clas 'shares_currency'!")
        elif shr_typs and shr_typs[0]:
            return shr_typs[0]
        else:
            raise ValidationError("The Ocp_Unit_Type with 'shares_currency' clas is not found!")

    def update_from_general(self): # TODO, if general.Unit_Type changes independently, update the subclass with new items
        return False


class Ocp_Unit_Type(Unit_Type):
    '''general_unit_type = models.OneToOneField(
        Unit_Type,
        on_delete=models.CASCADE,
        primary_key=True,
        parent_link=True
    )
    ocp_unit =  models.OneToOneField(
        Unit,
        on_delete=models.CASCADE,
        verbose_name=_('ocp unit'),
        related_name='ocp_unit_type',
        blank=True, null=True,
        help_text=_("a related OCP Unit")
    )
    general_unit = models.OneToOneField(
        Gene_Unit,
        on_delete=models.CASCADE,
        verbose_name=_('general unit'),
        related_name='ocp_unit_type',
        blank=True, null=True,
        help_text=_("a related General Unit")
    )'''

    objects = Ocp_Unit_TypeManager()

    class Meta:
        proxy = True
        verbose_name= _(u'Type of General Unit')
        verbose_name_plural= _(u'o-> Types of General Units')

    def __unicode__(self):
        us = self.units()
        if self.children.count():
            if len(us) == 1:
                return self.name+': <' #+'  ('+self.resource_type.name+')'
            else:
                return self.name+': '
        else:
            if len(us) == 1:
                return self.name+' <' #+'  ('+self.resource_type.name+')'
            else:
                return self.name

    def units(self):
        us = []
        if self.unit_set:
            for u in self.unit_set.all():
                us.append(u)
        return us

    def ocp_unit(self):
        us = self.units()
        if us:
            if us[0].ocp_unit:
                return us[0].ocp_unit
            else:
                raise ValidationError("The first unit related this Ocp_Unit_Type has not 'ocp_unit' - us[0]: "+str(us[0]))
        return None



'''class Gen_Unit(Gene_Unit):
    """general_unit = models.OneToOneField(
        Gene_Unit,
        on_delete=models.CASCADE,
        primary_key=True,
        parent_link=True
    )"""
    ocp_unit =  models.OneToOneField(
        Unit,
        on_delete=models.CASCADE,
        verbose_name=_('ocp unit'),
        related_name='gen_unit',
        blank=True, null=True,
        help_text=_("a related OCP Unit")
    )

    class Meta:
        verbose_name= _(u'General-OCP Unit')
        verbose_name_plural= _(u'o-> General-OCP Units')

    def __unicode__(self):
        if self.ocp_unit:
            return self.name+'('+self.ocp_unit.name+')'
        else:
            return self.name
'''

from django.db.models.signals import post_migrate

def create_unit_types(**kwargs):
    # Each
    ocp_eachs = Unit.objects.filter(name='Each')
    if ocp_eachs:
        ocp_each = ocp_eachs[0]
    else:
        ocp_each, created = Unit.objects.get_or_create(
            name='Each',
            unit_type='quantity',
            abbrev='u.')
        if created:
            print "- created Unit: 'Each' (u.)"
    ocp_each.abbrev = 'u.'
    ocp_each.save()

    gen_unitt = Artwork_Type.objects.get(clas='Unit')
    each_typ, created = Ocp_Unit_Type.objects.get_or_create(
        name='Each',
        parent=gen_unitt
    )
    if created:
        print "- created Ocp_Unit_type: 'Each'"
    each_typ.clas = 'each'
    each_typ.save()

    each = Gene_Unit.objects.filter(ocp_unit=ocp_each)
    if not each:
        each = Gene_Unit.objects.filter(name='Each')
    if not each:
        each, created = Gene_Unit.objects.get_or_create(
            name='Unit',
            code='u',
            unit_type=each_typ
        )
        if created:
            print "- created General.Unit for Each: 'Unit'"
    else:
        each = each[0]
    each.ocp_unit = ocp_each
    each.save()

    # Percent
    ocp_percs = Unit.objects.filter(name='Percent')
    if ocp_percs:
        ocp_perc = ocp_percs[0]
    else:
        ocp_perc, created = Unit.objects.get_or_create(
            name='Percent',
            unit_type='percent',
            abbrev='Pct')
        if created:
            print "- created Unit: 'Percent'"
    ocp_perc.symbol = '%'
    ocp_perc.save()

    perc_typ, created = Ocp_Unit_Type.objects.get_or_create(
        name='Percent',
        parent=gen_unitt
    )
    if created:
        print "- created Ocp_Unit_type: 'Percent'"
    perc_typ.clas = 'percent'
    perc_typ.save()

    perc = Gene_Unit.objects.filter(ocp_unit=ocp_perc)
    if not perc:
        perc, created = Gene_Unit.objects.get_or_create(
            name='percent',
            code='%',
            unit_type=perc_typ,
            ocp_unit=ocp_perc
        )
        if created:
            print "- created General.Unit for Percent: 'percent'"

    # Hours
    ocp_hours = Unit.objects.filter(name='Hour')
    if ocp_hours:
        ocp_hour = ocp_hours[0]
        ocp_hour.name = 'Hours'
        ocp_hour.save()
    else:
        ocp_hours = Unit.objects.filter(name='Hours')
        if ocp_hours:
            ocp_hour = ocp_hours[0]
        else:
            ocp_hour, created = Unit.objects.get_or_create(
                name='Hours',
                unit_type='time',
                abbrev='Hr')
            if created:
                print "- created Unit: 'Hours'"

    gen_time_typ, created = Ocp_Unit_Type.objects.get_or_create(
        name='Time',
        parent=gen_unitt
    )
    if created:
        print "- created Ocp_Unit_Type: 'Time'"
    gen_time_typ.clas = 'time_currency'
    gen_time_typ.save()

    hour = Gene_Unit.objects.filter(name='Hour')
    if not hour:
        hour = Gene_Unit.objects.get_or_create(
            name='Hour',
            code='h',
            unit_type=gen_time_typ
        )
        if created:
            print "- created General.Unit for Hours: 'Hour'"
    else:
        hour = hour[0]
    hour.ocp_unit = ocp_hour
    hour.save()

    # Days
    ocp_days = Unit.objects.filter(name='Day')
    if ocp_days:
        ocp_day = ocp_days[0]
    else:
        ocp_days = Unit.objects.filter(name='Days')
        if ocp_days:
            ocp_day = ocp_days[0]
        else:
            ocp_day, created = Unit.objects.get_or_create(
                name='Day',
                unit_type='time',
                abbrev='day')
            if created:
                print "- created Unit: 'Day'"

    days = Gene_Unit.objects.filter(name='Day')
    if not days:
        day, created = Gene_Unit.objects.get_or_create(
            name='Day',
            code='dd',
            unit_type=gen_time_typ
        )
    else:
        day = days[0]
    day.ocp_unit = ocp_day
    day.save()


    # Kilos
    ocp_kilos = Unit.objects.filter(name='Kilos')
    if ocp_kilos:
        ocp_kilos = ocp_kilos[0]
    else:
        ocp_kilos = Unit.objects.filter(name='Kilo')
        if ocp_kilos:
            ocp_kilos = ocp_kilos[0]
        else:
            ocp_kilos, created = Unit.objects.get_or_create(
                name='Kilos',
                unit_type='weight',
                abbrev='Kg')
            if created:
                print "- created Unit: 'Kilos'"
    ocp_kilos.name = 'Kilos'
    ocp_kilos.abbrev = 'Kg'
    ocp_kilos.save()

    gen_weight_typ, created = Ocp_Unit_Type.objects.get_or_create(
        name='Weight',
        parent=gen_unitt
    )
    if created:
        print "- created Ocp_Unit_Type: 'Weight'"

    kilos = Gene_Unit.objects.filter(name='Kilogram')
    if not kilos:
        kilo, created = Gene_Unit.objects.get_or_create(
            name='Kilogram',
            code='Kg',
            unit_type=gen_weight_typ
        )
        if created:
            print "- created General.Unit for Kilos: 'Kilogram'"
    else:
        kilo = kilos[0]
    kilo.ocp_unit = ocp_kilos
    kilo.save()


    # FairCoin
    ocp_fair, created = Unit.objects.get_or_create(name='FairCoin')
    if created:
        print "- created a main ocp Unit: 'FairCoin'!"
    ocp_fair.abbrev = 'fair'
    ocp_fair.save()

    gen_curr_typ, created = Ocp_Unit_Type.objects.get_or_create(
        name='Currency',
        parent=gen_unitt
    )
    if created:
        print "- created Ocp_Unit_Type: 'Currency'"
    gen_curr_typ.clas = 'currency'
    gen_curr_typ.save()

    gen_crypto_typ, created = Ocp_Unit_Type.objects.get_or_create(
        name='Crypto Currency',
        parent=gen_curr_typ
    )
    if created:
        print "- created Ocp_Unit_Type: 'Crypto Currency'"

    gen_fair_typ, created = Ocp_Unit_Type.objects.get_or_create(
        name='Faircoins',
        parent=gen_crypto_typ
    )
    if created:
        print "- created Ocp_Unit_Type: 'Faircoins'"
    gen_fair_typ.clas = 'faircoin'
    gen_fair_typ.save()

    fairs = Gene_Unit.objects.filter(name='FairCoin')
    if not fairs:
        fair, created = Gene_Unit.objects.get_or_create(
            name='FairCoin',
            code='ƒ'
        )
        if created:
            print "- created General.Unit for FairCoin: 'FairCoin'"
    else:
        fair = fairs[0]
    fair.code = 'ƒ'
    fair.unit_type = gen_fair_typ
    fair.ocp_unit = ocp_fair
    fair.save()

    ocp_fair_rts = EconomicResourceType.objects.filter(name='FairCoin')
    if not ocp_fair_rts:
        ocp_fair_rt, created = EconomicResourceType.objects.get_or_create(
            name='FairCoin')
        if created:
            print "- created ResourceType: 'FairCoin'"
    else:
        ocp_fair_rt = ocp_fair_rts[0]
    ocp_fair_rt.unit = ocp_fair
    ocp_fair_rt.unit_of_use = ocp_fair
    #ocp_fair_rt.unit_of_value = ocp_fair
    #ocp_fair_rt.value_per_unit = 1
    #ocp_fair_rt.value_per_unit_of_use = 1
    ocp_fair_rt.price_per_unit = 1
    ocp_fair_rt.unit_of_price = ocp_fair
    ocp_fair_rt.substitutable = True
    ocp_fair_rt.inventory_rule = 'yes'
    ocp_fair_rt.behavior = 'dig_curr'
    ocp_fair_rt.save()

    nonmat_typ = Ocp_Artwork_Type.objects.get(clas='Nonmaterial')
    digart_typ, created = Ocp_Artwork_Type.objects.get_or_create(
        name='Digital artwork',
        parent=nonmat_typ)
    if created:
        print "- created Ocp_Artwork_Type: 'Digital artwork'"
    digcur_typs = Ocp_Artwork_Type.objects.filter(name='digital Currencies')
    if not digcur_typs:
        digcur_typ, created = Ocp_Artwork_Type.objects.get_or_create(
            name='digital Currencies',
            parent=digart_typ)
        if created:
            print "- created Ocp_Artwork_Types: 'digital Currencies'"
    else:
        digcur_typ = digcur_typs[0]
    digcur_typ.clas = 'currency'
    digcur_typ.save()

    fair_rts = Ocp_Artwork_Type.objects.filter(name='FairCoin')
    if not fair_rts:
        fair_rt, created = Ocp_Artwork_Type.objects.get_or_create(
            name='FairCoin',
            parent=digcur_typ)
        if created:
            print "- created Ocp_Artwork_Types: 'FairCoin'"
    else:
        fair_rt = fair_rts[0]
    fair_rt.clas = 'fair_digital'
    fair_rt.resource_type = ocp_fair_rt
    fair_rt.general_unit_type = gen_fair_typ
    fair_rt.save()


    # Euros
    ocp_euro, created = Unit.objects.get_or_create(
        name='Euro',
        unit_type='value',
        abbrev='eur'
    )
    if created:
        print "- created Unit: 'Euro'"
    ocp_euro.symbol = '€'
    ocp_euro.save()
    gen_fiat_typ, created = Ocp_Unit_Type.objects.get_or_create(
        name='Fiat Currency',
        parent=gen_curr_typ
    )
    if created:
        print "- created Ocp_Unit_Type: 'Fiat Currency'"

    gen_euro_typ, created = Ocp_Unit_Type.objects.get_or_create(
        name='Euros',
        parent=gen_fiat_typ
    )
    if created:
        print "- created Ocp_Unit_Type: 'Euros'"
    gen_euro_typ.clas = 'euro'
    gen_euro_typ.save()

    euros = Gene_Unit.objects.filter(name='Euro')
    if not euros:
        euro, created = Gene_Unit.objects.get_or_create(
            name='Euro',
            code='€'
        )
        if created:
            print "- created General.Unit for Euros: 'Euro'"
    else:
        euro = euros[0]
    euro.code = '€'
    euro.unit_type = gen_euro_typ
    euro.ocp_unit = ocp_euro
    euro.save()

    ocp_euro_rts = EconomicResourceType.objects.filter(name__icontains='Euro')
    if len(ocp_euro_rts) == 1:
        if ocp_euro_rts[0].name == 'Euro':
            digi_rt = ocp_euro_rts[0]
            digi_rt.name = 'Euro digital'
            digi_rt.save()
        else:
            raise ValidationError("There is only one rt related Euro but is not 'Euro': "+str(ocp_euro_rts[0]))
    elif len(ocp_euro_rts) > 1:
        digi_rt = ocp_euro_rts.get(name='Euro digital')
        if not digi_rt:
            raise ValidationError("Can't find a ResourceType named 'Euro digital' rts: "+str(ocp_euro_rts))
        digi_rt.unit = ocp_euro
        digi_rt.unit_of_use = ocp_euro
        #digi_rt.unit_of_value = ocp_euro
        #digi_rt.value_per_unit = 1
        #digi_rt.value_per_unit_of_use = 1
        digi_rt.price_per_unit = 1
        digi_rt.unit_of_price = ocp_euro
        digi_rt.substitutable = True
        digi_rt.inventory_rule = 'yes'
        digi_rt.behavior = 'dig_curr'
        digi_rt.save()
        cash_rt = ocp_euro_rts.get(name='Euro cash')
        if not cash_rt:
            raise ValidationError("Can't find a ResourceType named 'Euro cash' rts: "+str(ocp_euro_rts))
        cash_rt.unit = ocp_euro
        cash_rt.unit_of_use = ocp_euro
        #cash_rt.unit_of_value = ocp_euro
        #cash_rt.value_per_unit = 1
        #cash_rt.value_per_unit_of_use = 1
        cash_rt.price_per_unit = 1
        cash_rt.unit_of_price = ocp_euro
        cash_rt.substitutable = True
        cash_rt.inventory_rule = 'yes'
        cash_rt.behavior = 'other'
        cash_rt.save()
    else:
        digi_rt, created = EconomicResourceType.objects.get_or_create(
            name='Euro digital',
            unit=ocp_euro,
            unit_of_use=ocp_euro,
            price_per_unit = 1,
            unit_of_price=ocp_euro,
            substitutable=True,
            inventory_rule='yes',
            behavior='dig_curr')
        if created:
            print "- created EconomicResourceType: 'Euro digital'"
        cash_rt, created = EconomicResourceType.objects.get_or_create(
            name='Euro cash',
            unit=ocp_euro,
            unit_of_use=ocp_euro,
            price_per_unit=1,
            unit_of_price=ocp_euro,
            substitutable=True,
            inventory_rule='yes',
            behavior='other')
        if created:
            print "- created EconomicResourceType: 'Euro cash'"

        #raise ValidationError("There are not ResourceTypes containing 'Euro' in the name!: "+str(ocp_euro_rts))

    artw_euros = Ocp_Artwork_Type.objects.filter(name__icontains="Euro")
    if len(artw_euros) > 1:
        digi = artw_euros.get(name='Euro digital')
        if digi:
            digi.clas = 'euro_digital'
            digi.resource_type = digi_rt
            digi.general_unit_type = gen_euro_typ
            digi.save()
        else:
            raise ValidationError("Can't find an Ocp_Artwork_Type named 'Euro digital' artw: "+str(artw_euros))
        cash = artw_euros.get(name='Euro cash')
        if cash:
            cash.clas = 'euro_cash'
            cash.resource_type = cash_rt
            cash.general_unit_type = gen_euro_typ
            cash.save()
        else:
            raise ValidationError("Can't find an Ocp_Artwork_Type named 'Euro cash' artw: "+str(artw_euros))
    else:
        raise ValidationError("There are not 2 Ocp_Artwork_Types containing 'Euro' in the name (should find 'Euro digital' and 'Euro cash'")



    # Shares

    gen_share_typs = Ocp_Unit_Type.objects.filter(name='Shares')
    if not gen_share_typs:
        gen_share_typs = Ocp_Unit_Type.objects.filter(name='Shares currency')
    if not gen_share_typs:
        gen_share_typ, created = Ocp_Unit_Type.objects.get_or_create(
            name='Shares currency',
            parent=gen_curr_typ)
        if created:
            print "- created Ocp_Unit_Type: 'Shares currency'"
    else:
        gen_share_typ = gen_share_typs[0]
    gen_share_typ.name = 'Shares currency'
    gen_share_typ.parent = gen_curr_typ
    gen_share_typ.clas = 'shares_currency'
    gen_share_typ.save()


    artw_share = Ocp_Artwork_Type.objects.filter(name='Share')
    if not artw_share:
        artw_sh, created = Ocp_Artwork_Type.objects.get_or_create(name='Shares')
        if created:
            print "- created Ocp_Artwork_Type branch: 'Shares'"
    else:
        artw_sh = artw_share[0]
    artw_sh.name = 'Shares'
    artw_sh.clas = 'shares'
    artw_sh.parent = digcur_typ
    artw_sh.resource_type = None
    artw_sh.general_unit_type = gen_share_typ
    artw_sh.save()


    ## FreedomCoop

    ocp_shares = Unit.objects.filter(name='Share')
    if not ocp_shares:
        ocp_shares = Unit.objects.filter(name='FreedomCoop Share')
    if not ocp_shares:
        ocp_share, created = Unit.objects.get_or_create(
            name='FreedomCoop Share',
            unit_type='value',
            abbrev='FdC'
        )
        if created:
            print "- created OCP Unit: 'FreedomCoop Share'"
    else:
        ocp_share = ocp_shares[0]
    ocp_share.name = 'FreedomCoop Share'
    ocp_share.unit_type = 'value'
    ocp_share.abbrev = 'FdC'
    ocp_share.save()

    gen_fdc_typs = Ocp_Unit_Type.objects.filter(name='FreedomCoop Shares')
    if not gen_fdc_typs:
        gen_fdc_typ, created = Ocp_Unit_Type.objects.get_or_create(
            name='FreedomCoop Shares',
            parent=gen_share_typ)
        if created:
            print "- created Ocp_Unit_Type: 'FreedomCoop Shares'"
    else:
        gen_fdc_typ = gen_fdc_typs[0]
    gen_fdc_typ.clas = 'freedom-coop_shares'
    gen_fdc_typ.save()

    fdc_share, created = Gene_Unit.objects.get_or_create(
        name='FreedomCoop Share',
        code='FdC')
    if created:
        print "- created General.Unit: 'FreedomCoop Share'"
    fdc_share.code = 'FdC'
    fdc_share.unit_type = gen_fdc_typ
    fdc_share.ocp_unit = ocp_share
    fdc_share.save()

    ocp_share_rts = EconomicResourceType.objects.filter(name='Membership Share')
    if not ocp_share_rts:
        ocp_share_rts = EconomicResourceType.objects.filter(name='FreedomCoop Share')
    if len(ocp_share_rts) == 1:
        share_rt = ocp_share_rts[0]
        share_rt.name = 'FreedomCoop Share'
        share_rt.unit = ocp_each
        share_rt.inventory_rule = 'yes'
        share_rt.behavior = 'other'
        share_rt.save()

    artw_fdc, created = Ocp_Artwork_Type.objects.get_or_create(
        name='FreedomCoop Share'
    )
    if created:
        print "- created Ocp_Artwork_Type: 'FreedomCoop Share'"
    artw_fdc.parent = Type.objects.get(id=artw_sh.id)
    artw_fdc.resource_type = share_rt
    artw_fdc.general_unit_type = Unit_Type.objects.get(id=gen_fdc_typ.id)
    artw_fdc.save()


    ## BankOfTheCommons

    boc_ag = EconomicAgent.objects.filter(nick="BoC")
    if not boc_ag:
        boc_ag = EconomicAgent.objects.filter(nick="BotC")
    if not boc_ag:
        print "- WARNING: the BoC agent don't exist, not created any unit for shares"
        return
    else:
        boc_ag = boc_ag[0]

    ocpboc_shares = Unit.objects.filter(name='BankOfTheCommons Share')
    if not ocpboc_shares:
        ocpboc_share, created = Unit.objects.get_or_create(
            name='BankOfTheCommons Share',
            unit_type='value',
            abbrev='BotC'
        )
        if created:
            print "- created OCP Unit: 'BankOfTheCommons Share (BotC)'"
    else:
        ocpboc_share = ocpboc_shares[0]
    ocpboc_share.name = 'BankOfTheCommons Share'
    ocpboc_share.unit_type = 'value'
    ocpboc_share.abbrev = 'BotC'
    ocpboc_share.save()

    gen_boc_typs = Ocp_Unit_Type.objects.filter(name='BankOfTheCommons Shares')
    if not gen_boc_typs:
        gen_boc_typ, created = Ocp_Unit_Type.objects.get_or_create(
            name='BankOfTheCommons Shares',
            parent=gen_share_typ)
        if created:
            print "- created Ocp_Unit_Type: 'BankOfTheCommons Shares'"
    else:
        gen_boc_typ = gen_boc_typs[0]
    gen_boc_typ.clas = 'bank-of-the-commons_shares'
    gen_boc_typ.save()


    boc_share, created = Gene_Unit.objects.get_or_create(
        name='BankOfTheCommons Share',
        code='BotC')
    if created:
        print "- created General.Unit: 'BankOfTheCommons Share'"
    boc_share.code = 'BotC'
    boc_share.unit_type = gen_boc_typ
    boc_share.ocp_unit = ocpboc_share
    boc_share.save()

    share_rt, created = EconomicResourceType.objects.get_or_create(
        name='BankOfTheCommons Share',
        unit=ocp_each,
        inventory_rule='yes',
        behavior='other'
    )
    if created:
        print "- created EconomicResourceType: 'BankOfTheCommons Share'"

    share_rt.context_agent = boc_ag
    share_rt.save()

    artw_boc, created = Ocp_Artwork_Type.objects.get_or_create(
        name='BankOfTheCommons Share'
    )
    if created:
        print "- created Ocp_Artwork_Type: 'BankOfTheCommons Share'"
    artw_boc.parent = Type.objects.get(id=artw_sh.id)
    artw_boc.resource_type = share_rt
    artw_boc.general_unit_type = Unit_Type.objects.get(id=gen_boc_typ.id)
    artw_boc.save()


post_migrate.connect(create_unit_types)



def rebuild_trees(**kwargs):
    uts = Unit_Type.objects.rebuild()
    print "rebuilded Unit_Type"

#post_migrate.connect(rebuild_trees)



from general.models import Relation

def create_exchange_skills(**kwargs):
    doin, created = Ocp_Skill_Type.objects.get_or_create(
        name="Doing", verb="to do", gerund="doing"
    )
    if created:
        print "Created main skill type: Doing"
    x_act, created = Ocp_Skill_Type.objects.get_or_create(
        name="Exchanging", verb="to exchange", gerund="exchanging", clas='exchange',
        parent=doin
    )
    if created:
        print "Created skill type: Exchanging"
    give, created = Ocp_Skill_Type.objects.get_or_create(
        name="Give", verb="to give", gerund="giving", clas='give',
        parent=x_act
    )
    if created:
        print "Created skill type: Give"
    receive, created = Ocp_Skill_Type.objects.get_or_create(
        name="Receive", verb="to receive", gerund="receiving", clas='receive',
        parent=x_act
    )
    if created:
        print "Created skill type: Receive"
    sell, created = Ocp_Skill_Type.objects.get_or_create(
        name="Sell", verb="to sell", gerund="selling", clas='sell',
        parent=x_act
    )
    if created:
        print "Created skill type: Sell"
    buy, created = Ocp_Skill_Type.objects.get_or_create(
        name="Buy", verb="to buy", gerund="buying", clas='buy',
        parent=x_act
    )
    if created:
        print "Created skill type: Buy"



    jjob, created = Relation.objects.get_or_create(
        name=":Relation Job-Job",
        clas="rel_job_jobs"
    )
    if created:
        print "Created the main Job-Job relation branch"
    oppose, created = Relation.objects.get_or_create(
        name="opposes", verb="to oppose", clas='oppose',
        parent=jjob
    )
    if created:
        print "Created the opposing relation"


    rel, created = give.rel_jobs1.get_or_create(
        job1=give, job2=receive, relation=oppose)
    if created:
        print "Created the Relation give<>receive"
    rel, created = receive.rel_jobs1.get_or_create(
        job1=receive, job2=give, relation=oppose)
    if created:
        print "Created the Relation receive<>give"
    rel, created = sell.rel_jobs1.get_or_create(
        job1=sell, job2=buy, relation=oppose)
    if created:
        print "Created the Relation sell<>buy"
    rel, created = buy.rel_jobs1.get_or_create(
        job1=buy, job2=sell, relation=oppose)
    if created:
        print "Created the Relation buy<>sell"


post_migrate.connect(create_exchange_skills)



