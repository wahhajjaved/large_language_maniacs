import re
import json
import time
import hashlib
import sqlite3
import collections
import sys
from datetime import datetime

class URLHandler():
    def __init__(self, mucbot):
        self.mucbot = mucbot
        self.salt1 = "happy happy hippo"
        self.salt2 = "sad pandas are sad"
        self.whitelist = ["1b49f24e1acf03ef8ad1b803593227ca1b94868c29d41a8ab22fbc7b6d94342c"]
        self.url_history = collections.deque(maxlen=10)

    def hash(self, plaintext):
        return hashlib.sha256(self.salt1 + str(plaintext) + self.salt2).hexdigest()

    def get_or_set(self, url_plaintext, nick, time):
        url = self.hash(url_plaintext)
        db = sqlite3.connect('db.sq3')
        ret = None

        if url in self.whitelist:
            return None

        c = db.execute('SELECT * FROM urls WHERE url = ? ORDER BY time DESC LIMIT 1', [url])
        row = c.fetchone()
        if row:
             ret = row
             # Sqlite does not now about cool stuff like INSERT OR UPDATE
             db.execute('UPDATE urls SET count=count+1 WHERE url = ?', [url])
        else:
             db.execute('INSERT INTO urls (nick, url, time) VALUES (?,?,?)', (nick, url, time) )

        db.commit()
        db.close()

        return ret

    def handle(self, msg):
        if msg['body'][:4] == "!url":
            self.mucbot.send_message(mto=msg['from'].bare,
                mbody="URL History:\n%s" % ("\n".join(self.url_history) ),
                    mtype='groupchat')

        if msg['body'][:11] == "URL History" or msg['body'][:1] == "!" or msg['mucnick'] == "Annarchy":
            return

        urls = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', msg['body'])
        if not urls:
            return

        for url in urls:
            self.url_history.append(url)

            urldata = self.get_or_set(url, msg['mucnick'], int(time.time()))

            if urldata:
                tdiff = datetime.now() - datetime.fromtimestamp(urldata[2])

                if urldata[0].lower() == msg['mucnick'].lower():
                    pass  #ignore if the user is the same
#                    self.mucbot.send_message(mto=msg['from'].bare,
#                        mbody="%s: Thats what you said (%s) ago" % (msg['mucnick'], tdiff),
#                        mtype='groupchat')
                else:
                    self.mucbot.send_message(mto=msg['from'].bare,
                        mbody="%s: Oooooooooold! %s was first (%s)" % (msg['mucnick'], urldata[0], tdiff),
                        mtype='groupchat')


# Importer
def do_import(path):
    db = sqlite3.connect('db.sq3')
    with open(path) as f:
        urls = [json.loads(line) for line in f]
        for url in urls:
            db.execute('INSERT INTO urls (nick, url, time) VALUES (?,?,?)', (url['nick'], url['url'], url['timestamp']) )

    db.commit()
    db.close()

# Test and mock
class MUCBotMock():
    def send_message(self, mto, mbody, mtype):
        print "MUCBotMock:", mto, mbody, mtype

class FromMock():
    def __init__(self, _from):
        self.bare = _from

def do_test():
    x = URLHandler(MUCBotMock())
    msg = {"from" : FromMock("channel@example.com"), "mucnick" : "kallsse", "body" : "hello http://events.ccc.de/congress/22014"}
    x.handle(msg)

    msg = {"from" : FromMock("channel@example.com"), "mucnick" : "kallsse", "body" : "!url"}
    x.handle(msg)

if __name__ == "__main__":
    if len(sys.argv) == 2:
        do_import(sys.argv[1])
    else:
        do_test()
