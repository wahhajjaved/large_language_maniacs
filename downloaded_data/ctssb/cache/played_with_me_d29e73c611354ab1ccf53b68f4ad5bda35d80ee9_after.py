from models import *
from huey.djhuey import crontab, periodic_task, db_task
import logging


log = logging.getLogger('pwm_logger')

@db_task()
def download_games(account_id):
    log.info("requisitando download de " + str(account_id))
    last_match_id = None
    while True:
        try:
            log.info("acc: {} last match: {}".format(account_id, last_match_id or 'started'))
            matches = get_until_success(lambda: dota_api.get_match_history(account_id,
                                                                           start_at_match_id=last_match_id))
            log.info("acc: {} results remaining: {}".format(account_id, matches.results_remaining))
            if matches.results_remaining <= 0:
                log.info("acc: {} finished parsing".format(account_id))
                return

            log.info("acc {} parse matches: {}".format(account_id, [m.match_id for m in matches.matches]))
            for match in matches.matches:
                with transaction.atomic():
                    get_details_match(match.match_id)

                last_match_id = match.match_id
                log.info("acc: {} parsed: {}".format(account_id, last_match_id))
        except Exception, e:
            log.exception(e)
