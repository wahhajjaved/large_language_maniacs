#!/usr/bin/env python3

import os
import sys
import shutil
import textwrap
import lib.yaml as yaml
from argparse import ArgumentParser
from configparser import ConfigParser, MissingSectionHeaderError
from lib.progress import progress as progress_bar
from lib.markdownify import markdownify
from lib.columnize import columnize
from lib.flatten import flatten
from lib.uniq import uniq
from lib.run import run_command as run

stogit = 'git@stogit.cs.stolaf.edu:sd-s16'
labnames = {
    'sound': 'lab2',
}


def warn(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def size(path='.'):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            if not f.startswith('.'):
                fp = os.path.join(dirpath, f)
                try:
                    size = os.path.getsize(fp)
                except OSError:
                    size = 0
                total_size += size
    return total_size


def get_args():
    parser = ArgumentParser(description='The core of the CS251 toolkit.')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Be quieter')
    parser.add_argument('--no-update', '-n', action='store_true',
                        help='Do not update the student folders before checking.')
    parser.add_argument('--day', action='store',
                        help='Check out the student folder as of 5pm on the last <day of week>.')
    parser.add_argument('--date', action='store',
                        help='Check out the student folder as of 5pm on <date> (Y-M-D).')
    parser.add_argument('--clean', action='store_true',
                        help='Remove student folders and re-clone them')
    parser.add_argument('--record', action='append', nargs='+', metavar='HW',
                        help="Record information on student submissions. Requires a spec file.")
    parser.add_argument('--students', action='append', nargs='+', metavar='STUDENT',
                        help='Only iterate over these students.')
    parser.add_argument('--section', action='append', nargs='+', metavar='SECTION',
                        help='Only check these sections: my, all, a, b, etc.')
    parser.add_argument('--sort-by', action='store', default='name', type=str,
                        choices=['name', 'homework'],
                        help='Sort by either student name or homework count.')
    return vars(parser.parse_args())


def get_config():
    config = ConfigParser(allow_no_value=True)
    if os.path.exists('./students.txt'):
        with open('./students.txt', 'r') as infile:
            try:
                config.read_file(infile)
            except MissingSectionHeaderError:
                # handle plain text files, too
                return {'my': [name.strip() for name in infile.readlines()]}

    return config


def single_student(student, index, args={}, specs={}, recordings={}):
    def progress(message):
        return progress_bar(len(args['students']), index, message='%s [%s]' % (student, message))

    if args['clean']:
        progress('cleaning')
        shutil.rmtree(student)

    if not os.path.exists(student):
        progress('cloning')
        git_clone = 'git clone --quiet %s/%s.git' % (stogit, student)
        run(git_clone.split())

    os.chdir(student)

    retval = ''

    try:
        progress('stashing')
        if run('git status --porcelain'.split())[1]:
            run('git stash -u'.split())
            run('git stash clear'.split())

        if not args['no_update']:
            progress('updating')
            run('git pull --quiet origin master'.split())

        if args['day']:
            progress('checkouting')
            rev_list = '(git rev-list -n 1 --before="%s 18:00" master)' % (day)
            git_checkout = 'git checkout %s --force --quiet' % (rev_list)
            run(git_checkout.split())

        all_folders = [folder
                       for folder in os.listdir('.')
                       if not folder.startswith('.') and os.path.isdir(folder)]

        filtered = [f for f in all_folders if size(f) > 100]
        FOLDERS = sorted([f.lower() for f in filtered])
        FOLDERS = [(labnames[f] if f in labnames else f) for f in FOLDERS]
        HWS = {f: f.startswith('hw') for f in FOLDERS}
        LABS = {f: f.startswith('lab') for f in FOLDERS}

        if args['record']:
            for to_record in args['record']:
                progress('recording %s' % to_record)
                if os.path.exists(to_record):
                    try:
                        os.chdir(to_record)
                        recording = markdownify(to_record, student, specs[to_record])
                    except Exception as err:
                        recording = err
                    finally:
                        try:
                            recordings[to_record].write(recording)
                        except Exception as err:
                            warn('error! could not write recording')
                        os.chdir('..')
                else:
                    recording = '# %s — %s\n\nNo submission.\n\n\n\n\n' % (student, to_record)
                    recordings[to_record].write(recording)

        retval = "%s\t%s\t%s" % (student,
                                 ' '.join([h for h, result in HWS.items() if result]),
                                 ' '.join([l for l, result in LABS.items() if result]))

        if args['day']:
            run('git checkout master --quiet --force'.split())

    except Exception as err:
        retval = "%s: %s" % (student, err)

    finally:
        os.chdir('..')

    return retval


def main():
    students = get_config()
    args = get_args()

    # argparser puts it into a nested list because you could have two
    # occurrences of the arg, each with a variable number of arguments.
    # `--students amy max --students rives` => `[[amy, max], [rives]]`
    args['students'] = list(flatten(args['students'] or []))
    args['section'] = list(flatten(args['section'] or []))
    args['record'] = list(flatten(args['record'] or []))

    # fall back to the students.my section
    if not args['students'] and not args['section']:
        args['section'] = ['my']

    # support 'my' students and 'all' students
    if 'my' in args['section']:
        if 'my' not in students:
            warn('There is no [my] section in students.txt')
            return
        args['students'] = list(students['my'])

    elif 'all' in args['section']:
        sections = [list(students[section])
                    for section in students]
        args['students'] = list(flatten(sections))

    # sections are identified by only being one char long
    elif any([section for section in args['section']]):
        sections = []
        for section in args['section']:
            try:
                sections.append(list(students['section-%s' % section] or students[section]))
            except KeyError:
                warn('Section "%s" could not be found in ./students.txt' % section)
        args['students'] = list(flatten(sections))

    # we can only read one stdin
    if '-' in args['students']:
        args['students'] = flatten(args['students'] + sys.stdin.read().splitlines())
        args['students'] = [student for student in args['students'] if student != '-']

    elif '-' in args['record']:
        args['record'] = flatten(args['record'] + sys.stdin.read().splitlines())
        args['record'] = [to_record for to_record in args['record'] if to_record != '-']

    # stop if we still don't have any students
    if not args['students']:
        msg = ' '.join('''
            Could not find a list of students.
            You must provide the `--students` argument, the `--section` argument,
            a ./students.txt file, or a list of usernames to stdin.
        '''.split())
        warn(textwrap.fill(msg))
        return

    args['students'] = uniq(args['students'])

    table = []
    root = os.getcwd()

    if args['day']:
        args['day'] = run(['date', '-v1w', '-v-' + day, '+%Y-%m-%d'])
        print('Checking out %s at 5:00pm' % day)
    elif args['date']:
        args['day'] = args['date']
        print('Checking out %s at 5:00pm' % date)

    recordings = {}
    filenames = {}
    specs = {}
    if args['record']:
        for to_record in args['record']:
            filenames[to_record] = './logs/log-' + to_record
            recordings[to_record] = open(filenames[to_record] + '.md', 'w')
            specs[to_record] = open(root + '/specs/' + to_record + '.yaml', 'r').read()
            if specs[to_record]:
                specs[to_record] = yaml.load(specs[to_record])

    os.makedirs('./students', exist_ok=True)
    os.chdir('./students')

    try:
        for i, student in enumerate(args['students']):
            table.append(single_student(student, i + 1,
                                        args=args, specs=specs,
                                        recordings=recordings))

    finally:
        [recording.close() for name, recording in recordings.items()]
        os.chdir(root)

    if not args['quiet']:
        print('\n' + columnize(table, sort_by=args['sort_by']))


if __name__ == '__main__':
    main()
