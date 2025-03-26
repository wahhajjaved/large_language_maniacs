# Copyright (C) 2015 Haruhiko Matsuo <halm.matsuo@gmail.com>
#
#  Distributed under the MIT License.
#  See accompanying file LICENSE or copy at
#  http://opensource.org/licenses/MIT

"""Parser"""

import re
import csv
import os


FJ_VERSION_TAG = 'Fujitsu Performance Profiler Version '
DATE_TAG = 'Measured time'
PROGRAM_TYPE_TAG = 'Type of program'
CPU_TAG = 'CPU frequency'
RANGE_TAG = 'Measured range'
PM_TAG = 'Performance monitor'
EVENT_TABLE_PATH = 'events.csv'


def _get_measured_rage(line):
    if re.match(RANGE_TAG, line[0]):
        pass
    return line[1]


def _get_date(line):
    if re.match(DATE_TAG, line[0]):
        pass
    return line[1]


def _get_cpu_freqency(line):
    if not re.match(CPU_TAG, line[0]):
        pass
    matched = re.search('(\d+)(\s\(MHz\))', line[1])
    return int(matched.group(1))


def _get_type_of_program(line):
    if re.match(PROGRAM_TYPE_TAG, line[0]):
        pass
    return line[1]


def _get_profiler_version(line):
    if re.match(FJ_VERSION_TAG, line[0]):
        pass
    return line[0].strip(FJ_VERSION_TAG)


def _init_parser(itr):
    ver = _get_profiler_version(itr.next())
    date = _get_date(itr.next())
    cpu = _get_cpu_freqency(itr.next())
    prog_type = _get_type_of_program(itr.next())
    measured_range = _get_measured_rage(itr.next())
    return (ver, date, cpu, prog_type, measured_range)


def _main_parser(itr, pa_range_label):
    module_path = os.path.dirname(os.path.abspath(__file__))
    full_file_path = os.path.join(module_path, EVENT_TABLE_PATH)
    with open(full_file_path) as f:
        pa_events = dict()
        next(f)  # skip header

        for row in csv.reader(f):
            pa_events[str(int(row[0], 2))] = row[1:]

    parsed_dat = {}
    ev_id = []
    dic_keys = 0

    for line in itr:

        if re.match('^Performance monitor', line[0]):
            elem = line[0].split(' - ')
            monitor = elem[2].split()
            monitor_level = monitor[0]

            if monitor_level == 'Thread':
                thread_id = int(monitor[1])
                dataset_id = (monitor_level, process_id, thread_id)
            elif monitor_level == 'Process':
                process_id = int(monitor[1])
                dataset_id = (monitor_level, process_id)
            elif monitor_level == 'Application':
                dataset_id = (monitor_level,)
                # When the number of process is one, process_id is called
                # before its value is set. To avoid this problem, set zero
                # as the default value.
                process_id = 0
            else:
                exit()

            ev_id = []
            range_counter = 0

        elif re.match('^Range$', line[0]):
            range_counter += 1

            if len(ev_id) == 8:
                pass
            elif len(ev_id) == 4:
                ev_id += [pa_events[l][i] for i, l
                          in enumerate(line[1:5], start=4)]
            elif len(ev_id) == 0:
                ev_id = [pa_events[l][i] for i, l
                         in enumerate(line[1:5], start=0)]

            if range_counter == 1:
                dic_keys = tuple(ev_id[0:4])
            elif range_counter == 2:
                dic_keys = tuple(ev_id[4:8])
            else:
                exit()

        else:
            id = line[0]
            if id != pa_range_label:
                continue

            counter_vals = [int(i) for i in line[1:]]
            dic = dict(zip(dic_keys, counter_vals))
            if dataset_id in parsed_dat:
                parsed_dat[dataset_id].update(dic)
            else:
                parsed_dat[dataset_id] = dic

    return parsed_dat


def parser(itr, pa_range_label):
    env_info = _init_parser(itr)
    counter_vals = _main_parser(itr, pa_range_label)
    return (env_info, counter_vals)
