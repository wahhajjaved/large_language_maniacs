
from datetime import datetime

from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext_lazy as _

try:
    from notification import models as notification
except ImportError:
    notification = None


class AnnouncementManager(models.Manager):
    """
    A basic manager for dealing with announcements.
    """
    def current(self, exclude=[], site_wide=False, for_members=False):
        """
        Fetches and returns a queryset with the current announcements. This
        method takes the following parameters:
        
        ``exclude``
            A list of IDs that should be excluded from the queryset.
        
        ``site_wide``
            A boolean flag to filter to just site wide announcments.
        
        ``for_members``
            A boolean flag to allow member only announcements to be returned
            in addition to any others.
        """
        queryset = self.all()
        if site_wide:
            queryset = queryset.filter(site_wide=True)
        if exclude:
            queryset = queryset.exclude(pk__in=exclude)
        if not for_members:
            queryset = queryset.filter(members_only=False)
        queryset = queryset.order_by("-creation_date")
        return queryset


class Announcement(models.Model):
    """
    A single announcment.
    """
    title = models.CharField(_("title"), max_length=50)
    content = models.TextField(_("content"))
    creator = models.ForeignKey(User, verbose_name=_("creator"))
    creation_date = models.DateTimeField(_("creation_date"), default=datetime.now)
    site_wide = models.BooleanField(_("site wide"), default=False)
    members_only = models.BooleanField(_("members only"), default=False)
    
    objects = AnnouncementManager()
    
    @models.permalink
    def get_absolute_url(self):
        return ("announcement_detail", [str(self.pk)])
    
    def __unicode__(self):
        return self.title
    
    class Meta:
        verbose_name = _("announcement")
        verbose_name_plural = _("announcements")
    
    def save(self, force_insert=False, force_update=False):
        """
        Saves an announcment to the database. This also sends out the
        announcement notification if django-notification is available. If
        DEBUG is turned on only send the announcment to staff members
        otherwise all users is fair game.
        """
        if notification:
            if settings.DEBUG:
                users = User.objects.filter(is_staff=True)
            else:
                users = User.objects.all()
            notification.send(users, "announcement", {"announcement": self}, issue_notice=False)
        super(Announcement, self).save(force_insert, force_update)

def current_announcements_for_request(request, **kwargs):
    """
    A helper function to get the current announcements based on some data from
    the HttpRequest.
    
    If request.user is authenticated then allow the member only announcments
    to be returned.
    
    Exclude announcments that have already been viewed by the user based on
    the ``excluded_announcments`` session variable.
    """
    defaults = {}
    if request.user.is_authenticated():
        defaults["for_members"] = True
    defaults["exclude"] = request.session.get("excluded_announcements", set())
    defaults.update(kwargs)
    return Announcement.objects.current(**defaults)
