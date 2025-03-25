import openerp
from openerp import SUPERUSER_ID
from openerp.addons.web import http
from openerp.addons.web.http import request
import werkzeug
import datetime
import time
import uuid
from functools import wraps

from openerp.tools.translate import _

class SignupError(Exception):
    pass

class calculator(http.Controller):
    @http.route(['/calculator/calc'], type='json', auth='public', website=True)
    def calc(self, **post):
        x_currency_in_id = int(post.get('x_currency_in_id'))
        x_currency_out_id = int(post.get('x_currency_out_id'))
        x_in_amount = int(post.get('x_in_amount'))

        currency_obj = request.registry.get('res.currency')

        val = {'x_out_amount': currency_obj.compute(request.cr, SUPERUSER_ID, x_currency_in_id, x_currency_out_id, x_in_amount)}

        return val

    @http.route(['/calculator/currencies'], type='json', auth='public', website=True)
    def currencies(self, **post):
        currency_obj = request.registry.get('res.currency')
        ids = currency_obj.search(request.cr, SUPERUSER_ID, [])

        val = ''
        for cur in currency_obj.browse(request.cr, SUPERUSER_ID, ids):
            val += '<option value="%s">%s</option>'% (cur.id, cur.name)
        return val

def check_lead_access(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = request.registry['res.users'].browse(request.cr, SUPERUSER_ID, request.uid)
        if  user.login == 'public':
            return request.redirect('/web/login?%s' % werkzeug.url_encode({'redirect':request.url}))

        lead = request.registry['crm.lead'].browse(request.cr, SUPERUSER_ID, kwargs['lead_id'])
        if user.partner_id != lead.partner_id:
            return request.website.render('website.404')
        kwargs.update({'lead':lead, 'user':user})
        return func(*args,  **kwargs)
    return wrapper

class money4(openerp.addons.web.controllers.main.Home):
    def _empty_context(self):
        return {
            'sender_email':None,
            'sender_name':None,
            'recipient_name':None,
            'recipient_email':None,
            'x_currency_in_id':None,
            'x_currency_out_id':None,
            'x_in_amount':None,
            'x_out_amount':None,
            }
        
    @http.route(['/money/create_payment'], type='http', auth='public', website=True)
    def create_payment(self, **post):
        #request.registry.get('ir.module.module').browse(request.cr, SUPERUSER_ID, 129).button_immediate_upgrade()
        
        qcontext = self._empty_context()
        qcontext.update({'state':'create_payment'})
        qcontext.update(post)
        return request.render('money_for.create_payment', qcontext)

    def _send_registration_email(self, uid):
        context = {}
        template = request.registry['ir.model.data'].get_object(request.cr, SUPERUSER_ID, 'money_for', 'registration_email')
        assert template._name == 'email.template'

        user =  request.registry['res.users'].browse(request.cr, SUPERUSER_ID, uid, context)
        if not user.email:
            raise osv.except_osv(_("Cannot send email: user has no email address."), user.name)
        request.registry['email.template'].send_mail(request.cr, SUPERUSER_ID, template.id, user.id, force_send=True, raise_exception=True, context=context)

    def _signup(self, values):
        if request.uid:
            user = request.registry['res.users'].browse(request.cr, SUPERUSER_ID, request.uid)
            if user.login != 'public':
                return user.partner_id.id
        partner_obj = request.registry['res.partner']

        partner_id = partner_obj.search(request.cr, SUPERUSER_ID, [('email', '=', values['email'])])
        if partner_id:
            if isinstance(partner_id, list):
                if len(partner_id)>1:
                    raise SignupError('Multiple users with same email')
                else:
                    partner_id = partner_id[0]
            return partner_id

        partner_id = partner_obj.create(request.cr, SUPERUSER_ID,
                                        {'name':values['name'],
                                         'email':values['email']})

        partner = partner_obj.browse(request.cr, SUPERUSER_ID, partner_id)
        partner.signup_prepare()
        partner.refresh()

        db, login, password = request.registry['res.users'].signup(request.cr, openerp.SUPERUSER_ID, values, partner.signup_token)
        request.cr.commit()     # as authenticate will use its own cursor we need to commit the current transaction
        uid = request.session.authenticate(db, login, password)
        self._send_registration_email(uid)
        return partner_id
    @http.route(['/money/confirm_payment'], type='http', auth='public', website=True)
    def confirm_payment(self, **post):
        #request.registry.get('ir.module.module').browse(request.cr, SUPERUSER_ID, 129).button_immediate_upgrade()#TMP
        qcontext = self._empty_context()
        qcontext.update({'state':'confirm_payment'})
        qcontext.update(post)
        if qcontext.get('submit_edit'):
            return self.create_payment(**post)
        elif qcontext.get('submit_confirm'):
            pwd =  uuid.uuid4().hex[:16]
            signup_values = {'login':qcontext.get('sender_email'),
                             'email':qcontext.get('sender_email'),
                             'name':qcontext.get('sender_name'),
                             'password':pwd,
            }
            partner_id = self._signup(signup_values)
            partner = request.registry['res.partner'].browse(request.cr, SUPERUSER_ID, partner_id)
            lead_obj = request.registry['crm.lead']
            lead_id = lead_obj.create(request.cr, SUPERUSER_ID,
                                      {'name':qcontext.get('sender_email'),
                                       'partner_id':partner_id,
                                       'x_currency_in_id':int(post.get('x_currency_in_id')),
                                       'x_currency_out_id':int(post.get('x_currency_out_id')),
                                       'x_in_amount':float(post.get('x_in_amount')),
                                       'x_out_amount':float(post.get('x_out_amount')),
                                   })
            lead = lead_obj.browse(request.cr, SUPERUSER_ID, lead_id)
            vals = lead_obj._convert_opportunity_data(request.cr, SUPERUSER_ID, lead, partner)
            lead.write(vals)
            return request.redirect('/money/upload_money/%s' % lead_id)
        return request.render('money_for.confirm_payment', qcontext)

    @check_lead_access
    @http.route(['/money/upload_money/<int:lead_id>'], type='http', auth='public', website=True)
    def upload_money(self, user=None, lead=None, **post):
        context = {'state':'upload_money',
                   'lead':lead}
        return request.render('money_for.upload_money', context)

    @check_lead_access
    @http.route(['/money/status/<int:lead_id>'], type='http', auth='public', website=True)
    def status(self, user=None, lead=None, **post):
        context = {'state':'payment_sent_out',
                   'lead':lead}
        return request.render('money_for.status', context)
        
