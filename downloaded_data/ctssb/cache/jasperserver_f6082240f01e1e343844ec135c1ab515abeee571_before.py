# -*- coding: utf-8 -*-
##############################################################################
#
#    jasper_server module for OpenERP, 
#    Copyright (C) 2009 SYLEAM Info Services (<http://www.syleam.fr/>) Christophe CHAUVET
#
#    This file is a part of jasper_server
#
#    jasper_server is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    jasper_server is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from osv import osv
from osv import fields
from lxml.etree import Element, tostring
from netsvc import Logger, LOG_DEBUG, LOG_INFO, LOG_ERROR
from tools import ustr

def log_error(message):
    Logger().notifyChannel('jasper_server', LOG_ERROR, message)

class jasper_server(osv.osv):
    """
    Class to store the Jasper Server configuration
    """
    _name = 'jasper.server'
    _description = 'Jasper server configuration'
    _rec_name = 'host'

    _columns = {
        'host': fields.char('Host', size=128, required=True, help='Enter hostname or IP address'),
        'port': fields.integer('Port'),
        'user': fields.char('Username', size=128, required=True, help='Enter the username for JasperServer user, by default is jasperadmin'),
        'pass': fields.char('Password', size=128, required=True, help='Enter the password for the user, by defaul is jasperadmin'),
        'repo': fields.char('Repository', size=256, required=True, help='Enter the address of the repository'),
        'wsdl': fields.char('WSDL', size=256, help='Enter the address of the WSDL description'),
        'sequence': fields.integer('Sequence'),
        'enable': fields.boolean('Enable', help='Check this, if the server is available',),
    }

    _defaults = {
        'host': lambda *a: 'localhost',
        'port': lambda *a: 8180,
        'user': lambda *a: 'jasperadmin',
        'pass': lambda *a: 'jasperadmin',
        'repo': lambda *a: '/jasperserver/services/repository',
        'wsdl': lambda *a: '/jasperserver/services/repository?wsdl',
        'sequence': lambda *a: 10,
    }

    ## ************************************************
    # These method can create an XML for Jasper Server
    # *************************************************
    # TODO: ban element per level
    ban = (
        'res.company','ir.model','ir.model.fields','res.groups','ir.model.data',
        'ir.model.grid','ir.model.access','ir.ui.menu','ir.actions.act_window',
        'ir.action.wizard','ir.attachment','ir.cron','ir.rule','ir.rule.group',
        'ir.actions.actions','ir.actions.report.custom','ir.actions.report.xml',
        'ir.actions.url','ir.ui.view','ir.sequence','res.partner.event',
    )

    @staticmethod
    def format_element(element):
        """
        convert element in lowercase and replace space per _
        """
        return ustr(element).lower().replace(' ','_')

    def generate_context(self, cr, uid, context=None):
        """
        generate xml with context header
        """
        f_list = (
            'context_tz','context_lang','name', 'signature','company_id',
        )

        # TODO: Use browse to add the address of the company
        user = self.pool.get('res.users')
        usr = user.read(cr, uid, [uid], context=context)[0]
        ctx = Element('context')

        for val in usr:
            if val in f_list:
                e = Element(val)
                if usr[val]:
                    if isinstance(usr[val], list):
                        e.set('id', str(usr[val][0]))
                        e.text = str(usr[val][1])
                    else:
                        e.text = str(usr[val])
                ctx.append(e)

        return ctx

    def generate_xml(self, cr, uid, relation, id, depth, old_relation='', old_field='', context=None):
        """
        Generate xml for an object recursively
        """
        if not context:
            context = {}
        irm = self.pool.get('ir.model')
        if isinstance(relation, int):
            irm_ids = [relation]
        else:
            irm_ids = irm.search(cr, uid, [('model','=',relation)])

        if not irm_ids:
            log_error('Model %s not found !' % relation)

        ##
        # We must ban many model
        #
        ban = (
            'res.company','ir.model','ir.model.fields','res.groups','ir.model.data',
            'ir.model.grid','ir.model.access','ir.ui.menu','ir.actions.act_window',
            'ir.action.wizard','ir.attachment','ir.cron','ir.rule','ir.rule.group',
            'ir.actions.actions','ir.actions.report.custom','ir.actions.report.xml',
            'ir.actions.url','ir.ui.view','ir.sequence',
        )

        ##
        # If generate_xml was called by a relation field, we must keep
        # the original filename
        ir_model = irm.read(cr, uid, irm_ids[0])
        if isinstance(relation, int):
            relation = ir_model['model']

        irm_name = self.format_element(ir_model['name'])
        if old_field:
            x = Element(self.format_element(old_field), relation=relation, id=str(id))
        else:
            x = Element(irm_name, id='%s' % id)

        if not id:
            return x

        if isinstance(id, int):
            id = [id]

        obj = self.pool.get(relation)
        mod_ids = obj.read(cr, uid, id, context=context)
        mod_fields = obj.fields_get(cr, uid)
        for mod in mod_ids:
            for f in mod_fields:
                field = f.lower()
                name = mod_fields[f]['string']
                type = mod_fields[f]['type']
                value = mod[f]
                e = Element(field, label='%s' % self.format_element(name))
                if type in ('char','integer','text','selection'):
                    if value:
                        e.text = unicode(value)
                elif type == 'float':
                    #e.set('precision', str(mod_fields[f]['digits'][0]))
                    #e.set('accuracy', str(mod_fields[f]['digits'][1]))
                    e.text = value and str(value) or 0.0
                elif type == 'date':
                    e.set('format','YYYY-mm-dd')
                    if value:
                        e.text = value
                elif type == 'datetime':
                    e.set('format','YYYY-mm-dd HH:MM:SS')
                    if value:
                        e.text = value
                elif type == 'boolean':
                    e.text = str(value)
                elif type == 'many2one':
                    if not isinstance(value, int):
                        value = value and value[0] or 0
                    #log_error('Current: %r Old: %r' % (mod_fields[f]['relation'], relation))
                    if depth > 0 and value and mod_fields[f]['relation'] != old_relation and mod_fields[f]['relation'] not in ban:
                        e = self.generate_xml(cr, uid, mod_fields[f]['relation'], value, depth - 1, relation, field)
                    else:
                        e.set('id', '%r' % value or 0)
                        if not isinstance(value, int):
                            e.text = str(mod[f][1])
                elif type in ('one2many','many2many'):
                    if depth > 0 and value and mod_fields[f]['relation'] not in ban:
                        for v in value:
                            e = self.generate_xml(cr, uid, mod_fields[f]['relation'], v, depth - 1, relation, field)
                            x.append(e)
                        continue
                    else:
                        e.set('id','%r' % value)
                elif type in ('binary','reference'):
                    e.text = 'Not supported'
                else:
                    log_error('OUPS un oubli %s: %s(%s)' % (field, name, type))
                x.append(e)
        return x

    def generator(self, cr, uid, model, id, depth, context=None):
        root = Element('data')
        root.append(self.generate_context(cr, uid, context=context))
        root.append(self.generate_xml(cr, uid, model, id, depth, context=context))
        return tostring(root, pretty_print=context.get('indent',False))

jasper_server()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
