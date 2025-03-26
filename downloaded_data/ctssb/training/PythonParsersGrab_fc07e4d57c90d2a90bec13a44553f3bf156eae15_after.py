# main.py
# Parser runner, based on grab framework
# r29

import logging
import os
import sys
import traceback

from datetime import datetime

from dev.logger import logger_setup
from helpers.config import Config
from helpers.fix_dir import fix_dirs
from helpers.module_loader import ModuleLoader
from helpers.save.data_saver_csv import DataSaverCSV
from helpers.save.data_saver_json import DataSaverJSON

CURRENT_VERSION = 29


def init_loggers():
    logger_setup(
        os.path.join(Config.get('APP_OUTPUT_DIR'), Config.get('APP_LOG_DIR'), Config.get('APP_LOG_DEBUG_FILE')),
        ['ddd_site_parse'], True)

    logger_setup(
        os.path.join(Config.get('APP_OUTPUT_DIR'), Config.get('APP_LOG_DIR'), Config.get('APP_LOG_GRAB_FILE')), [
            'grab.document',
            'grab.spider.base',
            'grab.spider.task',
            'grab.spider.base.verbose'
            'grab.proxylist',
            'grab.stat',
            'grab.script.crawl'
        ]
    )

    # TODO
    logger = logging.getLogger('ddd_site_parse')
    logger.addHandler(logging.NullHandler())

    return logger


def load_config():
    if len(sys.argv) > 1:
        Config.load(os.path.join(os.path.dirname(__file__), 'config'), sys.argv[1])
        return True

    return False


def init_saver_class(params):
    saver_name = Config.get('APP_SAVER_CLASS')

    if saver_name == 'csv':
        return DataSaverCSV(params)

    elif saver_name == 'json':
        return DataSaverJSON(params)

    raise Exception('Saver class not found')


def main():
    # load config
    if not load_config():
        print('Empty config?')
        exit(2)

    # create dirs if not exist
    fix_dirs(Config.get('APP_OUTPUT_DIR'), Config.get('APP_LOG_DIR'))

    # log
    logger = init_loggers()
    logger.info(' --- ')
    logger.info('Start app...')

    # output dirs init
    saver = init_saver_class({
        'output_dir': Config.get('APP_OUTPUT_DIR')
    })

    # output category for detect save mode
    # need for use after parse, but read before for prevent useless parse (if will errors)
    cat = Config.get('APP_OUTPUT_CAT', '')

    # parser loader
    loader = ModuleLoader('d_parser.{}'.format(Config.get('APP_PARSER')))

    # check version
    if not loader.check_version(CURRENT_VERSION):
        logger.fatal(f'Incompatible parser version ({CURRENT_VERSION} > {loader.version}). Update source and run script again')
        exit(3)

    # load spider script
    d_spider = loader.get('DSpider')

    # main
    try:
        # bot parser
        logger.info('Start...')
        threads_counter = int(Config.get('APP_THREAD_COUNT', '1'))
        bot = d_spider(thread_number=threads_counter, try_limit=int(Config.get('APP_TRY_LIMIT', '1')))
        bot.run()

        # post work
        if Config.get('APP_NEED_POST', ''):
            bot.d_post_work()

        # pass data
        saver.set_data(bot.result.data)

        # single file
        if not cat:
            saver.save(Config.get_seq('APP_SAVE_FIELDS'), {})

        # separate categories
        else:
            saver.save_by_category(Config.get_seq('APP_SAVE_FIELDS'), cat, {})

        logger.info(f'End with stats: \n{bot.get_stats()}')

    except Exception as exception:
        logger.fatal(f'!!! App crashed !!! ({type(exception).__name__}: {exception})\nTraceback: {traceback.format_exc()}')

    logger.info(f'{datetime.now():%Y/%m/%d %H:%M:%S} :: End...')


if __name__ == '__main__':
    main()
