import header as h
from header import users_key
from handlers.hash import valid_pw, make_pw_hash


class User(h.db.Model):
    username = h.db.StringProperty(required=True)
    password = h.db.StringProperty(required=True)
    email = h.db.StringProperty(required=True)
    created = h.db.DateTimeProperty(auto_now_add=True)
    last_modified = h.db.DateTimeProperty(auto_now=True)

    @classmethod
    def by_id(cls, uid):
        return User.get_by_id(uid, parent=users_key())

    @classmethod
    def by_name(cls, name):
        u = User.all().filter('name =', name).get()
        return u

    @classmethod
    def login(cls, name, password):
        u = cls.by_name(name)
        if u and valid_pw(name, password, u.password):
            return u

    @classmethod
    def register(cls, name, password, email):
        pw_hash = make_pw_hash(name, password)
        return User(
                parent=users_key(),
                name=name,
                password=pw_hash,
                email=email
        )
