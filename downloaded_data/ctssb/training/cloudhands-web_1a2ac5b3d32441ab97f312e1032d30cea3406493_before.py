#!/usr/bin/env python3
#   encoding: UTF-8

import argparse
import datetime
import logging
import os.path
import platform
import re
import sqlite3
import sys
import uuid

from pyramid.authentication import AuthTktAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.config import Configurator
from pyramid.exceptions import Forbidden
from pyramid.exceptions import NotFound
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.httpexceptions import HTTPCreated
from pyramid.httpexceptions import HTTPFound
from pyramid.httpexceptions import HTTPInternalServerError
from pyramid.interfaces import IAuthenticationPolicy
from pyramid.renderers import JSON
from pyramid.security import authenticated_userid

from pyramid_authstack import AuthenticationStackPolicy
from pyramid_macauth import MACAuthenticationPolicy

from waitress import serve

from cloudhands.burst.membership import handle_from_email
from cloudhands.burst.membership import Activation
from cloudhands.burst.membership import Invitation

from cloudhands.common.fsm import MembershipState
from cloudhands.common.connectors import initialise
from cloudhands.common.connectors import Registry
from cloudhands.common.fsm import HostState
from cloudhands.common.schema import EmailAddress
from cloudhands.common.schema import Host
from cloudhands.common.schema import Membership
from cloudhands.common.schema import Organisation
from cloudhands.common.schema import PosixUId
from cloudhands.common.schema import PosixGId
from cloudhands.common.schema import PublicKey
from cloudhands.common.schema import Resource
from cloudhands.common.schema import Serializable
from cloudhands.common.schema import State
from cloudhands.common.schema import Touch
from cloudhands.common.schema import User
#import cloudhands.common
import cloudhands.web
from cloudhands.web.indexer import people
from cloudhands.web import __version__
from cloudhands.web.model import HostView
from cloudhands.web.model import Page
from cloudhands.web.model import PeoplePage

DFLT_PORT = 8080
DFLT_DB = ":memory:"
DFLT_IX = "cloudhands.wsh"

CRED_TABLE = {}


def registered_connection():
    r = Registry()
    return r.connect(*next(iter(r.items)))


def authenticate_user(request):
    userId = authenticated_userid(request)
    if userId is None:
        raise Forbidden()

    con = registered_connection()
    user = con.session.query(User).join(Touch).join(
        EmailAddress).filter(EmailAddress.value == userId).first()
    if not user:
        nf = NotFound("User not found for {}".format(userId))
        nf.userId = userId
        raise nf 
    return user


def create_membership_resources(
    session, m, rTyp, vals, prvdr="cloudhands.web.indexer"):
    latest = m.changes[-1]
    for v in vals:
        resource = rTyp(value=v, provider=prvdr)
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
                rTyp.value == v, rTyp.provider == prvdr).first()


def paths(request):
    return {p: os.path.dirname(request.static_url(
        "cloudhands.web:static/{}/{}".format(p, f)))
        for p, f in (
            ("css", "any.css"), ("js", "any.js"), ("img", "any.png"))}


def regex_adapter(obj, request):
    return obj.pattern


def record_adapter(obj, request):
    rv = obj.as_dict()
    try:
        del rv["id"]
    except KeyError:
        pass
    return rv


def top_read(request):
    userId = authenticated_userid(request)
    if userId is None:
        raise Forbidden()

    con = registered_connection()
    status = con.session.query(Host).join(Touch).order_by(
        Touch.at.desc()).first()

    page = Page(paths=paths(request))
    if status:
        page.layout.items.push(status)

    return dict(page.termination())


def hosts_read(request):
    log = logging.getLogger("cloudhands.web.hosts")
    userId = authenticated_userid(request)
    if userId is None:
        raise Forbidden()

    con = registered_connection()
    user = con.session.query(User).join(Touch).join(
        EmailAddress).filter(EmailAddress.value == userId).first()
    if not user:
        raise NotFound("User not found for {}".format(userId))

    memberships = con.session.query(Membership).join(Touch).join(
        State).join(User).filter(
        User.id == user.id).filter(
        State.name == "active").all()
    log.debug(memberships)

    # FIXME!
    #hosts = con.session.query(Host).join(Touch).join(User).filter(
    #    User == user).all() # JVOs are containers for hosts
    hosts = con.session.query(Host).all()
    page = Page(paths=paths(request))
    for h in hosts:
        page.layout.items.push(h)
    for m in memberships:
        page.layout.options.push(m)

    return dict(page.termination())


def membership_read(request):
    log = logging.getLogger("cloudhands.web.membership")
    m_uuid = request.matchdict["mship_uuid"]
    con = registered_connection()
    mship = con.session.query(Membership).filter(
        Membership.uuid == m_uuid).first()
    try:
        user = authenticate_user(request)
    except NotFound as e:
        # Create user only if invited
        if mship.changes[-1].state.name != "invite":
            raise Forbidden()

        user = User(handle=handle_from_email(e.userId), uuid=uuid.uuid4().hex)
        ea = EmailAddress(
            value=cloudhands.web.main.authenticated_userid(),
            provider="https://login.persona.org")
        act = Activation(user, mship, ea)(con.session)
        log.debug(user)

    page = Page(session=con.session, user=user, paths=paths(request))
    for r in con.session.query(Resource).join(Touch).join(Membership).filter(
        Membership.uuid == m_uuid).all():
        page.layout.items.push(r)
    page.layout.options.push(mship)
    return dict(page.termination())


def membership_update(request):
    log = logging.getLogger("cloudhands.web.membership")
    user = authenticate_user(request)
    con = registered_connection()
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
    if not prvlg or not prvlg.changes[-1].state.name == "active":
        raise Forbidden("Admin privilege is required to update membership.")

    index = request.registry.settings["args"].index
    query = dict(request.POST).get("designator", "") # TODO: validate
    try:
        p = next(people(index, query, field="id"))
    except:
        raise Forbidden("LDAP record not accessible.")

    for typ, vals in zip(
        (PosixUId, PosixGId, PublicKey), ([p.uid], p.gids, p.keys)):
        for r in create_membership_resources(con.session, mship, typ, vals):
            log.debug(r)

    raise HTTPFound(
        location=request.route_url("membership", mship_uuid=m_uuid))

def organisation_read(request):
    log = logging.getLogger("cloudhands.web.organisation")
    userId = authenticated_userid(request)
    if userId is None:
        raise Forbidden()

    con = registered_connection()
    user = con.session.query(User).join(Touch).join(
        EmailAddress).filter(EmailAddress.value == userId).first()
    if not user:
        raise NotFound("User not found for {}".format(userId))
    oN = request.matchdict["org_name"]
    org = con.session.query(Organisation).filter(
        Organisation.name == oN).first()
    page = Page(session=con.session, user=user, paths=paths(request))
    page.layout.options.push(org)
    return dict(page.termination())


def organisation_hosts_create(request):
    log = logging.getLogger("cloudhands.web.organisation")
    userId = authenticated_userid(request)
    if userId is None:
        raise Forbidden()

    con = registered_connection()
    user = con.session.query(User).join(Touch).join(
        EmailAddress).filter(EmailAddress.value == userId).first()
    if not user:
        raise NotFound("User not found for {}".format(userId))

    data = HostView(request.POST)
    if data.invalid:
        raise HTTPBadRequest(
            "Bad value in '{}' field".format(data.invalid[0].name))

    oN = request.matchdict["org_name"]
    if data["organisation"] != oN:
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
        name=data["hostname"]
        )
    host.changes.append(
        Touch(artifact=host, actor=user, state=requested, at=now))
    log.info(host)
    con.session.add(host)
    con.session.commit()
    raise HTTPFound(location=request.route_url("hosts"))


def organisation_memberships_create(request):
    log = logging.getLogger("cloudhands.web.organisation")
    userId = authenticated_userid(request)
    if userId is None:
        raise Forbidden()

    con = registered_connection()
    oN = request.matchdict["org_name"]
    org = con.session.query(Organisation).filter(
        Organisation.name == oN).first()
    if not org:
        raise NotFound("Organisation '{}' not found".format(oN))

    user = con.session.query(User).join(Touch).join(
        EmailAddress).filter(EmailAddress.value == userId).first()
    if not user:
        raise NotFound("User not found for {}".format(userId))
    invite = Invitation(user, org)(con.session)
    if not invite:
        raise Forbidden("User {} lacks permission.".format(user.handle))
    else:
        log.debug(invite.artifact)
        locn = request.route_url(
            "membership", mship_uuid=invite.artifact.uuid)
        raise HTTPFound(
            #headers=[("Location", locn)],
            location=request.route_url("people"))


def people_read(request):
    log = logging.getLogger("cloudhands.web.people")
    userId = authenticated_userid(request)
    if userId is None:
        raise Forbidden()
    con = registered_connection()
    user = con.session.query(User).join(Touch).join(
        EmailAddress).filter(EmailAddress.value == userId).first()
    page = PeoplePage(session=con.session, user=user, paths=paths(request))
    index = request.registry.settings["args"].index
    query = dict(request.GET).get("description", "") # TODO: validate
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


def wsgi_app(args):
    # TODO: pick up settings by discovery
    settings = {
        "persona.secret": "FON85B9O3VCMQ90517Z1",
        "persona.audiences": [
            "http://{}:80".format(platform.node()),
            "http://localhost:8080"],
        "macauth.master_secret": "MU3D133C4FC4M0EDWHXK",
        "args": args
        }
    config = Configurator(settings=settings)
    config.include("pyramid_chameleon")
    config.include("pyramid_persona")

    hateoas = JSON(indent=4)
    hateoas.add_adapter(type(re.compile("")), regex_adapter)
    hateoas.add_adapter(Serializable, record_adapter)
    config.add_renderer("hateoas", hateoas)

    config.add_route("top", "/")
    config.add_view(
        top_read, route_name="top", request_method="GET",
        renderer="cloudhands.web:templates/base.pt")

    config.add_route("hosts", "/hosts")
    #config.add_view(
    #    hosts_read, route_name="hosts", request_method="GET",
    #    renderer="hateoas", accept="application/json", xhr=None)
    config.add_view(
        hosts_read, route_name="hosts", request_method="GET",
        renderer="cloudhands.web:templates/hosts.pt")

    config.add_route("membership", "/membership/{mship_uuid}")
    config.add_view(
        membership_read, route_name="membership", request_method="GET",
        #renderer="hateoas", accept="application/json", xhr=None)
        renderer="cloudhands.web:templates/membership.pt")

    config.add_view(
        membership_update,
        route_name="membership", request_method="POST",
        renderer="hateoas", accept="application/json", xhr=None)

    config.add_route("organisation", "/organisation/{org_name}")
    config.add_view(
        organisation_read, route_name="organisation", request_method="GET",
        #renderer="hateoas", accept="application/json", xhr=None)
        renderer="cloudhands.web:templates/organisation.pt")

    # TODO: unify organisation/{} and organisation/{}/hosts (use options)
    config.add_route("organisation_hosts", "/organisation/{org_name}/hosts")
    config.add_view(
        organisation_hosts_create,
        route_name="organisation_hosts", request_method="POST",
        renderer="cloudhands.web:templates/hosts.pt")

    config.add_route(
        "organisation_memberships", "/organisation/{org_name}/memberships")
    config.add_view(
        organisation_memberships_create,
        route_name="organisation_memberships", request_method="POST",
        renderer="hateoas", accept="application/json", xhr=None)

    config.add_route("people", "/people")
    config.add_view(
        people_read, route_name="people", request_method="GET",
        #renderer="hateoas", accept="application/json", xhr=None)
        renderer="cloudhands.web:templates/people.pt")

    config.add_route("creds", "/creds")
    config.add_view(
        macauth_creds, route_name="creds", request_method="GET",
        renderer="json", accept="application/json")
        #renderer="cloudhands.web:templates/creds.pt")

    config.add_static_view(name="css", path="cloudhands.web:static/css")
    config.add_static_view(name="js", path="cloudhands.web:static/js")
    config.add_static_view(name="img", path="cloudhands.web:static/img")

    authn_policy = AuthenticationStackPolicy()
    authn_policy.add_policy(
        "email",
        AuthTktAuthenticationPolicy(
            settings["persona.secret"],
            callback=None)
        )
    authn_policy.add_policy(
        "apimac",
        MACAuthenticationPolicy(
            settings["macauth.master_secret"],
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
    r = Registry()
    session = r.connect(sqlite3, args.db).session
    initialise(session)
    return session


def main(args):
    session = configure(args)
    app = wsgi_app(args)
    serve(app, host="localhost", port=args.port, url_scheme="http")
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
