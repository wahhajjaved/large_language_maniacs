# -*- coding: utf-8 -*-
from ZODB.POSException import ConflictError
from genweb.rectorat.content.document import IDocument
from collective.dexteritytextindexer.converters import DefaultDexterityTextIndexFieldConverter
from collective.dexteritytextindexer.interfaces import IDexterityTextIndexFieldConverter
from z3c.form.interfaces import IWidget
from zope.component import adapts
from zope.interface import implements
from zope.schema.interfaces import IField
from Products.CMFCore.utils import getToolByName

from Products.CMFPlone.utils import safe_unicode
from unicodedata import normalize

from logging import getLogger
logger = getLogger(__name__)


class SearchableText(DefaultDexterityTextIndexFieldConverter):
    implements(IDexterityTextIndexFieldConverter)
    adapts(IDocument, IField, IWidget)

    def __init__(self, context, field, widget):
        """Initialize field converter"""
        self.context = context
        self.field = field
        self.widget = widget

    def convert(self):
        """ This code only is executed when the field implements dexteritytextindexer
             By default the system indexes to plain text but when you upload multifile
             it doesn't work.
             This portion of code solves just this problem.
             When the widget is multifile (only this two ids) it makes the content 
             of the files searchable :)
        """
        if self.widget.id == 'PublishedFiles' or self.widget.id == 'OriginalFiles':
            searchableText = []
            for obj in self.widget.value:
                fileData = self.convertFileByFile(obj)
                searchableText.append(fileData)
            return str(searchableText)
        else:
            html = self.widget.render().strip()
            transforms = getToolByName(self.context, 'portal_transforms')
            if isinstance(html, unicode):
                html = html.encode('utf-8')
            stream = transforms.convertTo('text/plain', html, mimetype='text/html')
            return stream.getData().strip()

    def unicode_save_string_concat(self, *args):
        """
        concats args with spaces between and returns utf-8 string, it does not
        matter if input was unicode or str
        """
        result = ''
        for value in args:
            if isinstance(value, unicode):
                value = value.encode('utf-8', 'replace')
            result = ' '.join((result, value))
        return result

    def convertFileByFile(self, obj):
        """Transforms file data to text for indexing safely.
        """
        storage = self.field.interface(self.context)
        data = self.field.get(storage)

        # if there is no data, do nothing
        if not obj:
            return ''
        # If size is 0 return only filename
        if obj.getSize() == 0:
            return str(obj.filename)

        # if data is already in text/plain, just return it and the filename
        if obj.contentType == 'text/plain':
            return str(obj.filename) + ' ' + obj.data

        # if there is no path to text/plain, do nothing
        transforms = getToolByName(self.context, 'portal_transforms')

        if not transforms._findPath(obj.contentType, 'text/plain'):
            return str(obj.filename)

        try:
            datastream = transforms.convertTo('text/plain',
                                              str(obj.data),
                                              mimetype=obj.contentType,
                                              filename=obj.filename)

            contentData = safe_unicode(datastream.getData().decode('utf-8'))
            contentData = normalize('NFKD', contentData).encode('ascii', errors='ignore')
            contentData = contentData.replace('\n', ' ').replace(u'\xa0', u' ').replace(u'\x0c',u'')

            return self.unicode_save_string_concat(obj.filename, contentData)

        except (ConflictError, KeyboardInterrupt):
            raise

        except Exception, e:
            logger.error('Error while trying to convert file contents '
                         'to "text/plain": %s' % str(e))
