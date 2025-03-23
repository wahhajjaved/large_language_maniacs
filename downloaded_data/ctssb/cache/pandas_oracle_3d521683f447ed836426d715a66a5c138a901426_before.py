#! /usr/local/bin python3

import cx_Oracle
import getpass
import yaml
import pandas as pd

def open_connection(config_file: str):
    """Open a new connection to database
       based on yaml file.
       config_file: name of parameter file
    """ 
    ##open configuration file */
    with open(config_file, 'r') as ymlfile:
        cfg = yaml.load(ymlfile)
    ##loading variable usernamem, host
    user = cfg['database']['username']
    host = cfg['database']['host']
    ##verify if sysdba conn or not
    if 'sysdba' in cfg['database']:
            sysdba = cfg['database']['sysdba']
    else:
            sysdba = 'n'
    ##loading password or ask
    if 'password' in cfg['database']:
            pwd = cfg['database']['password']
    else:
            pwd = getpass.getpass('Database password: ')
    if sysdba == 'n':
            return(cx_Oracle.connect("{}/{}@{}".format(user, pwd, host)))
    elif sysdba == 'y':
            return(cx_Oracle.connect("{}/{}@{}".format(user, pwd, host), mode=cx_Oracle.SYSDBA))
    else :
            return(cx_Oracle.connect("{}/{}@{}".format(user, pwd, host)))

def query_to_df(query: str, conn_db: cx_Oracle.Connection, arraysize: int):
    """Do the query and transform the result to a dataframe
       parameters:
       *) query: str with a query statetement
       *) conn_db : a connection object from cx_oracle or open_connection
       *) arraysize : arrayfetch size
    """ 
    cur = conn_db.cursor()
    ##setting arraysize
    if arraysize :
       cur.arraysize = arraysize
    ##execute query 
    cur.execute(query)
    ##fetch all row
    r = cur.fetchall()
    cols = [n[0] for n in cur.description]
    cur.close()
    data = pd.DataFrame.from_records(r, columns=cols)
    return(data)

def execute(statement: str, conn_db: cx_Oracle.Connection):
    """execute a statement
       parameters:
       *) statement: str with a statetement
       *) conn_db : a connection object from cx_oracle or open_connection
    """
    cur = conn_db.cursor()
    cur.execute(statement)
    conn_db.commit()
    cur.close()

def insert_multiple(table_name: str, df: pd.DataFrame, conn_db: cx_Oracle.Connection, batch_size=5000):
    """multiple insert
       parameters:
       *) table_name : table_name to load
       *) df : dataframe to load
       *) conn_db : a connection object from cx_oracle or open_connection
       *) batch_size : batch size of commit
    """
    cur = conn_db.cursor()
    sql = "INSERT INTO {0} ({1}) VALUES (:{2})".format(table_name,
                                                      ', '.join(df.columns),
                                                      ', :'.join(list(map(str,range(1, len(df.columns)+1)))))
    i = 0
    while ((i * batch_size) < len(df)):
        rows = []
        min = i*batch_size
        max = ((i+1)*batch_size)-1
        for x in df.ix[min:max,:].values:
            rows.append([None if pd.isnull(y) else y for y in x])
        cur.executemany(sql, rows)
        con.commit()
        i = i + 1
    cur.close()

def open_connection(conn_db: cx_Oracle.Connection):
    """Close the connection
       parameters:
       *) conn_db : connection object 
    """
    conn_db.close()
