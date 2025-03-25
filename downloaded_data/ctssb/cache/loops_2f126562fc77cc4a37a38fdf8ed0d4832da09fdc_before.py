#
#  Copyright (c) 2009 Helmut Merz helmutm@cy55.de
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#

"""
Specialized fields factories.

$Id$
"""

from zope.component import adapts

from cybertools.composer.schema.factory import SchemaFactory
from loops.common import adapted
from loops.interfaces import IResourceAdapter, IFile, INote
from cybertools.meta.interfaces import IOptions
from cybertools.typology.interfaces import IType


class ResourceSchemaFactory(SchemaFactory):

    adapts(IResourceAdapter)

    def __call__(self, interface, **kw):
        schema = super(ResourceSchemaFactory, self).__call__(interface, **kw)
        #if 'data' in schema.fields.keys():
        schema.fields.data.height = 10
        if self.context.contentType == 'text/html':
            schema.fields.data.fieldType = 'html'
        return schema


class FileSchemaFactory(SchemaFactory):

    adapts(IFile)

    def __call__(self, interface, **kw):
        schema = super(FileSchemaFactory, self).__call__(interface, **kw)
        options = IOptions(self.context.type)
        hide = options('hide_fields') or []
        show = options('show_fields') or []
        for f in ('contentType', 'externalAddress',):
            if f in schema.fields and f not in show:
                schema.fields.remove(f)
        for f in hide:
            if f in schema.fields:
                schema.fields.remove(f)
        return schema


class NoteSchemaFactory(SchemaFactory):

    adapts(INote)

    def __call__(self, interface, **kw):
        schema = super(NoteSchemaFactory, self).__call__(interface, **kw)
        schema.fields.remove('description')
        schema.fields.data.height = 5
        return schema

