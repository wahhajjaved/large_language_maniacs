# -*- python -*-
#
#       Visualea Manager applet
# 
#       OpenAlea.OALab: Multi-Paradigm GUI
#
#       Copyright 2013 INRIA - CIRAD - INRA
#
#       File author(s): Julien Coste <julien.coste@inria.fr>
#
#       File contributor(s):
#
#       Distributed under the Cecill-C License.
#       See accompanying file LICENSE.txt or copy at
#           http://www.cecill.info/licences/Licence_CeCILL-C_V1-en.html
#
#       OpenAlea WebSite : http://openalea.gforge.inria.fr
#
###############################################################################
__revision__ = "$Id : "

DEBUG = False

import types
import sys

from openalea.vpltk.qt import QtCore, QtGui
from openalea.visualea.graph_operator import GraphOperator
from openalea.visualea import dataflowview
from openalea.core.compositenode import CompositeNodeFactory
from openalea.plantgl.wralea.visualization import viewernode


def repr_workflow(self, name=None):
    """
    :return: workflow repr to save
    """
    name = self.applet.name if not name else name

    if name[-3:] in '.py':
        name = name[-3:]
    elif name[-4:] in '.wpy':
        name = name[-4:]
    cn = composite_node = self.applet._workflow
    cnf = CompositeNodeFactory(name)
    cn.to_factory(cnf)

    repr_wf = repr(cnf.get_writer())
    # hack to allow eval rather than exec...
    # TODO: change the writer

    repr_wf = (' = ').join(repr_wf.split(' = ')[1:])
    return repr_wf


def actions(self):
    """
    :return: list of actions to set in the menu.
    """
    return self._actions    


def save(self, name=None):
    """
    Save Current workflow
    """
    applet = self.applet
    session = applet.session
    controller = applet.controller
    project = session.project

    if name:
        self.name = name

    wf_str = self.repr_workflow(self.name)

    if project:
        project.scripts[self.name] = wf_str
        project._save("src")
    else:
        if self.name == (u"workflow.wpy"):
            new_fname = QtGui.QFileDialog.getSaveFileName(self, 'Select name to save the file %s'%self.name,self.name)
            if new_fname != u"":
                self.name = new_fname
            
        f = open(self.name, "w")
        code = str(wf_str).encode("utf8","ignore")
        f.write(code)
        f.close()


def mainMenu(self):
    """
    :return: Name of menu tab to automatically set current when current widget
    begin current.
    """
    return "Simulation"


class VisualeaApplet(object):
    default_name = "Workflow"
    default_file_name = "workflow.wpy"
    pattern = "*.wpy"
    extension = "wpy"
    icon = ":/images/resources/openalealogo.png"
    
    def __init__(self, session, controller, parent=None, name="workflow.wpy", script=None):
        super(VisualeaApplet, self).__init__() 
        repr_model = script
        self.name = name
        self.session = session
        self.controller = controller
       
        # Workflow Editor
        _name = name.split('.wpy')[0]
        if ((repr_model is None) or (repr_model=="")):
            self._workflow = CompositeNodeFactory(_name).instantiate()
        elif isinstance(repr_model, CompositeNodeFactory):
            self._workflow = repr_model.instantiate()
        else:
            cnf = eval(repr_model,globals(),locals()) 
            self._workflow = cnf.instantiate()

        self._widget = dataflowview.GraphicalGraph.create_view(self._workflow, clone=True)
        self._clipboard = CompositeNodeFactory("Clipboard")

        GraphOperator.globalInterpreter = self.session.interpreter
        self._operator = GraphOperator(graph = self._workflow,
                                 graphScene = self._widget.scene(),
                                 clipboard  = self._clipboard,
                                 )
        self._widget.mainMenu = types.MethodType(mainMenu, self._widget)
        self._widget.applet = self
        self._widget.actionSave = QtGui.QAction(QtGui.QIcon(":/images/resources/save.png"),"Save", self._widget)
        
        self._widget._actions = None
        #self._widget._actions = ["Simulation",[["Workflow Edit",self._widget.actionSave,0]]]

        methods = {}
        methods['actions'] = actions
        methods['save'] = save
        methods['repr_workflow'] = repr_workflow
        methods['get_text'] = repr_workflow
        methods['mainMenu'] = mainMenu
        
        self._widget = adapt_widget(self._widget, methods)

        #self._widget.actionSave.setShortcut(QtGui.QApplication.translate("MainWindow", "Ctrl+S", None, QtGui.QApplication.UnicodeUTF8))
        #see Also QSignalMapper
        QtCore.QObject.connect(self._widget.actionSave, QtCore.SIGNAL('triggered(bool)'),self.controller.applet_container.save)        

        if hasattr(self.controller, "_plugins"):
            if self.controller._plugins.has_key('Viewer3D'):
                viewernode.registerPlotter(self.controller._plugins['Viewer3D'].instance())
        else:
            if self.controller.applets.has_key('Viewer3D'):
                viewernode.registerPlotter(self.controller.applets['Viewer3D'])
        
        #QtCore.QObject.connect(self.widget().scene(), QtCore.SIGNAL('focusedItemChanged(type?,type?)'), self.focus_change)
        self.widget().scene().focusedItemChanged.connect(self.item_focus_change)
        
    def item_focus_change(self, scene, item):
        """
        Set doc string in Help widget when focus on node changed
        """
        assert isinstance(item, dataflowview.vertex.GraphicalVertex)
        txt = item.vertex().get_tip()
        if hasattr(self.controller, "_plugins"):
            if self.controller._plugins.has_key('HelpWidget'):
                self.controller._plugins['HelpWidget'].instance().setText(txt)
        else:
            if self.controller.applets.has_key('HelpWidget'):
                self.controller.applets['HelpWidget'].setText(txt)
    
    def focus_change(self):
        """
        Set doc string in Help widget when focus changed
        """
        txt = """
<H1><IMG SRC=%s
 ALT="icon"
 HEIGHT=25
 WIDTH=25
 TITLE="Visualea logo">Visualea</H1>

More informations: http://openalea.gforge.inria.fr/doc/openalea/visualea/doc/_build/html/contents.html        
"""%str(self.icon)

        if hasattr(self.controller, "_plugins"):
            if self.controller._plugins.has_key('HelpWidget'):
                self.controller._plugins['HelpWidget'].instance().setText(txt)
        else:
            if self.controller.applets.has_key('HelpWidget'):
                self.controller.applets['HelpWidget'].setText(txt)

    def widget(self):
        """
        :return: the edition widget
        """
        return self._widget     
        
    def run(self):
        viewernode = sys.modules['openalea.plantgl.wralea.visualization.viewernode']
        if hasattr(self.controller, "_plugins"):
            if self.controller._plugins.has_key('Viewer3D'):
                viewernode.registerPlotter(self.controller._plugins['Viewer3D'].instance())
        else:
            if self.controller.applets.has_key('Viewer3D'):
                viewernode.registerPlotter(self.controller.applets['Viewer3D'])
        self._workflow.eval()

    def animate(self):
        viewernode = sys.modules['openalea.plantgl.wralea.visualization.viewernode']
        if hasattr(self.controller, "_plugins"):
            if self.controller._plugins.has_key('Viewer3D'):
                viewernode.registerPlotter(self.controller._plugins['Viewer3D'].instance())
        else:
            if self.controller.applets.has_key('Viewer3D'):
                viewernode.registerPlotter(self.controller.applets['Viewer3D'])
        self._workflow.eval()
        
    def step(self):
        self._workflow.eval_as_expression(step=True)
        
    def stop(self):
        # print "wf stop"
        pass

    def reinit(self):
        self._workflow.reset()


def adapt_widget(widget, methods):
    method_list = ['actions', 
                   'save', 
                   'repr_workflow', 'get_text', 'mainMenu']
    def check():
        for m in method_list:
            if m not in methods:
                raise NotImplementedError(m)
    check()
    for m in method_list:
        widget.__setattr__(m, types.MethodType(methods[m], widget))
    return widget
