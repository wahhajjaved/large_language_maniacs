from wss import Server
from recognizer import Recognizer
import json
import trollius as asyncio
from base64 import b64decode, b64encode
import numpy as np
import cv2

from .recognitionprotocol2 import Messages, Signals, ErrorMessages


class CameraBase:

	def __init__(self, name, maxsize=0):
		self.imgQueue = asyncio.Queue(maxsize)
		self.name = name


class RecognitionServer(Server):

	def __init__(self, cameras=[], port=9004, users_file="users.json", recognition_db="recognition.db"):

		Server.__init__(self, port=port, usessl=False)

		self.recognition_db = recognition_db

		self.last_user_uuid = ""
		self.last_len_persons_detected = 0

		self.camera_clients = []
		self.recognizer = Recognizer(users_file)

		self.cameras = cameras
		self.start()

		self.method_handlers = {}
		self.method_handlers["list_users"] = self.list_users
		self.method_handlers["select_camera"] = self.select_camera
		self.method_handlers["list_users_with_level"] = self.list_users_with_level
		self.method_handlers["add_association"] = self.add_association

		asyncio.get_event_loop().create_task(self.poll())


	def save_recognition_db(self):
		print("trying to save recognition db...")
		try: 
			with open(self.recognition_db, "w+") as db:
				data = self.recognizer.serialize()

				if not data:
					print("Failed to serialize recognition database")

				db.write(data)
		except:
			import sys, traceback
			exc_type, exc_value, exc_traceback = sys.exc_info()
			traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
			traceback.print_exception(exc_type, exc_value, exc_traceback,
						limit=6, file=sys.stdout)

	def load_recognition_db(self):
		try:
			with open(self.recognition_db, "r") as db:
				success = self.recognizer.deserialize(db.read())
		except:
			import sys, traceback
			exc_type, exc_value, exc_traceback = sys.exc_info()
			traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
			traceback.print_exception(exc_type, exc_value, exc_traceback,
						limit=6, file=sys.stdout)

	def reset_last_uuid(self):
		 self.last_user_uuid=""
	
	def send_all(self, msg):
		for client in self.camera_clients:
			client.sendMessage(msg, False)

	def face_detected(self, person):		
		msg = Signals.face_detected(None)
		
		self.send_all(msg)

	def face_recognized(self, user, img, confidence):
		msg = Signals.face_recognized(user, img, confidence)

		self.send_all(msg)


	@asyncio.coroutine
	def poll(self):
		while True:
			try: 
				persons = self.recognizer.detect_persons()

				if len(persons):
					print("persons? {}".format(len(persons)))
					self.process(persons)

			except:
				print("crashed while trying to poll recognizer...")
				import sys, traceback
				exc_type, exc_value, exc_traceback = sys.exc_info()
				traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
				traceback.print_exception(exc_type, exc_value, exc_traceback,
							limit=6, file=sys.stdout)
			yield asyncio.From(asyncio.sleep(1))


	def process(self, persons):
		
		for person in persons:
			try:
				if self.last_len_persons_detected != len(persons):
					self.last_len_persons_detected = len(persons)
					self.face_detected(person)

				user = self.recognizer.recognize(person.person_id.tracking_id)

				if not user or user.status > 1:
					if user:
						print(user.status_desc)
					return

				confidence = user.confidence
				uuid = user.recognition_id

				userdata = self.recognizer.user(uuid=uuid)

				if not userdata:
					continue

				print("user recognized: {}".format(userdata.username))
				print("confidence: {}".format(confidence))

				if confidence > 50:
					print("confidence is good.  Sending face_recognized signal")
					self.face_recognized(userdata, None, confidence)

			except:
				import sys, traceback
				exc_type, exc_value, exc_traceback = sys.exc_info()
				traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
				traceback.print_exception(exc_type, exc_value, exc_traceback,
							limit=6, file=sys.stdout)

	def onMessage(self, msg, fromClient):
		print("message received!!!")

		try:
			msg = json.loads(msg)

			if "method" in msg.keys():
				self.hndl_method(msg, fromClient)
			else:
				print("unhandled message: {}".format(msg))

		except:
			print ("message: {}".format(msg))
			import sys, traceback
			exc_type, exc_value, exc_traceback = sys.exc_info()
			traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
			traceback.print_exception(exc_type, exc_value, exc_traceback,
							limit=6, file=sys.stdout)

	def hndl_method(self, msg, fromClient):
		method = msg["method"]

		if method in self.method_handlers:
			self.method_handlers[method](msg, fromClient)
		else:
			print("method not handled: {}".format(method))

	def select_camera(self, msg, fromClient):
		if not "camera" in msg:
			print("Error: invalid select_camera message")
			return

		self.camera_clients.append(fromClient)

	def list_users(self, msg, fromClient):
		filter=None
		if "filter" in msg:
			filter = msg["filter"]

		reply = Signals.list_users(self.recognizer.getUsers(filter))

		fromClient.sendMessage(reply, False)

	def list_users_with_level(self, msg, fromClient):
		level = msg["level"]
		users = self.recognizer.users

		reply_user_list = []

		for user in users:
			if user.level >= level:
				reply_user_list.append(user.to_json())

		print("replying to list_users_with level with ({}) users".format(len(reply_user_list)))

		reply = Signals.list_users_with_level(reply_user_list)

		fromClient.sendMessage(reply, False)

	def add_association(self, msg, fromClient):
		uuid = msg["uuid"]
		associate_uuid = msg["associate_uuid"]
		self.recognizer.associate(uuid, associate_uuid)


class LocalCamera(CameraBase):

	def __init__(self, name, cam_dev=0):
		CameraBase.__init__(self, name, maxsize=5)

		asyncio.get_event_loop().create_task(self.poll_camera(cam_dev))

	@asyncio.coroutine
	def poll_camera(self, cam_dev):
		import cv2
		cap = cv2.VideoCapture(cam_dev)

		while True:
			try:
				ret, img = cap.read()
				if not ret:
					print("error reading from camera")
					return

				self.imgQueue.put_nowait(img)

			except asyncio.QueueFull:
				pass
			except KeyboardInterrupt:
				raise KeyboardInterrupt()

			except:
				print("error polling camera")

			yield asyncio.From(asyncio.sleep(1/30))

class WssCamera(CameraBase):
	def __init__(self, name, address, port, use_ssl=False):
		CameraBase.__init__(self, name, maxsize=5)

		self.address = address
		self.port = port

		from wss import Client

		client = Client(retry=True)
		client.setTextHandler(self.img_received)
		client.connectTo(self.address, self.port, useSsl=use_ssl)

	def img_received(self, payload):
		payload = b64decode(payload)
		img = np.frombuffer(payload, dtype='uint8')
		img = cv2.imdecode(img, cv2.IMREAD_COLOR)

		try:
			self.imgQueue.put_nowait(img)
		except asyncio.QueueFull:
			pass
