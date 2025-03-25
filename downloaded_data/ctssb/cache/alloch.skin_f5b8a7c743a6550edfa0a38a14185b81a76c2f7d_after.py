# -*- coding: utf-8 -*-

import simplejson
from datetime import date
from z3c.sqlalchemy import getSAWrapper
from sqlalchemy import and_, exists, func
from zope.publisher.browser import BrowserView
from pygeocoder import Geocoder, GeocoderError
from Products.CMFCore.utils import getToolByName

TYPES_HEB = [5, 6, 9]  # chambres d'hôtes : 'CH', 'MH', 'CHECR'
HEB_PHOTOS_URL = "http://www.gitesdewallonie.be/photos_heb/"
HEB_THUMBS_URL = "http://www.gitesdewallonie.be/vignettes_heb/"


class SearchHebergements(BrowserView):
    """
    """

    def getEpisIcons(self, number):
        result = []
        url = getToolByName(self.context, 'portal_url')()
        for i in range(number):
            result.append('<img src="%s/++resource++1_epis.gif"/>' % url)
        return " ".join(result)

    def getEpis(self, heb):
        """
        Get the epis icons
        """
        l = [self.getEpisIcons(i.heb_nombre_epis) for i in heb.epis]
        return " - ".join(l)

    def getPhotosURL(self, heb):
        """
        Returns photos URLs list
        """
        vignettes = []
        codeGDW = heb.heb_code_gdw
        listeImage = self.context.photos_heb.fileIds()
        for i in range(15):
            if i < 10:
                photo="%s0%s.jpg" % (codeGDW, i)
            else:
                photo="%s%s.jpg" % (codeGDW, i)
            if photo in listeImage:
                vignettes.append("%s%s" % (HEB_PHOTOS_URL, photo))
        return vignettes

    def getHebergement(self):
        """
        Return specified heb
        """
        hebPk = self.request.get('hebPk', None)
        wrapper = getSAWrapper('gites_wallons')
        session = wrapper.session
        hebergementTable = wrapper.getMapper('hebergement')
        query = session.query(hebergementTable)
        heb = query.get(hebPk)
        return heb

    def getGPSForAddress(self, address):
        """
        Transform an address into GPS coordinates
        """
        gcoder = Geocoder('NO_API_KEY')
        try:
            result = gcoder.geocode(address, language='fr', region='be')
        except GeocoderError:
            return None
        return result.coordinates

    def getClosestHebs(self):
        """
        Search for the closests available hebs
        """
        form = self.request.form
        address = form.get('address', None)
        searchLocation = self.getGPSForAddress(address)
        if not searchLocation:
            return []

        today = date.today()
        wrapper = getSAWrapper('gites_wallons')
        session = wrapper.session
        hebergementTable = wrapper.getMapper('hebergement')
        proprioTable = wrapper.getMapper('proprio')
        reservationsTable = wrapper.getMapper('reservation_proprio')

        query = session.query(hebergementTable).join('proprio')
        query = query.filter(hebergementTable.heb_site_public == '1')
        query = query.filter(proprioTable.pro_etat == True)
        query = query.filter(hebergementTable.heb_typeheb_fk.in_(TYPES_HEB))

        # on ne considère que les hébergements pour lequel le calendrier
        # est utilisé et qui sont libres
        query = query.filter(hebergementTable.heb_calendrier_proprio != 'non actif')
        query = query.filter(~exists().where(and_(reservationsTable.res_date == today,
                                                  hebergementTable.heb_pk == reservationsTable.heb_fk)))

        # et on prend les 5 plus proches de la localisation
        query = query.order_by(func.ST_distance_sphere(func.makepoint(hebergementTable.heb_gps_long, hebergementTable.heb_gps_lat),
                                                       func.ST_MakePoint(searchLocation[0], searchLocation[1])))
        query = query.limit(5)
        results = query.all()
        return results

    def getMobileClosestHebs(self):
        """
        Return the closests available hebs for mobile use
        """
        form = self.request.form
        lang = form.get('lang', 'fr')
        results = self.getClosestHebs()
        hebs = []
        for heb in results:
            hebDict = {'name': heb.heb_nom}
            hebDict['type'] = heb.type.getTitle(lang)
            hebDict['classification'] = [e.heb_nombre_epis for e in heb.epis]
            hebDict['capacity_min'] = int(heb.heb_cgt_cap_min)
            hebDict['capacity_max'] = int(heb.heb_cgt_cap_max)
            hebDict['description'] = heb.getDescription(lang)
            address = {'address': heb.heb_adresse,
                       'zip': heb.commune.com_cp,
                       'town': heb.heb_localite,
                       'city': heb.commune.com_nom}
            hebDict['address'] = address
            hebDict['price'] = heb.heb_tarif_chmbr_avec_dej_2p
            hebDict['room_number'] = int(heb.heb_cgt_nbre_chmbre)
            hebDict['one_person_bed'] = int(heb.heb_lit_1p)
            hebDict['two_person_bed'] = int(heb.heb_lit_2p)
            hebDict['additionnal_bed'] = int(heb.heb_lit_sup)
            hebDict['child_bed'] = int(heb.heb_lit_enf)
            if heb.heb_fumeur == 'oui':
                hebDict['smokers_allowed'] = True
            else:
                hebDict['smokers_allowed'] = False
            if heb.heb_animal == 'oui':
                hebDict['animal_allowed'] = True
            else:
                hebDict['animal_allowed'] = False
            owner = {'title': heb.proprio.civilite.civ_titre,
                     'firstname': heb.proprio.pro_prenom1,
                     'name': heb.proprio.pro_nom1,
                     'language': heb.proprio.pro_langue,
                     'phone': heb.proprio.pro_tel_priv,
                     'fax': heb.proprio.pro_fax_priv,
                     'mobile': heb.proprio.pro_gsm1,
                     'email': heb.proprio.pro_email,
                     'website': heb.proprio.pro_url}
            hebDict['owner'] = owner
            vignette = heb.getVignette()
            vignetteURL = "%s%s" % (HEB_THUMBS_URL, vignette)
            hebDict['thumb'] = vignetteURL
            hebDict['photos'] = self.getPhotosURL(heb)
            hebs.append(hebDict)
        jsonResult = simplejson.dumps({'results': hebs})
        return jsonResult
