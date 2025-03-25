import logging
import time
import os.path

import pymongo
from scotty import utils

logger = logging.getLogger(__name__)


def run(context):
    start_time_workload = time.time()
    workload = context.v1.workload
    utils.ExperimentHelper(context)
    mongo_user = workload.params['mongo_user']
    mongo_password = workload.params['mongo_password']
    mongo_host = workload.params['mongo_host']
    mongo_port = workload.params['mongo_port']
    sample_size = workload.params['sample_size']
    mongo_port = int(float(mongo_port))
    database_name = 'smartshark_test'
    mongo_client = pymongo.MongoClient(
        mongo_host,
        mongo_port,
        username=mongo_user,
        password=mongo_password,
        authSource=database_name)
    database = mongo_client.smartshark_test
    collection = database.code_entity_state
    document_count = collection.count()
    collection_size_message = 'Collection.count() --> {}'.format(document_count)
    logger.info(collection_size_message)
    pipeline = [{
        '$sample': {
            'size': sample_size
        }
    }, {
        '$group': {
            '_id': None,
            'avg': {
                '$avg': '$start_line'
            }
        }
    }]
    logger.info('Beginning with the workload')
    start_time_query = time.time()
    collection.aggregate(pipeline)
    end_time_query = time.time()
    duration = end_time_query - start_time_query
    logger.info('The MSR workload took {}s'.format(duration))
    end_time_workload = time.time()
    _store_result(start_time_workload, end_time_workload, sample_size, duration)
    return {'duration': duration}


def _store_result(start_time, end_time, sample_size, duration):
    results_filename = 'results.csv'
    init_file = False
    if not os.path.exists(results_filename):
        init_file = True
    with open(results_filename, 'a') as results_file:
        if init_file:
            header_line = 'start, end, sample_size, duration\n'
            results_file.write(header_line)
        csv_line = '{}, {}, {}, {}\n'.format(start_time, end_time, sample_size, duration)
        results_file.write(csv_line)


def clean(context):
    pass
