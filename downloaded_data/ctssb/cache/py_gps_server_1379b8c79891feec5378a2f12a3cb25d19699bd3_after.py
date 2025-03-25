from flask import Flask, request, jsonify, render_template
import models
import config
import datetime
import const
app = Flask(__name__)


def convert_coordinate(coord):
    degrees = float(coord[:2])
    min_sec = float(coord[2:]) / 60

    return degrees + min_sec


def write_to_log(data):
    with open(config.log_file, "a") as f:
        f.write("Recieved parameter: %s \r\n" % data)


def write_to_db(lat, lon, alt, speed, token):
    point = models.Point()
    point.lat = lat
    point.lon = lon
    point.alt = alt
    point.speed = speed
    point.token = token
    point.save()

def write_log_to_db(error, device):
    report = models.Report()
    report.error_desc = error
    report.device_id = device
    report.save()

@app.route("/")
def hello():
    return "Hello World!"


@app.route("/gps", methods=['GET', 'POST'])
def serve():
    lat_raw = request.args.get('latitude', '')
    if not lat_raw:
        lat_raw = request.args.get('lat', '')

    lon_raw = request.args.get('longitude', '')
    if not lon_raw:
        lon_raw = request.args.get('lon')

    alt_raw = request.args.get('altitude', '')
    if not alt_raw:
        alt_raw = request.args.get('alt', '0')

    speed_raw = request.args.get('speed', '0')

    token = request.args.get('device', 1)


    if not lat_raw or not lon_raw or not token:
        return jsonify({
            'error': 400,
            'message': 'Bad request. Provide lat-lon or latitude-longitude and a token',
        })

    lat = convert_coordinate(lat_raw)
    lon = convert_coordinate(lon_raw)
    alt = float(alt_raw)
    speed = float(speed_raw)

    write_to_db(lat, lon, alt, speed, token)

    return jsonify({
        'error': 0,
        'lat': lat,
        'lon': lon,
        'alt': alt,
        'speed': speed
    })


@app.route('/list', methods=['GET', 'POST'])
def list():
    device_id = request.args.get('token', None)
    if not device_id:
        return jsonify({
            'points': [],
            'error': 1,
            'status': 'Need to pass your device ID.'
        })
    points = models.Point.select().filter(token=device_id).order_by(models.Point.created_at.asc())
    reports = models.Report.select().filter(device_id=device_id).order_by(models.Report.created_at.asc())
    data = [point.json for point in points][const.LAST_IDX:]
    reports = [r.json for r in reports]

    return jsonify({
        'points': data,
        'reports': reports,
        'error': 0,
    })


@app.route('/view', methods=['GET', ])
def view():

    return render_template("map.html")


@app.route('/err', methods=['GET', ])
def err():
    print(request.args)
    error = request.args.get('error', None)
    device_id = request.args.get('device', None)
    if not device_id:
        return jsonify({
            'error': 1,
            'status': 'Need to pass your device ID.'
        })
    if not error:
        return jsonify({
            'error': 1,
            'status': 'Error msg is not passed.',
            'reported': 0
        })
    data = '[Error: %s, Device ID: %s, Created at: %s ]'\
           % (error, device_id, datetime.datetime.now().strftime("%d.%m.%Y, %H:%M:%S"))
    write_to_log(data)
    write_log_to_db(error, device_id)

    return jsonify({
        'error': 0,
        'reported': 1,
    })


# @app.route('/log', methods=['GET', ])
# def log():
#     # points = models.Point.select().order_by(models.Point.created_at.desc())
#     # data = [point.json_map for point in points]
#
#     return render_template("log.html")


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
