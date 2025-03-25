## -*- coding: utf-8 -*-
## Copyright (C) 2008 Ingeniweb

## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.

## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.

## You should have received a copy of the GNU General Public License
## along with this program; see the file COPYING. If not, write to the
## Free Software Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

# $Id$
"""
Migration (not upgrades) related resources.
"""
__author__  = 'Gilles Lenfant <gilles.lenfant@ingeniweb.com>'
__docformat__ = 'restructuredtext'

import logging

import transaction
from OFS.Image import File
from Products.Archetypes.BaseUnit import BaseUnit

from iw.fss import config
from iw.fss.zcml import patchedTypesRegistry

logger = logging.getLogger(config.PROJECTNAME)
LOG = logger.info
LOG_WARNING = logger.warning
LOG_ERROR = logger.error

class Migrator(object):

    def __init__(self, portal, do_log=False, commit_every=0):
        """Construction params:
        @param portal: portal object to migrate
        @param do_log: log details of migration (bool)
        @param commit_every: commit subtransaction every n content items changed"""

        self.portal = portal
        self.do_log = do_log
        self.commit_every = commit_every
        self.changed_items = 0
        return

    def commit(self):
        """Should we commit"""
        self.changed_items += 1
        if ((self.commit_every > 0)
            and (self.changed_items % self.commit_every == 0)):
            transaction.savepoint(optimistic=True)
        return

    def log(self, message, *args, **kw):
        """Logging if option set"""

        if self.do_log:
            LOG(message, *args, **kw)

    def migrateToFSS(self):
        """Do migrations to FSS"""

        catalog = self.portal.portal_catalog
        self.log("Starting migration to FSS")
        for content_class, patched_fields in patchedTypesRegistry.items():
            meta_type = content_class.meta_type
            self.log("Migrating %s content types", meta_type)
            brains = catalog.searchResults(meta_type=meta_type)
            for brain in brains:
                item_changed = False
                try:
                    item = brain.getObject()
                except Exception, e:
                    LOG_WARNING("Catalog mismatch on %s", brain.getPath(), exc_info=True)
                    continue
                if item is None:
                    LOG_WARNING("Catalog mismatch on %s", brain.getPath())
                    continue
                for fieldname, former_storage in patched_fields.items():
                    field = item.getField(fieldname)
                    try:
                        value = former_storage.get(fieldname, item)
                    except AttributeError, e:
                        # Optional empty value
                        continue
                    filename = getattr(value, 'filename', None) or obj.getId()
                    if isinstance(value, File):
                        unwrapped_value = value.data
                    else:
                        unwrapped_value = str(value)
                    data = BaseUnit(
                        fieldname,
                        unwrapped_value,
                        instance=item,
                        filename=filename,
                        mimetype=value.getContentType(),
                        )
                    try:
                        field.set(item, data)
                        self.commit()
                    except IOError, e:
                        LOG_ERROR("Migrating %s failed on field %s",
                                  '/'.join(brain.getPath()), fieldname,
                                  exc_info=True)
                        continue
                    former_storage.unset(fieldname, item)

                    # Removing empty files
                    if field.get_size(item) == 0:
                        field.set(item, 'DELETE_FILE')
                    self.log("Field %s of %s successfully migrated",
                             fieldname, brain.getPath())
                # /for fieldname...
            # /for brain...
        # /for content_class
        return self.changed_items


    def migrateFromFSS(self):
        """Do migrations from FSS"""

        self.log("Starting migrations from FSS")
        return self.changed_items

