# coding=utf-8
# __author__ = 'chengliang'
import os,json,time
from pprint import pprint


def list_logfiles(log_path, log_date=None):
    starTime = datetime_timestamp(log_date + ' 00:00:00')
    endTime = datetime_timestamp(log_date + ' 23:59:59')
    file_list = list()
    for parent, dirnames, filenames in os.walk(log_path):
        for filename in filenames:
            if filename[-4:] != '.txt':
                continue
            print 'processing: ' + parent + dirnames + '/' + filename
            try:
                file_time = int(filename[-14:-4])
            except ValueError:
                os.remove(log_path + '/'  + filename)
                continue

            if log_date is None:
                file_list.append(os.path.join(parent, filename))
            elif starTime <= file_time <= endTime :
                file_list.append(os.path.join(parent, filename))
    return file_list


def load_logfile(filename):
    s = json.load(file(filename))
    return s


def datetime_timestamp(dt):
    time.strptime(dt, '%Y-%m-%d %H:%M:%S')
    s = time.mktime(time.strptime(dt, '%Y-%m-%d %H:%M:%S'))
    return int(s)


def timestamp_datetime(value):
    dt_format = '%Y-%m-%d %H:%M:%S'
    value = time.localtime(value)
    dt = time.strftime(dt_format, value)
    return dt



