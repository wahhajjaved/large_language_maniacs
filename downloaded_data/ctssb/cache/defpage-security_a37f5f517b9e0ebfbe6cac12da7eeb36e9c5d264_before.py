import logging
from sqlalchemy import and_
from pyramid.httpexceptions import HTTPFound
from pyramid.httpexceptions import HTTPNotFound
from pyramid.httpexceptions import HTTPUnauthorized
from pyramid.response import Response
from pyramid.renderers import render_to_response
from pyramid.security import remember
from pyramid.security import forget
from pyramid.security import authenticated_userid
from defpage.lib.authentication import authenticated
from defpage.security.sql import DBSession
from defpage.security.sql import PendingRegistration
from defpage.security.sql import User
from defpage.security.util import validate_email
from defpage.security.config import system_params
from defpage.security.mail import signup_message
from defpage.security.mail import sendmail
from defpage.security.session import authenticated_sessions
from defpage.security import meta

sessions_logger = logging.getLogger("defpage_sessions")

def anonym_only(func):
    def wrapper(req):
        if authenticated_userid(req):
            req.session.flash(u"You are authenticated already")
            return HTTPFound(location="/")
        return func(req)
    return wrapper

def empty(req):
    return {}

@anonym_only
def anonym_only_empty_view(req):
    return {}

def default(req):
    user_id = authenticated_userid(req)
    if user_id:
        return {}
    return HTTPFound(location="/login")

def forbidden(req):
    req.response.status = 403
    return {}

def unauthorized(req):
    req.response.status = 401
    return {}

@anonym_only
def signup(req):
    email = req.POST.get("login")
    if email:
        if not validate_email(email):
            req.session.flash(u"Invalid email address")
            return {}
        dbs = DBSession()
        if dbs.query(User).filter(User.email==email).first():
            req.session.flash(u"Email already exist")
            return {}
        old = dbs.query(PendingRegistration).filter(PendingRegistration.email==email).first()
        if old:
            dbs.delete(old)
        pr = PendingRegistration(email)
        code = pr.code
        dbs.add(pr)
        url = u"http://%s/signup_confirm?&email=%s&code=%s" % (req.host, email, code)
        message_body = signup_message % (url, url, email)
        sendmail(recipients=[email], subject=u"Registration on defpage.com", body=message_body)
        req.session.flash(u"We've sent you a confirmation code! Please check your email.")
        return render_to_response("defpage.security:templates/empty.pt", {}, request=req) 
    return {}

@anonym_only
def signup_confirm(req):
    code = req.params.get("code")
    email = req.params.get("email")
    if not code or not email:
        return HTTPFound(location="/signup_code")
    dbs = DBSession()
    pr = dbs.query(PendingRegistration).filter(
        and_(PendingRegistration.code==code,
             PendingRegistration.email==email)
        ).first()
    if not pr:
        req.session.flash(u"Wrong invite code or email address")
        return HTTPFound(location="/signup_code")
    password = req.POST.get("password")
    confirm_password = req.POST.get("confirm_password")
    if password and confirm_password:
        if password != confirm_password:
            req.session.flash(u"Confirm password")
            return {}
        user = User(pr.email, password)
        dbs.add(user)
        dbs.delete(pr)
        req.session.flash(u"Welcome! Your account is activated now.")
        return HTTPFound(location=system_params.base_url)
    return {}

@anonym_only
def login(req):
    login = req.POST.get("login")
    password = req.POST.get("password")
    if login and password:
        dbs = DBSession()
        user = dbs.query(User).filter(User.email==login).first()
        if user and user.validate_password(password):
            next_url = req.POST.get("camefrom") or system_params.base_url
            headers = remember(req, str(user.id), email=login)
            return HTTPFound(location=next_url, headers=headers)
        else:
            req.session.flash(u"Wrong email address or password")
            return HTTPFound(location=system_params.base_url)
    return {}

def logout(req):
    return HTTPFound(location=system_params.base_url, headers=forget(req))

def sessions(req):
    k = req.matchdict['session_id']
    v = authenticated_sessions.get(k)
    sessions_logger.debug("Get session resource: " + unicode(k) + " :: " + unicode(v))
    return v or HTTPNotFound()

@authenticated
def account_overview(req):
    userid = req.matchdict["name"]
    if userid != authenticated_userid(req):
        raise HTTPUnauthorized
    dbs = DBSession()
    user = dbs.query(User).filter(User.id==int(userid)).first()
    return {"user":user}

@authenticated
def account_delete(req):
    userid = req.matchdict["name"]
    if userid != authenticated_userid(req):
        raise HTTPUnauthorized
    collections = meta.search_collections(userid)
    reasons = []
    for c in collections:
        if c["role"] == "owner":
            reasons.append(u"You are owner of collection <b>'" + c["title"] +
                           u"'</b>. Delete this collection or assign owner role to other user")
    if len(reasons) > 0:
        return render_to_response("defpage.security:templates/account_undelete.pt",
                                  {"reasons":reasons},
                                  request=req)
    if req.POST.get("submit"):
        if req.POST.get("confirm"):
            headers = forget(req)
            dbs = DBSession()
            user = dbs.query(User).filter(User.id==int(userid)).first()
            dbs.delete(user)
            return HTTPFound(location=system_params.base_url, headers=headers)
    return render_to_response("defpage.security:templates/account_delete.pt", {}, request=req)
