import avango
import avango.gua

import field_containers
import application


import json
import math

# json Loader Class
class jsonloader:

  def __init__(self):
    self.json_data = None
    self.root_node = None
    self.TriMeshLoader = avango.gua.nodes.TriMeshLoader()

  def create_application_from_json(self, json_path):
    print("creating application from", json_path)
    
    self.open_json(json_path)

    self.file_path = json_path.rpartition('/')[0] + '/'

    self.app = application.Application()

    # self.app.window = self.load_window()    

    self.create_scenegraph_nodes()
    self.create_field_containers()

    self.app.basic_setup()
    self.app.apply_field_connections()

    return self.app 

  def open_json(self, path):
    json_file = open(path)
    self.json_data = json.load(json_file)

  def create_scenegraph_nodes(self):
    self.nodes = {}
    child_parent_pairs = []

    new_camera, new_screen, parent_name = self.load_camera()
    self.nodes[new_camera.Name.value] = new_camera
    child_parent_pairs.append( [new_camera.Name.value, parent_name] )
    self.app.set_camera( new_camera )
    self.app.screen = new_screen
    
    self.load_materials()

    for mesh in self.json_data["meshes"]:
      new_mesh, parent_name = self.load_mesh(mesh)
      self.nodes[new_mesh.Name.value] = new_mesh
      child_parent_pairs.append( [new_mesh.Name.value, parent_name] )

    for transform in self.json_data["transforms"]:
      new_transform, parent_name = self.load_transform(transform)
      self.nodes[new_transform.Name.value] = new_transform
      child_parent_pairs.append( [new_transform.Name.value, parent_name] )

    for light in self.json_data["lights"]:
      new_light, parent_name = self.load_light(light)
      self.nodes[new_light.Name.value] = new_light
      child_parent_pairs.append( [new_light.Name.value, parent_name] )

    self.create_scenegraph_structure(child_parent_pairs)


  def create_field_containers(self):
    # TODO do something not useless
    for ts in self.json_data["time_sensors"]:
      self.create_time_sensor(ts)

    for rm in self.json_data["rotation_matrices"]:
      self.create_rotation_matrix(rm)

    for tm in self.json_data["translation_matrices"]:
      self.create_translation_matrix(tm)

    for fcfo in self.json_data["from_objects"]:
      self.create_field_container_from_object(fcfo)

    for vec3 in self.json_data["vec3s"]:
      self.create_vec3(vec3)

    for script in self.json_data["scripts"]:
      field_containers.script.create_new_script(self.json_data["scripts"][script], self.app, self.file_path)

    for fm in self.json_data["floatmaths"]:
      self.create_float_math(fm)


  def create_time_sensor(self, time_sensor):
    json_time_sensor = self.json_data["time_sensors"][time_sensor]

    name = json_time_sensor["name"]

    new_time_sensor = avango.nodes.TimeSensor(Name = name)

    self.app.add_field_container(new_time_sensor)

    for fieldconnection in json_time_sensor["field_connections"]:
      self.app.plan_field_connection(name, fieldconnection["from_field"], fieldconnection["to_node"], fieldconnection["to_field"])
      

  def create_rotation_matrix(self, rotation_matrix):
    new_field_container = field_containers.rotation_matrix.RotationMatrix()
    new_field_container.constructor(self.json_data["rotation_matrices"][rotation_matrix], self.app)

  def create_translation_matrix(self, translation_matrix):
    new_field_container = field_containers.translation_matrix.TranslationMatrix()
    new_field_container.constructor(self.json_data["translation_matrices"][translation_matrix], self.app)

  def create_field_container_from_object(self, field_containers_from_objects):
    json_fcfo = self.json_data["from_objects"][field_containers_from_objects]

    ref_name = json_fcfo["referenced_name"]
    ref_name = ref_name.replace('.', '_')

    obj = self.nodes[ref_name]
    self.app.add_field_container(obj)

  def create_vec3(self, vec3):
    new_field_container = field_containers.vec3.Vec3()
    new_field_container.constructor(self.json_data["vec3s"][vec3], self.app)

  def create_float_math(self, fm):
    new_field_container = field_containers.float_math.FloatMath()
    new_field_container.constructor(self.json_data["floatmaths"][fm], self.app)


  def create_scenegraph_structure(self, child_parent_pairs):
    for pair in child_parent_pairs:
      if pair[1] == "null":
        self.app.root.Children.value.append(self.nodes[pair[0]])
      else:
        self.nodes[pair[1]].Children.value.append(self.nodes[pair[0]])


  def load_window(self):
    print("load window")   

    json_window = self.json_data["windows"]["Window"]

    title = str(json_window["title"] )
    name = str(json_window["name"])
    size = avango.gua.Vec2ui(json_window["left_resolution"][0], 
                             json_window["left_resolution"][1] )

    mode = 0
    if (json_window["mode"] == "MONO"):
      mode = 0
    # TODO more stereo modes

    display = str(json_window["display"])

    new_window = avango.gua.nodes.GlfwWindow(Name = name, Size = size, LeftResolution = size,
                  StereoMode = mode, Title = title, Display = display)
    
    avango.gua.register_window(name, new_window)

    return new_window 

  def load_materials(self):
    json_materials = self.json_data["materials"]
      
    self.materials = {}

    self.materials["default_material"] = avango.gua.nodes.Material()

    for mat in json_materials:
      new_mat = avango.gua.nodes.Material()
      color = avango.gua.Vec4(json_materials[mat]['color'][0], json_materials[mat]['color'][1], json_materials[mat]['color'][2], 1.0)
      new_mat.set_uniform('Color', color)
      new_mat.set_uniform('Roughness', json_materials[mat]['roughness'])
      new_mat.set_uniform('Metalness', json_materials[mat]['metalness'])
      new_mat.set_uniform('Emissivity', json_materials[mat]['emissivity'])
      self.materials[mat] = new_mat

  def load_mesh(self, mesh):
    print("load mesh" , mesh) 

    json_mesh = self.json_data["meshes"][mesh]

    name = str(json_mesh["name"])
    name = name.replace('.','_')

    parent_name = str(json_mesh["parent"])
    parent_name = parent_name.replace('.','_')

    transform = load_transform_matrix( json_mesh["transform"] )
    material = self.materials[json_mesh["material"]]

    path = self.file_path + str(json_mesh["file"])

    geometry = self.TriMeshLoader.create_geometry_from_file( name
                                 , path
                                 , material
                                 , 0)

    geometry.Transform.value = transform

    return geometry, parent_name

  def load_camera(self):
    print("load camera")        

    json_camera = self.json_data["camera"]

    name = str(json_camera["name"])
    parent_name = str(json_camera["parent"])

    transform = load_transform_matrix( json_camera["transform"] )

    # scenegraph = str(json_camera["scenegraph"])

    # resolution = avango.gua.Vec2ui(json_camera["resolution"][0], json_camera["resolution"][1] )

    # output_window = str(json_camera["output_window_name"])

    # calculate a screen
    fov = json_camera["field_of_view"]
    width = math.tan(fov/2.0) * 2.0
    height = width * 9.0 / 16.0
    screen = avango.gua.nodes.ScreenNode(Name = "generated_screen", Width = width, Height = height)
    screen.Transform.value = avango.gua.make_trans_mat(0.0, 0.0, -1.0)

    cam = avango.gua.nodes.CameraNode(Name = name,
                                      # LeftScreenPath = "",
                                      SceneGraph = "SceneGraph",
                                      Resolution = avango.gua.Vec2ui(1600, 900),
                                      OutputWindowName = "window",
                                      Transform = transform)
    
    cam.Children.value.append(screen)

    return cam, screen, parent_name 


  def load_transform(self, transform):       
    print("load transform" , transform)       
 
    json_transform = self.json_data["transforms"][transform]

    name = str(json_transform["name"])
    parent_name = str(json_transform["parent"])

    transform = load_transform_matrix( json_transform["transform"] )

    node = avango.gua.nodes.TransformNode(Name = name)
    node.Transform.value = transform

    return node, parent_name


  def load_light(self, light):      
    print("load light" , light)   

    json_light = self.json_data["lights"][light]

    name = str(json_light["name"])
    parent_name = str(json_light["parent"])


    transform = load_transform_matrix( json_light["transform"] )

    distance = json_light["distance"]
    transform = transform * avango.gua.make_scale_mat(distance)

    color = avango.gua.Color(json_light["color"][0], json_light["color"][1], json_light["color"][2])

    energy = json_light["energy"]

    light = avango.gua.nodes.PointLightNode(Name = name
                                           ,Transform = transform
                                           ,Color = color
                                           ,EnableShadows = True
                                           ,Brightness = energy * 10)

    return light, parent_name


def load_transform_matrix(matrix_list):
  transform = avango.gua.make_identity_mat()

  for element in range(len(matrix_list)):
    transform.set_element(int(element/4), element%4 ,matrix_list[element])

  return transform
