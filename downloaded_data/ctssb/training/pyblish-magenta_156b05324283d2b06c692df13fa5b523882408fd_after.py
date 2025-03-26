import pyblish.api
import pyblish_magenta.api


class ValidateRigContents(pyblish.api.InstancePlugin):
    """Ensure rig contains pipeline-critical content

    Every rig must contain at least two object sets:
        "controls_SET" - Set of all animatable controls
        "pointcache_SET" - Set of all cachable meshes

    """

    order = pyblish_magenta.api.ValidateContentsOrder
    label = "Rig Contents"
    families = ["rig"]
    hosts = ["maya"]

    def process(self, instance):
        from maya import cmds

        objsets = ("controls_SET", "pointcache_SET")

        missing = list()
        for objset in objsets:
            if objset not in instance:
                missing.append(objset)

        assert not missing, ("%s is missing %s"
                             % (instance, missing))

        # Ensure there are at least some transforms or dag nodes
        # in the rig instance
        set_members = cmds.sets(instance.data['objSetName'], query=True) or []
        if not cmds.ls(set_members, type="dagNode", long=True):
            raise RuntimeError("No dag nodes in the pointcache instance. "
                               "(Empty instance?)")

        self.log.info("Evaluating contents of object sets..")
        not_meshes = list()
        members = cmds.sets("pointcache_SET", query=True) or []
        shapes = cmds.listRelatives(members,
                                    allDescendents=True,
                                    shapes=True,
                                    fullPath=True) or []
        for shape in shapes:
            if cmds.nodeType(shape) != "mesh":
                not_meshes.append(shape)

        not_transforms = list()
        for node in cmds.sets("controls_SET", query=True) or []:
            if cmds.nodeType(node) != "transform":
                not_transforms.append(node)

        assert not_transforms == [], (
            "Only transforms can be part of the controls_SET: %s"
            % not_transforms)

        assert not_meshes == [], (
            "Only meshes can be part of the pointcache_SET: %s"
            % not_meshes)
