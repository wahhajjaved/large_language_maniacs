# Affichages sans interaction/boutons qui sont controles via documents ou timers.
import traceback
import datetime
import logging
from threading import Thread, Event

from pymongo.errors import OperationFailure, ServerSelectionTimeoutError
from bson import ObjectId

from millegrilles.domaines.SenseursPassifs import SenseursPassifsConstantes


# Affichage qui se connecte a un ou plusieurs documents et recoit les changements live
class AfficheurDocumentMAJDirecte:

    # :params intervalle_secs: Intervalle (secondes) entre rafraichissements si watch ne fonctionne pas.
    def __init__(self, contexte, intervalle_secs=30):
        self._contexte = contexte
        self._documents = dict()
        self._intervalle_secs = intervalle_secs
        self._intervalle_erreurs_secs = 60  # Intervalle lors d'erreurs
        self._stop_event = Event()  # Evenement qui indique qu'on arrete la thread

        self._collection = None
        self._curseur_changements = None  # Si None, on fonctionne par timer
        self._watch_desactive = False  # Si true, on utilise watch. Sinon on utilise le timer
        self._thread_maj_document = None

    def start(self):
        try:
            self.initialiser_documents()
        except ServerSelectionTimeoutError as sste:
            logging.error("AffichagesPassifs: Erreur de connexion a Mongo. "
                  "On va demarrer quand meme et connecter plus tard. %s" % str(sste))
        except TypeError as te:
            logging.error("AffichagesPassifs: Erreur de connexion a Mongo. "
                  "On va demarrer quand meme et connecter plus tard. %s" % str(te))


        # Thread.start
        self._thread_maj_document = Thread(target=self.run_maj_document)
        self._thread_maj_document.start()
        logging.info("AfficheurDocumentMAJDirecte: thread demarree")

    def fermer(self):
        self._stop_event.set()

    def get_collection(self):
        raise NotImplemented('Doit etre implementee dans la sous-classe')

    def get_filtre(self):
        raise NotImplemented('Doit etre implementee dans la sous-classe')

    def initialiser_documents(self):
        self._collection = self.get_collection()
        filtre = self.get_filtre()

        filtre_watch = dict()
        # Rebatir le filtre avec fullDocument
        for cle in filtre:
            cle_watch = 'documentKey.%s' % cle
            filtre_watch[cle_watch] = filtre[cle]

        # Tenter d'activer watch par _id pour les documents
        try:
            match = {
                '$match': filtre_watch
             }
            pipeline = [match]
            logging.debug("Pipeline watch: %s" % str(pipeline))
            self._curseur_changements = self._collection.watch(pipeline)
            self._watch_desactive = False  # S'assurer qu'on utilise la fonctionnalite watch

        except OperationFailure as opf:
            logging.warning("Erreur activation watch, on fonctionne par timer: %s" % str(opf))
            self._watch_desactive = True

        self.charger_documents()  # Charger une version initiale des documents

    def charger_documents(self):
        # Sauvegarder la version la plus recente de chaque document
        filtre = self.get_filtre()
        curseur_documents = self._collection.find(filtre)
        for document in curseur_documents:
            # Sauvegarder le document le plus recent
            self._documents[document.get('_id')] = document
            logging.debug("#### Document rafraichi: %s" % str(document))

    def get_documents(self):
        return self._documents

    def run_maj_document(self):

        while not self._stop_event.is_set():
            try:
                # Verifier s'il faut se reconnecter
                if self._collection is None:
                    # Il faut se reconnecter
                    self.initialiser_documents()  # Reconnecte la collection, watch et recharge les documents

                # Executer la boucle de rafraichissement. Il y a deux comportements:
                # Si on a un _curseur_changements, on fait juste ecouter les changements du replice sets
                # Si on n'a pas de curseur, on utiliser un timer (_intervalle_sec) pour recharger avec Mongo
                if not self._watch_desactive and self._curseur_changements is not None:
                    logging.debug("Attente changement")
                    valeur = next(self._curseur_changements)

                    doc_id = valeur['documentKey']['_id']
                    if valeur.get('fullDocument') is not None:
                        logging.debug("Recu full document: %s" % str(valeur))
                        self._documents[doc_id] = valeur['fullDocument']
                    elif valeur.get('updateDescription') is not None:
                        logging.debug("Recu MAJ: %s" % str(valeur))
                        updated_fields = valeur['updateDescription']['updatedFields']
                        self._documents[doc_id].update(updated_fields)
                    else:
                        # Mise a jour inconnue. On va recharger le document au complet pour le synchroniser
                        logging.debug("Update de type inconnu, on recharge le document: %s" % str(valeur))
                        full_documents = self._collection.find({'_id': doc_id})
                        for full_document in full_documents:
                            self._documents[doc_id] = full_document

                else:
                    self.charger_documents()
                    self._stop_event.wait(self._intervalle_secs)

            except ServerSelectionTimeoutError as sste:
                logging.warning("AffichagesPassifs: perte de connexion a Mongo: %s" % str(sste))
                # L'erreur vient de la connexion, on va tenter d'aller chercher la collection/curseur a nouveau
                self._collection = None
                self._curseur_changements = None

                self._stop_event.wait(self._intervalle_erreurs_secs)  # On attend avant de se reconnecter

            except Exception as e:
                logging.warning("AfficheurDocumentMAJDirecte: Exception %s" % str(e))
                traceback.print_exc()

                # L'erreur vient peut-etre de la connexion, on va tenter d'aller chercher
                # la collection/curseur plus tard.
                self._collection = None
                self._curseur_changements = None

                self._stop_event.wait(self._intervalle_erreurs_secs)  # On attend avant de se reconnecter

    @property
    def contexte(self):
        return self._contexte


# Classe qui charge des senseurs pour afficher temperature, humidite, pression/tendance
# pour quelques senseurs passifs.
class AfficheurSenseurPassifTemperatureHumiditePression(AfficheurDocumentMAJDirecte):

    def __init__(self, contexte, document_ids, intervalle_secs=30):
        super().__init__(contexte, intervalle_secs)
        self._document_ids = document_ids
        self._thread_affichage = None
        self._thread_horloge = None
        self._horloge_event = Event()  # Evenement pour synchroniser l'heure
        self._lignes_ecran = None

    def get_collection(self):
        return self.contexte.document_dao.get_collection(SenseursPassifsConstantes.COLLECTION_DONNEES_NOM)

    def get_filtre(self):
        document_object_ids = []
        for doc_id in self._document_ids:
            document_object_ids.append(ObjectId(doc_id))

        filtre = {"_id": {'$in': document_object_ids}}
        return filtre

    def start(self):
        super().start()  # Demarre thread de lecture de documents
        self._thread_horloge = Thread(target=self.set_horloge_event)
        self._thread_horloge.start()

        # Thread.start
        self._thread_affichage = Thread(target=self.run_affichage)
        self._thread_affichage.start()
        logging.info("AfficheurDocumentMAJDirecte: thread demarree")

    def set_horloge_event(self):
        while not self._stop_event.is_set():
            # logging.debug("Tick")
            self._horloge_event.set()
            self._stop_event.wait(1)

    def run_affichage(self):

        while not self._stop_event.is_set():  # Utilise _stop_event de la superclasse pour synchroniser l'arret

            try:
                self.afficher_tph()

                # Afficher heure et date pendant 5 secondes
                self.afficher_heure()

            except Exception as e:
                logging.error("Erreur durant affichage: %s" % str(e))
                traceback.print_exc()
                self._stop_event.wait(10)  # Attendre 10 secondes et ressayer du debut

    def maj_affichage(self, lignes_affichage):
        self._lignes_ecran = lignes_affichage

    def afficher_tph(self):
        if not self._stop_event.is_set():
            lignes = self.generer_lignes()
            lignes.reverse()  # On utilise pop(), premieres lectures vont a la fin

            while len(lignes) > 0:
                lignes_affichage = [lignes.pop()]
                if len(lignes) > 0:
                    lignes_affichage.append(lignes.pop())

                # Remplacer contenu ecran
                self.maj_affichage(lignes_affichage)

                logging.debug("Affichage: %s" % lignes_affichage)
                self._stop_event.wait(5)

    def afficher_heure(self):
        nb_secs = 5
        self._horloge_event.clear()
        while not self._stop_event.is_set() and nb_secs > 0:
            self._horloge_event.wait(1)
            nb_secs -= 1

            # Prendre heure courante, formatter
            now = datetime.datetime.now()
            datestring = now.strftime('%Y-%m-%d')
            timestring = now.strftime('%H:%M:%S')

            lignes_affichage = [datestring, timestring]
            logging.debug("Horloge: %s" % str(lignes_affichage))
            self.maj_affichage(lignes_affichage)

            # Attendre 1 seconde
            self._horloge_event.clear()
            self._horloge_event.wait(1)

    def generer_lignes(self):
        lignes = []
        pression = None
        tendance = None

        taille_ecran = 16
        taille_titre_tph = taille_ecran - 11
        taille_titre_press = taille_ecran - 10

        ligne_tph_format = "{location:<%d} {temperature: 5.1f}C/{humidite:2.0f}%%" % taille_titre_tph
        ligne_pression_format = "{titre:<%d} {pression:5.1f}kPa{tendance}" % taille_titre_press

        for senseur_id in self._documents:
            senseur = self._documents[senseur_id].copy()
            if len(senseur.get('location')) > taille_titre_tph:
                senseur['location'] = senseur['location'][:taille_titre_tph]

            info_loc_temp_hum = ligne_tph_format.format(**senseur)
            lignes.append(info_loc_temp_hum)

            if pression is None and senseur.get('pression') is not None:
                pression = senseur['pression']

            if tendance is None and senseur.get('pression_tendance') is not None:
                tendance = senseur['pression_tendance']

        if pression is not None:
            lecture = {'titre': 'Press.', 'pression': pression, 'tendance': tendance}
            contenu = ligne_pression_format.format(**lecture)
            lignes.append(contenu)

        return lignes
