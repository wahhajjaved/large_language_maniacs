import os
import copy
import json
import time
import string

import arena
import scheduler

class Simulator:
    _chr2dir = { 
                'w': 0,
                'e': 45,
                'd': 90,
                'c': 135,
                'x': 180,
                'z': 225,
                'a': 270,
                'q': 315
                }
    
    def __init__(self, arena):
        self._arena = copy.deepcopy(arena)
        self._init_command_values(self._arena.airplanes.values())
        
    def update(self, buf):
        self._arena.clock += 1
        # buf might contain airplane updates from files
        # Simulator will add his stuff and return a combined update JSON
        if len(buf) > 0:
            update_data = json.loads(buf)
            update_data['clock'] = self._arena.clock
        else:
            update_data = { 'clock': self._arena.clock, 'airplanes': [] }
        
        # add existing planes or _arena.update() would delete them
        for a in self._arena.airplanes.values():
            for a2 in update_data['airplanes']:
                if a.id == a2.id:
                    raise Exception("input file tried to override airplane " + str(a))
                if not a2.id in self._arena.airplanes:
                    self._init_command_values([a2])
            
            update_data['airplanes'].append({
                                             'id': a.id,
                                             'x': a.x,
                                             'y': a.y,
                                             'alt': a.z,
                                             'dir': a.dir,
                                             'fuel': a.fuel,
                                             'dest': a.dest.name()
                                             })
                
        json_str = json.dumps(update_data)
        self._arena.update(json_str)

        json_update = self._step()
        
        return json_update
    
    def _init_command_values(self, airplanes):
        for a in airplanes:
            a.new_altitude = a.z
            a.new_dir = a.dir
    
    def _step(self):
        result = { 'clock': self._arena.clock, 'airplanes': [] }
        
        deletion_queue = []
        for a in self._arena.airplanes.values():
            if self._arena.clock % a.speed == 0:
                old_z = a.z
                # update altitude
                if a.new_altitude > a.z and a.z < 9:
                    a.z += 1
                elif a.new_altitude < a.z and a.z > 0:
                    a.z -= 1
                
                # update fuel
                if a.z > 0:
                    a.fuel -= 1
                    if a.fuel <= 0:
                        raise Exception("Airplane " + str(a) + " ran out of fuel.")
                
                # update direction
                if a.new_dir != a.dir:
                    if old_z == 0:
                        raise Exception("can't change direction while grounded")
                    
                    for angle in range(45, 360, 45):
                        if (a.dir + angle) % 360 == a.new_dir:
                            if angle > 180:
                                # turn left
                                a.dir -= min(angle, 90)
                            else:
                                # turn right
                                a.dir += min(angle, 90)
                            a.dir %= 360
                            break
                    else:
                        raise Exception("internal error: can't find turning angle")
                
                # move
                if a.z > 0:
                    p = a.step()
                    a.x = p.x
                    a.y = p.y
                    a.z = p.z
                
                # destination reached?
                if a.equals(a.dest):
                    deletion_queue.append(a)
                    print "SIMULATOR: airplane " + str(a) + " reached its destination " + a.dest.name()
                    continue
                    
                # check validity
                if a.z < 1 and old_z > 0:
                    raise Exception("Airplane " + str(a) + " hit the ground")
                if a.x < 1 or a.x >= self._arena.width - 1 \
                or a.y < 1 or a.y >= self._arena.height - 1:
                    raise Exception("Airplane " + str(a) + " illegally left the flight zone")
                
            # append to json data
            result['airplanes'].append({
                                        'id': a.id,
                                        'x': a.x,
                                        'y': a.y,
                                        'alt': a.z,
                                        'dir': a.dir,
                                        'fuel': a.fuel,
                                        'dest': a.dest.name()
                                        })
        
        for a in deletion_queue:
            del(self._arena.airplanes[a.id])
        
        # check collision
        for a in self._arena.airplanes.values():
            for a2 in self._arena.airplanes.values():
                if a2 is a or a2.z == 0:
                    continue
                if a2.is_collision(a):
                    raise Exception("Airplane " + str(a) + " collided with " + str(a2))
        
        return json.dumps(result)
        
    def send(self, commands):
        for c in string.split("\n", commands):
            self._apply_command(c)
            
    def _apply_command(self, command):
        if len(command) != 3:
            raise ValueError("Simulator received command '" + command + "' with invalid length (exptected: 3)")

        plane_id = command[0]
        ctype = command[1]
        arg = command[2]
        
        if not plane_id in self._arena.airplanes:
            raise ValueError("Can not apply command '" + command + "' for unknown airplane " + plane_id)

        if ctype == 'a':
            self._cmd_altitude(plane_id, int(arg))
        elif ctype == 't':
            if arg not in self._chr2dir:
                raise ValueError("unknown direction '" + arg + "' in command '" + command + "'")
            self._cmd_direction(plane_id, self._chr2dir[arg])
        else:
            raise ValueError("command '" + command + "' unknown, e.g. '" + ctype + "'")
        
    def _cmd_altitude(self, plane_id, altitude):
        self._arena.airplanes[plane_id].new_altitude = altitude
        
    def _cmd_direction(self, plane_id, direction):
        self._arena.airplanes[plane_id].new_dir = direction

if __name__ == '__main__':
    dir = '/home/rha/projects/atc/test-json/collision3'
    i = 0
    while True:
        i += 1
        time.sleep(1)
        filename = dir + "/p" + str(i) + ".json"
        
        if os.path.exists(filename):
            try:
                fil = open(filename, 'r')
                buf = fil.read()
                fil.close()
            
            except IOError as err:
                print "Error: reading file failed"
                exit(1)

        elif i == 1:
            raise Exception("Fatal: need initial arena: " + filename + " not found.")
        else:
            buf = ""
    
        if i == 1:
            #buf = con.read() # read arena
            arena = arena.Arena(buf)
            simul = Simulator(arena)
            sched = scheduler.Scheduler(arena, simul)
            
        else:
            buf = simul.update(buf)
            arena.update(buf)

        sched.update()