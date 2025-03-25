from models import ChatWxToDevice, ChatDeviceToWx, VToyUser, ChatVoices, DeviceStatus, DeviceInfo
import logging

logger = logging.getLogger('consolelogger')

class DBWrapper:
	from datetime import datetime
	utc_begin_datetime = datetime.utcfromtimestamp(0)
	# @staticmethod
	# def restoreWxVoice(fromUser, sessionId, createTime, content, msgId, openId, deviceId, toUser='wxgzzh', msgType='device_voice', deviceType=''):
	# 	"""Note: the cotent parameter is encoded by base64, this function will decode and then store to db."""

	# 	chatobj = ChatWxToDevice(from_user=fromUser, session_id=sessionId, create_time=createTime, device_id=deviceId, device_type=deviceType, msg_id=msgId, open_id=openId)

	# 	if msgType == 'device_voice':
	# 		chatobj.message_type = 0
	# 	elif msgType == 'device_text':
	# 		chatobj.message_type = 1
	# 	elif msgType == 'device_image':
	# 		chatobj.message_type = 2

	# 	voice = ChatVoices(voice_data=base64.b64decode(content))
	# 	voice.save()

	# 	chatobj.voice_id = voice.id
	# 	chatobj.save()

	@staticmethod
	def receiveWxVoice(fromuser,createtime,deviceid,devicetype,msgid, vdata):
		"""
		1) restore the voice data into ChatWxToDevice, ChatVoices 
		2) if user doesn't exist, add user into VToyUser 
		3) if DeviceStatus doesn't exist, create DeviceStatus instance into DeviceStatus table. if exist, update the latest_msg_receive_time of DeviceStatu.
		"""
		try:
			try:
				userobj = VToyUser.objects.get(weixin_id=fromuser)
			except VToyUser.DoesNotExist:
				userobj = VToyUser(username=fromuser, weixin_id=fromuser)
				userobj.save()
			
			chatobj = ChatWxToDevice(from_user=userobj, create_time=createtime, message_type='0', device_id=deviceid, \
				device_type=devicetype, msg_id=msgid)
			
			voice = ChatVoices(voice_data=vdata)
			voice.save()

			chatobj.voice_id = voice.id
			chatobj.save()

			#update device status
			try:
				logger.debug("begin to update devicestatus")
				devicestatus = DeviceStatus.objects.get(device_id=deviceid)
				devicestatus.latest_msg_receive_time = createtime
				userobj.save()
				logger.debug("end update devicestatus")

			except DeviceStatus.DoesNotExist:
				logger.debug("begin to create devicestatus")
				userobj = DeviceStatus(device_id=deviceid, latest_msg_receive_time=createtime, \
					lastest_syncfromdevice_time=DBWrapper.utc_begin_datetime)
				userobj.save()
				logger.debug("end to create devicestatus")

			return True,None
		except Exception,info:
			return False,info
	
	@staticmethod
	def registerDevice(deviceId, macAddress, connectProtocol='4',authKey='', connStrategy='1', closeStrategy='1', cryptMethod='0', authVer='0', manuMacPos='-1', serMacPos='-2'):
		"""
		store the device info
		"""
		try:
			deviceInfo = DeviceInfo(device_id=deviceId, mac=macAddress, connect_protocol=connectProtocol, auth_key=authKey, conn_strategy=connStrategy, \
			 close_strategy=closeStrategy, crypt_method=cryptMethod, auth_ver=authVer, manu_mac_pos=manuMacPos, ser_mac_pos=serMacPos)
			deviceInfo.save()

			return True,None
		except Exception,info: 
			return False,info
	# @staticmethod
	# def restoreDeviceVoice(toUser, createTime, deviceId, sessionId, content, msgType='device_voice', formUser='wxgzzh', deviceType=''):
	# 	"""Note: the content parameter should be binrary. this function will store to db directly."""

	# 	chatobj = ChatDeviceToWx(to_user=toUser, session_id=sessionId, create_time=createTime, device_id=deviceId, device_type=deviceType)
	# 	if msgType == 'device_voice':
	# 		chatobj.message_type = 0
	# 	elif msgType == 'device_text':
	# 		chatobj.message_type = 1
	# 	elif msgType == 'device_image':
	# 		chatobj.message_type = 2

	# 	voice = ChatVoices(voice_data=content)
	# 	voice.save()

	# 	chatobj.voice_id = voice.id
	# 	chatobj.save()
