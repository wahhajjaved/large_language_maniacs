import copy

class Foundation:
    """Base stats and data"""

    import random
    import equip
    import textwrap
    import feat
    import satk_list as satk
    import spell_list as spell
    import ai as ai_class
    import sys
    import uuid

    def __init__(self, name, side, AC, move, loc, hp, tilesize, str, dex, con, int, wis, cha, feat_list, type, subtype, size, reach, fort, ref, will, hands, legs):
        self.name = name
        self.id = self.uuid.uuid4()
        self.side = side
        self.AC = AC
        self.move = move
        self.startloc = loc
        self.loc = loc
        self.hp = hp
        self.tilesize = tilesize
        self.str = str
        self.dex = dex
        self.con = con
        self.int = int
        self.wis = wis
        self.cha = cha
        self.feat_list = feat_list
        self.type = type
        self.subtype = subtype
        self.size = size
        self.reach = reach
        self.fort = fort
        self.ref = ref
        self.will = will
        self.hands = hands
        self.legs = legs
        
        self.ai = None

        self.bab = 0
        self.arcane = False
        self.divine = False
        self.hit_die = 10
        self.damage = 0
        self.temp_dmg = 0
        self.damage_con = "Normal"
        self.equip_list = []
        self.melee_weaps = []
        self.ranged_weaps = []
        self.slots = {"armor":None, "belts":None, "body":None, "chest":None, "eyes":None, "feet":None, "hands":None, "head":None, "headband":None, "neck":None, "ring":[None,None], "shoulders":None, "wield":[None for i in range(self.hands)], "wrists":None}
        self.conditions = dict()
        
        self.ftr_wt = []
        self.ftr_mast = None
        
        self.ki_pool = 0
        self.ki_spent = 0
        self.ki_types = []
        
        self.rgr_fe = []
        
        self.sa = []
        self.sa_list = []
        self.sq = []
        self.sq_list = []
        self.da = []
        self.da_list = []
        self.vuln = []
        self.res = {}
        self.immune = []
        
        self.cast_stat = None
        
        self.spell_list_mem = [{} for i in range(0,10)]
        self.spell_mem_max = [0 for i in range(0,10)]
        self.sla_list = []
        self.max_spell_lvl = 0
        
        self.lang = []
        self.lang_spec = []
        
        self.dropped = []
        
    def __sizeof__(self):
        return object.__sizeof__(self) + \
            sum(sys.getsizeof(v) for v in self.__dict__.values())

    def copy(self):
        return copy.copy(self)
    
    def model_copy(self):
        model_copy = copy.copy(self)
        del model_copy.ai
        model_copy.model = True
        
        return model_copy

###################################################################
#
# Initialization functions

    def set_ai(self,mat):
        if self.ai == None:
            self.ai = self.ai_class.AI(self, mat)
        else:
            self.ai.mat = mat
        
    def set_tactic(self,tactic):
        if self.ai == None:
            pass
        else:
            self.ai.set_tactic(tactic)
    
    def set_targeting(self,target):
        if self.ai == None:
            pass
        else:
            self.ai.target = target
        

###################################################################
#
# General calculation functions

    def current_hp(self):
        return self.get_hp() - self.damage

    def range_pen(self, dist):
        pen = int(dist / self.weap_range()) * -2

        if pen < -10:
            pen = -10

        return pen

    def stat_bonus(self, stat):
        if stat >= 0:
            return int((stat - 10) / 2)
        else:
            return 0

    def tile_in_token(self, tile):
        x_dist = tile[0] - self.loc[0]
        y_dist = tile[1] - self.loc[1]

        return (x_dist in range(0,self.tilesize[0]) and y_dist in range(0,self.tilesize[1]))

    def TWF_pen(self, weap, bon_calc=False, off=False, light=False):
        
        offhand = self.slots["wield"][1]
        
        off = ((weap == offhand and not bon_calc) or off)
        
        light = (("L" in self.weap_type(offhand) and not bon_calc) or light)
        
        if (not self.has_offhand() and not bon_calc):
            return 0
        elif off:
            pen = -10
            pen += self.feat.two_weapon_fighting_bon(self)[1]
        else:
            pen = -6
            pen += self.feat.two_weapon_fighting_bon(self)[0]

        if light:
            pen += 2

        return pen


###################################################################
#
# Import functions

    def add_weapon(self, weapon, active=False, off=False):
        self.equip_list.append(weapon)

        if "M" in weapon.atk_type:
            self.melee_weaps.append(len(self.equip_list) - 1)
        if "R" in weapon.atk_type:
            self.ranged_weaps.append(len(self.equip_list) - 1)

        if active:
            self.set_weapon(len(self.equip_list) - 1)

        if off:
            self.set_off(len(self.equip_list) - 1)

    def add_armor(self, armor, active=False):
        self.equip_list.append(armor)
        if active:
            self.set_armor(len(self.equip_list) - 1)

    def add_shield(self, shield, active=False):
        self.equip_list.append(shield)
        if active:
            self.set_shield(len(self.equip_list) - 1)
    
    def add_spell_mem(self, spell, count=1):
        level_list = spell.lvl_parse()
        if self.charClass not in level_list:
            raise Exception("This spell cannot be used by class {}".format(self.charClass))
            
        spell_lev = level_list[self.charClass]
        spells_mem = self.spell_list_mem[spell_lev].values()
        if sum(i[1] for i in spells_mem) + count > self.spell_mem_max[spell_lev]:
            raise Exception("Not enough free spell slots of level {} to add spell".format(spell_lev))
        
        if spell.name not in self.spell_list_mem[spell_lev]:
            self.spell_list_mem[spell_lev][spell.name] = [spell,count]
        else:
            cur_count = self.spell_list_mem[spell_lev][spell.name][1]
            self.spell_list_mem[spell_lev][spell.name] = [spell,cur_count+count]

###################################################################
#
# Equipment data retrieval functions
    
    def item_type(self, val):
        return self.equip_list[val].item
    
    def default(self, val):
        if val == None:
            return True
        return self.equip_list[val].default

    def weap_basename(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None or val < 0 or self.item_type(val) != "weapon":
            return self.unarmed.name

        return self.equip_list[val].name

    def weap_name(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None or val < 0 or self.item_type(val) != "weapon":
            return self.unarmed.fullname()

        return self.equip_list[val].fullname()

    def weap_group(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None or val < 0 or self.item_type(val) != "weapon":
            return self.unarmed.group

        return self.equip_list[val].group

    def weap_type(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None or val < 0 or self.item_type(val) != "weapon":
            return self.unarmed.atk_type

        return self.equip_list[val].atk_type

    def weap_dmg(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None or val < 0 or self.item_type(val) != "weapon":
            return self.unarmed.atk_damage

        return self.equip_list[val].atk_damage

    def weap_avg_dmg(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None or val < 0 or self.item_type(val) != "weapon":
            return self.unarmed.atk_damage

        return self.equip_list[val].avg_dmg()

    def weap_range(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None or val < 0 or self.item_type(val) != "weapon":
            return self.unarmed.range

        return self.equip_list[val].range

    def weap_crit_range(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None or val < 0 or self.item_type(val) != "weapon":
            crit_rng = self.unarmed.crit_range
        else:
            crit_rng = self.equip_list[val].crit_range

        if self.feat.improved_critical(self, val):
            crit_rng = 21 - ((21 - crit_rng) * 2)

        return crit_rng

    def weap_crit_mult(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None or val < 0 or self.item_type(val) != "weapon":
            crit_mult = self.unarmed.crit_mult
        else:
            crit_mult = self.equip_list[val].crit_mult

        if self.ftr_wm():
            crit_mult += 1

        return crit_mult

    def weap_bon(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None or val < 0 or self.item_type(val) != "weapon":
            return self.unarmed.weap_bon

        return self.equip_list[val].weap_bon

    def weap_disarm(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None or val < 0 or self.item_type(val) != "weapon":
            return self.unarmed.disarm

        return self.equip_list[val].disarm

    def weap_reach(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None or val < 0 or self.item_type(val) != "weapon":
            return self.unarmed.reach

        return self.equip_list[val].reach

    def weap_trip(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None or val < 0 or self.item_type(val) != "weapon":
            return self.unarmed.trip

        return self.equip_list[val].trip

    def weap_mwk(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None or val < 0 or self.item_type(val) != "weapon":
            return self.unarmed.mwk

        return self.equip_list[val].mwk

    def weap_hands(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None or val < 0 or self.item_type(val) != "weapon":
            return self.unarmed.hands

        return self.equip_list[val].hands

    def has_weapon(self):
        return self.weap_name() != "unarmed strike"
    
    def has_offhand(self):
        main = self.slots["wield"][0]
        offhand = self.slots["wield"][1]
        
        return offhand != None and offhand != main and self.item_type(offhand) == "weapon"
    
    def curr_weap(self):
        return self.slots["wield"][0]

    # weap_list: returns list of weapons wielded (as array for future functionality expansion)
    
    def weap_list(self,no_array=False):
        list = []
        i = 0
        
        while i < len(self.slots["wield"]):        # Using while loop in order to vary index step by weapon hands
            item = self.slots["wield"][i]
            if item != None and self.item_type(item) == "weapon":
                if no_array:
                    list.append(item)
                else:
                    list.append([item])
            i += self.weap_hands(item)
        
        return list
    
    def weap_list_all(self):
        list = []
        
        for item in range(len(self.equip_list)):
            if self.equip_list[item] != None and self.item_type(item) == "weapon":
                list.append(item)
        
        return list
    
    def owns_weapon(self,weap_name):
        for item in range(len(self.equip_list)):
            if self.equip_list[item] != None and self.item_type(item) == "weapon" and self.weap_name(item) == weap_name:
                return [True,item]
        
        return [False,None]
        
    ##################################################################################

    def armor_name(self, val=None):
        if val == None:
            val = self.slots["armor"]
        if val == None or val < 0 or self.item_type(val) != "armor":
            return ""

        return self.equip_list[val].fullname()

    def armor_type(self, val=None):
        if val == None:
            val = self.slots["armor"]
        if val == None or val < 0 or self.item_type(val) != "armor":
            return ""

        return self.equip_list[val].type

    def armor_armor_bon(self, val=None, public=False):
        if val == None:
            val = self.slots["armor"]
        if val == None or val < 0 or self.item_type(val) != "armor":
            return 0

        bon = self.equip_list[val].armor_bon
        
        if not public:
            bon += self.equip_list[val].ench_bon
            
        return bon

    def armor_max_dex(self, val=None):
        if val == None:
            val = self.slots["armor"]
        if val == None:
            return 99       # no max dex when unarmored
        if val < 0 or self.item_type(val) != "armor":
            return 0

        return self.equip_list[val].max_dex

    def armor_armor_check(self, val=None):
        if val == None:
            val = self.slots["armor"]
        if val == None or val < 0 or self.item_type(val) != "armor":
            return 0

        return self.equip_list[val].armor_check

    def armor_asf(self, val=None):
        if val == None:
            val = self.slots["armor"]
        if val == None or val < 0 or self.item_type(val) != "armor":
            return 0

        return self.equip_list[val].asf

    def armor_ench_bon(self, val=None):
        if val == None:
            val = self.slots["armor"]
        if val == None or val < 0 or self.item_type(val) != "armor":
            return 0

        return self.equip_list[val].ench_bon

    def has_armor(self):
        return self.armor_name() != ""
        
    ##################################################################################

    def shield_name(self, val=None):
        if val == None:
            val = self.slots["wield"][1]
        if val == None or val < 0 or self.item_type(val) != "armor":
            return ""

        return self.equip_list[val].fullname()

    def shield_type(self, val=None):
        if val == None:
            val = self.slots["wield"][1]
        if val == None or val < 0 or self.item_type(val) != "armor":
            return ""

        return self.equip_list[val].type

    def shield_shield_bon(self, val=None, public=False):
        if val == None:
            val = self.slots["wield"][1]
        if val == None or val < 0 or self.item_type(val) != "armor":
            return 0

        bon = self.equip_list[val].shield_bon
        
        if not public:
            bon += self.equip_list[val].ench_bon
            
        return bon

    def shield_armor_check(self, val=None):
        if val == None:
            val = self.slots["wield"][1]
        if val == None or val < 0 or self.item_type(val) != "armor":
            return 0

        return self.equip_list[val].armor_check

    def shield_ench_bon(self, val=None):
        if val == None:
            val = self.slots["wield"][1]
        if val == None or val < 0 or self.item_type(val) != "armor":
            return 0

        return self.equip_list[val].ench_bon

    def shield_hands(self, val=None):
        if val == None:
            val = self.slots["wield"][1]
        if val == None or val < 0 or self.item_type(val) != "armor":
            return 0

        return self.equip_list[val].hands

    def has_shield(self):
        return self.shield_name() != ""

###################################################################
#
# Spell data retrieval functions
    
    def spell_list(self,type="All",target="All",minlevel=0,maxlevel="Max"):
        
        spell_list = self.mem_spell_list(type,target)
        
        return spell_list

    def mem_spell_list(self,type="All",target="All",minlevel=0,maxlevel="Max"):
        spell_list = []
        spell_list_temp = []
        
        if maxlevel == "Max":
            maxlevel = self.max_spell_lvl
        
        if maxlevel > 9:
            maxlevel = 9
        
        if minlevel > 9:
            minlevel = 9
            
        if minlevel > maxlevel:
            minlevel = maxlevel
        
        if maxlevel < 0:
            maxlevel = self.max_spell_lvl + maxlevel
            if maxlevel < 0:
                maxlevel = 0
        
        if minlevel < 0:
            minlevel = maxlevel + minlevel
            if minlevel < 0:
                minlevel = 0
    
        for SL in range(maxlevel,minlevel-1,-1):
            spell_list_temp = self.spell_list_mem[SL].copy()
            if len(spell_list_temp) == 0:
                continue
            
            for spellname,spells_memd in spell_list_temp.items():
                
                [spell,count] = spells_memd
                #print("spell: {}, count: {}".format(spell.name,count))
                if count <= 0:
                    continue
                if type == "All":
                    spell_list.append(spell)
                    continue
                if type == "Damage" and spell.dmg:
                    spell_list.append(spell)
                    continue
                if type == "Buff" and spell.buff:
                    spell_list.append(spell)
                    continue
                if type == "Debuff" and spell.debuff:
                    spell_list.append(spell)
                    continue
            
            spell_list_temp = spell_list[:]
            spell_list = []
                    
            for spell in spell_list_temp:
                if target == "All":
                    spell_list.append(spell)
                    continue
                if target == "Single" and spell.is_single():
                    spell_list.append(spell)
                    continue
                if target == "Multi" and spell.is_multi():
                    spell_list.append(spell)
                    continue            
        
        return spell_list

###################################################################
#
# Attack selection functions

    def avg_weap_dmg(self, weap, target, dist=0, FRA=True, offhand=False, oh_calc=False, light=False, fob=False):
            
        avg_dmg = 0
        weap_bon = self.get_atk_bon(dist, FRA, target.type, target.subtype, weap=weap, offhand=offhand, bon_calc=oh_calc, light=light, fob=fob)
        dmg_bon = self.get_base_dmg_bon(dist, target.type, target.subtype, weap=weap, offhand=offhand)
        AC = target.get_AC(self.type, self.subtype, atk_type=self.weap_type(weap))
        avg_base_dmg = self.weap_avg_dmg(weap)

        for attack in weap_bon:
            chance_to_hit = (21 - (AC - attack)) / 20.0
            if chance_to_hit <= 0:
                chance_to_hit = 0.05
            if chance_to_hit >= 1:
                chance_to_hit = 0.95
            chance_to_threat = (21 - self.weap_crit_range(weap)) / 20.0
            if chance_to_threat <= 0:
                chance_to_threat = 0.05
            if chance_to_threat >= chance_to_hit:
                chance_to_threat = chance_to_hit

            avg_hit_dmg = avg_base_dmg + dmg_bon

            if avg_hit_dmg < 0:
                avg_hit_dmg = 0

            avg_crit_bonus_dmg = avg_base_dmg * (self.weap_crit_mult(weap) - 1)
            
            avg_dmg += (chance_to_hit * avg_hit_dmg) + (chance_to_threat * chance_to_hit * avg_crit_bonus_dmg)
        
        return avg_dmg
    

    def avg_weap_dmgs(self, target, dist=0, weap_list=None, FRA=True, offhand=False, prn=False, oh_calc=False, light=False, fob=False):
        if weap_list == None:
            weap_list = self.weap_list_all()
        
        avg_dmgs = []
        
        for weap_i in weap_list:
                               
            avg_dmg = self.avg_weap_dmg(weap_i, target, dist, FRA, offhand, oh_calc, light, fob)
            
            avg_dmgs.append([weap_i,avg_dmg])
            
        avg_dmgs.sort(key=lambda i: i[1], reverse=True)
        
        if not prn:
            return avg_dmgs
        else:
            output_list = dict()
            for [weap,avg] in avg_dmgs:
                output_list[self.weap_name(weap)] = avg
            
            return output_list
                
    def best_weap(self, target, dist=0, weap_list=None, FRA=True, offhand=False, dmg_val=False, fob=False):
        if weap_list == None:
            weap_list = self.weap_list()
        
        if dmg_val:
            return self.avg_weap_dmgs(target, dist, weap_list, FRA, offhand=offhand, fob=fob)[0]
        else:
            return self.avg_weap_dmgs(target, dist, weap_list, FRA, offhand=offhand, fob=fob)[0][0]

    #############################
    #
    # Melee attack selection functions
    
    def best_melee_opt(self, target, dist=0, FRA=True, prn=False):        
        melee_opts = []
        
        best_weap_val = self.best_melee_equip(target, dist, FRA, dmg_val=True)
        
        if best_weap_val:
            best_weap = ["weap",best_weap_val[0],best_weap_val[1]]
            melee_opts.append(best_weap)
        
        if "flurry of blows" in self.sa and FRA:
            best_fob_val = self.best_melee_fob(target, dist, FRA, dmg_val=True)
            
            if best_fob_val:
                best_fob = ["fob",best_fob_val[0],best_fob_val[1]]
                melee_opts.append(best_fob)
        
        melee_opts.sort(key=lambda i:i[2], reverse=True)
        
        if not prn:
            return melee_opts[0]
        else:
            output_list = dict()
            for [atk_type,weap,avg] in melee_opts:
                if atk_type == "weap":
                    if type(weap) is list:
                        weap_name = self.weap_name(weap[0]) + ' and ' + self.weap_name(weap[1])
                    else:
                        weap_name = self.weap_name(weap)
                elif atk_type == "fob":
                    weap_name = self.weap_name(weap) + " flurry of blows"
                output_list[weap_name] = avg
                        
            return output_list       
        

    def best_melee_weap(self, target, dist=0, FRA=True, dmg_val=False):
        if not self.melee_weaps:
            return None
        else:
            return self.best_weap(target, dist, self.melee_weaps, FRA, dmg_val=dmg_val)
    
    def best_mainhand_weap(self, target, dist=0, FRA=True, dmg_val=False):
        if not self.melee_weaps:
            return None
        
        mainhand_weaps = []
        
        for weap in self.weap_list_all():
            if self.weap_hands(weap) == 1 and "M" in self.weap_type(weap):
                mainhand_weaps.append(weap)
        
        if not mainhand_weaps:
            return None
        
        return self.best_weap(target, dist, mainhand_weaps, FRA, False, dmg_val=dmg_val)
    
    def best_twohand_weap(self, target, dist=0, FRA=True, dmg_val=False):
        if not self.melee_weaps:
            return None
        
        twohand_weaps = []
        
        for weap in self.weap_list_all():
            if self.weap_hands(weap) == 2 and "M" in self.weap_type(weap):
                twohand_weaps.append(weap)
        
        if not twohand_weaps:
            return None
        
        return self.best_weap(target, dist, twohand_weaps, FRA, False, dmg_val=dmg_val)
    
    def best_dual_wield(self, target, dist=0, FRA=True, dmg_val=False, prn=False):
        if len(self.melee_weaps) < 2:
            return None
        
        dw_weaps = []
        
        for weap1 in self.weap_list_all():
            for weap2 in self.weap_list_all():
                if weap1 == weap2:
                    continue
                if self.weap_hands(weap1) == 1 and "M" in self.weap_type(weap1) and self.weap_hands(weap2) == 1 and "M" in self.weap_type(weap2):
                    dw_weaps.append([weap1,weap2])       
        
        if not dw_weaps:
            return None
        
        dw_weaps_dmg = []
        
        for [weap1,weap2] in dw_weaps:
            light = ("L" in self.weap_type(weap2))
            weap1_dmg = self.avg_weap_dmg(weap1, target, dist, FRA, False, True, light)
            weap2_dmg = self.avg_weap_dmg(weap1, target, dist, FRA, True, True, light)
            dw_weaps_dmg.append([[weap1,weap2],weap1_dmg+weap2_dmg])
            
        dw_weaps_dmg.sort(key=lambda i: i[1], reverse=True)
        
        if not prn:
            if dmg_val:
                return dw_weaps_dmg[0]
            else:
                return dw_weaps_dmg[0][0]
        else:
            output_list = dict()
            for [weap,avg] in dw_weaps_dmg:
                if type(weap) is list:
                    weap_name = self.weap_name(weap[0]) + ' and ' + self.weap_name(weap[1])
                else:
                    weap_name = self.weap_name(weap)
                output_list[weap_name] = avg
                        
            return output_list
    
    def best_melee_equip(self, target, dist=0, FRA=True, prn=False, dmg_val=False):
        if not self.melee_weaps:
            return None
        
        best_opts = []
        
        #############################
        #
        # One-handed single-weapon attack
        
        best_opts.append(self.best_mainhand_weap(target, dist, FRA, True))
        
        #############################
        #
        # Two-handed single-weapon attack
        
        best_opts.append(self.best_twohand_weap(target, dist, FRA, True))
        
        #############################
        #
        # Dual-wield attack
        
        best_opts.append(self.best_dual_wield(target, dist, FRA, True))
        
        while None in best_opts:
            best_opts.remove(None)
            
        best_opts.sort(key=lambda i: i[1], reverse=True)
        
        if not prn:
            if dmg_val:
                return best_opts[0]
            else:
                return best_opts[0][0]
        else:
            output_list = dict()
            for [weap,avg] in best_opts:
                if type(weap) is list:
                    weap_name = self.weap_name(weap[0]) + ' and ' + self.weap_name(weap[1])
                else:
                    weap_name = self.weap_name(weap)
                output_list[weap_name] = avg
                        
            return output_list

    #############################
    #
    # Melee class attack selection functions
    
    def best_melee_fob(self, target, dist=0, prn=False, dmg_val=False):
        if not self.melee_weaps:
            return None
        
        monk_melee_weaps = []
        
        for weap in self.melee_weaps:
            if "Monk" in self.weap_group(weap):
                monk_melee_weaps.append(weap)
        
        if not monk_melee_weaps:
            return None
            
        return self.best_weap(target, dist, monk_melee_weaps, FRA=True, offhand=False, dmg_val=dmg_val, fob=True)

    #############################
    #
    # Ranged attack selection functions

    def best_ranged_weap(self, target, dist=0, FRA=True):
        if not self.ranged_weaps:
            return None
        else:
            return self.best_weap(target, dist, self.ranged_weaps, FRA)

###################################################################
#
# Value-setting functions

    def set_weapon(self, weap_num):
        if type(weap_num) is list:
            self.set_weapon(weap_num[0])
            self.set_off(weap_num[1])
            return
            
        if self.weap_hands(weap_num) == 1:
            self.slots["wield"][0] = weap_num
            offhand = self.slots["wield"][1]
            if offhand and self.weap_hands(offhand) == 2:
                self.slots["wield"][0] = None
        else:
            offhand = self.slots["wield"][1]
            if offhand and self.weap_hands(offhand) == 1:
                raise Exception("Cannot equip two-handed weapon: offhand occupied")
            else:
                self.slots["wield"][0] = weap_num
                self.slots["wield"][1] = weap_num

    def set_off(self, weap_num, hand=1):
        if self.weap_hands(weap_num) == 2:
            raise Exception("Cannot equip two-handed weapon to offhand")
        if hand >= self.hands:
            raise Exception("Cannot equip offhand weapon to hand {}: does not exist".format(hand))
        offhand = self.slots["wield"][hand]
        if offhand and self.weap_hands(offhand) == 2:
            raise Exception("Cannot equip offhand weapon: two-handed weapon equipped")
        self.slots["wield"][hand] = weap_num

    def set_armor(self, armor_num):
        self.slots["armor"] = armor_num

    def set_shield(self, shield_num, hand=1):
        if hand >= self.hands:
            raise Exception("Cannot equip shield to hand {}: does not exist".format(hand))
        elif self.shield_hands(shield_num) == 2 and hand > self.hands:
            raise Exception("Cannot equip two-handed shield to hand {}: hand {} does not exist".format(hand, hand+1))
        offhand = self.slots["wield"][hand]
        if offhand and self.item_type(offhand) == "weapon" and self.weap_hands(offhand) == 2:
            raise Exception("Cannot equip shield: two-handed weapon equipped")
        self.slots["wield"][hand] = shield_num
        if self.shield_hands(shield_num) == 2:
            self.slots["wield"][hand + 1] = shield_num
    
    def drop(self, slot):
        slot_loc = slot.split(',')
        if len(slot_loc) == 1:
            place = slot_loc[0]
            i = self.slots[place]
            if not self.default(i):
                gear = self.equip_list[i]
                self.slots[place] = None
                if gear.item == "weapon":
                    if "M" in gear.atk_type:
                        self.melee_weaps.remove(i)
                    elif "R" in gear.atk_type:
                        self.ranged_weaps.remove(i)
                self.equip_list[i] = None
                return gear
            else:
                return None
        elif len(slot_loc) == 2:
            place = slot_loc[0]
            num = int(slot_loc[1])
            i = self.slots[place][num]
            if not self.default(i):
                gear = self.equip_list[i]
                self.slots[place][num] = None
                if gear.hands == 2:
                    self.slots[place][num + 1] = None
                if gear.item == "weapon":
                    if "M" in gear.atk_type:
                        self.melee_weaps.remove(i)
                    elif "R" in gear.atk_type:
                        self.ranged_weaps.remove(i)
                self.equip_list[i] = None
                return gear
            else:
                return None

    def take_damage(self, dmg):

        self.damage = self.damage + dmg

        self.check_hp()

    def check_hp(self):
        if self.damage == self.get_hp():
            self.damage_con = "Disabled"
        if self.damage > self.get_hp():
            self.damage_con = "Dying"
            if self.has("Raging"):
                self.drop_rage()
        if self.damage > self.get_hp() + self.contot():
            self.damage_con = "Dead"
            if self.has("Raging"):
                self.drop_rage()

    def set_condition(self, condition, duration=14400):
        if condition not in self.conditions.keys():
            if condition == "Fatigued" and "Exhausted" in self.conditions.keys():
                self.conditions["Exhausted"] = max(self.conditions["Exhausted"],duration)
            elif condition == "Stunned":
                self.conditions["Stunned"] = duration
                for i in range(self.hands):
                    self.drop("wield,{}".format(i))
            else:
                self.conditions[condition] = duration
        elif condition == "Fatigued":
            self.conditions["Exhausted"] = max(self.conditions["Fatigued"],duration)

    def drop_condition(self, condition):
        if condition in self.conditions.keys():
            del self.conditions[condition]

    def add_sq(self, quality):
        if quality not in self.sq:
            self.sq.append(quality)

    def del_sq(self, quality):
        if quality in self.sq:
            self.sq.remove(quality)

    def add_sa(self, quality):
        if quality not in self.sa:
            self.sa.append(quality)

    def del_sa(self, quality):
        if quality in self.sa:
            self.sa.remove(quality)

    def add_da(self, quality):
        if quality not in self.da:
            self.da.append(quality)

    def del_da(self, quality):
        if quality in self.da:
            self.da.remove(quality)
    
    def add_vuln(self, elem):
        if elem not in self.vuln:
            self.vuln.append(elem)
    
    def del_vuln(self, elem):
        if elem in self.vuln:
            self.vuln.remove(elem)
    
    def add_res(self, elem, amt):
        if elem not in self.res:
            self.res[elem] = amt
    
    def del_res(self, elem):
        if elem in self.res:
            del self.res[elem]
    
    def add_imm(self, elem):
        if elem not in self.immune:
            self.immune.append(elem)
    
    def del_imm(self, elem):
        if elem in self.immune:
            self.immune.remove(elem)
    
    def cast(self, spell):
        SL = spell.lvl_parse()[self.charClass]
        spl_name = spell.name
        
        if spl_name in self.spell_list_mem[SL]:
            self.spell_list_mem[SL][spl_name][1] -= 1

###################################################################
#
# Generic class ability functions

    def evasion(self):
        return "evasion" in self.da or "improved evasion" in self.da

    def trap_sense_bon(self):
        if self.charClass != "Barbarian" and self.charClass != "Rogue":
            return 0
        else:
            return int(self.level / 3)

    def uncanny_dodge(self):
        return "uncanny dodge" in self.da or "improved uncanny dodge" in self.da

    def uncanny_dodge_imp(self):
        return "improved uncanny dodge" in self.da

###################################################################
#
# Barbarian class ability functions

    def barbarian_rage_rds(self):

        rds = 4

        rds += self.stat_bonus(self.contot())

        rds += (self.level - 1) * 2

        return rds

    def set_rage(self):
        if not self.has("Fatigued") and not self.has("Exhausted"):
            self.set_condition("Raging",self.barbarian_rage_rds())
            self.rage_dur = 0
            if "R" in self.weap_type():
                self.set_weapon(self.best_melee_weap(None))
            return True
        else:
            return False

    def drop_rage(self):
        self.drop_condition("Raging")
        if self.level < 17:
            self.set_condition("Fatigued",2 * self.rage_dur)
        self.check_hp()

    def rage_bon(self):
        if self.charClass != "Barbarian":
            return 0
        elif self.level < 11:
            return 4
        elif self.level < 20:
            return 6
        else:
            return 8

    def rage_bon_indom_will(self):
        if self.charClass != "Barbarian" or level < 14:
            return 0
        else:
            return 4

        # Note: conditional save bonuses not yet implemented

    def barbarian_dr(self):
        return max(int((self.level - 4) / 3), 0)

###################################################################
#
# Fighter class ability functions

    def fighter_bravery(self):
        if self.charClass != "Fighter":
            return 0
        return int((self.level + 2) / 4)

        # Note: conditional save bonuses not yet implemented

    def fighter_armor_training(self):
        if self.charClass != "Fighter":
            return 0
        return int((self.level + 1) / 4)

    def set_fighter_weap_train(self, groups):
        if self.charClass != "Fighter":
            raise Exception("Cannot set Fighter options for non-Fighter")
        if len(groups) != int((self.level - 1) / 4):
            raise Exception("Wrong number of groups set for Weapon Training")
        self.ftr_wt = groups

        train_text = []
        for group in groups:
            train_text.append("{} {:+d}".format(group.lower(),groups[::-1].index(group) + 1))
        self.add_sa("weapon training ({})".format(', '.join(train_text)))

    def fighter_wt_bon(self, groups):
        if self.charClass != "Fighter":
            return 0
        matching_groups = list(set(groups).intersection(self.ftr_wt))
        if not matching_groups:
            return 0
        wt = self.ftr_wt[::-1]
        wt_bon = map(lambda x:wt.index(x) + 1, matching_groups)
        return max(wt_bon)

    def set_fighter_weap_mast(self, weapon):
        if self.charClass != "Fighter":
            raise Exception("Cannot set Fighter options for non-Fighter")
        self.ftr_mast = weapon
        self.add_sa("weapon mastery ({})".format(weapon))

    def ftr_am(self):
        return self.charClass == "Fighter" and self.level >= 19 and (self.has_armor() or self.has_shield())

    def ftr_wm(self):
        return self.charClass == "Fighter" and self.level >= 20 and self.weap_basename() == self.ftr_mast

###################################################################
#
# Monk class ability functions

    def monk_ki_tot(self):
        if self.charClass != "Monk":
            raise Exception("Cannot set Monk options for non-Monk")
        if self.level >= 4:    
            self.ki_pool = int(self.level / 2) + self.stat_bonus(self.wistot())
        else:
            self.ki_pool = 0

###################################################################
#
# Ranger class ability functions

    def set_ranger_favored_enemy(self, types):
        if self.charClass != "Ranger":
            raise Exception("Cannot set Ranger options for non-Ranger")
        tot_bon_count = int(self.level * 4 / 5) + 2
        if sum([x[1] for x in types]) != tot_bon_count:
            raise Exception("Wrong bonus assignment for Favored Enemy")
        self.rgr_fe = types

        fe_text = []
        for type in types:
            if len(type) == 3:
                if type[0] == "Outsider":
                    text = "{} {} {:+d}".format(type[2].lower(), type[0].lower(), type[1])
                else:
                    text = "{} {:+d}".format(type[2].lower(),type[1])
            else:
                text = "{} {:+d}".format(type[0].lower(),type[1])
            fe_text.append(text)

        fe_text = sorted(fe_text)
        self.add_sa("favored enemy ({})".format(', '.join(fe_text)))

    def ranger_fe_types(self):
        return [x[0] for x in self.rgr_fe]

    def ranger_fe_bon(self, type, subtype=[]):
        match_types = [i for i, x in enumerate(self.rgr_fe) if x[0]==type]

        if type not in ["Humanoid","Outsider"]:
            if match_types:
                return self.rgr_fe[match_types[0]][1]
            else:
                return 0
        else:
            match_subtypes = [i for i, x in enumerate(self.rgr_fe) if x[0]==type and x[2] in subtype]

            if match_subtypes:
                return self.rgr_fe[match_subtypes[0]][1]
            else:
                return 0

###################################################################
#
# Statistic value functions

    def add_bon(self, bon_list, bon_type, bon_val):
        if not bon_type in bon_list:
            bon_list[bon_type] = bon_val
        else:
            if bon_type in ["dodge", "racial", "untyped","circumstance", "feat", "condition", "class", "weapon"]:
                bon_list[bon_type] = bon_list[bon_type] + bon_val
            else:
                bon_list[bon_type] = max(bon_list[bon_type],bon_val)

    #############################
    #
    # Base stat functions

    def strtot(self):
        if self.str == None:
            return -999

        stat_bon = dict()

        self.add_bon(stat_bon,"stat",self.str)

        if self.has("Exhausted"):
            self.add_bon(stat_bon,"untyped",-6)
        if self.has("Fatigued"):
            self.add_bon(stat_bon,"untyped",-2)
        if self.has("Raging"):
            self.add_bon(stat_bon,"morale",self.rage_bon())

        return sum(stat_bon.values())

    def dextot(self):
        if self.dex == None:
            return -999

        stat_bon = dict()

        self.add_bon(stat_bon,"stat",self.dex)

        if self.has("Exhausted"):
            self.add_bon(stat_bon,"untyped",-6)
        if self.has("Fatigued"):
            self.add_bon(stat_bon,"untyped",-2)

        return sum(stat_bon.values())

    def contot(self):
        if self.con == None:
            return -999

        stat_bon = dict()

        self.add_bon(stat_bon,"stat",self.con)

        if self.has("Raging"):
            self.add_bon(stat_bon,"morale",self.rage_bon())

        return sum(stat_bon.values())

    def inttot(self):
        if self.int == None:
            return -999

        stat_bon = dict()

        self.add_bon(stat_bon,"stat",self.int)

        return sum(stat_bon.values())

    def wistot(self):
        if self.wis == None:
            return -999

        stat_bon = dict()

        self.add_bon(stat_bon,"stat",self.wis)

        return sum(stat_bon.values())

    def chatot(self):
        if self.cha == None:
            return -999

        stat_bon = dict()

        self.add_bon(stat_bon,"stat",self.cha)

        return sum(stat_bon.values())
    
    def casttot(self):
        if self.cast_stat == None:
            return -999
        elif self.cast_stat == "i":
            return self.inttot()
        elif self.cast_stat == "w":
            return self.wistot()
        elif self.cast_stat == "h":
            return self.chatot()

    #############################
    #
    # AC functions

    def get_AC_bons(self, type=None, subtype=None, atk_type="M", public=False):

        AC_bon = dict()

        stat_bon = min(self.armor_max_dex(), self.stat_bonus(self.dextot()))

        if not self.has("Stunned"):
            self.add_bon(AC_bon,"Dex",stat_bon)

        #############################
        #
        # Equipment bonus

        self.add_bon(AC_bon,"armor",self.armor_armor_bon(public=public))

        self.add_bon(AC_bon,"shield",self.shield_shield_bon(public=public))

        #############################
        #
        # Class bonuses
        
        if self.charClass == "Monk":
            self.add_bon(AC_bon,"Wis",self.stat_bonus(self.wistot()))
            self.add_bon(AC_bon,"monk",int(self.level / 4))

        #############################
        #
        # Feat bonuses

        self.add_bon(AC_bon,"dodge",self.feat.dodge_bon(self))

        self.add_bon(AC_bon,"dodge",self.feat.favored_defense_bon(self, type, subtype))

        #############################
        #
        # Condition bonuses

        if self.has("Prone"):
            if "M" in atk_type:
                self.add_bon(AC_bon,"condition",-4)
            elif "R" in atk_type:
                self.add_bon(AC_bon,"condition",-4)
                
        if self.has("Raging"):
            self.add_bon(AC_bon,"rage",-2)
        
        if self.has("Stunned"):
            self.add_bon(AC_bon,"condition",-2)

        return AC_bon

    def get_AC(self, type=None, subtype=None, FF=False, touch=False, atk_type="M", public=False):

        temp_AC_bons = self.get_AC_bons(type=type, subtype=subtype, atk_type=atk_type, public=public)

        if self.has("Flat-footed") or FF:
            temp_AC_bons = self.get_FF_AC_bons(temp_AC_bons)
        if touch:
            temp_AC_bons = self.get_touch_AC_bons(temp_AC_bons)

        return 10 + sum(temp_AC_bons.values())

    def get_FF_AC_bons(self, temp_AC_bons):

        if not self.uncanny_dodge():
            temp_AC_bons.pop("Dex",None)
            temp_AC_bons.pop("dodge",None)

        return temp_AC_bons

    def get_touch_AC_bons(self, temp_AC_bons):

        temp_AC_bons.pop("armor",None)
        temp_AC_bons.pop("natural",None)
        temp_AC_bons.pop("shield",None)

        return temp_AC_bons

    #############################
    #
    # AoO functions

    def can_aoo(self):
    
        active_check = self.is_active()
        
        if not active_check[0] or active_check[1] == "Disabled":
            return False
        
        if self.has("Flat-footed") and not self.uncanny_dodge():
            return False
            
        if "R" in self.weap_type() and not self.snap_shot():
            return False
        
        return True

    def get_aoo_count(self):
        if self.feat.combat_reflexes(self):
            return self.stat_bonus(self.dextot())
        else:
            return 1

    #############################
    #
    # Attack roll functions

    def get_atk_bon(self, dist, FRA, type, subtype, weap=None, nofeat=False, offhand=False, fob=False, bon_calc=False, off=False, light=False):
        if weap == None:
            weap = self.slots["wield"][0]

        atk_bon = dict()
        
        if "Monk" not in self.weap_group(weap):
            fob = False                         # just to be safe
        
        if fob:                                 # flurry of blows BAB
            bab = [i-2 for i in range(self.level, 0, -5)]
            bab.insert(1,self.level-2)
            if self.level >= 8:
                bab.insert(3,self.level-7)
                if self.level >= 15:
                    bab.insert(5,self.level-12)
                    
        elif offhand:                           # offhand BAB
            bab = [self.bab[0]]
            if self.feat.two_weapon_fighting_imp(self):
                bab.append(self.bab[0]-5)
                if self.feat.two_weapon_fighting_greater(self):
                    bab.append(self.bab[0]-10)
        else:                                   # normal mainhand BAB
            bab = self.bab

        #############################
        #
        # Stat bonus

        if "M" in self.weap_type(weap):
            if self.feat.weapon_finesse(self) and self.feat.weapon_finesse_weap(self, weap):
                self.add_bon(atk_bon,"stat",self.stat_bonus(self.dextot()))
                if self.has_shield():
                    self.add_bon(atk_bon,"shield",self.shield_armor_check())
            else:
                self.add_bon(atk_bon,"stat",self.stat_bonus(self.strtot()))
            self.add_bon(atk_bon,"untyped",self.TWF_pen(weap, bon_calc=bon_calc, off=offhand, light=light))
        elif "R" in self.weap_type(weap):
            self.add_bon(atk_bon,"stat",self.stat_bonus(self.dextot()))
            self.add_bon(atk_bon,"untyped",self.range_pen(dist))

        #############################
        #
        # Class bonus
            

        #############################
        #
        # Feat bonuses, all attacks

        if not nofeat:

            if "M" in self.weap_type():
                self.add_bon(atk_bon,"feat",self.feat.power_attack_pen(self))
            elif "R" in self.weap_type():
                self.add_bon(atk_bon,"feat",self.feat.deadly_aim_pen(self))
                if FRA:
                    self.add_bon(atk_bon,"feat",self.feat.rapid_shot_pen(self))
            
        if self.feat.weapon_focus(self,weap):
            self.add_bon(atk_bon,"feat",1)

        atk_bon = self.get_attack_roll_mods(atk_bon, dist, FRA, type, subtype, weap, nofeat)

        atk_bon_tot = sum(atk_bon.values())

        atk_bon_list = list(map(lambda x: x + atk_bon_tot, bab))

        #############################
        #
        # Feat bonuses, single attacks

        if not nofeat:
            if "R" in self.weap_type():
                if FRA:
                    if self.feat.rapid_shot(self):
                        atk_bon_list.insert(0,atk_bon_list[0])
                else:
                    atk_bon_list[0] = atk_bon_list[0] + self.feat.bullseye_shot_bon(self,FRA)

        if FRA:
            return atk_bon_list
        else:
            return atk_bon_list[0:1]

    def CMB(self, dist=5, type=None, subtype=None, weap=None, nofeat=False, man=""):

        cmb = dict()

        if "maneuver training" in self.sq:
            self.add_bon(cmb,"BAB",self.level)
        else:
            self.add_bon(cmb,"BAB",self.bab[0])
        
        if self.feat.weapon_finesse(self) and self.feat.weapon_finesse_weap(self, weap) and man in ["Disarm","Sunder","Trip"]:
            self.add_bon(cmb,"stat",self.stat_bonus(self.dextot()))
            if self.has_shield():
                self.add_bon(cmb,"shield",self.shield_armor_check())
        else:
            self.add_bon(cmb,"stat",self.stat_bonus(self.strtot()))

        size_bon = 0

        if self.size == "Fine":
            size_bon = -8
        elif self.size == "Diminutive":
            size_bon = -4
        elif self.size == "Tiny":
            size_bon = -2
        elif self.size == "Small":
            size_bon = -1
        elif self.size == "Medium":
            size_bon = 0
        elif self.size == "Large":
            size_bon = 1
        elif self.size == "Huge":
            size_bon = 2
        elif self.size == "Gargantuan":
            size_bon = 4
        elif self.size == "Colossal":
            size_bon = 8

        self.add_bon(cmb,"size",size_bon)

        cmb = self.get_attack_roll_mods(cmb, dist, False, type, subtype, weap, nofeat)
        
        if man == "Disarm":
            self.add_bon(cmb,"feat",self.feat.improved_disarm_bon(self))
            if self.weap_name(weap) == "unarmed strike":
                self.add_bon(cmb,"untyped",-4)
            if self.weap_disarm():
                self.add_bon(cmb,"weapon",2)
        elif man == "Trip":
            self.add_bon(cmb,"feat",self.feat.improved_trip_bon(self))

        cmb_tot = sum(cmb.values())

        return cmb_tot

    def get_attack_roll_mods(self, atk_bon, dist, FRA, type, subtype, weap=None, nofeat=False):

        #############################
        #
        # Enchantment/masterwork bonus

        if self.weap_mwk(weap):
            if self.weap_bon(weap) == 0:
                self.add_bon(atk_bon,"enhancement",1)
            else:
               self.add_bon(atk_bon,"enhancement",self.weap_bon(weap))

        #############################
        #
        # Class bonuses, all attacks

        if self.charClass == "Fighter" and self.level >= 5:
            self.add_bon(atk_bon,"untyped",self.fighter_wt_bon(self.weap_group(weap)))

        if self.charClass == "Ranger":
            self.add_bon(atk_bon,"untyped",self.ranger_fe_bon(type, subtype))

        #############################
        #
        # Feat bonuses
        
        if not nofeat:

            if "M" in self.weap_type():
                pass
            elif "R" in self.weap_type():
                if dist < 30:
                    self.add_bon(atk_bon,"feat",self.feat.pbs_bon(self))

        #############################
        #
        # Condition bonuses
        
        if self.has("Prone"):
            
            if "M" in self.weap_type():
                self.add_bon(atk_bon,"condition",-4)

        return atk_bon

    #############################
    #
    # CL functions
    
    def CL(self):
        
        CL = dict()
        
        if self.charClass in ["Bard","Cleric","Druid","Sorcerer","Wizard"]:
            self.add_bon(CL,"base",self.level)
        elif self.charClass in ["Paladin","Ranger"] and self.level >= 4:
            self.add_bon(CL,"base",self.level - 3)
        else:
            return 0
        
        CL_tot = sum(CL.values())
        
        return CL_tot
        

    #############################
    #
    # CMD functions

    def CMD(self, type=None, subtype=None, FF=False, man=None):
    
        cmd = dict()

        if "maneuver training" in self.sq:
            self.add_bon(cmd,"BAB",self.level)
        else:
            self.add_bon(cmd,"BAB",self.bab[0])

        self.add_bon(cmd,"Str",self.stat_bonus(self.strtot()))

        self.add_bon(cmd,"Dex",self.stat_bonus(self.dextot()))

        #############################
        #
        # Class bonuses
        
        if self.charClass == "Monk":
            self.add_bon(cmd,"Wis",self.stat_bonus(self.wistot()))
            self.add_bon(cmd,"monk",int(self.level / 4))

        #############################
        #
        # Condition bonuses
        
        if self.has("Stunned"):
            self.add_bon(cmd,"condition",-4)

        size_bon = 0

        if self.size == "Fine":
            size_bon = -8
        elif self.size == "Diminutive":
            size_bon = -4
        elif self.size == "Tiny":
            size_bon = -2
        elif self.size == "Small":
            size_bon = -1
        elif self.size == "Medium":
            size_bon = 0
        elif self.size == "Large":
            size_bon = 1
        elif self.size == "Huge":
            size_bon = 2
        elif self.size == "Gargantuan":
            size_bon = 4
        elif self.size == "Colossal":
            size_bon = 8

        self.add_bon(cmd,"size",size_bon)
        
        if man == "Disarm":
            self.add_bon(cmd,"feat",self.feat.improved_disarm_bon(self))
        elif man == "Trip":
            self.add_bon(cmd,"feat",self.feat.improved_trip_bon(self))
            if self.legs > 2:
                self.add_bon(cmd,"untyped",(self.legs - 2) * 2)

        AC_bons = self.get_AC_bons(type, subtype)

        if self.has("Flat-footed") or FF:
            AC_bons = self.get_FF_AC_bons(AC_bons)

        for key in AC_bons.keys():
            if key in ["circumstance", "deflection", "dodge", "insight", "luck", "morale", "profane", "sacred"]:
                self.add_bon(cmd,key,AC_bons[key])

        cmd_tot = 10 + sum(cmd.values())

        return cmd_tot

    #############################
    #
    # Concentration functions

    def concentration(self):

        conc = dict()
        
        self.add_bon(conc,"CL",self.CL())
        self.add_bon(conc,"Stat",self.stat_bonus(self.casttot()))
        
        conc_tot = sum(conc.values())
        
        return conc_tot

    #############################
    #
    # Condition functions

    def has(self, condition):
        return condition in self.conditions.keys() and self.conditions[condition] != 0

    def round_pass(self):
        if not self.model:
            self.ai.update_model()
        expire_conditions = []
        
        cond = dict(self.conditions)
        for condition in cond.keys():
            if condition == "Raging":
                self.rage_dur += 1
            if self.conditions[condition] > 0:
                self.conditions[condition] -= 1
            if self.conditions[condition] == 0:
                expire_conditions.append(condition)
                if condition == "Raging":
                    self.drop_rage()
                else:
                    self.drop_condition(condition)
                    
        for satk in self.sa_list:
            satk.round()
        
        return [expire_conditions]
    
    def is_active(self):
        self.check_hp()
        
        if self.damage_con not in ["Normal","Disabled"]:
            return [False,self.damage_con]
        else:
            return [True,self.damage_con]
    
    def can_act(self):
    
        active_check = self.is_active()
        
        if not active_check[0]:
            return active_check
        
        disable_list = ["Stunned","Paralyzed","Petrified","Unconscious"]
        
        for condition in disable_list:
            if self.has(condition):
                return [False,condition]
        else:
            return [True,""]
        

    #############################
    #
    # Damage bonus functions

    def get_base_dmg_bon(self, dist, type, subtype, weap=None, offhand=False, nofeat=False):
        
        dmg_bon = dict()

        #############################
        #
        # Enchantment/masterwork bonus

        self.add_bon(dmg_bon,"enhancement",self.weap_bon(weap))

        #############################
        #
        # Stat bonus

        str_bon = self.stat_bonus(self.strtot())
        dex_bon = self.stat_bonus(self.dextot())

        if self.has_offhand() and not offhand:
            if str_bon > 0:
                self.add_bon(dmg_bon,"Str",int((str_bon / 2)))
            else:
                self.add_bon(dmg_bon,"Str",str_bon)
        elif self.weap_hands(weap) == 2 and "R" not in self.weap_type(weap):
            if str_bon > 0:
                self.add_bon(dmg_bon,"Str",int((str_bon * 3 / 2)))
            else:
                self.add_bon(dmg_bon,"Str",str_bon)
        elif self.ambi and "R" in self.weap_type(weap):
            self.add_bon(dmg_bon,"Dex",dex_bon)
        elif "M" in self.weap_type(weap) or "T" in self.weap_type(weap):
            self.add_bon(dmg_bon,"Str",str_bon)

        #############################
        #
        # Class bonuses

        if self.charClass == "Fighter" and self.level >= 5:
            self.add_bon(dmg_bon,"class",self.fighter_wt_bon(self.weap_group()))

        if self.charClass == "Ranger":
            dmg_bon = dmg_bon + self.ranger_fe_bon(type, subtype)
            self.add_bon(dmg_bon,"class",self.ranger_fe_bon(type, subtype))

        #############################
        #
        # Feat bonuses

        if not nofeat:
            self.add_bon(dmg_bon,"feat",self.feat.arcane_strike_bon(self))

            if "M" in self.weap_type():
                self.add_bon(dmg_bon,"feat",self.feat.power_attack_bon(self))
            elif "R" in self.weap_type():
                self.add_bon(dmg_bon,"feat",self.feat.deadly_aim_bon(self))
                if dist <= 30:
                    self.add_bon(dmg_bon,"feat",self.feat.pbs_bon(self))

        return sum(dmg_bon.values())

    #############################
    #
    # Defensive ability functions
    
    def is_weak(self,atktype):
    
        return atktype in self.vuln
    
    def res_amt(self,atktype):
    
        if atktype in self.res:
            return self.res[atktype]
    
        return 0
    
    def is_immune(self,atktype):
    
        return atktype in self.immune

    #############################
    #
    # DR functions

    def get_dr(self):

        if self.ftr_am():
            return [5,["-"],""]

        if self.charClass == "Barbarian" and self.level >= 7:
            return [self.barbarian_dr(),["-"],""]
        
        if self.charClass == "Monk" and self.level >= 20:
            return [10,["chaotic"],""]

        return []

    #############################
    #
    # HP functions

    def get_hp_bon(self):

        hp_bon = 0

        #############################
        #
        # Stat bonus

        if self.type == "Undead":
            hp_stat_bon = self.stat_bonus(self.chatot()) * self.HD
        elif self.type == "Construct":
            if self.size == "Small":
                hp_stat_bon = 10
            elif self.size == "Medium":
                hp_stat_bon = 20
            elif self.size == "Large":
                hp_stat_bon = 30
            elif self.size == "Huge":
                hp_stat_bon = 40
            elif self.size == "Gargantuan":
                hp_stat_bon = 60
            elif self.size == "Colossal":
                hp_stat_bon = 80
            else:
                hp_stat_bon = 0
        else:
            hp_stat_bon = self.stat_bonus(self.contot()) * self.HD

        hp_bon += hp_stat_bon

        #############################
        #
        # Feat bonus

        hp_bon += self.feat.toughness_bon(self)

        #############################
        #
        # FC bonus

        hp_bon += self.fc.count("h")

        return hp_bon

    def get_hp(self):
        return max(self.hp + self.get_hp_bon(),self.HD)
    
    def get_hp_perc(self):
        maxhp = self.get_hp()
        curhp = maxhp - self.damage
        return max(curhp / maxhp,0)
    
    def get_hp_temp_perc(self):
        maxhp = self.get_hp()
        curhp = maxhp - self.damage - self.temp_dmg
        return max(curhp / maxhp,0)
    
    def temp_dmg_add(self,dmg):
        self.temp_dmg += dmg
    
    def temp_dmg_reset(self):
        self.temp_dmg = 0

    #############################
    #
    # Initiative functions

    def get_init(self):
        init = self.stat_bonus(self.dextot())

        init += self.feat.improved_initiative_bon(self)

        return init

    #############################
    #
    # Language functions
    
    def add_lang_spec(self, lang):
        if lang not in self.lang_spec:
            self.lang_spec.append(lang)
    
    def del_lang_spec(self, lang):
        if lang in self.lang_spec:
            self.lang_spec.remove(lang)

    #############################
    #
    # Movement functions

    def get_move(self):
        
        if self.has("Prone"):
            return 5

        move = self.move

        if "fast movement" in self.sq:
            if self.charClass == "Barbarian" and self.armor_type() != "Heavy":
                move += 10
            elif self.charClass == "Monk" and self.armor_name() == "":
                move += int(self.level / 3) * 10

        if self.has("Exhausted"):
            move /= 2

        return move
    
    def get_move_acts(self):
    
        if self.damage_con == "Disabled":
            return 1
        
        return 2

    #############################
    #
    # Saving throw functions

    def get_fort(self):

        speed = self.fort

        if speed == "Fast":
            save = int(self.HD / 2) + 2
        else:
            save = int(self.HD / 3)

        save_bon = dict()

        self.add_bon(save_bon,"base",save)
        self.add_bon(save_bon,"stat",self.stat_bonus(self.contot()))
        self.add_bon(save_bon,"untyped",self.feat.great_fortitude_bon(self))

        return sum(save_bon.values())

    def get_ref(self):

        speed = self.ref

        if speed == "Fast":
            save = int(self.HD / 2) + 2
        else:
            save = int(self.HD / 3)

        save_bon = dict()

        self.add_bon(save_bon,"base",save)
        self.add_bon(save_bon,"stat",self.stat_bonus(self.dextot()))
        self.add_bon(save_bon,"untyped",self.feat.lightning_reflexes_bon(self))

        return sum(save_bon.values())

    def get_will(self):

        speed = self.will

        if speed == "Fast":
            save = int(self.HD / 2) + 2
        else:
            save = int(self.HD / 3)

        save_bon = dict()

        self.add_bon(save_bon,"base",save)
        self.add_bon(save_bon,"stat",self.stat_bonus(self.wistot()))
        self.add_bon(save_bon,"untyped",self.feat.iron_will_bon(self))
        if self.has("Raging"):
            self.add_bon(save_bon,"morale",int(self.rage_bon() / 2))

        return sum(save_bon.values())

    #############################
    #
    # Spell resistance functions
    
    def get_sr(self):
    
        sr = 0
        
        if self.charClass == "Monk" and self.level >= 13:
            sr = max(sr, (self.level + 10))
        
        return sr

    #############################
    #
    # Threat range functions

    def threat_range(self, val=None):
        if val == None:
            val = self.slots["wield"][0]
        if val == None:
            return [[5, self.reach]]
            
        tr = []
        
        if type(val) is int:
            val = [val]
            
        for i in val:
            tr_temp = [0,0]
            
            if "M" in self.weap_type(i):
                tr_temp = [5, self.reach]
                if self.weap_reach(i):
                    tr_temp = [self.reach + 5, self.reach * 2]
            else:
                if self.feat.snap_shot(self):
                    tr_temp = [5,5]
                if self.feat.snap_shot_imp(self):
                    tr_temp = [5,15]
            tr.append(tr_temp[:])
        
        return tr


###################################################################
#
# Mechanics functions

    def check_attack(self, targ_AC, dist, FRA, type, subtype, offhand=False, fob=False):
        
        weapList = self.weap_list()
        atk_bon = [[] for i in range(len(weapList))]
        
        for i in range(len(atk_bon)):
            offhand = (weapList[i][0] != self.slots["wield"][0])
                
            atk_bon[i] = self.get_atk_bon(dist, FRA, type, subtype, fob=fob, weap=weapList[i][0], offhand=offhand)

        #############################
        #
        # Set up hit_miss array
        #
        # Each occupied weapon slot (by self.weap_list) assigned to tens place, ones place
        # indicating specific iterative attack bonus
        #
        # e.g., character with two weapons and 4 iterative attacks with main weapon would
        # have bonus totals in array values 00, 01, 02, 03, and 10
        #
        # If a character for some reason has >10 attacks with a single weapon, assign
        # it as two or more weapons (but why would this ever happen)
        
        hit_miss = [None for i in range((len(atk_bon))*10)]
        
        for i in range(len(atk_bon)):
            weapon = weapList[i][0]
            
            for j in range(len(atk_bon[i])):

                hmIx = i*10+j
                
                hit_miss[hmIx] = 0

                #############################
                #
                # Roll attack(s)

                atk_roll = self.random.randint(1,20)

                if atk_roll == 20:
                    hit_miss[hmIx] = 1
                elif (atk_roll + atk_bon[i][j]) >= targ_AC:
                    hit_miss[hmIx] = 1

                #############################
                #
                # Check for critical

                crit_rng = self.weap_crit_range(weapon)

                if atk_roll >= crit_rng and hit_miss[hmIx] == 1:
                    conf_roll = self.random.randint(1,20)

                    conf_bon = atk_bon[i][j]

                    conf_bon = conf_bon + self.feat.critical_focus_bon(self)

                    if conf_roll == 20 or (conf_roll + conf_bon) >= targ_AC or self.ftr_wm():
                        hit_miss[hmIx] = 2

        return hit_miss
    
    def check_CMB(self, targ_CMD, dist=5, type=None, subtype=None, man=""):
    
        CMB = self.CMB(dist=dist, type=type, subtype=subtype, man=man)
        
        CMB_roll = self.random.randint(1,20)
        
        result = (CMB_roll + CMB) - targ_CMD
        
        if CMB_roll == 20:
            return [True, result]
        elif CMB_roll == 1:
            return [False, result]
        else:    
            return [result >= 0, result]
    
    def check_save(self, stype, DC):
    
        if self.damage_con not in ["Normal","Disabled"]:
            return [False,"No save"]
        
        if stype == "F":
            save_bon = self.get_fort()
        elif stype == "R":
            save_bon = self.get_ref()
        elif stype == "W":
            save_bon = self.get_will()
        
        save_roll = self.random.randint(1,20) + save_bon
        
        save_pass = (save_roll >= DC)   #done this way rather than direct return to better support later expansion
        
        return [save_pass,save_roll]
    
    def check_conc(self, DC):
    
        conc_roll = self.random.randint(1,20) + self.concentration()
        
        conc_pass = (conc_roll >= DC)
        
        return [conc_pass,conc_roll]

    def roll_dmg(self, dist, crit=False, type=None, subtype=None, weap=None):
        
        if weap == None:
            weap = self.curr_weap()
        
        offhand = (weap != self.slots["wield"][0])

        #############################
        #
        # Crit multiplier

        if crit == True:
            roll_mult = self.weap_crit_mult(weap)
        else:
            roll_mult = 1

        dmg_bon = self.get_base_dmg_bon(dist, type, subtype, weap=weap, offhand=offhand)

        #############################
        #
        # Damage roll

        dmg = 0
        for j in range(roll_mult):
            for i in range(self.weap_dmg(weap)[0]):
                dmg = dmg + self.random.randint(1,self.weap_dmg(weap)[1])
            dmg = dmg + dmg_bon

        if dmg < 0:
            dmg = 0

        return dmg

    def roll_hp_tot(self):
        hp = 0

        hit_roll = self.HD

        if self.level > 0:
            hit_roll = hit_roll - 1
            hp = self.hit_die

        for i in range(hit_roll):
            hp = hp + self.random.randint(1,self.hit_die)

        self.hp = hp

    def weap_swap(self):
        if self.feat.quick_draw(self):
            return "free"
        else:
            return "move"

    def attack(self, targ_AC, dist=5, FRA=True, type=None, subtype=None, fob=False):

        dmg = 0
        hit_miss = self.check_attack(targ_AC, dist, FRA, type, subtype, fob=fob)
        dmg_vals = [0 for i in hit_miss]
        dmg_list_out = [None for i in hit_miss]

        weap_list=self.weap_list()
        for atk_count,atk_result in enumerate(hit_miss):
            if atk_result == None:
                continue
            weap = weap_list[atk_count//10][0]
            if atk_result == 0:
                dmg_vals[atk_count] = 0
                dmg_list_out[atk_count] = "miss"
            elif atk_result == 1:
                dmg_vals[atk_count] = self.roll_dmg(dist, type=type, subtype=subtype)

                if self.feat.manyshot(self) and "R" in self.weap_type(weap) and atk_count == 0:

                    dmg_vals[atk_count] = dmg_vals[atk_count] + self.roll_dmg(dist, type=type, subtype=subtype, weap=weap)

                dmg_list_out[atk_count] = str(dmg_vals[atk_count])
            elif atk_result == 2:
                dmg_vals[atk_count] = self.roll_dmg(dist, crit=True, type=type, subtype=subtype)

                if self.feat.manyshot(self) and "R" in self.weap_type(weap) and atk_count == 0:

                    dmg_vals[atk_count] = dmg_vals[atk_count] + self.roll_dmg(dist, type=type, subtype=subtype, weap=weap)

                dmg_list_out[atk_count] = "*" + str(dmg_vals[atk_count])
        return (sum(dmg_vals),dmg_list_out)

###################################################################
#
# Output functions

    # ordinal: outputs the ordinal version of an integer input
    
    def ordinal(self, num):    
        suffixes = {1: 'st', 2: 'nd', 3: 'rd'}
        if 10 <= num % 100 <= 20:
            suffix = 'th'
        else:
            suffix = suffixes.get(num % 10, 'th')
            
        return str(num) + suffix
    
    # base_presented_stats: the statistics visible to an outside party; used for AI mental models
    #(self, name, side, AC, move, loc, hp, tilesize, str, dex, con, int, wis, cha, feat_list, type, subtype, size, reach, fort, ref, will, hands, legs)
    
    def base_presented_stats(self,side):
    
        kwargstats = dict()
        
        kwargstats["name"] = "{} ({})".format(self.race,self.name)
        kwargstats["orig"] = self
        kwargstats["id"] = self.id
        
        kwargstats["type"] = self.type
        kwargstats["race"] = self.race
        kwargstats["size"] = self.size
        kwargstats["reach"] = self.reach
        kwargstats["hands"] = self.hands
        kwargstats["legs"] = self.legs
        
        kwargstats["str"] = self.strtot()
        kwargstats["dex"] = self.dextot()
        kwargstats["con"] = self.contot()
        
        kwargstats["loc"] = self.loc
        kwargstats["tilesize"] = self.tilesize
        kwargstats["side"] = self.side
    
        return kwargstats

    # print_dmg: prints weapon damage for given weapon in standard format, with all current feats and buffs
    #            pass nofeat=True to not include feat bonuses

    def print_dmg(self, dist, type, subtype, weap=None, nofeat=False):

        if weap==None:
            weap = self.slots["wield"][0]

        out = "{}d{}".format(self.weap_dmg(weap)[0],self.weap_dmg(weap)[1])

        dmg_bon = self.get_base_dmg_bon(dist, type, subtype, weap, nofeat)

        if dmg_bon != 0:
            out = out + "{:+d}".format(dmg_bon)

        return out
    
    # print_AC_bons: prints all current AC bonuses in alphabetical order

    def print_AC_bons(self, type=None, subtype=None):

        AC_bons = self.get_AC_bons(type, subtype)

        AC_keys = sorted(AC_bons.keys(), key=lambda x:x.lower())

        AC_out = ""

        for AC_type in AC_keys:
            if AC_bons[AC_type] != 0:
                AC_out = AC_out + "{:+d} {}, ".format(AC_bons[AC_type],AC_type)

        return AC_out[:-2]
    
    # print_AC_line: prints AC line in standard format, including base, touch, FF, and all current bonuses

    def print_AC_line(self, type=None, subtype=None):

        return "AC {}, touch {}, flat-footed {} ({})".format(self.get_AC(), self.get_AC(touch=True), self.get_AC(FF=True), self.print_AC_bons())
    
    # print_all_atks: prints atk line for all current weapons
    
    def print_all_atks(self, dist=0, FRA=True, type=None, subtype=None, nofeat=False):
        weap_list = self.weap_list()
        output = ["" for i in range(len(weap_list))]
        
        for i,weap in enumerate(weap_list):
            output[i] = self.print_atk_line(dist, FRA, type, subtype, weap[0], nofeat)
        
        return '; '.join(output)
    
    # print_atk_dmg: takes damage array as returned in 1 index of attack, formats into human-readable format
    
    def print_atk_dmg(self, dmg):
        weap_list = self.weap_list()
        output = ["" for i in range(len(weap_list))]
        
        for i,weap in enumerate(weap_list):
            if dmg[i*10] == None:
                continue
            output[i] += self.weap_name(weap[0]) + ": "
            output[i] += dmg[i*10]
            
            j=1
            while dmg[i*10+j] != None and j < 10:
                output[i] += ", " + dmg[i*10+j]
                j += 1
        
        while output.count("") > 0:
            output.remove("")
        
        return ('; '.join(output))
        
    
    # print_atk_line: prints attack line for a given weapon in standard format, with all current feats and buffs
    #                 pass nofeat=True to not include feat bonuses

    def print_atk_line(self, dist=0, FRA=True, type=None, subtype=None, weap=None, nofeat=False, fob=False):

        if weap == None:
            weap = self.slots["wield"][0]

        atk_out = "{} ".format(self.weap_name(weap))
        
        if fob:
            atk_out += "flurry of blows "

        atk_bon = self.get_atk_bon(dist, FRA, type, subtype, weap, nofeat, fob=fob)

        if len(atk_bon) == 1:
            temp = "{:+d}".format(atk_bon[0])
        else:
            temp = "/".join(map(lambda x:"{:+d}".format(x), atk_bon))

        atk_out += temp + " (" + self.print_dmg(dist,type,subtype,weap,nofeat)

        crit_rng = self.weap_crit_range(weap)

        if crit_rng != 20 or self.weap_crit_mult(weap) != 2:
            atk_out += "/"
            if crit_rng == 20:
                temp = "20"
            else:
                temp = "{}-20".format(crit_rng)

            atk_out += temp

            if self.weap_crit_mult(weap) != 2:
                atk_out += "/x" + str(self.weap_crit_mult(weap))

        atk_out += ")"

        return atk_out
    
    # print_fob: prints flurry atk line for current weapon
    
    def print_fob(self, dist=0, type=None, subtype=None, nofeat=False):
        weap_list = self.weap_list()
        output = ["" for i in range(len(weap_list))]
        
        for i,weap in enumerate(weap_list):
            output[i] = self.print_atk_line(dist, FRA, type, subtype, weap[0], nofeat, fob=True)
        
        return '; '.join(output)

    # print_HD: prints hit dice of character in standard format
    
    def print_HD(self):
        out = "{}d{}".format(self.HD,self.hit_die)

        hp_bon = self.get_hp_bon()

        if hp_bon != 0:
            out += "{:+d}".format(hp_bon)

        return out
    
    # print_hp: prints (cur)/(max) hp

    def print_hp(self):
        return "{}/{}".format(self.get_hp() - self.damage,self.get_hp())

    # print_save_line: prints current saving throw bonuses
    
    def print_save_line(self):
        return "Fort {:+d}, Ref {:+d}, Will {:+d}".format(self.get_fort(),self.get_ref(),self.get_will())
    
    def print_spell_line(self):
        
        spell_line = [[] for i in range(0,self.max_spell_lvl+1)]
        
        for i in range(self.max_spell_lvl,-1,-1):
            if i != 0:
                spell_line[i] = self.ordinal(i) + " - "
            else:
                spell_line[i] = "0 - "
                
            spell_text = []
            
            for spell_name in self.spell_list_mem[i].keys():
                spell = self.spell_list_mem[i][spell_name][0]
                spell_count = self.spell_list_mem[i][spell_name][1]
                
                spell_desc = spell_name
                
                if spell_count > 1:
                    spell_desc += " x{}".format(spell_count)
                
                if spell.has_save():
                    spell_desc += " (DC {})".format(10 + i + self.stat_bonus(self.casttot()))
                
                spell_text.append(spell_desc)
            
            spell_line[i] += ", ".join(sorted(spell_text))
        
        return spell_line

###################################################################

class Character(Foundation):
    """NPC stats and data"""

    def __init__(self, name=None, side=1, AC=10, move=None, loc=[0,0], tilesize=[1,1], level=1, charClass="Fighter", hp=1, str=10, dex=10, con=10, int=10, wis=10, cha=10, feat_list=[], ambi=False, type="Humanoid", subtype=["human"], size="Medium", reach=5, fort=None, ref=None, will=None, race="Human", hands=2, legs=2, fc=[]):
        if fc == []:
            fc = ["s" for i in range(level)]

        self.race = race
        self.level = level
        self.HD = level
        self.charClass = charClass
        self.ambi = ambi
        self.fc = fc
        
        if move == None:
            move = 30

        save_array = [fort,ref,will]
        save_array = self.set_saves(save_array)

        Foundation.__init__(self, name, side, AC, move, loc, hp, tilesize, str, dex, con, int, wis, cha, feat_list, type, subtype, size, reach, save_array[0], save_array[1], save_array[2], hands, legs)

        self.set_bab()
        self.set_spellcast_stats()
        self.set_hit_die()

        if hp == 0:
            self.roll_hp_tot()

        self.equip_unarmed()

        self.set_class_abilities()
        self.set_feat_abilities()
        
        self.model = False

    def equip_unarmed(self):

        self.unarmed = self.equip.Weapon(name="unarmed strike", group=["Monk","Natural"], atk_damage=[1,3])
        if self.charClass == "Monk":
            if self.level < 4:
                self.unarmed.atk_damage = [1,6]
            elif self.level < 8:
                self.unarmed.atk_damage = [1,8]
            elif self.level < 12:
                self.unarmed.atk_damage = [1,10]
            elif self.level < 16:
                self.unarmed.atk_damage = [2,6]
            elif self.level < 20:
                self.unarmed.atk_damage = [2,8]
            else:
                self.unarmed.atk_damage = [2,10]
        self.unarmed.default = True

        self.add_weapon(self.unarmed, active=True)

    def set_bab(self):

        if self.charClass in ["Barbarian", "Fighter", "Paladin", "Ranger"]:
            self.bab = range(self.level, 0, -5)
        elif self.charClass in ["Bard", "Cleric", "Druid", "Monk", "Rogue"]:
            self.bab = range(int(self.level * 3 / 4), 0, -5)
            if not self.bab:
                self.bab = [int(self.level * 3 / 4)]
        else:
            self.bab = range(int(self.level / 2), 0, -5)
            if not self.bab:
                self.bab = [int(self.level / 2)]

    def set_spellcast_stats(self):

        if self.charClass in ["Bard", "Sorcerer"]:
            self.arcane = True
            self.cast_stat = "h"
        
        if self.charClass in ["Wizard"]:
            self.arcane = True
            self.cast_stat = "i"

        if self.charClass in ["Cleric", "Druid"]:
            self.divine = True
            self.cast_stat = "w"

        if self.charClass in ["Paladin"] and self.level >= 4:
            self.divine = True
            self.cast_stat = "h"

        if self.charClass in ["Ranger"] and self.level >= 4:
            self.divine = True
            self.cast_stat = "w"

    def set_hit_die(self):

        if self.charClass in ["Barbarian"]:
            self.hit_die = 12
        elif self.charClass in ["Fighter", "Paladin", "Ranger"]:
            self.hit_die = 10
        elif self.charClass in ["Bard", "Cleric", "Druid", "Monk", "Rogue"]:
            self.hit_die = 8
        else:
            self.hit_die = 6

    def set_saves(self, save_array):
        fort, ref, will = save_array

        if not fort:
            if self.charClass in ["Barbarian", "Cleric", "Druid", "Fighter", "Monk", "Paladin", "Ranger"]:
                fort = "Fast"
            else:
                fort = "Slow"

        if not ref:
            if self.charClass in ["Bard", "Monk", "Ranger", "Rogue"]:
                ref = "Fast"
            else:
                ref = "Slow"

        if not will:
            if self.charClass in ["Bard", "Cleric", "Druid", "Monk", "Paladin", "Sorcerer", "Wizard"]:
                will = "Fast"
            else:
                will = "Slow"

        return [fort, ref, will]

    def set_class_abilities(self):
        if self.charClass == "Barbarian":
            self.add_sq("fast movement")
            if self.level < 11:
                self.add_sa("rage ({} rounds/day)".format(self.barbarian_rage_rds()))
            elif self.level < 20:
                self.add_sa("greater rage ({} rounds/day)".format(self.barbarian_rage_rds()))
            else:
                self.add_sa("mighty rage ({} rounds/day)".format(self.barbarian_rage_rds()))
            if self.level >= 2:
                if "uncanny dodge" in self.da:
                    self.del_da("uncanny dodge")
                    self.add_da("improved uncanny dodge")
                else:
                    self.add_da("uncanny dodge")
            if self.level >= 3:
                self.add_da("trap sense {:+d}".format(self.trap_sense_bon()))
            if self.level >= 5:
                self.del_da("uncanny dodge")
                self.add_da("improved uncanny dodge")

            if self.level >= 14:
                self.add_da("indomitable will")
            if self.level >= 17:
                self.add_sq("tireless rage")

        elif self.charClass == "Fighter":
            if self.level >= 2:
                self.add_da("bravery {:+d}".format(self.fighter_bravery()))
            if self.level >= 3:
                self.add_sq("armor training {}".format(self.fighter_armor_training()))
            if self.level >= 19:
                self.add_sq("armor mastery")
        
        elif self.charClass == "Monk":
            if "Improved Unarmed Strike" not in self.feat_list:
                self.feat_list.append("Improved Unarmed Strike")
            if "Stunning Fist" not in self.feat_list:
                self.feat_list.append("Stunning Fist")
            self.add_sa("flurry of blows")
            if self.level >= 2:
                if "evasion" in self.da:
                    self.del_da("evasion")
                    self.add_da("improved evasion")
                else:
                    self.add_da("evasion")
            if self.level >= 3:
                self.add_sq("fast movement")
            if self.level >= 4:
                self.add_sq("maneuver training")
                self.monk_ki_tot()
                self.ki_types.append("magic")
            if self.level >= 5:
                self.add_sq("high jump")
                self.add_sq("purity of body")
                self.add_imm("disease")
            if self.level >= 7:
                self.ki_types.append("cold iron")
                self.ki_types.append("silver")
                self.add_sq("wholeness of body")
            if self.level >= 9:
                self.del_da("evasion")
                self.add_da("improved evasion")
            if self.level >= 10:
                self.ki_types.append("lawful")
            if self.level >= 11:
                self.add_sq("diamond body")
                self.add_imm("poison")
            if self.level >= 12:
                self.add_sq("abundant step")
            if self.level >= 13:
                self.add_sq("diamond soul")
            if self.level >= 15:
                self.add_sa("quivering palm (1/day, DC {})".format(10 + int(self.level / 2) + self.stat_bonus(self.wistot())))
            if self.level >= 16:
                self.ki_types.append("adamantine")
            if self.level >= 17:
                self.add_sq("timeless body")
                self.add_lang_spec("tongue of the sun and moon")
            if self.level >= 19:
                self.add_sq("empty body")
            if self.level >= 20:
                self.add_sq("perfect self")
                self.type = "Outsider"
        
        elif self.charClass == "Wizard":
            if "Scribe Scroll" not in self.feat_list:
                self.feat_list.append("Scribe Scroll")

            if self.level == 1:
                self.spell_mem_max[0] = 3
            else:
                self.spell_mem_max[0] = 4
            
            cast_bon = self.stat_bonus(self.casttot())

            for i in range(1,10):
                start_level = (2*i) - 1
                if self.level < start_level:
                    continue
                elif self.level == start_level:
                    self.spell_mem_max[i] = 1
                elif self.level <= start_level + 2:
                    self.spell_mem_max[i] = 2
                elif self.level <= start_level + 5:
                    self.spell_mem_max[i] = 3
                else:
                    self.spell_mem_max[i] = 4
                
                if cast_bon < i:
                    pass
                else:
                    self.spell_mem_max[i] += ((cast_bon - i) // 4 + 1)
                
                self.max_spell_lvl = i
    
    def set_feat_abilities(self):
        if self.feat.stunning_fist(self):
            self.add_sa("stunning fist ({}/day, DC {})".format(self.level if self.charClass == "Monk" else int(self.level / 4), 10 + int(self.level / 2) + self.stat_bonus(self.wistot())))
            stun_fist = self.satk.stunning_fist.copy()
            if self.charClass == "Monk":
                uses_day = self.level
            else:
                uses_day = self.level // 4
            stun_fist.set_uses(uses_day,"day")
            self.sa_list.append(stun_fist)

    def update(self):

        self.set_bab()
        self.set_spellcast_stats()
        if self.charClass == "Monk":
            self.monk_ki_tot()
            self.monk_ki_check()
    
    def save_state(self):
    
        self.freeze_equip()
        self.freeze_spells()
        self.freeze_conditions()
    
    def freeze_equip(self):
        self.start_equip_list = copy.deepcopy(self.equip_list)
        self.start_melee_weaps = copy.deepcopy(self.melee_weaps)
        self.start_ranged_weaps = copy.deepcopy(self.ranged_weaps)
        self.start_slots = copy.deepcopy(self.slots)
    
    def freeze_spells(self):
    
        self.start_spell_list_mem = copy.deepcopy(self.spell_list_mem)
    
    def freeze_conditions(self):
    
        self.start_conditions = copy.deepcopy(self.conditions)

    def reset(self):

        self.damage = 0
        self.damage_con = "Normal"
        del self.conditions
        self.conditions = copy.deepcopy(self.conditions)
        self.loc = self.startloc
        
        self.rage_dur = 0
        self.ki_spent = 0
        
        del self.equip_list
        self.equip_list = copy.deepcopy(self.start_equip_list)
        del self.melee_weaps
        self.melee_weaps = copy.deepcopy(self.start_melee_weaps)
        del self.ranged_weaps
        self.ranged_weaps = copy.deepcopy(self.start_ranged_weaps)
        del self.slots
        self.slots = copy.deepcopy(self.start_slots)
        
        del self.spell_list_mem
        self.spell_list_mem = copy.deepcopy(self.start_spell_list_mem)

    ############################################

    def print_stat_block(self, textwidth=60):

        stats = [self.strtot(), self.dextot(), self.contot(), self.inttot(), self.wistot(), self.chatot()]

        stats = map(lambda x:x if x > 0 else "-", stats)

        da_line = ""
        if self.da:
            da_line += "Defensive Abilities {}".format(", ".join(sorted(self.da)))
        dr = self.get_dr()
        if dr:
            if da_line != "":
                da_line += "; "
            da_line += "DR {}/{}".format(dr[0],dr[2].join(sorted(dr[1])))
        if self.immune:
            if da_line != "":
                da_line += "; "
            da_line += "Immune {}".format(", ".join(sorted(self.immune)))   
        sr = self.get_sr()
        if sr > 0:
            if da_line != "":
                da_line += "; "
            da_line += "SR {}".format(sr)    

        melee_set = []
        fob_set = []
        if "M" in self.weap_type():
            base_atk_line = self.print_atk_line(nofeat=True)
            if self.has_offhand():
                base_atk_line += ", " + self.print_atk_line(nofeat=True,weap=self.slots["wield"][1])
            melee_set.append(base_atk_line)
            if "Monk" in self.weap_group() and self.charClass == "Monk":
                fob_set.append(self.print_atk_line(nofeat=True,fob=True))
        for weapon in self.melee_weaps:
            if weapon == self.slots["wield"][0] or weapon == self.slots["wield"][1]:
                continue
            if weapon == 0:
                if len(self.melee_weaps) > 1 and self.charClass != "Monk":
                    continue
            melee_set.append(self.print_atk_line(weap=weapon,nofeat=True))
            if "Monk" in self.weap_group(weapon) and self.charClass == "Monk":
                fob_set.append(self.print_atk_line(weap=weapon,nofeat=True,fob=True))
        melee_set += fob_set
        for i in range(len(melee_set[0:-1])):
            melee_set[i] += " or"

        ranged_set = []
        fob_set = []
        if "R" in self.weap_type():
            base_atk_line = self.print_atk_line(nofeat=True)
            ranged_set.append(base_atk_line)
            if "Monk" in self.weap_group() and self.charClass == "Monk":
                fob_set.append(self.print_atk_line(nofeat=True,fob=True))
        for weapon in self.ranged_weaps:
            if weapon == self.slots["wield"][0]:
                continue
            ranged_set.append(self.print_atk_line(weap=weapon,nofeat=True))
            if "Monk" in self.weap_group(weapon) and self.charClass == "Monk":
                fob_set.append(self.print_atk_line(weap=weapon,nofeat=True,fob=True))
        ranged_set += fob_set    
        for i in range(len(ranged_set[0:-1])):
            ranged_set[i] += " or"
        ranged_line = "Ranged {}".format(" or ".join(ranged_set))
        
        if self.CL() > 0:
            if self.charClass in ["Cleric","Wizard","Paladin","Ranger"]:
                spell_type = "Prepared"
            elif self.charClass in ["Bard","Sorcerer"]:
                spell_type = "Known"
        
        spell_line = self.print_spell_line()

        wordwrap = self.textwrap.TextWrapper(subsequent_indent="  ", width=textwidth)
        wordwrap_indent = self.textwrap.TextWrapper(initial_indent="  ", subsequent_indent="    ", width=textwidth)
        separator = "=" * textwidth

        out = []

        out.append(separator)
        out.append(wordwrap.fill("{}".format(self.name)))
        out.append(wordwrap.fill("{} {} {}".format(self.race, self.charClass, self.level)))
        out.append(wordwrap.fill("{} {} ({})".format(self.size, self.type.lower(), ', '.join(self.subtype))))
        out.append("")
        out.append(wordwrap.fill("Init {:+d}".format(self.get_init())))
        out.append(separator)
        out.append(wordwrap.fill("DEFENSE"))
        out.append(separator)
        out.append(wordwrap.fill(self.print_AC_line()))
        out.append(wordwrap.fill("hp {} ({})".format(self.get_hp(),self.print_HD())))
        out.append(wordwrap.fill(self.print_save_line()))
        if da_line:
            out.append(wordwrap.fill(da_line))
        out.append(separator)
        out.append(wordwrap.fill("OFFENSE"))
        out.append(separator)
        out.append(wordwrap.fill("Speed {} ft.".format(self.get_move())))
        if melee_set:
            out.append(wordwrap.fill("Melee {}".format(melee_set[0])))
            for melee in melee_set[1:]:
                out.append(wordwrap_indent.fill(melee))
        if ranged_set and not self.has("Raging"):
            out.append(wordwrap.fill("Ranged {}".format(ranged_set[0])))
            for ranged in ranged_set[1:]:
                out.append(wordwrap_indent.fill(ranged))
        if self.sa:
            out.append(wordwrap.fill("Special Attacks {}".format(", ".join(sorted(self.sa)))))
        if self.CL() > 0:
            out.append(wordwrap.fill("{} Spells {} (CL {}; concentration {:+d})".format(self.charClass,spell_type,self.ordinal(self.CL()),self.concentration())))
            for i in range(self.max_spell_lvl,-1,-1):
                out.append(wordwrap_indent.fill(spell_line[i]))
        out.append(separator)
        out.append(wordwrap.fill("STATISTICS"))
        out.append(separator)
        out.append(wordwrap.fill("Str {}, Dex {}, Con {}, Int {}, Wis {}, Cha {}".format(*stats)))
        out.append(wordwrap.fill("Base Atk {:+d}; CMB {:+d}; CMD {}".format(self.bab[0],self.CMB(),self.CMD())))
        out.append(wordwrap.fill("Feats {}".format(', '.join(sorted(self.feat_list)))))
        lang_list = ", ".join(sorted(self.lang))
        if lang_list:
            lang_list += "; "
        lang_list += ", ".join(sorted(self.lang_spec))
        if lang_list:
            out.append(wordwrap.fill("Languages {}".format(lang_list)))
        if self.sq:
            out.append(wordwrap.fill("SQ {}".format(", ".join(sorted(self.sq)))))
        out.append(separator)

        return '\n'.join(out)

###################################################################

class Monster(Foundation):
    """Monster stats and data"""

    def __init__(self, name=None, side=1, AC=10, move=30, loc=[0,0], tilesize=[1,1], HD=1, type="Humanoid", subtype=[], size="Medium", hp=1, str=10, dex=10, con=10, int=10, wis=10, cha=10, feat_list=[], arcane=False, divine=False, CL=0, reach=5, fort=None, ref=None, will=None, hands=2, legs=2):

        self.level = 0
        self.charClass = None
        self.HD = HD
        self.arcane = arcane
        self.divine = divine
        self.CL = CL
        self.weap_bon = 0
        self.fc = []

        Foundation.__init__(self, name, side, AC, move, loc, hp, tilesize, str, dex, con, int, wis, cha, feat_list, type, size, reach, fort, ref, will, hands, legs)

        self.set_bab()
        self.set_hit_die()
        
        self.model = False

        if hp == 0:
            self.roll_hp_tot()

    def set_bab(self):

        if self.type in ["Construct", "Dragon", "Magical Beast", "Monstrous Humanoid", "Outsider"]:
            self.bab = range(self.HD, 0, -5)
        elif self.type in ["Aberration", "Animal", "Humanoid", "Ooze", "Plant", "Undead", "Vermin"]:
            self.bab = range(int(self.HD * 3 / 4), 0, -5)
            if not self.bab:
                self.bab = [int(self.HD * 3 / 4)]
        else:
            self.bab = range(int(self.HD / 2), 0, -5)
            if not self.bab:
                self.bab = [int(self.HD / 2)]

    def set_hit_die(self):

        if self.type in ["Dragon"]:
            self.hit_die = 12
        elif self.type in ["Construct", "Magical Beast", "Monstrous Humanoid", "Outsider"]:
            self.hit_die = 10
        elif self.type in ["Aberration", "Animal", "Humanoid", "Ooze", "Plant", "Undead", "Vermin"]:
            self.hit_die = 8
        else:
            self.hit_die = 6

    def reset(self):

        self.damage = 0
        self.damage_con = "Normal"

###################################################################

class Charmodel(Foundation):
    """Mental model char framework"""
    
    def __init__(self, name=None, side=1, AC=10, bab=0, move=30, loc=[0,0], tilesize=[1,1], HD=1, type="Humanoid", subtype=[], size="Medium", hp=1, str=10, dex=10, con=10, int=10, wis=10, cha=10, feat_list=[], arcane=False, divine=False, CL=0, reach=5, fort=None, ref=None, will=None, hands=2, legs=2, init=0, race=None, charClass=None, level=1, fc=[], id=None, orig=None):
    
        
        Foundation.__init__(self, name, side, AC, move, loc, hp, tilesize, str, dex, con, int, wis, cha, feat_list, type, subtype, size, reach, fort, ref, will, hands, legs)
        
        self.model = True
        self.id = id
        self.orig = orig
        
        self.init = init
        
        if race:
            self.race = race
        else:
            self.race = "Unknown"
        
        if charClass:
            self.charClass = charClass
        else:
            self.charClass = "Unknown"
        
        self.level = level
        
        self.HD = HD
        
        self.fc = fc
    
    def is_active(self):
        return self.orig.is_active()