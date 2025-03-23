# Domaine MaitreDesCles
# Responsable de la gestion et de l'acces aux cles secretes pour les niveaux 3.Protege et 4.Secure.

from millegrilles import Constantes
from millegrilles.Domaines import GestionnaireDomaineStandard, TransactionTypeInconnuError
from millegrilles.domaines.GrosFichiers import ConstantesGrosFichiers
from millegrilles.dao.MessageDAO import TraitementMessageDomaine
from millegrilles.MGProcessus import MGProcessusTransaction

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography import x509
from base64 import b64encode, b64decode

import logging
import datetime
import os
import re


class ConstantesMaitreDesCles:

    DOMAINE_NOM = 'millegrilles.domaines.MaitreDesCles'
    COLLECTION_NOM = DOMAINE_NOM

    COLLECTION_TRANSACTIONS_NOM = COLLECTION_NOM
    COLLECTION_DOCUMENTS_NOM = '%s/documents' % COLLECTION_NOM
    COLLECTION_PROCESSUS_NOM = '%s/processus' % COLLECTION_NOM
    QUEUE_NOM = DOMAINE_NOM

    LIBVAL_CONFIGURATION = 'configuration'

    TRANSACTION_NOUVELLE_CLE_GROSFICHIER = '%s.nouvelleCle.grosFichier' % DOMAINE_NOM
    TRANSACTION_NOUVELLE_CLE_DOCUMENT = '%s.nouvelleCle.document' % DOMAINE_NOM
    TRANSACTION_MAJ_DOCUMENT_CLES = '%s.majcles' % DOMAINE_NOM

    TRANSACTION_DOMAINES_DOCUMENT_CLESRECUES = 'clesRecues'

    REQUETE_CERT_MAITREDESCLES = 'certMaitreDesCles'
    REQUETE_DECRYPTAGE_DOCUMENT = 'decryptageDocument'
    REQUETE_DECRYPTAGE_GROSFICHIER = 'decryptageGrosFichier'

    TRANSACTION_CHAMP_CLESECRETE = 'cle'
    TRANSACTION_CHAMP_CLES = 'cles'
    TRANSACTION_CHAMP_SUJET_CLE = 'sujet'
    TRANSACTION_CHAMP_DOMAINE = 'domaine'
    TRANSACTION_CHAMP_IDDOC = 'id-doc'
    TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS = 'identificateurs_document'
    TRANSACTION_CHAMP_MGLIBELLE = 'mg-libelle'

    TRANSACTION_VERSION_COURANTE = 5

    DOCUMENT_LIBVAL_CLES_GROSFICHIERS = 'cles.grosFichiers'
    DOCUMENT_LIBVAL_CLES_DOCUMENT = 'cles.document'

    DOCUMENT_SECURITE = 'securite'

    DOCUMENT_DEFAUT = {
        Constantes.DOCUMENT_INFODOC_LIBELLE: LIBVAL_CONFIGURATION,
        Constantes.TRANSACTION_MESSAGE_LIBELLE_VERSION: TRANSACTION_VERSION_COURANTE
    }

    # Document utilise pour conserver un ensemble de cles lie a un document
    DOCUMENT_CLES_GROSFICHIERS = {
        Constantes.DOCUMENT_INFODOC_LIBELLE: DOCUMENT_LIBVAL_CLES_GROSFICHIERS,

        # Template a remplir
        'fuuid': None,    # Identificateur unique de version de fichier
        'cles': dict(),   # Dictionnaire indexe par fingerprint de certificat signataire. Valeur: cle secrete cryptee
    }

    DOCUMENT_TRANSACTION_CONSERVER_CLES = {
        TRANSACTION_CHAMP_SUJET_CLE: DOCUMENT_LIBVAL_CLES_GROSFICHIERS,  # Mettre le sujet approprie
        'cles': dict(),  # Dictionnaire indexe par fingerprint de certificat signataire. Valeur: cle secrete cryptee
    }

    DOCUMENT_TRANSACTION_GROSFICHIERRESUME = {
        'fuuid': None,  # Identificateur unique de version de fichier
    }


class GestionnaireMaitreDesCles(GestionnaireDomaineStandard):

    def __init__(self, contexte):
        super().__init__(contexte)
        self._logger = logging.getLogger("%s.%s" % (__name__, self.__class__.__name__))

        nom_millegrille = contexte.configuration.nom_millegrille

        self.__repertoire_cles = '/opt/millegrilles/%s/pki/keys' % nom_millegrille
        self.__repertoire_certs = '/opt/millegrilles/%s/pki/certs' % nom_millegrille
        self.__repertoire_motsdepasse = '/opt/millegrilles/%s/pki/passwords' % nom_millegrille
        self.__prefix_maitredescles = '%s_maitredescles' % nom_millegrille

        self.__certificat_courant = None
        self.__certificat_courant_pem = None
        self.__cle_courante = None
        self.__certificats_backup = None  # Liste de certificats backup utilises pour conserver les cles secretes.

        # Queue message handlers
        self.__handler_requetes_noeuds = None

    def configurer(self):
        super().configurer()

        self.__handler_requetes_noeuds = TraitementRequetesNoeuds(self)

        self.initialiser_document(ConstantesMaitreDesCles.LIBVAL_CONFIGURATION, ConstantesMaitreDesCles.DOCUMENT_DEFAUT)

        self.charger_certificat_courant()
        self.charger_certificats_backup()

        # Index collection domaine
        collection_domaine = self.get_collection()

        # Index par identificateurs_documents, domaine
        collection_domaine.create_index([
            (ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS, 1),
            (Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE, 1),
            (Constantes.DOCUMENT_INFODOC_LIBELLE, 1),
        ], unique=True)

    def charger_certificat_courant(self):
        fichier_cert = '%s/%s.cert.pem' % (self.__repertoire_certs, self.__prefix_maitredescles)
        fichier_cle = '%s/%s.key.pem' % (self.__repertoire_cles, self.__prefix_maitredescles)
        mot_de_passe = '%s/%s.password.txt' % (self.__repertoire_motsdepasse, self.__prefix_maitredescles)

        with open(mot_de_passe, 'rb') as motpasse_courant:
            motpass = motpasse_courant.readline()[0:-1]  # Enlever newline a la fin.
            with open(fichier_cle, "rb") as keyfile:
                cle = serialization.load_pem_private_key(
                    keyfile.read(),
                    password=motpass,
                    backend=default_backend()
                )
                self.__cle_courante = cle

        self._logger.info("Cle courante: %s" % str(self.__cle_courante))

        with open(fichier_cert, 'rb') as certificat_pem:
            certificat_courant_pem = certificat_pem.read()
            # certificat_pem = bytes(certificat_pem, 'utf-8')
            cert = x509.load_pem_x509_certificate(
                certificat_courant_pem,
                backend=default_backend()
            )
            self.__certificat_courant = cert
            self.__certificat_courant_pem = certificat_courant_pem.decode('utf8')

        self._logger.info("Certificat courant: %s" % str(self.__certificat_courant))

    def charger_certificats_backup(self):
        """
        Charge les certificats de backup presents dans le repertoire des certificats.
        Les cles publiques des backups sont utilisees pour re-encrypter les cles secretes.
        :return:
        """
        certificats_backup = list()

        p = re.compile("%s_backup_[0-9]*.cert.pem" % self.configuration.nom_millegrille)
        for file in os.listdir(self.__repertoire_certs):
            if p.match(file) is not None:
                self._logger.debug('Fichier cert backup %s' % os.path.join(self.__repertoire_certs, file))
                certfilepath = os.path.join(self.__repertoire_certs, file)
                with open(certfilepath, 'rb') as certificat_pem:
                    certificat_courant_pem = certificat_pem.read()
                    # certificat_pem = bytes(certificat_pem, 'utf-8')
                    cert = x509.load_pem_x509_certificate(
                        certificat_courant_pem,
                        backend=default_backend()
                    )
                    certificats_backup.append(cert)

        if len(certificats_backup) > 0:
            self.__certificats_backup = certificats_backup

    def identifier_processus(self, domaine_transaction):

        if domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_NOUVELLE_CLE_GROSFICHIER:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusNouvelleCleGrosFichier"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_NOUVELLE_CLE_DOCUMENT:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusNouvelleCleDocument"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_MAJ_DOCUMENT_CLES:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusMAJDocumentCles"
        else:
            processus = super().identifier_processus(domaine_transaction)

        return processus

    def decrypter_contenu(self, contenu):
        """
        Utilise la cle privee en memoire pour decrypter le contenu.
        :param contenu:
        :return:
        """
        contenu_bytes = b64decode(contenu)

        contenu_decrypte = self.__cle_courante.decrypt(
            contenu_bytes,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return contenu_decrypte

    def decrypter_cle(self, dict_cles):
        """
        Decrypte la cle secrete en utilisant la cle prviee d'un certificat charge en memoire
        :param dict_cles: Dictionnaire de cles secretes cryptes, la cle_dict est le fingerprint du certificat
        :return:
        """
        fingerprint_courant = self.get_fingerprint_cert()
        cle_secrete_cryptee = dict_cles.get(fingerprint_courant)
        if cle_secrete_cryptee is not None:
            # On peut decoder la cle secrete
            return self.decrypter_contenu(cle_secrete_cryptee)
        else:
            return None

    def crypter_cle(self, cle_secrete, cert=None):
        if cert is None:
            cert = self.__certificat_courant
        cle_secrete_backup = cert.public_key().encrypt(
            cle_secrete,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        fingerprint = self.get_fingerprint_cert(cert)
        return cle_secrete_backup, fingerprint

    def get_nom_queue(self):
        return ConstantesMaitreDesCles.QUEUE_NOM

    def get_nom_collection(self):
        return ConstantesMaitreDesCles.COLLECTION_DOCUMENTS_NOM

    def get_collection_transaction_nom(self):
        return ConstantesMaitreDesCles.COLLECTION_TRANSACTIONS_NOM

    def get_collection_processus_nom(self):
        return ConstantesMaitreDesCles.COLLECTION_PROCESSUS_NOM

    def get_nom_domaine(self):
        return ConstantesMaitreDesCles.DOMAINE_NOM

    def get_handler_requetes_noeuds(self):
        return self.__handler_requetes_noeuds

    @property
    def get_certificat(self):
        return self.__certificat_courant

    @property
    def get_certificat_pem(self):
        return self.__certificat_courant_pem

    @property
    def get_certificats_backup(self):
        return self.__certificats_backup

    def get_fingerprint_cert(self, cert=None):
        if cert is None:
            cert = self.__certificat_courant
        return b64encode(cert.fingerprint(hashes.SHA1())).decode('utf-8')

    def traiter_cedule(self, evenement):
        pass

    @property
    def version_domaine(self):
        return ConstantesMaitreDesCles.TRANSACTION_VERSION_COURANTE


class TraitementRequetesNoeuds(TraitementMessageDomaine):

    def __init__(self, gestionnaire):
        super().__init__(gestionnaire)
        self._logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def traiter_message(self, ch, method, properties, body):
        message_dict = self.json_helper.bin_utf8_json_vers_dict(body)

        # Verifier quel processus demarrer. On match la valeur dans la routing key.
        routing_key = method.routing_key
        routing_key_sansprefixe = routing_key.replace(
            'requete.%s.' % ConstantesMaitreDesCles.DOMAINE_NOM,
            ''
        )

        if routing_key_sansprefixe == ConstantesMaitreDesCles.REQUETE_CERT_MAITREDESCLES:
            # Transmettre le certificat courant du maitre des cles
            self.transmettre_certificat(properties)

        elif routing_key_sansprefixe == ConstantesMaitreDesCles.REQUETE_DECRYPTAGE_GROSFICHIER:
            self.transmettre_cle_grosfichier(message_dict, properties)

        else:
            # Type de transaction inconnue, on lance une exception
            raise TransactionTypeInconnuError("Type de transaction inconnue: message: %s" % message_dict, routing_key)

    def transmettre_certificat(self, properties):
        """
        Transmet le certificat courant du MaitreDesCles au demandeur.
        :param properties:
        :return:
        """
        self._logger.debug("Transmettre certificat a %s" % properties.reply_to)
        # Genere message reponse
        message_resultat = {
            'certificat': self._gestionnaire.get_certificat_pem
        }

        self._gestionnaire.generateur_transactions.transmettre_reponse(
            message_resultat, properties.reply_to, properties.correlation_id
        )

    def transmettre_cle_grosfichier(self, evenement, properties):
        """
        Verifie si la requete de cle est valide, puis transmet une reponse (cle re-encryptee ou acces refuse)
        :param evenement:
        :param properties:
        :return:
        """
        self._logger.debug("Transmettre cle grosfichier a %s" % properties.reply_to)

        # Verifier que la signature de la requete est valide - c'est fort probable, il n'est pas possible de
        # se connecter a MQ sans un certificat verifie. Mais s'assurer qu'il n'y ait pas de "relais" via un
        # messager qui a acces aux noeuds. La signature de la requete permet de faire cette verification.
        enveloppe_certificat = self.gestionnaire.verificateur_transaction.verifier(evenement)
        # Aucune exception lancee, la signature de requete est valide et provient d'un certificat autorise et connu

        acces_permis = True  # Pour l'instant, les noeuds peuvent tout le temps obtenir l'acces a 4.secure.
        self._logger.debug(
            "Verification signature requete cle grosfichier. Cert: %s" % str(enveloppe_certificat.fingerprint_ascii))

        collection_documents = self.document_dao.get_collection(ConstantesMaitreDesCles.COLLECTION_DOCUMENTS_NOM)
        filtre = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_GROSFICHIERS,
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: {
                'fuuid': evenement['fuuid'],
            }
        }
        document = collection_documents.find_one(filtre)
        # Note: si le document n'est pas trouve, on repond acces refuse (obfuscation)
        reponse = {Constantes.SECURITE_LIBELLE_REPONSE: Constantes.SECURITE_ACCES_REFUSE}
        if document is not None:
            self._logger.debug("Document de cles pour grosfichiers: %s" % str(document))
            if acces_permis:
                cle_secrete = self._gestionnaire.decrypter_cle(document['cles'])
                cle_secrete_reencryptee, fingerprint = self._gestionnaire.crypter_cle(
                    cle_secrete, enveloppe_certificat.certificat)
                reponse = {
                    'cle': b64encode(cle_secrete_reencryptee).decode('utf-8'),
                    'iv': document['iv'],
                    Constantes.SECURITE_LIBELLE_REPONSE: Constantes.SECURITE_ACCES_PERMIS
                }

        self._gestionnaire.generateur_transactions.transmettre_reponse(
            reponse, properties.reply_to, properties.correlation_id
        )


class ProcessusReceptionCles(MGProcessusTransaction):

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)

    def traitement_regenerer(self, id_transaction, parametres_processus):
        """ Aucun traitement necessaire, le resultat est re-sauvegarde sous une nouvelle transaction """
        pass

    def recrypterCle(self, cle_secrete_encryptee):
        cert_maitredescles = self._controleur.gestionnaire.get_certificat
        fingerprint_certmaitredescles = b64encode(cert_maitredescles.fingerprint(hashes.SHA1())).decode('utf-8')
        cles_secretes_encryptees = {fingerprint_certmaitredescles: cle_secrete_encryptee}

        cle_secrete = self._controleur.gestionnaire.decrypter_contenu(cle_secrete_encryptee)
        # self._logger.debug("Cle secrete: %s" % cle_secrete)

        # Re-encrypter la cle secrete avec les cles backup
        if self._controleur.gestionnaire.get_certificats_backup is not None:
            for backup in self._controleur.gestionnaire.get_certificats_backup:
                cle_secrete_backup = backup.public_key().encrypt(
                    cle_secrete,
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None
                    )
                )
                fingerprint = b64encode(backup.fingerprint(hashes.SHA1())).decode('utf-8')
                cles_secretes_encryptees[fingerprint] = b64encode(cle_secrete_backup).decode('utf-8')

        return cles_secretes_encryptees

    def generer_transaction_majcles(self, sujet):
        generateur_transaction = self.generateur_transactions

        transaction_nouvellescles = ConstantesMaitreDesCles.DOCUMENT_TRANSACTION_CONSERVER_CLES.copy()
        transaction_nouvellescles[ConstantesMaitreDesCles.TRANSACTION_CHAMP_SUJET_CLE] = sujet
        transaction_nouvellescles[ConstantesMaitreDesCles.TRANSACTION_CHAMP_CLES] = \
            self.parametres['cles_secretes_encryptees']
        transaction_nouvellescles['iv'] = self.parametres['iv']

        # Copier les champs d'identification de ce document
        transaction_nouvellescles[Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE] = \
            self.parametres[Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE]
        transaction_nouvellescles[Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID] = \
            self.parametres[Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID]
        transaction_nouvellescles[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS] = \
            self.parametres[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS]

        # La transaction va mettre a jour (ou creer) les cles pour
        generateur_transaction.soumettre_transaction(
            transaction_nouvellescles,
            ConstantesMaitreDesCles.TRANSACTION_MAJ_DOCUMENT_CLES,
            version=ConstantesMaitreDesCles.TRANSACTION_VERSION_COURANTE
        )


class ProcessusNouvelleCleGrosFichier(ProcessusReceptionCles):

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def traitement_regenerer(self, id_transaction, parametres_processus):
        """ Aucun traitement necessaire, le resultat est re-sauvegarde sous une nouvelle transaction """
        pass

    def initiale(self):
        transaction = self.transaction

        # Decrypter la cle secrete et la re-encrypter avec toutes les cles backup
        cle_secrete_encryptee = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_CLESECRETE]
        cles_secretes_encryptees = self.recrypterCle(cle_secrete_encryptee)
        identificateurs_document = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS]

        self.set_etape_suivante(ProcessusNouvelleCleGrosFichier.generer_transaction_cles_backup.__name__)

        return {
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: identificateurs_document,
            'fuuid': identificateurs_document['fuuid'],
            'cles_secretes_encryptees': cles_secretes_encryptees,
            'iv': transaction['iv'],
        }

    def generer_transaction_cles_backup(self):
        """
        Sauvegarder les cles de backup sous forme de transaction dans le domaine MaitreDesCles.
        Va aussi declencher la mise a jour du document de cles associe.
        :return:
        """
        self.generer_transaction_majcles(ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_GROSFICHIERS)
        self.set_etape_suivante(ProcessusNouvelleCleGrosFichier.mettre_token_resumer_transaction.__name__)

    def mettre_token_resumer_transaction(self):
        """
        Mettre le token pour permettre a GrosFichier de resumer son processus de sauvegarde du fichier.
        :return:
        """
        generateur_transaction = self.generateur_transactions
        transaction_resumer = ConstantesMaitreDesCles.DOCUMENT_TRANSACTION_GROSFICHIERRESUME.copy()
        transaction_resumer['fuuid'] = self.parametres['fuuid']
        domaine_routing = ConstantesGrosFichiers.TRANSACTION_NOUVELLEVERSION_CLES_RECUES

        # La transaction va mettre permettre au processu GrosFichiers.nouvelleVersion de continuer
        self._logger.debug("Transmission nouvelle transaction cle recues pour GrosFichier")
        generateur_transaction.soumettre_transaction(transaction_resumer, domaine_routing)

        self.set_etape_suivante()  # Termine
        return {'resumer': transaction_resumer}


class ProcessusMAJDocumentCles(MGProcessusTransaction):

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement, TransactionDocumentMajClesVersionMapper())
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def initiale(self):
        transaction = self.transaction

        # Extraire les cles de document de la transaction (par processus d'elimination)
        cles_document = {
            Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE:
                transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE],
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS:
                transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS],
        }

        contenu_on_insert = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_SUJET_CLE],
            Constantes.DOCUMENT_INFODOC_DATE_CREATION: datetime.datetime.utcnow(),
            'iv': transaction['iv'],
        }
        contenu_on_insert.update(cles_document)

        contenu_date = {
            Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: {'$type': 'date'},
        }

        contenu_set = {
            Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID: transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID],
        }
        for fingerprint in transaction['cles'].keys():
            cle_dict = 'cles.%s' % fingerprint
            valeur = transaction['cles'].get(fingerprint)
            contenu_set[cle_dict] = valeur

        if transaction.get(ConstantesMaitreDesCles.DOCUMENT_SECURITE) is not None:
            contenu_set[ConstantesMaitreDesCles.DOCUMENT_SECURITE] = \
                transaction[ConstantesMaitreDesCles.DOCUMENT_SECURITE]
        else:
            # Par defaut, on met le document en mode secure
            contenu_on_insert[ConstantesMaitreDesCles.DOCUMENT_SECURITE] = Constantes.SECURITE_SECURE

        operations_mongo = {
            '$set': contenu_set,
            '$currentDate': contenu_date,
            '$setOnInsert': contenu_on_insert,
        }

        collection_documents = self.document_dao.get_collection(ConstantesMaitreDesCles.COLLECTION_DOCUMENTS_NOM)
        self.__logger.debug("Operations: %s" % str({'filtre': cles_document, 'operation': operations_mongo}))

        resultat_update = collection_documents.update_one(filter=cles_document, update=operations_mongo, upsert=True)
        self._logger.info("_id du nouveau document MaitreDesCles: %s" % str(resultat_update.upserted_id))

        self.set_etape_suivante()  # Termine


class ProcessusNouvelleCleDocument(ProcessusReceptionCles):

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def traitement_regenerer(self, id_transaction, parametres_processus):
        """ Aucun traitement necessaire, le resultat est re-sauvegarde sous une nouvelle transaction """
        pass

    def initiale(self):
        transaction = self.transaction
        domaine = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_DOMAINE]
        # UUID du contenu, pas celui dans en-tete
        uuid_transaction_doc = transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID]
        iddoc = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS]

        # Decrypter la cle secrete et la re-encrypter avec toutes les cles backup
        cle_secrete_encryptee = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_CLESECRETE]
        cles_secretes_encryptees = self.recrypterCle(cle_secrete_encryptee)
        self._logger.debug("Cle secrete encryptee: %s" % cle_secrete_encryptee)

        self.set_etape_suivante(ProcessusNouvelleCleDocument.generer_transaction_cles_backup.__name__)

        return {
            'domaine': domaine,
            Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID: uuid_transaction_doc,
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: iddoc,
            'cles_secretes_encryptees': cles_secretes_encryptees,
            'iv': transaction['iv'],
        }

    def generer_transaction_cles_backup(self):
        """
        Sauvegarder les cles de backup sous forme de transaction dans le domaine MaitreDesCles.
        Va aussi declencher la mise a jour du document de cles associe.
        :return:
        """
        self.generer_transaction_majcles(ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_DOCUMENT)

        self.set_etape_suivante(ProcessusNouvelleCleDocument.mettre_token_resumer_transaction.__name__)

    def mettre_token_resumer_transaction(self):
        """
        Mettre le token pour permettre a GrosFichier de resumer son processus de sauvegarde du fichier.
        :return:
        """
        generateur_transaction = self.generateur_transactions
        identificateurs_document = self.parametres[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS]
        transaction_resumer = {
            Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE:
                self.parametres[Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE],
            Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID:
                self.parametres[Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID],
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: identificateurs_document,
        }

        domaine_routing = '%s.%s' % (
            self.parametres['domaine'], ConstantesMaitreDesCles.TRANSACTION_DOMAINES_DOCUMENT_CLESRECUES)

        # La transaction va mettre permettre au processu GrosFichiers.nouvelleVersion de continuer
        self._logger.debug("Transmission nouvelle transaction cle recues pour %s" % domaine_routing)
        generateur_transaction.soumettre_transaction(transaction_resumer, domaine_routing)

        self.set_etape_suivante()  # Termine
        return {'resumer': transaction_resumer}


class TransactionDocumentMajClesVersionMapper:
    """
    Mapper de versions pour la transaction DocumentCles (GrosFichiers)
    """

    def __init__(self):
        self.__mappers = {
            '4': self.map_version_4_to_current,
            '5': self.map_version_5_to_current,
        }

        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def map_version_to_current(self, transaction):
        version = transaction[
            Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE][Constantes.TRANSACTION_MESSAGE_LIBELLE_VERSION]
        mapper = self.__mappers[str(version)]
        if mapper is None:
            raise ValueError("Version inconnue: %s" % str(version))

        mapper(transaction)

    def map_version_4_to_current(self, transaction):
        if transaction.get('fuuid') is not None:
            fuuid = transaction.get('fuuid')
            # Type GrosFichiers
            document = {
                Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE: ConstantesGrosFichiers.DOMAINE_NOM,
                Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID: fuuid,
                ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: {
                    ConstantesGrosFichiers.DOCUMENT_FICHIER_FUUID: fuuid,
                }
            }
            del transaction['fuuid']
            transaction.update(document)
            self.__logger.debug("Mapping V4->5 transaction GrosFichiers: %s" % str(transaction))
        elif transaction.get('mg-libelle'):
            document = {
                Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID: transaction['uuid'],
                ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: {
                    Constantes.DOCUMENT_INFODOC_LIBELLE: transaction['mg-libelle'],
                }
            }
            del transaction['mg-libelle']
            transaction.update(document)
            self.__logger.debug("Mapping V4->5 transaction Parametres: %s" % str(transaction))

    def map_version_5_to_current(self, transaction):
        """ Version courante, rien a faire """
        pass
