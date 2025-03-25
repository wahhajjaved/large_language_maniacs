#!/usr/bin/env python
# -*- encoding: utf-8 -*-

#=======================================================================
# Standard library imports
#=======================================================================
import re
from bisect import bisect

#=======================================================================
# Related third party imports
#=======================================================================
from PyQt4 import QtCore, QtGui

#=======================================================================
# Local application / Library specific imports
#=======================================================================
from prymatex import resources
from prymatex.core.settings import pmxConfigPorperty
from prymatex.core.plugin.editor import PMXBaseEditor
from prymatex.core import exceptions
from prymatex.support import PMXSnippet, PMXMacro, PMXCommand, PMXDragCommand, PMXSyntax, PMXPreferenceSettings
from prymatex.gui import utils
from prymatex.gui.codeeditor.sidebar import PMXSidebar
from prymatex.gui.codeeditor.processors import PMXCommandProcessor, PMXSnippetProcessor, PMXMacroProcessor
from prymatex.gui.codeeditor.modes import PMXMultiCursorEditorMode, PMXCompleterEditorMode, PMXSnippetEditorMode
from prymatex.gui.codeeditor.highlighter import PMXSyntaxHighlighter
from prymatex.gui.codeeditor.folding import PMXEditorFolding
from prymatex.gui.codeeditor.models import PMXSymbolListModel, PMXBookmarkListModel, PMXCompleterTableModel, PMXAlreadyTypedWords

from prymatex.utils.text import convert_functions
from prymatex.utils.i18n import ugettext as _

from prymatex.utils.decorator.helpers import printtime

class PMXCodeEditor(QtGui.QPlainTextEdit, PMXBaseEditor):
    #=======================================================================
    # Signals
    #=======================================================================
    syntaxChanged = QtCore.pyqtSignal(object)
    themeChanged = QtCore.pyqtSignal()
    modeChanged = QtCore.pyqtSignal()
    blocksRemoved = QtCore.pyqtSignal(QtGui.QTextBlock, int)
    blocksAdded = QtCore.pyqtSignal(QtGui.QTextBlock, int)

    #=======================================================================
    # Settings
    #=======================================================================
    SETTINGS_GROUP = 'CodeEditor'
    
    defaultSyntax = pmxConfigPorperty(default = "3130E4FA-B10E-11D9-9F75-000D93589AF6", tm_name = 'OakDefaultLanguage')
    tabStopSoft = pmxConfigPorperty(default = True)
    @pmxConfigPorperty(default = 4)
    def tabStopSize(self, size):
        self.setTabStopWidth(size * 9)
    
    @pmxConfigPorperty(default = QtGui.QFont("Monospace", 9))
    def font(self, font):
        font.setStyleStrategy(QtGui.QFont.PreferAntialias)
        self.document().setDefaultFont(font)
        self.sidebar.font = font
        self.setTabStopWidth(self.tabStopSize * 9)
    
    @pmxConfigPorperty(default = '766026CB-703D-4610-B070-8DE07D967C5F', tm_name = 'OakThemeManagerSelectedTheme')
    def theme(self, uuid):
        theme = self.application.supportManager.getTheme(uuid)

        firstTime = not self.syntaxHighlighter.hasTheme()
        self.syntaxHighlighter.setTheme(theme)
        self.colours = theme.settings
        
        #Set color for QPlainTextEdit
        appStyle = """QPlainTextEdit {background-color: %s;
        color: %s;
        selection-background-color: %s; }""" % (self.colours['background'].name(), self.colours['foreground'].name(), self.colours['selection'].name())
        self.setStyleSheet(appStyle)

        #Sidebar colours
        #TODO: que la sidebar lo tomo del editor
        self.sidebar.foreground = self.colours['foreground']
        self.sidebar.background = self.colours['gutter'] if 'gutter' in self.colours else self.colours['background']  
        
        self.updateLineNumberAreaWidth(0)
        self.highlightCurrent()
        if not firstTime:
            message = "<b>%s</b> theme set " % theme.name
            if theme.author is not None:
                message += "<i>(by %s)</i>" % theme.author
            self.showMessage(message)
        self.themeChanged.emit()
        
    #================================================================
    # Regular expresions
    #================================================================
    #TODO: Ver que pasa con [A-Za-z_]+ en lugar de [A-Za-z_]*
    RE_WORD = re.compile(r"[A-Za-z_]*")
    
    #================================================================
    # Selection types
    #================================================================
    SelectWord = QtGui.QTextCursor.WordUnderCursor #0
    SelectLine = QtGui.QTextCursor.LineUnderCursor #1
    SelectParagraph = QtGui.QTextCursor.BlockUnderCursor #2 este no es un paragraph pero no importa
    SelectAll = QtGui.QTextCursor.Document #3
    SelectEnclosingBrackets = 4
    SelectCurrentScope = 5
    
    #================================================================
    # Move types
    #================================================================
    MoveLineUp = QtGui.QTextCursor.Up
    MoveLineDown = QtGui.QTextCursor.Down
    MoveColumnLeft = QtGui.QTextCursor.Left
    MoveColumnRight = QtGui.QTextCursor.Right
    
    #================================================================
    # Convert types, los numeros son los indeces de convert_functions
    #================================================================
    ConvertToUppercase = 0
    ConvertToLowercase = 1
    ConvertToTitlecase = 2
    ConvertToOppositeCase = 3
    ConvertSpacesToTabs = 4
    ConvertTabsToSpaces = 5
    ConvertTranspose = 6

    #================================================================
    # Editor Flags
    #================================================================
    ShowTabsAndSpaces     = 1<<0
    ShowLineAndParagraphs = 1<<1
    ShowBookmarks         = 1<<2
    ShowLineNumbers       = 1<<3
    ShowFolding           = 1<<4
    WordWrap              = 1<<5
    
    @pmxConfigPorperty(default = ShowLineNumbers)
    def defaultFlags(self, flags):
        self.setFlags(flags)
                
    @property
    def tabKeyBehavior(self):
        return self.tabStopSoft and unicode(' ') * self.tabStopSize or unicode('\t')
    
    def __init__(self, parent = None):
        QtGui.QPlainTextEdit.__init__(self, parent)
        PMXBaseEditor.__init__(self)

        #Sidebar
        self.sidebar = PMXSidebar(self)

        #Models
        self.bookmarkListModel = PMXBookmarkListModel(self)
        self.symbolListModel = PMXSymbolListModel(self)
        self.alreadyTypedWords = PMXAlreadyTypedWords(self)
        
        #Folding
        self.folding = PMXEditorFolding(self)
        
        #Processors
        self.commandProcessor = PMXCommandProcessor(self)
        self.macroProcessor = PMXMacroProcessor(self)
        self.snippetProcessor = PMXSnippetProcessor(self)

        #Highlighter
        self.syntaxHighlighter = PMXSyntaxHighlighter(self)
        
        #Modes
        self.multiCursorMode = PMXMultiCursorEditorMode(self)
        self.completerMode = PMXCompleterEditorMode(self)
        self.snippetMode = PMXSnippetEditorMode(self)
        
        self.highlightWordTimer = QtCore.QTimer()
        self.currentHighlightWord = None
        self.extraCursorsSelections = []
        
        self.braces = []
        #Current braces for cursor position (leftBrace * rightBrace, oppositeLeftBrace, oppositeRightBrace) 
        # * the cursor is allways here>
        self._currentBraces = (None, None, None, None)
        
        #Block Count
        self.lastBlockCount = self.document().blockCount()
        self.setupActions()
        self.connectSignals()
        
        #Connect context menu
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showEditorContextMenu)
        
        #Basic setup
        #self.setCenterOnScroll(True)
            
    def initialize(self, mainWindow):
        PMXBaseEditor.initialize(self, mainWindow)
        #Load Default Syntax
        syntax = self.application.supportManager.getBundleItem(self.defaultSyntax)
        self.setSyntax(syntax)
        
    def updateIndent(self, block, userData, indent):
        self.logger.debug("Update Block Indent")
    
    def updateFolding(self, block, userData, foldingMark):
        self.logger.debug("Update Block Folding")
        if block.userData().foldingMark == None:
            self.folding.removeFoldingBlock(block)
        else:
            self.folding.addFoldingBlock(block)
        
    def updateSymbol(self, block, userData, symbol):
        self.logger.debug("Update Block Symbol")
        if block.userData().symbol is None:
            self.symbolListModel.removeSymbolBlock(block)
        else:
            self.symbolListModel.addSymbolBlock(block)
        
    def updateWords(self, block, userData, words):
        self.logger.debug("Update Words")
        oldWords = set(map(lambda (index, word): word, userData.words))
        newWords = set(map(lambda (index, word): word, words))
        #Quitar el blocke de las palabras anteriores
        self.alreadyTypedWords.removeWordsBlock(block, oldWords.difference(newWords))
        #Agregar las palabras nuevas
        self.alreadyTypedWords.addWordsBlock(block, newWords.difference(oldWords))
        userData.words = words
            
    #=======================================================================
    # Connect Signals
    #=======================================================================
    def connectSignals(self):
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.blockCountChanged.connect(self.on_blockCountChanged)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.on_cursorPositionChanged)
        self.modificationChanged.connect(self.on_modificationChanged)
        self.syntaxChanged.connect(self.showSyntaxMessage)
        
        self.actionCopyPath.triggered.connect(self.on_actionCopyPath_triggered)
        
    def setupActions(self):
        # Some actions
        self.actionCopyPath = QtGui.QAction(resources.getIcon("copy"), _("Copy path to clipboard"), self)
        
    def showSyntaxMessage(self, syntax):
        self.showMessage("Syntax changed to <b>%s</b>" % syntax.name)

    def on_modificationChanged(self, value):
        self.emit(QtCore.SIGNAL("tabStatusChanged()"))
    
    def on_blockCountChanged(self, newBlockCount):
        self.logger.debug("block Count changed")
        block = self.textCursor().block()
        if self.lastBlockCount > self.document().blockCount():
            self.blocksRemoved.emit(block, self.lastBlockCount - newBlockCount)
        else:
            self.blocksAdded.emit(block, newBlockCount - self.lastBlockCount)
        self.lastBlockCount = self.document().blockCount()
    
    def on_cursorPositionChanged(self):
        #El cursor se movio es hora de:
        self.setCurrentBraces()
        self.highlightCurrent()

    #=======================================================================
    # Base Editor Interface
    #=======================================================================
    @classmethod
    def acceptFile(cls, filePath, mimetype):
        return re.compile("text/.*").match(mimetype) is not None

    def open(self, filePath):
        """ Custom open for large files, use coroutines """
        self.application.fileManager.openFile(filePath)
        content = self.application.fileManager.readFile(filePath)
        self.setFilePath(filePath)
        chunksize = 512
        currentIndex = 0
        contentLength = len(content)
        while currentIndex <= contentLength:
            self.insertPlainText(content[currentIndex:currentIndex + chunksize])
            currentIndex += chunksize
            yield
        self.document().clearUndoRedoStacks()
        self.setModified(False)
        
    def close(self):
        QtGui.QPlainTextEdit.close(self)
        return PMXBaseEditor.close(self)

    def isModified(self):
        return self.document().isModified()
    
    def isEmpty(self):
        return self.document().isEmpty()
        
    def setModified(self, modified):
        self.document().setModified(modified)
        
    def setFilePath(self, filePath):
        extension = self.application.fileManager.extension(filePath)
        syntax = self.application.supportManager.findSyntaxByFileType(extension)
        if syntax is not None:
            self.setSyntax(syntax)
        PMXBaseEditor.setFilePath(self, filePath)
        
    def tabTitle(self):
        #Podemos marcar de otra forma cuando algo cambia :P
        return PMXBaseEditor.tabTitle(self)
    
    def fileFilters(self):
        if self.getSyntax() is not None:
            return [ "%s (%s)" % (self.getSyntax().bundle.name, " ".join(map(lambda ft: "*." + ft, self.getSyntax().fileTypes))) ]
        return PMXBaseEditor.fileFilters(self)
    
    def setCursorPosition(self, position):
        cursor = self.textCursor()
        blockPosition = self.document().findBlockByNumber(position[0]).position()
        cursor.setPosition(blockPosition + position[1])
        self.setTextCursor(cursor)

    #=======================================================================
    # Obteniendo datos del editor
    #=======================================================================
    def preferenceSettings(self, scope):
        return self.application.supportManager.getPreferenceSettings(scope, self.getSyntax().bundle)
        
    def getPreference(self, scope):
        """Deprecated"""
        return self.application.supportManager.getPreferenceSettings(scope, self.getSyntax().bundle)

    def wordUnderCursor(self):
        cursor = self.textCursor()
        cursor.select(QtGui.QTextCursor.WordUnderCursor)
        return cursor.selectedText(), cursor.selectionStart(), cursor.selectionEnd()

    def getCurrentScope(self):
        """Deprecated"""
        cursor = self.textCursor()
        return cursor.block().userData().getScopeAtPosition(cursor.columnNumber())

    def scope(self, cursor):
        return cursor.block().userData().getScopeAtPosition(cursor.columnNumber())

    def currentScope(self):
        return self.scope(self.textCursor())

    def currentWord(self, *largs, **kwargs):
        return self.getCurrentWord(*largs, **kwargs)
        
    def getCurrentWord(self, pat = RE_WORD, direction = "both"):
        cursor = self.textCursor()
        line = cursor.block().text()
        position = cursor.position()
        columnNumber = cursor.columnNumber()
        #Get text before and after the cursor position.
        first_part, last_part = line[:columnNumber][::-1], line[columnNumber:]
        #Try left word
        lword = rword = ""
        m = self.RE_WORD.match(first_part)
        if m and direction in ("left", "both"):
            lword = m.group(0)[::-1]
        #Try right word
        m = self.RE_WORD.match(last_part)
        if m and direction in ("right", "both"):
            rword = m.group(0)
        
        if lword or rword: 
            return lword + rword, position - len(lword), position + len(rword)
        
        lword = rword = ""
        #Search left word
        for i in range(len(first_part)):
            lword += first_part[i]
            m = self.RE_WORD.search(first_part[i + 1:], i )
            if m.group(0):
                lword += m.group(0)
                break
        lword = lword[::-1]
        #Search right word
        for i in range(len(last_part)):
            rword += last_part[i]
            m = self.RE_WORD.search(last_part[i:], i )
            if m.group(0):
                rword += m.group(0)
                break
        lword = lword.lstrip()
        rword = rword.rstrip()
        return lword + rword, position - len(lword), position + len(rword)
    
    def getSelectionBlockStartEnd(self, cursor = None):
        cursor = cursor or self.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        if start > end:
            return self.document().findBlock(end), self.document().findBlock(start)
        else:
            return self.document().findBlock(start), self.document().findBlock(end)

    # Flags
    def getFlags(self):
        flags = 0
        options = self.document().defaultTextOption()
        if options.flags() & QtGui.QTextOption.ShowTabsAndSpaces:
            flags |= self.ShowTabsAndSpaces
        if options.flags() & QtGui.QTextOption.ShowLineAndParagraphSeparators:
            flags |= self.ShowLineAndParagraphs
        if self.sidebar.showBookmarks:
            flags |= self.ShowBookmarks
        if self.sidebar.showLineNumbers:
            flags |= self.ShowLineNumbers
        if self.sidebar.showFolding:
            flags |= self.ShowFolding
        if options.wrapMode() & QtGui.QTextOption.WordWrap:
            flags |= self.WordWrap
        return flags
        
    def setFlags(self, flags):
        options = self.document().defaultTextOption()
        oFlags = options.flags()
        if flags & self.ShowTabsAndSpaces:
            oFlags |= QtGui.QTextOption.ShowTabsAndSpaces
        else:
            oFlags &= ~QtGui.QTextOption.ShowTabsAndSpaces
        if flags & self.ShowLineAndParagraphs:
            oFlags |= QtGui.QTextOption.ShowLineAndParagraphSeparators
        else:
            oFlags &= ~QtGui.QTextOption.ShowLineAndParagraphSeparators
        if flags & self.WordWrap:
            options.setWrapMode(QtGui.QTextOption.WordWrap)
        else:
            options.setWrapMode(QtGui.QTextOption.NoWrap)
        options.setFlags(oFlags)
        self.document().setDefaultTextOption(options)
        self.sidebar.showBookmarks = bool(flags & self.ShowBookmarks)
        self.sidebar.showLineNumbers = bool(flags & self.ShowLineNumbers)
        self.sidebar.showFolding = bool(flags & self.ShowFolding)
        self.updateLineNumberAreaWidth(0)
        #self.setCenterOnScroll(True)
        #self.viewport().repaint(self.viewport().visibleRegion())
    
    # Syntax
    def getSyntax(self):
        return self.syntaxHighlighter.syntax
        
    def setSyntax(self, syntax):
        if self.syntaxHighlighter.syntax != syntax:
            self.syntaxHighlighter.setSyntax(syntax)
            self.folding.indentSensitive = syntax.indentSensitive
            self.setBraces(syntax.scopeName)
            self.syntaxChanged.emit(syntax)

    # Move text
    def moveText(self, moveType):
        #Solo si tiene seleccion puede mover derecha y izquierda
        cursor = self.textCursor()
        cursor.beginEditBlock()
        if cursor.hasSelection():
            if (moveType == QtGui.QTextCursor.Left and cursor.selectionStart() == 0) or (moveType == QtGui.QTextCursor.Right and cursor.selectionEnd() == self.document().characterCount()):
                return
            openRight = cursor.position() == cursor.selectionEnd()
            text = cursor.selectedText()
            cursor.removeSelectedText()
            cursor.movePosition(moveType)
            start = cursor.position()
            cursor.insertText(text)
            end = cursor.position()
            if openRight:
                cursor.setPosition(start)
                cursor.setPosition(end, QtGui.QTextCursor.KeepAnchor)
            else:
                cursor.setPosition(end)
                cursor.setPosition(start, QtGui.QTextCursor.KeepAnchor)
        elif moveType in [QtGui.QTextCursor.Up, QtGui.QTextCursor.Down]:
            if (moveType == QtGui.QTextCursor.Up and cursor.block() == cursor.document().firstBlock()) or (moveType == QtGui.QTextCursor.Down and cursor.block() == cursor.document().lastBlock()):
                return
            column = cursor.columnNumber()
            cursor.select(QtGui.QTextCursor.LineUnderCursor)
            text1 = cursor.selectedText()
            cursor2 = QtGui.QTextCursor(cursor)
            otherBlock = cursor.block().next() if moveType == QtGui.QTextCursor.Down else cursor.block().previous()
            cursor2.setPosition(otherBlock.position())
            cursor2.select(QtGui.QTextCursor.LineUnderCursor)
            text2 = cursor2.selectedText()
            cursor.insertText(text2)
            cursor2.insertText(text1)
            cursor.setPosition(otherBlock.position() + column)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
    
    # Convert Text
    def convertText(self, convertType):
        cursor = self.textCursor()
        convertFunction = convert_functions[convertType]
        if convertType == self.ConvertSpacesToTabs:
            self.replaceSpacesForTabs()
        elif convertType == self.ConvertTabsToSpaces:
            self.replaceTabsForSpaces()
        else:
            if not cursor.hasSelection():
                word, start, end = self.getCurrentWord()
                position = cursor.position()
                cursor.setPosition(start)
                cursor.setPosition(end, QtGui.QTextCursor.KeepAnchor)
                cursor.insertText(convertFunction(word))
                cursor.setPosition(position)
            else:
                openRight = cursor.position() == cursor.selectionEnd()
                start, end = cursor.selectionStart(), cursor.selectionEnd()
                cursor.insertText(convertFunction(cursor.selectedText()))
                if openRight:
                    cursor.setPosition(start)
                    cursor.setPosition(end, QtGui.QTextCursor.KeepAnchor)
                else:
                    cursor.setPosition(end)
                    cursor.setPosition(start, QtGui.QTextCursor.KeepAnchor)
            self.setTextCursor(cursor)
        
    #=======================================================================
    # Espacio para la sidebar
    #=======================================================================
    def lineNumberAreaWidth(self):
        font_metrics = QtGui.QFontMetrics(self.document().defaultFont())
        area = self.sidebar.padding
        if self.sidebar.showLineNumbers:
            area += font_metrics.width(str(self.blockCount()))
        if self.sidebar.showBookmarks:
            area += self.sidebar.bookmarkArea
        if self.sidebar.showFolding:
            area += self.sidebar.foldArea
        return area
        
    def updateLineNumberAreaWidth(self, newBlockCount):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)
    
    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.sidebar.scroll(0, dy)
        else:
            self.sidebar.update(0, rect.y(), self.sidebar.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)
        
    #=======================================================================
    # Braces
    #=======================================================================
    def setBraces(self, scope):
        settings = self.preferenceSettings(scope)
        self.braces = filter(lambda pair: pair[0] != pair[1], settings.smartTypingPairs)
        
    def setCurrentBraces(self, cursor = None):
        cursor = QtGui.QTextCursor(cursor) if cursor is not None else QtGui.QTextCursor(self.textCursor())
        cursor.clearSelection()
        openBraces = map(lambda pair: pair[0], self.braces)
        closeBraces = map(lambda pair: pair[1], self.braces)
        
        leftChar = cursor.document().characterAt(cursor.position() - 1)
        rightChar = cursor.document().characterAt(cursor.position())
        
        self._currentBraces = (None, None, None, None)

        if leftChar in openBraces or rightChar in openBraces:
            if leftChar in openBraces:
                leftCursor = QtGui.QTextCursor(cursor)
                leftCursor.movePosition(QtGui.QTextCursor.PreviousCharacter, QtGui.QTextCursor.KeepAnchor)
                index = openBraces.index(leftChar)
                self._currentBraces = (leftCursor, None, self.findTypingPair(leftChar, closeBraces[index], leftCursor), None)
            if rightChar in openBraces:
                rightCursor = QtGui.QTextCursor(cursor)
                rightCursor.movePosition(QtGui.QTextCursor.NextCharacter, QtGui.QTextCursor.KeepAnchor)
                index = openBraces.index(rightChar)
                self._currentBraces = (self._currentBraces[0], rightCursor, self._currentBraces[2], self.findTypingPair(rightChar, closeBraces[index], rightCursor))
        if leftChar in closeBraces or rightChar in closeBraces:
            if leftChar in closeBraces:
                leftCursor = QtGui.QTextCursor(cursor)
                leftCursor.movePosition(QtGui.QTextCursor.PreviousCharacter, QtGui.QTextCursor.KeepAnchor)
                self._currentBraces = (leftCursor, None, self.findTypingPair(leftChar, openBraces[closeBraces.index(leftChar)], leftCursor, True), None)
            if rightChar in closeBraces:
                rightCursor = QtGui.QTextCursor(cursor)
                rightCursor.movePosition(QtGui.QTextCursor.NextCharacter, QtGui.QTextCursor.KeepAnchor)
                self._currentBraces = (self._currentBraces[0], rightCursor, self._currentBraces[2], self.findTypingPair(rightChar, openBraces[closeBraces.index(rightChar)], rightCursor, True))

    def getBracesPairs(self, cursor = None, forward = False):
        """ Retorna el otro cursor correspondiente al cursor (brace) pasado o actual del editor, puede retornar None en caso de no estar cerrado el brace"""
        cursor = QtGui.QTextCursor(cursor or self.textCursor())
        if not cursor.hasSelection():
            #poner seleccion en funcion del backward
            cursor.movePosition(forward and QtGui.QTextCursor.NextCharacter or QtGui.QTextCursor.PreviousCharacter, QtGui.QTextCursor.KeepAnchor)
        #Find selected
        for index in [0, 1]:
            if self._currentBraces[index] is not None and cursor.selectionStart() == self._currentBraces[index].selectionStart() and cursor.selectionEnd() == self._currentBraces[index].selectionEnd():
                opposite = QtGui.QTextCursor(self._currentBraces[index + 2]) if self._currentBraces[index + 2] is not None else None
                return (cursor, opposite)
        return (None, None)

    def beforeBrace(self, cursor):
        return self._currentBraces[1] is not None and self._currentBraces[1].position() - 1 == cursor.position()
    
    def afterBrace(self, cursor):
        return self._currentBraces[0] is not None and self._currentBraces[0].position() + 1 == cursor.position()
        
    def besideBrace(self, cursor):
        return self.beforeBrace(cursor) or self.afterBrace(cursor)

    def surroundBraces(self, cursor):
        #TODO: Esto esta mal
        return self.beforeBrace(cursor) and self.afterBrace(cursor)
        
    #=======================================================================
    # Highlight Editor
    #=======================================================================
    def highlightCurrent(self):
        #Clean current extra selection
        self.setExtraSelections([])
        if self.multiCursorMode.isActive():
            self.multiCursorMode.highlightCurrentLines()
        else:
            self.highlightCurrentLine()
            self.highlightCurrentBrace()
            self.highlightCurrentSelections()
            self.highlightCurrentWord()

    def highlightCurrentWord(self):
        return
        #TODO: Mejorar esto porque sino cuando se carga un archivo le manda como loco
        def highlightWord():
            if self.currentHighlightWord == self.getWordUnderCursor()[0]:
                self.extraCursorsSelections = self.findAll(self.currentHighlightWord, QtGui.QTextDocument.FindWholeWords | QtGui.QTextDocument.FindCaseSensitively)
                self.highlightCurrentSelections()
            self.highlightWordTimer.stop()
        if self.currentHighlightWord != self.getWordUnderCursor()[0]:
            if self.highlightWordTimer.isActive():
                self.highlightWordTimer.stop()
            self.currentHighlightWord = self.getWordUnderCursor()[0]
            self.highlightWordTimer.timeout.connect(highlightWord)
            self.highlightWordTimer.start(2000)
        
    def highlightCurrentSelections(self):
        extraSelections = self.extraSelections()
        for cursor in self.extraCursorsSelections:
            selection = QtGui.QTextEdit.ExtraSelection()
            color = QtGui.QColor(self.colours['selection'])
            color.setAlpha(100)
            selection.format.setBackground(color)
            selection.cursor = cursor
            extraSelections.append(selection)
        self.setExtraSelections(extraSelections)
        
    def highlightCurrentBrace(self):
        selectedBraces = []
        for cursor in self._currentBraces:
            if cursor is not None:
                selection = QtGui.QTextEdit.ExtraSelection()
                selection.format.setForeground(QtGui.QBrush(self.colours['caret']))
                selection.format.setFontUnderline(True)
                selection.format.setUnderlineColor(self.colours['foreground']) 
                selection.format.setBackground(QtGui.QBrush(QtCore.Qt.transparent))
                selection.cursor = cursor
                selectedBraces.append(selection)
        if selectedBraces:
            self.setExtraSelections(self.extraSelections() + selectedBraces)

    def highlightCurrentLine(self):
        extraSelections = self.extraSelections()
        selection = QtGui.QTextEdit.ExtraSelection()
        selection.format.setBackground(self.colours['lineHighlight'])
        selection.format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        extraSelections.append(selection)
        self.setExtraSelections(extraSelections)

    def select(self, selection):
        cursor = self.textCursor()
        if selection in [self.SelectLine, self.SelectParagraph, self.SelectAll]:
            #Handle by editor
            cursor.select(selection)
        elif selection == self.SelectWord:
            word, start, end = self.getCurrentWord()
            cursor.setPosition(start)
            cursor.setPosition(end, QtGui.QTextCursor.KeepAnchor)
        elif selection == self.SelectEnclosingBrackets:
            flags = QtGui.QTextDocument.FindFlags()
            flags |= QtGui.QTextDocument.FindBackward
            foundCursors = map(lambda (openBrace, closeBrace): (self.document().find(openBrace, cursor.selectionStart(), flags), closeBrace), self.braces)
            openCursor = reduce(lambda c1, c2: (not c1[0].isNull() and c1[0].selectionEnd() > c2[0].selectionEnd()) and c1 or c2, foundCursors)
            if not openCursor[0].isNull():
                closeCursor = self.findTypingPair(openCursor[0].selectedText(), openCursor[1], openCursor[0])
                if openCursor[0].selectionEnd() <= cursor.selectionStart() <= closeCursor.selectionStart():
                    cursor.setPosition(openCursor[0].selectionEnd())
                    cursor.setPosition(closeCursor.selectionStart(), QtGui.QTextCursor.KeepAnchor)
        elif selection == self.SelectCurrentScope:
            block = cursor.block()
            beginPosition = block.position()
            range = block.userData().scopeRange(cursor.columnNumber())
            if range is not None:
                scope, start, end = range
                cursor.setPosition(beginPosition + start)
                cursor.setPosition(beginPosition + end, QtGui.QTextCursor.KeepAnchor)
        self.setTextCursor(cursor)

    #=======================================================================
    # QPlainTextEdit Events
    #=======================================================================
    def resizeEvent(self, event):
        QtGui.QPlainTextEdit.resizeEvent(self, event)
        cr = self.contentsRect()
        self.sidebar.setGeometry(QtCore.QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))
        self.updateOverlays()
    
    def paintEvent(self, event):
        #QtGui.QPlainTextEdit.paintEvent(self, event)
        QtGui.QPlainTextEdit.paintEvent(self, event)
        page_bottom = self.viewport().height()
        font_metrics = QtGui.QFontMetrics(self.document().defaultFont())

        painter = QtGui.QPainter(self.viewport())
        
        block = self.firstVisibleBlock()
        viewport_offset = self.contentOffset()
        line_count = block.blockNumber()
        while block.isValid():
            line_count += 1
            # The top left position of the block in the document
            position = self.blockBoundingGeometry(block).topLeft() + viewport_offset
            # Check if the position of the block is out side of the visible area
            if position.y() > page_bottom:
                break

            user_data = block.userData()
            if block.isVisible() and self.folding.isStart(self.folding.getFoldingMark(block)) and user_data.folded:
                painter.drawPixmap(font_metrics.width(block.text()) + 10,
                    round(position.y()) + font_metrics.ascent() + font_metrics.descent() - resources.getImage("foldingellipsis").height(),
                    resources.getImage("foldingellipsis"))
            
            block = block.next()
        if self.multiCursorMode.isActive():
            for cursor in self.multiCursorMode.cursors:
                rec = self.cursorRect(cursor)
                cursor = QtCore.QLine(rec.x(), rec.y(), rec.x(), rec.y() + font_metrics.ascent() + font_metrics.descent())
                painter.setPen(QtGui.QPen(self.colours['caret']))
                painter.drawLine(cursor)
        if self.multiCursorMode.isDragCursor:
            pen = QtGui.QPen(self.colours['caret'])
            pen.setWidth(2)
            painter.setPen(pen)
            color = QtGui.QColor(self.colours['selection'])
            color.setAlpha(128)
            painter.setBrush(QtGui.QBrush(color))
            painter.setOpacity(0.2)
            painter.drawRect(self.multiCursorMode.getDragCursorRect())
        painter.end()

    #=======================================================================
    # Mouse Events
    #=======================================================================
    def wheelEvent(self, event):
        if event.modifiers() == QtCore.Qt.ControlModifier:
            if event.delta() == 120:
                self.zoomIn()
            elif event.delta() == -120:
                self.zoomOut()
            event.ignore()
        else:
            QtGui.QPlainTextEdit.wheelEvent(self, event)

    def mousePressEvent(self, event):
        if event.modifiers() == QtCore.Qt.ControlModifier:
            self.application.setOverrideCursor(QtGui.QCursor(QtCore.Qt.ArrowCursor))
            self.multiCursorMode.mousePressPoint(event.pos())
        else:
            QtGui.QPlainTextEdit.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        if event.modifiers() == QtCore.Qt.ControlModifier and self.multiCursorMode.isActive():
            #En este modo no hago el cursor visible
            self.multiCursorMode.mouseMovePoint(event.pos())
            self.viewport().repaint(self.viewport().visibleRegion())
        else:
            self.ensureCursorVisible()
            QtGui.QPlainTextEdit.mouseReleaseEvent(self, event)
 
    def mouseReleaseEvent(self, event):
        if event.modifiers() == QtCore.Qt.ControlModifier and self.multiCursorMode.isActive():
            self.multiCursorMode.mouseReleasePoint(event.pos())
            self.application.restoreOverrideCursor()
            self.viewport().repaint(self.viewport().visibleRegion())
        else:
            QtGui.QPlainTextEdit.mouseReleaseEvent(self, event)

    #=======================================================================
    # Keyboard Events
    #=======================================================================
    #@printtime
    def keyPressEvent(self, event):
        """
        This method is called whenever a key is pressed. The key code is stored in event.key()
        http://manual.macromates.com/en/working_with_text
        """
        
        #Primero ver si tengo un modo activo,
        for mode in [ self.snippetMode, self.multiCursorMode, self.completerMode ]:
            if mode.isActive():
                return mode.keyPressEvent(event)
        
        #No tengo modo activo, intento con los helpers
        #Obtener key, scope y cursor
        scope = self.getCurrentScope()
        cursor = self.textCursor()
        
        for helper in self.findHelpers(event.key()):
            #Buscar Entre los helpers
            if helper.accept(self, event, cursor, scope):
                #pasarle el evento
                return helper.execute(self, event, cursor, scope)
        
        #No tengo helper paso el evento a la base
        QtGui.QPlainTextEdit.keyPressEvent(self, event)
        
        self.emit(QtCore.SIGNAL("keyPressEvent(QEvent)"), event)

    #==========================================================================
    # Insert API
    #==========================================================================
    def insertNewLine(self, cursor = None):
        cursor = cursor or self.textCursor()
        block = cursor.block()
        settings = self.preferenceSettings(self.scope(cursor))
        indentMarks = settings.indent(block.text()[:cursor.columnNumber()])
        if PMXPreferenceSettings.INDENT_INCREASE in indentMarks:
            self.logger.debug("Increase indent")
            indent = block.userData().indent + self.tabKeyBehavior
        elif PMXPreferenceSettings.INDENT_NEXTLINE in indentMarks:
            #TODO: Creo que este no es el correcto
            self.logger.debug("Increase next line indent")
            indent = block.userData().indent + self.tabKeyBehavior
        elif PMXPreferenceSettings.UNINDENT in indentMarks:
            self.logger.debug("Unindent")
            indent = ""
        elif PMXPreferenceSettings.INDENT_DECREASE in indentMarks:
            indent = block.userData().indent[:len(self.tabKeyBehavior)]
        else:
            self.logger.debug("Preserve indent")
            indent = block.userData().indent
        cursor.insertText("\n%s" % indent)

    #==========================================================================
    # Bundle Items
    #==========================================================================
    def insertBundleItem(self, item, **processorSettings):
        """Inserta un bundle item"""
        if item.TYPE == PMXSnippet.TYPE:
            self.snippetProcessor.configure(processorSettings)
            self.textCursor().beginEditBlock()
            item.execute(self.snippetProcessor)
            self.textCursor().endEditBlock()
        elif item.TYPE == PMXCommand.TYPE or item.TYPE == PMXDragCommand.TYPE:
            self.commandProcessor.configure(processorSettings)
            self.textCursor().beginEditBlock()
            item.execute(self.commandProcessor)
            self.textCursor().endEditBlock()
        elif item.TYPE == PMXMacro.TYPE:
            self.macroProcessor.configure(processorSettings)
            self.textCursor().beginEditBlock()
            item.execute(self.macroProcessor)
            self.textCursor().endEditBlock()
        elif item.TYPE == PMXSyntax.TYPE:
            self.setSyntax(item)

    def selectBundleItem(self, items, tabTriggered = False):
        #Tengo mas de uno que hago?, muestro un menu
        syntax = any(map(lambda item: item.TYPE == 'syntax', items))
        options = []
        for index, item in enumerate(items):
            options.append({ "title": item.buildMenuTextEntry(False), "image": item.TYPE })
            
        def insertBundleItem(index):
            self.insertBundleItem(items[index], tabTriggered = tabTriggered)
        
        self.showFlatPopupMenu(options, insertBundleItem, cursorPosition = not syntax)
    
    def executeCommand(self, command = None, input = "none", output = "insertText"):
        if command is None:
            command = self.textCursor().selectedText() if self.textCursor().hasSelection() else self.textCursor().block().text()
        commandHash = {    'command': command, 
                       'name': command,
                      'input': input,
                     'output': output }
        command = PMXCommand(self.application.supportManager.uuidgen(), hash = commandHash)
        command.bundle = self.application.supportManager.getDefaultBundle()
        self.insertBundleItem(command)
    
    def buildEnvironment(self, env = {}):
        """ http://manual.macromates.com/en/environment_variables.html """
        cursor = self.textCursor()
        block = cursor.block()
        line = block.text()
        scope = self.getCurrentScope()
        preferences = self.getPreference(scope)
        current_word, start, end = self.getCurrentWord()
        #Combine base env from params and editor env
        env.update({
                'TM_CURRENT_LINE': line,
                'TM_LINE_INDEX': cursor.columnNumber(), 
                'TM_LINE_NUMBER': block.blockNumber() + 1,
                'TM_COLUMN_NUMBER': cursor.columnNumber() + 1, 
                'TM_SCOPE': scope,
                'TM_MODE': self.getSyntax().name,
                'TM_SOFT_TABS': self.tabStopSoft and unicode('YES') or unicode('NO'),
                'TM_TAB_SIZE': self.tabStopSize,
                'TM_NESTEDLEVEL': self.folding.getNestedLevel(block)
        })

        if current_word:
            env['TM_CURRENT_WORD'] = current_word
        if self.filePath is not None:
            env['TM_FILEPATH'] = self.filePath
            env['TM_FILENAME'] = self.application.fileManager.basename(self.filePath)
            env['TM_DIRECTORY'] = self.application.fileManager.dirname(self.filePath)
        if self.project is not None:
            env.update(self.project.buildEnvironment())
        if cursor.hasSelection():
            env['TM_SELECTED_TEXT'] = utils.replaceLineBreaks(cursor.selectedText())
            start, end = self.getSelectionBlockStartEnd()
            env['TM_INPUT_START_COLUMN'] = cursor.selectionStart() - start.position() + 1
            env['TM_INPUT_START_LINE'] = start.blockNumber() + 1
            env['TM_INPUT_START_LINE_INDEX'] = cursor.selectionStart() - start.position()
            
        env.update(preferences.shellVariables)
        return env

    #==========================================================================
    # Completer
    #==========================================================================
    def showCompleter(self, suggestions, alreadyTyped = "", caseInsensitive = True):
        case = QtCore.Qt.CaseInsensitive if caseInsensitive else QtCore.Qt.CaseSensitive
        self.completerMode.setCaseSensitivity(case)
        
        self.completerMode.setStartCursorPosition(self.textCursor().position() - len(alreadyTyped))
        self.completerMode.setCompletionPrefix(alreadyTyped)
        self.completerMode.setModel(PMXCompleterTableModel(suggestions, self))
        self.completerMode.complete(self.cursorRect())
    
    def completionSuggestions(self, cursor = None, scope = None):
        cursor = cursor or self.textCursor()
        scope = scope or self.scope(cursor)
        currentWord, start, end = self.currentWord()
        alreadyTyped = currentWord[:cursor.position() - start]

        settings = self.preferenceSettings(scope)
        disableDefaultCompletion = settings.disableDefaultCompletion
        if disableDefaultCompletion:
            print "no autocompletar"
        
        #An array of additional candidates when cycling through completion candidates from the current document.
        completions = settings.completions[:]

        #A shell command (string) which should return a list of candidates to complete the current word (obtained via the TM_CURRENT_WORD variable).
        completionCommand = settings.completionCommand
        if completionCommand:
            print "comando", completionCommand

        #A tab tigger completion
        completions += self.application.supportManager.getAllTabTiggerItemsByScope(scope)
        typedWords = self.alreadyTypedWords.typedWords()
        if alreadyTyped in typedWords:
            typedWords.remove(alreadyTyped)

        completions += typedWords
        
        return completions, alreadyTyped

    #==========================================================================
    # Folding
    #==========================================================================
    def codeFoldingFold(self, block):
        self._fold(block)
        self.update()
        self.sidebar.update()
    
    def codeFoldingUnfold(self, block):
        self._unfold(block)
        self.update()
        self.sidebar.update()
        
    def _fold(self, block):
        milestone = block
        if self.folding.isStart(self.folding.getFoldingMark(milestone)):
            startBlock = milestone.next()
            endBlock = self.folding.findBlockFoldClose(milestone)
            if endBlock is None:
                return
        else:
            endBlock = milestone
            milestone = self.folding.findBlockFoldOpen(endBlock)
            if milestone is None:
                return
            startBlock = milestone.next()
        block = startBlock
        while True:
            userData = block.userData()
            userData.foldedLevel += 1
            block.setVisible(userData.foldedLevel == 0)
            if block == endBlock:
                break
            block = block.next()
        
        milestone.userData().folded = True
        self.document().markContentsDirty(startBlock.position(), endBlock.position())

    def _unfold(self, block):
        milestone = block
        startBlock = milestone.next()
        endBlock = self.folding.findBlockFoldClose(milestone)
        if endBlock == None:
            return
        
        block = startBlock
        while True:
            userData = block.userData()
            userData.foldedLevel -= 1
            block.setVisible(userData.foldedLevel == 0)
            if block == endBlock:
                break
            block = block.next()

        milestone.userData().folded = False
        self.document().markContentsDirty(startBlock.position(), endBlock.position())

    #==========================================================================
    # Find and Replace
    #==========================================================================    
    def findTypingPair(self, b1, b2, cursor, backward = False):
        """
        Busca b2 asumiendo que b1 es su antitesis de ese modo controla el balanceo.
        b1 antitesis de b2
        b2 texto a buscar
        cursor representando la posicion a partir de la cual se busca
        backward buscar para atras
        Si b1 es igual a b2 no se controla el balanceo y se retorna la primera ocurrencia que se encuentre 
        """
        flags = QtGui.QTextDocument.FindFlags()
        if backward:
            flags |= QtGui.QTextDocument.FindBackward
        if cursor.hasSelection():
            startPosition = cursor.selectionEnd() if b1 == b2 or backward else cursor.selectionStart() 
        else:
            startPosition = cursor.position()
        c1 = self.document().find(b1, startPosition, flags)
        c2 = self.document().find(b2, startPosition, flags)
        if backward:
            while c1 > c2:
                c1 = self.document().find(b1, c1.selectionStart(), flags)
                if c1 > c2:
                    c2 = self.document().find(b2, c2.selectionStart(), flags)
        else:
            while not c1.isNull() and c1.position() != -1 and c1 < c2:
                c1 = self.document().find(b1, c1.selectionEnd(), flags)
                if c1.isNull():
                    break
                if c1 < c2:
                    c2 = self.document().find(b2, c2.selectionEnd(), flags)
        if not c2.isNull():
            return c2

    def findMatchCursor(self, match, flags, findNext = False, cursor = None, cyclicFind = True):
        cursor = cursor or self.textCursor()
        if not findNext and cursor.hasSelection():
            cursor.setPosition(cursor.selectionStart())
        cursor = self.document().find(match, cursor, flags)
        if cursor.isNull() and cyclicFind:
            cursor = self.textCursor()
            if flags & QtGui.QTextDocument.FindBackward:
                cursor.movePosition(QtGui.QTextCursor.End)
            else:
                cursor.movePosition(QtGui.QTextCursor.Start)
            cursor = self.document().find(match, cursor, flags)
        if not cursor.isNull():
            return cursor

    def findMatch(self, match, flags, findNext = False):
        cursor = self.findMatchCursor(match, flags, findNext)
        if cursor is not None:
            self.setTextCursor(cursor)
            return True
        return False
    
    def findAll(self, match, flags):
        cursors = []
        cursor = self.textCursor()
        cursor.movePosition(QtGui.QTextCursor.Start)
        cursor = self.findMatchCursor(match, flags, cursor = cursor, cyclicFind = False)
        while cursor is not None:
            cursors.append(cursor)
            cursor = QtGui.QTextCursor(cursor)
            cursor.setPosition(cursor.selectionEnd())
            cursor = self.findMatchCursor(match, flags, cursor = cursor, cyclicFind = False)
        return cursors
            
    def replaceMatch(self, match, text, flags, all = False):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        replaced = 0
        while True:
            findCursor = self.findMatchCursor(match, flags)
            if not findCursor: break
            if isinstance(match, QtCore.QRegExp):
                findCursor.insertText(re.sub(match.pattern(), text, cursor.selectedText()))
            else:
                findCursor.insertText(text)
            replaced += 1
            if not all: break
        cursor.endEditBlock()
        return replaced
    
    def replaceTabsForSpaces(self):
        match = QtCore.QRegExp("\t")
        self.replaceMatch(match, " " * self.tabStopSize, QtGui.QTextDocument.FindFlags(), True)
        
    def replaceSpacesForTabs(self):
        match = QtCore.QRegExp(" " * self.tabStopSize)
        self.replaceMatch(match, "\t", QtGui.QTextDocument.FindFlags(), True)
        
    #==========================================================================
    # Bookmarks and gotos
    #==========================================================================    
    def toggleBookmark(self, block = None):
        block = block or self.textCursor().block()
        self.bookmarkListModel.toggleBookmark(block)
        self.sidebar.update()
    
    def removeAllBookmarks(self):
        self.bookmarkListModel.removeAllBookmarks()
        self.sidebar.update()
    
    def bookmarkNext(self, block = None):
        block = block or self.textCursor().block()
        block = self.bookmarkListModel.nextBookmark(block)
        if block is not None:
            self.goToBlock(block)

    def bookmarkPrevious(self, block = None):
        block = block or self.textCursor().block()
        block = self.bookmarkListModel.previousBookmark(block)
        if block is not None:
            self.goToBlock(block)

    def goToBlock(self, block):
        cursor = self.textCursor()
        cursor.setPosition(block.position())
        self.setTextCursor(cursor)    
        self.centerCursor()

    def goToLine(self, lineNumber):
        cursor = self.textCursor()
        cursor.setPosition(self.document().findBlockByNumber(lineNumber - 1).position())
        self.setTextCursor(cursor)
        self.centerCursor()
    
    def goToColumn(self, columnNumber):
        cursor = self.textCursor()
        cursor.setPosition(cursor.block().position() + columnNumber)
        self.setTextCursor(cursor)
    
    #===========================================================================
    # Zoom
    #===========================================================================
    FONT_MAX_SIZE = 32
    FONT_MIN_SIZE = 6
    def zoomIn(self):
        font = self.font
        size = self.font.pointSize()
        if size < self.FONT_MAX_SIZE:
            size += 1
            font.setPointSize(size)
        self.font = font

    def zoomOut(self):
        font = self.font
        size = font.pointSize()
        if size > self.FONT_MIN_SIZE:
            size -= 1
            font.setPointSize(size)
        self.font = font

    #===========================================================================
    # Text Indentation
    #===========================================================================
    def findPreviousNoBlankBlock(self, block):
        """ Return previous no blank indent block """
        block = block.previous()
        while block.isValid() and block.text().strip() == "":
            block = block.previous()
        if block.isValid():
            return block
        
    def findPreviousEqualIndentBlock(self, block, indent = None):
        """ Return previous equal indent block """
        indent = indent if indent != None else block.userData().indent
        block = self.findPreviousNoBlankBlock(block)
        while block is not None and block.userData().indent > indent:
            block = self.findPreviousNoBlankBlock(block)
        if block is not None and block.userData().indent == indent:
            return block
    
    def findPreviousMoreIndentBlock(self, block, indent = None):
        """ Return previous more indent block """
        indent = indent if indent != None else block.userData().indent
        block = self.findPreviousNoBlankBlock(block)
        while block is not None and block.userData().indent <= indent:
            block = self.findPreviousNoBlankBlock(block)
        if block is not None:
            return block
    
    def findPreviousLessIndentBlock(self, block, indent = None):
        """ Return previous less indent block """
        indent = indent if indent != None else block.userData().indent
        block = self.findPreviousNoBlankBlock(block)
        while block is not None and block.userData().indent >= indent:
            block = self.findPreviousNoBlankBlock(block)
        if block is not None:
            return block

    def indentBlocks(self, cursor = None):
        """Indents text, block selections."""
        cursor = QtGui.QTextCursor(cursor or self.textCursor())
        start, end = self.getSelectionBlockStartEnd(cursor)
        cursor.beginEditBlock()
        while True:
            cursor.setPosition(start.position())
            cursor.insertText(self.tabKeyBehavior)
            if start == end:
                break
            start = start.next()
        cursor.endEditBlock()        

    def unindentBlocks(self, cursor = None):
        cursor = QtGui.QTextCursor(cursor or self.textCursor())
        start, end = self.getSelectionBlockStartEnd(cursor)
        cursor.beginEditBlock()
        while True:
            data = start.userData()
            if self.tabStopSoft:
                counter = self.tabStopSize if len(data.indent) > self.tabStopSize else len(data.indent)
            else:
                counter = 1 if len(data.indent) else 0
            if counter > 0:
                cursor.setPosition(start.position())
                for _ in range(counter):
                    cursor.deleteChar()
            if start == end:
                break
            start = start.next()
        cursor.endEditBlock()
    
    #===========================================================================
    # Menus
    #===========================================================================
    # Flat Popup Menu
    def showFlatPopupMenu(self, menuItems, callback, cursorPosition = True):
        menu = QtGui.QMenu(self)
        for index, item in enumerate(menuItems, 1):
            action = QtGui.QAction("%s \t&%d" % (item["title"], index), menu)
            if "image" in item:
                action.setIcon(resources.getIcon(item["image"]))
            receiver = lambda index = index: callback(index - 1)
            self.connect(action, QtCore.SIGNAL('triggered()'), receiver)
            menu.addAction(action)
        if cursorPosition:
            point = self.viewport().mapToGlobal(self.cursorRect(self.textCursor()).bottomRight())
        else:
            point = self.mainWindow.cursor().pos()
        menu.popup(point)
    
    # Default Context Menus
    def showEditorContextMenu(self, point):
        #TODO: Poneme aca tambien el menu por defecto de este bundle
        menu = self.createStandardContextMenu()
        menu.setParent(self)
        menu.popup(self.mapToGlobal(point))
    
    # Contributes to Tab Menu
    def contributeToTabMenu(self, menu):
        bundleMenu = self.application.supportManager.menuForBundle(self.getSyntax().bundle)
        if bundleMenu is not None:
            menu.addMenu(bundleMenu)
            menu.addSeparator()
        if self.filePath:
            menu.addAction(self.actionCopyPath)
    
    # Contributes to Main Menu
    @classmethod
    def contributeToMainMenu(cls):
        view = {
            'items': [
                {'title': 'Font',
                 'items': [
                     {'title': "Zoom In",
                      'shortcut': "Ctrl++",
                      'callback': cls.zoomIn},
                     {'title': "Zoom Out",
                      'shortcut': "Ctrl+-",
                      'callback': cls.zoomOut}
                ]},
                {'title': 'Gutter',
                 'items': [
                    {'title': 'Foldings',
                     'callback': cls.on_actionShowFoldings_toggled,
                     'shortcut': 'Shift+F10',
                     'checkable': True,
                     'testChecked': lambda editor: bool(editor.getFlags() & editor.ShowFolding) },
                    {'title': "Bookmarks",
                     'callback': cls.on_actionShowBookmarks_toggled,
                     'shortcut': 'Alt+F10',
                     'checkable': True,
                     'testChecked': lambda editor: bool(editor.getFlags() & editor.ShowBookmarks) },
                    {'title': "Line Numbers",
                     'callback': cls.on_actionShowLineNumbers_toggled,
                     'shortcut': 'F10',
                     'checkable': True,
                     'testChecked': lambda editor: bool(editor.getFlags() & editor.ShowLineNumbers) },
                ]},
                '-',
                {'title': "Show Tabs And Spaces",
                 'callback': cls.on_actionShowTabsAndSpaces_toggled,
                 'checkable': True,
                 'testChecked': lambda editor: bool(editor.getFlags() & editor.ShowTabsAndSpaces) },
                {'title': "Show Line And Paragraph",
                 'callback': cls.on_actionShowLineAndParagraphs_toggled,
                 'checkable': True, 
                 'testChecked': lambda editor: bool(editor.getFlags() & editor.ShowLineAndParagraphs) }, 
                {'title': "Word Wrap",
                 'callback': cls.on_actionWordWrap_toggled,
                 'checkable': True,
                 'testChecked': lambda editor: bool(editor.getFlags() & editor.WordWrap) },
            ]}
        text = {
            'items': [ 
                {'title': 'Select',
                 'items': [
                    {'title': '&Word',
                     'shortcut': 'Ctrl+A',
                     'callback': lambda editor: editor.select(0)
                     },
                    {'title': '&Line',
                     'callback': lambda editor: editor.select(1)
                     },
                    {'title': '&Paragraph',
                     'callback': lambda editor: editor.select(2)
                     },
                    {'title': 'Enclosing &Brackets',
                     'callback': lambda editor: editor.select(editor.SelectEnclosingBrackets)
                     },
                    {'title': 'Current &Scope',
                     'callback': lambda editor: editor.select(editor.SelectCurrentScope)
                     },
                    {'title': '&All',
                     'shortcut': 'Ctrl+A',
                     'callback': lambda editor: editor.select(3)
                     }    
                ]},
                {'title': 'Convert',
                 'items': [
                    {'title': 'To Uppercase',
                     'shortcut': 'Ctrl+U',
                     'callback': lambda editor: editor.convertText(editor.ConvertToUppercase),
                     },
                    {'title': 'To Lowercase',
                     'shortcut': 'Ctrl+Shift+U',
                     'callback': lambda editor: editor.convertText(editor.ConvertToLowercase),
                     },
                    {'title': 'To Titlecase',
                     'shortcut': 'Ctrl+Alt+U',
                     'callback': lambda editor: editor.convertText(editor.ConvertToTitlecase),
                     },
                    {'title': 'To Opposite Case',
                     'shortcut': 'Ctrl+G',
                     'callback': lambda editor: editor.convertText(editor.ConvertToOppositeCase),
                     }, '-',
                    {'title': 'Tab to Spaces',
                     'callback': lambda editor: editor.convertText(editor.ConvertTabsToSpaces),
                     },
                    {'title': 'Spaces to Tabs',
                     'callback': lambda editor: editor.convertText(editor.ConvertSpacesToTabs),
                     }, '-',
                    {'title': 'Transpose',
                     'shortcut': 'Ctrl+T',
                     'callback': lambda editor: editor.convertText(editor.ConvertTranspose),
                     }
                ]},
                {'title': 'Move',
                 'items': [
                    {'title': 'Line Up',
                     'shortcut': 'Meta+Ctrl+Up',
                     'callback': lambda editor: editor.moveText(editor.MoveLineUp),
                     },
                    {'title': 'Line Down',
                     'shortcut': 'Meta+Ctrl+Down',
                     'callback': lambda editor: editor.moveText(editor.MoveLineDown),
                     },
                    {'title': 'Column Left',
                     'shortcut': 'Meta+Ctrl+Left',
                     'callback': lambda editor: editor.moveText(editor.MoveColumnLeft),
                     },
                    {'title': 'Column Right',
                     'shortcut': 'Meta+Ctrl+Right',
                     'callback': lambda editor: editor.moveText(editor.MoveColumnRight),
                     }  
                  ]},
                '-',
                {'title': 'Select Bundle Item',
                 'shortcut': 'Meta+Ctrl+T',
                 'callback': cls.on_actionSelectBundleItem_triggered,
                 },
                {'title': 'Execute Line/Selection',
                 'callback': lambda editor: editor.executeCommand(),
                 }
            ]}
        navigation = {
            'items': [
                "-",
                {'title': 'Toggle Bookmark',
                 'callback': cls.toggleBookmark,
                 'shortcut': 'Meta+F12',
                 },
                {'title': 'Next Bookmark',
                 'callback': cls.bookmarkNext,
                 'shortcut': 'Meta+Alt+F12',
                 },
                {'title': 'Previous Bookmark',
                 'callback': cls.bookmarkPrevious,
                 'shortcut': 'Meta+Shift+F12',
                 },
                {'title': 'Remove All Bookmarks',
                 'callback': cls.removeAllBookmarks,
                 'shortcut': 'Meta+Ctrl+F12',
                 },
                "-",
                {'title': 'Go To &Symbol',
                 'callback': cls.on_actionGoToSymbol_triggered,
                 'shortcut': 'Meta+Ctrl+Shift+O',
                 },
                {'title': 'Go To &Bookmark',
                 'callback': cls.on_actionGoToBookmark_triggered,
                 'shortcut': 'Meta+Ctrl+Shift+B',
                 }
            ]}
        return { "View": view , "Text": text, "Navigation": navigation}
    
    @classmethod
    def contributeToSettings(cls):
        from prymatex.gui.settings.themes import PMXThemeWidget
        from prymatex.gui.settings.editor import PMXEditorWidget
        return [ PMXEditorWidget, PMXThemeWidget ]

    #===========================================================================
    # Menu Actions
    #===========================================================================
    def on_actionShowTabsAndSpaces_toggled(self, checked):
        if checked:
            flags = self.getFlags() | self.ShowTabsAndSpaces
        else:
            flags = self.getFlags() & ~self.ShowTabsAndSpaces
        self.setFlags(flags)
    
    def on_actionShowLineAndParagraphs_toggled(self, checked):
        if checked:
            flags = self.getFlags() | self.ShowLineAndParagraphs
        else:
            flags = self.getFlags() & ~self.ShowLineAndParagraphs
        self.setFlags(flags)
        
    def on_actionWordWrap_toggled(self, checked):
        if checked:
            flags = self.getFlags() | self.WordWrap
        else:
            flags = self.getFlags() & ~self.WordWrap
        self.setFlags(flags)
    
    def on_actionShowBookmarks_toggled(self, checked):
        if checked:
            flags = self.getFlags() | self.ShowBookmarks
        else:
            flags = self.getFlags() & ~self.ShowBookmarks
        self.setFlags(flags)
    
    def on_actionShowLineNumbers_toggled(self, checked):
        if checked:
            flags = self.getFlags() | self.ShowLineNumbers
        else:
            flags = self.getFlags() & ~self.ShowLineNumbers
        self.setFlags(flags)
        
    def on_actionShowFoldings_toggled(self, checked):
        if checked:
            flags = self.getFlags() | self.ShowFolding
        else:
            flags = self.getFlags() & ~self.ShowFolding
        self.setFlags(flags)
    
    def on_actionSelectBundleItem_triggered(self):
        scope = self.getCurrentScope()
        items = self.application.supportManager.getActionItems(scope)
        def itemsToDict(items):
            for item in items:
                yield [dict(title = item.name, image = item.TYPE), dict(title = item.bundle.name), dict(title = item.trigger)]
        index = self.mainWindow.bundleSelectorDialog.select(itemsToDict(items))
        if index is not None:
            self.insertBundleItem(items[index])
            
    def on_actionGoToSymbol_triggered(self):
        blocks = self.symbolListModel.blocks
        def symbolToDict(blocks):
            for block in blocks:
                userData = block.userData() 
                yield [dict(title = userData.symbol, image = resources.getIcon('codefunction'))]
        index = self.mainWindow.symbolSelectorDialog.select(symbolToDict(blocks))
        if index is not None:
            self.goToBlock(blocks[index])
        
    def on_actionGoToBookmark_triggered(self):
        blocks = self.bookmarkListModel.blocks
        def bookmarkToDict(blocks):
            for block in blocks:
                yield [dict(title = block.text(), image = resources.getIcon('bookmarkflag'))]
        index = self.mainWindow.bookmarkSelectorDialog.select(bookmarkToDict(blocks))
        if index is not None:
            self.goToBlock(blocks[index])
    
    #============================================================
    # Text Menu Actions
    #============================================================
    def on_actionExecute_triggered(self):
        self.currentEditor().executeCommand()

    def on_actionFilterThroughCommand_triggered(self):
        self.statusBar().showCommand()
    
    #===========================================================================
    # Drag and Drop
    #===========================================================================
    def dragEnterEvent(self, event):
        mimeData = event.mimeData()
        if mimeData.hasUrls() or mimeData.hasText():
            event.accept()
    
    def dragMoveEvent(self, event):
        cursor = self.cursorForPosition(event.pos())
        self.setTextCursor(cursor)
     
    def dropEvent(self, event):
        """
        When a url or text is dropped
        """
        #mimeData = event.mimeData()
        if event.mimeData().hasUrls():
            files = map(lambda url: url.toLocalFile(), event.mimeData().urls())
            scope = self.getCurrentScope()
            for file in files:                
                items = self.application.supportManager.getFileExtensionItem(file, scope)
                if items:
                    item = items[0]
                    env = { 
                            #relative path of the file dropped (relative to the document directory, which is also set as the current directory).
                            'TM_DROPPED_FILE': file,
                            #the absolute path of the file dropped.
                            'TM_DROPPED_FILEPATH': file,
                            #the modifier keys which were held down when the file got dropped.
                            #This is a bitwise OR in the form: SHIFT|CONTROL|OPTION|COMMAND (in case all modifiers were down).
                            'TM_MODIFIER_FLAGS': file
                    }
                    self.insertBundleItem(item, environment = env)
                else:
                    self.application.openFile(file)
        elif event.mimeData().hasText():
            self.textCursor().insertText(event.mimeData().text())

    @QtCore.pyqtSlot()
    def on_actionCopyPath_triggered(self):
        QtGui.QApplication.clipboard().setText(self.filePath)
