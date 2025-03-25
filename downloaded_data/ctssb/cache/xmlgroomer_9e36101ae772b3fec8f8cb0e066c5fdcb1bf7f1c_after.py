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

def fix_affiliation(root):
    global output
    for author in root.xpath("//contrib[@contrib-type='author']"):
        aff = author.xpath("xref[@ref-type='aff']")
        name = author.xpath("name/surname")[0].text
        if not aff:
            author.insert(1, etree.fromstring("""<xref ref-type='aff' rid='aff1'/>"""))
            output += 'correction: set rid=aff1 for '+name+'\n'
        elif aff[0].attrib['rid'] == 'aff':
            aff[0].attrib['rid'] = 'aff1'
            output += 'correction: set rid=aff1 for '+name+'\n'
    return root
groomers.append(fix_affiliation)

def fix_corresp(root):
    global output
    for corresp in root.xpath("//corresp"):
        if corresp.xpath("label"):
            author_notes = corresp.getparent()
            author_notes.replace(corresp, etree.fromstring(re.sub(r'(<label>|</label>)', r'', etree.tostring(corresp))))
            output += 'correction: removed label tag from corresp '+corresp.attrib['id']+'\n'
    return root
groomers.append(fix_corresp)

def fix_pubdate(root):
    global output
    doi = get_doi(root)
    proc = subprocess.Popen(['php', '/var/local/scripts/production/getPubdate.php', doi], shell=False, stdout=subprocess.PIPE)
    pubdate = proc.communicate()[0]
    if int(pubdate[:4]) > 2000:
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

def fix_related_article(root):
    global output
    h = '{http://www.w3.org/1999/xlink}href'
    related = root.xpath("//related-article")
    for link in related:
        if re.match(r'info:doi/[a-z]{4}\.[0-9]{7}', link.attrib[h]):
            old_link = link.attrib[h]
            link.attrib[h] = link.attrib[h].replace('info:doi/', 'info:doi/10.1371/journal.')
            output += 'correction: changed related article link from '+old_link+' to '+link.attrib[h]+'\n'
    return root
groomers.append(fix_related_article)

def fix_xref(root):
    global output
    for xref in root.xpath("//xref[@ref-type='bibr']"):
        rid = xref.attrib['rid']
        if not xref.text and rid.startswith('B'):
            if xref.tail:
                if xref.getprevious() is not None:
                    xref.getprevious().tail = (xref.getprevious().tail or '') + xref.tail
                else:
                    xref.getparent().text = (xref.getparent().text or '') + xref.tail
            xref.getparent().remove(xref)
            output += 'correction: removed closed xref bibr '+rid+'\n'
    return root
groomers.append(fix_xref)

def fix_title(root):
    global output
    for title in root.xpath("//title"):
        if title.text and re.search(r'\s$', title.text):
            title.text = title.text.strip()
            output += 'correction: removed whitespace from end of title '+title.text+'\n'
    return root
groomers.append(fix_title)

def fix_headed_title(root):
    global output
    for title in root.xpath("//sec[@sec-type='headed']/title"):
        if re.search(r':$', title.text):
            old_title = title.text
            title.text = re.sub(r':$', r'', title.text)
            output += 'correction: removed punctuation from headed title '+old_title+'\n'
    return root
groomers.append(fix_headed_title)

def fix_bold_heading(root):
    global output
    for title in root.xpath("//sec/title"):
        if title.xpath("bold"):
            sec = title.getparent()
            sec.replace(title, etree.fromstring(re.sub(r'(<bold>|</bold>)', r'', etree.tostring(title))))
            output += 'correction: removed bold tags from sec '+sec.attrib['id']+' title\n'
    return root
groomers.append(fix_bold_heading)

def fix_bold_caption(root):
    global output
    for caption in root.xpath("//table-wrap/caption"):
        if caption.xpath("bold") or caption.xpath("p"):
            table_wrap = caption.getparent()
            new_caption = re.sub(r'(<bold>|</bold>)', r'', etree.tostring(caption)).replace('<p>','<title>').replace('</p>','</title>')
            table_wrap.replace(caption, etree.fromstring(new_caption))
            output += 'correction: removed bold tags from '+table_wrap.xpath("label")[0].text+' caption\n'
    return root
groomers.append(fix_bold_caption)

def fix_formula(root):
    global output
    for formula in root.xpath("//fig//caption//disp-formula") + root.xpath("//table//disp-formula"):
        formula.tag = 'inline-formula'
        formula.attrib.pop('id')
        graphic = formula.xpath("graphic")[0]
        graphic.tag = 'inline-graphic'
        graphic.attrib.pop('position')
        output += 'correction: changed disp-formula to inline-formula for '+graphic.attrib['{http://www.w3.org/1999/xlink}href']+'\n'
    return root
groomers.append(fix_formula)

def fix_label(root):
    global output
    refnums = ''
    for label in root.xpath("//ref/label"):
        if list(label.iterdescendants()):
            text = next(s for s in [x.text for x in label.iterdescendants()] if s)
            refnums += text+' '
            label.clear()
            label.text = text
    if refnums:
        output += 'correction: removed tags inside reference labels '+refnums+'\n'
    return root
groomers.append(fix_label)

def fix_url(root):
    global output
    h = '{http://www.w3.org/1999/xlink}href'
    for link in root.xpath("//ext-link"):
        old_link = link.attrib[h]
        # remove whitespace
        if re.search(r'\s', link.attrib[h]):
            link.attrib[h] = re.sub(r'\s', r'', link.attrib[h])
        # prepend http:// if not there
        if not link.attrib[h].startswith('http'):
            link.attrib[h] = 'http://' + link.attrib[h]
        # prepend dx.doi.org/ for doi
        if re.match(r'http://10\.[0-9]{4}', link.attrib[h]):
            link.attrib[h] = link.attrib[h].replace('http://', 'http://dx.doi.org/')
        # prepend www.ncbi.nlm.nih.gov/pubmed/ for pmid
        if re.match(r'http://[0-9]{7,8}$', link.attrib[h]) or link.attrib['ext-link-type'] == 'pmid':
            link.attrib[h] = link.attrib[h].replace('http://', 'http://www.ncbi.nlm.nih.gov/pubmed/')
        if old_link != link.attrib[h]:
            output += 'correction: changed link from '+old_link+' to '+link.attrib[h]+'\n'        
    return root
groomers.append(fix_url)

def fix_merops_link(root):
    global output
    refnums = ''
    for link in root.xpath("//ext-link[@ext-link-type='doi' or @ext-link-type='pmid' or not(@ext-link-type)]"):
        link.attrib['ext-link-type'] = 'uri'
        link.attrib['{http://www.w3.org/1999/xlink}type'] = 'simple'
        refnums += list(link.iterancestors("ref"))[0].xpath("label")[0].text+' '
    if refnums:
        output += 'correction: set ext-link-type=uri and xlink:type=simple in journal references '+refnums+'\n'
    return root
groomers.append(fix_merops_link)

def fix_comment(root):
    global output
    refnums = ''
    for comment in root.xpath("//comment"):
        if comment.tail and comment.tail.startswith("."):
            comment.tail = re.sub(r'^\.', r'', comment.tail)
            refnums += list(comment.iterancestors("ref"))[0].xpath("label")[0].text+' '
    if refnums:
        output += 'correction: removed period after comment end tag in journal references '+refnums+'\n'
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

def fix_extension(root):
    global output    
    for si in root.xpath("//supplementary-material"):
        typ = si.xpath("caption/p")[-1].text
        if re.match(r'\(.*\)', typ):
            filename = si.attrib['{http://www.w3.org/1999/xlink}href']
            ext = typ.strip('()').lower()
            if re.match(r's[0-9]', filename[-4:]):
                si.attrib['{http://www.w3.org/1999/xlink}href'] = filename+'.'+ext
                output += 'correction: set extension of '+filename+' to '+ext+' for '+si.xpath("label")[0].text+'\n'
    return root
groomers.append(fix_extension)

def fix_mimetype(root):
    global output
    for si in root.xpath("//supplementary-material"):
        typ = si.xpath("caption/p")[-1].text
        if re.match(r'\(.*\)', typ):
            mime, enc = mimetypes.guess_type('x.'+typ.strip('()'), False)
            if 'mimetype' not in si.attrib or mime != si.attrib['mimetype']:
                si.attrib['mimetype'] = mime
                output += 'correction: set mimetype of '+typ+' to '+mime+' for '+si.xpath("label")[0].text+'\n'
    return root
groomers.append(fix_mimetype)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('usage: xmlgroomer.py before.xml after.xml')
    log = open('/var/local/scripts/production/xmlgroomer/log/log', 'a')
    log.write('-'*50 + '\n'+time.strftime("%Y-%m-%d %H:%M:%S   "))
    try: 
        parser = etree.XMLParser(recover = True)
        e = etree.parse(sys.argv[1], parser)
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
    log.write(output.encode('ascii','ignore'))
    log.close()
    print output
