import requests
import uuid
import wardenclyffe.main.tasks as maintasks

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.http import HttpResponseRedirect, HttpResponse
from django.utils.decorators import method_decorator
from django.views.generic import View
from wardenclyffe.main.models import Video, Collection
from django.contrib.auth.models import User
from django_statsd.clients import statsd
from django.conf import settings
from django.db import transaction

from .auth import MediathreadAuthenticator


def mediathread(request):
    # check their credentials
    authenticator = MediathreadAuthenticator(request.GET)
    if not authenticator.is_valid():
        statsd.incr("mediathread.auth_failure")
        return HttpResponse("invalid authentication token")

    username = authenticator.username
    user, created = User.objects.get_or_create(username=username)
    if created:
        statsd.incr("mediathread.user_created")

    request.session['username'] = username
    request.session['set_course'] = authenticator.set_course
    request.session['nonce'] = authenticator.nonce
    request.session['redirect_to'] = authenticator.redirect_to
    request.session['hmac'] = authenticator.hmc
    audio = request.GET.get('audio', False)
    folder = request.GET.get('folder', '')
    template = 'mediathread/mediathread.html'
    return render(
        request, template,
        dict(username=username, user=user, audio=audio, folder=folder))


@transaction.non_atomic_requests
def mediathread_post(request):
    if request.method != "POST":
        return HttpResponse("post only")

    # we see this now and then, probably due to browser plugins
    # that provide "privacy" by stripping session cookies off
    # requests. we really don't have any way of handling
    # the upload if we can't maintain a session, so bail.
    if 'username' not in request.session \
            or 'set_course' not in request.session:
        return HttpResponse("invalid session")

    return s3_upload(request)


def s3_upload(request):
    from wardenclyffe.main.views import key_from_s3url

    s3url = request.POST.get('s3_url')
    if s3url is None:
        return HttpResponse("Bad file upload. Please try again.")

    audio = request.POST.get('audio', False)
    folder_name = request.POST.get('folder', None)
    operations = []
    vuuid = uuid.uuid4()
    statsd.incr("mediathread.mediathread")
    key = key_from_s3url(s3url)
    # make db entry
    try:
        collection = Collection.objects.get(
            id=settings.MEDIATHREAD_COLLECTION_ID)
        v = Video.objects.create(collection=collection,
                                 title=request.POST.get('title', ''),
                                 creator=request.session['username'],
                                 uuid=vuuid)
        v.make_source_file(key)
        # we make a "mediathreadsubmit" file to store the submission
        # info and serve as a flag that it needs to be submitted
        # (when Elastic Transcoder comes back)
        user = User.objects.get(username=request.session['username'])
        v.make_mediathread_submit_file(
            key, user, request.session['set_course'],
            request.session['redirect_to'], audio=audio,
        )

        v.make_uploaded_source_file(key, audio=audio)
        operations = v.initial_operations(key, user, audio, folder_name)
    except (Collection.DoesNotExist, User.DoesNotExist, KeyError):
        statsd.incr("mediathread.mediathread.failure")
        raise
    else:
        # hand operations off to celery
        for o in operations:
            maintasks.process_operation.delay(o.id)
        return HttpResponseRedirect(request.session['redirect_to'])
    return HttpResponse("Bad file upload. Please try again.")


def mediathread_url(username):
    return (settings.MEDIATHREAD_BASE + "api/user/courses?secret=" +
            settings.MEDIATHREAD_SECRET + "&user=" +
            username)


class MediathreadCourseGetter(object):
    def run(self, username):
        try:
            url = mediathread_url(username)
            r = requests.get(url)
            courses = r.json()['courses']
            courses = [dict(id=k, title=v['title'])
                       for (k, v) in courses.items()]
            courses.sort(key=lambda x: x['title'].lower())
        except (ValueError, KeyError):
            courses = []
        return courses


def submit_video_to_mediathread(video, user, course):
    statsd.incr("mediathread.submit")
    video.make_mediathread_submit_file(
        video.filename(), user,
        course,
        redirect_to="",
        audio=video.is_audio_file())
    operations = video.handle_mediathread_submit()
    for o in operations:
        maintasks.process_operation.delay(o)
    video.clear_mediathread_submit()


class AuthenticatedNonAtomic(object):
    @method_decorator(login_required)
    @method_decorator(transaction.non_atomic_requests)
    def dispatch(self, *args, **kwargs):
        return super(AuthenticatedNonAtomic, self).dispatch(*args, **kwargs)


class VideoMediathreadSubmit(AuthenticatedNonAtomic, View):
    template_name = 'mediathread/mediathread_submit.html'
    course_getter = MediathreadCourseGetter

    def get(self, request, id):
        video = get_object_or_404(Video, id=id)
        courses = self.course_getter().run(request.user.username)
        return render(request, self.template_name,
                      dict(video=video, courses=courses,
                           mediathread_base=settings.MEDIATHREAD_BASE))

    def post(self, request, id):
        video = get_object_or_404(Video, id=id)
        submit_video_to_mediathread(video, request.user,
                                    request.POST.get('course', ''))
        return HttpResponseRedirect(video.get_absolute_url())


class CollectionMediathreadSubmit(AuthenticatedNonAtomic, View):
    template_name = 'mediathread/collection_mediathread_submit.html'
    course_getter = MediathreadCourseGetter

    def get(self, request, pk):
        collection = get_object_or_404(Collection, id=pk)
        courses = self.course_getter().run(request.user.username)
        return render(request, self.template_name,
                      dict(collection=collection, courses=courses,
                           mediathread_base=settings.MEDIATHREAD_BASE))

    def post(self, request, pk):
        collection = get_object_or_404(Collection, id=pk)
        for video in collection.video_set.all():
            submit_video_to_mediathread(video, request.user,
                                        request.POST.get('course', ''))
        return HttpResponseRedirect(collection.get_absolute_url())
