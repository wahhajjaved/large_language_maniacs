import os, sys, csv, yaml
import logging
# debug
import warnings
from urlparse import urlparse
from csv import DictReader, Sniffer
from itertools import groupby
from operator import itemgetter
from StringIO import StringIO
from requests import get, exceptions
from datetime import datetime
from dateutil.tz import tzoffset
from unidecode import unidecode
from feeds import extract_feed_links, get_first_working_feed_link
import feedparser
from app import db, app, Project, Organization, Story, Event, Error, Issue, Label, is_safe_name
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

# debug
warnings.filterwarnings('error')

# Org sources can be csv or yaml
# They should be lists of organizations you want included at /organizations
# columns should be name, website, events_url, rss, projects_list_url, city, latitude, longitude, type
ORG_SOURCES = 'org_sources.csv'

if 'GITHUB_TOKEN' in os.environ:
    github_auth = (os.environ['GITHUB_TOKEN'], '')
else:
    github_auth = None

if 'MEETUP_KEY' in os.environ:
    meetup_key = os.environ['MEETUP_KEY']
else:
    meetup_key = None

github_throttling = False

def get_github_api(url, headers=None):
    '''
        Make authenticated GitHub requests.
    '''
    logging.info('Asking Github for ' + url)

    got = get(url, auth=github_auth, headers=headers)

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

def get_organizations(org_sources):
    ''' Collate all organizations from different sources.
    '''
    organizations = []
    with open(org_sources) as file:
        for org_source in file.read().splitlines():
            if 'docs.google.com' in org_source:
                organizations.extend(get_organizations_from_spreadsheet(org_source))
            if '.yml' in org_source:
                # Only case is GitHub government list
                organizations.extend(get_organizations_from_government_github_com(org_source))

    return organizations

def get_organizations_from_spreadsheet(org_source):
    '''
        Get a row for each organization from the Brigade Info spreadsheet.
        Return a list of dictionaries, one for each row past the header.
    '''
    got = get(org_source)

    #
    # Requests response.text is a lying liar, with its UTF8 bytes as unicode()?
    # Use response.content to plain bytes, then decode everything.
    #
    organizations = list(DictReader(StringIO(got.content)))

    for (index, org) in enumerate(organizations):
        organizations[index] = dict([(k.decode('utf8'), v.decode('utf8'))
                                     for (k, v) in org.items()])

    return organizations

def get_organizations_from_government_github_com(org_source):
    ''' Get a row for each organization from government.github.com.

    That GitHub site is a useful resource and index of government organisations
    across the world that have organization profiles on GitHub.
    '''
    got = get(org_source)
    org_list = yaml.load(got.content)
    organizations = []
    for group in org_list:
        for org in org_list[group]:
            org = {'name': org, 'projects_list_url': 'https://github.com/' + org, 'type': 'government', 'city': group}
            organizations.append(org)

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
    return [dict(title=e.title, link=e.link, type=u'blog', organization_name=organization.name)
            for e in d.entries[:2]]

def get_adjoined_json_lists(response, headers=None):
    ''' Github uses the Link header (RFC 5988) to do pagination.

        If we see a Link header, assume we're dealing with lists
        and concat them all together.
    '''
    result = response.json()

    if type(result) is list:
        while 'next' in response.links:
            response = get_github_api(response.links['next']['url'], headers=headers)
            result += response.json()

    return result


def get_projects(organization):
    '''
        Get a list of projects from CSV, TSV, JSON, or Github URL.
        Convert to a dict.
        TODO: Have this work for GDocs.
    '''

    # If projects_list is a GitHub organization
    # Use the GitHub auth to request all the included repos.
    # Follow next page links
    _, host, path, _, _, _ = urlparse(organization.projects_list_url)
    matched = match(r'(/orgs)?/(?P<name>[^/]+)/?$', path)
    if host in ('www.github.com', 'github.com') and matched:
        projects_url = 'https://api.github.com/users/%s/repos' % matched.group('name')

        try:
            response = get_github_api(projects_url)

            # Consider any status other than 2xx an error
            if not response.status_code // 100 == 2:
                return []

            projects = get_adjoined_json_lists(response)

        except exceptions.RequestException as e:
            # Something has gone wrong, probably a bad URL or site is down.
            return []

    # Else its a csv or json of projects
    else:
        projects_url = organization.projects_list_url
        logging.info('Asking for ' + projects_url)

        try:
            response = get(projects_url)

            # Consider any status other than 2xx an error
            if not response.status_code // 100 == 2:
                return []

            # If its a csv
            if "csv" in organization.projects_list_url:
                data = response.content.splitlines()
                projects = list(DictReader(data, dialect='excel'))
                # convert all the values to unicode
                for project in projects:
                    for k, v in project.items():
                        project[k] = unicode(v)

            # Else just grab it as json
            else:
                try:
                    projects = response.json()
                except ValueError:
                    # Not a json file.
                    return []

        except exceptions.RequestException as e:
            # Something has gone wrong, probably a bad URL or site is down.
            return []

    # If projects is just a list of GitHub urls, like Open Gov Hack Night
    # turn it into a dict with
    if len(projects) and type(projects[0]) in (str, unicode):
        projects = [dict(code_url=item) for item in projects]

    # If data is list of dicts, like BetaNYC or a GitHub org
    elif len(projects) and type(projects[0]) is dict:
        for project in projects:
            project['organization_name'] = organization.name
            if "homepage" in project:
                project["link_url"] = project["homepage"]
            if "html_url" in project:
                project["code_url"] = project["html_url"]
            for key in project.keys():
                if key not in ['name','description','link_url','code_url','type','categories','organization_name']:
                    del project[key]

    # Get any updates on the projects
    projects = [update_project_info(proj) for proj in projects]

    # Drop projects with no updates
    projects = filter(None, projects)

    # Add organization names along the way.
    for project in projects:
            project['organization_name'] = organization.name

    return projects


def update_project_info(project):
    ''' Update info from Github, if it's missing.

        Modify the project in-place and return nothing.

        Complete repository project details go into extras, for example
        project details from Github can be found under "github_details".

        Github_details is specifically expected to be used on this page:
        http://opengovhacknight.org/projects.html
    '''

    def non_github_project_update_time(project):
        ''' If its a non-github project, we should check if any of the fields
            have been updated, such as the description.

            Set the last_updated timestamp.
        '''
        existing_project = db.session.query(Project).filter(Project.name == project['name']).first()

        if existing_project:
            # project gets existing last_updated
            project['last_updated'] = existing_project.last_updated

            # be ready for utf8 bites
            project['description'] = project['description'].decode('utf-8')

            # unless one of the fields has been updated
            if 'description' in project:
                if project['description'] != existing_project.description:
                    project['last_updated'] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %Z")
            if 'categories' in project:
                if project['categories'] != existing_project.categories:
                    project['last_updated'] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %Z")
            if 'type' in project:
                if project['type'] != existing_project.type:
                    project['last_updated'] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %Z")
            if 'link_url' in project:
                if project['link_url'] != existing_project.link_url:
                    project['last_updated'] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %Z")

        else:
            # Set a date when we first see a non-github project
            project['last_updated'] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %Z")

        return project

    if 'code_url' not in project:
        project = non_github_project_update_time(project)
        return project

    _, host, path, _, _, _ = urlparse(project['code_url'])

    if host != 'github.com':
        project = non_github_project_update_time(project)
        return project

    # Get the Github attributes
    if host == 'github.com':
        repo_url = 'https://api.github.com/repos' + path


        # If we've hit the GitHub rate limit, skip updating projects.
        global github_throttling
        if github_throttling:
            return project

        previous_project = db.session.query(Project).filter(Project.code_url == project['code_url']).first()
        if previous_project:
            if previous_project.last_updated:
                last_updated = datetime.strftime(previous_project.last_updated, "%a, %d %b %Y %H:%M:%S GMT")
                got = get_github_api(repo_url, headers={"If-Modified-Since": last_updated})
            else:
                # In rare cases, a project can be saved with out a last_updated.
                got = get_github_api(repo_url)

        else:
            got = get_github_api(repo_url)

        if got.status_code in range(400, 499):
            if got.status_code == 404:
                logging.error(repo_url + ' doesn\'t exist.')
                # If its a bad GitHub link, don't return it at all.
                return None
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
        # If project has not been modified, return
        elif got.status_code == 304:
            logging.info('Project %s has not been modified since last update', repo_url)
            return None

        # Save last_updated time header for future requests
        project['last_updated'] = got.headers['Last-Modified']

        all_github_attributes = got.json()
        github_details = {}
        for field in ('contributors_url', 'created_at', 'forks_count', 'homepage',
                      'html_url', 'id', 'language', 'open_issues', 'pushed_at',
                      'updated_at', 'watchers_count','name', 'description', 'stargazers_count'
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
    return project

def get_issues(org_name):
    '''
        Get github issues associated to each Organization's Projects.
    '''
    issues = []
    labels = []

    # Flush the current db session to save projects added in current run
    db.session.flush()

    # Only grab this organizations projects
    projects = db.session.query(Project).filter(Project.organization_name == org_name).all()

    # Populate issues for each project
    for project in projects:
        # Mark this projects issues for deletion
        db.session.execute(db.update(Issue, values={'keep': False}).where(Issue.project_id == project.id))

        # Get github issues api url
        _, host, path, _, _, _ = urlparse(project.code_url)
        issues_url = 'https://api.github.com/repos' + path + '/issues'

        # Ping github's api for project issues
        got = get_github_api(issues_url, headers={'If-None-Match': project.last_updated_issues})
        
        # Verify if content has not been modified since last run
        if got.status_code == 304:
            db.session.execute(db.update(Issue, values={'keep': True}).where(Issue.project_id == project.id))
            logging.info('Issues %s have not changed since last update', issues_url)

        elif not got.status_code in range(400,499):
            # Update project's last_updated_issue field
            project.last_updated_issues = unicode(got.headers['ETag'])
            db.session.add(project)

            responses = get_adjoined_json_lists(got, headers={'If-None-Match': project.last_updated_issues})

            # Save each issue in response
            for issue in responses:
                # Type check the issue, we are expecting a dictionary
                if type(issue) == type({}):
                    # Pull requests are returned along with issues. Skip them.
                    if "/pull/" in issue['html_url']:
                        continue
                    issue_dict = dict(title=issue['title'], html_url=issue['html_url'],
                                      body=issue['body'], project_id=project.id, labels=issue['labels'])
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

def save_issue(session, issue):
    '''
        Save a dictionary of issue info to the datastore session.
        Return an app.Issue instance
    '''
    # Select the current issue, filtering on title AND project_name.
    filter = Issue.title == issue['title'], Issue.project_id == issue['project_id']
    existing_issue = session.query(Issue).filter(*filter).first()

    # If this is a new issue save it
    if not existing_issue:
        new_issue = Issue(**issue)
        session.add(new_issue)
        session.commit()
    
    else:
        # Mark the existing issue for safekeeping.
        existing_issue.keep = True
        # Update existing issue details
        existing_issue.title = issue['title']
        existing_issue.body = issue['body']
        existing_issue.html_url = issue['html_url']
        existing_issue.project_id = issue['project_id']
        session.commit()

def save_labels(session, issue):
    '''
        Save labels to issues
    '''
    # Get issue from db, to get id
    filter = Issue.title == issue['title'], Issue.project_id == issue['project_id']
    existing_issue = session.query(Issue).filter(*filter).first()

    # Get list of existing label names
    existing_label_names = []
    for existing_label in existing_issue.labels:
        if existing_label.name not in existing_label_names:
            existing_label_names.append(existing_label.name)

    # Add labels to db
    for label in issue['labels']:
        # don't add duplicates
        if label["name"] not in existing_label_names:
            # add the issue id to the labels
            label["issue_id"] = existing_issue.id
            new_label = Label(**label)
            session.add(new_label)
            session.commit()


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

def main(org_name=None, org_sources=None):
    ''' Run update over all organizations. Optionally, update just one.
    '''
    # Keep a set of fresh organization names.
    organization_names = set()

    # Retrieve all organizations and shuffle the list in place.
    orgs_info = get_organizations(org_sources)
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

        # Mark everything in this organization for deletion at first.
        db.session.execute(db.update(Event, values={'keep': False}).where(Event.organization_name == org_info['name']))
        db.session.execute(db.update(Story, values={'keep': False}).where(Story.organization_name == org_info['name']))
        db.session.execute(db.update(Project, values={'keep': False}).where(Project.organization_name == org_info['name']))
        db.session.execute(db.update(Organization, values={'keep': False}).where(Organization.name == org_info['name']))

        # Empty lat longs are okay.
        if 'latitude' in org_info:
            if not org_info['latitude']:
                org_info['latitude'] = None
        if 'longitude' in org_info:
            if not org_info['longitude']:
                org_info['longitude'] = None

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
            if not meetup_key:
                logging.error("No Meetup.com key set.")
            if 'meetup.com' not in organization.events_url:
                logging.error("Only Meetup.com events work right now.")
            else:
                logging.info("Gathering all of %s's events." % organization.name)
                identifier = get_event_group_identifier(organization.events_url)
                if identifier:
                    for event in get_meetup_events(organization, identifier):
                        save_event_info(db.session, event)
                else:
                    logging.error("%s does not have a valid events url" % organization.name)

        # Get issues for all of the projects
        logging.info("Gathering all of %s's open GitHub issues." % organization.name)
        issues = get_issues(organization.name)
        for issue in issues:
            save_issue(db.session, issue)
            save_labels(db.session, issue)

        # Remove everything marked for deletion.
        db.session.query(Event).filter(not Event.keep).delete()
        db.session.query(Story).filter(not Story.keep).delete()
        db.session.query(Project).filter(not Project.keep).delete()
        db.session.query(Issue).filter(Issue.keep == False).delete()
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
    main(org_name=org_name, org_sources=ORG_SOURCES)
