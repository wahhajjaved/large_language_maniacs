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
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#    Adding code for generate email and send from template thanks to OpenCode
#    
###############################################################################
import os
import sys
import openerp.netsvc as netsvc
import logging
from openerp.osv import osv, fields
from datetime import datetime, timedelta
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT, DATETIME_FORMATS_MAP, float_compare
import openerp.addons.decimal_precision as dp
from openerp.tools.translate import _
import re


_logger = logging.getLogger(__name__)

class sql_payment_stage(osv.osv):
    ''' Payment stage for sending e-mail
    '''
    _name = 'sql.payment.stage'
    _description = 'Payment Stage'
    _order = 'sequence,days'

    def get_default(self, cr, uid, context=None):
        ''' Return first stage depend on days
        '''
        try:
            return self.search(cr, uid, [], context=context)[0]
        except:
            return False    

    def get_next(self, cr, uid, item_id, context=None):
        ''' Get next stage after item_id
        '''
        stage_ids = self.search(cr, uid, [], context=context)
        passed = False
        for stage in self.browse(cr, uid, stage_ids, context=context):
            if passed:
                return item.id
            if stage.id == item_id:
                passed = True                
        return False
        
    _columns = {
        'sequence': fields.integer('Seq.'),
        'name': fields.char('Stage', size=64, required=True, readonly=False),
        'days': fields.integer('Days', 
            help="Days after deadline for sending e-mail", required=True),
        'template_id': fields.many2one('email.template', 'Template', 
            required=True),
        'note': fields.char('Note'),
        'period': fields.selection([
            ('before', 'Before deadline'),
            ('after', 'After deadline'),
            #('mail', 'Sending mail'),
            ], 'Period', select=True),
        'recipient': fields.selection([
            ('all', 'All (agent and customer)'),
            ('agent', 'Agent'),
            ('customer', 'Customer'),            
            ], 'Recipients', select=True),
    }
    _defaults = {
        'sequence': lambda *a: 0,
        'period': lambda *a: 'after',
        'recipient': lambda *a: 'all',
    }

class sql_payment_duelist(osv.osv):
    ''' Master object for import payment due list
    '''
    _name = 'sql.payment.duelist'
    _inherit = 'mail.thread'
    
    _description = 'Payment duelist'
    #_order = 'deadline desc'
    _order = 'date desc'

    # --------
    # Utility:
    # --------
    def validate_mail(self, email):
        ''' Check if the email is in a valid format
        '''
        if re.match("^.+\\@(\\[?)[a-zA-Z0-9\\-\\.]+\\.([a-zA-Z]{2,3}|[0-9]{1,3})(\\]?)$", email) != None:
            return True
        else:
            False

    def write_thread_message(self, cr, uid, ids, subject='', body='', context=None):
        ''' Write generic message 
            # TODO unificare con quello dello stato
        '''
        # Default part of message:
        message = { 
            'subject': subject,
            'body': body,
            'type': 'comment', #'notification', 'email',
            'subtype': False,  #parent_id, #attachments,
            'content_subtype': 'html',
            'partner_ids': [],            
            'email_from': 'openerp@micronaet.it', #wizard.email_from,
            'context': context,
            }
        msg_id = self.message_post(cr, uid, ids, **message)
        return 
        
    def write_object_change_state(self, cr, uid, ids, state='state', context=None):
        ''' Write info in thread list (used in WF actions)
        '''
        current_proxy = self.browse(cr, uid, ids, context=context)[0]

        # Default part of message:
        message = { 
            'subject': _("Changing state:"),
            'body': _("State variation in <b>%s</b>") % current_proxy.__getattr__(state),
            'type': 'comment', #'notification', 'email',
            'subtype': False,  #parent_id, #attachments,
            'content_subtype': 'html',
            'partner_ids': [],            
            'email_from': 'openerp@micronaet.it', #wizard.email_from,
            'context': context,
            }

        self.message_subscribe_users(
            cr, uid, ids, user_ids=[uid], context=context)
                        
        msg_id = self.message_post(cr, uid, ids, **message)
        return    

    # -------------------------------------------------------------------------
    #                                 Scheduler
    # -------------------------------------------------------------------------
    def schedule_sql_fido_import(self, cr, uid, fido_file, context=None):
        ''' Update also FIDO information 
        '''
        _logger.info('Import also FIDO file')
        partner_pool = self.pool.get('res.partner')
        separator = ';'
        
        no_fido_ids = partner_pool.search(cr, uid, [
            ('duelist_fido', '=', 0),
            ], context=context)
        
        # FIDO File:
        f = open(os.path.expanduser(
            os.path.join(*fido_file)), 'r')

        for line in f:
            row = line.strip().split(separator)
            partner_code = row[0].strip()
            fido = row[1].strip()
            
            partner_id = partner_pool.get_partner_from_sql_code(
                cr, uid, partner_code, context=context)
            if not partner_id:
                _logger.error('Partner %s not found!' % partner_code)                
                continue
            if not fido and partner_id in no_fido_ids:
                _logger.warning('Partner %s yet 0 FIDO' % partner_code)                
                continue
                    
            partner_pool.write(cr, uid, [partner_id], {
                'duelist_fido': int(fido or '0'), 
                }, context=context)
        return True
    
    def schedule_sql_payment_duelist_import(self, cr, uid, csv_file, 
            from_code=False, to_code=False, fido_file=False, context=None):
        ''' Import schedule action, 3 operations
            1. Import all payment (deleting payed)
            2. Assign TODO next stage depend on deadline
            3. Sent mail that need to            
            
            If present FIDO file import also that information
        '''
        # -----------------
        # Utility function:
        # -----------------
        def format_string(value):
            ''' Format float value
            '''
            return value.strip()

        def format_float(value):
            ''' Format float value
            '''     
            try:
                value = format_string(value)
                return float(value.replace(",", "."))
            except:
                return 0.0 # in case of error # TODO log

        def format_date(value):
            ''' Format float value
            '''
            try:
                value = value.strip()
                if value and len(value) >= 8: # YYYYMMDD
                    return "%s-%s-%s" % (value[:4], value[4:6], value[6:8])
            except:
                return False

        # ---------------
        # Import duelist:
        # ---------------
        _logger.info(_("Start import payment duelist via CSV!"))
        
        # Check FIDO file if present:
        if fido_file:
            return self.schedule_sql_fido_import(
                cr, uid, fido_file, context=context)

        # Duelist file:
        f = open(os.path.expanduser(os.path.join(*csv_file)), "r")
        i = 0
        separator = ";"
        currencies = {}
        
        partner_pool = self.pool.get('res.partner')
        currency_pool = self.pool.get('res.currency')

        # Load currency:
        currency_ids = currency_pool.search(cr, uid, [
            ('sql_name', '!=', False)
            ], context=context)            
        currency_proxy = currency_pool.browse(
            cr, uid, currency_ids, context=context)
        for item in currency_proxy:
            currencies[item.sql_name] = item.id
 
        # Before importation list (for delete payed after importation)
        before_ids = self.search(cr, uid, [], context)

        for line in f:
            try:
                i += 1
                csv_line = line.strip().split(separator)

                customer_code = format_string(csv_line[0])
                # jump line if not in range
                if from_code:
                    if customer_code < from_code:
                        _logger.warning(_('%s. Jumped line from_code (%s)') % (
                            i, customer_code))
                        continue
                if to_code:
                    if customer_code >= to_code:
                        _logger.warning(_('%s. Jumped line to_code (%s)') % (
                            i, customer_code))
                        continue

                deadline = format_date(csv_line[1])      
                total = format_float(csv_line[2])
                payment_type = format_string(csv_line[3]).upper()
                ref = format_string(csv_line[4])
                date = format_date(csv_line[5])
                currency_ref = format_string(csv_line[6])
                currency_name = format_string(csv_line[7])

                currency_id = currencies.get(currency_name, False)                
                partner_id = partner_pool.get_partner_from_sql_code(
                        cr, uid, customer_code, context=context)
                
                if total <= 0.0:
                    _logger.info('Jump negative total')
                    continue
                    
                if not partner_id:
                    _logger.error(
                        'No partner found, ID: %s, create manually' % customer_code)
                    partner_id = partner_pool.create(cr, uid, {
                        'name': _("Customer %s") % customer_code,
                        'ref': customer_code,
                        'sql_customer_code': customer_code,
                        'sql_import': True,
                        }, context=context)
                        
                payment_type = payment_type if payment_type in (
                    'R', 'B', 'M', 'V') else False

                item_ids = self.search(cr, uid, [
                    ('name', '=', ref),
                    ('date', '=', date),
                    ('partner_id', '=', partner_id),
                    ], context=context)
                
                data = {
                    'name': ref,
                    'date': date,
                    'deadline': deadline,
                    'partner_id': partner_id, 
                    'total': total,
                    'currency_id': currency_id,
                    'payment_type': payment_type, 
                    }
                if item_ids:
                    if len(item_ids) > 1:
                        _logger.warning(
                            _("%s. Find more than one payment (take first)!") % i)
                    item_id = item_ids[0]
                    if item_id in before_ids:
                        before_ids.remove(item_id)
                    self.write(cr, uid, item_id, data, context=context)
                    _logger.info(_("%s. Write payment!") % i)
                    
                else:
                    self.create(cr, uid, data, context=context)
                    _logger.info(_("%s. Create payment!") % i)
                        
            except:
                _logger.error(_("Error update payment: %s") % (
                    sys.exc_info(), ))
                        
        # Delete all elements not present:                
        _logger.info(_("Delete payment payed"))        
        if before_ids:
            for item in before_ids:
                try:
                    self.unlink(cr, uid, [item], context=context)
                except:
                    _logger.warning(_("Error delete payment ID: %s [%s]") % (
                        item, sys.exc_info()))
                            
        # ------------------
        # Assign stage todo:
        # ------------------
        _logger.info(_("Start assign todo stage"))
        
        # Auto-confirm all payment for customer with opt in
        _logger.info(_("Confirm duelist mail for optin partner:"))
        duelist_ids = self.search(cr, uid, [('state', '=', 'draft')], context=context)
        duelist_proxy = self.browse(cr, uid, duelist_ids, context=context)
        wf_service = netsvc.LocalService("workflow")

        for item in duelist_proxy:
            if item.partner_id.duelist_optin: # Set confirmed for partner optin
                wf_service.trg_validate(
                    uid, 'sql.payment.duelist', item_id,
                    'trigger_duelist_draft_confirmed', cr)
            
        _logger.info(_("Generate todo stage for confirmed payment:"))

        # Read stage for analysis:
        stage_pool = self.pool.get('sql.payment.stage')
        stage_ids = stage_pool.search(cr, uid, [], context=context)
        stages = {}    
        for stage in stage_pool.browse(cr, uid, stage_ids, context=context):
            if stage.period == 'before':
                stages[-stage.days] = stage.id
            else: # 'deadline'    
                stages[stage.days] = stage.id
        
        # Search and setup stage todo     
        today = datetime.now()
        duelist_ids = self.search(cr, uid, [
            ('state', '=', 'confirmed')], context=context)
        stages_sorted = sorted(stages.iteritems(), reverse=True)
        
        for item in self.browse(cr, uid, duelist_ids, context=context):
            deadline = datetime.strptime(item.deadline, DEFAULT_SERVER_DATE_FORMAT)
            for days, stage in stages_sorted: # sort desc per days
                if today - timedelta(days=days)  >= deadline:
                    if stage != item.stage_id.id: # test if it's not current stage
                        self.write(cr, uid, item.id, {'todo_stage_id': stage}, 
                            context=context)
                    break # next duelist (this is setted)        

        # -------------------------
        # Send mail for todo stage:
        # -------------------------
        _logger.info(_("Start sending mail"))        
        
        duelist_ids = self.search(cr, uid, [('todo_stage_id', '!=', False)], 
            context=context)        

        # Pools for send message:
        message_pool = self.pool.get('mail.message')
        mail_pool = self.pool.get('mail.mail')
        template_pool = self.pool.get('email.template')
        compose_pool = self.pool.get('mail.compose.message')

        mail_ids = []
        for item in self.browse(cr, uid, duelist_ids, context=context):
            valid_email = True
            # Create template
            template = item.todo_stage_id.template_id
            
            # Translate template text:
            mail_subject = compose_pool.render_template(cr, uid, 
                _(template.subject), 'sql.payment.duelist', item.id,
                context=context,
                )
            mail_body = compose_pool.render_template(cr, uid,
                _(template.body_html), 'sql.payment.duelist', item.id,
                context=context,
                )
            mail_to = compose_pool.render_template(cr, uid, 
                _(template.email_to), 'sql.payment.duelist', item.id,
                context=context,
                )                
            reply_to = compose_pool.render_template(cr, uid, 
                _(template.reply_to), 'sql.payment.duelist', item.id,
                context=context,
                )
            mail_from = compose_pool.render_template(cr, uid, 
                _(template.email_from), 'sql.payment.duelist', item.id,
                context=context,
                )

            if not(mail_to and self.validate_mail(mail_to)): 
                # Send an e-mail to Company for correcting:
                valid_email = False                
                mail_subject = _("Fount invalid email for this payment partner")
                mail_to = item.partner_id.company_id.partner_id.email

            # Create relative message (required by mail)
            #  > Note: thread for link in payment message:
            message_id = message_pool.create(cr, uid, {
                'type': 'email',
                'subject': mail_subject,
                'body': _("[%s] Template for mail: %s ") % (
                    datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                    template.name,
                    ),
                'model': 'sql.payment.duelist',
                'res_id': item.id,
                }, context=context)
        
            # Create mail message
            mail_id = mail_pool.create(cr, uid, {
                'mail_message_id': message_id,
                'mail_server_id': template.mail_server_id and template.mail_server_id.id or False,
                'state': 'outgoing',
                'auto_delete': template.auto_delete, # False
                'email_from': mail_from,
                'email_to': mail_to,
                'reply_to': reply_to,
                'body_html': mail_body,
                })
            mail_ids.append(mail_id)
            
            # Set stage to last mail sent (TODO not yet sent!!!)
            if valid_email: # Remain in sending state:
                self.write(cr, uid, item.id, {
                    'stage_id': item.todo_stage_id.id,
                    'todo_stage_id': False
                    }, context=context)
            
        # Send all mail now:    
        _logger.info(_("Send mails [# %s]" % len(mail_ids)))
        mail_pool.send(cr, uid,  mail_ids, context=context)
        # TODO verify if mail are send (instead of stage is not correct)

        _logger.info(_("End import / send duelist procedure"))
        return True

    # -------------------------------------------------------------------------
    #                                Button action
    # -------------------------------------------------------------------------    
    # Utility for 2 button (workflow style):
    def trigger_duelist(self, cr, uid, ids, duelist_optin, context=None):
        ''' Raise a confirmed trigger but save the opt-in as True in partner
        '''
        try:
            wf_service = netsvc.LocalService("workflow")
            payment_proxy = self.browse(cr, uid, ids, context=context)[0]
            partner_id = payment_proxy.partner_id.id

            partner_pool = self.pool.get('res.partner')
            partner_pool.write(
                cr, uid, partner_id, {
                    'duelist_optin': duelist_optin,
                    }, context=context)
                    
            # Log operation:        
            partner_pool.message_post(cr, uid, partner_id, **{
                'subject': _('Duelist operation:'),
                'body': _('%s opt-in for duelist deadline [%s]') % (
                    _("<b>Enable</b>") if duelist_optin else _("<b>Disable</b>"),
                    datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                    ),
                'type': 'comment', 
                'subtype': False,
                'content_subtype': 'html',
                'partner_ids': [],            
                'email_from': 'openerp@micronaet.it',
                'context': context,
                })  
        except:
            raise osv.except_osv(
                _("Error setup partner opt-in, try in partner form!"))
            return False 
        if duelist_optin:
            # Trigger all payment for this partner:
            duelist_ids = self.search(cr, uid, [
                ('partner_id', '=', partner_id),
                ('state', '=', 'draft'),
                ], context=context)

            # Trigger all payment for this partner:            
            for item_id in duelist_ids:
                try:
                    wf_service.trg_validate(
                        uid, 'sql.payment.duelist', item_id,
                        'trigger_duelist_draft_confirmed', cr)
                except:
                    _logger.error("Error confirmed payment: %s" % item_id)        
        return True
                
    def trigger_duelist_draft_confirmed_always(self, cr, uid, ids, context=None):
        ''' Trigger always
        ''' 
        return self.trigger_duelist(cr, uid, ids, True, context=context)

    def trigger_duelist_draft_confirmed_never(self, cr, uid, ids, context=None):
        ''' Trigger never
        ''' 
        return self.trigger_duelist(cr, uid, ids, False, context=context)

    def resend_mail(self, cr, uid, ids, context=None):
        ''' Remove stage to payment so it will be resent
        '''
        self.write_thread_message(cr, uid, ids, 
            subject=_('Resend message:'), 
            body=_('Mail for stage will be resent'), 
            context=None,
            )
        
        return self.write(cr, uid, ids, {
            'stage_id': False, }, context=context)
        
    # -------------------------------------------------------------------------
    #                                  Workflow
    # -------------------------------------------------------------------------
    def duelist_draft(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {
            'draft_date': datetime.now().strftime(
                DEFAULT_SERVER_DATETIME_FORMAT),
            'confirmed_user_id': False,
            'confirmed_date': False,
            'done_user_id': False,
            'done_date': False,
            'cancel_user_id': False,
            'cancel_date': False,
            'state': 'draft',
            }, context=context)

    def duelist_confirmed(self, cr, uid, ids, context=None):
        self.write_thread_message(cr, uid, ids, 
            subject=_('Change state'), 
            body=_('Confirmed sending for this payment'), 
            context=None,
            )
            
        return self.write(cr, uid, ids, {
            'confirmed_user_id': uid,
            'confirmed_date': datetime.now().strftime(
                DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'confirmed',
            }, context=context)

    def duelist_done(self, cr, uid, ids, context=None):
        self.write_thread_message(cr, uid, ids, 
            subject=_('Change state'), 
            body=_('Payment will be notified manually (no automation)'), 
            context=None,
            )

        return self.write(cr, uid, ids, {
            'done_user_id': uid,
            'done_date': datetime.now().strftime(
                DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'done',
            }, context=context)

    def duelist_cancel(self, cr, uid, ids, context=None):
        self.write_thread_message(cr, uid, ids, 
            subject=_('Change state'), 
            body=_('Payment canceling, no automatic notification'), 
            context=None,
            )

        return self.write(cr, uid, ids, {
            'cancel_user_id': uid,
            'cancel_date': datetime.now().strftime(
                DEFAULT_SERVER_DATETIME_FORMAT),
            'state': 'cancel',
            }, context=context)

    # fields date
    def _get_date_month_4_group(self, cr, uid, ids, fields, args, context=None):
        ''' Fields function for calculate 
        '''
        res = {}
        for doc in self.browse(cr, uid, ids, context=context):
            if doc.date:
                res[doc.id] = ('%s' % doc.date)[:7]
            else:
                res[doc.id] = _('Nessuna')
        return res

    # fields deadline
    def _get_deadline_month_4_group(self, cr, uid, ids, fields, args, 
            context=None):
        ''' Fields function for calculate 
        '''
        res = {}
        for doc in self.browse(cr, uid, ids, context=context):
            if doc.deadline:
                res[doc.id] = ('%s' % doc.deadline)[:7]
            else:
                res[doc.id] = _('Nessuna')
        return res

    # -------------------------------------------------------------------------
    # Store function:    
    # -------------------------------------------------------------------------
    def _store_date_deadline_month(self, cr, uid, ids, context=None):
        ''' if change date reload data
        '''
        _logger.warning('Change date_mont depend on date or deadline')
        return ids

    # -------------------------------------------------------------------------
    #                                  Fields
    # -------------------------------------------------------------------------
    _columns = {
        # Generic info (imported):
        'name': fields.char('Ref.', size=64, required=True, 
            help='Invoice reference'),
        'date': fields.date('Date'),
        'deadline': fields.date('Deadline'),

        'date_month': fields.function(
            _get_date_month_4_group, method=True, 
            type='char', string='Mese inser.', size=15,
            store={
                'sql.payment.duelist': (
                    _store_date_deadline_month, ['date'], 10),
                }), 
        'deadline_month': fields.function(
            _get_deadline_month_4_group, method=True, 
            type='char', string='Scadenza', size=15, 
            store={
                'sql.payment.duelist': (
                    _store_date_deadline_month, ['deadline'], 10),
                }), 
                        
        'partner_id': fields.many2one('res.partner', 'Customer',
            required=True),
        'duelist_mail': fields.related('partner_id', 'duelist_mail', 
            type='char', string='Due list address', size=400),
        'country_id': fields.related('partner_id', 'country_id', 
            type='many2one', relation="res.country", string='Country', 
            store=True),
        'duelist_optin': fields.related('partner_id','duelist_optin', 
            type='boolean', string='Partner opt-in'),

        'total': fields.float('Total', digits=(16, 3)),
        'currency_id': fields.many2one('res.currency', 'Currency',
            required=False),
        'note': fields.text('Note'),
        'payment_type': fields.selection([
            ('R', 'RIBA'),
            ('B', 'Bank transfer'),
            ('M', 'Cash'),
            ('V', 'MAV'),
            ], 'Payment type', select=True, readonly=False),
        
        # Mail stage info:
        #'email_last_date': fields.date('E-mail last date'),
        #'email_next_date': fields.date('E-mail next date'),
        'todo_stage_id': fields.many2one('sql.payment.stage', 'Stage todo',
            required=False),
        'stage_id': fields.many2one('sql.payment.stage', 'Stage', 
            required=False),

        # Workflow:
        'draft_date': fields.date('Creation date'),
        'confirmed_date': fields.date('Confirmed date'),
        'confirmed_user_id': fields.many2one('res.users', 'Confirmed user',
            required=False),
        'done_date': fields.date('Done date'),
        'done_user_id': fields.many2one('res.users', 'Done user',
            required=False),
        'cancel_date': fields.date('Cancel date'),
        'cancel_user_id': fields.many2one('res.users', 'Done user',
            required=False),
        'state': fields.selection([
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('done', 'Done'),
            ('cancel', 'Cancel'),
            ], 'State', select=True, readonly=True),
        }

    _defaults = {
        'state': lambda *a: 'draft',
        'draft_date': datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT),
        'stage_id': lambda *x: False, 
        'todo_stage_id': lambda *x: False, 
        # s, cr, uid, ctx: s.pool.get('sql.payment.stage').get_default(cr, uid, context=ctx),
        }

class res_partner(osv.osv):
    ''' Add extra field for manage extra fields
    '''
    _name = 'res.partner'
    _inherit = 'res.partner'

    def _get_duelist_totals(self, cr, uid, ids, field, args, context=None):
        ''' Multifunction for compute uncovered amount and value
            Check all payment loaded deadlined not closed (or canceled)
        ''' 
        res = {}
        today = datetime.now().strftime(DEFAULT_SERVER_DATE_FORMAT)
        
        for partner in self.browse(cr, uid, ids, context=context):
            res[partner.id] = {}
            uncovered = exposition = 0.0    
            
            for due in partner.duelist_ids:
                if due.deadline < today:
                    uncovered += due.total
                exposition += due.total

            res[partner.id]['duelist_uncovered_amount'] = uncovered
            res[partner.id]['duelist_exposition_amount'] = exposition
            res[partner.id]['duelist_uncovered'] = uncovered > 0.0            

            if partner.duelist_fido and exposition > partner.duelist_fido:
                res[partner.id]['duelist_over_fido'] = True
            else:    
                res[partner.id]['duelist_over_fido'] = False
        return res
    
    _columns = {
        'duelist_fido': fields.integer('FIDO'),
        'duelist_mail': fields.char('Due list address', size=400),
        'duelist_optin': fields.boolean('Duelist opt-in'),
        'duelist_ids': fields.one2many(
            'sql.payment.duelist', 'partner_id', 'Duelist'),

        # ---------------------------------------------------------------------
        # Calculated fields:        
        # ---------------------------------------------------------------------
        # Test:
        'duelist_uncovered': fields.function(_get_duelist_totals, 
            method=True, type='boolean', string='Insolvent', 
            store=False, multi='totals', help='Payment over data present'),
        'duelist_over_fido': fields.function(_get_duelist_totals, 
            method=True, type='boolean', string='Over FIDO', 
            store=False, multi='totals', help='Exposition over FIDO'),
        
        # Amount:
        'duelist_uncovered_amount': fields.function(_get_duelist_totals, 
            method=True, type='float', string='Payment over data', 
            store=False, multi='totals', help='Sum of payment over data'),
        'duelist_exposition_amount': fields.function(_get_duelist_totals, 
            method=True, type='float', string='Total open payment', 
            store=False, multi='totals', help='Sum of all open payment'),

    }

class res_currency(osv.osv):
    ''' Add extra field for manage extra fields
    '''
    _name = 'res.currency'
    _inherit = 'res.currency'

    _columns = {
        'sql_id': fields.integer('SQL ID'),
        'sql_name': fields.char('Name', size=20),
    }
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
