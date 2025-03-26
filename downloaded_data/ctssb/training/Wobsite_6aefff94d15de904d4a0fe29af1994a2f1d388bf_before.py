import flask as f
from flask import render_template
from flask import request
from flask import jsonify
import os
import requests
import plaid
import pandas as pd

app = f.Blueprint('bank', __name__)

PLAID_CLIENT_ID = os.getenv('PLAID_CLIENT_ID')
PLAID_SECRET = os.getenv('PLAID_SECRET')
PLAID_PUBLIC_KEY = os.getenv('PLAID_PUBLIC_KEY')
PLAID_ENV  = 'sandbox'
host = 'https://sandbox.plaid.com'



client = plaid.Client(client_id = PLAID_CLIENT_ID, secret=PLAID_SECRET,
                  public_key=PLAID_PUBLIC_KEY, environment=PLAID_ENV)

@app.route("/begin")
def begin():
   return render_template('bank_system/begin.html', plaid_public_key=PLAID_PUBLIC_KEY, plaid_environment=PLAID_ENV)


access_token = None
public_token = None
item_id = None

@app.route("/get_access_token", methods=['POST'])
def get_access_token():
  global access_token
  global public_token
  global item_id

  public_token = request.form['public_token']
  exchange_response = client.Item.public_token.exchange(public_token)
  item_id = exchange_response['item_id']

  access_token = exchange_response['access_token']

  return jsonify(exchange_response)

def get_creds():
    global access_token
    global public_token
    global item_id
    return access_token, item_id

@app.route('/get_banks')
def get_banks():

    access_token, item_id = get_creds()



    start_date = '2018-01-01'
    end_date = '2018-03-01'

    data = {'client_id': PLAID_CLIENT_ID,
            'secret': PLAID_SECRET,
            'access_token': access_token,
            'start_date': start_date,
            'end_date': end_date,

            }

    return str(data)
    x = requests.post(host + '/transactions/get', json=data).json()
    try:
        x = pd.DataFrame(x['transactions'])
    except KeyError:
        return 'NO TRANSACTIONS FOUND'

    resp = f.make(df.to_csv())
    resp.headers["Content-Disposition"] = "attachment; filename=export.csv"
    resp.headers["Content-Type"] = "text/csv"
    return resp
