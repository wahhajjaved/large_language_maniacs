#!/usr/bin/env python3
#   encoding: UTF-8

import argparse
import datetime
import functools
import logging
import operator
import os.path
import platform
import re
import sqlite3
import sys
import uuid

import bcrypt

from pyramid.authentication import AuthTktAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.config import Configurator
from pyramid.exceptions import Forbidden
from pyramid.exceptions import NotFound
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.httpexceptions import HTTPClientError
from pyramid.httpexceptions import HTTPCreated
from pyramid.httpexceptions import HTTPFound
from pyramid.httpexceptions import HTTPInternalServerError
from pyramid.interfaces import IAuthenticationPolicy
from pyramid.renderers import JSON
from pyramid.security import authenticated_userid
from pyramid.security import forget
from pyramid.security import remember

from pyramid_authstack import AuthenticationStackPolicy
from pyramid_macauth import MACAuthenticationPolicy

from sqlalchemy import desc

from waitress import serve

from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry
from cloudhands.common.discovery import settings
import cloudhands.common.factories
from cloudhands.common.pipes import SimplePipeQueue
from cloudhands.common.schema import Appliance
from cloudhands.common.schema import BcryptedPassword
from cloudhands.common.schema import CatalogueChoice
from cloudhands.common.schema import CatalogueItem
from cloudhands.common.schema import EmailAddress
from cloudhands.common.schema import Host
from cloudhands.common.schema import Label
from cloudhands.common.schema import Membership
from cloudhands.common.schema import Organisation
from cloudhands.common.schema import OSImage
from cloudhands.common.schema import PosixUId
from cloudhands.common.schema import PosixUIdNumber
from cloudhands.common.schema import PosixGId
from cloudhands.common.schema import Provider
from cloudhands.common.schema import PublicKey
from cloudhands.common.schema import Registration
from cloudhands.common.schema import Resource
from cloudhands.common.schema import Serializable
from cloudhands.common.schema import Subscription
from cloudhands.common.schema import State
from cloudhands.common.schema import Touch
from cloudhands.common.schema import User
from cloudhands.common.states import ApplianceState
from cloudhands.common.states import HostState
from cloudhands.common.states import MembershipState
from cloudhands.common.states import RegistrationState

import cloudhands.web
from cloudhands.identity.ldap_account import change_password
from cloudhands.identity.ldap_account import next_uidnumber
from cloudhands.identity.membership import handle_from_email
from cloudhands.identity.membership import Acceptance
from cloudhands.identity.membership import Invitation
from cloudhands.identity.registration import NewAccount
from cloudhands.identity.registration import NewPassword
from cloudhands.web.catalogue import CatalogueItemView
from cloudhands.web.indexer import people
from cloudhands.web import __version__
from cloudhands.web.model import BcryptedPasswordView
from cloudhands.web.model import HostView
from cloudhands.web.model import LabelView
from cloudhands.web.model import MembershipView
from cloudhands.web.model import Page
from cloudhands.web.model import PageInfo
from cloudhands.web.model import PeoplePage
from cloudhands.web.model import PublicKeyView
from cloudhands.web.model import RegistrationView
from cloudhands.web.model import StateView

DFLT_PORT = 8080
DFLT_DB = ":memory:"
DFLT_IX = "cloudhands.wsh"

CRED_TABLE = {}


def cfg_paths(request, cfg=None):
    cfg = cfg or {
        "paths.assets": dict(
            css = "cloudhands.web:static/css",
            html = "cloudhands.web:static/html",
            img = "cloudhands.web:static/img",
            js = "cloudhands.web:static/js")
    }
    return {p: os.path.dirname(request.static_url(
        '/'.join((cfg["paths.assets"][p], f))))
        for p, f in (
            ("css", "any.css"), ("js", "any.js"), ("img", "any.png"))}


def registered_connection(request):
    r = Registry()
    return r.connect(*next(iter(r.items)))

def authenticate_user(request, refuse:Exception=None):
    userId = authenticated_userid(request)
    if refuse and userId is None:
        raise refuse("Authentication failure")

    con = registered_connection(request)

    # Persona's user ids are email addresses, whereas Pyramid auth uses
    # user names. We want to test for either.
    user = (con.session.query(User).filter(User.handle == userId).first() or
            con.session.query(User).join(Touch).join(
                EmailAddress).filter(EmailAddress.value == userId).first())

    if refuse and not user:
        nf = refuse("User not found for {}".format(userId))
        nf.userId = userId
        raise nf
    return user


def create_membership_resources(session, m, rTyp, vals):
    provider = session.query(Provider).first()  # FIXME
    latest = m.changes[-1]
    for v in vals:
        resource = rTyp(value=v, provider=provider)
        now = datetime.datetime.utcnow()
        act = Touch(artifact=m, actor=latest.actor, state=latest.state, at=now)
        m.changes.append(act)
        resource.touch = act
        try:
            session.add(resource)
            session.commit()
        except Exception as e:
            session.rollback()
        finally:
            yield session.query(rTyp).filter(
                rTyp.value == v, rTyp.provider == provider).first()


def datetime_adapter(obj, request):
    return str(obj)


def regex_adapter(obj, request):
    return obj.pattern


def record_adapter(obj, request):
    rv = obj.as_dict()
    try:
        del rv["id"]
    except KeyError:
        pass
    return rv


def touch_adapter(obj, request):
    return {
        "at": obj.at,
        "state": {
            "fsm": obj.state.fsm,
            "name": obj.state.name
        } 
    }


class LoginForbidden(Forbidden): pass
class RegistrationForbidden(Forbidden): pass

def top_read(request):
    log = logging.getLogger("cloudhands.web.top_read")
    con = registered_connection(request)
    user = authenticate_user(request)
    page = Page(
        session=con.session, user=user,
        paths=cfg_paths(request, request.registry.settings.get("cfg", None)))
    page.layout.info.push(PageInfo(refresh=30))

    if user:
        mships = con.session.query(Membership).join(Touch).join(User).filter(
            User.id==user.id).all()
        reg = con.session.query(Registration).join(Touch).join(User).filter(
            User.uuid == user.uuid).first()
        if reg:
            page.layout.nav.push(reg)
    else:
        mships = []

    for org in sorted(
        {i.organisation for i in mships}, key=operator.attrgetter("name")
    ):
        page.layout.nav.push(org)

    for act in con.session.query(Touch).order_by(desc(Touch.at)).limit(5):
        page.layout.items.push(act)

    return dict(page.termination())


def appliance_read(request):
    log = logging.getLogger("cloudhands.web.appliance_read")
    con = registered_connection(request)
    user = con.session.merge(authenticate_user(request, Forbidden))
    appUuid = request.matchdict["app_uuid"]
    app = con.session.query(Appliance).filter(
        Appliance.uuid == appUuid).first()
    if not app:
        raise NotFound("Appliance {} not found".format(appUuid))

    mships = con.session.query(Membership).join(Touch).join(User).filter(
        User.id==user.id).all()

    page = Page(
        session=con.session, user=user,
        paths=cfg_paths(request, request.registry.settings.get("cfg", None)))
    page.layout.info.push(PageInfo(title="Configure appliance"))

    for o in sorted(
        {i.organisation for i in mships}, key=operator.attrgetter("name")
    ):
        page.layout.nav.push(o)

    resources = [r for c in app.changes for r in c.resources]
    for i in resources:
        page.layout.items.push(i)
    if not any(i for i in resources if isinstance(i, Label)):
        label = Label()
        label.uuid = appUuid
        page.layout.items.push(label)

        # option for public IP address

    return dict(page.termination())


def appliance_modify(request):
    log = logging.getLogger("cloudhands.web.appliance_modify")
    con = registered_connection(request)
    user = con.session.merge(authenticate_user(request, Forbidden))
    appUuid = request.matchdict["app_uuid"]
    app = con.session.query(Appliance).filter(
        Appliance.uuid == appUuid).first()
    if not app:
        raise NotFound("Appliance {} not found".format(appUuid))

    now = datetime.datetime.utcnow()
    data = StateView(request.POST)
    if data.invalid:
        data = LabelView(request.POST)
        if data.invalid:
            raise HTTPBadRequest(
                "Bad value in '{}' field".format(data.invalid[0].name))
        else:
            pre_provision  = con.session.query(ApplianceState).filter(
                ApplianceState.name == "pre_provision").one()
            act = Touch(artifact=app, actor=user, state=pre_provision, at=now)

            label = Label(
                name=data["name"], description=data["description"],
                touch=act)
            con.session.add(label)
            con.session.commit()
    else:
        state = con.session.query(State).filter(
            State.fsm == data["fsm"]).filter(
            State.name == data["name"]).first()
        if state is None:
            raise HTTPBadRequest(
                "No such state {fsm} {name}".format(**data))
        else:
            act = Touch(artifact=app, actor=user, state=state, at=now)
            con.session.add(act)
            con.session.commit()

    raise HTTPFound(
        location=request.route_url(
            "organisation", org_name=app.organisation.name))
        

def host_update(request):
    log = logging.getLogger("cloudhands.web.host_update")
    con = registered_connection(request)
    user = con.session.merge(authenticate_user(request))
    hUuid = request.matchdict["host_uuid"]
    host = con.session.query(Host).filter(
        Host.uuid == hUuid).first()
    if not host:
        raise NotFound("Host {} not found".format(hUuid))

    try:
        oN = host.organisation.name
    except Exception as e:
        log.debug(e)
        raise NotFound("Organisation not found for host {}".format(hUuid))

    data = StateView(request.POST)

    try:
        badField = data.invalid[0].name
        log.debug(request.POST)
        log.debug(data)
        raise HTTPBadRequest(
            "Bad value in '{}' field".format(badField))
    except (IndexError, AttributeError):
        if data["fsm"] != "host":
            raise HTTPBadRequest(
                "Bad FSM value: {}".format(data["fsm"]))

    state = con.session.query(HostState).filter(
        HostState.name==data["name"]).first()

    if not state:
        raise NotFound("No such state '{}'".format(data["name"]))

    now = datetime.datetime.utcnow()
    act = Touch(artifact=host, actor=user, state=state, at=now)
    host.changes.append(act)
    try:
        con.session.commit()
    except Exception as e:
        log.debug(e)
        con.session.rollback()

    raise HTTPFound(
        location=request.route_url("organisation", org_name=oN))


def login_read(request):
    log = logging.getLogger("cloudhands.web.login_read")
    username = dict(request.GET).get("username", "")
    page = Page(
        paths=cfg_paths(request, request.registry.settings.get("cfg", None)))
    if getattr(request, "exception", None) is not None:
        page.layout.info.push(request.exception)
    user = User(
        uuid=uuid.uuid4().hex,
        handle=username)
    page.layout.options.push(user)
    return dict(page.termination())


def login_update(request):
    log = logging.getLogger("cloudhands.web.login_update")
    con = registered_connection(request)
    data = RegistrationView(request.POST)
    if data.invalid:
        raise HTTPBadRequest(
            "Bad value in '{}' field".format(data.invalid[0].name))

    user = con.session.query(User).filter(
        User.handle == data["username"]).first()
    if not user:
        raise HTTPClientError("User {} not found".format(data["username"]))

    # Find the most recent valid registration for this user
    reg = con.session.query(Registration).join(Touch).join(User).join(
        State).filter(User.handle == data["username"]).filter(
        State.name not in ("expired", "withdrawn")).order_by(
        desc(Touch.at)).first()
    if not reg:
        raise HTTPInternalServerError(
            "No valid registration found for {}".format(user.handle))

    try:
        passwords = sorted(
            ((c.at, r) for c in reg.changes for r in c.resources
            if isinstance(r, BcryptedPassword)),
            reverse=True)
        hash = passwords[0][1].value
    except (AttributeError, IndexError):
        raise HTTPInternalServerError(
            "Registration {} is missing a password".format(reg.uuid))

    if bcrypt.checkpw(data["password"], hash):
        headers = remember(request, user.handle)
        if reg.changes[-1].state.name == "pre_user_posixaccount":
            try:
                uids = sorted(
                    ((c.at, r) for c in reg.changes for r in c.resources
                    if isinstance(r, PosixUId)),
                    reverse=True)
                uid = uids[0][1].value
                status = change_password(uid, data["password"], timeout=3)
            except IndexError:
                raise HTTPInternalServerError(
                    "Registration {} is missing a uid".format(reg.uuid))
            else:
                if status is None:
                    raise HTTPInternalServerError(
                        "Unable to create password-protected account")

            taken = {i.value for i in con.session.query(PosixUIdNumber).all()}
            uidN = next_uidnumber(taken=taken)
            if uidN is None:
                raise HTTPInternalServerError(
                    "UIdNumber could not be allocated")
            else:
                log.info("Allocating user id number {}".format(uidN))
                act = NewAccount(user, uidN, reg)(con.session)
                # TODO: check state and report error

        try:
            config = request.registry.settings["cfg"]
            pxUId = con.session.query(PosixUId).join(Touch).join(
                Registration).filter(Registration.uuid == reg.uuid).first()
            providers = con.session.query(Provider).join(Subscription).join(
                Organisation).join(Membership).join(Touch).join(User).filter(
                User.id == user.id).all()
            for provider in providers:
                # TODO: pipes will be one per provider
                path = os.path.expanduser(config["pipe.tokens"]["vcloud"])
                msg = (reg.uuid, provider.name, pxUId.value, data["password"])
                pq = SimplePipeQueue.pipequeue(path)
                pq.put_nowait(msg)
                pq.close()
        except Exception as e:
            log.error(e)

        raise HTTPFound(
            location = request.route_url("top"), headers = headers)
    else:
        raise LoginForbidden("Login failed. Please try again.")


def logout_update(request):
    log = logging.getLogger("cloudhands.web.logout_update")
    headers = forget(request)
    log.debug(headers)
    raise HTTPFound(
        location = request.route_url("top"), headers = headers)


def membership_read(request):
    log = logging.getLogger("cloudhands.web.membership_read")
    con = registered_connection(request)
    user = authenticate_user(request)  # NB: may be None

    m_uuid = request.matchdict["mship_uuid"]
    mship = con.session.query(Membership).filter(
        Membership.uuid == m_uuid).first()

    if mship.changes[-1].state.name == "invited":
        act = Acceptance(mship, user)(con.session)
        log.debug(act)
        guest_uuid = act.actor.uuid
        reg = con.session.query(Registration).join(Touch).join(User).filter(
            User.uuid == guest_uuid).first()
        if not reg:
            raise NotFound("Registration not found for {}".format(guest_uuid))
        else:
            raise HTTPFound(
                location=request.route_url("registration", reg_uuid=reg.uuid))

    page = Page(
        session=con.session, user=user,
        paths=cfg_paths(request, request.registry.settings.get("cfg", None)))
    rsrcs = con.session.query(Resource).join(Touch).join(Membership).filter(
        Membership.uuid == m_uuid).all()
    for r in rsrcs:
        page.layout.items.push(r)
    page.layout.options.push(mship)
    return dict(page.termination())


def membership_update(request):
    log = logging.getLogger("cloudhands.web.membership_update")
    user = authenticate_user(request)
    con = registered_connection(request)
    m_uuid = request.matchdict["mship_uuid"]
    mship = con.session.query(Membership).filter(
        Membership.uuid == m_uuid).first()
    if not mship:
        raise NotFound()

    prvlg = con.session.query(Membership).join(Organisation).join(
        Touch).join(User).filter(
        User.id == user.id).filter(
        Organisation.id == mship.organisation.id).filter(
        Membership.role == "admin").first()
    if not prvlg or not prvlg.changes[-1].state.name in ("accepted", "active"):
        raise Forbidden("Admin privilege is required to update membership.")

    index = request.registry.settings["args"].index
    query = dict(request.POST).get("designator", "")  # TODO: validate
    try:
        p = next(people(index, query, field="id"))
    except:
        raise Forbidden("LDAP record not accessible.")

    for typ, vals in zip(
        (PosixUId, PosixGId, PublicKey), ([p.uid], p.gids, p.keys)
    ):
        for r in create_membership_resources(con.session, mship, typ, vals):
            log.debug(r)

    raise HTTPFound(
        location=request.route_url("membership", mship_uuid=m_uuid))


def organisation_read(request):
    log = logging.getLogger("cloudhands.web.organisation_read")
    con = registered_connection(request)
    user = con.session.merge(authenticate_user(request, Forbidden))

    page = Page(
        session=con.session, user=user,
        paths=cfg_paths(request, request.registry.settings.get("cfg", None)))
    mships = con.session.query(Membership).join(Touch).join(User).filter(
        User.id==user.id).all()

    oN = request.matchdict["org_name"]
    org = con.session.query(Organisation).filter(
        Organisation.name == oN).first()
    if not org:
        raise NotFound("Organisation not found for {}".format(oN))

    reg = con.session.query(Registration).join(Touch).join(User).filter(
        User.uuid == user.uuid).first()
    page.layout.nav.push(reg)

    for o in sorted(
        {i.organisation for i in mships},
        key=operator.attrgetter("name")
    ):
        page.layout.nav.push(o, isSelf=o is org)

    refresh = 300
    seconds = {
        "pre_provision": 5,
        "provisioning": 15,
        "pre_check": 2,
        "pre_delete": 2,
        "pre_start": 2,
        "pre_stop": 2,
        "pre_operational": 5,
        "operational": 60,
    }
    for t, s, a in sorted((
        (a.changes[-1].at, a.changes[-1].state.name, a)
        for a in org.appliances),
        reverse=True
    ):
        refresh = min(refresh, seconds.get(s, 300))
        page.layout.items.push(a)

 
    page.layout.info.push(PageInfo(title=oN, refresh=refresh))
    mships = con.session.query(Membership).join(Organisation).join(
        Touch).join(State).join(User).filter(
        User.id == user.id).filter(
        Organisation.id == org.id).all()
    for m in mships:
        page.layout.options.push(m, session=con.session)

    return dict(page.termination())


def organisation_catalogue_read(request):
    log = logging.getLogger("cloudhands.web.organisation_catalogue_read")
    con = registered_connection(request)
    user = con.session.merge(authenticate_user(request, Forbidden))

    page = Page(
        session=con.session, user=user,
        paths=cfg_paths(request, request.registry.settings.get("cfg", None)))
    mships = con.session.query(Membership).join(Touch).join(User).filter(
        User.id==user.id).all()

    oN = request.matchdict["org_name"]
    org = con.session.query(Organisation).filter(
        Organisation.name == oN).first()
    if not org:
        raise NotFound("Organisation not found for {}".format(oN))
    else:
        page.layout.info.push(PageInfo(title=oN))

    reg = con.session.query(Registration).join(Touch).join(User).filter(
        User.uuid == user.uuid).first()
    page.layout.nav.push(reg)
    for o in sorted(
        {i.organisation for i in mships}, key=operator.attrgetter("name")
    ):
        page.layout.nav.push(o, isSelf=o is org)

    for i in org.catalogue:
        page.layout.items.push(i)

    return dict(page.termination())


# TODO: Remove
def organisation_hosts_create(request):
    log = logging.getLogger("cloudhands.web.organisation_hosts_create")
    userId = authenticated_userid(request)
    if userId is None:
        raise Forbidden()

    con = registered_connection(request)
    user = con.session.query(User).join(Touch).join(
        EmailAddress).filter(EmailAddress.value == userId).first()
    if not user:
        raise NotFound("User not found for {}".format(userId))

    data = HostView(request.POST)
    if data.invalid:
        log.debug(request.POST)
        log.debug(data)
        raise HTTPBadRequest(
            "Bad value in '{}' field".format(data.invalid[0].name))

    oN = request.matchdict["org_name"]
    if data["jvo"] != oN:
        raise HTTPBadRequest("Mismatched organisation field")

    org = con.session.query(Organisation).filter(
        Organisation.name == oN).first()
    if not org:
        raise NotFound("Organisation '{}' not found".format(oN))

    now = datetime.datetime.utcnow()
    requested = con.session.query(HostState).filter(
        HostState.name == "requested").one()
    host = Host(
        uuid=uuid.uuid4().hex,
        model=cloudhands.common.__version__,
        organisation=org,
        name=data["name"]
        )
    act = Touch(artifact=host, actor=user, state=requested, at=now)
    host.changes.append(act)
    con.session.add(OSImage(name=data["image"], touch=act))
    log.info(host)
    con.session.add(host)
    con.session.commit()
    raise HTTPFound(
        location=request.route_url("organisation", org_name=oN))


def organisation_appliances_create(request):
    log = logging.getLogger("cloudhands.web.organisation_appliances_create")
    con = registered_connection(request)
    user = con.session.merge(authenticate_user(request, Forbidden))
    data = CatalogueItemView(request.POST)
    if data.invalid:
        log.debug(request.POST)
        log.debug(data)
        raise HTTPBadRequest(
            "Bad value in '{}' field".format(data.invalid[0].name))

    oN = request.matchdict["org_name"]
    org = con.session.query(Organisation).filter(
        Organisation.name == oN).first()
    if not org:
        raise NotFound("Organisation '{}' not found".format(oN))

    now = datetime.datetime.utcnow()
    configuring = con.session.query(ApplianceState).filter(
        ApplianceState.name == "configuring").one()
    app = Appliance(
        uuid=uuid.uuid4().hex,
        model=cloudhands.common.__version__,
        organisation=org,
        )
    act = Touch(artifact=app, actor=user, state=configuring, at=now)

    tmplt = con.session.query(CatalogueItem).filter(
        CatalogueItem.uuid == data["uuid"]).first()
    choice = CatalogueChoice(
        provider=None, touch=act,
        natrouted=True, **{k: getattr(tmplt, k, None)
        for k in ("name", "description", "logo")})
    con.session.add(choice)
    con.session.commit()

    raise HTTPFound(
        location=request.route_url("appliance", app_uuid=app.uuid))


def organisation_memberships_create(request):
    log = logging.getLogger("cloudhands.web.organisation_memberships_create")
    cfg = request.registry.settings.get("cfg", None)
    con = registered_connection(request)
    data = MembershipView(request.POST)
    
    if data.invalid:
        log.debug(request.POST)
        log.debug(data)
        raise HTTPBadRequest(
            "Bad value in '{}' field".format(data.invalid[0].name))

    oN = request.matchdict["org_name"]
    org = con.session.query(Organisation).filter(
        Organisation.name == oN).first()
    if not org:
        raise NotFound("Organisation '{}' not found".format(oN))

    admin = con.session.merge(authenticate_user(request, Forbidden))
    invite = Invitation(
        admin, org,
        data["username"], data["surname"], data["email"]
    )(con.session)
    if not invite:
        raise Forbidden("User {} lacks permission.".format(admin.handle))
    else:
        log.debug(invite.artifact)
        # TODO: calculate this location from membership_read view
        locn = request.route_url(
            "membership", mship_uuid=invite.artifact.uuid)
        raise HTTPFound(location=request.static_url(
            "{}/membership-confirm.html".format(
                cfg["paths.assets"]["html"])))


def people_read(request):
    log = logging.getLogger("cloudhands.web.people")
    userId = authenticated_userid(request)
    if userId is None:
        raise Forbidden()
    con = registered_connection(request)
    user = con.session.query(User).join(Touch).join(
        EmailAddress).filter(EmailAddress.value == userId).first()
    page = PeoplePage(
        session=con.session, user=user,
        paths=cfg_paths(request, request.registry.settings.get("cfg", None)))
    index = request.registry.settings["args"].index
    query = dict(request.GET).get("description", "")  # TODO: validate
    try:
        for p in people(index, query):
            page.layout.items.push(p)
    except Exception:
        log.warning("No access to index {}".format(index))
        raise HTTPInternalServerError(
            location=request.route_url("people"),
            detail="Temporary loss of index. Please try again later.")
    return dict(page.termination())


def macauth_creds(request):
    userId = authenticated_userid(request)
    if userId is None:
        raise Forbidden()

    # Get a reference to the MACAuthenticationPolicy plugin.
    stack = request.registry.getUtility(IAuthenticationPolicy)
    policy = stack.policies["apimac"]

    try:
        id, key = CRED_TABLE[userId]
    except KeyError:
        id, key = policy.encode_mac_id(request, userId)
        CRED_TABLE[userId] = (id, key)

    return {"id": id, "key": key}


def registration_passwords(request):
    log = logging.getLogger("cloudhands.web.registration_passwords")
    con = registered_connection(request)
    cfg = request.registry.settings.get("cfg", None)

    reg_uuid = request.matchdict["reg_uuid"]
    reg = con.session.query(Registration).filter(
        Registration.uuid == reg_uuid).first()
    if not reg:
        raise NotFound("Registration {} not found".format(reg_uuid))

    # This page can be visited while unauthenticated but only in the
    # first phase of the onboarding process.
    sName = reg.changes[-1].state.name
    if sName == "pre_registration_person":
        user = reg.changes[0].actor
    else:
        user = con.session.merge(authenticate_user(request, Forbidden))

    if not user is reg.changes[0].actor:
        raise Forbidden(
            "You are not authorized to modify this registration.")

    data = BcryptedPasswordView(request.POST)
    if data.invalid:
        bad = data.invalid[0].name
        if bad == "password":
            raise RegistrationForbidden(
                "The password you entered does not conform to requirements."
                " Please choose again.")
        else:
            raise HTTPBadRequest("Bad value in '{}' field".format(bad))

    act = NewPassword(user, data["password"], reg)(con.session)

    raise HTTPFound(location=request.route_url(
        "login", _query={"username": user.handle}))


def registration_keys(request):
    log = logging.getLogger("cloudhands.web.registration_keys")
    reg_uuid = request.matchdict["reg_uuid"]
    con = registered_connection(request)
    reg = con.session.query(Registration).filter(
        Registration.uuid == reg_uuid).first()
    if not reg:
        raise NotFound("Registration {} not found".format(reg_uuid))

    user = con.session.merge(authenticate_user(request, Forbidden))
    if not user is reg.changes[0].actor:
        raise Forbidden(
            "You are not authorized to modify this registration.")

    data = PublicKeyView(request.POST)
    if data.invalid:
        raise HTTPBadRequest(
            "Bad value in '{}' field".format(data.invalid[0].name))

    now = datetime.datetime.utcnow()
    state = reg.changes[-1].state
    act = Touch(artifact=reg, actor=user, state=state, at=now)

    key = PublicKey(touch=act, value=data["value"])
    con.session.add(key)
    con.session.commit()

    raise HTTPFound(
        location=request.route_url("registration", reg_uuid=reg.uuid))


def registration_read(request):
    log = logging.getLogger("cloudhands.web.registration_read")
    con = registered_connection(request)
    reg_uuid = request.matchdict["reg_uuid"]
    reg = con.session.query(Registration).filter(
        Registration.uuid == reg_uuid).first()
    if not reg:
        raise NotFound("Registration {} not found".format(reg_uuid))

    page = Page(
        session=con.session,
        paths=cfg_paths(request, request.registry.settings.get("cfg", None)))

    page.layout.nav.push(reg)

    # This page can be visited while unauthenticated but only in the
    # first phase of the onboarding process.
    sName = reg.changes[-1].state.name
    if sName == "pre_registration_person":
        # TODO: Check TimeInterval hasn't expired
        user = reg.changes[0].actor
    else:
        user = con.session.merge(authenticate_user(request, Forbidden))

    page.layout.info.push(PageInfo(title=user.handle))

    mships = con.session.query(Membership).join(Touch).join(User).filter(
        User.id==user.id).all()
    for o in sorted(
        {i.organisation for i in mships},
        key=operator.attrgetter("name")
    ):
        page.layout.nav.push(o)

    if sName == "pre_user_inetorgperson_dn":
        page.layout.options.push(PosixUId())
        return dict(page.termination())

    display = (
        (PosixUIdNumber, False),
        (PosixUId, False),
        (EmailAddress, False),
        (BcryptedPassword, True),
        (PosixGId, False),
        (PublicKey, True)
    )

    for class_, isCreatable in display:
        rsrcs = con.session.query(class_).join(Touch).join(Registration).filter(
            Registration.uuid == reg_uuid).order_by(desc(Touch.at)).all()
        if not rsrcs and isCreatable:
            blank = class_()
            blank.uuid = reg_uuid
            page.layout.options.push(blank)
        for r in rsrcs:
            page.layout.items.push(r)

    return dict(page.termination())

# TODO: Remove this view. Everything happens in registration
def user_read(request):
    log = logging.getLogger("cloudhands.web.user_read")
    con = registered_connection(request)
    user = con.session.merge(authenticate_user(request, Forbidden))
    u_uuid = request.matchdict["user_uuid"]
    actor = con.session.query(User).filter(User.uuid == u_uuid).first()

    mships = con.session.query(Membership).join(Touch).join(User).filter(
        User.id==user.id).all()

    page = Page(
        session=con.session, user=user,
        paths=cfg_paths(request, request.registry.settings.get("cfg", None)))

    for o in sorted(
        {i.organisation for i in mships}, key=operator.attrgetter("name")
    ):
        page.layout.nav.push(o)

    regs = con.session.query(Registration).join(Touch).join(User).filter(
        User.uuid == u_uuid).all()
    resources = [r for reg in regs for c in reg.changes for r in c.resources]
    for i in resources:
        page.layout.items.push(i)
    #if not any(i for i in resources if isinstance(i, Label)):
    #    label = Label()
    #    label.uuid = appUuid
    #    page.layout.items.push(label)
    return dict(page.termination())

def wsgi_app(args, cfg):
    attribs = {
        "macauth.master_secret": cfg["auth.macauth"]["secret"],
        "args": args,
        "cfg": cfg
        }

    config = Configurator(settings=attribs)
    config.include("pyramid_chameleon")

    if (cfg.has_section("auth.persona")
        and cfg.getboolean("auth.persona", "enable")):
        config.add_settings({
        "persona.secret": cfg["auth.persona"]["secret"],
        "persona.audiences": [
            cfg["auth.persona"]["host"],
            "http://{}:{}".format(platform.node(), args.port)],
        })
        config.include("pyramid_persona")

    hateoas = JSON(indent=4)
    hateoas.add_adapter(datetime.datetime, datetime_adapter)
    hateoas.add_adapter(type(re.compile("")), regex_adapter)
    hateoas.add_adapter(Serializable, record_adapter)
    hateoas.add_adapter(Touch, touch_adapter)
    config.add_renderer("hateoas", hateoas)

    config.add_route(
        "appliance", "/appliance/{app_uuid}")
    config.add_view(
        appliance_read,
        route_name="appliance", request_method="GET",
        renderer=cfg["paths.templates"]["appliance"])

    config.add_view(
        appliance_modify,
        route_name="appliance", request_method="POST",
        renderer=cfg["paths.templates"]["appliance"])

    config.add_route("top", "/")
    config.add_view(
        top_read, route_name="top", request_method="GET",
        #renderer="hateoas", accept="application/json", xhr=None)
        renderer=cfg["paths.templates"]["home"])

    config.add_route("login", "/login")
    config.add_view(
        login_read,
        route_name="login", request_method="GET",
        #renderer="hateoas", accept="application/json", xhr=None)
        renderer=cfg["paths.templates"]["login"])

    config.add_view(
        login_read, context=LoginForbidden,
        #renderer="hateoas", accept="application/json", xhr=None)
        renderer=cfg["paths.templates"]["login"])

    config.add_view(
        login_update, route_name="login", request_method="POST")
        #renderer="hateoas", accept="application/json", xhr=None)

    config.add_route("logout", "/logout")
    config.add_view(
        logout_update, route_name="logout", request_method="GET")

    config.add_route("host", "/host/{host_uuid}")
    config.add_view(
        host_update, route_name="host", request_method="POST",
        renderer="hateoas", accept="application/json", xhr=None)

    config.add_route("membership", "/membership/{mship_uuid}")
    config.add_view(
        membership_read, route_name="membership", request_method="GET",
        #renderer="hateoas", accept="application/json", xhr=None)
        renderer=cfg["paths.templates"]["membership"])

    config.add_view(
        membership_update,
        route_name="membership", request_method="POST",
        renderer="hateoas", accept="application/json", xhr=None)

    config.add_route("organisation", "/organisation/{org_name}")
    config.add_view(
        organisation_read, route_name="organisation", request_method="GET",
        #renderer="hateoas", accept="application/json", xhr=None)
        renderer=cfg["paths.templates"]["organisation"])

    config.add_route(
        "organisation_appliances", "/organisation/{org_name}/appliances")
    config.add_view(
        organisation_appliances_create,
        route_name="organisation_appliances", request_method="POST")

    config.add_route(
        "organisation_memberships", "/organisation/{org_name}/memberships")
    config.add_view(
        organisation_memberships_create,
        route_name="organisation_memberships", request_method="POST",
        renderer="hateoas", accept="application/json", xhr=None)

    config.add_route(
        "organisation_catalogue", "/organisation/{org_name}/catalogue")
    config.add_view(
        organisation_catalogue_read,
        route_name="organisation_catalogue", request_method="GET",
        #renderer="hateoas", accept="application/json", xhr=None)
        renderer=cfg["paths.templates"]["catalogue"])

    config.add_route("people", "/people")
    config.add_view(
        people_read, route_name="people", request_method="GET",
        #renderer="hateoas", accept="application/json", xhr=None)
        renderer=cfg["paths.templates"]["people"])

    config.add_view(
        login_read, context=RegistrationForbidden,
        renderer=cfg["paths.templates"]["registration"])

    config.add_route("account", "/account/{reg_uuid}")
    config.add_route("registration", "/registration/{reg_uuid}")
    config.add_view(
        registration_read, route_name="account", request_method="GET",
        #renderer="hateoas", accept="application/json", xhr=None)
        renderer=cfg["paths.templates"]["registration"])

    config.add_view(
        registration_read, route_name="registration", request_method="GET",
        #renderer="hateoas", accept="application/json", xhr=None)
        renderer=cfg["paths.templates"]["registration"])

    config.add_route("registration_keys", "/registration/{reg_uuid}/keys")
    config.add_view(
        registration_keys,
        route_name="registration_keys", request_method="POST")
        #renderer="hateoas", accept="application/json", xhr=None)

    config.add_route(
        "registration_passwords",
        "/registration/{reg_uuid}/passwords"
    )
    config.add_view(
        registration_passwords, route_name="registration_passwords",
        request_method="POST")

    config.add_route("creds", "/creds")
    config.add_view(
        macauth_creds, route_name="creds", request_method="GET",
        renderer="json", accept="application/json")
        #renderer="cloudhands.web:templates/creds.pt")

    config.add_route("user", "/user/{user_uuid}")
    config.add_view(
        user_read, route_name="user", request_method="GET",
        #renderer="hateoas", accept="application/json", xhr=None)
        renderer=cfg["paths.templates"]["user"])

    config.add_static_view(name="css", path=cfg["paths.assets"]["css"])
    config.add_static_view(name="html", path=cfg["paths.assets"]["html"])
    config.add_static_view(name="js", path=cfg["paths.assets"]["js"])
    config.add_static_view(name="img", path=cfg["paths.assets"]["img"])

    authn_policy = AuthenticationStackPolicy()
    authn_policy.add_policy(
        "auth_tkt",
        AuthTktAuthenticationPolicy(
            cfg["auth.macauth"]["secret"],
            callback=None)
        )
    authn_policy.add_policy(
        "apimac",
        MACAuthenticationPolicy(
            attribs["macauth.master_secret"],
        ))
    authz_policy = ACLAuthorizationPolicy()
    config.set_authentication_policy(authn_policy)
    config.set_authorization_policy(authz_policy)
    config.scan()

    app = config.make_wsgi_app()
    return app


def configure(args):
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s|%(message)s")
    cfgN, cfg = next(iter(settings.items()))
    r = Registry()
    session = r.connect(sqlite3, args.db).session
    initialise(session)
    return cfg, session


def main(args):
    cfg, session = configure(args)
    app = wsgi_app(args, cfg)
    serve(app, host=platform.node(), port=args.port, url_scheme="http")
    return 1


def parser(description=__doc__):
    rv = argparse.ArgumentParser(description)
    rv.add_argument(
        "--version", action="store_true", default=False,
        help="Print the current version number")
    rv.add_argument(
        "-v", "--verbose", required=False,
        action="store_const", dest="log_level",
        const=logging.DEBUG, default=logging.INFO,
        help="Increase the verbosity of output")
    rv.add_argument(
        "--port", type=int, default=DFLT_PORT,
        help="Set the port number [{}]".format(DFLT_PORT))
    rv.add_argument(
        "--db", default=DFLT_DB,
        help="Set the path to the database [{}]".format(DFLT_DB))
    rv.add_argument(
        "--index", default=DFLT_IX,
        help="Set the path to the index directory [{}]".format(DFLT_IX))
    rv.add_argument(
        "--log", default=None, dest="log_path",
        help="Set a file path for log output")
    return rv


def run():
    p = parser()
    args = p.parse_args()
    if args.version:
        sys.stdout.write(__version__ + "\n")
        rv = 0
    else:
        rv = main(args)
    sys.exit(rv)

if __name__ == "__main__":
    run()
