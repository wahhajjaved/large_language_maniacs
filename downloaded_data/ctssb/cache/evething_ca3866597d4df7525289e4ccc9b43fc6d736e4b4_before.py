import os
import sqlite3
import sys
import time
import urllib2
import xml.etree.ElementTree as ET

# Set up our environment and import settings
os.environ['DJANGO_SETTINGS_MODULE'] = 'evething.settings'
from django.conf import settings

from thing.models import *

# ---------------------------------------------------------------------------

SDE_FILE = 'esc10-sqlite3-v1.db'

ALLIANCE_URL = '%s/eve/AllianceList.xml.aspx' % (settings.API_HOST)
REF_TYPES_URL = '%s/eve/RefTypes.xml.aspx' % (settings.API_HOST)
STATION_URL = '%s/eve/ConquerableStationList.xml.aspx' % (settings.API_HOST)

# Override volume for ships, assembled volume is mostly useless :ccp:
PACKAGED = {
     25: 2500,  # frigate
     26: 10000, # cruiser
     27: 50000, # battleship
     28: 20000, # industrial
     31: 500,   # shuttle
    324: 2500,  # assault ship
    358: 10000, # heavy assault ship
    380: 20000, # transport ship
    419: 15000, # battlecruiser
    420: 5000,  # destroyer
    463: 3750,  # mining barge
    540: 15000, # command ship
    541: 5000,  # interdictor
    543: 3750,  # exhumer
    830: 2500,  # covert ops
    831: 2500,  # interceptor
    832: 10000, # logistics
    833: 10000, # force recon
    834: 2500,  # stealth bomber
    893: 2500,  # electronic attack ship
    894: 10000, # heavy interdictor
    898: 50000, # black ops
    900: 50000, # marauder
    906: 10000, # combat recon
    963: 5000,  # strategic cruiser
}

# ---------------------------------------------------------------------------

def time_func(text, f):
    start = time.time()
    print '=> %s:' % (text),
    sys.stdout.flush()
    
    added = f()
    
    print '%d (%0.2fs)' % (added, time.time() - start)


class Importer:
    def __init__(self):
        if os.path.isfile(SDE_FILE):
            self.conn = sqlite3.connect(SDE_FILE)
            self.cursor = self.conn.cursor()
        else:
            self.conn = None
    
    def import_all(self):
        if self.conn is not None:
            time_func('Region', self.import_region)
            time_func('Constellation', self.import_constellation)
            time_func('System', self.import_system)
            time_func('Station', self.import_station)
            time_func('MarketGroup', self.import_marketgroup)
            time_func('ItemCategory', self.import_itemcategory)
            time_func('ItemGroup', self.import_itemgroup)
            time_func('Item', self.import_item)
            time_func('Blueprint', self.import_blueprint)
            time_func('Skill', self.import_skill)
            time_func('InventoryFlag', self.import_inventoryflag)
            time_func('NPCFaction', self.import_npcfaction)
            time_func('NPCCorporation', self.import_npccorporation)
        
        time_func('Alliance', self.import_alliance)
        time_func('Conquerable Station', self.import_conquerable_station)
        time_func('RefTypes', self.import_reftypes)
    
    # -----------------------------------------------------------------------
    # Regions
    def import_region(self):
        added = 0
        
        self.cursor.execute('SELECT regionID, regionName FROM mapRegions WHERE regionName != "Unknown"')
        bulk_data = {}
        for row in self.cursor:
            bulk_data[int(row[0])] = row[1:]
        
        data_map = Region.objects.in_bulk(bulk_data.keys())
        
        new = []
        for id, data in bulk_data.items():
            if id in data_map:
                continue
            
            region = Region(
                id=id,
                name=data[0],
            )
            new.append(region)
            added += 1

        if new:
            Region.objects.bulk_create(new)
        
        return added
    
    # -----------------------------------------------------------------------
    # Constellations
    def import_constellation(self):
        added = 0
        
        self.cursor.execute('SELECT constellationID,constellationName,regionID FROM mapConstellations')
        bulk_data = {}
        for row in self.cursor:
            id = int(row[0])
            if id:
                bulk_data[id] = row[1:]
        
        data_map = Constellation.objects.in_bulk(bulk_data.keys())
        
        new = []
        for id, data in bulk_data.items():
            if id in data_map or not data[0] or not data[1]:
                continue
            
            con = Constellation(
                id=id,
                name=data[0],
                region_id=data[1],
            )
            new.append(con)
            added += 1
        
        if new:
            Constellation.objects.bulk_create(new)

        return added
    
    # -----------------------------------------------------------------------
    # Systems
    def import_system(self):
        added = 0
        
        self.cursor.execute('SELECT solarSystemID, solarSystemName, constellationID FROM mapSolarSystems')
        bulk_data = {}
        for row in self.cursor:
            id = int(row[0])
            if id:
                bulk_data[id] = row[1:]
        
        data_map = System.objects.in_bulk(bulk_data.keys())
        
        new = []
        for id, data in bulk_data.items():
            if id in data_map or not data[0] or not data[1]:
                continue
            
            system = System(
                id=id,
                name=data[0],
                constellation_id=data[1],
            )
            new.append(system)
            added += 1

        if new:
            System.objects.bulk_create(new)
        
        return added
    
    # -----------------------------------------------------------------------
    # Stations
    def import_station(self):
        added = 0
        
        self.cursor.execute('SELECT stationID, stationName, solarSystemID FROM staStations')
        bulk_data = {}
        for row in self.cursor:
            id = int(row[0])
            if id:
                bulk_data[id] = row[1:]
        
        data_map = Station.objects.in_bulk(bulk_data.keys())
        
        new = []
        for id, data in bulk_data.items():
            if id in data_map or not data[0] or not data[1]:
                continue
            
            station = Station(
                id=id,
                name=data[0],
                system_id=data[1],
            )
            new.append(station)
            added += 1
        
        if new:
            Station.objects.bulk_create(new)

        return added

    # -----------------------------------------------------------------------
    # Market groups
    def import_marketgroup(self):
        added = 0
        
        self.cursor.execute('SELECT marketGroupID, marketGroupName, parentGroupID FROM invMarketGroups')
        bulk_data = {}
        for row in self.cursor:
            id = int(row[0])
            if id:
                bulk_data[id] = row[1:]
        
        data_map = MarketGroup.objects.in_bulk(bulk_data.keys())
        
        while bulk_data:
            items = list(bulk_data.items())
            for id, data in items:
                # if we've already added this marketgroup, cache and skip
                if id in data_map:
                    del bulk_data[id]
                    continue
                
                if data[1] is None:
                    parent = None
                else:
                    # if the parent id doesn't exist yet we have to do this later
                    try:
                        parent = MarketGroup.objects.get(pk=data[1])
                    except MarketGroup.DoesNotExist:
                        continue
                
                mg = MarketGroup(
                    id=id,
                    name=data[0],
                    parent=parent,
                )
                mg.save()
                added += 1
                
                del bulk_data[id]
        
        return added
    
    # -----------------------------------------------------------------------
    # Item Categories
    def import_itemcategory(self):
        added = 0
        
        self.cursor.execute('SELECT categoryID, categoryName FROM invCategories')
        bulk_data = {}
        for row in self.cursor:
            id = int(row[0])
            if id and row[1]:
                bulk_data[id] = row[1:]
        
        data_map = ItemCategory.objects.in_bulk(bulk_data.keys())
        
        new = []
        for id, data in bulk_data.items():
            if id in data_map or not data[0]:
                continue
            
            ic = ItemCategory(
                id=id,
                name=data[0],
            )
            new.append(ic)
            added += 1

        if new:
            ItemCategory.objects.bulk_create(new)
        
        return added
    
    # -----------------------------------------------------------------------
    # Item Groups
    def import_itemgroup(self):
        added = 0
        
        self.cursor.execute('SELECT groupID, groupName, categoryID FROM invGroups')
        bulk_data = {}
        for row in self.cursor:
            id = int(row[0])
            if id and row[2]:
                bulk_data[id] = row[1:]
        
        data_map = ItemGroup.objects.in_bulk(bulk_data.keys())
        
        new = []
        for id, data in bulk_data.items():
            if data[1]:
                continue

            ig = data_map.get(id, None)
            if ig is not None:
                if ig.name != data[0]:
                    print '==> Renamed %r to %r' % (ig.name, data[0])
                    ig.name = data[0]
                    ig.save()
                continue

            ig = ItemGroup(
                id=id,
                name=data[0],
                category_id=data[1],
            )
            new.append(ig)
            added += 1

        if new:
            ItemGroup.objects.bulk_create(new)
        
        return added
    
    # -----------------------------------------------------------------------
    # Items
    def import_item(self):
        added = 0
        
        self.cursor.execute('SELECT typeID, typeName, groupID, marketGroupID, portionSize, volume, basePrice FROM invTypes')
        
        bulk_data = {}
        for row in self.cursor:
            bulk_data[int(row[0])] = row[1:]
        
        data_map = Item.objects.in_bulk(bulk_data.keys())
        
        new = []
        for id, data in bulk_data.items():
            if not data[1]:
                continue
            
            portion_size = Decimal(data[3])
            volume = PACKAGED.get(data[1], Decimal(str(data[4])))
            base_price = Decimal(data[5])

            # handle modified items
            item = data_map.get(id, None)
            if item is not None:
                if item.name != data[0] or item.portion_size != portion_size or item.volume != volume or \
                   item.base_price != base_price:
                    print '==> Updated data for #%s (%r)' % (item.id, item.name)
                    item.name = data[0]
                    item.portion_size = portion_size
                    item.volume = volume
                    item.base_price = base_price
                    item.save()
                continue
            
            item = Item(
                id=id,
                name=data[0],
                item_group_id=data[1],
                market_group_id=data[2],
                portion_size=portion_size,
                volume=volume,
                base_price=base_price,
            )
            new.append(item)
            added += 1

        if new:
            Item.objects.bulk_create(new)
        
        return added
    
    # -----------------------------------------------------------------------
    def import_blueprint(self):
        # Blueprints
        added = 0
        
        self.cursor.execute("""
            SELECT  b.blueprintTypeID, t.typeName, b.productTypeID, b.productionTime, b.productivityModifier, b.materialModifier, b.wasteFactor
            FROM    invBlueprintTypes AS b
            INNER JOIN invTypes AS t
            ON      b.blueprintTypeID = t.typeID
            WHERE   t.published = 1
        """)
        bulk_data = {}
        for row in self.cursor:
            bulk_data[int(row[0])] = row[1:]
        
        data_map = Blueprint.objects.in_bulk(bulk_data.keys())
        
        for id, data in bulk_data.items():
            if not data[0] or not data[1]:
                continue

            bp = data_map.get(id, None)
            if bp is not None:
                if bp.name != data[0]:
                    print '==> Renamed %r to %r' % (bp.name, data[0])
                    bp.name = data[0]
                    bp.save()
                continue
            
            bp = Blueprint(
                id=id,
                name=data[0],
                item_id=data[1],
                production_time=data[2],
                productivity_modifier=data[3],
                material_modifier=data[4],
                waste_factor=data[5],
            )
            bp.save()
            added += 1
            
            # Base materials
            self.cursor.execute('SELECT materialTypeID, quantity FROM invTypeMaterials WHERE typeID=?', (data[1],))
            for baserow in self.cursor:
                bpc = BlueprintComponent(
                    blueprint_id=id,
                    item_id=baserow[0],
                    count=baserow[1],
                    needs_waste=True,
                )
                bpc.save()
                added += 1
            
            # Extra materials. activityID 1 is manufacturing - categoryID 16 is skill requirements
            self.cursor.execute("""
                SELECT  r.requiredTypeID, r.quantity
                FROM    ramTypeRequirements AS r
                INNER JOIN invTypes AS t
                ON      r.requiredTypeID = t.typeID
                INNER JOIN invGroups AS g
                ON      t.groupID = g.groupID
                WHERE   r.typeID = ?
                        AND r.activityID = 1
                        AND g.categoryID <> 16
            """, (id,))
            
            for extrarow in self.cursor:
                bpc = BlueprintComponent(
                    blueprint_id=id,
                    item_id=extrarow[0],
                    count=extrarow[1],
                    needs_waste=False,
                )
                bpc.save()
                added += 1
        
        return added
    
    # -----------------------------------------------------------------------
    # Skills
    def import_skill(self):
        added = 0

        skills = {}
        self.cursor.execute("""
            SELECT  DISTINCT invTypes.typeID,
                    CAST(dgmTypeAttributes.valueFloat AS integer) AS rank,
                    invTypes.description
            FROM    invTypes
            INNER JOIN invGroups ON (invTypes.groupID = invGroups.groupID)
            INNER JOIN dgmTypeAttributes ON (invTypes.typeID = dgmTypeAttributes.typeID)
            WHERE   invGroups.categoryID = 16
                    AND invTypes.published = 1
                    AND dgmTypeAttributes.attributeID = 275
                    AND dgmTypeAttributes.valueFloat IS NOT NULL
            ORDER BY invTypes.typeID
        """)
        for row in self.cursor:
            skills[row[0]] = {
                'rank': row[1],
                'description': row[2].strip(),
            }

        # Primary/secondary attributes
        self.cursor.execute("""
            SELECT  typeID, attributeID, valueInt, valueFloat
            FROM    dgmTypeAttributes
            WHERE   attributeID IN (180, 181)
        """)
        for row in self.cursor:
            # skip unpublished
            skill = skills.get(row[0], None)
            if skill is None:
                continue

            if row[1] == 180:
                k = 'pri'
            else:
                k = 'sec'
            if row[2]:
                skill[k] = row[2]
            else:
                skill[k] = row[3]

        # filter skills I guess
        skill_map = {}
        for skill in Skill.objects.all():
            skill_map[skill.item_id] = skill

        for id, data in skills.items():
            # TODO: add value verification
            skill = skill_map.get(id, None)
            if skill is not None:
                if skill.rank != data['rank'] or skill.description != data['description'] or \
                   skill.primary_attribute != data['pri'] or skill.secondary_attribute != data['sec']:

                    skill.rank = data['rank']
                    skill.description = data['description']
                    skill.primary_attribute = data['pri']
                    skill.secondary_attribute = data['sec']
                    skill.save()
                    print '==> Updated skill details for #%d' % (id)
                continue

            skill = Skill(
                item_id=id,
                rank=data['rank'],
                primary_attribute=data['pri'],
                secondary_attribute=data['sec'],
            )
            skill.save()
            added += 1

        return added

# :skills:
#       :prerequisite: # These are the attribute ids for skill prerequisites. [item, level]
#         1: [182, 277]
#         2: [183, 278]
#         3: [184, 279]
#         4: [1285, 1286]
#         5: [1289, 1287]
#         6: [1290, 1288]
#       :primary_attribute: 180 # database attribute ID for primary attribute
#       :secondary_attribute: 181 # database attribute ID for secondary attribute
#       :attributes: # Mapping of id keys to the actual attribute
#         165: :intelligence
#         164: :charisma
#         166: :memory
#         167: :perception
#         168: :willpower

    # -----------------------------------------------------------------------
    # InventoryFlags
    def import_inventoryflag(self):
        added = 0

        self.cursor.execute('SELECT flagID, flagName, flagText FROM invFlags')

        bulk_data = {}
        for row in self.cursor:
            bulk_data[int(row[0])] = row[1:]

        data_map = InventoryFlag.objects.in_bulk(bulk_data.keys())

        new = []
        for id, data in bulk_data.items():
            if not data[0] or not data[1]:
                continue

            # handle renamed flags
            flag = data_map.get(id, None)
            if flag is not None:
                if flag.name != data[0] or flag.text != data[1]:
                    print '==> Renamed %r to %r' % (flag.name, data[0])
                    flag.name = data[0]
                    flag.text = data[1]
                    flag.save()
                continue

            flag = InventoryFlag(
                id=id,
                name=data[0],
                text=data[1],
            )
            new.append(flag)
            added += 1

        if new:
            InventoryFlag.objects.bulk_create(new)

        return added

    # -----------------------------------------------------------------------
    # NPC Factions
    def import_npcfaction(self):
        added = 0

        self.cursor.execute('SELECT factionID, factionName FROM chrFactions')

        bulk_data = {}
        for row in self.cursor:
            bulk_data[int(row[0])] = row[1]

        data_map = Faction.objects.in_bulk(bulk_data.keys())

        new = []
        for id, name in bulk_data.items():
            faction = data_map.get(id, None)
            if faction is not None:
                if faction.name != name:
                    print '==> Renamed %r to %r' % (faction.name, name)
                    faction.name = name
                    faction.save()
                continue

            faction = Faction(
                id=id,
                name=name,
            )
            new.append(faction)
            added += 1

        if new:
            Faction.objects.bulk_create(new)

        return added

    # -----------------------------------------------------------------------
    # NPC Corporations
    def import_npccorporation(self):
        added = 0

        self.cursor.execute("""
            SELECT  c.corporationID, i.itemName
            FROM    crpNPCCorporations c, invNames i
            WHERE   c.corporationID = i.itemID
        """)

        bulk_data = {}
        for row in self.cursor:
            bulk_data[int(row[0])] = row[1]

        data_map = Corporation.objects.in_bulk(bulk_data.keys())

        new = []
        for id, name in bulk_data.items():
            corp = data_map.get(id, None)
            if corp is not None:
                if corp.name != name:
                    print '==> Renamed %r to %r' % (corp.name, name)
                    corp.name = name
                    corp.save()
                continue

            corp = Corporation(
                id=id,
                name=name,
            )
            new.append(corp)
            added += 1

        if new:
            Corporation.objects.bulk_create(new)

        return added

    # -----------------------------------------------------------------------
    # Alliances
    def import_alliance(self):
        added = 0

        data = urllib2.urlopen(ALLIANCE_URL).read()
        root = ET.fromstring(data)

        bulk_data = {}
        for row in root.findall('result/rowset/row'):
            bulk_data[int(row.attrib['allianceID'])] = row

        data_map = Alliance.objects.in_bulk(bulk_data.keys())

        new = []
        # <row name="Goonswarm Federation" shortName="CONDI" allianceID="1354830081" executorCorpID="1344654522" memberCount="8960" startDate="2010-06-01 05:36:00"/>
        for id, row in bulk_data.items():
            alliance = data_map.get(id, None)
            if alliance is not None:
                pass

            else:
                alliance = Alliance(
                    id=id,
                    name=row.attrib['name'],
                    short_name=row.attrib['shortName'],
                )
                new.append(alliance)
                added += 1

        if new:
            Alliance.objects.bulk_create(new)

        # update any corporations in each alliance
        for id, row in bulk_data.items():
            corp_ids = []
            for corp_row in row.findall('rowset/row'):
                corp_ids.append(int(corp_row.attrib['corporationID']))

            Corporation.objects.filter(pk__in=corp_ids).update(alliance=id)
            Corporation.objects.filter(alliance_id=id).exclude(pk__in=corp_ids).update(alliance=None)

        return added

    # -----------------------------------------------------------------------
    # Conquerable stations
    def import_conquerable_station(self):
        added = 0
        
        data = urllib2.urlopen(STATION_URL).read()
        root = ET.fromstring(data)
        
        bulk_data = {}
        # <row stationID="61000042" stationName="442-CS V - 442 S T A L I N G R A D" stationTypeID="21644" solarSystemID="30002616" corporationID="1001879801" corporationName="VVS Corporition"/>
        for row in root.findall('result/rowset/row'):
            bulk_data[int(row.attrib['stationID'])] = row
        
        data_map = Station.objects.in_bulk(bulk_data.keys())
        
        new = []
        for id, row in bulk_data.items():
            station = data_map.get(id, None)
            if station is not None:
                # update the station name
                if station.name != row.attrib['stationName']:
                    station.name = row.attrib['stationName']
                    station.save()
                continue
            
            station = Station(
                id=id,
                name=row.attrib['stationName'],
                system_id=row.attrib['solarSystemID'],
            )
            new.append(station)
            added += 1
        
        if new:
            Station.objects.bulk_create(new)

        return added

    # -----------------------------------------------------------------------
    # RefTypes (journal entries)
    def import_reftypes(self):
        added = 0

        data = urllib2.urlopen(REF_TYPES_URL).read()
        root = ET.fromstring(data)

        bulk_data = {}
        # <row refTypeID="0" refTypeName="Undefined" />
        for row in root.findall('result/rowset/row'):
            bulk_data[int(row.attrib['refTypeID'])] = row

        data_map = RefType.objects.in_bulk(bulk_data.keys())

        new = []
        for id, row in bulk_data.items():
            reftype = data_map.get(id)
            if reftype is not None:
                if reftype.name != row.attrib['refTypeName']:
                    reftype.name = row.attrib['refTypeName']
                    reftype.save()
                continue

            reftype = RefType(
                id=id,
                name=row.attrib['refTypeName'],
            )
            new.append(reftype)
            added += 1

        if new:
            RefType.objects.bulk_create(new)

        return added

# ---------------------------------------------------------------------------

if __name__ == '__main__':
    importer = Importer()
    importer.import_all()
