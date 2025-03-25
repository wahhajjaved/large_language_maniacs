#!/usr/bin/env python
# usage: xmlgroomer.py before.xml after.xml

import sys
import time
import subprocess
import lxml.etree as etree
import mimetypes
import re

groomers = []
output = ''

def get_doi(root):
    return root.xpath("//article-id[@pub-id-type='doi']")[0].text

def fix_article_type(root):
    global output
    for typ in root.xpath("//article-categories//subj-group[@subj-group-type='heading']/subject"):
        if typ.text == 'Clinical Trial':
            typ.text = 'Research Article'
            output += 'correction: changed article type from Clinical Trial to Research Article\n'
    return root
groomers.append(fix_article_type)

def fix_article_title(root):
    global output
    for title in root.xpath("//title-group/article-title"):
        if re.search(r'[\t\n\r]| {2,}', unicode(title.text)):
            old_title = title.text
            title.text = re.sub(r'[\t\n\r ]+', r' ', unicode(title.text))
            output += 'correction: changed article title from '+old_title+' to '+title.text+'\n'
    return root
groomers.append(fix_article_title)

def fix_pubdate(root):
    global output
    doi = get_doi(root)
    proc = subprocess.Popen(['php', '/var/local/scripts/production/getPubdate.php', doi], shell=False, stdout=subprocess.PIPE)
    pubdate = proc.communicate()[0]
    em = {'year':pubdate[:4], 'month':str(int(pubdate[5:7])), 'day':str(int(pubdate[8:]))}
    for date in root.xpath("//pub-date[@pub-type='epub']"):
        for field in ['year','month','day']:
            xml_val = date.xpath(field)[0].text
            if xml_val != em[field]:
                date.xpath(field)[0].text = em[field]
                output += 'correction: changed pub '+field+' from '+xml_val+' to '+em[field]+'\n'
    return root
groomers.append(fix_pubdate)

def fix_collection(root):
    global output
    for coll in root.xpath("//pub-date[@pub-type='collection']"):
        for field in ['year','month']:
            if coll.xpath(field):
                pub_val = root.xpath("//pub-date[@pub-type='epub']/"+field)[0].text
                xml_val = coll.xpath(field)[0].text
                if xml_val != pub_val:
                    coll.xpath(field)[0].text = pub_val
                    output += 'correction: changed collection '+field+' from '+xml_val+' to '+pub_val+'\n'
    return root
groomers.append(fix_collection)

def fix_volume(root):
    global output
    year = root.xpath("//pub-date[@pub-type='epub']/year")[0].text
    journal = root.xpath("//journal-id[@journal-id-type='pmc']")[0].text
    volumes = {'plosbiol':2002, 'plosmed':2003, 'ploscomp':2004, 'plosgen':2004, 'plospath':2004,
                'plosone':2005, 'plosntds':2006}
    for volume in root.xpath("//article-meta/volume"):
        correct_volume = str(int(year) - volumes[journal])
        if volume.text != correct_volume:
            old_volume = volume.text
            volume.text = correct_volume
            output += 'correction: changed volume from '+old_volume+' to '+volume.text+'\n'
    return root
groomers.append(fix_volume)

def fix_issue(root):
    global output
    month = root.xpath("//pub-date[@pub-type='epub']/month")[0].text
    for issue in root.xpath("//article-meta/issue"):
        if issue.text != month:
            old_issue = issue.text
            issue.text = month
            output += 'correction: changed issue from '+old_issue+' to '+issue.text+'\n'
    return root
groomers.append(fix_issue)

def fix_copyright(root):
    global output
    year = root.xpath("//pub-date[@pub-type='epub']/year")[0].text
    for copyright in root.xpath("//article-meta//copyright-year"):
        if copyright.text != year:
            old_copyright = copyright.text
            copyright.text = year
            output += 'correction: changed copyright year from '+old_copyright+' to '+copyright.text+'\n'
    return root
groomers.append(fix_copyright)

def fix_elocation(root):
    global output
    doi = get_doi(root)
    correct_eloc = 'e'+str(int(doi[-7:]))
    elocs = root.xpath("//elocation-id")
    for eloc in elocs:
        if eloc.text != correct_eloc:
            old_eloc = eloc.text
            eloc.text = correct_eloc
            output += 'correction: changed elocation from '+old_eloc+' to '+eloc.text+'\n'
    if not elocs:
        eloc = etree.Element('elocation-id')
        eloc.text = correct_eloc
        issue = root.xpath("//article-meta/issue")[0]
        parent = issue.getparent()
        parent.insert(parent.index(issue) + 1, eloc)
        output += 'correction: added missing elocation '+eloc.text+'\n'
    return root
groomers.append(fix_elocation)

def fix_journal_ref(root):
    global output
    for link in root.xpath("//mixed-citation[@publication-type='journal']/ext-link"):
        parent = link.getparent()
        refnum = parent.getparent().xpath("label")[0].text
        index = parent.index(link)
        comment = etree.Element('comment')
        comment.append(link)
        previous = parent.getchildren()[index-1]
        if previous.tail:
            comment.text = previous.tail
            previous.tail = ''
        parent.insert(index, comment)
        output += 'correction: added comment tag around journal reference '+refnum+' link\n'
    return root
groomers.append(fix_journal_ref)

def fix_url(root):
    global output
    for link in root.xpath("//ext-link"):
        h = '{http://www.w3.org/1999/xlink}href'
        assert h in link.attrib  # error: ext-link does not have href
        # remove whitespace
        if re.search(r'\s', link.attrib[h]):
            old_link = link.attrib[h]
            link.attrib[h] = re.sub(r'\s', r'', link.attrib[h])
            output += 'correction: changed link from '+old_link+' to '+link.attrib[h]+'\n'
        # prepend dx.doi.org if url is only a doi
        if re.match(r'http://10.[0-9]{4}', link.attrib[h]):
            old_link = link.attrib[h]
            link.attrib[h] = link.attrib[h].replace('http://', 'http://dx.doi.org/')
            output += 'correction: changed link from '+old_link+' to '+link.attrib[h]+'\n'
    return root
groomers.append(fix_url)

def fix_comment(root):
    global output
    for comment in root.xpath("//comment"):
        if comment.tail and comment.tail.startswith("."):
            refnum = comment.getparent().getparent().xpath("label")[0].text
            comment.tail = re.sub(r'^\.', r'', comment.tail)
            output += 'correction: removed period after comment end tag in journal reference '+refnum+'\n'
    return root
groomers.append(fix_comment)

def fix_provenance(root):
    global output
    for prov in root.xpath("//author-notes//fn[@fn-type='other']/p/bold"):
        if prov.text == 'Provenance:':
            fngroup = etree.Element('fn-group')
            fngroup.append(prov.getparent().getparent())
            reflist = root.xpath("//ref-list")[0]
            parent = reflist.getparent()
            parent.insert(parent.index(reflist) + 1, fngroup)
            output += 'correction: moved provenance from author-notes to fn-group after references\n'
    return root
groomers.append(fix_provenance)

def fix_mimetype(root):
    global output
    for sup in root.xpath("//supplementary-material"):
        typ = sup.xpath("caption/p")[-1].text.strip('()')
        mime, enc = mimetypes.guess_type('x.'+typ, False)
        if 'mimetype' not in sup.attrib or mime != sup.attrib['mimetype']:
            sup.attrib['mimetype'] = mime
            output += 'correction: set mimetype of '+typ+' to '+mime+' for '+sup.xpath("label")[0].text+'\n'
    return root
groomers.append(fix_mimetype)

def fix_empty_element(root):
    global output
    # starts from the leaves of the tree to remove nested empty elements
    for element in reversed(list(root.iterdescendants())):
        if not element.text and not element.attrib and not element.getchildren():
            output += 'correction: removed empty element '+element.tag+' at '+root.getroottree().getpath(element)+'\n'
            element.getparent().remove(element)
    return root
groomers.append(fix_empty_element)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('usage: xmlgroomer.py before.xml after.xml')
    log = open('/var/local/scripts/production/xmlgroomer/log', 'a')
    log.write('-'*50 + '\n'+time.strftime("%Y-%m-%d %H:%M:%S   "))
    try: 
        parser = etree.XMLParser(recover = True)
        e = etree.parse(sys.argv[1],parser)
        root = e.getroot()
    except Exception as ee:
        log.write('** error parsing: '+str(ee)+'\n')
        log.close()
        raise
    try: log.write(get_doi(root)+'\n')
    except: log.write('** error getting doi\n')
    for groomer in groomers:
        try: root = groomer(root)
        except Exception as ee: log.write('** error in '+groomer.__name__+': '+str(ee)+'\n')
    e.write(sys.argv[2], xml_declaration = True, encoding = 'UTF-8')
    log.write(output)
    log.close()
    print output.strip()
