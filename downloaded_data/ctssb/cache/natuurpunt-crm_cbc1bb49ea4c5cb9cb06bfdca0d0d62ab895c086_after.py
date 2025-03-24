# -*- coding: utf-8 -*-
##############################################################################
#
#    Natuurpunt VZW
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from osv import osv, fields
from openerp import SUPERUSER_ID
import datetime
from mx import DateTime
import time
from openerp.tools.translate import _
import urllib2
import xml.etree.ElementTree as ET
import re
import logging
from natuurpunt_tools import compose, uids_in_group
from natuurpunt_tools import match_with_existing_partner
from natuurpunt_tools import send_internal_alerts
from functools import partial

_logger = logging.getLogger('natuurpunt_web_membership')

class OrganisatiePartnerEnum():
    AFDELING = 1
    RESERVAAT = 2
    KERN = 3
    WERKGROEP = 5
    REGIONALE = 7
    BEZOEKERSCENTRUM = 10

website_alert = """ Er is een probleem opgedoken bij de aanmaak van je lidmaatschap.
                    We nemen zo snel mogelijk contact op.
                    Heb je vragen? Stuur een e-mail bericht naar ledenservice@natuurpunt.be"""

def can_use_an_existing_invoice(obj,cr,uid,partner):
    """
    """
    mline, membership_state_field = obj._np_membership_state(cr, uid, partner)
    mline.membership_id.name == 'Gewoon lid'
    return True

def verify_partner_membership_state(obj,cr,uid,data):
    """
    does partner have a membership invoice that we can use
    set 'alert_website' so we can inform website API that we can't
    use this partner for memberships without manual interaction
    """
    partner, vals, log = data
    good_membership_states = ['none','old','canceled','waiting']
    if partner and not partner.membership_state in good_membership_states:
        if partner.membership_state in ['invoiced','paid']:
            log['alert'].append('Lidmaatschap aanvraag van betaald lid')
            log['alert_website'] = True
        if partner.membership_state in ['wait_member']:
            log['alert'].append('Lidmaatschap aanvraag van contact met wachtend lidmaatschap')
            log['wait_member'] = True
    return partner, vals, log

def verify_if_customer_or_supplier(obj,cr,uid,data):
    """
    when partner is known as customer or supplier
    set 'alert_website' so we can inform website API that we can't
    use this partner for memberships without manual interaction
    """
    # TODO
    partner, vals, log = data
    if partner and (partner.customer or partner.supplier):
        if log['renewal'] == False:
            log['alert'].append('Lidmaatschap aanvraag van contact met klant/lev. status')
            log['alert_website'] = not log['full_match'] if 'full_match' in log else True
        else:
            log['alert'].append('Website hernieuwing van contact met klant/lev. status')
    return partner, vals, log

class mail_group(osv.osv):
    _inherit = 'mail.group'

    def group_word_lid_alerts(self, cr, uid, context=None):
        vals = {'name':'website meldingen'}
        mail_group_id = self.search(cr, uid, [('name','=',vals['name'])])
        if mail_group_id:
            return mail_group_id
        else:
            # first automatic creation of discussion group
            # or when group is removed
            mail_alias = self.pool.get('mail.alias')
            if not vals.get('alias_id'):
                vals.pop('alias_name', None)  # prevent errors during copy()
                alias_id = mail_alias.create_unique_alias(cr, uid,
                              # Using '+' allows using subaddressing for those who don't
                              # have a catchall domain setup.
                              {'alias_name': "group+" + vals['name']},
                              model_name=self._name, context=context)
                vals['alias_id'] = alias_id

            # get parent menu
            menu_parent = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'membership', 'menu_membership')
            menu_parent = menu_parent and menu_parent[1] or False

            # Create menu id
            mobj = self.pool.get('ir.ui.menu')
            menu_id = mobj.create(cr, SUPERUSER_ID, {'name': vals['name'], 'parent_id': menu_parent}, context=context)
            vals['menu_id'] = menu_id

            # Create group and alias
            mail_group_id = super(mail_group, self).create(cr, uid, vals, context=context)
            mail_alias.write(cr, uid, [vals['alias_id']], {"alias_force_thread_id": mail_group_id}, context)
            group = self.browse(cr, uid, mail_group_id, context=context)

            # Create client action for this group and link the menu to it
            ref = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'mail', 'action_mail_group_feeds')
            if ref:
                search_ref = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'mail', 'view_message_search')
                params = {
                    'search_view_id': search_ref and search_ref[1] or False,
                    'domain': [
                        ('model', '=', 'mail.group'),
                        ('res_id', '=', mail_group_id),
                    ],
                    'context': {
                        'default_model': 'mail.group',
                        'default_res_id': mail_group_id,
                    },
                    'res_model': 'mail.message',
                    'thread_level': 1,
                    'header_description': self._generate_header_description(cr, uid, group, context=context),
                    'view_mailbox': True,
                    'compose_placeholder': 'Send a message to the group',
                }
                cobj = self.pool.get('ir.actions.client')
                newref = cobj.copy(cr, SUPERUSER_ID, ref[1], default={'params': str(params), 'name': vals['name']}, context=context)
                mobj.write(cr, SUPERUSER_ID, menu_id, {'action': 'ir.actions.client,' + str(newref), 'mail_group_id': mail_group_id}, context=context)

            crm_users = uids_in_group(self, cr, uid, 'group_natuurpunt_crm_manager', partner=True, context=context)
            self.message_subscribe(cr, uid, [mail_group_id], crm_users, context=context)
            return [mail_group_id]

class res_partner(osv.osv):
    _inherit = 'res.partner'

    def _web_membership_product(self,cr,uid,subscriptions,only_magazine=False,context=None):        
        # membership defaulf product
        mem_prod = 'Gewoon lid'
        if not only_magazine:
            sql_stat = "select id from product_product where membership_product"
            cr.execute(sql_stat)
            mem_prod_ids = map(lambda x: x[0], cr.fetchall())
            # website membership product = membership default + subscriptions
            web_prod_list = [mem_prod]
            web_prod_list.extend([s['name'] for s in subscriptions])
            res = self.subscriptions_to_membership_product(cr,uid,mem_prod_ids,web_prod_list,context=context)
        else:
            sql_stat = "select id from product_product where magazine_product"
            cr.execute(sql_stat)
            mag_prod_ids = map(lambda x: x[0], cr.fetchall())
            web_prod_list = []
            web_prod_list.extend([s['name'] for s in subscriptions])
            res = self.subscriptions_to_magazine_product(cr,uid,mag_prod_ids,web_prod_list,context=context)
        
        # default fall back is 'gewoon lid'
        # better a product to sell than nothing        
        if not res:
            res = self.subscriptions_to_membership_product(cr,uid,mem_prod_ids,[mem_prod],context=context)

        return res

    def subscriptions_to_magazine_product(self,cr,uid,ids,web_prod_list,context=None):
        product_obj = self.pool.get('product.product')
        mag_prod_list = []
        for product in product_obj.browse(cr, uid, ids, context=context):
            if product.included_product_ids:
                mag_prod_list.append((product.id, product.name_template, map(lambda p:p.id,product.included_product_ids)))
            else:
                mag_prod_list.append((product.id, product.name_template, [product.id]))
        #web_prod_list to ids
        w_ids = filter(lambda p_id: p_id,map(lambda p: p[0] if p[1] in web_prod_list else False ,mag_prod_list))
        res = filter(lambda p_id: p_id,map(lambda p: p[0] if sorted(p[2]) == sorted(w_ids) else False, mag_prod_list))
        return res[0] if res else False
    
    def subscriptions_to_membership_product(self,cr,uid,ids,web_prod_list,context=None):
        product_obj = self.pool.get('product.product')
        for product in product_obj.browse(cr, uid, ids, context=context):
            # membership product = membership default + included products
            mem_prod_list = web_prod_list[:1]
            if product.included_product_ids:
                 for included_product in product_obj.browse(cr, uid, product.included_product_ids, context=context):
                    prod_name = included_product.id.name_template
                    if mem_prod_list[0] != prod_name:
                        mem_prod_list.append(prod_name)
            # intersection match then return product_id
            if set(mem_prod_list) == set(web_prod_list):
               return product.id
        return None
    
    def membership_renewal_product_to_subscriptions(self,cr,uid,ids,context=None):    
        for partner in self.browse(cr, uid, ids, context=context):
            if partner.membership_renewal_product_id:
                mem_prod_list = []
                mem_prod = 'Gewoon lid'
                product_obj = self.pool.get('product.product')
                product = product_obj.browse(cr, uid, partner.membership_renewal_product_id.id, context=context)
                for included_product in product_obj.browse(cr, uid, product.included_product_ids, context=context):
                    prod_name = included_product.id.name_template
                    if mem_prod != prod_name:
                        mem_prod_list.append(prod_name)
                # convert list of subscriptions to list {'name':subscription}                                
                return map(lambda v: {'name':v},mem_prod_list)
        return None

    def address_origin_website(self,cr,uid,context=None):
        address_origin_obj = self.pool.get('res.partner.address.origin')
        ids = address_origin_obj.search(cr, uid, [('ref','=','website')],context=context)
        if ids:
            return ids[0]
        else:
            return False

    def _verify_membership_origin(self,cr,uid,ids,context=None):
        membership_origin_obj = self.pool.get('res.partner.membership.origin')
        if membership_origin_obj.search(cr, uid, [('id','in',ids)],context=context):
            return True
        else:
            return False

    def _verify_recruiting_organisation(self,cr,uid,ids,context=None):
        recruiting_organisation_obj = self.pool.get('res.partner')
        org_ids = [
            OrganisatiePartnerEnum.AFDELING,
            OrganisatiePartnerEnum.WERKGROEP,
            OrganisatiePartnerEnum.REGIONALE,
            OrganisatiePartnerEnum.BEZOEKERSCENTRUM,
        ]
        if recruiting_organisation_obj.search(cr, uid, [('id','in',ids),('organisation_type_id','in',org_ids)],context=context):
            return True
        else:
            return False

    def partner_state_website_double_address(self,cr,uid,context=None):
        partner_state_obj = self.pool.get('res.partner.state')
        ids = partner_state_obj.search(cr, uid, [('ref','=','1')],context=context)
        if ids:
            return ids[0]
        else:
            return False

    def _web_membership_partner(self,cr,uid,ids,vals,context=None):
        if ids:
            # address update via website resets status
            vals['address_state_id'] = False
            self.write(cr,uid,ids,vals,context=context)
        else:
            # address via website
            vals['address_origin_id'] = self.address_origin_website(cr,uid,context=context)
            ids.append(self.create(cr,uid,vals,context=context))
        return ids

    def _bban2bic(self,bank_account_number=None):
        """webservice BIC"""
        try:
            base_url = 'http://www.ibanbic.be/IBANBIC.asmx/BBANtoBIC?Value'
            url = '%s=%s' % (base_url, bank_account_number.replace(' ', ''))
            response = urllib2.urlopen(url).read()
            root = ET.fromstring(response)
            bic = root.text.replace(' ', '')
        except Exception:
            bic = 'DUMMY'
        _logger.info("BIC for bank account {}:{}".format(bank_account_number,bic))
        return bic

    def _get_bic_id(self,cr,uid,bic):
        sql_stat = "select id from res_bank where name = '{0}'".format(bic)
        cr.execute(sql_stat)
        ids = map(lambda x: x[0], cr.fetchall())
        return ids[0] if ids else None

    def get_membership_payment_method(self,cr,uid,ids,context=None):
        context = context or {}
        for id in ids:
            partner_data = self.browse(cr, uid, id, context=context)
            mline, membership_state = self._np_membership_state(cr, uid, partner_data, context=context)
            if not mline:
                return 'Niet-betalend'
            elif mline.account_invoice_id.sdd_mandate_id:
                return 'Domiciliëng' 
            else:
                return 'jaarlijks'

    def create_web_membership_mandate_invoice(self,cr,uid,ids,selected_product_id=None,datas=None,context=None):

        bank_acc = datas['bank_account_number']

        bic_id = self._get_bic_id(cr,uid,self._bban2bic(bank_acc))
        bic_id = bic_id if bic_id else self._get_bic_id(cr,uid,'DUMMY')

        scan_binary = datas['scan']

        mandate_obj = self.pool.get('partner.create.bank.mandate.invoice')
        vals = {'partner_id':ids[0],
                'bic_id':bic_id,
                'bank_account':bank_acc,
                'signature_date':time.strftime('%Y-%m-%d %H:%M:%S'),
                'membership_product_id':selected_product_id,
                'scan':scan_binary,}
        # create os_memory object 
        mandate_id = mandate_obj.create(cr,uid,vals)
        mandate = mandate_obj.browse(cr,uid,mandate_id)
        res = mandate.create_bank_mandate_invoice(context=context)
        # return invoice via context in variable web_invoice_id
        if 'context' in res:
            if 'web_invoice_id' in res['context']:
                return [res['context']['web_invoice_id']]
            else:
                return 0
        else:
            return 0

    def create_web_membership(self,cr,uid,ids,vals,datas,context=None):
        context = context or {}
        if ids == None:
            ids = []

        # membership_origin_id                    
        membership_origin_id = datas.get('membership_origin_id', 0)
        if self._verify_membership_origin(cr,uid,[membership_origin_id],context=context):
            vals['membership_origin_id'] = membership_origin_id

        # recruiting_organisation_id
        recruiting_organisation_id = datas.get('recruiting_organisation_id', 0)
        if not(self._verify_recruiting_organisation(cr,uid,[recruiting_organisation_id],context=context)):
            datas.pop('recruiting_organisation_id', None)

        # convert website membership + subscriptions to product
        only_magazine = datas.get('only_magazine', False)
        product_id = self._web_membership_product(cr,uid,datas['subscriptions'],only_magazine=only_magazine,context=context)

        # renewal product...? , update contact  
        if datas.get('membership_renewal', False):
            vals['membership_renewal_product_id'] = product_id

        # override default from website            
        vals['customer'] = False

        # membership partner update or create
        _logger.info(vals)
        if not ids:
            _logger.info("partner niet aangemeld")
            data = (vals, _logger, 'Lidmaatschap aanvraag naam match')
            ids,log = compose(
                    partial(match_with_existing_partner,self,cr,uid),
                    partial(verify_partner_membership_state,self,cr,uid),
                    partial(verify_if_customer_or_supplier,self,cr,uid),
                    partial(send_internal_alerts,self,cr,uid),
                    lambda (p,l):([p.id],l) if p else (ids,l)
            )(data)
            _logger.info("partner match ids:{}".format(ids))
        else:
            _logger.info("partner aangemeld ids:{}".format(ids))
            log = {
                'alert':[],
                'renewal':datas.get('membership_renewal', False)
            }
            ids,log = compose(
                    lambda ids:(self.browse(cr,uid,ids[0],context=context),vals,log),
                    partial(verify_if_customer_or_supplier,self,cr,uid),
                    partial(send_internal_alerts,self,cr,uid),
                    lambda (p,l):([p.id],l)
            )(ids)

        if 'alert_website' in log and log['alert_website']:
            _logger.info("website alert:{}".format(website_alert))
            return {'id':0,'alert_message':website_alert}
        else:
            ids = self._web_membership_partner(cr,uid,ids,vals,context=context)

        methods = {'OGONE':self.create_membership_invoice,
                   'SEPA':self.create_web_membership_mandate_invoice,
                   'OFFLINE':self.create_membership_invoice,}
        method = datas['method'].upper() if 'method' in datas else None
        if method in methods:
            inv_ids = methods[method](cr,uid,ids,selected_product_id=product_id,datas=datas,context=context)
        else:
            inv_ids = 0

        if inv_ids:
            invoice_obj = self.pool.get('account.invoice')
            for invoice in invoice_obj.browse(cr,uid,inv_ids,context=context):
                #ogone_log_obj = self.pool.get('ogone.log')
                #ogone_log_vals = {
                #    'invoice_id':invoice.id,
                #    'date_created':time.strftime('%Y-%m-%d %H:%M:%S'),
                #}
                #ogone_log_obj.create(cr, uid, ogone_log_vals, context=context)
                return {'id':invoice.partner_id.id,'invoice_id':invoice.id,'reference':invoice.reference}
        else:
            return {'id':ids[0]}

res_partner()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
