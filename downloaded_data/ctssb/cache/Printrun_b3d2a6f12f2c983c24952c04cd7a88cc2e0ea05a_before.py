#!/usr/bin/env python
# This file is copied from GCoder.
#
# GCoder is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# GCoder is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Printrun.  If not, see <http://www.gnu.org/licenses/>.

import sys
import re
import math

def get_coordinate_value(axis, parts):
    for i in parts:
        if (axis in i):
            return float(i[1:])
    return None

def hypot3d(X1, Y1, Z1, X2 = 0.0, Y2 = 0.0, Z2 = 0.0):
    return math.hypot(X2-X1, math.hypot(Y2-Y1, Z2-Z1))

class Line(object):
    def __init__(self,l):
        self._x = None
        self._y = None
        self._z = None
        self.e = None
        self.f = 0
        
        self.regex = re.compile("[-]?\d+[.]?\d*")
        self.raw = l.upper().lstrip()
        self.imperial = False
        self.relative = False
        self.relative_e = False
        
        if ";" in self.raw:
            self.raw = self.raw.split(";")[0]
        
        self._parse_coordinates()
        
    def _to_mm(self,v):
        if v and self.imperial:
            return v*25.4
        return v
        
    def _getx(self):
        return self._to_mm(self._x)
            
    def _setx(self,v):
        self._x = v

    def _gety(self):
        return self._to_mm(self._y)

    def _sety(self,v):
        self._y = v

    def _getz(self):
        return self._to_mm(self._z)

    def _setz(self,v):
        self._z = v

    def _gete(self):
        return self._to_mm(self._e)

    def _sete(self,v):
        self._e = v

    x = property(_getx,_setx)
    y = property(_gety,_sety)
    z = property(_getz,_setz)
    e = property(_gete,_sete)
    
        
    def command(self):
        try:
            return self.raw.split(" ")[0]
        except:
            return ""
            
    def _get_float(self,which):
        try:
            return float(self.regex.findall(self.raw.split(which)[1])[0])
        except:
            return None
        
    def _parse_coordinates(self):
        try:
            if "X" in self.raw:
                self._x = self._get_float("X")
        except:
            pass

        try:
            if "Y" in self.raw:
                self._y = self._get_float("Y")
        except:
            pass
            
        try:
            if "Z" in self.raw:
                self._z = self._get_float("Z")
        except:
            pass
            
        try:
            if "E" in self.raw:
                self.e = self._get_float("E")
        except:
            pass
            
        try:
            if "F" in self.raw:
                self.f = self._get_float("F")
        except:
            pass
            
        
    def is_move(self):
        return self.command() and ("G1" in self.raw or "G0" in self.raw)
        
        
    def __str__(self):
        return self.raw
        
class Layer(object):
    def __init__(self,lines):
        self.lines = lines
        
        
    def measure(self):
        xmin = float("inf")
        ymin = float("inf")
        zmin = 0
        xmax = float("-inf")
        ymax = float("-inf")
        zmax = float("-inf")
        relative = False
        relative_e = False

        current_x = 0
        current_y = 0
        current_z = 0

        for line in self.lines:
            if line.command() == "G92":
                current_x = line.x or current_x
                current_y = line.y or current_y
                current_z = line.z or current_z    

            if line.is_move():
                x = line.x 
                y = line.y
                z = line.z

                if line.relative:
                    x = current_x + (x or 0)
                    y = current_y + (y or 0)
                    z = current_z + (z or 0)


                if x and line.e:
                    if x < xmin:
                        xmin = x
                    if x > xmax:
                        xmax = x
                if y and line.e:
                    if y < ymin:
                        ymin = y
                    if y > ymax:
                        ymax = y
                if z:
                    if z < zmin:
                        zmin = z
                    if z > zmax:
                        zmax = z

                current_x = x or current_x
                current_y = y or current_y
                current_z = z or current_z

        return ( (xmin,xmax),(ymin,ymax),(zmin,zmax) )
    

class GCode(object):
    def __init__(self,data):
        self.lines = [Line(i) for i in data]
        self._preprocess()
        self._create_layers()

    def _preprocess(self):
        #checks for G20, G21, G90 and G91, sets imperial and relative flags
        imperial = False
        relative = False
        relative_e = False
        for line in self.lines:
            if line.command() == "G20":
                imperial = True
            elif line.command() == "G21":
                imperial = False
            elif line.command() == "G90":
                relative = False
                relative_e = False
            elif line.command() == "G91":
                relative = True
                relative_e = True
            elif line.command() == "M82":
                relative_e = False
            elif line.command() == "M83":
                relative_e = True
            elif line.is_move():
                line.imperial = imperial
                line.relative = relative
                line.relative_e = relative_e
        
    def _create_layers(self):
        self.layers = []

        prev_z = None
        cur_z = 0
        cur_lines = []
        layer_index = []
        
        temp_layers = {}
        for line in self.lines:
            if line.command() == "G92" and line.z != None:
                cur_z = line.z
            elif line.is_move():
                if line.z != None:
                    if line.relative:
                        cur_z += line.z
                    else:
                        cur_z = line.z
                    
            if cur_z != prev_z:
                old_lines = temp_layers.pop(prev_z,[])
                old_lines += cur_lines
                temp_layers[prev_z] = old_lines

                if not prev_z in layer_index:
                    layer_index.append(prev_z)
                    
                cur_lines = []
            
            cur_lines.append(line)
            prev_z = cur_z
        
        
        old_lines = temp_layers.pop(prev_z,[])
        old_lines += cur_lines
        temp_layers[prev_z] = old_lines

        if not prev_z in layer_index:
            layer_index.append(prev_z)
            
        layer_index.sort()
        
        for idx in layer_index:
            cur_lines = temp_layers[idx]
            has_movement = False
            for l in cur_lines:
                if l.is_move() and l.e != None:
                    has_movement = True
                    break
            
            if has_movement:
                self.layers.append(Layer(cur_lines))
            

    def num_layers(self):
        return len(self.layers)
                

    def measure(self):
        xmin = float("inf")
        ymin = float("inf")
        zmin = 0
        xmax = float("-inf")
        ymax = float("-inf")
        zmax = float("-inf")

        for l in self.layers:
            xd, yd, zd = l.measure()
            xmin = min(xd[0], xmin)
            xmax = max(xd[1], xmax)
            ymin = min(yd[0], ymin)
            ymax = max(yd[1], ymax)
            zmin = min(zd[0], zmin)
            zmax = max(zd[1], zmax)

        self.xmin = xmin
        self.xmax = xmax
        self.ymin = ymin
        self.ymax = ymax
        self.zmin = zmin
        self.zmax = zmax
        self.width = xmax - xmin
        self.depth = ymax - ymin
        self.height = zmax - zmin
    
    def filament_length(self):
        total_e = 0        
        cur_e = 0
        
        for line in self.lines:
            if line.e != None:
                continue
            if line.command() == "G92":
                cur_e = line.e
            elif line.is_move():
                if line.relative_e:
                    total_e += line.e
                else:
                    total_e += line.e - cur_e
                    cur_e = line.e

        return total_e

    def estimate_duration(self, g):
        lastx = lasty = lastz = laste = lastf = 0.0
        x = y = z = e = f = 0.0
        currenttravel = 0.0
        totaltravel = 0.0
        moveduration = 0.0
        totalduration = 0.0
        acceleration = 1500.0 #mm/s/s  ASSUMING THE DEFAULT FROM SPRINTER !!!!
        layerduration = 0.0
        layerbeginduration = 0.0
        layercount = 0
        #TODO:
        # get device caps from firmware: max speed, acceleration/axis (including extruder)
        # calculate the maximum move duration accounting for above ;)
        # self.log(".... estimating ....")
        for i in g:
            i = i.split(";")[0]
            if "G4" in i or "G1" in i:
                if "G4" in i:
                    parts = i.split(" ")
                    moveduration = get_coordinate_value("P", parts[1:])
                    if moveduration is None:
                        continue
                    else:
                        moveduration /= 1000.0
                if "G1" in i:
                    parts = i.split(" ")
                    x = get_coordinate_value("X", parts[1:])
                    if x is None: x = lastx
                    y = get_coordinate_value("Y", parts[1:])
                    if y is None: y = lasty
                    z = get_coordinate_value("Z", parts[1:])
                    if (z is None) or  (z<lastz): z = lastz # Do not increment z if it's below the previous (Lift z on move fix)
                    e = get_coordinate_value("E", parts[1:])
                    if e is None: e = laste
                    f = get_coordinate_value("F", parts[1:])
                    if f is None: f = lastf
                    else: f /= 60.0 # mm/s vs mm/m

                    # given last feedrate and current feedrate calculate the distance needed to achieve current feedrate.
                    # if travel is longer than req'd distance, then subtract distance to achieve full speed, and add the time it took to get there.
                    # then calculate the time taken to complete the remaining distance

                    currenttravel = hypot3d(x, y, z, lastx, lasty, lastz)
                    distance = abs(2* ((lastf+f) * (f-lastf) * 0.5 ) / acceleration)  #2x because we have to accelerate and decelerate
                    if distance <= currenttravel and ( lastf + f )!=0 and f!=0:
                        moveduration = 2 * distance / ( lastf + f )
                        currenttravel -= distance
                        moveduration += currenttravel/f
                    else:
                        moveduration = math.sqrt( 2 * distance / acceleration )

                totalduration += moveduration

                if z > lastz:
                    layercount +=1
                    #self.log("layer z: ", lastz, " will take: ", time.strftime('%H:%M:%S', time.gmtime(totalduration-layerbeginduration)))
                    layerbeginduration = totalduration

                lastx = x
                lasty = y
                lastz = z
                laste = e
                lastf = f

        #self.log("Total Duration: " #, time.strftime('%H:%M:%S', time.gmtime(totalduration)))
        return "{0:d} layers, ".format(int(layercount)) + str(datetime.timedelta(seconds = int(totalduration)))

def main():
    if len(sys.argv) < 2:
        print "usage: %s filename.gcode" % sys.argv[0]
        return

#    d = [i.replace("\n","") for i in open(sys.argv[1])]
#    gcode = GCode(d)
    d = list(open(sys.argv[1]))
    gcode = GCode(d) 
    
    gcode.measure()

    print "Dimensions:"
    print "\tX: %0.02f - %0.02f (%0.02f)" % (gcode.xmin,gcode.xmax,gcode.width)
    print "\tY: %0.02f - %0.02f (%0.02f)" % (gcode.ymin,gcode.ymax,gcode.depth)
    print "\tZ: %0.02f - %0.02f (%0.02f)" % (gcode.zmin,gcode.zmax,gcode.height)
    print "Filament used: %0.02fmm" % gcode.filament_length()
    print "Number of layers: %d" % gcode.num_layers()
    print "Estimated duration (pessimistic): ", gcode.estimate_duration(d)


if __name__ == '__main__':
    main()
