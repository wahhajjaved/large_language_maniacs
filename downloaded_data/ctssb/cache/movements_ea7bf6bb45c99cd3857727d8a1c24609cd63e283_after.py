import json
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse
from django.utils import translation as django_translation
from django.utils.translation import ugettext

from app.market.models import (
    TranslationBase)
from app.celerytasks import (
    takein_notification, approved_notification, approve_notification,
    revoke_notification, takeoff_notification
)


def get_or_create_translation(object_id, lang_code, model):
    q = model.objects.filter(status=model.global_state.GOOGLE, **model.get_params(object_id, lang_code))
    translation = q.first()
    if translation is not None:
        return translation
    with transaction.atomic():
        model.get_object_manager().select_for_update().get(pk=object_id)
        translation = q.first()
        if translation is not None:
            return translation
        return model.create_translation(object_id, lang_code)


def get_or_create_user_translation(object_id, lang_code, model):
    q = model.objects.filter(status__gte=model.global_state.PENDING, **model.get_params(object_id, lang_code))
    translation = q.first()
    if translation is not None:
        return translation
    google_translation = get_or_create_translation(object_id, lang_code, model)
    with transaction.atomic():
        model.get_object_manager().select_for_update().get(pk=object_id)
        translation = q.first()
        if translation:
            return translation
        google_translation.pk = None
        google_translation.status = model.global_state.PENDING
        google_translation.save()
        return google_translation


@login_required
def translate(request, object_id, model):
    lang_code = request.GET.get('lang_code', django_translation.get_language())
    translation = None
    result = {'response': 'error',
              'status': model.global_state.GOOGLE,
              'source_language': '',
              'human_aviable': False,
              'itemid': object_id}

    item = model.get_object(object_id)
    if item.language == lang_code:
        result.update(model.get_original(item))
        result.update({
            'response': 'success',
            'source_language': lang_code,
        })
        return HttpResponse(json.dumps(result), mimetype="application/json")

    if request.GET.get('human', 'true') != 'false':
        try:
            translation = model.objects.get(
                status__gt=model.global_state.PENDING,
                **model.get_params(object_id, lang_code))
            result.update({'status': translation.status, 'human_aviable': True})
        except model.DoesNotExist:
            pass
    elif model.objects.filter(status=model.global_state.DONE, **model.get_params(object_id, lang_code)).exists():
        result.update({'human_aviable': True})

    if result.get('status') < model.global_state.DONE:
        translation = get_or_create_translation(object_id, lang_code, model)

    if translation:
        result.update(translation.get_translated_data())
        result.update({'response': 'success'})
    return HttpResponse(json.dumps(result), mimetype="application/json")


@require_http_methods(['POST'])
@login_required
def take_in(request, object_id, model):
    lang_code = request.POST['lang_code']
    result = {'response': 'error', 'id': object_id}
    translation = get_or_create_user_translation(object_id, lang_code, model)
    if not translation.has_perm(request.user, lang_code):
        result.update({'error': ugettext('You do not currently have permissions to translate this item')})
        return HttpResponse(json.dumps(result), mimetype="application/json")
    if translation.c_status == translation.inner_state.NONE:
        translation.take_in(request.user)
        takein_notification.delay(translation, translation.is_done())
        result.update({'response': 'success'})
    elif translation.c_status == translation.inner_state.APPROVAL and request.user.userprofile.is_cm:
        result.update({'response': 'success'})
    elif translation.owner_candidate == request.user:
        result.update({'response': 'success'})
    else:
        force = request.POST.get('force', None)
        if request.user.userprofile.is_cm and force == '1':
            translation.take_in(request.user)
            result.update({'response': 'success'})
        else:
            result.update({
                'error': ugettext('Another user is currently translating this item'),
                'other_user_editing': True
            })
    if result['response'] == 'success':
        result.update(translation.get_init_data(request.user))
        if request.user.userprofile.is_cm:
            result.update(translation.cm_urls_dict())
    else:
        result.update({
            'status': 0,
            'active': False,
        })
    return HttpResponse(json.dumps(result), mimetype="application/json")


@require_http_methods(['POST'])
@login_required
def take_off(request, object_id, model):
    lang_code = request.POST['lang_code']
    result = {'response': 'error',
              'error': 'Translation is busy.'}
    try:
        translation = model.objects.get(
            c_status__in=[model.inner_state.TRANSLATION, model.inner_state.CORRECTION],
            owner_candidate=request.user,
            **model.get_params(object_id, lang_code))
    except model.DoesNotExist:
        result.update({'error': ugettext('No pending translation found to cancel.')})
    else:
        takeoff_notification.delay(translation)
        translation.clear_state()
        del result['error']
        result.update({'response': 'success', })
    return HttpResponse(json.dumps(result), mimetype="application/json")


@require_http_methods(['POST'])
@login_required
def done(request, object_id, model):
    lang_code = request.POST['lang_code']
    result = {'response': 'error', 'error': ''}
    try:
        translation = model.objects.get(
            c_status__in=[model.inner_state.TRANSLATION, model.inner_state.CORRECTION],
            owner_candidate=request.user,
            **model.get_params(object_id, lang_code))
    except model.DoesNotExist:
        result.update({'error': 'Translation record not found.'})
    else:
        if translation.has_perm(request.user, lang_code) and \
                        translation.c_status in [translation.inner_state.TRANSLATION,
                                                 translation.inner_state.CORRECTION]:
            translation.set_done(request.POST)
            approve_notification.delay(translation)
            result.update({'response': 'success'})

        if request.user.userprofile.is_cm:
            result.update(translation.cm_urls_dict())
    return HttpResponse(json.dumps(result), mimetype="application/json")


def _approve_correct_revoke(request, object_id, lang_code, model, params):
    params.update(model.get_params(object_id, lang_code))
    translation = None
    result = {'response': 'error'}
    if not request.user.userprofile.is_cm:
        result.update({'error': 'Has no permission. Only CMs are allowed.'})
    else:
        try:
            translation = model.objects.get(**params)
        except model.DoesNotExist:
            result.update({'error': 'Translation record not found.'})
    return result, translation


@require_http_methods(['POST'])
@login_required
def approve(request, object_id, model):
    lang_code = request.POST['lang_code']
    params = {'status__gte': TranslationBase.global_state.PENDING,
              'c_status': TranslationBase.inner_state.APPROVAL}
    result, translation = _approve_correct_revoke(request, object_id, lang_code, model, params)
    if translation:
        translation.approve(request.POST)
        approved_notification.delay(translation)
        translation.clear_state()
        result.update({'response': 'success'})
    return HttpResponse(json.dumps(result), mimetype="application/json")


@require_http_methods(['POST'])
@login_required
def corrections(request, object_id, model):
    lang_code = request.POST['lang_code']
    params = {'status__gte': TranslationBase.global_state.PENDING,
              'c_status': TranslationBase.inner_state.APPROVAL}
    result, translation = _approve_correct_revoke(request, object_id, lang_code, model, params)
    if translation:
        translation.c_status = translation.inner_state.CORRECTION
        translation.timer = datetime.utcnow()
        translation.save()
        takein_notification.delay(translation, True)
        result.update({'response': 'success'})

    return HttpResponse(json.dumps(result), mimetype="application/json")


@require_http_methods(['POST'])
@login_required
def revoke(request, object_id, model):
    lang_code = request.POST['lang_code']
    params = {'status__gte': TranslationBase.global_state.PENDING,
              'c_status__gt': TranslationBase.inner_state.NONE}
    result, translation = _approve_correct_revoke(request, object_id, lang_code, model, params)
    if translation:
        revoke_notification.delay(translation)
        translation.clear_state()
        result.update({'response': 'success'})
    return HttpResponse(json.dumps(result), mimetype="application/json")
