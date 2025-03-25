#!/usr/bin/env python
# coding: utf-8

import json, urllib

def request(url, func, *args):
    req = json.dumps({"method":func, "params":args, "id":1})
    result = urllib.urlopen("http://localhost:8888/jsonrpc", req).read()
    try:
        response = json.loads(result)
    except:
        return "error: %s" % result
    else:
        return response.get("result", response.get("error"))

url = "http://localhost:8888/jsonrpc"
print "echo:", request(url, "echo", "foo bar")
print "sort:", request(url, "sort", ["foo", "bar"])
print "count:", request(url, "count", ["foo", "bar"])
print "geoip_lookup:", request(url, "geoip_lookup", "google.com")
