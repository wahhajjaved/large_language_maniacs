#!bin/python
# Script to read an email template, either directly or as a JSON bundle,
# and send that bundle to a CiviCRM instance running remotely. JSON bundle
# data can be read from a local file or from a web service via a supplied
# URL.
#
# Written: August 2014 Ruth Ivimey-Cook
#

from __future__ import print_function
import sys
import os
import argparse
import json
import html2text
import requests

# basedir points to the parent dir of mailcivi, and pythoncivicrm
# is installed alongside mailcivi.
basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.sys.path.insert(0, os.path.join(basedir, 'python-civicrm'))

from pythoncivicrm import (CiviCRM, CivicrmError)


def debugmsg(settings, *objs):
    """
    Print additional info to stderr iff the verbose flag has been enabled
    """
    if settings.verbose > 1:
        print("DEBUG: ", *objs, end='\n', file=sys.stderr)


def infomsg(settings, *objs):
    """
    Print additional info to stderr iff the verbose flag has been enabled
    """
    if settings.verbose:
        print("INFO: ", *objs, end='\n', file=sys.stderr)


def warningmsg(settings, *objs):
    """
    Print warning message to stderr
    """
    print("WARNING: ", *objs, end='\n', file=sys.stderr)


def errormsg(settings, *objs):
    """
    Print error message to stderr
    """
    print("ERROR: ", *objs, end='\n', file=sys.stderr)


class CiviMailTemplate:
    """
    Mail template object, filled out by readjson() and readlocal(),
    to hold the intermediate form of the input email.
    """
    pass


def getoptions():
    """
    Use the Python argparse module to read in the command line args
    """
    parser = argparse.ArgumentParser(
        prog='mailcivi',
        description='Create a new mail template in a remote CiviCRM installation.',
        usage='%(prog)s [options] [--creator_id=id | --creator=name] (--recipient=n | --recipient_id=n ) (--json=file|--html=file) [--text=file]'
    )
    parser.add_argument('--verbose', '-v',
                        action='count',
                        help='Print additional messages to stderr',
                        default=0)
    parser.add_argument('--civicrm',
                        help='URL of the CiviCRM module on the destination site.',
                        default='http://crm.example.org/sites/all/modules/civicrm')
    parser.add_argument('--sitekey',
                        help='The CiviCRM site_key of the site you are connecting to.',
                        default='')
    parser.add_argument('--apikey',
                        help='The CiviCRM api key.',
                        default='')
    parser.add_argument('--name',
                        help='Name of new mail template. Overrides a name specified by file.')
    parser.add_argument('--subject',
                        help='Email subject text. Overrides a subject specified by file.')
    parser.add_argument('--from_email',
                        help='Email sender address; overrides creator details. e.g. "joe@example.com".')
    parser.add_argument('--from_name',
                        help='Email Name for source of the email; overrides creator details. e.g. "Joe"')

    parser.add_argument('--action',
                        choices=['disable', 'create', 'send'],
                        default='create',
                        help='What to do with the mail: nothing at all, upload it, or upload and send.')

    creatgroup = parser.add_mutually_exclusive_group(required=False)
    creatgroup.add_argument('--creator_id',
                            help='CiviCRM Contact ID number of template creator, e.g. "5".')
    creatgroup.add_argument('--creator',
                            help='CiviCRM Contact Name of template creator, e.g. "Joe Bloggs".')

    destgroup = parser.add_mutually_exclusive_group(required=False)
    destgroup.add_argument('--recipient_id',
                           help='Group ID for recipient group of the email. e.g. "16".')
    destgroup.add_argument('--recipient',
                           help='Group title for recipient group of the email. e.g. "Contacts"')

    inputgroup = parser.add_mutually_exclusive_group(required=True)
    inputgroup.add_argument('--json', nargs='?',
                            type=argparse.FileType('r'),
                            dest='jsonfile',
                            help='File containing the templated email as JSON.')
    inputgroup.add_argument('--url', nargs='?',
                            dest='jsonurl',
                            help='URL from which to fetch the templated email as JSON.')
    inputgroup.add_argument('--html', nargs='?',
                            type=argparse.FileType('r'),
                            dest='htmlfile',
                            help='File containing the templated HTML to email.')
    parser.add_argument('--text',
                        type=argparse.FileType('r'),
                        dest='textfile',
                        help='File containing the templated Text to email. If'
                             ' not supplied, the html version is rendered using'
                             ' html2text.')
    args = parser.parse_args()

    return args


def readjson(settings, civicrm, jsontemplate):
    """
    Read the necesary input data for the mail template into the
    result, where metadata from the command line (seen in the
    global settings) overrides json-supplied data.

    :param settings: The command line settings object.
    :param jsontemplate: The JSON-derived input.
    :return: an object containing the data to send
    """
    result = CiviMailTemplate()
    result.name = jsontemplate['name']
    result.subject = jsontemplate['subject']
    result.from_email = jsontemplate['from_email']
    result.from_name = jsontemplate['from_name']

    if 'creator' in jsontemplate:
        result.creator_id = creator_id_from_name(settings, civicrm, jsontemplate['creator'])
    elif 'creator_id' in jsontemplate:
        result.creator_id = jsontemplate['creator_id']

    if 'recipient' in jsontemplate:
        result.recipient_id = group_id_from_title(settings, civicrm, jsontemplate['recipient'])
    elif 'recipient_id' in jsontemplate:
        result.recipient_id = jsontemplate['recipient_id']

    if 'action' in jsontemplate:
        result.action = jsontemplate['action']
    else:
        result.action = 'create'

    result.html = jsontemplate['html']
    if 'plain' in jsontemplate:
        result.plain = jsontemplate['plain']
    else:
        result.plain = getplaintext(result.html)

    # Now enable the command line to override these settings.
    if settings.name > '':
        result.name = settings.name
    if settings.subject > '':
        result.subject = settings.subject

    if settings.creator_id > '':
        result.creator_id = settings.creator_id
    elif settings.creator > '':
        result.creator_id = creator_id_from_name(settings.creator)

    if settings.from_email > '':
        result.from_email = settings.from_email
    if settings.from_name > '':
        result.from_name = settings.from_name

    if settings.recipient_id > '':
        result.recipient_id = settings.recipient_id
    elif settings.recipient > '':
        result.recipient_id = group_id_from_title(settings, civicrm, settings.recipient)

    if settings.action > '':
        result.action = settings.action

    return result


def readlocal(settings, civicrm):
    """
    Read the necesary input data for the mail template into the
    result, where metadata from the command line (seen in the
    global settings) overrides json-supplied data.

    :param settings: The command line settings object.
    :return: an object containing the data to send
    """
    result = CiviMailTemplate()
    result.name = settings.name
    result.subject = settings.subject

    if settings.creator_id > '':
        result.creator_id = settings.creator_id
    elif settings.creator_name > '':
        result.creator_id = creator_id_from_name(settings, civicrm, settings.creator_name)

    result.from_email = settings.from_email
    result.from_name = settings.from_name

    if settings.recipient_id > '':
        result.recipient_id = settings.recipient_id
    elif settings.recipient_name > '':
        result.recipient_id = group_id_from_title(settings, civicrm, settings.recipient_name)

    result.action = settings.action
    result.html = settings.htmlfile.read()
    if settings.textfile:
        result.plain = settings.textfile.read()
    else:
        result.plain = getplaintext(result.html)

    return result


def fetch_url(jsonurl):
    """
    Read a JSON template for the email by fetching the URL provided.

    :param jsonurl: A URL that resolves to return application/json data.
    :return: The returned JSON content, or the null-json '{}'
    """
    r = requests.get(jsonurl)
    if r.status_code == 200 and r.headers['content-type'].startswith('application/json'):
        # Should be this instead? return r.text.encode('utf8')
        return r.text
    else:
        raise Exception('Failed to fetch JSON: ' + str(r.status_code))


def getplaintext(html):
    """
    Return a reasonable plain-text version of the HTML input.

    :param html: string containing HTML input text.
    :return: string containing plain-text equivalent.
    """
    return html2text.html2text(html)


def connect_to_civi(settings):
    """
    Create a new CiviCRM object from the values in 'settings'.

    :param settings: The command line settings object.
    :return:
    """
    civicrm = CiviCRM(settings.civicrm, site_key=settings.sitekey,
                      api_key=settings.apikey, use_ssl=False)
    return civicrm


def check_creator_exists(settings, civicrm, creator_id):
    """
    Check that creator_id is a valid CiviCRM user.

    :param settings: The command line settings object.
    :param civicrm: Object used to talk to the CiviCRM api.
    :param creator_id: A Civicrm userid.
    :return: Boolean - True if the userid exists in CiviCRM as a user.
    """
    params = {
        u'contact_id': creator_id,
    }
    try:
        contactresults = civicrm.get(u'Contact', **params)

    except CivicrmError as e:
        print(u'Contact check failed: ' + e.message)
        return False

    if False != contactresults and len(contactresults) == 1:
        infomsg(settings, u'Creator is ', contactresults[0][u'sort_name'])
        return True
    else:
        warningmsg(settings, u'Creator id was not found in CiviCRM.')
        return False


def creator_id_from_name(settings, civicrm, creator_name):
    """
    Check that is a valid CiviCRM user, and return its ID.

    :param settings: The command line settings object.
    :param civicrm: Object used to talk to the CiviCRM api.
    :param creator_name: A Civicrm userid.
    :return: Boolean - The user ID if the user exists in CiviCRM,
        or False otherwise.
    """
    params = {
        u'display_name': creator_name,
    }
    try:
        contactresults = civicrm.get(u'Contact', **params)

    except CivicrmError as e:
        print(u'Contact search failed: ' + e.message)
        return False

    if False != contactresults and len(contactresults) == 1:
        infomsg(settings, u'Creator id is ', contactresults[0][u'contact_id'])
        return contactresults[0][u'contact_id']
    else:
        warningmsg(settings, u'Creator id was not found or not unique in CiviCRM.')
        return False


def group_id_from_title(settings, civicrm, group_title):
    """
    Check that group is a valid CiviCRM group, and return its ID.

    :param settings: The command line settings object.
    :param civicrm: Object used to talk to the CiviCRM api.
    :param group_title: A (unique) Civicrm group title.
    :return: Boolean - The group ID if the group exists in CiviCRM,
        or False otherwise.
    """
    params = {
        u'title': group_title,
    }
    try:
        contactresults = civicrm.get(u'Group', **params)

    except CivicrmError as e:
        print(u'GroupID search failed: ' + e.message)
        return False

    if False != contactresults and len(contactresults) == 1:
        infomsg(settings, u'Group id is ', contactresults[0][u'id'])
        return contactresults[0][u'id']
    else:
        warningmsg(settings, u'Group title was not found or not unique in CiviCRM.')
        return False


def create_template(settings, civicrm, template, groupids, enable_mailingjob):
    """
    Send the email defined by the template to the CiviCRM instance.

    :param settings: The command line settings object.
    :param civicrm: Object defining a CiviCRM instance.
    :param template: Array defining the template mail.
    """

    # parameters that will be put in the http request.
    params = {
        u'name': template.name,
        u'subject': template.subject,
        u'created_id': template.creator_id,
        u'api.mailing_job.create': 0
    }

    # parameters that are json-encoded into the request.
    config = {
        u'from_email': template.from_email,
        u'from_name': template.from_name,
        u'body_html': template.html,
        u'body_text': template.plain,
        u'url_tracking': u'1',
    }

    if enable_mailingjob and len(groupids) > 0:
        # these cannot be in the http parameters.
        config[u'groups'] = {u'include': groupids,
                             u'exclude': []}
        config[u'scheduled_date'] = u'now'

    params[u'json'] = json.dumps(config)

    try:
        results = civicrm.create(u'Mailing', **params)

        infomsg(settings, u'Template Created on:', results[0][u'created_date'])
        infomsg(settings, u'Template Scheduled for:', results[0][u'scheduled_date'])

        # CiviCRM creates a MailingJob record for us, which is not
        # always wanted: this code deletes it again.
        # the_mailingjob = results[0]['api.mailing_job.create']['values']
        # if (not enable_mailingjob) and len(the_mailingjob) == 1:
        #     delete_mailingjob(settings, civicrm, the_mailingjob[0]['id'])

        return True

    except CivicrmError as e:
        print(u'Mail template creation failed: ' + e.message)
        return False


def delete_mailingjob(settings, civicrm, jobid):
    """
    Send the email defined by the template to the CiviCRM instance.

    :param settings: The command line settings object.
    :param civicrm: Object defining a CiviCRM instance.
    :param jobid: The mailing job ID to delete.
    """
    try:
        results = civicrm.delete(u'MailingJob', jobid, True)
        debugmsg(settings, u'Returned object ', results)
        infomsg(settings, u'Deleted:', jobid)
        return True

    except CivicrmError as e:
        print(u'Mailing job deletion failed: ' + e.message)
        return False


def mailcivi():
    """
    Parse the command line args to determine where the mail template
    is coming from, fetch it, and send it on to the CiviCRM instance
    using the supplied URL and keys.

    Returns the integer code to shell:
        0 for success,
        1 for parameter problem,
        2 for internal error.
    """
    settings = getoptions()

    # settings required for Civi connect are command-args only.
    civicrm = connect_to_civi(settings)

    # There is a hierarchy of input sources: local HTML files are preferred,
    # then a local JSON file, then a JSON URL. However this should not
    # be important because 'getoptions()' considers the three sources to be
    # mutually exclusive.
    template = None
    try:
        if settings.htmlfile:
            infomsg(settings, 'Input from: HTML file')
            template = readlocal(settings, civicrm)
        elif settings.jsonfile:
            infomsg(settings, 'Input from: JSON file')
            jsontemplate = json.load(settings, settings.jsonfile)
            template = readjson(settings, civicrm, jsontemplate)
        elif settings.jsonurl:
            infomsg(settings, 'Input from: Remote JSON <' + settings.jsonurl + '>')
            jsontemplate = json.loads(fetch_url(settings.jsonurl))
            template = readjson(settings, civicrm, jsontemplate)
    except Exception as e:
        print(e.message)
        return 2

    # If group lookups fail, we shouldn't continue. A message has
    # already been printed.
    if hasattr(template, 'creator_id') and False == template.creator_id:
        return 1
    if hasattr(template, 'recipient_id') and False == template.recipient_id:
        return 1

    # Show config in verbose mode.
    infomsg(settings, 'Using URL :', settings.civicrm)
    infomsg(settings, 'Action    :', template.action)
    infomsg(settings, 'Name      :', template.name)
    if hasattr(template, 'subject'):
        infomsg(settings, 'Subject   :', template.subject)
    if hasattr(template, 'creator_id'):
        infomsg(settings, 'Creator   :', template.creator_id)
    if hasattr(template, 'recipient_id'):
        infomsg(settings, 'GroupID   :', template.recipient_id)
    infomsg(settings, 'Email     :', template.from_email)
    infomsg(settings, 'Name      :', template.from_name)

    if template.action == 'disable':
        return 0

    if not check_creator_exists(settings, civicrm, template.creator_id):
        return 1

    enable_send = (template.action == 'send') and hasattr(template, 'recipient_id')
    group_list = []
    if enable_send:
        group_list = [ template.recipient_id ]

    if not create_template(settings, civicrm, template, group_list, enable_send):
        return 1

    return 0


def main():                 # needed for console script
    sys.exit(mailcivi())


if __name__ == "__main__":
    sys.exit(main())
