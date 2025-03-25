# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Ftube.com/ree Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import bpy
from copy import copy
from mathutils import *
from math import radians
from bpy.props import StringProperty
from bpy.props import IntProperty
from bpy.props import FloatProperty
from bpy.props import CollectionProperty
from bpy.props import PointerProperty
from bpy.props import BoolProperty
from bpy.types import PropertyGroup
from lindenmayer_system_parser import LindenmayerSystemParser, Token

bl_info = {
    "name"     : "Lindenmayer system",
    "author"   : "Alexander Stante",
    "version"  : (0, 1, 0),
    "blender"  : (2, 70, 0),
    "location" : "View3D > Add > Curve",
    "category" : "Add Curve",
    "warning"  : "Under development"
}

def draw_rule(layout, rule, index):
    """Draw a Lindenmayer rule on the layout
    
    layout -- the layout to draw on
    rule   -- the rule to be drawn
    index  -- the index of the rule in the rule collection
    """
    col = layout.column(align=True)
    box = col.box()

    row = box.row()

    # Extended arrow
    prop = row.operator("lindenmayer_system.production_show_extended", 
                        icon='TRIA_DOWN' if rule.show_extended else 'TRIA_RIGHT', 
                        emboss=False)
    prop.index = index

    # Rule string
    row.prop(rule, "rule", icon='NONE' if rule.is_valid else 'ERROR')

    rowmove = row.row(align=True)
   
    # Move up
    op = rowmove.operator("lindenmayer_system.production_move", icon='TRIA_UP')
    op.direction = 'UP'
    op.index = index
    
    # Move down
    op = rowmove.operator("lindenmayer_system.production_move", icon='TRIA_DOWN')
    op.direction = 'DOWN'
    op.index = index
    
    # Remove rule
    prop = row.operator("lindenmayer_system.production_remove", icon='X', emboss=False)
    prop.index = index

    # Extendend properties
    if rule.show_extended:
        box = col.box()
        col = box.column()
        col.prop(rule, "probability")
        
    return box

def check_rule(self, context):
    if self.parser.rule_valid(self.rule):
        self.is_valid = True
    else:
        self.is_valid = False


class ProductionItem(bpy.types.PropertyGroup):
    is_valid = BoolProperty(True)
    rule = StringProperty(name="", default="F:=F", update=check_rule)

    show_extended = BoolProperty(default=True)

    probability = FloatProperty(name="Probability",
                                min=0,
                                max=1,
                                default=1)

    parser = LindenmayerSystemParser()
    
    def get_parsed(self):
        p = self.parser.parse(self.rule)
        
        return (p[0], p[2:])


class ProductionShowExtended(bpy.types.Operator):
    bl_idname = "lindenmayer_system.production_show_extended"
    bl_label = ""

    index = IntProperty()
    
    def execute(self, context):
        settings = context.active_operator
        settings.productions[self.index].show_extended = not settings.productions[self.index].show_extended
        
        return {'FINISHED'}

class ProductionMove(bpy.types.Operator):
    bl_idname = "lindenmayer_system.production_move"
    bl_label = ""

    direction = StringProperty()
    index = IntProperty()

    def execute(self, context):
        rules = context.active_operator.productions
        if self.direction == 'UP' and self.index > 0:
            rules.move(self.index, self.index - 1)
        elif self.direction == 'DOWN' and self.index < len(rules) - 1:
            rules.move(self.index, self.index + 1)

        return {'FINISHED'}

class ProductionRemove(bpy.types.Operator):
    bl_idname = "lindenmayer_system.production_remove"
    bl_label = ""

    index = IntProperty()

    def execute(self, context):
        context.active_operator.productions.remove(self.index)

        return {'FINISHED'}

class ProductionAdd(bpy.types.Operator):
    """Operator to add a new rule to the Lindenmayer System

    Adds a new rule by adding a ProductionItem to the production collection
    """
    bl_idname = "lindenmayer_system.production_add"
    bl_label = ""

    def execute(self, context):
        settings = context.active_operator

        if settings.production.is_valid:
            prop = settings.productions.add()
            prop.rule = settings.production.rule

        return {'FINISHED'}

class LindenmayerSystem(bpy.types.Operator):
    """Construct turtle based on active object"""
    bl_idname = "curve.lindenmayer_system"
    bl_label = "Create L-system"
    bl_options = {'REGISTER', 'UNDO', 'PRESET'}
    
    start_symbol = StringProperty(name="Start Symbol", default="F")
    production = PointerProperty(type=ProductionItem, name="Production")

    iterations = IntProperty(name="Iterations",
                             min=0,
                             max=8,
                             default=0,
                             description="Iterations - number of rule applications")
    
    angle = FloatProperty(name="Angle", 
                              subtype="ANGLE",
                              unit='ROTATION',
                              default=radians(60))
    
    bevel_depth = FloatProperty(name="Depth",
                                min=0,
                                precision=3,
                                step=0.1,
                                default=0)

    bevel_resolution = IntProperty(name="Resolution",
                                   min=0,
                                   max=32,
                                   default=0)
    
    basic_length = FloatProperty(name="Length",
                                 min=0, 
                                 default=2)

    productions = CollectionProperty(type=ProductionItem)

    @classmethod
    def poll(cls, context):
        return True
        
    def execute(self, context):
        self.apply_turtle(self)

        return {'FINISHED'}

    def invoke(self, context, event):
        return self.execute(context)

    def draw(self, context):
        settings = context.active_operator
        layout = self.layout
        column = layout.column()

        # Rules
        column.label("Rules:")
        row = column.row(align=True)
        row.prop(settings.production, "rule", icon='NONE' if settings.production.is_valid
                 else 'ERROR')
        row.operator("lindenmayer_system.production_add", icon='ZOOMIN')

        for idx, prop in enumerate(settings.productions):
            draw_rule(column, prop, idx)

        # Settings
        column.separator()
        column.label("Settings:")
        column.prop(settings, "start_symbol")
        column.prop(settings, "iterations")
        column.prop(settings, "angle")
        column.prop(settings, "bevel_depth")
        column.prop(settings, "bevel_resolution")
        column.prop(settings, "basic_length")

    def apply_turtle(self, settings):
        direction = Vector((0, 0, 1))
        trans = Movement(direction)
        stack = []

        # Create start token
        start = [Token(type='SYMBOL', value=settings.start_symbol)]

        # Construct dictionary rules
        rules = {}
        for production in settings.productions:
            l, r = production.get_parsed()
            if l.value in rules:
                rules[l.value].append(r)
            else:
                rules[l.value] = [r]

        system = apply_rules(start, rules, settings.iterations)
        length = calculate_length(system, settings.basic_length)

        # Create new curve object
        curve = bpy.data.curves.new('LSystem', 'CURVE')
        curve.dimensions = '3D'
        curve.fill_mode = 'FULL'
        curve.bevel_depth = settings.bevel_depth
        curve.bevel_resolution = settings.bevel_resolution
        curve.resolution_u = 1

        obj = bpy.data.objects.new('LSystem', curve)
        bpy.context.scene.objects.link(obj)
        
        spline = branch(curve, Vector((0, 0, 0)))

        for token in system:
            if (token.type == 'SYMBOL'):
                if (token.value == 'F'):
                    grow(spline, trans, length)
                    continue

            if (token.type == 'DIRECTION'):
                if (token.value == '+'):
                    trans.yaw(settings.angle)
                    continue
                
                if (token.value == '-'):
                    trans.yaw(-settings.angle)
                    continue
                
                if (token.value == '^'):
                    trans.pitch(settings.angle)
                    continue

                if (token.value == '&'):
                    trans.pitch(-settings.angle)
                    continue

                if (token.value == '\\'):
                    trans.roll(settings.angle)
                    continue

                if (token.value == '/'):
                    trans.roll(-settings.angle)
                    continue

            if (token.type == 'PUSH'):
                stack.append((spline, copy(trans)))

                spline = branch(curve, spline.bezier_points[-1].co)
                continue

            if (token.type == 'POP'):
                if len(spline.bezier_points) == 1:
                    curve.splines.remove(spline)

                spline, trans = stack.pop()
                continue

def system_to_human(system):
    string = ""
    for token in system:
        if token.type == 'SYMBOL' or token.type == 'DIRECTION' or token.type == 'PUSH' or token.type == 'POP':
            string += token.value

    return string

def apply_single_rule(start, rules):
    lsystem = []
    for token in start:
        if token.type == 'SYMBOL':
            if token.value in rules:
                lsystem.extend(rules[token.value][0])
            else:
                lsystem.append(token)
        else:
            lsystem.append(token)

    return lsystem
    
def apply_rules(start, rules, times):
    lsystem = start

    for i in range(times):
        lsystem = apply_single_rule(lsystem, rules)

    return lsystem

def calculate_length(system, basic_length):
    cnt = 0
    stack = []

    for token in system:
        if token.type == 'SYMBOL' and token.value == 'F' and not stack:
            cnt+=1
            continue

        if token.type == 'PUSH':
            stack.append('[')

        if token.type == 'POP':
            stack.pop()

    return basic_length / cnt if cnt else 0
        
def grow(spline, movement, amount):
    direction = movement.get_vector()
    if movement.has_changed() or len(spline.bezier_points) == 1:
        # Add second point
        spline.bezier_points.add()
        newpoint = spline.bezier_points[-1]
        oldpoint = spline.bezier_points[-2]
        newpoint.co = oldpoint.co
        
    newpoint = spline.bezier_points[-1]
    oldpoint = spline.bezier_points[-2]
    direction = direction * amount

    newpoint.co = newpoint.co + direction

    oldpoint.handle_left = oldpoint.co - direction
    oldpoint.handle_right = oldpoint.co + direction
    newpoint.handle_left = newpoint.co - direction
    newpoint.handle_right = newpoint.co + direction
    
def branch(curve, position):
    """Creates a branch in curve at position
    
    Arguments:
    curve    -- Blender curve
    position -- Starting point of the new branch
    """

    # New spline (automatically creates a bezier point)
    spline = new_spline(curve, position)

    # Add second point
    # spline.bezier_points.add()
    # newpoint = spline.bezier_points[-1]
    # oldpoint = spline.bezier_points[-2]
    # newpoint.co = oldpoint.co
    
    return spline

def new_spline(curve, position):
    curve.splines.new('BEZIER')
    spline = curve.splines[-1]
    spline.bezier_points[-1].co = position
    return spline

    
def menu_func(self, context):
    self.layout.operator(LindenmayerSystem.bl_idname, text="L-system", icon='PLUGIN')

def register():
    bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_curve_add.append(menu_func)

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.INFO_MT_curve_add.remove(menu_func)

class Movement:

    def __init__(self, vector):
        self._has_changed = True
        self._vector = vector

    def rotate(self, amount, axis):
        self._has_changed = True
        self._vector = self._vector * Matrix.Rotation(amount, 3, axis)

    def yaw(self, amount):
        self._has_changed = True
        self.rotate(amount, 'X')

    def pitch(self, amount):
        self._has_changed = True
        self.rotate(amount, 'Y')

    def roll(self, amount):
        self._has_changed = True
        self.rotate(amount, 'Z')

    def get_vector(self):
        return self._vector

    def has_changed(self):
        if self._has_changed:
            self._has_changed = False
            return True
        else:
            return False
            

if __name__ == '__main__':
    register()
