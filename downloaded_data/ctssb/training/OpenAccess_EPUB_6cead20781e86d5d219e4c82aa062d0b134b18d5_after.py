"""
The OPF file has three basic jobs: it presents metadata in the Dublin Core
format, it presents a manifest of all the files within the ePub, and it
provides a spine for a document-level read order. The latter two jobs shall
depend very little, if at all, on the particular publisher or article. The
Dublin Core metadata will require publisher-specific definitions of metadata
conversion.
"""

import OpenAccess_EPUB.dublincore as dc
import OpenAccess_EPUB.utils as utils
import datetime
import os.path
import xml.dom.minidom
import logging

log = logging.getLogger('OPF')


class MetaOPF(object):
    """
    Represents the OPF document and the methods needed to produce it. Dublin
    Core metadata is referenced by this class per publisher.
    """

    def __init__(self, version, location, collection_mode=False):
        log.info('Instantiating OPF class')
        self.doi = ''
        self.dois = []
        self.collection_mode = collection_mode
        if self.collection_mode:
            log.debug('Collection Mode')
        self.version = version
        self.location = location
        #Initiate the document
        self.init_opf_document()
        log.info('Created the OPF document')
        #List of articles included
        self.articles = []

    def init_opf_document(self):
        """
        This method creates the initial DOM document for the content.opf file
        """
        impl = xml.dom.minidom.getDOMImplementation()
        self.doc = impl.createDocument(None, 'package', None)
        #Grab the root <package> node
        self.package = self.doc.lastChild
        #Set attributes for this node, including namespace declarations
        self.package.setAttribute('version', '2.0')
        self.package.setAttribute('unique-identifier', 'PrimaryID')
        self.package.setAttribute('xmlns:opf', 'http://www.idpf.org/2007/opf')
        self.package.setAttribute('xmlns:dc', 'http://purl.org/dc/elements/1.1/')
        self.package.setAttribute('xmlns', 'http://www.idpf.org/2007/opf')
        self.package.setAttribute('xmlns:oebpackage', 'http://openebook.org/namespaces/oeb-package/1.0/')
        #Create the sub elements for <package>
        opf_sub_elements = ['metadata', 'manifest', 'spine', 'guide']
        for el in opf_sub_elements:
            self.package.appendChild(self.doc.createElement(el))
        self.metadata, self.manifest, self.spine, self.guide = self.package.childNodes
        self.spine.setAttribute('toc', 'ncx')
        #Here we create a custom collection unique identifier string
        #Consists of software name and version along with timestamp
        t = datetime.datetime(1, 1, 1)
        self.ccuid = 'OpenAccess_EPUBv{0}-{1}'.format('__version__',
                                                      t.utcnow().__str__())

    def parse_article(self, article):
        """
        Process the contents of an article to build the content.opf
        """
        self.doi = article.getDOI()
        self.dois.append(self.doi)
        self.article = article
        self.a_doi = self.doi.split('/')[1]
        self.a_doi_dashed = self.a_doi.replace('.', '-')
        self.articles.append(article)
        if not self.collection_mode:
            self.single_metadata(article.metadata)
        else:
            self.collection_metadata(article.metadata)
        self.add_to_spine()

    def single_metadata(self, ameta):
        """
        This method handles the metadata for single article ePubs. Should be
        overridden by publisher-specific classes.
        """
        pass

    def collection_metadata(self, ameta):
        """
        This method handles the metadata for a collection. Should be overridden
        by publisher-specific classes.
        """
        pass

    def make_manifest(self):
        """
        The Manifest declares all of the documents within the ePub (except
        mimetype and META-INF/container.xml). It should be generated as a
        final step in the ePub process and after all articles have been parsed
        into <metadata> and <spine>.
        """
        mimetypes = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'xml':
                     'application/xhtml+xml', 'png': 'image/png', 'css':
                     'text/css', 'ncx': 'application/x-dtbncx+xml', 'gif':
                     'image/gif', 'tif': 'image/tif', 'pdf': 'application/pdf'}
        current_dir = os.getcwd()
        os.chdir(self.location)
        for path, _subname, filenames in os.walk('OPS'):
            path = path[4:]
            if filenames:
                for filename in filenames:
                    _name, ext = os.path.splitext(filename)
                    ext = ext[1:]
                    new = self.manifest.appendChild(self.doc.createElement('item'))
                    if path:
                        new.setAttribute('href', '/'.join([path, filename]))
                    else:
                        new.setAttribute('href', filename)
                    new.setAttribute('media-type', mimetypes[ext])
                    if filename == 'toc.ncx':
                        new.setAttribute('id', 'ncx')
                    elif ext == 'png':
                        trim = path[7:]
                        new.setAttribute('id', '{0}-{1}'.format(trim, filename.replace('.', '-')))
                    else:
                        new.setAttribute('id', filename.replace('.', '-'))
        os.chdir(current_dir)

    def add_to_spine(self):
        idref = '{0}-' + '{0}-xml'.format(self.a_doi_dashed)
        main_ref = self.spine.appendChild(self.doc.createElement('itemref'))
        bib_ref = self.doc.createElement('itemref')
        tab_ref = self.doc.createElement('itemref')
        for r, i, l in [(main_ref, 'main', 'yes'),
                        (bib_ref, 'biblio', 'yes'), (tab_ref, 'tables', 'no')]:
            r.setAttribute('linear', l)
            r.setAttribute('idref', idref.format(i))
        try:
            b = self.article.root_tag.getElementsByTagName('back')[0]
        except IndexError:
            pass
        else:
            if b.getElementsByTagName('ref'):
                self.spine.appendChild(bib_ref)
        if self.article.root_tag.getElementsByTagName('table-wrap'):
            self.spine.appendChild(tab_ref)

    def write(self):
        self.make_manifest()
        filename = os.path.join(self.location, 'OPS', 'content.opf')
        with open(filename, 'w') as output:
            output.write(self.doc.toprettyxml(encoding='utf-8'))


class FrontiersOPF(MetaOPF):
    """
    This is the OPF class intended for use with Frontiers articles.
    """

    def single_metadata(self, article_metadata):
        """
        This method handles the metadata for single article Frontiers ePubs.
        """
        #For brevity
        ameta = article_metadata

        log.info('Using Frontiers singleMetadata')
        #Make the dc:identifier using the DOI of the article
        dc_identifier = dc.identifier(self.doi, self.doc, primary=True)
        dc_identifier.setAttribute('opf:scheme', 'DOI')
        self.metadata.appendChild(dc_identifier)
        #Make the dc:language, it defaults to english
        self.metadata.appendChild(dc.language(self.doc))
        #Make the dc:title using the article title
        title = utils.serializeText(ameta.title.article_title, [])
        self.metadata.appendChild(dc.title(title, self.doc))
        #Make the dc:rights using the metadata in permissions
        s = utils.serializeText(ameta.permissions.statement, [])
        l = utils.serializeText(ameta.permissions.license, [])
        self.metadata.appendChild(dc.rights(' '.join([s, l]), self.doc))
        #Make the dc:creator elements for each contributing author
        #Note that the file-as name is: Surname, G(iven Initial)
        for contrib in ameta.contrib:
            if contrib.attrs['contrib-type'] == 'author':
                name = contrib.getName()[0]  # Work with only first name listed
                surname = name.surname
                given = name.given
                try:
                    gi = given[0]
                except IndexError:
                    auth = surname
                    file_as = surname
                else:
                    auth = ' '.join([given, surname])
                    file_as = ', '.join([surname, gi])
                dc_creator = dc.creator(auth, file_as, self.doc)
                self.metadata.appendChild(dc_creator)
        #Make the dc:contributor elements for editors and reviewers
        for fn in ameta.author_notes.getElementsByTagName('fn'):
            dc_contrib = []
            if fn.getAttribute('fn-type') == 'edited-by':
                p = fn.getElementsByTagName('p')[0]
                if p.firstChild.data[:11] == 'Edited by: ':
                    editor = p.firstChild.data[11:].split(',')[0]
                    dc_contrib = [dc.contributor(editor, self.doc, role='edt')]
                elif p.firstChild.data[:13] == 'Reviewed by: ':
                    reviewers = p.firstChild.data[13:].split(';')
                    dc_contrib = []
                    for r in reviewers:
                        r_text = r.split(',')[0].lstrip()
                        dc_contrib.append(dc.contributor(r_text, self.doc, role='rev'))
            for dc_c in dc_contrib:
                self.metadata.appendChild(dc_c)
        #Make the dc:date elements for important dates regarding the article
        #Creation
        try:
            credate = ameta.history['accepted']
        except KeyError:
            pass
        else:
            y, m, d = credate.year, credate.month, credate.day
            dc_date = dc.date(y, m, d, 'creation', self.doc)
            self.metadata.appendChild(dc_date)
        #Publication
        try:
            pubdate = ameta.pub_date['epub']
        except KeyError:
            pass
        else:
            y, m, d = pubdate.year, pubdate.month, pubdate.day
            dc_date = dc.date(y, m, d, 'publication', self.doc)
            self.metadata.appendChild(dc_date)
        #Create the epub format declaration in dc:format
        self.metadata.appendChild(dc.epubformat(self.doc))
        #Create the dc:relation for related articles
        #This is not yet implemented
        #self.metadata.appendChild(dc.relation(relation, self.doc))
        #Create the dc:publisher element
        self.metadata.appendChild(dc.publisher('Frontiers', self.doc))
        #Create the dc:type element
        self.metadata.appendChild(dc.texttype(self.doc))
        #Create the dc:subject elements for each keyword
        for kwd in ameta.all_kwds:
            kwd_text = utils.serializeText(kwd.node, [])
            self.metadata.appendChild(dc.subject(kwd_text, self.doc))
        #Create the dc:description element from the abstract if available
        if ameta.abstract:
            abstract_text = utils.serializeText(ameta.abstract[0].node, [])
            self.metadata.appendChild(dc.description(abstract_text, self.doc))

    def collection_metadata(self, article_metadata):
        """
        This method handles the metadata for a Frontiers article in a
        collection.
        """
        log.info('Using Frontiers collectionMetadata')


class PLoSOPF(MetaOPF):
    """
    This is the OPF class intended for use with PLoS articles.
    """

    def single_metadata(self, article_metadata):
        """
        This method handles the metadata for single article PLoS ePubs.
        """
        log.info('Using PLoS singleMetadata')

        #For brevity
        ameta = article_metadata

        #Make the dc:identifier using the DOI of the article
        dc_identifier = dc.identifier(self.doi, self.doc, primary=True)
        dc_identifier.setAttribute('opf:scheme', 'DOI')
        self.metadata.appendChild(dc_identifier)

        #Make the dc:language, it defaults to english
        self.metadata.appendChild(dc.language(self.doc))

        #Make the dc:title using the article title
        title = utils.serializeText(ameta.title.article_title, [])
        self.metadata.appendChild(dc.title(title, self.doc))

        #Make the dc:rights using the metadata in permissions
        license = utils.serializeText(ameta.permissions.license)
        self.metadata.appendChild(dc.rights(license, self.doc))

        #Make the dc:creator elements for each contributing author
        #Note that the file-as name is: Surname, G(iven Initial)
        for contrib in ameta.contrib:
            if contrib.attrs['contrib-type'] == 'author':
                if contrib.collab:
                    auth = utils.serializeText(contrib.collab[0])
                    file_as = auth
                elif contrib.anonymous:
                    auth = 'Anonymous'
                    file_as = auth
                else:
                    name = contrib.getName()[0]  # Work with only first name listed
                    surname = name.surname
                    given = name.given
                    try:
                        gi = given[0]
                    except IndexError:
                        auth = surname
                        file_as = surname
                    else:
                        auth = ' '.join([given, surname])
                        file_as = ', '.join([surname, gi])
                dc_creator = dc.creator(auth, file_as, self.doc)
                self.metadata.appendChild(dc_creator)

        #Make the dc:contributor elements for editors
        for contrib in ameta.contrib:
            if contrib.attrs['contrib-type'] == 'editor':
                name = contrib.getName()[0]
                try:
                    given_initial = name.given[0]
                except TypeError:
                    editor_name = name.surname
                    file_name = name.surname
                #except IndexError:
                #    editor_name = name.surname
                #    file_name = name.surname
                else:
                    editor_name = name.given + ' ' + name.surname
                    file_name = name.surname + ', ' + given_initial
                dc_contrib = dc.contributor(editor_name, self.doc, file_as=file_name, role='edt')
                self.metadata.appendChild(dc_contrib)

        #Make the dc:date elements for important dates regarding the article
        #Creation
        creation_date = ameta.history['accepted']
        if creation_date:
            dc_date = dc.date(creation_date.year,
                              creation_date.month,
                              creation_date.day,
                              event='creation',
                              dom=self.doc)
            self.metadata.appendChild(dc_date)
        #Publication
        try:
            pub_date = ameta.pub_date['epub']
        except KeyError:
            pass
        else:
            pub_date = dc.date(pub_date.year,
                               pub_date.month,
                               pub_date.day,
                               event='publication',
                               dom=self.doc)
            self.metadata.appendChild(pub_date)

        #Create the epub format declaration in dc:format
        self.metadata.appendChild(dc.epubformat(self.doc))

        #Create the dc:relation for related articles
        #This is not yet implemented
        #self.metadata.appendChild(dc.relation(relation, self.doc))

        #Create the dc:publisher element
        self.metadata.appendChild(dc.publisher('Public Library of Science', self.doc))

        #Create the dc:type element
        self.metadata.appendChild(dc.texttype(self.doc))

        #Create the dc:subject elements for each keyword
        for kwd in ameta.all_kwds:
            kwd_text = utils.serializeText(kwd.node, [])
            self.metadata.appendChild(dc.subject(kwd_text, self.doc))

        #Create the dc:description element from the abstract if available
        if ameta.abstract:
            abstract_text = utils.serializeText(ameta.abstract[0].node, [])
            self.metadata.appendChild(dc.description(abstract_text, self.doc))

    def collection_metadata(self, article_metadata):
        """
        This method handles the metadata for a PLoS article in a collection.
        """
        log.info('Using PLoS collectionMetadata')

    def add_to_spine(self):
        idref = '{0}-' + '{0}-xml'.format(self.a_doi_dashed)
        main_ref = self.spine.appendChild(self.doc.createElement('itemref'))
        bib_ref = self.doc.createElement('itemref')
        tab_ref = self.doc.createElement('itemref')
        for r, i, l in [(main_ref, 'main', 'yes'),
                        (bib_ref, 'biblio', 'yes'), (tab_ref, 'tables', 'no')]:
            r.setAttribute('linear', l)
            r.setAttribute('idref', idref.format(i))
        try:
            b = self.article.root_tag.getElementsByTagName('back')[0]
        except IndexError:
            pass
        else:
            if b.getElementsByTagName('ref'):
                self.spine.appendChild(bib_ref)
        #Here is the change for PLoS, this is for support of old articles
        #which may not have the proper table format
        table_wraps = self.article.root_tag.getElementsByTagName('table-wrap')
        tables = False
        for table_wrap in table_wraps:
            if table_wrap.getElementsByTagName('alternatives') and table_wrap.getElementsByTagName('table'):
                tables = True
        if tables:
            self.spine.appendChild(tab_ref)
