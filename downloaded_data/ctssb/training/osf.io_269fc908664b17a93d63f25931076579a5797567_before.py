import sys
import logging

from website.app import init_app
from website.models import User
from scripts import utils as script_utils
from modularodm import Q
from bson.son import SON
from framework.mongo import database as db

logger = logging.getLogger(__name__)

pipeline = [
    {"$unwind": "$emails"},
    {"$group": {"_id": { "$toLower" : "$emails"}, "count": {"$sum": 1}}},
    {"$sort": SON([("count", -1), ("_id", -1)])}
]


def get_duplicate_email():
    duplicate_emails = []
    result = db['user'].aggregate(pipeline)
    for each in result['result']:
        if each['count'] > 1:
            duplicate_emails.append(each['_id'])
    return duplicate_emails


def log_duplicate_acount(dry):
    duplicate_emails = get_duplicate_email()
    if duplicate_emails:
        for email in duplicate_emails:
            user = User.find(Q('emails', 'eq', email) & Q('merged_by', 'ne', None) & Q('username', 'ne', None))
            logger.info("User {}, username {}, id {}, email {} is a duplicate"
                        .format(user.fullname, user.username, user._id, user.emails))
    else:
        logger.infoe("There is no duplicate emails.")


def main():
    init_app(routes=False)  # Sets the storage backends on all models
    dry = 'dry' in sys.argv
    if not dry:
        script_utils.add_file_logger(logger, __file__)
    log_duplicate_acount(dry)


if __name__ == '__main__':
    main()




