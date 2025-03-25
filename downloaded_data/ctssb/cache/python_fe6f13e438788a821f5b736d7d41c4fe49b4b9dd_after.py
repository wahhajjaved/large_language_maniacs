#!/usr/bin/env python3

import os
import sys
import shutil
import argparse
import logging

class Color:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    ERROR = '\033[91m'
    ENDC = '\033[0m'

class WindowsMigrate:
    def __init__(self, log=False):
        self.log = log
        self.changed = 0
        self.home = ''
        self.path = ''
        self.valid_chars = "!@#$%^~`&-_.() abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    def check_username(self, username):
        if not username:
            if log:
                logging.debug('User did not enter a username.')
            print(Color.ERROR + '[ERROR]: You must enter a username!' + Color.ENDC)
            return False

        if os.path.exists('/home/' + username):
            self.home = '/home/' + username
            return True
        else:
            if log:
                logging.debug('Username that user enter was not found in /home.')
            print(Color.ERROR + '[ERROR]: User not found'+ Color.ENDC)
            return False

    def initial_cleanup(self):
        # The first thing we need to do is delete .macromedia as it is not needed and
        # usually contains file paths longer than 260 characters.
        print(Color.WARNING + 'Deleting ~/.macromedia and ~/.cache/mozilla/firefox!' + Color.ENDC)
        shutil.rmtree(self.home + '/.macromedia', ignore_errors=True)
        shutil.rmtree(self.home + '/.cache/mozilla/firefox', ignore_errors=True)

    def check_dupes(self, new_name, ext=''):
        dup_count = 0
        if os.path.exists(self.path + new_name + ext):
            while os.path.exists(self.path + new_name + ext):
                # This removes the dup_count from the filename so that the count is incremental.
                if dup_count > 0:
                    new_name = new_name[:-1]

                dup_count += 1
                new_name += str(dup_count)

        return new_name

    def trim_invalid_chars(self, string):
        return ''.join(c for c in string if c in self.valid_chars)

    def fix_names(self):
        for root, dirs, files in os.walk(self.home):
            self.path = root + '/'

            for name in files:
                if len(name) > 255:
                    # TODO: Truncate folder and/or filename.
                    if self.log:
                        log.warning('File {0} needs to be shortened!'.format(path + name))
                    print(Color.WARNING + '{0} needs to be shortened before moving to Windows.'.format(name) + Color.ENDC)

                # Create a copy of the filename to work with. Next we grab the file extension
                # for use later on. Then we remove any invalid characters.
                new_name, ext = os.path.splitext(name)
                new_name = self.trim_invalid_chars(new_name)
                ext = self.trim_invalid_chars(ext)

                try:
                    if name != (new_name + ext):
                        new_name = self.check_dupes(new_name, ext)
                        if self.log:
                            logging.info('Renaming file {old} to {new}{ext}'.format(old=self.path + name, new=new_name, ext=ext))
                        print('Renaming file {old} to {new}{ext}.'.format(old=name, new=new_name, ext=ext))
                        os.rename(self.path + name, self.path + new_name + ext)
                        self.changed += 1
                except OSError as e:
                    if self.log:
                        logging.debug('Failed to rename: {0} Was trying to use {1} Error message {2}'.format(self.path + name,
                            new_name, e))
                    print('Unable to rename file {0}.'.format(name))
                    print(e)

        for root, dirs, files in os.walk(self.home):
            self.path = root + '/'

            for directory in dirs:
                new_dir = self.trim_invalid_chars(directory)
                try:
                    if new_dir != directory:
                        new_dir = self.check_dupes(new_dir)
                        if self.log:
                            logging.info('Renaming directory {0} to {1}'.format(self.path + directory, new_dir))
                        print('Renaming directory {0} to {1}'.format(directory, new_dir))
                        os.rename(self.path + directory, self.path + new_dir)
                        self.changed += 1
                except OSError as e:
                    if self.log:
                        logging.debug('Failed to rename directory: {0} Was trying to use: {1} Error message {2}'.format(
                            self.path + directory, name, e))
                    print(Color.ERROR + '[ERROR]: Unable to rename directory {0}.'.format(directory) + Color.ENDC)
                    print(e)

    def results(self):
        if self.log:
            logging.info('A total of {0} files and folders have been renamed.'.format(self.changed))
        print('A total of {0} files and folders have been renamed.'.format(self.changed))

def main():
    parser = argparse.ArgumentParser(description='Prep files to be moved to Windows from *nix.')
    parser.add_argument('--debug', '-d', action='store_true', help='debug mode is used for testing this script')
    parser.add_argument('--log', action='store_true', help='enable logging, output is saved to output.log')
    parser.add_argument('--user', '-u', nargs='?', help='allows specifying the user to skip the intro')
    args = parser.parse_args()

    if args.log:
        migration = WindowsMigrate(log = True)
    else:
        migration = WindowsMigrate()

    if args.debug:
        migration.home = os.path.expanduser('~') + '/test_data'
        migration.fix_names()
        migration.results()
        sys.exit(0)

    if args.user:
        username = args.user
    else:
        print('Welcome to the Windows Migrate tool. This program will rename folders and files')
        print('so that they can be moved to Windows without causing issues due to illegal')
        print('characters or paths that are too long.\n')
        username = input('Please enter the username of the user who you are migrating: ')

    if args.log:
        logging.basicConfig(filename=username + '.log', format='%(levelname)s:%(message)s', level=logging.DEBUG)

    success = migration.check_username(username)
    if not success:
        print('Aborting...')
        sys.exit(1)

    print('Start migration for {0}.'.format(username))
    migration.initial_cleanup()
    migration.fix_names()
    migration.results()

if __name__ == '__main__':
    main()
