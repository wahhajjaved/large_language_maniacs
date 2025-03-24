import os
from flask import Flask
#from flask_environments import Environments
from flask.ext.sqlalchemy import SQLAlchemy
from flask import request
from flask import make_response
import requests
import json
import ast

import bitsource
import transactions
import addresses

import unicodedata

app = Flask(__name__)
app.config['PROPAGATE_EXCEPTIONS']=True
dbname='barisser'

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']  #"postgresql://localhost/"+dbname
db = SQLAlchemy(app)

import databases
db.create_all()



@app.route('/')
def something():
  #response="hey there!"
  #response=Response()
  response=make_response("Hey there!", 200)
  response.headers['Access-Control-Allow-Origin']= '*'
  return response

@app.route('/blocks/count')
def getblockcount():
  count=node.connect("getblockcount",[])
  response=make_response(str(count), 200)
  response.headers['Access-Control-Allow-Origin']= '*'
  return response

#GET HEX DECODED OP_RETURNS FROM A BLOCK
@app.route('/opreturns/<blockn>')           #WORKS
def opreturns_in_block(blockn=None):
    print blockn
    blockn=int(blockn)
    message=bitsource.op_return_in_block(blockn)
    return str(message)

#GET PARSED METADATA FOR OPEN ASSETS TRANSACTIONS IN BLOCK
@app.route('/oa/blocks/<blockn>')         #WORKS, needs color address
def oas_in_block(blockn=None):
  oas=bitsource.oa_in_block(int(blockn))
  return str(oas)

@app.route('/colors/signed', methods=['POST'])
def makenewcoin():
  public_address=str(request.form['public_address'])
  initial_coins=int(request.form['initial_coins'])
  name=str(request.form['name'])
  recipient=str(request.form['recipient'])
  fee_each=0.0001
  private_key=str(request.form['private_keys'])
  ticker=str(request.form['ticker'])
  description=str(request.form['description'])

  response=transactions.make_new_coin(public_address, initial_coins, name, recipient, fee_each, private_key, ticker, description)
  #print response
  return response
  #return "hi"

@app.route('/transactions/colored', methods=['POST'])  #DOESNT EXACTLY MATCH DOCS
def transfer_transaction_serverside():
  fromaddr=str(request.form['public_address'])
  dest=str(request.form['recipient'])
  fee=float(request.form['fee'])   #DOESNT MATCH DOCS
  private_key=str(request.form['private_key'])
  coloramt=int(request.form['coloramt'])

  #inputs=request.form['inputs']
  inputs=str(request.form['inputs'])
  inputs=ast.literal_eval(inputs)


  inputcoloramt=int(request.form['inputcoloramt'])
  print fromaddr
  print dest
  print fee
  print private_key
  print coloramt
  print inputs
  print inputcoloramt
  response= transactions.create_transfer_tx(fromaddr, dest, fee, private_key, coloramt, inputs, inputcoloramt)
  return str(response)
  #return str(coloramt)

@app.route('/transactions/<transaction_hash>')
def getrawtransaction(transaction_hash=None):
  transaction_hash=transaction_hash.encode('ascii')
  response=bitsource.tx_lookup(str(transaction_hash))
  #print response
  response=make_response(str(response), 200)
  response.headers['Access-Control-Allow-Origin']= '*'
  return response
  #return str(transaction_hash)

@app.route('/colors/statements/<address>')     #WORKS
def readmultistatements(address=None):
  result=addresses.read_opreturns_sent_by_address(address)
  response=make_response(result, 200)
  response.headers['Access-Control-Allow-Origin']= '*'
  return response

  return str(result)

@app.route('/colors/issue/signed', methods=['POST'])    #WORKS
def issuenewcoinsserverside():   #TO ONE RECIPIENT ADDRESS
  private_key=str(request.form['private_keys'])
  public_address=str(request.form['public_address'])
  more_coins=int(request.form['initial_coins'])
  recipient=str(request.form['recipients'])
  fee_each=0.0001
  name=str(request.form['name'])
  othermeta=str(name)

  print private_key
  response=transactions.create_issuing_tx(public_address, recipient, fee_each, private_key, more_coins, 0, othermeta)
  return response
  return str(name)

@app.route('/colors/issue', methods = ['POST'])      #WORKS
def issuenewcoins_clientside():
  #JUST RETURN RAW HEX OF UNSIGNED TX
  issuing_address=str(request.form['issuing_address'])
  more_coins=request.form['more_coins']
  coin_recipients=str(request.form['coin_recipients'])  #DISCREPANCY, SHOULD BE ARRAY for multiple
  othermeta='COIN NAME HERE'

  fee=0.0001
  print coin_recipients
  print more_coins
  print issuing_address
  print fee
  print othermeta
  tx=transactions.create_issuing_tx_unsigned(issuing_address, coin_recipients, fee, more_coins,othermeta)
  #return 'a'
  return str(tx)

@app.route('/addresses/generate')   #  WORKS
def makerandompair():
  return str(addresses.generate_secure_pair())

@app.route('/messages/<address>')
def opreturns_sent_by_address(address=None):
  results=addresses.find_opreturns_sent_by_address(address)
  return str(results)

@app.route('/transactions', methods = ['POST'])
def pushtx():
  txhex=str(request.form['transaction_hex'])
  response=transactions.pushtx(txhex)
  return str(response)

@app.route('/addresses/givenew', methods=['POST'])
def givenewaddress():
  public_address=request.form['public']
  private_key=request.form['private']
  coin_name=request.form['coin_name']
  color_amount=request.form['color_amount']
  dest_address=request.form['dest_address']
  description=request.form['description']

  fee_each=0.00005
  markup=1
  tosend=str(transactions.creation_cost(color_amount, coin_name, coin_name, description, fee_each, markup))
  print tosend

  color_address=addresses.hashlib.sha256(coin_name).hexdigest() #FIGURE THIS OUT

  newaddress=databases.address_db.Address(public_address, private_key, float(tosend)*100000000, 0, 0, coin_name, color_address, color_amount, dest_address, description)
  db.session.add(newaddress)
  db.session.commit()   #WORKS


  response=make_response(tosend, 200)
  response.headers['Access-Control-Allow-Origin']= '*'
  return response

def checkaddresses():  #FOR PAYMENT DUE      #WORKS
  owedlist=databases.address_db.Address.query.all()
  owed_data=[]
  for x in owedlist:
    r={}
    r['public_address']=x.public_address
    r['private_key']=x.private_key
    r['amount_expected']=x.amount_expected
    r['amount_received']=x.amount_received
    r['amount_withdrawn']=x.amount_withdrawn
    r['coin_name']=x.coin_name
    r['color_address']=x.color_address
    r['issued_amount']=x.issued_amount
    r['destination_address']=x.destination_address
    r['description']=x.description
    owed_data.append(r)

  for address in owed_data:
    unspents=addresses.unspent(address['public_address'])
    value=0
    for x in unspents:
      value=value+x['value']
    print "currently available in "+str(address['public_address'])+" : "+str(value/100000000)
    if value>=address['amount_expected']:
      #WITHDRAW IT AND PROCESS AND MARK AS WITHDRAWN IN DB
      fromaddr=address['public_address']
      colornumber=address['issued_amount']
      colorname=address['coin_name']
      destination=address['destination_address']
      fee_each=0.00005
      private_key=address['private_key']
      ticker=address['coin_name'][0:4]
      description=address['description']
      transactions.make_new_coin(fromaddr, colornumber, colorname, destination, fee_each, private_key, ticker, description)

      #MARK AS WITHDRAW IN DB
      address_entry=databases.address_db.Address.query.filter_by(private_key=address['private_key']).first()




  return owed_data

def workerstuff():
  checkaddresses()
  print "I am working!"

if __name__ == '__main__':
    app.run()
