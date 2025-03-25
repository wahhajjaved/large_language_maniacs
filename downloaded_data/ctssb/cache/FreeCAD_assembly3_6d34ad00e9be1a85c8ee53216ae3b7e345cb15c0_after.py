import random, math
from collections import namedtuple
import FreeCAD, FreeCADGui
from .assembly import Assembly, isTypeOf, setPlacement
from . import utils
from .utils import syslogger as logger, objName, isSamePlacement
from .constraint import Constraint, cstrName, \
                        NormalInfo, PlaneInfo, PointInfo
from .system import System

# Part: the part object
# PartName: text name of the part
# Placement: the original placement of the part
# Params: 7 parameters that defines the transformation of this part
# Workplane: a tuple of four entity handles, that is the workplane, the origin
#            point, and the normal, and x pointing normal. The workplane,
#            defined by the origin and norml, is essentially the XY reference
#            plane of the part.
# EntityMap: string -> entity handle map, for caching
# Group: transforming entity group handle
# CstrMap: map from other part to the constrains between this and the othe part.
#          This is for auto constraint DOF reduction. Only some composite
#          constraints will be mapped.
PartInfo = namedtuple('SolverPartInfo', ('Part','PartName','Placement',
    'Params','Workplane','EntityMap','Group','CstrMap'))

class Solver(object):
    def __init__(self,assembly,reportFailed,dragPart,recompute,rollback):
        self.system = System.getSystem(assembly)
        cstrs = assembly.Proxy.getConstraints()
        if not cstrs:
            logger.debug('skip assembly {} with no constraint'.format(
                objName(assembly)))
            return

        self._fixedGroup = 2
        self.group = 1 # the solving group
        self._partMap = {}
        self._cstrMap = {}
        self._fixedElements = set()

        self.system.GroupHandle = self._fixedGroup

        # convenience constant of zero and one
        self.v0 = self.system.addParamV(0,group=self._fixedGroup)
        self.v1 = self.system.addParamV(1,group=self._fixedGroup)

        # convenience x normals
        rotx = FreeCAD.Rotation(FreeCAD.Vector(0,1,0),-90)
        self.nx = self.system.addNormal3dV(*utils.getNormal(rotx))

        # convenience x pointing vector
        self.px = self.system.addPoint3d(self.v1,self.v0,self.v0)

        # convenience y normals
        roty = FreeCAD.Rotation(FreeCAD.Vector(1,0,0),90)
        self.ny = self.system.addNormal3dV(*utils.getNormal(roty))

        parts = assembly.Proxy.getPartGroup().Group
        self._fixedParts = Constraint.getFixedParts(self,cstrs,parts)
        for part in self._fixedParts:
            self._fixedElements.add((part,None))

        for cstr in cstrs:
            self.system.log('preparing {}'.format(cstrName(cstr)))
            self.system.GroupHandle += 1
            ret = Constraint.prepare(cstr,self)
            if ret:
                if isinstance(ret,(list,tuple)):
                    for h in ret:
                        if not isinstance(h,(list,tuple)):
                            self._cstrMap[h] = cstr
                else:
                    self._cstrMap[ret] = cstr

        if dragPart:
            # TODO: this is ugly, need a better way to expose dragging interface
            addDragPoint = getattr(self.system,'addWhereDragged',None)
            if addDragPoint:
                info = self._partMap.get(dragPart,None)
                if info and info.Workplane:
                    # add dragging point
                    self.system.log('add drag point '
                        '{}'.format(info.Workplane[1]))
                    # TODO: slvs addWhereDragged doesn't work as expected, need
                    # to investigate more
                    # addDragPoint(info.Workplane[1],group=self.group)

        self.system.log('solving {}'.format(objName(assembly)))
        try:
            self.system.solve(group=self.group,reportFailed=reportFailed)
        except RuntimeError as e:
            if reportFailed and self.system.Failed:
                msg = 'List of failed constraint:'
                for h in self.system.Failed:
                    cstr = self._cstrMap.get(h,None)
                    if not cstr:
                        try:
                            c = self.system.getConstraint(h)
                        except Exception as e2:
                            logger.error('cannot find failed constraint '
                                    '{}: {}'.format(h,e2))
                            continue
                        if c.group <= self._fixedGroup or \
                           c.group-self._fixedGroup >= len(cstrs):
                            logger.error('failed constraint in unexpected group'
                                    ' {}'.format(c.group))
                            continue
                        cstr = cstrs[c.group-self._fixedGroup]
                    msg += '\n{}, handle: {}'.format(cstrName(cstr),h)
                logger.error(msg)
            raise RuntimeError('Failed to solve {}: {}'.format(
                objName(assembly),e.message))
        self.system.log('done solving')

        touched = False
        for part,partInfo in self._partMap.items():
            if part in self._fixedParts:
                continue
            if utils.isDraftWire(part):
                changed = False
                points = part.Points
                for key,h in partInfo.EntityMap.items():
                    if not isinstance(key, str) or\
                       not key.endswith('.p') or\
                       not key.startswith('Vertex'):
                        continue
                    v = [ self.system.getParam(p).val for p in h.params ]
                    v = FreeCAD.Vector(*v)
                    v = partInfo.Placement.inverse().multVec(v)
                    idx = utils.draftWireVertex2PointIndex(part,key[:-2])
                    if utils.isSamePos(points[idx],v):
                        self.system.log('not moving {} point {}'.format(
                            partInfo.PartName,idx))
                    else:
                        changed = True
                        self.system.log('moving {} point{} from {}->{}'.format(
                            partInfo.PartName,idx,points[idx],v))
                        if rollback is not None:
                            rollback.append((partInfo.PartName,
                                             part,
                                             (idx, points[idx])))
                        points[idx] = v
                if changed:
                    touched = True
                    part.Points = points
            else:
                params = [self.system.getParam(h).val for h in partInfo.Params]
                p = params[:3]
                q = (params[4],params[5],params[6],params[3])
                pla = FreeCAD.Placement(FreeCAD.Vector(*p),FreeCAD.Rotation(*q))
                if isSamePlacement(partInfo.Placement,pla):
                    self.system.log('not moving {}'.format(partInfo.PartName))
                else:
                    touched = True
                    self.system.log('moving {} {} {} {}'.format(
                        partInfo.PartName,partInfo.Params,params,pla))
                    if rollback is not None:
                        rollback.append((partInfo.PartName,
                                        part,
                                        partInfo.Placement.copy()))
                    setPlacement(part,pla)

                if utils.isDraftCircle(part):
                    changed = False
                    h = partInfo.EntityMap.get('Edge1.c',None)
                    if not h:
                        continue
                    v0 = (part.Radius.Value,
                          part.FirstAngle.Value,
                          part.LastAngle.Value)
                    if part.FirstAngle == part.LastAngle:
                        v = (self.system.getParam(h.radius).val,v0[1],v0[2])
                    else:
                        params = [self.system.getParam(p).val for p in h.params]
                        p0 = FreeCAD.Vector(1,0,0)
                        p1 = FreeCAD.Vector(params[0],params[1],0)
                        p2 = FreeCAD.Vector(params[2],params[3],0)
                        v = (p1.Length,
                             math.degrees(p0.getAngle(p1)),
                             math.degrees(p0.getAngle(p2)))

                    if utils.isSameValue(v0,v):
                        self.system.log('not change draft circle {}'.format(
                            partInfo.PartName))
                    else:
                        touched = True
                        self.system.log('change draft circle {} {}->{}'.format(
                            partInfo.PartName,v0,v))
                        if rollback is not None:
                            rollback.append((partInfo.PartName, part, v0))
                        part.Radius = v[0]
                        part.FirstAngle = v[1]
                        part.LastAngle = v[2]

        if recompute and touched:
            assembly.recompute(True)

    def isFixedPart(self,part):
        return part in self._fixedParts

    def isFixedElement(self,part,subname):
        return (part,None) in self._fixedElements or \
               (part,subname) in self._fixedElements

    def addFixedElement(self,part,subname):
        self._fixedElements.add((part,subname))

    def getPartInfo(self,info,fixed=False,group=0):
        partInfo = self._partMap.get(info.Part,None)
        if partInfo:
            return partInfo

        if fixed or info.Part in self._fixedParts:
            g = self._fixedGroup
        else:
            g = self.group

        if utils.isDraftWire(info):
            # Special treatment for draft wire. We do not change its placement,
            # but individual point position, instead.
            params = None
            h = None
        else:
            self.system.NameTag = info.PartName
            params = self.system.addPlacement(info.Placement,group=g)

            self.system.NameTag = info.PartName + '.p'
            p = self.system.addPoint3d(*params[:3],group=g)
            self.system.NameTag = info.PartName + '.n'
            n = self.system.addNormal3d(*params[3:],group=g)
            self.system.NameTag = info.PartName + '.np0'
            p0 = self.system.addPoint3d(self.v0,self.v0,self.v0,group=g)
            self.system.NameTag = info.PartName + '.np1'
            p1 = self.system.addPoint3d(self.v0,self.v0,self.v1,group=g)
            self.system.NameTag = info.PartName + '.l'
            ln = self.system.addLineSegment(p0,p1,group=g)
            self.system.NameTag = info.PartName + '.w'
            w = self.system.addWorkplane(p,n,group=g)
            h = PlaneInfo(entity=w,
                    origin=PointInfo(entity=p, params=None,
                                     vector=FreeCAD.Vector()),
                    normal=NormalInfo(entity=n,rot=FreeCAD.Rotation(),
                                      params=params,p0=p0,ln=ln))

        partInfo = PartInfo(Part = info.Part,
                            PartName = info.PartName,
                            Placement = info.Placement.copy(),
                            Params = params,
                            Workplane = h,
                            EntityMap = {},
                            Group = group if group else g,
                            CstrMap = {})

        self.system.log('{}, {}'.format(partInfo,g))

        self._partMap[info.Part] = partInfo
        return partInfo

def _solve(objs=None,recursive=None,reportFailed=True,
        recompute=True,dragPart=None,rollback=None):
    if not objs:
        sels = FreeCADGui.Selection.getSelectionEx('',False)
        if len(sels):
            objs = Assembly.getSelection()
            if not objs:
                raise RuntimeError('No assembly found in selection')
        else:
            objs = FreeCAD.ActiveDocument.Objects
        if recursive is None:
            recursive = True
    elif not isinstance(objs,(list,tuple)):
        objs = [objs]

    assemblies = []
    for obj in objs:
        if not isTypeOf(obj,Assembly):
            continue
        if System.isDisabled(obj):
            logger.debug('bypass disabled assembly {}'.format(objName(obj)))
            continue
        logger.debug('adding assembly {}'.format(objName(obj)))
        assemblies.append(obj)

    if not assemblies:
        logger.info('no assembly found')
        return True

    if recursive:
        # Get all dependent object, including external ones, and return as a
        # topologically sorted list.
        #
        # TODO: it would be ideal if we can filter out those disabled assemblies
        # found during the recrusive search. Can't think of an easy way right
        # now
        objs = FreeCAD.getDependentObjects(assemblies,False,True)
        assemblies = []
        for obj in objs:
            if not isTypeOf(obj,Assembly):
                continue
            if System.isDisabled(obj):
                logger.debug('skip disabled assembly {}'.format(objName(obj)))
                continue
            logger.debug('adding assembly {}'.format(objName(obj)))
            assemblies.append(obj)

        if not assemblies:
            raise RuntimeError('no assembly need to be solved')

    try:
        for assembly in assemblies:
            if recompute:
                assembly.recompute(True)
            if not System.isTouched(assembly):
                logger.debug('skip untouched assembly '
                    '{}'.format(objName(assembly)))
                continue
            Solver(assembly,reportFailed,dragPart,recompute,rollback)
            System.touch(assembly,False)
    except Exception:
        if rollback is not None:
            for name,part,v in reversed(rollback):
                logger.debug('roll back {} to {}'.format(name,v))
                if isinstance(v,FreeCAD.Placement):
                    setPlacement(part,v)
                elif utils.isDraftWire(part):
                    idx,pt = v
                    part.Points[idx] = pt
                elif utils.isDraftWire(part):
                    r,a1,a2 = v
                    part.Radius = r
                    part.FirstAngle = a1
                    part.LastAngle = a2

        raise

    return True

_SolverBusy = False

def solve(*args, **kargs):
    global _SolverBusy
    if _SolverBusy:
        raise RuntimeError("Recursive call of solve() is not allowed")
    try:
        Assembly.cancelAutoSolve();
        _SolverBusy = True
        return _solve(*args,**kargs)
    finally:
        _SolverBusy = False

def isBusy():
    return _SolverBusy

