from UM.Workspace.WorkspaceReader import WorkspaceReader
from UM.Application import Application

from UM.Logger import Logger
from UM.Settings.ContainerStack import ContainerStack
from UM.Settings.DefinitionContainer import DefinitionContainer
from UM.Settings.InstanceContainer import InstanceContainer
from UM.Settings.ContainerRegistry import ContainerRegistry

import zipfile


##    Base implementation for reading 3MF workspace files.
class ThreeMFWorkspaceReader(WorkspaceReader):
    def __init__(self):
        super().__init__()
        self._supported_extensions = [".3mf"]

        self._3mf_mesh_reader = None

    def preRead(self, file_name):
        self._3mf_mesh_reader = Application.getInstance().getMeshFileHandler().getReaderForFile(file_name)
        if self._3mf_mesh_reader and self._3mf_mesh_reader.preRead(file_name) == WorkspaceReader.PreReadResult.accepted:
            pass
        else:
            Logger.log("w", "Could not find reader that was able to read the scene data for 3MF workspace")
            return WorkspaceReader.PreReadResult.failed
        # TODO: Ask user if it's  okay for the scene to be cleared
        return WorkspaceReader.PreReadResult.accepted

    def read(self, file_name):
        # Load all the nodes / meshdata of the workspace
        nodes = self._3mf_mesh_reader.read(file_name)
        if nodes is None:
            nodes = []

        container_registry = ContainerRegistry.getInstance()
        archive = zipfile.ZipFile(file_name, "r")

        cura_file_names = [name for name in archive.namelist() if name.startswith("Cura/")]

        # TODO: For the moment we use pretty naive existence checking. If the ID is the same, we assume in quite a few
        # TODO: cases that the container loaded is the same (most notable in materials & definitions).
        # TODO: It might be possible that we need to add smarter checking in the future.

        # Get all the definition files & check if they exist. If not, add them.
        definition_container_suffix = ContainerRegistry.getMimeTypeForContainer(DefinitionContainer).suffixes[0]
        definition_container_files = [name for name in cura_file_names if name.endswith(definition_container_suffix)]
        for definition_container_file in definition_container_files:
            container_id = definition_container_file.replace("Cura/", "")
            container_id = container_id.replace(".%s" % definition_container_suffix, "")
            definitions = container_registry.findDefinitionContainers(id=container_id)
            if not definitions:
                definition_container = DefinitionContainer(container_id)
                definition_container.deserialize(archive.open(definition_container_file).read().decode("utf-8"))
                container_registry.addContainer(definition_container)

        # Get all the material files and check if they exist. If not, add them.
        xml_material_profile = None
        for type_name, container_type in container_registry.getContainerTypes():
            if type_name == "XmlMaterialProfile":
                xml_material_profile = container_type
                break

        if xml_material_profile:
            material_container_suffix = ContainerRegistry.getMimeTypeForContainer(xml_material_profile).suffixes[0]
            material_container_files = [name for name in cura_file_names if name.endswith(material_container_suffix)]
            for material_container_file in material_container_files:
                container_id = material_container_file.replace("Cura/", "")
                container_id = container_id.replace(".%s" % material_container_suffix, "")
                materials = container_registry.findInstanceContainers(id=container_id)
                if not materials:
                    material_container = xml_material_profile(container_id)
                    material_container.deserialize(archive.open(material_container_file).read().decode("utf-8"))
                    container_registry.addContainer(material_container)

        # Get quality_changes and user profiles saved in the workspace
        instance_container_suffix = ContainerRegistry.getMimeTypeForContainer(InstanceContainer).suffixes[0]
        instance_container_files = [name for name in cura_file_names if name.endswith(instance_container_suffix)]
        user_instance_containers = []
        quality_changes_instance_containers = []
        for instance_container_file in instance_container_files:
            container_id = instance_container_file.replace("Cura/", "")
            container_id = container_id.replace(".%s" % instance_container_suffix, "")
            instance_container = InstanceContainer(container_id)

            # Deserialize InstanceContainer by converting read data from bytes to string
            instance_container.deserialize(archive.open(instance_container_file).read().decode("utf-8"))
            container_type = instance_container.getMetaDataEntry("type")
            if container_type == "user":
                user_instance_containers.append(instance_container)
            elif container_type == "quality_changes":
                quality_changes_instance_containers.append(instance_container)
            else:
                continue

        # Get the stack(s) saved in the workspace.
        '''container_stack_suffix = ContainerRegistry.getMimeTypeForContainer(ContainerStack).suffixes[0]
        container_stack_files = [name for name in cura_file_names if name.endswith(container_stack_suffix)]
        global_stack = None
        extruder_stacks = []
        for container_stack_file in container_stack_files:
            container_id = container_stack_file.replace("Cura/", "")
            container_id = container_id.replace(".%s" % container_stack_suffix, "")

            # Check if a stack by this ID already exists;
            container_stacks = container_registry.findContainerStacks(id = container_id)
            if container_stacks:
                print("CONTAINER ALREADY EXISTSSS")

            #stack = ContainerStack(container_id)

            # Deserialize stack by converting read data from bytes to string
            stack.deserialize(archive.open(container_stack_file).read().decode("utf-8"))

            if stack.getMetaDataEntry("type") == "extruder_train":
                extruder_stacks.append(stack)
            else:
                global_stack = stack'''

        return nodes
