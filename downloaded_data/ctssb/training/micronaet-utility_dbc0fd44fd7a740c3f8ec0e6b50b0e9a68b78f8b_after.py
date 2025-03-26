# -*- coding: utf-8 -*-
###############################################################################
#
#    Copyright (C) 2001-2014 Micronaet SRL (<http://www.micronaet.it>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
import os
import sys
import logging
import openerp
import openerp.netsvc as netsvc
import openerp.addons.decimal_precision as dp
from openerp.osv import fields, osv, expression, orm
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from openerp import SUPERUSER_ID, api
from openerp import tools
from openerp.tools.translate import _
from openerp.tools.float_utils import float_round as round
from openerp.tools import (DEFAULT_SERVER_DATE_FORMAT, 
    DEFAULT_SERVER_DATETIME_FORMAT, 
    DATETIME_FORMATS_MAP, 
    float_compare)


_logger = logging.getLogger(__name__)

    
class IrActivityLog(orm.Model):
    """ Model name: IrCron
    """    
    _name = 'ir.activity.log'
    _description = 'Activity log'
    _order = 'name'

    _columns = {
        'name': fields.char('Name', size=80, required=True),
        'code': fields.char('Code', size=15, required=True),
        'days': fields.integer('Repeat every day'),
        'type': fields.selection([
            ('cron', 'Cron event'),
            ], 'Type'),
        'note': fields.text('Note'),
        }

    _defaults = {
        'type': lambda *x: 'cron',
        'days': lambda *x: 1,
        }    

class IrActivityLogEvent(orm.Model):
    """ Model name: Ir Log event
    """    
    _name = 'ir.activity.log.event'
    _description = 'Activity log event'
    _rec_name = 'activity_id'
    _order = 'log_start'
    
    def log_data(self, event, data, append=True, mode='info'):
        ''' Log event in ODOO log queue
            Add in data extra dict (record) the event if append is True
            mode: info, warning, error
        '''        
        _logger.info(event)
        if append:
            if mode not in data:
                data[mode] = ''
            data[mode] += '%s: %s\n' % (datetime.now(), event)
        return True

    def log_start_event(self, cr, uid, code, context=None):
        ''' Save Start time when for activity code passed
            
        '''
        _logger.info('Start log activity code: %s' % code)
        activity_pool = self.pool.get('ir.activity.log')        
        activity_ids = activity_pool.search(cr, uid, [
            ('code', '=', code),
            ], context=context)
        if activity_ids:
            activity_id = activity_ids[0]     
        else:
            activity_id = activity_pool.create(cr, uid, {
                'code': code,
                'name': code,                
                }, context=context)

        return self.create(cr, uid, {
            'activity_id': activity_id,
            'log_start': datetime.now().strftime(
                DEFAULT_SERVER_DATETIME_FORMAT),
            }, context=context) 

    def log_stop_event(self, cr, uid, event_id, data=None, context=None):
        ''' Save Start time when end
            event_id: ID to update
            data: insert extra data in record (ex. error, warning, info fields)
        '''
        if data is None:
            data = {}
        _logger.info('End log activity ID: %s' % event_id)
        
        current_proxy = self.browse(cr, uid, event_id, context=context)
        start_dt = datetime.strptime(
            current_proxy.start, DEFAULT_SERVER_DATETIME_FORMAT)
        end_dt = datetime.now()
        
        data['log_stop'] = end_dt.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        data['duration'] = (end_dt - start_dt).total_seconds() / 3660.0 # hours
            
        if data.get('error', False):
            data['esit'] = 'error'
        elif data.get('warning', False):
            data['esit'] = 'warning'
        else:
            data['esit'] = 'info'
            
        return self.write(cr, uid, event_id, data, context=context) 
    
    _columns = {
        'activity_id': fields.many2one('ir.activity.log', 'Activity'),
        'log_start': fields.datetime('Start'),
        'log_stop': fields.datetime('Stop'),
        'duration': fields.float('Duration', digits=(16, 4)),
        'error': fields.text('Error'),
        'warning': fields.text('Warning'),
        'info': fields.text('Info'),
        'esit': fields.selection([
            ('info', 'OK'),
            ('warning', 'Warning'),
            ('error', 'Error'),
            ], 'Esit')
        }
       
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
