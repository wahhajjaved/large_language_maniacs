#!/usr/bin/env python

# -*- coding: utf-8 -*-

# I waive copyright and related rights in the this work worldwide
# through the CC0 1.0 Universal public domain dedication.
# https://creativecommons.org/publicdomain/zero/1.0/legalcode

# Author(s):
#   Tom Parker <tparker@usgs.gov>

"""Retrieve files from GINA
"""


import argparse
import re
import json
import signal
import logging
import os.path
import os
import posixpath
from datetime import timedelta, datetime
from urlparse import urlparse
import sqlite3
import cStringIO
import pycurl
import mattermost as mm
import hashlib
import socket
import viirs

DEFAULT_BACKFILL = 2
DEFAULT_NUM_CONN = 5

INSTRUMENTS = {'viirs': {
    'name': 'viirs',
    'level': 'level1',
    'out_path': 'viirs/sdr',
    # 'match':'/(SVM02|SVM03|SVM04|SVM05|SVM14|SVM15|SVM16|GMTCO)_'
    'match': '/(SVM05|GMTCO)_'
    }}

FACILITIES = ('uafgina', 'gilmore')
GINA_URL = ('http://nrt-status.gina.alaska.edu/products.json' +
            '?action=index&commit=Get+Products&controller=products' +
            '&facilities[]=uafgina')
OUT_DIR = os.environ['OUT_DIR']
DB_FILE = OUT_DIR + '/gina.db'


class MirrorGina(object):

    def __init__(self, args):
        self.args = args
        self.logger = self._setup_logging()

        # We should ignore SIGPIPE when using pycurl.NOSIGNAL - see
        # the libcurl tutorial for more info.
        try:
            signal.signal(signal.SIGPIPE, signal.SIG_IGN)
        except ImportError:
            pass

        self._instrument = INSTRUMENTS[args.instrument]
        self.logger.debug("instrument: %s", self._instrument)

        self._num_conn = args.num_conn
        self.logger.debug("num_conn: %s", self._num_conn)

        self._backfill = args.backfill
        self.logger.debug("backfill: %s", self._backfill)

        self.out_path = os.path.join(OUT_DIR, self._instrument['out_path'], self.args.facility)
        if not os.path.exists(self.out_path):
            self.logger.debug("Making out dir " + self.out_path)
            os.makedirs(self.out_path)

        self.conn = get_db_conn()
        self.mattermost = mm.Mattermost(verbose=True)
        # self.mattermost.set_log_level(logging.DEBUG)

        self.hostname = socket.gethostname()

    def _setup_logging(self):
        logger = logging.getLogger('MirrorGina')
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        if self.args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
            logger.info("Verbose logging")
        else:
            logging.getLogger().setLevel(logging.INFO)

        return logger

    def get_file_list(self):
        self.logger.debug("fetching files")	
        backfill = timedelta(days=self._backfill)
        end_date = datetime.utcnow() + timedelta(days=1)
        start_date = end_date - backfill

        url = GINA_URL
        url += '&start_date=' + start_date.strftime('%Y-%m-%d')
        url += '&end_date=' + end_date.strftime('%Y-%m-%d')
        url += '&sensors[]=' + self._instrument['name']
        url += '&processing_levels[]=' + self._instrument['level']

        self.logger.debug("URL: %s", url)
        buf = cStringIO.StringIO()

        c = pycurl.Curl()
        c.setopt(c.URL, url)
        c.setopt(c.WRITEFUNCTION, buf.write)
        c.perform()

        files = json.loads(buf.getvalue())
        buf.close()

        self.logger.info("Found %s files", len(files))
        files = sorted(files, key=lambda k: k['url'], cmp=viirs.filename_comparator)
        return files

    def path_from_url(self, url):
        path = urlparse(url).path
        filename = posixpath.basename(path)

        return os.path.join(self.out_path, filename)

    def queue_files(self, file_list):

        queue = []
        pattern = re.compile(self._instrument['match'])
        self.logger.debug("%d files before pruning", len(file_list))
        for new_file in file_list:
            out_path = self.path_from_url(new_file['url'])

            if pattern.search(out_path) and not os.path.exists(out_path):
                self.logger.debug("Queueing %s", out_path)
                queue.append((new_file, out_path))
            else:
                self.logger.debug("Skipping %s", out_path)

        self.logger.debug("%d files after pruning", len(queue))
        return queue

    def create_multi(self):
        m = pycurl.CurlMulti()
        m.handles = []
        for i in range(self._num_conn):
            self.logger.debug("creating curl object")
            c = pycurl.Curl()
            c.fp = None
            c.setopt(pycurl.FOLLOWLOCATION, 1)
            c.setopt(pycurl.MAXREDIRS, 5)
            c.setopt(pycurl.CONNECTTIMEOUT, 30)
            c.setopt(pycurl.TIMEOUT, 600)
            c.setopt(pycurl.NOSIGNAL, 1)
            m.handles.append(c)

        return m

    def _log_sighting(self, filename, size, status_code, success, message=None):
        granule = viirs.Viirs(filename)
        sight_date = datetime.utcnow()
        q = self.conn.execute("SELECT proc_date FROM sighting WHERE orbit = ? AND success = ? " 
                              "AND source = ? ORDER BY proc_date DESC",
                              (granule.orbit, True, self.args.facility))
        r = q.fetchone()
        if r is None:
            previous_date = datetime.fromtimestamp(0)
        else:
            previous_date = r[0]

        self.conn.execute('''INSERT OR IGNORE INTO sighting 
                        (source, granule_date, granule_channel, orbit, sight_date, proc_date, 
                        size, status_code, success) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                          (self.args.facility, granule.start, granule.channel, granule.orbit,
                           sight_date, granule.proc_date, size, status_code, success))
        self.conn.commit()

        proc_time = granule.proc_date - granule.start
        trans_time = sight_date - granule.proc_date

        msg = None
        if not success:
            msg = ':x: Failed file: %s %d %s\n' % (granule.channel, granule.orbit, granule.start)
            msg += '  processing delay: %s' % mm.format_timedelta(proc_time)
        else:
            pause = timedelta(hours=1)
            proc_span = granule.proc_date - previous_date
            if previous_date is None or proc_span > pause:
                if previous_date > datetime.fromtimestamp(0):
                    orb_msg = ':snail: _Reprocessed orbit_ from %s: %d' % (self.args.facility, granule.orbit)
                else:
                    orb_msg = ':earth_americas: New orbit from %s: %d' % (self.args.facility, granule.orbit)
                orb_msg += '\n  First granule: %s (%s)' % (mm.format_span(granule.start, granule.end), granule.channel)
                self.mattermost.post(orb_msg)

            if granule.channel in ('GMTCO', 'GITCO'):
                q = self.conn.execute('SELECT COUNT(*) FROM sighting WHERE granule_date = ?' +
                                      ' AND granule_channel = ? AND success = ? AND source = ?',
                                      (granule.start, granule.channel, True, self.args.facility))
                count = q.fetchone()[0]
                granule_span = mm.format_span(granule.start, granule.end)
                if count > 1:
                    msg = ':snail: _Reprocessed granule_ from %s: %s\n' % (self.args.facility, granule_span)
                else:
                    msg = ':satellite: New granule from %s: %s\n' % (self.args.facility, granule_span)

                msg += '  processing delay:  %s\n' % mm.format_timedelta(proc_time)
                msg += '  transfer delay:  %s\n' % mm.format_timedelta(trans_time)
                msg += '  granule length: %s' % mm.format_timedelta(granule.end - granule.start)

        if msg:
            if message:
                msg += "\n  message: %s" % message

            # msg += '  host: %s' % self.hostname
            self.mattermost.post(msg)

    def fetch_files(self):
        # modeled after retiever-multi.py from pycurl
        file_list = self.get_file_list()
        file_queue = self.queue_files(file_list)

        m = self.create_multi()

        freelist = m.handles[:]
        num_processed = 0
        num_files = len(file_queue)
        self.logger.debug("Fetching %d files with %d connections.", num_files, len(freelist))
        while num_processed < num_files:
            # If there is an url to process and a free curl object, add to multi stack
            while file_queue and freelist:
                new_file, filename = file_queue.pop(0)
                url = new_file['url']
                c = freelist.pop()
                c.fp = open(filename, "wb")
                c.setopt(pycurl.URL, url.encode('ascii', 'replace'))
                c.setopt(pycurl.WRITEDATA, c.fp)
                m.add_handle(c)
                self.logger.debug("added handle")
                # store some info
                c.filename = filename
                c.url = url
                c.md5 = new_file['md5sum']
            # Run the internal curl state machine for the multi stack
            while 1:
                ret, num_handles = m.perform()
                if ret != pycurl.E_CALL_MULTI_PERFORM:
                    break
            # Check for curl objects which have terminated, and add them to the freelist
            while 1:
                num_q, ok_list, err_list = m.info_read()
                for c in ok_list:
                    print("Success:", c.filename, c.url, c.getinfo(pycurl.EFFECTIVE_URL))
                    size = c.getinfo(pycurl.CONTENT_LENGTH_DOWNLOAD)
                    status_code = c.getinfo(pycurl.HTTP_CODE)
                    c.fp.close()
                    c.fp = None
                    m.remove_handle(c)
                    freelist.append(c)
                    file_md5 = hashlib.md5(open(c.filename, 'rb').read()).hexdigest()
                    self.logger.debug(str(c.md5) + " : " + str(file_md5))

                    if c.md5 == file_md5:
                        success = True
                        errmsg = None
                    else:
                        success = False
                        errmsg = 'Bad checksum'

                    self._log_sighting(c.filename, size, status_code, success, message=errmsg)

                for c, errno, errmsg in err_list:
                    print("Failed:", c.filename, c.url, errno, errmsg)
                    size = c.getinfo(pycurl.CONTENT_LENGTH_DOWNLOAD)
                    status_code = c.getinfo(pycurl.HTTP_CODE)
                    self._log_sighting(c.filename, size, status_code, False, message=errmsg)
                    c.fp.close()
                    os.unlink(c.filename)
                    c.fp = None
                    m.remove_handle(c)
                    freelist.append(c)
                num_processed += len(ok_list) + len(err_list)
                if num_q == 0:
                    break
            # Currently no more I/O is pending, could do something in the meantime
            # (display a progress bar, etc.).
            # We just call select() to sleep until some more data is available.
            m.select(1.0)

        # Cleanup
        self.logger.debug("cleaning up")
        for c in m.handles:
            if c.fp is not None:
                c.fp.close()
                c.fp = None
            c.close()
        m.close()
        self.conn.close()


def get_db_conn():
    conn = sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS sighting (
                    source text,
                    granule_date timestamp, 
                    granule_channel text,
                    orbit int,
                    sight_date timestamp, 
                    proc_date timestamp, 
                    size int,
                    status_code int,
                    success int,
                    PRIMARY KEY (source, granule_date, granule_channel, proc_date));''')

    conn.commit()

    return conn


# Get args
def arg_parse():

    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--num_conn", 
                        help="# of concurrent connections", type=int, 
                        default=DEFAULT_NUM_CONN)
    parser.add_argument("-b", "--backfill", 
                        help="# of days to back fill", 
                        type=int, default=DEFAULT_BACKFILL)
    parser.add_argument("-v", "--verbose", 
                        help="Verbose logging",
                        action='store_true')
    parser.add_argument('-f', '--facility', choices=FACILITIES,
                        help="facility to query", required=True)
    parser.add_argument('instrument', choices=INSTRUMENTS.keys(),
                        help="instrument to query")

    return parser.parse_args()


def main():
    args = arg_parse()

    mirror_gina = MirrorGina(args)
    mirror_gina.fetch_files()

if __name__ == "__main__":
    main()
