from flask import Flask, request, redirect
from twilio.rest import TwilioRestClient
#from config import account_sid, auth_token
import twilio.twiml, urllib2, os, json


application = Flask(__name__)

northwood = [440, 442, 443]
bb = [437, 438, 433, 434]
cn = [414, 415]
cs = [417, 418]
nwx = [412]
d2dn = [420]
d2ds = [419]
ox = [424]
number = os.environ['PHONE_NUMBER']
account_sid = os.environ['TWILIO_ACCOUNT_SID']
auth_token = os.environ['TWILIO_AUTH_TOKEN']

client = TwilioRestClient(account_sid, auth_token)
 
# message = client.messages.get("MM800f449d0399ed014aae2bcc0cc2f2ec")
# print message.body


@application.route("/", methods=['GET', 'POST'])
def send_bus_info():
	"""Respond to message of bus stop with eta info."""
	messages = client.messages.list()
	# messages = client.messages.list(from_=number,)
	# sid =  messages[0].sid
	body = messages[0].body
	print body	

	resp = twilio.twiml.Response()
	
	if body == "Pierpont":
		stop = "98"
	elif body == "Ugli":
		stop = "76"
	elif body == "Markley":
		stop = "29"
	elif body == "Cclittle":
		stop = "137"
	elif body == "Power center":
		stop = "43"
	elif body == "Cooley":
		stop = "88"
	elif body == "Law":
		stop = "149"
	else:
		resp.message("Couldnt find stop")
		return str(resp)
	print "valid stop received: ", stop	
	object = urllib2.urlopen("http://mbus.doublemap.com/map/v2/eta?stop=" + stop)
	object = json.load(object)
	
	try:
		bus_at_stop = object['etas'][stop]['etas']
	except:
		bus_at_stop = ""
		print "no routes servicing stop"
		resp.message("couldnt find route servicing stop")
		return str(resp)

	message = str(body)
	message += "\n"
	for bus in bus_at_stop:
		route = bus['route']
		time = bus['avg']
		if route in northwood:
			message += "Northwood "
		elif route in bb:
			message += "Burs. "
		elif route in cn:
			message += "Com. North "
		elif route in cs:
			message += "Com. South "
		elif route in nwx:
			message += "NWX "
		elif route in d2dn:
			message += "D2D North "
		elif route in d2ds:
			message += "D2D Central"
		elif route in ox:
			message += "Ox shuttle "
		message += str(time)
		message += " min to stop\n"

	resp.message(message)
	return str(resp)

if __name__ == "__main__":
	application.run(debug=True)
