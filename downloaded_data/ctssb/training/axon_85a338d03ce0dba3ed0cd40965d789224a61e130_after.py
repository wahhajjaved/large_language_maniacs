#! /usr/bin/env python
# -*- coding: utf-8 -*-
#  This software and supporting documentation are distributed by
#      Institut Federatif de Recherche 49
#      CEA/NeuroSpin, Batiment 145,
#      91191 Gif-sur-Yvette cedex
#      France
#
# This software is governed by the CeCILL license version 2 under
# French law and abiding by the rules of distribution of free software.
# You can  use, modify and/or redistribute the software under the
# terms of the CeCILL license version 2 as circulated by CEA, CNRS
# and INRIA at the following URL "http://www.cecill.info".
#
# As a counterpart to the access to the source code and  rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty  and the software's author,  the holder of the
# economic rights,  and the successive licensors  have only  limited
# liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading,  using,  modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean  that it is complicated to manipulate,  and  that  also
# therefore means  that it is reserved for developers  and  experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systems and/or
# data to be ensured and,  more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license version 2 and that you accept its terms.
#import anatomist.threaded.api as ana

from PyQt4 import QtCore, Qt
from PyQt4.QtCore import SIGNAL
from PyQt4.QtGui import QRadioButton, QPalette, QButtonGroup, QPainter, QLabel, QFrame, QVBoxLayout, QColor
from PyQt4.uic import loadUi
from brainvisa.processing.qtgui.neuroProcessesGUI import mainThreadActions
from brainvisa.tools.mainthreadlife import MainThreadLife
from functools import partial
import anatomist.threaded.api as ana
from anatomist.cpp.paletteEditor import PaletteEditor

#------------------------------------------------------------------------------
def displayTitledGrid(transformationManager, context, inverseRawColumn,
                      objPathMatrix,
                      rowTitle=['raw_space', "MRI_native_space", "mask",
                        "MNI_space", ],
                      rowColors=['darkOrange', 'blue', "MRI", 'blue',
                        'magenta'], # orange = rawSpace, blue = mri space, magenta = mni space
                      colTitle=['PET', "MRI", "grey"],
                      windowTitle='View grid',
                      linkWindows='space', # linkWindows possible values : 'all' | none | row
                      overlaidImages=[],
                      mainColormap='B-W LINEAR',
                      overlayColormap='RAINBOW',
                      customOverlayColormap='Blue-White'
                     ):
  _mw = mainThreadActions().call(_displayTitledGrid_onGuiThread,
                                 transformationManager, context,
                                 inverseRawColumn,
                                 objPathMatrix, rowTitle=rowTitle,
                                 rowColors=rowColors, colTitle=colTitle,
                                 windowTitle=windowTitle,
                                 linkWindows=linkWindows,
                                 overlaidImages=overlaidImages,
                                 mainColormap=mainColormap,
                                 overlayColormap=overlayColormap,
                                 customOverlayColormap=customOverlayColormap)
  mw = MainThreadLife(_mw)# pour etre sure que la destruction de la mw se fasse sur le thread de Gui
  return [mw]

def _displayTitledGrid_onGuiThread(transformationManager, context,
                                   inverseRawColumn, objPathMatrix, rowTitle,
                                   rowColors, colTitle, windowTitle,
                                   linkWindows, overlaidImages, mainColormap,
                                   overlayColormap, customOverlayColormap):
  # DisplayTitledGrid doit etre construit sur le thread de Gui pour etre sure que la destruction de la mw se fasse sur le thread de Gui
  TitledGrid = DisplayTitledGrid(objPathMatrix, parent=context,mainColormap=mainColormap, overlayColormap=overlayColormap, customOverlayColormap=customOverlayColormap)
  mw = TitledGrid.display(inverseRawColumn=inverseRawColumn,
    windowFlag=QtCore.Qt.Window, windowTitle=windowTitle, rowTitle=rowTitle,
    colTitle=colTitle, rowColors=rowColors, linkWindows=linkWindows,
    overlaidImages=overlaidImages)[0]
  return mw

#------------------------------------------------------------------------------

class DisplayTitledGrid():

  def __init__(self, objPathMatrix, parent=None,
               mainColormap='B-W LINEAR',
               overlayColormap='RAINBOW',
               customOverlayColormap='Blue-White'):
    self.parent = parent
    self._main_colormap = mainColormap
    self._overlay_colormap = overlayColormap
    self._custom_overlay_colormap = customOverlayColormap
    self._loadObjectInAnatomist(objPathMatrix)
    self._overlaid_images = []
    self._overlay_fusions = []
    self._custom_overlay_fusions = []#momoTODO : pas besoin d'une liste, un seul suffit sinon l'utilisateur s'y perd (selection avec row et column). 
    self._selectedRow = -1
    self._selectedColumn = -1
    self._row_titles = []
    self._col_titles = []
    self._paletteEditor=None

  def display(self, inverseRawColumn=False, windowFlag=QtCore.Qt.Window
              , windowTitle='Compare'
              , rowTitle=["row_1", "row_2", "row_3", "row_4"]
              , colTitle=["col_1", "col_2", "col_3"]
              , rowColors=['darkOrange', 'blue', 'blue', 'magenta']# orange = rawSpace, blue = mri space, magenta = mni space
              , linkWindows='space'# linkWindows possible values : 'all' | none | row, default value : space
              , overlaidImages=[]): 

    self.mw = self._loadUserInterface()  # create self.mw.gridLayout  
    self.mw.setWindowTitle(windowTitle)    
    self.mw.setParent(self.parent, windowFlag)# if the mw.parent is destroyed, mw is destroyed first
    self.mw.setAttribute(QtCore.Qt.WA_DeleteOnClose)# if the mw is closed ( by user with X ) then mw will be destroyed

    self._row_titles = rowTitle
    self._col_titles = colTitle
    #self._custom_row_titles = [ x for x in rowTitle ]

    # load overlay (fusionned) images, and make fusions
    self._loadOverlayImages(overlaidImages)
    self._createOverlayFusions()

    self._addColumnButton(colTitle, inverseRawColumn)
    self._addRowButton(rowTitle, rowColors, inverseRawColumn)

    self._createAndLinkAnatomistWindowsInMainLayout(
      linkWindows, inverseRawColumn, 'Sagittal', rowTitle)

    self.mw.anatomistObjectList = self.anatomistObjectList # momo  :ca sert a quoi?

    # replace individual objects by overlays fusions when applicable
    self._addObjectOrFusion_inAnatomistWindows()

    self.mw.comboBox.currentIndexChanged.connect(
      partial(self._onComboBox_changed))
    self.mw.mixingSlider.valueChanged.connect(self._onMixingRateChanged)
    self.mw.maximizeButton.clicked.connect(self._onMaximizeButtonClicked)

    self.mw.show()

    return [self.mw]

#-----------------------------------------------------------------------------            
# private : begins with _
#-----------------------------------------------------------------------------    

  def _loadObjectInAnatomist(self, objPathMatrix):
    a = ana.Anatomist()
    self.anatomistObjectList = []
    for r in range(0, len(objPathMatrix)):
      objPathRow = objPathMatrix[r]
      anaObjRow = []
      for c in range(0, len(objPathRow)):
        objPath = objPathRow[c]
        if (objPath is not None):
          obj = a.loadObject(objPath, forceReload=False)
          obj.setPalette(self._main_colormap)
          anaObjRow.append(obj)
        else:
          anaObjRow.append(None)

      self.anatomistObjectList.append(anaObjRow)

  def _loadUserInterface(self):
    dotIdx = __file__.rindex('.')
    uiFileName = __file__[:dotIdx] + '.ui'
    mw = loadUi(uiFileName)
    mw.mixRate.setText('50 %')
    return mw

  def _addColumnButton(self, buttonTitles, inverseRawColumn):
    for buttonIndex in range(0, len(buttonTitles)):
      title = buttonTitles[buttonIndex]
      button = QRadioButton(title)
      
      if (inverseRawColumn):
        self.mw.gridLayout.addWidget(button, buttonIndex + 1, 0, QtCore.Qt.AlignHCenter)
        self.mw.gridLayout.setRowStretch(buttonIndex + 1, 10)
      else:
        self.mw.gridLayout.addWidget(button, 0, buttonIndex + 1, QtCore.Qt.AlignHCenter)
        self.mw.gridLayout.setColumnStretch(buttonIndex + 1, 10)
      button.clicked.connect(partial(self._onColumnButtonClicked, buttonIndex))

  def _addRowButton(self, buttonTitles, buttonColors, inverseRawColumn):
    self.rowsButtonGroup = QButtonGroup(self.mw)
    self.rowsButtonGroup.setExclusive(True)
    for buttonIndex in range(0, len(buttonTitles)):
      title = buttonTitles[buttonIndex]
      NotNoneCount = len(filter(lambda x:x!=None,self.anatomistObjectList[ buttonIndex ]))
      isFusionPossibleOnRow = NotNoneCount>1 or len(self._overlaid_images)>0
      if(isFusionPossibleOnRow == False):
        widget = DisplayTitledGrid._createColoredLabel(title, buttonColors[buttonIndex])
      else:
        widget = DisplayTitledGrid._createColoredButton(title, buttonColors[buttonIndex])
        self.rowsButtonGroup.addButton(widget, buttonIndex)
        widget.setToolTip('<p>Click on this button to superimpose a different image. To do so, click on this row button, then click on a column button to display the column main image as overlay on this row.<p><p>Click again on the tow button to go back to the initial views.</p>')
        widget.clicked.connect(partial(self._onRowButtonClicked, buttonIndex))
      if (inverseRawColumn):
        self.mw.gridLayout.addWidget(widget, 0, buttonIndex + 1)
        self.mw.gridLayout.setColumnStretch(buttonIndex + 1, 10)
      else:
        self.mw.gridLayout.addWidget(widget, buttonIndex + 1, 0)
        self.mw.gridLayout.setRowStretch(buttonIndex + 1, 10)

  @staticmethod
  def _createColoredButton(title, color):
    button = QRadioButton(title)
    buttonPalette = QPalette()
    buttonPalette.setColor(QPalette.ButtonText, Qt.QColor(color))
    button.setPalette(buttonPalette)
    #button.setDisabled(True)
    button.setCheckable(True)
    return button

  @staticmethod
  def _createColoredLabel(title, color):
    button = QLabel(title)
    buttonPalette = QPalette()
    buttonPalette.setColor(QPalette.ButtonText, Qt.QColor(color))
    button.setPalette(buttonPalette)
    return button
  
  def _createAndLinkAnatomistWindowsInMainLayout(
      self, linkWindows, inverseRawColumn, initialView, spaceNames):

    mw = self.mw
    mw.anaWinMatrix = []
    for r in range(0, len(self.anatomistObjectList)):
      anaWinRow = self._createAnatomistWindows_InMainLayout(inverseRawColumn, initialView, r)
      DisplayTitledGrid._linkAnatomistWindows(linkWindows, anaWinRow, spaceNames)

  def _createAnatomistWindows_InMainLayout(self, inverseRawColumn, view, rowIndex):
    mw = self.mw
    a = ana.Anatomist()
    anaObjRow = self.anatomistObjectList[rowIndex]
    anaWinRow = []    
    for c in range(0, len(anaObjRow)):
      anaObj = anaObjRow[c]
      if (anaObj is not None):
        w = a.createWindow(view, no_decoration=True)
        anaObj.addInWindows([w])
        anaWinRow.append(w)
        frame = self._createFrame(mw, w)
        if (inverseRawColumn):
          mw.gridLayout.addWidget(frame, c + 1, rowIndex + 1)
        else:
          mw.gridLayout.addWidget(frame, rowIndex + 1, c + 1)
      else:
        anaWinRow.append(None)
    mw.anaWinMatrix.append(anaWinRow)
    return mw.anaWinMatrix

  def _createFrame(self, mw, w):
    mw.frame = QFrame()
    mw.flay = QVBoxLayout(mw.frame)
    mw.flay.addWidget(w.getInternalRep())
    mw.frame.setObjectName('winborder')
    mw.frame.setStyleSheet('QFrame#winborder { border: 0px solid; border-radius: 4px; }')
    pal = mw.frame.palette()
    pal.setColor(QPalette.Dark, QColor(255, 192, 0))
    pal.setColor(QPalette.Midlight, QColor(192, 255, 0))
    pal.setColor(QPalette.Shadow, QColor(192, 0, 255))
    pal.setColor(QPalette.Light, QColor(0, 255, 192))
    pal.setColor(QPalette.Mid, QColor(0, 192, 255))
    return mw.frame
  
  @staticmethod
  def _linkAnatomistWindows(linkWindows, anaWinRow, spaceNames):
    if (linkWindows == 'all'):
      DisplayTitledGrid._linkAnatomistWindows_all(anaWinRow)
    elif (linkWindows == 'row'):
      DisplayTitledGrid._linkAnatomistWindows_byRow(anaWinRow)
    elif (linkWindows == 'space'):
      DisplayTitledGrid._linkAnatomistWindows_bySpace(anaWinRow, spaceNames)

  @staticmethod  
  def _linkAnatomistWindows_all(anaWinMatrix):
    a = ana.Anatomist()
    wins = []
    for anaWinRow in anaWinMatrix:
      for w in anaWinRow:
        if (w is not None):
          wins.append(w)

    a.linkWindows(wins, group=None)
    a.execute('WindowConfig', windows=wins, linkedcursor_on_slider_change=1)


  @staticmethod
  def _linkAnatomistWindows_byRow(anaWinMatrix):
    a = ana.Anatomist()
    for anaWinRow in anaWinMatrix:
      wins = []
      for w in anaWinRow:
        if (w is not None):
          wins.append(w)

      a.linkWindows(wins, group=None)
      a.execute('WindowConfig', windows=wins, linkedcursor_on_slider_change=1)  

  @staticmethod
  def _linkAnatomistWindows_bySpace(anaWinMatrix, spaceNames):
    a = ana.Anatomist()
    winsDico = {}
    for anaWinRow, spaceName in zip(anaWinMatrix, spaceNames):
      isRawSpace = spaceName.lower().count('raw') != 0
      if (isRawSpace is False): # inutile de lier les fenetres si leur images sont des raw, donc dans leur propre espace. Par exemple, ne pas lier la pet avec l'irm
        keySpace = DisplayTitledGrid._convertSpaceName_to_key(spaceName)
        for w in anaWinRow:
          if (w is not None):
            if (winsDico.has_key(keySpace)):
              prevWins = winsDico[keySpace]
              prevWins.append(w)
              winsDico.update({keySpace:prevWins})
            else:
              winsDico.update({keySpace:[w]})

    for _k, wins in winsDico.items():
      a.linkWindows(wins, group=None)
      a.execute('WindowConfig', windows=wins, linkedcursor_on_slider_change=1)

  @staticmethod
  def _convertSpaceName_to_key(spaceName):
    isMRISpace = spaceName.lower().count('mri') > 0
    isPETSpace = spaceName.lower().count('pet') > 0
    isMNISpace = spaceName.lower().count('mni') > 0
    keySpace = spaceName
    if (isMRISpace):
      keySpace = 'mri'
    elif (isPETSpace):
      keySpace = 'pet'
    elif (isMNISpace):
      keySpace = 'mni'
    return keySpace

  def _onComboBox_changed(self):
    for anaWinRow in self.mw.anaWinMatrix:
      for w in anaWinRow:
        if(w is not None):
          if(self.mw.comboBox.currentText() == 'Axial'):
            w.muteAxial()
          elif(self.mw.comboBox.currentText() == 'Sagittal'):
            w.muteSagittal()
          elif(self.mw.comboBox.currentText() == 'Coronal'):
            w.muteCoronal()

  def _loadOverlayImages(self, overlaidImages):
    a = ana.Anatomist()
    images = []
    for filename in overlaidImages:
      if filename: # may be None to leave an un-overlayed row
        image = a.loadObject(filename)
        images.append(image)
        image.setPalette(palette=self._overlay_colormap)
      else: # None
        images.append(None)
    self._overlaid_images = images

  def _createOverlayFusions(self):
    if len(self._overlaid_images) == 0:
      # no overlays, nothing to be done.
      return

    matriceFusions = []
    for row, objRow in enumerate(self.anatomistObjectList):
      if row >= len(self._overlaid_images):
        overlayimage = self._overlaid_images[-1]
      else:
        overlayimage = self._overlaid_images[row]
      rowFusions=self._createFusionsWithOverlay(objRow, overlayimage)
      matriceFusions.append(rowFusions)
    self._overlay_fusions = matriceFusions

  def _createCustomOverlayFusions(self, row, column):
    if row >= 0 and column >= 0:
      overlayimage = self.anatomistObjectList[ row ][ column ]
      if overlayimage is not None:
        newoverlay = self._setPaletteOfOverlay(overlayimage)
        rowFusions=self._createFusionsWithOverlay(self.anatomistObjectList[row], newoverlay)    
        if len(self._custom_overlay_fusions) <= row:
          self._custom_overlay_fusions.extend([[]] * (row + 1 - len(self._custom_overlay_fusions)))
        self._custom_overlay_fusions[row] = rowFusions
        a = ana.Anatomist()
        a.execute('TexturingParams', objects=[x for x in rowFusions if x], texture_index=1, rate=float(self.mw.mixingSlider.value()) / 100)
      elif(row < len(self._custom_overlay_fusions)):
          self._custom_overlay_fusions[ row ] = None

  def _createFusionsWithOverlay(self, objects, overlayimage):
    a = ana.Anatomist()
    rowFusions=[]
    for obj in objects:
      if obj and overlayimage:
        fusion = a.fusionObjects(objects=[obj, overlayimage], method='Fusion2DMethod')
        rowFusions.append(fusion)
      else:
        rowFusions.append(None)
    return rowFusions
              
  def _setPaletteOfOverlay(self, overlayimage):
    a = ana.Anatomist()
    if (self._custom_overlay_colormap is not None):
      newoverlay = a.duplicateObject(overlayimage)
      newoverlay.setPalette(self._custom_overlay_colormap)
    else:
      newoverlay = overlayimage
      overlayimagepalette = overlayimage.palette().refPalette()
      paletteName = overlayimagepalette.name()
      newoverlay.setPalette(paletteName)
    return newoverlay
  
  def _addObjectOrFusion_inAnatomistWindows(self):
    for row, _anaWinRow in enumerate(self.mw.anaWinMatrix):
      if row < len(self._overlay_fusions):
        fusRow = self._overlay_fusions[ row ]
        self._addObjectOrFusion_inAnatomistWindowsRow(row, fusRow)

  def _addObjectOrFusion_inAnatomistWindowsRow(self, rowIndex, rowFusions): # rowFusions can be self._overlay_fusions or self._custom_overlay_fusions
    if(rowIndex>=0):
      anaWinRow = self.mw.anaWinMatrix[ rowIndex ]
      objRow = self.anatomistObjectList[ rowIndex ]
      for col, win in enumerate(anaWinRow):
        if win:
          if win.objects:
            win.removeObjects(win.objects)
          if rowFusions and rowFusions[ col ]:
            win.addObjects(rowFusions[ col ])
          elif objRow and objRow[ col ]:
            win.addObjects(objRow[ col ])

  def _removeCustomOverlays(self, row):
    self._custom_overlay_fusions[ row ] = []
    self._addObjectOrFusion_inAnatomistWindowsRow(row, self._overlay_fusions[ row ])

  def _onMixingRateChanged(self, value):
    self.mw.mixRate.setText(str(value) + ' %')
    a = ana.Anatomist()
    objects = []
    for fusRow in self._overlay_fusions:
      if(fusRow):
        objects.extend([ x for x in fusRow if x ])
    for fusRow in self._custom_overlay_fusions:
      if(fusRow):
        objects.extend([ x for x in fusRow if x ])
    a.execute('TexturingParams', objects=objects, texture_index=1,
      rate=float(value) / 100)

  def _removeWinFrame( self, row, column ):
    if row >= 0 and row < len( self.mw.anaWinMatrix ) and column >= 0:
      winrow = self.mw.anaWinMatrix[row]
      if column < len( winrow ):
        anatomistWindow = winrow[column]
        if(anatomistWindow.parent()):
          anatomistWindow.parent().setStyleSheet('QFrame#winborder { border: 0px; }') # momoTODO : il n'y a pas de parent!

  def _highlightWinFrame( self, row, column ):
    if row >= 0 and row < len( self.mw.anaWinMatrix ) and column >= 0:
      winrow = self.mw.anaWinMatrix[row]
      if column < len( winrow ):
        winrow[column].parent().setStyleSheet('QFrame#winborder { border: 2px solid #ffa000; border-radius: 4px; }')

  def _onColumnButtonClicked(self, column):
    oldcolumn = self._selectedColumn
    self._selectedColumn = column
    row = self.rowsButtonGroup.checkedId()
    self._removeWinFrame( row, oldcolumn )
    self._createCustomOverlayFusions(row, column)
    if(0<=row and row < len(self._custom_overlay_fusions)):
      self._addObjectOrFusion_inAnatomistWindowsRow(row, self._custom_overlay_fusions[ row ])
      self._highlightWinFrame( row, column )
    self._updatePalette()
    self._updateSelectedImageLabel()

  def _onRowButtonClicked(self, row):
    self._createCustomOverlayFusions(row, self._selectedColumn)
    self._addObjectOrFusion_inAnatomistWindowsRow(self._selectedRow, self._selectRowForFusions(self._selectedRow, thisRowIsSelected=False))# reset previous selectedRow
    self._removeWinFrame( self._selectedRow, self._selectedColumn )
    isRowUnselected = self._selectedRow == row
    if (isRowUnselected):
      self._unselectRowForFusion(row)
    else:
      self._addObjectOrFusion_inAnatomistWindowsRow(row, self._selectRowForFusions(row))
      self._highlightWinFrame( row, self._selectedColumn )
    self._updatePalette()
    self._updateSelectedImageLabel()

  def _updatePalette(self):
    if (self._selectedColumn >= 0 and self._selectedRow >= 0):
      if (self._paletteEditor is not None):
        self._paletteEditor.close()
      selectedImage = self.anatomistObjectList[self._selectedRow][self._selectedColumn]
      if(selectedImage is not None):
        self._paletteEditor = PaletteEditor(selectedImage, parent=self.mw, real_max=10000, sliderPrecision=10000, zoom=1)
        self.mw.horizontalLayout.insertWidget(2, self._paletteEditor)
  
  def _updateSelectedImageLabel(self):
    if (self._selectedColumn >= 0 and self._selectedRow >= 0):
      self.mw.selectedImageLabel.setText('<b>'+self._col_titles[self._selectedColumn]+'_'+self._row_titles[self._selectedRow]+'</b>')
    else:
      self.mw.selectedImageLabel.setText('None')
    
  def _unselectRowForFusion(self, row):    
    self._selectedRow = -1
    self._unselectButtonInGroup(self.rowsButtonGroup, row)
#    button.setText(self._row_titles[self._selectedRow])# momoTODO : pas besoin de changer le text si c'est un radio bouton. Le text peut contenir une information d'espace (mni, mri...) à ne pas mélanger avec la fusion

  def _unselectButtonInGroup(self, group, buttonId):
    if(buttonId>=0):
      button = group.button(buttonId)
      group.setExclusive(False)
      button.setChecked(False)
      group.setExclusive(True)
    
  def _selectRowForFusions(self, row, thisRowIsSelected = True):
    self._selectedRow = row
    fusions = None
    isCustomFusionsExist = len(self._custom_overlay_fusions)>0 and len(self._custom_overlay_fusions) > self._selectedRow
    isFusionsExist = len(self._overlay_fusions)>0 and len(self._overlay_fusions) > self._selectedRow
    if isCustomFusionsExist and thisRowIsSelected:
        fusions = self._custom_overlay_fusions[self._selectedRow]
    elif isFusionsExist:
        fusions = self._overlay_fusions[self._selectedRow]
    return fusions

  def _onMaximizeButtonClicked(self):
    print "_onMaximizeButtonClicked"# momoTODO utiliser display fusion et afficher la fusion de tous les objets de la ligne sélectionnée
  
# momoTODO : encadrer la reference utiliser pour la fusion    
#    painter = QPainter(mw)
#    painter.setPen(Qt.QColor('yellow'))
#    cellRect = mw.gridLayout.cellRect (rowIndex + 1, c + 1 )
#    cellRectWidth = cellRect.width()
#    cellRect.setWidth(cellRectWidth+200)
#    painter.fillRect(cellRect, Qt.QColor('yellow'))
#    painter.drawRect(cellRect)
