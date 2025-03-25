# -*- coding: utf-8 -*-
# This file is part of SWG (Static Website Generator).
#
# Copyright(c) 2010-2011 Simone Margaritelli
# evilsocket@gmail.com
# http://www.evilsocket.net
# http://www.backbox.org
#
# This file may be licensed under the terms of of the
# GNU General Public License Version 2 (the ``GPL'').
#
# Software distributed under the License is distributed
# on an ``AS IS'' basis, WITHOUT WARRANTY OF ANY KIND, either
# express or implied. See the GPL for the specific language
# governing rights and limitations.
#
# You should have received a copy of the GPL along with this
# program. If not, go to http://www.gnu.org/licenses/gpl.html
# or write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
import os
from entities.item        import Item
from core.config          import Config
from core.templatemanager import TemplateManager

class Page(Item):
  def __init__( self, title, template = None ):
    Item.__init__( self, Config.getInstance().basepath, title, Config.getInstance().page_ext )
    self.datetime   = None
    self.author     = None
    self.categories = []
    self.tags       = []
    self.abstract   = ""
    self.content    = ""
    self.template   = TemplateManager.getInstance().get( 'page.tpl' if template is None else template )
    self.custom     = {}

  def setCustom( self, name, value ):
    self.custom[name] = value
    return self

  def render( self ):
    return TemplateManager.render( template = self.template, page = self, **self.custom )
    
  def create( self ):
    Item.create(self)

    k_custom = self.custom.keys()[0]
    v_custom = self.custom.values()[0]

    # create only authors not already done
    if self.author != None and not os.path.exists( Config.getInstance().outputpath + "/" + self.author.url ):
      self.author.setCustom( k_custom, v_custom ).create()

    for category in self.categories:
      # create only categories not already done
      if not os.path.exists( Config.getInstance().outputpath + "/" + category.url ):
        category.setCustom( k_custom, v_custom ).create()

    for tag in self.tags:
      # create only tags not already done
      if not os.path.exists( Config.getInstance().outputpath + "/" + tag.url ):
        tag.create()
