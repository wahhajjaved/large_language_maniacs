import os, os.path
import re
import locale
from types import StringType, UnicodeType

from AccessControl import ClassSecurityInfo
from BTrees.OOBTree import OOBTree

from Globals import InitializeClass, package_home
from OFS.SimpleItem import SimpleItem
from Products.CMFCore.Expression import Expression
from Products.CMFCore.CMFCorePermissions  import ManagePortal, ModifyPortalContent, View
from Products.CMFCore.ActionInformation import ActionInformation
from Products.CMFCore.ActionProviderBase import ActionProviderBase
from Products.CMFCore.utils import UniqueObject, getToolByName
from Products.PageTemplates.PageTemplateFile import PageTemplateFile
from StringIO import StringIO
from Acquisition import aq_base
from ComputedAttribute import ComputedAttribute
from Products.Archetypes.debug import log

import availablelanguages

from ZPublisher import BeforeTraverse
from ZPublisher.HTTPRequest import HTTPRequest

try:
    from Products.PlacelessTranslationService.Negotiator import registerLangPrefsMethod
    _hasPTS=1
except: _hasPTS=None


class LanguageTool(UniqueObject, ActionProviderBase, SimpleItem):
    """ CMF Syndication Client  """

    id        = 'portal_languages'
    meta_type = 'Plone Language Tool'

    security = ClassSecurityInfo()

    AVAILABLE_LANGUAGES = availablelanguages.languages
    supported_langs = availablelanguages.languages.keys()
    default_lang = 'en'

    # copy global available_langs to class variable

    _actions = [ActionInformation(
        id='languages'
        , title='Portal Languages'
        , action=Expression(text='string: ${portal_url}/portal_languages/langConfig')
        , condition=Expression(text='member')
        , permissions=(ManagePortal,)
        , category='portal_tabs'
        , visible=0
        )]

    manage_options=(
        ({ 'label'   : 'LanguageConfig',
           'action'  : 'manage_configForm',
           },
         ) + SimpleItem.manage_options
        +  ActionProviderBase.manage_options
        )

    manage_configForm = PageTemplateFile('www/config', globals())

    def __init__(self):
        self.id = 'portal_languages'

        self.use_cookie_negotiation  = 1
        self.use_request_negotiation = 1
        
        log('init')


    def __call__(self, container, req):
        '''The __before_publishing_traverse__ hook.'''
        if req.__class__ is not HTTPRequest:
            return None
        if not req[ 'REQUEST_METHOD' ] in ( 'HEAD', 'GET', 'PUT', 'POST' ):
            return None
        if req.environ.has_key( 'WEBDAV_SOURCE_PORT' ):
            return None

        # bind the languages
        self.setLanguageBindings()


    security.declareProtected(ManagePortal, 'manage_setLanguageSettings')
    def manage_setLanguageSettings(self, defaultLanguage, supportedLanguages, setCookieN=None, setRequestN=None, REQUEST=None):
        ''' stores the tool settings '''

        self.default_lang=defaultLanguage

        if supportedLanguages and type(supportedLanguages) == type([]):
            self.supported_langs=supportedLanguages
        if setCookieN:
            self.use_cookie_negotiation  = 1
        else:
            self.use_cookie_negotiation  = 0
        if setRequestN:
            self.use_request_negotiation  = 1
        else:
            self.use_request_negotiation  = 0
        if REQUEST:
            REQUEST.RESPONSE.redirect(REQUEST['HTTP_REFERER'])

    def sortedDictItems(self,dict):
        items = list(dict.items())
        items.sort(lambda x, y: cmp(x[1], y[1]))
        return items


    def listSupportedLanguages(self):
        r = []
        for i in self.supported_langs:
            r.append((i,self.AVAILABLE_LANGUAGES[i]))
        return r

    def getSupportedLanguages(self):
        return self.supported_langs

    def listAvailableLanguages(self):
        return self.sortedDictItems(self.AVAILABLE_LANGUAGES)
    
    def getAvailableLanguages(self):
        return self.available_langs.keys()

    def getDefaultLanguage(self):
        return self.default_lang

    security.declareProtected(ManagePortal, 'setDefaultLanguage')
    def setDefaultLanguage(self, langCode):
        self.default_lang = langCode
    
    security.declareProtected(ManagePortal, 'addLanguage')
    def addLanguage(self, langCode, langDescription):
        self.AVAILABLE_LANGUAGES.append((langCode, langDescription))

    def deleteLanguage(self, langCode):
        # FIXME: to implement
        self.AVAILABLE_LANGUAGES.remove(langCode)

    # some convenience functions to improve the UI:
    security.declareProtected(ManagePortal, 'addSupportedLanguage')
    def addSupportedLanguage(self, langCode):
        if (langCode in self.AVAILABLE_LANGUAGES.keys()) and not langCode in self.supported_langs:
            self.supported_langs.append(langCode)
            
    security.declareProtected(ManagePortal, 'removeSupportedLanguages')
    def removeSupportedLanguages(self, langCodes):
        for i in LangCodes:
            self.supported_langs.remove(i)

    # some methods that should be user-available
    security.declareProtected(View, 'setPreferredLanguageCookie')
    def setPreferredLanguageCookie(self,lang=None, REQUEST=None,noredir=None):
        ''' sets a cookie for overriding language negotiation '''
        portal_url = getToolByName(self, 'portal_url')()
        if lang and lang in self.supported_langs:  
            self.REQUEST.RESPONSE.setCookie('I18N_CONTENT_LANGUAGE',lang,path='/') 
        if noredir is None:                
            if REQUEST:
                REQUEST.RESPONSE.redirect(REQUEST['HTTP_REFERER'])
                
    security.declareProtected(View, 'getPreferredLanguage')
    def getPreferredLanguage(self):
        ''' get the preferred cookie language '''
        
        if not hasattr(self, 'REQUEST'): return None
        
        langCookie = self.REQUEST.cookies.get('I18N_CONTENT_LANGUAGE')
        if langCookie is not None and langCookie in self.supported_langs:
            return langCookie
        else:
            return None
       
    def manage_beforeDelete(self, item, container):
        if item is self:
            handle = self.meta_type + '/' + self.getId()
            BeforeTraverse.unregisterBeforeTraverse(container, handle)

    def manage_afterAdd(self, item, container):
        if item is self:
            handle = self.meta_type + '/' + self.getId()
            container = container.this()
            nc = BeforeTraverse.NameCaller(self.getId())
            BeforeTraverse.registerBeforeTraverse(container, nc, handle)


    security.declareProtected(View, 'getRequestLanguages')        
    def getRequestLanguages(self):
        ''' parse the request and return language list '''
        
        if not hasattr(self, 'REQUEST'): return []
        
        # get browser accept languages
        browser_pref_langs = self.REQUEST.get('HTTP_ACCEPT_LANGUAGE', '')
        browser_pref_langs = browser_pref_langs.split(',')
                                                                                
        langs = []
        i=0
        length=len(browser_pref_langs)
                                                                                
        # parse quality strings and build a tuple
        # like ((float(quality), lang), (float(quality), lang))
        # which is sorted afterwards
        # if no quality string is given then the list order
        # is used as quality indicator
        for lang in browser_pref_langs:
            lang=lang.strip().lower().replace('_','-')
            if lang:
                l = lang.split(';', 2)
                quality=[]
                                                                                
                if len(l) == 2:
                    try:
                        q=l[1]
                        if q.startswith('q='):
                            q=q.split('=', 2)[1]
                            quality=float(q)
                    except: pass
                                                                                
                if quality == []:
                    quality=float(length-i)
                                                                                
                language=l[0]
                if language in self.supported_langs:
                    # if allowed the add language
                    langs.append((quality, language))
                i=i+1
                                                                                
        # sort and reverse it
        langs.sort()
        langs.reverse()

        # filter quality string
        langs = map(lambda x: x[1], langs)
        
        return langs            
            

    security.declareProtected(View, 'setLanguageBindings')
    def setLanguageBindings(self):
        # setup the current language stuff  
        
        useCookie=self.use_cookie_negotiation
        useRequest=self.use_request_negotiation
        useDefault=1 # this should never be disabled

        if not hasattr(self, 'REQUEST'): return
        
        binding = self.REQUEST.get('LANGUAGE_TOOL', None)
        if not isinstance(binding, LanguageBinding):
            # create new binding instance
            binding=LanguageBinding(self)
            
        # bind languages
        lang = binding.setLanguageBindings(useCookie, useRequest, useDefault)
        
        # set LANGUAGE to request
        self.REQUEST['LANGUAGE']=lang
        
        # set bindings instance to request
        self.REQUEST['LANGUAGE_TOOL']=binding
        
        return lang
    
    def getLanguageBindings(self):
        # return the bound languages
        # (language, default_language, languages_list)
        
        if not hasattr(self, 'REQUEST'): return (None, None, []) # cant do anything
        
        binding = self.REQUEST.get('LANGUAGE_TOOL', None)
        if not isinstance(binding, LanguageBinding):
            # not bound -> bind
            self.setLanguageBindings()
            binding=self.REQUEST.get('LANGUAGE_TOOL')
            
        return binding.getLanguageBindings()
       
        
        

class LanguageBinding:
    """ helper which holding language infos in request """
    
    DEFAULT_LANGUAGE=None
    LANGUAGE=None
    LANGUAGE_LIST=[]
    
    def __init__(self, tool):
        self.tool=tool
        
    def setLanguageBindings(self, useCookie=1, useRequest=1, useDefault=1):
        # setup the current language stuff
        
        
        langs=[]
               
        if useCookie: langsDefault=[self.tool.getPreferredLanguage(),]
        else: langsCookie=[]
            
        if useRequest: langsRequest=self.tool.getRequestLanguages()
        else: langsRequest=[]
         
        if useDefault: langsDefault=[self.tool.getDefaultLanguage(),]
        else: langsDefault=[]
        
        # build list
        langs = langsDefault+langsRequest+langsDefault
        
        # filter None languages
        langs = filter(lambda x: x is not None, langs)
        
        self.DEFAULT_LANGGUAGE=langs[-1]
        self.LANGUAGE=langs[0]
        self.LANGUAGE_LIST=langs[1:-1]
        
        return self.LANGUAGE

    
    def getLanguageBindings(self):
        # return bound languages
        # (language, default_language, languages_list)
        
        return (self.LANGUAGE, self.DEFAULT_LANGUAGE, self.LANGUAGE_LIST)
        

class PrefsForPTS:
    """ this one should hook into pts"""
    def __init__(self, context):
        self._env = context
        self.languages = []

        binding = context.get('LANGUAGE_TOOL')
        if not isinstance(binding, LanguageBinding):
            return None

        self.pref = binding.getLanguageBindings()
        self.languages=[self.pref[0],]+self.pref[2]+[self.pref[1],]

        return None
 
    def getPreferredLanguages(self):
        """ return the list of the bound langs """
        try: return self.languages
        except: return []
    
if _hasPTS is not None:
    registerLangPrefsMethod({'klass':PrefsForPTS,'priority':15 })

    
InitializeClass(LanguageTool)
