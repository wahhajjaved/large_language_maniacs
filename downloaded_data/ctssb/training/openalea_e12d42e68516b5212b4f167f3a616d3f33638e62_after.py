# -*- python -*-
#
#       Store Class
#       Use it to install new packages
# 
#       OpenAlea.OALab: Multi-Paradigm GUI
#
#       Copyright 2013 INRIA - CIRAD - INRA
#
#       File author(s): Julien Coste <julien.coste@inria.fr>
#
#       File contributor(s):
#
#       Distributed under the Cecill-C License.
#       See accompanying file LICENSE.txt or copy at
#           http://www.cecill.info/licences/Licence_CeCILL-C_V1-en.html
#
#       OpenAlea WebSite : http://openalea.gforge.inria.fr
#
###############################################################################
__revision__ = "$Id: $"

from openalea.deploygui.alea_install_gui import MainWindow as MainWindowAleaInstall
from openalea.vpltk.qt import QtGui, QtCore
from openalea.plantgl.all import *
from PyQGLViewer import *
import sys


from openalea.deploygui.alea_install_gui import * 


class Store(MainWindowAleaInstall):
    """
    This class is used to search, install and upgrade packages.
    
    Warning!!! Will kill OALab!!!
    """
    
    def __init__(self,session):
        super(Store, self).__init__()
        self.show = False
        self.session = session
        self.actionShowHide = QtGui.QAction(QtGui.QIcon(":/images/resources/store.png"),"Show", self)
        QtCore.QObject.connect(self.actionShowHide, QtCore.SIGNAL('triggered(bool)'),self.showhide)
        self._actions = ["Help",[["Package Store",self.actionShowHide,0]]]

    def showhide(self):
        """
        Show / Hide this widget
        """
        if self.show:
            self.session.storeDockWidget.hide()
            self.show = False
        else:
            self.session.storeDockWidget.show()
            self.session.storeDockWidget.raise_()
            self.show = True 
            
            
    def actions(self):
        """
        :return: list of actions to set in the menu.
        """
        return self._actions

    def mainMenu(self):
        """
        :return: Name of menu tab to automatically set current when current widget
        begin current.
        """
        return "Package Store" 
