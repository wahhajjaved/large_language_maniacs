# -*- coding: utf-8 -*-
# copyright reserved

from openerp.osv import fields, osv
from openerp import models, fields, api, exceptions, _
import openerp.addons.decimal_precision as dp
from openerp import workflow

from datetime import datetime,date,timedelta
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
from openerp.tools.translate import _
from openerp.exceptions import UserError, ValidationError
import logging
import time
import math
from urlparse import urljoin
from openerp import tools, SUPERUSER_ID
from urllib import urlencode
import openerp.addons.decimal_precision as dp
_logger = logging.getLogger(__name__)

class MrpProduction(models.Model):
    _inherit='mrp.production'
    
    @api.multi
    def confirm_prod_after_reset(self):
        for record in self:
            record.action_confirm()
        
    @api.multi
    def reset_mo(self):
        for rec in self:
            workorders=self.env['mrp.production.workcenter.line'].search([('production_id','=',rec.id)], order='sequence desc')
            if workorders:
                for wo in workorders:
                    wo.unlink()
            rec.write({'is_reset_mo':True,'state':'draft','routing_id':rec.bom_id.routing_id.id,'raw_request':False})
            for each_mv in rec.move_created_ids:
                each_mv.action_cancel()
                each_mv.unlink()
#            for each_mr in rec.material_request_id:
#                each_mr.unlink()
            for each_prod in rec.product_lines:
                each_prod.unlink()
        return True

    ''''@api.multi
    def write (self, vals, update=True, mini=True):
       
       for record in self:
           res=super(MrpProduction, self).write(vals, update=update, mini=mini)
           print"MMMMMMMMMMMMMMMMM", vals.get('product_qty'), vals.get('n_produce_qty')
           if vals.get('product_qty') and vals.get('n_produce_qty'):
              if res.product_qty == res.n_produce_qty :
                 res.state='in_production'
                 print"Yyyyyyyyyyyyyy",res.state
       return res'''
       
    @api.model
    def _get_uom_id(self):
        return self.env["product.uom"].search([('name','=','Kg')], limit=1, order='id')[0]
    
    rm_reject_reason = fields.Char(string='RM Reject Reason',track_visibility='always' ,copy=False)
    product_lines= fields.One2many('mrp.production.product.line', 'production_id', 'Scheduled goods', readonly=False)
    raw_request=fields.Boolean(string='Hide RM Request Button', default=False)
    is_reset_mo=fields.Boolean(string='Reset MO', default=False)
    material_request_id=fields.One2many('mrp.raw.material.request','production_id', 'RM Request No.')
    request_state=fields.Selection([('draft','Requested'),('approve','Approved'), ('reject','Rejeted'),('cancel','Cancelled')], string='Status', related='material_request_id.state')
    delivery_ids=fields.Many2many('stock.picking','mrp_stock_raw_material_rel','production_id',
                                  'picking_id',string='Delivery Details',copy=False)
    total_wastage_qty=fields.Float('Produced Wastage Qty',compute='count_wastage_qty')
    remain_wastage_qty=fields.Float('Remaining Wastage Qty',compute='remain_wastage')
    requested_wastage_qty=fields.Float('Requested Wastage Qty')
    remain_wastage_uom_id=fields.Many2one('product.uom',  default=_get_uom_id)
    wastage_uom_id=fields.Many2one('product.uom',  default=_get_uom_id)
    wastage_ids=fields.One2many('mrp.production.workcenter.line','production_id',string='Wastage Details',copy=False)
    wastage_allow=fields.Float('Allowed Wastage', compute='allowwastage_mo')
    allow_wastage_uom_id=fields.Many2one('product.uom', default=_get_uom_id)
    wastage_batch_ids=fields.One2many('mrp.order.batch.number','production_id', compute='wastage_batches')
  
    @api.multi
    def wastage_batches(self):
        for record in self: 
            lst=[]
            batches=self.env['mrp.order.batch.number'].search([('production_id','=',record.id),('used_type','in',('scrap','grinding'))])
            for batch in batches:
                lst.append((batch.id))
            record.wastage_batch_ids=lst
   
    @api.multi
    @api.depends('product_id.weight','bom_id.bom_wastage_ids', 'product_qty','mrp_sec_qty')
    def remain_wastage(self):
        for record in self:
            if record.requested_wastage_qty:
               record.remain_wastage_qty=record.total_wastage_qty - record.requested_wastage_qty
            else:
               record.remain_wastage_qty=record.total_wastage_qty 
               
    @api.multi
    @api.depends('product_id.weight','bom_id.one_time_wastage_ids','bom_id.bom_wastage_ids', 'product_qty','mrp_sec_qty')
    def allowwastage_mo(self):
        for record in self:
            qty=0.0
            total1=0.0
            weight=0.0#record.product_id.initial_weight - record.product_id.weight if  record.product_id.initial_weight else record.product_id.weight
            if record.bom_id and record.product_id.weight:
               total=sum(line.value for line in record.bom_id.bom_wastage_ids)
               weight=((record.product_id.weight)*total ) /100
            if record.bom_id.one_time_wastage_ids:
                total1=sum(line.value for line in record.bom_id.one_time_wastage_ids)
            if record.product_uom.name == 'Pcs':
               qty=record.product_qty
            if record.product_uom.name == 'Kg':
               qty=record.mrp_sec_qty
            record.wastage_allow = (qty * (weight))+total1
            
    @api.multi
    @api.depends('wastage_ids')
    def count_wastage_qty(self):
        for record in self:
            record.total_wastage_qty=sum(line.total_wastage_qty for line in record.wastage_ids)
    
    @api.model
    def default_get(self,fields):
        rec = super(MrpProduction, self).default_get(fields)
	#CH_N067 >>>raw_material_location
	data_obj = self.env['ir.model.data']
	location=False
	product_type = rec.get('product_id')
	if product_type:
		location = data_obj.get_object_reference('api_raw_material', 'receive_film_location')[1]
        else:
		location = data_obj.get_object_reference('api_raw_material', 'receive_injection_location')[1]
	if location:	
		rec.update({'location_src_id' : location})
	#<<<
	return rec

    @api.v7
    def product_id_change(self, cr, uid, ids, product_id, product_qty=0, context=None):
        """ Finds UoM of changed product.
        		@param product_id: Id of changed product.
       			@return: Dictionary of values."""
       			
        result = super(MrpProduction,self).product_id_change(cr, uid, ids, product_id, product_qty, context)
        product = self.pool.get('product.product').browse(cr, uid, product_id, context=context)
	if product:
		data_obj = self.pool.get('ir.model.data')
		location=False
		if product.categ_id.cat_type=='film':
			location = data_obj.get_object_reference(cr,uid,'api_raw_material', 'receive_film_location')[1]
		else:
			location = data_obj.get_object_reference(cr,uid,'api_raw_material', 'receive_injection_location')[1]
		if location:	
			result['value'].update({'location_src_id':location})
        return result

    @api.multi
    def RM_Request_Mo(self):
        for record in self:
            if record.product_lines:
                email_to=''
                temp_id = self.env.ref('gt_order_mgnt.email_template_for_rm_request')
                print "temp_idtemp_idtemp_id",temp_id
#                group = self.env['res.groups'].search([('name', '=', 'RM Request Approve')])
                group = self.env['res.groups'].search([('name', '=', 'RM Request Approve/Reject')])
                print "groupgroupgroupgroup",group
                if group:
                    user_ids = self.env['res.users'].sudo().search([('groups_id', 'in', [group.id])])
                    print "user_idsuser_ids",user_ids
                    email_to = ''.join([user.partner_id.email + ',' for user in user_ids])
                    email_to = email_to[:-1]
                    print "email_toemail_to",email_to
                
                body='<b>Raw Materials Request sent to Logistic Department:</b>'

                body +='<ul><li> Date. : '+str(date.today()) +'</li></ul>'
                body +='<ul><li> Created By : '+str(self.env.user.name) +'</li></ul>'
                body +='<ul><li> Manufacturing No. : '+str(record.name) +'</li></ul>'
                body +='<ul><li> Product Name. : '+str(record.product_id.name) +'</li></ul>' 
                body +='<ul><li> Product Qty. : '+str(record.product_qty) +'</li></ul>' 
                body +="<table class='table' style='width:80%; height: 50%;font-family:arial; text-align:left;'><tr><th>Material Name </th><th> qty</th></tr>" 
                lst=[]
                for line in record.product_lines:
                    #term_qry="select  date_planned from mrp_production_workcenter_line where id in (select DISTINCT order_id from workorder_raw_material where product_id ="+str(line.product_id.id)+ "and production_id =" +str(record.id) +") limit 1"
                    #self.env.cr.execute(term_qry)
                    #schedule_order=self.env.cr.fetchone()
                    body +="<tr><td>%s</td><td>%s %s</td></tr>"%(str(line.product_id.name), str(line.product_qty), str(line.product_uom.name)) 
                    lst.append((0,0,{'product_id':line.product_id.id,'uom_id':line.product_uom.id,
                        'qty':line.required_qty,'pending_qty':line.required_qty, 'rm_type':'stock','required_date':record.date_planned,
                        'expected_compl_date':record.n_request_date,
                        })) 
                location_dest_id=record.location_dest_id
#                to send respective stock location in rm request loction
                rm_location=self.env['stock.location'].search([('actual_location','=',True),('location_id','=',location_dest_id.location_id.id)])
                print "rm_locationrm_locationrm_locationrm_location",rm_location
                rm_rqst=self.env['mrp.raw.material.request'].create({'production_id':record.id,
                            'product_id':record.product_id.id,'required_qty':record.product_qty,
                            'request_type':'normal',
                            'required_uom_id':record.product_uom.id,
                            'expected_compl_date':record.n_request_date,
                            'request_line_ids':lst,
                            'source_location':rm_location.id if rm_location else False,
                            'request_date':record.date_planned}) 
                record.write({'state':'requestrm'})
#                            to send mail on rm request
                base_url = self.env['ir.config_parameter'].get_param('web.base.url')
                query = {'db': self._cr.dbname}
                fragment = {
                              'model': 'mrp.raw.material.request',
                              'view_type': 'form',
                              'id': rm_rqst.id,
                             }
                url = urljoin(base_url, "/web?%s#%s" % (urlencode(query), urlencode(fragment)))
                print "urlurl",url
                text_link = _("""<a href="%s">%s</a> """) % (url,"VIEW REQUEST")
                body +='<li> <b>RM Request :</b> '+str(text_link) +'</li>'

                body +="</table>"
                body +='<ul><li> RM Request No. : '+str(rm_rqst.name) +'</li></ul>'
                print "bodybodybodybody",body
                if temp_id:
                   base_url = self.env['ir.config_parameter'].get_param('web.base.url')
                   query = {'db': self._cr.dbname}
                   temp_id.write({'body_html': body, 'email_to':email_to,
                                  'email_from':self.env.user.login})
                   values = temp_id.generate_email(rm_rqst.id)
                   mail_mail_obj = self.env['mail.mail']
                   msg_id = mail_mail_obj.create(values) 
                   msg_id.send()	

                shifts=self.env['mrp.workorder.rm.shifts'].search([('production_id','=',record.id)])
                shifts.write({'request_id':rm_rqst.id})

                record.raw_request=True
                record.message_post(body=body)
                rm_rqst.message_post(body=body)

    @api.multi
    def wastage_request(self):
      if not self.product_id.check_grinding and  not self.product_id.check_scrap and self._context.get('use_raw'):
         raise UserError(_('Please Select Grinding or scrap Product in Manufacturing Product.')) 
      else:
	context = self._context.copy()
        lst=[]
        raw_use=[]
        pcs_qty=(self.total_wastage_qty/self.product_id.weight) if self.total_wastage_qty else 0.0
        for line in self.product_lines:
            lst.append((0,0,{'product_id':line.product_id.id, 'uom_id':line.product_uom.id, 
                                'qty':(pcs_qty * line.product_qty) if pcs_qty else 0.0}))
	context.update({'default_production_id':self.id, 
                        'default_wastage_qty':self.total_wastage_qty if not self.remain_wastage_qty else self.remain_wastage_qty,
                        'default_wastage_uom_id':self.wastage_uom_id.id,
                        'default_remain_qty':self.total_wastage_qty,
                        'default_required_uom_id':self.wastage_uom_id.id,
                        'default_required_qty':self.total_wastage_qty if not self.remain_wastage_qty else self.remain_wastage_qty,
                        'default_extra_product_ids':lst,
                        })
        mo_form = self.env.ref('api_raw_material.extra_raw_material_from', False)
        if mo_form:
                return {
                    'name':'Raw Material Request',
                    'type': 'ir.actions.act_window',
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': 'mrp.extra.raw.material',
                    'views': [(mo_form.id, 'form')],
                    'view_id': mo_form.id,
                    'target': 'new',
                    'context': context,
             }  


class MrpProductionProductLine(models.Model):
   _inherit='mrp.production.product.line'
   
   extra_qty=fields.Float('Extra Qty',)
   required_qty=fields.Float('Required Qty', compute='_get_rawMaterialQty')
   request_qty=fields.Float('Requested Qty', compute='_get_rawMaterialQty')
   receive_qty=fields.Float('Received Qty', compute='_get_rawMaterialQty') 
   consumed_qty=fields.Float('Consumed Qty', compute='_get_rawMaterialQty')
   remain_consumed=fields.Float('Remaining to Consume Qty', compute='_get_rawMaterialQty')
   remain_received=fields.Float('Remaining to Receive Qty', compute='_get_rawMaterialQty')
   raw_materials_id=fields.One2many('workorder.raw.material', 'order_id','Raw Material Details')# to show rawmaterial details in workorders
   
   @api.multi
   def _get_rawMaterialQty(self):
	for record in self:
#            requested qty shud always remain same
                div_var,no_of_one_time_wastage_ids,no_of_component_ids,product_ids,process_id=0.0,0.0,0.0,[],False
                if record.production_id.bom_id.one_time_wastage_ids:
                    no_of_one_time_wastage_ids=sum(line.value for line in record.production_id.bom_id.one_time_wastage_ids)
#                    if record.production_id.bom_id.one_time_wastage_ids[0].workcenter_id:
#                        process_id=record.production_id.bom_id.one_time_wastage_ids[0].workcenter_id.id
#                if process_id:
                bom_line_prod_ids=[x.product_id.id for x in record.production_id.bom_id.bom_line_ids]
#                    packging_line_prod_ids=[x.product_id.id for x in record.production_id.bom_id.bom_packging_line if x.workcenter_id.id==process_id]
#                    product_ids=bom_line_prod_ids+packging_line_prod_ids
                no_of_component_ids=len(record.production_id.bom_id.bom_line_ids.ids)
                print "no_of_one_time_wastage_idsno_of_one_time_wastage_ids",no_of_one_time_wastage_ids,no_of_component_ids
                div_var=float(no_of_one_time_wastage_ids)/float(no_of_component_ids)
                print "div_vardiv_vardiv_var",div_var,product_ids
#                if product_ids:
                if record.product_id.id in bom_line_prod_ids:
                    record.required_qty=record.product_qty + div_var - record.extra_qty

                else:
                    record.required_qty=record.product_qty -record.extra_qty
                record.request_qty =record.required_qty    
                received_qty=0.0
		for picking in record.production_id.delivery_ids:
                    print "pickingpickingpicking",picking
                    if picking.state == 'done':
#                            record.production_id.write({'state':'ready'})
                            for line in picking.pack_operation_product_ids:
                                    if line.product_id.id == record.product_id.id:
                                            received_qty += line.qty_done
		record.receive_qty=received_qty
		record.remain_received = round(record.required_qty - received_qty,2)
		consumed_qty =0.00
                
		for line in record.production_id.workcenter_lines:
                    for raw in line.raw_materials_id:
                            if raw.product_id.id == record.product_id.id:

                                    consumed_qty += raw.consumed_qty
		record.consumed_qty = consumed_qty
		record.remain_consumed =round( received_qty - consumed_qty,2)
#                wo_ids=self.env['mrp.production.workcenter.line'].search([('production_id','=',record.production_id.id)])
#                print "wo_idswo_ids",wo_ids,record.production_id
#                if wo_ids:
#                    if any(wo.state == 'startworking' for wo in wo_ids):
#                        print "xfgfxgdfgdfg"
#                        self._cr.execute('UPDATE mrp_production '\
#                       'SET state=%s '\
#                       'WHERE id = %s', ('in_production', record.production_id.id))
##                        record.production_id.write({'state':'in_production'})
#		
class MrpWorkorderBatchNo(models.Model):
    _inherit='mrp.order.batch.number'
    
    @api.multi	
    def unlink(self):
    	for res in self:
		if res.batch_tfred==True:
                    raise UserError("Batch Cannot be deleted as it is already Transferred!" )
		if res.product_qty>0.0:
                    raise UserError("Batch Cannot be deleted as qty is already produced!" )
    	return super(MrpWorkorderBatchNo,self).unlink()
    

    wastage_bool=fields.Boolean('Wastage Bool',default=False)
    request_state=fields.Selection([('draft','Draft'),('requested','Approved'),('cancel','Cancelled'),('done','Done')], 
   			   string='Status', default='draft')
   			   
    wastage_product=fields.Many2one('product.product', string='Update in Product')
    used_type=fields.Selection([('grinding','Grinding'),('scrap','Scrap')],string='Used Type')
       
    @api.multi
    def cancel_wastage(self):
        for record in self:
            record.production_id.requested_wastage_qty -=record.product_qty
            record.write({'request_state':'cancel'})
            body='<b>Wastage Request Cancelled:</b>'
            body +='<ul><li> Manufacturing No.    : '+str(record.production_id.name) +'</li></ul>'
            body +='<ul><li> Batch No. : '+str(record.name) +'</li></ul>'
            body +='<ul><li> Cancelled By      : '+str(self.env.user.name) +'</li></ul>' 
            body +='<ul><li> Cancelled Date   : '+str(datetime.now() + timedelta(hours=4)) +'</li></ul>' 
            record.production_id.message_post(body=body)
            
    @api.multi
    def approve_request(self):
        for record in self:
            warehouse=self.env['stock.warehouse']
            location_id=0
            if record.wastage_product:
            	if record.used_type == 'grinding':
            		location=warehouse.search([('code','=','GRDWH')],limit=1) 
            		location_id=location.lot_stock_id.id
            	else:
            		location=warehouse.search([('code','=','SCPWH')],limit=1)
            		location_id=location.lot_stock_id.id
            		picking_type=self.env['stock.picking.type'].search([('code','=','internal')],limit=1)
                inventory=self.env['stock.inventory'].create({'name':"stock update - "+str(record.name),
                          'filter':'partial','location_id':location_id})
            	inventory.prepare_inventory()
	        lst=[]          
                lst.append((0,0,{'product_id':record.wastage_product.id,'product_uom_id':record.uom_id.id,
                             'product_qty':(record.wastage_product.sudo().qty_available + record.product_qty),
                             'location_id':location_id}))
                inventory.line_ids=lst
                inventory.action_done()
                record.write({'request_state':'requested'})
                body='<b>Wastage Request Approved:</b>'
		body +='<ul><li> Manufacturing No.    : '+str(record.production_id.name) +'</li></ul>'
		body +='<ul><li> Batch No. : '+str(record.name) +'</li></ul>'
		body +='<ul><li> Approved By      : '+str(self.env.user.name) +'</li></ul>' 
                body +='<ul><li> Used in Product         : '+str(record.wastage_product.name) +'</li></ul>'
		body +='<ul><li> Approved Date   : '+str(datetime.now() + timedelta(hours=4)) +'</li></ul>' 
		record.production_id.message_post(body=body)
            else:
                raise UserError("Please Fill in update in product." )

