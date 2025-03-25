# -*- coding: utf-8 -*-

import json
import re
from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
from .models import ScheduleModel, ScheduleTimes
from django.core.mail import send_mail
from django.core.urlresolvers import reverse


rec_created = u'''
Здравствуйте, %s!

Вы успешно зарегистрировались на маршрут "%s".

Дата посещения маршрута: %s; %s

ВНИМАНИЕ!
Отменить регистрацию Вы сможете, перейдя по ссылке:

%s


Благодарим за участие,
оргкомитет проекта "Наука в путешествии. ПриМорье."
'''


rec_removed = u'''
Здравствуйте, %s!

Вы успешно отменили регистрацию (дата: %s%s) на маршрут "%s".

Благодарим за участие,
оргкомитет проекта "Наука в путешествии. ПриМорье."
'''


def validate(uname, phone):
    err_msg = ''
    if not re.match(r'^[\-\+\d]+$', phone):
        err_msg = 'Неправильный формат тел. номера'
    if not uname:
        err_msg = 'Имя не задано'
    return err_msg

@never_cache
@csrf_exempt
def register_user(request):
    response_data = {'error' : '', 'msg': '', 'ferr': ''}

    if request.method == 'GET':
        hashid = request.GET.get('hashid', '')
        if hashid and ScheduleModel.objects.filter(hashid=hashid).exists():
            try:
                obj = ScheduleModel.objects.filter(hashid=hashid)[0]
                ctime = str(obj.time.time)
                cdate = str(obj.time.date.date)
                cname= obj.username
                cmail = obj.email
                path = obj.time.date.name.name
                obj.delete()
                send_mail(u'Отмена регистрации на маршрут "Наука в путешествии. ПриМорье."',
                      rec_removed % (cname, cdate, ctime, path),
                      'ecocenter@botsad.ru', [cmail,], fail_silently=True)
            except:
                HttpResponse('<h2>Запись с Вашим ID не найдена.</h2>')
            return HttpResponse('<h2>Поздравляем! Вы успешно отменили регистрацию!</h2>')

    if request.method == 'POST':
        timepk = request.POST.get('timepk', None)
        uname = request.POST.get('username', '')
        uphone = request.POST.get('phone', '')
        umail = request.POST.get('email', '')
        unum = request.POST.get('num', '')
        upk = request.POST.get('upk', '')
        try:
            upk = int(upk)
        except ValueError:
            return HttpResponse(json.dumps({'error': 'Внутренняя ошибка при определении принадлежности к расписанию'}))

        try:
            user = get_user_model().objects.get(pk=upk)
        except get_user_model().DoesNotExist:
            return HttpResponse(json.dumps({'error': 'Внутренняя ошибка при определении принадлежности к расписанию'}))

        err_msg = validate(uname, uphone)
        if not err_msg:
            try:
                timeobj = ScheduleTimes.objects.get(id=timepk)
            except ScheduleTimes.DoesNotExist:
                response_data.update({'error': 'Неправильно выбрано время'})
                return HttpResponse(json.dumps(response_data), content_type="application/json")
            if timeobj.get_registered > 0 and not timeobj.date.dateonly:
                response_data.update({'error': 'Выбранное время занято'})
                return HttpResponse(json.dumps(response_data), content_type="application/json")
            elif timeobj.get_free_places <=0 and timeobj.date.dateonly:
                response_data.update({'error': 'Выбранная дата занята'})
                return HttpResponse(json.dumps(response_data), content_type="application/json")
            try:
                unum = int(unum)
                if ScheduleModel.objects.filter(username=uname, phone=uphone, emial=umail, num=unum, time=timeobj, user=user).exists():
                    response_data.update({'error': 'Вы уже зарегистрированы на это время/дату'})
                    return HttpResponse(json.dumps(response_data), content_type="application/json")
                umod = ScheduleModel.objects.create(username=uname,
                                                    phone=uphone,
                                                    email=umail,
                                                    num=unum,
                                                    time=timeobj,
                                                    user=user)
                hashurl = 'http://botsad.ru' + reverse('bgi-scheduler') + '?hashid=' + umod.hashid
                basic_mail = umod.user.email if umod.user else 'ecocenter@botsad.ru'
                send_mail(u'Регистрация на маршрут "Наука в путешествии. ПриМорье."',
                            rec_created%(uname, umod.time.date.name.name, umod.time.date.date, (u' время: ' + str(umod.time.time)) if not umod.time.date.dateonly else '', hashurl),
                            'ecocenter@botsad.ru', [umod.email, basic_mail] if basic_mail else [umod.email], fail_silently=True)
                response_data.update({'msg': 'Вы успешно зарегистрировались'})
            except:
                response_data.update({'error': 'Что-то пошло не так при регистрации'})
        else:
            response_data.update({'error':err_msg})
    else:
        response_data['error'] = 'Неправильный запрос'

    return HttpResponse(json.dumps(response_data), content_type="application/json")
