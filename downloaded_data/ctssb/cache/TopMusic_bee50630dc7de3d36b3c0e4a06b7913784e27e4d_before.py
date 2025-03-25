from contextlib import contextmanager
import re
import MySQLdb
import pickle

MYSQL_USER = 'DbMysql08'
MYSQL_PASSWORD = 'DbMysql08'
MYSQL_DB_NAME = 'DbMysql08'
MYSQL_HOST = 'mysqlsrv.cs.tau.ac.il'

@contextmanager
def db_cursor(commit_in_the_end):
    '''
    A wrapper that returns a cursor to the DB and makes to to clean everything up in when finished
    '''
    cnx = MySQLdb.connect(user=MYSQL_USER, db=MYSQL_DB_NAME, passwd=MYSQL_PASSWORD, host=MYSQL_HOST)
    cursor = cnx.cursor()
    try:
        yield cursor
    finally:
        if commit_in_the_end:
            cnx.commit()
        cursor.close()
        cnx.close()

def dump_results(file_name):
    query = 'SELECT * FROM Lyrics'
    with db_cursor(False) as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
        rows = [(row[0], row[1]) for row in rows]
        with open(file_name, 'w') as file:
            file.write(pickle.dumps(rows))

def fix_db_lyrics():
    query = 'SELECT * FROM Lyrics'
    update = 'UPDATE Lyrics SET lyrics = "{}" WHERE song_id = {}'
    with db_cursor(False) as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()
        print 'Got ' + str(cursor.rowcount) + ' rows'
    with db_cursor(True) as cursor:
        for row in rows:
            original = row[1]
            fixed_row = re.sub('^Paroles de la chanson .+ par .+\r\n', '', original, re.MULTILINE)
            if fixed_row != original:
                print 'Changing lyrics for song id ' + str(row[0])
                full_line = update.format(row[0], fixed_row)
                cursor.execute(full_line)

if '__main__' == __name__:
    dump_results('backup.pck')
    fix_db_lyrics()
    dump_results('after.pck')