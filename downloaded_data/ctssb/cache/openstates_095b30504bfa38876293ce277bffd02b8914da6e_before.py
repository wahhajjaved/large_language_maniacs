import re
import difflib
import urlparse
import collections

import lxml.html

from billy.scrape.legislators import LegislatorScraper, Legislator
import scrapelib

from .apiclient import ApiClient, BadApiResponse


class INLegislatorScraper(LegislatorScraper):
    jurisdiction = 'in'

    def api_legislators(self, session_year):
        '''Since we're scraping per term, this iterator
        '''
        legislators = self.client.get('chamber_legislators',
            session=session_year, chamber=self.api_chamber)
        for data in legislators['items']:
            yield data
        while True:
            if 'nextLink' in legislators:
                legislators = self.client.get_relurl(legislators['nextLink'])
                for data in legislators['items']:
                    yield data
            else:
                break

    def get_termdata(self, term_id):
        '''The api legislator calls expect a "session" parameter, which
        is simply a four-digit year. Aside from death, legislators generally
        shouldn't change between sessions (only terms), and tests with api
        responses for different years within a single term returned the same
        data.
        '''
        for term in self.metadata['terms']:
            if term['name'] == term_id:
                return term

    def get_api_id(self, photo_url):
        return photo_url.split('_').pop()

    def scrape(self, chamber, term):
        self.termdata = self.get_termdata(term)
        self.requests_per_minute = 15
        self.client = ApiClient(self)
        self.api_chamber = dict(upper='senate', lower='house')[chamber]

        legislators = {}
        districts = self.get_districts(chamber)
        years = (self.termdata['start_year'], self.termdata['start_year'])
        for session_year in years:
            for data in self.api_legislators(session_year):
                try:
                    data = self.client.get_relurl(data['link'])
                except BadApiResponse:
                    # At this point, we don't have district for the
                    # legislator, so we have to skip.
                    self.warning('Got bad API Response at %r' % data['link'])
                    self.warning('Skipping legislator: %r' % data)
                    continue
                name = '%s %s' % (data['firstName'], data['lastName'])

                matches = difflib.get_close_matches(name, districts)
                if not matches:
                    msg = "Found no matching district for legislator %r." % data
                    self.warning(msg)
                    continue
                key = matches[0]
                district = districts[key]['district']
                leg_url = districts[key]['url']

                photo_url = data['pngDownloadLink']
                photo_url = urlparse.urljoin(self.client.root, photo_url)

                api_id = self.get_api_id(photo_url)
                if api_id not in legislators:
                    leg = Legislator(
                        term, chamber, district, name,
                        first_name=data['firstName'],
                        last_name=data['lastName'],
                        party=data['party'],
                        photo_url=photo_url)
                else:
                    leg = legislators[api_id]
                    import pdb; pdb.set_trace()

                url = self.client.make_url('chamber_legislators',
                    session=session_year, chamber=self.api_chamber)
                leg.add_source(url)
                leg.add_source(leg_url)

                for comm in data['committees']:
                    leg.add_role(
                        'committee member', term=term, chamber=chamber,
                        commmittee=comm['name'])

                # Woooooo! Email addresses are guessable in IN/
                tmpl = '{chamber[0]}{district}@iga.in.gov'
                leg['email'] = tmpl.format(chamber=chamber, district=district)

                # Add district generic IGA address, usually the only thing available.
                tmpl = '''{title} {full_name}
                    200 W. Washington St.
                    Indianapolis, IN 46204'''
                title = 'Senator' if chamber == 'upper' else 'Representative'
                address = tmpl.format(title=title, full_name=leg['full_name'])
                address = re.sub(r' +', ' ', address)

                # Get the contact details.
                deets_getter = 'get_contact_%s_%s' % (chamber, data['party'])
                deets_getter = getattr(self, deets_getter)
                deets = deets_getter(leg, leg_url)

                # If email found, use that instead of guessed email.
                if deets is not None:
                    if deets.get("email"):
                        leg['email'] = deets.pop("email")

                    office = dict(deets or {},
                        address=address, name='District Office',
                        type='district', fax=None)

                    if office not in leg['offices']:
                        leg.add_office(**office)

                self.save_legislator(leg)

    def get_districts(self, chamber):
        '''In an epic winfail, API doesn't provide districts, so we have to
        get them from the public site.
        '''
        urls = {
            'upper': ('https://secure.in.gov/cgi-bin/legislative/listing/'
                      'listing-2.pl?data=district&chamber=Senate'),
            'lower': ('https://secure.in.gov/cgi-bin/legislative/listing/'
                      'listing-2.pl?data=district&chamber=House')}
        res = collections.defaultdict(dict)
        url = urls[chamber]
        html = self.urlopen(url)
        doc = lxml.html.fromstring(html)
        scrub = lambda el: el.text_content().strip()
        for tr in doc.xpath('//table/tr')[1:]:
            dist1, leg1, _, dist2, leg2 = tr

            dist1 = scrub(dist1)
            leg1_name = leg1.xpath('string(a)').strip()
            leg1_url = leg1.xpath('a/@href')[0]

            dist2 = scrub(dist2)
            leg2_name = leg2.xpath('string(a)').strip()
            leg2_url = leg2.xpath('a/@href')[0]

            res[leg1_name] = dict(district=dist1, url=leg1_url)
            res[leg2_name] = dict(district=dist2, url=leg2_url)
        return res


    def get_contact_upper_Republican(self, leg, leg_url):
        '''Get contact info for Senate Republicans.
        '''
        deets = {}
        try:
            html = self.urlopen(leg_url)
        except:
            return
        doc = lxml.html.fromstring(html)
        phone = email = None
        for el in doc.iterdescendants():
            tail = (el.tail or '').strip()

            if not email and tail.startswith('Email:'):
                email = deets['email'] = tail.replace('Email: ', '').strip()

            if not phone and tail.startswith('Phone:'):
                phone = tail.replace('Phone: ', '').strip()
                if ' or ' in phone:
                    phone, _, _ = phone.partition(' or ')
                deets['phone'] = phone
        return deets

    def get_contact_lower_Republican(self, leg, leg_url):
        '''Get contact info for House Republicans.
        '''
        try:
            html = self.urlopen(leg_url)
        except:
            return
        doc = lxml.html.fromstring(html)
        phones = []
        for el in doc.iterdescendants():
            tail = (el.tail or '').strip()
            m = re.search(r'\(\d{3}\)\s+\d{3}-\d{4}', tail)
            if m:
                phones.append(m.group())
        phone = ', '.join(phones)
        return dict(phone=phone or None)

    def get_contact_upper_Democratic(self, leg, leg_url):
        '''Get contact info for Senate Dems.
        '''
        deets = {}
        tmpl = ('http://www.in.gov/legislative/senate_democrats/'
                'homepages/s%s/contactme.htm')
        contact_url = tmpl % leg['roles'][0]['district']
        try:
            html = self.urlopen(leg_url)
        except:
            return
        doc = lxml.html.fromstring(html)
        for el in doc.iterdescendants():
            tail = (el.tail or '').strip()
            m = re.search(r'\(\d{3}\)\s+\d{3}-\d{4}', tail)
            if m:
                deets['phone'] = m.group()
        return deets

    def get_contact_lower_Democratic(self, leg, leg_url):
        '''Get contact info for House Dems.
        '''
        return dict(phone="800-382-9842")
