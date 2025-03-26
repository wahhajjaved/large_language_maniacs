import parsing
import sys
from datetime import datetime
module = sys.modules[__name__]

update_key = 'last_updated'
city = 'city'
zip = 'zip'
lines = 'lines'

parser = parsing.Parser()

def string(string, key):
    return string

class NaviObject():

    def get_atts(self):
        return self.__dict__

    def format(self, line, city_zip=False):
        obj = {}
        for k, vals in self.get_atts().iteritems():
            v, trans = vals[0], vals[1]
            rest = vals[2] if len(vals) == 3 else {}

            if city_zip and k == 'city_zip':
                obj[zip], obj[city] = parser.get_city(line[self.city_zip[0]], line[self.key[0]], **rest)
                continue
            obj[k] = trans(line[v], line[self.key[0]], **rest)

        obj[update_key] = datetime.utcnow()
        #obj[.zip_code, self.city = parser.get_city(line[self.city_zip[0]], line[self.key[0]])
        return obj



class Deptor(NaviObject):

    def __init__(self):
        self.key = (0, string)
        self.name  = (1, string)
        self.search_name  = (2, string)
        self.address = (4, string)
        self.city_zip = (6, string)
        self.attention = (7, string)
        self.phone = (8, string)
        self.fax = (79, string)
        self.email = (89, parser.get_email)

class Creditor(NaviObject):

    def __init__(self):
        self.key = (0, string)
        self.name  = (1, string)
        self.address = (4, string)
        self.city_zip = (6, string)
        self.attention = (7, string)
        self.phone = (8, string)
        self.fax = (62, string)


class Item(NaviObject):

    def __init__(self):
        self.key = (0, string)
        self.name  = (2, string)
        self.cost_price = (20, parser.get_price)
        self.price = (16, parser.get_price)
        self.price_1 = (74, parser.get_price)
        self.price_2 = (75, parser.get_price)
        self.price_3 = (97, parser.get_price)
        self.price_4 = (98, parser.get_price)
        self.inner_box = (76, parser.get_qty)
        self.outer_box = (77, parser.get_qty)
        self.quantity = (78, parser.get_qty)
        self.ean = (81, string)
        self.group = (108, string)

class SalesInvCredLine(NaviObject):

    def __init__(self):
        self.key = (1, string)
        self.item_number = (4, string)
        self.info = (9, string)
        self.quantity = (12, parser.get_qty)
        self.price = (13, parser.get_price)
        self.total_without_tax = (20, parser.get_price)
        self.total_with_tax = (21, parser.get_price)
        self.ean = (42, string)

class SalesInvoice(NaviObject):

    def __init__(self):
        self.customer_number = (0, string)
        self.key = (1, string)
        self.name = (3, string)
        self.name_1 = (4, string)
        self.address = (5, string)
        self.address_1 = (6, string)
        self.city_zip = (7, string, { 'log': False })
        self.attention = (8, string)
        self.order_date = (17, parser.get_date, { 'log': False })
        self.posting_date = (18, parser.get_date)
        self.total_with_tax = (68, parser.get_price)
        self.edi = (72, string)
        self.customer_order_number = (76, string)

class SalesCreditNota(NaviObject):

    def __init__(self):
        self.customer_number = (0, string)
        self.key = (1, string)
        self.name = (3, string)
        self.name_1 = (4, string)
        self.address = (5, string)
        self.address_1 = (6, string)
        self.city_zip = (7, string, { 'log': False })
        self.attention = (8, string)
        self.posting_date = (17, parser.get_date)
        self.total_with_tax = (68, parser.get_price)
        self.edi = (72, string)
        self.customer_order_number = (76, string)
