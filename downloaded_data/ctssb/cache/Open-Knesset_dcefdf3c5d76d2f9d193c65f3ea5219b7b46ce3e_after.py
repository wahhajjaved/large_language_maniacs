from committees.models import Committee, CommitteeMeeting
from django.utils.timezone import now, timedelta
from django.db.models import Q
from simple import scrapers


def handle_committee_entry(logger, entry):
    data = entry['data']
    qs = Committee.objects.filter(knesset_id=data['committee_id'])
    if qs.exists():
        committee = qs.first()
    else:
        qs = Committee.objects.filter(name=data['committee_name'])
        if qs.count() == 0:
            logger.info(u'could not find committee by knesset id or name - will create a new committee')
            # we create new committees as hidden by default, letting other scrapers un-hide if needed
            committee = Committee.objects.create(name=data['committee_name'], knesset_id=data['committee_id'], hide=True)
        else:
            if qs.count() > 1:
                logger.error(u'found more then 1 committee with same name %s'%data['committee_name'])
            committee = qs.first()
    committee.knesset_id = data['committee_id']
    committee.knesset_type_id = data['committee_type_id']
    committee.knesset_parent_id = data['committee_parent_id']
    committee.name = data['committee_name']
    committee.name_eng = data['committee_name_eng']
    committee.name_arb = data['committee_name_arb']
    committee.start_date = data['committee_begin_date']
    committee.end_date = data['committee_end_date']
    committee.knesset_description = data['committee_desc']
    committee.knesset_description_eng = data['committee_desc_eng']
    committee.knesset_description_arb = data['committee_desc_arb']
    committee.knesset_note = data['committee_note']
    committee.knesset_note_eng = data['committee_note_eng']
    committee.knesset_portal_link = data['committee_portal_link']
    committee.last_scrape_time = now()
    committee.save()
    return committee


def handle_committeemeeting_entry(logger, entry):
    data = entry['data']
    protocol_id = data['protocol_id']
    committee_id = data['committee_id']
    protocol_date = data['protocol_date']
    protocol_datetime = scrapers.parse_combined_datetime(data['protocol_date'], data['protocol_time'])
    title = data['agendum1']
    link = data['protocol_link']
    committee = CommitteeScraper().scrape(committee_id)['entry']
    if CommitteeMeeting.objects.filter(Q(knesset_id=protocol_id) | Q(date=protocol_date), committee=committee).exists():
        print protocol_date
        logger.debug('existing committee meeting most likely already exists in DB, will not create a new one')
        return data
    else:
        logger.info('creating new committee meeting object')
        # the id doesn't exist or there is not protocol for the given committee on that date
        # this condition should prevent duplicated meeting
        committee_meeting = CommitteeMeeting.objects.create(
            committee=committee,
            date_string=scrapers.hebrew_strftime(protocol_datetime, u'%d/%m/%Y'),
            date=protocol_date,
            topics=title,
            datetime=protocol_datetime,
            knesset_id=protocol_id,
            src_url=link,
        )
        committee_meeting.reparse_protocol()
        return committee_meeting


class CommitteeScraper(scrapers.KnessetDataServiceSingleEntryScraper):
    """
    fetch data about a committee from knesset api

    #  $ ./manage.py okscrape --scraper-args=2 committees CommitteeScraper

   the argument is the knesset committee id
    """

    SERVICE_NAME = "CommitteeScheduleData"
    METHOD_NAME = "View_committee"

    def _handle_entry(self, entry):
        return handle_committee_entry(self._getLogger(), entry)

    def _scrape_from_api(self, id):
        self._getLogger().info('failed to get an up-to-date committee, will try to access knesset api')
        self.storage.storeDict({'entry': self._handle_entry(self.source.fetch(id=id))})

    def _scrape(self, id):
        qs = Committee.objects.filter(knesset_id=id)
        if qs.count() == 0:
            self._getLogger().warning(u'failed to find committee by id (%s), will fetch from api and try by name'%id)
            self._scrape_from_api(id)
        else:
            if qs.count() > 1:
                raise Exception(u'found more then 1 committee with knesset id = %s'%id)
            committee = qs.first()
            if committee.last_scrape_time is None or committee.last_scrape_time < now()-timedelta(days=3):
                self._getLogger().info(u'committee (knesset_id=%s) is not up-to-date, will fetch fresh data from knesset api'%id)
                self._scrape_from_api(id)
            else:
                self.storage.storeDict({'entry': committee})


class CommitteeMeetingsScraper(scrapers.KnessetDataServiceListScraper):
    """
    fetch a list of committee meetings from knesset api

    #  $ ./manage.py okscrape --scraper-args=1 committees CommitteeMeetingsScraper

   the argument is the page number, returning 50 results per page, starting from the latest meetings

    this scraper also calls the CommitteeScraper for committees it encounters
    """

    SERVICE_NAME = "CommitteeScheduleData"
    METHOD_NAME = "View_protocols"
    ORDERBY_FIELD = "Protocol_date"

    def _handle_entry(self, entry):
        return handle_committeemeeting_entry(self._getLogger(), entry)


class CommitteeMeetingsMultiPageScraper(scrapers.KnessetDataServiceMultiPageScraper):

    LIST_SCRAPER_CLASS = CommitteeMeetingsScraper

    def _isEmpty(self, val):
        return isinstance(val, dict)
