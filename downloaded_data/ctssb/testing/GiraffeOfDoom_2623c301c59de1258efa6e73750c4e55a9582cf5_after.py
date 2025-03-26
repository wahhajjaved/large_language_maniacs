import sqlite3
import logging
import constants as k
from time import time
import statistics

errorloglevel = logging.WARNING
logging.basicConfig(filename=k.error_log, format='%(asctime)s %(message)s', level=errorloglevel)
logging.info("Created error log for this session")
dna_core = sqlite3.connect(k.dbfile)
db = dna_core.cursor()

# "SW_speed", "SW_Density"
station = "SW_Density"


def get_data(station):
    start_time = int(time()) - (60* 20)
    result = db.execute("select station_data.posix_time, station_data.data_value from station_data "
                        "where station_data.station_id = ? and station_data.posix_time > ? order by station_data.posix_time asc", [station, start_time])
    query_result = result.fetchall()
    db.close()
    return query_result


def process_dashboard(density):
    returnvalue = "none"
    if density < 10:
        returnvalue = "none"
    if density >= 10 and density < 20:
        returnvalue = "low"
    if density >= 20 and density < 40:
        returnvalue = "med"
    if density >=40:
        returnvalue = "high"
    return returnvalue


def create_dashboard(dash_msg):
    db = dna_core.cursor()
    t = int(time())
    values = [station, t, dash_msg]
    try:
        db.execute("insert into dashboard (station_id, posix_time, message) values (?,?,?)", values)
        dna_core.commit()
    except sqlite3.Error:
        print("DATABASE ERROR inserting new alert")
    db.close()

def wrapper():
    r = get_data(station)
    t = []
    for item in r:
        data = float(item[1])
        t.append(data)

    if len(t) > 2:
        avgdensity = statistics.mean(t)
        dashb_msg = process_dashboard(avgdensity)
        create_dashboard(dashb_msg)
    else:
        pass

wrapper()