# Built-in
import os
import logging
import threading
from functools import partial
import math

# Third-party
import numpy
from PyQt4 import uic
from PyQt4.QtCore import Qt, pyqtSlot
from PyQt4.QtGui import QMessageBox, QColor, QShortcut, QKeySequence, QPushButton, QWidget, QIcon,QApplication

# HCI
from lazyflow.utility import traceLogged
from volumina.api import LazyflowSource, AlphaModulatedLayer, ColortableLayer, LazyflowSinkSource
from volumina.utility import ShortcutManager
from ilastik.widgets.labelListView import Label
from ilastik.widgets.boxListModel import BoxListModel,BoxLabel
from ilastik.widgets.labelListModel import LabelListModel
from lazyflow.rtype import SubRegion
from volumina.navigationControler import NavigationInterpreter

# ilastik
from ilastik.utility import bind
from ilastik.utility.gui import threadRouted
from ilastik.shell.gui.iconMgr import ilastikIcons
from ilastik.applets.labeling.labelingGui import LabelingGui
from ilastik.applets.base.applet import ShellRequest
from lazyflow.operators.adaptors import Op5ifyer
from ilastik.applets.counting.countingGuiDotsInterface import DotCrosshairController,DotInterpreter, DotController
from ilastik.applets.base.appletSerializer import SerialListSlot



try:
    from volumina.view.volumeRendering import RenderingManager
except:
    pass

# Loggers
logger = logging.getLogger(__name__)
traceLogger = logging.getLogger('TRACE.' + __name__)

def _listReplace(old, new):
    if len(old) > len(new):
        return new + old[len(new):]
    else:
        return new




from PyQt4.QtCore import QObject, QRect, QSize, pyqtSignal, QEvent, QPoint,QString,QVariant
from PyQt4.QtGui import QRubberBand,QRubberBand,qRed,QPalette,QBrush,QColor,QGraphicsColorizeEffect,\
        QStylePainter, QPen

from countingGuiBoxesInterface import BoxController,BoxInterpreter,Tool

class CallToGui:
    def __init__(self,opslot,setfun):
        '''
        Helper class which registers a simple callback between an operator and a gui
        element so that gui elements can be kept in sync across different images
        :param opslot:
        :param setfun:
        :param defaultval:

        '''

        self.val=None
        self.opslot=opslot
        self.setfun=setfun
        self._exec()
        self.opslot.notifyDirty(bind(self._exec))

    def _exec(self):
        if self.opslot.ready():
            self.val=self.opslot.value

        if self.val!=None:
            #FXIME: workaround for recently introduced bug when setting
            #sigma box as spindoublebox
            if type(self.val)==list:
                val=self.val[0]
            else:
                val=self.val
            self.setfun(val)

class CountingGui(LabelingGui):

    ###########################################
    ### AppletGuiInterface Concrete Methods ###
    ###########################################
    def centralWidget( self ):
        return self

    def stopAndCleanUp(self):
        # Base class first
        super(CountingGui, self).stopAndCleanUp()

        # Ensure that we are NOT in interactive mode
        self.labelingDrawerUi.liveUpdateButton.setChecked(False)
        self._viewerControlUi.checkShowPredictions.setChecked(False)
        self._viewerControlUi.checkShowSegmentation.setChecked(False)
        self.toggleInteractive(False)

    def viewerControlWidget(self):
        return self._viewerControlUi

    ###########################################
    ###########################################

    @traceLogged(traceLogger)
    def __init__(self, parentApplet, topLevelOperatorView):

        # Tell our base class which slots to monitor
        labelSlots = LabelingGui.LabelingSlots()
        labelSlots.labelInput = topLevelOperatorView.LabelInputs
        labelSlots.labelOutput = topLevelOperatorView.LabelImages
        labelSlots.labelEraserValue = topLevelOperatorView.opLabelPipeline.opLabelArray.eraser
        labelSlots.labelDelete = topLevelOperatorView.opLabelPipeline.opLabelArray.deleteLabel
        labelSlots.maxLabelValue = topLevelOperatorView.MaxLabelValue
        labelSlots.labelsAllowed = topLevelOperatorView.LabelsAllowedFlags
        labelSlots.LabelNames = topLevelOperatorView.LabelNames

        # We provide our own UI file (which adds an extra control for interactive mode)
        labelingDrawerUiPath = os.path.split(__file__)[0] + '/countingDrawer.ui'

        # Base class init
        super(CountingGui, self).__init__(parentApplet, labelSlots, topLevelOperatorView, labelingDrawerUiPath )

        self.op = topLevelOperatorView

        self.topLevelOperatorView = topLevelOperatorView
        self.shellRequestSignal = parentApplet.shellRequestSignal
        self.predictionSerializer = parentApplet.predictionSerializer

        self.interactiveModeActive = False
        self._currentlySavingPredictions = False

        self.labelingDrawerUi.savePredictionsButton.clicked.connect(self.onSavePredictionsButtonClicked)
        self.labelingDrawerUi.savePredictionsButton.setIcon( QIcon(ilastikIcons.Save) )

        self.labelingDrawerUi.liveUpdateButton.setEnabled(False)
        self.labelingDrawerUi.liveUpdateButton.setIcon( QIcon(ilastikIcons.Play) )
        self.labelingDrawerUi.liveUpdateButton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.labelingDrawerUi.liveUpdateButton.toggled.connect( self.toggleInteractive )
        self.topLevelOperatorView.MaxLabelValue.notifyDirty( bind(self.handleLabelSelectionChange) )
        self._initShortcuts()

        try:
            self.render = True
            self._renderedLayers = {} # (layer name, label number)
            self._renderMgr = RenderingManager(
                renderer=self.editor.view.qvtk.renderer,
                qvtk=self.editor.view.qvtk)
        except:
            self.render = False


        self.initCounting()
        try:
            from sitecustomize import debug_trace
        except:
            self.labelingDrawerUi.DebugButton.setVisible(False)





    def initCounting(self):

        #=======================================================================
        # Init Dotting interface
        #=======================================================================


        self.dotcrosshairController=DotCrosshairController(self.editor.brushingModel,self.editor.imageViews)
        self.editor.crosshairControler=self.dotcrosshairController
        #self.dotController=DotController(self.editor.imageScenes[2],self.editor.brushingControler)
        self.editor.brushingInterpreter = DotInterpreter(self.editor.navCtrl,self.editor.brushingControler)
        self.dotInterpreter=self.editor.brushingInterpreter


        #=======================================================================
        # Init Label Control Ui Custom  setup
        #=======================================================================

        self._viewerControlUi.label.setVisible(False)
        self._viewerControlUi.checkShowPredictions.setVisible(False)
        self._viewerControlUi.checkShowSegmentation.setVisible(False)



        self._addNewLabel()
        self._addNewLabel()
        self._labelControlUi.brushSizeComboBox.setEnabled(False)
        self._labelControlUi.brushSizeCaption.setEnabled(False)
        self.selectLabel(0)



        #=======================================================================
        # Init labeling Drawer Ui Custom  setup
        #=======================================================================


        #labels for foreground and background
        self.labelingDrawerUi.labelListModel.makeRowPermanent(0)
        self.labelingDrawerUi.labelListModel.makeRowPermanent(1)
        self.labelingDrawerUi.labelListModel[0].name = "Foreground"
        self.labelingDrawerUi.labelListModel[1].name = "Background"
        self.labelingDrawerUi.labelListView.shrinkToMinimum()

        self.labelingDrawerUi.CountText.setReadOnly(True)



        #=======================================================================
        # Init Boxes Interface
        #=======================================================================

        #if not hasattr(self._labelControlUi, "boxListModel"):
        self.labelingDrawerUi.boxListModel=BoxListModel()
        self.labelingDrawerUi.boxListView.setModel(self.labelingDrawerUi.boxListModel)
        self.labelingDrawerUi.boxListModel.elementSelected.connect(self._onBoxSelected)
        #self.labelingDrawerUi.boxListModel.boxRemoved.connect(self._removeBox)

#        ###FIXME: Only for debug
        #self.op.Density.notifyDirty(self.updateSum)
        self.labelingDrawerUi.DensityButton.clicked.connect(self.updateSum)

        mainwin=self
        self.density5d=Op5ifyer(graph=self.op.graph, parent=self.op.parent) #FIXME: Hack , get the proper reference to the graph
        self.density5d.input.connect(self.op.Density)
        self.boxController=BoxController(mainwin.editor.imageScenes[2],self.density5d.output,self.labelingDrawerUi.boxListModel)
        self.boxInterpreter=BoxInterpreter(mainwin.editor.navInterpret,mainwin.editor.posModel,self.boxController,mainwin.centralWidget())


        self.navigationInterpreterDefault=self.editor.navInterpret

        self.boxController.fixedBoxesChanged.connect(self._handleBoxConstraints)

        self._setUIParameters()
        self._connectUIParameters()



        self.op.LabelPreviewer.Sigma.setValue(self.op.opTrain.Sigma.value)
        self.op.opTrain.fixClassifier.setValue(False)
        self.op.Density.notifyDirty(self._normalizePrediction)



    def _connectUIParameters(self):

        #=======================================================================
        # Gui to operator connections
        #=======================================================================

        #Debug interface only available to advanced users
        self.labelingDrawerUi.DebugButton.pressed.connect(self._debug)
        self.labelingDrawerUi.boxListView.resetEmptyMessage("no boxes defined yet")
        self.labelingDrawerUi.SVROptions.currentIndexChanged.connect(self._updateSVROptions)
        self.labelingDrawerUi.CBox.valueChanged.connect(self._updateC)


        self.labelingDrawerUi.SigmaBox.valueChanged.connect(self._updateSigma)
        self.labelingDrawerUi.EpsilonBox.valueChanged.connect(self._updateEpsilon)
        self.labelingDrawerUi.MaxDepthBox.valueChanged.connect(self._updateMaxDepth)
        self.labelingDrawerUi.NtreesBox.valueChanged.connect(self._updateNtrees)

        #=======================================================================
        # Operators to Gui connections
        #=======================================================================

        self._registerOperatorsToGuiCallbacks()

        #=======================================================================
        # Initialize Values
        #=======================================================================

        self._updateSigma()
        self._updateNtrees()
        self._updateMaxDepth()

    def _registerOperatorsToGuiCallbacks(self):

        op=self.op.opTrain
        gui=self.labelingDrawerUi

        CallToGui(op.Ntrees,gui.NtreesBox.setValue)
        CallToGui(op.MaxDepth,gui.MaxDepthBox.setValue)
        CallToGui(op.C,gui.CBox.setValue)
        CallToGui(op.Sigma,gui.SigmaBox.setValue)
        CallToGui(op.Epsilon,gui.EpsilonBox.setValue)

        def _setoption(option):
            index=gui.SVROptions.findText(option)
            gui.SVROptions.setCurrentIndex(index)

        CallToGui(op.SelectedOption,_setoption)
        idx = self.op.current_view_index()
        op = self.op.opTrain
        fix = op.fixClassifier.value
        op.fixClassifier.setValue(True)

        if op.BoxConstraintRois.ready() and len(op.BoxConstraintRois[idx].value) > 0:
            #if fixed boxes are existent, make column visible
            self.labelingDrawerUi.boxListView._table.setColumnHidden(self.boxController.boxListModel.ColumnID.Fix, False)
            for i, constr in enumerate(zip(op.BoxConstraintRois[idx].value, op.BoxConstraintValues[idx].value)):
                roi, val = constr
                if type(roi) is not list or len(roi) is not 2:
                    continue
                self.boxController.addNewBox(roi[0], roi[1])
                boxIndex = self.boxController.boxListModel.index(i, self.boxController.boxListModel.ColumnID.Fix)
                iconIndex = self.boxController.boxListModel.index(i, self.boxController.boxListModel.ColumnID.FixIcon)
                self.boxController.boxListModel.setData(boxIndex,QVariant(val))
        op.fixClassifier.setValue(fix)



    def _setUIParameters(self):

        self.labelingDrawerUi.SigmaBox.setKeyboardTracking(False)
        self.labelingDrawerUi.CBox.setRange(0,1000)
        self.labelingDrawerUi.CBox.setKeyboardTracking(False)
        self.labelingDrawerUi.EpsilonBox.setKeyboardTracking(False)
        self.labelingDrawerUi.EpsilonBox.setDecimals(6)
        self.labelingDrawerUi.NtreesBox.setKeyboardTracking(False)
        self.labelingDrawerUi.MaxDepthBox.setKeyboardTracking(False)

        for option in self.op.options:
            if "req" in option.keys():
                try:
                    import importlib
                    for req in option["req"]:
                        importlib.import_module(req)
                except:
                    continue
            #values=[v for k,v in option.items() if k not in ["gui", "req"]]
            self.labelingDrawerUi.SVROptions.addItem(option["method"], (option,))



        if self.op.classifier_cache._value and len(self.op.classifier_cache._value) > 0:
            #use parameters from cached classifier
            params = self.op.classifier_cache.Output.value[0].get_params()
            Sigma = params["Sigma"]
            Epsilon = params["epsilon"]
            C = params["C"]
            Ntrees = params["ntrees"]
            MaxDepth = params["maxdepth"]
            _ind = self.labelingDrawerUi.SVROptions.findText(params["method"])

            #set opTrain from parameters
            self.op.opTrain.initInputs(params)



        else:
            #read parameters from opTrain Operator
            Sigma = self.op.opTrain.Sigma.value
            Epsilon = self.op.opTrain.Epsilon.value
            C = self.op.opTrain.C.value
            Ntrees = self.op.opTrain.Ntrees.value
            MaxDepth = self.op.opTrain.MaxDepth.value
            _ind = self.labelingDrawerUi.SVROptions.findText(self.op.opTrain.SelectedOption.value)

        #FIXME: quick fix recently introduced bug

        if type(Sigma)==list:
            Sigma=Sigma[0]
        self.labelingDrawerUi.SigmaBox.setValue(Sigma)
        self.labelingDrawerUi.EpsilonBox.setValue(Epsilon)
        self.labelingDrawerUi.CBox.setValue(C)
        self.labelingDrawerUi.NtreesBox.setValue(Ntrees)
        self.labelingDrawerUi.MaxDepthBox.setValue(MaxDepth)
        if _ind == -1:
            self.labelingDrawerUi.SVROptions.setCurrentIndex(0)
            self._updateSVROptions()
        else:
            self.labelingDrawerUi.SVROptions.setCurrentIndex(_ind)

        self._hideParameters()



    def _updateMaxDepth(self):
        self.op.opTrain.MaxDepth.setValue(self.labelingDrawerUi.MaxDepthBox.value())
    def _updateNtrees(self):
        self.op.opTrain.Ntrees.setValue(self.labelingDrawerUi.NtreesBox.value())

    def _hideParameters(self):
        _ind = self.labelingDrawerUi.SVROptions.currentIndex()
        option = self.labelingDrawerUi.SVROptions.itemData(_ind).toPyObject()[0]
        if "svr" not in option["gui"]:
            self.labelingDrawerUi.gridLayout_2.setVisible(False)
        else:
            self.labelingDrawerUi.gridLayout_2.setVisible(True)


        if "rf" not in option["gui"]:
            self.labelingDrawerUi.rf_panel.setVisible(False)
        else:
            self.labelingDrawerUi.rf_panel.setVisible(True)


    #def _updateOverMult(self):
    #    self.op.opTrain.OverMult.setValue(self.labelingDrawerUi.OverBox.value())
    #def _updateUnderMult(self):
    #    self.op.opTrain.UnderMult.setValue(self.labelingDrawerUi.UnderBox.value())
    def _updateC(self):
        self.op.opTrain.C.setValue(self.labelingDrawerUi.CBox.value())
    def _updateSigma(self):
        #if self._changedSigma:

        sigma,_ = self._normalizeLayers()
        self.editor.crosshairControler.setSigma(sigma)
        #2 * the maximal value of a gaussian filter, to allow some leeway for overlapping
        self.op.opTrain.Sigma.setValue(sigma)
        self.op.LabelPreviewer.Sigma.setValue(sigma)
        #    self._changedSigma = False

    def _normalizeLayers(self):
            sigma = self._labelControlUi.SigmaBox.value()
            upperBound = 3 / (2 * math.pi * sigma**2)
            self.upperBound = upperBound

            if hasattr(self, "labelPreviewLayer"):
                self.labelPreviewLayer.set_normalize(0,(0,upperBound))
            return sigma, upperBound


    def _normalizePrediction(self, *args):
        if hasattr(self, "predictionLayer") and hasattr(self, "upperBound"):
            self.predictionLayer.set_normalize(0,(0,self.upperBound))


    def _updateEpsilon(self):
        self.op.opTrain.Epsilon.setValue(self.labelingDrawerUi.EpsilonBox.value())

    def _updateSVROptions(self):
        index = self.labelingDrawerUi.SVROptions.currentIndex()
        option = self.labelingDrawerUi.SVROptions.itemData(index).toPyObject()[0]
        self.op.opTrain.SelectedOption.setValue(option["method"])

        self._hideFixable(option)

        self._hideParameters()

    def _hideFixable(self,option):
        if 'boxes' in option and option['boxes'] == False:
            self.labelingDrawerUi.boxListView.allowFixIcon=False
            self.labelingDrawerUi.boxListView.allowFixValues=False
        elif 'boxes' in option and option['boxes'] == True:
            self.labelingDrawerUi.boxListView.allowFixIcon=True



    def _handleBoxConstraints(self, constr):
        opTrain = self.op.opTrain
        id = self.op.current_view_index()
        vals = constr["values"]
        rois = constr["rois"]
        fixedClassifier = opTrain.fixClassifier.value
        assert len(vals) == len(rois)
        if opTrain.BoxConstraintRois.ready() and opTrain.BoxConstraintValues.ready():
            if opTrain.BoxConstraintValues[id].value != vals and opTrain.BoxConstraintRois[id].value != rois:
                opTrain.fixClassifier.setValue(True)
                opTrain.BoxConstraintRois[id].setValue(rois)
                opTrain.fixClassifier.setValue(fixedClassifier)
                opTrain.BoxConstraintValues[id].setValue(vals)

        #boxes = self.boxController._currentBoxesList


    def _debug(self):
        import sitecustomize
        sitecustomize.debug_trace()



    @traceLogged(traceLogger)
    def initViewerControlUi(self):
        localDir = os.path.split(__file__)[0]
        self._viewerControlUi = uic.loadUi( os.path.join( localDir, "viewerControls.ui" ) )

        # Connect checkboxes
        def nextCheckState(checkbox):
            checkbox.setChecked( not checkbox.isChecked() )

        self._viewerControlUi.checkShowPredictions.clicked.connect( self.handleShowPredictionsClicked )
        self._viewerControlUi.checkShowSegmentation.clicked.connect( self.handleShowSegmentationClicked )

        # The editor's layerstack is in charge of which layer movement buttons are enabled
        model = self.editor.layerStack
        self._viewerControlUi.viewerControls.setupConnections(model)

    def _initShortcuts(self):
        mgr = ShortcutManager()
        shortcutGroupName = "Predictions"

        togglePredictions = QShortcut( QKeySequence("p"), self, member=self._viewerControlUi.checkShowPredictions.click )
        mgr.register( shortcutGroupName,
                      "Toggle Prediction Layer Visibility",
                      togglePredictions,
                      self._viewerControlUi.checkShowPredictions )

        toggleSegmentation = QShortcut( QKeySequence("s"), self, member=self._viewerControlUi.checkShowSegmentation.click )
        mgr.register( shortcutGroupName,
                      "Toggle Segmentaton Layer Visibility",
                      toggleSegmentation,
                      self._viewerControlUi.checkShowSegmentation )

        toggleLivePredict = QShortcut( QKeySequence("l"), self, member=self.labelingDrawerUi.liveUpdateButton.toggle )
        mgr.register( shortcutGroupName,
                      "Toggle Live Prediction Mode",
                      toggleLivePredict,
                      self.labelingDrawerUi.liveUpdateButton )

    def _setup_contexts(self, layer):
        def callback(pos, clayer=layer):
            name = clayer.name
            if name in self._renderedLayers:
                label = self._renderedLayers.pop(name)
                self._renderMgr.removeObject(label)
                self._update_rendering()
            else:
                label = self._renderMgr.addObject()
                self._renderedLayers[clayer.name] = label
                self._update_rendering()

        if self.render:
            layer.contexts.append(('Toggle 3D rendering', callback))

    @traceLogged(traceLogger)
    def setupLayers(self):
        """
        Called by our base class when one of our data slots has changed.
        This function creates a layer for each slot we want displayed in the volume editor.
        """
        # Base class provides the label layer.
        layers = super(CountingGui, self).setupLayers()

        # Add each of the predictions
        labels = self.labelListData



        slots = {'Prediction' : self.op.Density, 'LabelPreview': self.op.LabelPreview, 'Uncertainty' :
                 self.op.UncertaintyEstimate}

        for name, slot in slots.items():
            if slot.ready():
                from volumina import colortables
                sigma,upperBound = self._normalizeLayers()
                layer = ColortableLayer(LazyflowSource(slot), colorTable = countingColorTable, normalize =
                                       (0,upperBound))
                layer.name = name
                layer.visible = self.labelingDrawerUi.liveUpdateButton.isChecked()
                #layer.visibleChanged.connect(self.updateShowPredictionCheckbox)
                layers.append(layer)


        #Set LabelPreview-layer to True

        boxlabelsrc = LazyflowSinkSource(self.op.BoxLabelImages,self.op.BoxLabelInputs )
        boxlabellayer = ColortableLayer(boxlabelsrc, colorTable = self._colorTable16, direct = False)
        boxlabellayer.name = "Boxes"
        boxlabellayer.opacity = 1.0
        boxlabellayer.visibleChanged.connect(self.boxController.changeBoxesVisibility)
        boxlabellayer.opacityChanged.connect(self.boxController.changeBoxesOpacity)





        layers.append(boxlabellayer)
        self.boxlabelsrc = boxlabelsrc


        inputDataSlot = self.topLevelOperatorView.InputImages
        if inputDataSlot.ready():
            inputLayer = self.createStandardLayerFromSlot( inputDataSlot )
            inputLayer.name = "Input Data"
            inputLayer.visible = True
            inputLayer.opacity = 1.0

            def toggleTopToBottom():
                index = self.layerstack.layerIndex( inputLayer )
                self.layerstack.selectRow( index )
                if index == 0:
                    self.layerstack.moveSelectedToBottom()
                else:
                    self.layerstack.moveSelectedToTop()

            inputLayer.shortcutRegistration = (
                "Prediction Layers",
                "Bring Input To Top/Bottom",
                QShortcut( QKeySequence("i"), self.viewerControlWidget(), toggleTopToBottom),
                inputLayer )
            layers.append(inputLayer)

        self.handleLabelSelectionChange()
        return layers




    @traceLogged(traceLogger)
    def toggleInteractive(self, checked):
        """
        If enable
        """
        logger.debug("toggling interactive mode to '%r'" % checked)

        if checked==True:
            if not self.topLevelOperatorView.FeatureImages.ready() \
            or self.topLevelOperatorView.FeatureImages.meta.shape==None:
                self.labelingDrawerUi.liveUpdateButton.setChecked(False)
                mexBox=QMessageBox()
                mexBox.setText("There are no features selected ")
                mexBox.exec_()
                return

        self.labelingDrawerUi.savePredictionsButton.setEnabled(not checked)
        self.topLevelOperatorView.FreezePredictions.setValue( not checked )

        # Auto-set the "show predictions" state according to what the user just clicked.
        if checked:
            self._viewerControlUi.checkShowPredictions.setChecked( True )
            self.handleShowPredictionsClicked()

        # If we're changing modes, enable/disable our controls and other applets accordingly
        if self.interactiveModeActive != checked:
            if checked:
                self.labelingDrawerUi.labelListView.allowDelete = False
                #self.labelingDrawerUi.AddLabelButton.setEnabled( False )
            else:
                self.labelingDrawerUi.labelListView.allowDelete = True
                #self.labelingDrawerUi.AddLabelButton.setEnabled( True )
        self.interactiveModeActive = checked


    @traceLogged(traceLogger)
    def updateAllLayers(self, slot=None):
        super(CountingGui, self).updateAllLayers()
        for layer in self.layerstack:
            if layer.name == "LabelPreview":
                layer.visible = True
                self.labelPreviewLayer = layer
            if layer.name == "Prediction":
                self.predictionLayer = layer



    @pyqtSlot()
    @traceLogged(traceLogger)
    def handleShowPredictionsClicked(self):
        checked = self._viewerControlUi.checkShowPredictions.isChecked()
        for layer in self.layerstack:
            if "Prediction" in layer.name:
                layer.visible = checked

    @pyqtSlot()
    @traceLogged(traceLogger)
    def handleShowSegmentationClicked(self):
        checked = self._viewerControlUi.checkShowSegmentation.isChecked()
        for layer in self.layerstack:
            if "Segmentation" in layer.name:
                layer.visible = checked

    @pyqtSlot()
    @traceLogged(traceLogger)
    def updateShowPredictionCheckbox(self):
        predictLayerCount = 0
        visibleCount = 0
        for layer in self.layerstack:
            if "Prediction" in layer.name:
                predictLayerCount += 1
                if layer.visible:
                    visibleCount += 1

        if visibleCount == 0:
            self._viewerControlUi.checkShowPredictions.setCheckState(Qt.Unchecked)
        elif predictLayerCount == visibleCount:
            self._viewerControlUi.checkShowPredictions.setCheckState(Qt.Checked)
        else:
            self._viewerControlUi.checkShowPredictions.setCheckState(Qt.PartiallyChecked)

    @pyqtSlot()
    @traceLogged(traceLogger)
    def updateShowSegmentationCheckbox(self):
        segLayerCount = 0
        visibleCount = 0
        for layer in self.layerstack:
            if "Segmentation" in layer.name:
                segLayerCount += 1
                if layer.visible:
                    visibleCount += 1

        if visibleCount == 0:
            self._viewerControlUi.checkShowSegmentation.setCheckState(Qt.Unchecked)
        elif segLayerCount == visibleCount:
            self._viewerControlUi.checkShowSegmentation.setCheckState(Qt.Checked)
        else:
            self._viewerControlUi.checkShowSegmentation.setCheckState(Qt.PartiallyChecked)

    @pyqtSlot()
    @threadRouted
    @traceLogged(traceLogger)
    def handleLabelSelectionChange(self):
        enabled = False
        if self.topLevelOperatorView.MaxLabelValue.ready():
            enabled = True
            enabled &= self.topLevelOperatorView.MaxLabelValue.value >= 2
            enabled &= numpy.all(numpy.asarray(self.topLevelOperatorView.CachedFeatureImages.meta.shape) > 0)
            # FIXME: also check that each label has scribbles?

        self.labelingDrawerUi.savePredictionsButton.setEnabled(enabled)
        self.labelingDrawerUi.liveUpdateButton.setEnabled(enabled)
        self._viewerControlUi.checkShowPredictions.setEnabled(enabled)
        self._viewerControlUi.checkShowSegmentation.setEnabled(enabled)

    @pyqtSlot()
    @traceLogged(traceLogger)
    def onSavePredictionsButtonClicked(self):
        """
        The user clicked "Train and Predict".
        Handle this event by asking the topLevelOperatorView for a prediction over the entire output region.
        """
        import warnings
        warnings.warn("FIXME: Remove this function and just use the data export applet.")
        # The button does double-duty as a cancel button while predictions are being stored
        if self._currentlySavingPredictions:
            self.predictionSerializer.cancel()
        else:
            # Compute new predictions as needed
            predictionsFrozen = self.topLevelOperatorView.FreezePredictions.value
            self.topLevelOperatorView.FreezePredictions.setValue(False)
            self._currentlySavingPredictions = True

            originalButtonText = "Full Volume Predict and Save"
            self.labelingDrawerUi.savePredictionsButton.setText("Cancel Full Predict")

            @traceLogged(traceLogger)
            def saveThreadFunc():
                logger.info("Starting full volume save...")
                # Disable all other applets
                def disableAllInWidgetButName(widget, exceptName):
                    for child in widget.children():
                        if child.findChild( QPushButton, exceptName) is None:
                            child.setEnabled(False)
                        else:
                            disableAllInWidgetButName(child, exceptName)

                # Disable everything in our drawer *except* the cancel button
                disableAllInWidgetButName(self.labelingDrawerUi, "savePredictionsButton")

                # But allow the user to cancel the save
                self.labelingDrawerUi.savePredictionsButton.setEnabled(True)

                # First, do a regular save.
                # During a regular save, predictions are not saved to the project file.
                # (It takes too much time if the user only needs the classifier.)
                self.shellRequestSignal.emit( ShellRequest.RequestSave )

                # Enable prediction storage and ask the shell to save the project again.
                # (This way the second save will occupy the whole progress bar.)
                self.predictionSerializer.predictionStorageEnabled = True
                self.shellRequestSignal.emit( ShellRequest.RequestSave )
                self.predictionSerializer.predictionStorageEnabled = False

                # Restore original states (must use events for UI calls)
                self.thunkEventHandler.post(self.labelingDrawerUi.savePredictionsButton.setText, originalButtonText)
                self.topLevelOperatorView.FreezePredictions.setValue(predictionsFrozen)
                self._currentlySavingPredictions = False

                # Re-enable our controls
                def enableAll(widget):
                    for child in widget.children():
                        if isinstance( child, QWidget ):
                            child.setEnabled(True)
                            enableAll(child)
                enableAll(self.labelingDrawerUi)

                # Re-enable all other applets
                logger.info("Finished full volume save.")

            saveThread = threading.Thread(target=saveThreadFunc)
            saveThread.start()

    def _getNext(self, slot, parentFun, transform=None):
        numLabels = self.labelListData.rowCount()
        value = slot.value
        if numLabels < len(value):
            result = value[numLabels]
            if transform is not None:
                result = transform(result)
            return result
        else:
            return parentFun()

    def _onLabelChanged(self, parentFun, mapf, slot):
        parentFun()
        new = map(mapf, self.labelListData)
        old = slot.value
        slot.setValue(_listReplace(old, new))

    def _onLabelRemoved(self, parent, start, end):
        super(CountingGui, self)._onLabelRemoved(parent, start, end)
        op = self.topLevelOperatorView
        for slot in (op.LabelNames, op.LabelColors, op.PmapColors):
            value = slot.value
            value.pop(start)
            slot.setValue(value)

    def getNextLabelName(self):
        return self._getNext(self.topLevelOperatorView.LabelNames,
                             super(CountingGui, self).getNextLabelName)

    def getNextLabelColor(self):
        return self._getNext(
            self.topLevelOperatorView.LabelColors,
            super(CountingGui, self).getNextLabelColor,
            lambda x: QColor(*x)
        )

    def getNextPmapColor(self):
        return self._getNext(
            self.topLevelOperatorView.PmapColors,
            super(CountingGui, self).getNextPmapColor,
            lambda x: QColor(*x)
        )

    def onLabelNameChanged(self):
        self._onLabelChanged(super(CountingGui, self).onLabelNameChanged,
                             lambda l: l.name,
                             self.topLevelOperatorView.LabelNames)

    def onLabelColorChanged(self):
        self._onLabelChanged(super(CountingGui, self).onLabelColorChanged,
                             lambda l: (l.brushColor().red(),
                                        l.brushColor().green(),
                                        l.brushColor().blue()),
                             self.topLevelOperatorView.LabelColors)


    def onPmapColorChanged(self):
        self._onLabelChanged(super(CountingGui, self).onPmapColorChanged,
                             lambda l: (l.pmapColor().red(),
                                        l.pmapColor().green(),
                                        l.pmapColor().blue()),
                             self.topLevelOperatorView.PmapColors)

    def _update_rendering(self):
        if not self.render:
            return
        shape = self.topLevelOperatorView.InputImages.meta.shape[1:4]
        time = self.editor._posModel.slicingPos5D[0]
        if not self._renderMgr.ready:
            self._renderMgr.setup(shape)

        layernames = set(layer.name for layer in self.layerstack)
        self._renderedLayers = dict((k, v) for k, v in self._renderedLayers.iteritems()
                                if k in layernames)

        newvolume = numpy.zeros(shape, dtype=numpy.uint8)
        for layer in self.layerstack:
            try:
                label = self._renderedLayers[layer.name]
            except KeyError:
                continue
            for ds in layer.datasources:
                vol = ds.dataSlot.value[time, ..., 0]
                indices = numpy.where(vol != 0)
                newvolume[indices] = label

        self._renderMgr.volume = newvolume
        self._update_colors()
        self._renderMgr.update()

    def _update_colors(self):
        for layer in self.layerstack:
            try:
                label = self._renderedLayers[layer.name]
            except KeyError:
                continue
            color = layer.tintColor
            color = (color.red(), color.green() , color.blue() )
            self._renderMgr.setColor(label, color)



    def _gui_setNavigation(self):
        self._labelControlUi.brushSizeComboBox.setEnabled(False)
        self._labelControlUi.brushSizeCaption.setEnabled(False)
        self._labelControlUi.arrowToolButton.setChecked(True)

    def _gui_setBrushing(self):
#         self._labelControlUi.brushSizeComboBox.setEnabled(False)
#         self._labelControlUi.brushSizeCaption.setEnabled(False)
        # Make sure the paint button is pressed
        self._labelControlUi.paintToolButton.setChecked(True)
        # Show the brush size control and set its caption
        self._labelControlUi.brushSizeCaption.setText("Size:")
        # Make sure the GUI reflects the correct size
        #self._labelControlUi.brushSizeComboBox.setCurrentIndex(0)

    def _gui_setBox(self):
        self._labelControlUi.brushSizeComboBox.setEnabled(False)
        self._labelControlUi.brushSizeCaption.setEnabled(False)
        self._labelControlUi.arrowToolButton.setChecked(False)

        #self._labelControlUi.boxToolButton.setChecked(True)


    def _onBoxChanged(self,parentFun, mapf):

        parentFun()
        new = map(mapf, self.labelListData)


    def _changeInteractionMode( self, toolId ):
        """
        Implement the GUI's response to the user selecting a new tool.
        """
        QApplication.restoreOverrideCursor()
        for v in self.editor.crosshairControler._imageViews:
                    v._crossHairCursor.enabled=True


        # Uncheck all the other buttons
        for tool, button in self.toolButtons.items():
            if tool != toolId:
                button.setChecked(False)

        # If we have no editor, we can't do anything yet
        if self.editor is None:
            return

        # The volume editor expects one of two specific names
        modeNames = { Tool.Navigation   : "navigation",
                      Tool.Paint        : "brushing",
                      Tool.Erase        : "brushing",
                      Tool.Box          : "navigation"
                    }

        # If the user can't label this image, disable the button and say why its disabled
        labelsAllowed = False

        labelsAllowedSlot = self._labelingSlots.labelsAllowed
        if labelsAllowedSlot.ready():
            labelsAllowed = labelsAllowedSlot.value

            if hasattr(self._labelControlUi, "AddLabelButton"):
                self._labelControlUi.AddLabelButton.setEnabled(labelsAllowed and self.maxLabelNumber > self._labelControlUi.labelListModel.rowCount())
                if labelsAllowed:
                    self._labelControlUi.AddLabelButton.setText("Add Label")
                else:
                    self._labelControlUi.AddLabelButton.setText("(Labeling Not Allowed)")

        e = labelsAllowed & (self._labelControlUi.labelListModel.rowCount() > 0)
        self._gui_enableLabeling(e)

        if labelsAllowed:
            # Update the applet bar caption
            if toolId == Tool.Navigation:
                # update GUI
                self.editor.brushingModel.setBrushSize(0)
                self.editor.setNavigationInterpreter(NavigationInterpreter(self.editor.navCtrl))
                self._gui_setNavigation()

            elif toolId == Tool.Paint:
                # If necessary, tell the brushing model to stop erasing
                if self.editor.brushingModel.erasing:
                    self.editor.brushingModel.disableErasing()
                # Set the brushing size

                if self.editor.brushingModel.drawnNumber==1:
                    brushSize = 1
                    self.editor.brushingModel.setBrushSize(brushSize)

                # update GUI
                self._gui_setBrushing()


            elif toolId == Tool.Erase:

                # If necessary, tell the brushing model to start erasing
                if not self.editor.brushingModel.erasing:
                    self.editor.brushingModel.setErasing()
                # Set the brushing size
                eraserSize = self.brushSizes[self.eraserSizeIndex]
                self.editor.brushingModel.setBrushSize(eraserSize)
                # update GUI
                self._gui_setErasing()

            elif toolId == Tool.Box:
                self._labelControlUi.labelListModel.clearSelectionModel()
                for v in self.editor.crosshairControler._imageViews:
                    v._crossHairCursor.enabled=False

                QApplication.setOverrideCursor(Qt.CrossCursor)
                self.editor.brushingModel.setBrushSize(0)
                self.editor.setNavigationInterpreter(self.boxInterpreter)
                self._gui_setBox()

        self.editor.setInteractionMode( modeNames[toolId] )
        self._toolId = toolId



    def _initLabelUic(self, drawerUiPath):
        super(CountingGui, self)._initLabelUic(drawerUiPath)
        #self._labelControlUi.boxToolButton.setCheckable(True)
        #self._labelControlUi.boxToolButton.clicked.connect( lambda checked: self._handleToolButtonClicked(checked,
        #                                                                                                  Tool.Box) )
        #self.toolButtons[Tool.Box] = self._labelControlUi.boxToolButton
        if hasattr(self._labelControlUi, "AddBoxButton"):

            self._labelControlUi.AddBoxButton.setIcon( QIcon(ilastikIcons.AddSel) )
            self._labelControlUi.AddBoxButton.clicked.connect( bind(self.onAddNewBoxButtonClicked) )



    def onAddNewBoxButtonClicked(self):

        self._changeInteractionMode(Tool.Box)
        self.labelingDrawerUi.boxListView.resetEmptyMessage("Draw the box on the image")


    def _onBoxSelected(self, row):
        print "switching to box=%r" % (self._labelControlUi.boxListModel[row])
        print "row = ",row
        logger.debug("switching to label=%r" % (self._labelControlUi.boxListModel[row]))

        # If the user is selecting a label, he probably wants to be in paint mode
        self._changeInteractionMode(Tool.Box)

        print len(self.boxController._currentBoxesList)
        self.boxController.selectBoxItem(row)


    def _onLabelSelected(self, row):
        print "switching to label=%r" % (self._labelControlUi.labelListModel[row])
        logger.debug("switching to label=%r" % (self._labelControlUi.labelListModel[row]))



        # If the user is selecting a label, he probably wants to be in paint mode
        self._changeInteractionMode(Tool.Paint)



        self.toolButtons[Tool.Paint].setEnabled(True)
        #elf.toolButtons[Tool.Box].setEnabled(False)
        self.toolButtons[Tool.Paint].click()

        #+1 because first is transparent
        #FIXME: shouldn't be just row+1 here
        self.editor.brushingModel.setDrawnNumber(row+1)
        brushColor = self._labelControlUi.labelListModel[row].brushColor()
        self.editor.brushingModel.setBrushColor( brushColor )



        if row==0: #foreground

            self._cachedBrushSizeIndex= self._labelControlUi.brushSizeComboBox.currentIndex()
            self._labelControlUi.brushSizeComboBox.setEnabled(False)
            self._labelControlUi.brushSizeComboBox.setCurrentIndex(0)
        else:
            if not hasattr(self, "_cachedBrushSizeIndex"):
                self._cachedBrushSizeIndex=0

            self._labelControlUi.brushSizeComboBox.setCurrentIndex(self._cachedBrushSizeIndex)



    def updateSum(self, *args, **kw):
        print "updatingSum"
        density = self.op.OutputSum[...].wait()
        strdensity = "{0:.2f}".format(density[0])
        self._labelControlUi.CountText.setText(strdensity)


countingColorTable = [
    QColor(0.0,0.0,127.0,0.0).rgba(),
    QColor(0.0,0.0,134.0,1.0).rgba(),
    QColor(0.0,0.0,141.0,3.0).rgba(),
    QColor(0.0,0.0,148.0,4.0).rgba(),
    QColor(0.0,0.0,154.0,6.0).rgba(),
    QColor(0.0,0.0,161.0,7.0).rgba(),
    QColor(0.0,0.0,168.0,9.0).rgba(),
    QColor(0.0,0.0,175.0,10.0).rgba(),
    QColor(0.0,0.0,182.0,12.0).rgba(),
    QColor(0.0,0.0,189.0,13.0).rgba(),
    QColor(0.0,0.0,196.0,15.0).rgba(),
    QColor(0.0,0.0,202.0,16.0).rgba(),
    QColor(0.0,0.0,209.0,18.0).rgba(),
    QColor(0.0,0.0,216.0,19.0).rgba(),
    QColor(0.0,0.0,223.0,21.0).rgba(),
    QColor(0.0,0.0,230.0,22.0).rgba(),
    QColor(0.0,0.0,237.0,24.0).rgba(),
    QColor(0.0,0.0,244.0,25.0).rgba(),
    QColor(0.0,0.0,250.0,27.0).rgba(),
    QColor(0.0,0.0,255.0,28.0).rgba(),
    QColor(0.0,0.0,255.0,30.0).rgba(),
    QColor(0.0,0.0,255.0,31.0).rgba(),
    QColor(0.0,5.0,255.0,33.0).rgba(),
    QColor(0.0,11.0,255.0,34.0).rgba(),
    QColor(0.0,17.0,255.0,36.0).rgba(),
    QColor(0.0,23.0,255.0,37.0).rgba(),
    QColor(0.0,29.0,255.0,39.0).rgba(),
    QColor(0.0,35.0,255.0,40.0).rgba(),
    QColor(0.0,41.0,255.0,42.0).rgba(),
    QColor(0.0,47.0,255.0,43.0).rgba(),
    QColor(0.0,53.0,255.0,45.0).rgba(),
    QColor(0.0,59.0,255.0,46.0).rgba(),
    QColor(0.0,65.0,255.0,48.0).rgba(),
    QColor(0.0,71.0,255.0,49.0).rgba(),
    QColor(0.0,77.0,255.0,51.0).rgba(),
    QColor(0.0,83.0,255.0,52.0).rgba(),
    QColor(0.0,89.0,255.0,54.0).rgba(),
    QColor(0.0,95.0,255.0,55.0).rgba(),
    QColor(0.0,101.0,255.0,57.0).rgba(),
    QColor(0.0,107.0,255.0,58.0).rgba(),
    QColor(0.0,113.0,255.0,60.0).rgba(),
    QColor(0.0,119.0,255.0,61.0).rgba(),
    QColor(0.0,125.0,255.0,63.0).rgba(),
    QColor(0.0,132.0,255.0,64.0).rgba(),
    QColor(0.0,138.0,255.0,66.0).rgba(),
    QColor(0.0,144.0,255.0,67.0).rgba(),
    QColor(0.0,150.0,255.0,69.0).rgba(),
    QColor(0.0,156.0,255.0,70.0).rgba(),
    QColor(0.0,162.0,255.0,72.0).rgba(),
    QColor(0.0,168.0,255.0,73.0).rgba(),
    QColor(0.0,174.0,255.0,75.0).rgba(),
    QColor(0.0,180.0,255.0,76.0).rgba(),
    QColor(0.0,186.0,255.0,78.0).rgba(),
    QColor(0.0,192.0,255.0,79.0).rgba(),
    QColor(0.0,198.0,255.0,81.0).rgba(),
    QColor(0.0,204.0,255.0,82.0).rgba(),
    QColor(0.0,210.0,255.0,84.0).rgba(),
    QColor(0.0,216.0,255.0,85.0).rgba(),
    QColor(0.0,222.0,252.0,87.0).rgba(),
    QColor(0.0,228.0,247.0,88.0).rgba(),
    QColor(4.0,234.0,242.0,90.0).rgba(),
    QColor(9.0,240.0,237.0,91.0).rgba(),
    QColor(13.0,246.0,232.0,93.0).rgba(),
    QColor(18.0,252.0,228.0,94.0).rgba(),
    QColor(23.0,255.0,223.0,96.0).rgba(),
    QColor(28.0,255.0,218.0,97.0).rgba(),
    QColor(33.0,255.0,213.0,99.0).rgba(),
    QColor(38.0,255.0,208.0,100.0).rgba(),
    QColor(43.0,255.0,203.0,102.0).rgba(),
    QColor(47.0,255.0,198.0,103.0).rgba(),
    QColor(52.0,255.0,193.0,105.0).rgba(),
    QColor(57.0,255.0,189.0,106.0).rgba(),
    QColor(62.0,255.0,184.0,108.0).rgba(),
    QColor(67.0,255.0,179.0,109.0).rgba(),
    QColor(72.0,255.0,174.0,111.0).rgba(),
    QColor(77.0,255.0,169.0,112.0).rgba(),
    QColor(82.0,255.0,164.0,114.0).rgba(),
    QColor(86.0,255.0,159.0,115.0).rgba(),
    QColor(91.0,255.0,155.0,117.0).rgba(),
    QColor(96.0,255.0,150.0,118.0).rgba(),
    QColor(101.0,255.0,145.0,120.0).rgba(),
    QColor(106.0,255.0,140.0,121.0).rgba(),
    QColor(111.0,255.0,135.0,123.0).rgba(),
    QColor(116.0,255.0,130.0,124.0).rgba(),
    QColor(120.0,255.0,125.0,126.0).rgba(),
    QColor(125.0,255.0,120.0,127.0).rgba(),
    QColor(130.0,255.0,116.0,129.0).rgba(),
    QColor(135.0,255.0,111.0,130.0).rgba(),
    QColor(140.0,255.0,106.0,132.0).rgba(),
    QColor(145.0,255.0,101.0,133.0).rgba(),
    QColor(150.0,255.0,96.0,135.0).rgba(),
    QColor(155.0,255.0,91.0,136.0).rgba(),
    QColor(159.0,255.0,86.0,138.0).rgba(),
    QColor(164.0,255.0,82.0,139.0).rgba(),
    QColor(169.0,255.0,77.0,141.0).rgba(),
    QColor(174.0,255.0,72.0,142.0).rgba(),
    QColor(179.0,255.0,67.0,144.0).rgba(),
    QColor(184.0,255.0,62.0,145.0).rgba(),
    QColor(189.0,255.0,57.0,147.0).rgba(),
    QColor(193.0,255.0,52.0,148.0).rgba(),
    QColor(198.0,255.0,47.0,150.0).rgba(),
    QColor(203.0,255.0,43.0,151.0).rgba(),
    QColor(208.0,255.0,38.0,153.0).rgba(),
    QColor(213.0,255.0,33.0,154.0).rgba(),
    QColor(218.0,255.0,28.0,156.0).rgba(),
    QColor(223.0,255.0,23.0,157.0).rgba(),
    QColor(228.0,255.0,18.0,159.0).rgba(),
    QColor(232.0,255.0,13.0,160.0).rgba(),
    QColor(237.0,255.0,9.0,162.0).rgba(),
    QColor(242.0,250.0,4.0,163.0).rgba(),
    QColor(247.0,244.0,0.0,165.0).rgba(),
    QColor(252.0,239.0,0.0,166.0).rgba(),
    QColor(255.0,233.0,0.0,168.0).rgba(),
    QColor(255.0,227.0,0.0,169.0).rgba(),
    QColor(255.0,222.0,0.0,171.0).rgba(),
    QColor(255.0,216.0,0.0,172.0).rgba(),
    QColor(255.0,211.0,0.0,174.0).rgba(),
    QColor(255.0,205.0,0.0,175.0).rgba(),
    QColor(255.0,200.0,0.0,177.0).rgba(),
    QColor(255.0,194.0,0.0,178.0).rgba(),
    QColor(255.0,188.0,0.0,180.0).rgba(),
    QColor(255.0,183.0,0.0,181.0).rgba(),
    QColor(255.0,177.0,0.0,183.0).rgba(),
    QColor(255.0,172.0,0.0,184.0).rgba(),
    QColor(255.0,166.0,0.0,186.0).rgba(),
    QColor(255.0,160.0,0.0,187.0).rgba(),
    QColor(255.0,155.0,0.0,189.0).rgba(),
    QColor(255.0,149.0,0.0,190.0).rgba(),
    QColor(255.0,144.0,0.0,192.0).rgba(),
    QColor(255.0,138.0,0.0,193.0).rgba(),
    QColor(255.0,132.0,0.0,195.0).rgba(),
    QColor(255.0,127.0,0.0,196.0).rgba(),
    QColor(255.0,121.0,0.0,198.0).rgba(),
    QColor(255.0,116.0,0.0,199.0).rgba(),
    QColor(255.0,110.0,0.0,201.0).rgba(),
    QColor(255.0,105.0,0.0,202.0).rgba(),
    QColor(255.0,99.0,0.0,204.0).rgba(),
    QColor(255.0,93.0,0.0,205.0).rgba(),
    QColor(255.0,88.0,0.0,207.0).rgba(),
    QColor(255.0,82.0,0.0,208.0).rgba(),
    QColor(255.0,77.0,0.0,210.0).rgba(),
    QColor(255.0,71.0,0.0,211.0).rgba(),
    QColor(255.0,65.0,0.0,213.0).rgba(),
    QColor(255.0,60.0,0.0,214.0).rgba(),
    QColor(255.0,54.0,0.0,216.0).rgba(),
    QColor(255.0,49.0,0.0,217.0).rgba(),
    QColor(255.0,43.0,0.0,219.0).rgba(),
    QColor(255.0,37.0,0.0,220.0).rgba(),
    QColor(255.0,32.0,0.0,222.0).rgba(),
    QColor(255.0,26.0,0.0,223.0).rgba(),
    QColor(255.0,21.0,0.0,225.0).rgba(),
    QColor(250.0,15.0,0.0,226.0).rgba(),
    QColor(244.0,10.0,0.0,228.0).rgba(),
    QColor(237.0,4.0,0.0,229.0).rgba(),
    QColor(230.0,0.0,0.0,231.0).rgba(),
    QColor(223.0,0.0,0.0,232.0).rgba(),
    QColor(216.0,0.0,0.0,234.0).rgba(),
    QColor(209.0,0.0,0.0,235.0).rgba(),
    QColor(202.0,0.0,0.0,237.0).rgba(),
    QColor(196.0,0.0,0.0,238.0).rgba(),
    QColor(189.0,0.0,0.0,240.0).rgba(),
    QColor(182.0,0.0,0.0,241.0).rgba(),
    QColor(175.0,0.0,0.0,243.0).rgba(),
    QColor(168.0,0.0,0.0,244.0).rgba(),
    QColor(161.0,0.0,0.0,246.0).rgba(),
    QColor(154.0,0.0,0.0,247.0).rgba(),
    QColor(148.0,0.0,0.0,249.0).rgba(),
    QColor(141.0,0.0,0.0,250.0).rgba(),
    QColor(134.0,0.0,0.0,252.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba(),
    QColor(127.0,0.0,0.0,255.0).rgba()]
