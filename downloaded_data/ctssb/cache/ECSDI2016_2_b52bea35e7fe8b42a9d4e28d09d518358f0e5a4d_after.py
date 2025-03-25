import random

from rdflib import Graph
from rdflib.namespace import FOAF

from ecsdiLAB.ecsdimazon.controllers import Constants
from ecsdiLAB.ecsdimazon.controllers.AgentUtil import *
from ecsdiLAB.ecsdimazon.messages import Ontologies, FIPAACLPerformatives


class AgentSender:
    def __init__(self, sender, directory_uri):
        self.sender = sender
        self.min_price_per_kilo = 2.0
        self.max_price_per_kilo = 5.0
        self.__routings__ = {
            Ontologies.SENDERS_SEND_PRODUCT_REQUEST: self.send_products,
            Ontologies.SENDERS_NEGOTIATION_REQUEST: self.negotiate,
            Ontologies.SENDERS_PRICE_REQUEST: self.default_price
        }
        self.__ensure_registered__(directory_uri)

    def __ensure_registered__(self, directory_uri):
        import requests
        ontology = Ontologies.SENDERS_REGISTER_REQUEST
        performative = FIPAACLPerformatives.REQUEST
        graph = self.sender.to_graph()
        r = requests.post(directory_uri+"/comm", data=build_message(graph, performative, ontology).serialize())
        print "Register response was {}".format(r.text)
        response_performative = performative_of_message(Graph().parse(data=r.text))
        if response_performative == FIPAACLPerformatives.AGREE:
            print "Successfully registered agent."
        else:
            print "Agent not successfully registered. Response Performative was {}".format(response_performative)
            exit(-1)

    def comm(self, ontology, graph):
        if self.__routings__.get(ontology):
            return self.__routings__[ontology](graph).serialize()
        else:
            return build_message(Graph(), FIPAACLPerformatives.NOT_UNDERSTOOD, Ontologies.UNKNOWN_ONTOLOGY).serialize()

    def send_products(self, graph):
        ontology = Ontologies.SENDERS_SEND_PRODUCT_RESPONSE
        performative = FIPAACLPerformatives.AGREE
        price = self.__total_price__(graph)
        graph = Graph()
        n = Namespace(Constants.NAMESPACE)
        graph.add((n.__getattr__('#ProductSending#' + str(uuid.uuid4())), FOAF.TotalPrice, Literal(price)))
        return build_message(graph, performative, ontology)

    def negotiate(self, graph):
        query = """SELECT ?x ?pricePerKilo
            WHERE {{
                ?x ns1:PricePerKilo ?pricePerKilo.
            }}
            """
        qres = graph.query(query)
        for x, wanted_price_per_kilo in qres:
            ontology = Ontologies.SENDERS_NEGOTIATION_RESPONSE
            if wanted_price_per_kilo < self.min_price_per_kilo:
                performative = FIPAACLPerformatives.REFUSE
                return build_message(Graph(), performative, ontology)
            else:
                performative = FIPAACLPerformatives.AGREE
                return build_message(Graph(), performative, ontology)

    def default_price(self, graph):
        ontology = Ontologies.SENDERS_PRICE_RESPONSE
        performative = FIPAACLPerformatives.INFORM
        graph = self.__price_graph__(
            random.choice([  # either something random between the two boundaries or exactly the middle
                random.uniform(self.min_price_per_kilo, self.max_price_per_kilo),
                (self.max_price_per_kilo + self.min_price_per_kilo) / 2
            ]))
        return build_message(graph, performative, ontology)

    def __price_graph__(self, price):
        graph = Graph()
        n = Namespace(Constants.NAMESPACE)
        graph.add((n.__getattr__('#Sender#' + self.sender.name), FOAF.PricePerKilo, Literal(price)))
        return graph

    def __total_price__(self, graph):
        total_weight = 0
        for s, p, o in graph.triples((None, FOAF.Weight, None)):
            total_weight += o.toPython()
        for s, p, o in graph.triples((None, FOAF.AgreedPrice, None)):
            return total_weight * o.toPython()
