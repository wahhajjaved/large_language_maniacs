"""`main` is the top level module for the blueprint indexer Flask app)"""

from google.appengine.datastore.datastore_query import Cursor
from google.appengine.ext import blobstore, ndb
from flask import Flask, render_template, request, make_response, redirect, url_for
from starmade import Blueprint
from struct import Struct
from werkzeug import parse_options_header
import json
import math
import logging
import starmade
import zipfile

app = Flask(__name__)

millnames=['', 'K', 'M', 'B', 'T']
def millify(n):
    """Converts a number into it's short scale abbreviation

    From here: http://stackoverflow.com/a/3155023/153407
    """
    n = float(n)
    millidx = max(0,min(len(millnames)-1,
                  int(math.floor(math.log10(abs(n))/3))))
    return '%.0f %s'%(n/10**(3*millidx),millnames[millidx])

@app.route("/upload")
def upload():
    uploadUri = blobstore.create_upload_url('/submit',
                                            gs_bucket_name='blueprints')
    return render_template('upload.html', uploadUri=uploadUri)

@app.route("/submit", methods=['POST'])
def submit():
    if request.method == 'POST':
        f = request.files['file']
        power_recharge = starmade.valid_power(request.form['power_recharge'])
        power_capacity = starmade.valid_power(request.form['power_capacity'])
        blueprint_title = None
        header = f.headers['Content-Type']
        parsed_header = parse_options_header(header)
        blob_key = parsed_header[1]['blob-key']

        blue_key = process_blueprint(blob_key, blueprint_title, power_recharge,
                                     power_capacity)

        return render_template('finished_upload.html',
                               blue_key=blue_key.urlsafe())

def process_blueprint(blob_key, blueprint_title, power_recharge=0,
                      power_capacity=0, blue_key=None):
    blob_info = blobstore.get(blob_key)
    blob = blob_info.open()

    with zipfile.ZipFile(file=blob, mode="r") as zip_file:
        for filename in (name for name in zip_file.namelist()
                         if name.endswith('/header.smbph')
                            and name.count('/') <= 1):
            blueprint_title = filename[:filename.find("/")].replace("_", " ")
            header_blob = zip_file.open(filename)
            return process_header(blob_key, header_blob, blueprint_title,
                                  power_recharge, power_capacity, blue_key)

def process_header(blob_key, blob, blueprint_title, power_recharge=0,
                   power_capacity=0, blue_key=None):
    version_struct = Struct('>i')
    ver = version_struct.unpack(blob.read(version_struct.size))[0]
    if ver > 65535:
        endian = '<'
        ver = ver<<24&0xFF000000|ver<<8&0xFF0000|ver>>8&0xFF00|ver>>24&0xFF
    else:
        endian = '>'
    header_struct = Struct(endian + 'I3f3fi')
    block_struct = Struct(endian + 'hi') # BlockID<short>, blockCount<int>

    result = []
    result = header_struct.unpack(blob.read(header_struct.size))

    entity_type = result[0]

    # -2 since core-only blueprint gives 2, -1 respectively.
    length = int(result[6] - result[3]) - 2
    width = int(result[4] - result[1]) - 2
    height = int(result[5] - result[2]) - 2

    context = {
       "title": blueprint_title,
       "version": ver,
       "entity": entity_type,
       "length": length,
       "width": width,
       "height": height,
       "power_recharge": {"base": 1},
       "power_capacity": {"base": 50000},
       "power_usage": {},
       "thrust": "None",
       "shields": {"capacity": 220, "recharge": 0},
       "systems" : {"medical": 0, "factory": 0}
    }

    ship_dimensions = context['length'] + context['width'] + context['height']
    element_count = result[7]
    element_list = []
    total_block_count = 0
    total_mass = 0
    power_recharge_rating = 0
    complex_systems = {"salvage": 0, "astrotech": 0, "power_drain": 0,
                       "power_supply": 0, "shield_drain": 0, "shield_supply": 0}

    for element in xrange(0, element_count):
        new_element = block_struct.unpack(blob.read(block_struct.size))
        element_list.append([new_element])
        block_id = new_element[0]
        block_count = new_element[1]
        total_block_count += block_count
        total_mass += block_count * starmade.NON_STANDARD_MASS.get(block_id, 0.1)
        if block_id == 2: # Power Block
            power_output = starmade.calc_power_output(block_count,
                                                      ship_dimensions)
            ideal_generator = round(power_output, 1)
            if power_recharge > ideal_generator or power_recharge == 0:
               context['power_recharge']['ideal_generator'] = ideal_generator
               context['power_efficieny_gauge'] = 100.0
               power_recharge_rating = ideal_generator
            else:
               power_efficieny_gauge = power_recharge / ideal_generator
               context['power_efficiency_gauge'] = round(power_efficieny_gauge * 100.0,1)
               context['power_recharge']['power_recharge'] = power_recharge
               power_recharge_rating = power_recharge
        elif block_id == 331: # Power Capacitor
            power_storage = starmade.calc_power_capacity(block_count)
            ideal_capacitor = round(power_storage, 1)
            if entity_type == 0:
                base_capacity = 50000
            else:
                base_capacity = 0
            context['ideal_capacitor'] = ideal_capacitor
            if power_capacity > ideal_capacitor + base_capacity or power_capacity == 0:
               context['power_capacity']['ideal_capacitor'] = ideal_capacitor
            else:
               context['power_capacity']['power_capacity'] = power_capacity
               power_capacity_gauge = power_capacity / ideal_capacitor
               context['power_capacity_efficiency_gauge'] = round(power_capacity_gauge * 100.0,1)
        elif block_id == 8: # Thruster Block
            context['thrust'] = round(starmade.calc_thrust(block_count),1)
            context['power_usage']['thruster'] = round(-starmade.calc_thrust_power(block_count), 0)
        elif block_id == 3: # Shield Capacitor Block
            context['shields']['capacity'] = round(starmade.calc_shield_capacity(block_count), 0)
        elif block_id == 478: # Shield Recharger Block
            shield_power_standby = starmade.calc_shield_power(block_count)
            shield_power_active = starmade.calc_shield_power(block_count, True)
            shield_recharge = starmade.calc_shield_recharge(block_count)
            context['shields']['recharge'] = round(shield_recharge, 0)
            context['power_recharge']['shields'] = -round(shield_power_standby, 0)
            context['power_usage']['shield_recharge'] = -round(shield_power_active, 0)
        elif block_id == 15: # Radar Jamming
            context['systems']['radar_jamming'] = block_count
        elif block_id == 22: # Cloaking
            context['systems']['cloaking'] = block_count
        elif block_id == 291: # Faction
            context['systems']['faction'] = block_count
        elif block_id == 347: # Shop
            context['systems']['shop'] = block_count
        elif block_id == 94: # Plex Undeathinator
            context['systems']['plexundeathinator'] = block_count
        elif block_id >= 211 and block_id <= 215: # Factory equipment
            context['systems']['factory'] += block_count
        elif block_id == 121: # AI
            context['systems']['bobby_ai'] = block_count
        elif block_id == 445 or block_id == 446: # Medical Equipment
            context['systems']['medical'] += block_count
        elif block_id == 47: # Cameras
            context['systems']['camera'] = block_count
        elif block_id == 4: # Salvage Computer
            if complex_systems['salvage'] == 0:
                complex_systems['salvage'] = 1
            else:
                context['systems']['salvage'] = complex_systems['salvage']
        elif block_id == 24: # Salvage Modules
            if complex_systems['salvage'] == 0:
                complex_systems['salvage'] = block_count
            else:
                context['systems']['salvage'] = block_count
        elif block_id == 39: # Astrotech Computer
            if complex_systems['astrotech'] == 0:
                complex_systems['astrotech'] = 1
            else:
                context['systems']['astrotech'] = complex_systems['astrotech']
        elif block_id == 30: # Astrotech Modules
            if complex_systems['astrotech'] == 0:
                complex_systems['astrotech'] = block_count
            else:
                context['systems']['astrotech'] = block_count
        elif block_id == 332: # Power Drain Computer
            if complex_systems['power_drain'] == 0:
                complex_systems['power_drain'] = 1
            else:
                context['systems']['power_drain'] = complex_systems['power_drain']
        elif block_id == 333: # Power Drain Modules
            if complex_systems['power_drain'] == 0:
                complex_systems['power_drain'] = block_count
            else:
                context['systems']['power_drain'] = block_count
        elif block_id == 334: # Power Supply Computer
            if complex_systems['power_supply'] == 0:
                complex_systems['power_supply'] = 1
            else:
                context['systems']['power_supply'] = complex_systems['power_supply']
        elif block_id == 335: # Power Drain Modules
            if complex_systems['power_supply'] == 0:
                complex_systems['power_supply'] = block_count
            else:
                context['systems']['power_supply'] = block_count
        elif block_id == 46: # Shield Drain Computer
            if complex_systems['shield_drain'] == 0:
                complex_systems['shield_drain'] = 1
            else:
                context['systems']['shield_drain'] = complex_systems['shield_drain']
        elif block_id == 40: # Shield Drain Modules
            if complex_systems['shield_drain'] == 0:
                complex_systems['shield_drain'] = block_count
            else:
                context['systems']['shield_drain'] = block_count
        elif block_id == 54: # Shield Supply Computer
            if complex_systems['shield_supply'] == 0:
                complex_systems['shield_supply'] = 1
            else:
                context['systems']['shield_supply'] = complex_systems['shield_supply']
        elif block_id == 48: # Shield Supply Modules
            if complex_systems['shield_supply'] == 0:
                complex_systems['shield_supply'] = block_count
            else:
                context['systems']['shield_supply'] = block_count

    if 'radar_jamming' in context['systems']:
        context['power_usage']['radar_jamming'] = -total_mass * 50
    if 'cloaking' in context['systems']:
        context['power_usage']['cloaking'] = -total_mass * 14.5

    context['element_list'] = element_list
    context['mass'] = round(total_mass,1)

    context['systems'] = {key:value for key,value
                          in context['systems'].iteritems() if value > 0}

    thrust_gauge = 0
    speed_coefficient = 0.5
    thrust = context['thrust']
    if thrust != 'None':
        thrust_gauge = starmade.thrust_rating(thrust, total_mass)
        speed_coefficient = round(starmade.calc_speed_coefficient(thrust, total_mass), 1)

    shields = context['shields']
    max_shield_capacity = starmade.calc_shield_capacity(total_block_count)
    shield_capacity_gauge = starmade.shield_rating(shields['capacity'],
                                                   max_shield_capacity)
    max_shield_recharge = starmade.calc_shield_recharge(total_block_count)
    shield_recharge_gauge = starmade.shield_rating(shields['recharge'],
                                                   max_shield_recharge)
    max_power_output = starmade.calc_power_output(total_block_count, 
                                                  ship_dimensions)
    power_recharge_gauge = starmade.shield_rating(power_recharge_rating,
                                                  max_power_output)

    if entity_type == 0:
        context['thrust_gauge'] = round(thrust_gauge * 100.0,1)
        context['speed_coefficient'] = speed_coefficient
    context['shield_capacity_gauge'] = round(shield_capacity_gauge * 100.0,1)
    context['shield_recharge_gauge'] = round(shield_recharge_gauge * 100.0,1)
    context['power_recharge_gauge'] = round(power_recharge_gauge * 100.0,1)
    context['power_recharge_sum'] = sum(context['power_recharge'].itervalues())
    context['power_capacity_sum'] = sum(context['power_capacity'].itervalues())

    if context['power_recharge_sum'] > 0:
        charge_time = float(context['power_capacity_sum']) / context['power_recharge_sum']
        context['idle_time_charge'] = round(charge_time, 1)
    else:
        context['idle_time_charge'] = "N/A"

    if blue_key == None:
        blueprint = Blueprint()
    else:
        blueprint = ndb.Key(urlsafe=blue_key).get()
        blueprint.schema_version = starmade.SCHEMA_VERSION_CURRENT

    blueprint.blob_key = blob_key
    blueprint.context = json.dumps(context)
    blueprint.elements = json.dumps(element_list)
    blueprint.element_count = element_count
    blueprint.length = length
    blueprint.width = width
    blueprint.height = height
    blueprint.max_dimension = max(length, width, height)
    blueprint.class_rank = int(max(math.log10(total_mass), 0))
    blueprint.title = blueprint_title
    blueprint.power_recharge = power_recharge
    blueprint.power_capacity = power_capacity
    blue_key = blueprint.put()

    return blue_key

@app.route("/blueprint/<blob_key>")
def download_blueprint(blob_key):
    blob_info = blobstore.get(blob_key)
    response = make_response(blob_info.open().read())
    response.headers['Content-Type'] = blob_info.content_type
    return response

@app.route("/view/<blue_key>")
def view(blue_key):
    roman = {-1: "N", 0: "N", 1: "I", 2: "II", 3: "III", 4: "IV", 5: "V",
             6: "VI", 7: "VII", 8: "VIII"}
    blueprint = ndb.Key(urlsafe=blue_key).get()

    if blueprint.schema_version < starmade.SCHEMA_VERSION_CURRENT:
       power_recharge = starmade.valid_power(blueprint.power_recharge)
       power_capacity = starmade.valid_power(blueprint.power_capacity)
       blueprint = process_blueprint(blueprint.blob_key, blueprint.title,
                                     power_recharge, power_capacity,
                                     blue_key).get()

    context = json.loads(blueprint.context)
    context['class'] = "Class-" + roman.get(round(math.log10(context['mass']), 0), "?")
    context['blue_key'] = blue_key
    return render_template('view_blueprint.html', **context)

@app.route("/delete/<blue_key>", methods=['POST'])
def delete(blue_key):
    blue_key = ndb.Key(urlsafe=blue_key)
    blobstore.get(blue_key.get().blob_key).delete()
    blue_key.delete()
    return redirect(url_for('list'),303)


@app.route("/list/")
def list_new():
    return list()

@app.route("/list/<cursor_token>")
def list(cursor_token=None):
    query = Blueprint.query(projection=[Blueprint.title, Blueprint.class_rank])
    if cursor_token != None:
       curs = Cursor(urlsafe=cursor_token)
    else:
       curs = None

    list_query, next_curs, more_flag = query.fetch_page(50, start_cursor=curs)

    blueprint_list = [{"blue_key": r.key.urlsafe(), "title": r.title, "class_rank": r.class_rank} for r in list_query]
    return render_template("list.html", blueprint_list=blueprint_list,
                           next_curs=next_curs.urlsafe(), more_flag=more_flag)

@app.route("/old/")
def old_list():
    query = Blueprint.query(Blueprint.schema_version < starmade.SCHEMA_VERSION_CURRENT)
    blueprint_list = [{"blue_key":result.urlsafe()} for result in query.iter(keys_only=True)]

@app.route("/search/")
def search():
    return render_template('search.html')

@app.route("/search/list/")
def search_list():
    return render_template('search.html')

@app.errorhandler(404)
def page_not_found(e):
    """Return a custom 404 error."""
    return 'Sorry, Nothing at this URL.', 404


@app.errorhandler(500)
def application_error(e):
    """Return a custom 500 error."""
    return 'Sorry, unexpected error: {}'.format(e), 500
