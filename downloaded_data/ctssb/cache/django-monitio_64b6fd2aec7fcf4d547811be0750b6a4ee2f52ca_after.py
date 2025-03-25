import json
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render_to_response
from django.template import RequestContext
from django.core.exceptions import PermissionDenied
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django_sse.redisqueue import RedisQueueView
from sse import Sse
from monitio import testutil

from monitio.models import Monit
from monitio.storage import get_user
from monitio.conf import settings

SSE_ANONYMOUS = "__anonymous__"


def message_detail(request, message_id):
    user = get_user(request)
    if not user.is_authenticated():
        raise PermissionDenied

    message = get_object_or_404(Monit, user=user, pk=message_id)
    message.read = True
    message.save()

    return render_to_response('monitio/message/detail.html',
                              {'message': message},
                              context_instance=RequestContext(request))


def message_delete(request, message_id):
    user = get_user(request)
    if not user.is_authenticated():
        raise PermissionDenied

    message = get_object_or_404(Monit, user=user, pk=message_id)
    message.delete()

    if not request.is_ajax():
        return HttpResponseRedirect(request.META.get('HTTP_REFERER') or '/')
    else:
        return HttpResponse('')


def message_delete_all(request):
    user = get_user(request)
    if not user.is_authenticated():
        raise PermissionDenied

    Monit.objects.filter(user=user).delete()

    if not request.is_ajax():
        return HttpResponseRedirect(request.META.get('HTTP_REFERER') or '/')
    else:
        return HttpResponse('')


def message_mark_read(request, message_id):
    user = get_user(request)
    if not user.is_authenticated():
        raise PermissionDenied

    message = get_object_or_404(Monit, user=user, pk=message_id)
    message.read = True
    message.save()

    if not request.is_ajax():
        return HttpResponseRedirect(request.META.get('HTTP_REFERER') or '/')
    else:
        return HttpResponse('')


def message_mark_all_read(request):
    user = get_user(request)
    if not user.is_authenticated():
        raise PermissionDenied

    Monit.objects.filter(user=user).update(read=True)
    if not request.is_ajax():
        return HttpResponseRedirect(request.META.get('HTTP_REFERER') or '/')
    else:
        return HttpResponse('')


class DynamicChannelRedisQueueView(RedisQueueView):
    def get_redis_channel(self):
        return self.kwargs.get('channel') or self.redis_channel


    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        # This is basically the same method as in RedisQueueView.dispatch,
        # which should be a BaseSseView.dispatch. The only thing we modify
        # here is an extra header, called X-Accel-Buffering, which disables
        # buffering of this view by a webserver, for example nginx needs
        # that: http://wiki.nginx.org/X-accel#X-Accel-Buffering .

        # Also, we close db connection, as it won't be needed here.

        self.sse = Sse()

        self.request = request
        self.args = args
        self.kwargs = kwargs

        from django import db
        db.close_connection()

        response = HttpResponse(self._iterator(), content_type="text/event-stream")
        response['Cache-Control'] = 'no-cache'
        response['Software'] = 'django-sse'
        response['X-Accel-Buffering'] = 'no'
        return response


    def iterator(self):
        if settings.TESTING:
            #
            # When testing, with current Django (1.5.1) the LiveServerTestCase
            # servers only one thread for the server. So, if we listen for
            # Redis messages, we block the only socket of the test server. So,
            # to be able to test Javascript in web browsers (EventSource
            # support) we just fake incoming messages. Yes, this does not
            # test our Redis communication properly. On the other hand,
            # I rather leave Redis communication w/o testing, because
            # that's job of django-sse package - and focus on testing
            # browsers with EventSource support.
            #
            for message in testutil.MESSAGES:
                self.sse.add_message("message", message)
            testutil.MESSAGES = []
            return [1]

        return RedisQueueView.iterator(self)


class SameUserChannelRedisQueueView(DynamicChannelRedisQueueView):
    """Named Redis pub/sub, that allows logged-in users to connect
    with the same name, as their login.

    Anonymous users are also allowed by default. """

    redis_channel = SSE_ANONYMOUS
    allow_anonymous = True

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        self.kwargs = kwargs # needed for get_redis_channel
        pass_anon = request.user.is_anonymous() and self.get_redis_channel() == SSE_ANONYMOUS and self.allow_anonymous
        pass_logged_in = request.user.username == self.get_redis_channel()
        if pass_anon or pass_logged_in:
            return DynamicChannelRedisQueueView.dispatch(self, request, *args, **kwargs)
        return HttpResponseForbidden()
