import sqlite3

class SubscriberDB():

    @staticmethod
    def getAllClients(resource='1'):
        conn = sqlite3.connect('clients.db')
        c = conn.cursor()
        c.execute("Select * from Subscriber where resourceid='"+resource+"' order by id")
        result = c.fetchall()
        c.close()
        conn.close()
        return result

    @staticmethod
    def insertClient(uri, method, accept, resource=1):
        conn = sqlite3.connect('clients.db')
        c = conn.cursor()
        c.execute("insert into Subscriber (uri, method, accept, resourceid) values ('"+uri+"', '"+method+"', '"+accept+"', '"+resource+"')")
        result = c.lastrowid
        conn.commit()
        c.close()
        conn.close()
        return result

    @staticmethod
    def updateClient(uri, method, accept, clientid):
        conn = sqlite3.connect('clients.db')
        c = conn.cursor()
        c.execute("Update Subscriber set uri='"+uri+"', method='"+method+"', accept='"+accept+"' where id='"+clientid+"'")
        result = c.lastrowid
        conn.commit()
        c.close()
        conn.close()
        return result

    @staticmethod
    def deleteQuery(clientid):
        conn = sqlite3.connect('clients.db')
        c = conn.cursor()
        queryresult = c.execute("Delete from Subscriber where id='"+clientid+"'")
        conn.commit()
        c.close()
        conn.close()
        return queryresult

    @staticmethod
    def getClient(clientid):
        conn = sqlite3.connect('clients.db')
        c = conn.cursor()
        c.execute("Select * from Subscriber where id='"+clientid+"'")
        result = c.fetchall()[0]
        c.close()
        conn.close()
        return result
