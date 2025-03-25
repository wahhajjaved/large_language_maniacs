#!/usr/bin/env python3
# encoding: UTF-8

import argparse
from collections import namedtuple
import functools
import logging
import os
import sched
import sys

import ldap3
import whoosh.fields
import whoosh.index
import whoosh.qparser
import whoosh.query
import whoosh.writing

from cloudhands.common.discovery import settings

__doc__ = """
This utility collects data from an LDAP server and indexes it for local
search. The operation may be scheduled to occur regularly by supplying a
time interval.

Simple queries are also possible for testing and administration purposes.
"""

DFLT_IX = "cloudhands.wsh"

ldap_types = {
    "cn": whoosh.fields.ID(stored=True),
    "gecos": whoosh.fields.TEXT(stored=True),
    "uid": whoosh.fields.KEYWORD(stored=True),
    "uidNumber": whoosh.fields.NUMERIC(stored=True),
    "gidNumber": whoosh.fields.KEYWORD(stored=True),
    "sshPublicKey": whoosh.fields.STORED(),
}

Person = namedtuple(
    "PeopleType",
    ["designator", "uid", "gids", "description", "keys"]
)

def create(path, **kwargs):
    log = logging.getLogger("cloudhands.web.indexer.create")
    schema = whoosh.fields.Schema(
        id=whoosh.fields.ID(stored=True), **kwargs)
    whoosh.index.create_in(path, schema=schema)
    return indexer(path)


def indexer(path):
    return whoosh.index.open_dir(path)


def people(path, query, field="gecos"):
    log = logging.getLogger("cloudhands.web.indexer.people")
    ix = indexer(path)
    qp = whoosh.qparser.QueryParser(
        field, schema=ix.schema, termclass=whoosh.query.FuzzyTerm)
    q = qp.parse(query)
    results = []
    with ix.searcher() as searcher:
        log.debug("Searching {} records".format(searcher.doc_count()))
        try:
            results = searcher.search(q, limit=20)
        except IndexError as e:
            log.debug(e)
        else:
            log.debug(
                "Got {} hit{}".format(
                    results.estimated_length(),
                    "s" if results.estimated_length() > 1 else ""))
        for r in results:
            try:
                uid = r.get("uidNumber", None)
                gids = [i for i in r.get("gidNumber", "").split("\n") if i]
                keys = [i for i in r.get("sshPublicKey", "").split("\n") if i]
                yield Person(r["id"], uid, gids, r.get(field, ""), keys)
            except KeyError:
                continue


def ingest(args, config, loop=None):
    log = logging.getLogger("cloudhands.web.indexer.ingest")

    ix = create(
        args.index, 
        **{k: v for k, v in ldap_types.items()
        if config.getboolean("ldap.attributes", k)})

    s = ldap3.server.Server(
        config["ldap.search"]["host"],
        port=int(config["ldap.search"]["port"]),
        getInfo=ldap3.GET_ALL_INFO)
    c = ldap3.connection.Connection(
        s, autoBind=True, clientStrategy=ldap3.STRATEGY_SYNC)

    search = functools.partial(
        c.search,
        config["ldap.search"]["query"], config["ldap.search"]["filter"],
        ldap3.SEARCH_SCOPE_WHOLE_SUBTREE,
        attributes=[k for k, v in config["ldap.attributes"].items() if v])

    def pager(size=128):
        cookie = True
        result = search(pagedSize=size)
        yield from c.response
        while result and cookie:
            cookie = c.result["controls"]["1.2.840.113556.1.4.319"]["value"]["cookie"]
            result = search(pagedSize=size, pagedCookie=cookie)
            yield from c.response

    writer = ix.writer()
    log.info("Indexing fields " + ", ".join(ix.schema.names()))
    for n, i in enumerate(pager()):
        writer.add_document(
            id=i["dn"],
            **{k: '\n'.join(v) if v else None for k, v in i["attributes"].items()})
    log.info("Indexed {} records".format(n))
    writer.commit(mergetype=whoosh.writing.CLEAR)

    c.unbind()
    if loop is not None:
        log.debug("Rescheduling {}s later".format(args.interval))
        loop.enter(args.interval, 0, index, (args, config, loop))
    return n


def main(args):
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s|%(message)s")
    provider, config = next(iter(settings.items()))
    loop = sched.scheduler()

    try:
        os.mkdir(args.index)
    except OSError:
        pass

    if args.query is not None:
        for p in people(args.index, args.query):
            print(p)
        return 0

    if args.interval is None:
        return 0 if ingest(args, config) > 0 else 1
    else:
        loop.enter(args.interval, 0, ingest, (args, config, loop))
        loop.run()
        return 1


def parser(descr=__doc__):
    rv = argparse.ArgumentParser(description=descr)
    rv.add_argument(
        "--version", action="store_true", default=False,
        help="Print the current version number")
    rv.add_argument(
        "-v", "--verbose", required=False,
        action="store_const", dest="log_level",
        const=logging.DEBUG, default=logging.INFO,
        help="Increase the verbosity of output")
    rv.add_argument(
        "--index", default=DFLT_IX,
        help="Set the path to the index directory [{}]".format(DFLT_IX))
    rv.add_argument(
        "--interval", default=None, type=int,
        help="Set the indexing interval (s)")
    rv.add_argument(
        "--query", default=None,
        help="Issue a query and then exit")
    return rv


def run():
    p = parser()
    args = p.parse_args()
    rv = main(args)
    sys.exit(rv)

if __name__ == "__main__":
    run()
