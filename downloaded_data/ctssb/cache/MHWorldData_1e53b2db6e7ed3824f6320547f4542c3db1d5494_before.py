import sqlalchemy.orm
import mhdata.sql as db

from mhdata.io import DataMap
from mhdata.util import ensure, ensure_warn, get_duplicates

import mhdata.load.cfg as cfg

from .objectindex import ObjectIndex
from . import datafn

def build_sql_database(output_filename, mhdata):
    "Builds a SQLite database and outputs to output_filename"
    sessionbuilder = db.recreate_database(output_filename)

    with db.session_scope(sessionbuilder) as session:
        # Add languages before starting the build
        for language in cfg.supported_languages:
            session.add(db.Language(
                id=language,
                name=cfg.all_languages[language],
                is_complete=(language not in cfg.incomplete_languages)
            ))

        # Build the individual components
        # These functions are defined lower down in the file
        build_items(session, mhdata)
        build_locations(session, mhdata)
        build_monsters(session, mhdata)
        build_skills(session, mhdata)
        build_armor(session, mhdata)
        build_weapons(session, mhdata)
        build_decorations(session, mhdata)
        build_charms(session, mhdata)
        
    print("Finished build")


def build_items(session : sqlalchemy.orm.Session, mhdata):
    # Save basic item data first
    for entry in mhdata.item_map.values():
        item = db.Item(id=entry.id)
        item.category = entry['category']
        item.subcategory = entry['subcategory']
        item.rarity = entry['rarity'] or 0
        item.buy_price = entry['buy_price'] or 0
        item.sell_price = entry['sell_price'] or 0
        item.carry_limit = entry['carry_limit'] or 0
        item.points = entry['points'] or 0
        item.icon_name = entry['icon_name']
        item.icon_color = entry['icon_color']

        for language in cfg.supported_languages:
            item.translations.append(db.ItemText(
                lang_id=language,
                name=entry.name(language),
                description=entry['description'].get(language, None)
            ))

        session.add(item)

    # Now save item combination data
    for entry in mhdata.item_combinations:
        # should have been validated already
        session.add(db.ItemCombination(
            id=entry['id'],
            result_id=mhdata.item_map.id_of('en', entry['result']),
            first_id=mhdata.item_map.id_of('en', entry['first']),
            second_id=mhdata.item_map.id_of('en', entry['second']),
            quantity=entry['quantity']
        ))
    
    print("Built Items")

def build_locations(session : sqlalchemy.orm.Session, mhdata):
    for order_id, entry in enumerate(mhdata.location_map.values()):
        location_name = entry['name']['en']

        for language in cfg.supported_languages:
            session.add(db.Location(
                id=entry.id,
                order_id=order_id,
                lang_id=language,
                name=entry.name(language)
            ))

        for item_entry in entry['items']:
            item_lang = item_entry['item_lang']
            item_name = item_entry['item']
            item_id = mhdata.item_map.id_of(item_lang, item_name)

            session.add(db.LocationItem(
                location_id=entry.id,
                area=item_entry['area'],
                rank=item_entry['rank'],
                item_id=item_id,
                stack=item_entry['stack'],
                percentage=item_entry['percentage'],
                nodes=item_entry['nodes']
            ))
            
    print("Built locations")

def build_monsters(session : sqlalchemy.orm.Session, mhdata):
    item_map = mhdata.item_map
    location_map = mhdata.location_map
    monster_map = mhdata.monster_map
    monster_reward_conditions_map = mhdata.monster_reward_conditions_map

    # Save conditions first
    for condition_id, entry in monster_reward_conditions_map.items():
        for language in cfg.supported_languages:
            session.add(db.MonsterRewardConditionText(
                id=condition_id,
                lang_id=language,
                name=entry.name(language)
            ))

    # Save monsters
    for order_id, entry in enumerate(monster_map.values()):
        monster = db.Monster(
            id=entry.id,
            order_id=order_id,
            size=entry['size']
        )

        # Save basic weakness summary data
        if 'weaknesses' in entry and entry['weaknesses']:
            monster.has_weakness = True
            weaknesses = entry['weaknesses']
            for key, value in weaknesses['normal'].items():
                setattr(monster, 'weakness_'+key, value)

            if 'alt' in weaknesses:
                monster.has_alt_weakness = True
                for key, value in weaknesses['normal'].items():
                    setattr(monster, 'alt_weakness_'+key, value)

        # Save language data
        for language in cfg.supported_languages:
            alt_state_description = None
            if 'alt_description' in entry.get('weaknesses', {}):
                alt_state_description = entry['weaknesses']['alt_description'][language]

            monster.translations.append(db.MonsterText(
                lang_id=language,
                name=entry.name(language),
                ecology=entry['ecology'][language],
                description=entry['description'][language],
                alt_state_description=alt_state_description
            ))

        # Save hitzones
        for hitzone_data in entry.get('hitzones', []):
            hitzone = db.MonsterHitzone(
                cut=hitzone_data['cut'],
                impact=hitzone_data['impact'],
                shot=hitzone_data['shot'],
                fire=hitzone_data['fire'],
                water=hitzone_data['water'],
                thunder=hitzone_data['thunder'],
                dragon=hitzone_data['dragon'],
                ko=hitzone_data['ko'])

            for lang, part_name in hitzone_data['hitzone'].items():
                hitzone.translations.append(db.MonsterHitzoneText(
                    lang_id=lang,
                    name=part_name
                ))

            monster.hitzones.append(hitzone)

        # Save breaks
        for break_data in entry.get('breaks', []):
            breakzone = db.MonsterBreak(
                flinch=break_data['flinch'],
                wound=break_data['wound'],
                sever=break_data['sever'],
                extract=break_data['extract']
            )
                        
            for lang, part_name in break_data['part'].items():
                breakzone.translations.append(db.MonsterBreakText(
                    lang_id=lang,
                    part_name=part_name
                ))

            monster.breaks.append(breakzone)

        # Create a temp base map of the conditions
        # This temp map extends the global map with monster-specific conditions
        #monster_conditions = DataMap(reward_conditions_map)
        #monster_conditions.extend(entry.get('break_conditions', []))

        # Save hunting rewards
        for reward in entry.get('rewards', []):
            condition_en = reward['condition_en']
            rank = reward['rank']
            item_name = reward['item_en']

            condition_id = monster_reward_conditions_map.id_of('en', condition_en)
            item_id = item_map.id_of('en', item_name)

            monster.rewards.append(db.MonsterReward(
                condition_id=condition_id,
                rank=rank,
                item_id=item_id,
                stack=reward['stack'],
                percentage=reward['percentage']
            ))

        # Save Habitats
        for location_name, habitat_values in entry.get('habitats', {}).items():
            location_id = location_map.id_of("en", location_name)
            ensure(location_id, "Invalid location name " + location_name)

            monster.habitats.append(db.MonsterHabitat(
                location_id=location_id,
                **habitat_values
            ))

        # Complete - add to session
        session.add(monster)

    print("Built Monsters")

def build_skills(session : sqlalchemy.orm.Session, mhdata):
    skill_map = mhdata.skill_map

    for skill_entry in skill_map.values():
        skilltree = db.SkillTree(
            id=skill_entry.id,
            max_level=len(skill_entry['levels']),
            icon_color=skill_entry['icon_color'])

        for language in cfg.supported_languages:
            skilltree.translations.append(db.SkillTreeText(
                lang_id=language,
                name=skill_entry.name(language),
                description=skill_entry['description'][language]
            ))

            for effect in skill_entry['levels']:
                skilltree.skills.append(db.Skill(
                    lang_id=language,
                    level=effect['level'],
                    description=effect['description'][language]
                ))

        session.add(skilltree)
    
    print("Built Skills")

def build_armor(session : sqlalchemy.orm.Session, mhdata):
    item_map = mhdata.item_map
    skill_map = mhdata.skill_map
    armorset_map = mhdata.armorset_map
    armorset_bonus_map = mhdata.armorset_bonus_map
    armor_map = mhdata.armor_map

    # Create reverse mapping. In SQL, armor links to armorset instead
    armor_to_armorset = {}
    armorset_to_bonus = {}

    # Write entries from armor set bonuses
    # These are written first as they are "linked to"
    for bonus_entry in armorset_bonus_map.values():
        for language in cfg.supported_languages:
            session.add(db.ArmorSetBonusText(
                id=bonus_entry.id,
                lang_id=language,
                name=bonus_entry.name(language)
            ))
        
        for skill_name, required in datafn.iter_setbonus_skills(bonus_entry):
            skill_id = skill_map.id_of('en', skill_name)
            session.add(db.ArmorSetBonusSkill(
                setbonus_id=bonus_entry.id,
                skilltree_id=skill_id,
                required=required
            ))

    # Write entries for armor sets
    for set_id, entry in armorset_map.items():
        armor_lang = entry['armor_lang']
        armorset_bonus_id = None

        if entry['bonus']:
            armorset_bonus_id = armorset_bonus_map.id_of(armor_lang, entry['bonus'])
            ensure(armorset_bonus_id, f"Armorset bonus {entry['bonus']} in armorsets doesn't exist")
            armorset_to_bonus[set_id] = armorset_bonus_id

        armorset = db.ArmorSet(
            id=set_id,
            rank=entry['rank'],
            armorset_bonus_id=armorset_bonus_id
        ) 
        
        for language in cfg.supported_languages:
            armorset.translations.append(db.ArmorSetText(
                lang_id=language,
                name=entry.name(language)
            ))

        session.add(armorset)

        # Populate reverse map (to allow armor to link to armorset)
        for part in cfg.armor_parts:
            if not entry[part]:
                continue
            
            armor_reverse_id = mhdata.armor_map.id_of(armor_lang, entry[part])
            armor_to_armorset[armor_reverse_id] = set_id

    # Write entries for armor
    for order_id, entry in enumerate(armor_map.values()):
        armor_name_en = entry.name('en')

        armor = db.Armor(id = entry.id)
        armor.order_id = order_id
        armor.rarity = entry['rarity']
        armor.armor_type = entry['type']
        armor.male = entry['gender'] in ('male', 'both')
        armor.female = entry['gender'] in ('female', 'both')
        armor.slot_1 = entry['slot_1']
        armor.slot_2 = entry['slot_2']
        armor.slot_3 = entry['slot_3']
        armor.defense_base = entry['defense_base']
        armor.defense_max = entry['defense_max']
        armor.defense_augment_max = entry['defense_augment_max']
        armor.fire = entry['defense_fire']
        armor.water = entry['defense_water']
        armor.thunder = entry['defense_thunder']
        armor.ice = entry['defense_ice']
        armor.dragon = entry['defense_dragon']

        armorset_id = armor_to_armorset.get(entry.id, None)
        armorset_entry = armorset_map[armorset_id]
        armor.rank = armorset_entry['rank']
        armor.armorset_id = armorset_id
        armor.armorset_bonus_id = armorset_to_bonus.get(armorset_id, None)

        for language in cfg.supported_languages:
            armor.translations.append(db.ArmorText(
                lang_id=language, 
                name=entry.name(language)
            ))

        # Armor Skills
        for skill, level in datafn.iter_skill_points(entry):
            skill_id = skill_map.id_of('en', skill)
            armor.skills.append(db.ArmorSkill(
                skilltree_id=skill_id,
                level=level
            ))

        # Armor Crafting
        for item_name, quantity in datafn.iter_armor_recipe(entry):
            item_id = item_map.id_of('en', item_name)
            armor.craft_items.append(db.ArmorRecipe(
                item_id=item_id,
                quantity=quantity
            ))

        session.add(armor)

    print("Built Armor")

def build_weapons(session : sqlalchemy.orm.Session, mhdata):
    item_map = mhdata.item_map
    weapon_map = mhdata.weapon_map

    # Prepass to determine which weapons are "final"
    # All items that are a previous to another are "not final"
    all_final = set(weapon_map.keys())
    for entry in weapon_map.values():
        if not entry.get('previous_en', None):
            continue
        try:
            prev_id = weapon_map.id_of('en', entry['previous_en'])
            all_final.remove(prev_id)
        except KeyError:
            pass

    # now iterate over actual weapons
    for weapon_id, entry in weapon_map.items():
        weapon = db.Weapon(id = weapon_id)
        
        # Add language translations
        for language in cfg.supported_languages:
            weapon.translations.append(db.WeaponText(
                lang_id = language,
                name = entry.name(language)
            ))

        weapon.weapon_type = entry['weapon_type']
        weapon.rarity = entry['rarity']
        weapon.attack = entry['attack']
        weapon.defense = entry['defense'] or 0
        weapon.slot_1 = entry['slot_1']
        weapon.slot_2 = entry['slot_2']
        weapon.slot_3 = entry['slot_3']

        weapon.element1 = entry['element1']
        weapon.element1_attack = entry['element1_attack']
        weapon.element2 = entry['element2']
        weapon.element2_attack = entry['element2_attack']
        weapon.element_hidden = entry['element_hidden']

        weapon.sharpness = entry['sharpness']
        weapon.sharpness_complete = entry['sharpness_complete']
        weapon.kinsect_bonus = entry.get('kinsect_bonus', None)

        weapon.craftable = False # set to true later if it can be crafted
        weapon.final = weapon_id in all_final

        if entry.get('previous', None):
            previous_weapon_id = weapon_map.id_of("en", entry['previous'])
            ensure(previous_weapon_id, f"Weapon {entry['previous']} does not exist")
            weapon.previous_weapon_id = previous_weapon_id

        # Add crafting/upgrade recipes
        for recipe in entry.get('craft', {}):
            recipe_type = recipe['type']
            if recipe_type == "Create":
                weapon.craftable = True
                
            for item, quantity in datafn.iter_weapon_recipe(recipe):
                item_id = item_map.id_of("en", item)
                session.add(db.WeaponRecipe(
                    weapon_id = weapon_id,
                    item_id = item_id,
                    quantity = quantity,
                    recipe_type = recipe_type
                ))

        # Bow data (if any)
        if entry.get("bow", None):
            bow_data = entry['bow']
            weapon.coating_close = bow_data['close']
            weapon.coating_power = bow_data['power']
            weapon.coating_poison = bow_data['poison']
            weapon.coating_paralysis = bow_data['paralysis']
            weapon.coating_sleep = bow_data['sleep']
            weapon.coating_blast = bow_data['blast']

        # Gun data
        if entry.get("gun", None):
            gun_data = entry['gun']
            weapon.deviation = gun_data['deviation']
            weapon.special_ammo = gun_data['special']
            weapon.ammo_normal_1 = gun_data['normal_1']
            weapon.ammo_normal_2 = gun_data['normal_2']
            weapon.ammo_normal_3 = gun_data['normal_3']
            weapon.ammo_pierce_1 = gun_data['pierce_1']
            weapon.ammo_pierce_2 = gun_data['pierce_2']
            weapon.ammo_pierce_3 = gun_data['pierce_3']
            weapon.ammo_spread_1 = gun_data['spread_1']
            weapon.ammo_spread_2 = gun_data['spread_2']
            weapon.ammo_spread_3 = gun_data['spread_3']
            weapon.ammo_sticky_1 = gun_data['sticky_1']
            weapon.ammo_sticky_2 = gun_data['sticky_2']
            weapon.ammo_sticky_3 = gun_data['sticky_3']
            weapon.ammo_cluster_1 = gun_data['cluster_1']
            weapon.ammo_cluster_2 = gun_data['cluster_2']
            weapon.ammo_cluster_3 = gun_data['cluster_3']
            weapon.ammo_recover_1 = gun_data['recover_1']
            weapon.ammo_recover_2 = gun_data['recover_2']
            weapon.ammo_poison_1 = gun_data['poison_1']
            weapon.ammo_poison_2 = gun_data['poison_2']
            weapon.ammo_paralysis_1 = gun_data['paralysis_1']
            weapon.ammo_paralysis_2 = gun_data['paralysis_2']
            weapon.ammo_sleep_1 = gun_data['sleep_1']
            weapon.ammo_sleep_2 = gun_data['sleep_2']
            weapon.ammo_exhaust_1 = gun_data['exhaust_1']
            weapon.ammo_exhaust_2 = gun_data['exhaust_2']
            weapon.ammo_flaming = gun_data['flaming']
            weapon.ammo_water = gun_data['water']
            weapon.ammo_freeze = gun_data['freeze']
            weapon.ammo_thunder = gun_data['thunder']
            weapon.ammo_dragon = gun_data['dragon']
            weapon.ammo_slicing = gun_data['slicing']
            weapon.ammo_wyvern = gun_data['wyvern']
            weapon.ammo_demon = gun_data['demon']
            weapon.ammo_armor = gun_data['armor']
            weapon.ammo_tranq = gun_data['tranq']
        
        session.add(weapon)

    print("Built Weapons")

def build_decorations(session : sqlalchemy.orm.Session, mhdata):
    "Performs the build process for decorations. Must be done after skills"

    skill_map = mhdata.skill_map
    decoration_map = mhdata.decoration_map

    for decoration_id, entry in decoration_map.items():
        skill_id = skill_map.id_of('en', entry['skill_en'])
        ensure(skill_id, f"Decoration {entry.name('en')} refers to " +
            f"skill {entry['skill_en']}, which doesn't exist.")

        ensure("chances" in entry, "Missing chance data for " + entry.name('en'))
        
        decoration = db.Decoration(
            id=decoration_id,
            rarity=entry['rarity'],
            slot=entry['slot'],
            icon_color=entry['icon_color'],
            skilltree_id=skill_id,
            mysterious_feystone_chance=entry['chances']['mysterious_feystone_chance'],
            glowing_feystone_chance=entry['chances']['glowing_feystone_chance'],
            worn_feystone_chance=entry['chances']['worn_feystone_chance'],
            warped_feystone_chance=entry['chances']['warped_feystone_chance']
        )

        for language in cfg.supported_languages:
            decoration.translations.append(db.DecorationText(
                lang_id=language,
                name=entry.name('en')
            ))

        session.add(decoration)

    print("Built Decorations")

def build_charms(session : sqlalchemy.orm.Session, mhdata):
    item_map = mhdata.item_map
    skill_map = mhdata.skill_map
    charm_map = mhdata.charm_map

    for order_id, entry in enumerate(charm_map.values()):
        # Note: previous is ok to be None
        previous = charm_map.id_of('en', entry['previous_en'])

        charm = db.Charm(
            id=entry.id,
            order_id=order_id,
            previous_id=previous,
            rarity=entry['rarity']
        )

        for language in cfg.supported_languages:
            charm.translations.append(db.CharmText(
                lang_id=language,
                name=entry.name(language)
            ))

        for skill_en, level in entry['skills'].items():
            skill_id = skill_map.id_of('en', skill_en)
            ensure(skill_id, f"Charm {entry.name('en')} refers to " +
                f"item {skill_en}, which doesn't exist.")

            charm.skills.append(db.CharmSkill(
                skilltree_id=skill_id,
                level=level
            ))

        for item_en, quantity in entry['craft'].items():
            item_id = item_map.id_of('en', item_en)
            ensure(item_id, f"Charm {entry.name('en')} refers to " +
                f"item {item_en}, which doesn't exist.")

            charm.craft_items.append(db.CharmRecipe(
                item_id=item_id,
                quantity=quantity
            ))

        session.add(charm)

    print("Built Charms")
