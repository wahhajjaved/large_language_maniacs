# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from django.db import models

# Create your models here.
class Person(models.Model):
    name = models.CharField(max_length=128,
        help_text="Enter the musician name of group musical")

    class Meta:
        verbose_name = "Person"
        verbose_name_plural = "Persons"

    def __unicode__(self):
        return "%s" % (self.name)

    def __str__(self):
        return self.name


class Group(models.Model):
    name = models.CharField(max_length=128,
        help_text="Enter the group musical name")
    members = models.ManyToManyField(Person, through='Membership')

    class Meta:
        verbose_name = "Group"
        verbose_name_plural = "Groups"

    def __unicode__(self):
        return "%s" % (self.name)

    def __str__(self):
        return self.name

    def get_all_members(self):
        return ', '.join(self.members.values_list('name', flat=True).order_by('name'))
    get_all_members.admin_order_field = 'group__members'
    get_all_members.short_description = 'Group members'


class Membership(models.Model):
    person = models.ForeignKey(Person, on_delete=models.CASCADE,
        help_text="Select a musician from the list.")
    group = models.ForeignKey(Group, on_delete=models.CASCADE,
        help_text="Select a group musical from the list.")
    date_joined = models.DateField(help_text="The date that membership was made.")
    invite_reason = models.CharField(max_length=64,
        help_text="Enter the invite reason to this group musical.")
    actived = models.BooleanField(default=True,
        help_text="This membership is actived?")

    class Meta:
        verbose_name = "Membership"
        verbose_name_plural = "Memberships"

    def __unicode__(self):
    	date_joined = self.date_joined.isoformat().replace('', '')
        return "Member: %s from %s" % (self.actived, date_joined)
