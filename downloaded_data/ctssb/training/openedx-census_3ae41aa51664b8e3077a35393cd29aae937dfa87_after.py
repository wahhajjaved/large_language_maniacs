#!/usr/bin/env python
"""Automate the process of counting courses on Open edX sites."""

import asyncio
import collections
import itertools
import json
import logging
import pickle
import pprint
import re
import time
import traceback
import urllib.parse

import attr
import click
import requests
import tqdm

from census.helpers import ScrapeFail, domain_from_url
from census.html_report import html_report
from census.keys import username, password
from census.session import SessionFactory
from census.sites import Site, HashedSite, read_sites_csv, courses_and_orgs, totals, read_sites_flat
from census.site_patterns import find_site_functions

# We don't use anything from this module, it just registers all the parsers.
from census import parsers


STATS_SITE = "http://openedxstats.herokuapp.com"
UPDATE_JSON = "update.json"
SITES_CSV = "sites.csv"
SITES_PICKLE = "sites.pickle"


MAX_REQUESTS = 50
TIMEOUT = 30
USER_AGENT = "Open edX census-taker. Tell us about your site: oscm+census@edx.org"

HEADERS = {
    'User-Agent': USER_AGENT,
}

GONE_MSGS = [
    "Cannot connect to host",
    "Bad Gateway",
    "TimeoutError",
    "500",
    "503",
    "404",
    "530 get http",     # Cloudflare DNS failures
]

CERTIFICATE_MSGS = [
    "certificate verify failed",
    "CertificateError:",
]

async def parse_site(site, session_factory):
    for verify_ssl in [True, False]:
        async with session_factory.new(verify_ssl=verify_ssl) as session:
            start = time.time()
            errs = []
            for parser, args, kwargs, custom_parser in find_site_functions(site.url):
                try:
                    site.current_courses = await parser(site, session, *args, **kwargs)
                except ScrapeFail as exc:
                    site.tried.append((parser.__name__, f"{exc.__class__.__name__}: {exc}"))
                    err = str(exc) or exc.__class__.__name__
                except Exception as exc:
                    site.tried.append((parser.__name__, traceback.format_exc()))
                    err = str(exc) or exc.__class__.__name__
                else:
                    site.tried.append((parser.__name__, None))
                    if site.is_gone:
                        char = 'B'
                    else:
                        if site.current_courses == site.latest_courses:
                            char = '='
                        elif site.current_courses < site.latest_courses:
                            char = '-'
                        else:
                            char = '+'
                    break
                errs.append(err)
                if custom_parser:
                    site.custom_parser_err = True
            else:
                if verify_ssl and all(any(msg in err for msg in CERTIFICATE_MSGS) for err in errs):
                    site.ssl_err = True
                    site.tried = []
                    site.custom_parser_err = False
                    continue
                if all(any(msg in err for msg in GONE_MSGS) for err in errs):
                    site.is_gone_now = True
                    if site.is_gone:
                        char = 'X'
                    else:
                        char = 'G'
                else:
                    char = 'E'

            site.time = time.time() - start
            return char

async def run(sites, session_kwargs):
    kwargs = dict(max_requests=MAX_REQUESTS, timeout=TIMEOUT, headers=HEADERS)
    kwargs.update(session_kwargs)
    factory = SessionFactory(**kwargs)
    tasks = [asyncio.ensure_future(parse_site(site, factory)) for site in sites]
    chars = collections.Counter()
    progress = tqdm.tqdm(asyncio.as_completed(tasks), total=len(tasks))
    for completed in progress:
        char = await completed
        chars[char] += 1
        desc = " ".join(f"{c}{v}" for c, v in sorted(chars.items()))
        progress.set_description(desc)
    print()

def scrape_sites(sites, session_kwargs):
    try:
        loop = asyncio.get_event_loop()
        future = asyncio.ensure_future(run(sites, session_kwargs))
        # Some exceptions go to stderr and then to my except clause? Shut up.
        loop.set_exception_handler(lambda loop, context: None)
        loop.run_until_complete(future)
    except KeyboardInterrupt:
        pass

@click.group(help=__doc__)
def cli():
    pass

@cli.command()
@click.option('--log', 'log_level', type=str, default='info')
@click.option('--min', type=int, default=0)
@click.option('--gone', is_flag=True)
@click.option('--site', is_flag=True)
@click.option('--summarize', is_flag=True)
@click.option('--save', is_flag=True)
@click.option('--out', 'out_file', type=click.File('wb'), default=SITES_PICKLE)
@click.argument('site_patterns', nargs=-1)
def scrape(log_level, min, gone, site, summarize, save, out_file, site_patterns):
    """Visit sites and count their courses."""
    logging.basicConfig(level=log_level.upper())
    if site:
        # Exact sites provided on the command line
        sites = [Site.from_url(u) for u in site_patterns]
    else:
        # Make the list of sites we're going to scrape.
        sites = list(read_sites_csv(SITES_CSV))
        sites = [s for s in sites if s.latest_courses >= min]
        if site_patterns:
            sites = [s for s in sites if any(re.search(p, s.url) for p in site_patterns)]
        if not gone:
            sites = [s for s in sites if not s.is_gone]

    if len(sites) == 1:
        print("1 site")
    else:
        print(f"{len(sites)} sites")

    # SCRAPE!
    session_kwargs = {}
    if save:
        session_kwargs['save'] = True
    scrape_sites(sites, session_kwargs)

    if summarize:
        show_text_report(sites)
    else:
        with out_file:
            pickle.dump(sites, out_file)

@cli.command()
@click.option('--in', 'in_file', type=click.File('rb'), default=SITES_PICKLE,
              help='The sites.pickle file to read')
def summary(in_file):
    with in_file:
        sites = pickle.load(in_file)
    summarize(sites)

def summarize(sites):
    old, new = totals(sites)

    changed = sum(1 for s in sites if s.should_update())
    gone = sum(1 for s in sites if s.is_gone_now and not s.is_gone)
    back = sum(1 for s in sites if not s.is_gone_now and s.is_gone and s.current_courses)
    print(f"{len(sites)} sites")
    print(f"Courses: {old} --> {new} ({new-old:+d});   Sites: {changed} changed, {gone} gone, {back} back")

    hashed_sites = collections.defaultdict(HashedSite)
    nohash_sites = []
    for site in sites:
        if site.is_gone_now:
            continue
        if not site.current_courses:
            continue
        if site.fingerprint is None:
            hashed_site = HashedSite()
            hashed_site.sites.append(site)
            nohash_sites.append(hashed_site)
        else:
            hashed_site = hashed_sites[site.fingerprint]
            hashed_site.fingerprint = site.fingerprint
            hashed_site.sites.append(site)

    print(f"{len(nohash_sites)} with no hash, {len(hashed_sites)} with hash")
    if nohash_sites:
        print("No hash:")
        for site in nohash_sites:
            print(f" {site.best_url()}: {site.current_courses()}")
    chaff_sites = []
    not_chaff_sites = []
    for hashed_site in itertools.chain(hashed_sites.values(), nohash_sites):
        if hashed_site.all_chaff():
            chaff_sites.append(hashed_site)
        else:
            not_chaff_sites.append(hashed_site)
    print(f"Total sites: {len(not_chaff_sites)} not chaff, {len(chaff_sites)} chaff")

@cli.command()
@click.option('--in', 'in_file', type=click.File('rb'), default=SITES_PICKLE,
              help='The sites.pickle file to read')
@click.option('--out', 'out_file', type=click.File('w'), default="sites.html",
              help='The HTML file to write')
@click.option('--skip-none', is_flag=True, help="Don't include sites with no count")
@click.option('--only-new', is_flag=True, help="Only include sites we think are new")
def html(in_file, out_file, skip_none, only_new):
    """Write an HTML report."""
    with in_file:
        sites = pickle.load(in_file)

    if skip_none:
        sites = [site for site in sites if site.current_courses is not None]

    # Prep data for reporting.
    old, new = totals(sites)
    all_courses, all_orgs, all_course_ids = courses_and_orgs(sites)

    with open("course-ids.txt", "w") as f:
        f.write("".join(i + "\n" for i in sorted(all_course_ids)))

    known_domains = {domain_from_url(site.url) for site in read_sites_csv(SITES_CSV)}
    with open("aliases.txt") as aliases:
        known_domains.update(domain_from_url(line.strip()) for line in aliases)

    sites = sorted(sites, key=lambda s: s.url.split(".")[::-1])
    sites = sorted(sites, key=lambda s: s.current_courses or s.latest_courses, reverse=True)
    html_report(out_file, sites, old, new, all_courses, all_orgs, known_domains=known_domains, only_new=only_new)


@cli.command('json')
@click.option('--in', 'in_file', type=click.File('rb'), default=SITES_PICKLE)
def write_json(in_file):
    """Write the update.json file."""
    with in_file:
        sites = pickle.load(in_file)

    # Prep data for reporting.
    sites_descending = sorted(sites, key=lambda s: s.latest_courses, reverse=True)
    all_courses, all_orgs, all_course_ids = courses_and_orgs(sites)
    json_update(sites_descending, all_courses, include_overcount=True)


@cli.command()
@click.option('--log', 'log_level', type=str, default='info')
@click.option('--out', 'out_file', type=click.File('wb'), default='refsites.pickle')
@click.argument('referrer_sites', nargs=1)
def refscrape(log_level, out_file, referrer_sites):
    """Visit sites and count their courses."""
    logging.basicConfig(level=log_level.upper())
    sites = read_sites_flat(referrer_sites)
    print(f"{len(sites)} sites")

    # SCRAPE!
    scrape_sites(sites, {})

    with out_file:
        pickle.dump(sites, out_file)


@cli.command('text')
@click.option('--in', 'in_file', type=click.File('rb'), default=SITES_PICKLE,
              help='The sites.pickle file to read')
def text_report(in_file):
    """Write a text report about site scraping."""
    with in_file:
        sites = pickle.load(in_file)
    show_text_report(sites)

def show_text_report(sites):
    old, new = totals(sites)
    sites = sorted(sites, key=lambda s: s.latest_courses, reverse=True)
    print(f"Found courses went from {old} to {new}")
    for site in sites:
        print(f"{site.url}: {site.latest_courses} --> {site.current_courses} ({site.fingerprint})")
        for strategy, tb in site.tried:
            if tb is not None:
                line = tb.splitlines()[-1]
            else:
                line = "Worked"
            print(f"    {strategy}: {line}")

def json_update(sites, all_courses, include_overcount=False):
    data = {}

    site_updates = {
        s.url: {
            'old_course_count': s.latest_courses,
            'course_count': s.current_courses if s.current_courses is not None else s.latest_courses,
            'is_gone': s.is_gone_now,
        }
        for s in sites if s.should_update()
    }
    data['sites'] = site_updates

    if include_overcount:
        data['overcount'] = sum(len(s) - 1 for s in all_courses.values())

    with open(UPDATE_JSON, "w") as update_json:
        json.dump(data, update_json, indent=4)


def login(site, session):
    login_url = urllib.parse.urljoin(site, "/login/")
    resp = session.get(login_url)
    resp.raise_for_status()
    m = re.search(r"name='csrfmiddlewaretoken' value='([^']+)'", resp.text)
    if m:
        csrftoken = m.group(1)
    else:
        raise Exception(f"No CSRF token found from {login_url}")
    resp = session.post(login_url, data={'username': username, 'password': password, 'csrfmiddlewaretoken': csrftoken})
    if resp.status_code not in [200, 404]:
        resp.raise_for_status()

@cli.command()
@click.argument('site', default=STATS_SITE)
def getcsv(site):
    """Get the sites.csv file from the app."""
    with requests.Session() as s:
        login(site, s)
        csv_url = urllib.parse.urljoin(site, "/sites/csv/?complete=1")
        resp = s.get(csv_url)
        content = resp.content
        with open(SITES_CSV, "wb") as csv_file:
            csv_file.write(content)
        lines = content.splitlines()
        print(f"Wrote {len(lines)-1} sites to {SITES_CSV}")


@cli.command()
@click.argument('site', default=STATS_SITE)
def post(site):
    """Post updated numbers to the stats-collecting site."""
    with open(UPDATE_JSON) as f:
        data = f.read()

    with requests.Session() as s:
        login(site, s)
        bulk_url = urllib.parse.urljoin(site, "/sites/bulk/")
        resp = s.post(bulk_url, data=data)
        print(resp.text)


if __name__ == '__main__':
    cli()
