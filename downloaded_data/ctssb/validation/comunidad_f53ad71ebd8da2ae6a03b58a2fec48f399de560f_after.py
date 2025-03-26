
from openerp import fields, models, exceptions, api, _
import base64
import csv
import cStringIO


class ImportInventory(models.TransientModel):
    _name = 'import.inventory'
    _description = 'Import inventory'

    def _get_default_location(self):
        ctx = self._context
        if 'active_id' in ctx:
            inventory_obj = self.env['stock.inventory']
            inventory = inventory_obj.browse(ctx['active_id'])
        return inventory.location_id

    data = fields.Binary('File', required=True)
    name = fields.Char('Filename')
    delimeter = fields.Char('Delimeter', default=',',
                            help='Default delimeter is ","')
    location = fields.Many2one('stock.location', 'Default Location',
                               default=_get_default_location, required=True)

    def _find_product(self, value):
        if not value:
            return False
        product_obj = self.env['product.product']
        prod_lst = product_obj.search(['|', '|',
                                       ('default_code', '=', value),
                                       ('default_code', '=', value.upper()),
                                       ('default_code', '=', value.lower())
                                       ])
        if not prod_lst:
            #Busca por el nombre
            self._cr.execute("""
                SELECT  id
                FROM    product_product
                WHERE   trim(both ' ' from lower(name_template)) = %s
                        and active is true
            """, (value.lower(), ))
            res = self._cr.fetchall()
            prod_lst = product_obj.browse(res[0][0]) if res and len(res) == 1 else False
        return prod_lst

    def _get_keys(self):
        if not self.data:
            raise exceptions.Warning(_("You need to select a file!"))
        # Decode the file data
        data = base64.b64decode(self.data)
        file_input = cStringIO.StringIO(data)
        file_input.seek(0)
        reader_info = []
        if self.delimeter:
            delimeter = str(self.delimeter)
        else:
            delimeter = ','
        reader = csv.reader(file_input, delimiter=delimeter,
                            lineterminator='\r\n')
        try:
            reader_info.extend(reader)
        except Exception:
            raise exceptions.Warning(_("Not a valid file!"))
        # Convierte a minuscuilas
        keys = map(lambda x: x.lower(), reader_info[0])
        return keys, reader_info

    def _get_values(self, keys, field):
        ctx = self._context
        inventory_obj = self.env['stock.inventory']
        if 'active_id' in ctx:
            inventory = inventory_obj.browse(ctx['active_id'])
        val = {}
        values = dict(zip(keys, field))
        location = self.location
        prod_location = location.id
        if 'location' in values and values['location']:
            locations = stloc_obj.search([('name', '=',
                                           values['location'])])
            prod_location = locations[:1].id
        # Se reemplaza por funcion
        # prod_lst = product_obj.search([('default_code', '=',
        #                                values['code'])])
        prod_lst = self._find_product(values['codigo'])
        if prod_lst:
            val['product'] = prod_lst[0].id
        if 'lot' in values and values['lot']:
            val['lot'] = values['lot']
        val['code'] = values['codigo']
        val['quantity'] = values['cantidad'].strip()
        val['location_id'] = prod_location
        val['inventory_id'] = inventory.id
        val['fail'] = True
        val['fail_reason'] = _('No processed')
        return val

    def _valida_campos(self, keys):
        # check if keys exist
        if not isinstance(keys, list) or ('codigo' not in keys or
                                                  'cantidad' not in keys):
            raise exceptions.Warning(_("No se encontro las columnas codigo o cantidad en el archivo"))

    @api.one
    def action_import(self):
        """Load Inventory data from the CSV file."""
        ctx = self._context
        inventory_obj = self.env['stock.inventory']
        inv_imporline_obj = self.env['stock.inventory.import.line']
        if 'active_id' in ctx:
            inventory = inventory_obj.browse(ctx['active_id'])
        keys, reader_info = self._get_keys()
        self._valida_campos(keys)
        del reader_info[0]
        values = {}
        actual_date = fields.Date.today()
        inv_name = self.name + ' - ' + actual_date
        inventory.write({'name': inv_name,
                         'date': fields.Datetime.now(),
                         'imported': True, 'state': 'confirm'})
        for i in range(len(reader_info)):
            val = self._get_values(keys, reader_info[i])
            inv_imporline_obj.create(val)

class StockInventoryImportLine(models.Model):
    _name = "stock.inventory.import.line"
    _description = "Stock Inventory Import Line"

    code = fields.Char('Product Code')
    product = fields.Many2one('product.product', 'Found Product')
    quantity = fields.Float('Quantity')
    inventory_id = fields.Many2one('stock.inventory', 'Inventory',
                                   readonly=True)
    location_id = fields.Many2one('stock.location', 'Location')
    lot = fields.Char('Product Lot')
    fail = fields.Boolean('Fail')
    fail_reason = fields.Char('Fail Reason')
