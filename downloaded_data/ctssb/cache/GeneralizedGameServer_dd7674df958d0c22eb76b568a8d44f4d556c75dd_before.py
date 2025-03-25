import sys
import socket
import random as r

import helpers.message as msg

class BotHelper:
	def __init__(self, name, strategy):
		# Get server ip and port from commandline
		#  TODO: replace with config file
		try:
			server_info = (sys.argv[1], int(sys.argv[2]))
		except:
			# How did you mess this up?
			print "Usage:\n%s [ip] [port]" % sys.argv[0]
			raw_input("Press the any key to finish.")
			sys.exit(1)

		# Check if ip is in ipv4 format or ipv6 format
		ipv4 = False
		if '.' in server_info[0]: #this works, screw regex
			ipv4 = True

		# Connect to server
		if ipv4:
			self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		else:
			self.server = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)

		# Initialize other member variables
		self.name = name
		self.message = msg.Message(self.server, "", "")
		self.strategy = strategy
		self.history = []
		self.gamestate = None

		# Connect to the server
		connected = False

		# Attempt to connect 10 times. If it fails all 10, give up.
		for i in range(1, 11):
			try:
				self.server.connect(server_info)
				connected = True
				break
			except:
				print "Could not connect to the server (attempt #%d). Trying again." % i

		if not connected:
			print "Could not connect to the server, it might be down or super busy."
			return

		# Start waiting for server requests
		self.run()


	def run(self):
		# Only send an ACK as a response to an ACK once, don't want to enter an infinite ACK loop
		done_with_ack = False
		while True:
			# Wait for a message from the server
			try:
				got = self.message.recv()
				rq_type, body = got
			except Exception as e:
				print "The following error occured:", e
				self.cleanup()
				break
			if rq_type == msg._MSGTYP["Ack"] and not done_with_ack:
				self.message.sendAck()
				done_with_ack = True
			elif rq_type == msg._MSGTYP["Name"]:
				self.message.sendName(self.name)
				done_with_ack = False
			elif rq_type == msg._MSGTYP["Move"]:
				self.throw()
				done_with_ack = False
			elif rq_type == msg._MSGTYP["OppMove"]:
				self.history.append(body)
				self.message.sendAck()
				done_with_ack = False
			elif rq_type == msg._MSGTYP["GameState"]:
				self.gamestate = body
				self.message.sendAck()
				done_with_ack = False
			elif rq_type == msg._MSGTYP["Note"]:
				print "Message from server: %s" % body
				self.message.sendAck()
				done_with_ack = False
			elif rq_type == msg._MSGTYP["Termination"]:
				self.message.sendAck()
				done_with_ack = False
				self.cleanup()
				break # Done talking to server, quit out
			else:
				print "Unkown command type '%s', body: %s" % (type, body)
				continue # Unknown command, ignore

	def throw(self):
		move = self.strategy(self.history)
		self.message.sendMove(move)

	def cleanup(self):
		error_msg = ''
		try:
			self.server.close()
		except:
			pass

		print "Connection with server terminated."
