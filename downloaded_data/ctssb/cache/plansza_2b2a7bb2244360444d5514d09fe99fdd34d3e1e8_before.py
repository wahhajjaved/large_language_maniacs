import arrow
import requests
from django.contrib.auth import user_logged_in
from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from social.apps.django_app.default.fields import JSONField

from .utils import get_graph


def get_random_photo() -> str:
    return requests.head("https://source.unsplash.com/people/1500x550", allow_redirects=True).url


class Event(models.Model):
    name = models.CharField(max_length=255)
    facebook_id = models.BigIntegerField(null=True, blank=True, unique=True)
    facebook_data = JSONField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    image = models.URLField(default=get_random_photo)


class EventHour(models.Model):
    event = models.ForeignKey(Event, related_name="hours")
    users = models.ManyToManyField(User, related_name="hours")
    time = models.DateTimeField()


class Friend(models.Model):
    user = models.OneToOneField(User, related_name="friend")
    friends = models.ManyToManyField("self", symmetrical=True)

    def __str__(self):
        return self.user.username

    def update(self):
        with transaction.atomic():
            # TODO: this may not work for more than 15 or so friends
            self.friends = [Friend.objects.get(user__social_auth__uid=x["id"]) for x in
                            get_graph(self.user).get_connections("me", "friends")["data"]]
            self.save()


@receiver(user_logged_in)
def friend_reroll(sender, request, user, **kwargs):
    try:
        f = user.friend
    except:
        f = Friend.objects.create(user=user)
    f.update()


@receiver(post_save, sender=Event)
def generate_hours(sender, instance, created, **kwargs):
    if len(instance.facebook_data.keys()) and instance.hours.count() < 1:
        start = arrow.get(instance.facebook_data["start_time"])
        end = arrow.get(instance.facebook_data["end_time"])
        while start < end:
            EventHour.objects.create(event=instance, time=start.timestamp)
            start = start.replace(hours=+0.5)
