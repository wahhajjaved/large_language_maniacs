#-*- coding: utf-8 -*-

###########################################################################
##                                                                       ##
## Copyrights Frederic Rodrigo 2012                                      ##
##                                                                       ##
## This program is free software: you can redistribute it and/or modify  ##
## it under the terms of the GNU General Public License as published by  ##
## the Free Software Foundation, either version 3 of the License, or     ##
## (at your option) any later version.                                   ##
##                                                                       ##
## This program is distributed in the hope that it will be useful,       ##
## but WITHOUT ANY WARRANTY; without even the implied warranty of        ##
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         ##
## GNU General Public License for more details.                          ##
##                                                                       ##
## You should have received a copy of the GNU General Public License     ##
## along with this program.  If not, see <http://www.gnu.org/licenses/>. ##
##                                                                       ##
###########################################################################

from plugins.Plugin import Plugin
import urllib, re
import unicodedata


class TagACorriger_Tree(Plugin):

    only_for = ["fr"]

    def strip_accents(self, s):
        return ''.join((c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'))

    def normalize(self, string):
        return self.strip_accents(string.strip().lower()).replace(' commun', '')

    def liste_des_arbres_fruitiers(self):
        reline = re.compile("\[\[([^:]*)$")
        data = urllib.urlopen("http://fr.wikipedia.org/wiki/Liste_des_arbres_fruitiers?action=raw").read()
        #data = open("Liste_des_arbres_fruitiers?action=raw").read()
        data = data.split("]]")
        for line in data:
            line = line.decode("utf8")
            for res in reline.findall(line):
                for n in res.split('|'):
                    self.Tree[self.normalize(n)] = {'species:fr':res}

    def liste_des_essences_europennes(self):
        reline = re.compile("^\* \[\[([^]]*)\]\][^[]*\[\[([^]]*)\]\][^[]*(?:\[\[([^]]*)\]\][^[]*)?(?:\[\[([^]]*)\]\][^[]*)?")
        data = urllib.urlopen("http://fr.wikipedia.org/wiki/Liste_des_essences_forestières_européennes?action=raw").read()
        #data = open("Liste_des_essences_forestières_européennes?action=raw").read()
        data = data.split("\n")
        for line in data:
            line = line.decode("utf8")
            #print line
            for res in reline.findall(line):
                for n in res[0].split('|'):
                    self.Tree[self.normalize(n)] = {'genus':res[1], 'species':'|'.join(res[2:3]), 'species:fr':res[0]}

    def check(self, tag, value, subclass):
        name = self.normalize(u''.join(value))
        if name in self.Tree:
            return (3120, subclass, {"fr": u"Mauvais tag %s=\"%s\"" % (tag, value), "en": u"Bad tag %s=\"%s\"" % (tag, value), "fix": {"-": [tag], "+": self.Tree[name]} })

    def init(self, logger):
        Plugin.init(self, logger)
        self.errors[3120] = {"item": 3120, "level": 3, "tag": ["natural", "tree"], "desc": {"en": u"Tree taggin", "fr": u"Arbre"} }

        self.Tree = {}
        self.liste_des_arbres_fruitiers()
        self.liste_des_essences_europennes()

    def node(self, data, tags):
        if not ('natural' in tags and tags['natural'] == 'tree'):
            return

        err = []

        if 'name' in tags:
            if tags['name'].lower() in ('arbre', 'tree') or 'chablis' in tags['name'].lower() or 'branche' in tags['name'].lower():
                err.append((3120, 0, {"fr": u"Mauvais tag name=\"%s\"" % tags['name'], "en": u"Bad tag name=\"%s\"" % tags["name"]}))
            c = self.check('name', tags['name'], 1)
            if c:
                err.append(c)

        if 'type' in tags:
            c = self.check('type', tags['type'], 2)
            if c:
                err.append(c)
            elif tags['type'] not in ('broad_leaved', 'conifer', 'palm'):
                err.append((3120, 3, {"fr": u"Mauvais tag type=\"%s\"" % tags['type'], "en": u"Bad tag type=\"%s\"" % tags["type"]}))

        if 'denotation' in tags:
            if tags['denotation'] not in ('cluster', 'avenue', 'urban', 'natural_monument', 'park', 'landmark'):
                err.append((3120, 4, {"fr": u"Mauvais tag denotation=\"%s\"" % tags['denotation'], "en": u"Bad tag denotation=\"%s\"" % tags["denotation"]}))

        return err

    def way(self, data, tags, nds):
        return self.node(data, tags)

    def relation(self, data, tags, members):
        return self.node(data, tags)

if __name__ == "__main__":
    a = TagACorriger_Tree(None)
    a.init(None)
    for d in [u"Arbre de miel", u"Le Gros Chêne", u"Les Cinq Jumeaux"]:
        if a.node(None, {"natural":"tree", "name":d}):
            print "fail: %s" % d
    for d in [u"Arbre", u"chablis ouvert 25cmd", u"Bouleau", u"Tilleul commun", u"Pin Sylvestre", u"Cèdre", u"Frêne commun", u"Chêne écarlate", u"abricotier"]:
        if not a.node(None, {"natural":"tree", "name":d}):
            print "nofail: %s" % d
    for d in [u"cluster"]:
        if a.node(None, {"natural":"tree", "denotation":d}):
            print "fail: %s" % d
