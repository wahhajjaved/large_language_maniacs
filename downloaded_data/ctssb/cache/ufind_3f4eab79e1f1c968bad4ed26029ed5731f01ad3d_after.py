#! /usr/bin/python
#-*- coding:utf-8 -*-
#Filename: university.py
#Author: wangyu190810
#E-mail: wo190810401@gmail.com
#Date: 2015-01-22
#Description: 

import json
from flask import request,jsonify,g,session
from mysite.model.university import University
from mysite.model.offer import Offer
from mysite.view.base import allow_cross_domain,get_university_img
from mysite.model.user import User

@allow_cross_domain
def set_offer():
    if request.method == "POST":
        data = request.form
        print data
        user_id = session["user_id"]
        num = 0
        while True:
            offer_major_id = data.get("offers["+str(num)+"][majorid]")
            offer_grade = data.get("offers["+str(num)+"][grade]")
            offer_university_id = data.get("offers["+str(num)+"][universityid]")
            offer_type = data.get("offers["+str(num)+"][offertype]")
            scholarship_type = data.get("offers["+str(num)+"][scholarship][type]")
            scholarship_money = data.get("offers["+str(num)+"][scholarship][money]")
            if offer_major_id is None:
                break
            num += 1
            Offer.set_offer(g.db,
                            user_id=user_id,
                            university_id=offer_university_id,
                            major_id=offer_major_id,
                            result=1,
                            offer_type=offer_type,
                            grade=offer_grade,
                            scholarship=scholarship_money,
                            scholarship_type=scholarship_type
            )
        offer_list = list()
        for row in Offer.get_offer_student_info(g.db,user_id):
            offer_dict = dict()
            offer_dict["universityid"] = row.university_id
            offer_dict["universityname"] = University.get_university_from_id(g.db,row.university_id).name
            offer_dict["twodim"] = get_university_img(offer_dict["universityname"],1)
            offer_list.append(offer_dict)
        return jsonify(status="success",
                       offerlist=offer_list,
                       bginf=User.get_user_info(g.db,user_id).bginf)

@allow_cross_domain
def get_offer_student():
    if request.method == "GET":
        university_id,major_id = map(request.args.get,("universityid","majorid"))
        student_list = []
        for row in Offer.get_offer_student(g.db,university_id,major_id):
            student_list.append(row.id)
        return jsonify(studentlist=student_list,
                       status="success")

