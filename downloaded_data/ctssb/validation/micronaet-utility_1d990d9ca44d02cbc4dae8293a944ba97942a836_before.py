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
import io
import sys
import base64
import logging
import openerp
#import shutil
import shutil
import xlsxwriter
from xlsxwriter.utility import xl_rowcol_to_cell
import openerp.netsvc as netsvc
import openerp.addons.decimal_precision as dp
from openerp.osv import fields, osv, expression, orm
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from openerp import SUPERUSER_ID#, api
from openerp import tools
from openerp.tools.translate import _
from openerp.tools.float_utils import float_round as round
from openerp.tools import (DEFAULT_SERVER_DATE_FORMAT, 
    DEFAULT_SERVER_DATETIME_FORMAT, 
    DATETIME_FORMATS_MAP, 
    float_compare)


_logger = logging.getLogger(__name__)

class ExcelWriter(orm.Model):
    """ Model name: ExcelWriter
    """    
    _name = 'excel.writer'
    _description = 'Excel writer'
    
    # -------------------------------------------------------------------------
    #                                   UTILITY:
    # -------------------------------------------------------------------------
    def clean_filename(self, destination):
        ''' Clean char that generate error
        '''
        destination = destination.replace('/', '_').replace(':', '_')
        if not(destination.endswith('xlsx') or destination.endswith('xls')):
            destination = '%s.xlsx' % destination
        return destination    
        
    # Format utility:
    def clean_odoo_binary(self, odoo_binary_field):
        ''' Prepare image data from odoo binary field:
        '''
        return io.BytesIO(base64.decodestring(odoo_binary_field))
    
    def format_date(self, value):
        ''' Format hour DD:MM:YYYY
        '''
        if not value:
            return ''
        return '%s/%s/%s' % (
            value[8:10],
            value[5:7],
            value[:4],
            )

    def format_hour(self, value, hhmm_format=True, approx = 0.001, 
            zero_value='0:00'):
        ''' Format hour HH:MM
        '''
        if not hhmm_format:
            return value
            
        if not value:
            return zero_value
            
        value += approx    
        hour = int(value)
        minute = int((value - hour) * 60)
        return '%d:%02d' % (hour, minute) 
    
    # Excel utility:
    def _create_workbook(self, extension='xlsx'):
        ''' Create workbook in a temp file
        '''
        now = datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        now = now.replace(':', '_').replace('-', '_').replace(' ', '_')
        filename = '/tmp/wb_%s.%s' % (now, extension)
             
        _logger.info('Start create file %s' % filename)
        self._WB = xlsxwriter.Workbook(filename)
        self._WS = {}
        self._filename = filename
        _logger.warning('Created WB and file: %s' % filename)
        
        self.set_format() # setup default format for text used
        self.get_format() # Load database of formats

    def _close_workbook(self, ):
        ''' Close workbook
        '''
        self._WS = {}
        self._wb_format = False
        
        try:
            del(self._WB)
        except:            
            _logger.error('Error closing WB')    
        self._WB = False # remove object in instance

    def close_workbook(self, ):
        ''' Close workbook
        '''
        return self._close_workbook()

    def create_worksheet(self, name=False, extension='xlsx'):
        ''' Create database for WS in this module
        '''
        try:
            if not self._WB:
                self._create_workbook(extension=extension)
            _logger.info('Using WB: %s' % self._WB)
        except:
            self._create_workbook(extension=extension)
        self._WS[name] = self._WB.add_worksheet(name)

    def column_hidden(self, ws_name, columns_w):
        """ WS: Worksheet passed
            columns_w: list of dimension for the columns
        """
        for col in columns_w:
            self._WS[ws_name].set_column(
                col, col, None, None, {'hidden': True})
        return True

    def row_hidden(self, ws_name, row_w):
        """ WS: Worksheet passed
            columns_w: list of dimension for the columns
        """
        for row in row_w:
            self._WS[ws_name].set_row(
                row, None, None, {'hidden': True})
        return True

    def hide(self, ws_name):
        """ Hide sheet
        """
        return self._WS[ws_name].hide()

    def set_zoom(self, ws_name, zoom=100):
        ''' Set page zoom in preview
        '''
        _logger.warning('Set zoom for page: %s' % ws_name)
        self._WS[ws_name].set_zoom(zoom)
 
    def set_print_scale(self, ws_name, scale=100):
        ''' Set page scale in preview
        '''
        _logger.warning('Set scale for page: %s' % ws_name)
        self._WS[ws_name].set_print_scale(scale)
        
    def fit_to_pages(self, ws_name, width=1, height=1):
        ''' Set page scale in preview
        '''
        _logger.warning('Set fit to page: %s' % ws_name)
        self._WS[ws_name].fit_to_pages(width, height)
        
    def set_margins(self, ws_name, left=0.2, right=0.2, top=0.2, bottom=0.2):
        ''' Set page margins
        '''
        _logger.warning('Set margin for page: %s' % ws_name)
        self._WS[ws_name].set_margins(
            left=left, 
            right=right, 
            top=top, 
            bottom=bottom)
        
    def send_mail_to_group(self, cr, uid, 
            group_name,
            subject, body, filename, # Mail data
            context=None):
        ''' Send mail of current workbook to all partner present in group 
            passed
            group_name: use format module_name.group_id
            subject: mail subject
            body: mail body
            filename: name of xlsx attached file
        '''
        # Send mail with attachment:
        
        # Pool used
        group_pool = self.pool.get('res.groups')
        model_pool = self.pool.get('ir.model.data')
        thread_pool = self.pool.get('mail.thread')

        self._close_workbook() # Close before read file
        attachments = [(
            filename, 
            open(self._filename, 'rb').read(), # Raw data
            )]

        group = group_name.split('.')
        group_id = model_pool.get_object_reference(
            cr, uid, group[0], group[1])[1]    
        partner_ids = []
        for user in group_pool.browse(
                cr, uid, group_id, context=context).users:
            partner_ids.append(user.partner_id.id)
            
        thread_pool = self.pool.get('mail.thread')
        thread_pool.message_post(cr, uid, False, 
            type='email', 
            body=body, 
            subject=subject,
            partner_ids=[(6, 0, partner_ids)],
            attachments=attachments, 
            context=context,
            )
        self._close_workbook() # if not closed maually        

    def save_file_as(self, destination):
        ''' Close workbook and save in another place (passed)
        '''
        _logger.warning('Save file as: %s' % destination)        
        origin = self._filename
        self._close_workbook() # if not closed manually
        shutil.move(origin, destination)
        return True

    def save_binary_xlsx(self, binary):
        ''' Save binary data passed as file temp (returned)
        '''
        b64_file = base64.decodestring(binary)
        now = datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        filename = \
            '/tmp/file_%s.xlsx' % now.replace(':', '_').replace('-', '_')
        f = open(filename, 'wb')
        f.write(b64_file)
        f.close()
        return filename
        
    def return_attachment(self, cr, uid, name, name_of_file=False, 
            version='8.0', php=False, context=None):
        ''' Return attachment passed
            name: Name for the attachment
            name_of_file: file name downloaded
            php: paremeter if activate save_as module for 7.0 (passed base srv)
            context: context passed
        '''        
        if context is None: 
            context = {
                'lang': 'it_IT',
                }
        if not name_of_file:
            now = datetime.now()
            now = now.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            now = now.replace('-', '_').replace(':', '_') 
            name_of_file = '/tmp/report_%s.xlsx' % now
    
        # Pool used:         
        attachment_pool = self.pool.get('ir.attachment')
        
        origin = self._filename
        self._close_workbook() # if not closed manually
        try:
            b64 = open(origin, 'rb').read().encode('base64')
        except:
            _logger.error(_('Cannot return file: %s') % origin)
            raise osv.except_osv(
                _('Report error'), 
                _('Cannot return file: %s') % origin,
                )
                
        attachment_id = attachment_pool.create(cr, uid, {
            'name': name,
            'datas_fname': name_of_file,
            'type': 'binary',
            'datas': b64,
            'partner_id': 1,
            'res_model': 'res.partner',
            'res_id': 1,
            }, context=context)
        _logger.info('Return XLSX file: %s' % self._filename)
        
        if version=='8.0':        
            return {
                'type' : 'ir.actions.act_url',
                'url': '/web/binary/saveas?model=ir.attachment&field=datas&'
                    'filename_field=datas_fname&id=%s' % attachment_id,
                'target': 'self',
                }
        elif php: 
            config_pool = self.pool.get('ir.config_parameter')
            key = 'web.base.url.excel'
            config_ids = config_pool.search(cr, uid, [
                ('key', '=', key)], context=context)
            if not config_ids:
                raise osv.except_osv(
                    _('Errore'), 
                    _('Avvisare amministratore: configurare parametro: %s' % (
                        key)),
                    )
            config_proxy = config_pool.browse(
                cr, uid, config_ids, context=context)[0]
            base_address = config_proxy.value
            
            url_call = '%s/save_as.php?filename=%s&name=%s' % (
                base_address,
                origin, 
                os.path.basename(origin),
                )
            _logger.info('URL parameter: %s' % url_call)
            return {
                'type': 'ir.actions.act_url',
                'url': url_call,
                #'target': 'new',
                }            
        else: # version '7.0' (return as attachment to be opened)
            return {
                'type': 'ir.actions.act_window',
                'name': name,
                'type': 'ir.actions.act_window',
                'view_type': 'form',
                'view_mode': 'form',
                'res_id': attachment_id,
                'res_model': 'ir.attachment',
                'views': [(False, 'form')],
                'context': context,
                'target': 'current',
                'nodestroy': False,
                }                

    def set_paper(self, ws_name, page_format='A4'):
        ''' Set page format 
        '''
        self._WS[ws_name].set_paper(page_format)
        
    def merge_cell(self, ws_name, rectangle, default_format=False, data=''):
        ''' Merge cell procedure:
            WS: Worksheet where work
            rectangle: list for 2 corners xy data: [0, 0, 10, 5]
            default_format: setup format for cells
        '''
        rectangle.append(data)        
        if default_format:
            rectangle.append(default_format)            
        self._WS[ws_name].merge_range(*rectangle)
        return 
        
    def write_image(self, ws_name, row, col, 
            x_offset=0, y_offset=0, x_scale=1, y_scale=1, positioning=2,
            filename=False, data=False, 
            tip='Product image',
            #url=False, 
            ):
        ''' Insert image in cell with extra paramter
            positioning: 1 move + size, 2 move, 3 nothing
        '''
        parameters = {            
            #'url': url,
            'tip': tip,
            'x_scale': x_scale,
            'y_scale': y_scale,
            'x_offset': x_offset,
            'y_offset': y_offset,
            'positioning': positioning,            
            }
            
        if data:
            if not filename:
                filename = 'image1.png' # neeeded if data present
            parameters['image_data'] = data
        
        self._WS[ws_name].insert_image(row, col, filename, parameters) 
        return True
        
    def write_xls_line_debug(self, ws_name, row, line, col=0):
        for record in line:
            if type(record) == bool:
                self._WS[ws_name].write(
                    row, col, u'X' if record else '')
            elif type(record) in (list, tuple):
                if len(record) in (1, 2):
                    try:
                        self._WS[ws_name].write(
                            row, col, u'%s' % record[0])
                    except:
                        _logger.error('Impossibile stampare: %s' % record[0])
                        self._WS[ws_name].write(                        
                            row, col, u'ERRORE!!!!')
                        import pdb; pdb.set_trace()    
                else: # (value, format) case or rich text format
                    import pdb; pdb.set_trace()
                    self._WS[ws_name].write(row, col, *record)
            else: # type(record) in (unicode, str, float, int): # Normal text
                self._WS[ws_name].write(row, col, u'%s' % record)
            col += 1
        return True
    

    def write_xls_line(self, ws_name, row, line, default_format=False, col=0,
            verbose=False, debug=True):
        ''' Write line in excel file:
            WS: Worksheet where find
            row: position where write
            line: Row passed is a list of element or tuple (element, format)
            default_format: if present replace when format is not present
            
            @return: nothing
        '''
        if debug:
            return self.write_xls_line_debug(ws_name, row, line, col=col)
        for record in line:
            if type(record) == bool:
                self._WS[ws_name].write(
                    row, col, 'X' if record else '', default_format)
            elif type(record) in (list, tuple):
                if len(record) == 1:
                    self._WS[ws_name].write(
                        row, col, record[0], default_format)
                else: # (value, format) case or rich text format
                    self._WS[ws_name].write(row, col, *record)
            else: # type(record) in (unicode, str, float, int): # Normal text
                self._WS[ws_name].write(row, col, record, default_format)
            col += 1
        if verbose:
            _logger.info('%s' % line)    
        return True

    # Comment:
    def write_comment(self, ws_name, row, col, comment, parameters=None):
        """ Write comment in a cell
        """
        cell = self.rowcol_to_cell(row, col)
        if parameters is None:            
            parameters = {
                #author, visible, x_scale, width, y_scale, height, color
                #font_name, font_size, start_cell, start_row, start_col
                #x_offset, y_offset
                }
        if comment:    
            self._WS[ws_name].write_comment(cell, comment, parameters)
        
    def write_comment_line(self, ws_name, row, line, col=0):
        """ Write comment line
        """        
        for comment in line:
            if comment:
                self.write_comment(ws_name, row, col, comment)
            col += 1
        
    def freeze_panes(self, ws_name, row, col):
        """ Lock row or column
        """        
        self._WS[ws_name].freeze_panes(row, col)
       

    def write_xls_data(self, ws_name, row, col, data, default_format=False):
        ''' Write data in row col position with default_format
            
            @return: nothing
        '''
        if default_format:
            self._WS[ws_name].write(row, col, data, default_format)
        else:    
            self._WS[ws_name].write(row, col, data, default_format)
        return True

    def rowcol_to_cell(self, row, col, row_abs=False, col_abs=False):
        ''' Return row, col format in "A1" notation
        '''
        return xl_rowcol_to_cell(row, col, row_abs=row_abs, col_abs=col_abs)

    def write_formula(self, ws_name, row, col, formula, format_code, value):
        ''' Write formula in cell passed
        '''
        return self._WS[ws_name].write_formula(
            row, col, formula, default_format, value='')
        
    def column_width(self, ws_name, columns_w, col=0, default_format=False):
        ''' WS: Worksheet passed
            columns_w: list of dimension for the columns
        '''
        for w in columns_w:
            self._WS[ws_name].set_column(col, col, w, default_format)
            col += 1
        return True

    def row_height(self, ws_name, row_list, height=10):
        ''' WS: Worksheet passed
            row_list: list of row
        '''
        if type(row_list) in (list, tuple):            
            for row in row_list:
                self._WS[ws_name].set_row(row, height)
        else:        
            self._WS[ws_name].set_row(row_list, height)                
        return True

    def autofilter(self, ws_name, r1, c1, r2, c2):
        ''' Set auto filter
        '''
        return self._WS[ws_name].autofilter(r1, c1, r2, c2)
        
    def set_format(    
            self, 
            # Title:
            title_font='Courier 10 pitch', title_size=11, title_fg='black', 
            # Header:
            header_font='Courier 10 pitch', header_size=9, header_fg='black',
            # Text:
            text_font='Courier 10 pitch', text_size=9, text_fg='black',
            # Number:
            number_format='#,##0.#0',
            # Layout:
            border=1,
            ):
        ''' Setup 4 element used in normal reporting 
            Every time replace format setup with new database           
        '''
        self._default_format = {
            'title': (title_font, title_size, title_fg),
            'header': (header_font, header_size, header_fg),
            'text': (text_font, text_size, text_fg),
            'number': number_format,
            'border': border,
            }
        
        # Save in private method:    
        self._wb_format = False
        self.reload_format_db()  
  
        _logger.warning('Set format variables: %s' % self._default_format)            
        return
    
    def get_format(self, key=False):  
        ''' Database for format cells
            key: mode of format
            if not passed load database only
        '''
        try: # Used when load format before WS creation?!?!
            WB = self._WB # Create with start method
        except:
            _logger.warning('Load / Re-Load WB')
            self._create_workbook('xlsx')
            WB = self._WB # Create with start method
            # XXX Worksheet
            
        F = self._default_format # readability
        
        # Save database in self:
        self.reload_format_db()
        
        # Return format or default one's
        if key:
            return self._wb_format.get(
                key, 
                self._wb_format.get('default'),
                )
        else:
            return True        

    def reload_format_db(self, ):
        ''' Reload dict of format        
        '''
        try:
            if self._wb_format:
                return True
        except:
             pass
        
        WB = self._WB     
        F = self._default_format # readability
        # ---------------------------------------------------------------------
        # Create not the DB list:     
        # ---------------------------------------------------------------------
        self._wb_format = {
            # -------------------------------------------------------------
            # Used when key not present:
            # -------------------------------------------------------------
            'default' : WB.add_format({ # Usually text format
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'align': 'left',
                }),

            # -------------------------------------------------------------
            #                       TITLE:
            # -------------------------------------------------------------
            'title' : WB.add_format({
                'bold': True, 
                'font_name': F['title'][0],
                'font_size': F['title'][1],
                'font_color': F['title'][2],
                'align': 'left',
                }),
            'title_center' : WB.add_format({
                'bold': True, 
                'font_name': F['title'][0],
                'font_size': F['title'][1],
                'font_color': F['title'][2],
                'align': 'center',
                }),
                
            # -------------------------------------------------------------
            #                       HEADER:
            # -------------------------------------------------------------
            'header': WB.add_format({
                'bold': True, 
                'font_name': F['header'][0],
                'font_size': F['header'][1],
                'font_color': F['header'][2],
                'align': 'center',
                'valign': 'vcenter',
                'bg_color': '#cfcfcf', # grey
                'border': F['border'],
                #'text_wrap': True,
                }),
            'header_wrap': WB.add_format({
                'bold': True, 
                'font_name': F['header'][0],
                'font_size': F['header'][1],
                'font_color': F['header'][2],
                'align': 'center',
                'valign': 'vcenter',
                'bg_color': '#cfcfcf', # grey
                'border': F['border'],
                'text_wrap': True,
                }),

            'header90': WB.add_format({
                'bold': True, 
                'font_name': F['header'][0],
                'font_size': F['header'][1],
                'font_color': F['header'][2],
                'align': 'center',
                'valign': 'vcenter',
                'bg_color': '#cfcfcf', # grey
                'border': F['border'],
                'rotation': 90,
                'valign': 'vbottom',
                }),

            # -------------------------------------------------------------
            #                       TEXT:
            # -------------------------------------------------------------
            'text_wrap': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'align': 'left',
                'valign': 'top',
                'text_wrap': True,
                }),                    
            'text_right_wrap': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'align': 'right',
                'text_wrap': True,
                }),

            'text': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'align': 'left',
                'valign': 'top',
                }),                    
            'text_center': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'align': 'center',
                #'valign': 'vcenter',
                }),
            'text_center_all': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'align': 'center',
                'valign': 'vcenter',
                }),
            'text_right': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'text_right_green': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'align': 'right',
                'bg_color': '#b1f9c1',
                }),
            'text_right_red': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'align': 'right',
                'bg_color': '#ffc6af',
                }),
                
            'text_total': WB.add_format({
                'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#DDDDDD',
                'align': 'left',
                'valign': 'vcenter',
                #'text_wrap': True,
                }),

            # --------------
            # Text BG color:
            # --------------
            'bg_white': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#FFFFFF',
                'align': 'left',
                #'valign': 'vcenter',
                }),
            'bg_blue': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#c4daff',
                'align': 'left',
                #'valign': 'vcenter',
                }),
            'bg_red': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#ffc6af',
                'align': 'left',
                #'valign': 'vcenter',
                }),
            'bg_red_right': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#ffc6af',
                'align': 'right',
                #'valign': 'vcenter',
                }),

            'bg_green': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#b1f9c1',
                'align': 'left',
                #'valign': 'vcenter',
                }),
                
            'bg_yellow': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'font_color': 'black',
                'bg_color': '#fffec1',
                'align': 'left',
                #'valign': 'vcenter',
                }),                
            'bg_yellow_right': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'font_color': 'black',
                'bg_color': '#fffec1',
                'align': 'right',
                #'valign': 'vcenter',
                }),                

            'bg_orange': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'font_color': 'black',
                'bg_color': '#fcdebd',
                'align': 'left',
                #'valign': 'vcenter',
                }),                
            'bg_orange_right': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'font_color': 'black',
                'bg_color': '#fcdebd',
                'align': 'right',
                #'valign': 'vcenter',
                }),                

            'bg_red_number': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#ffc6af',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'bg_green_number': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#b1f9c1',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'bg_yellow_number': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'font_color': 'black',
                'bg_color': '#fffec1',##ffff99',
                'align': 'right',
                #'valign': 'vcenter',
                }),                
            'bg_orange_number': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'font_color': 'black',
                'bg_color': '#fcdebd',
                'align': 'right',
                #'valign': 'vcenter',
                }),                
            'bg_white_number': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'font_color': 'black',
                'bg_color': '#FFFFFF',
                'align': 'right',
                #'valign': 'vcenter',
                }),                
            'bg_blue_number': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'font_color': 'black',
                'bg_color': '#c4daff',##ffff99',
                'align': 'right',
                'num_format': F['number'],
                #'valign': 'vcenter',
                }),                

            # Number Bold background:
            'bg_red_number_bold': WB.add_format({
                'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'font_color': 'black',
                'bg_color': '#ffc6af',
                'align': 'right',
                'num_format': F['number'],
                #'valign': 'vcenter',
                }),                
            'bg_green_number_bold': WB.add_format({
                'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'font_color': 'black',
                'bg_color': '#b1f9c1',
                'align': 'right',
                'num_format': F['number'],
                #'valign': 'vcenter',
                }),                
            'bg_blue_number_bold': WB.add_format({
                'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'font_color': 'black',
                'bg_color': '#c4daff',##ffff99',
                'align': 'right',
                'num_format': F['number'],
                #'valign': 'vcenter',
                }),                

            # TODO remove?
            'bg_order': WB.add_format({
                'bold': True, 
                'bg_color': '#cc9900',
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'num_format': F['number'],
                'align': 'right',
                #'valign': 'vcenter',
                }),

            # --------------
            # Text FG color:
            # --------------
            'text_black': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': 'black',
                'border': F['border'],
                'align': 'left',
                'valign': 'vcenter',
                #'text_wrap': True
                }),
            'text_blue': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': 'blue',
                'border': F['border'],
                'align': 'left',
                'valign': 'vcenter',
                #'text_wrap': True
                }),
            'text_red': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': '#ff420e',
                'border': F['border'],
                'align': 'left',
                'valign': 'vcenter',
                #'text_wrap': True
                }),
            'text_green': WB.add_format({
                'font_color': '#328238', ##99cc66
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'align': 'left',
                'valign': 'vcenter',
                #'text_wrap': True
                }),
            'text_grey': WB.add_format({
                'font_color': '#eeeeee',
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'align': 'left',
                'valign': 'vcenter',
                #'text_wrap': True
                }),                
            'text_wrap': WB.add_format({
                'font_color': 'black',
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'align': 'left',
                'valign': 'vcenter',
                #'text_wrap': True,
                }),

            # -------------------------------------------------------------
            #                       NUMBER:
            # -------------------------------------------------------------
            # Heat map:
            'bg_red_number_0': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#FACACA',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'bg_red_number_1': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#FFB3B3',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'bg_red_number_2': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#FC8686',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'bg_red_number_3': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#FF4F4F',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'bg_red_number_4': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#D12A17',
                'align': 'right',
                #'valign': 'vcenter',
                }),
                
            'bg_green_number_0': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#DAFFD6',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'bg_green_number_1': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#BAFFB3',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'bg_green_number_2': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#93FF8F',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'bg_green_number_3': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#65FF54',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'bg_green_number_4': WB.add_format({
                #'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'bg_color': '#2BD119',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            

                
            'number': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'num_format': F['number'],
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'number_center': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'num_format': F['number'],
                'align': 'right',
                'valign': 'vcenter',
                }),

            # ----------------
            # Number FG color:
            # ----------------
            'number_black': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'num_format': F['number'],
                'font_color': 'black',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'number_blue': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'num_format': F['number'],
                'font_color': 'blue',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'number_grey': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'num_format': F['number'],
                'font_color': 'grey',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'number_red': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'num_format': F['number'],
                'font_color': 'red',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            'number_green': WB.add_format({
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'border': F['border'],
                'num_format': F['number'],
                'font_color': 'green',
                'align': 'right',
                #'valign': 'vcenter',
                }),

            'number_total': WB.add_format({
                'bold': True, 
                'font_name': F['text'][0],
                'font_size': F['text'][1],
                'font_color': F['text'][2],
                'border': F['border'],
                'num_format': F['number'],
                'bg_color': '#DDDDDD',
                'align': 'right',
                #'valign': 'vcenter',
                }),
            }                
        return True    
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
