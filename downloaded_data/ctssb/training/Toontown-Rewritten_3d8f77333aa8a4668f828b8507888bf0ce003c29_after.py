from toontown.hood import HoodAI
from toontown.dna.DNAParser import DNAData
from toontown.racing.DistributedRacePadAI import DistributedRacePadAI
from toontown.racing.DistributedViewPadAI import DistributedViewPadAI
from toontown.racing.DistributedStartingBlockAI import DistributedStartingBlockAI, DistributedViewingBlockAI
from toontown.building.DistributedDoorAI import DistributedDoorAI
from toontown.building.DistributedKartShopInteriorAI import DistributedKartShopInteriorAI
from toontown.toon import NPCToons
from toontown.building import DoorTypes
from toontown.racing import RaceGlobals
from otp.ai.MagicWordGlobal import *

class GSHoodAI(HoodAI.HoodAI):
    HOOD = 8000

    def __init__(self, air):
        HoodAI.HoodAI.__init__(self, air)
        self.racepads = []
        self.viewpads = []
        
    def createSafeZone(self):
        HoodAI.HoodAI.spawnObjects(self, 'phase_6/dna/goofy_speedway_sz.dna')
    
    def createKartShop(self):
        ksInterior = DistributedKartShopInteriorAI(self.air)
        ksInterior.setZoneIdAndBlock(8501, 0)
        ksInterior.generateWithRequired(8501)
    
        ksDoor = DistributedDoorAI(self.air)
        ksDoor.setZoneIdAndBlock(self.safezone, 1)
        ksDoor.setDoorType(DoorTypes.EXT_KS)
        ksDoor.setSwing(3)
        ksDoor.setDoorIndex(1)
        ksDoor.generateWithRequired(self.safezone)
        
        ksDoor2 = DistributedDoorAI(self.air)
        ksDoor2.setZoneIdAndBlock(self.safezone, 1)
        ksDoor2.setDoorType(DoorTypes.EXT_KS)
        ksDoor2.setSwing(3)
        ksDoor2.setDoorIndex(2)
        ksDoor2.generateWithRequired(self.safezone)
        
        ksDoorInt = DistributedDoorAI(self.air)
        ksDoorInt.setZoneIdAndBlock(8501, 0)
        ksDoorInt.setSwing(3)
        ksDoorInt.setDoorType(DoorTypes.INT_KS)
        ksDoorInt.setDoorIndex(1)
        ksDoorInt.setOtherZoneIdAndDoId(self.safezone, ksDoor.getDoId())
        ksDoorInt.generateWithRequired(8501)

        ksDoorInt2 = DistributedDoorAI(self.air)
        ksDoorInt2.setZoneIdAndBlock(8501, 0)
        ksDoorInt2.setSwing(3)
        ksDoorInt2.setDoorType(DoorTypes.INT_KS)
        ksDoorInt2.setOtherZoneIdAndDoId(self.safezone, ksDoor2.getDoId())
        ksDoorInt2.setDoorIndex(2)
        ksDoorInt2.generateWithRequired(8501)
        
        ksDoor.setOtherZoneIdAndDoId(8501, ksDoorInt.getDoId())
        ksDoor2.setOtherZoneIdAndDoId(8501, ksDoorInt2.getDoId())
        
        NPCToons.createNPC(self.air, 8001, NPCToons.NPCToonDict.get(8001), 8501, posIndex=0)
        NPCToons.createNPC(self.air, 8002, NPCToons.NPCToonDict.get(8002), 8501, posIndex=1)
        NPCToons.createNPC(self.air, 8003, NPCToons.NPCToonDict.get(8003), 8501, posIndex=2)
        NPCToons.createNPC(self.air, 8004, NPCToons.NPCToonDict.get(8004), 8501, posIndex=3)

    def createObjects(self, group):
        if group.getName()[:10] == 'racing_pad':
            index, dest = group.getName()[11:].split('_', 2)
            index = int(index)
            
            pad = DistributedRacePadAI(self.air)
            pad.setArea(self.HOOD)
            pad.nameType = dest
            pad.index = index
            nri = RaceGlobals.getNextRaceInfo(-1, dest, index)
            pad.setTrackInfo([nri[0], nri[1]])
            pad.generateWithRequired(self.HOOD)
            self.racepads.append(pad)
            for i in range(group.getNumChildren()):
                posSpot = group.at(i)
                if posSpot.getName()[:14] == 'starting_block':
                    spotIndex = int(posSpot.getName()[15:])
                    x, y, z = posSpot.getPos()
                    h, p, r = posSpot.getHpr()
                    startingBlock = DistributedStartingBlockAI(self.air)
                    startingBlock.setPosHpr(x, y, z, h, p, r)
                    startingBlock.setPadDoId(pad.getDoId())
                    startingBlock.setPadLocationId(index)
                    startingBlock.generateWithRequired(self.HOOD)
                    pad.addStartingBlock(startingBlock)
        elif group.getName()[:11] == 'viewing_pad':
            pad = DistributedViewPadAI(self.air)
            pad.setArea(self.HOOD)
            pad.generateWithRequired(self.HOOD)
            self.viewpads.append(pad)
            for i in range(group.getNumChildren()):
                posSpot = group.at(i)
                if posSpot.getName()[:14] == 'starting_block':
                    spotIndex = int(posSpot.getName()[15:])
                    x, y, z = posSpot.getPos()
                    h, p, r = posSpot.getHpr()
                    startingBlock = DistributedViewingBlockAI(self.air)
                    startingBlock.setPosHpr(x, y, z, h, p, r)
                    startingBlock.setPadDoId(pad.getDoId())
                    startingBlock.setPadLocationId(0)
                    #padLocationId is only used for racing pads... setting this like above causes the position to be wrong
                    startingBlock.generateWithRequired(self.HOOD)
                    pad.addStartingBlock(startingBlock)

        for i in range(group.getNumChildren()):
            self.createObjects(group.at(i))
            
@magicWord(category=CATEGORY_OVERRIDE)
def resetPads():
    GSW = simbase.air.hoods[6] # Hood 6 in the list in AIR :)
    RacingPads = GSW.racepads
    ViewingPads = GSW.viewpads
    
    for RacePadDO in RacingPads:
        RacePadDO.requestDelete()
        
    for ViewPadDO in ViewingPads:
        ViewPadDO.requestDelete()
        
    GSW.racepads = []
    GSW.viewpads = []
    
    GSW.createObjects(GSW.dnaData)
    
    return "Respawned the Race Pads at Goofy Speedway."