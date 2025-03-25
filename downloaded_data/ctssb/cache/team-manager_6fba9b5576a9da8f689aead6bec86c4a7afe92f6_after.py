# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.shortcuts import render
from django.contrib.auth.models import User
from django.contrib.auth import login as log
from django.contrib.auth import logout as loggedout
from django.views.decorators.csrf import csrf_exempt
import json
from django.contrib.auth import authenticate
from django.http import JsonResponse
from .models import *
import re
from django.db.models import Q
import uuid
# Create your views here.

'''This function adds the member to the team'''

def verifyEmail(email):
	if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
		return False
	return True

@csrf_exempt
def addMember(request):
	if request.method=='POST':
		data = request.body
		data = json.loads(data)

		first_name = data["first_name"]
		last_name = data["last_name"]
		email = data["email"]
		role = data["role"]
		phone = data["phone"]
		if (len(phone) != 10) or (not phone.isdigit()):
			return JsonResponse({"failed":"invalid attribute values"})

		role_num=1
		if role.lower()=="admin":
			role_num=0

		if not verifyEmail(email):
			return JsonResponse({"failed":"invalid attribute values"})

		try:
			member = Member(first_name=first_name,last_name=last_name,email=email,phone=phone,role=role_num)
			member.save()
		except:
			return JsonResponse({"failed":"invalid attribute values"})

		return JsonResponse({"id":member.id,"first_name":member.first_name,"last_name":member.last_name,"email":member.email,"phone":member.phone,"role":role})


'''This function deletes the team member'''
@csrf_exempt
def deleteMember(request):
	if request.method=="DELETE":
		data = request.body
		data = json.loads(data)
		id_member = data["id"]
		try:
			member = Member.objects.get(pk=id_member)
			member.delete()
			return JsonResponse({})
		except:
			return JsonResponse({"failed":"Invalid id"})

'''This function can be used to update the team member details'''
@csrf_exempt
def update(request):
	if request.method=='POST':
		data = request.body
		data = json.loads(data)

		id_member = data["id"]

		member=None
		try:
			member = Member.objects.get(pk=id_member)
		except:
			return JsonResponse({"failed":"invalid id"})
		if "first_name" in data:
			first_name = data["first_name"]
			member.first_name=first_name
		if "last_name" in data:
			last_name = data["last_name"]
			member.last_name=last_name	
		if "email" in data:
			email = data["email"]
			member.email=email
		if "role" in data:
			role = data["role"]
			if role=="admin":
				member.role=0
			else:
				member.role=1
		if "phone" in data:
			phone = data["phone"]
			if (len(phone) != 10) or (not phone.isdigit()):
				return JsonResponse({"failed":"invalid attribute values"})
			member.phone=phone
		member.save()
		role=None
		if member.role==1:
			role="regular"
		else:
			role="admin"
		return JsonResponse({"id":member.id,"first_name":member.first_name,"last_name":member.last_name,"email":member.email,"phone":member.phone,"role":role})

'''This function can be used to view all the team members'''
@csrf_exempt
def getMembers(request):
	if request.method=="GET":
		members = Member.objects.all()
		list_of_members=[]
		for member in members:
			role=None
			if member.role==1:
				role="regular"
			else:
				role="admin"
			list_of_members.append({
					"first_name":member.first_name,
					"last_name":member.last_name,
					"email":member.email,
					"id":member.id,
					"role":role
				})
		return JsonResponse({"data":list_of_members})
