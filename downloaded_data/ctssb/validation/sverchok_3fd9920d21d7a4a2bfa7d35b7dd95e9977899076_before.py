import bpy, bmesh, mathutils
from mathutils import Vector, Matrix
from node_s import *
import Viewer_draw
from Viewer_draw import *
from util import *

class SvObjBake(bpy.types.Operator):
    """ B A K E   OBJECTS """
    bl_idname = "node.sverchok_mesh_baker"
    bl_label = "Sverchok mesh baker"
    bl_options = {'REGISTER', 'UNDO'}
    
    idname = bpy.props.StringProperty(name='idname', default='', description='name of parent node')
    idtree = bpy.props.StringProperty(name='idtree', default='', description='name of parent tree')
    
    def execute(self, context):
        global cache_viewer_baker
        if cache_viewer_baker[self.idname+self.idtree+'m'] and not cache_viewer_baker[self.idname+self.idtree+'v']:
            return {'CANCELLED'}
        vers = dataCorrect(cache_viewer_baker[self.idname+self.idtree+'v'])
        edg_pol = dataCorrect(cache_viewer_baker[self.idname+self.idtree+'ep'])
        if cache_viewer_baker[self.idname+self.idtree+'m']:
            matrixes = dataCorrect(cache_viewer_baker[self.idname+self.idtree+'m'])
        else:
            matrixes = []
            for i in range((len(vers))):
                matrixes.append(Matrix())
        self.makeobjects(vers, edg_pol, matrixes)
        cache_viewer_baker = {}
        return {'FINISHED'}
    
    def makeobjects(self, vers, edg_pol, mats):
        # inception
        # fht = предохранитель от перебора рёбер и полигонов.
        fht = []
        if len(edg_pol[0][0]) == 2:
            pols = []
            for edgs in edg_pol:
                maxi = max(max(a) for a in edgs)
                fht.append(maxi)
                #print (maxi)
        elif len(edg_pol[0][0]) > 2:
            edgs = []
            for pols in edg_pol:
                maxi = max(max(a) for a in pols)
                fht.append(maxi)
                #print (maxi)
        #print (fht)
        vertices = Vector_generate(vers)
        matrixes = Matrix_generate(mats)
        #print('mats' + str(matrixes))
        objects = {}
        fhtagn = []
        for u, f in enumerate(fht):
            fhtagn.append(min(len(vertices[u]), fht[u]))
        #lenmesh = len(vertices) - 1
        #print ('запекание вершин ', vertices, " матрицы запекашка ", matrixes, " полиглоты ", edg_pol)
        #print (matrixes)
        for i, m in enumerate(matrixes):
            k = i
            lenver = len(vertices) - 1
            if i > lenver:
                v = vertices[-1]
                k = lenver
            else:
                v = vertices[k]
            #print (fhtagn, len(v)-1)
            if (len(v)-1) < fhtagn[k]:
                continue
            # возможно такая сложность не нужна, но пусть лежит тут. Удалять лишние точки не обязательно.
            elif fhtagn[k] < (len(v)-1):
                nonneed = (len(v)-1) - fhtagn[k]
                for q in range(nonneed):
                    v.pop((fhtagn[k]+1))
                #print (fhtagn[k], (len(v)-1))

            e = edg_pol[k] if edgs else []
            p = edg_pol[k] if pols else []
            
            objects[str(i)] = self.makemesh(i,v,e,p,m)
        for ite in objects.values():
            me = ite[1]
            ob = ite[0]
            calcedg = True
            if edgs: calcedg = False
            me.update(calc_edges=calcedg)
            bpy.context.scene.objects.link(ob)
            
    def makemesh(self,i,v,e,p,m):
        name = 'Sv_' + str(i)
        me = bpy.data.meshes.new(name)
        me.from_pydata(v, e, p)
        ob = bpy.data.objects.new(name, me)
        ob.matrix_world = m
        ob.show_name = False
        ob.hide_select = False
        #print ([ob,me])
        #print (ob.name + ' baked')
        return [ob,me]


class ViewerNode(Node, SverchCustomTreeNode):
    ''' ViewerNode '''
    bl_idname = 'ViewerNode'
    bl_label = 'Viewer Draw'
    bl_icon = 'OUTLINER_OB_EMPTY'
    
    Vertex_show = bpy.props.BoolProperty(name='Vertices', description='Show or not vertices', default=True,update=updateNode)
    activate = bpy.props.BoolProperty(name='Show', description='Activate node?', default=True,update=updateNode)
    transparant = bpy.props.BoolProperty(name='Transparant', description='transparant polygons?', default=False,update=updateNode)
    shading = bpy.props.BoolProperty(name='Shading', description='shade the object or index representation?', default=False,update=updateNode)
    coloris = SvColors
    coloris.color[1]['default'] = (0.055,0.312,0.5)
    color_view = coloris.color
        
    def init(self, context):
        self.inputs.new('VerticesSocket', 'vertices', 'vertices')
        self.inputs.new('StringsSocket', 'edg_pol', 'edg_pol')
        self.inputs.new('MatrixSocket', 'matrix', 'matrix')
    
    def draw_buttons(self, context, layout):
        row = layout.row(align=True)
        row.prop(self, "Vertex_show", text="Verts")
        row.prop(self, "activate", text="Show")
        row = layout.row()
        row.scale_y=4.0
        opera = row.operator('node.sverchok_mesh_baker', text='B A K E')
        opera.idname = self.name
        opera.idtree = self.id_data.name
        row = layout.row(align=True)
        row.scale_x=10.0
        row.prop(self, "transparant", text="Transp")
        row.prop(self, "shading", text="Shade")
        row = layout.row(align=True)
        row.scale_x=10.0
        row.prop(self, "color_view", text="Color")
        #a = self.color_view[2]
        #layout.label(text=str(round(a, 4)))
        
    def update(self):
        global cache_viewer_baker
        cache_viewer_baker[self.name+self.id_data.name+'v'] = []
        cache_viewer_baker[self.name+self.id_data.name+'ep'] = []
        cache_viewer_baker[self.name+self.id_data.name+'m'] = []
        if not self.id_data.sv_show:
            callback_disable(self.name+self.id_data.name)
            return
            
        if self.activate and (self.inputs['vertices'].links or self.inputs['matrix'].links):
            callback_disable(self.name+self.id_data.name)
            
            if 'vertices' in self.inputs and self.inputs['vertices'].links and \
                type(self.inputs['vertices'].links[0].from_socket) == VerticesSocket:
                
                propv = SvGetSocketAnyType(self, self.inputs['vertices'])
                cache_viewer_baker[self.name+self.id_data.name+'v'] = dataCorrect(propv)
            else:
                cache_viewer_baker[self.name+self.id_data.name+'v'] = []
                            
            if 'edg_pol' in self.inputs and self.inputs['edg_pol'].links and \
                type(self.inputs['edg_pol'].links[0].from_socket) == StringsSocket:
                prope = SvGetSocketAnyType(self, self.inputs['edg_pol'])
                cache_viewer_baker[self.name+self.id_data.name+'ep'] = dataCorrect(prope)
                #print (prope)
            else:
                cache_viewer_baker[self.name+self.id_data.name+'ep'] = []
                    
            if 'matrix' in self.inputs and self.inputs['matrix'].links and \
                type(self.inputs['matrix'].links[0].from_socket) == MatrixSocket:
                propm = SvGetSocketAnyType(self, self.inputs['matrix'])
                cache_viewer_baker[self.name+self.id_data.name+'m'] = dataCorrect(propm)
            else:
                cache_viewer_baker[self.name+self.id_data.name+'m'] = []
        
        else:
            callback_disable(self.name-self.id_data.name)
        
        if cache_viewer_baker[self.name+self.id_data.name+'v'] or cache_viewer_baker[self.name+self.id_data.name+'m']:
            callback_enable(self.name+self.id_data.name, cache_viewer_baker[self.name+self.id_data.name+'v'], cache_viewer_baker[self.name+self.id_data.name+'ep'], \
                cache_viewer_baker[self.name+self.id_data.name+'m'], self.Vertex_show, self.color_view, self.transparant, self.shading)
            
            self.use_custom_color=True
            self.color = (1,0.3,0)
        else:
            self.use_custom_color=True
            self.color = (0.1,0.05,0)
            #print ('отражения вершин ',len(cache_viewer_baker['v']), " рёбёры ", len(cache_viewer_baker['ep']), "матрицы",len(cache_viewer_baker['m']))
        if not self.inputs['vertices'].links and not self.inputs['matrix'].links:
            callback_disable(self.name+self.id_data.name)
            cache_viewer_baker = {}
    
    def update_socket(self, context):
        self.update()
    
    def free(self):
        global cache_viewer_baker
        callback_disable(self.name+self.id_data.name)
        #cache_viewer_baker[self.name+self.id_data.name+'v'] = []
        #cache_viewer_baker[self.name+self.id_data.name+'ep'] = []
        #cache_viewer_baker[self.name+self.id_data.name+'m'] = []            

def register():
    bpy.utils.register_class(ViewerNode)
    bpy.utils.register_class(SvObjBake)
    
def unregister():
    bpy.utils.unregister_class(SvObjBake)
    bpy.utils.unregister_class(ViewerNode)
    

if __name__ == "__main__":
    register()
