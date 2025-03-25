#!/usr/bin/env python3

import argparse
import os
import re
import sys
import json
import inspect
from pyaws import logd, __version__
from botocore.exceptions import ClientError
from pyaws.core.session import authenticated, boto3_session
from pyaws.core.script_utils import stdout_message, export_json_object
from pyaws.ec2.help_menu import menu_body
from pyaws.core.colors import Colors

try:
    from pyaws.core.oscodes_unix import exit_codes
except Exception:
    from pyaws.core.oscodes_win import exit_codes    # non-specific os-safe codes

# globals
logger = logd.getLogger(__version__)
VALID_FORMATS = ('json', 'text')
VALID_AMI_TYPES = (
        'amazonlinux1', 'amazonlinux2', 'redhat7.3', 'redhat7.4', 'redhat7.5',
        'ubuntu14.04', 'ubuntu16.04', 'ubuntu16.10', 'ubuntu18.04', 'ubuntu18.10'
    )
DEFAULT_REGION = os.environ['AWS_DEFAULT_REGION']

# AWS Marketplace Owner IDs
UBUNTU = '099720109477'
AMAZON = '137112412989'
CENTOS = '679593333241'
REDHAT = '679593333241'


def help_menu():
    """
    Displays help menu contents
    """
    print(
        Colors.BOLD + '\n\t\t\t  ' + 'machineimage' + Colors.RESET +
        ' help contents'
        )
    sys.stdout.write(menu_body)
    return


def get_regions(profile):
    """ Return list of all regions """
    try:

        client = boto3_session(service='ec2', profile=profile)

    except ClientError as e:
        logger.exception(
            '%s: Boto error while retrieving regions (%s)' %
            (inspect.stack()[0][3], str(e)))
        raise e
    return [x['RegionName'] for x in client.describe_regions()['Regions']]


def amazonlinux1(profile, region=None, detailed=False, debug=False):
    """
    Return latest current amazonlinux v1 AMI for each region
    Args:
        :profile (str): profile_name
        :region (str): if supplied as parameter, only the ami for the single
        region specified is returned
    Returns:
        amis, TYPE: list:  container for metadata dict for most current instance in region
    """
    amis, metadata = {}, {}
    if region:
        regions = [region]
    else:
        regions = get_regions(profile=profile)

    # retrieve ami for each region in list
    for region in regions:
        try:
            client = boto3_session(service='ec2', region=region, profile=profile)
            r = client.describe_images(
                Owners=['amazon'],
                Filters=[
                    {
                        'Name': 'name',
                        'Values': [
                            'amzn-ami-hvm-2018.??.?.2018????-x86_64-gp2'
                        ]
                    }
                ])
            metadata[region] = r['Images'][0]
            amis[region] = r['Images'][0]['ImageId']
        except ClientError as e:
            logger.exception(
                '%s: Boto error while retrieving AMI data (%s)' %
                (inspect.stack()[0][3], str(e)))
            continue
        except Exception as e:
            logger.exception(
                '%s: Unknown Exception occured while retrieving AMI data (%s)' %
                (inspect.stack()[0][3], str(e)))
            raise e
    if detailed:
        return metadata
    return amis


def amazonlinux2(profile, region=None, detailed=False, debug=False):
    """
    Return latest current amazonlinux v2 AMI for each region
    Args:
        :profile (str): profile_name
        :region (str): if supplied as parameter, only the ami for the single
        region specified is returned
    Returns:
        amis, TYPE: list:  container for metadata dict for most current instance in region
    """
    amis, metadata = {}, {}
    if region:
        regions = [region]
    else:
        regions = get_regions(profile=profile)

    # retrieve ami for each region in list
    for region in regions:
        try:
            if not profile:
                profile = 'default'
            client = boto3_session(service='ec2', region=region, profile=profile)

            r = client.describe_images(
                Owners=['amazon'],
                Filters=[
                    {
                        'Name': 'name',
                        'Values': [
                            'amzn2-ami-hvm-????.??.?.2018????.?-x86_64-gp2',
                            'amzn2-ami-hvm-????.??.?.2018????-x86_64-gp2'
                        ]
                    }
                ])
            metadata[region] = r['Images'][0]
            amis[region] = r['Images'][0]['ImageId']
        except ClientError as e:
            logger.exception(
                '%s: Boto error while retrieving AMI data (%s)' %
                (inspect.stack()[0][3], str(e)))
            continue
        except Exception as e:
            logger.exception(
                '%s: Unknown Exception occured while retrieving AMI data (%s)' %
                (inspect.stack()[0][3], str(e)))
            raise e
    if detailed:
        return metadata
    return amis


def redhat(profile, os, region=None, detailed=False, debug=False):
    """
    Return latest current Redhat AMI for each region
    Args:
        :profile (str): profile_name
        :region (str): if supplied as parameter, only the ami for the single
        region specified is returned
    Returns:
        amis, TYPE: list:  container for metadata dict for most current instance in region
    """
    amis, metadata = {}, {}
    if region:
        regions = [region]
    else:
        regions = get_regions(profile=profile)
    # retrieve ami for each region in list
    for region in regions:
        try:
            client = boto3_session(service='ec2', region=region, profile=profile)
            r = client.describe_images(
                Owners=['309956199498'],
                Filters=[
                    {
                        'Name': 'name',
                        'Values': [
                            'RHEL-%s*GA*' % os
                        ]
                    }
                ])

            # need to find ami with latest date returned
            newest = sorted(r['Images'], key=lambda k: k['CreationDate'])[-1]
            metadata[region] = newest
            amis[region] = newest['ImageId']
        except ClientError as e:
            logger.exception(
                '%s: Boto error while retrieving AMI data (%s)' %
                (inspect.stack()[0][3], str(e)))
            continue
        except Exception as e:
            logger.exception(
                '%s: Unknown Exception occured while retrieving AMI data (%s)' %
                (inspect.stack()[0][3], str(e)))
            raise e
    if detailed:
        return metadata
    return amis


def ubuntu(profile, os, region=None, detailed=False, debug=False):
    """
    Return latest current ubuntu AMI for each region
    Args:
        :profile (str): profile_name
        :region (str): if supplied as parameter, only the ami for the single
        region specified is returned
    Returns:
        amis, TYPE: list:  container for metadata dict for most current instance in region
    """
    amis, metadata = {}, {}
    if region:
        regions = [region]
    else:
        regions = get_regions(profile=profile)
    # retrieve ami for each region in list
    for region in regions:
        try:
            client = boto3_session(service='ec2', region=region, profile=profile)
            r = client.describe_images(
                Owners=[UBUNTU],
                Filters=[
                    {
                        'Name': 'name',
                        'Values': [
                            '*%s*' % os
                        ]
                    }
                ])

            # need to find ami with latest date returned
            if debug:
                print(json.dumps(r, indent=4))
            newest = sorted(r['Images'], key=lambda k: k['CreationDate'])[-1]
            metadata[region] = newest
            amis[region] = newest['ImageId']
        except ClientError as e:
            logger.exception(
                '%s: Boto error while retrieving AMI data (%s)' %
                (inspect.stack()[0][3], str(e)))
            continue
        except Exception as e:
            logger.exception(
                '%s: Unknown Exception occured while retrieving AMI data (%s)' %
                (inspect.stack()[0][3], str(e)))
            raise e
    if detailed:
        return metadata
    return amis


def is_tty():
    """
    Summary:
        Determines if output is displayed to the screen or redirected
    Returns:
        True if tty terminal | False is redirected, TYPE: bool
    """
    return sys.stdout.isatty()


def os_version(imageType):
    """ Returns the version when provided redhat AMI type """
    return ''.join(re.split('(\d+)', imageType)[1:])


def format_text(json_object):
    """ Formats json object into text format """
    block = ''
    try:
        for k,v in json_object.items():
            row = '%s:\t%s\n' % (str(k), str(v))
            block += row
        print(block.strip())
    except KeyError as e:
        logger.exception(
            '%s: json_object does not appear to be json structure. Error (%s)' %
            (inspect.stack()[0][3], str(e))
            )
    return True


def main(profile, imagetype, format, details, debug, filename='', rgn=None):
    """
    Summary:
        Calls appropriate module function to identify the latest current amazon machine
        image for the specified OS type
    Returns:
        json (dict) | text (str)
    """
    try:
        if imagetype == 'amazonlinux1':
            latest = amazonlinux1(profile=profile,  region=rgn, detailed=details, debug=debug)

        elif imagetype == 'amazonlinux2':
            latest = amazonlinux2(profile=profile, region=rgn, detailed=details, debug=debug)

        elif 'redhat' in imagetype:
            latest = redhat(profile=profile, os=os_version(imagetype), region=rgn, detailed=details, debug=debug)

        elif 'ubuntu' in imagetype:
            latest = ubuntu(profile=profile, os=os_version(imagetype), region=rgn, detailed=details, debug=debug)

        # return appropriate response format
        if format == 'json' and not filename:
            if is_tty():
                r = export_json_object(dict_obj=latest, logging=False)
            else:
                print(json.dumps(latest, indent=4))
                r = True

        elif format == 'json' and filename:
            r = export_json_object(dict_obj=latest, filename=filename)

        elif format == 'text' and not filename:
            r = format_text(latest)

    except Exception as e:
        logger.exception(
            '%s: Unknown problem retrieving data from AWS (%s)' %
            (inspect.stack()[0][3], str(e)))
        return False
    return r


def options(parser, help_menu=False):
    """
    Summary:
        parse cli parameter options
    Returns:
        TYPE: argparse object, parser argument set
    """
    parser.add_argument("-p", "--profile", nargs='?', default="default", required=False, help="type (default: %(default)s)")
    parser.add_argument("-i", "--image", nargs='?', type=str, choices=VALID_AMI_TYPES, required=False)
    parser.add_argument("-d", "--details", dest='details', default=False, action='store_true', required=False)
    parser.add_argument("-r", "--region", nargs='?', type=str, required=False)
    parser.add_argument("-f", "--format", nargs='?', default='json', type=str, choices=VALID_FORMATS, required=False)
    parser.add_argument("-n", "--filename", nargs='?', default='', type=str, required=False)
    parser.add_argument("-D", "--debug", dest='debug', default=False, action='store_true', required=False)
    parser.add_argument("-V", "--version", dest='version', action='store_true', required=False)
    parser.add_argument("-h", "--help", dest='help', action='store_true', required=False)
    return parser.parse_args()


def init_cli():
    """ Collect parameters and call main """
    try:
        parser = argparse.ArgumentParser(add_help=False)
        args = options(parser)
    except Exception as e:
        help_menu()
        stdout_message(str(e), 'ERROR')
        sys.exit(exit_codes['E_MISC']['Code'])

    if args.debug:
        print('profile is: ' + args.profile)
        print('image type: ' + args.image)
        print('format: ' + args.format)
        print('filename: ' + args.filename)
        print('debug flag: %b', str(args.debug))

    if len(sys.argv) == 1:
        help_menu()
        sys.exit(exit_codes['EX_OK']['Code'])

    elif args.help:
        help_menu()

    elif authenticated(profile=args.profile):
        # execute ami operation
        if args.image and args.region:
            if args.region in get_regions(args.profile):
                main(
                        profile=args.profile, imagetype=args.image,
                        format=args.format, filename=args.filename,
                        rgn=args.region, details=args.details, debug=args.debug
                    )
        elif args.image and not args.region:
            main(
                    profile=args.profile, imagetype=args.image,
                    format=args.format, filename=args.filename,
                    details=args.details, debug=args.debug
                )
        else:
            stdout_message(
                    f'Image type must be one of: {VALID_AMI_TYPES}',
                    prefix='INFO'
                )
            sys.exit(exit_codes['E_DEPENDENCY']['Code'])
    else:
        stdout_message(
            'Authenication Failed to AWS Account for user %s' % profile,
            prefix='AUTH',
            severity='WARNING'
            )
        sys.exit(exit_codes['E_AUTHFAIL']['Code'])

    failure = """ : Check of runtime parameters failed for unknown reason.
    Please ensure local awscli is configured. Then run keyconfig to
    configure keyup runtime parameters.   Exiting. Code: """
    logger.warning(failure + 'Exit. Code: %s' % sys.exit(exit_codes['E_MISC']['Code']))
    print(failure)
