#!/usr/bin/python3

import argparse

from getpass import getpass
from json import dump, load
from os.path import isfile

"""

    setup.py : This will populate the input json file with entries.

    Usage:

    setup.py -a [ --add ] :     Will prompt for host, email, password, mailbox and append to the input JSON file.
                                If the input JSON file does not exists, it will create one and add the data to it.

    setup.py -d [ --delete ] :  Will delete an existing entry from the input JSON file

    ==============================================================================================================

    Copyright (c) 2018 Nilashish Chakraborty


"""


def create_input_file():
    """
        This method creates a new input JSON file and initializes it with an empty dictionary called 'entries'.

    """

    entries = {}
    entries['items'] = []

    with open('data.json', 'w') as outfile:
        dump(entries, outfile, indent=4)

    print('Created a new data.json file...')


def append_entry(host, email, password, mailbox):
    """
        This method adds a new entry to the input JSON file - 'data.json'.

    """

    new_entry = {

        'host': host,
        'email': email,
        'password': password,
        'mailbox': mailbox
    }

    with open('data.json') as f:
        data = load(f)

    data["items"].append(new_entry)

    with open('data.json', 'w') as outfile:
        dump(data, outfile, indent=4)

    print('\nNew Entry Added Successfully!')


def add_entry():
    """
        This method prompts the user to enter details that need to be added to the input JSON file.
        If 'data.json' does not exists, it will create a new file and append to it.
        Else, it will append the new entry to the existing input JSON file.

    """

    host = input('\nEnter Mail Server Host: ')
    email = input('\nEnter Email ID: ')
    password = getpass(prompt='\nEnter Password: ')
    mailbox = input('\nEnter MailBox: ')
    mobile = input('\nEnter Mobile Number: ')

    if not isfile('data.json'):
        print('No input data.json found...')
        create_input_file()

    append_entry(host, email, password, mailbox)


def remove_entry():

    # TO-DO:    This method aims to remove an entry from the input JSON file
    #           based on the email id, mobile number & inbox given.

    pass


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description="A setup tool for Knowtify", prog='python3 setup.py')

    parser.add_argument(
        '-a',
        '--add',
        help='Add a new entry in the input JSON file',
        action='store_true')

    parser.add_argument(
        '-d',
        '--delete',
        help='Remove an existing entry from the input JSON file',
        action='store_true')

    args = parser.parse_args()

    if args.add:
        add_entry()

    elif args.delete:
        remove_entry()

    else:
        print("\nError: Requires an argument to perform an action")
        print("\nType python3 setup.py -h or python3 setup.py --help for help")
