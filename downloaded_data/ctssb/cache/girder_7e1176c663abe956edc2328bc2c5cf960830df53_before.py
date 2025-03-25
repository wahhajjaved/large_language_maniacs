#!/usr/bin/env python
# -*- coding: utf-8 -*-

###############################################################################
#  Copyright Kitware Inc.
#
#  Licensed under the Apache License, Version 2.0 ( the "License" );
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

import functools
import six
import sys
import traceback

from girder import events
from girder.plugins.jobs.constants import JobStatus
from girder.utility.model_importer import ModelImporter
from PIL import Image


def run(job):
    jobModel = ModelImporter.model('job', 'jobs')
    jobModel.updateJob(job, status=JobStatus.RUNNING)

    try:
        newFile = createThumbnail(**job['kwargs'])
        log = 'Created thumbnail file %s.' % newFile['_id']
        jobModel.updateJob(job, status=JobStatus.SUCCESS, log=log)
    except Exception:
        t, val, tb = sys.exc_info()
        log = '%s: %s\n%s' % (t.__name__, repr(val), traceback.extract_tb(tb))
        jobModel.updateJob(job, status=JobStatus.ERROR, log=log)
        raise


def createThumbnail(width, height, crop, fileId, attachToType, attachToId):
    """
    Creates the thumbnail. Validation and access control must be done prior
    to the invocation of this method.
    """
    fileModel = ModelImporter.model('file')
    file = fileModel.load(fileId, force=True)
    streamFn = functools.partial(fileModel.download, file, headers=False)

    event = events.trigger('thumbnails.create', info={
        'file': file,
        'width': width,
        'height': height,
        'crop': crop,
        'attachToType': attachToType,
        'attachToId': attachToId,
        'streamFn': streamFn
    })

    if len(event.responses):
        resp = event.responses[-1]
        newFile = resp['file']

        if event.defaultPrevented:
            if resp.get('attach', True):
                newFile = attachThumbnail(
                    file, newFile, attachToType, attachToId, width, height)
            return newFile
        else:
            file = newFile
            streamFn = functools.partial(
                fileModel.download, file, headers=False)

    if 'assetstoreId' not in file:
        # TODO(zachmullen) we could thumbnail link files if we really wanted.
        raise Exception('File %s has no assetstore.' % fileId)

    stream = streamFn()
    data = b''.join(stream())

    image = Image.open(six.BytesIO(data))

    if not width:
        width = int(height * image.size[0] / image.size[1])
    elif not height:
        height = int(width * image.size[1] / image.size[0])
    elif crop:
        x1 = y1 = 0
        x2, y2 = image.size
        wr = float(image.size[0]) / width
        hr = float(image.size[1]) / height

        if hr > wr:
            y1 = int(y2 / 2 - height * wr / 2)
            y2 = int(y2 / 2 + height * wr / 2)
        else:
            x1 = int(x2 / 2 - width * hr / 2)
            x2 = int(x2 / 2 + width * hr / 2)
        image = image.crop((x1, y1, x2, y2))

    image.thumbnail((width, height), Image.ANTIALIAS)

    uploadModel = ModelImporter.model('upload')

    out = six.BytesIO()
    image.save(out, 'JPEG', quality=85)
    size = out.tell()
    out.seek(0)

    thumbnail = uploadModel.uploadFromFile(
        out, size=size, name='_thumb.jpg', parentType=None, parent=None,
        user=None, mimeType='image/jpeg')

    return attachThumbnail(
        file, thumbnail, attachToType, attachToId, width, height)


def attachThumbnail(file, thumbnail, attachToType, attachToId, width, height):
    """
    Add the required information to the thumbnail file and the resource it
    is being attached to, and save the documents.

    :param file: The file from which the thumbnail was derived.
    :type file: dict
    :param thumbnail: The newly generated thumbnail file document.
    :type thumbnail: dict
    :param attachToType: The type to which the thumbnail is being attached.
    :type attachToType: str
    :param attachToId: The ID of the document to attach the thumbnail to.
    :type attachToId: str or ObjectId
    :param width: Thumbnail width.
    :type width: int
    :param height: Thumbnail height.
    :type height: int
    :returns: The updated thumbnail file document.
    """

    parentModel = ModelImporter.model(attachToType)
    parent = parentModel.load(attachToId, force=True)
    parent['_thumbnails'] = parent.get('_thumbnails', [])
    parent['_thumbnails'].append(thumbnail['_id'])
    parentModel.save(parent)

    thumbnail['attachedToType'] = attachToType
    thumbnail['attachedToId'] = parent['_id']
    thumbnail['isThumbnail'] = True
    thumbnail['derivedFrom'] = {
        'type': 'file',
        'id': file['_id'],
        'process': 'thumbnail',
        'width': width,
        'height': height
    }

    return ModelImporter.model('file').save(thumbnail)
