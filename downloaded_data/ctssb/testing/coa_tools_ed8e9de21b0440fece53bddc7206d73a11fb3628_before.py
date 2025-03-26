'''
Copyright (C) 2015 Andreas Esau
andreasesau@gmail.com

Created by Andreas Esau

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
    "name": "Cutout Animation Tools",
    "description": "This Addon provides a Toolset for a 2D Animation Workflow.",
    "author": "Andreas Esau",
    "version": (0, 1, 0, "Alpha"),
    "blender": (2, 75, 0),
    "location": "View 3D > Tools > Cutout Animation Tools",
    "warning": "This addon is still in development.",
    "wiki_url": "",
    "category": "Ndee Tools" }
    
import bpy
import bpy_extras
import bpy_extras.view3d_utils
from math import radians
import mathutils
from mathutils import Vector, Matrix, Quaternion
import math
import bmesh
from bpy.props import FloatProperty, IntProperty, BoolProperty, StringProperty, CollectionProperty, FloatVectorProperty, EnumProperty, IntVectorProperty
import os
from bpy_extras.io_utils import ExportHelper, ImportHelper
import json
from bpy.app.handlers import persistent
from .. functions import *


######################################################################################################################################### Grid Fill
def collapse_short_edges(bm,obj,threshold=1):
    ### collapse short edges
    edges_len_average = 0
    edges_count = 0
    shortest_edge = 10000
    for edge in bm.edges:
        if True:
            edges_count += 1
            length = edge.calc_length()
            edges_len_average += length
            if length < shortest_edge:
                shortest_edge = length
    edges_len_average = edges_len_average/edges_count

    verts = []
    for vert in bm.verts:
        if not vert.is_boundary:
            verts.append(vert)
    bmesh.update_edit_mesh(obj.data)
    
    bmesh.ops.remove_doubles(bm,verts=verts,dist=edges_len_average*threshold)

    bmesh.update_edit_mesh(obj.data)

def average_edge_cuts(bm,obj,cuts=1):
    ### collapse short edges
    edges_len_average = 0
    edges_count = 0
    shortest_edge = 10000
    for edge in bm.edges:
        if True:#edge.is_boundary:
            edges_count += 1
            length = edge.calc_length()
            edges_len_average += length
            if length < shortest_edge:
                shortest_edge = length
    edges_len_average = edges_len_average/edges_count

    subdivide_edges = []
    for edge in bm.edges:
        cut_count = int(edge.calc_length()/shortest_edge)*cuts
        if cut_count < 0:
            cut_count = 0
        if not edge.is_boundary:
            subdivide_edges.append([edge,cut_count])
    for edge in subdivide_edges:
        bmesh.ops.subdivide_edges(bm,edges=[edge[0]],cuts=edge[1])
        bmesh.update_edit_mesh(obj.data)
                
def triangle_fill(bm,obj):
    edges = []
    for edge in bm.edges:
        if edge.select == True:
            edges.append(edge)
    triangle_fill = bmesh.ops.triangle_fill(bm,edges=edges,use_beauty=True)
    bmesh.update_edit_mesh(obj.data)
    if triangle_fill["geom"] == []:
        return False
    else:
        return True

def triangulate(bm,obj):
    bmesh.ops.triangulate(bm,faces=bm.faces) 
    bmesh.update_edit_mesh(obj.data)
    
def smooth_verts(bm,obj):
    ### smooth verts
    smooth_verts = []
    for vert in bm.verts:
        if not vert.is_boundary:
            smooth_verts.append(vert)
    for i in range(50):
        #bmesh.ops.smooth_vert(bm,verts=smooth_verts,factor=1.0,use_axis_x=True,use_axis_y=True,use_axis_z=True)    
        bmesh.ops.smooth_vert(bm,verts=smooth_verts,factor=1.0,use_axis_x=True,use_axis_y=True,use_axis_z=True)    
    bmesh.update_edit_mesh(obj.data)
    
def clean_verts(bm,obj):
    ### find corrupted faces
    faces = []     
    for face in bm.faces:
        i = 0
        for edge in face.edges:
            if not edge.is_manifold:
                i += 1
            if i == len(face.edges):
                faces.append(face)           
    bmesh.ops.delete(bm,geom=faces,context=5)

    edges = []
    for face in bm.faces:
        i = 0
        for vert in face.verts:
            if not vert.is_manifold and not vert.is_boundary:
                i+=1
            if i == len(face.verts):
                for edge in face.edges:
                    if edge not in edges:
                        edges.append(edge)
    bmesh.ops.collapse(bm,edges=edges)
    
    bmesh.update_edit_mesh(obj.data)
    for vert in bm.verts:
        if not vert.is_boundary:
            vert.select = False
            
    verts = []
    for vert in bm.verts:
        if len(vert.link_edges) in [3,4] and not vert.is_boundary:
            verts.append(vert)
    bmesh.ops.dissolve_verts(bm,verts=verts)
    bmesh.update_edit_mesh(obj.data)
            
class Fill(bpy.types.Operator):
    bl_idname = "object.coa_fill"
    bl_label = "Triangle Fill"
    
    detail = FloatProperty(name="Detail",default=.3,min=0,max=1.0)
    triangulate = BoolProperty(default=False)
    

    
    def get_img(self,context,obj):
        bpy.ops.object.mode_set(mode="OBJECT")
        img = obj.data.uv_textures.active.data[0].image    
        bpy.ops.object.mode_set(mode="EDIT")
        return img
        
    def triangulate_fill(self,context):
        start_obj = context.active_object
        bm = bmesh.from_edit_mesh(start_obj.data)
        selected = False
        for vert in bm.verts:
            if vert.select:
                selected = True
        if not selected:
            self.report({'WARNING'},"No vertex selected.")
            return{'CANCELLED'}
        
        bpy.ops.mesh.separate(type="SELECTED")
        bpy.ops.object.mode_set(mode="OBJECT")
        context.scene.objects.active = context.selected_objects[0]
        obj = context.selected_objects[0]
        bpy.ops.object.mode_set(mode="EDIT")
        
        bpy.ops.mesh.select_all(action='SELECT')

        ### grid fill start
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.index_update()
            
        fill_ok = triangle_fill(bm,obj)
        if fill_ok:
            average_edge_cuts(bm,obj)
            triangulate(bm,obj)
            smooth_verts(bm,obj)
            collapse_short_edges(bm,obj)
            smooth_verts(bm,obj)
            clean_verts(bm,obj)
            smooth_verts(bm,obj)
            triangulate(bm,obj)
            smooth_verts(bm,obj)
            
            bm.verts.index_update()
            bmesh.update_edit_mesh(obj.data) 
            bmesh.ops.recalc_face_normals(bm,faces=bm.faces)
            bmesh.update_edit_mesh(obj.data)
                
            for vert in bm.verts:
                vert.select = True
        bmesh.update_edit_mesh(obj.data)
        if not fill_ok:
            return fill_ok 
        
        
        ### grid fill end
        
        bpy.ops.object.mode_set(mode="OBJECT")
        context.scene.objects.active = start_obj
        bpy.ops.object.join()
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.remove_doubles(use_unselected=True)
        
        
        ### create uv map
        bm = bmesh.from_edit_mesh(start_obj.data)
        filled_contour = []
        for vert in bm.verts:
            if vert.select:
                filled_contour.append(vert)
            vert.select = True
        
        not_selected_faces = []
        for face in bm.faces:
            if face.select == False:
                not_selected_faces.append(face)
            face.select = True
        bmesh.update_edit_mesh(start_obj.data)
        
        bpy.ops.uv.project_from_view(camera_bounds=False, correct_aspect=True, scale_to_bounds=True)
        for vert in bm.verts:
            if vert not in filled_contour:
                vert.select = False     
        for face in not_selected_faces:
            face.select = False
        bmesh.update_edit_mesh(start_obj.data)
        return fill_ok
    
    def normal_fill(self,context):
        obj = context.active_object
        
        bpy.ops.mesh.edge_face_add()
        bm = bmesh.from_edit_mesh(obj.data)
        unselected_faces = []
        for face in bm.faces:
            if face.select == False:
                unselected_faces.append(face)
            face.select = True    
            
        bmesh.update_edit_mesh(obj.data)
        
        bpy.ops.uv.project_from_view(camera_bounds=False, correct_aspect=True, scale_to_bounds=True)
        
        for face in unselected_faces:
            face.select = False
        bmesh.update_edit_mesh(obj.data)    
        
    
    def execute(self,context):
        start_obj = context.active_object
        img = self.get_img(context,start_obj)
        
        if self.triangulate:
            if not self.triangulate_fill(context):
                self.report({"WARNING"},"Please select a closed vertex loop.")
        else:
            self.normal_fill(context)
        
        ### assign texture to uv map
        if img != None:
            bpy.ops.object.mode_set(mode="OBJECT")
            assign_tex_to_uv(self,img,start_obj.data.uv_textures.active)
            bpy.ops.object.mode_set(mode="EDIT")
        
        bpy.ops.ed.undo_push(message="Grid Fill")
        return{'FINISHED'}

######################################################################################################################################### Draw Contours
''' scene.ray_cast return values for Blender 2.77
Return (hit, hit_location,hit_normal,?,hit_object,matrix)
'''

''' scene.ray_cast return values for Blender 2.76
Return (hit, hit_object,matrix,hit_location,hit_normal)

result = bpy.context.scene.ray_cast(start,end)
result = [result[0],result[4],result[5],result[1],result[2]]
'''

class DrawContour(bpy.types.Operator):
    bl_idname = "object.coa_edit_mesh" 
    bl_label = "Edit Mesh"
    
    def __init__(self):
        self.distance = .1
        self.cur_distance = 0
        self.old_coord = Vector((0,0,0))
        self.mouse_press = False
        self.mouse_press_hist = False
        self.inside_area = False
        self.show_manipulator = False
        self.cursor_pos_hist = Vector((1000000000,0,1000000))
        self.sprite_object = None
    
    def project_cursor(self, event):
        coord = mathutils.Vector((event.mouse_region_x, event.mouse_region_y))
        transform = bpy_extras.view3d_utils.region_2d_to_location_3d
        region = bpy.context.region
        rv3d = bpy.context.space_data.region_3d
        #### cursor used for the depth location of the mouse
        #depth_location = bpy.context.scene.cursor_location
        depth_location = bpy.context.active_object.location
        ### creating 3d vector from the cursor
        end = transform(region, rv3d, coord, depth_location)
        #end = transform(region, rv3d, coord, bpy.context.space_data.region_3d.view_location)
        ### Viewport origin
        start = bpy_extras.view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        
        ### Cast ray from view to mouselocation
        if b_version_bigger_than((2,76,0)):
            ray = bpy.context.scene.ray_cast(start, (start+(end-start)*2000)-start )
        else:    
            ray = bpy.context.scene.ray_cast(start, start+(end-start)*2000)
        
        ### ray_cast return values have changed after blender 2.67.0 
        if b_version_bigger_than((2,76,0)):
            ray = [ray[0],ray[4],ray[5],ray[1],ray[2]]
        
        return start, end, ray

    def automerge(self):
        ob = bpy.context.active_object
        me = ob.data
        scene = bpy.context.scene
        
        merge_distance = scene.coa_snap_distance * bpy.context.space_data.region_3d.view_distance
        bm = bmesh.from_edit_mesh(me)
        
        verts_added = []
        for vert in bm.verts:
            if vert.select:
                verts_added.append(vert)
        
        for vert in verts_added:
            tmp_distance = 100000000
            vert_to_merge = None
            for vert2 in bm.verts:
                if vert2 not in verts_added:
                    vec = Vector((vert2.co - vert.co))
                    if vec.magnitude < tmp_distance:
                        tmp_distance = vec.magnitude
                        vert_to_merge = vert2
            
            if vert_to_merge != None:           
                vec = Vector((vert_to_merge.co - vert.co))
                if vec.magnitude > merge_distance:
                    vert_to_merge = None
                
            if vert_to_merge != None:
                vert.co = vert_to_merge.co
                verts_to_merge = []
                verts_to_merge.append(vert)
                verts_to_merge.append(vert_to_merge)
    
                bmesh.ops.pointmerge(bm,verts=verts_to_merge,merge_co=Vector((vert.co)))
                bmesh.update_edit_mesh(me)

    def set_paint_distance(self,context,ray):
        ob = context.active_object
        scene = context.scene
        
        bpy.ops.object.mode_set(mode='OBJECT')
        if len(ob.data.vertices)==0:
            bpy.ops.object.mode_set(mode='EDIT')
            return 0.0
        
        vert_loc = ob.data.vertices[len(ob.data.vertices)-1].co
        distance = (ray - vert_loc - ob.location).magnitude
        bpy.ops.object.mode_set(mode='EDIT')
        return distance
    
    def limit_cursor_by_bounds(self,context,event,location):
        obj = context.active_object
        bounds = get_bounds_and_center(obj)[1]
        if location[0] < bounds[0][0]:
            location[0] = bounds[0][0]
        if location[0] > bounds[3][0]:
            location[0] = bounds[3][0]
        if location[2] < bounds[0][2]:
            location[2] = bounds[0][2]
        if location[2] > bounds[1][2]:
            location[2] = bounds[1][2]
        location[1] = bounds[0][1]

        return location 
        
    def draw_verts(self,context,obj):
        bm = bmesh.from_edit_mesh(obj.data)
        
        selected_verts_count = 0
        for vert in bm.verts:
            if vert.select:
                selected_verts_count += 1
        if selected_verts_count > 1:
            for vert in bm.verts:
                if vert.select:
                    vert.select = False
            for face in bm.faces:
                if face.select:
                    face.select = False  
            for edge in bm.edges:
                if edge.select:
                    edge.select = False        
        bmesh.update_edit_mesh(obj.data)
        
        selected_vert = []
        for vert in bm.verts:
            if vert.select:
                selected_vert.append(vert)
        new_vert = bm.verts.new(obj.matrix_world.inverted() * context.scene.cursor_location)
        new_vert.select = True
        if len(selected_vert) > 0:
            bm.edges.new([selected_vert[0],new_vert])
        for vert in selected_vert:
            vert.select = False
        
        bmesh.update_edit_mesh(obj.data)
    
    def modal(self, context, event):
        scene = context.scene
        ob = context.active_object
        
        self.mouse_press_hist = self.mouse_press
        
        ### check if mouse is in 3d View
        coord = mathutils.Vector((event.mouse_region_x, event.mouse_region_y))
        if coord[0] < 0 or coord[0] > bpy.context.area.width:
            self.inside_area = False
            bpy.context.window.cursor_set("DEFAULT")
        elif coord[1] < 0 or coord[1] > bpy.context.area.height:
            self.inside_area = False
            bpy.context.window.cursor_set("DEFAULT")
        else:
            self.inside_area = True
            bpy.context.window.cursor_set("PAINT_BRUSH")
            
        ### Cast Ray from mousePosition and set Cursor to hitPoint
        rayStart,rayEnd, ray = self.project_cursor(event)
        if rayEnd != None:
            bpy.context.scene.cursor_location = rayEnd
        if scene.coa_lock_to_bounds:
            bpy.context.scene.cursor_location = self.limit_cursor_by_bounds(context,event,bpy.context.scene.cursor_location)    
        
        ### Set Mouse click
        if (event.value == 'PRESS' or event.value == 'CLICK') and event.type == 'LEFTMOUSE':
            self.mouse_press = True
            #return{'RUNNING_MODAL'}
        if (event.value == 'RELEASE' and event.type == 'MOUSEMOVE'):
            self.mouse_press = False
            
               
        #self.cur_distance = (rayEnd - self.old_coord).magnitude
        self.cur_distance = (context.scene.cursor_location - self.cursor_pos_hist).magnitude
        if self.mouse_press and self.inside_area:
            mult = 1.0
            if scene.coa_distance_constraint:
                mult = bpy.context.space_data.region_3d.view_distance*.05
            if self.cur_distance > context.scene.coa_distance*mult:
                #bpy.ops.mesh.dupli_extrude_cursor('INVOKE_DEFAULT')
                self.draw_verts(context,ob)
                #self.old_coord = rayEnd
                self.cursor_pos_hist = Vector(bpy.context.scene.cursor_location)
                if event.alt or scene.coa_automerge:
                    self.automerge()
        else:
            self.old_coord = Vector((100000,100000,100000))
            self.cursor_pos_hist = Vector((100000,100000,100000))
        
        scene.tool_settings.double_threshold = scene.coa_snap_distance
        
        if (event.type in {'ESC'} and self.inside_area) or self.sprite_object.coa_edit_mesh == False:
            bpy.context.space_data.show_manipulator = self.show_manipulator
            bpy.context.window.cursor_set("CROSSHAIR")
            bpy.ops.object.mode_set(mode="OBJECT")
            self.sprite_object.coa_edit_mesh = False
            set_local_view(False)
            return{'CANCELLED'}
        
        if event.type in {'TAB'} and not event.ctrl:
            self.sprite_object.coa_edit_mesh = False
            bpy.ops.object.mode_set(mode='OBJECT')
            #return{'CANCELLED'}
        
        if self.mouse_press_hist and not self.mouse_press:
            bpy.ops.ed.undo_push(message="Stroke")
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.object.mode_set(mode="EDIT")
        
        return {'PASS_THROUGH'}
    
    def execute(self, context):
        #bpy.ops.wm.coa_modal() ### start coa modal mode if not running
    
        self.sprite_object = get_sprite_object(context.active_object)
        self.show_manipulator = bpy.context.space_data.show_manipulator
        bpy.context.space_data.show_manipulator = False
        bpy.ops.object.mode_set(mode="EDIT")
        self.sprite_object.coa_edit_mesh = True
        
        set_local_view(True)
        
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        bpy.context.space_data.show_manipulator = self.show_manipulator
        bpy.context.window_manager.sketch_assets_enabled = False
        return {'CANCELLED'}
