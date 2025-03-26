from sqlalchemy.orm import session
from zope import component
from zope.app.intid.interfaces import IIntIds

import domain, sync

def handleInventoryModified( _inventory, event ):
    """
    when an inventory is modified, we record inventory adjustments to the database
    """
    def _( s ):
        entry = domain.InventoryEntry()

        # fetch the db product 
        iid = component.getUtility( IIntIds ).queryId( event.product )
        product = s.query( domain.Product ).filter(
            domain.Product.content_uid == iid ).first()
        
        if product is None:
            product = domain.Product()
            sync.copyProduct( event.product, product, uid=iid )
        else:
            sync.copyProductInventory( _inventory, product )
            
        entry.product = product
        entry.quantity = event.stock_delta
        entry.action = u"added"
        entry.stock = _inventory.stock
        return entry
    
    return _interact( _ )

def handleInventoryOrderModified( _inventory, event ):
    """
    when an order is fufilled, we record inventory levels of products
    items to the database. the event is generated per product.
    """
    
    def _( s ):
        entry = domain.InventoryEntry()

        # fetch the db product 
        iid = component.getUtility( IIntIds ).queryId( event.product )
        product = s.query( domain.Product ).filter(
            domain.Product.content_uid == iid ).first()

        # really, product should already exist at this point
        # for a fresh install, we do this to play nice for plugin
        # installs into legacy
        if product is None:
            product = domain.Product()
            sync.copyProduct( product, event.product, uid=iid )        
        else:
            sync.copyProductInventory( _inventory, product )
            
        order = s.query( domain.Order ).filter(
            domain.Order.order_zid == event.order.order_id ).first()
        
        entry.product = product
        entry.order = order
        entry.quantity = -event.stock_delta
        entry.stock = _inventory.stock
        entry.action = u"delivered"

        return entry
    
    return _interact( _ )
    
def handleOrderTransition( _order, event ):
    """
    when an order is transition, we record the state changes to the database
    """
    def _( s ):
        order = s.query( domain.Order ).filter(
            domain.Order.order_zid == _order.order_id ).first()
        if order is None:
            return
        sync.copyState( _order, order )
        return order
    return _interact( _ )
        
def handleNewOrder( _order, event ):
    """
    when a new order is created, we serialize it do the database.
    """
    def _( s ):
        order = domain.Order()
        sync.copyOrder( s, _order, order )
        return order
    return _interact( _ )

def _interact( func ):
    s = session.Session()
    s.begin()

    try:
        value = func( s )
    except:
        s.rollback()
        raise
    else:
        if value is not None:
            s.save_or_update( value )
        s.commit()
    return value
