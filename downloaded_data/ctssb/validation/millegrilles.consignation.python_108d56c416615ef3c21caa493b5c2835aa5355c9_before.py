# Gestion des documents.
import ssl
import logging

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from bson.objectid import ObjectId
from millegrilles import Constantes
from millegrilles.dao.TransactionDocumentHelper import TransactionHelper
from millegrilles.dao.ProcessusDocumentHelper import ProcessusHelper

'''
Data access object pour les documents dans MongoDB
'''


class MongoDAO:

    def __init__(self, configuration):
        self._configuration = configuration
        self._nom_millegrille = "mg-%s" % self._configuration.nom_millegrille

        self._client = None
        self._mg_database = None
        self._collection_transactions = None
        self._collection_processus = None
        self._collection_information_documents = None
        self._transaction_document_helper = None
        self._processus_document_helper = None

    @staticmethod
    def _use_cert(ssl_option):
        if ssl_option == "nocert":
            return ssl.CERT_NONE
        elif ssl_option == 'on':
            return ssl.CERT_REQUIRED
        else:
            return None

    def connecter(self):
        ssl_option = self._configuration.mongo_ssl

        if ssl_option == "off" or "on":
            self._client = MongoClient(
                self._configuration.mongo_host,
                self._configuration.mongo_port,
                username=self._configuration.mongo_user,
                password=self._configuration.mongo_password,
                ssl=(ssl_option == "on" or ssl_option == "nocert"),
                ssl_cert_reqs=MongoDAO._use_cert(ssl_option)
            )

        logging.debug("Verify if connection established")
        self._client.admin.command('ismaster')

        logging.info("Connection etablie, ouverture base de donnes %s" % self.nom_millegrille)

        self._mg_database = self._client[self._nom_millegrille]
        self._collection_transactions = self._mg_database[Constantes.DOCUMENT_COLLECTION_TRANSACTIONS]
        self._collection_processus = self._mg_database[Constantes.DOCUMENT_COLLECTION_PROCESSUS]
        self._collection_information_documents = self._mg_database[Constantes.DOCUMENT_COLLECTION_INFORMATION_DOCUMENTS]

        # Generer les classes Helper
        self._transaction_document_helper = TransactionHelper(self._mg_database)
        self._processus_document_helper = ProcessusHelper(self._mg_database)

    def deconnecter(self):
        if self._client is not None:
            client = self._client

            self._mg_database = None
            self._collection_transactions = None
            self._collection_processus = None
            self._collection_information_documents = None
            self._transaction_document_helper = None
            self._processus_document_helper = None

            client.close()

    '''
    Utiliser pour verifier si la connexion a Mongo fonctionne
    
    :returns: True si la connexion est live, False sinon.
    '''
    def est_enligne(self):
        if self._client is None:
            return False

        try:
            # The ismaster command is cheap and does not require auth.
            self._client.admin.command('ismaster')
            return True
        except ConnectionFailure:
            logging.info("Server not available")
            return False

    '''
    Chargement d'un document de transaction a partir d'un identificateur MongoDB
    
    :param id_doc: Numero unique du document dans MongoDB.
    :returns: Document ou None si aucun document ne correspond.
    '''
    def charger_transaction_par_id(self, id_doc):
        if not isinstance(id_doc, ObjectId):
            id_doc = ObjectId(id_doc)
        return self._collection_transactions.find_one({Constantes.MONGO_DOC_ID: id_doc})

    def charger_processus_par_id(self, id_doc):
        return self._collection_processus.find_one({Constantes.MONGO_DOC_ID: ObjectId(id_doc)})

    def transaction_helper(self):
        return self._transaction_document_helper

    def processus_helper(self):
        return self._processus_document_helper

    def get_collection(self, collection):
        return self._mg_database[collection]
