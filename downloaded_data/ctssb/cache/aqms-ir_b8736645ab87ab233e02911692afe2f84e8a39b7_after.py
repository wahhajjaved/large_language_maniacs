""" inventory is an obspy Inventory object """
import six

import logging
from collections import OrderedDict
import datetime

from obspy import UTCDateTime

from sqlalchemy import text

from .schema import Abbreviation, Format, Unit, Channel, Station, SimpleResponse, AmpParms, CodaParms, Sensitivity
from .schema import PZ, PZ_Data, Poles_Zeros, StaCorrection

# when active_only is true, only load currently active stations/channels
# this can be toggled to True by adding the keyword argument active=True
# to the main inventory2db function
ACTIVE_ONLY = False

# the PZ loading part is still buggy, make loading them optional
INCLUDE_PZ = False

# station or channel end-date when none has been provided
DEFAULT_ENDDATE = datetime.datetime(3000,1,1)

# noise level in m/s used for determining cutoff level for Md
CUTOFF_GM = 1.7297e-7

# units for seismic channels
SEISMIC_UNITS = ['M/S', 'm/s', 'M/S**2', 'm/s**2', 'M/S/S', 'm/s/s', 'CM/S', 'cm/s', 'CM/S**2', 'cm/s**2', 'CM/S/S', 'cm/s/s', 'M', 'm', 'CM', 'cm']
# simple_response DU/M/S or DU/M/S**2 or counts/(cm/sec) counts/(cm/sec2)
GAIN_UNITS = {'M/S' : 'DU/M/S', 
              'm/s' : 'DU/M/S', 
              'M/S**2' : 'DU/M/S**2', 
              'm/s**2' : 'DU/M/S**2', 
              'M/S/S' : 'DU/M/S**2', 
              'm/s/s' : 'DU/M/S**2', 
              'CM/S' : 'counts/(cm/sec)', 
              'cm/s': 'counts/(cm/sec)', 
              'CM/S**2' : 'counts/(cm/sec2)', 
              'cm/s**2' : 'counts/(cm/sec2)', 
              'CM/S/S' : 'counts/(cm/sec2)', 
              'cm/s/s' : 'counts/(cm/sec2)', 
              'M' : 'DU/M', 
              'm' : 'DU/M', 
              'CM' : 'counts/cm', 
              'cm' : 'counts/cm'
             }

# keep track of successful and failed commits
commit_metrics = OrderedDict()
commit_metrics["stations_good"] = []
commit_metrics["stations_bad"]  = []
commit_metrics["channels_good"] = []
commit_metrics["channels_bad"]  = []
commit_metrics["response_good"] = []
commit_metrics["response_bad"]  = []
commit_metrics["codaparms_good"]= []
commit_metrics["codaparms_bad"] = []
commit_metrics["ampparms_good"] = []
commit_metrics["ampparms_bad"]  = []
commit_metrics["clip_bad"]      = []
commit_metrics["sensitivity_good"] = []
commit_metrics["sensitivity_bad"]  = []

commit_metrics["pz_good"]  = []
commit_metrics["pz_bad"]  = []
commit_metrics["poles_zeros_good"]  = []
commit_metrics["poles_zeros_bad"]  = []

def inventory2db(session, inventory, active=False, include_pz=False):
    
    # ugly kluge to propagate these flags to all the methods
    global ACTIVE_ONLY
    global INCLUDE_PZ
    ACTIVE_ONLY = active
    INCLUDE_PZ = include_pz

    if inventory.networks:
        _networks2db(session, inventory.networks, inventory.source)
    else:
        logging.warning("This inventory has no networks, doing nothing.")
    return

def _networks2db(session, networks, source):
    for network in networks:
        _network2db(session,network,source)
    return

def _network2db(session, network, source):
    net_id = None
    if network.stations:
        success,failed = _stations2db(session,network, source)
        logging.info("\n Success: {} stations, failure: {} stations.\n".format(success,failed))
    else:
        # only insert an entry into D_Abbreviation
        net_id = _get_net_id(session, network)
        if not net_id:
            logging.warning("Did not add network description to database")
    return

def _get_net_id(session, network):
    """ 
       given obspy Network object 
       get id from d_abbreviation with
       same description (creates a new entry
       if none exists yet).
    """
    result = session.query(Abbreviation).filter_by(description=network.description).first()
    if result:
        return result.id
    else:
        network_entry = Abbreviation(description=network.description)
        session.add(network_entry)
        try:
            session.commit()
            result = session.query(Abbreviation).filter_by(description=network.description).first()
            return result.id
        except:
            logging.error("Not able to commit abbreviation and get net_id")
    return None

def _get_inid(session, channel):
    """ 
       get id from d_abbreviation with
       same instrument type description (creates a new entry
       if none exists yet).
    """
    result = session.query(Abbreviation).filter_by(description=channel.sensor.description).first()
    if result:
        return result.id
    else:
        instr_entry = Abbreviation(description=channel.sensor.description)
        session.add(instr_entry)
        try:
            session.commit()
            result = session.query(Abbreviation).filter_by(description=channel.sensor.description).first()
            return result.id
        except:
            logging.error("Not able to commit abbreviation and get inid")
    return None

def _get_unit(session, unit_name, unit_description):
    """ 
       get id from d_unit with
       same unit description (creates a new entry
       if none exists yet).
    """
    result = session.query(Unit).filter_by(name=unit_name, description=unit_description).first()
    if result:
        return result.id
    else:
        instr_entry = Unit(name=unit_name, description=unit_description)
        session.add(instr_entry)
        try:
            session.commit()
            result = session.query(Unit).filter_by(name=unit_name, description=unit_description).first()
            return result.id
        except:
            logging.error("Not able to commit abbreviation and get unit id")
    return None

def _get_format_id(session, format_name=None):
    """ 
       get id from d_format
       (creates a new entry
       if none exists yet).
    """
    if not format_name:
        format_name="UNKNOWN"

    result = session.query(Format).filter_by(name=format_name).first()

    if result:
        return result.id
    else:
        instr_entry = Format(name=format_name)
        session.add(instr_entry)
        try:
            session.commit()
            result = session.query(Format).filter_by(name=format_name).first()
            return result.id
        except:
            logging.error("Not able to commit format_name and get format id")
    return None

def _remove_station(session, network, station):
    """
        Removes this station from station_data and will remove
        its channels as well. See remove_channels.
    """
    try:
        # obspy objects?
        network_code = network.code
        station_code = station.code
    except Exception as e:
        # no, then assume regular strings
        logging.info("Station: {}.{}".format(network,station))
        network_code = network
        station_code = station

    status = 0

    try:
        status = session.query(Station).filter_by(net=network_code,sta=station_code).delete()
    except Exception as e:
        logging.error("remove_station: {}".format(e))

    try:
        session.commit()
        logging.info("Removed {}.{} from {}".format(network_code,station_code,Station.__tablename__))
    except Exception as e:
        logging.error("Unable to delete station {}.{} from {}: {}".format(network_code,station_code,Station.__tablename__,e))
        sys.exit()

    if hasattr(station,"channels") and len(station.channels) > 0:
        status = status + _remove_channels(session, network_code, station)
    else:
        # no need to construct channels, just using string should work:
        status = status + _remove_channels(session, network_code, station_code)
    
    return status

def _remove_channels(session, network_code, station):
    try:
        # obspy object?
        station_code = station.code
    except Exception as e:
        # if not, assume a regular string
        station_code = station

    status = 0
    # remove all channels for this station, not just the ones in the XML file
    try:
        status = session.query(Channel).filter_by(net=network_code,sta=station_code).delete()
    except Exception as e:
        logging.error("Unable to delete channels: {}.{}: {}".format(network_code,station_code,e))

    try:
        status = _remove_simple_responses(session, network_code, station_code)
    except Exception as e:
        logging.error("Unable to delete responses: {}.{}: {}".format(network_code,station_code,e))

    try:
        status = _remove_sensitivity(session, network_code, station_code)
    except Exception as e:
        logging.error("Unable to delete overall sensitivity: {}.{}: {}".format(network_code,station_code,e))

    try:
        status = _remove_poles_zeros(session, network_code, station_code)
    except Exception as e:
        logging.error("Unable to delete poles and zeros: {}.{}: {}".format(network_code,station_code,e))

    try:
        commit_status = session.commit()
        logging.info("Successfully removed channels and instrument response for {}.{}".format(network_code,station_code))
    except Exception as e:
        logging.error("Unable to commit deletions from channels and response tables".format(e))

    return status

def _remove_simple_responses(session, network_code, station_code):

    try:
        status = session.query(SimpleResponse).filter_by(net=network_code,sta=station_code).delete()
    except Exception as e:
        logging.error("remove_simple_responses: {}.{}: {}".format(network_code,station_code,e))

    try:
        status = session.query(CodaParms).filter_by(net=network_code,sta=station_code).delete()
    except Exception as er:
        logging.error("remove_simple_responses, codaparms: {}.{}: {}".format(network_code,station_code,er))

    try:
        status = session.query(AmpParms).filter_by(net=network_code,sta=station_code).delete()
    except Exception as error:
        logging.error("remove_simple_responses,ampparms: {}.{}: {}".format(network_code,station_code,error))

    return status

def _remove_sensitivity(session, network_code, station_code):

    try:
        status = session.query(Sensitivity).filter_by(net=network_code,sta=station_code).delete()
    except Exception as e:
        logging.error("remove_sensitivity: {}.{}: {}".format(network_code,station_code,e))

    return status

def _remove_poles_zeros(session, network_code, station_code):
    """
        Removes any rows in poles_zeros for this station. Will also remove
        the PZ and PZ_Data entries if there are no other poles_zeros rows that
        refer to them, to limit the number of obsolete PZ,PZ_Data rows in the
        database.
    """

    pz_keys = set()
    status = -1
    logging.debug("In _remove_poles_zeros, for station {}.{}".format(network_code,station_code))
    try:
        all_in_list = session.query(Poles_Zeros.pz_key).filter_by(net=network_code,sta=station_code).all()
        for key in all_in_list:
            pz_keys.add(key)
        logging.debug("Retrieved {} unique pole zero keys for {}.{}\n".format(len(pz_keys),network_code,station_code))
        status = session.query(Poles_Zeros).filter_by(net=network_code,sta=station_code).delete()
        logging.debug("Deleting poles_zeros entries: {}".format(status))
    except Exception as e:
        logging.error(e)

    for key in pz_keys:
        # do other poles_zeros entries using this key? yes, keep, no, remove.
        rows_returned = session.query(Poles_Zeros.pz_key).filter(Poles_Zeros.pz_key==key, Poles_Zeros.net != network_code, Poles_Zeros.sta != station_code).all()
        logging.debug("PZ KEY: {}. Number of other poles_zeros that use this set of poles and zeros: {}".format(key,len(rows_returned)))
        if len(rows_returned) > 0:
            logging.debug("PZ and PZ_Data in use, not removing")
        else:
            # remove as well.
            status = status + session.query(PZ).filter_by(key=key).delete()
            status1 = session.query(PZ_Data).filter_by(key=key).delete()
            logging.debug("Removed {} PZ and PZ_data entries".format(status))

    return status 

def _remove_channel(session, network_code, station_code, channel):
    """
        Removes this channel from channel_data and will remove
        its response as well. See remove_simple_response
    """
    status = 0
    try:
        status = session.query(Channel).filter_by(net=network_code,sta=station_code \
                 ,seedchan=channel.code,location=fix(channel.location_code)).delete()
    except Exception as e:
        logging.error("remove_channel: {}".format(e))

    try:
        session.commit()
    except Exception as e:
        logging.error("Unable to delete channel {}.{}.{}.{}: {}".format(network_code,station_code,channel.code, channel.location_code,e))

    if channel.response:
        try:
            my_status = _remove_simple_response(session, network_code, station_code, channel.code, channel.location_code)
        except Exception as e:
            logging.error("remove_channel ({}): {}".format(my_status, e))

    return status

def _remove_simple_response(session, network_code, station_code, channel_code, location_code):

    try:
        status = session.query(SimpleResponse).filter_by(net=network_code,sta=station_code \
                     ,seedchan=channel_code,location=fix(location_code)).delete()
    except Exception as e:
        logging.error("remove_simple_response: {}".format(e))

    try:
        status = session.query(CodaParms).filter_by(net=network_code,sta=station_code \
                 ,seedchan=channel_code,location=fix(location_code)).delete()
    except Exception as er:
        logging.error("remove_simple_response, codaparms: {}".format(er))

    try:
        status = session.query(AmpParms).filter_by(net=network_code,sta=station_code \
                 ,seedchan=channel_code,location=fix(location_code)).delete()
    except Exception as error:
        logging.error("remove_simple_response,ampparms: {}".format(error))

    return status

def _station2db(session, network, station, source):

    net_id = _get_net_id(session,network)
    network_code = network.code
    station_code = station.code
    default_enddate = datetime.datetime(3000,1,1)
    # first remove any prior meta-data associated with Net-Sta and Net-Sta-Chan-Loc
    try:
        status = _remove_station(session,network,station)
        logging.info("Removed {} channels for station {}".format(status-1,station_code))
    except Exception as e:
        logging.error("Exception: {}".format(e))

    db_station = Station(net=network.code, sta=station.code, ondate=station.start_date.datetime)

    db_station.net_id = net_id
    if hasattr(station,"end_date") and station.end_date:
        db_station.offdate = station.end_date.datetime
    else:
        db_station.offdate = DEFAULT_ENDDATE

    # return if ACTIVE_ONLY is true and the station's offdate pre-dates today
    if ACTIVE_ONLY and db_station.offdate < UTCDateTime():
        logging.info("Station {}.{} not active, not adding".format(network.code,station.code))
        return

    session.add(db_station)
    db_station.lat = station.latitude
    db_station.lon = station.longitude
    db_station.elev = station.elevation
    db_station.staname = station.site.name

    try:
        session.commit()
        commit_metrics["stations_good"].append(station_code)
    except Exception as e:
        logging.error("Cannot save station_data: {}".format(e))
        commit_metrics["stations_bad"].append(station_code)
        
    if station.channels:
        _channels2db(session, network_code, station_code, station.channels, source)

    # magnitude station corrections 
    # only add default values if there is no entry in stacorrections for this station yet!
    try:
        logging.debug("Querying for station correction entries for {}.{}".format(network_code,station_code))
        stacors = session.query(StaCorrection).filter_by(net=network_code,sta=station_code).all()
        logging.debug("Number of station corrections: {}".format(len(stacors)))
        if len(stacors) == 0:
            # add default values for this station
            _insert_default_stacors(network_code,station_code)
    except Exception as e:
        logging.error("Unable to query station corrections for {}.{}: {}".format(network_code,station_code,e))

    return

def _insert_default_stacors(session,network_code,station_code):
    """
        inserts 0. (ml) and 1. (me) corrections for horizontal channels
    """
    statement = text("select net, sta, seedchan, location, min(ondate), max(offdate) "
                "from channel_data where seedchan in ('SNN', 'SNE', 'BNN', 'BNE', "
                "'ENN', 'ENE', 'HNN', 'HNE', 'EHN', 'EHE', 'BHN', 'BHE', 'HHN', "
                "'HHE', 'EH1','EH2','BH1','BH2','HH1','HH2') and  "
                "samprate in (20, 40, 50, 80, 100, 200) and net=:net and sta=:sta "
                "group by net, sta, seedchan,location")
    statement = statement.columns(Channel.net,Channel.sta,Channel.seedchan,Channel.location,Channel.ondate,Channel.offdate)
    logging.debug(statement)
    try:
        horizontals = session.query(Channel).from_statement(statement).params(net=network_code,sta=station_code).all()
        for chan in horizontals:
            for corr_type in ['ml', 'me']:
                scor = StaCorrection()
                scor.net = chan.net
                scor.sta = chan.sta
                scor.seedchan = chan.seedchan
                scor.location = chan.location
                scor.ondate = chan.ondate
                scor.offdate = chan.offdate
                scor.auth="UW"
                scor.corr_flag="C"
                if corr_type == "ml":
                    scor.corr = 0.
                else:
                    scor.corr = 1.
                scor.corr_type=corr_type
                session.add(scor)
    except Exception as e:
        logging.error("Unable to create default station correction for {}.{}: {}".format(network_code, station_code,e))
                   
    try:
        session.commit()
    except Exception as e:
        logging.error("Unable to commit station correction: {}".format(e))

    return

def _stations2db(session, network, source):
    success = 0
    failed = 0
    for station in network.stations:
        try:
             _station2db(session, network, station, source)
             success = success + 1
        except Exception as e:
            logging.error("Unable to add station {} to db: {}".format(station.code, e))
            failed = failed + 1
            continue
    return success, failed

def _channel2db(session, network_code, station_code, channel, source):

    if source != "IRIS-DMC":
        try:
            new_description = "{},{},{}".format(channel.sensor.model,channel.sensor.description,channel.sensor.manufacturer)
            channel.sensor.description = new_description
        except Exception as e:
            logging.error("Unable to change sensor description of channel {}.{} to db: {}".format(station_code,channel.code, e))

    inid = _get_inid(session, channel)
    calib_unit = _get_unit(session, channel.calibration_units, channel.calibration_units_description)
    if hasattr(channel.response,"instrument_sensitivity") and channel.response.instrument_sensitivity:
        signal_unit = _get_unit(session, channel.response.instrument_sensitivity.input_units, channel.response.instrument_sensitivity.input_units_description)
    elif hasattr(channel.response,"instrument_polynomial"):
        signal_unit = _get_unit(session, channel.response.instrument_polynomial.input_units, channel.response.instrument_polynomial.input_units_description)
    else:
        signal_unit=None

    format_id = _get_format_id(session)

    db_channel = Channel(net=network_code, sta=station_code, seedchan=channel.code, location=fix(channel.location_code), ondate=channel.start_date.datetime)

    if inid:
        db_channel.inid = inid

    if signal_unit:
        db_channel.unit_signal = signal_unit
    if calib_unit:
        db_channel.unit_calib = calib_unit
    db_channel.format_id = format_id
    if hasattr(channel,"end_date") and channel.end_date:
        db_channel.offdate = channel.end_date.datetime
    else:
        db_channel.offdate = DEFAULT_ENDDATE

    # return if ACTIVE_ONLY is true and the channel's offdate pre-dates today
    if ACTIVE_ONLY and db_channel.offdate < UTCDateTime():
        logging.info("Channel {}.{}.{}.{} not active, not adding".format(network_code,station_code,channel.code,channel.location_code))
        return

    session.add(db_channel)
    db_channel.lat = channel.latitude
    db_channel.lon = channel.longitude
    db_channel.elev = channel.elevation
    db_channel.edepth = channel.depth
    db_channel.azimuth = float(channel.azimuth)
    db_channel.dip = float(channel.dip)
    db_channel.samprate = float(channel.sample_rate)
    db_channel.flags = ''.join(t[0] for t in channel.types)


    try:
        session.commit()
        commit_metrics["channels_good"].append(station_code + "." + channel.code)
    except Exception as e:
        logging.error("Cannot save to channel_data: {}".format(e))
        commit_metrics["channels_bad"].append(station_code + "." + channel.code)

    if channel.response:
        try:
            _response2db(session, network_code, station_code, channel)
        except Exception as e:
            logging.error("Unable to add response for {}.{}.{} to db: {}".format(network_code,station_code,channel.code,e))

    return


def _channels2db(session, network_code, station_code, channels, source):
    for channel in channels:
        try:
            _channel2db(session, network_code, station_code, channel, source)
        except Exception as e:
            logging.error("Unable to add channel {} to db: {}".format(channel.code, e))
            continue
    return

def _response2db(session, network_code, station_code, channel,fill_all=False):


    # for now, only fill simple_response, channelmap_ampparms and channelmap_codaparms tables
    _simple_response2db(session,network_code,station_code,channel)

    # overall sensitivity
    if hasattr(channel.response,"instrument_sensitivity") and channel.response.instrument_sensitivity:
        _sensitivity2db(session,network_code,station_code,channel)

    if fill_all:
        # do all IR tables, not implemented yet.
        pass

    if INCLUDE_PZ:
        pz = None
        pz = channel.response.get_paz()
        if pz:
            _poles_zeros2db(session,network_code,station_code,channel)
        else:
            logging.warn("sta:{} chan:{} has no pz stage!".format(station_code, channel.code))


    return

def _simple_response2db(session,network_code,station_code,channel):
    from .util import simple_response, parse_instrument_identifier, get_cliplevel

    if not hasattr(channel.response,"instrument_sensitivity") or not channel.response.instrument_sensitivity:
        logging.warning("{}-{} does not have an instrument sensitivity, no response".format(station_code,channel.code))
        return

    if not hasattr(channel.response.instrument_sensitivity,"input_units") or \
           channel.response.instrument_sensitivity.input_units not in SEISMIC_UNITS:
        logging.warning("{}-{} is not a seismic component, no response".format(station_code,channel.code))
        return

    fn, damping, lowest_freq, highest_freq, gain = simple_response(channel.sample_rate,channel.response)

    db_simple_response = SimpleResponse(net=network_code, sta=station_code, \
                         seedchan=channel.code, location=fix(channel.location_code), \
                         ondate=channel.start_date.datetime)

    session.add(db_simple_response)

    db_simple_response.channel = channel.code
    db_simple_response.natural_frequency = fn
    db_simple_response.damping_constant = damping
    db_simple_response.gain = gain
    # gcda codes(rad2,ampgen) currently only understand DU/M/S or DU/M/S**2
    db_simple_response.gain_units = GAIN_UNITS[channel.response.instrument_sensitivity.input_units]
    db_simple_response.low_freq_corner = highest_freq
    db_simple_response.high_freq_corner = lowest_freq
    if hasattr(channel,"end_date") and channel.end_date:
        db_simple_response.offdate = channel.end_date.datetime
    else:
        db_simple_response.offdate = DEFAULT_ENDDATE

    try:
        session.commit()
        commit_metrics["response_good"].append(station_code + "." + channel.code)
    except Exception as e:
        logging.error("Unable to add simple_response {} to db: {}".format(db_simple_response,e))
        commit_metrics["response_bad"].append(station_code + "." + channel.code)

    # next fill channelmap_codaparms (only for seismic channels, verticals)
    if channel.dip != 0.0:

        db_codaparms = CodaParms(net=network_code, sta=station_code, \
                       seedchan=channel.code, location=fix(channel.location_code), \
                       ondate=channel.start_date.datetime)
        session.add(db_codaparms)
        db_codaparms.channel = channel.code
        db_codaparms.cutoff = gain * CUTOFF_GM # cutoff in counts
        # this is too low for strong-motion channels, multiply with 1000 to get something reasonable
        if channel.code[1] == "N":
            db_codaparms.cutoff = 1000.0 * db_codaparms.cutoff
        if hasattr(channel,"end_date") and channel.end_date:
            db_codaparms.offdate = channel.end_date.datetime
        else:
            db_codaparms.offdate = DEFAULT_ENDDATE
        try:
            session.commit()
            commit_metrics["codaparms_good"].append(station_code + "." + channel.code)
        except Exception as er:
            logging.error("Unable to add codaparms {} to db: {}".format(db_codaparms,er))
            commit_metrics["codaparms_bad"].append(station_code + "." + channel.code)

    # next fill channelmap_ampparms, for seismic channels only, all components

    if network_code in ["UW", "CC", "UO", "HW"]:

        # get sensor and logger info
        if "=" in channel.sensor.description and "-" in channel.sensor.description:
            # PNSN instrument identifier
            sensor, sensor_sn, logger, logger_sn = parse_instrument_identifier(channel.sensor.description)
        elif len(channel.sensor.description.split(",")) == 3:
            # possibly instrument identifier from SIS dataless->IRIS->StationXML
            sensor, sensor_sn, logger, logger_sn = parse_instrument_identifier(channel.sensor.description)
        else:
            sensor = channel.sensor.type
            sensor_sn = channel.sensor.serial_number
            logger = channel.data_logger.type
            logger_sn = channel.data_logger.serial_number

        logging.info("{}-{}: channel equipment: {}-{}={}-{}".format(station_code,channel.code,sensor,sensor_sn,logger,logger_sn))

        try:
            clip = get_cliplevel(sensor,sensor_sn,logger,logger_sn, gain)
        except Exception as err:
            logging.error("Cannot determine cliplevel {}: {}".format(channel.sensor,err))

    else:
        # first see if there is something like 2g,3g,4g in instrument identifier
        if "2g" in channel.sensor.description:
            clip = gain * 2 * 9.8
        elif "4g" in channel.sensor.description:
            clip = gain * 4 * 9.8
        elif "1g" in channel.sensor.description:
            clip = gain * 9.8
        elif "3g" in channel.sensor.description:
            clip = gain * 3 * 9.8
        elif channel.code[1] == "N" or channel.code[1] == "L":
            # strong-motion, assume 4g
            clip = gain * 4 * 9.8
        elif channel.code[0:2] in ["EH", "SH"]:
            # short-period
            clip = gain * 0.0001
        elif channel.code[0:2] in ["LH", "MH", "BH", "HH"]:
            # 1 cm/s
            clip = gain * 0.0100
        else:
            clip = -1
        
    if clip == -1:
        logging.error("No valid clip level found for {}".format(channel))
    # have clip, fill channelmap_ampparms                
    db_ampparms = AmpParms(net=network_code, sta=station_code, \
                  seedchan=channel.code, location=fix(channel.location_code), \
                  ondate=channel.start_date.datetime)

    session.add(db_ampparms)
    db_ampparms.channel = channel.code
    db_ampparms.clip = clip
    if hasattr(channel,"end_date") and channel.end_date:
        db_ampparms.offdate = channel.end_date.datetime
    else:
        db_ampparms.offdate = DEFAULT_ENDDATE
    if not clip or clip == -1:
        commit_metrics["clip_bad"].append(station_code + "." + channel.code)
    try:
        session.commit()
        commit_metrics["ampparms_good"].append(station_code + "." + channel.code)
    except Exception as error:
        logging.error("Unable to add ampparms {} to db: {}".format(db_ampparms,error))
        commit_metrics["ampparms_bad"].append(station_code + "." + channel.code)

    return

def _sensitivity2db(session,network_code,station_code,channel):
    db_sensitivity = Sensitivity(net=network_code, sta=station_code, seedchan=channel.code, location=fix(channel.location_code), ondate=channel.start_date.datetime)
    session.add(db_sensitivity)
    db_sensitivity.stage_seq = 0
    db_sensitivity.sensitivity = channel.response.instrument_sensitivity.value
    db_sensitivity.frequency = channel.response.instrument_sensitivity.frequency
    if hasattr(channel,"end_date") and channel.end_date:
        db_sensitivity.offdate = channel.end_date.datetime
    else:
        db_sensitivity.offdate = DEFAULT_ENDDATE

    try:
        session.commit()
        commit_metrics["sensitivity_good"].append(station_code + "." + channel.code)
    except Exception as error:
        logging.error("Unable to add overall sensitivity {} to db: {}".format(db_sensitivity,error))
        commit_metrics["sensitivity_bad"].append(station_code + "." + channel.code)

    return


def _poles_zeros2db(session,network_code,station_code,channel):
    """
       TO DO:
            - run channel.response.get_paz first!  returns obspy PolesZerosResponseStage
            - get the name of the poles_zeros response if it exists (pz.name), USE IT for PZ table. If not, 
              see if there is a sensor description and use it. If not, make something up like you did here.
            - If the named response is already in the database PZ table, use its pz_key to retrieve the info from PZ_Data,
              if the poles and zeros are the same, do not add another entry to PZ and PZ_Data.
            - get the stage_sequence number from it, pz.stage_sequence_number and USE IT for Poles_Zeros.stage_seq.
    """
    name = "Key to polezero response for sta:%s cha:%s" % (station_code, channel.code)

    db_pz = PZ(name=name)
    session.add(db_pz)
    try:
        session.commit()
        commit_metrics["pz_good"].append(station_code + "." + channel.code)
    except Exception as error:
        logging.error("Unable to add pz {} to db: {}".format(db_pz,error))
        commit_metrics["pz_bad"].append(station_code + "." + channel.code)
    #session.flush()
    pz_key = db_pz.key
    if pz_key is None:
        logging.error("Error retrieving pz_key we just inserted in db! sta:%s cha:%s" % \
                      (station_code, channel.code))

    pz = channel.response.get_paz()
    # May need to expand testing to determine if this is A (Laplace - rad/s) or B (Hz - /s)
    tf_type='B'
    if "LAPLACE" in pz.pz_transfer_function_type or "RADIAN" in pz.pz_transfer_function_type:
        tf_type='A'
    unit_in  = pz.input_units
    unit_out = pz.output_units
    zeros = pz.zeros
    poles = pz.poles
    ao = pz.normalization_factor
    af = pz.normalization_frequency

    unit_in_id  = _get_unit(session, pz.input_units, pz.input_units_description)
    unit_out_id = _get_unit(session, pz.output_units, pz.output_units_description)
    logging.info("MTH: insert poles_zeros: pz_key=[%s] tf_type=[%s] ao=%f" % \
                 (pz_key, tf_type, ao))

    db_poles_zeros = Poles_Zeros(net=network_code, sta=station_code, seedchan=channel.code, \
                                 location=fix(channel.location_code), \
                                 ondate=channel.start_date.datetime, stage_seq=0, \
                                 unit_in=unit_in_id, unit_out=unit_out_id, \
                                 ao=ao, af=af, tf_type=tf_type,
                                 pz_key=pz_key)

    session.add(db_poles_zeros)

    logging.info("MTH: npoles=%d nzeros=%d" % (len(poles), len(zeros)))
    db_pzs = []

    row_key=0
    pz_type = 'Z'
    for zero in zeros:
        db_pzs.append( PZ_Data(key=pz_key, row_key=row_key, pztype=pz_type, r_value=zero.real, i_value=zero.imag) )
        logging.info("MTH: insert zero: pz_key=[%s] row_key=[%s]" % (pz_key, row_key))
        row_key += 1
    pz_type = 'P'
    for pole in poles:
        db_pzs.append( PZ_Data(key=pz_key, row_key=row_key, pztype=pz_type, r_value=pole.real, i_value=pole.imag) )
        logging.info("MTH: insert pole: pz_key=[%s] row_key=[%s]" % (pz_key, row_key))
        row_key += 1

    for dbpz in db_pzs:
        session.add(dbpz)

    if hasattr(channel,"end_date") and channel.end_date:
        db_poles_zeros.offdate = channel.end_date.datetime
    else:
        db_poles_zeros.offdate = DEFAULT_ENDDATE

    try:
        session.commit()
        commit_metrics["poles_zeros_good"].append(station_code + "." + channel.code)
    except Exception as error:
        logging.error("Unable to add poleszeros {} to db: {}".format(db_poles_zeros,error))
        commit_metrics["poles_zeros_bad"].append(station_code + "." + channel.code)

    return


def fix(location):
    if location == "":
        return "  "
    else:
        return location

def print_metrics(bad_only=True, abbreviated=False):
    """ Returns number of bad metrics and prints
        metrics to the screen.
        
        param: bad_only Toggle whether to only show bad commits (default=True)
        type: boolean
        param: abbreviated Shorter output (default=False)
        type: boolean
    """
    bad_metrics = 0
    for k,v in six.iteritems(commit_metrics):
        if len(v) > 0:
            if "bad" in k:
                bad_metrics += 1
            if bad_only and "bad" in k:
                if abbreviated:
                    print("{}: {}".format(k,len(v)))
                else:
                    print_metric(k,v)
            elif not bad_only:
                if abbreviated:
                    print("{}: {}".format(k,len(v)))
                else:
                    print_metric(k,v)
    return bad_metrics

def print_metric(key, values):

    indent = "    "
    print("{}\n:".format(key))
    for v in values:
        print("{}{}".format(indent,v))
    return
    
     
    
