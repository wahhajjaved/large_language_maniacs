'''
Created on May 8, 2010

@author: Nicklas Boerjesson
'''

from qal.dal.dal_types import DB_MYSQL, DB_POSTGRESQL, DB_ORACLE, DB_DB2, DB_SQLSERVER, string_to_db_type
from qal.dal.dal_conversions import parse_description, python_type_to_SQL_type

class Database_Abstraction_Layer(object):
    """This class abstracts the different peculiarities of the different database backends with regards to connection details"""
    
    # Events
    
    on_connect = None
    
    # Properties
    
    connected = False
    
    db_connection = None

    db_type = None
    db_server = ''
    db_databasename = ''
    db_username = ''
    db_password = ''
    db_instance = ''
    db_driver = None
    db_autocommit = True
    
    
    field_names = None
    field_types = None
    
    def read_ini_settings(self, _ini_parser):
        """Read setting from the settings.Parser object"""
        self.db_type        = string_to_db_type(_ini_parser.Parser.get("database", "type"))
        self.db_server      = _ini_parser.Parser.get("database", "server")   
        self.db_databasename= _ini_parser.Parser.get("database", "database_name")   
        self.db_username    = _ini_parser.Parser.get("database", "username")
        self.db_password    = _ini_parser.Parser.get("database", "password")
        self.DB_Port        = _ini_parser.Parser.get("database", "port")
        self.autocommit     = _ini_parser.get("database", "autocommit", True)        
        if _ini_parser.Parser.has_option("database", "instance"):
            self.db_instance    = _ini_parser.Parser.get("database", "instance")
            
            
    def read_resource_settings(self, _resource):
        if _resource.type.upper() != 'RDBMS':
            raise Exception("DAL.read_resource_settings error: Wrong resource type - " + _resource.type)
        self.db_type =         string_to_db_type(_resource.data.get("db_type"))
        self.db_server =       _resource.data.get("server")
        self.db_databasename = _resource.data.get("database")
        self.db_instance =     _resource.data.get("instance")
        self.db_username =     _resource.data.get("username")
        self.db_password =     _resource.data.get("password")
        self.DB_Port =         _resource.data.get("DB_Port")
        self.autocommit =      _resource.data.get("autocommit")
        
                       
    def connect_to_db(self):
        '''Connects to the database'''
        if (self.db_type == DB_MYSQL):
            import pymysql
            Conn = pymysql.connect (host = self.db_server,
                            db = self.db_databasename,
                            user = self.db_username,
                            passwd = self.db_password,
                            )
            

        elif (self.db_type == DB_POSTGRESQL):
            import postgresql.driver as pg_driver 
            if self.DB_Port == None or self.DB_Port == "":
                _port = 5432
            else:
                _port = self.DB_Port
            Conn = pg_driver.connect(host = self.db_server, 
                                                database =  self.db_databasename, 
                                                user = self.db_username, 
                                                password = self.db_password,
                                                port = _port)
                            
        elif (self.db_type == DB_SQLSERVER):
            import pyodbc
            #TODO: Investigate if there is any more adapting needed, platform.release() can also be used. 
            import platform
            if platform.system().lower() == 'linux':
                connstr = "DRIVER=FreeTDS;SERVER=" + self.db_server + ";DATABASE=" + self.db_databasename +";TDS VERSION=8.0;UID=" + self.db_username + ";PWD=" + self.db_password + ";PORT="+self.DB_Port + ";Trusted_Connection=no"
            elif platform.system().lower() == 'windows':
                connstr = "Driver={SQL Server};Server=" + self.db_server + ";DATABASE=" + self.db_databasename +";UID=" + self.db_username + ";PWD=" + self.db_password + ";PORT="+self.DB_Port + ";Trusted_Connection=no"
            else:
                raise Exception("connect_to_db: ODBC connections on " + platform.system() + " not supported yet.")

            Conn = pyodbc.connect(connstr, autocommit=self.autocommit);      

        elif (self.db_type == DB_DB2):
            import pyodbc
            import platform
            if platform.system().lower() == 'linux':
                drivername = "DB2"
            elif platform.system().lower() == 'windows':
                drivername = "{IBM DATA SERVER DRIVER for ODBC - C:/PROGRA~1/IBM}"
            else:
                raise Exception("connect_to_db: DB2 connections on " + platform.system() + " not supported yet.")
            
            # DSN-less?{IBM DB2 ODBC DRIVER} ?? http://www.webmasterworld.com/forum88/4434.htm
            connstr =  "Driver=" + drivername + ";Database=" + self.db_databasename +";hostname=" + self.db_server + ";port="+self.DB_Port + ";protocol=TCPIP; uid=" + self.db_username + "; pwd=" + self.db_password
            #connstr = "DSN=" + self.db_server + ";UID=" + self.db_username + ";PWD=" + self.db_password 
            Conn = pyodbc.connect(connstr, autocommit=self.autocommit)
        
        # cx_Oracle in python 3.X not checked yet.
        elif (self.db_type == DB_ORACLE):
            import cx_Oracle
            connstr = self.db_username + '/' +  self.db_password + '@' + self.db_server + ':' + self.DB_Port + '/' + self.db_instance
            print(connstr)
            Conn = cx_Oracle.connect(connstr) 
            Conn.autocommit=self.autocommit
                  
        else:
            raise Exception("connect_to_db: Invalid database type.")              
      
        
        self.db_connection = Conn
        
        if self.on_connect:
            self.on_connect() 
        self.connected = True
            
        return Conn 
    
    
    
    def __init__(self, _settings = None, _resource = None):
        '''
        Init
          
        '''  
        if _settings != None:      
            self.settings = _settings
            self.read_ini_settings(_settings)
            self.db_driver = self.connect_to_db()
            
        if _resource != None:
            self.resource = _resource
            self.read_resource_settings(_resource)
            self.db_driver = self.connect_to_db()   


    def select(self, params):
        pass
    
    def execute(self, _sql):
        """Execute the SQL statement, expect no dataset"""
        if self.db_type == DB_POSTGRESQL:
            self.db_connection.execute(_sql)
        else:
            cur = self.db_connection.cursor()
            cur.execute(_sql)
            
    def _make_positioned_params(self, _input):

            _arg_idx = 1
            _output =  _input
            
            # Simplest possible scan, prepared to handle the types differently.                        
            for _curr_idx in range(0, len(_input)):
                _chunk = _input[_curr_idx:_curr_idx +2]
                
                if _chunk == "%s":
                    _output = _output.replace(_chunk,"$" + str(_arg_idx), 1)           
                    _arg_idx+=1            
                elif _chunk == "%d":                    
                    _output = _output.replace(_chunk,"$" + str(_arg_idx), 1)           
                    _arg_idx+=1            

            return _output    
                
           
    def executemany(self, _sql, _values):
        """Execute the SQL statements , expect no dataset"""
        if self.db_type == DB_POSTGRESQL:
            # Change parameter type into Postgres positional ones, like  $1, $2 and so on.
            # TODO: Correctly handle other datatypes than string.
            _sql = self._make_positioned_params(_sql)

            _prepared = self.db_connection.prepare(_sql)
            print(_sql)
            for _row in _values:
                _prepared(*_row)
        else:
            cur = self.db_connection.cursor()
            cur.executemany(_sql, _values)
    

    def query(self, _sql):
        """Execute the SQL statement, get a dataset"""
        # py-postgres doesn't use the DB-API, as it doesn't work well-
        if self.db_type == DB_POSTGRESQL:
            _ps = self.db_connection.prepare(_sql)
            _res = _ps()
            if _ps.column_names != None:
                self.field_names = _ps.column_names 
                self.field_types = []                
                for _curr_type in _ps.column_types:
                    self.field_types.append(python_type_to_SQL_type(_curr_type))

        else:
            cur = self.db_connection.cursor()
            cur.execute(_sql)
            
            self.field_names, self.field_types = parse_description(cur.description, self.db_type);
            
            _res = cur.fetchall()
            
        # Untuple. TODO: This might need to be optimised, perhaps by working with the same array. 
        _results = [] 
        for _row in _res:
            _results.append(list(_row))
        
        return _results
   
    def close(self):
        """Close the database connection"""
        self.db_connection.close()
            
    def commit(self):
        """Commit the transaction"""
        self.db_connection.commit()

    def rollback(self):
        """Rollback the transaction"""
        self.db_connection.rollback()
    