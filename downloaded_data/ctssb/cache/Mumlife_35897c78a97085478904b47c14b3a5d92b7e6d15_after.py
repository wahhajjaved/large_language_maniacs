# mumlife/models.py
import logging
import operator
import random
import re
from copy import deepcopy
from datetime import datetime, timedelta
from django.db import models
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.encoding import force_unicode
from django.utils.html import strip_tags
from django.utils.text import Truncator
from django.utils.timesince import timesince
from tagging.fields import TagField
from tagging.models import Tag, TaggedItem
from markitup.fields import MarkupField
from dateutil.rrule import rrule, WEEKLY
from dateutil.relativedelta import relativedelta
from mumlife import utils

logger = logging.getLogger('mumlife.models')


class Page(models.Model):
    title = models.CharField(max_length=64, unique=True)
    slug = models.CharField(max_length=64, unique=True)
    body = MarkupField()
    status = models.BooleanField("Publish Status", default=False)

    def __unicode__(self):
        return self.title
    
    @staticmethod
    def REGEX():
        """ Static pages regular expression used by the URL resolver """
        return r'^(?P<page>{})$'.format('|'.join([p['slug'] for p in Page.objects.filter(status=True).values('slug')]))


class Geocode(models.Model):
    code = models.CharField(max_length=125)
    latitude = models.FloatField()
    longitude = models.FloatField()

    def __unicode__(self):
        return '{} {}'.format(self.longitude, self.latitude)


class MemberManager(models.Manager):
    def with_distance_from(self, viewer=None, query_tags=None):
        """Return all Members, ordered by their distance from the viewer.

        Viewer has to exists, or this query doesn't make sense.
        Exclude the logged-in user, Administrators, Organisers and banned members.
        """
        if viewer is None:
            return self.all()
        if query_tags is not None:
            members = TaggedItem.objects.get_by_model(Member, query_tags)
        else:
            members = self.all()

        point = 'POINT({})'.format(viewer.geocode)
        members = members.exclude(user=viewer.user) \
                         .exclude(user__groups__name='Administrators') \
                         .exclude(user__is_active=False) \
                         .exclude(gender=Member.IS_ORGANISER) \
                         .extra(
                                select={'distance': """ST_Distance(
                                    ST_GeographyFromText(%s),
                                    ST_GeographyFromText(CONCAT('POINT(', geocode, ')'))
                                )"""},
                                select_params=(point,),
                         ) \
                         .order_by('distance')
        return members


class Member(models.Model):
    PENDING = 0
    VERIFIED = 1
    BANNED = 2
    STATUS_CHOICES = (
        (PENDING, 'Pending'),
        (VERIFIED, 'Verified'),
        (BANNED, 'Banned'),
    )
    
    IS_MUM = 0
    IS_DAD = 1
    IS_BUMP = 2
    IS_ORGANISER = 3
    GENDER_CHOICES = (
        (IS_MUM, 'Mum'),
        (IS_DAD, 'Dad'),
        (IS_BUMP, 'Bump'),
        (IS_ORGANISER, 'Organiser'),
    )

    user = models.OneToOneField(User, related_name='profile')
    fullname = models.CharField("Full Name", max_length=64)
    slug = models.CharField("Profile Slug", max_length=255, default='', blank=True)
    postcode = models.CharField("Postcode", max_length=8, help_text='Please include the gap (space) between the outward and inward codes')
    gender = models.IntegerField("Gender", choices=GENDER_CHOICES, null=True, blank=True)
    dob = models.DateField("Date of Birth", null=True, blank=True)
    status = models.IntegerField("Verification Status", choices=STATUS_CHOICES, default=PENDING)

    # Optional
    picture = models.ImageField("Picture", upload_to='./member/%Y/%m/%d', null=True, blank=True, \
                                help_text="PNG, JPEG, or GIF; max size 2 MB. Image must be 150 x 150 pixels or larger.")
    about = models.TextField("About", null=True, blank=True)
    spouse = models.ForeignKey('self', related_name='partner', null=True, blank=True, help_text="Spouse or Partner")
    interests = TagField("Interests")
    geocode = models.CharField("Geocode", max_length=255, null=True, blank=True)
    units = models.IntegerField("Units", choices=(
        (0, 'Kilometers'),
        (1, 'Miles'),
    ), null=True, blank=True, default=1, help_text="Distance measurement units")
    max_range = models.IntegerField("Maximum Search Distance", default=5, help_text="Maximum range used by the Event Calendar slider")
    friendships = models.ManyToManyField('self', null=True, blank=True, through='Friendships', \
                                         symmetrical=False, related_name='friends_with+')

    objects = MemberManager()

    def save(self, *args, **kwargs):
        if self.id is not None:
            # The profile is created after user creation,
            # therefore no data will be associated with it then.
            # It only makes sense to process data when it is updated,
            # i.e. when the data is there
            self.set_slug()
            if self.postcode:
                # Make sure the gap is there
                postcode = utils.Extractor(self.postcode.upper()).extract_postcode()
                if postcode:
                    self.postcode = postcode
                self.set_geocode()
            else:
                self.postcode = 'N/A'
        super(Member, self).save(*args, **kwargs)

    def __unicode__(self):
        return self.name

    def __repr__(self):
        return u'<Member: [{}] {}>'.format(self.id, self.name)

    def is_admin(self):
        return 'Administrators' in [g['name'] for g in self.user.groups.values('name')]

    def get_distance_from(self, entity=None):
        if not entity or not entity.geocode or entity.geocode == '0.0 0.0' or \
            not self.geocode or self.geocode == '0.0 0.0':
                return {
                    'units': 'N/A',
                    'distance-display': 'N/A',
                    'distance': 99999999999
                }
        else:
            units = entity.units if hasattr(entity, 'units') else self.units
            units_display = 'Km' if units == 0 else self.get_units_display()
            distance = self.distance / 1000
            distance = distance if units == 0 else distance * 0.6214
            if round(distance, 1) < 0.5:
                units_display = 'kilometer' if units == 0 else units_display[:-1]
                distance_display = 'less than half a {}'.format(units_display.lower())
            elif round(distance, 1) <= 1.1:
                units_display = units_display if units == 0 else units_display[:-1]
                distance_display = '{} {}'.format(round(distance, 1), units_display.lower())
            else:
                distance_display = '{} {}'.format(round(distance, 1), units_display.lower())
        return {
            'units': units_display,
            'distance_display': distance_display,
            'distance': distance
        }

    def format(self, viewer=None):
        member = {}
        member['id'] = self.id
        member['is_admin'] = self.is_admin()
        member['slug'] = self.slug
        member['url'] = '/profile/{}'.format(self.slug)
        member['name'] = self.get_name(viewer)
        member['age'] = self.age
        member['gender'] = self.get_gender_display()
        member['about'] = strip_tags(force_unicode(self.about)) if self.about else ''
        if viewer:
            member['friend_status'] = viewer.check_if_friend(self)
        else:
            member['friend_status'] = False
        member['area'] = self.area
        member['picture'] = self.picture.url if self.picture else ''
        # distance
        if viewer is not None:
            try:
                # The distance might have already been set by an earlier query
                # e.g. list of members includes the distance already
                # If not, this will raise an AttributeError
                _distance = self.distance
            except AttributeError:
                point_from = 'POINT({})'.format(viewer.geocode)
                point_to = 'POINT({})'.format(self.geocode)
                distance_query = Member.objects.raw("""SELECT id, ST_Distance(
                                            ST_GeographyFromText(%s),
                                            ST_GeographyFromText(%s)
                                          ) As distance
                                          FROM mumlife_member
                                          WHERE id=%s""",
                                       [point_from, point_to, self.id])
                self.distance = distance_query[0].distance
            distance = self.get_distance_from(viewer)
            member.update(distance)
        member['interests'] = self.interests.strip()
        member['kids'] = self.get_kids(viewer=viewer)
        return member

    @property
    def name(self):
        return self.get_name()

    def get_name(self, viewer=None):
        if self == viewer:
            return self.fullname
        else:
            try:
                # show lastame initials
                name = self.fullname.split()
                return '{} {}'.format(name[0], 
                                      ''.join(['{}.'.format(n[0].upper()) for n in name[1:]]))
            except IndexError:
                return 'N/A'
    
    @property
    def age(self):
        return utils.get_age(self.dob)

    @property
    def area(self):
        # For UK only, return inward code
        if self.postcode:
            try:
                area = self.postcode.split()[0]
            except IndexError:
                pass
            else:
                return area
        return 'N/A'

    @property
    def kids(self):
        return self.kid_set.exclude(visibility=Kid.HIDDEN)

    def get_kids(self, viewer=None):
        kids = []
        for kid in self.kids:
            # hide HIDDEN kids from other members
            if viewer != self and kid.visibility == Kid.HIDDEN:
                continue
            kids.append(kid.format(viewer=viewer))
        return kids

    def add_friend(self, member, status):
        friend, created = Friendships.objects.get_or_create(
            from_member=self,
            to_member=member,
            status=status)
        return friend

    def remove_friend(self, member):
        Friendships.objects.filter(
            from_member=self, 
            to_member=member).delete()

    def get_friends(self, status):
        return self.friendships.filter(to_friend__status=status, to_friend__from_member=self)

    def get_friend_requests(self):
        # Requests exclude any request from BLOCKED members
        blocked = [m['id'] for m in self.get_friends(status=Friendships.BLOCKED).values('id')]
        return Friendships.objects.filter(status=Friendships.PENDING, to_member=self)\
                                  .exclude(from_member__id__in=blocked)

    def check_if_friend(self, member):
        try:
            # first, we check if this member has already been requested as a friend
            member_relation = Friendships.objects.get(from_member=self, to_member=member)
            return member_relation.get_status_display()
        except Friendships.DoesNotExist:
            # if no relation exist, it hasn't been requested as a friend.
            # he might have requested self as a friend though, so we lookup any reverse
            # relationship from the member to self
            member_relation = self.get_friend_requests().filter(from_member=member)
            if member_relation:
                return 'Requesting'
            return False

    def set_slug(self):
        if not self.slug:
            # Slug format: hyphenise(fullname)/random(1-999)/(1+count(fullname)/random(1-999)*(1+count(fullname))
            initials = ''.join(['{}.'.format(n[0]) for n in self.fullname.split()])
            hyphenized = re.sub(r'\s\s*', '-', initials.lower())
            count = Member.objects.filter(slug__contains=hyphenized).count()
            slug = '{}/{}/{}/{}'.format(hyphenized, random.randint(1, 999), count+1, (count+1) * random.randint(1, 999))
            self.slug = slug

    def set_geocode(self):
        if not self.geocode or self.geocode == '0.0 0.0':
            try:
                geocode = Geocode.objects.get(code=self.postcode)
            except Geocode.DoesNotExist:
                if self.postcode is None:
                    geocode = '0.0 0.0'
                else:
                    # If the geocode for this postcode has not yet been stored,
                    # fetch it
                    try:
                        point = utils.get_postcode_point(self.postcode)
                    except:
                        # The function raises an Exception when the API call fails;
                        # when this happens, do nothing
                        logger.error('The Geocode retrieval for the postcode "{}" has failed.'.format(self.postcode))
                        geocode = '0.0 0.0'
                    else:
                        geocode = Geocode.objects.create(code=self.postcode, latitude=point[0], longitude=point[1])
            self.geocode = str(geocode)

    def _filter_messages(self, search=None):
        query_tags = None
        if search:
            search = re.sub(r'\s\s*', ' ', search)
            search = re.sub(r'#|%23', '', search)
            tags = ['#{}'.format(t) for t in search.split() if not t.startswith('@')]
            if tags:
                query_tags = Tag.objects.filter(name__in=tags)
        if query_tags is None:
            messages = Message.objects.all()
        else:
            messages = TaggedItem.objects.get_by_model(Message, query_tags)
        # exclude replies
        messages = messages.exclude(is_reply=True)
        return messages
        
    def get_messages(self, search=None):
        """Member Messages include:
            - @local (default):
                - Administrator messages (i.e. with no tags)
                - LOCAL & GLOBAL messages within account area
                - FRIENDS messages within account area, from account friends
                (using @local is redundant, as it is the default);
            - @global:
                - GLOBAL messages outside account area;
            - @friends:
                - FRIENDS messages in all areas, from account friends
            - @private:
                - PRIVATE messages sent to account, regardless of area or friendship
        """
        messages = self._filter_messages(search=search)

        # extract flags @flags
        # only one flag is allowed. Exceptions will default to @local
        flags = utils.Extractor(search).extract_flags()
        if not flags or len(flags) > 1:
            flags = ['@local']
        try:
            flag = flags[0]
        except IndexError:
            flag = None

        # exclude events
        messages = messages.exclude(eventdate__isnull=False)

        # @friends results
        if flag == '@friends':
            # OWN FRIENDS messages
            _own = models.Q(member=self, visibility=Message.FRIENDS)
            # All messages from account friends
            members_friends = [f['id'] for f in self.get_friends(status=Friendships.APPROVED).values('id')]
            _friends = models.Q(member__id__in=members_friends,
                         visibility__in=[Message.LOCAL, Message.GLOBAL, Message.FRIENDS])
            messages = messages.filter(_own | _friends)

        # @private results
        elif flag == '@private':
            # OWN PRIVATE messages
            _own = models.Q(member=self, visibility=Message.PRIVATE)
            # PRIVATE messages sent to account, regardless of area
            _privates = models.Q(visibility=Message.PRIVATE, recipient=self)
            messages = messages.filter(_own | _privates)

        # @global results
        elif flag == '@global':
            # GLOBAL messages outside account area
            _globals = models.Q(visibility=Message.GLOBAL) & ~models.Q(area=self.area)
            messages = messages.filter(_globals)

        # @local results
        else:
            # Administrators messages
            # i.e.: admins messages with no tags
            #     + admins messages in member area
            _admins_notags = models.Q(visibility=Message.LOCAL, member__user__groups__name='Administrators', tags='')
            _admins_locals = models.Q(visibility=Message.LOCAL, member__user__groups__name='Administrators', tags__contains='#{}'.format(self.area.lower()))
            # LOCAL and GLOBAL messages within account area
            _locals = models.Q(visibility__in=[Message.LOCAL, Message.GLOBAL], area=self.area)
            # FRIENDS messages within account area, from account friends
            members_friends = [f['id'] for f in self.get_friends(status=Friendships.APPROVED).values('id')]
            _friends = models.Q(member__id__in=members_friends,
                         visibility=Message.FRIENDS,
                         area=self.area)
            messages = messages.filter(_admins_notags | _admins_locals | _locals | _friends)
            # Administrators messages to non-local areas should not be included
            _admins_nolocals = models.Q(member__user__groups__name='Administrators') \
                             & ~models.Q(tags='') \
                             & ~models.Q(tags__contains='#{}'.format(self.area.lower()))
            messages = messages.exclude(_admins_nolocals)

        # order messages in reverse chronological order
        messages = messages.order_by('-timestamp')
        return messages.distinct()

    def get_events(self, search=None, distance_range=None):
        """All events are returned, regardless of the location of the sender/author.
        Events are ordered by Event Date, rather than Post Date, in chronological order.
        Events are upcoming (i.e. no past events).

        Recurring events are generated on-the-fly.
        """
        now = timezone.now()
        messages = self._filter_messages(search=search)

        # exclude non-events
        messages = messages.exclude(eventdate__isnull=True)

        # exclude past non-recurring events
        messages = messages.exclude(occurrence=Message.OCCURS_ONCE,
                                    eventdate__lt=now)

        messages = messages.distinct()

        # add extra distance field
        # Django ORM does not support HAVING clauses,
        # so we have to use the distance function twice, once to filter the results,
        # and once to add the field to the row.
        point = 'POINT({})'.format(self.geocode)
        range_ = distance_range if distance_range is not None else 10**5
        messages = messages.extra(select={'distance': """ST_Distance(
                                      ST_GeographyFromText(%s),
                                      ST_GeographyFromText(CONCAT('POINT(', mumlife_message.geocode, ')'))
                                  )"""},
                                  select_params=(point,))
        messages = messages.extra(where=["""ST_Distance(
                                      ST_GeographyFromText(%s),
                                      ST_GeographyFromText(CONCAT('POINT(', mumlife_message.geocode, ')'))
                                  ) <= %s"""],
                                  params=[point, range_])
        events = list(messages)

        # we keep recurring events for now, as we will use them to create the occurrences
        # the occurences will then be filtered according to their dates
        for message in messages.all():
            if message.occurrence == Message.OCCURS_WEEKLY:
                # generate occurrence from today, on this week day,
                # at the the same time (hour, minutes, seconds)
                if message.occurs_until:
                    # when an end date is provided, we generate occurrences until that date only
                    # ---
                    # we have to convert date to datetime,
                    # then make the datetime aware.
                    # this is because Django stores date objects as naive dates
                    d = datetime.combine(message.occurs_until, datetime.min.time())
                    until = timezone.make_aware(d, timezone.get_default_timezone())
                else:
                    # otherwise we generate them for a month
                    until = now+relativedelta(months=+1)

                occurrences = list(rrule(WEEKLY,
                                        byweekday=message.eventdate.weekday(),
                                        byhour=message.eventdate.hour,
                                        byminute=message.eventdate.minute,
                                        bysecond=message.eventdate.second,
                                        dtstart=now,
                                        until=until))
                # create events
                for occurrence in occurrences:
                    # we only add the occurence if its date is not the same as the original event
                    # otherwise we get 2 identical events on the same day
                    if occurrence.date() == message.eventdate.date():
                        continue
                    m = deepcopy(message)
                    m.eventdate = occurrence
                    events.append(m)

        # filter out-of-date events+occurences
        events = [e for e in events if e.eventdate >= now]

        # order messages by increasing eventdate
        events = sorted(events, key=operator.attrgetter('eventdate'))
        return events

    def get_notifications(self):
        """Search for any new notifications for the member.
        The results is different to the one stored in Member.notifications.all(),
        which stores the notifications already notified (i.e. already read).
        """
        count = 0
        results = []

        # 1. Private Messages
        # ------------------------------------------------
        # member who have sent you private messages in the last 7 days
        privates = Message.objects.filter(visibility=Message.PRIVATE,
                                          recipient=self,
                                          timestamp__gte=timezone.now()-timedelta(7))\
                                  .order_by('-timestamp')
        if privates.count():
            count += privates.count()
            results.append({
                'type': 'messages',
                'timestamp': privates[0].timestamp,
                'age': privates[0].get_age(),
                'count': privates.count()
            })

        # 2. Events of the day you're in
        # ------------------------------------------------
        # @TODO 'in' events
        events = self.get_events()
        events = [r for r in events if r.eventdate is not None and r.eventdate.date() == timezone.now().date()]
        count += len(events)
        for event in events:
            evt = event.format(viewer=self)
            results.append({
                'type': 'events',
                'timestamp': evt['timestamp'],
                'event': evt
            })

        # 3. Friends requests
        # ------------------------------------------------
        friend_requests = self.get_friend_requests().count()
        if friend_requests:
            count += friend_requests
            results.append({
                'type': 'friends_requests',
                'count': friend_requests
            })

        # 4. Messages you were part of in the last 30 days
        # ------------------------------------------------
        # this includes:
        #   - replies to own meassage
        #   - replies to messages I replied to

        # other's replies to own messages
        my_own = [m['id'] for m in Message.objects.filter(member=self, is_reply=False).values('id')]
        replies_to_my_own = models.Q(is_reply=True, reply_to__in=my_own) & ~models.Q(member=self)

        # replies to messages I replied to
        #   - first, find parent messages to which I replied to
        my_replies = Message.objects.filter(member=self, is_reply=True)
        parents_replied_to = list(set([r.reply_to.id for r in my_replies]))
        #   - we get notified of replies to this list of parent messages
        replies_to_thread = models.Q(is_reply=True, reply_to__id__in=parents_replied_to) & ~models.Q(member=self)

        # get messages
        messages = Message.objects.filter(replies_to_my_own | replies_to_thread)\
                                  .filter(timestamp__gte=timezone.now()-timedelta(30))\
                                  .distinct()\
                                  .order_by('-timestamp')

        count += messages.count()

        # group messages by thread
        parents = [] # tracks parent messages used for grouping replies
        threads = [] # holds threads
        for message in messages:
            if message.reply_to.id not in parents:
                # we create a group which will hold all replies
                # to the same parent
                parents.append(message.reply_to.id)
                thread = {
                    'parent': message.reply_to.format(viewer=self),
                    'messages': [
                        message.format(viewer=self)
                    ]
                }
                threads.append(thread)
            else:
                # we add the message to group already created
                # the group index will be the same as the parent index in 'parents'
                index = parents.index(message.reply_to.id)
                if message.member.id not in [t['member']['id'] for t in threads[index]['messages']]:
                    # we are interested in notifying who replied
                    # if we have the same member replying twice, we ignore it
                    threads[index]['messages'].append(message.format(viewer=self))
        # add threads to results
        for thread in threads:
            results.append({
                'type': 'threads',
                'timestamp': thread['messages'][0]['timestamp'],
                'age': thread['messages'][0]['age'],
                'thread': thread
            })

        return {
            'count': count,
            'results': results
        }

def create_member(sender, instance, created, **kwargs):
    # Only create associated Member on creation,
    if created:
        member = Member.objects.create(user=instance)
        notifications = Notifications.objects.create(member=member)
post_save.connect(create_member, sender=User)


class Kid(models.Model):
    HIDDEN = 0
    BRACKETS = 1
    FULL = 2
    VISIBILITY_CHOICES = (
        (HIDDEN, 'Hidden'),
        (BRACKETS, 'Show age bracket'),
        (FULL, 'Show exact age'),
    )

    parents = models.ManyToManyField(Member)
    fullname = models.CharField("Full Name", max_length=64)
    gender = models.IntegerField("Gender", choices=(
        (0, 'Daughter'),
        (1, 'Son'),
    ), null=True)
    dob = models.DateField("Date of Birth", null=True)
    visibility = models.IntegerField("Kid Visibility", choices=VISIBILITY_CHOICES, default=BRACKETS)

    def __unicode__(self):
        return self.fullname

    @property
    def name(self):
        return self.__unicode__()

    @property
    def age(self):
        if self.visibility == Kid.BRACKETS:
            return utils.get_age_bracket(self.dob)
        elif self.visibility == Kid.FULL:
            return utils.get_age(self.dob)
        else:
            # This will only happen on admin/edit page
            # as HIDDEN kids are simply not shown
            return '{} ({})'.format(utils.get_age_bracket(self.dob), utils.get_age(self.dob))

    def format(self, viewer=None):
        kid = dict([(f.name, getattr(self, f.name)) for f in self._meta.fields])
        kid['name'] = self.fullname
        kid['gender'] = self.get_gender_display()
        del kid['id']
        del kid['dob']
        kid['age'] = self.age
        kid['visibility'] = self.get_visibility_display()
        return kid


class Friendships(models.Model):
    PENDING = 0
    APPROVED = 1
    BLOCKED = 2
    STATUSES = (
        (PENDING, 'Pending'),
        (APPROVED, 'Approved'),
        (BLOCKED, 'Blocked'),
    )

    from_member = models.ForeignKey(Member, related_name='from_friend')
    to_member = models.ForeignKey(Member, related_name='to_friend')
    status = models.IntegerField(choices=STATUSES)

    def __unicode__(self):
        return u'{} & {} [{}]'.format(self.from_member, self.to_member, self.get_status_display())


class Message(models.Model):
    # Visibility Settings
    PRIVATE = 0
    FRIENDS = 1
    LOCAL   = 2
    GLOBAL  = 3
    VISIBILITY_CHOICES = (
        (PRIVATE,   'Private'),
        (FRIENDS,   'Friends'),
        (LOCAL,     'Local'),
        (GLOBAL,    'Global'),
    )

    # Occurrence Settings
    OCCURS_ONCE     = 0
    OCCURS_WEEKLY   = 1
    OCCURRENCE_CHOICES = (
        (OCCURS_ONCE,   'Once'),
        (OCCURS_WEEKLY, 'Weekly'),
    )

    member = models.ForeignKey(Member)
    area = models.CharField(max_length=4)
    name = models.CharField(max_length=200, blank=True, null=True)
    body = models.TextField()
    picture = models.ImageField("Picture", upload_to='./posts/%Y/%m/%d', null=True, blank=True, \
                                help_text="PNG, JPEG, or GIF; max size 2 MB. Image must be 403 x 403 pixels or larger.")
    location = models.TextField(blank=True, null=True)
    geocode = models.CharField(max_length=255, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    eventdate = models.DateTimeField(null=True, blank=True)
    eventenddate = models.DateTimeField(null=True, blank=True)
    visibility = models.IntegerField(choices=VISIBILITY_CHOICES, default=LOCAL)
    occurrence = models.IntegerField(choices=OCCURRENCE_CHOICES, default=OCCURS_ONCE)
    occurs_until = models.DateField(null=True, blank=True)
    tags = TagField()
    recipient = models.ForeignKey(Member, null=True, blank=True, related_name='sender')
    is_reply = models.BooleanField(default=False)
    reply_to = models.ForeignKey('self', null=True, blank=True, related_name='author')

    def __unicode__(self):
        return u'{}'.format(self.body)

    def __repr__(self):
        type_ = 'Event' if self.is_event else 'Message'
        date_ = self.eventdate.date() if self.is_event else self.timestamp.date()
        return '<{}: {} [{}]; From: {} [{}] ({})>'.format(type_,
                                                          self.id,
                                                          date_,
                                                          self.member,
                                                          self.get_visibility_display(),
                                                          self.tags)

    def save(self, *args, **kwargs):
        self.set_geocode()
        super(Message, self).save(*args, **kwargs)

    @property
    def is_event(self):
        return True if self.eventdate is not None else False

    @property
    def replies(self):
        return Message.objects.filter(is_reply=True, reply_to=self).order_by('timestamp')

    def get_age(self):
        return timesince(self.timestamp, timezone.now())

    def get_replies(self, viewer=None):
        return [message.format(viewer=viewer) for message in self.replies]

    @property
    def postcode(self):
        if not self.location:
            return None
        postcode = utils.Extractor(self.location).extract_postcode()
        if not postcode:
            return None
        return postcode.upper()

    def format(self, viewer=None):
        message = dict([(f.name, getattr(self, f.name)) for f in self._meta.fields])
        if not self.name:
            # messages have empty names,
            # in which case we set it to the body text
            message['title'] = self.body
        else:
            message['title'] = self.name
        # escape body to prevent script attacks
        body = strip_tags(force_unicode(self.body))
        # parse body to display hashtag links
        message['body'] = utils.Extractor(body).parse(with_links=False)
        message['body_with_links'] = utils.Extractor(body).parse()
        message['synopsis'] = Truncator(strip_tags(force_unicode(self.body))).words(20, truncate=' ...')
        message['date'] = self.timestamp.strftime('%c')
        message['picture'] = self.picture.url if self.picture else ''
        # format event details
        if self.eventdate:
            # escape location to prevent script attacks
            message['location'] = strip_tags(force_unicode(self.location))
            message['eventdate'] = self.eventdate.strftime('%A, %b %d, %Y')
            message['eventtime'] = self.eventdate.strftime('%H:%M')
            message['eventyear'] = self.eventdate.strftime('%Y')
            message['eventmonth'] = self.eventdate.strftime('%b')
            message['eventday'] = self.eventdate.strftime('%d')
            if self.eventenddate:
                message['eventenddate'] = self.eventenddate.strftime('%A, %b %d, %Y')
                message['eventendtime'] = self.eventenddate.strftime('%H:%M')
            message['postcode'] = self.postcode
            # events are not necessarily in the same area as the author
            # we therefore override it by the event location postcode area
            if self.postcode:
                message['area'] = self.postcode.split()[0]
            # distance between the message and the viewer
            # the actual distance is in the message object,
            # so we add it to the viewer before calling its distance getter.
            try:
                # The distance might have already been set by an earlier query
                # e.g. list of members includes the distance already
                # If not, this will raise an AttributeError
                _distance = self.distance
            except AttributeError:
                point_from = 'POINT({})'.format(viewer.geocode)
                point_to = 'POINT({})'.format(self.geocode)
                distance_query = Member.objects.raw("""SELECT id, ST_Distance(
                                            ST_GeographyFromText(%s),
                                            ST_GeographyFromText(%s)
                                          ) As distance
                                          FROM mumlife_member
                                          WHERE id=%s""",
                                       [point_from, point_to, viewer.id])
                self.distance = distance_query[0].distance
            viewer.distance = self.distance
            distance = viewer.get_distance_from(self)
            message.update(distance)
        message['age'] = self.get_age()
        message['member'] = self.member.format(viewer=viewer)
        if message.has_key('recipient') and message['recipient']:
            message['recipient'] = message['recipient'].format(viewer=viewer)
        message['visibility'] = self.get_visibility_display().lower()
        if self.is_reply:
            message['reply_to'] = self.reply_to.id
        else:
            message['tags'] = self.get_tags()
            message['tags_item'] = self.get_tags(filter_='item')
            message['tags_inline'] = self.get_tags(filter_='inline')
            message['replies'] = self.get_replies(viewer=viewer)
        return message

    def get_tags(self, filter_=None):
        tags = utils.Extractor(self.tags).extract_tags()
        item_tags = tags.copy()
        inline_tags = utils.Extractor(self.body).extract_tags()
        for tag in inline_tags.keys():
            if item_tags.has_key(tag):
                del item_tags[tag]
        if filter_:
            if filter_ == 'item':
                return [{'key': tag[0], 'value': tag[1]} for \
                        tag in item_tags.items()]
            elif filter_ == 'inline':
                return [{'key': tag[0], 'value': tag[1]} for \
                        tag in inline_tags.items()]
        return [{'key': tag[0], 'value': tag[1]} for \
                tag in tags.items()]

    def set_geocode(self):
        try:
            postcode = self.postcode
            if not postcode:
                postcode = 'N/A'
            geocode = Geocode.objects.get(code=postcode)
        except Geocode.DoesNotExist:
            if postcode is None or postcode == 'N/A':
                geocode = '0.0 0.0'
            else:
                # If the geocode for this postcode has not yet been stored,
                # fetch it
                try:
                    point = utils.get_postcode_point(postcode)
                except:
                    # The function raises an Exception when the API call fails;
                    # when this happens, do nothing
                    logger.error('The Geocode retrieval for the postcode "{}" has failed.'.format(self.postcode))
                    geocode = '0.0 0.0'
                else:
                    geocode = Geocode.objects.create(code=postcode, latitude=point[0], longitude=point[1])
        self.geocode = str(geocode)


class Notifications(models.Model):
    member = models.OneToOneField(Member, related_name='notifications')
    total = models.IntegerField(default=0)
    messages = models.IntegerField(default=0)
    friends_requests = models.IntegerField(default=0)
    events = models.ManyToManyField(Message, related_name='notification_events', blank=True)
    threads = models.ManyToManyField(Message, related_name='notification_threads', blank=True)

    def __unicode__(self):
        return u"{} Message(s), {} Friend(s) Request(s), {} Event(s), {} Thread(s)"\
               .format(self.messages,
                       self.friends_requests,
                       self.events.count(),
                       self.threads.count())

    def count(self):
        return self.messages \
               + self.friends_requests \
               + self.events.count() \
               + self.threads.count()

    def clear(self):
        self.messages = 0
        self.friends_requests = 0
        self.events.clear()
        self.threads.clear()

    def reset(self, data):
        """
        Reset account notifications.
        'data' is the result of the Notification API.

        """
        self.total = data['total']
        self.events.clear()
        self.threads.clear()
        for result in data['results']:
            if result['type'] in ('events', 'threads'):
                # ManyToMany fields
                if result['type'] == 'events':
                    self.events.add(Message.objects.get(pk=result['event']['id']))
                else:
                    for message in result['thread']['messages']:
                        self.threads.add(Message.objects.get(pk=message['id']))
            else:
                setattr(self, result['type'], result['count'])
        self.save()

    class Meta:
        verbose_name_plural = "notifications"
