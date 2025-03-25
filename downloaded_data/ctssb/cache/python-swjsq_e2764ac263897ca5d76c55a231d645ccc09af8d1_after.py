from __future__ import absolute_import
from __future__ import unicode_literals

import getopt
import hashlib
import logging
import os
import sys

from swjsq._compat import text_type
from swjsq.core import APIError
from swjsq.core import fast_d1ck, setup
from swjsq.core import TYPE_NORMAL_ACCOUNT, TYPE_NUM_ACCOUNT


class NoCredentialsError(RuntimeError):
    pass


class Arguments(object):
    def __init__(self):
        self.account_file_encrypted = '.swjsq.account'
        self.account_file_plain = 'swjsq.account.txt'


def show_usage():
    options = [
        ('-h, --help', 'show this help message and exit'),
    ]

    print('usage: {} [OPTIONS]'.format(sys.argv[0]))
    print()
    print('options:')
    for opt, description in options:
        print('  {}\t{}'.format(opt, description))


def parse_args():
    try:
        long_opts = ['help']
        opts, args = getopt.getopt(sys.argv[1:], 'h', long_opts)
    except getopt.GetoptError as err:
        print(err)
        show_usage()
        sys.exit(2)

    args = Arguments()

    for o, a in opts:
        if o in ('-h', '--help'):
            show_usage()
            sys.exit()
        else:
            assert False, 'Unhandled option'

    return args


def setup_logging():
    fh = logging.FileHandler('swjsq.log')
    fh.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    FMT = '%(asctime)s %(levelname)s %(message)s'
    DATE_FMT = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter(FMT, DATE_FMT)
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger = logging.getLogger()

    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.setLevel(logging.DEBUG)


class Credentials(object):
    def __init__(self, login_type, uid, password_hash):
        self.login_type = login_type
        self.uid = uid
        self.password_hash = password_hash


def load_credentials_from_file(path, skip_password_hash=False):
    with open(path, 'rb') as f:
        uid, pwd = f.read().strip().split(b',')
    if not skip_password_hash:
        pwd = hashlib.md5(pwd).hexdigest()
    # return type of hexdigest is different between PY2 and PY3
    if pwd is text_type:
        pwd = pwd.encode('utf-8')
    return uid, pwd


def load_credentials_from_env():
    uid, pwd = os.getenv('XUNLEI_UID'), os.getenv('XUNLEI_PASSWD')
    if not uid or not pwd:
        raise RuntimeError('Environment variables not set')
    # type of environment variable is different between PY2 and PY3
    if uid is text_type:
        uid = uid.encode(sys.getfilesystemencoding())
    if pwd is text_type:
        pwd = pwd.encode(sys.getfilesystemencoding())
    pwd = hashlib.md5(pwd).hexdigest()
    # return type of hexdigest is different between PY2 and PY3
    if pwd is text_type:
        pwd = pwd.encode('utf-8')
    return uid, pwd


def load_credentials(account_file_plain, account_file_encrypted):
    '''Try to load credentials.

    :param account_file_plain: Path to plain text credentials
    :param account_file_encrypted: Path to encrypted credentials
    :returns: the Credentials object loaded
    :raises NoCredentialsError: No credentials can be loaded.
    '''
    try:
        uid, pwd_md5 = load_credentials_from_file(account_file_plain)
        return Credentials(TYPE_NORMAL_ACCOUNT, uid, pwd_md5)
    except Exception:
        pass

    try:
        uid, pwd_md5 = load_credentials_from_file(account_file_encrypted,
                                                  skip_password_hash=True)
        return Credentials(TYPE_NUM_ACCOUNT, uid, pwd_md5)
    except Exception:
        pass

    try:
        uid, pwd_md5 = load_credentials_from_env()
        return Credentials(TYPE_NORMAL_ACCOUNT, uid, pwd_md5)
    except Exception:
        raise NoCredentialsError()


def main():
    try:
        # Arguments
        args = parse_args()

        # Setups
        setup_logging()
        setup()

        # Load credentials
        credentials = load_credentials(args.account_file_plain,
                                       args.account_file_encrypted)

        # Routine
        save_encrypted = (credentials.login_type != TYPE_NUM_ACCOUNT)
        fast_d1ck(credentials.uid, credentials.password_hash,
                  credentials.login_type,
                  save=save_encrypted,
                  account_file_encrypted=args.account_file_encrypted,
                  account_file_plain=args.account_file_plain)
    except NoCredentialsError:
        logging.error('No credentials provided.')
    except APIError as e:
        logging.error('API Error %s: (%d) %s',
                      e.command, e.errno, e.message or 'Unknown')
    except KeyboardInterrupt:
        logging.info('Stopping')


if __name__ == '__main__':
    main()
