# -*- coding: utf-8 -*-

from openerp import models, fields, api
from datetime import datetime

#Extra fields in crm.lead to deal with Hostel-reservations
class crm_lead(models.Model):
	_inherit = 'crm.lead'

	checkin = fields.Date('Check-in')
	checkout = fields.Date('Check-out')
	nr_adults = fields.Integer(default=0, string="Adults")
	nr_children = fields.Integer(default=0, string="Children")
	room = fields.Char('Requested room')

	# Confirm reservation
	# Opens a popup-window with the hotel.reservation form view with default-values from reservation-lead
	@api.multi
	def confirm(self):
		# Get currency id for Chilean pesos
		CLP_id = self.env['res.currency'].search([('name','=','CLP')]).id
		#Convert date to datetime-format
		temp_checkin = fields.Datetime.from_string(self.checkin + " 12:00:00")
		temp_checkout = fields.Datetime.from_string(self.checkout + " 12:00:00")
		#konvertera variabl till dattime?
		print "TESTING"
		print temp_checkin
		print temp_checkout
		print datetime.strptime(self.checkin)
		# Create a new partner from customer information
		newGuestID = self.env['res.partner'].create({'name':self.contact_name, 'phone':self.phone, 'email':self.email_from, 'country_id': int(self.country_id), 'type':0 }).id

		# act_window action-structure
		act_window = {
			'type': 'ir.actions.act_window',
			'res_model': 'hotel.reservation',
			'view_mode': 'form',
			'view_type': 'form',
			'target': 'new',
			'context': {	'default_adults': self.nr_adults,
					'default_children' : self.nr_children,
					'default_checkin': self.checkin,	
					'default_checkout': self.checkout,
					'default_pricelist_id': self.env['product.pricelist'].search([('currency_id','=', CLP_id)]).id,
					'default_partner_id': newGuestID,
					'default_crm_message': self.description,
					'default_requested_room': self.room,
				},
		}
		
		return act_window
