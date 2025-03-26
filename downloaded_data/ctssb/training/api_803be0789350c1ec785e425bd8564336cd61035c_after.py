import urllib
import json

WIT_ACCESS_TOKEN='GE3WFS7X5FGREBMX7WA46XIHMO2ES7WC'
WIT_API_HOST = 'https://api.wit.ai'
WIT_API_VERSION = '20160516'

class WitParser:
    def parse(self, message):
        req = urllib.request.Request(url=WIT_API_HOST + '/message?' + urllib.parse.urlencode({'q': message}), headers={
            'authorization': 'Bearer ' + WIT_ACCESS_TOKEN,
            'accept': 'application/vnd.wit.' + WIT_API_VERSION + '+json'
        })
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
