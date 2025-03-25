# -*- coding: utf-8 -*-
##############################################################################
#
#
#    Copyright (C) 2013-Today(www.aalmirplastic.com).
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

from openerp import fields, models ,api, _
from openerp.tools import amount_to_text_fr
from openerp import tools
from datetime import datetime, date, timedelta
from openerp.tools import float_is_zero, float_compare
from openerp.tools.translate import _
from openerp.tools import amount_to_text_en
from openerp.tools.amount_to_text_en import amount_to_text
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
from openerp.exceptions import UserError, RedirectWarning, ValidationError
from urllib import urlencode
from urlparse import urljoin
import base64
import json
import math

class AccountInvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    product_hs_code=fields.Char('Hs Code', related='product_id.product_hs_code')
    invoice_ids=fields.Many2one('account.invoice')
    gross_weight=fields.Float('Net Weight(Kg)', compute='grossweight')
    net_weight=fields.Float('Gross Weight(Kg)', compute='netweight')
    packaging_id=fields.Many2one('product.packaging' ,string='Packaging', compute='product_packaging')
    purchase_id=fields.Many2one('purchase.order' ,string='PO',store=True)
    lpo_documents=fields.Many2many('customer.upload.doc', string='LPO Documents')
    pack_qty=fields.Integer('Packaging Qty', compute='product_packaging')
    external_no=fields.Char('External No.', compute='product_ext_no')

    @api.multi
    @api.depends('product_id')
    def product_ext_no(self):
        for record in self:
            if record.product_id:
               pricelist=self.env['product.pricelist'].search([('customer','=',record.partner_id.id)])
               if pricelist:
                  for plist in pricelist:
                      if plist.currency_id.id == record.currency_id.id:
                         cust=self.env['customer.product'].search([('product_id','=',record.product_id.id),('pricelist_id','=',plist.id)])
                         if cust:
                            record.external_no=cust.ext_product_number
                         else:
                            record.external_no=str("NA")

    @api.multi
    @api.depends('product_id','quantity', 'product_id.packaging_ids','gross_weight','invoice_id.picking_ids')
    def netweight(self):
        for rec in self:
		if rec.packaging_id and rec.packaging_id.qty:
			gross_wt=0.0
			for pick in rec.invoice_id.picking_ids:
				for operation in pick.pack_operation_product_ids:
					if rec.product_id.id == operation.product_id.id and rec.quantity == operation.qty_done:
						gross_wt += operation.net_weight
						break
			if not rec.invoice_id.picking_ids or not gross_wt :
				sec=self.env['product.packaging'].search([('pkgtype','=','secondary'),
							('product_tmpl_id','=',rec.product_id.product_tmpl_id.id),
							('unit_id','=',rec.packaging_id.uom_id.id)],limit=1)		
				pack_qty=math.ceil(rec.quantity /rec.packaging_id.qty)
				pallet_qty = math.ceil(pack_qty / (sec.qty if sec else 1))
				gross_wt = rec.gross_weight +(pack_qty * rec.packaging_id.uom_id.product_id.weight) + \
						(pallet_qty * (sec.uom_id.product_id.weight if sec.uom_id else 0))
              		rec.net_weight = gross_wt
              			

    @api.multi
    @api.depends('product_id','quantity','product_id.weight')
    def grossweight(self):
        for rec in self:
        	if rec.packaging_id:
        		rec.gross_weight=(rec.quantity * (rec.product_id.weight if rec.uom_id.name!='Kg' else 1))
        	else:
        		rec.gross_weight=0.0
               
    @api.multi
    @api.depends('product_id','quantity')
    def product_packaging(self):
        for rec in self: 
		if rec.sale_line_ids:
			if rec.sale_line_ids.product_packaging:
				rec.packaging_id = rec.sale_line_ids.product_packaging.id
		if not rec.packaging_id:
	            	for packg in rec.product_id.packaging_ids:
    				if packg.pkgtype == 'primary':
					rec.packaging_id =packg.id
					break
		rec.pack_qty =math.ceil(rec.quantity /rec.packaging_id.qty if rec.packaging_id else 0)
	
    @api.multi
    def write(self, vals):
        if vals.has_key('price_unit'):
            if self[0].product_id.name == 'Advance payment':
                line_ids = self.env['sale.order.line'].search([('order_id.name', 'like', self[0].origin), ('product_id', '=', self[0].product_id.id)])
                if line_ids:
                    line_ids.sudo().write({'price_unit': vals.get('price_unit')})
        return super(AccountInvoiceLine, self).write(vals)

class AccountInvoice(models.Model):
    _inherit = 'account.invoice'
  
    ## already apply
    '''@api.multi    
    @api.depends('taxe',)
    def compute_global_tax(self):
        for record in self.invoice_line_ids:
            amount=0.0
            body='Taxes are Applied on this invoice:'
            body +='<li>Applied By:'+str(self.env.user.name)  +'</li>'
            body +="<li>Date:" +str(date.today()) +"</li>"
            for tax in self.taxe:
                    amount=(record.price_subtotal * tax.amount) /100
		    account = record.product_id.property_account_income_id or record.product_id.categ_id.property_account_income_categ_id
		    if record.product_id.name != 'Deposit Product' and self.advance_invoice !=True:
		        record.write({'invoice_line_tax_ids':[(6, 0, [x.id for x in self.taxe])]})
                        self.compute_taxes()
		        self.tax_apply=True
                        self.tax_cancel=False                 
		    else:
		       if self.advance_invoice==True and record.product_id.name == 'Deposit Product':
		          record.write({'invoice_line_tax_ids':[(6, 0, [x.id for x in self.taxe])]})
                          self.compute_taxes()
		          self.tax_apply=True
                          self.tax_cancel=False 
                    body +='<li>Taxes Name:'+str(tax.name)  +'</li>'
            self.message_post(body=body)'''

    '''@api.multi
    def cancel_tax(self):
        for record in self:
            if record.tax_line_ids:
               body='<span style="color:red">Applied Taxes are Cancelled:</span>'
               record.tax_line_ids.unlink()
               record.tax_apply=False  
               record.tax_cancel=True 
               body +='<li>Cancelled By:'+str(self.env.user.name)  +'</li>'
               body +="<li>Date:" +str(date.today()) +"</li>"
               record.message_post(body=body)'''
               
    state = fields.Selection([
            ('draft','Draft'),
            ('waiting_approval','Awaiting'),
            ('rejected','Rejected'),
            ('proforma', 'Pro-forma'),
            ('proforma2', 'Pro-forma'),
            ('open', 'Open'),
            ('paid', 'Paid'),
            ('cancel', 'Cancelled'),
        ], string='Status', index=True, readonly=True, default='draft',
        track_visibility='onchange', copy=False,
        help=" * The 'Draft' status is used when a user is encoding a new and unconfirmed Invoice.\n"
             " * The 'Pro-forma' status is used the invoice does not have an invoice number.\n"
             " * The 'Open' status is used when user create invoice, an invoice number is generated. Its in open status till user does not pay invoice.\n"
             " * The 'Paid' status is set automatically when the invoice is paid. Its related journal entries may or may not be reconciled.\n"
             " * The 'Cancelled' status is used when user cancel invoice.")

    delivery_date=fields.Datetime( string='Delivery Date', compute='payment_invoice_date')
    payment_date_inv =fields.Date('Invoice Due Date', compute='payment_invoice_date')
    invoice_due_date=fields.Datetime('Invoice Due Date')
    invoice_barcode=fields.Char('Barcode', related='number')
    signature= fields.Binary(string='Signature')
    depositor_name=fields.Char()
    depositor_mobile=fields.Char()
    document_id=fields.Many2many('customer.upload.doc', 'customer_invoice_rel','cust_doc_rel',
     string='LPO Number')
    user_ids=fields.Many2one('res.users', compute='user_name')
    visible_request_button= fields.Boolean(string='Visible Button', default=False)

    payment_term_request =fields.Selection([('request','Requested'),('approve','Approved'),('reject','Rejected')])

    taxe = fields.Many2many('account.tax', 
                                'product_taxes_rel_value_ext',
                                'prod_id',
                                 'tax_id',
                                'Global Taxes',)
                                
    check_vat=fields.Boolean('Print VAT')
    partner_vat=fields.Char('VAT',related='partner_id.vat')
    tax_documents=fields.Many2many('ir.attachment','customer_tax_documents_rel','invoice_id','doc_id','Upload Documents')
    
    @api.multi
    def show_payment_term(self):
	if self.payment_term_id.n_new_request and self.visible_request_button:
		form_id = self.env.ref('gt_order_mgnt.request_payment_term_wizard_form_view', False)
		return {
		    'type': 'ir.actions.act_window',
		    'view_type': 'form',
		    'view_mode': 'form',
		    'res_model': 'request.payment.term.wizard',
		    'views': [(form_id.id, 'form')],
		    'view_id': form_id.id,
		    'target':'new',
		} 

    @api.multi
    @api.onchange('payment_term_id')
    def n_payment_term(self):
	if self.payment_term_id.n_new_request:
		self.visible_request_button=True
	else:
		self.visible_request_button=False
	return 
    
    @api.multi
    def approve_bill(self):
        self.signal_workflow('invoice_open')
        self.write({'approved_by':self._uid})
        group = self.env['res.groups'].search([('name', '=', 'Inform Once Bill Approved')])
        print "groupgroupgroupgroup",group
        self.send_bill(group,check='bill_approved')

        return True

    @api.multi
    def send_mail_for_approval(self):
      for record in self:
          group = self.env['res.groups'].search([('name', '=', 'Approve Bills')])
          record.send_bill(group,check='send_for_approval')
          
    @api.multi
    def send_approval_reminder(self):
      for record in self:
          group = self.env['res.groups'].search([('name', '=', 'Approve Bills')])
          record.send_bill(group,check='send_approval_reminder')
    
    @api.multi
    def user_name(self):
      for record in self:
          group = self.env['res.groups'].search([('name', '=', 'Accountant')])
	  for recipient in group.users:
              record.user_ids = recipient.id
              
    #comment=fields.Text()
    @api.multi
    @api.onchange('partner_id')
    def invoice_note_data(self):
        for record in self:
            record.comment =record.company_id.n_invoice_note

    @api.one
    @api.depends('state', 'currency_id', 'invoice_line_ids.price_subtotal','move_id.line_ids.amount_residual',
        		'move_id.line_ids.currency_id', 'advance_invoice')
    def _compute_residual(self):
        residual = 0.0
        residual_company_signed = 0.0
        if self.advance_invoice:
           self.residual_signed = 0.0
        self.residual = 0.0
        sign = self.type in ['in_refund', 'out_refund'] and -1 or 1
        for line in self.sudo().move_id.line_ids:
            if line.account_id.internal_type in ('receivable', 'payable'):
                residual_company_signed += line.amount_residual
                if line.currency_id == self.currency_id:
                    residual += line.amount_residual_currency if line.currency_id else line.amount_residual
                else:
                    from_currency = (line.currency_id and line.currency_id.with_context(date=line.date)) or line.company_id.currency_id.with_context(date=line.date)
                    residual += from_currency.compute(line.amount_residual, self.currency_id)
        self.residual_company_signed = abs(residual_company_signed) * sign
        self.residual_signed = abs(residual) * sign
        self.residual = abs(residual)
        digits_rounding_precision = self.currency_id.rounding
        if float_is_zero(self.residual, precision_rounding=digits_rounding_precision):
            self.reconciled = True
        else:
            self.reconciled = False

    @api.multi
    def payment_invoice_date(self):
        for record in self:
            stock=0
           
            if record.type == 'out_invoice':
                stock=self.env['stock.picking'].search([('origin','=',record.origin),('state','=','delivered')], limit=1)
            if record.type == 'in_invoice':
                stock=self.env['stock.picking'].search([('origin','=',record.origin),('state','=','done')], limit=1)
            if stock:
               value=0
               days=0
               record.delivery_date=stock.delivery_date 
               if record.payment_term_id.payment_term_depend == 'delivery':
                      date = datetime.strptime(str(stock.delivery_date),'%Y-%m-%d %H:%M:%S') if stock.delivery_date else datetime.strptime(str(stock.min_date),'%Y-%m-%d %H:%M:%S')
                      record.payment_date_inv=date
               if record.payment_term_id.payment_term_depend == 'credit' and record.payment_term_id.payment_due == 'delvery':            
                      value = record.payment_term_id.time_limit_value
                      if record.payment_term_id.time_limit_type == 'day':
                         days = value
                      elif record.payment_term_id.time_limit_type == 'week':
                         days = value * 7
                      elif record.payment_term_id.time_limit_type == 'month':
                         days = value * 30
                      date_dl=datetime.strptime(str(stock.delivery_date),'%Y-%m-%d %H:%M:%S')+timedelta(int(days)) if stock.delivery_date else datetime.strptime(str(stock.min_date),'%Y-%m-%d %H:%M:%S')+timedelta(int(days))
                      record.payment_date_inv=date_dl
            else:
                record.payment_date_inv=record.sale_id.create_date
            if record.date_invoice and record.payment_term_id.payment_term_depend == 'credit' and record.payment_term_id.payment_due == 'invoice':# and record.state == 'open':                      
               value = record.payment_term_id.time_limit_value
               if record.payment_term_id.time_limit_type == 'day':
                  days = value
               elif record.payment_term_id.time_limit_type == 'week':
                  days = value * 7
               elif record.payment_term_id.time_limit_type == 'month':

                    days = value * 30
               date_dl=datetime.strptime(str(record.date_invoice),'%Y-%m-%d')+timedelta(int(days))
               record.payment_date_inv=date_dl
            if record.invoice_due_date and  record.advance_invoice == True:
               record.payment_date_inv=record.invoice_due_date

    paid_amount=fields.Float('Paid Amount', compute='total_paid_amount')
    proforma_date=fields.Date('ProForma Date', compute='proforma_date_visible')	#add by vml
    report_currency_id = fields.Many2one('res.currency', string="Converted Currency") #add by vml
    due_payment = fields.Boolean('Due Payment', default=False)
    #n_invoice_type = fields.Selection([('advance', 'Advance'),('normal', 'Normal')], string='Invoice Payment Type ', readonly=True, copy=False, index=True, default='normal')
    ### add fiels 
    delivery_no=fields.Char('Delivery Note No')
    contact_number=fields.Char(related='partner_id.mobile', string='Contact Number') 
    picking_ids = fields.Many2many('stock.picking',  string='Picking associated to this sale')
    
    delivery_id=fields.Many2one('stock.picking', 'Delivery Number')
    sale_id=fields.Many2one('sale.order' , string='Sale Order') 
    invoice_paid_date=fields.Date('Invoice Paid Date', compute='paid_invoice_date')
    total_current_invoice=fields.Float("Total Current Pending Invoice Amount", compute='total_invoice_val')
    advance_invoice=fields.Boolean('Invoice Payment Type',default=False)
    residual_new=fields.Float('Residual New', compute='cal')
    residual_new1=fields.Float('Residual New', compute='cal')
    receipt_remark=fields.Text('Remark On receipt')
    order_line=fields.One2many('account.invoice.line','invoice_ids')
    total_sale_amount=fields.Float('Total Order Amount',compute='totalsaleamount')
    payable_amount=fields.Float('Payable Amount')
    payable_discount=fields.Char()
    ##add new fields For report 
    refuse_reason = fields.Char(string='Refuse Reason',track_visibility='always' )

    manufactured_by=fields.Char('Manufactured By', default='Aal Mir Plastic Industries ,PO Box 4537, Sharjah, UAE.')
    origin_id=fields.Many2one('res.country', string='Origin of Goods',default=lambda self: self.env['res.country'].search([('code', '=','AE')]))
    total_gross_weight=fields.Float('Total Net Wt(Kg)', compute='totalweight')
    total_net_weight=fields.Float('Total Gross Wt(Kg)', compute='totalweight')
    shipment_mode=fields.Selection([('sea', 'Sea'), ('road', 'Road'), ('air', 'Air')], string="Shipment Mode")
    term_of_delivery=fields.Many2one('stock.incoterms',string='Terms', compute='LPO_number')
    check_origin=fields.Boolean(default=True)
    check_manuf=fields.Boolean(default=True)
    check_hs=fields.Boolean('Print HS Code on Report')
    check_gross=fields.Boolean()
    check_net=fields.Boolean()
    check_ship=fields.Boolean()
    check_term=fields.Boolean(default=False) 
    check_lpo=fields.Boolean() 
    partner_invoice_id=fields.Many2one('res.partner','Invoice Address')
    check_destination=fields.Boolean(default=False)
    check_partner=fields.Boolean(default=True)
    check_invnumber=fields.Boolean('Print Invoice No. on Report',default=True)
    check_date_withcol=fields.Boolean('Print Date With Column on Report',default=True)
    check_date_withnotcol=fields.Boolean('Print Only Date Column on Report')
    check_sale=fields.Boolean('Print SaleOrder No. on Report',default=True)
    check_saleperson=fields.Boolean('Print SalesPerson Name on Report',default=True)
    check_packaging=fields.Boolean('Print Packaging on Report')
    check_packaging_count=fields.Boolean('Print Packaging Count on Report')
    check_payment_term=fields.Boolean(default=True)
    check_do_number=fields.Boolean()
    comment = fields.Text('Additional Information', readonly=False, states={'draft': [('readonly', False)]})
    check_currency=fields.Boolean(default=True)   
    reference = fields.Char(string='Vendor Reference',
        track_visibility='onchange',help="The partner reference of this invoice.", readonly=True, states={'draft': [('readonly', False)]})    #vendor_invoice_no=fields.Char('Vendor Invoice No.')
    vendor_invoice_date=fields.Date('Vendor Invoice Date', track_visibility='onchange')
    vendor_uploaded_document = fields.Binary(string='Vendor Document',track_visibility='onchange',default=False , attachment=True)
    vendor_doc_name=fields.Char()
    approved_by=fields.Many2one('res.users','Payment Approved By')   
    send_bill_bool=fields.Boolean('Hide Send mail button', default=False)
    show_stamp=fields.Boolean('Show Stamp on Report',default=True)
    customer_name_report=fields.Char('Customer Name on Report',default='Customer Name')
    all_invoice_due_amount=fields.Float('Previous Invoices Due Amount', compute='_due_invoice_amount')
    report_company_name=fields.Many2one('res.company','LetterHead Company Name',default=lambda self: self.env['res.company']._company_default_get('account.inovice'))
    destination_report=fields.Char('Address on Report', default='Address',help="To Print Invoice address on report")
    delivey_address=fields.Char('Delivery Address', default='Delivery Address',help="To Print Delivery Address\n Take Address from related delivery order\n To print Address type the Label which you want to be print on Report")
    total_pack=fields.Float('Total Qty', compute='totalqty')
    check_lpo_line=fields.Boolean('Print LPO No. in Product Line',default=False)
    
    @api.multi
    def totalqty(self):
        for record in self:
            if record.invoice_line_ids:
               record.total_pack=sum(line.pack_qty for line in record.invoice_line_ids)

    @api.multi
    def _due_invoice_amount(self):
        for record in self:
            print "resdfd sale-------------",record.sale_id.id
            invoices=self.env['account.invoice'].search([('partner_id','=',record.partner_id.id),('id','!=',record.id),('state','=','open')])
            print "invoicesinvoicesinvoices",invoices
            if invoices:
               total=0.0
               for invoice in invoices:
                   total += invoice.residual_new1 if invoice.residual_new1 else invoice.amount_total
               record.all_invoice_due_amount=total

    @api.multi 
    def send_bill(self,group,check):
        if group:
            user_ids = self.env['res.users'].sudo().search([('groups_id', 'in', [group.id])])
            print "user_idsuser_ids",user_ids
            email_to = ''.join([user.partner_id.email + ',' for user in user_ids])
            email_to = email_to[:-1]
            print "email_toemail_to",email_to
        else:
            email_to=self.approved_by.login
        for record in self:
            if check=='send_for_approval':
                temp_id = self.env.ref('gt_order_mgnt.email_template_for_invoice_vendor_send_approval')
            elif check=='send_approval_reminder':
                  temp_id = self.env.ref('gt_order_mgnt.email_template_for_invoice_vendor_send_approval_reminder')
            elif check=='bill_approved':
                  temp_id = self.env.ref('gt_order_mgnt.email_template_for_invoice_vendor_bill_approved')
            elif check=='bill_refused':
                  temp_id = self.env.ref('gt_order_mgnt.email_template_for_invoice_vendor_bill_refused')
            else:
                temp_id = self.env.ref('gt_order_mgnt.email_template_for_invoice_vendor123')
            if temp_id:
               base_url = self.env['ir.config_parameter'].get_param('web.base.url')
	       query = {'db': self._cr.dbname}
	       fragment = {
			 'model': 'account.invoice',
			 'view_type': 'form',
			 'id': record.id,
			}
	       url = urljoin(base_url, "/web?%s#%s" % (urlencode(query), urlencode(fragment)))
               print "urlurl",url
               text_link = _("""<a href="%s">%s</a> """) % (url,"BILL")
               print "text_linktext_linktext_link",text_link
               if check=='send_for_approval':
                    body ='You have been requested for approval on the release of payment for the attached bill. ' 
                    body +='<li> <b>View Bill :</b> '+str(text_link) +'</li>'
                    record.state='waiting_approval'

               elif check=='send_approval_reminder':
                    body ='This is reminder for approval on release of payment for the attached bill. ' 
                    body +='<li> <b>View Bill :</b> '+str(text_link) +'</li>'
               elif check=='bill_approved':
                    email_to+=','+record.user_id.login
                    body ='Payment is Approved for the attached bill. ' 
                    body +='<li> <b>View Bill :</b> '+str(text_link) +'</li>'
               elif check=='bill_refused':
                    email_to=record.user_id.login

                    body ='Payment is Refused for the attached bill. ' 
                    body +='<li> <b>View Bill :</b> '+str(text_link) +'</li>'

               else:
                    body ='This is to just inform you that you have been marked as a person who has approved the release of payment for the attached bill. ' 

                    body +='<li> <b>View Bill :</b> '+str(text_link) +'</li>'
                    body +='<li> <b>Bill Due date :</b>'+str(record.date_due) +'</li>'
                    body +='<li> <b>Payment Term :</b> '+str(record.payment_term_id.name) +'</li>'
                    body +='<li> <b>Total Bill Amount :</b>'+str(record.amount_total) +str(record.currency_id.symbol)+'</li>'
                    body += '</b>Note:</b>After your approval, once payment is done, you will be informed.'
	       temp_id.write({'body_html': body, 'email_to':email_to,
                              'email_from':self.env.user.login})
               values = temp_id.generate_email(record.id)
               mail_mail_obj = self.env['mail.mail']
               msg_id = mail_mail_obj.create(values) 
               Attachment = self.env['ir.attachment']
               attachment_ids = values.pop('attachment_ids', [])
               attachments = values.pop('attachments', [])
               attachment_data={} 
               if record.vendor_uploaded_document:
                  attachments.append((self.vendor_doc_name,self.vendor_uploaded_document))
               purchase=self.env['purchase.order'].search([('name','=',record.origin)], limit=1)
               if purchase:
                  report_obj = self.pool.get('report')
                  data=report_obj.get_pdf(self._cr, self._uid, purchase.ids,
                              'purchase.report_purchaseorder',  context=self._context)
                  val  = base64.encodestring(data)
                  rep_name='Purchase Order:'+str(purchase.name)+'.pdf'
                  attachments.append((rep_name,val))
               if attachments:
		   for attachment in attachments: 
		       attachment_data = {
				        'name': attachment[0],
				        'datas_fname': attachment[0],
				        'datas': attachment[1],
				        'res_model': 'mail.message',
				        'res_id': msg_id.mail_message_id.id,
                                        'type':'binary'
				        
				          }
		       attachment_ids.append(Attachment.create(attachment_data).id)
		   if attachment_ids:
		      values['attachment_ids'] =[(4, attachment_ids)]
		      msg_id.write({'attachment_ids':[(4, attachment_ids)]}) 
               record.send_bill_bool=True
               msg_id.send()	       

    @api.multi
    @api.depends('invoice_line_ids.gross_weight','invoice_line_ids.net_weight')
    def totalweight(self):
        for record in self:
            if record.invoice_line_ids:
               record.total_gross_weight=sum(line.gross_weight for line in record.invoice_line_ids)
               record.total_net_weight=sum(line.net_weight for line in record.invoice_line_ids)
            else:
                record.total_gross_weight=0.0
                record.total_net_weight=0.0

    @api.multi
    @api.depends('origin')
    def LPO_number(self):
        for record in self:
            if record.origin:
               sale=self.env['sale.order'].search([('name','=',record.origin)], limit=1)
               if sale:
                  record.lpo_number=sale.lpo_number
                  record.term_of_delivery=sale.incoterm.id
               purchase=self.env['purchase.order'].search([('name','=',record.origin)], limit=1)
               if purchase:
                  record.term_of_delivery=purchase.incoterm_id.id
    @api.multi
    @api.depends('sale_id')
    def totalsaleamount(self):
       for record in self:
          currency_id=record.currency_id if record.currency_id else self.env.user.company_id.currency_id
          if record.sale_id:
             record.total_sale_amount=record.currency_id.compute((record.sale_id.amount_total),currency_id)
             
    @api.multi
    def credit_increase_amount(self):
        for line in self:
            move_form = self.env.ref('gt_order_mgnt.customer_credit_form_ac', False)
            if move_form:
                return {
                    'type': 'ir.actions.act_window',
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': 'res.partner',
                    'views': [(move_form.id, 'form')],
                    'res_id': line.partner_id.id,
                    'target': 'current',
                    'domain':[('id','=',self.partner_id.id)],
                }
        return True
        
    @api.multi
    @api.depends('advance_invoice','residual_signed','residual')
    def cal(self):
        for record in self:
            if record.advance_invoice and record.state == 'draft':
               record.residual_new=0.0
               record.residual_new1=0.0  
            else:
		if record.state=='paid':
			record.residual_new1=0.0 

              	elif record.payments_widget:
		       d=json.loads(record.payments_widget)
		       if d:
		          pay=0.0
		          for payment in d['content']:
		              pay += payment['amount']
		          record.residual_new=record.amount_total - pay if record.state =='open' else 0.0
		          record.residual_new1=record.amount_total - pay if record.state =='open' else 0.0
		       else :
		           record.residual_new=record.amount_total
		           record.residual_new1=record.amount_total

    @api.multi
    def total_invoice_val(self):
         for record in self:
             total=0.0
             invoice=self.env['account.invoice'].search([('state','=','open'),('origin','=',record.origin)])
             if invoice:
                pay=0.0
                for inv in invoice:
                    if inv.payments_widget:
                       d = json.loads(inv.payments_widget)
                       if d:
                          for payment in d['content']:
                              pay += payment['amount']
                          total += inv.amount_total
                record.total_current_invoice=total - pay

    @api.multi
    def paid_invoice_date(self):
        for record in self:
            if record.state == 'paid':
               record.invoice_paid_date = date.today()

    @api.multi
    def aalmir_invoice_print(self):
        self.ensure_one()
        self.sent = True
        return self.env['report'].get_action(self, 'gt_order_mgnt.report_invoice_aalmir') 
        #if self._context.get('in_invoice'):
           #return self.env['report'].get_action(self, 'gt_order_mgnt.report_invoice_aalmir')
       # if self._context.get('out_invoice'):
         #  return self.env['report'].get_action(self, 'gt_order_mgnt.report_invoice_aalmir_vendor')
         
    @api.multi
    def print_advance_payment_receipt(self):
        return self.env['report'].get_action(self, 'stock_merge_picking.report_payment')
        
    @api.multi
    @api.depends('amount_total', 'residual_new1')
    def total_paid_amount(self):
        for record in self:
            credit_currency_id=record.currency_id if record.currency_id else self.env.user.company_id.currency_id
            #record.paid_amount=record.currency_id.compute((record.amount_total - record.residual_new1),credit_currency_id) if record.residual_new1 else 0.0
            if record.payments_widget: 
               d = json.loads(record.payments_widget)
               if d:
		  pay=0.0
		  for payment in d['content']:
		      pay +=payment['amount']
		  record.paid_amount= record.currency_id.compute((pay),credit_currency_id)
            else:
               record.paid_amount=0.0  
    lpo_number = fields.Char(string='PO Number')
    n_lpo_receipt_date = fields.Date(string="PO Receipt Date")
    n_lpo_issue_date = fields.Date(string='PO Issued Date')
    n_lpo_name = fields.Char(string='PO name')
    n_lpo_document = fields.Binary(string='PO uploaded Document', default=False , attachment=True) 
    n_pop_receipt_date = fields.Date(string="POP Receipt Date")
    n_pop_uploaded_document = fields.Binary(string='POP uploaded Document', default=False, attachment=True)
#CH_N038 end <<

   ##ADD function for proforma date VML
    @api.multi
    def proforma_date_visible(self):
        for record in self:
            if record.state == 'proforma' or record.state == 'proforma2':
               record.proforma_date = datetime.now()
    ### add method total convert in words
    @api.depends('amount_total', 'currency_id')
    def compute_text(self):
        return amount_to_text_fr(self.amount_total, self.currency_id.symbol)

    @api.multi
    def check_due_on_invoice(self):
        invoice_ids = self.search([('state', '=', 'open')])
        for invoice in invoice_ids:
            value=0
            days=0
            if invoice.payment_term_id:
                if invoice.payment_term_id.payment_term_depend == 'delivery':
                   value1= invoice.payment_term_id.payment_days
                   days=value1
                if invoice.payment_term_id.payment_term_depend == 'credit':
                    value = invoice.payment_term_id.time_limit_value
                    if invoice.payment_term_id.time_limit_type == 'day':
                        days = value
                    elif invoice.payment_term_id.time_limit_type == 'week':
                        days = value * 7
                    elif invoice.payment_term_id.time_limit_type == 'month':
                        days = value * 30
                    if invoice.date_invoice:
                        date = datetime.strptime(invoice.date_invoice, '%Y-%m-%d')
                        due_date = date + timedelta(days=days)
                        if date.today() < due_date:
                            invoice.due_payment = True
                            sale_ids = self.env['sale.order'].search([('name', '=', invoice.origin)])
                            if sale_ids:
                                sale_ids.write({'due_payment': 'pending'})
                            temp_id = self.env.ref('gt_order_mgnt.email_template_for_due_payment')
                            if temp_id:
                                user_obj = self.env['res.users'].browse(self.env.uid)
                                base_url = self.env['ir.config_parameter'].get_param('web.base.url')
                                query = {'db': self._cr.dbname}
                                fragment = {
                                    'model': 'account.invoice',
                                    'view_type': 'form',
                                    'id': invoice.id,
                                }
                                url = urljoin(base_url, "/web?%s#%s" % (urlencode(query), urlencode(fragment)))
                                
                                group_id = self.env.ref('account.group_account_user', False)
                                if group_id:
                                    user_ids = self.env['res.users'].sudo().search([('groups_id', 'in', [group_id.id])])
                                    if user_ids:
                                        email_to = ''.join([user.partner_id.email + ',' for user in user_ids])
                                        email_to = email_to[:-1]
                                        text_link = _("""<a href="%s">%s</a> """) % (url,invoice.name)

                                        body_html_accountant = """<div>
                                <p> <strong>Due Payment</strong></p><br/>
                                <p>Dear Accountant,<br/>
                                    <b>Payment for </b>invoice :  <b> %s </b>is due. <br/>
                                </p>
                                </div>"""%(text_link)

                                        body_html_accountant = self.pool['mail.template'].render_template(self._cr, self._uid, body_html_accountant, 'account.invoice',invoice.id, context=self._context)
                                        temp_id.write({'body_html': body_html_accountant, 'email_to' : email_to, 'email_from': user_obj.user_id.email})
                                        temp_id.send_mail(invoice.id)
                                        
        return True
        
#CH_N031 inherite class to check advance payment is done or not start  
    @api.onchange('partner_id', 'company_id')
    def _onchange_partner_id(self):
        account_id = False
        payment_term_id = False
        fiscal_position = False
        bank_id = False
        p = self.partner_id
        company_id = self.company_id.id
        type = self.type
        if p:
            partner_id = p.id
            rec_account = p.property_account_receivable_id
            pay_account = p.property_account_payable_id
            if company_id:
                if p.property_account_receivable_id.company_id and \
                        p.property_account_receivable_id.company_id.id != company_id and \
                        p.property_account_payable_id.company_id and \
                        p.property_account_payable_id.company_id.id != company_id:
                    prop = self.env['ir.property']
                    rec_dom = [('name', '=', 'property_account_receivable_id'), ('company_id', '=', company_id)]
                    pay_dom = [('name', '=', 'property_account_payable_id'), ('company_id', '=', company_id)]
                    res_dom = [('res_id', '=', 'res.partner,%s' % partner_id)]
                    rec_prop = prop.search(rec_dom + res_dom) or prop.search(rec_dom, limit=1)
                    pay_prop = prop.search(pay_dom + res_dom) or prop.search(pay_dom, limit=1)
                    rec_account = rec_prop.get_by_record(rec_prop)
                    pay_account = pay_prop.get_by_record(pay_prop)
                    if not rec_account and not pay_account:
                        action = self.env.ref('account.action_account_config')
                        msg = _('Cannot find a chart of accounts for this company, You should configure it. \nPlease go to Account Configuration.')
                        raise RedirectWarning(msg, action.id, _('Go to the configuration panel'))

            if type in ('out_invoice', 'out_refund'):
                account_id = rec_account.id
                #payment_term_id = p.property_payment_term_id.id   #CH_N133 comented 
            else:
                account_id = pay_account.id
                #payment_term_id = p.property_supplier_payment_term_id.id
            addr = p.address_get(['delivery'])
            fiscal_position = self.env['account.fiscal.position'].get_fiscal_position(p.id, delivery_id=addr['delivery'])

        self.account_id = account_id
        self.payment_term_id = payment_term_id
        self.fiscal_position_id = fiscal_position
        if self._context.get('default_purchase_id'):
            purchase =self.env['purchase.order'].browse(self._context.get('default_purchase_id'))
            self.payment_term_id=purchase.payment_term_id.id
        if type in ('in_invoice', 'out_refund'):
            bank_ids = p.commercial_partner_id.bank_ids
            bank_id = bank_ids[0].id if bank_ids else False
            self.partner_bank_id = bank_id
            return {'domain': {'partner_bank_id': [('id', 'in', bank_ids.ids)]}}
        return {}

class AccountPayment(models.Model):
	_inherit = 'account.payment'  

	@api.multi
	def post(self):
	    result=super(AccountPayment,self).post()
	    for rec in self.invoice_ids:
	    	product_amount={}
	    	total_paid=advance_paid=0.0
	    	curr_product=[]
	    	if not rec.advance_invoice:
		    	for rec_line in rec.invoice_line_ids:
		    		curr_product.append(rec_line.product_id.id)
		    		
                invoice_ids = self.env['account.invoice'].search([('type','=','out_refund'),('sale_id','=',rec.sale_id.id),('state','not in',('draft','cancel'))])
                for invoice in invoice_ids:
                	total_paid += (invoice.amount_total-invoice.residual_new1)
        		if invoice.advance_invoice==True:
        			advance_paid += (invoice.amount_total-invoice.residual_new1)
        		else:
				for line in invoice.invoice_line_ids:
					if line.product_id.id in curr_product:
						product_amount[line.product_id.id] = product_amount[line.product_id.id] + line.price_subtotal if product_amount.get(line.product_id.id) else line.price_subtotal
		flag=False
		if total_paid >= rec.sale_id.amount_total:
			flag=True		
		for sale in rec.sale_id.order_line:
			#if product_amount.get(sale.product_id.id):
			if product_amount.get(sale.product_id.id) >= sale.price_total or flag:
        				new_id=self.env['sale.order.line.status'].search([('n_string','=','paid')],limit=1)#add status
					if new_id:
						n_status_rel=[(4,new_id.id)]
						search_id=self.env['sale.order.line.status'].search([('n_string','in',('invoiced','partial_invoice'))]) ## add status
						if search_id:
							n_status_rel.extend([(3,i.id) for i in search_id._ids])
						sale.n_status_rel=n_status_rel
						
		sale_ids=self.env['sale.order'].search([('name','=',rec.origin)])
		if sale_ids:
		   if rec.state=='paid':
		       sale_ids.due_payment='done'
		       break
		   if rec.residual == self.amount:
		       sale_ids.due_payment='done'
		       break
		   else:
		       sale_ids.due_payment='half_payment'
                       break
            return result
#CH_N031 end <<

