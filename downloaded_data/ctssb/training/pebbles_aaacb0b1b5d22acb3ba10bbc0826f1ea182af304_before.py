from flask.ext.bcrypt import generate_password_hash, check_password_hash
from sqlalchemy.ext.hybrid import hybrid_property
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
import uuid
import json
import datetime
from pouta_blueprints.server import db, app

MAX_PASSWORD_LENGTH = 100
MAX_EMAIL_LENGTH = 128
MAX_NAME_LENGTH = 128


def load_column(column):
    try:
        value = json.loads(column)
    except:
        value = {}
    return value


def create_first_user(email, password):
    user = User(email, password, is_admin=True)
    user.is_active = True
    worker = User('worker@pouta_blueprints', app.config['SECRET_KEY'], is_admin=True)
    worker.is_active = True
    db.session.add(user)
    db.session.add(worker)
    db.session.commit()
    return user


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.String(32), primary_key=True)
    email = db.Column(db.String(MAX_EMAIL_LENGTH), unique=True)
    password = db.Column(db.String(MAX_PASSWORD_LENGTH))
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)

    def __init__(self, email, password=None, is_admin=False):
        self.id = uuid.uuid4().hex
        self.email = email.lower()
        self.is_admin = is_admin
        if password:
            self.set_password(password)
            self.is_active = True
        else:
            self.set_password(uuid.uuid4().hex)

    def delete(self):
        self.email = self.email + datetime.datetime.utcnow().strftime("-%s")
        self.is_deleted = True
        self.is_active = True

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        if self.is_deleted:
            return None
        return check_password_hash(self.password, password)

    def generate_auth_token(self, expires_in=3600):
        s = Serializer(app.config['SECRET_KEY'], expires_in=expires_in)
        return s.dumps({'id': self.id}).decode('utf-8')

    @staticmethod
    def verify_auth_token(token):
        s = Serializer(app.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except:
            return None
        user = User.query.get(data['id'])
        if user and user.is_deleted:
            return None
        return user

    def __repr__(self):
        return '<User %r>' % self.email


class Keypair(db.Model):
    __tablename__ = 'keypairs'

    id = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id'))
    public_key = db.Column(db.String(450))

    def __init__(self):
        self.id = uuid.uuid4().hex


class ActivationToken(db.Model):
    __tablename__ = 'activation_tokens'

    token = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id'))

    def __init__(self, user):
        self.token = uuid.uuid4().hex
        self.user_id = user.id


class Plugin(db.Model):
    __tablename__ = 'plugins'

    id = db.Column(db.String(32), primary_key=True)
    name = db.Column(db.String(32))
    _schema = db.Column('schema', db.Text)
    _form = db.Column('form', db.Text)
    _model = db.Column('model', db.Text)

    def __init__(self):
        self.id = uuid.uuid4().hex

    @hybrid_property
    def schema(self):
        return load_column(self._schema)

    @schema.setter
    def schema(self, value):
        self._schema = json.dumps(value)

    @hybrid_property
    def form(self):
        return load_column(self._form)

    @form.setter
    def form(self, value):
        self._form = json.dumps(value)

    @hybrid_property
    def model(self):
        return load_column(self._model)

    @model.setter
    def model(self, value):
        self._model = json.dumps(value)


class Blueprint(db.Model):
    __tablename__ = 'blueprints'
    id = db.Column(db.String(32), primary_key=True)
    name = db.Column(db.String(MAX_NAME_LENGTH))
    _config = db.Column('config', db.Text)
    is_enabled = db.Column(db.Boolean, default=False)
    plugin = db.Column(db.String(32), db.ForeignKey('plugins.id'))
    max_lifetime = db.Column(db.Integer, default=3600)

    def __init__(self):
        self.id = uuid.uuid4().hex

    @hybrid_property
    def config(self):
        return load_column(self._config)

    @config.setter
    def config(self, value):
        self._config = json.dumps(value)


class Instance(db.Model):
    __tablename__ = 'instances'
    id = db.Column(db.String(32), primary_key=True)
    user_id = db.Column(db.String(32), db.ForeignKey('users.id'))
    blueprint_id = db.Column(db.String(32), db.ForeignKey('blueprints.id'))
    name = db.Column(db.String(64), unique=True)
    public_ip = db.Column(db.String(64))
    client_ip = db.Column(db.String(64))
    provisioned_at = db.Column(db.DateTime)
    state = db.Column(db.String(32))
    error_msg = db.Column(db.String(256))
    _instance_data = db.Column('instance_data', db.Text)

    def __init__(self, blueprint, user):
        self.id = uuid.uuid4().hex
        self.blueprint_id = blueprint.id
        self.user_id = user.id
        self.state = 'starting'

    @hybrid_property
    def instance_data(self):
        return load_column(self._instance_data)

    @instance_data.setter
    def instance_data(self, value):
        self._instance_data = json.dumps(value)

    @hybrid_property
    def user(self):
        return User.query.filter_by(id=self.user_id).first()


class SystemToken(db.Model):
    __tablename__ = 'system_tokens'

    token = db.Column(db.String(32), primary_key=True)
    role = db.Column(db.Integer)
    created_at = db.Column(db.DateTime)

    def __init__(self, role):
        self.role = role
        self.token = uuid.uuid4().hex
        self.created_at = datetime.datetime.utcnow()

    @staticmethod
    def verify(token):
        return SystemToken.query.filter_by(token=token).first()


db.create_all()
