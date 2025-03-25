#!/usr/bin/env python
# Copyright(C) 2011 by John Tobey <John.Tobey@gmail.com>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Affero General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public
# License along with this program.  If not, see
# <http://www.gnu.org/licenses/agpl.html>.

import sys
import os
import warnings
import optparse
import re
from cgi import escape
import posixpath
import wsgiref.util
import time

import DataStore

# bitcointools -- modified deserialize.py to return raw transaction
import deserialize
import util  # Added functions.
import base58

ABE_APPNAME = "Abe"
ABE_VERSION = '0.2'
ABE_URL = 'https://github.com/jtobey/bitcoin-abe'

COPYRIGHT_YEARS = '2011'
COPYRIGHT = "John Tobey"
COPYRIGHT_URL = "mailto:John.Tobey@gmail.com"

# XXX This should probably be a property of chain, or even a query param.
LOG10COIN = 8
COIN = 10 ** LOG10COIN

ADDRESS_RE = re.compile(
    '[123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]{6,}\\Z')
HEIGHT_RE = re.compile('(?:0|[1-9][0-9]*)\\Z')
HASH_PREFIX_RE = re.compile('[0-9a-fA-F]{6,64}\\Z')

def make_store(args):
    store = DataStore.new(args)
    store.initialize_if_needed()
    store.catch_up()
    return store

class NoSuchChainError(Exception):
    """Thrown when a chain lookup fails"""

class PageNotFound(Exception):
    """Thrown when code wants to return 404 Not Found"""

class Redirect(Exception):
    """Thrown when code wants to redirect the request"""

class Abe:
    def __init__(abe, store, args):
        abe.store = store
        abe.args = args
        abe.htdocs = os.path.join(os.path.split(__file__)[0], 'htdocs')
        abe.footer = (
            '<p style="font-size: smaller">' +
            '<span style="font-style: italic">' +
            '<a href="' + ABE_URL + '">' + ABE_APPNAME + '</a> ' +
            ABE_VERSION + ' &#9400; ' + COPYRIGHT_YEARS +
            ' <a href="' + escape(COPYRIGHT_URL) + '">' +
            escape(COPYRIGHT) + '</a></span>' +
            ' Tips appreciated! <a href="%(dotdot)saddress/' +
            '1PWC7PNHL1SgvZaN7xEtygenKjWobWsCuf">BTC</a>' +
            ' <a href="%(dotdot)saddress/' +
            'NJ3MSELK1cWnqUa6xhF2wUYAnz3RSrWXcK">NMC</a></p>\n')
        abe.debug = abe.args.debug
        import logging
        abe.log = logging
        abe.log.info('Abe initialized.')
        abe.handlers = {
            "": abe.show_world,
            "chains": abe.show_world,
            "chain": abe.show_chain,
            "block": abe.show_block,
            "tx": abe.show_tx,
            "address": abe.show_address,
            "search": abe.search,
            }
        # Change this to map the htdocs directory somewhere other than
        # the dynamic content root.  E.g., abe.static_path = '/static'
        # XXX Should be configurable.
        abe.static_path = ''

    def __call__(abe, env, start_response):
        import urlparse

        status = '200 OK'
        page = {
            "title": [escape(ABE_APPNAME), " ", ABE_VERSION],
            "body": [],
            "env": env,
            "params": {},
            "dotdot": "../" * (env['PATH_INFO'].count('/') - 1),
            "start_response": start_response,
            }
        if 'QUERY_STRING' in env:
            page['params'] = urlparse.parse_qs(env['QUERY_STRING'])

        if fix_path_info(env):
            print "fixed path_info"
            return redirect(page)

        # Always be up-to-date, even if we means having to wait for a response!
        # XXX Could use threads, timers, or a cron job.
        abe.store.catch_up()

        obtype = wsgiref.util.shift_path_info(env)
        handler = abe.handlers.get(obtype)
        try:
            if handler is None:
                return abe.serve_static(obtype + env['PATH_INFO'],
                                        start_response)
            handler(page)
        except PageNotFound:
            status = '404 Not Found'
            page["body"] = ['<p class="error">Sorry, ', env['SCRIPT_NAME'],
                            env['PATH_INFO'],
                            ' does not exist on this server.</p>']
        except NoSuchChainError, e:
            page['body'] += [
                '<p class="error">'
                'Sorry, I don\'t know about that chain!</p>\n']
        except Redirect:
            return redirect(page)
        except:
            abe.store.rollback()
            raise

        abe.store.rollback()  # Close imlicitly opened transaction.

        start_response(status, [('Content-type', 'application/xhtml+xml'),
                                ('Cache-Control', 'max-age=30')])

        return map(flatten,
                   ['<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"\n'
                    '  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">\n'
                    '<html xmlns="http://www.w3.org/1999/xhtml"'
                    ' xml:lang="en" lang="en">\n'
                    '<head>\n',
                    '<link rel="stylesheet" type="text/css" href="',
                    page['dotdot'], abe.static_path, 'abe.css" />\n'
                    '<link rel="shortcut icon" href="',
                    page['dotdot'], abe.static_path, 'favicon.ico" />\n'
                    '<title>', page['title'], '</title>\n</head>\n',
                    '<body>\n',
                    '<h1><a href="', page['dotdot'] or '/', '"><img src="',
                    page['dotdot'], abe.static_path, 'logo32.png',
                    '" alt="ABE logo" /></a> ',
                    page.get('h1') or page['title'], '</h1>\n', page['body'],
                    abe.footer % page, '</body></html>'])

    def show_world(abe, page):
        page['title'] = ABE_APPNAME + ' Search'
        body = page['body']
        body += [
            abe.search_form(page),
            '<table>\n',
            '<tr><th>Currency</th><th>Code</th><th>Block</th>',
            '<th>Started</th><th>Age (days)</th><th>Coins Created</th>',
            '<th>Avg Coin Age</th><th>',
            '% <a href="https://en.bitcoin.it/wiki/Bitcoin_Days_Destroyed">',
            'CoinDD</a></th>',
            '</tr>\n']
        now = time.time()

        for row in abe.store.selectall("""
            SELECT c.chain_name, b.block_height, b.block_nTime,
                   b.block_total_seconds, b.block_total_satoshis,
                   b.block_satoshi_seconds, b.block_hash,
                   b.block_total_ss, c.chain_id, c.chain_code3,
                   c.chain_address_version, c.chain_last_block_id
              FROM chain c
              LEFT JOIN block b ON (c.chain_last_block_id = b.block_id)
             ORDER BY c.chain_name
        """):
            name = row[0]
            chain = abe._row_to_chain((row[8], name, row[9], row[10], row[11]))
            body += [
                '<tr><td><a href="chain/', escape(name), '/">',
                escape(name), '</a></td><td>', escape(chain['code3']), '</td>']

            if row[1] is not None:
                (height, nTime, seconds, satoshis, ss, hash, total_ss) = (
                    int(row[1]), int(row[2]), int(row[3]), int(row[4]),
                    int(row[5]), abe.store.hashout_hex(row[6]), int(row[7]))

                started = nTime - seconds
                chain_age = now - started
                since_block = now - nTime

                if satoshis == 0:
                    avg_age = '&nbsp;'
                else:
                    avg_age = '%5g' % ((float(ss) / satoshis + since_block)
                                       / 86400.0)

                if chain_age <= 0:
                    percent_destroyed = '&nbsp;'
                else:
                    more = since_block * satoshis
                    percent_destroyed = '%5g' % (
                        100.0 - (100.0 * (ss + more) / (total_ss + more))) + '%'

                body += [
                    '<td><a href="block/', hash, '">', height, '</a></td>',
                    '<td>', format_time(started), '</td>',
                    '<td>', '%5g' % (chain_age / 86400.0), '</td>',
                    '<td>', format_satoshis(satoshis, chain), '</td>',
                    '<td>', avg_age, '</td>',
                    '<td>', percent_destroyed, '</td>']
            body += ['</tr>\n']
        body += ['</table>\n']

    def _chain_fields(abe):
        return ["id", "name", "code3", "address_version", "last_block_id"]

    def _row_to_chain(abe, row):
        if row is None:
            raise NoSuchChainError()
        chain = {}
        fields = abe._chain_fields()
        for i in range(len(fields)):
            chain[fields[i]] = row[i]
        chain['address_version'] = abe.store.binout(chain['address_version'])
        return chain

    def chain_lookup_by_name(abe, symbol):
        if symbol is None:
            return abe.get_default_chain()
        return abe._row_to_chain(abe.store.selectrow("""
            SELECT chain_""" + ", chain_".join(abe._chain_fields()) + """
              FROM chain
             WHERE chain_name = ?""", (symbol,)))

    def get_default_chain(abe):
        return abe.chain_lookup_by_name('Bitcoin')

    def chain_lookup_by_id(abe, chain_id):
        return abe._row_to_chain(abe.store.selectrow("""
            SELECT chain_""" + ", chain_".join(abe._chain_fields()) + """
              FROM chain
             WHERE chain_id = ?""", (chain_id,)))

    def show_chain(abe, page):
        symbol = wsgiref.util.shift_path_info(page['env'])
        chain = abe.chain_lookup_by_name(symbol)

        cmd = wsgiref.util.shift_path_info(page['env'])
        if cmd == 'b':
            return abe.show_block_number(chain, page)
        if cmd == '':
            #print "removing /"
            # Tolerate trailing slash.
            page['env']['SCRIPT_NAME'] = page['env']['SCRIPT_NAME'][:-1]
            raise Redirect()
        if cmd is not None:
            raise PageNotFound()

        page['title'] = chain['name']

        body = page['body']

        count = get_int_param(page, 'count') or 20
        hi = get_int_param(page, 'hi')
        orig_hi = hi

        if hi is None:
            row = abe.store.selectrow("""
                SELECT b.block_height
                  FROM block b
                  JOIN chain c ON (c.chain_last_block_id = b.block_id)
                 WHERE c.chain_id = ?
            """, (chain['id'],))
            if row:
                hi = row[0]
        if hi is None:
            if orig_hi is None and count > 0:
                body += ['<p>I have no blocks in this chain.</p>']
            else:
                body += ['<p class="error">'
                         'The requested range contains no blocks.</p>\n']
            return True

        rows = abe.store.selectall("""
            SELECT block_hash, block_height, block_nTime, num_tx,
                   block_nBits, block_value_out,
                   block_total_seconds, block_satoshi_seconds,
                   block_total_satoshis, block_ss_destroyed, block_total_ss
              FROM chain_summary
             WHERE chain_id = ?
               AND block_height BETWEEN ? AND ?
               AND in_longest = 1
             ORDER BY block_height DESC LIMIT ?
        """, (chain['id'], hi - count + 1, hi, count))

        if hi is None:
            hi = int(rows[0][1])
        basename = os.path.basename(page['env']['PATH_INFO'])

        nav = ['<a href="',
               basename, '?count=', str(count), '">&lt;&lt;</a>']
        nav += [' <a href="', basename, '?hi=', str(hi + count),
                 '&amp;count=', str(count), '">&lt;</a>']
        nav += [' ', '&gt;']
        if hi >= count:
            nav[-1] = ['<a href="', basename, '?hi=', str(hi - count),
                        '&amp;count=', str(count), '">', nav[-1], '</a>']
        nav += [' ', '&gt;&gt;']
        if hi != count - 1:
            nav[-1] = ['<a href="', basename, '?hi=', str(count - 1),
                        '&amp;count=', str(count), '">', nav[-1], '</a>']
        for c in (20, 50, 100, 500, 2016):
            nav += [' ']
            if c != count:
                nav += ['<a href="', basename, '?count=', str(c)]
                if hi is not None:
                    nav += ['&amp;hi=', str(max(hi, c - 1))]
                nav += ['">']
            nav += [' ', str(c)]
            if c != count:
                nav += ['</a>']

        nav += [' <a href="', page['dotdot'], '">Search</a>']

        extra = False
        #extra = True
        body += ['<p>', nav, '</p>\n',
                 '<table><tr><th>Block</th><th>Approx. Time</th>',
                 '<th>Transactions</th><th>Value Out</th>',
                 '<th>Difficulty</th><th>Outstanding</th>',
                 '<th>Average Age</th><th>Chain Age</th>',
                 '<th>% ',
                 '<a href="https://en.bitcoin.it/wiki/Bitcoin_Days_Destroyed">',
                 'CoinDD</a></th>',
                 ['<th>Satoshi-seconds</th>',
                  '<th>Total ss</th>']
                 if extra else '',
                 '</tr>\n']
        for row in rows:
            (hash, height, nTime, num_tx, nBits, value_out,
             seconds, ss, satoshis, destroyed, total_ss) = row
            nTime = int(nTime)
            value_out = int(value_out)
            seconds = int(seconds)
            satoshis = int(satoshis)
            ss = int(ss)
            total_ss = int(total_ss)

            if satoshis == 0:
                avg_age = '&nbsp;'
            else:
                avg_age = '%5g' % (ss / satoshis / 86400.0)

            if seconds <= 0:
                percent_destroyed = '&nbsp;'
            else:
                percent_destroyed = '%5g' % (
                    100.0 - (100.0 * ss / total_ss)) + '%'

            body += [
                '<tr><td><a href="', page['dotdot'], 'block/',
                abe.store.hashout_hex(hash),
                '">', height, '</a>'
                '</td><td>', format_time(int(nTime)),
                '</td><td>', num_tx,
                '</td><td>', format_satoshis(value_out, chain),
                '</td><td>', util.calculate_difficulty(int(nBits)),
                '</td><td>', format_satoshis(satoshis, chain),
                '</td><td>', avg_age,
                '</td><td>', '%5g' % (seconds / 86400.0),
                '</td><td>', percent_destroyed,
                ['</td><td>', '%8g' % ss,
                 '</td><td>', '%8g' % total_ss] if extra else '',
                '</td></tr>\n']

        body += ['</table>\n<p>', nav, '</p>\n']
        return True

    def _show_block(abe, where, bind, page, dotdotblock, chain):
        address_version = ('\0' if chain is None
                           else chain['address_version'])
        body = page['body']
        sql = """
            SELECT
                block_id,
                block_hash,
                block_version,
                block_hashMerkleRoot,
                block_nTime,
                block_nBits,
                block_nNonce,
                block_height,
                prev_block_hash,
                block_chain_work,
                block_value_in,
                block_value_out,
                block_total_satoshis,
                block_total_seconds,
                block_satoshi_seconds,
                block_total_ss,
                block_ss_destroyed,
                num_tx
              FROM chain_summary
             WHERE """ + where
        row = abe.store.selectrow(sql, bind)
        if (row is None):
            body += ['<p class="error">Block not found.</p>']
            return
        (block_id, block_hash, block_version, hashMerkleRoot,
         nTime, nBits, nNonce, height,
         prev_block_hash, block_chain_work, value_in, value_out,
         satoshis, seconds, ss, total_ss, destroyed, num_tx) = (
            row[0], abe.store.hashout_hex(row[1]), row[2],
            abe.store.hashout_hex(row[3]), row[4], int(row[5]), row[6],
            row[7], abe.store.hashout_hex(row[8]),
            abe.store.binout_int(row[9]), int(row[10]), int(row[11]),
            None if row[12] is None else int(row[12]),
            None if row[13] is None else int(row[13]),
            None if row[14] is None else int(row[14]),
            None if row[15] is None else int(row[15]),
            None if row[16] is None else int(row[16]),
            int(row[17]),
            )

        next_list = abe.store.selectall("""
            SELECT DISTINCT n.block_hash, cc.in_longest
              FROM block_next bn
              JOIN block n ON (bn.next_block_id = n.block_id)
              JOIN chain_candidate cc ON (n.block_id = cc.block_id)
             WHERE bn.block_id = ?
             ORDER BY cc.in_longest DESC""",
                                  (block_id,))

        if chain is None:
            page['title'] = ['Block ', height]
        else:
            page['title'] = [escape(chain['name']), ' ', height]
            page['h1'] = ['<a href="', page['dotdot'], 'chain/',
                          escape(chain['name']), '?hi=', height, '">',
                          escape(chain['name']), '</a> ', height]
        body += ['<p>Hash: ', block_hash, '<br />\n']

        if prev_block_hash is not None:
            body += ['Previous Block: <a href="', dotdotblock,
                     prev_block_hash, '">', prev_block_hash, '</a><br />\n']
        if next_list:
            body += ['Next Block: ']
        for row in next_list:
            hash = abe.store.hashout_hex(row[0])
            body += ['<a href="', dotdotblock, hash, '">', hash, '</a><br />\n']

        

        body += [
            'Height: ', height, '<br />\n',
            'Version: ', block_version, '<br />\n',
            'Transaction Merkle Root: ', hashMerkleRoot, '<br />\n',
            'Time: ', nTime, ' (', format_time(nTime), ')<br />\n',
            'Difficulty: ', format_difficulty(util.calculate_difficulty(nBits)),
            ' (Bits: %x)' % (nBits,), '<br />\n',
            'Cumulative Difficulty: ', format_difficulty(
                util.work_to_difficulty(block_chain_work)), '<br />\n',
            'Nonce: ', nNonce, '<br />\n',
            'Transactions: ', num_tx, '<br />\n',
            'Value out: ', format_satoshis(value_out, chain), '<br />\n',

            ['Average Coin Age: %6g' % (ss / 86400.0 / satoshis,),
             ' days<br />\n']
            if satoshis and (ss is not None) else '',

            '' if destroyed is None else
            ['Coin-days Destroyed: ',
             format_satoshis(int(destroyed / 86400.0), chain), '<br />\n'],

            ['Cumulative Coin-days Destroyed: %6g%%<br />\n' %
             (100 * (1 - float(ss) / total_ss),)]
            if total_ss else '',

            ['sat=',satoshis,';sec=',seconds,';ss=',ss,
             ';total_ss=',total_ss,';destroyed=',destroyed]
            if abe.debug else '',

            '</p>\n']

        body += ['<h3>Transactions</h3>\n']

        tx_ids = []
        txs = {}
        block_out = 0
        block_in = 0
        abe.store.sql("""
            SELECT tx_id, tx_hash, tx_size, txout_value, pubkey_hash
              FROM txout_detail
             WHERE block_id = ?
             ORDER BY tx_pos, txout_pos
        """, (block_id,))
        for row in abe.store.cursor:
            tx_id, tx_hash_hex, tx_size, txout_value, pubkey_hash = (
                row[0], abe.store.hashout_hex(row[1]), int(row[2]),
                int(row[3]), abe.store.binout(row[4]))
            tx = txs.get(tx_id)
            if tx is None:
                tx_ids.append(tx_id)
                txs[tx_id] = {
                    "hash": tx_hash_hex,
                    "total_out": 0,
                    "total_in": 0,
                    "out": [],
                    "in": [],
                    "size": tx_size,
                    }
                tx = txs[tx_id]
            tx['total_out'] += txout_value
            block_out += txout_value
            tx['out'].append({
                    "value": txout_value,
                    "address": hash_to_address(address_version, pubkey_hash),
                    })
        abe.store.sql("""
            SELECT tx_id, txin_value, pubkey_hash
              FROM txin_detail
             WHERE block_id = ?
             ORDER BY tx_pos, txin_pos
        """, (block_id,))
        for row in abe.store.cursor:
            tx_id, txin_value, pubkey_hash = (
                row[0], 0 if row[1] is None else int(row[1]),
                abe.store.binout(row[2]))
            tx = txs.get(tx_id)
            if tx is None:
                # Strange, inputs but no outputs?
                tx_ids.append(tx_id)
                #row2 = abe.store.selectrow("""
                #    SELECT tx_hash, tx_size FROM tx WHERE tx_id = ?""",
                #                           (tx_id,))
                txs[tx_id] = {
                    "hash": "AssertionFailedTxInputNoOutput",
                    "total_out": 0,
                    "total_in": 0,
                    "out": [],
                    "in": [],
                    "size": -1,
                    }
                tx = txs[tx_id]
            tx['total_in'] += txin_value
            block_in += txin_value
            tx['in'].append({
                    "value": txin_value,
                    "address": hash_to_address(address_version, pubkey_hash),
                    })

        body += ['<table><tr><th>Transaction</th><th>Fee</th>'
                 '<th>Size (kB)</th><th>From (amount)</th><th>To (amount)</th>'
                 '</tr>\n']
        for tx_id in tx_ids:
            tx = txs[tx_id]
            is_coinbase = (tx_id == tx_ids[0])
            if is_coinbase:
                fees = 0
            else:
                fees = tx['total_in'] - tx['total_out']
            body += ['<tr><td><a href="../tx/' + tx['hash'] + '">',
                     tx['hash'][:10], '...</a>'
                     '</td><td>', format_satoshis(fees, chain),
                     '</td><td>', tx['size'] / 1000.0,
                     '</td><td>']
            if is_coinbase:
                gen = block_out - block_in
                fees = tx['total_out'] - gen
                body += ['Generation: ', format_satoshis(gen, chain),
                         ' + ', format_satoshis(fees, chain), ' total fees']
            else:
                for txin in tx['in']:
                    body += ['<a href="', page['dotdot'], 'address/',
                             txin['address'], '">', txin['address'], '</a>: ',
                             format_satoshis(txin['value'], chain), '<br />']
            body += ['</td><td>']
            for txout in tx['out']:
                body += ['<a href="', page['dotdot'], 'address/',
                         txout['address'], '">', txout['address'], '</a>: ',
                         format_satoshis(txout['value'], chain), '<br />']
            body += ['</td></tr>\n']
        body += '</table>\n'

    def show_block_number(abe, chain, page):
        height = wsgiref.util.shift_path_info(page['env'])
        try:
            height = int(height)
        except:
            raise PageNotFound()
        if height < 0 or page['env']['PATH_INFO'] != '':
            raise PageNotFound()

        page['title'] = [escape(chain['name']), ' ', height]
        abe._show_block('chain_id = ? AND block_height = ? AND in_longest = 1',
                        (chain['id'], height), page, '../block/', chain)

    def show_block(abe, page):
        block_hash = wsgiref.util.shift_path_info(page['env'])
        if block_hash in (None, '') or page['env']['PATH_INFO'] != '':
            raise PageNotFound()

        page['title'] = 'Block'

        if not HASH_PREFIX_RE.match(block_hash):
            page['body'] += ['<p class="error">Not a valid block hash.</p>']
            return

        # Try to show it as a block number, not a block hash.

        dbhash = abe.store.hashin_hex(block_hash)

        # XXX arbitrary choice: minimum chain_id.  Should support
        # /chain/CHAIN/block/HASH URLs and try to keep "next block"
        # links on the chain.
        row = abe.store.selectrow("""
            SELECT MIN(cc.chain_id), cc.block_id, cc.block_height
              FROM chain_candidate cc JOIN block b USING (block_id)
             WHERE b.block_hash = ? AND cc.in_longest = 1
             GROUP BY cc.block_id, cc.block_height""",
            (dbhash,))
        if row is None:
            abe._show_block('block_hash = ?', (dbhash,), page, '', None)
        else:
            chain_id, block_id, height = row
            chain = abe.chain_lookup_by_id(chain_id)
            page['title'] = [escape(chain['name']), ' ', height]
            abe._show_block('block_id = ?', (block_id,), page, '', chain)

    def show_tx(abe, page):
        tx_hash = wsgiref.util.shift_path_info(page['env'])
        if tx_hash in (None, '') or page['env']['PATH_INFO'] != '':
            raise PageNotFound()

        page['title'] = ['Transaction ', tx_hash[:10], '...', tx_hash[-4:]]
        body = page['body']

        if not HASH_PREFIX_RE.match(tx_hash):
            body += ['<p class="error">Not a valid transaction hash.</p>']
            return

        row = abe.store.selectrow("""
            SELECT tx_id, tx_version, tx_lockTime, tx_size
              FROM tx
             WHERE tx_hash = ?
        """, (abe.store.hashin_hex(tx_hash),))
        if row is None:
            body += ['<p class="error">Transaction not found.</p>']
            return
        tx_id, tx_version, tx_lockTime, tx_size = (
            int(row[0]), int(row[1]), int(row[2]), int(row[3]))

        block_rows = abe.store.selectall("""
            SELECT c.chain_name, cc.in_longest,
                   b.block_nTime, b.block_height, b.block_hash,
                   block_tx.tx_pos
              FROM chain c
              JOIN chain_candidate cc USING (chain_id)
              JOIN block b USING (block_id)
              JOIN block_tx USING (block_id)
             WHERE block_tx.tx_id = ?
             ORDER BY c.chain_id, cc.in_longest DESC, b.block_hash
        """, (tx_id,))

        def parse_row(row):
            pos, script, value, o_hash, o_pos, binaddr = row
            return {
                "pos": int(pos),
                "script": abe.store.binout(script),
                "value": None if value is None else int(value),
                "o_hash": abe.store.hashout_hex(o_hash),
                "o_pos": None if o_pos is None else int(o_pos),
                "binaddr": abe.store.binout(binaddr),
                }

        def row_to_html(row, this_ch, other_ch, no_link_text):
            body = page['body']
            body += [
                '<tr>\n',
                '<td><a name="', this_ch, row['pos'], '">', row['pos'],
                '</a></td>\n<td>']
            if row['o_hash'] is None:
                body += [no_link_text]
            else:
                body += [
                    '<a href="', row['o_hash'], '#', other_ch, row['o_pos'],
                    '">', row['o_hash'][:10], '...:', row['o_pos'], '</a>']
            body += [
                '</td>\n',
                '<td>', format_satoshis(row['value'], chain), '</td>\n',
                '<td>']
            if row['binaddr'] is None:
                body += ['Unknown']
            else:
                addr = hash_to_address(chain['address_version'], row['binaddr'])
                body += ['<a href="../address/', addr, '">', addr, '</a>']
            body += [
                '</td>\n',
                '<td>', escape(deserialize.decode_script(row['script'])),
                '</td>\n</tr>\n']

        # XXX Unneeded outer join.
        in_rows = map(parse_row, abe.store.selectall("""
            SELECT 
                txin.txin_pos,
                txin.txin_scriptSig,
                txout.txout_value,
                COALESCE(prevtx.tx_hash, u.txout_tx_hash),
                COALESCE(txout.txout_pos, u.txout_pos),
                pubkey.pubkey_hash
              FROM txin
              LEFT JOIN txout USING (txout_id)
              LEFT JOIN pubkey USING (pubkey_id)
              LEFT JOIN tx prevtx ON (txout.tx_id = prevtx.tx_id)
              LEFT JOIN unlinked_txin u USING (txin_id)
             WHERE txin.tx_id = ?
             ORDER BY txin.txin_pos
        """, (tx_id,)))

        # XXX Only two outer JOINs needed.
        out_rows = map(parse_row, abe.store.selectall("""
            SELECT 
                txout.txout_pos,
                txout.txout_scriptPubKey,
                txout.txout_value,
                nexttx.tx_hash,
                txin.txin_pos,
                pubkey.pubkey_hash
              FROM txout
              LEFT JOIN txin USING (txout_id)
              LEFT JOIN pubkey USING (pubkey_id)
              LEFT JOIN tx nexttx ON (txin.tx_id = nexttx.tx_id)
             WHERE txout.tx_id = ?
             ORDER BY txout.txout_pos
        """, (tx_id,)))

        def sum_values(rows):
            ret = 0
            for row in rows:
                if row['value'] is None:
                    return None
                ret += row['value']
            return ret

        value_in = sum_values(in_rows)
        value_out = sum_values(out_rows)
        is_coinbase = None

        body += ['<p>Hash: ', tx_hash, '<br />\n']
        chain = None
        for row in block_rows:
            (name, in_longest, nTime, height, blk_hash, tx_pos) = (
                row[0], int(row[1]), int(row[2]), int(row[3]),
                abe.store.hashout_hex(row[4]), int(row[5]))
            if chain is None:
                chain = abe.chain_lookup_by_name(name)
                is_coinbase = (tx_pos == 0)
            elif name <> chain['name']:
                abe.log.warn('Transaction ' + tx_hash + ' in multiple chains: '
                             + name + ', ' + chain['name'])
            body += [
                'Appeared in <a href="../block/', blk_hash, '">',
                escape(name), ' ',
                height if in_longest else [blk_hash[:10], '...', blk_hash[-4:]],
                '</a> (', format_time(nTime), ')<br />\n']

        if chain is None:
            abe.log.warn('Assuming default chain for Transaction ' + tx_hash)
            chain = abe.get_default_chain()

        body += [
            'Number of inputs: ', len(in_rows),
            ' (<a href="#inputs">Jump to inputs</a>)<br />\n',
            'Total in: ', format_satoshis(value_in, chain), '<br />\n',
            'Number of outputs: ', len(out_rows),
            ' (<a href="#outputs">Jump to outputs</a>)<br />\n',
            'Total out: ', format_satoshis(value_out, chain), '<br />\n',
            'Size: ', tx_size, ' bytes<br />\n',
            'Fee: ', format_satoshis(0 if is_coinbase else
                                     (value_in and value_out and
                                      value_in - value_out), chain),
            '<br />\n']
        body += ['</p>\n',
                 '<a name="inputs"><h3>Inputs</h3></a>\n<table>\n',
                 '<tr><th>Index</th><th>Previous output</th><th>Amount</th>',
                 '<th>From address</th><th>ScriptSig</th></tr>\n']
        for row in in_rows:
            row_to_html(row, 'i', 'o',
                        'Generation' if is_coinbase else 'Unknown')
        body += ['</table>\n',
                 '<a name="outputs"><h3>Outputs</h3></a>\n<table>\n',
                 '<tr><th>Index</th><th>Redeemed at input</th><th>Amount</th>',
                 '<th>To address</th><th>ScriptPubKey</th></tr>\n']
        for row in out_rows:
            row_to_html(row, 'o', 'i', 'Not yet redeemed')

        body += ['</table>\n']

    def show_address(abe, page):
        address = wsgiref.util.shift_path_info(page['env'])
        if address in (None, '') or page['env']['PATH_INFO'] != '':
            raise PageNotFound()

        body = page['body']
        page['title'] = 'Address ' + escape(address)
        version, binaddr = decode_check_address(address)
        if binaddr is None:
            body += ['<p>Not a valid address.</p>']
            return

        dbhash = abe.store.binin(binaddr)

        chains = {}
        balance = {}
        received = {}
        sent = {}
        count = [0, 0]
        chain_ids = []
        def adj_balance(txpoint):
            chain_id = txpoint['chain_id']
            value = txpoint['value']
            if chain_id not in balance:
                chain_ids.append(chain_id)
                chains[chain_id] = abe.chain_lookup_by_id(chain_id)
                balance[chain_id] = 0
                received[chain_id] = 0
                sent[chain_id] = 0
            balance[chain_id] += value
            if value > 0:
                received[chain_id] += value
            else:
                sent[chain_id] -= value
            count[txpoint['is_in']] += 1

        txpoints = []
        rows = abe.store.selectall("""
            SELECT
                b.block_nTime,
                cc.chain_id,
                b.block_height,
                1,
                b.block_hash,
                tx.tx_hash,
                txin.txin_pos,
                -prevout.txout_value
              FROM chain_candidate cc
              JOIN block b USING (block_id)
              JOIN block_tx USING (block_id)
              JOIN tx USING (tx_id)
              JOIN txin USING (tx_id)
              JOIN txout prevout ON (txin.txout_id = prevout.txout_id)
              JOIN pubkey USING (pubkey_id)
             WHERE pubkey_hash = ?
               AND cc.in_longest = 1""",
                      (dbhash,))
        rows += abe.store.selectall("""
            SELECT
                b.block_nTime,
                cc.chain_id,
                b.block_height,
                0,
                b.block_hash,
                tx.tx_hash,
                txout.txout_pos,
                txout.txout_value
              FROM chain_candidate cc
              JOIN block b USING (block_id)
              JOIN block_tx USING (block_id)
              JOIN tx USING (tx_id)
              JOIN txout USING (tx_id)
              JOIN pubkey USING (pubkey_id)
             WHERE pubkey_hash = ?
               AND cc.in_longest = 1""",
                      (dbhash,))
        rows.sort()
        for row in rows:
            nTime, chain_id, height, is_in, blk_hash, tx_hash, pos, value = row
            txpoint = {
                    "nTime":    int(nTime),
                    "chain_id": int(chain_id),
                    "height":   int(height),
                    "is_in":    int(is_in),
                    "blk_hash": abe.store.hashout_hex(blk_hash),
                    "tx_hash":  abe.store.hashout_hex(tx_hash),
                    "pos":      int(pos),
                    "value":    int(value),
                    }
            adj_balance(txpoint)
            txpoints.append(txpoint)

        if (not chain_ids):
            body += ['<p>Address not seen on the network.</p>']
            return

        def format_amounts(amounts, link):
            ret = []
            for chain_id in chain_ids:
                chain = chains[chain_id]
                if chain_id != chain_ids[0]:
                    ret += [', ']
                ret += [format_satoshis(amounts[chain_id], chain),
                        ' ', escape(chain['code3'])]
                if link:
                    other = hash_to_address(chain['address_version'], binaddr)
                    if other != address:
                        ret[-1] = ['<a href="', page['dotdot'],
                                   'address/', other,
                                   '">', ret[-1], '</a>']
            return ret

        body += ['<p>Balance: '] + format_amounts(balance, True)

        for chain_id in chain_ids:
            balance[chain_id] = 0  # Reset for history traversal.

        body += ['<br />\n',
                 'Transactions in: ', count[0], '<br />\n',
                 'Received: ', format_amounts(received, False), '<br />\n',
                 'Transactions out: ', count[1], '<br />\n',
                 'Sent: ', format_amounts(sent, False), '<br />\n']

        body += ['</p>\n'
                 '<h3>Transactions</h3>\n'
                 '<table>\n<tr><th>Transaction</th><th>Block</th>'
                 '<th>Approx. Time</th><th>Amount</th><th>Balance</th>'
                 '<th>Currency</th></tr>\n']

        for elt in txpoints:
            chain = chains[elt['chain_id']]
            balance[elt['chain_id']] += elt['value']
            body += ['<tr><td><a href="../tx/', elt['tx_hash'],
                     '#', 'i' if elt['is_in'] else 'o', elt['pos'],
                     '">', elt['tx_hash'][:10], '...</a>',
                     '</td><td><a href="../block/', elt['blk_hash'],
                     '">', elt['height'], '</a></td><td>',
                     format_time(elt['nTime']), '</td><td>']
            if elt['value'] < 0:
                body += ['(', format_satoshis(elt['value'], chain), ')']
            else:
                body += [format_satoshis(elt['value'], chain)]
            body += ['</td><td>',
                     format_satoshis(balance[elt['chain_id']], chain),
                     '</td><td>', escape(chain['code3']),
                     '</td></tr>\n']
        body += ['</table>\n']

    def search_form(abe, page):
        q = (page['params'].get('q') or [''])[0]
        return [
            '<p>Search by address, block number, block or transaction hash,'
            ' or chain name:</p>\n'
            '<form action="', page['dotdot'], 'search"><p>\n'
            '<input name="q" size="64" value="', escape(q), '" />'
            '<button type="submit">Search</button>\n'
            '<br />Search does not yet support partial addresses.'
            ' Hash search requires at least the first six hex characters.'
            '</p></form>\n']

    def search(abe, page):
        page['title'] = 'Search'
        q = (page['params'].get('q') or [''])[0]
        if q == '':
            page['body'] = [
                '<p>Please enter search terms.</p>\n', abe.search_form(page)]
            return

        found = []
        if HEIGHT_RE.match(q):      found += abe.search_number(int(q))
        if ADDRESS_RE.match(q):     found += abe.search_address(q)
        if HASH_PREFIX_RE.match(q): found += abe.search_hash_prefix(q)
        found += abe.search_general(q)

        if not found:
            page['body'] = [
                '<p>No results found.</p>\n', abe.search_form(page)]
            return

        if len(found) == 1:
            # Undo shift_path_info.
            sn = posixpath.dirname(page['env']['SCRIPT_NAME'])
            if sn == '/': sn = ''
            page['env']['SCRIPT_NAME'] = sn
            page['env']['PATH_INFO'] = '/' + found[0]['uri']
            raise Redirect()

        body = page['body']
        body += ['<h3>Search Results</h3>\n<ul>\n']
        for result in found:
            body += [
                '<li><a href="', escape(result['uri']), '">',
                escape(result['name']), '</a></li>\n']
        body += ['</ul>\n']

    def search_number(abe, n):
        def process(row):
            (chain_name, dbhash, in_longest) = row
            hexhash = abe.store.hashout_hex(dbhash)
            if in_longest == 1:
                name = str(n)
            else:
                name = hexhash
            return {
                'name': chain_name + ' ' + name,
                'uri': 'block/' + hexhash,
                }

        return map(process, abe.store.selectall("""
            SELECT c.chain_name, b.block_hash, cc.in_longest
              FROM chain c
              JOIN chain_candidate cc USING (chain_id)
              JOIN block b USING (block_id)
             WHERE cc.block_height = ?
             ORDER BY c.chain_name, cc.in_longest DESC
        """, (n,)))

    def search_hash_prefix(abe, q):
        lo = abe.store.hashin_hex(q + '0' * (64 - len(q)))
        hi = abe.store.hashin_hex(q + 'f' * (64 - len(q)))
        ret = []
        for t in ('tx', 'block'):
            def process(row):
                hash = abe.store.hashout_hex(row[0])
                name = 'Transaction' if t == 'tx' else 'Block'
                return {
                    'name': name + ' ' + hash,
                    'uri': t + '/' + hash,
                    }
            ret += map(process, abe.store.selectall(
                "SELECT " + t + "_hash FROM " + t + " WHERE " + t +
                "_hash BETWEEN ? AND ? LIMIT 100",
                (lo, hi)))
        return ret

    def search_address(abe, address):
        try:
            binaddr = base58.bc_address_to_hash_160(address)
        except:
            return ()
        return ({ 'name': 'Address ' + address, 'uri': 'address/' + address },)

    def search_general(abe, q):
        """Search for something that is not an address, hash, or block number.
        Currently, this is limited to chain names and currency codes."""
        def process(row):
            (name, code3) = row
            return { 'name': name + ' (' + code3 + ')', 'uri': 'chain/' + name }
        return map(process, abe.store.selectall("""
            SELECT chain_name, chain_code3
              FROM chain
             WHERE UPPER(chain_name) LIKE '%' || ? || '%'
                OR UPPER(chain_code3) LIKE '%' || ? || '%'
        """, (q.upper(), q.upper())))

    def serve_static(abe, path, start_response):
        slen = len(abe.static_path)
        if path[:slen] != abe.static_path:
            raise PageNotFound()
        path = path[slen:]
        try:
            # Serve static content.
            # XXX Should check file modification time and handle HTTP
            # if-modified-since.  Or just hope serious users will map
            # our htdocs as static in their web server.
            # XXX is "+ pi" adequate for non-POSIX systems?
            found = open(abe.htdocs + '/' + path, "rb")
            import mimetypes
            (type, enc) = mimetypes.guess_type(path)
            # XXX Should do something with enc if not None.
            # XXX Should set Content-length.
            start_response('200 OK', [('Content-type', type or 'text/plain')])
            return found
        except IOError:
            raise PageNotFound()

def get_int_param(page, name):
    vals = page['params'].get(name)
    return vals and int(vals[0])

def format_time(nTime):
    import time
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(int(nTime)))

def format_satoshis(satoshis, chain):
    # XXX Should find COIN and LOG10COIN from chain.
    if satoshis is None:
        return ''
    if satoshis < 0:
        return '-' + format_satoshis(-satoshis, chain)
    integer = satoshis / COIN
    frac = satoshis % COIN
    return (str(integer) +
            ('.' + (('0' * LOG10COIN) + str(frac))[-LOG10COIN:])
            .rstrip('0').rstrip('.'))

def format_difficulty(diff):
    idiff = int(diff)
    ret = '.' + str(int(round((diff - idiff) * 1000)))
    while idiff > 999:
        ret = (' %03d' % (idiff % 1000,)) + ret
        idiff = idiff / 1000
    return str(idiff) + ret

def hash_to_address(version, hash):
    if hash is None:
        return 'UNKNOWN'
    vh = version + hash
    return base58.b58encode(vh + util.double_sha256(vh)[:4])

def decode_check_address(address):
    if ADDRESS_RE.match(address):
        bytes = base58.b58decode(address, 25)
        if bytes is not None:
            version = bytes[0]
            hash = bytes[1:21]
            if hash_to_address(version, hash) == address:
                return version, hash
    return None, None

def flatten(l):
    if isinstance(l, list):
        return ''.join(map(flatten, l))
    if l is None:
        raise Exception('NoneType in HTML conversion')
    return str(l)

def fix_path_info(env):
    pi = env['PATH_INFO']
    pi = posixpath.normpath(pi)
    if pi[-1] != '/' and env['PATH_INFO'][-1] == '/':
        pi += '/'
    if pi == env['PATH_INFO']:
        return False
    env['PATH_INFO'] = pi
    return True

def redirect(page):
    del(page['env']['QUERY_STRING'])
    uri = wsgiref.util.request_uri(page['env'])
    page['start_response'](
        '301 Moved Permanently',
        [('Location', uri),
         ('Content-Type', 'text/html')])
    return ('<html><head><title>Moved</title></head>\n'
            '<body><h1>Moved</h1><p>This page has moved to'
            '<a href="' + uri + '">' + uri + '</a></body></html>')

def serve(store):
    args = store.args
    abe = Abe(store, args)
    if args.host or args.port:
        # HTTP server.
        if args.host is None:
            args.host = "localhost"
        from wsgiref.simple_server import make_server
        port = int(args.port or 8888)
        httpd = make_server(args.host, port, abe)
        print "Serving HTTP..."
        try:
            httpd.serve_forever()
        except:
            httpd.shutdown()
            raise
    else:
        from flup.server.fcgi import WSGIServer
        WSGIServer(abe).run()

def parse_argv(argv):
    examples = (
        "PostgreSQL example:\n    --dbtype=psycopg2"
        " --connect-args='{\"database\":\"abe\"}' --binary-type hex\n\n"
        "Sqlite examle:\n    --dbtype=sqlite3 --connect-args='\"abe.sqlite\"'"
        " --binary-type buffer --int-type str\n\n"
        "To run an HTTP listener, supply either or both of HOST and PORT.\n"
        "By default, %(prog)s runs as a FastCGI service.  To disable this,\n"
        "pass --no-serve.")
    import argparse
    parser = argparse.ArgumentParser(
        description="Another Bitcoin block explorer.", epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter)
                                     
    parser.add_argument("--datadir", dest="datadirs", default=[],
                        metavar="DIR", action="append",
                        help="Look for block files (blk*.dat) in DIR."
                        " May be specified more than once.")
    parser.add_argument("--dbtype", "-d", dest="module", default=None,
                        help="DB-API driver module, by default `sqlite3'.")
    parser.add_argument("--connect-args", "-c", dest="connect_args",
                        default=None, metavar="JSON",
                        help="DB-API connect arguments formatted as a JSON"
                        " scalar, array, or object."
                        " If `--dbtype' is not supplied, this defaults to"
                        " `\":memory:\"'.")
    parser.add_argument("--binary-type", dest="binary_type",
                        choices=["buffer", "hex"],
                        help="Transform binary data to support a noncompliant"
                        " database or driver. Most database software is"
                        " noncompliant regarding binary data. `hex' stores"
                        " bytes as hex strings. `buffer' passes them as"
                        " Python buffer objects. Ignored for existing"
                        " databases.")
    parser.add_argument("--int-type", dest="int_type",
                        choices=["str"], help="Needed for drivers like"
                        " sqlite3 that give overflow errors when receiving"
                        " large values as Python integers")
    parser.add_argument("--port", dest="port", default=None, type=int,
                        help="TCP port on which to serve HTTP.")
    parser.add_argument("--host", dest="host", default=None,
                        help="Network interface for HTTP server.")
    parser.add_argument("--no-serve", dest="serve", default=True,
                        action="store_false",
                        help="Exit without handling HTTP or FastCGI requests.")
    parser.add_argument("--upgrade", dest="upgrade", default=False,
                        action="store_true",
                        help="Automatically upgrade database objects to"
                        " match software version.")
    parser.add_argument("--debug", dest="debug", default=False,
                        action="store_true",
                        help="Turn on miscellaneous output.")
                        
    args = parser.parse_args(argv)

    if not args.datadirs:
        args.datadirs = [util.determine_db_dir()]

    if args.module is None:
        args.module = "sqlite3"
        if args.connect_args is None:
            args.connect_args = '":memory:"'
        if args.binary_type is None:
            args.binary_type = "buffer"
        if args.int_type is None:
            args.binary_type = "str"
    args.module = __import__(args.module)
    if args.connect_args is not None:
        import json
        args.connect_args = json.loads(args.connect_args)

    return args

def main(argv):
    args = parse_argv(argv)
    store = make_store(args)
    if (args.serve):
        serve(store)
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
