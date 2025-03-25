from rdflib import Graph, Literal
from rdflib.namespace import Namespace, FOAF

from ecsdiLAB.ecsdimazon.controllers import Constants
from ecsdiLAB.ecsdimazon.model.BoughtProduct import BoughtProduct
from ecsdiLAB.ecsdimazon.model.Product import Product

from ecsdiLAB.ecsdimazon.model.User import User


class SendProductsMessage:
    def __init__(self, bought_products):
        self.bought_products = bought_products

    def to_graph(self):
        graph = Graph()
        n = Namespace(Constants.NAMESPACE)
        for bought_product in self.bought_products:
            p = n.__getattr__('#BoughtProduct#' + str(bought_product.uuid))
            graph.add((p, FOAF.Uuid, Literal(bought_product.uuid)))
            graph.add((p, FOAF.EAN, Literal(bought_product.product.ean)))
            graph.add((p, FOAF.Name, Literal(bought_product.product.name)))
            graph.add((p, FOAF.Brand, n.__getattr__('#Brand#' + str(bought_product.product.brand.name))))
            graph.add((p, FOAF.Price, Literal(bought_product.product.price)))
            graph.add((p, FOAF.Weight, Literal(bought_product.product.weight)))
            graph.add((p, FOAF.Height, Literal(bought_product.product.height)))
            graph.add((p, FOAF.Width, Literal(bought_product.product.width)))
            graph.add((p, FOAF.Purcahser, Literal(bought_product.purchaser.username)))
            graph.add((p, FOAF.SendTo, Literal(bought_product.purchaser.direction)))
            graph.add((p, FOAF.Payment, Literal(bought_product.payment)))
            graph.add((p, FOAF.Priority, Literal(bought_product.priority)))
            graph.add((p, FOAF.Seller, n.__getattr__('#Seller#' + str(bought_product.product.seller.name))))
        return graph

    @classmethod
    def list_to_graph(cls, spms):
        graph = Graph()
        for spm in spms:
            graph = graph + spm.to_graph()
        return graph

    @classmethod
    def from_graph(cls, graph):
        query = """SELECT ?x ?uuid ?ean ?name ?brand ?price ?weight ?height ?width ?seller ?purchaser ?send ?priority ?payment
            WHERE {
                ?x ns1:Uuid ?uuid.
                ?x ns1:EAN ?ean.
                ?x ns1:EAN ?ean.
                ?x ns1:Name ?name.
                ?x ns1:Brand ?brand.
                ?x ns1:Weight ?weight.
                ?x ns1:Height ?height.
                ?x ns1:Width ?width.
                ?x ns1:Seller ?seller.
                ?x ns1:Purchaser ?purchaser.
                ?x ns1:SendTo ?send.
                ?x ns1:Priority ?priority.
                ?x ns1:Payment ?payment.
            }
        """
        qres = graph.query(query)
        search_res = []
        for p, uuid, ean, name, brand, price, weight, height, width, seller, purchaser, send, priority, payment in qres:
            bought_product = BoughtProduct(uuid, Product(ean, name, brand, price, weight, height, width, seller),
                                           purchaser, priority, payment)
            search_res.append(bought_product)
        pm = SendProductsMessage(search_res)
        return pm
