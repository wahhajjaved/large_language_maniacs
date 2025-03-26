#!/usr/bin/env python
#-*- encoding: utf-8 -*-

import os
import codecs

from PyQt4 import QtCore, QtGui

from prymatex import resources
from prymatex.core.plugin.dock import PMXBaseDock
from prymatex.utils.i18n import ugettext as _
from prymatex.gui.project.models import PMXProjectTreeModel
from prymatex.gui.utils import createQMenu
from prymatex.ui.dockers.projects import Ui_ProjectsDock
from prymatex.gui.dialogs.newfromtemplate import PMXNewFromTemplateDialog
from prymatex.gui.dockers.fstasks import PMXFileSystemTasks
from prymatex.gui.project.base import PMXProject

class PMXProjectDock(QtGui.QDockWidget, Ui_ProjectsDock, PMXFileSystemTasks, PMXBaseDock):
    PREFERED_AREA = QtCore.Qt.LeftDockWidgetArea
    MENU_ICON = resources.getIcon("project")
    MENU_KEY_SEQUENCE = QtGui.QKeySequence("F8")

    def __init__(self, parent):
        QtGui.QDockWidget.__init__(self, parent)
        PMXBaseDock.__init__(self)
        self.setupUi(self)
        self.projectTreeProxyModel = self.application.projectManager.projectTreeProxyModel
        self.treeViewProjects.setModel(self.projectTreeProxyModel)

        self.setupTreeViewProjects()

    def setMainWindow(self, mainWindow):
        PMXBaseDock.setMainWindow(self, mainWindow)
        mainWindow.projects = self
    
    def setupTreeViewProjects(self):
        #Setup Context Menu
        projectMenuSettings = { 
            "title": "Project",
            "items": [
                {   "title": "New",
                    "items": [
                        self.actionNewProject, self.actionNewFolder, self.actionNewFile, "-", self.actionNewFromTemplate
                    ]
                },
                "-",
                self.actionOpen,
                self.actionOpenSystemEditor,
                "-",
                self.actionDelete,
                "-",
                self.actionRefresh,
                self.actionCloseProject,
                self.actionOpenProject,
                "-",
                self.actionProperties
            ]
        }
        self.projectsMenu, self.prejectMenuActions = createQMenu(projectMenuSettings, self)

        fileMenuSettings = { 
            "title": "File",
            "items": [
                {   "title": "New",
                    "items": [
                        self.actionNewProject, self.actionNewFolder, self.actionNewFile, "-", self.actionNewFromTemplate
                    ]
                },
                "-",
                self.actionOpen,
                {   "title": "Open With",
                    "items": [
                        self.actionOpenDefaultEditor, self.actionOpenSystemEditor 
                    ]
                },
                "-",
                self.actionDelete,
                "-",
                self.actionRefresh,
                "-",
                self.actionProperties
            ]
        }
        self.fileMenu, self.fileMenuActions = createQMenu(fileMenuSettings, self)
        
        directoryMenuSettings = { 
            "title": "File",
            "items": [
                {   "title": "New",
                    "items": [
                        self.actionNewProject, self.actionNewFolder, self.actionNewFile, "-", self.actionNewFromTemplate
                    ]
                },
                "-",
                self.actionOpen,
                self.actionOpenSystemEditor,
                "-",
                self.actionDelete,
                "-",
                self.actionRefresh,
                "-",
                self.actionProperties
            ]
        }
        self.directoryMenu, self.directoryMenuActions = createQMenu(directoryMenuSettings, self)
        
        #Setup Context Menu
        optionsMenu = { 
            "title": "Project Options",
            "items": [
                {   "title": "Order",
                    "items": [
                        (self.actionOrderByName, self.actionOrderBySize, self.actionOrderByDate, self.actionOrderByType),
                        "-", self.actionOrderDescending, self.actionOrderFoldersFirst
                    ]
                }
            ]
        }

        self.actionOrderFoldersFirst.setChecked(True)
        self.actionOrderByName.trigger()
        
        self.projectOptionsMenu, _ = createQMenu(optionsMenu, self)
        self.pushButtonOptions.setMenu(self.projectOptionsMenu)
        
        #=======================================================================
        # Drag and Drop (see the proxy model)
        #=======================================================================
        self.treeViewProjects.setDragEnabled(True)
        self.treeViewProjects.setAcceptDrops(True)
        self.treeViewProjects.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.treeViewProjects.setDropIndicatorShown(True)
        
        #Connect context menu
        self.treeViewProjects.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.treeViewProjects.customContextMenuRequested.connect(self.showProjectTreeViewContextMenu)
        self.treeViewProjects.setAlternatingRowColors(True)
        self.treeViewProjects.setAnimated(True)

    #================================================
    # Tree View Project
    #================================================
    def showProjectTreeViewContextMenu(self, point):
        index = self.treeViewProjects.indexAt(point)
        if not index.isValid():
            index = self.treeViewProjects.currentIndex()
        if index.isValid():
            node = self.projectTreeProxyModel.node(index)
            if isinstance(node, PMXProject):
                self.projectsMenu.popup(self.treeViewProjects.mapToGlobal(point))
            elif node.isfile:
                self.fileMenu.popup(self.treeViewProjects.mapToGlobal(point))
            elif node.isdir:
                self.directoryMenu.popup(self.treeViewProjects.mapToGlobal(point))
                
    def on_treeViewProjects_doubleClicked(self, index):
        path = self.projectTreeProxyModel.filePath(index)
        if os.path.isfile(path):
            self.application.openFile(path)
    
    def currentPath(self):
        return self.projectTreeProxyModel.filePath(self.treeViewProjects.currentIndex())
    
    def currentNode(self):
        return self.projectTreeProxyModel.node(self.treeViewProjects.currentIndex())
    #================================================
    # Actions Create, Delete, Rename objects
    #================================================      
    @QtCore.pyqtSlot()
    def on_actionNewFile_triggered(self):
        basePath = self.currentPath()
        self.createFile(basePath)
    
    @QtCore.pyqtSlot()
    def on_actionNewFromTemplate_triggered(self):
        basePath = self.currentPath()
        self.createFileFromTemplate(basePath)
    
    @QtCore.pyqtSlot()
    def on_actionNewFolder_triggered(self):
        basePath = self.currentPath()
        self.createDirectory(basePath)

    @QtCore.pyqtSlot()
    def on_actionDelete_triggered(self):
        treeNode = self.currentNode()
        if not treeNode.isproject:
            self.deletePath(treeNode.path)
        else:
            self.logger.debug("Delete Project")

    @QtCore.pyqtSlot()
    def on_actionRename_triggered(self):
        basePath = self.currentPath()
        self.renamePath(basePath)

    @QtCore.pyqtSlot()
    def on_actionNewProject_triggered(self):
        path = self.currentPath()
        print(path)
    
    @QtCore.pyqtSlot()
    def on_actionCloseProject_triggered(self):
        path = self.currentPath()
        print(path)
    
    @QtCore.pyqtSlot()
    def on_actionOpenProject_triggered(self):
        print (self.currentPath())
    
    @QtCore.pyqtSlot()
    def on_actionProperties_triggered(self):
        path = self.currentPath()
    
    @QtCore.pyqtSlot()
    def on_actionRefresh_triggered(self):
        self.projectTreeProxyModel.refresh(self.treeViewProjects.currentIndex())
    
    @QtCore.pyqtSlot()
    def on_actionOpen_triggered(self):
        print(self.currentPath())
        
    @QtCore.pyqtSlot()
    def on_actionOpenSystemEditor_triggered(self):
        path = self.currentPath()
        QtGui.QDesktopServices.openUrl(QtCore.QUrl("file://%s" % path, QtCore.QUrl.TolerantMode))
    
    @QtCore.pyqtSlot()
    def on_actionOpenDefaultEditor_triggered(self):
        print(self.currentPath())

    @QtCore.pyqtSlot()
    def on_pushButtonCollapseAll_pressed(self):
        self.treeViewProjects.collapseAll()

    @QtCore.pyqtSlot(bool)
    def on_pushButtonSync_toggled(self, checked):
        if checked:
            #Conectar se�al
            self.mainWindow.currentEditorChanged.connect(self.on_mainWindow_currentEditorChanged)
        else:
            #Desconectar se�al
            self.mainWindow.currentEditorChanged.disconnect(self.on_mainWindow_currentEditorChanged)
    
    def on_mainWindow_currentEditorChanged(self, editor):
        if editor is not None and not editor.isNew():
            index = self.projectTreeProxyModel.indexForPath(editor.filePath)
            self.treeViewProjects.setCurrentIndex(index)
            
    #================================================
    # Sort and order Actions
    #================================================      
    @QtCore.pyqtSlot()
    def on_actionOrderByName_triggered(self):
        self.projectTreeProxyModel.sortBy("name", self.actionOrderFoldersFirst.isChecked(), self.actionOrderDescending.isChecked())
    
    @QtCore.pyqtSlot()
    def on_actionOrderBySize_triggered(self):
        self.projectTreeProxyModel.sortBy("size", self.actionOrderFoldersFirst.isChecked(), self.actionOrderDescending.isChecked())
    
    @QtCore.pyqtSlot()
    def on_actionOrderByDate_triggered(self):
        self.projectTreeProxyModel.sortBy("date", self.actionOrderFoldersFirst.isChecked(), self.actionOrderDescending.isChecked())
    
    @QtCore.pyqtSlot()
    def on_actionOrderByType_triggered(self):
        self.projectTreeProxyModel.sortBy("type", self.actionOrderFoldersFirst.isChecked(), self.actionOrderDescending.isChecked())
    
    @QtCore.pyqtSlot()
    def on_actionOrderDescending_triggered(self):
        self.projectTreeProxyModel.sortBy(self.projectTreeProxyModel.orderBy, self.actionOrderFoldersFirst.isChecked(), self.actionOrderDescending.isChecked())
    
    @QtCore.pyqtSlot()
    def on_actionOrderFoldersFirst_triggered(self):
        self.projectTreeProxyModel.sortBy(self.projectTreeProxyModel.orderBy, self.actionOrderFoldersFirst.isChecked(), self.actionOrderDescending.isChecked())