import os, sys
import logging
from urlparse import urlparse
from csv import DictReader, Sniffer
from itertools import groupby
from operator import itemgetter
from StringIO import StringIO
from requests import get
from datetime import datetime
from dateutil.tz import tzoffset
import requests
from feeds import extract_feed_links, get_first_working_feed_link
import feedparser
from app import db, app, Project, Organization, Story, Event, Error, is_safe_name
from urllib2 import HTTPError, URLError
from urlparse import urlparse
from random import shuffle
from time import time
from re import match

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
requests_log = logging.getLogger("requests")
requests_log.setLevel(logging.WARNING)

# Production
gdocs_url = 'https://docs.google.com/a/codeforamerica.org/spreadsheet/ccc?key=0ArHmv-6U1drqdGNCLWV5Q0d5YmllUzE5WGlUY3hhT2c&output=csv'

# Testing
# gdocs_url = "https://docs.google.com/spreadsheet/pub?key=0ArHmv-6U1drqdEVkTUtZNVlYRE5ndERLLTFDb2RqQlE&output=csv"


if 'GITHUB_TOKEN' in os.environ:
    github_auth = (os.environ['GITHUB_TOKEN'], '')
else:
    github_auth = None

meetup_key = os.environ['MEETUP_KEY']

def get_github_api(url):
    '''
        Make authenticated GitHub requests.
    '''
    logging.info('Asking Github for ' + url)

    got = get(url, auth=github_auth)

    return got

def format_date(time_in_milliseconds, utc_offset_msec):
    '''
        Create a datetime object from a time in milliseconds from the epoch
    '''
    tz = tzoffset(None, utc_offset_msec/1000.0)
    dt = datetime.fromtimestamp(time_in_milliseconds/1000.0, tz)
    return datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)

def format_location(venue):
    address = venue['address_1']
    if('address_2' in venue.keys() and venue['address_2'] != ''):
        address = address + ', ' + venue['address_2']

    if 'state' in venue:
        return "{address}, {city}, {state}, {country}".format(address=address,
                city=venue['city'], state=venue['state'], country=venue['country'])
    else:
        return "{address}, {city}, {country}".format(address=address,
                city=venue['city'], country=venue['country'])

def get_meetup_events(organization, group_urlname):
    '''
        Get events associated with a group
    '''
    meetup_url = "https://api.meetup.com/2/events?status=past,upcoming&format=json&group_urlname={0}&key={1}".format(group_urlname, meetup_key)
    got = get(meetup_url)
    if got.status_code == 404:
        logging.error("%s's meetup page cannot be found" % organization.name)
        return []
    else:
        results = got.json()['results']
        events = []
        for event in results:
            event = dict(organization_name=organization.name,
                         name=event['name'],
                         description=event['description'],
                         event_url=event['event_url'],
                         start_time_notz=format_date(event['time'], event['utc_offset']),
                         created_at=format_date(event['created'], event['utc_offset']),
                         utc_offset=event['utc_offset']/1000.0)

            # Some events don't have locations.
            if 'venue' in event:
                event['location'] = format_location(event['venue'])

            events.append(event)
        return events

def get_organizations():
    '''
        Get a row for each organization from the Brigade Info spreadsheet.
        Return a list of dictionaries, one for each row past the header.
    '''
    got = get(gdocs_url)
    organizations = list(DictReader(StringIO(got.text.decode('utf8'))))

    return organizations

def get_stories(organization):
    '''
        Get two recent stories from an rss feed.
    '''
    # If there is no given rss link, try the website url.
    if organization.rss:
        rss = organization.rss
    else:
        rss = organization.website
    try:
        url = get_first_working_feed_link(rss)

        # If no blog found then give up
        if not url:
            url = None
            return None

    except (HTTPError, ValueError, URLError):
        url = None
        return None

    logging.info('Asking cyberspace for ' + url)
    d = feedparser.parse(get(url).text)
    
    #
    # Return dictionaries for the two most recent entries.
    #
    return [dict(title=e.title, link=e.link, type="blog", organization_name=organization.name)
            for e in d.entries[:2]]

def get_adjoined_json_lists(response):
    ''' Github uses the Link header (RFC 5988) to do pagination.

        If we see a Link header, assume we're dealing with lists
        and concat them all together.
    '''
    result = response.json()

    if type(result) is list:
        while 'next' in response.links:
            response = get(response.links['next']['url'])
            result += response.json()

    return result

def get_projects(organization):
    '''
        Get a list of projects from CSV, TSV, JSON, or Github URL.
        Convert to a dict.
        TODO: Have this work for GDocs.
    '''
    _, host, path, _, _, _ = urlparse(organization.projects_list_url)
    matched = match(r'(/orgs)?/(?P<name>[^/]+)/?$', path)

    if host in ('www.github.com', 'github.com') and matched:
        projects_url = 'https://api.github.com/users/%s/repos' % matched.group('name')
    else:
        projects_url = organization.projects_list_url

    logging.info('Asking for ' + projects_url)
    response = get(projects_url)

    try:
        data = get_adjoined_json_lists(response)

    except ValueError:
        # If projects_list_url is a type of csv
        data = response.text.splitlines()
        dialect = Sniffer().sniff(data[0])
        
        #
        # Google Docs CSV output uses double quotes instead of an escape char,
        # but there's not typically a way to know that just from the dialect
        # sniffer. If we see a comma delimiter and no escapechar, then set
        # doublequote to True so that GDocs output doesn't barf.
        #
        if dialect.delimiter == ',' and dialect.doublequote is False and dialect.escapechar is None:
            dialect.doublequote = True
        
        projects = list(DictReader(data, dialect=dialect))
        for project in projects:
            project['organization_name'] = organization.name

    else:
        # If projects_list_url is a json file
        if len(data) and type(data[0]) in (str, unicode):
            # Likely that the JSON data is a simple list of strings
            projects = [dict(organization_name=organization.name, code_url=item)
                        for item in data]

        elif len(data) and type(data[0]) is dict:
            # Map data to name, description, link_url, code_url (skip type, categories)
            projects = [dict(name=p['name'], description=p['description'],
                             link_url=p['homepage'], code_url=p['html_url'],
                             organization_name=organization.name)
                        for p in data]

        elif len(data):
            raise Exception('Unknown type for first project: "%s"' % repr(type(data[0])))

        else:
            projects = []

    map(update_project_info, projects)

    return projects

def update_project_info(project):
    ''' Update info from Github, if it's missing.

        Modify the project in-place and return nothing.

        Complete repository project details go into extras, for example
        project details from Github can be found under "github_details".

        Github_details is specifically expected to be used on this page:
        http://opengovhacknight.org/projects.html
    '''
    if 'code_url' not in project:
        return project

    _, host, path, _, _, _ = urlparse(project['code_url'])

    # Get the Github attributes
    if host == 'github.com':
        repo_url = 'https://api.github.com/repos' + path

        got = get_github_api(repo_url)
        if got.status_code in range(400, 499):
            if got.status_code == 404:
                logging.error(repo_url + ' doesn\'t exist.')
                return project
            if got.status_code == 403:
                logging.error("GitHub Rate Limit Remaining: " + got.headers["x-ratelimit-remaining"])
            raise IOError('We done got throttled')

        all_github_attributes = got.json()
        github_details = {}
        for field in ('contributors_url', 'created_at', 'forks_count', 'homepage',
                      'html_url', 'id', 'language', 'open_issues', 'pushed_at',
                      'updated_at', 'watchers_count','name', 'description'
                     ):
            github_details[field] = all_github_attributes[field]

        github_details['owner'] = dict()

        for field in ('avatar_url', 'html_url', 'login', 'type'):
            github_details['owner'][field] = all_github_attributes['owner'][field]

        project['github_details'] = github_details

        if 'name' not in project or not project['name']:
            project['name'] = all_github_attributes['name']

        if 'description' not in project or not project['description']:
            project['description'] = all_github_attributes['description']

        if 'link_url' not in project or not project['link_url']:
            project['link_url'] = all_github_attributes['homepage']

        #
        # Populate project contributors from github_details[contributors_url]
        #
        project['github_details']['contributors'] = []
        got = get_github_api(all_github_attributes['contributors_url'])

        # Check if there are contributors
        try:
            for contributor in got.json():
                # we don't want people without email addresses?
                if contributor['login'] == 'invalid-email-address':
                    break

                project['github_details']['contributors'].append(dict())

                for field in ('login', 'url', 'avatar_url', 'html_url', 'contributions'):
                    project['github_details']['contributors'][-1][field] = contributor[field]

                # flag the owner with a boolean value
                project['github_details']['contributors'][-1]['owner'] \
                    = bool(contributor['login'] == project['github_details']['owner']['login'])
        except:
            pass

        #
        # Populate project participation from github_details[url] + "/stats/participation"
        # Sometimes GitHub returns a blank dict instead of no participation.
        #
        got = get_github_api(all_github_attributes['url'] + '/stats/participation')
        try:
            project['github_details']['participation'] = got.json()['all']
        except:
            project['github_details']['participation'] = [0] * 50

        #
        # Populate project needs from github_details[issues_url] (remove "{/number}")
        #
        project['github_details']['project_needs'] = []
        url = all_github_attributes['issues_url'].replace('{/number}', '')
        got = get(url, auth=github_auth, params=dict(labels='project-needs'))

        # Check if GitHub Issues are disabled
        if all_github_attributes['has_issues']:
            for issue in got.json():
                project_need = dict(title=issue['title'], issue_url=issue['html_url'])
                project['github_details']['project_needs'].append(project_need)

def reformat_project_info_for_chicago(all_projects):
    ''' Return a clone of the project list, formatted for use by opengovhacknight.org.

        The representation here is specifically expected to be used on this page:
        http://opengovhacknight.org/projects.html

        See discussion at
        https://github.com/codeforamerica/civic-json-worker/issues/18
    '''
    return [project['github_details'] for project in all_projects]

def count_people_totals(all_projects):
    ''' Create a list of people details based on project details.

        Request additional data from Github API for each person.

        See discussion at
        https://github.com/codeforamerica/civic-json-worker/issues/18
    '''
    users, contributors = [], []
    for project in all_projects:
        contributors.extend(project['contributors'])

    #
    # Sort by login; there will be duplicates!
    #
    contributors.sort(key=itemgetter('login'))

    #
    # Populate users array with groups of contributors.
    #
    for (_, _contributors) in groupby(contributors, key=itemgetter('login')):
        user = dict(contributions=0, repositories=0)

        for contributor in _contributors:
            user['contributions'] += contributor['contributions']
            user['repositories'] += 1

            if 'login' in user:
                continue

            #
            # Populate user hash with Github info, if it hasn't been already.
            #
            got = get_github_api(contributor['url'])
            contributor = got.json()

            for field in (
                    'login', 'avatar_url', 'html_url',
                    'blog', 'company', 'location'
                    ):
                user[field] = contributor.get(field, None)

        users.append(user)

    return users

def save_organization_info(session, org_dict):
    ''' Save a dictionary of organization info to the datastore session.

        Return an app.Organization instance.
    '''
    if not is_safe_name(org_dict['name']):
        error_dict = {
          "error" : 'ValueError: Bad organization name: "%(name)s"' % org_dict,
          "time" : datetime.now()
        }
        new_error = Error(**error_dict)
        session.add(new_error)
        session.commit()
        raise ValueError('Bad organization name: "%(name)s"' % org_dict)

    # Select an existing organization by name.
    filter = Organization.name == org_dict['name']
    existing_org = session.query(Organization).filter(filter).first()

    # If this is a new organization, save and return it.
    if not existing_org:
        new_organization = Organization(**org_dict)
        session.add(new_organization)
        # session.commit()
        return new_organization

    # Mark the existing organization for safekeeping
    existing_org.last_updated = time()
    existing_org.keep = True

    # Update existing organization details.
    for (field, value) in org_dict.items():
        setattr(existing_org, field, value)

    # Flush existing object, to prevent a sqlalchemy.orm.exc.StaleDataError.
    session.flush()

    return existing_org

def save_project_info(session, proj_dict):
    ''' Save a dictionary of project info to the datastore session.

        Return an app.Project instance.
    '''
    # Select the current project, filtering on name AND organization.
    filter = Project.name == proj_dict['name'], Project.organization_name == proj_dict['organization_name']
    existing_project = session.query(Project).filter(*filter).first()

    # If this is a new project, save and return it.
    if not existing_project:
        new_project = Project(**proj_dict)
        session.add(new_project)
        return new_project

    # Mark the existing project for safekeeping.
    existing_project.keep = True

    # Update existing project details
    for (field, value) in proj_dict.items():
        setattr(existing_project, field, value)

    # Flush existing object, to prevent a sqlalchemy.orm.exc.StaleDataError.
    session.flush()

    return existing_project

def save_event_info(session, event_dict):
    '''
        Save a dictionary of event into to the datastore session then return
        that event instance
    '''
    # Select the current event, filtering on event_url and organization.
    filter = Event.event_url == event_dict['event_url'], \
             Event.organization_name == event_dict['organization_name']
    existing_event = session.query(Event).filter(*filter).first()

    # If this is a new event, save and return it.
    if not existing_event:
        new_event = Event(**event_dict)
        session.add(new_event)
        return new_event

    # Mark the existing event for safekeeping.
    existing_event.keep = True

    # Update existing event details
    for (field, value) in event_dict.items():
        setattr(existing_event, field, value)

    # Flush existing object, to prevent a sqlalchemy.orm.exc.StaleDataError.
    session.flush()

def save_story_info(session, story_dict):
    '''
        Save a dictionary of story into to the datastore session then return
        that story instance
    '''
    filter = Story.organization_name == story_dict['organization_name'], \
             Story.link == story_dict['link']

    existing_story = session.query(Story).filter(*filter).first()
    
    # If this is a new story, save and return it.
    if not existing_story:
        new_story = Story(**story_dict)
        session.add(new_story)
        return new_story
    
    # Mark the existing story for safekeeping.
    existing_story.keep = True

    # Update existing story details
    for (field, value) in story_dict.items():
        setattr(existing_story, field, value)

    # Flush existing object, to prevent a sqlalchemy.orm.exc.StaleDataError.
    session.flush()

def get_event_group_identifier(events_url):
    parse_result = urlparse(events_url)
    url_parts = parse_result.path.split('/')
    identifier = url_parts.pop()
    if not identifier:
        identifier = url_parts.pop()
    if(match('^[A-Za-z0-9-]+$', identifier)):
        return identifier
    else:
        return None

def main():
    # Keep a set of fresh organization names.
    organization_names = set()
    
    # Retrieve all organizations and shuffle the list in place.
    orgs_info = get_organizations()
    shuffle(orgs_info)
    
    # Iterate over organizations and projects, saving them to db.session.
    for org_info in orgs_info:
    
      try:
        # Mark everything in this organization for deletion at first.
        db.session.execute(db.update(Event, values={'keep': False}).where(Event.organization_name == org_info['name']))
        db.session.execute(db.update(Story, values={'keep': False}).where(Story.organization_name == org_info['name']))
        db.session.execute(db.update(Project, values={'keep': False}).where(Project.organization_name == org_info['name']))
        db.session.execute(db.update(Organization, values={'keep': False}).where(Organization.name == org_info['name']))
        
        organization = save_organization_info(db.session, org_info)
        organization_names.add(organization.name)

        if organization.rss or organization.website:
            logging.info("Gathering all of %s's stories." % organization.name)
            stories = get_stories(organization)
            if stories:
                for story_info in stories:
                    save_story_info(db.session, story_info)

        if organization.projects_list_url:
            logging.info("Gathering all of %s's projects." % organization.name)
            projects = get_projects(organization)
            for proj_info in projects:
                save_project_info(db.session, proj_info)

        if organization.events_url:
            logging.info("Gathering all of %s's events." % organization.name)
            identifier = get_event_group_identifier(organization.events_url)
            if identifier:
                for event in get_meetup_events(organization, identifier):
                    save_event_info(db.session, event)
            else:
                logging.error("%s does not have a valid events url" % organization.name)

        # Remove everything marked for deletion.
        db.session.execute(db.delete(Event).where(Event.keep == False))
        db.session.execute(db.delete(Story).where(Story.keep == False))
        db.session.execute(db.delete(Project).where(Project.keep == False))
        db.session.execute(db.delete(Organization).where(Organization.keep == False))
        
      except:
        # Raise the error, get out of main(), and don't commit the transaction.
        raise
      
      else:
        # Commit and move on to the next organization.
        db.session.commit()
    
    # Delete any organization not found on this round.
    for bad_org in db.session.query(Organization):
        if bad_org.name in organization_names:
            continue
    
        db.session.execute(db.delete(Event).where(Event.organization_name == bad_org.name))
        db.session.execute(db.delete(Story).where(Story.organization_name == bad_org.name))
        db.session.execute(db.delete(Project).where(Project.organization_name == bad_org.name))
        db.session.execute(db.delete(Organization).where(Organization.name == bad_org.name))
        db.session.commit()

if __name__ == "__main__":
    main()
