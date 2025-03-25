class TextBlock(object):
   def __init__(self, text=None, node=None):
      self.text = text;
      self.node = node;

class Arc(object):

   defaultIndent = '      ';

   def __init__(self, tag=None, parent=None, child=None):
       self.tag = tag;
       self.attributes = {};
       self.listOfText = [];
       self.parentNode = parent;
       self.childNode = child;

   def ShowAsHtml(self, indent=None):
      if indent:
         print indent,
      outStr = '<'+self.tag;
      for key in self.attributes.keys():
         attribute = self.attributes[key];
         for a in attribute:
            outStr = outStr + ''.join([' ', key, '=\"', a, '\"']);

      print (outStr + '>');

      if self.listOfText:
         for block in self.listOfText:
            if block.node:
               block.node.ShowAsHtml(indent);
            if indent:
               print indent,
            print block.text;
      else:
         if self.childNode:
            if len(self.childNode.arcs) > 0:
               nextIndent = indent;
               if not indent:
                  nextIndent = '';
               self.childNode.ShowAsHtml(nextIndent + Arc.defaultIndent);

      if indent:
         print indent,
      print ''.join(['</', self.tag, '>']);

   def Show(self, indent=None):
      #print tag
      if indent:
         print(indent),;
      print 'Tag: ', self.tag;
      for block in self.listOfText:
         if indent:
            print(indent),;
         print 'Text: ', block.text;
      #print all attributes in this arc
      for key in self.attributes.keys():
         attribute = self.attributes[key];
         for a in attribute:
            if indent:
               print(indent),;
            print key, ": ", a;

      #indent, then show data from the node this arc points to
      if self.childNode:
         if len(self.childNode.arcs) > 0:
            if indent:
               indent = Arc.defaultIndent;
            else:
               indent = indent +  Arc.defaultIndent;
            self.childNode.Show(indent);
      else:
         print '';

   def SetChildNode(self, node):
      self.childNode = node;

