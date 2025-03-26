# -*- coding: utf-8 -*-

from django.core.management.base import BaseCommand
from series.models import Serie, Capitulo, IPDescarga

import threading
from lxml import html
import requests
from requests.utils import quote
from datetime import datetime, timedelta
from time import sleep
import libtorrent as lt

class Command(BaseCommand):
    help = u"Inicia el análisis para el capítulo de la serie indicada"

    tempUrl = "/tmp/.appseries/"

    # Dormir durante 10s hasta próxima actualización
    sleepTime = 10

    def getTorrentsForEpisode(self, tvshow, season, episode, count):
        # Url de búsqueda en kat.cr
        url = "https://kat.cr/usearch/" + quote("%s S%02dE%02d" % (tvshow, season, episode), safe="")
        page = requests.get(url)
        root = html.fromstring(page.content)
        # La primera tabla de la clase data es la tabla correspondiente a la búsqueda
        try:
            table = root.find_class("data")[0]
        except IndexError:
            return []
        # Los enlaces al fichero .torrent tienen el atributo data-download en su elemento
        links = table.findall(".//a[@data-download]")
        # Devolvemos los enlaces
        return map(lambda x: x.attrib['href'], links[:count])

    def getTorrentFileAsString(self, url):
        # Necesario cambiar el User-Agent, sino el servidor cierra la conexión TCP
        headers = {"User-Agent" : "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.80 Safari/537.36"}
        if url.startswith("/"):
            url = "http:" + url
        return requests.get(url, headers=headers).content

    def analyze(self, serieId, temporada, numero):
        try:
            serie = Serie.objects.get(id=int(serieId))
            capitulo = Capitulo.objects.get(serie=serie, temporada=temporada, numero=numero)
        except Serie.DoesNotExist:
            self.stdout.write(u"No existe serie con id %i\n" % (int(serie)))
            return
        except Capitulo.DoesNotExist:
            self.stdout.write(u"No existe caṕítulo %i de la temporada %i para la serie %s\n" % (numero, temporada, serie.nombre))

        # Set de urls siendo actualmente descargadas
        urls = set()
        # Lista de ips de peers conocidos
        peers = []
        # Momento de finalización
        deadline = datetime.now() + timedelta(0, 0, 0, 0, serie.tiempoAnalisis, 0) # MODIF!!!!!!!!!!!!!!!!!!!
        # Establecer análisis del capítulo como iniciado
        capitulo.estado = 0
        capitulo.save()
        # Inicialización de la sesión de libtorrent
        ses = lt.session()
        ses.set_download_rate_limit(serie.limiteBajada * 1024)
        ses.set_upload_rate_limit(serie.limiteSubida * 1024)

        # Segundos totales del análisis
        totalSeconds = serie.tiempoAnalisis*3600
        remainingSeconds = totalSeconds

        while remainingSeconds>0:
            # Comprobar si hay más urls disponibles en caso de no disponer de suficientes
            if len(urls)<serie.numeroTorrents:
                newUrls = set(self.getTorrentsForEpisode(serie.nombre, int(temporada), int(numero), serie.numeroTorrents)) - urls
                for u in newUrls:
                    # Iniciar descarga para cada url
                    e = lt.bdecode(self.getTorrentFileAsString(u))
                    info = lt.torrent_info(e)
                    params = { "save_path": self.tempUrl, "storage_mode": lt.storage_mode_t.storage_mode_sparse, "ti": info }
                    ses.add_torrent(params)

                    # Añadir la url de la descarga a la lista
                    urls.add(u)

            # Para cada descarga comprobar a que peers se encuentra conectado
            for h in ses.get_torrents():
                for p in h.get_peer_info():
                    ip, port = p.ip
                    if ip not in peers:
                        # Añadir a la base de datos
                        newIpDescarga = IPDescarga(capitulo=capitulo, ip=ip, hora=datetime.utcnow().strftime("%s"))
                        newIpDescarga.save()
                        # Añadir los peers al set, evitando asi repetidos
                        peers.append(ip)

            # Actualizar contadores y progreso
            remainingSeconds = (deadline - datetime.now()).total_seconds()
            capitulo.estado = (totalSeconds-remainingSeconds) * 100 / totalSeconds
            capitulo.save()
            sleep(self.sleepTime)

        # Cerrar todas las conexiones activas
        for h in ses.get_torrents():
            ses.remove_torrent(h, lt.options_t.delete_files)
        # Establecer análisis del capítulo como finalizado
        capitulo.estado = -2
        capitulo.save()

    def handle(self, *args, **options):
        if len(args)==3:
            t = threading.Thread(target=self.analyze, args=args)
            t.start()

        else:
            self.stdout.write(u"Número incorrecto de parámetros")
