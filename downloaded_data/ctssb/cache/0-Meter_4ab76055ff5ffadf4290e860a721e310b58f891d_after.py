# -*- coding: utf-8 -*-
"""
Created on Sat Mar  5 23:47:16 2016

-0-Meter Main Class-

0-Meter is a configurable load testing framework for 0MQ-Based
Messaging Applications.

It reads from a configuration XML to determine how to proceed with test cases

We support sending an individual file as well as defining variables and
updating values with those from a separate CSV.

@author: alex barry
"""

import xml.etree.ElementTree as ET
import sys
import logging
import zmq
import os
import csv
import json
import time

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
except Exception as e:
    print('Unable to load scheduling libraries due to error:')
    print(e)


# There is a single Global Session
# This class stores config variables,
# as well as global variables
class Session(object):
    def __init__(self):
        self.param_list = {}

        #Global Variables
        self.msg_list = []
        self.response_list = []
        self.context = None
        self.socket = None
        self.num_msg = 0
        self.base_msg = ""

        #Global Variables for tracking response times
        self.resp_time_list = []
        self.time_list = []

    def teardown(self):
        self.param_list.clear()

    def __len__(self):
        return len(self.param_list)

    def __getitem__(self, key):
        return self.param_list[key]

    def __setitem__(self, key, value):
        self.param_list[key] = value

    def __delitem__(self, key):
        del self.param_list[key]

    def __iter__(self):
        return iter(self.param_list)

    def configure(self, config_file):
        # Read the config file
        self.param_list['single_message'] = False
        self.param_list['multi_message'] = False
        self.param_list['include_csv'] = False
        self.param_list['span_interval'] = False

        self.param_list['msg_location'] = ""
        self.param_list['msg_folder_location'] = ""
        self.param_list['msg_extension'] = ""
        self.param_list['interval'] = 5
        self.param_list['csv_location'] = ""
        self.param_list['csv_var_start'] = ""
        self.param_list['csv_var_end'] = ""
        self.param_list['out_0mq_connect'] = ""
        self.param_list['out_0mq_connect_type'] = ""
        self.param_list['timeout'] = 0
        self.param_list['log_file'] = ""
        self.param_list['log_level'] = ""

        self.param_list['parse_responses'] = False
        self.param_list['fail_on_response'] = False
        self.param_list['response_field_path'] = ""
        self.param_list['response_success_value'] = ""
        self.param_list['response_output_csv'] = ""
        self.param_list['response_key_path'] = ""

        #Parse the config XML and pull the values
        tree = ET.parse(sys.argv[1])
        root = tree.getroot()
        for element in root:
            if element.tag == 'Behavior':
                for param in element:
                    if param.tag == 'Single_Message':
                        if param.text == 'True' or param.text == 'true':
                            self.param_list['single_message'] = True
                    if param.tag == 'Multi_Message':
                        if param.text == 'True' or param.text == 'true':
                            self.param_list['multi_message'] = True
                    if param.tag == 'Include_CSV':
                        if param.text == 'True' or param.text == 'true':
                            self.param_list['include_csv'] = True
                    if param.tag == 'Span_Over_Interval':
                        if param.text == 'True' or param.text == 'true':
                            self.param_list['span_interval'] = True
                    if param.tag == 'Parse_Responses':
                        if param.text == 'True' or param.text == 'true':
                            self.param_list['parse_responses'] = True
                    if param.tag == 'Fail_On_Response':
                        if param.text == 'True' or param.text == 'true':
                            self.param_list['fail_on_response'] = True
            if element.tag == 'Message':
                for param in element:
                    if param.tag == 'Message_Location':
                        self.param_list['msg_location'] = param.text
                    if param.tag == 'Message_Folder_Location':
                        self.param_list['msg_folder_location'] = param.text
                    if param.tag == 'Message_Extension':
                        self.param_list['msg_extension'] = param.text
                    if param.tag == 'Interval':
                        self.param_list['interval'] = float(param.text)
                    if param.tag == 'CSV_Location':
                        self.param_list['csv_location'] = param.text
                    if param.tag == 'Variable_Start_Character':
                        self.param_list['csv_var_start'] = param.text
                    if param.tag == 'Variable_End_Character':
                        self.param_list['csv_var_end'] = param.text
            if element.tag == 'ZeroMQ':
                for param in element:
                    if param.tag == 'Outbound_Connection':
                        self.param_list['out_0mq_connect'] = param.text
                    if param.tag == 'Outbound_Connection_Type':
                        self.param_list['out_0mq_connect_type'] = param.text
                    if param.tag == "Timeout":
                        self.param_list['timeout'] = int(float(param.text))
            if element.tag == 'Logging':
                for param in element:
                    if param.tag == 'Log_File':
                        self.param_list['log_file'] = param.text
                    elif param.tag == 'Log_Level':
                        self.param_list['log_level'] = param.text
            if element.tag == 'Response':
                for param in element:
                    if param.tag == 'Field_Path':
                        self.param_list['response_field_path'] = param.text
                    if param.tag == 'Key_Path':
                        self.param_list['response_key_path'] = param.text
                    if param.tag == 'Success_Value':
                        self.param_list['response_success_value'] = param.text
                    if param.tag == 'Output_Csv':
                        self.param_list['response_output_csv'] = param.text

    def __str__(self):
        ret_str = "Session:\n"
        for key, val in self.param_list.iteritems():
            ret_str = ret_str + "%s: %s\n" % (key, val)
        return ret_str


# Define the single global session
session = None


# Replace a a set of variables within a message
# base_text - The message contianing variables
# variable_dict - A dictionary of variable names & values
def replace_variables(msg, variable_dict):
    # The dict uses different functions to return list generators of key/value pairs in 2.x vs 3.x
    # So, we use the sys module to detect at run time and use the correct method
    if sys.version_info[0] < 3:
        for key, val in variable_dict.iteritems():
            msg = msg.replace(key, val)
    else:
        for key, val in variable_dict.items():
            msg = msg.replace(key, val)
    return msg


# Parse a configuration path in the format root.obj[1
def parse_config_path(field_path):
    logging.debug("Entering Parsing of Response Field Path")
    # Parse the Field Path
    field_path_list = []
    # Pull the first value in assuming the message is an object
    cut_index = 0
    pd_index = field_path.find('.')
    ar_index = field_path.find('[')
    if pd_index < ar_index:
        cut_index = pd_index
    else:
        cut_index = ar_index
    path_list_tuple = ('.', field_path[0:cut_index])
    field_path = field_path[cut_index:]
    while(True):
        logging.debug("Parsing Iteration of Response Field Path, remaining field path: %s" % field_path)

        # Find the first delimiter
        cut_index = 0
        pd_index = field_path.find('.',1)
        ar_index = field_path.find('[',1)
        if pd_index > ar_index:
            cut_index = pd_index
        else:
            cut_index = ar_index
        path_list_tuple = None

        # If another . or [ is found
        if cut_index > -1:
            path_list_tuple = (field_path[0:1], field_path[1:cut_index])
            field_path = field_path[cut_index:]
        else:
            path_list_tuple = (field_path[0:1], field_path[1:])
            break
        field_path_list.append(path_list_tuple)

    return field_path_list


# Find a JSON Element within the specified doc, given the specified parsed path list
def find_json_path(json_doc, path_list):
    current_elt = json_doc
    # Iterate over the path_list to get to the element we want to match against
    for path_element in path_list:
        logging.debug("Entering Path Element %s -- %s" % (path_element[0], path_element[1]))
        if (path_element[0] == '.'):
            current_elt = current_elt[path_element[1]]
        elif (path_element[0] == '['):
            current_elt = current_elt[int(path_element[1])]
    return current_elt


# Populate the Base Message Global Variable
def build_msg(msg_path):
    #Open the base message File
    msg = None
    try:
        with open(msg_path, 'r') as f:
            msg = f.read()
            logging.debug("Base Message file opened")
    except Exception as e:
        logging.error('Exception during read of base message')
        logging.error(e)
    return msg


# Build a message list from a CSV
def build_msg_list_from_csv(msg, config_csv, csv_var_start, csv_var_end):

    message_list = []

    #Open the CSV File and start building Message Files
    with open(config_csv, 'rb') as csvfile:
        logging.debug('CSV File Opened')
        reader = csv.reader(csvfile, delimiter=',', quotechar='|')

        header_row = reader.next()
        header_dict = {}

        for row in reader:
            repl_dict = {}
            for i in range(0, len(row)):
                new_dict_key = "%s%s%s" % (csv_var_start, header_row[i], csv_var_end)
                repl_dict[new_dict_key] = row[i]
            message_list.append(replace_variables(msg, repl_dict))
    return message_list


# Select all files in a folder
def select_files_in_folder(dir, ext):
    for file in os.listdir(dir):
        if file.endswith('.%s' % ext):
            yield os.path.join(dir, file)

# Create an empty file
def touch(file_path):
    open(file_path, 'a').close()


# Post a message from the global variable list to the global socket
# When messages are sent on a scheduled interval, this is called on a
# background thread
def post_message():
    global session
    if len(session.msg_list) > 0:
        try:
            #Send the message
            msg = session.msg_list.pop(0)
            session.time_list.append(time.time())
            session.socket.send_string(msg + "\n")
            logging.info("Message sent:")
            logging.info(msg)

            if session['out_0mq_connect_type'] == "REQ":
                #Recieve the response
                resp = session.socket.recv()
                session.response_list.append(resp)
                session.resp_time_list.append(time.time())
                logging.info("Response Recieved:")
                logging.info(resp)
        except Exception as e:
            print("Error sending")
            logging.error('Exception')
            logging.error(e)
            del session.msg_list[:]
            session.socket.close()
            sys.exit(1)
    else:
        sys.exit(1)


# Execute the main function and start 0-meter
def execute_main(config_file):
    global session
    session = Session()
    base_msg = session.base_msg
    msg_list = session.msg_list

    # Set up the session
    session.configure(sys.argv[1])

    #Set up the file logging config
    if session['log_level'] == 'Debug':
        logging.basicConfig(filename=session['log_file'], level=logging.DEBUG)
    elif session['log_level'] == 'Info':
        logging.basicConfig(filename=session['log_file'], level=logging.INFO)
    elif session['log_level'] == 'Warning':
        logging.basicConfig(filename=session['log_file'], level=logging.WARNING)
    elif session['log_level'] == 'Error':
        logging.basicConfig(filename=session['log_file'], level=logging.ERROR)
    else:
        print("Log level not set to one of the given options, defaulting to debug level")
        logging.basicConfig(filename=session['log_file'], level=logging.DEBUG)

    try:
        #Attempt to connect to the outbound ZMQ Socket
        logging.debug("Attempting to connect to outbound 0MQ Socket with connection:")
        logging.debug(session['out_0mq_connect'])
        session.context = zmq.Context()
        if (session['timeout'] > 0):
            session.context.setsockopt(zmq.RCVTIMEO, session['timeout'])
            session.context.setsockopt(zmq.LINGER, 0)
        if session['out_0mq_connect_type'] == "REQ":
            session.socket = session.context.socket(zmq.REQ)
            session.socket.connect(session['out_0mq_connect'])
        elif session['out_0mq_connect_type'] == "PUB":
            socket = context.socket(zmq.PUB)
            socket.connect(session['out_0mq_connect'])
        else:
            logging.error("Unknown Connection Type encountered")
            sys.exit(1)
    except Exception as e:
        logging.error('Exception')
        logging.error(e)
        print("Exception encountered connecting to 0MQ Socket, please see logs for details")
        sys.exit(1)

    #Now, we need to determine how many messages we're sending and build them
    if session['single_message']:
        logging.debug("Building Single Message")
        session.num_msg=1
        base_msg = build_msg( os.path.abspath(session['msg_location']) )
        msg_list.append( base_msg )
    elif session['multi_message'] and session['include_csv']:
        logging.debug("Building Messages from CSV")
        #Pull the correct file paths
        msg_path = os.path.abspath(session['msg_location'])
        config_csv = os.path.abspath(session['csv_location'])
        base_msg = build_msg(msg_path)

        #Read the CSV, Build the message list, and take it's length for num_msg
        msg_list = build_msg_list_from_csv(base_msg, config_csv, session['csv_var_start'], session['csv_var_end'])
        session.num_msg=len(msg_list)

    elif session['multi_message']:
        logging.debug("Building Messages from Folder")
        msg_folder = select_files_in_folder(os.path.abspath(session['msg_folder_location']), session['msg_extension'])

        #Build the message list
        for path in msg_folder:
            msg_list.append( build_msg(os.path.abspath(path)) )
        session.num_msg = len(msg_list)

    #Now, we can execute the test plan
    if session['span_interval'] == False:
        logging.debug("Sending Messages all at once")
        while len(msg_list) > 0:
            post_message()
    else:
        logging.debug("Set up the Background Scheduler")
        scheduler = BackgroundScheduler()
        time_interv = num_msg / session['interval']
        logging.debug("Interval: %s" % (time_interv))
        interv = IntervalTrigger(seconds=time_interv)
        scheduler.add_job(post_message, interv)
        scheduler.start()
        time.sleep(session['interval'])

    # Perform any necessary response parsing
    if session['parse_responses']:
        success_field_list = parse_config_path(session['response_field_path'])
        success_key_list = parse_config_path(session['response_key_path'])
        with open(session['response_output_csv'], 'wb') as csvfile:
            csvwriter = csv.writer(csvfile, delimiter=',',
                        quotechar='|', quoting=csv.QUOTE_MINIMAL)
            csvwriter.writerow(['Key'])
            for response in session.response_list:
                # JSON Response Parsing
                if (session['msg_extension'] == 'json'):
                    logging.debug("Parsing Response: %s" % response)
                    parsed_json = None
                    try:
                        parsed_json = json.loads(response)
                    except Exception as e:
                        try:
                            parsed_json = json.loads(response[1:])
                        except Exception as e:
                            logging.error('Unable to parse response: %s' % response)
                    if parsed_json is not None:

                        # Write the response key to the CSV
                        key_val = find_json_path(parsed_json, success_key_list)
                        csvwriter.writerow([key_val])

                        # Test the success value and exit if necessary
                        if session['fail_on_response']:
                            success_val = find_json_path(parsed_json, success_field_list)
                            if success_val != session['response_success_value']:
                                sys.exit(1)
    return 0;


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("Input Parameters:")
        print("Configuration File: The file name of the Configuration XML")
        print("Example: python 0-meter.py config.xml")
    elif len(sys.argv) != 2:
        print("Wrong number of Input Parameters")
    else:
        print("Input Parameters:")
        print("Configuration File: %s" % (sys.argv[1]))
    execute_main(sys.argv[1])
