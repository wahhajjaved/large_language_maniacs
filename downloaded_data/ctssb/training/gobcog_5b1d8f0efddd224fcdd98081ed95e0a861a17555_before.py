# -*- coding: utf-8 -*-
import asyncio
import contextlib
import json
import logging
import os
import random
import re
import time
from collections import namedtuple
from datetime import date, datetime
from types import SimpleNamespace
from typing import List, Optional, Union

import discord
from redbot.cogs.bank import check_global_setting_admin
from redbot.core import Config, bank, checks, commands
from redbot.core.commands import Context
from redbot.core.data_manager import bundled_data_path, cog_data_path
from redbot.core.errors import BalanceTooHigh
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import (
    box,
    escape,
    humanize_list,
    humanize_timedelta,
    pagify,
)
from redbot.core.utils.common_filters import filter_various_mentions
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu, start_adding_reactions
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate

import adventure.charsheet

from .charsheet import (
    Character,
    GameSession,
    Item,
    ItemConverter,
    Stats,
    calculate_sp,
    can_equip,
    equip_level,
    has_funds,
    parse_timedelta,
    DEV_LIST,
    RARITIES,
    ORDER,
)

try:
    from redbot.core.utils.chat_formatting import humanize_number
except ImportError:

    def humanize_number(val: int) -> str:
        if isinstance(val, int):
            return "{:,}".format(val)
        return f"{val}"


try:
    from redbot.core.bank import get_max_balance
except ImportError:
    from redbot.core.bank import MAX_BALANCE

    async def get_max_balance(guild: discord.Guild = None) -> int:
        return MAX_BALANCE


BaseCog = getattr(commands, "Cog", object)

_ = Translator("Adventure", __file__)

log = logging.getLogger("red.cogs.adventure")

REBIRTH_LVL = 20
REBIRTH_STEP = 5
_SCHEMA_VERSION = 2
_config: Config = None


async def smart_embed(ctx, message, success=None):
    if ctx.guild:
        use_embeds = await _config.guild(ctx.guild).embed()
    else:
        use_embeds = True
    if use_embeds:
        if await ctx.embed_requested():
            if success is True:
                colour = discord.Colour.dark_green()
            elif success is False:
                colour = discord.Colour.dark_red()
            else:
                colour = await ctx.embed_colour()
            return await ctx.send(embed=discord.Embed(description=message, color=colour))
        else:
            return await ctx.send(message)
    return await ctx.send(message)


class AdventureResults:
    """Object to store recent adventure results."""

    def __init__(self, num_raids):
        """TODO: to be defined1. """
        self._num_raids = num_raids
        self._last_raids = []

    def add_result(self, main_action, amount, num_ppl, success):
        """Add result to this object.
        :main_action: Main damage action taken by the adventurers
            (highest amount dealt). Should be either "attack" or
            "talk". Running will just be notated by a 0 amount.
        :amount: Amount dealt.
        :num_ppl: Number of people in adventure.
        :success: Whether adventure was successful or not.
        """
        if len(self._last_raids) >= self._num_raids:
            self._last_raids.pop(0)
        raid_dict = {}
        for var in ("main_action", "amount", "num_ppl", "success"):
            raid_dict[var] = locals()[var]
        self._last_raids.append(raid_dict)

    def get_stat_range(self):
        """Return reasonable stat range for monster pool to have based
        on last few raids' damage.

        :returns: Dict with stat_type, min_stat and max_stat.
        """
        # how much % to increase damage for solo raiders so that they
        # can't just solo every monster based on their own average
        # damage
        SOLO_RAID_SCALE = 0.25
        if len(self._last_raids) == 0:
            return {
                "stat_type": "hp",
                "min_stat": 0,
                "max_stat": 0,
            }

        # tally up stats for raids
        num_attack = 0
        dmg_amount = 0
        num_talk = 0
        talk_amount = 0
        num_wins = 0
        for raid in self._last_raids:
            if raid["main_action"] == "attack":
                num_attack += 1
                dmg_amount += raid["amount"]
                if raid["num_ppl"] == 1:
                    dmg_amount += raid["amount"] * SOLO_RAID_SCALE
            else:
                num_talk += 1
                talk_amount += raid["amount"]
                if raid["num_ppl"] == 1:
                    talk_amount += raid["amount"] * SOLO_RAID_SCALE
            log.debug(f"raid dmg: {raid['amount']}")
            if raid["success"]:
                num_wins += 1

        # calculate relevant stats
        if num_wins == 0:
            num_wins = self._num_raids // 2
        win_percent = num_wins / self._num_raids
        stat_type = "hp"
        avg_amount = 0
        if num_attack > 0:
            avg_amount = dmg_amount / num_attack
        if dmg_amount < talk_amount:
            stat_type = "dipl"
            avg_amount = talk_amount / num_talk

        # return main stat and range
        min_stat = avg_amount * 0.75
        max_stat = avg_amount * 1.5
        # want win % to be at least 50%, even when solo
        # if win % is below 50%, scale back min/max for easier mons
        if win_percent < 0.5:
            min_stat = avg_amount * win_percent
            max_stat = avg_amount * 1.25

        stats_dict = {}
        for var in ("stat_type", "min_stat", "max_stat"):
            stats_dict[var] = locals()[var]
        return stats_dict

    def __str__(self):
        return str(self._last_raids)


@cog_i18n(_)
class Adventure(BaseCog):
    """Adventure, derived from the Goblins Adventure cog by locastan."""

    __version__ = "3.0.0"

    def __init__(self, bot):
        self.bot = bot
        self._last_trade = {}
        self._adv_results = AdventureResults(2)
        self.emojis = SimpleNamespace()
        self.emojis.fumble = "\N{EXCLAMATION QUESTION MARK}"
        self.emojis.level_up = "\N{BLACK UP-POINTING DOUBLE TRIANGLE}"
        self.emojis.rebirth = "\N{BABY SYMBOL}"
        self.emojis.attack = "\N{DAGGER KNIFE}"
        self.emojis.magic = "\N{SPARKLES}"
        self.emojis.talk = "\N{LEFT SPEECH BUBBLE}"
        self.emojis.pray = "\N{PERSON WITH FOLDED HANDS}"
        self.emojis.run = "\N{RUNNER}"
        self.emojis.crit = "\N{COLLISION SYMBOL}"
        self.emojis.magic_crit = "\N{HIGH VOLTAGE SIGN}"
        self.emojis.berserk = "\N{RIGHT ANGER BUBBLE}"
        self.emojis.dice = "\N{GAME DIE}"
        self.emojis.yes = "\N{WHITE HEAVY CHECK MARK}"
        self.emojis.no = "\N{NEGATIVE SQUARED CROSS MARK}"
        self.emojis.sell = "\N{MONEY BAG}"
        self.emojis.skills = SimpleNamespace()
        self.emojis.skills.bless = "\N{SCROLL}"
        # self.emojis.skills.psychic = "\N{SIX POINTED STAR WITH MIDDLE DOT}"
        self.emojis.skills.berserker = self.emojis.berserk
        self.emojis.skills.wizzard = self.emojis.magic_crit
        self.emojis.skills.bard = (
            "\N{EIGHTH NOTE}\N{BEAMED EIGHTH NOTES}\N{BEAMED SIXTEENTH NOTES}"
        )
        self.emojis.hp = "\N{HEAVY BLACK HEART}\N{VARIATION SELECTOR-16}"
        self.emojis.dipl = self.emojis.talk

        self._adventure_actions = [
            self.emojis.attack,
            self.emojis.magic,
            self.emojis.talk,
            self.emojis.pray,
            self.emojis.run,
        ]
        self._adventure_controls = {
            "fight": self.emojis.attack,
            "magic": self.emojis.magic,
            "talk": self.emojis.talk,
            "pray": self.emojis.pray,
            "run": self.emojis.run,
        }
        self._order = [
            "head",
            "neck",
            "chest",
            "gloves",
            "belt",
            "legs",
            "boots",
            "left",
            "right",
            "two handed",
            "ring",
            "charm",
        ]
        self._treasure_controls = {
            self.emojis.yes: "equip",
            self.emojis.no: "backpack",
            self.emojis.sell: "sell",
        }
        self._yes_no_controls = {self.emojis.yes: "yes", self.emojis.no: "no"}

        self._adventure_countdown = {}
        self._rewards = {}
        self._trader_countdown = {}
        self._current_traders = {}
        self._curent_trader_stock = {}
        self._sessions = {}
        self._react_messaged = []
        self.tasks = {}
        self.locks = {}

        self.config = Config.get_conf(self, 2_710_801_001, force_registration=True)

        default_user = {
            "exp": 0,
            "lvl": 1,
            "att": 0,
            "cha": 0,
            "int": 0,
            "treasure": [0, 0, 0, 0, 0],
            "items": {
                "head": {},
                "neck": {},
                "chest": {},
                "gloves": {},
                "belt": {},
                "legs": {},
                "boots": {},
                "left": {},
                "right": {},
                "ring": {},
                "charm": {},
                "backpack": {},
            },
            "loadouts": {},
            "class": {
                "name": _("Hero"),
                "ability": False,
                "desc": _("Your basic adventuring hero."),
                "cooldown": 0,
            },
            "skill": {"pool": 0, "att": 0, "cha": 0, "int": 0},
        }

        default_guild = {
            "cart_channels": [],
            "god_name": "",
            "cart_name": "",
            "embed": True,
            "cooldown": 0,
            "cartroom": None,
            "cart_timeout": 10800,
            "cooldown_timer_manual": 120,
        }
        default_global = {
            "god_name": _("Herbert"),
            "cart_name": _("Hawl's brother"),
            "theme": "default",
            "restrict": False,
            "embed": True,
            "enable_chests": True,
            "currentweek": date.today().isocalendar()[1],
            "schema_version": 1,
        }
        self.RAISINS: list = None
        self.THREATEE: list = None
        self.TR_GEAR_SET: dict = None
        self.ATTRIBS: dict = None
        self.MONSTERS: dict = None
        self.AS_MONSTERS: dict = None
        self.MONSTER_NOW: dict = None
        self.LOCATIONS: list = None
        self.PETS: dict = None

        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)
        self.config.register_user(**default_user)
        self.cleanup_loop = self.bot.loop.create_task(self.cleanup_tasks())
        log.exception("Creating Task", exc_info=False)
        self._init_task = self.bot.loop.create_task(self.initialize())
        self._ready_event = asyncio.Event()

    async def cog_before_invoke(self, ctx: Context):
        await self._ready_event.wait()

    @staticmethod
    def is_dev(user: Union[discord.User, discord.Member]):
        return user.id in DEV_LIST

    async def initialize(self):
        """This will load all the bundled data into respective variables."""
        await self.bot.wait_until_ready()
        try:
            global _config
            _config = self.config
            theme = await self.config.theme()
            as_monster_fp = cog_data_path(self) / f"{theme}" / "as_monsters.json"
            attribs_fp = cog_data_path(self) / f"{theme}" / "attribs.json"
            locations_fp = cog_data_path(self) / f"{theme}" / "locations.json"
            monster_fp = cog_data_path(self) / f"{theme}" / "monsters.json"
            pets_fp = cog_data_path(self) / f"{theme}" / "pets.json"
            raisins_fp = cog_data_path(self) / f"{theme}" / "raisins.json"
            threatee_fp = cog_data_path(self) / f"{theme}" / "threatee.json"
            tr_set_fp = cog_data_path(self) / f"{theme}" / "tr_set.json"
            prefixes_fp = cog_data_path(self) / f"{theme}" / "prefixes.json"
            materials_fp = cog_data_path(self) / f"{theme}" / "materials.json"
            equipment_fp = cog_data_path(self) / f"{theme}" / "equipment.json"
            suffixes_fp = cog_data_path(self) / f"{theme}" / "suffixes.json"
            files = {
                "pets": pets_fp,
                "attr": attribs_fp,
                "monster": monster_fp,
                "location": locations_fp,
                "raisins": raisins_fp,
                "threatee": threatee_fp,
                "set": tr_set_fp,
                "as_monsters": as_monster_fp,
                "prefixes": prefixes_fp,
                "materials": materials_fp,
                "equipment": equipment_fp,
                "suffixes": suffixes_fp,
            }
            for name, file in files.items():
                if not file.exists():
                    files[name] = bundled_data_path(self) / "default" / f"{file.name}"
            with files["pets"].open("r") as f:
                self.PETS = json.load(f)
            with files["attr"].open("r") as f:
                self.ATTRIBS = json.load(f)
            with files["monster"].open("r") as f:
                self.MONSTERS = json.load(f)
            with files["as_monsters"].open("r") as f:
                self.AS_MONSTERS = json.load(f)
            with files["location"].open("r") as f:
                self.LOCATIONS = json.load(f)
            with files["raisins"].open("r") as f:
                self.RAISINS = json.load(f)
            with files["threatee"].open("r") as f:
                self.THREATEE = json.load(f)
            with files["set"].open("r") as f:
                self.TR_GEAR_SET = json.load(f)
            with files["prefixes"].open("r") as f:
                self.PREFIXES = json.load(f)
            with files["materials"].open("r") as f:
                self.MATERIALS = json.load(f)
            with files["equipment"].open("r") as f:
                self.EQUIPMENT = json.load(f)
            with files["suffixes"].open("r") as f:
                self.SUFFIXES = json.load(f)

            adventure.charsheet.TR_GEAR_SET = self.TR_GEAR_SET
            adventure.charsheet.PETS = self.PETS
            adventure.charsheet.REBIRTH_LVL = REBIRTH_LVL
            adventure.charsheet.REBIRTH_STEP = REBIRTH_STEP
            await self._migrate_config(
                from_version=await self.config.schema_version(), to_version=_SCHEMA_VERSION
            )
        except Exception as err:
            log.exception("Everything is burning", exc_info=err)
        else:
            self._ready_event.set()

    async def cleanup_tasks(self):
        await self._ready_event.wait()
        while self is self.bot.get_cog("Adventure"):
            to_delete = []
            for msg_id, task in self.tasks.items():
                if task.done():
                    to_delete.append(msg_id)
            for task in to_delete:
                del self.tasks[task]
            await asyncio.sleep(300)

    async def _migrate_config(self, from_version: int, to_version: int) -> None:
        database_entries = []
        log.error(f"from_version: {from_version} to_version:{to_version}")
        if from_version == to_version:
            return
        if from_version < 2 <= to_version:
            # _guilds = [g for g in self.bot.guilds if not g.unavailable and g.large and not g.chunked]
            # _uguilds = [g for g in self.bot.guilds if g.unavailable]
            group = self.config._get_base_group(self.config.USER)
            # await self.bot.request_offline_members(*_guilds)
            accounts = await group.all()
            tmp = accounts.copy()
            # members = self.bot.get_all_members()
            # user_list = {str(m.id) for m in members if m.guild not in _uguilds}

            async with group.all() as adventurers_data:
                for user in tmp:
                    # if user not in user_list:
                    #     del adventurers_data[user]
                    # else:
                    new_backpack = {}
                    new_loadout = {}
                    user_equipped_items = adventurers_data[user]["items"]
                    for slot in user_equipped_items.keys():
                        if user_equipped_items[slot]:
                            for slot_item_name, slot_item in list(
                                user_equipped_items[slot].items()
                            )[:1]:
                                # update slot item if item equipped
                                new_name, slot_item = self._convert_item_migration(
                                    slot_item_name, slot_item
                                )
                                adventurers_data[user]["items"][slot] = {new_name: slot_item}
                    if "backpack" not in adventurers_data[user]:
                        adventurers_data[user]["backpack"] = {}
                    for backpack_item_name, backpack_item in adventurers_data[user][
                        "backpack"
                    ].items():
                        new_name, backpack_item = self._convert_item_migration(
                            backpack_item_name, backpack_item
                        )
                        new_backpack[new_name] = backpack_item
                    adventurers_data[user]["backpack"] = new_backpack
                    if "loadouts" not in adventurers_data[user]:
                        adventurers_data[user]["loadouts"] = {}
                    try:
                        for loadout_name, loadout in adventurers_data[user]["loadouts"].items():
                            for slot, equipped_loadout in loadout.items():
                                new_loadout[slot] = {}
                                for loadout_item_name, loadout_item in equipped_loadout.items():

                                    new_name, loadout_item = self._convert_item_migration(
                                        loadout_item_name, loadout_item
                                    )
                                    new_loadout[slot][new_name] = loadout_item
                        adventurers_data[user]["loadouts"] = new_loadout
                    except Exception:
                        adventurers_data[user]["loadouts"] = {}
        await self.config.schema_version.set(to_version)

    def _convert_item_migration(self, item_name, item_dict):
        new_name = item_name
        if "name" in item_dict:
            del item_dict["name"]
        if "rarity" not in item_name:
            item_dict["rarity"] = "common"
        if item_dict["rarity"] == "legendary":
            new_name = (
                item_name.replace("{Legendary:'", "").replace("legendary:'", "").replace("'}", "")
            )
        if item_dict["rarity"] == "epic":
            new_name = item_name.replace("[", "").replace("]", "")
        if item_dict["rarity"] == "rare":
            new_name = item_name.replace("_", " ").replace(".", "")
        if item_dict["rarity"] == "set":
            new_name = (
                item_name.replace("{Gear_Set:'", "")
                .replace("{gear_set:'", "")
                .replace("{Gear Set:'", "")
                .replace("'}", "")
            )
        if item_dict["rarity"] != "set":
            if "bonus" in item_dict:
                del item_dict["bonus"]
            if "parts" in item_dict:
                del item_dict["parts"]
            if "set" in item_dict:
                del item_dict["set"]
        return new_name, item_dict

    def in_adventure(self, ctx=None, user=None):
        author = user or ctx.author
        sessions = self._sessions
        if not sessions:
            return False
        participants_ids = set(
            [
                p.id
                for _loop, session in self._sessions.items()
                for p in [
                    *session.fight,
                    *session.magic,
                    *session.pray,
                    *session.talk,
                    *session.run,
                ]
            ]
        )
        return bool(author.id in participants_ids)

    async def allow_in_dm(self, ctx):
        """Checks if the bank is global and allows the command in dm."""
        if ctx.guild is not None:
            return True
        return bool(ctx.guild is None and await bank.is_global())

    def get_lock(self, member: discord.Member):
        if member.id not in self.locks:
            self.locks[member.id] = asyncio.Lock()
        return self.locks[member.id]

    @staticmethod
    def escape(t: str) -> str:
        return escape(filter_various_mentions(t), mass_mentions=True, formatting=True)

    @commands.command()
    @commands.is_owner()
    async def makecart(self, ctx: Context):
        """Force cart to appear in a channel."""
        await self._trader(ctx, True)

    async def _genitem(self, rarity: str = None, slot: str = None):
        """Generate an item."""
        if rarity == "set":
            items = list(self.TR_GEAR_SET.items())
            items = (
                [
                    i
                    for i in items
                    if i[1]["slot"] == [slot]
                    or (slot == "two handed" and i[1]["slot"] == ["left", "right"])
                ]
                if slot
                else items
            )
            item_name, item_data = random.choice(items)
            return Item.from_json({item_name: item_data})

        RARE_INDEX = RARITIES.index("rare")
        EPIC_INDEX = RARITIES.index("epic")
        PREFIX_CHANCE = {"rare": 0.5, "epic": 0.75, "legendary": 0.9, "set": 0}
        SUFFIX_CHANCE = {"epic": 0.5, "legendary": 0.75}

        if rarity not in RARITIES:
            rarity = "normal"
        if slot is None:
            slot = random.choice(ORDER)
            #  slot = random.choice(["right", "chest"])
        name = ""
        stats = {
            "att": 0,
            "cha": 0,
            "int": 0,
            "dex": 0,
            "luck": 0,
        }

        def add_stats(word_stats):
            """Add stats in word's dict to local stats dict."""
            for stat in stats.keys():
                if stat in word_stats:
                    stats[stat] += word_stats[stat]

        # only rare and above should have prefix with PREFIX_CHANCE
        if RARITIES.index(rarity) >= RARE_INDEX and random.random() <= PREFIX_CHANCE[rarity]:
            #  log.debug(f"Prefix %: {PREFIX_CHANCE[rarity]}")
            prefix, prefix_stats = random.choice(list(self.PREFIXES.items()))
            name += f"{prefix} "
            add_stats(prefix_stats)

        material, material_stat = random.choice(list(self.MATERIALS[rarity].items()))
        name += f"{material} "
        for stat in stats.keys():
            stats[stat] += material_stat

        equipment, equipment_stats = random.choice(list(self.EQUIPMENT[slot].items()))
        name += f"{equipment}"
        add_stats(equipment_stats)

        # only epic and above should have suffix with SUFFIX_CHANCE
        if RARITIES.index(rarity) >= EPIC_INDEX and random.random() <= SUFFIX_CHANCE[rarity]:
            #  log.debug(f"Suffix %: {SUFFIX_CHANCE[rarity]}")
            suffix, suffix_stats = random.choice(list(self.SUFFIXES.items()))
            of_keyword = "of" if "the" not in suffix_stats else "of the"
            name += f" {of_keyword} {suffix}"
            add_stats(suffix_stats)

        slot_list = [slot] if slot != "two handed" else ["left", "right"]
        return Item(
            name=name,
            slot=slot_list,
            rarity=rarity,
            att=stats["att"],
            int=stats["int"],
            cha=stats["cha"],
            dex=stats["dex"],
            luck=stats["luck"],
            owned=1,
            parts=1,
        )

    @commands.command()
    @commands.is_owner()
    async def genitems(self, ctx: Context, rarity: str, slot: str, num: int = 1):
        """Generate random items."""
        user = ctx.author
        rarity = rarity.lower()
        slot = slot.lower()
        if rarity not in RARITIES:
            return await smart_embed(
                ctx,
                _("Invalid rarity; choose one of {list}.").format(list=humanize_list(RARITIES)),
            )
        elif slot not in ORDER:
            return await smart_embed(
                ctx, _("Invalid slot; choose one of {list}.").format(list=humanize_list(ORDER))
            )
        async with self.get_lock(user):
            try:
                c = await Character.from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            for i in range(num):
                await c.add_to_backpack(await self._genitem(rarity, slot))
            await self.config.user(ctx.author).set(c.to_json())
        await ctx.invoke(self._backpack)

    @commands.command()
    @commands.is_owner()
    async def copyuser(self, ctx: Context, user_id: int):
        """Copy another members data to yourself.

        Note this overrides your current data.
        """
        user = namedtuple("User", "id")
        user = user(user_id)
        user_data = await self.config.user(user).all()
        await self.config.user(ctx.author).set(user_data)
        await ctx.tick()

    @commands.group(name="backpack", autohelp=False)
    async def _backpack(self, ctx: Context):
        """This shows the contents of your backpack.

        Selling: `[p]backpack sell item_name`
        Trading: `[p]backpack trade @user price item_name`
        Equip:   `[p]backpack equip item_name`
        or respond with the item name to the backpack command output.
        """
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if not ctx.invoked_subcommand:
            backpack_contents = _("[{author}'s backpack] \n\n{backpack}\n").format(
                author=self.escape(ctx.author.display_name), backpack=c.get_backpack()
            )
            msgs = []
            for page in pagify(backpack_contents, delims=["\n"], shorten_by=20):
                msgs.append(box(page, lang="css"))
            return await menu(ctx, msgs, DEFAULT_CONTROLS)

    @_backpack.command(name="equip")
    async def backpack_equip(self, ctx: Context, *, equip_item: ItemConverter):
        """Equip an item from your backpack."""
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _(
                    "You tried to equipping an item but the monster ahead did not allow you to do so"
                ),
            )
        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        equiplevel = equip_level(c, equip_item)
        if self.is_dev(ctx.author):  # FIXME:
            equiplevel = 0

        if not can_equip(c, equip_item):
            return await smart_embed(
                ctx,
                _("You need to be level `{level}` to equip this item").format(level=equiplevel),
            )
        equip = c.backpack[equip_item.name]
        if equip:
            slot = equip.slot[0]
            if len(equip.slot) > 1:
                slot = "two handed"
            if not getattr(c, equip.slot[0]):
                equip_msg = box(
                    _("{author} equipped {item} ({slot} slot).").format(
                        author=self.escape(ctx.author.display_name), item=str(equip), slot=slot
                    ),
                    lang="css",
                )
            else:
                equip_msg = box(
                    _(
                        "{author} equipped {item} "
                        "({slot} slot) and put {put} into their backpack."
                    ).format(
                        author=self.escape(ctx.author.display_name),
                        item=str(equip),
                        slot=slot,
                        put=getattr(c, equip.slot[0]),
                    ),
                    lang="css",
                )
            await ctx.send(equip_msg)
            async with self.get_lock(c.user):
                try:
                    c = await Character.from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                c = await c.equip_item(equip, True, self.is_dev(ctx.author))  # FIXME:
                await self.config.user(ctx.author).set(c.to_json())

    @_backpack.command(name="sellall")
    async def backpack_sellall(self, ctx: Context, rarity: str = None):
        """Sell all items in your backpack."""
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx, _("You tried to selling your items, but there is no merchants in sight.")
            )
        if rarity and rarity.lower() not in RARITIES:
            return await smart_embed(
                ctx, _("I've never heard of `{rarity}` rarity items before.").format(rarity=rarity)
            )
        elif rarity and rarity.lower() in ["set", "forged"]:
            return await smart_embed(
                ctx, _("You cannot sell `{rarity}` rarity items.").format(rarity=rarity)
            )
        async with self.get_lock(ctx.author):
            msg = ""
            try:
                c = await Character.from_json(self.config, ctx.author)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            total_price = 0
            items = [i for n, i in c.backpack.items() if i.rarity not in ["forged", "set"]]
            count = 0
            for item in items:
                if not rarity or item.rarity == rarity:
                    item_price = 0
                    old_owned = item.owned
                    for x in range(0, item.owned):
                        item.owned -= 1
                        item_price += self._sell(c, item)
                        if item.owned <= 0:
                            del c.backpack[item.name]
                        if not count % 10:
                            await asyncio.sleep(0.1)
                        count += 1
                    msg += _("{old_item} sold for {price}.\n").format(
                        old_item=str(old_owned) + " " + str(item),
                        price=humanize_number(item_price),
                    )
                    total_price += item_price
                    await asyncio.sleep(0.1)
                    item_price = max(item_price, 0)
                    if item_price > 0:
                        with contextlib.suppress(BalanceTooHigh):
                            await bank.deposit_credits(ctx.author, item_price)
            await self.config.user(ctx.author).set(c.to_json())
        msg_list = []
        new_msg = _("{author} sold all their{rarity} items for {price}.\n\n{items}").format(
            author=self.escape(ctx.author.display_name),
            rarity=f" {rarity}" if rarity else "",
            price=humanize_number(total_price),
            items=msg,
        )
        for page in pagify(new_msg, shorten_by=10):
            msg_list.append(box(page, lang="css"))
        await menu(ctx, msg_list, DEFAULT_CONTROLS)

    @_backpack.command(name="sell")
    @commands.cooldown(rate=3, per=60, type=commands.BucketType.user)
    async def backpack_sell(self, ctx: Context, *, item: ItemConverter):
        """Sell an item from your backpack."""
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx, _("You tried to selling your items, but there is no merchants in sight.")
            )
        if item.rarity == "forged":
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                box(
                    _(
                        "\n{author}, your {device} is "
                        "refusing to be sold and bit your finger for trying."
                    ).format(author=self.escape(ctx.author.display_name), device=str(item)),
                    lang="css",
                )
            )
        elif item.rarity == "set":
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                box(
                    _(
                        "\n{author}, you are not able to sell Gear Set items as they are bound to your soul."
                    ).format(author=self.escape(ctx.author.display_name)),
                    lang="css",
                )
            )
        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            ctx.command.reset_cooldown(ctx)
            log.exception("Error with the new character sheet")
            return
        price_shown = self._sell(c, item)
        messages = [
            _("**{author}**, do you want to sell this item for {price} each? {item}").format(
                author=self.escape(ctx.author.display_name),
                item=box(str(item), lang="css"),
                price=humanize_number(price_shown),
            )
        ]

        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(self.config, ctx.author)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            try:
                item = c.backpack[item.name]
            except KeyError:
                return

            async def _backpack_sell_menu(
                ctx: commands.Context,
                pages: list,
                controls: dict,
                message: discord.Message,
                page: int,
                timeout: float,
                emoji: str,
            ):
                if message:
                    with contextlib.suppress(discord.HTTPException):
                        await message.delete()
                    await self._backpack_sell_button_action(ctx, emoji, page, item, price_shown, c)
                    return None

            back_pack_sell_controls = {
                "\N{DIGIT ONE}\N{COMBINING ENCLOSING KEYCAP}": _backpack_sell_menu,
                "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}": _backpack_sell_menu,
                "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS WITH CIRCLED ONE OVERLAY}": _backpack_sell_menu,
                "\N{CROSS MARK}": _backpack_sell_menu,
            }

            await menu(ctx, messages, back_pack_sell_controls, timeout=60)

    async def _backpack_sell_button_action(self, ctx, emoji, page, item, price_shown, character):
        currency_name = await bank.get_currency_name(ctx.guild)
        msg = ""
        if (
            emoji == "\N{DIGIT ONE}\N{COMBINING ENCLOSING KEYCAP}"
        ):  # user reacted with one to sell.
            ctx.command.reset_cooldown(ctx)
            # sell one of the item
            price = 0
            item.owned -= 1
            price += price_shown
            msg += _("**{author}** sold one {item} for {price} {currency_name}.\n").format(
                author=self.escape(ctx.author.display_name),
                item=box(item, lang="css"),
                price=humanize_number(price),
                currency_name=currency_name,
            )
            if item.owned <= 0:
                del character.backpack[item.name]
            price = max(price, 0)
            if price > 0:
                with contextlib.suppress(BalanceTooHigh):
                    await bank.deposit_credits(ctx.author, price)
        elif (
            emoji == "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}"
        ):  # user wants to sell all owned.
            ctx.command.reset_cooldown(ctx)
            price = 0
            old_owned = item.owned
            count = 0
            for x in range(0, item.owned):
                item.owned -= 1
                price += price_shown
                if item.owned <= 0:
                    del character.backpack[item.name]
                if not count % 10:
                    await asyncio.sleep(0.1)
                count += 1
            msg += _(
                "**{author}** sold all their {old_item} for {price} {currency_name}.\n"
            ).format(
                author=self.escape(ctx.author.display_name),
                old_item=box(str(item) + " - " + str(old_owned), lang="css"),
                price=humanize_number(price),
                currency_name=currency_name,
            )
            price = max(price, 0)
            if price > 0:
                with contextlib.suppress(BalanceTooHigh):
                    await bank.deposit_credits(ctx.author, price)
        elif (
            emoji
            == "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS WITH CIRCLED ONE OVERLAY}"
        ):  # user wants to sell all but one.
            if item.owned == 1:
                ctx.command.reset_cooldown(ctx)
                return await smart_embed(ctx, _("You already only own one of those items."))
            price = 0
            old_owned = item.owned
            count = 0
            for x in range(1, item.owned):
                item.owned -= 1
                price += price_shown
            if not count % 10:
                await asyncio.sleep(0.1)
            count += 1
            if price != 0:
                msg += _(
                    "**{author}** sold all but one of their {old_item} for {price} {currency_name}.\n"
                ).format(
                    author=self.escape(ctx.author.display_name),
                    old_item=box(str(item) + " - " + str(old_owned - 1), lang="css"),
                    price=humanize_number(price),
                    currency_name=currency_name,
                )
                price = max(price, 0)
                if price > 0:
                    with contextlib.suppress(BalanceTooHigh):
                        await bank.deposit_credits(ctx.author, price)
        else:  # user doesn't want to sell those items.
            msg = _("Not selling those items.")

        if msg:
            await self.config.user(ctx.author).set(character.to_json())
            pages = [page for page in pagify(msg, delims=["\n"])]
            if pages:
                await menu(ctx, pages, DEFAULT_CONTROLS)

    @_backpack.command(name="trade")
    async def backpack_trade(
        self, ctx: Context, buyer: discord.Member, asking: Optional[int] = 1000, *, item
    ):
        """Trade an item from your backpack to another user."""
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _(
                    "You tried to trading your items, but the monster ahead neally took your head, pay attention."
                ),
            )
        if self.in_adventure(user=buyer):
            return await smart_embed(
                ctx,
                _(
                    "**{buyer}** is in an Adventure, you were unable to reach them via pigeon."
                ).format(buyer=self.escape(ctx.author.display_name)),
            )
        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if not any([x for x in c.backpack if item.lower() in x.lower()]):
            return await smart_embed(
                ctx,
                _("**{author}**, you have to specify an item from your backpack to trade.").format(
                    author=self.escape(ctx.author.display_name)
                ),
            )
        lookup = list(x for n, x in c.backpack.items() if item.lower() in x.name.lower())
        if len(lookup) > 1:
            await smart_embed(
                ctx,
                _(
                    "**{author}**, I found multiple items ({items}) "
                    "matching that name in your backpack.\nPlease be more specific."
                ).format(
                    author=self.escape(ctx.author.display_name),
                    items=humanize_list([x.name for x in lookup]),
                ),
            )
            return
        if any([x for x in lookup if x.rarity == "forged"]):
            device = [x for x in lookup if x.rarity == "forged"]
            return await ctx.send(
                box(
                    _("\n{author}, your {device} does not want to leave you.").format(
                        author=self.escape(ctx.author.display_name), device=str(device[0])
                    ),
                    lang="css",
                )
            )
        elif any([x for x in lookup if x.rarity == "set"]):
            return await ctx.send(
                box(
                    _(
                        "\n{character}, you cannot trade Gear set as they are bound to your soul."
                    ).format(character=self.escape(ctx.author.display_name)),
                    lang="css",
                )
            )
        else:
            item = lookup[0]
            hand = item.slot[0] if len(item.slot) < 2 else "two handed"
            currency_name = await bank.get_currency_name(ctx.guild)
            if str(currency_name).startswith("<"):
                currency_name = "credits"
            trade_talk = box(
                _(
                    "{author} wants to sell {item}. "
                    "(ATT: {att_item} | "
                    "CHA: {cha_item} | "
                    "INT: {int_item} | "
                    "DEX: {dex_item} | "
                    "LUCK: {luck_item}) "
                    "[{hand}])\n{buyer}, "
                    "do you want to buy this item for {asking} {currency_name}?"
                ).format(
                    author=self.escape(ctx.author.display_name),
                    item=item,
                    att_item=str(item.att),
                    cha_item=str(item.cha),
                    int_item=str(item.int),
                    dex_item=str(item.dex),
                    luck_item=str(item.luck),
                    hand=hand,
                    buyer=self.escape(buyer.display_name),
                    asking=str(asking),
                    currency_name=currency_name,
                ),
                lang="css",
            )
            trade_msg = await ctx.send(f"{buyer.mention}\n{trade_talk}")
            start_adding_reactions(trade_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(trade_msg, buyer)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
            except asyncio.TimeoutError:
                await self._clear_react(trade_msg)
                return
            if pred.result:  # buyer reacted with Yes.
                try:
                    if await bank.can_spend(buyer, asking):
                        async with self.get_lock(c.user):
                            try:
                                buy_user = await Character.from_json(self.config, buyer)
                            except Exception:
                                log.exception("Error with the new character sheet")
                                return
                            if buy_user.rebirths < c.rebirths:
                                return await smart_embed(
                                    ctx,
                                    _(
                                        "You can only trade with people the same rebirth level or higher than yours."
                                    ),
                                )
                            if not can_equip(buy_user, item):
                                return await smart_embed(
                                    ctx,
                                    "{buyer} can't equip this item so cancelling the trade".format(
                                        buyer=buyer.display_name
                                    ),
                                )
                            await bank.transfer_credits(buyer, ctx.author, asking)
                            c.backpack[item.name].owned -= 1
                            if c.backpack[item.name].owned <= 0:
                                del c.backpack[item.name]
                            await self.config.user(ctx.author).set(c.to_json())
                        async with self.get_lock(buyer):
                            try:
                                buy_user = await Character.from_json(self.config, buyer)
                            except Exception:
                                log.exception("Error with the new character sheet")
                                return
                            if item.name in buy_user.backpack:
                                buy_user.backpack[item.name].owned += 1
                            else:
                                item.owned = 1
                                buy_user.backpack[item.name] = item
                                await self.config.user(buyer).set(buy_user.to_json())
                        await trade_msg.edit(
                            content=(
                                box(
                                    _(
                                        "\n{author} traded {item} to "
                                        "{buyer} for {asking} {currency_name}."
                                    ).format(
                                        author=self.escape(ctx.author.display_name),
                                        item=item,
                                        buyer=self.escape(buyer.display_name),
                                        asking=asking,
                                        currency_name=currency_name,
                                    ),
                                    lang="css",
                                )
                            )
                        )
                        await self._clear_react(trade_msg)
                    else:
                        await trade_msg.edit(
                            content=_(
                                "**{buyer}**, you do not have enough {currency_name}."
                            ).format(
                                buyer=self.escape(buyer.display_name), currency_name=currency_name
                            )
                        )
                except discord.errors.NotFound:
                    pass
            else:
                with contextlib.suppress(discord.HTTPException):
                    await trade_msg.delete()

    @commands.group(aliases=["loadouts"])
    async def loadout(self, ctx: Context):
        """Setup various adventure settings."""

    @loadout.command(name="save")
    async def save_loadout(self, ctx: Context, name: str):
        """Save your current equipment as a loadout."""
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        name = name.lower()
        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if name in c.loadouts:
            await smart_embed(
                ctx,
                _("{author}, you already have a loadout named {name}.").format(
                    author=self.escape(ctx.author.display_name), name=name
                ),
            )
            return
        else:
            async with self.get_lock(c.user):
                try:
                    c = await Character.from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                loadout = await Character.save_loadout(c)
                c.loadouts[name] = loadout
                await self.config.user(ctx.author).set(c.to_json())
            await smart_embed(
                ctx,
                _("**{author}**, your current equipment has been saved to {name}.").format(
                    author=self.escape(ctx.author.display_name), name=name
                ),
            )

    @commands.guild_only()
    @commands.command()
    async def rebirth(self, ctx: Context):
        """Resets all your character data and increases your rebirths by 1."""
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx, _("You tried to rebirth but the monster ahead did not allow you to do so")
            )
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))

        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return

        if c.lvl < c.maxlevel:
            return await smart_embed(
                ctx, _("You need to be Level `{c.maxlevel}` to rebirth").format(c=c)
            )
        rebirthcost = 1000 * c.rebirths
        has_fund = await has_funds(ctx.author, rebirthcost)
        if not has_fund:
            currency_name = await bank.get_currency_name(ctx.guild)
            return await smart_embed(
                ctx,
                _("You need more {currency_name} to be able to rebirth").format(
                    currency_name=currency_name
                ),
            )
        open_msg = await smart_embed(
            ctx,
            _(
                "Note this will take all your money and items "
                "(except Legendary for 3 rebirths and Set items) "
                "and set you back to level 1 (keeping your current class), "
                "in turn it will give you stats bonuses and higher chance at better items as "
                "well as the ability to convert chests after the second rebirth"
            ),
        )
        start_adding_reactions(open_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(open_msg, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
        except asyncio.TimeoutError:
            await self._clear_react(open_msg)
            return await smart_embed(ctx, "I can't wait forever")
        else:
            if not pred.result:
                await open_msg.edit(
                    content=box(
                        _("{c} decided not to rebirth.").format(
                            c=self.escape(ctx.author.display_name)
                        ),
                        lang="css",
                    )
                )
                return await self._clear_react(open_msg)

            async with self.get_lock(ctx.author):
                try:
                    c = await Character.from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                if c.lvl < c.maxlevel:
                    return await smart_embed(
                        ctx, _("You need to be Level `{c.maxlevel}` to rebirth").format(c=c)
                    )
                bal = await bank.get_balance(ctx.author)
                if bal >= 1000:
                    withdraw = bal - 1000
                    await bank.withdraw_credits(ctx.author, withdraw)
                else:
                    withdraw = bal
                    await bank.set_balance(ctx.author, 0)

                await open_msg.edit(
                    content=(
                        box(
                            _("{c} congratulations with your rebirth.\nYou paid {bal}").format(
                                c=self.escape(ctx.author.display_name),
                                bal=humanize_number(withdraw),
                            ),
                            lang="css",
                        )
                    )
                )
                await self.config.user(ctx.author).set(await c.rebirth())

    @commands.is_owner()
    @commands.command()
    async def devrebirth(
        self,
        ctx: Context,
        rebirth_level: int = 1,
        character_level: int = 1,
        user: discord.Member = None,
    ):
        """Set a users rebith level."""
        target = user or ctx.author
        async with self.get_lock(target):
            try:
                c = await Character.from_json(self.config, target)
            except Exception:
                log.exception("Error with the new character sheet")
                return

            bal = await bank.get_balance(target)
            if bal >= 1000:
                withdraw = bal - 1000
                await bank.withdraw_credits(target, withdraw)
            else:
                withdraw = bal
                await bank.set_balance(target, 0)

            await ctx.send(
                content=(
                    box(
                        _("{c} congratulations with your rebirth.\nYou paid {bal}").format(
                            c=self.escape(target.display_name), bal=humanize_number(withdraw)
                        ),
                        lang="css",
                    )
                )
            )
            character_data = await c.rebirth(dev_val=rebirth_level)
            character_data["lvl"] = character_level
            await self.config.user(ctx.author).set(character_data)
        await ctx.tick()

    @commands.is_owner()
    @commands.command()
    async def devreset(self, ctx: commands.Context, user: discord.Member = None):
        """Reset the skill cooldown for this user."""
        target = user or ctx.author
        async with self.get_lock(target):
            try:
                c = await Character.from_json(self.config, target)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            c.heroclass["ability"] = False
            c.heroclass["cooldown"] = 0
            if "catch_cooldown" in c.heroclass:
                c.heroclass["catch_cooldown"] = 0
            await self.config.user(user).set(c.to_json())
        await ctx.tick()

    @loadout.command(name="delete", aliases=["del", "rem", "remove"])
    async def remove_loadout(self, ctx: Context, name: str):
        """Delete a saved loadout."""
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        name = name.lower()
        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if name not in c.loadouts:
            await smart_embed(
                ctx,
                _("**{author}**, you don't have a loadout named {name}.").format(
                    author=self.escape(ctx.author.display_name), name=name
                ),
            )
            return
        else:
            async with self.get_lock(c.user):
                try:
                    c = await Character.from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                del c.loadouts[name]
                await self.config.user(ctx.author).set(c.to_json())
            await smart_embed(
                ctx,
                _("**{author}**, loadout {name} has been deleted.").format(
                    author=self.escape(ctx.author.display_name), name=name
                ),
            )

    @loadout.command(name="show")
    async def show_loadout(self, ctx: Context, name: str = None):
        """Show saved loadouts."""
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if not c.loadouts:
            await smart_embed(
                ctx,
                _("**{author}**, you don't have any loadouts saved.").format(
                    author=self.escape(ctx.author.display_name)
                ),
            )
            return
        if name is not None and name.lower() not in c.loadouts:
            await smart_embed(
                ctx,
                _("**{author}**, you don't have a loadout named {name}.").format(
                    author=self.escape(ctx.author.display_name), name=name
                ),
            )
            return
        else:
            msg_list = []
            index = 0
            count = 0
            for l_name, loadout in c.loadouts.items():
                if name and name.lower() == l_name:
                    index = count
                stats = await self._build_loadout_display({"items": loadout})
                msg = _("[{name} Loadout for {author}]\n\n{stats}").format(
                    name=l_name, author=self.escape(ctx.author.display_name), stats=stats
                )
                msg_list.append(box(msg, lang="css"))
                count += 1
            await menu(ctx, msg_list, DEFAULT_CONTROLS, page=index)

    @loadout.command(name="equip", aliases=["load"])
    @commands.cooldown(rate=1, per=600, type=commands.BucketType.user)
    async def equip_loadout(self, ctx: Context, name: str):
        """Equip a saved loadout."""
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _(
                    "You tried to magically equipping multiple items at once, but the monster ahead nearly killed you."
                ),
            )
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        name = name.lower()
        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if name not in c.loadouts:
            ctx.command.reset_cooldown(ctx)
            await smart_embed(
                ctx,
                _("**{author}**, you don't have a loadout named {name}.").format(
                    author=self.escape(ctx.author.display_name), name=name
                ),
            )
            return
        else:
            async with self.get_lock(c.user):
                try:
                    c = await Character.from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                c = await c.equip_loadout(name)
                current_stats = box(
                    _(
                        "{author}'s new stats: "
                        "Attack: {stat_att} [{skill_att}], "
                        "Intelligence: {stat_int} [{skill_int}], "
                        "Diplomacy: {stat_cha} [{skill_cha}], "
                        "Dexterity: {stat_dex}, "
                        "Luck: {stat_luck}."
                    ).format(
                        author=self.escape(ctx.author.display_name),
                        stat_att=c.get_stat_value("att"),
                        skill_att=c.skill["att"],
                        stat_int=c.get_stat_value("int"),
                        skill_int=c.skill["int"],
                        stat_cha=c.get_stat_value("cha"),
                        skill_cha=c.skill["cha"],
                        stat_dex=c.get_stat_value("dex"),
                        stat_luck=c.get_stat_value("luck"),
                    ),
                    lang="css",
                )
                await ctx.send(current_stats)
                await self.config.user(ctx.author).set(c.to_json())
        return

    @commands.group()
    @commands.guild_only()
    async def adventureset(self, ctx: Context):
        """Setup various adventure settings."""

    @adventureset.command()
    @checks.admin_or_permissions(administrator=True)
    async def cartroom(self, ctx: Context, room: discord.TextChannel = None):
        """Set the room to show the cart in."""
        if room is None:
            return await smart_embed(
                ctx, _("Done, carts will now show in the room they are triggered in")
            )

        await self.config.guild(ctx.guild).cartroom.set(room.id)
        await smart_embed(ctx, _("Done, carts will now show in {room.mention}").format(room=room))

    @adventureset.command()
    @checks.is_owner()
    async def restrict(self, ctx: Context):
        """[Owner] Set whether or not adventurers are restricted to one adventure at a time."""
        toggle = await self.config.restrict()
        await self.config.restrict.set(not toggle)
        await smart_embed(
            ctx, _("Adventurers restricted to one adventure at a time: {}").format(not toggle)
        )

    @adventureset.command(name="advcooldown", hidden=True)
    @checks.guildowner()
    @commands.guild_only()
    async def advcooldown(self, ctx: Context, *, time_in_seconds: int):
        """Changes the adventure cooldown.

        Default is 120 seconds.
        """
        if time_in_seconds < 30:
            return await smart_embed(ctx, _("Cooldown cannot be set to less than 30 seconds"))

        await self.config.guild(ctx.guild).cooldown_timer_manual.set(time_in_seconds)
        await smart_embed(
            ctx, _("Adventure cooldown set to {cooldown} seconds").format(cooldown=time_in_seconds)
        )

    @adventureset.command()
    @checks.admin_or_permissions(administrator=True)
    async def version(self, ctx: Context):
        """Display the version of adventure being used."""
        await ctx.send(box(_("Adventure version: {}").format(self.__version__)))

    @adventureset.command()
    @checks.admin_or_permissions(administrator=True)
    async def god(self, ctx: Context, *, name):
        """[Admin] Set the server's name of the god."""
        await self.config.guild(ctx.guild).god_name.set(name)
        await ctx.tick()

    @adventureset.command()
    @checks.is_owner()
    async def globalgod(self, ctx: Context, *, name):
        """[Owner] Set the default name of the god."""
        await self.config.god_name.set(name)
        await ctx.tick()

    @adventureset.command(aliases=["embed"])
    @checks.admin_or_permissions(administrator=True)
    async def embeds(self, ctx: Context):
        """[Admin] Set whether or not to use embeds for the adventure game."""
        toggle = await self.config.guild(ctx.guild).embed()
        await self.config.guild(ctx.guild).embed.set(not toggle)
        await smart_embed(ctx, _("Embeds: {}").format(not toggle))

    @adventureset.command(aliases=["chests"])
    @checks.is_owner()
    async def cartchests(self, ctx: Context):
        """[Admin] Set whether or not to sell chests in the cart."""
        toggle = await self.config.enable_chests()
        await self.config.enable_chests.set(not toggle)
        await smart_embed(ctx, _("Carts can sell chests: {}").format(not toggle))

    @adventureset.command()
    @checks.admin_or_permissions(administrator=True)
    async def cartname(self, ctx: Context, *, name):
        """[Admin] Set the server's name of the cart."""
        await self.config.guild(ctx.guild).cart_name.set(name)
        await ctx.tick()

    @adventureset.command()
    @checks.admin_or_permissions(administrator=True)
    async def carttime(self, ctx: Context, *, time: str):
        """[Admin] Set the cooldown of the cart."""
        time_delta = parse_timedelta(time)
        if time_delta is None:
            return await smart_embed(
                ctx, _("You must supply a amount and time unit like `120 seconds`.")
            )
        if time_delta.total_seconds() < 600:
            cartname = await self.config.guild(ctx.guild).cart_name()
            if not cartname:
                cartname = await self.config.cart_name()
            return await smart_embed(
                ctx, _("{} doesn't have the energy to return that often.").format(cartname)
            )
        await self.config.guild(ctx.guild).cart_timeout.set(time_delta.seconds)
        await ctx.tick()

    @adventureset.command(name="clear")
    @checks.is_owner()
    async def clear_user(self, ctx: Context, *, user: discord.User):
        """Lets you clear a users entire character sheet."""
        await self.config.user(user).clear()
        await smart_embed(ctx, _("{user}'s character sheet has been erased.").format(user=user))

    @adventureset.command(name="remove")
    @checks.is_owner()
    async def remove_item(self, ctx: Context, user: discord.Member, *, full_item_name: str):
        """Lets you remove an item from a user.

        Use the full name of the item including the rarity characters like . or []  or {}.
        """
        async with self.get_lock(user):
            item = None
            try:
                c = await Character.from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            for slot in ORDER:
                if slot == "two handed":
                    continue
                equipped_item = getattr(c, slot)
                if equipped_item and equipped_item.name.lower() == full_item_name.lower():
                    item = equipped_item
            if item:
                with contextlib.suppress(Exception):
                    await c.unequip_item(item)
            else:
                try:
                    item = c.backpack[full_item_name]
                except KeyError:
                    return await smart_embed(
                        ctx, _("{} does not have an item named `{}`.").format(user, full_item_name)
                    )
            with contextlib.suppress(KeyError):
                del c.backpack[item.name]
            await self.config.user(user).set(c.to_json())
        await ctx.send(
            _("{item} removed from {user}.").format(item=box(str(item), lang="css"), user=user)
        )

    @adventureset.command()
    @checks.is_owner()
    async def globalcartname(self, ctx: Context, *, name):
        """[Owner] Set the default name of the cart."""
        await self.config.cart_name.set(name)
        await ctx.tick()

    @adventureset.command()
    @checks.is_owner()
    async def theme(self, ctx: Context, *, theme):
        """Change the theme for adventure."""
        if theme == "default":
            await self.config.theme.set("default")
            await smart_embed(ctx, _("Going back to the default theme."))
            await self.initialize()
            return
        if theme not in os.listdir(cog_data_path(self)):
            await smart_embed(ctx, _("That theme pack does not exist!"))
            return
        good_files = [
            "attribs.json",
            "locations.json",
            "as_monsters.json",
            "monsters.json",
            "pets.json",
            "raisins.json",
            "threatee.json",
            "tr_common.json",
            "tr_epic.json",
            "tr_rare.json",
            "tr_legendary.json",
            "tr_set.json",
        ]
        missing_files = set(good_files).difference(os.listdir(cog_data_path(self) / theme))

        if missing_files:
            await smart_embed(
                ctx,
                _("That theme pack is missing the following files {}").format(
                    humanize_list(missing_files)
                ),
            )
            return
        else:
            await self.config.theme.set(theme)
            await ctx.tick()
        await self.initialize()

    @adventureset.command()
    @checks.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def cart(self, ctx: Context, *, channel: discord.TextChannel = None):
        """[Admin] Add or remove a text channel that the Trader cart can appear in.

        If the channel is already in the list, it will be removed. Use `[p]adventureset cart` with
        no arguments to show the channel list.
        """

        channel_list = await self.config.guild(ctx.guild).cart_channels()
        if not channel_list:
            channel_list = []
        if channel is None:
            msg = _("Active Cart Channels:\n")
            if not channel_list:
                msg += _("None.")
            else:
                name_list = []
                for chan_id in channel_list:
                    name_list.append(self.bot.get_channel(chan_id))
                msg += "\n".join(chan.name for chan in name_list)
            return await ctx.send(box(msg))
        elif channel.id in channel_list:
            new_channels = channel_list.remove(channel.id)
            await smart_embed(
                ctx,
                _("The {} channel has been removed from the cart delivery list.").format(channel),
            )
            return await self.config.guild(ctx.guild).cart_channels.set(new_channels)
        else:
            channel_list.append(channel.id)
            await smart_embed(
                ctx, _("The {} channel has been added to the cart delivery list.").format(channel)
            )
            await self.config.guild(ctx.guild).cart_channels.set(channel_list)

    @commands.command()
    @commands.cooldown(rate=1, per=4, type=commands.BucketType.guild)
    async def convert(self, ctx: Context, box_rarity: str, amount: int = 1):
        """Convert normal, rare or epic chests.

        Trade 20 normal chests for 1 rare chest.
        Trade 20 rare chests for 1 epic chest.
        Trade 50 epic chests for 1 legendary chest
        """

        # Thanks to flare#0001 for the idea and writing the first instance of this
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx, _("You tried to converting some chets but the magician is back in town.")
            )
        normalcost = 20
        rarecost = 20
        epiccost = 50
        rebirth_normal = 2
        rebirth_rare = 30
        rebirth_epic = 50
        if amount < 1:
            return await smart_embed(ctx, _("Nice try :smirk:"))
        if amount > 1:
            plural = "s"
        else:
            plural = ""
        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(self.config, ctx.author)
            except Exception:
                log.exception("Error with the new character sheet")
                return

            if box_rarity.lower() == "rare" and c.rebirths < rebirth_rare:
                await smart_embed(
                    ctx,
                    (
                        "**{}**, You need to have {} or more rebirth to convert epic treasure chests."
                    ).format(self.escape(ctx.author.display_name), rebirth_rare),
                )
            elif box_rarity.lower() == "epic" and c.rebirths < rebirth_epic:
                await smart_embed(
                    ctx,
                    (
                        "**{}**, You need to have {} or more rebirth to convert epic treasure chests."
                    ).format(self.escape(ctx.author.display_name), rebirth_epic),
                )
            elif c.rebirths < 2:
                return await smart_embed(
                    ctx,
                    _("**{c}**, you need to 3 rebirths to use this.").format(
                        c=self.escape(ctx.author.display_name)
                    ),
                )

            if box_rarity.lower() == "normal" and c.rebirths >= rebirth_normal:
                if c.treasure[0] >= (normalcost * amount):
                    c.treasure[0] -= normalcost * amount
                    c.treasure[1] += 1 * amount
                    await ctx.send(
                        box(
                            _(
                                "Successfully converted {converted} normal treasure "
                                "chests to {to} rare treasure chest{plur}.\n{author} "
                                "now owns {normal} normal, {rare} rare, {epic} epic, "
                                "{leg} legendary treasure chests and {set} set treasure chests."
                            ).format(
                                converted=humanize_number(normalcost * amount),
                                to=humanize_number(1 * amount),
                                plur=plural,
                                author=self.escape(ctx.author.display_name),
                                normal=c.treasure[0],
                                rare=c.treasure[1],
                                epic=c.treasure[2],
                                leg=c.treasure[3],
                                set=c.treasure[4],
                            ),
                            lang="css",
                        )
                    )
                    await self.config.user(ctx.author).set(c.to_json())
                else:
                    await smart_embed(
                        ctx,
                        _(
                            "**{author}**, you do not have {amount} "
                            "normal treasure chests to convert."
                        ).format(
                            author=self.escape(ctx.author.display_name),
                            amount=humanize_number(normalcost * amount),
                        ),
                    )
            elif box_rarity.lower() == "rare" and c.rebirths >= rebirth_rare:
                if c.treasure[1] >= (rarecost * amount):
                    c.treasure[1] -= rarecost * amount
                    c.treasure[2] += 1 * amount
                    await ctx.send(
                        box(
                            _(
                                "Successfully converted {converted} rare treasure "
                                "chests to {to} epic treasure chest{plur}. \n{author} "
                                "now owns {normal} normal, {rare} rare, {epic} epic, "
                                "{leg} legendary treasure chests and {set} set treasure chests."
                            ).format(
                                converted=humanize_number(rarecost * amount),
                                to=humanize_number(1 * amount),
                                plur=plural,
                                author=self.escape(ctx.author.display_name),
                                normal=c.treasure[0],
                                rare=c.treasure[1],
                                epic=c.treasure[2],
                                leg=c.treasure[3],
                                set=c.treasure[4],
                            ),
                            lang="css",
                        )
                    )
                    await self.config.user(ctx.author).set(c.to_json())
                else:
                    await smart_embed(
                        ctx,
                        _(
                            "{author}, you do not have {amount} "
                            "rare treasure chests to convert."
                        ).format(
                            author=ctx.author.mention, amount=humanize_number(rarecost * amount)
                        ),
                    )
            elif box_rarity.lower() == "epic" and c.rebirths >= rebirth_epic:
                if c.treasure[2] >= (epiccost * amount):
                    c.treasure[2] -= epiccost * amount
                    c.treasure[3] += 1 * amount
                    await ctx.send(
                        box(
                            _(
                                "Successfully converted {converted} epic treasure "
                                "chests to {to} legendary treasure chest{plur}. \n{author} "
                                "now owns {normal} normal, {rare} rare, {epic} epic, "
                                "{leg} legendary treasure chests and {set} set treasure chests."
                            ).format(
                                converted=humanize_number(epiccost * amount),
                                to=humanize_number(1 * amount),
                                plur=plural,
                                author=self.escape(ctx.author.display_name),
                                normal=c.treasure[0],
                                rare=c.treasure[1],
                                epic=c.treasure[2],
                                leg=c.treasure[3],
                                set=c.treasure[4],
                            ),
                            lang="css",
                        )
                    )
                    await self.config.user(ctx.author).set(c.to_json())
                else:
                    await smart_embed(
                        ctx,
                        _(
                            "**{author}**, you do not have {amount} "
                            "epic treasure chests to convert."
                        ).format(
                            author=self.escape(ctx.author.display_name),
                            amount=humanize_number(epiccost * amount),
                        ),
                    )
            else:
                await smart_embed(
                    ctx,
                    _(
                        "**{}**, please select between normal, rare or epic treasure chests to convert."
                    ).format(self.escape(ctx.author.display_name)),
                )

    @commands.command()
    async def equip(self, ctx: Context, *, item: ItemConverter):
        """This equips an item from your backpack.

        `[p]equip name of item`
        """
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _(
                    "You tried to equipping your items, but the monster ahead nearly decapitated you."
                ),
            )
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))

        await ctx.invoke(self.backpack_equip, equip_item=item)

    @commands.command()
    async def forge(self, ctx):
        """[Tinkerer Class Only]

        This allows a Tinkerer to forge two items into a device. (1h cooldown)
        """
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _("You tried to forging a mystic item.. but there no functional forges nearby."),
            )
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(self.config, ctx.author)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            if c.heroclass["name"] != "Tinkerer":
                return await smart_embed(
                    ctx,
                    _("**{}**, you need to be a Tinkerer to do this.").format(
                        self.escape(ctx.author.display_name)
                    ),
                )
            else:
                cooldown_time = max(900, (3600 - (c.luck - c.total_int) * 2))
                if "cooldown" not in c.heroclass:
                    c.heroclass["cooldown"] = cooldown_time + 1
                if not c.heroclass["cooldown"] + cooldown_time <= time.time():
                    cooldown_time = (c.heroclass["cooldown"]) + cooldown_time - time.time()
                    return await smart_embed(
                        ctx,
                        _("This command is on cooldown. Try again in {}").format(
                            humanize_timedelta(seconds=int(cooldown_time))
                            if cooldown_time >= 1
                            else _("1 second")
                        ),
                    )
                consumed = []
                forgeables = len(
                    [i for n, i in c.backpack.items() if i.rarity not in ["forged", "set"]]
                )
                if forgeables <= 1:
                    return await smart_embed(
                        ctx,
                        _(
                            "**{}**, you need at least two forgeable items in your backpack to forge."
                        ).format(self.escape(ctx.author.display_name)),
                    )
                forgeables = _(
                    "[{author}'s forgeables]\n{bc}\n"
                    "(Reply with the full or partial name "
                    "of item 1 to select for forging. Try to be specific.)"
                ).format(author=self.escape(ctx.author.display_name), bc=c.get_backpack(True))
                for page in pagify(forgeables, delims=["\n"], shorten_by=20):
                    await ctx.send(box(page, lang="css"))

                try:
                    reply = await ctx.bot.wait_for(
                        "message", check=MessagePredicate.same_context(user=ctx.author), timeout=30
                    )
                except asyncio.TimeoutError:
                    timeout_msg = _("I don't have all day you know, **{}**.").format(
                        self.escape(ctx.author.display_name)
                    )
                    return await ctx.send(timeout_msg)
                new_ctx = await self.bot.get_context(reply)
                item = await ItemConverter().convert(new_ctx, reply.content)
                if not item:
                    wrong_item = _(
                        "**{c}**, I could not find that item - check your spelling."
                    ).format(c=self.escape(ctx.author.display_name))
                    return await smart_embed(ctx, wrong_item)

                if item.rarity in ["forged", "set"]:
                    return await smart_embed(
                        ctx,
                        _("**{c}**, {item.rarity} items cannot be reforged.").format(
                            c=self.escape(ctx.author.display_name), item=item
                        ),
                    )
                consumed.append(item)
                if not consumed:
                    wrong_item = _(
                        "**{}**, I could not find that item - check your spelling."
                    ).format(self.escape(ctx.author.display_name))
                    return await smart_embed(ctx, wrong_item)
                forgeables = _(
                    "(Reply with the full or partial name "
                    "of item 2 to select for forging. Try to be specific.)"
                )
                await ctx.send(box(forgeables, lang="css"))
                try:
                    reply = await ctx.bot.wait_for(
                        "message", check=MessagePredicate.same_context(user=ctx.author), timeout=30
                    )
                except asyncio.TimeoutError:
                    timeout_msg = _("I don't have all day you know, **{}**.").format(
                        self.escape(ctx.author.display_name)
                    )
                    return await smart_embed(ctx, timeout_msg)
                new_ctx = await self.bot.get_context(reply)
                item = await ItemConverter().convert(new_ctx, reply.content)
                if item.rarity in ["forged", "set"]:
                    return await smart_embed(
                        ctx,
                        _("**{c}**, {item.rarity} items cannot be reforged.").format(
                            c=self.escape(ctx.author.display_name), item=item
                        ),
                    )
                consumed.append(item)
                if len(consumed) < 2:
                    return await smart_embed(
                        ctx,
                        _("**{}**, I could not find that item - check your spelling.").format(
                            self.escape(ctx.author.display_name)
                        ),
                    )

                newitem = await self._to_forge(ctx, consumed, c)
                for x in consumed:
                    c.backpack[x.name].owned -= 1
                    if c.backpack[x.name].owned <= 0:
                        del c.backpack[x.name]
                    await self.config.user(ctx.author).set(c.to_json())
                # save so the items are eaten up already
                for item in c.get_current_equipment():
                    if item.rarity == "forged":
                        c = await c.unequip_item(item)
                lookup = list(i for n, i in c.backpack.items() if i.rarity == "forged")
                if len(lookup) > 0:
                    forge_str = box(
                        _(
                            "{author}, you already have a device. "
                            "Do you want to replace {replace}?"
                        ).format(
                            author=self.escape(ctx.author.display_name),
                            replace=", ".join([str(x) for x in lookup]),
                        ),
                        lang="css",
                    )
                    forge_msg = await ctx.send(forge_str)
                    start_adding_reactions(forge_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
                    pred = ReactionPredicate.yes_or_no(forge_msg, ctx.author)
                    try:
                        await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
                    except asyncio.TimeoutError:
                        await self._clear_react(forge_msg)
                        return
                    with contextlib.suppress(discord.HTTPException):
                        await forge_msg.delete()
                    if pred.result:  # user reacted with Yes.
                        created_item = box(
                            _(
                                "{author}, your new {newitem} consumed {lk} "
                                "and is now lurking in your backpack."
                            ).format(
                                author=self.escape(ctx.author.display_name),
                                newitem=newitem,
                                lk=", ".join([str(x) for x in lookup]),
                            ),
                            lang="css",
                        )
                        for item in lookup:
                            del c.backpack[item.name]
                        await ctx.send(created_item)
                        c.backpack[newitem.name] = newitem
                        await self.config.user(ctx.author).set(c.to_json())
                    else:
                        mad_forge = box(
                            _(
                                "{author}, {newitem} got mad at your rejection and blew itself up."
                            ).format(author=self.escape(ctx.author.display_name), newitem=newitem),
                            lang="css",
                        )
                        return await ctx.send(mad_forge)
                else:
                    c.backpack[newitem.name] = newitem
                    await self.config.user(ctx.author).set(c.to_json())
                    forged_item = box(
                        _("{author}, your new {newitem} is lurking in your backpack.").format(
                            author=self.escape(ctx.author.display_name), newitem=newitem
                        ),
                        lang="css",
                    )
                    await ctx.send(forged_item)

    async def _to_forge(self, ctx: Context, consumed, character):
        item1 = consumed[0]
        item2 = consumed[1]

        roll = random.randint(1, 20) + (character.total_int // 50) + (character.luck // 20)
        if roll == 1:
            modifier = 0.4
        elif 1 < roll <= 6:
            modifier = 0.5
        elif 6 < roll <= 8:
            modifier = 0.6
        elif 8 < roll <= 10:
            modifier = 0.7
        elif 10 < roll <= 13:
            modifier = 0.8
        elif 13 < roll <= 16:
            modifier = 0.9
        elif 16 < roll <= 17:
            modifier = 1.0
        elif 17 < roll <= 19:
            modifier = 1.1
        elif roll == 20:
            modifier = 1.2
        elif 21 <= roll <= 30:
            modifier = 1.5
        elif roll > 30:
            modifier = 2.0
        else:
            modifier = 1
        newatt = round((int(item1.att) + int(item2.att)) * modifier)
        newdip = round((int(item1.cha) + int(item2.cha)) * modifier)
        newint = round((int(item1.int) + int(item2.int)) * modifier)
        newdex = round((int(item1.dex) + int(item2.dex)) * modifier)
        newluck = round((int(item1.luck) + int(item2.luck)) * modifier)
        newslot = random.choice([item1.slot, item2.slot])
        if len(newslot) == 2:  # two handed weapons add their bonuses twice
            hand = "two handed"
        else:
            if newslot[0] == "right" or newslot[0] == "left":
                hand = newslot[0] + " handed"
            else:
                hand = newslot[0] + " slot"
        if len(newslot) == 2:
            two_handed_msg = box(
                _(
                    "{author}, your forging roll was {dice}({roll}).\n"
                    "The device you tinkered will have "
                    "(ATT {new_att} | "
                    "CHA {new_cha} | "
                    "INT {new_int} | "
                    "DEX {new_dex} | "
                    "LUCK {new_luck})"
                    " and be {hand}."
                ).format(
                    author=self.escape(ctx.author.display_name),
                    roll=roll,
                    dice=self.emojis.dice,
                    new_att=(newatt * 2),
                    new_cha=(newdip * 2),
                    new_int=(newint * 2),
                    new_dex=(newdex * 2),
                    new_luck=(newluck * 2),
                    hand=hand,
                ),
                lang="css",
            )
            await ctx.send(two_handed_msg)
        else:
            reg_item = box(
                _(
                    "{author}, your forging roll was {dice}({roll}).\n"
                    "The device you tinkered will have "
                    "(ATT {new_att} | "
                    "CHA {new_dip} | "
                    "INT {new_int} | "
                    "DEX {new_dex} | "
                    "LUCK {new_luck})"
                    " and be {hand}."
                ).format(
                    author=self.escape(ctx.author.display_name),
                    roll=roll,
                    dice=self.emojis.dice,
                    new_att=newatt,
                    new_dip=newdip,
                    new_int=newint,
                    new_dex=newdex,
                    new_luck=newluck,
                    hand=hand,
                ),
                lang="css",
            )
            await ctx.send(reg_item)
        get_name = _(
            "**{}**, please respond with "
            "a name for your creation within 30s.\n"
            "(You will not be able to change it afterwards. 40 characters maximum.)"
        ).format(self.escape(ctx.author.display_name))
        await smart_embed(ctx, get_name)
        reply = None
        try:
            reply = await ctx.bot.wait_for(
                "message", check=MessagePredicate.same_context(user=ctx.author), timeout=30
            )
        except asyncio.TimeoutError:
            name = _("Unnamed Artifact")
        if reply is None:
            name = _("Unnamed Artifact")
        else:
            if hasattr(reply, "content"):
                if len(reply.content) > 40:
                    name = _("Long-winded Artifact")
                else:
                    name = reply.content.lower()
        item = {
            name: {
                "slot": newslot,
                "att": newatt,
                "cha": newdip,
                "int": newint,
                "dex": newdex,
                "luck": newluck,
                "rarity": "forged",
            }
        }
        item = Item.from_json(item)
        return item

    @commands.group()
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def give(self, ctx: Context):
        """[Admin] Commands to add things to players' inventories."""

    @give.command(name="funds")
    @check_global_setting_admin()
    async def _give_funds(self, ctx: Context, amount: int = 1, *, to: discord.Member = None):
        """[Admin] Adds currency to a specified member's balance.

        `[p]give funds 10 @Elder Aramis` will create 10 currency and add to Elder Aramis' total.
        """
        if to is None:
            return await smart_embed(
                ctx,
                _("You need to specify a receiving member, **{}**.").format(
                    self.escape(ctx.author.display_name)
                ),
            )
        to_fund = discord.utils.find(lambda m: m.name == to.name, ctx.guild.members)
        if not to_fund:
            return await smart_embed(
                ctx,
                _(
                    "I could not find that user, **{}**. Try using their full Discord name (name#0000)."
                ).format(self.escape(ctx.author.display_name)),
            )
        amount = max(amount, 0)
        try:
            bal = await bank.deposit_credits(to, amount)
        except BalanceTooHigh:
            bal = await get_max_balance(ctx.guild)
        currency = await bank.get_currency_name(ctx.guild)
        if str(currency).startswith("<:"):
            currency = "credits"
        await ctx.send(
            box(
                _(
                    "{author}, you funded {amount} {currency}. {to} now has {bal} {currency}."
                ).format(
                    author=self.escape(ctx.author.display_name),
                    amount=humanize_number(amount),
                    currency=currency,
                    to=self.escape(to.display_name),
                    bal=bal,
                ),
                lang="css",
            )
        )

    @give.command(name="item")
    async def _give_item(
        self, ctx: Context, user: discord.Member, item_name: str, *, stats: Stats
    ):
        """[Admin] Adds a custom item to a specified member.

        Item names containing spaces must be enclosed in double quotes. `[p]give item @locastan
        "fine dagger" 1 att 1 charisma rare twohanded` will give a two handed .fine_dagger with 1
        attack and 1 charisma to locastan. if a stat is not specified it will default to 0, order
        does not matter. available stats are attack(att), charisma(diplo) or charisma(cha),
        intelligence(int), dexterity(dex), and luck.
        """
        if item_name.isnumeric():
            return await smart_embed(ctx, _("Item names cannot be numbers."))
        item_name = re.sub(r"[^\w]", "", item_name)
        if user is None:
            user = ctx.author
        new_item = {item_name: stats}
        item = Item.from_json(new_item)
        async with self.get_lock(user):
            try:
                c = await Character.from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            await c.add_to_backpack(item)
            await self.config.user(user).set(c.to_json())
        await ctx.send(
            box(
                _(
                    "An item named {item} has been created and placed in {author}'s backpack."
                ).format(item=item, author=self.escape(user.display_name)),
                lang="css",
            )
        )

    @give.command(name="loot")
    async def _give_loot(
        self, ctx: Context, loot_type: str, user: discord.Member = None, number: int = 1
    ):
        """[Admin] This rewards a treasure chest to a specified member.

        `[p]give loot normal @locastan 5` will give locastan 5 normal chests. Loot types: normal,
        rare, epic, legendary.
        """

        if user is None:
            user = ctx.author
        loot_types = ["normal", "rare", "epic", "legendary", "set"]
        if loot_type not in loot_types:
            return await smart_embed(
                ctx,
                (
                    "Valid loot types: `normal`, `rare`, `epic` or `legendary`: "
                    "ex. `{}give loot normal @locastan` "
                ).format(ctx.prefix),
            )
        if loot_type in ["legendary", "set"] and not await ctx.bot.is_owner(ctx.author):
            return await smart_embed(ctx, _("You are not worthy to award legendary loot."))
        async with self.get_lock(user):
            try:
                c = await Character.from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            if loot_type == "rare":
                c.treasure[1] += number
            elif loot_type == "epic":
                c.treasure[2] += number
            elif loot_type == "legendary":
                c.treasure[3] += number
            elif loot_type == "set":
                c.treasure[4] += number
            else:
                c.treasure[0] += number
            await self.config.user(user).set(c.to_json())
            await ctx.send(
                box(
                    _(
                        "{author} now owns {normal} normal, "
                        "{rare} rare, {epic} epic, "
                        "{leg} legendary and {set} set treasure chests."
                    ).format(
                        author=self.escape(user.display_name),
                        normal=str(c.treasure[0]),
                        rare=str(c.treasure[1]),
                        epic=str(c.treasure[2]),
                        leg=str(c.treasure[3]),
                        set=str(c.treasure[4]),
                    ),
                    lang="css",
                )
            )

    @commands.command()
    @commands.cooldown(rate=1, per=600, type=commands.BucketType.user)
    async def heroclass(self, ctx: Context, clz: str = None, action: str = None):
        """This allows you to select a class if you are Level 10 or above.

        For information on class use: `[p]heroclass "classname" info`.
        """
        if self.in_adventure(ctx):
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(ctx, _("The class hall is back in town."))
        if not await self.allow_in_dm(ctx):
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))

        classes = {
            "Wizard": {
                "name": _("Wizard"),
                "ability": False,
                "desc": _(
                    "Wizards have the option to focus and add large bonuses to their magic, "
                    "but their focus can sometimes go astray...\nUse the focus command when attacking in an adventure."
                ),
                "cooldown": time.time(),
            },
            "Tinkerer": {
                "name": _("Tinkerer"),
                "ability": False,
                "desc": _(
                    "Tinkerers can forge two different items into a device "
                    "bound to their very soul.\nUse the forge command."
                ),
                "cooldown": time.time(),
            },
            "Berserker": {
                "name": _("Berserker"),
                "ability": False,
                "desc": _(
                    "Berserkers have the option to rage and add big bonuses to attacks, "
                    "but fumbles hurt.\nUse the rage command when attacking in an adventure."
                ),
                "cooldown": time.time(),
            },
            "Cleric": {
                "name": _("Cleric"),
                "ability": False,
                "desc": _(
                    "Clerics can bless the entire group when praying.\n"
                    "Use the bless command when fighting in an adventure."
                ),
                "cooldown": time.time(),
            },
            "Ranger": {
                "name": _("Ranger"),
                "ability": False,
                "desc": _(
                    "Rangers can gain a special pet, which can find items and give "
                    "reward bonuses.\nUse the pet command to see pet options."
                ),
                "pet": {},
                "cooldown": time.time(),
                "catch_cooldown": time.time(),
            },
            "Bard": {
                "name": _("Bard"),
                "ability": False,
                "desc": _(
                    "Bards can perform to aid their comrades in diplomacy.\n"
                    "Use the music command when being diplomatic in an adventure."
                ),
                "cooldown": time.time(),
            },
        }

        if clz is None:
            ctx.command.reset_cooldown(ctx)
            await smart_embed(
                ctx,
                _(
                    "So you feel like taking on a class, **{author}**?\n"
                    "Available classes are: Tinkerer, Berserker, Wizard, Cleric, Ranger and Bard.\n"
                    "Use `{prefix}heroclass name-of-class` to choose one."
                ).format(author=self.escape(ctx.author.display_name), prefix=ctx.prefix),
            )

        else:
            clz = clz.title()
            if clz in classes and action == "info":
                ctx.command.reset_cooldown(ctx)
                return await smart_embed(ctx, f"{classes[clz]['desc']}")
            elif clz not in classes:
                ctx.command.reset_cooldown(ctx)
                return await smart_embed(
                    ctx, _("{} may be a class somewhere, but not on my watch.").format(clz)
                )
            elif clz in classes and action is None:
                bal = await bank.get_balance(ctx.author)
                currency_name = await bank.get_currency_name(ctx.guild)
                if str(currency_name).startswith("<"):
                    currency_name = "credits"
                spend = round(bal * 0.2)
                try:
                    c = await Character.from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                if c.heroclass["name"] == clz:
                    return await smart_embed(ctx, _("You already are a {}.").format(clz))
                class_msg = await ctx.send(
                    box(
                        _(
                            "This will cost {spend} {currency_name}. "
                            "Do you want to continue, {author}?"
                        ).format(
                            spend=humanize_number(spend),
                            currency_name=currency_name,
                            author=self.escape(ctx.author.display_name),
                        ),
                        lang="css",
                    )
                )
                broke = box(
                    _("You don't have enough {currency_name} to train to be a {clz}.").format(
                        currency_name=currency_name, clz=clz.title()
                    ),
                    lang="css",
                )
                start_adding_reactions(class_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
                pred = ReactionPredicate.yes_or_no(class_msg, ctx.author)
                try:
                    await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
                except asyncio.TimeoutError:
                    await self._clear_react(class_msg)
                    ctx.command.reset_cooldown(ctx)
                    return

                if not pred.result:
                    await class_msg.edit(
                        content=box(
                            _("{author} decided to continue being a {h_class}.").format(
                                author=self.escape(ctx.author.display_name),
                                h_class=c.heroclass["name"],
                            ),
                            lang="css",
                        )
                    )
                    ctx.command.reset_cooldown(ctx)
                    return await self._clear_react(class_msg)
                if bal < spend:
                    await class_msg.edit(content=broke)
                    ctx.command.reset_cooldown(ctx)
                    return await self._clear_react(class_msg)
                if not await bank.can_spend(ctx.author, spend):
                    return await class_msg.edit(content=broke)

                async with self.get_lock(ctx.author):
                    try:
                        c = await Character.from_json(self.config, ctx.author)
                    except Exception:
                        log.exception("Error with the new character sheet")
                        return
                    now_class_msg = _(
                        "Congratulations, **{author}**.\nYou are now a {clz}."
                    ).format(author=self.escape(ctx.author.display_name), clz=classes[clz]["name"])
                    if c.lvl >= 10:
                        if c.heroclass["name"] == "Tinkerer" or c.heroclass["name"] == "Ranger":
                            if c.heroclass["name"] == "Tinkerer":
                                await self._clear_react(class_msg)
                                await class_msg.edit(
                                    content=box(
                                        _(
                                            "{}, you will lose your forged "
                                            "device if you change your class.\nShall I proceed?"
                                        ).format(self.escape(ctx.author.display_name)),
                                        lang="css",
                                    )
                                )
                            else:
                                await self._clear_react(class_msg)
                                await class_msg.edit(
                                    content=box(
                                        _(
                                            "{}, you will lose your pet "
                                            "if you change your class.\nShall I proceed?"
                                        ).format(self.escape(ctx.author.display_name)),
                                        lang="css",
                                    )
                                )
                            start_adding_reactions(class_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
                            pred = ReactionPredicate.yes_or_no(class_msg, ctx.author)
                            try:
                                await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
                            except asyncio.TimeoutError:
                                await self._clear_react(class_msg)
                                ctx.command.reset_cooldown(ctx)
                                return
                            if pred.result:  # user reacted with Yes.
                                if c.heroclass["name"] == "Tinkerer":
                                    tinker_wep = []
                                    for item in c.get_current_equipment():
                                        if item.rarity == "forged":
                                            c = await c.unequip_item(item)
                                    for name, item in c.backpack.items():
                                        if item.rarity == "forged":
                                            tinker_wep.append(item)
                                    for item in tinker_wep:
                                        del c.backpack[item.name]
                                    await self.config.user(ctx.author).set(c.to_json())
                                    if tinker_wep:
                                        await class_msg.edit(
                                            content=box(
                                                _("{} has run off to find a new master.").format(
                                                    humanize_list(tinker_wep)
                                                ),
                                                lang="css",
                                            )
                                        )

                                else:
                                    c.heroclass["ability"] = False
                                    c.heroclass["pet"] = {}
                                    c.heroclass = classes[clz]

                                    await self.config.user(ctx.author).set(c.to_json())
                                    await self._clear_react(class_msg)
                                    await class_msg.edit(
                                        content=box(
                                            _("{} released their pet into the wild.\n").format(
                                                self.escape(ctx.author.display_name)
                                            ),
                                            lang="css",
                                        )
                                    )
                                await class_msg.edit(
                                    content=class_msg.content + box(now_class_msg, lang="css")
                                )
                            else:
                                ctx.command.reset_cooldown(ctx)
                                return
                        if c.skill["pool"] < 0:
                            c.skill["pool"] = 0
                        c.heroclass = classes[clz]
                        if c.heroclass["name"] == "Wizard":
                            c.heroclass["cooldown"] = (
                                max(300, (1200 - ((c.luck + c.total_int) * 2))) + time.time()
                            )
                        elif c.heroclass["name"] == "Ranger":
                            c.heroclass["cooldown"] = (
                                max(1800, (7200 - (c.luck * 2 + c.total_int * 2))) + time.time()
                            )
                            c.heroclass["catch_cooldown"] = (
                                max(600, (3600 - (c.luck * 2 + c.total_int * 2))) + time.time()
                            )
                        elif c.heroclass["name"] == "Berserker":
                            c.heroclass["cooldown"] = (
                                max(300, (1200 - ((c.luck + c.total_att) * 2))) + time.time()
                            )
                        elif c.heroclass["name"] == "Cleric":
                            c.heroclass["cooldown"] = (
                                max(300, (1200 - ((c.luck + c.total_int) * 2))) + time.time()
                            )
                        elif c.heroclass["name"] == "Bard":
                            c.heroclass["cooldown"] = (
                                max(300, (1200 - ((c.luck + c.total_cha) * 2))) + time.time()
                            )
                        elif c.heroclass["name"] == "Tinkerer":
                            c.heroclass["cooldown"] = (
                                max(900, (3600 - (c.luck - c.total_int) * 2)) + time.time()
                            )
                        await self.config.user(ctx.author).set(c.to_json())
                        await self._clear_react(class_msg)
                        await class_msg.edit(content=box(now_class_msg, lang="css"))
                        try:
                            await bank.withdraw_credits(ctx.author, spend)
                        except ValueError:
                            return await class_msg.edit(content=broke)
                    else:
                        ctx.command.reset_cooldown(ctx)
                        await smart_embed(
                            ctx,
                            _(
                                "**{}**, you need to be at least level 10 to choose a class."
                            ).format(self.escape(ctx.author.display_name)),
                        )

    @staticmethod
    def check_running_adventure(ctx):
        for guild_id, session in ctx.bot.get_cog("Adventure")._sessions.items():
            user_ids: list = []
            options = ["fight", "magic", "talk", "pray", "run"]
            for i in options:
                user_ids += [u.id for u in getattr(session, i)]
            if ctx.author.id in user_ids:
                return False
        return True

    @commands.command()
    @commands.cooldown(rate=1, per=4, type=commands.BucketType.user)
    async def loot(self, ctx: Context, box_type: str = None, number: int = 1):
        """This opens one of your precious treasure chests.

        Use the box rarity type with the command: normal, rare, epic, legendary or set.
        """
        if number > 100:
            return await smart_embed(ctx, _("Nice try :smirk:."),)
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _(
                    "You tried to opening a loot chest but then realise your left them all back at your inn."
                ),
            )
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if not box_type:
            return await ctx.send(
                box(
                    _(
                        "{author} owns {normal} normal, "
                        "{rare} rare, {epic} epic, {leg} legendary and {set} set chests."
                    ).format(
                        author=self.escape(ctx.author.display_name),
                        normal=str(c.treasure[0]),
                        rare=str(c.treasure[1]),
                        epic=str(c.treasure[2]),
                        leg=str(c.treasure[3]),
                        set=str(c.treasure[4]),
                    ),
                    lang="css",
                )
            )
        if box_type == "normal":
            redux = [1, 0, 0, 0, 0]
        elif box_type == "rare":
            redux = [0, 1, 0, 0, 0]
        elif box_type == "epic":
            redux = [0, 0, 1, 0, 0]
        elif box_type == "legendary":
            redux = [0, 0, 0, 1, 0]
        elif box_type == "set":
            redux = [0, 0, 0, 0, 1]
        else:
            return await smart_embed(
                ctx,
                _("There is talk of a {} treasure chest but nobody ever saw one.").format(
                    box_type
                ),
            )
        treasure = c.treasure[redux.index(1)]
        if treasure < 1 or treasure < number:
            await smart_embed(
                ctx,
                _("**{author}**, you do not have enough {box} treasure chest to open.").format(
                    author=self.escape(ctx.author.display_name), box=box_type
                ),
            )
        else:
            if number > 1:
                items = await self._open_chests(ctx, ctx.author, box_type, number, character=c)
                msg = _(
                    "{}, you've opened the following items:\n"
                    "( ATT | CHA | INT | DEX | LUCK ) | LEVEL REQ | LOOTED | SET (SET PIECES)"
                ).format(self.escape(ctx.author.display_name))
                rjust = max([len(str(i)) for i in items.values()])
                for item in items.values():
                    await asyncio.sleep(0)
                    settext = ""
                    att_space = " " if len(str(item.att)) == 1 else ""
                    cha_space = " " if len(str(item.cha)) == 1 else ""
                    int_space = " " if len(str(item.int)) == 1 else ""
                    dex_space = " " if len(str(item.dex)) == 1 else ""
                    luck_space = " " if len(str(item.luck)) == 1 else ""
                    owned = f" | {item.owned}"
                    if item.set:
                        settext += f" | Set `{item.set}` ({item.parts}pcs)"
                    msg += (
                        f"\n{str(item):<{rjust}} - "
                        f"({att_space}{item.att} |"
                        f"{cha_space}{item.cha} |"
                        f"{int_space}{item.int} |"
                        f"{dex_space}{item.dex} |"
                        f"{luck_space}{item.luck} )"
                        f" | Lv {equip_level(c, item):<3}"
                        f"{owned}{settext}"
                    )
                msgs = []
                for page in pagify(msg):
                    msgs.append(box(page, lang="css"))
            else:
                msgs = []
                await self._open_chest(
                    ctx, ctx.author, box_type, character=c
                )  # returns item and msg

            async with self.get_lock(ctx.author):
                # atomically save reduced loot count then lock again when saving inside
                # open chests
                c.treasure[redux.index(1)] -= number
                await self.config.user(ctx.author).set(c.to_json())
            if msgs:
                await menu(ctx, msgs, DEFAULT_CONTROLS)

    @commands.command(name="negaverse", aliases=["nv"])
    @commands.cooldown(rate=1, per=3600, type=commands.BucketType.user)
    @commands.guild_only()
    async def _negaverse(self, ctx: Context, offering: int = None):
        """This will send you to fight a nega-member!

        `[p]negaverse offering` 'offering' in this context is the amount of currency you are
        sacrificing for this fight.
        """
        if self.in_adventure(ctx):
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(
                ctx,
                _(
                    "You tried to teleport to another dimension but the monster ahead did not give you a chance."
                ),
            )
        bal = await bank.get_balance(ctx.author)
        currency_name = await bank.get_currency_name(ctx.guild)

        if offering is None:
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(
                ctx,
                _(
                    "**{author}**, you need to specify how many "
                    "{currency_name} you are willing to offer to the gods for your success."
                ).format(author=self.escape(ctx.author.display_name), currency_name=currency_name),
            )
        if offering <= 500 or bal <= 500:
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(ctx, _("The gods refuse your pitiful offering."))
        if offering > bal:
            offering = bal

        nv_msg = await ctx.send(
            _(
                "**{author}**, this will cost you at least {offer} {currency_name}.\n"
                "You currently have {bal}. Do you want to proceed?"
            ).format(
                author=self.escape(ctx.author.display_name),
                offer=humanize_number(offering),
                currency_name=currency_name,
                bal=humanize_number(bal),
            )
        )
        start_adding_reactions(nv_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
        pred = ReactionPredicate.yes_or_no(nv_msg, ctx.author)
        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
        except asyncio.TimeoutError:
            ctx.command.reset_cooldown(ctx)
            await self._clear_react(nv_msg)
            return
        if not pred.result:
            with contextlib.suppress(discord.HTTPException):
                ctx.command.reset_cooldown(ctx)
                await nv_msg.edit(
                    content=_("**{}** decides against visiting the negaverse... for now.").format(
                        self.escape(ctx.author.display_name)
                    )
                )
                return await self._clear_react(nv_msg)

        percentage_offered = (offering / bal) * 100
        min_roll = int(percentage_offered / 10)
        entry_roll = random.randint(max(1, min_roll), 20)
        if entry_roll == 1:
            tax_mod = random.randint(4, 8)
            tax = round(bal / tax_mod)
            if tax > offering:
                loss = tax
            else:
                loss = offering
            await bank.withdraw_credits(ctx.author, loss)
            entry_msg = _(
                "A swirling void slowly grows and you watch in horror as it rushes to "
                "wash over you, leaving you cold... and your coin pouch significantly lighter. "
                "The portal to the negaverse remains closed."
            )
            return await nv_msg.edit(content=entry_msg)
        else:
            entry_msg = _(
                "Shadowy hands reach out to take your offering from you and a swirling "
                "black void slowly grows and engulfs you, transporting you to the negaverse."
            )
            await nv_msg.edit(content=entry_msg)
            await self._clear_react(nv_msg)
            await bank.withdraw_credits(ctx.author, offering)

        negachar = _("Nega-{c}").format(
            c=self.escape(random.choice(ctx.message.guild.members).display_name)
        )

        nega_msg = await ctx.send(
            _("**{author}** enters the negaverse and meets **{negachar}**.").format(
                author=self.escape(ctx.author.display_name), negachar=negachar
            )
        )
        roll = random.randint(max(1, min_roll * 2), 50)
        versus = random.randint(10, 60)
        xp_mod = random.randint(1, 10)
        weekend = datetime.today().weekday() in [5, 6]
        wedfriday = datetime.today().weekday() in [2, 4]
        daymult = 2 if weekend else 1.5 if wedfriday else 1
        xp_won = int((offering / xp_mod) * daymult)
        async with self.get_lock(ctx.message.author):
            try:
                c = await Character.from_json(self.config, ctx.message.author)
            except Exception:
                log.exception("Error with the new character sheet")
                return
        xp_to_max = int((c.maxlevel + 1) ** 3)
        ten_percent = xp_to_max * 0.1
        xp_won = ten_percent if xp_won > ten_percent else xp_won
        xp_won = int(xp_won * (min(max(random.randint(0, c.rebirths), 1), 50) / 100 + 1))
        if roll < 10:
            loss = round(bal // 3)
            try:
                await bank.withdraw_credits(ctx.author, loss)
                loss_msg = ""
                loss = humanize_number(loss)
            except ValueError:
                await bank.set_balance(ctx.author, 0)
                loss = _("all of their")
            loss_msg = _(
                ", losing {loss} {currency_name} as **{negachar}** rifled through their belongings"
            ).format(loss=loss, currency_name=currency_name, negachar=negachar)
            await nega_msg.edit(
                content=_(
                    "{content}\n**{author}** fumbled and died to **{negachar}'s** savagery{loss_msg}."
                ).format(
                    content=nega_msg.content,
                    author=self.escape(ctx.author.display_name),
                    negachar=negachar,
                    loss_msg=loss_msg,
                )
            )
            ctx.command.reset_cooldown(ctx)
        elif roll == 50 and versus < 50:
            await nega_msg.edit(
                content=_(
                    "{content}\n**{author}** decapitated **{negachar}**. You gain {xp_gain} xp and take "
                    "{offering} {currency_name} back from the shadowy corpse."
                ).format(
                    content=nega_msg.content,
                    author=self.escape(ctx.author.display_name),
                    negachar=negachar,
                    xp_gain=humanize_number(xp_won),
                    offering=humanize_number(offering),
                    currency_name=currency_name,
                )
            )
            await self._add_rewards(ctx, ctx.message.author, xp_won, offering, False)
        elif roll > versus:
            await nega_msg.edit(
                content=_(
                    "{content}\n**{author}** "
                    "{dice}({roll}) bravely defeated **{negachar}** {dice}({versus}). "
                    "You gain {xp_gain} xp."
                ).format(
                    dice=self.emojis.dice,
                    content=nega_msg.content,
                    author=self.escape(ctx.author.display_name),
                    roll=roll,
                    negachar=negachar,
                    versus=versus,
                    xp_gain=humanize_number(xp_won),
                )
            )
            await self._add_rewards(ctx, ctx.message.author, xp_won, 0, False)
        elif roll == versus:
            ctx.command.reset_cooldown(ctx)
            await nega_msg.edit(
                content=_(
                    "{content}\n**{author}** "
                    "{dice}({roll}) almost killed **{negachar}** {dice}({versus})."
                ).format(
                    dice=self.emojis.dice,
                    content=nega_msg.content,
                    author=self.escape(ctx.author.display_name),
                    roll=roll,
                    negachar=negachar,
                    versus=versus,
                )
            )
        else:
            loss = round(bal / (random.randint(10, 25)))
            try:
                await bank.withdraw_credits(ctx.author, loss)
                loss_msg = ""
            except ValueError:
                await bank.set_balance(ctx.author, 0)
                loss = _("all of their")
            loss_msg = _(
                ", losing {loss} {currency_name} as **{negachar}** looted their backpack"
            ).format(
                loss=humanize_number(loss) if not isinstance(loss, str) else loss,
                currency_name=currency_name,
                negachar=negachar,
            )
            await nega_msg.edit(
                content=_(
                    "**{author}** {dice}({roll}) was killed by **{negachar}** {dice}({versus}){loss_msg}."
                ).format(
                    dice=self.emojis.dice,
                    author=self.escape(ctx.author.display_name),
                    roll=roll,
                    negachar=negachar,
                    versus=versus,
                    loss_msg=loss_msg,
                )
            )
            ctx.command.reset_cooldown(ctx)

    @commands.group(autohelp=False)
    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    async def pet(self, ctx: Context):
        """[Ranger Class Only]

        This allows a Ranger to tame or set free a pet or send it foraging. (2h cooldown)
        """
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx, _("You're too distracted with the monster you are facing.")
            )

        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if c.heroclass["name"] != "Ranger":
            return await ctx.send(
                box(
                    _("{}, you need to be a Ranger to do this.").format(
                        self.escape(ctx.author.display_name)
                    ),
                    lang="css",
                )
            )
        if ctx.invoked_subcommand is None:
            if c.heroclass["pet"]:
                ctx.command.reset_cooldown(ctx)
                return await ctx.send(
                    box(
                        _(
                            "{author}, you already have a pet. "
                            "Try foraging ({prefix}pet forage)."
                        ).format(author=self.escape(ctx.author.display_name), prefix=ctx.prefix),
                        lang="css",
                    )
                )
            async with self.get_lock(ctx.author):
                try:
                    c = await Character.from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                cooldown_time = max(600, (3600 - (c.luck * 2 + c.total_int * 2)))
                if "catch_cooldown" not in c.heroclass:
                    c.heroclass["catch_cooldown"] = cooldown_time + 1
                if c.heroclass["catch_cooldown"] + cooldown_time > time.time():
                    cooldown_time = (c.heroclass["catch_cooldown"]) + cooldown_time - time.time()
                    return await smart_embed(
                        ctx,
                        _(
                            "You caught a pet recently, you will be able to go hunting in {}."
                        ).format(
                            humanize_timedelta(seconds=int(cooldown_time))
                            if int(cooldown_time) >= 1
                            else _("1 second")
                        ),
                    )
                extra_dipl = 0
                pet_choices = list(self.PETS.keys())
                pet = random.choice(pet_choices)

                roll = random.randint(1, 20)
                dipl_value = roll + c.total_cha + (c.total_int // 3) + (c.luck // 2)
                dipl_value += extra_dipl
                pet_reqs = self.PETS[pet].get("bonuses", {}).get("req", {})
                pet_msg4 = ""
                if pet_reqs.get("set", False):
                    if pet_reqs.get("set", None) in c.sets:
                        if "Ainz Ooal Gown" == pet_reqs.get("set", None):
                            dipl_value = 100000
                            pet = "Guardians of Nazarick"
                    else:
                        dipl_value = -100000
                        pet_msg4 = _(
                            "\nPerhaps you're missing some requirements to tame {pet}"
                        ).format(pet=pet)

                pet_msg = box(
                    _("{c} is trying to tame a pet.").format(
                        c=self.escape(ctx.author.display_name)
                    ),
                    lang="css",
                )
                user_msg = await ctx.send(pet_msg)
                await asyncio.sleep(2)
                pet_msg2 = box(
                    _(
                        "{author} started tracking a wild {pet_name} with a roll of {dice}({roll})."
                    ).format(
                        dice=self.emojis.dice,
                        author=self.escape(ctx.author.display_name),
                        pet_name=self.PETS[pet]["name"],
                        roll=roll,
                    ),
                    lang="css",
                )
                await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}")
                await asyncio.sleep(2)
                bonus = ""
                if roll == 1:
                    bonus = _("But they stepped on a twig and scared it away.")
                elif roll == 20:
                    bonus = _("They happen to have its favorite food.")
                    dipl_value += 10
                if dipl_value > self.PETS[pet]["cha"] and roll > 1:
                    roll = random.randint(0, 2 if roll == 20 else 4)
                    if roll == 0:
                        pet_msg3 = box(
                            _("{bonus}\nThey successfully tamed the {pet}.").format(
                                bonus=bonus, pet=self.PETS[pet]["name"]
                            ),
                            lang="css",
                        )
                        await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}\n{pet_msg3}")
                        c.heroclass["pet"] = self.PETS[pet]
                        c.heroclass["catch_cooldown"] = time.time()
                        await self.config.user(ctx.author).set(c.to_json())
                    elif roll == 1:
                        bonus = _("But they stepped on a twig and scared it away.")
                        pet_msg3 = box(
                            _("{bonus}\nThe {pet} escaped.").format(
                                bonus=bonus, pet=self.PETS[pet]["name"]
                            ),
                            lang="css",
                        )
                        await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}\n{pet_msg3}{pet_msg4}")
                    else:
                        bonus = ""
                        pet_msg3 = box(
                            _("{bonus}\nThe {pet} escaped.").format(
                                bonus=bonus, pet=self.PETS[pet]["name"]
                            ),
                            lang="css",
                        )
                        await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}\n{pet_msg3}{pet_msg4}")
                else:
                    pet_msg3 = box(
                        _("{bonus}\nThe {pet} escaped.").format(
                            bonus=bonus, pet=self.PETS[pet]["name"]
                        ),
                        lang="css",
                    )
                    await user_msg.edit(content=f"{pet_msg}\n{pet_msg2}\n{pet_msg3}{pet_msg4}")

    @pet.command(name="forage")
    async def _forage(self, ctx: Context):
        """Use your pet to forage for items!"""
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx, _("You're too distracted with the monster you are facing.")
            )
        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if c.heroclass["name"] != "Ranger":
            return
        if not c.heroclass["pet"]:
            return await ctx.send(
                box(
                    _("{}, you need to have a pet to do this.").format(
                        self.escape(ctx.author.display_name)
                    ),
                    lang="css",
                )
            )
        cooldown_time = max(1800, (7200 - (c.luck * 2 + c.total_int * 2)))
        if "cooldown" not in c.heroclass:
            c.heroclass["cooldown"] = cooldown_time + 1
        if c.heroclass["cooldown"] + cooldown_time <= time.time():
            await self._open_chest(ctx, c.heroclass["pet"]["name"], "pet", character=c)
            async with self.get_lock(ctx.author):
                try:
                    c = await Character.from_json(self.config, ctx.author)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                c.heroclass["cooldown"] = time.time()
                await self.config.user(ctx.author).set(c.to_json())
        else:
            cooldown_time = (c.heroclass["cooldown"] + 7200) - time.time()
            return await smart_embed(
                ctx,
                _("This command is on cooldown. Try again in {}.").format(
                    humanize_timedelta(seconds=int(cooldown_time))
                    if int(cooldown_time) >= 1
                    else _("1 second")
                ),
            )

    @pet.command(name="free")
    async def _free(self, ctx: Context):
        """Free your pet :cry:"""
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx, _("You're too distracted with the monster you are facing.")
            )
        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if c.heroclass["name"] != "Ranger":
            return await ctx.send(
                box(
                    _("{}, you need to be a Ranger to do this.").format(
                        self.escape(ctx.author.display_name)
                    ),
                    lang="css",
                )
            )
        if c.heroclass["pet"]:
            async with self.get_lock(ctx.author):
                c.heroclass["pet"] = {}
                await self.config.user(ctx.author).set(c.to_json())
            return await ctx.send(
                box(
                    _("{} released their pet into the wild.").format(
                        self.escape(ctx.author.display_name)
                    ),
                    lang="css",
                )
            )
        else:
            return await ctx.send(box(_("You don't have a pet."), lang="css"))

    @commands.command()
    @commands.guild_only()
    async def bless(self, ctx: Context):
        """[Cleric Class Only]

        This allows a praying Cleric to add substantial bonuses for heroes fighting the battle. (10
        minute cooldown)
        """

        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if c.heroclass["name"] != "Cleric":
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(
                ctx,
                _("**{}**, you need to be a Cleric to do this.").format(
                    self.escape(ctx.author.display_name)
                ),
            )
        else:
            if c.heroclass["ability"]:
                return await smart_embed(
                    ctx,
                    _("**{}**, ability already in use.").format(
                        self.escape(ctx.author.display_name)
                    ),
                )
            cooldown_time = max(300, (1200 - ((c.luck + c.total_int) * 2)))
            if "cooldown" not in c.heroclass:
                c.heroclass["cooldown"] = cooldown_time + 1
            if c.heroclass["cooldown"] + cooldown_time <= time.time():
                c.heroclass["ability"] = True
                c.heroclass["cooldown"] = time.time()
                async with self.get_lock(c.user):
                    await self.config.user(ctx.author).set(c.to_json())

                await smart_embed(
                    ctx,
                    _("{bless}📜 **{c}** is starting an inspiring sermon. {bless}📜").format(
                        c=self.escape(ctx.author.display_name), bless=self.emojis.skills.bless,
                    ),
                )
            else:
                cooldown_time = (c.heroclass["cooldown"]) + cooldown_time - time.time()
                return await smart_embed(
                    ctx,
                    _(
                        "Your hero is currently recovering from the last time they used this skill. Try again in {}"
                    ).format(
                        humanize_timedelta(seconds=int(cooldown_time))
                        if int(cooldown_time) >= 1
                        else _("1 second")
                    ),
                )

    @commands.command()
    @commands.guild_only()
    async def rage(self, ctx: Context):
        """[Berserker Class Only]

        This allows a Berserker to add substantial attack bonuses for one battle. (10 minute cooldown)
        """

        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if c.heroclass["name"] != "Berserker":
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(
                ctx,
                _("**{}**, you need to be a Berserker to do this.").format(
                    self.escape(ctx.author.display_name)
                ),
            )
        else:
            if c.heroclass["ability"] is True:
                return await smart_embed(
                    ctx,
                    _("**{}**, ability already in use.").format(
                        self.escape(ctx.author.display_name)
                    ),
                )
            cooldown_time = max(300, (1200 - ((c.luck + c.total_att) * 2)))
            if "cooldown" not in c.heroclass:
                c.heroclass["cooldown"] = cooldown_time + 1
            if c.heroclass["cooldown"] + cooldown_time <= time.time():
                c.heroclass["ability"] = True
                c.heroclass["cooldown"] = time.time()
                async with self.get_lock(c.user):
                    await self.config.user(ctx.author).set(c.to_json())
                await smart_embed(
                    ctx,
                    _("🗯️{skill} **{c}** is starting to froth at the mouth... {skill}🗯️").format(
                        c=self.escape(ctx.author.display_name), skill=self.emojis.skills.berserker,
                    ),
                )
            else:
                cooldown_time = (c.heroclass["cooldown"]) + cooldown_time - time.time()
                return await smart_embed(
                    ctx,
                    _(
                        "Your hero is currently recovering from the last time they used this skill. Try again in {}"
                    ).format(
                        humanize_timedelta(seconds=int(cooldown_time))
                        if int(cooldown_time) >= 1
                        else _("1 second")
                    ),
                )

    @commands.command()
    @commands.guild_only()
    async def focus(self, ctx: Context):
        """[Wizard Class Only]

        This allows a Wizard to add substantial magic bonuses for one battle. (10 minute cooldown)
        """

        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if c.heroclass["name"] != "Wizard":
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(
                ctx,
                _("**{}**, you need to be a Wizard to do this.").format(
                    self.escape(ctx.author.display_name)
                ),
            )
        else:
            if c.heroclass["ability"] is True:
                return await smart_embed(
                    ctx,
                    _("**{}**, ability already in use.").format(
                        self.escape(ctx.author.display_name)
                    ),
                )
            cooldown_time = max(300, (1200 - ((c.luck + c.total_int) * 2)))
            if "cooldown" not in c.heroclass:
                c.heroclass["cooldown"] = cooldown_time + 1
            if c.heroclass["cooldown"] + cooldown_time <= time.time():
                c.heroclass["ability"] = True
                c.heroclass["cooldown"] = time.time()
                async with self.get_lock(c.user):
                    await self.config.user(ctx.author).set(c.to_json())
                await smart_embed(
                    ctx,
                    _("{skill} **{c}** is focusing all of their energy...{skill}").format(
                        c=self.escape(ctx.author.display_name), skill=self.emojis.skills.wizzard,
                    ),
                )
            else:
                cooldown_time = (c.heroclass["cooldown"]) + cooldown_time - time.time()
                return await smart_embed(
                    ctx,
                    _(
                        "Your hero is currently recovering from the last time they used this skill. Try again in {}"
                    ).format(
                        humanize_timedelta(seconds=int(cooldown_time))
                        if int(cooldown_time) >= 1
                        else _("1 second")
                    ),
                )

    @commands.command()
    @commands.guild_only()
    async def music(self, ctx: Context):
        """[Bard Class Only]

        This allows a Bard to add substantial diplomacy bonuses for one battle. (10 minute
        cooldown)
        """

        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if c.heroclass["name"] != "Bard":
            ctx.command.reset_cooldown(ctx)
            return await smart_embed(
                ctx,
                _("{}, you need to be a Bard to do this.").format(
                    self.escape(ctx.author.display_name)
                ),
            )
        else:
            if c.heroclass["ability"]:
                return await smart_embed(
                    ctx,
                    _("{}, ability already in use.").format(self.escape(ctx.author.display_name)),
                )
            cooldown_time = max(300, (1200 - ((c.luck + c.total_cha) * 2)))
            if "cooldown" not in c.heroclass:
                c.heroclass["cooldown"] = cooldown_time + 1
            if c.heroclass["cooldown"] + cooldown_time <= time.time():
                c.heroclass["ability"] = True
                c.heroclass["cooldown"] = time.time()
                async with self.get_lock(c.user):
                    await self.config.user(ctx.author).set(c.to_json())
                    await smart_embed(
                        ctx,
                        _("{skill} **{c}** is whipping up a performance...{skill}").format(
                            c=self.escape(ctx.author.display_name), skill=self.emojis.skills.bard,
                        ),
                    )
            else:
                cooldown_time = (c.heroclass["cooldown"]) + cooldown_time - time.time()
                return await smart_embed(
                    ctx,
                    _(
                        "Your hero is currently recovering from the last time they used this skill. Try again in {}"
                    ).format(humanize_timedelta(seconds=int(cooldown_time))),
                )

    @commands.command()
    @commands.cooldown(rate=1, per=2, type=commands.BucketType.user)
    async def skill(self, ctx: Context, spend: str = None, amount: int = 1):
        """This allows you to spend skillpoints.

        `[p]skill attack/charisma/intelligence`
        `[p]skill reset` Will allow you to reset your skill points for a cost.
        """
        if self.in_adventure(ctx):
            return await smart_embed(ctx, _("The skill cleric is back in town."))
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        if amount < 1:
            return await smart_embed(ctx, _("Nice try :smirk:"))
        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        if spend == "reset":
            bal = c.bal
            currency_name = await bank.get_currency_name(ctx.guild)

            offering = min(int(bal / 5 + (c.total_int // 3)), 1000000000)
            nv_msg = await ctx.send(
                _(
                    "{author}, this will cost you at least {offering} {currency_name}.\n"
                    "You currently have {bal}. Do you want to proceed?"
                ).format(
                    author=self.escape(ctx.author.display_name),
                    offering=humanize_number(offering),
                    currency_name=currency_name,
                    bal=humanize_number(bal),
                )
            )
            start_adding_reactions(nv_msg, ReactionPredicate.YES_OR_NO_EMOJIS)
            pred = ReactionPredicate.yes_or_no(nv_msg, ctx.author)
            try:
                await ctx.bot.wait_for("reaction_add", check=pred, timeout=60)
            except asyncio.TimeoutError:
                await self._clear_react(nv_msg)
                return

            if pred.result:
                c.skill["pool"] = c.skill["att"] + c.skill["cha"] + c.skill["int"]
                c.skill["att"] = 0
                c.skill["cha"] = 0
                c.skill["int"] = 0
                async with self.get_lock(c.user):
                    await self.config.user(ctx.author).set(c.to_json())
                await bank.withdraw_credits(ctx.author, offering)
                await smart_embed(
                    ctx,
                    _("{}, your skill points have been reset.").format(
                        self.escape(ctx.author.display_name)
                    ),
                )
            else:
                await smart_embed(
                    ctx,
                    _("Don't play games with me, {}.").format(
                        self.escape(ctx.author.display_name)
                    ),
                )
            return

        if c.skill["pool"] <= 0:
            return await smart_embed(
                ctx,
                _("{}, you do not have unspent skillpoints.").format(
                    self.escape(ctx.author.display_name)
                ),
            )
        elif c.skill["pool"] < amount:
            return await smart_embed(
                ctx,
                _("{}, you do not have enough unspent skillpoints.").format(
                    self.escape(ctx.author.display_name)
                ),
            )
        if spend is None:
            await smart_embed(
                ctx,
                _(
                    "**{author}**, you currently have **{skillpoints}** unspent skillpoints.\n"
                    "If you want to put them towards a permanent attack, charisma or intelligence bonus, use "
                    "`{prefix}skill attack`, `{prefix}skill charisma` or  `{prefix}skill intelligence`"
                ).format(
                    author=self.escape(ctx.author.display_name),
                    skillpoints=str(c.skill["pool"]),
                    prefix=ctx.prefix,
                ),
            )
        else:
            if spend not in ["attack", "charisma", "intelligence"]:
                return await smart_embed(
                    ctx, _("Don't try to fool me! There is no such thing as {}.").format(spend)
                )
            elif spend == "attack":
                c.skill["pool"] -= amount
                c.skill["att"] += amount
            elif spend == "charisma":
                c.skill["pool"] -= amount
                c.skill["cha"] += amount
            elif spend == "intelligence":
                c.skill["pool"] -= amount
                c.skill["int"] += amount
            async with self.get_lock(c.user):
                await self.config.user(ctx.author).set(c.to_json())
            await smart_embed(
                ctx,
                _("{author}, you permanently raised your {spend} value by {amount}.").format(
                    author=self.escape(ctx.author.display_name), spend=spend, amount=amount
                ),
            )

    @commands.command()
    async def stats(self, ctx: Context, *, user: discord.Member = None):
        """This draws up a charsheet of you or an optionally specified member.

        `[p]stats @locastan` will bring up locastans stats. `[p]stats` without user will open your
        stats.
        """
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        if user is None:
            user = ctx.author
        if user.bot:
            return
        try:
            c = await Character.from_json(self.config, user)
        except Exception:
            log.exception("Error with the new character sheet")
            return
        msg = await ctx.send(box(c, lang="css"))
        try:
            await msg.add_reaction("\N{CROSS MARK}")
        except discord.errors.Forbidden:
            return
        pred = ReactionPredicate.same_context(msg, ctx.author)
        try:
            react, user = await self.bot.wait_for("reaction_add", check=pred, timeout=60)
        except asyncio.TimeoutError:
            return
        if str(react.emoji) == "\N{CROSS MARK}":
            await msg.delete()

    async def _build_loadout_display(self, userdata):
        form_string = _("( ATT  |  CHA  |  INT  |  DEX  |  LUCK)\n" "Items Equipped:")
        last_slot = ""
        att = 0
        cha = 0
        intel = 0
        dex = 0
        luck = 0
        for slot, data in userdata["items"].items():

            if slot == "backpack":
                continue
            if last_slot == "two handed":
                last_slot = slot
                continue

            if not data:
                last_slot = slot
                form_string += _("\n\n {} slot").format(slot.title())
                continue
            item = Item.from_json(data)
            slot_name = userdata["items"][slot]["".join(i for i in data.keys())]["slot"]
            slot_name = slot_name[0] if len(slot_name) < 2 else _("two handed")
            form_string += _("\n\n {} slot").format(slot_name.title())
            last_slot = slot_name
            rjust = max([len(i) for i in data.keys()])
            form_string += f"\n  - {str(item):<{rjust}} - "
            form_string += (
                f"({item.att if len(item.slot) < 2 else (item.att * 2)} | "
                f"{item.cha if len(item.slot) < 2 else (item.cha * 2)} | "
                f"{item.int if len(item.slot) < 2 else (item.int * 2)} | "
                f"{item.dex if len(item.slot) < 2 else (item.dex * 2)} | "
                f"{item.luck if len(item.slot) < 2 else (item.luck * 2)})"
            )
            att += item.att if len(item.slot) < 2 else (item.att * 2)
            cha += item.cha if len(item.slot) < 2 else (item.cha * 2)
            intel += item.int if len(item.slot) < 2 else (item.int * 2)
            dex += item.dex if len(item.slot) < 2 else (item.dex * 2)
            luck += item.luck if len(item.slot) < 2 else (item.luck * 2)
        form_string += _("\n\nTotal stats: ")
        form_string += f"({att} | {cha} | {intel} | {dex} | {luck})"
        return form_string + "\n"

    @commands.command()
    async def unequip(self, ctx: Context, *, item: str):
        """This stashes a specified equipped item into your backpack.

        `[p]unequip name of item` or `[p]unequip slot` You can only have one of each uniquely named
        item in your backpack.
        """
        if self.in_adventure(ctx):
            return await smart_embed(
                ctx,
                _(
                    "You tried to unequipping your items, but there then you realised there no place to put them."
                ),
            )
        if not await self.allow_in_dm(ctx):
            return await smart_embed(ctx, _("This command is not available in DM's on this bot."))
        async with self.get_lock(ctx.author):
            try:
                c = await Character.from_json(self.config, ctx.author)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            slots = [
                "head",
                "neck",
                "chest",
                "gloves",
                "belt",
                "legs",
                "boots",
                "left",
                "right",
                "ring",
                "charm",
            ]
            msg = ""

            if item in slots:
                current_item = getattr(c, item, None)
                if not current_item:
                    msg = _(
                        "{author}, you do not have an item equipped in the {item} slot."
                    ).format(author=self.escape(ctx.author.display_name), item=item)
                    return await ctx.send(box(msg, lang="css"))
                await c.unequip_item(current_item)
                msg = _(
                    "{author} removed the {current_item} and put it into their backpack."
                ).format(author=self.escape(ctx.author.display_name), current_item=current_item)
            else:
                for current_item in c.get_current_equipment():
                    if item.lower() in current_item.name.lower():
                        await c.unequip_item(current_item)
                        msg = _(
                            "{author} removed the {current_item} and put it into their backpack."
                        ).format(
                            author=self.escape(ctx.author.display_name), current_item=current_item
                        )
                        # We break if this works because unequip
                        # will autmatically remove multiple items
                        break
            if msg:
                await ctx.send(box(msg, lang="css"))
                await self.config.user(ctx.author).set(c.to_json())
            else:
                await smart_embed(
                    ctx,
                    _("{author}, you do not have an item matching {item} equipped.").format(
                        author=self.escape(ctx.author.display_name), item=item
                    ),
                )

    @commands.command(name="devcooldown")
    @commands.is_owner()
    async def _devcooldown(self, ctx: Context):
        """Resets the Adventure cooldown in this server."""
        await self.config.guild(ctx.guild).cooldown.set(0)
        await ctx.tick()

    @commands.command(name="adventure", aliases=["a"])
    @commands.guild_only()
    async def _adventure(self, ctx: Context, *, challenge=None):
        """This will send you on an adventure!

        You play by reacting with the offered emojis.
        """

        if ctx.guild.id in self._sessions:
            return await smart_embed(
                ctx, _("There's already another adventure going on in this server.")
            )

        if not await has_funds(ctx.author, 250):
            currency_name = await bank.get_currency_name(ctx.guild)
            return await smart_embed(
                ctx,
                _("You need {req} {name} to start an adventure.").format(
                    req=250, name=currency_name
                ),
            )
        guild_settings = await self.config.guild(ctx.guild).all()
        cooldown = guild_settings["cooldown"]

        cooldown_time = guild_settings["cooldown_timer_manual"]
        cooldown_time = cooldown_time

        if cooldown + cooldown_time > time.time():
            cooldown_time = cooldown + cooldown_time - time.time()
            return await smart_embed(
                ctx,
                _("No heroes are ready to depart in an adventure, try again in {}").format(
                    humanize_timedelta(seconds=int(cooldown_time))
                    if int(cooldown_time) >= 1
                    else _("1 second")
                ),
            )

        if challenge and not (self.is_dev(ctx.author) or await ctx.bot.is_owner(ctx.author)):
            # Only let the bot owner specify a specific challenge
            challenge = None

        adventure_msg = _("You feel adventurous, **{}**?").format(
            self.escape(ctx.author.display_name)
        )
        try:
            reward, participants = await self._simple(ctx, adventure_msg, challenge)
            await self.config.guild(ctx.guild).cooldown.set(time.time())
        except Exception:
            await self.config.guild(ctx.guild).cooldown.set(0)
            log.error("Something went wrong controlling the game", exc_info=True)
            return
        if not reward and not participants:
            await self.config.guild(ctx.guild).cooldown.set(0)
            return
        reward_copy = reward.copy()
        for userid, rewards in reward_copy.items():
            if rewards:
                user = ctx.guild.get_member(userid)  # bot.get_user breaks sometimes :ablobsweats:
                if user is None:
                    # sorry no rewards if you leave the server
                    continue
                await self._add_rewards(
                    ctx, user, rewards["xp"], rewards["cp"], rewards["special"]
                )
                self._rewards[userid] = {}
        if participants:
            for user in participants:  # reset activated abilities
                async with self.get_lock(user):
                    try:
                        c = await Character.from_json(self.config, user)
                    except Exception:
                        log.exception("Error with the new character sheet")
                        continue
                    if c.heroclass["name"] != "Ranger" and c.heroclass["ability"]:
                        c.heroclass["ability"] = False
                        await self.config.user(user).set(c.to_json())

        while ctx.guild.id in self._sessions:
            del self._sessions[ctx.guild.id]

    @_adventure.error
    async def _error_handler(self, ctx: commands.Context, error: Exception) -> None:
        error = getattr(error, "original", error)
        if not isinstance(
            error,
            (
                commands.CheckFailure,
                commands.UserInputError,
                commands.DisabledCommand,
                commands.CommandOnCooldown,
            ),
        ):
            while ctx.guild.id in self._sessions:
                del self._sessions[ctx.guild.id]

        await ctx.bot.on_command_error(ctx, error, unhandled_by_cog=True)

    async def get_challenge(self, ctx: Context, monsters):
        try:
            c = await Character.from_json(self.config, ctx.author)
        except Exception:
            log.exception("Error with the new character sheet", exc_info=True)
            return
        possible_monsters = []
        stat_range = self._adv_results.get_stat_range()
        for e, (m, stats) in enumerate(monsters.items(), 1):
            appropriate_range = max(stats["hp"], stats["dipl"]) <= (max(c.att, c.int, c.cha) * 2)
            if stat_range["max_stat"] > 0:
                main_stat = stats["hp"] if (stat_range["stat_type"] == "attack") else stats["dipl"]
                appropriate_range = stat_range["min_stat"] <= main_stat <= stat_range["max_stat"]
            if not appropriate_range:
                continue
            if not stats["boss"] and not stats["miniboss"]:
                count = 0
                break_at = random.randint(1, 15)
                while count < break_at:
                    count += 1
                    possible_monsters.append(m)
                    if count == break_at:
                        break
            else:
                possible_monsters.append(m)
        if len(possible_monsters) == 0:
            return random.choice(list(monsters.keys()))
        else:
            return random.choice(possible_monsters)

    async def update_monster_roster(self, user):

        try:
            c = await Character.from_json(self.config, user)
        except Exception:
            log.exception("Error with the new character sheet")
            return self.MONSTERS, 1
        else:
            monster_stats = 1

        if c.rebirths >= 25:
            monsters = self.AS_MONSTERS
            monster_stats = 1 + max((c.rebirths // 25) - 1, 0)
        elif c.rebirths >= 15:
            monsters = {**self.AS_MONSTERS}
        elif c.rebirths >= 10:
            monsters = {**self.MONSTERS, **self.AS_MONSTERS}
        else:
            monster_stats = 1
            monsters = self.MONSTERS

        return monsters, monster_stats

    async def _simple(
        self, ctx: Context, adventure_msg, challenge: str = None, attribute: str = None
    ):
        self.bot.dispatch("adventure", ctx)
        text = ""
        monster_roaster, monster_stats = await self.update_monster_roster(ctx.author)
        if challenge and challenge.title() in list(monster_roaster.keys()):
            challenge = challenge.title()
        else:
            challenge = await self.get_challenge(ctx, monster_roaster)
        if attribute and attribute.lower() in list(self.ATTRIBS.keys()):
            attribute = attribute.lower()
        else:
            attribute = random.choice(list(self.ATTRIBS.keys()))

        if monster_roaster[challenge]["boss"]:
            timer = 60 * 5
            text = box(_("\n [{} Alarm!]").format(challenge), lang="css")
            self.bot.dispatch("adventure_boss", ctx)  # dispatches an event on bosses
        elif monster_roaster[challenge]["miniboss"]:
            timer = 60 * 3
            self.bot.dispatch("adventure_miniboss", ctx)
        else:
            timer = 60 * 2

        self._sessions[ctx.guild.id] = GameSession(
            challenge=challenge,
            attribute=attribute,
            guild=ctx.guild,
            boss=monster_roaster[challenge]["boss"],
            miniboss=monster_roaster[challenge]["miniboss"],
            timer=timer,
            monster=monster_roaster[challenge],
            monsters=monster_roaster,
            monster_stats=monster_stats,
            message=ctx.message,
        )
        adventure_msg = (
            f"{adventure_msg}{text}\n{random.choice(self.LOCATIONS)}\n"
            f"**{self.escape(ctx.author.display_name)}**{random.choice(self.RAISINS)}"
        )
        await self._choice(ctx, adventure_msg)
        if ctx.guild.id not in self._sessions:
            return None, None
        rewards = self._rewards
        participants = self._sessions[ctx.guild.id].participants
        return (rewards, participants)

    async def _choice(self, ctx: Context, adventure_msg):
        session = self._sessions[ctx.guild.id]
        dragon_text = _(
            "but **a{attr} {chall}** "
            "just landed in front of you glaring! \n\n"
            "What will you do and will other heroes be brave enough to help you?\n"
            "Heroes have 5 minutes to participate via reaction:"
            "\n\nReact with: {reactions}"
        ).format(
            attr=session.attribute,
            chall=session.challenge,
            reactions="**"
            + _("Fight")
            + "** - **"
            + _("Spell")
            + "** - **"
            + _("Talk")
            + "** - **"
            + _("Pray")
            + "** - **"
            + _("Run")
            + "**",
        )
        basilisk_text = _(
            "but **a{attr} {chall}** stepped out looking around. \n\n"
            "What will you do and will other heroes help your cause?\n"
            "Heroes have 3 minutes to participate via reaction:"
            "\n\nReact with: {reactions}"
        ).format(
            attr=session.attribute,
            chall=session.challenge,
            reactions="**"
            + _("Fight")
            + "** - **"
            + _("Spell")
            + "** - **"
            + _("Talk")
            + "** - **"
            + _("Pray")
            + "** - **"
            + _("Run")
            + "**",
        )
        normal_text = _(
            "but **a{attr} {chall}** "
            "is guarding it with{threat}. \n\n"
            "What will you do and will other heroes help your cause?\n"
            "Heroes have 2 minutes to participate via reaction:"
            "\n\nReact with: {reactions}"
        ).format(
            attr=session.attribute,
            chall=session.challenge,
            threat=random.choice(self.THREATEE),
            reactions="**"
            + _("Fight")
            + "** - **"
            + _("Spell")
            + "** - **"
            + _("Talk")
            + "** - **"
            + _("Pray")
            + "** - **"
            + _("Run")
            + "**",
        )

        embed = discord.Embed(colour=discord.Colour.blurple())
        use_embeds = (
            await self.config.guild(ctx.guild).embed()
            and ctx.channel.permissions_for(ctx.me).embed_links
        )
        if session.boss:
            if use_embeds:
                embed.description = f"{adventure_msg}\n{dragon_text}"
                embed.colour = discord.Colour.dark_red()
                if session.monster["image"]:
                    embed.set_image(url=session.monster["image"])
                adventure_msg = await ctx.send(embed=embed)
            else:
                adventure_msg = await ctx.send(f"{adventure_msg}\n{dragon_text}")
            timeout = 60 * 5

        elif session.miniboss:
            if use_embeds:
                embed.description = f"{adventure_msg}\n{basilisk_text}"
                embed.colour = discord.Colour.dark_green()
                if session.monster["image"]:
                    embed.set_image(url=session.monster["image"])
                adventure_msg = await ctx.send(embed=embed)
            else:
                adventure_msg = await ctx.send(f"{adventure_msg}\n{basilisk_text}")
            timeout = 60 * 3
        else:
            if use_embeds:
                embed.description = f"{adventure_msg}\n{normal_text}"
                if session.monster["image"]:
                    embed.set_thumbnail(url=session.monster["image"])
                adventure_msg = await ctx.send(embed=embed)
            else:
                adventure_msg = await ctx.send(f"{adventure_msg}\n{normal_text}")
            timeout = 60 * 2
        session.message_id = adventure_msg.id
        start_adding_reactions(adventure_msg, self._adventure_actions, ctx.bot.loop)
        timer = await self._adv_countdown(ctx, session.timer, "Time remaining")
        self.tasks[adventure_msg.id] = timer
        try:
            await asyncio.wait_for(timer, timeout=timeout + 5)
        except Exception:
            timer.cancel()
            log.error("Error with the countdown timer", exc_info=True)

        return await self._result(ctx, adventure_msg)

    async def local_perms(self, user):
        """Check the user is/isn't locally whitelisted/blacklisted.

        https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(user):
            return True
        guild_settings = self.bot.db.guild(user.guild)
        local_blacklist = await guild_settings.blacklist()
        local_whitelist = await guild_settings.whitelist()

        _ids = [r.id for r in user.roles if not r.is_default()]
        _ids.append(user.id)
        if local_whitelist:
            return any(i in local_whitelist for i in _ids)

        return not any(i in local_blacklist for i in _ids)

    async def global_perms(self, user):
        """Check the user is/isn't globally whitelisted/blacklisted.

        https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/release/3.0.0/redbot/core/global_checks.py
        """
        if await self.bot.is_owner(user):
            return True
        whitelist = await self.bot.db.whitelist()
        if whitelist:
            return user.id in whitelist

        return user.id not in await self.bot.db.blacklist()

    async def has_perm(self, user):
        if hasattr(self.bot, "allowed_by_whitelist_blacklist"):
            return await self.bot.allowed_by_whitelist_blacklist(user)
        else:
            return await self.local_perms(user) or await self.global_perms(user)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """This will be a cog level reaction_add listener for game logic."""
        await self.bot.wait_until_ready()
        if user.bot:
            return
        try:
            guild = user.guild
        except AttributeError:
            return
        emojis = ReactionPredicate.NUMBER_EMOJIS + self._adventure_actions
        if str(reaction.emoji) not in emojis:
            return
        if not await self.has_perm(user):
            return
        if guild.id in self._sessions:
            if reaction.message.id == self._sessions[guild.id].message_id:
                await self._handle_adventure(reaction, user)
        if guild.id in self._current_traders:
            if reaction.message.id == self._current_traders[guild.id][
                "msg"
            ] and not self.in_adventure(user=user):
                if user in self._current_traders[guild.id]["users"]:
                    return
                await self._handle_cart(reaction, user)

    async def _handle_adventure(self, reaction, user):
        action = {v: k for k, v in self._adventure_controls.items()}[str(reaction.emoji)]
        log.debug(action)
        session = self._sessions[user.guild.id]
        has_fund = await has_funds(user, 250)
        for x in ["fight", "magic", "talk", "pray", "run"]:
            if user in getattr(session, x, []):
                getattr(session, x).remove(user)

            if not has_fund or user in getattr(session, x, []):
                with contextlib.suppress(discord.HTTPException):
                    symbol = self._adventure_controls[x]
                    await reaction.message.remove_reaction(symbol, user)

        restricted = await self.config.restrict()
        if user not in getattr(session, action, []):
            if not has_fund:
                with contextlib.suppress(discord.HTTPException):
                    await user.send(
                        _(
                            "You contemplate going in an adventure with your friends, "
                            "you go to your bank to get some money to "
                            "prepare and they tell you that "
                            "your bank is empty\n"
                            "You run home to look for some and yet you can't even find a "
                            "single coin and realise how poor you are, then you just tell "
                            "your friends that you can't join them as you already have plans "
                            "as you are too embarrassed to tell them you are broke!"
                        )
                    )
                return
            if restricted:
                all_users = []
                for guild_id, guild_session in self._sessions.items():
                    guild_users_in_game = (
                        guild_session.fight
                        + guild_session.magic
                        + guild_session.talk
                        + guild_session.pray
                        + guild_session.run
                    )
                    all_users = all_users + guild_users_in_game

                if user in all_users:
                    user_id = f"{user.id}-{user.guild.id}"
                    # iterating through reactions here and removing them seems to be expensive
                    # so they can just keep their react on the adventures they can't join
                    if user_id not in self._react_messaged:
                        await reaction.message.channel.send(
                            _(
                                "**{c}**, you are already in an existing adventure. "
                                "Wait for it to finish before joining another one."
                            ).format(c=self.escape(user.display_name))
                        )
                        self._react_messaged.append(user_id)
                        return
                else:
                    getattr(session, action).append(user)
            else:
                getattr(session, action).append(user)

    async def _handle_cart(self, reaction, user):
        guild = user.guild
        emojis = ReactionPredicate.NUMBER_EMOJIS
        itemindex = emojis.index(str(reaction.emoji)) - 1
        items = self._current_traders[guild.id]["stock"][itemindex]
        self._current_traders[guild.id]["users"].append(user)
        spender = user
        channel = reaction.message.channel
        currency_name = await bank.get_currency_name(guild)
        if currency_name.startswith("<"):
            currency_name = "credits"
        item_data = box(
            items["item"].formatted_name + " - " + humanize_number(items["price"]), lang="css"
        )
        to_delete = await channel.send(
            _("{user}, how many {item} would you like to buy?").format(
                user=user.mention, item=item_data
            )
        )
        ctx = await self.bot.get_context(reaction.message)
        ctx.author = user
        pred = MessagePredicate.valid_int(ctx)
        try:
            msg = await self.bot.wait_for("message", check=pred, timeout=30)
        except asyncio.TimeoutError:
            self._current_traders[guild.id]["users"].remove(user)
            return
        if pred.result < 1:
            with contextlib.suppress(discord.HTTPException):
                await to_delete.delete()
                await msg.delete()
            await smart_embed(ctx, _("You're wasting my time."))
            self._current_traders[guild.id]["users"].remove(user)
            return
        if await bank.can_spend(spender, int(items["price"]) * pred.result):
            await bank.withdraw_credits(spender, int(items["price"]) * pred.result)
            async with self.get_lock(user):
                try:
                    c = await Character.from_json(self.config, user)
                except Exception:
                    log.exception("Error with the new character sheet")
                    return
                if "chest" in items["itemname"]:
                    if items["itemname"] == ".rare_chest":
                        c.treasure[1] += pred.result
                    elif items["itemname"] == "[epic chest]":
                        c.treasure[2] += pred.result
                    else:
                        c.treasure[0] += pred.result
                else:
                    item = items["item"]
                    item.owned = pred.result
                    if item.name in c.backpack:
                        c.backpack[item.name].owned += pred.result
                    else:
                        c.backpack[item.name] = item
                await self.config.user(user).set(c.to_json())
                with contextlib.suppress(discord.HTTPException):
                    await to_delete.delete()
                    await msg.delete()
                await channel.send(
                    box(
                        _(
                            "{author} bought {p_result} {item_name} for "
                            "{item_price} {currency_name} and put it into their backpack."
                        ).format(
                            author=self.escape(user.display_name),
                            p_result=pred.result,
                            item_name=item.formatted_name,
                            item_price=humanize_number(items["price"] * pred.result),
                            currency_name=currency_name,
                        ),
                        lang="css",
                    )
                )
                self._current_traders[guild.id]["users"].remove(user)
        else:
            with contextlib.suppress(discord.HTTPException):
                await to_delete.delete()
                await msg.delete()
            await channel.send(
                _("**{author}**, you do not have enough {currency_name}.").format(
                    author=self.escape(user.display_name), currency_name=currency_name
                )
            )
            self._current_traders[guild.id]["users"].remove(user)

    async def _result(self, ctx: Context, message: discord.Message):
        if ctx.guild.id not in self._sessions:
            return
        calc_msg = await ctx.send(_("Calculating..."))
        attack = 0
        diplomacy = 0
        magic = 0
        fumblelist: list = []
        critlist: list = []
        failed = False
        lost = False
        session = self._sessions[ctx.guild.id]
        with contextlib.suppress(discord.HTTPException):
            await message.clear_reactions()

        fight_list = list(set(session.fight))
        talk_list = list(set(session.talk))
        pray_list = list(set(session.pray))
        run_list = list(set(session.run))
        magic_list = list(set(session.magic))

        self._sessions[ctx.guild.id].fight = fight_list
        self._sessions[ctx.guild.id].talk = talk_list
        self._sessions[ctx.guild.id].pray = pray_list
        self._sessions[ctx.guild.id].run = run_list
        self._sessions[ctx.guild.id].magic = magic_list

        people = (
            len(fight_list) + len(magic_list) + len(talk_list) + len(pray_list) + len(run_list)
        )

        challenge = session.challenge

        attack, diplomacy, magic, run_msg = await self.handle_run(
            ctx.guild.id, attack, diplomacy, magic
        )
        failed = await self.handle_basilisk(ctx, failed)
        fumblelist, attack, diplomacy, magic, pray_msg = await self.handle_pray(
            ctx.guild.id, fumblelist, attack, diplomacy, magic
        )
        fumblelist, critlist, diplomacy, talk_msg = await self.handle_talk(
            ctx.guild.id, fumblelist, critlist, diplomacy
        )

        # need to pass challenge because we need to query MONSTERS[challenge]["pdef"] (and mdef)
        fumblelist, critlist, attack, magic, fight_msg = await self.handle_fight(
            ctx.guild.id, fumblelist, critlist, attack, magic, challenge
        )

        result_msg = run_msg + pray_msg + talk_msg + fight_msg
        challenge_attrib = session.attribute

        hp = (
            session.monsters[challenge]["hp"]
            * self.ATTRIBS[challenge_attrib][0]
            * session.monster_stats
        )
        dipl = (
            session.monsters[challenge]["dipl"]
            * self.ATTRIBS[challenge_attrib][1]
            * session.monster_stats
        )

        dmg_dealt = attack + magic
        slain = dmg_dealt >= round(hp)
        persuaded = diplomacy >= round(dipl)
        damage_str = ""
        diplo_str = ""
        if dmg_dealt > 0:
            damage_str = _("The group {status} {challenge} **({result}/{int_hp})**.\n").format(
                status=_("hit the") if failed or not slain else _("killed the"),
                challenge=challenge,
                result=humanize_number(dmg_dealt),
                int_hp=humanize_number(int(hp)),
            )
        if diplomacy > 0:
            diplo_str = _(
                "The group {status} the {challenge} with {how}" " **({diplomacy}/{int_dipl})**.\n"
            ).format(
                status=_("tried to persuade") if not persuaded else _("distracted"),
                challenge=challenge,
                how=_("flattery") if failed or not persuaded else _("insults"),
                diplomacy=humanize_number(diplomacy),
                int_dipl=humanize_number(int(dipl)),
            )
        if dmg_dealt >= diplomacy:
            self._adv_results.add_result("attack", dmg_dealt, people, slain)
        else:
            self._adv_results.add_result("talk", diplomacy, people, persuaded)
        #  log.debug(self._adv_results)
        result_msg = result_msg + "\n" + damage_str + diplo_str

        fight_name_list = []
        wizard_name_list = []
        talk_name_list = []
        pray_name_list = []
        repair_list = []
        for user in fight_list:
            fight_name_list.append(f"**{self.escape(user.display_name)}**")
        for user in magic_list:
            wizard_name_list.append(f"**{self.escape(user.display_name)}**")
        for user in talk_list:
            talk_name_list.append(f"**{self.escape(user.display_name)}**")
        for user in pray_list:
            pray_name_list.append(f"**{self.escape(user.display_name)}**")

        fighters_final_string = _(" and ").join(
            [", ".join(fight_name_list[:-1]), fight_name_list[-1]]
            if len(fight_name_list) > 2
            else fight_name_list
        )
        wizards_final_string = _(" and ").join(
            [", ".join(wizard_name_list[:-1]), wizard_name_list[-1]]
            if len(wizard_name_list) > 2
            else wizard_name_list
        )
        talkers_final_string = _(" and ").join(
            [", ".join(talk_name_list[:-1]), talk_name_list[-1]]
            if len(talk_name_list) > 2
            else talk_name_list
        )
        preachermen_final_string = _(" and ").join(
            [", ".join(pray_name_list[:-1]), pray_name_list[-1]]
            if len(pray_name_list) > 2
            else pray_name_list
        )
        await calc_msg.delete()
        text = ""
        success = False
        treasure = [0, 0, 0, 0, 0]
        if slain or persuaded and not failed:
            success = True
            roll = random.randint(1, 10)
            monster_amount = hp + dipl if slain and persuaded else hp if slain else dipl
            if session.boss:  # rewards 60:30:10 Epic Legendary Gear Set items
                treasure = random.choice(
                    [
                        [0, 1, 1, 0, 0],
                        [0, 1, 1, 0, 0],
                        [0, 2, 1, 0, 0],
                        [0, 2, 1, 0, 0],
                        [0, 3, 1, 0, 0],
                        [0, 3, 1, 0, 0],
                        [0, 1, 2, 0, 0],
                        [0, 2, 2, 0, 0],
                        [0, 3, 2, 0, 0],
                        [0, 0, 3, 1, 0],
                        [0, 0, 1, 2, 0],
                        [0, 0, 0, 3, 0],
                        [0, 0, 0, 1, 1],
                        [0, 0, 0, 0, 1],
                        [0, 0, 0, 0, 1],
                    ]
                )
            elif (
                session.miniboss
            ):  # rewards 50:50 rare:normal chest for killing something like the basilisk
                treasure = random.choice(
                    [[1, 1, 1, 0, 0], [0, 0, 1, 1, 0], [0, 0, 2, 2, 0], [0, 1, 0, 2, 0]]
                )
            elif monster_amount >= 700:  # super hard stuff
                if roll <= 7:
                    treasure = random.choice([[0, 0, 1, 0, 0], [0, 1, 0, 0, 0], [0, 0, 0, 1, 0]])
            elif monster_amount >= 500:  # rewards 50:50 rare:epic chest for killing hard stuff.
                if roll <= 5:
                    treasure = random.choice([[0, 0, 1, 0, 0], [0, 1, 0, 0, 0], [0, 1, 1, 0, 0]])
            elif (
                monster_amount >= 300
            ):  # rewards 50:50 rare:normal chest for killing hardish stuff
                if roll <= 2:
                    treasure = random.choice([[1, 0, 0, 0, 0], [0, 1, 0, 0, 0], [1, 1, 0, 0, 0]])
            elif (
                monster_amount >= 80
            ):  # small chance of a normal chest on killing stuff that's not terribly weak
                if roll == 1:
                    treasure = [1, 0, 0, 0, 0]

            if session.boss:  # always rewards at least an epic chest.
                # roll for legendary chest
                roll = random.randint(1, 100)
                if roll <= 20:
                    treasure[3] += 1
                else:
                    treasure[2] += 1
            if len(critlist) != 0:
                treasure[0] += 1
            if treasure == [0, 0, 0, 0, 0]:
                treasure = False
        if session.miniboss and failed:
            session.participants = set(
                fight_list + talk_list + pray_list + magic_list + fumblelist
            )
            currency_name = await bank.get_currency_name(ctx.guild)
            for user in session.participants:
                try:
                    c = await Character.from_json(self.config, user)
                except Exception:
                    log.exception("Error with the new character sheet")
                    continue
                multiplier = 0.1
                if c.dex != 0:
                    if c.dex < 0:
                        dex = min(1 / abs(c.dex), 1)
                    else:
                        dex = max(abs(c.dex), 3)
                    multiplier = multiplier / dex
                loss = round(c.bal * multiplier)
                if loss > c.bal:
                    loss = c.bal
                balance = c.bal
                loss = min(min(loss, balance), 1000000000)
                if c.bal > 0:
                    if user not in [u for u, t in repair_list]:
                        repair_list.append([user, loss])
                        if c.bal > loss:
                            await bank.withdraw_credits(user, loss)
                        else:
                            await bank.set_balance(user, 0)
                c.adventures.update({"loses": c.adventures.get("loses", 0) + 1})
                c.weekly_score.update({"adventures": c.weekly_score.get("adventures", 0) + 1})
                await self.config.user(user).set(c.to_json())
            loss_list = []
            result_msg += session.miniboss["defeat"]
            if len(repair_list) > 0:
                temp_repair = []
                for user, loss in repair_list:
                    if user not in temp_repair:
                        loss_list.append(
                            _("**{user}** used {loss} {currency_name}").format(
                                user=self.escape(user.display_name),
                                loss=humanize_number(loss),
                                currency_name=currency_name,
                            )
                        )
                        temp_repair.append(user)
                result_msg += _(
                    "\n{loss_list} to repay a passing cleric that unfroze the group."
                ).format(loss_list=humanize_list(loss_list))
            return await smart_embed(ctx, result_msg)
        if session.miniboss and not slain and not persuaded:
            lost = True
            session.participants = set(
                fight_list + talk_list + pray_list + magic_list + fumblelist
            )
            currency_name = await bank.get_currency_name(ctx.guild)
            for user in session.participants:
                try:
                    c = await Character.from_json(self.config, user)
                except Exception:
                    log.exception("Error with the new character sheet")
                    continue
                multiplier = 0.1
                if c.dex != 0:
                    if c.dex < 0:
                        dex = min(1 / abs(c.dex), 1)
                    else:
                        dex = max(abs(c.dex), 3)
                    multiplier = multiplier / dex
                loss = round(c.bal * multiplier)
                if loss > c.bal:
                    loss = c.bal
                balance = c.bal
                loss = min(min(loss, balance), 1000000000)
                if c.bal > 0:
                    if user not in [u for u, t in repair_list]:
                        repair_list.append([user, loss])
                        if c.bal > loss:
                            await bank.withdraw_credits(user, loss)
                        else:
                            await bank.set_balance(user, 0)
            loss_list = []
            if len(repair_list) > 0:
                temp_repair = []
                for user, loss in repair_list:
                    if user not in temp_repair:
                        loss_list.append(
                            f"**{self.escape(user.display_name)}** used {humanize_number(loss)} {currency_name}"
                        )
                        temp_repair.append(user)
            miniboss = session.challenge
            special = session.miniboss["special"]
            result_msg += _(
                "The {miniboss}'s "
                "{special} was countered, but he still managed to kill you."
                "\n{loss_l} to repay a passing "
                "cleric that resurrected the group."
            ).format(miniboss=miniboss, special=special, loss_l=humanize_list(loss_list))
        amount = 1 * session.monster_stats
        amount *= (hp + dipl) if slain and persuaded else hp if slain else dipl
        amount += int(amount * (0.25 * people))
        if people == 1:
            if slain:
                group = fighters_final_string if len(fight_list) == 1 else wizards_final_string
                text = _("{b_group} has slain the {chall} in an epic battle!").format(
                    b_group=group, chall=session.challenge
                )
                text += await self._reward(
                    ctx,
                    fight_list + magic_list + pray_list,
                    amount,
                    round(((attack if group == fighters_final_string else magic) / hp) * 0.25),
                    treasure,
                )

            if persuaded:
                text = _(
                    "{b_talkers} almost died in battle, but confounded the {chall} in the last second."
                ).format(b_talkers=talkers_final_string, chall=session.challenge)
                text += await self._reward(
                    ctx, talk_list + pray_list, amount, round((diplomacy / dipl) * 0.25), treasure
                )

            if not slain and not persuaded:
                lost = True
                currency_name = await bank.get_currency_name(ctx.guild)
                users = set(fight_list + magic_list + talk_list + pray_list + fumblelist)
                for user in users:
                    try:
                        c = await Character.from_json(self.config, user)
                    except Exception:
                        log.exception("Error with the new character sheet")
                        continue
                    multiplier = 0.1
                    if c.dex != 0:
                        if c.dex < 0:
                            dex = min(1 / abs(c.dex), 1)
                        else:
                            dex = max(abs(c.dex), 3)
                        multiplier = multiplier / dex
                    loss = round(c.bal * multiplier)
                    if loss > c.bal:
                        loss = c.bal
                    balance = c.bal
                    loss = min(min(loss, balance), 1000000000)
                    if c.bal > 0:
                        if user not in [u for u, t in repair_list]:
                            repair_list.append([user, loss])
                            if c.bal > loss:
                                await bank.withdraw_credits(user, loss)
                            else:
                                await bank.set_balance(user, 0)
                loss_list = []
                if len(repair_list) > 0:
                    temp_repair = []
                    for user, loss in repair_list:
                        if user not in temp_repair:
                            loss_list.append(
                                f"**{self.escape(user.display_name)}** used {humanize_number(loss)} {currency_name}"
                            )
                            temp_repair.append(user)
                repair_text = (
                    ""
                    if not loss_list
                    else f"{humanize_list(loss_list)} " + _("to repair their gear.")
                )
                options = [
                    _("No amount of diplomacy or valiant fighting could save you.\n{}").format(
                        repair_text
                    ),
                    _("This challenge was too much for one hero.\n{}").format(repair_text),
                    _(
                        "You tried your best, but the group couldn't succeed at their attempt.\n{}"
                    ).format(repair_text),
                ]
                text = random.choice(options)
        else:
            if slain and persuaded:
                if len(pray_list) > 0:
                    god = await self.config.god_name()
                    if await self.config.guild(ctx.guild).god_name():
                        god = await self.config.guild(ctx.guild).god_name()
                    if len(magic_list) > 0 and len(fight_list) > 0:
                        text = _(
                            "{b_fighters} slayed the {chall} "
                            "in battle, while {b_talkers} distracted with flattery, "
                            "{b_wizard} chanted magical incantations and "
                            "{b_preachers} aided in {god}'s name."
                        ).format(
                            b_fighters=fighters_final_string,
                            chall=session.challenge,
                            b_talkers=talkers_final_string,
                            b_wizard=wizards_final_string,
                            b_preachers=preachermen_final_string,
                            god=god,
                        )
                    else:
                        group = (
                            fighters_final_string if len(fight_list) > 0 else wizards_final_string
                        )
                        text = _(
                            "{b_group} slayed the {chall} "
                            "in battle, while {b_talkers} distracted with flattery and "
                            "{b_preachers} aided in {god}'s name."
                        ).format(
                            b_group=group,
                            chall=session.challenge,
                            b_talkers=talkers_final_string,
                            b_preachers=preachermen_final_string,
                            god=god,
                        )
                else:
                    if len(magic_list) > 0 and len(fight_list) > 0:
                        text = _(
                            "{b_fighters} slayed the {chall} "
                            "in battle, while {b_talkers} distracted with insults and "
                            "{b_wizard} chanted magical incantations."
                        ).format(
                            b_fighters=fighters_final_string,
                            chall=session.challenge,
                            b_talkers=talkers_final_string,
                            b_wizard=wizards_final_string,
                        )
                    else:
                        group = (
                            fighters_final_string if len(fight_list) > 0 else wizards_final_string
                        )
                        text = _(
                            "{b_group} slayed the {chall} "
                            "in battle, while {b_talkers} distracted with insults."
                        ).format(
                            b_group=group, chall=session.challenge, b_talkers=talkers_final_string
                        )
                text += await self._reward(
                    ctx,
                    fight_list + magic_list + talk_list + pray_list,
                    amount,
                    round(((dmg_dealt / hp) + (diplomacy / dipl)) * 0.25),
                    treasure,
                )

            if not slain and persuaded:
                if len(pray_list) > 0:
                    text = _(
                        "{b_talkers} talked the {chall} " "down with {b_preachers}'s blessing."
                    ).format(
                        b_talkers=talkers_final_string,
                        chall=session.challenge,
                        b_preachers=preachermen_final_string,
                    )
                else:
                    text = _("{b_talkers} talked the {chall} down.").format(
                        b_talkers=talkers_final_string, chall=session.challenge
                    )
                text += await self._reward(
                    ctx, talk_list + pray_list, amount, round((diplomacy / dipl) * 0.25), treasure
                )

            if slain and not persuaded:
                if len(pray_list) > 0:
                    if len(magic_list) > 0 and len(fight_list) > 0:
                        text = _(
                            "{b_fighters} killed the {chall} "
                            "in a most heroic battle with a little help from {b_preachers} and "
                            "{b_wizard} chanting magical incantations."
                        ).format(
                            b_fighters=fighters_final_string,
                            chall=session.challenge,
                            b_preachers=preachermen_final_string,
                            b_wizard=wizards_final_string,
                        )
                    else:
                        group = (
                            fighters_final_string if len(fight_list) > 0 else wizards_final_string
                        )
                        text = _(
                            "{b_group} killed the {chall} "
                            "in a most heroic battle with a little help from {b_preachers}."
                        ).format(
                            b_group=group,
                            chall=session.challenge,
                            b_preachers=preachermen_final_string,
                        )
                else:
                    if len(magic_list) > 0 and len(fight_list) > 0:
                        text = _(
                            "{b_fighters} killed the {chall} "
                            "in a most heroic battle with {b_wizard} chanting magical incantations."
                        ).format(
                            b_fighters=fighters_final_string,
                            chall=session.challenge,
                            b_wizard=wizards_final_string,
                        )
                    else:
                        group = (
                            fighters_final_string if len(fight_list) > 0 else wizards_final_string
                        )
                        text = _("{b_group} killed the {chall} in an epic fight.").format(
                            b_group=group, chall=session.challenge
                        )
                text += await self._reward(
                    ctx,
                    fight_list + magic_list + pray_list,
                    amount,
                    round((dmg_dealt / hp) * 0.25),
                    treasure,
                )

            if not slain and not persuaded:
                lost = True
                currency_name = await bank.get_currency_name(ctx.guild)
                users = set(fight_list + magic_list + talk_list + pray_list + fumblelist)
                for user in users:
                    try:
                        c = await Character.from_json(self.config, user)
                    except Exception:
                        log.exception("Error with the new character sheet")
                        continue
                    multiplier = 0.1
                    if c.dex != 0:
                        if c.dex < 0:
                            dex = min(1 / abs(c.dex), 1)
                        else:
                            dex = max(abs(c.dex), 3)
                        multiplier = multiplier / dex
                    loss = round(c.bal * multiplier)
                    if loss > c.bal:
                        loss = c.bal
                    balance = c.bal
                    loss = min(min(loss, balance), 1000000000)
                    if c.bal > 0:
                        if user not in [u for u, t in repair_list]:
                            repair_list.append([user, loss])
                            if c.bal > loss:
                                await bank.withdraw_credits(user, loss)
                            else:
                                await bank.set_balance(user, 0)
                if run_list:
                    users = run_list
                    for user in users:
                        try:
                            c = await Character.from_json(self.config, user)
                        except Exception:
                            log.exception("Error with the new character sheet")
                            continue
                        multiplier = 0.05
                        if c.dex != 0:
                            if c.dex < 0:
                                dex = min(1 / abs(c.dex), 1)
                            else:
                                dex = max(abs(c.dex), 3)
                            multiplier = multiplier / dex
                        loss = round(c.bal * multiplier)
                        if loss > c.bal:
                            loss = c.bal
                        balance = c.bal
                        loss = min(min(loss, balance), 1000000000)
                        if c.bal > 0:
                            if user not in [u for u, t in repair_list]:
                                repair_list.append([user, loss])
                                if user not in [u for u, t in repair_list]:
                                    if c.bal > loss:
                                        await bank.withdraw_credits(user, loss)
                                    else:
                                        await bank.set_balance(user, 0)
                loss_list = []
                if len(repair_list) > 0:
                    temp_repair = []
                    for user, loss in repair_list:
                        if user not in temp_repair:
                            loss_list.append(
                                _("**{user}** used {loss} {currency_name}").format(
                                    user=self.escape(user.display_name),
                                    loss=humanize_number(loss),
                                    currency_name=currency_name,
                                )
                            )
                            temp_repair.append(user)
                repair_text = (
                    ""
                    if not loss_list
                    else _("{} to repair their gear.").format(humanize_list(loss_list))
                )
                options = [
                    _("No amount of diplomacy or valiant fighting could save you.\n{}").format(
                        repair_text
                    ),
                    _("This challenge was too much for the group.\n{}").format(repair_text),
                    _("You tried your best, but couldn't succeed.\n{}").format(repair_text),
                ]
                text = random.choice(options)

        output = f"{result_msg}\n{text}"
        output = pagify(output)
        for i in output:
            await smart_embed(ctx, i, success=success)
        await self._data_check(ctx)
        session.participants = set(
            fight_list + magic_list + talk_list + pray_list + run_list + fumblelist
        )

        participants = {
            "fight": fight_list,
            "spell": magic_list,
            "talk": talk_list,
            "pray": pray_list,
            "run": run_list,
            "fumbles": fumblelist,
        }

        parsed_users = []
        for action_name, action in participants.items():
            for user in action:
                try:
                    c = await Character.from_json(self.config, user)
                except Exception:
                    log.exception("Error with the new character sheet")
                    continue
                current_val = c.adventures.get(action_name, 0)
                c.adventures.update({action_name: current_val + 1})
                if user not in parsed_users:
                    special_action = "loses" if lost or user in participants["run"] else "wins"
                    current_val = c.adventures.get(special_action, 0)
                    c.adventures.update({special_action: current_val + 1})
                    c.weekly_score.update({"adventures": c.weekly_score.get("adventures", 0) + 1})
                    parsed_users.append(user)
                await self.config.user(user).set(c.to_json())

    async def handle_run(self, guild_id, attack, diplomacy, magic):
        runners = []
        msg = ""
        session = self._sessions[guild_id]
        if len(list(session.run)) != 0:
            for user in session.run:
                runners.append(f"**{self.escape(user.display_name)}**")
            msg += _("{} just ran away.\n").format(humanize_list(runners))
        return (attack, diplomacy, magic, msg)

    async def handle_fight(self, guild_id, fumblelist, critlist, attack, magic, challenge):
        session = self._sessions[guild_id]
        fight_list = list(set(session.fight))
        magic_list = list(set(session.magic))
        attack_list = list(set(fight_list + magic_list))
        pdef = session.monsters[challenge]["pdef"]
        mdef = session.monsters[challenge]["mdef"]
        fumble_count = 0
        # make sure we pass this check first
        failed_emoji = self.emojis.fumble
        if len(attack_list) >= 1:
            msg = ""
            if len(fight_list) >= 1:
                # TODO: Remove me when psychic gets added
                if pdef >= 1.5:
                    msg += _(
                        "Swords bounce off this monster as it's skin is **almost impenetrable!**\n"
                    )
                elif pdef >= 1.25:
                    msg += _("This monster has **extremely tough** armour!\n")
                elif pdef > 1:
                    msg += _("Swords don't cut this monster **quite as well!**\n")
                elif 0.75 <= pdef < 1:
                    msg += _("This monster is **soft and easy** to slice!\n")
                elif pdef > 0 and pdef != 1:
                    msg += _(
                        "Swords slice through this monster like a **hot knife through butter!**\n"
                    )
            if len(magic_list) >= 1:
                if mdef >= 1.5:
                    msg += _("Magic? Pfft, your puny magic is **no match** for this creature!\n")
                elif mdef >= 1.25:
                    msg += _("This monster has **substantial magic resistance!**\n")
                elif mdef > 1:
                    msg += _("This monster has increased **magic resistance!**\n")
                elif 0.75 <= mdef < 1:
                    msg += _("This monster's hide **melts to magic!**\n")
                elif mdef > 0 and mdef != 1:
                    msg += _("Magic spells are **hugely effective** against this monster!\n")

            report = _("Attack Party: \n\n")
        else:
            return (fumblelist, critlist, attack, magic, "")

        for user in fight_list:
            try:
                c = await Character.from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                continue
            crit_mod = max(c.dex, c.luck) + (c.total_att // 20)  # Thanks GoaFan77
            mod = 0
            if crit_mod != 0:
                mod = round(crit_mod / 10)
            if (mod + 1) > 20:
                mod = 19
            roll = random.randint((1 + mod), 20)
            if c.heroclass.get("pet", {}).get("bonuses", {}).get("crit", False):
                pet_crit = c.heroclass.get("pet", {}).get("bonuses", {}).get("crit", 0)
                pet_crit = random.randint(pet_crit, 100)
                if pet_crit == 100:
                    roll = 20
                elif roll <= 15 and pet_crit >= 95:
                    roll = random.randint(15, 20)
                elif roll > 15 and pet_crit >= 95:
                    roll = random.randint(roll, 20)

            att_value = c.total_att
            if roll == 1:
                msg += _("**{}** fumbled the attack.\n").format(self.escape(user.display_name))
                fumblelist.append(user)
                fumble_count += 1
                if c.heroclass["name"] == "Berserker" and c.heroclass["ability"]:
                    bonus_roll = random.randint(5, 15)
                    bonus_multi = random.choice([0.2, 0.3, 0.4, 0.5])
                    bonus = max(bonus_roll, int((roll + att_value) * bonus_multi))
                    attack += int((roll - bonus + att_value) / pdef)
                    report += (
                        f"**{self.escape(user.display_name)}**: "
                        f"{self.emojis.dice}({roll}) + {self.emojis.berserk}{bonus} + {self.emojis.attack}{str(att_value)}\n"
                    )
            elif roll == 20 or c.heroclass["name"] == "Berserker":
                crit_str = ""
                crit_bonus = 0
                base_bonus = random.randint(5, 10) + c.rebirths // 3
                if roll == 20:
                    msg += _("**{}** landed a critical hit.\n").format(
                        self.escape(user.display_name)
                    )
                    critlist.append(user)
                    crit_bonus = random.randint(5, 20) + 2 * c.rebirths // 5
                    crit_str = f"{self.emojis.crit} {crit_bonus}"
                if c.heroclass["ability"]:
                    base_bonus = random.randint(15, 50) + 5 * c.rebirths // 10
                base_str = f"{self.emojis.crit}️ {base_bonus}"
                attack += int((roll + base_bonus + crit_bonus + att_value) / pdef)
                bonus = base_str + crit_str
                report += (
                    f"**{self.escape(user.display_name)}**: "
                    f"{self.emojis.dice}({roll}) + {self.emojis.berserk}{bonus} + {self.emojis.attack}{str(att_value)}\n"
                )
            else:
                attack += int((roll + att_value) / pdef) + c.rebirths // 5
                report += f"**{self.escape(user.display_name)}**: {self.emojis.dice}({roll}) + {self.emojis.attack}{str(att_value)}\n"
        for user in magic_list:
            try:
                c = await Character.from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                continue
            crit_mod = max(c.dex, c.luck) + (c.total_int // 20)
            mod = 0
            if crit_mod != 0:
                mod = round(crit_mod / 10)
            if (mod + 1) > 20:
                mod = 19
            roll = random.randint((1 + mod), 20)
            if c.heroclass.get("pet", {}).get("bonuses", {}).get("crit", False):
                pet_crit = c.heroclass.get("pet", {}).get("bonuses", {}).get("crit", 0)
                pet_crit = random.randint(pet_crit, 100)
                if pet_crit == 100:
                    roll = 20
                elif roll <= 15 and pet_crit >= 95:
                    roll = random.randint(15, 20)
                elif roll > 15 and pet_crit >= 95:
                    roll = random.randint(roll, 20)
            int_value = c.total_int
            if roll == 1:
                msg += _("{}**{}** almost set themselves on fire.\n").format(
                    failed_emoji, self.escape(user.display_name)
                )
                fumblelist.append(user)
                fumble_count += 1
                if c.heroclass["name"] == "Wizard" and c.heroclass["ability"]:
                    bonus_roll = random.randint(5, 15)
                    bonus_multi = random.choice([0.2, 0.3, 0.4, 0.5])
                    bonus = max(bonus_roll, int((roll + int_value) * bonus_multi))
                    magic += int((roll - bonus + int_value) / mdef)
                    report += (
                        f"**{self.escape(user.display_name)}**: "
                        f"{self.emojis.dice}({roll}) + {self.emojis.magic_crit}{bonus} + {self.emojis.magic}{str(int_value)}\n"
                    )
            elif roll == 20 or (c.heroclass["name"] == "Wizard"):
                crit_str = ""
                crit_bonus = 0
                base_bonus = random.randint(5, 10) + c.rebirths // 3
                base_str = f"{self.emojis.magic_crit}️ {base_bonus}"
                if roll == 20:
                    msg += _("**{}** had a surge of energy.\n").format(
                        self.escape(user.display_name)
                    )
                    critlist.append(user)
                    crit_bonus = random.randint(5, 20) + 2 * c.rebirths // 5
                    crit_str = f"{self.emojis.crit} {crit_bonus}"
                if c.heroclass["ability"]:
                    base_bonus = random.randint(15, 50) + 5 * c.rebirths // 10
                    base_str = f"{self.emojis.magic_crit}️ {base_bonus}"
                magic += int((roll + base_bonus + crit_bonus + int_value) / mdef)
                bonus = base_str + crit_str
                report += (
                    f"**{self.escape(user.display_name)}**: "
                    f"{self.emojis.dice}({roll}) + {bonus} + {self.emojis.magic}{str(int_value)}\n"
                )
            else:
                magic += int((roll + int_value) / mdef) + c.rebirths // 5
                report += f"**{self.escape(user.display_name)}**: {self.emojis.dice}({roll}) + {self.emojis.magic}{str(int_value)}\n"
        if fumble_count == len(attack_list):
            report += _("No one!")
        msg += report + "\n"
        for user in fumblelist:
            if user in session.fight:
                session.fight.remove(user)
            elif user in session.magic:
                session.magic.remove(user)
        return (fumblelist, critlist, attack, magic, msg)

    async def handle_pray(self, guild_id, fumblelist, attack, diplomacy, magic):
        session = self._sessions[guild_id]
        talk_list = list(set(session.talk))
        pray_list = list(set(session.pray))
        fight_list = list(set(session.fight))
        magic_list = list(set(session.magic))
        god = await self.config.god_name()
        if await self.config.guild(self.bot.get_guild(guild_id)).god_name():
            god = await self.config.guild(self.bot.get_guild(guild_id)).god_name()
        msg = ""
        failed_emoji = self.emojis.fumble
        for user in pray_list:
            try:
                c = await Character.from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                continue
            if c.heroclass["name"] == "Cleric":
                crit_mod = max(c.dex, c.luck) + (c.total_int // 20)
                mod = 0
                if crit_mod != 0:
                    mod = round(crit_mod / 10)
                if (mod + 1) > 20:
                    mod = 19
                roll = random.randint((1 + mod), 20)
                if len(fight_list + talk_list + magic_list) == 0:
                    msg += _(
                        "**{}** blessed like a madman but nobody was there to receive it.\n"
                    ).format(self.escape(user.display_name))

                if roll == 1:
                    attack -= 5 * len(fight_list)
                    diplomacy -= 5 * len(talk_list)
                    magic -= 5 * len(magic_list)
                    fumblelist.append(user)
                    msg += _(
                        "**{user}'s** sermon offended the mighty {god}. {failed_emoji}"
                        "(-{len_f_list}{attack}/-{len_t_list}{talk}/-{len_m_list}{magic})\n"
                    ).format(
                        user=self.escape(user.display_name),
                        god=god,
                        failed_emoji=failed_emoji,
                        attack=self.emojis.attack,
                        talk=self.emojis.talk,
                        magic=self.emojis.magic,
                        len_f_list=(5 * len(fight_list)),
                        len_t_list=(5 * len(talk_list)),
                        len_m_list=(5 * len(magic_list)),
                    )

                else:
                    mod = roll if not c.heroclass["ability"] else roll * 2
                    attack += mod * (len(fight_list) + c.rebirths // 5)
                    diplomacy += mod * (len(talk_list) + c.rebirths // 5)
                    magic += mod * (len(magic_list) + c.rebirths // 5)
                    if roll == 20:
                        roll_msg = _(
                            "{user} turned into an avatar of mighty {god}. "
                            "(+{len_f_list}{attack}/+{len_t_list}{talk}/+{len_m_list}{magic})\n"
                        )
                    else:
                        roll_msg = _(
                            "**{user}** blessed you all in {god}'s name. "
                            "(+{len_f_list}{attack}/+{len_t_list}{talk}/+{len_m_list}{magic})\n"
                        )
                    msg += roll_msg.format(
                        user=self.escape(user.display_name),
                        god=god,
                        attack=self.emojis.attack,
                        talk=self.emojis.talk,
                        magic=self.emojis.magic,
                        len_f_list=(mod * len(fight_list)),
                        len_t_list=(mod * len(talk_list)),
                        len_m_list=(mod * len(magic_list)),
                    )
            else:
                roll = random.randint(1, 4)
                if len(fight_list + talk_list + magic_list) == 0:
                    msg += _("**{}** prayed like a madman but nobody else helped them.\n").format(
                        self.escape(user.display_name)
                    )

                elif roll == 4:
                    attack += 10 * (len(fight_list) + c.rebirths // 15)
                    diplomacy += 10 * (len(talk_list) + c.rebirths // 15)
                    magic += 10 * (len(magic_list) + c.rebirths // 15)
                    msg += _(
                        "**{user}'s** prayer called upon the mighty {god} to help you. "
                        "(+{len_f_list}{attack}/+{len_t_list}{talk}/+{len_m_list}{magic})\n"
                    ).format(
                        user=self.escape(user.display_name),
                        god=god,
                        attack=self.emojis.attack,
                        talk=self.emojis.talk,
                        magic=self.emojis.magic,
                        len_f_list=(10 * len(fight_list)),
                        len_t_list=(10 * len(talk_list)),
                        len_m_list=(10 * len(magic_list)),
                    )
                else:
                    fumblelist.append(user)
                    msg += _("{}**{}'s** prayers went unanswered.\n").format(
                        failed_emoji, self.escape(user.display_name)
                    )
        for user in fumblelist:
            if user in pray_list:
                pray_list.remove(user)
        return (fumblelist, attack, diplomacy, magic, msg)

    async def handle_talk(self, guild_id, fumblelist, critlist, diplomacy):
        session = self._sessions[guild_id]
        talk_list = list(set(session.talk))
        if len(talk_list) >= 1:
            report = _("Talking Party: \n\n")
            msg = ""
            fumble_count = 0
        else:
            return (fumblelist, critlist, diplomacy, "")
        failed_emoji = self.emojis.fumble
        for user in talk_list:
            try:
                c = await Character.from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                continue
            crit_mod = max(c.dex, c.luck) + (c.total_int // 50) + (c.total_cha // 20)
            mod = 0
            if crit_mod != 0:
                mod = round(crit_mod / 10)
            if (mod + 1) > 20:
                mod = 19
            roll = random.randint((1 + mod), 20)
            dipl_value = c.total_cha
            if roll == 1:
                msg += _("{}**{}** accidentally offended the enemy.\n").format(
                    failed_emoji, self.escape(user.display_name)
                )
                fumblelist.append(user)
                fumble_count += 1
                if c.heroclass["name"] == "Bard" and c.heroclass["ability"]:
                    bonus = random.randint(5, 15)
                    diplomacy += roll - bonus + dipl_value
                    report += (
                        f"**{self.escape(user.display_name)}** "
                        f"🎲({roll}) +💥{bonus} +🗨{str(dipl_value)} | "
                    )
            elif roll == 20 or c.heroclass["name"] == "Bard":
                crit_str = ""
                crit_bonus = 0
                base_bonus = random.randint(5, 10) + c.rebirths // 3
                if roll == 20:
                    msg += _("**{}** made a compelling argument.\n").format(
                        self.escape(user.display_name)
                    )
                    critlist.append(user)
                    crit_bonus = random.randint(5, 20) + 2 * c.rebirths // 5
                    crit_str = f"{self.emojis.crit} {crit_bonus}"

                if c.heroclass["ability"]:
                    base_bonus = random.randint(15, 50) + 5 * c.rebirths // 10
                base_str = f"🎵 {base_bonus}"
                diplomacy += roll + base_bonus + crit_bonus + dipl_value
                bonus = base_str + crit_str
                report += (
                    f"**{self.escape(user.display_name)}** "
                    f"{self.emojis.dice}({roll}) + {bonus} + {self.emojis.talk}{str(dipl_value)}\n"
                )
            else:
                diplomacy += roll + dipl_value + c.rebirths // 5
                report += f"**{self.escape(user.display_name)}** {self.emojis.dice}({roll}) + {self.emojis.talk}{str(dipl_value)}\n"
        if fumble_count == len(talk_list):
            report += _("No one!")
        msg = msg + report + "\n"
        for user in fumblelist:
            if user in talk_list:
                session.talk.remove(user)
        return fumblelist, critlist, diplomacy, msg

    async def handle_basilisk(self, ctx: Context, failed):
        session = self._sessions[ctx.guild.id]
        fight_list = list(set(session.fight))
        talk_list = list(set(session.talk))
        pray_list = list(set(session.pray))
        magic_list = list(set(session.magic))
        if session.miniboss:
            failed = True
            item, slot = session.miniboss["requirements"]
            if item == "members" and isinstance(slot, int):
                if (len(fight_list) + len(magic_list) + len(talk_list) + len(pray_list)) > int(
                    slot
                ):
                    failed = False
            elif item == "emoji" and session.reacted:
                failed = False
            else:
                for user in (
                    fight_list + magic_list + talk_list + pray_list
                ):  # check if any fighter has an equipped mirror shield to give them a chance.
                    try:
                        c = await Character.from_json(self.config, user)
                    except Exception:
                        log.exception("Error with the new character sheet")
                        continue
                    if "Ainz Ooal Gown" in c.sets:
                        failed = False
                        break
                    try:
                        current_item = str(getattr(c, slot))
                        if item in current_item or "shiny " in current_item.lower():
                            failed = False
                            break
                    except KeyError:
                        continue

        else:
            failed = False
        return failed

    async def _add_rewards(self, ctx: Context, user, exp, cp, special):
        async with self.get_lock(user):
            try:
                c = await Character.from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            c.exp += exp
            member = ctx.guild.get_member(user.id)
            cp = max(cp, 0)
            if cp > 0:
                with contextlib.suppress(BalanceTooHigh):
                    await bank.deposit_credits(member, cp)
            extra = ""
            rebirthextra = ""
            lvl_start = c.lvl
            lvl_end = int(max(c.exp, 0) ** (1 / 3))
            lvl_end = lvl_end if lvl_end < c.maxlevel else c.maxlevel
            levelup_emoji = self.emojis.level_up
            rebirth_emoji = self.emojis.rebirth
            if lvl_end >= c.maxlevel:
                rebirthextra = _("{} You can now Rebirth {}").format(rebirth_emoji, user.mention)
            if lvl_start < lvl_end:
                # recalculate free skillpoint pool based on new level and already spent points.
                c.lvl = lvl_end
                assigned_stats = c.skill["att"] + c.skill["cha"] + c.skill["int"]
                starting_points = calculate_sp(lvl_start, c) + assigned_stats
                ending_points = calculate_sp(lvl_end, c) + assigned_stats

                if c.skill["pool"] < 0:
                    c.skill["pool"] = 0
                c.skill["pool"] += ending_points - starting_points
                if c.skill["pool"] > 0:
                    extra = _(" You have **{}** skill points available.").format(c.skill["pool"])
                await smart_embed(
                    ctx,
                    _("{} {} is now level **{}**!{}\n{}").format(
                        levelup_emoji, user.mention, lvl_end, extra, rebirthextra
                    ),
                )
            if c.rebirths > 1:
                roll = random.randint(1, 100)
                if lvl_end == c.maxlevel:
                    roll += random.randint(50, 100)
                if special is False:
                    special = [0, 0, 0, 0, 0]
                    if c.rebirths > 1 and roll < 50:
                        special[0] += 1
                    if c.rebirths > 5 and roll < 30:
                        special[1] += 1
                    if c.rebirths > 10 > roll:
                        special[2] += 1
                    if c.rebirths > 15 and roll < 5:
                        special[3] += 1
                    if special == [0, 0, 0, 0, 0]:
                        special = False
                else:
                    if c.rebirths > 1 and roll < 50:
                        special[0] += 1
                    if c.rebirths > 5 and roll < 30:
                        special[1] += 1
                    if c.rebirths > 10 > roll:
                        special[2] += 1
                    if c.rebirths > 15 and roll < 5:
                        special[3] += 1
                    if special == [0, 0, 0, 0, 0]:
                        special = False
            if special is not False:
                c.treasure = [sum(x) for x in zip(c.treasure, special)]
            await self.config.user(user).set(c.to_json())

    async def _adv_countdown(self, ctx: Context, seconds, title) -> asyncio.Task:
        await self._data_check(ctx)

        async def adv_countdown():
            secondint = int(seconds)
            adv_end = await self._get_epoch(secondint)
            timer, done, sremain = await self._remaining(adv_end)
            message_adv = await ctx.send(f"⏳ [{title}] {timer}s")
            while not done:
                timer, done, sremain = await self._remaining(adv_end)
                self._adventure_countdown[ctx.guild.id] = (timer, done, sremain)
                if done:
                    await message_adv.delete()
                    break
                elif int(sremain) % 5 == 0:
                    await message_adv.edit(content=f"⏳ [{title}] {timer}s")
                await asyncio.sleep(1)
            log.debug("Timer countdown done.")

        return ctx.bot.loop.create_task(adv_countdown())

    async def _cart_countdown(self, ctx: Context, seconds, title, room=None) -> asyncio.Task:
        room = room or ctx
        await self._data_check(ctx)

        async def cart_countdown():
            secondint = int(seconds)
            cart_end = await self._get_epoch(secondint)
            timer, done, sremain = await self._remaining(cart_end)
            message_cart = await room.send(f"⏳ [{title}] {timer}s")
            while not done:
                timer, done, sremain = await self._remaining(cart_end)
                self._trader_countdown[ctx.guild.id] = (timer, done, sremain)
                if done:
                    await message_cart.delete()
                    break
                if int(sremain) % 5 == 0:
                    await message_cart.edit(content=f"⏳ [{title}] {timer}s")
                await asyncio.sleep(1)

        return ctx.bot.loop.create_task(cart_countdown())

    @staticmethod
    async def _clear_react(msg):
        with contextlib.suppress(discord.HTTPException):
            await msg.clear_reactions()

    async def _data_check(self, ctx: Context):
        try:
            self._adventure_countdown[ctx.guild.id]
        except KeyError:
            self._adventure_countdown[ctx.guild.id] = 0
        try:
            self._rewards[ctx.author.id]
        except KeyError:
            self._rewards[ctx.author.id] = {}
        try:
            self._trader_countdown[ctx.guild.id]
        except KeyError:
            self._trader_countdown[ctx.guild.id] = 0

    @staticmethod
    async def _get_epoch(seconds: int):
        epoch = time.time()
        epoch += seconds
        return epoch

    @commands.Cog.listener()
    async def on_message_without_command(self, message):
        await self._ready_event.wait()
        if not message.guild:
            return
        channels = await self.config.guild(message.guild).cart_channels()
        if not channels:
            return
        if message.channel.id not in channels:
            return
        if not message.author.bot:
            roll = random.randint(1, 20)
            if roll == 20:
                try:
                    self._last_trade[message.guild.id]
                except KeyError:
                    self._last_trade[message.guild.id] = 0
                ctx = await self.bot.get_context(message)
                await asyncio.sleep(5)
                await self._trader(ctx)

    async def _roll_chest(self, chest_type: str, c: Character):
        # set rarity to chest by default
        rarity = chest_type
        if chest_type == "pet":
            rarity = "normal"
        INITIAL_MAX_ROLL = 400
        # max luck for best chest odds
        MAX_CHEST_LUCK = 200
        # lower gives you better chances for better items
        max_roll = INITIAL_MAX_ROLL - round(c.luck) - (c.rebirths // 2)
        top_range = max(max_roll, INITIAL_MAX_ROLL - MAX_CHEST_LUCK)
        roll = random.randint(1, top_range)
        if chest_type == "normal":
            if roll <= top_range * 0.025:  # 2.5% to roll epic
                rarity = "epic"
            elif roll <= top_range * 0.2:  # 17.5% to roll rare
                rarity = "rare"
            else:
                pass  # 80% to roll common
        elif chest_type == "rare":
            if roll <= top_range * 0.2:  # 20% to roll epic
                rarity = "epic"
            elif roll <= top_range * 0.8:  # 60% to roll rare
                pass
            else:
                rarity = "normal"  # 20% to roll normal
        elif chest_type == "epic":
            if roll <= top_range * 0.05:  # 5% to roll legendary
                rarity = "legendary"
            elif roll <= top_range * 0.85:  # 80% to roll epic
                pass
            elif roll <= top_range * 0.95:  # 10% to roll rare
                rarity = "rare"
            else:
                rarity = "normal"  # 5% to roll common
        elif chest_type == "legendary":
            if roll <= top_range * 0.55:  # 55% to roll legendary
                pass
            elif roll <= top_range * 0.95:  # 40% to roll epic
                rarity = "epic"
            else:
                rarity = "rare"  # 5% to roll rare
        elif chest_type == "pet":
            if roll <= top_range * 0.05:  # 5% to roll legendary
                rarity = "legendary"
            elif roll <= top_range * 0.15:  # 10% to roll epic
                rarity = "epic"
            elif roll <= top_range * 0.57:  # 42% to roll rare
                rarity = "rare"
            else:
                rarity = "normal"  # 47% to roll common
        elif chest_type == "set":
            if roll <= top_range * 0.55:  # 55% to roll set
                rarity = "set"
            else:
                rarity = "legendary"  # 45% to roll legendary

        return await self._genitem(rarity)

    async def _open_chests(
        self,
        ctx: Context,
        user: discord.Member,
        chest_type: str,
        amount: int,
        character: Character,
    ):
        async with self.get_lock(user):
            items = {}
            for i in range(0, max(amount, 0)):
                await asyncio.sleep(0)
                item = await self._roll_chest(chest_type, character)
                item_name = str(item)
                if item_name in items:
                    items[item_name].owned += 1
                else:
                    items[item_name] = item
                await character.add_to_backpack(item)
            await self.config.user(ctx.author).set(character.to_json())
            return items

    async def _open_chest(self, ctx: Context, user, chest_type, character):
        if hasattr(user, "display_name"):
            chest_msg = _("{} is opening a treasure chest. What riches lay inside?").format(
                self.escape(user.display_name)
            )
        else:
            chest_msg = _("{user}'s {f} is foraging for treasure. What will it find?").format(
                user=self.escape(ctx.author.display_name), f=(user[:1] + user[1:])
            )
        open_msg = await ctx.send(box(chest_msg, lang="css"))
        await asyncio.sleep(2)

        item = await self._roll_chest(chest_type, character)
        if chest_type == "pet" and not item:
            await open_msg.edit(
                content=box(
                    _("{c_msg}\nThe {user} found nothing of value.").format(
                        c_msg=chest_msg, user=(user[:1] + user[1:])
                    ),
                    lang="css",
                )
            )
            return None
        slot = item.slot[0]
        old_item = getattr(character, item.slot[0], None)
        old_stats = ""
        if old_item:
            old_slot = old_item.slot[0]
            if len(old_item.slot) > 1:
                old_slot = _("two handed")
            old_stats = (
                _("You currently have {item} [{slot}] equipped | Lvl req {lv} equipped.").format(
                    item=old_item, slot=old_slot, lv=equip_level(character, old_item)
                )
                + f" (ATT: {str(old_item.att)}, "
                f"CHA: {str(old_item.cha)}, "
                f"INT: {str(old_item.int)}, "
                f"DEX: {str(old_item.dex)}, "
                f"LUCK: {str(old_item.luck)}) "
            )
        if len(item.slot) > 1:
            slot = _("two handed")
        if hasattr(user, "display_name"):
            chest_msg2 = (
                _("{user} found {item} [{slot}] | Lvl req {lv}.").format(
                    user=self.escape(user.display_name),
                    item=str(item),
                    slot=slot,
                    lv=equip_level(character, item),
                )
                + f" (ATT: {str(item.att)}, "
                f"CHA: {str(item.cha)}, "
                f"INT: {str(item.int)}, "
                f"DEX: {str(item.dex)}, "
                f"LUCK: {str(item.luck)}) "
            )

            await open_msg.edit(
                content=box(
                    _(
                        "{c_msg}\n\n{c_msg_2}\n\nDo you want to equip "
                        "this item, put in your backpack, or sell this item?\n\n"
                        "{old_stats}"
                    ).format(c_msg=chest_msg, c_msg_2=chest_msg2, old_stats=old_stats),
                    lang="css",
                )
            )
        else:
            chest_msg2 = (
                _("The {user} found {item} [{slot}] | Lvl req {lv}.").format(
                    user=user, item=str(item), slot=slot, lv=equip_level(character, item)
                )
                + f" (ATT: {str(item.att)}, "
                f"CHA: {str(item.cha)}, "
                f"INT: {str(item.int)}, "
                f"DEX: {str(item.dex)}, "
                f"LUCK: {str(item.luck)}), "
            )
            await open_msg.edit(
                content=box(
                    _(
                        "{c_msg}\n{c_msg_2}\nDo you want to equip "
                        "this item, put in your backpack, or sell this item?\n\n{old_stats}"
                    ).format(c_msg=chest_msg, c_msg_2=chest_msg2, old_stats=old_stats),
                    lang="css",
                )
            )

        start_adding_reactions(open_msg, self._treasure_controls.keys())
        if hasattr(user, "id"):
            pred = ReactionPredicate.with_emojis(
                tuple(self._treasure_controls.keys()), open_msg, user
            )
        else:
            pred = ReactionPredicate.with_emojis(
                tuple(self._treasure_controls.keys()), open_msg, ctx.author
            )
        try:
            react, user = await self.bot.wait_for("reaction_add", check=pred, timeout=60)
        except asyncio.TimeoutError:
            await self._clear_react(open_msg)
            async with self.get_lock(ctx.author):
                await character.add_to_backpack(item)
                await open_msg.edit(
                    content=(
                        box(
                            _("{user} put the {item} into their backpack.").format(
                                user=self.escape(ctx.author.display_name), item=item
                            ),
                            lang="css",
                        )
                    )
                )
                await self.config.user(ctx.author).set(character.to_json())
            return
        await self._clear_react(open_msg)
        if self._treasure_controls[react.emoji] == "sell":
            price = self._sell(character, item)
            price = max(price, 0)
            if price > 0:
                with contextlib.suppress(BalanceTooHigh):
                    await bank.deposit_credits(ctx.author, price)
            currency_name = await bank.get_currency_name(ctx.guild)
            if str(currency_name).startswith("<"):
                currency_name = "credits"
            await open_msg.edit(
                content=(
                    box(
                        _("{user} sold the {item} for {price} {currency_name}.").format(
                            user=self.escape(ctx.author.display_name),
                            item=item,
                            price=humanize_number(price),
                            currency_name=currency_name,
                        ),
                        lang="css",
                    )
                )
            )
            await self._clear_react(open_msg)
            async with self.get_lock(ctx.author):
                await self.config.user(ctx.author).set(character.to_json())
            return
        elif self._treasure_controls[react.emoji] == "equip":
            async with self.get_lock(ctx.author):
                equiplevel = equip_level(character, item)
                if self.is_dev(ctx.author):
                    equiplevel = 0
                if not can_equip(character, item):
                    await character.add_to_backpack(item)
                    await self.config.user(ctx.author).set(character.to_json())
                    return await smart_embed(
                        ctx,
                        f"**{self.escape(ctx.author.display_name)}**, You need to be level `{equiplevel}` to equip this item, I've put it in your backpack",
                    )
                if not getattr(character, item.slot[0]):
                    equip_msg = box(
                        _("{user} equipped {item} ({slot} slot).").format(
                            user=self.escape(ctx.author.display_name), item=item, slot=slot
                        ),
                        lang="css",
                    )
                else:
                    equip_msg = box(
                        _(
                            "{user} equipped {item} "
                            "({slot} slot) and put {old_item} into their backpack."
                        ).format(
                            user=self.escape(ctx.author.display_name),
                            item=item,
                            slot=slot,
                            old_item=getattr(character, item.slot[0]),
                        ),
                        lang="css",
                    )
                await open_msg.edit(content=equip_msg)
                character = await character.equip_item(item, False, self.is_dev(ctx.author))
                await self.config.user(ctx.author).set(character.to_json())
            return
        else:
            async with self.get_lock(ctx.author):
                await character.add_to_backpack(item)
                await open_msg.edit(
                    content=(
                        box(
                            _("{user} put the {item} into their backpack.").format(
                                user=self.escape(ctx.author.display_name), item=item
                            ),
                            lang="css",
                        )
                    )
                )
                await self._clear_react(open_msg)
                await self.config.user(ctx.author).set(character.to_json())
            return

    @staticmethod
    async def _remaining(epoch):
        remaining = epoch - time.time()
        finish = remaining < 0
        m, s = divmod(remaining, 60)
        h, m = divmod(m, 60)
        s = int(s)
        m = int(m)
        h = int(h)
        if h == 0 and m == 0:
            out = "{:02d}".format(s)
        elif h == 0:
            out = "{:02d}:{:02d}".format(m, s)
        else:
            out = "{:01d}:{:02d}:{:02d}".format(h, m, s)
        return out, finish, remaining

    async def _reward(self, ctx: Context, userlist, amount, modif, special):
        if modif == 0:
            modif = 0.5
        weekend = datetime.today().weekday() in [5, 6]
        wedfriday = datetime.today().weekday() in [2, 4]
        daymult = 3 if weekend else 2 if wedfriday else 1
        xp = max(1, round(amount)) * daymult
        cp = max(1, round(amount)) * daymult
        newxp = 0
        newcp = 0
        rewards_list = []
        phrase = ""
        for user in userlist:
            self._rewards[user.id] = {}
            try:
                c = await Character.from_json(self.config, user)
            except Exception:
                log.exception("Error with the new character sheet")
                return
            userxp = int(xp + (xp * 0.1 * c.total_int))
            usercp = int(cp + (cp * c.luck) // 2)
            userxp = int(userxp * c.gear_set_bonus.get("xpmult", 1))
            usercp = int(usercp * c.gear_set_bonus.get("cpmult", 1))
            newxp += userxp
            newcp += usercp
            roll = random.randint(1, 5)
            if c.heroclass.get("pet", {}).get("bonuses", {}).get("crit", False):
                roll = 5
            if roll == 5 and c.heroclass["name"] == "Ranger" and c.heroclass["pet"]:
                petxp = int(userxp * c.heroclass["pet"]["bonus"])
                newxp += petxp
                userxp += petxp
                self._rewards[user.id]["xp"] = userxp
                petcp = int(usercp * c.heroclass["pet"]["bonus"])
                newcp += petcp
                usercp += petcp
                self._rewards[user.id]["cp"] = usercp + petcp
                percent = round((c.heroclass["pet"]["bonus"] - 1.0) * 100)
                phrase += _(
                    "\n**{user}** received a **{percent}%** reward bonus from their {pet_name}."
                ).format(
                    user=self.escape(user.display_name),
                    percent=str(percent),
                    pet_name=c.heroclass["pet"]["name"],
                )

            else:
                self._rewards[user.id]["xp"] = userxp
                self._rewards[user.id]["cp"] = usercp
            if special is not False:
                self._rewards[user.id]["special"] = special
            else:
                self._rewards[user.id]["special"] = False
            rewards_list.append(f"**{self.escape(user.display_name)}**")

        currency_name = await bank.get_currency_name(ctx.guild)
        to_reward = " and ".join(
            [", ".join(rewards_list[:-1]), rewards_list[-1]]
            if len(rewards_list) > 2
            else rewards_list
        )

        word = "has" if len(userlist) == 1 else "have"
        if special is not False and sum(special) == 1:
            types = [" normal", " rare", "n epic", " legendary", " set"]
            chest_type = types[special.index(1)]
            phrase += _(
                "\n{b_reward} {word} been awarded {xp} xp and found {cp} {currency_name} (split based on stats). "
                "You also secured **a{chest_type} treasure chest**!"
            ).format(
                b_reward=to_reward,
                word=word,
                xp=humanize_number(int(newxp)),
                cp=humanize_number(int(newcp)),
                currency_name=currency_name,
                chest_type=chest_type,
            )
        elif special is not False and sum(special) > 1:
            phrase += _(
                "\n{b_reward} {word} been awarded {xp} xp and found {cp} {currency_name} (split based on stats). "
                "You also secured **several treasure chests**!"
            ).format(
                b_reward=to_reward,
                word=word,
                xp=humanize_number(int(newxp)),
                cp=humanize_number(int(newcp)),
                currency_name=currency_name,
            )
        else:
            phrase += _(
                "\n{b_reward} {word} been awarded {xp} xp and found {cp} {currency_name} (split based on stats)."
            ).format(
                b_reward=to_reward,
                word=word,
                xp=humanize_number(int(newxp)),
                cp=humanize_number(int(newcp)),
                currency_name=currency_name,
            )
        return phrase

    @staticmethod
    def _sell(c: Character, item: Item, *, amount: int = 1):
        if item.rarity == "legendary":
            base = (1000, 2000)
        elif item.rarity == "epic":
            base = (500, 750)
        elif item.rarity == "rare":
            base = (250, 500)
        else:
            base = (10, 100)
        price = random.randint(base[0], base[1]) * item.max_main_stat
        price += price * int((c.total_cha) / 1000)

        if c.luck > 0:
            price = price + round(price * (c.luck / 1000))
        if c.luck < 0:
            price = price - round(price * (abs(c.luck) / 1000))
            if price < 0:
                price = 0
        price += round(price * min(0.1 * c.rebirths / 15, 0.4))

        return max(price, base[0])

    async def _trader(self, ctx: Context, bypass=False):
        em_list = ReactionPredicate.NUMBER_EMOJIS

        cart = await self.config.cart_name()
        if await self.config.guild(ctx.guild).cart_name():
            cart = await self.config.guild(ctx.guild).cart_name()
        text = box(_("[{} is bringing the cart around!]").format(cart), lang="css")
        timeout = await self.config.guild(ctx.guild).cart_timeout()
        if ctx.guild.id not in self._last_trade:
            self._last_trade[ctx.guild.id] = 0

        if not bypass:
            if self._last_trade[ctx.guild.id] == 0:
                self._last_trade[ctx.guild.id] = time.time()
            elif self._last_trade[ctx.guild.id] >= time.time() - timeout:
                # trader can return after 3 hours have passed since last visit.
                return  # silent return.
        self._last_trade[ctx.guild.id] = time.time()

        room = await self.config.guild(ctx.guild).cartroom()
        if room:
            room = ctx.guild.get_channel(room)
        if room is None or bypass:
            room = ctx
        self.bot.dispatch("adventure_cart", ctx)  # dispatch after silent return
        stockcount = random.randint(3, 9)
        controls = {em_list[i + 1]: i for i in range(stockcount)}
        self._curent_trader_stock[ctx.guild.id] = stockcount, controls

        stock = await self._trader_get_items(stockcount)
        currency_name = await bank.get_currency_name(ctx.guild)
        if str(currency_name).startswith("<"):
            currency_name = "credits"
        for index, item in enumerate(stock):
            item = stock[index]
            if len(item["item"].slot) == 2:  # two handed weapons add their bonuses twice
                hand = "two handed"
                att = item["item"].att * 2
                cha = item["item"].cha * 2
                intel = item["item"].int * 2
                luck = item["item"].luck * 2
                dex = item["item"].dex * 2
            else:
                if item["item"].slot[0] == "right" or item["item"].slot[0] == "left":
                    hand = item["item"].slot[0] + _(" handed")
                else:
                    hand = item["item"].slot[0] + _(" slot")
                att = item["item"].att
                cha = item["item"].cha
                intel = item["item"].int
                luck = item["item"].luck
                dex = item["item"].dex
            text += box(
                _(
                    "\n[{i}] Lvl req {lvl} | {item_name} ("
                    "Attack: {str_att}, "
                    "Intelligence: {str_int}, "
                    "Charisma: {str_cha} "
                    "Luck: {str_luck} "
                    "Dexterity: {str_dex} "
                    "[{hand}]) for {item_price} {currency_name}."
                ).format(
                    i=str(index + 1),
                    item_name=item["item"].formatted_name,
                    lvl=item["item"].lvl,
                    str_att=str(att),
                    str_int=str(intel),
                    str_cha=str(cha),
                    str_luck=str(luck),
                    str_dex=str(dex),
                    hand=hand,
                    item_price=humanize_number(item["price"]),
                    currency_name=currency_name,
                ),
                lang="css",
            )
        text += _("Do you want to buy any of these fine items? Tell me which one below:")
        msg = await room.send(text)
        start_adding_reactions(msg, controls.keys())
        self._current_traders[ctx.guild.id] = {"msg": msg.id, "stock": stock, "users": []}
        timeout = self._last_trade[ctx.guild.id] + 180 - time.time()
        if timeout <= 0:
            timeout = 0
        timer = await self._cart_countdown(ctx, timeout, _("The cart will leave in: "), room=room)
        self.tasks[msg.id] = timer
        try:
            await asyncio.wait_for(timer, timeout + 5)
        except asyncio.TimeoutError:
            await self._clear_react(msg)
            return
        with contextlib.suppress(discord.HTTPException):
            await msg.delete()

    async def _trader_get_items(self, howmany: int):
        items = {}
        output = {}

        while len(items) < howmany:
            rarity_roll = random.random()
            #  rarity_roll = .9
            # 1% legendary
            if rarity_roll >= 0.99:
                item = await self._genitem("legendary")
                # min. 10 stat for legendary, want to be about 50k
                price = random.randint(2500, 5000)
            # 20% epic
            elif rarity_roll >= 0.7:
                item = await self._genitem("epic")
                # min. 5 stat for epic, want to be about 25k
                price = random.randint(1000, 2000)
            # 35% rare
            elif rarity_roll >= 0.35:
                item = await self._genitem("rare")
                # around 3 stat for rare, want to be about 3k
                price = random.randint(500, 1000)
            else:
                item = await self._genitem("normal")
                # 1 stat for normal, want to be <1k
                price = random.randint(100, 500)
            # 35% normal
            price *= item.max_main_stat

            items.update(
                {
                    item.name: {
                        "itemname": item.name,
                        "item": item,
                        "price": price,
                        "lvl": item.lvl,
                    }
                }
            )

        for index, item in enumerate(items):
            output.update({index: items[item]})
        return output

    def cog_unload(self):
        if self.cleanup_loop:
            self.cleanup_loop.cancel()
        if self._init_task:
            self._init_task.cancel()

        for msg_id, task in self.tasks.items():
            task.cancel()

    async def get_leaderboard(
        self, positions: int = None, guild: discord.Guild = None
    ) -> List[tuple]:
        """Gets the Adventure's leaderboard.

        Parameters
        ----------
        positions : `int`
            The number of positions to get
        guild : discord.Guild
            The guild to get the leaderboard of. If this
            is provided, get only guild members on the leaderboard

        Returns
        -------
        `list` of `tuple`
            The sorted leaderboard in the form of :code:`(user_id, raw_account)`
        """
        raw_accounts = await self.config.all_users()
        if guild is not None:
            tmp = raw_accounts.copy()
            for acc in tmp:
                if not guild.get_member(acc):
                    del raw_accounts[acc]
        raw_accounts_new = {}
        for k, v in raw_accounts.items():
            user_data = {}
            for item in ["lvl", "rebirths", "set_items"]:
                if item not in v:
                    v.update({item: 0})
            for vk, vi in v.items():
                if vk in ["lvl", "rebirths", "set_items"]:
                    user_data.update({vk: vi})

            if user_data:
                user_data = {k: user_data}
            raw_accounts_new.update(user_data)
        sorted_acc = sorted(
            raw_accounts_new.items(),
            key=lambda x: (x[1].get("rebirths", 0), x[1].get("lvl", 1), x[1].get("set_items", 0)),
            reverse=True,
        )
        if positions is None:
            return sorted_acc
        else:
            return sorted_acc[:positions]

    @commands.command()
    @commands.guild_only()
    async def aleaderboard(self, ctx: Context, show_global: bool = False):
        """Print the leaderboard."""
        guild = ctx.guild
        rebirth_sorted = await self.get_leaderboard(
            guild=guild if not show_global else None, positions=40
        )
        if rebirth_sorted:
            pages = await self._format_leaderboard_pages(ctx, accounts=rebirth_sorted)
            await menu(ctx, pages, DEFAULT_CONTROLS, timeout=60)
        else:
            await smart_embed(ctx, _("There are no adventurers in the server."))

    async def get_global_scoreboard(
        self, positions: int = None, guild: discord.Guild = None, keyword: str = None
    ) -> List[tuple]:
        """Gets the bank's leaderboard.

        Parameters
        ----------
        positions : `int`
            The number of positions to get
        guild : discord.Guild
            The guild to get the leaderboard of. If this
            is provided, get only guild members on the leaderboard

        Returns
        -------
        `list` of `tuple`
            The sorted leaderboard in the form of :code:`(user_id, raw_account)`

        Raises
        ------
        TypeError
            If the bank is guild-specific and no guild was specified
        """
        if keyword is None:
            keyword = "wins"
        raw_accounts = await self.config.all_users()
        if guild is not None:
            tmp = raw_accounts.copy()
            for acc in tmp:
                if not guild.get_member(acc):
                    del raw_accounts[acc]
        raw_accounts_new = {}
        for k, v in raw_accounts.items():
            user_data = {}
            for item in ["adventures", "rebirths"]:
                if item not in v:
                    if item == "adventures":
                        v.update({item: {keyword: 0}})
                    else:
                        v.update({item: 0})

            for vk, vi in v.items():
                if vk in ["rebirths"]:
                    user_data.update({vk: vi})
                elif vk in ["adventures"]:
                    for s, sv in vi.items():
                        if s == keyword:
                            user_data.update(vi)

            if user_data:
                user_data = {k: user_data}
            raw_accounts_new.update(user_data)

        sorted_acc = sorted(
            raw_accounts_new.items(),
            key=lambda x: (x[1].get(keyword, 0), x[1].get("rebirths", 0)),
            reverse=True,
        )
        if positions is None:
            return sorted_acc
        else:
            return sorted_acc[:positions]

    @commands.command()
    @commands.guild_only()
    async def scoreboard(
        self, ctx: Context, stats: Optional[str] = None, show_global: bool = False
    ):
        """Print the scoreboard.

        Defaults to top 10 based on Wins
        """
        possible_stats = ["wins", "loses", "fight", "spell", "talk", "pray", "run", "fumbles"]
        if stats and stats.lower() not in possible_stats:
            return await smart_embed(
                ctx,
                _("Stats must be one of the following: {}").format(humanize_list(possible_stats)),
            )
        elif stats is None:
            stats = "wins"

        guild = ctx.guild
        rebirth_sorted = await self.get_global_scoreboard(
            guild=guild if not show_global else None, keyword=stats.lower(), positions=40
        )
        if rebirth_sorted:
            pages = await self._format_scoreboard_pages(
                ctx, accounts=rebirth_sorted, stats=stats.lower()
            )
            await menu(ctx, pages, DEFAULT_CONTROLS, timeout=60)
        else:
            await smart_embed(ctx, _("There are no adventurers in the server."))

    @commands.command()
    @commands.guild_only()
    async def wscoreboard(self, ctx: Context, show_global: bool = False):
        """Print the weekly scoreboard.

        Defaults to top 10 based on Wins
        """

        stats = "adventures"
        guild = ctx.guild
        adventures = await self.get_weekly_scoreboard(guild=guild if not show_global else None)
        if adventures:
            pages = await self._format_scoreboard_pages(
                ctx, accounts=adventures, stats=stats.lower(), positions=40
            )
            await menu(ctx, pages, DEFAULT_CONTROLS, timeout=60)
        else:
            await smart_embed(ctx, _("No stats to show for this week."))

    async def get_weekly_scoreboard(
        self, positions: int = None, guild: discord.Guild = None
    ) -> List[tuple]:
        """Gets the bank's leaderboard.

        Parameters
        ----------
        positions : `int`
            The number of positions to get
        guild : discord.Guild
            The guild to get the leaderboard of. If this
            is provided, get only guild members on the leaderboard

        Returns
        -------
        `list` of `tuple`
            The sorted leaderboard in the form of :code:`(user_id, raw_account)`

        Raises
        ------
        TypeError
            If the bank is guild-specific and no guild was specified
        """
        current_week = date.today().isocalendar()[1]
        keyword = "adventures"
        raw_accounts = await self.config.all_users()
        if guild is not None:
            tmp = raw_accounts.copy()
            for acc in tmp:
                if not guild.get_member(acc):
                    del raw_accounts[acc]
        raw_accounts_new = {}
        for k, v in raw_accounts.items():
            user_data = {}
            for item in ["weekly_score"]:
                if item not in v:
                    if item == "weekly_score":
                        v.update({item: {keyword: 0, "rebirths": 0}})

            for vk, vi in v.items():
                if vk in ["weekly_score"]:
                    if vi.get("week", -1) == current_week:
                        for s, sv in vi.items():
                            if s in [keyword]:
                                user_data.update(vi)

            if user_data:
                user_data = {k: user_data}
            raw_accounts_new.update(user_data)

        sorted_acc = sorted(
            raw_accounts_new.items(),
            key=lambda x: (x[1].get(keyword, 0), x[1].get("rebirths", 0)),
            reverse=True,
        )
        if positions is None:
            return sorted_acc
        else:
            return sorted_acc[:positions]

    async def _format_leaderboard_pages(self, ctx: Context, **kwargs) -> List[str]:
        _accounts = kwargs.pop("accounts", {})
        rebirth_len = len(humanize_number(_accounts[0][1]["rebirths"])) + 3
        account_number = len(_accounts)
        pos_len = len(humanize_number(account_number)) + 2

        rebirth_len = (len("Rebirths") if len("Rebirths") > rebirth_len else rebirth_len) + 2
        set_piece_len = len("Set Pieces") + 2
        level_len = len("Level") + 2
        header = f"{'#':{pos_len}}{'Rebirths':{rebirth_len}}{'Level':{level_len}}{'Set Pieces':{set_piece_len}}{'Name':2}"

        if ctx is not None:
            author = ctx.author
        else:
            author = None

        if getattr(ctx, "guild", None):
            guild = ctx.guild
        else:
            guild = None
        entries = [header]
        pages = []
        for pos, (user_id, account_data) in enumerate(_accounts, start=1):
            if guild is not None:
                member = guild.get_member(user_id)
            else:
                member = None

            if member is not None:
                username = member.display_name
            else:
                user = self.bot.get_user(user_id)
                if user is None:
                    username = user_id
                else:
                    username = user.name

            if user_id == author.id:
                # Highlight the author's position
                username = f"<<{username}>>"

            pos_str = humanize_number(pos)
            balance = humanize_number(account_data["rebirths"])
            set_items = humanize_number(account_data["set_items"])
            level = humanize_number(account_data["lvl"])

            data = (
                f"{f'{pos_str}.': <{pos_len}} "
                f"{balance: <{rebirth_len}} "
                f"{level: <{level_len}} "
                f"{set_items: <{set_piece_len}} "
                f"{username}"
            )
            entries.append(data)
            if pos % 10 == 0:
                pages.append(box("\n".join(entries), lang="md"))
                entries = [header]
            elif account_number == pos:
                pages.append(box("\n".join(entries), lang="md"))
        return pages

    async def _format_scoreboard_pages(self, ctx: Context, **kwargs) -> List[str]:
        _accounts = kwargs.pop("accounts", {})
        _importantStats = kwargs.pop("stats", "wins")
        stats_len = len(humanize_number(_accounts[0][1][_importantStats])) + 3
        account_number = len(_accounts)
        pos_len = len(humanize_number(account_number)) + 2

        stats_plural = _importantStats if _importantStats.endswith("s") else f"{_importantStats}s"
        stats_len = (len(stats_plural) if len(stats_plural) > stats_len else stats_len) + 2
        rebirth_len = len("Rebirths") + 2
        header = f"{'#':{pos_len}}{stats_plural.title().ljust(stats_len)}{'Rebirths':{rebirth_len}}{'Name':2}"

        if ctx is not None:
            author = ctx.author
        else:
            author = None

        if getattr(ctx, "guild", None):
            guild = ctx.guild
        else:
            guild = None
        entries = [header]
        pages = []
        for pos, (user_id, account_data) in enumerate(_accounts, start=1):
            if guild is not None:
                member = guild.get_member(user_id)
            else:
                member = None

            if member is not None:
                username = member.display_name
            else:
                user = self.bot.get_user(user_id)
                if user is None:
                    username = user_id
                else:
                    username = user.name

            if user_id == author.id:
                # Highlight the author's position
                username = f"<<{username}>>"

            pos_str = humanize_number(pos)
            rebirths = humanize_number(account_data["rebirths"])
            stats_value = humanize_number(account_data[_importantStats.lower()])

            data = (
                f"{f'{pos_str}.': <{pos_len}} "
                f"{stats_value: <{stats_len}} "
                f"{rebirths: <{rebirth_len}} "
                f"{username}"
            )
            entries.append(data)
            if pos % 10 == 0:
                pages.append(box("\n".join(entries), lang="md"))
                entries = [header]
            elif account_number == pos:
                pages.append(box("\n".join(entries), lang="md"))
        return pages
