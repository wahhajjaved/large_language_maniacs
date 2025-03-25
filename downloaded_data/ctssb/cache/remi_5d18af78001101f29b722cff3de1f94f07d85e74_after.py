"""
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

import os
import logging
from functools import cmp_to_key

from .server import runtimeInstances, update_event

log = logging.getLogger('remi.gui')


def to_pix(x):
    return str(x) + 'px'


def from_pix(x):
    v = 0
    try:
        v = int(float(x.replace('px', '')))
    except Exception as e:
        log.error('error parsing px', exc_info=True)
    return v


def jsonize(d):
    return ';'.join(map(lambda k, v: k + ':' + v + '', d.keys(), d.values()))


class EventManager(object):
    """Manages the event propagation to the listeners functions"""

    def __init__(self):
        self.listeners = {}

    def propagate(self, eventname, params):
        # if for an event there is a listener, it calls the listener passing the parameters
        if eventname not in self.listeners:
            return
        listener = self.listeners[eventname]
        return getattr(listener['instance'], listener['funcname'])(*params)

    def register_listener(self, eventname, instance, funcname):
        """register a listener for a specific event"""
        self.listeners[eventname] = {'instance':instance, 'funcname':funcname}


class Tag(object):
    def __init__(self):
        # the runtime instances are processed every time a requests arrives, searching for the called method
        # if a class instance is not present in the runtimeInstances, it will
        # we not callable
        runtimeInstances.append(self)

        self._render_children_list = []

        self.children = {}
        self.attributes = {}  # properties as class id style

        self.type = ''
        self.attributes['id'] = str(id(self))
        self.attributes['class'] = self.__class__.__name__

    def repr(self, client, include_children=True):
        """it is used to automatically represent the object to HTML format
        packs all the attributes, children and so on."""

        self.attributes['children_list'] = ','.join(map(lambda k, v: str(
            id(v)), self.children.keys(), self.children.values())) 

        # concatenating innerHTML. in case of html object we use repr, in case
        # of string we use directly the content
        innerHTML = ''
        for s in self._render_children_list:
            if isinstance(s, type('')):
                innerHTML = innerHTML + s
            elif isinstance(s, type(u'')):
                innerHTML = innerHTML + s.encode('utf-8')
            elif include_children:
                innerHTML = innerHTML + s.repr(client)

        html = '<%s %s>%s</%s>' % (self.type,
                                   ' '.join(map(lambda k, v: k + '="' + str(v) + '"', self.attributes.keys(), self.attributes.values())),
                                   innerHTML,
                                   self.type)
        return html

    def append(self, key, value):
        """it allows to add child to this.

        The key can be everything you want, in order to access to the
        specific child in this way 'widget.children[key]'.

        """
        if hasattr(value, 'attributes'):
            value.attributes['parent_widget'] = str(id(self))

        if key in self.children:
            self._render_children_list.remove(self.children[key])
        self._render_children_list.append(value)

        self.children[key] = value

    def empty(self):
        for k in list(self.children.keys()):
            self.remove(self.children[k])

    def remove(self, child):
        if child in self.children.values():
            #runtimeInstances.pop( runtimeInstances.index( self.children[key] ) )
            self._render_children_list.remove(child)
            for k in self.children.keys():
                if str(id(self.children[k])) == str(id(child)):
                    self.children.pop(k)
                    #when the child is removed we stop the iteration
                    #this implies that a child replication should not be allowed
                    break


class Widget(Tag):

    """base class for gui widgets.

    In html, it is a DIV tag    
    the "self.type" attribute specifies the HTML tag representation    
    the "self.attributes[]" attribute specifies the HTML attributes like "style" "class" "id" 
    the "self.style[]" attribute specifies the CSS style content like "font" "color". 
    It will be packet togheter with "self.attributes"

    """
    #constants
    LAYOUT_HORIZONTAL = True
    LAYOUT_VERTICAL = False

    def __init__(self, w=1, h=1, layout_orientation=LAYOUT_HORIZONTAL, widget_spacing=0):
        """w = numeric with
        h = numeric height
        layout_orientation = specifies the "float" css attribute
        widget_spacing = specifies the "margin" css attribute for the children"""
        super(Widget,self).__init__()

        self.style = {}

        self.type = 'div'

        self.layout_orientation = layout_orientation
        self.widget_spacing = widget_spacing

        # some constants for the events
        self.EVENT_ONCLICK = 'onclick'
        self.EVENT_ONDBLCLICK = 'ondblclick'
        self.EVENT_ONMOUSEDOWN = 'onmousedown'
        self.EVENT_ONMOUSEMOVE = 'onmousemove'
        self.EVENT_ONMOUSEOVER = 'onmouseover'
        self.EVENT_ONMOUSEOUT = 'onmouseout'
        self.EVENT_ONMOUSELEAVE = 'onmouseleave'
        self.EVENT_ONMOUSEUP = 'onmouseup'
        self.EVENT_ONTOUCHMOVE = 'ontouchmove'
        self.EVENT_ONTOUCHSTART = 'ontouchstart'
        self.EVENT_ONTOUCHEND = 'ontouchend'
        self.EVENT_ONTOUCHENTER = 'ontouchenter'
        self.EVENT_ONTOUCHLEAVE = 'ontouchleave'
        self.EVENT_ONTOUCHCANCEL = 'ontouchcancel'
        self.EVENT_ONKEYDOWN = 'onkeydown'
        self.EVENT_ONKEYPRESS = 'onkeypress'
        self.EVENT_ONKEYUP = 'onkeyup'
        self.EVENT_ONCHANGE = 'onchange'
        self.EVENT_ONFOCUS = 'onfocus'
        self.EVENT_ONBLUR = 'onblur'
        self.EVENT_ONCONTEXTMENU = "oncontextmenu"
        self.EVENT_ONUPDATE = 'onupdate'

        if w > -1:
            self.style['width'] = to_pix(w)
        if h > -1:
            self.style['height'] = to_pix(h)
        self.style['margin'] = '0px auto'

        self.oldRootWidget = None  # used when hiding the widget

        self.eventManager = EventManager()

    def redraw(self):
        update_event.set()

    def repr(self, client, include_children = True):
        """it is used to automatically represent the widget to HTML format
        packs all the attributes, children and so on."""
        self.attributes['style'] = jsonize(self.style)
        return super(Widget,self).repr(client, include_children)

    def append(self, key, value):
        """it allows to add child widgets to this.

        The key can be everything you want, in order to access to the
        specific child in this way 'widget.children[key]'.

        """
        super(Widget,self).append(key, value)

        if hasattr(self.children[key], 'style'):
            spacing = to_pix(self.widget_spacing)
            selfHeight = 0
            selfWidth = 0
            if 'height' in self.style.keys() and 'height' in self.children[key].style.keys():
                selfHeight = from_pix(self.style['height']) - from_pix(self.children[key].style['height'])
            if 'width' in self.style.keys() and 'width' in self.children[key].style.keys():
                selfWidth = from_pix(self.style['width']) - from_pix(self.children[key].style['width'])
            self.children[key].style['margin'] = spacing + " " + to_pix(selfWidth/2)
            
            if self.layout_orientation:
                self.children[key].style['margin'] = to_pix(selfHeight/2) + " " + spacing
                if 'float' in self.children[key].style.keys():
                    if not (self.children[key].style['float'] == 'none'):
                        self.children[key].style['float'] = 'left'
                else:
                    self.children[key].style['float'] = 'left'

    def onfocus(self):
        return self.eventManager.propagate(self.EVENT_ONFOCUS, [])

    def set_on_focus_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONFOCUS] = "sendCallback('%s','%s');event.stopPropagation();event.preventDefault();" % (id(self), self.EVENT_ONFOCUS)
        self.eventManager.register_listener(self.EVENT_ONFOCUS, listener, funcname)

    def onblur(self):
        return self.eventManager.propagate(self.EVENT_ONBLUR, [])

    def set_on_blur_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONBLUR] = "sendCallback('%s','%s');event.stopPropagation();event.preventDefault();" % (id(self), self.EVENT_ONBLUR)
        self.eventManager.register_listener(self.EVENT_ONBLUR, listener, funcname)

    def show(self, baseAppInstance):
        """Allows to show the widget as root window"""
        self.baseAppInstance = baseAppInstance
        # here the widget is set up as root, in server.gui_updater is monitored
        # this change and the new window is send to the browser
        self.oldRootWidget = self.baseAppInstance.client.root
        self.baseAppInstance.client.root = self

    def hide(self):
        """The root window is restored after a show"""
        if hasattr(self,'baseAppInstance'):
            self.baseAppInstance.client.root = self.oldRootWidget

    def onclick(self):
        return self.eventManager.propagate(self.EVENT_ONCLICK, [])

    def set_on_click_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONCLICK] = "sendCallback('%s','%s');event.stopPropagation();event.preventDefault();" % (id(self), self.EVENT_ONCLICK)
        self.eventManager.register_listener(self.EVENT_ONCLICK, listener, funcname)

    def oncontextmenu(self):
        return self.eventManager.propagate(self.EVENT_ONCONTEXTMENU, [])

    def set_on_contextmenu_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONCONTEXTMENU] = "sendCallback('%s','%s');event.stopPropagation();event.preventDefault();return false;" % (id(self), self.EVENT_ONCONTEXTMENU)
        self.eventManager.register_listener(self.EVENT_ONCONTEXTMENU, listener, funcname)

    def onmousedown(self, x, y):
        return self.eventManager.propagate(self.EVENT_ONMOUSEDOWN, [x, y])

    def set_on_mousedown_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONMOUSEDOWN] = "var params={};params['x']=event.clientX-this.offsetLeft;params['y']=event.clientY-this.offsetTop; sendCallbackParam('%s','%s',params);event.stopPropagation();event.preventDefault();return false;" % (id(self), self.EVENT_ONMOUSEDOWN)
        self.eventManager.register_listener(self.EVENT_ONMOUSEDOWN, listener, funcname)
        
    def onmouseup(self, x, y):
        return self.eventManager.propagate(self.EVENT_ONMOUSEUP, [x, y])

    def set_on_mouseup_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONMOUSEUP] = "var params={};params['x']=event.clientX-this.offsetLeft;params['y']=event.clientY-this.offsetTop; sendCallbackParam('%s','%s',params);event.stopPropagation();event.preventDefault();return false;" % (id(self), self.EVENT_ONMOUSEUP)
        self.eventManager.register_listener(self.EVENT_ONMOUSEUP, listener, funcname)
        
    def onmouseout(self):
        return self.eventManager.propagate(self.EVENT_ONMOUSEOUT, [])

    def set_on_mouseout_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONMOUSEOUT] = "sendCallback('%s','%s');event.stopPropagation();event.preventDefault();return false;" % (id(self), self.EVENT_ONMOUSEOUT)
        self.eventManager.register_listener(self.EVENT_ONMOUSEOUT, listener, funcname)

    def onmouseleave(self):
        return self.eventManager.propagate(self.EVENT_ONMOUSELEAVE, [])

    def set_on_mouseleave_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONMOUSELEAVE] = "sendCallback('%s','%s');event.stopPropagation();event.preventDefault();return false;" % (id(self), self.EVENT_ONMOUSELEAVE)
        self.eventManager.register_listener(self.EVENT_ONMOUSELEAVE, listener, funcname)

    def onmousemove(self, x, y):
        return self.eventManager.propagate(self.EVENT_ONMOUSEMOVE, [x, y])

    def set_on_mousemove_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONMOUSEMOVE] = "var params={};params['x']=event.clientX-this.offsetLeft;params['y']=event.clientY-this.offsetTop; sendCallbackParam('%s','%s',params);event.stopPropagation();event.preventDefault();return false;" % (id(self), self.EVENT_ONMOUSEMOVE)
        self.eventManager.register_listener(self.EVENT_ONMOUSEMOVE, listener, funcname)

    def ontouchmove(self, x, y):
        return self.eventManager.propagate(self.EVENT_ONTOUCHMOVE, [x, y])

    def set_on_touchmove_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONTOUCHMOVE] = "var params={};params['x']=parseInt(event.changedTouches[0].clientX)-this.offsetLeft;params['y']=parseInt(event.changedTouches[0].clientY)-this.offsetTop; sendCallbackParam('%s','%s',params);event.stopPropagation();event.preventDefault();return false;" % (id(self), self.EVENT_ONTOUCHMOVE)
        self.eventManager.register_listener(self.EVENT_ONTOUCHMOVE, listener, funcname)

    def ontouchstart(self, x, y):
        return self.eventManager.propagate(self.EVENT_ONTOUCHSTART, [x, y])

    def set_on_touchstart_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONTOUCHSTART] = "var params={};params['x']=parseInt(event.changedTouches[0].clientX)-this.offsetLeft;params['y']=parseInt(event.changedTouches[0].clientY)-this.offsetTop; sendCallbackParam('%s','%s',params);event.stopPropagation();event.preventDefault();return false;" % (id(self), self.EVENT_ONTOUCHSTART)
        self.eventManager.register_listener(self.EVENT_ONTOUCHSTART, listener, funcname)

    def ontouchend(self, x, y):
        return self.eventManager.propagate(self.EVENT_ONTOUCHEND, [x, y])

    def set_on_touchend_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONTOUCHEND] = "var params={};params['x']=parseInt(event.changedTouches[0].clientX)-this.offsetLeft;params['y']=parseInt(event.changedTouches[0].clientY)-this.offsetTop; sendCallbackParam('%s','%s',params);event.stopPropagation();event.preventDefault();return false;" % (id(self), self.EVENT_ONTOUCHEND)
        self.eventManager.register_listener(self.EVENT_ONTOUCHEND, listener, funcname)

    def ontouchenter(self, x, y):
        return self.eventManager.propagate(self.EVENT_ONTOUCHENTER, [x, y])

    def set_on_touchenter_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONTOUCHENTER] = "var params={};params['x']=parseInt(event.changedTouches[0].clientX)-this.offsetLeft;params['y']=parseInt(event.changedTouches[0].clientY)-this.offsetTop; sendCallbackParam('%s','%s',params);event.stopPropagation();event.preventDefault();return false;" % (id(self), self.EVENT_ONTOUCHENTER)
        self.eventManager.register_listener(self.EVENT_ONTOUCHENTER, listener, funcname)

    def ontouchleave(self):
        return self.eventManager.propagate(self.EVENT_ONTOUCHLEAVE, [])

    def set_on_touchleave_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONTOUCHLEAVE] = "sendCallback('%s','%s');event.stopPropagation();event.preventDefault();return false;" % (id(self), self.EVENT_ONTOUCHLEAVE)
        self.eventManager.register_listener(self.EVENT_ONTOUCHLEAVE, listener, funcname)

    def ontouchcancel(self):
        return self.eventManager.propagate(self.EVENT_ONTOUCHCANCEL, [])

    def set_on_touchcancel_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONTOUCHCANCEL] = "sendCallback('%s','%s');event.stopPropagation();event.preventDefault();return false;" % (id(self), self.EVENT_ONTOUCHCANCEL)
        self.eventManager.register_listener(self.EVENT_ONTOUCHCANCEL, listener, funcname)


class Button(Widget):

    def __init__(self, w, h, text=''):
        super(Button, self).__init__(w, h)
        self.type = 'button'
        self.attributes[self.EVENT_ONCLICK] = "sendCallback('%s','%s');" % (id(self), self.EVENT_ONCLICK)
        self.set_text(text)

    def set_text(self, t):
        self.append('text', t)


class TextInput(Widget):

    """multiline text area widget"""

    def __init__(self, w, h, single_line=True):
        super(TextInput, self).__init__(w, h)
        self.type = 'textarea'

        self.EVENT_ONENTER = 'onenter'
        self.attributes[self.EVENT_ONCLICK] = ''
        self.attributes[self.EVENT_ONCHANGE] = \
            "var params={};params['newValue']=document.getElementById('%(id)s').value;"\
            "sendCallbackParam('%(id)s','%(evt)s',params);" % {'id':id(self), 'evt':self.EVENT_ONCHANGE}
        self.set_text('')

        if single_line:
            self.style['resize'] = 'none'
            self.attributes['rows'] = '1'

    def set_text(self, t):
        """sets the text content."""
        self.append('text', t)

    def get_text(self):
        return self.children['text']

    def set_value(self, t):
        self.set_text(t)

    def get_value(self):
        #facility, same as get_text
        return self.get_text()

    def onchange(self, newValue):
        """returns the new text value."""
        self.set_text(newValue)
        return self.eventManager.propagate(self.EVENT_ONCHANGE, [newValue])

    def set_on_change_listener(self, listener, funcname):
        """register the listener for the onchange event."""
        self.eventManager.register_listener(self.EVENT_ONCHANGE, listener, funcname)

    def onkeydown(self,newValue):
        """returns the new text value."""
        self.set_text(newValue)
        return self.eventManager.propagate(self.EVENT_ONKEYDOWN, [newValue])
        
    def set_on_key_down_listener(self,listener,funcname):
        self.attributes[self.EVENT_ONKEYDOWN] = \
            "var params={};params['newValue']=document.getElementById('%(id)s').value;"\
            "sendCallbackParam('%(id)s','%(evt)s',params);" % {'id':id(self), 'evt':self.EVENT_ONKEYDOWN}
        self.eventManager.register_listener(self.EVENT_ONKEYDOWN, listener, funcname)

    def onenter(self,newValue):
        """returns the new text value."""
        self.set_text(newValue)
        return self.eventManager.propagate(self.EVENT_ONENTER, [newValue])

    def set_on_enter_listener(self,listener,funcname):
        self.attributes[self.EVENT_ONKEYDOWN] = """
            if (event.keyCode == 13) {
                var params={};
                params['newValue']=document.getElementById('%(id)s').value;
                sendCallbackParam('%(id)s','%(evt)s',params);
                return false;
            }""" % {'id':id(self), 'evt':self.EVENT_ONENTER}
        self.eventManager.register_listener(self.EVENT_ONENTER, listener, funcname)


class Label(Widget):

    def __init__(self, w, h, text):
        super(Label, self).__init__(w, h)
        self.type = 'p'
        self.append('text', text)

    def set_text(self, t):
        self.append('text', t)

    def get_text(self):
        return self.children['text']


class GenericDialog(Widget):

    """input dialog, it opens a new webpage allows the OK/CANCEL functionality
    implementing the "confirm_value" and "cancel_dialog" events."""

    def __init__(self, width=500, height=80, title='', message=''):
        self.width = width
        self.height = height
        super(GenericDialog, self).__init__(self.width, self.height, Widget.LAYOUT_VERTICAL, 10)

        self.EVENT_ONCONFIRM = 'confirm_dialog'
        self.EVENT_ONCANCEL = 'cancel_dialog'

        if len(title) > 0:
            t = Label(self.width - 20, 50, title)
            t.style['font-size'] = '16px'
            t.style['font-weight'] = 'bold'
            self.append('1', t)
            self.height = self.height + 50
            self.style['height'] = to_pix(from_pix(self.style['height']) + 50)
            
        if len(message) > 0:
            m = Label(self.width - 20, 30, message)
            self.append('2', m)
            self.height = self.height + 30
            self.style['height'] = to_pix(from_pix(self.style['height']) + 30)
        
        self.container = Widget(self.width - 20,0, Widget.LAYOUT_VERTICAL, 0)
        self.conf = Button(50, 30, 'Ok')
        self.cancel = Button(50, 30, 'Cancel')

        hlay = Widget(self.width - 20, 30)
        hlay.append('1', self.conf)
        hlay.append('2', self.cancel)
        self.conf.style['float'] = 'right'
        self.cancel.style['float'] = 'right'

        self.append('3', self.container)
        self.append('4', hlay)

        self.conf.attributes[self.EVENT_ONCLICK] = "sendCallback('%s','%s');" % (id(self), self.EVENT_ONCONFIRM)
        self.cancel.attributes[self.EVENT_ONCLICK] = "sendCallback('%s','%s');" % (id(self), self.EVENT_ONCANCEL)

        self.inputs = {}

        self.baseAppInstance = None

    def add_field_with_label(self,key,labelDescription,field):
        fields_spacing = 5
        field_height = from_pix(field.style['height']) + fields_spacing*2
        field_width = from_pix(field.style['width']) + fields_spacing*4
        self.style['height'] = to_pix(from_pix(self.style['height']) + field_height)
        self.container.style['height'] = to_pix(from_pix(self.container.style['height']) + field_height)
        self.inputs[key] = field
        label = Label(self.width-20-field_width-1, 30, labelDescription )
        container = Widget(self.width-20, field_height, Widget.LAYOUT_HORIZONTAL, fields_spacing)
        container.append('lbl' + key,label)
        container.append(key, self.inputs[key])
        self.container.append(key, container)
        
    def add_field(self,key,field):
        fields_spacing = 5
        field_height = from_pix(field.style['height']) + fields_spacing*2
        field_width = from_pix(field.style['width']) + fields_spacing*2
        self.style['height'] = to_pix(from_pix(self.style['height']) + field_height)
        self.container.style['height'] = to_pix(from_pix(self.container.style['height']) + field_height)
        self.inputs[key] = field
        container = Widget(self.width-20, field_height, Widget.LAYOUT_HORIZONTAL, fields_spacing)
        container.append(key, self.inputs[key])
        self.container.append(key, container)

    def get_field(self, key):
        return self.inputs[key]

    def confirm_dialog(self):
        """event called pressing on OK button.
        """
        self.hide()
        return self.eventManager.propagate(self.EVENT_ONCONFIRM, [])

    def set_on_confirm_dialog_listener(self, listener, funcname):
        self.eventManager.register_listener(self.EVENT_ONCONFIRM, listener, funcname)

    def cancel_dialog(self):
        self.hide()
        return self.eventManager.propagate(self.EVENT_ONCANCEL, [])

    def set_on_cancel_dialog_listener(self, listener, funcname):
        self.eventManager.register_listener(self.EVENT_ONCANCEL, listener, funcname)


class InputDialog(GenericDialog):

    """input dialog, it opens a new webpage allows the OK/CANCEL functionality
    implementing the "confirm_value" and "cancel_dialog" events."""

    def __init__(self, width=500, height=160, title='Title', message='Message',
                    initial_value=''):
        super(InputDialog, self).__init__(width, height, title, message)

        self.inputText = TextInput(width - 20, 30)
        self.inputText.set_on_enter_listener(self,'on_text_enter_listener')
        self.add_field('textinput',self.inputText)
        self.inputText.set_text(initial_value)

        self.EVENT_ONCONFIRMVALUE = 'confirm_value'
        self.set_on_confirm_dialog_listener(self, 'confirm_value')

    def on_text_enter_listener(self,value):
        """event called pressing on ENTER key.
        propagates the string content of the input field
        """
        self.hide()
        return self.eventManager.propagate(self.EVENT_ONCONFIRMVALUE, [value])

    def confirm_value(self):
        """event called pressing on OK button.
        propagates the string content of the input field
        """
        self.hide()
        return self.eventManager.propagate(self.EVENT_ONCONFIRMVALUE, [self.inputText.get_text()])

    def set_on_confirm_value_listener(self, listener, funcname):
        self.eventManager.register_listener(self.EVENT_ONCONFIRMVALUE, listener, funcname)


class ListView(Widget):

    """list widget it can contain ListItems."""

    def __init__(self, w, h, orientation=Widget.LAYOUT_VERTICAL):
        super(ListView, self).__init__(w, h, orientation)
        self.type = 'ul'
        self.EVENT_ONSELECTION = 'onselection'
        self.selected_item = None
        self.selected_key = None

    def append(self, key, item):
        # if an event listener is already set for the added item, it will not generate a selection event
        if item.attributes[self.EVENT_ONCLICK] == '':
            item.set_on_click_listener(self, self.EVENT_ONSELECTION)
        item.attributes['selected'] = False
        super(ListView, self).append(key, item)
    
    def empty(self):
        self.selected_item = None
        self.selected_key = None
        super(ListView,self).empty()

    def onselection(self, clicked_item):
        self.selected_key = None
        for k in self.children:
            if self.children[k] == clicked_item:
                self.selected_key = k
                log.debug('ListView - onselection. Selected item key: %s' % k)
                if self.selected_item is not None:
                    self.selected_item.attributes['selected'] = False
                self.selected_item = self.children[self.selected_key]
                self.selected_item.attributes['selected'] = True
                break
        return self.eventManager.propagate(self.EVENT_ONSELECTION, [self.selected_key])

    def set_on_selection_listener(self, listener, funcname):
        """The listener will receive the key of the selected item.
        If you add the element from an array, use a numeric incremental key
        """
        self.eventManager.register_listener(self.EVENT_ONSELECTION, listener, funcname)

    def get_value(self):
        """Returns the value of the selected item or None
        """
        if self.selected_item is None:
            return None
        return self.selected_item.get_value()

    def get_key(self):
        """Returns the key of the selected item or None
        """
        return self.selected_key

    def select_by_key(self, itemKey):
        """
        selects an item by its key
        """
        self.selected_key = None
        self.selected_item = None
        for item in self.children.values():
            item.attributes['selected'] = False

        if itemKey in self.children:
            self.children[itemKey].attributes['selected'] = True
            self.selected_key = itemKey
            self.selected_item = self.children[itemKey]

    def set_value(self, value):
        """
        selects an item by the value of a child
        """
        self.selected_key = None
        self.selected_item = None
        for k in self.children:
            item = self.children[k]
            item.attributes['selected'] = False
            if value == item.get_value():
                self.selected_key = k
                self.selected_item = item
                self.selected_item.attributes['selected'] = True


class ListItem(Widget):

    """item widget for the ListView"""

    def __init__(self, w, h, text):
        super(ListItem, self).__init__(w, h)
        self.type = 'li'

        self.attributes[self.EVENT_ONCLICK] = ''
        self.set_text(text)

    def set_text(self, text):
        self.append('text', text)

    def get_text(self):
        return self.children['text']

    def get_value(self):
        return self.get_text()

    def onclick(self):
        return self.eventManager.propagate(self.EVENT_ONCLICK, [self])


class DropDown(Widget):

    """combo box widget implements the onchange event.
    """

    def __init__(self, w, h):
        super(DropDown, self).__init__(w, h)
        self.type = 'select'
        self.attributes[self.EVENT_ONCHANGE] = \
            "var params={};params['newValue']=document.getElementById('%(id)s').value;"\
            "sendCallbackParam('%(id)s','%(evt)s',params);" % {'id':id(self),
                                                               'evt':self.EVENT_ONCHANGE}
        self.selected_item = None
        self.selected_key = None

    def select_by_key(self, itemKey):
        """
        selects an item by its key
        """
        for item in self.children.values():
            if 'selected' in item.attributes:
                del item.attributes['selected']
        self.children[itemKey].attributes['selected'] = 'selected'
        self.selected_key = itemKey
        self.selected_item = self.children[itemKey]

    def set_value(self, newValue):
        """
        selects the item by the contained text
        """
        self.selected_key = None
        self.selected_item = None
        for k in self.children:
            item = self.children[k]
            if item.attributes['value'] == newValue:
                item.attributes['selected'] = 'selected'
                self.selected_key = k
                self.selected_item = item
            else:
                if 'selected' in item.attributes:
                    del item.attributes['selected']

    def get_value(self):
        """Returns the value of the selected item or None
        """
        if self.selected_item is None:
            return None
        return self.selected_item.get_value()

    def get_key(self):
        """Returns the key of the selected item or None
        """
        return self.selected_key

    def onchange(self, newValue):
        log.debug('combo box. selected %s' % newValue)
        self.set_value(newValue)
        return self.eventManager.propagate(self.EVENT_ONCHANGE, [newValue])

    def set_on_change_listener(self, listener, funcname):
        self.eventManager.register_listener(self.EVENT_ONCHANGE, listener, funcname)


class DropDownItem(Widget):

    """item widget for the DropDown"""

    def __init__(self, w, h, text):
        super(DropDownItem, self).__init__(w, h)
        self.type = 'option'
        self.attributes[self.EVENT_ONCLICK] = ''
        self.set_text(text)

    def set_text(self, text):
        self.attributes['value'] = text
        self.append('text', text)

    def get_text(self):
        return self.attributes['value']

    def set_value(self, text):
        return self.set_text(text)

    def get_value(self):
        return self.get_text()


class Image(Widget):

    """image widget."""

    def __init__(self, w, h, filename):
        """filename should be an URL."""
        super(Image, self).__init__(w, h)
        self.type = 'img'
        self.attributes['src'] = filename


class Table(Widget):

    """
    table widget - it will contains TableRow
    """

    def __init__(self, w, h):
        super(Table, self).__init__(w, h)
        self.type = 'table'
        self.style['float'] = 'none'
        
    def from_2d_matrix(self, _matrix, fill_title=True):
        """
        Fills the table with the data contained in the provided 2d _matrix
        The first row of the matrix is set as table title
        """
        for child_keys in list(self.children):
            self.remove(self.children[child_keys])
        first_row = True
        for row in _matrix:
            tr = TableRow()
            for item in row:
                if first_row and fill_title:
                    ti = TableTitle(item)
                else:
                    ti = TableItem(item)
                tr.append( str(id(ti)), ti )
            self.append( str(id(tr)), tr )
            first_row = False


class TableRow(Widget):

    """
    row widget for the Table - it will contains TableItem
    """

    def __init__(self):
        super(TableRow, self).__init__(-1, -1)
        self.type = 'tr'
        self.style['float'] = 'none'


class TableItem(Widget):

    """item widget for the TableRow."""

    def __init__(self, text=''):
        super(TableItem, self).__init__(-1, -1)
        self.type = 'td'
        self.append('text', text)
        self.style['float'] = 'none'


class TableTitle(Widget):

    """title widget for the table."""

    def __init__(self, title=''):
        super(TableTitle, self).__init__(-1, -1)
        self.type = 'th'
        self.append('text', title)
        self.style['float'] = 'none'


class Input(Widget):

    def __init__(self, w, h, _type='', defaultValue=''):
        super(Input, self).__init__(w, h)
        self.type = 'input'
        self.attributes['class'] = _type

        self.attributes[self.EVENT_ONCLICK] = ''
        self.attributes[self.EVENT_ONCHANGE] = \
            "var params={};params['newValue']=document.getElementById('%(id)s').value;"\
            "sendCallbackParam('%(id)s','%(evt)s',params);" % {'id':id(self),
                                                               'evt':self.EVENT_ONCHANGE}
        self.attributes['value'] = str(defaultValue)
        self.attributes['type'] = _type

    def set_value(self,value):
        self.attributes['value'] = str(value)

    def get_value(self):
        """returns the new text value."""
        return self.attributes['value']

    def onchange(self, newValue):
        self.attributes['value'] = newValue
        return self.eventManager.propagate(self.EVENT_ONCHANGE, [newValue])

    def set_on_change_listener(self, listener, funcname):
        """register the listener for the onchange event."""
        self.eventManager.register_listener(self.EVENT_ONCHANGE, listener, funcname)


class CheckBoxLabel(Widget):
    def __init__(self, w, h, label='', checked=False, user_data=''):
        super(CheckBoxLabel, self).__init__(w, h, Widget.LAYOUT_HORIZONTAL)
        inner_checkbox_width = 30
        inner_label_padding_left = 10
        self._checkbox = CheckBox(inner_checkbox_width, h, checked, user_data)
        self._label = Label(w-inner_checkbox_width-inner_label_padding_left, h, label)
        self.append('checkbox', self._checkbox)
        self.append('label', self._label)
        self._label.style['padding-left'] = to_pix(inner_label_padding_left)

        self.set_value = self._checkbox.set_value
        self.get_value = self._checkbox.get_value
        self.set_on_change_listener = self._checkbox.set_on_change_listener
        self.onchange = self._checkbox.onchange


class CheckBox(Input):

    """check box widget usefull as numeric input field implements the onchange
    event.
    """

    def __init__(self, w, h, checked=False, user_data=''):
        super(CheckBox, self).__init__(w, h, 'checkbox', user_data)
        self.attributes[self.EVENT_ONCHANGE] = \
            "var params={};params['newValue']=document.getElementById('%(id)s').checked;"\
            "sendCallbackParam('%(id)s','%(evt)s',params);" % {'id':id(self),
                                                               'evt':self.EVENT_ONCHANGE}
        self.set_value(checked)

    def onchange(self, newValue):
        self.set_value( newValue in ('True', 'true') )
        return self.eventManager.propagate(self.EVENT_ONCHANGE, [newValue])

    def set_value(self, checked):
        if checked:
            self.attributes['checked']='checked'
        else:
            if 'checked' in self.attributes:
                del self.attributes['checked']

    def get_value(self):
        """returns the boolean value."""
        return 'checked' in self.attributes


class SpinBox(Input):

    """spin box widget usefull as numeric input field implements the onchange
    event.
    """

    def __init__(self, w, h, defaultValue='100', min=100, max=5000, step=1):
        super(SpinBox, self).__init__(w, h, 'number', defaultValue)
        self.attributes['min'] = str(min)
        self.attributes['max'] = str(max)
        self.attributes['step'] = str(step)
        self.attributes[self.EVENT_ONKEYPRESS] = 'return event.charCode >= 48 && event.charCode <= 57 || event.charCode == 46 || event.charCode == 13;'


class Slider(Input):

    def __init__(self, w, h, defaultValue='', min=0, max=10000, step=1):
        super(Slider, self).__init__(w, h, 'range', defaultValue)
        self.attributes['min'] = str(min)
        self.attributes['max'] = str(max)
        self.attributes['step'] = str(step)
        self.EVENT_ONINPUT = 'oninput'

    def oninput(self, newValue):
        return self.eventManager.propagate(self.EVENT_ONINPUT, [newValue])

    def set_oninput_listener(self, listener, funcname):
        self.attributes[self.EVENT_ONINPUT] = \
            "var params={};params['newValue']=document.getElementById('%(id)s').value;"\
            "sendCallbackParam('%(id)s','%(evt)s',params);" % {'id':id(self), 'evt':self.EVENT_ONINPUT}
        self.eventManager.register_listener(self.EVENT_ONINPUT, listener, funcname)


class ColorPicker(Input):

    def __init__(self, w, h, defaultValue='#995500'):
        super(ColorPicker, self).__init__(w, h, 'color', defaultValue)


class Date(Input):

    def __init__(self, w, h, defaultValue='2015-04-13'):
        super(Date, self).__init__(w, h, 'date', defaultValue)
        
        
class GenericObject(Widget):

    """
    GenericObject widget - allows to show embedded object like pdf,swf..
    """

    def __init__(self, w, h, filename):
        """filename should be an URL."""
        super(GenericObject, self).__init__(w, h)
        self.type = 'object'
        self.attributes['data'] = filename


class FileFolderNavigator(Widget):

    """FileFolderNavigator widget."""

    def __init__(self, w, h, multiple_selection,selection_folder):
        super(FileFolderNavigator, self).__init__(w, h, Widget.LAYOUT_VERTICAL)
        self.w = w
        self.h = h
        self.multiple_selection = multiple_selection

        self.selectionlist = []
        self.controlsContainer = Widget(w, 25, Widget.LAYOUT_HORIZONTAL)
        self.controlBack = Button(45, 25, 'Up')
        self.controlBack.set_on_click_listener(self, 'dir_go_back')
        self.controlGo = Button(45, 25, 'Go >>')
        self.controlGo.set_on_click_listener(self, 'dir_go')
        self.pathEditor = TextInput(w-90, 25)
        self.pathEditor.style['resize'] = 'none'
        self.pathEditor.attributes['rows'] = '1'
        self.controlsContainer.append('1', self.controlBack)
        self.controlsContainer.append('2', self.pathEditor)
        self.controlsContainer.append('3', self.controlGo)

        self.itemContainer = Widget(w, h-25, Widget.LAYOUT_VERTICAL)
        self.itemContainer.style['overflow-y'] = 'scroll'
        self.itemContainer.style['overflow-x'] = 'hidden'

        self.append('controls', self.controlsContainer)
        self.append('items', self.itemContainer)

        self.folderItems = list()

        # fixme: we should use full paths and not all this chdir stuff
        self.chdir(selection_folder)  # move to actual working directory

    def get_selection_list(self):
        return self.selectionlist

    def populate_folder_items(self,directory):
        def _sort_files(a,b):
            if os.path.isfile(a) and os.path.isdir(b):
                return 1
            elif os.path.isfile(b) and os.path.isdir(a):
                return -1
            else:
                try:
                    if a[0] == '.': a = a[1:]
                    if b[0] == '.': b = b[1:]
                    return (a.lower() > b.lower())
                except (IndexError, ValueError):
                    return (a > b)

        log.debug("FileFolderNavigator - populate_folder_items")

        l = os.listdir(directory)
        l.sort(key=cmp_to_key(_sort_files))

        # used to restore a valid path after a wrong edit in the path editor
        self.lastValidPath = directory 
        # we remove the container avoiding graphic update adding items
        # this speeds up the navigation
        self.remove(self.itemContainer)
        # creation of a new instance of a itemContainer
        self.itemContainer = Widget(self.w,self.h-25,Widget.LAYOUT_VERTICAL)
        self.itemContainer.style['overflow-y'] = 'scroll'
        self.itemContainer.style['overflow-x'] = 'hidden'

        for i in l:
            full_path = os.path.join(directory, i)
            is_folder = not os.path.isfile(full_path)
            fi = FileFolderItem(self.w, 33, i, is_folder)
            fi.set_on_click_listener(self, 'on_folder_item_click')  # navigation purpose
            fi.set_on_selection_listener(self, 'on_folder_item_selected')  # selection purpose
            self.folderItems.append(fi)
            self.itemContainer.append(i, fi)
        self.append('items', self.itemContainer)

    def dir_go_back(self):
        curpath = os.getcwd()  # backup the path
        try:
            os.chdir( self.pathEditor.get_text() )
            os.chdir('..')
            self.chdir(os.getcwd())
        except Exception as e:
            self.pathEditor.set_text(self.lastValidPath)
            log.error('error changing directory', exc_info=True)
        os.chdir(curpath)  # restore the path

    def dir_go(self):
        # when the GO button is pressed, it is supposed that the pathEditor is changed
        curpath = os.getcwd()  # backup the path
        try:
            os.chdir(self.pathEditor.get_text())
            self.chdir(os.getcwd())
        except Exception as e:
            log.error('error going to directory', exc_info=True)
            self.pathEditor.set_text(self.lastValidPath)
        os.chdir(curpath)  # restore the path

    def chdir(self, directory):
        curpath = os.getcwd()  # backup the path
        log.debug("FileFolderNavigator - chdir: %s" % directory)
        for c in self.folderItems:
            self.itemContainer.remove(c)  # remove the file and folders from the view
        self.folderItems = []
        self.selectionlist = []  # reset selected file list
        os.chdir(directory)
        directory = os.getcwd()
        self.populate_folder_items(directory)
        self.pathEditor.set_text(directory)
        os.chdir(curpath)  # restore the path

    def on_folder_item_selected(self,folderitem):
        if not self.multiple_selection:
            self.selectionlist = []
            for c in self.folderItems:
                c.set_selected(False)
            folderitem.set_selected(True)
        log.debug("FileFolderNavigator - on_folder_item_click")
        # when an item is clicked it is added to the file selection list
        f = os.path.join(self.pathEditor.get_text(), folderitem.get_text())
        if f in self.selectionlist:
            self.selectionlist.remove(f)
        else:
            self.selectionlist.append(f)

    def on_folder_item_click(self,folderitem):
        log.debug("FileFolderNavigator - on_folder_item_dblclick")
        # when an item is clicked two time
        f = os.path.join(self.pathEditor.get_text(), folderitem.get_text())
        if not os.path.isfile(f):
            self.chdir(f)

    def get_selected_filefolders(self):
        return self.selectionlist


class FileFolderItem(Widget):

    """FileFolderItem widget for the FileFolderNavigator"""

    def __init__(self, w, h, text, isFolder=False):
        super(FileFolderItem, self).__init__(w, h, Widget.LAYOUT_HORIZONTAL)
        self.EVENT_ONSELECTION = 'onselection'
        self.attributes[self.EVENT_ONCLICK] = ''
        self.icon = Widget(33, h)
        # the icon click activates the onselection event, that is propagates to registered listener
        if isFolder:
            self.icon.set_on_click_listener(self, self.EVENT_ONCLICK)
        self.icon.attributes['class'] = 'FileFolderItemIcon'
        icon_file = 'res/folder.png' if isFolder else 'res/file.png'
        self.icon.style['background-image'] = "url('%s')" % icon_file
        self.label = Label(w-33, h, text)
        self.label.set_on_click_listener(self, self.EVENT_ONSELECTION)
        self.append('icon', self.icon)
        self.append('text', self.label)
        self.selected = False

    def onclick(self):
        return self.eventManager.propagate(self.EVENT_ONCLICK, [self])

    def set_on_click_listener(self, listener, funcname):
        self.eventManager.register_listener(self.EVENT_ONCLICK, listener, funcname)

    def set_selected(self, selected):
        self.selected = selected
        self.style['color'] = 'red' if self.selected else 'black'

    def onselection(self):
        self.set_selected(not self.selected)
        return self.eventManager.propagate(self.EVENT_ONSELECTION, [self])

    def set_on_selection_listener(self, listener, funcname):
        self.eventManager.register_listener(self.EVENT_ONSELECTION, listener, funcname)

    def set_text(self, t):
        """sets the text content."""
        self.children['text'].set_text(t)

    def get_text(self):
        return self.children['text'].get_text()


class FileSelectionDialog(GenericDialog):

    """file selection dialog, it opens a new webpage allows the OK/CANCEL functionality
    implementing the "confirm_value" and "cancel_dialog" events."""

    def __init__(self, width = 600, fileFolderNavigatorHeight=210, title='File dialog',
                 message='Select files and folders', multiple_selection=True, selection_folder='.'):
        super(FileSelectionDialog, self).__init__(width, 80, title, message)
        self.fileFolderNavigator = FileFolderNavigator(width-30, fileFolderNavigatorHeight,
                                                       multiple_selection, selection_folder)
        self.add_field('fileFolderNavigator',self.fileFolderNavigator)
        self.EVENT_ONCONFIRMVALUE = 'confirm_value'
        self.set_on_confirm_dialog_listener(self, 'confirm_value')

    def confirm_value(self):
        """event called pressing on OK button.
           propagates the string content of the input field
        """
        self.hide()
        params = [self.fileFolderNavigator.get_selection_list()]
        return self.eventManager.propagate(self.EVENT_ONCONFIRMVALUE, params)

    def set_on_confirm_value_listener(self, listener, funcname):
        self.eventManager.register_listener(self.EVENT_ONCONFIRMVALUE, listener, funcname)


class MenuBar(Widget):
    def __init__(self, w, h, orientation=Widget.LAYOUT_HORIZONTAL):
        super(MenuBar, self).__init__(w, h, orientation)
        self.type = 'nav'


class Menu(Widget):

    """Menu widget can contain MenuItem."""

    def __init__(self, w, h, orientation=Widget.LAYOUT_HORIZONTAL):
        super(Menu, self).__init__(w, h, orientation)
        self.type = 'ul'


class MenuItem(Widget):

    """MenuItem widget can contain other MenuItem."""

    def __init__(self, w, h, text):
        super(MenuItem, self).__init__(w, h)
        self.w = w
        self.h = h
        self.subcontainer = None
        self.type = 'li'
        self.attributes[self.EVENT_ONCLICK] = ''
        self.set_text(text)
        self.append = self.addSubMenu

    def addSubMenu(self, key, value):
        if self.subcontainer is None:
            self.subcontainer = Menu(self.w, self.h, Widget.LAYOUT_VERTICAL)
            super(MenuItem, self).append('subcontainer', self.subcontainer)
        self.subcontainer.append(key, value)

    def set_text(self, text):
        self.append('text', text)

    def get_text(self):
        return self.children['text']


class FileUploader(Widget):

    """
    FileUploader widget:
        allows to upload multiple files to a specified folder.
        implements the onsuccess and onfailed events.
    """

    def __init__(self, w, h, savepath='./', multiple_selection_allowed=False):
        super(FileUploader, self).__init__(w, h)
        self._savepath = savepath
        self._multiple_selection_allowed = multiple_selection_allowed
        self.type = 'input'
        self.attributes['type'] = 'file'
        if multiple_selection_allowed:
            self.attributes['multiple'] = 'multiple'
        self.attributes['accept'] = '*.*'
        self.attributes[self.EVENT_ONCLICK] = ''
        self.EVENT_ON_SUCCESS = 'onsuccess'
        self.EVENT_ON_FAILED = 'onfailed'

        self.attributes[self.EVENT_ONCHANGE] = \
            "var files = this.files;"\
            "for(var i=0; i<files.length; i++){"\
            "uploadFile('%(id)s','%(evt_success)s','%(evt_failed)s','%(savepath)s',files[i]);}" % {
                'id':id(self), 'evt_success':self.EVENT_ON_SUCCESS, 'evt_failed':self.EVENT_ON_FAILED,
                'savepath':self._savepath}

    def onsuccess(self,filename):
        return self.eventManager.propagate(self.EVENT_ON_SUCCESS, [filename])

    def set_on_success_listener(self, listener, funcname):
        self.eventManager.register_listener(
            self.EVENT_ON_SUCCESS, listener, funcname)

    def onfailed(self,filename):
        return self.eventManager.propagate(self.EVENT_ON_FAILED, [filename])

    def set_on_failed_listener(self, listener, funcname):
        self.eventManager.register_listener(self.EVENT_ON_FAILED, listener, funcname)
        

class FileDownloader(Widget):

    """FileDownloader widget. Allows to start a file download."""

    def __init__(self, w, h, text, filename, path_separator='/'):
        super(FileDownloader, self).__init__(w, h, Widget.LAYOUT_HORIZONTAL)
        self.type = 'a'
        self.attributes['download'] = os.path.basename(filename)
        self.attributes['href'] = "/%s/download" % id(self)
        self.set_text(text)
        self._filename = filename
        self._path_separator = path_separator

    def set_text(self, t):
        self.append('text', t)

    def download(self):
        with open(self._filename, 'r+b') as f:
            content = f.read()
        headers = {'Content-type':'application/octet-stream',
                   'Content-Disposition':'attachment; filename=%s' % os.path.basename(self._filename)}
        return [content,headers]


class Link(Widget):

    def __init__(self, w, h, url, text, open_new_window=True):
        super(Link, self).__init__(w, h)
        self.type = 'a'
        self.attributes['href'] = url
        if open_new_window:
            self.attributes['target'] = "_blank"
        self.set_text(text)

    def set_text(self, t):
        self.append('text', t)

    def get_text(self):
        return self.children['text']

    def get_url(self):
        return self.children['href']


class VideoPlayer(Widget):

    def __init__(self, w, h, video, poster=None):
        super(VideoPlayer, self).__init__(w, h, Widget.LAYOUT_HORIZONTAL)
        self.type = 'video'
        self.attributes['src'] = video
        self.attributes['preload'] = 'auto'
        self.attributes['controls'] = None
        self.attributes['poster'] = poster
        

class Svg(Widget):
    def __init__(self, width, height):
        super(Svg, self).__init__(width, height)
        self.attributes['width'] = width
        self.attributes['height'] = height
        self.type = 'svg'
        
    def set_viewbox(self, x, y, w, h):
        self.attributes['viewBox'] = "%s %s %s %s"%(x,y,w,h)
        self.attributes['preserveAspectRatio'] = 'none'
        

class SvgCircle(Widget):
    def __init__(self, x, y, radix):
        super(SvgCircle, self).__init__(0, 0)
        self.set_position(x, y)
        self.set_radix(radix)
        self.set_stroke()
        self.type = 'circle'
    
    def set_position(self, x, y):
        self.attributes['cx'] = x
        self.attributes['cy'] = y
        
    def set_radix(self, radix):
        self.attributes['r'] = radix
        
    def set_stroke(self, width=1, color='black'):
        self.attributes['stroke'] = color
        self.attributes['stroke-width'] = str(width)

    def set_fill(self, color):
        self.attributes['fill'] = color


class SvgLine(Widget):
    def __init__(self, x1, y1, x2, y2):
        super(SvgLine, self).__init__(0, 0)
        self.set_coords(x1, y1, x2, y2)
        self.set_stroke()
        self.type = 'line'
    
    def set_coords(self, x1, y1, x2, y2):
        self.set_p1(x1, y1)
        self.set_p2(x2, y2)
        
    def set_p1(self, x1, y1):
        self.attributes['x1'] = x1
        self.attributes['y1'] = y1
    
    def set_p2(self, x2, y2):
        self.attributes['x2'] = x2
        self.attributes['y2'] = y2
    
    def set_stroke(self, width=1, color='black'):
        self.style['stroke'] = color
        self.style['stroke-width'] = str(width)
        

class SvgPolyline(Widget):
    def __init__(self):
        super(SvgPolyline, self).__init__(0, 0)
        self.set_stroke()
        self.style['fill'] = 'none'
        self.type = 'polyline'
        self.coordsX = list()
        self.coordsY = list()
        self.max_len = 0 #no limit
        self.attributes['points'] = ''

    def add_coord(self, x, y):
        if self.max_len > 0:
            if len(self.coordsX) > self.max_len:
                #we assume that if there is some chars, there is a space
                if len(self.attributes['points']) > 1: #slower performaces if ' ' in self.attributes['points'] :
                    self.attributes['points'] = self.attributes['points'][self.attributes['points'].find(' ')+1:]
                self.coordsX = self.coordsX[len(self.coordsX)-self.max_len:]
                self.coordsY = self.coordsY[len(self.coordsY)-self.max_len:]
        self.coordsX.append(x)
        self.coordsY.append(y)
        self.attributes['points'] = self.attributes['points'] + "%s,%s "%(x,y)
    
    def set_max_len(self, value):
        self.max_len = value
        if len(self.coordsX) > self.max_len:
            self.attributes['points'] = ' '.join(map(lambda x,y: str(x) + ',' + str(y), self.coordsX, self.coordsY))
            self.coordsX = self.coordsX[len(self.coordsX)-self.max_len:]
            self.coordsY = self.coordsY[len(self.coordsY)-self.max_len:]
        
    def set_stroke(self, width=1, color='black'):
        self.style['stroke'] = color
        self.style['stroke-width'] = str(width)
        

class SvgText(Widget):
    def __init__(self, x, y, text):
        super(SvgText, self).__init__(0, 0)
        self.type = 'text'
        self.set_position(x, y)
        self.set_fill()
        self.set_text(text)

    def set_text(self, text):
        self.append('text', text)
    
    def set_position(self, x, y):
        self.attributes['x'] = str(x)
        self.attributes['y'] = str(y)
    
    def set_fill(self, color='black'):
        self.attributes['fill'] = color
        
