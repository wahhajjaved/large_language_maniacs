"""a module for compositional bias calculation.

The module contains site wrappers, function for site digitizing, and
dumper-loader functions for wrapped site collections. Each wrapper class
implements a method of compositional bias calculation.
"""

import cPickle
from decimal import Decimal

__all__ = [
    "hash_struct", "digitize",
    "Site", "MarkovSite", "PevznerSite", "KarlinSite",
    "dump_site_list", "load_site_list",
    "get_wrapper_by_abbr", "get_structs"
]

NUCLS = {"A": 0, "C": 1, "G": 2, "T": 3}

DNUCLS = {
    "N": [0, 1, 2, 3],
    "A": [0], "B": [1, 2, 3],
    "C": [1], "D": [0, 2, 3],
    "G": [2], "H": [0, 1, 3],
    "T": [3], "V": [0, 1, 2],
    "M": [0, 1], "K": [2, 3],
    "R": [0, 2], "Y": [1, 3],
    "W": [0, 3], "S": [1, 2],
}

MAX_LENGTH = 14
MAX_GAP_LENGTH = 14

def hash_struct(site_length, gap_position=0, gap_length=0):
    """Calculate hash for the given structure of a site.

    Arguments:
        `site_length` -- length of a site
        `gap_position` -- gap location inside the biparted site (length of
                          the left part); 0 (default) means continuous site
        `gap_length` -- gap length of the biparted site; 0 (default) means
                        continuous site

    Returns:
        int -- the returned number is unique for every valid site structure
    """
    if site_length <= 0:
        return 0
    struct_hash = site_length
    if 0 < gap_position < site_length and gap_length > 0:
        struct_hash += MAX_LENGTH + 1 # + site_length == 0
        struct_hash += (gap_position - 1) * MAX_LENGTH
        struct_hash += (gap_length - 1) * (MAX_LENGTH - 1) * MAX_LENGTH
    return struct_hash

def digitize(site, gap_position=0, gap_length=0):
    """Return integer representation of the site.

    Arguments:
        `site` -- site as string (or other iterable); if the site is
                  biparted it should be in gap-trimmed form
        `gap_position` -- gap location inside the biparted site; set to 0
                          if the site is continuous (default)
        `gap_length` -- length of the biparted site gap; set to 0 if the
                        site is continuous (default)

    Returns:
        list -- list of integers - degenerate variants of the site
        int -- site structure hash, obtained with `hash_struct` function
    """
    sites = [0]
    begin = 0
    while begin < len(site) and site[begin] == "N":
        begin += 1
    end = len(site)
    while end > 0 and site[end - 1] == "N":
        end -= 1
    for nucl in site[begin:end]:
        if nucl in NUCLS:
            digit = NUCLS[nucl]
            sites = [digit + (dsite << 2) for dsite in sites]
        else:
            sites = [digit + (dsite << 2) for dsite in sites
                     for digit in DNUCLS[nucl]]
    length = end - begin
    gap_position -= begin
    struct_hash = hash_struct(length, gap_position, gap_length)
    return sites, struct_hash

class Site(object):

    """A parent site wrapper class.

    Implements Bernoulli model-based method of the expected number
    calculation.

    Class methods:
        `get_structs` -- get all structs (as tuples) required for counts
                         calculation

    Class variables:
        `abbr` -- name abbreviation for the wrapper class

    Instance methods:
        `get_length` -- get length of the site
        `calc_observed` -- calculate the observed number of site occurences
        `calc_expected` -- calculate the expected number of site occurences
        `calc_contrast` -- calculate the compositional bias for the site

    Instance variables:
        `str_init` -- string representation of the site
        `str_site` -- string representation of the site with gap trimmed
                      in case of bipartite site
        `length` -- length of `str_site`
        `eff_length` -- effective length of the site (without N positions)
        `gap_position` -- gap location in case of bipartite site, else 0
        `gap_length` -- gap length in case of bipartite site, else 0
        `dsite` -- a list of integers - degenerate varians of the site
        `struct_hash` -- site structure hash
    """

    abbr = "M0"

    @staticmethod
    def get_structs(site):
        """Get all site structures required for calculation of counts.

        Arguments:
            `site` -- `Site` (or subclass) instance

        Returns:
            list -- site structures as tuples
        """
        return [(site.length, site.gap_position, site.gap_length)]

    def __init__(self, site, maxlen=MAX_LENGTH, maxgap=MAX_GAP_LENGTH):
        """Constructor.

        Arguments:
            `site` -- string, could contain ATGCBDHVSWMKRYN symbols
            `maxlen` -- site length cutoff
            `maxgap` -- gap length cutoff

        Raises:
            `ValueError` -- if site length is greater than `maxlen`, if
                            gap length is greater than `maxgap`, or if
                            the site is empty
        """
        self.str_init = site.upper().strip("N")
        if len(self.str_init) > 8 and "NNN" in self.str_init:
            uhalf = self.str_init[:6].strip("N")
            dhalf = self.str_init[6:].strip("N")
            self.str_site = uhalf + dhalf
            self.gap_position = len(uhalf)
        else:
            self.str_site = self.str_init
            self.gap_position = 0
        self.length = len(self.str_site)
        if self.length > maxlen:
            raise ValueError("site is too long: %d", self.length)
        if self.length == 0:
            raise ValueError("empty site")
        self.gap_length = len(self.str_init) - self.length
        if self.gap_length > maxgap:
            raise ValueError("gap is too long: %d", self.gap_length)
        self.eff_length = self.length - self.str_site.count("N")
        self.dsite, self.struct_hash = digitize(
            self.str_site, self.gap_position, self.gap_length
        )

    def get_length(self, effective=True):
        """Get length of the site.

        Arguments:
            `effective` -- True (default) is for the effective length,
                           which is the number of meaning (not N)
                           positions; False is for full length, i.e. the
                           number of all postitions except for the gap

        Returns:
            int -- length of the site
        """
        return self.eff_length if effective else self.length

    def calc_observed(self, counts):
        """Calculate observed number of occurences of the site by counts.

        Arguments:
            `counts` -- `Counts` object from `cbclib.counts` module

        Returns:
            long -- observed number of site occurences
        """
        return counts.get_count(self.dsite, self.struct_hash)

    def calc_expected(self, counts):
        """Estimate expected number of occurences of the site.

        Implements Bernoulli model-based method, i.e. assumes that all
        all site positions are independent.

        Arguments:
            `counts` -- `Counts` object from `cbclib.counts` module

        Returns:
            float -- expected number of site occurences
        """
        expected = counts.get_total(self.struct_hash)
        for nucl in self.str_site:
            expected *= counts.get_freq(DNUCLS[nucl])
        return expected

    def calc_contrast(self, counts):
        """Calculate compositional bias value.

        Calculates compositional bias as the ratio of the observed to the
        expected number of occurences of the site.

        Arguments:
            `counts` -- `Counts` object from `cbclib.counts` module

        Returns:
            float -- compositional bias value
        """
        expected = self.calc_expected(counts) or float("NaN")
        return self.calc_observed(counts) / expected

    def __len__(self):
        return len(self.str_init)

    def __str__(self):
        return self.str_init

    def __repr__(self):
        return "<%s '%s' of %d-%d-%d structure>" % (
            self.__class__.__name__, self.str_init,
            self.length, self.gap_position, self.gap_length
        )

class MarkovSite(Site):

    """Site wrapper implementing Mmax-based expected number calculation.

    Note: the complete list of methods and attibutes is available in
    `Site` class dicstring.
    """

    abbr = "MM"

    @staticmethod
    def get_structs(site):
        """See `Site.get_structs` docstring for details."""
        slen = site.length
        pos = site.gap_position
        glen = site.gap_length
        structs = [(slen, pos, glen)]
        if pos > 1:
            structs.append([slen-1, pos-1, glen])
        else:
            structs.append([slen-1, 0, 0])
        return structs

    def __init__(self, site, maxlen=MAX_LENGTH, maxgap=MAX_GAP_LENGTH):
        """See `Site.__init__` docstring for details."""
        super(MarkovSite, self).__init__(site, maxlen, maxgap)
        site_arr = list(self.str_site)
        site_arr[0] = "N"
        self.rpart = digitize(site_arr, self.gap_position, self.gap_length)
        site_arr[-1] = "N"
        self.cpart = digitize(site_arr, self.gap_position, self.gap_length)
        site_arr[0] = self.str_site[0]
        self.lpart = digitize(site_arr, self.gap_position, self.gap_length)

    def calc_expected(self, counts):
        """Estimate expected number of occurences of the site.

        Implements the method based on the Markov chain model of the
        maximum applicable order (Mmax), which assumes that only the edge
        positions of the site are independent (Schbath et al., 1995;
        Gelfand et al., 1997).

        Arguments:
            `counts` -- `Counts` object from `cbclib.counts` module

        Returns:
            float -- expected number of site occurences
        """
        if self.eff_length == 1:
            return counts.get_total() * len(self.dsite) / 4.0
        div = counts.get_count(*self.cpart)
        if div == 0:
            return float("NaN")
        num = counts.get_count(*self.lpart) * counts.get_count(*self.rpart)
        return float(num) / div

class PevznerSite(Site):

    """Site wrapper implementing the method of Pevzner et al.

    Note: the complete list of methods and attibutes is available in
    `Site` class dicstring.
    """

    abbr = "PBM"

    @staticmethod
    def get_structs(site):
        """See `Site.get_structs` docstring for details."""
        slen = site.length
        pos = site.gap_position
        glen = site.gap_length
        structs = [(slen, pos, glen)]
        if pos > 2:
            structs.append((slen-2, pos-2, glen))
            structs.append((slen-1, pos-1, glen))
        elif pos > 1:
            structs.append((slen-1, pos-1, glen))
            structs.append((slen-2, 0, 0))
        else:
            structs.append([slen-1, 0, 0])
        return structs

    def __init__(self, site, maxlen=MAX_LENGTH, maxgap=MAX_GAP_LENGTH):
        """See `Site.__init__` docstring for details."""
        super(PevznerSite, self).__init__(site, maxlen, maxgap)
        arr_site = list(self.str_site)
        single_n = []
        double_n = []
        for i in range(self.length):
            if arr_site[i] == "N":
                continue
            arr_site[i] = "N"
            single_n.append(
                digitize(arr_site, self.gap_position, self.gap_length)
            )
            for j in range(i + 1, self.length):
                if arr_site[j] == "N":
                    continue
                arr_site[j] = "N"
                double_n.append(
                    digitize(arr_site, self.gap_position, self.gap_length)
                )
                arr_site[j] = self.str_site[j]
            arr_site[i] = self.str_site[i]
        self.single_n = single_n
        self.double_n = double_n

    def calc_expected(self, counts):
        """Estimate expected number of occurences of the site.

        Implements the method suggested by Pevzner et al., which is the
        geometric mean of Mmax-like estimations over all pairs of site
        positions assumed to be independent.

        Arguments:
            `counts` -- `Counts` object from `cbclib.counts` module

        Returns:
            float -- expected number of site occurences
        """
        eff_len = self.eff_length
        if eff_len == 1:
            return counts.get_total() * len(self.dsite) / 4.0
        divisor = 1.0
        for _site in self.double_n:
            divisor *= counts.get_count(*_site)
        if divisor == 0.0:
            return float("NaN")
        divisor = pow(divisor, 2.0 / (eff_len**2 - eff_len))
        numerator = 1.0
        for _site in self.single_n:
            numerator *= counts.get_count(*_site)
        return pow(numerator, 2.0/self.eff_length) / divisor

def _degenerate(start, arr_site, eff_length,
                curr_list, next_list, gap_position, gap_length):
    """Recursively degenerate the given site."""
    if eff_length == 1:
        return
    for index in range(start, len(arr_site)):
        if arr_site[index] == "N":
            continue
        removed = arr_site[index]
        arr_site[index] = "N"
        curr_list.append(digitize(arr_site, gap_position, gap_length))
        _degenerate(index+1, arr_site, eff_length-1,
                    next_list, curr_list, gap_position, gap_length)
        arr_site[index] = removed

class KarlinSite(Site):

    """Site wrapper implementing the method of Karlin et al.

    Note: the complete list of methods and attibutes is available in
    `Site` class dicstring.
    """

    abbr = "BCK"

    @staticmethod
    def get_structs(site):
        """See `Site.get_structs` docstring for details."""
        slen = site.length
        pos = site.gap_position
        glen = site.gap_length
        structs = [(max(pos, slen-pos), 0, 0)]
        for i in range(pos):
            structs.append((slen-i, pos-i, glen))
        return structs

    def __init__(self, site, maxlen=MAX_LENGTH, maxgap=MAX_GAP_LENGTH):
        """See `Site.__init__` docstring for details."""
        super(KarlinSite, self).__init__(site, maxlen, maxgap)
        arr_site = list(self.str_site)
        self.odd_ns = []
        self.even_ns = []
        _degenerate(
            0, arr_site, self.eff_length,
            self.odd_ns, self.even_ns, self.gap_position, self.gap_length
        )

    def calc_expected(self, counts):
        """Estimate expected number of occurences of the site.

        Implements the method described by Karlin and Cardon in 1994.

        Arguments:
            `counts` -- `Counts` object from `cbclib.counts` module

        Returns:
            float -- expected number of site occurences
        """
        if self.eff_length == 1:
            return counts.get_total() * len(self.dsite) / 4.0
        divisor = Decimal(1)
        for _site in self.even_ns:
            divisor *= Decimal(counts.get_freq(*_site))
        if divisor.is_zero():
            return float("NaN")
        numerator = Decimal(counts.get_total(self.struct_hash))
        for _site in self.odd_ns:
            numerator *= Decimal(counts.get_freq(*_site))
        return float(numerator / divisor)

def get_wrapper_by_abbr(abbr):
    """Get site wrapper class by abbreviation."""
    for cls in [Site, MarkovSite, PevznerSite, KarlinSite]:
        if cls.abbr == abbr:
            return cls
    return None

def dump_site_list(site_list, ounsl):
    """Dump collection of wrapped sites into file."""
    with ounsl:
        cPickle.dump(site_list, ounsl, -1)

def load_site_list(innsl):
    """Load collection of wrapped sites from the dump file."""
    with innsl:
        return cPickle.load(innsl)

def get_structs(site_list, method_abbrs):
    """Return a tuple of site structures required to handle the sites.

    Use this function to get the structs for counts calculation.
    """
    struct_dict = {(0, 0): 1}
    _get_structs = Site.get_structs
    for cls in [KarlinSite, PevznerSite, MarkovSite]:
        if cls.abbr in method_abbrs:
            _get_structs = cls.get_structs
            break
    for site in site_list:
        for slen, pos, glen in _get_structs(site):
            if struct_dict.get((pos, glen), 0) < slen:
                struct_dict[(pos, glen)] = slen
    structs = []
    for (pos, glen), slen in struct_dict.items():
        structs.append((slen, pos, glen))
    return structs

