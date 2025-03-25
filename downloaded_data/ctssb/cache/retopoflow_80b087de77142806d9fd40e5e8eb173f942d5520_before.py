'''
Copyright (C) 2014 CG Cookie
http://cgcookie.com
hello@cgcookie.com

Created by Jonathan Denning, Jonathan Williamson, and Patrick Moore

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

bl_info = {
    "name":        "RetopoFlow",
    "description": "A suite of dedicated retopology tools for Blender",
    "author":      "Jonathan Denning, Jonathan Williamson, Patrick Moore",
    "version":     (1, 0, 0),
    "blender":     (2, 7, 2),
    "location":    "View 3D > Tool Shelf",
    "warning":     "",  # used for warning icon and text in addons panel
    "wiki_url":    "http://cgcookiemarkets.com/blender/all-products/retopoflow/?view=docs",
    "tracker_url": "https://github.com/CGCookie/retopoflow/issues",
    "category":    "3D View"
    }


# System imports
import os
import sys

import copy
import math
import random
import time
from math import sqrt
from mathutils import Vector, Matrix, Quaternion
from mathutils.geometry import intersect_line_plane, intersect_point_line

# Blender imports
import bgl
import blf
import bmesh
import bpy
from bpy.props import EnumProperty, StringProperty, BoolProperty, IntProperty, FloatVectorProperty, FloatProperty
from bpy.types import Operator, AddonPreferences
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_vector_3d, region_2d_to_location_3d

# Common imports
from .lib import common_utilities
from .lib import common_drawing
from .lib.common_utilities import get_object_length_scale, dprint, profiler, frange, selection_mouse, showErrorMessage
from .lib.common_classes import SketchBrush

# Polystrip imports
from . import polystrips_utilities
from .polystrips import *
from .polystrips_draw import *

# Contour imports
from . import contour_utilities
from .contour_classes import ContourCutLine, ExistingVertList, CutLineManipulatorWidget, ContourCutSeries, ContourStatePreserver

# Create a class that contains all location information for addons
AL = common_utilities.AddonLocator()

#a place to store stokes for later
global contour_cache 
contour_cache = {}
contour_undo_cache = []

#store any temporary triangulated objects
#store the bmesh to prevent recalcing bmesh
#each time :-)
global contour_mesh_cache
contour_mesh_cache = {}

# Used to store undo snapshots
polystrips_undo_cache = []


class RetopoFlowPreferences(AddonPreferences):
    bl_idname = __name__
    
    def update_theme(self, context):
        print('theme updated to ' + str(theme))

    # Theme definitions
    theme = EnumProperty(
        items=[
            ('blue', 'Blue', 'Blue color scheme'),
            ('green', 'Green', 'Green color scheme'),
            ('orange', 'Orange', 'Orange color scheme'),
            ],
        name='theme',
        default='blue'
        )

    def rgba_to_float(r, g, b, a):
        return (r/255.0, g/255.0, b/255.0, a/255.0)

    theme_colors_active = {
        'blue': rgba_to_float(78, 207, 81, 255),
        'green': rgba_to_float(26, 111, 255, 255),
        'orange': rgba_to_float(207, 135, 78, 255)
    }
    theme_colors_selection = {
        'blue': rgba_to_float(78, 207, 81, 255),
        'green': rgba_to_float(26, 111, 255, 255),
        'orange': rgba_to_float(207, 135, 78, 255)
    }
    theme_colors_mesh = {
        'blue': rgba_to_float(26, 111, 255, 255),
        'green': rgba_to_float(78, 207, 81, 255),
        'orange': rgba_to_float(26, 111, 255, 255)
    }

    # User settings
    show_segment_count = BoolProperty(
        name='Show Selected Segment Count',
        description='Show segment count on selection',
        default=True
        )

    use_pressure = BoolProperty(
        name='Use Pressure Sensitivity',
        description='Adjust size of Polystrip with pressure of tablet pen',
        default=False
        )

    # Tool settings
    contour_panel_settings = BoolProperty(
        name="Show Contour Settings",
        description = "Show the Contour settings",
        default=False,
        )

    # System settings
    quad_prev_radius = IntProperty(
        name="Pixel Brush Radius",
        description="Pixel brush size",
        default=15,
        )

    undo_depth = IntProperty(
        name="Undo Depth",
        description="Max number of undo steps",
        default=15,
        )
    
    show_edges = BoolProperty(
            name="Show Span Edges",
            description = "Display the extracted mesh edges. Usually only turned off for debugging",
            default=True,
            )
    
    show_ring_edges = BoolProperty(
            name="Show Ring Edges",
            description = "Display the extracted mesh edges. Usually only turned off for debugging",
            default=True,
            )

    draw_widget = BoolProperty(
            name="Draw Widget",
            description = "Turn display of widget on or off",
            default=True,
            )
    
    show_axes = BoolProperty(
            name = "show_axes",
            description = "Show Cut Axes",
            default = False)

    show_experimental = BoolProperty(
            name="Enable Experimental",
            description = "Enable experimental features and functions that are still in development, useful for experimenting and likely to crash",
            default=False,
            )
    
    vert_size = IntProperty(
            name="Vertex Size",
            default=4,
            min = 1,
            max = 10,
            )
    edge_thick = IntProperty(
            name="Edge Thickness",
            default=1,
            min=1,
            max=10,
            )

    theme = EnumProperty(
        items=[
            ('blue', 'Blue', 'Blue color scheme'),
            ('green', 'Green', 'Green color scheme'),
            ('orange', 'Orange', 'Orange color scheme'),
            ],
        name='theme',
        default='blue'
        )
    
    #TODO  Theme this out nicely :-) 
    widget_color = FloatVectorProperty(name="Widget Color", description="Choose Widget color", min=0, max=1, default=(0,0,1), subtype="COLOR")
    widget_color2 = FloatVectorProperty(name="Widget Color", description="Choose Widget color", min=0, max=1, default=(1,0,0), subtype="COLOR")
    widget_color3 = FloatVectorProperty(name="Widget Color", description="Choose Widget color", min=0, max=1, default=(0,1,0), subtype="COLOR")
    widget_color4 = FloatVectorProperty(name="Widget Color", description="Choose Widget color", min=0, max=1, default=(0,0.2,.8), subtype="COLOR")
    widget_color5 = FloatVectorProperty(name="Widget Color", description="Choose Widget color", min=0, max=1, default=(.9,.1,0), subtype="COLOR")
 
    handle_size = IntProperty(
            name="Handle Vertex Size",
            default=8,
            min = 1,
            max = 10,
            )
    
    line_thick = IntProperty(
            name="Line Thickness",
            default=1,
            min = 1,
            max = 10,
            )
    
    stroke_thick = IntProperty(
            name="Stroke Thickness",
            description = "Width of stroke lines drawn by user",
            default=1,
            min = 1,
            max = 10,
            )
    
    auto_align = BoolProperty(
            name="Automatically Align Vertices",
            description = "Attempt to automatically align vertices in adjoining edgeloops. Improves outcome, but slows performance",
            default=True,
            )
    
    live_update = BoolProperty(
            name="Live Update",
            description = "Will live update the mesh preview when transforming cut lines. Looks good, but can get slow on large meshes",
            default=True,
            )
    
    use_x_ray = BoolProperty(
            name="X-Ray",
            description = 'Enable X-Ray on Retopo-mesh upon creation',
            default=False,
            )
    
    use_perspective = BoolProperty(
            name="Use Perspective",
            description = 'Make non parallel cuts project from the same view to improve expected outcome',
            default=True,
            )
    
    widget_radius = IntProperty(
            name="Widget Radius",
            description = "Size of cutline widget radius",
            default=25,
            min = 20,
            max = 100,
            )
    
    widget_radius_inner = IntProperty(
            name="Widget Inner Radius",
            description = "Size of cutline widget inner radius",
            default=10,
            min = 5,
            max = 30,
            )
    
    widget_thickness = IntProperty(
            name="Widget Line Thickness",
            description = "Width of lines used to draw widget",
            default=2,
            min = 1,
            max = 10,
            )
    
    widget_thickness2 = IntProperty(
            name="Widget 2nd Line Thick",
            description = "Width of lines used to draw widget",
            default=4,
            min = 1,
            max = 10,
            )
        
    arrow_size = IntProperty(
            name="Arrow Size",
            default=12,
            min=5,
            max=50,
            )   
    
    arrow_size2 = IntProperty(
            name="Translate Arrow Size",
            default=10,
            min=5,
            max=50,
            )      
    
    vertex_count = IntProperty(
            name = "Vertex Count",
            description = "The Number of Vertices Per Edge Ring",
            default=10,
            min = 3,
            max = 250,
            )
    
    ring_count = IntProperty(
        name="Ring Count",
        description="The Number of Segments Per Guide Stroke",
        default=10,
        min=3,
        max=100,
        )

    cyclic = BoolProperty(
            name = "Cyclic",
            description = "Make contour loops cyclic",
            default = False)
    
    recover = BoolProperty(
            name = "Recover",
            description = "Recover strokes from last session",
            default = False)
    
    recover_clip = IntProperty(
            name = "Recover Clip",
            description = "Number of cuts to leave out, usually set to 0 or 1",
            default=1,
            min = 0,
            max = 10,
            )
    
    search_factor = FloatProperty(
            name = "Search Factor",
            description = "Factor of existing segment length to connect a new cut",
            default=5,
            min = 0,
            max = 30,
            )
        
    intersect_threshold = FloatProperty(
            name = "Intersect Factor",
            description = "Stringence for connecting new strokes",
            default=1.,
            min = .000001,
            max = 1,
            )
    
    merge_threshold = FloatProperty(
            name = "Intersect Factor",
            description = "Distance below which to snap strokes together",
            default=1.,
            min = .000001,
            max = 1,
            )
    
    cull_factor = IntProperty(
            name = "Cull Factor",
            description = "Fraction of screen drawn points to throw away. Bigger = less detail",
            default = 4,
            min = 1,
            max = 10,
            )
    
    smooth_factor = IntProperty(
            name = "Smooth Factor",
            description = "Number of iterations to smooth drawn strokes",
            default = 5,
            min = 1,
            max = 10,
            )
    
    feature_factor = IntProperty(
            name = "Smooth Factor",
            description = "Fraction of sketch bounding box to be considered feature. Bigger = More Detail",
            default = 4,
            min = 1,
            max = 20,
            )
    
    extend_radius = IntProperty(
            name="Snap/Extend Radius",
            default=20,
            min=5,
            max=100,
            )

    undo_depth = IntProperty(
            name="Undo Depth",
            default=10,
            min = 0,
            max = 100,
            )

    ## Debug Settings
    show_debug = BoolProperty(
            name="Show Debug Settings",
            description = "Show the debug settings, useful for troubleshooting",
            default=False,
            )

    debug = IntProperty(
        name="Debug Level",
        default=1,
        min=0,
        max=4,
        )

    raw_vert_size = IntProperty(
            name="Raw Vertex Size",
            default=1,
            min = 1,
            max = 10,
            )

    simple_vert_inds = BoolProperty(
            name="Simple Inds",
            default=False,
            )
    
    vert_inds = BoolProperty(
            name="Vert Inds",
            description = "Display indices of the raw contour verts",
            default=False,
            )

    show_backbone = BoolProperty(
            name = "show_backbone",
            description = "Show Cut Series Backbone",
            default = False)

    show_nodes = BoolProperty(
            name = "show_nodes",
            description = "Show Cut Nodes",
            default = False)

    show_ring_inds = BoolProperty(
            name = "show_ring_inds",
            description = "Show Ring Indices",
            default = False)

    show_verts = BoolProperty(
            name="Show Raw Verts",
            description = "Display the raw contour verts",
            default=False,
            )

    show_cut_indices = BoolProperty(
            name="Show Cut Indices",
            description = "Display the order the operator stores cuts. Usually only turned on for debugging",
            default=False,
            )

    new_method = BoolProperty(
            name="New Method",
            description = "Use robust cutting, may be slower, more accurate on dense meshes",
            default=True,
            )


    def draw(self, context):
        
        # Polystrips 
        layout = self.layout

        row = layout.row(align=True)
        row.prop(self, "theme", "Theme")

        row = layout.row(align=True)
        row.prop(self, "use_pressure")
        row.prop(self, "show_segment_count")

        row = layout.row(align=True)
        row.prop(self, "debug") 

        # Contours
        layout = self.layout

        # Interaction Settings
        row = layout.row(align=True)
        row.prop(self, "auto_align")
        row.prop(self, "live_update")
        row.prop(self, "use_perspective")
        
        row = layout.row()
        row.prop(self, "use_x_ray", "Enable X-Ray at Mesh Creation")
        
        # Visualization Settings
        box = layout.box().column(align=False)
        row = box.row()
        row.label(text="Stroke And Loop Settings")        

        row = box.row(align=False)
        row.prop(self, "handle_size", text="Handle Size")
        row.prop(self, "stroke_thick", text="Stroke Thickness")

        row = box.row(align=False)
        row.prop(self, "show_edges", text="Show Edge Loops")
        row.prop(self, "line_thick", text ="Edge Thickness")
        
        row = box.row(align=False)
        row.prop(self, "show_ring_edges", text="Show Edge Rings")
        row.prop(self, "vert_size")

        row = box.row(align=True)
        row.prop(self, "show_cut_indices", text = "Edge Indices")
        
        # Widget Settings
        box = layout.box().column(align=False)
        row = box.row()
        row.label(text="Widget Settings")

        row = box.row()
        row.prop(self,"draw_widget", text = "Display Widget")

        if self.draw_widget:
            row = box.row()
            row.prop(self, "widget_radius", text="Radius")
            row.prop(self,"widget_radius_inner", text="Active Radius")
            
            row = box.row()
            row.prop(self, "widget_thickness", text="Line Thickness")
            row.prop(self, "widget_thickness2", text="2nd Line Thickness")
            row.prop(self, "arrow_size", text="Arrow Size")
            row.prop(self, "arrow_size2", text="Translate Arrow Size")

        # Debug Settings
        box = layout.box().column(align=False)
        row = box.row()
        row.label(text="Debug Settings")

        row = box.row()
        row.prop(self, "show_debug", text="Show Debug Settings")
        
        if self.show_debug:
            row = box.row()
            row.prop(self, "new_method")
            row.prop(self, "debug")
            
            
            row = box.row()
            row.prop(self, "vert_inds", text="Show Vertex Indices")
            row.prop(self, "simple_vert_inds", text="Show Simple Indices")

            row = box.row()
            row.prop(self, "show_verts", text="Show Raw Vertices")
            row.prop(self, "raw_vert_size")
            
            row = box.row()
            row.prop(self, "show_backbone", text="Show Backbone")
            row.prop(self, "show_nodes", text="Show Cut Nodes")
            row.prop(self, "show_ring_inds", text="Show Ring Indices")


class CGCOOKIE_OT_retopoflow_panel(bpy.types.Panel):
    '''RetopoFlow Tools'''
    bl_category = "Retopology"
    bl_label = "RetopoFlow"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    @classmethod
    def poll(cls, context):
        mode = bpy.context.mode
        obj = context.active_object
        return (obj and obj.type == 'MESH' and mode in ('OBJECT', 'EDIT_MESH'))

    def draw(self, context):
        layout = self.layout

        settings = common_utilities.get_settings()

        col = layout.column(align=True)
        col.operator("cgcookie.contours", icon='IPO_LINEAR')

        box = layout.box()
        row = box.row()

        row.prop(settings, "contour_panel_settings")

        if settings.contour_panel_settings:
            col = box.column()
            col.prop(settings, "vertex_count")

            col.label("Guide Mode:")
            col.prop(settings, "ring_count")

            col.label("Cache:")
            col.prop(settings, "recover", text="Recover")

            if settings.recover:
                col.prop(settings, "recover_clip")

            col.operator("cgcookie.contours_clear_cache", text = "Clear Cache", icon = 'CANCEL')

        col = layout.column(align=True)
        col.operator("cgcookie.polystrips", icon='IPO_BEZIER')


class CGCOOKIE_OT_retopoflow_menu(bpy.types.Menu):  
    bl_label = "Retopology"
    bl_space_type = 'VIEW_3D'
    bl_idname = "object.retopology_menu"

    def draw(self, context):
        layout = self.layout

        layout.operator_context = 'INVOKE_DEFAULT'

        layout.operator("cgcookie.contours", icon="IPO_LINEAR")
        layout.operator("cgcookie.polystrips", icon="IPO_BEZIER")


################### Contours ###################

def object_validation(ob):
    me = ob.data

    # get object data to act as a hash
    counts = (len(me.vertices), len(me.edges), len(me.polygons), len(ob.modifiers))
    bbox   = (tuple(min(v.co for v in me.vertices)), tuple(max(v.co for v in me.vertices)))
    vsum   = tuple(sum((v.co for v in me.vertices), Vector((0,0,0))))

    return (ob.name, counts, bbox, vsum)


def is_object_valid(ob):
    global contour_mesh_cache
    if 'valid' not in contour_mesh_cache: return False
    return contour_mesh_cache['valid'] == object_validation(ob)


def write_mesh_cache(orig_ob,tmp_ob, bme):
    print('writing mesh cache')
    global contour_mesh_cache
    clear_mesh_cache()
    contour_mesh_cache['valid'] = object_validation(orig_ob)
    contour_mesh_cache['bme'] = bme
    contour_mesh_cache['tmp'] = tmp_ob


def clear_mesh_cache():
    print('clearing mesh cache')

    global contour_mesh_cache

    if 'valid' in contour_mesh_cache and contour_mesh_cache['valid']:
        del contour_mesh_cache['valid']

    if 'bme' in contour_mesh_cache and contour_mesh_cache['bme']:
        bme_old = contour_mesh_cache['bme']
        bme_old.free()
        del contour_mesh_cache['bme']

    if 'tmp' in contour_mesh_cache and contour_mesh_cache['tmp']:
        old_obj = contour_mesh_cache['tmp']
        #context.scene.objects.unlink(self.tmp_ob)
        old_me = old_obj.data
        old_obj.user_clear()
        if old_obj and old_obj.name in bpy.data.objects:
            bpy.data.objects.remove(old_obj)
        if old_me and old_me.name in bpy.data.meshes:
            bpy.data.meshes.remove(old_me)
        del contour_mesh_cache['tmp']


class CGCOOKIE_OT_contours_cache_clear(bpy.types.Operator):
    '''Removes the temporary object and mesh data from the cache. Do this if you have altered your original form in any way'''
    bl_idname = "cgcookie.contours_clear_cache"
    bl_label = "Clear Contour Cache" 

    def execute(self,context):

        clear_mesh_cache()

        return {'FINISHED'}


def retopo_draw_callback(self,context):

    settings = common_utilities.get_settings()

    if (self.post_update or self.modal_state == 'NAVIGATING') and context.space_data.use_occlude_geometry:
        for path in self.cut_paths:
            path.update_visibility(context, self.original_form)
            for cut_line in path.cuts:
                cut_line.update_visibility(context, self.original_form)
                    
        self.post_update = False
        

    for i, c_cut in enumerate(self.cut_lines):
        if self.widget_interaction and self.drag_target == c_cut:
            interact = True
        else:
            interact = False
        
        c_cut.draw(context, settings,three_dimensional = self.navigating, interacting = interact)

        if c_cut.verts_simple != [] and settings.show_cut_indices:
            loc = location_3d_to_region_2d(context.region, context.space_data.region_3d, c_cut.verts_simple[0])
            blf.position(0, loc[0], loc[1], 0)
            blf.draw(0, str(i))


    if self.cut_line_widget and settings.draw_widget:
        self.cut_line_widget.draw(context)
        
    if len(self.draw_cache):
        common_drawing.draw_polyline_from_points(context, self.draw_cache, (1,.5,1,.8), 2, "GL_LINE_SMOOTH")
        
    if len(self.cut_paths):
        for path in self.cut_paths:
            path.draw(context, path = True, nodes = settings.show_nodes, rings = True, follows = True, backbone = settings.show_backbone    )
            
    if len(self.snap_circle):
        common_drawing.draw_polyline_from_points(context, self.snap_circle, self.snap_color, 2, "GL_LINE_SMOOTH")

  
class CGCOOKIE_OT_contours(bpy.types.Operator):
    '''Draw Strokes Perpindicular to Cylindrical Forms to Retopologize Them'''
    bl_idname = "cgcookie.contours"
    bl_label = "Contours"
    
    @classmethod
    def poll(cls,context):
        if context.mode not in {'EDIT_MESH','OBJECT'}:
            return False
        elif context.object.type != 'MESH':
            return False
        else:
            return True

    def hover_guide_mode(self,context, settings, event):
        '''
        handles mouse selection, hovering, highlighting
        and snapping when the mouse moves in guide
        mode
        '''
        
        # Identify hover target for highlighting
        if self.cut_paths != []:
            target_at_all = False
            breakout = False
            for path in self.cut_paths:
                if not path.select:
                    path.unhighlight(settings)
                for c_cut in path.cuts:                    
                    h_target = c_cut.active_element(context,event.mouse_region_x,event.mouse_region_y)
                    if h_target:
                        path.highlight(settings)
                        target_at_all = True
                        self.hover_target = path
                        breakout = True
                        break
                
                if breakout:
                    break
                                  
            if not target_at_all:
                self.hover_target = None
        
        # Assess snap points
        if self.cut_paths != [] and not self.force_new:
            rv3d = context.space_data.region_3d
            breakout = False
            snapped = False
            for path in self.cut_paths:
                
                end_cuts = []
                if not path.existing_head and len(path.cuts):
                    end_cuts.append(path.cuts[0])
                if not path.existing_tail and len(path.cuts):
                    end_cuts.append(path.cuts[-1])
                    
                if path.existing_head and not len(path.cuts):
                    end_cuts.append(path.existing_head)
                    
                for n, end_cut in enumerate(end_cuts):
                    
                    # Potential verts to snap to
                    snaps = [v for i, v in enumerate(end_cut.verts_simple) if end_cut.verts_simple_visible[i]]
                    # The screen versions os those
                    screen_snaps = [location_3d_to_region_2d(context.region,rv3d,snap) for snap in snaps]
                    
                    mouse = Vector((event.mouse_region_x,event.mouse_region_y))
                    dists = [(mouse - snap).length for snap in screen_snaps]
                    
                    if len(dists):
                        best = min(dists)
                        if best < 2 * settings.extend_radius and best > 4: #TODO unify selection mouse pixel radius.

                            best_vert = screen_snaps[dists.index(best)]
                            view_z = rv3d.view_rotation * Vector((0,0,1))
                            if view_z.dot(end_cut.plane_no) > -.75 and view_z.dot(end_cut.plane_no) < .75:

                                imx = rv3d.view_matrix.inverted()
                                normal_3d = imx.transposed() * end_cut.plane_no
                                if n == 1 or len(end_cuts) == 1:
                                    normal_3d = -1 * normal_3d
                                screen_no = Vector((normal_3d[0],normal_3d[1]))
                                angle = math.atan2(screen_no[1],screen_no[0]) - 1/2 * math.pi
                                left = angle + math.pi
                                right =  angle
                                self.snap = [path, end_cut]
                                
                                if end_cut.desc == 'CUT_LINE' and len(path.cuts) > 1:
    
                                    self.snap_circle = contour_utilities.pi_slice(best_vert[0],best_vert[1],settings.extend_radius,.1 * settings.extend_radius, left,right, 20,t_fan = True)
                                    self.snap_circle.append(self.snap_circle[0])
                                else:
                                    self.snap_circle = contour_utilities.simple_circle(best_vert[0], best_vert[1], settings.extend_radius, 20)
                                    self.snap_circle.append(self.snap_circle[0])
                                    
                                breakout = True
                                if best < settings.extend_radius:
                                    snapped = True
                                    self.snap_color = (1,0,0,1)
                                    
                                else:
                                    alpha = 1 - best/(2*settings.extend_radius)
                                    self.snap_color = (1,0,0,alpha)
                                    
                                break
                        
                    if breakout:
                        break
                    
            if not breakout:
                self.snap = []
                self.snap_circle = []


    def hover_loop_mode(self,context, settings, event):
        '''
        Handles mouse selection and hovering
        '''
        # Identify hover target for highlighting
        if self.cut_paths != []:
            
            new_target = False
            target_at_all = False
            
            for path in self.cut_paths:
                for c_cut in path.cuts:
                    if not c_cut.select:
                        c_cut.unhighlight(settings) 
                    
                    h_target = c_cut.active_element(context,event.mouse_region_x,event.mouse_region_y)
                    if h_target:
                        c_cut.highlight(settings)
                        target_at_all = True
                         
                        if (h_target != self.hover_target) or (h_target.select and not self.cut_line_widget):
                            
                            self.hover_target = h_target
                            if self.hover_target.desc == 'CUT_LINE':

                                if self.hover_target.select:
                                    for possible_parent in self.cut_paths:
                                        if self.hover_target in possible_parent.cuts:
                                            parent_path = possible_parent
                                            break
                                            
                                    self.cut_line_widget = CutLineManipulatorWidget(context, 
                                                                                    settings,
                                                                                    self.original_form, self.bme,
                                                                                    self.hover_target,
                                                                                    parent_path,
                                                                                    event.mouse_region_x,
                                                                                    event.mouse_region_y)
                                    self.cut_line_widget.derive_screen(context)
                                
                                else:
                                    self.cut_line_widget = None
                            
                        else:
                            if self.cut_line_widget:
                                self.cut_line_widget.x = event.mouse_region_x
                                self.cut_line_widget.y = event.mouse_region_y
                                self.cut_line_widget.derive_screen(context)
                    # elif not c_cut.select:
                        # c_cut.geom_color = (settings.geom_rgb[0],settings.geom_rgb[1],settings.geom_rgb[2],1)          
            if not target_at_all:
                self.hover_target = None
                self.cut_line_widget = None
                
    def new_path_from_draw(self,context,settings):
        '''
        package all the steps needed to make a new path
        TODO: What if errors?
        '''
        path = ContourCutSeries(context, self.draw_cache,
                                    segments = settings.ring_count,
                                    ring_segments = settings.vertex_count,
                                    cull_factor = settings.cull_factor, 
                                    smooth_factor = settings.smooth_factor,
                                    feature_factor = settings.feature_factor)
        
        
        path.ray_cast_path(context, self.original_form)
        if len(path.raw_world) == 0:
            print('NO RAW PATH')
            return None
        path.find_knots()
        
        if self.snap != [] and not self.force_new:
            merge_series = self.snap[0]
            merge_ring = self.snap[1]
            
            path.snap_merge_into_other(merge_series, merge_ring, context, self.original_form, self.bme)
            
            return merge_series

        path.smooth_path(context, ob = self.original_form)
        path.create_cut_nodes(context)
        path.snap_to_object(self.original_form, raw = False, world = False, cuts = True)
        path.cuts_on_path(context, self.original_form, self.bme)
        path.connect_cuts_to_make_mesh(self.original_form)
        path.backbone_from_cuts(context, self.original_form, self.bme)
        path.update_visibility(context, self.original_form)
        if path.cuts:
            # TODO: should this ever be empty?
            path.cuts[-1].do_select(settings)
        
        self.cut_paths.append(path)
        

        return path
    
    def click_new_cut(self,context, settings, event):

        new_cut = ContourCutLine(event.mouse_region_x, event.mouse_region_y)
        
        
        for path in self.cut_paths:
            for cut in path.cuts:
                cut.deselect(settings)
                
        new_cut.do_select(settings)
        self.cut_lines.append(new_cut)
        
        return new_cut
    
    def release_place_cut(self,context,settings, event):
        self.selected.tail.x = event.mouse_region_x
        self.selected.tail.y = event.mouse_region_y
        
        width = Vector((self.selected.head.x, self.selected.head.y)) - Vector((self.selected.tail.x, self.selected.tail.y))
        
        # Prevent small errant strokes
        if width.length < 20: #TODO: Setting for minimum pixel width
            self.cut_lines.remove(self.selected)
            self.selected = None
            print('Placed cut is too short')
            return
        
        # Hit the mesh for the first time
        hit = self.selected.hit_object(context, self.original_form, method = 'VIEW')
        
        if not hit:
            self.cut_lines.remove(self.selected)
            self.selected = None
            print('Placed cut did not hit the mesh')
            return
        
        self.selected.cut_object(context, self.original_form, self.bme)
        self.selected.simplify_cross(self.segments)
        self.selected.update_com()
        self.selected.update_screen_coords(context)
        self.selected.head = None
        self.selected.tail = None
        
        if not len(self.selected.verts) or not len(self.selected.verts_simple):
            self.selected = None
            print('cut failure')  #TODO, header text message.
            
            return
    
        
        if settings.debug > 1:
            print('release_place_cut')
            print('len(self.cut_paths) = %d' % len(self.cut_paths))
            print('self.force_new = ' + str(self.force_new))
        
        if self.cut_paths != [] and not self.force_new:
            for path in self.cut_paths:
                if path.insert_new_cut(context, self.original_form, self.bme, self.selected, search = settings.search_factor):
                    # The cut belongs to the series now
                    path.connect_cuts_to_make_mesh(self.original_form)
                    path.update_visibility(context, self.original_form)
                    path.seg_lock = True
                    path.do_select(settings)
                    path.unhighlight(settings)
                    self.selected_path = path
                    self.cut_lines.remove(self.selected)
                    for other_path in self.cut_paths:
                        if other_path != self.selected_path:
                            other_path.deselect(settings)
                    # No need to search for more paths
                    return
        
        # Create a blank segment
        path = ContourCutSeries(context, [],
                        cull_factor = settings.cull_factor, 
                        smooth_factor = settings.smooth_factor,
                        feature_factor = settings.feature_factor)
        
        path.insert_new_cut(context, self.original_form, self.bme, self.selected, search = settings.search_factor)
        path.seg_lock = False  # Not locked yet...not until a 2nd cut is added in loop mode
        path.segments = 1
        path.ring_segments = len(self.selected.verts_simple)
        path.connect_cuts_to_make_mesh(self.original_form)
        path.update_visibility(context, self.original_form)
        
        for other_path in self.cut_paths:
            other_path.deselect(settings)
        
        self.cut_paths.append(path)
        self.selected_path = path
        path.do_select(settings)
        
        self.cut_lines.remove(self.selected)
        self.force_new = False
    
    def finish_mesh(self, context):
        back_to_edit = (context.mode == 'EDIT_MESH')
                    
        # This is where all the magic happens
        print('pushing data into bmesh')
        for path in self.cut_paths:
            path.push_data_into_bmesh(context, self.destination_ob, self.dest_bme, self.original_form, self.dest_me)
        
        if back_to_edit:
            print('updating edit mesh')
            bmesh.update_edit_mesh(self.dest_me, tessface=False, destructive=True)
        
        else:
            # Write the data into the object
            print('write data into the object')
            self.dest_bme.to_mesh(self.dest_me)
        
            # Remember we created a new object
            print('link destination object')
            context.scene.objects.link(self.destination_ob)
            
            print('select and make active')
            self.destination_ob.select = True
            context.scene.objects.active = self.destination_ob
            
            if context.space_data.local_view:
                view_loc = context.space_data.region_3d.view_location.copy()
                view_rot = context.space_data.region_3d.view_rotation.copy()
                view_dist = context.space_data.region_3d.view_distance
                bpy.ops.view3d.localview()
                bpy.ops.view3d.localview()
                #context.space_data.region_3d.view_matrix = mx_copy
                context.space_data.region_3d.view_location = view_loc
                context.space_data.region_3d.view_rotation = view_rot
                context.space_data.region_3d.view_distance = view_dist
                context.space_data.region_3d.update()
        
        print('wrap up')
        context.area.header_text_set()
        common_utilities.callback_cleanup(self,context)
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        
        print('finished mesh!')
        return {'FINISHED'}
        
    def widget_transform(self,context,settings, event):
        
        self.cut_line_widget.user_interaction(context, event.mouse_region_x, event.mouse_region_y, shift = event.shift)
        
            
        self.selected.cut_object(context, self.original_form, self.bme)
        self.selected.simplify_cross(self.selected_path.ring_segments)
        self.selected.update_com()
        self.selected_path.align_cut(self.selected, mode = 'BETWEEN', fine_grain = True)
        
        self.selected_path.connect_cuts_to_make_mesh(self.original_form)
        self.selected_path.update_visibility(context, self.original_form)
        
        self.temporary_message_start(context, 'WIDGET_TRANSFORM: ' + str(self.cut_line_widget.transform_mode))    
    
    def guide_arrow_shift(self,context,event):
        if event.type == 'LEFT_ARROW':         
            for cut in self.selected_path.cuts:
                cut.shift += .05
                cut.simplify_cross(self.selected_path.ring_segments)
        else:
            for cut in self.selected_path.cuts:
                cut.shift += -.05
                cut.simplify_cross(self.selected_path.ring_segments)
                                
        self.selected_path.connect_cuts_to_make_mesh(self.original_form)
        self.selected_path.update_visibility(context, self.original_form)  

    def loop_arrow_shift(self,context,event):    
        if event.type == 'LEFT_ARROW':
            self.selected.shift += .05
            
        else:
            self.selected.shift += -.05
            
        self.selected.simplify_cross(self.selected_path.ring_segments)
        self.selected_path.connect_cuts_to_make_mesh(self.original_form)
        self.selected_path.update_backbone(context, self.original_form, self.bme, self.selected, insert = False)
        self.selected_path.update_visibility(context, self.original_form)
            

        self.temporary_message_start(context, self.mode +': Shift ' + str(self.selected.shift))
                                                
    def loop_align_modal(self,context, event):
        if not event.ctrl and not event.shift:
            act = 'BETWEEN'
                
        # Align ahead    
        elif event.ctrl and not event.shift:
            act = 'FORWARD'
            
        # Align behind    
        elif event.shift and not event.ctrl:
            act = 'BACKWARD'
            
        self.selected_path.align_cut(self.selected, mode = act, fine_grain = True)
        self.selected.simplify_cross(self.selected_path.ring_segments)
        
        self.selected_path.connect_cuts_to_make_mesh(self.original_form)
        self.selected_path.update_backbone(context, self.original_form, self.bme, self.selected, insert = False)
        self.selected_path.update_visibility(context, self.original_form)
        self.temporary_message_start(context, 'Align Loop: %s' % act)
            
    def loop_hotkey_modal(self,context,event):
            

        if self.hot_key == 'G':
            self.cut_line_widget = CutLineManipulatorWidget(context, self.settings, 
                                                        self.original_form, self.bme,
                                                        self.selected,
                                                        self.selected_path,
                                                        event.mouse_region_x,event.mouse_region_y,
                                                        hotkey = self.hot_key)
            self.cut_line_widget.transform_mode = 'EDGE_SLIDE'

        
        elif self.hot_key == 'R':
            #TODO...if CoM is off screen, then what?
            screen_pivot = location_3d_to_region_2d(context.region,context.space_data.region_3d,self.selected.plane_com)
            self.cut_line_widget = CutLineManipulatorWidget(context, self.settings, 
                                                        self.original_form, self.bme,
                                                        self.selected,
                                                        self.selected_path,
                                                        screen_pivot[0],screen_pivot[1],
                                                        hotkey = self.hot_key)
            self.cut_line_widget.transform_mode = 'ROTATE_VIEW'
            
        
        
        self.cut_line_widget.initial_x = event.mouse_region_x
        self.cut_line_widget.initial_y = event.mouse_region_y
        self.cut_line_widget.derive_screen(context)
    
    
    def temporary_message_start(self,context, message):
        self.msg_start_time = time.time()
        if not self._timer:
            self._timer = context.window_manager.event_timer_add(0.1, context.window)
        
        context.area.header_text_set(text = message)    
                                                 
    
    def modal(self, context, event):
        context.area.tag_redraw()
        settings = common_utilities.get_settings()
        
        if event.type == 'Z' and event.ctrl and event.value == 'PRESS':
            self.temporary_message_start(context, "Undo Action")
            self.undo_action()
            
        # Check messages
        if event.type == 'TIMER':
            now = time.time()
            if now - self.msg_start_time > self.msg_duration:
                if self._timer:
                    context.window_manager.event_timer_remove(self._timer)
                    self._timer = None
                
                if self.mode == 'GUIDE':
                    context.area.header_text_set(text = self.guide_msg)
                else:
                    context.area.header_text_set(text = self.loop_msg)
                
                
        if self.modal_state == 'NAVIGATING':
            
            if (event.type in {'MOUSEMOVE',
                               'MIDDLEMOUSE', 
                                'NUMPAD_2', 
                                'NUMPAD_4', 
                                'NUMPAD_6',
                                'NUMPAD_8', 
                                'NUMPAD_1', 
                                'NUMPAD_3', 
                                'NUMPAD_5', 
                                'NUMPAD_7',
                                'NUMPAD_9'} and event.value == 'RELEASE'):
            
                self.modal_state = 'WAITING'
                self.post_update = True
                return {'PASS_THROUGH'}
            
            if (event.type in {'TRACKPADPAN', 'TRACKPADZOOM'} or event.type.startswith('NDOF_')):
            
                self.modal_state = 'WAITING'
                self.post_update = True 
                return {'PASS_THROUGH'}
        
        if self.mode == 'LOOP':
            
            if self.modal_state == 'WAITING':
                
                if (event.type in {'ESC','RIGHT_MOUSE'} and 
                    event.value == 'PRESS'):
                    
                    context.area.header_text_set()
                    common_utilities.callback_cleanup(self,context)
                    if self._timer:
                        context.window_manager.event_timer_remove(self._timer)
                        
                    return {'CANCELLED'}
                
                elif (event.type == 'TAB' and 
                      event.value == 'PRESS'):
                    
                    self.mode = 'GUIDE'
                    self.selected = None  #WHY?
                    if self.selected_path:
                        self.selected_path.highlight(settings)
                    
                    if self._timer:
                        context.window_manager.event_timer_remove(self._timer)
                        self._timer = None
                
                    
                    context.area.header_text_set(text = self.guide_msg)
                
                elif event.type == 'N' and event.value == 'PRESS':
                    self.force_new = self.force_new != True
                    #self.selected_path = None
                    self.snap = None
                    
                    self.temporary_message_start(context, self.mode +': FORCE NEW: ' + str(self.force_new))
                    return {'RUNNING_MODAL'}
                
                elif (event.type in {'RET', 'NUMPAD_ENTER'} and 
                    event.value == 'PRESS'):
                    
                    return self.finish_mesh(context)
                

                    
                if event.type == 'MOUSEMOVE':
                    
                    self.hover_loop_mode(context, settings, event)

                
                elif (event.type == 'C' and
                      event.value == 'PRESS'):
                    
                    bpy.ops.view3d.view_center_cursor()
                    self.temporary_message_start(context, 'Center View to Cursor')
                    return {'RUNNING_MODAL'}
                
                elif event.type == 'S' and event.value == 'PRESS':
                    if self.selected:
                        context.scene.cursor_location = self.selected.plane_com
                        self.temporary_message_start(context, 'Cursor to selected loop or segment')
                
                # NAVIGATION KEYS
                elif (event.type in {'MIDDLEMOUSE', 
                                    'NUMPAD_2', 
                                    'NUMPAD_4', 
                                    'NUMPAD_6',
                                    'NUMPAD_8', 
                                    'NUMPAD_1', 
                                    'NUMPAD_3', 
                                    'NUMPAD_5', 
                                    'NUMPAD_7',
                                    'NUMPAD_9'} and event.value == 'PRESS'):
                    
                    self.modal_state = 'NAVIGATING'
                    self.post_update = True
                    self.temporary_message_start(context, self.mode + ': NAVIGATING')

                    return {'PASS_THROUGH'}
                elif (event.type in {'TRACKPADPAN', 'TRACKPADZOOM'} or event.type.startswith('NDOF_')):
                    
                    self.modal_state = 'NAVIGATING'
                    self.post_update = True
                    self.temporary_message_start(context, 'NAVIGATING')

                    return {'PASS_THROUGH'}
                
                # ZOOM KEYS
                elif (event.type in  {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and not 
                        (event.ctrl or event.shift)):
                    
                    self.post_update = True
                    return{'PASS_THROUGH'}
                
                elif event.type in selection_mouse() and event.value == 'PRESS':
                    
                    if self.hover_target and self.hover_target != self.selected:
                        
                        self.selected = self.hover_target    
                        if not event.shift:
                            for path in self.cut_paths:
                                for cut in path.cuts:
                                        cut.deselect(settings)  
                                if self.selected in path.cuts and path != self.selected_path:
                                    path.do_select(settings)
                                    path.unhighlight(settings)
                                    self.selected_path = path
                                else:
                                    path.deselect(settings)
                        
                        # Select the ring
                        self.hover_target.do_select(settings)
                        
                    
                    elif self.hover_target  and self.hover_target == self.selected:
                        
                        self.create_undo_snapshot('WIDGET_TRANSFORM')
                        self.modal_state = 'WIDGET_TRANSFORM'
                        # Sometimes, there is not a widget from the hover?
                        self.cut_line_widget = CutLineManipulatorWidget(context, 
                                                                        settings,
                                                                        self.original_form, self.bme,
                                                                        self.hover_target,
                                                                        self.selected_path,
                                                                        event.mouse_region_x,
                                                                        event.mouse_region_y)
                        self.cut_line_widget.derive_screen(context)
                        
                    else:
                        self.create_undo_snapshot('CUTTING')
                        self.modal_state = 'CUTTING'
                        self.temporary_message_start(context, self.mode + ': CUTTING')
                        # Make a new cut and handle it with self.selected
                        self.selected = self.click_new_cut(context, settings, event)
                        
                        
                    return {'RUNNING_MODAL'}
                
                if self.selected:
                    #print(event.type + " " + event.value)
                    
                    #G -> HOTKEY
                    if event.type == 'G' and event.value == 'PRESS':
                        
                        self.create_undo_snapshot('HOTKEY_TRANSFORM')
                        self.modal_state = 'HOTKEY_TRANSFORM'
                        self.hot_key = 'G'
                        self.loop_hotkey_modal(context,event)
                        self.temporary_message_start(context, self.mode + ':Hotkey Grab')
                        return {'RUNNING_MODAL'}
                    # R -> HOTKEY
                    if event.type == 'R' and event.value == 'PRESS':
                        
                        self.create_undo_snapshot('HOTKEY_TRANSFORM')
                        self.modal_state = 'HOTKEY_TRANSFORM'
                        self.hot_key = 'R'
                        self.loop_hotkey_modal(context,event)
                        self.temporary_message_start(context, self.mode + ':Hotkey Rotate')
                        return {'RUNNING_MODAL'}
                    
                    # X, DEL -> DELETE
                    elif event.type == 'X' and event.value == 'PRESS':
                        
                        self.create_undo_snapshot('DELETE')
                        if len(self.selected_path.cuts) > 1 or (len(self.selected_path.cuts) == 1 and self.selected_path.existing_head):
                            self.selected_path.remove_cut(context, self.original_form, self.bme, self.selected)
                            self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                            self.selected_path.update_visibility(context, self.original_form)
                            self.selected_path.backbone_from_cuts(context, self.original_form, self.bme)
                        
                        else:
                            self.cut_paths.remove(self.selected_path)
                            self.selected_path = None
                            
                        self.selected = None
                        self.temporary_message_start(context, self.mode + ': DELETE')
                    
                    # S -> CURSOR SELECTED CoM
                    
                    # LEFT_ARROW, RIGHT_ARROW to shift
                    elif (event.type in {'LEFT_ARROW', 'RIGHT_ARROW'} and 
                          event.value == 'PRESS'):
                        self.create_undo_snapshot('LOOP_SHIFT') 
                        self.loop_arrow_shift(context,event)
                        
                        return {'RUNNING_MODAL'}
                    
                    elif event.type == 'A' and event.value == 'PRESS':
                        self.create_undo_snapshot('ALIGN')
                        self.loop_align_modal(context,event)
                         
                        return {'RUNNING_MODAL'}
                        
                    elif ((event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.ctrl) or
                          (event.type in {'NUMPAD_PLUS','NUMPAD_MINUS'} and event.value == 'PRESS') and event.ctrl):
                        
                        self.create_undo_snapshot('RING_SEGMENTS')  
                        if not self.selected_path.ring_lock:
                            old_segments = self.selected_path.ring_segments
                            self.selected_path.ring_segments += 1 - 2 * (event.type == 'WHEELDOWNMOUSE' or event.type == 'NUMPAD_MINUS')
                            if self.selected_path.ring_segments < 3:
                                self.selected_path.ring_segments = 3
                                
                            for cut in self.selected_path.cuts:
                                new_bulk_shift = round(cut.shift * old_segments/self.selected_path.ring_segments)
                                new_fine_shift = old_segments/self.selected_path.ring_segments * cut.shift - new_bulk_shift
                                
                                
                                new_shift =  self.selected_path.ring_segments/old_segments * cut.shift
                                
                                print(new_shift - new_bulk_shift - new_fine_shift)
                                cut.shift = new_shift
                                cut.simplify_cross(self.selected_path.ring_segments)
                            
                            self.selected_path.backbone_from_cuts(context, self.original_form, self.bme)    
                            self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                            self.selected_path.update_visibility(context, self.original_form)
                            
                            self.temporary_message_start(context, self.mode +': RING SEGMENTS %i' %self.selected_path.ring_segments)
                            self.msg_start_time = time.time()
                        else:
                            self.temporary_message_start(context, self.mode +': RING SEGMENTS: Can not be changed.  Path Locked')
                            
                        #else:
                            #let the user know the path is locked
                            #header message set

                        return {'RUNNING_MODAL'}
                    #if hover == selected:
                        #LEFTCLICK -> WIDGET
                        
                
                        
                return {'RUNNING_MODAL'}
                        
            elif self.modal_state == 'CUTTING':
                
                if event.type == 'MOUSEMOVE':
                    # Pass mouse coords to widget
                    x = str(event.mouse_region_x)
                    y = str(event.mouse_region_y)
                    message = self.mode + ':CUTTING: X: ' +  x + '  Y:  ' +  y
                    context.area.header_text_set(text = message)
                    
                    self.selected.tail.x = event.mouse_region_x
                    self.selected.tail.y = event.mouse_region_y
                    #self.seleted.screen_to_world(context)
                    
                    return {'RUNNING_MODAL'}
                
                elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':

                    #the new cut is created
                    #the new cut is assessed to be placed into an existing series
                    #the new cut is assessed to be an extension of selected gemometry
                    #the new cut is assessed to become the beginning of a new path
                    self.release_place_cut(context, settings, event)
                    
                    
                    # We return to waiting
                    self.modal_state = 'WAITING'
                    return {'RUNNING_MODAL'}
            
            
            elif self.modal_state == 'HOTKEY_TRANSFORM':
                if self.hot_key == 'G':
                    action = 'Grab'
                elif self.hot_key == 'R':
                    action = 'Rotate'
                    
                if event.shift:
                        action = 'FINE CONTROL ' + action
                
                if event.type == 'MOUSEMOVE':
                    #pass mouse coords to widget
                    x = str(event.mouse_region_x)
                    y = str(event.mouse_region_y)
                    message  = self.mode + ": " + action + ": X: " +  x + '  Y:  ' +  y
                    self.temporary_message_start(context, message)

                    #widget.user_interaction
                    self.cut_line_widget.user_interaction(context, event.mouse_region_x,event.mouse_region_y)
                    self.selected.cut_object(context, self.original_form, self.bme)
                    self.selected.simplify_cross(self.selected_path.ring_segments)
                    self.selected.update_com()
                    self.selected_path.align_cut(self.selected, mode = 'BETWEEN', fine_grain = True)
                    
                    self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                    self.selected_path.update_visibility(context, self.original_form)
                    return {'RUNNING_MODAL'}
                
                
                #LEFTMOUSE event.value == 'PRESS':#RET, ENTER
                if (event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and
                    event.value == 'PRESS'):
                    #confirm transform
                    #recut, align, visibility?, and update the segment
                    self.selected_path.update_backbone(context, self.original_form, self.bme, self.selected, insert = False)
                    self.modal_state = 'WAITING'
                    return {'RUNNING_MODAL'}
                
                if (event.type in {'ESC', 'RIGHTMOUSE'} and
                    event.value == 'PRESS'):
                    self.cut_line_widget.cancel_transform()
                    self.selected.cut_object(context, self.original_form, self.bme)
                    self.selected.simplify_cross(self.selected_path.ring_segments)
                    self.selected_path.align_cut(self.selected, mode = 'BETWEEN', fine_grain = True)
                    self.selected.update_com()
                    
                    self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                    self.selected_path.update_visibility(context, self.original_form)
                    self.modal_state = 'WAITING'
                    return {'RUNNING_MODAL'}
                
            
            elif self.modal_state == 'WIDGET_TRANSFORM':
                
                #MOUSEMOVE
                if event.type == 'MOUSEMOVE':
                    if event.shift:
                        action = 'FINE WIDGET'
                    else:
                        action = 'WIDGET'
                    
                    
                    self.widget_transform(context, settings, event)
                    
                    return {'RUNNING_MODAL'}
               
                elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                    #destroy the widget
                    self.cut_line_widget = None
                    self.modal_state = 'WAITING'
                    self.selected_path.update_backbone(context, self.original_form, self.bme, self.selected, insert = False)
                    
                    return {'RUNNING_MODAL'}
                    
                elif  event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS' and self.hot_key:
                    self.cut_line_widget.cancel_transform()
                    self.selected.cut_object(context, self.original_form, self.bme)
                    self.selected.simplify_cross(self.selected_path.ring_segments)
                    self.selected.update_com()
                    
                    self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                    self.selected_path.update_visibility(context, self.original_form)
                    
                return {'RUNNING_MODAL'}

            return{'RUNNING_MODAL'}

        if self.mode == 'GUIDE':
            
            if self.modal_state == 'WAITING':
                #NAVIGATION KEYS
                if (event.type in {'MIDDLEMOUSE', 
                                    'NUMPAD_2', 
                                    'NUMPAD_4', 
                                    'NUMPAD_6',
                                    'NUMPAD_8', 
                                    'NUMPAD_1', 
                                    'NUMPAD_3', 
                                    'NUMPAD_5', 
                                    'NUMPAD_7',
                                    'NUMPAD_9'} and event.value == 'PRESS'):
                    
                    self.modal_state = 'NAVIGATING'
                    self.post_update = True
                    self.temporary_message_start(context, 'NAVIGATING')

                    return {'PASS_THROUGH'}
                
                elif (event.type in {'ESC','RIGHT_MOUSE'} and 
                    event.value == 'PRESS'):
                    
                    context.area.header_text_set()
                    common_utilities.callback_cleanup(self,context)
                    if self._timer:
                        context.window_manager.event_timer_remove(self._timer)
                        
                    return {'CANCELLED'}
                
                elif (event.type in {'RET', 'NUMPAD_ENTER'} and 
                    event.value == 'PRESS'):
                    
                    return self.finish_mesh(context)
                
                elif (event.type in {'TRACKPADPAN', 'TRACKPADZOOM'} or event.type.startswith('NDOF_')):
                    
                    self.modal_state = 'NAVIGATING'
                    self.post_update = True
                    self.temporary_message_start(context, 'NAVIGATING')

                    return {'PASS_THROUGH'}
                
                #ZOOM KEYS
                elif (event.type in  {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and not 
                        (event.ctrl or event.shift)):
                    
                    self.post_update = True
                    self.temporary_message_start(context, 'ZOOM')
                    return{'PASS_THROUGH'}
                
                elif event.type == 'TAB' and event.value == 'PRESS':
                    self.mode = 'LOOP'
                    self.snap_circle = []
                    
                    if self.selected_path:
                        self.selected_path.unhighlight(settings)
                        
                    if self._timer:
                        context.window_manager.event_timer_remove(self._timer)
                        self._timer = None
                
                    context.area.header_text_set(text = self.loop_msg)
                    return {'RUNNING_MODAL'}
                
                elif event.type == 'C' and event.value == 'PRESS':
                    #center cursor
                    bpy.ops.view3d.view_center_cursor()
                    self.temporary_message_start(context, 'Center View to Cursor')
                    return {'RUNNING_MODAL'}
                    
                elif event.type == 'N' and event.value == 'PRESS':
                    self.force_new = self.force_new != True
                    #self.selected_path = None
                    self.snap = None
                    
                    self.temporary_message_start(context, self.mode +': FORCE NEW: ' + str(self.force_new))
                    return {'RUNNING_MODAL'}
                
                
                elif event.type == 'MOUSEMOVE':
                    
                    self.hover_guide_mode(context, settings, event)
                    
                    return {'RUNNING_MODAL'}

                    
                elif event.type in selection_mouse() and event.value == 'PRESS':
                    if self.hover_target and self.hover_target.desc == 'CUT SERIES':
                        self.hover_target.do_select(settings)
                        self.selected_path = self.hover_target
                        
                        for path in self.cut_paths:
                            if path != self.hover_target:
                                path.deselect(settings)
                    else:
                        self.create_undo_snapshot('DRAW_PATH')
                        self.modal_state = 'DRAWING'
                        self.temporary_message_start(context, 'DRAWING')
                    
                    return {'RUNNING_MODAL'}    
                
                if self.selected_path:

                    if event.type in {'X', 'DEL'} and event.value == 'PRESS':
                        
                        self.create_undo_snapshot('DELETE')
                        self.cut_paths.remove(self.selected_path)
                        self.selected_path = None
                        self.modal_state = 'WAITING'
                        self.temporary_message_start(context, 'DELETED PATH')
                        
                        return {'RUNNING_MODAL'}
                    
                    elif (event.type in {'LEFT_ARROW', 'RIGHT_ARROW'} and 
                          event.value == 'PRESS'):
                        
                        self.create_undo_snapshot('PATH_SHIFT')
                        self.guide_arrow_shift(context, event)
                          
                        #shift entire segment
                        self.temporary_message_start(context, 'Shift entire segment')
                        return {'RUNNING_MODAL'}
                        
                    elif ((event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.ctrl) or
                          (event.type in {'NUMPAD_PLUS','NUMPAD_MINUS'} and event.value == 'PRESS')):
                          
                        #if not selected_path.lock:
                        #TODO: path.locked
                        #TODO:  dont recalc the path when no change happens
                        if event.type in {'WHEELUPMOUSE','NUMPAD_PLUS'}:
                            if not self.selected_path.seg_lock:                            
                                self.create_undo_snapshot('PATH_SEGMENTS')
                                self.selected_path.segments += 1
                        elif event.type in {'WHEELDOWNMOUSE', 'NUMPAD_MINUS'} and self.selected_path.segments > 3:
                            if not self.selected_path.seg_lock:
                                self.create_undo_snapshot('PATH_SEGMENTS')
                                self.selected_path.segments -= 1
                    
                        if not self.selected_path.seg_lock:
                            self.selected_path.create_cut_nodes(context)
                            self.selected_path.snap_to_object(self.original_form, raw = False, world = False, cuts = True)
                            self.selected_path.cuts_on_path(context, self.original_form, self.bme)
                            self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                            self.selected_path.update_visibility(context, self.original_form)
                            self.selected_path.backbone_from_cuts(context, self.original_form, self.bme)
                            #selected will hold old reference because all cuts are recreated (dumbly, it should just be the in between ones)
                            self.selected = self.selected_path.cuts[-1]
                            self.temporary_message_start(context, 'PATH SEGMENTS: %i' % self.selected_path.segments)
                            
                            
                        else:
                            self.temporary_message_start(context, 'PATH SEGMENTS: Path is locked, cannot adjust segments')
                        return {'RUNNING_MODAL'}
                   
                    elif event.type == 'S' and event.value == 'PRESS':

                        if event.shift:
                            self.create_undo_snapshot('SMOOTH')
                            #path.smooth_normals
                            self.selected_path.average_normals(context, self.original_form, self.bme)
                            self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                            self.selected_path.backbone_from_cuts(context, self.original_form, self.bme)
                            self.temporary_message_start(context, 'Smooth normals based on drawn path')
                            
                        elif event.ctrl:
                            self.create_undo_snapshot('SMOOTH')
                            #smooth CoM path
                            self.temporary_message_start(context, 'Smooth normals based on CoM path')
                            self.selected_path.smooth_normals_com(context, self.original_form, self.bme, iterations = 2)
                            self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                            self.selected_path.backbone_from_cuts(context, self.original_form, self.bme)
                        elif event.alt:
                            self.create_undo_snapshot('SMOOTH')
                            #path.interpolate_endpoints
                            self.temporary_message_start(context, 'Smoothly interpolate normals between the endpoints')
                            self.selected_path.interpolate_endpoints(context, self.original_form, self.bme)
                            self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                            self.selected_path.backbone_from_cuts(context, self.original_form, self.bme)
                            
                        else:
                            half = math.floor(len(self.selected_path.cuts)/2)
                            
                            if math.fmod(len(self.selected_path.cuts), 2):  #5 segments is 6 rings
                                loc = 0.5 * (self.selected_path.cuts[half].plane_com + self.selected_path.cuts[half+1].plane_com)
                            else:
                                loc = self.selected_path.cuts[half].plane_com
                            
                            context.scene.cursor_location = loc
                    
                        return{'RUNNING_MODAL'}
                        
            if self.modal_state == 'DRAWING':
                
                if event.type == 'MOUSEMOVE':
                    action = 'GUIDE MODE: Drawing'
                    x = str(event.mouse_region_x)
                    y = str(event.mouse_region_y)
                    #record screen drawing
                    self.draw_cache.append((event.mouse_region_x,event.mouse_region_y))   
                    
                    return {'RUNNING_MODAL'}
                    
                if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                    if len(self.draw_cache) > 10:
                        
                        for path in self.cut_paths:
                            path.deselect(settings)
                            
                        self.selected_path  = self.new_path_from_draw(context, settings)
                        if self.selected_path:
                            self.selected_path.do_select(settings)
                            if self.selected_path.cuts:
                                self.selected = self.selected_path.cuts[-1]
                            else:
                                self.selected = None
                            if self.selected:
                                self.selected.do_select(settings)
                        
                        self.drag = False #TODO: is self.drag still needed?
                        self.force_new = False
                    
                    self.draw_cache = []
                    
                    self.modal_state = 'WAITING'
                    return{'RUNNING_MODAL'}
                
                
            return{'RUNNING_MODAL'}
            
    
                        
    def create_undo_snapshot(self, action):
        '''
        saves data and operator state snapshot
        for undoing
        
        TODO:  perhaps pop/append are not fastest way
        deque?
        prepare a list and keep track of which entity to
        replace?
        '''
        
        repeated_actions = {'LOOP_SHIFT', 'PATH_SHIFT', 'PATH_SEGMENTS', 'LOOP_SEGMENTS'}
        
        if action in repeated_actions:
            if action == contour_undo_cache[-1][2]:
                dprint('repeatable...dont take snapshot')
                return
        
        dprint('undo: ' + action)
        cut_data = copy.deepcopy(self.cut_paths)
        #perhaps I don't even need to copy this?
        state = copy.deepcopy(ContourStatePreserver(self))
        contour_undo_cache.append((cut_data, state, action))
            
        if len(contour_undo_cache) > self.settings.undo_depth:
            contour_undo_cache.pop(0)
            
            

    def undo_action(self):
        
        if len(contour_undo_cache) > 0:
            cut_data, op_state, action = contour_undo_cache.pop()
            
            self.cut_paths = cut_data
            op_state.push_state(self)

    def invoke(self, context, event):
        #HINT you are in contours code
        #TODO Settings harmon CODE REVIEW
        settings = common_utilities.get_settings()
        
        if context.space_data.viewport_shade in {'WIREFRAME','BOUNDBOX'}:
            showErrorMessage('Viewport shading must be at least SOLID')
            return {'CANCELLED'}
        elif context.mode == 'EDIT_MESH' and len(context.selected_objects) != 2:
            showErrorMessage('Must select exactly two objects')
            return {'CANCELLED'}
        elif context.mode == 'OBJECT' and len(context.selected_objects) != 1:
            showErrorMessage('Must select only one object')
            return {'CANCELLED'}
        
        
        self.valid_cut_inds = []
        self.existing_loops = []
        
        #This is a cache for any cut line whose connectivity
        #has not been established.
        self.cut_lines = []
        
        #a list of all the cut paths (segments)
        self.cut_paths = []
        #a list to store screen coords when drawing
        self.draw_cache = []
        
        #TODO Settings harmony CODE REVIEW
        self.settings = settings
        
        #default verts in a loop (spans)
        self.segments = settings.vertex_count
        #default number of loops in a segment
        self.guide_cuts = settings.ring_count
        
        #if edit mode
        if context.mode == 'EDIT_MESH':
            
            #retopo mesh is the active object
            self.destination_ob = context.object  #TODO:  Clarify destination_ob as retopo_on consistent with design doc
            
            #get the destination mesh data
            self.dest_me = self.destination_ob.data
            
            #we will build this bmesh using from editmesh
            self.dest_bme = bmesh.from_edit_mesh(self.dest_me)
            
            #the selected object will be the original form
            #or we wil pull the mesh cache
            target = [ob for ob in context.selected_objects if ob.name != context.object.name][0]
            
            #this is a simple set of recorded properties meant to help detect
            #if the mesh we are using is the same as the one in the cache.
            is_valid = is_object_valid(target)
            if is_valid:
                use_cache = True
                print('willing and able to use the cache!')
            else:
                use_cache = False  #later, we will double check for ngons and things
                clear_mesh_cache()
                self.original_form = target
                
            
            #count and collect the selected edges if any
            ed_inds = [ed.index for ed in self.dest_bme.edges if ed.select]
            
            self.existing_loops = []
            if len(ed_inds):
                vert_loops = contour_utilities.edge_loops_from_bmedges(self.dest_bme, ed_inds)
                
          
                
                if len(vert_loops) > 1:
                    self.report({'WARNING'}, 'Only one edge loop will be used for extension')
                print('there are %i edge loops selected' % len(vert_loops))
                
                #for loop in vert_loops:
                #until multi loops are supported, do this    
                loop = vert_loops[0]
                if loop[-1] != loop[0] and len(list(set(loop))) != len(loop):
                    self.report({'WARNING'},'Edge loop selection has extra parts!  Excluding this loop')
                    
                else:
                    lverts = [self.dest_bme.verts[i] for i in loop]
                    
                    existing_loop =ExistingVertList(context,
                                                    lverts, 
                                                    loop, 
                                                    self.destination_ob.matrix_world,
                                                    key_type = 'INDS')
                    
                    #make a blank path with just an existing head
                    path = ContourCutSeries(context, [],
                                    cull_factor = settings.cull_factor, 
                                    smooth_factor = settings.smooth_factor,
                                    feature_factor = settings.feature_factor)
                
                    
                    path.existing_head = existing_loop
                    path.seg_lock = False
                    path.ring_lock = True
                    path.ring_segments = len(existing_loop.verts_simple)
                    path.connect_cuts_to_make_mesh(target)
                    path.update_visibility(context, target)
                
                    #path.update_visibility(context, self.original_form)
                    
                    self.cut_paths.append(path)
                    self.existing_loops.append(existing_loop)
                    
                    
        elif context.mode == 'OBJECT':
            
            #make the irrelevant variables None
            self.sel_edges = None
            self.sel_verts = None
            self.existing_cut = None
            
            #the active object will be the target
            target = context.object
            
            is_valid = is_object_valid(target)
            has_tmp = 'ContourTMP' in bpy.data.objects and bpy.data.objects['ContourTMP'].data
            
            if is_valid and has_tmp:
                use_cache = True
            else:
                use_cache = False
                self.original_form  = target #TODO:  Clarify original_form as reference_form consistent with design doc
            
            #no temp bmesh needed in object mode
            #we will create a new obeject
            self.tmp_bme = None
            
            #new blank mesh data
            self.dest_me = bpy.data.meshes.new(target.name + "_recontour")
            
            #new object to hold mesh data
            self.destination_ob = bpy.data.objects.new(target.name + "_recontour",self.dest_me) #this is an empty currently
            self.destination_ob.matrix_world = target.matrix_world
            self.destination_ob.update_tag()
            
            #destination bmesh to operate on
            self.dest_bme = bmesh.new()
            self.dest_bme.from_mesh(self.dest_me)
            

        
        #get the info about the original form
        #and convert it to a bmesh for fast connectivity info
        #or load the previous bme to save even more time
        
        
        
        if use_cache:
            start = time.time()
            print('the cache is valid for use!')
            
            self.bme = contour_mesh_cache['bme']
            print('loaded old bme in %f' % (time.time() - start))
            
            start = time.time()
            
            self.tmp_ob = contour_mesh_cache['tmp']
            print('loaded old tmp ob in %f' % (time.time() - start))
            
            if self.tmp_ob:
                self.original_form = self.tmp_ob
            else:
                self.original_form = target
              
        else:
    
            start = time.time()
            
            #clear any old saved data
            clear_mesh_cache()
            
            
            me = self.original_form.to_mesh(scene=context.scene, apply_modifiers=True, settings='PREVIEW')
            me.update()
            
            self.bme = bmesh.new()
            self.bme.from_mesh(me)
             
            #check for ngons, and if there are any...triangulate just the ngons
            #this mainly stems from the obj.ray_cast function returning triangulate
            #results and that it makes my cross section method easier.
            ngons = []
            for f in self.bme.faces:
                if len(f.verts) > 4:
                    ngons.append(f)
            if len(ngons) or len(self.original_form.modifiers) > 0:
                print('Ngons or modifiers detected this is a real hassle just so you know')
                
                if len(ngons):
                    #new_geom = bmesh.ops.triangulate(self.bme, faces = ngons, use_beauty = True)
                    new_geom = bmesh.ops.triangulate(self.bme, faces = ngons, quad_method=0, ngon_method=1)
                    new_faces = new_geom['faces']
                    
                    
                new_me = bpy.data.meshes.new('tmp_recontour_mesh')
                self.bme.to_mesh(new_me)
                new_me.update()
                
                
                self.tmp_ob = bpy.data.objects.new('ContourTMP', new_me)
                
                
                #I think this is needed to generate the data for raycasting
                #there may be some other way to update the object
                context.scene.objects.link(self.tmp_ob)
                self.tmp_ob.update_tag()
                context.scene.update() #this will slow things down
                context.scene.objects.unlink(self.tmp_ob)
                self.tmp_ob.matrix_world = self.original_form.matrix_world
                
                
                ###THIS IS A HUGELY IMPORTANT THING TO NOTICE!###
                #so maybe I need to make it more apparent or write it differnetly#
                #We are using a temporary duplicate to handle ray casting
                #and triangulation
                self.original_form = self.tmp_ob
                
            else:
                self.tmp_ob = None
            
            
            #store this stuff for next time.  We will most likely use it again
            #keep in mind, in some instances, tmp_ob is self.original orm
            #where as in others is it unique.  We want to use "target" here to
            #record validation because that is the the active or selected object
            #which is visible in the scene with a unique name.
            write_mesh_cache(target, self.tmp_ob, self.bme)
            print('derived new bme and any triangulations in %f' % (time.time() - start))

        message = "Segments: %i" % self.segments
        context.area.header_text_set(text = message)
            
        #here is where we will cache verts edges and faces
        #unti lthe user confirms and we output a real mesh.
        self.verts = []
        self.edges = []
        self.faces = []
            
       
        if settings.use_x_ray:
            self.orig_x_ray = self.destination_ob.show_x_ray
            self.destination_ob.show_x_ray = True     
            
        ####MODE, UI, DRAWING, and MODAL variables###
        self.mode = 'LOOP'
        #'LOOP' or 'GUIDE'
        
        self.modal_state = 'WAITING'
        
        #does the user want to extend an existing cut or make a new segment
        self.force_new = False
        
        #is the mouse clicked and held down
        self.drag = False
        self.navigating = False
        self.post_update = False
        
        #what is the user dragging..a cutline, a handle etc
        self.drag_target = None
        
        #potential item for snapping in 
        self.snap = []
        self.snap_circle = []
        self.snap_color = (1,0,0,1)
        
        #what is the mouse over top of currently
        self.hover_target = None
        #keep track of selected cut_line and path
        self.selected = None   #TODO: Change this to selected_loop
        if len(self.cut_paths) == 0:
            self.selected_path = None   #TODO: change this to selected_segment
        else:
            print('there is a selected_path')
            self.selected_path = self.cut_paths[-1] #this would be an existing path from selected geom in editmode
        
        self.cut_line_widget = None  #An object of Class "CutLineManipulator" or None
        self.widget_interaction = False  #Being in the state of interacting with a widget o
        self.hot_key = None  #Keep track of which hotkey was pressed
        self.draw = False  #Being in the state of drawing a guide stroke
        
        self.loop_msg = 'LOOP MODE:  LMB: Select Stroke, X: Delete Sroke, , G: Translate, R: Rotate, Ctrl/Shift + A: Align, S: Cursor to Stroke, C: View to Cursor, N: Force New Segment, TAB: toggle Guide mode'
        self.guide_msg = 'GUIDE MODE: LMB to Draw or Select, Ctrl/Shift/ALT + S to smooth, WHEEL or +/- to increase/decrease segments, TAB: toggle Loop mode'
        context.area.header_text_set(self.loop_msg)
        
        if settings.recover and is_valid:
            print('loading cache!')
            self.undo_action()
            
        else:
            contour_undo_cache = []
            
            
        #add in the draw callback and modal method
        self._handle = bpy.types.SpaceView3D.draw_handler_add(retopo_draw_callback, (self, context), 'WINDOW', 'POST_PIXEL')
        
        #timer for temporary messages
        self._timer = None
        self.msg_start_time = time.time()
        self.msg_duration = .75
        
        context.window_manager.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}


################### Polystrips ###################

class CGCOOKIE_OT_polystrips(bpy.types.Operator):
    bl_idname = "cgcookie.polystrips"
    bl_label = "Polystrips"

    @classmethod
    def poll(cls, context):
        if context.mode not in {'EDIT_MESH', 'OBJECT'}:
            return False

        return context.object.type == 'MESH'

    def draw_callback(self, context):
        return self.ui.draw_callback(context)

    def modal(self, context, event):
        ret = self.ui.modal(context, event)
        if 'FINISHED' in ret or 'CANCELLED' in ret:
            self.ui.cleanup(context)
            common_utilities.callback_cleanup(self, context)
        return ret

    def invoke(self, context, event):

        if context.mode == 'EDIT_MESH' and len(context.selected_objects) != 2:
            showErrorMessage('Must select exactly two objects')
            return {'CANCELLED'}
        elif context.mode == 'OBJECT' and len(context.selected_objects) != 1:
            showErrorMessage('Must select only one object')
            return {'CANCELLED'}

        self.ui = PolystripsUI(context, event)

        # Switch to modal
        self._handle = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback, (context, ), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


# Used to store keymaps for addon
addon_keymaps = []

def register():
    bpy.utils.register_class(CGCOOKIE_OT_polystrips)

    bpy.utils.register_class(RetopoFlowPreferences)
    bpy.utils.register_class(CGCOOKIE_OT_retopoflow_panel)
    bpy.utils.register_class(CGCOOKIE_OT_contours_cache_clear)
    bpy.utils.register_class(CGCOOKIE_OT_contours)
    bpy.utils.register_class(CGCOOKIE_OT_retopoflow_menu)

    # Create the addon hotkeys
    kc = bpy.context.window_manager.keyconfigs.addon
   
    # create the mode switch menu hotkey
    km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
    kmi = km.keymap_items.new('wm.call_menu', 'V', 'PRESS', ctrl=True, shift=True)
    kmi.properties.name = 'object.retopology_menu' 
    kmi.active = True
    addon_keymaps.append((km, kmi))


def unregister():
    bpy.utils.unregister_class(CGCOOKIE_OT_polystrips)

    clear_mesh_cache()
    bpy.utils.unregister_class(CGCOOKIE_OT_contours)
    bpy.utils.unregister_class(CGCOOKIE_OT_contours_cache_clear)
    bpy.utils.unregister_class(CGCOOKIE_OT_retopoflow_panel)
    bpy.utils.unregister_class(CGCOOKIE_OT_retopoflow_menu)
    bpy.utils.unregister_class(RetopoFlowPreferences)

    # Remove addon hotkeys
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()


class PolystripsUI:
    def __init__(self, context, event):
        settings = common_utilities.get_settings()

        self.mode = 'main'
        
        self.fullscreened = False

        self.mode_pos = (0, 0)
        self.cur_pos = (0, 0)
        self.mode_radius = 0
        self.action_center = (0, 0)
        self.action_radius = 0
        self.is_navigating = False
        self.sketch_curpos = (0, 0)
        self.sketch_pressure = 1
        self.sketch = []
        
        self.tweak_data = None

        self.post_update = True

        self.footer = ''
        self.footer_last = ''

        self.last_matrix = None

        self._timer = context.window_manager.event_timer_add(0.1, context.window)

        self.stroke_smoothing = 0.75          # 0: no smoothing. 1: no change

        if context.mode == 'OBJECT':

            self.obj_orig = context.object
            # duplicate selected objected to temporary object but with modifiers applied
            self.me = self.obj_orig.to_mesh(scene=context.scene, apply_modifiers=True, settings='PREVIEW')
            self.me.update()
            self.obj = bpy.data.objects.new('PolystripsTmp', self.me)
            bpy.context.scene.objects.link(self.obj)
            self.obj.hide = True
            self.obj.matrix_world = self.obj_orig.matrix_world
            self.me.update()

            # HACK
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.object.mode_set(mode='OBJECT')

            self.bme = bmesh.new()
            self.bme.from_mesh(self.me)

            #Create a new empty destination object for new retopo mesh
            nm_polystrips = self.obj_orig.name + "_polystrips"
            self.dest_bme = bmesh.new()
            dest_me  = bpy.data.meshes.new(nm_polystrips)
            self.dest_obj = bpy.data.objects.new(nm_polystrips, dest_me)
            self.dest_obj.matrix_world = self.obj.matrix_world
            context.scene.objects.link(self.dest_obj)
            
            self.extension_geometry = []
            self.snap_eds = []
            self.snap_eds_vis = []
            self.hover_ed = None

        if context.mode == 'EDIT_MESH':
            self.obj_orig = [ob for ob in context.selected_objects if ob != context.object][0]
            self.me = self.obj_orig.to_mesh(scene=context.scene, apply_modifiers=True, settings='PREVIEW')
            self.me.update()
            self.bme = bmesh.new()
            self.bme.from_mesh(self.me)

            self.obj = bpy.data.objects.new('PolystripsTmp', self.me)
            bpy.context.scene.objects.link(self.obj)
            self.obj.hide = True
            self.obj.matrix_world = self.obj_orig.matrix_world
            self.me.update()

            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.mode_set(mode='EDIT')

            self.dest_obj = context.object
            self.dest_bme = bmesh.from_edit_mesh(context.object.data)
            self.snap_eds = [] #EXTEND
                   
            #self.snap_eds = [ed for ed in self.dest_bme.edges if not ed.is_manifold]
            
            
            region, r3d = context.region, context.space_data.region_3d
            mx = self.dest_obj.matrix_world
            rv3d = context.space_data.region_3d
            self.snap_eds_vis = [False not in common_utilities.ray_cast_visible([mx * ed.verts[0].co, mx * ed.verts[1].co], self.obj, rv3d) for ed in self.snap_eds]
            self.hover_ed = None

        self.scale = self.obj.scale[0]
        self.length_scale = get_object_length_scale(self.obj)
        # World stroke radius
        self.stroke_radius = 0.01 * self.length_scale
        self.stroke_radius_pressure = 0.01 * self.length_scale
        # Screen_stroke_radius
        self.screen_stroke_radius = 20  # TODO, hood to settings

        self.sketch_brush = SketchBrush(context,
                                        settings,
                                        event.mouse_region_x, event.mouse_region_y,
                                        15,  # settings.quad_prev_radius,
                                        self.obj)

        self.act_gedge  = None                          # active gedge
        self.sel_gedges = set()                         # all selected gedges
        self.act_gvert  = None                          # active gvert (operated upon)
        self.sel_gverts = set()                         # all selected gverts
        self.act_gpatch = None
        self.hov_gvert = None
        self.polystrips = PolyStrips(context, self.obj, self.dest_obj)
        self.polystrips.extension_geometry_from_bme(self.dest_bme) 
        polystrips_undo_cache = []  # Clear the cache in case any is left over
        if self.obj.grease_pencil:
            self.create_polystrips_from_greasepencil()
        elif 'BezierCurve' in bpy.data.objects:
            self.create_polystrips_from_bezier(bpy.data.objects['BezierCurve'])

        context.area.header_text_set('PolyStrips')

    ###############################
    def create_undo_snapshot(self, action):
        '''
        unsure about all the _timers get deep copied
        and if sel_gedges and verts get copied as references
        or also duplicated, making them no longer valid.
        '''

        settings = common_utilities.get_settings()
        repeated_actions = {'count', 'zip count'}

        if action in repeated_actions and len(polystrips_undo_cache):
            if action == polystrips_undo_cache[-1][1]:
                dprint('repeatable...dont take snapshot')
                return

        p_data = copy.deepcopy(self.polystrips)

        if self.act_gedge:
            act_gedge = self.polystrips.gedges.index(self.act_gedge)
        else:
            act_gedge = None

        if self.act_gvert:
            act_gvert = self.polystrips.gverts.index(self.act_gvert)
        else:
            act_gvert = None

        if self.act_gvert:
            act_gvert = self.polystrips.gverts.index(self.act_gvert)
        else:
            act_gvert = None

        polystrips_undo_cache.append(([p_data, act_gvert, act_gedge, act_gvert], action))

        if len(polystrips_undo_cache) > settings.undo_depth:
            polystrips_undo_cache.pop(0)

    def undo_action(self):
        '''
        '''
        if len(polystrips_undo_cache) > 0:
            data, action = polystrips_undo_cache.pop()

            self.polystrips = data[0]

            if data[1]:
                self.act_gvert = self.polystrips.gverts[data[1]]
            else:
                self.act_gvert = None

            if data[2]:
                self.sel_gedge = self.polystrips.gedges[data[2]]
            else:
                self.sel_gedge = None

            if data[3]:
                self.act_gvert = self.polystrips.gverts[data[3]]
            else:
                self.act_gvert = None

    def cleanup(self, context):
        '''
        remove temporary object
        '''
        dprint('cleaning up!')

        tmpobj = self.obj  # Not always, sometimes if duplicate remains...will be .001
        meobj  = tmpobj.data

        # Delete object
        context.scene.objects.unlink(tmpobj)
        tmpobj.user_clear()
        if tmpobj.name in bpy.data.objects:
            bpy.data.objects.remove(tmpobj)

        bpy.context.scene.update()
        bpy.data.meshes.remove(meobj)

    ################################
    # Draw functions

    def draw_callback(self, context):
        settings = common_utilities.get_settings()
        region,r3d = context.region,context.space_data.region_3d

        new_matrix = [v for l in r3d.view_matrix for v in l]
        if self.post_update or self.last_matrix != new_matrix:
            for gv in self.polystrips.gverts:
                gv.update_visibility(r3d)
                
            for gv in self.polystrips.extension_geometry:
                gv.update_visibility(r3d)
                
            for ge in self.polystrips.gedges:
                ge.update_visibility(r3d)
            for gp in self.polystrips.gpatches:
                gp.update_visibility(r3d)
            if self.act_gedge:
                for gv in [self.act_gedge.gvert1, self.act_gedge.gvert2]:
                    gv.update_visibility(r3d)
            if self.act_gvert:
                for gv in self.act_gvert.get_inner_gverts():
                    gv.update_visibility(r3d)

            if len(self.snap_eds):
                mx = self.obj.matrix_world
                self.snap_eds_vis = [False not in common_utilities.ray_cast_visible([mx * ed.verts[0].co, mx * ed.verts[1].co], self.obj, r3d) for ed in self.snap_eds]

            self.post_update = False
            self.last_matrix = new_matrix


        if settings.debug < 3:
            self.draw_callback_themed(context)

    def draw_gedge_direction(self, context, gedge, color):
        p0,p1,p2,p3 = gedge.gvert0.snap_pos,  gedge.gvert1.snap_pos,  gedge.gvert2.snap_pos,  gedge.gvert3.snap_pos
        n0,n1,n2,n3 = gedge.gvert0.snap_norm, gedge.gvert1.snap_norm, gedge.gvert2.snap_norm, gedge.gvert3.snap_norm
        pm = cubic_bezier_blend_t(p0,p1,p2,p3,0.5)
        px = cubic_bezier_derivative(p0,p1,p2,p3,0.5).normalized()
        pn = (n0+n3).normalized()
        py = pn.cross(px).normalized()
        rs = (gedge.gvert0.radius+gedge.gvert3.radius) * 0.35
        rl = rs * 0.75
        p3d = [pm-px*rs,pm+px*rs,pm+px*(rs-rl)+py*rl,pm+px*rs,pm+px*(rs-rl)-py*rl]
        common_drawing.draw_polyline_from_3dpoints(context, p3d, color, 5, "GL_LINE_SMOOTH")


    def draw_callback_themed(self, context):
        settings = common_utilities.get_settings()
        region,r3d = context.region,context.space_data.region_3d
        
        m = Vector([-1,1,1])

        # theme_number = int(settings.theme)


        color_inactive = RetopoFlowPreferences.theme_colors_mesh[settings.theme]
        color_selection = RetopoFlowPreferences.theme_colors_selection[settings.theme]
        color_active = RetopoFlowPreferences.theme_colors_active[settings.theme]

        bgl.glEnable(bgl.GL_POINT_SMOOTH)

        color_handle = (color_inactive[0], color_inactive[1], color_inactive[2], 1.00)
        color_border = (color_inactive[0], color_inactive[1], color_inactive[2], 1.00)
        color_fill = (color_inactive[0], color_inactive[1], color_inactive[2], 0.20)

        ### Patches ###
        for i_gp,gpatch in enumerate(self.polystrips.gpatches):
            if gpatch == self.act_gpatch:
                color_border = (color_active[0], color_active[1], color_active[2], 0.50)
                color_fill = (color_active[0], color_active[1], color_active[2], 0.20)
            else:
                color_border = (color_inactive[0], color_inactive[1], color_inactive[2], 0.50)
                color_fill = (color_inactive[0], color_inactive[1], color_inactive[2], 0.10)
            
            if gpatch.is_frozen():
                color_border = (0.80,0.80,0.80,1.00)
                color_fill   = (0.80,0.80,0.80,0.20)
            
            for (p0,p1,p2,p3) in gpatch.iter_segments(only_visible=True):
                common_drawing.draw_polyline_from_3dpoints(context, [p0,p1,p2,p3,p0], color_border, 1, "GL_LINE_STIPPLE")
                common_drawing.draw_quads_from_3dpoints(context, [p0,p1,p2,p3], color_fill)
            
            common_drawing.draw_3d_points(context, [p for p,v,k in gpatch.pts if v], color_border, 3)

        ### Edges ###
        for i_ge,gedge in enumerate(self.polystrips.gedges):
            # Color active strip
            if gedge == self.act_gedge:
                color_border = (color_active[0], color_active[1], color_active[2], 1.00)
                color_fill = (color_active[0], color_active[1], color_active[2], 0.20)
            # Color selected strips
            elif gedge in self.sel_gedges:
                color_border = (color_selection[0], color_selection[1], color_selection[2], 0.75)
                color_fill = (color_selection[0], color_selection[1], color_selection[2], 0.20)
            # Color unselected strips
            else:
                color_border = (color_inactive[0], color_inactive[1], color_inactive[2], 1.00)
                color_fill = (color_inactive[0], color_inactive[1], color_inactive[2], 0.20)
            
            if gedge.is_frozen():
                color_border = (0.80,0.80,0.80,1.00)
                color_fill   = (0.80,0.80,0.80,0.20)

            for c0,c1,c2,c3 in gedge.iter_segments(only_visible=True):
                common_drawing.draw_quads_from_3dpoints(context, [c0,c1,c2,c3], color_fill)
                common_drawing.draw_polyline_from_3dpoints(context, [c0,c1,c2,c3,c0], color_border, 1, "GL_LINE_STIPPLE")

            if settings.debug >= 2:
                # draw bezier
                p0,p1,p2,p3 = gedge.gvert0.snap_pos, gedge.gvert1.snap_pos, gedge.gvert2.snap_pos, gedge.gvert3.snap_pos
                p3d = [cubic_bezier_blend_t(p0,p1,p2,p3,t/16.0) for t in range(17)]
                common_drawing.draw_polyline_from_3dpoints(context, p3d, (1,1,1,0.5),1, "GL_LINE_STIPPLE")

        ### Verts ###
        for ge in self.sel_gedges:
            if ge == self.act_gedge: continue
            self.sel_gverts.add(ge.gvert0)
            self.sel_gverts.add(ge.gvert3)

        # Highlight possible extension gverts from existing geometry ### disable for now.
        # for gv in itertools.chain(self.polystrips.extension_geometry):
        #     if not gv.is_visible(): continue
        #     p0,p1,p2,p3 = gv.get_corners()

        #     if gv.is_unconnected() and not gv.from_mesh: continue

        #     color_border = (color_inactive[0], color_inactive[1], color_inactive[2], 1.00)
        #     color_fill   = (color_inactive[0], color_inactive[1], color_inactive[2], 0.20)

        #     p3d = [p0,p1,p2,p3,p0]
        #     common_drawing.draw_quads_from_3dpoints(context, [p0,p1,p2,p3], color_fill)
        #     common_drawing.draw_polyline_from_3dpoints(context, p3d, color_border, 1, "GL_LINE_STIPPLE")

        # Color all gverts
        for gv in itertools.chain(self.polystrips.gverts):
            if not gv.is_visible(): continue
            p0,p1,p2,p3 = gv.get_corners()

            if gv.is_unconnected() and not gv.from_mesh: continue

            is_active = False
            is_active |= gv == self.act_gvert
            is_active |= self.act_gedge!=None and (self.act_gedge.gvert0 == gv or self.act_gedge.gvert1 == gv)
            is_active |= self.act_gedge!=None and (self.act_gedge.gvert2 == gv or self.act_gedge.gvert3 == gv)

            # Theme colors for selected and unselected gverts
            if is_active:
                color_border = (color_active[0], color_active[1], color_active[2], 0.75)
                color_fill   = (color_active[0], color_active[1], color_active[2], 0.20)
            else:
                color_border = (color_inactive[0], color_inactive[1], color_inactive[2], 1.00)
                color_fill   = (color_inactive[0], color_inactive[1], color_inactive[2], 0.20)
            # # Take care of gverts in selected edges
            if gv in self.sel_gverts:
                color_border = (color_selection[0], color_selection[1], color_selection[2], 0.75)
                color_fill   = (color_selection[0], color_selection[1], color_selection[2], 0.20)
            if gv.is_frozen():
                color_border = (0.80,0.80,0.80,1.00)
                color_fill   = (0.80,0.80,0.80,0.20)

            p3d = [p0,p1,p2,p3,p0]
            common_drawing.draw_quads_from_3dpoints(context, [p0,p1,p2,p3], color_fill)
            common_drawing.draw_polyline_from_3dpoints(context, p3d, color_border, 1, "GL_LINE_STIPPLE")

        # Draw inner gvert handles (dots) on each gedge
        p3d = [gvert.position for gvert in self.polystrips.gverts if not gvert.is_unconnected() and gvert.is_visible()]
        # color_handle = (color_active[0], color_active[1], color_active[2], 1.00)
        common_drawing.draw_3d_points(context, p3d, color_handle, 4)

        ### Vert Handles ###
        if self.act_gvert:
            color_handle = (color_active[0], color_active[1], color_active[2], 1.00)
            gv = self.act_gvert
            p0 = gv.position
            common_drawing.draw_3d_points(context, [p0], color_handle, 8)

        if self.act_gvert:
            color_handle = (color_active[0], color_active[1], color_active[2], 1.00)
            gv = self.act_gvert
            p0 = gv.position
            # Draw inner handle when selected
            if gv.is_inner():
                p1 = gv.gedge_inner.get_outer_gvert_at(gv).position
                common_drawing.draw_3d_points(context, [p0], color_handle, 8)
                common_drawing.draw_polyline_from_3dpoints(context, [p0,p1], color_handle, 2, "GL_LINE_SMOOTH")
            # Draw both handles when gvert is selected
            else:
                p3d = [ge.get_inner_gvert_at(gv).position for ge in gv.get_gedges_notnone() if not ge.is_zippered()]
                common_drawing.draw_3d_points(context, [p0] + p3d, color_handle, 8)
                # Draw connecting line between handles
                for p1 in p3d:
                    common_drawing.draw_polyline_from_3dpoints(context, [p0,p1], color_handle, 2, "GL_LINE_SMOOTH")

        # Draw gvert handles on active gedge
        if self.act_gedge:
            color_handle = (color_active[0], color_active[1], color_active[2], 1.00)
            ge = self.act_gedge
            if self.act_gedge.is_zippered():
                p3d = [ge.gvert0.position, ge.gvert3.position]
                common_drawing.draw_3d_points(context, p3d, color, 8)
            
            else:
                p3d = [gv.position for gv in ge.gverts()]
                common_drawing.draw_3d_points(context, p3d, color_handle, 8)
                common_drawing.draw_polyline_from_3dpoints(context, [p3d[0], p3d[1]], color_handle, 2, "GL_LINE_SMOOTH")
                common_drawing.draw_polyline_from_3dpoints(context, [p3d[2], p3d[3]], color_handle, 2, "GL_LINE_SMOOTH")

            if settings.show_segment_count:
                draw_gedge_info(self.act_gedge, context)
                
        if self.hov_gvert:  #TODO, hover color
            color_border = (color_selection[0], color_selection[1], color_selection[2], 1.00)
            color_fill   = (color_selection[0], color_selection[1], color_selection[2], 0.20)
            
            gv = self.hov_gvert
            p0,p1,p2,p3 = gv.get_corners()
            p3d = [p0,p1,p2,p3,p0]
            common_drawing.draw_quads_from_3dpoints(context, [p0,p1,p2,p3], color_fill)
            common_drawing.draw_polyline_from_3dpoints(context, p3d, color_border, 1, "GL_LINE_STIPPLE")
            

        if self.mode == 'sketch':
            # Draw smoothing line (end of sketch to current mouse position)
            common_drawing.draw_polyline_from_points(context, [self.sketch_curpos, self.sketch[-1][0]], color_active, 1, "GL_LINE_SMOOTH")

            # Draw sketching stroke
            common_drawing.draw_polyline_from_points(context, [co[0] for co in self.sketch], color_selection, 2, "GL_LINE_STIPPLE")

            # Report pressure reading
            if settings.use_pressure:
                info = str(round(self.sketch_pressure,3))
                txt_width, txt_height = blf.dimensions(0, info)
                d = self.sketch_brush.pxl_rad
                blf.position(0, self.sketch_curpos[0] - txt_width/2, self.sketch_curpos[1] + d + txt_height, 0)
                blf.draw(0, info)

        if self.mode in {'scale tool','rotate tool'}:
            # Draw a scale/rotate line from tool origin to current mouse position
            common_drawing.draw_polyline_from_points(context, [self.action_center, self.mode_pos], (0, 0, 0, 0.5), 1, "GL_LINE_STIPPLE")

        bgl.glLineWidth(1)

        if self.mode == 'brush scale tool':
            # scaling brush size
            self.sketch_brush.draw(context, color=(1, 1, 1, .5), linewidth=1, color_size=(1, 1, 1, 1))
        elif self.mode not in {'grab tool','scale tool','rotate tool'} and not self.is_navigating:
            # draw the brush oriented to surface
            ray,hit = common_utilities.ray_cast_region2d(region, r3d, self.cur_pos, self.obj, settings)
            hit_p3d,hit_norm,hit_idx = hit
            if hit_idx != -1: # and not self.hover_ed:
                mx = self.obj.matrix_world
                mxnorm = mx.transposed().inverted().to_3x3()
                hit_p3d = mx * hit_p3d
                hit_norm = mxnorm * hit_norm
                if settings.use_pressure:
                    common_drawing.draw_circle(context, hit_p3d, hit_norm.normalized(), self.stroke_radius_pressure, (1,1,1,.5))
                else:
                    common_drawing.draw_circle(context, hit_p3d, hit_norm.normalized(), self.stroke_radius, (1,1,1,.5))
            if self.mode == 'sketch':
                ray,hit = common_utilities.ray_cast_region2d(region, r3d, self.sketch[0][0], self.obj, settings)
                hit_p3d,hit_norm,hit_idx = hit
                if hit_idx != -1:
                    mx = self.obj.matrix_world
                    mxnorm = mx.transposed().inverted().to_3x3()
                    hit_p3d = mx * hit_p3d
                    hit_norm = mxnorm * hit_norm
                    if settings.use_pressure:
                        common_drawing.draw_circle(context, hit_p3d, hit_norm.normalized(), self.stroke_radius_pressure, (1,1,1,.5))
                    else:
                        common_drawing.draw_circle(context, hit_p3d, hit_norm.normalized(), self.stroke_radius, (1,1,1,.5))

        if self.hover_ed and False:  #EXTEND  to display hoverable edges
            color = (color_selection[0], color_selection[1], color_selection[2], 1.00)
            common_drawing.draw_bmedge(context, self.hover_ed, self.dest_obj.matrix_world, 2, color)


    def create_mesh(self, context):
        verts,quads,non_quads = self.polystrips.create_mesh(self.dest_bme)

        if 'EDIT' in context.mode:  #self.dest_bme and self.dest_obj:  #EDIT MODE on Existing Mesh
            mx = self.dest_obj.matrix_world
            imx = mx.inverted()

            mx2 = self.obj.matrix_world
            imx2 = mx2.inverted()

        else:
            #bm = bmesh.new()  #now new bmesh is created at the start
            mx2 = Matrix.Identity(4)
            imx = Matrix.Identity(4)

            self.dest_obj.update_tag()
            self.dest_obj.show_all_edges = True
            self.dest_obj.show_wire      = True
            self.dest_obj.show_x_ray     = True
         
            self.dest_obj.select = True
            context.scene.objects.active = self.dest_obj
        
        container_bme = bmesh.new()
        
        bmverts = [container_bme.verts.new(imx * mx2 * v) for v in verts]
        container_bme.verts.index_update()
        for q in quads: 
            container_bme.faces.new([bmverts[i] for i in q])
        for nq in non_quads:
            container_bme.faces.new([bmverts[i] for i in nq])
        
        container_bme.faces.index_update()

        if 'EDIT' in context.mode: #self.dest_bme and self.dest_obj:
            bpy.ops.object.mode_set(mode='OBJECT')
            container_bme.to_mesh(self.dest_obj.data)
            bpy.ops.object.mode_set(mode = 'EDIT')
            #bmesh.update_edit_mesh(self.dest_obj.data, tessface=False, destructive=True)
        else: 
            container_bme.to_mesh(self.dest_obj.data)
        
        self.dest_bme.free()
        container_bme.free()

    ###########################
    # fill function

    def fill(self, eventd):
        
        # GVert active
        if self.act_gvert:
            lges = self.act_gvert.get_gedges()
            if self.act_gvert.is_ljunction():
                lgepairs = [(lges[0],lges[1])]
            elif self.act_gvert.is_tjunction():
                lgepairs = [(lges[0],lges[1]), (lges[3],lges[0])]
            elif self.act_gvert.is_cross():
                lgepairs = [(lges[0],lges[1]), (lges[1],lges[2]), (lges[2],lges[3]), (lges[3],lges[0])]
            else:
                showErrorMessage('GVert must be a L-junction, T-junction, or Cross type to use simple fill')
                return
            
            # find gedge pair that is not a part of a gpatch
            lgepairs = [(ge0,ge1) for ge0,ge1 in lgepairs if not set(ge0.gpatches).intersection(set(ge1.gpatches))]
            if not lgepairs:
                showErrorMessage('Could not find two GEdges that are not already patched')
                return
            
            self.sel_gedges = set(lgepairs[0])
            self.act_gedge = next(iter(self.sel_gedges))
            self.act_gvert = None
        
        loop_selected = True
        sgedges = set(self.sel_gedges)
        ge0 = sgedges.pop()
        gedges = [ge0]
        while sgedges and loop_selected:
            for ge1 in sgedges:
                if ge1.has_endpoint(ge0.gvert3) or ge1.has_endpoint(ge0.gvert0):
                    gedges += [ge1]
                    sgedges.remove(ge1)
                    ge0 = ge1
                    break
            else:
                loop_selected = False
        
        if len(self.sel_gedges) not in {3,4,5} and loop_selected:
            showErrorMessage('Can only fill a 3-, 4-, or 5-sided patch')
            return
            
        if len(self.sel_gedges) == 5 and not loop_selected:
            showErrorMessage('Must select five GEdges that form a ring!')
            return
        
        
        if loop_selected:
            
            # test if we need to change direction!
            gv0,gv1 = gedges[0].gvert0,gedges[0].gvert3
            gv2 = gedges[-1].gvert0 if gedges[-1].gvert3 in [gv0,gv1] else gedges[-1].gvert3
            if gv0 != gedges[-1].gvert0 and gv0 != gedges[-1].gvert3:
                gv0,gv1 = gv1,gv0
            n0 = gv0.snap_norm
            n1 = (gv1.snap_pos-gv0.snap_pos).cross(gv2.snap_pos-gv0.snap_pos).normalized()
            if n0.dot(n1) > 0:
                gedges.reverse()
            
            gp = self.polystrips.create_gpatch(*gedges)
            self.act_gvert = None
            self.act_gedge = None
            self.sel_gedges.clear()
            self.sel_gverts.clear()
            self.act_gpatch = gp
            
            gp.update()
            self.polystrips.update_visibility(eventd['r3d'])
            return
        
        if len(self.sel_gedges) != 2:
            showErrorMessage('Must have exactly 2 selected edges')
            return

        # check that we have a hole
        # TODO: handle multiple edges on one side
        
        sge0 = self.act_gedge
        sge1 = [ge for ge in self.sel_gedges if ge!=sge0][0]
        
        lcgvs = [gv for gv in [sge0.gvert0,sge0.gvert3] if gv in [sge1.gvert0,sge1.gvert3]]
        if lcgvs:
            # corner!
            if len(lcgvs) == 2:
                # Eye shape
                showErrorMessage('Cannot simple fill this shape, yet!')
                return
            cgv = lcgvs[0]
            logvs = [gv for gv in [sge0.gvert0,sge0.gvert3,sge1.gvert0,sge1.gvert3] if gv != cgv]
            assert len(logvs) == 2
            np = cgv.snap_pos + (logvs[0].snap_pos - cgv.snap_pos) + (logvs[1].snap_pos - cgv.snap_pos)
            nr = cgv.radius + (logvs[0].radius - cgv.radius) + (logvs[1].radius - cgv.radius)
            ngv = self.polystrips.create_gvert(np, radius=nr)
            sge0 = self.polystrips.insert_gedge_between_gverts(logvs[0], ngv)
            self.polystrips.insert_gedge_between_gverts(logvs[1], ngv)
        
        lgedge,rgedge = sge0,sge1
        tlgvert = lgedge.gvert0
        blgvert = lgedge.gvert3

        trgvert,brgvert = None,None
        tgedge,bgedge = None,None
        for gv in [rgedge.gvert0,rgedge.gvert3]:
            for ge in gv.get_gedges_notnone():
                if ge.gvert0 == tlgvert:
                    trgvert = ge.gvert3
                    tgedge = ge
                if ge.gvert0 == blgvert:
                    brgvert = ge.gvert3
                    bgedge = ge
                if ge.gvert3 == tlgvert:
                    trgvert = ge.gvert0
                    tgedge = ge
                if ge.gvert3 == blgvert:
                    brgvert = ge.gvert0
                    bgedge = ge
        
        if any(ge.is_zippered() for ge in [lgedge,rgedge,tgedge,bgedge] if ge):
            showErrorMessage('Cannot use simple fill with zippered edges')
            return

        # handle cases where selected gedges have no or only one connecting gedge
        if not trgvert and not brgvert:
            # create two gedges
            dl = (blgvert.position - tlgvert.position).normalized()
            d0 = (rgedge.gvert0.position - tlgvert.position).normalized()
            d3 = (rgedge.gvert3.position - tlgvert.position).normalized()
            if dl.dot(d0) > dl.dot(d3):
                trgvert = rgedge.gvert3
                brgvert = rgedge.gvert0
            else:
                trgvert = rgedge.gvert0
                brgvert = rgedge.gvert3
            tgedge = self.polystrips.insert_gedge_between_gverts(tlgvert, trgvert)
            bgedge = self.polystrips.insert_gedge_between_gverts(blgvert, brgvert)
        elif not trgvert and brgvert:
            if brgvert == rgedge.gvert0:
                trgvert = rgedge.gvert3
            else:
                trgvert = rgedge.gvert0
            tgedge = self.polystrips.insert_gedge_between_gverts(tlgvert, trgvert)
        elif not brgvert and trgvert:
            if trgvert == rgedge.gvert0:
                brgvert = rgedge.gvert3
            else:
                brgvert = rgedge.gvert0
            bgedge = self.polystrips.insert_gedge_between_gverts(blgvert, brgvert)

        if not all(gv.is_ljunction for gv in [trgvert,tlgvert,blgvert,brgvert]):
            showErrorMessage('All corners must be L-Junctions')
            return
        
        if tlgvert.snap_norm.dot((trgvert.snap_pos-tlgvert.snap_pos).cross(blgvert.snap_pos-tlgvert.snap_pos)) < 0:
            lgedge,bgedge,rgedge,tgedge = lgedge,tgedge,rgedge,bgedge

        gp = self.polystrips.create_gpatch(lgedge, bgedge, rgedge, tgedge)
        self.act_gvert = None
        self.act_gedge = None
        self.sel_gedges.clear()
        self.sel_gverts.clear()
        self.act_gpatch = gp
        
        gp.update()
        self.polystrips.update_visibility(eventd['r3d'])



    ###########################
    # hover functions

    def hover_geom(self,eventd):
        
        if not len(self.polystrips.extension_geometry): return
        self.hov_gvert = None
        for gv in self.polystrips.extension_geometry:
            if not gv.is_visible(): continue
            rgn   = eventd['context'].region
            r3d   = eventd['context'].space_data.region_3d
            mx,my = eventd['mouse']
            c0 = location_3d_to_region_2d(rgn, r3d, gv.corner0)
            c1 = location_3d_to_region_2d(rgn, r3d, gv.corner1)
            c2 = location_3d_to_region_2d(rgn, r3d, gv.corner2)
            c3 = location_3d_to_region_2d(rgn, r3d, gv.corner3)
            inside = contour_utilities.point_inside_loop2d([c0,c1,c2,c3],Vector((mx,my)))
            if inside:
                self.hov_gvert = gv
                break
                print('found hover gv')
    ###########################
    # tool functions

    def ready_tool(self, eventd, tool_fn):
        rgn   = eventd['context'].region
        r3d   = eventd['context'].space_data.region_3d
        mx,my = eventd['mouse']
        if self.act_gvert:
            loc   = self.act_gvert.position
            cx,cy = location_3d_to_region_2d(rgn, r3d, loc)
        elif self.act_gedge:
            loc   = (self.act_gedge.gvert0.position + self.act_gedge.gvert3.position) / 2.0
            cx,cy = location_3d_to_region_2d(rgn, r3d, loc)
        else:
            cx,cy = mx-100,my
        rad   = math.sqrt((mx-cx)**2 + (my-cy)**2)

        self.action_center = (cx,cy)
        self.mode_start    = (mx,my)
        self.action_radius = rad
        self.mode_radius   = rad
        
        self.prev_pos      = (mx,my)

        # spc = bpy.data.window_managers['WinMan'].windows[0].screen.areas[4].spaces[0]
        # r3d = spc.region_3d
        vrot = r3d.view_rotation
        self.tool_x = (vrot * Vector((1,0,0))).normalized()
        self.tool_y = (vrot * Vector((0,1,0))).normalized()

        self.tool_rot = 0.0

        self.tool_fn = tool_fn
        self.tool_fn('init', eventd)

    def scale_tool_gvert(self, command, eventd):
        if command == 'init':
            self.footer = 'Scaling GVerts'
            sgv = self.act_gvert
            lgv = [ge.gvert1 if ge.gvert0==sgv else ge.gvert2 for ge in sgv.get_gedges() if ge]
            self.tool_data = [(gv,Vector(gv.position)) for gv in lgv]
        elif command == 'commit':
            pass
        elif command == 'undo':
            for gv,p in self.tool_data:
                gv.position = p
                gv.update()
            self.act_gvert.update()
            self.act_gvert.update_visibility(eventd['r3d'], update_gedges=True)
        else:
            m = command
            sgv = self.act_gvert
            p = sgv.position
            for ge in sgv.get_gedges():
                if not ge: continue
                gv = ge.gvert1 if ge.gvert0 == self.act_gvert else ge.gvert2
                gv.position = p + (gv.position-p) * m
                gv.update()
            sgv.update()
            self.act_gvert.update_visibility(eventd['r3d'], update_gedges=True)

    def scale_tool_gvert_radius(self, command, eventd):
        if command == 'init':
            self.footer = 'Scaling GVert radius'
            self.tool_data = self.act_gvert.radius
        elif command == 'commit':
            pass
        elif command == 'undo':
            self.act_gvert.radius = self.tool_data
            self.act_gvert.update()
            self.act_gvert.update_visibility(eventd['r3d'], update_gedges=True)
        else:
            m = command
            self.act_gvert.radius *= m
            self.act_gvert.update()
            self.act_gvert.update_visibility(eventd['r3d'], update_gedges=True)

    def scale_tool_stroke_radius(self, command, eventd):
        if command == 'init':
            self.footer = 'Scaling Stroke radius'
            self.tool_data = self.stroke_radius
        elif command == 'commit':
            pass
        elif command == 'undo':
            self.stroke_radius = self.tool_data
        else:
            m = command
            self.stroke_radius *= m

    def grab_tool_gvert_list(self, command, eventd, lgv):
        '''
        translates list of gverts
        note: translation is relative to first gvert
        '''

        def l3dr2d(p): return location_3d_to_region_2d(eventd['region'], eventd['r3d'], p)

        if command == 'init':
            self.footer = 'Translating GVert position(s)'
            s2d = l3dr2d(lgv[0].position)
            self.tool_data = [(gv, Vector(gv.position), l3dr2d(gv.position)-s2d) for gv in lgv]
        elif command == 'commit':
            pass
        elif command == 'undo':
            for gv,p,_ in self.tool_data: gv.position = p
            for gv,_,_ in self.tool_data:
                gv.update()
                gv.update_visibility(eventd['r3d'], update_gedges=True)
        else:
            factor_slow,factor_fast = 0.2,1.0
            dv = Vector(command) * (factor_slow if eventd['shift'] else factor_fast)
            s2d = l3dr2d(self.tool_data[0][0].position)
            lgv2d = [s2d+relp+dv for _,_,relp in self.tool_data]
            pts = common_utilities.ray_cast_path(eventd['context'], self.obj, lgv2d)
            if len(pts) != len(lgv2d): return ''
            for d,p2d in zip(self.tool_data, pts):
                d[0].position = p2d
            for gv,_,_ in self.tool_data:
                gv.update()
                gv.update_visibility(eventd['r3d'], update_gedges=True)

    def grab_tool_gvert(self, command, eventd):
        '''
        translates selected gvert
        '''
        if command == 'init':
            lgv = [self.act_gvert]
        else:
            lgv = None
        self.grab_tool_gvert_list(command, eventd, lgv)

    def grab_tool_gvert_neighbors(self, command, eventd):
        '''
        translates selected gvert and its neighbors
        note: translation is relative to selected gvert
        '''
        if command == 'init':
            sgv = self.act_gvert
            lgv = [sgv] + [ge.get_inner_gvert_at(sgv) for ge in sgv.get_gedges_notnone()]
        else:
            lgv = None
        self.grab_tool_gvert_list(command, eventd, lgv)

    def grab_tool_gedge(self, command, eventd):
        if command == 'init':
            sge = self.act_gedge
            lgv = [sge.gvert0, sge.gvert3]
            lgv += [ge.get_inner_gvert_at(gv) for gv in lgv for ge in gv.get_gedges_notnone()]
        else:
            lgv = None
        self.grab_tool_gvert_list(command, eventd, lgv)

    def rotate_tool_gvert_neighbors(self, command, eventd):
        if command == 'init':
            self.footer = 'Rotating GVerts'
            self.tool_data = [(gv,Vector(gv.position)) for gv in self.act_gvert.get_inner_gverts()]
        elif command == 'commit':
            pass
        elif command == 'undo':
            for gv,p in self.tool_data:
                gv.position = p
                gv.update()
        else:
            ang = command
            q = Quaternion(self.act_gvert.snap_norm, ang)
            p = self.act_gvert.position
            for gv,up in self.tool_data:
                gv.position = p+q*(up-p)
                gv.update()

    def scale_brush_pixel_radius(self,command, eventd):
        if command == 'init':
            self.footer = 'Scale Brush Pixel Size'
            self.tool_data = self.stroke_radius
            x,y = eventd['mouse']
            self.sketch_brush.brush_pix_size_init(eventd['context'], x, y)
        elif command == 'commit':
            self.sketch_brush.brush_pix_size_confirm(eventd['context'])
            if self.sketch_brush.world_width:
                self.stroke_radius = self.sketch_brush.world_width
        elif command == 'undo':
            self.sketch_brush.brush_pix_size_cancel(eventd['context'])
            self.stroke_radius = self.tool_data
        else:
            x,y = command
            self.sketch_brush.brush_pix_size_interact(x, y, precise = eventd['shift'])


    ##############################
    # modal state functions

    def modal_nav(self, eventd):
        events_numpad = {
            'NUMPAD_1',       'NUMPAD_2',       'NUMPAD_3',
            'NUMPAD_4',       'NUMPAD_5',       'NUMPAD_6',
            'NUMPAD_7',       'NUMPAD_8',       'NUMPAD_9',
            'CTRL+NUMPAD_1',  'CTRL+NUMPAD_2',  'CTRL+NUMPAD_3',
            'CTRL+NUMPAD_4',  'CTRL+NUMPAD_5',  'CTRL+NUMPAD_6',
            'CTRL+NUMPAD_7',  'CTRL+NUMPAD_8',  'CTRL+NUMPAD_9',
            'SHIFT+NUMPAD_1', 'SHIFT+NUMPAD_2', 'SHIFT+NUMPAD_3',
            'SHIFT+NUMPAD_4', 'SHIFT+NUMPAD_5', 'SHIFT+NUMPAD_6',
            'SHIFT+NUMPAD_7', 'SHIFT+NUMPAD_8', 'SHIFT+NUMPAD_9',
            'NUMPAD_PLUS', 'NUMPAD_MINUS', # CTRL+NUMPAD_PLUS and CTRL+NUMPAD_MINUS are used elsewhere
            'NUMPAD_PERIOD',
        }

        handle_nav = False
        handle_nav |= eventd['type'] == 'MIDDLEMOUSE'
        handle_nav |= eventd['type'] == 'MOUSEMOVE' and self.is_navigating
        handle_nav |= eventd['type'].startswith('NDOF_')
        handle_nav |= eventd['type'].startswith('TRACKPAD')
        handle_nav |= eventd['ftype'] in events_numpad
        handle_nav |= eventd['ftype'] in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}

        if handle_nav:
            self.post_update = True
            self.is_navigating = True

            return 'nav' if eventd['value']=='PRESS' else 'main'

        self.is_navigating = False
        return ''

    def modal_main(self, eventd):

        settings = common_utilities.get_settings()

        self.footer = 'LMB: draw, RMB: select, G: grab, R: rotate, S: scale, F: brush size, K: knife, M: merge, X: delete, CTRL+D: dissolve, CTRL+Wheel Up/Down: adjust segments, CTRL+C: change selected junction type'

        #############################################
        # General navigation

        nmode = self.modal_nav(eventd)
        if nmode:
            return nmode

        ########################################
        # accept / cancel

        if eventd['press'] in {'RET', 'NUMPAD_ENTER'}:
            self.create_mesh(eventd['context'])
            eventd['context'].area.header_text_set()
            return 'finish'

        if eventd['press'] in {'ESC'}:
            eventd['context'].area.header_text_set()
            return 'cancel'

        #####################################
        # General

        if eventd['type'] == 'MOUSEMOVE':  #mouse movement/hovering
            #update brush and brush size
            x,y = eventd['mouse']
            self.sketch_brush.update_mouse_move_hover(eventd['context'], x,y)
            self.sketch_brush.make_circles()
            self.sketch_brush.get_brush_world_size(eventd['context'])

            if self.sketch_brush.world_width:
                self.stroke_radius = self.sketch_brush.world_width
                self.stroke_radius_pressure = self.sketch_brush.world_width

            self.hover_geom(eventd)

        if eventd['press'] == 'CTRL+Z':
            self.undo_action()
            return ''

        if eventd['press'] == 'F':
            self.ready_tool(eventd, self.scale_brush_pixel_radius)
            return 'brush scale tool'

        if eventd['press'] == 'Q':                                                  # profiler printout
            profiler.printout()
            return ''

        if eventd['press'] == 'P':                                                  # grease pencil => strokes
            # TODO: only convert gpencil strokes that are visible and prevent duplicate conversion
            for gpl in self.obj.grease_pencil.layers: gpl.hide = True
            for stroke in self.strokes_original:
                self.polystrips.insert_gedge_from_stroke(stroke, True)
            self.polystrips.remove_unconnected_gverts()
            self.polystrips.update_visibility(eventd['r3d'])
            return ''
        
        if eventd['press'] in {'T','SHIFT+T'}:
            self.create_undo_snapshot('tweak')
            self.footer = 'Tweak: ' + ('Moving' if eventd['press']=='T' else 'Relaxing')
            self.act_gvert = None
            self.act_gedge = None
            self.sel_gedges = set()
            self.act_gpatch = None
            return 'tweak move tool' if eventd['press']=='T' else 'tweak relax tool'
        
        # Selecting and Sketching
        ## if LMB is set to select, selecting happens in def modal_sketching
        if eventd['press'] in {'LEFTMOUSE', 'CTRL+LEFTMOUSE'}:
            self.create_undo_snapshot('sketch')
            # start sketching
            self.footer = 'Sketching'
            x,y = eventd['mouse']

            if settings.use_pressure:
                p = eventd['pressure']
                r = eventd['mradius']
            else:
                p = 1
                r = self.stroke_radius

            self.sketch_curpos = (x,y)

            if eventd['ctrl'] and self.act_gvert:
                # continue sketching from selected gvert position
                gvx,gvy = location_3d_to_region_2d(eventd['region'], eventd['r3d'], self.act_gvert.position)
                self.sketch = [((gvx,gvy),self.act_gvert.radius), ((x,y),r)]
            else:
                self.sketch = [((x,y),r)]
            
            return 'sketch'

        # If RMB is set to select, select as normal
        if eventd['press'] in {'RIGHTMOUSE', 'SHIFT+RIGHTMOUSE'}:
            if 'LEFTMOUSE' not in selection_mouse():
                # Select element
                self.pick(eventd)
            return ''

        if eventd['press'] == 'CTRL+U':
            self.create_undo_snapshot('update')
            for gv in self.polystrips.gverts:
                gv.update_gedges()

        ###################################
        # Selected gpatch commands
        
        if self.act_gpatch:
            if eventd['press'] == 'X':
                self.create_undo_snapshot('delete')
                self.polystrips.disconnect_gpatch(self.act_gpatch)
                self.act_gpatch = None
                return ''
            if eventd['press'] in {'R','SHIFT+R'}:
                reverse = eventd['press']=='SHIFT+R'
                self.act_gpatch.rotate_pole(reverse=reverse)
                self.polystrips.update_visibility(eventd['r3d'])
                return ''

        ###################################
        # Selected gedge commands
     
        if self.act_gedge:
            if eventd['press'] == 'X':
                self.create_undo_snapshot('delete')
                self.polystrips.disconnect_gedge(self.act_gedge)
                self.act_gedge = None
                self.sel_gedges.clear()
                self.polystrips.remove_unconnected_gverts()
                return ''

            if eventd['press'] == 'K' and not self.act_gedge.is_zippered() and not self.act_gedge.has_zippered() and not self.act_gedge.is_gpatched():
                self.create_undo_snapshot('knife')
                x,y = eventd['mouse']
                pts = common_utilities.ray_cast_path(eventd['context'], self.obj, [(x,y)])
                if not pts:
                    return ''
                t,_    = self.act_gedge.get_closest_point(pts[0])
                _,_,gv = self.polystrips.split_gedge_at_t(self.act_gedge, t)
                self.act_gedge = None
                self.sel_gedges.clear()
                self.act_gvert = gv
                self.act_gvert = gv
                return ''

            if eventd['press'] == 'U':
                self.create_undo_snapshot('update')
                self.act_gedge.gvert0.update_gedges()
                self.act_gedge.gvert3.update_gedges()
                return ''

            if eventd['press']in {'OSKEY+WHEELUPMOUSE', 'CTRL+NUMPAD_PLUS'}:
                self.create_undo_snapshot('count')
                self.act_gedge.set_count(self.act_gedge.n_quads + 1)
                self.polystrips.update_visibility(eventd['r3d'])
                return ''

            if eventd['press'] in {'OSKEY+WHEELDOWNMOUSE', 'CTRL+NUMPAD_MINUS'}:

                if self.act_gedge.n_quads > 3:
                    self.create_undo_snapshot('count')
                    self.act_gedge.set_count(self.act_gedge.n_quads - 1)
                    self.polystrips.update_visibility(eventd['r3d'])
                return ''

            if eventd['press'] == 'Z' and not self.act_gedge.is_gpatched():

                if self.act_gedge.zip_to_gedge:
                    self.create_undo_snapshot('unzip')
                    self.act_gedge.unzip()
                    return ''

                lge = self.act_gedge.gvert0.get_gedges_notnone() + self.act_gedge.gvert3.get_gedges_notnone()
                if any(ge.is_zippered() for ge in lge):
                    # prevent zippering a gedge with gvert that has a zippered gedge already
                    # TODO: allow this??
                    return ''

                x,y = eventd['mouse']
                pts = common_utilities.ray_cast_path(eventd['context'], self.obj, [(x,y)])
                if not pts:
                    return ''
                pt = pts[0]
                for ge in self.polystrips.gedges:
                    if ge == self.act_gedge: continue
                    if not ge.is_picked(pt): continue
                    self.create_undo_snapshot('zip')
                    self.act_gedge.zip_to(ge)
                    return ''
                return ''

            if eventd['press'] == 'G':
                if not self.act_gedge.is_zippered():
                    self.create_undo_snapshot('grab')
                    self.ready_tool(eventd, self.grab_tool_gedge)
                    return 'grab tool'
                return ''

            if eventd['press'] == 'A':
                self.act_gvert = self.act_gedge.gvert0
                self.act_gedge = None
                self.sel_gedges.clear()
                return ''
            if eventd['press'] == 'B':
                self.act_gvert = self.act_gedge.gvert3
                self.act_gedge = None
                self.sel_gedges.clear()
                return ''

            if eventd['press'] == 'CTRL+R' and not self.act_gedge.is_zippered():
                self.create_undo_snapshot('rip')
                self.act_gedge = self.polystrips.rip_gedge(self.act_gedge)
                self.sel_gedges = [self.act_gedge]
                self.ready_tool(eventd, self.grab_tool_gedge)
                return 'grab tool'

            if eventd['press'] == 'SHIFT+F':
                self.create_undo_snapshot('simplefill')
                self.fill(eventd)
                return ''

        ###################################
        # selected gvert commands

        if self.act_gvert:

            if eventd['press'] == 'K':
                if not self.act_gvert.is_endpoint():
                    showErrorMessage('Selected GVert must be endpoint (exactly one GEdge)')
                    return ''
                x,y = eventd['mouse']
                pts = common_utilities.ray_cast_path(eventd['context'], self.obj, [(x,y)])
                if not pts:
                    return ''
                pt = pts[0]
                for ge in self.polystrips.gedges:
                    if not ge.is_picked(pt): continue
                    if ge.is_zippered() or ge.is_gpatched():
                        showErrorMessage('Cannot knife a GEdge that is zippered or patched')
                        continue
                    self.create_undo_snapshot('split')
                    t,d = ge.get_closest_point(pt)
                    self.polystrips.split_gedge_at_t(ge, t, connect_gvert=self.act_gvert)
                    return ''
                return ''

            if eventd['press'] == 'X':
                if self.act_gvert.is_inner():
                    return ''
                self.create_undo_snapshot('delete')
                self.polystrips.disconnect_gvert(self.act_gvert)
                self.act_gvert = None
                self.polystrips.remove_unconnected_gverts()
                return ''

            if eventd['press'] == 'CTRL+D':
                if any(ge.is_zippered() or ge.is_gpatched() for ge in self.act_gvert.get_gedges_notnone()):
                    showErrorMessage('Cannot dissolve GVert with GEdge that is zippered or patched')
                    return ''
                self.create_undo_snapshot('dissolve')
                self.polystrips.dissolve_gvert(self.act_gvert)
                self.act_gvert = None
                self.polystrips.remove_unconnected_gverts()
                self.polystrips.update_visibility(eventd['r3d'])
                return ''

            if eventd['press'] == 'S' and not self.act_gvert.is_unconnected():
                self.create_undo_snapshot('scale')
                self.ready_tool(eventd, self.scale_tool_gvert_radius)
                return 'scale tool'

            if eventd['press'] == 'CTRL+G':
                self.create_undo_snapshot('grab')
                self.ready_tool(eventd, self.grab_tool_gvert)
                return 'grab tool'

            if eventd['press'] == 'G':
                self.create_undo_snapshot('grab')
                self.ready_tool(eventd, self.grab_tool_gvert_neighbors)
                return 'grab tool'

            if eventd['press'] == 'CTRL+C':
                if any(ge.is_zippered() or ge.is_gpatched() for ge in self.act_gvert.get_gedges_notnone()):
                    showErrorMessage('Cannot change corner type of GVert with GEdge that is zippered or patched')
                    return ''
                self.create_undo_snapshot('toggle')
                self.act_gvert.toggle_corner()
                self.act_gvert.update_visibility(eventd['r3d'], update_gedges=True)
                return ''

            if eventd['press'] == 'CTRL+S' and not self.act_gvert.is_unconnected():
                self.create_undo_snapshot('scale')
                self.ready_tool(eventd, self.scale_tool_gvert)
                return 'scale tool'

            if eventd['press'] == 'C':
                self.create_undo_snapshot('smooth')
                self.act_gvert.smooth()
                self.act_gvert.update_visibility(eventd['r3d'], update_gedges=True)
                return ''

            if eventd['press'] == 'R':
                self.create_undo_snapshot('rotate')
                self.ready_tool(eventd, self.rotate_tool_gvert_neighbors)
                return 'rotate tool'

            if eventd['press'] == 'U':
                self.act_gvert.update_gedges()
                return ''

            if eventd['press'] == 'CTRL+R':
                # self.polystrips.rip_gvert(self.act_gvert)
                # self.act_gvert = None
                # return ''
                if any(ge.is_zippered() or ge.is_gpatched() for ge in self.act_gvert.get_gedges_notnone()):
                    showErrorMessage('Cannot rip GVert with GEdge that is zippered or patched')
                    return ''
                x,y = eventd['mouse']
                pts = common_utilities.ray_cast_path(eventd['context'], self.obj, [(x,y)])
                if not pts:
                    return ''
                pt = pts[0]
                for ge in self.act_gvert.get_gedges_notnone():
                    if not ge.is_picked(pt): continue
                    self.create_undo_snapshot('rip')
                    self.act_gvert = self.polystrips.rip_gedge(ge, at_gvert=self.act_gvert)
                    self.ready_tool(eventd, self.grab_tool_gvert_neighbors)
                    return 'grab tool'
                showErrorMessage('Must hover over GEdge you wish to rip')
                return ''
  
            if eventd['press'] == 'M':
                if self.act_gvert.is_inner():
                    showErrorMessage('Cannot merge inner GVert')
                    return ''
                if any(ge.is_zippered() or ge.is_gpatched() for ge in self.act_gvert.get_gedges_notnone()):
                    showErrorMessage('Cannot merge inner GVert with GEdge that is zippered or patched')
                    return ''
                x,y = eventd['mouse']
                pts = common_utilities.ray_cast_path(eventd['context'], self.obj, [(x,y)])
                if not pts:
                    return ''
                pt = pts[0]
                sel_ge = set(self.act_gvert.get_gedges_notnone())
                for gv in self.polystrips.gverts:
                    if gv.is_inner() or not gv.is_picked(pt) or gv == self.act_gvert: continue
                    if any(ge.is_zippered() or ge.is_gpatched() for ge in gv.get_gedges_notnone()):
                        showErrorMessage('Cannot merge GVert with GEdge that is zippered or patched')
                        return ''
                    if len(self.act_gvert.get_gedges_notnone()) + len(gv.get_gedges_notnone()) > 4:
                        showErrorMessage('Too many connected GEdges for merge!')
                        continue
                    if any(ge in sel_ge for ge in gv.get_gedges_notnone()):
                        showErrorMessage('Cannot merge GVerts that share a GEdge')
                        continue
                    self.create_undo_snapshot('merge')
                    self.polystrips.merge_gverts(self.act_gvert, gv)
                    self.act_gvert = gv
                    return ''
                return ''

            if self.act_gvert.zip_over_gedge:
                gvthis = self.act_gvert
                gvthat = self.act_gvert.get_zip_pair()

                if eventd['press'] == 'CTRL+NUMPAD_PLUS':
                    self.create_undo_snapshot('zip count')
                    max_t = 1 if gvthis.zip_t>gvthat.zip_t else gvthat.zip_t-0.05
                    gvthis.zip_t = min(gvthis.zip_t+0.05, max_t)
                    gvthis.zip_over_gedge.update()
                    dprint('+ %f %f' % (min(gvthis.zip_t, gvthat.zip_t),max(gvthis.zip_t, gvthat.zip_t)), l=4)
                    return ''

                if eventd['press'] == 'CTRL+NUMPAD_MINUS':
                    self.create_undo_snapshot('zip count')
                    min_t = 0 if gvthis.zip_t<gvthat.zip_t else gvthat.zip_t+0.05
                    gvthis.zip_t = max(gvthis.zip_t-0.05, min_t)
                    gvthis.zip_over_gedge.update()
                    dprint('- %f %f' % (min(gvthis.zip_t, gvthat.zip_t),max(gvthis.zip_t, gvthat.zip_t)), l=4)
                    return ''

            if eventd['press'] == 'SHIFT+F':
                self.create_undo_snapshot('simplefill')
                self.fill(eventd)
                return ''
                
        return ''
    
    def pick(self, eventd):
        x,y = eventd['mouse']
        pts = common_utilities.ray_cast_path(eventd['context'], self.obj, [(x,y)])
        if not pts:
            # user did not click on the object
            self.act_gvert,self.act_gedge,self.act_gvert = None,None,None
            self.sel_gedges.clear()
            self.sel_gverts.clear()
            return ''
        pt = pts[0]

        if self.act_gvert or self.act_gedge:
            # check if user is picking an inner control point
            if self.act_gedge and not self.act_gedge.zip_to_gedge:
                lcpts = [self.act_gedge.gvert1,self.act_gedge.gvert2]
            elif self.act_gvert:
                sgv = self.act_gvert
                lge = self.act_gvert.get_gedges()
                lcpts = [ge.get_inner_gvert_at(sgv) for ge in lge if ge and not ge.zip_to_gedge] + [sgv]
            else:
                lcpts = []

            for cpt in lcpts:
                if not cpt.is_picked(pt): continue
                self.act_gedge = None
                self.sel_gedges.clear()
                self.act_gvert = cpt
                self.act_gpatch = None
                return ''
        # Select gvert
        for gv in self.polystrips.gverts:
            if gv.is_unconnected(): continue
            if not gv.is_picked(pt): continue
            self.act_gedge = None
            self.sel_gedges.clear()
            self.sel_gverts.clear()
            self.act_gvert = gv
            self.act_gpatch = None
            return ''

        for ge in self.polystrips.gedges:
            if not ge.is_picked(pt): continue
            self.act_gvert = None
            self.act_gedge = ge
            if not eventd['shift']:
                self.sel_gedges.clear()
            self.sel_gedges.add(ge)
            self.act_gpatch = None
            return ''
        # Select patch
        for gp in self.polystrips.gpatches:
            if not gp.is_picked(pt): continue
            self.act_gvert = None
            self.act_gedge = None
            self.sel_gedges.clear()
            self.sel_gverts.clear()
            self.act_gpatch = gp
            print('norm dot = %f' % gp.normal().dot(gp.ge0.gvert0.snap_norm))
            return ''

        self.act_gedge,self.act_gvert = None,None
        self.act_gedge,self.act_gvert,self.act_gpatch = None,None,None
        self.sel_gedges.clear()
        self.sel_gverts.clear()
    
    def modal_sketching(self, eventd):

        settings = common_utilities.get_settings()

        if eventd['type'] == 'MOUSEMOVE':
            x,y = eventd['mouse']
            if settings.use_pressure:
                p = eventd['pressure']
                r = eventd['mradius']
            else:
                p = 1
                r = self.stroke_radius

            stroke_point = self.sketch[-1]

            (lx, ly) = stroke_point[0]
            lr = stroke_point[1]
            self.sketch_curpos = (x,y)
            self.sketch_pressure = p

            ss0,ss1 = self.stroke_smoothing,1-self.stroke_smoothing
            # Smooth radii
            self.stroke_radius_pressure = lr*ss0 + r*ss1
            if settings.use_pressure:
                self.sketch += [((lx*ss0+x*ss1, ly*ss0+y*ss1), self.stroke_radius_pressure)]
            else:
                self.sketch += [((lx*ss0+x*ss1, ly*ss0+y*ss1), self.stroke_radius)]

            return ''

        if eventd['release'] in {'LEFTMOUSE','SHIFT+LEFTMOUSE', 'CTRL+LEFTMOUSE'}:
            # correct for 0 pressure on release
            if self.sketch[-1][1] == 0:
                self.sketch[-1] = self.sketch[-2]

            # if is selection mouse, check distance
            if 'LEFTMOUSE' in selection_mouse():
                dist_traveled = 0.0
                for s0,s1 in zip(self.sketch[:-1],self.sketch[1:]):
                    dist_traveled += (Vector(s0[0]) - Vector(s1[0])).length

                # user like ly picking, because distance traveled is very small
                if dist_traveled < 5.0:
                    self.pick(eventd)
                    self.sketch = []
                    return 'main'

            p3d = common_utilities.ray_cast_stroke(eventd['context'], self.obj, self.sketch) if len(self.sketch) > 1 else []
            if len(p3d) <= 1: return 'main'

            # tessellate stroke (if needed) so we have good stroke sampling
            # TODO, tesselate pressure/radius values?
            # length_tess = self.length_scale / 700
            # p3d = [(p0+(p1-p0).normalized()*x) for p0,p1 in zip(p3d[:-1],p3d[1:]) for x in frange(0,(p0-p1).length,length_tess)] + [p3d[-1]]
            # stroke = [(p,self.stroke_radius) for i,p in enumerate(p3d)]

            self.sketch = []
            
            while p3d:
                next_i_p = len(p3d)
                for i_p,p in enumerate(p3d):
                    if p[0].x < 0.0:
                        next_i_p = i_p
                        break
                self.polystrips.insert_gedge_from_stroke(p3d[:next_i_p], False)
                p3d = p3d[next_i_p:]
                next_i_p = len(p3d)
                for i_p,p in enumerate(p3d):
                    if p[0].x >= 0.0:
                        next_i_p = i_p
                        break
                p3d = p3d[next_i_p:]
            #stroke = p3d
            #self.polystrips.insert_gedge_from_stroke(stroke, False)
            self.polystrips.remove_unconnected_gverts()
            self.polystrips.update_visibility(eventd['r3d'])

            self.act_gvert = None
            self.act_gedge = None
            self.sel_gedges = set()

            return 'main'

        return ''

    ##############################
    # modal tool functions
    
    def modal_tweak_setup(self, eventd, max_dist=1.0):
        settings = common_utilities.get_settings()
        region = eventd['region']
        r3d = eventd['r3d']
        
        mx = self.obj.matrix_world
        mx3x3 = mx.to_3x3()
        imx = mx.inverted()
        
        ray,hit = common_utilities.ray_cast_region2d(region, r3d, eventd['mouse'], self.obj, settings)
        hit_p3d,hit_norm,hit_idx = hit
        
        hit_p3d = mx * hit_p3d
        
        lgvmove = []
        lgemove = []
        lgpmove = []
        supdate = set()
        
        for gv in self.polystrips.gverts:
            lcorners = gv.get_corners()
            ld = [(c-hit_p3d).length / self.stroke_radius for c in lcorners]
            if not any(d < max_dist for d in ld):
                continue
            gv.freeze()
            lgvmove += [(gv,ic,c,d) for ic,c,d in zip([0,1,2,3], lcorners, ld) if d < max_dist]
            supdate.add(gv)
            for ge in gv.get_gedges_notnone():
                supdate.add(ge)
                for gp in ge.gpatches:
                    supdate.add(gp)
        
        for ge in self.polystrips.gedges:
            for i,gv in ge.iter_igverts():
                p0 = gv.position+gv.tangent_y*gv.radius
                p1 = gv.position-gv.tangent_y*gv.radius
                d0 = (p0-hit_p3d).length / self.stroke_radius
                d1 = (p1-hit_p3d).length / self.stroke_radius
                if d0 >= max_dist and d1 >= max_dist: continue
                ge.freeze()
                lgemove += [(gv,i,p0,d0,p1,d1)]
                supdate.add(ge)
                supdate.add(ge.gvert0)
                supdate.add(ge.gvert3)
                for gp in ge.gpatches:
                    supdate.add(gp)
        
        for gp in self.polystrips.gpatches:
            freeze = False
            for i_pt,pt in enumerate(gp.pts):
                p,_,_ = pt
                d = (p-hit_p3d).length / self.stroke_radius
                if d >= max_dist: continue
                freeze = True
                lgpmove += [(gp,i_pt,p,d)]
            if not freeze: continue
            gp.freeze()
            supdate.add(gp)
            
        
        self.tweak_data = {
            'mouse': eventd['mouse'],
            'lgvmove': lgvmove,
            'lgemove': lgemove,
            'lgpmove': lgpmove,
            'supdate': supdate,
            'mx': mx,
            'mx3x3': mx3x3,
            'imx': imx,
        }
        
    
    def modal_tweak_move_tool(self, eventd):
        if eventd['release'] == 'T':
            return 'main'
        
        settings = common_utilities.get_settings()
        region = eventd['region']
        r3d = eventd['r3d']
        
        if eventd['press'] == 'LEFTMOUSE':
            self.modal_tweak_setup(eventd)
            return ''
        
        if (eventd['type'] == 'MOUSEMOVE' and self.tweak_data) or eventd['release'] == 'LEFTMOUSE':
            cx,cy = eventd['mouse']
            lx,ly = self.tweak_data['mouse']
            dx,dy = cx-lx,cy-ly
            dv = Vector((dx,dy))
            
            mx = self.tweak_data['mx']
            mx3x3 = self.tweak_data['mx3x3']
            imx = self.tweak_data['imx']
            
            def update(p3d, d):
                if d >= 1.0: return p3d
                p2d = location_3d_to_region_2d(region, r3d, p3d)
                p2d += dv * (1.0-d)
                hit = common_utilities.ray_cast_region2d(region, r3d, p2d, self.obj, settings)[1]
                if hit[2] == -1: return p3d
                return mx * hit[0]
                
                return pts[0]
            
            for gv,ic,c,d in self.tweak_data['lgvmove']:
                if ic == 0:
                    gv.corner0 = update(c,d)
                elif ic == 1:
                    gv.corner1 = update(c,d)
                elif ic == 2:
                    gv.corner2 = update(c,d)
                elif ic == 3:
                    gv.corner3 = update(c,d)
            
            for gv,ic,c0,d0,c1,d1 in self.tweak_data['lgemove']:
                nc0 = update(c0,d0)
                nc1 = update(c1,d1)
                gv.position = (nc0+nc1)/2.0
                gv.tangent_y = (nc0-nc1).normalized()
                gv.radius = (nc0-nc1).length / 2.0
            
            for gp,i_pt,c,d in self.tweak_data['lgpmove']:
                p,v,k = gp.pts[i_pt]
                nc = update(c,d)
                gp.pts[i_pt] = (nc,v,k)
            
            if eventd['release'] == 'LEFTMOUSE':
                for u in self.tweak_data['supdate']:
                   u.update()
                for u in self.tweak_data['supdate']:
                   u.update_visibility(eventd['r3d'])
                self.tweak_data = None
        
        return ''
    
    def modal_tweak_relax_tool(self, eventd):
        if eventd['release'] == 'SHIFT+T':
            return 'main'
        
        settings = common_utilities.get_settings()
        region = eventd['region']
        r3d = eventd['r3d']
        
        if eventd['press'] == 'LEFTMOUSE':
            modal_tweak_setup(self, eventd, max_dist=2.0)
            return ''
        
        if (eventd['type'] == 'MOUSEMOVE' and self.tweak_data) or eventd['release'] == 'LEFTMOUSE':
            cx,cy = eventd['mouse']
            
            mx = self.tweak_data['mx']
            mx3x3 = self.tweak_data['mx3x3']
            imx = self.tweak_data['imx']
            
            def update(p3d, d):
                if d >= 1.0: return p3d
                p2d = location_3d_to_region_2d(region, r3d, p3d)
                p2d += dv * (1.0-d)
                hit = common_utilities.ray_cast_region2d(region, r3d, p2d, self.obj, settings)[1]
                if hit[2] == -1: return p3d
                return mx * hit[0]
                
                return pts[0]
            
            for gv,ic,c,d in self.tweak_data['lgvmove']:
                if ic == 0:
                    gv.corner0 = update(c,d)
                elif ic == 1:
                    gv.corner1 = update(c,d)
                elif ic == 2:
                    gv.corner2 = update(c,d)
                elif ic == 3:
                    gv.corner3 = update(c,d)
            
            for gv,ic,c0,d0,c1,d1 in self.tweak_data['lgemove']:
                nc0 = update(c0,d0)
                nc1 = update(c1,d1)
                gv.position = (nc0+nc1)/2.0
                gv.tangent_y = (nc0-nc1).normalized()
                gv.radius = (nc0-nc1).length / 2.0
            
            for gp,i0,i1,c,d in self.tweak_data['lgpmove']:
                nc = update(c,d)
                gp.pts = [(_0,_1,_p) if _0!=i0 or _1!=i1 else (_0,_1,nc) for _0,_1,_p in gp.pts]
                gp.map_pts[(i0,i1)] = nc
                
            
            if eventd['release'] == 'LEFTMOUSE':
                for u in self.tweak_data['supdate']:
                   u.update()
                for u in self.tweak_data['supdate']:
                   u.update_visibility(eventd['r3d'])
                self.tweak_data = None
        
        return ''
    
    def modal_scale_tool(self, eventd):
        cx,cy = self.action_center
        mx,my = eventd['mouse']
        ar = self.action_radius
        pr = self.mode_radius
        cr = math.sqrt((mx-cx)**2 + (my-cy)**2)

        if eventd['press'] in {'RET','NUMPAD_ENTER','LEFTMOUSE'}:
            self.tool_fn('commit', eventd)
            return 'main'

        if eventd['press'] in {'ESC', 'RIGHTMOUSE'}:
            self.tool_fn('undo', eventd)
            return 'main'

        if eventd['type'] == 'MOUSEMOVE':
            self.tool_fn(cr / pr, eventd)
            self.mode_radius = cr
            return ''

        return ''

    def modal_grab_tool(self, eventd):
        cx,cy = self.action_center
        mx,my = eventd['mouse']
        px,py = self.prev_pos #mode_pos
        sx,sy = self.mode_start

        if eventd['press'] in {'RET','NUMPAD_ENTER','LEFTMOUSE','SHIFT+RET','SHIFT+NUMPAD_ENTER','SHIFT+LEFTMOUSE'}:
            self.tool_fn('commit', eventd)
            return 'main'

        if eventd['press'] in {'ESC','RIGHTMOUSE'}:
            self.tool_fn('undo', eventd)
            return 'main'

        if eventd['type'] == 'MOUSEMOVE':
            self.tool_fn((mx-px,my-py), eventd)
            self.prev_pos = (mx,my)
            return ''

        return ''

    def modal_rotate_tool(self, eventd):
        cx,cy = self.action_center
        mx,my = eventd['mouse']
        px,py = self.prev_pos #mode_pos

        if eventd['press'] in {'RET', 'NUMPAD_ENTER', 'LEFTMOUSE'}:
            self.tool_fn('commit', eventd)
            return 'main'

        if eventd['press'] in {'ESC', 'RIGHTMOUSE'}:
            self.tool_fn('undo', eventd)
            return 'main'

        if eventd['type'] == 'MOUSEMOVE':
            vp = Vector((px-cx,py-cy,0))
            vm = Vector((mx-cx,my-cy,0))
            ang = vp.angle(vm) * (-1 if vp.cross(vm).z<0 else 1)
            self.tool_rot += ang
            self.tool_fn(self.tool_rot, eventd)
            self.prev_pos = (mx,my)
            return ''

        return ''

    def modal_scale_brush_pixel_tool(self, eventd):
        '''
        This is the pixel brush radius
        self.tool_fn is expected to be self.
        '''
        mx,my = eventd['mouse']

        if eventd['press'] in {'RET','NUMPAD_ENTER','LEFTMOUSE'}:
            self.tool_fn('commit', eventd)
            return 'main'

        if eventd['press'] in {'ESC', 'RIGHTMOUSE'}:
            self.tool_fn('undo', eventd)

            return 'main'

        if eventd['type'] == 'MOUSEMOVE':
            '''
            '''
            self.tool_fn((mx,my), eventd)

            return ''

        return ''

    ###########################
    # main modal function (FSM)

    def modal(self, context, event):
        if not context.area: return {'RUNNING_MODAL'}
        
        context.area.tag_redraw()
        settings = common_utilities.get_settings()

        eventd = self.get_event_details(context, event)

        if self.footer_last != self.footer:
            context.area.header_text_set('PolyStrips: %s' % self.footer)
            self.footer_last = self.footer

        FSM = {}
        FSM['main'] = self.modal_main
        FSM['nav'] = self.modal_nav
        FSM['sketch'] = self.modal_sketching
        FSM['scale tool'] = self.modal_scale_tool
        FSM['grab tool'] = self.modal_grab_tool
        FSM['rotate tool'] = self.modal_rotate_tool
        FSM['brush scale tool'] = self.modal_scale_brush_pixel_tool
        FSM['tweak move tool'] = self.modal_tweak_move_tool
        FSM['tweak relax tool'] = self.modal_tweak_relax_tool

        self.cur_pos = eventd['mouse']
        nmode = FSM[self.mode](eventd)
        self.mode_pos = eventd['mouse']

        self.is_navigating = (nmode == 'nav')
        if nmode == 'nav': return {'PASS_THROUGH'}

        if nmode in {'finish','cancel'}:
            self.kill_timer(context)
            polystrips_undo_cache = []
            
            bpy.ops.screen.screen_full_area(use_hide_panels=True)
            self.fullscreened = False
            
            return {'FINISHED'} if nmode == 'finish' else {'CANCELLED'}

        if nmode: self.mode = nmode
        
        if not self.fullscreened:
            bpy.ops.screen.screen_full_area(use_hide_panels=True)
            self.fullscreened = True

        return {'RUNNING_MODAL'}

    ###########################################################
    # functions to convert beziers and gpencils to polystrips

    def create_polystrips_from_bezier(self, ob_bezier):
        data  = ob_bezier.data
        mx    = ob_bezier.matrix_world

        def create_gvert(self, mx, co, radius):
            p0  = mx * co
            r0  = radius
            n0  = Vector((0,0,1))
            tx0 = Vector((1,0,0))
            ty0 = Vector((0,1,0))
            return GVert(self.obj,self.dest_obj, p0,r0,n0,tx0,ty0)

        for spline in data.splines:
            pregv = None
            for bp0,bp1 in zip(spline.bezier_points[:-1],spline.bezier_points[1:]):
                gv0 = pregv if pregv else self.create_gvert(mx, bp0.co, 0.2)
                gv1 = self.create_gvert(mx, bp0.handle_right, 0.2)
                gv2 = self.create_gvert(mx, bp1.handle_left, 0.2)
                gv3 = self.create_gvert(mx, bp1.co, 0.2)

                ge0 = GEdge(self.obj, self.dest_obj, gv0, gv1, gv2, gv3)
                ge0.recalc_igverts_approx()
                ge0.snap_igverts_to_object()

                if pregv:
                    self.polystrips.gverts += [gv1,gv2,gv3]
                else:
                    self.polystrips.gverts += [gv0,gv1,gv2,gv3]
                self.polystrips.gedges += [ge0]
                pregv = gv3

    def create_polystrips_from_greasepencil(self):
        Mx = self.obj.matrix_world
        gp = self.obj.grease_pencil
        gp_layers = gp.layers
        # for gpl in gp_layers: gpl.hide = True
        strokes = [[(p.co,p.pressure) for p in stroke.points] for layer in gp_layers for frame in layer.frames for stroke in frame.strokes]
        self.strokes_original = strokes

        #for stroke in strokes:
        #    self.polystrips.insert_gedge_from_stroke(stroke)


    ##########################
    # General functions

    def kill_timer(self, context):
        if not self._timer: return
        context.window_manager.event_timer_remove(self._timer)
        self._timer = None

    def get_event_details(self, context, event):
        '''
        Construct an event dict that is *slightly* more convenient than
        stringing together a bunch of logical conditions
        '''

        event_ctrl = 'CTRL+'  if event.ctrl  else ''
        event_shift = 'SHIFT+' if event.shift else ''
        event_alt = 'ALT+'   if event.alt   else ''
        event_oskey = 'OSKEY+' if event.oskey else ''
        event_ftype = event_ctrl + event_shift + event_alt + event_oskey + event.type

        event_pressure = 1 if not hasattr(event, 'pressure') else event.pressure

        def pressure_to_radius(r, p, map = 0):
            if   map == 0:  p = max(0.25,p)
            elif map == 1:  p = 0.25 + .75 * p
            elif map == 2:  p = max(0.05,p)
            elif map == 3:  p = .7 * (2.25*p-1)/((2.25*p-1)**2 +1)**.5 + .55
            return r*p

        return {
            'context': context,
            'region': context.region,
            'r3d': context.space_data.region_3d,

            'ctrl': event.ctrl,
            'shift': event.shift,
            'alt': event.alt,
            'value': event.value,
            'type': event.type,
            'ftype': event_ftype,
            'press': event_ftype if event.value=='PRESS'   else None,
            'release': event_ftype if event.value=='RELEASE' else None,

            'mouse': (float(event.mouse_region_x), float(event.mouse_region_y)),
            'pressure': event_pressure,
            'mradius': pressure_to_radius(self.stroke_radius, event_pressure),
            }
