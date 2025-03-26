#!/usr/bin/env python3

import os
import sys
import shutil
import argparse


class WindowsMigrate:
    def __init__(self):
        self.HOME = os.path.expanduser('~')
        self.path = ''
        self.valid_chars="-_.() abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    def initial_cleanup(self):
        # The first thing we need to do is delete .macromedia as it is not needed and
        # usually contains file paths longer than 260 characters.
        shutil.rmtree(self.HOME + '/.macromedia', ignore_errors=True)
        shutil.rmtree(self.HOME + '/.cache/mozilla/firefox', ignore_errors=True)

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

    def fix_filenames(self):
        # After I'm finished testing this os.walk will just be called on /home.
        # For now however I'm just calling it on test data.
        for root, dirs, files in os.walk(self.HOME + '/python/migrate/test_data'):
            self.path = root + '/'
            for directory in dirs:
                new_dir = self.trim_invalid_chars(directory)
                print('Old -> {0} New -> {1}'.format(directory, new_dir))
                try:
                    if new_dir != directory:
                        print('Renaming directory {0} to {1}'.format(directory, new_dir))
                        new_dir = self.check_dupes(new_dir)
                        os.rename(self.path + directory, self.path + new_dir)
                except OSError as e:
                    print('Unable to rename directory {0}.'.format(directory))
                    print(e)

            for name in files:
                if len(name) > 255:
                    # TODO: Truncate filename.
                    print('File {0} needs to be shortened.'.format(name))

                # Create a copy of the filename to work with. Next we grab the file extension
                # for use later on. Then we remove any invalid characters.
                new_name, ext = os.path.splitext(name)
                new_name = self.trim_invalid_chars(new_name)
                ext = self.trim_invalid_chars(ext)

                try:
                    if name != (new_name + ext):
                        print('Renaming file {old} to {new}{ext}.'.format(old=name, new=new_name, ext=ext))
                        new_name = self.check_dupes(new_name, ext)
                        os.rename(self.path + name, self.path + new_name + ext)
                except OSError as e:
                    print('Unable to rename file {0}.'.format(name))
                    print(e)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Prep files to be moved to Windows from *nix.')
    parser.add_argument('--debug', '-d', action='store_true', help='debug mode is used for testing this script')
    args = parser.parse_args()

    migration = WindowsMigrate()

    if args.debug:
        migration.fix_filenames()
        sys.exit(0)

    print("You should not be running this on your machine. It will delete", end=' ')
    print("several files and rename others.")
