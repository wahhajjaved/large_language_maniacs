from django.shortcuts import render
from .models import *
from django.http import HttpResponse
import requests
from shop.models import shop_data
from django.views.decorators.csrf import csrf_exempt
# Create your views here.
@csrf_exempt
def send_offer(request):
	response_json={}
	if request.method=="GET":
		try:
			for x,y in request.GET.items():
				print x,":",y
			#category_id= str(request.POST.get("category_id"))
			shop_id=str(request.GET.get("shop_id"))
			print"............................shopid",shop_id
			shop_row=shop_data.objects.get(shop_id=int(shop_id))
			response_json["success"]=True
			response_json["shop_id"]=int(shop_id)
			response_json["shop_name"]=str(shop_row.name)
			response_json["shop_description"]=str(shop_row.description)
			response_json["shop_image"]=request.scheme+'://'+request.get_host()+'/media/'+str(shop_row.image)
			response_json["shop_address"]=str(shop_row.address)
			response_json["offer_list"]=[]
			print "debuuged 25"
			for o in offer_data.objects.filter(shop_id=int(shop_id)):
				if o.active==True:
					temp_json={}
					temp_json["offer_id"]=int(o.offer_id)
					temp_json["name"]=str(o.name)
					temp_json["description"]=str(o.description)
					temp_json["validity"]=str(o.validity)
					temp_json["image"]=request.scheme+'://'+request.get_host()+'/media/'+str(o.image)
					temp_json["price"]=int(o.price)
					response_json["offer_list"].append(temp_json)
		except Exception,e:
			print "e@offer",e
			response_json["success"]=False
			response_json["message"]=" offer_data not  found"
	else:
		response_json['success']=False
		response_json['message']="not get method"
	print str(response_json)
	return HttpResponse(str(response_json))
# Create your views here.
