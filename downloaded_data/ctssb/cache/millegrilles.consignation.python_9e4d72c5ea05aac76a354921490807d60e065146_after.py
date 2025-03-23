# Domaine de l'interface GrosFichiers
from pymongo.errors import DuplicateKeyError

from millegrilles import Constantes
from millegrilles.Domaines import GestionnaireDomaine
from millegrilles.dao.MessageDAO import TraitementMessageDomaineMiddleware, TraitementMessageDomaineRequete
from millegrilles.MGProcessus import MGProcessusTransaction, MGPProcesseur

import logging
import datetime
import uuid


class ConstantesGrosFichiers:
    """ Constantes pour le domaine de GrosFichiers """

    DOMAINE_NOM = 'millegrilles.domaines.GrosFichiers'
    COLLECTION_TRANSACTIONS_NOM = DOMAINE_NOM
    COLLECTION_DOCUMENTS_NOM = '%s/documents' % COLLECTION_TRANSACTIONS_NOM
    COLLECTION_PROCESSUS_NOM = '%s/processus' % COLLECTION_TRANSACTIONS_NOM
    QUEUE_NOM = 'millegrilles.domaines.GrosFichiers'
    QUEUE_ROUTING_CHANGEMENTS = 'noeuds.source.millegrilles_domaines_GrosFichiers'

    TRANSACTION_TYPE_METADATA = 'millegrilles.domaines.GrosFichiers.nouvelleVersion.metadata'
    TRANSACTION_TYPE_TRANSFERTCOMPLETE = 'millegrilles.domaines.GrosFichiers.nouvelleVersion.transfertComplete'

    TRANSACTION_CHAMP_LIBELLE = 'libelle'

    LIBVAL_CONFIGURATION = 'configuration'
    LIBVAL_REPERTOIRE = 'repertoire'
    LIBVAL_REPERTOIRE_RACINE = 'repertoire.racine'
    LIBVAL_REPERTOIRE_ORPHELINS = 'repertoire.orphelins'
    LIBVAL_REPERTOIRE_CORBEILLE = 'repertoire.corbeille'
    LIBVAL_FICHIER = 'fichier'

    # Repertoires speciaux
    REPERTOIRE_ORPHELINS = 'orphelins'
    REPERTOIRE_CORBEILLE = 'corbeille'

    DOCUMENT_SECURITE = 'securite'
    DOCUMENT_NOMREPERTOIRE = 'nom'
    DOCUMENT_COMMENTAIRES = 'commentaires'
    DOCUMENT_CHEMIN = 'chemin_repertoires'

    DOCUMENT_REPERTOIRE_FICHIERS = 'fichiers'
    DOCUMENT_REPERTOIRE_SOUSREPERTOIRES = 'repertoires'
    DOCUMENT_REPERTOIRE_UUID = 'repertoire_uuid'
    DOCUMENT_REPERTOIRE_PARENT_ID = 'parent_id'

    DOCUMENT_FICHIER_NOMFICHIER = 'nom'
    DOCUMENT_FICHIER_UUID_DOC = 'uuid'                    # UUID du document de fichier (metadata)
    DOCUMENT_FICHIER_FUUID = 'fuuid'                    # UUID (v1) du fichier
    DOCUMENT_FICHIER_DATEVCOURANTE = 'date_v_courante'  # Date de la version courante
    DOCUMENT_FICHIER_UUIDVCOURANTE = 'fuuid_v_courante'  # FUUID de la version courante
    DOCUMENT_FICHIER_VERSIONS = 'versions'
    DOCUMENT_FICHIER_MIMETYPE = 'mimetype'
    DOCUMENT_FICHIER_TAILLE = 'taille'
    DOCUMENT_FICHIER_SHA256 = 'sha256'
    DOCUMENT_FICHIER_SUPPRIME = 'supprime'
    DOCUMENT_FICHIER_SUPPRIME_DATE = 'supprime_date'

    DOCUMENT_VERSION_NOMFICHIER = 'nom'
    DOCUMENT_VERSION_DATE_FICHIER = 'date_fichier'
    DOCUMENT_VERSION_DATE_VERSION = 'date_version'

    DOCUMENT_DEFAULT_MIMETYPE = 'application/binary'

    TRANSACTION_NOUVELLEVERSION_METADATA = '%s.nouvelleVersion.metadata' % DOMAINE_NOM
    TRANSACTION_NOUVELLEVERSION_TRANSFERTCOMPLETE = '%s.nouvelleVersion.transfertComplete' % DOMAINE_NOM
    TRANSACTION_NOUVELLEVERSION_CLES_RECUES = '%s.nouvelleVersion.clesRecues' % DOMAINE_NOM
    TRANSACTION_COPIER_FICHIER = '%s.copierFichier' % DOMAINE_NOM
    TRANSACTION_RENOMMER_FICHIER = '%s.renommerFichier' % DOMAINE_NOM
    TRANSACTION_DEPLACER_FICHIER = '%s.deplacerFichier' % DOMAINE_NOM
    TRANSACTION_SUPPRIMER_FICHIER = '%s.supprimerFichier' % DOMAINE_NOM
    TRANSACTION_COMMENTER_FICHIER = '%s.commenterFichier' % DOMAINE_NOM

    TRANSACTION_CREER_REPERTOIRE_SPECIAL = '%s.creerRepertoireSpecial' % DOMAINE_NOM
    TRANSACTION_CREER_REPERTOIRE = '%s.creerRepertoire' % DOMAINE_NOM
    TRANSACTION_RENOMMER_REPERTOIRE = '%s.renommerRepertoire' % DOMAINE_NOM
    TRANSACTION_DEPLACER_REPERTOIRE = '%s.deplacerRepertoire' % DOMAINE_NOM
    TRANSACTION_SUPPRIMER_REPERTOIRE = '%s.supprimerRepertoire' % DOMAINE_NOM
    TRANSACTION_COMMENTER_REPERTOIRE = '%s.commenterRepertoire' % DOMAINE_NOM
    TRANSACTION_CHANGER_SECURITE_REPERTOIRE = '%s.changerSecuriteRepertoire' % DOMAINE_NOM

    # Document par defaut pour la configuration de l'interface GrosFichiers
    DOCUMENT_DEFAUT = {
        Constantes.DOCUMENT_INFODOC_LIBELLE: LIBVAL_CONFIGURATION,
    }

    DOCUMENT_REPERTOIRE = {
        Constantes.DOCUMENT_INFODOC_LIBELLE: LIBVAL_REPERTOIRE,
        DOCUMENT_SECURITE: Constantes.SECURITE_PRIVE,   # Niveau de securite
        DOCUMENT_COMMENTAIRES: None,

        # Information repertoire
        DOCUMENT_REPERTOIRE_UUID: None,                 # Identificateur unique du repertoire (uuid trans originale)
        DOCUMENT_REPERTOIRE_PARENT_ID: None,            # Identificateur unique du repertoire parent
        DOCUMENT_CHEMIN: '/chemin/dummy',               # Chemin complet du repertoire, excluant nom du repertoire
        DOCUMENT_NOMREPERTOIRE: 'repertoire',           # Nom du repertoire affiche a l'usager

        # Contenu
        DOCUMENT_REPERTOIRE_FICHIERS: dict(),           # Liste des fichiers, cle: uuid, valeur: doc fichier filtre
        DOCUMENT_REPERTOIRE_SOUSREPERTOIRES: dict(),    # Liste des sous-repertoires, cle: uuid, valeur: doc rep filtre
    }

    DOCUMENT_FICHIER = {
        Constantes.DOCUMENT_INFODOC_LIBELLE: LIBVAL_FICHIER,
        DOCUMENT_FICHIER_UUID_DOC: None,  # Identificateur unique du fichier (UUID trans initiale)
        DOCUMENT_SECURITE: Constantes.SECURITE_PRIVE,       # Niveau de securite
        DOCUMENT_COMMENTAIRES: None,                        # Commentaires
        DOCUMENT_FICHIER_NOMFICHIER: None,                  # Nom du fichier (libelle affiche a l'usager)

        # Repertoire
        DOCUMENT_REPERTOIRE_UUID: None,                     # Identificateur unique du repertoire principal
        # DOCUMENT_NOMREPERTOIRE: 'repertoire',             # Nom du repertoire (repertoire principal)
        DOCUMENT_CHEMIN: REPERTOIRE_ORPHELINS,              # Chemin complet du repertoire/fichier

        # Versions
        # DOCUMENT_FICHIER_VERSIONS: dict(),
        # DOCUMENT_FICHIER_DATEVCOURANTE: None,
        # DOCUMENT_FICHIER_UUIDVCOURANTE: None,
        # DOCUMENT_FICHIER_MIMETYPE: DOCUMENT_DEFAULT_MIMETYPE,
        # DOCUMENT_FICHIER_TAILLE: None,
    }

    SOUSDOCUMENT_VERSION_FICHIER = {
        DOCUMENT_FICHIER_FUUID: None,
        DOCUMENT_FICHIER_NOMFICHIER: None,
        DOCUMENT_FICHIER_MIMETYPE: DOCUMENT_DEFAULT_MIMETYPE,
        DOCUMENT_VERSION_DATE_FICHIER: None,
        DOCUMENT_VERSION_DATE_VERSION: None,
        DOCUMENT_FICHIER_TAILLE: None,
        DOCUMENT_FICHIER_SHA256: None,
        DOCUMENT_COMMENTAIRES: None,
    }


class GestionnaireGrosFichiers(GestionnaireDomaine):

    def __init__(self, contexte):
        super().__init__(contexte)
        self._traitement_middleware = None
        self._traitement_noeud = None
        self._logger = logging.getLogger("%s.GestionnaireRapports" % __name__)

    def configurer(self):
        super().configurer()

        self._traitement_middleware = TraitementMessageDomaineMiddleware(self)
        self._traitement_noeud = TraitementMessageDomaineRequete(self)
        self.initialiser_document(ConstantesGrosFichiers.LIBVAL_CONFIGURATION, ConstantesGrosFichiers.DOCUMENT_DEFAUT)
        self.creer_index()  # Creer index dans MongoDB

    def setup_rabbitmq(self, channel):
        # Configurer la Queue pour les rapports sur RabbitMQ
        nom_queue_domaine = self.get_nom_queue()

        queues_config = [
            {
                'nom': self.get_nom_queue(),
                'routing': 'destinataire.domaine.millegrilles.domaines.GrosFichiers.#',
                'exchange': Constantes.DEFAUT_MQ_EXCHANGE_MIDDLEWARE,
                'callback': self.callback_queue_transaction
            },
            {
                'nom': self.get_nom_queue_requetes_noeuds(),
                'routing': 'requete.%s.#' % ConstantesGrosFichiers.DOMAINE_NOM,
                'exchange': Constantes.DEFAUT_MQ_EXCHANGE_NOEUDS,
                'callback': self.callback_queue_requete_noeud
            },
            {
                'nom': self.get_nom_queue_requetes_inter(),
                'routing': 'requete.%s.#' % ConstantesGrosFichiers.DOMAINE_NOM,
                'exchange': Constantes.DEFAUT_MQ_EXCHANGE_INTER,
                'callback': self.callback_queue_requete_inter
            },
        ]

        channel = self.message_dao.channel
        for queue_config in queues_config:
            channel.queue_declare(
                queue=queue_config['nom'],
                durable=False,
                callback=queue_config['callback'],
            )

            channel.queue_bind(
                exchange=queue_config['exchange'],
                queue=queue_config['nom'],
                routing_key=queue_config['routing'],
                callback=None,
            )

        channel.queue_bind(
            exchange=self.configuration.exchange_middleware,
            queue=nom_queue_domaine,
            routing_key='ceduleur.#',
            callback=None,
        )

        channel.queue_bind(
            exchange=self.configuration.exchange_middleware,
            queue=nom_queue_domaine,
            routing_key='processus.domaine.%s.#' % ConstantesGrosFichiers.DOMAINE_NOM,
            callback=None,
        )

    def demarrer(self):
        super().demarrer()
        self.demarrer_watcher_collection(
            ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM, ConstantesGrosFichiers.QUEUE_ROUTING_CHANGEMENTS)

    def identifier_processus(self, domaine_transaction):
        # Fichiers
        if domaine_transaction == ConstantesGrosFichiers.TRANSACTION_NOUVELLEVERSION_METADATA:
            processus = "millegrilles_domaines_GrosFichiers:ProcessusTransactionNouvelleVersionMetadata"
        elif domaine_transaction == ConstantesGrosFichiers.TRANSACTION_NOUVELLEVERSION_TRANSFERTCOMPLETE:
            processus = "millegrilles_domaines_GrosFichiers:ProcessusTransactionNouvelleVersionTransfertComplete"
        elif domaine_transaction == ConstantesGrosFichiers.TRANSACTION_NOUVELLEVERSION_CLES_RECUES:
            processus = "millegrilles_domaines_GrosFichiers:ProcessusTransactionNouvelleVersionClesRecues"
        elif domaine_transaction == ConstantesGrosFichiers.TRANSACTION_DEPLACER_FICHIER or \
                domaine_transaction == ConstantesGrosFichiers.TRANSACTION_RENOMMER_FICHIER:
            processus = "millegrilles_domaines_GrosFichiers:ProcessusTransactionRenommerDeplacerFichier"
        elif domaine_transaction == ConstantesGrosFichiers.TRANSACTION_SUPPRIMER_FICHIER:
            processus = "millegrilles_domaines_GrosFichiers:ProcessusTransactionSupprimerFichier"
        elif domaine_transaction == ConstantesGrosFichiers.TRANSACTION_COMMENTER_FICHIER:
            processus = "millegrilles_domaines_GrosFichiers:ProcessusTransactionCommenterFichier"

        # Repertoires
        elif domaine_transaction == ConstantesGrosFichiers.TRANSACTION_CREER_REPERTOIRE_SPECIAL:
            processus = "millegrilles_domaines_GrosFichiers:ProcessusTransactionCreerRepertoireSpecial"
        elif domaine_transaction == ConstantesGrosFichiers.TRANSACTION_CREER_REPERTOIRE:
            processus = "millegrilles_domaines_GrosFichiers:ProcessusTransactionCreerRepertoire"
        elif domaine_transaction == ConstantesGrosFichiers.TRANSACTION_RENOMMER_REPERTOIRE or \
                domaine_transaction == ConstantesGrosFichiers.TRANSACTION_DEPLACER_REPERTOIRE:
            processus = "millegrilles_domaines_GrosFichiers:ProcessusTransactionRenommerDeplacerRepertoire"
        elif domaine_transaction == ConstantesGrosFichiers.TRANSACTION_SUPPRIMER_REPERTOIRE:
            processus = "millegrilles_domaines_GrosFichiers:ProcessusTransactionSupprimerRepertoire"
        elif domaine_transaction == ConstantesGrosFichiers.TRANSACTION_COMMENTER_REPERTOIRE:
            processus = "millegrilles_domaines_GrosFichiers:ProcessusTransactionCommenterRepertoire"
        elif domaine_transaction == ConstantesGrosFichiers.TRANSACTION_CHANGER_SECURITE_REPERTOIRE:
            processus = "millegrilles_domaines_GrosFichiers:ProcessusTransactionChangerSecuriteRepertoire"

        else:
            processus = super().identifier_processus(domaine_transaction)

        return processus

    def traiter_cedule(self, evenement):
        pass

    def traiter_transaction(self, ch, method, properties, body):
        self._traitement_middleware.callbackAvecAck(ch, method, properties, body)

    def get_nom_collection(self):
        return ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM

    def get_nom_queue(self):
        return ConstantesGrosFichiers.QUEUE_NOM

    def get_nom_queue_requetes_noeuds(self):
        return '%s.noeuds' % self.get_nom_queue()

    def get_nom_queue_requetes_inter(self):
        return '%s.inter' % self.get_nom_queue()

    def get_collection_transaction_nom(self):
        return ConstantesGrosFichiers.COLLECTION_TRANSACTIONS_NOM

    def get_collection_processus_nom(self):
        return ConstantesGrosFichiers.COLLECTION_PROCESSUS_NOM

    def get_document_racine(self):
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)
        document_repertoire_racine = collection_domaine.find_one({
            ConstantesGrosFichiers.DOCUMENT_CHEMIN: '/',
            ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE: '/',
        })
        return document_repertoire_racine

    def get_document_corbeille(self):
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)
        document_repertoire_corbeille = collection_domaine.find_one(
            {
                ConstantesGrosFichiers.DOCUMENT_CHEMIN: ConstantesGrosFichiers.REPERTOIRE_CORBEILLE,
                ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE: ConstantesGrosFichiers.REPERTOIRE_CORBEILLE,
             }
        )
        return document_repertoire_corbeille

    def get_document_orphelins(self):
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)
        document_repertoire_orphelins = collection_domaine.find_one(
            {
                ConstantesGrosFichiers.DOCUMENT_CHEMIN: ConstantesGrosFichiers.REPERTOIRE_ORPHELINS,
                ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE: ConstantesGrosFichiers.REPERTOIRE_ORPHELINS,
             }
        )
        return document_repertoire_orphelins

    def traiter_requete_noeud(self, ch, method, properties, body):
        self._traitement_noeud.callbackAvecAck(ch, method, properties, body)

    def traiter_requete_inter(self, ch, method, properties, body):
        pass

    def initialiser_document(self, mg_libelle, doc_defaut):
        # Configurer MongoDB, inserer le document de configuration de reference s'il n'existe pas
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)

        # Trouver le document de configuration
        document_configuration = collection_domaine.find_one(
            {Constantes.DOCUMENT_INFODOC_LIBELLE: mg_libelle}
        )
        if document_configuration is None:
            self._logger.info("On insere le document %s pour domaine GrosFichiers" % mg_libelle)

            super().initialiser_document(doc_defaut[Constantes.DOCUMENT_INFODOC_LIBELLE], doc_defaut)

            # Initialiser document repertoire racine
            document_repertoire_racine = self.get_document_racine()
            if document_repertoire_racine is None:
                # Creer le repertoire racine (parent=None)
                transaction_racine = {
                    ConstantesGrosFichiers.TRANSACTION_CHAMP_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_RACINE,
                    ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE: '/',
                    ConstantesGrosFichiers.DOCUMENT_SECURITE: Constantes.SECURITE_PRIVE,
                    ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: str(uuid.uuid1()),
                }
                self.generateur_transactions.soumettre_transaction(transaction_racine, ConstantesGrosFichiers.TRANSACTION_CREER_REPERTOIRE_SPECIAL)

            document_repertoire_orphelins = self.get_document_orphelins()
            if document_repertoire_orphelins is None:
                transaction_orphelins = {
                    ConstantesGrosFichiers.TRANSACTION_CHAMP_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_ORPHELINS,
                    ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE: ConstantesGrosFichiers.REPERTOIRE_ORPHELINS,
                    ConstantesGrosFichiers.DOCUMENT_SECURITE: Constantes.SECURITE_PRIVE,
                    ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: str(uuid.uuid1()),
                }
                self.generateur_transactions.soumettre_transaction(transaction_orphelins, ConstantesGrosFichiers.TRANSACTION_CREER_REPERTOIRE_SPECIAL)

            document_repertoire_corbeille = self.get_document_corbeille()
            if document_repertoire_corbeille is None:
                transaction_corbeille = {
                    ConstantesGrosFichiers.TRANSACTION_CHAMP_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_CORBEILLE,
                    ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE: ConstantesGrosFichiers.REPERTOIRE_CORBEILLE,
                    ConstantesGrosFichiers.DOCUMENT_SECURITE: Constantes.SECURITE_PRIVE,
                    ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: str(uuid.uuid1()),
                }
                self.generateur_transactions.soumettre_transaction(transaction_corbeille, ConstantesGrosFichiers.TRANSACTION_CREER_REPERTOIRE_SPECIAL)

        else:
            self._logger.info("Document de %s pour GrosFichiers: %s" % (mg_libelle, str(document_configuration)))

    def creer_index(self):
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)

        # Creer un index pour les chemins et noms de fichiers. L'index est unique (empeche duplication).
        collection_domaine.create_index([
            (ConstantesGrosFichiers.DOCUMENT_CHEMIN, 1),
            (ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE, 1),
            (ConstantesGrosFichiers.DOCUMENT_FICHIER_NOMFICHIER, 1)
        ], unique=True)

        # Index _mg-libelle
        collection_domaine.create_index([
            (Constantes.DOCUMENT_INFODOC_LIBELLE, 1),
        ])

        # Index pour trouver un repertoire par UUID
        collection_domaine.create_index([
            (ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID, 1),
        ])

        # Index pour trouver un fichier par UUID
        collection_domaine.create_index([
            (ConstantesGrosFichiers.DOCUMENT_FICHIER_FUUID, 1),
        ])

        # Index pour trouver une version de fichier par FUUID
        collection_domaine.create_index([
            ('%s.%s' %
             (ConstantesGrosFichiers.DOCUMENT_FICHIER_VERSIONS,
              ConstantesGrosFichiers.DOCUMENT_FICHIER_FUUID),
             1),
        ])

        # Index par SHA256 / taille. Permet de determiner si le fichier existe deja (et juste faire un lien).
        collection_domaine.create_index([
            ('%s.%s' %
             (ConstantesGrosFichiers.DOCUMENT_FICHIER_VERSIONS,
              ConstantesGrosFichiers.DOCUMENT_FICHIER_SHA256),
             1),
            ('%s.%s' %
             (ConstantesGrosFichiers.DOCUMENT_FICHIER_VERSIONS,
              ConstantesGrosFichiers.DOCUMENT_FICHIER_TAILLE),
             1),
        ])

    def get_nom_domaine(self):
        return ConstantesGrosFichiers.DOMAINE_NOM

    def creer_repertoire_special(self, nom_repertoire, mg_libelle, uuid, securite=Constantes.SECURITE_PRIVE, libelle=ConstantesGrosFichiers.LIBVAL_REPERTOIRE):
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)

        # Un repertoire special est unique, on peut juste en creer un de ce type
        check_document = collection_domaine.find_one({Constantes.DOCUMENT_INFODOC_LIBELLE: mg_libelle})
        if check_document is not None:
            raise ValueError("Le document %s existe deja" % mg_libelle)

        document_repertoire = ConstantesGrosFichiers.DOCUMENT_REPERTOIRE.copy()

        document_repertoire[Constantes.DOCUMENT_INFODOC_LIBELLE] = mg_libelle

        maintenant = datetime.datetime.utcnow()
        document_repertoire[Constantes.DOCUMENT_INFODOC_DATE_CREATION] = maintenant
        document_repertoire[Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION] = maintenant

        document_repertoire[ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE] = nom_repertoire
        document_repertoire[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID] = uuid
        document_repertoire[ConstantesGrosFichiers.DOCUMENT_SECURITE] = securite

        document_repertoire[ConstantesGrosFichiers.DOCUMENT_CHEMIN] = nom_repertoire

        self._logger.info("Insertion repertoire special: %s" % str(document_repertoire))

        collection_domaine.insert(document_repertoire)

        return document_repertoire

    def creer_repertoire(self, nom_repertoire, parent_uuid, uuid_repertoire, securite=Constantes.SECURITE_PRIVE, libelle=ConstantesGrosFichiers.LIBVAL_REPERTOIRE):
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)

        document_repertoire = ConstantesGrosFichiers.DOCUMENT_REPERTOIRE.copy()

        document_repertoire[Constantes.DOCUMENT_INFODOC_LIBELLE] = libelle

        maintenant = datetime.datetime.utcnow()
        document_repertoire[Constantes.DOCUMENT_INFODOC_DATE_CREATION] = maintenant
        document_repertoire[Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION] = maintenant

        document_repertoire[ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE] = nom_repertoire
        document_repertoire[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID] = uuid_repertoire
        document_repertoire[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_PARENT_ID] = parent_uuid
        document_repertoire[ConstantesGrosFichiers.DOCUMENT_SECURITE] = securite

        if parent_uuid is not None:
            document_parent = collection_domaine.find_one({ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: parent_uuid})

            if document_parent is None:
                self._logger.info("Repertoire orphelin")
                document_parent = collection_domaine.find_one(
                    {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_ORPHELINS}
                )
                document_repertoire[ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE] = '%s_%s' % (uuid_repertoire, nom_repertoire)

            chemin_gparent = document_parent[ConstantesGrosFichiers.DOCUMENT_CHEMIN]
            nom_repertoire = document_parent[ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE]
            chemin_parent = '%s/%s' % (
                chemin_gparent,
                nom_repertoire,
            )
            chemin_parent = chemin_parent.replace('///', '/').replace('//', '/')
        else:
            chemin_parent = '/'  # Racine

        document_repertoire[ConstantesGrosFichiers.DOCUMENT_CHEMIN] = chemin_parent

        self._logger.info("Insertion repertoire: %s" % str(document_repertoire))

        collection_domaine.insert(document_repertoire)

        return document_repertoire

    def maj_repertoire_fichier(self, uuid_fichier, ancien_repertoire_uuid=None):
        """
        Met a jour l'information d'un fichier dans le document de repertoire.
        :param uuid_fichier:
        :param ancien_repertoire_uuid:
        :return:
        """
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)
        document_fichier = collection_domaine.find_one({ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC: uuid_fichier})
        supprime_flag = document_fichier.get(ConstantesGrosFichiers.DOCUMENT_FICHIER_SUPPRIME)
        if not supprime_flag:
            repertoire_uuid = document_fichier[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]
        else:
            document_corbeille = self.get_document_corbeille()
            repertoire_uuid = document_corbeille[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]

        copie_doc_fichier = dict()

        champs_conserver = [
            ConstantesGrosFichiers.DOCUMENT_FICHIER_TAILLE,
            ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC,
            ConstantesGrosFichiers.DOCUMENT_SECURITE,
            ConstantesGrosFichiers.DOCUMENT_FICHIER_NOMFICHIER,
            ConstantesGrosFichiers.DOCUMENT_FICHIER_DATEVCOURANTE,
            ConstantesGrosFichiers.DOCUMENT_FICHIER_UUIDVCOURANTE,
            ConstantesGrosFichiers.DOCUMENT_FICHIER_MIMETYPE,
            ConstantesGrosFichiers.DOCUMENT_FICHIER_TAILLE,
        ]

        for key in document_fichier.keys():
            if key in champs_conserver:
                copie_doc_fichier[key] = document_fichier[key]

        # Creer l'update du repertoire
        filtre_rep = {
            ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: repertoire_uuid,
            '$or': [
                {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE},
                {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_RACINE},
                {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_ORPHELINS},
                {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_CORBEILLE},
            ]
        }
        set_op = {
            '%s.%s' % (
                ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_FICHIERS,
                document_fichier[ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC]): copie_doc_fichier,
        }
        update_op = {
            '$set': set_op,
            '$currentDate': {Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True},
        }
        resultat = collection_domaine.update_one(filtre_rep, update_op)
        self._logger.debug("Resultat maj_fichier : %s" % str(resultat))

        if ancien_repertoire_uuid is not None:
            collection_domaine.update_one(
                {
                    ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: ancien_repertoire_uuid,
                    '$or': [
                        {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE},
                        {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_RACINE},
                        {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_ORPHELINS},
                        {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_CORBEILLE},
                    ]
                },
                {
                    '$unset': set_op,
                    '$currentDate': {Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True},
                })
            self._logger.debug("Resultat maj_fichier unset: %s" % str(resultat))

    def maj_repertoire_parent(self, uuid_sousrepertoire, ancien_parent_uuid=None):

        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)
        document_repertoire = collection_domaine.find_one({ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: uuid_sousrepertoire})
        parent_uuid = document_repertoire[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_PARENT_ID]
        supprime_flag = document_repertoire.get(ConstantesGrosFichiers.DOCUMENT_FICHIER_SUPPRIME)
        if supprime_flag == True:
            document_corbeille = self.get_document_corbeille()
            parent_uuid = document_corbeille[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]

        document_repertoire_resume = {
            ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: uuid_sousrepertoire,
            ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE: document_repertoire[ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE],
            ConstantesGrosFichiers.DOCUMENT_SECURITE: document_repertoire[ConstantesGrosFichiers.DOCUMENT_SECURITE],
        }

        set_operation = {
            '%s.%s' % (ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_SOUSREPERTOIRES, uuid_sousrepertoire):
                document_repertoire_resume
        }
        resultat = collection_domaine.update_one(
            {ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: parent_uuid},
            {
                '$set': set_operation,
                '$currentDate': {Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True},
            }
        )
        self._logger.debug("maj_repertoire_parent resultat: %s" % str(resultat))

        if ancien_parent_uuid is not None and ancien_parent_uuid:
            resultat = collection_domaine.update_one(
                {
                    ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: ancien_parent_uuid,
                    '$or': [
                        {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE},
                        {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_RACINE},
                        {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_ORPHELINS},
                        {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_CORBEILLE},
                    ]
                },
                {
                    '$unset': set_operation,
                    '$currentDate': {Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True},
                }
            )
            self._logger.debug("maj_repertoire_parent resultat unset: %s" % str(resultat))

    def renommer_deplacer_repertoire(self, uuid_repertoire, nom_repertoire, parent_uuid=None):
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)

        if parent_uuid is None:
            # Trouver parent uuid
            parent_document = None
        else:
            parent_document = collection_domaine.find_one({ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: parent_uuid})

        chemin_parent = parent_document[ConstantesGrosFichiers.DOCUMENT_CHEMIN]
        if chemin_parent == '/':
            chemin_parent = ''
        nouveau_chemin = '%s/%s' % (chemin_parent, nom_repertoire)

        set_operation = {
            ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE: nom_repertoire,
            ConstantesGrosFichiers.DOCUMENT_CHEMIN: nouveau_chemin
        }
        if parent_uuid is not None:
            set_operation[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_PARENT_ID] = parent_uuid

        # On ne permet pas de deplacer les repertoires speciaux (racine, corbeille, etc.)
        filtre = {
            ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: uuid_repertoire,
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE
        }
        collection_domaine.update_one(filtre, {
            '$set': set_operation,
            '$currentDate': {Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True},
        })

    def refresh_chemin_sousrepertoires(self, uuid_repertoire):
        """
        Fait une mise a jour de tous les fichiers et sous-repertoires (recursivement) d'un repertoire suite
        a un deplacement ou un changement de nom.

        :param uuid_repertoire: Repertoire qui a ete modifie.
        :return:
        """
        pass

    def maj_fichier(self, transaction):
        """
        Genere ou met a jour un document de fichier avec l'information recue dans une transaction metadata.
        :param transaction:
        :return: True si c'est la version la plus recent, false si la transaction est plus vieille.
        """
        domaine = transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE].get(Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE)
        if domaine != ConstantesGrosFichiers.TRANSACTION_TYPE_METADATA:
            raise ValueError('La transaction doit etre de type metadata. Trouve: %s' % domaine)

        repertoire_uuid = transaction[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)
        document_repertoire = collection_domaine.find_one({ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: repertoire_uuid})

        fuuid = transaction[ConstantesGrosFichiers.DOCUMENT_FICHIER_FUUID]
        est_orphelin = False
        if document_repertoire is None:
            self._logger.info("Fichier orphelin fuuid: %s" % fuuid)
            document_repertoire = collection_domaine.find_one(
                {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_ORPHELINS}
            )
            est_orphelin = True

        uuid_fichier = transaction.get(ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC)
        if uuid_fichier is None:
            # Chercher a identifier le fichier par chemin et nom
            doc_fichier = collection_domaine.find_one({
                ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: transaction[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID],
                ConstantesGrosFichiers.DOCUMENT_FICHIER_NOMFICHIER: transaction[ConstantesGrosFichiers.DOCUMENT_FICHIER_NOMFICHIER]
            })

            if doc_fichier is not None:
                uuid_fichier = doc_fichier[ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC]

        chemin_fichier = '%s/%s' % (
            document_repertoire[ConstantesGrosFichiers.DOCUMENT_CHEMIN],
            document_repertoire[ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE],
        )
        chemin_fichier = chemin_fichier.replace('///', '/').replace('//', '/')
        nom_fichier = transaction[ConstantesGrosFichiers.DOCUMENT_FICHIER_NOMFICHIER]
        if est_orphelin:
            nom_fichier = '%s_%s' % (fuuid, nom_fichier)

        set_on_insert = ConstantesGrosFichiers.DOCUMENT_FICHIER.copy()
        set_on_insert[ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC] =\
            transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE][Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID]
        set_on_insert[ConstantesGrosFichiers.DOCUMENT_FICHIER_NOMFICHIER] = nom_fichier

        set_on_insert[ConstantesGrosFichiers.DOCUMENT_CHEMIN] = chemin_fichier
        set_on_insert[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID] = document_repertoire[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]
        set_on_insert[ConstantesGrosFichiers.DOCUMENT_SECURITE] = transaction[ConstantesGrosFichiers.DOCUMENT_SECURITE]

        operation_currentdate = {
            Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True
        }

        plus_recente_version = True  # Lors d<une MAJ, on change la plus recente version seulement si necessaire
        set_operations = {}
        if uuid_fichier is None:
            # On n'a pas reussi a identifier le fichier. On prepare un nouveau document.
            uuid_fichier = set_on_insert[ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC]
            operation_currentdate[Constantes.DOCUMENT_INFODOC_DATE_CREATION] = True
        else:
            document_fichier = collection_domaine.find_one({Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID: uuid_fichier})
            # Determiner si le fichier est la plus recente version

        # Filtrer transaction pour creer l'entree de version dans le fichier
        masque_transaction = [
            ConstantesGrosFichiers.DOCUMENT_CHEMIN,
            ConstantesGrosFichiers.DOCUMENT_FICHIER_NOMFICHIER,
            ConstantesGrosFichiers.DOCUMENT_FICHIER_TAILLE,
            ConstantesGrosFichiers.DOCUMENT_FICHIER_SHA256,
            ConstantesGrosFichiers.DOCUMENT_FICHIER_FUUID,
            ConstantesGrosFichiers.DOCUMENT_FICHIER_MIMETYPE,
            ConstantesGrosFichiers.DOCUMENT_SECURITE,
            ConstantesGrosFichiers.DOCUMENT_COMMENTAIRES,
        ]
        date_version = transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_EVENEMENT].get('_estampille')
        info_version = {
            ConstantesGrosFichiers.DOCUMENT_VERSION_DATE_VERSION: date_version
        }
        for key in transaction.keys():
            if key in masque_transaction:
                info_version[key] = transaction[key]
        set_operations['%s.%s' % (ConstantesGrosFichiers.DOCUMENT_FICHIER_VERSIONS, fuuid)] = info_version

        if plus_recente_version:
            set_operations[ConstantesGrosFichiers.DOCUMENT_FICHIER_DATEVCOURANTE] = date_version
            set_operations[ConstantesGrosFichiers.DOCUMENT_FICHIER_UUIDVCOURANTE] = \
                transaction[ConstantesGrosFichiers.DOCUMENT_FICHIER_FUUID]
            set_operations[ConstantesGrosFichiers.DOCUMENT_FICHIER_MIMETYPE] = \
                transaction[ConstantesGrosFichiers.DOCUMENT_FICHIER_MIMETYPE]
            set_operations[ConstantesGrosFichiers.DOCUMENT_FICHIER_TAILLE] = \
                transaction[ConstantesGrosFichiers.DOCUMENT_FICHIER_TAILLE]

        operations = {
            '$set': set_operations,
            '$currentDate': operation_currentdate,
            '$setOnInsert': set_on_insert
        }
        filtre = {
            ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC: uuid_fichier,
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_FICHIER,
        }

        self._logger.debug("maj_fichier: filtre = %s" % filtre)
        self._logger.debug("maj_fichier: operations = %s" % operations)
        try:
            resultat = collection_domaine.update_one(filtre, operations, upsert=True)
        except DuplicateKeyError as dke:
            self._logger.info("Cle dupliquee sur fichier %s, on ajoute un id unique dans le nom" % fuuid)
            nom_fichier = '%s_%s' % (uuid.uuid1(), transaction[ConstantesGrosFichiers.DOCUMENT_FICHIER_NOMFICHIER])
            set_on_insert[ConstantesGrosFichiers.DOCUMENT_FICHIER_NOMFICHIER] = nom_fichier
            resultat = collection_domaine.update_one(filtre, operations, upsert=True)

        self._logger.debug("maj_fichier resultat %s" % str(resultat))

        return {'plus_recent': plus_recente_version, 'uuid_fichier': uuid_fichier}

    def renommer_deplacer_fichier(self, uuid_doc, uuid_repertoire=None, nouveau_nom=None):
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)
        document_fichier = collection_domaine.find_one({ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC: uuid_doc})

        ancien_repertoire_uuid = document_fichier[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]
        set_operations = dict()
        if nouveau_nom is not None:
            set_operations[ConstantesGrosFichiers.DOCUMENT_FICHIER_NOMFICHIER] = nouveau_nom
        if uuid_repertoire is not None:
            document_repertoire = collection_domaine.find_one({
                ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: uuid_repertoire,
                Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE
            })
            set_operations[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID] = uuid_repertoire

            chemin_repertoire = document_repertoire[ConstantesGrosFichiers.DOCUMENT_CHEMIN]
            chemin = '%s/%s' % (chemin_repertoire, document_repertoire[ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE])
            chemin = chemin.replace('///', '/').replace('//', '/')
            set_operations[ConstantesGrosFichiers.DOCUMENT_CHEMIN] = chemin

        filtre = {
            ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC: uuid_doc,
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_FICHIER,
        }

        resultat = collection_domaine.update_one(filtre, {
            '$set': set_operations,
            '$currentDate': {Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True},
        })
        self._logger.debug('renommer_deplacer_fichier resultat: %s' % str(resultat))

        return {'ancien_repertoire_uuid': ancien_repertoire_uuid}

    def supprimer_fichier(self, uuid_doc):
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)

        # Trouver l'information de repertoires pour prochain processus
        # On le fait a l'avance pour eviter de commencer les changements et trouver qu'on manque d'info
        document_fichier = collection_domaine.find_one({ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC: uuid_doc})
        repertoire_corbeille = self.get_document_corbeille()
        uuid_repertoire_corbeille = repertoire_corbeille[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]
        ancien_repertoire_uuid = document_fichier[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]

        set_operations = {
            ConstantesGrosFichiers.DOCUMENT_FICHIER_SUPPRIME: True,
        }

        filtre = {
            ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC: uuid_doc,
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_FICHIER,
        }
        resultat = collection_domaine.update_one(filtre, {
            '$set': set_operations,
            '$currentDate': {
                Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True,
                ConstantesGrosFichiers.DOCUMENT_FICHIER_SUPPRIME_DATE: True
            },
        })
        self._logger.debug('supprimer_fichier resultat: %s' % str(resultat))

        return {
            'ancien_repertoire_uuid': ancien_repertoire_uuid,
            'corbeille': uuid_repertoire_corbeille
        }

    def supprimer_repertoire(self, uuid_doc):
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)

        # Trouver l'information de repertoires pour prochain processus
        # On le fait a l'avance pour eviter de commencer les changements et trouver qu'on manque d'info
        document_repertoire = collection_domaine.find_one({
            ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: uuid_doc,
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE,
        })
        repertoire_corbeille = self.get_document_corbeille()
        uuid_repertoire_corbeille = repertoire_corbeille[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]
        ancien_repertoire_uuid = document_repertoire[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_PARENT_ID]

        set_operations = {
            ConstantesGrosFichiers.DOCUMENT_FICHIER_SUPPRIME: True,
        }

        # On ne permet pas de supprimer les repertoires speciaux (racine, corbeille, etc.)
        filtre = {
            ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: uuid_doc,
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE,
        }
        resultat = collection_domaine.update_one(filtre, {
            '$set': set_operations,
            '$currentDate': {
                Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True,
                ConstantesGrosFichiers.DOCUMENT_FICHIER_SUPPRIME_DATE: True,
            },
        })
        self._logger.debug('supprimer_repertoire resultat: %s' % str(resultat))

        return {
            'ancien_repertoire_uuid': ancien_repertoire_uuid,
            'corbeille': uuid_repertoire_corbeille
        }

    def maj_commentaire_repertoire(self, uuid_repertoire, commentaire):
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)

        set_operation = {
            ConstantesGrosFichiers.DOCUMENT_COMMENTAIRES: commentaire
        }
        filtre = {
            ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: uuid_repertoire,
            '$or': [
                {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE},
                {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_RACINE},
                {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_ORPHELINS},
                {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_CORBEILLE},
            ]
        }
        resultat = collection_domaine.update_one(filtre, {
            '$set': set_operation
        })
        self._logger.debug('maj_commentaire_repertoire resultat: %s' % str(resultat))

    def maj_securite_repertoire(self, uuid_repertoire, securite):
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)

        set_operation = {
            ConstantesGrosFichiers.DOCUMENT_SECURITE: securite
        }
        filtre = {
            ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: uuid_repertoire,
            '$or': [
                {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE},
                {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_RACINE},
                {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_ORPHELINS},
                {Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_REPERTOIRE_CORBEILLE},
            ]
        }
        resultat = collection_domaine.update_one(filtre, {
            '$set': set_operation
        })
        self._logger.debug('maj_securite_repertoire resultat: %s' % str(resultat))

    def maj_commentaire_fichier(self, uuid_fichier, commentaire):
        collection_domaine = self.document_dao.get_collection(ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)

        set_operation = {
            ConstantesGrosFichiers.DOCUMENT_COMMENTAIRES: commentaire
        }
        filtre = {
            ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC: uuid_fichier,
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesGrosFichiers.LIBVAL_FICHIER
        }
        resultat = collection_domaine.update_one(filtre, {
            '$set': set_operation
        })
        self._logger.debug('maj_commentaire_fichier resultat: %s' % str(resultat))


# ********** Mappers ************
class TransactionCreerRepertoireVersionMapper:

    def __init__(self):
        self.__mappers = {
            '4': self.map_version_4_to_current,
            '5': self.map_version_5_to_current,
        }

    def map_version_to_current(self, transaction):
        version = transaction[
            Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE][Constantes.TRANSACTION_MESSAGE_LIBELLE_VERSION]
        mapper = self.__mappers[str(version)]
        if mapper is None:
            raise ValueError("Version inconnue: %s" % str(version))

        mapper(transaction)

    def map_version_4_to_current(self, transaction):
        # Il manque le uuid du repertoire. Dans V5, c'est un uuid v1. Mais pour V4 on ne l'avait pas,
        # ca empeche de reconnecter les fichiers crees precedement. Les fichiers deviennent orphelins et
        # doivent etre ramenes sous le bon repertoire a la main. La transaction de deplacement creee a ce moment
        # permet de corriger le probleme de facon permanente.
        uuid_transaction = transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE][Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID]
        transaction[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID] = uuid_transaction

    def map_version_5_to_current(self, transaction):
        """ Version courante, rien a faire """
        pass


# ******************* Processus *******************
class ProcessusGrosFichiers(MGProcessusTransaction):

    def get_collection_transaction_nom(self):
        return ConstantesGrosFichiers.COLLECTION_TRANSACTIONS_NOM

    def get_collection_processus_nom(self):
        return ConstantesGrosFichiers.COLLECTION_PROCESSUS_NOM


class ProcessusTransactionNouvelleVersionMetadata(ProcessusGrosFichiers):
    """
    Processus de d'ajout de nouveau fichier ou nouvelle version d'un fichier
    C'est le processus principal qui depend de deux sous-processus:
     -  ProcessusTransactionNouvelleVersionTransfertComplete
     -  ProcessusNouvelleCleGrosFichier (pour securite 3.protege et 4.secure)
    """

    def __init__(self, controleur: MGPProcesseur, evenement):
        super().__init__(controleur, evenement)

    def initiale(self):
        """ Sauvegarder une nouvelle version d'un fichier """
        transaction = self.charger_transaction()

        # Vierifier si le document de fichier existe deja
        self._logger.debug("Fichier existe, on ajoute une version")
        self.set_etape_suivante(
            ProcessusTransactionNouvelleVersionMetadata.ajouter_version_fichier.__name__)

        fuuid = transaction['fuuid']

        return {'fuuid': fuuid, 'securite': transaction['securite']}

    def ajouter_version_fichier(self):
        # Ajouter version au fichier
        transaction = self.charger_transaction()
        resultat = self._controleur.gestionnaire.maj_fichier(transaction)

        self.set_etape_suivante(
            ProcessusTransactionNouvelleVersionMetadata.maj_repertoire.__name__)

        return resultat

    def maj_repertoire(self):
        uuid_fichier = self.parametres['uuid_fichier']
        self._controleur.gestionnaire.maj_repertoire_fichier(uuid_fichier)

        self.set_etape_suivante(
            ProcessusTransactionNouvelleVersionMetadata.attendre_transaction_transfertcomplete.__name__)

    def attendre_transaction_transfertcomplete(self):
        self.set_etape_suivante(
            ProcessusTransactionNouvelleVersionMetadata.confirmer_hash.__name__,
            self._get_tokens_attente())

    def confirmer_hash(self):
        if self.parametres.get('attente_token') is not None:
            # Il manque des tokens, on boucle.
            self._logger.debug('attendre_transaction_transfertcomplete(): Il reste des tokens actifs, on boucle')
            self.set_etape_suivante(
                ProcessusTransactionNouvelleVersionMetadata.confirmer_hash.__name__)
            return

        # Verifie que le hash des deux transactions (metadata, transfer complete) est le meme.
        self.set_etape_suivante()  # Processus termine

    def _get_tokens_attente(self):
        fuuid = self.parametres.get('fuuid')
        tokens = [
            '%s:%s' % (ConstantesGrosFichiers.TRANSACTION_NOUVELLEVERSION_TRANSFERTCOMPLETE, fuuid)
        ]

        if self.parametres['securite'] in [Constantes.SECURITE_PROTEGE, Constantes.SECURITE_SECURE]:
            tokens.append('%s:%s' % (ConstantesGrosFichiers.TRANSACTION_NOUVELLEVERSION_CLES_RECUES, fuuid))

        return tokens


class ProcessusTransactionNouvelleVersionTransfertComplete(ProcessusGrosFichiers):

    def __init__(self, controleur: MGPProcesseur, evenement):
        super().__init__(controleur, evenement)

    def initiale(self):
        """
        Emet un evenement pour indiquer que le transfert complete est arrive. Comme on ne donne pas de prochaine
        etape, une fois les tokens consommes, le processus sera termine.
        """
        transaction = self.charger_transaction()
        fuuid = transaction.get('fuuid')

        self.set_etape_suivante(ProcessusTransactionNouvelleVersionTransfertComplete.declencher_resumer.__name__)
        return {'fuuid': fuuid}

    def declencher_resumer(self):
        fuuid = self.parametres.get('fuuid')
        token_resumer = '%s:%s' % (ConstantesGrosFichiers.TRANSACTION_NOUVELLEVERSION_TRANSFERTCOMPLETE, fuuid)
        self.resumer_processus([token_resumer])

        # Une fois les tokens consommes, le processus sera termine.
        self.set_etape_suivante()


class ProcessusTransactionNouvelleVersionClesRecues(ProcessusGrosFichiers):

    def __init__(self, controleur: MGPProcesseur, evenement):
        super().__init__(controleur, evenement)

    def initiale(self):
        """
        Emet un evenement pour indiquer que les cles sont recues par le MaitreDesCles.
        """
        transaction = self.charger_transaction()
        fuuid = transaction.get('fuuid')

        token_resumer = '%s:%s' % (ConstantesGrosFichiers.TRANSACTION_NOUVELLEVERSION_CLES_RECUES, fuuid)
        self.resumer_processus([token_resumer])

        self.set_etape_suivante()  # Termine
        return {'fuuid': fuuid}


class ProcessusTransactionCreerRepertoireSpecial(ProcessusGrosFichiers):
    """
    Creer repertoire special (racine, corbeille, etc.)
    """

    def __init__(self, controleur: MGPProcesseur, evenement):
        super().__init__(controleur, evenement)

    def initiale(self):
        """
        Emet un evenement pour indiquer que le transfert complete est arrive. Comme on ne donne pas de prochaine
        etape, une fois les tokens consommes, le processus sera termine.
        """
        transaction = self.charger_transaction()
        mg_libelle = transaction[ConstantesGrosFichiers.TRANSACTION_CHAMP_LIBELLE]
        nom_repertoire = transaction[ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE]
        uuid = transaction[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]

        securite = transaction.get(ConstantesGrosFichiers.DOCUMENT_SECURITE)
        if securite is None:
            securite = Constantes.SECURITE_PRIVE

        document_repertoire = self._controleur.gestionnaire.creer_repertoire_special(
            nom_repertoire, mg_libelle, uuid=uuid, securite=securite)

        self.set_etape_suivante()  # Termine

        return {'document_repertoire': document_repertoire, '_mg-libelle': mg_libelle}


class ProcessusTransactionCreerRepertoire(ProcessusGrosFichiers):

    def __init__(self, controleur: MGPProcesseur, evenement):
        super().__init__(controleur, evenement, TransactionCreerRepertoireVersionMapper())

    def initiale(self):
        """
        Emet un evenement pour indiquer que le transfert complete est arrive. Comme on ne donne pas de prochaine
        etape, une fois les tokens consommes, le processus sera termine.
        """
        transaction = self.charger_transaction()
        repertoire_parent_uuid = transaction[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_PARENT_ID]
        nom_repertoire = transaction[ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE]
        uuid_repertoire = transaction[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]

        securite = transaction.get(ConstantesGrosFichiers.DOCUMENT_SECURITE)
        if securite is None:
            securite = Constantes.SECURITE_PRIVE

        document_repertoire = self._controleur._gestionnaire.creer_repertoire(
            nom_repertoire, repertoire_parent_uuid, uuid_repertoire, securite=securite)

        self.set_etape_suivante(ProcessusTransactionCreerRepertoire.maj_repertoire_parent.__name__)

        return {'document_repertoire': document_repertoire, 'repertoire_parent_uuid': repertoire_parent_uuid}

    def maj_repertoire_parent(self):

        document_repertoire = self.parametres['document_repertoire']
        repertoire_uuid = document_repertoire[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]
        self._controleur.gestionnaire.maj_repertoire_parent(repertoire_uuid)

        self.set_etape_suivante()  # Termine


class ProcessusTransactionRenommerDeplacerRepertoire(ProcessusGrosFichiers):

    def __init__(self, controleur: MGPProcesseur, evenement):
        super().__init__(controleur, evenement)

    def initiale(self):
        transaction = self.charger_transaction()
        uuid_repertoire = transaction[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]

        nom_repertoire = transaction.get(ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE)
        repertoire_parent_uuid = transaction.get(ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_PARENT_ID)

        collection_documents = self.document_dao.get_collection(
            ConstantesGrosFichiers.COLLECTION_DOCUMENTS_NOM)
        document_repertoire = collection_documents.find_one(
            {ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID: uuid_repertoire})

        if document_repertoire is None:
            raise ValueError("Document pour uuid repertoire %s non trouve" % uuid_repertoire)

        # Le processus sert a renommer et deplacer les repertoires.
        # Pour renommer, on a juste le nom et pas necessairement le parent
        # Pour deplacer, on a le nouveau parent mais pas necessairement l'ancien ni le nom
        if nom_repertoire is None:
            nom_repertoire = document_repertoire[ConstantesGrosFichiers.DOCUMENT_NOMREPERTOIRE]

        ancien_parent = document_repertoire[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_PARENT_ID]

        if repertoire_parent_uuid is None:
            repertoire_parent_uuid = ancien_parent

        self._controleur._gestionnaire_domaine.renommer_deplacer_repertoire(
            uuid_repertoire, nom_repertoire, parent_uuid=repertoire_parent_uuid)

        self.set_etape_suivante(ProcessusTransactionRenommerDeplacerRepertoire.maj_repertoire_parent.__name__)

        return {
            'uuid_repertoire': uuid_repertoire,
            'repertoire_parent_uuid': repertoire_parent_uuid,
            'ancien_parent_uuid': ancien_parent
        }

    def maj_repertoire_parent(self):
        repertoire_uuid = self.parametres['uuid_repertoire']
        ancien_parent = self.parametres['ancien_parent_uuid']
        if self.parametres['repertoire_parent_uuid'] == ancien_parent:
            ancien_parent = None  # Pas de unset a faire

        self._controleur._gestionnaire_domaine.maj_repertoire_parent(repertoire_uuid, ancien_parent_uuid=ancien_parent)

        self.set_etape_suivante(ProcessusTransactionRenommerDeplacerRepertoire.refresh_recursif_sousrepertoires.__name__)

    def refresh_recursif_sousrepertoires(self):
        # A faire, un refresh recursif de tous les fichiers/repertoires sous le repertoire modifie

        self.set_etape_suivante()  # Termine


class ProcessusTransactionRenommerDeplacerFichier(ProcessusGrosFichiers):

    def __init__(self, controleur: MGPProcesseur, evenement):
        super().__init__(controleur, evenement)

    def initiale(self):
        transaction = self.charger_transaction()
        uuid_doc = transaction[ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC]
        nouveau_repertoire_uuid = transaction.get(ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID)
        nouveau_nom = transaction.get(ConstantesGrosFichiers.DOCUMENT_FICHIER_NOMFICHIER)

        resultat = self._controleur._gestionnaire_domaine.renommer_deplacer_fichier(
            uuid_doc, uuid_repertoire=nouveau_repertoire_uuid, nouveau_nom=nouveau_nom)

        # Le resultat a deja ancien_repertoire_uuid. On ajoute le nouveau pour permettre de traiter les deux.
        resultat['fichier_uuid'] = uuid_doc
        if nouveau_repertoire_uuid is not None:
            resultat['repertoire_uuid'] = nouveau_repertoire_uuid

        self.set_etape_suivante(ProcessusTransactionRenommerDeplacerFichier.maj_repertoire_parent.__name__)

        return resultat

    def maj_repertoire_parent(self):
        fichier_uuid = self.parametres['fichier_uuid']
        repertoire_uuid = self.parametres.get('repertoire_uuid')
        ancien_repertoire_uuid = self.parametres.get('ancien_repertoire_uuid')

        # Verifier si l'ancien et le nouveau repertoire sont le meme. Dans ce cas on
        # ne fait aucun changement a _l'ancien_.
        if repertoire_uuid is None or repertoire_uuid == ancien_repertoire_uuid:
            ancien_repertoire_uuid = None

        self._controleur._gestionnaire_domaine.maj_repertoire_fichier(fichier_uuid, ancien_repertoire_uuid)

        self.set_etape_suivante()  # Termine


class ProcessusTransactionSupprimerFichier(ProcessusGrosFichiers):

    def __init__(self, controleur: MGPProcesseur, evenement):
        super().__init__(controleur, evenement)

    def initiale(self):
        transaction = self.charger_transaction()
        uuid_doc = transaction[ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC]

        resultat = self._controleur._gestionnaire_domaine.supprimer_fichier(uuid_doc)
        # Le resultat contient ancien_repertoire_uuid.

        self.set_etape_suivante(ProcessusTransactionRenommerDeplacerFichier.maj_repertoire_parent.__name__)

        resultat['fichier_uuid'] = uuid_doc

        return resultat

    def maj_repertoire_parent(self):
        fichier_uuid = self.parametres['fichier_uuid']
        ancien_repertoire_uuid = self.parametres.get('ancien_repertoire_uuid')

        self._controleur._gestionnaire_domaine.maj_repertoire_fichier(fichier_uuid, ancien_repertoire_uuid)

        self.set_etape_suivante()  # Termine


class ProcessusTransactionSupprimerRepertoire(ProcessusGrosFichiers):

    def __init__(self, controleur: MGPProcesseur, evenement):
        super().__init__(controleur, evenement)

    def initiale(self):
        transaction = self.charger_transaction()
        uuid_repertoire = transaction[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]

        resultat = self._controleur._gestionnaire_domaine.supprimer_repertoire(uuid_repertoire)
        # Le resultat contient ancien_repertoire_uuid.

        self.set_etape_suivante(ProcessusTransactionSupprimerRepertoire.maj_repertoire_parent.__name__)

        resultat['uuid_repertoire'] = uuid_repertoire

        return resultat

    def maj_repertoire_parent(self):
        uuid_repertoire = self.parametres['uuid_repertoire']
        ancien_repertoire_uuid = self.parametres.get('ancien_repertoire_uuid')

        self._controleur._gestionnaire_domaine.maj_repertoire_parent(
            uuid_repertoire, ancien_parent_uuid=ancien_repertoire_uuid)

        self.set_etape_suivante()  # Termine


class ProcessusTransactionCommenterRepertoire(ProcessusGrosFichiers):

    def __init__(self, controleur: MGPProcesseur, evenement):
        super().__init__(controleur, evenement)

    def initiale(self):
        transaction = self.charger_transaction()
        uuid_repertoire = transaction[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]
        commentaire = transaction[ConstantesGrosFichiers.DOCUMENT_COMMENTAIRES]
        self._controleur._gestionnaire_domaine.maj_commentaire_repertoire(uuid_repertoire, commentaire)

        self.set_etape_suivante()  # Termine


class ProcessusTransactionCommenterFichier(ProcessusGrosFichiers):

    def __init__(self, controleur: MGPProcesseur, evenement):
        super().__init__(controleur, evenement)

    def initiale(self):
        transaction = self.charger_transaction()
        uuid_fichier = transaction[ConstantesGrosFichiers.DOCUMENT_FICHIER_UUID_DOC]
        commentaire = transaction[ConstantesGrosFichiers.DOCUMENT_COMMENTAIRES]
        self._controleur._gestionnaire_domaine.maj_commentaire_fichier(uuid_fichier, commentaire)

        self.set_etape_suivante()  # Termine


class ProcessusTransactionChangerSecuriteRepertoire(ProcessusGrosFichiers):

    def __init__(self, controleur: MGPProcesseur, evenement):
        super().__init__(controleur, evenement)

    def initiale(self):
        transaction = self.charger_transaction()
        uuid_repertoire = transaction[ConstantesGrosFichiers.DOCUMENT_REPERTOIRE_UUID]
        securite = transaction[ConstantesGrosFichiers.DOCUMENT_SECURITE]
        if securite in [Constantes.SECURITE_PROTEGE, Constantes.SECURITE_PRIVE]:
            self._controleur.gestionnaire.maj_securite_repertoire(uuid_repertoire, securite)
        else:
            raise ValueError("Type de securite non supporte: %s" % securite)

        self.set_etape_suivante()  # Termine

