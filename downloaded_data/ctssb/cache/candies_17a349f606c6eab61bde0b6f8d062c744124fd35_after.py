#!/usr/bin/env python
# -*- coding: utf-8 -*-

import gobject
import clutter

class Box(clutter.Actor, clutter.Container):
    """
    A stacking box container.
    
    Works horizontally and vertically (see HBox and VBox for shortcut classes).
    
    The elements contained in a box are defined by a clutter actor (the
    children of the container), a name (str) and optional properties.
    
    If bg_ignore_allocation_box is set to True, the box will allocate
    his background bypassing the allocation box height.
    
    Element properties can be :
    
        - resizable (float) : if set, defines the proportion an element take in
          the available place (value is between 0 and 1). It applies to width
          in horizontal box and to height in vertical one.
        
        - expand (bool) : if True, the element size is expanded on the whole
          box height (for horizontal boxes) and on the whole box width (for
          vertical ones).
        
        - keep_ratio (bool) : if True, the element resized because of the
          resizable or expand properties while keep its natural aspect ratio.
          (Please don't set it to True when resizable and expand are both set!)
        
        - center (bool) : if True, the element is centered (vertically for
          horizontal box and vice-versa).
    """
    __gtype_name__ = 'Box'
    
    def __init__(self, horizontal=True, spacing=0, padding=0, bg_ignore_allocation_box=True):
        clutter.Actor.__init__(self)
        self.elements = list()
        self.background = None
        self.overlay = None
        self.spacing = spacing
        self.padding = padding
        if horizontal:
            self._horizontal = True
        else:
            self._horizontal = False
        if bg_ignore_allocation_box == True:
            self.bg_ignore_allocation_box = True
        else:
            self.bg_ignore_allocation_box = False
    
    def get_by_name(self, name):
        for element in self.elements:
            if element['name'] == name:
                return element
        return None
    
    def set_horizontal(self, boolean):
        if boolean:
            self._horizontal = True
        else:
            self._horizontal = False
    
    def set_background(self, background):
        self.background = background
        background.set_parent(self)
    
    def set_overlay(self, overlay):
        self.overlay = overlay
        self.overlay.hide()
        overlay.set_parent(self)
    
    def remove_background(self):
        if self.background:
            self.background.unparent()
            self.background = None
    
    def remove_overlay(self):
        if self.overlay:
            self.overlay.unparent()
            self.overlay = None
    
    def show_overlay(self):
        if self.overlay:
            if self.background:
                self.background.hide()
            for element in self.elements:
                element['object'].hide()
            self.overlay.show()
    
    def hide_overlay(self):
        if self.overlay:
            self.overlay.hide()
            if self.background:
                self.background.show()
            for element in self.elements:
                element['object'].show()
    
    def add(self, *new_elements):
        for new_ele in new_elements:
            if 'name' not in new_ele or 'object' not in new_ele:
                raise KeyError('Can not add element to box. Element to add must be a dict with at least "name" and "object" in his keys')
            self.elements.append(new_ele)
            new_ele['object'].set_parent(self)
        self.queue_relayout()
    
    def add_element(self, obj, name, index=-1, **properties):
        element = properties.copy()
        element['name'] = name
        element['object'] = obj
        if index == -1 or index < 0 or index > len(self.elements):
            self.elements.append(element)
        else:
            self.elements.insert(index, element)
        obj.set_parent(self)
        self.queue_relayout()
    
    def do_remove(self, *children):
        for child in children:
            if self.background == child:
                child.unparent()
                self.background = None
            if self.overlay == child:
                child.unparent()
                self.overlay = None
            for element in self.elements:
                if element['object'] == child:
                    child.unparent()
                    self.elements.remove(element)
    
    def remove_element(self, name):
        element = self.get_by_name(name)
        if element:
            element['object'].unparent()
            self.elements.remove(element)
            return True
        else:
            return False
    
    def remove_all_elements(self):
        for element in self.elements:
            element['object'].unparent()
        self.elements = list()
    
    def clear(self):
        for element in self.elements:
            element['object'].unparent()
            element['object'].destroy()
        self.elements = list()
        if self.background:
            self.background.unparent()
            self.background.destroy()
            self.background = None
        if self.overlay:
            self.overlay.unparent()
            self.overlay.destroy()
            self.overlay = None
    
    def do_get_preferred_width(self, for_height):
        inner_height = for_height - 2*self.padding
        preferred_width = 0
        if self._horizontal is False:
            #find size available for special elements with expand and keep_ratio
            special_elements = list()
            special_height = inner_height
            for element in self.elements:
                #take preferred size for resizable elements in preferred size calcul
                if element.get('resizable', 0) != 0:
                    pass
                else:
                    if element.get('expand') is True and element.get('keep_ratio') is True:
                        special_elements.append(element)
                    else:
                        special_height -= element['object'].get_preferred_size()[3]
                special_height -= self.spacing
            special_height += self.spacing
            
            #find size available for resizable elements
            resizable_elements = list()
            resizable_height = inner_height
            for element in self.elements:
                if element.get('resizable', 0) != 0:
                    if element['resizable'] > 1:
                        element['resizable'] = 1
                    elif element['resizable'] < 0:
                        element['resizable'] = 0
                    resizable_elements.append(element)
                else:
                    resizable_height -= element['object'].get_preferred_size()[3]
                resizable_height -= self.spacing
            if resizable_height != inner_height:
                resizable_height += self.spacing
                if special_elements:
                    resizable_height -= special_height
            
            #find maximum object width
            for element in self.elements:
                obj_width = element['object'].get_preferred_size()[2]
                used_width = obj_width
                if element.get('resizable', 0) != 0:
                    original_height = element['object'].get_preferred_size()[3]
                    if element.get('keep_ratio') is True and original_height != 0 and for_height != -1:
                        obj_height = element['resizable'] * resizable_height
                        factor = float(obj_height)/float(original_height)
                        used_width = int(obj_width*factor)
                obj_height = element['object'].get_preferred_size()[3]
                if element.get('expand') is True and element.get('keep_ratio') is True and obj_width != 0 and obj_height != 0:
                    ratio = float(obj_width) / float(obj_height)
                    used_width = int(special_height * ratio)
                preferred_width = max(preferred_width, used_width)
        else:
            for element in self.elements:
                obj_width = element['object'].get_preferred_size()[2]
                used_width = obj_width
                if element.get('keep_ratio') is True and obj_width != 0 and element.get('expand') is True and for_height != -1:
                    obj_height = element['object'].get_preferred_size()[3]
                    ratio = float(obj_width) / float(obj_height)
                    used_width = int(inner_height * ratio)
                preferred_width += used_width + self.spacing
        
            if preferred_width != 0:
                preferred_width -= self.spacing
        
        preferred_width += 2*self.padding
        return preferred_width, preferred_width
    
    def do_get_preferred_height(self, for_width):
        inner_width = for_width - 2*self.padding
        preferred_height = 0
        if self._horizontal is True:
            #find size available for special elements with expand and keep_ratio
            special_elements = list()
            special_width = inner_width
            for element in self.elements:
                #take preferred size for resizable elements in preferred size calcul
                if element.get('resizable', 0) != 0:
                    pass
                else:
                    if element.get('expand') is True and element.get('keep_ratio') is True:
                        special_elements.append(element)
                    else:
                        special_width -= element['object'].get_preferred_size()[2]
                special_width -= self.spacing
            special_width += self.spacing
            
            #find size available for resizable elements
            resizable_elements = list()
            resizable_width = inner_width
            for element in self.elements:
                if element.get('resizable', 0) != 0:
                    if element['resizable'] > 1:
                        element['resizable'] = 1
                    elif element['resizable'] < 0:
                        element['resizable'] = 0
                    resizable_elements.append(element)
                else:
                    resizable_width -= element['object'].get_preferred_size()[2]
                resizable_width -= self.spacing
            if resizable_width != inner_width:
                resizable_width += self.spacing
                if special_elements:
                    resizable_width -= special_width
            
            #find maximum object height
            for element in self.elements:
                obj_height = element['object'].get_preferred_size()[3]
                used_height = obj_height
                if element.get('resizable', 0) != 0:
                    original_width = element['object'].get_preferred_size()[2]
                    if element.get('keep_ratio') is True and original_width != 0 and for_width != -1:
                        obj_width = element['resizable'] * resizable_width
                        factor = float(obj_width) / float(original_width)
                        used_height = int(obj_height*factor)
                preferred_height = max(preferred_height, used_height)
                obj_width = element['object'].get_preferred_size()[3]
                if element.get('expand') is True and element.get('keep_ratio') is True and obj_width != 0 and obj_height != 0:
                    ratio = float(obj_width) / float(obj_height)
                    used_height = int(special_width / ratio)
                preferred_height = max(preferred_height, used_height)
        else:
            preferred_height = 0
            for element in self.elements:
                obj_height = element['object'].get_preferred_size()[3]
                used_height = obj_height
                if element.get('keep_ratio') is True and obj_height != 0 and element.get('expand') is True and for_width != -1:
                    obj_width = element['object'].get_preferred_size()[2]
                    ratio = float(obj_width) / float(obj_height)
                    used_height = int(inner_width / ratio)
                preferred_height += used_height + self.spacing
        
            if preferred_height != 0:
                preferred_height -= self.spacing
        
        preferred_height += 2*self.padding
        return preferred_height, preferred_height
    
    def do_allocate(self, box, flags):
        main_width = box.x2 - box.x1
        main_height = box.y2 - box.y1
        inner_width = main_width - 2*self.padding
        inner_height = main_height - 2*self.padding
        
        #find size available for special elements with expand and keep_ratio, ignoring elements with resizable
        special_elements = list()
        special_width = inner_width
        special_height = inner_height
        needed_width = 0
        needed_height = 0
        for element in self.elements:
            if element.get('resizable', 0) != 0:
                pass
            else:
                if element.get('expand') is True and element.get('keep_ratio') is True:
                    special_elements.append(element)
                else:
                    special_width -= element['object'].get_preferred_size()[2]
                    special_height -= element['object'].get_preferred_size()[3]
            special_width -= self.spacing
            special_height -= self.spacing
        special_width += self.spacing
        special_height += self.spacing
        
        #check if some place will remain for resizable elements
        for element in special_elements:
            original_width = element['object'].get_preferred_size()[2]
            original_height = element['object'].get_preferred_size()[3]
            if self._horizontal is True:
                obj_width = original_width
                obj_height = inner_height
                if original_width != 0 and original_height != 0:
                    factor = float(obj_height) / float(original_height)
                    obj_width = int(original_width * factor)
                    if obj_width > special_width:
                        obj_width = int(special_width)
                        special_width = 0
                        ratio = float(original_width) / float(original_height)
                        obj_height = int(float(obj_width) / ratio)
                    else:
                        special_width -= obj_width
                needed_width += obj_width
            else:
                obj_width = inner_width
                obj_height = original_height
                if element.get('keep_ratio') is True and original_width != 0 and original_height != 0:
                    factor = float(obj_width) / float(original_width)
                    obj_height = int(original_height * factor)
                    if obj_height > special_height:
                        obj_height = int(special_height)
                        special_height = 0
                        ratio = float(original_width) / float(original_height)
                        obj_width = int(float(obj_height) * ratio)
                    else:
                        special_height -= obj_height
                needed_height += obj_height
        special_width = needed_width
        special_height = needed_height
        
        #find size available for resizable elements
        resizable_elements = list()
        resizable_width = inner_width
        resizable_height = inner_height
        for element in self.elements:
            if element.get('resizable', 0) != 0:
                if element['resizable'] > 1:
                    element['resizable'] = 1
                elif element['resizable'] < 0:
                    element['resizable'] = 0
                resizable_elements.append(element)
            else:
                if element.get('expand') is True and element.get('keep_ratio') is True:
                    pass
                else:
                    resizable_width -= element['object'].get_preferred_size()[2]
                    resizable_height -= element['object'].get_preferred_size()[3]
            resizable_width -= self.spacing
            resizable_height -= self.spacing
        resizable_width += self.spacing
        resizable_height += self.spacing
        if special_elements:
            resizable_width -= special_width
            resizable_height -= special_height
        
        #find resizable elements who will bypass box size
        for element in self.elements:
            if element.get('resizable', 0) != 0:
                original_width, original_height = element['object'].get_preferred_size()[2:]
                if self._horizontal is True:
                    if element.get('keep_ratio') is True and original_width != 0:
                        obj_width = element['resizable'] * resizable_width
                        ratio = float(obj_width/original_width)
                        obj_height = int(original_height*ratio)
                        if obj_height > inner_height:
                            # reduce resizable property
                            ratio = float(inner_height/original_height)
                            obj_width = int(original_width*ratio)
                            element['resizable'] = float(obj_width/resizable_width)
                else:
                    if element.get('keep_ratio') is True and original_height != 0:
                        obj_height = element['resizable'] * resizable_height
                        ratio = float(obj_height/original_height)
                        obj_width = int(original_width*ratio)
                        if obj_width > inner_width:
                            # reduce resizable property
                            ratio = float(inner_width/original_width)
                            obj_height = int(original_height*ratio)
                            element['resizable'] = float(obj_height/resizable_height)
        
        x = self.padding
        y = self.padding
        for element in self.elements:
            obj_width, obj_height = element['object'].get_preferred_size()[2:]
            if element.get('expand') is True:
                original_height = obj_height
                original_width = obj_width
                if self._horizontal is True:
                    obj_height = inner_height
                    if element.get('keep_ratio') is True and original_width != 0 and original_height != 0:
                        factor = float(obj_height) / float(original_height)
                        obj_width = int(original_width * factor)
                        if obj_width > special_width:
                            obj_width = int(special_width)
                            special_width = 0
                            ratio = float(original_width) / float(original_height)
                            obj_height = int(float(obj_width) / ratio)
                        else:
                            special_width -= obj_width
                else:
                    obj_width = inner_width
                    if element.get('keep_ratio') is True and original_width != 0 and original_height != 0:
                        factor = float(obj_width) / float(original_width)
                        obj_height = int(original_height * factor)
                        if obj_height > special_height:
                            obj_height = int(special_height)
                            special_height = 0
                            ratio = float(original_width) / float(original_height)
                            obj_width = int(float(obj_height) * ratio)
                        else:
                            special_height -= obj_height
            if element in resizable_elements:
                if self._horizontal is True:
                    original_width = obj_width
                    obj_width = element['resizable'] * resizable_width
                    if element.get('keep_ratio') is True and original_width != 0:
                        ratio = float(obj_width/original_width)
                        obj_height = int(obj_height*ratio)
                else:
                    original_height = obj_height
                    obj_height = element['resizable'] * resizable_height
                    if element.get('keep_ratio') is True and original_height != 0:
                        ratio = float(obj_height/original_height)
                        obj_width = int(obj_width*ratio)
            # Manage centering
            x_offset = 0
            y_offset = 0
            if element.get('center') is True:
                if self._horizontal is True:
                    y_offset = max(0, (inner_height - obj_height) / 2)
                else:
                    x_offset = max(0, (inner_width - obj_width) / 2)
            
            objbox = clutter.ActorBox()
            objbox.x1 = round(x + x_offset)
            objbox.y1 = round(y + y_offset)
            objbox.x2 = round(x + x_offset + obj_width)
            objbox.y2 = round(y + y_offset + obj_height)
            element['object'].allocate(objbox, flags)
            if self._horizontal is True:
                x += obj_width + self.spacing
            else:
                y += obj_height + self.spacing
        
        #box background
        if self.background:
            if self.bg_ignore_allocation_box == True and len(self.elements) > 0:
                if self._horizontal is True:
                    bgbox = clutter.ActorBox()
                    bgbox.x1 = 0
                    bgbox.y1 = 0
                    bgbox.x2 = self.padding + round(x) - self.spacing
                    bgbox.y2 = main_height
                    self.background.allocate(bgbox, flags)
                else:
                    bgbox = clutter.ActorBox()
                    bgbox.x1 = 0
                    bgbox.y1 = 0
                    bgbox.x2 = main_width
                    bgbox.y2 = self.padding + round(y) - self.spacing
                    self.background.allocate(bgbox, flags)
            else:
                bgbox = clutter.ActorBox()
                bgbox.x1 = 0
                bgbox.y1 = 0
                bgbox.x2 = main_width
                bgbox.y2 = main_height
                self.background.allocate(bgbox, flags)
        
        #box overlay
        if self.overlay:
            if self.bg_ignore_allocation_box == True and len(self.elements) > 0:
                if self._horizontal is True:
                    ovbox = clutter.ActorBox()
                    ovbox.x1 = self.padding
                    ovbox.y1 = self.padding
                    ovbox.x2 = round(x) - self.spacing
                    ovbox.y2 = main_height - self.padding
                    self.overlay.allocate(ovbox, flags)
                else:
                    ovbox = clutter.ActorBox()
                    ovbox.x1 = self.padding
                    ovbox.y1 = self.padding
                    ovbox.x2 = main_width - self.padding
                    ovbox.y2 = round(y) - self.spacing
                    self.overlay.allocate(ovbox, flags)
            else:
                ovbox = clutter.ActorBox()
                ovbox.x1 = self.padding
                ovbox.y1 = self.padding
                ovbox.x2 = main_width - self.padding
                ovbox.y2 = main_height - self.padding
                self.overlay.allocate(ovbox, flags)
        
        clutter.Actor.do_allocate(self, box, flags)
    
    def set_bg_ignore_allocation_box(self, state):
        if state:
            self.bg_ignore_allocation_box = True
        else:
            self.bg_ignore_allocation_box = False
        self.queue_redraw()
    
    def do_foreach(self, func, data=None):
        if self.background:
            func(self.background, data)
        if self.overlay:
            func(self.overlay, data)
        for element in self.elements:
            func(element['object'], data)
    
    def do_paint(self):
        if self.background:
            self.background.paint()
        if self.overlay:
            self.overlay.paint()
        draw_last_objects = list()
        for element in self.elements:
            if element.get('draw_last'):
                draw_last_objects.append(element['object'])
            else:
                element['object'].paint()
        for obj in draw_last_objects:
            obj.paint()
    
    def do_pick(self, color):
        self.do_paint()
    
    def do_destroy(self):
        self.unparent()
        if hasattr(self, 'elements'):
            for element in self.elements:
                element['object'].unparent()
                element['object'].destroy()
            self.elements = list()
        if hasattr(self, 'background'):
            if self.background:
                self.background.unparent()
                self.background.destroy()
                self.background = None
        if hasattr(self, 'overlay'):
            if self.overlay:
                self.overlay.unparent()
                self.overlay.destroy()
                self.overlay = None

class HBox(Box):
    
    def __init__(self, *args, **kw):
        Box.__init__(self, horizontal=True, *args, **kw)

class VBox(Box):
    
    def __init__(self, *args, **kw):
        Box.__init__(self, horizontal=False, *args, **kw)

class AlignedElement(clutter.Actor, clutter.Container):
    __gtype_name__ = 'AlignedElement'

    def __init__(self, align='center', padding=0, expand=False, keep_ratio=True, pick_enabled=True):
        clutter.Actor.__init__(self)
        if align == 'top_left':
            self.align = 'top_left'
        elif align == 'top':
            self.align = 'top'
        elif align == 'top_right':
            self.align = 'top_right'
        elif align == 'left':
            self.align = 'left'
        elif align == 'center':
            self.align = 'center'
        elif align == 'right':
            self.align = 'right'
        elif align == 'bottom_left':
            self.align = 'bottom_left'
        elif align == 'bottom':
            self.align = 'bottom'
        elif align == 'bottom_right':
            self.align = 'bottom_right'
        else:
            self.align = 'center'
        self.padding = padding
        self.expand = expand
        self.keep_ratio = keep_ratio
        self.element = None
        self.background = None
        self.pick_enabled = pick_enabled
    
    def set_background(self, background):
        if self.background is not None:
            self.background.unparent()
        self.background = background
        background.set_parent(self)
    
    def remove_background(self):
        if self.background is not None:
            self.background.unparent()
            self.background = None
    
    def set_element(self, new_element):
        if self.element is not None:
            self.element.unparent()
        self.element = new_element
        self.element.set_parent(self)
    
    def remove_element(self):
        if self.element is not None:
            self.element.unparent()
            self.element = None
    
    def do_remove(self, actor):
        if self.background == actor:
            actor.unparent()
            self.background = None
        if self.element == actor:
            actor.unparent()
            self.elements = None
    
    def clear(self):
        if self.element is not None:
            self.element.destroy()
            self.element = None
        if self.background is not None:
            self.background.destroy()
            self.background = None
    
    def do_get_preferred_width(self, for_height):
        if self.element is not None:
            if self.expand == True:
                preferred_size = self.element.get_preferred_size()
                element_width = preferred_size[2]
                element_height = preferred_size[3]
                if self.keep_ratio == True and element_width != 0 and element_height != 0 and for_height != -1:
                    ratio = float(float(element_width) / float(element_height))
                    prefered_width = int(for_height * ratio) + 2*self.padding
                else:
                    prefered_width = element_width + 2*self.padding
            else:
                element_width = self.element.get_preferred_size()[2]
                prefered_width = element_width + 2*self.padding
            return prefered_width, prefered_width
        else:
            return 0, 0
    
    def do_get_preferred_height(self, for_width):
        if self.element is not None:
            if self.expand == True:
                preferred_size = self.element.get_preferred_size()
                element_width = preferred_size[2]
                element_height = preferred_size[3]
                if self.keep_ratio == True and element_width != 0 and element_height != 0 and for_width != -1:
                    ratio = float(float(element_height) / float(element_width))
                    prefered_height = int(for_width / ratio) + 2*self.padding
                else:
                    prefered_height = element_height + 2*self.padding
            else:
                element_height = self.element.get_preferred_size()[3]
                prefered_height = element_height + 2*self.padding
            return prefered_height, prefered_height
        else:
            return 0, 0
    
    def do_allocate(self, box, flags):
        main_width = box.x2 - box.x1
        main_height = box.y2 - box.y1
        inner_width = main_width - 2*self.padding
        inner_height = main_height - 2*self.padding
        
        #box background
        if self.background:
            bgbox = clutter.ActorBox()
            bgbox.x1 = 0
            bgbox.y1 = 0
            bgbox.x2 = main_width
            bgbox.y2 = main_height
            self.background.allocate(bgbox, flags)
        
        if self.element:
            element_width, element_height = self.element.get_preferred_size()[2:]
            ele_x1 = self.padding
            ele_y1 = self.padding
            ele_x2 = self.padding
            ele_y2 = self.padding
            if self.expand == True:
                if self.keep_ratio == True and element_height != 0:
                    ratio = float(float(element_width) / float(element_height))
                    element_width = inner_width
                    element_height = int(element_width / ratio)
                    if element_width > inner_width:
                        element_width = inner_width
                        element_height = int(element_width / ratio)
                    if element_height > inner_height:
                        element_height = inner_height
                        element_width = int(element_height * ratio)
                    ele_x1 = self.padding + int((inner_width - element_width)/2)
                    ele_y1 = self.padding + int((inner_height - element_height)/2)
                    ele_x2 = main_width - self.padding - int((inner_width - element_width)/2)
                    ele_y2 = main_height - self.padding - int((inner_height - element_height)/2)
                else:
                    ele_x1 = self.padding
                    ele_y1 = self.padding
                    ele_x2 = main_width - self.padding
                    ele_y2 = main_height - self.padding
            else:
                if self.align == 'top_left' or self.align == 'left' or self.align == 'bottom_left':
                    ele_x1 = self.padding
                    ele_x2 = self.padding + element_width
                if self.align == 'top_right' or self.align == 'right' or self.align == 'bottom_right':
                    ele_x1 = main_width - self.padding - element_width
                    ele_x2 = main_width - self.padding
                if self.align == 'top_left' or self.align == 'top' or self.align == 'top_right':
                    ele_y1 = self.padding
                    ele_y2 = self.padding + element_height
                if self.align == 'bottom_left' or self.align == 'bottom' or self.align == 'bottom_right':
                    ele_y1 = main_height - self.padding - element_height
                    ele_y2 = main_height - self.padding
                if self.align == 'center':
                    ele_x1 = self.padding + int((inner_width-element_width)/2)
                    ele_x2 = self.padding + int((inner_width-element_width)/2) + element_width
                    ele_y1 = self.padding + int((inner_height-element_height)/2)
                    ele_y2 = self.padding + int((inner_height-element_height)/2) + element_height
            elebox = clutter.ActorBox()
            elebox.x1 = ele_x1
            elebox.y1 = ele_y1
            elebox.x2 = ele_x2
            elebox.y2 = ele_y2
            self.element.allocate(elebox, flags)
        
        clutter.Actor.do_allocate(self, box, flags)
    
    def do_foreach(self, func, data=None):
        if self.background is not None:
            func(self.background, data)
        if self.element is not None:
            func(self.element, data)
    
    def do_paint(self):
        if self.background is not None:
            self.background.paint()
        if self.element is not None:
            self.element.paint()
    
    def do_pick(self, color):
        if self.pick_enabled:
            self.do_paint()
        else:
            clutter.Actor.do_pick(self, color)
    
    def do_destroy(self):
        self.unparent()
        if hasattr(self, 'background'):
            if self.background is not None:
                self.background.unparent()
                self.background.destroy()
                self.background = None
        if hasattr(self, 'element'):
            if self.element is not None:
                self.element.unparent()
                self.element.destroy()
                self.element = None

class MultiLayerContainer(clutter.Actor, clutter.Container):
    __gtype_name__ = 'MultiLayerContainer'
    """
    A box in wich all childs have the same space allocated
    """
    def __init__(self):
        clutter.Actor.__init__(self)
        self._children = list()
    
    def do_add(self, *children):
        for child in children:
            if child in self._children:
                raise Exception("Actor %s is already a children of %s" % (child, self))
            self._children.append(child)
            child.set_parent(self)
            self.queue_relayout()
    
    def do_remove(self, *children):
        for child in children:
            if child in self._children:
                self._children.remove(child)
                child.unparent()
                self.queue_relayout()
            else:
                raise Exception("Actor %s is not a child of %s" % (child, self))
    
    def remove_all(self):
        for child in self._children:
            child.unparent()
        self._children = list()
        self.queue_relayout()
    
    def do_get_preferred_width(self, for_height):
        preferred_width = 0
        for child in self._children:
            preferred_width = max(preferred_width, child.get_preferred_width(for_height=for_height)[1])
        return preferred_width, preferred_width

    def do_get_preferred_height(self, for_width):
        preferred_height = 0
        for child in self._children:
            preferred_height = max(preferred_height, child.get_preferred_height(for_width=for_width)[1])
        return preferred_height, preferred_height
    
    def do_raise_child(self, child, sibling=None):
        if child not in self._children:
            raise Exception("Actor %s is not a child of %s" % (child, self))
        if sibling:
            if sibling not in self._children:
                raise Exception("Actor %s is not a child of %s" % (sibling, self))
            sibling_index = self._children.index(sibling)
            child_index = self._children.index(child)
            self._children[sibling_index] = child
            self._children[child_index] = sibling
        else:
            self._children.remove(child)
            self._children.append(child)
    
    def do_lower_child(self, child, sibling=None):
        if child not in self._children:
            raise Exception("Actor %s is not a child of %s" % (child, self))
        if sibling:
            if sibling not in self._children:
                raise Exception("Actor %s is not a child of %s" % (sibling, self))
            sibling_index = self._children.index(sibling)
            child_index = self._children.index(child)
            self._children[sibling_index] = child
            self._children[child_index] = sibling
        else:
            self._children.remove(child)
            self._children.insert(0, child)
    
    def do_allocate(self, box, flags):
        main_width = box.x2 - box.x1
        main_height = box.y2 - box.y1
        for child in self._children:
            child_box = clutter.ActorBox()
            child_box.x1 = 0
            child_box.y1 = 0
            child_box.x2 = main_width - 0
            child_box.y2 = main_height - 0
            child.allocate(child_box, flags)
        clutter.Actor.do_allocate(self, box, flags)
    
    def do_foreach(self, func, data=None):
        for child in self._children:
            func(child, data)
    
    def do_paint(self):
        for actor in self._children:
            actor.paint()
    
    def do_pick(self, color):
        for actor in self._children:
            actor.paint()
    
    def do_destroy(self):
        self.unparent()
        if hasattr(self, '_children'):
            for child in self._children:
                child.unparent()
                child.destroy()
            self._children = list()

if __name__ == '__main__':
    # stage
    stage = clutter.Stage()
    stage_width = 1200
    stage_height = 600
    stage.set_size(stage_width, stage_height)
    stage.set_color('#000000ff')
    stage.connect('destroy', clutter.main_quit)
    
    rect_bg = clutter.Rectangle()
    rect_bg.set_color('#ffffffff')
    rect_bg2 = clutter.Rectangle()
    rect_bg2.set_color('#ccccccff')
    
    rect1 = clutter.Rectangle()
    rect1.set_size(200, 50)
    rect1.set_color(clutter.color_from_string('Black'))
    
    rect2 = clutter.Rectangle()
    rect2.set_size(20, 10)
    rect2.set_color(clutter.color_from_string('Blue'))
    
    rect3 = clutter.Rectangle()
    rect3.set_size(20, 20)
    rect3.set_color(clutter.color_from_string('Yellow'))
    
    rect4 = clutter.Rectangle()
    rect4.set_size(40, 40)
    rect4.set_color(clutter.color_from_string('Red'))
    
    
    col = Box(horizontal=False, spacing=10, padding=0)
    col.set_background(rect_bg2)
    col.add(
        {'name': 'rect2',
        #'resizable': 1.0,
        'keep_ratio': True,
        'expand': True,
        'center': True,
        'object': rect2},
        
        {'name': 'rect3',
        #'resizable': 1.0,
        'object': rect3},
        
        {'name': 'rect4',
        'object': rect4}
    )
        
    line = Box(horizontal=True, spacing=10, padding=20)
    line.set_background(rect_bg)
    line.add_element(col, 'col', resizable=0.5, expand=True)
    line.add_element(rect1, 'rect1', resizable=0.5)
    
    #col.props.request_mode = clutter.REQUEST_WIDTH_FOR_HEIGHT
    #line.props.request_mode = clutter.REQUEST_WIDTH_FOR_HEIGHT
    line.set_height(400)
    line.set_width(500)
    #line.set_size(400, 350)
    line.set_bg_ignore_allocation_box(False)
    
    line.set_position(30, 30)
    stage.add(line)
    
    def on_click(btn_test, event):
        color_a = '#ff000088'
        color_b = '#ff0000ff'
        current_color = line.get_by_name('rect4')['object'].get_color()
        if str(current_color) == color_a:
            line.get_by_name('rect4')['object'].set_color(color_b)
        else:
            line.get_by_name('rect4')['object'].set_color(color_a)
    btn_test = AlignedElement()
    btn_rect = clutter.Rectangle()
    btn_rect.set_color('#ff00ffff')
    btn_test.set_background(btn_rect)
    btn_test.set_position(80, 480)
    btn_test.set_size(50, 50)
    btn_test.set_reactive(True)
    btn_test.connect('button-press-event', on_click)
    stage.add(btn_test)
    
    
    
    rect5 = clutter.Rectangle()
    rect5.set_size(250, 150)
    rect5.set_color('#ffffffff')
    
    rect6 = clutter.Rectangle()
    rect6.set_size(5, 5)
    rect6.set_color('#00ff0088')
    
    rect_bg_2 = clutter.Rectangle()
    rect_bg_2.set_color('#ffffffff')
    
    test_layer = MultiLayerContainer()
    test_layer.add(rect5, rect6)
    test_layer.set_position(700, 30)
    stage.add(test_layer)
    
    """
    other_box = Box(horizontal=True, spacing=10, padding=20)
    other_box.set_background(rect_bg_2)
    other_box.add(
        {'name': 'rect5',
        'expand': True,
        'object': rect5},
        {'name': 'rect6',
        #'expand': True,
        'resizable': 1.0,
        'keep_ratio': True,
        'object': rect6}
    )
    other_box.set_size(400, 300)
    other_box.set_position(700, 30)
    stage.add(other_box)
    """
    test_memory_usage = False
    if test_memory_usage:
        import gc
        gc.set_debug(gc.DEBUG_LEAK)
        from pprint import pprint
        
        max_count = 20000
        
        def create_test_object():
            t = Box(horizontal=True, spacing=10, padding=20)
            r = clutter.Rectangle()
            r.set_size(250, 150)
            r.set_color(clutter.color_from_string('Blue'))
            t.add_element(r, 'rect')
            return t
        def remove_test_object(obj, stage):
            obj.destroy()
            return False
        
        def test_memory(stage, counter, max_count):
            if counter < max_count or max_count == 0:
                counter += 1
                print counter
                tested_object = create_test_object()
                stage.add(tested_object)
                gobject.timeout_add(2, remove_tested_object, tested_object, stage, counter)
            return False
        
        def remove_tested_object(tested_object, stage, counter):
            remove_test_object(tested_object, stage)
            
            gc.collect()
            pprint(gc.garbage)
            
            gobject.timeout_add(2, test_memory, stage, counter, max_count)
            return False
        
        gobject.timeout_add(10, test_memory, stage, 0, max_count)

    
    stage.show()
    clutter.main()
    
    
