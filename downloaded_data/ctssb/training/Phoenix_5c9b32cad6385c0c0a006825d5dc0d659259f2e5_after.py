#---------------------------------------------------------------------------
# Name:        etg/scrolwin.py
# Author:      Kevin Ollivier
#              Robin Dunn
#
# Created:     16-Sept-2011
# Copyright:   (c) 2011 by Kevin Ollivier
# License:     wxWindows License
#---------------------------------------------------------------------------

import etgtools
import etgtools.tweaker_tools as tools
import copy

PACKAGE   = "wx"
MODULE    = "_core"
NAME      = "scrolwin"   # Base name of the file to generate to for this script
DOCSTRING = ""

# The classes and/or the basename of the Doxygen XML files to be processed by
# this script. 
ITEMS  = [ 'wxScrolled' ]    
    
#---------------------------------------------------------------------------

def run():
    # Parse the XML file(s) building a collection of Extractor objects
    module = etgtools.ModuleDef(PACKAGE, MODULE, NAME, DOCSTRING)
    etgtools.parseDoxyXML(module, ITEMS)
    
    #-----------------------------------------------------------------
    # Tweak the parsed meta objects in the module object as needed for
    # customizing the generated code and docstrings.
    
    scrolled = module.find('wxScrolled')
    assert isinstance(scrolled, etgtools.ClassDef)

    scrolled.find('GetViewStart').findOverload('()').ignore()
    scrolled.find('GetViewStart.x').out = True
    scrolled.find('GetViewStart.y').out = True
    
    scrolled.find('CalcScrolledPosition.xx').out = True
    scrolled.find('CalcScrolledPosition.yy').out = True

    scrolled.find('CalcUnscrolledPosition.xx').out = True
    scrolled.find('CalcUnscrolledPosition.yy').out = True

    scrolled.find('GetScrollPixelsPerUnit.xUnit').out = True
    scrolled.find('GetScrollPixelsPerUnit.yUnit').out = True
    
    scrolled.find('GetVirtualSize.x').out = True
    scrolled.find('GetVirtualSize.y').out = True

        
    if True:
        # When SIP gets the ability to support template classes where the
        # base class is the template parameter, then we can use this instead
        # of the trickery below.
        
        # Doxygen doesn't declare the base class (the template parameter in
        # this case) so we can just add it here.
        scrolled.bases.append('T')
        
        scrolled.addPrivateCopyCtor()
        scrolled.addPrivateAssignOp()
        tools.fixWindowClass(scrolled)

        # Add back some virtuals that were removed in fixWindowClass
        scrolled.find('OnDraw').isVirtual = True
        scrolled.find('GetSizeAvailableForScrollTarget').isVirtual = True
        scrolled.find('GetSizeAvailableForScrollTarget').ignore(False)
        scrolled.find('SendAutoScrollEvents').isVirtual = True
        
        
    else:
        
        # NOTE: We do a tricky tweak here because wxScrolled requires using
        # a template parameter as the base class, which SIP doesn't handle
        # yet. So instead we'll just copy the current extractor elements for
        # wxScrolled and morph it into nodes that will generate wrappers for
        # wxScrolledWindow and wxScrolledCanvas as if they were non-template
        # classes.

        # First ignore the existing typedefs
        module.find('wxScrolledWindow').ignore()
        module.find('wxScrolledCanvas').ignore()

        swDoc = " This class derives from wxPanel so it shares its behavior with regard "\
                "to TAB traversal and focus handling.  If you do not want this then use "\
                "wxScrolledCanvas instead."
        scDoc = " This scrolled window is not intended to have children so it doesn't "\
                "have special handling for TAB traversal or focus management."
        
        # Make the copies and add them to the module
        for name, base, doc in [ ('wxScrolledCanvas', 'wxWindow', scDoc),
                                 ('wxScrolledWindow', 'wxPanel', swDoc), ]:
            node = copy.deepcopy(scrolled)
            assert isinstance(node, etgtools.ClassDef)
            node.name = name
            node.templateParams = []
            node.bases = [base]
            node.briefDoc = etgtools.flattenNode(node.briefDoc, False)
            node.briefDoc = node.briefDoc.replace('wxScrolled', name)
            node.briefDoc += doc
            for ctor in node.find('wxScrolled').all():
                ctor.name = name

            node.addPrivateCopyCtor()
            node.addPrivateAssignOp()
            tools.fixWindowClass(node)

            # Add back some virtuals that were removed in fixWindowClass
            node.find('OnDraw').isVirtual = True
            node.find('GetSizeAvailableForScrollTarget').isVirtual = True
            node.find('GetSizeAvailableForScrollTarget').ignore(False)
            node.find('SendAutoScrollEvents').isVirtual = True
            
            module.insertItemAfter(scrolled, node)
            
        # Ignore the wxScrolled template class
        scrolled.ignore()
        
    
    module.addPyCode("PyScrolledWindow = wx.deprecated(ScrolledWindow)")
    
    #-----------------------------------------------------------------
    tools.doCommonTweaks(module)
    tools.runGenerators(module)
    
    
#---------------------------------------------------------------------------
if __name__ == '__main__':
    run()

