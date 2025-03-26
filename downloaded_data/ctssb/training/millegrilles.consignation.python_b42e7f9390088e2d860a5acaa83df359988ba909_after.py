# Module avec utilitaires generiques pour mgdomaines
from millegrilles import Constantes
from millegrilles.dao.MessageDAO import JSONHelper, TraitementMessageDomaine, \
    TraitementMessageDomaineMiddleware, TraitementMessageDomaineRequete, TraitementMessageCedule
from millegrilles.dao.DocumentDAO import MongoJSONEncoder
from millegrilles.MGProcessus import MGPProcessusDemarreur, MGPProcesseurTraitementEvenements, MGPProcesseurRegeneration
from millegrilles.util.UtilScriptLigneCommande import ModeleConfiguration
from millegrilles.dao.Configuration import ContexteRessourcesMilleGrilles
from millegrilles.transaction.ConsignateurTransaction import ConsignateurTransactionCallback
from millegrilles.SecuritePKI import GestionnaireEvenementsCertificat

import logging
import json
import datetime

from pika.exceptions import ChannelClosed
from pymongo.errors import OperationFailure
from bson import ObjectId

from threading import Thread, Event, Lock


class GestionnaireDomainesMilleGrilles(ModeleConfiguration):
    """
    Classe qui agit comme gestionnaire centralise de plusieurs domaines MilleGrilles.
    Cette classe s'occupe des DAOs et du cycle de vie du programme.
    """

    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger("%s.%s" % (__name__, self.__class__.__name__))
        self._gestionnaires = []
        self._stop_event = Event()
        self.__mq_ioloop = None
        self.__channel = None  # Ouvrir un channel pour savoir quand MQ est pret
        self.__wait_mq_ready = Event()

    def initialiser(self, init_document=True, init_message=True, connecter=True):
        """ L'initialisation connecte RabbitMQ, MongoDB, lance la configuration """
        super().initialiser(init_document, init_message, connecter)
        self.__mq_ioloop = Thread(name="MQ-ioloop", target=self.contexte.message_dao.run_ioloop, daemon=True)
        self.__mq_ioloop.start()
        self.contexte.message_dao.register_channel_listener(self)

    def on_channel_open(self, channel):
        super().on_channel_open(channel)
        channel.basic_qos(prefetch_count=10)
        channel.add_on_close_callback(self.on_channel_close)
        self.__channel = channel

        # MQ est pret, on charge les domaines
        self.__wait_mq_ready.set()

    def on_channel_close(self, channel=None, code=None, reason=None):
        self.__wait_mq_ready.clear()
        self.__channel = None
        self._logger.info("MQ Channel ferme")

    def configurer_parser(self):
        super().configurer_parser()

        self.parser.add_argument(
            '--domaines',
            type=str,
            required=False,
            help="Gestionnaires de domaines a charger. Format: nom_module1:nom_classe1,nom_module2:nom_classe2,[...]"
        )

        self.parser.add_argument(
            '--configuration',
            type=str,
            required=False,
            help="Chemin du fichier de configuration des domaines"
        )

    ''' Charge les domaines listes en parametre '''
    def charger_domaines(self):

        liste_classes_gestionnaires = []

        # Faire liste des domaines args
        liste_domaines = self.args.domaines
        if liste_domaines is not None:
            gestionnaires = liste_domaines.split(',')
            self._logger.info("Chargement des gestionnaires: %s" % str(gestionnaires))

            for gestionnaire in gestionnaires:
                noms_module_class = gestionnaire.strip().split(':')
                nom_module = noms_module_class[0]
                nom_classe = noms_module_class[1]
                classe = self.importer_classe_gestionnaire(nom_module, nom_classe)
                liste_classes_gestionnaires.append(classe)

        # Charger le fichier de configuration json
        chemin_fichier_configuration = self.args.configuration
        if chemin_fichier_configuration is None:
            chemin_fichier_configuration = self.contexte.configuration.domaines_json

        if chemin_fichier_configuration is not None:
            self._logger.info("Charger la configuration a partir du fichier: %s" % chemin_fichier_configuration)

            with open(chemin_fichier_configuration) as json_config:
                configuration_json = json.load(json_config)

            domaines = configuration_json['domaines']
            for domaine in domaines:
                classe = self.importer_classe_gestionnaire(
                    domaine['module'],
                    domaine['classe']
                )
                liste_classes_gestionnaires.append(classe)

        self._logger.info("%d classes de gestionnaires a charger" % len(liste_classes_gestionnaires))

        # On prepare et configure une instance de chaque gestionnaire
        for classe_gestionnaire in liste_classes_gestionnaires:
            # Preparer une instance du gestionnaire
            instance = classe_gestionnaire(self.contexte)
            instance.configurer()  # Executer la configuration du gestionnaire de domaine
            self._gestionnaires.append(instance)

    def importer_classe_gestionnaire(self, nom_module, nom_classe):
        self._logger.info("Nom package: %s, Classe: %s" % (nom_module, nom_classe))
        classe_processus = __import__(nom_module, fromlist=[nom_classe])
        classe = getattr(classe_processus, nom_classe)
        self._logger.debug("Classe gestionnaire chargee: %s %s" % (classe.__module__, classe.__name__))
        return classe

    def demarrer_execution_domaines(self):
        for gestionnaire in self._gestionnaires:
            self._logger.debug("Demarrer un gestionnaire")
            gestionnaire.demarrer()

    def exit_gracefully(self, signum=None, frame=None):
        self.arreter()
        super().exit_gracefully()

    def executer(self):
        self.__wait_mq_ready.wait(60)
        if not self.__wait_mq_ready.is_set():
            raise Exception("MQ n'est pas pret apres 60 secondes")

        self.charger_domaines()

        if len(self._gestionnaires) > 0:
            self.demarrer_execution_domaines()
        else:
            self._stop_event.set()
            self._logger.fatal("Aucun gestionnaire de domaine n'a ete charge. Execution interrompue.")

        # Surveiller les gestionnaires - si un gestionnaire termine son execution, on doit tout fermer
        while not self._stop_event.is_set():
            # self.contexte.message_dao.start_consuming()  # Blocking
            # self._logger.debug("Erreur consuming, attendre 5 secondes pour ressayer")

            self._stop_event.wait(60)   # Boucler pour maintenance  A FAIRE

        self._logger.info("Fin de la boucle executer() dans MAIN")

    def arreter(self):
        self._logger.info("Arret du gestionnaire de domaines MilleGrilles")
        self._stop_event.set()  # Va arreter la boucle de verification des gestionnaires

        # Avertir chaque gestionnaire
        for gestionnaire in self._gestionnaires:
            try:
                gestionnaire.arreter()
            except ChannelClosed as ce:
                self._logger.debug("Channel deja ferme: %s" % str(ce))
            except Exception as e:
                self._logger.warning("Erreur arret gestionnaire %s: %s" % (gestionnaire.__class__.__name__, str(e)))

        self.deconnecter()

    def set_logging_level(self):
        super().set_logging_level()
        """ Utilise args pour ajuster le logging level (debug, info) """
        if self.args.debug:
            self._logger.setLevel(logging.DEBUG)
            logging.getLogger('mgdomaines').setLevel(logging.DEBUG)
        elif self.args.info:
            self._logger.setLevel(logging.INFO)
            logging.getLogger('mgdomaines').setLevel(logging.INFO)


class GestionnaireDomaine:
    """ Le gestionnaire de domaine est une superclasse qui definit le cycle de vie d'un domaine. """

    def __init__(self, contexte):

        # Nouvelle approche, utilisation classe contexte pour obtenir les ressources
        self.__contexte = contexte
        self.demarreur_processus = None
        self.json_helper = JSONHelper()
        self._logger = logging.getLogger("%s.GestionnaireDomaine" % __name__)
        self._thread = None
        self._watchers = list()
        self.connexion_mq = None
        self.channel_mq = None
        self._arret_en_cours = False
        self._stop_event = Event()
        self._traitement_evenements = None
        self.wait_Q_ready = Event()  # Utilise pour attendre configuration complete des Q
        self.wait_Q_ready_lock = Lock()
        self.nb_routes_a_config = 0

        self._consumer_tags_parQ = dict()

        # ''' L'initialisation connecte RabbitMQ, MongoDB, lance la configuration '''
    # def initialiser(self):
    #     self.connecter()  # On doit se connecter immediatement pour permettre l'appel a configurer()

    def configurer(self):
        self._traitement_evenements = MGPProcesseurTraitementEvenements(self._contexte, self._stop_event, gestionnaire_domaine=self)
        self._traitement_evenements.initialiser([self.get_collection_processus_nom()])
        """ Configure les comptes, queues/bindings (RabbitMQ), bases de donnees (MongoDB), etc. """
        self.demarreur_processus = MGPProcessusDemarreur(
            self._contexte, self.get_nom_domaine(), self.get_collection_transaction_nom(),
            self.get_collection_processus_nom(), self._traitement_evenements, gestionnaire=self)

    def demarrer(self):
        """ Demarrer une thread pour ce gestionnaire """
        self._logger.debug("Debut thread gestionnaire %s" % self.__class__.__name__)
        # self.configurer()  # Deja fait durant l'initialisation
        self._logger.info("On enregistre la queue %s" % self.get_nom_queue())

        self._contexte.message_dao.register_channel_listener(self)
        self._logger.info("Attente Q et routes prets")
        self.wait_Q_ready.wait(5)  # Donner 5 seconde a MQ

        if not self.wait_Q_ready.is_set():
            if self.nb_routes_a_config > 0:
                self._logger.error("Les routes de Q du domaine ne sont pas configures correctement, il reste %d a configurer" % self.nb_routes_a_config)
            else:
                self._logger.warning('wait_Q_read pas set, on va forcer error state sur la connexion pour recuperer')
            self.message_dao.enter_error_state()
        else:
            self._logger.info("Q et routes prets")

            # Verifier si on doit upgrader les documents avant de commencer a ecouter
            doit_regenerer = self.verifier_version_transactions(self.version_domaine)

            if doit_regenerer:
                self.regenerer_documents()
                self.changer_version_collection(self.version_domaine)

            # Lance le processus de regeneration des rapports sur cedule pour s'assurer d'avoir les donnees a jour
            self.regenerer_rapports_sur_cedule()

    def on_channel_open(self, channel):
        """
        Callback pour l"ouverture ou la reouverture du channel MQ
        :param channel:
        :return:
        """
        if self.channel_mq is not None:
            # Fermer le vieux channel
            try:
                self.channel_mq.close()
            finally:
                self.channel_mq = None

        self.channel_mq = channel
        channel.basic_qos(prefetch_count=1)
        channel.add_on_close_callback(self.on_channel_close)

        self.setup_rabbitmq()  # Setup Q et consumers

    def get_queue_configuration(self):
        """
        :return: Liste de Q avec configuration pour le domaine
        """
        raise NotImplementedError("Pas implemente")

    def setup_rabbitmq(self, consume=True):
        """
        Callback pour faire le setup de rabbitMQ quand le channel est ouvert. Permet aussi de refaire les binding
        avec les Q apres avoir appele unbind_rabbitmq.
        """
        channel = self.channel_mq
        queues_config = self.get_queue_configuration()

        self.nb_routes_a_config = len([r for r in [q.get('routing') for q in queues_config]])
        self.wait_Q_ready.clear()  # Reset flag au besoin
        # channel = self.message_dao.channel
        for queue_config in queues_config:

            def callback_init_transaction(queue, gestionnaire=self, in_queue_config=queue_config, in_consume=consume):
                if in_consume:
                    gestionnaire.inscrire_basicconsume(queue, in_queue_config['callback'])

                routing_list = in_queue_config.get('routing')
                if routing_list is not None:
                    for routing in routing_list:
                        channel.queue_bind(
                            exchange=in_queue_config['exchange'],
                            queue=in_queue_config['nom'],
                            routing_key=routing,
                            callback=self.__compter_route
                        )

            args = {}
            if queue_config.get('arguments'):
                args.update(queue_config.get('arguments'))
            if queue_config.get('ttl'):
                args['x-message-ttl'] = queue_config['ttl']

            durable = False
            if queue_config.get('durable'):
                durable = True

            self._logger.info("Declarer Q %s" % queue_config['nom'])
            channel.queue_declare(
                queue=queue_config['nom'],
                durable=durable,
                callback=callback_init_transaction,
                arguments=args,
            )

    def __compter_route(self, arg1):
        """
        Sert a compter les routes qui sont pretes. Declenche Event wait_Q_ready lorsque complet.
        :param arg1:
        :return:
        """
        # Indiquer qu'une route a ete configuree
        with self.wait_Q_ready_lock:
            self.nb_routes_a_config = self.nb_routes_a_config - 1

            if self.nb_routes_a_config <= 0:
                # Il ne reste plus de routes a configurer, set flag comme pret
                self.wait_Q_ready.set()

    def stop_consuming(self, queue = None):
        """
        Deconnecte les consommateur queues du domaine pour effectuer du travail offline.
        """
        channel = self.channel_mq
        if queue is None:
           tags = channel.consumer_tags
           for tag in tags:
                self._logger.debug("Removing ctag %s" % tag)
                with self.message_dao.lock_transmettre_message:
                    channel.basic_cancel(consumer_tag=tag, nowait=True)
        else:
           ctag = self._consumer_tags_parQ.get(queue)
           if ctag is not None:
               with self.message_dao.lock_transmettre_message:
                    channel.basic_cancel(consumer_tag=ctag, nowait=True)

    def resoumettre_transactions(self):
        """
        Soumets a nouveau les notifications de transactions non completees du domaine.
        Utilise l'ordre de persistance.
        :return:
        """
        idmg = self.configuration.idmg
        champ_complete = '%s.%s' % (Constantes.TRANSACTION_MESSAGE_LIBELLE_EVENEMENT, Constantes.EVENEMENT_TRANSACTION_COMPLETE)
        champ_persiste = '%s.%s.%s' % (Constantes.TRANSACTION_MESSAGE_LIBELLE_EVENEMENT, idmg, Constantes.EVENEMENT_DOCUMENT_PERSISTE)
        filtre = {
            champ_complete: False
        }
        hint = [
            (champ_complete, 1),
            (champ_persiste, 1)
        ]

        collection_transactions = self.document_dao.get_collection(self.get_collection_transaction_nom())
        transactions_incompletes = collection_transactions.find(filtre, sort=hint).hint(hint)

        try:
            for transaction in transactions_incompletes:
                self._logger.debug("Transaction incomplete: %s" % transaction)
                id_document = transaction[Constantes.MONGO_DOC_ID]
                en_tete = transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE]
                uuid_transaction = en_tete[Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID]
                domaine = en_tete[Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE]
                self.message_dao.transmettre_evenement_persistance(
                    id_document, uuid_transaction, domaine, None)
        except OperationFailure as of:
            self._logger.error("Collection %s, erreur requete avec hint: %s.\n%s" % (
                self.get_collection_transaction_nom(), str(hint), str(of)))

    def on_channel_close(self, channel=None, code=None, reason=None):
        """
        Callback pour la fermeture du channel
        :param channel:
        :return:
        """
        self._logger.info("Channel ferme: %s, %s" %(code, reason))
        self.channel_mq = None

    def inscrire_basicconsume(self, queue, callback):
        """
        Inscrit le channel sur la queue.
        :param queue:
        :param callback:
        :return: Consumer tag (ctag)
        """
        if isinstance(queue, str):
            nom_queue = queue
        else:
            nom_queue = queue.method.queue

        self._logger.info("Queue prete, on enregistre basic_consume %s" % nom_queue)
        with self.message_dao.lock_transmettre_message:
            ctag = self.channel_mq.basic_consume(callback, queue=nom_queue, no_ack=False)

        # Conserver le ctag - permet de faire cancel au besoin (e.g. long running process)
        self._consumer_tags_parQ[nom_queue] = ctag

        return ctag

    def demarrer_watcher_collection(self, nom_collection_mongo: str, routing_key: str, exchange_router=None):
        """
        Enregistre un watcher et demarre une thread qui lit le pipeline dans MongoDB. Les documents sont
        lus au complet et envoye avec la routing_key specifiee.
        :param nom_collection_mongo: Nom de la collection dans MongoDB pour cette MilleGrille
        :param routing_key: Nom du topic a enregistrer,
               e.g. noeuds.source.millegrilles_domaines_SenseursPassifs.affichage.__nom_noeud__.__no_senseur__
        :param exchange_router: Routeur pour determiner sur quels exchanges le document sera place.
        :return:
        """
        watcher = WatcherCollectionMongoThread(self._contexte, self._stop_event, nom_collection_mongo, routing_key, exchange_router)
        self._watchers.append(watcher)
        watcher.start()

    def identifier_processus(self, domaine_transaction):
        nom_domaine = self.get_nom_domaine()
        operation = domaine_transaction.replace('%s.' % nom_domaine, '')

        if operation == Constantes.TRANSACTION_ROUTING_DOCINITIAL:
            processus = "%s:millegrilles_MGProcessus:MGProcessusDocInitial" % operation
        elif operation == Constantes.TRANSACTION_ROUTING_UPDATE_DOC:
            processus = "%s:millegrilles_MGProcessus:MGProcessusUpdateDoc" % operation
        else:
            raise TransactionTypeInconnuError("Type de transaction inconnue: routing: %s" % domaine_transaction)

        return processus

    def regenerer_rapports_sur_cedule(self):
        """ Permet de regenerer les documents de rapports sur cedule lors du demarrage du domaine """
        pass

    def regenerer_documents(self, stop_consuming=True):
        self._logger.info("Regeneration des documents de %s" % self.get_nom_domaine())
        processeur_regeneration = MGPProcesseurRegeneration(self.__contexte, self)
        processeur_regeneration.regenerer_documents(stop_consuming=stop_consuming)
        self._logger.info("Fin regeneration des documents de %s" % self.get_nom_domaine())

    def get_collection_transaction_nom(self):
        raise NotImplementedError("N'est pas implemente - doit etre definit dans la sous-classe")

    def get_collection_processus_nom(self):
        raise NotImplementedError("N'est pas implemente - doit etre definit dans la sous-classe")

    def get_nom_domaine(self):
        raise NotImplementedError("N'est pas implemente - doit etre definit dans la sous-classe")

    ''' Arrete le traitement des messages pour le domaine '''
    def arreter_traitement_messages(self):
        self._arret_en_cours = True
        self._stop_event.set()
        if self.channel_mq is not None:
            self.channel_mq.close()
        self._traitement_evenements.arreter()

    def demarrer_processus(self, processus, parametres):
        self.demarreur_processus.demarrer_processus(processus, parametres)

    def verifier_version_transactions(self, version_domaine):
        # Configurer MongoDB, inserer le document de configuration de reference s'il n'existe pas
        collection_domaine = self.get_collection()

        # Trouver le document de configuration
        document_configuration = collection_domaine.find_one(
            {Constantes.DOCUMENT_INFODOC_LIBELLE: Constantes.LIBVAL_CONFIGURATION}
        )
        self._logger.debug("Document config domaine: %s" % document_configuration)

        doit_regenerer = True
        if document_configuration is not None:
            version_collection = document_configuration.get(Constantes.TRANSACTION_MESSAGE_LIBELLE_VERSION)
            if version_collection is None:
                self._logger.warning(
                    "La collection a une version inconnue a celle du code Python (V%d), on regenere les documents" %
                    version_domaine
                )
            elif version_collection == version_domaine:
                doit_regenerer = False
            elif version_collection > version_domaine:
                message_erreur = "Le code du domaine est V%d, le document de configuration est V%d (plus recent)" % (
                    version_domaine, version_collection
                )
                raise Exception(message_erreur)
            else:
                self._logger.warning(
                    "La collection a une version inferieure (V%d) a celle du code Python (V%d), on regenere les documents" %
                    (version_collection, version_domaine)
                )

        return doit_regenerer

    def initialiser_document(self, mg_libelle, doc_defaut):
        """
        Insere un document de configuration du domaine, au besoin. Le libelle doit etre unique dans la collection.
        :param mg_libelle: Libelle a donner au document
        :param doc_defaut: Document a inserer.
        :return:
        """
        # Configurer MongoDB, inserer le document de configuration de reference s'il n'existe pas
        collection_domaine = self.get_collection()

        # Trouver le document de configuration
        document_configuration = collection_domaine.find_one(
            {Constantes.DOCUMENT_INFODOC_LIBELLE: mg_libelle}
        )
        if document_configuration is None:
            self._logger.info("On insere le document %s pour domaine Principale" % mg_libelle)

            # Preparation document de configuration pour le domaine
            configuration_initiale = doc_defaut.copy()
            # maintenant = datetime.datetime.utcnow()
            # configuration_initiale[Constantes.DOCUMENT_INFODOC_DATE_CREATION] = maintenant.timestamp()
            # configuration_initiale[Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION] = maintenant.timestamp()
            nouveau_doc = {
                Constantes.DOCUMENT_INFODOC_SOUSDOCUMENT: configuration_initiale
            }

            # collection_domaine.insert(configuration_initiale)
            domaine_transaction = '%s.%s' % (self.get_nom_domaine(), Constantes.TRANSACTION_ROUTING_DOCINITIAL)
            self.generateur_transactions.soumettre_transaction(nouveau_doc, domaine_transaction)
        else:
            self._logger.debug("Document de %s pour %s: %s" % (
                mg_libelle, str(document_configuration), self.__class__.__name__
            ))

    def changer_version_collection(self, version):
        nouveau_doc = {
            Constantes.DOCUMENT_INFODOC_SOUSDOCUMENT: {
                Constantes.DOCUMENT_INFODOC_LIBELLE: Constantes.LIBVAL_CONFIGURATION,
                Constantes.TRANSACTION_MESSAGE_LIBELLE_VERSION: version
            }
        }

        # collection_domaine.insert(configuration_initiale)
        domaine_transaction = '%s.%s' % (self.get_nom_domaine(), Constantes.TRANSACTION_ROUTING_UPDATE_DOC)
        self.generateur_transactions.soumettre_transaction(nouveau_doc, domaine_transaction)

    def marquer_transaction_en_erreur(self, dict_message):
        # Type de transaction inconnue, on lance une exception
        id_transaction = dict_message[Constantes.TRANSACTION_MESSAGE_LIBELLE_ID_MONGO]
        domaine = dict_message[Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE]
        collection = ConsignateurTransactionCallback.identifier_collection_domaine(domaine)

        evenement = {
            Constantes.TRANSACTION_MESSAGE_LIBELLE_EVENEMENT: Constantes.EVENEMENT_MESSAGE_EVENEMENT,
            Constantes.MONGO_DOC_ID: id_transaction,
            Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE: collection,
            Constantes.EVENEMENT_MESSAGE_EVENEMENT: Constantes.EVENEMENT_TRANSACTION_ERREUR_TRAITEMENT,
        }
        self.message_dao.transmettre_message(evenement, Constantes.TRANSACTION_ROUTING_EVENEMENT)

    '''
    Implementer cette methode pour retourner le nom de la queue.

    :returns: Nom de la Q a ecouter.
    '''
    def get_nom_queue(self):
        raise NotImplementedError("Methode non-implementee")

    def get_nom_collection(self):
        raise NotImplementedError("Methode non-implementee")

    def get_collection(self):
        return self.document_dao.get_collection(self.get_nom_collection())

    def get_transaction(self, id_transaction):
        collection_transactions = self.document_dao.get_collection(self.get_collection_transaction_nom())
        return collection_transactions.find_one({Constantes.MONGO_DOC_ID: ObjectId(id_transaction)})

    def arreter(self):
        self._logger.warning("Arret de GestionnaireDomaine")
        self.arreter_traitement_messages()
        for watcher in self._watchers:
            try:
                watcher.stop()
            except Exception as e:
                self._logger.info("Erreur fermeture watcher: %s" % str(e))

    @property
    def configuration(self):
        return self._contexte.configuration

    @property
    def message_dao(self):
        return self._contexte.message_dao

    @property
    def document_dao(self):
        return self._contexte.document_dao

    @property
    def generateur_transactions(self):
        return self._contexte.generateur_transactions

    @property
    def verificateur_transaction(self):
        return self._contexte.verificateur_transaction

    @property
    def verificateur_certificats(self):
        return self._contexte.verificateur_certificats

    def creer_regenerateur_documents(self):
        return RegenerateurDeDocuments(self)

    @property
    def _contexte(self):
        return self.__contexte

    @property
    def version_domaine(self):
        return Constantes.TRANSACTION_MESSAGE_LIBELLE_VERSION_6


class GestionnaireDomaineStandard(GestionnaireDomaine):
    """
    Implementation des Q standards pour les domaines.
    """

    def __init__(self, contexte):
        super().__init__(contexte)

        self.__traitement_middleware = None
        self.__traitement_noeud = None
        self.__handler_cedule = None

        self._logger = logging.getLogger("%s.%s" % (__name__, self.__class__.__name__))

    def configurer(self):
        super().configurer()

        self.__traitement_middleware = TraitementMessageDomaineMiddleware(self)
        self.__traitement_noeud = TraitementMessageDomaineRequete(self)
        self.__handler_cedule = TraitementMessageCedule(self)

        collection_domaine = self.document_dao.get_collection(self.get_nom_collection())
        # Index noeud, _mg-libelle
        collection_domaine.create_index(
            [
                (Constantes.DOCUMENT_INFODOC_LIBELLE, 1)
            ],
            name='mglibelle'
        )
        collection_domaine.create_index(
            [
                (Constantes.DOCUMENT_INFODOC_DATE_CREATION, 1)
            ],
            name='datecreation'
        )
        collection_domaine.create_index(
            [
                (Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION, -1)
            ],
            name='dernieremodification'
        )

    def get_queue_configuration(self):
        """
        :return: Liste de configuration pour les Q du domaine
        """

        queues_config = [
            {
                'nom': '%s.%s' % (self.get_nom_queue(), 'transactions'),
                'routing': [
                    'destinataire.domaine.%s.#' % self.get_nom_domaine(),
                ],
                'exchange': self.configuration.exchange_middleware,
                'ttl': 300000,
                'callback': self.get_handler_transaction().callbackAvecAck
            },
            {
                'nom': '%s.%s' % (self.get_nom_queue(), 'ceduleur'),
                'routing': [
                    'ceduleur.#',
                ],
                'exchange': self.configuration.exchange_middleware,
                'ttl': 30000,
                'callback': self.get_handler_cedule().callbackAvecAck
            },
            {
                'nom': '%s.%s' % (self.get_nom_queue(), 'processus'),
                'routing': [
                    'processus.domaine.%s.#' % self.get_nom_domaine()
                ],
                'exchange': self.configuration.exchange_middleware,
                'ttl': 600000,
                'callback': self._traitement_evenements.callbackAvecAck
            }
        ]

        # Ajouter les handles de requete par niveau de securite
        for securite, handler_requete in self.get_handler_requetes().items():
            if securite == Constantes.SECURITE_SECURE:
                exchange = self.configuration.exchange_middleware
            elif securite == Constantes.SECURITE_PROTEGE:
                exchange = self.configuration.exchange_noeuds
            elif securite == Constantes.SECURITE_PRIVE:
                exchange = self.configuration.exchange_prive
            else:
                exchange = self.configuration.exchange_public

            queues_config.append({
                'nom': '%s.%s' % (self.get_nom_queue(), 'requete.noeuds.' + securite),
                'routing': [
                    'requete.%s.#' % self.get_nom_domaine(),
                ],
                'exchange': exchange,
                'ttl': 20000,
                'callback': handler_requete.callbackAvecAck
            })

        for securite, handler_requete in self.get_handler_commandes().items():
            if securite == Constantes.SECURITE_SECURE:
                exchange = self.configuration.exchange_middleware
            elif securite == Constantes.SECURITE_PROTEGE:
                exchange = self.configuration.exchange_noeuds
            elif securite == Constantes.SECURITE_PRIVE:
                exchange = self.configuration.exchange_prive
            else:
                exchange = self.configuration.exchange_public

            queues_config.append({
                'nom': '%s.%s' % (self.get_nom_queue(), 'commande.' + securite),
                'routing': [
                    'commande.%s.#' % self.get_nom_domaine(),
                ],
                'exchange': exchange,
                'ttl': 20000,
                'callback': handler_requete.callbackAvecAck
            })

        return queues_config

    def map_transaction_vers_document(self, transaction: dict, document: dict):
        for key, value in transaction.items():
            if key != Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE and not key.startswith('_'):
                document[key] = value

    def get_handler_transaction(self):
        return self.__traitement_middleware

    def get_handler_requetes_noeuds(self):
        return self.__traitement_noeud

    def get_handler_requetes(self) -> dict:
        return {
            Constantes.SECURITE_PROTEGE: self.get_handler_requetes_noeuds()
        }

    def get_handler_commandes(self) -> dict:
        return dict()  # Aucun par defaut

    def get_handler_cedule(self):
        return self.__handler_cedule

    def traiter_cedule(self, evenement):
        """ Appele par __handler_cedule lors de la reception d'un message sur la Q .ceduleur du domaine """

        indicateurs = evenement['indicateurs']
        self._logger.debug("Cedule webPoll: %s" % str(indicateurs))

        # Faire la liste des cedules a declencher
        if 'heure' in indicateurs:
            self.nettoyer_processus()

    def nettoyer_processus(self):
        collection_processus = self.document_dao.get_collection(self.get_collection_processus_nom())

        date_complet = datetime.datetime.utcnow() - datetime.timedelta(days=1)
        date_incomplet = datetime.datetime.utcnow() - datetime.timedelta(days=14)

        filtre_complet = {
            "etape-suivante": {"$exists": False},
            "_mg-derniere-modification": {"$lte": date_complet}
        }
        filtre_incomplet = {
            "etape-suivante": {"$exists": True},
            "_mg-creation": {"$lte": date_incomplet}
        }

        collection_processus.delete_many(filtre_complet)
        collection_processus.delete_many(filtre_incomplet)


class TraitementRequetesNoeuds(TraitementMessageDomaine):

    def __init__(self, gestionnaire):
        super().__init__(gestionnaire)
        self._logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def traiter_message(self, ch, method, properties, body):
        routing_key = method.routing_key
        exchange = method.exchange
        message_dict = self.json_helper.bin_utf8_json_vers_dict(body)
        evenement = message_dict.get(Constantes.EVENEMENT_MESSAGE_EVENEMENT)
        enveloppe_certificat = self.gestionnaire.verificateur_transaction.verifier(message_dict)

        self._logger.debug("Certificat: %s" % str(enveloppe_certificat))
        resultats = list()
        for requete in message_dict['requetes']:
            resultat = self.executer_requete(requete)
            resultats.append(resultat)

        # Genere message reponse
        self.transmettre_reponse(message_dict, resultats, properties.reply_to, properties.correlation_id)

    def executer_requete(self, requete):
        self._logger.debug("Requete: %s" % str(requete))
        collection = self.document_dao.get_collection(self._gestionnaire.get_nom_collection())
        filtre = requete.get('filtre')
        projection = requete.get('projection')
        sort_params = requete.get('sort')

        if projection is None:
            curseur = collection.find(filtre)
        else:
            curseur = collection.find(filtre, projection)

        curseur.limit(2500)  # Mettre limite sur nombre de resultats

        if sort_params is not None:
            curseur.sort(sort_params)

        resultats = list()
        for resultat in curseur:
            resultats.append(resultat)

        self._logger.debug("Resultats: %s" % str(resultats))

        return resultats

    def transmettre_reponse(self, requete, resultats, replying_to, correlation_id=None):
        # enveloppe_val = generateur.soumettre_transaction(requete, 'millegrilles.domaines.Principale.creerAlerte')
        if correlation_id is None:
            correlation_id = requete[Constantes.TRANSACTION_MESSAGE_LIBELLE_INFO_TRANSACTION][Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID]

        message_resultat = {
            'resultats': resultats,
        }

        self.gestionnaire.generateur_transactions.transmettre_reponse(message_resultat, replying_to, correlation_id)


class ExchangeRouter:
    """
    Classe qui permet de determiner sur quel echange le document doit etre soumis
    """

    def __init__(self, contexte: ContexteRessourcesMilleGrilles):
        self.__contexte = contexte

        self._exchange_public = self.__contexte.configuration.exchange_public
        self._exchange_prive = self.__contexte.configuration.exchange_prive
        self._exchange_protege = self.__contexte.configuration.exchange_noeuds
        self._exchange_secure = self.__contexte.configuration.exchange_middleware

    def determiner_exchanges(self, document: dict) -> list:
        """
        :return: Liste des echanges sur lesquels le document doit etre soumis
        """
        return [self._exchange_protege]


class WatcherCollectionMongoThread:
    """
    Ecoute les changements sur une collection MongoDB et transmet les documents complets sur RabbitMQ.
    """

    def __init__(
            self,
            contexte: ContexteRessourcesMilleGrilles,
            stop_event: Event,
            nom_collection_mongo: str,
            routing_key: str,
            exchange_router: ExchangeRouter,
    ):
        """
        :param contexte:
        :param stop_event: Stop event utilise par le gestionnaire.
        :param nom_collection_mongo:
        :param routing_key:
        :param exchange_routing: Permet de determiner quels documents vont sur les echanges proteges, prives et publics.
        """
        self.__logger = logging.getLogger("%s.%s" % (__name__, self.__class__.__name__))

        self.__contexte = contexte
        self.__stop_event = stop_event
        self.__nom_collection_mongo = nom_collection_mongo
        self.__routing_key = routing_key

        self.__exchange_router = exchange_router
        if self.__exchange_router is None:
            self.__exchange_router = ExchangeRouter(contexte)

        self.__collection_mongo = None
        self.__thread = None
        self.__curseur_changements = None

    def start(self):
        self.__logger.info("Demarrage thread watcher:%s vers routing:%s" % (
            self.__nom_collection_mongo, self.__routing_key))
        self.__thread = Thread(name="DocWatcher", target=self.run, daemon=True)
        self.__thread.start()

    def stop(self):
        self.__curseur_changements.close()

    def run(self):
        self.__logger.info("Thread watch: %s" % self.__nom_collection_mongo)

        # Boucler tant que le stop event n'est pas active
        while not self.__stop_event.isSet():
            if self.__curseur_changements is not None:
                try:
                    change_event = self.__curseur_changements.next()
                    self.__logger.debug("Watcher event recu: %s" % str(change_event))

                    operation_type = change_event['operationType']
                    if operation_type in ['insert', 'update', 'replace']:
                        full_document = change_event['fullDocument']
                        self._emettre_document(full_document)
                    elif operation_type == 'invalidate':
                        # Curseur ferme
                        self.__logger.warning("Curseur watch a ete invalide, on le ferme.\n%s" % str(change_event))
                        self.__curseur_changements = None
                    elif operation_type in ['delete', 'drop', 'rename']:
                        pass
                    elif operation_type == 'dropDatabase':
                        self.__logger.error("Drop database event : %s" % str(change_event))
                    else:
                        self.__logger.debug("Evenement non supporte: %s" % operation_type)
                        self.__stop_event.wait(0.5)  # Attendre 0.5 secondes, throttle
                except StopIteration:
                    self.__logger.info("Arret watcher dans l'iteration courante")
                    self.__curseur_changements = None
                except Exception:
                    self.__logger.exception("Erreur dans le traitement du watcher")
                    self.__stop_event.wait(1)  # Attendre 1 seconde, throttle

            else:
                self.__stop_event.wait(5)  # Attendre 5 secondes, throttle
                self.__logger.info("Creer pipeline %s" % self.__nom_collection_mongo)
                self._creer_pipeline()

    def _creer_pipeline(self):
        collection_mongo = self.__contexte.document_dao.get_collection(self.__nom_collection_mongo)

        # Tenter d'activer watch par _id pour les documents
        try:
            option = {'full_document': 'updateLookup', 'max_await_time_ms': 1000}
            pipeline = []
            logging.info("Pipeline watch: %s" % str(pipeline))
            self.__curseur_changements = collection_mongo.watch(pipeline, **option)

        except OperationFailure as opf:
            self.__logger.warning("Erreur activation watch, on fonctionne par timer: %s" % str(opf))
            self.__curseur_changements = None

    def _emettre_document(self, document):
        self.__logger.debug("Watcher document recu: %s" % str(document))

        # Ajuster la routing key pour ajouter information si necessaire.
        routing_key = self.__routing_key
        exchanges = self.__exchange_router.determiner_exchanges(document)
        mg_libelle = document.get(Constantes.DOCUMENT_INFODOC_LIBELLE)
        if mg_libelle is not None:
            routing_key = '%s.%s' % (routing_key, mg_libelle)

        # Transmettre document sur MQ
        self.__contexte.generateur_transactions.emettre_message(document, routing_key, exchanges)


class TraiteurRequeteDomaineNoeud:
    """
    Execute les requetes faites par les noeuds sur le topic domaine._domaine_.requete.noeud
    """

    def __init__(self):
        pass


class RegenerateurDeDocuments:
    """
    Efface et regenere les /documents d'un domaine.
    """

    def __init__(self, gestionnaire_domaine):
        self._gestionnaire_domaine = gestionnaire_domaine
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    @property
    def contexte(self):
        return self._gestionnaire_domaine.contexte

    def supprimer_documents(self):
        """
        Supprime les documents de la collection
        :return:
        """
        nom_collection_documents = self._gestionnaire_domaine.get_nom_collection()
        self.__logger.info("Supprimer les documents de %s" % nom_collection_documents)

        collection_documents = self._gestionnaire_domaine.get_collection()
        collection_documents.delete_many({})

    def creer_generateur_transactions(self):
        return GroupeurTransactionsARegenerer(self._gestionnaire_domaine)


class RegenerateurDeDocumentsSansEffet(RegenerateurDeDocuments):
    """
    Empeche la regeneration d'un domaine
    """

    def supprimer_documents(self):
        pass

    def creer_generateur_transactions(self):
        return GroupeurTransactionsSansEffet()


class GroupeurTransactionsARegenerer:
    """
    Classe qui permet de grouper les transactions d'un domaine pour regenerer les documents.
    Groupe toutes les transactions dans un seul groupe, en ordre de transaction_traitee.
    """

    def __init__(self, gestionnaire_domaine: GestionnaireDomaine):
        self.__gestionnaire_domaine = gestionnaire_domaine
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        self.__complet = False

    def __preparer_curseur_transactions(self):
        nom_collection_transaction = self.__gestionnaire_domaine.get_collection_transaction_nom()
        self.__logger.debug('Preparer curseur transactions sur %s' % nom_collection_transaction)

        collection_transactions = self.__gestionnaire_domaine.document_dao.get_collection(nom_collection_transaction)

        filtre, index = self.__preparer_requete()
        return collection_transactions.find(filtre).sort(index).hint(index)

    def __preparer_requete(self):
        idmg = self.__gestionnaire_domaine.configuration.idmg

        # Parcourir l'index:
        #  - _evenements.transaction_complete
        #  - _evenements.IDMGtransaction_traitee
        index = [
            ('%s.%s' % (Constantes.TRANSACTION_MESSAGE_LIBELLE_EVENEMENT,
                        Constantes.EVENEMENT_TRANSACTION_COMPLETE), 1),
            ('%s.%s.%s' % (Constantes.TRANSACTION_MESSAGE_LIBELLE_EVENEMENT, idmg,
                           Constantes.EVENEMENT_TRANSACTION_TRAITEE), 1)
        ]
        # ordre_tri = index  # L'index est trie dans l'ordre necessaire

        # Filtre par transaction completee:
        #  - _evenements.transaction_complete = True
        #  - _evenements.IDMG.transaction_traitee existe
        filtre = {
            '%s.%s' % (Constantes.TRANSACTION_MESSAGE_LIBELLE_EVENEMENT,
                       Constantes.EVENEMENT_TRANSACTION_COMPLETE): True,
            '%s.%s.%s' % (Constantes.TRANSACTION_MESSAGE_LIBELLE_EVENEMENT, idmg,
                          Constantes.EVENEMENT_TRANSACTION_TRAITEE): {'$exists': True}
        }

        return filtre, index

    def __iter__(self):
        return self.__next__()

    def __next__(self):
        """
        Retourne un curseur Mongo avec les transactions a executer en ordre.
        :return:
        """
        if self.__complet:
            raise StopIteration()

        curseur = self.__preparer_curseur_transactions()
        for valeur in curseur:
            self.__logger.debug("Transaction: %s" % str(valeur))
            yield valeur

        self.__complet = True

        return

    @property
    def gestionnaire(self):
        return self.__gestionnaire_domaine

    @property
    def _complet(self):
        return self.__complet


class GroupeurTransactionsSansEffet:

    def __init__(self):
        self.__complete = True

    def __iter__(self):
        return self

    def __next__(self):
        if self.__complete:
            raise StopIteration()

        self.__complete = True
        return


class TransactionTypeInconnuError(Exception):

    def __init__(self, msg, routing_key=None):
        if routing_key is not None:
            msg = '%s: %s' % (msg, routing_key)
        super().__init__(msg)
        self.routing_key = routing_key
