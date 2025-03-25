# -*- coding: utf-8 -*-
"""
/***************************************************************************
 LTS
                                 A QGIS plugin
 Computes level of traffic stress
                              -------------------
        begin                : 2014-04-24
        copyright            : (C) 2014 by Peyman Noursalehi / Northeastern University
        email                : p.noursalehi@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
# Import the PyQt and QGIS libraries
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import QtCore, QtGui
from qgis.core import *
from qgis.utils import iface
# Initialize Qt resources from file resources.py
import resources_rc
# Import the code for the dialog
from ltsdialog import LTSDialog
from ui_lts import Ui_Dialog
import os.path
from os.path import expanduser
from math import floor,ceil
import networkx as nx 
from collections import OrderedDict
import os 
############## read or write shapefiles
"""
*********
Shapefile
*********
####

Edited read write, added file name option

#####
Generates a networkx.DiGraph from point and line shapefiles.

"The Esri Shapefile or simply a shapefile is a popular geospatial vector
data format for geographic information systems software. It is developed
and regulated by Esri as a (mostly) open specification for data
interoperability among Esri and other software products."
See http://en.wikipedia.org/wiki/Shapefile for additional information.
"""
#    Copyright (C) 2004-2010 by
#    Ben Reilly <benwreilly@gmail.com>
#    Aric Hagberg <hagberg@lanl.gov>
#    Dan Schult <dschult@colgate.edu>
#    Pieter Swart <swart@lanl.gov>
#    All rights reserved.
#    BSD license.

__author__ = """Ben Reilly (benwreilly@gmail.com)"""
__all__ = ['read_shp', 'write_shp']


def read_shp(path):
    """Generates a networkx.DiGraph from shapefiles. Point geometries are
    translated into nodes, lines into edges. Coordinate tuples are used as
    keys. Attributes are preserved, line geometries are simplified into start
    and end coordinates. Accepts a single shapefile or directory of many
    shapefiles.

    "The Esri Shapefile or simply a shapefile is a popular geospatial vector
    data format for geographic information systems software [1]_."

    Parameters
    ----------
    path : file or string
       File, directory, or filename to read.

    Returns
    -------
    G : NetworkX graph

    Examples
    --------
    >>> G=nx.read_shp('test.shp') # doctest: +SKIP

    References
    ----------
    .. [1] http://en.wikipedia.org/wiki/Shapefile
    """
    try:
        from osgeo import ogr
    except ImportError:
        raise ImportError("read_shp requires OGR: http://www.gdal.org/")

    net = nx.DiGraph()

    def getfieldinfo(lyr, feature, flds):
            f = feature
            return [f.GetField(f.GetFieldIndex(x)) for x in flds]

    def addlyr(lyr, fields):
        for findex in xrange(lyr.GetFeatureCount()):
            f = lyr.GetFeature(findex)
            flddata = getfieldinfo(lyr, f, fields)
            g = f.geometry()
            attributes = dict(zip(fields, flddata))
            attributes["ShpName"] = lyr.GetName()
            if g.GetGeometryType() == 1:  # point
                net.add_node((g.GetPoint_2D(0)), attributes)
            if g.GetGeometryType() == 2:  # linestring
                attributes["Wkb"] = g.ExportToWkb()
                attributes["Wkt"] = g.ExportToWkt()
                attributes["Json"] = g.ExportToJson()
                last = g.GetPointCount() - 1
                net.add_edge(g.GetPoint_2D(0), g.GetPoint_2D(last), attributes)

    if isinstance(path, str):
        shp = ogr.Open(path)
        lyrcount = shp.GetLayerCount()  # multiple layers indicate a directory
        for lyrindex in xrange(lyrcount):
            lyr = shp.GetLayerByIndex(lyrindex)
            flds = [x.GetName() for x in lyr.schema]
            addlyr(lyr, flds)
    return net


def write_shp(G, outdir,edges_name):
    """Writes a networkx.DiGraph to two shapefiles, edges and nodes.
    Nodes and edges are expected to have a Well Known Binary (Wkb) or
    Well Known Text (Wkt) key in order to generate geometries. Also
    acceptable are nodes with a numeric tuple key (x,y).

    "The Esri Shapefile or simply a shapefile is a popular geospatial vector
    data format for geographic information systems software [1]_."

    Parameters
    ----------
    outdir : directory path
       Output directory for the two shapefiles.

    Returns
    -------
    None

    Examples
    --------
    nx.write_shp(digraph, '/shapefiles') # doctest +SKIP

    References
    ----------
    .. [1] http://en.wikipedia.org/wiki/Shapefile
    """
    try:
        from osgeo import ogr
    except ImportError:
        raise ImportError("write_shp requires OGR: http://www.gdal.org/")
    # easier to debug in python if ogr throws exceptions
    ogr.UseExceptions()

    def netgeometry(key, data):
        if 'Wkb' in data:
            geom = ogr.CreateGeometryFromWkb(data['Wkb'])
        elif 'Wkt' in data:
            geom = ogr.CreateGeometryFromWkt(data['Wkt'])
        elif type(key[0]).__name__ == 'tuple':  # edge keys are packed tuples
            geom = ogr.Geometry(ogr.wkbLineString)
            _from, _to = key[0], key[1]
            try:
                geom.SetPoint(0, *_from)
                geom.SetPoint(1, *_to)
            except TypeError:
                # assume user used tuple of int and choked ogr
                _ffrom = [float(x) for x in _from]
                _fto = [float(x) for x in _to]
                geom.SetPoint(0, *_ffrom)
                geom.SetPoint(1, *_fto)
        else:
            geom = ogr.Geometry(ogr.wkbPoint)
            try:
                geom.SetPoint(0, *key)
            except TypeError:
                # assume user used tuple of int and choked ogr
                fkey = [float(x) for x in key]
                geom.SetPoint(0, *fkey)

        return geom

    # Create_feature with new optional attributes arg (should be dict type)
    def create_feature(geometry, lyr, attributes=None):
        feature = ogr.Feature(lyr.GetLayerDefn())
        feature.SetGeometry(g)
        if attributes != None:
            # Loop through attributes, assigning data to each field
            for field, data in attributes.iteritems():
                feature.SetField(field, data)
        lyr.CreateFeature(feature)
        feature.Destroy()

    drv = ogr.GetDriverByName("ESRI Shapefile")
    shpdir = drv.CreateDataSource(outdir)
    # delete pre-existing output first otherwise ogr chokes
    # try:
    #     shpdir.DeleteLayer(nodes_name)
    # except:
    #     pass
    # nodes = shpdir.CreateLayer(nodes_name, None, ogr.wkbPoint)
    # for n in G:
    #     data = G.node[n] or {}
    #     g = netgeometry(n, data)
    #     create_feature(g, nodes)
    try:
        shpdir.DeleteLayer(edges_name)
    except:
        pass
    edges = shpdir.CreateLayer(edges_name, None, ogr.wkbLineString)

    # New edge attribute write support merged into edge loop
    fields = {}      # storage for field names and their data types
    attributes = {}  # storage for attribute data (indexed by field names)

    # Conversion dict between python and ogr types
    OGRTypes = {int: ogr.OFTInteger, str: ogr.OFTString, float: ogr.OFTReal}

    # Edge loop
    for e in G.edges(data=True):
        data = G.get_edge_data(*e)
        g = netgeometry(e, data)
        # Loop through attribute data in edges
        for key, data in e[2].iteritems():
            # Reject spatial data not required for attribute table
            if (key != 'Json' and key != 'Wkt' and key != 'Wkb'
                and key != 'ShpName'):
                  # For all edges check/add field and data type to fields dict
                    if key not in fields:
                  # Field not in previous edges so add to dict
                        if type(data) in OGRTypes:
                            fields[key] = OGRTypes[type(data)]
                        else:
                            # Data type not supported, default to string (char 80)
                            fields[key] = ogr.OFTString
                        # Create the new field
                        newfield = ogr.FieldDefn(key, fields[key])
                        edges.CreateField(newfield)
                        # Store the data from new field to dict for CreateLayer()
                        attributes[key] = data
                    else:
                     # Field already exists, add data to dict for CreateLayer()
                        attributes[key] = data
        # Create the feature with, passing new attribute data
        create_feature(g, edges, attributes)

    nodes, edges = None, None


# fixture for nose tests
def setup_module(module):
    from nose import SkipTest
    try:
        import ogr
    except:
        raise SkipTest("OGR not available")


###########################################################
###########################################################
class LTS:

    def __init__(self, iface):
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value("locale/userLocale")[0:2]
        localePath = os.path.join(self.plugin_dir, 'i18n', 'lts_{}.qm'.format(locale))

        if os.path.exists(localePath):
            self.translator = QTranslator()
            self.translator.load(localePath)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Create the dialog (after translation) and keep reference
        self.dlg = LTSDialog()
        self.update_ui()
        



    def initGui(self):
        # Create action that will start plugin configuration
        self.action = QAction(
            QIcon(":/plugins/lts/icon.png"),
            u"LTS calculator", self.iface.mainWindow())
        # connect the action to the run method
        self.action.triggered.connect(self.run)

        # Add toolbar button and menu item
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(u"&LTS Calculator", self.action)

        # QtCore.QObject.connect(self.dlg.ui.find_cc, QtCore.SIGNAL("clicked()"), self.find_connected_components)
        
        QtCore.QObject.connect(self.dlg.ui.process_Button,QtCore.SIGNAL("clicked()"), self.process)
        # QtCore.QObject.connect(self.dlg.ui.layerCombo,QtCore.SIGNAL("currentIndexChanged(int)"), self.update_lts_field)
        QtCore.QObject.connect(self.dlg.ui.layerCombo,QtCore.SIGNAL("activated (int)"), self.update_lts_field)
        QtCore.QObject.connect(self.dlg.ui.find_cc_Button,QtCore.SIGNAL("clicked()"), self.find_connected_components)


        self.update_ui()
        self.layers = self.iface.legendInterface().layers()  # store the layer list 
        # self.dlg.ui.layerCombo.clear()  # clear the combo 
        for layer in self.layers:    # foreach layer in legend 
            self.dlg.ui.layerCombo.addItem( layer.name() )    # add it to the combo 

    def unload(self):
        # Remove the plugin menu item and icon
        self.iface.removePluginMenu(u"&LTS Calculator", self.action)
        self.iface.removeToolBarIcon(self.action)

    def update_ui(self):
        # self.dlg.ui.lineEdit_in.clear()
        self.dlg.ui.progress_bar.setValue(0)

    
    def make_column(self,layer,name):
        index = layer.fieldNameIndex(str(name))
        if index == -1: # field doesn't exist
            caps = layer.dataProvider().capabilities()
            if caps & QgsVectorDataProvider.AddAttributes:
              res = layer.dataProvider().addAttributes( [ QgsField(str(name), \
                QVariant.Int) ] )
            layer.updateFields()
            return 0  # so I know if the column already existed or did I create it for the first time
        return 1

    def remove_column(self,layer,name,did_it_existed):
        #did_it_existed is number; if 1 means it was there before, so column should not be deleted.
        index = layer.fieldNameIndex(str(name))
        if index != -1 and did_it_existed==0 :  # field exists and wasn't there before
            layer.dataProvider().deleteAttributes( [index]  )            
            layer.updateFields()

    def update_lts_field(self):
        index = self.dlg.ui.layerCombo.currentIndex() 
        if index < 0: 
            # it may occur if there's no layer in the combo/legend 
            pass
        else: 
            layer = self.dlg.ui.layerCombo.itemData(index) 
        try:
            self.dlg.ui.lts_combo.clear()
            for attr in layer.dataProvider().fieldNameMap().keys(): # dict with column names as keys
                # if layer.type() == QgsMapLayer.VectorLayer and layer.geometryType() == QGis.Line:
                self.dlg.ui.lts_combo.addItem(str(attr), attr) 
        except:
            pass

    def process(self):
        """ Calculates Level of Traffic Stress for the selected layer"""


        index = self.dlg.ui.layerCombo.currentIndex() 
        if index < 0: 
            # it may occur if there's no layer in the combo/legend 
            pass
        else: 
            layer = self.dlg.ui.layerCombo.itemData(index) 
        # layer = QgsVectorLayer(self.fileName, "layer_name", "ogr")
 

        nFeat = layer.featureCount()
        layer.startEditing()

        

        # Should really put these in a function

        index = layer.fieldNameIndex("_lts")
        if index == -1: # field doesn't exist
            caps = layer.dataProvider().capabilities()
            if caps & QgsVectorDataProvider.AddAttributes:
              res = layer.dataProvider().addAttributes( [ QgsField("_lts", \
                QVariant.Int) ] )
            layer.updateFields()
        index = layer.fieldNameIndex("_num_lane")
        if index == -1: # field doesn't exist
            caps = layer.dataProvider().capabilities()
            if caps & QgsVectorDataProvider.AddAttributes:
              res = layer.dataProvider().addAttributes( [ QgsField("_num_lane", \
                QVariant.Int) ] )
            layer.updateFields()

        index = layer.fieldNameIndex("_protected")
        if index == -1: # field doesn't exist
            caps = layer.dataProvider().capabilities()
            if caps & QgsVectorDataProvider.AddAttributes:
              res = layer.dataProvider().addAttributes( [ QgsField("_protected", \
                QVariant.Int) ] )
            layer.updateFields()
        index = layer.fieldNameIndex("_bike_lane")
        if index == -1: # field doesn't exist
            caps = layer.dataProvider().capabilities()
            if caps & QgsVectorDataProvider.AddAttributes:
              res = layer.dataProvider().addAttributes( [ QgsField("_bike_lane", \
                QVariant.Int) ] )
            layer.updateFields()
        index = layer.fieldNameIndex("CROSSINGME")
        if index == -1: # field doesn't exist
            caps = layer.dataProvider().capabilities()
            if caps & QgsVectorDataProvider.AddAttributes:
              res = layer.dataProvider().addAttributes( [ QgsField("CROSSINGME", \
                QVariant.Int) ] )
            layer.updateFields()
        index = layer.fieldNameIndex("_lts11")
        if index == -1: # field doesn't exist
            caps = layer.dataProvider().capabilities()
            if caps & QgsVectorDataProvider.AddAttributes:
              res = layer.dataProvider().addAttributes( [ QgsField("_lts11", \
                QVariant.Int) ] )
            layer.updateFields()
        index = layer.fieldNameIndex("_lts12")
        if index == -1: # field doesn't exist
            caps = layer.dataProvider().capabilities()
            if caps & QgsVectorDataProvider.AddAttributes:
              res = layer.dataProvider().addAttributes( [ QgsField("_lts12", \
                QVariant.Int) ] )
            layer.updateFields()
        index = layer.fieldNameIndex("_lts13")
        if index == -1: # field doesn't exist
            caps = layer.dataProvider().capabilities()
            if caps & QgsVectorDataProvider.AddAttributes:
              res = layer.dataProvider().addAttributes( [ QgsField("_lts13", \
                QVariant.Int) ] )
            layer.updateFields()
        index = layer.fieldNameIndex("_lts_woX")
        if index == -1: # field doesn't exist
            caps = layer.dataProvider().capabilities()
            if caps & QgsVectorDataProvider.AddAttributes:
              res = layer.dataProvider().addAttributes( [ QgsField("_lts_woX", \
                QVariant.Int) ] )
            layer.updateFields()
        index = layer.fieldNameIndex("LTS")
        if index == -1: # field doesn't exist
            caps = layer.dataProvider().capabilities()
            if caps & QgsVectorDataProvider.AddAttributes:
              res = layer.dataProvider().addAttributes( [ QgsField("LTS", \
                QVariant.Int) ] )
            layer.updateFields()



        i=1
        featid_lts ={}
        for feature in layer.getFeatures():
            street = street_link_object()
            street.path_width = feature['PATHWIDTH']
            street.park_width = feature['PARKWIDTH']
            street.num_lane = feature['NUMLANE']
            street.f_code = feature['ROADCLASS']
            street.foc_width = feature['FOC_WIDTH']
            # street.median = feature['MEDIAN']
            street.speed_limit = feature['SPD_LIM']
            # street.pocket_lane = feature['RTLANE']
            street.illegial_parking = feature['ILLPARKING']
            street.center_line = feature['CL']
            street.net_type = feature['NET_TYPE']
            street.right_turn_speed=feature['RTSPEED']
            street.pocket_lane_shift = feature['RTLANSHIFT']
            street.right_turn_lane_length = feature['RTPOCKLENG']
            street.one_way = feature['ONEWAY']
            street.raw_cross_stress = feature['_rawCrossS']
            street.cross_treat = feature['CrossTreat']

            street.calculate_crossing_me(street.num_lane) # has to always be before computing lts
            street.compute_LTS()
            if street.LTS != None :
                i+=1
                j=ceil(i/(nFeat/100))
                self.dlg.ui.progress_bar.setValue(j)
            feature["_lts_woX"] = street.LTS
            feature["_lts"] = street.LTS
            feature["_lts11"] = street.lts11
            feature["_lts12"] = street.lts12
            feature["_lts13"] = street.lts13
            feature["_num_lane"] = street.num_lane
            feature["_bike_lane"] = street.bike_lane
            feature["_protected"] = street.protected
            feature["CROSSINGME"] = street.crossing_me
            layer.updateFeature(feature)
        # layer.updateFields()
        # QMessageBox.information(self.dlg, ("WAIT"), ("Please wait!"))
        layer.commitChanges()
            # layer.commitChanges()
        QMessageBox.information(self.dlg, ("Successful"), ("LTS has been computed!"))  

        self.dlg.close()


    def find_connected_components(self):
        """finds "islands" in the network """
        index = self.dlg.ui.layerCombo.currentIndex() 
        if index < 0: 
            # it may occur if there's no layer in the combo/legend 
            pass
        else: 
            layer = self.dlg.ui.layerCombo.itemData(index) 
        # layer = QgsVectorLayer(self.fileName, "layer_name", "ogr")


        index = self.dlg.ui.lts_combo.currentIndex() 
        if index < 0: 
            # it may occur if there's no layer in the combo/legend 
            pass
        else: 
            lts_column = self.dlg.ui.lts_combo.itemData(index) 
        # with open("C:\Users\Peyman.n\Dropbox\Boulder\Plugin\LTS\log.txt","w")as file:
        #     file.write(lts_column +"\n")
            
        lts1_existed = self.make_column(layer,"_isl_lts1")
        lts2_existed = self.make_column(layer,"_isl_lts2")
        lts3_existed = self.make_column(layer,"_isl_lts3")
        lts4_existed = self.make_column(layer,"_isl_lts4")
        # path = "C:/Users/Peyman.n/Dropbox/Boulder/BoulderStreetsRating_20140407_Peter/for_test.shp"
        # out_path = "C:/Users/Peyman.n/Dropbox/Boulder/BoulderStreetsRating_20140407_Peter"
        # get the path from selected layer
        myfilepath= os.path.dirname( unicode( layer.dataProvider().dataSourceUri() ) ) ;
        layer_name = layer.name()
        path2 = myfilepath +"/"+layer_name+".shp"
        out_path = myfilepath
        # with open("C:\Users\Peyman.n\Dropbox\Boulder\Plugin\LTS\log.txt","a")as file:
        #     file.write(path2 +"\n")
        # ##
        # path3="C:/Users/Peyman.n/Dropbox/Boulder/BoulderStreetsRating_20140407_Peter/BoulderStreetsWProjection_20140407_Joined.shp"
        layer2 = nx.read_shp(str(path2))
        self.dlg.ui.progressBar.setValue(5)
        G=layer2.to_undirected()
        self.dlg.ui.progressBar.setValue(10)
        lts_threshs = [(1,"_isl_lts1"),(2,"_isl_lts2"),(3,"_isl_lts3"),(4,"_isl_lts4")]
        field = str(lts_column)
        # with open("C:\Users\Peyman.n\Dropbox\Boulder\Plugin\LTS\log.txt","a")as file:
        #     file.write(field +"\n")
        prog =0
        for lts_thresh,attr in (lts_threshs):
            prog +=1
            temp = [(u,v,d) for u,v,d in G.edges_iter(data=True) if d[field] <= lts_thresh]  # set the edges numbers to zero
            g2 = nx.Graph(temp)
            H=nx.connected_component_subgraphs(g2)

            for idx, cc in enumerate(H):
                for edge in cc.edges(data=True):
                    G[edge[0]][edge[1]][attr]=idx+1 # zero means it was filtered out
            j= prog * 20
            self.dlg.ui.progressBar.setValue(j)

        # order attributes table
        for index, edge in enumerate (G.edges(data=True)):
            edge = list(edge)
            edge[2] = OrderedDict(sorted(edge[2].items()))
            edge=tuple(edge)
            G[edge[0]][edge[1]] = edge[2] 


        self.remove_column(layer,"_isl_lts1",lts1_existed)
        self.remove_column(layer,"_isl_lts2",lts2_existed)
        self.remove_column(layer,"_isl_lts3",lts3_existed)
        self.remove_column(layer,"_isl_lts4",lts4_existed)


        out_name =str(layer_name+"_with islands")
        write_shp(G,out_path,out_name)
        self.dlg.ui.progressBar.setValue(100)
        QMessageBox.information(self.dlg, ("Successful"), ("A new shapefile "+ out_name+" has been created in your folder"))  
        # Add to TOC
        vlayer = QgsVectorLayer(out_path +"/"+out_name+".shp",out_name,"ogr")
        #get crs of project
        actual_crs = iface.mapCanvas().mapRenderer().destinationCrs()
        #change crs of layer
        vlayer.setCrs(actual_crs)

        QgsMapLayerRegistry.instance().addMapLayer(vlayer)
        
        self.dlg.close()


    # run method that performs all the real work
    def run(self):
        # show the dialog
        self.dlg.show()
        self.dlg.ui.progress_bar.setValue(0)
        self.dlg.ui.progressBar.setValue(0)
        self.dlg.ui.layerCombo.clear()
        self.dlg.ui.lts_combo.clear()

        layers = QgsMapLayerRegistry.instance().mapLayers().values()
        for layer in layers:
            if layer.type() == QgsMapLayer.VectorLayer and layer.geometryType() == QGis.Line:
                self.dlg.ui.layerCombo.addItem( layer.name(), layer ) 

        self.update_lts_field()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result == 1:
            # do something useful (delete the line containing pass and
            # substitute with your code)
            pass


    def lets_Test(self):
        for feature in layer.getFeatures():
            numberOfLane = feature['NUMLANE']
            lts = feature ['_lts12']
            islLTS_1 = feature['_isl_lts1']
            islLTS_2 = feature['_isl_lts2'] 
            islLTS_3 = feature['_isl_lts3'] 
            islLTS_4 = feature['_isl_lts4'] 
            if lts ==1 : assert islLTS_1 > 0
            elif lts ==2 :
                assert islLTS_1 == 0
                assert islLTS_2 > 0
            elif lts ==3 :
                assert islLTS_1 == islLTS_2 == 0
                assert islLTS_3 > 0
            elif lts ==4 :
                assert islLTS_1 == islLTS_2 == islLTS_3 == 0
                assert islLTS_4 > 0



#############################################################################################################
class street_link_object(object):
    ''' object representing a link, with the goal of calculating its LTS'''
    def __init__(self):
        self.id = None
        self.center_line = None
        self.path_width=None
        self.f_code = None
        self.park_width = None 
        self.num_lane = None
        self.speed_limit = None
        self.illegial_parking = None
        self.foc_width = None
        self.protected = None
        self.override = None
        self.LTS = 1
        self.lts11 = 1
        self.lts12 = 1
        self.lts13 = 1
        self.cross_LTS=None
        self.bike_lane = None 
        self.cl_guess = None
        self.one_way = None
        self.net_type=None
        self.right_turn_lane_length = None
        self.pocket_lane_shift = None
        self.right_turn_speed = None
        self.multi_right_turn_lane = None
        self.crossing_me = 1
        self.raw_cross_stress = None
        self.cross_treat = None 



    def update_LTS(self, new_lts):
        ''' updates LTS if input is higher''' 
        if new_lts > self.LTS:
            self.LTS = new_lts


    def compute_num_lane(self):
        if self.one_way:  #it's not NULL
            self.num_lane = floor(self.num_lane/2)

    def compute_bke_lane(self):
        if self.net_type in ['PAVED SHOULDER','ON-STREET BIKE LANE','SINGLE BIKE LANE']:
            self.bike_lane =1
    def compute_protected(self):
        if self.net_type in ['MULTI-USE PATH','SIDEWALK CONNECTION','SS MULTI-USE PATH','CONNECTOR']:
            self.protected =1
        else:
            self.protected =0

    def calculate_crossing_me(self,number_of_lanes):
        num_lane = number_of_lanes
        if self.one_way in ["TF","FT"]:
            # street has a median
            if num_lane <= 3:
                if self.speed_limit <35:
                    pass
                elif self.speed_limit <=35:
                    #
                    self.crossing_me =2
                else:
                    
                    self.crossing_me = 3
            elif num_lane in [4,5]:
                if self.speed_limit <= 25:
                    pass
                elif self.speed_limit <=30:
                    
                    self.crossing_me = 2
                elif self.speed_limit <=35:
                    
                    self.crossing_me = 3
                else:
                   
                    self.crossing_me = 4
            else:
                if self.speed_limit<=25:
                   
                    self.crossing_me = 2
                elif self.speed_limit <=30:
                    
                    self.crossing_me = 3
                else:
                    
                    self.crossing_me = 4
        else:
            # no median refuge
            if num_lane <= 3:
                if self.speed_limit <35:
                    pass
                elif self.speed_limit <=35:
                    
                    self.crossing_me = 2
                else:
                   
                    self.crossing_me = 3
            elif num_lane in [4,5]:
                if self.speed_limit <= 25:
                    self.crossing_me = 2
                elif self.speed_limit <=30:
                    self.crossing_me = 2
                elif self.speed_limit <=35:
                    self.crossing_me = 3
                else:
                   
                    self.crossing_me = 4
            else:
                
                self.crossing_me = 4

    def compute_LTS(self):
        ''' Computes level of stress for each link'''

        ##############
        #saving original num lane for crossing calclations
        # orig_num_lane= self.num_lane
        ##############
        skip = False
        if (not self.one_way) or (self.one_way == "None"):  #it's 2 way 
            self.num_lane = floor(self.num_lane/2)
        #####
        # for now, cl_guess is always none
        if not self.center_line :  # if it's NULL
            self.center_line = self.cl_guess
        
        if self.net_type in ['MULTI-USE PATH','SIDEWALK CONNECTION','SS MULTI-USE PATH','CONNECTOR']:
            self.protected =1
        else:
            self.protected =0
        if self.net_type in ['PAVED SHOULDER','ON-STREET BIKE LANE','SINGLE BIKE LANE']:
            self.bike_lane =1
        else:
            self.bike_lane =0

        if self.cross_LTS != NULL:
            update_LTS(int(self.cross_LTS))

        if self.override != None:
            self.LTS = self.override
            skip = True

        if self.protected:
            self.LTS = 1
            self.crossing_me = 0
            skip = True
        ############################
        if not skip: 
            if self.bike_lane >0: # and NewBikeLnae  in [1,2]
                # it has a bike lane
                if self.park_width >0:
                    # has parking
                    assert self.path_width >= 4
                    reach = self.path_width + self.park_width
                    if self.num_lane >= 2:
                        #overrides the wide lane criteria
                        # self.LTS = max(3,self.LTS)
                        self.update_LTS(3)


                    # if self.f_code in [ local or private]: # 
                    if reach > 14.5:
                        pass # leave LTS unchanged
                    elif reach >= 14 :
                            # self.LTS = max(2, self.LTS)
                        self.update_LTS(2)
                    elif self.speed_limit <=25 or self.f_code in [ "LOCAL STR" ,"PRIVATE ST"]:
                            # self.LTS = max(3, self.LTS)
                        self.update_LTS(2)

                    else: 
                        self.update_LTS(3)

                else: 
                    # it has no parking
                    if self.num_lane <= 1:
                        pass
                    elif self.num_lane ==2 and self.one_way : # each side is two lanes
                        self.update_LTS(2)
                    else:
                        self.update_LTS(3)

                    # if self.f_code in ["RES, LOCAL STR"]: #remove
                    if self.path_width >= 6:
                        pass
                    else:
                        self.update_LTS(2)
                        
                    if self.speed_limit >= 40:
                        self.update_LTS(4)
                    elif self.speed_limit >= 35 :
                        self.update_LTS(3)
                    
                    if self.illegial_parking:
                        self.update_LTS(3)
                ###########################
            else: 
                # There is no bike lane
                if self.speed_limit <= 25:  # ALMOST EVERYTHING ENDS UP HERE
                    
                    if self.num_lane >= 3 :
                        self.update_LTS(4)
                    elif self.num_lane >=2 :
                        self.update_LTS(3)
                    elif self.f_code in [ "LOCAL STR" ,"PRIVATE ST"] and not self.center_line :
                        pass
                    else:
                        self.update_LTS(2)

                elif self.speed_limit <= 30 :
                    if self.num_lane >=2 :
                        self.update_LTS(4)
                    elif self.f_code in [ "LOCAL STR" ,"PRIVATE ST"] and not self.center_line :
                        self.update_LTS(2)
                    else:
                        self.update_LTS(3)
                
                else: 
                    self.update_LTS(4)
            ################################
                if self.right_turn_lane_length in [0 , None]:
                    pass
                elif self.multi_right_turn_lane:
                    self.update_LTS(4)
                elif self.right_turn_lane_length <= 150 and not self.pocket_lane_shift:
                    if self.right_turn_speed <= 15 :
                        self.update_LTS(2)
                    elif self.right_turn_speed <= 20:
                        self.update_LTS(3)
                    else:
                        self.update_LTS(4)
                elif self.right_turn_speed <= 15 :
                    self.update_LTS(3)
                else:
                    self.update_LTS(4)
            # return True

            ####################### Added on Apr 24. #######################################
        _temp = self.LTS
        _temp2 = max(self.LTS,self.raw_cross_stress)
        if self.cross_treat not in [11,12,13]:
            self.lts11 = _temp2
            self.lts12 = _temp2
            self.lts13 = _temp2
        elif self.cross_treat == 11:
            self.lts11 = _temp;
            self.lts12 = _temp
            self.lts13 = _temp
        elif self.cross_treat == 12:
            self.lts11 = _temp2;
            self.lts12 = _temp
            self.lts13 = _temp
        elif self.cross_treat == 13:
            self.lts11 = _temp2;
            self.lts12 = _temp2
            self.lts13 = _temp
    #############################################################################################################
    ##################### End of Street Class #####################
    #############################################################################################################

