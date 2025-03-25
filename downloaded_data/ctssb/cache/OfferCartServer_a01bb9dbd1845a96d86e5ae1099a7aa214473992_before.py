from django.shortcuts import render
from django.http import HttpResponse,JsonResponse
from .models import *
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def version(request):
	version_row= version_data.objects.get(ver_type='production')
	version=version_row.version
	compulsory_update=version_row.compulsory_update
	response_json={}
	response_json['version']=version
	response_json['compulsory_update']=compulsory_update
	if(request.method=='GET'):
		for x,y in request.GET.items():
			print x,":",y

		try:
			fcm=str(request.GET.get("fcm"))
			#fcm="tmp from server"
			print "fcm recieved",fcm
			if fcm!="None":
				try:
					fcm_list=fcm_data.objects.get(fcm=fcm)
					response_json["success"]=True
					response_json["message"]="already added"
				except:
					fcm_list=fcm_data.objects.create(fcm=fcm)
					response_json["success"]=True
					response_json["message"]="successfully added"
			else:
				response_json["success"]=False
				response_json["message"]="fcm none recieved"

		except:
			response_json["success"]=False
			response_json["message"]="send fcm : invalid parameters"
	else:
		response_json["success"]=False
		response_json["message"]="not get method"
				
	print str(response_json)
	return JsonResponse(response_json)

def initial(request):
	return HttpResponse("<a href=./login>admin_login</a>")



