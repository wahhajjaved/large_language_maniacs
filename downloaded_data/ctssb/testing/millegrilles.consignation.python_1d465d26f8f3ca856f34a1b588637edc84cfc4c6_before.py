# Module avec les classes de donnees, processus et gestionnaire de sous domaine millegrilles.domaines.SenseursPassifs
import logging
import json
import datetime

from typing import Optional

from millegrilles import Constantes
from millegrilles.Constantes import SenseursPassifsConstantes
from millegrilles.Domaines import GestionnaireDomaineStandard, TraitementMessageDomaineRequete, TraitementRequetesProtegees
from millegrilles.Domaines import ExchangeRouter, TraitementCommandesSecures
from millegrilles.MGProcessus import MGProcessusTransaction
from millegrilles.dao.MessageDAO import TraitementMessageDomaine
from millegrilles.transaction.GenerateurTransaction import TransactionOperations
from bson.objectid import ObjectId


class TraitementRequetesPubliquesSenseursPassifs(TraitementMessageDomaineRequete):

    def traiter_requete(self, ch, method, properties, body, message_dict):
        routing_key = method.routing_key
        action = routing_key.split('.')[-1]
        if action == SenseursPassifsConstantes.REQUETE_LISTE_NOEUDS:
            reponse = {'resultats': self.gestionnaire.get_liste_noeuds()}
        elif routing_key == 'requete.' + SenseursPassifsConstantes.REQUETE_VITRINE_DASHBOARD:
            reponse = self.gestionnaire.get_vitrine_dashboard()
        else:
            raise Exception("Requete publique non supportee " + routing_key)

        self.transmettre_reponse(message_dict, reponse, properties.reply_to, properties.correlation_id)


class TraitementRequetesProtegeesSenseursPassifs(TraitementRequetesProtegees):

    def traiter_requete(self, ch, method, properties, body, message_dict):
        routing_key = method.routing_key
        action = routing_key.split('.')[-1]
        if action == SenseursPassifsConstantes.REQUETE_LISTE_NOEUDS:
            reponse = {'resultats': self.gestionnaire.get_liste_noeuds()}
        elif action == SenseursPassifsConstantes.REQUETE_LISTE_SENSEURS_NOEUD:
            reponse = {'resultats': self.gestionnaire.get_liste_senseurs_noeud(message_dict)}
        elif routing_key == 'requete.' + SenseursPassifsConstantes.REQUETE_VITRINE_DASHBOARD:
            reponse = self.gestionnaire.get_vitrine_dashboard()
        else:
            super().traiter_requete(ch, method, properties, body, message_dict)
            return

        self.transmettre_reponse(message_dict, reponse, properties.reply_to, properties.correlation_id)


class TraitementCommandeSenseursPassifs(TraitementCommandesSecures):

    def traiter_commande(self, enveloppe_certificat, ch, method, properties, body, message_dict):
        # routing_key = method.routing_key
        #
        # resultat = None
        # if Falserouting_key == 'commande.' + SenseursPassifsConstantes.COMMANDE_RAPPORT_HEBDOMADAIRE:
        #     CommandeGenererRapportHebdomadaire(self.gestionnaire, message_dict).generer()
        # elif routing_key == 'commande.' + SenseursPassifsConstantes.COMMANDE_RAPPORT_ANNUEL:
        #     CommandeGenererRapportAnnuel(self.gestionnaire, message_dict).generer()
        # elif routing_key == 'commande.' + SenseursPassifsConstantes.COMMANDE_DECLENCHER_RAPPORTS:
        #     resultat = CommandeDeclencherRapports(self.gestionnaire, message_dict).declencher()
        # else:
        #     resultat = super().traiter_commande(enveloppe_certificat, ch, method, properties, body, message_dict)

        resultat = super().traiter_commande(enveloppe_certificat, ch, method, properties, body, message_dict)

        return resultat


class TraitementMessageLecture(TraitementMessageDomaine):

    def __init__(self, gestionnaire_domaine):
        super().__init__(gestionnaire_domaine)
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

    def traiter_message(self, ch, method, properties, body):
        lecture = json.loads(body.decode('utf-8'))
        self.traiter_lecture(lecture, method.exchange)

    def traiter_lecture(self, lecture: dict, exchange: str):
        if self.__logger.isEnabledFor(logging.DEBUG):
            self.__logger.debug("Lecture recue : %s" % json.dumps(lecture, indent=2))

        noeud_id = lecture[SenseursPassifsConstantes.TRANSACTION_NOEUD_ID]
        uuid_senseur = lecture[SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR]
        senseurs = lecture['senseurs']

        # Conserver dans staging
        staging = self.gestionnaire.document_dao.get_collection(SenseursPassifsConstantes.COLLECTION_STAGING_NOM)
        staging.insert(lecture)

        # Charger le document du senseur
        collection = self.gestionnaire.document_dao.get_collection(SenseursPassifsConstantes.COLLECTION_DOCUMENTS_NOM)

        filter = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: SenseursPassifsConstantes.LIBVAL_DOCUMENT_SENSEUR,
            SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR: uuid_senseur,
        }
        doc_senseur = collection.find_one(filter)

        if not doc_senseur or doc_senseur.get('noeud_id') is None:
            self.ajouter_senseur(lecture, exchange)
            # Creer un document sommaire qui va etre insere
            doc_senseur = {
                SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR: uuid_senseur,
                'senseurs': dict()
            }

        # Verifier quels senseurs on met a jour
        senseurs_actuels = doc_senseur['senseurs']
        set_ops = dict()
        for cle, donnees in senseurs.items():
            donnees_actuelles = senseurs_actuels.get(cle)
            if donnees_actuelles is None or donnees_actuelles['timestamp'] < donnees['timestamp']:
                for key, value in donnees.items():
                    set_ops['senseurs.' + cle + '.' + key] = value

        if len(set_ops.keys()) > 0:
            set_on_insert = {
                Constantes.DOCUMENT_INFODOC_DATE_CREATION: datetime.datetime.utcnow()
            }
            set_on_insert.update(filter)
            ops = {
                '$set': set_ops,
                '$setOnInsert': set_on_insert,
            }

            collection.update(filter, ops, upsert=True)
        else:
            self.__logger.debug("Evenement avec donnees plus vieilles que lectures dans les documents")

    def ajouter_senseur(self, lecture: dict, securite: str):
        transaction = {
            SenseursPassifsConstantes.TRANSACTION_NOEUD_ID: lecture[SenseursPassifsConstantes.TRANSACTION_NOEUD_ID],
            SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR: lecture[SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR],
            Constantes.DOCUMENT_INFODOC_SECURITE: securite,
        }
        domaine_action = SenseursPassifsConstantes.TRANSACTION_MAJ_SENSEUR
        self.gestionnaire.generateur_transactions.soumettre_transaction(transaction, domaine_action)


class SenseursPassifsExchangeRouter(ExchangeRouter):

    def determiner_exchanges(self, document):
        """
        :return: Liste des echanges sur lesquels le document doit etre soumis
        """
        exchanges = set()
        mg_libelle = document.get(Constantes.DOCUMENT_INFODOC_LIBELLE)
        if mg_libelle in [SenseursPassifsConstantes.LIBVAL_VITRINE_DASHBOARD, SenseursPassifsConstantes.LIBVAL_DOCUMENT_SENSEUR]:
            exchanges.add(self._exchange_public)
            # exchanges.add(self._exchange_prive)
            # exchanges.add(self._exchange_protege)
        else:
            exchanges.add(self._exchange_protege)

        return list(exchanges)


# Gestionnaire pour le domaine millegrilles.domaines.SenseursPassifs.
class GestionnaireSenseursPassifs(GestionnaireDomaineStandard):

    def __init__(self, contexte):
        super().__init__(contexte)
        self.__traitement_lecture = None
        self.__traitement_requetes = None
        self._traitement_evenements_lecture: Optional[TraitementMessageLecture] = None
        self._traitement_backlog_lectures = None

        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        self.__handler_requetes_noeuds = {
            Constantes.SECURITE_PUBLIC: TraitementRequetesPubliquesSenseursPassifs(self),
            Constantes.SECURITE_PROTEGE: TraitementRequetesProtegeesSenseursPassifs(self)
        }

        self._traitement_evenements_lecture = TraitementMessageLecture(self)

        self.__handler_commandes_noeuds = super().get_handler_commandes()
        self.__handler_commandes_noeuds[Constantes.SECURITE_SECURE] = TraitementCommandeSenseursPassifs(self)

        self.__gateway_blynk = None

    def configurer(self):
        super().configurer()

        # Section hook pour Blynk (optionnel)
        try:
            from millegrilles.extension.BlynkGateway import GatewayBlynk
            self.__gateway_blynk = GatewayBlynk(self._contexte)
            self.__gateway_blynk.configurer()
        except ImportError:
            self.__gateway_blynk = False

        # Ajouter les index dans la collection de transactions
        collection_transactions = self.document_dao.get_collection(SenseursPassifsConstantes.COLLECTION_TRANSACTIONS_NOM)
        collection_transactions.create_index(
            [
                (SenseursPassifsConstantes.TRANSACTION_DATE_LECTURE, 2),
                ('%s.%s' %
                 (Constantes.TRANSACTION_MESSAGE_LIBELLE_INFO_TRANSACTION, Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE),
                 1),
                (Constantes.DOCUMENT_INFODOC_LIBELLE, 1)
            ],
            name='date-domaine-mglibelle'
        )
        collection_transactions.create_index(
            [
                (SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR, 1),
                ('%s' % SenseursPassifsConstantes.TRANSACTION_DATE_LECTURE, 2),
                ('%s.%s' %
                 (Constantes.TRANSACTION_MESSAGE_LIBELLE_INFO_TRANSACTION, Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE),
                 1),
            ],
            name='senseur-noeud-date-domaine'
        )

    def get_queue_configuration(self):
        configuration = super().get_queue_configuration()

        configuration.append({
            'nom': '%s.%s' % (self.get_nom_queue(), 'evenements_lectures'),
            'routing': [
                'evenement.%s.#.lecture' % self.get_nom_domaine(),
            ],
            'exchange': self.configuration.exchange_protege,
            'ttl': 60000,
            'callback': self._traitement_evenements_lecture.callbackAvecAck
        })
        configuration.append({
            'nom': '%s.%s' % (self.get_nom_queue(), 'evenements_lectures'),
            'routing': [
                'evenement.%s.#.lecture' % self.get_nom_domaine(),
            ],
            'exchange': self.configuration.exchange_prive,
            'ttl': 60000,
            'callback': self._traitement_evenements_lecture.callbackAvecAck
        })

        return configuration

    def demarrer(self):
        super().demarrer()
        # Documents initiaux
        self.initialiser_document(
            SenseursPassifsConstantes.LIBVAL_CONFIGURATION,
            SenseursPassifsConstantes.DOCUMENT_DEFAUT_CONFIGURATION
        )
        self.initialiser_document(
            SenseursPassifsConstantes.LIBVAL_VITRINE_DASHBOARD,
            SenseursPassifsConstantes.DOCUMENT_DEFAUT_VITRINE_DASHBOARD
        )

        if self.__gateway_blynk:
            self.__gateway_blynk.start()

        # self.demarrer_watcher_collection(
        #     SenseursPassifsConstantes.COLLECTION_DOCUMENTS_NOM, SenseursPassifsConstantes.QUEUE_ROUTING_CHANGEMENTS,
        #     SenseursPassifsExchangeRouter(self._contexte))

    def arreter(self):
        super().arreter()
        if self.__gateway_blynk:
            self.__gateway_blynk.fermer()

    def get_handler_requetes(self) -> dict:
        return self.__handler_requetes_noeuds

    def get_handler_commandes(self) -> dict:
        return self.__handler_commandes_noeuds

    def get_nom_queue(self):
        return SenseursPassifsConstantes.QUEUE_NOM

    def get_collection_transaction_nom(self):
        return SenseursPassifsConstantes.COLLECTION_TRANSACTIONS_NOM

    def get_collection_processus_nom(self):
        return SenseursPassifsConstantes.COLLECTION_PROCESSUS_NOM

    def get_nom_domaine(self):
        return SenseursPassifsConstantes.DOMAINE_NOM

    ''' Traite les evenements sur cedule. '''
    def traiter_cedule(self, evenement):
        super().traiter_cedule(evenement)

        indicateurs = evenement['indicateurs']

        # Verifier si les indicateurs sont pour notre timezone
        if 'heure' in indicateurs:
            try:
                self.traiter_cedule_heure(evenement)
            except Exception as he:
                self.__logger.exception("Erreur traitement cedule horaire: %s" % str(he))

            # Verifier si on a l'indicateur jour pour notre TZ (pas interesse par minuit UTC)
            if 'Canada/Eastern' in indicateurs:
                if 'jour' in indicateurs:
                    try:
                        self.traiter_cedule_quotidienne(evenement)
                    except Exception as de:
                        self.__logger.exception("Erreur traitement cedule quotidienne: %s" % str(de))

    def traiter_cedule_heure(self, evenement):
        # Declencher l'aggregation horaire des lectures de senseurs (derniere semaine)
        pass

    def traiter_cedule_quotidienne(self, evenement):
        # Declencher l'aggregation quotidienne des lectures de senseur (derniere annee)
        pass

    def get_nom_collection(self):
        return SenseursPassifsConstantes.COLLECTION_DOCUMENTS_NOM

    def identifier_processus(self, domaine_transaction):
        if domaine_transaction == SenseursPassifsConstantes.TRANSACTION_DOMAINE_LECTURE:
            processus = "millegrilles_domaines_SenseursPassifs:ProcessusTransactionSenseursPassifsLecture"
        elif domaine_transaction == SenseursPassifsConstantes.TRANSACTION_MAJ_SENSEUR:
            processus = "millegrilles_domaines_SenseursPassifs:ProcessusMajSenseur"
        elif domaine_transaction == SenseursPassifsConstantes.TRANSACTION_MAJ_NOEUD:
            processus = "millegrilles_domaines_SenseursPassifs:ProcessusMajNoeud"
        elif domaine_transaction == SenseursPassifsConstantes.TRANSACTION_DOMAINE_SUPPRESSION_SENSEUR:
            processus = "millegrilles_domaines_SenseursPassifs:ProcessusSupprimerSenseur"
        else:
            # Type de transaction inconnue, on lance une exception
            processus = super().identifier_processus(domaine_transaction)

        return processus

    def transmettre_declencheur_domaine(self, domaine, dict_message):
        routing_key = 'destinataire.domaine.%s' % domaine
        self.message_dao.transmettre_message(dict_message, routing_key)

    def get_vitrine_dashboard(self):
        """
        :return: Le document dashboard de vitrine
        """
        collection = self.document_dao.get_collection(SenseursPassifsConstantes.COLLECTION_DOCUMENTS_NOM)
        document_dashboard = collection.find_one({
            Constantes.DOCUMENT_INFODOC_LIBELLE: SenseursPassifsConstantes.LIBVAL_VITRINE_DASHBOARD
        })
        return document_dashboard

    def get_liste_noeuds(self):
        """
        :return: Le document dashboard de vitrine
        """
        collection = self.document_dao.get_collection(SenseursPassifsConstantes.COLLECTION_DOCUMENTS_NOM)

        filtre = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: SenseursPassifsConstantes.LIBVAL_DOCUMENT_NOEUD
        }
        projection = {
            'noeud_id': 1,
            Constantes.DOCUMENT_INFODOC_SECURITE: 1,
            Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: 1,
            'descriptif': 1,
            'blynk_auth':1, 'blynk_host': 1, 'blynk_port': 1,
        }

        noeuds = list()
        for noeud in collection.find(filtre, projection):
            del noeud['_id']
            noeuds.append(noeud)

        return noeuds

    def get_liste_senseurs_noeud(self, params: dict):
        collection = self.document_dao.get_collection(SenseursPassifsConstantes.COLLECTION_DOCUMENTS_NOM)

        filtre = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: SenseursPassifsConstantes.LIBVAL_DOCUMENT_SENSEUR,
            'noeud_id': params['noeud_id'],
        }
        projection = {
            'noeud_id': 1,
            Constantes.DOCUMENT_INFODOC_SECURITE: 1,
            Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: 1,
            'uuid_senseur': 1,
            'senseurs': 1,
            'descriptif': 1,
        }

        seneurs = list()
        for senseur in collection.find(filtre, projection):
            del senseur['_id']
            seneurs.append(senseur)

        return seneurs

    def declencher_rapports(self, type_rapport):
        commande = {
            'type_rapport': type_rapport
        }
        self.generateur_transactions.transmettre_commande(
            commande, 'commande.millegrilles.domaines.SenseursPassifs.declencherRapports',
            exchange=Constantes.DEFAUT_MQ_EXCHANGE_MIDDLEWARE)

    def maj_document_noeud_senseurpassif(self, id_document_senseur):
        """
        Mise a jour du document de noeud par une transaction senseur passif

        :param id_document_senseur: _id du document du senseur.
        :return:
        """

        collection_documents = self._contexte.document_dao.get_collection(SenseursPassifsConstantes.COLLECTION_DOCUMENTS_NOM)
        document_senseur = collection_documents.find_one(ObjectId(id_document_senseur))

        noeud = document_senseur['noeud']
        no_senseur = document_senseur[SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR]

        champs_a_exclure = ['en-tete', 'moyennes_dernier_jour', 'extremes_dernier_mois']

        valeurs = document_senseur.copy()
        operations_filtre = TransactionOperations()
        valeurs = operations_filtre.enlever_champsmeta(valeurs, champs_a_exclure)
        senseur_label = 'dict_senseurs.%s' % str(no_senseur)

        donnees_senseur = {
            senseur_label: valeurs
        }

        filtre = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: SenseursPassifsConstantes.LIBVAL_DOCUMENT_NOEUD,
            'noeud': noeud
        }

        update = {
            '$currentDate': {Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True},
            '$setOnInsert': filtre,
            '$set': donnees_senseur
        }

        collection_documents.update_one(filter=filtre, update=update, upsert=True)

        # S'assurer de nettoyer le senseur s'il etait dans un autre noeud
        filtre = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: SenseursPassifsConstantes.LIBVAL_DOCUMENT_NOEUD,
            'noeud': {'$ne': noeud},
            senseur_label: {'$exists': True}
        }
        update = {
            '$currentDate': {Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True},
            '$unset': {
                senseur_label: 1,
            }
        }
        collection_documents.update_many(filtre, update)
        self.__logger.debug("Requete update noeuds :\n%s\n%s" % (filtre, update))


    '''
    Mise a jour du document du dashboard de vitrine

    :param id_document_senseur: _id du document du senseur.
    '''

    def maj_document_vitrine_dashboard(self, id_document_senseur):
        collection_senseurs = self._contexte.document_dao.get_collection(SenseursPassifsConstantes.COLLECTION_DOCUMENTS_NOM)
        document_senseur = collection_senseurs.find_one(ObjectId(id_document_senseur))

        noeud = document_senseur['noeud']
        uuid_senseur = document_senseur[SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR]

        champs_a_inclure = [
            'uuid_senseur', 'affichage', 'bat_mv', 'bat_reserve', 'location'
        ]

        valeurs = dict()
        for key, value in document_senseur.items():
            if key in champs_a_inclure:
                valeurs[key] = value

        libelle_senseur = 'noeuds.%s.%s' % (noeud, uuid_senseur)
        donnees_senseur = {
            libelle_senseur: valeurs
        }

        filtre = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: SenseursPassifsConstantes.LIBVAL_VITRINE_DASHBOARD,
        }

        update = {
            '$currentDate': {Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True},
            '$set': donnees_senseur
        }

        nouveau_document = collection_senseurs.find_one_and_update(filter=filtre, update=update, new=True)

        # S'assurer que le senseur n'a pas change de noeud
        operation_unset = dict()
        for noeud_doc, valeurs in nouveau_document['noeuds'].items():
            if valeurs.get(uuid_senseur) is not None and noeud_doc != noeud:
                operation_unset['noeuds.%s.%s' % (noeud_doc, uuid_senseur)] = True

        if len(operation_unset.keys()) > 0:
            update = {
                '$currentDate': {Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True},
                '$unset': operation_unset
            }
            collection_senseurs.update_one(filter=filtre, update=update)


class ProcessusSenseursPassifs(MGProcessusTransaction):

    def get_collection_transaction_nom(self):
        return SenseursPassifsConstantes.COLLECTION_TRANSACTIONS_NOM

    def get_collection_processus_nom(self):
        return SenseursPassifsConstantes.COLLECTION_PROCESSUS_NOM


class ProcessusTransactionSenseursPassifsLecture(ProcessusSenseursPassifs):
    """
    Processus pour enregistrer une transaction d'un senseur passif
    """

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger('%s.ProcessusTransactionSenseursPassifsLecture' % __name__)

    def initiale(self):
        """
        Enregistrer l'information de la transaction dans le document du senseur
        :return:
        """
        transaction = self.charger_transaction(SenseursPassifsConstantes.COLLECTION_TRANSACTIONS_NOM)
        self.__logger.debug("Document processus: %s" % self._document_processus)
        self.__logger.debug("Document transaction: %s" % transaction)

        self.__logger.debug("Nettoyer staging transaction senseur %s" % transaction[SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR])
        self.nettoyer_staging(transaction)

        document_senseur = self.charger_document_senseur(transaction[SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR])
        if document_senseur is None:
            securite = Constantes.SECURITE_PROTEGE
        else:
            senseur_info = document_senseur['senseurs'].get(transaction['senseur'])
            if senseur_info is not None and senseur_info.get('securite'):
                securite = senseur_info.get('securite')
            else:
                securite = document_senseur.get('securite') or Constantes.SECURITE_PROTEGE

        # Emettre evenement de lecture pour la derniere lecture de la transaction
        # Permettre de mettre a jour le document de senseur, creer documents manquants, etc.
        self.emettre_evenement_transaction(transaction, securite)

        self.set_etape_suivante()  # Termine

    def charger_document_senseur(self, uuid_senseur) -> dict:
        collection = self.get_collection_documents()
        doc = collection.find_one({
            Constantes.DOCUMENT_INFODOC_LIBELLE: SenseursPassifsConstantes.LIBVAL_DOCUMENT_SENSEUR,
            SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR: uuid_senseur,
        })
        return doc

    def emettre_evenement_transaction(self, transaction, securite):

        lecture = transaction['lectures'][-1]  # Prendre derniere/plus recente lecture
        nom_senseur = transaction['senseur']
        timestamp = transaction['timestamp']
        type_lecture = transaction['type']

        evenement = {
            SenseursPassifsConstantes.TRANSACTION_NOEUD_ID: transaction[SenseursPassifsConstantes.TRANSACTION_NOEUD_ID],
            SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR: transaction[SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR],
            "senseurs": {
                nom_senseur: {
                    'timestamp': timestamp,
                    'type': type_lecture,
                    'valeur': lecture['valeur'],
                }
            }
        }

        domaine_action = 'evenement.' + SenseursPassifsConstantes.TRANSACTION_MAJ_SENSEUR
        if securite is None or securite == Constantes.SECURITE_PROTEGE:
            # Emettre sur exchange protege
            self.generateur_transactions.emettre_message(
                evenement, domaine_action, exchanges=[Constantes.SECURITE_PROTEGE])
        else:
            # Emettre sur exchange prive
            self.generateur_transactions.emettre_message(
                evenement, domaine_action, exchanges=[Constantes.SECURITE_PRIVE])

    def nettoyer_staging(self, transaction):
        collection = self.document_dao.get_collection(SenseursPassifsConstantes.COLLECTION_STAGING_NOM)
        noeud_id = transaction[SenseursPassifsConstantes.TRANSACTION_NOEUD_ID]
        uuid_senseur = transaction[SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR]
        senseur = transaction['senseur']
        timestamp_min = transaction['timestamp_min']
        timestamp_max = transaction['timestamp_max']
        filtre = {
            SenseursPassifsConstantes.TRANSACTION_NOEUD_ID: noeud_id,
            SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR: uuid_senseur,
            'senseurs.%s.timestamp' % senseur: {
                '$lte': timestamp_max,
                '$gte': timestamp_min,
            }
        }
        collection.delete_many(filtre)


class ProcessusMajSenseur(ProcessusSenseursPassifs):
    """ Processus de modification d'un senseur """

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

    def initiale(self):
        """ Mettre a jour le document de senseur """

        # transaction = self.charger_transaction(SenseursPassifsConstantes.COLLECTION_TRANSACTIONS_NOM)
        transaction_filtree = self.transaction_filtree

        uuid_senseur = transaction_filtree[SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR]

        filtre = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: SenseursPassifsConstantes.LIBVAL_DOCUMENT_SENSEUR,
            SenseursPassifsConstantes.TRANSACTION_ID_SENSEUR: uuid_senseur,
        }

        set_ops = dict()
        for key, value in transaction_filtree.items():
            if key not in filtre.keys():
                set_ops[key] = value

        # Formatter les modifications de la collection de senseurs au besoin
        senseurs = set_ops.get('senseurs')
        if senseurs:
            del set_ops['senseurs']  # Applatir toutes operations sur senseurs
            senseurs = dict(senseurs)
            # Derouler toutes les collections sous forme de cle (e.g. 'senseurs.dummy.valeur'}
            for cle1, valeur1 in senseurs.items():
                if isinstance(valeur1, dict):
                    for cle2, valeur2 in valeur1.items():
                        cle_totale = '.'.join(['senseurs', cle1, cle2])
                        set_ops[cle_totale] = valeur2

        set_on_insert = {
            Constantes.DOCUMENT_INFODOC_DATE_CREATION: datetime.datetime.utcnow()
        }
        set_on_insert.update(filtre)

        ops = {
            '$set': set_ops,
            '$currentDate': {Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True},
            '$setOnInsert': set_on_insert,
        }

        collection = self.document_dao.get_collection(SenseursPassifsConstantes.COLLECTION_DOCUMENTS_NOM)
        resultat_update = collection.update_one(filtre, ops, upsert=True)

        if resultat_update.upserted_id is None and resultat_update.matched_count == 0:
            raise Exception("Erreur mise a jour document senseur id %s" % uuid_senseur)

        # S'assurer que le document de noeud existe
        self.verifier_noeud(transaction_filtree)

        # self.set_etape_suivante(ProcessusMajManuelle.modifier_noeud.__name__)  # Mettre a jour le noeud
        self.set_etape_suivante()  # Termine

    def verifier_noeud(self, transaction):
        """
        S'assurer que le document de noeud existe
        :param transaction:
        :return:
        """
        noeud_id = transaction[SenseursPassifsConstantes.TRANSACTION_NOEUD_ID]
        securite = transaction['securite']
        collection = self.document_dao.get_collection(SenseursPassifsConstantes.COLLECTION_DOCUMENTS_NOM)

        filtre = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: SenseursPassifsConstantes.LIBVAL_DOCUMENT_NOEUD,
            SenseursPassifsConstantes.TRANSACTION_NOEUD_ID: noeud_id,
        }

        document_noeud = collection.find_one(filtre)

        if document_noeud is None:
            # Transmettre transaction de noeud
            transaction = {
                SenseursPassifsConstantes.TRANSACTION_NOEUD_ID: noeud_id,
                Constantes.DOCUMENT_INFODOC_SECURITE: securite,
            }
            domaine_action = SenseursPassifsConstantes.TRANSACTION_MAJ_NOEUD
            self.generateur_transactions.soumettre_transaction(transaction, domaine_action)


class ProcessusMajNoeud(ProcessusSenseursPassifs):
    """ Processus de modification d'un noeud """

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

    def initiale(self):
        """ Mettre a jour le document de noeud """

        transaction_filtree = self.transaction_filtree

        noeud_id = transaction_filtree[SenseursPassifsConstantes.TRANSACTION_NOEUD_ID]

        filtre = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: SenseursPassifsConstantes.LIBVAL_DOCUMENT_NOEUD,
            SenseursPassifsConstantes.TRANSACTION_NOEUD_ID: noeud_id,
        }

        set_ops = dict()
        for key, value in transaction_filtree.items():
            if key not in filtre.keys():
                set_ops[key] = value

        set_on_insert = {
            Constantes.DOCUMENT_INFODOC_DATE_CREATION: datetime.datetime.utcnow()
        }
        set_on_insert.update(filtre)

        ops = {
            '$set': set_ops,
            '$currentDate': {Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True},
            '$setOnInsert': set_on_insert,
        }

        collection_transactions = self.document_dao.get_collection(SenseursPassifsConstantes.COLLECTION_DOCUMENTS_NOM)
        resultat_update = collection_transactions.update_one(filtre, ops, upsert=True)

        if resultat_update.upserted_id is None and resultat_update.matched_count == 0:
            raise Exception("Erreur mise a jour document noeud id %s" % noeud_id)

        # self.set_etape_suivante(ProcessusMajManuelle.modifier_noeud.__name__)  # Mettre a jour le noeud
        self.set_etape_suivante()  # Termine

