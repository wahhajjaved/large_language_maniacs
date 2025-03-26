import logging
import transaction
from sqlalchemy import and_
from sqlalchemy.sql import func
from sqlalchemy.sql import exists
from pyramid.response import Response
from pyramid.httpexceptions import HTTPNotFound
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.httpexceptions import HTTPForbidden
from pyramid.security import authenticated_userid
from defpage.meta.sql import DBSession
from defpage.meta.config import system_params
from defpage.meta.sql import Collection
from defpage.meta.sql import Document
from defpage.meta.sql import Source
from defpage.meta.sql import CollectionUserRole
from defpage.meta.sql import Transmission
from defpage.meta.util import int_required
from defpage.meta.util import dict_required
from defpage.meta.util import list_required
from defpage.meta.util import is_equal_items
from defpage.meta.source import make_details

meta_logger = logging.getLogger("defpage_meta")

def add_collection(req):
    params = req.json_body
    try:
        title = params["title"]
        userid = int_required(params["owner"])
    except KeyError:
        raise HTTPBadRequest
    dbs = DBSession()
    c = Collection(title)
    cid = c.id
    dbs.add(c)
    dbs.add(CollectionUserRole(cid, userid, u"owner"))
    req.response.status = "201 Created"
    return {"id":cid}

def edit_collection(req):
    userid = authenticated_userid(req)
    dbs = DBSession()
    params = req.json_body
    title = params.get("title")
    source = params.get("source")
    roles = params.get("roles")
    if title:
        req.context.title = title

    #################################
    #
    # Configure source for collection
    #
    #################################
    if source:
        source = dict_required(source)
        stype = source["type"]
        if not req.context.source_id:
            # Define source.
            # User id should be real, not system user.
            userid = int_required(userid)
            s = dbs.query(Source).filter(and_(
                    Source.user_id==userid,
                    Source.source_type==stype
                    )).scalar()
            if not s:
                # There is no such source for this {user id, source type},
                # so create new source.
                s = Source(stype, userid)
                s.source_details = make_details(stype, "source", source)
                req.context.source_id = s.id
                req.context.source_details = make_details(stype, "collection", source)
                dbs.add(s)
            else:
                # Assign existing source to this colllection.
                req.context.source_id = s.id
                req.context.source_details = make_details(stype, "collection", source)
        else:
            # Update already configured collection source data.
            # User id can be system, therefore do not pass userid into database.
            s = dbs.query(Source).filter(Source.id==req.context.source_id).scalar()
            if not is_equal_items(s.source_details, source):
                s.source_details = make_details(stype, "source", source)
            if not is_equal_items(req.context.source_details, source):
                req.context.source_details = make_details(stype, "collection", source)
    cid = req.context.id
    if roles:
        roles = dict_required(roles)
        if u"owner" not in roles.values():
            raise HTTPBadRequest
        for i in dbs.query(CollectionUserRole).filter(
            CollectionUserRole.collection_id==cid):
            dbs.delete(i)
        for userid, role in roles.items():
            dbs.add(CollectionUserRole(cid, userid, role))
    return Response(status="204 No Content")

ALLOW_DELETE = ("gd")

def del_collection(req):
    dbs = DBSession()
    cid = req.context.id
    roles = dbs.query(CollectionUserRole).filter(CollectionUserRole.collection_id==cid)
    for r in roles:
        dbs.delete(r)
    docs = dbs.query(Document).filter(Document.collection_id==cid)
    for d in docs:
        if d.source["type"] in ALLOW_DELETE:
            dbs.delete(d)
    transmissions = dbs.query(Transmission).filter(Transmission.collection_id==cid)
    for t in transmissions:
        dbs.delete(t)
    transaction.commit()
    dbs.delete(req.context)
    return Response(status="204 No Content")

def get_collection(req):
    dbs = DBSession()
    c = req.context
    cid = c.id
    roles = dict((i.user_id, i.role) for i in dbs.query(CollectionUserRole).filter( 
            CollectionUserRole.collection_id==cid))
    count_doc = dbs.query(Document.id).filter(Document.collection_id==cid).count()
    count_trs = dbs.query(Transmission.id).filter(Transmission.collection_id==cid).count()
    source = {}
    if c.source_id:
        s = dbs.query(Source).filter(Source.id==c.source_id).scalar()
        source.update(s.source_details)
        source.update(c.source_details or {})
        source["type"] = s.source_type
    return {"title":c.title,
            "source":source or None,
            "roles":roles,
            "count_documents":count_doc,
            "count_transmissions":count_trs}

def get_collection_documents(req):
    cid = req.context.id
    return [{"id":i.id,
             "title":i.title,
             "modified":i.modified,
             "source":i.source}
            for i in DBSession().query(Document).filter(Document.collection_id==cid)]

def search_collections(req):
    userid = req.GET.get("user_id")
    info = req.GET.get("info")
    if userid:
        r = DBSession().query(CollectionUserRole).filter(
            CollectionUserRole.user_id==int_required(userid))
        return [{"id":x.collection_id,
                 "title":x.collection.title,
                 "role":x.role}
                for x in r]
    elif info == "total_num":
        return {"total_num": DBSession().query(Collection.id).count()}
    elif info == "max_id":
        return {"max_id": DBSession().query(func.max(Collection.id)).scalar()}

def add_document(req):
    params = req.json_body
    title = params.get("title")
    source = params.get("source")
    cid = params.get("collection_id")
    modified = params.get("modified")
    if title is None:
        raise HTTPBadRequest
    if cid:
        cid = int_required(cid)
    dbs = DBSession()
    doc = Document(title, modified)
    docid = doc.id
    if source:
        doc.source = source
    if cid:
        doc.collection_id = cid
    dbs.add(doc)
    req.response.status = "201 Created"
    return {"id":docid}

def edit_document(req):
    params = req.json_body
    title = params.get("title")
    source = params.get("source")
    cid = params.get("collection_id")
    modified = params.get("modified")
    if title:
        req.context.title = title
    if cid:
        req.context.collection_id = int_required(cid)
    if modified:
        req.context.modified = int_required(modified)
    if source:
        req.context.source = source
    return Response(status="204 No Content")

def del_document(req):
    DBSession().delete(req.context)
    return Response(status="204 No Content")

def get_document(req):
    return {"title":req.context.title,
            "modified":req.context.modified,
            "source":req.context.source,
            "collection_id":req.context.collection_id}

def set_source(req):
    params = req.json_body
    cid = int_required(params.get("collection_id"))
    c = DBSession().query(Collection).filter(Collection.id==cid).scalar()
    if c.source_id and (params.get("force") is not True):
        raise HTTPForbidden
    c.source_id = req.context.id
    return Response(status="204 No Content")

def add_transmission(req):
    d = req.json_body
    DBSession().add(Transmission(req.context.id, d["type"], d["description"], d["params"]))
    return Response(status="204 No Content")

def get_collection_transmissions(req):
    return [{"id":x.id,
             "type":x.type_name,
             "description":x.description,
             "params":x.params
             } for x in DBSession().query(Transmission).filter(
            Transmission.collection_id==req.context.id)]

def get_transmission(req):
    o = DBSession().query(Transmission).filter(Transmission.id==req.matchdict["id"]).scalar()
    if not o:
        raise HTTPNotFound
    return {"type":o.type_name,
            "description":o.description,
            "params":o.params}
