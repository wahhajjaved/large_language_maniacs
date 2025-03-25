"""

ec2 spotprice retriever, GPL v3 License

Copyright (c) 2018-2019 Blake Huber

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the 'Software'), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

"""
import os
import sys
import datetime
import json
import inspect
import argparse
import boto3
from botocore.exceptions import ClientError
from spotlib.lambda_utils import get_regions, read_env_variable
from libtools import stdout_message
from spotlib.core import SpotPrices, UtcConversion
from spotlib.statics import local_config
from spotlib import logger


try:
    from libtools.oscodes_unix import exit_codes
    os_type = 'Linux'
    user_home = os.getenv('HOME')
    splitchar = '/'                                   # character for splitting paths (linux)

except Exception:
    from libtools.oscodes_win import exit_codes         # non-specific os-safe codes
    os_type = 'Windows'
    user_home = os.getenv('username')
    splitchar = '\\'                                  # character for splitting paths (windows)


# globals
container = []
module = os.path.basename(__file__)
iloc = os.path.abspath(os.path.dirname(__file__))     # installed location of modules


def summary_statistics(data, instances):
    """
    Calculate stats across spot price data elements retrieved
    in the current execution.  Prints to stdout

    Args:
        :data (list): list of spot price dictionaries
        :instances (list): list of unique instance types found in data

    Returns:
        Success | Failure, TYPE:  bool
    """
    instance_dict, container = {}, []
    for itype in instances:
        try:
            cur_type = [
                {'SpotPrice': x['SpotPrice'], 'InstanceType': x['InstanceType']} for x in prices['SpotPriceHistory'] if x['InstanceType'] == itype
            ]
            instance_dict['InstanceType'] = str(itype)
            instance_dict['average'] = sum([float(x['SpotPrice']) for x in cur_type]) / len(cur_type)
            container.append(instance_dict)
        except KeyError as e:
            logger.exception('KeyError on key {} while printing summary report statistics.'.format(e))
            continue
    # output to stdout
    print_ending_summary(instances, container)
    return True


def print_ending_summary(itypes_list, summary_data, region):
    """
    Prints summary statics to stdout at the conclusion of spot
    price data retrieval
    """
    now = datetime.datetime.now().strftime('%Y-%d-%m %H:%M:%S')
    print('EC2 Spot price data retrieval concluded {}'.format(now))
    print('Found {} different types of EC2 isntances in {} spot data'.format(len(itypes_list), region))
    print('Instance Type distribution:')


def source_environment():
    """
    Sources all environment variables
    """
    return {
        'duration_days': read_env_variable('default_duration'),
        'page_size': read_env_variable('page_size', 500),
        'bucket': read_env_variable('S3_BUCKET', None)
    }.get(env_var, None)


def modules_location():
    """Filsystem location of Python3 modules"""
    return os.path.split(os.path.abspath(__file__))[0]


def options(parser, help_menu=False):
    """
    Summary:
        parse cli parameter options

    Returns:
        TYPE: argparse object, parser argument set

    """
    # default datetime objects when no custom datetimes supplied
    start_dt, end_dt = default_endpoints()

    parser.add_argument("-p", "--pull", dest='pull', action='store_true', required=False)
    parser.add_argument("-C", "--configure", dest='configure', action='store_true', required=False)
    parser.add_argument("-d", "--debug", dest='debug', action='store_true', default=False, required=False)
    parser.add_argument("-h", "--help", dest='help', action='store_true', required=False)
    parser.add_argument("-s", "--start", dest='start', nargs='*', default=start_dt, required=False)
    parser.add_argument("-e", "--end", dest='end', nargs='*', default=end_dt, required=False)
    parser.add_argument("-V", "--version", dest='version', action='store_true', required=False)
    return parser.parse_known_args()


def package_version():
    """
    Prints package version and requisite PACKAGE info
    """
    print(about.about_object)
    sys.exit(exit_codes['EX_OK']['Code'])


def precheck(debug):
    """
    Runtime Dependency Checks: postinstall artifacts, environment
    """
    try:
        pass
    except OSError:
        fx = inspect.stack()[0][3]
        logger.exception('{}: Problem installing user config files. Exit'.format(fx))
        return False
    return True


def default_endpoints(duration_days=1):
    """
    Supplies the default start and end datetime objects in absence
    of user supplied endpoints which frames time period from which
    to begin and end retrieving spot price data from Amazon APIs.

    Returns:  TYPE: tuple, containing:
        - start (datetime), midnight yesterday
        - end (datetime) midnight, current day

    """
    # end datetime calcs
    dt_date = datetime.datetime.today().date()
    dt_time = datetime.datetime.min.time()
    end = datetime.datetime.combine(dt_date, dt_time)

    # start datetime calcs
    duration = datetime.timedelta(days=duration_days)
    start = end - duration
    return start, end


def calculate_duration_endpoints(duration_days=1, start_time=None, end_time=None):
    try:

        if all(x is None for x in [start_time, end_time]):
            start, end = default_duration_endpoints()

        elif all(isinstance(x, datetime.datetime) for x in [start_time, end_time]):
            start = convert_dt(start_time)
            end = convert_dt(end_time)

    except Exception as e:
        logger.exception(f'Unknown exception while calc start & end duration: {e}')
        sys.exit(exit_codes['E_BADARG']['Code'])
    return  start, end


def retreive_spotprice_data(start_dt, end_dt, debug=False):
    """
    Returns:
        spot price data (dict), unique list of instance sizes (list)

    """
    try:
        for region in get_regions():
            client = boto3.client('ec2', region_name=region)
            pricelist = client.describe_spot_price_history(StartTime=start, EndTime=end).get(['SpotPriceHistory'])
            instance_sizes = set([x['InstanceType'] for x in pricelist])
    except ClientError as e:
        return [], []
    return pricelist, instance_sizes


def spotprice_generator(start_dt, end_dt, region, debug=False):
    """
    Summary:
        Generator returning up to 1000 data items at once

    Returns:
        spot price data (generator)

    """
    try:
        client = boto3.client('ec2', region_name=region)
        paginator = client.get_paginator('describe_spot_price_history')
        page_size= read_env_variable('page_size', 500)
        page_iterator = paginator.paginate(
                            StartTime=start_dt,
                            EndTime=end_dt,
                            DryRun=debug,
                            PaginationConfig={'PageSize': page_size}
                        )
        for page in page_iterator:
            try:
                for price_dict in page['SpotPriceHistory']:
                    yield price_dict
            except ClientError as e:
                logger.exception(f'Boto client error while downloading spot history data: {e}')
                continue
    except KeyError as e:
        logger.exception(f'KeyError while processing spot history data. Schema change?: {e}')
    except Exception as e:
        logger.exception(f'Unknown exception while calc start & end duration: {e}')


def s3upload(bucket, s3object, key, profile='default'):
    """
        Streams object to S3 for long-term storage

    Returns:
        Success | Failure, TYPE: bool
    """
    try:
        session = boto3.Session(profile_name=profile)
        s3client = session.client('s3')
        # dict --> str -->  bytes (utf-8 encoded)
        bcontainer = json.dumps(s3object, indent=4, default=str).encode('utf-8')
        response = s3client.put_object(Bucket=bucket, Body=bcontainer, Key=key)

        # http completion code
        statuscode = response['ResponseMetadata']['HTTPStatusCode']

    except ClientError as e:
        logger.exception(f'Unknown exception while calc start & end duration: {e}')
        return False
    return True if str(statuscode).startswith('20') else False


def init():

    parser = argparse.ArgumentParser(add_help=False)

    try:

        args, unknown = options(parser)

    except Exception as e:
        help_menu()
        stdout_message(str(e), 'ERROR')
        sys.exit(exit_codes['E_BADARG']['Code'])



    if len(sys.argv) == 1 or args.help:
        help_menu()
        sys.exit(exit_codes['EX_OK']['Code'])

    elif args.version:
        package_version()


    elif args.pull:

        # validate prerun conditions
        if not precheck(args.debug):
            sys.exit(exit_codes['E_BADARG']['Code'])

        d = EC2SpotPrices()
        start, end = d.set_endpoints(args.start, args.end)

        for region in get_regions():

            s3_fname = '_'.join(
                            [
                                start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                end.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                'all-instance-spot-prices.json'
                            ]
                        )

            prices = [x for x in d.spotprice_generator(region)]

            # conversion of datetime obj => utc strings
            uc = UtcConversion(prices)

            # build unique collection of instances for this region
            instances = list(set([x['InstanceType'] for x in prices['SpotPriceHistory']]))
            instances.sort()

            # spot price data destination
            bucket = read_env_variable('S3_BUCKET', None)
            data = prices
            key = os.path.join(region, s3_fname)

            _completed = s3upload(bucket, data, key)
            success = f'Successful write to s3 bucket {bucket} of object {key}'
            failure = f'Problem writing data to s3 bucket {bucket} of object {key}'
            logger.info(success) if _completed else logger.warning(failure)

            # instance types list destination
            bucket = 'aws01-storage'
            s3object = instances
            key = os.path.join(region, 'spot-instanceTypes')


            if s3upload(bucket, s3object, key):
                return summary_statistics(instances, prices, region) and _completed

            failure = f'Problem writing data to s3 bucket {bucket} of object {key}'
            logger.warning(failure)
            return False

    else:
        stdout_message(
            'Dependency check fail %s' % json.dumps(args, indent=4),
            prefix='AUTH',
            severity='WARNING'
            )
        sys.exit(exit_codes['E_DEPENDENCY']['Code'])

    failure = """ : Check of runtime parameters failed for unknown reason.
    Please ensure you have both read and write access to local filesystem. """
    logger.warning(failure + 'Exit. Code: %s' % sys.exit(exit_codes['E_MISC']['Code']))
    print(failure)
