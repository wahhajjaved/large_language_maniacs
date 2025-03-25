#!/usr/bin/env python
'''
mavproxy - a MAVLink proxy program

Copyright Andrew Tridgell 2011
Released under the GNU GPL version 3 or later

'''

import sys, os, struct, math, time, socket
import fnmatch, errno, threading
import serial, Queue

# find the mavlink.py module
for d in [ 'pymavlink',
           os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', 'pymavlink') ]:
    if os.path.exists(d):
        sys.path.insert(0, d)
        if os.name == 'nt':
            try:
                # broken python compilation of mavlink.py on windows!
                os.unlink(os.path.join(d, 'mavlink.pyc'))
            except:
                pass

if os.getenv('MAVLINK10'):
    import mavlinkv10 as mavlink
else:
    import mavlink
import mavutil, mavwp
import select

def kt2mps(x):
    '''knots to meters per second'''
    return float(x)*0.514444444

def deg2rad(x):
    '''degrees to radians'''
    return (float(x) / 360.0) * 2.0 * math.pi

def ft2m(x):
    '''feet to meters'''
    return float(x) * 0.3048

def get_usec():
    '''time since 1970 in microseconds'''
    return int(time.time() * 1.0e6)

class rline(object):
    '''async readline abstraction'''
    def __init__(self, prompt):
        import threading
        self.prompt = prompt
        self.line = None
        try:
            import readline
        except Exception:
            pass

    def set_prompt(self, prompt):
        if prompt != self.prompt:
            self.prompt = prompt
            sys.stdout.write(prompt)
            
def say(text, priority='important'):
    '''speak some text'''
    ''' http://cvs.freebsoft.org/doc/speechd/ssip.html see 4.3.1 for priorities'''
    print(text)
    if settings.speech:
        import speechd
        status.speech = speechd.SSIPClient('MAVProxy%u' % os.getpid())
        status.speech.set_output_module('festival')
        status.speech.set_language('en')
        status.speech.set_priority(priority)
        status.speech.set_punctuation(speechd.PunctuationMode.SOME)
        status.speech.speak(text)
        status.speech.close()

class settings(object):
    def __init__(self):
        self.vars = [ ('altreadout', int),
                      ('battreadout', int),
                      ('basealtitude', int),
                      ('heartbeat', int),
                      ('numcells', int),
                      ('speech', int),
                      ('streamrate', int),
                      ('heartbeatreport', int),
                      ('radiosetup', int),
                      ('rc1mul', int),
                      ('rc2mul', int),
                      ('rc4mul', int)]
        self.altreadout = 10
        self.battreadout = 1
        self.basealtitude = -1
        self.heartbeat = 1
        self.numcells = 0
        self.speech = 0
        self.streamrate = 4
        self.radiosetup = 0
        self.heartbeatreport = 1
        self.rc1mul = 1
        self.rc2mul = 1
        self.rc4mul = 1

    def set(self, vname, value):
        '''set a setting'''
        for (v,t) in sorted(self.vars):
            if v == vname:
                try:
                    value = t(value)
                except:
                    print("Unable to convert %s to type %s" % (value, t))
                    return
                setattr(self, vname, value)
                return

    def show(self, v):
        '''show settings'''
        print("%20s %s" % (v, getattr(self, v)))

    def show_all(self):
        '''show all settings'''
        for (v,t) in sorted(self.vars):
            self.show(v)

class status(object):
    '''hold status information about the master'''
    def __init__(self):
        if opts.quadcopter:
            self.rc_throttle = [ 0.0, 0.0, 0.0, 0.0 ]
        else:
            self.rc_aileron  = 0
            self.rc_elevator = 0
            self.rc_throttle = 0
            self.rc_rudder   = 0
        self.gps	 = None
        self.msgs = {}
        self.msg_count = {}
        self.counters = {'MasterIn' : 0, 'MasterOut' : 0, 'FGearIn' : 0, 'FGearOut' : 0, 'Slave' : 0}
        self.setup_mode = opts.setup
        self.wp_op = None
        self.wp_save_filename = None
        self.wploader = mavwp.MAVWPLoader()
        self.loading_waypoints = False
        self.loading_waypoint_lasttime = time.time()
        self.mav_error = 0
        self.target_system = -1
        self.target_component = -1
        self.speech = None
        self.last_altitude_announce = 0.0
        self.last_battery_announce = 0
        self.last_avionics_battery_announce = 0
        self.battery_level = -1
        self.avionics_battery_level = -1
        self.last_waypoint = 0
        self.exit = False
        self.override = [ 0 ] * 8
        self.flightmode = 'MAV'
        self.logdir = None
        self.last_heartbeat = 0
        self.heartbeat_error = False

    def show(self, f, pattern=None):
        '''write status to status.txt'''
        if pattern is None:
            f.write('Counters: ')
            for c in status.counters:
                f.write('%s:%u ' % (c, status.counters[c]))
            f.write('\n')
            f.write('MAV Errors: %u\n' % status.mav_error)
            f.write(str(self.gps)+'\n')
        for m in sorted(status.msgs.keys()):
            if pattern is not None and not fnmatch.fnmatch(str(m).upper(), pattern.upper()):
                continue
            f.write("%u: %s\n" % (status.msg_count[m], str(status.msgs[m])))

    def write(self):
        '''write status to status.txt'''
        f = open('status.txt', mode='w')
        self.show(f)
        f.close()

# current MAV master parameters
mav_param = {}

def get_mav_param(param, default=None):
    '''return a EEPROM parameter value'''
    global mav_param
    if not param in mav_param:
        return default
    return mav_param[param]


def send_rc_override(mav_master):
    '''send RC override packet'''
    if sitl_output:
        buf = struct.pack('<HHHHHHHH',
                          *status.override)
        sitl_output.write(buf)
    else:
        mav_master.mav.rc_channels_override_send(status.target_system,
                                                 status.target_component,
                                                 *status.override)

def control_set(mav_master, name, channel, args):
    '''set a fixed RC control PWM value'''
    if len(args) != 1:
        print("Usage: %s <pwmvalue>" % name)
        return
    status.override[channel-1] = int(args[0])
    send_rc_override(mav_master)
    
    
def cmd_roll(args, rl, mav_master):
    control_set(mav_master, 'roll', 1, args)

def cmd_pitch(args, rl, mav_master):
    control_set(mav_master, 'pitch', 2, args)

def cmd_rudder(args, rl, mav_master):
    control_set(mav_master, 'rudder', 4, args)

def cmd_throttle(args, rl, mav_master):
    control_set(mav_master, 'throttle', 3, args)


def cmd_switch(args, rl, mav_master):
    '''handle RC switch changes'''
    mapping = [ 0, 1165, 1295, 1425, 1555, 1685, 1815 ]
    if len(args) != 1:
        print("Usage: switch <pwmvalue>")
        return
    value = int(args[0])
    if value < 0 or value > 6:
        print("Invalid switch value. Use 1-6 for flight modes, '0' to disable")
        return
    if opts.quadcopter:
        default_channel = 5
    else:
        default_channel = 8
    flite_mode_ch_parm = int(get_mav_param("FLTMODE_CH", default_channel))
    status.override[flite_mode_ch_parm-1] = mapping[value]
    send_rc_override(mav_master)
    if value == 0:
        print("Disabled RC switch override")
    else:
        print("Set RC switch override to %u (PWM=%u)" % (value, mapping[value]))

def cmd_trim(args, rl, mav_master):
    '''trim aileron, elevator and rudder to current values'''
    if not 'RC_CHANNELS_RAW' in status.msgs:
        print("No RC_CHANNELS_RAW to trim with")
        return
    m = status.msgs['RC_CHANNELS_RAW']

    mav_master.param_set_send('ROLL_TRIM',  m.chan1_raw)
    mav_master.param_set_send('PITCH_TRIM', m.chan2_raw)
    mav_master.param_set_send('YAW_TRIM',   m.chan4_raw)
    print("Trimmed to aileron=%u elevator=%u rudder=%u" % (
        m.chan1_raw, m.chan2_raw, m.chan4_raw))
    

def cmd_rc(args, rl, mav_master):
    '''handle RC value override'''
    if len(args) != 2:
        print("Usage: rc <channel> <pwmvalue>")
        return
    channel = int(args[0])
    value   = int(args[1])
    if value == -1:
        value = 65535
    if channel < 1 or channel > 8:
        print("Channel must be between 1 and 8")
        return
    status.override[channel-1] = value
    send_rc_override(mav_master)

def cmd_loiter(args, rl, mav_master):
    '''set LOITER mode'''
    MAV_ACTION_LOITER = 27
    mav_master.mav.action_send(status.target_system, status.target_component, MAV_ACTION_LOITER)

def cmd_auto(args, rl, mav_master):
    '''set AUTO mode'''
    MAV_ACTION_SET_AUTO = 13
    mav_master.mav.action_send(status.target_system, status.target_component, MAV_ACTION_SET_AUTO)

def cmd_ground(args, rl, mav_master):
    '''do a ground start mode'''
    MAV_ACTION_CALIBRATE_GYRO = 17
    mav_master.mav.action_send(status.target_system, status.target_component, MAV_ACTION_CALIBRATE_GYRO)

def cmd_rtl(args, rl, mav_master):
    '''set RTL mode'''
    MAV_ACTION_RETURN = 3
    mav_master.mav.action_send(status.target_system, status.target_component, MAV_ACTION_RETURN)

def cmd_manual(args, rl, mav_master):
    '''set MANUAL mode'''
    MAV_ACTION_SET_MANUAL = 12
    mav_master.mav.action_send(status.target_system, status.target_component, MAV_ACTION_SET_MANUAL)

def cmd_magreset(args, rl, mav_master):
    '''reset magnetometer offsets'''
    mav_master.mav.set_mag_offsets_send(status.target_system, status.target_component,
                                        0, 0, 0)


def process_waypoint_request(m, mav_master):
    '''process a waypoint request from the master'''
    if (not status.loading_waypoints or
        time.time() > status.loading_waypoint_lasttime + 10.0):
        status.loading_waypoints = False
        print("not loading waypoints")
        return
    if m.seq >= status.wploader.count():
        print("Request for bad waypoint %u (max %u)" % (m.seq, status.wploader.count()))
        return
    mav_master.mav.send(status.wploader.wp(m.seq))
    status.loading_waypoint_lasttime = time.time()
    if m.seq == status.wploader.count() - 1:
        status.loading_waypoints = False
        print("Sent all %u waypoints" % status.wploader.count())
    else:
        print("Sent waypoint %u : %s" % (m.seq, status.wploader.wp(m.seq)))

def load_waypoints(filename):
    '''load waypoints from a file'''
    status.wploader.target_system = status.target_system
    status.wploader.target_component = status.target_component
    try:
        status.wploader.load(filename)
    except Exception, msg:
        print("Unable to load %s - %s" % (filename, msg))
        return
    print("Loaded %u waypoints from %s" % (status.wploader.count(), filename))

    mav_master.waypoint_clear_all_send()
    if status.wploader.count() == 0:
        return

    status.loading_waypoints = True
    status.loading_waypoint_lasttime = time.time()
    mav_master.waypoint_count_send(status.wploader.count())

def save_waypoints(filename):
    '''save waypoints to a file'''
    try:
        status.wploader.save(filename)
    except Exception, msg:
        print("Failed to save %s - %s" % (filename, msg))
        return
    print("Saved %u waypoints to %s" % (status.wploader.count(), filename))
             

def cmd_wp(args, rl, mav_master):
    '''waypoint commands'''
    if len(args) < 1:
        print("usage: wp <list|load|save|set|clear>")
        return

    if args[0] == "load":
        if len(args) != 2:
            print("usage: wp load <filename>")
            return
        load_waypoints(args[1])
    elif args[0] == "list":
        status.wp_op = "list"
        mav_master.waypoint_request_list_send()
    elif args[0] == "save":
        if len(args) != 2:
            print("usage: wp save <filename>")
            return
        status.wp_save_filename = args[1]
        status.wp_op = "save"
        mav_master.waypoint_request_list_send()
    elif args[0] == "set":
        if len(args) != 2:
            print("usage: wp set <wpindex>")
            return
        mav_master.waypoint_set_current_send(int(args[1]))
    elif args[0] == "clear":
        mav_master.waypoint_clear_all_send()
    else:
        print("Usage: wp <list|load|save|set|clear>")


def param_set(mav_master, name, value, retries=3):
    '''set a parameter'''
    got_ack = False
    while retries > 0 and not got_ack:
        retries -= 1
        mav_master.param_set_send(name, float(value))
        tstart = time.time()
        while time.time() - tstart < 1:
            ack = mav_master.recv_match(type='PARAM_VALUE', blocking=False)
            if ack == None:
                time.sleep(0.1)
                continue
            if str(name) == str(ack.param_id):
                got_ack = True
                break
    if not got_ack:
        print("timeout setting %s to %f" % (name, float(value)))
        return False
    return True


def param_save(filename, wildcard):
    '''save parameters to a file'''
    f = open(filename, mode='w')
    k = mav_param.keys()
    k.sort()
    count = 0
    for p in k:
        if p and fnmatch.fnmatch(str(p).upper(), wildcard.upper()):
            f.write("%-15.15s %f\n" % (p, mav_param[p]))
            count += 1
    f.close()
    print("Saved %u parameters to %s" % (count, filename))


def param_load_file(filename, wildcard, mav_master):
    '''load parameters from a file'''
    try:
        f = open(filename, mode='r')
    except:
        print("Failed to open file '%s'" % filename)
        return
    count = 0
    changed = 0
    for line in f:
        line = line.strip()
        if line[0] == "#":
            continue
        a = line.split()
        if len(a) != 2:
            print("Invalid line: %s" % line)
            continue
        if a[0] in ['SYSID_SW_MREV', 'SYS_NUM_RESETS']:
            continue
        if not fnmatch.fnmatch(a[0].upper(), wildcard.upper()):
            continue
        if a[0] not in mav_param:
            print("Unknown parameter %s" % a[0])
            continue
        old_value = mav_param[a[0]]
        if math.fabs(old_value - float(a[1])) > 0.000001:
            if param_set(mav_master, a[0], a[1]):
                print("changed %s from %f to %f" % (a[0], old_value, float(a[1])))
            changed += 1
        count += 1
    f.close()
    print("Loaded %u parameters from %s (changed %u)" % (count, filename, changed))
    

param_wildcard = "*"

def cmd_param(args, rl, mav_master):
    '''control parameters'''
    if len(args) < 1:
        print("usage: param <fetch|edit|set|show|store>")
        return
    if args[0] == "fetch":
        mav_master.param_fetch_all()
        print("Requested parameter list")
    elif args[0] == "save":
        if len(args) < 2:
            print("usage: param save <filename> [wildcard]")
            return
        if len(args) > 2:
            param_wildcard = args[2]
        else:
            param_wildcard = "*"
        param_save(args[1], param_wildcard)
    elif args[0] == "set":
        if len(args) != 3:
            print("Usage: param set PARMNAME VALUE")
            return
        param = args[1]
        value = args[2]
        if not param in mav_param:
            print("Warning: Unable to find parameter '%s'" % param)
        param_set(mav_master, param, value)
    elif args[0] == "load":
        if len(args) < 2:
            print("Usage: param load <filename> [wildcard]")
            return
        if len(args) > 2:
            param_wildcard = args[2]
        else:
            param_wildcard = "*"
        param_load_file(args[1], param_wildcard, mav_master);
    elif args[0] == "show":
        if len(args) > 1:
            pattern = args[1]
        else:
            pattern = "*"
        k = sorted(mav_param.keys())
        for p in k:
            if fnmatch.fnmatch(str(p).upper(), pattern.upper()):
                print("%-15.15s %f" % (str(p), mav_param[p]))
    elif args[0] == "store":
        MAV_ACTION_STORAGE_WRITE = 15
        mav_master.mav.action_send(status.target_system, status.target_component, MAV_ACTION_STORAGE_WRITE)
    else:
        print("Unknown subcommand '%s' (try 'fetch', 'save', 'set', 'show', 'load' or 'store')" % args[0]);

def cmd_set(args, rl, mav_master):
    '''control mavproxy options'''
    if len(args) == 0:
        settings.show_all()
        return

    if getattr(settings, args[0], None) is None:
        print("Unknown setting '%s'" % args[0])
        return
    if len(args) == 1:
        settings.show(args[0])
    else:
        settings.set(args[0], args[1])

def cmd_status(args, rl, mav_master):
    '''show status'''
    if len(args) == 0:
        status.show(sys.stdout, pattern=pattern)
    else:
        for pattern in args:
            status.show(sys.stdout, pattern=pattern)

def cmd_bat(args, rl, mav_master):
    '''show battery levels'''
    print("Flight battery:   %u%%" % status.battery_level)
    print("Avionics battery: %u%%" % status.avionics_battery_level)

def cmd_setup(args, rl, mav_master):
    status.setup_mode = True
    rl.set_prompt("")


def cmd_reset(args, rl, mav_master):
    print("Resetting master")
    mav_master.reset()

command_map = {
    'roll'    : (cmd_roll,     'set fixed roll PWM'),
    'pitch'   : (cmd_pitch,    'set fixed pitch PWM'),
    'rudder'  : (cmd_rudder,   'set fixed rudder PWM'),
    'throttle': (cmd_throttle, 'set fixed throttle PWM'),
    'switch'  : (cmd_switch,   'set RC switch (1-5), 0 disables'),
    'rc'      : (cmd_rc,       'override a RC channel value'),
    'wp'      : (cmd_wp,       'waypoint management'),
    'param'   : (cmd_param,    'manage APM parameters'),
    'setup'   : (cmd_setup,    'go into setup mode'),
    'reset'   : (cmd_reset,    'reopen the connection to the MAVLink master'),
    'status'  : (cmd_status,   'show status'),
    'trim'    : (cmd_trim,     'trim aileron, elevator and rudder to current values'),
    'auto'    : (cmd_auto,     'set AUTO mode'),
    'ground'  : (cmd_ground,   'do a ground start'),
    'loiter'  : (cmd_loiter,   'set LOITER mode'),
    'rtl'     : (cmd_rtl,      'set RTL mode'),
    'manual'  : (cmd_manual,   'set MANUAL mode'),
    'magreset': (cmd_magreset, 'reset magnetometer offsets'),
    'set'     : (cmd_set,      'mavproxy settings'),
    'bat'     : (cmd_bat,      'show battery levels'),
    };

def process_stdin(rl, line, mav_master):
    '''handle commands from user'''
    if line is None:
        sys.exit(0)
    line = line.strip()

    if status.setup_mode:
        # in setup mode we send strings straight to the master
        if line == '.':
            status.setup_mode = False
            rl.set_prompt("MAV> ")
            return
        mav_master.write(line + '\r')
        return

    if not line:
        return

    args = line.split(" ")
    cmd = args[0]
    if cmd == 'help':
        k = command_map.keys()
        k.sort()
        for cmd in k:
            (fn, help) = command_map[cmd]
            print("%-15s : %s" % (cmd, help))
        return
    if not cmd in command_map:
        print("Unknown command '%s'" % line)
        return
    (fn, help) = command_map[cmd]
    try:
        fn(args[1:], rl, mav_master)
    except Exception as e:
        print("ERROR in command: %s" % str(e))


def scale_rc(servo, min, max, param):
    '''scale a PWM value'''
    # default to servo range of 1000 to 2000
    min_pwm  = get_mav_param('%s_MIN'  % param, 0)
    max_pwm  = get_mav_param('%s_MAX'  % param, 0)
    if min_pwm == 0 or max_pwm == 0:
        return 0
    if max_pwm == min_pwm:
        p = 0.0
    else:
        p = (servo-min_pwm) / float(max_pwm-min_pwm)
    v = min + p*(max-min)
    if v < min:
        v = min
    if v > max:
        v = max
    return v


def system_check():
    '''check that the system is ready to fly'''
    ok = True

    if mavlink.wire_protocol_version == '1.0':
        if not 'GPS_RAW_INT' in status.msgs:
            say("WARNING no GPS status")
            return
        if status.msgs['GPS_RAW_INT'].fix_type != 2:
            say("WARNING no GPS lock")
            ok = False
    else:
        if not 'GPS_RAW' in status.msgs and not 'GPS_RAW_INT' in status.msgs:
            say("WARNING no GPS status")
            return
        if status.msgs['GPS_RAW'].fix_type != 2:
            say("WARNING no GPS lock")
            ok = False

    if not 'PITCH_MIN' in mav_param:
        say("WARNING no pitch parameter available")
        return
        
    if int(mav_param['PITCH_MIN']) > 1300:
        say("WARNING PITCH MINIMUM not set")
        ok = False

    if not 'ATTITUDE' in status.msgs:
        say("WARNING no attitude recorded")
        return

    if math.fabs(status.msgs['ATTITUDE'].pitch) > math.radians(5):
        say("WARNING pitch is %u degrees" % math.degrees(status.msgs['ATTITUDE'].pitch))
        ok = False

    if math.fabs(status.msgs['ATTITUDE'].roll) > math.radians(5):
        say("WARNING roll is %u degrees" % math.degrees(status.msgs['ATTITUDE'].roll))
        ok = False

    if ok:
        say("All OK SYSTEM READY TO FLY")


def beep():
    f = open("/dev/tty", mode="w")
    f.write(chr(7))
    f.close()

def vcell_to_battery_percent(vcell):
    '''convert a cell voltage to a percentage battery level'''
    if vcell > 4.1:
        # above 4.1 is 100% battery
        return 100.0
    elif vcell > 3.81:
        # 3.81 is 17% remaining, from flight logs
        return 17.0 + 83.0 * (vcell - 3.81) / (4.1 - 3.81)
    elif vcell > 3.81:
        # below 3.2 it degrades fast. It's dead at 3.2
        return 0.0 + 17.0 * (vcell - 3.20) / (3.81 - 3.20)
    # it's dead or disconnected
    return 0.0


def battery_update(SYS_STATUS):
    '''update battery level'''

    # main flight battery
    status.battery_level = SYS_STATUS.battery_remaining/10.0

    # avionics battery
    if not 'AP_ADC' in status.msgs:
        return
    rawvalue = float(status.msgs['AP_ADC'].adc2)
    INPUT_VOLTAGE = 4.68
    VOLT_DIV_RATIO = 3.56
    voltage = rawvalue*(INPUT_VOLTAGE/1024.0)*VOLT_DIV_RATIO
    vcell = voltage / settings.numcells

    avionics_battery_level = vcell_to_battery_percent(vcell)

    if status.avionics_battery_level == -1 or abs(avionics_battery_level-status.avionics_battery_level) > 70:
        status.avionics_battery_level = avionics_battery_level
    else:
        status.avionics_battery_level = (95*status.avionics_battery_level + 5*avionics_battery_level)/100



def battery_report():
    '''report battery level'''
    if int(settings.battreadout) == 0:
        return

    rbattery_level = int((status.battery_level+5)/10)*10;

    if rbattery_level != status.last_battery_announce:
        say("Flight battery %u percent" % rbattery_level,priority='notification')
        status.last_battery_announce = rbattery_level
    if rbattery_level <= 20:
        say("Flight battery warning")

    # avionics battery reporting disabled for now
    return
    avionics_rbattery_level = int((status.avionics_battery_level+5)/10)*10;

    if avionics_rbattery_level != status.last_avionics_battery_announce:
        say("Avionics Battery %u percent" % avionics_rbattery_level,priority='notification')
        status.last_avionics_battery_announce = avionics_rbattery_level
    if avionics_rbattery_level <= 20:
        say("Avionics battery warning")

    

def master_callback(m, master, recipients):
    '''process mavlink message m on master, sending any messages to recipients'''

    if getattr(m, '_timestamp', None) is None:
        master.post_message(m)
    status.counters['MasterIn'] += 1

#    print("Got MAVLink msg: %s" % m)

    mtype = m.get_type()
    if mtype == 'HEARTBEAT':
        if (status.target_system != m.get_srcSystem() or
            status.target_component != m.get_srcComponent()):
            status.target_system = m.get_srcSystem()
            status.target_component = m.get_srcComponent()
            say("online system %u component %u" % (status.target_system, status.target_component),'message')
        if status.heartbeat_error:
            status.heartbeat_error = False
            say("heartbeat OK")
        status.last_heartbeat = time.time()
    elif mtype == 'STATUSTEXT':
        print("APM: %s" % m.text)
    elif mtype == 'PARAM_VALUE':
        mav_param[str(m.param_id)] = m.param_value
        if m.param_index+1 == m.param_count:
            print("Received %u parameters" % m.param_count)
            if status.logdir != None:
                param_save(os.path.join(status.logdir, 'mav.parm'), '*')

    elif mtype == 'SERVO_OUTPUT_RAW':
        if opts.quadcopter:
            status.rc_throttle[0] = scale_rc(m.servo1_raw, 0.0, 1.0, param='RC3')
            status.rc_throttle[1] = scale_rc(m.servo2_raw, 0.0, 1.0, param='RC3')
            status.rc_throttle[2] = scale_rc(m.servo3_raw, 0.0, 1.0, param='RC3')
            status.rc_throttle[3] = scale_rc(m.servo4_raw, 0.0, 1.0, param='RC3')
        else:
            status.rc_aileron  = scale_rc(m.servo1_raw, -1.0, 1.0, param='RC1') * settings.rc1mul
            status.rc_elevator = scale_rc(m.servo2_raw, -1.0, 1.0, param='RC2') * settings.rc2mul
            status.rc_throttle = scale_rc(m.servo3_raw, 0.0, 1.0, param='RC3')
            status.rc_rudder   = scale_rc(m.servo4_raw, -1.0, 1.0, param='RC4') * settings.rc4mul
            if status.rc_throttle < 0.1:
                status.rc_throttle = 0

    elif mtype in ['WAYPOINT_COUNT','MISSION_COUNT']:
        if status.wp_op is None:
            print("No waypoint load started")
        else:
            status.wploader.clear()
            status.wploader.expected_count = m.count
            print("Requesting %u waypoints t=%s now=%s" % (m.count,
                                                           time.asctime(time.localtime(m._timestamp)),
                                                           time.asctime()))
            mav_master.waypoint_request_send(0)

    elif mtype in ['WAYPOINT', 'MISSION_ITEM'] and status.wp_op != None:
        if m.seq > status.wploader.count():
            print("Unexpected waypoint number %u - expected %u" % (m.seq, status.wploader.count()))
        elif m.seq < status.wploader.count():
            # a duplicate
            pass
        else:
            status.wploader.add(m)
        if m.seq+1 < status.wploader.expected_count:
            mav_master.waypoint_request_send(m.seq+1)
        else:
            if status.wp_op == 'list':
                for i in range(status.wploader.count()):
                    w = status.wploader.wp(i)
                    print("%u %u %.10f %.10f %f p1=%.1f p2=%.1f p3=%.1f p4=%.1f cur=%u auto=%u" % (
                        w.command, w.frame, w.x, w.y, w.z,
                        w.param1, w.param2, w.param3, w.param4,
                        w.current, w.autocontinue))
            elif status.wp_op == "save":
                save_waypoints(status.wp_save_filename)
            status.wp_op = None

    elif mtype in ["WAYPOINT_REQUEST", "MISSION_REQUEST"]:
        process_waypoint_request(m, master)

    elif mtype in ["WAYPOINT_CURRENT", "MISSION_CURRENT"]:
        if m.seq != status.last_waypoint:
            status.last_waypoint = m.seq
            say("waypoint %u" % m.seq,priority='message')

    elif mtype == "SYS_STATUS":
        battery_update(m)
        if mav_master.flightmode != status.flightmode:
            status.flightmode = mav_master.flightmode
            rl.set_prompt(status.flightmode + "> ")
            say("Mode " + status.flightmode)

    elif mtype == "VFR_HUD":
        have_gps_fix = False
        if 'GPS_RAW' in status.msgs and status.msgs['GPS_RAW'].fix_type == 2:
            have_gps_fix = True
        if 'GPS_RAW_INT' in status.msgs and status.msgs['GPS_RAW_INT'].fix_type == 2:
            have_gps_fix = True
        if have_gps_fix and m.alt != 0.0:
            if settings.basealtitude == -1:
                settings.basealtitude = m.alt
                status.last_altitude_announce = 0.0
                say("GPS lock at %u meters" % m.alt, priority='notification')
            else:
                if m.alt < settings.basealtitude:
                    settings.basealtitude = m.alt
                    status.last_altitude_announce = m.alt
                if (int(settings.altreadout) > 0 and
                    math.fabs(m.alt - status.last_altitude_announce) >= int(settings.altreadout)):
                    status.last_altitude_announce = m.alt
                    rounded_alt = int(settings.altreadout) * ((5+int(m.alt - settings.basealtitude)) / int(settings.altreadout))
                    say("%u meters" % rounded_alt, priority='notification')

    elif mtype == "RC_CHANNELS_RAW":
        if (m.chan7_raw > 1700 and status.flightmode == "MANUAL"):
            system_check()
        if settings.radiosetup:
            for i in range(1,9):
                v = getattr(m, 'chan%u_raw' % i)
                rcmin = get_mav_param('RC%u_MIN' % i, 0)
                if rcmin > v:
                    if param_set(mav_master, 'RC%u_MIN' % i, v):
                        print("Set RC%u_MIN=%u" % (i, v))
                rcmax = get_mav_param('RC%u_MAX' % i, 0)
                if rcmax < v:
                    if param_set(mav_master, 'RC%u_MAX' % i, v):
                        print("Set RC%u_MAX=%u" % (i, v))
                    

    elif mtype == "BAD_DATA":
        if mavutil.all_printable(m.data):
            sys.stdout.write(m.data)
            sys.stdout.flush()
    elif mtype in [ 'HEARTBEAT', 'GLOBAL_POSITION', 'RC_CHANNELS_SCALED',
                    'ATTITUDE', 'RC_CHANNELS_RAW', 'GPS_STATUS', 'WAYPOINT_CURRENT',
                    'SERVO_OUTPUT_RAW', 'VFR_HUD',
                    'GLOBAL_POSITION_INT', 'RAW_PRESSURE', 'RAW_IMU',
                    'WAYPOINT_ACK', 'MISSION_ACK',
                    'NAV_CONTROLLER_OUTPUT', 'GPS_RAW', 'GPS_RAW_INT', 'WAYPOINT',
                    'SCALED_PRESSURE', 'SENSOR_OFFSETS', 'MEMINFO', 'AP_ADC' ]:
        pass
    else:
        print("Got MAVLink msg: %s" % m)

    # keep the last message of each type around
    status.msgs[m.get_type()] = m
    if not m.get_type() in status.msg_count:
        status.msg_count[m.get_type()] = 0
    status.msg_count[m.get_type()] += 1

    # also send the message on to all the slaves
    if mtype != "BAD_DATA":
        for r in recipients:
            r.write(m.get_msgbuf().tostring())

    # and log them
    if master.logqueue and mtype != "BAD_DATA":
        master.logqueue.put(str(struct.pack('>Q', get_usec()) + m.get_msgbuf().tostring()))


def process_master(m):
    '''process packets from the MAVLink master'''
    s = m.recv()
    if m.logqueue_raw:
        m.logqueue_raw.put(str(s))

    if status.setup_mode:
        sys.stdout.write(str(s))
        sys.stdout.flush()
        return

    msgs = m.mav.parse_buffer(s)
    if msgs:
        for msg in msgs:
            m.post_message(msg)
            if msg.get_type() == "BAD_DATA":
                if opts.show_errors:
                    print("MAV error: %s" % msg)
                status.mav_error += 1

    

def process_mavlink(slave, master):
    '''process packets from MAVLink slaves, forwarding to the master'''
    try:
        buf = slave.recv()
    except socket.error:
        return
    try:
        m = slave.mav.decode(buf)
    except mavlink.MAVError as e:
        print("Bad MAVLink slave message from %s: %s" % (slave.address, e.message))
        return
    if not status.setup_mode:
        master.write(m.get_msgbuf())
    status.counters['Slave'] += 1

def send_flightgear_controls(fg):
    '''send control values to flightgear'''
    status.counters['FGearOut'] += 1
    if opts.quadcopter:
        r = [0, 0, 0, 0, 0, 0, 0, 0]
        if 'RC_CHANNELS_RAW' in status.msgs:
            for i in range(0, 8):
                r[i] = getattr(status.msgs['RC_CHANNELS_RAW'], 'chan%u_raw' % (i+1))
        buf = struct.pack('>ffffHHHHHHHH',
                          status.rc_throttle[0], # right
                          status.rc_throttle[1], # left
                          status.rc_throttle[2], # front
                          status.rc_throttle[3], # back
                          r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7])
    else:
        buf = struct.pack('>dddd', status.rc_aileron, status.rc_elevator,
                          status.rc_rudder, status.rc_throttle)
    fg.write(buf)
    


def process_flightgear(m, master):
    '''process flightgear protocol input'''
    buf = m.recv()
    if len(buf) == 0:
        return
    # see MAVLink.xml for the protocol format
    try:
        (latitude, longitude, altitude, heading,
         speedN, speedE,
         xAccel, yAccel, zAccel,
         rollRate, pitchRate, yawRate,
         rollDeg, pitchDeg, yawDeg,
         airspeed, magic) = struct.unpack('>ddddddddddddddddI', buf)
    except struct.error as e:
        print("Bad flightgear input of length %u: %s" % (len(buf), e.message))
        return
    if magic != 0x4c56414d:
        print("Bad flightgear magic 0x%08x should be 0x4c56414d" % magic)
        return
    if altitude <= 0 or latitude == 0 or longitude == 0:
        # the first packets from flightgear are often rubbish
        return

    status.counters['FGearIn'] += 1

    if yawDeg == 0.0:
        # not all planes give a yaw value
        yawDeg = heading

    if status.setup_mode:
        return

    try:
        lon_scale = math.cos(math.radians(latitude))
        gps_heading = math.degrees(math.atan2(lon_scale*speedE, speedN))
    except Exception:
        gps_heading = 0
    if gps_heading < 0:
        gps_heading += 360

    groundspeed = ft2m(math.sqrt((speedN * speedN) + (speedE * speedE)))

    if math.isnan(heading):
        heading = 0.0

    # send IMU data to the master
    status.counters['MasterOut'] += 1
    master.mav.attitude_send(get_usec(),
                             deg2rad(rollDeg), deg2rad(pitchDeg), deg2rad(yawDeg),
                             deg2rad(rollRate),deg2rad(pitchRate),deg2rad(yawRate))

    # and airspeed
    status.counters['MasterOut'] += 1
    if opts.quadcopter:
        master.mav.vfr_hud_send(kt2mps(airspeed), groundspeed, int(heading),
                                int(status.rc_throttle[0]*100), ft2m(altitude), 0)
    else:
        master.mav.vfr_hud_send(kt2mps(airspeed), groundspeed, int(heading),
                                int(status.rc_throttle*100), ft2m(altitude), 0)

    # remember GPS fix, we send this at opts.gpsrate
    status.gps = mavlink.MAVLink_gps_raw_message(get_usec(),
                                                 3, # we have a 3D fix
                                                 latitude, longitude,
                                                 ft2m(altitude),
                                                 0, # no uncertainty
                                                 0, # no uncertainty
                                                 groundspeed,
                                                 gps_heading)

def mkdir_p(dir):
    '''like mkdir -p'''
    if not dir:
        return
    if dir.endswith("/"):
        mkdir_p(dir[:-1])
        return
    if os.path.isdir(dir):
        return
    mkdir_p(os.path.dirname(dir))
    os.mkdir(dir)

def log_writer():
    '''log writing thread'''
    global mav_master
    m = mav_master
    while True:
        m.logfile_raw.write(m.logqueue_raw.get())
        while not m.logqueue_raw.empty():
            m.logfile_raw.write(m.logqueue_raw.get())
        while not m.logqueue.empty():
            m.logfile.write(m.logqueue.get())
        m.logfile.flush()
        m.logfile_raw.flush()
        if status_period.trigger():
            status.write()

def open_logs(mav_master):
    '''open log files'''
    if opts.append_log:
        mode = 'a'
    else:
        mode = 'w'
    logfile = opts.logfile
    if opts.aircraft is not None:
        dirname = "%s/logs/%s" % (opts.aircraft, time.strftime("%Y-%m-%d"))
        mkdir_p(dirname)
        for i in range(1, 10000):
            fdir = os.path.join(dirname, 'flight%u' % i)
            if not os.path.exists(fdir):
                break
        if os.path.exists(fdir):
            print("Flight logs full")
            sys.exit(1)
        mkdir_p(fdir)
        print(fdir)
        logfile = os.path.join(fdir, logfile)
        status.logdir = fdir
    print("Logging to %s" % logfile)
    mav_master.logfile = open(logfile, mode=mode)
    mav_master.logfile_raw = open(logfile+'.raw', mode=mode)

    # queues for logging
    mav_master.logqueue = Queue.Queue()
    mav_master.logqueue_raw = Queue.Queue()

    # use a separate thread for writing to the logfile to prevent
    # delays during disk writes (important as delays can be long if camera
    # app is running)
    t = threading.Thread(target=log_writer)
    t.daemon = True
    t.start()


# master mavlink device
mav_master = None

# mavlink outputs
mav_outputs = []

# flightgear input
fg_input = None

# flightgear output
fg_output = []

# SITL output
sitl_output = None

settings = settings()

def periodic_tasks(mav_master):
    '''run periodic checks'''
    if (status.setup_mode or
        status.target_system == -1 or
        status.target_component == -1):
        return

    if len(fg_output) != 0 and fg_period.trigger():
        for f in fg_output:
            send_flightgear_controls(f)

    if status.gps and gps_period.trigger():
        status.counters['MasterOut'] += 1
        mav_master.mav.send(status.gps)

    if heartbeat_period.trigger() and settings.heartbeat != 0:
        status.counters['MasterOut'] += 1
        if mavlink.WIRE_PROTOCOL_VERSION == '1.0':
            mav_master.mav.heartbeat_send(mavlink.MAV_TYPE_GCS, mavlink.MAV_AUTOPILOT_INVALID,
                                          0, 0, 0)
        else:
            MAV_GROUND = 5
            MAV_AUTOPILOT_NONE = 4
            mav_master.mav.heartbeat_send(MAV_GROUND, MAV_AUTOPILOT_NONE)

    if heartbeat_check_period.trigger() and (
        status.last_heartbeat != 0 and time.time() > status.last_heartbeat + 5):
        say("no heartbeat")
        status.heartbeat_error = True

    if msg_period.trigger():
        mav_master.mav.request_data_stream_send(status.target_system, status.target_component,
                                                mavlink.MAV_DATA_STREAM_ALL,
                                                settings.streamrate, 1)
    if not mav_master.param_fetch_complete and mav_master.time_since('PARAM_VALUE') > 2:
        mav_master.param_fetch_all()
 
    if battery_period.trigger():
        battery_report()

    if override_period.trigger():
        if status.override != [ 0 ] * 8:
            send_rc_override(mav_master)


def main_loop():
    '''main processing loop'''
    if not status.setup_mode:
        mav_master.wait_heartbeat()
        mav_master.mav.request_data_stream_send(mav_master.target_system, mav_master.target_component,
                                                mavlink.MAV_DATA_STREAM_ALL,
                                                settings.streamrate, 1)
        mav_master.param_fetch_all()

    while True:
        if status.exit:
            return
        if rl.line is not None:
            process_stdin(rl, rl.line, mav_master)
            rl.line = None

        if mav_master.fd is None:
            if mav_master.port.inWaiting() > 0:
                process_master(mav_master)

        periodic_tasks(mav_master)
    
        rin = []
        if mav_master.fd is not None:
            rin.append(mav_master.fd)
        for m in mav_outputs:
            rin.append(m.fd)
        if fg_input:
            rin.append(fg_input.fd)
        if rin == []:
            time.sleep(0.001)
            continue
        try:
            (rin, win, xin) = select.select(rin, [], [], 0.001)
        except select.error:
            continue

        for fd in rin:
            if fd == mav_master.fd:
                process_master(mav_master)
            for m in mav_outputs:
                if fd == m.fd:
                    process_mavlink(m, mav_master)
            if fg_input and fd == fg_input.fd:
                process_flightgear(fg_input, mav_master)


def input_loop():
    '''wait for user input'''
    while True:
        while rl.line is not None:
            time.sleep(0.01)
        try:
            line = raw_input(rl.prompt)
        except EOFError:
            status.exit = True
            sys.exit(1)
        rl.line = line
            

def run_script(scriptfile):
    '''run a script file'''
    try:
        f = open(scriptfile, mode='r')
    except Exception:
        return
    print("Running script %s" % scriptfile)
    for line in f:
        line = line.strip()
        if line == "":
            continue
        print("-> %s" % line)
        process_stdin(rl, line, mav_master)
    f.close()
        

if __name__ == '__main__':

    from optparse import OptionParser
    parser = OptionParser("mavproxy.py [options]")

    parser.add_option("--master",dest="master", help="MAVLink master port")
    parser.add_option("--baudrate", dest="baudrate", type='int',
                      help="master port baud rate", default=115200)
    parser.add_option("--out",   dest="output", help="MAVLink output port",
                      action='append', default=[])
    parser.add_option("--fgin",  dest="fgin",   help="flightgear input")
    parser.add_option("--fgout", dest="fgout",  action='append', default=[],
                      help="flightgear output")
    parser.add_option("--sitl", dest="sitl",  default=None, help="SITL output port")
    parser.add_option("--fgrate",dest="fgrate", default=50.0, type='float',
                      help="flightgear update rate")
    parser.add_option("--gpsrate",dest="gpsrate", default=4.0, type='float',
                      help="GPS update rate")
    parser.add_option("--streamrate",dest="streamrate", default=4, type='int',
                      help="MAVLink stream rate")
    parser.add_option("--source-system", dest='SOURCE_SYSTEM', type='int',
                      default=255, help='MAVLink source system for this GCS')
    parser.add_option("--target-system", dest='TARGET_SYSTEM', type='int',
                      default=-1, help='MAVLink target master system')
    parser.add_option("--target-component", dest='TARGET_COMPONENT', type='int',
                      default=-1, help='MAVLink target master component')
    parser.add_option("--logfile", dest="logfile", help="MAVLink master logfile",
                      default='mav.log')
    parser.add_option("-a", "--append-log", dest="append_log", help="Append to log files",
                      action='store_true', default=False)
    parser.add_option("--quadcopter", dest="quadcopter", help="use quadcopter controls",
                      action='store_true', default=False)
    parser.add_option("--setup", dest="setup", help="start in setup mode",
                      action='store_true', default=False)
    parser.add_option("--nodtr", dest="nodtr", help="disable DTR drop on close",
                      action='store_true', default=False)
    parser.add_option("--show-errors", dest="show_errors", help="show MAVLink error packets",
                      action='store_true', default=False)
    parser.add_option("--speech", dest="speech", help="use text to speach",
                      action='store_true', default=False)
    parser.add_option("--num-cells", dest="num_cells", help="number of LiPo battery cells",
                      type='int', default=0)
    parser.add_option("--aircraft", dest="aircraft", help="aircraft name", default=None)
    
    
    (opts, args) = parser.parse_args()

    if not opts.master:
        serial_list = mavutil.auto_detect_serial(preferred='*FTDI*')
        if len(serial_list) == 1:
            opts.master = serial_list[0].device
        else:
            print('''
Please choose a MAVLink master with --master
For example:
    --master=com14
    --master=/dev/ttyUSB0
    --master=127.0.0.1:14550

Auto-detected serial ports are:
''')
            for port in serial_list:
                print("%s" % port)
            sys.exit(1)

    # container for status information
    status = status()
    status.target_system = opts.TARGET_SYSTEM
    status.target_component = opts.TARGET_COMPONENT

    # open master link
    if opts.master.startswith('tcp:'):
        mav_master = mavutil.mavtcp(opts.master[4:])
    elif opts.master.find(':') != -1:
        mav_master = mavutil.mavudp(opts.master, input=True)
    elif opts.master.endswith(".elf"):
        mav_master = mavutil.mavchildexec(opts.master)  
    else:
        mav_master = mavutil.mavserial(opts.master, baud=opts.baudrate)
    mav_master.mav.set_callback(master_callback, mav_master, mav_outputs)

    # log all packets from the master, for later replay
    open_logs(mav_master)

    # open any mavlink UDP ports
    for p in opts.output:
        mav_outputs.append(mavutil.mavudp(p, input=False))

    # open any flightgear UDP ports
    if opts.fgin:
        fg_input = mavutil.mavudp(opts.fgin, input=True)
    for f in opts.fgout:
        fg_output.append(mavutil.mavudp(f, input=False))
    if opts.sitl:
        sitl_output = mavutil.mavudp(opts.sitl, input=False)

    settings.numcells = opts.num_cells
    settings.speech = opts.speech
    settings.streamrate = opts.streamrate

    fg_period = mavutil.periodic_event(opts.fgrate)
    gps_period = mavutil.periodic_event(opts.gpsrate)
    status_period = mavutil.periodic_event(1.0)
    msg_period = mavutil.periodic_event(1.0/30)
    heartbeat_period = mavutil.periodic_event(1)
    battery_period = mavutil.periodic_event(0.1)
    if sitl_output:
        override_period = mavutil.periodic_event(50)
    else:
        override_period = mavutil.periodic_event(1)
    heartbeat_check_period = mavutil.periodic_event(0.2)

    rl = rline("MAV> ")
    if opts.setup:
        rl.set_prompt("")

    if opts.aircraft is not None:
        start_script = os.path.join(opts.aircraft, "mavinit.scr")
        if os.path.exists(start_script):
            run_script(start_script)

    # run main loop as a thread
    status.thread = threading.Thread(target=main_loop)
    status.thread.daemon = True
    status.thread.start()

    # use main program for input. This ensures the terminal cleans
    # up on exit
    try:
        input_loop()
    except KeyboardInterrupt:
        print("exiting")
        status.exit = True
        sys.exit(1)
