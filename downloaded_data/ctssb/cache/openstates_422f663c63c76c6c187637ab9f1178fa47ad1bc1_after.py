import datetime
import os
import re

from billy.scrape import ScrapeError
from billy.scrape.bills import BillScraper, Bill
from billy.scrape.votes import Vote
from billy.scrape.utils import convert_pdf

import lxml.html


def action_type(action):
    action = action.lower()
    atypes = []
    if re.match('^read (the )?(first|1st) time', action):
        atypes.append('bill:introduced')
        atypes.append('bill:reading:1')
    elif re.match('^read second time', action):
        atypes.append('bill:reading:2')
    elif re.match('^read third time', action):
        atypes.append('bill:reading:3')

    if re.match('^referred to (the )?committee', action):
        atypes.append('committee:referred')
    elif re.match('^referred to (the )?subcommittee', action):
        atypes.append('committee:referred')

    if re.match('^introduced and adopted', action):
        atypes.append('bill:introduced')
        #not sure if adopted means passed
        atypes.append('bill:passed')
    elif re.match('^introduced and read first time', action):
        atypes.append('bill:introduced')
        atypes.append('bill:reading:1')
    elif re.match('^introduced', action):
        atypes.append('bill:introduced')

    if atypes:
        return atypes

    return ['other']


class SCBillScraper(BillScraper):
    state = 'sc'
    urls = {
        'bill-detail' : "http://scstatehouse.gov/cgi-bin/web_bh10.exe?bill1=%s&session=%s" ,
        'vote-url' : "http://www.scstatehouse.gov/php/votehistory.php?type=BILL&session=%s&bill_number=%s",
        'vote-url-base' : "http://www.scstatehouse.gov",

        'lower' : {
          'daily-bill-index': "http://www.scstatehouse.gov/hintro/hintros.php",
        },

        'upper' : {
          'daily-bill-index': "http://www.scstatehouse.gov/sintro/sintros.php",
        }
    }

    def scrape_vote_history(self, bill, vurl):
        html = self.urlopen(vurl)
        doc = lxml.html.fromstring(html)
        doc.make_links_absolute(vurl)

        # skip first two rows
        for row in doc.xpath('//table/tr')[2:]:
            tds = row.getchildren()
            if len(tds) != 10:
                self.warning('irregular vote row: %s' % vurl)
                continue
            (timestamp, motion, vote, yeas, nays, nv, exc, abst,
             total, result) = tds

            timestamp = timestamp.text.replace(u'\xa0', ' ')
            timestamp = datetime.datetime.strptime(timestamp,
                                                   '%m/%d/%Y %H:%M %p')
            yeas = int(yeas.text)
            nays = int(nays.text)
            others = int(nv.text) + int(exc.text) + int(abst.text)
            assert yeas + nays + others == int(total.text)

            passed = (result.text == 'Passed')

            vote_link = vote.xpath('a')[0]
            if '[H]' in vote_link.text:
                chamber = 'lower'
            else:
                chamber = 'upper'

            vote = Vote(chamber, timestamp, motion.text, passed, yeas, nays,
                        others)
            vote.add_source(vurl)

            rollcall_pdf = vote_link.get('href')
            self.scrape_rollcall(vote, rollcall_pdf)
            vote.add_source(rollcall_pdf)

            bill.add_vote(vote)

    def scrape_rollcall(self, vote, vurl):
        (path, resp) = self.urlretrieve(vurl)
        pdflines = convert_pdf(path, 'text')
        os.remove(path)

        current_vfunc = None

        for line in pdflines.split('\n'):
            line = line.strip()

            # change what is being recorded
            if line.startswith('YEAS'):
                current_vfunc = vote.yes
            elif line.startswith('NAYS'):
                current_vfunc = vote.no
            elif (line.startswith('EXCUSED') or
                  line.startswith('NOT VOTING') or
                  line.startswith('ABSTAIN')):
                current_vfunc = vote.other
            # skip these
            elif not line or line.startswith('Page '):
                continue

            # if a vfunc is active
            elif current_vfunc:
                # split names apart by 3 or more spaces
                names = re.split('\s{3,}', line)
                for name in names:
                    if name:
                        current_vfunc(name.strip())


    def process_rollcall(self,chamber,vvote_date,bill,bill_id,action):
        self.debug("508 Roll call: [%s]" % action )
        if re.search(action,'Ayes'):
            pat1 = re.compile('<a href="(.+)" target="_blank">Ayes-(\d+)\s+Nays-(\d+)</a>')
        else:
            pat1 = re.compile('<a href="(.+)" target="_blank">Yeas-(\d+)\s+Nays-(\d+)</a>')
        sr1 = pat1.search(action)
        if not sr1:
            self.debug("515 Roll call: NO MATCH " )
            return

        the_link = sr1.group(1)
        the_ayes = sr1.group(2)
        the_nays = sr1.group(3)

        vbase = self.urls['vote-url-base']
        vurl = "%s%s" % (self.urls['vote-url-base'], the_link)
        self.debug("VOTE 512 Roll call: link [%s] AYES [%s] NAYS[%s] vurl[%s]"
                   % (the_link, the_ayes, the_nays, vurl ))

        motion = "some rollcall action"
        yes_count = int(the_ayes)
        no_count = int(the_nays)
        other_count = 0
        passed = True
        vote = Vote(chamber, vvote_date, motion, passed, yes_count, no_count,
                    other_count)
        self.extract_rollcall_from_pdf(chamber,vote, bill,vurl,bill_id)
        self.debug("2 ADD VOTE %s" % bill_id)
        bill.add_vote(vote)


    def scrape_details(self, bill_detail_url, session, chamber, bill_id):
        page = self.urlopen(bill_detail_url)

        if 'INVALID BILL NUMBER' in page:
            self.warning('INVALID BILL %s' % bill_detail_url)
            return

        doc = lxml.html.fromstring(page)
        doc.make_links_absolute(bill_detail_url)

        bill_div = doc.xpath('//div[@style="margin:0 0 40px 0;"]')[0]

        bill_type = bill_div.xpath('span/text()')[0]

        if 'General Bill' in bill_type:
            bill_type = 'bill'
        elif 'Concurrent Resolution' in bill_type:
            bill_type = 'concurrent resolution'
        elif 'Joint Resolution' in bill_type:
            bill_type = 'joint resolution'
        elif 'Resolution' in bill_type:
            bill_type = 'resolution'
        else:
            raise ValueError('unknown bill type: %s' % bill_type)

        # this is fragile, but less fragile than it was
        b = bill_div.xpath('./b[text()="Summary:"]')[0]
        bill_summary = b.getnext().tail.strip()

        bill = Bill(session, chamber, bill_id, bill_summary, type=bill_type)

        # sponsors
        for sponsor in doc.xpath('//a[contains(@href, "member.php")]/text()'):
            bill.add_sponsor('sponsor', sponsor)

        # find versions
        version_url = doc.xpath('//a[text()="View full text"]/@href')[0]
        version_html = self.urlopen(version_url)
        version_doc = lxml.html.fromstring(version_html)
        version_doc.make_links_absolute(version_url)
        for version in version_doc.xpath('//a[contains(@href, "/prever/")]'):
            bill.add_version(version.text, version.get('href'))

        # actions
        for row in bill_div.xpath('table/tr'):
            date_td, chamber_td, action_td = row.xpath('td')

            date = datetime.datetime.strptime(date_td.text, "%m/%d/%y")
            action_chamber = {'Senate':'upper',
                              'House':'lower',
                              None: 'other'}[chamber_td.text]

            action = action_td.text_content()
            action = action.split('(House Journal')[0]
            action = action.split('(Senate Journal')[0]

            atype = action_type(action)
            bill.add_action(action_chamber, action, date, atype)


        # votes
        vurl = doc.xpath('//a[text()="View Vote History"]/@href')
        if vurl:
            vurl = vurl[0]
            self.scrape_vote_history(bill, vurl)

        bill.add_source(bill_detail_url)
        self.save_bill(bill)


    def scrape(self, chamber, session):
        index_url = self.urls[chamber]['daily-bill-index']
        chamber_letter = 'S' if chamber == 'upper' else 'H'

        page = self.urlopen(index_url)
        doc = lxml.html.fromstring(page)
        doc.make_links_absolute(index_url)

        # visit each day and extract bill ids
        days = doc.xpath('//div/b/a/@href')
        for day_url in days:
            data = self.urlopen(day_url)
            doc = lxml.html.fromstring(data)
            doc.make_links_absolute(day_url)

            for bill_a in doc.xpath('//p/a[1]'):
                bill_id = bill_a.text
                if bill_id.startswith(chamber_letter):
                    self.scrape_details(bill_a.get('href'), session, chamber,
                                        bill_id)
