"""
Objects that can be manipulated by the model editor GUI.

Originally written by Alan Lindsay.
$Id$
"""
__version__='$Revision$'

from Tkinter import Button, Label, Frame, Toplevel, TOP, LEFT, RIGHT, BOTTOM, E, LAST, FIRST
import Pmw
import math

from topo.commands.analysis import update_activity
from parametersframe import ParametersFrame

class EditorObject :
    """
    Anything that can be added and manipulated in an EditorCanvas. Every EditorCanvas
    has a corresponding Topo object associated with it. An instance of this class can 
    have the focus.
    """
    FROM = 0
    TO = 1

    # constructor
    def __init__(self, name, canvas) :
        self.canvas = canvas # retains a reference to the canvas
        self.name = name # set the name of the sheet
        self.focus = False # this does not have the focus
        self.viewing_choices = []
        self.object_cover_dict = {}

    def draw(self) :
        # draw the object at the current x, y position
        pass

    def show_properties(self) :
        # show parameters frame for object
        parameter_window = Toplevel()
        Label(parameter_window, text = self.name).pack(side = TOP)
        self.parameter_frame = ParametersFrame(parameter_window)
        self.button_panel = Frame(parameter_window)
        self.button_panel.pack(side = BOTTOM)
        update_button = Button(self.button_panel, text = 'Apply', 
            command = self.update_parameters)
        okay_button = Button(self.button_panel, text = 'Ok', 
            command = lambda : self.okay_parameters(parameter_window))
        okay_button.pack(side = RIGHT)
        update_button.pack(side = RIGHT)

    def update_parameters(self) :
        self.parameter_frame.set_obj_params()
        self.object_cover_dict = self.parameter_frame.object_dictionary

    def okay_parameters(self, parameter_window) :
        self.update_parameters()
        parameter_window.destroy()

    def set_focus(self, focus) : # set focus
        self.focus = focus

    def show_activity(self) : # set whether activity should be displayed.
        pass

    def move(self) :
        # update position of object and redraw
        pass

    def remove(self) :
        # remove this object from the canvas and deal with relevant 
        # Topographica objects.
        pass    

    def in_bounds(self, x, y) : 
        # return true, if x,y lies within this gui object's boundary
        pass

####################################################################


class EditorNode(EditorObject) :
    """
    An EditorNode is used to cover any topographica node, presently this can only be a sheet.
    It is a sub class of EditorObject and supplies the methods required by any node to be used
    in a EditorCanvas. Extending classes will supply a draw method and other type specific 
    attributes. 
    """
    show_density = False
    show_activity = False


    def __init__(self, canvas, pos, name, colour = ('dark red','black')):#('slate blue', 'lavender')) :
        EditorObject.__init__(self, name, canvas)
        self.colours = colour # colours for drawing this node on the canvas
        self.from_connections = [] # connections from this node
        self.to_connections = [] # connections to this node
        self.x = pos[0] # set the x and y coords of the centre of this node
        self.y = pos[1]

    ############ Connection methods ########################

    def attach_connection(self, con, from_to) :
        if (from_to == self.FROM) :
            if (con.from_node == con.to_node) :
                self.from_connections = [con] + self.from_connections
            else :
                self.from_connections = self.from_connections + [con]
        else :
            if (con.from_node == con.to_node) :
                self.to_connections = [con] + self.to_connections
            else :
                self.to_connections = self.to_connections + [con]
	
    def remove_connection(self, con, from_to) : # remove a connection to or from this node
        if (from_to) :
            l = len(self.to_connections)
            for i in range(l) :
                if (con == self.to_connections[i]) : break
            else : return
            del self.to_connections[i]
            node = con.from_node
        else :
            l = len(self.from_connections)
            for i in range(l) :
                if (con == self.from_connections[i]) : break
            else : return
            del self.from_connections[i]
            node = con.to_node
        index = con.draw_index
        # Decrease the indexes of the connections between the same nodes and with a higher index.
        for connection in self.from_connections :
            if (node == connection.to_node and connection.draw_index > index) :
                connection.decrement_draw_index()
            if connection.to_node == connection.from_node : return
        for connection in self.to_connections :       
            if (node == connection.from_node and connection.draw_index > index) :
                connection.decrement_draw_index()


    def get_connection_count(self, node) :
        count = 0
        for con in self.from_connections :
            if (con.to_node == node) :
                count += 1
        for con in self.to_connections :
            if (con.from_node == node) :
                count += 1
        if node == self : count /= 2
        return count

    ############ Util methods ##############################
    
    def get_pos(self) :
        return (self.x, self.y) # return center point of node

    def show_properties(self) :
        EditorObject.show_properties(self)
        self.parameter_frame.create_widgets(self.sheet, self.object_cover_dict)
        lateral_button = Button(self.button_panel, text = 'Lateral', command = self.show_lateral_parameters)
        lateral_button.pack(side = RIGHT)

    def show_lateral_parameters(self) :
        lateral_connection_list = []
        for con in self.from_connections :
            if (con.to_node == con.from_node) :
                lateral_connection_list += [con]
        parameter_window = Toplevel()
        for con in lateral_connection_list :
            frame = Frame(parameter_window)
            frame.pack(side = LEFT)
            Label(frame, text = con.name).pack(side = TOP)
            con.parameter_frame = ParametersFrame(frame)
            con.parameter_frame.create_widgets(con.connection)
            button_panel = Frame(frame)
            button_panel.pack(side = BOTTOM)
            Button(button_panel, text = 'Apply', 
                command = con.update_parameters).pack(side = LEFT)
            Button(button_panel, text = 'Delete',
                command = con.remove).pack(side = RIGHT)

class EditorSheet(EditorNode) :
    """
    Represents any topo sheet. It is a subclass of EditorNode and fills in the
    methods that are not defined. It is represented by a Paralellogram in its
    Canvas. The colours used for drawing can be set. Uses bounding box to
    determine if x, y coord is within its boundary.
    """

    def __init__(self, canvas, sheet, pos, name) :
        # super constructor call
        EditorNode.__init__(self, canvas, pos, name)
        self.sheet = sheet # the topo sheet that this object represents
        sheet.gui_x, sheet.gui_y = self.x, self.y # store the ed coords in the topo sheet
        self.element_count = self.matrix_element_count()
        self.set_bounds()
        self.activity = False
        col = self.colours[1]
        self.view = 'normal'
        self.init_draw(col, False) # create a new paralellogram
        self.currentCol = col
        self.gradient = 1
        self.viewing_choices = [('Normal', lambda: self.select_view('normal')),
                                ('Activity', lambda: self.select_view('activity'))]

    ############ Draw methods ############################

    def set_focus(self, focus) :
        for id in self.id :
            self.canvas.delete(id)
        self.canvas.delete(self.label) # remove label	
        EditorNode.set_focus(self, focus) # call to super's set focus
        if (focus) : col = self.colours[0]
        else : col = self.colours[1]
        self.init_draw(col, focus) # create new one with correct colour
        self.currentCol = col
        self.draw()

    def select_view(self, view_choice) :
        self.view = view_choice
        self.set_focus(False)
        self.canvas.redraw_objects()

    def init_draw(self, colour, focus) :
        self.id = []
        if focus : label_colour = colour
        else : label_colour = 'black'
        factor = self.canvas.scaling_factor
        h, w = 0.5 * self.height * factor, 0.5 * self.width *factor
        if not(self.focus) :
            if self.view == 'activity' :
                colour = ''
                x, y = self.x - w + h, self.y - h
                # AL, the idea will be to allow any available plots to be shown on the sheet.
                # eg m = self.sheet.sheet_view_dict['OrientationPreference'].view()[0]
                update_activity()
                m = self.sheet.sheet_view_dict['Activity'].view()[0]
                m = self.normalize(m)
                matrix_width, matrix_height = self.element_count
                dX, dY = (w * 2)/ matrix_width, (h * 2) / matrix_height
                for i in range(matrix_height) :
                    for j in range(matrix_width) :
                        a = i * dY
                        x1, y1 = x - a + (j * dX), y + a
                        x2, y2 = x1 - dY, y1 + dY
                        x3, x4 = x2 + dX, x1 + dX
                        col = '#' + (self.dec_to_hex_str(m[i][j], 3)) * 3
                        self.id = self.id + [self.canvas.create_polygon
                           (x1, y1, x2, y2, x3, y2, x4, y1, fill = col, outline = col)]
        x, y = self.x, self.y
        x1,y1 = (x - w - h, y + h)
        x2,y2 = (x - w + h, y - h)
        x3,y3 = x2 + (w * 2), y2
        x4,y4 = x1 + (w * 2), y1
        self.id = self.id + [self.canvas.create_polygon(x1, y1, x2, y2, x3, y3, x4, y4, 
            fill = colour , outline = "black")]
        dX = w + 5
        self.label = self.canvas.create_text(x - dX, y, anchor = E, fill = label_colour, text = self.name)
        # adds a density grid over the sheet
        if self.show_density :
            x, y = self.x - w + h, self.y - h
            matrix_width, matrix_height = self.element_count
            dX, dY = (w * 2)/ matrix_width, (h * 2) / matrix_height
            for i in range(matrix_height + 1) :
                x1 = x - (i * dY)
                x2 = x1 + (w * 2)
                y1 = y + (i * dY)
                self.id = self.id + [self.canvas.create_line(x1, y1, x2, y1, fill = 'slate blue')]
            for j in range(matrix_width + 1) :
                x1 = x + (j * dX)
                x2 = x1 - (h * 2)
                y1 = y
                y2 = y1 + (h * 2)
                self.id = self.id + [self.canvas.create_line(x1, y1, x2, y2, fill = 'slate blue')]

    def normalize(self,a):
        """ 
        Normalize an array s.
        In case of a constant array, ones is returned for value greater than zero,
        and zeros in case of value inferior or equal to zero.
        """
        # AL is it possible to use the normalize method in plot?
        from Numeric import zeros, ones, Float, divide
        a_offset = a-min(a.flat)
        max_a_offset = max(a_offset.flat)
        if max_a_offset>0:
             a = divide(a_offset,float(max_a_offset))
        else:
             if min(a.flat)<=0:
                  a=zeros(a.shape,Float)
             else:
                  a=ones(a.shape,Float)
        return a

    def dec_to_hex_str(self, val, length) :
        # expects a normalised value and maps it to a hex value of the given length
        max_val = pow(16, length) - 1
        hex_string = str(hex(int(val * max_val)))
        extend = length - len(hex_string) + 2
        hex_string = (extend * '0') + hex_string[2:]
        return hex_string

    def draw(self, x = 0, y = 0) :
        # move the parallelogram and label by the given x, y coords (default redraw)
        if not(x == y == 0) :
            for id in self.id :
                self.canvas.move(id, x, y)
            self.canvas.move(self.label, x, y)
        for id in self.id :
            self.canvas.tag_raise(id)
        self.canvas.tag_raise(self.label)
        # redraw the connections
        for con in self.to_connections : 
            if (con.from_node == con.to_node) :
                con.move()
        for con in self.to_connections :
            if (not(con.from_node == con.to_node)) :
                con.move()
        for con in self.from_connections :
            if (not(con.from_node == con.to_node)) :
                con.move()

    ############ Update methods ############################ 

    def remove(self) :
        l = len(self.from_connections) # remove all the connections from and to this sheet
        for index in range(l) :
            self.from_connections[0].remove()
        l = len(self.to_connections)
        for index in range(l) :
            self.to_connections[0].remove()
        for id in self.id :
            self.canvas.delete(id)
        self.canvas.delete(self.label)
        self.canvas.remove_object(self) # remove from canvas' object list

    def move(self, x, y) :
        # the connections position is updated
        old = self.x, self.y
        self.x = x
        self.y = y
        self.sheet.gui_x, self.sheet.gui_y = x, y # update topo sheet position
        self.draw(self.x - old[0], self.y - old[1])

    ############ Util methods ##############################

    def in_bounds(self, pos_x, pos_y) : # returns true if point lies in a bounding box
        # if the coord is pressed within the parallelogram representation this 
        # returns true.
        # Get the paralellogram points and centers them around the given point
        x = self.x - pos_x; y = self.y - pos_y
        w = 0.5 * self.width * self.canvas.scaling_factor
        h = 0.5 * self.height * self.canvas.scaling_factor
        A = (x - w - h, y + h)
        B = (x - w + h, y - h)
        C = B[0] + (2 * w), B[1]
        D = A[0] + (2 * w), A[1]
        # calculate the line constants 	
        # As the gradient of the lines is 1 the calculation is simple.
        a_AB = A[1] + A[0]
        a_CD = C[1] + C[0]
        # The points are centered around the given coord, finding the intersects with line y = 0
        # and ensuring that the left line lies on the negative side of the point and the right line
        # lies on the positive side of the point determines that the point is within the parallelogram.
        if ((D[1] >= 0) and (B[1] <= 0) and (a_AB <= 0) and (a_CD >= 0)) :
            return True
        return False

    def matrix_element_count(self) :
        # returns the length and width of the matrix that holds this sheet's plot values
        lbrt = self.sheet.bounds.aarect().lbrt()
        density = self.sheet.density
        return int(density *(lbrt[2] - lbrt[0])), int(density *(lbrt[3] - lbrt[1]))
    
    def set_bounds(self) :
        width_fact = 120; height_fact = 60
        lbrt = self.sheet.bounds.aarect().lbrt()
        self.width = width_fact * (lbrt[2] - lbrt[0]) * self.canvas.scaling_factor
        self.height = height_fact * (lbrt[3] - lbrt[1]) * self.canvas.scaling_factor

####################################################################

class EditorConnection(EditorObject) :

    """
    A connection formed between 2 EditorNodes on a EditorCanvas. A EditorConnection is used
    to cover any topographica connection (connection / projection), and extending 
    classes will supply a draw method and other type specific attributes.
    """
    def __init__(self, name, canvas, from_node) :
        EditorObject.__init__(self, name, canvas)
        self.from_node = from_node # initial node selected
        self.to_node = None # updated when the user selects the second node - self.connect(..)
        # temporary point, for when the to connection node is undefined
        self.to_position = from_node.get_pos()
	
    ############ Draw methods ############################

    def set_focus(self, focus) : # give this connection the focus
        EditorObject.set_focus(self, focus)
        self.draw()

    ############ Update methods ############################ 
    
    def move(self) :
        # if one of the nodes connected by this connection move, then move by redrawing	
        self.gradient = self.calculate_gradient()
        self.update_factor()
        self.draw() 

    def update_position(self, pos) : # update the temporary point
        self.to_position = pos
        self.draw()

    def connect(self, to_node, con) : # pass the node this connection is to
        self.connection = con # store the topo connection this object represents
        if (self.name == "") :
            self.name = con.name
        # ALALERT this shouldn't be here.
        self.draw_index = self.from_node.get_connection_count(to_node)
        if (self.from_node == to_node) :
            self.factor = self.get_factor() 
        else :
            self.connect_to_coord((self.from_node.width / 2) - 10)
        self.to_node = to_node # store a reference to the node this is connected to
        self.from_node.attach_connection(self, self.FROM) # tell the sheets that they are connected.
        self.to_node.attach_connection(self, self.TO)

    ############ Util methods ##############################
    def show_properties(self) :
        EditorObject.show_properties(self)
        self.parameter_frame.create_widgets(self.connection, self.object_cover_dict)

    def connect_to_coord(self, width) :
        n = self.draw_index
        sign = math.pow(-1, n)
        self.deviation = sign * width + (-sign) * math.pow(0.5, math.ceil(0.5 * (n))) * width


class EditorProjection(EditorConnection) :

    """
    Represents any topo projection. It is a subclass of EditorConnection and fills 
    in the methods that are not defined. Can be represented by a representation of a
    projection's receptive field or by a line with an arrow head in the middle;
    lateral projections are represented by a dotted ellipse around the centre.
    Can determine if x,y coord is within the triangular receptive field or within an
    area around the arrow head. The same can be determined for a lateral projection 
    ellipse
    """	
    def __init__(self, name, canvas, from_node, receptive_field = True) :
        EditorConnection.__init__(self, name, canvas, from_node)
        # if more than one connection between nodes, 
        # this will reflect how to draw this connection
        self.draw_index = 0
        self.deviation = 0
        self.normal_radius = 15
        self.radius = self.get_radius()
        self.gradient = (1,1)
        self.id = (None,None)
        self.label = None
        self.balloon = Pmw.Balloon(canvas)
        self.factor = self.get_factor()
        self.receptive_field = receptive_field
        self.view = 'radius'
        self.viewing_choices = [('Field Radius', lambda: self.select_view('radius')),
                                ('Line', lambda: self.select_view('line')),
                                ('Fixed Size', lambda: self.select_view('normal'))]

    ############ Draw methods ############################
    def select_view(self, view_choice) :
        self.view = view_choice
        self.move()
        self.set_focus(False)  


    def draw(self) :
        # determine if connected to a second node, and find the correct from_position
        for id in self.id : # remove the old connection
            self.canvas.delete(id)
        self.canvas.delete(self.label)
        from_position = self.from_node.get_pos() # get the centre points of the two nodes
        if (self.to_node == None) :  # if not connected yet, use temporary point.
            to_position = self.to_position
        else :
            to_position = self.to_node.get_pos()

        {'normal' : self.draw_normal,
         'line' :   self.draw_line,
         'radius' : self.draw_radius
        }[self.view](from_position, to_position)

    def draw_line(self,from_position, to_position) :
        # set the colour to be used depending on whether connection has the focus.
        if (self.focus) : 
            text_col = col = 'dark red'
            lateral_colour = self.from_node.colours[0]
        else :
            text_col = 'black'
            col = 'purple'#'dark green'
            lateral_colour = '' #self.from_node.currentCol
        middle = self.get_middle(from_position, to_position)
        factor = self.canvas.scaling_factor
        if (to_position == from_position) : # connection to and from the same node
            deviation = self.draw_index * 15 * factor
            x1 = to_position[0] - ((20 * factor) + deviation)
            y2 = to_position[1]
            x2 = x1 + (40 * factor) + (2 * deviation)
            y1 = y2 - ((30 * factor) + deviation) 
            midX = self.get_middle((x1,0),(x2,0))[0]
            # create oval and an arrow head.
            self.id = (self.canvas.create_oval(x1, y1, x2, y2, outline = col), 
            self.canvas.create_line(midX, y1, midX+1, y1, arrow = FIRST, fill = col))
            # draw name label beside arrow head
            self.label = self.canvas.create_text(middle[0] - 
            (20 + len(self.name)*3), middle[1] - (30 + deviation) , text = self.name)
        else :    
            # create a line between the nodes - use 2 to make arrow in centre.
            dev = self.deviation
            from_pos = from_position[0] + self.deviation, from_position[1]
            mid = middle[0] + 0.5 * dev, middle[1]
            self.id = (self.canvas.create_line(from_pos, mid , arrow = LAST, fill = col),
                    self.canvas.create_line(mid, to_position, fill = col))
            # draw name label
            dX = 20 * factor
            dY = self.draw_index * 20 * factor
            self.label = self.canvas.create_text(middle[0] - dX,
                middle[1] - dY, fill = text_col, text = self.name, anchor = E)

    def draw_radius(self, from_position, to_position) :
         # set the colour to be used depending on whether connection has the focus.
        if (self.focus) : 
            text_col = col = 'dark red'
            lateral_colour = self.from_node.colours[0]
        else :
            text_col = 'black'
            col = 'purple'#'dark green'
            lateral_colour = '' #self.from_node.currentCol
        # midpoint of line
        middle = self.get_middle(from_position, to_position)
        factor = self.canvas.scaling_factor
        if (to_position == from_position) : # connection to and from the same node
            a, b = self.get_radius()
            x1 = to_position[0] - a
            y1 = to_position[1] + b
            x2 = to_position[0] + a
            y2 = to_position[1] - b
            self.id = (self.canvas.create_oval(x1, y1, x2, y2, fill = lateral_colour, 
                dash = (2,2), outline = 'yellow', width = 2), None)
            self.balloon.tagbind(self.canvas, self.id[0], self.name)       
        else :  # connection between distinct nodes
            x1, y1 = to_position
            x2, y2 = from_position
            # this is for cases when the radius changes size.
            radius_x, radius_y = self.get_radius()
            self.id = (self.canvas.create_line(x1, y1, x2 - radius_x, y2, fill = col),
                self.canvas.create_line(x1, y1, x2 + radius_x, y2, fill = col),
                self.canvas.create_oval(x2 - radius_x, y2 - radius_y, 
                    x2 + radius_x, y2 + radius_y, outline = col))
            # draw name label
            dX = 20
            dY = self.draw_index * 20
            self.label = self.canvas.create_text(middle[0] - dX,
                middle[1] - dY, fill = text_col, text = self.name, anchor = E)



    def draw_normal(self, from_position, to_position) :
        # set the colour to be used depending on whether connection has the focus.
        if (self.focus) : 
            text_col = col = 'dark red'
            lateral_colour = self.from_node.colours[0]
        else :
            text_col = 'black'
            col = 'purple'#'dark green'
            lateral_colour = '' #self.from_node.currentCol
        # midpoint of line
        middle = self.get_middle(from_position, to_position)
        if (to_position == from_position) : # connection to and from the same node
            a, b = self.factor
            x1 = to_position[0] - a
            y1 = to_position[1] + b
            x2 = to_position[0] + a
            y2 = to_position[1] - b
            self.id = (self.canvas.create_oval(x1, y1, x2, y2, fill = lateral_colour, 
                dash = (2,2), outline = 'yellow', width = 2), None)
            self.balloon.tagbind(self.canvas, self.id[0], self.name)

        else :  # connection between distinct nodes
            x1, y1 = to_position
            x2, y2 = from_position
            x2 += self.deviation
            radius = self.normal_radius
            self.id = (self.canvas.create_line(x1, y1, x2 - radius, y2, fill = col),
                self.canvas.create_line(x1, y1, x2 + radius, y2, fill = col),
                self.canvas.create_oval(x2 - radius, y2 - (0.5 * radius), 
                x2 + radius, y2 + (0.5 * radius), outline = col))
            # draw name label
            dX = 20
            dY = self.draw_index * 20
            self.label = self.canvas.create_text(middle[0] - dX,
                middle[1] - dY, fill = text_col, text = self.name, anchor = E)
	
    ############ Update methods ############################ 
    def remove(self) :
        if (self.to_node != None) : # if a connection had been made then remove it from the 'to' node
            self.to_node.remove_connection(self, self.TO)
            self.from_node.remove_connection(self, self.FROM) # and remove from 'from' node
        for id in self.id : # remove the representation from the canvas
            self.canvas.delete(id)
            print 'delete'
        self.canvas.delete(self.label)

    def decrement_draw_index(self) :
        self.draw_index -= 1
        if self.to_node == self.from_node :
            self.update_factor()
        else: 
            self.connect_to_coord((self.from_node.width / 2) - 10)

    def connect(self, to_node, con) :
        EditorConnection.connect(self, to_node, con)
        self.to_position = None
        self.gradient = self.calculate_gradient()
        self.radius = self.get_radius()

    ############ Util methods ##############################
    def get_middle(self, pos1, pos2) : # returns the middle of two points
        return (pos1[0] + (pos2[0] - pos1[0])*0.5, pos1[1] + (pos2[1] - pos1[1])*0.5)

    def get_radius(self) :
        factor = self.canvas.scaling_factor
        if self.to_node == None :
            return (factor * self.normal_radius, factor * self.normal_radius * 
                self.from_node.height / self.from_node.width)
        node = self.from_node
        node_bounds = node.sheet.bounds.aarect().lbrt()
        try :
            bounds = self.connection.weights_bounds.aarect().lbrt()
        except :
            try :
                bounds = self.connection._weights_bounds_param_value.aarect().lbrt()
            except : return (factor * self.normal_radius, factor * self.normal_radius * 
                self.from_node.height / self.from_node.width)
        radius_x = factor * (node.width / 2) * (bounds[2] - bounds[0]) / (node_bounds[2] - node_bounds[0])
        radius_y = radius_x * node.height / node.width
        return radius_x, radius_y

    # returns the size of the semimajor and semiminor axis of the ellipse representing 
    # the draw_index-th lateral projection.
    def get_factor(self) :
        factor = self.canvas.scaling_factor
        w = factor * self.from_node.width; h = factor * self.from_node.height
        a = 20; n = (w / 2) - 10; b = (n - a)
        major = a + (b * (1 - pow(0.8, self.draw_index)))
        a = 20 * h / w; n = (h / 2) - 10; b = (n - a)
        minor = a + (b * (1 - pow(0.8, self.draw_index)))
        return major, minor

    def update_factor(self) :
        self.factor = self.get_factor()
    # returns the gradients of the two lines making the opening 'v' part of the receptive field. 
    # this depends on the draw_index, as it determines where the projection's representation begins.
    def calculate_gradient(self) :
        factor = self.canvas.scaling_factor
        if self.view == 'radius':
            A = self.to_node.get_pos()
            T = self.from_node.get_pos()
            B = (T[0] - self.radius[0], T[1])
            C = (T[0] + self.radius[0], T[1])
        else :
            A = self.to_node.get_pos()
            T = (self.from_node.get_pos()[0] + self.deviation ,self.from_node.get_pos()[1])
            B = (T[0] - (factor * self.normal_radius), T[1])
            C = (T[0] + (factor * self.normal_radius), T[1])
        den_BA = (A[0] - B[0])
        if not(den_BA == 0) :
            m_BA = (A[1] - B[1]) / den_BA
        else : 
            m_BA = 99999 # AL - this should be a big number
        den_CA = (A[0] - C[0])
        if not(den_CA == 0) :
            m_CA = (A[1] - C[1]) / den_CA
        else : 
            m_CA = 99999 # AL - this should be a big number
        return (m_BA, m_CA)

    def in_bounds(self, x, y) : # returns true if point lies in a bounding box
        factor = self.canvas.scaling_factor
        if self.view == 'line':
            # If connections are represented as lines
            # currently uses an extent around the arrow head.
            to_position = self.to_node.get_pos()
            from_position = self.from_node.get_pos()
            if (self.to_node == self.from_node) :
                deviation = self.draw_index * 15 * factor
                middle = (to_position[0], to_position[1] - ((30 * factor) + deviation))
            else :
                dev = self.deviation * 0.5
                middle = self.get_middle(from_position, to_position)
            if ((x < middle[0] + 10 + dev) & (x > middle[0] - 10 + dev) & (y < middle[1] + 10) & (y > middle[1] - 10)) :
                return True
            return False
        else :
            # returns true if x, y lie inside the oval representing this lateral projection
            if (self.to_node == None or self.to_node == self.from_node) :
                if self.view == 'radius' :
                    a, b = self.get_radius()
                else :
                    a, b = self.factor
                x, y = x - self.to_node.get_pos()[0], y - self.to_node.get_pos()[1]
                if (x > a or x < -a) :
                    return False
                pY = math.sqrt(pow(b,2) * (1 - (pow(x,2)/pow(a,2))))
                if (y > pY or y < -pY) :
                    return False
                return True
            # returns true if x, y lie inside the triangular receptive field representing this projection
            # get the points of the triangular receptive field, centered around the x, y point given
            to_position = self.to_node.get_pos()
            from_position = self.from_node.get_pos()
            if self.view == 'radius' :
                A = (to_position[0] - x, to_position[1] - y)
                T = (from_position[0] + (self.deviation * factor) - x, from_position[1] - y)
                B = (T[0] - self.radius[0], T[1])
                C = (T[0] + self.radius[0], T[1])
            else :
                A = (to_position[0] - x, to_position[1] - y)
                T = (from_position[0] + (self.deviation * factor) - x, from_position[1] - y)
                B = (T[0] - (self.normal_radius * factor), T[1])
                C = (T[0] + (self.normal_radius * factor), T[1])
            # if the y coords lie outwith the boundaries, return false
            if (((A[1] < B[1]) and (B[1] < 0 or A[1] > 0)) or 
                ((A[1] >= B[1]) and (B[1] > 0 or A[1] < 0))) :
                return False
            # calculate the constant for the lines of the triangle
            a_BA = A[1] - (self.gradient[0] * A[0])
            a_CA = A[1] - (self.gradient[1] * A[0])
            # The points are centered around the given coord, finding the intersects with line y = 0
            # and ensuring that the left line lies on the negative side of the point and the right line
            # lies on the positive side of the point determines that the point is within the triangle.
            if (((0 - a_CA) / self.gradient[1] >= 0) and ((0 - a_BA) / self.gradient[0] <= 0)) :
                return True
            return False	
