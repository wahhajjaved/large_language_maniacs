# Copyright (c) 2014, The MITRE Corporation. All rights reserved.
# See LICENSE.txt for complete terms.

import stix
from itertools import izip
from distutils.version import StrictVersion
from lxml import etree

class UnsupportedVersionError(Exception):
    pass

class UnknownVersionError(Exception):
    pass

class UnsupportedRootElement(Exception):
    pass

class EntityParser(object):
    def __init__(self):
        pass

    def _check_version(self, tree):
        '''Returns true of the instance document @tree is a version supported by python-stix'''

        try:
            root = tree.getroot() # is tree an lxml.Element or lxml.ElementTree
        except AttributeError:
            root = tree

        if not root.attrib.get('version'):
            raise UnknownVersionError("No version attribute set on xml instance. Unable to determine version compatibility")

        python_stix_version = stix.__version__ # ex: '1.1.0.0'
        supported_stix_version = python_stix_version[:-2] # ex: '1.1.0'
        document_version = root.attrib['version']

        if StrictVersion(supported_stix_version) != StrictVersion(document_version):
            raise UnsupportedVersionError("Your python-stix library supports STIX %s. Document version was %s" % (supported_stix_version, document_version))

        return True

    def _check_root(self, tree):
        try:
            root = tree.getroot() # is tree an lxml.Element or lxml.ElementTree
        except AttributeError:
            root = tree

        if root.tag != "{http://stix.mitre.org/stix-1}STIX_Package":
            raise UnsupportedRootElement("Document root element must be an instance of STIX_Package")

        return True

    def _apply_input_namespaces(self, tree, entity):
        try:
            root = tree.getroot() # is tree an lxml.Element or lxml.ElementTree
        except AttributeError:
            root = tree
        
        entity.__input_namespaces__ = {}
        for alias, ns in root.nsmap.iteritems():
            entity.__input_namespaces__[ns] = alias

    def _apply_input_schemalocations(self, tree, entity):
        """
        Attaches an __input_schemalocations__ dictionary to the input entity.

        :param tree: The input etree instance
        :param entity: The entity to attach the schemlocation dictionary to
        """
        try:
            root = tree.getroot() # is tree an lxml.Element or lxml.ElementTree
        except AttributeError:
            root = tree

        schemaloc_attrib_name = \
            '{http://www.w3.org/2001/XMLSchema-instance}schemaLocation'
        if root.attrib.get(schemaloc_attrib_name):
            schemalocs = root.attrib[schemaloc_attrib_name].split()
            pairs = izip(schemalocs[::2], schemalocs[1::2])
            entity.__input_schemalocations__ = dict(pairs)


    def parse_xmlto_obj(self, xml_file, check_version=True, check_root=True):
        """Creates a STIX binding object from the supplied xml file.

        Arguments:
        xml_file -- A filename/path or a file-like object reprenting a STIX instance document
        check_version -- Inspect the version before parsing.
        check_root -- Inspect the root element before parsing.

        """
        parser = etree.ETCompatXMLParser(huge_tree=True)
        tree = etree.parse(xml_file, parser=parser)

        if check_version:
            self._check_version(tree)

        if check_root:
            self._check_root(tree)

        import stix.bindings.stix_core as stix_core_binding 
        stix_package_obj = stix_core_binding.STIXType().factory()
        stix_package_obj.build(tree.getroot())

        return stix_package_obj

    def parse_xml(self, xml_file, check_version=True, check_root=True):
        """Creates a python-stix STIXPackage object from the supplied xml_file.

        Arguments:
        xml_file -- A filename/path or a file-like object reprenting a STIX instance document
        check_version -- Inspect the version before parsing.
        check_root -- Inspect the root element before parsing.

        """
        parser = etree.ETCompatXMLParser(huge_tree=True)
        tree = etree.parse(xml_file, parser=parser)

        if check_version:
            self._check_version(tree)

        if check_root:
            self._check_root(tree)

        import stix.bindings.stix_core as stix_core_binding 
        stix_package_obj = stix_core_binding.STIXType().factory()
        stix_package_obj.build(tree.getroot())
        
        from stix.core import STIXPackage # resolve circular dependencies
        stix_package = STIXPackage().from_obj(stix_package_obj)
        self._apply_input_namespaces(tree, stix_package)
        self._apply_input_schemalocations(tree, stix_package)
        
        return stix_package
