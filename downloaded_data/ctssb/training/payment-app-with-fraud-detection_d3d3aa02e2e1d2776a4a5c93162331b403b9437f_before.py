import dateutil.parser
from flask import Flask, request, json
import sqlite3
import os.path

import fraudService
import util

app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Hello World!'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, "db.sqlite")

@app.route('/transactions',  methods=['GET'])
def get_transactions():
    responseData = util.get_transactions_db()
    return json.dumps(responseData)


@app.route('/transactions', methods=['POST'])
def add_transaction():
    date = request.form["date"]
    try:
        dateutil.parser.parse(date)
    except ValueError:
        return "Invalid Date", 400
    merchant = request.form["merchant"]
    amount = 0
    try:
        amount = float(request.form["amount"])
    except ValueError:
        return "Invalid amount", 400
    charge = amount - int(amount)
    if charge > 0.8:
        charge = 1 - charge
    elif 0.5 > charge > 0.30:
        charge = 0.5 - charge
    else:
        charge = 0
    total = charge + amount

    t = (date, merchant, amount, charge, total)
    conn = sqlite3.connect(db_path, isolation_level=None)
    c = conn.cursor()
    c.execute('INSERT INTO transactions(date, merchant, amount, charge, total) VALUES(?, ?, ?, ?, ?)', t)
    conn.commit()
    fraud = fraudService.detect_fraud_json(util.get_transactions_db(include_id=True))
    if fraud[-1][1] == 1:
        c.execute('UPDATE transactions SET fraud = 1 WHERE id = ?', (fraud[-1][0] + 1,))
        conn.commit()
    c.close()
    return "OK " + str(fraud[-1][1])

if __name__ == '__main__':
    app.run()
