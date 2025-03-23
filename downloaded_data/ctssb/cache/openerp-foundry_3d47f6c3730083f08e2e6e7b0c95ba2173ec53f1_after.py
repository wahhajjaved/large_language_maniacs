## KG Purchase Order ##

from datetime import *
import time
from openerp import tools
from openerp.osv import osv, fields
from openerp.tools.translate import _
import decimal_precision as dp
from itertools import groupby
from datetime import datetime, timedelta,date
from dateutil.relativedelta import relativedelta
import smtplib
import socket
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.MIMEImage import MIMEImage
import logging
from openerp import netsvc
from tools import number_to_text_convert_india
logger = logging.getLogger('server')
today = datetime.now()

import urllib
import urllib2
import logging
import base64
dt_time = time.strftime('%m/%d/%Y %H:%M:%S')

UOM_CONVERSATION = [
    ('one_dimension','One Dimension'),('two_dimension','Two Dimension')
]

class kg_purchase_order(osv.osv):
	
	def _amount_line_tax(self, cr, uid, line, context=None):
		logger.info('[KG OpenERP] Class: kg_purchase_order, Method: _amount_line_tax called...')
		val = 0.0
		qty = 0
		if line.price_type == 'per_kg':
			if line.product_id.uom_conversation_factor == 'two_dimension':
				if line.product_id.po_uom_in_kgs > 0:
					qty = line.product_qty * line.product_id.po_uom_in_kgs * line.length * line.breadth
			elif line.product_id.uom_conversation_factor == 'one_dimension':
				if line.product_id.po_uom_in_kgs > 0:
					qty = line.product_qty * line.product_id.po_uom_in_kgs
				else:
					qty = line.product_qty
			else:
				qty = line.product_qty
		else:
			qty = line.product_qty
			
		new_amt_to_per = line.kg_discount / qty
		amt_to_per = (line.kg_discount / (qty * line.price_unit or 1.0 )) * 100
		kg_discount_per = line.kg_discount_per
		tot_discount_per = amt_to_per + kg_discount_per

		for c in self.pool.get('account.tax').compute_all(cr, uid, line.taxes_id,
			line.price_unit * (1-(tot_discount_per or 0.0)/100.0), qty, line.product_id,
				line.order_id.partner_id)['taxes']:
			 
			val += c.get('amount', 0.0)
		return val	
	
	def _amount_all(self, cr, uid, ids, field_name, arg, context=None):
		logger.info('[KG OpenERP] Class: kg_purchase_order, Method: _amount_all called...')
		res = {}
		cur_obj=self.pool.get('res.currency')
		other_charges_amt = 0
		discount_per_value = 0
		for order in self.browse(cr, uid, ids, context=context):
			res[order.id] = {
				'total_amount': 0.0,
				'discount': 0.0,
				'amount_untaxed': 0.0,
				'amount_tax': 0.0,
				'grand_total': 0.0,
				'round_off': 0.0,
				'amount_total': 0.0,
				'other_charge': 0.0,
			}
			val = val1 = val3 = 0.0
			cur = order.pricelist_id.currency_id
			po_charges=order.value1 + order.value2
			
			if order.expense_line_id:
				for item in order.expense_line_id:
					other_charges_amt += item.expense_amt
			else:
				other_charges_amt = 0
				
			pol = self.pool.get('purchase.order.line')
			for line in order.order_line:
				discount_per_value = ((line.product_qty * line.price_unit) / 100.00) * line.kg_discount_per
				tot_discount = line.kg_discount + discount_per_value
				val1 += line.price_subtotal
				val += self._amount_line_tax(cr, uid, line, context=context)
				val3 += tot_discount
			res[order.id]['total_amount'] = (val1 + val3) - val
			print"res[order.id]['total_amount']",res[order.id]['total_amount']
			res[order.id]['other_charge'] = other_charges_amt or 0
			res[order.id]['amount_tax'] = val
			res[order.id]['amount_untaxed'] = val1 - val 
			res[order.id]['discount'] = val3
			res[order.id]['grand_total'] = val1
			res[order.id]['round_off'] = order.round_off
			res[order.id]['amount_total'] = val1 + order.round_off or 0.00
			
		return res
	
	def _get_order(self, cr, uid, ids, context=None):
		logger.info('[KG OpenERP] Class: kg_purchase_order, Method: _get_order called...')
		result = {}
		for line in self.pool.get('purchase.order.line').browse(cr, uid, ids, context=context):
			result[line.order_id.id] = True
		return result.keys()
	
	_name = "purchase.order"
	_inherit = "purchase.order"
	_order = "creation_date desc"
	
	_columns = {
		
		## Basic Info
		
		'note': fields.text('Remarks'),
		
		## Module Requirement Fields
		
		#~ 'po_type': fields.selection([('direct', 'Direct'),('frompi', 'From PI'),('fromquote', 'From Quote')], 'PO Type',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'po_type': fields.selection([('direct', 'Direct'),('frompi', 'From PI'),('fromquote', 'From Quote')], 'PO Type',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'bill_type': fields.selection([('cash','Cash'),('credit','Credit'),('advance','Advance')], 'Payment Mode',states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'po_expenses_type1': fields.selection([('freight','Freight Charges'),('others','Others')], 'Expenses Type1', readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)]}),
		'po_expenses_type2': fields.selection([('freight','Freight Charges'),('others','Others')], 'Expenses Type2', readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)]}),
		'value1':fields.float('Value1',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)]}),
		'value2':fields.float('Value2',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)]}),
		'vendor_bill_no': fields.float('Vendor.Bill.No',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)]}),
		'vendor_bill_date': fields.date('Vendor.Bill.Date',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)]}),
		'location_id': fields.many2one('stock.location', 'Destination', domain=[('usage','=','internal')], states={'approved':[('readonly',True)],'done':[('readonly',True)]} ),		
		'payment_term_id': fields.many2one('account.payment.term', 'Payment Term', readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)]}),
		'pricelist_id':fields.many2one('product.pricelist', 'Pricelist', states={'approved':[('readonly',True)],'done':[('readonly',True)]}, help="The pricelist sets the currency used for this purchase order. It also computes the supplier price for the selected products/quantities."),	
		'date_order': fields.date('PO Date',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'payment_mode': fields.many2one('kg.payment.master', 'Payment Term', readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'delivery_mode': fields.many2one('kg.delivery.master','Delivery Term', required=True,readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'partner_address':fields.char('Supplier Address', size=128,readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)]}),
		'email':fields.char('Contact Email', size=128,readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)]}),
		'contact_person':fields.char('Contact Person', size=128),
		'round_off': fields.float('Round off',size=5,readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)]}),
		'other_charge': fields.function(_amount_all, digits_compute= dp.get_precision('Account'), string='Other Charges(+)',
			 multi="sums", help="The amount without tax", track_visibility='always',store=True),		
		'discount': fields.function(_amount_all, digits_compute= dp.get_precision('Account'), string='Discount(-)',
			store={
				'purchase.order': (lambda self, cr, uid, ids, c={}: ids, ['order_line'], 10),
				'purchase.order.line': (_get_order, ['price_unit', 'tax_id', 'kg_discount', 'product_qty'], 10),
			}, multi="sums", help="The amount without tax", track_visibility='always'),
		'amount_untaxed': fields.function(_amount_all, digits_compute= dp.get_precision('Account'), string='Untaxed Amount',
			store={
				'purchase.order': (lambda self, cr, uid, ids, c={}: ids, ['order_line'], 10),
				'purchase.order.line': (_get_order, ['price_unit', 'tax_id', 'kg_discount', 'product_qty'], 10),
			}, multi="sums", help="The amount without tax", track_visibility='always'),
		'amount_tax': fields.function(_amount_all, digits_compute= dp.get_precision('Account'), string='Taxes',
			store=True, multi="sums", help="The tax amount"),
		'amount_total': fields.function(_amount_all, digits_compute= dp.get_precision('Account'), string='Net Amount',
			 multi="sums", store=True, help="The amount without tax", track_visibility='always'),
		'total_amount': fields.function(_amount_all, digits_compute= dp.get_precision('Account'), string='Total Amount',
			 multi="sums", store=True, help="The amount without tax", track_visibility='always'),
		'grand_total': fields.function(_amount_all, digits_compute= dp.get_precision('Account'), string='Grand Total',
			 multi="sums", store=True, help="The amount without tax", track_visibility='always'),
		'po_flag': fields.boolean('PO Flag'),
		'grn_flag': fields.boolean('GRN'),
		'name': fields.char('PO No.', size=64, select=True,readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)]}),
		'bill_flag':fields.boolean('PO Bill'),
		'amend_flag': fields.boolean('Amendment', select=True),
		'add_text': fields.text('Address',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'type_flag':fields.boolean('Type Flag'),
		'pi_flag':fields.boolean('Type Flag'),
		'delivery_address':fields.text('Delivery Address',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'term_price':fields.selection([('inclusive','Inclusive of all Taxes and Duties'),('exclusive', 'Exclusive')], 'Price',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}), 
		'term_warranty':fields.char('Warranty',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'term_freight':fields.selection([('Inclusive','Inclusive'),('Extra','Extra'),('To Pay','To Pay'),('Paid','Paid'),
						  ('Extra at our Cost','Extra at our Cost')], 'Freight',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}), 
		'quot_ref_no':fields.char('Quot. Ref.',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'text_amt':fields.char('Amount in Words'),
		'frieght_flag':fields.boolean('Freight Flag'),
		'version':fields.char('Version'),
		'purpose':fields.selection([('for_sale','For Production'),('own_use','Own use')], 'Purpose',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}), 
		'quotation_date': fields.date('Quotation Date',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'entry_mode': fields.selection([('manual','Manual'),('auto','Auto')],'Entry Mode'),
		'insurance': fields.selection([('sam','By Sam'),('supplier','By Supplier'),('na','N/A')],'Insurance',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'excise_duty': fields.selection([('inclusive','Inclusive'),('extra','Extra'),('nil','Nil')],'Excise Duty',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'division': fields.selection([('ppd','PPD'),('ipd','IPD'),('foundry','Foundry')],'Division',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'revision': fields.integer('Revision',readonly=True),
		'mode_of_dispatch': fields.many2one('kg.dispatch.master','Mode of Dispatch',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'item_quality_term': fields.many2one('kg.item.quality.master','Item Quality Term',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)]}),
		'item_quality_term_id': fields.many2many('kg.item.quality.master','general_term','po_id','term_id','Item Quality Term',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)],'cancel':[('readonly',True)]}),
		'sent_mail_flag': fields.boolean('Sent Mail Flag'),
		'adv_flag': fields.boolean('Advance Flag'),
		'advance_amt': fields.float('Advance(%)',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)]}),
		
		## Child Tables Declaration
		
		'expense_line_id': fields.one2many('kg.purchase.order.expense.track','expense_id','Expense Track',readonly=False, states={'approved':[('readonly',True)],'done':[('readonly',True)]}),
		
		# Entry Info
		
		'active': fields.boolean('Active'),
		'creation_date':fields.datetime('Created Date',readonly=True),
		'user_id': fields.many2one('res.users', 'Created by',readonly=True),
		'confirmed_by':fields.many2one('res.users','Confirmed By',readonly=True),
		'confirmed_date':fields.datetime('Confirmed Date',readonly=True),
		'cancel_date': fields.datetime('Cancelled Date', readonly=True),
		'cancel_user_id': fields.many2one('res.users', 'Cancelled By', readonly=True),
		'verified_by':fields.many2one('res.users','Verified By',readonly=True),
		'verified_date':fields.datetime('Verified Date',readonly=True),
		'approved_by':fields.many2one('res.users','Approved By',readonly=True),
		'approved_date':fields.datetime('Approved Date',readonly=True),
		'reject_date': fields.datetime('Rejected Date', readonly=True),
		'rej_user_id': fields.many2one('res.users', 'Rejected By', readonly=True),
		'update_date' : fields.datetime('Last Updated Date',readonly=True),
		'update_user_id' : fields.many2one('res.users','Last Updated By',readonly=True),
		
	}
	
	_defaults = {
		
		'bill_type': 'credit',
		'date_order': lambda * a: time.strftime('%Y-%m-%d'),
		'po_type': 'direct',
		'name': lambda self, cr, uid, c: self.pool.get('purchase.order').browse(cr, uid, id, c).id,
		'user_id': lambda self, cr, uid, c: self.pool.get('res.users').browse(cr, uid, uid, c).id,
		'creation_date': lambda * a: time.strftime('%Y-%m-%d %H:%M:%S'),
		'frieght_flag': False,
		'version': '00',
		'pricelist_id': 2,
		'type_flag': False,
		'insurance': 'na',
		'sent_mail_flag': False,
		'adv_flag': False,
		'active': True,
		
	}
	
	def create(self, cr, uid, vals,context=None):
		order =  super(kg_purchase_order, self).create(cr, uid, vals, context=context)
		return order
	
	def onchange_type_flag(self, cr, uid, ids, po_type):
		value = {'type_flag':False,'po_flag':True}
		if po_type == 'direct':
			value = {'type_flag': True,'pi_flag': False,'po_flag': False}
		else:
			value = {'pi_flag': True,'type_flag': False,'po_flag': False}
		if po_type == 'frompi':
			value = {'po_flag': False,'type_flag':False,'pi_flag': True}
		print"valuevaluevalue",value
		return {'value': value}
	
	def onchange_company(self, cr, uid, ids, company_id,delivery_address):
		value = {'delivery_address':''}
		com_obj = self.pool.get('res.company').search(cr,uid,([('id','=',company_id)]))
		com_rec = self.pool.get('res.company').browse(cr,uid,com_obj[0])
		part_obj = self.pool.get('res.partner').search(cr,uid,([('id','=',com_rec.partner_id.id)]))
		part_rec = self.pool.get('res.company').browse(cr,uid,part_obj[0])
		address = part_rec.street or ' '+''+ part_rec.street2 or ' '+''+part_rec.city or ' '+','+part_rec.state_id.name or ' '+','+part_rec.country_id.name or ' '+','+part_rec.zip or ' '
		value = {'delivery_address': address}
		return {'value': value}	
	
	def onchange_frieght_flag(self, cr, uid, ids, term_freight):
		value = {'frieght_flag':False}
		if term_freight == 'Extra':
			value = {'frieght_flag': True}
		return {'value': value}
	
	def onchange_partner_id(self, cr, uid, ids, partner_id,add_text):
		logger.info('[KG OpenERP] Class: kg_purchase_order, Method: onchange_partner_id called...')
		partner = self.pool.get('res.partner')
		if not partner_id:
			return {'value': {
				'fiscal_position': False,
				'payment_term_id': False,
				}}
		supplier_address = partner.address_get(cr, uid, [partner_id], ['default'])
		supplier = partner.browse(cr, uid, partner_id)
		tot_add = (supplier.street or '')+ ' ' + (supplier.street2 or '') + '\n'+(supplier.city_id.name or '')+ ',' +(supplier.state_id.name or '') + '-' +(supplier.zip or '') + '\nPh:' + (supplier.phone or '')+ '\n' +(supplier.mobile or '')		
		return {'value': {
			'pricelist_id': supplier.property_product_pricelist_purchase.id,
			'fiscal_position': supplier.property_account_position and supplier.property_account_position.id or False,
			'payment_term_id': supplier.property_supplier_payment_term.id or False,
			'add_text' : tot_add or False
			}}
	
	def confirm_po(self,cr,uid,ids, context=None):
		obj = self.browse(cr,uid,ids[0])
		if obj.state == 'draft':
			if not obj.name:
				if obj.division == 'ipd':
					seq_id = self.pool.get('ir.sequence').search(cr,uid,[('code','=','purchase.order')])
					seq_rec = self.pool.get('ir.sequence').browse(cr,uid,seq_id[0])
					cr.execute("""select generatesequenceno(%s,'%s','%s') """%(seq_id[0],seq_rec.code,obj.date_order))
				elif obj.division == 'ppd':
					seq_id = self.pool.get('ir.sequence').search(cr,uid,[('code','=','ppd.purchase.order')])
					seq_rec = self.pool.get('ir.sequence').browse(cr,uid,seq_id[0])
					cr.execute("""select generatesequenceno(%s,'%s','%s') """%(seq_id[0],seq_rec.code,obj.date_order))
				elif obj.division == 'foundry':
					seq_id = self.pool.get('ir.sequence').search(cr,uid,[('code','=','fou.purchase.order')])
					seq_rec = self.pool.get('ir.sequence').browse(cr,uid,seq_id[0])
					cr.execute("""select generatesequenceno(%s,'%s','%s') """%(seq_id[0],seq_rec.code,obj.date_order))
				seq_name = cr.fetchone();
				self.write(cr,uid,ids,{'name':seq_name[0]})
			back_list = []
			approval = ''
			for item in obj.order_line:
				prod_obj = self.pool.get('kg.brandmoc.rate').search(cr,uid,[('product_id','=',item.product_id.id),('state','=','approved')])
				if not prod_obj:
					raise osv.except_osv(_('Warning!'),_('Kindly check and approve %s in Brand/Moc/Rate master !'%(item.product_id.name)))
				price_sql = """ 
							select line.price_unit 
							from purchase_order_line line 
							left join purchase_order po on (po.id=line.order_id)
							join kg_brandmoc_rate rate on (rate.product_id=line.product_id)
							join ch_brandmoc_rate_details det on (det.header_id=rate.id)
							where po.state = 'approved' and rate.state in ('approved')
							and line.product_id = %s and line.order_id != %s and line.brand_id = %s 
							and line.moc_id = %s 
							order by po.approved_date desc limit 1
							"""%(item.product_id.id,obj.id,item.brand_id.id,item.moc_id.id)
				cr.execute(price_sql)		
				price_data = cr.dictfetchall()
				if price_data:
					if price_data[0]['price_unit'] < item.price_unit:
						self.write(cr,uid,ids,{'approval_flag':True})
						approval = 'yes'
						self.pool.get('purchase.order.line').write(cr,uid,item.id,{'approval_flag':True})
				else:
					# When raised the first po for the product
					price_sql = """ 
							select line.price_unit 
							from purchase_order_line line 
							left join purchase_order po on (po.id=line.order_id)
							join kg_brandmoc_rate rate on (rate.product_id=line.product_id)
							join ch_brandmoc_rate_details det on (det.header_id=rate.id)
							where po.state = 'approved' and rate.state in ('approved')
							and line.product_id = %s and line.order_id != %s and line.brand_id = %s 
							and line.moc_id = %s 
							order by po.approved_date desc limit 1
							"""%(item.product_id.id,obj.id,item.brand_id.id,item.moc_id.id)
					cr.execute(price_sql)		
					price_data = cr.dictfetchall()
					if not price_data:
						approval = 'yes'
						self.pool.get('purchase.order.line').write(cr,uid,item.id,{'approval_flag':True})
					
					# Po price exceeds design rate process
					prod_obj = self.pool.get('kg.brandmoc.rate').search(cr,uid,[('product_id','=',item.product_id.id),('state','=','approved')])
					if prod_obj:
						prod_rec = self.pool.get('kg.brandmoc.rate').browse(cr,uid,prod_obj[0])
						for ele in prod_rec.line_ids:
							if item.brand_id.id == ele.brand_id.id and item.moc_id.id == ele.moc_id.id:
								if ele.rate < item.price_unit:
									self.write(cr,uid,ids,{'approval_flag':True})
									approval = 'yes'
									self.pool.get('purchase.order.line').write(cr,uid,item.id,{'approval_flag':True})
					else:
						raise osv.except_osv(_('Warning!'),_('Kindly check and approve %s in Brand/Moc/Rate master !'%(item.product_id.name)))
				if item.price_type == 'per_kg':
					if item.product_id.uom_conversation_factor == 'two_dimension':
						if item.product_id.po_uom_in_kgs > 0:
							qty = item.product_qty * item.product_id.po_uom_in_kgs * item.length * item.breadth
					elif item.product_id.uom_conversation_factor == 'one_dimension':
						if item.product_id.po_uom_in_kgs > 0:
							qty = item.product_qty * item.product_id.po_uom_in_kgs
						else:
							qty = item.product_qty
					else:
						qty = item.product_qty
				else:
					qty = item.product_qty
				
				self.pool.get('purchase.order.line').write(cr,uid,item.id,{'quantity':qty})
			print"obj.approval_flagobj.approval_flag",obj.approval_flag
			print"approvalapprovalapprovalapproval",approval
			
			date_order = obj.date_order
			date_order1 = datetime.strptime(date_order, '%Y-%m-%d')
			date_order1 = datetime.date(date_order1)
			today_date = datetime.date(today)
			today_new = today.date()
			bk_date = date.today() - timedelta(days=2)
			back_date = bk_date.strftime('%Y-%m-%d')
			d1 = today_new
			d2 = bk_date
			delta = d1 - d2
			for i in range(delta.days + 1):
				bkk_date = d1 - timedelta(days=i)
				backk_date = bkk_date.strftime('%Y-%m-%d')
				back_list.append(backk_date)
			sql = """ select id,name,date_order from purchase_order where state != 'draft' and state != 'cancel 'order by id desc limit 1 """
			cr.execute(sql)
			data = cr.dictfetchall()
			#~ if obj.amount_total <= 0:
				#~ raise osv.except_osv(
						#~ _('Purchase Order Value Error !'),_('System not allow to confirm a Purchase Order with Zero Value'))	
			po_lines = obj.order_line
			cr.execute("""select piline_id from kg_poindent_po_line where po_order_id = %s"""  %(str(ids[0])))
			data = cr.dictfetchall()
			val = [d['piline_id'] for d in data if 'piline_id' in d] # Get a values form list of dict if the dict have with empty values
			for i in range(len(po_lines)):
				po_qty=po_lines[i].product_qty
				if po_lines[i].line_id:
					total = sum(wo.qty for wo in po_lines[i].line_id)
					if total <= po_qty:
						pass
					else:
						raise osv.except_osv(_('Warning!'),_('Please Check WO Qty'))
					
					wo_sql = """ select count(wo_id) as wo_tot,wo_id as wo_name from ch_purchase_wo where header_id = %s group by wo_id"""%(po_lines[i].id)
					cr.execute(wo_sql)		
					wo_data = cr.dictfetchall()
					
					for wo in wo_data:
						if wo['wo_tot'] > 1:
							raise osv.except_osv(_('Warning!'),_('%s This WO No. repeated'%(wo['wo_name'])))
						else:
							pass
			
			for order_line in obj.order_line:
				product_tax_amt = self._amount_line_tax(cr, uid, order_line, context=context)			
				cr.execute("""update purchase_order_line set product_tax_amt = %s where id = %s"""%(product_tax_amt,order_line.id))
			if approval == 'yes' and obj.sent_mail_flag == False:
				self.spl_po_apl_mail(cr,uid,ids,obj,context)
				self.write(cr,uid,ids,{'sent_mail_flag':True,'approval_flag':True,'state':'confirmed','confirmed_by':uid,'confirmed_date':dt_time})
			if approval != 'yes':
				self.write(cr,uid,ids,{'state':'verified','confirmed_by':uid,'confirmed_date':dt_time,'approval_flag':False})
		return True
	
	def verify_po(self,cr,uid,ids, context=None):
		obj = self.browse(cr,uid,ids[0])
		if obj.state == 'confirmed':
			user_obj = self.pool.get('res.users').search(cr,uid,[('id','=',uid)])
			user_rec = self.pool.get('res.users').browse(cr,uid,user_obj[0])
			if user_rec.special_approval == True:
				pass
			else:
				if obj.confirmed_by.id == uid:
					raise osv.except_osv(_('Warning'),_('Verify cannot be done by Confirmed user'))
			self.write(cr,uid,ids,{'state':'verified','verified_by':uid,'verified_date':dt_time,'approval_flag':True,'sent_mail_flag':False})
		
		return True
	
	def entry_approve(self, cr, uid, ids, context=None):
		obj = self.browse(cr, uid, ids[0], context=context)
		user_obj = self.pool.get('res.users').search(cr,uid,[('id','=',uid)])
		user_rec = self.pool.get('res.users').browse(cr,uid,user_obj[0])
		if user_rec.special_approval == True:
			pass
		else:
			if obj.confirmed_by.id == uid:
				raise osv.except_osv(_('Warning'),_('Approve cannot be done by Confirmed user'))
			elif obj.verified_by.id == uid:
				raise osv.except_osv(_('Warning'),_('Approve cannot be done by Verified user'))
			else:
				pass
		
		for item in obj.order_line:
			price_sql = """ 
						select line.price_unit
						from purchase_order_line line
						left join purchase_order po on (po.id = line.order_id)
						where line.product_id = %s and line.order_id != %s and line.brand_id = %s and line.moc_id = %s
						and po.state in ('approved')
						order by po.approved_date desc limit 1"""%(item.product_id.id,obj.id,item.brand_id.id,item.moc_id.id)
			cr.execute(price_sql)
			price_data = cr.dictfetchall()
			if price_data:
				if price_data[0]['price_unit'] < item.price_unit:
					if user_rec.special_approval == True:
						pass
					else:
						raise osv.except_osv(_('Warning'),
							_('%s price is exceeding last purchase price. It should be approved by special approver'%(item.product_id.name)))
			else:
				# When raised the first po for the product
				price_sql = """ 
						select line.price_unit
						from purchase_order_line line
						left join purchase_order po on (po.id=line.order_id)
						join kg_brandmoc_rate rate on (rate.product_id=line.product_id)
						join ch_brandmoc_rate_details det on (det.header_id=rate.id)
						where po.state = 'approved' and rate.state in ('approved')
						and line.product_id = %s and line.order_id != %s and line.brand_id = %s
						and line.moc_id = %s
						order by po.approved_date desc limit 1
						"""%(item.product_id.id,obj.id,item.brand_id.id,item.moc_id.id)
				cr.execute(price_sql)		
				price_data = cr.dictfetchall()
				if not price_data:
					if user_rec.special_approval == True:
						pass
					else:
						raise osv.except_osv(_('Warning'),
							_('%s price is exceeding last purchase price. It should be approved by special approver'%(item.product_id.name)))
				# Po price exceeds design rate
				prod_obj = self.pool.get('kg.brandmoc.rate').search(cr,uid,[('product_id','=',item.product_id.id),('state','=','approved')])
				if prod_obj:
					prod_rec = self.pool.get('kg.brandmoc.rate').browse(cr,uid,prod_obj[0])
					for ele in prod_rec.line_ids:
						if item.brand_id.id == ele.brand_id.id and item.moc_id.id == ele.moc_id.id:
							latest_rate = 0
							if ele.rate < item.price_unit:
								if user_rec.special_approval == True:
									pass
								else:
									raise osv.except_osv(_('Warning'),
										_('%s price is exceeding design price. It should be approved by special approver'%(item.product_id.name)))
								#~ latest_rate = item.price_unit + ((item.price_unit/100) * 5)
								#~ self.pool.get('ch.brandmoc.rate.details').write(cr,uid,ele.id,{'rate':latest_rate})
				else:
					raise osv.except_osv(_('Warning!'),_('%s Please Check for this item in Brand/Moc/Rate master !'%(item.product_id.name)))	
			if item.price_type == 'per_kg':
				if item.product_id.uom_conversation_factor == 'two_dimension':
					if item.product_id.po_uom_in_kgs > 0:
						qty = item.product_qty * item.product_id.po_uom_in_kgs * item.length * item.breadth
				elif item.product_id.uom_conversation_factor == 'one_dimension':
					if item.product_id.po_uom_in_kgs > 0:
						qty = item.product_qty * item.product_id.po_uom_in_kgs
					else:
						qty = item.product_qty
				else:
					qty = item.product_qty
			else:
				qty = item.product_qty
			self.pool.get('purchase.order.line').write(cr,uid,item.id,{'quantity':qty})	
		
		#~ if obj.bill_type == 'advance':
			#~ self.advance_creation(cr,uid,obj)
		
		if obj.payment_mode.term_category == 'advance':
			cr.execute("""select * from kg_supplier_advance where state='confirmed' and po_id = %s"""  %(str(ids[0])))
			data = cr.dictfetchall()
			if not data:
				raise osv.except_osv(_('Warning'),_('Advance is mandate for this PO'))
			else:
				pass		
		text_amount = number_to_text_convert_india.amount_to_text_india(obj.amount_total,"INR:")
		self.write(cr,uid,ids[0],{'text_amt':text_amount})
		line_obj = self.pool.get('purchase.order.line')
		line_rec = line_obj.search(cr, uid, [('order_id','=',obj.id)])
		for order_line in line_rec:
			order_line_rec = line_obj.browse(cr, uid, order_line)
			product_tax_amt = self._amount_line_tax(cr, uid, order_line_rec, context=context)
			cr.execute("""update purchase_order_line set product_tax_amt = %s where id = %s"""%(product_tax_amt,order_line_rec.id))
		#~ for order_line in obj.order_line:
			#~ product_tax_amt = self._amount_line_stax(cr, uid, order_line, context=context)			
			#~ cr.execute("""update purchase_order_line set product_tax_amt = %s where id = %s"""%(product_tax_amt,order_line.id))
			line_obj.write(cr,uid,order_line,{'cancel_flag':'True','line_flag':'True'})
		
		self.write(cr, uid, ids, {
								  'state': 'approved', 
								  'date_approve': time.strftime('%Y-%m-%d'),
								  'order_line.line_state' : 'confirm',
								  'approved_by': uid,
								  'approved_date': dt_time})
		po_id=obj.id
		po_lines = obj.order_line
		cr.execute("""select piline_id from kg_poindent_po_line where po_order_id = %s"""  %(str(ids[0])))
		data = cr.dictfetchall()
		val = [d['piline_id'] for d in data if 'piline_id' in d] # Get a values form list of dict if the dict have with empty values
		for i in range(len(po_lines)):
			po_qty=po_lines[i].product_qty
			if po_lines[i].line_id:
				total = sum(wo.qty for wo in po_lines[i].line_id)
				if total <= po_qty:
					pass
				else:
					raise osv.except_osv(_('Warning!'),_('Please Check WO Qty'))
				wo_sql = """ select count(wo_id) as wo_tot,wo_id as wo_name from ch_purchase_wo where header_id = %s group by wo_id"""%(po_lines[i].id)
				cr.execute(wo_sql)		
				wo_data = cr.dictfetchall()
				
				for wo in wo_data:
					if wo['wo_tot'] > 1:
						raise osv.except_osv(_('Warning!'),_('%s This WO No. repeated'%(wo['wo_name'])))
					else:
						pass
			if obj.po_type == 'frompi':
				if po_lines[i].pi_line_id and po_lines[i].group_flag == False:
					pi_line_id=po_lines[i].pi_line_id
					product = po_lines[i].product_id.name
					po_qty=po_lines[i].product_qty
					po_pending_qty=po_lines[i].pi_qty
					pi_pending_qty= po_pending_qty - po_qty
					if po_qty > po_pending_qty:
						raise osv.except_osv(_('If PO from Purchase Indent'),
							_('PO Qty should not be greater than purchase indent Qty. You can raise this PO Qty upto %s --FOR-- %s.'
									%(po_pending_qty, product)))
					
					pi_obj=self.pool.get('purchase.requisition.line')
					pi_line_obj=pi_obj.search(cr, uid, [('id','=',val[i])])
					pi_obj.write(cr,uid,pi_line_id.id,{'draft_flag' : False})
					sql = """ update purchase_requisition_line set pending_qty=%s where id = %s"""%(pi_pending_qty,pi_line_id.id)
					cr.execute(sql)
					
					if pi_pending_qty == 0:
						pi_obj.write(cr,uid,pi_line_id.id,{'line_state' : 'noprocess'})
					
					if po_lines[i].group_flag == True:
							self.update_product_pending_qty(cr,uid,ids,line=po_lines[i])
					else:
						print "All are correct Values and working fine"
			else:
				line_obj.write(cr,uid,po_lines[i].id,{'pending_qty':po_lines[i].product_qty})
			
			prod_obj = self.pool.get('product.product')
			prod_obj.write(cr,uid,po_lines[i].product_id.id,{'latest_price' : po_lines[i].price_unit})
			
			bmr_obj = self.pool.get('kg.brandmoc.rate').search(cr,uid,[('product_id','=',po_lines[i].product_id.id),('state','=','approved')])
			if bmr_obj:
				bmr_rec = self.pool.get('kg.brandmoc.rate').browse(cr,uid,bmr_obj[0])
				for item in bmr_rec.line_ids:
					if item.brand_id.id == po_lines[i].brand_id.id and item.moc_id.id == po_lines[i].moc_id.id and po_lines[i].rate_revise == 'yes':
						self.pool.get('ch.brandmoc.rate.details').write(cr,uid,item.id,{'purchase_price' : po_lines[i].price_unit})
						
						## Design Rate update process start
						
						design_rate = 0
						if item.rate <= po_lines[i].price_unit:
							design_rate = ((po_lines[i].price_unit/100.00) * 5) + po_lines[i].price_unit
							self.pool.get('ch.brandmoc.rate.details').write(cr,uid,item.id,{'rate' : design_rate})
						elif (item.rate - ((item.rate/100.00) * 5)) >= po_lines[i].price_unit:
							design_rate = ((po_lines[i].price_unit/100.00)*5) + po_lines[i].price_unit
							self.pool.get('ch.brandmoc.rate.details').write(cr,uid,item.id,{'rate' : design_rate})
						else:
							pass
						## Design Rate update process end
					else:
						pass
		#~ self.approved_po_mail(cr,uid,ids,obj,context)
		return True
	
	def wkf_approve_order(self, cr, uid, ids, context=None):
		logger.info('[KG OpenERP] Class: kg_purchase_order, Method: wkf_approve_order called...')
		obj = self.browse(cr,uid,ids[0])
		if obj.state == 'confirmed':
			if obj.confirmed_by.id == uid:
				raise osv.except_osv(_('Warning'),_('Approve cannot be done by Confirmed user'))
			elif obj.verified_by.id == uid:
				raise osv.except_osv(_('Warning'),_('Approve cannot be done by Verified user'))
			else:
				pass
			user_obj = self.pool.get('res.users').search(cr,uid,[('id','=',uid)])
			if user_obj:
				user_rec = self.pool.get('res.users').browse(cr,uid,user_obj[0])
			for item in obj.order_line:
				price_sql = """ 
							select line.price_unit
							from purchase_order_line line
							left join purchase_order po on (po.id = line.order_id)
							where line.product_id = %s and line.order_id != %s and line.brand_id = %s and line.moc_id = %s
							and po.state in ('approved')
							order by po.approved_date desc limit 1"""%(item.product_id.id,obj.id,item.brand_id.id,item.moc_id.id)
				cr.execute(price_sql)
				price_data = cr.dictfetchall()
				if price_data:
					if price_data[0]['price_unit'] < item.price_unit:
						if user_rec.special_approval == True:
							pass
						else:
							raise osv.except_osv(_('Warning'),
								_('%s price is exceeding last purchase price. It should be approved by special approver'%(item.product_id.name)))
				else:
					# When raised the first po for the product
					price_sql = """ 
							select line.price_unit
							from purchase_order_line line
							left join purchase_order po on (po.id=line.order_id)
							join kg_brandmoc_rate rate on (rate.product_id=line.product_id)
							join ch_brandmoc_rate_details det on (det.header_id=rate.id)
							where po.state = 'approved' and rate.state in ('approved')
							and line.product_id = %s and line.order_id != %s and line.brand_id = %s
							and line.moc_id = %s
							order by po.approved_date desc limit 1
							"""%(item.product_id.id,obj.id,item.brand_id.id,item.moc_id.id)
					cr.execute(price_sql)		
					price_data = cr.dictfetchall()
					if not price_data:
						if user_rec.special_approval == True:
							pass
						else:
							raise osv.except_osv(_('Warning'),
								_('%s price is exceeding last purchase price. It should be approved by special approver'%(item.product_id.name)))
					# Po price exceeds design rate
					prod_obj = self.pool.get('kg.brandmoc.rate').search(cr,uid,[('product_id','=',item.product_id.id),('state','=','approved')])
					if prod_obj:
						prod_rec = self.pool.get('kg.brandmoc.rate').browse(cr,uid,prod_obj[0])
						for ele in prod_rec.line_ids:
							if item.brand_id.id == ele.brand_id.id and item.moc_id.id == ele.moc_id.id:
								latest_rate = 0
								if ele.rate < item.price_unit:
									if user_rec.special_approval == True:
										pass
									else:
										raise osv.except_osv(_('Warning'),
											_('%s price is exceeding design price. It should be approved by special approver'%(item.product_id.name)))
									#~ latest_rate = item.price_unit + ((item.price_unit/100) * 5)
									#~ self.pool.get('ch.brandmoc.rate.details').write(cr,uid,ele.id,{'rate':latest_rate})
					else:
						raise osv.except_osv(_('Warning!'),_('%s Please Check for this item in Brand/Moc/Rate master !'%(item.product_id.name)))	
				if item.price_type == 'per_kg':
					if item.product_id.uom_conversation_factor == 'two_dimension':
						if item.product_id.po_uom_in_kgs > 0:
							qty = item.product_qty * item.product_id.po_uom_in_kgs * item.length * item.breadth
					elif item.product_id.uom_conversation_factor == 'one_dimension':
						if item.product_id.po_uom_in_kgs > 0:
							qty = item.product_qty * item.product_id.po_uom_in_kgs
						else:
							qty = item.product_qty
					else:
						qty = item.product_qty
				else:
					qty = item.product_qty
				self.pool.get('purchase.order.line').write(cr,uid,item.id,{'quantity':qty})	
			
			#~ if obj.bill_type == 'advance':
				#~ self.advance_creation(cr,uid,obj)
			
			if obj.payment_mode.term_category == 'advance':
				cr.execute("""select * from kg_supplier_advance where state='confirmed' and po_id = %s"""  %(str(ids[0])))
				data = cr.dictfetchall()
				if not data:
					raise osv.except_osv(_('Warning'),_('Advance is mandate for this PO'))
				else:
					pass		
			text_amount = number_to_text_convert_india.amount_to_text_india(obj.amount_total,"INR:")
			self.write(cr,uid,ids[0],{'text_amt':text_amount})
			line_obj = self.pool.get('purchase.order.line')
			line_rec = line_obj.search(cr, uid, [('order_id','=',obj.id)])
			for order_line in line_rec:
				order_line_rec = line_obj.browse(cr, uid, order_line)
				product_tax_amt = self._amount_line_tax(cr, uid, order_line_rec, context=context)
				cr.execute("""update purchase_order_line set product_tax_amt = %s where id = %s"""%(product_tax_amt,order_line_rec.id))
			#~ for order_line in obj.order_line:
				#~ product_tax_amt = self._amount_line_stax(cr, uid, order_line, context=context)			
				#~ cr.execute("""update purchase_order_line set product_tax_amt = %s where id = %s"""%(product_tax_amt,order_line.id))
				line_obj.write(cr,uid,order_line,{'cancel_flag':'True','line_flag':'True'})
			
			self.write(cr, uid, ids, {
									  'state': 'approved', 
									  'date_approve': time.strftime('%Y-%m-%d'),
									  'order_line.line_state' : 'confirm',
									  'approved_by': uid,
									  'approved_date': dt_time})
			
			po_id=obj.id
			po_lines = obj.order_line
			cr.execute("""select piline_id from kg_poindent_po_line where po_order_id = %s"""  %(str(ids[0])))
			data = cr.dictfetchall()
			val = [d['piline_id'] for d in data if 'piline_id' in d] # Get a values form list of dict if the dict have with empty values
			for i in range(len(po_lines)):
				po_qty=po_lines[i].product_qty
				if po_lines[i].line_id:
					total = sum(wo.qty for wo in po_lines[i].line_id)
					if total <= po_qty:
						pass
					else:
						raise osv.except_osv(_('Warning!'),_('Please Check WO Qty'))
					wo_sql = """ select count(wo_id) as wo_tot,wo_id as wo_name from ch_purchase_wo where header_id = %s group by wo_id"""%(po_lines[i].id)
					cr.execute(wo_sql)		
					wo_data = cr.dictfetchall()
					
					for wo in wo_data:
						if wo['wo_tot'] > 1:
							raise osv.except_osv(_('Warning!'),_('%s This WO No. repeated'%(wo['wo_name'])))
						else:
							pass
				if obj.po_type == 'frompi':
					if po_lines[i].pi_line_id and po_lines[i].group_flag == False:
						pi_line_id=po_lines[i].pi_line_id
						product = po_lines[i].product_id.name
						po_qty=po_lines[i].product_qty
						po_pending_qty=po_lines[i].pi_qty
						pi_pending_qty= po_pending_qty - po_qty
						if po_qty > po_pending_qty:
							raise osv.except_osv(_('If PO from Purchase Indent'),
								_('PO Qty should not be greater than purchase indent Qty. You can raise this PO Qty upto %s --FOR-- %s.'
										%(po_pending_qty, product)))
						
						pi_obj=self.pool.get('purchase.requisition.line')
						pi_line_obj=pi_obj.search(cr, uid, [('id','=',val[i])])
						pi_obj.write(cr,uid,pi_line_id.id,{'draft_flag' : False})
						sql = """ update purchase_requisition_line set pending_qty=%s where id = %s"""%(pi_pending_qty,pi_line_id.id)
						cr.execute(sql)
						
						if pi_pending_qty == 0:
							pi_obj.write(cr,uid,pi_line_id.id,{'line_state' : 'noprocess'})
						
						if po_lines[i].group_flag == True:
								self.update_product_pending_qty(cr,uid,ids,line=po_lines[i])
						else:
							print "All are correct Values and working fine"
				else:
					line_obj.write(cr,uid,po_lines[i].id,{'pending_qty':po_lines[i].product_qty})
				
				prod_obj = self.pool.get('product.product')
				prod_obj.write(cr,uid,po_lines[i].product_id.id,{'latest_price' : po_lines[i].price_unit})
				
				bmr_obj = self.pool.get('kg.brandmoc.rate').search(cr,uid,[('product_id','=',po_lines[i].product_id.id),('state','=','approved')])
				if bmr_obj:
					bmr_rec = self.pool.get('kg.brandmoc.rate').browse(cr,uid,bmr_obj[0])
					for item in bmr_rec.line_ids:
						if item.brand_id.id == po_lines[i].brand_id.id and item.moc_id.id == po_lines[i].moc_id.id and po_lines[i].rate_revise == 'yes':
							self.pool.get('ch.brandmoc.rate.details').write(cr,uid,item.id,{'purchase_price' : po_lines[i].price_unit})
							
							## Design Rate update process start
							
							design_rate = 0
							if item.rate <= po_lines[i].price_unit:
								design_rate = ((po_lines[i].price_unit/100.00) * 5) + po_lines[i].price_unit
								self.pool.get('ch.brandmoc.rate.details').write(cr,uid,item.id,{'rate' : design_rate})
							elif (item.rate - ((item.rate/100.00) * 5)) >= po_lines[i].price_unit:
								design_rate = ((po_lines[i].price_unit/100.00)*5) + po_lines[i].price_unit
								self.pool.get('ch.brandmoc.rate.details').write(cr,uid,item.id,{'rate' : design_rate})
							else:
								pass
							## Design Rate update process end
						else:
							pass
	
	def advance_creation(self,cr,uid,obj,context=None):
		
		advance_amt = (obj.amount_total / 100.00) * obj.advance_amt
		print"advance_amt",advance_amt
		sup_adv_id = self.pool.get('kg.supplier.advance').create(cr,uid,{'supplier_id': obj.partner_id.id,
															'order_category': 'purchase',
															'po_id': obj.id,
															'advance_amt': advance_amt,
															'order_value': obj.amount_total,
															'order_no': obj.name,
															'entry_mode': 'auto',
															})
		sup_ids = self.pool.get('kg.supplier.advance').search(cr,uid,[('supplier_id','=',obj.partner_id.id),('state','=','confirmed')])		
		if sup_ids:
			for ele in sup_ids:
				adv_rec = self.pool.get('kg.supplier.advance').browse(cr,uid,ele)
				self.pool.get('ch.advance.line').create(cr,uid,{'header_id': sup_adv_id,
															   'advance_no':adv_rec.name,
															   'advance_date':adv_rec.entry_date,
															   'order_no':adv_rec.order_no,
															   'advance_amt':adv_rec.advance_amt,
															   'adjusted_amt':adv_rec.adjusted_amt,
															   'balance_amt':adv_rec.balance_amt,
																})
		return True
	
	def spl_po_apl_mail(self,cr,uid,ids,obj,context=None):
		cr.execute("""select trans_po_spl_approval('po spl approval',"""+str(obj.id)+""")""")
		data = cr.fetchall();
		if data[0][0] is None:
			return False
		if data[0][0] is not None:	
			maildet = (str(data[0])).rsplit('~');
			cont = data[0][0].partition('UNWANTED.')		
			email_from = maildet[1]	
			if maildet[2]:	
				email_to = [maildet[2]]
			else:
				email_to = ['']			
			if maildet[3]:
				email_cc = [maildet[3]]	
			else:
				email_cc = ['']		
			ir_mail_server = self.pool.get('ir.mail_server')
			if maildet[4] != '':
				msg = ir_mail_server.build_email(
					email_from = email_from,
					email_to = email_to,
					subject = maildet[4],
					body = cont[0],
					email_cc = email_cc,
					object_id = ids and ('%s-%s' % (ids, 'kg.mail.settings')),
					subtype = 'html',
					subtype_alternative = 'plain')
				res = ir_mail_server.send_email(cr, uid, msg,mail_server_id=1, context=context)
			else:
				pass
		
		return True
	
	def approved_po_mail(self,cr,uid,ids,obj,context=None):
		cr.execute("""select trans_po_approved('approved po',"""+str(obj.id)+""")""")
		data = cr.fetchall();
		if data[0][0] is None:
			return False
		if data[0][0] is not None:	
			maildet = (str(data[0])).rsplit('~');
			cont = data[0][0].partition('UNWANTED.')		
			email_from = maildet[1]	
			if maildet[2]:	
				email_to = [maildet[2]]
			else:
				email_to = ['']			
			if maildet[3]:
				email_cc = [maildet[3]]	
			else:
				email_cc = ['']		
			ir_mail_server = self.pool.get('ir.mail_server')
			if maildet[4] != '':
				msg = ir_mail_server.build_email(
					email_from = email_from,
					email_to = email_to,
					subject = maildet[4],
					body = cont[0],
					email_cc = email_cc,
					object_id = ids and ('%s-%s' % (ids, 'kg.mail.settings')),
					subtype = 'html',
					subtype_alternative = 'plain')
				res = ir_mail_server.send_email(cr, uid, msg,mail_server_id=1, context=context)
			else:
				pass
		
		return True
	
	def poindent_line_move(self, cr, uid,ids, poindent_lines , context=None):
		logger.info('[KG OpenERP] Class: kg_purchase_order, Method: poindent_line_move called...')
		return {}
	
	def _create_pickings(self, cr, uid, order, order_lines, picking_id=False, context=None):
		logger.info('[KG OpenERP] Class: kg_purchase_order, Method: _create_pickings called...')
		return {}
		# Default Openerp workflow stopped and inherited the function
	
	def action_cancel(self, cr, uid, ids, context=None):
		logger.info('[KG OpenERP] Class: kg_purchase_order, Method: action_cancel called...')
		wf_service = netsvc.LocalService("workflow")
		purchase = self.browse(cr, uid, ids[0], context=context)
		if purchase.state == 'approved':
			product_obj = self.pool.get('product.product')
			pi_line_obj = self.pool.get('purchase.requisition.line')
			po_grn_obj = self.pool.get('kg.po.grn')
			if not purchase.can_remark:
				raise osv.except_osv(_('Remarks Needed !!'),_('Enter Remark in Remarks Tab....'))
			
			if purchase.po_type == 'frompi':
				if purchase.state in ('draft','confirmed','verified'):
					for line in purchase.order_line:
						sql = """ update purchase_requisition_line set draft_flag=False where line_state = 'process' and id = %s """%(line.pi_line_id.id)
						cr.execute(sql)
					self.write(cr,uid,ids,{'state':'cancel','cancel_user_id': uid,'cancel_date':time.strftime('%Y-%m-%d %H:%M:%S')})
				elif purchase.state == 'approved': 
					cr.execute(""" select grn_id from multiple_po where po_id = %s """ %(ids[0]))
					multi_po = cr.dictfetchall()
					if multi_po:
						for pick in multi_po:
							pick = po_grn_obj.browse(cr, uid, pick['grn_id'])
							if pick.state not in ('draft','cancel'):
								raise osv.except_osv(_('Unable to cancel this purchase order.'),
									_('First cancel all GRN related to this purchase order.'))
					for line in purchase.order_line:
						if line.pi_line_id and line.group_flag == False:
							pi_obj=self.pool.get('purchase.requisition.line')
							pi_line_obj=pi_obj.search(cr, uid, [('id','=',line.pi_line_id.id)])
							orig_pending_qty = line.pi_line_id.pending_qty
							po_qty = line.product_qty
							orig_pending_qty += po_qty
							sql = """ update purchase_requisition_line set line_state = 'process',pending_qty=%s where id = %s"""%(orig_pending_qty,line.pi_line_id.id)
							cr.execute(sql)
						else:
							if line.pi_line_id and line.group_flag == True:
								cr.execute(""" select piline_id from kg_poindent_po_line where po_order_id = %s """ %(str(ids[0])))
								data = cr.dictfetchall()
								val = [d['piline_id'] for d in data if 'piline_id' in d] 
								product_id = line.product_id.id
								product_record = product_obj.browse(cr, uid, product_id)
								list_line = pi_line_obj.search(cr,uid,[('id', 'in', val), ('product_id', '=', product_id)],context=context)
								po_used_qty = line.product_qty
								orig_pi_qty = line.group_qty
								for i in list_line:
									bro_record = pi_line_obj.browse(cr, uid,i)
									pi_pen_qty = bro_record.pending_qty
									pi_qty = orig_pi_qty + pi_pen_qty
									orig_pi_qty +=pi_pen_qty
									po_qty = po_used_qty
									if po_qty < pi_qty:
										pi_qty = pi_pen_qty + po_qty
										sql = """ update purchase_requisition_line set line_state = 'process',pending_qty=%s where id = %s"""%(pi_qty,bro_record.id)
										cr.execute(sql)
										break		
									else:
										remain_qty = po_used_qty - orig_pi_qty
										sql = """ update purchase_requisition_line set line_state = 'process',pending_qty=%s where id = %s"""%(orig_pi_qty,bro_record.id)
										cr.execute(sql)
										if remain_qty < 0:
											break
										po_used_qty = remain_qty
										orig_pi_qty = pi_pen_qty + remain_qty
					self.write(cr,uid,ids,{'state':'cancel','cancel_user_id': uid,'cancel_date':time.strftime('%Y-%m-%d %H:%M:%S')})					
				else:
					for line in purchase.order_line:
						pi_line_obj.write(cr,uid,line.pi_line_id.id,{'line_state' : 'noprocess'})		
			else:
				self.write(cr,uid,ids,{'state': 'cancel','cancel_user_id': uid,'cancel_date': dt_time})
			
			for (id, name) in self.name_get(cr, uid, ids):
				wf_service.trg_validate(uid, 'purchase.order', id, 'purchase_cancel', cr)
		return True			
	
	def entry_reject(self, cr, uid, ids, context=None):
		rec = self.browse(cr, uid, ids[0], context=context)
		if rec.state in ('confirmed','verified'):
			pi_line_obj = self.pool.get('purchase.requisition.line')
			for line in rec.order_line:
				if line.pi_line_id.id:
					pi_line_obj.write(cr,uid,line.pi_line_id.id,{'line_state' : 'noprocess'})	
			if not rec.reject_remark:
				raise osv.except_osv(_('Remarks Needed !!'),_('Enter Remark in Reject Remarks'))
			else:
				if rec.approval_flag == True and rec.state == 'verified':
					if rec.confirmed_by.id == uid:
						raise osv.except_osv(_('Warning'),_('Reject cannot be done by Confirmed user'))
					if rec.verified_by.id == uid:
						raise osv.except_osv(_('Warning'),_('Reject cannot be done by Verified user'))
					self.write(cr,uid,ids,{'state': 'confirmed','rej_user_id': uid,'reject_date': dt_time})
				elif rec.approval_flag == True and rec.state == 'confirmed':
					if rec.confirmed_by.id == uid:
						raise osv.except_osv(_('Warning'),_('Reject cannot be done by Confirmed user'))
					self.write(cr,uid,ids,{'state': 'draft','rej_user_id': uid,'reject_date': dt_time})
				if rec.approval_flag != True:
					if rec.confirmed_by.id == uid:
						raise osv.except_osv(_('Warning'),_('Reject cannot be done by Confirmed user'))
					self.write(cr,uid,ids,{'state': 'draft','rej_user_id': uid,'reject_date': dt_time})
		return True
	
	def action_set_to_draft(self, cr, uid, ids, context=None):
		purchase = self.browse(cr, uid, ids[0], context=context)
		if purchase.state == 'reject':
			self.write(cr,uid,ids,{'state':'draft'})
		return True
	
	def write(self, cr, uid, ids, vals, context=None):		
		vals.update({'update_date': dt_time,'update_user_id': uid})
		return super(kg_purchase_order, self).write(cr, uid, ids, vals, context)
	
	def _check_line(self, cr, uid, ids, context=None):
		logger.info('[KG ERP] Class: kg_purchase_order, Method: _check_line called...')
		rec = self.browse(cr,uid,ids[0])
		if rec.po_type == 'direct':
			if not rec.order_line:
				raise osv.except_osv(_('Warning !'),_('System sholud not accecpt with out Order Item Details!'))
		if rec.po_type == 'frompi' and rec.state != 'draft': 
			if rec.kg_poindent_lines == []:
				tot = 0.0
				for line in rec.order_line:
					tot += line.price_subtotal
				if tot <= 0.0 or rec.amount_total <=0:		
					return False
		return True
	
	def _check_advance(self, cr, uid, ids, context=None):
		rec = self.browse(cr,uid,ids[0])
		if rec.bill_type == 'advance':
			if rec.advance_amt <= 0.00:
				raise osv.except_osv(_('Warning !'),_('System sholud not be accecpt with out Advance !'))
			elif rec.advance_amt > 100:
				raise osv.except_osv(_('Warning !'),_('System sholud not be greater than 100 !'))
			else:
				pass
		return True
	
	def _future_date(self, cr, uid, ids, context=None):
		rec = self.browse(cr,uid,ids[0])
		today_date = today.strftime('%Y-%m-%d')
		today_new = today.date()
		bk_date = date.today() - timedelta(days=2)
		back_date = bk_date.strftime('%Y-%m-%d')
		if rec.quotation_date:
			if rec.quotation_date <= back_date:
				raise osv.except_osv(_('Warning'),_('Quotation date should not be accept past date!'))
		return True
	
	_constraints = [
		
		(_check_line,'You can not save this Purchase Order with out Line and Zero Qty !',['order_line']),
		(_check_advance,'System sholud not be accecpt with out Advance !',['']),
		#~ (_future_date,'System sholud not be accecpt future date !',['']),
		
	]
	
kg_purchase_order()


class kg_purchase_order_line(osv.osv):
	
	def onchange_discount_value_calc(self, cr, uid, ids, kg_discount_per, product_qty, price_unit):
		logger.info('[KG OpenERP] Class: kg_purchase_order_line, Method: onchange_discount_value_calc called...')
		discount_value = (product_qty * price_unit) * kg_discount_per / 100.00
		if discount_value:
			return {'value': {'kg_discount_per_value': discount_value,'discount_flag':True }}
		else:
			return {'value': {'kg_discount_per_value': discount_value,'discount_flag':False }}
	
	def onchange_disc_amt(self,cr,uid,ids,kg_discount,product_qty,price_unit,kg_disc_amt_per):
		logger.info('[KG OpenERP] Class: kg_purchase_order_line, Method: onchange_disc_amt called...')
		if kg_discount:
			kg_discount = kg_discount + 0.00
			amt_to_per = (kg_discount / (product_qty * price_unit or 1.0 )) * 100.00
			return {'value': {'kg_disc_amt_per': amt_to_per,'discount_per_flag':True}}
		else:
			return {'value': {'kg_disc_amt_per': 0.0,'discount_per_flag':False}}	
	
	def _amount_line(self, cr, uid, ids, prop, arg, context=None):
		logger.info('[KG OpenERP] Class: kg_purchase_order_line, Method: _amount_line called...')
		cur_obj=self.pool.get('res.currency')
		tax_obj = self.pool.get('account.tax')
		res = {}
		if context is None:
			context = {}
		for line in self.browse(cr, uid, ids, context=context):
			# Qty Calculation
			qty = 0.00
			if line.price_type == 'per_kg':
				if line.product_id.uom_conversation_factor == 'two_dimension':
					if line.product_id.po_uom_in_kgs > 0:
						qty = line.product_qty * line.product_id.po_uom_in_kgs * line.length * line.breadth
				elif line.product_id.uom_conversation_factor == 'one_dimension':
					if line.product_id.po_uom_in_kgs > 0:
						qty = line.product_qty * line.product_id.po_uom_in_kgs
					else:
						qty = line.product_qty
				else:
					qty = line.product_qty
			else:
				qty = line.product_qty
			
			# Price Calculation
			price_amt = 0
			if line.price_type == 'per_kg':
				if line.product_id.po_uom_in_kgs > 0:
					price_amt = line.product_qty / line.product_id.po_uom_in_kgs * line.price_unit
			else:
				price_amt = qty * line.price_unit
			
			amt_to_per = (line.kg_discount / (qty * line.price_unit or 1.0 )) * 100
			kg_discount_per = line.kg_discount_per
			tot_discount_per = amt_to_per + kg_discount_per
			price = line.price_unit * (1 - (tot_discount_per or 0.0) / 100.0)
			taxes = tax_obj.compute_all(cr, uid, line.taxes_id, price, qty, line.product_id, line.order_id.partner_id)
			cur = line.order_id.pricelist_id.currency_id
			res[line.id] = cur_obj.round(cr, uid, cur, taxes['total_included'])
		return res
	
	_name = "purchase.order.line"
	_inherit = "purchase.order.line"
	
	_columns = {
		
		## Basic Info
		
		'name': fields.text('Description'),
		'cancel_remark':fields.text('Cancel Remarks'),
		
		## Module Requirement Fields
		
		'price_subtotal': fields.function(_amount_line, store=True,string='Subtotal', digits_compute= dp.get_precision('Account')),
		'kg_discount': fields.float('Discount Amount'),
		'discount_flag': fields.boolean('Discount Flag'),
		'kg_disc_amt_per': fields.float('Disc Amt(%)', digits_compute= dp.get_precision('Discount')),
		'price_unit': fields.float('Unit Price', required=True, digits_compute= dp.get_precision('Product Price')),
		'product_qty': fields.float('Quantity'),
		'pending_qty': fields.float('Pending Qty'),
		'received_qty':fields.float('Received Qty'),
		'tax_amt':fields.float('tax amt'),
		'cancel_qty':fields.float('Cancel Qty'),
		'pi_qty':fields.float('Indent Qty'),
		'group_qty':fields.float('Group Qty'),
		'product_uom': fields.many2one('product.uom', 'UOM', readonly=True),
		'date_planned': fields.date('Scheduled Date', select=True),
		'po_date': fields.related('order_id','date_order',type='date',string="PO Date",store=True),
		'note': fields.text('Remarks'),
		'pi_line_id':fields.many2one('purchase.requisition.line','PI Line'),
		'kg_discount_per': fields.float('Discount (%)', digits_compute= dp.get_precision('Discount')),
		'discount_per_flag': fields.boolean('Discount Amount Flag'),
		'kg_discount_per_value': fields.float('Discount(%)Value', digits_compute= dp.get_precision('Discount')),
		'line_state': fields.selection([('draft', 'Active'),('confirm','Confirmed'),('cancel', 'Cancel')], 'State'),
		'group_flag': fields.boolean('Group By'),
		'total_disc': fields.float('Discount Amt'),
		'line_bill': fields.boolean('PO Bill'),
		'cancel_flag':fields.boolean('Cancel Flag'),
		'move_line_id':fields.many2one('stock.move','Move Id'),
		'line_flag':fields.boolean('Line Flag'),
		'po_specification':fields.text('Specification'),
		'product_tax_amt':fields.float('Tax Amount'),
		'brand_id':fields.many2one('kg.brand.master','Brand',domain="[('product_ids','in',(product_id)),('state','in',('draft','confirmed','approved'))]"),
		'least_price': fields.float('Least Price'),
		'high_price': fields.float('Highest Price'),
		'recent_price': fields.float('Recent Price'),
		'price_type': fields.selection([('po_uom','PO UOM'),('per_kg','Per Kg')],'Price Type'),
		'moc_id': fields.many2one('kg.moc.master','MOC'),
		'moc_id_temp': fields.many2one('ch.brandmoc.rate.details','MOC',domain="[('brand_id','=',brand_id),('header_id.product_id','=',product_id),('header_id.state','in',('draft','confirmed','approved'))]"),
		'uom_conversation_factor': fields.related('product_id','uom_conversation_factor', type='selection',selection=UOM_CONVERSATION, string='UOM Conversation Factor',store=True,required=True),
		'length': fields.float('Length',digits=(16,4)),
		'breadth': fields.float('Breadth',digits=(16,4)),
		'quantity': fields.float("Qty/Weight(Kg's)"),
		'rate_revise': fields.selection([('yes','Yes'),('no','No')],'Rate Revise'),
		'approval_flag': fields.boolean('Spl Approval'),
		'test_cert_flag': fields.boolean('Test Certificate'),
		'test_certificate': fields.binary('Test Certificate Attach'),
		
		## Child Tables Declaration
		
		'po_order':fields.one2many('kg.po.line','line_id','PO order Line'),
		'line_id': fields.one2many('ch.purchase.wo','header_id','Ch Line Id'),
		
	}
	
	_defaults = {
		
		'date_planned': lambda * a: time.strftime('%Y-%m-%d'),
		'line_state': 'draft',
		'name': 'PO',
		'cancel_flag': False,
		'price_type': 'po_uom',
		'discount_flag': False,
		'discount_per_flag': False,
		'rate_revise': 'yes',
		'approval_flag': False,
		'test_cert_flag': False,
	}
	
	def create(self, cr, uid, vals,context=None):
		if vals['product_id']:
			product_obj =  self.pool.get('product.product')
			product_rec = product_obj.browse(cr,uid,vals['product_id'])
			if product_rec.uom_id.id != product_rec.uom_po_id.id:
				vals.update({
							'product_uom':product_rec.uom_po_id.id,
							})
			elif  product_rec.uom_id.id == product_rec.uom_po_id.id:
				vals.update({
							'product_uom':product_rec.uom_id.id,
							})
		order =  super(kg_purchase_order_line, self).create(cr, uid, vals, context=context)
		return order
	
	def onchange_brand_moc(self, cr, uid, ids, product_id,brand_id):
		value = {'moc_id_temp':''}
		return {'value': value}
	
	def onchange_price(self, cr, uid, ids, product_id,brand_id,moc_id):
		value = {'least_price':'','high_price':'','recent_price':'','moc_id_temp':''}
		max_val = 0
		min_val = 0
		recent_val = 0
		if product_id and brand_id and moc_id:
			max_sql = """ 
						select max(line.price_unit),min(line.price_unit) from purchase_order_line line 
						left join purchase_order po on (po.id=line.order_id)
						join kg_brandmoc_rate rate on (rate.product_id=line.product_id)
						join ch_brandmoc_rate_details det on (det.header_id=rate.id)
						where po.state = 'approved' and rate.state in ('draft','confirmed','approved')
						and line.product_id=%s and line.brand_id = %s and line.moc_id = %s """%(product_id,brand_id,moc_id)
			cr.execute(max_sql)		
			max_data = cr.dictfetchall()
			recent_sql = """ 
						select line.price_unit from purchase_order_line line 
						left join purchase_order po on (po.id=line.order_id)
						join kg_brandmoc_rate rate on (rate.product_id=line.product_id)
						join ch_brandmoc_rate_details det on (det.header_id=rate.id)
						where po.state = 'approved' and rate.state in ('draft','confirmed','approved')
						and line.product_id = %s and line.brand_id = %s 
						and line.moc_id = %s order by po.approved_date desc limit 1 """%(product_id,brand_id,moc_id)
			cr.execute(recent_sql)		
			recent_data = cr.dictfetchall()
			if max_data:
				max_val = max_data[0]['max'] or 0
				#max_val = max_val.values()[0]
				min_val = max_data[0]['min'] or 0
			else:
				max_val = 0
				min_val = 0
			if recent_data:
				recent_val = recent_data[0]['price_unit']
			else:
				recent_val = 0
			value = {'least_price':min_val,'high_price':max_val,'recent_price':recent_val}
		return {'value': value}
	
	def onchange_moc(self, cr, uid, ids, moc_id_temp):
		value = {'moc_id':''}
		if moc_id_temp:
			rate_rec = self.pool.get('ch.brandmoc.rate.details').browse(cr,uid,moc_id_temp)
			value = {'moc_id': rate_rec.moc_id.id}
		return {'value': value}
	
	def onchange_price_exceed_alert(self, cr, uid, ids, recent_price,price_unit,product_id,brand_id,moc_id):
		if product_id and brand_id and moc_id:
			max_sql = """ 
						select det.rate from kg_brandmoc_rate rate
						join ch_brandmoc_rate_details det on (det.header_id=rate.id)
						where rate.state = 'approved' and rate.product_id=%s
						and det.brand_id = %s and det.moc_id = %s """%(product_id,brand_id,moc_id)
			cr.execute(max_sql)		
			max_data = cr.dictfetchall()
			design_rate = max_data[0]['rate']
			if design_rate < price_unit and recent_price < price_unit:
				raise osv.except_osv(_('Warning!'),_("Rate %s exceed from design %s & last PO rate %s"%(price_unit,design_rate,recent_price)))
			if design_rate < price_unit:
				raise osv.except_osv(_('Warning!'),_("Rate %s exceed from design rate %s"%(price_unit,design_rate)))
		if recent_price < price_unit:
			raise osv.except_osv(_('Warning!'),_("Rate %s exceed from Last PO rate %s"%(price_unit,recent_price)))
		
		return True
	
	def _check_length(self, cr, uid, ids, context=None):		
		rec = self.browse(cr, uid, ids[0])
		if rec.order_id.po_type != 'frompi':
			if rec.uom_conversation_factor == 'two_dimension':
				if rec.length <= 0:
					return False					
		return True
	
	def _check_breadth(self, cr, uid, ids, context=None):		
		rec = self.browse(cr, uid, ids[0])
		if rec.order_id.po_type != 'frompi':
			if rec.uom_conversation_factor == 'two_dimension':
				if rec.breadth <= 0:
					return False					
		return True
	
	_constraints = [
		
		(_check_length,'You can not save this Length with Zero value !',['Length']),
		(_check_breadth,'You can not save this Breadth with Zero value !',['Breadth']),
		
	]
	
	def onchange_qty(self, cr, uid, ids,product_qty,pending_qty,pi_line_id,pi_qty,uom_conversation_factor,length,breadth,price_type,product_id):
		logger.info('[KG OpenERP] Class: kg_purchase_order_line, Method: onchange_qty called...')
		
		# Need to do block flow
		value = {'pending_qty': '','quantity': 0}
		quantity = 0
		if price_type == 'per_kg':
			prod_rec = self.pool.get('product.product').browse(cr,uid,product_id)
			if uom_conversation_factor == 'two_dimension':
				if prod_rec.po_uom_in_kgs > 0:
					quantity = product_qty * prod_rec.po_uom_in_kgs * length * breadth
			elif uom_conversation_factor == 'one_dimension':
				if prod_rec.po_uom_in_kgs > 0:
					quantity = product_qty * prod_rec.po_uom_in_kgs
				else:
					quantity = product_qty
			else:
				quantity = product_qty
		else:
			quantity = product_qty
		if pi_line_id:
			if product_qty and product_qty > pi_qty:
				raise osv.except_osv(_(' If PO From PI !!'),_("PO Qty can not be greater than Indent Qty !") )
			else:
				value = {'pending_qty': product_qty,'quantity': quantity}
		else:
			value = {'pending_qty': product_qty,'quantity': quantity}
		if uom_conversation_factor == 'two_dimension':
			if length <= 0:
				raise osv.except_osv(_(' Warning !!'),_("You can not save this Length with Zero value !") )
			if breadth <= 0:
				raise osv.except_osv(_(' Warning !!'),_("You can not save this Breadth with Zero value !") )
		
		return {'value': value}
	
	def onchange_price_type(self, cr, uid, ids,product_qty,uom_conversation_factor,length,breadth,price_type,product_id):
		value = {'quantity': 0}
		quantity = 0
		if price_type == 'per_kg':
			prod_rec = self.pool.get('product.product').browse(cr,uid,product_id)
			if uom_conversation_factor == 'two_dimension':
				if prod_rec.po_uom_in_kgs > 0:
					quantity = product_qty * prod_rec.po_uom_in_kgs * length * breadth
			elif uom_conversation_factor == 'one_dimension':
				if prod_rec.po_uom_in_kgs > 0:
					quantity = product_qty * prod_rec.po_uom_in_kgs
				else:
					quantity = product_qty
			else:
				quantity = product_qty
		else:
			quantity = product_qty
		value = {'quantity': quantity}
		return {'value': value}
	
	def unlink(self, cr, uid, ids, context=None):
		if context is None:
			context = {}
		for rec in self.browse(cr, uid, ids, context=context):
			parent_rec = rec.order_id
			if parent_rec.state not in ['draft','confirmed']:
				raise osv.except_osv(_('Invalid Action!'), _('Cannot delete a purchase order line which is in state \'%s\'.') %(parent_rec.state,))
			else:
				if parent_rec.po_type == 'direct' or parent_rec.po_type == 'fromquote':
					return super(kg_purchase_order_line, self).unlink(cr, uid, ids, context=context)
				else:
					order_id = parent_rec.id
					pi_line_rec = rec.pi_line_id
					pi_line_id = rec.pi_line_id.id
					pi_line_rec.write({'line_state' : 'process','draft_flag':False})
					del_sql = """ delete from kg_poindent_po_line where po_order_id=%s and piline_id=%s """ %(order_id,pi_line_id)
					cr.execute(del_sql)				
					return super(kg_purchase_order_line, self).unlink(cr, uid, ids, context=context)
	
kg_purchase_order_line()

class kg_po_line(osv.osv):
	
	_name = "kg.po.line"
	
	_columns = {
			
			## Basic Info
			
			'line_id': fields.many2one('purchase.order.line', 'PO No'),
			
			## Module Requirement Info
			
			'kg_discount': fields.float('Discount Amount'),
			'kg_discount_per': fields.float('Discount (%)', digits_compute= dp.get_precision('Discount')),
			'price_unit': fields.float('Unit Price', size=120),
			'date_order':fields.date('PO Date'),
			'supp_name':fields.many2one('res.partner','Supplier',size=120),
			'other_ch':fields.float('Other Charges',size=128),
			'po_no': fields.many2one('purchase.order','PO No'),
			
	}
	
kg_po_line()


class kg_purchase_order_expense_track(osv.osv):
	
	_name = "kg.purchase.order.expense.track"
	_description = "kg expense track"
	
	_columns = {
			
			## Basic Info
			
			'expense_id': fields.many2one('purchase.order', 'Expense Track'),
			
			## Module Requirement Info
			
			'name': fields.char('Number', size=128, select=True,readonly=False),
			'date': fields.date('Creation Date'),
			'company_id': fields.many2one('res.company', 'Company Name'),
			'description': fields.char('Description'),
			'expense_amt': fields.float('Amount'),
			'expense': fields.many2one('kg.expense.master','Expense'),
			
	}
	
	_defaults = {
			
			'company_id': lambda self,cr,uid,c: self.pool.get('res.company')._company_default_get(cr, uid, 'kg.purchase.order.expense.track', context=c),
			'date' : lambda * a: time.strftime('%Y-%m-%d'),
			
		}
	
kg_purchase_order_expense_track()

class ch_purchase_wo(osv.osv):
	
	_name = "ch.purchase.wo"
	_description = "Ch Purchase WO"
	
	_columns = {
			
			## Basic Info
			
			'header_id': fields.many2one('purchase.order.line', 'PO Line'),
			
			## Module Requirement Info
			
			'wo_id': fields.char('WO No.'),
			'w_order_id': fields.many2one('kg.work.order','WO',required=True, domain="[('state','=','confirmed')]"),
			'w_order_line_id': fields.many2one('ch.work.order.details','WO',required=True),
			'qty': fields.float('Qty'),
			
	}
	
	def onchange_wo(self, cr, uid, ids,w_order_line_id):
		value = {'wo_id': ''}
		if w_order_line_id:
			wo_rec = self.pool.get('ch.work.order.details').browse(cr,uid,w_order_line_id)
			value = {'wo_id':wo_rec.order_no}
		return {'value':value}
	
	def _check_qty(self, cr, uid, ids, context=None):		
		rec = self.browse(cr, uid, ids[0])
		if rec.qty <= 0.00:
			return False					
		return True
	
	_constraints = [
		
		(_check_qty,'You cannot save with zero qty !',['Qty']),
		
		]
	
ch_purchase_wo()
