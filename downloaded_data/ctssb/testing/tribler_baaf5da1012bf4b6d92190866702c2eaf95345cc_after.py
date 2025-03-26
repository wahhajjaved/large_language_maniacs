from hashlib import sha1

from dispersydatabase import DispersyDatabase
from crypto import ec_from_private_bin, ec_from_public_bin, ec_signature_length, ec_verify, ec_sign

if __debug__:
    from dprint import dprint
    from crypto import ec_check_public_bin, ec_check_private_bin

class DummyMember(object):
    def __init__(self, mid):
        assert isinstance(mid, str)
        assert len(mid) == 20
        self._mid = mid

        assert DispersyDatabase.has_instance(), "DispersyDatabase has not yet been created"
        database = DispersyDatabase.get_instance()

        if __debug__:
            # may only create a DummyMember when the public key is not available
            try:
                public_key, = database.execute(u"SELECT public_key FROM member WHERE mid = ? LIMIT 1", (buffer(mid),)).next()
                assert public_key is None
            except StopIteration:
                pass

        try:
            database_id, tags = database.execute(u"SELECT id, tags FROM member WHERE mid = ? LIMIT 1", (buffer(mid),)).next()
        except StopIteration:
            database.execute(u"INSERT INTO member (mid) VALUES (?)", (buffer(mid),))
            database_id = database.last_insert_rowid
            tags = u""

        self._database_id = database_id
        self._mid = mid

    @property
    def mid(self):
        """
        The member id.  This is the 20 byte sha1 hash over the public key.
        """
        return self._mid

    @property
    def database_id(self):
        """
        The database id.  This is the unsigned integer used to store
        this member in the Dispersy database.
        """
        return self._database_id

    @property
    def public_key(self):
        return ""

    @property
    def private_key(self):
        return ""

    @property
    def signature_length(self):
        return 0

    def has_identity(self, community):
        return False

    # @property
    def __get_must_store(self):
        return False
    # @must_store.setter
    def __set_must_store(self, value):
        pass
    # .setter was introduced in Python 2.6
    must_store = property(__get_must_store, __set_must_store)

    # @property
    def __get_must_ignore(self):
        return False
    # @must_ignore.setter
    def __set_must_ignore(self, value):
        pass
    # .setter was introduced in Python 2.6
    must_ignore = property(__get_must_ignore, __set_must_ignore)

    # @property
    def __get_must_blacklist(self):
        return False
    # @must_blacklist.setter
    def __set_must_blacklist(self, value):
        pass
    # .setter was introduced in Python 2.6
    must_blacklist = property(__get_must_blacklist, __set_must_blacklist)

    def verify(self, data, signature, offset=0, length=0):
        return False

    def sign(self, data, offset=0, length=0):
        return ""

    def __eq__(self, member):
        return False

    def __ne__(self, member):
        return True

    def __cmp__(self, member):
        return -1

    def __hash__(self):
        return self._mid.__hash__()

    def __str__(self):
        return "<%s 0 %s>" % (self.__class__.__name__, self._mid.encode("HEX"))

class Member(DummyMember):
    __cache_length = 512
    __cache = []

    if __debug__:
        __stats_hit = 0
        __stats_prio_hit = 0
        __stats_miss = 0
        __stats_move = 0
        __stats_del = 0

    def __new__(cls, public_key, private_key=""):
        assert isinstance(public_key, str)
        assert isinstance(private_key, str)
        assert ec_check_public_bin(public_key), [len(public_key), public_key.encode("HEX")]
        assert private_key == "" or ec_check_private_bin(private_key), [len(private_key), private_key.encode("HEX")]

        # retrieve Member from cache
        for index, member in enumerate(cls.__cache):
            if member._public_key == public_key:
                if cls.__cache_length / 2 < index:
                    del cls.__cache[index]
                    cls.__cache.insert(0, member)

                if __debug__:
                    cls.__stats_hit += 1
                    if cls.__cache_length / 2 < index:
                        cls.__stats_move += 1
                    else:
                        cls.__stats_prio_hit += 1

                return member

        # create new Member and store in cache
        member = object.__new__(cls)
        if len(cls.__cache) >= cls.__cache_length:
            del cls.__cache[-1]
        cls.__cache.insert(cls.__cache_length / 3, member)

        if __debug__:
            # stats prio hit: 3689 hit: 4715 miss: 1325 move: 1026 del: 1069                [insert at length/2]
            # stats prio hit: 4332 hit: 4529 miss: 1325 move:  197 del: 1069 cache: 256     [insert at length/3]
            # stats prio hit:119684 hit:125291 miss:33901 move:5607 del:33646 cache:256     [long run]
            # stats prio hit:142272 hit:147010 miss:40155 move:4738 del:39644 cache:512
            cls.__stats_miss += 1
            if len(cls.__cache) == cls.__cache_length:
                cls.__stats_del += 1
            dprint("stats prio hit:", cls.__stats_prio_hit, " hit:", cls.__stats_hit, " miss:", cls.__stats_miss, " move:", cls.__stats_move, " del:", cls.__stats_del, " cache:", len(cls.__cache))

        return member

    def __init__(self, public_key, private_key=""):
        """
        Create a new Member instance.
        """
        assert isinstance(public_key, str)
        assert isinstance(private_key, str)
        assert ec_check_public_bin(public_key), public_key.encode("HEX")
        assert private_key == "" or ec_check_private_bin(private_key), private_key.encode("HEX")

        if not hasattr(self, "_public_key"):
            assert DispersyDatabase.has_instance(), "DispersyDatabase has not yet been created"
            database = DispersyDatabase.get_instance()

            try:
                database_id, mid, tags, private_key_from_db = database.execute(u"SELECT m.id, m.mid, m.tags, p.private_key FROM member AS m LEFT OUTER JOIN private_key AS p ON p.member = m.id WHERE m.public_key = ? LIMIT 1", (buffer(public_key),)).next()

            except StopIteration:
                mid = sha1(public_key).digest()
                private_key_from_db = None
                try:
                    database_id, tags = database.execute(u"SELECT id, tags FROM member WHERE mid = ? LIMIT 1", (buffer(mid),)).next()

                except StopIteration:
                    database.execute(u"INSERT INTO member (mid, public_key) VALUES (?, ?)", (buffer(mid), buffer(public_key)))
                    database_id = database.last_insert_rowid
                    tags = u""

                else:
                    database.execute(u"UPDATE member SET public_key = ? WHERE id = ?", (buffer(public_key), database_id))

            else:
                mid = str(mid)
                private_key_from_db = str(private_key_from_db) if private_key_from_db else ""
                assert private_key_from_db == "" or ec_check_private_bin(private_key_from_db), private_key_from_db.encode("HEX")

            if private_key_from_db:
                private_key = private_key_from_db
            elif private_key:
                database.execute(u"INSERT INTO private_key (member, private_key) VALUES (?, ?)", (database_id, buffer(private_key)))

            self._database = database
            self._database_id = database_id
            self._mid = mid
            self._public_key = public_key
            self._private_key = private_key
            self._ec = ec_from_private_bin(private_key) if private_key else ec_from_public_bin(public_key)
            self._signature_length = ec_signature_length(self._ec)
            self._tags = [tag for tag in tags.split(",") if tag]

            if __debug__:
                assert len(set(self._tags)) == len(self._tags), ("there are duplicate tags", self._tags)
                for tag in self._tags:
                    assert tag in (u"store", u"ignore", u"blacklist"), tag

            if __debug__: dprint("mid:", self._mid.encode("HEX"), " db:", self._database_id, " public:", bool(self._public_key), " private:", bool(self._private_key))

    @property
    def public_key(self):
        """
        The public key.

        This is binary representation of the public key.
        """
        return self._public_key

    @property
    def private_key(self):
        """
        The private key.

        This is binary representation of the private key.

        It may be an empty string when the private key is not yet available.  In this case the sign
        method will raise a RuntimeError.
        """
        return self._private_key

    @property
    def signature_length(self):
        """
        The length, in bytes, of a signature.
        """
        return self._signature_length

    def has_identity(self, community):
        """
        Returns True when we have a dispersy-identity message for this member in COMMUNITY.
        """
        if __debug__:
            from community import Community
            assert isinstance(community, Community)
        try:
            self._database.execute(u"SELECT 1 FROM sync WHERE member = ? AND meta_message = ?",
                                   (self._database_id, community.get_meta_message(u"dispersy-identity").database_id)).next()
        except StopIteration:
            return False
        return True

    def _set_tag(self, tag, value):
        assert isinstance(tag, unicode)
        assert tag in [u"store", u"ignore", u"blacklist"]
        assert isinstance(value, bool)
        if __debug__: dprint(tag, " -> ", value)
        if value:
            if tag in self._tags:
                # the tag is already set
                return False
            self._tags.append(tag)

        else:
            if not tag in self._tags:
                # the tag isn't there to begin with
                return False
            self._tags.remove(tag)

        self._database.execute(u"UPDATE member SET tags = ? WHERE id = ?", (u",".join(sorted(self._tags)), self._database_id))
        return True

    # @property
    def __get_must_store(self):
        return u"store" in self._tags
    # @must_store.setter
    def __set_must_store(self, value):
        return self._set_tag(u"store", value)
    # .setter was introduced in Python 2.6
    must_store = property(__get_must_store, __set_must_store)

    # @property
    def __get_must_ignore(self):
        return u"ignore" in self._tags
    # @must_ignore.setter
    def __set_must_ignore(self, value):
        return self._set_tag(u"ignore", value)
    # .setter was introduced in Python 2.6
    must_ignore = property(__get_must_ignore, __set_must_ignore)

    # @property
    def __get_must_blacklist(self):
        return u"blacklist" in self._tags
    # @must_blacklist.setter
    def __set_must_blacklist(self, value):
        return self._set_tag(u"blacklist", value)
    # .setter was introduced in Python 2.6
    must_blacklist = property(__get_must_blacklist, __set_must_blacklist)

    def verify(self, data, signature, offset=0, length=0):
        """
        Verify that DATA, starting at OFFSET up to LENGTH bytes, was signed by this member and
        matches SIGNATURE.

        DATA is the signed data and the signature concatenated.
        OFFSET is the offset for the signed data.
        LENGTH is the length of the signature and the data, in bytes.

        Returns True or False.
        """
        assert isinstance(data, str)
        assert isinstance(signature, str)
        assert isinstance(offset, (int, long))
        assert isinstance(length, (int, long))
        return self._public_key and \
               self._signature_length == len(signature) \
               and ec_verify(self._ec, sha1(data[offset:offset+(length or len(data))]).digest(), signature)

    def sign(self, data, offset=0, length=0):
        """
        Returns the signature of DATA, starting at OFFSET up to LENGTH bytes.

        Will raise a RuntimeError when this we do not have the private key.
        """
        if self._private_key:
            return ec_sign(self._ec, sha1(data[offset:length or len(data)]).digest())
        else:
            raise RuntimeError("unable to sign data without the private key")

    def __eq__(self, member):
        assert isinstance(member, DummyMember)
        assert (self._database_id == member.database_id) == (self._mid == member.mid)
        return self._database_id == member.database_id

    def __ne__(self, member):
        assert isinstance(member, DummyMember)
        assert (self._database_id == member.database_id) == (self._mid == member.mid)
        return self._database_id != member.database_id

    def __cmp__(self, member):
        assert isinstance(member, DummyMember)
        assert (self._database_id == member.database_id) == (self._mid == member.mid)
        return cmp(self._database_id, member.database_id)

    def __hash__(self):
        """
        Allows Member classes to be used as keys in a dictionary.
        """
        return self._public_key.__hash__()

    def __str__(self):
        """
        Returns a human readable string representing the member.
        """
        return "<%s %d %s>" % (self.__class__.__name__, self._database_id, self._mid.encode("HEX"))
