
# Controller is used by many Handlers, possibly concurrently
# So make sure it does NOT modify internal state while handling a request

import hashlib
import random
from functools import wraps
import types
from concurrent.futures import ThreadPoolExecutor
import passlib.hash  # For passwords
import json
from itertools import chain

from sparrow import *

from model import *
from util import *
from util import sim


# Helper stuff (decorators, metaclasses)
# ======================================

# Decorator stuff
# ---------------

def require_user_level(level):
    def handler_decorator(method):
        @wraps(method)
        async def handler_wrapper(self, req):
            if req.conn.user is None:
                raise Authentication("not_logged_in", "You need to be logged in", "conn.user is None, can't use type " + method.__name__)
            else:
                # TODO check level
                await method(self, req)
        return handler_wrapper
    return handler_decorator


def handle_ws_type(typ):
    def decorator(method):
        method.__handle_type__ = typ
        return method
    return decorator


# Metaclasses
# -----------

class MetaController(type):
    def __new__(self, name, bases, dct):
        dct["wshandlers"] = {}
        # Detects functions marked with handle_ws_type
        for (n,f) in dct.items():
            if hasattr(f, "__handle_type__"):
                dct["wshandlers"][f.__handle_type__] = f
        return type.__new__(self, name, bases, dct)


# Actual little helper functions and constants
# --------------------------------------------

def check_for_type(req: "Request", typ: str):
    if not req.metadata["for"]["what"] == typ:
        raise Error("wrong_object_type", "Wrong object type in for.what")

# Dictionary which contains frequently used operation codes
op_codes = {'gt': '>', 'lt': '<', 'eq': '=','le': '<=', 'ge': '>=', 'in': 'IN'}

# Dictionary to limit possible fields on which to filter in 'where' clause
value_props_per_type = {}
for cls in Value, HourValue, DayValue, MonthValue, YearValue:
    value_props = {p.name: p for p in cls._props if p.json}
    value_props_per_type[cls.__name__] = (cls, value_props)

sensor_props = {p.name: p for p in Sensor._props if p.json}

# The Controller
# ==============

class Controller(metaclass=MetaController):
    executor = ThreadPoolExecutor(4)

    # General methods
    # ---------------

    def __init__(self, logger, model):
        self.logger = logger
        self.model = model

        self.sessions = {}
        # Session --> User.key

    async def handle_request(self, req):
        # See metaclass
        # Kind of a switch class too, but I'd like to keep it flat
        if req.metadata["type"] in Controller.wshandlers:
            await Controller.wshandlers[req.metadata["type"]](self, req)
        else:
            self.logger.error("No handler for %s in Controller"%req.metadata["type"])

    async def get_user(self, session):
        if session in self.sessions:
            return await User.find_by_key(self.sessions[session], self.db)
        else:
            return None

    async def conn_close(self, conn):
        pass  # TODO?

    # Will you look at that. Beautiful replacement for a switch statement if I say
    # so myself.
    class switch_what(switch):
        """Base class for switch selecting on "what"."""
        def select(self, req):
            return req.metadata["what"]

        def default(self, req):
            raise Error("unknown_object_type", "Object type '{}' not recognized".format(req.metadata["what"]))


    # Helper methods
    # --------------

    @property
    def db(self):
        """Shortcut (simple getter)"""
        return self.model.db

    @blocking  # executed on Controller.executor
    def create_password(self, p):
        return passlib.hash.bcrypt.encrypt(p, rounds=13)

    @blocking
    def verify_password(self, hashed, p):
        return passlib.hash.bcrypt.verify(p, hashed)


    # Websocket handlers
    # ------------------

    # TODO take queries out of function and add the to the model so they can be printed

    @handle_ws_type("signup")
    async def handle_signup(self, req):
        c = await User.get(User.email == Unsafe(req.data["email"])).count(self.db)
        if c >= 1:
            self.logger.error("Email %s already taken"%req.data["email"])
            await req.answer({"status": "failure", "reason": "email_taken"})
        else:
            # Manual initialisation because password isn't in json
            hash = await self.create_password(req.data["password"])
            w = Wall(is_user=True)
            await w.insert(self.db)
            u = User(email=req.data["email"], password=hash,
                     first_name=req.data["first_name"], last_name=req.data["last_name"],
                     admin=False,
                     wall=w.key,)
            await u.insert(self.db)
            await req.answer({
                "status": "success",
                "UID": u.UID
            })


    @handle_ws_type("login")
    async def handle_login(self, req):
        res = await User.get(User.email == Unsafe(req.data["email"])).exec(self.db)
        if res.count() == 0:
            await req.answer({"status": "failure", "reason": "email_unknown"})
            return
        u = res.single()

        if (await self.verify_password(u.password, req.data["password"])):
            session = hashlib.md5(bytes(str(random.random())[2:] + "WoordPopNoordzee", "utf8")).hexdigest()
            self.sessions[session] = u.key
            req.conn.user = u
            req.conn.session = session
            await req.answer({"status": "success", "session": session, "user": u.json_repr()})
        else:
            await req.answer({"status": "failure", "reason": "wrong_password"})


    @handle_ws_type("logout")
    @require_user_level(1)
    async def handle_logout(self, req):
        self.sessions.pop(req.conn.session)
        req.conn.session = None
        req.conn.user = None


    @handle_ws_type("add")
    @require_user_level(1)
    class handle_add(switch_what):
        @case("Location")
        async def location(self, req):
            if req.data["user_UID"] == req.conn.user.UID:
                l = Location(json_dict=req.data)
                await l.insert(self.db)
                await req.answer(l.json_repr())
            else:
                raise Authentication("wrong", "You gave a wrong user_UID.")

        @case("Sensor")
        async def sensor(self, req):
            l = await Location.find_by_key(req.data["location_LID"], self.db)
            await l.check_auth(req)
            if req.data["user_UID"] == req.conn.user.UID:
                s = Sensor(json_dict=req.data)
                await s.insert(self.db)
                await req.answer(s.json_repr())
            else:
                raise Authentication("wrong", "You gave a wrong user_UID.")

        @case("Value")
        async def value(self, req):
            check_for_type(req, "Sensor")
            v = Value(sensor=req.metadata["for"]["SID"], time=req.data[0], value=req.data[1])
            # await v.check_auth(req, db=self.db)
            # TODO fix check_auth and error occurs when values with same sid,time keys are in the database
            await v.insert(self.db)
            await req.answer(v.json_repr())

        @case("Tag")
        async def tag(self, req):
            check_for_type(req, "Sensor")
            t = Tag(sensor=req.metadata["for"]["SID"], text=req.data["text"])
            # TODO fix error check_auth
            # await t.check_auth(req, db=self.db)
            await t.insert(self.db)
            await req.answer(t.json_repr())

        @case("Group")
        async def group(self, req):
            g = Group(json_dict=req.data)
            await g.check_auth(req, db=self.db)
            await g.insert(self.db)
            await req.answer(g.json_repr())

        @case("Wall")
        async def wall(self, req):
            w = Wall(is_user=req.data["is_user"])
            await w.check_auth(req, db=self.db)
            await w.insert(self.db)
            await req.answer(w.json_repr())

        @case("Status")
        async def status(self, req):
            s = Status(json_dict=req.data)
            await s.check_auth(req, db=self.db)
            await s.insert(self.db)
            await req.answer(s.json_repr())

        @case("Comment")
        async def comment(self, req):
            c = Comment(json_dict=req.data)
            await c.check_auth(req, db=self.db)
            await c.insert(self.db)
            await req.answer(c.json_repr())

        @case("Like")
        async def like(self, req):
            l = Like(json_dict=req.data)
            await l.check_auth(req, db=self.db)
            await l.insert(self.db)
            await req.answer(l.json_repr())

        @case("Friendship")
        async def friendship(self, req):
            if req.data["user1_UID"] > req.data["user2_UID"]:
                req.data["user1_UID"], req.data["user2_UID"] = req.data["user2_UID"], req.data["user1_UID"]
            if await Friendship.contains(req.data["user1_UID"],req.data["user2_UID"],self.db):
                await req.answer({"status":"failure", "reason":"Friendship already exists."})
            else:
                f = Friendship(json_dict=req.data)
                await f.check_auth(req, db=self.db)
                await f.insert(self.db)
                await req.answer(f.json_repr())

        @case("Membership")
        async def membership(self, req):
            m = Membership(json_dict=req.data)
            await m.check_auth(req, db=self.db)
            await m.insert(self.db)
            await req.answer(m.json_repr())

    @handle_ws_type("get")
    @require_user_level(1)
    class handle_get(switch_what):
        @case("Location")
        async def location(self, req):
            l = await Location.find_by_key(req.data["LID"], self.db)
            await l.check_auth(req)
            await req.answer(l.json_repr())

        @case("Sensor")
        async def sensor(self, req):
            s = await Sensor.find_by_key(req.data["SID"], self.db)
            await s.check_auth(req)
            await req.answer(s.json_repr())

        @case("User")
        async def user(self, req):
            u = await User.find_by_key(req.data["UID"], self.db)
            # Just a superficial get so no need to check for authorisation
            # await u.check_auth(req)
            await req.answer(u.json_repr())


    # TODO currently permissions are a bit weird: handle_get will trust the Sensor/Value's is_authorized,
    # but handle_get_all will trust the User's is_authorized...
    @handle_ws_type("get_all")
    @require_user_level(1)
    class handle_get_all(switch_what):
        @case("Location")
        async def location(self, req):
            check_for_type(req, "User")
            u = await User.find_by_key(req.metadata["for"]["UID"], self.db)
            await u.check_auth(req)
            locations = await Location.get(Location.user == u.key).all(self.db)
            await req.answer([l.json_repr() for l in locations])

        @case("Like")
        async def like(self, req):
            check_for_type(req, "Status")
            s = await Status.find_by_key(req.metadata["for"]["SID"], self.db)
            await s.check_auth(req)
            likes = await Like.get(Like.status == s.key).all(self.db)
            await req.answer([l.json_repr() for l in likes])

        @case("Sensor")
        class sensor(switch):
            select = lambda self, req: req.metadata["for"]["what"] if "for" in req.metadata else "Admin"

            @case("User")
            async def for_user(self, req):
                u = await User.find_by_key(req.metadata["for"]["UID"], self.db)
                await u.check_auth(req)
                sensors = await Sensor.get(Sensor.user == u.key).all(self.db)
                await req.answer([s.json_repr() for s in sensors])

            @case("Location")
            async def for_location(self, req):
                l = await Location.find_by_key(req.metadata["for"]["LID"], self.db)
                await l.check_auth(req)
                sensors = await Sensor.get(Sensor.location == l.key).all(self.db)
                await req.answer([s.json_repr() for s in sensors])

            @case("Admin")
            async def for_admin(self, req):
                # Verify if the connection is a real admin for security reasonsx
                u = await User.find_by_key(req.conn.user.UID, self.db)
                if u.admin:
                    sensors = await Sensor.get().all(self.db)
                    await req.answer([s.json_repr() for s in sensors])
                else:
                    await req.answer({"status":"failure", "reason":"You are not an admin."})

        @case("Value", "HourValue", "DayValue", "MonthValue", "YearValue")
        async def value(self, req):
            what_type = req.metadata["what"]
            value_cls, value_props = value_props_per_type[what_type]
            check_for_type(req, "Sensor")
            s = await Sensor.find_by_key(req.metadata["for"]["SID"], self.db)
            await s.check_auth(req)
            if "where" in req.metadata:
                clauses = []
                for c in req.metadata["where"]:
                    clauses.append(Where(value_props[c["field"]].name, op_codes[c["op"]], Unsafe(c["value"])))
                clauses.append(Where(value_props["sensor_SID"].name, "=", s.key))
                values = await value_cls.get(*clauses).all(self.db)
            else:
                values = await value_cls.get(value_cls.sensor == s.key).all(self.db)
            await req.answer([v.json_repr() for v in values])

        @case("User")
        async def user(self, req):
            check_for_type(req, "User")
            u = await User.find_by_key(req.metadata["for"]["UID"], self.db)
            await u.check_auth(req)
            users = await User.get(User.key != u.key).all(self.db)
            await req.answer([u.json_repr() for u in users])

        @case("Group")
        async def group(self, req):
            if "for" in req.metadata:
                check_for_type(req, "User")
                u = await User.find_by_key(req.metadata["for"]["UID"], self.db)
                await u.check_auth(req)
                groups = await Group.raw("SELECT * FROM table_Group WHERE table_Group.gid IN (SELECT table_Membership.group_gid FROM table_Membership WHERE table_Membership.user_uid = {0})".format(req.metadata["for"]["UID"])).all(self.db)
                await req.answer([g.json_repr() for g in groups])
            else:
                groups = await Group.get(Group.public == True).all(self.db)
                await req.answer([g.json_repr() for g in groups])

        @case("Friendship")
        async def friendship(self, req):
            check_for_type(req, "User")
            u = await User.find_by_key(req.metadata["for"]["UID"], self.db)
            await u.check_auth(req)
            friendships = await Friendship.get(Or(Friendship.user1 == u.key, Friendship.user2 == u.key)).all(self.db)
            await req.answer([f.json_repr() for f in friendships])

        @case("Membership")
        async def membership(self, req):
            check_for_type(req, "Group")
            g = await Group.find_by_key(req.metadata["for"]["GID"], self.db)
            await g.check_auth(req)
            memberships = await Membership.get(Membership.group == g.key).all(self.db)
            await req.answer([m.json_repr() for m in memberships])

        @case("Tag")
        async def tag(self, req):
            if "for" in req.metadata:
                check_for_type(req, "Sensor")
                s = await Sensor.find_by_key(req.metadata["for"]["SID"], self.db)
                await s.check_auth(req)
                tags = await Tag.get(Tag.sensor == s.key).all(self.db)
                await req.answer([t.json_repr() for t in tags])
            else:
                tags = await Tag.raw("SELECT * FROM table_Tag WHERE table_Tag.text IN (SELECT MIN(table_Tag.text) FROM table_tag GROUP BY table_Tag.text)").all(self.db)
                await req.answer([t.json_repr() for t in tags])

        @case("Status")
        async def status(self, req):
            check_for_type(req, "Wall")
            w = await Wall.find_by_key(req.metadata["for"]["WID"], self.db)
            await w.check_auth(req)
            status = await Status.get(Status.wall == w.key).all(self.db)
            await req.answer([s.json_repr() for s in status])

        @case("Comment")
        async def comment(self, req):
            check_for_type(req, "Status")
            s = await Comment.find_by_key(req.metadata["for"]["SID"], self.db)
            await s.check_auth(req)
            comments = await Comment.get(Comment.status == s.key).all(self.db)
            await req.answer([c.json_repr() for c in comments])


    @handle_ws_type("edit")
    @require_user_level(1)
    class handle_edit(switch_what):
        @case("User")
        async def user(self, req):
            u = await User.find_by_key(req.data["UID"], self.db)
            await u.check_auth(req)
            u.edit_from_json(req.data)
            await u.update(self.db)
            await req.answer(u.json_repr())

        @case("Location")
        async def location(self, req):
            l = await Location.find_by_key(req.data["LID"], self.db)
            await l.check_auth(req)
            l.edit_from_json(req.data)
            await l.update(self.db)
            await req.answer(l.json_repr())

        @case("Sensor")
        async def sensor(self, req):
            s = await Sensor.find_by_key(req.data["SID"], self.db)
            await s.check_auth(req)
            s.edit_from_json(req.data)
            await s.update(self.db)
            await req.answer(s.json_repr())

        @case("Like")
        async def like(self, req):
            l = await Like.find_by_key((req.data["status_SID"], req.data["user_UID"]), self.db)
            await l.check_auth(req)
            l.edit_from_json(req.data)
            await l.update(self.db)
            await req.answer(l.json_repr())

    # TODO handle FOREIGN KEY constraints (CASCADE?)
    @handle_ws_type("delete")
    @require_user_level(1)
    class handle_delete(switch_what):
        @case("Location")
        async def location(self, req):
            l = await Location.find_by_key(req.data["LID"], self.db)
            await l.check_auth(req)
            await l.delete(self.db)
            await req.answer({"status": "success"})

        @case("Status")
        async def status(self, req):
            s = await Status.find_by_key(req.data["SID"], self.db)
            await s.check_auth(req)
            await s.delete(self.db)
            await req.answer({"status": "success"})

        @case("Comment")
        async def comment(self, req):
            c = await Comment.find_by_key((req.data["CID"],req.data["SID"]), self.db)
            await c.check_auth(req)
            await c.delete(self.db)
            await req.answer({"status": "success"})

        @case("Membership")
        async def membership(self, req):
            m = await Membership.find_by_key((req.data["user_UID"],req.data["group_GID"]), self.db)
            await m.check_auth(req)
            await m.delete(self.db)
            await req.answer({"status": "success"})

        @case("Sensor")
        async def sensor(self, req):
            s = await Sensor.find_by_key(req.data["SID"], self.db)
            await s.check_auth(req)
            await s.delete(self.db)
            await req.answer({"status": "success"})

        @case("Friendship")
        async def friendship(self, req):
            f = await Friendship.find_by_key((req.data["user1_UID"],req.data["user2_UID"]), self.db)
            await f.check_auth(req)
            await f.delete(self.db)
            await req.answer({"status": "success"})

        @case("Tag")
        async def tag(self, req):
            if 'for' in req.metadata:
                check_for_type(req, "Sensor")
                s = await Sensor.find_by_key(req.metadata["for"]["SID"], self.db)
                await s.check_auth(req)
                tags = await Tag.get(Tag.sensor == s.key).all(self.db)
                for t in tags: await t.delete(self.db)
                await req.answer({"status": "succes"})
            else:
                t = await Tag.find_by_key((req.data["sensor_SID"], req.data["text"]), self.db)
                # await t.check_auth(req, self.db)
                await t.delete(self.db)
                await req.answer({"status": "succes"})


    @handle_ws_type("get_values")
    @require_user_level(1)
    async def handle_get_values(self, req):
        base_wheres = []
        valueType = req.metadata["timespan"]["valueType"]
        group_by = req.metadata.get("group_by", [])
        #if valueType == "Value" and len(group_by) != 0:
        #    raise Error("no_group_by_permitted", "Grouping is not permitted when searching for raw values")

        value_cls, value_props = value_props_per_type[valueType]

        for c in req.metadata.get("where", []):
            val = c["value"] if not isinstance(c["value"], list) else tuple(c["value"])
            w = Where(sensor_props[c["field"]].name, op_codes[c["op"]], Unsafe(val))
            base_wheres.append(w)

        if not req.conn.user.admin:
            base_wheres.append(Sensor.user == req.conn.user.key)

        # Tactic: divide all graphs further and further
        # Each list is a limitation aka Where object that filters sensors
        wheres_list = [base_wheres]  # To start, one graph with the basic wheres
        for g in group_by:
            extra_wheres = []
            if g["what"] == "Sensor":
                for SID in g["IDs"]:
                    extra_wheres.append(Sensor.SID == SID)
            elif g["what"] == "Type":
               for t in g["IDs"]:
                   if t not in Sensor.type_type.options:
                       raise Error("unknown_type", "Unknown type")
                   extra_wheres.append(Sensor.type == t)
            elif g["what"] == "Tag":
                for t in g["IDs"]:
                    # Not really a where but anyway
                    extra_wheres.append(RawSql("SELECT * FROM table_sensor WHERE table_sensor.SID IN (SELECT table_tag.sensor_SID FROM table_Tag WHERE text = %(tagtext)s)", {"tagtext": t}))
            elif g["what"] == "Location":
                for LID in g["IDs"]:
                    extra_wheres.append(Sensor.location == LID)
            else:
                raise Error("no_such_group_by", "There is no such group_by 'what' attribute")

            new_where_list = []
            for wheres in wheres_list:
                for w in extra_wheres:
                    new_where_list.append([w]+wheres)
            wheres_list = new_where_list

        graphs = []
        for wheres in wheres_list:
            print("wheres = ", ", ".join([str(w) for w in wheres]))
            sensors = await Sensor.get(*wheres).all(self.db)
            IDs = [s.SID for s in sensors]
            # TODO give more metadata to Graph
            graph = Graph([], IDs, req.metadata["timespan"], value_cls)
            await graph.fill(self.db)
            graphs.append(graph)

        await req.answer([g.json_repr() for g in graphs])


# Some day, this will be in Model
class Graph:
    def __init__(self, grouped_by, sensors, timespan, cls):
        self.grouped_by = grouped_by
        # TODO wtf @grouped_by
        self.sensors = tuple(sensors)
        self.timespan = timespan
        self.cls = cls
        self.values = []

    async def fill(self, db):
        req = RawSql("SELECT time, avg(value) AS value FROM {s.cls._table_name} WHERE sensor_SID IN {sensors} GROUP BY time HAVING time >= %(start)s AND time < %(end)s ORDER BY time".format(s=self, sensors="("+str(self.sensors[0])+")" if len(self.sensors) == 1 else str(self.sensors)), {
            "start": self.timespan["start"],
            "end": self.timespan["end"],
        })
        result = await req.exec(db)
        self.values = result.raw_all()

    def json_repr(self):
        return {"grouped_by": self.grouped_by,
                "sensors": self.sensors,
                "values": [list(v) for v in self.values]}
