import eventlet
eventlet.monkey_patch()

from flask import Flask, make_response, jsonify
from fractal_landscape import build_landscape

import eventlet.wsgi
import numpy as np
import requests
import datetime
import traceback

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret'

# microservices_urls = {
#   'socket':'http://localhost:9000',
#   'terrain': 'http://159.203.226.234',
#   'field_objects': 'http://192.241.215.101', 
# }
microservices_urls = {
    'socket': 'http://104.236.155.241',
    'terrain': 'http://159.203.226.234:7000',
    'field_objects': 'http://192.241.215.101:7001',
}

@app.route('/')
def test_connect():
    return 'Docker hosting image on port 7000'


@app.route('/get_landscape')
def get_landscape():
    seed = datetime.datetime.now()
    seed = seed.hour + 24 * (seed.day + 31 * seed.month) * 4352 + 32454354
    print('get landscape', terrain)
    # terrain = build_landscape(250, 250, seed=seed, octaves=1).tolist()
    terrain = np.zeros((250, 250)).tolist()
    requests.post(microservices_urls['field_objects']+'/store_terrain', json = {'terrain':terrain})
    requests.post(microservices_urls['socket']+'/send_terrain', json = {'terrain':terrain})
    # Delete once stored in Redis
    print('in get landscape')
    # return jsonify({'terrain': terrain}, 201)
    # return jsonify('ok')
    return 'ok'

# error handling
@app.errorhandler(500)
def internal_error(exception):
    """Show traceback in the browser when running a flask app on a production server.
    By default, flask does not show any useful information when running on a production server.
    By adding this view, we output the Python traceback to the error 500 page.
    """
    trace = traceback.format_exc()
    return("<pre>" + trace + "</pre>"), 500

if __name__ == '__main__':
    print('running')
    # app.run(host='0.0.0.0', port=7000, debug=True)
    eventlet.wsgi.server(eventlet.listen(('', 7000)), app, debug=True)

