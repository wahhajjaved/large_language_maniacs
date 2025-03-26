import datetime

from domain.shared.service import Service
from domain.model.delivery.delivery import Delivery


class DeliveryService(Service):
    """
    Domain service which creates deliveries and their documentation from orders.
    """

    def __init__(self, customer_repository, order_repository, inventory_repository):
        self.customer_repository = customer_repository
        self.order_repository = order_repository
        self.inventory_repository = inventory_repository

    def create_delivery(self, customer, order_ids):

        if not self.customer_repository.find(customer):
            raise ValueError("Cannot find specified customer for delivery")

        delivery = Delivery(None, customer, datetime.datetime.now())

        for order_id in order_ids:
            order = self.order_repository.find(order_id)

            for line_item in order.line_items:
                inventory_item = self.inventory_repository.find(line_item.sku)
                commitments = inventory_item.find_committed_for_order(order_id)

                for (_, warehouse), item in commitments:
                    if inventory_item.committed.get_unverified(warehouse):
                        raise DeliveryError("Cannot create delivery from unverified order")

                    delivery.add_item(line_item.sku, item.quantity, warehouse, item.order_id)

        return delivery


class DeliveryError(Exception):
    """
    A generic exception which is thrown when delivery creation fails.
    """
    pass
