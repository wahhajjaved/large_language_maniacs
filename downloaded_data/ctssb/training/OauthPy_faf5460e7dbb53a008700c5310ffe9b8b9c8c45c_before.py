# oauthpy is implementation of oauth
# usage :
# oauth = OAuth(consumer_secret, consumer_key)
# oauth.request_token() # for request token
# oauth.do_request() # if you want to implement other request just use this one and wrap arround
import time
from base64 import b64encode
from urllib.parse import quote, parse_qs
from urllib.request import Request, urlopen
from hmac import new as hmac
from hashlib import sha1

class OAuthPy():
    
    # constructor init parameter is consumer secret and consumer key
    def __init__(self, consumer_secret, consumer_key):
        self.consumer_secret = consumer_secret
        self.consumer_key = consumer_key

    # parameter
    # url_request : api url for request ex https://api.twitter.com/oauth/request_token
    # oauth_token : access token for accessing api this step should be after request granting from user to application
    # oauth_token_secret : access token will concate with consumer secret for generating signing key
    # oauth_callback : required if request oauth token and oauth token sercret, this callback should be same with application callback on api provider
    # request_method can be POST/GET
    # use_headers_auth False/True, depend on provider restriction
    # if use_headers_auth True headers will send with Authorization payload
    # additional_params should be pair key and val as dictionary and will put on payload request
    def do_request(self, url_request='', request_method='GET',
        oauth_token='', oauth_token_secret='',
        oauth_callback='', use_headers_auth=False, additional_params={}):

        oauth_nonce = str(time.time()).replace('.', '')
        oauth_timestamp = str(int(time.time()))

        params = {'oauth_consumer_key':self.consumer_key,
            'oauth_nonce':oauth_nonce,
            'oauth_signature_method':'HMAC-SHA1',
            'oauth_timestamp':oauth_timestamp,
            'oauth_version':'1.0'}

        # if validate callback
        # and request token and token secret
        if(oauth_callback != ''):
            params['oauth_callback'] = oauth_callback

        # if request with token
        if(oauth_token != ''):
            params['oauth_token'] = oauth_token

        # check if additional_params length != 0
        # append additional param to params
        if(len(additional_params)):
            for k in additional_params:
                params[k] = additional_params[k]

        # create signing key
        # generate oauth_signature
        # key structure oauth standard is [POST/GET]&url_request&parameter_in_alphabetical_order
        params_str = '&'.join(['%s=%s' % (self.urlquote(k), self.urlquote(params[k])) for k in sorted(params)])
        message = '&'.join([request_method, self.urlquote(url_request), self.urlquote(params_str)])

        # Create a HMAC-SHA1 signature of the message.
        # Concat consumer secret with oauth token secret if token secret available
        # if token secret not available it's mean request token and token secret
        key = '%s&%s' % (self.consumer_secret, oauth_token_secret) # Note compulsory "&".
        signature = hmac(key.encode('UTF-8'), message.encode('UTF-8'), sha1)
        digest_base64 = b64encode(signature.digest()).decode('UTF-8')
        params["oauth_signature"] = digest_base64

        # this is parameter should be pash into url_request
        params_str = '&'.join(['%s=%s' % (self.urlquote(k), self.urlquote(params[k])) for k in sorted(params)])

        # if use_headers_auth
        headers_payload = {}
        if use_headers_auth:
            headers_str_payload = 'OAuth ' + ', '.join(['%s="%s"' % (self.urlquote(k), self.urlquote(params[k])) for k in sorted(params)])
            headers_payload['Authorization'] = headers_str_payload

            # if POST method add urlencoded
            if request_method == 'POST':
                headers_payload['Content-Type'] = 'application/x-www-form-urlencoded'
                
            headers_payload['User-Agent'] = 'HTTP Client'

        # request to provider with
        # return result
        try:
            req = Request(url_request, data=params_str.encode('ISO-8859-1') ,headers=headers_payload)
            res = urlopen(req)
            return res.readall()
        except Exception as e:
            return None

    # simplify request token
    # get request token
    # depend on do_request method
    # if request success will return
    # {oauth_token:'', oauth_token_secret:'', oauth_callback_confirmed:''}
    # else return None
    def request_token(self, url_request, oauth_callback, request_method='GET', use_headers_auth=False):
        res = oauth.do_request(url_request=url_request,
            request_method=request_method,
            oauth_callback=oauth_callback,
            use_headers_auth=use_headers_auth)

        # mapping to dictionary
        # return result as dictioanary
        if res:
            res = parse_qs(res.decode('UTF-8'))
            data_out = {}
            for k in res:
                data_out[k] = res[k][0]

            return data_out
            

        # default return is None
        return None

    # urlquote
    # quote url as percent quote
    def urlquote(self, text):
        return quote(text, '~')

# testing outh request token
oauth = OAuthPy('PUT_YOUR_CONSUMER_SECRET', 'PUT_YOUR_CONSUMER_KEY')
res = oauth.request_token(url_request='https://api.twitter.com/oauth/request_token',
    request_method='POST',
    oauth_callback='http://127.0.0.1:8888/p/authenticate/twitter',
    use_headers_auth=True)
print(res)