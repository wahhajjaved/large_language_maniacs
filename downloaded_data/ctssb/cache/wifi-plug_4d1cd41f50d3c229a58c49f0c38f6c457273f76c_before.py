import json
import subprocess
import sys
import jsonify
from subprocess import call
from flask import abort, Flask

app = Flask(__name__)

def get_switch(switch_key):
    if switch_key in json_data.keys():
        return json_data[switch_key]
    else:
        return None

def switch(switch_key, state):
    switch_cfg = get_switch(switch_key)

    if switch_cfg is None:
        abort(404)
    else:
        mac = switch_cfg['mac']
        code = switch_cfg['code']
        rfslave = None
        if 'rfslave' in switch_cfg.keys():
            rfslave = switch_cfg['rfslave']

        call_array = []
        call_array.append("php")
        call_array.append("wifi_cmd.php")
        call_array.append(mac)
        call_array.append(code)
        call_array.append(str(state))

        print ("Mac  " + mac)
        print ("Code " + code)
        if rfslave is not None:
            print ("Rfslave " + rfslave)
            call_array.append(rfslave)

        #print (call_array)
        subprocess.run(call_array)

@app.route('/')
@app.route('/switch')
def index():
    return "Medion/Lidl Wifi Switch Control"

@app.route('/switch/config')
def config():
    return jsonify(json_data)

@app.route('/switch/activate/<string:switch_name>', methods=['GET'])
def activate_switch(switch_name):
    switch(switch_name, 1)
    return "Activate " + switch_name

@app.route('/switch/deactivate/<string:switch_name>', methods=['GET'])
def deactivate_switch(switch_name):
    switch(switch_name, 0)
    return "De-Activate " + str(switch_name)

if __name__ == '__main__':
    with open('config.json') as jsonfile:
        json_data = json.load(jsonfile)

    if not json_data:
        sys.exit()

    app.run(host= '0.0.0.0')
