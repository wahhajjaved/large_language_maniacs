#!/usr/bin/python3

import os
import sys
import pyodbc
import pytz
import time

from argparse         import ArgumentParser
from ldap3            import Server, Connection, SCHEMA, BASE, LEVEL
from ldap3            import ALL_ATTRIBUTES, DEREF_NEVER
from ldap3            import MODIFY_REPLACE, MODIFY_DELETE, MODIFY_ADD
from datetime         import datetime
from ldaptimestamp    import LdapTimeStamp
from aes_pkcs7        import AES_Cipher
from binascii         import hexlify, unhexlify

def log (msg) :
    """ FIXME: We want real logging someday """
    print (msg)
# end def log

class LDAP_Access (object) :

    def __init__ (self, args) :
        self.args  = args
        # FIXME: Poor-mans logger for now
        self.log = Namespace ()
        self.log ['debug'] = self.log ['error'] = self.log ['warn'] = log

        self.srv   = Server (self.args.uri, get_info = SCHEMA)
        self.ldcon = Connection \
            (self.srv, self.args.bind_dn, self.args.password)
        self.ldcon.bind ()
        if not self.ldcon.bound :
            msg = \
                ( "Error on LDAP bind: %(description)s: %(message)s"
                  " (code: %(result)s)"
                % self.ldcon.result
                )
            self.log.error (msg)
            sys.exit (23)
    # end def __init__

    def get_by_dn (self, dn, base_dn = None) :
        """ Get entry by dn
        """
        if base_dn is None :
            base_dn = self.dn
        r = self.ldcon.search \
            ( dn, '(objectClass=*)'
            , search_scope = BASE
            , attributes   = ALL_ATTRIBUTES
            )
        if r :
            if len (self.ldcon.response) != 1 :
                self.log.error ("Got more than one record with dn %s" % dn)
            return self.ldcon.response [0]
    # end def get_by_dn

    def get_entry (self, pk_uniqueid) :
        r = self.ldcon.search \
            ( self.dn, '(phonlineUniqueId=%s)' % pk_uniqueid
            , search_scope = LEVEL
            , attributes   = ALL_ATTRIBUTES
            )
        if r :
            if len (self.ldcon.response) != 1 :
                self.log.error \
                    ( "Got more than one record with pk_uniqueid %s"
                    % pk_uniqueid
                    )
            return self.ldcon.response [0]
    # end def get_entry

    def set_dn (self, dn) :
        self.dn = dn
    # end def set_dn

    def __getattr__ (self, name) :
        """ Delegate to our ldcon, caching variant """
        if name.startswith ('_') :
            raise AttributeError (name)
        r = getattr (self.ldcon, name)
        # Don't cache!
        return r
    # end def __getattr__

# end class LDAP_Access

class Namespace (dict) :
    def __getattr__ (self, key) :
        try :
            return self [key]
        except KeyError as ke :
            raise AttributeError (ke)
    # end def __getattr__
# end class Namespace

def from_db_date (item) :
    """ Note that phonline stores the only date attribute
        "phonlineGebDatum" as a string!
        Also note: the seconds always contain a trailing '.0' in the
        original LDAP tree.
    """
    return item.strftime ("%Y-%m-%d %H:%M:%S") + '.0'
# end def from_db_date

def from_db_number (item) :
    if item is None :
        return item
    return str (int (item))
# end def from_db_number

def from_db_rstrip (item) :
    """ Strip items before writing to LDAP. Note that if the stripping
        results in an empty string we return None (leave attribute empty)
    """
    if item is None :
        return item
    item = item.rstrip ()
    if item :
        return item
    return None
# end def from_db_rstrip

def from_db_strip (item) :
    """ Strip items before writing to LDAP. Note that if the stripping
        results in an empty string we return None (leave attribute empty)
    """
    if item is None :
        return item
    item = item.strip ()
    if item :
        return item
    return None
# end def from_db_strip

def from_multi (item) :
    """ Return array for an item containing several fields separated by
        semicolon in the database
    """
    if item is None :
        return item
    return item.split (';')
# end def from_multi

class ODBC_Connector (object) :

    fields = dict \
        ( benutzer_alle_dirxml_v =
            ( 'person_nr_obf'
            , 'st_person_nr_obf'
            , 'org_einheiten'
            , 'emailadresse_b'
            , 'emailadresse_st'
            , 'bpk'
            , 'pm_sap_personalnummer'
            , 'schulkennzahlen'
            , 'funktionen'
            , 'pk_uniqueid'
            , 'vorname'
            , 'nachname'
            , 'benutzername'
            , 'passwort'
            , 'benutzergruppen'
            , 'aktiv_st_person'
            , 'aktiv_a_person'
            , 'aktiv_b_person'
            , 'chipid_b'
            , 'chipid_st'
            , 'chipid_a'
            , 'mirfareid_b'
            , 'mirfareid_st'
            , 'mirfareid_a'
            , 'matrikelnummer'
            , 'account_status_b'
            , 'account_status_st'
            , 'account_status_a'
            , 'geburtsdatum'
            , 'person_nr'
            , 'st_person_nr'
            , 'ident_nr'
            )
        , eventlog_ph =
            ( 'record_id'
            , 'table_key'
            , 'status'
            , 'event_type'
            , 'event_time'
            , 'perpetrator'
            , 'table_name'
            , 'column_name'
            , 'old_value'
            , 'new_value'
            , 'synch_id'
            , 'synch_online_flag'
            , 'transaction_flag'
            , 'read_time'
            , 'error_message'
            , 'attempt'
            , 'admin_notify_flag'
            )
        )
    odbc_to_ldap_field = dict \
        ( account_status_a      = 'phonlineAccStWeiterbildung'
        , account_status_b      = 'phonlineAccStBediensteter'
        , account_status_st     = 'phonlineAccStStudent'
        , aktiv_a_person        = 'phonlineWeiterbildungAktiv'
        , aktiv_b_person        = 'phonlineBediensteterAktiv'
        , aktiv_st_person       = 'phonlineStudentAktiv'
        , benutzergruppen       = 'phonlineBenutzergruppe'
        , benutzername          = 'cn'
        , bpk                   = 'phonlineBPK'
        , chipid_a              = 'phonlineChipIDWeiterbildung'
        , chipid_b              = 'phonlineChipIDBediensteter'
        , chipid_st             = 'phonlineChipIDStudent'
        , emailadresse_b        = 'phonlineEmailBediensteter'
        , emailadresse_st       = 'phonlineEmailStudent'
        , funktionen            = 'phonlineFunktionen'
        , geburtsdatum          = 'phonlineGebDatum'
        , ident_nr              = 'phonlineIdentNr'
        , matrikelnummer        = 'phonlineMatrikelnummer'
        , mirfareid_a           = 'phonlineMirfareIDWeiterbildung'
        , mirfareid_b           = 'phonlineMirfareIDBediensteter'
        , mirfareid_st          = 'phonlineMirfareIDStudent'
        , nachname              = 'sn'
        , org_einheiten         = 'phonlineOrgEinheiten'
        , passwort              = 'idnDistributionPassword'
        , person_nr             = 'phonlinePersonNr'
        , person_nr_obf         = 'phonlinePersonNrOBF'
        , pk_uniqueid           = 'phonlineUniqueId'
        , pm_sap_personalnummer = 'phonlineSapPersnr'
        , schulkennzahlen       = 'phonlineSchulkennzahlen'
        , st_person_nr          = 'phonlinePersonNrStudent'
        , st_person_nr_obf      = 'phonlinePersonNrOBFStudent'
        , vorname               = 'givenName'
        )

    data_conversion = dict \
        ( geburtsdatum    = from_db_date
        , ident_nr        = from_db_number
        , person_nr       = from_db_number
        , st_person_nr    = from_db_number
        , pk_uniqueid     = from_db_number
        , funktionen      = from_multi
        , schulkennzahlen = from_multi
        , emailadresse_b  = from_db_rstrip
        , emailadresse_st = from_db_rstrip
        , benutzername    = from_db_strip
        , vorname         = from_db_rstrip
        , nachname        = from_db_rstrip
        )
    event_types = \
        { 4.0   : 'delete'
        , 5.0   : 'insert'
        , 6.0   : 'update'
        }


    def __init__ (self, args) :
        self.args      = args
        self.ldap      = LDAP_Access (self.args)
        self.table     = 'benutzer_alle_dirxml_v'
        self.crypto_iv = None
        if self.args.crypto_iv :
            self.crypto_iv = self.args.crypto_iv
        self.aes = AES_Cipher \
            (hexlify (self.args.encryption_password.encode ('utf-8')))
        # FIXME: Poor-mans logger for now
        self.log = Namespace ()
        self.log ['debug'] = self.log ['error'] = self.log ['warn'] = log
        self.get_passwords ()
        # copy class dict to local dict
        self.data_conversion = dict (self.data_conversion)
        # and add a bound method
        self.data_conversion ['passwort'] = self.from_password
    # end def __init__

    def action (self) :
        if self.args.action == 'initial_load' :
            self.initial_load ()
        else :
            while True :
                for dn, db in zip (self.args.base_dn, self.args.databases) :
                    self.db = db
                    self.dn = dn
                    self.ldap.set_dn (dn)
                    self.cnx    = pyodbc.connect (DSN = db)
                    self.cursor = self.cnx.cursor ()
                    self.etl ()
                time.sleep (self.args.sleeptime)
    # end def action

    def delete_in_ldap (self, pk_uniqueid) :
        uid = self.to_ldap (pk_uniqueid, 'pk_uniqueid')
        ldrec = self.ldap.get_entry (uid)
        if not ldrec :
            return
        dn = ldrec ['dn']
        r = self.ldap.delete (dn)
        if not r :
            msg = \
                ( "Error on LDAP delete: "
                  "%(description)s: %(message)s"
                  " (code: %(result)s)"
                % self.ldap.result
                )
            self.log.error (msg)
            return msg
    # end def delete_in_ldap

    def etl (self) :
        tbl    = 'eventlog_ph'
        fields = self.fields [tbl]
        sql = "select %s from %s where status in ('N', 'E')"
        sql = sql % (', '.join (fields), tbl)
        self.cursor.execute (sql)
        updates = {}
        for row in self.cursor.fetchall () :
            rw = Namespace ((k, row [i]) for i, k in enumerate (fields))
            if rw.event_type not in self.event_types :
                msg = 'Invalid event_type: %s' % rw.event_type
                updates [rw.record_id] = dict \
                    ( error_message = msg
                    , status        = 'F'
                    )
                self.error (msg)
                continue
            event_type = self.event_types [rw.event_type]
            if not rw.table_key.startswith ('pk_uniqueid=') :
                msg = 'Invalid table_key, expect pk_uniqueid='
                updates [rw.record_id] = dict \
                    ( error_message = msg
                    , status        = 'F'
                    )
                self.error (msg)
                continue
            if rw.table_name.lower () != 'benutzer_alle_dirxml_v' :
                msg = 'Invalid table_name, expect benutzer_alle_dirxml_v'
                updates [rw.record_id] = dict \
                    ( error_message = msg
                    , status        = 'F'
                    )
                self.error (msg)
                continue
            uid = rw.table_key.split ('=', 1) [-1]
            try :
                uid = int (uid)
            except ValueError :
                msg = 'Invalid table_key, expect numeric id'
                updates [rw.record_id] = dict \
                    ( error_message = msg
                    , status        = 'F'
                    )
                self.error (msg)
                continue
            sql = 'select %s from %s where pk_uniqueid = ?'
            sql = sql % (','.join (self.fields [self.table]), self.table)
            self.cursor.execute (sql, uid)
            usr = self.cursor.fetchall ()
            assert len (usr) <= 1
            self.warning_message = None
            if len (usr) :
                if event_type == 'delete' :
                    msg = 'Record %s existing in DB' % uid
                    updates [rw.record_id] = dict \
                        ( error_message = msg
                        , status        = 'W'
                        )
                    self.log.warn (msg)
                is_new = event_type == 'insert'
                msg = self.sync_to_ldap (usr [0], is_new = is_new)
            else :
                if event_type != 'delete' :
                    msg = 'Record %s not existing in DB' % uid
                    updates [rw.record_id] = dict \
                        ( error_message = msg
                        , status        = 'W'
                        )
                    self.log.warn (msg)
                msg = self.delete_in_ldap (uid)
            if msg :
                # Error message, overwrite possible earlier warnings for
                # this record
                status  = 'E'
                attempt = int (rw.attempt)
                if attempt > 10 :
                    status = 'F'
                attempt += 1
                updates [rw.record_id] = dict \
                    ( error_message = msg
                    , status        = status
                    , attempt       = attempt
                    )
            elif self.warning_message :
                if rw.record_id in updates :
                    assert updates [rw.record_id][status] == 'W'
                    updates [rw.record_id]['error_message'] = '\n'.join \
                        (( updates [rw.record_id]['error_message']
                         , self.warning_message
                        ))
                else :
                    updates [rw.record_id] = dict \
                        ( error_message = self.warning_message
                        , status        = 'W'
                        )
            elif rw.record_id in updates :
                pass
            else :
                updates [rw.record_id] = dict (status = 'S')
            updates [rw.record_id]['read_time'] = datetime.utcnow ()
        for key in updates :
            fn  = list (sorted (updates [key].keys ()))
            sql = "update eventlog_ph set %s where record_id = ?"
            sql = sql % ', '.join ('%s = ?' % k for k in fn)
            #print (sql)
            p   = list (updates [key][k] for k in fn)
            p.append (float (key))
            #print (p)
            self.cursor.execute (sql, * p)
        self.cursor.commit ()
    # end def etl

    def generate_initial_tree (self) :
        """ Check if initial tree exists, generate if non-existing
        """
        top = None
        for dn in self.args.base_dn :
            dnparts = dn.split (',')
            bdn = ''
            for dn in reversed (dnparts) :
                if top is None :
                    top = dn
                if bdn :
                    bdn = ','.join ((dn, bdn))
                else :
                    bdn = dn
                entry = self.ldap.get_by_dn (bdn, base_dn = top)
                k, v  = dn.split ('=', 1)
                if entry :
                    assert entry ['attributes'][k] in (v, [v])
                    continue
                d = {k : v}
                if k == 'o' :
                    d ['objectClass'] = 'Organization'
                else :
                    d ['objectClass'] = 'organizationalUnit'
                r = self.ldap.add (bdn, attributes = d)
                if not r :
                    msg = \
                        ( "Error on LDAP add: "
                          "%(description)s: %(message)s"
                          " (code: %(result)s)"
                        % self.ldap.result
                        )
                    self.log.error (msg)
                    self.log.error ("DN: %s, Attributes were: %s" % (bdn, d))
    # end def generate_initial_tree

    def get_passwords (self) :
        self.passwords = dict ()
        with open ('/etc/conf/passwords', 'r') as f :
            for line in f :
                line = line.strip ()
                if line.startswith ('DATABASE_PASSWORDS') :
                    pws = line.split ('=', 1)[-1].strip ()
                    for entry in pws.split (',') :
                        db, pw = (x.strip () for x in entry.split (':', 1))
                        self.passwords [db] = pw
    # end def get_passwords

    def initial_load (self) :
        self.generate_initial_tree ()
        for bdn, db in zip (self.args.base_dn, self.args.databases) :
            self.db = db
            self.dn = bdn
            self.ldap.set_dn (self.dn)
            self.log.debug ("%s: %s" % (db, self.dn))
            # Get all unique ids currently in ldap under our tree
            self.uidmap = {}
            r = self.ldap.search \
                ( self.dn, '(phonlineUniqueId=*)'
                , search_scope = LEVEL
                , attributes   = ['phonlineUniqueId']
                )
            if r :
                for entry in self.ldap.response :
                    uid = entry ['attributes']['phonlineUniqueId']
                    self.uidmap [uid] = entry ['dn']
                    assert entry ['dn'].endswith (self.dn)
            self.cnx    = pyodbc.connect (DSN = db)
            self.cursor = self.cnx.cursor ()
            tbl         = self.table
            fields      = self.fields [tbl]
            self.cursor.execute \
                ('select %s from %s' % (','.join (fields), self.table))
            for n, row in enumerate (self.cursor) :
                if (n % 100) == 0 or self.args.verbose :
                    self.log.debug (n)
                idx = fields.index ('pk_uniqueid')
                uid = "%d" % row [idx]
                if uid in self.uidmap :
                    del self.uidmap [uid]
                self.sync_to_ldap (row, is_new = True)
            for u in sorted (self.uidmap) :
                udn = self.uidmap [u]
                self.log.warn ("Deleting: %s: %s" % (u, udn))
                r = self.ldap.delete (udn)
                if not r :
                    msg = \
                        ( "Error on LDAP delete: "
                          "%(description)s: %(message)s"
                          " (code: %(result)s)"
                        % self.ldap.result
                        )
                    self.log.error (msg)
        self.log.warn ("SUCCESS")
        sys.stdout.flush ()
        # Default is to wait forever after initial load
        if not self.args.terminate :
            while True :
                time.sleep (self.args.sleeptime)
    # end def initial_load

    def sync_to_ldap (self, row, is_new = False) :
        """ Sync a single record to LDAP. We return an error message if
            something goes wrong (and log the error). The caller might
            want to put the error message into some table in the
            database.
        """
        timestamp = LdapTimeStamp (datetime.now (pytz.utc))
        etl_ts = timestamp.as_generalized_time ()
        tbl = self.table
        rw  = Namespace ((k, row [i]) for i, k in enumerate (self.fields [tbl]))
        if not rw.pk_uniqueid :
            # FIXME: Do we want to log user data here??
            self.log.error ("Got User without pk_uniqueid")
            return
        # Find pk_uniqueid in LDAP phonlineUniqueId
        uid   = self.to_ldap (rw.pk_uniqueid, 'pk_uniqueid')
        ldrec = self.ldap.get_entry (uid)
        if ldrec :
            if is_new :
                # Log a warning but continue like a normal sync
                # During initial_load issue warning only if verbose
                msg = 'Found pk_uniqueid "%s" when sync says it should be new' \
                    % uid
                if self.args.verbose or self.args.action != 'initial_load' :
                    self.log.warn (msg)
                self.warning_message = msg
            # Ensure we use the same IV for comparison
            pw = ldrec ['attributes'].get ('idnDistributionPassword', '')
            if len (pw) > 32 :
                self.crypto_iv = pw [:32]
            ld_update = {}
            ld_delete = {}
            for k in rw :
                v  = self.to_ldap (rw [k], k)
                lk = self.odbc_to_ldap_field [k]
                lv = ldrec ['attributes'].get (lk, None)
                if v == lv or [v] == lv :
                    continue
                if v is None :
                    ld_delete [lk] = None
                else :
                    # Ensure we use new random IV if pw changes
                    # We've used the IV of the old password for
                    # comparison previously
                    if k == 'passwort' :
                        self.crypto_iv = self.args.crypto_iv
                        v = self.to_ldap (rw [k], k)
                    ld_update [lk] = v
            assert 'phonlineUniqueId' not in ld_update
            assert 'phonlineUniqueId' not in ld_delete
            if not ld_delete and not ld_update :
                return
            ld_update ['etlTimestamp'] = etl_ts
            # dn modified, the cn is the rdn!
            dn = ldrec ['dn']
            if 'cn' in ld_update :
                cn = 'cn=' + ld_update ['cn']
                r  = self.ldap.modify_dn (ldrec ['dn'], cn)
                if not r :
                    msg = \
                        ( "Error on LDAP modify_dn: "
                          "%(description)s: %(message)s"
                          " (code: %(result)s)"
                        % self.ldap.result
                        )
                    self.log.error (msg)
                    return msg
                del ld_update ['cn']
                dn = cn + ',' + dn.split (',', 1)[-1]
            if 'idnDistributionPassword' in ld_update :
                self.ldap.extend.standard.modify_password \
                    (dn, new_password = rw ['passwort'].encode ('utf-8'))
            if ld_update or ld_delete :
                changes = {}
                for k in ld_update :
                    if isinstance (ld_update [k], type ([])) :
                        changes [k] = (MODIFY_REPLACE, ld_update [k])
                    else :
                        changes [k] = (MODIFY_REPLACE, [ld_update [k]])
                for k in ld_delete :
                    changes [k] = (MODIFY_DELETE, [])
                r = self.ldap.modify (dn, changes)
                if not r :
                    msg = \
                        ( "Error on LDAP modify: "
                          "%(description)s: %(message)s"
                          " (code: %(result)s)"
                        % self.ldap.result
                        )
                    self.log.error (msg + str (changes))
                    return msg
        else :
            # Ensure we use new random IV if pw changes
            # We've used the IV of the old password for
            # comparison previously
            self.crypto_iv = self.args.crypto_iv
            if not is_new :
                # Log a warning but continue like a normal sync
                msg = 'pk_uniqueid "%s" not found, sync says it exists' % uid
                self.log.warn (msg)
                self.warning_message = msg
            ld_update = {}
            for k in rw :
                lk = self.odbc_to_ldap_field [k]
                v  = self.to_ldap (rw [k], k)
                if v is not None :
                    ld_update [lk] = v
            ld_update ['objectClass'] = \
                ['inetOrgPerson', 'phonlinePerson','idnSyncstat']
            ld_update ['etlTimestamp'] = etl_ts
            dn = ('cn=%s,' % ld_update ['cn']) + self.dn
            r  = self.ldap.add (dn, attributes = ld_update)
            if not r :
                msg = \
                    ( "Error on LDAP add: %(description)s: %(message)s"
                      " (code: %(result)s)"
                    % self.ldap.result
                    )
                self.log.error (msg)
                return msg
            if 'idnDistributionPassword' in ld_update :
                self.ldap.extend.standard.modify_password \
                    (dn, new_password = rw ['passwort'])
    # end def sync_to_ldap

    def to_ldap (self, item, dbkey) :
        conv = self.data_conversion.get (dbkey)
        if conv :
            return conv (item)
        return item
    # end def to_ldap

    def from_password (self, item) :
        """ Return encrypted password
        """
        iv = None
        if self.crypto_iv :
            iv = unhexlify (self.crypto_iv)
        return self.aes.encrypt (item.encode ('utf-8'), iv).decode ('ascii')
    # end def from_password

# end class ODBC_Connector

def main () :
    cmd = ArgumentParser ()
    cmd.add_argument \
        ( 'action'
        , help    = 'Action to perform, one of "initial_load", "etl"'
        )
    default_bind_dn = os.environ.get ('LDAP_BIND_DN', 'cn=admin,o=BMUKK')
    cmd.add_argument \
        ( "-B", "--bind-dn"
        , help    = "Bind-DN, default=%(default)s"
        , default = default_bind_dn
        )
    cmd.add_argument \
        ( "-c", "--database-connect"
        , dest    = 'databases'
        , help    = "Database name for connecting usually configured via "
                    "environment, will use *all* databases specified"
        , action  = 'append'
        , default = []
        )
    cmd.add_argument \
        ( "-d", "--base-dn"
        , help    = "Base-DN for starting search, usually configured via "
                    "environment, will use *all* databases specified"
        , action  = 'append'
        , default = []
        )
    cmd.add_argument \
        ( "-i", "--crypto-iv"
        , help    = "You can pass in a fixed crypto initialisation vector"
                    " for regression testing -- don't do this in production!"
        )
    cmd.add_argument \
        ( '-o', '--output-file'
        , help    = 'Output file for writing CSV, default is table name'
        )
    # Get default_pw from /etc/conf/passwords LDAP_PASSWORD entry.
    # Also get password-encryption password when we're at it
    ldap_pw = 'changeme'
    pw_encr = 'changemetoo*****' # must be 16 characters long after encoding
    with open ('/etc/conf/passwords', 'r') as f :
        for line in f :
            if line.startswith ('LDAP_PASSWORD') :
                ldap_pw = line.split ('=', 1) [-1].strip ()
            if line.startswith ('PASSWORD_ENCRYPTION_PASSWORD') :
                pw_encr = line.split ('=', 1) [-1].strip ()
    cmd.add_argument \
        ( "-P", "--password"
        , help    = "Password(s) for binding to LDAP"
        , default = ldap_pw
        )
    cmd.add_argument \
        ( "-p", "--encryption-password"
        , help    = "Password(s) for encrypting passwords in LDAP"
        , default = pw_encr
        )
    sleeptime = int (os.environ.get ('ETL_SLEEPTIME', '20'))
    cmd.add_argument \
        ( '-s', '--sleeptime'
        , help    = "Seconds to sleep between etl invocations, "
                    " default=%(default)s"
        , type    = int
        , default = sleeptime
        )
    cmd.add_argument \
        ( '-t', '--terminate'
        , help    = "Terminate container after initial_load"
        , action  = "store_true"
        , default = False
        )
    cmd.add_argument \
        ( '-v', '--verbose'
        , help    = "Verbose logging"
        , action  = "store_true"
        , default = False
        )
    default_ldap = os.environ.get ('LDAP_URI', 'ldap://06openldap:8389')
    cmd.add_argument \
        ( '-u', '--uri'
        , help    = "LDAP uri, default=%(default)s"
        , default = default_ldap
        )
    args = cmd.parse_args ()
    if not args.base_dn or not args.databases :
        args.base_dn   = []
        args.databases = []
        for inst in os.environ ['DATABASE_INSTANCES'].split (',') :
            db, dummy = (x.strip () for x in inst.split (':'))
            dn = ','.join \
                (( os.environ ['LDAP_USER_OU']
                ,  'ou=%s' % db
                ,  os.environ ['LDAP_BASE_DN']
                ))
            args.base_dn.append   (dn)
            args.databases.append (db)

    odbc = ODBC_Connector (args)
    odbc.action ()
# end def main

if __name__ == '__main__' :
    main ()
