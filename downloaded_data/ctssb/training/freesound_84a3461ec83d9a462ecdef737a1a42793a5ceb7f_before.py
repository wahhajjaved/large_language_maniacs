# -*- coding: utf-8 -*-
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models, connection
from django.utils.encoding import smart_unicode
from django.utils.translation import ugettext as _
from general.models import OrderedModel, SocialModel
from geotags.models import GeoTag
from tags.models import TaggedItem, Tag
from utils.sql import DelayedQueryExecuter
from utils.text import slugify
from utils.locations import locations_decorator
import os, logging, random, datetime
from utils.search.search import delete_sound_from_solr
from utils.filesystem import delete_object_files

search_logger = logging.getLogger('search')
web_logger = logging.getLogger('web')

class License(OrderedModel):
    """A creative commons license model"""
    name = models.CharField(max_length=512)
    abbreviation = models.CharField(max_length=8, db_index=True)
    summary = models.TextField()
    deed_url = models.URLField()
    legal_code_url = models.URLField()
    is_public = models.BooleanField(default=True)

    def __unicode__(self):
        return self.name

class SoundManager(models.Manager):
    def latest_additions(self, num_sounds, period='2 weeks'):
        return DelayedQueryExecuter("""
                select
                    username,
                    sound_id,
                    extra
                from (
                select
                    (select username from auth_user where auth_user.id = user_id) as username,
                    max(id) as sound_id,
                    max(created) as created,
                    count(*) - 1 as extra
                from
                    sounds_sound
                where
                    processing_state = 'OK' and
                    moderation_state = 'OK' and
                    created > now() - interval '%s'
                group by
                    user_id
                ) as X order by created desc limit %d;""" % (period, num_sounds))

    def random(self):

        sound_count = self.filter(moderation_state="OK", processing_state="OK").count()

        if sound_count:
            offset = random.randint(0, sound_count - 1)
            cursor = connection.cursor() #@UndefinedVariable
            cursor.execute("""select id from sounds_sound
                              where moderation_state='OK'
                              and processing_state='OK'
                              offset %d limit 1""" % offset)

            return cursor.fetchone()[0]
        else:
            return None


class PublicSoundManager(models.Manager):
    """ a class which only returns public sounds """
    def get_query_set(self):
        return super(PublicSoundManager, self).get_query_set().filter(moderation_state="OK", processing_state="OK")

class Sound(SocialModel):
    user = models.ForeignKey(User)
    created = models.DateTimeField(db_index=True, auto_now_add=True)

    # filenames
    original_filename = models.CharField(max_length=512) # name of the file the user uploaded
    original_path = models.CharField(max_length=512, null=True, blank=True, default=None) # name of the file on disk before processing
    base_filename_slug = models.CharField(max_length=512, null=True, blank=True, default=None) # base of the filename, this will be something like: id__username__filenameslug

    # user defined fields
    description = models.TextField()
    date_recorded = models.DateField(null=True, blank=True, default=None)

    license = models.ForeignKey(License)
    sources = models.ManyToManyField('self', symmetrical=False, related_name='remixes', blank=True)
    pack = models.ForeignKey('Pack', null=True, blank=True, default=None)
    geotag = models.ForeignKey(GeoTag, null=True, blank=True, default=None)

    # file properties
    SOUND_TYPE_CHOICES = (
        ('wav', 'Wave'),
        ('ogg', 'Ogg Vorbis'),
        ('aiff', 'AIFF'),
        ('mp3', 'Mp3'),
        ('flac', 'Flac')
    )
    type = models.CharField(db_index=True, max_length=4, choices=SOUND_TYPE_CHOICES)
    duration = models.FloatField(default=0)
    bitrate = models.IntegerField(default=0)
    bitdepth = models.IntegerField(null=True, blank=True, default=None)
    samplerate = models.FloatField(default=0)
    filesize = models.IntegerField(default=0)
    channels = models.IntegerField(default=0)
    md5 = models.CharField(max_length=32, unique=True, db_index=True)
    is_index_dirty = models.BooleanField(null=False, default=True)

    # moderation
    MODERATION_STATE_CHOICES = (
        ("PE",_('Pending')),
        ("OK",_('OK')),
        ("DE",_('Deferred')),
    )
    moderation_state = models.CharField(db_index=True, max_length=2, choices=MODERATION_STATE_CHOICES, default="PE")
    moderation_date = models.DateTimeField(null=True, blank=True, default=None)
    moderation_note = models.TextField(null=True, blank=True, default=None)
    has_bad_description = models.BooleanField(default=False)

    # processing
    PROCESSING_STATE_CHOICES = (
        ("QU",_('Queued')),
        ("PE",_('Pending')),
        ("PR",_('Processing')),
        ("OK",_('OK')),
        ("FA",_('Failed')),
    )
    processing_state = models.CharField(db_index=True, max_length=2, choices=PROCESSING_STATE_CHOICES, default="PE")
    processing_date = models.DateTimeField(null=True, blank=True, default=None)
    processing_log = models.TextField(null=True, blank=True, default=None)

    similarity_state = models.CharField(db_index=True, max_length=2, choices=PROCESSING_STATE_CHOICES, default="PE")
    analysis_state = models.CharField(db_index=True, max_length=2, choices=PROCESSING_STATE_CHOICES, default="PE")

    num_comments = models.PositiveIntegerField(default=0)
    num_downloads = models.PositiveIntegerField(default=0)

    avg_rating = models.FloatField(default=0)
    num_ratings = models.PositiveIntegerField(default=0)

    objects = SoundManager()
    public = PublicSoundManager()

    def __unicode__(self):
        return u"%s by %s" % (self.base_filename_slug, self.user)

    def friendly_filename(self):
        filename_slug = slugify(os.path.splitext(self.original_filename)[0])
        username_slug =  slugify(self.user.username)
        return "%d__%s__%s.%s" % (self.id, username_slug, filename_slug, self.type)

    @locations_decorator()
    def locations(self):
        id_folder = str(self.id/1000)
        return dict(
            path = os.path.join(settings.SOUNDS_PATH, id_folder, "%d_%d.%s" % (self.id, self.user.id, self.type)),
            sendfile_url = settings.SOUNDS_SENDFILE_URL + "%s/%d_%d.%s" % (id_folder, self.id, self.user.id, self.type),
            preview = dict(
                HQ = dict(
                    mp3 = dict(
                        path = os.path.join(settings.PREVIEWS_PATH, id_folder, "%d_%d-hq.mp3" % (self.id, self.user.id)),
                        url = settings.PREVIEWS_URL + "%s/%d_%d-hq.mp3" % (id_folder, self.id, self.user.id)
                    ),
                    ogg = dict(
                        path = os.path.join(settings.PREVIEWS_PATH, id_folder, "%d_%d-hq.ogg" % (self.id, self.user.id)),
                        url = settings.PREVIEWS_URL + "%s/%d_%d-hq.ogg" % (id_folder, self.id, self.user.id)
                    )
                ),
                LQ = dict(
                    mp3 = dict(
                        path = os.path.join(settings.PREVIEWS_PATH, id_folder, "%d_%d-lq.mp3" % (self.id, self.user.id)),
                        url = settings.PREVIEWS_URL + "%s/%d_%d-lq.mp3" % (id_folder, self.id, self.user.id)
                    ),
                    ogg = dict(
                        path = os.path.join(settings.PREVIEWS_PATH, id_folder, "%d_%d-lq.ogg" % (self.id, self.user.id)),
                        url = settings.PREVIEWS_URL + "%s/%d_%d-lq.ogg" % (id_folder, self.id, self.user.id)
                    )
                )
            ),
            display = dict(
                spectral = dict(
                    S = dict(
                        path = os.path.join(settings.DISPLAYS_PATH, id_folder, "%d_%d_spec_S.jpg" % (self.id, self.user.id)),
                        url = settings.DISPLAYS_URL + "%s/%d_%d_spec_S.jpg" % (id_folder, self.id, self.user.id)
                    ),
                    M = dict(
                        path = os.path.join(settings.DISPLAYS_PATH, id_folder, "%d_%d_spec_M.jpg" % (self.id, self.user.id)),
                        url = settings.DISPLAYS_URL + "%s/%d_%d_spec_M.jpg" % (id_folder, self.id, self.user.id)
                    ),
                    L = dict(
                        path = os.path.join(settings.DISPLAYS_PATH, id_folder, "%d_%d_spec_L.jpg" % (self.id, self.user.id)),
                        url = settings.DISPLAYS_URL + "%s/%d_%d_spec_L.jpg" % (id_folder, self.id, self.user.id)
                    )
                ),
                wave = dict(
                    S = dict(
                        path = os.path.join(settings.DISPLAYS_PATH, id_folder, "%d_%d_wave_S.png" % (self.id, self.user.id)),
                        url = settings.DISPLAYS_URL + "%s/%d_%d_wave_S.png" % (id_folder, self.id, self.user.id)
                    ),
                    M = dict(
                        path = os.path.join(settings.DISPLAYS_PATH, id_folder, "%d_%d_wave_M.png" % (self.id, self.user.id)),
                        url = settings.DISPLAYS_URL + "%s/%d_%d_wave_M.png" % (id_folder, self.id, self.user.id)
                    ),
                    L = dict(
                        path = os.path.join(settings.DISPLAYS_PATH, id_folder, "%d_%d_wave_L.png" % (self.id, self.user.id)),
                        url = settings.DISPLAYS_URL + "%s/%d_%d_wave_L.png" % (id_folder, self.id, self.user.id)
                    )
                )
            ),
            analysis = dict(
                statistics = dict(
                    path = os.path.join(settings.ANALYSIS_PATH, id_folder, "%d_%d_statistics.yaml" % (self.id, self.user.id)),
                    url = settings.ANALYSIS_URL + "%s/%d_%d_statistics.yaml" % (id_folder, self.id, self.user.id)
                ),
                frames = dict(
                    path = os.path.join(settings.ANALYSIS_PATH, id_folder, "%d_%d_frames.json" % (self.id, self.user.id)),
                    url = settings.ANALYSIS_URL + "%s/%d_%d_frames.json" % (id_folder, self.id, self.user.id)
                )
            )
        )

    def get_channels_display(self):
        if self.channels == 1:
            return u"Mono"
        elif self.channels == 2:
            return u"Stereo"
        else:
            return self.channels

    def type_warning(self):
        return self.type == "ogg" or self.type == "flac"

    def duration_warning(self):
        # warn from 5 minutes and more
        return self.duration > 60*5

    def filesize_warning(self):
        # warn for 50MB and up
        return self.filesize > 50 * 1024 * 1024

    def samplerate_warning(self):
        # warn anything special
        return self.samplerate not in [11025, 22050, 44100]

    def bitdepth_warning(self):
        return self.bitdepth not in [8,16]

    def bitrate_warning(self):
        return self.bitrate not in [32, 64, 96, 128, 160, 192, 224, 256, 320]

    def channels_warning(self):
        return self.channels not in [1,2]

    def duration_ms(self):
        return self.duration * 1000

    def rating_percent(self):
        return int(self.avg_rating*10)

    def process(self, force=False):
        if force or self.processing_state != "OK":
            sound.processing_date = datetime.now()
            sound.processing_state = "QU"
            gm_client.submit_job("process_sound", str(sound.id), wait_until_complete=False, background=True)
        if force or self.analysis_state != "OK":
            sound.analysis_state = "QU"
            gm_client.submit_job("analyze_sound", str(sound.id), wait_until_complete=False, background=True)
        sound.save()

    def mark_index_dirty(self):
        self.is_index_dirty = True
        self.save()


    @models.permalink
    def get_absolute_url(self):
        return ('sound', (self.user.username, smart_unicode(self.id),))

    def set_tags(self, tags):
        # remove tags that are not in the list
        for tagged_item in self.tags.all():
            if tagged_item.tag.name not in tags:
                tagged_item.delete()

        # add tags that are not there yet
        for tag in tags:
            if self.tags.filter(tag__name=tag).count() == 0:
                (tag_object, created) = Tag.objects.get_or_create(name=tag) #@UnusedVariable
                tagged_object = TaggedItem.objects.create(user=self.user, tag=tag_object, content_object=self)
                tagged_object.save()

    def delete(self):
        # remove from solr
        delete_sound_from_solr(self)
        # delete foreignkeys
        if self.geotag:
            self.geotag.delete()
        # delete files
        delete_object_files(self, web_logger)
        # super class delete
        super(Sound, self).delete()

    # N.B. This is used in the ticket template (ugly, but a quick fix)
    def is_sound(self):
        return True

    class Meta(SocialModel.Meta):
        ordering = ("-created", )

class Pack(SocialModel):
    user = models.ForeignKey(User)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True, default=None)
    is_dirty = models.BooleanField(db_index=True, default=True)

    created = models.DateTimeField(db_index=True, auto_now_add=True)
    num_downloads = models.PositiveIntegerField(default=0)

    def __unicode__(self):
        return u"%s by %s" % (self.name, self.user)

    @models.permalink
    def get_absolute_url(self):
        return ('pack', (smart_unicode(self.id),))

    class Meta(SocialModel.Meta):
        unique_together = ('user', 'name')
        ordering = ("-created",)

    def friendly_filename(self):
        name_slug = slugify(self.name)
        username_slug =  slugify(self.user.username)
        return "%d__%s__%s.zip" % (self.id, username_slug, name_slug)

    @locations_decorator()
    def locations(self):
        return dict(
                    sendfile_url = settings.PACKS_SENDFILE_URL + "%d.zip" % self.id,
                    path = os.path.join(settings.PACKS_PATH, "%d.zip" % self.id)
                   )

    def create_zip(self):
        import zipfile
        from django.template.loader import render_to_string

        logger = logging.getLogger("audio")

        logger.info("creating pack zip for pack %d" % self.id)
        logger.info("\twill save in %s" % self.locations("path"))
        zip_file = zipfile.ZipFile(self.locations("path"), "w", zipfile.ZIP_STORED, True)

        logger.info("\tadding attribution")
        licenses = License.objects.all()
        attribution = render_to_string("sounds/pack_attribution.txt", dict(pack=self, licenses=licenses))
        zip_file.writestr("_readme_and_license.txt", attribution.encode("UTF-8"))

        logger.info("\tadding sounds")
        for sound in self.sound_set.filter(processing_state="OK", moderation_state="OK"):
            path = sound.locations("path")
            logger.info("\t- %s" % os.path.normpath(path))
            zip_file.write(path, sound.friendly_filename().encode("utf-8"))

        zip_file.close()

        self.is_dirty = False
        self.save()

        logger.info("\tall done")

    def remove_sounds_from_pack(self):
        Sound.objects.filter(pack_id=self.id).update(pack=None)
        self.is_dirty = True
        self.save()

    def delete(self):
        """ This deletes all sounds in the pack as well. """
        # TODO: remove from solr?
        # delete files
        delete_object_files(self, web_logger)
        # super class delete
        super(Sound, self).delete()


class Flag(models.Model):
    sound = models.ForeignKey(Sound)
    reporting_user = models.ForeignKey(User, null=True, blank=True, default=None)
    email = models.EmailField()
    REASON_TYPE_CHOICES = (
        ("O",_('Offending sound')),
        ("I",_('Illegal sound')),
        ("T",_('Other problem')),
    )
    reason_type = models.CharField(max_length=1, choices=REASON_TYPE_CHOICES, default="I")
    reason = models.TextField()

    created = models.DateTimeField(db_index=True, auto_now_add=True)

    def __unicode__(self):
        return u"%s: %s" % (self.reason_type, self.reason[:100])

    class Meta:
        ordering = ("-created",)


class Download(models.Model):
    user = models.ForeignKey(User)
    sound = models.ForeignKey(Sound, null=True, blank=True, default=None)
    pack = models.ForeignKey(Pack, null=True, blank=True, default=None)
    created = models.DateTimeField(db_index=True, auto_now_add=True)

    class Meta:
        unique_together = ('user', 'sound', 'pack')
        ordering = ("-created",)
