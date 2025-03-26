#Python
import os
import logging
logger = logging.getLogger(__name__)
traceLogger = logging.getLogger('TRACE.' + __name__)

#SciPy
import numpy

#PyQt
from PyQt4.QtCore import QRectF
from PyQt4.QtGui import *
from PyQt4 import uic

#lazyflow
from lazyflow.stype import ArrayLike
from lazyflow.operators import OpSingleChannelSelector, OpWrapSlot
from lazyflow.utility import traceLogged

#volumina
from volumina.api import LazyflowSource, GrayscaleLayer, RGBALayer, \
                         LayerStackModel, VolumeEditor
from volumina.utility import ShortcutManager
from lazyflow.operators.adaptors import Op5ifyer
from volumina.interpreter import ClickReportingInterpreter

from ilastik.widgets.viewerControls import ViewerControls

#ilastik
from ilastik.utility import bind
from ilastik.utility.gui import ThreadRouter, threadRouted
from ilastik.config import cfg as ilastik_config

#===----------------------------------------------------------------------------------------------------------------===

class LayerViewerGuiMetaclass(type(QWidget)):
    """
    Custom metaclass to enable the _after_init function.
    """
    def __call__(cls, *args, **kwargs):
        """
        This is where __init__ is called.
        Here we can call code to execute immediately before or after the *subclass* __init__ function.
        """
        # Base class first. (type is our baseclass)
        # type.__call__ calls instance.__init__ internally
        instance = super(LayerViewerGuiMetaclass, cls).__call__(*args,**kwargs)
        instance._after_init()
        return instance

class LayerViewerGui(QWidget):
    """
    Implements an applet GUI whose central widget is a VolumeEditor
    and whose layer controls simply contains a layer list widget.
    Intended to be used as a subclass for applet GUI objects.

    Provides: Central widget (viewer), View Menu, and Layer controls
    Provides an EMPTY applet drawer widget.  Subclasses should replace it with their own applet drawer.
    """
    __metaclass__ = LayerViewerGuiMetaclass
    
    ###########################################
    ### AppletGuiInterface Concrete Methods ###
    ###########################################

    def centralWidget( self ):
        return self

    def appletDrawer(self):
        return self._drawer

    def menus( self ):
        debug_mode = ilastik_config.getboolean("ilastik", "debug")
        return [ self.volumeEditorWidget.getViewMenu(debug_mode) ]

    def viewerControlWidget(self):
        return self.__viewerControlWidget

    def stopAndCleanUp(self):
        self._stopped = True

        # Remove all layers
        self.layerstack.clear()

        # Stop rendering
        for scene in self.editor.imageScenes:
            if scene._tileProvider:
                scene._tileProvider.notifyThreadsToStop()
            scene.joinRendering()
            
        for op in self._orphanOperators:
            op.cleanUp()

    ###########################################
    ###########################################

    @traceLogged(traceLogger)
    def __init__(self, topLevelOperatorView, additionalMonitoredSlots=[], centralWidgetOnly=False, crosshair=True):
        """
        Constructor.  **All** slots of the provided *topLevelOperatorView* will be monitored for changes.
        Changes include slot resize events, and slot ready/unready status changes.
        When a change is detected, the `setupLayers()` function is called, and the result is used to update the list of layers shown in the central widget.

        :param topLevelOperatorView: The top-level operator for the applet this GUI belongs to.
        :param additionalMonitoredSlots: Optional.  Can be used to add additional slots to the set of viewable layers (all slots from the top-level operator are already monitored).
        :param centralWidgetOnly: If True, provide only a central widget without drawer or viewer controls.
        """
        super(LayerViewerGui, self).__init__()

        self._stopped = False
        self._initialized = False

        self.threadRouter = ThreadRouter(self) # For using @threadRouted

        self.topLevelOperatorView = topLevelOperatorView

        observedSlots = []

        for slot in topLevelOperatorView.inputs.values() + topLevelOperatorView.outputs.values():
            if slot.level == 0 or slot.level == 1:
                observedSlots.append(slot)
        
        observedSlots += additionalMonitoredSlots

        self._orphanOperators = [] # Operators that are owned by this GUI directly (not owned by the top-level operator)
        self.observedSlots = []
        for slot in observedSlots:
            if slot.level == 0:
                if not isinstance(slot.stype, ArrayLike):
                    # We don't support visualization of non-Array slots.
                    continue
                # To be monitored and updated correctly by this GUI, slots must have level=1, but this slot is of level 0.
                # Pass it through a trivial "up-leveling" operator so it will have level 1 for our purposes.
                opPromoteInput = OpWrapSlot(graph=slot.operator.graph)
                opPromoteInput.Input.connect(slot)
                slot = opPromoteInput.Output
                self._orphanOperators.append( opPromoteInput )

            # Each slot should now be indexed as slot[layer_index]
            assert slot.level == 1
            self.observedSlots.append( slot )
            slot.notifyInserted( bind(self._handleLayerInsertion) )
            slot.notifyRemoved( bind(self._handleLayerRemoval) )
            for i in range(len(slot)):
                self._handleLayerInsertion(slot, i)
 
        self.layerstack = LayerStackModel()

        self._initCentralUic()
        self._initEditor(crosshair=crosshair)
        self.__viewerControlWidget = None
        if not centralWidgetOnly:
            self.initViewerControlUi() # Might be overridden in a subclass. Default implementation loads a standard layer widget.
            #self._drawer = QWidget( self )
            self.initAppletDrawerUi() # Default implementation loads a blank drawer from drawer.ui.
        
    def _after_init(self):
        self._initialized = True
        self.updateAllLayers()

    def setupLayers( self ):
        """
        Create a list of layers to be displayed in the central widget.
        Subclasses should override this method to create the list of layers that can be displayed.
        For debug and development purposes, the base class implementation simply generates layers for all topLevelOperatorView slots.
        """
        layers = []
        for multiLayerSlot in self.observedSlots:
            for j, slot in enumerate(multiLayerSlot):
                if slot.ready() and slot.meta.axistags is not None:
                    layer = self.createStandardLayerFromSlot(slot)
                    
                    # Name the layer after the slot name.
                    if isinstance( multiLayerSlot.getRealOperator(), OpWrapSlot ):
                        # We attached an 'upleveling' operator, so look upstream for the real slot.
                        layer.name = multiLayerSlot.getRealOperator().Input.partner.name
                    else:
                        layer.name = multiLayerSlot.name + " " + str(j)
                    layers.append(layer)
        return layers

    @traceLogged(traceLogger)
    def _handleLayerInsertion(self, slot, slotIndex):
        """
        The multislot providing our layers has a new item.
        Make room for it in the layer GUI and subscribe to updates.
        """
        # When the slot is ready, we'll replace the blank layer with real data
        slot[slotIndex].notifyReady( bind(self.updateAllLayers) )
        slot[slotIndex].notifyUnready( bind(self.updateAllLayers) )

    @traceLogged(traceLogger)
    def _handleLayerRemoval(self, slot, slotIndex):
        """
        An item is about to be removed from the multislot that is providing our layers.
        Remove the layer from the GUI.
        """
        self.updateAllLayers(slot)

    def generateAlphaModulatedLayersFromChannels(self, slot):
        # TODO
        assert False

    @classmethod
    def createStandardLayerFromSlot(cls, slot, lastChannelIsAlpha=False):
        """
        Convenience function.
        Generates a volumina layer using the given slot.
        Chooses between grayscale or RGB depending on the number of channels in the slot.

        * If *slot* has 1 channel or more than 4 channels, a GrayscaleLayer is created.
        * If *slot* has 2 non-alpha channels, an RGBALayer is created with R and G channels.
        * If *slot* has 3 non-alpha channels, an RGBALayer is created with R,G, and B channels.
        * If *slot* has 4 channels, an RGBA layer is created

        :param slot: The slot to generate a layer from
        :param lastChannelIsAlpha: If True, the last channel in the slot is assumed to be an alpha channel.
                                   If slot has 4 channels, this parameter has no effect.
        """
        def getRange(meta):
            if 'drange' in meta:
                return meta.drange
            if meta.dtype == numpy.uint8:
                return (0, 255)
            else:
                # If we don't know the range of the data, create a layer that is auto-normalized.
                # See volumina.pixelpipeline.datasources for details.
                #
                # Even in the case of integer data, which has more than 255 possible values,
                # (like uint16), it seems reasonable to use this setting as default
                return 'autoPercentiles'
        
        shape = slot.meta.shape
        normalize = getRange(slot.meta)
        
        try:
            channelAxisIndex = slot.meta.axistags.index('c')
            #assert channelAxisIndex < len(slot.meta.axistags), \
            #    "slot %s has shape = %r, axistags = %r, but no channel dimension" \
            #    % (slot.name, slot.meta.shape, slot.meta.axistags)
            numChannels = shape[channelAxisIndex]
            axisinfo = slot.meta.axistags["c"].description
        except:
            numChannels = 1
            axisinfo = "" # == no info on channels given
        
        rindex = None
        bindex = None
        gindex = None
        aindex = None
        
        if axisinfo == "" or axisinfo == "default":
            # Examine channel dimension to determine Grayscale vs. RGB

            if numChannels == 4:
                lastChannelIsAlpha = True
                
            if lastChannelIsAlpha:
                assert numChannels <= 4, "Can't display a standard layer with more than four channels (with alpha).  Your image has {} channels.".format(numChannels)

            if numChannels == 1 or (numChannels > 4):
                assert not lastChannelIsAlpha, "Can't have an alpha channel if there is no color channel"
                source = LazyflowSource(slot)
                layer = GrayscaleLayer(source)
                layer.numberOfChannels = numChannels
                return layer

            assert numChannels > 2 or (numChannels == 2 and not lastChannelIsAlpha), \
                "Unhandled combination of channels.  numChannels={}, lastChannelIsAlpha={}, axistags={}".format( numChannels, lastChannelIsAlpha, slot.meta.axistags )
            
            rindex = 0
            gindex = 1
            if numChannels > 3 or (numChannels == 3 and not lastChannelIsAlpha):
                bindex = 2
            if lastChannelIsAlpha:
                aindex = numChannels-1
        
        elif axisinfo == "grayscale":
            source = LazyflowSource(slot)
            layer = GrayscaleLayer(source)
            layer.numberOfChannels = numChannels
            return layer
        
        elif axisinfo == "rgba":
            rindex = 0
            if numChannels>=2:
                gindex = 1
            if numChannels>=3:
                bindex = 2
            if numChannels>=4:
                aindex = numChannels-1
        else:
            raise RuntimeError("unknown channel display mode")

        redSource = None
        if rindex is not None:
            redProvider = OpSingleChannelSelector(graph=slot.graph)
            redProvider.Input.connect(slot)
            redProvider.Index.setValue( rindex )
            redSource = LazyflowSource( redProvider.Output )
        
        greenSource = None
        if gindex is not None:
            greenProvider = OpSingleChannelSelector(graph=slot.graph)
            greenProvider.Input.connect(slot)
            greenProvider.Index.setValue( gindex )
            greenSource = LazyflowSource( greenProvider.Output )
        
        blueSource = None
        if bindex is not None:
                blueProvider = OpSingleChannelSelector(graph=slot.graph)
                blueProvider.Input.connect(slot)
                blueProvider.Index.setValue( bindex )
                blueSource = LazyflowSource( blueProvider.Output )

        alphaSource = None
        if aindex is not None:
            alphaProvider = OpSingleChannelSelector(graph=slot.graph)
            alphaProvider.Input.connect(slot)
            alphaProvider.Index.setValue( aindex )
            alphaSource = LazyflowSource( alphaProvider.Output )

        layer = RGBALayer( red=redSource, green=greenSource, blue=blueSource, alpha=alphaSource )
        return layer

    @traceLogged(traceLogger)
    @threadRouted
    def updateAllLayers(self, slot=None):
        if self._stopped or not self._initialized:
            return
        if slot is not None and slot.meta.axistags is None:
            return

        # Ask for the updated layer list (usually provided by the subclass)
        newGuiLayers = self.setupLayers()

        newNames = set(l.name for l in newGuiLayers)
        if len(newNames) != len(newGuiLayers):
            msg = "All layers must have unique names.\n"
            msg += "You're attempting to use these layer names:\n"
            msg += str( [l.name for l in newGuiLayers] )
            raise RuntimeError(msg)

        # If the datashape changed, tell the editor
        # FIXME: This may not be necessary now that this gui doesn't handle the multi-image case...
        newDataShape = self.determineDatashape()
        if newDataShape is not None and self.editor.dataShape != newDataShape:
            self.editor.dataShape = newDataShape
                       
            # Find the xyz midpoint
            midpos5d = [x/2 for x in newDataShape]
            midpos3d = midpos5d[1:4]

            # Start in the center of the volume
            self.editor.posModel.slicingPos = midpos3d
            self.editor.navCtrl.panSlicingViews( midpos3d, [0,1,2] )

        # Old layers are deleted if
        # (1) They are not in the new set or
        # (2) Their data has changed
        for index, oldLayer in reversed(list(enumerate(self.layerstack))):
            if oldLayer.name not in newNames:
                needDelete = True
            else:
                newLayer = filter(lambda l: l.name == oldLayer.name, newGuiLayers)[0]
                needDelete = (newLayer.datasources != oldLayer.datasources)

            if needDelete:
                layer = self.layerstack[index]
                if hasattr(layer, 'shortcutRegistration'):
                    obsoleteShortcut = layer.shortcutRegistration[2]
                    obsoleteShortcut.setEnabled(False)
                    ShortcutManager().unregister( obsoleteShortcut )
                self.layerstack.selectRow(index)
                self.layerstack.deleteSelected()

        # Insert all layers that aren't already in the layerstack
        # (Identified by the name attribute)
        existingNames = set(l.name for l in self.layerstack)
        for index, layer in enumerate(newGuiLayers):
            if layer.name not in existingNames:
                # Insert new
                self.layerstack.insert( index, layer )

                # If this layer has an associated shortcut, register it with the shortcut manager
                if hasattr(layer, 'shortcutRegistration'):
                    ShortcutManager().register( *layer.shortcutRegistration )
            else:
                # Clean up the layer instance that the client just gave us.
                # We don't want to use it.
                if hasattr(layer, 'shortcutRegistration'):
                    shortcut = layer.shortcutRegistration[2]
                    shortcut.setEnabled(False)

                # Move existing layer to the correct position
                stackIndex = self.layerstack.findMatchingIndex(lambda l: l.name == layer.name)
                self.layerstack.selectRow(stackIndex)
                while stackIndex > index:
                    self.layerstack.moveSelectedUp()
                    stackIndex -= 1
                while stackIndex < index:
                    self.layerstack.moveSelectedDown()
                    stackIndex += 1

    @traceLogged(traceLogger)
    def determineDatashape(self):
        newDataShape = None
        for provider in self.observedSlots:
            for i, slot in enumerate(provider):
                if newDataShape is None and slot.ready() and slot.meta.axistags is not None:
                    # Use an Op5ifyer adapter to transpose the shape for us.
                    op5 = Op5ifyer( graph=slot.graph )
                    op5.input.connect( slot )
                    newDataShape = op5.output.meta.shape

                    # We just needed the operator to determine the transposed shape.
                    # Disconnect it so it can be garbage collected.
                    op5.input.disconnect()
        return newDataShape

    @traceLogged(traceLogger)
    def initViewerControlUi(self):
        """
        Load the viewer controls GUI, which appears below the applet bar.
        In our case, the viewer control GUI consists mainly of a layer list.
        Subclasses should override this if they provide their own viewer control widget.
        """
        localDir = os.path.split(__file__)[0]
        self.__viewerControlWidget = ViewerControls()

        # The editor's layerstack is in charge of which layer movement buttons are enabled
        model = self.editor.layerStack

        if self.__viewerControlWidget is not None:
            self.__viewerControlWidget.setupConnections(model)

    @traceLogged(traceLogger)
    def initAppletDrawerUi(self):
        """
        By default, this base class provides a blank applet drawer.
        Override this in a subclass to get a real applet drawer.
        """
        # Load the ui file (find it in our own directory)
        localDir = os.path.split(__file__)[0]
        self._drawer = uic.loadUi(localDir+"/drawer.ui")

    def getAppletDrawerUi(self):
        return self._drawer

    @traceLogged(traceLogger)
    def _initCentralUic(self):
        """
        Load the GUI from the ui file into this class and connect it with event handlers.
        """
        # Load the ui file into this class (find it in our own directory)
        localDir = os.path.split(__file__)[0]
        uic.loadUi(localDir+"/centralWidget.ui", self)

    @traceLogged(traceLogger)
    def _initEditor(self, crosshair):
        """
        Initialize the Volume Editor GUI.
        """
        self.editor = VolumeEditor(self.layerstack, crosshair=crosshair)

        # Replace the editor's navigation interpreter with one that has extra functionality
        self.clickReporter = ClickReportingInterpreter( self.editor.navInterpret, self.editor.posModel )
        self.editor.setNavigationInterpreter( self.clickReporter )
        self.clickReporter.rightClickReceived.connect( self._handleEditorRightClick )
        self.clickReporter.leftClickReceived.connect( self._handleEditorLeftClick )

        self.editor.setInteractionMode( 'navigation' )
        self.volumeEditorWidget.init(self.editor)

        self.editor._lastImageViewFocus = 0

        # Zoom at a 1-1 scale to avoid loading big datasets entirely...
        for view in self.editor.imageViews:
            view.doScaleTo(1)

    @traceLogged(traceLogger)
    def _convertPositionToDataSpace(self, voluminaPosition):
        taggedPosition = {k:p for k,p in zip('txyzc', voluminaPosition)}

        # Find the first lazyflow layer in the stack
        # We assume that all lazyflow layers have the same axistags
        dataTags = None
        for layer in self.layerstack:
            for datasource in layer.datasources:
                try: # not all datasources have the dataSlot property, find out by trying
                    dataTags = datasource.dataSlot.meta.axistags
                    if dataTags is not None:
                        break
                except AttributeError:
                    pass

        if(dataTags is None):
            raise RuntimeError("Can't convert mouse click coordinates from volumina-5d: Could not find a lazyflow data source in any layer.")
        position = ()
        for tag in dataTags:
            position += (taggedPosition[tag.key],)

        return position

    def _handleEditorRightClick(self, position5d, globalWindowCoordinate):
        dataPosition = self._convertPositionToDataSpace(position5d)
        self.handleEditorRightClick(dataPosition, globalWindowCoordinate)

    def _handleEditorLeftClick(self, position5d, globalWindowCoordinate):
        dataPosition = self._convertPositionToDataSpace(position5d)
        self.handleEditorLeftClick(dataPosition, globalWindowCoordinate)

    def handleEditorRightClick(self, position5d, globalWindowCoordinate):
        # Override me
        pass

    def handleEditorLeftClick(self, position5d, globalWindowCoordiante):
        # Override me
        pass
