"""
Gateway entre Blynk et SenseursPassifs de MilleGrilles
"""
import logging
import json

from blynklib import Blynk
from threading import Thread, Event
from typing import Optional

from millegrilles.dao.ConfigurationDocument import ContexteRessourcesDocumentsMilleGrilles
from millegrilles.dao.MessageDAO import BaseCallback
from millegrilles import Constantes
from millegrilles.Constantes import SenseursPassifsConstantes


class ConstantesGatewayBlynk:
    pass


class GatewayBlynk:
    """
    Gestionnaire de gateway, supporte tous les noeuds prive configures pour Blynk
    """

    def __init__(self, contexte: ContexteRessourcesDocumentsMilleGrilles):
        self._contexte = contexte

        self.__channel = None

        self._blynk_devices = dict()
        self._senseur_devicevpin = dict()  # Mapping de cle:uuid_senseur vers le value:{noeud_id, vpin} correspondant

        self._traitement_messages = None

        self.__thread: Optional[Thread] = None
        self.__stop_event = Event()

        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

    def configurer(self):
        """
        Charger la configuration des noeuds prives/publics avec configuration Blynk
        :return:
        """
        collection = self._contexte.document_dao.get_collection(SenseursPassifsConstantes.COLLECTION_DOCUMENTS_NOM)

        filtre_noeuds = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: SenseursPassifsConstantes.LIBVAL_DOCUMENT_NOEUD,
            Constantes.DOCUMENT_INFODOC_SECURITE: {'$in': [Constantes.SECURITE_PUBLIC, Constantes.SECURITE_PRIVE]}
        }
        noeuds = collection.find(filtre_noeuds)

        for noeud in noeuds:
            self.configurer_gateway(noeud)

        # Charger les VPINs des senseurs
        filtre_senseurs = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: SenseursPassifsConstantes.LIBVAL_DOCUMENT_SENSEUR,
            Constantes.DOCUMENT_INFODOC_SECURITE: {'$in': [Constantes.SECURITE_PUBLIC, Constantes.SECURITE_PRIVE]},
        }
        senseurs_device = collection.find(filtre_senseurs)
        for doc_senseur in senseurs_device:
            for type_senseur, senseur in doc_senseur['senseurs'].items():
                vpin = senseur.get('blynk_vpin')
                if vpin:
                    # C'est un senseur associe a un vpin, on fait le mapping
                    senseur_path = '/'.join([doc_senseur[SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR], type_senseur])
                    self.__logger.info("Blynk %s = vpin %d" % (senseur_path, vpin))
                    self._senseur_devicevpin[senseur_path] = {'noeud_id': doc_senseur['noeud_id'], 'vpin': vpin}

                    noeud_id = doc_senseur[SenseursPassifsConstantes.TRANSACTION_NOEUD_ID]
                    blynk_device = self._blynk_devices.get(noeud_id)
                    if blynk_device:
                        blynk_device.enregistrer_read(vpin)

                        # Enregistrer derniere valeur dans le cache
                        valeur = senseur.get('valeur')
                        if valeur:
                            blynk_device.virtual_write(vpin, valeur)

        # Enregistrer MQ
        self._traitement_messages = TraitementMessages(self._contexte, self)

        routing = [
            'evenement.SenseursPassifs.#.lecture',
            'transaction.SenseursPassifs.#.majNoeud',
            'transaction.SenseursPassifs.#.majSenseur',
        ]

        self.contexte.message_dao.inscrire_topic(
            self.contexte.configuration.exchange_prive,
            routing,
            self._traitement_messages.callbackAvecAck
        )

        # Tenter de s'inscrire a l'echange protege
        self.contexte.message_dao.inscrire_topic(
            self.contexte.configuration.exchange_protege,
            routing,
            self._traitement_messages.callbackAvecAck
        )

    def configurer_gateway(self, noeud_doc: dict):
        """
        Configure un gateway blynk si tous les parametres sont presents

        :param noeud_doc:
        :return:
        """
        noeud_id = noeud_doc['noeud_id']
        blynk_gateway = self._blynk_devices.get(noeud_id)

        securite = noeud_doc.get(Constantes.DOCUMENT_INFODOC_SECURITE)
        blynk_auth = noeud_doc.get('blynk_auth')
        blynk_host = noeud_doc.get('blynk_host')
        blynk_port = noeud_doc.get('blynk_port')

        if securite in [Constantes.SECURITE_PRIVE, Constantes.SECURITE_PUBLIC] and \
                blynk_auth and blynk_host and blynk_port:
            # S'assurer que le gateway existe et est configure
            if blynk_gateway is not None:
                # Verifier si la configuration a changee
                blynk_gateway.update_config(blynk_auth, blynk_host, blynk_port, self._contexte.configuration.mq_cafile)
            else:
                blynk_gateway = GatewayNoeud(blynk_auth, blynk_host, blynk_port, self._contexte.configuration.mq_cafile)

                # Enregistrer vpins connus pour ce noeud
                for senseur in self._senseur_devicevpin.values():
                    noeud_id_senseur = senseur['noeud_id']
                    if noeud_id_senseur == noeud_id:
                        vpin = senseur['vpin']
                        blynk_gateway.enregistrer_read(vpin)

                # Faire copie du dict pour eviter erreur de mutation (RuntimeError)
                copie_dict_devices = dict(self._blynk_devices)
                copie_dict_devices[noeud_id] = blynk_gateway
                self._blynk_devices = copie_dict_devices

        elif blynk_gateway is not None:
            # Le device existe - il faut l'envelever (securite n'est pas prive/public ou configuration retiree)
            self.__logger.info("Blynk: Desactiver gateway %s" % noeud_id)
            blynk_gateway.fermer()

            # Faire copie du dict pour eviter erreur de mutation (RuntimeError)
            copie_dict_devices = dict(self._blynk_devices)
            del copie_dict_devices[noeud_id]  # Supprimer entree device
            self._blynk_devices = copie_dict_devices

    def start(self):
        """
        :return:
        """
        self.__thread = Thread(name="blynk", target=self.run)
        self.__thread.run()

    def fermer(self):
        self.__stop_event.set()

    def run(self):
        while not self.__stop_event.is_set():

            if len(self._blynk_devices) > 0:
                # Executer un cycle pour chaque device
                for noeud_id, blynk in self._blynk_devices.items():
                    try:
                        blynk.run()
                    except Exception:
                        self.__logger.exception("Erreur blynk noeud_id: %s" % noeud_id)
            else:
                self.__stop_event.wait(5)

        for noeud_id, blynk in self._blynk_devices.items():
            try:
                blynk.disconnect()
            except:
                self.__logger.info("Erreur dexonnexion %s" % noeud_id)

    def transmettre_lecture(self, uuid_senseur, type_senseur, valeur):
        cle = '/'.join([uuid_senseur, type_senseur])
        senseur_config = self._senseur_devicevpin.get(cle)
        if senseur_config:
            noeud_id = senseur_config['noeud_id']
            vpin = senseur_config['vpin']
            self.__logger.debug("Transmettre noeud: %s, vpin: %s, valeur: %s" % (noeud_id, vpin, valeur))
            blynk = self._blynk_devices.get(noeud_id)
            if blynk:
                blynk.virtual_write(vpin, valeur)

    def maj_noeud(self, message_dict: dict):
        noeud_id = message_dict[SenseursPassifsConstantes.TRANSACTION_NOEUD_ID]

        # Charger document courant
        collection = self._contexte.document_dao.get_collection(SenseursPassifsConstantes.COLLECTION_DOCUMENTS_NOM)
        noeud_doc = collection.find_one({
            Constantes.DOCUMENT_INFODOC_LIBELLE: SenseursPassifsConstantes.LIBVAL_DOCUMENT_NOEUD,
            SenseursPassifsConstantes.TRANSACTION_NOEUD_ID: noeud_id,
        })
        noeud_doc.update(message_dict)  # Override du document avec nouvelles valeurs de la transaction

        self.configurer_gateway(noeud_doc)

    def maj_senseur(self, message_dict: dict):
        pass

    @property
    def contexte(self):
        return self._contexte


class GatewayNoeud:
    """
    Gateway et connexion pour un device Blynk associe a un noeud prive MilleGrille
    """

    def __init__(self, auth_token: str, host: str, port: int, ca_file: str):
        self.__auth_token = auth_token

        self.__host: Optional[str] = None
        self.__port: Optional[str] = None
        self.__ca_file: Optional[str] = None
        self._blynk: Optional[Blynk] = None

        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__cache_valeurs = dict()

        self.__vpins_read = set()

        # Creer client Blynk
        self.update_config(auth_token, host, port, ca_file)

    def update_config(self, auth_token: str, host: str, port: int, ca_file: str):
        if self.__auth_token != auth_token or \
                self.__host != host or \
                self.__port != port or \
                self.__ca_file != ca_file:

            if self._blynk is not None:
                self._blynk.disconnect()

            self.__auth_token = auth_token
            self.__host = host
            self.__port = port
            self.__ca_file = ca_file

            self._blynk = Blynk(
                self.__auth_token, server=self.__host, port=self.__port,
                ssl_cert=self.__ca_file,
                heartbeat=10, rcv_buffer=1024, log=self.__logger.debug
            )

            # Re-enregistrer evenements
            for vpin in self.__vpins_read:
                self.enregistrer_read(vpin)

    def virtual_write(self, v_pin, val):
        self.__cache_valeurs[str(v_pin)] = val
        if self._blynk.connected():
            self._blynk.virtual_write(v_pin, val)

    def enregistrer_read(self, v_pin):
        blynk = self._blynk
        self.__vpins_read.add(v_pin)

        @blynk.handle_event('read V' + str(v_pin))
        def read_virtual_pin_handler(pin):
            valeur = self.__cache_valeurs[str(pin)]
            self._blynk.virtual_write(pin, valeur)

    def run(self):
        self._blynk.run()

    def fermer(self):
        self._blynk.disconnect()


class TraitementMessages(BaseCallback):
    """
    Recoit les messages d'evenements et changements de configuration SenseursPassifs
    """

    def __init__(self, contexte: ContexteRessourcesDocumentsMilleGrilles, gateway: GatewayBlynk):
        super().__init__(contexte)
        self._gateway = gateway

    def traiter_message(self, ch, method, properties, body):
        message_dict = json.loads(body.decode('utf-8'))
        routing_key = method.routing_key
        action = routing_key.split('.')[-1]

        if action == 'lecture':
            self.traiter_lecture(message_dict)
        elif action == 'majNoeud':
            self._gateway.maj_noeud(message_dict)
        elif action == 'majSenseur':
            self._gateway.maj_senseur(message_dict)

    def traiter_lecture(self, message_dict: dict):
        uuid_senseur = message_dict.get(SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR)
        senseurs = message_dict.get('senseurs')

        if uuid_senseur and senseurs:
            for type_senseur, senseur in senseurs.items():
                valeur = senseur.get('valeur')
                if valeur:
                    self._gateway.transmettre_lecture(uuid_senseur, type_senseur, valeur)
