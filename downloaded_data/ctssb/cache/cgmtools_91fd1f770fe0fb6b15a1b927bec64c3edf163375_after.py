# From Python =============================================================
import copy
import re

#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# From Maya =============================================================
import maya.cmds as mc

# From Red9 =============================================================
from Red9.core import Red9_Meta as r9Meta
from Red9.core import Red9_General as r9General

# From cgm ==============================================================
from cgm.core import cgm_Meta as cgmMeta
from cgm.lib import (cgmMath,
                     joints,
                     rigging,
                     attributes,
                     locators,
                     distance,
                     autoname,
                     search,
                     curves,
                     dictionary,
                     lists,
                     settings,
                     modules)
reload(joints)
reload(cgmMath)
from cgm.core.lib import nameTools
typesDictionary = dictionary.initializeDictionary(settings.getTypesDictionaryFile())
namesDictionary = dictionary.initializeDictionary( settings.getNamesDictionaryFile())
settingsDictionary = dictionary.initializeDictionary( settings.getSettingsDictionaryFile())
#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# Modules
#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> 
class go(object):
    @r9General.Timer
    def __init__(self,moduleInstance,forceNew = True,saveTemplatePose = True,**kws): 
        """
        To do:
        Add rotation order settting
        Add module parent check to make sure parent is templated to be able to move forward, or to constrain
        Add any other piece meal data necessary
        Add a cleaner to force a rebuild
        """
        # Get our base info
        #==============	        
        #>>> module null data 
        assert moduleInstance.mClass in ['cgmModule','cgmLimb'],"Not a module"
        assert moduleInstance.isTemplated(),"Module is not templated"
        #assert object is templated
        #assert ...
        log.info(">>> JointFactory.go.__init__")
        self.cls = "JointFactory.go"
        self.m = moduleInstance# Link for shortness
        
        if moduleInstance.isSkeletonized():
            if forceNew:
                deleteSkeleton(moduleInstance)
            else:
                log.warning("'%s' has already been skeletonized"%moduleInstance.getShortName())
                return        
        
        #>>> store template settings
        if saveTemplatePose:
            log.info("Saving template pose in JointFactory.go")
            self.m.storeTemplatePose()
        
        self.rigNull = self.m.getMessage('rigNull')[0] or False
        self.i_rigNull = self.m.rigNull
        self.moduleColors = self.m.getModuleColors()
        self.l_coreNames = self.m.i_coreNames.value
        self.foundDirections = False #Placeholder to see if we have it
                
        #>>> part name 
        self.partName = nameTools.returnRawGeneratedName(self.m.mNode, ignore = 'cgmType')
        self.partType = self.m.moduleType or False
        
        self.direction = None
        if self.m.hasAttr('cgmDirection'):
            self.direction = self.m.cgmDirection or None
        
        #>>> template null 
        self.i_templateNull = self.m.templateNull
        self.curveDegree = self.i_templateNull.curveDegree
        
        #>>> Instances and joint stuff
        self.jointOrientation = modules.returnSettingsData('jointOrientation')
        self.i_root = self.i_templateNull.root
        self.i_orientRootHelper = self.i_templateNull.orientRootHelper
        self.i_curve = self.i_templateNull.curve
        self.i_controlObjects = self.i_templateNull.controlObjects
        
        log.debug("Module: %s"%self.m.getShortName())
        log.debug("partType: %s"%self.partType)
        log.debug("direction: %s"%self.direction) 
        log.debug("colors: %s"%self.moduleColors)
        log.debug("coreNames: %s"%self.l_coreNames)
        log.debug("root: %s"%self.i_root.getShortName())
        log.debug("curve: %s"%self.i_curve.getShortName())
        log.debug("orientRootHelper: %s"%self.i_orientRootHelper.getShortName())
        log.debug("rollJoints: %s"%self.i_templateNull.rollJoints)
        log.debug("jointOrientation: %s"%self.jointOrientation)
        
        if self.m.mClass == 'cgmLimb':
            log.info("mode: cgmLimb Skeletonize")
            doSkeletonize(self)
        else:
            raise NotImplementedError,"haven't implemented '%s' templatizing yet"%self.m.mClass
        
#@r9General.Timer
def doSkeletonize(self):
    """ 
    DESCRIPTION:
    Basic limb skeletonizer
    
    ARGUMENTS:
    stiffIndex(int) - the index of the template objects you want to not have roll joints
                      For example, a value of -1 will let the chest portion of a spine 
                      segment be solid instead of having a roll segment. Default is the modules setting
    RETURNS:
    l_limbJoints(list)
    """
    log.info(">>> doSkeletonize")
    # Get our base info
    #==================	        
    assert self.cls == 'JointFactory.go',"Not a JointFactory.go instance!"
    assert mc.objExists(self.m.mNode),"module no longer exists"
    curve = self.i_curve.mNode
    partName = self.partName
    l_limbJoints = []
    
    #>>> Check roll joint args
    rollJoints = self.i_templateNull.rollJoints
    d_rollJointOverride = self.i_templateNull.rollOverride
    if type(d_rollJointOverride) is not dict:
        d_rollJointOverride = False
    
    #>>> See if we have have a suitable parent joint to use
    # We'll know it is if the first template position shares an equivalent position with it's parentModule
    #======================================================
    i_parentJointToUse = False
    
    pos = distance.returnWorldSpacePosition( self.i_templateNull.getMessage('controlObjects')[0] )
    log.info("pos: %s"%pos)
    #Get parent position, if we have one
    if self.m.getMessage('moduleParent'):
        log.info("Found moduleParent, checking joints...")
        i_parentRigNull = self.m.moduleParent.rigNull
        parentJoints = i_parentRigNull.getMessage('skinJoints',False)
        log.info(parentJoints)
        if parentJoints:
            parent_pos = distance.returnWorldSpacePosition( parentJoints[-1] )
            log.info("parentPos: %s"%parent_pos)  
            
        log.info("Equivalent: %s"%cgmMath.isVectorEquivalent(pos,parent_pos))
        if cgmMath.isVectorEquivalent(pos,parent_pos):#if they're equivalent
            i_parentJointToUse = cgmMeta.cgmObject(parentJoints[-1])
            
    #>>> Make if our segment only has one handle
    #==========================================	
    if len(self.i_controlObjects) == 1:
        if i_parentJointToUse:
            log.info("Single joint: moduleParent mode")
            #Need to grab the last joint for this module
            l_limbJoints = [parentJoints[-1]]
            i_parentRigNull.connectChildrenNodes(parentJoints[:-1],'skinJoints','module')
        else:
            log.info("Single joint: no parent mode")
            l_limbJoints.append ( mc.joint (p=(pos[0],pos[1],pos[2]))) 
    else:
        if i_parentJointToUse:
            #We're going to reconnect all but the last joint back to the parent module and delete the last parent joint which we're replacing
            i_parentRigNull.connectChildrenNodes(parentJoints[:-1],'skinJoints','module')
            mc.delete(i_parentJointToUse.mNode)
            
        #>>> Make the limb segment
        #==========================	 
        l_spanUPositions = []
        #>>> Divide stuff
        for i_obj in self.i_controlObjects:#These are our base span u positions on the curve
            l_spanUPositions.append(distance.returnNearestPointOnCurveInfo(i_obj.mNode,curve)['parameter'])
        l_spanSegmentUPositions = lists.parseListToPairs(l_spanUPositions)
        #>>>Get div per span
        l_spanDivs = []
        for segment in l_spanSegmentUPositions:
            l_spanDivs.append(rollJoints)
            
        if d_rollJointOverride:
            for k in d_rollJointOverride.keys():
                try:
                    l_spanDivs[int(k)]#If the arg passes
                    l_spanDivs[int(k)] = d_rollJointOverride.get(k)#Override the roll value
                except:log.warning("%s:%s rollOverride arg failed"%(k,d_rollJointOverride.get(k)))
        
        log.debug("l_spanSegmentUPositions: %s"%l_spanSegmentUPositions)
        log.debug("l_spanDivs: %s"%l_spanDivs)
        
        #>>>Get div per span 
        l_jointUPositions = []
        for i,segment in enumerate(l_spanSegmentUPositions):#Split stuff up
            #Get our span u value distance
            length = segment[1]-segment[0]
            div = length / (l_spanDivs[i] +1)
            tally = segment[0]
            l_jointUPositions.append(tally)
            for i in range(l_spanDivs[i] +1)[1:]:
                tally = segment[0]+(i*div)
                l_jointUPositions.append(tally)
        l_jointUPositions.append(l_spanUPositions[-1])
                
        l_jointPositions = []
        for u in l_jointUPositions:
            l_jointPositions.append(mc.pointPosition("%s.u[%f]"%(curve,u)))
            
        #>>> Remove the duplicate positions"""
        l_jointPositions = lists.returnPosListNoDuplicates(l_jointPositions)
        #>>> Actually making the joints
        for pos in l_jointPositions:
            l_limbJoints.append ( mc.joint (p=(pos[0],pos[1],pos[2]))) 
               
    #>>> Naming
    #=========== 
    """ 
    Copy naming information from template objects to the joints closest to them
    copy over a cgmNameModifier tag from the module first
    """
    #attributes.copyUserAttrs(moduleNull,l_limbJoints[0],attrsToCopy=['cgmNameModifier'])
    
    #>>>First we need to find our matches
    log.info("Finding matches from module controlObjects")
    for i_obj in self.i_controlObjects:
        closestJoint = distance.returnClosestObject(i_obj.mNode,l_limbJoints)
        #transferObj = attributes.returnMessageObject(obj,'cgmName')
        """Then we copy it"""
        attributes.copyUserAttrs(i_obj.mNode,closestJoint,attrsToCopy=['cgmPosition','cgmNameModifier','cgmDirection','cgmName'])
       
    
    #>>>Store it
    #self.i_rigNull.connectChildren(l_limbJoints,'skinJoints','module')
    self.i_rigNull.connectChildrenNodes(l_limbJoints,'skinJoints','module')
    log.info(self.i_rigNull.skinJoints)       

    #>>>Store these joints and rename the heirarchy
    log.info("Metaclassing our objects") 
    for i,o in enumerate(l_limbJoints):
        i_o = cgmMeta.cgmObject(o)
        i_o.addAttr('mClass','cgmObject',lock=True) 
        
    self.i_rigNull.skinJoints[0].doName(nameChildren=True,fastIterate=False)
        
    
    #>>> Orientation    
    #=============== 
    if not doOrientSegment(self):
        raise StandardError,"Segment orientation failed"    
    
    
    #>>> Set its radius and toggle axis visbility on
    #averageDistance = distance.returnAverageDistanceBetweenObjects (l_limbJoints)
    l_limbJoints = self.i_rigNull.getMessage('skinJoints')
    jointSize = (distance.returnDistanceBetweenObjects (l_limbJoints[0],l_limbJoints[-1])/6)
    reload(attributes)
    #jointSize*.2
    attributes.doMultiSetAttr(l_limbJoints,'radi',3)
    
    #Connect to parent
    if self.m.getMessage('moduleParent'):#If we have a moduleParent, constrain it
        connectToParentModule(self.m)    
    return True 

#@r9General.Timer
def doOrientSegment(self):
    """ 
    Segement orienter. Must have a JointFactory Instance
    """ 
    log.info(">>> doOrientSegment")
    # Get our base info
    #==================	        
    assert self.cls == 'JointFactory.go',"Not a JointFactory.go instance!"
    assert mc.objExists(self.m.mNode),"module no longer exists"
    
    #self.i_rigNull = self.m.rigNull#refresh
    
    #>>> orientation vectors
    #=======================    
    orientationVectors = search.returnAimUpOutVectorsFromOrientation(self.jointOrientation)
    wantedAimVector = orientationVectors[0]
    wantedUpVector = orientationVectors[1]  
    log.debug("wantedAimVector: %s"%wantedAimVector)
    log.debug("wantedUpVector: %s"%wantedUpVector)
    
    #>>> Put objects in order of closeness to root
    #l_limbJoints = distance.returnDistanceSortedList(l_limbJoints[0],l_limbJoints)
    
    #>>> Segment our joint list by cgmName, prolly a better way to optimize this
    l_cull = copy.copy(self.i_rigNull.getMessage('skinJoints'))  
    if len(l_cull)==1:
        log.info('Single joint orient mode')
        helper = self.i_templateNull.orientRootHelper.mNode
        if helper:
            log.info("helper: %s"%helper)
            constBuffer = mc.orientConstraint( helper,l_cull[0],maintainOffset = False)
            mc.delete (constBuffer[0])  
            
    else:#Normal mode
        log.info('Normal orient mode')        
        self.l_jointSegmentIndexSets= []
        while l_cull:
            matchTerm = search.findRawTagInfo(l_cull[0],'cgmName')
            buffer = []
            objSet = search.returnMatchedTagsFromObjectList(l_cull,'cgmName',matchTerm)
            for o in objSet:
                buffer.append(self.i_rigNull.getMessage('skinJoints').index(o))
            self.l_jointSegmentIndexSets.append(buffer)
            for obj in objSet:
                l_cull.remove(obj)
            
        #>>> un parenting the chain
        for i_jnt in self.i_rigNull.skinJoints:
            i_jnt.parent = False
            i_jnt.displayLocalAxis = 1#tmp
	    #Set rotateOrder
            try:
		#i_jnt.rotateOrder = 2
                i_jnt.rotateOrder = self.jointOrientation
	    except StandardError,error:
		log.error("doOrientSegment>>rotate order set fail: %s"%i_jnt.getShortName())
    
        #>>>per segment stuff
        assert len(self.l_jointSegmentIndexSets) == len(self.m.i_coreNames.value)#quick check to make sure we've got the stuff we need
        cnt = 0
        for cnt,segment in enumerate(self.l_jointSegmentIndexSets):#for each segment
            segmentHelper = self.i_templateNull.controlObjects[cnt].getMessage('helper')[0]
            helperObjectCurvesShapes =  mc.listRelatives(segmentHelper,shapes=True)
            upLoc = locators.locMeCvFromCvIndex(helperObjectCurvesShapes[0],30)        
            if not mc.objExists(segmentHelper) and search.returnObjectType(segmentHelper) != 'nurbsCurve':
                log.error("No helper found")
                return False
    
            if len(segment) > 1:
                #>>> Create our up object from from the helper object 
                #>>> make a pair list
                pairList = lists.parseListToPairs(segment)
                for pair in pairList:
                    #>>> Set up constraints """
                    constraintBuffer = mc.aimConstraint(self.i_rigNull.skinJoints[pair[1]].mNode,self.i_rigNull.skinJoints[pair[0]].mNode,maintainOffset = False, weight = 1, aimVector = wantedAimVector, upVector = wantedUpVector, worldUpVector = [0,1,0], worldUpObject = upLoc, worldUpType = 'object' )
                    mc.delete(constraintBuffer[0])
                for index in segment[-1:]:
                    constraintBuffer = mc.orientConstraint(self.i_rigNull.skinJoints[segment[-2]].mNode,self.i_rigNull.skinJoints[index].mNode,maintainOffset = False, weight = 1)
                    mc.delete(constraintBuffer[0])
                #>>>  Increment and delete the up loc """
                mc.delete(upLoc)
            else:
                #>>> Make an aim object and move it """
                aimLoc = locators.locMeObject(segmentHelper)
                aimLocGroup = rigging.groupMeObject(aimLoc)
                mc.move (0,0,10, aimLoc, localSpace=True)
                constraintBuffer = mc.aimConstraint(aimLoc,self.i_rigNull.skinJoints[segment[0]].mNode,maintainOffset = False, weight = 1, aimVector = wantedAimVector, upVector = wantedUpVector, worldUpVector = [0,1,0], worldUpObject = upLoc, worldUpType = 'object' )
                mc.delete(constraintBuffer[0])
                mc.delete(aimLocGroup)
                mc.delete(upLoc)
               
        #>>>Reconnect the joints
        for cnt,i_jnt in enumerate(self.i_rigNull.skinJoints[1:]):#parent each to the one before it
            i_jnt.parent = self.i_rigNull.skinJoints[cnt].mNode
    
    if self.m.moduleType in ['foot']:
        log.info("Special case orient")
        if len(self.i_rigNull.getMessage('skinJoints')) > 1:
            helper = self.i_templateNull.orientRootHelper.mNode
            if helper:
                log.info("Root joint fix...")                
                rootJoint = self.i_rigNull.getMessage('skinJoints')[0]
                self.i_rigNull.skinJoints[1].parent = False #unparent the first child
                constBuffer = mc.orientConstraint( helper,rootJoint,maintainOffset = False)
                mc.delete (constBuffer[0])   
                self.i_rigNull.skinJoints[1].parent = rootJoint
        
    """ Freeze the rotations """
    mc.makeIdentity(self.i_rigNull.skinJoints[0].mNode,apply=True,r=True)
    return True




#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# Module tools
#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> 
@r9General.Timer
def deleteSkeleton(i_module,*args,**kws):  
    if not i_module.isSkeletonized():
        log.warning("Not skeletonized. Cannot delete skeleton: '%s'"%i_module.getShortName())
        return False
    
    #We need to see if any of or skinJoints have children
    l_strayChildren = []
    l_moduleJoints = i_module.rigNull.getMessage('skinJoints',longNames = True)
    for i_jnt in i_module.rigNull.skinJoints:
        buffer = i_jnt.getChildren(True)
        for c in buffer:
            if c not in l_moduleJoints:
                try:
                    i_c = cgmMeta.cgmObject(c)
                    i_c.parent = False
                    l_strayChildren.append(i_c.mNode)
                except StandardError,error:
                    log.warning(error)     
    log.info("l_strayChildren: %s"%l_strayChildren)
    mc.delete(i_module.rigNull.getMessage('skinJoints'))
    return True

@r9General.Timer
def connectToParentModule(self):
    """
    Pass a module class. Constrains template root to parent's closest template object
    """
    log.debug(">>> constrainToParentModule")
    if not self.isSkeletonized():
        log.error("Must be skeletonized to contrainToParentModule: '%s' "%self.getShortName())
        return False
    if not self.getMessage('moduleParent'):
        return False
    else:
        #>>> Get some info
        i_rigNull = self.rigNull #Link
        i_parent = self.moduleParent #Link
        parentState = i_parent.getState() 
        if i_parent.isSkeletonized():#>> If we have a module parent
            #>> If we have another anchor
            parentSkinJoints = i_parent.rigNull.getMessage('skinJoints')
            closestObj = distance.returnClosestObject(i_rigNull.getMessage('skinJoints')[0],parentSkinJoints)
            i_rigNull.skinJoints[0].parent = closestObj
            
        else:
            log.debug("Parent has not been skeletonized...")           
            return False  
    return True


#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# Module tools
#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>  

def skeletonizeCharacter(masterNull):
    """ 
    >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    DESCRIPTION:
    Skeletonizes a character
    
    ARGUMENTS:
    masterNull(string)
    
    RETURNS:
    nothin
    >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    """
    modules = modules.returnModules(masterNull)
    orderedModules = modules.returnOrderedModules(modules)
    #>>> Do the spine first
    stateCheck = modules.moduleStateCheck(orderedModules[0],['template'])
    if stateCheck == 1:
        spineJoints = skeletonize(orderedModules[0])
    else:
        print ('%s%s' % (module,' has already been skeletonized. Moving on...'))
    
    #>>> Do the rest
    for module in orderedModules[1:]:
        stateCheck = modules.moduleStateCheck(module,['template'])
        if stateCheck == 1:
            templateNull = modules.returnTemplateNull(module)
            root =  modules.returnInfoNullObjects(module,'templatePosObjects',types='templateRoot')
            
            #>>> See if our item has a non default anchor
            anchored = storeTemplateRootParent(module) 
            if anchored == True:
                anchor =  attributes.returnMessageObject(root[0],'skeletonParent')
                closestJoint = distance.returnClosestObject(anchor,spineJoints)
            else:
                closestJoint = distance.returnClosestObject(root[0],spineJoints) 
        
            l_limbJoints = skeletonize(module)
            rootName = rigging.doParentReturnName(l_limbJoints[0],closestJoint)
            print rootName
        else:
            print ('%s%s' % (module,' has already been skeletonized. Moving on...'))

#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
def skeletonStoreCharacter(masterNull):
    """ 
    >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    DESCRIPTION:
    stores a skeleton of a character
    
    ARGUMENTS:
    masterNull(string)
    
    RETURNS:
    nothin
    >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    """
    modules = modules.returnModules(masterNull)
    orderedModules = modules.returnOrderedModules(modules)
    #>>> Do the spine first
    stateCheck = modules.moduleStateCheck(orderedModules[0],['template'])
    if stateCheck == 1:
        spineJoints = modules.saveTemplateToModule(orderedModules[0])
    else:
        print ('%s%s' % (module,' has already been skeletonized. Moving on...'))
    
    #>>> Do the rest
    for module in orderedModules[1:]:
        stateCheck = modules.moduleStateCheck(module,['template'])
        if stateCheck == 1:
            templateNull = modules.returnTemplateNull(module)        
            modules.saveTemplateToModule(module)
        else:
            print ('%s%s' % (module,' has already been skeletonized. Moving on...'))

       
         
#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>            

def storeTemplateRootParent(moduleNull):
    """ 
    >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    DESCRIPTION:
    Stores the template root parent to the root control if there is a new one
    
    ARGUMENTS:
    moduleNull(string)
    
    RETURNS:
    success(bool)
    >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    """
    templateNull = modules.returnTemplateNull(moduleNull)
    root =   modules.returnInfoNullObjects(moduleNull,'templatePosObjects',types='templateRoot')
    parent = search.returnParentObject(root, False)
    if parent != templateNull:
        if parent != False:
            attributes.storeObjectToMessage(parent,root,'skeletonParent')
            return True
    return False



#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>    
#>>> Tools    
#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
def orientSegment(l_limbJoints,posTemplateObjects,orientation):
    """ 
    >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    DESCRIPTION:
    Basic limb skeletonizer
    
    ARGUMENTS:
    l_limbJoints(list)
    templeateObjects(list)
    orientation(string) - ['xyz','yzx','zxy','xzy','yxz','zyx']
    
    RETURNS:
    l_limbJoints(list)
    >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    """  
    """ orientation vectors"""
    orientationVectors = search.returnAimUpOutVectorsFromOrientation(orientation)
    wantedAimVector = orientationVectors[0]
    wantedUpVector = orientationVectors[1]    
    
    """put objects in order of closeness to root"""
    l_limbJoints = distance.returnDistanceSortedList(l_limbJoints[0],l_limbJoints)
    
    #>>> Segment our joint list by names
    jointSegmentsList = []
    cullList = []
    """ gonna be culling items from the list so need to rebuild it, just doing a list1 = list2 
    somehow keeps the relationship....odd """
    for obj in l_limbJoints:
        cullList.append(obj)
    
    while len(cullList) > 0:
        matchTerm = search.returnTagInfo(cullList[0],'cgmName')
        objSet = search.returnMatchedTagsFromObjectList(cullList,'cgmName',matchTerm)
        jointSegmentsList.append(objSet)
        for obj in objSet:
            cullList.remove(obj)
            
    #>>> get our orientation helpers
    helperObjects = []
    for obj in posTemplateObjects:
        templateObj = attributes.returnMessageObject(obj,'cgmName')
        helperObjects.append(attributes.returnMessageObject(templateObj,'orientHelper'))
    
    #>>> un parenting the chain
    for joint in l_limbJoints[1:]:
        mc.parent(joint,world=True)
    
    #>>>per segment stuff
    cnt = 0
    for segment in jointSegmentsList:
        if len(segment) > 1:
            """ creat our up object from from the helper object """
            helperObjectCurvesShapes =  mc.listRelatives(helperObjects[cnt],shapes=True)
            upLoc = locators.locMeCvFromCvIndex(helperObjectCurvesShapes[0],30)
            print upLoc
            """ make a pair list"""
            pairList = lists.parseListToPairs(segment)
            for pair in pairList:
                """ set up constraints """
                constraintBuffer = mc.aimConstraint(pair[1],pair[0],maintainOffset = False, weight = 1, aimVector = wantedAimVector, upVector = wantedUpVector, worldUpVector = [0,1,0], worldUpObject = upLoc, worldUpType = 'object' )
                mc.delete(constraintBuffer[0])
            for obj in segment[-1:]:
                constraintBuffer = mc.orientConstraint(segment[-2],obj,maintainOffset = False, weight = 1)
                mc.delete(constraintBuffer[0])
            """ increment and delete the up loc """
            cnt+=1
            mc.delete(upLoc)
        else:
            helperObjectCurvesShapes =  mc.listRelatives(helperObjects[cnt],shapes=True)
            upLoc = locators.locMeCvFromCvIndex(helperObjectCurvesShapes[0],30)
            """ make an aim object """
            aimLoc = locators.locMeObject(helperObjects[cnt])
            aimLocGroup = rigging.groupMeObject(aimLoc)
            mc.move (10,0,0, aimLoc, localSpace=True)
            constraintBuffer = mc.aimConstraint(aimLoc,segment[0],maintainOffset = False, weight = 1, aimVector = wantedAimVector, upVector = wantedUpVector, worldUpVector = [0,1,0], worldUpObject = upLoc, worldUpType = 'object' )
            mc.delete(constraintBuffer[0])
            mc.delete(aimLocGroup)
            mc.delete(upLoc)
            cnt+=1
    #>>>reconnect the joints
    pairList = lists.parseListToPairs(l_limbJoints)
    for pair in pairList:
        mc.parent(pair[1],pair[0])
        
    """ Freeze the rotations """
    mc.makeIdentity(l_limbJoints[0],apply=True,r=True)
    return l_limbJoints



