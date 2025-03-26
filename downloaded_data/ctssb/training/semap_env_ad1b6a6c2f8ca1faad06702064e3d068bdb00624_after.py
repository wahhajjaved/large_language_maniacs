#!/usr/bin/env python

import rospy, tf
import roslib; roslib.load_manifest("spatial_environment")

from visualization_msgs.msg import *
from geometry_msgs.msg import Pose, PoseStamped, PointStamped, PolygonStamped, Polygon
from spatial_db_ros.srv import *
from spatial_db_ros.service_calls import *
from spatial_db_msgs.msg import Point2DModel, Point3DModel, Pose2DModel, Pose3DModel, Polygon2DModel, Polygon3DModel, TriangleMesh3DModel, PolygonMesh3DModel
from spatial_db_msgs.msg import ColorCommand
from spatial_db_msgs.msg import ObjectDescription as ROSObjectDescription
from spatial_db_msgs.msg import ObjectInstance as ROSObjectInstance
from object_description_marker import *

class InstVisu:
  relative = None
  absolute = None

class DescVisu:
  geometries = None
  abstractions = None

class ModelVisu:
  type = None
  id = None
  show_geo = False
  geo_color = []
  geo_scale = []
  show_text = False
  text_color = []
  text_scale = []
  text_offset = []
  handle = None

  def __init__(self, type = None, id = None,\
               show_geo = False, \
               geo_color = [0,0,0,1], \
               geo_scale = [0.2,0.2,0.2], \
               show_text = False, \
               text_color = [0,0,0,1], \
               text_scale = [0.1,0.1,0.1], \
               text_offset = [0.0,0.0,0.25]):
    self.id = id
    self.type = type
    self.show_geo = show_geo
    self.geo_color = geo_color
    self.geo_scale = geo_scale
    self.show_text = show_text
    self.text_color = text_color
    self.text_scale = text_scale
    self.text_offset = text_offset

  def __repr__(self):
    string = "ModelVisu(type=%r, id=%r, show_geo=%r)" % (
                                        self.type,
                                        self.id,
                                        self.show_geo)
                                        #self.geo_color,
                                        #self.geo_scale,
                                        #self.show_text,
                                        #self.text_color,
                                        #self.text_scale,
                                        #self.text_offset
    return string

def defaultRelativeDescriptionVisu(geo_set):
  model_dict = {}

  for model in geo_set.point2d_models:
    visu = visuPoint2DModel(model)
    model_dict[visu.type] = visu

  for model in geo_set.pose2d_models:
    visu = visuPose2DModel(model)
    model_dict[visu.type] = visu

  for model in geo_set.polygon2d_models:
    visu = visuPolygon2DModel(model)
    model_dict[visu.type] = visu

  for model in geo_set.point3d_models:
    visu = visuPoint3DModel(model)
    model_dict[visu.type] = visu

  for model in geo_set.pose3d_models:
    visu = visuPose3DModel(model)
    model_dict[visu.type] = visu

  for model in geo_set.polygon3d_models:
    visu = visuPolygon3DModel(model)
    model_dict[visu.type] = visu

  for model in geo_set.trianglemesh3d_models:
    visu = visuTriangleMesh3DModel(model)
    visu.show_geo = True
    model_dict[visu.type] = visu

  for model in geo_set.polygonmesh3d_models:
    visu = visuPolygonMesh3DModel(model)
    model_dict[visu.type] = visu

  return model_dict

def defaultAbsoluteDescriptionVisu(geo_set):
  model_dict = {}

  for model in geo_set.point2d_models:
    visu = visuPoint2DModel(model)
    visu.show_geo = False
    visu.geo_color = [1.0, 0.5, 0.5, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.pose2d_models:
    visu = visuPose2DModel(model)
    visu.show_geo = False
    model_dict[visu.type] = visu

  for model in geo_set.polygon2d_models:
    visu = visuPolygon2DModel(model)
    visu.show_geo = False
    visu.geo_color = [1.0, 0.5, 0.5, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.point3d_models:
    visu = visuPoint3DModel(model)
    visu.show_geo = False
    visu.geo_color = [1.0, 0.5, 0.5, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.pose3d_models:
    visu = visuPose3DModel(model)
    visu.show_geo = False
    visu.geo_color = [1.0, 0.5, 0.5, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.polygon3d_models:
    visu = visuPolygon3DModel(model)
    visu.show_geo = False
    visu.geo_color = [1.0, 0.5, 0.5, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.trianglemesh3d_models:
    visu = visuTriangleMesh3DModel(model)
    visu.show_geo = False
    visu.geo_color = [1.0, 0.5, 0.5, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.polygonmesh3d_models:
    visu = visuPolygonMesh3DModel(model)
    visu.show_geo = False
    visu.geo_color = [1.0, 0.5, 0.5, 1.0]
    visu.geo_scale = [0.01, 0.01, 0.01]
    model_dict[visu.type] = visu

  return model_dict

def defaultRelativeAbstractionVisu(geo_set):
  model_dict = {}

  for model in geo_set.point2d_models:
    visu = visuPoint2DModel(model)
    if model.type == "Position2D":
      visu.show_geo = False
      visu.geo_color = [0.0, 0.5, 0.0, 1.0]
      visu.geo_scale = [0.02, 0.02, 0.02]
    model_dict[visu.type] = visu

  for model in geo_set.pose2d_models:
    visu = visuPose2DModel(model)
    model_dict[visu.type] = visu

  for model in geo_set.polygon2d_models:
    visu = visuPolygon2DModel(model)
    if model.type == "FootprintBox":
      visu.show_geo = False
      visu.geo_color = [0.0, 0.0, 0.50, 1.0]
      visu.geo_scale = [0.01, 0.01, 0.01]
    if model.type == "FootprintHull":
      visu.show_geo = False
      visu.geo_color = [0.0, 0.50, 0.0, 1.0]
      visu.geo_scale = [0.01, 0.01, 0.01]
    model_dict[visu.type] = visu

  for model in geo_set.point3d_models:
    visu = visuPoint3DModel(model)
    if model.type == "Position3D":
      visu.show_geo = False
      visu.geo_color = [0.0, 0.75, 6.0, 1.0]
      visu.geo_scale = [0.21, 0.21, 0.21]
    model_dict[visu.type] = visu

  for model in geo_set.pose3d_models:
    visu = visuPose3DModel(model)
    model_dict[visu.type] = visu

  for model in geo_set.polygon3d_models:
    visu = visuPolygon3DModel(model)
    if model.type == "Front":
      visu.show_geo = False
      visu.geo_color = [1.0, 0.0, 0.0, 1.0]
      visu.geo_scale = [0.03, 0.03, 0.03]
    if model.type == "Back":
      visu.show_geo = False
      visu.geo_color = [1.0, 1.0, 0.0, 1.0]
      visu.geo_scale = [0.03, 0.03, 0.03]
    if model.type == "Left":
      visu.show_geo = False
      visu.geo_color = [0.0, 1.0, 0.0, 1.0]
      visu.geo_scale = [0.03, 0.03, 0.03]
    if model.type == "Right":
      visu.show_geo = False
      visu.geo_color = [0.0, 1.0, 1.0, 1.0]
      visu.geo_scale = [0.03, 0.03, 0.03]
    if model.type == "Top":
      visu.show_geo = False
      visu.geo_color = [1.0, 0.0, 1.0, 1.0]
      visu.geo_scale = [0.03, 0.03, 0.03]
    if model.type == "Bottom":
      visu.show_geo = False
      visu.geo_color = [0.0, 0.0, 1.0, 1.0]
      visu.geo_scale = [0.03, 0.03, 0.03]
    model_dict[visu.type] = visu

  for model in geo_set.trianglemesh3d_models:
    visu = visuTriangleMesh3DModel(model)
    model_dict[visu.type] = visu

  for model in geo_set.polygonmesh3d_models:
    visu = visuPolygonMesh3DModel(model)
    if model.type == "BoundingHull":
      visu.show_geo = False
      visu.geo_color = [0.0, 0.75, 0.0, 1.0]
      visu.geo_scale = [0.005, 0.005, 0.005]
    if model.type == "BoundingBox":
      visu.show_geo = False
      visu.geo_color = [0.0, 0.0, 0.75, 1.0]
      visu.geo_scale = [0.01, 0.01, 0.01]
    if model.type == "BoundingHull":
      visu.show_geo = False
      visu.geo_color = [0.75, 0.75, 0.0, 1.0]
      visu.geo_scale = [0.005, 0.005, 0.005]
    if model.type == "BoundingBox":
      visu.show_geo = False
      visu.geo_color = [0.75, 0.0, 0.0, 1.0]
      visu.geo_scale = [0.01, 0.01, 0.01]
    if model.type == "AxisAligned3D":
      visu.show_geo = False
      visu.geo_color = [0.75, 0.75, 0.75, 1.0]
      visu.geo_scale = [0.01, 0.01, 0.01]
      visu.show_text = False
    if model.type == "FrontExtrusion":
      visu.show_geo = True
      visu.geo_color = [1.0, 0.0, 0.0, 1.0]
      visu.geo_scale = [0.04, 0.04, 0.04]
    if model.type == "BackExtrusion":
      visu.show_geo = True
      visu.geo_color = [1.0, 1.0, 0.0, 1.0]
      visu.geo_scale = [0.04, 0.04, 0.04]
    if model.type == "LeftExtrusion":
      visu.show_geo = True
      visu.geo_color = [0.0, 1.0, 0.0, 1.0]
      visu.geo_scale = [0.04, 0.04, 0.04]
    if model.type == "RightExtrusion":
      visu.show_geo = True
      visu.geo_color = [0.0, 1.0, 1.0, 1.0]
      visu.geo_scale = [0.04, 0.04, 0.04]
    if model.type == "TopExtrusion":
      visu.show_geo = True
      visu.geo_color = [1.0, 0.0, 1.0, 1.0]
      visu.geo_scale = [0.04, 0.04, 0.04]
    if model.type == "BottomExtrusion":
      visu.show_geo = True
      visu.geo_color = [0.0, 0.0, 1.0, 1.0]
      visu.geo_scale = [0.04, 0.04, 0.04]
      
    model_dict[visu.type] = visu

  return model_dict

def defaultAbsoluteAbstractionVisu(geo_set):
  model_dict = {}

  for model in geo_set.point2d_models:
    visu = visuPoint2DModel(model)

    if model.type == "Position2D":
      visu.show_geo = False
      visu.geo_color = [0.5, 0.5, 0.0, 1.0]
      visu.geo_scale = [0.1, 0.1, 0.1]
    model_dict[visu.type] = visu

  for model in geo_set.pose2d_models:
    visu = visuPose2DModel(model)
    visu.show_geo = False
    model_dict[visu.type] = visu

  for model in geo_set.polygon2d_models:
    visu = visuPolygon2DModel(model)
    if model.type == "FootprintBox":
      visu.show_geo = False
      visu.geo_color = [0.5, 0.0, 0.0, 1.0]
      visu.geo_scale = [0.01, 0.01, 0.01]
    if model.type == "FootprintHull":
      visu.show_geo = False
      visu.geo_color = [0.5, 0.5, 0.0, 1.0]
      visu.geo_scale = [0.1, 0.1, 0.1]
      visu.show_text = False
    if model.type == "AxisAligned2D":
      visu.show_geo = False
      visu.geo_color = [0.55, 0.75, 0.75, 1.0]
      visu.geo_scale = [0.05, 0.05, 0.05]
      visu.show_text = False
    model_dict[visu.type] = visu

  for model in geo_set.point3d_models:
    visu = visuPoint3DModel(model)
    if model.type == "Position3D":
      visu.show_geo = False
      visu.geo_color = [0.75, 0.5, 6.0, 1.0]
      visu.geo_scale = [0.02, 0.02, 0.02]
    model_dict[visu.type] = visu

  for model in geo_set.pose3d_models:
    visu = visuPose3DModel(model)
    visu.show_geo = False
    model_dict[visu.type] = visu

  for model in geo_set.polygon3d_models:
    visu = visuPolygon3DModel(model)
    visu.show_geo = False
    if model.type == "Front":
      visu.show_geo = False
      visu.geo_color = [1.0, 0.0, 0.0, 1.0]
      visu.geo_scale = [0.03, 0.03, 0.03]
    if model.type == "Back":
      visu.show_geo = False
      visu.geo_color = [1.0, 1.0, 0.0, 1.0]
      visu.geo_scale = [0.03, 0.03, 0.03]
    if model.type == "Left":
      visu.show_geo = False
      visu.geo_color = [0.0, 1.0, 0.0, 1.0]
      visu.geo_scale = [0.03, 0.03, 0.03]
    if model.type == "Right":
      visu.show_geo = False
      visu.geo_color = [0.0, 1.0, 1.0, 1.0]
      visu.geo_scale = [0.03, 0.03, 0.03]
    if model.type == "Top":
      visu.show_geo = False
      visu.geo_color = [1.0, 0.0, 1.0, 1.0]
      visu.geo_scale = [0.03, 0.03, 0.03]
    if model.type == "Bottom":
      visu.show_geo = False
      visu.geo_color = [0.0, 0.0, 1.0, 1.0]
      visu.geo_scale = [0.03, 0.03, 0.03]
    model_dict[visu.type] = visu

  for model in geo_set.trianglemesh3d_models:
    visu = visuTriangleMesh3DModel(model)
    visu.show_geo = False
    model_dict[visu.type] = visu

  for model in geo_set.polygonmesh3d_models:
    visu = visuPolygonMesh3DModel(model)
    if model.type == "BoundingHull":
      visu.show_geo = False
      visu.geo_color = [0.75, 0.75, 0.0, 1.0]
      visu.geo_scale = [0.005, 0.005, 0.005]
    if model.type == "BoundingBox":
      visu.show_geo = False
      visu.geo_color = [0.75, 0.0, 0.0, 1.0]
      visu.geo_scale = [0.01, 0.01, 0.01]
    if model.type == "AxisAligned3D":
      visu.show_geo = False
      visu.geo_color = [0.75, 0.75, 0.75, 1.0]
      visu.geo_scale = [0.01, 0.01, 0.01]
      visu.show_text = False
    if model.type == "FrontExtrusion":
      visu.show_geo = True
      visu.geo_color = [1.0, 0.0, 0.0, 1.0]
      visu.geo_scale = [0.01, 0.01, 0.01]
    if model.type == "BackExtrusion":
      visu.show_geo = True
      visu.geo_color = [1.0, 1.0, 0.0, 1.0]
      visu.geo_scale = [0.01, 0.01, 0.01]
    if model.type == "LeftExtrusion":
      visu.show_geo = True
      visu.geo_color = [0.0, 1.0, 0.0, 1.0]
      visu.geo_scale = [0.01, 0.01, 0.01]
    if model.type == "RightExtrusion":
      visu.show_geo = True
      visu.geo_color = [0.0, 1.0, 1.0, 1.0]
      visu.geo_scale = [0.01, 0.01, 0.01]
    if model.type == "TopExtrusion":
      visu.show_geo = True
      visu.geo_color = [1.0, 0.0, 1.0, 1.0]
      visu.geo_scale = [0.01, 0.01, 0.01]
    if model.type == "BottomExtrusion":
      visu.show_geo = True
      visu.geo_color = [0.0, 0.0, 1.0, 1.0]
      visu.geo_scale = [0.01, 0.01, 0.01]
    model_dict[visu.type] = visu

  return model_dict

def defaultGhostRelativeDescriptionVisu(geo_set):
  model_dict = {}

  for model in geo_set.point2d_models:
    visu = visuPoint2DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.pose2d_models:
    visu = visuPose2DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.polygon2d_models:
    visu = visuPolygon2DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.point3d_models:
    visu = visuPoint3DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.pose3d_models:
    visu = visuPose3DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.polygon3d_models:
    visu = visuPolygon3DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.trianglemesh3d_models:
    visu = visuTriangleMesh3DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.polygonmesh3d_models:
    visu = visuPolygonMesh3DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu

  return model_dict

def defaultGhostAbsoluteDescriptionVisu(geo_set):
  model_dict = {}

  for model in geo_set.point2d_models:
    visu = visuPoint2DModel(model)
    visu.show_geo = True
    visu.geo_color = [0.5, 0.5, 0.5, 0.5]
    model_dict[visu.type] = visu

  for model in geo_set.pose2d_models:
    visu = visuPose2DModel(model)
    visu.show_geo = True
    visu.geo_color = [0.5, 0.5, 0.5, 0.5]
    model_dict[visu.type] = visu

  for model in geo_set.polygon2d_models:
    visu = visuPolygon2DModel(model)
    visu.show_geo = False
    visu.geo_color = [1.0, 0.5, 0.5, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.point3d_models:
    visu = visuPoint3DModel(model)
    visu.show_geo = True
    visu.geo_color = [0.5, 0.5, 0.5, 0.5]
    model_dict[visu.type] = visu

  for model in geo_set.pose3d_models:
    visu = visuPose3DModel(model)
    visu.show_geo = True
    visu.geo_color = [0.5, 0.5, 0.5, 0.5]
    model_dict[visu.type] = visu

  for model in geo_set.polygon3d_models:
    visu = visuPolygon3DModel(model)
    visu.show_geo = True
    visu.geo_color = [0.5, 0.5, 0.5, 0.5]
    model_dict[visu.type] = visu

  for model in geo_set.trianglemesh3d_models:
    visu = visuTriangleMesh3DModel(model)
    visu.show_geo = True
    visu.geo_color = [0.5, 0.5, 0.5, 0.5]
    model_dict[visu.type] = visu

  for model in geo_set.polygonmesh3d_models:
    visu = visuPolygonMesh3DModel(model)
    visu.show_geo = True
    visu.geo_color = [0.5, 0.5, 0.5, 0.5]
    visu.geo_scale = [0.01, 0.01, 0.01]
    model_dict[visu.type] = visu

  return model_dict

def defaultGhostRelativeAbstractionVisu(geo_set):
  model_dict = {}

  for model in geo_set.point2d_models:
    visu = visuPoint2DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.pose2d_models:
    visu = visuPose2DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.polygon2d_models:
    visu = visuPolygon2DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.point3d_models:
    visu = visuPoint3DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.pose3d_models:
    visu = visuPose3DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.polygon3d_models:
    visu = visuPolygon3DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.trianglemesh3d_models:
    visu = visuTriangleMesh3DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu

  for model in geo_set.polygonmesh3d_models:
    visu = visuPolygonMesh3DModel(model)
    visu.show_geo = False
    visu.geo_color = [0.0, 0.0, 0.0, 1.0]
    model_dict[visu.type] = visu
  return model_dict

def defaultGhostAbsoluteAbstractionVisu(geo_set):
  model_dict = {}

  for model in geo_set.point2d_models:
    visu = visuPoint2DModel(model)
    if model.type == "Position2D":
      visu.show_geo = False
      visu.geo_color = [0.5, 0.5, 0.5, 0.5]
      visu.geo_scale = [0.1, 0.1, 0.1]
    model_dict[visu.type] = visu

  for model in geo_set.pose2d_models:
    visu = visuPose2DModel(model)
    visu.show_geo = False
    model_dict[visu.type] = visu

  for model in geo_set.polygon2d_models:
    visu = visuPolygon2DModel(model)
    if model.type == "FootprintBox":
      visu.show_geo = False
      visu.geo_color = [0.5, 0.5, 0.5, 0.5]
      visu.geo_scale = [0.01, 0.01, 0.01]
    if model.type == "FootprintHull":
      visu.show_geo = False
      visu.geo_color = [0.5, 0.5, 0.5, 0.5]
      visu.geo_scale = [0.1, 0.1, 0.1]
      visu.show_text = False
    if model.type == "AxisAligned2D":
      visu.show_geo = False
      visu.geo_color = [0.5, 0.5, 0.5, 0.5]
      visu.geo_scale = [0.05, 0.05, 0.05]
      visu.show_text = False
    model_dict[visu.type] = visu

  for model in geo_set.point3d_models:
    visu = visuPoint3DModel(model)
    if model.type == "Position3D":
      visu.show_geo = False
      visu.geo_color = [0.5, 0.5, 0.5, 0.5]
      visu.geo_scale = [0.02, 0.02, 0.02]
    model_dict[visu.type] = visu

  for model in geo_set.pose3d_models:
    visu = visuPose3DModel(model)
    visu.show_geo = False
    model_dict[visu.type] = visu

  for model in geo_set.polygon3d_models:
    visu = visuPolygon3DModel(model)
    visu.show_geo = False
    model_dict[visu.type] = visu

  for model in geo_set.trianglemesh3d_models:
    visu = visuTriangleMesh3DModel(model)
    visu.show_geo = False
    model_dict[visu.type] = visu

  for model in geo_set.polygonmesh3d_models:
    visu = visuPolygonMesh3DModel(model)
    if model.type == "BoundingHull":
      visu.show_geo = False
      visu.geo_color = [0.5, 0.5, 0.5, 0.5]
      visu.geo_scale = [0.005, 0.005, 0.005]
    if model.type == "BoundingBox":
      visu.show_geo = False
      visu.geo_color = [0.5, 0.5, 0.5, 0.5]
      visu.geo_scale = [0.01, 0.01, 0.01]
    if model.type == "AxisAligned3D":
      visu.show_geo = False
      visu.geo_color = [0.5, 0.5, 0.5, 0.5]
      visu.geo_scale = [0.01, 0.01, 0.01]
      visu.show_text = False
    model_dict[visu.type] = visu

  return model_dict

def create_model_visualization_marker(frame, model, model_visu):

    array = MarkerArray()

    if type(model) is Point2DModel:
      pose = ROSPoseStamped()
      pose.header.frame_id = frame
      pose.pose.orientation.w = 1.0
      pose.pose.position.x = model.geometry.x
      pose.pose.position.y = model.geometry.y
      pose.pose.position.z = 0.0

      if model_visu[model.type].show_geo:
        geo_marker = create_point_marker("Point2D", pose, model_visu[model.type].geo_color, model_visu[model.type].geo_scale)
        array.markers.append(geo_marker)

      if model_visu[model.type].show_text:
        text_marker = create_text_marker("Label", pose, model_visu[model.type].text_color, model_visu[model.type].text_scale, model.type)
        array.markers.append(text_marker)

    if type(model) is Pose2DModel:
      pose = ROSPoseStamped()
      pose.header.frame_id = frame
      pose.pose.orientation.w = 1.0
      quat = quaternion_from_euler(0, 0, model.pose.theta)
      pose.pose.position.x = model.pose.x
      pose.pose.position.y = model.pose.y
      pose.pose.position.z = 0.0
      pose.pose.orientation.x = quat[0]
      pose.pose.orientation.y = quat[1]
      pose.pose.orientation.z = quat[2]
      pose.pose.orientation.w = quat[3]

      if model_visu[model.type].show_geo:
        geo_marker = create_pose_marker("Pose2D", pose, model_visu[model.type].geo_color, model_visu[model.type].geo_scale)
        array.markers.append(geo_marker)

      if model_visu[model.type].show_text:
        text_marker = create_text_marker("Label", pose, model_visu[model.type].text_color, model_visu[model.type].text_scale, model.type)
        array.markers.append(text_marker)

    if type(model) is Polygon2DModel:
      pose = ROSPoseStamped()
      pose.header.frame_id = frame
      pose.pose.orientation.w = 1.0
      pose.pose = model.pose

      if absolute:
        pose.header.frame_id = "world"

      if model_visu[model.type].show_geo:
        geo_marker = create_polygon_marker("Polygon2D", pose, model_visu[model.type].geo_color, model_visu[model.type].geo_scale, model.geometry)
        array.markers.append(geo_marker)
      if model_visu[model.type].show_text:
        text_marker = create_text_marker("Label", pose, model_visu[model.type].text_color, model_visu[model.type].text_scale, model.type)
        array.markers.append(text_marker)

    if type(model) is Point3DModel:
      pose = ROSPoseStamped()
      pose.header.frame_id = frame
      pose.pose.orientation.w = 1.0
      pose.pose.position = model.geometry

      if model_visu[model.type].show_geo:
        geo_marker = create_point_marker("Point3D", pose, model_visu[model.type].geo_color, model_visu[model.type].geo_scale)
        array.markers.append(geo_marker)

      if model_visu[model.type].show_text:
        text_marker = create_text_marker("Label", pose, model_visu[model.type].text_color, model_visu[model.type].text_scale, model.type)
        array.markers.append(text_marker)

    if type(model) is Pose3DModel:
      pose = ROSPoseStamped()
      pose.header.frame_id = frame
      pose.pose.orientation.w = 1.0
      pose.pose = model.pose

      if model_visu[model.type].show_geo:
        geo_marker = create_pose_marker("Pose3D", pose, model_visu[model.type].geo_color, model_visu[model.type].geo_scale)
        array.markers.append(geo_marker)

      if model_visu[model.type].show_text:
        text_marker = create_text_marker("Label", pose, model_visu[model.type].text_color, model_visu[model.type].text_scale, model.type)
        array.markers.append(text_marker)

    if type(model) is Polygon3DModel:
      pose = ROSPoseStamped()
      pose.header.frame_id = frame
      pose.pose.orientation.w = 1.0
      pose.pose = model.pose

      if model_visu[model.type].show_geo:
        geo_marker = create_polygon_marker("Polygon3D", pose, model_visu[model.type].geo_color, model_visu[model.type].geo_scale, model.geometry)
        array.markers.append(geo_marker)

      if model_visu[model.type].show_text:
        text_marker = create_text_marker("Label", pose, model_visu[model.type].text_color, model_visu[model.type].text_scale, model.type)
        array.markers.append(text_marker)

    if type(model) is TriangleMesh3DModel:
      pose = ROSPoseStamped()
      pose.header.frame_id = frame
      pose.pose.orientation.w = 1.0
      pose.pose = model.pose

      if model_visu[model.type].show_geo:
        geo_marker = create_mesh_marker("TriangleMesh3D", pose, model_visu[model.type].geo_color, model_visu[model.type].geo_scale, model.geometry)
        array.markers.append(geo_marker)

      if model_visu[model.type].show_text:
        text_marker = create_text_marker("Label", pose, model_visu[model.type].text_color, model_visu[model.type].text_scale, model.type)
        array.markers.append(text_marker)

    if type(model) is PolygonMesh3DModel:
      pose = ROSPoseStamped()
      pose.header.frame_id = frame
      pose.pose.orientation.w = 1.0
      pose.pose = model.pose

      if model_visu[model.type].show_geo:
        for polygon in model.geometry.polygons:
          geo_marker = create_polygon_marker("PolygonMesh3D", pose, model_visu[model.type].geo_color, model_visu[model.type].geo_scale, polygon)
          array.markers.append(geo_marker)

      if model_visu[model.type].show_text:
        text_marker = create_text_marker("Label", pose, model_visu[model.type].text_color, model_visu[model.type].text_scale, model.type, model_visu[model.type].text_offset)
        array.markers.append(text_marker)

    id = 0
    for m in array.markers:
      m.id = id
      id += 1

    return array

def create_geometry_model_set_marker(geo_set, pose, visu):

  array = MarkerArray()

  for model in geo_set.point2d_models:
    model_pose = copy.deepcopy(pose)
    model_pose.pose.position.x = model.geometry.x
    model_pose.pose.position.y = model.geometry.y
    model_pose.pose.position.z = 0.0
    if visu[model.type].show_geo:
      geo_marker = create_point_marker("Point2D", model_pose, visu[model.type].geo_color, visu[model.type].geo_scale)
      array.markers.append(geo_marker)

    if visu[model.type].show_text:
      text_marker = create_text_marker("Label", model_pose, visu[model.type].text_color, visu[model.type].text_scale, model.type)
      array.markers.append(text_marker)

  for model in geo_set.pose2d_models:
    quat = quaternion_from_euler(0, 0, model.pose.theta)
    model_pose = copy.deepcopy(pose)
    
    model_pose.pose.position.x = model.pose.x
    model_pose.pose.position.y = model.pose.y
    model_pose.pose.position.z = 0.0
    model_pose.pose.orientation.x = quat[0]
    model_pose.pose.orientation.y = quat[1]
    model_pose.pose.orientation.z = quat[2]
    model_pose.pose.orientation.w = quat[3]

    if visu[model.type].show_geo:
      geo_marker = create_pose_marker("Pose2D", model_pose, visu[model.type].geo_color, visu[model.type].geo_scale)
      array.markers.append(geo_marker)

    if visu[model.type].show_text:
      text_marker = create_text_marker("Label", model_pose, visu[model.type].text_color, visu[model.type].text_scale, model.type)
      array.markers.append(text_marker)

  for model in geo_set.polygon2d_models:
    model_pose = copy.deepcopy(pose)
    model_pose.pose = model.pose
    if visu[model.type].show_geo:
      geo_marker = create_polygon_marker("Polygon2D", model_pose, visu[model.type].geo_color, visu[model.type].geo_scale, model.geometry)
      array.markers.append(geo_marker)
    if visu[model.type].show_text:
      text_marker = create_text_marker("Label", model_pose, visu[model.type].text_color, visu[model.type].text_scale, model.type)
      array.markers.append(text_marker)

  for model in geo_set.point3d_models:
    model_pose = copy.deepcopy(pose)
    model_pose.pose.position = model.geometry

    if visu[model.type].show_geo:
      geo_marker = create_point_marker("Point3D", model_pose, visu[model.type].geo_color, visu[model.type].geo_scale)
      array.markers.append(geo_marker)

    if visu[model.type].show_text:
      text_marker = create_text_marker("Label", model_pose, visu[model.type].text_color, visu[model.type].text_scale, model.type)
      array.markers.append(text_marker)

  for model in geo_set.pose3d_models:
    model_pose = copy.deepcopy(pose)
    model_pose.pose = model.pose

    if visu[model.type].show_geo:
      geo_marker = create_pose_marker("Pose3D", model_pose, visu[model.type].geo_color, visu[model.type].geo_scale)
      array.markers.append(geo_marker)

    if visu[model.type].show_text:
      text_marker = create_text_marker("Label", model_pose, visu[model.type].text_color, visu[model.type].text_scale, model.type)
      array.markers.append(text_marker)
  for model in geo_set.polygon3d_models:
    model_pose = copy.deepcopy(pose)
    model_pose.pose = model.pose

    if visu[model.type].show_geo:
      geo_marker = create_polygon_marker("Polygon3D", model_pose, visu[model.type].geo_color, visu[model.type].geo_scale, model.geometry)
      array.markers.append(geo_marker)

    if visu[model.type].show_text:
      text_marker = create_text_marker("Label", model_pose, visu[model.type].text_color, visu[model.type].text_scale, model.type)
      array.markers.append(text_marker)
  for model in geo_set.trianglemesh3d_models:
    model_pose = copy.deepcopy(pose)
    model_pose.pose = model.pose

    if visu[model.type].show_geo:
      geo_marker = create_mesh_marker("TriangleMesh3D", model_pose, visu[model.type].geo_color, visu[model.type].geo_scale, model.geometry)
      array.markers.append(geo_marker)

    if visu[model.type].show_text:
      text_marker = create_text_marker("Label", model_pose, visu[model.type].text_color, visu[model.type].text_scale, model.type)
      array.markers.append(text_marker)

  for model in geo_set.polygonmesh3d_models:
    model_pose = copy.deepcopy(pose)
    model_pose.pose = model.pose
    if visu[model.type].show_geo:
      for polygon in model.geometry.polygons:
        poly = ROSPolygon()
        for point in polygon.vertex_indices:
          poly.points.append(model.geometry.vertices[point])

        geo_marker = create_polygon_marker("PolygonMesh3D", model_pose, visu[model.type].geo_color, visu[model.type].geo_scale, poly)
        array.markers.append(geo_marker)

    if visu[model.type].show_text:
      text_marker = create_text_marker("Label", model_pose, visu[model.type].text_color, visu[model.type].text_scale, model.type, visu[model.type].text_offset)
      array.markers.append(text_marker)

  id = 0
  for m in array.markers:
    m.id = id
    id += 1

  return array

def create_inactive_object_visualization_marker(inst, inst_visu):

  array = MarkerArray()

  root_pose = ROSPoseStamped()
  root_pose.header.frame_id = "world"
  root_pose.pose.orientation.w = 1.0
  absolute_geometries_marker = create_geometry_model_set_marker(inst.absolute.geometries, root_pose, inst_visu.absolute.geometries)
  absolute_abstraction_marker = create_geometry_model_set_marker(inst.absolute.abstractions, root_pose, inst_visu.absolute.abstractions)
  array.markers += absolute_geometries_marker.markers
  array.markers += absolute_abstraction_marker.markers

  id = 0
  for m in array.markers:
    m.id = id
    id += 1

  return array

def create_object_visualization_marker(inst, inst_visu):

  array = MarkerArray()

  inst_pose = ROSPoseStamped()
  inst_pose.header.frame_id = inst.name
  inst_pose.pose.orientation.w = 1.0
  relative_geometries_marker = create_geometry_model_set_marker(inst.description.geometries, inst_pose, inst_visu.relative.geometries)
  array.markers += relative_geometries_marker.markers

  relative_abstraction_marker = create_geometry_model_set_marker(inst.description.abstractions, inst_pose, inst_visu.relative.abstractions)
  array.markers += relative_abstraction_marker.markers

  root_pose = ROSPoseStamped()
  root_pose.header.frame_id = "world"
  root_pose.pose.orientation.w = 1.0
  absolute_geometries_marker = create_geometry_model_set_marker(inst.absolute.geometries, root_pose, inst_visu.absolute.geometries)
  absolute_abstraction_marker = create_geometry_model_set_marker(inst.absolute.abstractions, root_pose, inst_visu.absolute.abstractions)

  array.markers += absolute_geometries_marker.markers
  array.markers += absolute_abstraction_marker.markers

  id = 0
  for m in array.markers:
    m.id = id
    id += 1

  return array

def visuPoint2DModel( model ):
  visu = ModelVisu()
  visu.id = model.id
  visu.type = model.type
  visu.show_geo = True
  visu.geo_color = [1.0, 0.0, 0.0, 1.0]
  visu.geo_scale = [0.05, 0.05, 0.05]
  visu.show_text = False
  visu.text_color = [1.0, 1.0, 1.0, 1.0]
  visu.text_scale = [0.1, 0.1, 0.1]
  visu.text_offset = [0.0, 0.0, 0.1]
  return visu

def visuPose2DModel( model ):
  visu = ModelVisu()
  visu.id = model.id
  visu.type = model.type
  visu.show_geo = True
  visu.geo_color = [1.0, 1.0, 0.0, 1.0]
  visu.geo_scale = [0.1, 0.025, 0.025]
  visu.show_text = False
  visu.text_color = [1.0, 1.0, 1.0, 1.0]
  visu.text_scale = [0.1, 0.1, 0.1]
  visu.text_offset = [0.0, 0.0, 0.1]
  return visu

def visuPolygon2DModel( model ):
  visu = ModelVisu()
  visu.id = model.id
  visu.type = model.type
  visu.show_geo = True
  visu.geo_color = [0.0, 1.0, 1.0, 1.0]
  visu.geo_scale = [0.05, 0.05, 0.05]
  visu.show_text = False
  visu.text_color = [1.0, 1.0, 1.0, 1.0]
  visu.text_scale = [0.1, 0.1, 0.1]
  visu.text_offset = [0.0, 0.0, 0.1]
  return visu

def visuPoint3DModel( model ):
  visu = ModelVisu()
  visu.id = model.id
  visu.type = model.type
  visu.show_geo = True
  visu.geo_color = [0.0, 0.0, 1.0, 1.0]
  visu.geo_scale = [0.05, 0.05, 0.05]
  visu.show_text = False
  visu.text_color = [1.0, 1.0, 1.0, 1.0]
  visu.text_scale = [0.1, 0.1, 0.1]
  visu.text_offset = [0.0, 0.0, 0.1]
  return visu

def visuPose3DModel( model ):
  visu = ModelVisu()
  visu.id = model.id
  visu.type = model.type
  visu.show_geo = True
  visu.geo_color = [0.0, 0.0, 1.0, 1.0]
  visu.geo_scale = [0.1, 0.025, 0.025]
  visu.show_text = False
  visu.text_color = [1.0, 1.0, 1.0, 1.0]
  visu.text_scale = [0.1, 0.1, 0.1]
  visu.text_offset = [0.0, 0.0, 0.1]
  return visu

def visuPolygon3DModel( model ):
  visu = ModelVisu()
  visu.id = model.id
  visu.type = model.type
  visu.show_geo = True
  visu.geo_color = [0.0, 1.0, 0.0, 1.0]
  visu.geo_scale = [0.05, 0.05, 0.05]
  visu.show_text = False
  visu.text_color = [1.0, 1.0, 1.0, 1.0]
  visu.text_scale = [0.1, 0.1, 0.1]
  visu.text_offset = [0.0, 0.0, 0.1]
  return visu

def visuTriangleMesh3DModel( model ):
  visu = ModelVisu()
  visu.id = model.id
  visu.type = model.type
  visu.show_geo = True
  visu.geo_color = [0.0, 0.5, 0.5, 1.0]
  visu.geo_scale = [1.0, 1.0, 1.0]
  visu.show_text = False
  visu.text_color = [1.0, 1.0, 1.0, 1.0]
  visu.text_scale = [0.1, 0.1, 0.1]
  visu.text_offset = [0.0, 0.0, 0.1]
  return visu

def visuPolygonMesh3DModel( model ):
  visu = ModelVisu()
  visu.id = model.id
  visu.type = model.type
  visu.show_geo = True
  visu.geo_color = [0.5, 1.0, 0.5, 1.0]
  visu.geo_scale = [0.01, 0.01, 0.01]
  visu.show_text = False
  visu.text_color = [1.0, 1.0, 1.0, 1.0]
  visu.text_scale = [0.1, 0.1, 0.1]
  visu.text_offset = [0.0, 0.0, 0.1]
  return visu
