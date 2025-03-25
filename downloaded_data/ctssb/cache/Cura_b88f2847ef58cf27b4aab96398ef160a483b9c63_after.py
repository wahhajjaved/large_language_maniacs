# Copyright (c) 2015 Ultimaker B.V.
# Cura is released under the terms of the AGPLv3 or higher.

from UM.Qt.QtApplication import QtApplication
from UM.Scene.SceneNode import SceneNode
from UM.Scene.Camera import Camera
from UM.Scene.Platform import Platform
from UM.Math.Vector import Vector
from UM.Math.Quaternion import Quaternion
from UM.Math.AxisAlignedBox import AxisAlignedBox
from UM.Resources import Resources
from UM.Scene.ToolHandle import ToolHandle
from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator
from UM.Mesh.ReadMeshJob import ReadMeshJob
from UM.Logger import Logger
from UM.Preferences import Preferences
from UM.JobQueue import JobQueue
from UM.SaveFile import SaveFile
from UM.Scene.Selection import Selection
from UM.Scene.GroupDecorator import GroupDecorator
import UM.Settings.Validator

from UM.Operations.AddSceneNodeOperation import AddSceneNodeOperation
from UM.Operations.RemoveSceneNodeOperation import RemoveSceneNodeOperation
from UM.Operations.GroupedOperation import GroupedOperation
from UM.Operations.SetTransformOperation import SetTransformOperation
from cura.SetParentOperation import SetParentOperation

from UM.Settings.SettingDefinition import SettingDefinition, DefinitionPropertyType
from UM.Settings.ContainerRegistry import ContainerRegistry

from UM.i18n import i18nCatalog

from . import ExtrudersModel
from . import PlatformPhysics
from . import BuildVolume
from . import CameraAnimation
from . import PrintInformation
from . import CuraActions
from . import MultiMaterialDecorator
from . import ZOffsetDecorator
from . import CuraSplashScreen
from . import MachineManagerModel

from PyQt5.QtCore import pyqtSlot, QUrl, pyqtSignal, pyqtProperty, QEvent, Q_ENUMS
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtQml import qmlRegisterUncreatableType, qmlRegisterSingletonType, qmlRegisterType

import platform
import sys
import os.path
import numpy
import copy
import urllib
numpy.seterr(all="ignore")

#WORKAROUND: GITHUB-88 GITHUB-385 GITHUB-612
if platform.system() == "Linux": # Needed for platform.linux_distribution, which is not available on Windows and OSX
    # For Ubuntu: https://bugs.launchpad.net/ubuntu/+source/python-qt4/+bug/941826
    if platform.linux_distribution()[0] in ("Ubuntu", ): # TODO: Needs a "if X11_GFX == 'nvidia'" here. The workaround is only needed on Ubuntu+NVidia drivers. Other drivers are not affected, but fine with this fix.
        import ctypes
        from ctypes.util import find_library
        ctypes.CDLL(find_library('GL'), ctypes.RTLD_GLOBAL)

try:
    from cura.CuraVersion import CuraVersion, CuraBuildType
except ImportError:
    CuraVersion = "master"  # [CodeStyle: Reflecting imported value]
    CuraBuildType = ""


class CuraApplication(QtApplication):
    class ResourceTypes:
        QmlFiles = Resources.UserType + 1
        Firmware = Resources.UserType + 2
        QualityInstanceContainer = Resources.UserType + 3
        MaterialInstanceContainer = Resources.UserType + 4
        VariantInstanceContainer = Resources.UserType + 5
        UserInstanceContainer = Resources.UserType + 6
        MachineStack = Resources.UserType + 7
        ExtruderStack = Resources.UserType + 8

    Q_ENUMS(ResourceTypes)

    def __init__(self):
        Resources.addSearchPath(os.path.join(QtApplication.getInstallPrefix(), "share", "cura", "resources"))
        if not hasattr(sys, "frozen"):
            Resources.addSearchPath(os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "resources"))

        self._open_file_queue = []  # Files to open when plug-ins are loaded.

        # Need to do this before ContainerRegistry tries to load the machines
        SettingDefinition.addSupportedProperty("global_only", DefinitionPropertyType.Function, default = False)
        SettingDefinition.addSettingType("extruder", int, str, UM.Settings.Validator)

        super().__init__(name = "cura", version = CuraVersion, buildtype = CuraBuildType)

        self.setWindowIcon(QIcon(Resources.getPath(Resources.Images, "cura-icon.png")))

        self.setRequiredPlugins([
            "CuraEngineBackend",
            "MeshView",
            "LayerView",
            "STLReader",
            "SelectionTool",
            "CameraTool",
            "GCodeWriter",
            "LocalFileOutputDevice"
        ])
        self._physics = None
        self._volume = None
        self._platform = None
        self._output_devices = {}
        self._print_information = None
        self._i18n_catalog = None
        self._previous_active_tool = None
        self._platform_activity = False
        self._scene_bounding_box = AxisAlignedBox()
        self._job_name = None
        self._center_after_select = False
        self._camera_animation = None
        self._cura_actions = None
        self._started = False

        self.getController().getScene().sceneChanged.connect(self.updatePlatformActivity)
        self.getController().toolOperationStopped.connect(self._onToolOperationStopped)

        Resources.addType(self.ResourceTypes.QmlFiles, "qml")
        Resources.addType(self.ResourceTypes.Firmware, "firmware")

        ## Add the 4 types of profiles to storage.
        Resources.addStorageType(self.ResourceTypes.QualityInstanceContainer, "quality")
        Resources.addStorageType(self.ResourceTypes.VariantInstanceContainer, "variants")
        Resources.addStorageType(self.ResourceTypes.MaterialInstanceContainer, "materials")
        Resources.addStorageType(self.ResourceTypes.UserInstanceContainer, "user")
        Resources.addStorageType(self.ResourceTypes.ExtruderStack, "extruders")
        Resources.addStorageType(self.ResourceTypes.MachineStack, "machine_instances")

        ContainerRegistry.getInstance().addResourceType(self.ResourceTypes.QualityInstanceContainer)
        ContainerRegistry.getInstance().addResourceType(self.ResourceTypes.VariantInstanceContainer)
        ContainerRegistry.getInstance().addResourceType(self.ResourceTypes.MaterialInstanceContainer)
        ContainerRegistry.getInstance().addResourceType(self.ResourceTypes.UserInstanceContainer)
        ContainerRegistry.getInstance().addResourceType(self.ResourceTypes.ExtruderStack)
        ContainerRegistry.getInstance().addResourceType(self.ResourceTypes.MachineStack)

        # Add empty variant, material and quality containers.
        # Since they are empty, they should never be serialized and instead just programmatically created.
        # We need them to simplify the switching between materials.
        empty_container = ContainerRegistry.getInstance().getEmptyInstanceContainer()
        empty_variant_container = copy.deepcopy(empty_container)
        empty_variant_container._id = "empty_variant"
        empty_variant_container.addMetaDataEntry("type", "variant")
        ContainerRegistry.getInstance().addContainer(empty_variant_container)
        empty_material_container = copy.deepcopy(empty_container)
        empty_material_container._id = "empty_material"
        empty_material_container.addMetaDataEntry("type", "material")
        ContainerRegistry.getInstance().addContainer(empty_material_container)
        empty_quality_container = copy.deepcopy(empty_container)
        empty_quality_container._id = "empty_quality"
        empty_quality_container.addMetaDataEntry("type", "quality")
        ContainerRegistry.getInstance().addContainer(empty_quality_container)

        ContainerRegistry.getInstance().load()

        Preferences.getInstance().addPreference("cura/active_mode", "simple")
        Preferences.getInstance().addPreference("cura/recent_files", "")
        Preferences.getInstance().addPreference("cura/categories_expanded", "")
        Preferences.getInstance().addPreference("cura/jobname_prefix", True)
        Preferences.getInstance().addPreference("view/center_on_select", True)
        Preferences.getInstance().addPreference("mesh/scale_to_fit", True)
        Preferences.getInstance().addPreference("mesh/scale_tiny_meshes", True)
        Preferences.getInstance().setDefault("local_file/last_used_type", "text/x-gcode")

        Preferences.getInstance().setDefault("general/visible_settings", """
            machine_settings
                resolution
                layer_height
            shell
                wall_thickness
                top_bottom_thickness
            infill
                infill_sparse_density
            material
                material_print_temperature
                material_bed_temperature
                material_diameter
                material_flow
                retraction_enable
            speed
                speed_print
                speed_travel
            travel
            cooling
                cool_fan_enabled
            support
                support_enable
                support_type
                support_roof_density
            platform_adhesion
                adhesion_type
                brim_width
                raft_airgap
                layer_0_z_overlap
                raft_surface_layers
            meshfix
            blackmagic
                print_sequence
                dual
            experimental
        """.replace("\n", ";").replace(" ", ""))

        JobQueue.getInstance().jobFinished.connect(self._onJobFinished)

        self.applicationShuttingDown.connect(self.saveSettings)

        self._recent_files = []
        files = Preferences.getInstance().getValue("cura/recent_files").split(";")
        for f in files:
            if not os.path.isfile(f):
                continue

            self._recent_files.append(QUrl.fromLocalFile(f))

    ##  Cura has multiple locations where instance containers need to be saved, so we need to handle this differently.
    #
    #   Note that the AutoSave plugin also calls this method.
    def saveSettings(self):
        if not self._started: # Do not do saving during application start
            return

        for instance in ContainerRegistry.getInstance().findInstanceContainers():
            if not instance.isDirty():
                continue

            try:
                data = instance.serialize()
            except NotImplementedError:
                continue
            except Exception:
                Logger.logException("e", "An exception occurred when serializing container %s", instance.getId())
                continue

            file_name = urllib.parse.quote_plus(instance.getId()) + ".inst.cfg"
            instance_type = instance.getMetaDataEntry("type")
            path = None
            if instance_type == "material":
                path = Resources.getStoragePath(self.ResourceTypes.MaterialInstanceContainer, file_name)
            elif instance_type == "quality":
                path = Resources.getStoragePath(self.ResourceTypes.QualityInstanceContainer, file_name)
            elif instance_type == "user":
                path = Resources.getStoragePath(self.ResourceTypes.UserInstanceContainer, file_name)
            elif instance_type == "variant":
                path = Resources.getStoragePath(self.ResourceTypes.VariantInstanceContainer, file_name)

            if path:
                with SaveFile(path, "wt", -1, "utf-8") as f:
                    f.write(data)

        for stack in ContainerRegistry.getInstance().findContainerStacks():
            if not stack.isDirty():
                continue

            try:
                data = stack.serialize()
            except NotImplementedError:
                continue
            except Exception:
                Logger.logException("e", "An exception occurred when serializing container %s", instance.getId())
                continue

            file_name = urllib.parse.quote_plus(stack.getId()) + ".stack.cfg"
            stack_type = stack.getMetaDataEntry("type", None)
            path = None
            if not stack_type or stack_type == "machine":
                path = Resources.getStoragePath(self.ResourceTypes.MachineStack, file_name)
            elif stack_type == "extruder":
                path = Resources.getStoragePath(self.ResourceTypes.ExtruderStack, file_name)
            if path:
                with SaveFile(path, "wt", -1, "utf-8") as f:
                    f.write(data)


    @pyqtSlot(result = QUrl)
    def getDefaultPath(self):
        return QUrl.fromLocalFile(os.path.expanduser("~/"))
    
    ##  Handle loading of all plugin types (and the backend explicitly)
    #   \sa PluginRegistery
    def _loadPlugins(self):
        self._plugin_registry.addType("profile_reader", self._addProfileReader)
        self._plugin_registry.addPluginLocation(os.path.join(QtApplication.getInstallPrefix(), "lib", "cura"))
        if not hasattr(sys, "frozen"):
            self._plugin_registry.addPluginLocation(os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "plugins"))
            self._plugin_registry.loadPlugin("ConsoleLogger")
            self._plugin_registry.loadPlugin("CuraEngineBackend")

        self._plugin_registry.loadPlugins()

        if self.getBackend() == None:
            raise RuntimeError("Could not load the backend plugin!")

        self._plugins_loaded = True

    def addCommandLineOptions(self, parser):
        super().addCommandLineOptions(parser)
        parser.add_argument("file", nargs="*", help="Files to load after starting the application.")
        parser.add_argument("--debug", dest="debug-mode", action="store_true", default=False, help="Enable detailed crash reports.")

    def run(self):
        self._i18n_catalog = i18nCatalog("cura");

        i18nCatalog.setTagReplacements({
            "filename": "font color=\"black\"",
            "message": "font color=UM.Theme.colors.message_text;",
        })

        self.showSplashMessage(self._i18n_catalog.i18nc("@info:progress", "Setting up scene..."))

        controller = self.getController()

        controller.setActiveView("SolidView")
        controller.setCameraTool("CameraTool")
        controller.setSelectionTool("SelectionTool")

        t = controller.getTool("TranslateTool")
        if t:
            t.setEnabledAxis([ToolHandle.XAxis, ToolHandle.YAxis,ToolHandle.ZAxis])

        Selection.selectionChanged.connect(self.onSelectionChanged)

        root = controller.getScene().getRoot()
        self._platform = Platform(root)

        self._volume = BuildVolume.BuildVolume(root)

        self.getRenderer().setBackgroundColor(QColor(245, 245, 245))

        self._physics = PlatformPhysics.PlatformPhysics(controller, self._volume)

        camera = Camera("3d", root)
        camera.setPosition(Vector(-80, 250, 700))
        camera.setPerspective(True)
        camera.lookAt(Vector(0, 0, 0))
        controller.getScene().setActiveCamera("3d")

        self.getController().getTool("CameraTool").setOrigin(Vector(0, 100, 0))

        self._camera_animation = CameraAnimation.CameraAnimation()
        self._camera_animation.setCameraTool(self.getController().getTool("CameraTool"))

        self.showSplashMessage(self._i18n_catalog.i18nc("@info:progress", "Loading interface..."))

        qmlRegisterSingletonType(MachineManagerModel.MachineManagerModel, "Cura", 1, 0, "MachineManager",
                                 MachineManagerModel.createMachineManagerModel)

        self.setMainQml(Resources.getPath(self.ResourceTypes.QmlFiles, "Cura.qml"))
        self._qml_import_paths.append(Resources.getPath(self.ResourceTypes.QmlFiles))
        self.initializeEngine()

        if self._engine.rootObjects:
            self.closeSplash()

            for file in self.getCommandLineOption("file", []):
                self._openFile(file)
            for file_name in self._open_file_queue: #Open all the files that were queued up while plug-ins were loading.
                self._openFile(file_name)

            self._started = True

            self.exec_()

    ##   Handle Qt events
    def event(self, event):
        if event.type() == QEvent.FileOpen:
            if self._plugins_loaded:
                self._openFile(event.file())
            else:
                self._open_file_queue.append(event.file())

        return super().event(event)

    ##  Get print information (duration / material used)
    def getPrintInformation(self):
        return self._print_information

    def registerObjects(self, engine):
        engine.rootContext().setContextProperty("Printer", self)
        self._print_information = PrintInformation.PrintInformation()
        engine.rootContext().setContextProperty("PrintInformation", self._print_information)
        self._cura_actions = CuraActions.CuraActions(self)
        engine.rootContext().setContextProperty("CuraActions", self._cura_actions)

        qmlRegisterUncreatableType(CuraApplication, "Cura", 1, 0, "ResourceTypes", "Just an Enum type")

        qmlRegisterType(ExtrudersModel.ExtrudersModel, "Cura", 1, 0, "ExtrudersModel")

        qmlRegisterSingletonType(QUrl.fromLocalFile(Resources.getPath(CuraApplication.ResourceTypes.QmlFiles, "Actions.qml")), "Cura", 1, 0, "Actions")

        for path in Resources.getAllResourcesOfType(CuraApplication.ResourceTypes.QmlFiles):
            type_name = os.path.splitext(os.path.basename(path))[0]
            if type_name in ("Cura", "Actions"):
                continue

            qmlRegisterType(QUrl.fromLocalFile(path), "Cura", 1, 0, type_name)

    def onSelectionChanged(self):
        if Selection.hasSelection():
            if not self.getController().getActiveTool():
                if self._previous_active_tool:
                    self.getController().setActiveTool(self._previous_active_tool)
                    self._previous_active_tool = None
                else:
                    self.getController().setActiveTool("TranslateTool")
            if Preferences.getInstance().getValue("view/center_on_select"):
                self._center_after_select = True
        else:
            if self.getController().getActiveTool():
                self._previous_active_tool = self.getController().getActiveTool().getPluginId()
                self.getController().setActiveTool(None)
            else:
                self._previous_active_tool = None

    def _onToolOperationStopped(self, event):
        if self._center_after_select:
            self._center_after_select = False
            self._camera_animation.setStart(self.getController().getTool("CameraTool").getOrigin())
            self._camera_animation.setTarget(Selection.getSelectedObject(0).getWorldPosition())
            self._camera_animation.start()

    requestAddPrinter = pyqtSignal()
    activityChanged = pyqtSignal()
    sceneBoundingBoxChanged = pyqtSignal()

    @pyqtProperty(bool, notify = activityChanged)
    def getPlatformActivity(self):
        return self._platform_activity

    @pyqtProperty(str, notify = sceneBoundingBoxChanged)
    def getSceneBoundingBoxString(self):
        return self._i18n_catalog.i18nc("@info", "%(width).1f x %(depth).1f x %(height).1f mm") % {'width' : self._scene_bounding_box.width.item(), 'depth': self._scene_bounding_box.depth.item(), 'height' : self._scene_bounding_box.height.item()}

    def updatePlatformActivity(self, node = None):
        count = 0
        scene_bounding_box = None
        for node in DepthFirstIterator(self.getController().getScene().getRoot()):
            if type(node) is not SceneNode or not node.getMeshData():
                continue

            count += 1
            if not scene_bounding_box:
                scene_bounding_box = copy.deepcopy(node.getBoundingBox())
            else:
                scene_bounding_box += node.getBoundingBox()

        if not scene_bounding_box:
            scene_bounding_box = AxisAlignedBox()

        if repr(self._scene_bounding_box) != repr(scene_bounding_box):
            self._scene_bounding_box = scene_bounding_box
            self.sceneBoundingBoxChanged.emit()

        self._platform_activity = True if count > 0 else False
        self.activityChanged.emit()

    # Remove all selected objects from the scene.
    @pyqtSlot()
    def deleteSelection(self):
        if not self.getController().getToolsEnabled():
            return

        op = GroupedOperation()
        nodes = Selection.getAllSelectedObjects()
        for node in nodes:
            op.addOperation(RemoveSceneNodeOperation(node))

        op.push()

        pass

    ##  Remove an object from the scene.
    #   Note that this only removes an object if it is selected.
    @pyqtSlot("quint64")
    def deleteObject(self, object_id):
        if not self.getController().getToolsEnabled():
            return

        node = self.getController().getScene().findObject(object_id)

        if not node and object_id != 0:  # Workaround for tool handles overlapping the selected object
            node = Selection.getSelectedObject(0)

        if node:
            if node.getParent():
                group_node = node.getParent()
                if not group_node.callDecoration("isGroup"):
                    op = RemoveSceneNodeOperation(node)
                else:
                    while group_node.getParent().callDecoration("isGroup"):
                        group_node = group_node.getParent()
                    op = RemoveSceneNodeOperation(group_node)
            op.push()

    ##  Create a number of copies of existing object.
    @pyqtSlot("quint64", int)
    def multiplyObject(self, object_id, count):
        node = self.getController().getScene().findObject(object_id)

        if not node and object_id != 0:  # Workaround for tool handles overlapping the selected object
            node = Selection.getSelectedObject(0)

        if node:
            op = GroupedOperation()
            for _ in range(count):
                if node.getParent() and node.getParent().callDecoration("isGroup"):
                    new_node = copy.deepcopy(node.getParent()) #Copy the group node.
                    new_node.callDecoration("setConvexHull",None)

                    op.addOperation(AddSceneNodeOperation(new_node,node.getParent().getParent()))
                else:
                    new_node = copy.deepcopy(node)
                    new_node.callDecoration("setConvexHull", None)
                    op.addOperation(AddSceneNodeOperation(new_node, node.getParent()))

            op.push()

    ##  Center object on platform.
    @pyqtSlot("quint64")
    def centerObject(self, object_id):
        node = self.getController().getScene().findObject(object_id)
        if not node and object_id != 0:  # Workaround for tool handles overlapping the selected object
            node = Selection.getSelectedObject(0)

        if not node:
            return

        if node.getParent() and node.getParent().callDecoration("isGroup"):
            node = node.getParent()

        if node:
            op = SetTransformOperation(node, Vector())
            op.push()
    
    ##  Delete all nodes containing mesh data in the scene.
    @pyqtSlot()
    def deleteAll(self):
        if not self.getController().getToolsEnabled():
            return

        nodes = []
        for node in DepthFirstIterator(self.getController().getScene().getRoot()):
            if type(node) is not SceneNode:
                continue
            if not node.getMeshData() and not node.callDecoration("isGroup"):
                continue  # Node that doesnt have a mesh and is not a group.
            if node.getParent() and node.getParent().callDecoration("isGroup"):
                continue  # Grouped nodes don't need resetting as their parent (the group) is resetted)
            nodes.append(node)
        if nodes:
            op = GroupedOperation()

            for node in nodes:
                op.addOperation(RemoveSceneNodeOperation(node))

            op.push()

    ## Reset all translation on nodes with mesh data. 
    @pyqtSlot()
    def resetAllTranslation(self):
        nodes = []
        for node in DepthFirstIterator(self.getController().getScene().getRoot()):
            if type(node) is not SceneNode:
                continue
            if not node.getMeshData() and not node.callDecoration("isGroup"):
                continue  # Node that doesnt have a mesh and is not a group.
            if node.getParent() and node.getParent().callDecoration("isGroup"):
                continue  # Grouped nodes don't need resetting as their parent (the group) is resetted)

            nodes.append(node)

        if nodes:
            op = GroupedOperation()
            for node in nodes:
                node.removeDecorator(ZOffsetDecorator.ZOffsetDecorator)
                op.addOperation(SetTransformOperation(node, Vector(0,0,0)))

            op.push()
    
    ## Reset all transformations on nodes with mesh data. 
    @pyqtSlot()
    def resetAll(self):
        nodes = []
        for node in DepthFirstIterator(self.getController().getScene().getRoot()):
            if type(node) is not SceneNode:
                continue
            if not node.getMeshData() and not node.callDecoration("isGroup"):
                continue  # Node that doesnt have a mesh and is not a group.
            if node.getParent() and node.getParent().callDecoration("isGroup"):
                continue  # Grouped nodes don't need resetting as their parent (the group) is resetted)
            nodes.append(node)

        if nodes:
            op = GroupedOperation()

            for node in nodes:
                # Ensure that the object is above the build platform
                node.removeDecorator(ZOffsetDecorator.ZOffsetDecorator)
                op.addOperation(SetTransformOperation(node, Vector(0,0,0), Quaternion(), Vector(1, 1, 1)))

            op.push()
            
    ##  Reload all mesh data on the screen from file.
    @pyqtSlot()
    def reloadAll(self):
        nodes = []
        for node in DepthFirstIterator(self.getController().getScene().getRoot()):
            if type(node) is not SceneNode or not node.getMeshData():
                continue

            nodes.append(node)

        if not nodes:
            return

        for node in nodes:
            if not node.getMeshData():
                continue

            file_name = node.getMeshData().getFileName()
            if file_name:
                job = ReadMeshJob(file_name)
                job._node = node
                job.finished.connect(self._reloadMeshFinished)
                job.start()
    
    ##  Get logging data of the backend engine
    #   \returns \type{string} Logging data
    @pyqtSlot(result = str)
    def getEngineLog(self):
        log = ""

        for entry in self.getBackend().getLog():
            log += entry.decode()

        return log

    recentFilesChanged = pyqtSignal()

    @pyqtProperty("QVariantList", notify = recentFilesChanged)
    def recentFiles(self):
        return self._recent_files

    @pyqtSlot("QStringList")
    def setExpandedCategories(self, categories):
        categories = list(set(categories))
        categories.sort()
        joined = ";".join(categories)
        if joined != Preferences.getInstance().getValue("cura/categories_expanded"):
            Preferences.getInstance().setValue("cura/categories_expanded", joined)
            self.expandedCategoriesChanged.emit()

    expandedCategoriesChanged = pyqtSignal()

    @pyqtProperty("QStringList", notify = expandedCategoriesChanged)
    def expandedCategories(self):
        return Preferences.getInstance().getValue("cura/categories_expanded").split(";")

    @pyqtSlot()
    def mergeSelected(self):
        self.groupSelected()
        try:
            group_node = Selection.getAllSelectedObjects()[0]
        except Exception as e:
            Logger.log("d", "mergeSelected: Exception:", e)
            return
        multi_material_decorator = MultiMaterialDecorator.MultiMaterialDecorator()
        group_node.addDecorator(multi_material_decorator)
        # Reset the position of each node
        for node in group_node.getChildren():
            new_position = node.getMeshData().getCenterPosition()
            new_position = new_position.scale(node.getScale())
            node.setPosition(new_position)
        
        # Use the previously found center of the group bounding box as the new location of the group
        group_node.setPosition(group_node.getBoundingBox().center)

    @pyqtSlot()
    def groupSelected(self):
        # Create a group-node
        group_node = SceneNode()
        group_decorator = GroupDecorator()
        group_node.addDecorator(group_decorator)
        group_node.setParent(self.getController().getScene().getRoot())
        group_node.setSelectable(True)
        center = Selection.getSelectionCenter()
        group_node.setPosition(center)
        group_node.setCenterPosition(center)

        # Move selected nodes into the group-node
        Selection.applyOperation(SetParentOperation, group_node)

        # Deselect individual nodes and select the group-node instead
        for node in group_node.getChildren():
            Selection.remove(node)
        Selection.add(group_node)

    @pyqtSlot()
    def ungroupSelected(self):
        selected_objects = Selection.getAllSelectedObjects().copy()
        for node in selected_objects:
            if node.callDecoration("isGroup"):
                op = GroupedOperation()

                group_parent = node.getParent()
                children = node.getChildren().copy()
                for child in children:
                    # Set the parent of the children to the parent of the group-node
                    op.addOperation(SetParentOperation(child, group_parent))

                    # Add all individual nodes to the selection
                    Selection.add(child)
                    child.callDecoration("setConvexHull", None)

                op.push()
                # Note: The group removes itself from the scene once all its children have left it,
                # see GroupDecorator._onChildrenChanged

    def _createSplashScreen(self):
        return CuraSplashScreen.CuraSplashScreen()

    def _onActiveMachineChanged(self):
        pass

    fileLoaded = pyqtSignal(str)

    def _onFileLoaded(self, job):
        node = job.getResult()
        if node != None:
            self.fileLoaded.emit(job.getFileName())
            node.setSelectable(True)
            node.setName(os.path.basename(job.getFileName()))
            op = AddSceneNodeOperation(node, self.getController().getScene().getRoot())
            op.push()

            self.getController().getScene().sceneChanged.emit(node) #Force scene change.

    def _onJobFinished(self, job):
        if type(job) is not ReadMeshJob or not job.getResult():
            return

        f = QUrl.fromLocalFile(job.getFileName())
        if f in self._recent_files:
            self._recent_files.remove(f)

        self._recent_files.insert(0, f)
        if len(self._recent_files) > 10:
            del self._recent_files[10]

        pref = ""
        for path in self._recent_files:
            pref += path.toLocalFile() + ";"

        Preferences.getInstance().setValue("cura/recent_files", pref)
        self.recentFilesChanged.emit()

    def _reloadMeshFinished(self, job):
        # TODO; This needs to be fixed properly. We now make the assumption that we only load a single mesh!
        job._node.setMeshData(job.getResult().getMeshData())

    def _openFile(self, file):
        job = ReadMeshJob(os.path.abspath(file))
        job.finished.connect(self._onFileLoaded)
        job.start()

    def _addProfileReader(self, profile_reader):
        # TODO: Add the profile reader to the list of plug-ins that can be used when importing profiles.
        pass
