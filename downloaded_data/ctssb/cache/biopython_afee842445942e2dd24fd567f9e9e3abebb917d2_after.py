# Copyright 2012 by Wibowo Arindrarto.  All rights reserved.
# This code is part of the Biopython distribution and governed by its
# license.  Please see the LICENSE file that should have been included
# as part of this package.

"""Bio.SearchIO objects to model homology search program outputs (PRIVATE)."""


from Bio.Align import MultipleSeqAlignment
from Bio.Alphabet import single_letter_alphabet
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from Bio._py3k import OrderedDict


# attributes that should be converted from text
_INTS = (
        # qresult-specific attributes
        'param_gap_open', 'param_gap_extend', 'param_score_match',
        'param_score_mismatch', 'stat_db_num', 'stat_db_len',
        # hit-specific attributes
        'domain_obs_num',
        # hsp-specific attributes
        'init_len', 'ident_num', 'pos_num', 'mismatch_num', 'gap_num',
        'query_from', 'query_to', 'hit_from', 'hit_to', 'query_frame',
        'hit_frame', 'gapopen_num', 'env_from', 'env_to', 'domain_index',
        # attributes used in qresult, hit, and/or hsp
        'seq_len',
)
_FLOATS = (
        # qresult-specific attributes
        'param_evalue_threshold', 'stat_eff_space', 'stat_kappa',
        'stat_lambda', 'stat_entropy',
        # hit-specific attributes
        'domain_exp_num',
        # hsp attributes
        'bitscore', 'bitscore_raw', 'evalue', 'ident_pct', 'pos_pct', 'bias',
        'evalue_cond', 'acc_avg',
)


class BaseSearchObject(object):

    """Abstract class for SearchIO objects."""

    _NON_STICKY_ATTRS = ()

    def __setattr__(self, name, value):
        if isinstance(value, basestring):
            if name in _INTS:
                value = int(value)
            elif name in _FLOATS:
                value = float(value)
        object.__setattr__(self, name, value)

    def _transfer_attrs(self, obj):
        """Transfer instance attributes to the given object.

        This method is used to transfer attributes set externally (for example
        using setattr()) to a new object created from this one (for example
        from slicing).

        The reason this method is necessary is because different parsers will
        set different attributes for each QueryResult, Hit, or HSP object they use,
        depending on the attributes they found in the search output file.
        Ideally, we want these attributes to 'stick' with any new instance
        object created from the original one.

        """
        # list of attribute names we don't want to transfer
        for attr in self.__dict__.keys():
            if attr not in self._NON_STICKY_ATTRS:
                setattr(obj, attr, self.__dict__[attr])


class QueryResult(BaseSearchObject):

    # TODO: Check for self.filter()? Or implement this in SearchIO.parse?

    """Class representing search results from a single query.

    The QueryResult object is a container for storing all search hits from a single
    search query. It is the top-level object returned by SearchIO's two main
    functions, SearchIO.read:

    >>> from Bio import SearchIO
    >>> qresult = SearchIO.read('tblastx_human_wnts.xml', 'blast-xml')
    >>> qresult
    QueryResult(program='TBLASTX', target='refseq_mrna', id='gi|195230749:301-1383', 5 hits)

    and SearchIO.parse:

    >>> qresults = SearchIO.parse('tblastx_human_wnts.xml', 'blast-xml')
    >>> qresult = qresults.next()
    >>> qresult
    QueryResult(program='TBLASTX', target='refseq_mrna', id='gi|195230749:301-1383', 5 hits)

    QueryResult is basically a container of the hits (see Hit objects) from one
    query sequence. Its length is how many hits it has and iteration over a
    QueryResult object returns Hit objects.

    >>> len(qresult)
    5
    >>> for hit in qresult:
    ...     print hit.id
    ...
    gi|195230749|ref|NM_003391.2|
    gi|281183280|ref|NM_001168718.1|
    gi|281182577|ref|NM_001168597.1|
    gi|274325896|ref|NM_001168687.1|
    gi|209529663|ref|NM_001135848.1|

    QueryResult objects behaves like a hybrid of Python's built-in list and
    dictionary, enabling retrieval of search hits using its index (integer) or
    its key (string, defaults to ID).

    Indexing using integers works exactly the same as Python lists:

    >>> first_hit = qresult[0]
    >>> first_hit
    Hit(id='gi|195230749|ref|NM_003391.2|', query_id='gi|195230749:301-1383', 10 alignments)

    >>> last_hit = qresult[-1]
    >>> last_hit
    Hit(id='gi|209529663|ref|NM_001135848.1|', query_id='gi|195230749:301-1383', 10 alignments)

    Indexing using hit IDs works just like Python dictionaries. This is useful
    if you know what you are expecting from the search beforehand.

    >>> qresult['gi|195230749|ref|NM_003391.2|']
    Hit(id='gi|195230749|ref|NM_003391.2|', query_id='gi|195230749:301-1383', 10 alignments)

    To get a list of all the hits contained in a QueryResult object, you can use
    the hits attribute. To obtain all the hit keys, the hit_keys attribute
    is used.

    >>> qresult.hits
    [Hit(id='gi|195230749|ref|NM_003391.2|', query_id='gi|195230749:301-1383', 10 alignments), Hit(id='gi|281183280|ref|NM_001168718.1|', query_id='gi|195230749:301-1383', 10 alignments), Hit(id='gi|281182577|ref|NM_001168597.1|', query_id='gi|195230749:301-1383', 10 alignments), Hit(id='gi|274325896|ref|NM_001168687.1|', query_id='gi|195230749:301-1383', 10 alignments), Hit(id='gi|209529663|ref|NM_001135848.1|', query_id='gi|195230749:301-1383', 10 alignments)]

    >>> qresult.hit_keys
    [u'gi|195230749|ref|NM_003391.2|', u'gi|281183280|ref|NM_001168718.1|', u'gi|281182577|ref|NM_001168597.1|', u'gi|274325896|ref|NM_001168687.1|', u'gi|209529663|ref|NM_001135848.1|']

    Similar to Python lists, you can also slice QueryResult objects. However,
    instead of returning a list, slicing will return a new QueryResult object.
    The new QueryResult object will have its hits sliced accordingly and attributes
    present in the unsliced QueryResult object are retained.

    >>> qresult
    QueryResult(program='TBLASTX', target='refseq_mrna', id='gi|195230749:301-1383', 5 hits)
    >>> sliced_qresult = qresult[:3]
    >>> sliced_qresult
    QueryResult(program='TBLASTX', target='refseq_mrna', id='gi|195230749:301-1383', 3 hits)
    >>> len(qresult)
    5
    >>> len(sliced_qresult)
    3
    >>> qresult.program
    u'TBLASTX'
    >>> qresult.program == sliced_qresult.program
    True
    >>> qresult[0] in sliced_qresult
    True
    >>> qresult[4] in sliced_qresult
    False

    You can check whether a hit is present in a QueryResult object using its key
    (defaults to hit ID) or the Hit object itself.

    >>> hit = qresult[0]
    >>> hit in qresult
    True
    >>> hit.id in qresult
    True

    Finally, QueryResult objects has other methods normally used in Python lists:
    append(), index(), pop(), and sort(). Consult their documentation for more
    information.

    """

    # attributes we don't want to transfer when creating a new QueryResult class
    # from this one
    _NON_STICKY_ATTRS = ('_hits',)

    def __init__(self, query_id, hits=[], meta={}, program='<unknown>', \
            target='<unknown>', hit_key_function=lambda hit: hit.id):
        """Initializes a QueryResult object.

        Arguments:
        query_id -- String of query sequence ID.
        hits     -- Iterator returning Hit objects.
        meta     -- Dictionary of additional information about the search.
                    This is the information stored in the header of the
                    search output file (anything prior to the first result,
                    if it exists) and varies depending on the search program.
        program  -- String of search program name.
        target   -- String of database name to search against.
        hit_key_function -- Function to define hit keys, defaults to a function
                            that return Hit object IDs.

        """
        # meta must be a dict
        if not isinstance(meta, dict):
            raise TypeError("Meta argument must be a dictionary object.")

        self.id = query_id
        self.meta = meta
        self.program = program
        self.target = target
        self._hit_key_function = hit_key_function
        self._hits = OrderedDict()

        # validate Hit objects and fill up self._hits
        for hit in hits:
            # validation is handled by __setitem__
            self.append(hit)

    def __repr__(self):
        hit = 'hit'
        if len(self) != 1:
            hit += 's'
        return "QueryResult(program='%s', target='%s', id='%s', %i %s)" % \
                (self.program, self.target, self.id, len(self), hit)

    # handle Python 2 OrderedDict behavior
    if hasattr(OrderedDict, 'iteritems'):

        def __iter__(self):
            return iter(self.iterhits())

        def _hits_get(self):
            return self._hits.values()

        hits = property(fget=_hits_get, \
                doc="""Returns a list of Hit objects contained by this object.""")

        def _hit_keys_get(self):
            return self._hits.keys()

        hit_keys = property(fget=_hit_keys_get, \
                doc="""Returns a list of Hit IDs contained by this object.""")

        def _items_get(self):
            return self._hits.items()

        items = property(fget=_items_get, \
            doc="""Returns a list of tuples of Hit ID and Hit object contained by this object.""")

        def iterhits(self):
            """Returns an iterator over the Hit objects."""
            for hit in self._hits.itervalues():
                yield hit

        def iterhit_keys(self):
            """Returns an iterator over the ID of the Hit objects."""
            for hit_id in self._hits.iterkeys():
                yield hit_id

        def iteritems(self):
            """Returns an iterator of tuples of Hit ID and Hit objects."""
            for item in self._hits.iteritems():
                yield item

    else:

        def __iter__(self):
            return iter(self.hits)

        @property
        def hits(self):
            """Returns an iterator over the Hit objects contained by this object."""
            for hit in self._hits.values():
                yield hit

        @property
        def hit_keys(self):
            """Returns an iterator over the Hit IDs contained by this object."""
            for hit_id in  self._hits.keys():
                yield hit_id

        @property
        def items(self):
            """Returns an iterator over the Hit ID and Hit object contained by this object."""
            for item in self._hits.items():
                yield item

    def __contains__(self, hit_key):
        """Checks whether a Hit object or a Hit object with the given ID exists."""
        if isinstance(hit_key, Hit):
            return self._hit_key_function(hit_key) in self._hits
        return hit_key in self._hits

    def __len__(self):
        return len(self._hits)

    def __nonzero__(self):
        return bool(self._hits)

    def __reversed__(self):
        hits = reversed(list(self.hits))
        obj =  self.__class__(self.id, hits, self.meta, self.program, \
                self.target, self._hit_key_function)
        self._transfer_attrs(obj)
        return obj

    def __setitem__(self, hit_key, hit):
        """Custom Search object item assignment.

        Hit key must be a string and hit must be a Hit object.

        """
        # only accept string keys
        if not isinstance(hit_key, basestring):
            raise TypeError("QueryResult object keys must be a string.")
        # hit must be a Hit object
        if not isinstance(hit, Hit):
            raise TypeError("QueryResult objects can only contain Hit objects.")
        # and it must have the same query ID as this object's ID
        if hit.query_id != self.id:
            raise ValueError("Expected Hit with query ID '%s', found '%s' "
                    "instead." % (self.id, hit.query_id))

        self._hits[hit_key] = hit

    def __getitem__(self, hit_key):
        """Custom Search object item retrieval.

        Allows value retrieval by its key, location index, or a slice of
        location index. Also allows direct HSP retrieval if hit key is a tuple
        or list of hit ID and HSP index.

        """
        # allow for direct HSP retrieval if key is list / tuple
        # of two items (hit index / id, hsp rank)
        # retrieve Hit object first, then get the HSP according
        # to the given index
        if isinstance(hit_key, (tuple, list)):
            # ensure the tuple / list has at least 2 items
            try:
                hit_id = hit_key[0]
                # note that this allows the second item to be a slice as well
                hsp_rank = hit_key[1]
            except IndexError:
                raise ValueError("Expected tuple or list with 2 items, found: "
                        "%i item(s)." % len(hit_key))

            # allow for hit retrieval by string ID or integer index
            if isinstance(hit_id, basestring):
                # if key is string, we can retrieve directly from the dict
                hit = self._hits[hit_id]
            elif isinstance(hit_id, int):
                # if not, retrieve from the list
                hit = list(self.hits)[hit_id]
            else:
                raise TypeError("Hit index must be a string or an integer if "
                        "double-index slicing is performed.")

            # return a list of hsps if hsp_rank is a slice object, instead
            # of simply slicing the hit object (which would return another hit
            # object)
            return hit.hsps[hsp_rank]

        # retrieval using slice objects returns another QueryResult object
        elif isinstance(hit_key, slice):
            # should we return just a list of Hits instead of a full blown
            # QueryResult object if it's a slice?
            hits = list(self.hits)[hit_key]
            obj =  self.__class__(self.id, hits, self.meta, self.program, \
                    self.target, self._hit_key_function)
            self._transfer_attrs(obj)
            return obj

        # if key is an int, then retrieve the Hit at the int index
        elif isinstance(hit_key, int):
            return list(self.hits)[hit_key]

        # if key is a string, then do a regular dictionary retrieval
        return self._hits[hit_key]

    def __delitem__(self, hit_key):
        """Custom Search object item deletion.

        If hit_key is a string, then the method will delete the Hit object whose
        ID matches the string. If key is an integer or a slice object, then
        the Hit objects within that range will be deleted.

        The method can also delete HSP objects within a given Hit object if
        hit_key is given as a tuple or list of two items: the Hit index and
        the HSP index.

        """
        if isinstance(hit_key, (list, tuple)):
            # if hit_key is a list or tuple, deletion is done at the hsp level
            try:
                hit_id = hit_key[0]
                # note that this allows the second item to be a slice as well
                hsp_rank = hit_key[1]
            except IndexError:
                raise ValueError("Expected tuple or list with 2 items, found: "
                        "%i item(s)." % len(hit_key))

            # allow for hit retrieval by string ID or integer index
            if isinstance(hit_id, basestring):
                # if key is string, we can retrieve directly from the dict
                hit = self._hits[hit_id]
            elif isinstance(hit_id, int):
                # if not, retrieve from the list
                hit = list(self.hits)[hit_id]
            else:
                raise TypeError("Hit index must be a string or an integer if "
                        "double-index slicing is performed.")

            # delete the HSPs from the hit and assign it to replace the old hit
            # TODO: this allows cases where a Hit object can have 0 HSPs ~ is
            # it ok to allow this? should we delete the hit object instead?
            del hit[hsp_rank]
            self._hits[self._hit_key_function(hit)] = hit
            return

        else:
            # if hit_key an integer or slice, get the corresponding key first
            # and put it into a list
            if isinstance(hit_key, int):
                hit_keys = [list(self.hit_keys)[hit_key]]
            # the same, if it's a slice
            elif isinstance(hit_key, slice):
                hit_keys = list(self.hit_keys)[hit_key]
            # otherwise put it in a list
            else:
                hit_keys = [hit_key]

            for key in hit_keys:
                del self._hits[key]
            return

    def append(self, hit):
        """Adds a Hit object to the end of QueryResult.

        Argument:
        hit -- Hit object.

        The hit key used for the appended Hit object depends on the
        hit_key_function used to initialize the QueryResult object. Any Hit object
        appended must have the same query_id attribute as the QueryResult object's
        id attribute. If the hit key already exists, a ValueError will be
        raised.

        """
        # if a custom hit_key_function is supplied, use it to define th hit key
        if self._hit_key_function is not None:
            hit_key = self._hit_key_function(hit)
        else:
            hit_key = hit.id

        if hit_key not in self:
            self[hit_key] = hit
        else:
            raise ValueError("Hit '%s' already present in this QueryResult." % \
                    hit_key)

    # marker for default self.pop() return value
    # this method is adapted from Python's built in OrderedDict.pop
    # implementation
    __marker = object()

    def pop(self, hit_key=-1, default=__marker):
        """Removes the specified hit key and return the Hit object.

        Arguments:
        hit_key -- Integer index or string of hit key that points to a Hit
                   object.
        default -- Value that will be returned if the Hit object with the
                   specified index or hit key is not found.

        By default, pop will remove and return the last Hit object in the
        QueryResult object. To remove specific Hit objects, you can use its integer
        index or its hit key.

        >>> from Bio import SearchIO
        >>> qresult = SearchIO.read('tblastx_human_wnts.xml', 'blast-xml')
        >>> len(qresult)
        5
        >>> for hit in qresult:
        ...     print hit.id
        ...
        gi|195230749|ref|NM_003391.2|
        gi|281183280|ref|NM_001168718.1|
        gi|281182577|ref|NM_001168597.1|
        gi|274325896|ref|NM_001168687.1|
        gi|209529663|ref|NM_001135848.1|

        >>> qresult.pop()
        Hit(id='gi|209529663|ref|NM_001135848.1|', query_id='gi|195230749:301-1383', 10 alignments)

        >>> qresult.pop(0)
        Hit(id='gi|195230749|ref|NM_003391.2|', query_id='gi|195230749:301-1383', 10 alignments)

        >>> qresult.pop('gi|281182577|ref|NM_001168597.1|')
        Hit(id='gi|281182577|ref|NM_001168597.1|', query_id='gi|195230749:301-1383', 10 alignments)

        >>> len(qresult)
        2

        """
        # if key is an integer (index)
        # get the ID for the Hit object at that index
        if isinstance(hit_key, int):
            # raise the appropriate error if there is no hit
            if not self:
                raise IndexError("pop from empty list")
            hit_key = list(self.hit_keys)[hit_key]

        try:
            return self._hits.pop(hit_key)
        except KeyError:
            # if key doesn't exist and no default is set, raise a KeyError
            if default is self.__marker:
                raise KeyError(hit_key)
        # if key doesn't exist but a default is set, return the default value
        return default

    def index(self, hit_key):
        """Returns the index of a given hit key, zero-based.

        Argument:
        hit_key -- String of hit key or Hit object.

        >>> from Bio import SearchIO
        >>> qresult = SearchIO.read('tblastx_human_wnts.xml', 'blast-xml')
        >>> qresult.index('gi|209529663|ref|NM_001135848.1|')
        4
        >>> hit = qresult['gi|209529663|ref|NM_001135848.1|']
        >>> qresult.index(hit)
        4
        >>> qresult.index('my_key')
        -1

        This method is useful for finding out the integer index (usually
        correlated with search rank) of a given hit key.

        """
        try:
            if isinstance(hit_key, Hit):
                return list(self.hit_keys).index(hit_key.id)
            return list(self.hit_keys).index(hit_key)
        except ValueError:
            return -1

    def sort(self, key=None, reverse=False):
        # no cmp argument to make sort more Python 3-like
        """Sorts the Hit objects.

        Arguments:
        key -- Function used to sort the Hit objects.
        reverse -- Boolean, whether to reverse the sorting or not.

        >>> from Bio import SearchIO
        >>> qresult = SearchIO.read('tblastx_human_wnts.xml', 'blast-xml')
        >>> for hit in qresult:
        ...     print hit.id
        ...
        gi|195230749|ref|NM_003391.2|
        gi|281183280|ref|NM_001168718.1|
        gi|281182577|ref|NM_001168597.1|
        gi|274325896|ref|NM_001168687.1|
        gi|209529663|ref|NM_001135848.1|

        >>> qresult.sort(reverse=True)
        >>> for hit in qresult:
        ...     print hit.id
        ...
        gi|209529663|ref|NM_001135848.1|
        gi|274325896|ref|NM_001168687.1|
        gi|281182577|ref|NM_001168597.1|
        gi|281183280|ref|NM_001168718.1|
        gi|195230749|ref|NM_003391.2|

        >>> qresult.sort(key=lambda hit: hit.id)
        >>> for hit in qresult:
        ...     print hit.id
        ...
        gi|195230749|ref|NM_003391.2|
        gi|209529663|ref|NM_001135848.1|
        gi|274325896|ref|NM_001168687.1|
        gi|281182577|ref|NM_001168597.1|
        gi|281183280|ref|NM_001168718.1|

        By default, sorting is based on the expect values of the Hit objects,
        from the smallest to the largest. If the Hit objects do not have any
        expect values (e.g. BLAT Hit objects), then no sorting is performed.

        The sort creates a new Hit container object, but appears to be
        in-place since the new Hit container replaces the old one.

        """
        # if no key is specified, attempt to sort by Hit evalue
        if key is None:
            try:
                sorted_hits = sorted(self.hits, key=lambda hit: hit.evalue, \
                        reverse=reverse)
            # handle cases where the Hit objects doesn't have evalue
            except AttributeError:
                # if reverse is set to True, reverse the ordering
                # we don't use sorted() since no __eq__ etc. magic methods
                # are defined for Hit objects
                if reverse:
                    sorted_hits = self.hits[::-1]
                # otherwise the object is the same as the old one and no
                # sorting is required
                else:
                    return
        # otherwise try to sort using the given parameters
        # and let any exceptions rise to the top
        else:
            sorted_hits = sorted(self.hits, key=key, reverse=reverse)

        new_hits = OrderedDict()
        for hit in sorted_hits:
            new_hits[self._hit_key_function(hit)] = hit

        self._hits = new_hits


class Hit(BaseSearchObject):

    """Class representing a single database hit of a search result.

    Hit objects are the second-level container in the SearchIO module. They
    are the objects contained within a QueryResult object (see QueryResult). Each Hit
    object is uniquely identified by its ID and the query ID that results in
    its creation.

    >>> from Bio import SearchIO
    >>> qresult = SearchIO.read('tblastx_human_wnts.xml', 'blast-xml')
    >>> hit = qresult[0]
    >>> hit
    Hit(id='gi|195230749|ref|NM_003391.2|', query_id='gi|195230749:301-1383', 10 alignments)

    Hit objects themselves are container for the basic SearchIO unit: the
    HSP object (see HSP). Since these HSPs usually do not have any unique
    IDs, Hit objects behave very similar to a Python built-in list.

    The length of a Hit object is how many HSPs it contains and iteration
    over Hit objects return these HSPs:

    >>> len(hit)
    10
    >>> for hsp in hit:
    ...     print hsp.hit_id, hsp.evalue, len(hsp)
    gi|195230749|ref|NM_003391.2| 0.0 340
    gi|195230749|ref|NM_003391.2| 0.0 253
    gi|195230749|ref|NM_003391.2| 0.0 69
    gi|195230749|ref|NM_003391.2| 0.0 361
    gi|195230749|ref|NM_003391.2| 0.0 178
    gi|195230749|ref|NM_003391.2| 0.0 161
    gi|195230749|ref|NM_003391.2| 0.0 237
    gi|195230749|ref|NM_003391.2| 0.0 106
    gi|195230749|ref|NM_003391.2| 0.0 288
    gi|195230749|ref|NM_003391.2| 0.0 28

    Like built-in Python lists, you can index Hit objects with integers or
    slice them. Slicing a Hit object will return a new Hit object with its
    HSPs properly sliced but any other attributes retained.

    >>> hit[0]
    HSP(hit_id='gi|195230749|ref|NM_003391.2|', query_id='gi|195230749:301-1383', evalue=0.0, 340-column alignment)
    >>> hit[-1]
    HSP(hit_id='gi|195230749|ref|NM_003391.2|', query_id='gi|195230749:301-1383', evalue=0.0, 28-column alignment)

    >>> hit
    Hit(id='gi|195230749|ref|NM_003391.2|', query_id='gi|195230749:301-1383', 10 alignments)
    >>> sliced_hit = hit[:3]
    >>> sliced_hit
    Hit(id='gi|195230749|ref|NM_003391.2|', query_id='gi|195230749:301-1383', 3 alignments)
    >>> len(hit)
    10
    >>> len(sliced_hit)
    3
    >>> hit.description
    u'Homo sapiens wingless-type MMTV integration site family member 2 (WNT2), transcript variant 1, mRNA'
    >>> hit.description == sliced_hit.description
    True
    >>> hit[0] in sliced_hit
    True
    >>> hit[6] in sliced_hit
    False

    You can check whether an hsp is present in a QueryResult object using the HSP
    object itself.

    >>> hsp = hit[0]
    >>> hsp in hit
    True

    Finally, similar to Python built-in list, the Hit object also has the
    append(), pop(), reverse(), and sort() method, which behave similar to
    their list method counterparts.

    """

    # attributes we don't want to transfer when creating a new Hit class
    # from this one
    _NON_STICKY_ATTRS = ('_hsps',)

    def __init__(self, hit_id, query_id, hsps=[]):
        """Initializes a Hit object.

        Arguments:
        query_id -- String of the query name used to obtain this hit.
        hit_id   -- String of unique identifier for this hit.
        hsps     -- Iterable returning HSP objects.

        """
        self.query_id= query_id
        self.id = hit_id

        self._hsps = []
        for hsp in hsps:
            # validate each HSP
            self._validate_hsp(hsp)
            # and store it them as an instance attribute
            self._hsps.append(hsp)

    def __repr__(self):
        al = 'alignment'
        if len(self) != 1:
            al += 's'
        return "Hit(id='%s', query_id='%s', %i %s)" % (self.id, \
                self.query_id, len(self), al)

    def _hsps_get(self):
        return self._hsps

    hsps = property(fget=_hsps_get)

    def __iter__(self):
        return iter(self._hsps)

    def __len__(self):
        return len(self._hsps)

    def __nonzero__(self):
        return bool(self._hsps)

    def __reversed__(self):
        obj = self.__class__(self.id, self.query_id, reversed(self._hsps))
        self._transfer_attrs(obj)
        return obj

    def __setitem__(self, idx, hsps):
        # handle case if hsps is a list of hsp
        if isinstance(hsps, (list, tuple)):
            for hsp in hsps:
                self._validate_hsp(hsp)
        else:
            self._validate_hsp(hsps)

        self._hsps[idx] = hsps

    def __getitem__(self, idx):
        # if key is slice, return a new Hit instance
        if isinstance(idx, slice):
            obj = self.__class__(self.id, self.query_id, self._hsps[idx])
            self._transfer_attrs(obj)
            return obj
        return self._hsps[idx]

    def __delitem__(self, idx):
        del self._hsps[idx]

    def _validate_hsp(self, hsp):
        """Validates an HSP object.

        Valid HSP objects have the same hit_id as the Hit object ID and the
        same query_id as the Hit object's query_id.

        """
        if not isinstance(hsp, HSP):
            raise TypeError("Hit objects can only contain HSP objects.")
        if hsp.hit_id != self.id:
            raise ValueError("Expected HSP with hit ID '%s', found '%s' "
                    "instead." % (self.id, hsp.hit_id))
        if hsp.query_id != self.query_id:
            raise ValueError("Expected HSP with query ID '%s', found '%s' "
                    "instead." % (self.query_id, hsp.query_id))

    def append(self, hsp):
        self._validate_hsp(hsp)
        self._hsps.append(hsp)

    def pop(self, index=-1):
        return self._hsps.pop(index)

    def reverse(self):
        self._hsps.reverse()

    def sort(self, key=None, reverse=False):
        self._hsps.sort(key=key, reverse=reverse)


class HSP(BaseSearchObject):

    """Class representing high-scoring alignment regions of the query and hit.

    Although HSP objects represent a pairwise alignment of the query and hit
    sequences, in reality some file formats such as BLAST+'s standard tabular
    format do not output any alignments at all. This is why, depending on
    the search output file format, an HSP object may or may not contain a real
    sequence alignment.

    If the parsed search output file contains alignments, the HSP object will
    have an alignment attribute which is Biopython's MultipleSeqAlignment
    object. The HSP object will have a query and a hit attribute, each being
    Biopython's SeqRecord object. Without any alignments, these attributes are
    set to None.

    >>> from Bio import SearchIO
    >>> qresult = SearchIO.read('tblastx_human_wnts.xml', 'blast-xml')
    >>> hsp = qresult[0][0]
    >>> hsp
    HSP(hit_id='gi|195230749|ref|NM_003391.2|', query_id='gi|195230749:301-1383', evalue=0.0, 340-column alignment)

    >>> print hsp.alignment
    SingleLetterAlphabet() alignment with 2 rows and 340 columns
    EVNSSWWYMRATGGSSRVMCDNVPGLVSSQRQLCHRHPDVMRAI...AT* gi|195230749:301-1383
    EVNSSWWYMRATGGSSRVMCDNVPGLVSSQRQLCHRHPDVMRAI...AT* gi|195230749|ref|NM_003391.2|
    >>> print hsp.query
    ID: gi|195230749:301-1383
    Name: query
    Description: aligned query sequence
    Number of features: 0
    Seq('EVNSSWWYMRATGGSSRVMCDNVPGLVSSQRQLCHRHPDVMRAISQGVAEWTAE...AT*', SingleLetterAlphabet())
    >>> print hsp.hit
    ID: gi|195230749|ref|NM_003391.2|
    Name: hit
    Description: aligned hit sequence
    Number of features: 0
    Seq('EVNSSWWYMRATGGSSRVMCDNVPGLVSSQRQLCHRHPDVMRAISQGVAEWTAE...AT*', SingleLetterAlphabet())

    For the most part, an HSP object is read-only. It does not support item
    assignment, item deletion, or even iteration. It does, however, support item
    slicing. Slicing on an HSP object will return another HSP object with
    an alignment consisting of sliced SeqRecords.

    >>> print hsp.alignment
    SingleLetterAlphabet() alignment with 2 rows and 340 columns
    EVNSSWWYMRATGGSSRVMCDNVPGLVSSQRQLCHRHPDVMRAI...AT* gi|195230749:301-1383
    EVNSSWWYMRATGGSSRVMCDNVPGLVSSQRQLCHRHPDVMRAI...AT* gi|195230749|ref|NM_003391.2|
    >>> print hsp[10:20].alignment
    SingleLetterAlphabet() alignment with 2 rows and 10 columns
    ATGGSSRVMC gi|195230749:301-1383
    ATGGSSRVMC gi|195230749|ref|NM_003391.2|

    Finally, doing a len() on an HSP object will return the column length of
    the contained pairwise alignment. Note that this is different from a
    MultipleSeqAlignment object where doing a len() would return how many
    SeqRecords make up the MultipleSeqAlignment object.

    >>> len(hsp)
    340
    >>> len(hsp[:50])
    50

    """

    # attributes we don't want to transfer when creating a new HSP class
    # from this one
    _NON_STICKY_ATTRS = ('hit', 'query', 'alignment',)

    def __init__(self, hit_id, query_id, hit_seq='', query_seq='', \
            alphabet=single_letter_alphabet):
        """Initializes an HSP object.

        Arguments:
        hit_id    -- String, Hit ID of the HSP object.
        query_id  -- String of the search query ID.
        hit_seq   -- String or SeqRecord object of the aligned Hit sequence.
        query_seq -- String or SeqRecord object of the aligned query sequence.

        """
        self.hit_id = hit_id
        self.query_id = query_id
        self._alphabet = alphabet

        # only initialize MultipleSeqAlignment if hit_seq and query_seq is given
        if hit_seq and query_seq:
            self.add_alignment(hit_seq, query_seq, alphabet)

    def add_query(self, query_seq, alphabet):
        """Adds a query sequence to an instantiated HSP object."""
        # only accept query_seq as string or SeqRecord objects
        if not isinstance(query_seq, (SeqRecord, basestring)):
            raise TypeError("HSP sequence must be a string or a "
                    "SeqRecord object.")
        # if query_seq is a string, create a new SeqRecord object
        if isinstance(query_seq, basestring):
            query = SeqRecord(Seq(query_seq, alphabet), id=self.query_id, \
                    name='query', description='aligned query sequence')
        # otherwise query is the query_seq
        else:
            query = query_seq

        self.query = query

    def add_hit(self, hit_seq, alphabet):
        """Adds a hit sequence to an instantiated HSP object."""
        # only accept hit_seq as string or SeqRecord objects
        if not isinstance(hit_seq, (SeqRecord, basestring)):
            raise TypeError("HSP sequence must be a string or a "
                    "SeqRecord object.")
        # if hit_seq is a string, create a new SeqRecord object
        if isinstance(hit_seq, basestring):
            hit = SeqRecord(Seq(hit_seq, alphabet), id=self.hit_id, \
                    name='hit', description='aligned hit sequence')
        # otherwise hit is the hit_seq
        else:
            hit = hit_seq

        self.hit = hit

    def add_alignment(self, hit_seq, query_seq, alphabet=single_letter_alphabet):
        """Adds a hit and query sequence to an instantiated HSP object."""
        self.add_query(query_seq, alphabet)
        self.add_hit(hit_seq, alphabet)
        self.alignment = MultipleSeqAlignment([self.query, self.hit], alphabet)

    def __repr__(self):
        info = "hit_id='%s', query_id='%s'" % (self.hit_id, self.query_id)

        try:
            info += ", evalue=%s" % str(self.evalue)
        except AttributeError:
            pass

        try:
            info += ", %i-column alignment" % len(self)
        except TypeError:
            pass

        return "HSP(%s)" % (info)

    def __len__(self):
        # len should return alignment length if alignment is not None
        try:
            assert len(self.query) == len(self.hit)
            return len(self.query)
        except AttributeError:
            raise TypeError("HSP objects without alignment does not have any length.")

    def __getitem__(self, idx):
        if hasattr(self, 'alignment'):
            obj = self.__class__(self.hit_id, self.query_id, self.hit[idx], \
                    self.query[idx], self._alphabet)
            self._transfer_attrs(obj)
            return obj
        else:
            raise TypeError("Slicing for HSP objects without alignment is not supported.")

    def __delitem__(self, idx):
        raise TypeError("HSP objects are read-only.")

    def __setitem__(self, idx, value):
        raise TypeError("HSP objects are read-only.")

    def __iter__(self):
        raise TypeError("HSP objects do not support iteration.")

    def _query_strand_get(self):
        if not hasattr(self, '_query_strand'):
            # attempt to get strand from frame
            try:
                self._query_strand = self.query_frame / \
                        abs(self.query_frame)
            # handle if query frame is 0
            except ZeroDivisionError:
                self._query_strand = 0
            # handle if query frame is None
            except TypeError:
                self._query_strand = None
            # and handle cases if query_frame is not set
            except AttributeError:
                raise AttributeError("Not enough is known to compute query_strand")
        return self._query_strand

    def _query_strand_set(self, value):
        # follow SeqFeature's convention
        if not value in [-1, 0, 1, None]:
            raise ValueError("Strand should be -1, 0, 1, or None; not %r" % \
                    value)
        self._query_strand = value

    query_strand = property(fget=_query_strand_get, fset=_query_strand_set)

    def _query_from_get(self):
        # from is always less than to, regardless of strand
        return min(self._query_from, self._query_to)

    def _query_from_set(self, value):
        self._query_from = value

    query_from = property(fget=_query_from_get, fset=_query_from_set)

    def _query_to_get(self):
        # to is always greater than from, regardless of strand
        return max(self._query_from, self._query_to)

    def _query_to_set(self, value):
        self._query_to = value

    query_to = property(fget=_query_to_get, fset=_query_to_set)

    def _hit_strand_get(self):
        if not hasattr(self, '_hit_strand'):
            # attempt to get strand from frame
            try:
                self._hit_strand = self.hit_frame / \
                        abs(self.hit_frame)
            # handle if hit frame is 0
            except ZeroDivisionError:
                self._hit_strand = 0
            # handle if hit frame is None
            except TypeError:
                self._hit_strand = None
            # and handle if hit_frame doesn't exist
            except AttributeError:
                raise AttributeError("Not enought is known to compute strand")
        return self._hit_strand

    def _hit_strand_set(self, value):
        # follow SeqFeature's convention
        if not value in [-1, 0, 1, None]:
            raise ValueError("Strand should be -1, 0, 1, or None; not %r" % \
                    value)
        self._hit_strand = value

    hit_strand = property(fget=_hit_strand_get, fset=_hit_strand_set)

    def _hit_from_get(self):
        # from is always less than to, regardless of strand
        return min(self._hit_from, self._hit_to)

    def _hit_from_set(self, value):
        self._hit_from = value

    hit_from = property(fget=_hit_from_get, fset=_hit_from_set)

    def _hit_to_get(self):
        # to is always greater than from, regardless of strand
        return max(self._hit_from, self._hit_to)

    def _hit_to_set(self, value):
        self._hit_to = value

    hit_to = property(fget=_hit_to_get, fset=_hit_to_set)

    # The properties init_len, gap_num, mismatch_num, and ident_num are all
    # interconnected ~ we can infer the value of one if the others are all
    # known. So the idea here is to enable the HSP object to compute these
    # values if enough is known.
    # However, the golden rule here is that *parsed values takes precedent
    # over computed values*. So if the parsed information is available,
    # computation is never done as the parsed values are used instead.

    def _init_len_get(self):
        if not hasattr(self, '_init_len'):
            try:
                self._init_len = self._ident_num + self._mismatch_num + \
                        self._gap_num
            except AttributeError:
                raise ValueError("Not enough is known to compute this property.")
        return self._init_len

    def _init_len_set(self, value):
        self._init_len = value

    init_len = property(fget=_init_len_get, fset=_init_len_set)

    def _ident_num_get(self):
        if not hasattr(self, '_ident_num'):
            try:
                self._ident_num = self._init_len - self._mismatch_num - \
                        self._gap_num
            except AttributeError:
                raise ValueError("Not enough is known to compute this property.")
        return self._ident_num

    def _ident_num_set(self, value):
        self._ident_num = value

    ident_num = property(fget=_ident_num_get, fset=_ident_num_set)

    def _mismatch_num_get(self):
        if not hasattr(self, '_mismatch_num'):
            try:
                self._mismatch_num = self._init_len - self._ident_num - \
                        self._gap_num
            except AttributeError:
                raise ValueError("Not enough is known to compute this property.")
        return self._mismatch_num

    def _mismatch_num_set(self, value):
        self._mismatch_num = value

    mismatch_num = property(fget=_mismatch_num_get, fset=_mismatch_num_set)

    def _gap_num_get(self):
        if not hasattr(self, '_gap_num'):
            try:
                self._gap_num = self._init_len - self._ident_num - \
                        self._mismatch_num
            except AttributeError:
                raise ValueError("Not enough is known to compute this property.")
        return self._gap_num

    def _gap_num_set(self, value):
        self._gap_num = value

    gap_num = property(fget=_gap_num_get, fset=_gap_num_set)

    # for percent values (ident_pct, pos_pct, and gap_pct), the same golden
    # rule follows: parsed values takes precedent over computed values

    def _ident_pct_get(self):
        if not hasattr(self, '_ident_pct'):
            try:
                self._ident_pct = self.ident_num / float(self.init_len) * 100
            except AttributeError:
                raise ValueError("Not enough is known to compute this property.")
        return self._ident_pct

    def _ident_pct_set(self, value):
        self._ident_pct = value

    ident_pct = property(fget=_ident_pct_get, fset=_ident_pct_set)

    def _pos_pct_get(self):
        if not hasattr(self, '_pos_pct'):
            try:
                self._pos_pct = self.pos_num / float(self.init_len) * 100
            except AttributeError:
                raise ValueError("Not enough is known to compute this property.")
        return self._pos_pct

    def _pos_pct_set(self, value):
        self._pos_pct = value

    pos_pct = property(fget=_pos_pct_get, fset=_pos_pct_set)

    def _gap_pct_get(self):
        if not hasattr(self, '_gap_pct'):
            try:
                self._gap_pct = self.gap_num / float(self.init_len) * 100
            except AttributeError:
                raise ValueError("Not enough is known to compute this property.")
        return self._gap_pct

    def _gap_pct_set(self, value):
        self._gap_pct = value

    gap_pct = property(fget=_gap_pct_get, fset=_gap_pct_set)


class SearchIndexer(object):

    """Iterator that returns file positions of results in a Search output file.

    """



def _test():
    """Run the Bio.SearchIO module's doctests.

    This will try and locate the unit tests directory, and run the doctests
    from there in order that the relative paths used in the examples work.
    """
    import doctest
    import os

    test_dir = os.path.join('Tests', 'Blast')

    if os.path.isdir(os.path.join('..', '..', test_dir)):
        print "Runing doctests..."
        cur_dir = os.path.abspath(os.curdir)
        os.chdir(os.path.join('..', '..', test_dir))
        doctest.testmod()
        os.chdir(cur_dir)
        print "Done"


# if not used as a module, run the doctest
if __name__ == "__main__":
    _test()
