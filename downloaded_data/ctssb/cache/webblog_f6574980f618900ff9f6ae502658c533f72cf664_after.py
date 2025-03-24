from utils.connect_db import *
from utils.constants import *
from utils.time_format import *
from utils.crossdomain import *
import json
from . import routes


# return all info of an user
# http://127.0.0.1:8080/api/users/view_profile?myid=1&otherid=2
@routes.route('/api/users/view_profile', methods=['GET'])
@crossdomain(origin='*')
def view_user_profile():
    if request.method == 'GET':
        try:
            myid = request.args.get('myid')
            otherid = request.args.get('otherid')
            exe_sql = "SELECT * FROM users WHERE uid = %s"
            res = conn.execute(exe_sql, otherid)
            row = res.fetchone()
            ret = {}
            if row:
                ret[STATUS] = SUCCESS
                u_info = {
                    "uid"  : row["uid"],
                    "email": row["email"],
                    "birth": date_to_timestamp(row["birth"]),
                    "sex"  : row["sex"],
                    "name" : row["name"]
                }
                exe_sql = "SELECT count(*) AS count FROM follows WHERE source = %s AND destination = %s"
                res = conn.execute(exe_sql, (myid, otherid))
                if res.fetchone()["count"] == 1:
                    u_info["isFollow"] = TRUE
                else:
                    u_info["isFollow"] = FALSE
                exe_sql = "SELECT count(*) AS count FROM follows WHERE destination = %s;"
                res = conn.execute(exe_sql, otherid)
                u_info["follows"] = int(res.fetchone()["count"])
                ret[RESULT] = u_info
            else:
                ret[STATUS] = FAIL
                fail_info = dict()
                fail_info[CODE] = "0"
                fail_info[MSG] = "User None Exist"
                ret[RESULT] = fail_info
            print ret
            return json.dumps(ret)
        except Exception, e:
            print e
            return default_error_msg(e.message)


# return topics subscribed by an user
# http://127.0.0.1:8080/api/users/subscribes?id=2
@routes.route('/api/users/subscribes', methods=['GET'])
def user_subscribes():
    if request.method == 'GET':
        try:
            id = request.args.get('id')
            exe_sql = "SELECT topic FROM subscribes WHERE uid = %s"
            res = conn.execute(exe_sql, id)
            rows = res.fetchall()
            ret = dict()
            if rows:
                ret[STATUS] = SUCCESS
                topics = []
                for row in rows:
                    topics.append(row["topic"])
                ret[RESULT] = topics
            else:
                ret[STATUS] = FAIL
                fail_info = dict()
                fail_info[CODE] = "0"
                fail_info[MSG] = "None topics"
                ret[RESULT] = fail_info
            print ret
            return json.dumps(ret)
        except Exception, e:
            print e
            return default_error_msg(e.message)


# return topics subscribed by an user
# http://127.0.0.1:8080/api/users/follow?sour=2&dest=1&isFollow=1
@routes.route('/api/users/follow', methods=['GET'])
@crossdomain(origin='*')
def user_follows():
    if request.method == 'GET':
        try:
            source = request.args.get('sour')
            destination = request.args.get('dest')
            isFollow = request.args.get('isFollow')
            ret = {}
            ret[STATUS] = SUCCESS
            ret[RESULT] = NULL
            if isFollow == "1":
                exe_sql = "SELECT * FROM follows WHERE source = %s AND destination = %s"
                res = conn.execute(exe_sql, (source, destination))
                row = res.fetchall()
                print row
                # No record before:
                if row:
                    pass
                else:
                    exe_sql = "INSERT INTO follows(source, destination) VALUES(%s, %s)"
                    # INSERT statement does not return rows. It'll close automatically.
                    conn.execute(exe_sql, (source, destination))
            elif isFollow == "0":
                exe_sql = "DELETE FROM follows WHERE source = %s and destination = %s"
                # INSERT statement does not return rows. It'll close automatically.
                conn.execute(exe_sql, (source, destination))
            else:
                raise Exception("isFollow should be either 1 or 0!")
            print ret
            return json.dumps(ret)
        except Exception, e:
            print e
            return default_error_msg(e.message)
