# -*- coding: utf-8 -*-
#
# Poio Tools for Linguists
#
# Copyright (C) 2009-2013 Poio Project
# Author: António Lopes <alopes@cidles.eu>
# URL: <http://media.cidles.eu/poio/>
# For license information, see LICENSE.TXT

"""This module contains classes to access Elan data.
The class Eaf is a low level API to .eaf files.

EafGlossTree, EafPosTree, etc. are the classes to
access the data via tree, which also contains the
original .eaf IDs. Because of this EafTrees are
read-/writeable.
"""

from __future__ import absolute_import

import xml.etree.ElementTree as ET

from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

import poioapi.io.graf

class ElanTier(poioapi.io.graf.Tier):
    __slots__ = ["linguistic_type"]

    def __init__(self, name, linguistic_type):
        self.name = name
        self.linguistic_type = linguistic_type
        self.annotation_space = linguistic_type


class Parser(poioapi.io.graf.BaseParser):
    """
    Class that will handle parse Elan files.

    """

    def __init__(self, filepath):
        """Class's constructor.

        Parameters
        ----------
        filepath : str
            Path of the elan file.

        """

        self.filepath = filepath

        self.parse()

    def parse(self):
        """This method will set the variables
        to make possible to do the parsing
        correctly.

        """

        self.root = ET.parse(self.filepath)
        self.tree = self.root.getroot()
        self.regions_map = self._map_time_slots()
        self.meta_information = self._retrieve_aditional_information()

    def get_root_tiers(self):
        """This method retrieves all the root tiers.
        In this case the root tiers are all those
        that doesn't contain "PARENT_REF".

        Returns
        -------
        list : array-like
            List of tiers type.

        """

        return [ElanTier(tier.attrib['TIER_ID'], tier.attrib['LINGUISTIC_TYPE_REF'])
                for tier in self.tree.findall('TIER')
                if not 'PARENT_REF' in tier.attrib]

    def get_child_tiers_for_tier(self, tier):
        """This method retrieves all the child tiers
        of a specific tier. The children of a tier
        are all the "TIERS" that has the "PARENT_REF"
        equal to the specific tier name.

        Parameters
        ----------
        tier : object
            Tier to find the children from.

        Returns
        -------
        child_tiers : array-like
            List of tiers type.

        """

        child_tiers = []

        for t in self.tree.findall("TIER"):
            if "PARENT_REF" in t.attrib and t.attrib["PARENT_REF"] == tier.name:
                child_tiers.append(ElanTier(t.attrib['TIER_ID'],
                    t.attrib['LINGUISTIC_TYPE_REF']))

        return child_tiers

    def get_annotations_for_tier(self, tier, annotation_parent=None):
        """This method retrieves all the annotations
        of a specific tier. In elan type files there
        are two different types of annotations,
        ANNOTATION_REF and ALIGNABLE_ANNOTATION. For
        the ANNOTATION_REF the annotation_parent it's
        specified in the attribute "ANNOTATION_REF".
        As for the ALIGNABLE_ANNOTATION in order to
        use the annotation_parent it's necessary to
        try to match if the ranges of theirs
        "TIME_SLOT_REF".

        Parameters
        ----------
        tier : object
            Tier to find the annotations.
        annotation_parent : object
            Annotation parent it is the reference.

        Returns
        -------
        annotations : array-like
            List of annotations type.

        """

        annotations = []
        tier_annotations = []

        for t in self.tree.findall("TIER"):
            if t.attrib["TIER_ID"] == tier.name:
                if annotation_parent is not None and self.tier_has_regions(tier) == False:
                    for a in t.findall("ANNOTATION/*"):
                        if a.attrib["ANNOTATION_REF"] == annotation_parent.id:
                            tier_annotations.append(a)
                    break
                else:
                    tier_annotations = t.findall("ANNOTATION/*")
                    break

        for annotation in tier_annotations:
            annotation_id = annotation.attrib['ANNOTATION_ID']
            annotation_value = annotation.find('ANNOTATION_VALUE').text

            if annotation.tag == "ALIGNABLE_ANNOTATION":
                if annotation_parent is None:
                    features = {'time_slot1': annotation.attrib['TIME_SLOT_REF1'],
                                'time_slot2': annotation.attrib['TIME_SLOT_REF2']}
                elif self._find_ranges_in_annotation_parent(annotation_parent, annotation):
                    features = {'time_slot1': annotation.attrib['TIME_SLOT_REF1'],
                                'time_slot2': annotation.attrib['TIME_SLOT_REF2']}
                else:
                    continue
            else:
                annotation_ref = annotation.attrib['ANNOTATION_REF']

                features = {'ref_annotation': annotation_ref,
                            'tier_id': tier.name}

                for attribute in annotation.attrib:
                    if attribute != 'ANNOTATION_REF' and attribute != 'ANNOTATION_ID' and\
                       attribute != 'ANNOTATION_VALUE':
                        features[attribute] = annotation.attrib[attribute]

            annotations.append(poioapi.io.graf.Annotation(annotation_id, annotation_value, features))

        return annotations

    def _find_ranges_in_annotation_parent(self, annotation_parent, annotation):
        if annotation_parent is not None:
            annotation_parent_regions = self.region_for_annotation(annotation_parent)

            annotation_regions = [int(self.regions_map[annotation.attrib['TIME_SLOT_REF1']]),
                                  int(self.regions_map[annotation.attrib['TIME_SLOT_REF2']])]

            if annotation_parent_regions[0] <= annotation_regions[0]\
            and annotation_regions[1] <= annotation_parent_regions[1]:
                return True

        return False

    def region_for_annotation(self, annotation):
        """This method retrieves the region for a
        specific annotation. The region are obtained
        through the time slots references.

        Parameters
        ----------
        annotation : object
            Annotation to get the region.

        Returns
        -------
        region : tuple
            Region of an annotation.

        """

        if 'time_slot1' in annotation.features:
            part_1 = int(self.regions_map[annotation.features['time_slot1']])
            part_2 = int(self.regions_map[annotation.features['time_slot2']])

            region = (part_1, part_2)

            return region

        return None

    def tier_has_regions(self, tier):
        """This method check if a tier has regions.
        The tiers that are considerate with regions
        are the ones that theirs "LINGUISTIC_TYPE"
        is "TIME_ALIGNABLE" true.

        Parameters
        ----------
        tier : object
            Tier to check if has regions.

        Returns
        -------
        boolean : bool
            Result of the TIME_ALIGNABLE check.

        """

        for l in self.tree.findall("LINGUISTIC_TYPE"):
            if l.attrib["LINGUISTIC_TYPE_ID"] == tier.linguistic_type:
                if l.attrib['TIME_ALIGNABLE'] == 'true':
                    return True

        return False

    def _map_time_slots(self):
        """This method map "TIME_SLOT_ID"s with
        their respective values.

        Returns
        -------
        time_order_dict : dict
            A dictonary with the time slot's and their values.

        See also
        --------
        _fix_time_slots

        """

        time_order = self.tree.find('TIME_ORDER')
        time_order_dict = dict()

        for time in time_order:
            key = time.attrib['TIME_SLOT_ID']

            if 'TIME_VALUE' in time.attrib:
                value = time.attrib['TIME_VALUE']
            else:
                value = None

            time_order_dict[key] = value

        time_order_dict = self._fix_time_slots(time_order_dict)

        return time_order_dict

    def _fix_time_slots(self, time_order_dict):
        """Helper function that fix some of the missing
        values in the time slots. Some of the "TIME_SLOT_ID"
        doesn't contain the "TIME_VALUE" since this
        attribute is optional.

        Parameters
        ----------
        time_order_dict : dict
            A dictonary with the time slot's and their values.

        Returns
        -------
        time_order_dict : dict
            A dictonary with the time slot's and their values.

        See also
        --------
        _find_time_slot_value

        """

        for time_slot, value in time_order_dict.items():
            if value is None:
                time_order_dict[time_slot] = self._find_time_slot_value(time_slot,
                    time_order_dict)

        return time_order_dict

    def _find_time_slot_value(self, time_slot, time_order_dict):
        """Helper function to find and calculate the missing
        time value. The calculation is made base in the range
        where the time slot is used. The First it's obtain the
        range values then is made a summation of that values
        and divide by the number of values. In the end it's
        a mean count.

        Parameters
        ----------
        time_slot : str
            Id of a "TIME_ORDER".
        time_order_dict : dict
            A dictonary with the time slot's and their values.

        Returns
        -------
        time_slot_value : int
            Time value of a specific time slot.

        """

        tiers = self.tree.findall('TIER')
        range_time_slots = []

        for tier in tiers:
            annotations = tier.findall('ANNOTATION')
            for annotation in annotations:
                if annotation[0].tag == 'ALIGNABLE_ANNOTATION':
                    if annotation[0].attrib['TIME_SLOT_REF1'] == time_slot:
                        range_time_slots.append(annotation[0].attrib['TIME_SLOT_REF2'])
                    if annotation[0].attrib['TIME_SLOT_REF2'] == time_slot:
                        range_time_slots.append(annotation[0].attrib['TIME_SLOT_REF1'])

        time_slot_value = 0

        for time_slot in range_time_slots:
            time_slot_value += int(time_order_dict[time_slot])

        time_slot_value = (time_slot_value / len(range_time_slots))

        return time_slot_value

    def _retrieve_aditional_information(self):
        """This method retrieve all the elan
        core file, except the ANNOTATION tags,
        to make it possible to reconstruct the
        elan file again.

        Returns
        -------
        meta_information : ElementTree
            Element with all the elan elements except the Tiers
            annotations.

        """

        meta_information = Element(self.root._root.tag,
            self.root._root.attrib)

        for element in self.tree:
            if element.tag != 'ANNOTATION_DOCUMENT':
                if element.tag == 'TIER':
                    meta_information.append(Element(element.tag,
                        element.attrib))
                else:
                    parent_element = SubElement(meta_information,
                        element.tag, element.attrib)
                    for child in element:
                        other_chid = SubElement(parent_element,
                            child.tag, child.attrib)
                        if not str(child.text).isspace() or\
                           child.text is not None:
                            other_chid.text = child.text

        return meta_information


class Writer:
    """
    Class that will handle the writing of
    GrAF files into Elan files again.

    """

    def write(self, outputfile, graf_graph, tier_hierarchies, meta_information):
        """Write the GrAF object into a Elan file.

        Parameters
        ----------
        outputfile : str
            The filename of the output file. The filename should have
            the Elan extension ".eaf".
        graf_graph : obejct
            A GrAF object.
        tier_hierarchies : array_like
            Array with all the tier hierarchies from the GrAF.
        meta_information : ElementTree
            Element tree contains all the information in Elan file
            besides the Tiers annotations.

        """

        for tier in self._flatten_hierarchy_elements(tier_hierarchies):
            tier_name = tier.split('/')[-1]

            for et in meta_information.findall("TIER"):
                if et.attrib["TIER_ID"] == tier_name:
                    for node in graf_graph.nodes.iter_ordered():
                        if tier_name == str(node.id).split('/')[1]:
                            for ann in node.annotations:
                                features = {'ANNOTATION_ID': ann.id}
                                annotation_value = None

                                if "ref_annotation" in ann.features:
                                    ann_type = "REF_ANNOTATION"
                                    features["ANNOTATION_REF"] = ann.features["ref_annotation"]
                                    if "previous_annotation" in ann.features:
                                        features["PREVIOUS_ANNOTATION"] = ann.features["previous_annotation"]
                                else:
                                    ann_type = "ALIGNABLE_ANNOTATION"
                                    features['TIME_SLOT_REF1'] = ann.features['time_slot1']
                                    features['TIME_SLOT_REF2'] = ann.features['time_slot2']

                                if "annotation_value" in ann.features:
                                    annotation_value = ann.features['annotation_value']

                                for key, feature in ann.features.items():
                                    if key != 'ref_annotation' and\
                                       key != 'annotation_value' and\
                                       key != 'tier_id' and\
                                       key != 'previous_annotation' and not 'time_slot' in key:
                                        features[key] = feature

                                annotation_element = SubElement(et, 'ANNOTATION')
                                new_ann = SubElement(annotation_element, ann_type, features)
                                SubElement(new_ann, 'ANNOTATION_VALUE').text =\
                                annotation_value

        self._write_file(outputfile, meta_information)

    def _write_file(self, outputfile, element_tree):
        """Write and indent the element tree into a
        Elan file.

        Parameters
        ----------
        outputfile : str
            The filename of the output file. The filename should have
            the Elan extension ".eaf".
        element_tree : ElementTree
            Element tree with all the information.

        """

        file = open(outputfile, 'wb')
        doc = minidom.parseString(tostring(element_tree))
        file.write(doc.toprettyxml(indent='    ', encoding='UTF-8'))
        file.close()

    def _flatten_hierarchy_elements(self, elements):
        """Flat the elements appended to a new list of elements.

        Parameters
        ----------
        elements : array_like
            An array of string values.

        Returns
        -------
        flat_elements : array_like
            An array of flattened `elements`.

        """

        flat_elements = []
        for e in elements:
            if type(e) is list:
                flat_elements.extend(self._flatten_hierarchy_elements(e))
            else:
                flat_elements.append(e)
        return flat_elements