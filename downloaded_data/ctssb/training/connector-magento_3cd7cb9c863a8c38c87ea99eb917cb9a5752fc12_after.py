#########################################################################
#This module intergrates Open ERP with the magento core                 #
#Core settings are stored here                                          #
#########################################################################
#                                                                       #
# Copyright (C) 2009  Sharoon Thomas                                    #
#                                                                       #
#This program is free software: you can redistribute it and/or modify   #
#it under the terms of the GNU General Public License as published by   #
#the Free Software Foundation, either version 3 of the License, or      #
#(at your option) any later version.                                    #
#                                                                       #
#This program is distributed in the hope that it will be useful,        #
#but WITHOUT ANY WARRANTY; without even the implied warranty of         #
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the          #
#GNU General Public License for more details.                           #
#                                                                       #
#You should have received a copy of the GNU General Public License      #
#along with this program.  If not, see <http://www.gnu.org/licenses/>.  #
#########################################################################

from osv import osv, fields
import magerp_osv
from base_external_referentials import external_osv

DEBUG = True
TIMEOUT = 2
        
class external_referential(magerp_osv.magerp_osv):
    #This class stores instances of magento to which the ERP will connect, the concept of multi website, multistore integration?
    _inherit = "external.referential"

    _columns = {
        'attribute_sets':fields.one2many('magerp.product_attribute_set', 'instance', 'Attribute Sets'),
        'default_pro_cat':fields.many2one('product.category','Default Product Category',required=True, help="Products imported from magento may have many categories.\nOpen ERP requires a specific category for a product to facilitate invoicing etc.")
    }

                
             
    def connect(self, cr, uid, ids, ctx={}):#TODO used?
        #ids has to be a list
        if ids:
            if len(ids) == 1:
                instance = self.browse(cr, uid, ids, ctx)[0]
                if instance:
                    core_imp_conn = self.external_connection(cr, uid, instance, DEBUG)
                    if core_imp_conn.connect():
                        return core_imp_conn
        return False

    def core_sync(self, cr, uid, ids, ctx={}):
        instances = self.browse(cr, uid, ids, ctx)
        filter = []
        for inst in instances:
            core_imp_conn = self.external_connection(cr, uid, inst, DEBUG)
            if core_imp_conn:
                #New import methods
                self.pool.get('external.shop.group').mage_import_base(cr, uid,core_imp_conn, inst.id)
                self.pool.get('magerp.storeviews').mage_import_base(cr,uid,core_imp_conn, inst.id)
                self.pool.get('sale.shop').mage_import_base(cr, uid, core_imp_conn, inst.id)
            else:
                osv.except_osv(_("Connection Error"), _("Could not connect to server\nCheck location, username & password."))
    
    def sync_categs(self, cr, uid, ids, ctx):
        instances = self.browse(cr, uid, ids, ctx)
        for inst in instances:
            pro_cat_conn = self.external_connection(cr, uid, inst, DEBUG)
            if pro_cat_conn:
                confirmation = pro_cat_conn.call('catalog_category.currentStore', [0])   #Set browse to root store
                if confirmation:
                    categ_tree = pro_cat_conn.call('catalog_category.tree')             #Get the tree
                    self.pool.get('product.category').record_entire_tree(cr, uid, inst.id, pro_cat_conn, categ_tree, DEBUG)
                    exp_ids = self.pool.get('product.category').search(cr,uid,[('exportable','=',True)])
                    self.pool.get('product.category').ext_export(cr,uid,exp_ids,[inst.id],{},{'conn_obj':pro_cat_conn})
            else:
                osv.except_osv(_("Connection Error"), _("Could not connect to server\nCheck location, username & password."))
    
    def sync_attribs(self, cr, uid, ids, ctx):
        instances = self.browse(cr, uid, ids, ctx)
        for inst in instances:
            attr_conn = self.external_connection(cr, uid, inst, DEBUG)
            if attr_conn:
                attrib_set_ids = self.pool.get('magerp.product_attribute_set').search(cr, uid, [('instance', '=', inst.id)])
                attrib_sets = self.pool.get('magerp.product_attribute_set').read(cr, uid, attrib_set_ids, ['magento_id'])
                #Get all attribute set ids to get all attributes in one go
                all_attr_set_ids = self.pool.get('magerp.product_attribute_set').get_all_mage_ids(cr, uid, [], inst.id)
                #Call magento for all attributes
                mage_inp = attr_conn.call('ol_catalog_product_attribute.list', all_attr_set_ids)             #Get the tree
                #self.pool.get('magerp.product_attributes').sync_import(cr, uid, mage_inp, inst.id, DEBUG) #Last argument is extra mage2oe filter as same attribute ids
                self.pool.get('magerp.product_attributes').ext_import(cr, uid, mage_inp, inst.id, defaults={'instance':inst.id}, context={'referential_id':inst.id})
                #Relate attribute sets & attributes
                mage_inp = {}
                #Pass in {attribute_set_id:{attributes},attribute_set_id2:{attributes}}
                #print "Attribute sets are:", attrib_sets
                for each in attrib_sets:
                    mage_inp[each['magento_id']] = attr_conn.call('ol_catalog_product_attribute.relations', [each['magento_id']])
                if mage_inp:
                    self.pool.get('magerp.product_attribute_set').relate(cr, uid, mage_inp, inst.id, DEBUG)
            else:
                osv.except_osv(_("Connection Error"), _("Could not connect to server\nCheck location, username & password."))
            
                
    
    def sync_attrib_sets(self, cr, uid, ids, ctx):
        instances = self.browse(cr, uid, ids, ctx)
        for inst in instances:
            attr_conn = self.external_connection(cr, uid, inst, DEBUG)
            if attr_conn:
                filter = []
                #self.pool.get('magerp.product_attribute_set').mage_import(cr, uid, filter, attr_conn, inst.id, DEBUG)
                self.pool.get('magerp.product_attribute_set').mage_import_base(cr, uid, attr_conn, inst.id,{'instance':inst.id},{'ids_or_filter':filter})
            else:
                osv.except_osv(_("Connection Error"), _("Could not connect to server\nCheck location, username & password."))          
    
    def sync_attrib_groups(self, cr, uid, ids, ctx):
        instances = self.browse(cr, uid, ids, ctx)
        for inst in instances:
            attr_conn = self.external_connection(cr, uid, inst, DEBUG)
            attrset_ids = self.pool.get('magerp.product_attribute_set').get_all_mage_ids(cr, uid, [], inst.id)
            filter = [{'attribute_set_id':{'in':attrset_ids}}]
            if attr_conn:
                #self.pool.get('magerp.product_attribute_groups').mage_import(cr, uid, filter, attr_conn, inst.id, DEBUG)
                self.pool.get('magerp.product_attribute_groups').mage_import_base(cr, uid, attr_conn, inst.id, {'instance':inst.id}, {'ids_or_filter':filter})
            else:
                osv.except_osv(_("Connection Error"), _("Could not connect to server\nCheck location, username & password."))
    
    def sync_customer_groups(self, cr, uid, ids, ctx):
        instances = self.browse(cr, uid, ids, ctx)
        for inst in instances:
            attr_conn = self.external_connection(cr, uid, inst, DEBUG)
            filter = []
            if attr_conn:
                self.pool.get('res.partner.category').mage_import(cr, uid, filter, attr_conn, inst.id, DEBUG)
            else:
                osv.except_osv(_("Connection Error"), _("Could not connect to server\nCheck location, username & password."))
    
    def sync_customer_addresses(self, cr, uid, ids, ctx):
        instances = self.browse(cr, uid, ids, ctx)
        for inst in instances:
            attr_conn = self.external_connection(cr, uid, inst, DEBUG)
            filter = []
            if attr_conn:
                self.pool.get('res.partner').mage_import(cr, uid, filter, attr_conn, inst.id, DEBUG)
            else:
                osv.except_osv(_("Connection Error"), _("Could not connect to server\nCheck location, username & password."))
    
    def sync_products(self, cr, uid, ids, ctx):
        instances = self.browse(cr, uid, ids, ctx)
        for inst in instances:
            attr_conn = self.external_connection(cr, uid, inst, DEBUG)
            filter = []
            if attr_conn:
                list_prods = attr_conn.call('catalog_product.list')
                #self.pool.get('product.product').mage_import(cr, uid, filter, attr_conn, inst.id, DEBUG)
                result = []
                for each in list_prods:
                    each_product_info = attr_conn.call('catalog_product.info', [each['product_id']])
                    result.append(each_product_info)
                self.pool.get('product.product').ext_import(cr, uid, result, inst.id, defaults={'instance':inst.id,'categ_id':inst.default_pro_cat.id}, context={})
            else:
                osv.except_osv(_("Connection Error"), _("Could not connect to server\nCheck location, username & password."))                        
    def redefine_prod_view(self,cr,uid,ids,ctx):
        #This function will rebuild the view for product from instances, attribute groups etc
        #Get all objects needed
        inst_obj = self.pool.get('external.referential')
        attr_set_obj = self.pool.get('magerp.product_attribute_set')
        attr_group_obj = self.pool.get('magerp.product_attribute_group')
        attr_obj = self.pool.get('magerp.product_attributes')
        #Predefined items on top
        #Instance
        #Attribute Set
        #Get all instances
        inst_ids = inst_obj.search(cr,uid,[])#TODO:Search for active instances only
        instances = inst_obj.read(cr,uid,inst_ids,[])
        for each_instance in instances:
            #create a group & a notebook inside, group attr
            attr_set_ids = attr_set_obj.search(cr,uid,[('instance','=',each_instance['id'])])
            attr_sets = attr_set_obj.browse(cr,uid,attr_set_ids)
            for each_set in attr_sets:
                #Create a page with attrs corresponding to the set id
                attr_grp_ids = attr_group_obj.search(cr,uid,[('attribute_set','=',each_set['id'])]) #attribute_set is a function field, may slow down the whole thing
                attr_groups = attr_group_obj.read(cr,uid,attr_grp_ids,[])
                for each_group in attr_groups:
                    #Create a page for the attribute group
                    attribute_ids = each_set.attributes
                    attr
                
    def export_products(self, cr, uid, ids, ctx):
        instances = self.browse(cr, uid, ids, ctx)
        for inst in instances:
            attr_conn = self.external_connection(cr, uid, inst, DEBUG)
            if attr_conn:
                ids = self.pool.get('product.product').search(cr, uid, [])
                self.pool.get('product.product').mage_export(cr, uid, ids, attr_conn, inst.id, DEBUG)
            else:
                osv.except_osv(_("Connection Error"), _("Could not connect to server\nCheck location, username & password."))                        


                                
external_referential()

class external_shop_group(magerp_osv.magerp_osv):
    _inherit = "external.shop.group"
    #Return format of API:{'code': 'base', 'name': 'Main', 'website_id': '1', 'is_default': '1', 'sort_order': '0', 'default_group_id': '1'}
            
    def _get_group(self, cr, uid, ids, prop, unknow_none, context):
        res = self.group_get(cr, uid, ids, context={'field':'default_group_id'})
        return dict(res)        

    _order = 'magento_id'
    
    _columns = {
        'code':fields.char('Code', size=100),
        'magento_id':fields.integer('Website ID'),
        'is_default':fields.boolean('Is Active?'),
        'sort_order':fields.integer('Sort Order'),
        'default_group_id':fields.integer('Default Store Group'), #Many 2 one?
        'default_group':fields.function(_get_group, type="many2one", relation="sale.shop", method=True, string="Default Store (Group)"),
        'instance':fields.many2one('external.referential', 'Instance', ondelete='cascade')
    }


external_shop_group()

class magerp_storeviews(magerp_osv.magerp_osv):
    _name = "magerp.storeviews"
    _description = "The magento store views information"
       
    def _get_website(self, cr, uid, ids, prop, unknow_none, context):
        res = self.website_get(cr, uid, ids, context={'field':'magento_id'})
        return dict(res)
    
    def _get_group(self, cr, uid, ids, prop, unknow_none, context):
        res = self.group_get(cr, uid, ids, context={'field':'group_id'})
        return dict(res) 
    
    _order = 'magento_id'
    _LIST_METHOD = 'ol_storeviews.list'
    _MAGE_P_KEY = 'store_id'
    _columns = {
        'name':fields.char('Store View Name', size=100),
        'code':fields.char('Code', size=100),
        'magento_id':fields.integer('Store ID'),
        'website_id':fields.integer('Website'), # Many 2 one ?
        'website':fields.function(_get_website, type="many2one", relation="external.shop.group", method=True, string="Website"),
        'is_active':fields.boolean('Default ?'),
        'sort_order':fields.integer('Sort Order'),
        'group_id':fields.integer('Default Store Group'), #Many 2 one?
        'default_group':fields.function(_get_group, type="many2one", relation="sale.shop", method=True, string="Default Store (Group)"),
        #'instance':fields.many2one('external.referential', 'Instance', ondelete='cascade')
    }

    #Return format of API:{'code': 'default', 'store_id': '1', 'website_id': '1', 'is_active': '1', 'sort_order': '0', 'group_id': '1', 'name': 'Default Store View'}


magerp_storeviews()