#!/usr/bin/env python
from flask import Flask, request
import db
import re
import json

app = Flask(__name__)


# API calls
@app.route("/register_purchase/")
def register_purchase():
    shop_id = request.args.get('shop_id', '')
    m_hash = request.args.get('hash', '')
    valid_hash = re.compile("^[A-F0-9]{16}$|^[A-F0-9]{32}$|^[A-F0-9]{64}$")
    if valid_hash.match(m_hash) is not None:
        try:
            if not int(shop_id):
                raise ValueError
        except ValueError:
            return json.dumps({"status": "FAIL", "message": "shop_id should be a positive number"})
        db.save_tx(shop_id, m_hash)
        return json.dumps({"status": "OK", "message": ""})
    else:
        return json.dumps({"status": "FAIL", "message": "hash should have 16, 32 or 64 symbols"})


@app.route("/get_block/")
def get_block():
    m_hash = request.args.get('hash', '')
    valid_hash = re.compile("^[A-F0-9]{16}$|^[A-F0-9]{32}$|^[A-F0-9]{64}$")
    if valid_hash.match(m_hash) is not None:
        block, date = db.get_block_by_tx_hash(m_hash)
        if block is None:
            return json.dumps({"status": "OK", "block": None, "date": None, "message": "hash not found"})
        return json.dumps({"status": "OK", "block": block, "date": date, "message": ""})
    else:
        return json.dumps({"status": "FAIL", "message": "hash should have 16, 32 or 64 symbols"})
