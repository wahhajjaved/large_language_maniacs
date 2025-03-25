#coding:utf-8
import os
import string
import sys
import time
import re
import StringIO
import tempfile
import select
from email.parser import Parser
from email.message import Message
from gettext import gettext as _
from subprocess import Popen, PIPE

from mailpile.crypto.state import *
from mailpile.crypto.mime import MimeSigningWrapper, MimeEncryptingWrapper


DEFAULT_SERVER = "pool.sks-keyservers.net"
GPG_KEYID_LENGTH = 8
GNUPG_HOMEDIR = None  # None=use what gpg uses

openpgp_trust = {"-": _("Trust not calculated"),
                 "o": _("Unknown trust"),
                 "q": _("Undefined trust"),
                 "n": _("Never trust"),
                 "m": _("Marginally trust"),
                 "f": _("Full trust"),
                 "u": _("Ultimate trust"),
                 "e": _("Expired key, not trusted"),
                 "d": _("Disabled key, not trusted"),  # Deprecated flag.
                 "r": _("Revoked key, not trusted")}

openpgp_algorithms = {1: _("RSA"),
                      2: _("RSA (encrypt only)"),
                      3: _("RSA (sign only)"),
                      16: _("Elgamal (encrypt only)"),
                      17: _("DSA"),
                      20: _("Elgamal (encrypt/sign) [COMPROMISED]")}
# For details on type 20 compromisation, see
# http://lists.gnupg.org/pipermail/gnupg-announce/2003q4/000160.html

# These are detailed in the GnuPG source under doc/DETAILS.
status_messages = {
    "ENTER": [],
    "LEAVE": [],
    "ABORT": [],
    "NEWSIG": [],
    "GOODSIG": ["long_keyid_or_fpr", "username"],
    "KEYEXPIRED": ["expire_timestamp"],
    "KEYREVOKED": [],
    "BADSIG": ["long_keyid_or_fpr", "username"],
    "ERRSIG": ["long_keyid_or_fpr", "pubkey_algo", "hash_algo", "sig_class",
               "timestamp", "rc"],
    "BADARMOR": [],
    "TRUST_UNDEFINED": ["error_token"],
    "TRUST_NEVER": ["error_token"],
    "TRUST_MARGINAL": ["zero", "validation_model"],
    "TRUST_FULLY": ["zero", "validation_model"],
    "TRUST_ULTIMATE": ["zero", "validation_model"],
    "GET_BOOL": [],
    "GET_LINE": [],
    "GET_HIDDEN": [],
    "GOT_IT": [],
    "SHM_INFO": [],
    "SHM_GET": [],
    "SHM_GET_BOOL": [],
    "SHM_GET_HIDDEN": [],
    "NEED_PASSPHRASE": ["long_main_keyid", "long_keyid",
                        "keytype", "keylength"],
    "VALIDSIG": ["fingerprint", "sig_creation_date", "sig_timestamp",
                 "expire_timestamp", "sig_version", "reserved", "pubkey_algo",
                 "hash_algo", "sig_class", "primary_key_fpr"],
    "SIG_ID": ["radix64_string", "sig_creation_date", "sig_timestamp"],
    "ENC_TO": ["long_keyid", "keytype", "keylength"],
    "NODATA": ["what"],
    "BAD_PASSPHRASE": ["long_keyid"],
    "NO_PUBKEY": ["long_keyid"],
    "NO_SECKEY": ["long_keyid"],
    "NEED_PASSPHRASE_SYM": ["cipher_algo", "s2k_mode", "s2k_hash"],
    "NEED_PASSPHRASE_PIN": ["card_type", "chvno", "serialno"],
    "DECRYPTION_FAILED": [],
    "DECRYPTION_OKAY": [],
    "MISSING_PASSPHRASE": [],
    "GOOD_PASSPHRASE": [],
    "GOODMDC": [],
    "BADMDC": [],
    "ERRMDC": [],
    "IMPORTED": ["long keyid", "username"],
    "IMPORT_OK": ["reason", "fingerprint"],
    "IMPORT_PROBLEM": ["reason", "fingerprint"],
    "IMPORT_CHECK": [],
    "IMPORT_RES": ["count", "no_user_id", "imported", "imported_rsa",
                   "unchanged", "n_uids", "n_subk", "n_sigs", "n_revoc",
                   "sec_read", "sec_imported", "sec_dups", "skipped_new_keys",
                   "not_imported"],
    "FILE_START": ["what", "filename"],
    "FILE_DONE": [],
    "FILE_ERROR": [],
    "BEGIN_DECRYPTION": ["mdc_method", "sym_algo"],
    "END_DECRYPTION": [],
    "BEGIN_ENCRYPTION": [],
    "END_ENCRYPTION": [],
    "DELETE_PROBLEM": ["reason_code"],
    "PROGRESS": ["what", "char", "cur", "total"],
    "SIG_CREATED": ["type" "pubkey algo", "hash algo", "class",
                    "timestamp", "key fpr"],
    "SESSION_KEY": ["algo:hexdigits"],
    "NOTATION_NAME": ["name"],
    "NOTATION_DATA": ["string"],
    "POLICY_URL": ["string"],
    "BEGIN_STREAM": [],
    "END_STREAM": [],
    "KEY_CREATED": ["type", "fingerprint", "handle"],
    "KEY_NOT_CREATED": ["handle"],
    "USERID_HINT": ["long main keyid", "string"],
    "UNEXPECTED": ["what"],
    "INV_RECP": ["reason", "requested_recipient"],
    "INV_SGNR": ["reason", "requested_sender"],
    "NO_RECP": ["reserved"],
    "NO_SGNR": ["reserved"],
    "ALREADY_SIGNED": ["long-keyid"],  # Experimental, may disappear
    "SIGEXPIRED": [],  # Deprecated but may crop up; keyexpired overrides
    "TRUNCATED": ["maxno"],
    "EXPSIG": ["long_keyid_or_fpr", "username"],
    "EXPKEYSIG": ["long_keyid_or_fpr", "username"],
    "REVKEYSIG": ["long_keyid_or_fpr", "username"],
    "ATTRIBUTE": ["fpr", "octets", "type", "index",
                  "count", "timestamp", "expiredate", "flags"],
    "CARDCTRL": ["what", "serialno"],
    "PLAINTEXT": ["format", "timestamp", "filename"],
    "PLAINTEXT_LENGTH": ["length"],
    "SIG_SUBPACKET": ["type", "flags", "len", "data"],
    "SC_OP_SUCCESS": ["code"],
    "SC_OP_FAILURE": ["code"],
    "BACKUP_KEY_CREATED": ["fingerprint", "fname"],
    "PKA_TRUST_BAD": ["unknown"],
    "PKA_TRUST_GOOD": ["unknown"],
    "BEGIN_SIGNING": [],
    "ERROR": ["error location", "error code", "more"],
    "MOUNTPOINT": ["mdc_method", "sym_algo"],
    "SUCCESS": ["location"],
    "DECRYPTION_INFO": [],
}

UID_PARSE_RE = "([^\(\<]+){0,1}( \((.+)\)){0,1} (\<(.+)\>){0,1}"
def parse_uid(uidstr):
    matches = re.match(UID_PARSE_RE, uidstr)
    if matches:
        email = matches.groups(0)[4] or ""
        comment = matches.groups(0)[2] or ""
        name = matches.groups(0)[0] or ""
    else:
        email = uidstr
        name = ""
        comment = ""

    try:
        name = name.decode("utf-8")
    except UnicodeDecodeError:
        try:
            name = name.decode("iso-8859-1")
        except UnicodeDecodeError:
            name = name.decode("utf-8", "replace")

    try:
        comment = comment.decode("utf-8")
    except UnicodeDecodeError:
        try:
            comment = comment.decode("iso-8859-1")
        except UnicodeDecodeError:
            comment = comment.decode("utf-8", "replace")

    return email, name, comment


class GnuPG:
    """
    Wrap GnuPG and make all functionality feel Pythonic.
    """

    def __init__(self):
        self.available = None
        self.gpgbinary = 'gpg'
        self.passphrase = None
        self.fds = {"passphrase": True,
                    "command": True,
                    "logger": False,
                    "status": False}
        self.handles = {}
        self.pipes = {}
        self.needed_fds = ["stdin", "stdout", "stderr", "status"]
        self.errors = []
        self.statuscallbacks = {}
        global GNUPG_HOMEDIR
        self.homedir = GNUPG_HOMEDIR

    def default_errorhandler(self, *error):
        if error != "":
            self.errors.append(error)
        return True

    def default_output(self, output):
        return output

    def parse_status(self, output, *args):
        status = []
        lines = output.split("\n")
        for line in lines:
            line = line.replace("[GNUPG:] ", "")
            if line == "":
                continue
            elems = line.split(" ")
            callback_kwargs = dict(zip(status_messages, elems[1:]))
            if elems[0] in self.statuscallbacks:
                for callback in self.statuscallbacks[elems[0]]:
                    callback(*kwargs)
            status.append(elems)

        return status

    def parse_verify(self, output, *args):
        lines = output.split("\n")
        sig = {"datetime": "",
               "status": "",
               "keyid": "",
               "signer": "",
               "ok": None,
               "version": "",
               "hash": ""}

        if "no valid OpenPGP data found" in lines[0]:
            sig["ok"] = False
            sig["status"] = lines[1][4:]
        elif False:
            pass

        return sig

    def parse_keylist(self, keylist, *args):
        """
        >>> g = GnuPG()
        >>> v = g.parse_keylist("pub:u:4096:1:D5DC2A79C2E4AE92:2010-12-30:::\
u:Smari McCarthy <smari@immi.is>::scESC:\\nsub:u:4096:1:13E0BB42176BA0AC:\
2010-12-30::::::e:")
        >>> v.has_key("D5DC2A79C2E4AE92")
        True
        >>> v["D5DC2A79C2E4AE92"]["size"]
        4096
        >>> v["D5DC2A79C2E4AE92"]["creation-date"]
        '2010-12-30'
        >>> v["D5DC2A79C2E4AE92"]["algorithm"]
        1
        >>> v["D5DC2A79C2E4AE92"]["subkeys"][0]["algorithm"]
        1
        """
        keys = {}
        curkey = None

        def parse_capabilities(curkey, caps):
            if "e" in caps or "E" in caps:
                keys[curkey]["capabilities"]["encrypt"] = True
            if "s" in caps or "S" in caps:
                keys[curkey]["capabilities"]["sign"] = True
            if "c" in caps or "C" in caps:
                keys[curkey]["capabilities"]["certify"] = True
            if "a" in caps or "A" in caps:
                keys[curkey]["capabilities"]["authenticate"] = True
            if "D" in caps:
                keys[curkey]["disabled"] = True


        def parse_pubkey(line, curkey, keys):
            keys[line[4]] = {
                "size": int(line[2]),
                "creation-date": line[5],
                "uids": [],
                "subkeys": [],
                "signatures": [],
                "trust": line[1],
                "algorithm": int(line[3]),
                "capabilities": {
                    "encrypt": False,
                    "sign": False,
                    "certify": False,
                    "authenticate": False,
                },
                "disabled": False
            }

            if line[6] != "":
                keys[line[4]]["revocation-date"] = line[5]
            curkey = line[4]
            parse_capabilities(curkey, line[11])
            curkey, keys = parse_uidline(line, curkey, keys)
            return (curkey, keys)

        def parse_subkey(line, curkey, keys):
            subkey = {"id": line[4], "size": int(line[2]),
                      "creation-date": line[5],
                      "algorithm": int(line[3])}
            parse_capabilities(curkey, line[11])
            if line[0] == "ssb":
                subkey["secret"] = True
            keys[curkey]["subkeys"].append(subkey)
            return (curkey, keys)

        def parse_fingerprint(line, curkey, keys):
            keys[curkey]["fingerprint"] = line[9]
            return (curkey, keys)

        def parse_userattribute(line, curkey, keys):
            # TODO: We are currently ignoring user attributes as not useful.
            #       We may at some point want to use --attribute-fd and read
            #       in user photos and such?
            return (curkey, keys)

        def parse_privkey(line, curkey, keys):
            curkey, keys = parse_pubkey(line, curkey, keys)
            return (curkey, keys)

        def parse_uidline(line, curkey, keys):
            email, name, comment = parse_uid(line[9])
            keys[curkey]["uids"].append({"email": email,
                                         "name": name,
                                         "comment": comment,
                                         "creation-date": line[5]})
            return (curkey, keys)

        def parse_trust(line, curkey, keys):
            # TODO: We are currently ignoring commentary from the Trust DB.
            return (curkey, keys)

        def parse_signature(line, curkey, keys):
            sig = {"signer": line[9], "signature-date": line[5],
                   "keyid": line[4], "trust": line[10], "algorithm": line[4]}

            keys[curkey]["signatures"].append(sig)
            return (curkey, keys)

        def parse_revoke(line, curkey, keys):
            # FIXME: Do something more to this
            print line
            return (curkey, keys)

        def parse_unknown(line, curkey, keys):
            print "Unknown line with code '%s'" % line[0]
            return (curkey, keys)

        def parse_none(line, curkey, keys):
            return (curkey, keys)

        disp = {"pub": parse_pubkey,
                "sub": parse_subkey,
                "ssb": parse_subkey,
                "fpr": parse_fingerprint,
                "uat": parse_userattribute,
                "sec": parse_privkey,
                "tru": parse_trust,
                "sig": parse_signature,
                "rev": parse_revoke,
                "uid": parse_uidline,
                "gpg": parse_none}

        lines = keylist.split("\n")
        for line in lines:
            if line == "":
                continue
            parms = line.split(":")
            r = disp.get(parms[0], parse_unknown)
            curkey, keys = r(parms, curkey, keys)

        return keys

    def parse_import(self, output, *args):
        res = {"imported": [], "updated": [], "failed": []}
        for x in output:
            if x[0] == "IMPORTED":
                res["imported"].append({
                    "fingerprint": x[1], 
                    "username": x[2]
                })
            elif x[0] == "IMPORT_OK":
                reasons = {
                    "0": "unchanged",
                    "1": "new key",
                    "2": "new user IDs",
                    "4": "new signatures",
                    "8": "new subkeys",
                    "16": "contains private key",
                }
                res["updated"].append({
                    "details": int(x[1]),
                    "details_text": reasons[x[1]],
                    "fingerprint": x[2],
                })
            elif x[0] == "IMPORT_PROBLEM":
                reasons = {
                    "0": "no reason given",
                    "1": "invalid certificate",
                    "2": "issuer certificate missing",
                    "3": "certificate chain too long",
                    "4": "error storing certificate",
                }
                res["failed"].append({
                    "details": int(x[1]),
                    "details_text": reasons[x[1]],
                    "fingerprint": x[2]
                })
            elif x[0] == "IMPORT_RES":
                res["results"] = {
                    "count": int(x[1]),
                    "no_userids": int(x[2]),
                    "imported": int(x[3]),
                    "imported_rsa": int(x[4]),
                    "unchanged": int(x[5]),
                    "num_uids": int(x[6]),
                    "num_subkeys": int(x[7]),
                    "num_signatures": int(x[8]),
                    "num_revoked": int(x[9]),
                    "sec_read": int(x[10]),
                    "sec_imported": int(x[11]),
                    "sec_dups": int(x[12]),
                    "skipped_new_keys": int(x[13]),
                    "not_imported": int(x[14]),
                }
        return res

    def emptycallbackmap():
        """
        Utility function for people who are confused about what callbacks
        exist.
        """
        return dict([[x, []] for x in self.needed_fds])

    def run(self, args=[], callbacks={}, output=None, debug=False):
        """
        >>> g = GnuPG()
        >>> g.run(["--list-keys"])[0]
        0
        
        @return: proc.returncode, retvals
        """
        try :
            import fcntl # Unix-only
            return self._run_with_fcntl(fcntl, args, callbacks, output, debug)
        except ImportError : # perhaps on Windows
            raise NotImplementedError("Currently not for windows")

    def _run_with_fcntl(self, fcntl, args, callbacks, output, debug):
        self.pipes = {}
        args.insert(0, self.gpgbinary)
        args.insert(1, "--utf8-strings")
        args.insert(1, "--with-colons")
        args.insert(1, "--verbose")
        args.insert(1, "--batch")
        args.insert(1, "--enable-progress-filter")

        if self.homedir:
            args.insert(1, "--homedir=%s" % self.homedir)

        try:
            for fd in self.fds.keys():
                if fd not in self.needed_fds:
                    continue
                self.pipes[fd] = os.pipe()
                if debug:
                    print ("Opening fd %s, fh %d, mode %s"
                           ) % (fd,
                                self.pipes[fd][self.fds[fd]],
                                ["r", "w"][self.fds[fd]])
                args.insert(1, "--%s-fd" % fd)
                # The remote end of the pipe:
                args.insert(2, "%d" % self.pipes[fd][not self.fds[fd]])
                fdno = self.pipes[fd][self.fds[fd]]
                self.handles[fd] = os.fdopen(fdno, ["r", "w"][self.fds[fd]])
                # Cause file handles to stay open after execing
                fcntl.fcntl(self.handles[fd], fcntl.F_SETFD, 0)
                fl = fcntl.fcntl(self.handles[fd], fcntl.F_GETFL)
                fcntl.fcntl(self.handles[fd], fcntl.F_SETFL, fl | os.O_NONBLOCK)

            if debug:
                print "Running gpg as: %s" % " ".join(args)

            proc = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE)

            self.handles["stdout"] = proc.stdout
            self.handles["stderr"] = proc.stderr
            self.handles["stdin"] = proc.stdin
            rhandles = dict([(h, k) for (k, h) in self.handles.items()])
            for fd in self.handles.keys():
                fl = fcntl.fcntl(self.handles[fd], fcntl.F_GETFL)
                fcntl.fcntl(self.handles[fd], fcntl.F_SETFL, fl | os.O_NONBLOCK)

            readwrite = dict(self.fds)
            readwrite["stdout"] = False
            readwrite["stderr"] = False
            readwrite["stdin"] = True

            rlist = [h for (k, h) in self.handles.items() if not readwrite.get(k, False)]
            wlist = [h for (k, h) in self.handles.items() if readwrite.get(k, False)]

            buffers = {}
            if output:
                buffers["stdin"] = output
            if self.passphrase:
                buffers["passphrase"] = self.passphrase
            CHUNKSIZE = 1024

            while (rlist or wlist):
                rrlist, rwlist, rxlist = select.select(rlist, wlist, rlist+wlist, 0.02)
                for fd in rrlist:
                    k = rhandles.get(fd)
                    if not k:
                        continue
                    b = buffers.get(k, '')
                    if debug:
                        print "Reading from handle '%s'" % (k,)
                    chunk = self.handles[k].read(CHUNKSIZE)
                    if not chunk:
                        rlist = [h for h in rlist if h != fd]
                        fd.close()
                    buffers[k] = b + chunk
                if proc.returncode is not None and not rrlist:
                    break
                for fd in rwlist:
                    k = rhandles.get(fd)
                    if not k:
                        continue
                    b = buffers.get(k, '')
                    chunk = b[:CHUNKSIZE]
                    buffers[k] = b[CHUNKSIZE:]
                    if debug:
                        print "Writing to handle '%s'" % (k,)
                    self.handles[k].write(chunk)
                    if not buffers[k]:
                        wlist = [h for h in wlist if h != fd]
                        fd.close()
                proc.poll()

            retvals = {"status": []}
            if buffers.get("status", ""):
                for res in self.parse_status(buffers["status"]):
                    retvals["status"].append(res)
            for fd in ["stdout", "stderr"]:
                if fd not in callbacks:
                    continue
                if fd not in retvals:
                    retvals[fd] = []
                if buffers.get(fd, "") == "":
                    retvals[fd].append("")
                    continue
                buf = buffers[fd]
                if isinstance(callbacks[fd], list):
                    for cb in callbacks[fd]:
                        retvals[fd].append(cb(buf))
                else:
                    retvals[fd].append(callbacks[fd](buf))

            while proc.returncode is None:
                proc.poll()
            return proc.returncode, retvals
        finally:
            for fds in self.pipes.values():
                for fd in fds:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            self.pipes = {}
            for fd in self.handles.values():
                try:
                    fd.close()
                except Exception:
                    pass
            self.handles = {}

    def is_available(self):
        try:
            retvals = self.run(["--version"])
            self.available = True
        except OSError:
            self.available = False

        return self.available

    def gen_key(self, name, email, passphrase):
        # FIXME: Allow for selection of alternative keyring
        #        Syntax:
        #        %%pubring mypubring.pgp
        #        %%secring mysecring.pgp

        batchjob = """
            %%echo starting keygen
            Key-Type: RSA
            Key-Length: 4096
            Subkey-Type: RSA
            Subkey-Length: 4096
            Name-Real: %(name)s
            Name-Email: %(email)s
            Expire-Date: 0
            Passphrase: %(passphrase)s
            %%commit
            %%echo done
        """ % {"name": name, "email": email, "passphrase": passphrase}

        returncode, retvals = self.run(["--gen-key"], output=batchjob)
        return returncode, retvals

    def list_keys(self):
        """
        >>> g = GnuPG()
        >>> g.list_keys()[0]
        0
        """
        retvals = self.run(["--list-keys", "--fingerprint"],
                           callbacks={"stdout": self.parse_keylist})
        return retvals[1]["stdout"][0]

    def list_sigs(self):
        retvals = self.run(["--list-sigs", "--fingerprint"],
                           callbacks={"stdout": self.parse_keylist})
        return retvals[1]["stdout"][0]

    def list_secret_keys(self):
        """
        >>> g = GnuPG()
        >>> g.list_secret_keys()[0]
        0
        """
        #
        # Note: The "." parameter that is passed is to work around a bug
        #       in GnuPG < 2.1, where --list-secret-keys does not list
        #       details about key capabilities or expiry for 
        #       --list-secret-keys unless a selector is provided. A dot
        #       is reasonably likely to appear in all PGP keys, as it is
        #       a common component of e-mail addresses (and @ does not
        #       work as a selector for some reason...)
        #
        #       The downside of this workaround is that keys with no e-mail
        #       address or an address like alice@localhost won't be found.
        #       Therefore, this paramter should be removed when GnuPG >= 2.1
        #       becomes commonplace.
        #
        #       (This is a better workaround than doing an additional 
        #       --list-keys and trying to aggregate it though...)
        #
        retvals = self.run(["--list-secret-keys", ".", "--fingerprint"],
                           callbacks={"stdout": self.parse_keylist})
        if retvals[1]["stdout"]:
            return retvals[1]["stdout"][0]
        else:
            return []

    def import_keys(self, key_data=None):
        """
        Imports gpg keys from a file object or string.
        >>> key_data = open("testing/pub.key").read()
        >>> g = GnuPG()
        >>> g.import_keys(key_data)
        {'failed': [], 'updated': [{'details_text': 'unchanged', 'details': 0, 'fingerprint': '08A650B8E2CBC1B02297915DC65626EED13C70DA'}], 'imported': [], 'results': {'sec_dups': 0, 'unchanged': 1, 'num_uids': 0, 'skipped_new_keys': 0, 'no_userids': 0, 'num_signatures': 0, 'num_revoked': 0, 'sec_imported': 0, 'sec_read': 0, 'not_imported': 0, 'count': 1, 'imported_rsa': 0, 'imported': 0, 'num_subkeys': 0}}
        """
        retvals = self.run(["--import"], output=key_data)
        return self.parse_import(retvals[1]["status"])

    class ResultParser:
        """
        Parse the GPG response into EncryptionInfo and SignatureInfo.
        """
        def __init__(rp):
            rp.signature_info = SignatureInfo()
            rp.signature_info["protocol"] = "openpgp"

            rp.encryption_info = EncryptionInfo()
            rp.encryption_info["protocol"] = "openpgp"

            rp.plaintext = ""

        def parse(rp, retvals):
            signature_info = rp.signature_info
            encryption_info = rp.encryption_info
            from mailpile.mailutils import ExtractEmailAndName

            # First pass, set some initial state.
            for data in retvals[1]["status"]:
                keyword = data[0]

                if keyword == "DECRYPTION_FAILED":
                    missing = [x[1] for x in retvals[1]["status"]
                               if x[0] == "NO_SECKEY"]
                    if missing:
                        encryption_info["status"] = "missingkey"
                        encryption_info["missing_keys"] = missing
                    else:
                        encryption_info["status"] = "error"

                elif keyword == "DECRYPTION_OKAY":
                    encryption_info["status"] = "decrypted"
                    rp.plaintext = retvals[1]["stdout"][0]

                elif keyword == "ENC_TO":
                    keylist = encryption_info.get("have_keys", [])
                    if data[0] not in keylist:
                        keylist.append(data[1])
                    encryption_info["have_keys"] = keylist

                elif signature_info["status"] == "none":
                    # Only one of these will ever be emitted per key, use
                    # this to set initial state. We may end up revising
                    # the status depending on more info later.
                    if keyword in ("GOODSIG", "BADSIG"):
                        email, fn = ExtractEmailAndName(
                            " ".join(data[2:]).decode('utf-8'))
                        signature_info["name"] = fn
                        signature_info["email"] = email
                        signature_info["status"] = ((keyword == "GOODSIG")
                                                    and "unverified"
                                                    or "invalid")
                    elif keyword == "ERRSIG":
                        signature_info["status"] = "error"
                        signature_info["keyinfo"] = data[1]
                        signature_info["timestamp"] = int(data[5])

            # Second pass, this may update/mutate the state set above
            for data in retvals[1]["status"]:
                keyword = data[0]

                if keyword == "NO_SECKEY":
                    if "missing_keys" not in encryption_info:
                        encryption_info["missing_keys"] = [data[1]]
                    else:
                        encryption_info["missing_keys"].append(data[1])
                    try:
                        encryption_info["have_keys"].remove(data[1])
                    except (KeyError, ValueError):
                        pass

                elif keyword == "VALIDSIG":
                    # FIXME: Determine trust level, between new, unverified,
                    #        verified, untrusted.
                    signature_info["keyinfo"] = data[1]
                    signature_info["timestamp"] = int(data[3])

                elif keyword in ("EXPKEYSIG", "REVKEYSIG"):
                    email, fn = ExtractEmailAndName(
                        " ".join(data[2:]).decode('utf-8'))
                    signature_info["name"] = fn
                    signature_info["email"] = email
                    signature_info["status"] = ((keyword == "EXPKEYSIG")
                                                and "expired"
                                                or "revoked")

              # FIXME: This appears to be spammy. Is my key borked, or
              #        is GnuPG being stupid?
              #
              # elif keyword == "KEYEXPIRED":  # Ignoring: SIGEXPIRED
              #     signature_info["status"] = "expired"
                elif keyword == "KEYREVOKED":
                    signature_info["status"] = "revoked"
                elif keyword == "NO_PUBKEY":
                    signature_info["status"] = "unknown"

                elif keyword in ["TRUST_ULTIMATE", "TRUST_FULLY"]:
                    if signature_info["status"] == "unverified":
                        signature_info["status"] = "verified"

            return rp

    def decrypt(self, data, passphrase=None):
        """
        Note that this test will fail if you don't replace the recipient with
        one whose key you control.
        >>> g = GnuPG()
        >>> ct = g.encrypt("Hello, World", to=["smari@mailpile.is"])[1]
        >>> g.decrypt(ct)["text"]
        'Hello, World'
        """
        if passphrase:
            self.passphrase = passphrase
        action = ["--decrypt"]
        retvals = self.run(action, callbacks={"stdout": self.default_output},
                           output=data)
        self.passphrase = None

        rp = self.ResultParser().parse(retvals)

        return rp.signature_info, rp.encryption_info, rp.plaintext

    def verify(self, data, signature=None):
        """
        >>> g = GnuPG()
        >>> s = g.sign("Hello, World", _from="smari@mailpile.is",
            clearsign=True)[1]
        >>> g.verify(s)
        """
        params = ["--verify"]
        if signature:
            sig = tempfile.NamedTemporaryFile()
            sig.write(signature)
            sig.flush()
            params.append(sig.name)
            params.append("-")

        ret, retvals = self.run(params,
                                callbacks={"stderr": self.parse_verify},
                                output=data)

        return self.ResultParser().parse([None, retvals]).signature_info

    def encrypt(self, data, tokeys=[], armor=True):
        """
        >>> g = GnuPG()
        >>> g.encrypt("Hello, World", to=["smari@mailpile.is"])[0]
        0
        """
        action = ["--encrypt", "--yes", "--expert", "--trust-model", "always"]
        if armor:
            action.append("--armor")
        for r in tokeys:
            action.append("--recipient")
            action.append(r)
        retvals = self.run(action, callbacks={"stdout": self.default_output},
                           output=data)
        return retvals[0], retvals[1]["stdout"][0]

    def sign(self, data,
             fromkey=None, armor=True, detatch=True, clearsign=False,
             passphrase=None):
        """
        >>> g = GnuPG()
        >>> g.sign("Hello, World", fromkey="smari@mailpile.is")[0]
        0
        """
        if passphrase:
            self.passphrase = passphrase
        if detatch and not clearsign:
            action = ["--detach-sign"]
        elif clearsign:
            action = ["--clearsign"]
        else:
            action = ["--sign"]
        if armor:
            action.append("--armor")
        if fromkey:
            action.append("--local-user")
            action.append(fromkey)

        retvals = self.run(action, callbacks={"stdout": self.default_output},
                           output=data)
        self.passphrase = None
        return retvals[0], retvals[1]["stdout"][0]

    def sign_encrypt(self, data, fromkey=None, tokeys=[], armor=True,
                     detatch=False, clearsign=True):
        retval, signblock = self.sign(data, fromkey=fromkey, armor=armor,
                                      detatch=detatch, clearsign=clearsign)
        if detatch:
            # TODO: Deal with detached signature.
            retval, cryptblock = self.encrypt(data, tokeys=tokeys,
                                              armor=armor)
        else:
            retval, cryptblock = self.encrypt(signblock, tokeys=tokeys,
                                              armor=armor)

        return cryptblock

    def recv_key(self, keyid, keyserver=DEFAULT_SERVER):
        retvals = self.run(['--keyserver', keyserver, '--recv-key', keyid])
        return self.parse_import(retvals[1]["status"])

    def search_key(self, term, keyserver=DEFAULT_SERVER):
        retvals = self.run(['--keyserver', keyserver,
                            '--search-key', self._escape_hex_keyid_term(term)],
                            callbacks={"stdout": lambda x: x})[1]["stdout"][0]
        results = {}
        lines = [x.split(":") for x in retvals.strip().split("\n")]
        curpub = None
        for line in lines:
            if line[0] == "info":
                pass
            elif line[0] == "pub":
                curpub = line[1]
                results[curpub] = {"created": line[4],
                                   "keytype": openpgp_algorithms[int(line[2])],
                                   "keysize": line[3],
                                   "uids": []}
            elif line[0] == "uid":
                email, name, comment = parse_uid(line[1])
                results[curpub]["uids"].append({"name": name,
                                                "email": email,
                                                "comment": comment})
        return results

    def address_to_keys(self, address):
        res = {}
        keys = self.list_keys()
        for key, props in keys.iteritems():
            if any([x["email"] == address for x in props["uids"]]):
                res[key] = props

        return res

    def _escape_hex_keyid_term(self, term):
        """Prepends a 0x to hexadecimal key ids, e.g. D13C70DA is converted to 0xD13C70DA.

            This is necessary because version 1 and 2 of GnuPG show a different behavior here,
            version 1 allows to search without 0x while version 2 requires 0x in front of the key id.
        """
        is_hex_keyid = False
        if len(term) == GPG_KEYID_LENGTH or len(term) == 2*GPG_KEYID_LENGTH:
            hex_digits = set(string.hexdigits)
            is_hex_keyid = all(c in hex_digits for c in term)

        if is_hex_keyid:
            return '0x%s' % term
        else:
            return term




def GetKeys(gnupg, config, people):
    keys = []
    missing = []

    # First, we go to the contact database and get a list of keys.
    for person in set(people):
        if '#' in person:
            keys.append(person.rsplit('#', 1)[1])
        else:
            vcard = config.vcards.get_vcard(person)
            if vcard:
                # FIXME: Rather than get_all, we should give the vcard the
                #        option of providing us with its favorite key.
                lines = [vcl for vcl in vcard.get_all('KEY')
                         if vcl.value.startswith('data:application'
                                                 '/x-pgp-fingerprint,')]
                if len(lines) == 1:
                    keys.append(lines[0].value.split(',', 1)[1])
                else:
                    missing.append(person)
            else:
                missing.append(person)

    # FIXME: This doesn't really feel scalable...
    all_keys = gnupg.list_keys()
    for key in all_keys.values():
        for uid in key["uids"]:
            if uid["email"] in missing:
                missing.remove(uid["email"])
                keys.append(key["fingerprint"])

    # Next, we go make sure all those keys are really in our keychain.
    fprints = [k["fingerprint"] for k in all_keys.values()]
    for key in keys:
        if key not in keys and key not in fprints:
            missing.append(key)

    if missing:
        raise KeyLookupError(_('Keys missing or ambiguous for %s'
                               ) % ', '.join(missing), missing)
    return keys


class OpenPGPMimeSigningWrapper(MimeSigningWrapper):
    CRYPTO_CLASS = GnuPG
    CONTAINER_PARAMS = (('micalg', 'pgp-sha1'),
                        ('protocol', 'application/pgp-signature'))
    SIGNATURE_TYPE = 'application/pgp-signature'
    SIGNATURE_DESC = 'OpenPGP Digital Signature'

    def get_keys(self, who):
        return GetKeys(self.crypto, self.config, who)


class OpenPGPMimeEncryptingWrapper(MimeEncryptingWrapper):
    CRYPTO_CLASS = GnuPG
    CONTAINER_PARAMS = (('protocol', 'application/pgp-encrypted'), )
    ENCRYPTION_TYPE = 'application/pgp-encrypted'
    ENCRYPTION_VERSION = 1

    def get_keys(self, who):
        return GetKeys(self.crypto, self.config, who)


def change_gnupg_home(path):
    global GNUPG_HOMEDIR
    GNUPG_HOMEDIR = path


if __name__ == "__main__":
    g = GnuPG()
    # print g.recv_key("c903bef1")

    # print g.list_secret_keys()
    print g.address_to_keys("smari@immi.is")
    # import doctest
    # t = doctest.testmod()
    # if t.failed == 0:
    #     print "GPG Interface: All %d tests successful" % (t.attempted)
    # else:
    #     print ("GPG Interface: %d out of %d tests failed"
    #            ) % (t.failed, t.attempted)
