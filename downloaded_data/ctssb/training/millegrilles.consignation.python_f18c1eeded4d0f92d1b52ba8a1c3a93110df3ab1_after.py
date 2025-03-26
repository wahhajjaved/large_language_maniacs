# Domaine MaitreDesCles
# Responsable de la gestion et de l'acces aux cles secretes pour les niveaux 3.Protege et 4.Secure.

from millegrilles import Constantes
from millegrilles.Constantes import ConstantesMaitreDesCles, ConstantesSecurite, ConstantesSecurityPki
from millegrilles.Domaines import GestionnaireDomaineStandard, TransactionTypeInconnuError, \
    TraitementMessageDomaineRequete, TraitementRequetesProtegees, TraitementCommandesProtegees, TraitementCommandesSecures
from millegrilles.domaines.GrosFichiers import ConstantesGrosFichiers
from millegrilles.dao.MessageDAO import CertificatInconnu
from millegrilles.MGProcessus import MGProcessusTransaction, MGProcessus
from millegrilles.util.X509Certificate import EnveloppeCleCert, \
    ConstantesGenerateurCertificat, RenouvelleurCertificat, PemHelpers
from millegrilles.util.JSONEncoders import DocElemFilter
from millegrilles.domaines.Pki import ConstantesPki
from millegrilles.SecuritePKI import EnveloppeCertificat
from millegrilles.domaines.Annuaire import ConstantesAnnuaire

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography import x509
from base64 import b64encode, b64decode
from typing import Optional

import binascii
import logging
import datetime


class TraitementRequetesNoeuds(TraitementMessageDomaineRequete):

    def __init__(self, gestionnaire):
        super().__init__(gestionnaire)
        self._logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def traiter_requete(self, ch, method, properties, body, message_dict):
        # Verifier quel processus demarrer. On match la valeur dans la routing key.
        routing_key = method.routing_key
        routing_key_sansprefixe = routing_key.replace(
            'requete.%s.' % ConstantesMaitreDesCles.DOMAINE_NOM,
            ''
        )

        if routing_key_sansprefixe == ConstantesMaitreDesCles.REQUETE_CERT_MAITREDESCLES:
            # Transmettre le certificat courant du maitre des cles
            self.gestionnaire.transmettre_certificat(properties)
        else:
            # Type de transaction inconnue, on lance une exception
            raise TransactionTypeInconnuError("Type de transaction inconnue: message: %s" % message_dict, routing_key)


class TraitementRequetesMaitreDesClesProtegees(TraitementRequetesProtegees):

    def traiter_requete(self, ch, method, properties, body, message_dict):
        domaine_routing_key = method.routing_key.replace('requete.%s.' % ConstantesMaitreDesCles.DOMAINE_NOM, '')

        action = domaine_routing_key.split('.')[-1]

        reponse = None
        if domaine_routing_key == ConstantesMaitreDesCles.REQUETE_CLE_RACINE:
            reponse = self.gestionnaire.transmettre_cle_racine(properties, message_dict)
        elif domaine_routing_key == ConstantesMaitreDesCles.REQUETE_DECRYPTAGE_GROSFICHIER:
            self.gestionnaire.transmettre_cle_grosfichier(message_dict, properties)
        elif domaine_routing_key == ConstantesMaitreDesCles.REQUETE_DECRYPTAGE_DOCUMENT:
            self.gestionnaire.transmettre_cle_document(message_dict, properties)
        elif domaine_routing_key == ConstantesMaitreDesCles.REQUETE_TROUSSEAU_HEBERGEMENT:
            self.gestionnaire.transmettre_trousseau_hebergement(message_dict, properties)
        elif action == ConstantesMaitreDesCles.REQUETE_CERT_MAITREDESCLES:
            self.gestionnaire.transmettre_certificat(properties)
        else:
            reponse = super().traiter_requete(ch, method, properties, body, message_dict)

        if reponse is not None:
            self.transmettre_reponse(message_dict, reponse, properties.reply_to, properties.correlation_id)


class TraitementCommandesMaitreDesClesProtegees(TraitementCommandesProtegees):

    def traiter_commande(self, enveloppe_certificat, ch, method, properties, body, message_dict):
        routing_key = method.routing_key

        resultat: dict
        if routing_key == 'commande.%s.%s' % (ConstantesMaitreDesCles.DOMAINE_NOM, ConstantesMaitreDesCles.COMMANDE_SIGNER_CLE_BACKUP):
            resultat = self.gestionnaire.signer_cle_backup(properties, message_dict)
        elif routing_key == 'commande.%s.%s' % (
            ConstantesMaitreDesCles.DOMAINE_NOM, ConstantesMaitreDesCles.COMMANDE_RESTAURER_BACKUP_CLES):
                resultat = self.gestionnaire.restaurer_backup_cles(properties, message_dict)
        elif routing_key == 'commande.%s.%s' % (
            ConstantesMaitreDesCles.DOMAINE_NOM, ConstantesMaitreDesCles.COMMANDE_SIGNER_CSR):
                resultat = self.gestionnaire.signer_csr(properties, message_dict)
        elif routing_key == 'commande.%s.%s' % (
            ConstantesMaitreDesCles.DOMAINE_NOM, ConstantesMaitreDesCles.COMMANDE_SIGNER_NAVIGATEUR_CSR):
                resultat = self.gestionnaire.signer_csr_navigateur(properties, message_dict)
        else:
            resultat = super().traiter_commande(enveloppe_certificat, ch, method, properties, body, message_dict)

        return resultat


class TraitementCommandesMaitreDesClesSecures(TraitementCommandesSecures):

    def traiter_commande(self, enveloppe_certificat, ch, method, properties, body, message_dict):
        routing_key = method.routing_key
        correlation_id = properties.correlation_id

        prefixe_commande = 'commande.' + ConstantesMaitreDesCles.DOMAINE_NOM + '.'

        if routing_key == prefixe_commande + ConstantesMaitreDesCles.COMMANDE_SIGNER_CLE_BACKUP:
            resultat = self.gestionnaire.signer_cle_backup(properties, message_dict)

        elif routing_key == prefixe_commande + ConstantesMaitreDesCles.COMMANDE_CREER_CLES_MILLEGRILLE_HEBERGEE:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusCreerClesMilleGrilleHebergee"
            resultat = self.gestionnaire.demarreur_processus.demarrer_processus(processus, message_dict)

        elif routing_key == prefixe_commande + ConstantesMaitreDesCles.COMMANDE_SIGNER_CSR_CA_DEPENDANT:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusSignerCSRCADependant"
            resultat = self.gestionnaire.demarreur_processus.demarrer_processus(processus, message_dict)

        elif correlation_id == ConstantesMaitreDesCles.CORRELATION_CERTIFICATS_BACKUP:
            resultat = self.gestionnaire.verifier_certificats_backup(message_dict)

        else:
            resultat = super().traiter_commande(enveloppe_certificat, ch, method, properties, body, message_dict)

        return resultat


class GestionnaireMaitreDesCles(GestionnaireDomaineStandard):

    def __init__(self, contexte):
        super().__init__(contexte)
        self._logger = logging.getLogger("%s.%s" % (__name__, self.__class__.__name__))

        # self.__repertoire_maitredescles = self.configuration.pki_config[Constantes.CONFIG_MAITREDESCLES_DIR]

        # self.__nomfichier_maitredescles_cert = self.configuration.pki_config[Constantes.CONFIG_PKI_CERT_MAITREDESCLES]
        self.__nomfichier_autorite_cert = self.configuration.pki_config[Constantes.CONFIG_PKI_CERT_MILLEGRILLE]
        # self.__nomfichier_maitredescles_key = self.configuration.pki_config[Constantes.CONFIG_PKI_KEY_MAITREDESCLES]
        # self.__nomfichier_maitredescles_password = self.configuration.pki_config[Constantes.CONFIG_PKI_PASSWORD_MAITREDESCLES]
        self.__clecert_intermediaire = None  # Cle et certificat de millegrille
        # self.__clecert_maitredescles = None  # Cle et certificat de maitredescles local
        # self.__certificat_courant_pem = None
        self.__certificat_intermediaires_pem = None
        self.__certificat_millegrille: Optional[EnveloppeCertificat] = None
        self.__certificats_backup = dict()  # Liste de certificats backup utilises pour conserver les cles secretes.
        self.__ca_file_pem = None
        self.__dict_ca = None  # Key=akid, Value=x509.Certificate()

        self.__renouvelleur_certificat = None

        # Queue message handlers
        self.__handler_requetes = {
            Constantes.SECURITE_SECURE: TraitementRequetesMaitreDesClesProtegees(self),
            Constantes.SECURITE_PROTEGE: TraitementRequetesMaitreDesClesProtegees(self),
            Constantes.SECURITE_PRIVE: TraitementRequetesNoeuds(self),
            Constantes.SECURITE_PUBLIC: TraitementRequetesNoeuds(self),
        }

        self.__handler_commandes = super().get_handler_commandes()
        self.__handler_commandes[Constantes.SECURITE_PROTEGE] = TraitementCommandesMaitreDesClesProtegees(self)
        self.__handler_commandes[Constantes.SECURITE_SECURE] = TraitementCommandesMaitreDesClesSecures(self)

        self.__encryption_helper = None

    def configurer(self):
        super().configurer()

        self.charger_ca_chaine()
        self.__clecert_intermediaire = self.charger_clecert_intermediaire()
        self.__certificat_intermediaires_pem = self.__clecert_intermediaire.cert_bytes.decode('utf-8')

        self.__renouvelleur_certificat = RenouvelleurCertificat(
            self.configuration.idmg,
            self.__dict_ca,
            clecert_intermediaire=self.__clecert_intermediaire
        )

        # try:
        #     self.charger_certificat_courant()
        # except FileNotFoundError as fnf:
        #     self._logger.warning("Certificat maitredescles non trouve, on va en generer un nouveau. %s" % str(fnf))
        #     self.creer_certificat_maitredescles()

        # Faire une demande pour charger les certificats de backup courants
        self.demander_certificats_backup()

        # Index collection domaine
        collection_domaine = self.get_collection()

        # Index par identificateurs_documents, domaine
        collection_domaine.create_index(
            [
                (ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS, 1),
                (Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE, 1),
                (Constantes.DOCUMENT_INFODOC_LIBELLE, 1),
            ],
            name='domaine-libelle',
            unique=True,
        )

    def demarrer(self):
        super().demarrer()
        self.initialiser_document(ConstantesMaitreDesCles.LIBVAL_CONFIGURATION, ConstantesMaitreDesCles.DOCUMENT_DEFAUT)

    def charger_ca_chaine(self):
        self.__dict_ca = dict()

        self._logger.info("CA FILE: %s" % self.configuration.pki_cafile)
        ca_file = self.configuration.pki_cafile
        with open(ca_file, 'rb') as fichier:
            cert = fichier.read()
            self.__ca_file_pem = cert.decode('utf-8')
            x509_cert = x509.load_pem_x509_certificate(cert, backend=default_backend())
            skid = EnveloppeCleCert.get_subject_identifier(x509_cert)
            self.__dict_ca[skid] = x509_cert
            self.__certificat_millegrille = EnveloppeCertificat(certificat_pem=cert)

        self._logger.info("Cert maitre des cles: %s" % self.configuration.pki_certfile)
        with open(self.configuration.pki_certfile, 'r') as fichier:
            chaine = fichier.read()
            chaine = PemHelpers.split_certificats(chaine)

            # Prendre tous les certificats apres le premier (c'est celui du maitre des cles)
            for cert in chaine[1:]:
                x509_cert = x509.load_pem_x509_certificate(cert.encode('utf-8'), backend=default_backend())
                skid = EnveloppeCleCert.get_subject_identifier(x509_cert)
                self.__dict_ca[skid] = x509_cert

    def charger_clecert_intermediaire(self) -> EnveloppeCleCert:
        """
        Charge le certificat et la cle intermediaire. Permet de signer des certificats au nom de la MilleGrille.
        :return:
        """
        clecert = self.configuration.pki_config.get(Constantes.CONFIG_PKI_CLECERT_INTERMEDIAIRE)

        if not clecert:
            password_intermediaire_path = self.configuration.pki_config[Constantes.CONFIG_PKI_PASSWORD_INTERMEDIAIRE]
            with open(password_intermediaire_path, 'rb') as fichier:
                password_intermediaire = fichier.read()

            cert_millegrille = self.configuration.pki_config[Constantes.CONFIG_PKI_CERT_INTERMEDIAIRE]
            key_millegrille = self.configuration.pki_config[Constantes.CONFIG_PKI_KEY_INTERMEDIAIRE]
            clecert = EnveloppeCleCert()
            clecert.from_files(
                key_millegrille,
                cert_millegrille,
                password_intermediaire,
            )

        return clecert

    # def creer_certificat_maitredescles(self):
    #     self._logger.info("Generation de nouveau certificat de maitre des cles")
    #     hostname = socket.gethostname()
    #     generateurMaitreDesCles = GenererMaitredesclesCryptage(
    #         self.configuration.idmg,
    #         ConstantesGenerateurCertificat.ROLE_MAITREDESCLES,
    #         hostname,
    #         self.__dict_ca,
    #         self.__clecert_intermediaire
    #     )
    #     clecert = generateurMaitreDesCles.generer()
    #
    #     # repertoire_maitredescles = self.configuration.pki_config[Constantes.CONFIG_MAITREDESCLES_DIR]
    #     self._logger.debug("Sauvegarde cert maitre des cles: %s/%s" % (self.__repertoire_maitredescles, self.__nomfichier_maitredescles_cert))
    #     with open('%s/%s' % (self.__repertoire_maitredescles, self.__nomfichier_maitredescles_key), 'wb') as fichier:
    #         fichier.write(clecert.private_key_bytes)
    #     with open('%s/%s' % (self.__repertoire_maitredescles, self.__nomfichier_maitredescles_password), 'wb') as fichier:
    #         fichier.write(clecert.password)
    #     with open('%s/%s' % (self.__repertoire_maitredescles, self.__nomfichier_maitredescles_cert), 'wb') as fichier:
    #         fichier.write(clecert.cert_bytes)
    #     with open('%s/%s' % (self.__repertoire_maitredescles, self.__nomfichier_autorite_cert), 'w') as fichier:
    #         fichier.write(clecert.chaine[1])
    #
    #     self._logger.info("Nouveau certificat MaitreDesCles genere:\n%s" % (clecert.cert_bytes.decode('utf-8')))
    #
    #     # Enchainer pour charger le certificat normalement
    #     self.charger_certificat_courant()

    # def charger_certificat_courant(self):
    #     fichier_cert = '%s/%s' % (self.__repertoire_maitredescles, self.__nomfichier_maitredescles_cert)
    #     fichier_autorite = '%s/%s' % (self.__repertoire_maitredescles, self.__nomfichier_autorite_cert)
    #     fichier_cle = '%s/%s' % (self.__repertoire_maitredescles, self.__nomfichier_maitredescles_key)
    #     mot_de_passe = '%s/%s' % (self.__repertoire_maitredescles, self.__nomfichier_maitredescles_password)
    #
    #     with open(mot_de_passe, 'rb') as motpasse_courant:
    #         motpass = motpasse_courant.readline().strip()
    #     with open(fichier_cle, "rb") as keyfile:
    #         cle = serialization.load_pem_private_key(
    #             keyfile.read(),
    #             password=motpass,
    #             backend=default_backend()
    #         )
    #
    #     with open(fichier_cert, 'rb') as certificat_pem:
    #         certificat_courant_pem = certificat_pem.read()
    #         cert = x509.load_pem_x509_certificate(
    #             certificat_courant_pem,
    #             backend=default_backend()
    #         )
    #         cert_fullchain = certificat_courant_pem.decode('utf8')
    #         self.__certificat_courant_pem = PemHelpers.split_certificats(cert_fullchain)[0]
    #
    #     with open(fichier_autorite, 'rb') as fichier:
    #         certificat_autorite_pem = fichier.read()
    #         self.__certificat_intermediaires_pem = certificat_autorite_pem.decode('utf8')
    #
    #     self.__clecert_maitredescles = EnveloppeCleCert(cle, cert, motpass)
    #
    #     self._logger.info("Certificat courant: %s" % str(cert.subject))

    def demander_certificats_backup(self):
        requete = {}
        domaine = '%s.%s' % (ConstantesPki.DOMAINE_NOM, ConstantesPki.REQUETE_CERTIFICAT_BACKUP)
        queue = '%s.commande.4.secure' % ConstantesMaitreDesCles.QUEUE_NOM
        self.generateur_transactions.transmettre_requete(
            requete,
            domaine,
            correlation_id=ConstantesMaitreDesCles.CORRELATION_CERTIFICATS_BACKUP,
            reply_to=queue,
            securite=Constantes.SECURITE_SECURE,
        )

    def verifier_certificats_backup(self, message_dict):
        """
        Charge les certificats de backup presents dans le repertoire des certificats.
        Les cles publiques des backups sont utilisees pour re-encrypter les cles secretes.
        :return:
        """
        certificats = message_dict.get('certificats') or message_dict['resultats']['certificats']

        verificateur_certificats = self.verificateur_certificats
        for fingerprint_hex, certificat in certificats.items():

            enveloppe = EnveloppeCertificat(certificat_pem=certificat)
            fingerprint_b64 = EnveloppeCertificat.calculer_fingerprint_b64(enveloppe.certificat)

            # Verifier que c'est un certificat du bon type
            roles_acceptes = [
                ConstantesGenerateurCertificat.ROLE_BACKUP, ConstantesGenerateurCertificat.ROLE_MAITREDESCLES
            ]
            if any([role in roles_acceptes for role in enveloppe.get_roles]):
                resultat_verification = verificateur_certificats.verifier_chaine(enveloppe)
                if resultat_verification:
                    self.__certificats_backup[fingerprint_b64] = enveloppe
            else:
                self._logger.warning("Certificat fournit pour backup n'a pas le role 'backup' : fingerprint hex " + fingerprint_hex)

        processus = "millegrilles_domaines_MaitreDesCles:ProcessusTrouverClesBackupManquantes"
        fingerprints_backup = {'fingerprints_base64': list(self.__certificats_backup.keys())}
        self.demarrer_processus(processus, fingerprints_backup)

    def identifier_processus(self, domaine_transaction):

        domaine_action = domaine_transaction.split('.')[-1]

        if domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_NOUVELLE_CLE_GROSFICHIER:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusNouvelleCleGrosFichier"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_NOUVELLE_CLE_BACKUPTRANSACTIONS:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusNouvelleCleBackupTransaction"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_NOUVELLE_CLE_DOCUMENT:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusNouvelleCleDocument"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_MAJ_DOCUMENT_CLES:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusMAJDocumentCles"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_MAJ_MOTDEPASSE:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusMAJMotdepasse"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_RENOUVELLEMENT_CERTIFICAT:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusRenouvellerCertificat"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_SIGNER_CERTIFICAT_NOEUD:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusSignerCertificatNoeud"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_GENERER_CERTIFICAT_NAVIGATEUR:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusGenererCertificatNavigateur"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_DECLASSER_CLE_GROSFICHIER:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusDeclasserCleGrosFichier"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_GENERER_DEMANDE_INSCRIPTION:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusGenererDemandeInscription"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_GENERER_CERTIFICAT_POUR_TIERS:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusGenererCertificatPourTiers"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_HEBERGEMENT_NOUVEAU_TROUSSEAU:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusHebergementNouveauTrousseau"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_HEBERGEMENT_MAJ_TROUSSEAU:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusHebergementMajTrousseau"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_HEBERGEMENT_MOTDEPASSE_CLE:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusHebergementMotdepasseCle"
        elif domaine_transaction == ConstantesMaitreDesCles.TRANSACTION_HEBERGEMENT_SUPPRIMER:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusHebergementSupprimer"

        elif domaine_action == ConstantesMaitreDesCles.TRANSACTION_NOUVELLE_CLE_GROSFICHIER_BACKUP:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusCleGrosfichierBackup"
        elif domaine_action == ConstantesMaitreDesCles.TRANSACTION_NOUVELLE_CLE_BACKUPTRANSACTIONS_BACKUP:
            processus = "millegrilles_domaines_MaitreDesCles:ProcessusNouvelleCleBackupTransactionBackup"

        else:
            processus = super().identifier_processus(domaine_transaction)

        return processus

    def decrypter_contenu(self, contenu):
        """
        Utilise la cle privee en memoire pour decrypter le contenu.
        :param contenu:
        :return:
        """
        return self._contexte.signateur_transactions.dechiffrage_asymmetrique(contenu)

    def decrypter_cle(self, dict_cles):
        """
        Decrypte la cle secrete en utilisant la cle prviee d'un certificat charge en memoire
        :param dict_cles: Dictionnaire de cles secretes cryptes, la cle_dict est le fingerprint du certificat
        :return:
        """
        enveloppe = self._contexte.signateur_transactions.enveloppe_certificat_courant
        fingerprint_courant = enveloppe.fingerprint_b64
        cle_secrete_cryptee = dict_cles.get(fingerprint_courant)
        if cle_secrete_cryptee is not None:
            # On peut decoder la cle secrete
            return self.decrypter_contenu(cle_secrete_cryptee)
        else:
            return None

    def decrypter_motdepasse(self, dict_cles):
        """
        Decrypte un mot de passe en trouvant la cle correspondante
        :param dict_cles: Dictionnaire de mots de passes cryptes, la key est le fingerprint du certificat
        :return:
        """
        enveloppe = self._contexte.signateur_transactions.enveloppe_certificat_courant
        fingerprint_courant = enveloppe.fingerprint_b64
        cle_secrete_cryptee = dict_cles.get(fingerprint_courant)
        if cle_secrete_cryptee is not None:
            # On peut decoder la cle secrete
            motdepasse = self.decrypter_contenu(cle_secrete_cryptee)
            return b64encode(motdepasse)
        else:
            return None

    def decrypter_grosfichier(self, fuuid):
        """
        Verifie si la requete de cle est valide, puis transmet une reponse en clair.
        Le fichier est maintenant declasse, non protege.
        :param fuuid:
        :return:
        """
        collection_documents = self.document_dao.get_collection(ConstantesMaitreDesCles.COLLECTION_DOCUMENTS_NOM)
        filtre = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_GROSFICHIERS,
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: {
                'fuuid': fuuid,
            }
        }
        document = collection_documents.find_one(filtre)
        # Note: si le document n'est pas trouve, on repond acces refuse (obfuscation)
        reponse = {Constantes.SECURITE_LIBELLE_REPONSE: Constantes.SECURITE_ACCES_REFUSE}
        if document is not None:
            self._logger.debug("Document de cles pour grosfichiers: %s" % str(document))
            cle_secrete = self.decrypter_cle(document['cles'])
            reponse = {
                'cle_secrete_decryptee': b64encode(cle_secrete).decode('utf-8'),
                'iv': document['iv'],
                Constantes.SECURITE_LIBELLE_REPONSE: Constantes.SECURITE_ACCES_PERMIS
            }

        return reponse

    def generer_certificat_connecteur(self, idmg_tiers, csr) -> EnveloppeCleCert:
        # Trouver generateur pour le role
        renouvelleur = self.renouvelleur_certificat
        certificat = renouvelleur.signer_connecteur_tiers(idmg_tiers, csr)
        clecert = EnveloppeCleCert(cert=certificat)

        return clecert

    def transmettre_cle_racine(self, properties, message_dict: dict):
        self._logger.debug("Preparation transmission de la cle Racine, requete : %s" % str(message_dict))

        # Verifier que le demandeur a l'autorisation de se faire transmettre la cle racine
        en_tete = message_dict[Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE]
        fingerprint_demandeur = en_tete[Constantes.TRANSACTION_MESSAGE_LIBELLE_CERTIFICAT]
        certificat_demandeur = self._contexte.verificateur_certificats.charger_certificat(fingerprint=fingerprint_demandeur)
        exchanges_certificat = certificat_demandeur.get_exchanges
        roles_certificat = certificat_demandeur.get_roles

        exchanges_acceptes = [ConstantesSecurite.EXCHANGE_PROTEGE, ConstantesSecurite.EXCHANGE_SECURE]
        roles_acceptes = [
            ConstantesGenerateurCertificat.ROLE_MAITREDESCLES,
            ConstantesGenerateurCertificat.ROLE_COUPDOEIL_NAVIGATEUR,
            ConstantesGenerateurCertificat.ROLE_COUPDOEIL
        ]
        if not any(exchange in exchanges_acceptes for exchange in exchanges_certificat):
            raise Exception("Certificat %s non autorise a recevoir cle racine (exchange)" % fingerprint_demandeur)
        if not any(exchange in roles_acceptes for exchange in roles_certificat):
            raise Exception("Certificat %s non autorise a recevoir cle racine (role)" % fingerprint_demandeur)

        with open(self.configuration.pki_cafile, 'r') as fichier:
            fichier_cert_racine = fichier.read()

        with open(self.configuration.pki_keymillegrille, 'rb') as fichier:
            fichier_key_racine = fichier.read()

        with open(self.configuration.pki_password_millegrille, 'rb') as fichier:
            password_millegrille = fichier.read()

        clecert = EnveloppeCleCert()
        clecert.key_from_pem_bytes(fichier_key_racine, password_millegrille)

        # Dechiffrer le mot de passe demande pour le retour de la cle privee chiffree
        mot_de_passe_chiffre = message_dict['mot_de_passe_chiffre']
        mot_de_passe_dechiffre = self.decrypter_contenu(mot_de_passe_chiffre)
        clecert.password = mot_de_passe_dechiffre
        cle_privee_chiffree = clecert.private_key_bytes

        return {
            'cle_racine': cle_privee_chiffree.decode('utf-8'),
            'cert_racine': fichier_cert_racine,
        }

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

        temps_limite_demande = datetime.datetime.utcnow().timestamp() - 30  # 30 secondes max
        estampille = evenement[Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE][
            Constantes.TRANSACTION_MESSAGE_LIBELLE_ESTAMPILLE]

        if evenement.get('roles_permis'):
            # C'est une demande pour un tiers (e.g. domaine pour consignationfichiers)
            # Le certificat va etre attache, on doit s'assurer que c'est un role permis

            # En premier, s'assurer que l'emetteur est autorise
            enveloppe_certificat = self.verificateur_transaction.verifier(evenement)
            roles = enveloppe_certificat.get_roles
            if 'domaines' in roles:
                cert = evenement.get('_certificat_tiers')
                cert_navi = cert[0]
                cert_inter = cert[1]

                enveloppe_certificat = EnveloppeCertificat(certificat_pem=cert_navi)
                enveloppe_certificat_inter = EnveloppeCertificat(certificat_pem=cert_inter)

                self.verificateur_certificats.charger_certificat(enveloppe=enveloppe_certificat_inter)
                self.verificateur_certificats.charger_certificat(enveloppe=enveloppe_certificat)
                self.verificateur_certificats.verifier_chaine(enveloppe_certificat)

                # Verifier si la validite de la permission de dechiffrage est expiree
                estampille = evenement[Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE][
                    Constantes.TRANSACTION_MESSAGE_LIBELLE_ESTAMPILLE]

                # Verifiser si le role du certificat correspond a celui de la permission
                roles_certificat = enveloppe_certificat.get_roles
                roles_permis = evenement.get('roles_permis')
                if not any([r in roles_permis for r in roles_certificat]):
                    enveloppe_certificat = None  # Acces refuse

                # Par defaut, 30 minutes pour une permission
                duree_permission = evenement.get(ConstantesMaitreDesCles.TRANSACTION_CHAMP_DUREE_PERMISSION) or (30 * 60)
                temps_limite_demande = datetime.datetime.utcnow().timestamp() - duree_permission

            else:
                enveloppe_certificat = None  # Va forcer le refus de la requete

        elif evenement.get('certificat'):
            cert = self.verificateur_certificats.split_chaine_certificats(evenement['certificat'])
            cert_navi = '\n'.join(cert[0].split(';'))
            cert_inter = '\n'.join(cert[1].split(';'))

            enveloppe_certificat = EnveloppeCertificat(certificat_pem=cert_navi)
            enveloppe_certificat_inter = EnveloppeCertificat(certificat_pem=cert_inter)

            self.verificateur_certificats.charger_certificat(enveloppe=enveloppe_certificat_inter)
            self.verificateur_certificats.charger_certificat(enveloppe=enveloppe_certificat)
            self.verificateur_certificats.verifier_chaine(enveloppe_certificat)

            if ConstantesGenerateurCertificat.ROLE_NAVIGATEUR not in enveloppe_certificat.get_roles:
                enveloppe_certificat = None  # Acces refuse

        else:
            enveloppe_certificat = self.verificateur_transaction.verifier(evenement)

            if ConstantesGenerateurCertificat.ROLE_NAVIGATEUR not in enveloppe_certificat.get_roles:
                enveloppe_certificat = None  # Acces refuse

        # Aucune exception lancee, la signature de requete est valide et provient d'un certificat autorise et connu

        # Verifier si on utilise un certificat different pour re-encrypter la cle
        fingerprint_demande = evenement.get('fingerprint')
        if fingerprint_demande is not None:
            self._logger.debug("Re-encryption de la cle secrete avec certificat %s" % fingerprint_demande)
            try:
                enveloppe_certificat = self.verificateur_certificats.charger_certificat(fingerprint=fingerprint_demande)

                # S'assurer que le certificat est d'un type qui permet d'exporter le contenu
                if ConstantesGenerateurCertificat.ROLE_NAVIGATEUR in enveloppe_certificat.get_roles:
                    pass
                else:
                    self._logger.warning("Refus decrryptage cle avec fingerprint %s" % fingerprint_demande)
                    enveloppe_certificat = None
            except CertificatInconnu:
                enveloppe_certificat = None

        reponse = {Constantes.SECURITE_LIBELLE_REPONSE: Constantes.SECURITE_ACCES_REFUSE}

        if enveloppe_certificat is None:
            pass  # Pas de cert, Acces refuse
        elif not enveloppe_certificat.est_verifie:
            pass  # Cert invalide, access refuse
        elif temps_limite_demande > estampille:
            pass  # Vieille demande, on la rejette
        else:

            self._logger.debug(
                "Verification signature requete cle grosfichier. Cert: %s" % str(
                    enveloppe_certificat.fingerprint_ascii))
            acces_permis = True  # Pour l'instant, les noeuds peuvent tout le temps obtenir l'acces a 4.secure.

            collection_documents = self.document_dao.get_collection(ConstantesMaitreDesCles.COLLECTION_DOCUMENTS_NOM)
            filtre = {
                Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_GROSFICHIERS,
                ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: {
                    'fuuid': evenement['fuuid'],
                }
            }
            document = collection_documents.find_one(filtre)
            # Note: si le document n'est pas trouve, on repond acces refuse (obfuscation)
            if document is not None:
                self._logger.debug("Document de cles pour grosfichiers: %s" % str(document))
                if acces_permis:
                    cle_secrete = self.decrypter_cle(document['cles'])
                    try:
                        cle_secrete_reencryptee, fingerprint = self.crypter_cle(
                            cle_secrete, enveloppe_certificat.certificat)
                        reponse = {
                            'cle': b64encode(cle_secrete_reencryptee).decode('utf-8'),
                            'iv': document['iv'],
                            Constantes.SECURITE_LIBELLE_REPONSE: Constantes.SECURITE_ACCES_PERMIS
                        }
                    except TypeError:
                        self._logger.exception("Document fuuid %s non dechiffrable" % evenement['fuuid'])
                        reponse = {
                            Constantes.SECURITE_LIBELLE_REPONSE: Constantes.SECURITE_ACCES_ERREUR
                        }

        self.generateur_transactions.transmettre_reponse(
            reponse, properties.reply_to, properties.correlation_id
        )

    def transmettre_cle_document(self, evenement, properties):
        """
        Verifie si la requete de cle est valide, puis transmet une reponse (cle re-encryptee ou acces refuse)
        :param evenement:
        :param properties:
        :return:
        """
        self._logger.debug("Transmettre cle document a %s" % properties.reply_to)

        # Verifier que la signature de la requete est valide - c'est fort probable, il n'est pas possible de
        # se connecter a MQ sans un certificat verifie. Mais s'assurer qu'il n'y ait pas de "relais" via un
        # messager qui a acces aux noeuds. La signature de la requete permet de faire cette verification.
        certificat_demandeur = self.verificateur_transaction.verifier(evenement)
        enveloppe_certificat = certificat_demandeur
        # Aucune exception lancee, la signature de requete est valide et provient d'un certificat autorise et connu

        fingerprint_demande = evenement.get('fingerprint')
        if fingerprint_demande is not None:
            self._logger.debug("Re-encryption de la cle secrete avec certificat %s" % fingerprint_demande)
            try:
                enveloppe_certificat = self.verificateur_certificats.charger_certificat(fingerprint=fingerprint_demande)

                # S'assurer que le certificat est d'un type qui permet d'exporter le contenu
                if ConstantesGenerateurCertificat.ROLE_COUPDOEIL_NAVIGATEUR in enveloppe_certificat.get_roles:
                    pass
                elif ConstantesGenerateurCertificat.ROLE_DOMAINES in certificat_demandeur.get_roles:
                    # Le middleware a le droit de demander une cle pour un autre composant
                    pass
                else:
                    self._logger.warning("Refus decrryptage cle avec fingerprint %s" % fingerprint_demande)
                    enveloppe_certificat = None
            except CertificatInconnu:
                enveloppe_certificat = None

        reponse = {Constantes.SECURITE_LIBELLE_REPONSE: Constantes.SECURITE_ACCES_REFUSE}
        acces_permis = enveloppe_certificat is not None
        self._logger.debug(
            "Verification signature requete cle document. Cert: %s" % str(enveloppe_certificat.fingerprint_ascii))

        collection_documents = self.document_dao.get_collection(ConstantesMaitreDesCles.COLLECTION_DOCUMENTS_NOM)
        filtre = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_DOCUMENT,
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: evenement[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS]
        }
        document = collection_documents.find_one(filtre)
        # Note: si le document n'est pas trouve, on repond acces refuse (obfuscation)
        if document is not None:
            self._logger.debug("Document de cles pour grosfichiers: %s" % str(document))
            if acces_permis:
                cle_secrete = self.decrypter_cle(document['cles'])
                cle_secrete_reencryptee, fingerprint = self.crypter_cle(
                    cle_secrete, enveloppe_certificat.certificat)
                reponse = {
                    'cle': b64encode(cle_secrete_reencryptee).decode('utf-8'),
                    'iv': document['iv'],
                    Constantes.SECURITE_LIBELLE_REPONSE: Constantes.SECURITE_ACCES_PERMIS
                }

        self.generateur_transactions.transmettre_reponse(
            reponse, properties.reply_to, properties.correlation_id
        )

    def transmettre_trousseau_hebergement(self, evenement: dict, properties):
        """
        Charge et transmet le trousseau de cle-cert de millegrilles hebergees, avec mot de passe chiffre.
        :param evenement:
        :param properties:
        :return:
        """
        fingerprint = evenement[Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE][Constantes.TRANSACTION_MESSAGE_LIBELLE_CERTIFICAT]
        certificat_destinataire: EnveloppeCertificat = self._contexte.verificateur_certificats.charger_certificat(fingerprint=fingerprint)
        certificat = certificat_destinataire.certificat

        # Identifier le role a extraire des trousseaux / mots de passe
        roles = certificat_destinataire.get_roles
        # role = 'transaction'
        # role = roles[0]

        roles = [role.replace('heb_', '') for role in roles if role.startswith('heb_')]
        if len(roles) == 1:
            role = roles[0]
        else:
            raise ValueError("Plusieurs roles d'hebergement trouve : %s" % roles)

        if role == ConstantesGenerateurCertificat.ROLE_MAITREDESCLES:
            # Ajouter le mot de passe et cle intermediaire
            roles.append('intermediaire')

        collection = self.document_dao.get_collection(ConstantesMaitreDesCles.COLLECTION_DOCUMENTS_NOM)
        liste_idmg = evenement['idmg']

        # Charger mots de passe, rechiffrer pour destination
        filtre_motsdepasses = {
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS + '.idmg': {'$in': liste_idmg},
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS + '.role': {'$in': roles},
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesMaitreDesCles.DOCUMENT_LIBVAL_MOTDEPASSE,
        }
        curseur_motsdepasse = collection.find(filtre_motsdepasses)
        dict_motsdepasse_paridmg = dict()
        dict_motsdepasse_intermediaire_paridmg = dict()
        for motdepasse_info in curseur_motsdepasse:
            idmg = motdepasse_info[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS]['idmg']
            role_motdepasse = motdepasse_info[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS]['role']
            motdepasse_dechiffre = self.decrypter_motdepasse(motdepasse_info['motdepasse'])
            motdepasse_chiffre, fingerprint = self.crypter_cle(motdepasse_dechiffre, cert=certificat)

            if role_motdepasse == 'intermediaire':
                dict_motsdepasse_intermediaire_paridmg[idmg] = str(b64encode(motdepasse_chiffre), 'utf-8')
            else:
                dict_motsdepasse_paridmg[idmg] = str(b64encode(motdepasse_chiffre), 'utf-8')

        filtre = {
            'identificateurs_document.idmg': {'$in': liste_idmg},
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesMaitreDesCles.DOCUMENT_LIBVAL_HEBERGEMENT_TROUSSEAU,
        }
        curseur_trousseaux = collection.find(filtre)

        resultats = []
        for doc in curseur_trousseaux:
            # Charger trousseaux
            idmg = doc['idmg']
            info_millegrille = {
                'idmg': idmg,
                'certificats': {
                    'millegrille': doc['millegrille'][ConstantesSecurityPki.LIBELLE_CERTIFICAT_PEM],
                    'intermediaire': doc['intermediaire'][ConstantesSecurityPki.LIBELLE_CERTIFICAT_PEM],
                    ConstantesMaitreDesCles.TRANSACTION_CHAMP_HEBERGEMENT:
                        doc[ConstantesMaitreDesCles.TRANSACTION_CHAMP_HEBERGEMENT][
                            ConstantesSecurityPki.LIBELLE_CERTIFICAT_PEM],
                    ConstantesMaitreDesCles.TRANSACTION_CHAMP_HOTE_PEM:
                        doc[ConstantesMaitreDesCles.TRANSACTION_CHAMP_HEBERGEMENT][
                            ConstantesMaitreDesCles.TRANSACTION_CHAMP_HOTE_PEM],
                },
                'motdepasse_chiffre': dict_motsdepasse_paridmg[idmg],
            }
            info_millegrille.update(doc[role])

            motdepasse_intermediaire = dict_motsdepasse_intermediaire_paridmg.get(idmg)
            if motdepasse_intermediaire:
                info_millegrille['intermediaire_passwd'] = motdepasse_intermediaire
                info_millegrille['intermediaire_cle'] = doc['intermediaire']['cle']

            resultats.append(info_millegrille)

        reponse = {
            'resultats': resultats
        }
        self.generateur_transactions.transmettre_reponse(
            reponse, properties.reply_to, properties.correlation_id
        )

    def signer_cle_backup(self, properties, message_dict):
        self._logger.debug("Signer cle de backup : %s" % str(message_dict))

        # Verifier que le demandeur a l'autorisation de se faire transmettre la cle racine
        en_tete = message_dict[Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE]
        fingerprint_demandeur = en_tete[Constantes.TRANSACTION_MESSAGE_LIBELLE_CERTIFICAT]
        certificat_demandeur = self._contexte.verificateur_certificats.charger_certificat(fingerprint=fingerprint_demandeur)
        exchanges_certificat = certificat_demandeur.get_exchanges
        roles_certificat = certificat_demandeur.get_roles

        exchanges_acceptes = [ConstantesSecurite.EXCHANGE_PROTEGE, ConstantesSecurite.EXCHANGE_SECURE]
        roles_acceptes = [
            ConstantesGenerateurCertificat.ROLE_MAITREDESCLES,
            ConstantesGenerateurCertificat.ROLE_COUPDOEIL_NAVIGATEUR,
            ConstantesGenerateurCertificat.ROLE_COUPDOEIL
        ]
        if not any(exchange in exchanges_acceptes for exchange in exchanges_certificat):
            raise Exception("Certificat %s non autorise a recevoir cle racine (exchange)" % fingerprint_demandeur)
        if not any(exchange in roles_acceptes for exchange in roles_certificat):
            raise Exception("Certificat %s non autorise a recevoir cle racine (role)" % fingerprint_demandeur)

        public_key_str = message_dict['cle_publique']
        if 'BEGIN PUBLIC KEY' not in public_key_str:
            public_key_str = PemHelpers.wrap_public_key(public_key_str)
        sujet = 'Backup'

        # Trouver generateur pour le role
        renouvelleur = self.renouvelleur_certificat
        clecert = renouvelleur.signer_backup(public_key_str, sujet)

        # Generer nouvelle transaction pour sauvegarder le certificat
        transaction = {
            ConstantesPki.LIBELLE_CERTIFICAT_PEM: clecert.cert_bytes.decode('utf-8'),
            ConstantesPki.LIBELLE_FINGERPRINT: clecert.fingerprint,
            ConstantesPki.LIBELLE_SUBJECT: clecert.formatter_subject(),
            ConstantesPki.LIBELLE_NOT_VALID_BEFORE: int(clecert.not_valid_before.timestamp()),
            ConstantesPki.LIBELLE_NOT_VALID_AFTER: int(clecert.not_valid_after.timestamp()),
            ConstantesPki.LIBELLE_SUBJECT_KEY: clecert.skid,
            ConstantesPki.LIBELLE_AUTHORITY_KEY: clecert.akid,
            ConstantesPki.LIBELLE_ROLES: clecert.get_roles
        }

        self.generateur_transactions.soumettre_transaction(
            transaction,
            ConstantesPki.TRANSACTION_DOMAINE_NOUVEAU_CERTIFICAT
        )

        # Ajouter certificat a la liste des certs de backup
        enveloppe = EnveloppeCertificat(certificat_pem=clecert.cert_bytes)
        fingerprint_backup = EnveloppeCertificat.calculer_fingerprint_b64(enveloppe.certificat)
        self.__certificats_backup[fingerprint_backup] = enveloppe

        # Rechiffrer toutes les cles avec ce nouveau certificat de backup
        processus = "millegrilles_domaines_MaitreDesCles:ProcessusTrouverClesBackupManquantes"
        fingerprints_backup = {'fingerprints_base64': list(self.__certificats_backup.keys())}
        self.demarrer_processus(processus, fingerprints_backup)

        # Creer une reponse pour coupdoeil
        info_cert = transaction.copy()
        del info_cert[ConstantesPki.LIBELLE_CERTIFICAT_PEM]

        return {
            'certificat_info': info_cert,
            'cert': clecert.cert_bytes.decode('utf-8'),
            'fullchain': clecert.chaine,
        }

    def restaurer_backup_cles(self, properties, message_dict):
        """
        Rechiffrer les cles secretes avec la cle de maitre des cles. Utilise une cle privee de backup.
        :param properties:
        :param message_dict:
        :return:
        """
        self._logger.debug("Restaurer cles a partir de backup : %s" % str(message_dict))

        # Extraire la liste de cles qui n'ont pas tous ces certificats
        filtre = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: {'$in': [
                ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_GROSFICHIERS,
                ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_DOCUMENT,
            ]},
            # 'cles.%s' % fingerprint_maitredescles_b64: {'$exists': False},
        }

        collection_documents = self.document_dao.get_collection(ConstantesMaitreDesCles.COLLECTION_DOCUMENTS_NOM)
        curseur = collection_documents.find(filtre)

        mot_de_passe_chiffre = message_dict['mot_de_passe_chiffre']
        try:
            mot_de_passe_dechiffre = self.decrypter_contenu(mot_de_passe_chiffre.encode('utf-8'))
        except ValueError as ve:
            self._logger.error("Erreur dechiffrage, mot de passe non dechiffrable")
            raise ve
        # self._logger.debug("Mot de passe dechiffre : %s" % mot_de_passe_dechiffre)

        clecert_backup = EnveloppeCleCert()
        clecert_backup.key_from_pem_bytes(message_dict['cle_privee'].encode('utf-8'), mot_de_passe_dechiffre)
        fingerprint_backup = message_dict.get('fingerprint_base64')

        # Le fingerprint est optionnel. Si seule la cle privee est transmise, on va trouver quel certificat
        # correspond lors du dechiffrage.
        if fingerprint_backup:
            clecert_backup.fingerprint_b64 = fingerprint_backup

        for doc in curseur:
            self._logger.debug("Rechiffrage cle pour maitre des cles : %s" % str(doc))
            secret_backup_dechiffre = None
            if fingerprint_backup:
                secret_backup = doc[ConstantesMaitreDesCles.TRANSACTION_CHAMP_CLES].get(clecert_backup.fingerprint_b64)
                try:
                    secret_backup_dechiffre = clecert_backup.dechiffrage_asymmetrique(secret_backup)
                except TypeError:
                    self._logger.exception("Erreur extraction secret, document non rechiffrable: %s" %
                                           doc.get(ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS))
            else:
                # Le fingerprint de la cle n'a pas ete fourni. On va parcourir toutes les cles
                # pour tenter de trouver une cle qui fonctionne avec notre cle de backup.
                for fingerprint_public, secret_backup in doc[ConstantesMaitreDesCles.TRANSACTION_CHAMP_CLES].items():
                    try:
                        secret_backup_dechiffre = clecert_backup.dechiffrage_asymmetrique(secret_backup)

                        # On a un match, fingerprint du certificat de backup trouve, on conserve le fingerprint.
                        fingerprint_backup = fingerprint_public
                        clecert_backup.fingerprint_b64 = fingerprint_public
                        break
                    except ValueError:
                        # Mismatch, essayer prochaine cle secrete chiffree
                        continue

            if not secret_backup_dechiffre:
                raise ValueError("Le cle de backup ne correspond a aucun certificat utilise")

            # self._logger.debug("Cle document dechiffree : %s" % str(secret_backup_dechiffre))
            secret_backup_rechiffre, fingerprint_maitredescles_b64 = self.crypter_cle(secret_backup_dechiffre)
            secret_backup_rechiffre = str(b64encode(secret_backup_rechiffre), 'utf-8')
            self._logger.debug("Cle document rechiffree : %s" % str(secret_backup_rechiffre))

            # Soumettre transaction pour la nouvelle cle chiffree
            self.creer_transaction_cles_manquantes(doc, clecert_backup)

        return {'ok': True}

    def signer_csr(self, properties, message_dict):
        """
        Signer des requetes (CSR) et retourner les certificats
        :param properties:
        :param message_dict:
        :return:
        """
        # Verifier si le demandeur est autorise
        enveloppe_cert = self.verificateur_transaction.verifier(message_dict)
        roles_permis = [
            ConstantesGenerateurCertificat.ROLE_MONITOR_DEPENDANT,
            ConstantesGenerateurCertificat.ROLE_MAITREDESCLES,
            ConstantesGenerateurCertificat.ROLE_WEB_PROTEGE,
        ]
        roles_cert = enveloppe_cert.get_roles
        if enveloppe_cert.subject_organization_name == self.configuration.idmg and \
            any([role in roles_cert] for role in roles_permis):

            # Generer certificats
            pems = list()
            chaines = list()
            for pem in message_dict['liste_csr']:
                clecert = self.__renouvelleur_certificat.signer_csr(pem.encode('utf-8'), role=message_dict.get('role'))
                pems.append(str(clecert.cert_bytes, 'utf-8'))

                chaine = {
                    'pems': clecert.chaine
                }
                chaines.append(chaine)

                # Soumettre transaction du nouveau certificat
                self.soumettre_transaction_certificat(clecert)

            # Transmettre certificats en reponse
            reponse = {
                'certificats_pem': pems,
                'chaines': chaines,
            }
            return reponse
            # self.generateur_transactions.transmettre_reponse(
            #     reponse, replying_to=properties.reply_to, correlation_id=properties.correlation_id)
        else:
            raise Exception("Certificat non autorise pour signature de CSR : %s" % str(roles_cert))

    def signer_csr_navigateur(self, properties, message_dict):
        """
        Signer des requetes (CSR) et retourner les certificats
        :param properties:
        :param message_dict:
        :return:
        """
        # Verifier si le demandeur est autorise
        enveloppe_cert = self.verificateur_transaction.verifier(message_dict)
        roles_permis = [
            ConstantesGenerateurCertificat.ROLE_WEB_PROTEGE,
            ConstantesGenerateurCertificat.ROLE_DOMAINES,
        ]
        roles_cert = enveloppe_cert.get_roles
        if enveloppe_cert.subject_organization_name == self.configuration.idmg and \
            any(any([role in roles_cert]) for role in roles_permis):
            pass
        else:
            raise Exception("Role non permis pour signer un certificat de navigateur : %s" % str(roles_cert))

        # Generer certificats
        pem_csr = message_dict['csr']

        niveau_securite = Constantes.SECURITE_PRIVE
        est_proprietaire = message_dict.get('estProprietaire')
        if est_proprietaire:
            niveau_securite = Constantes.SECURITE_PROTEGE

        clecert = self.__renouvelleur_certificat.signer_navigateur(
            pem_csr.encode('utf-8'),
            securite=niveau_securite,
            est_proprietaire=est_proprietaire
        )
        chaine = clecert.chaine

        # Soumettre transaction du nouveau certificat
        self.soumettre_transaction_certificat(clecert)

        # Transmettre certificats en reponse
        pem_cert = clecert.cert_bytes.decode('utf-8')

        reponse = {
            'certificat_pem': pem_cert,
            'chaine': chaine,
        }
        return reponse

    def sauvegarder_trousseau_hebergement(self, transaction):
        """
        Conserve le trousseau (certs, cles) dans un document d'hebergement
        :param transaction:
        :return:
        """
        idmg = transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_IDMG]

        set_ops = {
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_MILLEGRILLE: transaction[
                ConstantesMaitreDesCles.TRANSACTION_CHAMP_MILLEGRILLE],
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_INTERMEDIAIRE: transaction[
                ConstantesMaitreDesCles.TRANSACTION_CHAMP_INTERMEDIAIRE],
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_HEBERGEMENT: transaction[
                ConstantesMaitreDesCles.TRANSACTION_CHAMP_HEBERGEMENT],
        }
        contenu_on_insert = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesMaitreDesCles.DOCUMENT_LIBVAL_HEBERGEMENT_TROUSSEAU,
            Constantes.DOCUMENT_INFODOC_DATE_CREATION: datetime.datetime.utcnow(),
            Constantes.DOCUMENT_INFODOC_SECURITE: Constantes.SECURITE_SECURE,
            Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE: Constantes.ConstantesHebergement.DOMAINE_NOM,
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: {
                Constantes.TRANSACTION_MESSAGE_LIBELLE_IDMG: idmg
            }
        }
        ops = {
            '$set': set_ops,
            '$currentDate': {Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True},
            '$setOnInsert': contenu_on_insert,
        }

        filtre = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesMaitreDesCles.DOCUMENT_LIBVAL_HEBERGEMENT_TROUSSEAU,
            Constantes.TRANSACTION_MESSAGE_LIBELLE_IDMG: idmg,
        }

        collection = self.document_dao.get_collection(ConstantesMaitreDesCles.COLLECTION_DOCUMENTS_NOM)
        collection.update_one(filtre, ops, upsert=True)

    def maj_trousseau_hebergement(self, idmg, cles):
        """
        Conserve le trousseau (certs, cles) dans un document d'hebergement
        :param idmg:
        :param cles:
        :return:
        """
        set_ops = cles
        ops = {
            '$set': set_ops,
            '$currentDate': {Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: True},
        }

        filtre = {
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS + '.' + Constantes.TRANSACTION_MESSAGE_LIBELLE_IDMG: idmg,
            Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE: Constantes.ConstantesHebergement.DOMAINE_NOM,
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesMaitreDesCles.DOCUMENT_LIBVAL_HEBERGEMENT_TROUSSEAU,
        }

        collection = self.document_dao.get_collection(ConstantesMaitreDesCles.COLLECTION_DOCUMENTS_NOM)
        collection.update_one(filtre, ops)

    def supprimer_trousseau_hebergement(self, idmg):
        """
        Supprimer le trousseau d'une MilleGrille hebergee
        :param idmg:
        :param cles:
        :return:
        """
        filtre = {
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS + '.' + Constantes.TRANSACTION_MESSAGE_LIBELLE_IDMG: idmg,
            Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE: Constantes.ConstantesHebergement.DOMAINE_NOM,
            Constantes.DOCUMENT_INFODOC_LIBELLE: {'$in': [
                ConstantesMaitreDesCles.DOCUMENT_LIBVAL_HEBERGEMENT_TROUSSEAU,
                ConstantesMaitreDesCles.DOCUMENT_LIBVAL_MOTDEPASSE,
            ]}
        }

        collection = self.document_dao.get_collection(ConstantesMaitreDesCles.COLLECTION_DOCUMENTS_NOM)
        collection.delete_many(filtre)

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

    def get_handler_requetes(self) -> dict:
        return self.__handler_requetes

    def get_handler_commandes(self) -> dict:
        return self.__handler_commandes

    @property
    def get_certificat(self):
        return self._contexte.signateur_transactions.enveloppe_certificat_courant.certificat

    @property
    def get_certificat_pem(self):
        return self._contexte.signateur_transactions.enveloppe_certificat_courant.certificat_pem

    @property
    def get_intermediaires_pem(self):
        return self.__certificat_intermediaires_pem

    @property
    def get_ca_pem(self):
        return self.__ca_file_pem

    @property
    def get_certificats_backup(self):
        return self.__certificats_backup

    def traiter_cedule(self, evenement):
        super().traiter_cedule(evenement)

    @property
    def version_domaine(self):
        return ConstantesMaitreDesCles.TRANSACTION_VERSION_COURANTE

    @property
    def renouvelleur_certificat(self) -> RenouvelleurCertificat:
        return self.__renouvelleur_certificat

    def creer_transaction_cles_manquantes(self, document, clecert_dechiffrage: EnveloppeCleCert = None):
        """
        Methode qui va dechiffrer une cle secrete et la rechiffrer pour chaque cle backup/maitre des cles manquant.

        :param clecert_dechiffrage: Clecert qui peut dechiffrer toutes les cles chiffrees.
        :param document: Document avec des cles chiffrees manquantes.
        :return:
        """

        # Extraire cle secrete en utilisant le certificat du maitre des cles courant
        try:

            if clecert_dechiffrage:
                fingerprint_cert_dechiffrage = clecert_dechiffrage.fingerprint_b64
                cle_chiffree = document[ConstantesMaitreDesCles.TRANSACTION_CHAMP_MOTDEPASSE][
                    fingerprint_cert_dechiffrage]
                cle_dechiffree = clecert_dechiffrage.dechiffrage_asymmetrique(cle_chiffree)
            else:
                # Par defaut, utiliser clecert du maitredescles
                cle_dechiffree = self.decrypter_motdepasse(document)

        except KeyError:
            self._logger.exception("Cle du document non-rechiffrable (%s), cle secrete associe au cert introuvable" %
                                   document.get(ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS))
            return

        # Recuperer liste des certs a inclure
        enveloppe_maitredescles = self._contexte.signateur_transactions.enveloppe_certificat_courant
        clecert_maitredescles = EnveloppeCleCert(cert=enveloppe_maitredescles.certificat)
        dict_certs = self.get_certificats_backup.copy()
        dict_certs[clecert_maitredescles.fingerprint_b64] = clecert_maitredescles
        cles_connues = list(dict_certs.keys())
        cles_documents = list(document[ConstantesMaitreDesCles.TRANSACTION_CHAMP_CLES].keys())

        # Parcourir
        for fingerprint in cles_connues:
            if fingerprint not in cles_documents:
                identificateur_document = document[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS]

                self._logger.debug("Ajouter cle %s dans document %s" % (
                    fingerprint, identificateur_document))
                enveloppe_backup = dict_certs[fingerprint]
                fingerprint_backup_b64 = enveloppe_backup.fingerprint_b64

                try:
                    # Type EnveloppeCertificat
                    certificat = enveloppe_backup.certificat
                except AttributeError:
                    # Type EnveloppeCleCert
                    certificat = enveloppe_backup.cert

                cle_chiffree_backup, fingerprint_hex = self.crypter_cle(cle_dechiffree, cert=certificat)
                cle_chiffree_backup_base64 = str(b64encode(cle_chiffree_backup), 'utf-8')
                self._logger.debug("Cle chiffree pour cert %s : %s" % (fingerprint_backup_b64, cle_chiffree_backup_base64))

                transaction = {
                    ConstantesMaitreDesCles.TRANSACTION_CHAMP_SUJET_CLE: document[Constantes.DOCUMENT_INFODOC_LIBELLE],
                    ConstantesMaitreDesCles.TRANSACTION_CHAMP_CLES: {
                        fingerprint_backup_b64: cle_chiffree_backup_base64
                    },

                    ConstantesMaitreDesCles.TRANSACTION_CHAMP_DOMAINE: document[ConstantesMaitreDesCles.TRANSACTION_CHAMP_DOMAINE],
                    ConstantesMaitreDesCles.TRANSACTION_CHAMP_IV: document[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IV],
                    ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: identificateur_document,
                    Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID: document[Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID],
                }
                sujet = document.get(ConstantesMaitreDesCles.TRANSACTION_CHAMP_SUJET_CLE)
                if sujet:
                    transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_SUJET_CLE] = sujet

                # Soumettre la transaction immediatement
                # Permet de fonctionner incrementalement si le nombre de cles est tres grand
                self.generateur_transactions.soumettre_transaction(
                    transaction,
                    ConstantesMaitreDesCles.TRANSACTION_MAJ_DOCUMENT_CLES,
                    version=ConstantesMaitreDesCles.TRANSACTION_VERSION_COURANTE,
                )

    def creer_transaction_motsdepasse_manquants(self, document, clecert_dechiffrage: EnveloppeCleCert = None):
        """
        Methode qui va dechiffrer un mot de passe et le rechiffrer pour chaque cle backup/maitre des cles manquant.

        :param clecert_dechiffrage: Clecert qui peut dechiffrer toutes les cles chiffrees.
        :param document: Document avec des cles chiffrees manquantes.
        :return:
        """

        # Extraire cle secrete en utilisant le certificat du maitre des cles courant
        try:

            if clecert_dechiffrage:
                fingerprint_cert_dechiffrage = clecert_dechiffrage.fingerprint_b64
                cle_chiffree = document[ConstantesMaitreDesCles.TRANSACTION_CHAMP_MOTDEPASSE][
                    fingerprint_cert_dechiffrage]
                cle_dechiffree = clecert_dechiffrage.dechiffrage_asymmetrique(cle_chiffree)
            else:
                # Par defaut, utiliser clecert du maitredescles
                cle_dechiffree = self.decrypter_motdepasse(document)

        except KeyError:
            self._logger.exception("Cle du document non-rechiffrable (%s), cle secrete associe au cert introuvable" %
                                   document.get(ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS))
            return

        # Recuperer liste des certs a inclure
        enveloppe_maitredescles = self._contexte.signateur_transactions.enveloppe_certificat_courant
        clecert_maitredescles = EnveloppeCleCert(cert=enveloppe_maitredescles.certificat)

        dict_certs = self.get_certificats_backup.copy()
        dict_certs[clecert_maitredescles.fingerprint_b64] = clecert_maitredescles
        cles_connues = list(dict_certs.keys())
        cles_documents = list(document[ConstantesMaitreDesCles.TRANSACTION_CHAMP_MOTDEPASSE].keys())

        # Parcourir
        for fingerprint in cles_connues:
            if fingerprint not in cles_documents:
                identificateur_document = document[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS]

                self._logger.debug("Ajouter cle %s dans document %s" % (
                    fingerprint, identificateur_document))
                enveloppe_backup = dict_certs[fingerprint]
                fingerprint_backup_b64 = enveloppe_backup.fingerprint_b64

                try:
                    # Type EnveloppeCertificat
                    certificat = enveloppe_backup.certificat
                except AttributeError:
                    # Type EnveloppeCleCert
                    certificat = enveloppe_backup.cert

                cle_chiffree_backup, fingerprint_hex = self.crypter_cle(cle_dechiffree, cert=certificat)
                cle_chiffree_backup_base64 = str(b64encode(cle_chiffree_backup), 'utf-8')
                self._logger.debug("Cle chiffree pour cert %s : %s" % (fingerprint_backup_b64, cle_chiffree_backup_base64))

                transaction = {
                    ConstantesMaitreDesCles.TRANSACTION_CHAMP_SUJET_CLE: document[Constantes.DOCUMENT_INFODOC_LIBELLE],
                    ConstantesMaitreDesCles.TRANSACTION_CHAMP_MOTDEPASSE: {
                        fingerprint_backup_b64: cle_chiffree_backup_base64
                    },

                    ConstantesMaitreDesCles.TRANSACTION_CHAMP_DOMAINE: document[ConstantesMaitreDesCles.TRANSACTION_CHAMP_DOMAINE],
                    ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: identificateur_document,
                    Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID: document[Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID],
                }
                sujet = document.get(ConstantesMaitreDesCles.TRANSACTION_CHAMP_SUJET_CLE)
                if sujet:
                    transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_SUJET_CLE] = sujet

                # Soumettre la transaction immediatement
                # Permet de fonctionner incrementalement si le nombre de cles est tres grand
                self.generateur_transactions.soumettre_transaction(
                    transaction,
                    ConstantesMaitreDesCles.TRANSACTION_MAJ_MOTDEPASSE,
                    version=ConstantesMaitreDesCles.TRANSACTION_VERSION_COURANTE,
                )

    def creer_cles_millegrille_hebergee(self, parametres):
        trousseau_millegrille = self.__renouvelleur_certificat.generer_nouveau_idmg()
        idmg = trousseau_millegrille['idmg']

        # Sauvegarder les certificats et cles de la nouvelle millegrille
        motdepasse_millegrille = trousseau_millegrille[ConstantesMaitreDesCles.TRANSACTION_CHAMP_MILLEGRILLE]['motdepasse']
        motdepasse_intermediaire = trousseau_millegrille[ConstantesMaitreDesCles.TRANSACTION_CHAMP_INTERMEDIAIRE]['motdepasse']
        motdepasse_millegrille_crypte, fingerprint_cert_hex = self.crypter_cle(b64decode(motdepasse_millegrille))
        motdepasse_intermediaire_crypte, fingerprint_cert_hex = self.crypter_cle(b64decode(motdepasse_intermediaire))

        # fingerprint_cert_maitredescles = binascii.unhexlify(fingerprint_cert_hex)
        # fingerprint_maitredescles_b64 = str(b64encode(fingerprint_cert_maitredescles), 'utf-8')

        transactions = {
            'paires': {
                'idmg': idmg,
                'millegrille': {
                    ConstantesSecurityPki.LIBELLE_CERTIFICAT_PEM: trousseau_millegrille['millegrille'][ConstantesSecurityPki.LIBELLE_CERTIFICAT_PEM],
                    'cle': trousseau_millegrille['millegrille']['cle'],
                    # 'motdepasse': str(b64encode(motdepasse_millegrille_crypte), 'utf-8'),
                    'fingerprint': trousseau_millegrille['millegrille']['fingerprint_b64'],
                },
                'intermediaire': {
                    ConstantesSecurityPki.LIBELLE_CERTIFICAT_PEM: trousseau_millegrille['intermediaire'][ConstantesSecurityPki.LIBELLE_CERTIFICAT_PEM],
                    'cle': trousseau_millegrille['intermediaire']['cle'],
                    # 'motdepasse': str(b64encode(motdepasse_intermediaire_crypte), 'utf-8'),
                    'fingerprint': trousseau_millegrille['intermediaire']['fingerprint_b64'],
                },
                'hebergement': trousseau_millegrille['hebergement'],
                'securite': Constantes.SECURITE_SECURE,
            },
            'transaction_cle_millegrille': {
                'domaine': 'millegrilles.domaines.Hebergement',
                ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: {
                    'idmg': idmg,
                    'role': 'millegrille',
                    'fingerprint': trousseau_millegrille['millegrille']['fingerprint_b64'],
                },
                'sujet': 'motdepasse.cleprivee',
                'motdepasse': str(b64encode(motdepasse_millegrille_crypte), 'utf-8'),
                'securite': Constantes.SECURITE_SECURE,
            },
            'transaction_cle_intermediaire': {
                'domaine': 'millegrilles.domaines.Hebergement',
                ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: {
                    'idmg': idmg,
                    'role': 'intermediaire',
                    'fingerprint': trousseau_millegrille['intermediaire']['fingerprint_b64'],
                },
                'sujet': 'motdepasse.cleprivee',
                'motdepasse': str(b64encode(motdepasse_intermediaire_crypte), 'utf-8'),
                'securite': Constantes.SECURITE_SECURE,
            },
        }

        return transactions

    def creer_cles_modules_heberges(self, idmg: str, noms_roles: list):
        collection = self.document_dao.get_collection(ConstantesMaitreDesCles.COLLECTION_DOCUMENTS_NOM)

        filtre_trousseau = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesMaitreDesCles.DOCUMENT_LIBVAL_HEBERGEMENT_TROUSSEAU,
            Constantes.TRANSACTION_MESSAGE_LIBELLE_IDMG: idmg,
        }
        trousseau = collection.find_one(filtre_trousseau)

        info_roles_cles = dict()  # Roles pour lesquels on charge la cle
        fingerprint_intermediaire = None
        clecerts = dict()
        dict_ca = dict()  # Liste de clecert CA par skid, utilise par RenouvelleurCertificats
        for cle, valeur in trousseau.items():
            if isinstance(valeur, dict):
                fingerprint = valeur.get(ConstantesPki.LIBELLE_FINGERPRINT)

                if fingerprint:
                    clecert = EnveloppeCleCert()
                    clecert.cert_from_pem_bytes(valeur[ConstantesPki.LIBELLE_CERTIFICAT_PEM].encode('utf-8'))
                    clecerts[fingerprint] = clecert

                    # Ajouter cert dans la liste des autorites connues
                    dict_ca[clecert.skid] = clecert.cert

                    if cle in ['intermediaire']:  # Role pour lesquels on charge la cle
                        fingerprint = valeur[ConstantesPki.LIBELLE_FINGERPRINT]
                        info_roles_cles[fingerprint] = valeur

                    if cle == 'intermediaire':
                        fingerprint_intermediaire = fingerprint

        filtre_motsdepasse = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: ConstantesMaitreDesCles.DOCUMENT_LIBVAL_MOTDEPASSE,
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS + "." + Constantes.TRANSACTION_MESSAGE_LIBELLE_IDMG: idmg,
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS + "." + ConstantesPki.LIBELLE_FINGERPRINT: {'$in': list(info_roles_cles.keys())},
        }
        curseur_mots_de_passe = collection.find(filtre_motsdepasse)
        for doc_motdepasse in curseur_mots_de_passe:
            fingerprint = doc_motdepasse[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS][ConstantesPki.LIBELLE_FINGERPRINT]
            motdepasse = self.decrypter_motdepasse(doc_motdepasse[ConstantesMaitreDesCles.TRANSACTION_CHAMP_MOTDEPASSE])

            info_role_courant = info_roles_cles[fingerprint]
            key_pem = info_role_courant[ConstantesPki.LIBELLE_CLE].encode('utf-8')

            clecert = clecerts[fingerprint]
            clecert.key_from_pem_bytes(key_pem, motdepasse)

        # Preparer le generateur de certicats. Toujours generer cles privees avec mots de passe.
        clecert_intermediaire = clecerts[fingerprint_intermediaire]
        renouvelleur_certificat_hebergement = RenouvelleurCertificat(
            idmg, dict_ca, clecert_intermediaire=clecert_intermediaire, generer_password=True)

        transaction_trousseau = {
            'idmg': idmg,
            'securite': Constantes.SECURITE_SECURE,
        }
        transactions_motsdepasse = list()
        for role in noms_roles:
            clecert = renouvelleur_certificat_hebergement.renouveller_par_role(role, 'heberge')
            motdepasse_cle_chiffre, fingerprint = self.crypter_cle(b64decode(clecert.password))
            motdepasse_cle_chiffre = str(b64encode(motdepasse_cle_chiffre), 'utf-8')
            fingerprint_b64 = clecert.fingerprint_b64

            transaction_trousseau[role] = {
                ConstantesPki.LIBELLE_CERTIFICAT_PEM: str(clecert.cert_bytes, 'utf-8'),
                ConstantesPki.LIBELLE_CLE: str(clecert.private_key_bytes, 'utf-8'),
                ConstantesPki.LIBELLE_FINGERPRINT: fingerprint_b64,
            }

            transactions_motsdepasse.append({
                'domaine': 'millegrilles.domaines.Hebergement',
                ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: {
                    'idmg': idmg,
                    'role': role,
                    'fingerprint': fingerprint_b64,
                },
                'sujet': 'motdepasse.cleprivee',
                'motdepasse': motdepasse_cle_chiffre,
                'securite': Constantes.SECURITE_SECURE,
            })

        return {
            'trousseau': transaction_trousseau,
            'motsdepasse': transactions_motsdepasse,
        }

    def soumettre_transaction_certificat(self, clecert):
        transaction = {
            ConstantesPki.LIBELLE_CERTIFICAT_PEM: clecert.cert_bytes.decode('utf-8'),
            ConstantesPki.LIBELLE_FINGERPRINT: clecert.fingerprint,
            ConstantesPki.LIBELLE_SUBJECT: clecert.formatter_subject(),
            ConstantesPki.LIBELLE_NOT_VALID_BEFORE: int(clecert.not_valid_before.timestamp()),
            ConstantesPki.LIBELLE_NOT_VALID_AFTER: int(clecert.not_valid_after.timestamp()),
            ConstantesPki.LIBELLE_SUBJECT_KEY: clecert.skid,
            ConstantesPki.LIBELLE_AUTHORITY_KEY: clecert.akid,
        }
        self.generateur_transactions.soumettre_transaction(
            transaction,
            domaine_action=ConstantesPki.TRANSACTION_DOMAINE_NOUVEAU_CERTIFICAT
        )

    def transmettre_certificat(self, properties):
        """
        Transmet le certificat courant du MaitreDesCles au demandeur.
        :param properties:
        :return:
        """
        self._logger.debug("Transmettre certificat a %s" % properties.reply_to)
        # Genere message reponse
        message_resultat = {
            'certificat_millegrille': self.get_ca_pem,
            'certificat': [self.get_certificat_pem, self.get_intermediaires_pem],
            'certificats_backup': self.get_certificats_backup,
        }

        self.generateur_transactions.transmettre_reponse(
            message_resultat, properties.reply_to, properties.correlation_id
        )

    def maj_document_cle(self, transaction: dict):
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

        contenu_set = dict()
        cles = transaction.get('cles')
        if cles is None:
            # Mode individuel / backup de cle
            fingerprint = transaction['fingerprint']
            cles = {fingerprint: transaction['cle']}

        for fingerprint in cles.keys():
            cle_dict = 'cles.%s' % fingerprint
            valeur = cles.get(fingerprint)
            contenu_set[cle_dict] = valeur

        if transaction.get(ConstantesMaitreDesCles.DOCUMENT_SECURITE) is not None:
            contenu_set[ConstantesMaitreDesCles.DOCUMENT_SECURITE] = \
                transaction[ConstantesMaitreDesCles.DOCUMENT_SECURITE]
        else:
            # Par defaut, on met le document en mode secure
            contenu_on_insert[ConstantesMaitreDesCles.DOCUMENT_SECURITE] = Constantes.SECURITE_PROTEGE

        operations_mongo = {
            '$set': contenu_set,
            '$currentDate': contenu_date,
            '$setOnInsert': contenu_on_insert,
        }

        collection_documents = self.document_dao.get_collection(ConstantesMaitreDesCles.COLLECTION_DOCUMENTS_NOM)
        self._logger.debug("Operations: %s" % str({'filtre': cles_document, 'operation': operations_mongo}))

        resultat_update = collection_documents.update_one(filter=cles_document, update=operations_mongo, upsert=True)
        self._logger.info("_id du nouveau document MaitreDesCles: %s" % str(resultat_update.upserted_id))
        if resultat_update.upserted_id is None and resultat_update.matched_count != 1:
            raise Exception("Erreur insertion cles")

    @property
    def certificat_millegrille(self) -> EnveloppeCertificat:
        return self.__certificat_millegrille


class ProcessusReceptionCles(MGProcessusTransaction):

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)

    def traitement_regenerer(self, id_transaction, parametres_processus):
        """ Aucun traitement necessaire, le resultat est re-sauvegarde sous une nouvelle transaction """
        pass

    def recrypterCle(self, cle_secrete_encryptee):
        cert_maitredescles = self._controleur.gestionnaire.get_certificat
        fingerprint_certmaitredescles = b64encode(cert_maitredescles.fingerprint(hashes.SHA1())).decode('utf-8')
        cle_symmetrique_chiffree = cle_secrete_encryptee[fingerprint_certmaitredescles]
        cles_secretes_encryptees = cle_secrete_encryptee.copy()

        cle_secrete = self._controleur.gestionnaire.decrypter_contenu(cle_symmetrique_chiffree)
        # self._logger.debug("Cle secrete: %s" % cle_secrete)

        # Re-encrypter la cle secrete avec les cles backup
        if self._controleur.gestionnaire.get_certificats_backup is not None:
            certificats_backup = self.controleur.gestionnaire.get_certificats_backup
            for backup in certificats_backup.values():
                cle_secrete_backup, fingerprint = self.controleur.gestionnaire.crypter_cle(cle_secrete, cert=backup.certificat)
                fingerprint_b64 = b64encode(binascii.unhexlify(fingerprint)).decode('utf-8')
                cles_secretes_encryptees[fingerprint_b64] = b64encode(cle_secrete_backup).decode('utf-8')

        return cles_secretes_encryptees

    def generer_transaction_majcles(self, sujet):

        transaction_nouvellescles = ConstantesMaitreDesCles.DOCUMENT_TRANSACTION_CONSERVER_CLES.copy()
        transaction_nouvellescles[ConstantesMaitreDesCles.TRANSACTION_CHAMP_SUJET_CLE] = sujet
        transaction_nouvellescles[ConstantesMaitreDesCles.TRANSACTION_CHAMP_CLES] = \
            self.parametres['cles_secretes_encryptees']
        transaction_nouvellescles['iv'] = self.parametres['iv']

        # Copier les champs d'identification de ce document
        transaction_nouvellescles[Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE] = \
            self.parametres[Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE]
        transaction_nouvellescles[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS] = \
            self.parametres[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS]

        self.ajouter_transaction_a_soumettre(ConstantesMaitreDesCles.TRANSACTION_MAJ_DOCUMENT_CLES, transaction_nouvellescles)

        # # La transaction va mettre a jour (ou creer) les cles pour
        # generateur_transaction.soumettre_transaction(
        #     transaction_nouvellescles,
        #     ConstantesMaitreDesCles.TRANSACTION_MAJ_DOCUMENT_CLES,
        #     version=ConstantesMaitreDesCles.TRANSACTION_VERSION_COURANTE
        # )

    def generer_transactions_backup(self, sujet):
        """
        Genere les transaction manquantes pour cle de millegrille ou cles de backup
        Remplace le domaine MaitreDesCles.* par MaitreDesCles.FINGERPRINTB64.*
        :param sujet:
        :return:
        """
        transaction = self.transaction
        domaine_action = transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE][Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE]
        action = domaine_action.split('.')[-1]

        cert_millegrille = self.controleur.gestionnaire.certificat_millegrille
        fingerprint_cert_millegrille = cert_millegrille.fingerprint_b64

        fingerprint_backup = [fingerprint_cert_millegrille]
        if self._controleur.gestionnaire.get_certificats_backup is not None:
            certificats_backup = self.controleur.gestionnaire.get_certificats_backup
            for fingerprint_cle_backup in certificats_backup.keys():
                fingerprint_backup.append(fingerprint_cle_backup)

        for fingerprint, cle in self.parametres['cles_secretes_encryptees'].items():
            if fingerprint not in fingerprint_backup:
                continue

            sous_domaine = '.'.join([ConstantesMaitreDesCles.DOMAINE_NOM, fingerprint, action + 'Backup'])
            transaction_cle = {
                'domaine': transaction['domaine'],
                'identificateurs_document': transaction['identificateurs_document'],
                'fingerprint': fingerprint,
                'cle': cle,
                'iv': transaction['iv'],
                'sujet': sujet,
            }
            self.ajouter_transaction_a_soumettre(sous_domaine, transaction_cle)

    def generer_transaction_maj_motdepasse(self, sujet, information):
        """
        Genere une transaction pour sauvegarder le mot de passe avec toutes les cles connues.

        :param sujet:
        :param information:
        :return: uuid-transaction de la transaction soumise
        """
        generateur_transaction = self.generateur_transactions

        transaction_nouvellescles = ConstantesMaitreDesCles.DOCUMENT_TRANSACTION_CONSERVER_CLES.copy()
        transaction_nouvellescles[ConstantesMaitreDesCles.TRANSACTION_CHAMP_SUJET_CLE] = sujet
        transaction_nouvellescles[ConstantesMaitreDesCles.TRANSACTION_CHAMP_MOTDEPASSE] = \
            information['motdepasse_chiffre']

        # Copier les champs d'identification de ce document
        transaction_nouvellescles[Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE] = \
            information[Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE]
        transaction_nouvellescles[Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID] = \
            information[Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID]
        transaction_nouvellescles[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS] = \
            information[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS]

        if information.get('synchroniser'):
            transaction_nouvellescles['synchroniser'] = True

        # La transaction va mettre a jour (ou creer) les mots de passe
        uuid_transaction = generateur_transaction.soumettre_transaction(
            transaction_nouvellescles,
            ConstantesMaitreDesCles.TRANSACTION_MAJ_MOTDEPASSE,
            version=ConstantesMaitreDesCles.TRANSACTION_VERSION_COURANTE
        )

        return uuid_transaction


class ProcessusNouvelleCleGrosFichier(ProcessusReceptionCles):

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    # def traitement_regenerer(self, id_transaction, parametres_processus):
    #     """ Aucun traitement necessaire, le resultat est re-sauvegarde sous une nouvelle transaction """
    #     pass

    def initiale(self):
        transaction = self.transaction

        # Decrypter la cle secrete et la re-encrypter avec toutes les cles backup
        cle_secrete_encryptee = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_CLES]
        cles_secretes_encryptees = self.recrypterCle(cle_secrete_encryptee)
        identificateurs_document = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS]

        nouveaux_params = {
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: identificateurs_document,
            'fuuid': identificateurs_document['fuuid'],
            'cles_secretes_encryptees': cles_secretes_encryptees,
            'iv': transaction['iv'],
        }
        self.parametres.update(nouveaux_params)

        # Verifier si on a des cles differentes
        if all([cle in cle_secrete_encryptee.keys() for cle in cles_secretes_encryptees.keys()]):
            self.controleur.gestionnaire.maj_document_cle(transaction)
        else:
            self.generer_transaction_majcles(ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_GROSFICHIERS)

        # Generer transactions pour separer les sous-domaines de backup
        self.generer_transactions_backup(ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_GROSFICHIERS)

        self.set_etape_suivante()  # Termine

        return nouveaux_params

    def generer_transaction_cles_backup(self):
        """
        Sauvegarder les cles de backup sous forme de transaction dans le domaine MaitreDesCles.
        Va aussi declencher la mise a jour du document de cles associe.
        :return:
        """
        self.generer_transaction_majcles(ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_GROSFICHIERS)


class ProcessusNouvelleCleBackupTransaction(ProcessusReceptionCles):

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def initiale(self):
        transaction = self.transaction

        # Decrypter la cle secrete et la re-encrypter avec toutes les cles backup
        cle_secrete_encryptee = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_CLES]
        cles_secretes_encryptees = self.recrypterCle(cle_secrete_encryptee)
        identificateurs_document = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS]

        nouveaux_params = {
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: identificateurs_document,
            'transactions_nomfichier': identificateurs_document['transactions_nomfichier'],
            'cles_secretes_encryptees': cles_secretes_encryptees,
            'iv': transaction['iv'],
        }
        self.parametres.update(nouveaux_params)

        # Verifier si on a des cles differentes
        if all([cle in cle_secrete_encryptee.keys() for cle in cles_secretes_encryptees.keys()]):
            self.controleur.gestionnaire.maj_document_cle(transaction)
        else:
            self.generer_transaction_majcles(ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_BACKUPTRANSACTIONS)

        # Generer transactions pour separer les sous-domaines de backup
        self.generer_transactions_backup(ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_BACKUPTRANSACTIONS)

        self.set_etape_suivante()  # Termine

        return nouveaux_params

    def generer_transaction_cles_backup(self):
        """
        Sauvegarder les cles de backup sous forme de transaction dans le domaine MaitreDesCles.
        Va aussi declencher la mise a jour du document de cles associe.
        :return:
        """
        self.generer_transaction_majcles(ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_BACKUPTRANSACTIONS)


class ProcessusCleGrosfichierBackup(ProcessusReceptionCles):

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def initiale(self):
        transaction = self.transaction

        # Decrypter la cle secrete et la re-encrypter avec toutes les cles backup
        self.controleur.gestionnaire.maj_document_cle(transaction)

        self.set_etape_suivante()  # Termine


class ProcessusNouvelleCleBackupTransactionBackup(ProcessusReceptionCles):

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def initiale(self):
        transaction = self.transaction

        # Decrypter la cle secrete et la re-encrypter avec toutes les cles backup
        self.controleur.gestionnaire.maj_document_cle(transaction)

        self.set_etape_suivante()  # Termine


class ProcessusNouveauMotDePasse(ProcessusReceptionCles):

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def traitement_regenerer(self, id_transaction, parametres_processus):
        """ Aucun traitement necessaire, le resultat est re-sauvegarde sous une nouvelle transaction """
        pass

    def initiale(self):
        transaction = self.transaction
        uuid_transaction = self.transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE][Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID]

        # Decrypter la cle secrete et la re-encrypter avec toutes les cles backup
        mot_de_passe_chiffre = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_MOTDEPASSE]
        mot_de_passe_rechiffre = self.recrypterCle(mot_de_passe_chiffre)

        domaine = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_DOMAINE]
        identificateurs_document = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS]

        information = {
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: identificateurs_document,
            Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID: uuid_transaction,
            Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE: domaine,
            'motdepasse_chiffre': mot_de_passe_rechiffre,
        }

        etape_resumer = self._etape_resumer()
        if etape_resumer:
            information[ConstantesMaitreDesCles.TRANSACTION_CHAMP_SYNCHRONISER] = True

        uuid_transaction = self.generer_transaction_maj_motdepasse(ConstantesMaitreDesCles.DOCUMENT_LIBVAL_MOTDEPASSE, information)

        if etape_resumer:
            token_resumer = ConstantesMaitreDesCles.TOKEN_SYNCHRONISER + ':' + uuid_transaction
            self.set_etape_suivante(etape_resumer, [token_resumer])
        else:
            self.set_etape_suivante()  # Termine

        return information

    def _etape_resumer(self):
        """
        Si retourne True, le processus a une etape resumer.
        :return: Etape resumer, ou False si non supporte
        """
        return False


class ProcessusMAJDocumentCles(MGProcessusTransaction):

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement, TransactionDocumentMajClesVersionMapper())
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def initiale(self):
        transaction = self.transaction
        self.controleur.gestionnaire.maj_document_cle(transaction)

        self.set_etape_suivante()  # Termine


class ProcessusMAJMotdepasse(MGProcessusTransaction):

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def initiale(self):
        transaction = self.transaction

        # Extraire les cles de document de la transaction (par processus d'elimination)
        filtre_document = {
            Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE:
                transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_DOMAINE],
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS:
                transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS],
        }

        contenu_on_insert = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_SUJET_CLE],
            Constantes.DOCUMENT_INFODOC_DATE_CREATION: datetime.datetime.utcnow(),
        }
        contenu_on_insert.update(filtre_document)

        contenu_date = {
            Constantes.DOCUMENT_INFODOC_DERNIERE_MODIFICATION: {'$type': 'date'},
        }

        contenu_set = {
            Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID: transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID],
        }
        for fingerprint in transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_MOTDEPASSE].keys():
            cle_dict = ConstantesMaitreDesCles.TRANSACTION_CHAMP_MOTDEPASSE + '.' + fingerprint
            valeur = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_MOTDEPASSE].get(fingerprint)
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
        self.__logger.debug("Operations: %s" % str({'filtre': filtre_document, 'operation': operations_mongo}))

        resultat_update = collection_documents.update_one(filter=filtre_document, update=operations_mongo, upsert=True)
        self.__logger.info("_id du nouveau document MaitreDesCles: %s" % str(resultat_update.upserted_id))

        if transaction.get(ConstantesMaitreDesCles.TRANSACTION_CHAMP_SYNCHRONISER):
            uuid_transaction = transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE][Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID]
            token_resumer = ConstantesMaitreDesCles.TOKEN_SYNCHRONISER + ':' + uuid_transaction
            self.resumer_processus([token_resumer])

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
        self.__logger.debug("Cle secrete encryptee: %s" % cle_secrete_encryptee)

        nouveaux_params = {
            'domaine': domaine,
            Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID: uuid_transaction_doc,
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_IDENTIFICATEURS_DOCUMENTS: iddoc,
            'cles_secretes_encryptees': cles_secretes_encryptees,
            'iv': transaction['iv'],
        }
        self.parametres.update(nouveaux_params)

        self.generer_transaction_majcles(ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_DOCUMENT)

        self.set_etape_suivante()  # Terminer

        return nouveaux_params


class ProcessusRenouvellerCertificat(MGProcessusTransaction):

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def traitement_regenerer(self, id_transaction, parametres_processus):
        """ Aucun traitement necessaire, le nouveau cert est re-sauvegarde sous une nouvelle transaction dans PKI """
        pass

    def initiale(self):
        transaction = self.transaction
        role = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_ROLE_CERTIFICAT]
        altdomains = transaction.get(ConstantesPki.CHAMP_ALT_DOMAINS)
        node = transaction['node']

        # Reverifier la signature de la transaction (eviter alteration dans la base de donnees)
        # Extraire certificat et verifier type. Doit etre: maitredescles ou deployeur.
        enveloppe_cert = self._controleur.verificateur_transaction.verifier(transaction)
        roles_cert = enveloppe_cert.get_roles
        if enveloppe_cert.subject_organization_name == self._controleur.configuration.idmg and \
            'deployeur' in roles_cert or 'maitredescles' in roles_cert:
            # Le deployeur et le maitre des cles ont l'autorisation de renouveller n'importe quel certificat
            # Coupdoeil a tous les acces au niveau secure
            self.set_etape_suivante(ProcessusRenouvellerCertificat.generer_cert.__name__)
        else:
            self.set_etape_suivante(ProcessusRenouvellerCertificat.refuser_generation.__name__)
            return {
                'autorise': False,
                'role': role,
                'altdomains': altdomains,
                'description': 'demandeur non autorise a renouveller ce certificat',
                'roles_demandeur': roles_cert
            }

        return {
            'autorise': True,
            'role': role,
            'altdomains': altdomains,
            'roles_demandeur': roles_cert,
            'node': node,
        }

    def generer_cert(self):
        """
        Generer cert et creer nouvelle transaction pour PKI
        :return:
        """
        transaction = self.transaction
        role = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_ROLE_CERTIFICAT]
        node_name = self.parametres['node']
        csr_bytes = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_CSR].encode('utf-8')

        # Trouver generateur pour le role
        generateur = self._controleur.gestionnaire.renouvelleur_certificat
        clecert = generateur.renouveller_avec_csr(role, node_name, csr_bytes)

        # Generer nouvelle transaction pour sauvegarder le certificat
        self.controleur.gestionnaire.soumettre_transaction_certificat(clecert)

        self.set_etape_suivante()  # Termine - va repondre automatiquement au deployeur dans finale()

        return {
            'cert': clecert.cert_bytes.decode('utf-8'),
            'fullchain': clecert.chaine,
        }

    def refuser_generation(self):
        """
        Refuser la creation d'un nouveau certificat.
        :return:
        """
        # Repondre au demandeur avec le refus

        self.set_etape_suivante()  # Termine


class ProcessusSignerCertificatNoeud(MGProcessusTransaction):

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def traitement_regenerer(self, id_transaction, parametres_processus):
        """ Aucun traitement necessaire, le nouveau cert est re-sauvegarde sous une nouvelle transaction dans PKI """
        pass

    def initiale(self):
        transaction = self.transaction
        domaines = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_DOMAINES]

        # Reverifier la signature de la transaction (eviter alteration dans la base de donnees)
        # Extraire certificat et verifier type. Doit etre: maitredescles ou deployeur.
        enveloppe_cert = self._controleur.verificateur_transaction.verifier(transaction)
        roles_cert = enveloppe_cert.get_roles
        if enveloppe_cert.subject_organization_name == self._controleur.configuration.idmg and \
            'coupdoeil' in roles_cert or 'deployeur' in roles_cert:
            # Le coupdoeil a l'autorisation de signer n'importe quel certificat
            self.set_etape_suivante(ProcessusSignerCertificatNoeud.generer_cert.__name__)
        else:
            self.set_etape_suivante(ProcessusSignerCertificatNoeud.refuser_generation.__name__)
            return {
                'autorise': False,
                'domaines': domaines,
                'description': 'demandeur non autorise a signer ce certificat',
                'roles_demandeur': roles_cert
            }

        return {
            'autorise': True,
            'domaines': domaines,
            'roles_demandeur': roles_cert,
        }

    def generer_cert(self):
        """
        Generer cert et creer nouvelle transaction pour PKI
        :return:
        """
        transaction = self.transaction
        domaines = self.parametres['domaines']
        csr_bytes = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_CSR].encode('utf-8')

        # Trouver generateur pour le role
        renouvelleur = self._controleur.gestionnaire.renouvelleur_certificat
        clecert = renouvelleur.signer_noeud(csr_bytes)

        # Generer nouvelle transaction pour sauvegarder le certificat
        transaction = {
            ConstantesPki.LIBELLE_CERTIFICAT_PEM: clecert.cert_bytes.decode('utf-8'),
            ConstantesPki.LIBELLE_FINGERPRINT: clecert.fingerprint,
            ConstantesPki.LIBELLE_SUBJECT: clecert.formatter_subject(),
            ConstantesPki.LIBELLE_NOT_VALID_BEFORE: int(clecert.not_valid_before.timestamp()),
            ConstantesPki.LIBELLE_NOT_VALID_AFTER: int(clecert.not_valid_after.timestamp()),
            ConstantesPki.LIBELLE_SUBJECT_KEY: clecert.skid,
            ConstantesPki.LIBELLE_AUTHORITY_KEY: clecert.akid,
        }
        self._controleur.generateur_transactions.soumettre_transaction(
            transaction,
            ConstantesPki.TRANSACTION_DOMAINE_NOUVEAU_CERTIFICAT
        )

        # Creer une commande pour que le monitor genere le compte sur RabbitMQ
        commande_creation_compte = {
            ConstantesPki.LIBELLE_CERTIFICAT_PEM: clecert.cert_bytes.decode('utf-8'),
        }
        self._controleur.generateur_transactions.transmettre_commande(
            commande_creation_compte,
            'commande.' + Constantes.ConstantesServiceMonitor.COMMANDE_AJOUTER_COMPTE
        )

        self.set_etape_suivante()  # Termine - va repondre automatiquement au deployeur dans finale()

        return {
            'cert': clecert.cert_bytes.decode('utf-8'),
            'fullchain': clecert.chaine,
        }

    def refuser_generation(self):
        """
        Refuser la creation d'un nouveau certificat.
        :return:
        """
        # Repondre au demandeur avec le refus

        self.set_etape_suivante()  # Termine


class ProcessusSignerCSRCADependant(MGProcessusTransaction):

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def traitement_regenerer(self, id_transaction, parametres_processus):
        """ Aucun traitement necessaire, le nouveau cert est re-sauvegarde sous une nouvelle transaction dans PKI """
        pass

    def initiale(self):
        transaction = self.transaction
        domaines = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_DOMAINES]

        # Reverifier la signature de la transaction (eviter alteration dans la base de donnees)
        # Extraire certificat et verifier type. Doit etre: maitredescles ou deployeur.
        enveloppe_cert = self._controleur.verificateur_transaction.verifier(transaction)
        roles_cert = enveloppe_cert.get_roles
        if enveloppe_cert.subject_organization_name == self._controleur.configuration.idmg and \
            'monitor_dependant' in roles_cert:
            self.set_etape_suivante(ProcessusSignerCertificatNoeud.generer_cert.__name__)
        else:
            self.set_etape_suivante(ProcessusSignerCertificatNoeud.refuser_generation.__name__)
            return {
                'autorise': False,
                'domaines': domaines,
                'description': 'demandeur non autorise a signer ce certificat',
                'roles_demandeur': roles_cert
            }

        return {
            'autorise': True,
            'domaines': domaines,
            'roles_demandeur': roles_cert,
        }

    def generer_cert(self):
        """
        Generer cert et creer nouvelle transaction pour PKI
        :return:
        """
        transaction = self.transaction
        csr_bytes = transaction[ConstantesMaitreDesCles.TRANSACTION_CHAMP_CSR].encode('utf-8')

        # Trouver generateur pour le role
        renouvelleur = self._controleur.gestionnaire.renouvelleur_certificat
        clecert = renouvelleur.signer_ca(csr_bytes)

        # Generer nouvelle transaction pour sauvegarder le certificat
        transaction = {
            ConstantesPki.LIBELLE_CERTIFICAT_PEM: clecert.cert_bytes.decode('utf-8'),
            ConstantesPki.LIBELLE_FINGERPRINT: clecert.fingerprint,
            ConstantesPki.LIBELLE_SUBJECT: clecert.formatter_subject(),
            ConstantesPki.LIBELLE_NOT_VALID_BEFORE: int(clecert.not_valid_before.timestamp()),
            ConstantesPki.LIBELLE_NOT_VALID_AFTER: int(clecert.not_valid_after.timestamp()),
            ConstantesPki.LIBELLE_SUBJECT_KEY: clecert.skid,
            ConstantesPki.LIBELLE_AUTHORITY_KEY: clecert.akid,
        }
        self._controleur.generateur_transactions.soumettre_transaction(
            transaction,
            ConstantesPki.TRANSACTION_DOMAINE_NOUVEAU_CERTIFICAT
        )

        # Creer une commande pour que le monitor genere le compte sur RabbitMQ
        self.set_etape_suivante()  # Termine - va repondre automatiquement au deployeur dans finale()

        return {
            'cert': clecert.cert_bytes.decode('utf-8'),
            'fullchain': clecert.chaine,
        }

    def refuser_generation(self):
        """
        Refuser la creation d'un nouveau certificat.
        :return:
        """
        # Repondre au demandeur avec le refus

        self.set_etape_suivante()  # Termine


class ProcessusDeclasserCleGrosFichier(MGProcessusTransaction):

    def initiale(self):
        transaction = self.transaction
        self.__logger.warning("Declasser grosfichier, transmettre cle secrete decryptee pour %s" % transaction['fuuid'])

        # Verifier que la signature de la requete est valide - c'est fort probable, il n'est pas possible de
        # se connecter a MQ sans un certificat verifie. Mais s'assurer qu'il n'y ait pas de "relais" via un
        # messager qui a acces aux noeuds. La signature de la requete permet de faire cette verification.
        enveloppe_certificat = self.controleur.verificateur_transaction.verifier(transaction)
        # Aucune exception lancee, la signature de transaction est valide et provient d'un certificat autorise et connu

        acces_permis = True  # Pour l'instant, les noeuds peuvent tout le temps obtenir l'acces a 4.secure.
        self.__logger.debug(
            "Verification signature requete cle grosfichier. Cert: %s" % str(enveloppe_certificat.fingerprint_ascii))

        fuuid = transaction['fuuid']

        if acces_permis:
            cle_decryptee = self.controleur.gestionnaire.decrypter_grosfichier(fuuid)

            transaction = cle_decryptee.copy()
            transaction['fuuid'] = fuuid

            self.controleur.generateur_transactions.soumettre_transaction(
                transaction, ConstantesGrosFichiers.TRANSACTION_CLESECRETE_FICHIER
            )

        self.set_etape_suivante()  # Termine


class ProcessusGenererCertificatNavigateur(MGProcessusTransaction):
    """
    Generer un certificat pour un navigateur a partir d'une cle publique.
    """

    def initiale(self):
        transaction = self.transaction

        # Reverifier la signature de la transaction (eviter alteration dans la base de donnees)
        # Extraire certificat et verifier type. Doit etre: maitredescles ou deployeur.
        enveloppe_cert = self._controleur.verificateur_transaction.verifier(transaction)
        roles_cert = enveloppe_cert.get_roles
        if enveloppe_cert.subject_organization_name == self._controleur.configuration.idmg and \
                'coupdoeil' in roles_cert:
            # Le coupdoeil peut demander un certificat de navigateur
            self.set_etape_suivante(ProcessusSignerCertificatNoeud.generer_cert.__name__)
        else:
            self.set_etape_suivante(ProcessusSignerCertificatNoeud.refuser_generation.__name__)
            return {
                'autorise': False,
                'description': 'demandeur non autorise a demander la signateur de ce certificat',
                'roles_demandeur': roles_cert
            }

        return {
            'autorise': True,
            'roles_demandeur': roles_cert,
        }

    def generer_cert(self):
        """
        Generer cert et creer nouvelle transaction pour PKI
        :return:
        """
        transaction = self.transaction
        public_key_str = transaction['cle_publique']
        wrapped_public_key = PemHelpers.wrap_public_key(public_key_str)

        sujet = transaction['sujet']

        # Trouver generateur pour le role
        renouvelleur = self._controleur.gestionnaire.renouvelleur_certificat
        clecert = renouvelleur.signer_navigateur(wrapped_public_key, sujet)

        # Generer nouvelle transaction pour sauvegarder le certificat
        transaction = {
            ConstantesPki.LIBELLE_CERTIFICAT_PEM: clecert.cert_bytes.decode('utf-8'),
            ConstantesPki.LIBELLE_FINGERPRINT: clecert.fingerprint,
            ConstantesPki.LIBELLE_SUBJECT: clecert.formatter_subject(),
            ConstantesPki.LIBELLE_NOT_VALID_BEFORE: int(clecert.not_valid_before.timestamp()),
            ConstantesPki.LIBELLE_NOT_VALID_AFTER: int(clecert.not_valid_after.timestamp()),
            ConstantesPki.LIBELLE_SUBJECT_KEY: clecert.skid,
            ConstantesPki.LIBELLE_AUTHORITY_KEY: clecert.akid,
        }
        self._controleur.generateur_transactions.soumettre_transaction(
            transaction,
            ConstantesPki.TRANSACTION_DOMAINE_NOUVEAU_CERTIFICAT
        )

        # Creer une reponse pour coupdoeil
        info_cert = transaction.copy()
        del info_cert[ConstantesPki.LIBELLE_CERTIFICAT_PEM]

        self.set_etape_suivante()  # Termine - va repondre automatiquement

        return {
            'certificat_info': info_cert,
            'cert': clecert.cert_bytes.decode('utf-8'),
            'fullchain': clecert.chaine,
        }

    def refuser_generation(self):
        """
        Refuser la creation d'un nouveau certificat.
        :return:
        """
        # Repondre au demandeur avec le refus

        self.set_etape_suivante()  # Termine


class ProcessusGenererDemandeInscription(MGProcessusTransaction):
    """
    Generer une nouvelle transaction pour l'Annuaire, va servir a demander l'acces a une MilleGrille tierce
    """

    def initiale(self):
        """
        Effecuter une requete pour obtenir la plus recente fiche privee
        """
        domaine = ConstantesAnnuaire.REQUETE_FICHE_PRIVEE
        self.set_requete(domaine, {})

        self.set_etape_suivante(ProcessusGenererDemandeInscription.demander_csr_connecteurs.__name__)

    def demander_csr_connecteurs(self):
        """
        Demander de nouveaux CSR aupres des connecteurs
        """

        domaine = 'inter.genererCsr'
        self.set_requete(domaine, {})

        self.set_etape_suivante(ProcessusGenererDemandeInscription.generer_transaction_annuaire.__name__)

    def generer_transaction_annuaire(self):
        """
        Generer la transaction signee pour l'Annuaire.
        """
        transaction = self.transaction

        idmg = transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_IDMG]
        fiche_privee = self.parametres['reponse'][0]
        csr_reponse = self.parametres['reponse'][1]

        csr = csr_reponse['csr']
        csr_correlation = csr_reponse['correlation']

        certificats_existants = list()
        certificats_existants.append(fiche_privee[ConstantesAnnuaire.LIBELLE_DOC_CERTIFICAT_RACINE])
        certificats_existants.append(fiche_privee[ConstantesAnnuaire.LIBELLE_DOC_CERTIFICAT])
        try:
            certificats_existants.extend(fiche_privee[ConstantesAnnuaire.LIBELLE_DOC_CERTIFICATS_INTERMEDIAIRES])
        except TypeError:
            pass  # Array vide, OK
        try:
            certificats_existants.extend(fiche_privee[ConstantesAnnuaire.LIBELLE_DOC_CERTIFICAT_ADDITIONNELS])
        except TypeError:
            pass  # Array vide, OK

        with open(self.controleur.configuration.pki_certfile, 'r') as fichier:
            certfile_fullchain = fichier.read()
            certs_chain = list()
            for cert in certfile_fullchain.split('-----END CERTIFICATE-----\n'):
                if cert != '' and cert not in certificats_existants:
                    cert = cert + '-----END CERTIFICATE-----\n'
                    certs_chain.append(cert)

        nouvelle_transaction = {
            ConstantesAnnuaire.LIBELLE_DOC_IDMG_SOLLICITE: idmg,
            ConstantesAnnuaire.LIBELLE_DOC_FICHE_PRIVEE: fiche_privee,
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_CSR: csr,
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_CSR_CORRELATION: csr_correlation,
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_TYPEDEMANDE: ConstantesMaitreDesCles.TYPE_DEMANDE_INSCRIPTION,
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_FULLCHAIN: certs_chain,
        }

        # Transmettre la transaction. La correlation permet au domaine de savoir que la transaction
        # doit etre sauvegardee et non actionnee (certificat signe)
        domaine = ConstantesAnnuaire.TRANSACTION_DEMANDER_INSCRIPTION
        self.generateur_transactions.soumettre_transaction(nouvelle_transaction, domaine)

        self.set_etape_suivante()  # Termine


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


class ProcessusGenererCertificatPourTiers(MGProcessusTransaction):
    """
    Genere un certificat de connexion pour un tiers
    """

    def initiale(self):
        domaine = ConstantesAnnuaire.REQUETE_FICHE_PRIVEE
        self.set_requete(domaine, {})

        self.set_etape_suivante(ProcessusGenererCertificatPourTiers.signer_demande.__name__)

    def signer_demande(self):
        """
        Extrait le CSR et genere un nouveau certificat de connecteur.
        """
        fiche_privee = self.parametres['reponse'][0]

        transaction = self.transaction
        fiche_privee_tiers = transaction[ConstantesAnnuaire.LIBELLE_DOC_FICHE_PRIVEE]
        idmg_tiers = fiche_privee_tiers[Constantes.TRANSACTION_MESSAGE_LIBELLE_IDMG]
        csr = transaction[ConstantesAnnuaire.LIBELLE_DOC_DEMANDES_CSR]

        clecert = self.controleur.gestionnaire.generer_certificat_connecteur(idmg_tiers, csr)

        # Sauvegarder certificat pour tiers et transmettre vers tiers
        self._transmettre_a_pki(clecert)
        self._transmettre_a_annuaire(transaction, idmg_tiers, clecert, fiche_privee)

        self.set_etape_suivante()

    def _transmettre_a_annuaire(self, transaction, idmg_tiers, clecert: EnveloppeCleCert, fiche_privee: dict):

        fiche_privee_filtree = DocElemFilter.retirer_champs_doc_transaction(fiche_privee)

        with open(self.controleur.configuration.pki_certfile, 'r') as fichier:
            cert_fullchain = PemHelpers.split_certificats(fichier.read())

        nouvelle_transaction_annuaire = {
            ConstantesAnnuaire.LIBELLE_DOC_IDMG_SOLLICITE: transaction[ConstantesAnnuaire.LIBELLE_DOC_IDMG_SOLLICITE],
            ConstantesAnnuaire.LIBELLE_DOC_EXPIRATION: int(clecert.not_valid_after.timestamp()),
            ConstantesAnnuaire.LIBELLE_DOC_CERTIFICAT: clecert.cert_bytes.decode('utf-8'),
            ConstantesAnnuaire.LIBELLE_DOC_DEMANDES_CORRELATION: transaction[ConstantesAnnuaire.LIBELLE_DOC_DEMANDES_CORRELATION],
            ConstantesAnnuaire.LIBELLE_DOC_FICHE_PRIVEE: fiche_privee_filtree,
            ConstantesMaitreDesCles.TRANSACTION_CHAMP_FULLCHAIN: cert_fullchain,
        }
        self._controleur.generateur_transactions.soumettre_transaction(
            nouvelle_transaction_annuaire, ConstantesAnnuaire.TRANSACTION_SIGNATURE_INSCRIPTION_TIERS,
            idmg_destination=idmg_tiers)

    def _transmettre_a_pki(self, clecert):
        # Generer nouvelle transaction pour sauvegarder le certificat
        transaction = {
            ConstantesPki.LIBELLE_CERTIFICAT_PEM: clecert.cert_bytes.decode('utf-8'),
            ConstantesPki.LIBELLE_FINGERPRINT: clecert.fingerprint,
            ConstantesPki.LIBELLE_SUBJECT: clecert.formatter_subject(),
            ConstantesPki.LIBELLE_NOT_VALID_BEFORE: int(clecert.not_valid_before.timestamp()),
            ConstantesPki.LIBELLE_NOT_VALID_AFTER: int(clecert.not_valid_after.timestamp()),
            ConstantesPki.LIBELLE_SUBJECT_KEY: clecert.skid,
            ConstantesPki.LIBELLE_AUTHORITY_KEY: clecert.akid,
        }
        self._controleur.generateur_transactions.soumettre_transaction(
            transaction,
            ConstantesPki.TRANSACTION_DOMAINE_NOUVEAU_CERTIFICAT,
        )


class ProcessusTrouverClesBackupManquantes(MGProcessus):
    """
    Processus qui identifie les documents de MaitreDesCles avec des cles manquantes.
    Utilise la liste des fingerprints en parametres comme selecteur, mais rechiffre avec
    toutes les cles backup/maitre des cles actives.
    """

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

    def initiale(self):
        fingerprints = self.parametres['fingerprints_base64']

        erreurs = list()
        for doc in self.curseur_docs_cle_manquante(fingerprints):
            self.__logger.debug("Cles manquantes dans " + str(doc))
            self.controleur.gestionnaire.creer_transaction_cles_manquantes(doc)

        for doc in self.curseur_motsdepasse_manquants(fingerprints):
            self.__logger.debug("Mot de passe manquants dans " + str(doc))
            self.controleur.gestionnaire.creer_transaction_motsdepasse_manquants(doc)

        self.set_etape_suivante()  # Termine

        return {'erreurs': erreurs}

    def curseur_docs_cle_manquante(self, fingerprints):
        liste_operateurs = list()
        for fingerprint_base64 in fingerprints:
            liste_operateurs.append({'cles.%s' % fingerprint_base64: {'$exists': False}})
        # Extraire la liste de cles qui n'ont pas tous ces certificats
        filtre = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: {'$in': [
                ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_GROSFICHIERS,
                ConstantesMaitreDesCles.DOCUMENT_LIBVAL_CLES_DOCUMENT,
            ]},
            '$or': liste_operateurs
        }

        collection_documents = self.document_dao.get_collection(ConstantesMaitreDesCles.COLLECTION_DOCUMENTS_NOM)
        return collection_documents.find(filtre)

    def curseur_motsdepasse_manquants(self, fingerprints):
        liste_operateurs = list()
        for fingerprint_base64 in fingerprints:
            liste_operateurs.append({'motdepasse.%s' % fingerprint_base64: {'$exists': False}})

        # Extraire la liste des mots de passe qui n'ont pas tous ces certificats
        filtre = {
            Constantes.DOCUMENT_INFODOC_LIBELLE: {'$in': [
                ConstantesMaitreDesCles.DOCUMENT_LIBVAL_MOTDEPASSE,
            ]},
            '$or': liste_operateurs
        }

        collection_documents = self.document_dao.get_collection(ConstantesMaitreDesCles.COLLECTION_DOCUMENTS_NOM)
        return collection_documents.find(filtre)


class ProcessusCreerClesMilleGrilleHebergee(MGProcessus):
    """
    Genere les cles et certificats pour une nouvelle MilleGrille herbergee.
    """

    def __init__(self, controleur, evenement):
        super().__init__(controleur, evenement)
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

    def initiale(self):
        transactions = self.controleur.gestionnaire.creer_cles_millegrille_hebergee(self.parametres)

        transaction_paires = transactions['paires']
        idmg = transaction_paires['idmg']
        transaction_cle_millegrille = transactions['transaction_cle_millegrille']
        transaction_cle_intermediaire = transactions['transaction_cle_intermediaire']

        # Soumettre transactions immediatement, emettre tokens attente
        uuid_transaction_paires = self.controleur.generateur_transactions.soumettre_transaction(
            transaction_paires, ConstantesMaitreDesCles.TRANSACTION_HEBERGEMENT_NOUVEAU_TROUSSEAU)

        uuid_transaction_cle_millegrille = self.controleur.generateur_transactions.soumettre_transaction(
            transaction_cle_millegrille, ConstantesMaitreDesCles.TRANSACTION_HEBERGEMENT_MOTDEPASSE_CLE)

        uuid_transaction_cle_intermediaire = self.controleur.generateur_transactions.soumettre_transaction(
            transaction_cle_intermediaire, ConstantesMaitreDesCles.TRANSACTION_HEBERGEMENT_MOTDEPASSE_CLE)

        # Emettre tokens attente
        tokens_attente = [
            'ProcessusCreerClesMilleGrilleHebergee_nouveauidmg:' + uuid_transaction_paires,
            'ProcessusCreerClesMilleGrilleHebergee_clemotpasse:' + uuid_transaction_cle_millegrille,
            'ProcessusCreerClesMilleGrilleHebergee_clemotpasse:' + uuid_transaction_cle_intermediaire,
        ]
        # uuids = [uuid_transaction_paires, uuid_transaction_cle_millegrille, uuid_transaction_cle_intermediaire]
        # tokens_attente = ['ProcessusCreerClesMilleGrilleHebergee_nouveauidmg:' + uuid_transaction for uuid_transaction in uuids]
        self.set_etape_suivante(ProcessusCreerClesMilleGrilleHebergee.creer_cles_modules.__name__, tokens_attente)

        return {
            'idmg': idmg,
        }

    def creer_cles_modules(self):
        """
        Generer cles et certificats pour les modules de la MilleGrille
        :return:
        """
        idmg = self.parametres[Constantes.TRANSACTION_MESSAGE_LIBELLE_IDMG]
        roles = [
            ConstantesGenerateurCertificat.ROLE_TRANSACTIONS,
            ConstantesGenerateurCertificat.ROLE_MAITREDESCLES,
            ConstantesGenerateurCertificat.ROLE_COUPDOEIL,
            ConstantesGenerateurCertificat.ROLE_FICHIERS,
            ConstantesGenerateurCertificat.ROLE_DOMAINES,
        ]

        transactions = self.controleur.gestionnaire.creer_cles_modules_heberges(idmg, roles)

        # Emettre tokens attente
        transaction_trousseau = transactions['trousseau']
        uuid_transaction_trousseau = self.generateur_transactions.soumettre_transaction(
            transaction_trousseau,
            ConstantesMaitreDesCles.TRANSACTION_HEBERGEMENT_MAJ_TROUSSEAU
        )

        tokens_attente = [
            'ProcessusCreerClesMilleGrilleHebergee_maj_trousseau:' + uuid_transaction_trousseau,
        ]

        transactions_motsdepasse = transactions['motsdepasse']
        for transaction_motdepasse in transactions_motsdepasse:
            uuid_transaction = self.generateur_transactions.soumettre_transaction(
                transaction_motdepasse,
                ConstantesMaitreDesCles.TRANSACTION_HEBERGEMENT_MOTDEPASSE_CLE
            )
            tokens_attente.append('ProcessusCreerClesMilleGrilleHebergee_clemotpasse:' + uuid_transaction)

        self.set_etape_suivante(
            ProcessusCreerClesMilleGrilleHebergee.transmettre_transaction_hebergement.__name__,
            tokens_attente
        )

    def transmettre_transaction_hebergement(self):
        idmg = self.parametres['idmg']

        transaction_hebergement = {
            'idmg': idmg,
        }
        domaine = Constantes.ConstantesHebergement.TRANSACTION_NOUVEAU_IDMG
        self.ajouter_transaction_a_soumettre(domaine, transaction_hebergement)

        self.set_etape_suivante()  # Termine


class ProcessusHebergementNouveauTrousseau(MGProcessusTransaction):

    def initiale(self):
        transaction = self.transaction
        uuid_transaction = transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE][Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID]
        token_resumer = 'ProcessusCreerClesMilleGrilleHebergee_nouveauidmg:' + uuid_transaction

        # Conserver information du trousseau dans le document d'herbergement sous le maitre des cles
        self.controleur.gestionnaire.sauvegarder_trousseau_hebergement(transaction)

        self.resumer_processus([token_resumer])
        self.set_etape_suivante()  #Termine


class ProcessusHebergementMajTrousseau(MGProcessusTransaction):

    def initiale(self):
        transaction = self.transaction
        idmg = transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_IDMG]
        uuid_transaction = transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE][Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID]
        token_resumer = 'ProcessusCreerClesMilleGrilleHebergee_maj_trousseau:' + uuid_transaction

        # Conserver information du trousseau dans le document d'herbergement sous le maitre des cles
        self.controleur.gestionnaire.maj_trousseau_hebergement(idmg, self.transaction_filtree)

        self.resumer_processus([token_resumer])
        self.set_etape_suivante()  #Termine


class ProcessusHebergementMotdepasseCle(ProcessusNouveauMotDePasse):
    """
    Conserve un mot de passe de cle de certificat d'hebergement
    """

    def resumer(self):
        transaction = self.transaction
        uuid_transaction = transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_EN_TETE][
            Constantes.TRANSACTION_MESSAGE_LIBELLE_UUID]
        token_resumer = 'ProcessusCreerClesMilleGrilleHebergee_clemotpasse:' + uuid_transaction

        self.resumer_processus([token_resumer])
        self.set_etape_suivante()  # Termine

    def _etape_resumer(self):
        return ProcessusHebergementMotdepasseCle.resumer.__name__


class ProcessusHebergementSupprimer(MGProcessusTransaction):
    """
    Supprime le trousseau d'une MilleGrille hebergee
    """
    def initiale(self):
        transaction = self.transaction
        idmg = transaction[Constantes.TRANSACTION_MESSAGE_LIBELLE_IDMG]

        self.controleur.gestionnaire.supprimer_trousseau_hebergement(idmg)

        self.set_etape_suivante()  #Termine
