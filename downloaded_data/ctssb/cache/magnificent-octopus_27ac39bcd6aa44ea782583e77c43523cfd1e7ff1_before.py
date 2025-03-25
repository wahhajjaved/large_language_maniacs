from octopus.lib import dataobj
from octopus.lib import xml as xutil
from lxml import etree

class JATSException(Exception):
    def __init__(self, message, rawstring, *args, **kwargs):
        super(JATSException, self).__init__(message, *args, **kwargs)
        self.raw = rawstring

class EPMCFullTextException(JATSException):
    """
    Here for backwards compatibility
    """
    pass

class EPMCMetadataException(Exception):
    def __init__(self, message, rawstring, *args, **kwargs):
        super(EPMCMetadataException, self).__init__(message, *args, **kwargs)
        self.raw = rawstring

class EPMCMetadataXML(object):
    def __init__(self, raw=None, xml=None):
        self.raw = None
        self.xml = None
        if raw is not None:
            self.raw = raw
            try:
                self.xml = etree.fromstring(self.raw)
            except:
                raise JATSException("Unable to parse XML", self.raw)
        elif xml is not None:
            self.xml = xml

    def tostring(self):
        if self.raw is not None:
            return self.raw
        elif self.xml is not None:
            return etree.tostring(self.xml)

    @property
    def title(self):
        return xutil.xp_first_text(self.xml, "title")

    @property
    def publication_type(self):
        return xutil.xp_first_text(self.xml, "//pubTypeList/pubType")

    @property
    def language(self):
        return xutil.xp_first_text(self.xml, "language")

    @property
    def publication_date(self):
        pd = xutil.xp_first_text(self.xml, "firstPublicationDate")
        if pd is not None:
            return pd
        pd = xutil.xp_first_text(self.xml, "electronicPublicationDate")
        if pd is not None:
            return pd
        pd = xutil.xp_first_text(self.xml, "//journalInfo/printPublicationDate")
        return pd

    @property
    def pmid(self):
        return xutil.xp_first_text(self.xml, "pmid")

    @property
    def pmcid(self):
        return xutil.xp_first_text(self.xml, "pmcid")

    @property
    def doi(self):
        return xutil.xp_first_text(self.xml, "DOI")

    @property
    def issns(self):
        issn = xutil.xp_first_text(self.xml, "//journalInfo/journal/ISSN")
        essn = xutil.xp_first_text(self.xml, "//journalInfo/journal/ESSN")
        issns = []
        if issn is not None:
            issns.append(issn)
        if essn is not None:
            issns.append(essn)
        return issns

    @property
    def keywords(self):
        return xutil.xp_texts(self.xml, "//keywordList/keyword")

    @property
    def author_string(self):
        return xutil.xp_first_text(self.xml, "//authorString")

    @property
    def authors(self):
        """
        <fullName>Cerasoli E</fullName>
        <firstName>Eleonora</firstName>
        <lastName>Cerasoli</lastName>
        <initials>E</initials>
        <affiliation>Biotechnology Department, National Physical Laboratory Teddington, UK.</affiliation>
        """
        author_elements = self.xml.xpath("//authorList/author")
        obs = []
        for ael in author_elements:
            ao = {}

            fn = ael.find("fullName")
            if fn is not None:
                ao["fullName"] = fn.text

            first = ael.find("firstName")
            if first is not None:
                ao["firstName"] = first.text

            last = ael.find("lastName")
            if last is not None:
                ao["lastName"] = last.text

            inits = ael.find("initials")
            if inits is not None:
                ao["initials"] = inits.text

            aff = ael.find("affiliation")
            if aff is not None:
                ao["affiliation"] = aff.text

            if len(ao.keys()) > 0:
                obs.append(ao)

        return obs

    @property
    def grants(self):
        grant_elements = self.xml.xpath("//grantsList/grant")
        obs = []
        for ael in grant_elements:
            go = {}

            gid = ael.find("grantId")
            if gid is not None:
                go["grantId"] = gid.text

            ag = ael.find("agency")
            if ag is not None:
                go["agency"] = ag.text

            if len(go.keys()) > 0:
                obs.append(go)

        return obs

    @property
    def mesh_descriptors(self):
        return xutil.xp_texts(self.xml, "//meshHeadingList/meshHeading/descriptorName")


class EPMCMetadata(dataobj.DataObj):
    def __init__(self, raw):
        super(EPMCMetadata, self).__init__(raw)

    @property
    def pmcid(self):
        return self._get_single("pmcid", self._utf8_unicode(), allow_coerce_failure=False)

    @property
    def pmid(self):
        return self._get_single("pmid", self._utf8_unicode(), allow_coerce_failure=False)

    @property
    def doi(self):
        return self._get_single("doi", self._utf8_unicode(), allow_coerce_failure=False)

    @property
    def in_epmc(self):
        return self._get_single("inEPMC", self._utf8_unicode(), allow_coerce_failure=False)

    @property
    def is_oa(self):
        return self._get_single("isOpenAccess", self._utf8_unicode(), allow_coerce_failure=False)

    @property
    def issn(self):
        return self._get_single("journalInfo.journal.issn", self._utf8_unicode(), allow_coerce_failure=False)

    @property
    def journal(self):
        return self._get_single("journalInfo.journal.title", self._utf8_unicode(), allow_coerce_failure=False)

    @property
    def essn(self):
        return self._get_single("journalInfo.journal.essn", self._utf8_unicode(), allow_coerce_failure=False)

    @property
    def title(self):
        return self._get_single("title", self._utf8_unicode(), allow_coerce_failure=False)

class JATS(object):
    def __init__(self, raw=None, xml=None):
        self.raw = None
        self.xml = None
        if raw is not None:
            self.raw = raw
            try:
                self.xml = etree.fromstring(self.raw)
            except:
                raise JATSException("Unable to parse XML", self.raw)
        elif xml is not None:
            self.xml = xml

    @property
    def title(self):
        return xutil.xp_first_text(self.xml, "//title-group/article-title")

    @property
    def is_aam(self):
        manuscripts = self.xml.xpath("//article-id[@pub-id-type='manuscript']")
        return len(manuscripts) > 0

    def get_licence_details(self):
        # get the licence type
        l = self.xml.xpath("//license")
        if len(l) > 0:
            l = l[0]
        else:
            return None, None, None
        type = l.get("license-type")
        url = l.get("{http://www.w3.org/1999/xlink}href")

        # get the paragraph(s) describing the licence
        para = self.xml.xpath("//license/license-p")
        out = ""
        for p in para:
            out += etree.tostring(p)

        return type, url, out

    @property
    def copyright_statement(self):
        return xutil.xp_first_text(self.xml, "//copyright-statement")

    @property
    def categories(self):
        return xutil.xp_texts(self.xml, "//article-categories/subj-group/subject")

    @property
    def authors(self):
        aels = self.xml.xpath("//contrib-group/contrib[@contrib-type='author']")
        return self._make_contribs(aels)

    @property
    def contribs(self):
        cs = self.xml.xpath("//contrib-group/contrib")
        return self._make_contribs(cs)

    @property
    def emails(self):
        return xutil.xp_texts(self.xml, "//email")

    @property
    def keywords(self):
        return xutil.xp_texts(self.xml, "//kwd-group/kwd")

    @property
    def publisher(self):
        return xutil.xp_first_text(self.xml, "//publisher/publisher-name")

    @property
    def publication_date(self):
        # first look for an explicit publication date
        pds = self.xml.xpath("//article-meta/pub-date[@date-type='pub']")
        if len(pds) > 0:
            return self._make_date(pds[0])

        # if not, look for exactly one pub-date and use that
        pds = self.xml.xpath("//article-meta/pub-date")
        if len(pds) == 1:
            return self._make_date(pds[0])

        # otherwise, insufficient information
        return None

    @property
    def date_accepted(self):
        das = self.xml.xpath("//history/date[@date-type='accepted']")
        if len(das) > 0:
            return self._make_date(das[0])

    @property
    def date_submitted(self):
        rcs = self.xml.xpath("//history/date[@date-type='received']")
        if len(rcs) > 0:
            return self._make_date(rcs[0])

    @property
    def issn(self):
        return xutil.xp_texts(self.xml, "//journal-meta/issn")

    @property
    def pmcid(self):
        id = xutil.xp_first_text(self.xml, "//article-meta/article-id[@pub-id-type='pmcid']")
        if not id.startswith("PMC"):
            id = "PMC" + id
        return id

    @property
    def doi(self):
        return xutil.xp_first_text(self.xml, "//article-meta/article-id[@pub-id-type='doi']")

    def _make_date(self, element):
        ob = xutil.objectify(element)
        year = ob.get("year")
        month = ob.get("month", "01")
        day = ob.get("day", "01")
        if len(month) < 2:
            month = "0" + month
        if len(day) < 2:
            day = "0" + day
        if year is None or len(year) != 4:
            return None
        return year + "-" + month + "-" + day

    def _make_contribs(self, elements):
        obs = []

        for c in elements:
            con = {}

            # first see if there is a name we can pull out
            name = c.find("name")
            if name is not None:
                sn = name.find("surname")
                if sn is not None:
                    con["surname"] = sn.text

                gn = name.find("given-names")
                if gn is not None:
                    con["given-names"] = gn.text

            # see if there's an email address
            email = c.find("email")
            if email is not None:
                con["email"] = email.text

            # now do the affiliations (by value and by (x)reference)
            affs = []

            aff = c.find("aff")
            if aff is not None:
                contents = aff.xpath("string()")
                norm = " ".join(contents.split())
                affs.append(norm)

            xrefs = c.findall("xref")
            for x in xrefs:
                if x.get("ref-type") == "aff":
                    affid = x.get("rid")
                    xp = "//aff[@id='" + affid + "']"
                    aff_elements = self.xml.xpath(xp)
                    for ae in aff_elements:
                        contents = ae.xpath("string()")
                        norm = " ".join(contents.split())
                        affs.append(norm)

            if len(affs) > 0:
                con["affiliations"] = affs

            if len(con.keys()) > 0:
                obs.append(con)

        return obs

    def tostring(self):
        if self.raw is not None:
            return self.raw
        elif self.xml is not None:
            return etree.tostring(self.xml)