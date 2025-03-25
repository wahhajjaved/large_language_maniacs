import logging

from scotty import utils

import pymongo

logger = logging.getLogger(__name__)


def run(context):
    workload = context.v1.workload
    utils.ExperimentHelper(context)
    logger.info('{}'.format(workload.params['greeting']))
    logger.info('mongo_user')
    pymongo.MongoClient()
    logger.info('I\'m workload generator {}'.format(workload.name))
    return None


def clean(context):
    pass
