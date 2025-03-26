from django.shortcuts import render, redirect
from django.shortcuts import render_to_response,get_object_or_404
from django.template import RequestContext
from django.http import HttpResponse
from rest_framework.renderers import JSONRenderer
from rest_framework.parsers import JSONParser
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout as auth_logout
from django.views.decorators.csrf import csrf_exempt
from hackathon import models
from hackathon.serializer import *
from hackathon.models import AnswerHistory
from hackathon.serializer import QuestionSerializer
from django.contrib.auth.models import User
from django.db.models import F
from django.db.models import Q
import operator
from django.db import transaction
from urllib import FancyURLopener
import json
import re
from urllib import urlencode
import urllib2
import random

HIGHLIGHT_SCORE = 0.2

class JSONResponse(HttpResponse):
    """
    An HttpResponse that renders its content into JSON.
    """
    def __init__(self, data, **kwargs):
        content = JSONRenderer().render(data)
        kwargs['content_type'] = 'application/json'
        super(JSONResponse, self).__init__(content, **kwargs)


@login_required(login_url='/login/')
def index(request):
    return render_to_response('index.html', context_instance=RequestContext(request))

def login(request):
    return render(request, 'login.html')

def login_failed(request):
    return render(request, 'login.html')

def logout(request):
    auth_logout(request)
    return redirect('/login/')

@login_required(login_url='/login/')
@csrf_exempt
@transaction.atomic
def questions_list(request):
    if request.method == 'GET':
        my_answers = models.AnswerHistory.objects.filter(user_id=request.user.id)
        my_answers_id = list(x.question_id for x in my_answers)

        my_questions = models.Question.objects.filter(user_id=request.user.id).exclude(id__in=my_answers_id)
        my_questions_id = list(x.id for x in my_questions)

        questions = models.Question.objects.all().exclude(id__in=my_answers_id).order_by('-left_count')

        questions_id = []
        for question in questions:
            questions_id.append(question.id)
            question.view_count = question.view_count + 1
            question.save()
            if len(questions_id) >= 50:
                break

        questions = models.Question.objects.filter(id__in=questions_id)
        sample_size = min(10,questions.count())
        questions = random.sample(questions, sample_size)
        questions_id = list(x.id for x in questions)

        new_questions = models.Question.objects.filter(Q(id__in=questions_id)|
                                                       Q(id__in=my_questions_id)).order_by('create_time')
        serializer = QuestionSerializer(new_questions, many=True)
        return JSONResponse(serializer.data)

    if request.method == 'POST':
        data = JSONParser().parse(request)
        data['user'] = request.user.id
        try:
            data['url'] = fetch_related_image(data['question'])
        except Exception as e:
            data['url'] = 'https://cdn.vectorstock.com/i/composite/88,69/question-mark-vector-1068869.jpg'
        serializer = QuestionCreateSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return JSONResponse(serializer.data, status=201)
        return JSONResponse(serializer.errors, status=400)

class MyOpener(FancyURLopener):
    version = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; it; rv:1.8.1.11) Gecko/20071127 Firefox/2.0.0.11'

def fetch_related_image(question):
    searchTerm = question
    params = {'v': '1.0', 'q': searchTerm.encode('utf8'), 'start': 0, 'userip': 'MyIP'}
    params = urlencode(params)
    params = params.replace(' ','%20')
    url = ('https://ajax.googleapis.com/ajax/services/search/images?' + params)
    request = urllib2.Request(url, None, {'Referer': 'testing'})
    response = urllib2.urlopen(request)

    results = json.load(response)
    data = results['responseData']
    dataInfo = data['results']

    for myUrl in dataInfo:
        return myUrl['unescapedUrl']

@login_required(login_url='/login/')
@csrf_exempt
def questions_edit(request,pk):
    try:
        question = models.Question.objects.get(pk=pk)
    except models.Question.DoesNotExist:
        return HttpResponse(status=404)

    if request.method == 'POST':
        data = JSONParser().parse(request)
        data['user_id'] = request.user.id
        serializer = QuestionCreateSerializer(question, data=data)
        if serializer.is_valid():
            serializer.save()
            return JSONResponse(serializer.data)
        return JSONResponse(serializer.errors, status=400)

    elif request.method == 'DELETE':
        question.delete()
        return HttpResponse(status=204)

@login_required(login_url='/login/')
@csrf_exempt
def my_questions(request):
    if request.method == 'GET':
        questions = models.Question.objects.filter(user_id=request.user.id
                                                   ).order_by('-create_time')[:10]
        serializer = QuestionSerializer(questions, many=True)
        return JSONResponse(serializer.data)


def get_best_match_questions(questions, keyword, n):
    ques_dict = {}
    keys = keyword.split(' ')
    for question in questions:
        same_num = 0
        for key in keys:
            if question.question.lower().find(key.lower()) > 0:
                same_num += 1
        ques_dict[question] = same_num
    sorted_x = sorted(ques_dict.items(), key=operator.itemgetter(1), reverse=True)
    res_dict = sorted_x[:n]
    result = [res[0] for res in res_dict]
    return result


@login_required(login_url='/login/')
@csrf_exempt
def questions_search(request):
    if request.method == 'POST':
        data = JSONParser().parse(request)
        keywords = data['keywords']
        num = 3
        if 'number' in data:
            num = data['number']
        questions = models.Question.objects.all()
        questions = get_best_match_questions(questions, keywords, num)
        serializer = QuestionSerializer(questions, many=True)
        return JSONResponse(serializer.data)

@login_required()
@csrf_exempt
def user(request):
    if request.method == 'GET':
        try:
            user = User.objects.get(id=request.user.id)
        except models.User.DoesNotExist:
            return HttpResponse(status=404)

        serializer = UserSerializer(user)
        mydata = serializer.data
        try:
            user_profile = models.User_Profile.objects.get(user_id=user.pk)
        except:
            return HttpResponse(status=404)

        mydata['avatar'] = '/avatar/{0}_social.jpg'.format(user.pk)
        highlights = []
        sum = 0.0
        myAnswers = AnswerHistory.objects.filter(user=user)
        for answer in myAnswers:
            ques = answer.question
            if ques.right_count + ques.left_count == 0:
                continue
            if answer.answer == AnswerHistory.LEFT:
                score = ques.left_count * 1.0 / (ques.right_count + ques.left_count)
                sum += score
                if score < HIGHLIGHT_SCORE:
                    highlights.append(ques)
            elif answer.answer == AnswerHistory.RIGHT:
                score = ques.right_count * 1.0 / (ques.right_count + ques.left_count)
                sum += score
                if score < HIGHLIGHT_SCORE:
                    highlights.append(ques)

        highlights = highlights[:5]
        if len(highlights) > 0:
            qSerializer = QuestionSerializer(highlights, many=True)
            mydata['highlight'] = qSerializer.data

        uniqueness = 0
        if len(myAnswers):
            uniqueness = 1 - sum/len(myAnswers)

        mydata['uniqueness'] = uniqueness
        return JSONResponse(mydata)

@csrf_exempt
@login_required(login_url='/login/')
def answers_list(request):
    if request.method == 'GET':
        answers = AnswerHistory.objects.filter(user=request.user)
        serializer = AnswerHistorySerializer(answers, many=True)
        return JSONResponse(serializer.data)

@login_required(login_url='/login/')
@csrf_exempt
def answers(request, question_id):
    try:
        question = models.Question.objects.get(pk=question_id)
    except models.Question.DoesNotExist:
        return HttpResponse(status=404)

    if request.method == 'POST':
        hasAnswers = AnswerHistory.objects.filter(user_id=request.user.pk, question_id=question.pk)
        if hasAnswers:
            result = {'isExist':1}
            return JSONResponse(result)
        data = JSONParser().parse(request)
        data['user'] = request.user.pk
        data['question'] = question.pk
        serializer = AnswerHistoryCreateSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            ans = data['answer']
            if ans == AnswerHistory.LEFT:
                question.left_count += 1
            elif ans == AnswerHistory.RIGHT:
                question.right_count += 1
            elif ans == AnswerHistory.SKIP:
                question.skip_count += 1
            elif ans == AnswerHistory.REPORT:
                question.report_count += 1
            question.save()
            return JSONResponse(serializer.data)
        return JSONResponse(serializer.errors, status=400)
