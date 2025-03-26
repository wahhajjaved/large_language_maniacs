
# geocoding


from zope import interface, component

from getpaid.core.interfaces import IStoreSettings, IShippableLineItem, IOrder, IOriginRouter
from getpaid.core.payment import ContactInformation

import interfaces

class OriginRouter( object ):
    
    " warehouse aware origin router "
    
    component.adapts( IOrder )
    
    interface.implements( IOriginRouter )
    
    def __init__( self, context ):
        self.context = context

    def getOrigin( self ):
        warehouses = self.getOrderWarehouses()
        if not warehouses:
            fallback_router = component.getAdapter( self.context, IOriginRouter, name="default" )
            return fallback_router.getOrigin()
        assert len(warehouses) == 1, "only origin warehouse allowed per order, atm"
        warehouse = warehouses.pop()
        contact = self.getStoreContact()
        contact.name = warehouse.name
        return contact, warehouse.location
        
    def getOrderWarehouses( self ):
        items = filter( IShippableLineItem.providedBy, self.context.shopping_cart.values())
        if not items:
            return
            
        warehouse_names = set()
        for i in items:
            shippable = i.resolve()
            if shippable is None:
                continue
            inventory = interfaces.IProductInventory( shippable )
            warehouse_names.add( inventory.warehouse )
        
        container = component.getUtility( interfaces.IWarehouseContainer )
        return filter( None, map( container.get, warehouse_names ) )
        
    def getStoreContact( self ):
        store_settings = component.getUtility( IStoreSettings )
        contact = ContactInformation( name = ( store_settings.contact_company or store_settings.store_name ),
                                      phone_number = store_settings.contact_phone,
                                      email = store_settings.contact_email )
        return contact
