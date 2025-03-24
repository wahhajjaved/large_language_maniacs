# Ce module possede des methodes generiques pour transmettre un message declencheur (trigger) par RabbitMQ.
from millegrilles.dao.Configuration import TransactionConfiguration
from millegrilles.dao.MessageDAO import PikaDAO


# Classe qui possede des methodes pour transmettre un message declencheur.
class Declencheur:

    def __init__(self):
        self.configuration = TransactionConfiguration()
        self.configuration.loadEnvironment()
        self.message_dao = PikaDAO(self.configuration)
        self.message_dao.connecter()

    '''
    Transmet un message via l'echange MilleGrilles pour un domaine specifique
    
    :param domaine: Domaine millegrilles    
    '''
    def transmettre_declencheur_domaine(self, domaine, dict_message):
        nom_millegrille = self.configuration.nom_millegrille
        routing_key = '%s.destinataire.domaine.%s' % (nom_millegrille, domaine)
        self.message_dao.transmettre_message(dict_message, routing_key)
