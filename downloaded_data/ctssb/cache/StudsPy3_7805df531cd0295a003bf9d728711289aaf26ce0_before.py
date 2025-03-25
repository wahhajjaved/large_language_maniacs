# -*- coding: utf-8 -*-
import requests

#  import django services
from django.contrib.auth.models import User

# import rest framework services
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

# import db models serializers
from mainapp.serializers.serializer import ParaSerializer

# import needed app models
from mainapp.models.userProfile import ProfileModel

from mainapp.models.helpermodels import WorkingDay
from mainapp.models.faculty import Para

# import my own helper methods
from ..utils.custom_utils import *


STUDS_BOT_TOKEN = '289647729:AAENTWQjxU_JMOxnaEqffkwKqjhwV3NWHmU'


class TelegramBot:

    def __init__(self, bot_token):
        self.url = 'https://api.telegram.org/bot' + bot_token

    def send_message(self, message, chat_id):
        url = self.url + "/sendMessage"
        response = dict()
        response['chat_id'] = chat_id
        response['text'] = message
        send = requests.post(url, response)
        return send


STUDS_TELEGRAM_BOT = TelegramBot(STUDS_BOT_TOKEN)


def get_schedule(chat_id):
    profile = ProfileModel.objects.filter(chat_id=chat_id)
    if profile:
        profile = profile[0]
        todaysdate = datetime.date.today()
        weektype = get_weektype(todaysdate)
        current_weekday = datetime.date.today().weekday()  # integer 0-monday .. 6-Sunday
        today = WorkingDay.objects.filter(dayoftheweeknumber=current_weekday)
        if today:
            today = today[0]
            current_semester = StartSemester.objects.get(
                semesterstart__lt=todaysdate,
                semesterend__gt=todaysdate
            )
            if profile.is_student:
                student_group = profile.student_group

                classes_for_today = Para.objects.filter(
                    para_group=student_group,
                    para_day=today,
                    week_type=weektype,
                    semester=current_semester
                )
                if classes_for_today:
                    result = ''
                    for i, para in enumerate(classes_for_today):
                        result += ParaSerializer(para).data['para_number'] + ' : ' \
                                  + ParaSerializer(para).data['discipline'] + "\n"
                    return result
                else:
                    return "Жодної пари сьогодні! Здається у когось з'явився час на саморозвиток :)"
        else:
            return "Довгоочікуваний вихідний... Можна і трішки відпочити :)"
    else:
        return "Жоден користувач в базі не зв'язаний із вашим аккаунтом в Telegram"


def add_chat_id(chat_id, phone_number):
    user = User.objects.filter(username=phone_number)

    if user:
        if not user[0].profilemodel.is_verified:
            user[0].profilemodel.chat_id = chat_id
            user[0].profilemodel.save()
            user[0].save()
            response = 'Ваш код для реєстрації: ' + str(chat_id)
        else:
            response = u'Введений вами аккаунт вже був успішно активований'
    else:
        response = u'Аккаунта з таким номером телефону немає. Будь ласка перевірте номер'

    return response.encode('utf-8')


def userhelp(chat_id):
    return "commands:\n/schedule" + '\n' + 'chat_id: ' + str(chat_id)


def forgot_password(chat_id):
    user_profile = ProfileModel.objects.filter(chat_id=chat_id)
    if user_profile:
        user = User.objects.filter(user__profilemodel=user_profile)[0]
    else:
        return "Жоден користувач в базі не зв'язаний із вашим аккаунтом в Telegram"

    if user is not None:
        temp_password = generate_new_password()
        user.set_password(temp_password)
        user.save()
        message = u'Ваш новий пароль:\n' + temp_password
        message1 = u"Ви можете змінити його в нашлаштуваннях вашого профілю"
        return message + message1
    else:
        return "Жоден користувач в базі не зв'язаний із вашим аккаунтом в Telegram"


COMMANDS = {
    '/help': userhelp,
    '/schedule': get_schedule,
    '/forgot_password': forgot_password}


class TelegramBotView(APIView):
    permission_classes = (AllowAny, )

    def post(self, request):
        data = request.data
        chat_id = data['message']['chat']['id']
        user_command = data['message']['text']

        func = COMMANDS.get(user_command.lower())
        if func:
            req = STUDS_TELEGRAM_BOT.send_message(func(chat_id), chat_id)
        else:
            if user_command[0:3] == '380' and len(user_command) == 12:
                req = STUDS_TELEGRAM_BOT.send_message(add_chat_id(chat_id, user_command), chat_id)
            else:
                req = STUDS_TELEGRAM_BOT.send_message(userhelp(chat_id), chat_id)

        return Response(req.json(), status=req.status_code)
