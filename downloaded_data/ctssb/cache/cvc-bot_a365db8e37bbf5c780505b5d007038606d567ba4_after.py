# -*- coding: utf-8 -*-

import os
import sys
import datetime

# this file is expected to be in {caffe_root}/examples
caffe_root = '/home/vagrant/software/caffe/build/install/'
sys.path.insert(0, caffe_root + 'python')

import cv2
import caffe
import json
import telebot
import urllib2
import cleverbot
import subprocess
import numpy as np

class CVCBot(object):
	def __init__(self, key_fname, root_path, caffe_args, memnet_args):
		# load the TOKEN from a given file
		self.key = self.load_key(key_fname)
		# set project path
		self.root_path = root_path
		# create a new Telegram Bot object
		self.bot = telebot.TeleBot(self.key)
		# create caffe net
		self.caffe_net = CVCaffe(**caffe_args)
		# create memnet
		#self.memnet = CVCaffe(**memnet_args)
		# create clever bot instance
		self.cb = {}
		# create log file with date name
		fname = 'log/%s.txt' % datetime.datetime.now()
		self.file = open(fname, 'w')
		# variable to set bot busy
		self.is_busy = {}

		# Handle '/start' and '/help'
		@self.bot.message_handler(commands=['start'])
		def on_start(message):
			self.bot.send_message(message.chat.id, """\
			Hi there, I am the CVCBot.
			I am here to do some computer vision stuff. Just send me an \
			image and let the magic flow!\
			""")

		@self.bot.message_handler(commands=["ping"])
		def on_ping(message):
			self.bot.send_message(message.chat.id, "Still alive and kicking!")

		@self.bot.message_handler(commands=["stop"])
		def on_stop(message):
			self.bot.send_message(message.chat.id, "Dude! Are you trying to hack me?!")

		@self.bot.message_handler(commands=["help"])
		def on_help(message):
			self.bot.send_message(message.chat.id, "Dou you want to chat with me?")

		@self.bot.message_handler(commands=["memnet"])
		def on_memnet(message):
			self.set_is_busy(message, True)
			self.bot.send_message(message.chat.id, 'Just send me an image and let the magic flow!')
			#self.bot.register_next_step_handler(message, process_memnet_step)

		@self.bot.message_handler(commands=["cancel"])
		def on_cancel(message):
			if self.get_is_busy(message):
				self.bot.send_message(message.chat.id, "Success! The current operation was cancelled")
			else:
				self.set_is_busy(message, False)
				self.bot.send_message(message.chat.id, "No active command " \
					"to cancel. I wasn't doing anything anyway. Zzzzz...")		

		# Handle a simple text message
		@self.bot.message_handler(func=lambda message: True, content_types=['text'])
		def echo_message(message):
			print 'Received text message from %s' % message.from_user
			print 'Question: %s' % message.text

			if self.get_is_busy(message):
				return

			usr_id = message.from_user.id
			if not usr_id in self.cb:
				self.cb[usr_id] = cleverbot.Cleverbot()
			
			# query question to cleverbot
			question = message.text.encode('utf8')
			answer = self.cb[usr_id].ask(question)
			
			# log messages
			self.file.write('%s : %s\n' % (message.from_user.id, question))

			# return cleverbot answer to user
			self.bot.send_message(message.chat.id, answer)
			print 'Answer: %s' % answer

		# Handles all sent documents and audio files
		@self.bot.message_handler(content_types=['photo'])
		def handle_photo(message):

			print '[INFO] Image received from: ' + str(message.from_user)

			# send info to user
			self.bot.reply_to(message, \
				'**** Wait until your image is being precessed ****')

			file_info = None
			for p in message.photo:
				file_info = self.bot.get_file(p.file_id)

			# process data
			caffe_prediction = self.process_caffe(file_info)
			memnet_prediction = self.process_memnet_web(file_info)

			# join obtained messages
			msg = caffe_prediction + '\n' + memnet_prediction

			# send result to user
			self.bot.send_message(message.chat.id, msg)

		def process_memnet_step(message):
			if message.content_type == 'photo':
				self.bot.send_message(message.chat.id, 'Your image is being processed!')
			else:
				self.bot.send_message(message.chat.id, 'Just send me an image and let the magic flow!')
				self.bot.register_next_step_handler(message, process_memnet_step)

	def process_image_caca(self, img_path):
		img_txt = os.path.splitext(img_path)[0] + '.txt'
		subprocess.call('img2txt %s > %s' % (img_path, img_txt), shell=True)
		subprocess.call('cat %s ' % img_txt, shell=True)

	def process_memnet_web(self, file_info):

		# define url for memnet			
		url_memnet = 'http://memorability.csail.mit.edu/cgi-bin/image.py?url='
		url_file = 'https://api.telegram.org/file/bot{0}/{1}'.format(self.key, file_info.file_path)
		url_get = url_memnet + url_file

		# get from demo website
		# http://memorability.csail.mit.edu/demo.html
		response = urllib2.urlopen(url_get)
		html = response.read()

		# define return message
		memscore = 100 * float(json.loads(html)['memscore'])
		msg = 'LaMem says your image has a %s %% of memorability' % memscore
		print msg
		return msg
	
	def process_caffe(self, file_info):

		# download the image and save it to the system
		img_path = self.download_image(file_info)

		# log image into terminal
		#self.process_image_caca(img_path)

		# process photo
		prediction = self.caffe_net.predict(img_path)
	
		# prepare message		
		msg = 'Googlenet classified as: %s' % prediction
		print msg
		return msg

	def download_image(self, file_info):
		# download the image
		downloaded_file = self.bot.download_file(file_info.file_path)
		# convert to opencv format
		img = self.file_to_arr(downloaded_file)
		# save image to system
		filename = '%s.png' % file_info.file_id
		path_file = os.path.join(self.root_path, 'tmp', filename)
		cv2.imwrite(path_file, img)
		return path_file

	def file_to_arr(self, file):
		# url to array
		arr = np.asarray(bytearray(file), dtype=np.uint8)
		img = cv2.imdecode(arr,-1) # 'load it as it is'
		return img

	def get_is_busy(self, message):
		usr_id = message.from_user.id
		if not usr_id in self.is_busy:
			self.is_busy[usr_id] = False
		return self.is_busy[usr_id]

	def set_is_busy(self, message, _is_busy):
		usr_id = message.from_user.id
		self.is_busy[usr_id] = _is_busy

	def load_key(self, key_fname):
		with open(key_fname, 'r') as f:
			return f.readlines()[0].rstrip('\r\n')
	
	def run(self):
		self.bot.polling(none_stop=True)


class CVCaffe(object):
	def __init__(self, proto_txt, caffe_model, labels=None, mean_dir=None, size=None):
		# load caffe model
		self.net = caffe.Net(proto_txt, caffe_model, caffe.TEST)
		# load labels
		if labels is not None:
			self.labels = np.loadtxt(labels, str, delimiter='\t')
		# transformer to preprocess the input data
		self.transformer = self.init_transformer(mean_dir, size)
		# set blobs size
		self.net.blobs['data'].reshape(1, 3, size, size)

	def init_transformer(self, mean_dir, size):
		# input preprocessing: 'data' is the name of the input blob == net.inputs[0]
		transformer = caffe.io.Transformer({'data': self.net.blobs['data'].data.shape})
		transformer.set_transpose('data', (2,0,1))
		# the reference model operates on images in [0,255] range instead of [0,1]
		transformer.set_raw_scale('data', 255)
		# the reference model has channels in BGR order instead of RGB
		transformer.set_channel_swap('data', (2,1,0))

		if mean_dir is not None:
			# first convert mean.binaryproto to array
			# preprocess the mean file
			blob = caffe.proto.caffe_pb2.BlobProto()
			data = open(os.path.join(models_dir, mean_dir), 'rb').read()
			blob.ParseFromString(data)
			arr = np.array( caffe.io.blobproto_to_array(blob) )
			mean = np.mean(np.mean(np.mean(arr, 1), 1), 1)
			mean_arr = np.tile(mean, (3, size, size))
			# set the mean
			transformer.set_mean('data', mean_arr) # mean pixel

		return transformer

	def predict(self, img_path):
		# set image array as input
		self.net.blobs['data'].data[...] = self.transformer.preprocess('data', \
			caffe.io.load_image(img_path))
		out = self.net.forward()
		print('Predicted class is #{}.'.format(out['prob'][0].argmax()))

		# sort top k predictions from softmax output
		top_k = self.net.blobs['prob'].data[0].flatten().argsort()[-1:-6:-1]
		print self.labels[top_k]
		return self.labels[top_k][0].split(' ', 1)[1]

	# TODO(edgar): find how to properly set model mean
	def predict_memnet(self, img_path):
		# set image array as input
		self.net.blobs['data'].data[...] = self.transformer.preprocess('data', \
			caffe.io.load_image(img_path))
		out = self.net.forward()

		return True

if __name__ == '__main__':

	project_path, filename = os.path.split(os.path.realpath(__file__))
	models_dir = os.path.join(project_path, 'data/models')
	key_filename = os.path.join(project_path, 'data/key.txt')

	caffe_args = {
		'proto_txt': os.path.join(models_dir, 'googlenet/deploy.prototxt'),
		'caffe_model': os.path.join(models_dir, 'googlenet/bvlc_googlenet.caffemodel'),
		'labels': os.path.join(models_dir, 'googlenet/synset_words.txt'),
		'size': 224,
	}

	memnet_args = {
		'proto_txt': os.path.join(models_dir, 'memnet/deploy.prototxt'),
		'caffe_model': os.path.join(models_dir, 'memnet/memnet.caffemodel'),
		'mean_dir': os.path.join(models_dir, 'memnet/mean.binaryproto'),
		'size': 227,
	}

	cvc_bot = CVCBot(key_filename, project_path, caffe_args, memnet_args)
	cvc_bot.run()
