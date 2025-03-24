import datetime
import json
import logging
import os
import secrets
import tempfile
from base64 import b64decode, b64encode
from os import path
from typing import cast

import docker
from cryptography import x509
from cryptography.hazmat import primitives
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import asymmetric, hashes

from millegrilles import Constantes
from millegrilles.Constantes import ConstantesServiceMonitor
from millegrilles.monitor.MonitorConstantes import ForcerRedemarrage
# from millegrilles.monitor.ServiceMonitor import DOCKER_LABEL_TIME, GestionnaireModulesDocker
from millegrilles.util.X509Certificate import EnveloppeCleCert, RenouvelleurCertificat, ConstantesGenerateurCertificat, \
    GenerateurInitial, GenerateurCertificat, GenerateurCertificatNginxSelfsigned
from millegrilles.monitor import MonitorConstantes


class GestionnaireCertificats:

    MONITOR_CERT_PATH = 'monitor_cert_path'
    MONITOR_KEY_FILE = 'monitor_key_file'

    def __init__(self, docker_client: docker.DockerClient, service_monitor, **kwargs):
        self._docker = docker_client
        self._service_monitor = service_monitor
        self._date: str = cast(str, None)
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        self.certificats = dict()
        self._clecert_millegrille: EnveloppeCleCert = cast(EnveloppeCleCert, None)
        self._clecert_intermediaire: EnveloppeCleCert = cast(EnveloppeCleCert, None)
        self.clecert_monitor: EnveloppeCleCert = cast(EnveloppeCleCert, None)

        self.secret_path = kwargs.get('secrets')
        self._mode_insecure = kwargs.get('insecure') or False

        self.maj_date()

        self._nodename = self._docker.info()['Name']
        self.idmg: str = cast(str, None)

        self.__cles_memorisees = dict()

        cert_pem = kwargs.get('millegrille_cert_pem')
        if cert_pem:
            self._clecert_millegrille = EnveloppeCleCert()
            self._clecert_millegrille.cert_from_pem_bytes(cert_pem.encode('utf-8'))
        else:
            # Tenter de charger le certificat a partir de millegrille.configuration
            try:
                config = self._docker.configs.get('millegrille.configuration')
                config_json = json.loads(b64decode(config.attrs['Spec']['Data']))

                millegrille_pem_config = self._docker.configs.get('pki.millegrille.cert')
                json_millegrille = b64decode(millegrille_pem_config.attrs['Spec']['Data'])
                self._clecert_millegrille = EnveloppeCleCert()
                self._clecert_millegrille.cert_from_pem_bytes(json_millegrille)

            except docker.errors.NotFound:
                self.__logger.info("millegrille.configuration abstente : Nouvelle MilleGrille, noeud principal.")

        # Calculer le IDMG a partir du certificat de MilleGrille
        if self._clecert_millegrille:
            self.idmg = self._clecert_millegrille.idmg
            self.__logger.info("Gestionnaire certificat, idmg : %s" % self.idmg)

    def maj_date(self):
        self._date = str(datetime.datetime.utcnow().strftime(MonitorConstantes.DOCKER_LABEL_TIME))

    def __preparer_label(self, name, date: str = None):
        if date is None:
            date = self._date
        params = {
            'name': name,
            'date': date,
        }
        name_docker = '%(name)s.%(date)s' % params
        return name_docker[0:64]  # Max 64 chars pour name docker

    def ajouter_config(self, name: str, data: bytes, date: str = None):
        name_tronque = self.__preparer_label(name, date)
        self._docker.configs.create(name=name_tronque, data=data, labels={'idmg': self.idmg})

    def ajouter_secret(self, name: str, data: bytes):
        name_tronque = self.__preparer_label(name)
        self._docker.secrets.create(name=name_tronque, data=data, labels={'idmg': self.idmg})
        return name_tronque

    def __generer_private_key(self, generer_password=False, keysize=2048, public_exponent=65537):
        info_cle = dict()
        clecert = EnveloppeCleCert()
        clecert.generer_private_key(generer_password=generer_password)
        if generer_password:
            # info_cle['password'] = b64encode(secrets.token_bytes(16))
            info_cle['password'] = clecert.password

        # info_cle['cle'] = asymmetric.rsa.generate_private_key(
        #     public_exponent=public_exponent,
        #     key_size=keysize,
        #     backend=default_backend()
        # )

        info_cle['pem'] = clecert.private_key_bytes
        info_cle['clecert'] = clecert
        info_cle['cle'] = clecert.private_key

        return info_cle

    def generer_csr(self, type_cle: str = None, insecure=False, inserer_cle=True, generer_password=False):
        # Generer cle privee
        info_cle = self.__generer_private_key(generer_password=generer_password)

        # Generer CSR
        # node_name = self._docker.info()['Name']
        noeud_id = self._service_monitor.noeud_id
        builder = x509.CertificateSigningRequestBuilder()

        name_list = list()
        if type_cle:
            name_list.append(x509.NameAttribute(x509.name.NameOID.ORGANIZATIONAL_UNIT_NAME, type_cle))
        name_list.append(x509.NameAttribute(x509.name.NameOID.COMMON_NAME, noeud_id))

        if self.idmg:
            name_list.append(x509.NameAttribute(x509.name.NameOID.OID_ORGANIZATION_NAME, self.idmg))
        name = x509.Name(name_list)
        builder = builder.subject_name(name)

        request = builder.sign(
            info_cle['cle'], hashes.SHA256(), default_backend()
        )
        request_pem = request.public_bytes(primitives.serialization.Encoding.PEM)
        info_cle['request'] = request_pem
        info_cle['cle_pem'] = info_cle['pem']

        self.__logger.debug("Request CSR : %s" % request_pem)

        cle_pem = info_cle['cle_pem']
        cle_passwd = info_cle.get('password')

        if inserer_cle:
            label_key_inter = 'pki.%s.key' % type_cle
            self.ajouter_secret(label_key_inter, data=cle_pem)
            if cle_passwd:
                label_passwd_inter = 'pki.%s.passwd' % type_cle
                self.ajouter_secret(label_passwd_inter, data=cle_passwd)
            label_csr_inter = 'pki.%s.csr' % type_cle
            self.ajouter_config(label_csr_inter, data=request_pem)

        if insecure:  # Mode insecure
            try:
                os.mkdir(self.secret_path, 0o755)
            except FileExistsError:
                pass

            key_path = path.join(self.secret_path, 'pki.%s.key.pem' % type_cle)
            try:
                with open(key_path, 'xb') as fichier:
                    fichier.write(cle_pem)
            except FileExistsError:
                pass

            if cle_passwd:
                passwd_path = path.join(self.secret_path, 'pki.%s.passwd.txt' % type_cle)
                try:
                    with open(passwd_path, 'xb') as fichier:
                        fichier.write(cle_passwd)
                except FileExistsError:
                    pass

        return info_cle

    def _charger_certificat_docker(self, nom_certificat) -> bytes:
        """
        Extrait un certificat de la config docker vers un fichier temporaire.
        Conserve le nom du fichier dans self.__certificats.
        :param nom_certificat:
        :return: Contenu du certificat en PEM
        """
        cert = MonitorConstantes.trouver_config(nom_certificat, self._docker)['config']
        cert_pem = b64decode(cert.attrs['Spec']['Data'])
        fp, fichier_cert = tempfile.mkstemp(dir='/tmp')
        try:
            os.write(fp, cert_pem)
            self.certificats[nom_certificat] = fichier_cert
        finally:
            os.close(fp)

        return cert_pem

    def recevoir_certificat(self, message: dict):
        self.__logger.info("Certificat recu :\n%s" % json.dumps(message, indent=2))
        chaines = message.get('chaines') or message['resultats']['chaines']

        for info_chaine in chaines['chaines']:
            pems = info_chaine['pems']

            # Identifier le role du certificat (OU)
            self.traiter_reception_certificat(pems)

        self._service_monitor.trigger_event_attente()

    def traiter_reception_certificat(self, pems):
        cert = pems[0]
        clecert = EnveloppeCleCert()
        clecert.cert_from_pem_bytes(cert.encode('utf-8'))
        subject_dict = clecert.formatter_subject()
        role = subject_dict['organizationalUnitName']

        # Trouver cle correspondante (date)
        label_role_cert = 'pki.%s.cert' % role
        label_role_key = 'pki.%s.key' % role
        info_role_key = self._service_monitor.gestionnaire_docker.trouver_secret(label_role_key)
        date_key = info_role_key['date']

        # Inserer la chaine de certificat
        chaine = '\n'.join(pems)
        self._service_monitor.gestionnaire_certificats.ajouter_config(label_role_cert, chaine, date_key)

    @property
    def idmg_tronque(self):
        return self.idmg[0:12]

    def memoriser_cle(self, role, cle_pem):
        self.__cles_memorisees[role] = cle_pem

    def _recuperer_cle_memorisee(self, role):
        cle = self.__cles_memorisees[role]
        del self.__cles_memorisees[role]
        return cle

    def set_clecert_millegrille(self, clecert_millegrille):
        self._clecert_millegrille = clecert_millegrille

    def set_clecert_intermediaire(self, clecert_intermediaire):
        self._clecert_intermediaire = clecert_intermediaire

    def charger_certificats(self):
        raise NotImplementedError()

    def generer_nouveau_idmg(self):
        raise NotImplementedError()

    def generer_clecert_module(self, role: str, node_name: str, nomcle: str = None) -> EnveloppeCleCert:
        raise NotImplementedError()


class GestionnaireCertificatsNoeudPrive(GestionnaireCertificats):

    def __init__(self, docker_client: docker.DockerClient, service_monitor, **kwargs):
        super().__init__(docker_client, service_monitor, **kwargs)
        self._passwd_mq: str = cast(str, None)

    def charger_certificats(self):
        secret_path = path.abspath(self.secret_path)
        os.makedirs(secret_path, exist_ok=True)  # Creer path secret, au besoin

        # Charger information certificat monitor
        cert_pem = self._charger_certificat_docker('pki.monitor.cert')
        with open(path.join(secret_path, 'pki.monitor.key.pem'), 'rb') as fichiers:
            key_pem = fichiers.read()
        clecert_monitor = EnveloppeCleCert()
        clecert_monitor.from_pem_bytes(key_pem, cert_pem)
        self.clecert_monitor = clecert_monitor

        # Conserver reference au cert monitor pour middleware
        self.certificats[GestionnaireCertificats.MONITOR_CERT_PATH] = self.certificats['pki.monitor.cert']
        self.certificats[GestionnaireCertificats.MONITOR_KEY_FILE] = 'pki.monitor.key.pem'

        # with open(path.join(secret_path, ConstantesServiceMonitor.FICHIER_MONGO_MOTDEPASSE), 'r') as fichiers:
        #     self._passwd_mongo = fichiers.read()
        # with open(path.join(secret_path, ConstantesServiceMonitor.FICHIER_MQ_MOTDEPASSE), 'r') as fichiers:
        #     self._passwd_mq = fichiers.read()

        # Charger le certificat de millegrille
        self._charger_certificat_docker('pki.millegrille.cert')

    def generer_motsdepasse(self):
        """
        Genere les mots de passes pour composants internes de middleware
        :return:
        """
        pass  # Aucun mot de passe prive


class GestionnaireCertificatsNoeudProtegeDependant(GestionnaireCertificatsNoeudPrive):

    def __init__(self, docker_client: docker.DockerClient, service_monitor, **kwargs):
        super().__init__(docker_client, service_monitor, **kwargs)
        self._passwd_mongo: str = cast(str, None)
        self._passwd_mongoxp: str = cast(str, None)

        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

    def generer_motsdepasse(self):
        """
        Genere les mots de passes pour composants internes de middleware
        :return:
        """
        super().generer_motsdepasse()

        passwd_mq = b64encode(secrets.token_bytes(32)).replace(b'=', b'')
        self._passwd_mq = str(passwd_mq, 'utf-8')
        label_passwd_mq = 'passwd.mq.' + self._date
        self._docker.secrets.create(name=label_passwd_mq, data=passwd_mq, labels={'millegrille': self.idmg})

        passwd_mongo = b64encode(secrets.token_bytes(32)).replace(b'=', b'')
        self.ajouter_secret('passwd.mongo', passwd_mongo)
        self._passwd_mongo = str(passwd_mongo, 'utf-8')

        passwd_mongoxpweb = b64encode(secrets.token_bytes(24)).replace(b'=', b'')
        self.ajouter_secret('passwd.mongoxpweb', passwd_mongoxpweb)
        self._passwd_mongoxp = str(passwd_mongoxpweb, 'utf-8')

        if self._mode_insecure:
            try:
                os.mkdir('/var/opt/millegrilles/secrets', 0o755)
            except FileExistsError:
                pass

            with open('/var/opt/millegrilles/secrets/passwd.mongo.txt', 'w') as fichiers:
                fichiers.write(self._passwd_mongo)
            with open('/var/opt/millegrilles/secrets/passwd.mongoxpweb.txt', 'w') as fichiers:
                fichiers.write(self._passwd_mongoxp)

            try:
                os.mkdir('/var/opt/millegrilles/secrets', 0o700)
            except FileExistsError:
                pass

            with open('/var/opt/millegrilles/secrets/passwd.mq.txt', 'w') as fichiers:
                fichiers.write(self._passwd_mq)

    def charger_certificats(self):
        secret_path = path.abspath(self.secret_path)

        # Charger mots de passes middleware
        with open(path.join(secret_path, ConstantesServiceMonitor.FICHIER_MONGO_MOTDEPASSE), 'r') as fichiers:
            self._passwd_mongo = fichiers.read()
        with open(path.join(secret_path, ConstantesServiceMonitor.FICHIER_MQ_MOTDEPASSE), 'r') as fichiers:
            self._passwd_mq = fichiers.read()

        # Charger information certificat monitor
        clecert_monitor = EnveloppeCleCert()
        with open(path.join(secret_path, 'pki.monitor_dependant.key.pem'), 'rb') as fichiers:
            key_pem = fichiers.read()
        try:
            cert_pem = self._charger_certificat_docker('pki.monitor_dependant.cert')
            clecert_monitor.from_pem_bytes(key_pem, cert_pem)

            # Conserver reference au cert monitor
            self.certificats[GestionnaireCertificats.MONITOR_CERT_PATH] = self.certificats['pki.monitor_dependant.cert']
            self.certificats[GestionnaireCertificats.MONITOR_KEY_FILE] = 'pki.monitor_dependant.key.pem'

        except AttributeError:
            self.__logger.info("Certificat monitor_dependant non trouve, on va l'attendre")
            clecert_monitor.key_from_pem_bytes(key_pem)

        self.clecert_monitor = clecert_monitor

        # Charger le certificat de millegrille, chaine pour intermediaire
        self._charger_certificat_docker('pki.millegrille.cert')

    def traiter_reception_certificat(self, pems):
        cert = pems[0]
        clecert = EnveloppeCleCert()
        clecert.cert_from_pem_bytes(cert.encode('utf-8'))
        subject_dict = clecert.formatter_subject()
        role = subject_dict['organizationalUnitName']

        if role == 'mongo':
            # Pour MongoDB on insere la cle (en memoire) et le nouveau certificat dans le meme secret (une key_cert)
            label_role_cert = 'pki.%s.cert' % role
            label_role_key = 'pki.%s.key' % role

            chaine = '\n'.join(pems)
            cle_mongo = self._recuperer_cle_memorisee(role)  # Note : efface la cle en memoire
            if not cle_mongo:
                raise ValueError("Cle mongo n'est pas presente en memoire")
            key_cert = str(cle_mongo, 'utf-8') + '\n' + chaine

            # Inserer la chaine de certificat
            nom_cle = self._service_monitor.gestionnaire_certificats.ajouter_secret(label_role_key, key_cert)
            date_key = nom_cle.split('.')[-1]
            self._service_monitor.gestionnaire_certificats.ajouter_config(label_role_cert, chaine, date_key)
        else:
            super().traiter_reception_certificat(pems)


class GestionnaireCertificatsNoeudProtegePrincipal(GestionnaireCertificatsNoeudProtegeDependant):

    def __init__(self, docker_client: docker.DockerClient, service_monitor, **kwargs):
        super().__init__(docker_client, service_monitor, **kwargs)
        self.__renouvelleur: RenouvelleurCertificat = cast(RenouvelleurCertificat, None)
        self._clecert_intermediaire: EnveloppeCleCert = cast(EnveloppeCleCert, None)

    def generer_clecert_module(self, role: str, common_name: str, nomcle: str = None) -> EnveloppeCleCert:
        if nomcle is None:
            nomcle = role

        clecert = self.__renouvelleur.renouveller_par_role(role, common_name)
        chaine = list(clecert.chaine)
        chaine_certs = '\n'.join(chaine)

        secret = clecert.private_key_bytes

        # Verifier si on doit combiner le cert et la cle (requis pour Mongo)
        if role in [ConstantesGenerateurCertificat.ROLE_MONGO, ConstantesGenerateurCertificat.ROLE_MONGOEXPRESS]:
            secret_str = [str(secret, 'utf-8')]
            secret_str.extend(clecert.chaine)
            secret = '\n'.join(secret_str).encode('utf-8')

        self.ajouter_secret('pki.%s.key' % nomcle, secret)
        self.ajouter_config('pki.%s.cert' % nomcle, chaine_certs.encode('utf-8'))

        return clecert

    def charger_certificats(self):
        secret_path = path.abspath(self.secret_path)
        os.makedirs(secret_path, exist_ok=True)  # Creer path secret, au besoin

        # Charger information certificat intermediaire
        cert_pem = self._charger_certificat_docker('pki.intermediaire.cert')
        with open(path.join(secret_path, 'pki.intermediaire.key.pem'), 'rb') as fichiers:
            key_pem = fichiers.read()
        with open(path.join(secret_path, 'pki.intermediaire.passwd.txt'), 'rb') as fichiers:
            passwd_bytes = fichiers.read()

        clecert_intermediaire = EnveloppeCleCert()
        clecert_intermediaire.from_pem_bytes(key_pem, cert_pem, passwd_bytes)
        clecert_intermediaire.password = None  # Effacer mot de passe
        self._clecert_intermediaire = clecert_intermediaire

        # Charger information certificat monitor
        cert_pem = self._charger_certificat_docker('pki.monitor.cert')
        with open(path.join(secret_path, 'pki.monitor.key.pem'), 'rb') as fichiers:
            key_pem = fichiers.read()
        clecert_monitor = EnveloppeCleCert()
        clecert_monitor.from_pem_bytes(key_pem, cert_pem)
        self.clecert_monitor = clecert_monitor

        # Conserver reference au cert monitor pour middleware
        self.certificats[GestionnaireCertificats.MONITOR_CERT_PATH] = self.certificats['pki.monitor.cert']
        self.certificats[GestionnaireCertificats.MONITOR_KEY_FILE] = 'pki.monitor.key.pem'

        # with open(path.join(secret_path, ConstantesServiceMonitor.FICHIER_MONGO_MOTDEPASSE), 'r') as fichiers:
        #     self._passwd_mongo = fichiers.read()
        # with open(path.join(secret_path, ConstantesServiceMonitor.FICHIER_MQ_MOTDEPASSE), 'r') as fichiers:
        #     self._passwd_mq = fichiers.read()

        # Charger le certificat de millegrille, chaine pour intermediaire
        self._charger_certificat_docker('pki.intermediaire.chain')
        self._charger_certificat_docker('pki.millegrille.cert')

        self.__charger_renouvelleur()

    def __charger_renouvelleur(self):
        dict_ca = {
            self._clecert_intermediaire.skid: self._clecert_intermediaire.cert,
            self._clecert_millegrille.skid: self._clecert_millegrille.cert,
        }

        self.__renouvelleur = RenouvelleurCertificat(self.idmg, dict_ca, self._clecert_intermediaire, generer_password=False)

    def preparer_repertoires(self):
        mounts = path.join('/var/opt/millegrilles', self.idmg, 'mounts')
        os.makedirs(mounts, mode=0o770)

    def generer_nouveau_idmg(self) -> str:
        """
        Generer nouveau trousseau de MilleGrille, incluant cle/cert de MilleGrille, intermediaire et monitor.
        Insere les entrees de configs et secrets dans docker.
        :return: idmg
        """
        generateur_initial = GenerateurInitial(None)
        clecert_intermediaire = generateur_initial.generer()
        clecert_millegrille = generateur_initial.autorite

        self._clecert_millegrille = clecert_millegrille
        self._clecert_intermediaire = clecert_intermediaire
        self.idmg = clecert_millegrille.idmg

        # Preparer repertoires locaux pour le noeud
        self.preparer_repertoires()

        # Conserver la configuration de base pour ServiceMonitor
        configuration = {
            Constantes.CONFIG_IDMG: self.idmg,
            'pem': str(clecert_millegrille.cert_bytes, 'utf-8'),
            Constantes.DOCUMENT_INFODOC_SECURITE: '3.protege',
        }
        configuration_bytes = json.dumps(configuration).encode('utf-8')
        self._docker.configs.create(name='millegrille.configuration', data=configuration_bytes, labels={'idmg': self.idmg})

        # Sauvegarder certificats, cles et mots de passe dans docker
        self.ajouter_secret(ConstantesServiceMonitor.DOCKER_CONFIG_MILLEGRILLE_KEY, clecert_millegrille.private_key_bytes)
        self.ajouter_secret(ConstantesServiceMonitor.DOCKER_CONFIG_MILLEGRILLE_PASSWD, clecert_millegrille.password)
        self.ajouter_config(ConstantesServiceMonitor.DOCKER_CONFIG_MILLEGRILLE_CERT, clecert_millegrille.cert_bytes)

        chaine_certs = '\n'.join(clecert_intermediaire.chaine).encode('utf-8')
        self.ajouter_secret(ConstantesServiceMonitor.DOCKER_CONFIG_INTERMEDIAIRE_KEY, clecert_intermediaire.private_key_bytes)
        self.ajouter_secret(ConstantesServiceMonitor.DOCKER_CONFIG_INTERMEDIAIRE_PASSWD, clecert_intermediaire.password)
        self.ajouter_config(ConstantesServiceMonitor.DOCKER_CONFIG_INTERMEDIAIRE_CERT, clecert_intermediaire.cert_bytes)
        self.ajouter_config(ConstantesServiceMonitor.DOCKER_CONFIG_INTERMEDIAIRE_CHAIN, chaine_certs)

        # Initialiser le renouvelleur de certificats avec le nouveau trousseau
        self.__charger_renouvelleur()

        # Generer certificat pour monitor
        self.clecert_monitor = self.generer_clecert_module(ConstantesGenerateurCertificat.ROLE_MONITOR, self._nodename)

        if self._mode_insecure:
            self.sauvegarder_secrets()

        # Generer mots de passes
        self.generer_motsdepasse()

        return self.idmg

    def sauvegarder_secrets(self):
        """
        Sauvegarder le certificat de millegrille sous 'args.secrets' - surtout utilise pour dev (insecure)
        :return:
        """
        secret_path = path.abspath(self.secret_path)
        os.makedirs(secret_path, exist_ok=True)  # Creer path secret, au besoin

        # Sauvegarder information certificat intermediaire
        with open(path.join(secret_path, ConstantesServiceMonitor.DOCKER_CONFIG_MILLEGRILLE_KEY + '.pem'), 'wb') as fichiers:
            fichiers.write(self._clecert_millegrille.private_key_bytes)
        with open(path.join(secret_path, ConstantesServiceMonitor.DOCKER_CONFIG_MILLEGRILLE_PASSWD + '.txt'), 'wb') as fichiers:
            fichiers.write(self._clecert_millegrille.password)

        # Sauvegarder information certificat intermediaire
        with open(path.join(secret_path, ConstantesServiceMonitor.DOCKER_CONFIG_INTERMEDIAIRE_KEY + '.pem'), 'wb') as fichiers:
            fichiers.write(self._clecert_intermediaire.private_key_bytes)
        with open(path.join(secret_path, ConstantesServiceMonitor.DOCKER_CONFIG_INTERMEDIAIRE_PASSWD + '.txt'), 'wb') as fichiers:
            fichiers.write(self._clecert_intermediaire.password)

        # Sauvegarder information certificat monitor
        with open(path.join(secret_path, ConstantesServiceMonitor.DOCKER_CONFIG_MONITOR_KEY + '.pem'), 'wb') as fichiers:
            fichiers.write(self.clecert_monitor.private_key_bytes)


class GestionnaireCertificatsInstallation(GestionnaireCertificats):

    def __init__(self, docker_client: docker.DockerClient, service_monitor, **kwargs):
        super().__init__(docker_client, service_monitor, **kwargs)
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

    def preparer_repertoires(self):
        mounts = path.join('/var/opt/millegrilles', self.idmg, 'mounts')
        os.makedirs(mounts, mode=0o770)

        if self._mode_insecure:
            try:
                os.mkdir('/var/opt/millegrilles/secrets', 0o755)
            except FileExistsError:
                pass

    def signer_csr(self, csr: bytes):
        generateur = RenouvelleurCertificat(self.idmg, dict(), self._clecert_intermediaire, ca_autorite=self._clecert_millegrille)
        clecert = generateur.signer_csr(csr)
        return clecert

    def generer_certificat_nginx_selfsigned(self, insecure=False):
        """
        Utilise pour genere un certificat self-signed initial pour nginx
        :return:
        """
        generateur = GenerateurCertificatNginxSelfsigned()
        clecert = generateur.generer('nanana')

        cle_pem_bytes = clecert.private_key_bytes

        self.ajouter_secret('pki.nginx.key', data=cle_pem_bytes)
        self.ajouter_config('pki.nginx.cert', data=clecert.public_bytes)

        if insecure:  # Mode insecure
            key_path = path.join(self.secret_path, 'pki.nginx.key.pem')
            try:
                with open(key_path, 'xb') as fichier:
                    fichier.write(cle_pem_bytes)
            except FileExistsError:
                pass

        return clecert
