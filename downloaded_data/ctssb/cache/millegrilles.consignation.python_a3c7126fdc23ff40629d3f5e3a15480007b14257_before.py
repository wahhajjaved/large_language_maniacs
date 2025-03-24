# Gestion des messages via Pika.
import codecs
import pika
import json
import traceback
import logging
import ssl

from threading import Lock, RLock, Event, Thread, Barrier

from millegrilles import Constantes
from millegrilles.util.JSONEncoders import MongoJSONEncoder
from pika.credentials import PlainCredentials, ExternalCredentials
from pika.exceptions import AMQPConnectionError

''' 
DAO vers la messagerie
Connection a un moteur de messagerie via Pika.
'''

jsonEncoder = MongoJSONEncoder()


class PikaDAO:

    def __init__(self, configuration):
        self._logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))
        self.lock_transmettre_message = RLock()
        self.lock_initialiser_connections = Barrier(2)  # S'assurer d'avoir consumer et publisher

        self._attendre_channel = Event()
        self.configuration = configuration

        self.__stop_event = Event()

        # Wrappers pour connexions MQ
        # Pour les modules avec beaucoup d'activite bidirectionnelle simultanee, il faut au moins une connexion
        # consumer et une connexion publisher.
        self.__connexionmq_consumer = ConnexionWrapper(
            self.configuration, self.__stop_event)
        self.__connexionmq_publisher = ConnexionWrapper(
            self.configuration, self.__stop_event)
        self.__connexionsmq = [self.__connexionmq_consumer, self.__connexionmq_publisher]

        self._queue_reponse = None

        self._executer_configurer_rabbitmq = False

        self._actif = False
        self._in_error = True

        # Thread utilisee pour verifier le fonctionnement correct de MQ
        self.__maintenance_event = Event()
        self._intervalle_maintenance = 30  # secondes entre execution de maintenance de connexion
        self.__thread_maintenance = Thread(target=self.executer_maintenance_connexions, name="MQ-Maint")
        self.__thread_maintenance.start()

        # Liste des processus qui veulent se faire allouer un channel au demarrage
        # Methode appellee: channel_open(channel)
        self.__liste_listeners_channels = None

        self.json_helper = JSONHelper()

    def register_channel_listener(self, listener):
        self._logger.info("Enregistrer listener pour channel %s" % listener.__class__.__name__)
        self.__connexionmq_consumer.register_channel_listener(listener)

    def connecter(self):

        barrier = Barrier(len(self.__connexionsmq) + 1)  # Nb connexions + 1 (self)
        for connexion in self.__connexionsmq:
            connexion.connecter(barrier)

        # Attendre que les connexions soient pretes ou 10 secondes
        barrier.wait(20)
        if barrier.broken:
            self._logger.error("Initialisation connexions a echoue")
            self.enter_error_state()
            raise Exception("Initialisation connexion echoue")
        else:
            # Informer toutes les threads en attente que la connexion est prete
            self._attendre_channel.set()

    def configurer_rabbitmq(self):

        # Generer liste de callbacks
        nom_echanges = [
            self.configuration.exchange_middleware,
            self.configuration.exchange_inter,
            self.configuration.exchange_noeuds,
            self.configuration.exchange_public
        ]

        self.attendre_channel(timeout=30)
        if not self._attendre_channel.is_set():
            raise Exception("Channel MQ n'est pas ouvert")

        setupHandler = PikaSetupHandler()

        # Q nouvelle.transactions, existe sur tous les exchanges
        for nom_echange in nom_echanges:
            setupHandler.add_configuration(PikaSetupCallbackHandler(
                self.__channel_consumer,
                nom_echange,
                self.queuename_nouvelles_transactions(),
                [Constantes.TRANSACTION_ROUTING_NOUVELLE],
                queue_durable=True,
                arguments={'x-queue-mode': 'lazy'}
            ))

        # Ajouter TTL de 30 secondes pour certaines Q

        exchange_middleware = self.configuration.exchange_middleware
        setupHandler.add_configuration(PikaSetupCallbackHandler(
            self.__channel_consumer,
            exchange_middleware,
            self.queuename_nouvelles_transactions(),
            [Constantes.TRANSACTION_ROUTING_NOUVELLE],
            queue_durable=True,
            arguments={'x-queue-mode': 'lazy'},
        ))

        setupHandler.add_configuration(PikaSetupCallbackHandler(
            self.__channel_consumer,
            exchange_middleware,
            self.queuename_evenements_transactions(),
            [Constantes.TRANSACTION_ROUTING_EVENEMENT],
            queue_durable=True
        ))

        # Q erreurs
        setupHandler.add_configuration(PikaSetupCallbackHandler(
            self.__channel_consumer,
            exchange_middleware,
            self.queuename_erreurs_processus(),
            ['processus.erreur'],
            queue_durable=True,
            arguments={'x-queue-mode': 'lazy'},
        ))

        # Q entretien (ceduleur)
        setupHandler.add_configuration(PikaSetupCallbackHandler(
            self.__channel_consumer,
            exchange_middleware,
            Constantes.DEFAUT_QUEUE_ENTRETIEN_TRANSACTIONS,
            ['ceduleur.#'],
            queue_durable=False,
            arguments={'x-message-ttl': 30000}
        ))

        # On attend l'execution de la configuration
        configurations_manquantes = None
        for essai in range(2, 5):
            configurations_manquantes = setupHandler.attendre()

            if configurations_manquantes is not None:
                self._logger.warning("Erreur configuration MQ, Q  incompletes: %s" % ['%s/%s' % (c.exchange, c.queue) for c in configurations_manquantes])
                self._logger.warning("On tente de re-executer configuration (essai %d de 3)" % essai)
                setupHandler.executer_incompletes()
            else:
                break

        if configurations_manquantes is not None:
            raise Exception("Configuration Q incomplete: %s" % ['%s/%s' % (c.exchange, c.queue) for c in configurations_manquantes])

    def start_consuming(self):
        self._logger.warning("start_consuming(): Deprecated, gere dans MessageDAO")

    def run_ioloop(self):
        self._logger.warning("run_ioloop(): Deprecated, gere dans MessageDAO")

    def enregistrer_callback(self, queue, callback):
        queue_name = queue
        with self.lock_transmettre_message:
            self.__channel_consumer.basic_consume(callback, queue=queue_name, no_ack=False)

    def inscrire_topic(self, exchange, routing: list, callback):
        def callback_inscrire(
                queue, self=self, exchange_in=exchange, routing_in=frozenset(routing), callback_in=callback):
            nom_queue = queue.method.queue
            self._queue_reponse = nom_queue
            self._logger.debug("Resultat creation queue: %s" % nom_queue)
            bindings = set()
            bindings.update(routing_in)
            bindings.add('reponse.%s' % nom_queue)
            with self.lock_transmettre_message:
                for routing_key in bindings:
                    self.__channel_publisher.queue_bind(queue=nom_queue, exchange=exchange_in, routing_key=routing_key, callback=None)
                tag_queue = self.__channel_consumer.basic_consume(callback_in, queue=nom_queue, no_ack=False)
                self._logger.debug("Tag queue: %s" % tag_queue)

                self._logger.info("Declarer Q exclusive pour routing %s" % str(routing))
                self.__channel_publisher.queue_declare(queue='', exclusive=True, callback=callback_inscrire)

    def demarrer_lecture_nouvelles_transactions(self, callback):
        queue_name = self.configuration.queue_nouvelles_transactions
        with self.lock_transmettre_message:
            self.__channel_consumer.basic_consume(callback, queue=queue_name, no_ack=False)

    def demarrer_lecture_etape_processus(self, callback):
        """ Demarre la lecture de la queue mgp_processus. Appel bloquant. """

        with self.lock_transmettre_message:
            self.__channel_consumer.basic_consume(callback,
                                                  queue=self.queuename_mgp_processus(),
                                                  no_ack=False)
        self.start_consuming()

    ''' 
    Methode generique pour transmettre un evenement JSON avec l'echange millegrilles
    
    :param routing_key: Routing key utilise pour distribuer le message.
    :param message_dict: Dictionnaire du contenu du message qui sera encode en JSON
    '''

    def transmettre_message(self, message_dict, routing_key, delivery_mode_v=1, encoding=json.JSONEncoder, reply_to=None, correlation_id=None, channel=None):

        if self.__connexionmq_consumer is None or self.__connexionmq_consumer.is_closed:
            raise ExceptionConnectionFermee("La connexion Pika n'est pas ouverte")

        if channel is None:
            # Utiliser le channel implicite
            if self.__channel_publisher is None:
                # Le channel n'est pas pret, on va l'attendre max 30 secondes (cycle de maintenance)
                with self.lock_transmettre_message:
                    pass  # On fait juste attendre que le channel soit pret
            channel = self.__channel_publisher

        properties = pika.BasicProperties(delivery_mode=delivery_mode_v)
        if reply_to is not None:
            properties.reply_to = reply_to
        if correlation_id is not None:
            properties.correlation_id = correlation_id

        message_utf8 = self.json_helper.dict_vers_json(message_dict, encoding)
        with self.lock_transmettre_message:
            channel.basic_publish(
                exchange=self.configuration.exchange_middleware,
                routing_key=routing_key,
                body=message_utf8,
                properties=properties,
                mandatory=True)
            self.__stop_event.wait(0.01)  # Throttle

        if channel is self.__channel_publisher:
            # Utiliser pubdog pour la connexion publishing par defaut
            self.__connexionmq_publisher.publish_watch()

        self._in_error = False

    ''' 
    Methode generique pour transmettre un evenement JSON avec l'echange millegrilles

    :param routing_key: Routing key utilise pour distribuer le message.
    :param message_dict: Dictionnaire du contenu du message qui sera encode en JSON
    '''

    def transmettre_message_noeuds(self, message_dict, routing_key, delivery_mode_v=1,
                                   encoding=json.JSONEncoder, reply_to=None, correlation_id=None):

        if self.__connexionmq_consumer is None or self.__connexionmq_consumer.is_closed:
            raise ExceptionConnectionFermee("La connexion Pika n'est pas ouverte")

        properties = pika.BasicProperties(delivery_mode=delivery_mode_v)
        if reply_to is not None:
            properties.reply_to = reply_to
        if correlation_id is not None:
            properties.correlation_id = correlation_id

        message_utf8 = self.json_helper.dict_vers_json(message_dict, encoding)
        with self.lock_transmettre_message:
            self.__channel_publisher.basic_publish(
                exchange=self.configuration.exchange_noeuds,
                routing_key=routing_key,
                body=message_utf8,
                properties=properties,
                mandatory=True)

        # Utiliser pubdog pour la connexion publishing par defaut
        self.__connexionmq_publisher.publish_watch()

        self._in_error = False

    def transmettre_reponse(self, message_dict, replying_to, correlation_id, delivery_mode_v=1, encoding=json.JSONEncoder):

        if self.__connexionmq_publisher is None or self.__connexionmq_publisher.is_closed:
            raise ExceptionConnectionFermee("La connexion Pika n'est pas ouverte")

        properties = pika.BasicProperties(delivery_mode=delivery_mode_v)
        properties.correlation_id = correlation_id

        message_utf8 = self.json_helper.dict_vers_json(message_dict, encoding)
        with self.lock_transmettre_message:
            self.__channel_publisher.basic_publish(
                exchange='',  # Exchange default
                routing_key=replying_to,
                body=message_utf8,
                properties=properties,
                mandatory=True)

        # Utiliser pubdog pour la connexion publishing par defaut
        self.__connexionmq_publisher.publish_watch()

        self._in_error = False

    def transmettre_nouvelle_transaction(self, document_transaction, reply_to, correlation_id, channel=None):
        routing_key = 'transaction.nouvelle'
        # Utiliser delivery mode 2 (persistent) pour les transactions
        self.transmettre_message(
            document_transaction, routing_key, delivery_mode_v=2, reply_to=reply_to, correlation_id=correlation_id, channel=channel)

    def transmettre_commande(self, document_commande, routing_key, channel=None, encoding=MongoJSONEncoder):
        """
        Sert a transmettre une commande vers un noeud
        :param document_commande:
        :param routing_key:
        :param channel:
        :param encoding:
        :return:
        """
        if channel is None:
            channel = self.__channel_publisher

        if self.__connexionmq_consumer is None or self.__connexionmq_consumer.is_closed:
            raise ExceptionConnectionFermee("La connexion Pika n'est pas ouverte")

        properties = pika.BasicProperties(delivery_mode=1)

        message_utf8 = self.json_helper.dict_vers_json(document_commande, encoding)
        with self.lock_transmettre_message:
            channel.basic_publish(
                exchange=self.configuration.exchange_noeuds,
                routing_key=routing_key,
                body=message_utf8,
                properties=properties,
                mandatory=True)

        # Utiliser pubdog pour la connexion publishing par defaut
        if channel is self.__channel_publisher:
            self.__connexionmq_publisher.publish_watch()

        self._in_error = False

    def transmettre_notification(self, document_transaction, sub_routing_key):
        routing_key = 'notification.%s' % sub_routing_key
        # Utiliser delivery mode 2 (persistent) pour les notifications
        self.transmettre_message(document_transaction, routing_key, delivery_mode_v=2)

    def transmettre_demande_certificat(self, fingerprint):
        routing_key = 'pki.requete.%s' % fingerprint
        # Utiliser delivery mode 2 (persistent) pour les notifications
        self.transmettre_message({'fingerprint': fingerprint}, routing_key, delivery_mode_v=2)
        self.transmettre_message_noeuds({'fingerprint': fingerprint}, routing_key, delivery_mode_v=2)

    def transmettre_evenement_persistance(self, id_document, id_transaction, nom_domaine, properties_mq):
        message = {
            Constantes.TRANSACTION_MESSAGE_LIBELLE_ID_MONGO: str(id_document),
            Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID: id_transaction,
            Constantes.EVENEMENT_MESSAGE_EVENEMENT: "transaction_persistee",
            Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE: nom_domaine,
            Constantes.TRANSACTION_MESSAGE_LIBELLE_PROPERTIES_MQ: properties_mq
        }
        message_utf8 = self.json_helper.dict_vers_json(message)
        routing_key = 'destinataire.domaine.%s' % nom_domaine

        with self.lock_transmettre_message:
            self._logger.info("Transmission evenement persistance %s pour %s" % (routing_key, id_transaction))
            self.__channel_publisher.basic_publish(
                exchange=self.configuration.exchange_middleware,
                routing_key=routing_key,
                body=message_utf8)

        self.__connexionmq_publisher.publish_watch()

    ''' 
    Transmet un evenement de ceduleur. Utilise par les gestionnaires (ou n'importe quel autre processus abonne)
    pour declencher des processus reguliers. 
    
    Message: 
    {
      "evenements": "minute",
      "timestamp": {
        "annee": 2018, "mois": 12, "jour": 8, "heure": 9, "minute": 54, "joursemaine": 5
      },
      "indicateurs": [
        "heure", "TIMEZONE", "jour", "mois", "annee", "semaine"
      ]
    }
    
    Les indicateurs speciaux suivants sont ajoutes a la liste "indicateurs" lorsqu'applicable:
    - "heure"    # lorsque minute == 0
    - "UTC"      # Lorsque c'est pour UTC. Autres time zones peuvent etre EST (ou EDT), etc.
    - "jour"     # lorsque heure == 0 et minute == 0
    - "mois"     # lorsque jour == 1 et heure == 0 et minute == 0
    - "annee"    # lorsque mois == 1 et jour == 1 et heure == 0 et minute == 0
    - "semaine"  # lorsque joursemaine == 0 et heure == 0 et minute == 0
    
    Noter que ces memes indicateurs sont aussi ajoutes a la routing key. Il est possible de s'abonner
    uniquement a la notification desiree.
    
    routing_key: 
    - "sansnom.ceduleur.minute" # Cle de base (sansnom est le nom de la MilleGrille)
    - "sansnom.ceduleur.minute.heure.jour.mois.annee.semaine": Lorsque tous les indicateurs sont inclus
    - "sansnom.ceduleur.minute.heure.jour": Nouvelle journee a minuit.
    '''
    def transmettre_evenement_ceduleur(self, ts_dict, indicateurs):

        message = {
            Constantes.EVENEMENT_MESSAGE_EVENEMENT: Constantes.EVENEMENT_CEDULEUR,
            'timestamp': ts_dict,
            'indicateurs': indicateurs
        }
        message_utf8 = self.json_helper.dict_vers_json(message)

        # Creer la routing key avec les indicateurs (join l'array avec .)
        ind_routing_key = '.'.join(indicateurs)
        if len(ind_routing_key) > 0:
            ind_routing_key = '.%s' % ind_routing_key
        routing_key = 'ceduleur.minute%s' % ind_routing_key

        with self.lock_transmettre_message:
            self.__channel_publisher.basic_publish(
                exchange=self.configuration.exchange_middleware,
                routing_key=routing_key,
                body=message_utf8)
            self.__channel_consumer.basic_publish(
                exchange=self.configuration.exchange_noeuds,
                routing_key=routing_key,
                body=message_utf8)

    '''
    Transmet un declencheur pour une etape de processus MilleGrilles.
    
    :param id_document: Document contenant l'information pour ce processus.
    :param nom_process: Nom du processus a executer.
    :param nom_etape: (Optionnel) Nom de la prochaine etape a declencher. Defaut: initiale
    :param evenement_declencheur: (Optionnel) Evenement qui a declenche l'execution de l'etape courante.
    :param dict_parametres: (Optionnel) Parametres a utiliser pour la prochaine etape du processus.
    '''

    def transmettre_evenement_mgpprocessus(self, nom_domaine: str, id_document, nom_processus, nom_etape='initiale',
                                           tokens=None,
                                           info=None,
                                           channel=None):
        if channel is None:
            channel = self.__channel_publisher

        message = {
            Constantes.PROCESSUS_MESSAGE_LIBELLE_ID_DOC_PROCESSUS: str(id_document),
            Constantes.PROCESSUS_MESSAGE_LIBELLE_PROCESSUS: nom_processus,
            Constantes.PROCESSUS_DOCUMENT_LIBELLE_ETAPESUIVANTE: nom_etape
        }

        if tokens is not None:
            message[Constantes.PROCESSUS_DOCUMENT_LIBELLE_TOKEN_RESUMER] = tokens

        if info is not None:
            message[Constantes.PROCESSUS_DOCUMENT_LIBELLE_INFO] = info

        message_utf8 = self.json_helper.dict_vers_json(message)

        routing_key = 'processus.domaine.%s.%s.%s' % \
                      (nom_domaine, nom_processus, nom_etape)

        with self.lock_transmettre_message:
            channel.basic_publish(exchange=self.configuration.exchange_middleware,
                                                   routing_key=routing_key,
                                                   body=message_utf8)

        if channel is self.__channel_publisher:
            self.__connexionmq_publisher.publish_watch()


    def transmettre_evenement_mgp_resumer(self, nom_domaine, id_document_declencheur, tokens: list,
                                          id_document_processus_attente=None,
                                          channel=None):
        if channel is None:
            channel = self.__channel_publisher

        message = {
            Constantes.EVENEMENT_MESSAGE_EVENEMENT: Constantes.EVENEMENT_RESUMER,
            Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE: nom_domaine,
            Constantes.PROCESSUS_MESSAGE_LIBELLE_ID_DOC_PROCESSUS_DECLENCHEUR: str(id_document_declencheur),
            Constantes.PROCESSUS_MESSAGE_LIBELLE_RESUMER_TOKENS: tokens,
        }
        if id_document_processus_attente is not None:
            message[Constantes.PROCESSUS_MESSAGE_LIBELLE_ID_DOC_PROCESSUS_ATTENTE] = str(id_document_processus_attente)

        message_utf8 = self.json_helper.dict_vers_json(message)
        routing_key = 'processus.domaine.%s.resumer' % nom_domaine

        with self.lock_transmettre_message:
            channel.basic_publish(exchange=self.configuration.exchange_middleware,
                                                   routing_key=routing_key,
                                                   body=message_utf8)

        self.__connexionmq_publisher.publish_watch()

    def transmettre_evenement_mgp_verifier_resumer(self, nom_domaine, id_document_processus_attente, tokens: list,
                                                   channel=None):
        if channel is None:
            channel = self.__channel_publisher

        message = {
            Constantes.EVENEMENT_MESSAGE_EVENEMENT: Constantes.EVENEMENT_VERIFIER_RESUMER,
            Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE: nom_domaine,
            Constantes.PROCESSUS_MESSAGE_LIBELLE_ID_DOC_PROCESSUS_ATTENTE: str(id_document_processus_attente),
            Constantes.PROCESSUS_MESSAGE_LIBELLE_RESUMER_TOKENS: tokens,
        }

        message_utf8 = self.json_helper.dict_vers_json(message)
        routing_key = 'processus.domaine.%s.verifier.resumer' % nom_domaine

        with self.lock_transmettre_message:
            channel.basic_publish(exchange=self.configuration.exchange_middleware,
                                  routing_key=routing_key,
                                  body=message_utf8)

        self.__connexionmq_publisher.publish_watch()

    '''
    Methode a utiliser pour mettre fin a l'execution d'un processus pour une transaction suite a une erreur fatale.
    
    :param id_document: Document affecte (Object ID dans Mongo)
    :param id_transaction: (Optionnel) Identificateur de la transaction qui est bloquee
    :param detail: (Optionnel) Information sur l'erreur.
    '''

    def transmettre_erreur_transaction(self, id_document, id_transaction=None, detail=None):

        message = {
            Constantes.MONGO_DOC_ID: id_document,
        }
        if id_transaction is not None:
            message[Constantes.TRANSACTION_MESSAGE_LIBELLE_ID_MONGO] = id_transaction
        if detail is not None:
            message["erreur"] = str(detail)
            message["stacktrace"] = traceback.format_exception(etype=type(detail), value=detail,
                                                               tb=detail.__traceback__)

        message_utf8 = self.json_helper.dict_vers_json(message)

        with self.lock_transmettre_message:
            self.__channel_publisher.basic_publish(exchange=self.configuration.exchange_middleware,
                                                   routing_key='transaction.erreur',
                                                   body=message_utf8)

        self.__connexionmq_publisher.publish_watch()

    '''
     Methode a utiliser pour mettre fin a l'execution d'un processus pour une transaction suite a une erreur fatale.

     :param id_document: Document affecte (Object ID dans Mongo)
     :param id_transaction: (Optionnel) Identificateur de la transaction qui est bloquee
     :param detail: (Optionnel) Information sur l'erreur.
     '''

    def transmettre_erreur_processus(self, id_document_processus, message_original=None, detail=None):

        message = {
            "_id": id_document_processus,
        }
        if message_original is not None:
            message['message_original'] = message_original
        if detail is not None:
            message["erreur"] = str(detail)
            message["stacktrace"] = traceback.format_exception(etype=type(detail), value=detail,
                                                               tb=detail.__traceback__)

        message_utf8 = self.json_helper.dict_vers_json(message)

        with self.lock_transmettre_message:
            self.__channel_publisher.basic_publish(exchange=self.configuration.exchange_middleware,
                                                   routing_key='processus.erreur',
                                                   body=message_utf8)
        self.__connexionmq_publisher.publish_watch()

    # Mettre la classe en etat d'erreur
    def enter_error_state(self):
        self._logger.warning("MQ Enter error state")
        self._in_error = True

        for connexion in self.__connexionsmq:
            connexion.enter_error_state()

        self.__maintenance_event.set()

    # Se deconnecter de RabbitMQ
    def deconnecter(self):
        self._actif = False
        self.__stop_event.set()
        self.__maintenance_event.set()

        for connexion in self.__connexionsmq:
            connexion.deconnecter()

    def executer_maintenance_connexions(self):
        self._logger.info("Demarrage maintenance")
        self.__maintenance_event.wait(self._intervalle_maintenance)  # Attendre avant premier cycle de maintenance

        while not self.__stop_event.is_set():
            self.__maintenance_event.clear()
            self._logger.debug("Maintenance MQ, in error: %s" % self._in_error)

            for connexion in self.__connexionsmq:
                try:
                    if connexion.is_closed:
                        self._logger.warning("La connection MQ est fermee. On tente de se reconnecter.")
                        connexion.connecter()
                    else:
                        self._logger.debug("Rien a faire pour reconnecter a MQ")

                except Exception as e:
                    self._logger.exception("Erreur dans boucle de maintenance: %s" % str(e), exc_info=e)
                    self.enter_error_state()

            self.__maintenance_event.wait(self._intervalle_maintenance)

        self._logger.info("MQ-Maint closing")

    def attendre_channel(self, timeout):
        self._attendre_channel.wait(timeout)

    def queuename_nouvelles_transactions(self):
        return self.configuration.queue_nouvelles_transactions

    def queuename_evenements_transactions(self):
        return self.configuration.queue_evenements_transactions

    def queuename_erreurs_transactions(self):
        return self.configuration.queue_erreurs_transactions

    def queuename_erreurs_processus(self):
        return self.configuration.queue_erreurs_processus

    def queuename_mgp_processus(self):
        return self.configuration.queue_mgp_processus

    @property
    def __channel_consumer(self):
        return self.__connexionmq_consumer.channel

    @property
    def __channel_publisher(self):
        return self.__connexionmq_publisher.channel

    @property
    def queue_reponse(self):
        return self._queue_reponse

    @property
    def in_error(self):
        return self._in_error


class ConnexionWrapper:
    """
    Helper pour les connexions MQ.
    Prepare une connexion et un channel. Lance le ioloop dans une thread.
    """

    def __init__(self, configuration, stop_event: Event, heartbeat=None):
        self.configuration = configuration
        self.__stop_event = stop_event
        self.__heartbeat = heartbeat
        self._logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

        self.__connexionmq = None
        self.__channel = None
        self.__thread_ioloop = None

        self.__publish_confirm_event = Event()
        self.__published = False
        self.__thread_publishing_watchdog = None

        self._in_error = False
        self.__liste_listeners_channels = None

        self.__lock_init = None

        self.__last_publish = None

    def preparer_connexion(self):
        """ Retourne un dictionnaire avec les parametres de connexion a RabbitMQ """

        if self.__heartbeat is None:
            self.__heartbeat = self.configuration.mq_heartbeat

        connection_parameters = {
            'host': self.configuration.mq_host,
            'port': self.configuration.mq_port,
            'virtual_host': self.configuration.nom_millegrille,
            'heartbeat': self.__heartbeat,
            'blocked_connection_timeout': self.configuration.mq_heartbeat / 3
        }

        self._logger.info("Connecter RabbitMQ, parametres de connexion: %s" % str(connection_parameters))

        if self.configuration.mq_auth_cert == 'on':
            # Va faire la connection via plugin configure dans MQ, normalement c'est rabbitmq_auth_mechanism_ssl
            connection_parameters['credentials'] = ExternalCredentials()
        else:
            credentials = {
                'username': self.configuration.mq_user,
                'password': self.configuration.mq_password,
                'erase_on_connect': True
            }
            connection_parameters['credentials'] = PlainCredentials(**credentials)

        if self.configuration.mq_ssl == 'on':
            ssl_options = {
                'ssl_version': ssl.PROTOCOL_TLSv1_2,
                'keyfile': self.configuration.mq_keyfile,
                'certfile': self.configuration.mq_certfile,
                'ca_certs': self.configuration.mq_cafile,
                'cert_reqs': ssl.CERT_REQUIRED
            }

            connection_parameters['ssl'] = True
            connection_parameters['ssl_options'] = ssl_options

        return connection_parameters

    def connecter(self, lock_init: Barrier = None):
        """
        Connecter au serveur RabbitMQ
        Le callback est une methode qui va etre appelee lorsqu'un message est recu

        :param lock_init: Barrier pour synchroniser toutes les connexions
        :return: Connexion a RabbitMQ.
        """

        self._logger.info("Connecter RabbitMQ")
        self.__lock_init = lock_init

        if self.__connexionmq is not None:
            self._logger.warning("Appel de connecter avec connection deja ouverte")
            connectionmq = self.__connexionmq
            self.__connexionmq = None
            self.__channel = None
            self.__thread_ioloop = None

            try:
                connectionmq.close()
            except Exception as e:
                self._logger.debug("Erreur fermeture MQ avant de reconnecter: %s" % str(e))

        try:
            parametres_connexion = self.preparer_connexion()
            parametres = pika.ConnectionParameters(**parametres_connexion)
            self.__connexionmq = pika.SelectConnection(
                parameters=parametres,
                on_open_callback=self.__on_connection_open,
                on_close_callback=self.__on_connection_close,
            )
            self.__thread_ioloop = Thread(name='MQ-IOloop', target=self.__run_ioloop, daemon=True)
            self.__thread_ioloop.start()  # Va faire un hook avec la nouvelle connexion MQ immediatement

        except Exception as e:
            self.enter_error_state()
            raise e  # S'assurer de mettre le flag d'erreur

        return self.__connexionmq

    def deconnecter(self):
        if self.__connexionmq is not None:
            try:
                self.__connexionmq.close()
            finally:
                self.__connexionmq = None

        self.__publish_confirm_event.set()
        self.__channel = None
        self.__thread_ioloop = None

    def register_channel_listener(self, listener):
        self._logger.info("Enregistrer listener pour channel %s" % listener.__class__.__name__)
        if self.__liste_listeners_channels is None:
            self.__liste_listeners_channels = list()
        self.__liste_listeners_channels.append(listener)
        self._logger.info("On a %d listeners de channels" % len(self.__liste_listeners_channels))

        # On verifie si on peut ouvrir le channel immediatement
        if self.__connexionmq is not None and not self.__connexionmq.is_closed and not self._in_error:
            self.__ouvrir_channel_listener(listener)

    # Mettre la classe en etat d'erreur
    def enter_error_state(self):
        self._logger.warning("MQ Enter error state")
        self._in_error = True

        try:
            if self.__channel is not None:
                self.__channel.close()
        except Exception as e:
            self._logger.warning("MessageDAO.enterErrorState: Erreur stop consuming %s" % str(e))
        finally:
            self.__channel = None

        try:
            if self.__connexionmq is not None:
                self.__connexionmq.close()
        except Exception as e:
            self._logger.info("Erreur fermeture connexion dans enter_error_state(): %s" % str(e))
        finally:
            self.__connexionmq = None
            self.__thread_ioloop = None

    def executer_maintenance(self):
        self._logger.debug("Maintenance connexion MQ, in error: %s" % self._in_error)
        try:
            if self.__connexionmq is not None and self.__channel is None:
                self._logger.error("La connection MQ est invalide - channel n'est pas ouvert.")
                self.enter_error_state()
            elif self.__connexionmq is None or self.__connexionmq.is_closed:
                self._logger.warning("La connection MQ est fermee. On tente de se reconnecter.")
                self.connecter()
            else:
                self._logger.debug("Rien a faire pour reconnecter a MQ")

                # Verifier si les listeners fonctionnent bien
                if self.__liste_listeners_channels is not None:
                    for listener in self.__liste_listeners_channels:
                        if 'is_channel_open' in dir(listener):  # Methode est optionnelle
                            if not listener.is_channel_open():
                                self._logger.warning("Re-ouverture d'un channel de listener")
                                self.__ouvrir_channel_listener(listener)

        except Exception as e:
            self._logger.exception("Erreur dans boucle de maintenance: %s" % str(e), exc_info=e)
            self.enter_error_state()

    def __run_ioloop(self):
        self._logger.info("Demarrage MQ-IOLoop")
        try:
            self.__connexionmq.ioloop.start()
        except AMQPConnectionError as e:
            self._logger.error("Erreur ouverture connexion MQ: %s" % str(e))
            self.enter_error_state()
        self._logger.info("Fin execution MQ-IOLoop")

    def __on_connection_open(self, connection):
        self._logger.info("Callback connection, on ouvre le channel")
        connection.add_on_close_callback(self.__on_connection_close)
        connection.channel(on_open_callback=self.__on_channel_open)

        # Aussi allouer un channel a chaque listener inscrit
        if self.__liste_listeners_channels is not None:
            for listener in self.__liste_listeners_channels:
                self.__ouvrir_channel_listener(listener)

    def __on_channel_open(self, channel):
        self.__channel = channel
        channel.basic_qos(prefetch_count=1)
        channel.add_on_close_callback(self.__on_channel_close)
        channel.confirm_delivery(self.__confirm_delivery)
        channel.add_on_flow_callback(self.__on_flow)
        channel.add_on_return_callback(self.__on_return)
        self._in_error = False

        self.__stop_event.clear()
        if self.__lock_init is not None:
            self.__lock_init.wait()  # Permet de synchroniser le demarrage
        self.__lock_init = None

        self._logger.info("Connexion / channel prets")

    def __on_connection_close(self, connection=None, code=None, reason=None):
        self.__connexionmq = None
        self.__channel = None
        self.__thread_ioloop = None
        if not self.__stop_event.is_set():
            self._logger.error("Connection fermee anormalement: %s, %s" % (code, reason))
            self.enter_error_state()
        else:
            self._logger.info("Connection fermee normalement: %s, %s" % (code, reason))

    def __on_channel_close(self, channel=None, code=None, reason=None):
        self._logger.warning("Channel ferme: %s, %s" % (code, reason))
        self.__channel = None
        if not self.__stop_event.is_set():
            self._in_error = True  # Au cas ou la fermeture ne soit pas planifiee

    def __on_flow(self, frame):
        self._logger.warning("Flow callback: %s" % str(frame))

    def __on_return(self, channel, method, properties, body):
        self._logger.warning("Return callback %s:\n%s" % (str(method), str(body)))

    def __ouvrir_channel_listener(self, listener):
        self.__connexionmq.channel(on_open_callback=listener.on_channel_open)

    def __confirm_delivery(self, frame):
        self._logger.info("Delivery: %s" % str(frame))
        if isinstance(frame.method, pika.spec.Basic.Nack):
            self._logger.error("Delivery NACK")
            self.enter_error_state()
        else:
            self.__publish_confirm_event.set()

    def publish_watch(self):
        """
        Indique qu'on veut savoir si la connexion fonctionne (on s'attend a recevoir un confirm delivery moment donne)
        :return:
        """
        if not self.__published:

            if self.__thread_publishing_watchdog is None:
                self.__thread_publishing_watchdog = Thread(name="PubDog", target=self.__run_publishing_watchdog, daemon=True)
                self.__thread_publishing_watchdog.start()
            else:
                # Reset timer du watchdog, aucun evenement en attente
                self.__publish_confirm_event.set()

            self.__published = True

    def __run_publishing_watchdog(self):
        """
        Main du watchdog de publication. Permet de detecter rapidement une connexion MQ qui ne repond plus.
        """

        self._logger.warning("Demarrage watchdog publishing")

        while not self.__stop_event.is_set():

            if self.__published:

                # Attendre timeout ou confirmation de publication du message
                self.__publish_confirm_event.wait(1)

                if not self.__publish_confirm_event.is_set():
                    self._logger.warning("Confirmation de publish non recue, erreur sur connexion")
                    self.enter_error_state()

                self.__published = False

            # Attendre prochain evenement de publish
            self.__publish_confirm_event.clear()
            self.__publish_confirm_event.wait(600)

    @property
    def channel(self):
        return self.__channel

    @property
    def is_closed(self):
        return self.__connexionmq is None or self.__channel is None or \
               self.__connexionmq.is_closed or self.__channel.is_closed


# Classe avec utilitaires pour JSON
class JSONHelper:

    def __init__(self):
        self.reader = codecs.getreader("utf-8")

    def dict_vers_json(self, enveloppe_dict: dict, encoding=json.JSONEncoder) -> str:
        message_utf8 = json.dumps(enveloppe_dict, sort_keys=True, ensure_ascii=False, cls=encoding)
        return message_utf8

    def bin_utf8_json_vers_dict(self, json_utf8):
        message_json = json_utf8.decode("utf-8")
        dict = json.loads(message_json)
        return dict


class TraitementMessageCallback:
    """
    Classe qui facilite l'implementation de callbacks avec ACK
    """

    def __init__(self, message_dao, configuration):
        self.__json_helper = JSONHelper()
        self.__message_dao = message_dao
        self.__configuration = configuration
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def callbackAvecAck(self, ch, method, properties, body):
        try:
            self.traiter_message(ch, method, properties, body)
        except CertificatInconnu as ci:
            fingerprint = ci.fingerprint
            self.__logger.warning("Certificat inconnu, on fait la demande %s" % fingerprint)
            self.message_dao.transmettre_demande_certificat(fingerprint)
        except Exception as e:
            self.__logger.exception("Erreur dans callbackAvecAck, exception: %s" % str(e))
            self.transmettre_erreur(ch, body, e)
        finally:
            self.transmettre_ack(ch, method)

    def transmettre_ack(self, ch, method):
        with self.message_dao.lock_transmettre_message:
            ch.basic_ack(delivery_tag=method.delivery_tag)

    def transmettre_erreur(self, ch, body, erreur):
        message = {
            "message_original": str(body)
        }
        if erreur is not None:
            message["erreur"] = str(erreur)
            message["stacktrace"] = traceback.format_exception(etype=type(erreur), value=erreur,
                                                               tb=erreur.__traceback__)

        message_utf8 = self.__json_helper.dict_vers_json(message)

        with self.message_dao.lock_transmettre_message:
            ch.basic_publish(exchange=self.__configuration.exchange_middleware,
                             routing_key='processus.erreur',
                             body=message_utf8)

    def decoder_message_json(self, body):
        return self.__json_helper.bin_utf8_json_vers_dict(body)

    @property
    def message_dao(self):
        return self.__message_dao

    @property
    def configuration(self):
        return self.__configuration

    @property
    def json_helper(self):
        return self.__json_helper

    def traiter_message(self, ch, method, properties, body):
        """
        Traitement du message. A implementer dans la sous-classe.
        :param ch:
        :param method:
        :param properties:
        :param body:
        :return:
        """
        raise NotImplemented('traiter_message() methode doit etre implementee')


class BaseCallback(TraitementMessageCallback):

    def __init__(self, contexte):
        super().__init__(message_dao=contexte.message_dao, configuration=contexte.configuration)
        self._contexte = contexte

    @property
    def contexte(self):
        return self._contexte


class TraitementMessageDomaine(TraitementMessageCallback):

    def __init__(self, gestionnaire_domaine):
        super().__init__(message_dao=gestionnaire_domaine.message_dao, configuration=gestionnaire_domaine.configuration)
        self._gestionnaire = gestionnaire_domaine

    @property
    def document_dao(self):
        return self._gestionnaire.document_dao

    @property
    def gestionnaire(self):
        return self._gestionnaire


class TraitementMessageDomaineMiddleware(TraitementMessageDomaine):

    def traiter_message(self, ch, method, properties, body):
        routing_key = method.routing_key
        message_dict = self.json_helper.bin_utf8_json_vers_dict(body)

        # Verifier quel processus demarrer.
        routing_key_sansprefixe = routing_key.replace(
            'destinataire.domaine.',
            ''
        )

        try:
            processus = self.gestionnaire.identifier_processus(routing_key_sansprefixe)
            self.gestionnaire.demarrer_processus(processus, message_dict)
        except Exception as e:
            self.gestionnaire.marquer_transaction_en_erreur(message_dict)
            raise e


class TraitementMessageDomaineRequete(TraitementMessageDomaine):

    def traiter_message(self, ch, method, properties, body):
        message_dict = self.json_helper.bin_utf8_json_vers_dict(body)

        try:
            self.gestionnaire.verificateur_transaction.verifier(message_dict)

            # routing_key = method.routing_key
            # exchange = method.exchange
            # evenement = message_dict.get(Constantes.EVENEMENT_MESSAGE_EVENEMENT)

            resultats = list()
            for requete in message_dict['requetes']:
                resultat = self.executer_requete(requete)
                resultats.append(resultat)

            # Genere message reponse
            self.transmettre_reponse(message_dict, resultats, properties.reply_to, properties.correlation_id)
        except CertificatInconnu as ci:
            fingerprint = ci.fingerprint
            self.message_dao.transmettre_demande_certificat(fingerprint)


    def executer_requete(self, requete):
        collection = self.gestionnaire.get_collection()
        filtre = requete.get('filtre')
        projection = requete.get('projection')
        sort_params = requete.get('sort')
        hint = requete.get('hint')

        if projection is None:
            curseur = collection.find(filtre)
        else:
            curseur = collection.find(filtre, projection)

        if sort_params is not None:
            curseur.sort(sort_params)

        if hint is not None:
            curseur.hint(hint)

        resultats = list()
        for resultat in curseur:
            resultats.append(resultat)

        return resultats

    def transmettre_reponse(self, requete, resultats, replying_to, correlation_id=None):
        # enveloppe_val = generateur.soumettre_transaction(requete, 'millegrilles.domaines.Principale.creerAlerte')
        if correlation_id is None:
            correlation_id = requete[Constantes.TRANSACTION_MESSAGE_LIBELLE_INFO_TRANSACTION][Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID]

        message_resultat = {
            'resultats': resultats,
        }

        self.gestionnaire.generateur_transactions.transmettre_reponse(message_resultat, replying_to, correlation_id)


class TraitementMessageCedule(TraitementMessageDomaine):

    def traiter_message(self, ch, method, properties, body):
        routing_key = method.routing_key
        message_dict = self.json_helper.bin_utf8_json_vers_dict(body)
        evenement = message_dict.get(Constantes.EVENEMENT_MESSAGE_EVENEMENT)

        if evenement == Constantes.EVENEMENT_CEDULEUR:
            self.traiter_evenement(message_dict)
        else:
            raise ValueError("Type de transaction inconnue: routing: %s, message: %s" % (routing_key, evenement))

    def traiter_evenement(self, message):
        self.gestionnaire.traiter_cedule(message)


class PikaSetupCallbackHandler:

    class RoutingKeyCallback:

        def __init__(self, handler, routing_key):
            self.__handler = handler
            self.__routing_key = routing_key

        def callback(self, method):
            self.__handler.routing_key_complete(self.__routing_key)

    def __init__(self, channel, exchange: str, queue: str, routing_keys: list, queue_durable=False, arguments=None):
        """
        Callback qui permet de declarer un exchange / queue pour une liste de routing keys. Garde aussi le compte
        pour savoir si l'exchange, la Q et les routing keys ont ete configures

        RabbitMQ utilise une interface stable, alors declarer les Q et XCHG pluieurs fois ne cause pas de problemes.
        :param exchange:
        :param queue:
        :param routing_keys:
        :param queue_durable:
        """
        self.__channel = channel
        self.__exchange = exchange
        self.__queue = queue
        self.__queue_durable = queue_durable
        self.__routing_keys = routing_keys
        self.__callback_when_done = None
        self.__arguments = arguments

        self.__nombre_routing_keys_restant = 0
        self.__exchange_complete = exchange is None
        self.__queue_complete = queue is None
        if routing_keys is not None:
            self.__nombre_routing_keys_restant = len(routing_keys)

        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def exchange_callback(self, method):
        self.__logger.debug("Exchange configure: %s" % self.exchange)
        self.__exchange_complete = True
        if self.__queue is not None:
            self.__logger.info("Q Declare %s" % self.__queue)
            self.__channel.queue_declare(
                queue=self.__queue,
                durable=self.__queue_durable,
                callback=self.queue_callback,
                arguments=self.__arguments
            )

    def queue_callback(self, method):
        self.__logger.debug("Q configuree: %s" % self.queue)
        self.__queue_complete = True
        if self.__routing_keys is not None:
            for routing_key in self.__routing_keys:
                rk_callback = PikaSetupCallbackHandler.RoutingKeyCallback(self, routing_key)
                self.__channel.queue_bind(
                    exchange=self.__exchange,
                    queue=self.__queue,
                    routing_key=routing_key,
                    callback=rk_callback.callback
                )

    def routing_key_complete(self, routing_key):
        self.__logger.debug("Routing key configuree: %s" % routing_key)
        self.__nombre_routing_keys_restant = self.__nombre_routing_keys_restant - 1

        if self.__callback_when_done is not None and self.complete:
            self.__logger.debug("Configuration complete, exchange/queue: %s/%s" % (self.exchange, self.queue))
            self.__callback_when_done(self)

    def set_callback_when_done(self, callback):
        self.__callback_when_done = callback

    @property
    def channel(self):
        return self.__channel

    @property
    def queue(self):
        return self.__queue

    @property
    def exchange(self):
        return self.__exchange

    @property
    def complete(self):
        return self.__queue_complete and self.__exchange_complete and self.__nombre_routing_keys_restant <= 0


class PikaSetupHandler:

    def __init__(self):
        self.__config_list = list()
        self.__wait_event = Event()
        self.__config_completee = list()

        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def add_configuration(self, handler: PikaSetupCallbackHandler):
        self.__logger.debug("Ajout configuration exchange/queue: %s/%s" % (handler.exchange, handler.queue))
        handler.set_callback_when_done(self.config_completee)
        self.__config_list.append(handler)
        self.executer_exchange(handler)

    def executer_exchange(self, handler):
        self.__logger.debug("Executer configuration exchange/queue: %s/%s" % (handler.exchange, handler.queue))
        handler.channel.exchange_declare(
            exchange=handler.exchange,
            exchange_type='topic',
            durable=True,
            callback=handler.exchange_callback
        )

    def config_completee(self, handler: PikaSetupCallbackHandler):
        self.__config_completee.append(handler)

        if len(self.__config_completee) == len(self.__config_list):
            self.__logger.debug("Configuration MQ completee")
            self.__wait_event.set()

    def attendre(self):
        """
        Attend l'execution de la configuration, retourne la liste des configuration incompletes
        :return:
        """
        self.__wait_event.wait(15)

        if self.__wait_event.is_set() or len(self.__config_completee) == len(self.__config_list):
            # Toutes les configurations ont ete appliques
            self.__logger.debug("Attendre - termine, toutes configuration completees")
            return None
        else:
            # Il manque certaines configurations, on fait la liste
            return [c for c in self.__config_list if not c.complete]

    def executer_incompletes(self):
        self.__logger.info("Re-execution config incomplete")
        # Reset execution
        self.__config_list = [c for c in self.__config_list if not c.complete]
        self.__config_completee = list()

        for handler in self.__config_list:
            self.executer_exchange(handler)


class ExceptionConnectionFermee(Exception):
    pass


class CertificatInconnu(Exception):

    def __init__(self, message, errors=None, fingerprint=None):
        super().__init__(message, errors)
        self.errors = errors
        self.__fingerprint = fingerprint

    @property
    def fingerprint(self):
        return self.__fingerprint


class RoutingKeyInconnue(Exception):

    def __init__(self, message, routing_key=None):
        super().__init__(message)
        self.__routing_key = routing_key

    @property
    def routing_key(self):
        return self.__routing_key
