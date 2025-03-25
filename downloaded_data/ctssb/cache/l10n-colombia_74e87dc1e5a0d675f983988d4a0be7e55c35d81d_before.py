# -*- coding: utf-8 -*-
# Copyright 2019 Joan Marín <Github@JoanMarin>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import global_functions
from datetime import datetime
from validators import url
from requests import post, exceptions
from lxml import etree
from odoo import api, models, fields, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    einvoicing_enabled = fields.Boolean(string='E-Invoicing Enabled')
    send_invoice_to_dian = fields.Selection(
        [('0', 'Immediately'),
         ('1', 'After 1 Day'),
         ('2', 'After 2 Days')],
        string='Send Invoice to DIAN?',
        default='0')
    profile_execution_id = fields.Selection(
        [('1', 'Production'), ('2', 'Test')],
        'Destination Environment of Document',
        default='2',
        required=True)
    test_set_id = fields.Char(string='Test Set Id')
    software_id = fields.Char(string='Software Id')
    software_pin = fields.Char(string='Software PIN')
    certificate_filename = fields.Char(string='Certificate Filename')
    certificate_file = fields.Binary(string='Certificate File')
    certificate_password = fields.Char(string='Certificate Password')
    certificate_date = fields.Date(string='Certificate Date Validity')
    certificate_remaining_days = fields.Integer(
        string='Certificate Remaining Days',
        default=False)
    signature_policy_url = fields.Char(string='Signature Policy Url')
    signature_policy_description = fields.Char(string='Signature Policy Description')
    files_path = fields.Char(string='Files Path')
    einvoicing_email = fields.Char(
        string='E-invoice Email From',
        help="Enter the e-invoice sender's email.")
    einvoicing_partner_no_email = fields.Char(
        string='Failed Emails To', 
        help='Enter the email where the invoice will be sent when the customer does not have an email.')
    report_template = fields.Many2one(
        string='Report Template',
        comodel_name='ir.actions.report.xml')
    notification_group_ids = fields.One2many(
        comodel_name='einvoice.notification.group',
        inverse_name='company_id',
        string='Notification Group')
    get_numbering_range_response = fields.Text(string='GetNumberingRange Response')

    @api.onchange('signature_policy_url')
    def onchange_signature_policy_url(self):
        if not url(self.signature_policy_url):
            raise ValidationError(_('Invalid URL.'))

    @api.multi
    def write(self, vals):
        rec = super(ResCompany, self).write(vals)

        for company in self:
            if company.einvoicing_enabled:
                if not vals.get('certificate_date'):
                    pkcs12 = global_functions.get_pkcs12(
                        company.certificate_file,
                        company.certificate_password)
                    x509 = pkcs12.get_certificate()
                    date = x509.get_notAfter()
                    date = '{}-{}-{}'.format(date[0:4], date[4:6], date[6:8])
                    company.certificate_date = date

        return rec

    def _get_GetNumberingRange_values(self):
        xml_soap_values = global_functions.get_xml_soap_values(
            self.certificate_file,
            self.certificate_password)

        xml_soap_values['accountCode'] = self.partner_id.identification_document
        xml_soap_values['accountCodeT'] = self.partner_id.identification_document
        xml_soap_values['softwareCode'] = self.software_id

        return xml_soap_values

    def action_GetNumberingRange(self):
        msg1 = _("Unknown Error,\nStatus Code: %s,\nReason: %s.")
        msg2 = _("Unknown Error: %s\n.")
        wsdl = 'https://vpfe.dian.gov.co/WcfDianCustomerServices.svc?wsdl'
        s = "http://www.w3.org/2003/05/soap-envelope"

        GetNumberingRange_values = self._get_GetNumberingRange_values()
        GetNumberingRange_values['To'] = wsdl.replace('?wsdl', '')
        xml_soap_with_signature = global_functions.get_xml_soap_with_signature(
            global_functions.get_template_xml(GetNumberingRange_values, 'GetNumberingRange'),
            GetNumberingRange_values['Id'],
            self.certificate_file,
            self.certificate_password)

        try:
            response = post(
                wsdl,
                headers={'content-type': 'application/soap+xml;charset=utf-8'},
                data=etree.tostring(xml_soap_with_signature))

            if response.status_code == 200:
                root = etree.fromstring(response.text)
                response = ''

                for element in root.iter("{%s}Body" % s):
                    response = etree.tostring(element, pretty_print=True)

                if response == '':
                    response = etree.tostring(root, pretty_print=True)

                self.write({'get_numbering_range_response': response})
            else:
                raise ValidationError(msg1 % (response.status_code, response.reason))

        except exceptions.RequestException as e:
            raise ValidationError(msg2 % (e))

        return True

    @api.multi
    def action_process_dian_documents(self):
        for company in self:
            count = 0
            dian_documents = self.env['account.invoice.dian.document'].search(
                [('state', 'in', ('draft', 'sent')), ('company_id', '=', company.id)],
                order = 'zipped_filename asc')

            for dian_document in dian_documents:
                today = datetime.strptime(fields.Date.context_today(self), '%Y-%m-%d')
                date_from = datetime.strptime(dian_document.invoice_id.date_invoice, '%Y-%m-%d')
                days = (today - date_from).days

                if int(dian_document.invoice_id.send_invoice_to_dian) <= days:
                    dian_document.action_process()
                    count += 1

                if dian_document.state != 'done' or count <= 10:
                    return True

        return True

    @api.model
    def cron_process_dian_documents(self):
        for company in self.search([]):
            company.action_process_dian_documents()
