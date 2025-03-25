#!/usr/bin/python
# -*- coding: utf-8 -*-
###############################################################################
#
# ODOO (ex OpenERP)
# Open Source Management Solution
# Copyright (C) 2001-2015 Micronaet S.r.l. (<https://micronaet.com>)
# Developer: Nicola Riolini @thebrush (<https://it.linkedin.com/in/thebrush>)
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################

import os
import sys
import logging
import openerp
import openerp.netsvc as netsvc
import openerp.addons.decimal_precision as dp
import xlsxwriter
from openerp.osv import fields, osv, expression
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from openerp import SUPERUSER_ID
from openerp import tools
from openerp.tools.translate import _
from openerp.tools.float_utils import float_round as round
from openerp.tools import (DEFAULT_SERVER_DATE_FORMAT,
    DEFAULT_SERVER_DATETIME_FORMAT,
    DATETIME_FORMATS_MAP,
    float_compare)

_logger = logging.getLogger(__name__)


class ResCompany(osv.osv):
    """ Model name: Parameters
    """

    _inherit = 'res.company'

    def get_type(self, code, uom):
        """ Extract type from code
        """
        code = (code or '').strip().upper()
        uom = (uom or '').upper()

        if not code:
            return _('Not assigned')

        start = code[0]
        end = code[-1]

        if uom == 'PCE':  # Machinery and Component
            return _('COMP')
        if start in 'PR':  # Waste
            return _('REC')
        if start in 'AB':  # Raw materials
            return _('MP')
        if end == 'X':  # Production (MX)
            return _('PT')
        return _('IT')  # Reselled (IT)

    # Override for MX report (was different)
    def extract_product_level_xlsx(self, cr, uid, ids, context=None):
        """ Extract current report stock level
        """
        # Pool used:
        excel_pool = self.pool.get('excel.writer')
        product_pool = self.pool.get('product.product')

        # ---------------------------------------------------------------------
        #                          Excel export:
        # ---------------------------------------------------------------------
        # Setup:
        header = [
            u'Tipo',

            u'Codigo', u'Descripcion', u'UM',
            u'Appr.', u'Mod.',

            u'Manual', u'Tiempo de Entrega', u'Promedio Kg/Dia',

            u'Nivel Minimo Dias', u'Nivel Minimo Kg.',
            u'Nivel Maximo Dia', u'Nivel Maximo Kg.',
            u'Contipaq', u'Status',
            ]

        width = [
            18,
            15, 25, 5,
            6, 9,
            5, 15, 15,
            15, 15,
            15, 15,
            15, 10,
            ]

        # ---------------------------------------------------------------------
        # Create WS:
        # ---------------------------------------------------------------------
        ws_list = (
            ('Livelli auto', [
                ('manual_stock_level', '=', False),
                ('medium_stock_qty', '>', 0),
                ]),
            ('Livelli manuali', [
                ('manual_stock_level', '=', True),
                # ('min_stock_level', '>', 0),
                ]),
            ('Non presenti', [
                ('min_stock_level', '<=', 0),
                ]),
            )
        # Create all pages:
        excel_format = {}
        for ws_name, product_filter in ws_list:
            excel_pool.create_worksheet(name=ws_name)

            excel_pool.column_width(ws_name, width)
            # excel_pool.row_height(ws_name, row_list, height=10)
            excel_pool.freeze_panes(ws_name, 2, 1)

            # -----------------------------------------------------------------
            # Generate format used (first time only):
            # -----------------------------------------------------------------
            if not excel_format:
                excel_pool.set_format()
                excel_format['title'] = excel_pool.get_format(key='title')
                excel_format['header'] = excel_pool.get_format(key='header')
                excel_format['text'] = excel_pool.get_format(key='text')
                excel_format['right'] = excel_pool.get_format(key='text_right')
                excel_format['number'] = excel_pool.get_format(key='number')

            # -----------------------------------------------------------------
            # Write title / header
            # -----------------------------------------------------------------
            row = 0
            excel_pool.write_xls_line(
                ws_name, row, header, default_format=excel_format['header'])
            excel_pool.autofilter(ws_name, row, row, 0, len(header) - 1)

            # -----------------------------------------------------------------
            # Product selection:
            # -----------------------------------------------------------------
            product_ids = product_pool.search(
                cr, uid, product_filter, context=context)

            products = product_pool.browse(
                cr, uid, product_ids,
                context=context)

            # TODO add also package data!!!
            row += 1
            for product in sorted(products, key=lambda x: (
                    self.get_type(x.default_code, x.uom_id.name),
                    x.default_code)):
                # Filter code:
                default_code = product.default_code

                # Clean some code:
                if default_code.startswith('SER'):
                    continue

                account_qty = int(product.accounting_qty)
                min_stock_level = int(product.min_stock_level)
                if account_qty < min_stock_level:
                    state = _('Under level')
                elif account_qty < 0:
                    state = _('Negative')
                else:
                    state = _('OK')

                line = [
                    self.get_type(product.default_code, product.uom_id.name),
                    default_code or '',
                    product.name or '',
                    product.uom_id.name or '',

                    (product.approx_integer, excel_format['right']),
                    product.approx_mode or '',

                    (product.manual_stock_level or '', excel_format['right']),
                    product.day_leadtime or '',
                    (int(product.medium_stock_qty), excel_format['right']),

                    (product.day_min_level, excel_format['right']),
                    (min_stock_level, excel_format['right']),

                    (product.day_max_level, excel_format['right']),
                    (int(product.max_stock_level), excel_format['right']),

                    (account_qty, excel_format['right']),
                    state,
                    ]

                excel_pool.write_xls_line(
                    ws_name, row, line, default_format=excel_format['text'])
                row += 1
        return excel_pool.return_attachment(
            cr, uid, 'Livelli prodotto MX', 'stock_level_MX.xlsx',
            version='7.0', php=True, context=context)
