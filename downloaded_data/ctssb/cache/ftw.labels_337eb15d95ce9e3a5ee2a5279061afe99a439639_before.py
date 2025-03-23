from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from ftw.labels.interfaces import ILabelSupport
from ftw.labels.interfaces import ILabeling
from plone.app.portlets.portlets.base import Renderer


class Renderer(Renderer):
    render = ViewPageTemplateFile('labeling.pt')

    @property
    def available(self):
        return ILabelSupport.providedBy(self.context) and \
            [label for label in self.available_labels]

    @property
    def active_labels(self):
        return ILabeling(self.context).active_labels()

    @property
    def available_labels(self):
        return ILabeling(self.context).available_labels()
