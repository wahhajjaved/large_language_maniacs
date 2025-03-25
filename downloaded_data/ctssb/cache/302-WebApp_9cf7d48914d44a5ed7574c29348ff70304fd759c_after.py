import cherrypy
import socket
import webbrowser
import os
import hashlib
import urllib
import urllib2
import time
import threading
import sqlite3
import json
import datetime
import base64
import sys
from cherrypy.process.plugins import Monitor
reload(sys)
sys.setdefaultencoding('utf-8')

# Returns the internal IP address of the current machine of which the server is to be hosted on 
def getIP():
    try:
        ip = socket.gethostbyname(socket.getfqdn())  # return fully-qualified domain name
    except:
        ip = socket.gethostbyname(socket.gethostname()) 
    return ip


local_ip = getIP() # socket to listen  
ext_ip = '122.62.141.222'
#ip = "127.0.0.1"
port = 10008  # TCP port to listen 
salt = "COMPSYS302-2017"
db_file = 'app.db'
curs = ''
upi = ""
pw = ""


def connectDatabse(db_file):
    try:
        conn = sqlite3.connect(db_file, check_same_thread=False)
        print(sqlite3.version)
    except Error as e:
        print(e)
    # finally: 
    #   conn.close()
    return conn


def createTable(db, create_table_sql):
    try:
        curs = db.cursor() 
        curs.execute(create_table_sql)
        db.commit() 
    except Error as e:
        print(e)

def insertUser(user_details, db, cursor): 
    username = user_details[0]
    location = user_details[1]
    ip = user_details[2]
    port = user_details[3]
    login_time = user_details[4]
    cursor.execute('''SELECT * FROM user_list WHERE username=?''', (username,))
    if (cursor.fetchone() is None):
        cursor.execute('''INSERT INTO user_list (username, location, ip, port, login_time)
        VALUES (?, ?, ?, ?, ?)''', (username, location, ip, port, login_time))
    else:
        cursor.execute('''UPDATE user_list SET location=?, ip=?, port=?, login_time=? WHERE username=?''', (location, ip, port, login_time, username,))
    db.commit()

def initProfile(user_details, db, cursor):
    username = user_details[0]
    cursor.execute('''SELECT * FROM profiles WHERE username=?''', (username,))
    if (cursor.fetchone() is None):
        location = user_details[1]
        if (location == '0'):
            location_str = 'Lab'
        elif (location == '1'): 
            location_str = 'UoA Wifi'
        elif (location == '2'): 
            location_str = 'Outside world'
        else: 
            location_str = '???'
        cursor.execute('''INSERT INTO profiles (username, fullname, position, description, location, picture, encoding, encryption, decryption_key)
        VALUES (?,?,?,?,?,?,?,?,?)''', (username, username, 'student', 'this is my description', location_str, 'picture', 0, 0, 'no key'))
        db.commit() 

class MainApp(object):
    msg = " "
    chat_error = ""
    chat = ""
    conversation = ""

    global db
    db = connectDatabse(db_file)
    global cursor 
    cursor = db.cursor()
    # Make user list db 
    createTable(db, """CREATE TABLE IF NOT EXISTS user_list ( id INTEGER PRIMARY KEY, username TEXT, location INTEGER, ip TEXT, port INTEGER, login_time TEXT);""")
    # Make messages db 
    createTable(db, """CREATE TABLE IF NOT EXISTS messages ( id INTEGER PRIMARY KEY, sender TEXT, recipient TEXT, message TEXT, stamp INTEGER);""")
    # Make profiles db 
    createTable(db, """CREATE TABLE IF NOT EXISTS profiles ( id INTEGER PRIMARY KEY, username TEXT, fullname TEXT, position TEXT, description TEXT, location TEXT, picture TEXT, encoding INTEGER, encryption INTEGER, decryption_key TEXT);""")


    @cherrypy.expose
    def index(self):
        page = open('main.html', 'r').read().format(message=self.msg)
        #page = html.read()
        #logged_in = False
        #page = self.checkLogin(page)
        return page

    @cherrypy.expose
    def home(self):
        try:
            page = open('loggedin.html', 'r').read().format(username=cherrypy.session['username'], user_list=self.getList(), chat_error=self.chat_error, chat_messages=self.chat, conversation=self.conversation)
        except KeyError:
            self.msg = "Session expired, please login again"
            raise cherrypy.HTTPRedirect('/')
        #html.close()
        #page = self.checkLogin(page)
        return page

    @cherrypy.expose
    def signin(self, username=None, password=None): 
        hash_pw = hashlib.sha256(str(password+salt)).hexdigest()
        error = self.report(username, hash_pw)
        print error
        if (int(error) == 0):
            global upi
            global pw
            upi = username
            pw = hash_pw
            cherrypy.session['username'] = username
            cherrypy.session['password'] = hash_pw 
            # self.t = threading.Thread(target=self.report, args=[cherrypy.session['username'], cherrypy.session['password'], False])
            # self.daemon = True
            # self.t.start()
            self.report_thread.start()
            raise cherrypy.HTTPRedirect('/home')
        else:
            print "login failed!2"
            self.msg = "Incorrect credentials, please try again"
            raise cherrypy.HTTPRedirect('/')

       
    @cherrypy.expose
    def report(self, username, hash_pw):
        #time.sleep(30)
        try:
            url = 'http://cs302.pythonanywhere.com/report?username=' + str(username)
            url += '&password=' + str(hash_pw)  + '&location=' + '2' + '&ip=' + ext_ip # TODO: DON'T HARDCODE LOCATION
            url += '&port=' + str(port) + '&enc=0'
            print "logged in as " + username
        except:
            self.msg = 'Login failed!'
            print "login failed!"
            raise cherrypy.HTTPRedirect('/')
        # Getting the error code from the server
        response_message = (urllib2.urlopen(url)).read()
        response = str(response_message)[0]
        # Display response message from the server
        print "Server response: " + str(response_message)
        return response

    @cherrypy.expose
    def reportThread():
        print 'reporting'
        # try:
        url = 'http://cs302.pythonanywhere.com/report?username=' + upi
        url += '&password=' + pw + '&location=' + '2' + '&ip=' + ext_ip # TODO: DON'T HARDCODE LOCATION
        url += '&port=' + str(port) + '&enc=0'
        print url
        response_message = (urllib2.urlopen(url)).read()
        response = str(response_message)[0]
        # Display response message from the server
        print "Server response: " + str(response_message)
        # except:
        #     print "could not report!"
        # Getting the error code from the server
        return
          
    report_thread = Monitor(cherrypy.engine, reportThread, frequency=10)


    def authoriseLogin(self, username, hash_pw):
        return self.report(username, hash_pw)

    def checkLogin(self, page):
        logged_in = True
        try:
            username = cherrypy.session['username']
        except KeyError:
            logged_in = False

        if (logged_in == True):
            html = open('loggedin.html', 'r')
            page = str(html.read())
            html.close()
            page = self.checkLogin(page)

        return page

    @cherrypy.expose
    def signout(self):
        # try:
        url = 'http://cs302.pythonanywhere.com/logoff?username=' + str(cherrypy.session['username']) + '&password=' + str(cherrypy.session['password']) + '&enc=0'
        self.report_thread.stop()
        # except: 
        #     print 'logout failed'
        response = (urllib2.urlopen(url)).read()
        error = str(response)[0]
        if (int(error) == 0):
            self.msg = 'Logout successful!'
            cherrypy.session.clear() # clear user session 
            raise cherrypy.HTTPRedirect('/')

    def getList(self): 
        try: 
            url = 'http://cs302.pythonanywhere.com/getList?username=' + str(cherrypy.session['username']) + '&password=' + str(cherrypy.session['password']) + '&enc=0'
        except: 
            print 'getList failed!'
            raise cherrypy.HTTPRedirect('/')

        response = str((urllib2.urlopen(url)).read())
        error = int(response[0])
        if (error == 0):
            user_list = response
            usernames = []
            page = ''
            user_details = response.replace("0, Online user list returned", "")
            user_details = user_details.split() 
            for i in range (len(user_details)):
                if (',' in user_details[i]):
                    split_details = user_details[i].split(',')
                    if (split_details[0] != cherrypy.session['username']):
                        usernames.append(split_details[0])
                        insertUser(split_details, db, cursor)
                        initProfile(split_details, db, cursor)
            return ", ".join(usernames)

    @cherrypy.expose
    def ping(sender):
        print 'SOMEONE PINGED YOU!!!!!'
        return '0'

    @cherrypy.expose 
    def listAPI(self):
        return '/ping [sender] /listAPI /receiveMessage [sender] [destination] [message] [stamp] /getProfile [profile_username] /receiveFile [sender] [destination] [file] [filename] [content_type] [stamp]'

    @cherrypy.expose
    @cherrypy.tools.json_in()
    def receiveMessage(self):
        # try:
        data = cherrypy.request.json
        print data
        print data['message']
        # if (data['destination'] == cherrypy.session['username']):
        cursor.execute('''INSERT INTO messages (sender, recipient, message, stamp)
        VALUES (?, ?, ?, ?)''', (data['sender'], data['destination'], data['message'], data['stamp']))
        db.commit()
        self.chat_error = 'Someone sent you a message!: ' + data['message']
        print self.chat_error
        self.chat += '<div style="text-align:left">'
        self.chat += data['sender'] + ': ' + data['message'] + '<br></div>'
        return '0'
        # else:
        # except:
        # return '5'
        # print 'could not receive message!'
        #     self.chat_error = 'Could not receive message!'
        #     print self.chat_error
        #     return '0'
        #print self.chat_error

    @cherrypy.expose 
    def sendMessage(self, recipient, message):
        print recipient
        current_time = time.time()
        curs = db.execute("""SELECT id, username, location, ip, port, login_time from user_list""")
        for row in curs: 
            if (recipient == row[1]):
                recipient_ip = row[3]
                recipient_port = row[4]

                post_data = {"sender": cherrypy.session['username'], "destination": recipient, "message": message, "stamp": int(current_time)}
                #post_data = post_data.encode('utf8')
                post_data = json.dumps(post_data)
                url = 'http://' + str(recipient_ip) + ":" + str(recipient_port) + '/receiveMessage?'
                print url
                req = urllib2.Request(url, post_data, {'Content-Type': 'application/json'})

                response = urllib2.urlopen(req).read()
                print response
                # print str(response)
                if (str(response[0]) == '0'):
                    self.chat = 'Message sent!'
                    cursor.execute('''INSERT INTO messages (sender, recipient, message, stamp)
                    VALUES (?, ?, ?, ?)''', (cherrypy.session['username'], recipient, message, current_time))
                    db.commit()
                else:
                    error = 'Message failed to send!'
                    print error 
                    self.chat = error

                break
                # else:
                #     print 'could not send message!'
        cherrypy.HTTPRedirect('/home')

    @cherrypy.expose
    def viewConversation(self, username):
        curs = db.execute("""SELECT id, sender, recipient, message, stamp from messages""")
        for row in curs: 
            if (username == row[1]):
                self.conversation += '<div style="text-align:left">'
                self.conversation += '[' + datetime.datetime.fromtimestamp(row[4]).strftime('%c') + '] '
                self.conversation += row[1] + ': ' + row[3] + '<br></div>'
            elif (username == row[2]):
                self.conversation += '<div style="text-align:right">'
                self.conversation += datetime.datetime.fromtimestamp(row[4]).strftime('%c') + ' '
                self.conversation += 'You: ' + row[3] + '<br></div>'
        raise cherrypy.HTTPRedirect('/home')

    @cherrypy.expose
    @cherrypy.tools.json_in()
    def receiveFile(self):
        print 'Someone sent you a file! '
        data = cherrypy.request.json
        sender = data['sender']
        file = data['file']
        filename = data['filename']
        print filename
        stamp = data['stamp']

        with open(filename, "wb") as fh:
            fh.write(file.decode('base64'))

        return '0'

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def sendFile(self, send_file, recipient):
        stamp = int(time.time())
        enc_file = base64.b64encode(send_file.file.read())
        #filetype = magic.Magic(mime=True)
        #filetype.from_file(file)
        post_data = {"sender": cherrypy.session['username'], "destination": recipient, "file": enc_file, "stamp": stamp, "filename": send_file.filename, "content_type": str(send_file.content_type)}
        print send_file.content_type
        post_data = json.dumps(post_data)

        curs = db.execute("""SELECT id, username, location, ip, port, login_time from user_list""")
        for row in curs: 
            if (recipient == row[1]):
                recipient_ip = row[3]
                recipient_port = row[4]
                url = 'http://' + str(recipient_ip) + ":" + str(recipient_port) + '/receiveFile?'
                print url
                req = urllib2.Request(url, post_data, {'Content-Type': 'application/json'})

                response = urllib2.urlopen(req).read()
                print response

    @cherrypy.expose
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def getProfile(self, user=None):
        if user is None:
            data = cherrypy.request.json
            username = data['profile_username']
        else:
            username = user

        print 'getProfile requesting ' + username
        # In order to output as dict, need dto utilise row_factory
        db_row = sqlite3.connect(db_file, check_same_thread=False)
        db_row.row_factory = sqlite3.Row
        c = db_row.cursor()
        c.execute('''SELECT * FROM profiles WHERE username=?''', (username,))
        profile_data = c.fetchone()
        #print dict(profile_data)
        return dict(profile_data)

    @cherrypy.expose
    def viewProfile(self, user=None):
        try:
            if user is None:
                username = cherrypy.session['username']
            else:
                username = user

            profile_data = self.getProfile(user=username)
            page = open('profile.html', 'r').read().format(profile_data=str(profile_data))
            return page
        except:
            self.msg = 'Session expired, please login again'
            raise cherrypy.HTTPRedirect('/')

    @cherrypy.expose
    def editProfile(self, parameter, changes, user=None):
        print parameter
        print changes
        if user is None:
            username = cherrypy.session['username']
        else:
            username = user

        if (parameter == 'fullname'):
            cursor.execute('''UPDATE profiles SET fullname=? WHERE username=?''', (changes, username,))
        elif (parameter == 'position'):
            cursor.execute('''UPDATE profiles SET position=? WHERE username=?''', (changes, username,))
        elif (parameter == 'desc'):
            cursor.execute('''UPDATE profiles SET description=? WHERE username=?''', (changes, username,))
        elif (parameter == 'location'):
            cursor.execute('''UPDATE profiles SET location=? WHERE username=?''', (changes, username,))
        else:
            print "invalid parameter!"

        db.commit()
        raise cherrypy.HTTPRedirect('/viewProfile')


    #webbrowser.open_new('http://%s:%d/login' % (local_ip, port))

def runMainApp():
    conf = {
         '/': {
             'tools.sessions.on': True,
             'tools.staticdir.root': os.path.abspath(os.getcwd())
         },
         '/generator': {
             'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
             'tools.response_headers.on': True,
             'tools.response_headers.headers': [('Content-Type', 'text/plain')],
         },
         '/static': {
             'tools.staticdir.on': True,
             'tools.staticdir.dir': './static'
         }
    }

    cherrypy.tree.mount(MainApp(), "/", conf)

    cherrypy.config.update({'server.socket_host': '0.0.0.0',
                        'server.socket_port': port,
                        #'engine.autoreload.on': True,
                        'tools.encode.on': True,
                        'tools.encode.encoding': 'utf-8'
                        })

    # cherrypy.config["tools.enconde.on"] = True
    # cherrypy.config["tools.encode.encoding"] = "utf-8"


    cherrypy.engine.start() # start webserver

    cherrypy.engine.block() # stop doing anything else 
    #cherrypy.engine.stop() # terminate; stop the channel of the bus 
    #cherrypy.server.unsubscribe() # disable built-in HTTP server 

runMainApp()