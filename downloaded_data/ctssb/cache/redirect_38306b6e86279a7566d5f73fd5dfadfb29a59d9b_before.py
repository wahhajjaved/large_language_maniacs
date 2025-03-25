import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, lazyload

from models import User, Domain, Base, Action, ActionType
import util


class Storage:

    def __init__(self, session):
        self.session = session

    def delete_user(self, user):
        for domain in user.domains:
            self.delete_domain(domain)
        self.delete(user)

    def delete_domain(self, domain):
        self.delete(domain)

    def get_users_emails(self, query):
        emails = []
        result = self.session.execute(query)
        for row in result:
            email = row[0]
            emails.append(email)
        return emails

    def get_user_by_email(self, email):
        user = self.session.query(User).filter(User.email == email).first()
        if user and not user.update_token:
            user.update_token = util.create_token()
        return user

    def get_user_by_activate_token(self, activate_token):
        return self.get_user_by_token(ActionType.ACTIVATE, activate_token)

    def get_user_by_token(self, type, token):
        user = self.session\
            .query(User)\
            .join(Action)\
            .filter(Action.action_type_id == type)\
            .filter(Action.token == token).first()
        return user

    def get_user_by_update_token(self, update_token):
        user = self.session.query(User).filter(User.update_token == update_token).first()
        return user

    def get_domain_by_update_token(self, update_token):
        domain = self.session.query(Domain).filter(Domain.update_token == update_token).first()
        return domain

    def get_domain_by_name(self, user_domain):
        domain = self.session.query(Domain).filter(Domain.user_domain == user_domain).first()
        return domain

    def domains_iterate(self):
        for domain in self.session.query(Domain).yield_per(10):
            yield domain
    
    def get_domains_last_update_before(self, date, limit):
        return self.session.query(Domain).filter(Domain.last_update < data).filter(Domain.ip != None).order_by(Domain.last_update).limit(limit).all()

    def users_iterate(self, include_unsubscribed=False):
        if include_unsubscribed:
            for user in self.session.query(User).options(lazyload('*')).yield_per(10):
                yield user
        else:
            for user in self.session.query(User).options(lazyload('*')).filter(User.unsubscribed == False).yield_per(10):
                yield user

    def get_action(self, token):
        return self.session.query(Action).filter(Action.token == token).first()

    def add(self, *args):
        if len(args) > 0 and isinstance(args[0], list):
            args = args[0]
        for obj in args:
            self.session.add(obj)

    def delete(self, *args):
        if len(args) > 0 and isinstance(args[0], list):
            args = args[0]
        for obj in args:
            self.session.delete(obj)
            self.session.flush()

    def clear(self):
        self.session.query(Domain).delete()
        self.session.query(Action).delete()
        self.session.query(User).delete()


class SessionContext:

    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return Storage(self.session)

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_val is not None:
                logging.error('exception happened', exc_info=(exc_type, exc_val, exc_tb))
                raise exc_val
            else:
                try:
                    self.session.commit()
                except Exception, e:
                    logging.exception('unable to commit transaction')
                    self.session.rollback()
                    raise e
        finally:
            self.session.expunge_all()
            self.session.close()


class SessionContextFactory:

    def __init__(self, maker):
        self.maker = maker

    def __call__(self):
        return SessionContext(self.maker())


def get_session_maker(database_spec):
    engine = create_engine(database_spec)
    maker = sessionmaker(expire_on_commit = False)
    maker.configure(bind=engine)
    Base.metadata.create_all(engine)
    return maker


def mysql_spec(host, user, password, database, port=3306):
    database_spec = "mysql+mysqldb://{0}:{1}@{2}:{3}/{4}".format(user, password, host, port, database)
    return database_spec


def mysql_spec_config(config):
    host = config.get('mysql', 'host')
    user = config.get('mysql', 'user')
    password = config.get('mysql', 'passwd')
    database = config.get('mysql', 'db')
    return mysql_spec(host, user, password, database)
