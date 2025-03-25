import alltheitems.__main__ as ati

import bottle
import collections
import contextlib
import itertools
import json
import pathlib
import re
import xml.sax.saxutils

import alltheitems.item
import alltheitems.world

class FillLevel:
    def __init__(self, stack_size, total_items, max_slots):
        self.stack_size = stack_size
        self.total_items = total_items
        self.max_slots = max_slots

    def __str__(self):
        if self.total_items == 0:
            return 'SmartChest is empty'
        elif self.total_items == self.max_items:
            return 'SmartChest is full'
        else:
            stacks, items = self.stacks
            return 'SmartChest is filled {}% ({} {stack}{}{} out of {} {stack}s).'.format(int(100 * self.fraction), stacks, '' if stacks == 1 else 's', ' and {} item{}'.format(items, '' if items == 1 else 's') if items > 0 else '', self.max_slots, stack='item' if self.stack_size == 1 else 'stack')

    @property
    def fraction(self):
        return self.total_items / self.max_items

    def is_empty(self):
        return self.total_items == 0

    def is_full(self):
        return self.total_items == self.max_items

    @property
    def max_items(self):
        return self.max_slots * self.stack_size

    @property
    def stacks(self):
        return divmod(self.total_items, self.stack_size)

HOPPER_FACINGS = {
    0: 'down',
    1: 'up', #for droppers
    2: 'north',
    3: 'south',
    4: 'west',
    5: 'east'
}

HTML_COLORS = {
    'cyan': '#0ff',
    'gray': '#777',
    'red': '#f00',
    'orange': '#f70',
    'yellow': '#ff0',
    None: 'transparent'
}

def hopper_chain_connected(start_coords, end_coords, *, world=None, chunk_cache=None, block_at=None):
    if world is None:
        world = alltheitems.world.World()
    if chunk_cache is None:
        chunk_cache = {}
    if block_at is None:
        block_at=world.block_at
    visited_coords = set()
    x, y, z = start_coords
    while (x, y, z) != end_coords:
        if (x, y, z) in visited_coords:
            return False, 'hopper chain points into itself at {} {} {}'.format(x, y, z)
        visited_coords.add((x, y, z))
        block = block_at(x, y, z, chunk_cache=chunk_cache)
        if block['id'] != 'minecraft:hopper':
            return False, 'block at {} {} {} is not a <a href="/block/minecraft/hopper">hopper</a>'.format(x, y, z, *end_coords)
        if block['damage'] & 0x7 == 0:
            y -= 1 # down
        elif block['damage'] & 0x7 == 2:
            z -= 1 # north
        elif block['damage'] & 0x7 == 3:
            z += 1 # south
        elif block['damage'] & 0x7 == 4:
            x -= 1 # west
        elif block['damage'] & 0x7 == 5:
            x += 1 # east
        else:
            raise ValueError('Unknown hopper facing {} at {}'.format(block['damage'] & 0x7, (x, y, z)))
    return True, None

def smart_chest_schematic(document_root=ati.document_root):
    layers = {}
    with (document_root / 'static' / 'smartchest.txt').open() as smart_chest_layers:
        current_y = None
        current_layer = None
        for line in smart_chest_layers:
            if line == '\n':
                continue
            match = re.fullmatch('layer (-?[0-9]+)\n', line)
            if match:
                # new layer
                if current_y is not None:
                    layers[current_y] = current_layer
                current_y = int(match.group(1))
                current_layer = []
            else:
                current_layer.append(line.rstrip('\r\n'))
        if current_y is not None:
            layers[current_y] = current_layer
    return sorted(layers.items())

def chest_iter():
    """Returns an iterator yielding tuples (x, corridor, y, floor, z, chest)."""
    with (ati.assets_root / 'json' / 'cloud.json').open() as cloud_json:
        cloud_data = json.load(cloud_json)
    for y, floor in enumerate(cloud_data):
        for x, corridor in sorted(((int(x), corridor) for x, corridor in floor.items()), key=lambda tup: tup[0]):
            for z, chest in enumerate(corridor):
                yield x, corridor, y, floor, z, chest

def chest_coords(item, *, include_meta=False):
    if not isinstance(item, alltheitems.item.Item):
        item = alltheitems.item.Item(item)
    for x, corridor, y, _, z, chest in chest_iter():
        if item == chest:
            if include_meta:
                return (x, y, z), len(corridor), None if isinstance(chest, str) else chest.get('name')
            else:
                return x, y, z
    if include_meta:
        return None, 0, None

def chest_state(coords, item_stub, corridor_length, item_name=None, *, items_data=None, block_at=alltheitems.world.World().block_at, document_root=ati.document_root, chunk_cache=None):
    if items_data is None:
        with (ati.assets_root / 'json' / 'items.json').open() as items_file:
            items_data = json.load(items_file)
    if chunk_cache is None:
        chunk_cache = {}
    if isinstance(item_stub, str):
        item_stub = {'id': item_stub}
    item = alltheitems.item.Item(item_stub, items_data=items_data)
    if item_name is None:
        item_name = item.info()['name']
    state = None, None
    x, y, z = coords
    # determine the base coordinate, i.e. the position of the north half of the access chest
    if z % 2 == 0:
        # left wall
        base_x = 15 * x + 2
    else:
        # right wall
        base_x = 15 * x - 3
    base_y = 73 - 10 * y
    base_z = 28 + 10 * y + 4 * (z // 2)

    def layer_coords(layer_x, layer_y, layer_z):
        if z % 2 == 0:
            # left wall
            exact_x = base_x + 5 - layer_x
        else:
            # right wall
            exact_x = base_x - 5 + layer_x
        exact_y = base_y + layer_y
        exact_z = base_z + 3 - layer_z
        return exact_x, exact_y, exact_z

    # does the access chest exist?
    exists = False
    north_half = block_at(base_x, base_y, base_z, chunk_cache=chunk_cache)
    south_half = block_at(base_x, base_y, base_z + 1, chunk_cache=chunk_cache)
    if north_half['id'] != 'minecraft:chest' and south_half['id'] != 'minecraft:chest':
        state = 'gray', 'Access chest does not exist.'
    elif north_half['id'] != 'minecraft:chest':
        state = 'gray', 'North half of access chest does not exist.'
    elif south_half['id'] != 'minecraft:chest':
        state = 'gray', 'South half of access chest does not exist.'
    else:
        exists = True
    # does it have a SmartChest?
    has_smart_chest = False
    missing_droppers = set()
    for dropper_y in range(base_y - 7, base_y):
        dropper = block_at(base_x, dropper_y, base_z, chunk_cache=chunk_cache)
        if dropper['id'] != 'minecraft:dropper':
            missing_droppers.add(dropper_y)
    if len(missing_droppers) == 7:
        if state[0] is None:
            state = 'orange', 'SmartChest droppers do not exist.'
    elif len(missing_droppers) > 1:
        if state[0] is None:
            state = 'orange', 'SmartChest droppers at y={} do not exist.'.format(missing_droppers)
    elif len(missing_droppers) == 1:
        if state[0] is None:
            state = 'orange', 'SmartChest dropper at y={} does not exist, is {}.'.format(next(iter(missing_droppers)), block_at(base_x, dropper_y, base_z)['id'])
    else:
        has_smart_chest = True
    # is it stackable?
    stackable = item.info().get('stackable', True)
    if not stackable and state[0] is None:
        state = 'cyan', state[1]
    # does it have a sorter?
    has_sorter = False
    sorting_hopper = block_at(base_x - 2 if z % 2 == 0 else base_x + 2, base_y - 3, base_z, chunk_cache=chunk_cache)
    if sorting_hopper['id'] != 'minecraft:hopper':
        if state[0] is None:
            state = 'yellow', 'Sorting hopper does not exist, is {}.'.format(sorting_hopper['id'])
    else:
        for slot in sorting_hopper['tileEntity']['Items']:
            if slot['Slot'] == 0 and stackable and not item.matches_slot(slot) and alltheitems.item.Item('minecraft:ender_pearl', items_data=items_data).matches_slot(slot):
                if state[0] is None or state[0] == 'cyan':
                    state = 'yellow', 'Sorting hopper is full of Ender pearls, but the sorted item is stackable, so the first slot should contain the item.'
                break
        else:
            has_sorter = True
    # does it have an overflow?
    has_overflow = False
    missing_overflow_hoppers = set()
    for overflow_x in range(base_x + 3 if z % 2 == 0 else base_x - 3, base_x + 6 if z % 2 == 0 else base_x - 6, 1 if z % 2 == 0 else -1):
        overflow_hopper = block_at(overflow_x, base_y - 7, base_z - 1, chunk_cache=chunk_cache)
        if overflow_hopper['id'] != 'minecraft:hopper':
            missing_overflow_hoppers.add(overflow_x)
    if len(missing_overflow_hoppers) == 0:
        has_overflow = True
    # state determined, check for errors
    if coords == (1, 1, 0): # Ender pearls
        # error check: input hopper chain
        start = 15, 61, 30 # the last point where the Soup channel for the Cloud merges
        end = -1, 25, 52 # the half of the uppermost overflow chest into which the hopper chain is pointing
        is_connected, message = hopper_chain_connected(start, end, chunk_cache=chunk_cache, block_at=block_at)
        if not is_connected:
            return 'red', 'Input hopper chain at {} is not connected to the unsorted overflow at {}: {}.'.format(start, end, message)
    if stackable and has_sorter:
        # error check: overflow exists
        if not has_overflow:
            if len(missing_overflow_hoppers) == 3:
                return 'red', 'Missing overflow hoppers.'
            elif len(missing_overflow_hoppers) > 1:
                return 'red', 'Overflow hoppers at x={} do not exist.'.format(missing_overflow_hoppers)
            elif len(missing_overflow_hoppers) == 1:
                return 'red', 'Overflow hopper at x={} does not exist, is {}.'.format(next(iter(missing_overflow_hoppers)), block_at(next(iter(missing_overflow_hoppers)), base_y - 7, base_z - 1)['id'])
            else:
                return 'red', 'Missing overflow.'
    if has_sorter:
        # error check: sorting hopper
        if sorting_hopper['damage'] != 2:
            return 'red', 'Sorting hopper ({} {} {}) should be pointing north, but is facing {}.'.format(base_x - 2 if z % 2 == 0 else base_x + 2, base_y - 3, base_z, HOPPER_FACINGS[sorting_hopper['damage']], sorting_hopper['damage'])
        empty_slots = set(range(5))
        for slot in sorting_hopper['tileEntity']['Items']:
            empty_slots.remove(slot['Slot'])
            if slot['Slot'] == 0 and stackable:
                if not item.matches_slot(slot) and not alltheitems.item.Item('minecraft:ender_pearl', items_data=items_data).matches_slot(slot):
                    return 'red', 'Sorting hopper is sorting the wrong item: {}.'.format(alltheitems.item.Item.from_slot(slot, items_data=items_data).link_text())
            else:
                if not alltheitems.item.Item('minecraft:ender_pearl', items_data=items_data).matches_slot(slot):
                    return 'red', 'Sorting hopper has wrong filler item in slot {}: {} (should be an Ender pearl).'.format(slot['Slot'], alltheitems.item.Item.from_slot(slot, items_data=items_data).link_text())
            if alltheitems.item.Item('minecraft:ender_pearl', items_data=items_data).matches_slot(slot) and slot['Count'] > 1:
                return 'red', 'Too many Ender pearls in slot {}.'.format(slot['Slot'])
        if len(empty_slots) > 0:
            if len(empty_slots) == 5:
                return 'red', 'Sorting hopper is empty.'
            elif len(empty_slots) == 1:
                return 'red', 'Slot {} of the sorting hopper is empty.'.format(next(iter(empty_slots)))
            else:
                return 'red', 'Some slots in the sorting hopper are empty: {}.'.format(join(empty_slots))
    if exists:
        # error check: wrong items in access chest
        for slot in itertools.chain(north_half['tileEntity']['Items'], south_half['tileEntity']['Items']):
            if not item.matches_slot(slot):
                return 'red', 'Access chest contains items of the wrong kind: {}.'.format(alltheitems.item.Item.from_slot(slot, items_data=items_data).link_text())
        # error check: wrong name on sign
        sign = block_at(base_x - 1 if z % 2 == 0 else base_x + 1, base_y + 1, base_z + 1, chunk_cache=chunk_cache)
        if sign['id'] != 'minecraft:wall_sign':
            return 'red', 'Sign is missing.'
        text = []
        for line in range(1, 5):
            line_text = json.loads(sign['tileEntity']['Text{}'.format(line)])['text'].translate(dict.fromkeys(range(0xf700, 0xf704), None))
            if len(line_text) > 0:
                text.append(line_text)
        text = ' '.join(text)
        if text != item_name:
            return 'red', 'Sign has wrong text: should be {!r}, is {!r}.'.format(xml.sax.saxutils.escape(item_name), xml.sax.saxutils.escape(text))
    if has_overflow:
        # error check: overflow hopper chain
        start = base_x + 5 if z % 2 == 0 else base_x - 5, base_y - 7, base_z - 1
        end = -35, 6, 38 # position of the dropper leading into the Smelting Center's item elevator
        is_connected, message = hopper_chain_connected(start, end, chunk_cache=chunk_cache, block_at=block_at)
        if not is_connected:
            return 'red', 'Overflow hopper chain at {} is not connected to the Smelting Center item elevator at {}: {}.'.format(start, end, message)
    if exists and has_smart_chest and has_sorter and has_overflow:
        # error check: all blocks
        for layer_y, layer in smart_chest_schematic(document_root=document_root):
            for layer_x, row in enumerate(layer):
                for layer_z, block_symbol in enumerate(row):
                    # determine the coordinate of the current block
                    exact_x, exact_y, exact_z = layer_coords(layer_x, layer_y, layer_z)
                    # determine current block
                    block = block_at(exact_x, exact_y, exact_z, chunk_cache=chunk_cache)
                    # check against schematic
                    if block_symbol == ' ':
                        # air
                        if block['id'] != 'minecraft:air':
                            return 'red', 'Block at {} {} {} should be air, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                    elif block_symbol == '!':
                        # sign
                        if block['id'] != 'minecraft:wall_sign':
                            return 'red', 'Block at {} {} {} should be a sign, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        if block['damage'] != (4 if z % 2 == 0 else 5):
                            return 'red', 'Sign at {} {} {} is facing the wrong way.'.format(exact_x, exact_y, exact_z)
                    elif block_symbol == '#':
                        # chest
                        if block['id'] != 'minecraft:chest':
                            return 'red', 'Block at {} {} {} should be a chest, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        for slot in block['tileEntity']['Items']:
                            if not item.matches_slot(slot):
                                return 'red', 'Storage chest at {} {} {} contains items of the wrong kind: {}.'.format(exact_x, exact_y, exact_z, alltheitems.item.Item.from_slot(slot, items_data=items_data).link_text())
                    elif block_symbol == '<':
                        # hopper facing south
                        if block['id'] != 'minecraft:hopper':
                            return 'red', 'Block at {} {} {} should be a hopper, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        if block['damage'] & 0x7 != 3: # south
                            return 'red', 'Hopper at {} {} {} should be pointing south, is {}.'.format(exact_x, exact_y, exact_z, HOPPER_FACINGS[block['damage']])
                        pass #TODO check contents
                    elif block_symbol == '>':
                        # hopper facing north
                        if layer_y == -7 and layer_x == 0 and z < 8:
                            # the first few chests get ignored because their overflow points in the opposite direction
                            pass #TODO introduce special checks for them
                        else:
                            if block['id'] != 'minecraft:hopper':
                                return 'red', 'Block at {} {} {} should be a hopper, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                            if block['damage'] & 0x7 != 2: # north
                                return 'red', 'Hopper at {} {} {} should be pointing north, is {}.'.format(exact_x, exact_y, exact_z, HOPPER_FACINGS[block['damage']])
                            pass #TODO check contents
                    elif block_symbol == '?':
                        # any block
                        pass
                    elif block_symbol == 'C':
                        # comparator
                        if block['id'] != 'minecraft:unpowered_comparator':
                            return 'red', 'Block at {} {} {} should be a comparator, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        known_facings = {
                            (5, -7, 2): 0x2, # south
                            (5, -5, 2): 0x2, # south
                            (7, -3, 4): 0x0, # north
                            (0, -1, 1): 0x0, # north
                            (1, -1, 2): 0x0, # north
                            (2, 0, 2): 0x1 if z % 2 == 0 else 0x3, # east / west
                            (2, 0, 3): 0x2, # south
                            (4, 0, 2): 0x1 if z % 2 == 0 else 0x3, # east / west
                            (4, 0, 3): 0x2 # south
                        }
                        facing = block['damage'] & 0x3
                        if (layer_x, layer_y, layer_z) in known_facings:
                            if known_facings[layer_x, layer_y, layer_z] != facing:
                                return 'red', 'Comparator at {} {} {} is facing the wrong way.'.format(exact_x, exact_y, exact_z)
                        else:
                            return 'red', 'Direction check for comparator at {} {} {} (relative coords: {} {} {}) not yet implemented.'.format(exact_x, exact_y, exact_z, layer_x, layer_y, layer_z)
                        known_modes = {
                            (5, -7, 2): False, # compare
                            (5, -5, 2): False, # compare
                            (7, -3, 4): False, # compare
                            (0, -1, 1): False, # compare
                            (1, -1, 2): True, # subtract
                            (2, 0, 2): True, # subtract
                            (2, 0, 3): False, # compare
                            (4, 0, 2): True, #subtract
                            (4, 0, 3): False # compare
                        }
                        mode = (block['damage'] & 0x4) == 0x4
                        if (layer_x, layer_y, layer_z) in known_modes:
                            if known_modes[layer_x, layer_y, layer_z] != mode:
                                return 'red', 'Comparator at {} {} {} is in {} mode, should be in {} mode.'.format(exact_x, exact_y, exact_z, 'subtraction' if mode else 'comparison', 'subtraction' if known_modes[layer_x, layer_y, layer_z] else 'comparison')
                        else:
                            return 'red', 'Mode check for comparator at {} {} {} (relative coords: {} {} {}) not yet implemented.'.format(exact_x, exact_y, exact_z, layer_x, layer_y, layer_z)
                    elif block_symbol == 'D':
                        # dropper facing up
                        if block['id'] != 'minecraft:dropper':
                            return 'red', 'Block at {} {} {} should be a dropper, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        if block['damage'] & 0x7 != 1: # up
                            return 'red', 'Dropper at {} {} {} should be facing up, is {}.'.format(exact_x, exact_y, exact_z, HOPPER_FACINGS[block['damage']])
                        for slot in block['tileEntity']['Items']:
                            if not item.matches_slot(slot):
                                return 'red', 'Dropper at {} {} {} contains items of the wrong kind: {}.'.format(exact_x, exact_y, exact_z, alltheitems.item.Item.from_slot(slot, items_data=items_data).link_text())
                    elif block_symbol == 'F':
                        # furnace
                        if layer_y == -6 and layer_x == 0 and z < 2:
                            # the first few chests get ignored because their overflow points in the opposite direction
                            pass #TODO introduce special checks for them
                        elif layer_y == -1 and layer_x == 7 and layer_z == 1 and (z == corridor_length - 1 or z == corridor_length - 2 and z % 2 == 0):
                            # the floor ends with a quartz slab instead of a furnace here
                            if block['id'] != 'minecraft:stone_slab':
                                return 'red', 'Block at {} {} {} should be a quartz slab, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                            if block['damage'] & 0x7 != 0x7:
                                slab_variant = {
                                    0: 'stone',
                                    1: 'sandstone',
                                    2: 'fake wood',
                                    3: 'cobblestone',
                                    4: 'brick',
                                    5: 'stone brick',
                                    6: 'Nether brick',
                                    7: 'quartz'
                                }[block['damage'] & 0x7]
                                return 'red', 'Block at {} {} {} should be a <a href="/block/minecraft/stone_slab/7">quartz slab</a>, is a <a href="/block/minecraft/stone_slab/{}">{} slab</a>.'.format(exact_x, exact_y, exact_z, block['damage'] & 0x7, slab_variant)
                            if block['damage'] & 0x8 != 0x8:
                                return 'red', 'Quartz slab at {} {} {} should be a top slab, is a bottom slab.'.format(exact_x, exact_y, exact_z)
                        else:
                            if block['id'] != 'minecraft:furnace':
                                return 'red', 'Block at {} {} {} should be a furnace, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                            known_signals = {
                                (0, -6, 4): 0,
                                (0, -6, 5): 0,
                                (0, -6, 6): 0,
                                (0, -6, 7): 0,
                                (0, -1, 0): 8,
                                (7, -1, 1): 0,
                                (7, -1, 2): 0,
                                (7, -1, 3): 0,
                                (7, -1, 4): 0,
                                (2, 0, 4): 1,
                                (4, 0, 4): 5
                            }
                            signal = alltheitems.item.comparator_signal(block, items_data=items_data)
                            if (layer_x, layer_y, layer_z) in known_signals:
                                if known_signals[layer_x, layer_y, layer_z] != signal:
                                    return 'red', 'Furnace at {} {} {} has a fill level of {}, should be {}.'.format(exact_x, exact_y, exact_z, signal, known_signals[layer_x, layer_y, layer_z])
                            else:
                                return 'red', 'Fill level check for furnace at {} {} {} (relative coords: {} {} {}) not yet implemented.'.format(exact_x, exact_y, exact_z, layer_x, layer_y, layer_z)
                    elif block_symbol == 'G':
                        # glowstone
                        if block['id'] != 'minecraft:glowstone':
                            return 'red', 'Block at {} {} {} should be glowstone, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                    elif block_symbol == 'N':
                        # overflow hopper chain pointing down
                        if y > 1 and (z == 0 or z == 1):
                            if block['id'] != 'minecraft:hopper':
                                return 'red', 'Block at {} {} {} should be a hopper, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                            if block['damage'] != 2: # north
                                return 'red', 'Overflow hopper at {} {} {} should be pointing north, is {}.'.format(exact_x, exact_y, exact_z, HOPPER_FACINGS[block['damage']])
                        else:
                            if block['id'] != 'minecraft:air':
                                return 'red', 'Block at {} {} {} should be air, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                    elif block_symbol == 'P':
                        # upside-down oak stairs
                        if block['id'] != 'minecraft:oak_stairs':
                            return 'red', 'Block at {} {} {} should be oak stairs, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        if block['damage'] & 0x3 != (0x1 if z % 2 == 0 else 0x0):
                            stairs_facings = {
                                0: 'west',
                                1: 'east',
                                2: 'south',
                                3: 'north'
                            }
                            return 'red', 'Stairs at {} {} {} should be facing {}, is {}.'.format(exact_x, exact_y, exact_z, stairs_facings[0x1 if z % 2 == 0 else 0x0], stairs_facings[block['damage'] & 0x3])
                        if block['damage'] & 0x4 != 0x4:
                            return 'red', 'Stairs at {} {} {} should be upside-down.'.format(exact_x, exact_y, exact_z)
                    elif block_symbol == 'Q':
                        # quartz top slab
                        if block['id'] != 'minecraft:stone_slab':
                            return 'red', 'Block at {} {} {} should be a quartz slab, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        if block['damage'] & 0x7 != 0x7:
                            slab_variant = {
                                0: 'stone',
                                1: 'sandstone',
                                2: 'fake wood',
                                3: 'cobblestone',
                                4: 'brick',
                                5: 'stone brick',
                                6: 'Nether brick',
                                7: 'quartz'
                            }[block['damage'] & 0x7]
                            return 'red', 'Block at {} {} {} should be a <a href="/block/minecraft/stone_slab/7">quartz slab</a>, is a <a href="/block/minecraft/stone_slab/{}">{} slab</a>.'.format(exact_x, exact_y, exact_z, block['damage'] & 0x7, slab_variant)
                        if block['damage'] & 0x8 != 0x8:
                            return 'red', 'Quartz slab at {} {} {} should be a top slab, is a bottom slab.'.format(exact_x, exact_y, exact_z)
                    elif block_symbol == 'R':
                        # repeater
                        if block['id'] not in ('minecraft:unpowered_repeater', 'minecraft:powered_repeater'):
                            return 'red', 'Block at {} {} {} should be a repeater, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        known_facings = {
                            (1, -8, 2): 0x0, # north
                            (3, -8, 3): 0x3 if z % 2 == 0 else 0x1, # west / east
                            (6, -6, 2): 0x0, # north
                            (7, -5, 5): 0x2, # south
                            (3, -3, 1): 0x1 if z % 2 == 0 else 0x3 # east / west
                        }
                        facing = block['damage'] & 0x3
                        if (layer_x, layer_y, layer_z) in known_facings:
                            if known_facings[layer_x, layer_y, layer_z] != facing:
                                return 'red', 'Repeater at {} {} {} is facing the wrong way.'.format(exact_x, exact_y, exact_z)
                        else:
                            return 'red', 'Direction check for repeater at {} {} {} (relative coords: {} {} {}) not yet implemented.'.format(exact_x, exact_y, exact_z, layer_x, layer_y, layer_z)
                        known_delays = { # in game ticks
                            (1, -8, 2): 4,
                            (3, -8, 3): 2,
                            (6, -6, 2): 2,
                            (7, -5, 5): 2,
                            (3, -3, 1): 2
                        }
                        delay_ticks = 2 * (block['damage'] >> 2) + 2
                        if (layer_x, layer_y, layer_z) in known_delays:
                            if known_delays[layer_x, layer_y, layer_z] != delay_ticks:
                                return 'red', 'Repeater at {} {} {} has a delay of {} game tick{}, should be {}.'.format(exact_x, exact_y, exact_z, delay_ticks, '' if delay_ticks == 1 else 's', known_delays[layer_x, layer_y, layer_z])
                        else:
                            return 'red', 'Delay check for repeater at {} {} {} (relative coords: {} {} {}) not yet implemented.'.format(exact_x, exact_y, exact_z, layer_x, layer_y, layer_z)
                    elif block_symbol == 'S':
                        # stone top slab
                        if block['id'] != 'minecraft:stone_slab':
                            return 'red', 'Block at {} {} {} should be a stone slab, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        if block['damage'] & 0x7 != 0x0:
                            slab_variant = {
                                0: 'stone',
                                1: 'sandstone',
                                2: 'fake wood',
                                3: 'cobblestone',
                                4: 'brick',
                                5: 'stone brick',
                                6: 'Nether brick',
                                7: 'quartz'
                            }[block['damage'] & 0x7]
                            return 'red', 'Block at {} {} {} should be a <a href="/block/minecraft/stone_slab/0">stone slab</a>, is a <a href="/block/minecraft/stone_slab/{}">{} slab</a>.'.format(exact_x, exact_y, exact_z, block['damage'] & 0x7, slab_variant)
                        if block['damage'] & 0x8 != 0x8:
                            return 'red', 'Quartz slab at {} {} {} should be a top slab.'.format(exact_x, exact_y, exact_z)
                    elif block_symbol == 'T':
                        # redstone torch attached to the side of a block
                        if block['id'] not in ('minecraft:unlit_redstone_torch', 'minecraft:redstone_torch'):
                            return 'red', 'Block at {} {} {} should be a redstone torch, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        pass #TODO check facing
                    elif block_symbol == 'W':
                        # back wall
                        if z == corridor_length - 1 or z == corridor_length - 2 and z % 2 == 0:
                            if block['id'] != 'minecraft:stone':
                                return 'red', 'Block at {} {} {} should be stone, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                            if block['damage'] != 0:
                                stone_variant = {
                                    0: 'stone',
                                    1: 'granite',
                                    2: 'polished granite',
                                    3: 'diorite',
                                    4: 'polished diorite',
                                    5: 'andesite',
                                    6: 'polished andesite'
                                }[block['damage']]
                                return 'red', 'Block at {} {} {} should be <a href="/block/minecraft/stone/0">regular stone</a>, is <a href="/block/minecraft/stone/{}">{}</a>.'.format(exact_x, exact_y, exact_z, block['damage'], stone_variant)
                    elif block_symbol == 'X':
                        # overflow hopper chain pointing down
                        if layer_y < -7 and y < 6 and (z == 4 or z == 5) or layer_y > -7 and y > 1 and (z == 0 or z == 1):
                            if block['id'] != 'minecraft:hopper':
                                return 'red', 'Block at {} {} {} should be a hopper, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                            if block['damage'] != 0: # down
                                return 'red', 'Overflow hopper at {} {} {} should be pointing down, is {}.'.format(exact_x, exact_y, exact_z, HOPPER_FACINGS[block['damage']])
                        else:
                            if block['id'] != 'minecraft:air':
                                return 'red', 'Block at {} {} {} should be air, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                    elif block_symbol == '^':
                        # hopper facing outward
                        if block['id'] != 'minecraft:hopper':
                            return 'red', 'Block at {} {} {} should be a hopper, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        if block['damage'] & 0x7 != (5 if z % 2 == 0 else 4): # east / west
                            return 'red', 'Hopper at {} {} {} should be pointing {}, is {}.'.format(exact_x, exact_y, exact_z, 'east' if z % 2 == 0 else 'west', HOPPER_FACINGS[block['damage']])
                        pass #TODO check contents
                    elif block_symbol == 'c':
                        # crafting table
                        if layer_y == -7 and (z < 4 or z < 6 and layer_z > 1):
                            if block['id'] != 'minecraft:stone':
                                return 'red', 'Block at {} {} {} should be stone, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                            pass #TODO check damage
                        else:
                            if block['id'] != 'minecraft:crafting_table':
                                return 'red', 'Block at {} {} {} should be a crafting table, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                    elif block_symbol == 'i':
                        # torch attached to the top of a block
                        if block['id'] != 'minecraft:torch':
                            return 'red', 'Block at {} {} {} should be a torch, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        pass #TODO check facing
                    elif block_symbol == 'p':
                        # oak planks
                        if layer_y == -8 and (z < 4 or z < 6 and layer_z > 1):
                            if block['id'] != 'minecraft:stone':
                                return 'red', 'Block at {} {} {} should be stone, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                            pass #TODO check damage
                        else:
                            if block['id'] != 'minecraft:planks':
                                return 'red', 'Block at {} {} {} should be oak planks, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                            pass #TODO check material
                    elif block_symbol == 'r':
                        # redstone dust
                        if block['id'] != 'minecraft:redstone_wire':
                            return 'red', 'Block at {} {} {} should be redstone, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                    elif block_symbol == 's':
                        # stone
                        if block['id'] != 'minecraft:stone':
                            return 'red', 'Block at {} {} {} should be stone, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        if block['damage'] != 0:
                            stone_variant = {
                                0: 'stone',
                                1: 'granite',
                                2: 'polished granite',
                                3: 'diorite',
                                4: 'polished diorite',
                                5: 'andesite',
                                6: 'polished andesite'
                            }[block['damage']]
                            return 'red', 'Block at {} {} {} should be <a href="/block/minecraft/stone/0">regular stone</a>, is <a href="/block/minecraft/stone/{}">{}</a>.'.format(exact_x, exact_y, exact_z, block['damage'], stone_variant)
                    elif block_symbol == 't':
                        # redstone torch attached to the top of a block
                        if block['id'] not in ('minecraft:unlit_redstone_torch', 'minecraft:redstone_torch'):
                            return 'red', 'Block at {} {} {} should be a redstone torch, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        pass #TODO check facing
                    elif block_symbol == 'v':
                        # hopper facing inwards
                        if block['id'] != 'minecraft:hopper':
                            return 'red', 'Block at {} {} {} should be a hopper, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        if block['damage'] & 0x7 != (4 if z % 2 == 0 else 5): # west / east
                            return 'red', 'Hopper at {} {} {} should be pointing {}, is {}.'.format(exact_x, exact_y, exact_z, 'west' if z % 2 == 0 else 'east', HOPPER_FACINGS[block['damage']])
                        pass #TODO check contents
                    elif block_symbol == 'x':
                        # hopper facing down
                        if block['id'] != 'minecraft:hopper':
                            return 'red', 'Block at {} {} {} should be a hopper, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        if block['damage'] & 0x7 != 0: # down
                            return 'red', 'Hopper at {} {} {} should be pointing down, is {}.'.format(exact_x, exact_y, exact_z, HOPPER_FACINGS[block['damage']])
                        pass #TODO check contents
                    elif block_symbol == '~':
                        # hopper chain
                        if block['id'] == 'minecraft:hopper':
                            pass #TODO check facing
                            pass #TODO check alignment
                        elif block['id'] == 'minecraft:air':
                            pass #TODO check alignment
                        else:
                            return 'red', 'Block at {} {} {} should be a hopper or air, is {}.'.format(exact_x, exact_y, exact_z, block['id'])
                        pass #TODO check hopper chain integrity
                    else:
                        return 'red', 'Not yet implemented: block at {} {} {} should be {}.'.format(exact_x, exact_y, exact_z, block_symbol)
    if state[0] is None or state[0] == 'cyan':
        containers = [ # layer coords of all counted container blocks in the SmartChest
            (3, -7, 3),
            (3, -7, 4),
            (4, -7, 4),
            (5, -7, 3),
            (5, -7, 4),
            (2, -6, 3),
            (3, -6, 2),
            (3, -6, 3),
            (2, -5, 2),
            (2, -5, 3),
            (3, -5, 3),
            (2, -4, 3),
            (3, -4, 2),
            (3, -4, 3),
            (3, -3, 2),
            (4, -3, 2),
            (5, -3, 2),
            (6, -3, 2),
            (5, -2, 2),
            (6, -2, 2),
            (5, -1, 2),
            (5, 0, 2),
            (5, 0, 3)
        ]
        total_items = sum(sum(slot['Count'] for slot in block_at(*layer_coords(*container), chunk_cache=chunk_cache)['tileEntity']['Items']) for container in containers)
        max_slots = sum(alltheitems.item.NUM_SLOTS[block_at(*layer_coords(*container), chunk_cache=chunk_cache)['id']] for container in containers)
        return state[0], FillLevel(item.max_stack_size(), total_items, max_slots)
    return state

def cell_from_chest(coords, item_stub, corridor_length, item_name=None, *, chunk_cache=None, items_data=None, colors_to_explain=None):
    color, state_message = chest_state(coords, item_stub, corridor_length, item_name, items_data=items_data, chunk_cache=chunk_cache)
    if colors_to_explain is not None:
        colors_to_explain.add(color)
    if isinstance(state_message, FillLevel) and not state_message.is_full():
        return '<td>{}<div class="durability"><div style="background-color: white; width: {}px;"></div></div></td>'.format(alltheitems.item.Item(item_stub, items_data=items_data).image(), int(state_message.fraction * 14) * 2)
    else:
        return '<td style="background-color: {};">{}</td>'.format(HTML_COLORS[color], alltheitems.item.Item(item_stub, items_data=items_data).image())

def index():
    yield ati.header(title='Cloud')
    def body():
        yield '<p>The <a href="http://wiki.{host}/Cloud">Cloud</a> is the public item storage on <a href="http://{host}/">Wurstmineberg</a>, consisting of 6 underground floors with <a href="http://wiki.{host}/SmartChest">SmartChests</a> in them.</p>'.format(host=ati.host)
        yield """<style type="text/css">
            .item-table td {
                box-sizing: content-box;
                height: 32px;
                width: 32px;
                position: relative;
            }

            .item-table .left-sep {
                border-left: 1px solid gray;
            }

            .durability {
                z-index: 1;
            }
        </style>"""
        chunk_cache = {}
        with (ati.assets_root / 'json' / 'items.json').open() as items_file:
            items_data = json.load(items_file)
        colors_to_explain = set()
        floors = {}
        for x, corridor, y, floor, z, chest in chest_iter():
            if y not in floors:
                floors[y] = floor
        for y, floor in sorted(floors.items(), key=lambda tup: tup[0]):
            def cell(coords, item_stub, corridor):
                if isinstance(item_stub, str):
                    item_stub = {'id': item_stub}
                    item_name = None
                elif 'name' in item_stub:
                    item_name = item_stub['name']
                    item_stub = item_stub.copy()
                    del item_stub['name']
                else:
                    item_name = None
                return cell_from_chest(coords, item_stub, len(corridor), item_name, chunk_cache=chunk_cache, colors_to_explain=colors_to_explain, items_data=items_data)

            yield bottle.template("""
                %import itertools
                <h2 id="floor{{y}}">{{y}}{{ati.ordinal(y)}} floor (y={{73 - 10 * y}})</h2>
                <table class="item-table" style="margin-left: auto; margin-right: auto;">
                    %for x in range(-3, 4):
                        %if x > -3:
                            <colgroup class="left-sep">
                                <col />
                                <col />
                            </colgroup>
                        %else:
                            <colgroup>
                                <col />
                                <col />
                            </colgroup>
                        %end
                    %end
                    <tbody>
                        %for z_left, z_right in zip(itertools.count(step=2), itertools.count(start=1, step=2)):
                            %found = False
                            <tr>
                                %for x in range(-3, 4):
                                    %if str(x) not in floor:
                                        <td></td>
                                        <td></td>
                                        %continue
                                    %end
                                    %corridor = floor[str(x)]
                                    %if len(corridor) > z_right:
                                        {{!cell((x, y, z_right), corridor[z_right], corridor)}}
                                    %else:
                                        <td></td>
                                    %end
                                    %if len(corridor) > z_left:
                                        {{!cell((x, y, z_left), corridor[z_left], corridor)}}
                                        %found = True
                                    %else:
                                        <td></td>
                                    %end
                                %end
                            </tr>
                            %if not found:
                                %break
                            %end
                        %end
                    </tbody>
                </table>
            """, ati=ati, cell=cell, floor=floor, y=y)
        color_explanations = collections.OrderedDict([
            ('red', '<p>A red background means that there is something wrong with the chest. See the item info page for details.</p>'),
            ('gray', "<p>A gray background means that the chest hasn't been built yet or is still located somewhere else.</p>"),
            ('orange', "<p>An orange background means that the chest doesn't have a SmartChest yet. It can only store 54 stacks.</p>"),
            ('yellow', "<p>A yellow background means that the chest doesn't have a sorter yet.</p>"),
            ('cyan', '<p>A cyan background means that the chest has no sorter because it stores an unstackable item. These items should not be automatically <a href="http://wiki.wurstmineberg.de/Soup#Cloud">sent</a> to the Cloud.</p>'),
            (None, '<p>A white background means that everything is okay: the chest has a SmartChest, a sorter, and overflow protection.</p>)')
        ])
        for chest_color in colors_to_explain:
            if chest_color is not None or len(colors_to_explain) > 1:
                yield color_explanations[chest_color]
    yield from ati.html_exceptions(body())
    yield ati.footer(linkify_headers=True)

def todo():
    yield ati.header(title='Cloud by priority')
    def body():
        yield """<style type="text/css">
            .todo-table td {
                text-align: left;
                vertical-align: middle;
            }

            .todo-table .coord {
                width: 3em;
                text-align: right;
            }

            .todo-table .item-image {
                box-sizing: content-box;
                width: 32px;
            }

            .todo-table .item-name {
                width: 24em;
            }
        </style>"""

        headers = collections.OrderedDict([
            ('red', 'Build errors'),
            ('gray', 'Missing chests'),
            ('orange', 'Missing SmartChests'),
            ('yellow', 'Missing sorters'),
            ('cyan', 'Missing items (unstackable)'),
            (None, 'Missing items (stackable)')
        ])
        header_indexes = {color: i for i, color in enumerate(headers.keys())}

        def priority(pair):
            coords, state = pair
            x, y, z = coords
            color, state_message, item_name = state
            return header_indexes[color], state_message.fraction if isinstance(state_message, FillLevel) else None, y * (-1 if color == 'orange' else 1), x * (-1 ** y), z

        chunk_cache = {}
        with (ati.assets_root / 'json' / 'items.json').open() as items_file:
            items_data = json.load(items_file)
        states = {}
        current_color = None
        for x, corridor, y, _, z, item_stub in chest_iter():
            if isinstance(item_stub, str):
                item_stub = {'id': item_stub}
                item_name = None
            elif 'name' in item_stub:
                item_name = item_stub['name']
                item_stub = item_stub.copy()
                del item_stub['name']
            else:
                item_name = None
            color, state_message = chest_state((x, y, z), item_stub, len(corridor), item_name, items_data=items_data, chunk_cache=chunk_cache)
            if not isinstance(state_message, FillLevel) or not state_message.is_full():
                states[x, y, z] = color, state_message, alltheitems.item.Item(item_stub, items_data=items_data)
        for coords, state in sorted(states.items(), key=priority):
            x, y, z = coords
            color, state_message, item = state
            if color != current_color:
                if current_color is not None:
                    yield '</tbody></table>'
                yield bottle.template('<h2 id="{{color}}">{{header}}</h2>', color='white' if color is None else color, header=headers[color])
                yield '<table class="todo-table table table-responsive"><thead><tr><th class="coord">X</th><th class="coord">Y</th><th class="coord">Z</th><th class="item-image">&nbsp;</th><th class="item-name">Item</th><th>{}</th></tr></thead><tbody>'.format('Fill Level' if color is None or color == 'cyan' else 'Info')
                current_color = color
            yield bottle.template("""
                <tr>
                    <td class="coord">{{x}}</td>
                    <td class="coord">{{y}}</td>
                    <td class="coord">{{z}}</td>
                    <td class="item-image">{{!item.image()}}</td>
                    <td class="item-name">{{!item.link_text()}}</td>
                    <td style="background-color: {{color}}">{{state_message}}</td>
                </tr>
            """, x=x, y=y, z=z, item=item, color=HTML_COLORS[color], state_message=state_message)
        yield '</tbody></table>'
    yield from ati.html_exceptions(body())
    yield ati.footer(linkify_headers=True)
