import re
import csv
import urllib2
import datetime
from operator import itemgetter
from collections import defaultdict

from billy.scrape import NoDataForPeriod
from billy.scrape.bills import BillScraper, Bill
from billy.scrape.votes import Vote
from openstates.ct.utils import parse_directory_listing

import lxml.html


class CTBillScraper(BillScraper):
    state = 'ct'

    _committee_names = {}
    _introducers = defaultdict(set)

    def __init__(self, *args, **kwargs):
        super(CTBillScraper, self).__init__(*args, **kwargs)
        self.scrape_committee_names()
        self.scrape_introducers('upper')
        self.scrape_introducers('lower')

    def scrape(self, chamber, session):
        if session != '2011':
            raise NoDataForPeriod(session)

        self.bills = {}
        self.scrape_bill_info(chamber, session)
        self.scrape_bill_history()
        self.scrape_versions(chamber, session)

        for bill in self.bills.itervalues():
            self.save_bill(bill)

    def scrape_bill_info(self, chamber, session):
        info_url = "ftp://ftp.cga.ct.gov/pub/data/bill_info.csv"
        page = urllib2.urlopen(info_url)
        page = csv.DictReader(page)

        abbrev = {'upper': 'S', 'lower': 'H'}[chamber]

        for row in page:
            bill_id = row['bill_num']
            if not bill_id[0] == abbrev:
                continue

            bill = Bill(session, chamber, bill_id, row['bill_title'])
            bill.add_source(info_url)

            self.scrape_votes(bill)

            for introducer in self._introducers[bill_id]:
                    bill.add_sponsor('introducer', introducer)

            self.bills[bill_id] = bill

    def scrape_votes(self, bill):
        url = ("http://www.cga.ct.gov/asp/cgabillstatus/"
               "cgabillstatus.asp?selBillType=Bill"
               "&bill_num=%s&which_year=%s" % (bill['bill_id'],
                                               bill['session']))
        with self.urlopen(url) as page:
            page = lxml.html.fromstring(page)
            page.make_links_absolute(url)

            for link in page.xpath("//a[contains(@href, 'VOTE')]"):
                self.scrape_vote(bill, link.text.strip(),
                                 link.attrib['href'])

    def scrape_vote(self, bill, name, url):
        if "VOTE/H" in url:
            vote_chamber = 'lower'
            cols = (1, 5, 9, 13)
            name_offset = 3
            yes_offset = 0
            no_offset = 1
        else:
            vote_chamber = 'upper'
            cols = (1, 6)
            name_offset = 4
            yes_offset = 1
            no_offset = 2

        with self.urlopen(url) as page:
            page = lxml.html.fromstring(page)

            yes_count = page.xpath(
                "string(//span[contains(., 'Those voting Yea')])")
            yes_count = int(re.match(r'.*(\d+).*', yes_count).group(1))

            no_count = page.xpath(
                "string(//span[contains(., 'Those voting Nay')])")
            no_count = int(re.match(r'.*(\d+).*', no_count).group(1))

            other_count = page.xpath(
                "string(//span[contains(., 'Those absent')])")
            other_count = int(re.match(r'.*(\d+).*', other_count).group(1))

            need_count = page.xpath(
                "string(//span[contains(., 'Necessary for')])")
            need_count = int(re.match(r'.*(\d+).*', need_count).group(1))

            date = page.xpath("string(//span[contains(., 'Taken on')])")
            date = re.match(r'.*Taken\s+on\s+(\d+/\d+)', date).group(1)
            date = datetime.datetime.strptime(date, "%m/%d").date()

            vote = Vote(vote_chamber, date, name, yes_count > need_count,
                        yes_count, no_count, other_count)
            vote.add_source(url)

            table = page.xpath("//table")[0]
            for row in table.xpath("tr"):
                for i in cols:
                    name = row.xpath("string(td[%d])" % (
                        i + name_offset)).strip()

                    if not name:
                        continue

                    if "Y" in row.xpath("string(td[%d])" %
                                        (i + yes_offset)):
                        vote.yes(name)
                    elif "N" in row.xpath("string(td[%d])" %
                                          (i + no_offset)):
                        vote.no(name)
                    else:
                        vote.other(name)

            bill.add_vote(vote)

    def scrape_bill_history(self):
        history_url = "ftp://ftp.cga.ct.gov/pub/data/bill_history.csv"
        page = urllib2.urlopen(history_url)
        page = csv.DictReader(page)

        action_rows = defaultdict(list)

        for row in page:
            bill_id = row['bill_num']

            if bill_id in self.bills:
                action_rows[bill_id].append(row)

        for (bill_id, actions) in action_rows.iteritems():
            bill = self.bills[bill_id]

            actions.sort(key=itemgetter('act_date'))
            act_chamber = bill['chamber']

            for row in actions:
                date = row['act_date']
                date = datetime.datetime.strptime(
                    date, "%Y-%m-%d %H:%M:%S").date()

                action = row['act_desc'].strip()
                act_type = []

                if action.endswith('COMM. ON'):
                    comm_code = row['qual1']
                    comm_name = self._committee_names.get(comm_code,
                                                          comm_code)
                    action = "%s %s" % (action, comm_name)
                    act_type.append('committee:referred')
                elif row['qual1']:
                    if bill['session'] in row['qual1']:
                        action += ' (%s' % row['qual1']
                        if row['qual2']:
                            action += ' %s)' % row['qual2']
                    else:
                        action += ' %s' % row['qual1']

                if re.match(r'^ADOPTED, (HOUSE|SENATE)', action):
                    act_type.append('bill:passed')

                if not act_type:
                    act_type = ['other']

                bill.add_action(act_chamber, action, date,
                                type=act_type)

                if 'TRANS.TO HOUSE' in action:
                    act_chamber = 'lower'

                if 'TRANSMITTED TO SENATE' in action:
                    act_chamber = 'upper'

    def scrape_versions(self, chamber, session):
        chamber_letter = {'upper': 's', 'lower': 'h'}[chamber]
        versions_url = "ftp://ftp.cga.ct.gov/%s/tob/%s/" % (
            session, chamber_letter)

        with self.urlopen(versions_url) as page:
            files = parse_directory_listing(page)

            for f in files:
                match = re.match(r'^\d{4,4}([A-Z]+-\d{5,5})-(R\d\d)',
                                 f.filename)
                bill_id = match.group(1).replace('-', '')

                try:
                    bill = self.bills[bill_id]
                except KeyError:
                    continue

                url = versions_url + f.filename
                bill.add_version(match.group(2), url)

    def scrape_committee_names(self):
        comm_url = "ftp://ftp.cga.ct.gov/pub/data/committee.csv"
        page = urllib2.urlopen(comm_url)
        page = csv.DictReader(page)

        for row in page:
            comm_code = row['comm_code'].strip()
            comm_name = row['comm_name'].strip()
            comm_name = re.sub(r' Committee$', '', comm_name)
            self._committee_names[comm_code] = comm_name

    def scrape_introducers(self, chamber):
        chamber_letter = {'upper': 's', 'lower': 'h'}[chamber]
        url = "http://www.cga.ct.gov/asp/menu/%slist.asp" % chamber_letter

        with self.urlopen(url) as page:
            page = lxml.html.fromstring(page)
            page.make_links_absolute(url)

            for link in page.xpath("//a[contains(@href, 'MemberBills')]"):
                name = link.xpath("string(../../td[1])").strip()
                name = re.match("^S?\d+\s+-\s+(.*)$", name).group(1)

                self.scrape_introducer(name, link.attrib['href'])

    def scrape_introducer(self, name, url):
        with self.urlopen(url) as page:
            page = lxml.html.fromstring(page)

            for link in page.xpath("//a[contains(@href, 'billstatus')]"):
                bill_id = link.text.strip()
                self._introducers[bill_id].add(name)
