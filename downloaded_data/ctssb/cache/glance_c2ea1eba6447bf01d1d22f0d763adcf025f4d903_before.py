# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2010-2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Defines interface for DB access
"""


from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import sessionmaker

from glance.common import config
from glance.common import exception
from glance.common import utils
from glance.registry.db import models

_ENGINE = None
_MAKER = None
BASE = models.BASE

# attributes common to all models
BASE_MODEL_ATTRS = set(['id', 'created_at', 'updated_at', 'deleted_at',
                        'deleted'])

IMAGE_ATTRS = BASE_MODEL_ATTRS | set(['name', 'status', 'size',
                                      'disk_format', 'container_format',
                                      'is_public', 'location'])

CONTAINER_FORMATS = ['ami', 'ari', 'aki', 'bare', 'ovf']
DISK_FORMATS = ['ami', 'ari', 'aki', 'vhd', 'vmdk', 'raw', 'qcow2', 'vdi']
STATUSES = ['active', 'saving', 'queued', 'killed']


def configure_db(options):
    """
    Establish the database, create an engine if needed, and
    register the models.

    :param options: Mapping of configuration options
    """
    global _ENGINE
    if not _ENGINE:
        verbose = config.get_option(
            options, 'verbose', type='bool', default=False)
        timeout = config.get_option(
            options, 'sql_idle_timeout', type='int', default=3600)
        _ENGINE = create_engine(options['sql_connection'],
                                echo=verbose,
                                echo_pool=verbose,
                                pool_recycle=timeout)
        register_models()


def get_session(autocommit=True, expire_on_commit=False):
    """Helper method to grab session"""
    global _MAKER, _ENGINE
    if not _MAKER:
        assert _ENGINE
        _MAKER = sessionmaker(bind=_ENGINE,
                              autocommit=autocommit,
                              expire_on_commit=expire_on_commit)
    return _MAKER()


def register_models():
    """Register Models and create properties"""
    global _ENGINE
    assert _ENGINE
    BASE.metadata.create_all(_ENGINE)


def unregister_models():
    """Unregister Models, useful clearing out data before testing"""
    global _ENGINE
    assert _ENGINE
    BASE.metadata.drop_all(engine)


def image_create(context, values):
    """Create an image from the values dictionary."""
    return _image_update(context, values, None)


def image_update(context, image_id, values):
    """Set the given properties on an image and update it.

    Raises NotFound if image does not exist.

    """
    return _image_update(context, values, image_id)


def image_destroy(context, image_id):
    """Destroy the image or raise if it does not exist."""
    session = get_session()
    with session.begin():
        image_ref = image_get(context, image_id, session=session)
        image_ref.delete(session=session)


def image_get(context, image_id, session=None):
    """Get an image or raise if it does not exist."""
    session = session or get_session()
    try:
        return session.query(models.Image).\
                       options(joinedload(models.Image.properties)).\
                       filter_by(deleted=_deleted(context)).\
                       filter_by(id=image_id).\
                       one()
    except exc.NoResultFound:
        new_exc = exception.NotFound("No model for id %s" % image_id)
        raise new_exc.__class__, new_exc, sys.exc_info()[2]


def image_get_all_public(context):
    """Get all public images."""
    session = get_session()
    return session.query(models.Image).\
                   options(joinedload(models.Image.properties)).\
                   filter_by(deleted=_deleted(context)).\
                   filter_by(is_public=True).\
                   all()


def _drop_protected_attrs(model_class, values):
    """Removed protected attributes from values dictionary using the models
    __protected_attributes__ field.
    """
    for attr in model_class.__protected_attributes__:
        if attr in values:
            del values[attr]


def validate_image(values):
    """
    Validates the incoming data and raises a Invalid exception
    if anything is out of order.

    :param values: Mapping of image metadata to check
    """

    status = values.get('status')
    disk_format = values.get('disk_format')
    container_format = values.get('container_format')

    status = values.get('status', None)
    if not status:
        msg = "Image status is required."
        raise exception.Invalid(msg)

    if status not in STATUSES:
        msg = "Invalid image status '%s' for image." % status
        raise exception.Invalid(msg)

    if disk_format and disk_format not in DISK_FORMATS:
        msg = "Invalid disk format '%s' for image." % disk_format
        raise exception.Invalid(msg)

    if container_format and container_format not in CONTAINER_FORMATS:
        msg = "Invalid container format '%s' for image." % container_format
        raise exception.Invalid(msg)

    if disk_format in ('aki', 'ari', 'ami') or\
            container_format in ('aki', 'ari', 'ami'):
        if container_format != disk_format:
            msg = ("Invalid mix of disk and container formats. "
                   "When setting a disk or container format to "
                   "one of 'ami', 'ari', or 'ami', the container "
                   "and disk formats must match.")
            raise exception.Invalid(msg)


def _image_update(context, values, image_id):
    """Used internally by image_create and image_update

    :param context: Request context
    :param values: A dict of attributes to set
    :param image_id: If None, create the image, otherwise, find and update it
    """

    session = get_session()
    with session.begin():

        # Remove the properties passed in the values mapping. We
        # handle properties separately from base image attributes,
        # and leaving properties in the values mapping will cause
        # a SQLAlchemy model error because SQLAlchemy expects the
        # properties attribute of an Image model to be a list and
        # not a dict.
        properties = values.pop('properties', {})

        if image_id:
            image_ref = image_get(context, image_id, session=session)
        else:
            if 'size' in values:
                values['size'] = int(values['size'])

            values['is_public'] = bool(values.get('is_public', False))
            image_ref = models.Image()

        _drop_protected_attrs(models.Image, values)
        image_ref.update(values)

        # Validate the attributes before we go any further. From my
        # investigation, the @validates decorator does not validate
        # on new records, only on existing records, which is, well,
        # idiotic.
        validate_image(image_ref.to_dict())

        image_ref.save(session=session)

        _set_properties_for_image(context, image_ref, properties, session)

    return image_get(context, image_ref.id)


def _set_properties_for_image(context, image_ref, properties, session=None):
    """
    Create or update a set of image_properties for a given image

    :param context: Request context
    :param image_ref: An Image object
    :param properties: A dict of properties to set
    :param session: A SQLAlchemy session to use (if present)
    """
    orig_properties = {}
    for prop_ref in image_ref.properties:
        orig_properties[prop_ref.key] = prop_ref

    for key, value in properties.iteritems():
        prop_values = {'image_id': image_ref.id,
                       'key': key,
                       'value': value}
        if key in orig_properties:
            prop_ref = orig_properties[key]
            image_property_update(context, prop_ref, prop_values,
                                  session=session)
        else:
            image_property_create(context, prop_values, session=session)


def image_property_create(context, values, session=None):
    """Create an ImageProperty object"""
    prop_ref = models.ImageProperty()
    return _image_property_update(context, prop_ref, values, session=session)


def image_property_update(context, prop_ref, values, session=None):
    """Update an ImageProperty object"""
    return _image_property_update(context, prop_ref, values, session=session)


def _image_property_update(context, prop_ref, values, session=None):
    """Used internally by image_property_create and image_property_update
    """
    _drop_protected_attrs(models.ImageProperty, values)
    prop_ref.update(values)
    prop_ref.save(session=session)
    return prop_ref


# pylint: disable-msg=C0111
def _deleted(context):
    """Calculates whether to include deleted objects based on context.

    Currently just looks for a flag called deleted in the context dict.
    """
    if not hasattr(context, 'get'):
        return False
    return context.get('deleted', False)
