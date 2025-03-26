#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Pootling
# Copyright 2006 WordForge Foundation
#
# Version 0.1 (29 December 2006)
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# See the LICENSE file for more details. 
#
# Developed by:
#       Hok Kakada (hokkakada@khmeros.info)
#       Keo Sophon (keosophon@khmeros.info)
#       San Titvirak (titvirak@khmeros.info)
#       Seth Chanratha (sethchanratha@khmeros.info)
#
# This module is working on Catalog Manager of translation files

from PyQt4 import QtCore, QtGui
from pootling.ui.Ui_Catalog import Ui_Catalog
from pootling.modules.CatalogSetting import CatalogSetting
from pootling.modules import tmSetting
from pootling.modules.AboutEditor import AboutEditor
from translate.storage import factory
import pootling.modules.World as World
from pootling.modules.FindInCatalog import FindInCatalog
from pootling.modules.NewProject import newProject
from pootling.ui.Ui_tmSetting import Ui_tmsetting
import __version__
import os

class Catalog(QtGui.QMainWindow):
    """
    The Catalog Manager which holds the toolviews.
    """
    def __init__(self, parent = None):
        QtGui.QMainWindow.__init__(self, parent)
        self.ui = None
    
    def lazyInit(self):
        """
        Initialize only at time of calling Catalog.
        """
        if (self.ui):
            return
        self.ui = Ui_Catalog()
        self.ui.setupUi(self)
        self.resize(720,400)
        self.autoRefresh = True
        self.recentProject = []
        self.startOpenFile()
        title = self.tr("%s Catalog Manager" % (World.settingApp))
        self.setWindowTitle(title)
        self.ui.toolBar.toggleViewAction()
        self.ui.toolBar.setWindowTitle("ToolBar View")
        self.ui.toolBar.setStatusTip("Toggle ToolBar View")
        
        self.folderIcon = QtGui.QIcon("../images/open.png")
        self.iconFile = QtGui.QIcon("../images/iconfile.png")
        
        # set up table appearance and behavior
        self.headerLabels = [self.tr("Name"),
                            self.tr("Translated"),
                            self.tr("Fuzzy"),
                            self.tr("Untranslated"),
                            self.tr("Total"),
                            self.tr("CVS/SVN Status"),
                            self.tr("Last Revision"),
                            self.tr("Last Translator")]
        self.ui.treeCatalog.setColumnCount(len(self.headerLabels))
        self.ui.treeCatalog.setHeaderLabels(self.headerLabels)
        self.ui.treeCatalog.hideColumn(5)
        self.ui.treeCatalog.header().setResizeMode(QtGui.QHeaderView.Interactive)
        self.ui.treeCatalog.setWhatsThis("The catalog manager merges all files and folders enter one treewidget and displays all po, xlf... files. the way you can easily see if a template has been added or removed. Also some information about the files is displayed.")
        
        # File menu action
        self.connect(self.ui.actionQuit, QtCore.SIGNAL("triggered()"), QtCore.SLOT("close()"))
        self.ui.actionQuit.setWhatsThis("<h3>Quit</h3>Quit Catalog")
        self.ui.actionQuit.setStatusTip("Quit application")

        # Edit menu action
        self.connect(self.ui.actionReload, QtCore.SIGNAL("triggered()"), self.refresh)
        self.ui.actionReload.setWhatsThis("<h3>Reload</h3>Set the current files or folders to get the most up-to-date version.")
        self.ui.actionReload.setStatusTip("Reload the current files")

        # create statistics action
        self.connect(self.ui.actionStatistics, QtCore.SIGNAL("triggered()"), self.showStatistic)
        self.ui.actionStatistics.setWhatsThis("<h3>Statistics</h3>Show status of files that have filename, fuzzy, untranslated,translated and total of strings.")
        self.ui.actionStatistics.setStatusTip("Show status of files")

        # a new project of Catalog Manager
        self.Project = newProject(self)
        self.connect(self.ui.actionNew, QtCore.SIGNAL("triggered()"), self.Project.show)
        self.connect(self.ui.actionOpen, QtCore.SIGNAL("triggered()"), self.Project.openProject)
        self.connect(self.Project, QtCore.SIGNAL("updateCatalog"), self.updateCatalog)
        self.connect(self.Project, QtCore.SIGNAL("pathOfFileName"), self.setOpening)

        # catalog setting's checkboxes action.
        self.catSetting = CatalogSetting(self)
        self.connect(self.ui.actionConfigure, QtCore.SIGNAL("triggered()"), self.catSetting.show)
        self.connect(self.ui.actionBuild, QtCore.SIGNAL("triggered()"), self.emitBuildTM)
        self.ui.actionConfigure.setWhatsThis("<h3>Configure...</h3>Set the configuration items with your prefered values.")
        self.ui.actionConfigure.setStatusTip("Set the prefered configuration")
        self.connect(self.catSetting.ui.chbname, QtCore.SIGNAL("stateChanged(int)"), self.toggleHeaderItem)
        self.connect(self.catSetting.ui.chbfuzzy, QtCore.SIGNAL("stateChanged(int)"), self.toggleHeaderItem)
        self.connect(self.catSetting.ui.chblastrevision, QtCore.SIGNAL("stateChanged(int)"), self.toggleHeaderItem)
        self.connect(self.catSetting.ui.chbtranslator, QtCore.SIGNAL("stateChanged(int)"), self.toggleHeaderItem)
        self.connect(self.catSetting.ui.chbuntranslated, QtCore.SIGNAL("stateChanged(int)"), self.toggleHeaderItem)
        self.connect(self.catSetting.ui.chbtotal, QtCore.SIGNAL("stateChanged(int)"), self.toggleHeaderItem)
        self.connect(self.catSetting.ui.chbSVN, QtCore.SIGNAL("stateChanged(int)"), self.toggleHeaderItem)
        self.connect(self.catSetting.ui.chbtranslated, QtCore.SIGNAL("stateChanged(int)"), self.toggleHeaderItem)

        # Create Find String in Catalog
        self.findBar = FindInCatalog(self)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.findBar)

        self.connect(self.ui.actionFind_in_Files, QtCore.SIGNAL("triggered()"), self.findBar.showFind)
        self.ui.actionFind_in_Files.setWhatsThis("<h3>Find</h3>You can find string ever you want in Catalog")
        self.ui.actionFind_in_Files.setStatusTip("Search for a text")
        # emit findfiles signal from FindInCatalog file
        self.connect(self.findBar, QtCore.SIGNAL("initSearch"), self.find)

        # progress bar
        self.progressBar = QtGui.QProgressBar()
        self.progressBar.setEnabled(True)
        self.progressBar.setProperty("value",QtCore.QVariant(0))
        self.progressBar.setOrientation(QtCore.Qt.Horizontal)
        self.progressBar.setObjectName("progressBar")
        self.progressBar.setVisible(False)
        self.ui.statusbar.addPermanentWidget(self.progressBar)

        # Help menu of aboutQt
        self.ui.menuHelp.addSeparator()
        action = QtGui.QWhatsThis.createAction(self)
        self.ui.menuHelp.addAction(action)
        self.aboutDialog = AboutEditor(self)
        self.connect(self.ui.actionAbout, QtCore.SIGNAL("triggered()"), self.aboutDialog.showDialog)
        self.connect(self.ui.actionAboutQt, QtCore.SIGNAL("triggered()"), QtGui.qApp, QtCore.SLOT("aboutQt()"))
        
        self.connect(self.catSetting, QtCore.SIGNAL("updateCatalog"), self.updateCatalog)
        self.connect(self.ui.treeCatalog, QtCore.SIGNAL("itemDoubleClicked(QTreeWidgetItem *, int)"), self.emitOpenFile)
        self.setupCheckbox()

        # timer..
        self.timer = QtCore.QTimer()
        self.connect(self.timer, QtCore.SIGNAL("timeout()"), self.updateStatistic)
        self.lastFoundNumber = 0
        
        # context menu of items
        self.menu = QtGui.QMenu()
        self.actionOpen = self.menu.addAction(QtGui.QIcon("../images/open.png"), self.tr("Open"))
        self.actionFind = self.menu.addAction(QtGui.QIcon("../images/find.png"), self.tr("Find"))
        self.actionShowStat = self.menu.addAction(QtGui.QIcon("../images/statistic.png"), self.tr("Show statistic"))
        if (self.autoRefresh):
            self.actionOpen.setEnabled(False)
            self.actionFind.setEnabled(False)
            self.actionShowStat.setEnabled(False)

        self.connect(self.actionOpen, QtCore.SIGNAL("triggered()"), self.emitOpenFile)
        self.connect(self.actionFind, QtCore.SIGNAL("triggered()"), self.findBar.showFind)
        self.connect(self.actionShowStat, QtCore.SIGNAL("triggered()"), self.showStatistic)

        # install custom menu event for treeCatalog
        self.ui.treeCatalog.contextMenuEvent = self.customContextMenuEvent
        
        self.searchedCount = 0
        self.reachedEnd = True
        # bool indicates progress bar need update as TM progresses.
        self.allowUpdate = False
    
    def setReachedEnd(self):
        self.reachedEnd = True
    
    def find(self, searchString, searchOptions):
        """
        The search here is only determine if search string exist in filename,
        then it connect to search function in operator.
        """
        if (not searchString):
            return
        if (self.searchedCount >= len(self.fileItems)):
            self.searchedCount = 0
            return
        
        if (self.reachedEnd):
            self.reachedEnd = False
            while (self.searchedCount < len(self.fileItems)):
                item = self.fileItems[self.searchedCount]
                self.searchedCount += 1
            
                filename = self.getFilename(item)
                store = factory.getobject(filename)
                found = -1
                for unit in store.units:
                    searchableText = ""
                    if (searchOptions & World.source):
                        searchableText += unit.source
                    if (searchOptions & World.target):
                        searchableText += unit.target
                    index = searchableText.find(searchString)
                    if (index > -1):
                        found = index
                        break
                if (found >= 0):
                    self.emit(QtCore.SIGNAL("openFile"), filename)
                    filter = []
                    if (searchOptions & World.source):
                        filter.append(World.source)
                    if (searchOptions & World.target):
                        filter.append(World.target)
                    self.emit(QtCore.SIGNAL("initSearch"), searchString, filter, False)
                    self.emit(QtCore.SIGNAL("searchNext"))
                    break
        else:
            self.emit(QtCore.SIGNAL("searchNext"))
        return

    def showStatistic(self):
        item = self.ui.treeCatalog.currentItem()
        if (not item):
            return
        
        filename = self.getFilename(item)
        title = unicode(os.path.basename(filename))
        
        self.numOfFiles = 0
        stats = self.getStatsFromItem(item)
        translated = stats["translated"]
        fuzzy = stats["fuzzy"]
        untranslated = stats["untranslated"]
        total = float(translated + fuzzy + untranslated)
        
        if (total > 0):
            perTranslated = str((translated/total) * 100)
            perTranslated = perTranslated[0:perTranslated.find(".")+3] + "%"
            perFuzzy = str((fuzzy/total) * 100)
            perFuzzy = perFuzzy[0:perFuzzy.find(".")+3] + "%"
            perUntranslated = str((untranslated/total) * 100)
            perUntranslated = perUntranslated[0:perUntranslated.find(".")+3] + "%"
        else:
            perTranslated = "0%"
            perFuzzy = "0%"
            perUntranslated = "0%"

        from pootling.modules.StatisticsDialog import StatisticDialog
        self.statisticsDialog = StatisticDialog(self)

        self.lblStatistic = self.statisticsDialog.ui.lblStatistic
        self.lblStatistic.setText(title)

        self.lblNumberofFiles = self.statisticsDialog.ui.lblNumberofFiles
        self.lblNumberofFiles.setText(str(self.numOfFiles))
  
        self.lblTranslated = self.statisticsDialog.ui.lblTranslated
        self.lblTranslated.setText(str(translated))
      
        self.lblTransPercent = self.statisticsDialog.ui.lblTransPercent
        self.lblTransPercent.setText(perTranslated)

        self.lblFuzzy = self.statisticsDialog.ui.lblFuzzy
        self.lblFuzzy.setText(str(fuzzy))

        self.lblFuzzyPercent = self.statisticsDialog.ui.lblFuzzyPercent
        self.lblFuzzyPercent.setText(perFuzzy)

        self.lblUntranslated = self.statisticsDialog.ui.lblUntranslated
        self.lblUntranslated.setText(str(untranslated)) 

        self.lblUntranPercent = self.statisticsDialog.ui.lblUntranPercent
        self.lblUntranPercent.setText(perUntranslated) 

        self.lblTotal = self.statisticsDialog.ui.lblTotal
        self.lblTotal.setText(str(int(total)))

        self.statisticsDialog.show()

    def toggleHeaderItem(self):
        if (isinstance(self.sender(), QtGui.QCheckBox)):
            text = self.sender().text()
            if text in self.headerLabels:
                checked = self.sender().isChecked()
                if (checked):
                    self.ui.treeCatalog.showColumn(self.headerLabels.index(text))
                    self.ui.treeCatalog.hideColumn(5)
                else:
                    self.ui.treeCatalog.hideColumn(self.headerLabels.index(text))
                    self.ui.treeCatalog.hideColumn(5)
                World.settings.setValue("Catalog." + text, QtCore.QVariant(checked))

    def updateProgress(self, value):
        """
        Set the value for the progress bar.
        self.allowUpdate is a condition wether to update or not, use to protect
        other class call.
        @param value: value to set.
        """
        if (not hasattr(self, "allowUpdate")) or (not self.allowUpdate):
           return
        if (not self.progressBar.isVisible()):
            self.progressBar.setVisible(True)
        elif (value == 100):
            self.allowUpdate = False
            self.progressBar.setVisible(False)
        self.progressBar.setValue(value)
        
    def showDialog(self):
        self.lazyInit()
        self.show()
        cats = World.settings.value("CatalogPath").toStringList()
        if (cats) and (self.ui.treeCatalog.topLevelItemCount() == 0):
            self.updateCatalog()
    
    def updateCatalog(self,  itemList = [],  includeSub = None):
        """
        Read data from world's "CatalogPath" and display statistic of files
        in tree view.
        """
        # Icon enabled when toolBar not files into treeCatalog
        self.lazyInit()
        self.show()
        self.ui.actionFind_in_Files.setEnabled(True)
        self.ui.actionStatistics.setEnabled(True)
        self.ui.actionReload.setEnabled(True)
        # Icon enabled when context menu not files into treeCatalog
        self.actionOpen.setEnabled(True)
        self.actionFind.setEnabled(True)
        self.actionShowStat.setEnabled(True)
        self.ui.treeCatalog.clear()
        if itemList:
            cats = itemList
            includeSub = includeSub
        else:
            cats = World.settings.value("CatalogPath").toStringList()
            includeSub = World.settings.value("diveIntoSubCatalog").toBool()
        
        self.fileItems = []
        self.itemNumber = 0
        
        for catalogFile in cats:
            catalogFile = unicode(catalogFile)
            title = unicode(self.tr("%s - %s Catalog Manager")) % (unicode(catalogFile), World.settingApp)
            self.setWindowTitle(str(title))
            self.addCatalogFile(catalogFile, includeSub, None)
        
        self.ui.treeCatalog.resizeColumnToContents(0)
        self.allowUpdate = True
        self.timer.start(10)
    
    def addCatalogFile(self, path, includeSub, item):
        """
        add path to catalog tree view if it's file, if it's directory then
        dive into it and add files.
        """
        if (os.path.isfile(path)):
            existedItem = self.getExistedItem(os.path.dirname(path))
            if (existedItem):
                item = existedItem
            elif (item == None):
                item = QtGui.QTreeWidgetItem(item)
                self.ui.treeCatalog.addTopLevelItem(item)
                self.ui.treeCatalog.expandItem(item)
                item.setText(0, os.path.dirname(path))

            # if file is already existed in the item's child... skip.
            if (path.endswith(".po") or path.endswith(".pot") or path.endswith(".xlf") or path.endswith(".xliff")) and (not self.ifFileExisted(path, item)):
                childItem = QtGui.QTreeWidgetItem(item)
                childItem.setText(0, os.path.basename(path))
                childItem.setIcon(0, self.iconFile)
                self.fileItems.append(childItem)
            # check extension of file if not have .po or .pot or xlf and xliff files. hide folder
#            if (item.childCount() == 0):
#                item.parent().takeChild(0)

        if (os.path.isdir(path)) and (not path.endswith(".svn")):
            existedItem = self.getExistedItem(path)
            if (existedItem):
                # it's already existed, so use the existed one
                childItem = existedItem
            else:
                # it does not exist in tree yet, create new one
                if (item == None):
                    childItem = QtGui.QTreeWidgetItem(item)
                    self.ui.treeCatalog.addTopLevelItem(childItem)
                    self.ui.treeCatalog.expandItem(childItem)
                    childItem.setText(0, path)
                # it's existed in tree but it is the sub directory
                elif hasattr(item, "parent"):
##                    childItem = QtGui.QTreeWidgetItem()
##                    item.insertChild(0, childItem)
                    childItem = QtGui.QTreeWidgetItem(item)
                    childItem.setText(0, os.path.basename(path))
                childItem.setIcon(0, self.folderIcon)

#            if (item.childCount() == 0):
#                item.setHidden(True)

            for root, dirs, files in os.walk(path):
                for file in files:
                    path = os.path.join(root + os.path.sep + file)
                    self.addCatalogFile(path, includeSub, childItem)
                # whether dive into subfolder
                if (includeSub):
                    for folder in dirs:
                        path = os.path.join(root + os.path.sep + folder)
                        self.addCatalogFile(path, includeSub, childItem)

                break
    
    def getExistedItem(self, path):
        """
        Get existed item in the tree's top level. If the item existed, it returns
        the item, otherwise returns False.
        """
        for i in range(self.ui.treeCatalog.topLevelItemCount()):
            item = self.ui.treeCatalog.topLevelItem(i)
            if (hasattr(item, "text")) and (item.text(0) == path):
                return item
        return False
    
    def ifFileExisted(self, path, item):
        """
        Get existed item in the tree's top level. If the item existed, it returns
        the item, otherwise returns False.
        """
        if (not hasattr(item, "childCount")):
            return False
        for i in range(item.childCount()):
            it = item.child(i)
            if (hasattr(it, "text")) and (it.text(0) == os.path.basename(path)):
                return it
        return False
    
    def getStats(self, filename):
        """
        return a dictionary which consist of basename, translatedCount, fuzzyCount,
        untranslatedCount, totalCount, subVersionState, revisionDate, lastTranslator
        or return False when error.
        @param filename: path and file name.
        """
        try:
            store = factory.getobject(filename)
        except:
            return False
        
        if (not os.path.isfile(filename)):
            return False
        
        basename = os.path.basename(filename)
        numTranslated = store.translated_unitcount()
        numFuzzy = store.fuzzy_unitcount()
        numUntranslated = store.untranslated_unitcount()
    
        numTotal = numTranslated + numUntranslated + numFuzzy
        subVersionState = ""
        
        revisionDate = ""
        lastTranslator = ""
        if hasattr(store, "parseheader"):
            headerDic = store.parseheader()
            try:
                revisionDate = str(headerDic["PO-Revision-Date"])
            except:
                pass
            try:
                lastTranslator = str(headerDic["Last-Translator"])
            except:
                pass
        
        return {"basename":basename, "numTranslated":numTranslated, "numFuzzy":numFuzzy, 
                "numUntranslated":numUntranslated, "numTotal":numTotal, 
                "subVersionState":subVersionState, "revisionDate":revisionDate, 
                "lastTranslator":lastTranslator}
    
    def getStatsFromItem(self, item):
        """
        get number of translated, untranslated, and fuzzy units from item.
        @param item: treewidget item which has at least those four fields.
        @return dictionary of stats.
        """
        try:
            translated = int(item.text(1))
            fuzzy = int(item.text(2))
            untranslated = int(item.text(3))
            self.numOfFiles += 1
        except:
            translated = 0
            fuzzy = 0
            untranslated = 0
        
        for i in range(item.childCount()):
            child = item.child(i)
            stats = self.getStatsFromItem(child)
            translated += stats["translated"]
            fuzzy += stats["fuzzy"]
            untranslated += stats["untranslated"]
        
        
        return {"translated": translated, "fuzzy":fuzzy, "untranslated":untranslated}
    
    def setupCheckbox(self):
        value = World.settings.value("Catalog.Name")
        if (value.isValid()):
            if not (value.toBool()):
                checkState = QtCore.Qt.Unchecked
            else:
                checkState = QtCore.Qt.Checked
        else:
            # on fresh start of program, if the value is not in setting yet
            # make it True by default.
            checkState = QtCore.Qt.Checked
        self.catSetting.ui.chbname.setCheckState(checkState)
        
        value = World.settings.value("Catalog.Translated")
        if (value.isValid()):
            if not (value.toBool()):
                checkState = QtCore.Qt.Unchecked
            else:
                checkState = QtCore.Qt.Checked
        else:
            checkState = QtCore.Qt.Checked
        self.catSetting.ui.chbtranslated.setCheckState(checkState)
        
        value = World.settings.value("Catalog.Fuzzy")
        if (value.isValid()):
            if not (value.toBool()):
                checkState = QtCore.Qt.Unchecked
            else:
                checkState = QtCore.Qt.Checked
        else:
            checkState = QtCore.Qt.Checked
        self.catSetting.ui.chbfuzzy.setCheckState(checkState)
        
        value = World.settings.value("Catalog.Untranslated")
        if (value.isValid()):
            if not (value.toBool()):
                checkState = QtCore.Qt.Unchecked
            else:
                checkState = QtCore.Qt.Checked
        else:
            checkState = QtCore.Qt.Checked
        self.catSetting.ui.chbuntranslated.setCheckState(checkState)
        
        value = World.settings.value("Catalog.Total")
        if (value.isValid()):
            if not (value.toBool()):
                checkState = QtCore.Qt.Unchecked
            else:
                checkState = QtCore.Qt.Checked
        else:
            checkState = QtCore.Qt.Checked
        self.catSetting.ui.chbtotal.setCheckState(checkState)
        
        value = World.settings.value("Catalog.CVS/SVN Status")
        if (value.isValid()):
            if not (value.toBool()):
                checkState = QtCore.Qt.Unchecked
            else:
                checkState = QtCore.Qt.Checked
        else:
            checkState = QtCore.Qt.Checked
        self.catSetting.ui.chbSVN.setCheckState(checkState)
        self.catSetting.ui.chbSVN.setVisible(False)
        
        value = World.settings.value("Catalog.Last Revision")
        if (value.isValid()):
            if not (value.toBool()):
                checkState = QtCore.Qt.Unchecked
            else:
                checkState = QtCore.Qt.Checked
        else:
            checkState = QtCore.Qt.Checked
        self.catSetting.ui.chblastrevision.setCheckState(checkState)
        
        value = World.settings.value("Catalog.Last Translator")
        if (value.isValid()):
            if not (value.toBool()):
                checkState = QtCore.Qt.Unchecked
            else:
                checkState = QtCore.Qt.Checked
        else:
            checkState = QtCore.Qt.Checked
        self.catSetting.ui.chbtranslator.setCheckState(checkState)
        
    def emitOpenFile(self, item=None, col=None):
        """
        Send "openFile" signal with filename.
        """
        if (not item):
            try:
                item = self.ui.treeCatalog.selectedItems()[0]
            except:
                return
        
        filename = self.getFilename(item)
        if (os.path.isfile(filename)): 
            self.emit(QtCore.SIGNAL("openFile"), filename)
        
    def getFilename(self, item):
        """
        return filename join from item.text(0) to its parent.
        """
        if (not item):
            return None
        filename = unicode(item.text(0))
        if (item.parent()):
            filename = os.path.join(self.getFilename(item.parent()) + os.path.sep + filename)
        return filename
    
    def refresh(self):
        self.settings = QtCore.QSettings()
        if self.autoRefresh:
            self.updateCatalog()
        else:
            self.settings.sync()
    
    def emitBuildTM(self):
        """
        Emit "buildTM" signal with catalog paths.
        """
        catPaths = []
        for i in range(self.ui.treeCatalog.topLevelItemCount()):
            topItem = self.ui.treeCatalog.topLevelItem(i)
            catPath = self.getFilename(topItem)
            catPaths.append(catPath)
        self.allowUpdate = True
        self.emit(QtCore.SIGNAL("buildTM"), catPaths)
    
    def updateStatistic(self):
        if (len(self.fileItems) <= 0):
            self.timer.stop()
            self.itemNumber = 0
            return

        self.timer.stop()
        
        item = self.fileItems[self.itemNumber]
        path = self.getFilename(item)
        childStats = self.getStats(path)
  
        if (childStats):
            item.setText(1, str(childStats["numTranslated"]))
            item.setText(2, str(childStats["numFuzzy"]))
            item.setText(3, str(childStats["numUntranslated"]))
            item.setText(4, str(childStats["numTotal"]))
            item.setText(5, childStats["subVersionState"])
            item.setText(6, childStats["revisionDate"])
            item.setText(7, childStats["lastTranslator"])

        self.itemNumber += 1
        
        perc = int((float(self.itemNumber) / len(self.fileItems)) * 100)
        self.updateProgress(perc)
        
        # start getting statistic
        self.timer.start(10)
        if (self.itemNumber == len(self.fileItems)):
            self.timer.stop()
            self.itemNumber = 0

    def startOpenFile(self):
        files = World.settings.value("recentProjectList").toStringList()
        if (files):
            self.createRecentProject()
            self.ui.menuOpenRecentProject.setEnabled(True)
        else:
            self.ui.menuOpenRecentProject.setEnabled(False)

    def createRecentProject(self):
        for i in range(World.MaxRecentFiles):
            self.recentProject.append(QtGui.QAction(self))
            self.recentProject[i].setVisible(False)
            self.connect(self.recentProject[i], QtCore.SIGNAL("triggered()"), self.startRecentProject)
            self.ui.menuOpenRecentProject.addAction(self.recentProject[i])
        self.ui.menuOpenRecentProject.addSeparator()
        self.clearAction = QtGui.QAction("&Clear", self)
        self.connect(self.clearAction, QtCore.SIGNAL("triggered()"), self.clearRecentProject)
        self.ui.menuOpenRecentProject.addAction(self.clearAction)
        self.ui.menuOpenRecentProject.setEnabled(False)
        self.updateRecentProject()

    def startRecentProject(self):
        action = self.sender()
        filename = action.data().toString()
        self.setOpening(filename)

    def setOpening(self, filename):
        proSettings = QtCore.QSettings(filename, QtCore.QSettings.IniFormat)
        itemList = proSettings.value("itemList").toStringList()
        # set location of filename to list Widget of Catalog Setting when click open recent project.
        self.catSetting = CatalogSetting(self)
        self.catSetting.clearLocation()
        for location in itemList:
            self.catSetting.addLocation(location)
        includeSub = proSettings.value("itemList").toBool()
        self.updateCatalog(itemList,  includeSub)

        files = World.settings.value("recentProjectList").toStringList()
        files.removeAll(filename)
        files.prepend(filename)
        while files.count() > World.MaxRecentFiles:
            files.removeAt(files.count() - 1)
        if (files.count() > 0):
            self.ui.menuOpenRecentProject.setEnabled(True)
        World.settings.setValue("recentProjectList", QtCore.QVariant(files))
        self.updateRecentProject()

    def clearRecentProject(self):
        self.ui.menuOpenRecentProject.clear()
        self.ui.menuOpenRecentProject.setEnabled(False)
        World.settings.remove("recentProjectList")

    def updateRecentProject(self):
        """
        Update recent project of open recent project with names of recent opened project
        """
        if (not len(self.ui.menuOpenRecentProject.actions())):
            self.createRecentProject()
        project = World.settings.value("recentProjectList").toStringList()
        if (project.count() > 0):
            self.ui.menuOpenRecentProject.setEnabled(True)
        numRecentProject = min(project.count(), World.MaxRecentFiles)
        for i in range(numRecentProject):
            self.recentProject[i].setText(self.tr("&" + str(i+1) + ": ") + project[i])
            self.recentProject[i].setData(QtCore.QVariant(project[i]))
            self.recentProject[i].setVisible(True)

        for j in range(numRecentProject, World.MaxRecentFiles):
            self.recentProject[j].setVisible(False)

    def customContextMenuEvent(self, e):
        self.menu.exec_(e.globalPos())

def main(self):
    # set the path for QT in order to find the icons
    if __name__ == "__main__":
        QtCore.QDir.setCurrent(os.path.join(sys.path[0], "../ui"))
        app = QtGui.QApplication(sys.argv)
        catalog = Catalog()
        sys.exit(app.exec_())

if __name__ == "__main__":
    main()
