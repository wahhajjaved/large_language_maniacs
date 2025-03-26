import os
import json
import couchdb
import telepot
import requests
from   flask          import Flask, jsonify, request, make_response
from   flask_httpauth import HTTPBasicAuth

app      = Flask(__name__)
auth     = HTTPBasicAuth()
tgmtoken = os.environ['TGM-TOKEN']
couch    = couchdb.Server('http://%s:5984/' % os.environ.get("CENTRAL_COUCHDB_SERVER", "localhost"))

try:
    db = couch['orders']
except Exception as e:
    db = couch.create('orders')


@auth.get_password
def get_password(username):
    if username == 'ansi':
        return 'test'
    return None

@auth.error_handler
def unauthorized():
    return make_response(jsonify({'error': 'Unauthorized access'}), 401)


def prepareanswer(r, msg):
    #print(json.dumps(r, indent=2, sort_keys=True))

    if 'action' in r['output']:

        if r['output']['action'] == "EatDrink":
            entry = {"drinkFood": r['context']['DrinkOrFood'], "seat": "23F", "name": "Ansgar Schmidt", "new": False, "done": False}
            ordersdb = couch['orders']
            ordersdb.save(entry)
            print("Bring %s to %s" % (r['context']['DrinkOrFood'], msg['from']['username']))

        if r['output']['action'] == "NewUser":
            print("Bring %s to %s" % (r['context']['DrinkOrFood'], msg['from']['username']))

    if 'text' in r['output'] and len(r['output']['text']) > 0:
        return r['output']['text'][0]
    else:
        return "No valid answer from NLP system, please contact Sandra"


def handle(msg):
    print("Message received")
    print(msg['text'])
    uID    = msg['from']['id']
    text   = msg['text']
    r      = json.loads(requests.post('http://conversation:8011/api/v1.0/conversation/process',
                                      json={'text': text, "telegramid": uID, "telegrammsg": msg},
                                      auth=('ansi', 'test')
                                      ).content
                       )
    bot.sendMessage(uID, prepareanswer(r, msg))


bot  = telepot.Bot(tgmtoken)
bot.message_loop(handle)
bot.sendMessage(276371592, 'Start Feelflight Bot')
bot.sendMessage(457425242, 'Start Feelflight Bot')

@app.route('/api/v1.0/chat/send', methods=['POST'])
@auth.login_required
def process_text():
    r = request.get_json(silent=True)
    if r is not None and 'text' in r:
        text = r['text']
        uID  = int(r['uid'])
        bot.sendMessage(uID, text)
        return make_response(jsonify({'done': 'done'}), 200)
    return make_response(jsonify({'error': 'Not a valid json'}), 401)

if __name__ == '__main__':
    print("2-0-chat started")
    app.run(host="::", port=8020)
