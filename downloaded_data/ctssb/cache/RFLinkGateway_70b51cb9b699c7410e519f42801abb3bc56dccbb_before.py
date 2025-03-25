import logging
import multiprocessing
import time
import json

import serial
import Processors

class SerialProcess(multiprocessing.Process):

    def __init__(self, messageQ, commandQ, config):
        self.logger = logging.getLogger('RFLinkGW.SerialProcessing')

        self.logger.info("Starting Serial Processor...")
        multiprocessing.Process.__init__(self)

        self.messageQ = messageQ
        self.commandQ = commandQ

        self.gateway_port = config['rflink_tty_device']
        self.json_format = None
        if 'mqtt_json' in config and config['mqtt_json'] == 'true':
            self.json_format = True
            self.logger.info("   -> MQTT payloads are JSON formatted messages")
        else:
            self.json_format = False
            self.logger.info("   -> MQTT payloads are raw messages")

        self.switch_index=-1
        self.switch_num=-1
        self.switch_incl_topic = None
        if 'mqtt_switch_incl_topic' in config and config['mqtt_switch_incl_topic'] == 'true':
            self.switch_incl_topic = True
            self.logger.info("   -> Including Switch number in MQTT Topic")
        else:
            self.switch_incl_topic = False

        self.include_message = None 
        if 'mqtt_include_message' in config and config['mqtt_include_message'] == 'true':
            self.include_message = True
            if not self.json_format:
                self.logger.info("   -> Full message AND individual informations are published")
        else:
            self.include_message = False
            if not self.json_format:
                self.logger.info("   -> Full message is NOT published")

        self.output_params_processing = config['rflink_output_params_processing']
        self.ignored_devices = config['rflink_ignored_devices']
        self.logger.info("Ignoring devices: %s", self.ignored_devices)

        self.sp = serial.Serial()
        self.connect()

    def process_data(self, field, value):
        v = {field : value}
        if not field in self.output_params_processing or (not self.output_params_processing[field]):
            return v
        else:
            procs = self.output_params_processing[field]
            if isinstance(procs, list):
                if len(procs) > 0:
                    if isinstance(procs[0], list):
                        i = 0
                        for group in procs:
                            vv = value
                            for processor in group:
                                if Processors.processors[processor]:
                                    vv = Processors.processors[processor](vv)
                            if i == 0:
                                v[field] = vv
                            else:
                                v[field + "_ALT_" + str(i)] = vv
                            i = i + 1
                    else:
                        for processor in procs:
                            if Processors.processors[processor]:
                                v[field] = Processors.processors[processor](v[field])
            return v

    def close(self):
        self.sp.close()
        self.logger.debug('Serial closed')

    def prepare_output(self, data_in):
        out = []
        msg = data_in.decode("ascii")
        data = msg.replace(";\r\n", "").split(";")

        if len(data) > 1 and data[1] == '00':
            self.logger.info("%s" % (data[2]))
        else:
            self.logger.debug("Received message:%s" % (data))

            if len(data) > 3 and data[0] == '20' and data[2].split("=")[0] != 'VER' : # Special Control Command 'VERSION' returns a len=5 data object. This trick is necessary... but not very clean
                family = data[2]
                device_id = data[3].split("=")[1]  # TODO: For some debug messages there is no =

                if (device_id not in self.ignored_devices and
                    family not in self.ignored_devices and
                    "%s/%s" % (family, device_id) not in self.ignored_devices):

                    #handle switch re-inclusion in CMD(after the /R/)
                    if self.switch_incl_topic:
                        tokens=["dummy","dummy","dummy","dummy"]
                        for t in data[4:]:
                            tokens.append(t.split("=")[0])
                        if "SWITCH" in tokens:
                            self.logger.debug('Switch recognized in the data, including it in CMD if present')
                            self.switch_index=tokens.index("SWITCH")
                            self.logger.debug("Switch index in data : " + str(self.switch_index) + ";" + tokens[self.switch_index] + ";" + data[self.switch_index] )
                            self.switch_num=data[self.switch_index]
                            self.switch_num=self.switch_num.split("=")[1]
                            data.pop(self.switch_index)

                    d = {'message': msg}
                    for t in data[4:]:
                        token = t.split("=")
                        d.update(self.process_data(token[0], token[1]))

                    if not self.include_message:
                        d.pop('message')

                    if self.json_format:
                        if self.switch_incl_topic:
                            keymod =  str(self.switch_num) + "/message"
                        else:
                            keymod =  'message'

                        data_out = {
                            'action': 'NCC',
                            'topic': '',
                            'family': family,
                            'device_id': device_id,
                            'param': keymod,
                            'payload': json.dumps(d),
                            'qos': 1,
                            'timestamp': time.time()
                        }
                        out = [data_out]
                    else:
                        for key in d:
                            val = d[key]

                            #handle switch re-inclusion in CMD(after the /R/, before the "CMD")
                            if key == "CMD" and self.switch_incl_topic and self.switch_num >= 0:
                                keymod =  str(self.switch_num) + "/CMD"
                            else:
                                keymod = key

                            data_out = {
                                'action': 'NCC',
                                'topic': '',
                                'family': family,
                                'device_id': device_id,
                                'param': keymod,
                                'payload': str(val),
                                'qos': 1,
                                'timestamp': time.time()
                            }
                            out = out + [data_out]

            elif (len(data) == 3 and data[0] == '20') or (len(data) > 3 and data[0] == '20' and data[2].split("=")[0] == 'VER'):
                payload = ";".join(data[2:])
                data_out = {
                            'action': 'SCC',
                            'topic': '',
                            'family': '',
                            'device_id': '',
                            'param': '',
                            'payload': payload,
                            'qos': 1,
                            'timestamp': time.time()
                }
                out = [data_out]
        return out

    def prepare_input(self, task):
        if task['action'] == 'SCC':
            out_str = '10;%s;\n' % task['payload']
        else:
            out_str = '10;%s;%s;%s;%s;\n' % (task['family'], task['device_id'], task['param'], task['payload'])
        self.logger.debug('Sending to serial:%s' % (out_str))
        return out_str

    def connect(self):
        self.logger.info('Connecting to Serial')
        while not self.sp.isOpen():
            try:
                self.sp = serial.Serial(self.gateway_port, 57600, timeout=1)
                self.logger.debug('Serial connection established')
            except Exception as e:
                self.logger.error('Serial port is closed %s' % (e))

    def run(self):
        self.sp.flushInput()
        while True:
            try:
                if not self.commandQ.empty():
                    task = self.commandQ.get()
                    # send it to the serial device if not present in the ignored list
                    if task['device_id'] not in self.ignored_devices:
                        self.sp.write(self.prepare_input(task).encode('ascii'))
                    else:
                        self.logger.debug('Nothing sent to serial: device_id (%s) is in the devices ignored list.' % (task['device_id']))
            except Exception as e:
                self.logger.error("Send error:%s" % (e))
            try:
                if (self.sp.inWaiting() > 0):
                    data = self.sp.readline()
                    task_list = self.prepare_output(data)
                    for task in task_list:
                        self.logger.debug("Sending to Q:%s" % (task))
                        self.messageQ.put(task)
                else:
                    time.sleep(0.01)
            except Exception as e:
                self.logger.error('Error received: %s' % (e))
                self.connect()
