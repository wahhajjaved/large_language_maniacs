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

class res_partner(osv.osv):
    _inherit = 'res.partner'

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
            #disable create button
            [node.set('create', '0') for node in doc.xpath("/tree")]
            [node.set('delete', '0') for node in doc.xpath("/tree")]

        if view_type == 'form' and uid in protect_contact:
            #disable create button
            [node.set('create', '0') for node in doc.xpath("/form")]
            [node.set('delete', '0') for node in doc.xpath("/form")]

            #disable stamdata
            view = self.pool.get('ir.ui.view').browse(cr,uid,view_id)
            if view.id and view.name != u'organisation.partner.form':
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
