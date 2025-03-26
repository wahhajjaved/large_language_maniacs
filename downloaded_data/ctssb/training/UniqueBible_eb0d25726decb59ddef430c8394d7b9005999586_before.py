import config, platform, webbrowser, os
from qtpy.QtCore import Qt
from qtpy.QtGui import QStandardItemModel, QStandardItem
from qtpy.QtWidgets import QDialog, QLabel, QTableView, QAbstractItemView, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton, QMessageBox

class ConfigFlagsWindow(QDialog):

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        # set title
        self.setWindowTitle(config.thisTranslation["menu_config_flags"])
        self.setMinimumSize(830, 500)
        # set variables
        self.setupVariables()
        # setup interface
        self.setupUI()

    def setupVariables(self):
        self.isUpdating = False

    def setupUI(self):
        mainLayout = QVBoxLayout()

        title = QLabel(config.thisTranslation["menu_config_flags"])
        title.mouseReleaseEvent = self.openWiki
        mainLayout.addWidget(title)

        filterLayout = QHBoxLayout()
        filterLayout.addWidget(QLabel(config.thisTranslation["menu5_search"]))
        self.filterEntry = QLineEdit()
        self.filterEntry.textChanged.connect(self.resetItems)
        filterLayout.addWidget(self.filterEntry)
        mainLayout.addLayout(filterLayout)

        self.dataView = QTableView()
        self.dataView.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.dataView.setSortingEnabled(True)
        self.dataViewModel = QStandardItemModel(self.dataView)
        self.dataView.setModel(self.dataViewModel)
        self.resetItems()
        self.dataViewModel.itemChanged.connect(self.itemChanged)
        mainLayout.addWidget(self.dataView)

        buttonLayout = QHBoxLayout()
        button = QPushButton(config.thisTranslation["close"])
        button.clicked.connect(self.close)
        buttonLayout.addWidget(button)
        button = QPushButton(config.thisTranslation["restoreAllDefaults"])
        button.clicked.connect(self.restoreAllDefaults)
        buttonLayout.addWidget(button)
        mainLayout.addLayout(buttonLayout)

        self.setLayout(mainLayout)

    def getOptions(self):
        options = [
            ("showControlPanelOnStartup", config.showControlPanelOnStartup, self.showControlPanelOnStartupChanged, False, config.thisTranslation["showControlPanelOnStartup"]),
            ("preferControlPanelForCommandLineEntry", config.preferControlPanelForCommandLineEntry, self.preferControlPanelForCommandLineEntryChanged, False, config.thisTranslation["preferControlPanelForCommandLineEntry"]),
            ("closeControlPanelAfterRunningCommand", config.closeControlPanelAfterRunningCommand, self.closeControlPanelAfterRunningCommandChanged, True, config.thisTranslation["closeControlPanelAfterRunningCommand"]),
            ("restrictControlPanelWidth", config.restrictControlPanelWidth, self.restrictControlPanelWidthChanged, False, config.thisTranslation["restrictControlPanelWidth"]),
            ("clearCommandEntry", config.clearCommandEntry, self.clearCommandEntryChanged, False, config.thisTranslation["clearCommandEntry"]),
            ("openBibleWindowContentOnNextTab", config.openBibleWindowContentOnNextTab, self.openBibleWindowContentOnNextTabChanged, False, config.thisTranslation["openBibleWindowContentOnNextTab"]),
            ("openStudyWindowContentOnNextTab", config.openStudyWindowContentOnNextTab, self.openStudyWindowContentOnNextTabChanged, True, config.thisTranslation["openStudyWindowContentOnNextTab"]),
            ("populateTabsOnStartup", config.populateTabsOnStartup, self.populateTabsOnStartupChanged, False, config.thisTranslation["populateTabsOnStartup"]),
            ("qtMaterial", config.qtMaterial, self.qtMaterialChanged, False, config.thisTranslation["qtMaterial"]),
            ("addBreakAfterTheFirstToolBar", config.addBreakAfterTheFirstToolBar, self.addBreakAfterTheFirstToolBarChanged, True, config.thisTranslation["addBreakAfterTheFirstToolBar"]),
            ("addBreakBeforeTheLastToolBar", config.addBreakBeforeTheLastToolBar, self.addBreakBeforeTheLastToolBarChanged, False, config.thisTranslation["addBreakBeforeTheLastToolBar"]),
            ("parserStandarisation", (config.parserStandarisation == "YES"), self.parserStandarisationChanged, False, config.thisTranslation["parserStandarisation"]),
            ("useFastVerseParsing", config.useFastVerseParsing, self.useFastVerseParsingChanged, False, config.thisTranslation["useFastVerseParsing"]),
            ("parseWordDocument", config.parseWordDocument, self.parseWordDocumentChanged, True, config.thisTranslation["parseWordDocument"]),
            ("convertChapterVerseDotSeparator", config.convertChapterVerseDotSeparator, self.convertChapterVerseDotSeparatorChanged, True, config.thisTranslation["convertChapterVerseDotSeparator"]),
            ("parseBookChapterWithoutSpace", config.parseBookChapterWithoutSpace, self.parseBookChapterWithoutSpaceChanged, True, config.thisTranslation["parseBookChapterWithoutSpace"]),
            ("preferHtmlMenu", config.preferHtmlMenu, self.preferHtmlMenuChanged, False, config.thisTranslation["preferHtmlMenu"]),
            ("showVerseNumbersInRange", config.showVerseNumbersInRange, self.showVerseNumbersInRangeChanged, True, config.thisTranslation["showVerseNumbersInRange"]),
            ("addFavouriteToMultiRef", config.addFavouriteToMultiRef, self.addFavouriteToMultiRefChanged, False, config.thisTranslation["addFavouriteToMultiRef"]),
            ("enableVerseHighlighting", config.enableVerseHighlighting, self.enableVerseHighlightingChanged, False, config.thisTranslation["enableVerseHighlighting"]),
            ("regexCaseSensitive", config.regexCaseSensitive, self.regexCaseSensitiveChanged, False, config.thisTranslation["regexCaseSensitive"]),
            ("alwaysDisplayStaticMaps", config.alwaysDisplayStaticMaps, self.alwaysDisplayStaticMapsChanged, False, config.thisTranslation["alwaysDisplayStaticMaps"]),
            ("exportEmbeddedImages", config.exportEmbeddedImages, self.exportEmbeddedImagesChanged, True, config.thisTranslation["exportEmbeddedImages"]),
            ("clickToOpenImage", config.clickToOpenImage, self.clickToOpenImageChanged, True, config.thisTranslation["clickToOpenImage"]),
            ("showNoteIndicatorOnBibleChapter", config.showNoteIndicatorOnBibleChapter, self.parent.enableNoteIndicatorButtonClicked, True, config.thisTranslation["showNoteIndicatorOnBibleChapter"]),
            ("openBibleNoteAfterSave", config.openBibleNoteAfterSave, self.openBibleNoteAfterSaveChanged, False, config.thisTranslation["openBibleNoteAfterSave"]),
            ("openBibleNoteAfterEditorClosed", config.openBibleNoteAfterEditorClosed, self.openBibleNoteAfterEditorClosedChanged, False, config.thisTranslation["openBibleNoteAfterEditorClosed"]),
            ("hideNoteEditorStyleToolbar", config.hideNoteEditorStyleToolbar, self.hideNoteEditorStyleToolbarChanged, False, config.thisTranslation["hideNoteEditorStyleToolbar"]),
            ("hideNoteEditorTextUtility", config.hideNoteEditorTextUtility, self.hideNoteEditorTextUtilityChanged, True, config.thisTranslation["hideNoteEditorTextUtility"]),
            ("overwriteNoteFont", config.overwriteNoteFont, self.overwriteNoteFontChanged, True, config.thisTranslation["overwriteNoteFont"]),
            ("overwriteNoteFontSize", config.overwriteNoteFontSize, self.overwriteNoteFontSizeChanged, True, config.thisTranslation["overwriteNoteFontSize"]),
            ("overwriteBookFont", config.overwriteBookFont, self.overwriteBookFontChanged, True, config.thisTranslation["overwriteBookFont"]),
            ("overwriteBookFontSize", config.overwriteBookFontSize, self.overwriteBookFontSizeChanged, True, config.thisTranslation["overwriteBookFontSize"]),
            ("bookOnNewWindow", config.bookOnNewWindow, self.bookOnNewWindowChanged, False, config.thisTranslation["bookOnNewWindow"]),
            ("virtualKeyboard", config.virtualKeyboard, self.virtualKeyboardChanged, False, config.thisTranslation["virtualKeyboard"]),
            ("useWebbrowser", config.useWebbrowser, self.useWebbrowserChanged, True, config.thisTranslation["useWebbrowser"]),
            ("removeHighlightOnExit", config.removeHighlightOnExit, self.removeHighlightOnExitChanged, False, config.thisTranslation["removeHighlightOnExit"]),
            ("disableModulesUpdateCheck", config.disableModulesUpdateCheck, self.disableModulesUpdateCheckChanged, True, config.thisTranslation["disableModulesUpdateCheck"]),
            ("updateWithGitPull", config.updateWithGitPull, self.updateWithGitPullChanged, True, config.thisTranslation["updateWithGitPull"]),
            ("enableGist", config.enableGist, self.enableGistChanged, False, config.thisTranslation["enableGist"]),
            ("enableMacros", config.enableMacros, self.enableMacrosChanged, False, config.thisTranslation["enableMacros"]),
            ("enablePlugins", config.enablePlugins, self.enablePluginsChanged, True, config.thisTranslation["enablePlugins"]),
            ("hideBlankVerseCompare", config.hideBlankVerseCompare, self.hideBlankVerseCompareChanged, False, config.thisTranslation["hideBlankVerseCompare"]),
            ("enforceCompareParallel", config.enforceCompareParallel, self.parent.enforceCompareParallelButtonClicked, False, config.thisTranslation["enforceCompareParallel"]),
            ("enableMenuUnderline", config.enableMenuUnderline, self.enableMenuUnderlineChanged, True, config.thisTranslation["enableMenuUnderline"]),
            ("openBibleInMainViewOnly", config.openBibleInMainViewOnly, self.parent.enableStudyBibleButtonClicked, False, config.thisTranslation["openBibleInMainViewOnly"]),
            ("addOHGBiToMorphologySearch", config.addOHGBiToMorphologySearch, self.addOHGBiToMorphologySearchChanged, True, config.thisTranslation["addOHGBiToMorphologySearch"]),
        ]
        if config.isTtsInstalled:
            options += [
                ("useLangDetectOnTts", config.useLangDetectOnTts, self.useLangDetectOnTtsChanged, False, config.thisTranslation["useLangDetectOnTts"]),
                ("ttsEnglishAlwaysUS", config.ttsEnglishAlwaysUS, self.ttsEnglishAlwaysUSChanged, False, config.thisTranslation["ttsEnglishAlwaysUS"]),
                ("ttsEnglishAlwaysUK", config.ttsEnglishAlwaysUK, self.ttsEnglishAlwaysUKChanged, False, config.thisTranslation["ttsEnglishAlwaysUK"]),
                ("ttsChineseAlwaysMandarin", config.ttsChineseAlwaysMandarin, self.ttsChineseAlwaysMandarinChanged, False, config.thisTranslation["ttsChineseAlwaysMandarin"]),
                ("ttsChineseAlwaysCantonese", config.ttsChineseAlwaysCantonese, self.ttsChineseAlwaysCantoneseChanged, False, config.thisTranslation["ttsChineseAlwaysCantonese"]),
            ]
        if platform.system() == "Linux":
            options += [
                ("linuxStartFullScreen", config.linuxStartFullScreen, self.linuxStartFullScreenChanged, False, config.thisTranslation["linuxStartFullScreen"]),
                ("fcitx", config.fcitx, self.fcitxChanged, False, config.thisTranslation["fcitx"]),
                ("ibus", config.ibus, self.ibusChanged, False, config.thisTranslation["ibus"]),
                ("espeak", config.espeak, self.espeakChanged, False, config.thisTranslation["espeak"]),
            ]
        if config.developer:
            options += [
                ("forceGenerateHtml", config.forceGenerateHtml, self.forceGenerateHtmlChanged, False, config.thisTranslation["forceGenerateHtml"]),
                ("enableLogging", config.enableLogging, self.enableLoggingChanged, False, config.thisTranslation["enableLogging"]),
                ("logCommands", config.logCommands, self.logCommandsChanged, False, config.thisTranslation["logCommands"]),
            ]
        data = {}
        for flag, configValue, action, default, tooltip in options:
            data[flag] = [configValue, default, tooltip, action]
        return data

    def restoreAllDefaults(self):
        for key, value in self.data.items():
            code = "config.{0} = {1}".format(key, value[1])
            exec(code)
        self.resetItems()
        self.displayMessage(config.thisTranslation["message_restart"])

    def itemChanged(self, standardItem):
        flag = standardItem.text()
        if flag in self.data and not self.isUpdating:
            self.data[flag][-1]()

    def resetItems(self):
        self.isUpdating = True
        # Empty the model before reset
        self.dataViewModel.clear()
        # Reset
        self.data = self.getOptions()
        filterEntry = self.filterEntry.text().lower()
        rowCount = 0
        for flag, value in self.data.items():
            configValue, default, tooltip, *_ = value
            if filterEntry == "" or (filterEntry != "" and (filterEntry in flag.lower() or filterEntry in tooltip.lower())):
                # 1st column
                item = QStandardItem(flag)
                item.setToolTip(tooltip)
                item.setCheckable(True)
                item.setCheckState(Qt.CheckState.Checked if configValue else Qt.CheckState.Unchecked)
                self.dataViewModel.setItem(rowCount, 0, item)
                # 2nd column
                item = QStandardItem(str(default))
                self.dataViewModel.setItem(rowCount, 1, item)
                # 3rd column
                tooltip = tooltip.replace("\n", " ")
                item = QStandardItem(tooltip)
                item.setToolTip(tooltip)
                self.dataViewModel.setItem(rowCount, 2, item)
                # add row count
                rowCount += 1
        self.dataViewModel.setHorizontalHeaderLabels([config.thisTranslation["flag"], config.thisTranslation["default"], config.thisTranslation["description"]])
        self.dataView.resizeColumnsToContents()
        self.isUpdating = False

    def displayMessage(self, message="", title="UniqueBible"):
        QMessageBox.information(self, title, message)

    def openWiki(self, event):
        wikiLink = "https://github.com/eliranwong/UniqueBible/wiki/Config-file-reference"
        webbrowser.open(wikiLink)

    def ibusChanged(self):
        config.ibus = not config.ibus
        if config.fcitx and config.ibus:
            config.fcitx = not config.fcitx
        if config.virtualKeyboard and config.ibus:
            config.virtualKeyboard = not config.virtualKeyboard
        self.displayMessage(config.thisTranslation["message_restart"])

    def fcitxChanged(self):
        config.fcitx = not config.fcitx
        if config.fcitx and config.ibus:
            config.ibus = not config.ibus
        if config.fcitx and config.virtualKeyboard:
            config.virtualKeyboard = not config.virtualKeyboard
        self.displayMessage(config.thisTranslation["message_restart"])

    def virtualKeyboardChanged(self):
        config.virtualKeyboard = not config.virtualKeyboard
        if config.fcitx and config.virtualKeyboard:
            config.fcitx = not config.fcitx
        if config.virtualKeyboard and config.ibus:
            config.ibus = not config.ibus
        self.displayMessage(config.thisTranslation["message_restart"])

    def parseWordDocumentChanged(self):
        config.parseWordDocument = not config.parseWordDocument

    def useLangDetectOnTtsChanged(self):
        config.useLangDetectOnTts = not config.useLangDetectOnTts

    def ttsEnglishAlwaysUSChanged(self):
        config.ttsEnglishAlwaysUS = not config.ttsEnglishAlwaysUS
        if config.ttsEnglishAlwaysUK and config.ttsEnglishAlwaysUS:
            config.ttsEnglishAlwaysUK = not config.ttsEnglishAlwaysUK

    def ttsEnglishAlwaysUKChanged(self):
        config.ttsEnglishAlwaysUK = not config.ttsEnglishAlwaysUK
        if config.ttsEnglishAlwaysUK and config.ttsEnglishAlwaysUS:
            config.ttsEnglishAlwaysUS = not config.ttsEnglishAlwaysUS

    def ttsChineseAlwaysMandarinChanged(self):
        config.ttsChineseAlwaysMandarin = not config.ttsChineseAlwaysMandarin
        if config.ttsChineseAlwaysMandarin and config.ttsChineseAlwaysCantonese:
            config.ttsChineseAlwaysCantonese = not config.ttsChineseAlwaysCantonese

    def ttsChineseAlwaysCantoneseChanged(self):
        config.ttsChineseAlwaysCantonese = not config.ttsChineseAlwaysCantonese
        if config.ttsChineseAlwaysMandarin and config.ttsChineseAlwaysCantonese:
            config.ttsChineseAlwaysMandarin = not config.ttsChineseAlwaysMandarin

    def showVerseNumbersInRangeChanged(self):
        config.showVerseNumbersInRange = not config.showVerseNumbersInRange

    #def customPythonOnStartupChanged(self):
    #    config.customPythonOnStartup = not config.customPythonOnStartup

    def openBibleWindowContentOnNextTabChanged(self):
        config.openBibleWindowContentOnNextTab = not config.openBibleWindowContentOnNextTab
        self.newTabException = False

    def showControlPanelOnStartupChanged(self):
        config.showControlPanelOnStartup = not config.showControlPanelOnStartup
        self.displayMessage(config.thisTranslation["message_restart"])

    def preferControlPanelForCommandLineEntryChanged(self):
        config.preferControlPanelForCommandLineEntry = not config.preferControlPanelForCommandLineEntry
        self.displayMessage(config.thisTranslation["message_restart"])

    def closeControlPanelAfterRunningCommandChanged(self):
        config.closeControlPanelAfterRunningCommand = not config.closeControlPanelAfterRunningCommand

    def restrictControlPanelWidthChanged(self):
        config.restrictControlPanelWidth = not config.restrictControlPanelWidth
        self.parent.reloadControlPanel(False)

    def regexCaseSensitiveChanged(self):
        config.regexCaseSensitive = not config.regexCaseSensitive

    def openStudyWindowContentOnNextTabChanged(self):
        config.openStudyWindowContentOnNextTab = not config.openStudyWindowContentOnNextTab
        self.newTabException = False

    def addFavouriteToMultiRefChanged(self):
        config.addFavouriteToMultiRef = not config.addFavouriteToMultiRef

    def addOHGBiToMorphologySearchChanged(self):
        config.addOHGBiToMorphologySearch = not config.addOHGBiToMorphologySearch

    def exportEmbeddedImagesChanged(self):
        config.exportEmbeddedImages = not config.exportEmbeddedImages

    def clickToOpenImageChanged(self):
        config.clickToOpenImage = not config.clickToOpenImage

    def openBibleNoteAfterEditorClosedChanged(self):
        config.openBibleNoteAfterEditorClosed = not config.openBibleNoteAfterEditorClosed

    def preferHtmlMenuChanged(self):
        config.preferHtmlMenu = not config.preferHtmlMenu

    def hideNoteEditorStyleToolbarChanged(self):
        config.hideNoteEditorStyleToolbar = not config.hideNoteEditorStyleToolbar

    def hideNoteEditorTextUtilityChanged(self):
        config.hideNoteEditorTextUtility = not config.hideNoteEditorTextUtility

    def populateTabsOnStartupChanged(self):
        config.populateTabsOnStartup = not config.populateTabsOnStartup

    def bookOnNewWindowChanged(self):
        config.bookOnNewWindow = not config.bookOnNewWindow

    def convertChapterVerseDotSeparatorChanged(self):
        config.convertChapterVerseDotSeparator = not config.convertChapterVerseDotSeparator

    def updateWithGitPullChanged(self):
        config.updateWithGitPull = not config.updateWithGitPull
        if config.updateWithGitPull and not os.path.isdir(".git"):
            config.updateWithGitPull = False

    def parseBookChapterWithoutSpaceChanged(self):
        config.parseBookChapterWithoutSpace = not config.parseBookChapterWithoutSpace

    def overwriteNoteFontChanged(self):
        config.overwriteNoteFont = not config.overwriteNoteFont

    def overwriteNoteFontSizeChanged(self):
        config.overwriteNoteFontSize = not config.overwriteNoteFontSize

    def overwriteBookFontChanged(self):
        config.overwriteBookFont = not config.overwriteBookFont

    def useWebbrowserChanged(self):
        config.useWebbrowser = not config.useWebbrowser

    def removeHighlightOnExitChanged(self):
        config.removeHighlightOnExit = not config.removeHighlightOnExit

    def overwriteBookFontSizeChanged(self):
        config.overwriteBookFontSize = not config.overwriteBookFontSize

    def alwaysDisplayStaticMapsChanged(self):
        config.alwaysDisplayStaticMaps = not config.alwaysDisplayStaticMaps

    def openBibleNoteAfterSaveChanged(self):
        config.openBibleNoteAfterSave = not config.openBibleNoteAfterSave

    def addBreakAfterTheFirstToolBarChanged(self):
        config.addBreakAfterTheFirstToolBar = not config.addBreakAfterTheFirstToolBar
        self.displayMessage(config.thisTranslation["message_restart"])

    def addBreakBeforeTheLastToolBarChanged(self):
        config.addBreakBeforeTheLastToolBar = not config.addBreakBeforeTheLastToolBar
        self.displayMessage(config.thisTranslation["message_restart"])

    def disableModulesUpdateCheckChanged(self):
        config.disableModulesUpdateCheck = not config.disableModulesUpdateCheck

    def forceGenerateHtmlChanged(self):
        config.forceGenerateHtml = not config.forceGenerateHtml

    def parserStandarisationChanged(self):
        if config.parserStandarisation == "YES":
            config.parserStandarisation = "NO"
        else:
            config.parserStandarisation = "YES"

    def linuxStartFullScreenChanged(self):
        config.linuxStartFullScreen = not config.linuxStartFullScreen
        self.displayMessage(config.thisTranslation["message_restart"])

    def espeakChanged(self):
        config.espeak = not config.espeak
        self.displayMessage(config.thisTranslation["message_restart"])

    def enableLoggingChanged(self):
        config.enableLogging = not config.enableLogging
        self.displayMessage(config.thisTranslation["message_restart"])

    def logCommandsChanged(self):
        config.logCommands = not config.logCommands

    def enableVerseHighlightingChanged(self):
        config.enableVerseHighlighting = not config.enableVerseHighlighting
        self.displayMessage(config.thisTranslation["message_restart"])

    def useFastVerseParsingChanged(self):
        config.useFastVerseParsing = not config.useFastVerseParsing

    def enableMacrosChanged(self):
        config.enableMacros = not config.enableMacros
        self.displayMessage(config.thisTranslation["message_restart"])

    def enablePluginsChanged(self):
        config.enablePlugins = not config.enablePlugins
        self.parent.setMenuLayout(config.menuLayout)

    def clearCommandEntryChanged(self):
        config.clearCommandEntry = not config.clearCommandEntry

    def qtMaterialChanged(self):
        if not config.qtMaterial:
            self.parent.enableQtMaterial(True)
        else:
            self.parent.enableQtMaterial(False)

    def enableGistChanged(self):
        if not config.enableGist and config.isPygithubInstalled:
            config.enableGist = True
            self.displayMessage(config.thisTranslation["message_restart"])
        elif config.enableGist:
            config.enableGist = not config.enableGist
            self.displayMessage(config.thisTranslation["message_restart"])
        else:
            self.displayMessage(config.thisTranslation["message_noSupport"])

    def hideBlankVerseCompareChanged(self):
        config.hideBlankVerseCompare = not config.hideBlankVerseCompare

    def enableMenuUnderlineChanged(self):
        config.enableMenuUnderline = not config.enableMenuUnderline
        if config.enableMenuUnderline:
            config.menuUnderline = "&"
        else:
            config.menuUnderline = ""
        self.parent.setMenuLayout(config.menuLayout)
