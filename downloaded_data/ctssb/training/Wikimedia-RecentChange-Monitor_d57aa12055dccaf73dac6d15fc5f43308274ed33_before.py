# -*- coding: utf-8 -*-
import configparser
import functools
import hashlib
import html
import ipaddress
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import requests

import pymysql
from bs4 import BeautifulSoup


class Monitor():
    def __init__(self):
        config = configparser.ConfigParser()
        configpath = os.path.dirname(
            os.path.realpath(__file__)) + '/config.ini'
        config.read_file(open(configpath, encoding="utf8"))
        self.token = config.get('telegram', 'token')
        self.chat_id = config.getint('telegram', 'default_chat_id')
        self.response_chat_id = json.loads(
            config.get('telegram', 'response_chat_id'))
        self.dbhost = config.get('database', 'host')
        self.dbuser = config.get('database', 'user')
        self.dbpasswd = config.get('database', 'passwd')
        self.dbdb = config.get('database', 'db')
        self.dbcharset = config.get('database', 'charset')
        self.dbretry = 5
        self.dbconnected = False
        self.db_connect()
        self.siteurl = config.get('site', 'url')
        self.defaultwiki = config.get('monitor', 'defaultwiki')
        self.wiki = config.get('monitor', 'defaultwiki')
        self.domain = config.get('monitor', 'defaultdomain')
        self.ipv4limit = 2 ** config.getint('monitor', 'ipv4limit')
        self.ipv6limit = 2 ** config.getint('monitor', 'ipv6limit')
        self.wp_api = config.get('wikipedia', 'api')
        self.wp_user = config.get('wikipedia', 'user')
        self.wp_pass = config.get('wikipedia', 'pass')
        self.wp_user_agent = config.get('wikipedia', 'user_agent')
        self.wp_ipcheck_token = config.get('wikipedia', 'ipcheck_token')
        self.abusefilter_watch_id = None
        self.abusefilter_watch_name = None
        self.abusefilter_blacklist_id = None
        self.abusefilter_blacklist_name = None
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.wp_user_agent})
        self.csrftoken = None

    def db_connect(self, noRaise=True):
        try:
            logging.info('Connecting to database.')
            self.db = pymysql.connect(host=self.dbhost,
                                      user=self.dbuser,
                                      passwd=self.dbpasswd,
                                      db=self.dbdb,
                                      charset=self.dbcharset)
            self.cur = self.db.cursor()
        except pymysql.err.OperationalError as e:
            logging.warning(e)
            self.dbconnected = False
            if not noRaise:
                raise e
        else:
            self.dbconnected = True

    def db_execute(self, query, args):
        if not self.dbconnected:
            self.db_connect(noRaise=False)
        for tryCnt in range(self.dbretry + 1):
            try:
                result = self.cur.execute(query, args)
                self.db.commit()
                return result
            except (pymysql.err.InterfaceError, pymysql.err.OperationalError) as e:
                if tryCnt == self.dbretry:
                    logging.warning('%s. Quitting.', e)
                    raise e
                logging.warning(
                    '%s. Wait %s seconds and try to reconnect database.', e, 2**tryCnt)
                time.sleep(2**tryCnt)
                self.db_connect()

    def db_fetchall(self):
        return self.cur.fetchall()

    def db_fetchone(self):
        return self.cur.fetchone()

    def change_wiki_and_domain(self, wiki, domain):
        self.wiki = wiki
        self.domain = domain
        self.wp_api = 'https://{}/w/api.php'.format(domain)

    def addRC_wiki(self, change):
        self.db_execute(
            """INSERT INTO `RC_wiki`
                (`wiki`, `server_name`)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE `server_name` = %s""",
            (change["wiki"], change["server_name"], change["server_name"]))

    def addRC_edit(self, change):
        self.db_execute(
            """INSERT INTO `RC_edit`
                (`bot`, `comment`, `id`,
                `length_new`, `length_old`,
                `minor`, `namespace`,
                `parsedcomment`, `revision_new`,
                `revision_old`, `timestamp`,
                `title`, `user`, `wiki`,
                `userhash`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %r, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s,
                        %s)""",
            (change["bot"], change["comment"], change["id"],
                change["length"]["new"], change["length"]["old"],
                change["minor"], change["namespace"],
                change["parsedcomment"], change["revision"]["new"],
                change["revision"]["old"], change["timestamp"],
                change["title"], change["user"], change["wiki"],
                self.user_type(change["user"]).userhash))

    def addRC_142(self, change):
        self.db_execute(
            """INSERT INTO `RC_142`
                (`bot`, `comment`, `id`,
                `namespace`, `parsedcomment`,
                `timestamp`, `title`,
                `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["namespace"], change["parsedcomment"],
                change["timestamp"], change["title"],
                change["user"], change["wiki"]))

    def addRC_new(self, change):
        self.db_execute(
            """INSERT INTO `RC_new`
                (`bot`, `comment`, `id`,
                `length_new`, `minor`,
                `namespace`, `parsedcomment`,
                `patrolled`, `revision_new`,
                `timestamp`, `title`,
                `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %r, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["length"]["new"], change["minor"],
                change["namespace"], change["parsedcomment"],
                change["patrolled"], change["revision"]["new"],
                change["timestamp"], change["title"],
                change["user"], change["wiki"]))

    def addRC_categorize(self, change):
        self.db_execute(
            """INSERT INTO `RC_categorize`
                (`bot`, `comment`, `id`,
                `namespace`, `parsedcomment`,
                `timestamp`, `title`,
                `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["namespace"], change["parsedcomment"],
                change["timestamp"], change["title"],
                change["user"], change["wiki"]))

    def addRC_log_move(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_move`
                (`bot`, `comment`, `id`,
                `log_action`, `log_action_comment`,
                `log_id`, `log_params_noredir`,
                `log_params_target`, `namespace`,
                `parsedcomment`, `timestamp`,
                `title`, `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["log_action"], change["log_action_comment"],
                change["log_id"], change["log_params"]["noredir"],
                change["log_params"]["target"], change["namespace"],
                change["parsedcomment"], change["timestamp"],
                change["title"], change["user"], change["wiki"]))

    def addRC_log_abusefilter_hit(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_abusefilter_hit`
                (`bot`, `log_action_comment`,
                `log_id`, `log_params_action`,
                `log_params_actions`,
                `log_params_filter`, `log_params_log`,
                `namespace`, `timestamp`,
                `title`, `user`, `wiki`)
                VALUES (%r, %s,
                        %s, %s,
                        %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s)""",
            (change["bot"], change["log_action_comment"],
                change["log_id"], change["log_params"]["action"],
                change["log_params"]["actions"],
                change["log_params"]["filter"], change["log_params"]["log"],
                change["namespace"], change["timestamp"],
                change["title"], change["user"], change["wiki"]))

    def addRC_log_abuselog(self, change):
        import dateutil.parser
        if change["global"]:
            filter_id = 'global-{}'.format(change["filter_id"])
        else:
            filter_id = str(change["filter_id"])
        if "revid" not in change or change["revid"] == "":
            revid = 0
        else:
            revid = change["revid"]
        timestamp = str(int(
            dateutil.parser.parse(change["timestamp"]).timestamp()))
        self.db_execute(
            """INSERT INTO `RC_log_abuselog`
                (`id`, `filter_id`, `filter`,
                `user`, `ns`,
                `revid`, `result`,
                `action`, `timestamp`,
                `title`, `wiki`)
                VALUES (%s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s)""",
            (change["id"], filter_id, change["filter"],
                change["user"], change["ns"],
                revid, change["result"],
                change["action"], timestamp,
                change["title"], self.wiki))

    def addRC_log_abusefilter_modify(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_abusefilter_modify`
                (`bot`, `log_action_comment`,
                `log_id`, `log_params_historyId`,
                `log_params_newId`, `namespace`,
                `timestamp`, `title`,
                `user`, `wiki`)
                VALUES (%r, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s)""",
            (change["bot"], change["log_action_comment"],
                change["log_id"], change["log_params"]["historyId"],
                change["log_params"]["newId"], change["namespace"],
                change["timestamp"], change["title"],
                change["user"], change["wiki"]))

    def addRC_log_newusers(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_newusers`
            (`bot`, `comment`, `id`,
                `log_action`, `log_action_comment`,
                `log_id`, `log_params_userid`,
                `namespace`, `parsedcomment`,
                `timestamp`, `title`,
                `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["log_action"], change["log_action_comment"],
                change["log_id"], change["log_params"]["userid"],
                change["namespace"], change["parsedcomment"],
                change["timestamp"], change["title"],
                change["user"], change["wiki"]))

    def addRC_log_block(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_block`
                (`bot`, `comment`, `id`,
                `log_action`, `log_action_comment`,
                `log_id`, `log_params_flags`,
                `log_params_duration`, `namespace`,
                `parsedcomment`, `timestamp`,
                `title`, `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["log_action"], change["log_action_comment"],
                change["log_id"], change["log_params"]["flags"],
                change["log_params"]["duration"], change["namespace"],
                change["parsedcomment"], change["timestamp"],
                change["title"], change["user"], change["wiki"]))

    def addRC_log_block_unblock(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_block`
            (`bot`, `comment`, `id`,
            `log_action`, `log_action_comment`,
            `log_id`, `log_params_flags`, `log_params_duration`, `namespace`,
            `parsedcomment`, `timestamp`,
            `title`, `user`, `wiki`)
            VALUES (%r, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["log_action"], change["log_action_comment"],
                change["log_id"], "", "", change["namespace"],
                change["parsedcomment"], change["timestamp"],
                change["title"], change["user"], change["wiki"]))

    def addRC_log_upload(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_upload`
                (`bot`, `comment`, `id`,
                `log_action`, `log_action_comment`,
                `log_id`, `log_params_img_timestamp`,
                `log_params_img_sha1`, `namespace`,
                `parsedcomment`, `timestamp`,
                `title`, `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["log_action"], change["log_action_comment"],
                change["log_id"], change["log_params"]["img_timestamp"],
                change["log_params"]["img_sha1"], change["namespace"],
                change["parsedcomment"], change["timestamp"],
                change["title"], change["user"], change["wiki"]))

    def addRC_log_protect(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_protect`
                (`bot`, `comment`, `id`,
                `log_action`, `log_action_comment`,
                `log_id`,
                `log_params_details`,
                `log_params_description`,
                `log_params_cascade`, `namespace`,
                `parsedcomment`, `timestamp`,
                `title`, `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s,
                        %s,
                        %s,
                        %r, %s,
                        %s, %s,
                        %s, %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["log_action"], change["log_action_comment"],
                change["log_id"],
                json.dumps(change["log_params"]["details"]),
                change["log_params"]["description"],
                change["log_params"]["cascade"], change["namespace"],
                change["parsedcomment"], change["timestamp"],
                change["title"], change["user"], change["wiki"]))

    def addRC_log_protect_unprotect(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_protect_unprotect`
                (`bot`, `comment`, `id`,
                `log_action`, `log_action_comment`,
                `log_id`, `namespace`,
                `parsedcomment`, `timestamp`,
                `title`, `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %r, %s,
                        %s, %s,
                        %s, %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["log_action"], change["log_action_comment"],
                change["log_id"], change["namespace"],
                change["parsedcomment"], change["timestamp"],
                change["title"], change["user"], change["wiki"]))

    def addRC_log_protect_move_prot(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_protect_move_prot`
                (`bot`, `comment`, `id`,
                `log_action`, `log_action_comment`,
                `log_id`, `log_params_oldtitle`,
                `namespace`, `parsedcomment`,
                `timestamp`, `title`,
                `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %r,
                        %s, %s,
                        %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["log_action"], change["log_action_comment"],
                change["log_id"], change["log_params"]["oldtitle"],
                change["namespace"], change["parsedcomment"],
                change["timestamp"], change["title"],
                change["user"], change["wiki"]))

    def addRC_log_renameuser(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_renameuser`
                (`bot`, `comment`, `id`,
                `log_action`, `log_action_comment`,
                `log_id`, `log_params_olduser`,
                `log_params_newuser`,
                `log_params_edits`, `namespace`,
                `parsedcomment`, `timestamp`,
                `title`, `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["log_action"], change["log_action_comment"],
                change["log_id"], change["log_params"]["olduser"],
                change["log_params"]["newuser"],
                change["log_params"]["edits"], change["namespace"],
                change["parsedcomment"], change["timestamp"],
                change["title"], change["user"], change["wiki"]))

    def addRC_log_merge(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_merge`
                (`bot`, `comment`, `id`,
                `log_action`, `log_action_comment`,
                `log_id`, `log_params_dest`,
                `log_params_mergepoint`, `namespace`,
                `parsedcomment`, `timestamp`,
                `title`, `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["log_action"], change["log_action_comment"],
                change["log_id"], change["log_params"]["dest"],
                change["log_params"]["mergepoint"], change["namespace"],
                change["parsedcomment"], change["timestamp"],
                change["title"], change["user"], change["wiki"]))

    def addRC_log_rights(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_rights`
                (`bot`, `comment`, `id`,
                `log_action`, `log_action_comment`,
                `log_id`,
                `log_params_newgroups`,
                `log_params_oldgroups`,
                `log_params_newmetadata`,
                `log_params_oldmetadata`,
                `namespace`, `parsedcomment`,
                `timestamp`, `title`,
                `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s, %s,
                        %s, %s,
                        %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["log_action"], change["log_action_comment"],
                change["log_id"],
                json.dumps(change["log_params"]["newgroups"]),
                json.dumps(change["log_params"]["oldgroups"]),
                json.dumps(change["log_params"]["newmetadata"]),
                json.dumps(change["log_params"]["oldmetadata"]),
                change["namespace"], change["parsedcomment"],
                change["timestamp"], change["title"],
                change["user"], change["wiki"]))

    def addRC_log_patrol(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_patrol`
                (`bot`, `log_action`,
                `log_action_comment`, `log_id`,
                `log_params_auto`, `log_params_previd`,
                `log_params_curid`, `namespace`,
                `timestamp`, `title`,
                `user`, `wiki`)
                VALUES (%r, %s,
                        %s, %s,
                        %r, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s)""",
            (change["bot"], change["log_action"],
                change["log_action_comment"], change["log_id"],
                change["log_params"]["auto"], change["log_params"]["previd"],
                change["log_params"]["curid"], change["namespace"],
                change["timestamp"], change["title"],
                change["user"], change["wiki"]))

    def addRC_log_thanks(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_thanks`
                (`bot`, `log_action`,
                `log_action_comment`, `log_id`,
                `namespace`, `timestamp`,
                `title`, `user`, `wiki`)
                VALUES (%r, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s)""",
            (change["bot"], change["log_action"],
                change["log_action_comment"], change["log_id"],
                change["namespace"], change["timestamp"],
                change["title"], change["user"], change["wiki"]))

    def addRC_log_delete(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_delete`
                (`bot`, `comment`, `id`,
                `log_action`, `log_action_comment`,
                `log_id`, `namespace`,
                `parsedcomment`, `timestamp`,
                `title`, `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["log_action"], change["log_action_comment"],
                change["log_id"], change["namespace"],
                change["parsedcomment"], change["timestamp"],
                change["title"], change["user"], change["wiki"]))

    def addRC_log_delete_restore(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_delete_restore`
                (`bot`, `comment`, `id`,
                `log_action_comment`, `log_id`,
                `log_params_count_files`,
                `log_params_count_revisions`,
                `namespace`, `parsedcomment`,
                `timestamp`, `title`,
                `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s,
                        %s,
                        %s, %s,
                        %s, %s,
                        %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["log_action_comment"], change["log_id"],
                change["log_params"]["count"]["files"],
                change["log_params"]["count"]["revisions"],
                change["namespace"], change["parsedcomment"],
                change["timestamp"], change["title"],
                change["user"], change["wiki"]))

    def addRC_log_delete_revision(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_delete_revision`
                (`bot`, `comment`, `id`,
                `log_action_comment`, `log_id`,
                `log_params_ids`,
                `log_params_type`, `log_params_nfield`,
                `log_params_ofield`, `namespace`,
                `parsedcomment`, `timestamp`,
                `title`, `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["log_action_comment"], change["log_id"],
                json.dumps(change["log_params"]["ids"]),
                change["log_params"]["type"], change["log_params"]["nfield"],
                change["log_params"]["ofield"], change["namespace"],
                change["parsedcomment"], change["timestamp"],
                change["title"], change["user"], change["wiki"]))

    def addRC_log_globalauth(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_globalauth`
                (`bot`, `comment`, `id`,
                `log_action`, `log_action_comment`,
                `log_id`, `log_params`,
                `namespace`, `parsedcomment`,
                `timestamp`, `title`,
                `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s)""",
            (change["bot"], change["comment"], change["id"],
                change["log_action"], change["log_action_comment"],
                change["log_id"], json.dumps(change["log_params"]),
                change["namespace"], change["parsedcomment"],
                change["timestamp"], change["title"],
                change["user"], change["wiki"]))

    def addRC_log_gblblock(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_gblblock`
                (`bot`, `comment`, `id`,
                `log_action`, `log_action_comment`,
                `log_id`, `log_params`,
                `namespace`, `parsedcomment`,
                `timestamp`, `title`,
                `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s)""",
            (change["bot"], change["comment"], change["id"],
             change["log_action"], change["log_action_comment"],
             change["log_id"], json.dumps(change["log_params"]),
             change["namespace"], change["parsedcomment"],
             change["timestamp"], change["title"],
             change["user"], change["wiki"]))

    def addRC_log_gblrename(self, change):
        self.db_execute(
            """INSERT INTO `RC_log_gblrename`
                (`bot`, `comment`, `id`,
                `log_action`, `log_action_comment`,
                `log_id`, `log_params_movepages`,
                `log_params_suppressredirects`,
                `log_params_olduser`,
                `log_params_newuser`, `namespace`,
                `parsedcomment`, `timestamp`, `title`,
                `user`, `wiki`)
                VALUES (%r, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s,
                        %s,
                        %s, %s,
                        %s, %s, %s,
                        %s, %s)""",
            (change["bot"], change["comment"], change["id"],
             change["log_action"], change["log_action_comment"],
             change["log_id"], change["log_params"]["movepages"],
             change["log_params"]["suppressredirects"],
             change["log_params"]["olduser"],
             change["log_params"]["newuser"], change["namespace"],
             change["parsedcomment"], change["timestamp"], change["title"],
             change["user"], change["wiki"]))

    def getuser_score(self, userobj):
        userhash = userobj.userhash
        self.db_execute(
            """SELECT `point` FROM `user_score`
               WHERE `userhash` = %s""",
            (userhash)
        )
        rows = self.db_fetchall()
        if len(rows) == 0:
            res = 0
        else:
            res = rows[0][0]
        return res

    def adduser_score(self, userobj, point):
        if point == 0:
            return
        oldpoint = self.getuser_score(userobj)
        timestamp = int(time.time())
        userhash = userobj.userhash
        self.db_execute(
            """INSERT INTO `user_score`
            (`userhash`, `point`, `timestamp`) VALUES (%s, %s, %s)
            ON DUPLICATE KEY
            UPDATE `point` = `point` + %s, `timestamp` = %s""",
            (userhash, point, timestamp, point, timestamp)
        )

        newpoint = self.getuser_score(userobj)
        if oldpoint > 0 and newpoint <= 0:  # pylint: disable=R1716
            self.sendmessage("{}的分數小於等於0，已停止監視".format(
                self.link_user(userobj.val)))

    def addblack_user(self, user, timestamp, reason, wiki=None, msgprefix=""):
        if wiki is None:
            wiki = self.wiki
        user = self.normalize_user(user)
        wiki = self.normalize_wiki(wiki)

        userobj = self.user_type(user)
        if isinstance(userobj, User):  # pylint: disable=R1705
            self.db_execute(
                """INSERT INTO `black_user`
                   (`wiki`, `user`, `timestamp`, `reason`, `userhash`)
                   VALUES (%s, %s, %s, %s, %s)""",
                (wiki, userobj.user, str(timestamp), reason, userobj.userhash)
            )

            message = "{}加入User:{}@{}至黑名單\n原因：{}".format(
                msgprefix,
                self.link_user(userobj.user, wiki),
                wiki,
                self.parse_wikicode(reason)
            )
            self.sendmessage(message, userobj.user + "|" + wiki)
            return message
        elif isinstance(userobj, IPv4):
            if int(userobj.end) - int(userobj.start) > self.ipv4limit:
                message = "IP數量超過上限"
                self.sendmessage(message)
                return message
            self.db_execute(
                """INSERT INTO `black_ipv4`
                   (`wiki`, `val`, `start`, `end`, `timestamp`, `reason`, `userhash`)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (wiki, userobj.val, int(userobj.start), int(userobj.end),
                    str(timestamp), reason, userobj.userhash)
            )

        elif isinstance(userobj, IPv6):
            if int(userobj.end) - int(userobj.start) > self.ipv6limit:
                message = "IP數量超過上限"
                self.sendmessage(message)
                return message
            self.db_execute(
                """INSERT INTO `black_ipv6`
                   (`wiki`, `val`, `start`, `end`, `timestamp`, `reason`, `userhash`)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (wiki, userobj.val, int(userobj.start), int(userobj.end),
                    str(timestamp), reason, userobj.userhash)
            )

        else:
            message = "cannot detect user type: " + user
            self.error(message)
            return message
        if isinstance(userobj, (IPv4, IPv6)):
            if userobj.start == userobj.end:  # pylint: disable=R1705
                message = "{}加入IP:{}@{}至黑名單\n原因：{}".format(
                    msgprefix,
                    self.link_user(str(userobj.val), wiki),
                    wiki,
                    self.parse_wikicode(reason)
                )
                self.sendmessage(message, userobj.val + "|" + wiki)
                return message
            elif userobj.type == "CIDR":
                message = "{}加入IP:{}@{}至黑名單\n原因：{}".format(
                    msgprefix,
                    self.link_user(userobj.val, wiki),
                    wiki,
                    self.parse_wikicode(reason)
                )
                self.sendmessage(message, userobj.val + "|" + wiki)
                return message
            elif userobj.type == "range":
                message = "{}加入IP:{}-{}@{}至黑名單\n原因：{}".format(
                    msgprefix,
                    userobj.start,
                    userobj.end,
                    wiki,
                    self.parse_wikicode(reason)
                )
                self.sendmessage(message, userobj.val + "|" + wiki)
                return message
        return None

    def getblackuser(self, user, wiki=None, prefix=True):
        if wiki is None:
            wiki = self.wiki
        user = self.normalize_user(user)
        wiki = self.normalize_wiki(wiki)

        message = ""
        rows = self.check_user_blacklist(user, wiki)
        if len(rows) != 0:
            if prefix:
                message += "於黑名單："
            for record in rows:
                message += "\n" + self.parse_wikicode(record[0])
                if record[2] != "":
                    message += "(" + record[2] + "@" + record[3] + ")"
                else:
                    message += "(" + record[3] + ")"
                message += ', ' + self.formattimediff(record[1])

        return message.strip()

    def checkuser(self, user, wiki=None):
        if wiki is None:
            wiki = self.wiki
        user = self.normalize_user(user)
        wiki = self.normalize_wiki(wiki)

        message = (self.getblackuser(user, wiki)).strip()

        userobj = self.user_type(user)
        point = self.getuser_score(userobj)
        if message != "":  # pylint: disable=R1705
            return "{}@{}，{}p\n{}".format(user, wiki, point, message)
        else:
            return "{}@{}：查無結果".format(user, wiki)

    def delblack_user(self, user, wiki=None, msgprefix=""):
        if wiki is None:
            wiki = self.wiki
        user = self.normalize_user(user)
        wiki = self.normalize_wiki(wiki)

        blacklist = self.getblackuser(user, wiki, prefix=False)
        userobj = self.user_type(user)
        if isinstance(userobj, User):  # pylint: disable=R1705
            count = self.db_execute(
                """DELETE FROM `black_user`
                   WHERE `user` = %s AND `wiki` = %s""",
                (userobj.user, wiki))

            message = "{}{}條對於User:{}({})的紀錄從黑名單刪除\n{}".format(
                msgprefix,
                count,
                self.link_user(userobj.user, wiki),
                wiki,
                blacklist
            )
            self.sendmessage(message)
            return message
        elif isinstance(userobj, IPv4):
            count = self.db_execute(
                """DELETE FROM `black_ipv4`
                   WHERE `start` = %s AND `end` = %s AND `wiki` = %s""",
                (int(userobj.start), int(userobj.end), wiki))

        elif isinstance(userobj, IPv6):
            count = self.db_execute(
                """DELETE FROM `black_ipv6`
                   WHERE `start` = %s AND `end` = %s AND `wiki` = %s""",
                (int(userobj.start), int(userobj.end), wiki))

        else:
            message = "cannot detect user type: " + user
            self.error(message)
            return message
        if isinstance(userobj, (IPv4, IPv6)):
            if userobj.start == userobj.end:
                message = "{}{}條對於IP:{}@{}的紀錄從黑名單刪除\n{}".format(
                    msgprefix,
                    count,
                    self.link_user(str(userobj.start), wiki),
                    wiki,
                    blacklist
                )
                self.sendmessage(message)
            elif userobj.type == "CIDR":
                message = "{}{}條對於IP:{}@{}的紀錄從黑名單刪除\n{}".format(
                    msgprefix,
                    count,
                    self.link_user(userobj.val, wiki),
                    wiki,
                    blacklist
                )
                self.sendmessage(message)
            elif userobj.type == "range":
                message = "{}{}條對於IP:{}-{}@{}的紀錄從黑名單刪除\n{}".format(
                    msgprefix,
                    count,
                    userobj.start,
                    userobj.end,
                    wiki,
                    blacklist
                )
                self.sendmessage(message)
            return message
        return None

    def setwikiblack_user(self, user, wiki=None):
        if wiki is None:
            wiki = self.wiki
        user = self.normalize_user(user)
        wiki = self.normalize_wiki(wiki)

        userobj = self.user_type(user)
        if isinstance(userobj, User):  # pylint: disable=R1705
            count = self.db_execute(
                """UPDATE `black_user` SET `wiki` = %s
                   WHERE `user` = %s""",
                (wiki, userobj.user))

            self.sendmessage("{}條對於User:{}的紀錄設定wiki為{}".format(
                count, self.link_user(userobj.user, wiki), wiki))
            return
        elif isinstance(userobj, IPv4):
            count = self.db_execute(
                """UPDATE `black_ipv4` SET `wiki` = %s
                   WHERE `start` = %s AND `end` = %s""",
                (wiki, int(userobj.start), int(userobj.end)))

        elif isinstance(userobj, IPv6):
            count = self.db_execute(
                """UPDATE `black_ipv6` SET `wiki` = %s
                   WHERE `start` = %s AND `end` = %s""",
                (wiki, int(userobj.start), int(userobj.end)))

        else:
            self.error("cannot detect user type: " + user)
            return
        if isinstance(userobj, (IPv4, IPv6)):
            if userobj.start == userobj.end:
                self.sendmessage("{}條對於IP:{}的紀錄設定wiki為{}".format(
                    count,
                    self.link_user(str(userobj.start), wiki),
                    wiki
                ))
            elif userobj.type == "CIDR":
                self.sendmessage(
                    "{}條對於IP:{}的紀錄設定wiki為{}".format(
                        count, self.link_user(userobj.val, wiki), wiki))
            elif userobj.type == "range":
                self.sendmessage(
                    "{}條對於IP:{}-{}的紀錄設定wiki為{}".format(
                        count, userobj.start, userobj.end, wiki))

    def check_user_blacklist(self, user, wiki=None):
        if wiki is None:
            wiki = self.wiki
        user = self.normalize_user(user)
        wiki = self.normalize_wiki(wiki)

        userobj = self.user_type(user)
        if isinstance(userobj, User):  # pylint: disable=R1705
            self.db_execute(
                """SELECT `reason`, `black_user`.`timestamp`, '' AS `val`, `wiki`, `point`
                   FROM `black_user`
                   LEFT JOIN `user_score`
                   ON `black_user`.`userhash` = `user_score`.`userhash`
                   WHERE `user` = %s
                   AND (`wiki` = %s OR `wiki` = 'global')
                   AND `point` > 0
                   ORDER BY `black_user`.`timestamp` DESC""",
                (user, wiki))
            return self.db_fetchall()
        elif isinstance(userobj, IPv4):
            self.db_execute(
                """SELECT `reason`, `black_ipv4`.`timestamp`, `val`, `wiki`, `point`
                   FROM `black_ipv4`
                   LEFT JOIN `user_score`
                   ON `black_ipv4`.`userhash` = `user_score`.`userhash`
                   WHERE `start` <= %s AND `end` >= %s
                   AND (`wiki` = %s OR `wiki` = 'global')
                   AND `point` > 0
                   ORDER BY `black_ipv4`.`timestamp` DESC""",
                (int(userobj.start), int(userobj.end), wiki))
            return self.db_fetchall()
        elif isinstance(userobj, IPv6):
            self.db_execute(
                """SELECT `reason`, `black_ipv6`.`timestamp`, `val`, `wiki`, `point`
                   FROM `black_ipv6`
                   LEFT JOIN `user_score`
                   ON `black_ipv6`.`userhash` = `user_score`.`userhash`
                   WHERE `start` <= %s AND  `end` >= %s
                   AND (`wiki` = %s OR `wiki` = 'global')
                   AND `point` > 0
                   ORDER BY `black_ipv6`.`timestamp` DESC""",
                (int(userobj.start), int(userobj.end), wiki))
            return self.db_fetchall()
        else:
            self.error("cannot detect user type: " + user)
            return []

    def check_user_blacklist_with_reason(self, user, reason, wiki=None):
        if wiki is None:
            wiki = self.wiki
        user = self.normalize_user(user)

        userobj = self.user_type(user)
        if isinstance(userobj, User):  # pylint: disable=R1705
            self.db_execute(
                """SELECT `reason`, `black_user`.`timestamp`, `user`, `point`
                   FROM `black_user`
                   LEFT JOIN `user_score`
                   ON `black_user`.`userhash` = `user_score`.`userhash`
                   WHERE `user` = %s AND `reason` = %s
                   AND (`wiki` = %s OR `wiki` = 'global')
                   AND `point` > 0
                   ORDER BY `black_user`.`timestamp` DESC""",
                (user, reason, wiki))
            return self.db_fetchall()
        elif isinstance(userobj, IPv4):
            self.db_execute(
                """SELECT `reason`, `black_ipv4`.`timestamp`, `val`, `point`
                   FROM `black_ipv4`
                   LEFT JOIN `user_score`
                   ON `black_ipv4`.`userhash` = `user_score`.`userhash`
                   WHERE `start` <= %s AND  `end` >= %s
                   AND `reason` = %s AND (`wiki` = %s OR `wiki` = 'global')
                   AND `point` > 0
                   ORDER BY `black_ipv4`.`timestamp` DESC""",
                (int(userobj.start), int(userobj.end), reason, wiki))
            return self.db_fetchall()
        elif isinstance(userobj, IPv6):
            self.db_execute(
                """SELECT `reason`, `black_ipv6`.`timestamp`, `val`, `point`
                   FROM `black_ipv6`
                   LEFT JOIN `user_score`
                   ON `black_ipv6`.`userhash` = `user_score`.`userhash`
                   WHERE `start` <= %s AND  `end` >= %s
                   AND `reason` = %s AND (`wiki` = %s OR `wiki` = 'global')
                   AND `point` > 0
                   ORDER BY `black_ipv6`.`timestamp` DESC""",
                (int(userobj.start), int(userobj.end), reason, wiki))
            return self.db_fetchall()
        else:
            self.error("cannot detect user type: " + user)
            return []

    def getpage_hash(self, page, wiki=None):
        if wiki is None:
            wiki = self.wiki
        page = self.normalize_page(page)
        wiki = self.normalize_wiki(wiki)

        pagehash = int(hashlib.sha1(
            str('{0}|{1}'.format(page, wiki))
            .encode("utf8")).hexdigest(), 16) % (2 ** 64) - 2 ** 63

        return pagehash

    def getpage_score(self, page, wiki=None):
        if wiki is None:
            wiki = self.wiki
        page = self.normalize_page(page)
        wiki = self.normalize_wiki(wiki)

        pagehash = self.getpage_hash(page, wiki)
        self.db_execute(
            """SELECT `point` FROM `black_page`
               WHERE `pagehash` = %s""",
            (pagehash)
        )
        rows = self.db_fetchall()
        if len(rows) == 0:
            res = 0
        else:
            res = rows[0][0]
        return res

    def addpage_score(self, page, wiki=None, point=30):
        if point == 0:
            return

        if wiki is None:
            wiki = self.wiki
        page = self.normalize_page(page)
        wiki = self.normalize_wiki(wiki)

        oldpoint = self.getpage_score(page, wiki)

        pagehash = self.getpage_hash(page, wiki)
        self.db_execute(
            """UPDATE `black_page`
            SET `point` = `point` + %s
            WHERE `pagehash` = %s""",
            (point, pagehash)
        )

        newpoint = self.getpage_score(page, wiki)
        if oldpoint > 0 and newpoint <= 0:  # pylint: disable=R1716
            self.sendmessage("{}的分數小於等於0，已停止監視".format(
                self.link_page(page, wiki)))

    def addblack_page(self, page, timestamp, reason, point=30, wiki=None, msgprefix=""):
        if wiki is None:
            wiki = self.wiki

        page = self.normalize_page(page)

        pagehash = self.getpage_hash(page, wiki)
        self.db_execute(
            """INSERT INTO `black_page`
               (`pagehash`, `wiki`, `page`, `timestamp`, `reason`, `point`)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY
               UPDATE `point` = `point` + %s, `timestamp` = %s, `reason` = %s""",
            (pagehash, wiki, page, timestamp, reason, point, point, timestamp, reason))

        message = "{}加入{}({})至監視頁面\n原因：{}".format(
            msgprefix,
            self.link_page(page, wiki), wiki, self.parse_wikicode(reason)
        )
        self.sendmessage(message, page=page + "|" + wiki)
        return message

    def delblack_page(self, page, wiki=None, msgprefix=""):
        if wiki is None:
            wiki = self.wiki
        page = self.normalize_page(page)
        wiki = self.normalize_wiki(wiki)

        pagehash = self.getpage_hash(page, wiki)
        count = self.db_execute(
            """DELETE FROM `black_page` WHERE `pagehash` = %s""",
            (pagehash))

        message = "{}{}條對於{}({})從監視頁面刪除".format(
            msgprefix,
            count,
            self.link_page(page, wiki),
            wiki
        )
        self.sendmessage(message, page=page + "|" + wiki)
        return message

    def check_page_blacklist(self, page, wiki=None):
        if wiki is None:
            wiki = self.wiki
        page = self.normalize_page(page)
        wiki = self.normalize_wiki(wiki)

        pagehash = self.getpage_hash(page, wiki)
        timestamp = int(time.time())
        self.db_execute("""SELECT `reason`, `timestamp`, `point` FROM `black_page`
                            WHERE `pagehash` = %s AND `timestamp` < %s
                            ORDER BY `timestamp` DESC""",
                        (pagehash, timestamp))
        return self.db_fetchall()

    def link_all(self, page, text=None, wiki=None):
        page = re.sub(r'^:', '', page)
        if text is None:
            text = page
        if wiki is not None and wiki != self.wiki:
            return page
        return ('<a href="https://{}/wiki/{}">{}</a>'
                .format(self.domain, urllib.parse.quote(page), text))

    def link_user(self, user, wiki=None):
        if wiki is not None and wiki != self.wiki:
            return user
        return ('<a href="https://{}/wiki/Special:Contributions/{}">{}</a>'
                .format(self.domain, urllib.parse.quote(user), user))

    def link_page(self, title, wiki=None):
        if wiki is not None and wiki != self.wiki:
            return title
        return ('<a href="https://{}/wiki/{}">{}</a>'
                .format(self.domain, urllib.parse.quote(title), title))

    def link_diff(self, diffid):
        return ('<a href="https://{}/wiki/Special:Diff/{}">差異</a>'
                .format(self.domain, diffid))

    def link_abusefilter(self, afid):
        if afid == "":
            return "過濾器"
        return ('<a href="https://{0}/wiki/Special:Abusefilter/{1}">過濾器{1}</a>'
                .format(self.domain, afid))

    def link_abuselog(self, logid):
        return ('<a href="https://{}/wiki/Special:Abuselog/{}">詳情</a>'
                .format(self.domain, logid))

    def sendmessage(self, message, user=None, page=None, nolog=False, chat_id=None, token=None):
        if len(message) == 0:
            self.error('try to send empty message')
            return
        if chat_id is None:
            chat_id = self.chat_id
        if token is None:
            token = self.token
        elif token != self.token:
            nolog = True
        try:
            if not nolog:
                self.log(message, logtype='Monitor/sendmessage')
            url = ("https://api.telegram.org/bot{}/sendMessage" +
                   "?chat_id={}&parse_mode=HTML&disable_web_page_preview=1"
                   + "&text={}"
                   ).format(token,
                            chat_id,
                            urllib.parse.quote_plus(message.encode()))
            res = urllib.request.urlopen(url).read().decode("utf8")
            res = json.loads(res)
            if res["ok"]:
                if not nolog and (user is not None or page is not None):
                    self.bot_message(
                        res["result"]["message_id"], user, page, message)
            else:
                self.error("send message error:\n{}".format(json.dumps(res)))
        except urllib.error.HTTPError as e:
            self.error("send message error:{}\n{}\nmessage:{}".format(
                e.code, e.read().decode("utf-8"), message))

    def editmessage(self, message_id, message, chat_id=None, token=None):
        if len(message) == 0:
            self.error('try to send empty message')
            return
        if chat_id is None:
            chat_id = self.chat_id
        if token is None:
            token = self.token
        try:
            url = ("https://api.telegram.org/bot{}/editMessageText" +
                   "?chat_id={}&message_id={}&parse_mode=HTML&disable_web_page_preview=1"
                   + "&text={}"
                   ).format(token,
                            chat_id,
                            message_id,
                            urllib.parse.quote_plus(message.encode()))
            res = urllib.request.urlopen(url).read().decode("utf8")
            res = json.loads(res)
            if res["ok"]:
                pass
            else:
                self.error("edit message error:\n{}".format(json.dumps(res)))
        except urllib.error.HTTPError as e:
            self.error("edit message error:{}\n{}\nmessage:{}".format(
                e.code, e.read().decode("utf-8"), message))

    def deletemessage(self, message_id):
        try:
            url = ("https://api.telegram.org/bot{}/deleteMessage"
                   + "?chat_id={}&message_id={}"
                   ).format(self.token,
                            self.chat_id,
                            message_id)
            urllib.request.urlopen(url)
            self.log(message_id, logtype="delete")
            self.db_execute("""DELETE FROM `bot_message`
                                WHERE `message_id` = %s""", (message_id))

        except urllib.error.HTTPError as e:
            datastr = e.read().decode("utf8")
            data = json.loads(datastr)
            if (data["description"]
                    == "Bad Request: message to delete not found"):
                self.db_execute("""DELETE FROM `bot_message`
                                    WHERE `message_id` = %s""", (message_id))

            else:
                self.log("delete message error:" + str(e.code) + " "
                         + str(e.read().decode("utf-8")) + " message_id: "
                         + str(message_id))

    def bot_message(self, message_id, user, page, message):
        if user is None:
            user = ""
        if page is None:
            page = ""
        timestamp = int(time.time())
        self.db_execute(
            """INSERT INTO `bot_message`
               (`timestamp`, `message_id`, `user`, `page`, `message`)
               VALUES (%s, %s, %s, %s, %s)""",
            (timestamp, message_id, user, page, message)
        )

    def get_user_from_message_id(self, message_id):
        self.db_execute("""SELECT `user` FROM `bot_message`
                            WHERE `message_id` = %s""",
                        (message_id))
        return self.db_fetchall()

    def get_page_from_message_id(self, message_id):
        self.db_execute("""SELECT `page` FROM `bot_message`
                            WHERE `message_id` = %s""",
                        (message_id))
        return self.db_fetchall()

    def log(self, log, timestamp=None, logtype=""):
        if timestamp is None:
            timestamp = int(time.time())
        self.db_execute("""INSERT INTO `log` (`timestamp`, `type`, `log`)
                            VALUES (%s, %s, %s)""",
                        (timestamp, str(logtype), str(log)))

    def error(self, error, timestamp=None, noRaise=False):
        if timestamp is None:
            timestamp = int(time.time())
        try:
            self.db_execute("""INSERT INTO `error` (`timestamp`, `error`)
                                VALUES (%s, %s)""",
                            (timestamp, str(error)))

        except Exception as e:
            logging.warning('Failed to log error (%s)', e)
            if not noRaise:
                raise e

    def formattimediff(self, timestamp, basetime=None):
        if basetime is None:
            basetime = int(time.time())
        diff = abs(int(timestamp) - basetime)
        res = ""
        if diff < 60:
            res = str(diff) + "秒"
        elif diff < 60 * 60:
            res = str(int(diff / 60)) + "分"
        elif diff < 60 * 60 * 24:
            res = str(int(diff / 60 / 60)) + "小時"
        else:
            res = str(int(diff / 60 / 60 / 24)) + "日"
        if timestamp > basetime:
            res += "後"
        else:
            res += "前"
        return res

    def normalize_wiki(self, wiki):
        wiki = wiki.strip()
        return wiki

    def normalize_user(self, user):
        user = user.strip()
        user = re.sub(r'^User:', '', user, flags=re.I)
        if len(user) == 0:
            return ''
        user = user.replace('_', ' ')
        user = user[0].upper() + user[1:]
        return user

    def normalize_page(self, page):
        page = page.strip()
        if len(page) == 0:
            return ''
        page = page.replace('_', ' ')
        page = page[0].upper() + page[1:]
        return page

    def parse_user(self, user, delimiter="|"):
        user = self.normalize_user(user)
        if delimiter in user:
            wiki = user.split(delimiter)[1]
            user = user.split(delimiter)[0]
        else:
            wiki = self.wiki
        if len(user) == 0:
            return "", wiki
        user = self.normalize_user(user)
        return user, wiki

    def parse_page(self, page, delimiter="|"):
        if delimiter in page:
            wiki = page.split(delimiter)[1]
            page = page.split(delimiter)[0]
        else:
            wiki = self.wiki
        page = self.normalize_page(page)
        return page, wiki

    def parse_reason(self, reason):
        if reason is None or reason.strip() == "":
            return "無原因"
        return reason

    def parse_wikicode(self, code):
        code = html.escape(code, quote=False)

        def rep_template(m):
            text = m.group(1)
            page = "Template:" + m.group(1)
            parms = ""
            if len(m.groups()) == 2 and m.group(2) is not None:
                parms = m.group(2)
            return "{{" + self.link_all(page, text) + parms + "}}"
        code = re.sub(r"{{([^\|}\[\]]+)(\|[^}]+)?}}", rep_template, code)

        def rep_link(m):
            page = m.group(1)
            if len(m.groups()) == 2:  # pylint: disable=R1705
                text = m.group(2)
                return self.link_all(page, text)
            else:
                return self.link_all(page)
        code = re.sub(r"\[\[([^\]\|]+)(?:\|([^\]]+))?\]\]", rep_link, code)

        return code

    def user_type(self, user):
        try:
            user = self.normalize_user(user)
            m = re.match(r"(.+)\-(.+)", user)
            if m is not None:
                ip1 = ipaddress.ip_address(m.group(1))
                ip2 = ipaddress.ip_address(m.group(2))
                if ip1 > ip2:
                    ip1, ip2 = ip2, ip1
                if isinstance(ip1, type(ip2)):
                    if isinstance(ip1, ipaddress.IPv4Address):  # pylint: disable=R1705
                        return IPv4(ip1, ip2, "range", user)
                    elif isinstance(ip1, ipaddress.IPv6Address):
                        return IPv6(ip1, ip2, "range", user)
                self.error("cannot detect user type: " + user)
                raise ValueError
            network = ipaddress.ip_network(user, strict=False)
            if isinstance(network, ipaddress.IPv4Network):  # pylint: disable=R1705
                if network[0] == network[-1]:  # pylint: disable=R1705
                    return IPv4(network[0], network[-1], "CIDR", network[0])
                else:
                    return IPv4(network[0], network[-1], "CIDR", network)
            elif isinstance(network, ipaddress.IPv6Network):
                if network[0] == network[-1]:  # pylint: disable=R1705
                    return IPv6(network[0], network[-1], "CIDR", network[0])
                else:
                    return IPv6(network[0], network[-1], "CIDR", network)
            else:
                self.error("cannot detect user type: " + user)
                raise ValueError
        except ValueError as e:
            return User(user)
        except Exception as e:
            exc_type, _, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            self.error(str(e))
            self.error(str(exc_type) + " " + str(fname)
                       + " " + str(exc_tb.tb_lineno))
            return None

    @functools.lru_cache()
    def get_proxy_info(self, ip):
        url = 'https://tools.wmflabs.org/ipcheck/index.php?ip={}&api=true&key={}'.format(ip, self.wp_ipcheck_token)
        jsonstr = urllib.request.urlopen(url).read().decode("utf8")
        try:
            res = json.loads(jsonstr)
        except json.decoder.JSONDecodeError as e:
            self.error('M.get_proxy_info JSONDecodeError: {} content: {} url: {}'.format(e, jsonstr, url))
            res = {}
        return res

    def get_proxy_score(self, ip):
        info = self.get_proxy_info(ip)
        score = 0
        if 'proxycheck' in info:
            if info['proxycheck']['result']['proxy']:
                score += 1
        if 'getIPIntel' in info:
            if float(info['getIPIntel']['result']['chance']) > 50:
                score += 1
        if 'ipQualityScore' in info:
            if info['ipQualityScore']['result']['proxy'] or info['ipQualityScore']['result']['vpn']:
                score += 1
        if 'ipHub' in info:
            if info['ipHub']['result']['block']:
                score += 1
        if 'teohio' in info and 'result' in info['teohio']:
            if info['teohio']['result']['hosting'] or info['teohio']['result']['vpnOrProxy']:
                score += 1
        if 'ipHunter' in info:
            if info['ipHunter']['result']['block']:
                score += 1
        if 'noFraud' in info and 'result' in info['noFraud']:
            if float(info['noFraud']['result']['chance']) > 50:
                score += 1
        return score

    def get_diff(self, fromrev, torev=None, torelative=None):
        result = {
            'removed_lines': [],
            'added_lines': [],
            'removed_words': [],
            'added_words': [],
        }

        params = {
            'action': 'compare',
            'fromrev': fromrev,
            'format': 'json',
        }
        if torev:
            params['torev'] = torev
        if torelative:
            params['torelative'] = torelative
        diffhtml = self.session.get(self.wp_api, params=params).json()
        if 'compare' not in diffhtml:
            self.error('[M.get_diff] fromrev={} torev={} result={}'.format(fromrev, torev, diffhtml))
            return result
        diffhtml = diffhtml['compare']['*']

        soup = BeautifulSoup(diffhtml, 'html.parser')

        for el in soup.find_all('td', {'class': 'diff-deletedline'}):
            result['removed_lines'].append(el.text)
        for el in soup.find_all('td', {'class': 'diff-addedline'}):
            result['added_lines'].append(el.text)
        for el in soup.find_all('del', {'class': 'diffchange-inline'}):
            result['removed_words'].append(el.text)
        for el in soup.find_all('ins', {'class': 'diffchange-inline'}):
            result['added_words'].append(el.text)

        return result

    def get_tags(self, title, revid):
        url = '{0}?action=query&format=json&prop=revisions&titles={1}&rvprop=tags&rvlimit=1&rvstartid={2}&rvendid={2}'.format(
            self.wp_api, urllib.parse.quote(title), revid)
        apiresult = urllib.request.urlopen(url).read().decode('utf8')
        apiresult = json.loads(apiresult)
        if 'query' not in apiresult:
            self.error('[M.get_tags] title={} revid={} result={}'.format(title, revid, apiresult))
            return []
        if 'revisions' not in list(apiresult['query']['pages'].values())[0]:
            self.error('[M.get_tags] title={} revid={} page={}'.format(
                title, revid, list(apiresult['query']['pages'].values())[0]))
            return []
        result = list(apiresult['query']['pages'].values())[0]['revisions'][0]['tags']
        return result

    @functools.lru_cache()
    def get_af_id_by_name(self, af_name, wiki=None):
        if wiki is None:
            wiki = self.wiki

        self.db_execute(
            """SELECT `af_id` FROM `abusefilter`
                WHERE `af_name` = %s AND `wiki` = %s""",
            (af_name, wiki)
        )
        row = self.db_fetchone()
        if row is not None:
            return str(row[0])

        self.db_execute(
            """SELECT `af_id` FROM `abusefilter`
                WHERE `af_name` = %s AND `wiki` = 'metawiki'""",
            (af_name)
        )
        row = self.db_fetchone()
        if row is not None:
            return 'global-{}'.format(row[0])

        return 0

    def load_abusefilter_mode(self, wiki=None):
        if wiki is None:
            wiki = self.wiki

        self.db_execute(
            """SELECT `af_id`, `af_name` FROM `abusefilter`
                WHERE `mode` = 'watch' AND `wiki` = %s""",
            (wiki)
        )
        rows = self.db_fetchall()
        self.abusefilter_watch_id = []
        self.abusefilter_watch_name = []
        for row in rows:
            self.abusefilter_watch_id.append(row[0])
            self.abusefilter_watch_name.append(row[1])

        self.db_execute(
            """SELECT `af_id`, `af_name` FROM `abusefilter`
                WHERE `mode` = 'blacklist' AND `wiki` = %s""",
            (wiki)
        )
        rows = self.db_fetchall()
        self.abusefilter_blacklist_id = []
        self.abusefilter_blacklist_name = []
        for row in rows:
            self.abusefilter_blacklist_id.append(row[0])
            self.abusefilter_blacklist_name.append(row[1])

    def check_abusefilter_watch(self, af_id=None, af_name=None, wiki=None):
        if wiki is None:
            wiki = self.wiki

        if self.abusefilter_watch_id is None:
            return False

        if af_id is not None:
            return af_id in self.abusefilter_watch_id

        if af_name is not None:
            return af_name in self.abusefilter_watch_name

        return False

    def check_abusefilter_blacklist(self, af_id=None, af_name=None, wiki=None):
        if wiki is None:
            wiki = self.wiki

        if self.abusefilter_blacklist_id is None:
            return False

        if af_id is not None:
            return af_id in self.abusefilter_blacklist_id

        if af_name is not None:
            return af_name in self.abusefilter_blacklist_name

        return False

    def login(self):
        logging.info("fetching login token")
        res = self.session.get(self.wp_api, params={
            'action': 'query',
            'meta': 'tokens',
            'type': 'login',
            'format': 'json',
        }).json()
        logintoken = res["query"]["tokens"]["logintoken"]

        logging.info("logging in")
        res = self.session.post(self.wp_api, data={
            'action': 'login',
            'lgname': self.wp_user,
            'lgpassword': self.wp_pass,
            'lgtoken': logintoken,
            'format': 'json',
        }).json()
        if res["login"]["result"] == "Success":
            logging.info("login success")
        else:
            logging.info("login fail")
            return

        res = self.session.get(self.wp_api, params={
            'action': 'query',
            'meta': 'tokens',
            'type': 'csrf|rollback',
            'format': 'json',
        }).json()
        self.csrftoken = res["query"]["tokens"]["csrftoken"]

    def __del__(self):
        if hasattr(self, 'db'):
            self.db.close()


class User():
    def __init__(self, user):
        self.user = user
        self.val = user
        self.userhash = int(hashlib.sha1(user.encode(
            "utf8")).hexdigest(), 16) % (2**64) - 2**63
        self.isuser = True
        self.isipv4 = False
        self.isipv6 = False


class IPv4():
    def __init__(self, start, end, usertype, val):
        self.start = start
        self.end = end
        self.type = usertype
        self.val = str(val)
        self.userhash = int(hashlib.sha1(str(val).encode(
            "utf8")).hexdigest(), 16) % (2**64) - 2**63
        self.isuser = False
        self.isipv4 = True
        self.isipv6 = False


class IPv6():
    def __init__(self, start, end, usertype, val):
        self.start = start
        self.end = end
        self.type = usertype
        self.val = str(val).upper()
        self.userhash = int(hashlib.sha1(str(val).encode(
            "utf8")).hexdigest(), 16) % (2**64) - 2**63
        self.isuser = False
        self.isipv4 = False
        self.isipv6 = True
