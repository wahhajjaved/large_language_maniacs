import os
import inspect
import subprocess
import boto3
from botocore.exceptions import ClientError, ProfileNotFound
from pyaws.core.script_utils import stdout_message
from pyaws.core import loggers
from pyaws._version import __version__

try:
    from pyaws.core.oscodes_unix import exit_codes
    splitchar = '/'     # character for splitting paths (linux)
except Exception:
    from pyaws.core.oscodes_win import exit_codes    # non-specific os-safe codes
    splitchar = '\\'    # character for splitting paths (window


DEFAULT_REGION = os.environ['AWS_DEFAULT_REGION']
logger = loggers.getLogger(__version__)


def profile_prefix(profile_name):
    """
    Summary:
        Determines if temp credential used;
        - if yes, returns profile with correct prefix
        - if no, returns profile (profile_name) unaltered
    Returns:
        awscli profilename, TYPE str
    """
    try:
        if subprocess.getoutput(f'aws configure get profile.{profile}.aws_access_key_id 2>/dev/null'):
            return profile
        elif subprocess.getoutput(f'aws configure get profile.{PREFIX + profile}.aws_access_key_id 2>/dev/null'):
            return PREFIX + profile
    except Exception as e:
        logger.exception(
            f'{inspect.stack()[0][3]}: Unknown error while interrogating local awscli config: {e}'
            )
        raise
    return None


def boto3_session(service, region=DEFAULT_REGION, profile=None):
    """
    Summary:
        Establishes boto3 sessions, client
    Args:
        :service (str): boto3 service abbreviation ('ec2', 's3', etc)
        :profile (str): profile_name of an iam user from local awscli config
    Returns:
        TYPE: boto3 client object
    """
    try:
        if profile:
            if profile == 'default':
                client = boto3.client(service, region_name=region)
            else:
                session = boto3.Session(profile_name=profile)
                client = session.client(service, region_name=region)
        else:
            client = boto3.client(service, region_name=region)
    except ClientError as e:
        logger.exception(
            "%s: IAM user or role not found (Code: %s Message: %s)" %
            (inspect.stack()[0][3], e.response['Error']['Code'],
             e.response['Error']['Message']))
        raise
    except ProfileNotFound:
        msg = (
            '%s: The profile (%s) was not found in your local config. Exit.' %
            (inspect.stack()[0][3], profile))
        stdout_message(msg, 'FAIL')
        logger.warning(msg)
        sys.exit(exit_codes['EX_NOUSER']['Code'])
    return client


def authenticated(profile):
    """
    Summary:
        Tests generic authentication status to AWS Account
    Args:
        :profile (str): iam user name from local awscli configuration
    Returns:
        TYPE: bool, True (Authenticated)| False (Unauthenticated)
    """
    try:
        sts_client = boto3_session(service='sts', profile=profile)
        httpstatus = sts_client.get_caller_identity()['ResponseMetadata']['HTTPStatusCode']
        if httpstatus == 200:
            return True

    except ClientError as e:
        if e.response['Error']['Code'] == 'InvalidClientTokenId':
            logger.info(
                '%s: Invalid credentials to authenticate for profile user (%s). Exit. [Code: %d]'
                % (inspect.stack()[0][3], profile, exit_codes['EX_NOPERM']['Code']))
        elif e.response['Error']['Code'] == 'ExpiredToken':
            logger.info(
                '%s: Expired temporary credentials detected for profile user (%s) [Code: %d]'
                % (inspect.stack()[0][3], profile, exit_codes['EX_CONFIG']['Code']))
        else:
            logger.exception(
                '%s: Unknown Boto3 problem. Error: %s' %
                (inspect.stack()[0][3], e.response['Error']['Message']))
    except Exception as e:
        return False
    return False
