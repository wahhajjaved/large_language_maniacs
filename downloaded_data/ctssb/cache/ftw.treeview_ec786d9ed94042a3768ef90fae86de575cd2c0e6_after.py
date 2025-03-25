from Products.Five.browser import BrowserView
from Products.CMFCore.utils import getToolByName
from plone.app.layout.navigation.navtree import buildFolderTree
from Products.CMFPlone.browser.navtree import NavtreeQueryBuilder
from Products.CMFPlone.browser.navigation import CatalogNavigationTree
from plone.app.layout.navigation.interfaces import INavtreeStrategy
from Products.CMFCore.utils import getToolByName
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.component import getMultiAdapter, queryUtility
from Acquisition import aq_inner



class TreeView(CatalogNavigationTree):

    recurse = ViewPageTemplateFile('recurse.pt')
    
    def render(self):
        """return a html tree for treeview"""
        

        context = aq_inner(self.context)

        queryBuilder = NavtreeQueryBuilder(context)

        #XXX use querybuilder... 
        #query = queryBuilder()
        query = {'path': '/'.join(self.context.getPhysicalPath()), 'depth':1, 'Type': 'RepositoryFolder'}
        strategy = getMultiAdapter((context, self), INavtreeStrategy)
        data = buildFolderTree(context, obj=context, query=query, strategy=strategy)
        html=self.recurse(children=data.get('children', []),level=1, bottomLevel=999)
        return html
        # queryBuilder = NavtreeQueryBuilder
        # strategy = getMultiAdapter((aq_inner(self.context), self),
        #                            INavtreeStrategy)
        # 
        # query=queryBuilder()
        # 
        # data=buildFolderTree(root, query=query, strategy=strategy)
        # html=self.recurse(children=data.get('children', []), level=1, bottomLevel=0)
        # 
        # return html.encode('utf8')
