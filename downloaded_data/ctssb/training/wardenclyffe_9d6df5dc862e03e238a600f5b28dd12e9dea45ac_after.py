from json import loads, dumps
import os
import tempfile
import unicodedata

from django.conf import settings
from django_statsd.clients import statsd
from panopto.session import PanoptoSessionManager
from panopto.upload import PanoptoUpload, PanoptoUploadStatus

from wardenclyffe.main.models import Video, File, Image, Poster
from wardenclyffe.main.tasks import pull_from_s3, sftp_get


def prepare_description(descript):
    # Panopto accepts line feeds in the description field
    # but they must be properly encoded
    html_escape_table = {
        '&': '&amp;',
        '"': '&quot;',
        "'": '&apos;',
        '>': '&gt;',
        '<': '&lt;',
    }
    descript = u''.join(html_escape_table.get(c, c) for c in descript)
    descript = descript.replace('\n', '&#10;&#10;')
    return unicodedata.normalize('NFKD', descript)


def panopto_upload(operation, video, folder, input_file, extension):
    uploader = PanoptoUpload()
    uploader.server = settings.PANOPTO_SERVER
    uploader.folder = folder
    uploader.username = settings.PANOPTO_API_USER
    uploader.password = settings.PANOPTO_API_PASSWORD
    uploader.input_file = input_file
    uploader.title = video.title
    uploader.description = prepare_description(video.description)
    uploader.dest_filename = '{}.{}'.format(video.uuid, extension)

    if not uploader.create_session():
        operation.fail('Failed to create a Panopto upload session')
        return None
    operation.log(info='Panopto upload initialized')

    uploader.create_bucket()
    operation.log(info='Upload bucket created')

    uploader.upload_manifest()
    operation.log(info='Manifest uploaded')

    uploader.upload_media()
    operation.log(info='Media file uploaded')

    if not uploader.complete_session():
        operation.fail('Panopto complete session failed')
        return None

    operation.log(info='Panopto upload completed')
    return uploader


def pull_from_s3_and_upload_to_panopto(operation):
    statsd.incr('pull_from_s3_and_upload_to_panopto')

    params = loads(operation.params)
    video_id = params['video_id']
    video = Video.objects.get(id=video_id)

    if video.has_s3_transcoded():
        suffix = '.mp4'
        s3_key = video.s3_transcoded().cap
        bucket_name = settings.AWS_S3_OUTPUT_BUCKET
    else:
        suffix = video.extension()
        s3_key = video.s3_key()
        bucket_name = settings.AWS_S3_UPLOAD_BUCKET

    tmp = pull_from_s3(
        suffix, bucket_name, s3_key)
    operation.log(info='downloaded from S3')

    # the pull_from_s3 returns an open file pointer. Wait to close it
    # until the pypanopto library reads it
    uploader = panopto_upload(
        operation, video, params['folder'], tmp.name, suffix)
    tmp.close()

    if uploader:
        params['upload_id'] = uploader.get_upload_id()
        operation.params = dumps(params)
        operation.save()

    return ('complete', '')


def pull_from_cunix_and_upload_to_panopto(operation):
    statsd.incr('pull_from_cunix_and_upload_to_panopto')

    params = loads(operation.params)

    # pull the file down from cunix
    try:
        video_id = params['video_id']
        video = Video.objects.get(id=video_id)
        f = video.cuit_file()
    except Video.DoesNotExist:
        operation.fail('Unable to find video')
        return None
    except AttributeError:
        operation.fail('Unable to get cunix file')
        return None

    suffix = os.path.splitext(f.filename)[1]
    tmp = tempfile.NamedTemporaryFile(suffix=suffix)
    sftp_get(f.filename, tmp.name)
    tmp.seek(0)

    uploader = panopto_upload(
        operation, video, params['folder'], tmp.name, suffix[1:])
    tmp.close()

    if uploader:
        params['upload_id'] = uploader.get_upload_id()
        operation.params = dumps(params)
        operation.save()

    return ('complete', '')


def verify_upload_to_panopto(operation):
    statsd.incr('verify upload to panopto')

    params = loads(operation.params)
    video_id = params['video_id']
    video = Video.objects.get(id=video_id)

    upload_status = PanoptoUploadStatus()
    upload_status.server = settings.PANOPTO_SERVER
    upload_status.username = settings.PANOPTO_API_USER
    upload_status.password = settings.PANOPTO_API_PASSWORD
    upload_status.upload_id = params['upload_id']

    (state, panopto_id) = upload_status.check()
    if state != 4:  # Panopto "Complete" State
        raise Exception('Panopto is not yet finished.')

    url = settings.PANOPTO_LINK_URL.format(panopto_id)

    File.objects.create(
        video=video, location_type='panopto', url=url,
        filename=panopto_id, label='uploaded to panopto')

    params['panopto_id'] = panopto_id
    operation.params = dumps(params)
    operation.save()

    return ('complete', '')


def pull_thumb_from_panopto(operation):
    statsd.incr('verify upload to panopto')

    params = loads(operation.params)
    video_id = params['video_id']
    video = Video.objects.get(id=video_id)
    panopto_id = params['panopto_id']

    session_mgr = PanoptoSessionManager(
        settings.PANOPTO_SERVER, settings.PANOPTO_API_USER,
        instance_name=settings.PANOPTO_INSTANCE_NAME,
        password=settings.PANOPTO_API_PASSWORD)

    thumb_url = session_mgr.get_thumb_url(panopto_id)

    if not thumb_url or 'no_thumbnail' in thumb_url:
        raise Exception('Panopto thumbnail is not yet ready.')

    url = 'https://{}{}'.format(settings.PANOPTO_SERVER, thumb_url)
    img = Image.objects.create(video=operation.video, image=url)
    Poster.objects.create(video=video, image=img)
    return ('complete', '')
