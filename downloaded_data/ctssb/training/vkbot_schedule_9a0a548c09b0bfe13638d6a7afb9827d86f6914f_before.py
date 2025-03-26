from vkbot_schedule.models import *


def command_analyzer(query, uid):

    list_query = query.split(' ') # сохраняеи запрос в виде списка через пробел
    command = list_query[0].lower()
    q = list_query[1:]

    dict_command = {'!каждыйдень': query_analyzer_every_day,
                    '!каждуюнеделю': query_analyzer_every_week,
                    '!каждыймесяц': query_analyzer_every_month,
                    '!каждыйгод': query_analyzer_every_year,
                    '!день': query_analyzer_day}

    try:
        response = dict_command[command](q, uid)
    except KeyError:
        response = 'Такой команды не существует'
    else:
        response = 'Команда успешно сохранена и активирована!' + response
    finally:
        return response


def query_analyzer_every_day(query, uid):

    times = query[1].split(',') # разбиваем времена через запятую
    repeat = int(query[-1]) if len(query) == 4 else 1  # Сколько раз повторять?
    instance_times = [] # необходимые экземпляры для сохранения

    message = (' ').join(query[2].split('-')) # сообщение наше за место пробелов дефисы

    # Сохраняем время и запоминаем экземпляры для создания связи
    for time in times:
        inst = TimesForEveryDay(time=time, repeat_count=repeat)
        inst.save()
        instance_times.append(inst)

    # Создаем задание в базе данных
    sed = ScheduleEveryDay(uid=uid, name=query[0], message=message)
    sed.save()

    # сохраняем ранее созданые экземпляры времён в наш экземлпяр задания
    for time in instance_times:
        sed.times.add(time)

    return 'Теперь я буду напоминать тебе о твоей задаче ежедневно в %s!' % query[1]


def query_analyzer_every_week(query, uid):
    message = (' ').join(query[2].split('-')) # сообщение наше за место пробелов дефисы
    ScheduleEveryWeek(uid=uid, name=query[0], week_day=query[1], message=message).save()

    return 'Теперь я буду напоминать тебе в %s о твоей задаче!' % query[1]


def query_analyzer_every_month(query, uid):
    message = (' ').join(query[2].split('-')) # сообщение наше за место пробелов дефисы
    ScheduleEveryMonth(uid=uid, name=query[0], days=query[1], message=message).save()

    return 'Теперь я буду напоминать тебе о твоей задаче по %s числам ежемесячно!' % query[1]


def query_analyzer_every_year(query, uid):
    message = (' ').join(query[2].split('-')) # сообщение наше за место пробелов дефисы
    ScheduleEveryYear(uid=uid, name=query[0], day=query[1], message=message).save()

    return 'Теперь я буду напоминать тебе о твоей задаче %s ежегодно!' % query[1]


def query_analyzer_day(query, uid):

    message = (' ').join(query[2].split('-')) # сообщение наше за место пробелов дефисы
    ScheduleDay(uid=uid, name=query[0], time=query[1], message=message).save()

    return 'Теперь я напомню о твоей задаче %s.' % query[1]




def answer_done(uid, name_schedule):
    """
    Эта функция будет обрабатывать подтвреждение выполнения задания.
    На вход приходит uid пользователя и название задания
    Если данные верны, то функция запишет в первом времени done в True
    """
    try:
        command = ScheduleEveryDay.objects.get(uid=uid, name=name_schedule)
    except:
        return False

    for time in command.times.all():
        if not time.repeat_count:
            time.repeat_count = 0
            time.save()
            break


