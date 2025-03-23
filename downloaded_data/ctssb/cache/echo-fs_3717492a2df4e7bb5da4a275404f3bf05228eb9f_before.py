from multiprocessing import Pool
import echo_listener_settings as settings
from boto import sqs
from boto.sqs.message import RawMessage, Message
from boto.s3.connection import S3Connection
from boto.s3.key import Key
import json
import os.path
import sys
import redis
import time
import random
import string
import datetime

class AgnosticMessage(RawMessage):
	"""
	A message might originate from SNS or SQS. If from SNS then it will have a wrapper on it.
	"""
	
	def get_effective_message(self):
		b = json.loads(str(self.get_body()))
		if 'Type' in b and b['Type'] == "Notification":
			return json.loads(b['Message'])
		return b

def main():
	if len(sys.argv) < 6:
		showUsage()
		return
	
	redisHost = sys.argv[1]
	redisPort = int(sys.argv[2])
	redisDB = int(sys.argv[3])

	region = sys.argv[4]
	inputQueueName = sys.argv[5]
	errorQueueName = sys.argv[6]
	
	input_queue = get_queue(sys.argv[4], sys.argv[5])

	input_queue.set_message_class(AgnosticMessage)
	
	num_pool_workers = settings.NUM_POOL_WORKERS
	messages_per_fetch = settings.MESSAGES_PER_FETCH

	pool = Pool(num_pool_workers, initializer=workerSetup, initargs=(redisHost, redisPort, redisDB, region, errorQueueName))

	while True:
			messages = input_queue.get_messages(num_messages=messages_per_fetch, visibility_timeout=120, wait_time_seconds=20)
			if len(messages) > 0:
					pool.map(process_message, messages)

def workerSetup(redisHost, redisPort, redisDB, region, errorQueueName):
	global s3Connection
	s3Connection = S3Connection()
	
	global redisClient
	redisClient = redis.Redis(host=redisHost, port=redisPort, db=redisDB)
	
	global errorQueue
	errorQueue = get_queue(region, errorQueueName)

def showUsage():
	print "Usage: echo_listener.py <Redis IP> <Redis Port> <Redis DB> <AWS region> <AWS input queue name> <AWS error queue name>"
	print "Example: echo_listener.py 172.17.0.2 6379 0 eu-west-1 echo-eu-west-1a echo-eu-west-1a-errors"

def process_message(message):
	# console_log("process_message called")
	
	message_body = message.get_effective_message()
	
	# console_log("message type=" + message_body['_type'])
	
	try:
	
		if '_type' in message_body and 'message' in message_body and 'params' in message_body:
			if message_body['message'] == "echo::cache-item":
				cache_item(message_body['params'])
			elif message_body['message'] == "echo::item-access":
				item_access(message_body['params'])
	except:
		e = sys.exc_info()[0]
		handle_error(e, message)
		
	message.delete()

def handle_error(e, message):

	console_log("exception: %s" % str(e))

	m = Message()
	m.set_body(str(message.get_effective_message()))
	error_queue.write(m)
	
def item_access(payload):
	# console_log("item_access: " + payload['target'])
		
	record_access(payload['target'])
			
def cache_item(payload):
	# "source": "s3://my-bucket/key"
	# "target": "/my-path/key.maybe-extension-too
	# "bucket": "my-bucket"
	# "key": "key"
	
	console_log("cache_item: s3://" + payload['bucket'] + '/' + payload['key'] + ' -> ' + payload['target'])

	target = settings.CACHE_ROOT + payload['target'].decode('utf-8')

	targetPath = '/'.join(target.split('/')[0:-1])	

	try:
		if not os.path.isdir(targetPath):
			os.makedirs(targetPath)
	except:
		pass
		
	if os.path.exists(target):
		console_log("already exists in cache")
	else:
		#console_log("synchronisation lock")
		timeout_start = time.time()
		timeout = settings.LOCK_TIMEOUT
		
		timeout_occurred = True
		
		# if the flag exists, then loop until timeout for the flag to disappear
		if redisClient.exists(payload['target']):
			while time.time() < timeout_start + timeout:
				if redisClient.exists(payload['target']):
					# currently an operation happening for this file
					time.sleep(0.01)
				else:
					timeout_occurred = False
					break
					
			if timeout_occurred:
				raise Exception("lock timeout")
		
		if not os.path.exists(target):
			redisClient.set(payload['target'], payload['target'])
	
			bucket = s3Connection.get_bucket(payload['bucket'])

			k = Key(bucket)
			k.key = payload['key']

			k.get_contents_to_filename(target + ".moving")
			console_log("downloaded " + payload['key'] + " -> " + target + ".moving")
			os.rename(target + ".moving", target)
			console_log("renamed to " + target)
			
			record_access(payload['target'])
				
			redisClient.delete(payload['target'])
	
def record_access(item):
	#print "record_access for " + item
	accessTime = int(time.time())
	redisClient.zadd('access', item, accessTime)
	
def get_queue(region, queue):
	conn = sqs.connect_to_region(region)
	return conn.get_queue(queue)

def console_log(message):
	print('{:%Y%m%d %H:%M:%S} '.format(datetime.datetime.now()) + message)
	
if __name__ == "__main__":
	main()
