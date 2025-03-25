#!/usr/bin/env python

from pyspatialite import dbapi2 as spatialite
from threading import Thread
import gislib
import time
import copy
import math
import geom

# ===============================================================================

# Starting search radius.  The actual radius is adjusted as we find / don't find
# caches.
STARTING_SEARCH_RADIUS = 1000 #m

# Automatically show cache within this distance regardless of the direction to 
# the cache.
CLOSE_RADIUS = 100 #m

# Maximum search radius.  Prevents search radius from growing indefinately.
MAXIMUM_RADIUS = 40000 #m

# When traveling above SPEED_THRESHOLD, return closest cache that is no more
# that this distance from the estimate path of travel.  This will approximately 
# return caches on your route when traveling along highways.
MAXIMUM_DISTANCE_FROM_PATH = 200 #m

# This speed threshold is used to switch between the slow speed searching 
# behaviour (look for closest cache in any direction) and the high speed
# behaviour (look for closest cache along path of travel).
SPEED_THRESHOLD = 60 #km/h

# ===============================================================================

class GeocacheFinder(Thread):
  def __init__(self, database_file, ping_func):
    Thread.__init__(self)
    self.daemon = True
    self.__bearing = 0
    self.__speed = 0
    self.__position = None
    self.__closest = None
    self.__database_file = database_file
    self.__radius = STARTING_SEARCH_RADIUS
    self.__ping_func = ping_func
    self.__paused = False

  def pause(self):
    self.__paused = True

  def unpause(self):
    self.__paused = False

  def update_speed(self, speed): #m/s
    self.__speed = speed

  def update_position(self, position): 
    self.__position = position

  def update_bearing(self, bearing):
    self.__bearing = bearing

  def closest(self):
    return copy.copy(self.__closest)

  def run(self):
    db = spatialite.connect(self.__database_file)
    while 1:
      while self.__paused: time.sleep(5)
      if (self.__position):
        self.__closest = self.__findNearest(db, self.__position, self.__bearing, self.__speed)
        self.__ping_func()

  def __findNearest(self, db, position, bearing, speed):
    while 1:
      result = self.__findNearest_helper(db, position[0], position[1], bearing, speed)
      if result:
        self.__radius = result['distance'] * 2;
        return result
      else:
        self.__radius *= 2
        if self.__radius > MAXIMUM_RADIUS: 
          self.__radius = MAXIMUM_RADIUS
          return None
        print "doubling radius", self.__radius

  def __findNearest_helper(self, db, lat, lon, bearing, speed):
    cur = db.cursor()

    # SQL to define a circle around the home point with a given radius
    circle = 'BuildCircleMbr(%f, %f, %f)' % (lat, lon, self.__radius / 111319.0)

    # SQL to calculate distance between geocache and home point
    dist = 'greatcirclelength(geomfromtext("linestring(" || x(location) || " " || y(location) || ", %f %f)", 4326))' % (lat, lon)

    # Query for caches within circle and order by distance
    rs = cur.execute('select code, description, x(location), y(location) from gc where MbrWithin(location, %(searchCircle)s)' % {'dist':dist, 'searchCircle':circle})

    data = []
    for row in rs:
      coord = (row[2], row[3])
      data.append({
        'code': row[0],
        'description': row[1],
        'distance': int(1000.0 * gislib.getDistance(coord, (lat, lon))),
        'bearing': gislib.calculateBearing(coord, (lat, lon)),
        'position': coord
        })

    if len(data) == 0: return None

    # sort by distance again since we aren't using the database distance
    # this should be removed if I switch back to using the Spatialite dist.
    data.sort(key=lambda x: x['distance'])

    # If first cache is within closeRadius return that 
    if data[0]['distance'] < CLOSE_RADIUS:
      print "cache within ", CLOSE_RADIUS, "m"
      return data[0] 

    # only right in front of us.
    if (speed < .2778 * SPEED_THRESHOLD): 
      print "slow speed", (speed / .2778), "km/h"
      return data[0]

    # sift through caches looking for closest one within our travel path
    for row in data:
      # look for caches within 200m of path of travel
      distanceFromPath = geom.distanceFromPath(bearing, row['bearing'], row['distance'])
      if distanceFromPath and distanceFromPath < MAXIMUM_DISTANCE_FROM_PATH:
        return row

      # look for cache within 30 degree arc.  This has dumb behaviour if dist is large
      #if gislib.isAngleWithin(bearing, row['bearing'], 15):
      #  return row

    return None

