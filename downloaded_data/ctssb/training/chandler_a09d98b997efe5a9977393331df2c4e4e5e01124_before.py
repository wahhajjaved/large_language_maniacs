#   Copyright (c) 2003-2006 Open Source Applications Foundation
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.


import sys
import wx.grid

from application import schema
from application.Application import mixinAClass

from osaf.pim import ContentCollection
import application.dialogs.RecurrenceDialog as RecurrenceDialog
from osaf.sharing import ChooseFormat

from Block import (
    RectangularChild,
    Block,
    WithoutSynchronizeWidget,
    IgnoreSynchronizeWidget
    )

from ControlBlocks import Column

import Styles
import DragAndDrop
import PimBlocks
import DrawingUtilities


class wxTableData(wx.grid.PyGridTableBase):
    def __init__(self, *arguments, **keywords):
        super (wxTableData, self).__init__ (*arguments, **keywords)
        self.defaultRWAttribute = wx.grid.GridCellAttr()
        self.defaultROAttribute = wx.grid.GridCellAttr()
        self.defaultROAttribute.SetReadOnly (True)

    def __del__ (self):
        self.defaultRWAttribute.DecRef()
        self.defaultROAttribute.DecRef()
        
    def GetNumberRows (self):
        return self.GetView().GetElementCount()

    def GetNumberCols (self):
        return self.GetView().GetColumnCount()

    def GetColLabelValue (self, column):
        grid = self.GetView()
        item = grid.blockItem.contents.getFirstSelectedItem()
        return grid.GetColumnHeading (column, item)

    def GetColLabelBitmap(self, column):
        grid = self.GetView()
        table = grid.blockItem
        columnItem = table.columns[column]

        if hasattr(columnItem, 'icon'):            
            # we'll cache the bitmap so we're not constantly loading
            # it from disk
            bitmap = getattr(self, '_colbitmap%s' % column, None)
            if bitmap is None:
                bitmap = wx.GetApp().GetImage(columnItem.icon + ".png")
                setattr(self, '_colbitmap%s' % column, bitmap)
            return bitmap
        
        else:
            return None
        

    def IsEmptyCell (self, row, column): 
        return False 

    def GetValue (self, row, column):
        return self.GetView().GetElementValue (row, column)

    def SetValue (self, row, column, value):
        self.GetView().SetElementValue (row, column, value) 

    def GetTypeName (self, row, column):
        return self.GetView().GetElementType (row, column)

    def GetAttr (self, row, column, kind):
        attribute = super(wxTableData, self).GetAttr (row, column, kind)
        if attribute is None:
            type = self.GetTypeName (row, column)
            delegate = AttributeEditors.getSingleton (type)
            attribute = self.defaultROAttribute
            grid = self.GetView()
            assert (row < grid.GetTable().GetNumberRows() and
                    column < grid.GetTable().GetNumberCols())

            if (not grid.blockItem.columns[column].readOnly and
                not grid.ReadOnly (row, column)[0] and
                not delegate.ReadOnly (grid.GetElementValue (row, column))):
                attribute = self.defaultRWAttribute
            attribute.IncRef()
        return attribute

class wxTable(DragAndDrop.DraggableWidget, 
              DragAndDrop.DropReceiveWidget, 
              DragAndDrop.FileOrItemClipboardHandler,
              wx.grid.Grid):
    def __init__(self, parent, widgetID, characterStyle, headerCharacterStyle, *arguments, **keywords):
        if '__WXMAC__' in wx.PlatformInfo:
            theStyle=wx.BORDER_SIMPLE
        else:
            theStyle=wx.BORDER_STATIC
        """
          Giant hack. Calling event.GetEventObject in OnShow of
          application, while the object is being created cause the
          object to get the wrong type because of a
          "feature" of SWIG. So we need to avoid OnShows in this case.
        """
        IgnoreSynchronizeWidget(True, super(wxTable, self).__init__,
                                parent, widgetID, style=theStyle,
                                *arguments, **keywords)

        self.SetDefaultCellFont(Styles.getFont(characterStyle))
        self.SetLabelFont(Styles.getFont(headerCharacterStyle))
        self.SetColLabelAlignment(wx.ALIGN_LEFT, wx.ALIGN_CENTRE)
        self.SetRowLabelSize(0)
        self.AutoSizeRows()
        self.EnableDragCell(True)
        self.DisableDragRowSize()
        self.SetDefaultCellBackgroundColour(wx.WHITE)
        self.EnableCursor (False)
        self.SetLightSelectionBackground()
        self.SetScrollLineY (self.GetDefaultRowSize())
        self.SetUseVisibleColHeaderSelection(True)
        self.SetUseColSortArrows(True)

        self.Bind(wx.EVT_KILL_FOCUS, self.OnLoseFocus)
        self.Bind(wx.EVT_SET_FOCUS, self.OnGainFocus)
        self.Bind(wx.grid.EVT_GRID_CELL_BEGIN_DRAG, self.OnItemDrag)
        self.Bind(wx.grid.EVT_GRID_CELL_RIGHT_CLICK, self.OnRightClick)
        self.Bind(wx.grid.EVT_GRID_COL_SIZE, self.OnColumnDrag)
        self.Bind(wx.grid.EVT_GRID_RANGE_SELECT, self.OnRangeSelect)
        self.Bind(wx.grid.EVT_GRID_LABEL_LEFT_CLICK, self.OnLabelLeftClicked)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.GetGridWindow().Bind(wx.EVT_PAINT, self.OnPaint)


    def OnPaint (self, event):
        # Bug #7117: Don't draw gridWindows who's data has changed but hasn't
        # been synchronized to the widget.
        wx.GetApp().fireAsynchronousNotifications()
        if not self.blockItem.isDirty():
            event.Skip()

    def OnGainFocus (self, event):
        self.SetSelectionBackground (wx.SystemSettings.GetColour (wx.SYS_COLOUR_HIGHLIGHT))
        self.InvalidateSelection ()

    def OnLoseFocus (self, event):
        self.SetLightSelectionBackground()
        self.InvalidateSelection ()

    def OnLabelLeftClicked (self, event):
        assert (event.GetRow() == -1) # Currently Table only supports column headers
        blockItem = self.blockItem
        column = blockItem.columns[event.GetCol()]
        indexName = column.indexName
        sameColumn = blockItem.contents.indexName == indexName
        blockItem.contents.setCollectionIndex(indexName,
             toggleDescending=sameColumn)
        self.wxSynchronizeWidget()

    def OnKeyDown(self, event):

        # default grid behavior is to move to the "next" cell,
        # whatever that may be. We want to edit instead.
        if event.GetKeyCode() == wx.WXK_RETURN:
            defaultEditableAttribute = getattr(self.blockItem,
                                               'defaultEditableAttribute',
                                               None)
            if defaultEditableAttribute is not None:
                self.EditAttribute(self.blockItem.defaultEditableAttribute)
                
            return

        # other keys should just get propagated up
        event.Skip()
        

    def SetLightSelectionBackground (self):
        background = wx.SystemSettings.GetColour (wx.SYS_COLOUR_HIGHLIGHT)
        background.Set ((background.Red() + 255) / 2,
                        (background.Green() + 255) / 2,
                         (background.Blue() + 255) / 2)
        self.SetSelectionBackground (background)

    def InvalidateSelection (self):
        # Calling InvalidateSelection when the Table block is
        # out of sync with the data, i.e. the data has changed
        # but the block hasn't yet synchronized to the data
        # triggers an assert. So let's fire the notifications
        # and, if the block is dirtied, skip invalidating the
        # selection. We'll eventually draw the the selection
        # anyway since the block is dirtied.
        wx.GetApp().fireAsynchronousNotifications()
        block = self.blockItem
        if not block.isDirty():
            lastRow = self.GetNumberCols() - 1
            
            for rowStart, rowEnd in self.SelectedRowRanges():
                dirtyRect = wx.Rect()
                dirtyRect.SetTopLeft(self.CellToRect(rowStart, 0).GetTopLeft())
                dirtyRect.SetBottomRight(self.CellToRect(rowEnd,
                                                         lastRow).GetBottomRight())
                dirtyRect.OffsetXY (self.GetRowLabelSize(), self.GetColLabelSize())
                self.RefreshRect (dirtyRect)

    def OnInit (self):
        """
          wxTableData handles the callbacks to display the elements of the
        table. Setting the second argument to True cause the table to be deleted
        when the grid is deleted.

          We've also got the usual chicken and egg problem: SetTable uses the
        table before initializing it's view so let's first set the view.
        """
        
        elementDelegate = self.blockItem.elementDelegate
        if not elementDelegate:
            elementDelegate = 'osaf.framework.blocks.ControlBlocks.AttributeDelegate'
        mixinAClass (self, elementDelegate)
        self.InitElementDelegate()

        gridTable = wxTableData()
        gridTable.SetView (self)
        self.SetTable (gridTable, True, selmode=wx.grid.Grid.SelectRows)

        self.EnableGridLines (self.blockItem.hasGridLines)

    @WithoutSynchronizeWidget
    def OnRangeSelect(self, event):
        """
        Synchronize the grid's selection back into the row
        """
        blockItem = self.blockItem
        # Ignore notifications that arrise as a side effect of
        # changes to the selection
        blockItem.stopNotificationDirt()
        try:
            # map row ranges to index ranges 
            contents = self.blockItem.contents

            firstRow = event.GetTopRow()
            lastRow = event.GetBottomRow()
            indexStart = self.RowToIndex(firstRow)
            indexEnd = self.RowToIndex(lastRow)

            postSelection = True
            selectionChanged = False

            if event.Selecting():
                if -1 not in (indexStart, indexEnd) and \
                   not contents.isSelected((indexStart, indexEnd)):
                    selectionChanged = True
                    contents.addSelectionRange((indexStart, indexEnd))
            elif (firstRow == 0 and lastRow != 0 
                  and lastRow == self.GetNumberRows()-1):
                # this is a special "deselection" event that the
                # grid sends us just before selecting another
                # single item. This happens just before a user
                # simply clicks from one item to another.

                # this allows us to avoid broadcasting an empty
                # deselection if the user is just clicking from
                # one item to another.
                contents.clearSelection()
                postSelection = False
            else:
                assert -1 not in (firstRow, lastRow)
                if contents.isSelected((indexStart, indexEnd)):
                    selectionChanged = True
                    
                # we always want to remove the old selection
                contents.removeSelectionRange((indexStart, indexEnd))
                    
            # possibly broadcast the "new" selection
            if selectionChanged and postSelection:
                gridTable = self.GetTable()
                for columnIndex in xrange (gridTable.GetNumberCols()):
                    self.SetColLabelValue (columnIndex, gridTable.GetColLabelValue (columnIndex))
                blockItem.PostSelectItems()
        finally:
            blockItem.startNotificationDirt()

        event.Skip()

    @WithoutSynchronizeWidget
    def OnColumnDrag(self, event):
        for index, column in enumerate(self.blockItem.columns):
            column.width = self.GetColSize (index)

    def OnItemDrag(self, event):

        # To fix bug 2159, tell the grid to release the mouse now because the
        # grid object may get destroyed before it has a chance to later on:
        gridWindow = self.GetGridWindow()
        if gridWindow.HasCapture():
            gridWindow.ReleaseMouse()

        # If we don't have a selection, set it the firstRow of the event.
        contents = self.blockItem.contents
        if len (contents.getSelectionRanges()) == 0:
            firstRow = event.GetRow()
            selectedItemIndex = self.RowToIndex(firstRow)
            if selectedItemIndex != -1:
                contents.setSelectionRanges([(selectedItemIndex,
                                              selectedItemIndex)])
        self.DoDragAndDrop(copyOnly=True)

    def AddItems(self, itemList):
        
        collection = self.blockItem.GetCurrentContents(writable=True)
        assert collection, "Can't add items to readonly collection - should block before the drop"
        
        for item in itemList:
            item.addToCollection(collection)

    def OnRightClick(self, event):
        itemIndex = self.RowToIndex(event.GetRow())
        if itemIndex == -1:
            item = []
        else:
            item = self.blockItem.contents[itemIndex]
            
        self.blockItem.DisplayContextMenu(event.GetPosition(), item)

    def OnFilePaste(self):
        for filename in self.fileDataObject.GetFilenames():
            ChooseFormat.importFile(filename, self.blockItem.itsView,
                                    selectedCollection=True)

    def OnEmailPaste(self, text):
        ChooseFormat.importEmail(text, self.blockItem.itsView,
                                 selectedCollection=True)

    def wxSynchronizeWidget(self, useHints=False):
        """
          A Grid can't easily redisplay its contents, so we write the following
        helper function to readjust everything after the contents change
        """

        def UpdateSelection(columns):
            """
            Update the grid's selection based on the collection's selection.
    
            If we previously had selected items, but now are not, then we
            probably just deleted all the selected items so we should try
            to select the next logical item in the collection.
            """
    
            # remember the first row in the old selection
            topLeftSelection = self.GetSelectionBlockTopLeft()
            
            if len(topLeftSelection) > 0:
                newRowSelection = topLeftSelection[0][0]
            else:
                newRowSelection = -1
            
            # avoid OnRangeSelect
            IgnoreSynchronizeWidget(True, self.ClearSelection)
            contents = self.blockItem.contents
            for rowStart,rowEnd in self.SelectedRowRanges():
                # since we're selecting something, we don't need to
                # auto-select any rows
                newRowSelection = -1
    
                # now just do the selection update
                try:
                    self.SelectBlock (rowStart, 0, rowEnd, columns, True)
                except:
                    import pdb; pdb.set_trace()
    
            # now auto-select a row if necessary
            if newRowSelection != -1:
                itemIndex = self.RowToIndex(newRowSelection)
                if itemIndex != -1:
                    # we need to do this after the current
                    # wxSynchronizeWidget is over
                    wx.CallAfter(self.blockItem.PostSelectItems,
                                 [self.blockItem.contents[itemIndex]])
        
        rowHeight = getattr (self.blockItem, "rowHeight", None)
        if rowHeight is not None:
            self.SetDefaultRowSize (rowHeight)
        
        self.SynchronizeDelegate()

        #Trim/extend the control's rows and update all values
        if self.blockItem.hideColumnHeadings:
            self.SetColLabelSize (0)
        else:
            self.SetColLabelSize (wx.grid.GRID_DEFAULT_COL_LABEL_HEIGHT)


        gridTable = self.GetTable()
        newColumns = gridTable.GetNumberCols()
        newRows = gridTable.GetNumberRows()

        oldColumns = self.GetNumberCols()
        oldRows = self.GetNumberRows()
        # update the widget to reflect the new or removed rows or
        # columns. Note that we're only telling the grid HOW MANY rows
        # or columns to add/remove - the per-cell callbacks will
        # determine what actual text to display in each cell

        def SendTableMessage(current, new, deleteMessage, addMessage):
            if new == current: return
            
            if new < current: 
                message = wx.grid.GridTableMessage(gridTable, deleteMessage,
                                                   new, current-new) 
            elif new > current: 
                message = wx.grid.GridTableMessage(gridTable, addMessage,
                                                   new-current) 
            self.ProcessTableMessage (message) 


        self.BeginBatch()
        SendTableMessage(oldRows, newRows,
                         wx.grid.GRIDTABLE_NOTIFY_ROWS_DELETED,
                         wx.grid.GRIDTABLE_NOTIFY_ROWS_APPENDED)
        
        SendTableMessage(oldColumns, newColumns,
                         wx.grid.GRIDTABLE_NOTIFY_COLS_DELETED,
                         wx.grid.GRIDTABLE_NOTIFY_COLS_APPENDED)
        
        assert (self.GetNumberCols() == gridTable.GetNumberCols() and
                self.GetNumberRows() == gridTable.GetNumberRows())

        # Update column widths and sortedness
        indexName = self.blockItem.contents.indexName
        for i, column in enumerate(self.blockItem.columns):
            self.SetColSize (i, column.width)
            self.ScaleColumn (i, column.scaleColumn)
            columnIndexName = getattr(column, 'indexName', '__adhoc__')
            if indexName == '__adhoc__' and column.defaultSort:
                indexName = columnIndexName
                self.blockItem.contents.setCollectionIndex(indexName)
            if columnIndexName == indexName:
                self.SetUseColSortArrows(column.useSortArrows)
                self.SetSelectedCol(i)

        self.ScaleWidthToFit (self.blockItem.scaleWidthsToFit)

        UpdateSelection(newColumns)
        self.EndBatch()

        # Update all displayed values
        gridTable = self.GetTable()
        message = wx.grid.GridTableMessage (gridTable, wx.grid.GRIDTABLE_REQUEST_VIEW_GET_VALUES) 
        self.ProcessTableMessage (message)
        self.ForceRefresh () 

        editAttributeNamed = getattr(self, "editAttributeNamed", None)
        if editAttributeNamed is not None:
            del self.editAttributeNamed
            self.EditAttribute(editAttributeNamed)


    def EditAttribute(self, attrName):
        contents = self.blockItem.contents

        index = contents.index(contents.getFirstSelectedItem())
        cursorRow = self.IndexToRow(index)
        
        if cursorRow == -1:
            return

        # find the relevant column
        for colIndex,column in enumerate(self.blockItem.columns):
            if (column.valueType == 'attribute' and
                column.attributeName == attrName):
                break
        else:
            return

        self.SetGridCursor (cursorRow, colIndex)
        self.EnableCellEditControl()

    def GoToItem(self, item):
        if item != None:
            try:
                index = self.blockItem.contents.index (item)
                row = self.IndexToRow(index)
            except ValueError:
                item = None
        blockItem = self.blockItem
        if item is not None:
            blockItem.contents.addSelectionRange (index)
            self.SelectBlock (row, 0, row, self.GetColumnCount() - 1)
            self.MakeCellVisible (row, 0)
        else:
            blockItem.contents.clearSelection()
            self.ClearSelection()
        self.blockItem.PostSelectItems()

    def SelectedRowRanges(self):
        """
        Uses IndexRangeToRowRange to convert the selected indexes to
        selected rows
        """
        selection = self.blockItem.contents.getSelectionRanges()
        return self.IndexRangeToRowRange(selection)

    def IndexRangeToRowRange(self, indexRanges):
        """
        Given a list of index ranges, [(a,b), (c,d), ...], generate
        corresponding row ranges [(w,x), (y, z),..]

        Eventually this will need to get more complex when
        IndexToRow() returns multiple rows
        """
        for (indexStart, indexEnd) in indexRanges:
            topRow = self.IndexToRow(indexStart)
            bottomRow = self.IndexToRow(indexEnd)

            # not sure when the -1 case would happen?
            if -1 not in (topRow, bottomRow):
                yield (topRow, bottomRow)

    def DeleteSelection (self, DeleteItemCallback=None, *args, **kwargs):
        def DefaultCallback(item, collection=self.blockItem.contents):
            collection.remove(item)
            
        blockItem = self.blockItem
        if DeleteItemCallback is None:
            DeleteItemCallback = DefaultCallback

        # save a list copy of the ranges because we're about to clear them.
        selectionRanges = list(reversed(self.blockItem.contents.getSelectionRanges()))

        """
          Clear the selection before removing the elements from the collection
        otherwise our delegate will get called asking for deleted items
        """
        self.ClearSelection()
        # now delete rows - since we reverse sorted, the
        # "newSelectedItemIndex" will be the highest row that we're
        # not deleting
        
        # this is broken - we shouldn't be going through the widget
        # to delete the items! Instead, when items are removed from the
        # current collection, the widget should be notified to remove
        # the corresponding rows.
        # (that probably can't be fixed until ItemCollection
        # becomes Collection and notifications work again)

        newRowSelection = 0
        contents = blockItem.contents
        newSelectedItemIndex = -1
        for selectionStart,selectionEnd in selectionRanges:
            for itemIndex in xrange (selectionEnd, selectionStart - 1, -1):
                DeleteItemCallback(contents[itemIndex])
                # remember the last deleted row
                newSelectedItemIndex = itemIndex
        
        blockItem.contents.clearSelection()
        blockItem.itsView.commit()
        
        # now select the "next" item
        """
          We call wxSynchronizeWidget here because the postEvent
          causes the DetailView to call it's wxSynchronizeWidget,
          which calls layout, which causes us to redraw the table,
          which hasn't had time to get it's notificaitons so its data
          is out of synch and chandler Crashes. So I think the long
          term fix is to not call wxSynchronizeWidget here or in the
          DetailView and instead let the notifications cause
          wxSynchronizeWidget to be called. -- DJA
        """
        blockItem.synchronizeWidget()
        totalItems = len(contents)
        if totalItems > 0:
            if newSelectedItemIndex != -1:
                newSelectedItemIndex = min(newSelectedItemIndex, totalItems - 1)
            blockItem.PostSelectItems([contents[newSelectedItemIndex]])
        else:
            blockItem.PostSelectItems([])

    def SelectedItems(self):
        """
        Return the list of selected items.
        """
        return self.blockItem.contents.iterSelection()

class GridCellAttributeRenderer (wx.grid.PyGridCellRenderer):
    def __init__(self, type):
        super (GridCellAttributeRenderer, self).__init__ ()
        self.delegate = AttributeEditors.getSingleton (type)

    def Draw (self, grid, attr, dc, rect, row, column, isInSelection):
        """
          Currently only handles left justified multiline text
        """
        DrawingUtilities.SetTextColorsAndFont (grid, attr, dc, isInSelection)
        value = grid.GetElementValue (row, column)
        assert len(value) != 2 or not value[0].isDeleted()            
        self.delegate.Draw(grid, dc, rect, value, isInSelection)

class GridCellAttributeEditor (wx.grid.PyGridCellEditor):
    def __init__(self, type):
        super (GridCellAttributeEditor, self).__init__ ()
        self.delegate = AttributeEditors.getSingleton (type)

    def Create (self, parent, id, evtHandler):
        """
          Create an edit control to edit the text
        """
        self.control = self.delegate.CreateControl(True, False, parent, id, None, None)
        self.SetControl (self.control)
        if evtHandler:
            self.control.PushEventHandler (evtHandler)

    def PaintBackground (self, *arguments, **keywords):
        """
          background drawing is done by the edit control
        """
        pass

    def BeginEdit (self, row,  column, grid):
        assert getattr(self, 'editingCell', None) is None
        if __debug__:
            self.editingCell = (row, column)
        
        item, attributeName = grid.GetElementValue (row, column)
        assert not item.isDeleted()
        item = RecurrenceDialog.getProxy(u'ui', item)
        
        self.initialValue = self.delegate.GetAttributeValue (item, attributeName)
        self.delegate.BeginControlEdit (item, attributeName, self.control)
        self.control.SetFocus()
        self.control.ActivateInPlace()

    def EndEdit (self, row, column, grid):
        # We'd better be editing the same cell we started with
        if not __debug__ or hasattr (self, "editingCell"):
            assert self.editingCell == (row, column)
            
            value = self.delegate.GetControlValue (self.control)
            item, attributeName = grid.GetElementValue (row, column)
            assert not item.isDeleted()
            item = RecurrenceDialog.getProxy(u'ui', item)
    
            if value == self.initialValue:
                changed = False
            # @@@ For now we do not want to allow users to blank out fields.  This should eventually be
            #  replaced by proper editor validation.
            elif value.strip() == '':
                changed = False
            else:
                changed = True
                # set the value using the delegate's setter, if it has one.
                try:
                    attributeSetter = self.delegate.SetAttributeValue
                except AttributeError:
                    grid.SetElementValue (row, column, value)
                else:
                    attributeSetter (item, attributeName, value)
            self.delegate.EndControlEdit (item, attributeName, self.control)
            if __debug__:
                del self.editingCell
            return changed

    def Reset (self):
        self.delegate.SetControlValue (self.control, self.initialValue)

    def GetValue (self):
        assert False # who needs this?
        return self.delegate.GetControlValue (self.control)

    def IsAcceptedKey(self, event):

        # These are the keys that are acceptable to begin editing in
        # the table. Because these keys are also bound to menu items,
        # we don't want them to start editing.

        # Really, we should be able to look them up in the window's
        # accelerator table, but there's no way to do that from
        # Python.
        
        if event.GetKeyCode() in (wx.WXK_DELETE, wx.WXK_BACK):
            return False

        return super(GridCellAttributeEditor, self).IsAcceptedKey(event)


class Table (PimBlocks.FocusEventHandlers, RectangularChild):

    columns = schema.Sequence(Column, required=True)
    
    rowHeight = schema.One(schema.Integer)
    
    elementDelegate = schema.One(schema.Text, initialValue = '')
    defaultEditableAttribute = \
        schema.One(schema.Text,
                   doc="The default attribute to edit, for instance if "
                   "the user uses the keyboard to activate in-place editing")
    
    hideColumnHeadings = schema.One(schema.Boolean, initialValue = False)
    characterStyle = schema.One(Styles.CharacterStyle)
    headerCharacterStyle = schema.One(Styles.CharacterStyle)
    hasGridLines = schema.One(schema.Boolean, initialValue = False)
    scaleWidthsToFit = schema.One(schema.Boolean, defaultValue = False)

    schema.addClouds(
        copying = schema.Cloud(
            byRef=[characterStyle, headerCharacterStyle],
            byCloud=[columns]
        )
    )

    def __init__(self, *arguments, **keywords):
        super (Table, self).__init__ (*arguments, **keywords)

    def instantiateWidget (self):
        widget = wxTable (self.parentBlock.widget, 
                          Block.getWidgetID(self),
                          characterStyle=getattr(self, "characterStyle", None),
                          headerCharacterStyle=getattr(self, "headerCharacterStyle", None))        
        self.registerAttributeEditors(widget)
        return widget
    
    def registerAttributeEditors(self, widget):
        defaultName = "_default"
        widget.SetDefaultRenderer (GridCellAttributeRenderer (defaultName))
        aeKind = AttributeEditors.AttributeEditorMapping.getKind(self.itsView)
        for ae in aeKind.iterItems():
            key = ae.itsName
            if key != defaultName:
                widget.RegisterDataType (key,
                                         GridCellAttributeRenderer (key),
                                         GridCellAttributeEditor (key))

    def GetCurrentContents(self, writable=False):
        """
        The table's self.contents may contain a collectionList, in
        case this collection is composed of other collections. In this
        case, collectionList.first() is the 'primary' collection that
        should handle adds/deletes and other status updates
        """
        if hasattr(self.contents, 'collectionList'):
            collection = self.contents.collectionList.first()
        else:
            collection = self.contents
            
        # Sometimes you need a non-readonly collection. Should we be
        # checking if the collection has an 'add' attribute too?
        if not (writable and not collection.isReadOnly()):
            return collection

    def onSetContentsEvent (self, event):
        item = event.arguments ['item']
        if isinstance (item, ContentCollection):
            self.setContentsOnBlock(item, event.arguments['collection'])
            self.PostSelectItems()

    def onSetFocusEvent (self, event):
        self.widget.GetGridWindow().SetFocus()

    def onSelectItemsEvent (self, event):
        items = event.arguments ['items']
        self.selectItems (items)
            
        editAttributeNamed = event.arguments.get ('editAttributeNamed')
        if editAttributeNamed is not None:
            self.widget.EnableCellEditControl (False)
            self.widget.editAttributeNamed = editAttributeNamed

    def PostSelectItems(self, items = None):
        if items is None:
            items = list(self.contents.iterSelection())
        
        self.postEventByName("SelectItemsBroadcast",
                             {'items': items,
                              'collection': self.contentsCollection })
        
    def select (self, item):
        # polymorphic method used by scripts
        self.selectItems ([item])

    def selectItems (self, items):
        """
        Select the row corresponding to each item, and account for the
        fact that not all of the items are int the table Also make the
        first visible.
        """

        self.contents.clearSelection()
        for item in items:
            if item in self.contents:
                self.contents.selectItem(item)

    def onSelectAllEventUpdateUI(self, event):
        event.arguments['Enable'] = len(self.contents) > 0
        
    def onSelectAllEvent(self, event):
        self.PostSelectItems(self.contents)
            
# Ewww, yuk.  Blocks and attribute editors are mutually interdependent
import osaf.framework.attributeEditors
AttributeEditors = sys.modules['osaf.framework.attributeEditors']
