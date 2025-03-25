#!/usr/bin/python

import re
import sys
import pprint
from collections import defaultdict, namedtuple

DOMAIN, \
FIRST_SLASH, \
SECOND_SLASH, \
THIRD_SLASH, \
FOURTH_SLASH, \
FULL_URL = range(6)

Extraction = namedtuple('Extraction', 'keep feedfn')

def httpify(p):
	return p.replace("https://", "http://", 1)

def last3seg(p): # get only last three segments of domain
	try:
		schema, _, domain, rest = p.split("/", 3)
		segments = domain.split(".")[-3:]
		return schema + "//" + ".".join(segments) + "/" + rest
	except ValueError:
		schema, _, domain = p.split("/", 2)
		segments = domain.split(".")[-3:]
		return schema + "//" + ".".join(segments)

def get_domain_and_path(p):
	schema, _, domain_and_path = p.split("/", 2)
	return domain_and_path

def get_non_www_domain_segment(p, index, skiplist=set()):
	schema, _, domain_and_path = p.split("/", 2)
	candidate = domain_and_path.split(".")[index - 1]
	if candidate == "www" or candidate in skiplist:
		candidate = domain_and_path.split(".")[index - 1 + 1]
	return candidate

def get_path_segment(p, index):
	try:
		schema, _, domain, rest = p.split("/", 3)
		return rest.split('/')[index - 1]
	except ValueError:
		return ''

def tumblr_com(p):
	if ".media.tumblr.com" in p or "/media.tumblr.com" in p:
		return []
	return [httpify(last3seg(p)) + "/rss"]

def wordpress_com(p):
	assert not p.endswith('/'), p
	# This handles username.wordpress.com and username.files.wordpress.com
	username = get_non_www_domain_segment(p, 1)
	return [
		 "http://%s.wordpress.com/feed" % (username,)
		,"http://%s.wordpress.com/feed/" % (username,)
		,"http://%s.wordpress.com/feed/atom" % (username,)
		,"http://%s.wordpress.com/feed/atom/" % (username,)
		,"http://%s.wordpress.com/feed/rss" % (username,)
		,"http://%s.wordpress.com/feed/rss/" % (username,)
		,"http://%s.wordpress.com/comments/feed" % (username,)
		,"http://%s.wordpress.com/comments/feed/" % (username,)
		,"http://%s.wordpress.com/?feed=rss2" % (username,) # rare
		,"http://%s.wordpress.com/?feed=atom" % (username,) # rare
		,"http://%s.wordpress.com/?feed=comments-rss2" % (username,) # very rare
	]

def blogspot_com(p):
	if ".bp.blogspot.com" in p:
		return []
	username = get_non_www_domain_segment(p, 1)
	return [
		 'http://%s.blogspot.com/feeds/posts/default' % (username,)
		,'http://%s.blogspot.com/feeds/posts/default?alt=rss' % (username,)
		,'http://%s.blogspot.com/atom.xml' % (username,)
		,'http://%s.blogspot.com/rss.xml' % (username,)
	]

def blog4ever_com(p):
	if p.endswith("/rss_articles.xml") or p.endswith("/rss_articles_commentaires.xml"):
		return [p]
	else:
		return []

def groups_google_com(p):
	groupname = get_path_segment(p, 2)
	return [
		 'http://groups.google.com/group/%s/feed/rss_v2_0_msgs.xml' % (groupname,)
		,'http://groups.google.com/group/%s/feed/atom_v1_0_msgs.xml' % (groupname,)
		,'https://groups.google.com/group/%s/feed/rss_v2_0_msgs.xml' % (groupname,)
		,'https://groups.google.com/group/%s/feed/atom_v1_0_msgs.xml' % (groupname,)
		,'http://groups.google.com/group/%s/feed/rss_v2_0_msgs.xml' % (groupname.lower(),)
		,'http://groups.google.com/group/%s/feed/atom_v1_0_msgs.xml' % (groupname.lower(),)
		,'https://groups.google.com/group/%s/feed/rss_v2_0_msgs.xml' % (groupname.lower(),)
		,'https://groups.google.com/group/%s/feed/atom_v1_0_msgs.xml' % (groupname.lower(),)
	]

def groups_yahoo_com(p):
	return [
		 "http://rss.%s/rss" % (get_domain_and_path(last3seg(p)),)
		,"http://%s/messages?rss=1" % (get_domain_and_path(last3seg(p)),)
		,"http://rss.%s/rss" % (get_domain_and_path(last3seg(p)).lower(),)
		,"http://%s/messages?rss=1" % (get_domain_and_path(last3seg(p)).lower(),)
	]

def ameblo_jp(p):
	username = get_path_segment(p, 1)
	return [
		 "http://rssblog.ameba.jp/%s/rss20.xml" % (username,)
		,"http://feedblog.ameba.jp/rss/ameblo/%s/rss20.xml" % (username,)
		,"http://fullrss.net/a/http/feedblog.ameba.jp/rss/ameblo/%s/rss20.xml" % (username,)
	]

def wretch_cc(p):
	username = get_path_segment(p, 2)
	return [
		 "http://www.wretch.cc/blog/%s&rss20=1" % (username,)
		,"http://www.wretch.cc/blog/%s&rss20=1" % (username.lower(),)
	]

def livejournal_com(p):
	username = get_non_www_domain_segment(p, 1)
	return [
		 'http://%s.livejournal.com/data/rss' % (username,)
		,'http://%s.livejournal.com/data/atom' % (username,)
		,'http://www.livejournal.com/users/%s/data/rss' % (username,)
		,'http://www.livejournal.com/users/%s/data/atom' % (username,)
	]

def typepad_com(p): # also handles typepad.jp
	if p.endswith("/") or not (p.startswith("http://") or p.startswith("https://")):
		# No blogname, so we don't know where the feed is
		return []
	blogname = get_path_segment(p, 1)
	if blogname.startswith("."):
		return []
	return [
		 p + '/atom.xml'
		,p + '/rss.xml'
		,p + '/index.rdf'
	]

def posterous_com(p):
	username = get_non_www_domain_segment(p, 1)
	return [
		'http://%s.posterous.com/rss.xml' % (username,)
	]

def egloos_com(p):
	username = get_non_www_domain_segment(p, 1)
	return ["http://rss.egloos.com/blog/" + username]

def hatena_ne_jp(p):
	if p.endswith("/"):
		# No username
		return []
	return [
		 p + "/rss"
		,p + "/rss2"
	]

def blog_hexun_com(p):
	username = get_non_www_domain_segment(p, 1)
	return [
		 "http://%s.blog.hexun.com/rss2.aspx" % (username,)
		,"http://fulltextrssfeed.com/%s.blog.hexun.com/rss2.aspx" % (username,)
	]

def rss_exblog_jp(p):
	username = get_path_segment(p, 2)
	return [
		 "http://%s.exblog.jp/index.xml" % (username,)
		,"http://%s.exblog.jp/atom.xml" % (username,)
		,"http://rss.exblog.jp/rss/exblog/%s/index.xml" % (username,)
		,"http://rss.exblog.jp/rss/exblog/%s/atom.xml" % (username,)
	]

def blog_roodo_com(p):
	username = get_path_segment(p, 1)
	return [
		  "http://blog.roodo.com/%s/rss.xml" % (username,)
		 ,"http://blog.roodo.com/%s/atom.xml" % (username,)
	]

def exblog_jp(p):
	username = get_non_www_domain_segment(p, 1)
	return [
		 "http://%s.exblog.jp/index.xml" % (username,)
		,"http://%s.exblog.jp/atom.xml" % (username,)
		,"http://rss.exblog.jp/rss/exblog/%s/index.xml" % (username,)
		,"http://rss.exblog.jp/rss/exblog/%s/atom.xml" % (username,)
	]

def blog_shinobi_jp(p):
	username = get_non_www_domain_segment(p, 1, skiplist=set(["file"]))
	return [
		 "http://%s.blog.shinobi.jp/RSS/" % (username,)
		,"http://%s.blog.shinobi.jp/ATOM/" % (username,)
		,"http://blogrss.shinobi.jp/rss/ninja/%s/atom" % (username,)
	]

def blogger_com_feeds(p):
	feedid = get_path_segment(p, 2)
	return [
		 "http://www.blogger.com/feeds/%s/posts/default" % (feedid,)
		,"http://www.blogger.com/feeds/%s/posts/full" % (feedid,)
		,"http://www.blogger.com/feeds/%s/posts/default?alt=rss" % (feedid,)
		,"http://www.blogger.com/feeds/%s/posts/default?alt=rss&orderby=published" % (feedid,)
	]

def feedsky_com(p):
	if not (p.startswith("http://") or p.startswith("https://")):
		return []
	if p.endswith(".html") or "/~feedsky/" in p:
		return []
	return [p]

def fc2_com(p):
	if not (p.startswith("http://") or p.startswith("https://")):
		return []

	part1 = get_non_www_domain_segment(p, 1)
	part2 = get_non_www_domain_segment(p, 2)

	return [
		 "http://%s.%s.fc2.com/?xml" % (part1, part2)
		,"http://feeds.fc2.com/fc2/xml?host=%s.%s" % (part1, part2)
		,"http://mrss.dokoda.jp/a/http/%s.%s.fc2.com/?xml" % (part1, part2)
		,"http://mrss.dokoda.jp/a/http/feeds.fc2.com/fc2/xml?host=%s.%s" % (part1, part2)
	]

def formspring_me(p):
	username = get_path_segment(p, 1)
	return [
		 "http://www.formspring.me/profile/%s.rss" % (username,)
		,"http://www.formspring.me/profile/%s.rss" % (username.lower(),)
	]

def diarynote_jp(p):
	sub = get_non_www_domain_segment(p, 1)

	return [
		 "http://%s.diarynote.jp/rss?version=2_0" % (sub,)
		,"http://%s.diarynote.jp/rss?version=1_0" % (sub,)
	]

def blog_livedoor_jp(p):
	username = get_path_segment(p, 1)
	return [
		 "http://blog.livedoor.jp/%s/index.rdf" % (username,)
		,"http://blog.livedoor.jp/%s/atom.xml" % (username,)
	]

def feed43_com(p):
	if not p.endswith(".xml"):
		return []

	feedname = get_path_segment(p, 1)
	return [
		 "http://feed43.com/%s" % (feedname,)
		,"http://www.feed43.com/%s" % (feedname,)
	]

def qzone_qq_com(p):
	sub = get_non_www_domain_segment(p, 1)
	return [
		"http://feeds.qzone.qq.com/cgi-bin/cgi_rss_out?uin=%s" % (sub,)
	]

def blog_163_com(p):
	blogname = get_non_www_domain_segment(p, 1)
	if blogname == "blog":
		blogname = get_path_segment(p, 1)
	return [
		 "http://%s.blog.163.com/rss/" % (blogname,)
		,"http://blog.163.com/%s/rss/" % (blogname,)
	]

def xanga_com(p):
	blogname = get_non_www_domain_segment(p, 1)
	return [
		 "http://www.xanga.com/rss.aspx?user=%s" % (blogname,)
		,"http://www.xanga.com/rssfeed.aspx?u=%s" % (blogname,)
		,"http://%s.xanga.com/rss/" % (blogname,)
		,"http://%s.xanga.com/rss" % (blogname,)
		,"http://www.xanga.com/%s/rss" % (blogname,)
	]

def as_is(p):
	p = p.replace("feed://", "http://", 1)
	if not (p.startswith("http://") or p.startswith("https://")):
		return []
	return [p]

def as_is_and_lower(p):
	p = p.replace("feed://", "http://", 1)
	if not (p.startswith("http://") or p.startswith("https://")):
		return []
	return [p, p.lower()]

def get_wordpress_feed_urls_for_base(base):
	return [
		 "%s/feed" % (base,)
		,"%s/feed/" % (base,)
		,"%s/feed/atom/" % (base,)
		,"%s/feed/rss/" % (base,)
		,"%s/comments/feed" % (base,)
		,"%s/comments/feed/" % (base,)
		,"%s/?feed=rss2" % (base,)
		,"%s/?feed=atom" % (base,)
		,"%s/?feed=comments-rss2" % (base,)
		,"%s/wp-rss2.php" % (base,)
		,"%s/wp-atom.php" % (base,)
	]

YYYY_MM_PATH_RE = re.compile("/20[01][0-9]/[01][0-9]/")

def get_guessed_feeds(url):
	if not (url.startswith("http://") or url.startswith("https://")):
		return []

	# TODO: vbulletin
	for wordpress_pattern in ("/wp-content/", "/wordpress/", "/category/"):
		if wordpress_pattern in url and not "=http://" in url and not "=https://" in url:
			base = url.split(wordpress_pattern, 1)[0]
			# Filter out all sorts of crap like google image search URLs
			if len(base) <= 70:
				return get_wordpress_feed_urls_for_base(base)

	if (url.endswith(".html") or url.endswith("/")) and not ".blogspot." in url and not "=http" in url and not '?http' in url:
		yyyy_mm_matches = YYYY_MM_PATH_RE.findall(url)
		if yyyy_mm_matches:
			base = url.split(yyyy_mm_matches[0], 1)[0]
			if len(base) <= 100:
				##print "XX", base
				return get_wordpress_feed_urls_for_base(base)

	return []

path_to_extraction = {
	 'tumblr.com': Extraction(keep=DOMAIN, feedfn=tumblr_com)
	,'community.livejournal.com': Extraction(keep=FIRST_SLASH, feedfn=None)
	,'www.livejournal.com/users/': Extraction(keep=SECOND_SLASH, feedfn=None)
	,'www.livejournal.com/community/': Extraction(keep=SECOND_SLASH, feedfn=None)
	,'livejournal.com': Extraction(keep=DOMAIN, feedfn=livejournal_com)
	,'wordpress.com': Extraction(keep=DOMAIN, feedfn=wordpress_com)
	,'blogspot.com': Extraction(keep=DOMAIN, feedfn=blogspot_com)
	,'blogger.com/feeds/': Extraction(keep=SECOND_SLASH, feedfn=blogger_com_feeds)
	,'feeds.feedburner.com': Extraction(keep=FIRST_SLASH, feedfn=as_is_and_lower)
	,'feeds2.feedburner.com': Extraction(keep=FIRST_SLASH, feedfn=as_is_and_lower)
	,'feeds.rapidfeeds.com': Extraction(keep=FIRST_SLASH, feedfn=as_is)
	,'posterous.com': Extraction(keep=DOMAIN, feedfn=posterous_com)
	,'groups.google.com/group/': Extraction(keep=SECOND_SLASH, feedfn=groups_google_com)
	,'groups.yahoo.com/group/': Extraction(keep=SECOND_SLASH, feedfn=groups_yahoo_com)
	,'typepad.com': Extraction(keep=FIRST_SLASH, feedfn=typepad_com)
	,'typepad.jp': Extraction(keep=FIRST_SLASH, feedfn=typepad_com)
	,'blog.roodo.com': Extraction(keep=FIRST_SLASH, feedfn=blog_roodo_com)
	,'diarynote.jp': Extraction(keep=DOMAIN, feedfn=diarynote_jp)
	,'ameblo.jp': Extraction(keep=FIRST_SLASH, feedfn=ameblo_jp)
	,'rssblog.ameba.jp': Extraction(keep=FIRST_SLASH, feedfn=ameblo_jp)
	,'wretch.cc/blog/': Extraction(keep=SECOND_SLASH, feedfn=wretch_cc)
	,'formspring.me': Extraction(keep=FIRST_SLASH, feedfn=formspring_me)
	,'blog.shinobi.jp': Extraction(keep=DOMAIN, feedfn=blog_shinobi_jp)
	,'rss.exblog.jp/rss/exblog/': Extraction(keep=THIRD_SLASH, feedfn=rss_exblog_jp)
	,'exblog.jp': Extraction(keep=DOMAIN, feedfn=exblog_jp)
	,'blog.hexun.com': Extraction(keep=DOMAIN, feedfn=blog_hexun_com)
	,'blog.hexun.com.tw': Extraction(keep=DOMAIN, feedfn=blog_hexun_com)
	,'blog.livedoor.jp': Extraction(keep=FIRST_SLASH, feedfn=blog_livedoor_jp)
	,'altervista.org': Extraction(keep=DOMAIN, feedfn=None)
	,'feeds.qzone.qq.com/cgi-bin/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'qzone.qq.com': Extraction(keep=DOMAIN, feedfn=qzone_qq_com)
	,'blog.163.com': Extraction(keep=FIRST_SLASH, feedfn=blog_163_com)
	,'inube.com': Extraction(keep=DOMAIN, feedfn=None)
	,'rss.my.nero.com/user/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'my.nero.com': Extraction(keep=DOMAIN, feedfn=None)
	,'feed43.com': Extraction(keep=FIRST_SLASH, feedfn=feed43_com)
	,'static.blog4ever.com': Extraction(keep=FULL_URL, feedfn=blog4ever_com)
	,'www.xanga.com/rss.aspx': Extraction(keep=FULL_URL, feedfn=as_is)
	,'xanga.com': Extraction(keep=DOMAIN, feedfn=xanga_com)
	,'feed.pixnet.net/blog/posts/rss/': Extraction(keep=FOURTH_SLASH, feedfn=as_is)
	,'feed.pixnet.net/blog/posts/atom/': Extraction(keep=FOURTH_SLASH, feedfn=as_is)
	,'pixnet.net': Extraction(keep=DOMAIN, feedfn=None)
	,'twitter.com': Extraction(keep=FIRST_SLASH, feedfn=None)
	,'rss2lj.net': Extraction(keep=FULL_URL, feedfn=as_is)
	,'gplusrss.com': Extraction(keep=FULL_URL, feedfn=as_is)
	,'googleplusfeed.net': Extraction(keep=FULL_URL, feedfn=as_is)
	,'twitter-rss.com': Extraction(keep=FULL_URL, feedfn=as_is)
	,'dreamwidth.org': Extraction(keep=DOMAIN, feedfn=None)
	,'blog.com': Extraction(keep=DOMAIN, feedfn=None)
	,'pipes.yahoo.com/pipes/pipe.run': Extraction(keep=FULL_URL, feedfn=as_is)
	,'page2rss.com/atom/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'page2rss.com/rss/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'boards.4chan.org': Extraction(keep=FIRST_SLASH, feedfn=None)
	,'dis.4chan.org/atom/': Extraction(keep=SECOND_SLASH, feedfn=None)
	,'vox.com': Extraction(keep=DOMAIN, feedfn=None)
	,'jux.com': Extraction(keep=DOMAIN, feedfn=None)
	,'at.webry.info': Extraction(keep=DOMAIN, feedfn=None)
	,'rsspect.com': Extraction(keep=FULL_URL, feedfn=as_is)
	,'buzz.googleapis.com/feeds/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'craigslist.org': Extraction(keep=FIRST_SLASH, feedfn=None)
	,'www.reddit.com/user/': Extraction(keep=SECOND_SLASH, feedfn=None)
	,'pay.reddit.com/user/': Extraction(keep=SECOND_SLASH, feedfn=None)
	,'www.reddit.com/r/': Extraction(keep=SECOND_SLASH, feedfn=None)
	,'pay.reddit.com/r/': Extraction(keep=SECOND_SLASH, feedfn=None)
	,'blog.myspace.com/blog/rss.cfm': Extraction(keep=FULL_URL, feedfn=as_is)
	,'spaces.live.com': Extraction(keep=DOMAIN, feedfn=None)
	,'rss.searchyc.com': Extraction(keep=FULL_URL, feedfn=as_is)
	,'lesswrong.com/user/': Extraction(keep=SECOND_SLASH, feedfn=None)
	,'www.quora.com': Extraction(keep=FIRST_SLASH, feedfn=None)
	,'www.google.com/reader/public/': Extraction(keep=FULL_URL, feedfn=as_is)
	# skipped kickstarter
	,'del.icio.us/rss/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'del.icio.us/tag/': Extraction(keep=SECOND_SLASH, feedfn=None)
	,'youtube.com/user/': Extraction(keep=SECOND_SLASH, feedfn=None)
	,'youtube.com/rss/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'gdata.youtube.com/feeds/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'multiply.com': Extraction(keep=DOMAIN, feedfn=None)
	,'bandcamp.com/feed/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'bandcamp.com': Extraction(keep=DOMAIN, feedfn=None)
	,'hatena.ne.jp': Extraction(keep=FIRST_SLASH, feedfn=hatena_ne_jp)
	# vimeo.com needs to be filtered afterwards to get usernames and exclude video IDs
	,'vimeo.com': Extraction(keep=FIRST_SLASH, feedfn=None)
	,'flickr.com/services/feeds/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'flickr.com/recent_comments_feed.gne': Extraction(keep=FULL_URL, feedfn=as_is)
	,'api.twitter.com/1/statuses/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'twitter.com/statuses/user_timeline/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'rss.egloos.com': Extraction(keep=FULL_URL, feedfn=as_is)
	,'egloos.com': Extraction(keep=DOMAIN, feedfn=egloos_com)
	,'podomatic.com': Extraction(keep=DOMAIN, feedfn=None)
	,'secuobs.com/revue/xml/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'blogs.com': Extraction(keep=DOMAIN, feedfn=None)
	,'mysyndicaat.com/myfeed/feed/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'blog.sina.com.cn/rss/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'blog.sina.com.cn': Extraction(keep=FIRST_SLASH, feedfn=None)
	,'loadaveragezero.com/drx/rss/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'feedsky.com': Extraction(keep=FULL_URL, feedfn=feedsky_com)
	,'rss.pics.livedoor.com': Extraction(keep=FULL_URL, feedfn=as_is)
	,'news.livedoor.com/rss/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'podbean.com': Extraction(keep=DOMAIN, feedfn=None)
	,'blogs.msdn.com': Extraction(keep=FIRST_SLASH, feedfn=None)
	,'libsyn.com': Extraction(keep=DOMAIN, feedfn=None)
	,'prlog.org/rss/': Extraction(keep=FULL_URL, feedfn=as_is)
	,'npr.org/rss/': Extraction(keep=FULL_URL, feedfn=as_is)
	# TODO: spaces.msn.com; has annoying pattern
	,'blog.yam.com/rss.php': Extraction(keep=FULL_URL, feedfn=as_is)
	,'blog.yam.com': Extraction(keep=FIRST_SLASH, feedfn=None)
	# TODO: news.google.com, needs filter on output=(rss|atom)
	,'webcast.berkeley.edu/media/common/rss/': Extraction(keep=FULL_URL, feedfn=as_is)
	,"fullrss.net": Extraction(keep=FULL_URL, feedfn=as_is)
	,"mrss.dokoda.jp/a/": Extraction(keep=FULL_URL, feedfn=as_is)
	,"fc2.com": Extraction(keep=DOMAIN, feedfn=fc2_com)
}

_domain_to_extraction = defaultdict(list)
for k, extraction in path_to_extraction.iteritems():
	try:
		domain, path = k.split('/', 1)
	except ValueError:
		domain = k
		path = ''
	_domain_to_extraction[domain].append((path, extraction))
del domain, path, k, extraction

for k, extraction in _domain_to_extraction.iteritems():
	_domain_to_extraction[k] = sorted(_domain_to_extraction[k], key=lambda x: len(x), reverse=True)
del k, extraction

##pprint.pprint(dict(_domain_to_extraction))


def up_domain_variants(domain):
	variants = []
	parts = domain.split('.')
	for how_many in xrange(1, len(parts)):
		variant = '.'.join(parts[-how_many:])
		variants.append(variant)

	variants.reverse()
	return [domain] + variants

assert up_domain_variants("blah.cnn.com") == ["blah.cnn.com", "cnn.com", "com"]


def get_extraction(domain, rest):
	extractions = None

	for domain_variant in up_domain_variants(domain):
		extractions = _domain_to_extraction.get(domain_variant)
		if extractions:
			break

	if not extractions:
		return None

	extraction = None
	for extraction_path, maybe_extraction in extractions:
		##print rest, action_path
		if rest.startswith(extraction_path):
			extraction = maybe_extraction
			break

	return extraction


assert get_extraction("blah.com", "") == None
assert get_extraction("youtube.com", "user/blah") == Extraction(keep=SECOND_SLASH, feedfn=None)
assert get_extraction("youtube.com", "usx") == None
assert get_extraction("bandcamp.com", "feed/blah") == Extraction(keep=FULL_URL, feedfn=as_is)
assert get_extraction("bandcamp.com", "fee") == Extraction(keep=DOMAIN, feedfn=None)
assert get_extraction("x.bandcamp.com", "") == Extraction(keep=DOMAIN, feedfn=None)


def without_query(rest):
	rest = rest.split("?", 1)[0]
	rest = rest.split("&", 1)[0]
	return rest


EXTRACT, PRINT_FEED_URLS = range(2)

def main():
	if sys.argv[1:] == ["print_paths"]:
		print "\n".join(sorted(path_to_extraction.keys()))
		sys.exit(0)

	mode = EXTRACT
	if sys.argv[1:] == ["print_feed_urls"]:
		mode = PRINT_FEED_URLS

	last_printed = None
	for line in sys.stdin:
		url = line.rstrip()
		try:
			schema, _, domain, rest = url.split('/', 3)
		except ValueError:
			try:
				schema, _, domain = url.split('/', 2)
				rest = ""
			except ValueError:
				continue

		extraction = get_extraction(domain, rest)
		if extraction is None:
			if mode == PRINT_FEED_URLS:
				guessed_feeds = get_guessed_feeds(url)
				if guessed_feeds:
					print "\n".join(guessed_feeds)

			# Don't want this URL
			continue

		##print url, extraction
		keep = extraction.keep
		if keep == FULL_URL:
			maybe_print = url
		elif keep == DOMAIN:
			maybe_print = schema + "//" + domain
		elif keep == FIRST_SLASH:
			maybe_print = schema + "//" + domain + "/" + without_query(rest.split("/", 1)[0])
		elif keep == SECOND_SLASH:
			maybe_print = schema + "//" + domain + "/" + without_query("/".join(rest.split("/", 2)[:2]))
		elif keep == THIRD_SLASH:
			maybe_print = schema + "//" + domain + "/" + without_query("/".join(rest.split("/", 2)[:3]))
		elif keep == FOURTH_SLASH:
			maybe_print = schema + "//" + domain + "/" + without_query("/".join(rest.split("/", 2)[:4]))

		if last_printed != maybe_print:
			if mode == EXTRACT:
				print maybe_print
			elif mode == PRINT_FEED_URLS:
				if extraction.feedfn:
					feed_urls = extraction.feedfn(maybe_print)
					if feed_urls:
						print "\n".join(feed_urls)
			else:
				1/0
			last_printed = maybe_print


if __name__ == '__main__':
	main()
