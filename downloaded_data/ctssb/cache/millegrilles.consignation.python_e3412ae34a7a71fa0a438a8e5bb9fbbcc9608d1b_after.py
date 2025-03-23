from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography import x509
from cryptography.hazmat.primitives import asymmetric

import datetime
import secrets
import base64
import logging
import base58

from millegrilles import Constantes
from millegrilles.SecuritePKI import ConstantesSecurityPki


class ConstantesGenerateurCertificat:

    DUREE_CERT_ROOT = datetime.timedelta(days=3655)
    DUREE_CERT_BACKUP = datetime.timedelta(days=3655)
    DUREE_CERT_MILLEGRILLE = datetime.timedelta(days=730)
    DUREE_CERT_NOEUD = datetime.timedelta(days=366)
    DUREE_CERT_NAVIGATEUR = datetime.timedelta(weeks=6)
    DUREE_CERT_TIERS = datetime.timedelta(weeks=4)
    DUREE_CERT_HERBERGEMENT_XS = datetime.timedelta(days=90)
    ONE_DAY = datetime.timedelta(1, 0, 0)

    ROLE_MQ = 'mq'
    ROLE_MONGO = 'mongo'
    ROLE_DEPLOYEUR = 'deployeur'
    ROLE_MAITREDESCLES = 'maitrecles'
    ROLE_TRANSACTIONS = 'transaction'
    ROLE_CEDULEUR = 'ceduleur'
    ROLE_DOMAINES = 'domaines'
    ROLE_COUPDOEIL = 'coupdoeil'
    ROLE_COUPDOEIL_NAVIGATEUR = 'coupdoeil.navigateur'
    ROLE_FICHIERS = 'fichiers'
    ROLE_VITRINE = 'vitrineapi'
    ROLE_PUBLICATEUR = 'publicateur'
    ROLE_MONGOEXPRESS = 'mongoxp'
    ROLE_NGINX = 'vitrineweb'
    ROLE_CONNECTEUR = 'connecteur'
    ROLE_MONITOR = 'monitor'
    ROLE_MONITOR_DEPENDANT = 'monitor_dependant'
    ROLE_CONNECTEUR_TIERS = 'tiers'
    ROLE_BACKUP = 'backup'
    ROLE_HEBERGEMENT = 'hebergement'
    ROLE_HEBERGEMENT_TRANSACTIONS = 'heb_transaction'
    ROLE_HEBERGEMENT_DOMAINES = 'heb_domaines'
    ROLE_HEBERGEMENT_MAITREDESCLES = 'heb_maitrecles'
    ROLE_HEBERGEMENT_FICHIERS = 'heb_fichiers'
    ROLE_HEBERGEMENT_COUPDOEIL = 'heb_coupdoeil'


    ROLES_ACCES_MONGO = [
        ROLE_MONGO,
        ROLE_TRANSACTIONS,
        ROLE_DOMAINES,
        ROLE_MONGOEXPRESS,
        ROLE_MAITREDESCLES,
    ]

    # Custom OIDs

    # Composant avec acces interne.
    # Liste des exchanges: millegrilles.middleware,millegrilles.noeud,etc.
    MQ_EXCHANGES_OID = x509.ObjectIdentifier('1.2.3.4.0')

    # Liste de roles internes speciaux: transaction,deployeur,maitredescles
    MQ_ROLES_OID = x509.ObjectIdentifier('1.2.3.4.1')

    # Liste des domaines: SenseursPassifs,GrosFichiers,MaitreDesCles,etc.
    MQ_DOMAINES_OID = x509.ObjectIdentifier('1.2.3.4.2')


class EnveloppeCleCert:

    def __init__(self, private_key=None, cert=None, password=None):
        self.private_key = private_key
        self.cert = cert
        self.password = password
        self.csr = None
        self.chaine = None
        self.__fingerprint_b64 = None

    def set_cert(self, cert):
        self.cert = cert

    def set_csr(self, csr):
        self.csr = csr

    def set_chaine(self, chaine: list):
        self.chaine = chaine

    def set_chaine_str(self, chaine: str):
        chaine_list = chaine.split('-----END PRIVATE KEY-----')
        self.chaine = list()
        for cert in chaine_list:
            cert = cert + '-----END PRIVATE KEY-----'
            self.chaine.append(cert)

    def from_pem_bytes(self, private_key_bytes, cert_bytes, password_bytes=None):
        self.private_key = serialization.load_pem_private_key(
            private_key_bytes,
            password=password_bytes,
            backend=default_backend()
        )

        self.password = password_bytes

        self.cert_from_pem_bytes(cert_bytes)

    def cert_from_pem_bytes(self, cert_bytes):
        self.cert = x509.load_pem_x509_certificate(cert_bytes, default_backend())

    def cle_correspondent(self):
        if self.private_key is not None and self.cert is not None:
            # Verifier que le cert et la cle privee correspondent
            public1 = self.private_key.public_key().public_numbers()
            public2 = self.cert.public_key().public_numbers()

            n1 = public1.n
            n2 = public2.n

            return n1 == n2

        return False

    def key_from_pem_bytes(self, key_bytes, password_bytes=None):
        self.private_key = serialization.load_pem_private_key(
            key_bytes,
            password=password_bytes,
            backend=default_backend()
        )

    def from_files(self, private_key, cert, password_bytes=None):
        with open(cert, 'rb') as fichier:
            self.cert = x509.load_pem_x509_certificate(fichier.read(), default_backend())

        with open(private_key, 'rb') as fichier:
            self.key_from_pem_bytes(fichier.read(), password_bytes)

    def chiffrage_asymmetrique(self, cle_secrete):
        public_key = self.cert.public_key()
        cle_secrete_backup = public_key.encrypt(
            cle_secrete,
            asymmetric.padding.OAEP(
                mgf=asymmetric.padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        fingerprint = self.fingerprint
        return cle_secrete_backup, fingerprint

    def dechiffrage_asymmetrique(self, contenu):
        """
        Utilise la cle privee en memoire pour dechiffrer le contenu.
        :param contenu:
        :return:
        """
        contenu_bytes = base64.b64decode(contenu)

        contenu_dechiffre = self.private_key.decrypt(
            contenu_bytes,
            asymmetric.padding.OAEP(
                mgf=asymmetric.padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        return contenu_dechiffre

    @property
    def get_roles(self):
        extensions = self.cert.extensions
        oid_attribute = extensions.get_extension_for_oid(ConstantesGenerateurCertificat.MQ_ROLES_OID)
        oid_value = oid_attribute.value
        oid_value = oid_value.value.decode('utf-8')
        attribute_values = oid_value.split(',')
        return attribute_values

    @property
    def get_exchanges(self):
        MQ_EXCHANGES_OID = x509.ObjectIdentifier('1.2.3.4.0')
        extensions = self.cert.extensions
        oid_attribute = extensions.get_extension_for_oid(MQ_EXCHANGES_OID)
        oid_value = oid_attribute.value
        oid_value = oid_value.value.decode('utf-8')
        attribute_values = oid_value.split(',')
        return attribute_values

    @property
    def get_domaines(self):
        MQ_DOMAINES_OID = x509.ObjectIdentifier('1.2.3.4.2')
        extensions = self.cert.extensions
        oid_attribute = extensions.get_extension_for_oid(MQ_DOMAINES_OID)
        oid_value = oid_attribute.value
        oid_value = oid_value.value.decode('utf-8')
        attribute_values = oid_value.split(',')
        return attribute_values

    @property
    def cert_bytes(self):
        return self.cert.public_bytes(serialization.Encoding.PEM)

    @property
    def public_bytes(self):
        if self.cert:
            return self.cert_bytes
        elif self.private_key:
            return self.private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)

        return None

    @property
    def csr_bytes(self):
        return self.csr.public_bytes(serialization.Encoding.PEM)

    @property
    def akid(self):
        return EnveloppeCleCert.get_authority_identifier(self.cert)

    @property
    def skid(self):
        return EnveloppeCleCert.get_subject_identifier(self.cert)

    @property
    def fingerprint(self) -> str:
        return bytes.hex(self.cert.fingerprint(hashes.SHA1()))

    @property
    def fingerprint_base58(self) -> str:
        return self.idmg

    @property
    def fingerprint_b64(self):
        if not self.__fingerprint_b64:
            self.__fingerprint_b64 = str(base64.b64encode(self.cert.fingerprint(hashes.SHA1())), 'utf-8')

        return self.__fingerprint_b64

    @fingerprint_b64.setter
    def fingerprint_b64(self, fingerprint_b64):
        self.__fingerprint_b64 = fingerprint_b64

    @property
    def idmg(self) -> str:
        """
        Retourne le idmg du certificat.
        Calcule avec SHA-512/224 retourne en base58
        """
        idmg = base58.b58encode(self.cert.fingerprint(hashes.SHA512_224())).decode('utf-8')
        return idmg

    @property
    def not_valid_before(self) -> datetime.datetime:
        return self.cert.not_valid_before

    @property
    def not_valid_after(self) -> datetime.datetime:
        return self.cert.not_valid_after

    @property
    def private_key_bytes(self):
        if self.password is not None:
            cle_privee_bytes = self.private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.BestAvailableEncryption(self.password)
            )
        else:
            cle_privee_bytes = self.private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()
            )

        return cle_privee_bytes

    def generer_private_key(self, generer_password=False, keysize=2048, public_exponent=65537):
        if generer_password:
            self.password = base64.b64encode(secrets.token_bytes(16))

        self.private_key = asymmetric.rsa.generate_private_key(
            public_exponent=public_exponent,
            key_size=keysize,
            backend=default_backend()
        )

    @staticmethod
    def get_authority_identifier(certificat):
        authorityKeyIdentifier = certificat.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier)
        key_id = bytes.hex(authorityKeyIdentifier.value.key_identifier)
        return key_id

    @staticmethod
    def get_subject_identifier(certificat):
        subjectKeyIdentifier = certificat.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
        key_id = bytes.hex(subjectKeyIdentifier.value.digest)
        return key_id

    def formatter_subject(self):
        sujet_dict = {}

        sujet = self.cert.subject
        for elem in sujet:
            sujet_dict[elem.oid._name] = elem.value

        return sujet_dict

    def formatter_issuer(self):
        sujet_dict = {}

        sujet = self.cert.issuer
        for elem in sujet:
            sujet_dict[elem.oid._name] = elem.value

        return sujet_dict

    def subject_rfc4514_string(self):
        return self.cert.subject.rfc4514_string()

    def subject_rfc4514_string_mq(self):
        """
        Subject avec ordre inverse pour RabbitMQ EXTERNAL
        :return:
        """
        subject = self.subject_rfc4514_string()
        subject_list = subject.split(',')
        subject_list.reverse()
        return ','.join(subject_list)


class GenerateurCertificat:

    def __init__(self, idmg):
        self._idmg = idmg
        self.__public_exponent = 65537
        self.__keysize = 2048
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    @staticmethod
    def split_chaine(chaine: str) -> list:
        """ Split une liste de certificats en liste """
        pass

    def generer(self) -> EnveloppeCleCert:
        raise NotImplementedError("Pas implemente")

    def signer(self, csr) -> x509.Certificate:
        raise NotImplementedError("Pas implemente")

    def _get_keyusage(self, builder):
        raise NotImplementedError("Pas implemente")

    def _preparer_builder_from_csr(self, csr_request, autorite_cert,
                                   duree_cert=ConstantesGenerateurCertificat.DUREE_CERT_NOEUD) -> x509.CertificateBuilder:

        builder = x509.CertificateBuilder()
        builder = builder.subject_name(csr_request.subject)
        builder = builder.issuer_name(autorite_cert.subject)
        builder = builder.not_valid_before(datetime.datetime.today() - ConstantesGenerateurCertificat.ONE_DAY)
        builder = builder.not_valid_after(datetime.datetime.today() + duree_cert)
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.public_key(csr_request.public_key())

        return builder

    def preparer_request(self, common_name, unit_name=None, alt_names: list = None) -> EnveloppeCleCert:
        clecert = EnveloppeCleCert()
        clecert.generer_private_key()

        builder = x509.CertificateSigningRequestBuilder()

        # Batir subject
        name_list = [x509.NameAttribute(x509.name.NameOID.ORGANIZATION_NAME, self._idmg)]
        if unit_name is not None:
            name_list.append(x509.NameAttribute(x509.name.NameOID.ORGANIZATIONAL_UNIT_NAME, unit_name))
        name_list.append(x509.NameAttribute(x509.name.NameOID.COMMON_NAME, common_name))
        name = x509.Name(name_list)
        builder = builder.subject_name(name)

        if alt_names is not None:
            self.__logger.debug("Preparer requete %s avec urls publics: %s" % (common_name, str(alt_names)))
            liste_names = list()
            for alt_name in alt_names:
                liste_names.append(x509.DNSName(alt_name))
            # Ajouter noms DNS valides pour MQ
            builder = builder.add_extension(x509.SubjectAlternativeName(liste_names), critical=False)

        request = builder.sign(
            clecert.private_key, hashes.SHA256(), default_backend()
        )
        clecert.set_csr(request)

        return clecert

    def preparer_key_request(self, unit_name, common_name, generer_password=False, alt_names: list = None) -> EnveloppeCleCert:
        clecert = EnveloppeCleCert()
        clecert.generer_private_key(generer_password=generer_password)

        builder = x509.CertificateSigningRequestBuilder()
        name = x509.Name([
            x509.NameAttribute(x509.name.NameOID.ORGANIZATION_NAME, self._idmg),
            x509.NameAttribute(x509.name.NameOID.ORGANIZATIONAL_UNIT_NAME, unit_name),
            x509.NameAttribute(x509.name.NameOID.COMMON_NAME, common_name),
        ])
        builder = builder.subject_name(name)

        if alt_names is not None:
            self.__logger.debug("Preparer requete %s avec urls publics: %s" % (common_name, str(alt_names)))
            liste_names = list()
            for alt_name in alt_names:
                liste_names.append(x509.DNSName(alt_name))
            # Ajouter noms DNS valides pour MQ
            builder = builder.add_extension(x509.SubjectAlternativeName(liste_names), critical=False)

        request = builder.sign(
            clecert.private_key, hashes.SHA256(), default_backend()
        )
        clecert.set_csr(request)

        return clecert


class GenerateurCertificateParClePublique(GenerateurCertificat):

    def __init__(self, idmg, dict_ca: dict = None, autorite: EnveloppeCleCert = None, domaines_publics: list = None):
        super().__init__(idmg)
        self._dict_ca = dict_ca
        self._autorite = autorite
        self.__domaines_publics = domaines_publics
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def _get_keyusage(self, builder):
        builder = builder.add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )

        builder = builder.add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=True,
                data_encipherment=True,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False
            ),
            critical=False
        )

        return builder

    def preparer_builder(self, cle_publique_pem: str, sujet: str,
                                   duree_cert=ConstantesGenerateurCertificat.DUREE_CERT_NAVIGATEUR) -> x509.CertificateBuilder:

        builder = x509.CertificateBuilder()

        name = x509.Name([
            x509.NameAttribute(x509.name.NameOID.ORGANIZATION_NAME, self._idmg),
            x509.NameAttribute(x509.name.NameOID.COMMON_NAME, sujet),
        ])
        builder = builder.subject_name(name)

        builder = builder.issuer_name(self._autorite.cert.subject)
        builder = builder.not_valid_before(datetime.datetime.today() - ConstantesGenerateurCertificat.ONE_DAY)
        builder = builder.not_valid_after(datetime.datetime.today() + duree_cert)
        builder = builder.serial_number(x509.random_serial_number())

        pem_bytes = cle_publique_pem.encode('utf-8')

        public_key = serialization.load_pem_public_key(
            pem_bytes,
            backend=default_backend()
        )

        builder = builder.public_key(public_key)

        builder = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(public_key),
            critical=False
        )

        ski = self._autorite.cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_KEY_IDENTIFIER)
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier(
                ski.value.digest,
                None,
                None
            ),
            critical=False
        )

        # Ajouter les acces specifiques a ce type de cert
        builder = self._get_keyusage(builder)

        return builder

    def signer(self, builder) -> x509.Certificate:

        cle_autorite = self._autorite.private_key
        certificate = builder.sign(
            private_key=cle_autorite,
            algorithm=hashes.SHA256(),
            backend=default_backend()
        )

        return certificate

    def aligner_chaine(self, certificat: x509.Certificate):
        """
        Genere la chaine PEM str avec le certificat et les certificats intermediares. Exclue root.
        :param certificat:
        :return:
        """
        chaine = [certificat]

        akid_autorite = EnveloppeCleCert.get_authority_identifier(certificat)
        idx = 0
        for idx in range(0, 100):
            cert_autorite = self._dict_ca.get(akid_autorite)

            if cert_autorite is None:
                raise Exception("Erreur, autorite introuvable")

            chaine.append(cert_autorite)
            akid_autorite_suivante = EnveloppeCleCert.get_authority_identifier(cert_autorite)

            if akid_autorite == akid_autorite_suivante:
                # On est rendu au root
                break

            akid_autorite = akid_autorite_suivante

        if idx == 100:
            raise Exception("Depasse limite profondeur")

        # Generer la chaine de certificats avec les intermediaires
        return [c.public_bytes(serialization.Encoding.PEM).decode('utf-8') for c in chaine]


class GenerateurCertificateParRequest(GenerateurCertificat):

    def __init__(self, idmg, dict_ca: dict = None, autorite: EnveloppeCleCert = None, domaines_publics: list = None):
        super().__init__(idmg)
        self._dict_ca = dict_ca
        self._autorite = autorite
        self.__domaines_publics = domaines_publics
        self.__logger = logging.getLogger('%s.%s' % (__name__, self.__class__.__name__))

    def _get_keyusage(self, builder):
        builder = builder.add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )

        builder = builder.add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=True,
                data_encipherment=True,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False
            ),
            critical=False
        )

        return builder

    def signer(self, csr: x509.CertificateSigningRequest) -> x509.Certificate:
        cert_autorite = self._autorite.cert
        builder = self._preparer_builder_from_csr(
            csr, cert_autorite, ConstantesGenerateurCertificat.DUREE_CERT_NOEUD)

        builder = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(csr.public_key()),
            critical=False
        )

        ski = cert_autorite.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_KEY_IDENTIFIER)
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier(
                ski.value.digest,
                None,
                None
            ),
            critical=False
        )

        # Ajouter les acces specifiques a ce type de cert
        builder = self._get_keyusage(builder)

        cle_autorite = self._autorite.private_key
        certificate = builder.sign(
            private_key=cle_autorite,
            algorithm=hashes.SHA256(),
            backend=default_backend()
        )
        return certificate

    def aligner_chaine(self, certificat: x509.Certificate):
        """
        Genere la chaine PEM str avec le certificat et les certificats intermediares. Exclue root.
        :param certificat:
        :return:
        """
        chaine = [certificat]

        akid_autorite = EnveloppeCleCert.get_authority_identifier(certificat)
        idx = 0
        for idx in range(0, 5):
            cert_autorite = self._dict_ca.get(akid_autorite)

            if cert_autorite is None:
                raise Exception("Erreur, autorite %s introuvable" % akid_autorite)

            chaine.append(cert_autorite)
            akid_autorite_suivante = EnveloppeCleCert.get_authority_identifier(cert_autorite)

            if akid_autorite == akid_autorite_suivante:
                # On est rendu au root
                # chaine.pop()
                break

            akid_autorite = akid_autorite_suivante

        if idx == 5:
            raise Exception("Depasse limite profondeur")

        # Generer la chaine de certificats avec les intermediaires
        return [c.public_bytes(serialization.Encoding.PEM).decode('utf-8') for c in chaine]


class GenerateurCertificatMilleGrille(GenerateurCertificateParRequest):

    def __init__(self, idmg, dict_ca: dict = None, autorite: EnveloppeCleCert = None):
        super().__init__(idmg, dict_ca, autorite)

    def generer(self) -> EnveloppeCleCert:
        """
        Sert a renouveller un certificat de millegrille. Conserve tous les autres certs de MilleGrille valides
        jusqu'a echeance.
        :return:
        """
        # Preparer une nouvelle cle et CSR pour la millegrille
        clecert = super().preparer_key_request(
            unit_name=u'MilleGrille',
            common_name=self._idmg,
            generer_password=True
        )

        # Signer avec l'autorite pour obtenir le certificat de MilleGrille
        csr_millegrille = clecert.csr
        certificate = self.signer(csr_millegrille)
        clecert.set_cert(certificate)

        chaine = self.aligner_chaine(certificate)
        clecert.set_chaine(chaine)

        return clecert

    def _get_keyusage(self, builder):
        builder = builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=4),
            critical=True,
        )

        builder = builder.add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=True,
                data_encipherment=True,
                key_agreement=True,
                key_cert_sign=True,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False
            ),
            critical=False
        )

        return builder


class GenerateurInitial(GenerateurCertificatMilleGrille):
    """
    Sert a generer une chaine initiale de cles et certs CA pour une millegrille.
    """

    def __init__(self, idmg, autorite: EnveloppeCleCert = None):
        super().__init__(idmg, None, None)
        self._autorite = autorite

    def generer(self) -> EnveloppeCleCert:
        """
        :return:
        """
        if self.autorite is None:
            # Le certificat d'autorite n'a pas encore ete generer, on s'en occupe
            self._autorite = self._generer_self_signed()

        ss_cert = self.autorite.cert
        ss_skid = self.autorite.skid
        self._dict_ca = {ss_skid: ss_cert}

        # Calculer idmg de la nouvelle MilleGrille
        self._idmg = self.autorite.idmg

        millegrille = super().generer()
        millegrille_skid = EnveloppeCleCert.get_subject_identifier(ss_cert)
        self._dict_ca[millegrille_skid] = millegrille

        return millegrille

    def __preparer_builder(self, private_key, duree_cert=ConstantesGenerateurCertificat.DUREE_CERT_NOEUD) -> x509.CertificateBuilder:
        public_key = private_key.public_key()
        builder = x509.CertificateBuilder()
        builder = builder.not_valid_before(datetime.datetime.today() - ConstantesGenerateurCertificat.ONE_DAY)
        builder = builder.not_valid_after(datetime.datetime.today() + duree_cert)
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.public_key(public_key)

        builder = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(public_key),
            critical=False
        )

        return builder

    def _generer_self_signed(self) -> EnveloppeCleCert:
        clecert = EnveloppeCleCert()
        clecert.generer_private_key(generer_password=True, keysize=4096)
        builder = self.__preparer_builder(clecert.private_key, duree_cert=ConstantesGenerateurCertificat.DUREE_CERT_ROOT)

        name = x509.Name([
            x509.NameAttribute(x509.name.NameOID.ORGANIZATION_NAME, u'MilleGrille'),
            x509.NameAttribute(x509.name.NameOID.COMMON_NAME, u'Racine'),
        ])
        builder = builder.subject_name(name)
        builder = builder.issuer_name(name)

        builder = builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=5),
            critical=True,
        )

        ski = x509.SubjectKeyIdentifier.from_public_key(clecert.private_key.public_key())
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier(
                ski.digest,
                None,
                None
            ),
            critical=False
        )

        certificate = builder.sign(
            private_key=clecert.private_key,
            algorithm=hashes.SHA512(),
            backend=default_backend()
        )

        clecert.set_cert(certificate)

        return clecert

    @property
    def autorite(self):
        return self._autorite


class GenerateurNoeud(GenerateurCertificateParRequest):

    def __init__(self, idmg, organization_nom, common_name, dict_ca: dict, autorite: EnveloppeCleCert = None,
                 domaines_publics: list = None, generer_password=False):
        super().__init__(idmg, dict_ca, autorite, domaines_publics)
        self._organization_name = organization_nom
        self._common_name = common_name
        self._domaines_publics = domaines_publics
        self._generer_password = generer_password

    def generer(self) -> EnveloppeCleCert:
        # Preparer une nouvelle cle et CSR pour la millegrille
        clecert = super().preparer_key_request(
            unit_name=self._organization_name,
            common_name=self._common_name,
            generer_password=self.generer_password
        )

        # Signer avec l'autorite pour obtenir le certificat de MilleGrille
        csr_millegrille = clecert.csr
        certificate = self.signer(csr_millegrille)
        clecert.set_cert(certificate)

        chaine = self.aligner_chaine(certificate)
        clecert.set_chaine(chaine)

        return clecert

    @property
    def generer_password(self):
        return self._generer_password


class GenererDeployeur(GenerateurNoeud):
    """
    Deployeur de MilleGrilles
    """

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID
        exchanges = ('%s' % Constantes.DEFAUT_MQ_EXCHANGE_MIDDLEWARE).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ('%s' % ConstantesGenerateurCertificat.ROLE_DEPLOYEUR).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder


class GenererCeduleur(GenerateurNoeud):
    """
    Ceduleur de MilleGrilles
    """

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID

        exchanges_supportes = [
            Constantes.DEFAUT_MQ_EXCHANGE_MIDDLEWARE,
            Constantes.DEFAUT_MQ_EXCHANGE_NOEUDS,
            Constantes.DEFAUT_MQ_EXCHANGE_PRIVE,
            Constantes.DEFAUT_MQ_EXCHANGE_PUBLIC,
        ]

        exchanges = (','.join(exchanges_supportes)).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ('%s' % ConstantesGenerateurCertificat.ROLE_CEDULEUR).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder


class GenererMaitredescles(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID
        exchanges = ('%s' % Constantes.DEFAUT_MQ_EXCHANGE_MIDDLEWARE).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ('%s' % ConstantesGenerateurCertificat.ROLE_MAITREDESCLES).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder


class GenererMaitredesclesCryptage(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID
        exchanges = ('%s' % Constantes.DEFAUT_MQ_EXCHANGE_MIDDLEWARE).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ('%s' % ConstantesGenerateurCertificat.ROLE_MAITREDESCLES).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder

    @property
    def generer_password(self):
        return True


class GenererTransactions(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID
        exchanges = ('%s' % Constantes.DEFAUT_MQ_EXCHANGE_MIDDLEWARE).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ('%s' % ConstantesGenerateurCertificat.ROLE_TRANSACTIONS).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder


class GenererDomaines(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID
        exchanges = ('%s' % Constantes.DEFAUT_MQ_EXCHANGE_MIDDLEWARE).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ('%s' % ConstantesGenerateurCertificat.ROLE_DOMAINES).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder


class GenererConnecteur(GenerateurNoeud):
    """
    Generateur de certificats pour le connecteur inter-MilleGrilles
    """

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID
        exchanges = ('%s,%s' % (Constantes.DEFAUT_MQ_EXCHANGE_NOEUDS, Constantes.DEFAUT_MQ_EXCHANGE_PRIVE)).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ('%s' % ConstantesGenerateurCertificat.ROLE_CONNECTEUR).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder


class GenererMonitor(GenerateurNoeud):
    """
    Generateur de certificats pour le monitor de noeud protege principal
    """

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID

        exchanges = ','.join([
            Constantes.DEFAUT_MQ_EXCHANGE_MIDDLEWARE,
            Constantes.DEFAUT_MQ_EXCHANGE_NOEUDS,
            Constantes.DEFAUT_MQ_EXCHANGE_PRIVE
        ]).encode('utf-8')

        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ConstantesGenerateurCertificat.ROLE_MONITOR.encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder


class GenererMonitorDependant(GenerateurNoeud):
    """
    Generateur de certificats pour le monitor de services
    """

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID

        exchanges = ','.join([
            Constantes.DEFAUT_MQ_EXCHANGE_MIDDLEWARE,
            Constantes.DEFAUT_MQ_EXCHANGE_NOEUDS,
            Constantes.DEFAUT_MQ_EXCHANGE_PRIVE
        ]).encode('utf-8')

        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ConstantesGenerateurCertificat.ROLE_MONITOR_DEPENDANT.encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder


class GenererMQ(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ('%s' % ConstantesGenerateurCertificat.ROLE_MQ).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        liste_dns = [
            x509.DNSName(u'mq'),
            x509.DNSName(u'mq-%s.local' % self._idmg),
            x509.DNSName(u'%s' % self._common_name),
            x509.DNSName(u'%s.local' % self._common_name),
        ]

        # Ajouter la liste des domaines publics recus du CSR
        if self._domaines_publics is not None:
            liste_dns.extend([x509.DNSName(d) for d in self._domaines_publics])

        # Si le CN == mg-IDMG, on n'a pas besoin d'ajouter cette combinaison (identique)
        if self._common_name != 'mg-%s' % self._idmg:
            liste_dns.append(x509.DNSName(u'mg-%s' % self._idmg))
            liste_dns.append(x509.DNSName(u'mg-%s.local' % self._idmg))

        # Ajouter noms DNS valides pour MQ
        builder = builder.add_extension(x509.SubjectAlternativeName(liste_dns), critical=False)

        return builder


class GenererMongo(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ('%s' % ConstantesGenerateurCertificat.ROLE_MONGO).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        liste_dns = [
            x509.DNSName(u'mongo'),
            x509.DNSName(u'mongo-%s.local' % self._idmg),
            x509.DNSName(u'%s' % self._common_name),
            x509.DNSName(u'%s.local' % self._common_name),
        ]

        # Si le CN == mg-IDMG, on n'a pas besoin d'ajouter cette combinaison (identique)
        if self._common_name != 'mg-%s' % self._idmg:
            liste_dns.append(x509.DNSName(u'mg-%s' % self._idmg))
            liste_dns.append(x509.DNSName(u'mg-%s.local' % self._idmg))

        if self._domaines_publics is not None:
            for domaine in self._domaines_publics:
                liste_dns.append(x509.DNSName(u'%s' % domaine))
                liste_dns.append(x509.DNSName(u'mq.%s' % domaine))

        # Ajouter noms DNS valides pour MQ
        builder = builder.add_extension(x509.SubjectAlternativeName(liste_dns), critical=False)

        return builder


class GenererCoupdoeil(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID
        exchanges = ('%s' % Constantes.DEFAUT_MQ_EXCHANGE_NOEUDS).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ('%s' % ConstantesGenerateurCertificat.ROLE_COUPDOEIL).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        liste_dns = [
            x509.DNSName(u'www'),
            x509.DNSName(u'www-%s.local' % self._idmg),
            x509.DNSName(u'%s' % self._common_name),
            x509.DNSName(u'%s.local' % self._common_name),
            x509.DNSName(u'coupdoeil-%s' % self._idmg),
            x509.DNSName(u'coupdoeil-%s.local' % self._idmg),
        ]

        if self._domaines_publics is not None:
            for domaine in self._domaines_publics:
                liste_dns.append(x509.DNSName(u'%s' % domaine))
                liste_dns.append(x509.DNSName(u'coupdoeil.%s' % domaine))

        # Ajouter noms DNS valides pour CoupDoeil
        builder = builder.add_extension(x509.SubjectAlternativeName(liste_dns), critical=False)

        return builder


class GenererFichiers(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID
        exchanges = ('%s' % Constantes.DEFAUT_MQ_EXCHANGE_NOEUDS).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ('%s' % ConstantesGenerateurCertificat.ROLE_FICHIERS).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        liste_dns = [
            x509.DNSName(u'fichiers'),
            x509.DNSName(u'%s' % self._common_name),
            x509.DNSName(u'%s.local' % self._common_name),
        ]

        # Ajouter noms DNS valides pour MQ
        builder = builder.add_extension(x509.SubjectAlternativeName(liste_dns), critical=False)

        return builder


class GenererVitrine(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID
        exchanges = ('%s' % Constantes.DEFAUT_MQ_EXCHANGE_PUBLIC).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ('%s' % ConstantesGenerateurCertificat.ROLE_VITRINE).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        liste_dns = [
            x509.DNSName(u'www'),
            x509.DNSName(u'www-%s.local' % self._idmg),
            x509.DNSName(u'%s' % self._common_name),
            x509.DNSName(u'%s.local' % self._common_name),
            x509.DNSName(u'vitrine-%s' % self._idmg),
            x509.DNSName(u'vitrine-%s.local' % self._idmg),
        ]

        if self._domaines_publics is not None:
            for domaine in self._domaines_publics:
                liste_dns.append(x509.DNSName(u'%s' % domaine))
                liste_dns.append(x509.DNSName(u'vitrine.%s' % domaine))

        # Ajouter noms DNS valides pour CoupDoeil
        builder = builder.add_extension(x509.SubjectAlternativeName(liste_dns), critical=False)

        return builder


class GenererMongoexpress(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ('%s' % ConstantesGenerateurCertificat.ROLE_MONGOEXPRESS).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        liste_dns = [
            x509.DNSName(u'mongoxp'),
            x509.DNSName(u'mongoxp-%s.local' % self._idmg),
            x509.DNSName(u'%s' % self._common_name),
            x509.DNSName(u'%s.local' % self._common_name),
        ]

        # # Si le CN == mg-IDMG, on n'a pas besoin d'ajouter cette combinaison (identique)
        # if self._common_name != 'mg-%s' % self._idmg:
        #     liste_dns.append(x509.DNSName(u'mg-%s' % self._idmg))
        #     liste_dns.append(x509.DNSName(u'mg-%s.local' % self._idmg))

        # Ajouter noms DNS valides pour MQ
        builder = builder.add_extension(x509.SubjectAlternativeName(liste_dns), critical=False)

        return builder


class GenererNginx(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ('%s' % ConstantesGenerateurCertificat.ROLE_NGINX).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        liste_dns = [
            x509.DNSName(u'www'),
            x509.DNSName(u'www-%s.local' % self._idmg),
            x509.DNSName(u'%s' % self._common_name),
            x509.DNSName(u'%s.local' % self._common_name),
        ]

        # Si le CN == mg-idmg, on n'a pas besoin d'ajouter cette combinaison (identique)
        if self._common_name != 'mg-%s' % self._idmg:
            liste_dns.append(x509.DNSName(u'mg-%s' % self._idmg))
            liste_dns.append(x509.DNSName(u'mg-%s.local' % self._idmg))

        if self._domaines_publics is not None:
            for domaine in self._domaines_publics:
                liste_dns.append(x509.DNSName(u'%s' % domaine))
                liste_dns.append(x509.DNSName(u'www.%s' % domaine))

        # Ajouter noms DNS valides pour MQ
        builder = builder.add_extension(x509.SubjectAlternativeName(liste_dns), critical=False)

        return builder


class GenererHebergementTransactions(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID
        exchange_list = [
            Constantes.DEFAUT_MQ_EXCHANGE_MIDDLEWARE,
            Constantes.DEFAUT_MQ_EXCHANGE_NOEUDS,
            Constantes.DEFAUT_MQ_EXCHANGE_PRIVE,
            Constantes.DEFAUT_MQ_EXCHANGE_PUBLIC,
        ]
        exchanges = ','.join(exchange_list).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles_list = [
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT_TRANSACTIONS,
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT,
        ]
        roles = ','.join(roles_list).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder


class GenererHebergementDomaines(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID
        exchange_list = [
            Constantes.DEFAUT_MQ_EXCHANGE_MIDDLEWARE,
            Constantes.DEFAUT_MQ_EXCHANGE_NOEUDS,
            Constantes.DEFAUT_MQ_EXCHANGE_PRIVE,
            Constantes.DEFAUT_MQ_EXCHANGE_PUBLIC,
        ]
        exchanges = ','.join(exchange_list).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles_list = [
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT_DOMAINES,
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT,
        ]
        roles = ','.join(roles_list).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder


class GenererHebergementMaitredescles(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID
        exchange_list = [
            Constantes.DEFAUT_MQ_EXCHANGE_MIDDLEWARE,
            Constantes.DEFAUT_MQ_EXCHANGE_NOEUDS,
            Constantes.DEFAUT_MQ_EXCHANGE_PRIVE,
            Constantes.DEFAUT_MQ_EXCHANGE_PUBLIC,
        ]
        exchanges = ','.join(exchange_list).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles_list = [
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT_MAITREDESCLES,
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT,
        ]
        roles = ','.join(roles_list).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder


class GenererHebergementCoupdoeil(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID
        exchange_list = [
            Constantes.DEFAUT_MQ_EXCHANGE_NOEUDS,
        ]
        exchanges = ','.join(exchange_list).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles_list = [
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT_COUPDOEIL,
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT,
        ]
        roles = ','.join(roles_list).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder


class GenererHebergementFichiers(GenerateurNoeud):

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_permis = ConstantesGenerateurCertificat.MQ_EXCHANGES_OID
        exchange_list = [
            Constantes.DEFAUT_MQ_EXCHANGE_MIDDLEWARE,
            Constantes.DEFAUT_MQ_EXCHANGE_NOEUDS,
            Constantes.DEFAUT_MQ_EXCHANGE_PRIVE,
        ]
        exchanges = ','.join(exchange_list).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_permis, exchanges),
            critical=False
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles_list = [
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT_FICHIERS,
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT,
        ]
        roles = ','.join(roles_list).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        liste_dns = [
            x509.DNSName(u'heb_fichiers'),
            x509.DNSName(u'fichiers'),
            x509.DNSName(u'%s' % self._common_name),
            x509.DNSName(u'%s.local' % self._common_name),
        ]

        # Ajouter noms DNS valides pour MQ
        builder = builder.add_extension(x509.SubjectAlternativeName(liste_dns), critical=False)

        return builder


class GenerateurCertificateNoeud(GenerateurCertificateParRequest):

    def __init__(self, idmg, domaines: list, dict_ca: dict = None, autorite: EnveloppeCleCert = None):
        super().__init__(idmg, dict_ca, autorite)
        self.__domaines = domaines

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ','.join(self.__domaines).encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder


class GenerateurCertificatTiers(GenerateurCertificateParRequest):

    def __init__(self, idmg_local, idmg_tiers, dict_ca: dict = None, autorite: EnveloppeCleCert = None):
        super().__init__(idmg_local, dict_ca, autorite)
        self._idmg_tiers = idmg_tiers

    def _preparer_builder_from_csr(self, csr_request, autorite_cert,
                                   duree_cert=ConstantesGenerateurCertificat.DUREE_CERT_TIERS) -> x509.CertificateBuilder:

        builder = x509.CertificateBuilder()
        builder = builder.issuer_name(autorite_cert.subject)
        builder = builder.not_valid_before(datetime.datetime.today() - ConstantesGenerateurCertificat.ONE_DAY)
        builder = builder.not_valid_after(datetime.datetime.today() + ConstantesGenerateurCertificat.DUREE_CERT_TIERS)
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.public_key(csr_request.public_key())

        # Modifier le nom
        name = x509.Name([
            x509.NameAttribute(x509.name.NameOID.ORGANIZATION_NAME, self._idmg),
            x509.NameAttribute(x509.name.NameOID.COMMON_NAME, self._idmg_tiers),
        ])

        builder = builder.subject_name(name)

        return builder

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)
        return builder


class GenerateurCertificateNavigateur(GenerateurCertificateParClePublique):

    def __init__(self, idmg, dict_ca: dict = None, autorite: EnveloppeCleCert = None):
        super().__init__(idmg, dict_ca, autorite)

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = 'coupdoeil.navigateur'.encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder


class GenerateurCertificatBackup(GenerateurCertificateParClePublique):

    def __init__(self, idmg, dict_ca: dict = None, autorite: EnveloppeCleCert = None):
        super().__init__(idmg, dict_ca, autorite)

    def preparer_builder(self, cle_publique_pem: str, sujet: str, duree_cert=ConstantesGenerateurCertificat.DUREE_CERT_BACKUP) -> x509.CertificateBuilder:
        return super().preparer_builder(cle_publique_pem, sujet, duree_cert)

    def _get_keyusage(self, builder):
        builder = super()._get_keyusage(builder)

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ConstantesGenerateurCertificat.ROLE_BACKUP.encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder


class GenerateurCertificatHebergementXS(GenerateurCertificateParRequest):
    """
    Genere un certificat intermediaire par cross-signing avec la millegrille hote.
    """

    def __init__(self, cert: EnveloppeCleCert, autorite: EnveloppeCleCert = None):
        """

        :param cert: Certificat intermediaire existant pour lequel on veut appliquer le cross-signing d'hebergement.
        :param autorite: Certificat intermediaire de la millegrille hote
        """
        idmg = cert.idmg
        super().__init__(idmg, dict_ca=dict(), autorite=autorite)
        self.__cert = cert

    def _preparer_builder_from_csr(self, csr_request, autorite_cert,
                                   duree_cert=ConstantesGenerateurCertificat.DUREE_CERT_TIERS) -> x509.CertificateBuilder:

        builder = x509.CertificateBuilder()
        builder = builder.subject_name(csr_request.subject)   # Conserver le nom de la millegrille hebergee
        builder = builder.issuer_name(autorite_cert.subject)  # Inserer nom de la millegrille hote
        builder = builder.not_valid_before(datetime.datetime.today() - ConstantesGenerateurCertificat.ONE_DAY)
        builder = builder.not_valid_after(datetime.datetime.today() + ConstantesGenerateurCertificat.DUREE_CERT_HERBERGEMENT_XS)
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.public_key(csr_request.public_key())

        return builder

    def _get_keyusage(self, builder):
        # Mettre pathlen=0 pour empecher de generer un CA avec le certificat XS (serait un probleme de securite).
        builder = builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=0),
            critical=True,
        )

        custom_oid_roles = ConstantesGenerateurCertificat.MQ_ROLES_OID
        roles = ConstantesGenerateurCertificat.ROLE_HEBERGEMENT.encode('utf-8')
        builder = builder.add_extension(
            x509.UnrecognizedExtension(custom_oid_roles, roles),
            critical=False
        )

        return builder

    def signer(self, csr=None) -> x509.Certificate:
        cert: x509.Certificate = self.__cert.cert
        key = self.__cert.private_key

        if csr is None:
            csr_builder = x509.CertificateSigningRequestBuilder()
            subject = cert.subject
            csr_builder = csr_builder.subject_name(subject)
            csr = csr_builder.sign(key, hashes.SHA256(), backend=default_backend())

        return super().signer(csr)


class RenouvelleurCertificat:

    def __init__(self, idmg, dict_ca: dict, millegrille: EnveloppeCleCert, ca_autorite: EnveloppeCleCert = None, generer_password=False):
        self.__idmg = idmg
        self.__dict_ca = dict_ca
        self.__millegrille = millegrille
        self.__generer_password = generer_password
        self.__generateurs_par_role = {
            ConstantesGenerateurCertificat.ROLE_FICHIERS: GenererFichiers,
            ConstantesGenerateurCertificat.ROLE_COUPDOEIL: GenererCoupdoeil,
            ConstantesGenerateurCertificat.ROLE_MQ: GenererMQ,
            ConstantesGenerateurCertificat.ROLE_MONGO: GenererMongo,
            ConstantesGenerateurCertificat.ROLE_DOMAINES: GenererDomaines,
            ConstantesGenerateurCertificat.ROLE_TRANSACTIONS: GenererTransactions,
            ConstantesGenerateurCertificat.ROLE_MAITREDESCLES: GenererMaitredescles,
            ConstantesGenerateurCertificat.ROLE_VITRINE: GenererVitrine,
            ConstantesGenerateurCertificat.ROLE_DEPLOYEUR: GenererDeployeur,
            ConstantesGenerateurCertificat.ROLE_CEDULEUR: GenererCeduleur,
            ConstantesGenerateurCertificat.ROLE_MONGOEXPRESS: GenererMongoexpress,
            ConstantesGenerateurCertificat.ROLE_NGINX: GenererNginx,
            ConstantesGenerateurCertificat.ROLE_CONNECTEUR: GenererConnecteur,

            # Monitors de service pour noeuds middleware
            ConstantesGenerateurCertificat.ROLE_MONITOR: GenererMonitor,
            ConstantesGenerateurCertificat.ROLE_MONITOR_DEPENDANT: GenererMonitorDependant,

            # Hebergement
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT: GenerateurCertificatHebergementXS,
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT_TRANSACTIONS: GenererHebergementTransactions,
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT_DOMAINES: GenererHebergementDomaines,
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT_MAITREDESCLES: GenererHebergementMaitredescles,
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT_COUPDOEIL: GenererHebergementCoupdoeil,
            ConstantesGenerateurCertificat.ROLE_HEBERGEMENT_FICHIERS: GenererHebergementFichiers,
        }

        self.__generateur_par_csr = GenerateurCertificateParRequest

        self.__generateur_millegrille = None
        if ca_autorite is not None:
            self.__generateur_millegrille = GenerateurCertificatMilleGrille(idmg, dict_ca, ca_autorite)

        # Permettre de conserver le nouveau cert millegrille en attendant confirmation de l'activation
        self.__clecert_millegrille_nouveau = None

    def renouveller_cert_millegrille(self) -> EnveloppeCleCert:
        if self.__generateur_millegrille is None:
            raise Exception("L'autorite n'est pas disponible pour generer un nouveau cert millegrille")

        clecert = self.__generateur_millegrille.generer()

        # Ajouter a la liste de CAs
        self.__dict_ca[clecert.akid] = clecert.cert

        # Conserver le cert en memoire en attendant confirmation d'activation par le deployeur
        # Permet d'eviter un redemarrage pour charger les nouveaux secrets dans Docker
        self.__clecert_millegrille_nouveau = clecert

        return clecert

    def signer_csr(self, csr_bytes: bytes):
        csr = x509.load_pem_x509_csr(csr_bytes, backend=default_backend())
        sujet_dict = dict()
        for elem in csr.subject:
            sujet_dict[elem.oid._name] = elem.value
        role = sujet_dict['organizationalUnitName']
        common_name = sujet_dict['commonName']

        return self.renouveller_avec_csr(role, common_name, csr_bytes)

    def renouveller_avec_csr(self, role, node_name, csr_bytes: bytes):
        csr = x509.load_pem_x509_csr(csr_bytes, backend=default_backend())

        # Extraire les extensions pour alt names
        # Copier les extensions fournies dans la requete (exemple subject alt names)
        domaines_publics = None
        try:
            subject_alt_names = csr.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            domaines_publics = [d.value for d in subject_alt_names.value]
        except x509.extensions.ExtensionNotFound:
            pass

        generateur = self.__generateurs_par_role[role]
        generateur_instance = generateur(
            self.__idmg, role, node_name, self.__dict_ca, self.__millegrille,
            domaines_publics=domaines_publics
        )

        certificat = generateur_instance.signer(csr)
        chaine = generateur_instance.aligner_chaine(certificat)

        clecert = EnveloppeCleCert(cert=certificat)
        clecert.chaine = chaine

        return clecert

    def signer_noeud(self, csr_bytes: bytes, domaines: list = None):
        csr = x509.load_pem_x509_csr(csr_bytes, backend=default_backend())
        if not csr.is_signature_valid:
            raise ValueError("Signature invalide")

        if domaines is not None:
            generateur = GenerateurCertificateNoeud(self.__idmg, domaines, self.__dict_ca, self.__millegrille)
            certificat = generateur.signer(csr)
            chaine = generateur.aligner_chaine(certificat)
            clecert = EnveloppeCleCert(cert=certificat)
            clecert.chaine = chaine
        else:
            # Verifier si on peut trouver un generateur de certificat
            sujet = csr.subject
            sujet_dict = dict()
            for elem in sujet:
                sujet_dict[elem.oid._name] = elem.value
            role = sujet_dict['organizationalUnitName']
            common_name = sujet_dict['commonName']
            clecert = self.renouveller_avec_csr(role, common_name, csr_bytes)

        return clecert

    def renouveller_par_role(self, role, common_name):
        generateur = self.__generateurs_par_role[role]
        if issubclass(generateur, GenerateurNoeud):
            generateur_instance = generateur(
                self.__idmg, role, common_name, self.__dict_ca, self.__millegrille, generer_password=self.__generer_password)
        else:
            generateur_instance = generateur(
                self.__idmg, role, common_name, self.__dict_ca, self.__millegrille)

        cert_dict = generateur_instance.generer()
        return cert_dict

    def signer_navigateur(self, public_key_pem: str, sujet: str):
        generateur = GenerateurCertificateNavigateur(self.__idmg, self.__dict_ca, self.__millegrille)

        builder = generateur.preparer_builder(public_key_pem, sujet)
        certificat = generateur.signer(builder)
        chaine = generateur.aligner_chaine(certificat)

        clecert = EnveloppeCleCert(cert=certificat)
        clecert.chaine = chaine

        return clecert

    def signer_backup(self, public_key_pem: str, sujet: str):
        generateur = GenerateurCertificatBackup(self.__idmg, self.__dict_ca, self.__millegrille)

        builder = generateur.preparer_builder(public_key_pem, sujet)
        certificat = generateur.signer(builder)
        chaine = generateur.aligner_chaine(certificat)

        clecert = EnveloppeCleCert(cert=certificat)
        clecert.chaine = chaine

        return clecert

    def signer_connecteur_tiers(self, idmg_tiers: str, csr: str):
        generateur = GenerateurCertificatTiers(self.__idmg, idmg_tiers, self.__dict_ca, self.__millegrille)
        csr_instance = x509.load_pem_x509_csr(csr.encode('utf-8'), default_backend())
        certificat = generateur.signer(csr_instance)
        return certificat

    def generer_nouveau_idmg(self):
        generateur = GenerateurInitial(None, None)
        enveloppe_intermediaire = generateur.generer()
        enveloppe_racine = generateur.autorite
        idmg = enveloppe_racine.idmg

        generateur_xs = GenerateurCertificatHebergementXS(enveloppe_intermediaire, autorite=self.__millegrille)
        certificat_xs = generateur_xs.signer()
        enveloppe_hebergement_xs = EnveloppeCleCert(cert=certificat_xs)

        # Generer mots de passe pour les cles de millegrille, intermediaire.
        mot_de_passe_millegrille = enveloppe_racine.password
        mot_de_passe_intermediaire = enveloppe_intermediaire.password

        cle_privee_racine = str(enveloppe_racine.private_key_bytes, 'utf-8')
        cle_privee_intermediaire = str(enveloppe_intermediaire.private_key_bytes, 'utf-8')

        cert_hote = str(self.__millegrille.cert_bytes, 'utf-8')
        cert_racine = str(enveloppe_racine.cert_bytes, 'utf-8')
        cert_intermediaire = str(enveloppe_intermediaire.cert_bytes, 'utf-8')
        cert_hebergement = str(enveloppe_hebergement_xs.cert_bytes, 'utf-8')

        trousseau = {
            'idmg': idmg,
            'millegrille': {
                ConstantesSecurityPki.LIBELLE_CERTIFICAT_PEM: cert_racine,
                'cle': cle_privee_racine,
                'motdepasse': mot_de_passe_millegrille,
                'fingerprint_b64': enveloppe_racine.fingerprint_b64,
            },
            'intermediaire': {
                ConstantesSecurityPki.LIBELLE_CERTIFICAT_PEM: cert_intermediaire,
                'cle': cle_privee_intermediaire,
                'motdepasse': mot_de_passe_intermediaire,
                'fingerprint_b64': enveloppe_intermediaire.fingerprint_b64,
            },
            'hebergement': {
                ConstantesSecurityPki.LIBELLE_CERTIFICAT_PEM: cert_hebergement,
                'hote_pem': cert_hote,
            }
        }

        return trousseau


class DecryptionHelper:

    def __init__(self, clecert: EnveloppeCleCert):
        self.__clecert = clecert

    def decrypter_asymmetrique(self, contenu: str):
        """
        Utilise la cle privee en memoire pour decrypter le contenu.
        :param contenu:
        :return:
        """
        contenu_bytes = base64.b64decode(contenu)

        contenu_decrypte = self.__clecert.private_key.decrypt(
            contenu_bytes,
            asymmetric.padding.OAEP(
                mgf=asymmetric.padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return contenu_decrypte

    def decrypter_symmetrique(self, cle_secrete: bytes, iv: bytes, contenu_crypte: bytes):
        backend = default_backend()

        cipher = Cipher(algorithms.AES(cle_secrete), modes.CBC(iv), backend=backend)
        unpadder = padding.PKCS7(ConstantesSecurityPki.SYMETRIC_PADDING).unpadder()
        decryptor = cipher.decryptor()

        contenu_decrypte = decryptor.update(contenu_crypte) + decryptor.finalize()
        contenu_unpadde = unpadder.update(contenu_decrypte) + unpadder.finalize()

        return contenu_unpadde[16:]  # Enleve 16 premiers bytes, c'est l'IV


class PemHelpers:

    def __init__(self):
        pass

    @staticmethod
    def wrap_public_key(public_key_str: str):
        wrapped_public_key = ''
        while len(public_key_str) > 0:
            wrapped_public_key = wrapped_public_key + '\n' + public_key_str[0:64]
            public_key_str = public_key_str[64:]

        wrapped_public_key = '-----BEGIN PUBLIC KEY-----' + wrapped_public_key + '\n-----END PUBLIC KEY-----'
        return wrapped_public_key

    @staticmethod
    def split_certificats(certs: str):
        END_CERT_VALUE = '-----END CERTIFICATE-----'
        liste_certs = list()
        for cert in certs.split(END_CERT_VALUE):
            if cert and cert.replace('\n', '') != '' and not END_CERT_VALUE in cert:
                liste_certs.append(cert + END_CERT_VALUE + '\n')
        return liste_certs
