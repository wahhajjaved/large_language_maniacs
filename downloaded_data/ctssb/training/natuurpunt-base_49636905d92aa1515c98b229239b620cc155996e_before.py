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
from openerp.tools.translate import _
from lxml import etree
from openerp.osv.orm import setup_modifiers
from natuurpunt_tools import uids_in_group
from functools import partial

CONTEXT_SEARCH = [
    'default_supplier',
    'default_customer',
    'addressbook',
    'search_default_all_members',
]

def neighborhood(iterator):
    prev = -1
    for current in iterator:
        yield (prev,current)
        prev = current

def fn(p,c):
    if p > -1:
       return c if c-1 != p else -1
    else:
       return c

class account_analytic_account(osv.osv):
    _inherit = 'account.analytic.account'

    def fields_view_get(self, cr, uid, view_id=None, view_type=None, context=None, toolbar=False, submenu=False):
        res = super(account_analytic_account, self).fields_view_get(cr, uid, view_id=view_id, view_type=view_type, context=context, toolbar=toolbar, submenu=submenu)
        context = context or {}

        if (view_type == 'form' or view_type == 'tree'):
            res['toolbar'] = False
        return res

account_analytic_account()

class ir_attachment(osv.osv):
    _inherit = 'ir.attachment'

    def _search(self, cr, user, args, offset=0, limit=None, order=None, context=None, count=False, access_rights_uid=None):
        context = dict(context or {}, active_test=False)
        return super(ir_attachment, self)._search(cr, user, args, offset=offset, limit=limit, order=order, context=context,
                                                count=count, access_rights_uid=access_rights_uid)

ir_attachment()

class res_partner(osv.osv):
    _inherit = 'res.partner'

    def adress_history_domain(self, cr, user, args):

        def args_filter(elem):
            if elem[0] == 'display_name' or elem[0] == 'last_name':
                return ['name',elem[1],elem[2]]
            if elem[0] == 'zip_id':
                try:
                   city = self.pool.get('res.country.city').browse(cr,user,elem[2])
                   return ['zip',elem[1],str(city.zip)]
                except:
                   return False
            if elem[0] not in ['name','street','zip','city']:
                return False
            else:
                return elem

        c = args.count('|')
        if not c:
            return { '&': filter(None,map(args_filter,args)), }
        if len(args)-c > c+1:
            return {
                '|': filter(None,map(args_filter,args[c:c*2+1])),
                '&': filter(None,map(args_filter,args[c*2+1:])),
            }
        else:
            return { '|': filter(None,map(args_filter,args[c:c*2+1])), }

    def _search(self, cr, user, args, offset=0, limit=None, order=None, context=None, count=False, access_rights_uid=None):
        res = super(res_partner, self)._search(cr, user, args, offset=offset, limit=limit, order=order, context=context,
                                                count=count, access_rights_uid=access_rights_uid)
        if context and any(key in context for key in CONTEXT_SEARCH):
            idx = [i for i,e in enumerate(args) if e == '|']
            index = [0] + filter(lambda x:x>-1,[fn(p,c) for p,c in neighborhood(idx)])
            args2 = []
            hist_args = []
            for p,c in neighborhood(list(set(index))):
                if p != -1:
                    args2.append(args[p:c])
            else:
                args2.append(args[c:])

            for d in map(partial(self.adress_history_domain,cr,user),args2):
                if '|' in d:
                    hist_args = hist_args + ['|' for x in range(len(d['|'])-1)] + d['|']
                if '&' in d:
                    hist_args = hist_args + d['&']

            if hist_args:
                history_ids = self.pool.get('res.partner.address.history').search(cr,user,hist_args,context=context)
                for partner in self.pool.get('res.partner.address.history').browse(cr,user,history_ids):
                    if partner.partner_id and partner.partner_id.id not in res:
                        res.append(partner.partner_id.id)
        return res

    def _edit_only(self,cr,uid,ids,fieldnames,args,context=None):
        res = dict.fromkeys(ids)
        for partner in self.browse(cr, uid, ids, context=context):
            protect_contact = uids_in_group(self, cr, uid, 'group_natuurpunt_protect_partner', context=context)
            res[partner.id] = True if uid in protect_contact else False
        return res

    _columns = {
        'edit_only':fields.function(
                         _edit_only,
                         method=True,
                         type='boolean',
                         string='edit_only',
                    ),
    }


    def fields_view_get(self, cr, uid, view_id=None, view_type=None, context=None, toolbar=False, submenu=False):
        res = super(res_partner, self).fields_view_get(cr, uid, view_id=view_id, view_type=view_type, context=context, toolbar=toolbar, submenu=submenu)
        context = context or {}
        # custom natuurpunt sidebar security
        gp_users = uids_in_group(self, cr, uid, 'group_natuurpunt_crm_user', context=context)
        # power user
        protect_contact = uids_in_group(self, cr, uid, 'group_natuurpunt_protect_partner', context=context)

        doc = etree.XML(res['arch'])

        if view_type == 'tree' and uid in protect_contact:
            view = self.pool.get('ir.ui.view').browse(cr,uid,view_id)
            if view.id and view.name != u'organisation.partner.tree':
                #disable create button
                [node.set('create', '0') for node in doc.xpath("/tree")]
                [node.set('delete', '0') for node in doc.xpath("/tree")]

        if view_type == 'form' and uid in protect_contact:
            #disable stamdata
            view = self.pool.get('ir.ui.view').browse(cr,uid,view_id)
            if view.id and view.name != u'organisation.partner.form' or not view.id:
                #disable create button
                [node.set('create', '0') for node in doc.xpath("/form")]
                [node.set('delete', '0') for node in doc.xpath("/form")]
                method_nodes = doc.xpath("//field[not(ancestor::notebook)]")
                for node in method_nodes:
                    node.set('readonly', '1')
                    field = node.get('name')
                    setup_modifiers(node, res['fields'][field])

            #disable contacts tab, assuming this is the first tab always!
            method_nodes = doc.xpath("(/form/sheet/notebook/page)[1]//field")
            for node in method_nodes:
                node.set('readonly', '1')
                field = node.get('name')
                setup_modifiers(node, res['fields'][field])

        res['arch'] = etree.tostring(doc)

        if (view_type == 'form' or view_type == 'tree') and uid not in gp_users:
            res['toolbar'] = False
        return res

res_partner()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
