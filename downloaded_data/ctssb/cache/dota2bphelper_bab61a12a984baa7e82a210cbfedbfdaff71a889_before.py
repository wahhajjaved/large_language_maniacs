import dota2api2
from pymongo import MongoClient
import time
import pymongo
from pandas import DataFrame, Series
import pandas as pd
import numpy as np

import sys

import json
from bson import BSON
from bson import json_util

db_client = MongoClient()
db = db_client.match_data_details

statics_db = db_client.match_statics

import psycopg2
import logging
import settings

console = logging.StreamHandler()
console.setLevel(logging.INFO)

psql_conn = psycopg2.connect("host='localhost' dbname={} user={}".format(settings.PSQL_DB,settings.PSQL_USER))
psql_cursor = psql_conn.cursor()

mongo_db_client = pymongo.MongoClient()
mongo_db = mongo_db_client.match_statics

def main():
    while true:
        hero_win_rate()

def hero_win_rate():
    psql_cursor.execute("SELECT * FROM dota2_hero;")
    hero_records = psql_cursor.fetchall()

    for record in hero_records:
        psql_cursor.execute("SELECT * FROM win_rate WHERE hero_id={};".format(int(record[1])))
        result = psql_cursor.fetchall()
        if len(result)>0:
            result_info = get_hero_record(int(record[1]),int(result[0][-1]))
            if result_info['total_match'] > 0:
                psql_cursor.execute("UPDATE win_rate \
                SET total_match={}, win_match={}, last_match_seq={} \
                WHERE id={}\
                ".format(result[0][4]+result_info['total_match'],result[0][5]+result_info['win_match'],result[0][4]+result_info['max_seq'],int(result[0][0])))
            psql_conn.commit()
        else:
            result_info = get_hero_record(int(record[1]),0)
            if result_info['total_match'] > 0:
                psql_cursor.execute("INSERT INTO win_rate (hero_id,total_match,win_match,last_match_seq) VALUES ({},{},{},{})".format(int(record[1]),result_info['total_match'],result_info['win_match'],result_info['max_seq']))
            psql_conn.commit()
        print('.')
        # hero_match = mongo_db.match_record.find({"hero_id":int(record[1])})
        # hero_win_match = mongo_db.match_record.find({"$and":[{"hero_id":int(record[1])},{"win":True}]})
    psql_cursor.close()
    psql_conn.close()

def get_hero_record(hero_id,max_seq):
    hero_match = mongo_db.match_record.find({"$and":[{"hero_id":hero_id},{"match_seq":{"$gt":max_seq}}]})
    hero_win_match = mongo_db.match_record.find({"$and":[{"hero_id":hero_id},{"match_seq":{"$gt":max_seq}},{"win":True}]})
    hero_info = dict()
    hero_info['total_match'] = hero_match.count() if hero_match.count() > 0 else 0
    hero_info['win_match'] = hero_win_match.count() if hero_win_match.count()> 0 else 0

    last_record = mongo_db.match_record.find_one({"$and":[{"hero_id":hero_id},{"match_seq":{"$gt":max_seq}}]},sort=[("match_seq", -1)])
    if last_record :
        hero_info['max_seq'] = last_record["match_seq"]
    else:
        hero_info['max_seq'] = 0
    return hero_info

if __name__ == '__main__':
    main()
