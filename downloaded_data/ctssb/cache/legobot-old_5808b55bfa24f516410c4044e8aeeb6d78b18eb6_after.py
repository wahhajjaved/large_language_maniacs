#!usr/bin/python
import os, sys, re
sys.path.append(os.environ['HOME'] + '/pyenwiki')
import wikipedia, catlib, pagegenerators, query
def API(params):
	return query.GetData(params, useAPI = True, encodeTitle = False)
def unicodify(text):
    if not isinstance(text, unicode):
        return text.decode('utf-8')
    return text
def delink(link):
	link = re.compile(r'\[\[(.*?)\]\]', re.IGNORECASE).sub(r'\1', str(link))
	return link
site = wikipedia.getSite()
def createlist(cat, wpproj, raw = False, cats = True):
	category = catlib.Category(site, cat)
	gen = pagegenerators.CategorizedPageGenerator(category, recurse=True)
	wikitext = ''
	wikitext2 = ''
	wikitext3 = ''
	
	if not cats:
		for page in gen:
			wikitext = wikitext+'\n*'+str(page)
			link = delink(str(page))
			print link
			wikitext2 = wikitext2+'\n'+link
		wikitext = unicodify(wikitext)
	if cats:
		subcats = category.subcategories(recurse = True)
		for subcat in subcats:
			newtext = retpages(subcat)
			wikitext3 += newtext
		wikitext3 = unicodify(wikitext3)
	
	page = wikipedia.Page(site, wpproj + '/Articles')
	if not cats:
		page.put(wikitext, 'Updating watchlist (Trial BRFA)')
	if cats:
		page.put(wikitext3, 'Updating watchlist (Trial BRFA)')
	wikitext2 = '<pre>\n' + wikitext2 + '\n</pre>'
	wikitext2 = unicodify(wikitext2)
	if raw == True:
		page = wikipedia.Page(site, wpproj + '/Articles/raw')
		page.put(wikitext2, 'Updating raw watchlist (Trial BRFA)')
def retpages(cat):
	cat = delink(str(cat))
	wikitext = '==[[:%s]]==\n' %cat
	print 'Getting pages in [[%s]] using API...' %cat
	params = {
		'action':'query',
		'list':'categorymembers',
		'cmtitle':cat,
		'cmlimit':'500',
	}
	res = API(params)
	res = res['query']['categorymembers']
	for article in res:
		try:
			if article['ns'] != (14 or '14'):
				wikitext += '*[[%s]]\n' %str(article['title']).encode("utf-8")
		except KeyError:
			return ''
	return wikitext

def main():
	createlist('Canadian football', 'Wikipedia:WikiProject Canadian football', raw = True)
	
if __name__ == '__main__':
	try:
		main()
	finally:
		wikipedia.stopme()