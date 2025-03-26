#!/usr/bin/env python3

# samil_upload.py
#
# Daemon for automatically uploading Samil Power data to PVOutput. Uses samil.py
# and pvoutput.py

import samil
import pvoutput
# ExitStack needed from own module because it is only available from Python 3.3
# onwards in the standard library (I use Python 3.2 on RPi).
import exitstack

import sched
import time
import configparser
import logging
import os.path

def applies(inverter, section):
    """Returns whether the inverter applies for given configuration section."""
    if not section['IP address']:
        return True
    if section['IP address'] == inverter.addr[0]:
        return True
    return False

def next_timestamp(boundary):
    """Returns the timestamp for the first moment after current time on the
    given boundary."""
    timestamp = time.time()
    return timestamp + boundary - timestamp % boundary

def upload(pv, inverters, scheduler, timestamp, boundary):
    """Retrieves and uploads inverter data, and schedules the next upload."""
    values = [inverter.request_values() for inverter in inverters]
    # Filter systems with normal operating mode
    values = [val for val in values if val['operating_mode'] == 'normal']

    if values:
        data = {
            'd': time.strftime('%Y%m%d'),
            't': time.strftime('%H:%M'),
            'v1': round(sum(value['energy_today'] for value in values) * 1000),
            'v2': sum(value['output_power'] for value in values),
            'v5': sum(value['internal_temp'] for value in values) / len(values),
            'v6': sum(value['grid_voltage'] for value in values) / len(values)
        }
        logging.info('Uploading: %s', data)
        pv.add_status(data)
    else:
        logging.info('Not uploading, no inverter has operating mode normal')
    sched_args = (pv, inverters, scheduler, timestamp + boundary, boundary)
    scheduler.enterabs(timestamp + boundary, 1, upload, sched_args)

def main():
    """Reads configuration, connects to inverters and schedules uploads."""
    # Read config
    config = configparser.ConfigParser()
    config_file = os.path.dirname(os.path.abspath(__file__)) + '/samil_upload.ini'
    config.read_file(open(config_file))
    interface_ip = ''
    if config.has_option('DEFAULTS', 'Interface IP'):
        interface_ip = config['DEFAULTS']['Interface IP']
    sections = config.sections() if config.sections() else ['DEFAULTS']
    logging.debug('Read configuration: %s', config)

    # Context manager to gracefully close sockets
    with exitstack.ExitStack() as stack:

        # Connect to inverters & match sections
        section_inverter = []
        while sections:
            inverter = stack.enter_context(samil.Inverter(interface_ip))
            new_sections = []
            for section_name in sections:
                if applies(inverter, config[section_name]):
                    section_inverter += (config[section_name], inverter)
                    logging.info('Match with configuration %s', section_name)
                else:
                    new_sections += section_name
            sections = new_sections

        # Find equal PVOutput systems
        systems = dict()
        for section, inverter in section_inverter:
            pv = pvoutput.System(section['API key'], section['System ID'])
            if pv in systems:
                systems[pv] = (section.getint('Status interval') * 60, [inverter])
            else:
                systems[pv][1] += inverter
        logging.info('Systems configuration: %s', systems)

        # Schedule uploads
        scheduler = sched.scheduler(time.time, time.sleep)
        for pv, (boundary, inverters) in systems.items():
            timestamp = next_timestamp(boundary)
            sched_args = (pv, inverters, scheduler, timestamp, boundary)
            scheduler.enterabs(timestamp, 1, upload, sched_args)
        logging.info('Scheduled first uploads')

        # Run scheduler
        scheduler.run()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
