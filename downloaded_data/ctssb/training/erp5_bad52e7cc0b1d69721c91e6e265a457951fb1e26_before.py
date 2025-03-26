# -*- coding: utf-8 -*-
##############################################################################
#
# Copyright (c) 2010 Nexedi SA and Contributors. All Rights Reserved.
#                    Nicolas Delaby <nicolas@nexedi.com>
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
##############################################################################
from AccessControl import ClassSecurityInfo, Unauthorized
from Products.ERP5Type import Permissions
from Products.ERP5Type.Utils import fill_args_from_request
from Products.CMFCore.utils import getToolByName, _setCacheHeaders,\
    _ViewEmulator
import warnings

_MARKER = []

class DownloadableMixin:
  security = ClassSecurityInfo()

  ### Content processing methods
  security.declareProtected(Permissions.View, 'index_html')
  @fill_args_from_request
  def index_html(self, REQUEST, RESPONSE, format=_MARKER, **kw):
    """
      We follow here the standard Zope API for files and images
      and extend it to support format conversion. The idea
      is that an image which ID is "something.jpg" should
      ne directly accessible through the URL
      /a/b/something.jpg. The same is true for a file and
      for any document type which primary purpose is to
      be used by a helper application rather than displayed
      as HTML in a web browser. Exceptions to this approach
      include Web Pages which are intended to be primarily rendered
      withing the layout of a Web Site or withing a standard ERP5 page.
      Please refer to the index_html of TextDocument.

      Should return appropriate format (calling convert
      if necessary) and set headers.

      format -- the format specied in the form of an extension
      string (ex. jpeg, html, text, txt, etc.)

      **kw -- can be various things - e.g. resolution

    """
    from Products.ERP5.Document.Document import VALID_TEXT_FORMAT_LIST,\
                                                        VALID_IMAGE_FORMAT_LIST
    web_cache_kw = kw.copy()
    if format is not _MARKER:
      web_cache_kw['format'] = format
    _setCacheHeaders(_ViewEmulator().__of__(self), web_cache_kw)

    if format is _MARKER and not kw:
      # conversion parameters is mandatory to download the converted content.
      # By default allways return view action.
      # for all WevDAV access return raw content.
      return self.view()
    if format is _MARKER:
      format = None
    self._checkConversionFormatPermission(format, **kw)
    mime, data = self.convert(format, **kw)
    if not format:
      # Guess the format from original mimetype
      mimetypes_registry = getToolByName(self.getPortalObject(),
                                                          'mimetypes_registry')
      mimetype_object_list = mimetypes_registry.lookup(mime)
      for mimetype_object in mimetype_object_list:
        if mimetype_object.extensions:
          output_format = mimetype_object.extensions[0]
          break
        elif mimetype_object.globs:
          output_format = mimetype_object.globs.strip('*.')
          break
    else:
      output_format = format

    RESPONSE.setHeader('Content-Length', len(data))
    if output_format in VALID_TEXT_FORMAT_LIST:
      RESPONSE.setHeader('Content-Type', '%s; charset=utf-8' % mime)
    else:
      RESPONSE.setHeader('Content-Type', mime)
    if output_format not in (VALID_TEXT_FORMAT_LIST + VALID_IMAGE_FORMAT_LIST):
      # need to return it as attachment
      filename = self.getStandardFileName(format=format)
      RESPONSE.setHeader('Content-Disposition',
                         'attachment; filename="%s"' % filename)
      RESPONSE.setHeader('Accept-Ranges', 'bytes')
    return str(data)

  security.declareProtected(Permissions.AccessContentsInformation,
                            'getStandardFilename')
  def getStandardFilename(self, format=None):
    """Returns the document coordinates as a standard file name. This
    method is the reverse of getPropertyDictFromFileName.
    """
    try:
      method = self._getTypeBasedMethod('getStandardFilename',
                             fallback_script_id='Document_getStandardFilename')
    except AttributeError:
      # backward compatibility
      method = self._getTypeBasedMethod('getStandardFileName',
                             fallback_script_id='Document_getStandardFileName')
    try:
      return method(format=format)
    except TypeError:
      # Old versions of this script did not support 'format' parameter
      return method()

  # backward compatibility
  security.declareProtected(Permissions.AccessContentsInformation,
                            'getStandardFileName')
  def getStandardFileName(self, format=None):
    """(deprecated) use getStandardFilename() instead."""
    warnings.warn('getStandardFileName() is deprecated. '
                  'use getStandardFilename() instead.')
    return self.getStandardFilename(format=format)

  def manage_FTPget(self):
    """Return body for ftp. and WebDAV
    """
    # pass format argument to force downloading raw content
    REQUEST = self.REQUEST
    return self.index_html(REQUEST, REQUEST.RESPONSE, format=None)
