# Explanation
# This is a very simplified server class handling requests and returning a
# corresponding responses. It uses a simple connection to execute SQL queries
# to a database. It currently is able to process user registration and user
# login.
# 
# Tasks (maybe read the "What you are not required to do" section first...)
# - Explain why is this a bad implementation in terms of design, error handling
#   and security, you can also do this by adding comments in the code
# - Rewrite the server to handle different databases as well as the possibility 
#   to specify a different response output format at server object creation
# - Write a working test that ensures the server works as expected and is 
#   "fault tolerant" to invalid input
#
# What you are not required to do - unless you have too much time ;)
# - You don't have to really implement a different database handler, response,
#   security strategies, just make sure to explain them well
# - You do not have to write beautiful HTML (I know there is no doctype, 
#   encoding, etc.)
# - You don't have to implement an actual server running the code
# - You don't have to make the database connection work

"""
Comments:
The initial implementation doesn't support multiple database connections, or other databases types as PostgresSQL.
It's insecure the way that handles the request, is not using a strong password policy and anyone could create a new user
and do everything with the connections.
It's insecure since is not doing any validation about the sentences / queries that may be allowed or not.
It doesn't support transactions to ensure atomicity, consistency, isolation and durability. At least a rollback in case
of error.
It's not possible to end a connection or shut down the server.
It doesn't handle properly the Exceptions.
Error messages are not defined in a special module or global variables.
HTML Code must be defined in templates files and not inside of server module.
"""

from database import MySQLConnection
from utils import render

DEFAULT_HOST = u'http://localhost'
DEFAULT_USERNAME = u'default'
DEFAULT_PASSWORD = u'default123'
DEFAULT_DB = u'default'


class Server(object):
    
    def __init__(self):
        self.__db_connections = {u'default': MySQLConnection(DEFAULT_HOST, DEFAULT_USERNAME,
                                                             DEFAULT_PASSWORD, DEFAULT_DB)}

    def add_connection(self, user, pwd, host=DEFAULT_HOST, db_name=u'default'):
        assert db_name in self.__db_connections, u'Database %s already exists' % db_name
        self.__db_connections[db_name] = MySQLConnection(host, user, pwd, db_name)

    def handle_request(self, parameters):
        # the method is part of 
        print u"Handling request..."
        action = parameters.get(u'action')

        # This is a very insecure to authenticate or register new users.
        # If is not possible at least to use system authentication, we must force a strong password policy.
        # Also, regarding security, change the default SQL, and other DB ports, that comes by default with
        # the installation to keep hackers from port scanning to the server.
        username = parameters.get(u'username')
        password = parameters.get(u'password')
        db = parameters.get(u'db', u'default')
        fmt = parameters.get(u'format', u'html')

        # must process the request and return the response
        if action == u'login':
            msg = self.login(username, password, db)
        elif action == u'register':
            msg = self.register_user(username, password, db)

        # Not sure if this was required or not.
        # elif action == u'execute':
        #     sql = parameters.get(u'query')
        #     msg = self.execute_sql(sql, db, commit=True)

        return render(msg, fmt)

    def execute_sql(self, sql, db=u'default', commit=True):
        result = self.__db_connections[db].execute(sql, commit)
        return result

    def register_user(self, username, pwd, db):
        print u"Registering user %s in the db: %s" % (username, db)
        sql = u"INSERT INTO users ('%s', '%s'" % (username, pwd)
        # if the user already exists we get an error here
        # no need for checking user existence
        self.execute_sql(sql, db, True)
        print u"Registration OK"
        return u"Thank you for registering %s" % username

    def login(self, username, pwd, db):
        print u"Login user %s" % username
        sql = u"SELECT password FROM users WHERE username = '" + username + u"';"
        result_set = self.execute_sql(sql, db, True)
        if len(result_set) == 1 and result_set[0] == pwd:
            print u"Login OK"
            return u"Thank you for logging in %s" % username
        else:
            print u"Cannot Login."
            return u"ERROR!!!"

    def shut_down(self):
        errors = []
        print u"Shutting down server..."
        for db in self.__db_connections:
            try:
                self.close_db(db)
            except Exception as error:
                errors.append(error)
        if errors:
            print u"Something went wrong:\n%s" % u'\n'.join([e.message for e in errors])
        else:
            print u"OK"

    def close_db(self, db_name):
        db = self.__db_connections[db_name]
        try:
            print u"Closing db connection for database %s..." % db_name
            db.close()
        except Exception as error:
            print u"Cannot close DB connection for database %s...\nError: %s" % (db_name, error.message)
        finally:
            print u"Closed db connection for database %s..." % db_name
