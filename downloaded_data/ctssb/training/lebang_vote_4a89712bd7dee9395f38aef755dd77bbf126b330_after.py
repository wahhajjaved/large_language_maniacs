#!coding:utf8
from datetime import datetime, timedelta
from django.utils.decorators import method_decorator
from django.db.models import Model
from django.db.transaction import atomic
from .models import VoteLog, Option, Counter
from .exceptions import VoteError


class VoteService():
    @method_decorator(atomic)
    def user_vote(self, user, option_id):
        try:
            option = Option.objects.get(pk=option_id)
        except Option.DoesNotExist:
            raise VoteError("选项不存在")
        game = option.game
        start_time = datetime.now() - timedelta(hours=game.vote_cicle_hour)
        voted = VoteLog.objects.filter(user=user, option__in=game.options.all(),
                                       created__gte=start_time)
        if len(voted) >= game.max_vote:
            raise VoteError("您已经投过票了")
        log = VoteLog.objects.create(user=user, option_id=option_id)
        option.count_vote += 1
        game.voted_amount += 1
        if len(voted) == 0:
            game.voted_person += 1
        option.save()
        log.save()
        game.save()
        return True


class CounterService():
    def __init__(self, name):
        self.counter, _ = Counter.objects.get_or_create(name=name)

    def add(self):
        self.counter.value += 1
        self.counter.save()
        return self.counter.value

    @property
    def value(self):
        return self.counter.value


class VisterCounterService():
    def __init__(self, object):
        assert isinstance(object, Model)
        if object.hasattr("name"):
            self.uuid = "%s__%s" % (object.name, object.pk)
        else:
            self.uuid = "%s__%s" % (object.__class__.name, object.pk)
        self.cs = CounterService(self.uuid)

    def add(self):
        self.cs.add()
        return self.cs.value

    @property
    def value(self):
        return self.cs.value


vote_service = VoteService()
