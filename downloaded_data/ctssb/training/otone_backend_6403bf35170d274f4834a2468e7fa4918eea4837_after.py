import json, os

import smoothie_ser2net as openSmoothie

from the_queue import TheQueue
from file_io import FileIO
from pipette import Pipette


debug = True
verbose = True

class Head:
    """
    A representation of the robot head
    
    The Head class is intended to be instantiated to a head object which
    aggregates the subclassed tool objects and the smoothieAPI object.
    It also hold a references to theQueue and publisher objects.
    Appropriate methods are exposed to allow access to the aggregated object's
    functionality.

    :todo:
    1. Figure out if :meth:`move_plunger` is redundant and refactor accordingly
    2. Should :obj:`theState` be updated BEFORE the actions taken from given state?
    3. Is :meth:`create_deck` redundant?
    4. Is :meth:`create_pipettes` needed?
    """
    
#Special Methods-----------------------
    #def __init__(self, tools, global_handlers, theQueue):
    def __init__(self, tools, publisher):
        """
        Initialize Head object
        
        tools = dictionary of the tools on the head
        
        """
        if debug == True: FileIO.log('head.__init__ called')
        self.smoothieAPI = openSmoothie.Smoothie(self)
        self.PIPETTES = {'a':Pipette('a'),'b':Pipette('b')}    #need to create this dict in head setup
        self.tools = tools
        self.pubber = publisher
        self.smoothieAPI.set_raw_callback(self.pubber.on_raw_data)
        self.smoothieAPI.set_limit_hit_callback(self.pubber.on_limit_hit)
        self.smoothieAPI.set_move_callback(self.pubber.on_start)
        self.theQueue = TheQueue(self, publisher)
        
        #connect with the smoothie board
        self.smoothieAPI.connect()
        self.path = os.path.abspath(__file__)
        self.dir_path = os.path.dirname(self.path)        

        self.load_pipette_values()
        
    def __str__(self):
        return "Head"
        
    def __repr__(self):
        return "Head({0!r})".format(self.tools.keys())
        
# the current coordinate position, as reported from 'smoothie.js'
    theState = {'x' : 0,'y' : 0,'z' : 0,'a' : 0,'b' : 0}

    # this function fires when 'smoothie.js' transitions between {stat:0} and {stat:1}
    #SMOOTHIEBOARD.on_state_change = function (state) {
    def on_state_change(self, state):
        """
        Check the given state (from Smoothieboard) and engage :obj:`theQueue` (:class:`the_queue`) accordingly

        If the state is 1 or the state.delaying is 1 then :obj:`theQueue` is_busy,

        else if the state is 0 and the state.delaying is 0, :obj:`theQueue` is not busy, 
        clear the currentCommand for the next one, and if not paused, tell :obj:`theQueue` 
        to step. Then update :obj:`theState`.

        :todo:
        2. Should :obj:`theState` be updated BEFORE the actions taken from given state?
        """
        if debug == True: FileIO.log('head.on_state_change called')
        
        if state['stat'] == 1 or state['delaying'] == 1:
            self.theQueue.is_busy = True

        elif state['stat'] == 0 and state['delaying'] == 0:
            self.theQueue.is_busy = False
            self.theQueue.currentCommand = None
            if self.theQueue.paused==False:
                self.theQueue.step(False)
    
        self.theState = state
        if debug == True and verbose == True: FileIO.log('\n\n\tHead state:\n\n',self.theState,'\n')


#local functions---------------
    def get_tool_type(self, head_tool):
        """
        Get the tooltype and axis from head_tool dict
        
        :returns: (tool_type, axis)
        :rtype: tuple
        """
        if debug == True: FileIO.log('head.get_tool_info called')
        tool_type = head_tool['tool']
        axis = head_tool['axis']
        
        return (tool_type, axis)
        
        
        
#Methods-----------------------
    def configure_head(self, head_data):
        """
        Configure the head per Head section of protocol.json file
        
        
        :example head_data:

        head_data = dictionary of head data (example below):
            "p200" : {
                "tool" : "pipette",
                "tip-racks" : [{"container" : "p200-rack"}],
                "trash-container" : {"container" : "trash"},
                "tip-depth" : 5,
                "tip-height" : 45,
                "tip-total" : 8,
                "axis" : "a",
                "volume" : 160
            },
            "p1000" : {
                "tool" : "pipette",
                "tip-racks" : [{"container" : "p1000-rack"}],
                "trash-container" : {"container" : "trash"},
                "tip-depth" : 7,
                "tip-height" : 65,
                "tip-total" : 8,
                "axis" : "b",
                "volume" : 800
            }
        """
        if debug == True: 
            FileIO.log('head.configure_head called')
            if verbose == True: FileIO.log('\targs: ',head_data,'\n')
        #delete any previous tools in head
        del self.tools
        self.tools = []
        #instantiate a new tool for each name and tool type in the file
        #ToDo - check for data validity before using

        for key in head_data:
            hd = head_data[key]
            #get the tool type to know what kind of tool to instantiate
            tool_type = self.get_tool_type(hd)  #tuple (toolType, axis)
            print('tool_type...'+tool_type[0])
            if tool_type[0] == 'pipette':
                #newtool = Pipette(hd['axis'])
                #pass
                #self.PIPETTES[hd['axis']] = newtool
                setattr(self.PIPETTES[hd['axis']],'tip_racks',hd['tip-racks'])
                if len(hd['tip-racks'])>0:
                    tpOD = hd['tip-racks'][0]
                    tpItems = tpOD.items()
                    listTPItems = list(tpItems)
                    setattr(self.PIPETTES[hd['axis']],'tip_rack_origin',listTPItems[0][1])


                setattr(self.PIPETTES[hd['axis']],'trash_container',hd['trash-container'])
            elif tool_type[0] == 'grabber':
                #newtool = Grabber(key,*tool_info)
                pass
            else:
                #ToDo - add error handling here
                pass
            
            #add tool to the tools list
            #self.tools.append(newtool)




        

        #fill the PIPETTES object with tools of the tool type 'pipette'
        #for tool in self.tools:
        #    print('from line 545 in head: ',tool,type(tool))
        #    if tool.tooltype == 'pipette':
        #        print('tooltype called')
        #        axis = tool.axis
        #        if 'tip-racks' in tool:
        #            self.PIPETTES[axis].calibrate('tip_racks',head_data[key]['tip-racks'])
        #        self.PIPETTES[axis] = Pipette(axis)
        #        if 'tip-racks' in tool:
        #            self.PIPETTES[axis].calibrate('tip_racks',head_data['tip-racks'])

        self.save_pipette_values()
        self.publish_calibrations()


    def relative_coords(self):
        for axis in self.PIPETTES:
            self.PIPETTES[axis].relative_coords()
        self.save_pipette_values()
        self.publish_calibrations()
        
    #this came from pipette class in js code
    def create_pipettes(self, axis):
        """
        Create and return a dictionary of Pipette objects

        :returns: A dictionary of pipette objects
        :rtype: dictionary
        
        :note: Seems nothing calls this...

        :todo:
        4. Is :meth:`create_pipettes` needed?
        """
        if debug == True: FileIO.log('head.create_pipettes called')
        thePipettes = {}
        if len(axis):
            for a in axis:
            #for i in range(0,len(axis)):
                #a = axis(i)
                thePipettes[a] = Pipette(a)
                
        return thePipettes
        
        
    #Command related methods for the head object
    #corresponding to the exposed methods in the Planner.js file
    #from planner.js
    def home(self, axis_dict):   #, callback):
        """
        Home robot according to axis_dict
        """
        #maps to smoothieAPI.home()
        #print('{} msg received in head, calling home on smoothie'.format(axis_dict))
        if debug == True:
            FileIO.log('head.home called, args: ',axis_dict)
        
        self.smoothieAPI.home(axis_dict)
        
        
    #from planner.js
    def raw(self, string):
        """
        Send a raw command to the Smoothieboard
        """
        if debug == True: FileIO.log('head.raw called')
        #maps to smoothieAPI.raw()
        #function raw(string)
        self.smoothieAPI.raw(string)
        
        
    #from planner.js
    def kill(self):
        """
        Halt the Smoothieboard (M112) and clear the the object (:class:`the_queue`)
        """
        if debug == True: FileIO.log('head.kill called')
        #maps to smoothieAPI.halt() with extra code
#        print('{} msg received in head, calling halt on smoothie'.format(data))
        self.smoothieAPI.halt()
        self.theQueue.clear();

    #from planner.js
    def reset(self):
        """
        Reset the Smoothieboard and clear theQueue object (:class:`the_queue`)
        """
        if debug == True: FileIO.log('head.reset called')
        #maps to smoothieAPI.reset() with extra code
        self.smoothieAPI.reset()
        self.theQueue.clear();
        
        
    #from planner.js
    def get_state(self):
        """
        Get state information from Smoothieboard
        """
        if debug == True: FileIO.log('head.get_state called')
        #maps to smoothieAPI.get_state()
        #function get_state ()
        return self.smoothieAPI.get_state()
        
        
        #from planner.js
    def set_speed(self, axis, value):
        """
        Set the speed for given axis to given value
        """
        if debug == True: FileIO.log('head.set_speed called')
        
        #maps to smoothieAPI.set_speed()
        #function setSpeed(axis, value, callback)
        self.smoothieAPI.set_speed(axis, value)
        
        
        #from planner.js
        #function move (locations)
        #doesn't map to smoothieAPI
    def move(self, locations):
        """
        Moves the head by adding locations to theQueue



        var locations = [location,location,...]

        var location = {
        'relative' : true || false || undefined (defaults to absolute)
        'x' : 30,
        'y' : 20,
        'z' : 10,
        'a' : 20,
        'b' : 32
        }

        """
        if debug == True: FileIO.log('head.move called')
        if locations:
            if debug == True and verbose == True:
                FileIO.log('locations:\n',locations)
            self.theQueue.add(locations)
        
    #from planner.js
    #function step (locations)
    #doesn't map to smoothieAPI
    def step(self, locations):
        """
        Step to the next command in theQueue(:class:`the_queue`) object's qlist

        
        locations = [location,location,...]

        location = {
        'x' : 30,
        'y' : 20,
        'z' : 10,
        'a' : 20,
        'b' : 32
        }
        """
        if debug == True:
            FileIO.log('head.step called')
            if verbose == True: 
                FileIO.log('\tlocations:\n\n',locations,'\n')
                # only step with the UI if the queue is currently empty
                FileIO.log('head:\n\tlen(self.theQueue.qlist): ',len(self.theQueue.qlist),'\n')
                FileIO.log('head:\n\tself.theQueue.is_busy?: ',self.theQueue.is_busy,'\n')
        if len(self.theQueue.qlist)==0: # and self.theQueue.is_busy==False:

            if locations is not None:
                if isinstance(locations,list):
#                    for( i = 0; i < locations.length; i++):
                    for i in range(len(locations)):
                        locations[i]['relative']  = True
                        
                elif ('x' in locations) or ('y' in locations) or ('z' in locations) or ('a' in locations) or ('b' in locations):
                    locations['relative']  = True
                    
                self.move(locations)
         
         
    #from planner.js
    #function pipette(group)
    def pipette(self, group):
        """
        Run a pipette operation based on a given Group from protocol instructions


        group = {
          command : 'pipette',
          axis : 'a' || 'b',
          locations : [location, location, ...]
        }
    
        location = {
          x : number,
          y : number,
          z : number,
          container : string,
          plunger : float || 'blowout' || 'droptip'
        }
    
        If no container is specified, XYZ coordinates are absolute to the Smoothieboard
        if a container is specified, XYZ coordinates are relative to the container's origin 
        (180 degree rotation around X axis, ie Z and Y +/- flipped)
        
        """
        if debug == True: FileIO.log('head.pipette called')
        if group and 'axis' in group and group['axis'] in self.PIPETTES and 'locations' in group and len(group['locations'])>0:
    
            this_axis = group['axis']  
            current_pipette = self.PIPETTES[this_axis]  
    
            # the array of move commands we are about to build from each location
            # starting with this pipette's initializing move commands
            move_commands = current_pipette.init_sequence()
            if debug == True and verbose == True:
                FileIO.log('\nhead.pipette\n\tcurrent_pipette.init_sequence():\n\n',current_pipette.init_sequence(),'\n')
                FileIO.log('\nhead.pipette\n\tmove_commands:\n\n',move_commands,'\n')
    
            # loop through each location
            # using each pipette's calibrations to test and convert to absolute coordinates
            for i in range(len(group['locations'])) :
    
                thisLocation = group['locations'][i]  
    
                # convert to absolute coordinates for the specifed pipette axis
                if debug == True: FileIO.log('head.pipette:\n\tlocation: ',thisLocation,'\n')
                absCoords = current_pipette.pmap(thisLocation)  
    
                # add the absolute coordinates we just made to our final array
                move_commands.extend(absCoords)  
    
            if len(move_commands):
                move_commands.extend(current_pipette.end_sequence())  
                self.move(move_commands)  
      
    
    #from planner.js
    def calibrate_pipette(self, pipette, property_):
        """
        Sets the value of a property for given pipette by fetching state information 
        from smoothieboard(:meth:`smoothie_ser2net.get_state`)
        """
        if debug == True: FileIO.log('head.calibrate_pipette called')
        #maps to smoothieAPI.get_state() with extra code
        if pipette and self.PIPETTES[pipette]: 
            state = self.smoothieAPI.get_state()
            # firststop, bottom to delete
            if property_=='top' or property_=='blowout' or property_=='droptip':
                value = state[pipette]  
                self.PIPETTES[pipette].calibrate(property_,value)  
                #self.save_pipette_values()  


    def calibrate_container(self, pipette, container):   
        """
        Set the location of a container
        """
        if debug == True: FileIO.log('head.calibrate_container called')
        if pipette and self.PIPETTES[pipette]:     
            state = self.smoothieAPI.get_state()
            self.PIPETTES[pipette].calibrate_container(container,state)

             
    def save_volume(self, data):
        """
        Save pipette volume to data/pipette_values.json
        """
        if debug == True: FileIO.log('head.save_volume called')
        if(self.PIPETTES[data.axis] and data.volume is not None and data.volume > 0):
            self.PIPETTES[data.axis].volume = data.volume
            
        self.save_pipette_values()
        
        
    #from planner.js
    def save_pipette_values(self):
        """
        Save pipette values to data/pipette_values.json
        """
        if debug == True: FileIO.log('head.save_pipette_values called')
        pipette_values = {}

        for axis in self.PIPETTES:
            pipette_values[axis] = {}
            for k, v in self.PIPETTES[axis].__dict__.items():
                pipette_values[axis][k] = v

            # should include:
            #  'top'
            #  'bottom'
            #  'blowout'
            #  'droptip'
            #  'volume'
            #  'theContainers'

        filetext = json.dumps(pipette_values,sort_keys=True,indent=4,separators=(',',': '))
        if debug == True: FileIO.log('filetext: ', filetext)
        
        filename = os.path.join(self.dir_path,'data/pipette_calibrations.json')

        # save the pipette's values to a local file, to be loaded when the server restarts
        FileIO.writeFile(filename,filetext,lambda: FileIO.onError('\t\tError saving the file:\r\r'))      


    #from planner.js
    #fs.readFile('./data/pipette_calibrations.json', 'utf8', function (err,data)
    #load_pipette_values()
    def load_pipette_values(self):
        """
        Load pipette values from data/pipette_calibrations.json
        """
        if debug == True: FileIO.log('head.load_pipette_values called')
        old_values = FileIO.get_dict_from_json(os.path.join(self.dir_path,'data/pipette_calibrations.json'))
        if debug == True: FileIO.log('old_values:\n',old_values,'\n')
        
        if self.PIPETTES is not None and len(self.PIPETTES) > 0:
            for axis in old_values:
                #for n in old_values[axis]:
                for k, v in old_values[axis].items():
                    self.PIPETTES[axis].__dict__[k] = v

                    # should include:
                    #  'resting'
                    #  'top'
                    #  'bottom'
                    #  'blowout'
                    #  'droptip'
                    #  'volume'
                    #  'theContainers'
            
            if debug == True: FileIO.log('self.PIPETTES[',axis,']:\n\n',self.PIPETTES[axis],'\n')
        else:
            if debug == True: FileIO.log('head.load_pipette_values: No pipettes defined in PIPETTES')
            
    #from planner.js
    # an array of new container names to be stored in each pipette
    #ToDo: this method may be redundant
    def create_deck(self, new_deck):
        """
        Create a dictionary of new container names to be stored in each pipette given a deck list

        Calls :meth:`head.save_pipette_values` right before returning dictionary

        :returns: container data for each axis
        :rtype: dictionary
        
        :todo:
        3. Is :meth:`create_deck` redundant?
        """
        if debug == True: 
            FileIO.log('head.create_deck called')
            if verbose == True:
                FileIO.log('\tnewDeck:\n\n', new_deck,'\n')
        
        #doesn't map to smoothieAPI
        nameArray = []  

        for containerName in new_deck :
            nameArray.append(containerName) 
        
        response = {}  
        
        for n in self.PIPETTES:
            response[n] = self.PIPETTES[n].create_deck(nameArray)  

        self.save_pipette_values() 
        return response         
            
            
    def get_deck(self):
        """
        Get a dictionary of container names currently stored in each pipette

        Calls :meth:`head.save_pipette_values` right before returning dictionary

        :returns: container data for each axis
        :rtype: dictionary
        
        """
        if debug == True: FileIO.log('head.get_deck called')
        response = {}
        for axis in self.PIPETTES:
            response[axis] = {}
            if debug == True: FileIO.log('self.PIPETTES[',axis,'].theContainers:\n\n',self.PIPETTES[axis].theContainers)
            for name in self.PIPETTES[axis].theContainers:
                if debug == True: FileIO.log('self.PIPETTES[',axis,'].theContainers[',name,']:\n\n',self.PIPETTES[axis].theContainers[name])
                response[axis][name] = self.PIPETTES[axis].theContainers[name]
  
        self.save_pipette_values()

        if debug == True: FileIO.log('head.get_deck response:\n\n',response)
        return response


    def get_pipettes(self):
        """
        Get a dictionary of pipette properties for each pipette on head

        :returns: Pipette properties for each pipette
        :rtype: dictionary
        
        """
        if debug == True: FileIO.log('head.get_pipettes called')
        response = {}

        for axis in self.PIPETTES:
            response[axis] = {}
            for k, v in self.PIPETTES[axis].__dict__.items():
                response[axis][k] = v
            
            # should include:
            #  'top'
            #  'bottom'
            #  'blowout'
            #  'droptip'
            #  'volume'
        
        if debug == True: FileIO.log('head.get_pipettes response:\n\n',response);
        return response

    #from planner.js
    def move_pipette(self, axis, property_):
        """
        Move the pipette to one of it's calibrated positions (top, bottom, blowout, droptip)
        
        This command is useful for seeing saved pipette positions while calibrating
        """
        #doesn't map to smoothieAPI
        #function movePipette (axis, property)
        if debug == True: 
            FileIO.log('head.move_pipette called')
            if verbose == True:
                FileIO.log('\n\taxis: ',axis,'\n\tproperty_: ',property_,'\n')
                FileIO.log('head:\n\tself.PIPETTES[axis].__dict__[',property_,'] = ',self.PIPETTES[axis].__dict__[property_],'\n')
        if self.PIPETTES[axis] and property_ in self.PIPETTES[axis].__dict__:
            moveCommand = {}
            moveCommand[axis] = self.PIPETTES[axis].__dict__[property_]
            if debug == True and verbose == True:
                FileIO.log('\nmoveCommand = ',moveCommand)
                FileIO.log(moveCommand)
            self.move(moveCommand)
            
    
    
    def move_plunger(self, axis, locations):
        """
        Move the plunger for given axis according to locations

        :note: This is only called from :class:`subscriber` and may be redundant

        locations = [loc, loc, etc... ]

        loc = {'plunger' : number}

        :todo:
        1. Figure out if :meth:`move_plunger` is redundant and refactor accordingly
        """

        if debug == True:
            FileIO.log('head.move_plunger called')
            if verbose == True:
                FileIO.log('\n\tlocations:\n\n',locations,'\n')

        if(self.PIPETTES[axis]):
            for i in range(len(locations)):
                moveCommand = self.PIPETTES[axis].pmap(locations[i])
                self.move(moveCommand)


    def erase_job(self):
        """
        Tell theQueue to clear
        """
        if debug == True: FileIO.log('head.erase_job called')
        self.theQueue.clear()


    def publish_calibrations(self):
        """
        Publish calibrations data
        """
        if debug == True: FileIO.log('head.publish_calibrations called')
        self.pubber.send_message('containerLocations',self.get_deck())
        self.pubber.send_message('pipetteValues',self.get_pipettes())
        