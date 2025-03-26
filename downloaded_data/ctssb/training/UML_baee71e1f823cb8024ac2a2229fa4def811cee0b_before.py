from gi.repository import Gdk
from gi.repository import Gtk
from DragBox import DragBox
import State


class UMLComponent(DragBox):
    def __init__(self, width, height):
        super(UMLComponent, self).__init__()

        self.connect('draw', self.on_draw)
        self.set_app_paintable(True)
        self.state = State.NORMAL
        self.layout = Gtk.Layout()
        self.add(self.layout)

        # init class field
        self.selected_block_size = 10
        self.show_selected_line = False
        self.selected_line_width = 3
        self.selected_line_dashes = [6.0]
        self.width = width
        self.height = height
        self.set_size_request(width+2*self.selected_block_size,
                              height+2*self.selected_block_size)
        self.selected_blocks = None

    def set_state(self, state):
        self.state = state

    def on_draw(self, widget, cairo_context):
        self.draw_background(cairo_context)
        if self.state == State.UMLComponent.SELECTED:
            if self.show_selected_line:
                self.draw_selected_line(cairo_context)
            if self.selected_blocks is None:
                self.selected_blocks = self.setup_selected_blocks()
            # TODO: Fix infinite loop into draw when move component
            # else:
            #     self.rearrange_widget()

    def rearrange_widget(self):
        raise NotImplementedError

    def draw_background(self, cairo_context):
        cairo_context.rectangle(self.selected_block_size, self.selected_block_size, self.width, self.height)
        cairo_context.set_source_rgb(0, 1, 0)
        cairo_context.fill()

    def setup_selected_blocks(self):
        raise NotImplementedError

    def draw_selected_line(self, cairo_context):
        raise NotImplementedError

    def set_size(self, width, height):
        self.width = width
        self.height = height
        self.update_component_size()

    def set_selected_line_visible(self, setting):
        self.show_selected_line = setting

    def set_selected_line_width(self, line_width):
        self.selected_line_width = line_width

    def set_selected_line_dashes(self, line_dashes):
        self.selected_line_dashes = line_dashes

    def set_selected_block_size(self, selected_block_size):
        self.selected_block_size = selected_block_size
        self.update_component_size()

    def update_component_size(self):
        self.set_size_request(self.width+2*self.selected_block_size,
                              self.height+2*self.selected_block_size)