__author__ = 'Fang'


import util
import os
import unicodecsv as ucsv
import math
import datetime


INTER_DATA_DIR = "Intermediate"
GRIDS_DICT = "grids_dict"
WAY_ID2NAME = "ways_id2name"
MAP_INFO = "map_info"
INIT_DATA_DIR = "init_data"
SPEED_LIMIT = "speed_limit"
FOLDER = "init_data/speed/"
TIME_POSITION_IN_CSV = 1
LONGITUDE_POSITION_IN_CSV = 2
LATITUDE_POSITION_IN_CSV = 3
MILEAGE_POSITION_IN_CSV = -1
RESULT = "Result"
TIME = 0
LAT = 1
LON = 2
MILE = 3
TYPE = -2
MAX_NUM = 1e20
THIRTY_MINUTES = 1800
STEP = 0.01
RADIUS = 6371000
LOGS = "solve.log"


def read_info():
    grids = util.read_json(GRIDS_DICT, INTER_DATA_DIR)
    way_name = util.read_json(WAY_ID2NAME, INTER_DATA_DIR)
    map_info = util.read_json(MAP_INFO, INTER_DATA_DIR)
    speed_limit = util.read_json(SPEED_LIMIT, INIT_DATA_DIR)
    return grids, way_name, map_info, speed_limit


def extract_info(init_file):
    data = []
    with open(init_file) as input_csv:
        reader = ucsv.reader(input_csv)
        for row in reader:
            data_row = [util.str_time_to_second(row[TIME_POSITION_IN_CSV]), float(row[LATITUDE_POSITION_IN_CSV]),
                        float(row[LONGITUDE_POSITION_IN_CSV]),
                        float(row[MILEAGE_POSITION_IN_CSV].split(u":")[1].split(u"k")[0])]
            data.append(data_row)
    return data


def find_grid(x, y):
    loc_x = int((x - Min_lat) / STEP)
    if loc_x == Num_lat:
        loc_x -= 1
    loc_y = int((y - Min_lon) / STEP)
    if loc_y == Num_lon:
        loc_y -= 1
    return loc_x, loc_y


def find_neighbor(lat, lon):
    loc_x, loc_y = find_grid(lat, lon)
    loc_id = loc_x * Num_lon + loc_y
    conner_x = Min_lat + STEP * loc_x
    conner_y = Min_lon + STEP * loc_y
    tmp_x = lat - conner_x
    tmp_y = lon - conner_y
    ret = [loc_id]
    # self
    up = loc_id - Num_lon
    down = loc_id + Num_lon
    left = loc_id - 1
    right = loc_id + 1
    up_left = up - 1
    up_right = up + 1
    down_left = down - 1
    down_right = down + 1
    if tmp_x < STEP / 2:
        # up
        if loc_x != 0:
            ret.append(up)
        if tmp_y < STEP / 2:
            # left up
            if loc_y != 0:
                ret.append(left)
                if loc_x != 0:
                    ret.append(up_left)
        else:
            # right up
            if loc_y != Num_lon - 1:
                ret.append(right)
                if loc_x != 0:
                    ret.append(up_right)
    else:
        # down
        if loc_x != Num_lat - 1:
            ret.append(down)
        if tmp_y < STEP / 2:
            # left down
            if loc_y != 0:
                ret.append(left)
                if loc_x != Num_lat - 1:
                    ret.append(down_left)
        else:
            # right down
            if loc_y != Num_lon - 1:
                ret.append(right)
                if loc_x != Num_lat - 1:
                    ret.append(down_right)
    return ret


def get_project_point(x0, y0, x1, y1, x2, y2):
    molecule = (x1 - x0) * (x1 - x2) + (y1 - y0) * (y1 - y2)
    denominator = (x1 - x2) * (x1 - x2) + (y1 - y2) * (y1 - y2)
    if denominator < 1e-8:
        return x1, y1
    temp = molecule / denominator
    ret_x = x1 + temp * (x2 - x1)
    ret_y = y1 + temp * (y2 - y1)
    return ret_x, ret_y


def cal_probe_distance(s_lat, s_lon, e_lat, e_lon):
    s_lat = math.radians(s_lat)
    s_lon = math.radians(s_lon)
    e_lat = math.radians(e_lat)
    e_lon = math.radians(e_lon)
    theta_lat = s_lat - e_lat
    theta_long = s_lon - e_lon
    first = pow(math.sin(theta_lat / 2.0), 2)
    second = math.cos(s_lat) * math.cos(e_lat) * pow(math.sin(theta_long / 2.0), 2)
    angle = 2 * math.asin(math.sqrt(first + second))
    return math.floor(RADIUS * angle + 0.5)


def cal_point_route(lat, lon, segment):
    s_x = float(segment.values()[0][u"snode"][0])
    s_y = float(segment.values()[0][u"snode"][1])
    e_x = float(segment.values()[0][u"enode"][0])
    e_y = float(segment.values()[0][u"enode"][1])
    p_x, p_y = get_project_point(lat, lon, s_x, s_y, e_x, e_y)
    if (p_x - s_x) * (p_x - e_x) < 1e-8 and (p_y - s_y) * (p_y - e_y) < 1e-8:
        return cal_probe_distance(lat, lon, p_x, p_y)
    else:
        return min(cal_probe_distance(lat, lon, s_x, s_y),cal_probe_distance(lat, lon, e_x, e_y))


def match_point_naive(lat, lon):
    neighbor_grid = find_neighbor(lat, lon)
    min_dis = MAX_NUM
    min_seg = u""
    min_type = u"unclassified"
    for grid_id in neighbor_grid:
        try:
            segments = Grids[str(grid_id)]
        except KeyError:
            continue
        for seg in segments:
            dist = cal_point_route(lat, lon, seg)
            if dist < min_dis:
                min_seg = seg.keys()[0]
                min_type = seg.values()[0][u"highway"]
                min_dis = dist
    return min_seg, min_type, min_dis


def match(start_line, end_line, rows):
    i = start_line
    while i <= end_line:
        matched_segment, segment_type, distance = match_point_naive(rows[i][LAT], rows[i][LON])
        try:
            matched_way_name = Way_name[matched_segment.split(u"_")[1]]
        except KeyError:
            matched_way_name = u""
            util.write_log(LOGS, "row %d pos ( %f , %f ) doesn't match\n" % (i, rows[i][LAT], rows[i][LON]))
        rows[i].extend([matched_way_name, matched_segment, segment_type, distance])


def test_over_speed(start_line, end_line, rows):
    i = start_line
    former_time = rows[i][TIME]
    former_mileage = rows[i][MILE]
    former_type = rows[i][TYPE]
    later_time = rows[i + 1][TIME]
    later_mileage = rows[i + 1][MILE]
    distance_later = later_mileage - former_mileage
    time_later = later_time - former_time
    v_former = 0
    if time_later != 0:
        v_former = distance_later * 1000 / time_later
    try:
        is_over_speed = v_former > Speed_limit[former_type]
    except KeyError:
        former_type = u"unclassified"
        is_over_speed = v_former > Speed_limit[former_type]
    rows[i].extend([v_former, is_over_speed])
    i += 1
    while i + 1 <= end_line:
        former_time = later_time
        former_mileage = later_mileage
        former_type = rows[i][TYPE]
        distance_former = distance_later
        time_former = time_later
        later_time = rows[i + 1][TIME]
        later_mileage = rows[i + 1][MILE]
        distance_later = later_mileage - former_mileage
        time_later = later_time - former_time
        v_former = 0
        if time_later != 0:
            v_former = (distance_former + distance_later) * 1000 / (time_former + time_later)
        try:
            is_over_speed = v_former > Speed_limit[former_type]
        except KeyError:
            former_type = u"unclassified"
            is_over_speed = v_former > Speed_limit[former_type]
        rows[i].extend([v_former, is_over_speed])
        i += 1
    former_type = rows[i][TYPE]
    distance_former = distance_later
    time_former = time_later
    v_former = 0
    if time_former != 0:
        v_former = distance_former * 1000 / time_former
    try:
        is_over_speed = v_former > Speed_limit[former_type]
    except KeyError:
        former_type = u"unclassified"
        is_over_speed = v_former > Speed_limit[former_type]
    rows[i].extend([v_former, is_over_speed])


def solve():
    for init_file in os.listdir(FOLDER):
        start_file = datetime.datetime.now()
        util.write_log(LOGS, "%s start\n" % init_file)
        rows = extract_info(FOLDER + init_file)
        filename = init_file.split(".")[0]
        folder = RESULT + "/" + filename
        os.mkdir(folder)
        os.chdir(folder)
        # select (cut) a part of rows to match
        file_idx = 0
        length = len(rows)
        row_written = -1
        last_diff = 0
        last_time = int(MAX_NUM)
        i = 0
        time_i = rows[0][TIME]
        mileage_i = rows[0][MILE]
        j = 1
        while j < length:
            mileage_j = rows[j][MILE]
            time_j = rows[j][TIME]
            if mileage_i == mileage_j:
                if (row_written != -1) and (time_j - last_time >= THIRTY_MINUTES):
                    if row_written != last_diff:
                        match(row_written, last_diff, rows)
                        test_over_speed(row_written, last_diff, rows)
                        with open(str(file_idx) + ".csv", "wb") as output_csv:
                            writer = ucsv.writer(output_csv)
                            writer.writerows(rows[row_written:last_diff + 1])
                        row_written = -1
                        file_idx += 1
            else:
                last_diff = i
                last_time = time_i
                if row_written == -1:
                    row_written = last_diff
            i += 1
            time_i = time_j
            mileage_i = mileage_j
            j += 1
        if (row_written != -1) and (row_written < length - 1):
            match(row_written, length - 1, rows)
            test_over_speed(row_written, length - 1, rows)
            with open(str(file_idx) + ".csv", "wb") as output_csv:
                writer = ucsv.writer(output_csv)
                writer.writerows(rows[row_written:])
        os.chdir("../..")
        end_file = datetime.datetime.now()
        util.write_log(LOGS, "%s finish , total costs %s\n" % (init_file, str(end_file - start_file)))


if __name__ == "__main__":
    start = datetime.datetime.now()
    Grids, Way_name, Map_info, Speed_limit = read_info()
    Min_lat, Max_lat, Min_lon, Max_lon, Num_lat, Num_lon, Num_grids = Map_info
    end = datetime.datetime.now()
    util.write_log(LOGS, "loading files costs %s\n" % str(end - start))
    solve()
