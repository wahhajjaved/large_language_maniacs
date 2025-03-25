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

import os
import re
import binascii

# bitcointools -- modified deserialize.py to return raw transaction
import BCDataStream
import deserialize
import util

SCHEMA_VERSION = "Abe15"

WORK_BITS = 304  # XXX more than necessary.

BITCOIN_MAGIC = "\xf9\xbe\xb4\xd9"
BITCOIN_MAGIC_ID = 1
BITCOIN_POLICY_ID = 1
BITCOIN_CHAIN_ID = 1
BITCOIN_ADDRESS_VERSION = "\0"

TESTNET_MAGIC = "\xfa\xbf\xb5\xda"
TESTNET_MAGIC_ID = 2
TESTNET_POLICY_ID = 2
TESTNET_CHAIN_ID = 2
TESTNET_ADDRESS_VERSION = "\x6f"

NAMECOIN_MAGIC = "\xf9\xbe\xb4\xfe"
NAMECOIN_MAGIC_ID = 3
NAMECOIN_POLICY_ID = 3
NAMECOIN_CHAIN_ID = 3
NAMECOIN_ADDRESS_VERSION = "\x34"

GENESIS_HASH_PREV = "\0" * 32

SCRIPT_ADDRESS_RE = re.compile("\x76\xa9\x14(.{20})\x88\xac", re.DOTALL)
SCRIPT_PUBKEY_RE = re.compile("\x41(.{65})\xac", re.DOTALL)

class DataStore(object):

    """
    Bitcoin data storage class based on DB-API 2 and SQL1992 with
    workarounds to support SQLite3 and PostgreSQL/psycopg2.
    """

    def __init__(store, args):
        """
        Opens and stores a connection to the SQL database.

        args.dbtype should name a DB-API 2 driver module, e.g.,
        "sqlite3".

        args.connect_args should be an argument to the module's
        connect() method, or None for no argument, or a list of
        arguments, or a dictionary of named arguments.

        args.datadir names Bitcoin data directories containing
        blk0001.dat to scan for new blocks.
        """
        store.args = args
        store.module = __import__(args.dbtype)
        cargs = args.connect_args

        if cargs is None:
            conn = store.module.connect()
        else:
            if isinstance(cargs, dict):
                conn = store.module.connect(**cargs)
            elif isinstance(cargs, list):
                conn = store.module.connect(*cargs)
            else:
                conn = store.module.connect(cargs)

        store.conn = conn
        store.cursor = conn.cursor()
        store._ddl = store._get_ddl()

        # Read the CONFIG and CONFIGVAR tables if present.
        store.config = store._read_config()

        if store.config is None:
            store.initialize()
        elif store.config['schema_version'] != SCHEMA_VERSION:
            if args.upgrade:
                store._set_sql_flavour()
                import upgrade
                upgrade.upgrade_schema(store)
            else:
                raise Exception(
                    "Database schema version (%s) does not match software"
                    " (%s).  Please run with --upgrade to convert database."
                    % (store.config['schema_version'], SCHEMA_VERSION))

        store._set_sql_flavour()
        store._blocks = {}
        store._init_datadirs()

    def _read_config(store):
        # Read table CONFIGVAR if it exists.
        config = {}
        try:
            store.cursor.execute("""
                SELECT configvar_name, configvar_value
                  FROM configvar""")
            for row in store.cursor.fetchall():
                name, value = row
                config[name] = value
            if config:
                return config

        except store.module.DatabaseError:
            try:
                store.rollback()
            except:
                pass

        # Read legacy table CONFIG if it exists.
        try:
            store.cursor.execute("""
                SELECT schema_version, binary_type
                  FROM config
                 WHERE config_id = 1""")
            row = store.cursor.fetchone()
            sv, btype = row
            return { 'schema_version': sv, 'binary_type': btype }
        except:
            try:
                store.rollback()
            except:
                pass

        # Return None to indicate no schema found.
        return None

    # Accommodate SQL quirks.
    def _set_sql_flavour(store):
        def identity(x):
            return x
        transform = identity

        if store.module.paramstyle in ('format', 'pyformat'):
            transform = store._qmark_to_format(transform)
        elif store.module.paramstyle != 'qmark':
            warnings.warn("Database parameter style is " +
                          "%s, trying qmark" % module.paramstyle)
            pass

        # Binary I/O with the database.
        # Hashes are a special type; since the protocol treats them as
        # 256-bit integers and represents them as little endian, we
        # have to reverse them in hex to satisfy human expectations.
        def rev(x):
            return x[::-1]
        def to_hex(x):
            return None if x is None else binascii.hexlify(x)
        def from_hex(x):
            return None if x is None else binascii.unhexlify(x)
        def to_hex_rev(x):
            return None if x is None else binascii.hexlify(x[::-1])
        def from_hex_rev(x):
            return None if x is None else binascii.unhexlify(x)[::-1]

        btype = store.config.get('binary_type')

        if btype in (None, 'str'):
            binin       = identity
            binin_hex   = from_hex
            binout      = identity
            binout_hex  = to_hex
            hashin      = rev
            hashin_hex  = from_hex
            hashout     = rev
            hashout_hex = to_hex

        elif btype in ("buffer", "bytearray"):
            if btype == "buffer":
                def to_btype(x):
                    return None if x is None else buffer(x)
            else:
                def to_btype(x):
                    return None if x is None else bytearray(x)

            binin       = to_btype
            binin_hex   = lambda x: to_btype(from_hex(x))
            binout      = str
            binout_hex  = to_hex
            hashin      = lambda x: to_btype(rev(x))
            hashin_hex  = lambda x: to_btype(from_hex(x))
            hashout     = rev
            hashout_hex = to_hex

        elif btype == "hex":
            transform = store._sql_binary_as_hex(transform)
            binin       = to_hex
            binin_hex   = identity
            binout      = from_hex
            binout_hex  = identity
            hashin      = to_hex_rev
            hashin_hex  = identity
            hashout     = from_hex_rev
            hashout_hex = identity

        else:
            raise Exception("Unsupported binary-type %s" % btype)

        itype = store.config.get('int_type')

        if itype in (None, 'int'):
            intin = identity

        # Work around sqlite3's overflow when importing large ints.
        elif itype == 'str':
            intin = str
            transform = store._approximate_txout(transform)

        else:
            raise Exception("Unsupported int-type %s" % itype)

        stype = store.config.get('sequence_type')
        if stype in (None, 'update'):
            new_id = lambda key: store._new_id_update(key)

        else:
            raise Exception("Unsupported sequence-type %s" % stype)

        store.sql_transform = transform
        store._sql_cache = {}

        store.binin       = binin
        store.binin_hex   = binin_hex
        store.binout      = binout
        store.binout_hex  = binout_hex
        store.hashin      = hashin
        store.hashin_hex  = hashin_hex
        store.hashout     = hashout
        store.hashout_hex = hashout_hex

        # Might reimplement these someday...
        store.binout_int = lambda x: int(binout_hex(x), 16)
        store.binin_int = lambda x, bits: binin_hex(("%%0%dx" % (bits / 4)) % x)

        store.intin       = intin
        store.new_id      = new_id

    def sql(store, stmt, params=()):
        cached = store._sql_cache.get(stmt)
        if cached is None:
            cached = store.sql_transform(stmt)
            store._sql_cache[stmt] = cached
        store.cursor.execute(cached, params)

    # Convert standard placeholders to Python "format" style.
    def _qmark_to_format(store, fn):
        def ret(stmt):
            # XXX Simplified by assuming no literals contain "?".
            return fn(stmt.replace('%', '%%').replace("?", "%s"))
        return ret

    # Convert the standard BIT type to a hex string for databases
    # and drivers that don't support BIT.
    def _sql_binary_as_hex(store, fn):
        patt = re.compile("BIT((?: VARYING)?)\\(([0-9]+)\\)")
        def fixup(match):
            # XXX This assumes no string literals match.
            return (("VARCHAR(" if match.group(1) else "CHAR(") +
                    str(int(match.group(2)) / 4) + ")")
        def ret(stmt):
            # XXX This assumes no string literals match.
            return fn(patt.sub(fixup, stmt).replace("X'", "'"))
        return ret

    def _approximate_txout(store, fn):
        def ret(stmt):
            return fn(re.sub(
                    r'\btxout_value txout_approx_value\b',
                    'CAST(txout_value AS DOUBLE PRECISION) txout_approx_value',
                    stmt))
        return ret

    def selectrow(store, stmt, params=()):
        store.sql(stmt, params)
        return store.cursor.fetchone()

    def selectall(store, stmt, params=()):
        store.sql(stmt, params)
        return store.cursor.fetchall()

    def _init_datadirs(store):
        datadirs = {}
        for row in store.selectall("""
            SELECT dirname, blkfile_number, blkfile_offset, chain_id
              FROM datadir"""):
            dir, num, offs, chain_id = row
            datadirs[dir] = {
                "dirname": dir,
                "blkfile_number": int(num),
                "blkfile_offset": int(offs),
                "chain_id": None if chain_id is None else int(chain_id)}

        # By default, scan every dir we know.  This doesn't happen in
        # practise, because abe.py sets ~/.bitcoin as default datadir.
        if store.args.datadir is None:
            store.datadirs = datadirs.values()
            return

        store.datadirs = []
        for dircfg in store.args.datadir:
            if isinstance(dircfg, dict):
                dirname = dircfg.get('dirname')
                if dirname is None:
                    raise ValueError(
                        'Missing dirname in datadir configuration: '
                        + str(dircfg))
                if dirname in datadirs:
                    store.datadirs.append(datadirs[dirname])
                    continue

                chain_id = dircfg.get('chain_id')
                if chain_id is None:
                    chain_name = dircfg.get('chain')
                    row = store.selectrow(
                        "SELECT chain_id FROM chain WHERE chain_name = ?",
                        (chain_name,))
                    if row is not None:
                        chain_id = row[0]
                    elif chain_name is not None:
                        chain_id = store.new_id('chain')
                        code3 = dircfg.get('code3')
                        if code3 is None:
                            code3 = '000' if chain_id > 999 else "%03d" % (
                                chain_id,)
                        addr_vers = dircfg.get('address_version')
                        if addr_vers is None:
                            addr_vers = BITCOIN_ADDRESS_VERSION
                        store.sql("""
                            INSERT INTO chain (
                                chain_id, chain_name, chain_code3,
                                chain_address_version
                            ) VALUES (?, ?, ?, ?)""",
                                  (chain_id, chain_name, code3,
                                   store.binin(addr_vers)))
                        print "Assigned chain_id", chain_id, "to", chain_name

            elif dircfg in datadirs:
                store.datadirs.append(datadirs[dircfg])
                continue
            else:
                # Not a dict.  A string naming a directory holding
                # standard chains.
                dirname = dircfg
                chain_id = None

            store.datadirs.append({
                "dirname": dirname,
                "blkfile_number": 1,
                "blkfile_offset": 0,
                "chain_id": chain_id,
                })

    def _new_id_update(store, key):
        try:
            row = store.selectrow(
                "SELECT nextid FROM abe_sequences WHERE key = ?", (key,))
        except store.module.DatabaseError:
            store.rollback()
            store.sql(store._ddl['abe_sequences'])
            row = None
        if row is None:
            store.sql("INSERT INTO abe_sequences (key, nextid) VALUES (?, 1)",
                      (key,))
            ret = 1
        else:
            ret = int(row[0])
        store.sql("UPDATE abe_sequences SET nextid = nextid + 1 WHERE key = ?",
                  (key,))
        return ret

    def commit(store):
        store.conn.commit()

    def rollback(store):
        store.conn.rollback()

    def close(store):
        store.conn.close()

    def _get_ddl(store):
        return {
            "chain_summary":
# XXX I could do a lot with MATERIALIZED views.
"""CREATE VIEW chain_summary AS SELECT
    cc.chain_id,
    cc.in_longest,
    b.block_id,
    b.block_hash,
    b.block_version,
    b.block_hashMerkleRoot,
    b.block_nTime,
    b.block_nBits,
    b.block_nNonce,
    cc.block_height,
    b.prev_block_id,
    prev.block_hash prev_block_hash,
    b.block_chain_work,
    COUNT(DISTINCT bt.tx_id) num_tx,
    b.block_value_in,
    b.block_value_out,
    b.block_total_satoshis,
    b.block_total_seconds,
    b.block_satoshi_seconds,
    b.block_total_ss,
    SUM(bt.satoshi_seconds_destroyed) block_ss_destroyed
FROM chain_candidate cc
JOIN block b ON (cc.block_id = b.block_id)
LEFT JOIN block prev ON (b.prev_block_id = prev.block_id)
JOIN block_tx bt ON (bt.block_id = b.block_id)
JOIN txout USING (tx_id)
GROUP BY
    cc.chain_id,
    cc.in_longest,
    b.block_id,
    b.block_hash,
    b.block_version,
    b.block_hashMerkleRoot,
    b.block_nTime,
    b.block_nBits,
    b.block_nNonce,
    cc.block_height,
    b.prev_block_id,
    prev.block_hash,
    b.block_chain_work,
    b.block_value_in,
    b.block_value_out,
    b.block_total_satoshis,
    b.block_total_seconds,
    b.block_satoshi_seconds,
    b.block_total_ss""",

            "txout_detail":
"""CREATE VIEW txout_detail AS SELECT
    cc.chain_id,
    cc.in_longest,
    cc.block_id,
    b.block_hash,
    b.block_height,
    block_tx.tx_pos,
    tx.tx_id,
    tx.tx_hash,
    tx.tx_lockTime,
    tx.tx_version,
    tx.tx_size,
    txout.txout_id,
    txout.txout_pos,
    txout.txout_value,
    txout.txout_scriptPubKey,
    pubkey.pubkey_id,
    pubkey.pubkey_hash,
    pubkey.pubkey
  FROM chain_candidate cc
  JOIN block b ON (cc.block_id = b.block_id)
  JOIN block_tx ON (b.block_id = block_tx.block_id)
  JOIN tx    ON (tx.tx_id = block_tx.tx_id)
  JOIN txout ON (tx.tx_id = txout.tx_id)
  LEFT JOIN pubkey USING (pubkey_id)""",

            "txin_detail":
"""CREATE VIEW txin_detail AS SELECT
    cc.chain_id,
    cc.in_longest,
    cc.block_id,
    b.block_hash,
    b.block_height,
    block_tx.tx_pos,
    tx.tx_id,
    tx.tx_hash,
    tx.tx_lockTime,
    tx.tx_version,
    tx.tx_size,
    txin.txin_id,
    txin.txin_pos,
    txin.txout_id prevout_id,
    txin.txin_scriptSig,
    txin.txin_sequence,
    prevout.txout_value txin_value,
    pubkey.pubkey_id,
    pubkey.pubkey_hash,
    pubkey.pubkey
  FROM chain_candidate cc
  JOIN block b ON (cc.block_id = b.block_id)
  JOIN block_tx ON (b.block_id = block_tx.block_id)
  JOIN tx    ON (tx.tx_id = block_tx.tx_id)
  JOIN txin  ON (tx.tx_id = txin.tx_id)
  LEFT JOIN txout prevout ON (txin.txout_id = prevout.txout_id)
  LEFT JOIN pubkey
      ON (prevout.pubkey_id = pubkey.pubkey_id)""",

            "txout_approx":
# View of txout for drivers like sqlite3 that can not handle large
# integer arithmetic.  For them, we transform the definition of
# txout_approx_value to DOUBLE PRECISION (approximate) by a CAST.
"""CREATE VIEW txout_approx AS SELECT
    txout_id,
    tx_id,
    txout_value txout_approx_value
  FROM txout""",

            "configvar":
# ABE accounting.  This table is read without knowledge of the
# database's SQL quirks, so it must use only the most widely supported
# features.
"""CREATE TABLE configvar (
    configvar_name  VARCHAR(100) PRIMARY KEY,
    configvar_value VARCHAR(255)
)""",

            "abe_sequences":
"""CREATE TABLE abe_sequences (
    key VARCHAR(100) PRIMARY KEY,
    nextid NUMERIC(30)
)""",
            }

    def initialize(store):
        """
        Create the database schema.
        """
        store.configure()

        for stmt in (

store._ddl['configvar'],

"""CREATE TABLE datadir (
    dirname     VARCHAR(32767) PRIMARY KEY,
    blkfile_number NUMERIC(4),
    blkfile_offset NUMERIC(20),
    chain_id    NUMERIC(10) NULL
)""",

# MAGIC lists the magic numbers seen in messages and block files, known
# in the original Bitcoin source as `pchMessageStart'.
"""CREATE TABLE magic (
    magic_id    NUMERIC(10) PRIMARY KEY,
    magic       BIT(32)     UNIQUE NOT NULL,
    magic_name  VARCHAR(100) UNIQUE NOT NULL
)""",

# POLICY identifies a block acceptance policy.
"""CREATE TABLE policy (
    policy_id   NUMERIC(10) PRIMARY KEY,
    policy_name VARCHAR(100) UNIQUE NOT NULL
)""",

# A block of the type used by Bitcoin.
"""CREATE TABLE block (
    block_id      NUMERIC(14) PRIMARY KEY,
    block_hash    BIT(256)    UNIQUE NOT NULL,
    block_version NUMERIC(10),
    block_hashMerkleRoot BIT(256),
    block_nTime   NUMERIC(20),
    block_nBits   NUMERIC(10),
    block_nNonce  NUMERIC(10),
    block_height  NUMERIC(14),
    prev_block_id NUMERIC(14) NULL,
    block_chain_work BIT(""" + str(WORK_BITS) + """),
    block_value_in NUMERIC(30),
    block_value_out NUMERIC(30),
    block_total_satoshis NUMERIC(26),
    block_total_seconds NUMERIC(20),
    block_satoshi_seconds NUMERIC(28),
    block_total_ss NUMERIC(28),
    FOREIGN KEY (prev_block_id)
        REFERENCES block (block_id)
)""",

# CHAIN comprises a magic number, a policy, and (indirectly via
# CHAIN_LAST_BLOCK_ID and the referenced block's ancestors) a genesis
# block, possibly null.  A chain may have a currency code.
"""CREATE TABLE chain (
    chain_id    NUMERIC(10) PRIMARY KEY,
    magic_id    NUMERIC(10) NULL,
    policy_id   NUMERIC(10) NULL,
    chain_name  VARCHAR(100) UNIQUE NOT NULL,
    chain_code3 CHAR(3)     NULL,
    chain_address_version BIT VARYING(800) NOT NULL,
    chain_last_block_id NUMERIC(14) NULL,
    FOREIGN KEY (magic_id)  REFERENCES magic (magic_id),
    FOREIGN KEY (policy_id) REFERENCES policy (policy_id),
    FOREIGN KEY (chain_last_block_id)
        REFERENCES block (block_id)
)""",

# CHAIN_CANDIDATE lists blocks that are, or might become, part of the
# given chain.  IN_LONGEST is 1 when the block is in the chain, else 0.
# IN_LONGEST denormalizes information stored canonically in
# CHAIN.CHAIN_LAST_BLOCK_ID and BLOCK.PREV_BLOCK_ID.
"""CREATE TABLE chain_candidate (
    chain_id      NUMERIC(10),
    block_id      NUMERIC(14),
    in_longest    NUMERIC(1),
    block_height  NUMERIC(14),
    PRIMARY KEY (chain_id, block_id),
    FOREIGN KEY (block_id) REFERENCES block (block_id)
)""",
"""CREATE INDEX x_cc_block ON chain_candidate (block_id)""",
"""CREATE INDEX x_cc_chain_block_height
    ON chain_candidate (chain_id, block_height)""",
"""CREATE INDEX x_cc_block_height ON chain_candidate (block_height)""",

# An orphan block must remember its hashPrev.
"""CREATE TABLE orphan_block (
    block_id      NUMERIC(14) PRIMARY KEY,
    block_hashPrev BIT(256)   NOT NULL,
    FOREIGN KEY (block_id) REFERENCES block (block_id)
)""",
"""CREATE INDEX x_orphan_block_hashPrev ON orphan_block (block_hashPrev)""",

# Denormalize the relationship inverse to BLOCK.PREV_BLOCK_ID.
"""CREATE TABLE block_next (
    block_id      NUMERIC(14),
    next_block_id NUMERIC(14),
    PRIMARY KEY (block_id, next_block_id),
    FOREIGN KEY (block_id) REFERENCES block (block_id),
    FOREIGN KEY (next_block_id) REFERENCES block (block_id)
)""",

# A transaction of the type used by Bitcoin.
"""CREATE TABLE tx (
    tx_id         NUMERIC(26) PRIMARY KEY,
    tx_hash       BIT(256)    UNIQUE NOT NULL,
    tx_version    NUMERIC(10),
    tx_lockTime   NUMERIC(10),
    tx_size       NUMERIC(10)
)""",

# Presence of transactions in blocks is many-to-many.
"""CREATE TABLE block_tx (
    block_id      NUMERIC(14),
    tx_id         NUMERIC(26),
    tx_pos        NUMERIC(10) NOT NULL,
    satoshi_seconds_destroyed NUMERIC(28),
    PRIMARY KEY (block_id, tx_id),
    UNIQUE (block_id, tx_pos),
    FOREIGN KEY (block_id)
        REFERENCES block (block_id),
    FOREIGN KEY (tx_id)
        REFERENCES tx (tx_id)
)""",
"""CREATE INDEX x_block_tx_tx ON block_tx (tx_id)""",

# A transaction out-point.
"""CREATE TABLE txout (
    txout_id      NUMERIC(26) PRIMARY KEY,
    tx_id         NUMERIC(26),
    txout_pos     NUMERIC(10),
    txout_value   NUMERIC(30) NOT NULL,
    txout_scriptPubKey BIT VARYING(80000),
    pubkey_id     NUMERIC(26),
    UNIQUE (tx_id, txout_pos)
)""",
"""CREATE INDEX x_txout_pubkey ON txout (pubkey_id)""",

# A transaction in-point.
"""CREATE TABLE txin (
    txin_id       NUMERIC(26) PRIMARY KEY,
    tx_id         NUMERIC(26) NOT NULL,
    txin_pos      NUMERIC(10) NOT NULL,
    txout_id      NUMERIC(26),
    txin_scriptSig BIT VARYING(80000),
    txin_sequence NUMERIC(10),
    UNIQUE (tx_id, txin_pos),
    FOREIGN KEY (tx_id)
        REFERENCES tx (tx_id)
)""",

# While TXIN.TXOUT_ID can not be found, we must remember TXOUT_POS,
# a.k.a. PREVOUT_N.
"""CREATE TABLE unlinked_txin (
    txin_id       NUMERIC(26) PRIMARY KEY,
    txout_tx_hash BIT(256)    NOT NULL,
    txout_pos     NUMERIC(10) NOT NULL,
    FOREIGN KEY (txin_id) REFERENCES txin (txin_id)
)""",
"""CREATE INDEX x_unlinked_txin_outpoint
    ON unlinked_txin (txout_tx_hash, txout_pos)""",

"""CREATE TABLE block_txin (
    block_id      NUMERIC(14) NOT NULL,
    txin_id       NUMERIC(26) NOT NULL,
    out_block_id  NUMERIC(14) NOT NULL,
    PRIMARY KEY (block_id, txin_id),
    FOREIGN KEY (block_id) REFERENCES block (block_id),
    FOREIGN KEY (txin_id) REFERENCES txin (txin_id),
    FOREIGN KEY (out_block_id) REFERENCES block (block_id)
)""",

# A public key for sending bitcoins.  PUBKEY_HASH is derivable from a
# Bitcoin or Testnet address.
"""CREATE TABLE pubkey (
    pubkey_id     NUMERIC(26) PRIMARY KEY,
    pubkey_hash   BIT(160)    UNIQUE NOT NULL,
    pubkey        BIT(520)    UNIQUE NULL
)""",

store._ddl['chain_summary'],
store._ddl['txout_detail'],
store._ddl['txin_detail'],
store._ddl['txout_approx'],
):
            try:
                store.sql(stmt)
            except:
                print "Failed:", stmt
                raise

        ins_magic = """INSERT INTO magic (magic_id, magic, magic_name)
            VALUES (?, ?, ?)"""
        ins_policy = """INSERT INTO policy (policy_id, policy_name)
            VALUES (?, ?)"""
        ins_chain = """
            INSERT INTO chain (
                chain_id, magic_id, policy_id, chain_name, chain_code3,
                chain_address_version
            ) VALUES (?, ?, ?, ?, ?, ?)"""

        # Some public data.
        store.sql(ins_magic, (BITCOIN_MAGIC_ID, store.binin(BITCOIN_MAGIC),
                              "Bitcoin"))
        store.sql(ins_magic, (TESTNET_MAGIC_ID, store.binin(TESTNET_MAGIC),
                              "Testnet"))
        store.sql(ins_magic, (NAMECOIN_MAGIC_ID,
                              store.binin(NAMECOIN_MAGIC), "Namecoin"))
        store.sql(ins_policy, (BITCOIN_POLICY_ID, "Bitcoin policy"))
        store.sql(ins_policy, (TESTNET_POLICY_ID, "Testnet policy"))
        store.sql(ins_policy, (NAMECOIN_POLICY_ID, "Namecoin policy"))
        store.sql(ins_chain,
                  (BITCOIN_CHAIN_ID, BITCOIN_MAGIC_ID, BITCOIN_POLICY_ID,
                   'Bitcoin', 'BTC', store.binin(BITCOIN_ADDRESS_VERSION)))
        store.sql(ins_chain,
                  (TESTNET_CHAIN_ID, TESTNET_MAGIC_ID, TESTNET_POLICY_ID,
                   'Testnet', 'BC0', store.binin(TESTNET_ADDRESS_VERSION)))
        store.sql(ins_chain,
                  (NAMECOIN_CHAIN_ID, NAMECOIN_MAGIC_ID, NAMECOIN_POLICY_ID,
                   'Namecoin', 'NMC', store.binin(NAMECOIN_ADDRESS_VERSION)))

        store.save_config()
        store.commit()
        store.config['schema_version'] = SCHEMA_VERSION

    def configure(store):
        store.config = {}

        for btype in (
            ['str', 'bytearray', 'buffer', 'hex', '']
            if store.args.binary_type is None else
            [ store.args.binary_type, '' ]):

            if btype == '':
                raise Exception(
                    "No known binary data representation works"
                    if store.args.binary_type is None else
                    "Binary type " + store.args.binary_type + " fails test")
            store.config['binary_type'] = btype
            store._set_sql_flavour()
            if store._test_binary_type():
                print "binary_type=%s" % (btype,)
                break

        for itype in ['int', 'str', '']:
            if itype == '':
                raise Exception(
                    "No known large integer representation works")
            store.config['int_type'] = itype
            store._set_sql_flavour()
            if store._test_int_type():
                print "int_type=%s" % (itype,)
                break

        for stype in ['update', '']:
            if stype == '':
                raise Exception(
                    "No known sequence type works")
            store.config['sequence_type'] = stype
            store._set_sql_flavour()
            if store._test_sequence_type():
                print "sequence_type=%s" % (stype,)
                break

    def _drop_if_exists(store, otype, name):
        try:
            store.sql("DROP " + otype + " " + name)
        except store.module.DatabaseError:
            store.rollback()

    def _drop_table_if_exists(store, obj):
        store._drop_if_exists("TABLE", obj)
    def _drop_view_if_exists(store, obj):
        store._drop_if_exists("VIEW", obj)
    def _drop_sequence_if_exists(store, obj):
        store._drop_if_exists("SEQUENCE", obj)

    def _test_binary_type(store):
        store._drop_table_if_exists("abe_test_1")
        try:
            store.sql(
                "CREATE TABLE abe_test_1 (test_id NUMERIC(2) PRIMARY KEY,"
                " test_bit BIT(256), test_varbit BIT VARYING(80000))")
            val = str(''.join(map(chr, range(32))))
            store.sql("INSERT INTO abe_test_1 (test_id, test_bit, test_varbit)"
                      " VALUES (?, ?, ?)",
                      (1, store.hashin(val), store.binin(val)))
            (bit, vbit) = store.selectrow(
                "SELECT test_bit, test_varbit FROM abe_test_1")
            if store.hashout(bit) != val:
                return False
            if store.binout(vbit) != val:
                return False
            return True
        except store.module.DatabaseError, e:
            store.rollback()
            return False
        except Exception, e:
            print "_test_binary_type:", store.config['binary_type'] + ":", e
            store.rollback()
            return False
        finally:
            store._drop_table_if_exists("abe_test_1")

    def _test_int_type(store):
        store._drop_table_if_exists("abe_test_1")
        store._drop_view_if_exists("abe_test_v1")
        try:
            store.sql(
                "CREATE TABLE abe_test_1 (test_id NUMERIC(2) PRIMARY KEY,"
                " txout_value NUMERIC(30), i2 NUMERIC(20))")
            store.sql(
                "CREATE VIEW abe_test_v1 AS SELECT test_id,"
                " txout_value txout_approx_value, i2 FROM abe_test_1")
            v1 = 1234567890123456789
            v2 = 1234567890
            store.sql("INSERT INTO abe_test_1 (test_id, txout_value, i2)"
                      " VALUES (?, ?, ?)",
                      (1, store.intin(v1), v2))
            (prod,) = store.selectrow(
                "SELECT txout_approx_value * i2 FROM abe_test_v1")
            prod = int(prod)
            if prod < v1 * v2 * 1.0001 and prod > v1 * v2 * 0.9999:
                return True
            return False
        except store.module.DatabaseError, e:
            store.rollback()
            return False
        except Exception, e:
            print "_test_int_type:", store.config['int_type'] + ":", e
            store.rollback()
            return False
        finally:
            store._drop_table_if_exists("abe_test_1")
            store._drop_view_if_exists("abe_test_v1")

    def _test_sequence_type(store):
        store._drop_table_if_exists("abe_test_1")
        try:
            store.sql(
                "CREATE TABLE abe_test_1 ("
                " abe_test_1_id NUMERIC(12) PRIMARY KEY,"
                " foo VARCHAR(10))")
            id1 = store.new_id('abe_test_1')
            id2 = store.new_id('abe_test_1')
            if int(id1) != int(id2):
                return True
            return False
        except store.module.DatabaseError, e:
            store.rollback()
            return False
        except Exception, e:
            print "_test_sequence_type:", store.config['sequence_type'] + ":", e
            store.rollback()
            return False
        finally:
            store._drop_table_if_exists("abe_test_1")

    def save_config(store):
        store.insert_configvar('schema_version', SCHEMA_VERSION)
        for name, value in store.config.items():
            store.insert_configvar(name, value)

    def insert_configvar(store, name, value):
        store.sql("INSERT INTO configvar (configvar_name, configvar_value)"
                  " VALUES (?, ?)", (name, value))

    def _get_block(store, block_id):
        return store._blocks.get(int(block_id))

    def _put_block(store, block_id, prev_id, height):
        block = {
            'prev_id': None if prev_id is None else int(prev_id),
            'height':  None if height  is None else int(height),
            'in_longest_chains': set()}
        store._blocks[int(block_id)] = block
        return block

    def _load_block(store, block_id):
        block = store._get_block(block_id)
        if block is None:
            row = store.selectrow("""
                SELECT prev_block_id, block_height
                  FROM block
                 WHERE block_id = ?""", (block_id,))
            if row is None:
                return None
            prev_id, height = row
            block = store._put_block(block_id, prev_id, height)
            for row in store.selectall("""
                SELECT chain_id
                  FROM chain_candidate
                 WHERE block_id = ? AND in_longest = 1""", (block_id,)):
                (chain_id,) = row
                store._add_block_chain(block_id, chain_id)
        return block

    def _update_block(store, block_id, prev_id, height):
        block = store._get_block(block_id)
        if block:
            block['prev_id'] = int(prev_id)
            block['height'] = int(height)

    def _add_block_chain(store, block_id, chain_id):
        block = store._get_block(block_id)
        if block:
            block['in_longest_chains'].add(int(chain_id))

    def _remove_block_chain(store, block_id, chain_id):
        block = store._get_block(block_id)
        if block:
            block['in_longest_chains'].remove(int(chain_id))

    def is_descended_from(store, block_id, ancestor_id):
#        ret = store._is_descended_from(block_id, ancestor_id)
#        print block_id, "is" + ('' if ret else ' NOT'), "descended from", ancestor_id
#        return ret
#    def _is_descended_from(store, block_id, ancestor_id):
        if block_id == ancestor_id:
            return True
        block = store._load_block(block_id)
        if block['prev_id'] == ancestor_id:
            return True
        ancestor = store._load_block(ancestor_id)
        chains = ancestor['in_longest_chains']
        while True:
            #print "is_descended_from", ancestor_id, block
            if chains.intersection(block['in_longest_chains']):
                return ancestor['height'] <= block['height']
            if block['in_longest_chains'] - chains:
                return False
            if block['prev_id'] is None:
                return None
            block = store._load_block(block['prev_id'])
            if block['prev_id'] == ancestor_id:
                return True
            if block['height'] <= ancestor['height']:
                return False

    def contains_block(store, hash):
        return store.block_hash_to_id(hash)

    def block_hash_to_id(store, hash):
        row = store.selectrow("SELECT block_id FROM block WHERE block_hash = ?",
                              (store.hashin(hash),))
        return row[0] if row else row

    def find_prev(store, hash):
        row = store.selectrow("""
            SELECT block_id, block_height, block_chain_work,
                   block_total_satoshis, block_total_seconds,
                   block_satoshi_seconds, block_total_ss, block_nTime
              FROM block
             WHERE block_hash=?""", (store.hashin(hash),))
        if row is None:
            return (None, None, None, None, None, None, None, None)
        (id, height, chain_work, satoshis, seconds, satoshi_seconds,
         total_ss, nTime) = row
        return (id, None if height is None else int(height),
                store.binout_int(chain_work),
                None if satoshis is None else int(satoshis),
                None if seconds is None else int(seconds),
                None if satoshi_seconds is None else int(satoshi_seconds),
                None if total_ss is None else int(total_ss),
                int(nTime))

    def import_block(store, b):

        # Get a new block ID.
        block_id = store.new_id("block")
        b['block_id'] = block_id

        # Import new transactions.
        b['value_in'] = 0
        b['value_out'] = 0
        for pos in xrange(len(b['transactions'])):
            tx = b['transactions'][pos]
            if 'hash' not in tx:
                tx['hash'] = util.double_sha256(tx['tx'])
            tx['tx_id'] = (store.tx_find_id_and_value(tx) or
                           store.import_tx(tx, pos == 0))
            b['value_in'] += tx['value_in']
            b['value_out'] += tx['value_out']

        # Look for the parent block.
        hashPrev = b['hashPrev']
        is_genesis = hashPrev == GENESIS_HASH_PREV
        (prev_block_id, prev_height, prev_work, prev_satoshis,
         prev_seconds, prev_ss, prev_total_ss, prev_nTime) = (
            (None, -1, 0, 0, 0, 0, 0, b['nTime'])
            if is_genesis else
            store.find_prev(hashPrev))

        b['prev_block_id'] = prev_block_id
        b['height'] = None if prev_height is None else prev_height + 1
        b['chain_work'] = util.calculate_work(prev_work, b['nBits'])

        store._put_block(block_id, prev_block_id, b['height'])

        b['seconds'] = prev_seconds + b['nTime'] - prev_nTime
        b['satoshis'] = prev_satoshis + b['value_out'] - b['value_in']

        # Insert the block table row.
        store.sql(
            """INSERT INTO block (
                block_id, block_hash, block_version, block_hashMerkleRoot,
                block_nTime, block_nBits, block_nNonce, block_height,
                prev_block_id, block_chain_work, block_value_in,
                block_value_out, block_total_satoshis,
                block_total_seconds, block_satoshi_seconds,
                block_total_ss
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL
            )""",  # XXX NULLs
            (block_id, store.hashin(b['hash']), b['version'],
             store.hashin(b['hashMerkleRoot']), b['nTime'],
             b['nBits'], b['nNonce'], b['height'], prev_block_id,
             store.binin_int(b['chain_work'], WORK_BITS),
             b['value_in'], b['value_out'], b['satoshis'], b['seconds']))

        # List the block's transactions in block_tx.
        for tx_pos in xrange(len(b['transactions'])):
            tx = b['transactions'][tx_pos]
            store.sql("""
                INSERT INTO block_tx
                    (block_id, tx_id, tx_pos)
                VALUES (?, ?, ?)""",
                      (block_id, tx['tx_id'], tx_pos))
            print "block_tx", block_id, tx['tx_id']

        # Create rows in block_txin.
        for row in store.selectall("""
            SELECT txin.txin_id, obt.block_id
              FROM block_tx bt
              JOIN txin USING (tx_id)
              JOIN txout USING (txout_id)
              JOIN block_tx obt ON (txout.tx_id = obt.tx_id)
             WHERE bt.block_id = ?""", (block_id,)):
            (txin_id, oblock_id) = row
            if store.is_descended_from(block_id, oblock_id):
                store.sql("""
                    INSERT INTO block_txin (block_id, txin_id, out_block_id)
                    VALUES (?, ?, ?)""",
                          (block_id, txin_id, oblock_id))

        ss_destroyed = store._get_block_ss_destroyed(
            block_id, b['nTime'],
            map(lambda tx: tx['tx_id'], b['transactions']))

        if prev_satoshis is not None:
            ss_created = prev_satoshis * (b['nTime'] - prev_nTime)
            b['ss'] = prev_ss + ss_created - ss_destroyed
            b['total_ss'] = prev_total_ss + ss_created

            store.sql("""
                UPDATE block
                   SET block_satoshi_seconds = ?,
                       block_total_ss = ?
                 WHERE block_id = ?""",
                      (store.intin(b['ss']),
                       store.intin(b['total_ss']),
                       block_id))

        # Store the inverse hashPrev relationship or mark the block as
        # an orphan.
        if prev_block_id:
            store.sql("""
                INSERT INTO block_next (block_id, next_block_id)
                VALUES (?, ?)""", (prev_block_id, block_id))
        elif not is_genesis:
            store.sql("INSERT INTO orphan_block (block_id, block_hashPrev)" +
                      " VALUES (?, ?)", (block_id, store.hashin(b['hashPrev'])))

        for row in store.selectall("""
            SELECT block_id FROM orphan_block WHERE block_hashPrev = ?""",
                                   (store.hashin(b['hash']),)):
            (orphan_id,) = row
            store.sql("UPDATE block SET prev_block_id = ? WHERE block_id = ?",
                      (block_id, orphan_id))
            store.sql("""
                INSERT INTO block_next (block_id, next_block_id)
                VALUES (?, ?)""", (block_id, orphan_id))
            store.sql("DELETE FROM orphan_block WHERE block_id = ?",
                      (orphan_id,))

        b['top'], new_work = store.adopt_orphans(b, 0)

        return block_id

    def _get_block_ss_destroyed(store, block_id, nTime, tx_ids):
        block_ss_destroyed = 0
        for tx_id in tx_ids:
            destroyed = int(store.selectrow("""
                SELECT COALESCE(SUM(txout_approx.txout_approx_value *
                                    (? - b.block_nTime)), 0)
                  FROM block_txin bti
                  JOIN txin USING (txin_id)
                  JOIN txout_approx USING (txout_id)
                  JOIN block_tx obt ON (txout_approx.tx_id = obt.tx_id)
                  JOIN block b ON (obt.block_id = b.block_id)
                 WHERE bti.block_id = ? AND txin.tx_id = ?""",
                                            (nTime, block_id, tx_id))[0])
            block_ss_destroyed += destroyed
            store.sql("""
                UPDATE block_tx
                   SET satoshi_seconds_destroyed = ?
                 WHERE block_id = ?
                   AND tx_id = ?""",
                      (store.intin(destroyed), block_id, tx_id))
        return block_ss_destroyed

    # Propagate cumulative values to descendant blocks.  Return info
    # about the longest chain rooted at b.
    def adopt_orphans(store, b, orphan_work):
        block_id = b['block_id']
        next_blocks = store.find_next_blocks(block_id)
        if not next_blocks:
            return b, orphan_work

        height = None if b['height'] is None else b['height'] + 1
        best = None
        best_work = orphan_work

        for row in store.selectall("""
            SELECT bn.next_block_id, b.block_nBits,
                   b.block_value_out - b.block_value_in, block_nTime
              FROM block_next bn
              JOIN block b ON (bn.next_block_id = b.block_id)
             WHERE bn.block_id = ?""", (block_id,)):
            next_id, nBits, generated, nTime = row
            nBits = int(nBits)
            generated = None if generated is None else int(generated)
            nTime = int(nTime)
            new_work = util.calculate_work(orphan_work, nBits)

            if b['chain_work'] is None:
                chain_work = None
            else:
                chain_work = b['chain_work'] + new_work - orphan_work

            if b['seconds'] is None:
                seconds = None
            else:
                seconds = b['seconds'] + nTime - b['nTime']

            if b['satoshis'] is None or generated is None:
                satoshis = None
            else:
                satoshis = b['satoshis'] + generated

            if b['ss'] is None or b['satoshis'] is None or b['seconds'] is None:
                ss = None
            else:
                tx_ids = map(
                    lambda row: row[0],
                    store.selectall("""
                        SELECT tx_id
                          FROM block_tx
                         WHERE block_id = ?""", (next_id,)))
                destroyed = store._get_block_ss_destroyed(
                    next_id, nTime, tx_ids)
                ss = b['ss'] + b['satoshis'] * (nTime - b['nTime']) - destroyed

            store.sql("""
                UPDATE block
                   SET block_height = ?,
                       block_chain_work = ?,
                       block_total_seconds = ?,
                       block_total_satoshis = ?,
                       block_satoshi_seconds = ?
                 WHERE block_id = ?""",
                      (height, chain_work, seconds, satoshis,
                       store.intin(ss), next_id))
            store._update_block(next_id, block_id, height)

            if height is not None:
                store.sql("""
                    UPDATE chain_candidate SET block_height = ?
                     WHERE block_id = ?""",
                    (height, next_id))

            nb = {
                "block_id": next_id,
                "height": height,
                "chain_work": chain_work,
                "nTime": nTime,
                "seconds": seconds,
                "satoshis": satoshis,
                "ss": ss}
            ret, work = store.adopt_orphans(nb, new_work)

            if work > best_work:
                best = ret
                best_work = work

        return best, best_work

    def tx_find_id_and_value(store, tx):
        row = store.selectrow("""
            SELECT tx_id, SUM(txout.txout_value)
              FROM tx
              LEFT JOIN txout USING (tx_id)
             WHERE tx_hash = ?
             GROUP BY tx_id""",
                              (store.hashin(tx['hash']),))
        if row:
            tx_id, value_out = row
            (value_in,) = store.selectrow("""
                SELECT SUM(prevout.txout_value)
                  FROM txin
                  JOIN txout prevout USING (txout_id)
                 WHERE txin.tx_id = ?""", (tx_id,))
            tx['value_in'] = 0 if value_in is None else int(value_in)
            tx['value_out'] = 0 if value_out is None else int(value_out)
            return tx_id

        return None

    def import_tx(store, tx, is_coinbase):
        tx_id = store.new_id("tx")
        dbhash = store.hashin(tx['hash'])
        store.sql("""
            INSERT INTO tx (tx_id, tx_hash, tx_version, tx_lockTime, tx_size)
            VALUES (?, ?, ?, ?, ?)""",
                  (tx_id, dbhash, tx['version'], tx['lockTime'], len(tx['tx'])))

        # Import transaction outputs.
        tx['value_out'] = 0
        for pos in xrange(len(tx['txOut'])):
            txout = tx['txOut'][pos]
            tx['value_out'] += txout['value']
            txout_id = store.new_id("txout")

            pubkey_id = None
            match = SCRIPT_ADDRESS_RE.match(txout['scriptPubKey'])
            if match:
                pubkey_id = store.pubkey_hash_to_id(match.group(1))
            else:
                match = SCRIPT_PUBKEY_RE.match(txout['scriptPubKey'])
                if match:
                    pubkey_id = store.pubkey_to_id(match.group(1))

            store.sql("""
                INSERT INTO txout (
                    txout_id, tx_id, txout_pos, txout_value,
                    txout_scriptPubKey, pubkey_id
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                      (txout_id, tx_id, pos, txout['value'],
                       store.binin(txout['scriptPubKey']), pubkey_id))
            store.sql("""
                UPDATE txin
                   SET txout_id = ?
                 WHERE EXISTS (
                    SELECT 1
                      FROM unlinked_txin utxin
                     WHERE txin.txin_id = utxin.txin_id
                       AND txout_tx_hash = ?
                       AND txout_pos = ?)""",
                      (txout_id, dbhash, pos))
            if (store.cursor.rowcount or 0) > 0:
                store.sql("""
                    DELETE FROM unlinked_txin
                     WHERE txout_tx_hash = ? AND txout_pos = ?)""",
                      (dbhash, pos))

        # Import transaction inputs.
        tx['value_in'] = 0
        for pos in xrange(len(tx['txIn'])):
            txin = tx['txIn'][pos]
            txin_id = store.new_id("txin")

            if is_coinbase:
                txout_id = None
            else:
                txout_id, value = store.lookup_txout(
                    txin['prevout_hash'], txin['prevout_n'])
                tx['value_in'] += value

            store.sql("""
                INSERT INTO txin (
                    txin_id, tx_id, txin_pos, txout_id,
                    txin_scriptSig, txin_sequence
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                      (txin_id, tx_id, pos, txout_id,
                       store.binin(txin['scriptSig']), txin['sequence']))
            if not is_coinbase and txout_id is None:
                store.sql("""
                    INSERT INTO unlinked_txin (
                        txin_id, txout_tx_hash, txout_pos
                    ) VALUES (?, ?, ?)""",
                          (txin_id, store.hashin(txin['prevout_hash']),
                           txin['prevout_n']))

        # XXX Could populate PUBKEY.PUBKEY with txin scripts...
        # or leave that to an offline process.  Nothing in this program
        # requires them.
        return tx_id

    # Called to indicate that the given block has the correct magic
    # number and policy for the given chain.  Updates CHAIN_CANDIDATE
    # and CHAIN.CHAIN_LAST_BLOCK_ID as appropriate.
    def offer_block_to_chain(store, b, chain_id):
        if b['chain_work'] is None:
            in_longest = 0
        else:
            # Do we produce a chain longer than the current chain?
            # Query whether the new block (or its tallest descendant)
            # beats the current chain_last_block_id.
            row = store.selectrow("""
                SELECT b.block_id, b.block_height
                  FROM block b, chain c
                 WHERE b.block_id = c.chain_last_block_id
                   AND c.chain_id = ?
                   AND b.block_chain_work < ?""",
                      (chain_id, store.binin_int(b['top']['chain_work'],
                                                 WORK_BITS)))
            if row:
                # New longest chain.
                in_longest = 1
                (loser_id, loser_height) = row
                to_connect = []
                to_disconnect = []
                winner_id = b['top']['block_id']
                winner_height = b['top']['height']
                #print "start", winner_height, loser_height
                while loser_height > winner_height:
                    to_disconnect.insert(0, loser_id)
                    loser_id = store.get_prev_block_id(loser_id)
                    loser_height -= 1
                while winner_height > loser_height:
                    to_connect.insert(0, winner_id)
                    winner_id = store.get_prev_block_id(winner_id)
                    winner_height -= 1
                #print "tie", loser_height, loser_id, winner_id
                loser_height = None
                while loser_id <> winner_id:
                    to_disconnect.insert(0, loser_id)
                    loser_id = store.get_prev_block_id(loser_id)
                    to_connect.insert(0, winner_id)
                    winner_id = store.get_prev_block_id(winner_id)
                    winner_height -= 1
                for block_id in to_disconnect:
                    store.disconnect_block(block_id, chain_id)
                for block_id in to_connect:
                    store.connect_block(block_id, chain_id)

            elif b['hashPrev'] == GENESIS_HASH_PREV:
                in_longest = 1  # Assume only one genesis block per chain.  XXX
            else:
                in_longest = 0

        store.sql("""
            INSERT INTO chain_candidate (
                chain_id, block_id, in_longest, block_height
            ) VALUES (?, ?, ?, ?)""",
                  (chain_id, b['block_id'], in_longest, b['height']))
        if in_longest == 1:
            store._add_block_chain(b['block_id'], chain_id)

        if in_longest > 0:
            store.sql("""
                UPDATE chain
                   SET chain_last_block_id = ?
                 WHERE chain_id = ?""", (b['top']['block_id'], chain_id))

    def find_next_blocks(store, block_id):
        ret = []
        for row in store.selectall(
            "SELECT next_block_id FROM block_next WHERE block_id = ?",
            (block_id,)):
            ret.append(row[0])
        return ret

    def get_prev_block_id(store, block_id):
        return store.selectrow(
            "SELECT prev_block_id FROM block WHERE block_id = ?",
            (block_id,))[0]

    def disconnect_block(store, block_id, chain_id):
        #print "disconnect", block_id, chain_id
        store.sql("""
            UPDATE chain_candidate
               SET in_longest = 0
             WHERE block_id = ? AND chain_id = ?""",
                  (block_id, chain_id))
        store._remove_block_chain(block_id, chain_id)

    def connect_block(store, block_id, chain_id):
        #print "connect", block_id, chain_id
        store.sql("""
            UPDATE chain_candidate
               SET in_longest = 1
             WHERE block_id = ? AND chain_id = ?""",
                  (block_id, chain_id))
        store._add_block_chain(block_id, chain_id)

    def lookup_txout(store, tx_hash, txout_pos):
        row = store.selectrow("""
            SELECT txout.txout_id, txout.txout_value
              FROM txout, tx
             WHERE txout.tx_id = tx.tx_id
               AND tx.tx_hash = ?
               AND txout.txout_pos = ?""",
                  (store.hashin(tx_hash), txout_pos))
        return (None, 0) if row is None else (row[0], int(row[1]))

    def pubkey_hash_to_id(store, pubkey_hash):
        return store._pubkey_id(pubkey_hash, None)

    def pubkey_to_id(store, pubkey):
        pubkey_hash = util.pubkey_to_hash(pubkey)
        return store._pubkey_id(pubkey_hash, pubkey)

    def _pubkey_id(store, pubkey_hash, pubkey):
        dbhash = store.binin(pubkey_hash)  # binin, not hashin for 160-bit
        row = store.selectrow("""
            SELECT pubkey_id
              FROM pubkey
             WHERE pubkey_hash = ?""", (dbhash,))
        if row:
            return row[0]
        pubkey_id = store.new_id("pubkey")
        store.sql("""
            INSERT INTO pubkey (pubkey_id, pubkey_hash, pubkey)
            VALUES (?, ?, ?)""",
                  (pubkey_id, dbhash, store.binin(pubkey)))
        return pubkey_id

    def catch_up(store):
        for dircfg in store.datadirs:
            store.catch_up_dir(dircfg)

    # Load all blocks starting at the current file and offset.
    def catch_up_dir(store, dircfg):
        def open_blkfile():
            filename = os.path.join(dircfg['dirname'], "blk%04d.dat"
                                    % (dircfg['blkfile_number'],))
            ds = BCDataStream.BCDataStream()
            ds.map_file(open(filename, "rb"), 0)
            return ds

        try:
            ds = open_blkfile()
        except IOError, e:
            print "Skipping datadir " + dircfg['dirname'] + ": " + str(e)
            return
        ds.read_cursor = dircfg['blkfile_offset']

        while (True):
            store.import_blkdat(dircfg, ds)

            # Try another file.
            dircfg['blkfile_number'] += 1
            try:
                ds = open_blkfile()
            except IOError:
                # No more block files.
                dircfg['blkfile_number'] -= 1
                return

            dircfg['blkfile_offset'] = 0

    # Load all blocks from the given data stream.
    def import_blkdat(store, dircfg, ds):
        bytes_done = 0

        while ds.read_cursor + 8 <= len(ds.input):
            offset = ds.read_cursor
            magic = ds.read_bytes(4)  # XXX should scan past invalid data.
            length = ds.read_int32()
            if ds.read_cursor + length > len(ds.input):
                ds.read_cursor = offset
                break

            hash = util.double_sha256(
                ds.input[ds.read_cursor : ds.read_cursor + 80])
            # XXX should decode target and check hash against it to avoid
            # loading garbage data.

            if store.contains_block(hash):
                # Block header already seen.  Skip the block.
                # XXX Could rescan transactions in case we loaded an
                # incomplete block or if operating under --rescan.
                ds.read_cursor += length
            else:
                b = deserialize.parse_Block(ds)
                b["hash"] = hash
                store.import_block(b)

                # Assume blocks obey the respective policy if they get here.
                if 'chain_id' in dircfg:
                    chain_id = dircfg['chain_id']
                elif magic == BITCOIN_MAGIC:
                    chain_id = BITCOIN_CHAIN_ID
                elif magic == TESTNET_MAGIC:
                    chain_id = TESTNET_CHAIN_ID
                elif magic == NAMECOIN_MAGIC:
                    chain_id = NAMECOIN_CHAIN_ID
                else:
                    chain_id = None

                if chain_id is not None:
                    store.offer_block_to_chain(b, chain_id)

            bytes_done += length
            # XXX should be configurable
            if bytes_done > 100000 :
                store.save_blkfile_offset(dircfg, ds.read_cursor)
                store.commit()
                bytes_done = 0

        if bytes_done > 0:
            store.save_blkfile_offset(dircfg, ds.read_cursor)
            store.commit()

    def save_blkfile_offset(store, dircfg, offset):
        store.sql("""
            UPDATE datadir
               SET blkfile_number = ?,
                   blkfile_offset = ?
             WHERE dirname = ?""",
                  (dircfg['blkfile_number'], offset, dircfg['dirname']))
        if store.cursor.rowcount == 0:
            store.sql("""
                INSERT INTO datadir (dirname, blkfile_number,
                    blkfile_offset, chain_id)
                VALUES (?, ?, ?, ?)""",
                      (dircfg['dirname'], dircfg['blkfile_number'], offset,
                       dircfg['chain_id']))
        dircfg['blkfile_offset'] = offset

def new(args):
    return DataStore(args)
