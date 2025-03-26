import argparse
import signal
import logging
import sys
import docker
import json
import datetime
import os
import psutil
import tarfile
import io

from typing import cast, Optional
from threading import Event, BrokenBarrierError
from docker.errors import APIError
from base64 import b64decode

from millegrilles import Constantes
from millegrilles.Constantes import ConstantesServiceMonitor
from millegrilles.monitor.MonitorCertificats import GestionnaireCertificats, \
    GestionnaireCertificatsNoeudProtegeDependant, GestionnaireCertificatsNoeudProtegePrincipal, \
    GestionnaireCertificatsInstallation, GestionnaireCertificatsNoeudPrive
from millegrilles.monitor.MonitorCommandes import GestionnaireCommandes, GestionnaireCommandesNoeudProtegeDependant
from millegrilles.monitor.MonitorComptes import GestionnaireComptesMQ
from millegrilles.monitor.MonitorConstantes import ForcerRedemarrage
from millegrilles.monitor.MonitorDocker import GestionnaireModulesDocker
from millegrilles.monitor.MonitorRelaiMessages import ConnexionPrincipal, ConnexionMiddleware
from millegrilles.monitor.MonitorNetworking import GestionnaireWeb
from millegrilles.util.X509Certificate import EnveloppeCleCert, \
    ConstantesGenerateurCertificat
from millegrilles.dao.Configuration import TransactionConfiguration
from millegrilles.monitor import MonitorConstantes
from millegrilles.monitor.MonitorApplications import GestionnaireApplications
from millegrilles.monitor.MonitorWebAPI import ServerWebAPI
from millegrilles.monitor.MonitorMdns import MdnsGestionnaire


class InitialiserServiceMonitor:

    def __init__(self):
        self.__docker: docker.DockerClient = cast(docker.DockerClient, None)  # Client docker
        self.__args = None
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        self._configuration_json = None

    def __parse(self):
        parser = argparse.ArgumentParser(description="Service Monitor de MilleGrilles")

        parser.add_argument(
            '--debug', action="store_true", required=False,
            help="Active le debugging (tres verbose)"
        )

        parser.add_argument(
            '--info', action="store_true", required=False,
            help="Afficher davantage de messages (verbose)"
        )

        parser.add_argument(
            '--dev', action="store_true", required=False,
            help="Active des options de developpement (insecure)"
        )

        parser.add_argument(
            '--secrets', type=str, required=False, default="/run/secrets",
            help="Repertoire de secrets"
        )

        parser.add_argument(
            '--configs', type=str, required=False, default="/etc/opt/millegrille",
            help="Repertoire de configuration"
        )

        parser.add_argument(
            '--securite', type=str, required=False, default='protege',
            choices=['prive', 'protege', 'secure'],
            help="Niveau de securite du noeud. Defaut = protege"
        )

        parser.add_argument(
            '--docker', type=str, required=False, default='/run/docker.sock',
            help="Path du pipe docker"
        )

        parser.add_argument(
            '--pipe', type=str, required=False, default=MonitorConstantes.PATH_FIFO,
            help="Path du pipe de controle du ServiceMonitor"
        )

        parser.add_argument(
            '--config', type=str, required=False, default='/etc/opt/millegrilles/servicemonitor.json',
            help="Path du fichier de configuration de l'hote MilleGrilles"
        )

        parser.add_argument(
            '--data', type=str, required=False, default='/var/opt/millegrilles',
            help="Path du repertoire data de toutes les MilleGrilles"
        )

        parser.add_argument(
            '--webroot', type=str, required=False, default='/var/opt/millegrilles/installation',
            help="Path du webroot de l'installeur"
        )

        self.__args = parser.parse_args()

        # Appliquer args
        if self.__args.debug:
            logging.getLogger('__main__').setLevel(logging.DEBUG)
            logging.getLogger('millegrilles').setLevel(logging.DEBUG)
            self.__logger.setLevel(logging.DEBUG)
        elif self.__args.info:
            logging.getLogger('__main__').setLevel(logging.INFO)
            logging.getLogger('millegrilles').setLevel(logging.INFO)

        self.__logger.info("Arguments: %s", self.__args)

    def __connecter_docker(self):
        self.__docker = docker.DockerClient('unix://' + self.__args.docker)
        # self.__logger.debug("Docker info: %s", str(self.__docker.info()))

        self.__nodename = self.__docker.info()['Name']
        self.__logger.debug("Docker node name: %s", self.__nodename)

        self.__logger.debug("--------------")
        self.__logger.debug("Docker configs")
        self.__logger.debug("--------------")
        for config in self.__docker.configs.list():
            self.__logger.debug("  %s", str(config.name))

        self.__logger.debug("--------------")
        self.__logger.debug("Docker secrets")
        self.__logger.debug("--------------")
        for secret in self.__docker.secrets.list():
            self.__logger.debug("  %s", str(secret.name))

        self.__logger.debug("--------------")
        self.__logger.debug("Docker services")
        self.__logger.debug("--------------")
        for service in self.__docker.services.list():
            self.__logger.debug("  %s", str(service.name))

        self.__logger.debug("--------------")

    def detecter_type_noeud(self):
        self.__parse()
        self.__connecter_docker()

        try:
            config_item = self.__docker.configs.get('millegrille.configuration')
            configuration = json.loads(b64decode(config_item.attrs['Spec']['Data']))
            self._configuration_json = configuration
            self.__logger.debug("Configuration millegrille : %s" % configuration)

            specialisation = configuration.get('specialisation')
            securite = configuration.get('securite')
            if securite == '1.public':
                self.__logger.error("Noeud public, non supporte")
                raise ValueError("Noeud de type non reconnu")
            elif securite == '2.prive':
                self.__logger.error("Noeud prive, non supporte")
                raise ValueError("Noeud de type non reconnu")
            elif securite == '3.protege' and specialisation == 'dependant':
                service_monitor_classe = ServiceMonitorDependant
            elif securite == '3.protege' and specialisation == 'extension':
                self.__logger.error("Noeud d'extension, non supporte")
                service_monitor_classe = ServiceMonitorExtension
            elif securite == '3.protege' and specialisation == 'principal':
                service_monitor_classe = ServiceMonitorPrincipal
            elif securite == '3.protege':
                service_monitor_classe = ServiceMonitorPrincipal
            else:
                raise ValueError("Noeud de type non reconnu")
        except docker.errors.NotFound:
            self.__logger.info("Config millegrille.configuration n'existe pas, le noeud est demarre en mode d'installation")
            service_monitor_classe = ServiceMonitorInstalleur

        return service_monitor_classe

    def demarrer(self):
        class_noeud = self.detecter_type_noeud()
        service_monitor = class_noeud(self.__args, self.__docker, self._configuration_json)
        service_monitor.run()


class ServiceMonitor:
    """
    Service deploye dans un swarm docker en mode global qui s'occupe du deploiement des autres modules de la
    MilleGrille et du renouvellement des certificats. S'occupe de configurer les comptes RabbitMQ et MongoDB.

    Supporte aussi les MilleGrilles hebergees par l'hote.
    """

    def __init__(self, args, docker_client: docker.DockerClient, configuration_json: dict):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        self._args = args                                       # Arguments de la ligne de commande
        self._docker: docker.DockerClient = docker_client       # Client docker
        self._configuration_json = configuration_json           # millegrille.configuration dans docker

        self._securite: str = cast(str, None)                   # Niveau de securite de la swarm docker
        self._connexion_middleware: ConnexionMiddleware = cast(ConnexionMiddleware, None)  # Connexion a MQ, MongoDB
        self._noeud_id: Optional[str] = None                    # UUID du noeud
        self._idmg: str = cast(str, None)                       # IDMG de la MilleGrille hote

        self._socket_fifo = None  # Socket FIFO pour les commandes

        self._fermeture_event = Event()
        self._attente_event = Event()

        self._gestionnaire_certificats: GestionnaireCertificats = cast(GestionnaireCertificats, None)
        self._gestionnaire_docker: GestionnaireModulesDocker = cast(GestionnaireModulesDocker, None)
        self._gestionnaire_mq: GestionnaireComptesMQ = cast(GestionnaireComptesMQ, None)
        self._gestionnaire_commandes: GestionnaireCommandes = cast(GestionnaireCommandes, None)
        self._gestionnaire_web: GestionnaireWeb = cast(GestionnaireWeb, None)
        self._gestionnaire_applications: GestionnaireApplications = cast(GestionnaireApplications, None)
        self._gestionnaire_mdns: MdnsGestionnaire = cast(MdnsGestionnaire, None)

        self._web_api: ServerWebAPI = cast(ServerWebAPI, None)

        self.limiter_entretien = True

        self._nodename = self._docker.info()['Name']            # Node name de la connexion locale dans Docker

        # Gerer les signaux OS, permet de deconnecter les ressources au besoin
        signal.signal(signal.SIGINT, self.fermer)
        signal.signal(signal.SIGTERM, self.fermer)

        self.exit_code = 0

    def fermer(self, signum=None, frame=None):
        if signum:
            self.__logger.warning("Fermeture ServiceMonitor, signum=%d", signum)
        if not self._fermeture_event.is_set():
            self._fermeture_event.set()
            self._attente_event.set()
            try:
                self._gestionnaire_mdns.fermer()
            except Exception as mdnse:
                if self.__logger.isEnabledFor(logging.DEBUG):
                    self.__logger.exception('Erreur fermeture mdns')
                else:
                    self.__logger.info("Erreur fermeture mdns : %s", str(mdnse))

            try:
                self._web_api.server_close()
            except Exception:
                self.__logger.debug("Erreur fermeture web_api")
                if self.__logger.isEnabledFor(logging.DEBUG):
                    self.__logger.exception('Erreur fermeture Web API')

            try:
                self._connexion_middleware.stop()
            except Exception:
                pass

            try:
                self._docker.close()
            except Exception:
                pass

            try:
                self._gestionnaire_docker.fermer()
            except Exception:
                pass

            # Cleanup fichiers temporaires de certificats/cles
            try:
                for fichier in self._gestionnaire_certificats.certificats.values():
                    os.remove(fichier)
            except Exception:
                pass

            try:
                if self._gestionnaire_commandes:
                    self._gestionnaire_commandes.stop()
            except Exception:
                self.__logger.exception("Erreur fermeture gestionnaire commandes")

            try:
                os.remove(MonitorConstantes.PATH_FIFO)
            except Exception:
                pass

    def connecter_middleware(self):
        """
        Genere un contexte et se connecte a MQ et MongoDB.
        Lance une thread distincte pour s'occuper des messages.
        :return:
        """
        configuration = TransactionConfiguration()

        self._connexion_middleware = ConnexionMiddleware(
            configuration, self._docker, self, self._gestionnaire_certificats.certificats,
            secrets=self._args.secrets)

        try:
            self._connexion_middleware.initialiser()
            self._connexion_middleware.start()
        except TypeError as te:
            self.__logger.exception("Erreur fatale configuration MQ, abandonner")
            self.fermer()
            raise te
        except BrokenBarrierError:
            self.__logger.warning("Erreur connexion MQ, on va reessayer plus tard")
            self._connexion_middleware.stop()
            self._connexion_middleware = None

    def preparer_gestionnaire_certificats(self):
        raise NotImplementedError()

    def preparer_gestionnaire_comptesmq(self):
        mode_insecure = self._args.dev
        path_secrets = self._args.secrets
        self._gestionnaire_mq = GestionnaireComptesMQ(
            self._idmg, self._gestionnaire_certificats.clecert_monitor, self._gestionnaire_certificats.certificats,
            host=self._nodename, secrets=path_secrets, insecure=mode_insecure
        )

    def preparer_gestionnaire_commandes(self):
        try:
            os.mkfifo(self._args.pipe)
        except FileExistsError:
            self.__logger.debug("Pipe %s deja cree", self._args.pipe)

        os.chmod(MonitorConstantes.PATH_FIFO, 0o620)

        # Verifier si on doit creer une instance (utilise pour override dans sous-classe)
        if self._gestionnaire_commandes is None:
            self._gestionnaire_commandes = GestionnaireCommandes(self._fermeture_event, self)

        self._gestionnaire_commandes.start()

    def preparer_gestionnaire_applications(self):
        if not self._gestionnaire_applications:
            self._gestionnaire_applications = GestionnaireApplications(
                self,
                self._gestionnaire_docker
            )

    def preparer_web_api(self):
        self._web_api = ServerWebAPI(self, webroot=self._args.webroot)
        self._web_api.start()

    def preparer_mdns(self):
        self._gestionnaire_mdns = MdnsGestionnaire(self)

    def _charger_configuration(self):
        # classe_configuration = self._classe_configuration()
        try:
            # Charger l'identificateur de noeud
            configuration_docker = self._docker.configs.get(ConstantesServiceMonitor.DOCKER_CONFIG_NOEUD_ID)
            data = b64decode(configuration_docker.attrs['Spec']['Data'])
            self._noeud_id = data.decode('utf-8')
        except docker.errors.NotFound as he:
            self.__logger.debug("Configuration %s n'existe pas" % ConstantesServiceMonitor.DOCKER_CONFIG_NOEUD_ID)

        try:
            configuration_docker = self._docker.configs.get(ConstantesServiceMonitor.DOCKER_LIBVAL_CONFIG)
            data = b64decode(configuration_docker.attrs['Spec']['Data'])
            configuration_json = json.loads(data)
            self._idmg = configuration_json[Constantes.CONFIG_IDMG]
            self._securite = configuration_json[Constantes.DOCUMENT_INFODOC_SECURITE]

            self.__logger.debug("Configuration noeud, idmg: %s, securite: %s", self._idmg, self._securite)
        except docker.errors.NotFound as he:
            self.__logger.debug("Configuration %s n'existe pas" % ConstantesServiceMonitor.DOCKER_LIBVAL_CONFIG)

    def _classe_configuration(self):
        """
        Retourne la classe de gestion de certificat
        :return: Sous-classe de GestionnaireCertificats
        """
        raise NotImplementedError()

    def __entretien_certificats(self):
        """
        Effectue l'entretien des certificats : genere certificats manquants ou expires avec leur cle
        :return:
        """
        # MAJ date pour creation de certificats
        self._gestionnaire_certificats.maj_date()

        prefixe_certificats = 'pki.'
        filtre = {'name': prefixe_certificats}

        # Generer tous les certificas qui peuvent etre utilises
        roles = dict()
        for role in [info['role'] for info in MonitorConstantes.DICT_MODULES.values() if info.get('role')]:
            roles[role] = dict()

        # Charger la configuration existante
        date_renouvellement = datetime.datetime.utcnow() + datetime.timedelta(days=21)
        for config in self._docker.configs.list(filters=filtre):
            self.__logger.debug("Config : %s", str(config))
            nom_config = config.name.split('.')
            nom_role = nom_config[1]
            if nom_config[2] == 'cert' and nom_role in roles.keys():
                role_info = roles[nom_role]
                self.__logger.debug("Verification cert %s date %s", nom_role, nom_config[3])
                pem = b64decode(config.attrs['Spec']['Data'])
                clecert = EnveloppeCleCert()
                clecert.cert_from_pem_bytes(pem)
                date_expiration = clecert.not_valid_after

                expiration_existante = role_info.get('expiration')
                if not expiration_existante or expiration_existante < date_expiration:
                    role_info['expiration'] = date_expiration
                    if date_expiration < date_renouvellement:
                        role_info['est_expire'] = True
                    else:
                        role_info['est_expire'] = False

        # Generer certificats expires et manquants
        for nom_role, info_role in roles.items():
            if not info_role.get('expiration') or info_role.get('est_expire'):
                self.__logger.debug("Generer nouveau certificat role %s", nom_role)
                self._gestionnaire_certificats.generer_clecert_module(nom_role, self._nodename)

    def configurer_millegrille(self):
        besoin_initialiser = not self._idmg

        if besoin_initialiser:
            # Generer certificat de MilleGrille
            self._idmg = self._gestionnaire_certificats.generer_nouveau_idmg()

        self._gestionnaire_docker = GestionnaireModulesDocker(
            self._idmg, self._docker, self._fermeture_event, MonitorConstantes.MODULES_REQUIS_PRIMAIRE.copy(),
            self, insecure=self._args.dev)
        self._gestionnaire_docker.start_events()
        self._gestionnaire_docker.add_event_listener(self)

        if besoin_initialiser:
            self._gestionnaire_docker.initialiser_millegrille()

            # Modifier service docker du service monitor pour ajouter secrets
            self._gestionnaire_docker.configurer_monitor()
            self.fermer()  # Fermer le monitor, va forcer un redemarrage du service
            raise ForcerRedemarrage("Redemarrage")

        # Generer certificats de module manquants ou expires, avec leur cle
        self._gestionnaire_certificats.charger_certificats()  # Charger certs sur disque
        self.__entretien_certificats()

        # Initialiser gestionnaire web
        self._gestionnaire_web = GestionnaireWeb(self, mode_dev=self._args.dev)

    def _entretien_modules(self):
        if not self.limiter_entretien:
            # S'assurer que les modules sont demarres - sinon les demarrer, en ordre.
            self._gestionnaire_docker.entretien_services()

            # Entretien du middleware
            self._gestionnaire_mq.entretien()

            # Entretien web
            self._gestionnaire_web.entretien()

    def run(self):
        raise NotImplementedError()

    def verifier_load(self):
        cpu_load, cpu_load5, cpu_load10 = psutil.getloadavg()
        if cpu_load > 3.0 or cpu_load5 > 4.0:
            self.limiter_entretien = True
            self.__logger.warning("Charge de travail elevee %s / %s, entretien limite" % (cpu_load, cpu_load5))
        else:
            self.limiter_entretien = False

    @property
    def noeud_id(self) -> str:
        return self._noeud_id

    @property
    def idmg(self):
        return self._idmg

    @property
    def idmg_tronque(self):
        return self._idmg[0:12]

    @property
    def nodename(self):
        return self._nodename

    @property
    def identificateur(self):
        return self._nodename

    def event(self, event):
        event_json = json.loads(event)
        if event_json.get('Type') == 'container':
            if event_json.get('Action') == 'start' and event_json.get('status') == 'start':
                self.__logger.debug("Container demarre: %s", event_json)
                self._attente_event.set()

    def _preparer_csr(self):
        date_courante = datetime.datetime.utcnow().strftime(MonitorConstantes.DOCKER_LABEL_TIME)
        # Sauvegarder information pour cert, cle
        label_cert_millegrille = self.idmg_tronque + '.pki.millegrille.cert.' + date_courante
        self._docker.configs.create(name=label_cert_millegrille, data=json.dumps(self._configuration_json['pem']))

    def transmettre_info_acteur(self, commande):
        """
        Transmet les information du noeud vers l'acteur
        :param commande:
        :return:
        """
        information_systeme = self._get_info_noeud()
        information_systeme['commande'] = 'set_info'
        self._gestionnaire_commandes.transmettre_vers_acteur(information_systeme)

    def _get_info_noeud(self):
        information_systeme = {
            'noeud_id': self.noeud_id
        }
        if self._idmg:
            information_systeme['idmg'] = self._idmg

        return information_systeme

    @property
    def gestionnaire_mq(self):
        return self._gestionnaire_mq

    @property
    def gestionnaire_mongo(self):
        return self._connexion_middleware.get_gestionnaire_comptes_mongo

    @property
    def gestionnaire_docker(self) -> GestionnaireModulesDocker:
        return self._gestionnaire_docker

    @property
    def gestionnaire_commandes(self):
        return self._gestionnaire_commandes

    @property
    def gestionnaire_certificats(self):
        return self._gestionnaire_certificats

    @property
    def generateur_transactions(self):
        return self._connexion_middleware.generateur_transactions

    @property
    def gestionnaire_applications(self):
        return self._gestionnaire_applications

    @property
    def docker(self):
        return self._docker

    def set_noeud_id(self, noeud_id: str):
        self._noeud_id = noeud_id

    def rediriger_messages_downstream(self, nom_domaine: str, exchanges_routing: dict):
        raise NotImplementedError()


class ServiceMonitorPrincipal(ServiceMonitor):
    """
    ServiceMonitor pour noeud protege principal
    """

    def __init__(self, args, docker_client: docker.DockerClient, configuration_json: dict):
        super().__init__(args, docker_client, configuration_json)
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

    def run(self):
        self.__logger.info("Demarrage du ServiceMonitor")

        try:
            self._charger_configuration()
            self.preparer_gestionnaire_certificats()
            self.configurer_millegrille()
            self.preparer_mdns()
            self.preparer_gestionnaire_comptesmq()
            self.preparer_gestionnaire_commandes()
            self.preparer_gestionnaire_applications()
            self.preparer_web_api()

            while not self._fermeture_event.is_set():
                self._attente_event.clear()

                try:
                    self.__logger.debug("Cycle entretien ServiceMonitor")

                    self.verifier_load()

                    self._entretien_modules()

                    if not self._connexion_middleware:
                        try:
                            self.connecter_middleware()
                        except BrokenBarrierError:
                            self.__logger.warning("Erreur connexion MQ, on va reessayer plus tard")

                    self.__logger.debug("Fin cycle entretien ServiceMonitor")
                except Exception:
                    self.__logger.exception("ServiceMonitor: erreur generique")
                finally:
                    self._attente_event.wait(30)

        except ForcerRedemarrage:
            self.__logger.info("Configuration initiale terminee, fermeture pour redemarrage")
            self.exit_code = ConstantesServiceMonitor.EXIT_REDEMARRAGE

        except Exception:
            self.__logger.exception("Erreur demarrage ServiceMonitor, on abandonne l'execution")

        self.__logger.info("Fermeture du ServiceMonitor")
        self.fermer()

        # Fermer le service monitor, retourne exit code pour shell script
        sys.exit(self.exit_code)

    def preparer_gestionnaire_certificats(self):
        params = dict()
        if self._args.dev:
            params['insecure'] = True
        if self._args.secrets:
            params['secrets'] = self._args.secrets
        self._gestionnaire_certificats = GestionnaireCertificatsNoeudProtegePrincipal(self._docker, self, **params)

    def preparer_gestionnaire_commandes(self):
        self._gestionnaire_commandes = GestionnaireCommandes(self._fermeture_event, self)

        super().preparer_gestionnaire_commandes()  # Creer pipe et demarrer

    def preparer_mdns(self):
        super().preparer_mdns()
        # self._gestionnaire_mdns.ajouter_service('millegrilles', '_amqps._tcp.local.', 5673)
        # self._gestionnaire_mdns.ajouter_service('millegrilles', '_https._tcp.local.', 443)

    def rediriger_messages_downstream(self, nom_domaine: str, exchanges_routing: dict):
        pass  # Rien a faire pour le monitor principal


class ServiceMonitorDependant(ServiceMonitor):
    """
    ServiceMonitor pour noeud protege dependant
    """

    def __init__(self, args, docker_client: docker.DockerClient, configuration_json: dict):
        super().__init__(args, docker_client, configuration_json)
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__event_attente = Event()

        self.__connexion_principal: ConnexionPrincipal = cast(ConnexionPrincipal, None)

    def fermer(self, signum=None, frame=None):
        super().fermer(signum, frame)
        self.__event_attente.set()

    def trigger_event_attente(self):
        self.__event_attente.set()

    def run(self):
        self.__logger.debug("Execution noeud dependant")
        self._charger_configuration()
        self._gestionnaire_docker = GestionnaireModulesDocker(
            self._idmg, self._docker, self._fermeture_event, MonitorConstantes.MODULES_REQUIS_DEPENDANT.copy(),
            self, insecure=self._args.dev)
        self._gestionnaire_docker.start_events()
        self._gestionnaire_docker.add_event_listener(self)
        self.preparer_gestionnaire_certificats()

        methode_run = self.__determiner_type_run()
        methode_run()  # Excuter run

    def __determiner_type_run(self):
        # Verifier si le certificat de millegrille a ete charge
        try:
            info_cert_millegrille = MonitorConstantes.trouver_config(
                'pki.millegrille.cert', self.idmg_tronque, self._docker)
            self.__logger.debug("Cert millegrille deja charge, date %s" % info_cert_millegrille['date'])
        except AttributeError:
            self.__logger.info("Run initialisation noeud dependant")
            return self.run_configuration_initiale

        # Le certificat de millegrille est charge, s'assurer que la cle de monitor est generee
        # Il est anormal que le cert millegrille soit charge et la cle de monitor absente, mais c'est supporte
        try:
            label_key = 'pki.' + ConstantesGenerateurCertificat.ROLE_MONITOR_DEPENDANT + '.key'
            info_cle_monitor = self.gestionnaire_docker.trouver_secret(label_key)
            self.__logger.debug("Cle monitor deja chargee, date %s" % info_cle_monitor['date'])
        except AttributeError:
            self.__logger.warning("Cle secrete monitor manquante, run initialisation noeud dependant")
            return self.run_configuration_initiale

        # Verifier si le certificat de monitor correspondant a la cle est charge

        return self.run_monitor

    def run_configuration_initiale(self):
        """
        Sert a initialiser le noeud protege dependant.
        Termine son execution immediatement apres creation du CSR.
        :return:
        """

        self.__logger.info("Run configuration initiale, (mode insecure: %s)" % self._args.dev)

        # Creer CSR pour le service monitor
        self._gestionnaire_certificats.generer_csr(
            ConstantesGenerateurCertificat.ROLE_MONITOR_DEPENDANT, insecure=self._args.dev)

        # Generer mots de passe
        self._gestionnaire_certificats.generer_motsdepasse()

        # Sauvegarder information pour CSR, cle
        cert_millegrille = self._configuration_json['pem'].encode('utf-8')
        self._gestionnaire_certificats.ajouter_config(
            name='pki.millegrille.cert', data=cert_millegrille)

        self._gestionnaire_docker.initialiser_millegrille()

        print("Preparation CSR du noeud dependant terminee")
        print("Redemarrer le service monitor")

    def run_monitor(self):
        """
        Execution du monitor.
        :return:
        """
        self.__logger.info("Run monitor noeud protege dependant")

        # Activer ecoute des commandes
        self.preparer_gestionnaire_commandes()

        # Initialiser cles, certificats disponibles
        self._gestionnaire_certificats.charger_certificats()  # Charger certs sur disque

        self._attendre_certificat_monitor()  # S'assurer que le certificat du monitor est correct, l'attendre au besoin
        self._initialiser_middleware()       # S'assurer que les certificats du middleware sont corrects
        self._run_entretien()                # Mode d'operation de base, lorsque le noeud est bien configure

    def _attendre_certificat_monitor(self):
        """
        Mode d'attente de la commande avec le certificat signe du monitor.
        :return:
        """
        self.__logger.info("Verifier et attendre certificat du service monitor")

        clecert_monitor = self._gestionnaire_certificats.clecert_monitor
        if not clecert_monitor.cert:
            while not self.__event_attente.is_set():
                self.__logger.info("Attente du certificat de monitor dependant")
                self.__event_attente.wait(120)

        self.__logger.debug("Certificat monitor valide jusqu'a : %s" % clecert_monitor.not_valid_after)

        self.__logger.info("Certificat du service monitor pret")

    def _initialiser_middleware(self):
        """
        Mode de creation des certificats du middleware (MQ, Mongo, MongoExpress)
        :return:
        """
        self.__logger.info("Verifier et attendre certificats du middleware")

        # Charger certificats - copie les certs sous /tmp pour connecter a MQ
        self._gestionnaire_certificats.charger_certificats()

        # Connecter au MQ principal
        self.__connexion_principal = ConnexionPrincipal(self._docker, self)
        self.__connexion_principal.connecter()

        # Confirmer que les cles mq, mongo, mongoxp ont ete crees
        liste_csr = list()
        for role in MonitorConstantes.CERTIFICATS_REQUIS_DEPENDANT:
            label_cert = 'pki.%s.cert' % role
            try:
                MonitorConstantes.trouver_config(label_cert, self.idmg_tronque, self._docker)
            except AttributeError:
                label_key = 'pki.%s.key' % role
                fichier_csr = 'pki.%s.csr.pem' % role
                try:
                    self._gestionnaire_docker.trouver_secret(label_key)
                    path_fichier = os.path.join(MonitorConstantes.PATH_PKI, fichier_csr)
                    with open(path_fichier, 'r') as fichier:
                        csr = fichier.read()
                except AttributeError:
                    # Creer la cle, CSR correspondant
                    inserer_cle = role not in ['mongo']
                    info_csr = self._gestionnaire_certificats.generer_csr(role, insecure=self._args.dev, inserer_cle=inserer_cle)
                    csr = str(info_csr['request'], 'utf-8')
                    if role == 'mongo':
                        self._gestionnaire_certificats.memoriser_cle(role, info_csr['cle_pem'])
                liste_csr.append(csr)

        if len(liste_csr) > 0:
            self.__event_attente.clear()
            commande = {
                'liste_csr': liste_csr,
            }
            # Transmettre commande de signature de certificats, attendre reponse
            while not self.__event_attente.is_set():
                self.__connexion_principal.generateur_transactions.transmettre_commande(
                    commande,
                    'commande.MaitreDesCles.%s' % Constantes.ConstantesMaitreDesCles.COMMANDE_SIGNER_CSR,
                    correlation_id=ConstantesServiceMonitor.CORRELATION_CERTIFICAT_SIGNE,
                    reply_to=self.__connexion_principal.reply_q
                )
                self.__logger.info("Attente certificats signes du middleware")
                self.__event_attente.wait(120)

        self.preparer_gestionnaire_comptesmq()
        self.__logger.info("Certificats du middleware prets")

    def _run_entretien(self):
        """
        Mode d'operation de base du monitor, lorsque toute la configuration est completee.
        :return:
        """
        self.__logger.info("Debut boucle d'entretien du service monitor")

        while not self._fermeture_event.is_set():
            self._attente_event.clear()

            try:
                self.__logger.debug("Cycle entretien ServiceMonitor")

                self.verifier_load()

                if not self._connexion_middleware:
                    try:
                        self.connecter_middleware()
                        self._connexion_middleware.set_relai(self.__connexion_principal)
                        self.__connexion_principal.initialiser_relai_messages(self._connexion_middleware.relayer_message)
                    except BrokenBarrierError:
                        self.__logger.warning("Erreur connexion MQ, on va reessayer plus tard")

                self._entretien_modules()

                self.__logger.debug("Fin cycle entretien ServiceMonitor")
            except Exception:
                self.__logger.exception("ServiceMonitor: erreur generique")
            finally:
                self._attente_event.wait(30)

        self.__logger.info("Fin execution de la boucle d'entretien du service monitor")

    def connecter_middleware(self):
        super().connecter_middleware()

    def __charger_cle(self):
        if self._args.dev:
            path_cle = '/var/opt/millegrilles/pki/servicemonitor.key.pem'
        else:
            path_cle = '/run/secrets/pki.monitor.key.pem'

        with open(path_cle, 'rb') as fichier:
            cle_bytes = fichier.read()

    def preparer_gestionnaire_certificats(self):
        params = dict()
        if self._args.dev:
            params['insecure'] = True
        if self._args.secrets:
            params['secrets'] = self._args.secrets
        self._gestionnaire_certificats = GestionnaireCertificatsNoeudProtegeDependant(self._docker, self, **params)

    def preparer_gestionnaire_commandes(self):
        self._gestionnaire_commandes = GestionnaireCommandesNoeudProtegeDependant(self._fermeture_event, self)

        super().preparer_gestionnaire_commandes()  # Creer pipe et demarrer

    def inscrire_domaine(self, nom_domaine: str, exchanges_routing: dict):
        self._connexion_middleware.rediriger_messages_domaine(nom_domaine, exchanges_routing)

    def rediriger_messages_downstream(self, nom_domaine: str, exchanges_routing: dict):
        self.__connexion_principal.enregistrer_domaine(nom_domaine, exchanges_routing)


class ServiceMonitorInstalleur(ServiceMonitor):

    def __init__(self, args, docker_client: docker.DockerClient, configuration_json: dict):
        super().__init__(args, docker_client, configuration_json)
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__event_attente = Event()

        self.__connexion_principal: ConnexionPrincipal = cast(ConnexionPrincipal, None)

        self.csr_intermediaire = None

    def fermer(self, signum=None, frame=None):
        super().fermer(signum, frame)
        self.__event_attente.set()

    def trigger_event_attente(self):
        self.__event_attente.set()

    def _charger_configuration(self):
        super()._charger_configuration()
        self._idmg = ''

    def run(self):
        self.__logger.debug("Execution installation du noeud")
        self.__logger.info("Run configuration initiale, (mode insecure: %s)" % self._args.dev)
        self._charger_configuration()

        self._gestionnaire_docker = GestionnaireModulesDocker(
            self._idmg, self._docker, self._fermeture_event, MonitorConstantes.MODULES_REQUIS_INSTALLATION.copy(),
            self, insecure=self._args.dev
        )

        self.preparer_mdns()

        try:
            self._gestionnaire_docker.initialiser_noeud()
        except APIError:
            self.__logger.info("Docker.initialiser_noeud: Noeud deja initialise")

        # Initialiser gestionnaire web
        self._gestionnaire_web = GestionnaireWeb(self, mode_dev=self._args.dev)
        self._gestionnaire_web.entretien()

        self._gestionnaire_docker.start_events()
        self._gestionnaire_docker.add_event_listener(self)

        self.__logger.info("Preparation CSR du noeud dependant terminee")
        self.preparer_gestionnaire_certificats()

        self.preparer_gestionnaire_commandes()

        # Entretien initial pour s'assurer d'avoir les services de base
        try:
            self._gestionnaire_docker.entretien_services()
        except AttributeError as ae:
            self.__logger.exception("Erreur creation services, docker config non chargee")
            raise ae

        self.__logger.info("Web API - attence connexion sur port 8444")
        self.preparer_web_api()

        while not self.__event_attente.is_set():
            self._run_entretien()
            self.__event_attente.wait(10)

    def _run_entretien(self):
        """
        Mode d'operation de base du monitor, lorsque toute la configuration est completee.
        :return:
        """
        self.__logger.info("Debut boucle d'entretien du service monitor")

        while not self._fermeture_event.is_set():
            self._attente_event.clear()

            try:
                self.__logger.debug("Cycle entretien ServiceMonitor")
                self.verifier_load()

                if not self.limiter_entretien:
                    # S'assurer que les modules sont demarres - sinon les demarrer, en ordre.
                    self._gestionnaire_docker.entretien_services()

                self.__logger.debug("Fin cycle entretien ServiceMonitor")
            except Exception:
                self.__logger.exception("ServiceMonitor: erreur generique")
            finally:
                self._attente_event.wait(30)

        self.__logger.info("Fin execution de la boucle d'entretien du service monitor")

    def preparer_gestionnaire_certificats(self):
        params = dict()
        if self._args.dev:
            params['insecure'] = True
        if self._args.secrets:
            params['secrets'] = self._args.secrets
        self._gestionnaire_certificats = GestionnaireCertificatsInstallation(self._docker, self, **params)

        nouveau_secrets_monitor_ajoutes = False  # Flag qui va indiquer si de nouveaux secrets sont ajoutes

        # Verifier si le certificat nginx existe deja - generer un cert self-signed au besoin
        try:
            docker_cert_nginx = self._gestionnaire_docker.charger_config_recente('pki.nginx.cert')
        except AttributeError:
            # Certificat absent, on genere un certificat et cle nginx
            self._gestionnaire_certificats.generer_certificat_nginx_selfsigned()

        # Verifier si le CSR a deja ete genere, sinon le generer
        try:
            csr_config_docker = self._gestionnaire_docker.charger_config_recente('pki.intermediaire.csr')
            data_csr = b64decode(csr_config_docker['config'].attrs['Spec']['Data'])
            self.csr_intermediaire = data_csr
        except AttributeError:
            # Creer CSR pour le service monitor
            csr_info = self._gestionnaire_certificats.generer_csr('intermediaire', insecure=self._args.dev, generer_password=True)
            self.csr_intermediaire = csr_info['request']

        # Verifier si la cle du monitor existe, sinon la generer
        try:
            self._gestionnaire_docker.trouver_secret('pki.monitor.key')
        except ValueError:
            # Creer CSR pour le service monitor
            self._gestionnaire_certificats.generer_csr('monitor', insecure=self._args.dev, generer_password=False)
            nouveau_secrets_monitor_ajoutes = True

        # if nouveau_secrets_monitor_ajoutes:
        if nouveau_secrets_monitor_ajoutes and not self._args.dev:
            # Besoin reconfigurer le service pour ajouter les secrets et redemarrer
            self._gestionnaire_docker.configurer_monitor()

            # Redemarrer / reconfigurer le monitor
            self.__logger.info("Configuration completee, redemarrer le monitor")
            raise ForcerRedemarrage("Redemarrage")

    def initialiser_domaine(self, commande):
        params = commande.contenu
        gestionnaire_docker = self.gestionnaire_docker

        # Aller chercher le certificat SSL de LetsEncrypt
        domaine_noeud = params['domaine']  # 'mg-dev4.maple.maceroc.com'
        mode_test = self._args.dev or params.get('modeTest')

        params_environnement = list()
        params_secrets = list()
        if params.get('modeCreation') == 'dns_cloudns':
            methode_validation = '--dns dns_cloudns'
            params_environnement.append("CLOUDNS_SUB_AUTH_ID=" + params['cloudnsSubid'])
            params_secrets.append("CLOUDNS_AUTH_PASSWORD=" + params['cloudnsPassword'])
        else:
            methode_validation = '--webroot /usr/share/nginx/html'

        configuration_acme = {
            'domain': domaine_noeud,
            'methode': {
                'commande': methode_validation,
                'mode_test': True,
                'params_environnement': params_environnement,
            }
        }

        commande_acme = methode_validation
        if mode_test:
            commande_acme = '--test ' + methode_validation

        params_combines = list(params_environnement)
        params_combines.extend(params_secrets)

        acme_container_id = gestionnaire_docker.trouver_container_pour_service('acme')
        commande_acme = "acme.sh --issue %s -d %s" % (commande_acme, domaine_noeud)
        resultat_acme, output_acme = gestionnaire_docker.executer_script_blind(
            acme_container_id,
            commande_acme,
            environment=params_combines
        )
        if resultat_acme != 0:
            self.__logger.error("Erreur ACME, code : %d\n%s", resultat_acme, output_acme.decode('utf-8'))
            #raise Exception("Erreur creation certificat avec ACME")
        cert_bytes = gestionnaire_docker.get_archive_bytes(acme_container_id, '/acme.sh/%s' % domaine_noeud)
        io_buffer = io.BytesIO(cert_bytes)
        with tarfile.open(fileobj=io_buffer) as tar_content:
            member_key = tar_content.getmember('%s/%s.key' % (domaine_noeud, domaine_noeud))
            key_bytes = tar_content.extractfile(member_key).read()
            member_fullchain = tar_content.getmember('%s/fullchain.cer' % domaine_noeud)
            fullchain_bytes = tar_content.extractfile(member_fullchain).read()

        # Inserer certificat, cle dans docker
        secret_name, date_secret = gestionnaire_docker.sauvegarder_secret(
            'pki.web.key', key_bytes, ajouter_date=True)

        gestionnaire_docker.sauvegarder_config('acme.configuration', json.dumps(configuration_acme).encode('utf-8'))
        gestionnaire_docker.sauvegarder_config('pki.web.cert.' + date_secret, fullchain_bytes)

        # Forcer reconfiguration nginx
        gestionnaire_docker.maj_service('nginx')

    def initialiser_noeud(self, commande):
        params = commande.contenu
        gestionnaire_docker = self.gestionnaire_docker

        gestionnaire_certs = GestionnaireCertificatsNoeudProtegePrincipal(
            self.docker, self, secrets=self._args.secrets, insecure=self._args.dev)
        gestionnaire_certs.generer_motsdepasse()

        # Faire correspondre et sauvegarder certificat de noeud
        secret_intermediaire = gestionnaire_docker.trouver_secret('pki.intermediaire.key')

        with open(os.path.join(self._args.secrets, 'pki.intermediaire.key.pem'), 'rb') as fichier:
            intermediaire_key_pem = fichier.read()
        with open(os.path.join(self._args.secrets, 'pki.intermediaire.passwd.txt'), 'rb') as fichier:
            intermediaire_passwd_pem = fichier.read()

        clecert_intermediaire = EnveloppeCleCert()
        clecert_intermediaire.from_pem_bytes(intermediaire_key_pem, params['certificatIntermediairePem'].encode('utf-8'), intermediaire_passwd_pem)
        if not clecert_intermediaire.cle_correspondent():
            raise ValueError('Cle et Certificat intermediaire ne correspondent pas')

        # Comencer sauvegarde
        gestionnaire_docker.sauvegarder_config('pki.millegrille.cert', params['certificatMillegrillePem'])

        gestionnaire_docker.sauvegarder_config(
            'pki.intermediaire.cert.' + str(secret_intermediaire['date']),
            params['certificatIntermediairePem']
        )
        chaine_intermediaire = '\n'.join([params['certificatIntermediairePem'], params['certificatMillegrillePem']])
        gestionnaire_docker.sauvegarder_config('pki.intermediaire.chain.' + str(secret_intermediaire['date']), chaine_intermediaire)
        # Supprimer le CSR
        gestionnaire_docker.supprimer_config('pki.intermediaire.csr.' + str(secret_intermediaire['date']))

        # Extraire IDMG
        clecert_millegrille = EnveloppeCleCert()
        clecert_millegrille.cert_from_pem_bytes(params['certificatMillegrillePem'].encode('utf-8'))
        idmg = clecert_millegrille.idmg

        # Configurer gestionnaire certificats avec clecert millegrille, intermediaire
        self._gestionnaire_certificats.idmg = idmg
        self._gestionnaire_certificats.set_clecert_millegrille(clecert_millegrille)
        self._gestionnaire_certificats.set_clecert_intermediaire(clecert_intermediaire)

        # Generer nouveau certificat de monitor
        # Charger CSR monitor
        config_csr_monitor = self._gestionnaire_docker.charger_config_recente('pki.monitor.csr')
        data_csr_monitor = b64decode(config_csr_monitor['config'].attrs['Spec']['Data'])
        clecert_monitor = self._gestionnaire_certificats.signer_csr(data_csr_monitor)

        # Sauvegarder certificat monitor
        # Faire correspondre et sauvegarder certificat de noeud
        secret_monitor = gestionnaire_docker.trouver_secret('pki.monitor.key')
        gestionnaire_docker.sauvegarder_config(
            'pki.monitor.cert.' + str(secret_monitor['date']),
            '\n'.join(clecert_monitor.chaine)
        )
        # Supprimer le CSR
        gestionnaire_docker.supprimer_config('pki.monitor.csr.' + str(secret_monitor['date']))

        # Terminer configuration swarm docker
        gestionnaire_docker.initialiser_noeud(idmg=idmg)

        # Sauvegarder configuration.millegrille
        configuration_millegrille = {
            'securite': params['securite'],
            'idmg': idmg,
        }
        gestionnaire_docker.sauvegarder_config('millegrille.configuration', configuration_millegrille)

        # Regenerer la configuraiton de NGINX (change defaut de /installation vers /vitrine)
        # Redemarrage est implicite (fait a la fin de la prep)
        self._gestionnaire_web.regenerer_configuration(mode_installe=True)

        # Redemarrer / reconfigurer le monitor
        self.__logger.info("Configuration completee, redemarrer le monitor")
        gestionnaire_docker.configurer_monitor()

        raise ForcerRedemarrage("Redemarrage")

    def preparer_mdns(self):
        self.__logger.info("Initialisation mdns http sur port 80")
        super().preparer_mdns()
        # self._gestionnaire_mdns.ajouter_service('millegrilles', '_http._tcp.local.', 80)

    def _get_info_noeud(self):
        information_systeme = super()._get_info_noeud()
        information_systeme['csr'] = self.csr_intermediaire.decode('utf-8')
        return information_systeme

class ServiceMonitorExtension(ServiceMonitor):
    """
    Monitor pour le noeud d'extension
    """

    def __init__(self, args, docker_client: docker.DockerClient, configuration_json: dict):
        super().__init__(args, docker_client, configuration_json)
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

    def run(self):
        self.__logger.info("Demarrage du ServiceMonitor")

        try:
            self._charger_configuration()
            self.preparer_gestionnaire_certificats()
            self.configurer_millegrille()
            self.preparer_gestionnaire_commandes()
            self.preparer_web_api()

            while not self._fermeture_event.is_set():
                self._attente_event.clear()

                try:
                    self.__logger.debug("Cycle entretien ServiceMonitor")

                    self.verifier_load()

                    self._entretien_modules()

                    if not self._connexion_middleware:
                        try:
                            self.connecter_middleware()
                        except BrokenBarrierError:
                            self.__logger.warning("Erreur connexion MQ, on va reessayer plus tard")

                    self.__logger.debug("Fin cycle entretien ServiceMonitor")
                except Exception:
                    self.__logger.exception("ServiceMonitor: erreur generique")
                finally:
                    self._attente_event.wait(30)

        except ForcerRedemarrage:
            self.__logger.info("Configuration initiale terminee, fermeture pour redemarrage")
            self.exit_code = ConstantesServiceMonitor.EXIT_REDEMARRAGE

        except Exception:
            self.__logger.exception("Erreur demarrage ServiceMonitor, on abandonne l'execution")

        self.__logger.info("Fermeture du ServiceMonitor")
        self.fermer()

        # Fermer le service monitor, retourne exit code pour shell script
        sys.exit(self.exit_code)

    def preparer_gestionnaire_certificats(self):
        params = dict()
        if self._args.dev:
            params['insecure'] = True
        if self._args.secrets:
            params['secrets'] = self._args.secrets
        self._gestionnaire_certificats = GestionnaireCertificatsNoeudPrive(self._docker, self, **params)

    def preparer_gestionnaire_commandes(self):
        self._gestionnaire_commandes = GestionnaireCommandes(self._fermeture_event, self)

        super().preparer_gestionnaire_commandes()  # Creer pipe et demarrer


# Section main
if __name__ == '__main__':
    logging.basicConfig(stream=sys.stdout, format=MonitorConstantes.SERVICEMONITOR_LOGGING_FORMAT)
    logging.getLogger(ServiceMonitor.__name__).setLevel(logging.INFO)

    # ServiceMonitor().run()
    InitialiserServiceMonitor().demarrer()
