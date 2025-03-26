# -*- coding: utf-8 -*-
import sys

from log import setup_logger
from collecter import CardDataCollecter
from db import GyazaiDB
from paths import DirPaths


def main():
    logger = setup_logger('collect_card_data.log')

    try:
        logger.info('Start collecting card data')
        # DBに接続
        with GyazaiDB.connect(host='mysql',
                              user='gyazai_user',
                              password='gyazai_user_password') as gyazai_db:
            # 全てのカード情報をデータベースに登録
            for i, card_data in enumerate(
              CardDataCollecter.collect_all_card_data()):
                gyazai_db.insert_card_data(card_data)
                logger.info('Insert row %d: %s (%s)',
                            i+1, card_data.eng_name, card_data.jan_name)
    except Exception as e:
        logger.exception(e)
        sys.exit(1)


if __name__ == '__main__':
    main()
