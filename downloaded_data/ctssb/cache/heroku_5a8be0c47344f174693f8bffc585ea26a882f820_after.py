import json
from flask import Flask, request, render_template, send_file
from actions import *

app = Flask(__name__)

PAT = "EAAUXU7pfXaUBANDYYDowVgl631ejD4kARCBmIECs5BqLotsBZCAIZAR6ACUVNJ56QHJelpUZAn4eLYG5QWOZBpR6uF0JtNqtELfv6FqUKRbLlrZC2HIavCgVogFR27k8G93zUnIBjSkRWNNqWO5mZAND2HWtEoHbXrQAoeZBfVB6QZDZD"

@app.route('/', methods=['GET'])
def verify():
    # when the endpoint is registered as a webhook, it must echo back
    # the 'hub.challenge' value it receives in the query arguments
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.challenge"):
        if not request.args.get("hub.verify_token") == "verification_string@":
            return "Verification token mismatch", 403
        return request.args["hub.challenge"], 200

    return render_template('index.html'), 200

@app.route('/', methods=['POST'])
def callback():
    data = request.get_json()
    if data == None:
        return request.form
    if data["object"] == "page":
        for entry in data["entry"]:
            EM = EntryManager(entry)
            result_list = map(answer, EM.answerEntry())
    return "OK", 200

def answer(answer_details):
    params  = {"access_token": PAT}
    headers = {"Content-Type": "application/json"}
    data    = JSONify(answer_details)
    if(data is None):
        return None
    r = requests.post("https://graph.facebook.com/v2.6/me/messages",params=params,headers=headers,data=data)
    if r.status_code != 200:
        print(r.status_code)
        print(r.text)

#Generate Response
def JSONify(answer_details):
    print(answer_details)
    _type = answer_details['type']
    sender_id = answer_details['sender']

    if "text" in _type:
        message_answer = answer_details['text']
        data = {
                "recipient":{"id":sender_id},
                "message":{"text":message_answer}
                }
        return json.dumps(data)

#Deal with Entries

@app.route("/sayhi", methods=['POST','GET'])
def sayingHi():
    if request.method == 'GET':
        return "Get this",200
    if request.method == 'POST':
        request.get_data()
        data = request.json
        string = ""
        for key in data.keys():
            string += data[key]
        return string,200

@app.route("/Comment", methods=['GET'])
def postRequest():
    name = request.args.get("name")
    email = request.args.get("email")
    message = request.args.get("message")
    print(name+"\n"+email+"\n"+message)
    string = name+" "+email+" "+message
    return string,200
