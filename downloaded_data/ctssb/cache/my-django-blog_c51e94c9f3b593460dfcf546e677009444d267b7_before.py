from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
import hashlib
from disk.models import FileInfo
from django.utils import timezone
import os
import json
import urllib.request
from activity.mail import SendEmail
import activity

# Create your views here.

def index(request):
	return render(request, 'disk/index.html')

def upload(request):
	if request.method == "POST":
		myFile = request.FILES.get('upfile')
		if not myFile:
			return HttpResponse('no file is uploaded')

		file = myFile.read()
		if not file:
			return HttpResponse('The file is not exists')

		md5 = hashlib.md5(file).hexdigest()
		filename = myFile.name
		filesize = myFile.size
		fileInfo = FileInfo.objects.filter(md5=md5)
		user_ip = get_client_ip(request)
		now = timezone.localtime(timezone.now())

		if not fileInfo:
			try:
				with open('disk/files/{}'.format(md5), 'wb') as fn:
					fn.write(file)
					print('try: files/disk')
			except Exception as e:
				THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))
				my_file = os.path.join(THIS_FOLDER, 'files/{}'.format(md5))
				print('except-before: /files/disk')
				with open(my_file, 'wb') as fn:
					fn.write(file)
					print('except-after: /files/disk')
			else:
				print('no exception: 666')
			finally:
				print('finally: 886')

		print('now is {}'.format(now))
		FileInfo(name=filename,size=filesize,md5=md5,created_date= now, user_ip=user_ip).save()
		return HttpResponseRedirect('/disk/s/{}'.format(md5))
	else:
		return HttpResponse('GET')


def download_list(request, md5):
	fileInfo = FileInfo.objects.filter(md5=md5)
	if not fileInfo:
		return render(request, 'disk/error_404.html')

	files = {
		'name': fileInfo[0].name,
		'size': fileInfo[0].size,
		'downloads': fileInfo[0].downloads,
		'created_date': fileInfo[0].created_date.strftime('%Y-%m-%d %H:%M:%S'),
		'url':'/disk/files/{}'.format(fileInfo[0].name)
	}

	print(files)
	return render(request, 'disk/uploadfiles.html', {'files': files})

def download_detail(request):
	referer = request.META.get('HTTP_REFERER')	
	if not referer:
		return render(request, 'disk/error_404.html')

	md5 = referer[-32:]
	fileinfo = FileInfo.objects.filter(md5=md5)
	if not fileinfo:
		return render(request, 'disk/error_404.html')

	file = None
	try:
		file = open('files/{}'.format(md5), 'rb').read()
	except Exception as e:
		THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))
		my_file = os.path.join(THIS_FOLDER, 'files/{}'.format(md5))
		file = open(my_file, 'rb').read()		
	else:
		pass
	finally:
		pass

	fileinfo[0].downloads = fileinfo[0].downloads + 1
	fileinfo[0].save()
	response=HttpResponse(file)
	response['Content-type'] = 'application/octet-stream'
	return response

def search(request):
	ip = get_client_ip(request)
	name = request.GET.get('kw', '')
	fileInfo = FileInfo.objects.filter(name__contains=name)
	if not fileInfo:
		return HttpResponse('[]')

	fileinfoLen = len(fileInfo)
	fileinfoList = []

	for x in range(0,fileinfoLen):
		files = {
			"ip": fileInfo[0].user_ip,
			"name":fileInfo[0].name,
			"size":fileInfo[0].size,
			"downloads":fileInfo[0].downloads,
			"created_date": fileInfo[0].created_date.strftime('%Y-%m-%d %H:%M:%S'),
			"url":"/disk/files/{}".format(fileInfo[0].name)
		}
		fileinfoList.append(files)

	return HttpResponse(str(fileinfoList))


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def gps(request):
	lng = 113.271709
	lat = 23.1345508
	# //显示数据并返回对应的位置信息
	# http://restapi.amap.com/v3/geocode/regeo?key=您的key&location=113.271709,23.1345508&poitype=商务写字楼&radius=1000&extensions=all&batch=false&roadlevel=0
	url='http://restapi.amap.com/v3/geocode/regeo?key=a8cf9a8f73e9786d454b43ee4e4735ad&location=113.271709,23.1345508'
	#url = 'http://maps.google.com/maps/api/geocode/xml?latlng={},{}&language=zh-CN&sensor=false'.format(lat,lng)
	print(url)
	headers={
		'User-Agent':'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36'
	}

	req = urllib.request.Request(url, headers = headers)
	# req.headers = headers
	res = urllib.request.urlopen(req)
	# res = opener.open(req)
	html = res.read().decode()
	dict1 = json.loads(html)
	address = dict1['regeocode'][u'formatted_address']
	do_send_text_mail(address)
	return HttpResponse(address)

def gpsimage(request):
	now = timezone.localtime().strftime('%Y%m%d%H%M%S')
	lng = 113.271709
	lat = 23.1345508
	# //显示数据并返回对应的位置信息
	# http://restapi.amap.com/v3/geocode/regeo?key=您的key&location=113.271709,23.1345508&poitype=商务写字楼&radius=1000&extensions=all&batch=false&roadlevel=0
	
	url = 'http://restapi.amap.com/v3/staticmap?location={},{}&size=750*300&markers=mid,0xFF0000,A:{},{}&key=a8cf9a8f73e9786d454b43ee4e4735ad'.format(lng,lat,lng,lat)
	# url='http://restapi.amap.com/v3/staticmap?location=113.271709,23.1345508&zoom=10&size=750*300&markers=mid,,A:116.481485,39.990464&key=a8cf9a8f73e9786d454b43ee4e4735ad'
	#url = 'http://maps.google.com/maps/api/geocode/xml?latlng={},{}&language=zh-CN&sensor=false'.format(lat,lng)
	print(url)
	headers={
		'User-Agent':'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.100 Safari/537.36'
	}

	req = urllib.request.Request(url, headers = headers)
	# req.headers = headers
	res = urllib.request.urlopen(req)
	# res = opener.open(req)
	code_img = res.read()
	THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))
	my_file = os.path.join(THIS_FOLDER, 'files/{}.png'.format(now))
	with open(my_file, 'wb') as fn:
		fn.write(code_img)
	print(u'文件保存成功')

	do_send_mail(my_file, 'files/{}.png'.format(now))
	
	return HttpResponse('iimage')

def location(req):
	return render('disk/location.html')

def do_send_mail(my_file, filename):
	# sendMail
	# logger.debug('---submit send mail begin ---')
	emailAddress='36040944@qq.com'
	mailFrom = activity.account.mailFrom
	mailSubject = activity.config.mailSubject
	mailBodyDear = activity.config.mailBodyDear.format('Gracy')
	mailBodyEmbedImage = activity.config.mailBodyEmbedImage
	mailBodyEmbedImagePath = filename
	mailBodySignuture = activity.config.mailBodySignuture
	msg = '{}{}{}'.format(mailBodyDear, mailBodyEmbedImage, mailBodySignuture)

	try:
		SendEmail(mailFrom, emailAddress, None, mailSubject, msg, mailBodyEmbedImagePath)
	except Exception as e:
		print('*************error**************')
		print(e)
		# logger.error('send mail to {} error: {}'.format(emailAddress, e))
		return HttpResponse(e)
	
	# logger.debug('---submit send mail to {} end---'.format(emailAddress))
	print('send mail over')

def do_send_text_mail(text1):
	# sendMail
	# logger.debug('---submit send mail begin ---')
	emailAddress='36040944@qq.com'
	mailFrom = activity.account.mailFrom
	mailSubject = u"「位置已找到, 请确认」"
	mailBodyDear =  u"人员具体位置如下：<br />{}".format(text1)
	mailBodyEmbedImage = activity.config.mailBodyEmbedImage
	mailBodyEmbedImagePath = ""
	mailBodySignuture = u"【敬启】感谢您的查阅，谢谢。"
	msg = '{}{}{}'.format(mailBodyDear, mailBodyEmbedImage, mailBodySignuture)

	try:
		SendEmail(mailFrom, emailAddress, None, mailSubject, msg, mailBodyEmbedImagePath)
	except Exception as e:
		print('*************error**************')
		print(e)
		# logger.error('send mail to {} error: {}'.format(emailAddress, e))
		return HttpResponse(e)
	
	# logger.debug('---submit send mail to {} end---'.format(emailAddress))
	print('send mail over')	