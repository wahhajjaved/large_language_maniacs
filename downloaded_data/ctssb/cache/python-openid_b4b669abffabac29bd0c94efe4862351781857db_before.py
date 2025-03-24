import string
import time
import urllib
import urlparse

from openid import cryptutil
from openid import kvform
from openid import oidutil
from openid.association import Association
from openid.consumer.parse import parseLinkAttrs
from openid.dh import DiffieHellman

from openid.consumer.interface import \
     SUCCESS, FAILURE, SETUP_NEEDED, PARSE_ERROR, HTTP_FAILURE, \
     OpenIDAuthRequest

def getOpenIDParameters(query):
    params = {}
    for k, v in query.iteritems():
        if k.startswith('openid.'):
            params[k] = v
    return params

class OpenIDConsumerImpl(object):
    NONCE_LEN = 8
    NONCE_CHRS = string.letters + string.digits
    TOKEN_LIFETIME = 60 * 2 # two minutes

    def __init__(self, store, immediate, fetcher):
        self.store = store
        self.fetcher = fetcher

        if immediate:
            self.mode = 'checkid_immediate'
        else:
            self.mode = 'checkid_setup'

        self.immediate = immediate

    def beginAuth(self, user_url):
        status, info = self._findIdentityInfo(user_url)
        if status != SUCCESS:
            return status, info

        consumer_id, server_id, server_url = info
        nonce = cryptutil.randomString(self.NONCE_LEN, self.NONCE_CHRS)

        token = self._genToken(nonce, consumer_id, server_url)
        return SUCCESS, OpenIDAuthRequest(token, server_id, server_url, nonce)

    def constructRedirect(self, auth_req, return_to, trust_root):
        redir_args = {
            'openid.identity': auth_req.server_id,
            'openid.return_to': return_to,
            'openid.trust_root': trust_root,
            'openid.mode': self.mode,
            }

        assoc = self.getAssociation(auth_req.server_url, replace=1)
        if assoc is not None:
            redir_args['openid.assoc_handle'] = assoc.handle

        self.store.storeNonce(auth_req.nonce)
        return str(oidutil.appendArgs(auth_req.server_url, redir_args))

    def completeAuth(self, token, query):
        mode = query.get('openid.mode', '')
        if mode == 'cancel':
            return SUCCESS, None
        elif mode == 'error':
            error = query.get('openid.error')
            if error is not None:
                pass # XXX: log this
            return FAILURE, None
        elif mode == 'id_res':
            return self._doIdRes(token, query)
        else:
            return FAILURE, None

    def _doIdRes(self, token, query):
        ret = self._splitToken(token)
        if ret is None:
            return FAILURE, None

        nonce, consumer_id, server_url = ret

        return_to = query.get('openid.return_to')
        server_id = query.get('openid.identity')
        assoc_handle = query.get('openid.assoc_handle')

        if return_to is None or server_id is None or assoc_handle is None:
            return FAILURE, consumer_id

        user_setup_url = query.get('openid.user_setup_url')
        if user_setup_url is not None:
            return SETUP_NEEDED, user_setup_url

        assoc = self.store.getAssociation(server_url)

        if (assoc is None or assoc.handle != assoc_handle or
            assoc.expiresIn <= 0):
            # It's not an association we know about.  Dumb mode is our
            # only possible path for recovery.
            check_args = getOpenIDParameters(query)
            check_args['openid.mode'] = 'check_authentication'
            post_data = urllib.urlencode(check_args)

            return self._checkAuth(
                nonce, consumer_id, post_data, server_url)

        # Check the signature
        sig = query.get('openid.sig')
        signed = query.get('openid.signed')
        if sig is None or signed is None:
            return FAILURE, consumer_id

        args = getOpenIDParameters(query)
        signed_list = signed.split(',')
        v_sig = assoc.signDict(signed_list, args)

        if v_sig != sig:
            return FAILURE, consumer_id

        if not self.store.useNonce(nonce):
            return FAILURE, consumer_id

        return SUCCESS, consumer_id

    def _checkAuth(self, nonce, consumer_id, post_data, server_url):
        ret = self.fetcher.post(server_url, post_data)
        if ret is None:
            return FAILURE, consumer_id

        results = oidutil.kvToDict(ret[1])
        is_valid = results.get('is_valid', 'false')

        if is_valid == 'true':
            invalidate_handle = results.get('invalidate_handle')
            if invalidate_handle is not None:
                self.store.removeAssociation(server_url, invalidate_handle)

            if not self.store.useNonce(nonce):
                return FAILURE, consumer_id

            return SUCCESS, consumer_id

        error = results.get('error')
        if error is not None:
            return FAILURE, consumer_id

        return FAILURE, consumer_id

    def getAssociation(self, server_url, replace=0):
        if self.store.isDumb():
            return None
        
        assoc = self.store.getAssociation(server_url)

        if assoc is None or \
               (replace and assoc.expiresIn < self.TOKEN_LIFETIME):
            assoc = self._associate(server_url)

        return assoc

    def _genToken(self, nonce, consumer_id, server_url):
        timestamp = str(int(time.time()))
        joined = '\x00'.join([timestamp, nonce, consumer_id, server_url])
        sig = cryptutil.hmacSha1(self.store.getAuthKey(), joined)

        return oidutil.toBase64('%s%s' % (sig, joined))

    def _splitToken(self, token):
        token = oidutil.fromBase64(token)
        if len(token) < 20:
            return None

        sig, joined = token[:20], token[20:]
        if cryptutil.hmacSha1(self.store.getAuthKey(), joined) != sig:
            return None

        split = joined.split('\x00')
        if len(split) != 4:
            return None

        try:
            ts = int(split[0])
        except ValueError:
            return None

        if ts + self.TOKEN_LIFETIME < time.time():
            return None

        return tuple(split[1:])

    def _quoteMinimal(self, s):
        # Do not escape anything that is already 7-bit safe, so we do the
        # minimal transform on the identity URL
        res = []
        for c in s:
            if c >= u'\x80':
                for b in c.encode('utf8'):
                    res.append('%%%02X' % ord(b))
            else:
                res.append(c)
        return str(''.join(res))

    def _normalizeUrl(self, url):
        assert isinstance(url, (str, unicode)), type(url)

        url = url.strip()
        parsed = urlparse.urlparse(url)

        if parsed[0] == '' or parsed[1] == '':
            url = 'http://' + url
            parsed = urlparse.urlparse(url)

        if isinstance(url, unicode):
            authority = parsed[1].encode('idna')
        else:
            authority = str(parsed[1])

        tail = map(self._quoteMinimal, parsed[2:])
        if tail[0] == '':
            tail[0] = '/'
        encoded = (str(parsed[0]), authority) + tuple(tail)
        url = urlparse.urlunparse(encoded)
        assert type(url) is str

        return url

    def _findIdentityInfo(self, identity_url):
        url = self._normalizeUrl(identity_url)
        ret = self.fetcher.get(url)
        if ret is None:
            return HTTP_FAILURE, None

        http_code, consumer_id, data = ret

        server = None
        delegate = None
        link_attrs = parseLinkAttrs(data)
        for attrs in link_attrs:
            rel = attrs.get('rel')
            if rel == 'openid.server' and server is None:
                href = attrs.get('href')
                if href is not None:
                    server = href

            if rel == 'openid.delegate' and delegate is None:
                href = attrs.get('href')
                if href is not None:
                    delegate = href

        if server is None:
            return PARSE_ERROR, None

        if delegate is not None:
            server_id = delegate
        else:
            server_id = consumer_id

        urls = (consumer_id, server_id, server)
        return SUCCESS, tuple(map(self._normalizeUrl, urls))

    def _associate(self, server_url):
        dh = DiffieHellman()
        cpub = cryptutil.longToBase64(dh.createKeyExchange())

        args = {
            'openid.mode': 'associate',
            'openid.assoc_type':'HMAC-SHA1',
            'openid.session_type':'DH-SHA1',
            'openid.dh_modulus': cryptutil.longToBase64(dh.p),
            'openid.dh_gen': cryptutil.longToBase64(dh.g),
            'openid.dh_consumer_public': cpub,
            }

        body = urllib.urlencode(args)

        ret = self.fetcher.post(server_url, body)
        if ret is None:
            return None

        http_code, url, data = ret
        results = kvform.kvToDict(data)

        try:
            assoc_type = results['assoc_type']
            if assoc_type != 'HMAC-SHA1':
                return None

            assoc_handle = results['assoc_handle']
            expires_in = int(results.get('expires_in', '0'))

            session_type = results.get('session_type')
            if session_type is None:
                secret = oidutil.fromBase64(results['mac_key'])
            else:
                if session_type != 'DH-SHA1':
                    return None

                spub = cryptutil.base64ToLong(results['dh_server_public'])
                enc_mac_key = oidutil.fromBase64(results['enc_mac_key'])
                secret = dh.xorSecret(spub, enc_mac_key)

            assoc = Association.fromExpiresIn(
                expires_in, assoc_handle, secret, assoc_type)
            self.store.storeAssociation(server_url, assoc)

            return assoc

        except KeyError:
            return None
