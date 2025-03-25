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
from unidecode import unidecode
from feeds import extract_feed_links, get_first_working_feed_link
import feedparser
from app import db, app, Project, Organization, Story, Event, Error, Issue, is_safe_name
from urllib2 import HTTPError, URLError
from urlparse import urlparse
from random import shuffle
from argparse import ArgumentParser
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

github_throttling = False

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
                         event_url=event['event_url'],
                         start_time_notz=format_date(event['time'], event['utc_offset']),
                         created_at=format_date(event['created'], event['utc_offset']),
                         utc_offset=event['utc_offset']/1000.0)

            # Some events don't have descriptions
            if 'description' in event:
                description=event['description']

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

    #
    # Requests response.text is a lying liar, with its UTF8 bytes as unicode()?
    # Use response.content to plain bytes, then decode everything.
    #
    organizations = list(DictReader(StringIO(got.content)))

    for (index, org) in enumerate(organizations):
        organizations[index] = dict([(k.decode('utf8'), v.decode('utf8'))
                                     for (k, v) in org.items()])

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
        data = response.content.splitlines()
        dialect = Sniffer().sniff(response.content)
        #
        # Google Docs CSV output uses double quotes instead of an escape char,
        # but there's not typically a way to know that just from the dialect
        # sniffer. If we see a comma delimiter and no escapechar, then set
        # doublequote to True so that GDocs output doesn't barf.
        #
        # Code for Philly's CSV is confusing the sniffer. I suspect its the
        # fields with quoted empty strings.
        # "OpenPhillyGlobe","\"Google Earth for Philadelphia\" with open source
        # and open transit data." ","http://cesium.agi.com/OpenPhillyGlobe/",
        # "https://github.com/AnalyticalGraphicsInc/OpenPhillyGlobe","",""
        #
        if '\\' in response.content:
            dialect.escapechar = '\\'

        # Check for quoted empty strings vs doublequotes
        if ',""' not in response.content and '""' in response.content:
            dialect.doublequote = True

        projects = list(DictReader(data, dialect=dialect))

        # Decode everything to unicode objects.
        for (index, proj) in enumerate(projects):
            projects[index] = dict([(k.decode('utf8'), v.decode('utf8'))
                                         for (k, v) in proj.items()])

        # Add organization names along the way.
        for project in projects:
            project['organization_name'] = organization.name

    else:
        # Fail silently when the github url is no valid
        if type(data) != list and data['message'] == u'Not Found':
            return []

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


        # If we've hit the GitHub rate limit, skip updating projects.
        global github_throttling
        if github_throttling:
            return project

        got = get_github_api(repo_url)
        if got.status_code in range(400, 499):
            if got.status_code == 404:
                logging.error(repo_url + ' doesn\'t exist.')
                return project
            elif got.status_code == 403:
                logging.error("GitHub Rate Limit Remaining: " + str(got.headers["x-ratelimit-remaining"]))
                error_dict = {
                  "error" : 'IOError: We done got throttled by GitHub',
                  "time" : datetime.now()
                }
                new_error = Error(**error_dict)
                db.session.add(new_error)
                db.session.commit()
                github_throttling = True
                return project
            else:
              raise IOError

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

def get_issues():
    '''
        Get github issues associated to each Projects.
    '''
    issues = []

    # Flush the current db session to save projects added in current run
    db.session.flush()

    # Get all projects not currently marked for deletion
    projects = db.session.query(Project).filter(Project.keep == True).all()

    # Populate issues for each project
    for project in projects:
        # Mark this projects issues for deletion
        db.session.execute(db.update(Issue, values={'keep': False}).where(Issue.project_id == project.id))

        # Get github issues api url
        _, host, path, _, _, _ = urlparse(project.code_url)
        issues_url = 'https://api.github.com/repos' + path + '/issues'

        # Ping github's api for project issues
        got = get(issues_url, auth=github_auth)

        if not got.status_code in range(400,499):
            # Save each issue in response
            for issue in got.json():
                # Type check the issue, we are expecting a dictionary
                if type(issue) == type({}):
                    issue_dict = dict(title=issue['title'], html_url=issue['html_url'],
                                 labels=issue['labels'], body=issue['body'], project_id=project.id)
                    issues.append(issue_dict)
                else:
                    logging.error('Issue for project %s is not a dictionary', project.name)
    return issues

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

def save_issue_info(session, issue_dict):
    '''
        Save a dictionary of issue ingo to the datastore session.
        Return an app.Issue instance
    '''
    # Select the current issue, filtering on title AND project_name.
    filter = Issue.title == issue_dict['title'], Issue.project_id == issue_dict['project_id']
    existing_issue = session.query(Issue).filter(*filter).first()

    # If this is a new issue, save and return it.
    if not existing_issue:
        new_issue = Issue(**issue_dict)
        session.add(new_issue)
        return new_issue

    # Mark the existing issue for safekeeping.
    existing_issue.keep = True

    # Update existing issue details
    for (field, value) in issue_dict.items():
        setattr(existing_issue, field, value)

    # Flush existing object, to prevent a sqlalchemy.orm.exc.StaleDataError.
    session.flush()

    return existing_issue

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

def main(org_name=None, minimum_age=3*3600):
    ''' Run update over all organizations. Optionally, update just one.
    
        Also optionally, reset minimum age to trigger org update, in seconds.
    '''
    # Set a single cutoff timestamp for orgs we'll look at.
    maximum_updated = time() - minimum_age
    
    # Keep a set of fresh organization names.
    organization_names = set()

    # Retrieve all organizations and shuffle the list in place.
    orgs_info = get_organizations()
    shuffle(orgs_info)

    if org_name:
        orgs_info = [org for org in orgs_info if org['name'] == org_name]

    # Iterate over organizations and projects, saving them to db.session.
    for org_info in orgs_info:

      if not is_safe_name(org_info['name']):
          error_dict = {
            "error" : 'ValueError: Bad organization name: "%s"' % org_info['name'],
            "time" : datetime.now()
          }
          new_error = Error(**error_dict)
          db.session.add(new_error)
          db.session.commit()
          continue

      try:
        filter = Organization.name == org_info['name']
        existing_org = db.session.query(Organization).filter(filter).first()
        organization_names.add(org_info['name'])
        
        if existing_org and not org_name:
            if existing_org.last_updated > maximum_updated:
                # Skip this organization, it's been updated too recently.
                logging.info("Skipping update for {0}".format(org_info['name'].encode('utf8')))
                continue
      
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

        # Get issues for all of the projects
        logging.info("Gathering all of %s's project's issues." % organization.name)
        issues = get_issues()
        for issue_info in issues:
            save_issue_info(db.session, issue_info)

        # Remove everything marked for deletion.
        db.session.query(Event).filter(not Event.keep).delete()
        db.session.query(Story).filter(not Story.keep).delete()
        db.session.query(Project).filter(not Project.keep).delete()
        db.session.query(Issue).filter(not Issue.keep).delete()
        db.session.query(Organization).filter(not Organization.keep).delete()

      except:
        # Raise the error, get out of main(), and don't commit the transaction.
        raise

      else:
        # Commit and move on to the next organization.
        db.session.commit()

    # Stop right here if an org name was specified.
    if org_name:
        return

    # Delete any organization not found on this round.
    for bad_org in db.session.query(Organization):
        if bad_org.name in organization_names:
            continue

        db.session.execute(db.delete(Event).where(Event.organization_name == bad_org.name))
        db.session.execute(db.delete(Story).where(Story.organization_name == bad_org.name))
        db.session.execute(db.delete(Project).where(Project.organization_name == bad_org.name))
        db.session.execute(db.delete(Organization).where(Organization.name == bad_org.name))
        db.session.commit()

parser = ArgumentParser(description='''Update database from CSV source URL.''')
parser.add_argument('--name', dest='name', help='Single organization name to update.')

if __name__ == "__main__":
    args = parser.parse_args()
    org_name = args.name and args.name.decode('utf8') or ''
    main(org_name=org_name)
