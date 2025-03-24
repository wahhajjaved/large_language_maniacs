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
import bgl


######################################################################################################################################### Grid Fill
def collapse_short_edges(bm,obj,threshold=1.0):
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

def get_average_edge_length(bm,obj):
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
    return edges_len_average, shortest_edge

def clean_boundary_edges(bm,obj):
    edges_len_average, shortest_edge = get_average_edge_length(bm,obj)
    edges = []
    
    for edge in bm.edges:
        if edge.calc_length() < edges_len_average*.12 and not edge.tag:
            edges.append(edge)
    bmesh.ops.collapse(bm,edges=edges,uvs=False)        
    bmesh.update_edit_mesh(obj.data)        

def average_edge_cuts(bm,obj,cuts=1):
    ### collapse short edges
    edges_len_average, shortest_edge = get_average_edge_length(bm,obj)
    
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

def remove_doubles(obj,edge_average_len,edge_min_len):
    bm = bmesh.from_edit_mesh(obj.data)
    verts = []
    for vert in bm.verts:
        if not vert.hide:
            verts.append(vert)
    bmesh.ops.remove_doubles(bm,verts=verts,dist=0.0001)
    bmesh.update_edit_mesh(obj.data)     
        

class ReprojectSpriteTexture(bpy.types.Operator):
    bl_idname = "coa_tools.reproject_sprite_texture"
    bl_label = "Reproject Sprite Texture"
    bl_description = ""
    bl_options = {"REGISTER"}
    
    def reproject(self,context):
        ### unwrap
        obj = context.active_object
        hide_base_sprite = obj.data.coa_hide_base_sprite
        obj.data.coa_hide_base_sprite = False
        bm = bmesh.from_edit_mesh(obj.data)
        selected_edges = []
        for edge in bm.edges:
            if edge.select:
                selected_edges.append(edge)
                
        unselected_verts = []
        for vert in bm.verts:
            if not vert.select:
                unselected_verts.append(vert)
                vert.select = True
        unselected_faces = []
        for face in bm.faces:
            if not face.select:
                unselected_faces.append(face)
                face.select = True        
        bpy.ops.uv.project_from_view(camera_bounds=False, correct_aspect=True, scale_to_bounds=True)        
        
        for edge in selected_edges:
            edge.select = True
        for vert in unselected_verts:
            vert.select = False
        for face in unselected_faces:
            face.select = False
        bmesh.update_edit_mesh(obj.data)    
        obj.data.coa_hide_base_sprite = hide_base_sprite
    
    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        self.reproject(context)
        return {"FINISHED"}
        

class Fill(bpy.types.Operator):
    bl_idname = "object.coa_fill"
    bl_label = "Triangle Fill"
    bl_description = ""
    bl_options = {"REGISTER"}
    
    detail = FloatProperty(name="Detail",default=.3,min=0,max=1.0)
    triangulate = BoolProperty(default=False)
    
    def __init__(self):
        self.tiles_x = 1
        self.tiles_y = 1
        self.sprite_frame = 0

    
    def get_img(self,context,obj):
        bpy.ops.object.mode_set(mode="OBJECT")
        img = obj.data.uv_textures.active.data[0].image    
        bpy.ops.object.mode_set(mode="EDIT")
        return img
        
        
    def selection_closed(self,context,bm):
        for vert in bm.verts:
            if vert.select and len(vert.link_edges) == 1:
                return False
        return True    
            
        
    def triangulate_fill(self,context):
        start_obj = context.active_object
        
        bm = bmesh.from_edit_mesh(start_obj.data)
        selected = False
        select_count = 0
        for vert in bm.verts:
            if vert.select:
                select_count += 1
                selected = True
        
        if select_count in [1]:
            self.report({'WARNING'},"Select a full loop to fill.")
            return{'CANCELLED'}    
        
        if not selected:
            self.report({'WARNING'},"No vertex selected.")
            return{'CANCELLED'}
        
        if not self.selection_closed(context,bm):
            self.report({'WARNING'},"Selection needs to be a loop. Close the loop first.")
            return{'CANCELLED'}    
            
        
        bpy.ops.mesh.separate(type="SELECTED")
        bpy.ops.object.mode_set(mode="OBJECT")
        context.scene.objects.active = context.selected_objects[0]
        obj = context.selected_objects[0]
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action='SELECT')
        
        ### get edge lenght
        bm = bmesh.from_edit_mesh(context.active_object.data)
        edges_len_average, shortest_edge = get_average_edge_length(bm,context.active_object)

        ### grid fill start
        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.index_update()
        
            
        fill_ok = triangle_fill(bm,obj)
        
        if fill_ok:
            ### remove short edges
            clean_boundary_edges(bm,obj)
            
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
        #bpy.ops.mesh.remove_doubles(use_unselected=True)
        remove_doubles(context.active_object,edges_len_average, shortest_edge)
        
        
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
        
        for vert in bm.verts:
            if vert not in filled_contour:
                vert.select = False     
        for face in not_selected_faces:
            face.select = False
        bmesh.update_edit_mesh(start_obj.data)
        
        ### unwrap
        obj = context.active_object
        self.reset_spritesheet(context,start_obj)
        bm = bmesh.from_edit_mesh(obj.data)
        unselected_verts = []
        for vert in bm.verts:
            if not vert.select:
                unselected_verts.append(vert)
                vert.select = True
        unselected_faces = []
        for face in bm.faces:
            if not face.select:
                unselected_faces.append(face)
                face.select = True        
        bpy.ops.uv.project_from_view(camera_bounds=False, correct_aspect=True, scale_to_bounds=True)        
        
        for vert in unselected_verts:
            vert.select = False
        for face in unselected_faces:
            face.select = False
            
        self.revert_rest_spritesheet(context,start_obj)
        
        return fill_ok
    
    def reset_spritesheet(self,context,obj):
        selected_verts = []
        bpy.ops.object.mode_set(mode="OBJECT")
        
        handle_uv_items(context,obj)
        
        self.tiles_x = obj.coa_tiles_x
        self.tiles_y = obj.coa_tiles_y
        self.sprite_frame = obj.coa_sprite_frame
        obj.coa_sprite_frame = 0
        obj.coa_tiles_x = 1
        obj.coa_tiles_y = 1
        
        bpy.ops.object.mode_set(mode="EDIT")
    
    def revert_rest_spritesheet(self,context,obj):
        bpy.ops.object.mode_set(mode="OBJECT")
        set_uv_default_coords(context,obj)
        obj.coa_tiles_x = self.tiles_x
        obj.coa_tiles_y = self.tiles_y
        obj.coa_sprite_frame = self.sprite_frame
        bpy.ops.object.mode_set(mode="EDIT")
        
    def normal_fill(self,context):
        obj = context.active_object
        
        bpy.ops.mesh.edge_face_add()
        bpy.ops.uv.project_from_view(camera_bounds=False, correct_aspect=True, scale_to_bounds=True)
        
        self.reset_spritesheet(context,obj)
        
        
        bm = bmesh.from_edit_mesh(obj.data)
        unselected_faces = []
        for face in bm.faces:
            if face.select == False:
                unselected_faces.append(face)
            face.select = True    
            
            
        bpy.ops.uv.project_from_view(camera_bounds=False, correct_aspect=True, scale_to_bounds=True)
        
        
        for face in unselected_faces:
            face.select = False
            
        bmesh.update_edit_mesh(obj.data)
        
        self.revert_rest_spritesheet(context,obj)
    
    def execute(self,context):
        start_obj = context.active_object
        img = self.get_img(context,start_obj)
        
        hide_sprite = start_obj.data.coa_hide_base_sprite
        start_obj.data.coa_hide_base_sprite = False
        
        if self.triangulate:
            if not self.triangulate_fill(context):
                bpy.ops.object.mode_set(mode="OBJECT")
                context.scene.objects.active = start_obj
                bpy.ops.object.join()
                bpy.ops.object.mode_set(mode="EDIT")
                self.report({"WARNING"},"Please select a closed vertex loop.")
        else:
            self.normal_fill(context)
        
        ### assign texture to uv map
        if img != None:
            bpy.ops.object.mode_set(mode="OBJECT")
            assign_tex_to_uv(img,start_obj.data.uv_textures.active)
            bpy.ops.object.mode_set(mode="EDIT")
        
        start_obj.data.coa_hide_base_sprite = hide_sprite
        
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
    
    mode = StringProperty(default="EDIT_MESH")
    
    def __init__(self):
        self.type = ""
        self.value = ""
        self.distance = .1
        self.cur_distance = 0
        self.draw_dir = Vector((0,0,0))
        self.old_coord = Vector((0,0,0))
        self.mouse_press = False
        self.mouse_press_hist = False
        self.mouse_pos = Vector((0,0,0))
        self.inside_area = False
        self.show_manipulator = False
        self.cursor_pos_hist = Vector((1000000000,0,1000000))
        self.sprite_object = None
        self.in_view_3d = False
        self.nearest_vertex_co = Vector((0,0,0))
        self.contour_length = 0
        
        self.selected_vert_coord = None
        self.visible_verts = []
        self.visible_edges = []
        self.selected_verts_count = 0
        self.cut_edge = False
        
        self.bone = None
        self.armature = None
        self.bone_shape = None
        self.draw_bounds = False
        self.draw_type = ""
        self.draw_handler_removed = False
        self.bounds = []
        self.type_prev = ""
        self.value_prev = ""
        self.prev_coa_view = ""
    
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
    
    def limit_cursor_by_bounds(self,context,location):
        obj = context.active_object
        bounds = self.bounds#get_bounds_and_center(obj)[1]
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
            
    
    def draw_verts(self,context,obj,position,use_snap=False):
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
        
        snap_position, point_type = self.snap_vert_location(position)
        if point_type == "VERT" and use_snap:
            snap_vert = None
            
            for vert in bm.verts:
                if obj.matrix_world * vert.co == snap_position:
                    snap_vert = vert
                    break
            if len(bm.select_history) > 0 and bm.select_history[0] != snap_vert:
                try:   
                    bm.edges.new([bm.select_history[0],snap_vert])
                except:
                    print("Edge is irgnored. It exists already")    
                
            if len(selected_vert) == 0:
                if snap_vert != None:
                    snap_vert.select = True
                    bm.select_history.add(snap_vert)
                    
            if self.contour_length == 0:
                self.contour_length = 1
                if snap_vert != None:
                    self.selected_vert_coord = obj.matrix_world * snap_vert.co
            else:
                self.selected_vert_coord = None    
                
        elif point_type == "EDGE" and use_snap:
            for edge in bm.edges:
                sub_edge = None
                edge_center = obj.matrix_world * ((edge.verts[0].co + edge.verts[1].co) * .5)
                if (edge_center - snap_position).magnitude < 0.001:
                    sub_edge = edge
                    break
            if sub_edge != None:
                bmesh.ops.subdivide_edges(bm,edges=[sub_edge],cuts=1)
            bmesh.update_edit_mesh(context.active_object.data)    
            new_vert = None
            for vert in bm.verts:
                vert.select = False
#                if obj.matrix_world * vert.co == edge_center:
#                    new_vert = vert
#                    new_vert.select = True
#                    bm.select_history = [new_vert]
            
            ### triangulate faces
            self.cut_edge = True
            bmesh.ops.triangulate(bm,faces=vert.link_faces)
        else:
            new_vert = bm.verts.new(obj.matrix_world.inverted() * position)
            new_vert.select = True
            bm.select_history.add(new_vert)
            self.selected_vert_coord = position
            if len(selected_vert) > 0 and self.contour_length > 0:
                bm.edges.new([selected_vert[0],new_vert])
            self.contour_length += 1
        for vert in selected_vert:
            try:
                vert.select = False
            except:
                pass    
        bmesh.update_edit_mesh(obj.data)
    
    def set_bone_shape_color_and_wireframe(self,context,obj):
        if self.bone.bone_group != None:
            bone_group_name = self.bone.bone_group.name
            bone_group_color = self.bone.bone_group.colors.normal
            suffix = "_group_color"
            if (bone_group_name+suffix) not in bpy.data.materials:
                material = bpy.data.materials.new(bone_group_name+suffix)
            else:
                material = bpy.data.materials[bone_group_name+suffix]
            
            material.diffuse_color = bone_group_color
            material.use_shadeless = True
            
            if len(obj.material_slots) == 0:
                obj.data.materials.append(material)
            else:
                obj.material_slots[0].material = material
        else:
            if len(obj.material_slots) > 0:
                obj.material_slots[0].material = None
                      
        bm = bmesh.from_edit_mesh(obj.data)
        if len(bm.faces) > 0:
            self.armature.data.bones[self.bone.name].show_wire = False
        else:
            self.armature.data.bones[self.bone.name].show_wire = True
        bm.free()    
    
    def check_verts(self,context,event):
        verts = []
        bm = bmesh.from_edit_mesh(context.active_object.data)
        for vert in bm.verts:
            if vert.select:
                verts.append(vert)
        for vert in verts:
            vert.co = context.active_object.matrix_world.inverted() * self.limit_cursor_by_bounds(context,context.active_object.matrix_world * vert.co)
        bmesh.update_edit_mesh(context.active_object.data)
    
    
    def get_selected_vert_pos(self,context):
        bm = bmesh.from_edit_mesh(context.active_object.data)
        for vert in bm.verts:
            if vert.select == True:
                bmesh.update_edit_mesh(context.active_object.data)
                return vert.co
        bmesh.update_edit_mesh(context.active_object.data)
        return None
        
    def exit(self,context,event):
        context.screen.coa_view = self.prev_coa_view
        bpy.ops.object.mode_set(mode="EDIT")
        if self.mode == "DRAW_BONE_SHAPE":
            self.set_bone_shape_color_and_wireframe(context,self.bone_shape)
            
        bpy.context.space_data.show_manipulator = self.show_manipulator
        bpy.context.window.cursor_set("CROSSHAIR")
        bpy.ops.object.mode_set(mode="OBJECT")
        self.sprite_object.coa_edit_mesh = False
        set_local_view(False)
        
            
        if self.mode == "DRAW_BONE_SHAPE":
            self.armature.draw_type = self.draw_type
            context.scene.coa_lock_to_bounds = self.draw_bounds
            if self.armature != None:
                context.scene.objects.active = self.armature
            if len(self.bone_shape.data.vertices) > 1:
                self.bone.custom_shape = self.bone_shape
                self.bone.use_custom_shape_bone_size = False
            else:
                self.bone.custom_shape = None    
            
            self.bone_shape.select = False
            self.bone_shape.parent = None
            context.scene.objects.unlink(self.bone_shape)
            bpy.ops.object.mode_set(mode="POSE")    
        else:
            bpy.ops.object.mode_set(mode="OBJECT")    
        return{'CANCELLED'}
        
    def check_selected_verts(self,context):
        bm = bmesh.from_edit_mesh(context.active_object.data)
        return bm.select_history
    
    def get_visible_verts(self,context):
        obj = context.active_object
        bm = bmesh.from_edit_mesh(context.active_object.data)
        self.visible_verts = []
        self.visible_edges = []
        self.selected_verts_count = 0
        
        active_vert = None
        if len(bm.select_history)>0 and type(bm.select_history[0]) == bmesh.types.BMVert:
            active_vert = bm.select_history[0]
        
        for edge in bm.edges:
            if not edge.hide:# and (edge.is_wire or edge.is_boundary):
                self.visible_edges.append([obj.matrix_world * edge.verts[0].co,obj.matrix_world * edge.verts[1].co])
        
        for vert in bm.verts:
            if vert.select:
                self.selected_verts_count += 1
            if not vert.hide and (vert.is_boundary or vert.is_wire or len(vert.link_edges)==0):# and len(vert.link_edges) <= 1:
                if self.contour_length == 0 or vert != active_vert and self.contour_length > 0:
                    self.visible_verts.append(obj.matrix_world * vert.co)
    
    def snap_vert_location(self,coord):
        obj = bpy.context.active_object
        scene = bpy.context.scene
        distance = scene.coa_snap_distance * bpy.context.space_data.region_3d.view_distance
        snap_coord = coord
        point_type = None
        
        points = []
        if self.contour_length == 0:
            for edge_coords in self.visible_edges:
                edge_center = (edge_coords[0] + edge_coords[1]) * .5
                points.append([edge_center,"EDGE"])
        for vert in self.visible_verts:
            points.append([vert,"VERT"])
        
        #for vert in self.visible_verts:
        for vert,type in points:
            if (vert - coord).magnitude < distance:
                distance = (vert - coord).magnitude
                snap_coord = vert
                point_type = type    
        return [snap_coord,point_type]
    
    def modal(self, context, event):
        obj = context.active_object
        self.type = str(event.type)
        self.value = str(event.value)
        self.in_view_3d = check_region(context,event)
        if event.value == "RELEASE" and context.active_object.mode == "EDIT" and context.scene.coa_lock_to_bounds:
            self.check_verts(context,event)
        
        if self.in_view_3d and context.active_object != None:
            
            if (context.active_object.mode != "EDIT" and not self.draw_handler_removed) or self.sprite_object.coa_edit_mesh == False:
                self.draw_handler_removed = True
                self.sprite_object.coa_edit_mesh = False
                bpy.types.SpaceView3D.draw_handler_remove(self.draw_handler, "WINDOW")
                bpy.context.space_data.show_manipulator = self.show_manipulator
                bpy.context.window.cursor_set("CROSSHAIR")
                bpy.ops.object.mode_set(mode="OBJECT")
                self.sprite_object.coa_edit_mesh = False
                set_local_view(False)
                
                self.exit(context,event)
                return {"FINISHED"}
                
            scene = context.scene
            ob = context.active_object
            
                
            ### get visible boundary and wire vertices
            self.get_visible_verts(context)
            
            ### set mouse press history
            self.mouse_press_hist = self.mouse_press
            
            ### Cast Ray from mousePosition and set Cursor to hitPoint
            rayStart,rayEnd, ray = self.project_cursor(event)
            if rayEnd != None:
                bpy.context.scene.cursor_location = rayEnd
                self.mouse_pos = rayEnd
            if scene.coa_lock_to_bounds and self.mode == "EDIT_MESH":
                bpy.context.scene.cursor_location = self.limit_cursor_by_bounds(context,bpy.context.scene.cursor_location)    
                
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
                
                snap_vert, point_type = self.snap_vert_location(rayEnd)
                if point_type == "EDGE":
                    bpy.context.window.cursor_set("KNIFE")
                else:
                    bpy.context.window.cursor_set("PAINT_BRUSH")
              
            
            ### Set Mouse click
            mouse_button = None
            if context.user_preferences.inputs.select_mouse == "RIGHT":
                mouse_button = 'LEFTMOUSE'
            else:
                mouse_button = 'RIGHTMOUSE'  
            
            if (event.value == 'PRESS' or event.value == 'CLICK') and event.type == mouse_button and self.mouse_press == False:
                self.mouse_press = True
                
                ### add vert on first mouse press
                self.cursor_pos_hist = Vector(context.scene.cursor_location)
                self.draw_verts(context,ob,self.cursor_pos_hist,use_snap=True)
                
                return{'RUNNING_MODAL'}
            if (event.value == 'RELEASE' and event.type == 'MOUSEMOVE'):
                self.mouse_press = False
                self.cut_edge = False
            
            
            self.cur_distance = (context.scene.cursor_location - self.cursor_pos_hist).magnitude
            self.draw_dir = (context.scene.cursor_location - self.cursor_pos_hist).normalized()
            
            ### add verts while mouse is pressed and moved
            mult = 1.0
            if not self.cut_edge:
                if self.mouse_press and self.inside_area:
                    if self.cur_distance > context.scene.coa_distance*mult:
                        if scene.coa_distance_constraint:
                            mult = bpy.context.space_data.region_3d.view_distance*.05
                        i = int(self.cur_distance / (context.scene.coa_distance*mult))
                        
                        for j in range(i):
                            new_vertex_pos = (self.cursor_pos_hist + (self.draw_dir*context.scene.coa_distance*mult))
                            self.draw_verts(context,ob,new_vertex_pos,use_snap=False)

                            self.cursor_pos_hist = Vector(new_vertex_pos)
                else:
                    self.old_coord = Vector((100000,100000,100000))

            ### check selected verts
            select_history = self.check_selected_verts(context)
            if len(select_history) == 0 or self.selected_verts_count != 1:
                self.selected_vert_coord = None
                self.contour_length = 0
            elif len(select_history) > 0 and type(select_history[0]) == bmesh.types.BMVert:
                self.selected_vert_coord = obj.matrix_world* select_history[0].co
                if self.contour_length == 0:
                    self.contour_length = 1
                
            
            scene.tool_settings.double_threshold = scene.coa_snap_distance
            
            #context.area.tag_redraw()
            
            ### deselect verts
            if event.type in ["ESC"] and self.selected_verts_count > 0:
                bm = bmesh.from_edit_mesh(context.active_object.data)
                bm.select_history = []
                for vert in bm.verts:
                    vert.select = False
                for edge in bm.edges:
                    edge.select = False        
                for face in bm.faces:
                    face.select = False    
            
            if (event.type in {'TAB'} and not event.ctrl):# or (event.type in {'ESC'} and self.inside_area and self.selected_verts_count == 0):
                self.sprite_object.coa_edit_mesh = False
                bpy.ops.object.mode_set(mode='OBJECT')
            
            if self.mouse_press_hist and not self.mouse_press:
                bpy.ops.ed.undo_push(message="Stroke")
                bpy.ops.object.mode_set(mode="OBJECT")
                bpy.ops.object.mode_set(mode="EDIT")
            
        self.type_prev = str(event.type)
        self.value_prev = str(event.value)    
        return {'PASS_THROUGH'}
    
    _timer = 0
    
    def execute(self, context):
        obj = context.active_object
        #bpy.ops.wm.coa_modal() ### start coa modal mode if not running
        self.sprite_object = get_sprite_object(context.active_object)
        if self.sprite_object != None:
            self.sprite_object = bpy.data.objects[self.sprite_object.name]
        
        ### get Sprite Boundaries
        if obj.type == "MESH":
            hide_sprite = obj.data.coa_hide_base_sprite
            obj.data.coa_hide_base_sprite = False
            self.bounds = get_bounds_and_center(obj)[1]
            obj.data.coa_hide_base_sprite = hide_sprite
        
        if self.mode == "EDIT_MESH":
            hide_base_sprite(bpy.context.active_object)
        
        if self.mode == "DRAW_BONE_SHAPE":
            self.draw_bounds = context.scene.coa_lock_to_bounds
            context.scene.coa_lock_to_bounds = False
            
            bone = bpy.context.active_pose_bone
            bone.use_custom_shape_bone_size = False
            armature = bpy.context.active_object
            bone_mat = armature.matrix_world * bone.matrix
            bone_loc, bone_rot, bone_scale = bone_mat.decompose()
            
            if bone.custom_shape != None and bone.custom_shape.name in bpy.data.objects:
                shape_name = bone.custom_shape.name
            else:    
                shape_name = bone.name+"_custom_shape"
                
            if shape_name in bpy.data.meshes:
                me = bpy.data.meshes[shape_name]
            else:    
                me = bpy.data.meshes.new(shape_name)
            me.show_double_sided = True
            if shape_name in bpy.data.objects:
                bone_shape = bpy.data.objects[shape_name]
            else:    
                bone_shape = bpy.data.objects.new(shape_name,me)
            context.scene.objects.link(bone_shape)
            context.scene.objects.active = bone_shape
            bone_shape.select = True
            bone_shape.parent = self.sprite_object
            
            bone_shape.name = bone.name+"_custom_shape"
            me.name = bone.name+"_custom_shape"
            
            bone_shape.name = bone.name+"_custom_shape"
            bone_shape.matrix_local = bone_mat
            bone_shape.show_x_ray = True
            self.bone_shape = bone_shape
            self.bone = bone
            self.armature = armature
            bone.custom_shape = None#self.bone_shape
            self.draw_type = self.armature.draw_type
            self.armature.draw_type = "WIRE"    


        
        self.show_manipulator = bpy.context.space_data.show_manipulator
        bpy.context.space_data.show_manipulator = False
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type='VERT')

        if self.sprite_object != None:
            self.sprite_object.coa_edit_mesh = True
        
        wm = context.window_manager
        
        if self.mode == "EDIT_MESH":
            set_local_view(True)
        self.prev_coa_view = str(context.screen.coa_view)
        context.screen.coa_view = "2D"
        
        args = ()
        self.draw_handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_callback_px, args, "WINDOW", "POST_VIEW")
                
        bpy.ops.view3d.viewnumpad(type="FRONT")        
        #self._timer = wm.event_timer_add(0.1, context.window)
        wm.modal_handler_add(self)        
        #context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        bpy.context.space_data.show_manipulator = self.show_manipulator
        bpy.context.window_manager.sketch_assets_enabled = False
        return {'CANCELLED'}
    
    def draw_callback_px(self):
        obj = bpy.context.active_object
        
        y_offset = Vector((0,-0.1,0))
        
        vertex_vec_new = self.mouse_pos
        
        if len(self.bounds) > 3:
            vec1 = Vector(self.bounds[0]) + y_offset
            vec2 = Vector(self.bounds[1]) + y_offset
            vec3 = Vector(self.bounds[3]) + y_offset
            vec4 = Vector(self.bounds[2]) + y_offset
            
            color = [1,.7,.5]
            bgl.glEnable(bgl.GL_BLEND)
            bgl.glColor4f(color[0], color[1], color[2], 1.0)
            bgl.glLineWidth(1)
            
            bgl.glEnable(bgl.GL_LINE_SMOOTH)
            
            bgl.glBegin(bgl.GL_LINE_STRIP)
            bgl.glVertex3f(vec1[0],vec1[1],vec1[2])
            bgl.glVertex3f(vec2[0],vec2[1],vec2[2])
            bgl.glVertex3f(vec3[0],vec3[1],vec3[2])
            bgl.glVertex3f(vec4[0],vec4[1],vec4[2])
            bgl.glVertex3f(vec1[0],vec1[1],vec1[2])
            bgl.glEnd()
        
        
        ### draw lines and dots
        if self.type not in ["K","C","B","R","G","S"] and self.in_view_3d:
            vertex_vec_new = self.limit_cursor_by_bounds(bpy.context,self.mouse_pos)
            point_type = None
            snapped_vert_coord, point_type = self.snap_vert_location(vertex_vec_new)
            if self.value != "PRESS":
                vertex_vec_new =  snapped_vert_coord + y_offset
            
            if self.selected_vert_coord != None:
                bgl.glEnable(bgl.GL_LINE_SMOOTH)
                vertex_vec = self.selected_vert_coord + y_offset
                    
                color = [1,0,0]
                bgl.glColor4f(color[0], color[1], color[2], 1.0)
                bgl.glBegin(bgl.GL_LINE_STRIP)
                bgl.glVertex3f(vertex_vec[0],vertex_vec[1],vertex_vec[2])
                bgl.glVertex3f(vertex_vec_new[0],vertex_vec_new[1],vertex_vec_new[2])
                bgl.glEnd()
            
            if point_type == "VERT":
                color = [0,1,0]
            elif point_type == "EDGE":
                color = [0,0,1]
            else:
                color = [1,1,0]
            bgl.glColor4f(color[0], color[1], color[2], 1.0)
            bgl.glPointSize(8)
            bgl.glBegin(bgl.GL_POINTS)
            bgl.glVertex3f(vertex_vec_new[0],vertex_vec_new[1],vertex_vec_new[2])
            bgl.glEnd()
            
                    
        # restore opengl defaults
        bgl.glLineWidth(1)
        bgl.glDisable(bgl.GL_BLEND)
        bgl.glDisable(bgl.GL_LINE_SMOOTH)
        bgl.glColor4f(0.0, 0.0, 0.0, 1.0) 


class PickEdgeLength(bpy.types.Operator):
    bl_idname = "coa_tools.pick_edge_length"
    bl_label = "Pick Edge Length"
    bl_description = ""
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        scene = context.scene
        obj = context.active_object
        bm = bmesh.from_edit_mesh(obj.data)
        
        mult = 1
        if context.scene.coa_distance_constraint:
            mult = bpy.context.space_data.region_3d.view_distance*.05
        
        for edge in bm.edges:
            if edge.select:
                scene.coa_distance = edge.calc_length()/mult
#        for vert in bm.verts:
#            vert.select = False
#        for edge in bm.edges:
#            edge.select = False    
#        for face in bm.faces:
#            face.select = False            
        bmesh.update_edit_mesh(obj.data)    
        return {"FINISHED"}
        