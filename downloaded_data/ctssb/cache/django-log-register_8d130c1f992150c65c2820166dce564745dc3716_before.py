from datetime import datetime
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.db import models
from log_register.managers import LotManager, LogManager
from log_register.settings import ERROR, DEBUG, SUCCESS, WARNING, INFO


class Lot(models.Model):
    """
    This model represents a lot of logs.
    * The 'register_start' field represents when the log was created, but doesn't represent the first log.
    * The 'register_end' field just represent when you end to register log for this lot, This field is set when you
    call the 'close' method.
    You must not set this field manually, but (like everything in python) you can, of course. :)
    * The 'single' field represents that this Lot is a unique (must be) lot instance for a particular object in
    database.
    You must not set this field manually, but (like everything in python) you can, of course. :)
    * The 'content_type', 'object_id' and 'lot_object' fields represent (polymorphically) the object
    in database, where happen the logs.
    If single is False (be default it's just like that), the three field don't make sense (For me and my mind)

    See the examples (When I'll write them :) )
    """
    register_start = models.DateField(auto_now_add=True)
    register_end = models.DateField(blank=True, null=True)

    single = models.BooleanField(default=False)
    content_type = models.ForeignKey(ContentType, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    lot_object = generic.GenericForeignKey()

    objects = LotManager()

    def close(self):
        """
        This method set the current date time and, by convention, you wont log
         anything with it. but you can :)
        """
        self.register_end = datetime.now()
        self.save()
        return self

    def info_count(self):
        """
        Return the count of info logs
        """
        level = INFO
        return self.__get_count(level)

    def debug_count(self):
        """
        Return the count of debug logs
        """
        level = DEBUG
        return self.__get_count(level)

    def warning_count(self):
        """
        Return the count of warning logs
        """
        level = WARNING
        return self.__get_count(level)

    def error_count(self):
        """
        Return the count of error logs
        """
        level = ERROR
        return self.__get_count(level)

    def success_count(self):
        """
        Return the count of success logs
        """
        level = SUCCESS
        return self.__get_count(level)

    def success(self, reason, extra_data="", log_object=None):
        """
        Register a successful log.
        """
        level = SUCCESS
        log = self.log(reason=reason, extra_data=extra_data, level=level, log_object=log_object)
        return log

    def warning(self, reason, extra_data="", log_object=None):
        """
        Register a warning log.
        """
        level = WARNING
        log = self.log(reason=reason, extra_data=extra_data, level=level, log_object=log_object)
        return log

    def info(self, reason, extra_data="", log_object=None):
        """
        Register a info log.
        """
        level = INFO
        log = self.log(reason=reason, extra_data=extra_data, level=level, log_object=log_object)
        return log

    def error(self, reason, extra_data="", log_object=None):
        """
        Register a error log.
        """
        level = ERROR
        log = self.log(reason=reason, extra_data=extra_data, level=level, log_object=log_object)
        return log

    def debug(self, reason, extra_data="", log_object=None):
        """
        Register a debug log.
        """
        level = DEBUG
        log = self.log(reason=reason, extra_data=extra_data, level=level, log_object=log_object)
        return log

    def log(self, reason, extra_data="", level=INFO, log_object=None):
        """
        Register a log.
        Only the param 'reason' it's required.
        """
        log = Log(reason=reason, extra_data=extra_data, level=level)
        if not log_object is None:
            log.log_object = log_object
        log.save()
        return log

    def __get_count(self, level):
        count = self.logs.filter(lovel=level).count()
        return count


class Log(models.Model):
    """
    This method represent the a log of something that happen.
    Only the 'lot' and 'reason' field are required.

    * The 'reason' field represents the answer for "Why this log happen?" (See the examples)
    * The 'extra_date' field represent the the answer for "What is the context of this log?",
    "What details are useful?"
    * The 'level' field represents the level of this log. By default, there are five, the same of django-messages
    framework. In the near future, you'll be able to customize them. Just wait :)
    * The 'content_type', 'object_id' and 'log_object' represent the object inn the database that cause the error.
    This is useful to find them and fix some warnings that don't are fatal errors. (See the examples)

    """
    LEVEL_CHOICES = (
        (DEBUG, 'DEBUG'),
        (INFO, 'INFO'),
        (SUCCESS, 'SUCCESS'),
        (WARNING, 'WARNING'),
        (ERROR, 'ERROR'),
    )
    lot = models.ForeignKey(Lot, related_name="logs")
    reason = models.CharField(max_length=200)
    extra_data = models.TextField(blank=True, null=True)
    level = models.CharField(max_length=5, choices=LEVEL_CHOICES, default=INFO)

    content_type = models.ForeignKey(ContentType, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    log_object = generic.GenericForeignKey()

    objects = LogManager()