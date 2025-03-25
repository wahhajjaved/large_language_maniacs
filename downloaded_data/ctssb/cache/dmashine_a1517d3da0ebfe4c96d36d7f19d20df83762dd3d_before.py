#!/usr/bin/env python
# -*- coding: utf-8-*-
""" loads all AFI to sqlite base, collects stats
 Author Drakosh <cpsoft@gmail.com>
 License GNU GPL v3 / Beerware """

import catlib, wikipedia, sys # pywikipedia and category module
import httphelp
from Storage import Storage

class TemplateRandom:
    """Class to form a random 5 articles in template"""
    def __init__(self):
        self.cache = Storage()
    def _wikitext(self):
        """Text for template"""
        ex  = self.cache.cursor.execute("SELECT name FROM articles GROUP BY name ORDER BY RANDOM() LIMIT 5;").fetchall()
        text = u"{{fmbox | text = <center>Статьи для доработки: [["
        text += u"|]]; [[".join([_[0] for _ in ex])
        text += u"|]].</center>}}<noinclude>[[Категория:Навигационные шаблоны:Для обсуждений]]</noinclude>"
        return text
    def save(self):
        """Save text to template"""
        site = wikipedia.getSite()
        httphelp.save(site, text = self._wikitext(),
            pagename = u"Шаблон:Случайные статьи с КУЛ",\
            comment  = u"Обновление шаблона", \
            minoredit = True, botflag = True, dry = False)

class AllAFI:
    """module for AFI stats update"""
    def __init__(self, action):
        self.action = action
        self.site = wikipedia.getSite()
        self.afi = catlib.Category(self.site, \
            u'Категория:Википедия:Статьи для срочного улучшения')
        self.afi_list = []
        self.afi_list_title = []
        self.cache = Storage() 
    def load_all(self):
        """Loads all articles for improvement to sqlite table"""
        self.cache.create('category', {'name':'TEXT', 'cat':'TEXT'})
        self.cache.delete('category')
        self.afi_list = self.afi.articlesList()
        self.afi_list_title = [self.cache.quote(_.title(withNamespace=False)) for _ in self.afi.articlesList()]
        
        for a in self.afi_list:
            wikipedia.output(a)
            for cat in a.categories():
                self.cache.insert('category', (a.title(withNamespace=False), cat.title(withNamespace=False)))

        # now clear articles table from non-actual articles
        re = self.cache.cursor.execute(u"SELECT name FROM articles;")
        for l in re.fetchall():
            if l[0] not in self.afi_list_title:
                wikipedia.output(l[0])
                self.cache.delete('articles', {'name':l[0]})

    def update_stats(self):
        """prints stats to wikipedia page"""
        text = ""
        n1 = self.cache.cursor.execute("SELECT count(DISTINCT name) FROM category;").fetchone()[0]
        n2 = self.cache.cursor.execute("SELECT count(*) FROM articles;").fetchone()[0]
        text += u"Всего статей на КУЛ: '''%s''', статей в базе бота '''%s''' \r\n" % (n1, n2)

        re = self.cache.cursor.execute("SELECT cat, count(*) AS c FROM category GROUP BY cat HAVING c>10 ORDER BY c DESC;")
        text += u"== Топ категорий <ref>Категории, в которых более 10 статей на улучшении, количество статей указано в скобках</ref> == \r\n"
        for l in re.fetchall():
            text += u"* [[:Категория:%s|]]: (%s) \r\n" % l

        text += u"== Самые старые статьи <ref>Учитывается самая первая номинация КУЛ</ref> == \r\n"
        re = self.cache.cursor.execute(u"SELECT name, ts FROM articles ORDER BY ts limit 20;")
        for l in re.fetchall():
            text += u"* [[%s]] (%s) \r\n" % l
        
        re = self.cache.cursor.execute("SELECT count(*), replics FROM articles GROUP BY replics;")
        text += u"== По количеству реплик == \r\n"
        for l in re.fetchall():
            text += u"* Обсуждения %s статей имеют %s реплик\r\n" % (l)
        
        re = self.cache.cursor.execute("SELECT topic, topic, n, ts FROM updates ORDER BY n DESC;")
        text += u"== Последние обновления == \r\n"
        for l in re.fetchall():
            text += u"* [[Википедия:К улучшению/Тематические обсуждения/%s|%s]]: (Статей %s, обновлена %s) \r\n" % (l)
        text += u"== Примечания ==\r\n{{примечания}}"
        
        P = wikipedia.Page(self.site, u"Википедия:К улучшению/Тематические обсуждения/Статистика")
        P.put(text, u"Обновление статистики", botflag = True)

    def run(self):
        """entry point"""
        if self.action == "all":
            self.load_all()
        self.update_stats()

if __name__ == "__main__":
    A = AllAFI(sys.argv[1])
    A.run()
