VALID     = 'valid'
REQUIRED  = 'required'
CHILDREN  = 'children'
DEFAULT   = 'default'

from pyy_html.html import html_tag

class dtd(object):
  valid = {}

  def __init__(self):

    # convert lists to sets so "in" operator is faster
    for tag, dict in self.valid.iteritems():
      dict.setdefault(VALID,    [])
      dict.setdefault(REQUIRED, [])
      dict.setdefault(CHILDREN, [])
      dict.setdefault(DEFAULT,  {})
      
      for k in [VALID, REQUIRED, CHILDREN]:
        dict[k] = set(dict[k])

  def validate(self, tag, child=None):
    cls = type(tag)
    valid = self.valid[cls]
    
    #Check children
    children = child and [child] or tag.children
    if tag.is_single and children:
      raise ValueError('%s element cannot contain any child elements. Currently has: %s.' \
        % (cls.__name__, ', '.join(type(c).__name__ for c in children)))

    for child in children:
      if type(child) not in valid[CHILDREN]:
        raise ValueError('%s element cannot contain %s element as child.' % \
            (cls.__name__, type(child).__name__))
      
      if isinstance(child, html_tag): self.validate(child)

    #Add default attributes
    for attribute, value in valid[DEFAULT].iteritems():
      tag.attributes.setdefault(attribute, value)

    if tag.allow_invalid: # should this apply recursively to children?
      return True

    #Check for invalid attributes
    invalid_attributes = []
    for attribute, value in tag.attributes.iteritems():
      if attribute not in valid[VALID]: invalid_attributes.append(attribute)
    if invalid_attributes:
      raise AttributeError('%s element has one or more invalid attributes: %s.' \
        % (cls.__name__, ', '.join(invalid_attributes)))

    #Check for missing required attributes
    missing_attributes = [attribute for attribute in valid[REQUIRED] if attribute not in tag.attributes]
    if missing_attributes:
      raise AttributeError('%s element has one or more missing attributes that are required: %s.' \
        % (cls.__name__, ', '.join(missing_attributes)))

    return True
  
  def render(self):
    return self.docstring

import xhtml11 as _xhtml11

xhtml11 = _xhtml11.xhtml11()
