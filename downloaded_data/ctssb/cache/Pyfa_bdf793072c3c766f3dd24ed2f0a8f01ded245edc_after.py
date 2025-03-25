#===============================================================================
# Copyright (C) 2010 Diego Duclos
#
# This file is part of eos.
#
# eos is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# eos is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with eos.  If not, see <http://www.gnu.org/licenses/>.
#===============================================================================

from sqlalchemy.orm import validates, reconstructor

from eos.modifiedAttributeDict import ModifiedAttributeDict, ItemAttrShortcut, ChargeAttrShortcut
from eos.effectHandlerHelpers import HandledItem, HandledCharge
from eos.enum import Enum
from eos.mathUtils import floorFloat
import eos.db
import logging

logger = logging.getLogger(__name__)

class State(Enum):
    OFFLINE = -1
    ONLINE = 0
    ACTIVE = 1
    OVERHEATED = 2

class Slot(Enum):
    # These are self-explanatory
    LOW = 1
    MED = 2
    HIGH = 3
    RIG = 4
    SUBSYSTEM = 5
    # not a real slot, need for pyfa display rack separation
    MODE = 6
    # system effects. They are projected "modules" and pyfa assumes all modules
    # have a slot. In this case, make one up.
    SYSTEM = 7

class Hardpoint(Enum):
    NONE = 0
    MISSILE = 1
    TURRET = 2

class Module(HandledItem, HandledCharge, ItemAttrShortcut, ChargeAttrShortcut):
    """An instance of this class represents a module together with its charge and modified attributes"""
    DAMAGE_TYPES = ("em", "thermal", "kinetic", "explosive")
    MINING_ATTRIBUTES = ("miningAmount", )

    def __init__(self, item):
        """Initialize a module from the program"""
        self.__item = item

        if item is not None and self.isInvalid:
            raise ValueError("Passed item is not a Module")

        self.__charge = None
        self.itemID = item.ID if item is not None else None
        self.projected = False
        self.state = State.ONLINE
        self.build()

    @reconstructor
    def init(self):
        """Initialize a module from the database and validate"""
        self.__item = None
        self.__charge = None

        # we need this early if module is invalid and returns early
        self.__slot = self.dummySlot

        if self.itemID:
            self.__item = eos.db.getItem(self.itemID)
            if self.__item is None:
                logger.error("Item (id: %d) does not exist", self.itemID)
                return

        if self.isInvalid:
            logger.error("Item (id: %d) is not a Module", self.itemID)
            return

        if self.chargeID:
            self.__charge = eos.db.getItem(self.chargeID)

        self.build()

    def build(self):
        """ Builds internal module variables from both init's """

        if self.__charge and self.__charge.category.name != "Charge":
            self.__charge = None

        self.__dps = None
        self.__miningyield = None
        self.__volley = None
        self.__reloadTime = None
        self.__reloadForce = None
        self.__chargeCycles = None
        self.__hardpoint = Hardpoint.NONE
        self.__itemModifiedAttributes = ModifiedAttributeDict(parent=self)
        self.__chargeModifiedAttributes = ModifiedAttributeDict(parent=self)
        self.__slot = self.dummySlot  # defaults to None

        if self.__item:
            self.__itemModifiedAttributes.original = self.__item.attributes
            self.__itemModifiedAttributes.overrides = self.__item.overrides
            self.__hardpoint = self.__calculateHardpoint(self.__item)
            self.__slot = self.__calculateSlot(self.__item)
        if self.__charge:
            self.__chargeModifiedAttributes.original = self.__charge.attributes
            self.__chargeModifiedAttributes.overrides = self.__charge.overrides


    @classmethod
    def buildEmpty(cls, slot):
        empty = Module(None)
        empty.__slot = slot
        empty.dummySlot = slot
        return empty

    @classmethod
    def buildRack(cls, slot):
        empty = Rack(None)
        empty.__slot = slot
        empty.dummySlot = slot
        return empty

    @property
    def isEmpty(self):
        return self.dummySlot is not None

    @property
    def hardpoint(self):
        return self.__hardpoint

    @property
    def isInvalid(self):
        if self.isEmpty:
            return False
        return self.__item is None or (self.__item.category.name not in ("Module", "Subsystem") and self.__item.group.name != "Effect Beacon")

    @property
    def numCharges(self):
        if self.charge is None:
            charges = 0
        else:
            chargeVolume = self.charge.volume
            containerCapacity = self.item.capacity
            if chargeVolume is None or containerCapacity is None:
                charges = 0
            else:
                charges = floorFloat(float(containerCapacity) / chargeVolume)
        return charges

    @property
    def numShots(self):
        if self.charge is None:
            return None
        if self.__chargeCycles is None and self.charge:
            numCharges = self.numCharges
            # Usual ammo like projectiles and missiles
            if numCharges > 0 and "chargeRate" in self.itemModifiedAttributes:
                self.__chargeCycles = self.__calculateAmmoShots()
            # Frequency crystals (combat and mining lasers)
            elif numCharges > 0 and "crystalsGetDamaged" in self.chargeModifiedAttributes:
                self.__chargeCycles = self.__calculateCrystalShots()
            # Scripts and stuff
            else:
                self.__chargeCycles = 0
            return self.__chargeCycles
        else:
            return self.__chargeCycles

    @property
    def hpBeforeReload(self):
        """
        If item is some kind of repairer with charges, calculate
        HP it reps before going into reload.
        """
        cycles = self.numShots
        armorRep = self.getModifiedItemAttr("armorDamageAmount") or 0
        shieldRep = self.getModifiedItemAttr("shieldBonus") or 0
        if not cycles or (not armorRep and not shieldRep):
            return None
        hp = round((armorRep + shieldRep) * cycles)
        return hp

    def __calculateAmmoShots(self):
        if self.charge is not None:
            # Set number of cycles before reload is needed
            chargeRate = self.getModifiedItemAttr("chargeRate")
            numCharges = self.numCharges
            numShots = floorFloat(float(numCharges) / chargeRate)
        else:
            numShots = None
        return numShots

    def __calculateCrystalShots(self):
        if self.charge is not None:
            if self.getModifiedChargeAttr("crystalsGetDamaged") == 1:
                # For depletable crystals, calculate average amount of shots before it's destroyed
                hp = self.getModifiedChargeAttr("hp")
                chance = self.getModifiedChargeAttr("crystalVolatilityChance")
                damage = self.getModifiedChargeAttr("crystalVolatilityDamage")
                crystals = self.numCharges
                numShots = floorFloat(float(crystals * hp) / (damage * chance))
            else:
                # Set 0 (infinite) for permanent crystals like t1 laser crystals
                numShots = 0
        else:
            numShots = None
        return numShots

    @property
    def maxRange(self):
        attrs = ("maxRange", "shieldTransferRange", "powerTransferRange",
                 "energyDestabilizationRange", "empFieldRange",
                 "ecmBurstRange", "warpScrambleRange", "cargoScanRange",
                 "shipScanRange", "surveyScanRange")
        for attr in attrs:
            maxRange = self.getModifiedItemAttr(attr)
            if maxRange is not None: return maxRange
        if self.charge is not None:
            try:
                chargeName = self.charge.group.name
            except AttributeError:
                pass
            else:
                if chargeName in ("Scanner Probe", "Survey Probe"):
                    return None
            # Source: http://www.eveonline.com/ingameboard.asp?a=topic&threadID=1307419&page=1#15
            # D_m = V_m * (T_m + T_0*[exp(- T_m/T_0)-1])
            maxVelocity = self.getModifiedChargeAttr("maxVelocity")
            flightTime = self.getModifiedChargeAttr("explosionDelay") / 1000.0
            mass = self.getModifiedChargeAttr("mass")
            agility = self.getModifiedChargeAttr("agility")
            if maxVelocity and flightTime and mass and agility:
                accelTime =  min(flightTime, mass*agility/1000000)
                # Average distance done during acceleration
                duringAcceleration = maxVelocity / 2 * accelTime
                # Distance done after being at full speed
                fullSpeed = maxVelocity * (flightTime - accelTime)
                return duringAcceleration + fullSpeed

    @property
    def falloff(self):
        attrs = ("falloff", "shipScanFalloff", "falloffEffectiveness")
        for attr in attrs:
            falloff = self.getModifiedItemAttr(attr)
            if falloff is not None: return falloff

    @property
    def slot(self):
        return self.__slot


    @property
    def itemModifiedAttributes(self):
        return self.__itemModifiedAttributes

    @property
    def chargeModifiedAttributes(self):
        return self.__chargeModifiedAttributes

    @property
    def item(self):
        return self.__item if self.__item != 0 else None

    @property
    def charge(self):
        return self.__charge if self.__charge != 0 else None

    @charge.setter
    def charge(self, charge):
        self.__charge = charge
        if charge is not None:
            self.chargeID = charge.ID
            self.__chargeModifiedAttributes.original = charge.attributes
            self.__chargeModifiedAttributes.overrides = charge.overrides
        else:
            self.chargeID = None
            self.__chargeModifiedAttributes.original = None
            self.__chargeModifiedAttributes.overrides = {}

        self.__itemModifiedAttributes.clear()

    def damageStats(self, targetResists):
        if self.__dps == None:
            self.__dps = 0
            self.__volley = 0

            if not self.isEmpty and self.state >= State.ACTIVE:
                if self.charge:
                    func = self.getModifiedChargeAttr
                else:
                    func = self.getModifiedItemAttr

                volley = sum(map(lambda attr: (func("%sDamage"%attr) or 0) * (1-getattr(targetResists, "%sAmount"%attr, 0)), self.DAMAGE_TYPES))
                volley *= self.getModifiedItemAttr("damageMultiplier") or 1
                if volley:
                    cycleTime = self.cycleTime
                    self.__volley = volley
                    self.__dps = volley / (cycleTime / 1000.0)

        return self.__dps, self.__volley

    @property
    def miningStats(self):
        if self.__miningyield == None:
            if self.isEmpty:
                self.__miningyield = 0
            else:
                if self.state >= State.ACTIVE:
                    volley = self.getModifiedItemAttr("specialtyMiningAmount") or self.getModifiedItemAttr("miningAmount") or 0
                    if volley:
                        cycleTime = self.cycleTime
                        self.__miningyield = volley / (cycleTime / 1000.0)
                    else:
                        self.__miningyield = 0
                else:
                    self.__miningyield = 0

        return self.__miningyield

    @property
    def dps(self):
        return self.damageStats(None)[0]

    @property
    def volley(self):
        return self.damageStats(None)[1]

    @property
    def reloadTime(self):
        # Get reload time from attrs first, then use
        # custom value specified otherwise (e.g. in effects)
        moduleReloadTime = self.getModifiedItemAttr("reloadTime")
        if moduleReloadTime is None:
            moduleReloadTime = self.__reloadTime
        return moduleReloadTime

    @reloadTime.setter
    def reloadTime(self, milliseconds):
        self.__reloadTime = milliseconds

    @property
    def forceReload(self):
        return self.__reloadForce

    @forceReload.setter
    def forceReload(self, type):
        self.__reloadForce = type

    def fits(self, fit, hardpointLimit=True):
        slot = self.slot
        if fit.getSlotsFree(slot) <= (0 if self.owner != fit else -1):
            return False

        # Check ship type restrictions
        fitsOnType = set()
        fitsOnGroup = set()

        shipType = self.getModifiedItemAttr("fitsToShipType")
        if shipType is not None:
            fitsOnType.add(shipType)

        for i in xrange(1, 10):
            shipType = self.getModifiedItemAttr("canFitShipType%d" % i)
            if shipType is not None:
                fitsOnType.add(shipType)


        # Check ship group restrictions
        for i in xrange(1, 10):
            shipGroup = self.getModifiedItemAttr("canFitShipGroup%d" % i)
            if shipGroup is not None:
                fitsOnGroup.add(shipGroup)

        if (len(fitsOnGroup) > 0 or len(fitsOnType) > 0) and fit.ship.item.group.ID not in fitsOnGroup and fit.ship.item.ID not in fitsOnType:
            return False


        # If the mod is a subsystem, don't let two subs in the same slot fit
        if self.slot == Slot.SUBSYSTEM:
            subSlot = self.getModifiedItemAttr("subSystemSlot")
            for mod in fit.modules:
                if mod.getModifiedItemAttr("subSystemSlot") == subSlot:
                    return False

        # Check rig sizes
        if self.slot == Slot.RIG:
            if self.getModifiedItemAttr("rigSize") != fit.ship.getModifiedItemAttr("rigSize"):
                return False

        # Check max group fitted
        max = self.getModifiedItemAttr("maxGroupFitted")
        if max is not None:
            current = 0 if self.owner != fit else -1
            for mod in fit.modules:
                if mod.item and mod.item.groupID == self.item.groupID:
                    current += 1

            if current >= max:
                return False

        # Check this only if we're told to do so
        if hardpointLimit:
            if self.hardpoint == Hardpoint.TURRET:
                if fit.ship.getModifiedItemAttr('turretSlotsLeft') - fit.getHardpointsUsed(Hardpoint.TURRET) < 1:
                    return False
            elif self.hardpoint == Hardpoint.MISSILE:
                if fit.ship.getModifiedItemAttr('launcherSlotsLeft') - fit.getHardpointsUsed(Hardpoint.MISSILE) < 1:
                    return False

        return True

    def isValidState(self, state):
        """
        Check if the state is valid for this module, without considering other modules at all
        """
        #Check if we're within bounds
        if state < -1 or state > 2:
            return False
        elif state >= State.ACTIVE and not self.item.isType("active"):
            return False
        elif state == State.OVERHEATED and not self.item.isType("overheat"):
            return False
        else:
            return True

    def canHaveState(self, state=None, projectedOnto=None):
        """
        Check with other modules if there are restrictions that might not allow this module to be activated
        """
        # If we're going to set module to offline or online for local modules or offline for projected,
        # it should be fine for all cases
        item = self.item
        if (state <= State.ONLINE and projectedOnto is None) or (state <= State.OFFLINE):
            return True

        # Check if the local module is over it's max limit; if it's not, we're fine
        maxGroupActive = self.getModifiedItemAttr("maxGroupActive")
        if maxGroupActive is None and projectedOnto is None:
            return True

        # Following is applicable only to local modules, we do not want to limit projected
        if projectedOnto is None:
            currActive = 0
            group = item.group.name
            for mod in self.owner.modules:
                currItem = getattr(mod, "item", None)
                if mod.state >= State.ACTIVE and currItem is not None and currItem.group.name == group:
                    currActive += 1
                if currActive > maxGroupActive:
                    break
            return currActive <= maxGroupActive
        # For projected, we're checking if ship is vulnerable to given item
        else:
            # Do not allow to apply offensive modules on ship with offensive module immunite, with few exceptions
            # (all effects which apply instant modification are exception, generally speaking)
            if item.offensive and projectedOnto.ship.getModifiedItemAttr("disallowOffensiveModifiers") == 1:
                offensiveNonModifiers = set(("energyDestabilizationNew", "leech", "energyNosferatuFalloff", "energyNeutralizerFalloff"))
                if not offensiveNonModifiers.intersection(set(item.effects)):
                    return False
            # If assistive modules are not allowed, do not let to apply these altogether
            if item.assistive and projectedOnto.ship.getModifiedItemAttr("disallowAssistance") == 1:
                return False
            return True

    def isValidCharge(self, charge):
        #Check sizes, if 'charge size > module volume' it won't fit
        if charge is None: return True
        chargeVolume = charge.volume
        moduleCapacity = self.item.capacity
        if chargeVolume is not None and moduleCapacity is not None and chargeVolume > moduleCapacity:
            return False

        itemChargeSize = self.getModifiedItemAttr("chargeSize")
        if itemChargeSize is not None:
            chargeSize = charge.getAttribute('chargeSize')
            if itemChargeSize != chargeSize:
                return False

        chargeGroup = charge.groupID
        for i in range(5):
            itemChargeGroup = self.getModifiedItemAttr('chargeGroup' + str(i))
            if itemChargeGroup is None: continue
            if itemChargeGroup == chargeGroup: return True

        return False

    def getValidCharges(self):
        validCharges = set()
        for i in range(5):
            itemChargeGroup = self.getModifiedItemAttr('chargeGroup' + str(i))
            if itemChargeGroup is not None:
                g = eos.db.getGroup(int(itemChargeGroup), eager=("items.icon", "items.attributes"))
                if g is None:
                    continue
                for i in g.items:
                    if i.published and self.isValidCharge(i):
                        validCharges.add(i)

        return validCharges

    def __calculateHardpoint(self, item):
        effectHardpointMap = {"turretFitted" : Hardpoint.TURRET,
                              "launcherFitted": Hardpoint.MISSILE}

        if item is None:
            return Hardpoint.NONE

        for effectName, slot in effectHardpointMap.iteritems():
            if effectName in item.effects:
                return slot

        return Hardpoint.NONE

    def __calculateSlot(self, item):
        effectSlotMap = {"rigSlot" : Slot.RIG,
                         "loPower" : Slot.LOW,
                         "medPower" : Slot.MED,
                         "hiPower" : Slot.HIGH,
                         "subSystem" : Slot.SUBSYSTEM}
        if item is None:
            return None
        for effectName, slot in effectSlotMap.iteritems():
            if effectName in item.effects:
                return slot
        if item.group.name == "Effect Beacon":
            return Slot.SYSTEM

        raise ValueError("Passed item does not fit in any known slot")

    @validates("ID", "itemID", "ammoID")
    def validator(self, key, val):
        map = {"ID": lambda val: isinstance(val, int),
               "itemID" : lambda val: val is None or isinstance(val, int),
               "ammoID" : lambda val: isinstance(val, int)}

        if map[key](val) == False: raise ValueError(str(val) + " is not a valid value for " + key)
        else: return val

    def clear(self):
        self.__dps = None
        self.__miningyield = None
        self.__volley = None
        self.__reloadTime = None
        self.__reloadForce = None
        self.__chargeCycles = None
        self.itemModifiedAttributes.clear()
        self.chargeModifiedAttributes.clear()

    def calculateModifiedAttributes(self, fit, runTime, forceProjected = False):
        #We will run the effect when two conditions are met:
        #1: It makes sense to run the effect
        #    The effect is either offline
        #    or the effect is passive and the module is in the online state (or higher)

        #    or the effect is active and the module is in the active state (or higher)
        #    or the effect is overheat and the module is in the overheated state (or higher)
        #2: the runtimes match

        if self.projected or forceProjected:
            context = "projected", "module"
            projected = True
        else:
            context = ("module",)
            projected = False

        if self.charge is not None:
            # fix for #82 and it's regression #106
            if not projected or (self.projected and not forceProjected):
                for effect in self.charge.effects.itervalues():
                    if effect.runTime == runTime:
                        effect.handler(fit, self, ("moduleCharge",))

        if self.item:
            if self.state >= State.OVERHEATED:
                for effect in self.item.effects.itervalues():
                    if effect.runTime == runTime and \
                       effect.isType("overheat") and \
                       not forceProjected:
                        effect.handler(fit, self, context)

            for effect in self.item.effects.itervalues():
                if effect.runTime == runTime and \
                (effect.isType("offline") or
                (effect.isType("passive") and self.state >= State.ONLINE) or \
                (effect.isType("active") and self.state >= State.ACTIVE)) and \
                ((projected and effect.isType("projected")) or not projected):
                        effect.handler(fit, self, context)

    @property
    def cycleTime(self):
        reactivation = (self.getModifiedItemAttr("moduleReactivationDelay") or 0)
        # Reactivation time starts counting after end of module cycle
        speed = self.rawCycleTime + reactivation
        if self.charge:
            reload = self.reloadTime
        else:
            reload = 0.0
        # Determine if we'll take into account reload time or not
        factorReload = self.owner.factorReload if self.forceReload is None else self.forceReload
        # If reactivation is longer than 10 seconds then module can be reloaded
        # during reactivation time, thus we may ignore reload
        if factorReload and reactivation < reload:
            numShots = self.numShots
            # Time it takes to reload module after end of reactivation time,
            # given that we started when module cycle has just over
            additionalReloadTime = (reload - reactivation)
            # Speed here already takes into consideration reactivation time
            speed = (speed * numShots + additionalReloadTime) / numShots if numShots > 0 else speed

        return speed

    @property
    def rawCycleTime(self):
        speed =  self.getModifiedItemAttr("speed") or self.getModifiedItemAttr("duration")
        return speed

    @property
    def capUse(self):
        capNeed = self.getModifiedItemAttr("capacitorNeed")
        if capNeed and self.state >= State.ACTIVE:
            cycleTime = self.cycleTime
            capUsed = capNeed / (cycleTime / 1000.0)
            return capUsed
        else:
            return 0

    def __deepcopy__(self, memo):
        item = self.item
        if item is None:
            copy = Module.buildEmpty(self.slot)
        else:
            copy = Module(self.item)
        copy.charge = self.charge
        copy.state = self.state
        return copy

    def __repr__(self):
        if self.item:
            return "Module(ID={}, name={}) at {}".format(
                self.item.ID, self.item.name, hex(id(self))
            )
        else:
            return "EmptyModule() at {}".format(hex(id(self)))

class Rack(Module):
    '''
    This is simply the Module class named something else to differentiate
    it for app logic. This class does not do anything special
    '''
    pass
