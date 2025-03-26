from math import floor
from urlparse import parse_qs
from urllib import urlencode
from aweber_api.response import AWeberResponse

class AWeberCollection(AWeberResponse):
    """
    Represents a collection of similar objects.  Encapsulates data that is
    found at the base URI's for a given object type, ie:
        /accounts
        /accounts/XXX/lists
    Parses the data from the response and provides basic sequence like
    operations, such as iteration and indexing to access the entries that
    are contained in this collection.
    """
    page_size = 100

    def __init__(self, url, data, adapter):
        self._entry_data = {}
        self._current = 0

        AWeberResponse.__init__(self, url, data, adapter)
        self._key_entries(self._data)

    def get_by_id(self, id):
        """
        Returns an entry from this collection, as found by its actual
        AWeber id, not its offset.  Will actually request the data from
        the API.
        """
        return self.load_from_url("{0}/{1}".format(self.url, id))

    def _key_entries(self, response):
        count = 0
        for entry in response['entries']:
            self._entry_data[count+response['start']] = entry
            count += 1

    def _load_page_for_offset(self, offset):
        page = self._get_page_params(offset)
        response = self.adapter.request('GET', self.url, page)
        self._key_entries(response)

    def _get_page_params(self, offset):
        next_link = self._data['next_collection_link']
        url, query = next_link.split('?')
        query_parts = parse_qs(query)
        self.page_size = int(query_parts['ws.size'][0])
        page_number = int(floor(offset / self.page_size))
        start = page_number * self.page_size
        return { 'ws.start' : start, 'ws.size' : self.page_size }

    def find(self, **kwargs):
        params = {'ws.op': 'find'}
        params.update(kwargs)
        query_string = urlencode(params)
        url = '{0.url}?{1}'.format(self, query_string)
        return self.adapter.request('GET', url, params)

    def _create_entry(self, offset):
        from aweber_api.entry import AWeberEntry
        data = self._entry_data[offset]

        url = "{0}/{1}".format(self.url, data['id'])
        self._entries[offset] = AWeberEntry(url, data, self.adapter)

    def __len__(self):
        return self.total_size

    def __iter__(self):
        return self

    def next(self):
        if self._current < self.total_size:
            self._current += 1
            return self[self._current-1]
        self._current = 0
        raise StopIteration

    def __getitem__(self, offset):
        if offset < 0 or offset >= self._data['total_size']:
            raise ValueError('Offset {0} does not exist'.format(offset))

        if not offset in self._entries:
            if not offset in self._entry_data:
                self._load_page_for_offset(offset)
            self._create_entry(offset)
        return self._entries[offset]

