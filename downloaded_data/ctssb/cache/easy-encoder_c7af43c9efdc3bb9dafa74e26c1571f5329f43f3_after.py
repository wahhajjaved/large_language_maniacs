#!/usr/bin/python
# -*- coding: UTF-8 -*-
import sys
import os
import subprocess
import json
import platform
import ConfigParser
import codecs
import re

_acodec = ''
_acodec_param = ''
_vcodec = ''
_app_info = 'avprobe' #.exe _linux
_app_encode = 'avconv'

#_app_info = 'ffprobe'
#_app_encode = 'ffmpeg'

_out_ext = '.m4v'

_save_param = []
_path = os.path.dirname(os.path.realpath(__file__))
_is_win = 0
_is_lin = 0
if platform.system() == 'Windows':
	_is_win = 1
	reload(sys)
	sys.setdefaultencoding("cp1251")
if platform.system() == 'Linux':
	_is_lin = 1

config = ConfigParser.ConfigParser()
config_name = 'config.cfg'
if not os.path.exists(os.path.join(_path,config_name)):
	print "Config file ("+config_name+") not found!"
	sys.exit(0)
else:
	config.readfp(codecs.open(os.path.join(_path,config_name), 'r', 'utf-8'))

_out = config.get('Main', 'output')
_auto_out = 0
if len(_out) == 0:
	_auto_out = 1

input_files = sys.argv[1:]
if len(input_files) == 0:
	print "Files for converting not found!"
	sys.exit(0)
if len(input_files) == 1:
	folder = input_files[0]
	if os.path.isdir(folder):
		input_files = []
		for file in os.listdir(folder):
			full_path = os.path.realpath(os.path.join(folder,file))
			if os.path.isdir(full_path):
				continue
			ex = file.split('.')[-1]
			if ex in ['avi','mkv','ts','wma','mp4']:
				input_files.append(full_path)
	print "Loaded files:",'\n'.join(input_files)
if len(input_files) == 0:
	print "Files for converting not found!"
	sys.exit(0)

def get_aac_codec():
	global _acodec
	global _acodec_param
	global _vcodec
	print 'AVmpeg: get codecs'
	app = _app_encode + ('.exe' if _is_win else '_linux' if _is_lin else '')
	app_path = os.path.join(_path,'bin',app)
	atr = [ app_path,
				'-codecs'
	]
	process = subprocess.Popen((' ').join(atr), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	aprio  = 0
	vprio = 0
	acodec = ''
	vcodec = ''
	param = []
	while True:
		buff = process.stdout.readline().replace('\r','').replace('\n','')
		if buff == '' and process.poll() != None: 
			break
		if re.match(r'.*libfdk_aac  .*',buff):
			acodec = 'libfdk_aac'
			param = []
			aprio  = 4
		if re.match(r'.*libfaac  .*',buff):
			if aprio > 3: continue
			acodec = 'libfaac'
			param = []
			aprio  = 3
		if re.match(r'.*aac  .*',buff):
			if aprio > 2: continue
			acodec = 'aac'
			param = ['-strict','-2']
			aprio  = 2
		if re.match(r'.*libvo_aacenc  .*',buff):
			if aprio != 0: continue
			acodec = 'libvo_aacenc'
			param = []
			aprio  = 1
		if re.match(r'.*h264  .*',buff):
			if vprio != 0: continue
			vcodec = 'h264'
			vprio  = 1
		if re.match(r'.*libx264  .*',buff):
			vcodec = 'libx264'
			vprio  = 2
	process.wait()
	_acodec = acodec
	_acodec_param = param
	_vcodec = vcodec

def ffmpeg(s,d,params):
	print 'AVmpeg: open',s
	d_tmp = d+'.converting'+_out_ext
	app = _app_encode + ('.exe' if _is_win else '_linux' if _is_lin else '')
	app_path = os.path.join(_path,'bin',app)
	atr = [ app_path,
				'-y',
				'-i',s,
				'-f','mp4',
				'-threads','auto',
				'-preset','slow',
				'-qmax','48',
				'-qmin','2'
	]
	atr += _acodec_param
	atr += params
	atr.append(d_tmp)
	print "Command line:",' '.join(atr)
	subprocess.Popen(atr, stdout=subprocess.PIPE).communicate()[0]
	if os.path.getsize(d_tmp) == 0:
		os.remove(d_tmp)
		return 0
	else:
		os.rename(d_tmp,d+_out_ext)
		return 1

def get_info(s):
	print 'AVprobe: open',s
	app = _app_info + ('.exe' if _is_win else '_linux' if _is_lin else '')
	app_path = os.path.join(_path,'bin',app)
	atr = [ app_path,
				'"'+s.replace("$","\$").replace("`","\`")+'"',
				'-of','json','-show_streams', '-show_format'
	]
	process = subprocess.Popen((' ').join(atr), shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	json_out = ''
	writeing = 0
	while True:
		buff = process.stdout.readline().replace('\r','').replace('\n','')
		if buff == '' and process.poll() != None: 
			break
		if writeing == 0 and len(buff) > 0 and buff[0] == '{':
			writeing = 1
		if writeing == 0 and len(buff) > 0 and buff.strip() == '"streams": [':
			buff = "{" + buff
			writeing = 1
		if writeing:
			json_out += buff
		if writeing and len(buff) > 0 and buff[0] == '}':
			writeing = 0
	process.wait()
	try:
		out = json.loads(json_out)
	except Exception: 
		try:
			out = json.loads(json_out.decode("cp1251"))
		except Exception: 
			out = json.loads(json_out.decode("utf-8","ignore"))
	return out

def select_streams(info):
	global _save_param
	if not 'streams' in info:
		print('Streams not found!')
		return ['-c','copy','-c:v','h264','-c:a','aac'];
	streams = {}
	v_count = 0
	a_count = 0
	o_count = 0
	all_arr = []
	for stream in info['streams']:
		def g(i,e=''):
			return str(stream[i]) if i in stream else e
		l_id = g('index','-1')
		l_lang = ''
		l_title = ''
		if 'tags' in stream:
			l_lang = stream['tags']['language'] if 'language' in stream['tags'] else ''
			l_title = stream['tags']['title'] if 'title' in stream['tags'] else '[No title]'
		l_type = g('codec_type')
		l_codec = g('codec_name')
		if l_type == 'video':
			v_count += 1
		elif l_type == 'audio':
			a_count += 1
		else:
			o_count += 1
		l_sample_rate = g('sample_rate')
		l_bit_rate = g('bit_rate')
		l_channel = g('channels')
		l_resol = g('width')+'x'+g('height')
		l_def = stream['disposition']['default'] if 'disposition' in stream and 'default' in stream['disposition'] else ''
		if len(l_resol) == 1: l_resol = ''
		streams[l_id] = {
			'type'  : l_type,
			'codec' : l_codec,
			'bit_rate' : l_bit_rate
		}
		all_arr.append(l_id)
		print 'Stream:',l_id, \
				('('+l_lang+')' if l_lang!='' else '') + \
				(', [D]' if l_def else '') + \
				(', '+l_bit_rate if l_bit_rate else '') + \
				(', '+l_type.capitalize()+': '+l_codec) + \
				(', ch '+l_channel if l_channel else '') + \
				(', '+l_resol if l_resol else '') + \
				(', '+l_title if l_title else '')
	save_query = ''
	if v_count == 1 and a_count == 1 and o_count == 0:
		stream_arr = '0 1'
	elif len(_save_param) == 0:				
		stream_arr = raw_input('Enter stream numers (spase for split, -1 for all): ')
		save_query = raw_input('Use for all? Enter (y/n): ')
	else:
		stream_arr = _save_param
	if len(save_query.lower()) > 0 and save_query.lower()[0] == 'y':
		_save_param = stream_arr
	if stream_arr == "-1":
		stream_arr = all_arr
	else:
		stream_arr = stream_arr.split(' ')
	param_encode = []
	n = 0
	for indx in stream_arr:
		if (streams[indx]['codec'] == 'unknown'):
			continue
		param_encode.append('-map')
		param_encode.append('0:'+indx)
		if streams[indx]['type'] == 'audio' and streams[indx]['codec'] != 'aac':
			param_encode.append('-c:'+str(n))
			param_encode.append(_acodec)

			#param_encode.append('-q:'+str(n))
			#param_encode.append('1')
			
			if len(streams[indx]['bit_rate']) > 0:
				param_encode.append('-b:'+str(n))
				param_encode.append(streams[indx]['bit_rate'])
			n += 1
			continue
		if streams[indx]['type'] == 'video' and streams[indx]['codec'] != 'h264':
			param_encode.append('-c:'+str(n))
			param_encode.append(_vcodec)

			#param_encode.append('-q:'+str(n))
			#param_encode.append('1')

			n += 1
			continue
		if streams[indx]['type'] == 'subtitle' and streams[indx]['codec'] == 'subrip':
			param_encode.append('-c:'+str(n))
			param_encode.append('mov_text')
			n += 1
			continue

		param_encode.append('-c:'+str(n))
		param_encode.append('copy')
		n += 1

	return param_encode

get_aac_codec()

for file in input_files:
	if _auto_out:
		_out = os.path.dirname(file)
	f_name = os.path.splitext(os.path.basename(file))[0]
	f_name = os.path.join(_out,f_name)
	if os.path.exists(f_name+_out_ext):
		print "Exists!",f_name
		continue
	info = get_info(file)
	params = select_streams(info)
	ffmpeg(file,f_name,params)
	print "Dune!",f_name

print "All dune!"
for file in input_files:
	print "From folder:", os.path.dirname(file)
	print "File:", os.path.basename(file)