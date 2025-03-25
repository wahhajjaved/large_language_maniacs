#!/usr/bin/env python3

import logging

from . import app
from raw import db, Account

from data_import import importOfxAccounts, importOfxEntries

from flask import jsonify, request, make_response

# --------------------------------------------------------------------------------

def accounts():
	"""Retrieves basic account information from the database and returns
	in. This version does not expand to include all entries.
	"""
	return [item.value for item in db.session.query(Account).all()]

@app.route('/accounts', methods=['GET'])
def getAccounts():
	"""REST endpoint to retrieve accounts
	"""
	return jsonify(accounts())

# ----------------------------------------

def updateAccounts():
	"""Issues updates for all OFX accounts, downloading any new entries and
	updating any existing ones that have changed on the server.
	"""
	logging.info('Updating Accounts')

	try:
		importOfxAccounts(db.session)
		importOfxEntries(db.session)
		db.session.commit()

	except Exception as e:
		logging.error(e)

@app.route('/accounts/update', methods=['POST'])
def postUpdate():
	"""A slightly abused REST endpoint to initiate a update operation. This
	returns no information, but has side effects on the database.
	"""

	updateAccounts()
	return make_response("", 204)
