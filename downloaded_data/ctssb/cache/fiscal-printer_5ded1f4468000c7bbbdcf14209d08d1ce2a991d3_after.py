# -*- coding: utf-8 -*-
##############################################################################
# For copyright and license notices, see __openerp__.py file in module root
# directory
##############################################################################

import re
from openerp import netsvc
from openerp import tools, models, fields, api, _
from openerp.osv import osv, fields
from openerp.tools.translate import _

from controllers.main import do_event
from datetime import datetime

from openerp.addons.fpoc.controllers.main import DenialService

import logging
_logger = logging.getLogger(__name__)
#TODO Quitar esto cuando funcione
_logger.setLevel('DEBUG')


class FiscalPrinterDisconnected(osv.TransientModel):
    """
    Disconnected but published printers.
    """
    _name = 'fpoc.disconnected'
    _description = 'Printers not connected to the server.'

    _columns = {
        'name': fields.char(string='Name'),
        'protocol': fields.char(string='Protocol'),
        'model': fields.char(string='Model'),
        'serialNumber': fields.char(string='Serial Number'),
        'session_id': fields.char(string='Session'),
        'user_id': fields.many2one('res.users', string='Responsable'),
    }

    def auto_connect(self, cr, uid, context=None):
        """ si hay una impresora desconectada la conecta, llamado desde cron
        """
        ids = self.search(cr, uid, [], context=context)
        # si hay alguna desconectada la conecto
        if ids:
            for fiscal_id in ids:
                self.create_fiscal_printer(cr, uid, [fiscal_id])
                # verifico que los diarios la tengan y si no se las pongo.
                # TODO si hay mas de una impresora esto no anda.
                fiscal_printer_obj = self.pool.get('fpoc.fiscal_printer')
                fiscal_printer_obj.auto_attach(cr, uid, ids)

    def _update_(self, cr, uid, force=True, context=None):
        cr.execute('SELECT COUNT(*) FROM %s' % self._table)
        count = cr.fetchone()[0]
        if not force and count > 0:
            return 
        if count > 0:
            cr.execute('DELETE FROM %s' % self._table)
        t_fp_obj = self.pool.get('fpoc.fiscal_printer')
        R = do_event('list_printers', control=True)
        w_wfp_ids = []
        i = 0
        for resp in R:
            if not resp: continue
            for p in resp['printers']:
                if t_fp_obj.search(cr, uid, [("name", "=", p['name'])]):
                    pass
                else:
                    values = {
                        'name': p['name'],
                        'protocol': p['protocol'],
                        'model': p.get('model', 'undefined'),
                        'serialNumber': p.get('serialNumber', 'undefined'),
                        'session_id': p['sid'],
                        'user_id': p['uid'],
                    }
                    pid = self.create(cr, uid, values)

    def search(self, cr, uid, args, offset=0, limit=None, order=None, context=None, count=False):
        self._update_(cr, uid, force=True)
        return super(FiscalPrinterDisconnected, self).search(cr, uid, args, offset=offset, limit=limit, order=order, context=context, count=count)

    def read(self, cr, uid, ids, fields=None, context=None, load='_classic_read'):
        self._update_(cr, uid, force=False)
        return super(FiscalPrinterDisconnected, self).read(cr, uid, ids, fields=fields, context=context, load=load)

    def create_fiscal_printer(self, cr, uid, ids, context=None):
        """
        Create fiscal printers from this temporal printers
        """
        fp_obj = self.pool.get('fpoc.fiscal_printer')
        for pri in self.browse(cr, uid, ids):
            values = {
                'name': pri.name,
                'protocol': pri.protocol,
                'model': pri.model,
                'serialNumber': pri.serialNumber,
                'session_id': pri.session_id
            }
            fp_obj.create(cr, uid, values)
        return {
            'name': _('Fiscal Printers'),
            'domain': [],
            'res_model': 'fpoc.fiscal_printer',
            'type': 'ir.actions.act_window',
            'view_id': False,
            'view_mode': 'tree,form',
            'view_type': 'form',
            'context': context,
        }


class FiscalPrinter(osv.osv):
    """
    The fiscal printer entity.
    """

    def _get_status(self, cr, uid, ids, field_name, arg, context=None):
        s = self.get_state(cr, uid, ids, context)

        r = {}
        for p_id in ids:
            if s[p_id]:
                if s[p_id].has_key('clock'):
                    dt = datetime.strptime(s[p_id]['clock'], "%Y-%m-%d %H:%M:%S")
                    clock_now = dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    clock_now = str(datetime.datetime.now())
                r[p_id] = {
                    #'clock': dt.strftime("%Y-%m-%d %H:%M:%S"),
                    'clock': clock_now,
                    'printerStatus': s[p_id].get('strPrinterStatus', 'Unknown'),
                    'fiscalStatus': s[p_id].get('strFiscalStatus', 'Unknown'),
                }
            else:
                r[p_id]= {
                    'clock': False,
                    'printerStatus': 'Offline',
                    'fiscalStatus': 'Offline',
                }
        return r

    _name = 'fpoc.fiscal_printer'
    _description = 'fiscal_printer'

    _columns = {
        'name': fields.char(string='Name', required=True),
        'protocol': fields.char(string='Protocol'),
        'model': fields.char(string='Model'),
        'serialNumber': fields.char(string='Serial Number (S/N)'),
        'lastUpdate': fields.datetime(string='Last Update'),
        'printerStatus': fields.function(_get_status, type="char", method=True, readonly="True", multi="state", string='Printer status'),
        'fiscalStatus':  fields.function(_get_status, type="char", method=True, readonly="True", multi="state", string='Fiscal status'),
        'clock':         fields.function(_get_status, type="datetime", method=True, readonly="True", multi="state", string='Clock'),
        'session_id': fields.char(string='session_id'),
    }

    _defaults = {
    }

    _constraints = [
    ]

    _sql_constraints = [('model_serialNumber_unique', 'unique("model", "serialNumber")', 'this printer with this model and serial number yet exists')]

    def auto_attach(self, cr, uid, ids, context=None):
        # TODO si hay mas de una impresora esto no anda y tiene harcodeado el diario (jobiols)
        journal_obj = self.pool.get('account.journal')
        journal_ids = journal_obj.search(cr, uid, ['|',
                                                    ('code', '=', 'RVE08'),
                                                    ('code', '=', 'VEN08')])
        ids = self.search(cr, uid, [])
        for fp_id in ids:
            for journ in journal_obj.browse(cr, uid, journal_ids):
                journ.fiscal_printer_id = fp_id

    def update_printers(self, cr, uid, ids, context=None):
        r = do_event('info', {})
        return True

    def short_test(self, cr, uid, ids, context=None):
        for fp in self.browse(cr, uid, ids):
            do_event('short_test', {'name': fp.name},
                     session_id=fp.session_id, printer_id=fp.name)
        return True

    def large_test(self, cr, uid, ids, context=None):
        for fp in self.browse(cr, uid, ids):
            do_event('large_test', {'name': fp.name},
                     session_id=fp.session_id, printer_id=fp.name)
        return True

    def advance_paper(self, cr, uid, ids, context=None):
        for fp in self.browse(cr, uid, ids):
            do_event('advance_paper', {'name': fp.name},
                     session_id=fp.session_id, printer_id=fp.name)
        return True
        
    def cut_paper(self, cr, uid, ids, context=None):
        for fp in self.browse(cr, uid, ids):
            do_event('cut_paper', {'name': fp.name},
                     session_id=fp.session_id, printer_id=fp.name)
        return True
        
    def open_fiscal_journal(self, cr, uid, ids, context=None):
        for fp in self.browse(cr, uid, ids):
            do_event('open_fiscal_journal', {'name': fp.name},
                     session_id=fp.session_id, printer_id=fp.name)
        return True

    def cancel_fiscal_ticket(self, cr, uid, ids, context=None):
        for fp in self.browse(cr, uid, ids):
            do_event('cancel_fiscal_ticket', {'name': fp.name},
                     session_id=fp.session_id, printer_id=fp.name)
        return True

    def close_fiscal_journal(self, cr, uid, ids, context=None):
        for fp in self.browse(cr, uid, ids):
            do_event('close_fiscal_journal', {'name': fp.name},
                     session_id=fp.session_id, printer_id=fp.name)
        return True

    def shift_change(self, cr, uid, ids, context=None):
        for fp in self.browse(cr, uid, ids):
            do_event('shift_change', {'name': fp.name},
                     session_id=fp.session_id, printer_id=fp.name)
        return True

    def get_state(self, cr, uid, ids, context=None):
        r = {}
        for fp in self.browse(cr, uid, ids):
            try:
                event_result = do_event('get_status', {'name': fp.name},
                                        session_id=fp.session_id, printer_id=fp.name)
            except DenialService as m:
                raise osv.except_osv(_('Connectivity Error'), m)
            r[fp.id] = event_result.pop() if event_result else False
        return r

    def get_counters(self, cr, uid, ids, context=None):
        r = {}
        for fp in self.browse(cr, uid, ids):
            event_result = do_event('get_counters', {'name': fp.name},
                                    session_id=fp.session_id, printer_id=fp.name)
            r[fp.id] = event_result.pop() if event_result else False
        return r

    def make_fiscal_ticket(self, cr, uid, ids, options={}, ticket={}, context=None):
        fparms = {}
        r = {}
        for fp in self.browse(cr, uid, ids):
            fparms['name'] = fp.name
            fparms['options'] = options
            fparms['ticket'] = ticket
            #event_result = do_event('make_fiscal_ticket', fparms,
            event_result = do_event('make_ticket_factura', fparms,
                                    session_id=fp.session_id, printer_id=fp.name)
            r[fp.id] = event_result.pop() if event_result else False
        return r

    def make_fiscal_refund_ticket(self, cr, uid, ids, options={}, ticket={}, context=None):
        fparms = {}
        r = {}
        for fp in self.browse(cr, uid, ids):
            fparms['name'] = fp.name
            fparms['options'] = options
            fparms['ticket'] = ticket
            # import pdb;pdb.set_trace()
            # event_result = do_event('make_fiscal_ticket', fparms,
            event_result = do_event('make_ticket_notacredito', fparms,
                                    session_id=fp.session_id, printer_id=fp.name)
            r[fp.id] = event_result.pop() if event_result else False
        return r

    def cancel_fiscal_ticket(self, cr, uid, ids, context=None):
        fparms = {} 
        r = {}
        for fp in self.browse(cr, uid, ids):
            fparms['name'] = fp.name
            event_result = do_event('cancel_fiscal_ticket', fparms,
                                    session_id=fp.session_id, printer_id=fp.name)
            r[fp.id] = event_result.pop() if event_result else False
        return r


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
