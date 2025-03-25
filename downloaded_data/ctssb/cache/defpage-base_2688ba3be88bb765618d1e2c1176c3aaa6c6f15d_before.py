from pyramid.httpexceptions import HTTPFound
from pyramid.renderers import render_to_response
from defpage.base.config import system_params
from defpage.base import meta
from defpage.base import apps

def anonym_only(func):
    def wrapper(req):
        if req.user.authenticated:
            req.session.flash(u"You are authenticated already")
            return HTTPFound(location="/")
        return func(req)
    return wrapper

def empty(req):
    return {}

def forbidden(req):
    req.response.status = 403
    return {}

def unauthorized(req):
    req.response.status = 401
    return {}

def default(req):
    if not req.user.authenticated:
        return render_to_response("defpage.base:templates/frontpage/unauthenticated.pt",
                                  {"login_url":system_params.login_url,
                                   "signup_url":system_params.signup_url},
                                  request=req)
    return render_to_response("defpage.base:templates/frontpage/authenticated.pt",
                              {}, request=req)

def create_collection(req):
    if req.POST.get("submit"):
        title = req.POST.get("title", u"").strip()
        if not title:
            req.session.flash(u"Title is required")
            return {}
        cid = meta.create_collection(req.user.userid, title)
        return HTTPFound(location="/collection/%s" % cid)
    return {}

def display_collection(req):
    cid = req.matchdict["name"]
    info = meta.get_collection(req.user.userid, cid)
    return {"info":info}

def delete_collection(req):
    cid = req.matchdict["name"]
    info = meta.get_collection(req.user.userid, cid)
    if req.POST.get("submit"):
        if req.POST.get("confirm"):
            meta.delete_collection(req.user.userid, cid)
            return HTTPFound(location="/")
    return {"info":info}

def collection_properties(req):
    cid = req.matchdict["name"]
    info = meta.get_collection(req.user.userid, cid)
    if req.POST.get("submit"):
        title = req.POST.get("title")
        if title:
            meta.edit_collection(req.user.userid, cid, title=title)
            return HTTPFound(location="/collection/%s" % cid)
    return {"info":info}

def collection_roles(req):
    return {}

def source_overview(req):
    cid = req.matchdict["name"]
    info = meta.get_collection(req.user.userid, cid)
    source = len(info["sources"]) == 1 and info["sources"][0] or None
    stypes  = apps.get_source_types()
    def get_stype(k):
        for i in stypes:
            if i["id"] == k:
                return i
    if req.POST.get("setup_source"):
        stype_id = req.POST.get("source_type_id")
        stype = get_stype(stype_id)
        if stype:
            return HTTPFound(location=u"%s/collections/%s" % (stype["url"], cid))
    return {"source":source, "source_types":stypes}

def transmission_overview(req):
    return {}

def public_overview(req):
    return {}
