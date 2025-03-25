"""SAML 2.0 core module

Implementation of SAML 2.0 for NDG Security

NERC DataGrid Project

This implementation is adapted from the Java OpenSAML implementation.  The 
copyright and licence information are included here:

Copyright [2005] [University Corporation for Advanced Internet Development, Inc.]

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
__author__ = "P J Kershaw"
__date__ = "11/08/09"
__copyright__ = "(C) 2009 Science and Technology Facilities Council"
__contact__ = "Philip.Kershaw@stfc.ac.uk"
__license__ = "http://www.apache.org/licenses/LICENSE-2.0"
__contact__ = "Philip.Kershaw@stfc.ac.uk"
__revision__ = "$Id$"
from datetime import datetime
from urlparse import urlsplit, urlunsplit
import urllib

from ndg.saml.common import SAMLObject, SAMLVersion
from ndg.saml.common.xml import SAMLConstants, QName
from ndg.saml.utils import TypedList


class Attribute(SAMLObject):
    '''SAML 2.0 Core Attribute
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME:  Local name of the Attribute element.
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME:  Default element name.
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    @cvar TYPE_LOCAL_NAME:  Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME:  QName of the XSI type.
    @type TYPE_NAME: ndg.saml.common.xml.QName
    @cvar NAME_ATTRIB_NAME:  Name of the Name attribute.
    @type NAME_ATTRIB_NAME: string
    @cvar NAME_FORMAT_ATTRIB_NAME:  Name for the NameFormat attribute.
    @type NAME_FORMAT_ATTRIB_NAME: string
    @cvar FRIENDLY_NAME_ATTRIB_NAME:  Name of the FriendlyName attribute.
    @type FRIENDLY_NAME_ATTRIB_NAME: string
    @cvar UNSPECIFIED:  Unspecified attribute format ID.
    @type UNSPECIFIED: string
    @cvar URI_REFERENCE:  URI reference attribute format ID.
    @type URI_REFERENCE: string
    @cvar BASIC:  Basic attribute format ID.
    @type BASIC: string
    
    @ivar __name: attribute name
    @type __name: NoneType / basestring
    @ivar __nameFormat: name format
    @type __nameFormat: NoneType / basestring
    @ivar __friendlyName: friendly name for attribute
    @type __friendlyName: NoneType / basestring
    @ivar __attributeValues: list of values
    @type __attributeValues: list / tuple
    '''
    
    # Local name of the Attribute element. 
    DEFAULT_ELEMENT_LOCAL_NAME = "Attribute"

    # Default element name. 
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20_PREFIX)

    # Local name of the XSI type. 
    TYPE_LOCAL_NAME = "AttributeType"

    # QName of the XSI type. 
    TYPE_NAME = QName(SAMLConstants.SAML20_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20_PREFIX)

    # Name of the Name attribute. 
    NAME_ATTRIB_NAME = "Name"

    # Name for the NameFormat attribute. 
    NAME_FORMAT_ATTRIB_NAME = "NameFormat"

    # Name of the FriendlyName attribute. 
    FRIENDLY_NAME_ATTRIB_NAME = "FriendlyName"

    # Unspecified attribute format ID. 
    UNSPECIFIED = "urn:oasis:names:tc:SAML:2.0:attrname-format:unspecified"

    # URI reference attribute format ID. 
    URI_REFERENCE = "urn:oasis:names:tc:SAML:2.0:attrname-format:uri"

    # Basic attribute format ID. 
    BASIC = "urn:oasis:names:tc:SAML:2.0:attrname-format:basic"

    __slots__ = (
        '__name',
        '__nameFormat',
        '__friendlyName',
        '__attributeValues'
    )
    
    def __init__(self, **kw):
        """Initialise Attribute Class attributes
        @param kw: keywords SAMLObject parent instantiation
        @type kw: dict
        """
        super(Attribute, self).__init__(**kw)
        
        self.__name = None
        self.__nameFormat = None
        self.__friendlyName = None
        self.__attributeValues = []

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''
        _dict = super(Attribute, self).__getstate__()
        for attrName in Attribute.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_Attribute" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
    
    def _get_name(self):
        """Get name
        @return: name
        @rtype: string
        """
        return self.__name
    
    def _set_name(self, name):
        """Set name
        @param name: name
        @type name: basestring
        @raise TypeError: invalid input value type
        """
        if not isinstance(name, basestring):
            raise TypeError("Expecting basestring type for name, got %r"% 
                            type(name))
        
        self.__name = name
        
    name = property(fget=_get_name,
                    fset=_set_name,
                    doc="name of this attribute")
    
    def _get_nameFormat(self):
        """Get name format
        @return: name format
        @rtype: string
        """
        return self.__nameFormat
    
    def _set_nameFormat(self, nameFormat):
        """Set name format
        @param nameFormat: name format
        @type nameFormat: string
        @raise TypeError: invalid input value type
        """
        if not isinstance(nameFormat, basestring):
            raise TypeError("Expecting basestring type for nameFormat, got %r"
                            % type(nameFormat))
            
        self.__nameFormat = nameFormat
        
    nameFormat = property(fget=_get_nameFormat,
                          fset=_set_nameFormat,
                          doc="Get the name format of this attribute.")
    
    def _get_friendlyName(self):
        """Get friendly name
        @return: friendly name
        @rtype: string
        """
        return self.__friendlyName
    
    def _set_friendlyName(self, friendlyName):
        """Set friendly name
        @param friendlyName: friendly name
        @type friendlyName: string
        @raise TypeError: invalid input value type
        """
        if not isinstance(friendlyName, basestring):
            raise TypeError("Expecting basestring type for friendlyName, got "
                            "%r" % type(friendlyName))
            
        self.__friendlyName = friendlyName
        
    friendlyName = property(fget=_get_friendlyName,
                            fset=_set_friendlyName,
                            doc="the friendly name of this attribute.")
    
    def _get_attributeValues(self):
        """Get attribute values
        @return: attribute values
        @rtype: string
        """
        return self.__attributeValues
    
    def _set_attributeValues(self, attributeValues):
        """Set attribute values
        @param attributeValues: attribute values
        @type attributeValues: list/tuple
        @raise TypeError: invalid input value type
        """
        if not isinstance(attributeValues, (list, tuple)):
            raise TypeError("Expecting list/tuple type for attributeValues, "
                            "got %r" % type(attributeValues))
            
        self.__attributeValues = attributeValues
        
    attributeValues = property(fget=_get_attributeValues,
                               fset=_set_attributeValues,
                               doc="the list of attribute values for this "
                               "attribute.")


class Statement(SAMLObject):
    '''SAML 2.0 Core Statement.  Abstract base class which all statement 
    types must implement.
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type
    @type TYPE_NAME: ndg.saml.common.xml.QName
    '''
    __slots__ = ()
    
    # Element local name
    DEFAULT_ELEMENT_LOCAL_NAME = "Statement"

    # Default element name
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20_PREFIX)

    # Local name of the XSI type
    TYPE_LOCAL_NAME = "StatementAbstractType"

    # QName of the XSI type
    TYPE_NAME = QName(SAMLConstants.SAML20_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20_PREFIX)
    
            
class AttributeStatement(Statement):
    '''SAML 2.0 Core AttributeStatement
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name.
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type.
    @type TYPE_NAME: ndg.saml.common.xml.QName
    
    @ivar __attributes: list of ndg.saml.saml2.core.Attribute type attributes
    @type __attributes: ndg.saml.utils.TypedList
    @ivar __encryptedAttributes: list of encrypted attributes of type 
    ndg.saml.saml2.core.Attribute 
    @type __encryptedAttributes: ndg.saml.utils.TypedList
    '''
    
    # Element local name
    DEFAULT_ELEMENT_LOCAL_NAME = "AttributeStatement"
    
    # Default element name.
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME, 
                                 SAMLConstants.SAML20_PREFIX)
    
    # Local name of the XSI type. 
    TYPE_LOCAL_NAME = "AttributeStatementType" 
        
    # QName of the XSI type.
    TYPE_NAME = QName(SAMLConstants.SAML20_NS, 
                      TYPE_LOCAL_NAME, 
                      SAMLConstants.SAML20_PREFIX)
    
    __slots__ = ('__attributes', '__encryptedAttributes')
    
    def __init__(self, **kw):
        """
        @param kw: keywords Statement parent class instantiation
        @type kw: dict
        """
        super(AttributeStatement, self).__init__(**kw)
        
        self.__attributes = TypedList(Attribute)
        self.__encryptedAttributes = TypedList(Attribute)

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''

        _dict = super(AttributeStatement, self).__getstate__()
        for attrName in AttributeStatement.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_AttributeStatement" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict

    def _get_attributes(self):
        '''@return: the attributes expressed in this statement
        @rtype: ndg.saml.utils.TypedList
        '''
        return self.__attributes

    attributes = property(fget=_get_attributes)
    
    def _get_encryptedAttributes(self):
       '''@return: the encrypted attribtues expressed in this statement
       @rtype: ndg.saml.utils.TypedList
       '''
       return self.__encryptedAttributes
   
    encryptedAttributes = property(fget=_get_encryptedAttributes)


class AuthnStatement(Statement):
    '''SAML 2.0 Core AuthnStatement.  Currently implemented in abstract form
    only
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type
    @type TYPE_NAME: ndg.saml.common.xml.QName
    @cvar AUTHN_INSTANT_ATTRIB_NAME: AuthnInstant attribute name
    @type AUTHN_INSTANT_ATTRIB_NAME: string
    @cvar SESSION_INDEX_ATTRIB_NAME: SessionIndex attribute name
    @type SESSION_INDEX_ATTRIB_NAME: string
    @cvar SESSION_NOT_ON_OR_AFTER_ATTRIB_NAME: SessionNoOnOrAfter attribute name
    @type SESSION_NOT_ON_OR_AFTER_ATTRIB_NAME: string
    '''

    # Element local name
    DEFAULT_ELEMENT_LOCAL_NAME = "AuthnStatement"

    # Default element name
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20_PREFIX)

    # Local name of the XSI type
    TYPE_LOCAL_NAME = "AuthnStatementType"

    # QName of the XSI type
    TYPE_NAME = QName(SAMLConstants.SAML20_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20_PREFIX)

    # AuthnInstant attribute name
    AUTHN_INSTANT_ATTRIB_NAME = "AuthnInstant"

    # SessionIndex attribute name
    SESSION_INDEX_ATTRIB_NAME = "SessionIndex"

    # SessionNoOnOrAfter attribute name
    SESSION_NOT_ON_OR_AFTER_ATTRIB_NAME = "SessionNotOnOrAfter"
    
    __slots__ = ()
    
    def _getAuthnInstant(self):
        '''Abstract method.  Gets the time when the authentication took place.
        
        @return: the time when the authentication took place
        @rtype: datetime.datetime
        @raise NotImplementedError: abstract method
        '''
        raise NotImplementedError()

    def _setAuthnInstant(self, value):
        '''Sets the time when the authentication took place.
        
        @param value: the time when the authentication took place
        @type value: datetime.datetime
        @raise NotImplementedError: abstract method
        '''
        raise NotImplementedError()

    def _getSessionIndex(self):
        '''Get the session index between the principal and the authenticating 
        authority.
        
        @return: the session index between the principal and the authenticating 
        authority
        @rtype: ?
        @raise NotImplementedError: abstract method
        '''
        raise NotImplementedError()

    def _setSessionIndex(self, value):
        '''Sets the session index between the principal and the authenticating 
        authority.
        
        @param value: the session index between the principal and the 
        authenticating authority
        @type value: ?
        @raise NotImplementedError: abstract method
        '''
        raise NotImplementedError()

    def _getSessionNotOnOrAfter(self):
        '''Get the time when the session between the principal and the SAML 
        authority ends.
        
        @return: the time when the session between the principal and the SAML 
        authority ends
        @rtype: datetime.datetime
        @raise NotImplementedError: abstract method
        '''
        raise NotImplementedError()

    def _setSessionNotOnOrAfter(self, value):
        '''Set the time when the session between the principal and the SAML 
        authority ends.
        
        @param value: the time when the session between the 
        principal and the SAML authority ends
        @type value: datetime.datetime
        @raise NotImplementedError: abstract method
        '''
        raise NotImplementedError()

    def _getSubjectLocality(self):
        '''Get the DNS domain and IP address of the system where the principal 
        was authenticated.
        
        @return: the DNS domain and IP address of the system where the principal
        was authenticated
        @rtype: ?
        @raise NotImplementedError: abstract method
        '''
        raise NotImplementedError()

    def _setSubjectLocality(self, value):
        '''Set the DNS domain and IP address of the system where the principal 
        was authenticated.
        
        @param value: the DNS domain and IP address of the system where 
        the principal was authenticated
        @type value: ?
        @raise NotImplementedError: abstract method
        '''
        raise NotImplementedError()

    def _getAuthnContext(self):
        '''Gets the context used to authenticate the subject.
        
        @return: the context used to authenticate the subject
        @rtype: ?
        @raise NotImplementedError: abstract method
        '''
        raise NotImplementedError()

    def _setAuthnContext(self, value):
        '''Sets the context used to authenticate the subject.
        
        @param value: the context used to authenticate the subject
        @type value: ?
        @raise NotImplementedError: abstract method
        '''
        raise NotImplementedError()


class DecisionType(object):
    """Define decision types for the authorisation decisions
        
    @cvar PERMIT_STR: "Permit" decision type
    @type PERMIT_STR: string
    @cvar DENY_STR: "Deny" decision type
    @type DENY_STR: string
    @cvar INDETERMINATE_STR: "Indeterminate" decision type
    @type INDETERMINATE_STR: string
    @cvar TYPES: Permissable type strings
    @type TYPES: string

    @cvar PERMIT: permit as a decision type subclass
    @type PERMIT: ndg.saml.saml2.core.PermitDecisionType
    @cvar DENY: deny as a decision type subclass
    @type DENY: ndg.saml.saml2.core.DenyDecisionType
    @cvar INDETERMINATE: indeterminate as a decision type subclass
    @type INDETERMINATE: ndg.saml.saml2.core.IndeterminateDecisionType
    
    @ivar __value: decision value
    @type __value: string
    """
    
    # "Permit" decision type
    PERMIT_STR = "Permit"
    
    # "Deny" decision type
    DENY_STR = "Deny"
    
    # "Indeterminate" decision type
    INDETERMINATE_STR = "Indeterminate"
    
    # Permissable type strings
    TYPES = (PERMIT_STR, DENY_STR, INDETERMINATE_STR)
    
    __slots__ = ('__value',)
    
    def __init__(self, decisionType):
        '''@param decisionType: decision value
        @type decisionType: string/ndg.saml.saml2.core.DecisionType
        '''
        self.__value = None
        self.value = decisionType

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''

        _dict = {}
        for attrName in DecisionType.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_DecisionType" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
  
    def __setstate__(self, attrDict):
        '''Enable pickling
        
        @param attrDict: object's attribute dictionary
        @type attrDict: dict
        '''
        for attrName, val in attrDict.items():
            setattr(self, attrName, val)
            
    def _setValue(self, value):
        '''Set decision type
        @param value: decision value
        @type value: string/ndg.saml.saml2.core.DecisionType
        '''
        if isinstance(value, DecisionType):
            # Cast to string
            value = str(value)
            
        elif not isinstance(value, basestring):
            raise TypeError('Expecting string or DecisionType instance for '
                            '"value" attribute; got %r instead' % type(value))
            
        if value not in self.__class__.TYPES:
            raise AttributeError('Permissable decision types are %r; got '
                                 '%r instead' % (DecisionType.TYPES, value))
        self.__value = value
        
    def _getValue(self):
        '''Get decision type
        @return: decision value
        @rtype: string/ndg.saml.saml2.core.DecisionType
        '''
        return self.__value
    
    value = property(fget=_getValue, fset=_setValue, doc="Decision value")
    
    def __str__(self):
        '''Representation of decision type as a string
        @return: decision value
        @rtype: string
        '''
        return self.__value

    def __eq__(self, decision):
        """Test for equality against an input decision type
        
        @param decision: decision type
        @type decision: ndg.saml.saml2.core.DecisionType or basestring
        @return: True if input and this object match
        @rtype: bool
        @raise TypeError: unexpected type for decision type input
        """
        if isinstance(decision, DecisionType):
            # Cast to string
            value = decision.value
            
        elif isinstance(decision, basestring):
            value = decision
            
        else:
            raise TypeError('Expecting string or DecisionType instance for '
                            'input decision value; got %r instead' % 
                            type(value))
            
        if value not in self.__class__.TYPES:
            raise AttributeError('Permissable decision types are %r; got '
                                 '%r instead' % (DecisionType.TYPES, value))
            
        return self.__value == value


class PermitDecisionType(DecisionType):
    """Permit authorisation Decision"""
    __slots__ = ()

    def __init__(self):
        """Initialise with permit decision setting"""
        super(PermitDecisionType, self).__init__(DecisionType.PERMIT_STR)
        
    def _setValue(self):
        """
        @raise AttributeError: instances have read only decision type
        """ 
        raise AttributeError("can't set attribute")


class DenyDecisionType(DecisionType):
    """Deny authorisation Decision"""
    __slots__ = ()
    
    def __init__(self):
        """Initialise with deny decision setting"""
        super(DenyDecisionType, self).__init__(DecisionType.DENY_STR)
        
    def _setValue(self, value):  
        """
        @raise AttributeError: instances have read only decision type
        """ 
        raise AttributeError("can't set attribute")


class IndeterminateDecisionType(DecisionType):
    """Indeterminate authorisation Decision"""
    __slots__ = ()
    
    def __init__(self):
        """Initialise with indeterminate decision setting"""
        super(IndeterminateDecisionType, self).__init__(
                                            DecisionType.INDETERMINATE_STR)
        
    def _setValue(self, value):  
        """
        @raise AttributeError: instances have read only decision type
        """ 
        raise AttributeError("can't set attribute")

# Add instances of each for convenience
DecisionType.PERMIT = PermitDecisionType()
DecisionType.DENY = DenyDecisionType()
DecisionType.INDETERMINATE = IndeterminateDecisionType()


class AuthzDecisionStatement(Statement):
    '''SAML 2.0 Core AuthzDecisionStatement.  Currently implemented in abstract
    form only

    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type
    @type TYPE_NAME: ndg.saml.common.xml.QName
    @cvar RESOURCE_ATTRIB_NAME: Resource attribute name
    @type RESOURCE_ATTRIB_NAME: string
    @cvar DECISION_ATTRIB_NAME: Decision attribute name
    @type DECISION_ATTRIB_NAME: string
    
    @ivar __resource: identifier for the resource which is the subject of the 
    authorisation statement
    @type __resource: basestring
    @ivar __decision: decision type for this authorisation statement
    @type __decision: ndg.saml.saml2.core.DecisionType
    @ivar __actions: list of ndg.saml.saml2.core.Action elements
    @type __actions: ndg.saml.utils.TypedList
    @ivar __evidence: evidence (not currently implemented)
    @type __evidence: None
    @ivar __normalizeResource: set to True to normalize the URI object attribute
    in the set property method (functionality likely to be deprecated)
    @type __normalizeResource: bool
    @ivar __safeNormalizationChars: acceptable characters for normalizing URIs
    (functionality likely to be deprecated)
    @type __safeNormalizationChars: string
    '''
    
    # Element local name
    DEFAULT_ELEMENT_LOCAL_NAME = "AuthzDecisionStatement"

    # Default element name
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20_PREFIX)

    # Local name of the XSI type
    TYPE_LOCAL_NAME = "AuthzDecisionStatementType"

    # QName of the XSI type
    TYPE_NAME = QName(SAMLConstants.SAML20_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20_PREFIX)

    # Resource attribute name
    RESOURCE_ATTRIB_NAME = "Resource"

    # Decision attribute name
    DECISION_ATTRIB_NAME = "Decision"
    
    __slots__ = (
        '__resource', 
        '__decision', 
        '__actions', 
        '__evidence',
        '__normalizeResource',
        '__safeNormalizationChars'
    )
    
    def __init__(self, 
                 normalizeResource=True, 
                 safeNormalizationChars='/%',
                 **kw):
        '''Create new authorisation decision statement
        @param normalizeResource: set to True to normalize the URI object 
        attribute in the set property method (functionality likely to be 
        deprecated)
        @type normalizeResource: bool
        @param safeNormalizationChars: acceptable characters for normalizing 
        URIs (functionality likely to be deprecated)
        @type safeNormalizationChars: string
        @param kw: keywords for the initialisation of the parent classes'
        attributes
        @type kw: dict
        '''
        super(AuthzDecisionStatement, self).__init__(**kw)

        # Resource attribute value. 
        self.__resource = None  
        
        self.__decision = DecisionType.INDETERMINATE   
        self.__actions = TypedList(Action)
        self.__evidence = None
        
        # Tuning for normalization of resource URIs in property set method
        self.normalizeResource = normalizeResource
        self.safeNormalizationChars = safeNormalizationChars

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''

        _dict = super(AuthzDecisionStatement, self).__getstate__()
        for attrName in AuthzDecisionStatement.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_AuthzDecisionStatement" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
    
    def _getNormalizeResource(self):
        '''Get normalise resource flag
        @return: flag value
        @rtype: bool        
        '''
        return self.__normalizeResource

    def _setNormalizeResource(self, value):
        '''Set normalise resource flag
        @param value: flag value
        @type value: bool
        @raise TypeError: input value is incorrect type
        '''
        if not isinstance(value, bool):
            raise TypeError('Expecting bool type for "normalizeResource" '
                            'attribute; got %r instead' % type(value))
            
        self.__normalizeResource = value

    normalizeResource = property(_getNormalizeResource, 
                                 _setNormalizeResource, 
                                 doc="Flag to normalize new resource value "
                                     "assigned to the \"resource\" property.  "
                                     "The setting only applies for URIs "
                                     'beginning with "http://" or "https://"')

    def _getSafeNormalizationChars(self):
        '''Get normalisation safe chars
        @return: normalisation safe chars
        @rtype: basetring
        '''
        return self.__safeNormalizationChars

    def _setSafeNormalizationChars(self, value):
        '''Set normalisation safe chars
        @param value: normalisation safe chars
        @type value: basetring
        @raise TypeError: input value is incorrect type
        '''
        if not isinstance(value, basestring):
            raise TypeError('Expecting string type for "normalizeResource" '
                            'attribute; got %r instead' % type(value))
            
        self.__safeNormalizationChars = value

    safeNormalizationChars = property(_getSafeNormalizationChars, 
                                      _setSafeNormalizationChars, 
                                      doc="String containing a list of "
                                          "characters that should not be "
                                          "converted when Normalizing the "
                                          "resource URI.  These are passed to "
                                          "urllib.quote when the resource "
                                          "property is set.  The default "
                                          "characters are '/%'")

    def _getResource(self):
        '''Gets the Resource attrib value of this statement.

        @return: the Resource attrib value of this statement
        @rtype: basestring
        '''
        return self.__resource
    
    def _setResource(self, value):
        '''Sets the Resource attrib value of this statement normalizing the path
        component, removing spurious port numbers (80 for HTTP and 443 for 
        HTTPS) and converting the host component to lower case.
        
        @param value: the new Resource attrib value of this statement
        @type value: basestring
        @raise TypeError: input value is incorrect type
        '''
        if not isinstance(value, basestring):
            raise TypeError('Expecting string type for "resource" attribute; '
                            'got %r instead' % type(value))
        
        if (self.normalizeResource and 
            value.startswith('http://') or value.startswith('https://')):
            # Normalise the path, set the host name to lower case and remove 
            # port redundant numbers 80 and 443
            splitResult = urlsplit(value)
            uriComponents = list(splitResult)
            
            # hostname attribute is lowercase
            uriComponents[1] = splitResult.hostname
            
            if splitResult.port is not None:
                isHttpWithStdPort = (splitResult.port == 80 and 
                                     splitResult.scheme == 'http')
                
                isHttpsWithStdPort = (splitResult.port == 443 and
                                      splitResult.scheme == 'https')
                
                if not isHttpWithStdPort and not isHttpsWithStdPort:
                    uriComponents[1] += ":%d" % splitResult.port
            
            uriComponents[2] = urllib.quote(splitResult.path, 
                                            self.safeNormalizationChars)
            
            self.__resource = urlunsplit(uriComponents)
        else:
            self.__resource = value
    
    resource = property(fget=_getResource, fset=_setResource,
                        doc="Resource for which authorisation was requested")

    def _getDecision(self):
        '''
        Gets the decision of the authorization request.
        
        @return: the decision of the authorization request
        '''
        return self.__decision

    def _setDecision(self, value):
        '''
        Sets the decision of the authorization request.
        
        @param value: the decision of the authorization request
        @raise TypeError: input value is incorrect type
        '''
        if not isinstance(value, DecisionType):
            raise TypeError('Expecting %r type for "decision" attribute; '
                            'got %r instead' % (DecisionType, type(value)))
        self.__decision = value

    decision = property(_getDecision, _setDecision, 
                        doc="Authorization decision as a DecisionType instance")
    
    @property
    def actions(self):
        '''The actions for which authorisation is requested
        
        @return: the Actions of this statement
        @rtype: TypedList
        '''
        return self.__actions
   
    def _getEvidence(self):
        '''Gets the Evidence of this statement.  Evidence attribute 
        functionality is not currently implemented in this class

        @return: the Evidence of this statement
        @rtype: None'''
        return self.__evidence

    def _setEvidence(self, value):
        '''Sets the Evidence of this statement.  Evidence attribute 
        functionality is not currently implemented in this class
        
        @param value: the new Evidence of this statement 
        @type value: None 
        @raise TypeError: input value is incorrect type
        '''
        if not isinstance(value, Evidence):
            raise TypeError('Expecting Evidence type for "evidence" '
                            'attribute; got %r' % type(value))

        self.__evidence = value  

    evidence = property(fget=_getEvidence, fset=_setEvidence, 
                        doc="A set of assertions which the Authority may use "
                            "to base its authorisation decision on")
    
    def getOrderedChildren(self):
        """Get ordered children
        @return: list actions and evidence for this statement
        @rtype: tuple
        """
        children = []

        superChildren = super(AuthzDecisionStatement, self).getOrderedChildren()
        if superChildren:
            children.extend(superChildren)

        children.extend(self.__actions)
        
        if self.__evidence is not None:
            children.extend(self.__evidence)

        if len(children) == 0:
            return None

        return tuple(children)
        

class Subject(SAMLObject):
    '''Implementation of SAML 2.0 Subject
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name.
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name.
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type.
    @type TYPE_NAME: ndg.saml.common.xml.QName
    
    @ivar __baseID: base identifier
    @type __baseID: basestring
    @ivar __nameID: name identifier
    @type __nameID: basestring
    @ivar __encryptedID: encrypted identifier
    @type __encryptedID: any - not implemented for type checking
    @ivar __subjectConfirmations: list of subject confirmations
    @type __subjectConfirmations: list
    '''
    
    # Element local name.
    DEFAULT_ELEMENT_LOCAL_NAME = "Subject"

    # Default element name.
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20_PREFIX)

    # Local name of the XSI type.
    TYPE_LOCAL_NAME = "SubjectType"

    # QName of the XSI type.
    TYPE_NAME = QName(SAMLConstants.SAML20_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20_PREFIX)
    
    __slots__ = (
        '__baseID',
        '__nameID',
        '__encryptedID',
        '__subjectConfirmations'
    )
    
    def __init__(self, **kw):
        '''
        @param kw: keywords for initialisation of parent class attributes
        @type kw: dict
        '''
        super(Subject, self).__init__(**kw)
        
        # BaseID child element.
        self.__baseID = None
    
        # NameID child element.
        self.__nameID = None
    
        # EncryptedID child element.
        self.__encryptedID = None
    
        # Subject Confirmations of the Subject.
        self.__subjectConfirmations = []

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''
        _dict = super(Subject, self).__getstate__()
        for attrName in Subject.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_Subject" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
    
    def _getBaseID(self): 
        """Get base identifier
        @return: base identifier
        @rtype: basestring
        """ 
        return self.__baseID

    def _setBaseID(self, value):
        """Set base identifier
        @param value: base identifier
        @type value: basestring
        @raise TypeError: invalid input value type
        """ 
        if not isinstance(value, basestring):
            raise TypeError("Expecting %r type for \"baseID\" got %r" %
                            (basestring, value.__class__))
        self.__baseID = value

    baseID = property(fget=_getBaseID, 
                      fset=_setBaseID, 
                      doc="Base identifier")
      
    def _getNameID(self):
        """Get name identifier
        @return: name identifier
        @rtype: basestring
        """ 
        return self.__nameID
    
    def _setNameID(self, value):
        """Set name identifier
        @param value: name identifier
        @type value: basestring
        @raise TypeError: invalid input value type
        """ 
        if not isinstance(value, NameID):
            raise TypeError("Expecting %r type for \"nameID\" got %r" %
                            (NameID, type(value)))
        self.__nameID = value

    nameID = property(fget=_getNameID, 
                      fset=_setNameID, 
                      doc="Name identifier")
    
    def _getEncryptedID(self):
        """Get encrypted identifier
        @return: encrypted identifier
        @rtype: basestring
        """ 
        return self.__encryptedID
    
    def _setEncryptedID(self, value): 
        """Set encrypted identifier
        
        @param value: encrypted identifier
        @type value: any type
        @raise TypeError: invalid input value type
        """ 
        self.__encryptedID = value

    encryptedID = property(fget=_getEncryptedID, 
                           fset=_setEncryptedID, 
                           doc="EncryptedID's Docstring")
    
    def _getSubjectConfirmations(self): 
        """Get list of subject confirmations
        @return: list of subject confirmations
        @rtype: list
        """ 
        return self.__subjectConfirmations

    subjectConfirmations = property(fget=_getSubjectConfirmations, 
                                    doc="Subject Confirmations")    
    
    def getOrderedChildren(self): 
        """Get list containing base, name and encrypted IDs and the subject 
        confirmations
        
        @return: list of all child attributes
        @rtype: list
        """ 
        children = []

        if self.baseID is not None:
            children.append(self.baseID)
        
        if self.nameID is not None: 
            children.append(self.nameID)
        
        if self.encryptedID is not None: 
            children.append(self.encryptedID)
        
        children += self.subjectConfirmations

        return tuple(children)


class AbstractNameIDType(SAMLObject):
    '''Abstract implementation of NameIDType
    
    @cvar SP_NAME_QUALIFIER_ATTRIB_NAME: SPNameQualifier attribute name.
    @type SP_NAME_QUALIFIER_ATTRIB_NAME: string
    @cvar FORMAT_ATTRIB_NAME: Format attribute name.
    @type FORMAT_ATTRIB_NAME: string
    @cvar SPPROVIDED_ID_ATTRIB_NAME: SPProviderID attribute name.
    @type SPPROVIDED_ID_ATTRIB_NAME: string
    @cvar UNSPECIFIED: URI for unspecified name format.
    @type UNSPECIFIED: string
    @cvar EMAIL: URI for email name format.
    @type EMAIL: string
    @cvar X509_SUBJECT: URI for X509 subject name format.
    @type X509_SUBJECT: string
    @cvar WIN_DOMAIN_QUALIFIED: URI for windows domain qualified name name 
    format.
    @type WIN_DOMAIN_QUALIFIED: string
    @cvar KERBEROS: URI for kerberos name format.
    @type KERBEROS: string
    @cvar ENTITY: URI for SAML entity name format.
    @type ENTITY: string
    @cvar PERSISTENT: URI for persistent name format.
    @type PERSISTENT: string
    @cvar TRANSIENT: URI for transient name format.
    @type TRANSIENT: string
    @cvar ENCRYPTED: Special URI used by NameIDPolicy to indicate a NameID 
    should be encrypted
    @type ENCRYPTED: string

    @ivar __name: Name of the Name ID.
    @type __name: string
    @ivar __nameQualifier: Name Qualifier of the Name ID.
    @type __nameQualifier: string
    @ivar __spNameQualifier: SP Name Qualifier of the Name ID.
    @type __spNameQualifier: string
    @ivar __format: Format of the Name ID.
    @type __format: string
    @ivar __spProvidedID: SP ProvidedID of the NameID.
    @type __spProvidedID: string
    '''

    # SPNameQualifier attribute name.
    SP_NAME_QUALIFIER_ATTRIB_NAME = "SPNameQualifier"

    # Format attribute name.
    FORMAT_ATTRIB_NAME = "Format"

    # SPProviderID attribute name.
    SPPROVIDED_ID_ATTRIB_NAME = "SPProvidedID"

    # URI for unspecified name format.
    UNSPECIFIED = "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"

    # URI for email name format.
    EMAIL = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"

    # URI for X509 subject name format.
    X509_SUBJECT = "urn:oasis:names:tc:SAML:1.1:nameid-format:X509SubjectName"

    # URI for windows domain qualified name name format.
    WIN_DOMAIN_QUALIFIED = \
        "urn:oasis:names:tc:SAML:1.1:nameid-format:WindowsDomainQualifiedName"

    # URI for kerberos name format.
    KERBEROS = "urn:oasis:names:tc:SAML:2.0:nameid-format:kerberos"

    # URI for SAML entity name format.
    ENTITY = "urn:oasis:names:tc:SAML:2.0:nameid-format:entity"

    # URI for persistent name format.
    PERSISTENT = "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"

    # URI for transient name format.
    TRANSIENT = "urn:oasis:names:tc:SAML:2.0:nameid-format:transient"

    # Special URI used by NameIDPolicy to indicate a NameID should be encrypted
    ENCRYPTED = "urn:oasis:names:tc:SAML:2.0:nameid-format:encrypted"
    
    __slots__ = (
        '__name',
        '__nameQualifier',
        '__spNameQualifier',
        '__format',
        '__spProvidedID',
        '__value'
    )
    
    def __init__(self, **kw): 
        '''
        @param kw: keywords to set attributes of parent class
        @type kw: dict
        '''
        super(AbstractNameIDType, self).__init__(**kw)
    
        # Name of the Name ID.
        self.__name = None
        
        # Name Qualifier of the Name ID.
        self.__nameQualifier = None
    
        # SP Name Qualifier of the Name ID.
        self.__spNameQualifier = None
    
        # Format of the Name ID.
        self.__format = None
    
        # SP ProvidedID of the NameID.
        self.__spProvidedID = None

        self.__value = None

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''

        _dict = super(AbstractNameIDType, self).__getstate__()
        for attrName in AbstractNameIDType.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_AbstractNameIDType" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
             
    def _getValue(self):
        """Get name value
        @return: name value
        @rtype: string
        """
        return self.__value
        
    def _setValue(self, value):
        """Set name value
        @param value: name value
        @type value: string
        @raise TypeError: invalid input value type
        """
        if not isinstance(value, basestring):
            raise TypeError("\"value\" must be a basestring derived type, "
                            "got %r" % value.__class__)
            
        self.__value = value

    value = property(fget=_getValue, fset=_setValue, doc="string value")  
    
    def _getNameQualifier(self): 
        """Get name qualifier
        @return: name qualifier
        @rtype: string
        """
        return self.__nameQualifier
    
    def _setNameQualifier(self, value): 
        """Set name qualifier
        @param value: name qualifier
        @type value: string
        """
        self.__nameQualifier = value

    nameQualifier = property(fget=_getNameQualifier, 
                             fset=_setNameQualifier, 
                             doc="Name qualifier")    

    def _getSPNameQualifier(self): 
        """Get SP name qualifier
        @return: SP name qualifier
        @rtype: string
        """
        return self.__spNameQualifier
    
    def _setSPNameQualifier(self, value): 
        """Set SP name qualifier
        @param value: SP name qualifier
        @type value: string
        """
        self.__spNameQualifier = value

    spNameQualifier = property(fget=_getSPNameQualifier, 
                               fset=_setSPNameQualifier, 
                               doc="SP Name qualifier")    
    
    def _getFormat(self):
        """Get name format
        @return: name format
        @rtype: string
        """
        return self.__format
        
    def _setFormat(self, format):
        """Set name format
        @param format: name format
        @type format: string
        @raise TypeError: invalid input value type
        """
        if not isinstance(format, basestring):
            raise TypeError("\"format\" must be a basestring derived type, "
                            "got %r" % format.__class__)
            
        self.__format = format

    format = property(fget=_getFormat, fset=_setFormat, doc="Name format")  
    
    def _getSPProvidedID(self): 
        """Get SP provided identifier
        @return: SP provided identifier
        @rtype: string
        """
        return self.__spProvidedID
    
    def _setSPProvidedID(self, value): 
        """Set SP provided identifier
        @param value: SP provided identifier
        @type value: string
        """
        self.__spProvidedID = value

    spProvidedID = property(fget=_getSPProvidedID, fset=_setSPProvidedID, 
                            doc="SP Provided Identifier")  
    
    def getOrderedChildren(self): 
        """Get attributes as a list - not currently implemented
        @return: list of object attribute values
        @rtype: tuple
        @raise NotImplementedError: not implemented in this version
        """
        raise NotImplementedError()

   
class Issuer(AbstractNameIDType):
    """SAML 2.0 Core Issuer type
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name.
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name.
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: Qualified Name of the XSI type.
    @type TYPE_NAME: ndg.saml.common.xml.QName
    """
    
    # Element local name. 
    DEFAULT_ELEMENT_LOCAL_NAME = "Issuer"

    # Default element name. 
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20_PREFIX)

    # Local name of the XSI type. 
    TYPE_LOCAL_NAME = "IssuerType"

    # QName of the XSI type.
    TYPE_NAME = QName(SAMLConstants.SAML20_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20_PREFIX) 
    
    __slots__ = ()

     
class NameID(AbstractNameIDType):
    '''SAML 2.0 Core NameID
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name.
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name.
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: Qualified Name of the XSI type.
    @type TYPE_NAME: ndg.saml.common.xml.QName
    '''
    
    # Element local name. 
    DEFAULT_ELEMENT_LOCAL_NAME = "NameID"

    # Default element name. 
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20_PREFIX)

    # Local name of the XSI type. 
    TYPE_LOCAL_NAME = "NameIDType"

    # QName of the XSI type. 
    TYPE_NAME = QName(SAMLConstants.SAML20_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20_PREFIX)
    
    __slots__ = ()
    

class Conditions(SAMLObject): 
    '''SAML 2.0 Core Conditions.
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name.
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name.
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: Qualified Name of the XSI type.
    @type TYPE_NAME: ndg.saml.common.xml.QName
    @cvar NOT_BEFORE_ATTRIB_NAME: NotBefore attribute name.
    @type NOT_BEFORE_ATTRIB_NAME: string
    @cvar NOT_ON_OR_AFTER_ATTRIB_NAME: NotOnOrAfter attribute name.
    @type NOT_ON_OR_AFTER_ATTRIB_NAME: string
    
    @ivar self.__conditions: A list of Conditions.
    @type self.__conditions: list
    @ivar self.__notBefore: Not Before condition
    @type self.__notBefore: NoneType / datetime.datetime
    @ivar self.__notOnOrAfter: Not On Or After conditions.
    @type self.__notOnOrAfter: NoneType / datetime.datetime
    '''
    
    # Element local name.
    DEFAULT_ELEMENT_LOCAL_NAME = "Conditions"

    # Default element name.
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20_PREFIX)

    # Local name of the XSI type.
    TYPE_LOCAL_NAME = "ConditionsType"

    # QName of the XSI type.
    TYPE_NAME = QName(SAMLConstants.SAML20_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20_PREFIX)

    # NotBefore attribute name.
    NOT_BEFORE_ATTRIB_NAME = "NotBefore"

    # NotOnOrAfter attribute name.
    NOT_ON_OR_AFTER_ATTRIB_NAME = "NotOnOrAfter"

    __slots__ = (
        '__conditions',
        '__notBefore',
        '__notOnOrAfter'
    )
    
    def __init__(self, **kw):
        super(Conditions, self).__init__(**kw)
        
        # A list of Conditions
        self.__conditions = []
    
        # Not Before time condition
        self.__notBefore = None
    
        # Not On Or After time conditions
        self.__notOnOrAfter = None

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''
        _dict = super(Conditions, self).__getstate__()
        for attrName in Conditions.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_Conditions" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
    
    def _getNotBefore(self):
        '''Get the date/time before which the assertion is invalid.
        
        @return: the date/time before which the assertion is invalid
        @rtype: NoneType / datetime.datetime
        '''
        return self.__notBefore
    
    def _setNotBefore(self, value):
        '''Sets the date/time before which the assertion is invalid.
        
        @param value: the date/time before which the assertion is invalid
        @type value: datetime.datetime
        '''
        if not isinstance(value, datetime):
            raise TypeError('Expecting "datetime" type for "notBefore", '
                            'got %r' % type(value))
        self.__notBefore = value

    def _getNotOnOrAfter(self):
        '''Gets the date/time on, or after, which the assertion is invalid.
        
        @return: the date/time on, or after, which the assertion is invalid'
        @rtype: NoneType / datetime.datetime
        '''
        return self.__notOnOrAfter
    
    def _setNotOnOrAfter(self, value):
        '''Sets the date/time on, or after, which the assertion is invalid.
        
        @param value: the date/time on, or after, which the assertion 
        is invalid
        @type value: datetime.datetime
        '''
        if not isinstance(value, datetime):
            raise TypeError('Expecting "datetime" type for "notOnOrAfter", '
                            'got %r' % type(value))
        self.__notOnOrAfter = value  

    notBefore = property(_getNotBefore, _setNotBefore, 
                         doc="Not before time restriction")

    notOnOrAfter = property(_getNotOnOrAfter, _setNotOnOrAfter, 
                            doc="Not on or after time restriction")

    @property
    def conditions(self):
        '''All the conditions on the assertion.
        
        @return: all the conditions on the assertion
        @rtype: list
        '''
        return self.__conditions
    
    def _getAudienceRestrictions(self):
        '''Get the audience restriction conditions for the assertion.
        
        @return: the audience restriction conditions for the assertion
        @rtype: list
        @raise NotImplementedError: not currently implemented
        '''
        raise NotImplementedError()

    def _getOneTimeUse(self):
        '''Get the OneTimeUse condition for the assertion
        
        @return: the OneTimeUse condition for the assertion
        @rtype: ?
        @raise NotImplementedError: not currently implemented
        '''
        raise NotImplementedError()

    def _getProxyRestriction(self):    
        '''Get the ProxyRestriction condition for the assertion
        
        @return: the ProxyRestriction condition for the assertion
        @rtype: ?
        @raise NotImplementedError: not currently implemented
        '''
        raise NotImplementedError()
    
    
class Advice(SAMLObject):
    '''SAML 2.0 Core Advice.  Only the skeleton of this class is implemented
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name.
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name.
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    '''

    # Element local name
    DEFAULT_ELEMENT_LOCAL_NAME = "Advice"

    # Default element name.
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20_PREFIX)

    # Local name of the XSI type
    TYPE_LOCAL_NAME = "AdviceType"

    # QName of the XSI type
    TYPE_NAME = QName(SAMLConstants.SAML20_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20_PREFIX)

    __slots__ = ()
    
    def _getChildren(self, typeOrName=None):
        '''
        Gets the list of all child elements attached to this advice.
        
        @return: the list of all child elements attached to this advice
        @rtype: list
        @raise NotImplementedError: not currently implemented
        '''
        raise NotImplementedError()

    def _getAssertionIDReferences(self):
        '''Gets the list of AssertionID references used as advice.
        
        @return: the list of AssertionID references used as advice
        @rtype: list
        @raise NotImplementedError: not currently implemented
        '''
        raise NotImplementedError()

    def _getAssertionURIReferences(self):
        '''Gets the list of AssertionURI references used as advice.
        
        @return: the list of AssertionURI references used as advice
        @rtype: list
        @raise NotImplementedError: not currently implemented
        '''
        raise NotImplementedError()
    
    def _getAssertions(self):
        '''Gets the list of Assertions used as advice.
        
        @return: the list of Assertions used as advice
        @rtype: list
        @raise NotImplementedError: not currently implemented
        '''
        raise NotImplementedError()
    
    def _getEncryptedAssertions(self):
        '''Gets the list of EncryptedAssertions used as advice.
        
        @return: the list of EncryptedAssertions used as advice
        @rtype: list
        @raise NotImplementedError: not currently implemented
        '''
        raise NotImplementedError()
        

class Assertion(SAMLObject):
    """SAML 2.0 Attribute Assertion for use with NERC DataGrid    

    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name.
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name.
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type.
    @type TYPE_NAME: ndg.saml.common.xml.QName
    @cvar VERSION_ATTRIB_NAME: Version attribute name.
    @type VERSION_ATTRIB_NAME: string
    @cvar ISSUE_INSTANT_ATTRIB_NAME: IssueInstant attribute name.
    @type ISSUE_INSTANT_ATTRIB_NAME: string
    @cvar ID_ATTRIB_NAME: ID attribute name.
    @type ID_ATTRIB_NAME: string
    
    @ivar __version: SAML version used
    @type __version: ndg.saml.common.SAMLVersion
    @ivar __issueInstant: issue instant for assertion
    @type __issueInstant: datetime.datetime
    @ivar __id: assertion identifier
    @type __id: string
    @ivar __issuer: issuer of this assertion
    @type __issuer: ndg.saml.saml2.core.Issuer
    @ivar __subject: subject of this assertion
    @type __subject: ndg.saml.saml2.core.Subject
    @ivar __conditions: conditions for this assertion
    @type __conditions: ndg.saml.saml2.core.Conditions
    @ivar __advice: advice statement
    @type __advice: string
    @ivar __statements: asserted statements
    @type __statements: ndg.saml.utils.TypedList
    @ivar __authnStatements: asserted authentication statements
    @type __authnStatements: list
    @ivar __authzDecisionStatements: asserted authorization decision statements
    @type __authzDecisionStatements: ndg.saml.utils.TypedList
    @ivar __attributeStatements: asserted attribute statements
    @type __attributeStatements: ndg.saml.utils.TypedList
    """   
     
    # Element local name.
    DEFAULT_ELEMENT_LOCAL_NAME = "Assertion"

    # Default element name.
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20_PREFIX)

    # Local name of the XSI type.
    TYPE_LOCAL_NAME = "AssertionType"

    # QName of the XSI type.
    TYPE_NAME = QName(SAMLConstants.SAML20_NS, TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20_PREFIX)

    # Version attribute name.
    VERSION_ATTRIB_NAME = "Version"

    # IssueInstant attribute name.
    ISSUE_INSTANT_ATTRIB_NAME = "IssueInstant"

    # ID attribute name.
    ID_ATTRIB_NAME = "ID"

    __slots__ = (
        '__version',
        '__issueInstant',
        '__id',
        '__issuer',
        '__subject',
        '__conditions',
        '__advice',
        '__statements',
        '__authnStatements',
        '__authzDecisionStatements',
        '__attributeStatements'
    )
    
    def __init__(self):
        # Base class initialisation
        super(Assertion, self).__init__()
        
        self.__version = None
        self.__issueInstant = None
        self.__id = None
        self.__issuer = None
        self.__subject = None
        
        self.__conditions = None
        self.__advice = None
        self.__statements = TypedList(Statement)
        
        # TODO: Implement AuthnStatement class
        self.__authnStatements = []
        self.__authzDecisionStatements = TypedList(AuthzDecisionStatement)
        self.__attributeStatements = TypedList(AttributeStatement)

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''
        _dict = super(Assertion, self).__getstate__()
        for attrName in Assertion.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_Assertion" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict   
                 
    def _get_version(self):
        '''
        @return: the SAML Version of this assertion
        @rtype: ndg.saml.common.SAMLVersion/NoneType
        '''
        return self.__version
    
    def _set_version(self, version):
        '''
        @param version: the SAML Version of this assertion
        @type version: ndg.saml.common.SAMLVersion
        @raise TypeError: incorrect type for input value
        '''
        if not isinstance(version, SAMLVersion):
            raise TypeError("Expecting SAMLVersion type got: %r" % 
                            version.__class__)
        
        self.__version = version
        
    version = property(fget=_get_version,
                       fset=_set_version,
                       doc="SAML Version of the assertion")

    def _get_issueInstant(self):
        '''Gets the issue instance of this assertion.
        
        @return: the issue instance of this assertion
        @rtype: datetime.datetime/NoneType
        '''
        return self.__issueInstant
    
    def _set_issueInstant(self, issueInstant):
        '''Sets the issue instance of this assertion.
        
        @param issueInstant: the issue instance of this assertion
        @type issueInstant: datetime.datetime/NoneType
        @raise TypeError: incorrect type for input value
        '''
        if not isinstance(issueInstant, datetime):
            raise TypeError('Expecting "datetime" type for "issueInstant", '
                            'got %r' % issueInstant.__class__)
            
        self.__issueInstant = issueInstant
        
    issueInstant = property(fget=_get_issueInstant, 
                            fset=_set_issueInstant,
                            doc="Issue instant of the assertion")

    def _get_id(self):
        '''Get the ID of this assertion
        
        @return: the ID of this assertion
        @rtype: basestring/NoneType
        '''
        return self.__id
    
    def _set_id(self, _id):
        '''Set the ID of this assertion
        
        @param _id: the ID of this assertion
        @type _id: basestring
        @raise TypeError: incorrect type for input value
        '''
        if not isinstance(_id, basestring):
            raise TypeError('Expecting basestring derived type for "id", got '
                            '%r' % _id.__class__)
        self.__id = _id
        
    id = property(fget=_get_id, fset=_set_id, doc="ID of assertion")
    
    def _set_issuer(self, issuer):
        """Set issuer
        @param issuer: issuer of the assertion
        @type issuer: ndg.saml.saml2.core.Issuer
        @raise TypeError: incorrect type for input value
        """
        if not isinstance(issuer, Issuer):
            raise TypeError("issuer must be %r, got %r" % (Issuer, 
                                                           type(issuer)))
        self.__issuer = issuer
    
    def _get_issuer(self):
        """Get the issuer name 
        @return: issuer name
        @rtype: ndg.saml.saml2.core.Issuer
        """
        return self.__issuer

    issuer = property(fget=_get_issuer, 
                      fset=_set_issuer,
                      doc="Issuer of assertion")
    
    def _set_subject(self, subject):
        """Set subject string
        @param subject: subject of this assertion
        @type subject: ndg.saml.saml2.core.Subject
        @raise TypeError: incorrect type for input value"""
        if not isinstance(subject, Subject):
            raise TypeError("subject must be %r, got %r" % (Subject, 
                                                            type(subject)))

        self.__subject = subject
    
    def _get_subject(self):
        """Get subject string
        
        @return: subject of this assertion
        @rtype: ndg.saml.saml2.core.Subject
        """
        return self.__subject

    subject = property(fget=_get_subject,
                       fset=_set_subject, 
                       doc="Attribute Assertion subject")
    
    def _get_conditions(self):
        """Get conditions 
        @return: conditions for this assertion
        @rtype: ndg.saml.saml2.core.Conditions
        """
        return self.__conditions
    
    def _set_conditions(self, value):
        """Set conditions 
        @param value: conditions for this assertion
        @type value: ndg.saml.saml2.core.Conditions
        @raise TypeError: incorrect type for input value"""
        if not isinstance(value, Conditions):
            raise TypeError("Conditions must be %r, got %r" % (Conditions, 
                                                               type(value)))

        self.__conditions = value

    conditions = property(fget=_get_conditions,
                          fset=_set_conditions,
                          doc="Attribute Assertion conditions")
    
    def _set_advice(self, advice):
        """Set advice string
        
        @param advice: advice for this assertion
        @type advice: basestring
        @raise TypeError: incorrect type for input value"""
        if not isinstance(advice, basestring):
            raise TypeError("advice must be a string")

        self.__advice = advice
    
    def _get_advice(self):
        """Get advice string
        
        @return: advice for this assertion
        @rtype: basestring
        """
        return self.__advice

    advice = property(fget=_get_advice,
                      fset=_set_advice, 
                      doc="Attribute Assertion advice")
    
    @property
    def statements(self):
        """Assertion statements
        
        @return: list of assertion statements
        @rtype: ndg.saml.utils.TypedList
        """
        return self.__statements
    
    @property
    def authnStatements(self):
        """Attribute Assertion authentication
        
        @return: list of assertion statements
        @rtype: ndg.saml.utils.TypedList
        """
        return self.__authnStatements
    
    @property
    def authzDecisionStatements(self):
        """Attribute Assertion authorisation decision statements
        
        @return: list of assertion statements
        @rtype: ndg.saml.utils.TypedList
        """
        return self.__authzDecisionStatements
    
    @property
    def attributeStatements(self):
        """Attribute Assertion attribute statements
        
        @return: list of assertion statements
        @rtype: ndg.saml.utils.TypedList
        """
        return self.__attributeStatements
    

class AttributeValue(SAMLObject):
    """Base class for Attribute Value type
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element name, no namespace
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName    
    """
    
    # Element name, no namespace
    DEFAULT_ELEMENT_LOCAL_NAME = "AttributeValue"

    # Default element name
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20_PREFIX)
    __slots__ = ()


class XSStringAttributeValue(AttributeValue):
    """XML XS:String Attribute Value type
    
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type
    @type TYPE_NAME: ndg.saml.common.xml.QName
    
    @ivar __value: value of this attribute
    @type __value: basestring
    """
    
    # Local name of the XSI type
    TYPE_LOCAL_NAME = "string"
        
    # QName of the XSI type
    TYPE_NAME = QName(SAMLConstants.XSD_NS, 
                      TYPE_LOCAL_NAME, 
                      SAMLConstants.XSD_PREFIX)
    
    DEFAULT_FORMAT = "%s#%s" % (SAMLConstants.XSD_NS, TYPE_LOCAL_NAME)
  
    __slots__ = ('__value',)
    
    def __init__(self, **kw):
        """
        @param kw: keywords for setting attributes of parent class
        @type kw: dict
        """
        super(XSStringAttributeValue, self).__init__(**kw)
        self.__value = None

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''
        _dict = super(XSStringAttributeValue, self).__getstate__()
        for attrName in XSStringAttributeValue.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_XSStringAttributeValue" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
            
    def _getValue(self):
        """Set value of XS string
        @return: value of string to assign
        @rtype: string
        """
        return self.__value
        
    def _setValue(self, value):
        """Set value of XS string
        @param value: value
        @type value: string
        @raise TypeError: invalid input value type
        """
        if not isinstance(value, basestring):
            raise TypeError("Input must be a basestring derived type, got %r" %
                            value.__class__)
            
        self.__value = value

    value = property(fget=_getValue, fset=_setValue, doc="string value")  


class StatusDetail(SAMLObject):
    '''Implementation of SAML 2.0 StatusDetail
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Local Name of StatusDetail.
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name.
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type.
    @type TYPE_NAME: ndg.saml.common.xml.QName
    
    @ivar __unknownChildren: unknown child elements
    @type __unknownChildren: ndg.saml.common.SAMLObject
    
    '''
    
    # Local Name of StatusDetail.
    DEFAULT_ELEMENT_LOCAL_NAME = "StatusDetail"

    # Default element name.
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20P_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20P_PREFIX)

    # Local name of the XSI type.
    TYPE_LOCAL_NAME = "StatusDetailType"

    # QName of the XSI type.
    TYPE_NAME = QName(SAMLConstants.SAML20P_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20P_PREFIX)
    
    __slots__ = ('__unknownChildren', )
    
    def __init__(self, **kw):
        """
        @param kw: keywords for setting attributes of parent class
        @type kw: dict
        """
        super(StatusDetail, self).__init__(**kw)
        
        # child "any" elements.
        self.__unknownChildren = TypedList(SAMLObject)         

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''

        _dict = super(StatusDetail, self).__getstate__()
        for attrName in StatusDetail.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_StatusDetail" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
    
    def getUnknownXMLTypes(self, qname=None):
        """Retrieve unknown child attributes
        
        This is untested
        @param qname: qualified name for matching types to be retrieved
        @type qname: ndg.saml.common.xml.QName
        @raise TypeError: incorrect type for qname keyword
        """ 
        if qname is not None:
            if not isinstance(qname, QName):
                raise TypeError("\"qname\" must be a %r derived type, "
                                "got %r" % (QName, type(qname)))
                
            children = []
            for child in self.__unknownChildren:
                childQName = getattr(child, "qname", None)
                if childQName is not None:
                    if childQName.namespaceURI == qname.namespaceURI or \
                       childQName.localPart == qname.localPart:
                        children.append(child)
                        
            return children
        else:
            return self.__unknownChildren
    
    unknownChildren = property(fget=getUnknownXMLTypes,
                               doc="Child objects of Status Detail - may be "
                                   "any type")
    

class StatusMessage(SAMLObject):
    '''Implementation of SAML 2.0 Status Message
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME:  Local name of the Status message element
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME:  Default element name
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    
    @ivar __value: message text
    @type __value: basestring
    '''

    DEFAULT_ELEMENT_LOCAL_NAME = "StatusMessage"
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20P_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20P_PREFIX)
    
    __slots__ = ('__value', )
    
    def __init__(self, **kw):
        super(StatusMessage, self).__init__(**kw)
        
        # message text
        self.__value = None        

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''
        _dict = super(StatusMessage, self).__getstate__()
        for attrName in StatusMessage.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_StatusMessage" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
    
    def _getValue(self):
        '''
        @return: message text
        @rtype: basestring
        '''
        return self.__value
        
    def _setValue(self, value):
        '''
        @param value: message text
        @type value: basestring
        @raise TypeError: incorrect type for input value
        '''
        if not isinstance(value, basestring):
            raise TypeError("\"value\" must be a basestring derived type, "
                            "got %r" % type(value))
            
        self.__value = value

    value = property(fget=_getValue, fset=_setValue, doc="Status message value")


class StatusCode(SAMLObject):
    '''Implementation of SAML 2.0 StatusCode.
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Local Name of StatusCode.                                                                        
    @type DEFAULT_ELEMENT_LOCAL_NAME: string                                                                                           
    @cvar DEFAULT_ELEMENT_NAME: Default element name.                                                                                  
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName                                                                                                 
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.                                                                                 
    @type TYPE_LOCAL_NAME: string                                                                                                      
    @cvar TYPE_NAME: QName of the XSI type.                                                                                            
    @type TYPE_NAME: ndg.saml.common.xml.QName                                                                                                            
    @cvar VALUE_ATTRIB_NAME: Local Name of the Value attribute.                                                                        
    @type VALUE_ATTRIB_NAME: string                                                                                                    
    @cvar SUCCESS_URI: URI for Success status code.                                                                                    
    @type SUCCESS_URI: string                                                                                                          
    @cvar REQUESTER_URI: URI for Requester status code.                                                                                
    @type REQUESTER_URI: string                                                                                                        
    @cvar RESPONDER_URI: URI for Responder status code.
    @type RESPONDER_URI: string
    @cvar VERSION_MISMATCH_URI: URI for VersionMismatch status code.
    @type VERSION_MISMATCH_URI: string
    @cvar AUTHN_FAILED_URI: URI for AuthnFailed status code.
    @type AUTHN_FAILED_URI: string
    @cvar INVALID_ATTR_NAME_VALUE_URI: URI for InvalidAttrNameOrValue status code.
    @type INVALID_ATTR_NAME_VALUE_URI: string
    @cvar INVALID_NAMEID_POLICY_URI: URI for InvalidNameIDPolicy status code.
    @type INVALID_NAMEID_POLICY_URI: string
    @cvar NO_AUTHN_CONTEXT_URI: URI for NoAuthnContext status code.
    @type NO_AUTHN_CONTEXT_URI: string
    @cvar NO_AVAILABLE_IDP_URI: URI for NoAvailableIDP status code.
    @type NO_AVAILABLE_IDP_URI: string
    @cvar NO_PASSIVE_URI: URI for NoPassive status code.
    @type NO_PASSIVE_URI: string
    @cvar NO_SUPPORTED_IDP_URI: URI for NoSupportedIDP status code.
    @type NO_SUPPORTED_IDP_URI: string
    @cvar PARTIAL_LOGOUT_URI: URI for PartialLogout status code.
    @type PARTIAL_LOGOUT_URI: string
    @cvar PROXY_COUNT_EXCEEDED_URI: URI for ProxyCountExceeded status code.
    @type PROXY_COUNT_EXCEEDED_URI: string
    @cvar REQUEST_DENIED_URI: URI for RequestDenied status code.
    @type REQUEST_DENIED_URI: string
    @cvar REQUEST_UNSUPPORTED_URI: URI for RequestUnsupported status code.
    @type REQUEST_UNSUPPORTED_URI: string
    @cvar REQUEST_VERSION_DEPRECATED_URI: URI for RequestVersionDeprecated status code.
    @type REQUEST_VERSION_DEPRECATED_URI: string
    @cvar REQUEST_VERSION_TOO_HIGH_URI: URI for RequestVersionTooHigh status code.
    @type REQUEST_VERSION_TOO_HIGH_URI: string
    @cvar REQUEST_VERSION_TOO_LOW_URI: URI for RequestVersionTooLow status code.
    @type REQUEST_VERSION_TOO_LOW_URI: string
    @cvar RESOURCE_NOT_RECOGNIZED_URI: URI for ResourceNotRecognized status code.
    @type RESOURCE_NOT_RECOGNIZED_URI: string
    @cvar TOO_MANY_RESPONSES: URI for TooManyResponses status code.
    @type TOO_MANY_RESPONSES: string
    @cvar UNKNOWN_ATTR_PROFILE_URI: URI for UnknownAttrProfile status code.
    @type UNKNOWN_ATTR_PROFILE_URI: string
    @cvar UNKNOWN_PRINCIPAL_URI: URI for UnknownPrincipal status code.
    @type UNKNOWN_PRINCIPAL_URI: string
    @cvar UNSUPPORTED_BINDING_URI: URI for UnsupportedBinding status code.
    @type UNSUPPORTED_BINDING_URI: string
    
    @ivar __value: status code value
    @type __value:
    @ivar __childStatusCode: child element status code value
    @type __childStatusCode:
    '''
    
    # Local Name of StatusCode.
    DEFAULT_ELEMENT_LOCAL_NAME = "StatusCode"

    # Default element name.
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20P_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20P_PREFIX)

    # Local name of the XSI type.
    TYPE_LOCAL_NAME = "StatusCodeType"

    # QName of the XSI type.
    TYPE_NAME = QName(SAMLConstants.SAML20P_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20P_PREFIX)

    # Local Name of the Value attribute.
    VALUE_ATTRIB_NAME = "Value"

    # URI for Success status code.
    SUCCESS_URI = "urn:oasis:names:tc:SAML:2.0:status:Success"

    # URI for Requester status code.
    REQUESTER_URI = "urn:oasis:names:tc:SAML:2.0:status:Requester"

    # URI for Responder status code.
    RESPONDER_URI = "urn:oasis:names:tc:SAML:2.0:status:Responder"

    # URI for VersionMismatch status code.
    VERSION_MISMATCH_URI = "urn:oasis:names:tc:SAML:2.0:status:VersionMismatch"

    # URI for AuthnFailed status code.
    AUTHN_FAILED_URI = "urn:oasis:names:tc:SAML:2.0:status:AuthnFailed"

    # URI for InvalidAttrNameOrValue status code.
    INVALID_ATTR_NAME_VALUE_URI = \
                "urn:oasis:names:tc:SAML:2.0:status:InvalidAttrNameOrValue"

    # URI for InvalidNameIDPolicy status code.
    INVALID_NAMEID_POLICY_URI = \
                "urn:oasis:names:tc:SAML:2.0:status:InvalidNameIDPolicy"

    # URI for NoAuthnContext status code.
    NO_AUTHN_CONTEXT_URI = "urn:oasis:names:tc:SAML:2.0:status:NoAuthnContext"

    # URI for NoAvailableIDP status code.
    NO_AVAILABLE_IDP_URI = "urn:oasis:names:tc:SAML:2.0:status:NoAvailableIDP"

    # URI for NoPassive status code.
    NO_PASSIVE_URI = "urn:oasis:names:tc:SAML:2.0:status:NoPassive"

    # URI for NoSupportedIDP status code.
    NO_SUPPORTED_IDP_URI = "urn:oasis:names:tc:SAML:2.0:status:NoSupportedIDP"

    # URI for PartialLogout status code.
    PARTIAL_LOGOUT_URI = "urn:oasis:names:tc:SAML:2.0:status:PartialLogout"

    # URI for ProxyCountExceeded status code.
    PROXY_COUNT_EXCEEDED_URI = \
                "urn:oasis:names:tc:SAML:2.0:status:ProxyCountExceeded"

    # URI for RequestDenied status code.
    REQUEST_DENIED_URI = "urn:oasis:names:tc:SAML:2.0:status:RequestDenied"

    # URI for RequestUnsupported status code.
    REQUEST_UNSUPPORTED_URI = \
                "urn:oasis:names:tc:SAML:2.0:status:RequestUnsupported"

    # URI for RequestVersionDeprecated status code.
    REQUEST_VERSION_DEPRECATED_URI = \
                "urn:oasis:names:tc:SAML:2.0:status:RequestVersionDeprecated"

    # URI for RequestVersionTooHigh status code.
    REQUEST_VERSION_TOO_HIGH_URI = \
                "urn:oasis:names:tc:SAML:2.0:status:RequestVersionTooHigh"
    
    # URI for RequestVersionTooLow status code.
    REQUEST_VERSION_TOO_LOW_URI = \
                "urn:oasis:names:tc:SAML:2.0:status:RequestVersionTooLow"

    # URI for ResourceNotRecognized status code.
    RESOURCE_NOT_RECOGNIZED_URI = \
                "urn:oasis:names:tc:SAML:2.0:status:ResourceNotRecognized"

    # URI for TooManyResponses status code.
    TOO_MANY_RESPONSES = "urn:oasis:names:tc:SAML:2.0:status:TooManyResponses"

    # URI for UnknownAttrProfile status code.
    UNKNOWN_ATTR_PROFILE_URI = \
                "urn:oasis:names:tc:SAML:2.0:status:UnknownAttrProfile"

    # URI for UnknownPrincipal status code.
    UNKNOWN_PRINCIPAL_URI = \
                "urn:oasis:names:tc:SAML:2.0:status:UnknownPrincipal"

    # URI for UnsupportedBinding status code.
    UNSUPPORTED_BINDING_URI = \
                "urn:oasis:names:tc:SAML:2.0:status:UnsupportedBinding"

    __slots__ = ('__value', '__childStatusCode',)
    
    def __init__(self, **kw):
        """
        @param kw: keywords to initialise superclass attributes
        @type kw: dict
        """
        super(StatusCode, self).__init__(**kw)
        
        # Value attribute URI.
        self.__value = None
    
        # Nested secondary StatusCode child element.
        self.__childStatusCode = None

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''

        _dict = super(StatusCode, self).__getstate__()
        for attrName in StatusCode.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_StatusCode" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
    
    def _getStatusCode(self): 
        """Get child status code
        @return: status code value
        @rtype: ndg.saml.saml2.core.StatusCode
        """
        return self.__childStatusCode
    
    def _setStatusCode(self, value):
        """Set child status code
        @param value: status code value
        @type value: ndg.saml.saml2.core.StatusCode
        """
        if not isinstance(value, StatusCode):
            raise TypeError('Child "statusCode" must be a %r derived type, '
                            "got %r" % (StatusCode, type(value)))
            
        self.__childStatusCode = value

    value = property(fget=_getStatusCode, 
                     fset=_setStatusCode, 
                     doc="Child Status code")
              
    def _getValue(self):
        """Get status message
        @return: message text
        @rtype: basestring
        """ 
        return self.__value
        
    def _setValue(self, value):
        """Set status message
        @param value: message text
        @type value: basestring
        """ 
        if not isinstance(value, basestring):
            raise TypeError("\"value\" must be a basestring derived type, "
                            "got %r" % value.__class__)
            
        self.__value = value

    value = property(fget=_getValue, fset=_setValue, doc="Status code value")
        

class Status(SAMLObject): 
    '''SAML 2.0 Core Status
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Local Name of Status.
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name.
    @type DEFAULT_ELEMENT_NAME: ndg.common.xml.QName
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type.
    @type TYPE_NAME: ndg.common.xml.QName
    
    @ivar __statusCode: status code
    @type __statusCode: ndg.saml.saml2.core.StatusCode
    @ivar __statusMessage: status message
    @type __statusMessage: ndg.saml.saml2.core.StatusMessage
    @ivar __statusDetail: status detail
    @type __statusDetail: ndg.saml.saml2.core.StatusDetail
    '''
    
    # Local Name of Status.
    DEFAULT_ELEMENT_LOCAL_NAME = "Status"

    # Default element name.
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20P_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20P_PREFIX)

    # Local name of the XSI type.
    TYPE_LOCAL_NAME = "StatusType"

    # QName of the XSI type.
    TYPE_NAME = QName(SAMLConstants.SAML20P_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20P_PREFIX)

    __slots__ = (
        '__statusCode', 
        '__statusMessage', 
        '__statusDetail', 
    )
    
    def __init__(self, **kw):
        super(Status, self).__init__(**kw)
        
        # StatusCode element.
        self.__statusCode = None
    
        # StatusMessage element.
        self.__statusMessage = None
    
        # StatusDetail element. 
        self.__statusDetail = None
        
    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''
        _dict = super(Status, self).__getstate__()
        for attrName in Status.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_Status" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
    
    def _getStatusCode(self):
        '''Get the Code of this Status
        
        @return: Status object's StatusCode
        @rtype: ndg.saml.saml2.core.StatusCode
        '''
        return self.__statusCode

    def _setStatusCode(self, value):
        '''Set the Code of this Status
        
        @param value: the Code of this Status object
        @type value: ndg.saml.saml2.core.StatusCode
        @raise TypeError: incorrect type for input code value
        '''
        if not isinstance(value, StatusCode):
            raise TypeError('"statusCode" must be a %r derived type, '
                            "got %r" % (StatusCode, type(value)))
            
        self.__statusCode = value
        
    statusCode = property(fget=_getStatusCode,
                          fset=_setStatusCode,
                          doc="status code object")
    
    def _getStatusMessage(self):
        '''Get the Message of this Status.
        
        @return: Status message
        @rtype: ndg.saml.saml2.core.StatusMessage
        '''
        return self.__statusMessage

    def _setStatusMessage(self, value):
        '''Set the Message of this Status
        
        @param value: the Message associated with this Status
        @type value: ndg.saml.saml2.core.StatusMessage
        @raise TypeError: incorrect input value type
        '''
        if not isinstance(value, StatusMessage):
            raise TypeError('"statusMessage" must be a %r derived type, '
                            "got %r" % (StatusMessage, type(value)))
            
        self.__statusMessage = value
        
    statusMessage = property(fget=_getStatusMessage,
                             fset=_setStatusMessage,
                             doc="status message")

    def _getStatusDetail(self):
        '''Get the Detail of this Status
        
        @return: Status object's StatusDetail
        @rtype: ndg.saml.saml2.core.StatusDetail
        '''
        return self.__statusDetail
    
    def _setStatusDetail(self, value):
        '''
        Sets the Detail of this Status.
        
        @param value: the Detail of this Status
        @type value: ndg.saml.saml2.core.StatusDetail;
        @raise TypeError: incorrect input value type
        '''
        if not isinstance(value, StatusDetail):
            raise TypeError('"statusDetail" must be a %r derived type, '
                            "got %r" % (StatusDetail, type(value)))
        self.__statusDetail = value
        
    statusDetail = property(fget=_getStatusDetail,
                            fset=_setStatusDetail,
                            doc="status detail")


class Action(SAMLObject): 
    '''SAML 2.0 Core Action
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name.                                  
    @type DEFAULT_ELEMENT_LOCAL_NAME: string                                               
    @cvar DEFAULT_ELEMENT_NAME: Default element name.                                      
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName                                                     
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.                                     
    @type TYPE_LOCAL_NAME: string                                                          
    @cvar TYPE_NAME: QName of the XSI type                                                 
    @type TYPE_NAME: ndg.saml.common.xml.QName                                                                
    @cvar NAMESPACE_ATTRIB_NAME: Name of the Namespace attribute.
    @type NAMESPACE_ATTRIB_NAME: string
    @cvar RWEDC_NS_URI: Read/Write/Execute/Delete/Control action namespace.
    @type RWEDC_NS_URI: string
    @cvar RWEDC_NEGATION_NS_URI: Read/Write/Execute/Delete/Control negation 
    action namespace.
    @type RWEDC_NEGATION_NS_URI: string
    @cvar GHPP_NS_URI: Get/Head/Put/Post action namespace.
    @type GHPP_NS_URI: string
    @cvar UNIX_NS_URI: UNIX file permission action namespace.
    @type UNIX_NS_URI: string
    @cvar ACTION_NS_IDENTIFIERS: Action namespace identifiers
    @type ACTION_NS_IDENTIFIERS: tuple
    @cvar READ_ACTION: Read action.
    @type READ_ACTION: string
    @cvar WRITE_ACTION: Write action.
    @type WRITE_ACTION: string
    @cvar EXECUTE_ACTION: Execute action.
    @type EXECUTE_ACTION: string
    @cvar DELETE_ACTION: Delete action.
    @type DELETE_ACTION: string
    @cvar CONTROL_ACTION: Control action.
    @type CONTROL_ACTION: string
    @cvar NEG_READ_ACTION: Negated Read action.
    @type NEG_READ_ACTION: string
    @cvar NEG_WRITE_ACTION: Negated Write action.
    @type NEG_WRITE_ACTION: string
    @cvar NEG_EXECUTE_ACTION: Negated Execute action.
    @type NEG_EXECUTE_ACTION: string
    @cvar NEG_DELETE_ACTION: Negated Delete action.
    @type NEG_DELETE_ACTION: string
    @cvar NEG_CONTROL_ACTION: Negated Control action.
    @type NEG_CONTROL_ACTION: string
    @cvar HTTP_GET_ACTION: HTTP GET action.
    @type HTTP_GET_ACTION: string
    @cvar HTTP_HEAD_ACTION: HTTP HEAD action.
    @type HTTP_HEAD_ACTION: string
    @cvar HTTP_PUT_ACTION: HTTP PUT action.
    @type HTTP_PUT_ACTION: string
    @cvar HTTP_POST_ACTION: HTTP POST action.
    @type HTTP_POST_ACTION: string
    @cvar ACTION_TYPES: Recognised action URI to action types mapping
    @type ACTION_TYPES: dict 
       
    @ivar __namespace: action namespace
    @type __namespace: string
    @ivar __value: action type value
    @type __value: string
    @ivar __actionTypes: valid action types for each of a given set of action
    namespaces
    @type __actionTypes: dict
    '''
    
    # Element local name. 
    DEFAULT_ELEMENT_LOCAL_NAME = "Action"

    # Default element name. 
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20_PREFIX)

    # Local name of the XSI type. 
    TYPE_LOCAL_NAME = "ActionType"

    # QName of the XSI type 
    TYPE_NAME = QName(SAMLConstants.SAML20_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20_PREFIX)

    # Name of the Namespace attribute. 
    NAMESPACE_ATTRIB_NAME = "Namespace"

    # Read/Write/Execute/Delete/Control action namespace. 
    RWEDC_NS_URI = "urn:oasis:names:tc:SAML:1.0:action:rwedc"

    # Read/Write/Execute/Delete/Control negation action namespace. 
    RWEDC_NEGATION_NS_URI = "urn:oasis:names:tc:SAML:1.0:action:rwedc-negation"

    # Get/Head/Put/Post action namespace. 
    GHPP_NS_URI = "urn:oasis:names:tc:SAML:1.0:action:ghpp"

    # UNIX file permission action namespace. 
    UNIX_NS_URI = "urn:oasis:names:tc:SAML:1.0:action:unix"

    # Action namespace identifiers
    ACTION_NS_IDENTIFIERS = (
        RWEDC_NS_URI,
        RWEDC_NEGATION_NS_URI,    
        GHPP_NS_URI,
        UNIX_NS_URI       
    )
    
    # Read action. 
    READ_ACTION = "Read"

    # Write action. 
    WRITE_ACTION = "Write"

    # Execute action. 
    EXECUTE_ACTION = "Execute"

    # Delete action. 
    DELETE_ACTION = "Delete"

    # Control action. 
    CONTROL_ACTION = "Control"

    # Negated Read action. 
    NEG_READ_ACTION = "~Read"

    # Negated Write action. 
    NEG_WRITE_ACTION = "~Write"

    # Negated Execute action. 
    NEG_EXECUTE_ACTION = "~Execute"

    # Negated Delete action. 
    NEG_DELETE_ACTION = "~Delete"

    # Negated Control action. 
    NEG_CONTROL_ACTION = "~Control"

    # HTTP GET action. 
    HTTP_GET_ACTION = "GET"

    # HTTP HEAD action. 
    HTTP_HEAD_ACTION = "HEAD"

    # HTTP PUT action. 
    HTTP_PUT_ACTION = "PUT"

    # HTTP POST action. 
    HTTP_POST_ACTION = "POST"
    
    # Recognised action URI to action types mapping
    ACTION_TYPES = {
        RWEDC_NS_URI: (READ_ACTION, WRITE_ACTION, EXECUTE_ACTION, DELETE_ACTION,
                       CONTROL_ACTION),
        RWEDC_NEGATION_NS_URI: (READ_ACTION, WRITE_ACTION, EXECUTE_ACTION, 
                                DELETE_ACTION, CONTROL_ACTION, NEG_READ_ACTION, 
                                NEG_WRITE_ACTION, NEG_EXECUTE_ACTION, 
                                NEG_CONTROL_ACTION),    
        GHPP_NS_URI: (HTTP_GET_ACTION, HTTP_HEAD_ACTION, HTTP_PUT_ACTION,
                      HTTP_POST_ACTION),
                      
        # This namespace uses octal bitmask for file permissions
        UNIX_NS_URI: ()   
    }
    
    __slots__ = (
        '__namespace', 
        '__value', 
        '__actionTypes'
    )
    
    def __init__(self, **kw):
        '''Create an authorization action type
        '''
        super(Action, self).__init__(**kw)

        # URI of the Namespace of this action.  Default to read/write/negation 
        # type - 2.7.4.2 SAML 2 Core Spec. 15 March 2005
        self.__namespace = Action.RWEDC_NEGATION_NS_URI

        # Action value
        self.__value = None       
    
        self.__actionTypes = Action.ACTION_TYPES
        
    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''
        _dict = super(Action, self).__getstate__()
        for attrName in Action.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_Action" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
    
    def _getActionTypes(self):
        """Get action namespace to action types map
        @return: action types map
        @rtype: dict
        """ 
        return self.__actionTypes

    def _setActionTypes(self, value):
        """Set action namespace to action types map
        @param value: action types map
        @type value: dict
        @raise TypeError: incorrect type for input value
        """ 
        if not isinstance(value, dict):
            raise TypeError('Expecting list or tuple type for "actionTypes" '
                            'attribute; got %r' % type(value))
            
        for k, v in value.items():
            if not isinstance(v, (tuple, type(None))):
                raise TypeError('Expecting None or tuple type for '
                                '"actionTypes" dictionary values; got %r for '
                                '%r key' % (type(value), k))
        self.__actionTypes = value

    actionTypes = property(_getActionTypes, 
                           _setActionTypes, 
                           doc="Restrict vocabulary of action types")
        
    def _getNamespace(self):
        '''Get the namespace of the action
        
        @return: the namespace of the action
        @rtype: basestring
        '''
        return self.__namespace

    def _setNamespace(self, value):
        '''Set the namespace of the action
        
        @param value: the namespace of the action
        @type value: basestring
        '''
        if not isinstance(value, basestring):
            raise TypeError('Expecting string type for "namespace" '
                            'attribute; got %r' % type(value))
            
        if value not in self.__actionTypes.keys():
            raise AttributeError('"namespace" action type %r not recognised. '
                                 'It must be one of these action types: %r' % 
                                 self.__actionTypes.keys())
            
        self.__namespace = value

    namespace = property(_getNamespace, _setNamespace, doc="Action Namespace")

    def _getValue(self):
        '''Get the URI of the action to be performed.
        
        @return: the URI of the action to be performed
        @rtype: basestring or int
        '''
        return self.__value

    def _setValue(self, value):
        '''Set the URI of the action to be performed.
        
        @param value: the URI of the value to be performed
        @type value: basestring or int
        @raise TypeError: incorrect type for input value
        '''
        # int and oct allow for UNIX file permissions action type
        if not isinstance(value, (basestring, int)):
            raise TypeError('Expecting string or int type for "action" '
                            'attribute; got %r' % type(value))
            
        # Default to read/write/negation type - 2.7.4.2 SAML 2 Core Spec.
        # 15 March 2005
        allowedActions = self.__actionTypes.get(self.__namespace,
                                                Action.RWEDC_NEGATION_NS_URI)
        
        # Only apply restriction for action type that has a restricted 
        # vocabulary - UNIX type is missed out of this because its an octal
        # mask
        if len(allowedActions) > 0 and value not in allowedActions:
            raise AttributeError('%r action not recognised; known actions for '
                                 'the %r namespace identifier are: %r.  ' 
                                 'If this is not as expected make sure to set '
                                 'the "namespace" attribute to an alternative '
                                 'value first or override completely by '
                                 'explicitly setting the "allowTypes" '
                                 'attribute' % 
                                 (value, self.__namespace, allowedActions))
        self.__value = value

    value = property(_getValue, _setValue, doc="Action string")
        

class RequestAbstractType(SAMLObject): 
    '''SAML 2.0 Core RequestAbstractType
    
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type.
    @type TYPE_NAME: ndg.saml.common.xml.QName
    @cvar ID_ATTRIB_NAME: ID attribute name.
    @type ID_ATTRIB_NAME: string
    @cvar VERSION_ATTRIB_NAME: Version attribute name.
    @type VERSION_ATTRIB_NAME: string
    @cvar ISSUE_INSTANT_ATTRIB_NAME: IssueInstant attribute name.
    @type ISSUE_INSTANT_ATTRIB_NAME: string
    @cvar DESTINATION_ATTRIB_NAME: Destination attribute name.
    @type DESTINATION_ATTRIB_NAME: string
    @cvar CONSENT_ATTRIB_NAME: Consent attribute name.
    @type CONSENT_ATTRIB_NAME: string
    @cvar UNSPECIFIED_CONSENT: Unspecified consent URI.
    @type UNSPECIFIED_CONSENT: string
    @cvar OBTAINED_CONSENT: Obtained consent URI.
    @type OBTAINED_CONSENT: string
    @cvar PRIOR_CONSENT: Prior consent URI.
    @type PRIOR_CONSENT: string
    @cvar IMPLICIT_CONSENT: Implicit consent URI.
    @type IMPLICIT_CONSENT: string
    @cvar EXPLICIT_CONSENT: Explicit consent URI.
    @type EXPLICIT_CONSENT: string
    @cvar UNAVAILABLE_CONSENT: Unavailable consent URI.
    @type UNAVAILABLE_CONSENT: string
    @cvar INAPPLICABLE_CONSENT: Inapplicable consent URI.
    @type INAPPLICABLE_CONSENT: string
    
    @ivar __version: SAML version
    @type __version: string
    @ivar __id: request identifier
    @type __id: string
    @ivar __issueInstant: issue instant
    @type __issueInstant: string
    @ivar __destination: destination for request
    @type __destination: string
    @ivar __consent: consent information
    @type __consent: string
    @ivar __issuer: request issuer identifier
    @type __issuer: string
    @ivar __extensions: request extensions
    @type __extensions: string
    '''
    
    # Local name of the XSI type.
    TYPE_LOCAL_NAME = "RequestAbstractType"

    # QName of the XSI type.
    TYPE_NAME = QName(SAMLConstants.SAML20P_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20P_PREFIX)

    # ID attribute name.
    ID_ATTRIB_NAME = "ID"

    # Version attribute name.
    VERSION_ATTRIB_NAME = "Version"

    # IssueInstant attribute name.
    ISSUE_INSTANT_ATTRIB_NAME = "IssueInstant"

    # Destination attribute name.
    DESTINATION_ATTRIB_NAME = "Destination"

    # Consent attribute name.
    CONSENT_ATTRIB_NAME = "Consent"

    # Unspecified consent URI.
    UNSPECIFIED_CONSENT = "urn:oasis:names:tc:SAML:2.0:consent:unspecified"

    # Obtained consent URI.
    OBTAINED_CONSENT = "urn:oasis:names:tc:SAML:2.0:consent:obtained"

    # Prior consent URI.
    PRIOR_CONSENT = "urn:oasis:names:tc:SAML:2.0:consent:prior"

    # Implicit consent URI.
    IMPLICIT_CONSENT = "urn:oasis:names:tc:SAML:2.0:consent:implicit"

    # Explicit consent URI.
    EXPLICIT_CONSENT = "urn:oasis:names:tc:SAML:2.0:consent:explicit"

    # Unavailable consent URI.
    UNAVAILABLE_CONSENT = "urn:oasis:names:tc:SAML:2.0:consent:unavailable"

    # Inapplicable consent URI.
    INAPPLICABLE_CONSENT = "urn:oasis:names:tc:SAML:2.0:consent:inapplicable"
     
    __slots__ = (
        '__version',
        '__id',
        '__issueInstant',
        '__destination',
        '__consent',
        '__issuer',
        '__extensions'
    )
    
    def __init__(self, **kw):
        '''Request abstract type
        @type kw: dict
        @param kw: see SAMLObject.__init__
        '''
        super(RequestAbstractType, self).__init__(**kw)
        
        # SAML Version of the request. 
        self.__version = None
    
        # Unique identifier of the request. 
        self.__id = None
    
        # Date/time request was issued. 
        self.__issueInstant = None
    
        # URI of the request destination. 
        self.__destination = None
    
        # URI of the SAML user consent type. 
        self.__consent = None
    
        # URI of the SAML user consent type. 
        self.__issuer = None
    
        # Extensions child element. 
        self.__extensions = None

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''

        _dict = super(RequestAbstractType, self).__getstate__()
        for attrName in RequestAbstractType.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_RequestAbstractType" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
    
    def _get_version(self):
        '''
        @return: the SAML Version of this assertion
        @rtype: ndg.saml.common.SAMLVersion
        '''
        return self.__version
    
    def _set_version(self, version):
        '''
        @param version: the SAML Version of this assertion
        @type version: ndg.saml.common.SAMLVersion
        @raise TypeError: incorrect input version value type
        '''
        if not isinstance(version, SAMLVersion):
            raise TypeError("Expecting SAMLVersion type got: %r" % 
                            version.__class__)
        
        self.__version = version
        
    version = property(fget=_get_version,
                       fset=_set_version,
                       doc="SAML Version of the assertion")

    def _get_issueInstant(self):
        '''Get the date/time the request was issued
        
        @return: the issue instance of this request
        @rtype: datetime.datetime
        '''
        return self.__issueInstant
    
    def _set_issueInstant(self, value):
        '''Sets the date/time the request was issued
        
        @param value: the issue instance of this request
        @type value: datetime.datetime
        '''
        if not isinstance(value, datetime):
            raise TypeError('Expecting "datetime" type for "issueInstant", '
                            'got %r' % type(value))
            
        self.__issueInstant = value
        
    issueInstant = property(fget=_get_issueInstant, 
                            fset=_set_issueInstant,
                            doc="Issue instant of the request") 

    def _get_id(self):
        '''Get the unique identifier for this request
        
        @return: the ID of this request
        @rtype: basestring
        '''
        return self.__id
    
    def _set_id(self, value):
        '''Set the unique identifier for this request
        
        @param value: the ID of this assertion
        @type value: basestring
        @raise TypeError: incorrect input type
        '''
        if not isinstance(value, basestring):
            raise TypeError('Expecting basestring derived type for "id", got '
                            '%r' % type(value))
        self.__id = value
        
    id = property(fget=_get_id, fset=_set_id, doc="ID of request")

    def _get_destination(self):
        '''Get the URI of the destination of the request
        
        @return: the URI of the destination of the request
        @rtype: basestring
        '''
        return self.__destination
    
    def _set_destination(self, value):
        '''Set the URI of the destination of the request
        
        @param value: the URI of the destination of the request
        @type value: basestring
        @raise TypeError: incorrect input value type
        '''
        if not isinstance(value, basestring):
            raise TypeError('Expecting basestring derived type for '
                            '"destination", got %r' % type(value))
        self.__destination = value
        
    destination = property(fget=_get_destination, 
                           fset=_set_destination,
                           doc="Destination of request")
     
    def _get_consent(self):
        '''Get the consent obtained from the principal for sending this 
        request
        
        @return: the consent obtained from the principal for sending this 
        request
        @rtype: basestring
        '''
        return self.__consent
        
    def _set_consent(self, value):
        '''Set the consent obtained from the principal for sending this 
        request
        
        @param value: the new consent obtained from the principal for 
        sending this request
        @type value: basestring
        @raise TypeError: incorrect input type
        ''' 
        if not isinstance(value, basestring):
            raise TypeError('Expecting basestring derived type for "consent", '
                            'got %r' % type(value))
        self.__consent = value
              
    consent = property(fget=_get_consent, 
                       fset=_set_consent,
                       doc="Consent for request")
   
    def _set_issuer(self, issuer):
        """Set issuer of request
        
        @param issuer: issuer of the request
        @type issuer: ndg.saml.saml2.coreIssuer
        @raise TypeError: incorrect input type
        """
        if not isinstance(issuer, Issuer):
            raise TypeError('"issuer" must be a %r, got %r' % (Issuer, 
                                                               type(issuer)))
        
        self.__issuer = issuer
    
    def _get_issuer(self):
        """Get the issuer name 
                
        @return: issuer of the request
        @rtype: ndg.saml.saml2.coreIssuer
        """
        return self.__issuer

    issuer = property(fget=_get_issuer, 
                      fset=_set_issuer,
                      doc="Issuer of request")
 
    def _get_extensions(self):
        '''Get the Extensions of this request
        
        @return: the Status of this request
        @rtype: iterable
        '''
        return self.__extensions
      
    def _set_extensions(self, value):
        '''Sets the Extensions of this request.
        
        @param value: the Extensions of this request
        @type value: iterable
        '''
        self.__extensions = value
        
    extensions = property(fget=_get_extensions, 
                          fset=_set_extensions,
                          doc="Request extensions")


class SubjectQuery(RequestAbstractType):
    """SAML 2.0 Core Subject Query type
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: XML element name for Subject Query
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    
    @ivar __subject: subject for this query
    @type __subject: ndg.saml.saml2.core.Subject 
    """
    
    DEFAULT_ELEMENT_LOCAL_NAME = 'SubjectQuery'
    
    __slots__ = ('__subject', )
    
    def __init__(self, **kw):
        '''Subject Query initialisation
        @type kw: dict
        @param kw: keywords to set attributes of superclasses
        '''
        super(SubjectQuery, self).__init__(**kw)
        self.__subject = None

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''

        _dict = super(SubjectQuery, self).__getstate__()
        for attrName in SubjectQuery.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_SubjectQuery" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
            
    def _getSubject(self):
        '''Gets the Subject of this request.
        
        @return: the Subject of this request
        @rtype: ndg.saml.saml2.core.Subject
        '''   
        return self.__subject
    
    def _setSubject(self, value):
        '''Sets the Subject of this request.
        
        @param value: the Subject of this request
        @type value: ndg.saml.saml2.core.Subject
        @raise TypeError: incorrect input type
        '''
        if not isinstance(value, Subject):
            raise TypeError('Setting "subject", got %r, expecting %r' %
                            (Subject, type(value)))
            
        self.__subject = value
        
    subject = property(fget=_getSubject, fset=_setSubject, doc="Query subject")
    
    
class AttributeQuery(SubjectQuery):
    '''SAML 2.0 AttributeQuery
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name.
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name.
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type.
    @type TYPE_NAME: ndg.saml.common.xml.QName

    @ivar __attributes: list of attributes for this query
    @type __attributes: TypedList
    '''
    
    # Element local name.
    DEFAULT_ELEMENT_LOCAL_NAME = "AttributeQuery"

    # Default element name.
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20P_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20P_PREFIX)

    # Local name of the XSI type.
    TYPE_LOCAL_NAME = "AttributeQueryType"

    # QName of the XSI type.
    TYPE_NAME = QName(SAMLConstants.SAML20P_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20P_PREFIX)

    __slots__ = ('__attributes',)
    
    def __init__(self, **kw):
        '''Attribute Query initialisation
        @type kw: dict
        @param kw: keywords to set attributes of superclasses
        '''
        super(AttributeQuery, self).__init__(**kw)
        self.__attributes = TypedList(Attribute)

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''

        _dict = super(AttributeQuery, self).__getstate__()
        for attrName in AttributeQuery.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_AttributeQuery" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
 
    def _getAttributes(self):
        '''Get the Attributes of this query
        
        @return: the list of Attributes of this query
        @rtype: ndg.saml.utils.TypedList'''
        return self.__attributes

    def _setAttributes(self, value):
        '''Set the attributes for this query
        
        @param value: new attributes for this query
        @type value: TypedList
        @raise TypeError: incorrect type for attributes list
        '''
        if isinstance(value, TypedList) and not issubclass(value.elementType, 
                                                           Attribute):
            raise TypeError('Expecting %r derived type for "attributes" '
                            'elements; got %r' % (Attribute, value.elementType))
        else:
            self.__attributes = TypedList(Attribute)
            for i in value:
                self.__attributes.append(i)
            
    attributes = property(fget=_getAttributes, 
                          fset=_setAttributes, 
                          doc="Attributes")


class Evidentiary(SAMLObject):
    """Base class for types set in an evidence object"""
    __slots__ = ()


class AssertionURIRef(Evidentiary):
    '''SAML 2.0 Core AssertionURIRef
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName

    @ivar __assertionURI: URI for this assertion reference
    @type __assertionURI: basestring
    '''
    __slots__ = ('__assertionURI',)
    
    # Element local name
    DEFAULT_ELEMENT_LOCAL_NAME = "AssertionURIRef"

    # Default element name
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20_PREFIX)
    
    def __init__(self, **kw):
        '''Create assertion URI reference
        
        @param kw: keywords to initialise superclasses
        @type kw: dict
        '''
        super(AssertionURIRef, self).__init__(**kw)
        
        # URI of the Assertion
        self.__assertionURI = None   

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''
        _dict = super(AssertionURIRef, self).__getstate__()
        for attrName in AssertionURIRef.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_AssertionURIRef" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
    
    def _getAssertionURI(self):
        '''Get assertion URI
        
        @return: assertion URI 
        @rtype: basestring
        '''
        return self.__assertionURI

    def _setAssertionURI(self, value):
        '''Set assertion URI
        
        @param value: assertion URI
        @type value: basestring
        @raise TypeError: incorrect input value type
        '''
        if not isinstance(value, basestring):
            raise TypeError('Expecting string type for "assertionID" '
                            'attribute; got %r' % type(value))
        self.__assertionURI = value

    def getOrderedChildren(self):
        """Return list of all attributes - not implemented for this class
        """

    assertionURI = property(_getAssertionURI, _setAssertionURI, 
                            doc="Assertion URI")
    
    
class AssertionIDRef(Evidentiary):
    '''SAML 2.0 Core AssertionIDRef.
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name.
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name.
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName

    @ivar __assertionID: assertion identifier
    @type __assertionID: basestring
    '''

    # Element local name.
    DEFAULT_ELEMENT_LOCAL_NAME = "AssertionIDRef"

    # Default element name.
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20_PREFIX)
    
    __slots__ = ("__assertionID",)
    
    def __init__(self, **kw):
        '''
        @param kw: keywords for superclass initialisation
        @type kw: dict
        '''
        super(AssertionIDRef, self).__init__(**kw)
        self.__assertionID = None

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''

        _dict = super(AssertionIDRef, self).__getstate__()
        for attrName in AssertionIDRef.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_AssertionIDRef" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
        
    def _getAssertionID(self):
        '''Get the ID of the assertion this references
        
        @return: the ID of the assertion this references
        @rtype: basestring
        '''
        return self.__assertionID
        
    def _setAssertionID(self, value):
        '''Sets the ID of the assertion this references.
        
        @param value: the ID of the assertion this references
        @type value: basestring
        @raise TypeError: incorrect type for input value
        '''
        if not isinstance(value, basestring):
            raise TypeError('Expecting string type for "assertionID" '
                            'attribute; got %r' % type(value))
        self.__assertionID = value

    def getOrderedChildren(self):
        '''Get attributes for this element as a list - not implemented for this
        class'''

    assertionID = property(_getAssertionID, _setAssertionID, 
                           doc="Assertion ID")
        
    
class EncryptedElementType(SAMLObject):
    '''SAML 2.0 Core EncryptedElementType
    
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type.
    @type TYPE_NAME: string

    '''
    
    # Local name of the XSI type.
    TYPE_LOCAL_NAME = "EncryptedElementType"
        
    # QName of the XSI type.
    TYPE_NAME = QName(SAMLConstants.SAML20_NS, 
                      TYPE_LOCAL_NAME, 
                      SAMLConstants.SAML20_PREFIX)
    
    __slots__ = ()
    
    def _getEncryptedData(self):
        '''Get the EncryptedData child element.  Not currently implemented
        
        @return: the EncryptedData child element'''
        raise NotImplementedError()
    
    def _setEncryptedData(self, value):
        '''Set the EncryptedData child element.  Not currently implemented
        
        @param value: the new EncryptedData child element'''
        raise NotImplementedError()
    
    def _getEncryptedKeys(self):
        '''A list of EncryptedKey child elements.  Not currently implemented
        
        @return: a list of EncryptedKey child elements'''
        raise NotImplementedError()
    
    
class EncryptedAssertion(EncryptedElementType, Evidentiary):
    '''SAML 2.0 Core EncryptedAssertion
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name.
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name.
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    '''
    
    # Element local name. 
    DEFAULT_ELEMENT_LOCAL_NAME = "EncryptedAssertion"

    # Default element name. 
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20_PREFIX) 
    __slots__ = ()
      
    
class Evidence(SAMLObject):
    '''SAML 2.0 Core Evidence
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name.
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name.
    @type DEFAULT_ELEMENT_NAME: ndg.saml.common.xml.QName
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type.
    @type TYPE_NAME: ndg.saml.common.xml.QName
    
    @ivar __values: list of evidence values
    @type __values: ndg.saml.utils.TypedList
    '''
    
    # Element local name.
    DEFAULT_ELEMENT_LOCAL_NAME = "Evidence"
    
    # Default element name.
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME, 
                                 SAMLConstants.SAML20_PREFIX)
    
    # Local name of the XSI type.
    TYPE_LOCAL_NAME = "EvidenceType" 
        
    # QName of the XSI type.
    TYPE_NAME = QName(SAMLConstants.SAML20_NS, 
                      TYPE_LOCAL_NAME, 
                      SAMLConstants.SAML20_PREFIX)

    __slots__ = ('__values',)
    
    def __init__(self, **kw):
        '''Create an authorization evidence type
        
        @param kw: keyword to initialise superclasses
        @type kw: dict
        '''
        super(Evidence, self).__init__(**kw)

        # Assertion of the Evidence. 
        self.__values = TypedList(Evidentiary) 

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''

        _dict = super(Evidence, self).__getstate__()
        for attrName in Evidence.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_Evidence" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict   
         
    @property
    def assertionIDReferences(self):
        '''Get the list of Assertion ID references used as evidence
    
        @return: the list of AssertionID references used as evidence
        @rtype: list
        '''
        return [i for i in self.__values 
                if (getattr(i, "DEFAULT_ELEMENT_NAME") == 
                    AssertionIDRef.DEFAULT_ELEMENT_NAME)]
    
    @property
    def assertionURIReferences(self):
        '''Get the list of Assertion URI references used as evidence
       
        @return: the list of AssertionURI references used as evidence
        @rtype: list'''
        return [i for i in self.__values 
                if (getattr(i, "DEFAULT_ELEMENT_NAME") == 
                    AssertionURIRef.DEFAULT_ELEMENT_NAME)]
    
    @property
    def assertions(self):
        '''Get the list of Assertions used as evidence
       
        @return: the list of Assertions used as evidence
        @rtype: list
        '''
        return [i for i in self.__values 
                if (getattr(i, "DEFAULT_ELEMENT_NAME") == 
                    Assertion.DEFAULT_ELEMENT_NAME)]
    
    @property
    def encryptedAssertions(self):
        '''Gets the list of EncryptedAssertions used as evidence.
       
        @return: the list of EncryptedAssertions used as evidence
        @rtype: list
        '''
        return [i for i in self.__values 
                if (getattr(i, "DEFAULT_ELEMENT_NAME") == 
                    EncryptedAssertion.DEFAULT_ELEMENT_NAME)]   

    @property
    def values(self):
        '''Get the list of all elements used as evidence.
       
        @return: the list of Evidentiary objects used as evidence
        @rtype: ndg.saml.utils.TypedList
        '''
        return self.__values
    
    def getOrderedChildren(self):
        '''Return list of evidence objects
        '''
        children = []

        if len(self.__values) == 0:
            return None

        children.extend(self.__values)

        return tuple(children)
    

class AuthzDecisionQuery(SubjectQuery):
    '''SAML 2.0 AuthzDecisionQuery
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name.
    @type DEFAULT_ELEMENT_LOCAL_NAME: string
    @cvar DEFAULT_ELEMENT_NAME: Default element name.
    @type DEFAULT_ELEMENT_NAME: string
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type.
    @type TYPE_NAME: string
    @cvar RESOURCE_ATTRIB_NAME: Resource attribute name.
    @type RESOURCE_ATTRIB_NAME: string
   
    @ivar resource: Resource attribute value.
    @type resource: string
    @ivar evidence: Evidence child element.
    @type evidence: string
    @ivar actions: Action child elements.
    @type actions: string
    @ivar normalizeResource: Set to Truefor normalization of resource URIs in 
    property set method
    @type normalizeResource: bool
    @ivar safeNormalizationChars: safe character settings for normalisation
    @type safeNormalizationChars: string
    '''

    # Element local name.
    DEFAULT_ELEMENT_LOCAL_NAME = "AuthzDecisionQuery"

    # Default element name.
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20P_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME,
                                 SAMLConstants.SAML20P_PREFIX)

    # Local name of the XSI type.
    TYPE_LOCAL_NAME = "AuthzDecisionQueryType"

    # QName of the XSI type.
    TYPE_NAME = QName(SAMLConstants.SAML20P_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20P_PREFIX)

    # Resource attribute name.
    RESOURCE_ATTRIB_NAME = "Resource"
    
    __slots__ = (
       '__resource',
       '__evidence',
       '__actions',
       '__normalizeResource',
       '__safeNormalizationChars'
    )
    
    def __init__(self, normalizeResource=True, safeNormalizationChars='/%'):
        '''Create new authorisation decision query
        '''
        super(AuthzDecisionQuery, self).__init__()

        # Resource attribute value. 
        self.__resource = None
    
        # Evidence child element.
        self.__evidence = None
    
        # Action child elements.
        self.__actions = TypedList(Action)   
        
        # Tuning for normalization of resource URIs in property set method
        self.normalizeResource = normalizeResource
        self.safeNormalizationChars = safeNormalizationChars

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''

        _dict = super(AuthzDecisionQuery, self).__getstate__()
        for attrName in AuthzDecisionQuery.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_AuthzDecisionQuery" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
    
    def _getNormalizeResource(self):
        '''
        @return: flag to set whether to apply normalisation of resource URI or 
        not
        @rtype: bool
        '''
        return self.__normalizeResource

    def _setNormalizeResource(self, value):
        '''
        @param value: flag to set whether to apply normalisation of resource URI 
        or not
        @type value: bool
        @raise TypeError: incorrect type for input value
        '''
        if not isinstance(value, bool):
            raise TypeError('Expecting bool type for "normalizeResource" '
                            'attribute; got %r instead' % type(value))
            
        self.__normalizeResource = value

    normalizeResource = property(_getNormalizeResource, 
                                 _setNormalizeResource, 
                                 doc="Flag to normalize new resource value "
                                     "assigned to the \"resource\" property.  "
                                     "The setting only applies for URIs "
                                     'beginning with "http://" or "https://"')

    def _getSafeNormalizationChars(self):
        '''
        @return: safe normalisation characters for input into normalisation
        of resource URI.
        @rtype: string
        '''
        return self.__safeNormalizationChars

    def _setSafeNormalizationChars(self, value):
        '''
        @param value: safe normalisation characters for input into normalisation
        of resource URI.  It only applies if normalizeResource is set to True
        @type value: string
        @raise TypeError: incorrect type for input value
        '''
        if not isinstance(value, basestring):
            raise TypeError('Expecting string type for "normalizeResource" '
                            'attribute; got %r instead' % type(value))
            
        self.__safeNormalizationChars = value

    safeNormalizationChars = property(_getSafeNormalizationChars, 
                                      _setSafeNormalizationChars, 
                                      doc="String containing a list of "
                                          "characters that should not be "
                                          "converted when Normalizing the "
                                          "resource URI.  These are passed to "
                                          "urllib.quote when the resource "
                                          "property is set.  The default "
                                          "characters are '/%'")

    def _getResource(self):
        '''Get the Resource attrib value of this query

        @return: the Resource attrib value of this query
        @rtype: basestring
        '''
        return self.__resource
    
    def _setResource(self, value):
        '''Sets the Resource attrib value of this query.
        
        If normalizeResource attribute is True, the path is normalized
        removing spurious port numbers (80 for HTTP and 443 for HTTPS) and 
        converting the host component to lower case.
        
        @param value: the new Resource attrib value of this query
        @type value: basestring
        @raise TypeError: if incorrect input type 
        '''
        if not isinstance(value, basestring):
            raise TypeError('Expecting string type for "resource" attribute; '
                            'got %r instead' % type(value))
        
        if (self.normalizeResource and 
            value.startswith('http://') or value.startswith('https://')):
            # Normalise the path, set the host name to lower case and remove 
            # port redundant numbers 80 and 443
            splitResult = urlsplit(value)
            uriComponents = list(splitResult)
            
            # hostname attribute is lowercase
            uriComponents[1] = splitResult.hostname
            
            if splitResult.port is not None:
                isHttpWithStdPort = (splitResult.port == 80 and 
                                     splitResult.scheme == 'http')
                
                isHttpsWithStdPort = (splitResult.port == 443 and
                                      splitResult.scheme == 'https')
                
                if not isHttpWithStdPort and not isHttpsWithStdPort:
                    uriComponents[1] += ":%d" % splitResult.port
            
            uriComponents[2] = urllib.quote(splitResult.path, 
                                            self.safeNormalizationChars)
            
            self.__resource = urlunsplit(uriComponents)
        else:
            self.__resource = value
    
    resource = property(fget=_getResource, fset=_setResource,
                        doc="Resource for which authorisation is requested")
    
    @property
    def actions(self):
        '''The actions for which authorisation is requested
        
        @return: the Actions of this query
        @rtype: ndg.saml.utils.TypedList
        '''
        return self.__actions
   
    def _getEvidence(self):
        '''Get the Evidence of this query

        @return: the Evidence of this query
        @rtype: ndg.saml.saml2.core.Evidence or NoneType
        '''
        return self.__evidence

    def _setEvidence(self, value):
        '''Set the Evidence of this query
        
        @param value: the new Evidence of this query
        @type value: ndg.saml.saml2.core.Evidence
        @raise TypeError: incorrect input type
        '''  
        if not isinstance(value, Evidence):
            raise TypeError('Expecting Evidence type for "evidence" '
                            'attribute; got %r' % type(value))

        self.__evidence = value  

    evidence = property(fget=_getEvidence, fset=_setEvidence, 
                        doc="A set of assertions which the Authority may use "
                            "to base its authorisation decision on")
    
    def getOrderedChildren(self):
        '''Return attributes for this element as a tuple
        
        @return: attributes for this element
        @rtype: tuple
        '''
        children = []

        superChildren = super(AuthzDecisionQuery, self).getOrderedChildren()
        if superChildren:
            children.extend(superChildren)

        children.extend(self.__actions)
        
        if self.__evidence is not None:
            children.extend(self.__evidence)

        if len(children) == 0:
            return None

        return tuple(children)


class StatusResponseType(SAMLObject):
    '''SAML 2.0 Core Status Response Type

    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type.
    @type TYPE_NAME: ndg.saml.common.xml.QName
    @cvar ID_ATTRIB_NAME: ID attribute name
    @type ID_ATTRIB_NAME: string
    @cvar IN_RESPONSE_TO_ATTRIB_NAME: InResponseTo attribute name
    @type IN_RESPONSE_TO_ATTRIB_NAME: string
    @cvar VERSION_ATTRIB_NAME: Version attribute name
    @type VERSION_ATTRIB_NAME: string
    @cvar ISSUE_INSTANT_ATTRIB_NAME: IssueInstant attribute name
    @type ISSUE_INSTANT_ATTRIB_NAME: string
    @cvar DESTINATION_ATTRIB_NAME: Destination attribute name
    @type DESTINATION_ATTRIB_NAME: string
    @cvar CONSENT_ATTRIB_NAME: Consent attribute name.
    @type CONSENT_ATTRIB_NAME: string
    @cvar UNSPECIFIED_CONSENT: Unspecified consent URI
    @type UNSPECIFIED_CONSENT: string
    @cvar OBTAINED_CONSENT: Obtained consent URI
    @type OBTAINED_CONSENT: string
    @cvar PRIOR_CONSENT: Prior consent URI
    @type PRIOR_CONSENT: string
    @cvar IMPLICIT_CONSENT: Implicit consent URI
    @type IMPLICIT_CONSENT: string
    @cvar EXPLICIT_CONSENT: Explicit consent URI
    @type EXPLICIT_CONSENT: string
    @cvar UNAVAILABLE_CONSENT: Unavailable consent URI
    @type UNAVAILABLE_CONSENT: string
    @cvar INAPPLICABLE_CONSENT: Inapplicable consent URI
    @type INAPPLICABLE_CONSENT: string

    @ivar __version: SAML version
    @type __version: string
    @ivar __id: response identifier
    @type __id: string
    @ivar __inResponseTo: identifier corresponding to the query this response is
    responding to
    @type __inResponseTo: string
    @ivar __issueInstant: issue instant for the response
    @type __issueInstant: datetime.datetime
    @ivar __destination: destination for the response
    @type __destination: string
    @ivar __consent: consent information
    @type __consent: string
    @ivar __issuer: issuer identifier
    @type __issuer: ndg.saml.saml2.core.Issuer
    @ivar __status: status of the response
    @type __status: ndg.saml.saml2.core.Status
    @ivar __extensions: response extensions
    @type __extensions: list or tuple
    '''

    # Local name of the XSI type.
    TYPE_LOCAL_NAME = "StatusResponseType"

    # QName of the XSI type.
    TYPE_NAME = QName(SAMLConstants.SAML20P_NS, 
                      TYPE_LOCAL_NAME,
                      SAMLConstants.SAML20P_PREFIX)

    # ID attribute name
    ID_ATTRIB_NAME = "ID"

    # InResponseTo attribute name
    IN_RESPONSE_TO_ATTRIB_NAME = "InResponseTo"

    # Version attribute name
    VERSION_ATTRIB_NAME = "Version"

    # IssueInstant attribute name
    ISSUE_INSTANT_ATTRIB_NAME = "IssueInstant"

    # Destination attribute name
    DESTINATION_ATTRIB_NAME = "Destination"

    # Consent attribute name.
    CONSENT_ATTRIB_NAME = "Consent"

    # Unspecified consent URI
    UNSPECIFIED_CONSENT = "urn:oasis:names:tc:SAML:2.0:consent:unspecified"

    # Obtained consent URI
    OBTAINED_CONSENT = "urn:oasis:names:tc:SAML:2.0:consent:obtained"

    # Prior consent URI
    PRIOR_CONSENT = "urn:oasis:names:tc:SAML:2.0:consent:prior"

    # Implicit consent URI
    IMPLICIT_CONSENT = "urn:oasis:names:tc:SAML:2.0:consent:implicit"

    # Explicit consent URI
    EXPLICIT_CONSENT = "urn:oasis:names:tc:SAML:2.0:consent:explicit"

    # Unavailable consent URI
    UNAVAILABLE_CONSENT = "urn:oasis:names:tc:SAML:2.0:consent:unavailable"

    # Inapplicable consent URI
    INAPPLICABLE_CONSENT = "urn:oasis:names:tc:SAML:2.0:consent:inapplicable"

    __slots__ = (    
        '__version',
        '__id',
        '__inResponseTo',
        '__issueInstant',
        '__destination',
        '__consent',
        '__issuer',
        '__status',
        '__extensions'                
    )
    
    def __init__(self, **kw):
        '''
        @param kw: keywords for initialisation of superclass
        @type kw: dict
        '''
        super(StatusResponseType, self).__init__(**kw)
        
        self.__version = SAMLVersion(SAMLVersion.VERSION_20)
        self.__id = None
        self.__inResponseTo = None
        self.__issueInstant = None
        self.__destination = None
        self.__consent = None
        self.__issuer = None
        self.__status = None
        self.__extensions = None

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''

        _dict = super(StatusResponseType, self).__getstate__()
        for attrName in StatusResponseType.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_StatusResponseType" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
    
    def _get_version(self):
        '''@return: the SAML Version of this response
        @rtype: string
        '''
        return self.__version
    
    def _set_version(self, version):
        '''@param version: the SAML Version of this response
        @type version: basestring
        @raise TypeError: incorrect type for input version 
        '''
        if not isinstance(version, SAMLVersion):
            raise TypeError("Expecting SAMLVersion type got: %r" % 
                            version.__class__)
        
        self.__version = version
       
    version = property(fget=_get_version,
                       fset=_set_version,
                       doc="SAML Version of the response")

    def _get_id(self):
        '''Sets the ID of this response.
        
        @return: the ID of this response
        @rtype: basestring
        '''
        return self.__id
    
    def _set_id(self, value):
        '''Sets the ID of this response.
        
        @param value: the ID of this response
        @type value: basestring
        @raise TypeError: incorrect type for input value
        '''
        if not isinstance(value, basestring):
            raise TypeError('Expecting basestring derived type for "id", got '
                            '%r' % type(value))
        self.__id = value
        
    id = property(fget=_get_id, fset=_set_id, doc="ID of response")

    def _getInResponseTo(self):
        '''Get the unique request identifier for which this is a response
        
        @return: the unique identifier of the originating 
        request
        @rtype: basestring
        '''
        return self.__inResponseTo
    
    def _setInResponseTo(self, value):
        '''Set the unique request identifier for which this is a response
        
        @param value: the unique identifier of the originating 
        request
        @type value: basestring
        @raise TypeError: incorrect type for input value
        '''
        if not isinstance(value, basestring):
            raise TypeError('Expecting basestring derived type for '
                            '"inResponseTo", got %r' % type(value))
        self.__inResponseTo = value
        
    inResponseTo = property(fget=_getInResponseTo, 
                            fset=_setInResponseTo,
                            doc="unique request identifier for which this is "
                                "a response")

    def _get_issueInstant(self):
        '''Gets the issue instant of this response.
        
        @return: the issue instant of this response
        @rtype: datetime.datetime'''
        return self.__issueInstant
    
    def _set_issueInstant(self, issueInstant):
        '''Set the issue instant of this response
        
        @param issueInstant: the issue instance of this response
        @type issueInstant: datetime.datetime
        @raise TypeError: incorrect type for input value
        '''
        if not isinstance(issueInstant, datetime):
            raise TypeError('Expecting "datetime" type for "issueInstant", '
                            'got %r' % issueInstant.__class__)
            
        self.__issueInstant = issueInstant
        
    issueInstant = property(fget=_get_issueInstant, 
                            fset=_set_issueInstant,
                            doc="Issue instant of the response")

    def _get_destination(self):
        '''Gets the URI of the destination of the response.
        
        @return: the URI of the destination of the response
        @rtype: basestring
        '''
        return self.__destination
    
    def _set_destination(self, value):
        '''Sets the URI of the destination of the response.
        
        @param value: the URI of the destination of the response
        @type value: basestring
        @raise TypeError: incorrect type for input value
        '''
        if not isinstance(value, basestring):
            raise TypeError('Expecting basestring derived type for '
                            '"destination", got %r' % type(value))
        self.__destination = value
        
    destination = property(fget=_get_destination, 
                           fset=_set_destination,
                           doc="Destination of response")
     
    def _get_consent(self):
        '''Get the consent obtained from the principal for sending this 
        response
        
        @return: the consent obtained from the principal for sending this 
        response
        @rtype: basestring
        '''
        return self.__consent
        
    def _set_consent(self, value):
        '''Sets the consent obtained from the principal for sending this 
        response.
        
        @param value: the new consent obtained from the principal for 
        sending this response
        @type value: basestring
        @raise TypeError: incorrect type for input value
        ''' 
        if not isinstance(value, basestring):
            raise TypeError('Expecting basestring derived type for "consent", '
                            'got %r' % type(value))
        self.__consent = value
              
    consent = property(fget=_get_consent, 
                       fset=_set_consent,
                       doc="Consent for response")
   
    def _set_issuer(self, issuer):
        """Set issuer of response
        
        @param issuer: issuer of this response 
        sending this response
        @type issuer: ndg.saml.saml2.core.Issuer
        @raise TypeError: incorrect type for input value
        """
        if not isinstance(issuer, Issuer):
            raise TypeError('"issuer" must be a %r, got %r' % (Issuer,
                                                               type(issuer)))
        self.__issuer = issuer
    
    def _get_issuer(self):
        """Get the issuer name 
        
        @return: issuer of this response 
        sending this response
        @rtype: ndg.saml.saml2.core.Issuer
        """
        return self.__issuer

    issuer = property(fget=_get_issuer, 
                      fset=_set_issuer,
                      doc="Issuer of response")
    
    def _getStatus(self):
        '''Gets the Status of this response.
        
        @return: the Status of this response
        @rtype: ndg.saml.saml2.core.Status
        '''
        return self.__status

    def _setStatus(self, value):
        '''Sets the Status of this response.
        
        @param value: the Status of this response
        @type value: ndg.saml.saml2.core.Status
        @raise TypeError: incorrect type for input value
        '''
        if not isinstance(value, Status):
            raise TypeError('"status" must be a %r, got %r' % (Status,
                                                               type(value)))
        self.__status = value
        
    status = property(fget=_getStatus, fset=_setStatus, doc="Response status")    
        
    def _get_extensions(self):
        '''Gets the Extensions of this response.
        
        @return: the Status of this response
        @rtype: tuple/list/NoneType
        '''
        return self.__extensions
      
    def _set_extensions(self, value):
        '''Sets the Extensions of this response.
        
        @param value: the Extensions of this response
        @type value: tuple or list
        @raise TypeError: incorrect type for input value        
        '''
        if not isinstance(value, (list, tuple)):
            raise TypeError('Expecting list or tuple for "extensions", got %r'
                            % type(value))
        self.__extensions = value
        
    extensions = property(fget=_get_extensions, 
                          fset=_set_extensions,
                          doc="Response extensions")    


class Response(StatusResponseType):
    '''SAML2 Core Response
    
    @cvar DEFAULT_ELEMENT_LOCAL_NAME: Element local name.
    @type DEFAULT_ELEMENT_LOCAL_NAME: ndg.saml.common.xml.QName
    @cvar DEFAULT_ELEMENT_NAME: Default element name.
    @type DEFAULT_ELEMENT_NAME: string
    @cvar TYPE_LOCAL_NAME: Local name of the XSI type.
    @type TYPE_LOCAL_NAME: string
    @cvar TYPE_NAME: QName of the XSI type.
    @type TYPE_NAME: ndg.saml.common.xml.QName
    
    @ivar __indexedChildren: response elements
    @type __indexedChildren: list
    '''
    
    # Element local name.
    DEFAULT_ELEMENT_LOCAL_NAME = "Response"
    
    # Default element name.
    DEFAULT_ELEMENT_NAME = QName(SAMLConstants.SAML20P_NS, 
                                 DEFAULT_ELEMENT_LOCAL_NAME, 
                                 SAMLConstants.SAML20P_PREFIX)
    
    # Local name of the XSI type.
    TYPE_LOCAL_NAME = "ResponseType"
        
    # QName of the XSI type.
    TYPE_NAME = QName(SAMLConstants.SAML20P_NS, 
                      TYPE_LOCAL_NAME, 
                      SAMLConstants.SAML20P_PREFIX)
    
    __slots__ = ('__indexedChildren',)
    
    def __init__(self, **kw):
        '''
        @param kw: keywords to initialise superclass instance
        @type kw: dict
        ''' 
        super(Response, self).__init__(**kw)
        
        # Assertion child elements
        self.__indexedChildren = []

    def __getstate__(self):
        '''Enable pickling
        
        @return: object's attribute dictionary
        @rtype: dict
        '''

        _dict = super(Response, self).__getstate__()
        for attrName in Response.__slots__:
            # Ugly hack to allow for derived classes setting private member
            # variables
            if attrName.startswith('__'):
                attrName = "_Response" + attrName
                
            _dict[attrName] = getattr(self, attrName)
            
        return _dict
        
    @property
    def assertions(self): 
        """Assertions contained in this response
        
        @return: list of assertion for this response
        @rtype: list
        """
        return self.__indexedChildren
