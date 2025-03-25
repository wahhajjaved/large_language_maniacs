#MAEC Bundle Class

#Copyright (c) 2013, The MITRE Corporation
#All rights reserved.

#Compatible with MAEC v4.0
#Last updated 09/20/2013

import datetime
import collections

from cybox.core import Object

import maec
import maec.bindings.maec_bundle as bundle_binding
from maec.bundle.malware_action import MalwareAction
from maec.bundle.av_classification import AVClassifications
from maec.bundle.behavior import Behavior
from maec.bundle.candidate_indicator import CandidateIndicator, CandidateIndicatorList
from maec.bundle.action_reference_list import ActionReferenceList
from maec.bundle.process_tree import ProcessTree


class Bundle(maec.Entity):
    def __init__(self, id, defined_subject, schema_version = 4.0, content_type = None, malware_instance_object = None):
        self.id = id
        self.schema_version = schema_version
        self.defined_subject = defined_subject
        self.content_type = content_type
        self.timestamp = None
        self.malware_instance_object_attributes = malware_instance_object
        #Add all of the top-level containers
        self.av_classifications = AVClassifications()
        self.actions = ActionList()
        self.process_tree = None
        self.behaviors = BehaviorList()
        self.objects = ObjectList()
        self.candidate_indicators = CandidateIndicatorList()
        self.collections = Collections()

    #Set the Malware Instance Object Attributes
    def set_malware_instance_object_atttributes(self, malware_instance_object):
        self.malware_instance_object_attributes = malware_instance_object

    #Add an AV classification
    def add_av_classification(self, av_classification):
        self.av_classifications.append(av_classification)

    #Set the Process Tree, in the top-level <Process_Tree> element
    def set_process_tree(self, process_tree):
        self.process_tree = process_tree

    #Add a new Named Action Collection
    def add_named_action_collection(self, collection_name, collection_id):
        if collection_name is not None and collection_id is not None:
            self.collections.action_collections.append(ActionCollection(collection_name, collection_id))
        
    #Add an Action to an existing named collection; if it does not exist, add it to the top-level <Actions> element
    def add_action(self, action, action_collection_name = None):
        if action_collection_name is not None:
            #The collection has already been defined
            if self.collections.action_collections.has_collection(action_collection_name):
                action_collection = self.collections.action_collections.get_named_collection(action_collection_name)
                action_collection.add_action(action)
        elif action_collection_name == None:
            self.actions.append(action)

    #Add a new Named Object Collection
    def add_named_object_collection(self, collection_name, collection_id):
        if collection_name is not None and collection_id is not None:
            self.collections.object_collections.append(ObjectCollection(collection_name, collection_id))
              
    # return a list of all objects from self.actions and all actions collections
    def get_all_actions(self):
        all_actions = []
        for action in self.actions:
            all_actions.append(action)
            
        for collection in self.collections.action_collections:
            for action in collection.action_list:
                all_actions.append(action)
                
        return all_actions
              
    #Add an Object to an existing named collection; if it does not exist, add it to the top-level <Objects> element
    def add_object(self, object, object_collection_name = None):
        if object_collection_name is not None:
            #The collection has already been defined
            if self.collections.object_collections.has_collection(object_collection_name):
                object_collection = self.collections.object_collections.get_named_collection(object_collection_name)
                object_collection.add_object(object)
        elif object_collection_name == None:
            self.objects.append(object)

    # return a list of all objects from self.objects and all object collections
    def get_all_objects(self):
        all_objects = []
        for obj in self.objects:
            all_objects.append(obj)
            
        for collection in self.collections.object_collections:
            for obj in collection.object_list:
                all_objects.append(obj)
                
        return all_objects
    
    # finds actions and objects by id
    def get_object_by_id(self, id):
        for action in self.actions:
            if action.id == id:
                return action
            
            for associated_obj in action.associated_objects:
                    if associated_obj.id_ == id:
                        return associated_obj
            
        for collection in self.collections.action_collections:
            for action in collection.action_list:
                if action.id == id:
                    return action
                
                for associated_obj in action.associated_objects:
                    if associated_obj.id_ == id:
                        return associated_obj
        
        for obj in self.objects:
            print obj.id
            if obj.id == id:
                return obj
            
        for collection in self.collections.object_collections:
            for obj in collection.object_list:
                print obj.id
                if obj.id == id:
                    return obj

    #Add a new Named Behavior Collection
    def add_named_behavior_collection(self, collection_name, collection_id):
        if collection_name is not None and collection_id is not None:
            self.collections.behavior_collections.append(BehaviorCollection(collection_name, collection_id))

    #Add a Behavior to an existing named collection; if it does not exist, add it to the top-level <Behaviors> element
    def add_behavior(self, behavior, behavior_collection_name = None):
        if behavior_collection_name is not None:
            #The collection has already been defined
            if self.collections.behavior_collections.has_collection(behavior_collection_name):
                behavior_collection = self.collections.behavior_collections.get_named_collection(behavior_collection_name)
                behavior_collection.add_Behavior(behavior)
        elif behavior_collection_name == None:
            self.behaviors.append(behavior)

    #Add a new Named Behavior Collection
    def add_named_candidate_indicator_collection(self, collection_name, collection_id):
        if collection_name is not None and collection_id is not None:
            self.collections.candidate_indicator_collections.append(CandidateIndicatorCollection(collection_name, collection_id))

    #Add a Candidate Indicator to an existing named collection; if it does not exist, add it to the top-level <Candidate_Indicators> element
    def add_candidate_indicator(self, candidate_indicator, candidate_indicator_collection_name = None):
        if candidate_indicator_collection_name is not None:
            #The collection has already been defined
            if self.collections.candidate_indicator_collections.has_collection(candidate_indicator_collection_name):
                candidate_indicator_collection = self.collections.candidate_indicator_collections.get_named_collection(candidate_indicator_collection_name)
                candidate_indicator_collection.add_candidate_indicator(candidate_indicator)
        elif candidate_indicator_collection_name == None:
            self.candidate_indicators.append(candidate_indicator)
    
    def to_obj(self):
        bundle_obj = bundle_binding.BundleType(id=self.id)
        #Set the bundle schema version
        bundle_obj.set_schema_version(self.schema_version)
        #Set whether this Bundle has a defined_subject
        bundle_obj.set_defined_subject(self.defined_subject)
        #Set the bundle timestamp
        if self.timestamp is not None : bundle_obj.set_timestamp(self.timestamp.isoformat())
        #Set the content_type if it is not none
        if self.content_type is not None: bundle_obj.set_content_type(self.content_type)
        #Set the Malware Instance Object Attributes (a CybOX object) if they are not none
        if self.malware_instance_object_attributes is not None: bundle_obj.set_Malware_Instance_Object_Attributes(self.malware_instance_object_attributes.to_obj())
        #Add the AV Classifications
        if self.av_classifications: bundle_obj.set_AV_Classifications(self.av_classifications.to_obj())
        #Add the Behaviors
        if self.behaviors: bundle_obj.set_Behaviors(self.behaviors.to_obj())
        #Add the Actions
        if self.actions: bundle_obj.set_Actions(self.actions.to_obj())
        #Add the Objects
        if self.objects: bundle_obj.set_Objects(self.objects.to_obj())
        #Add the Process Tree
        if self.process_tree is not None: bundle_obj.set_Process_Tree(self.process_tree.to_obj())
        #Add the Candidate Indicators
        if self.candidate_indicators: bundle_obj.set_Candidate_Indicators(self.candidate_indicators.to_obj())
        #Add the collections
        if self.collections is not None and self.collections.has_content(): bundle_obj.set_Collections(self.collections.to_obj())
        return bundle_obj

    def to_dict(self):
        bundle_dict = {}
        if self.id is not None : bundle_dict['id'] = self.id
        if self.schema_version is not None : bundle_dict['schema_version'] = self.schema_version
        if self.defined_subject is not None : bundle_dict['defined_subject'] = self.defined_subject
        if self.content_type is not None : bundle_dict['content_type'] = self.content_type
        if self.timestamp is not None : bundle_dict['timestamp'] = self.timestamp.isoformat()
        if self.malware_instance_object_attributes is not None : bundle_dict['malware_instance_object_attributes'] = self.malware_instance_object_attributes.to_dict()
        if self.av_classifications : bundle_dict['av_classifications'] = self.av_classifications.to_list()
        if self.process_tree is not None : bundle_dict['process_tree'] = self.process_tree.to_dict()
        if self.behaviors : bundle_dict['behaviors'] = self.behaviors.to_list()
        if self.actions : bundle_dict['actions'] = self.actions.to_list()
        if self.objects : bundle_dict['objects'] = self.objects.to_list()
        if self.candidate_indicators : bundle_dict['candidate_indicators'] = self.candidate_indicators.to_list()
        if self.collections is not None and self.collections.has_content(): bundle_dict['collections'] = self.collections.to_dict()
        return bundle_dict

    @staticmethod
    def from_obj(bundle_obj):
        if not bundle_obj:
            return None
        bundle_ = Bundle(None, None)
        bundle_.id = bundle_obj.get_id()
        bundle_.schema_version = bundle_obj.get_schema_version()
        bundle_.defined_subject = bundle_obj.get_defined_subject()
        bundle_.content_type = bundle_obj.get_content_type()
        bundle_.timestamp = bundle_obj.get_timestamp()
        bundle_.malware_instance_object_attributes = Object.from_obj(bundle_obj.get_Malware_Instance_Object_Attributes())
        if bundle_obj.get_AV_Classifications() is not None: bundle_.av_classifications = AVClassifications.from_obj(bundle_obj.get_AV_Classifications())
        bundle_.process_tree = ProcessTree.from_obj(bundle_obj.get_Process_Tree())
        if bundle_obj.get_Behaviors() is not None : bundle_.behaviors = BehaviorList.from_obj(bundle_obj.get_Behaviors())
        if bundle_obj.get_Actions() is not None : bundle_.actions = ActionList.from_obj(bundle_obj.get_Actions())
        if bundle_obj.get_Objects() is not None : bundle_.objects = ObjectList.from_obj(bundle_obj.get_Objects())
        if bundle_obj.get_Candidate_Indicators() is not None : bundle_.candidate_indicators = CandidateIndicatorList.from_obj(bundle_obj.get_Candidate_Indicators())
        bundle_.collections = Collections.from_obj(bundle_obj.get_Collections())
        return bundle_

    @staticmethod
    def from_dict(bundle_dict):
        if not bundle_dict:
            return None
        bundle_ = Bundle(None, None)
        bundle_.id = bundle_dict.get('id')
        bundle_.schema_version = bundle_dict.get('schema_version')
        bundle_.defined_subject = bundle_dict.get('defined_subject')
        bundle_.content_type = bundle_dict.get('content_type')
        bundle_.timestamp = datetime.datetime.strptime(bundle_dict.get('timestamp'), "%Y-%m-%dT%H:%M:%S.%f")
        bundle_.malware_instance_object_attributes = Object.from_dict(bundle_dict.get('malware_instance_object_attributes'))
        bundle_.av_classifications = AVClassifications.from_list(bundle_dict.get('av_classifications'))
        bundle_.process_tree = ProcessTree.from_dict(bundle_dict.get('process_tree'))
        bundle_.behaviors = BehaviorList.from_list(bundle_dict.get('behaviors', []))
        bundle_.actions = ActionList.from_list(bundle_dict.get('actions', []))
        bundle_.objects = ObjectList.from_list(bundle_dict.get('objects', []))
        bundle_.candidate_indicators = CandidateIndicatorList.from_list(bundle_dict.get('candidate_indicators', []))
        bundle_.collections = Collections.from_dict(bundle_dict.get('collections'))
        return bundle_

    @classmethod
    def compare(cls, bundle_list, match_on = None):
        return BundleComparator.compare(bundle_list, match_on);
    
class ComparisonResult(object):
    def __init__(self, bundle_list, lookup_table):
        self.lookup_table = lookup_table
        self.bundle_list = bundle_list
    
    def get_unique(self, bundle_list=None):
        unique_objs = {}
        
        if bundle_list is None:
            bundle_list = self.bundle_list
        
        for b in self.bundle_list:
            unique_objs[b.id] = []
        
        for obj_hash in self.lookup_table:
            sources = BundleComparator.get_sources(self.lookup_table, obj_hash)
            if len(sources) == 1:
                result_index = sources[0]
                for unique_obj in self.lookup_table[obj_hash][result_index]:
                    unique_objs[result_index].append(unique_obj['object'].id_)
                
        return unique_objs
    
    def get_common(self, bundle_list=None):
        confirmed_objs = []
        
        if bundle_list is None:
            bundle_list = self.bundle_list
            
        for obj_hash in self.lookup_table:
            sources = BundleComparator.get_sources(self.lookup_table, obj_hash)
            if len(sources) > 1:
                confirmed_obj_dict = {}
                confirmed_obj_dict['object'] = obj_hash
                confirmed_obj_dict['object_instances'] = {}

                for key, obj_list in self.lookup_table[obj_hash].items():
                    confirmed_obj_dict['object_instances'][key] = []
                    for common_obj in obj_list:
                        confirmed_obj_dict['object_instances'][key].append(common_obj['object'].id_)

                if confirmed_obj_dict not in confirmed_objs:
                    confirmed_objs.append(confirmed_obj_dict)
                        
        return confirmed_objs
    
    
class SimilarObjectCluster(dict):
    def __init__(self):
        pass
        
    def add_object(self, obj, owner):
        if owner not in self:
            self[owner] = [{ 'object':obj, 'ownerBundle':owner }]
        else:
            self[owner].append({ 'object':obj, 'ownerBundle':owner })
        
    def get_object_by_owner_id(self, owner_id):
        return self[owner_id][0]["object"]
            
    
class BundleComparator(object):
    @classmethod
    def compare(cls, bundle_list, match_on = None):
        cls.object_table = {}
        if not match_on:
            # Default matching properties
            cls.match_on = {
                            'FileObjectType': 
                                ['file_name', 'file_path'],
                            'WindowsRegistryKeyObjectType': 
                                ['hive','key'],
                            'WindowsMutexObjectType':
                                ['name'],
                            'SocketObjectType':
                                ['address_value', 'port_value'],
                            'WindowsPipeObjectType':
                                ['name'],
                            'ProcessObjectType':
                                ['command_line']}
        else:
            cls.match_on = match_on

        lookup_table = {}
        
        for bundle in bundle_list:
            for action in bundle.get_all_actions():
                cls.process_action(action, lookup_table, bundle.id)
                    
            for obj in bundle.get_all_objects():
                cls.process_object(obj, lookup_table, bundle.id)

        return ComparisonResult(bundle_list, lookup_table)
        
    @classmethod
    def process_action(cls, action, lookup_table, bundle):
        for associated_object in action.associated_objects:
            # get actual object from associated object
            obj = associated_object
            cls.process_object(obj, lookup_table, bundle)

    @classmethod
    def process_object(cls, obj, lookup_table, bundle):
        # get hash string from object to use as key in lookup table
        # Make sure the object is one of the supported types in the match_on dictionary
        if obj.properties._XSI_TYPE in cls.match_on:
            hash_value = cls.get_hash(obj)
            if hash_value:
                if hash_value not in lookup_table:
                    lookup_table[hash_value] = SimilarObjectCluster()
                lookup_table[hash_value].add_object(obj, bundle)
                
    @classmethod
    def get_hash(cls, obj):
        hash_val = ''
        
        for typed_field in obj.properties._get_vars():
            # Make sure the typed field is comparable
            if typed_field.comparable:
                # Check if we're dealing with a nested element that we want to compare
                nested_element = cls.is_nested_match(str(typed_field), cls.match_on[obj.properties._XSI_TYPE])
                # Handle the normal, non-nested case
                if not nested_element and str(typed_field) in cls.match_on[obj.properties._XSI_TYPE]:
                    hash_val = cls.get_val(obj, typed_field, hash_val)
                # Handle the nested case
                elif nested_element:
                   split_nested_element = nested_element.split('.')
                   hash_val = cls.get_val(obj, typed_field, hash_val, split_nested_element[1:])
        return hash_val

    @classmethod
    def get_val(cls, obj, typed_field, hash_val, nested_elements = None):
        if not nested_elements:
            val = getattr(obj.properties, str(typed_field))

            if val is not None:
                hash_val += str(typed_field) + ":" + str(val) + " "
        else:
            if len(nested_elements) == 1:
                val = getattr(obj.properties, str(typed_field))
                if val is not None:
                    hash_val += str(typed_field) + ":"
                    if isinstance(val, collections.MutableSequence):
                        for list_item in val:
                            if '/' in str(nested_elements[0]):
                                hash_val += '['
                                split_names = nested_elements[0].split('/')
                                for name in split_names:
                                    name_val = getattr(list_item, name)
                                    if name_val :  hash_val += name + ':' + str(name_val) + ','
                                hash_val = hash_val.rstrip(',')
                                hash_val += ']'
                            else:
                                hash_val += '[' + str(nested_elements[0]) + ':' +  str(getattr(list_item, str(nested_elements[0]))) + ']'
                    else:
                        hash_val += str(getattr(val, nested_elements[0]))
        return hash_val

    @classmethod
    def get_sources(cls, lookup_table, obj_hash):
        val = []
        for obj_dict_list in lookup_table[obj_hash].values():
            if not obj_dict_list[0] in val: 
                val.append(obj_dict_list[0]['ownerBundle'])
        return val

    @classmethod
    def is_nested_match(cls, typed_field_name, match_on_list):
        for matching_property in match_on_list:
            if '.' in matching_property and typed_field_name in matching_property:
                return matching_property
        return False

class BehaviorList(maec.EntityList):
    _contained_type = Behavior
    _binding_class = bundle_binding.BehaviorListType
    _binding_var = "Behavior"

class ActionList(maec.EntityList):
    _contained_type = MalwareAction
    _binding_class = bundle_binding.ActionListType
    _binding_var = "Action"
    
class ObjectList(maec.EntityList):
    _contained_type = Object
    _binding_class = bundle_binding.ObjectListType
    _binding_var = "Object"

class BaseCollection(maec.Entity):
    def __init__(self, name = None):
        super(BaseCollection, self).__init__()
        self.name = name
        self.affinity_type = None
        self.affinity_degree = None
        self.description = None

    def to_obj(self, derived_collection_obj = None):
        if derived_collection_obj == None:
            collection_obj = bundle_binding.BaseCollectionType()
        else:
            collection_obj = derived_collection_obj
        if self.name is not None: collection_obj.set_name(self.name)
        if self.affinity_type is not None: collection_obj.set_Affinity_Type(self.affinity_type)
        if self.affinity_degree is not None: collection_obj.set_Affinity_Degree(self.affinity_degree)               
        if self.description is not None: collection_obj.set_Description(self.description)
        return collection_obj

    def to_dict(self):
        base_collection_dict = {}
        if self.name is not None : base_collection_dict['name'] = self.name
        if self.affinity_type is not None : base_collection_dict['affinity_type'] = self.affinity_type
        if self.affinity_degree is not None : base_collection_dict['affinity_degree'] = self.affinity_degree
        if self.description is not None : base_collection_dict['description'] = self.description
        return base_collection_dict

    @staticmethod
    def from_obj(collection_obj, derived_collection_cls = None):
        if not collection_obj:
            return None
        if derived_collection_cls == None:
            collection_obj_ = BaseCollection()
        else:
            collection_obj_ = derived_collection_cls
        collection_obj_.name = collection_obj.get_name()
        collection_obj_.affinity_type = collection_obj.get_Affinity_Type()
        collection_obj_.affinity_degree = collection_obj.get_Affinity_Degree()
        collection_obj_.description = collection_obj.get_Description()
        return collection_obj_

    @staticmethod
    def from_dict(collection_dict, derived_collection_cls = None):
        if not collection_dict:
            return None
        if derived_collection_cls == None:
            collection_obj_ = BaseCollection()
        else:
            collection_obj_ = derived_collection_cls
        collection_obj_.name = collection_dict.get('name')
        collection_obj_.affinity_type = collection_dict.get('affinity_type')
        collection_obj_.affinity_degree = collection_dict.get('affinity_degree')
        collection_obj_.description = collection_dict.get('description')
        return collection_obj_

class ActionCollection(BaseCollection):
    superclass = BaseCollection

    def __init__(self, name = None, id = None):
        super(ActionCollection, self).__init__(name)
        self.id = id
        self.action_list = ActionList()

    def add_action(self, action):
        self.action_list.append(action)

    def to_obj(self):
        action_collection_obj = super(ActionCollection, self).to_obj(bundle_binding.ActionCollectionType())
        if self.id is not None : action_collection_obj.set_id(self.id)
        if len(self.action_list) > 0:  action_collection_obj.set_Action_List(self.action_list.to_obj())
        return action_collection_obj

    def to_dict(self):
        action_collection_dict = super(ActionCollection, self).to_dict()
        if self.id is not None : action_collection_dict['id'] = self.id
        if len(self.action_list) > 0: action_collection_dict['action_list'] = self.action_list.to_list()
        return action_collection_dict

    @staticmethod
    def from_obj(action_collection_obj):
        if not action_collection_obj:
            return None
        action_collection_ = BaseCollection.from_obj(action_collection_obj, ActionCollection())
        action_collection_.id = action_collection_obj.get_id()
        action_collection_.action_list = ActionList.from_obj(action_collection_obj.get_Action_List())
        return action_collection_

    @staticmethod
    def from_dict(action_collection_dict):
        if not action_collection_dict:
            return action_collection_dict
        action_collection_ = BaseCollection.from_dict(action_collection_dict, ActionCollection())
        action_collection_.id = action_collection_dict.get('id')
        action_collection_.action_list = ActionList.from_list(action_collection_dict.get('action_list'))
        return action_collection_

class BehaviorCollection(BaseCollection):
    superclass = BaseCollection

    def __init__(self, name = None, id = None):
        super(BehaviorCollection, self).__init__(name)
        self.id = id
        self.behavior_list = BehaviorList()

    def add_behavior(self, behavior):
        self.behavior_list.append(behavior)

    def to_obj(self):
        behavior_collection_obj = super(BehaviorCollection, self).to_obj(bundle_binding.BehaviorCollectionType())
        if self.id is not None : behavior_collection_obj.set_id(self.id)
        if len(self.behavior_list) > 0: behavior_collection_obj.set_Behavior_List(self.behavior_list.to_obj())
        return behavior_collection_obj

    def to_dict(self):
        behavior_collection_dict = super(BehaviorCollection, self).to_dict()
        if self.id is not None : behavior_collection_dict['id'] = self.id
        if len(self.behavior_list) > 0: behavior_collection_dict['behavior_list'] = self.behavior_list.to_list()
        return behavior_collection_dict

    @staticmethod
    def from_obj(behavior_collection_obj):
        if not behavior_collection_obj:
            return None
        behavior_collection_ = BaseCollection.from_obj(behavior_collection_obj, BehaviorCollection())
        behavior_collection_.id = behavior_collection_obj.get_id()
        behavior_collection_.behavior_list = BehaviorList.from_obj(behavior_collection_obj.get_Behavior_List())
        return behavior_collection_

    @staticmethod
    def from_dict(behavior_collection_dict):
        if not behavior_collection_dict:
            return None
        behavior_collection_ = BaseCollection.from_dict(behavior_collection_dict, BehaviorCollection())
        behavior_collection_.id = behavior_collection_dict.get('id')
        behavior_collection_.behavior_list = BehaviorList.from_list(behavior_collection_dict.get('behavior_list'))
        return behavior_collection_

class ObjectCollection(BaseCollection):
    superclass = BaseCollection

    def __init__(self, name = None, id = None):
        super(ObjectCollection, self).__init__(name)
        self.id = id
        self.object_list = ObjectList()

    def add_object(self, object):
        self.object_list.append(object)

    def to_obj(self):
        object_collection_obj = super(ObjectCollection, self).to_obj(bundle_binding.ObjectCollectionType())
        if self.id is not None : object_collection_obj.set_id(self.id)
        if len(self.object_list) > 0 : object_collection_obj.set_Object_List(self.object_list.to_obj())
        return object_collection_obj

    def to_dict(self):
        object_collection_dict = {}
        if self.id is not None : object_collection_dict['id'] = self.id
        if len(self.object_list) > 0 : object_collection_dict['object_list'] = self.object_list.to_list()
        return object_collection_dict

    @staticmethod
    def from_obj(object_collection_obj):
        if not object_collection_obj:
            return None
        object_collection_ = BaseCollection.from_obj(object_collection_obj, ObjectCollection())
        object_collection_.id = object_collection_obj.get_id()
        object_collection_.object_list =  ObjectList.from_obj(object_collection_obj.get_Object_List())
        return object_collection_

    @staticmethod
    def from_dict(object_collection_dict):
        if not object_collection_dict:
            return None
        object_collection_ = BaseCollection.from_dict(object_collection_dict, ObjectCollection())
        object_collection_.id = object_collection_dict.get('id')
        object_collection_.object_list =  ObjectList.from_list(object_collection_dict.get('object_list'))
        return object_collection_

class CandidateIndicatorCollection(BaseCollection):
    superclass = BaseCollection

    def __init__(self, name = None, id = None):
        super(CandidateIndicatorCollection, self).__init__(name)
        self.id = id
        self.candidate_indicator_list = CandidateIndicatorList()

    def add_candidate_indicator(self, candidate_indicator):
        self.candidate_indicator_list.append(candidate_indicator)

    def to_obj(self):
        candidate_indicator_collection_obj = super(CandidateIndicatorCollection, self).to_obj(bundle_binding.CandidateIndicatorCollectionType())
        if self.id is not None : candidate_indicator_collection_obj.set_id(self.id)
        if len(self.candidate_indicator_list) > 0 is not None: candidate_indicator_collection_obj.set_Candidate_Indicator_List(self.candidate_indicator_list.to_obj())
        return candidate_indicator_collection_obj

    def to_dict(self):
        candidate_indicator_collection_dict = {}
        if self.id is not None : candidate_indicator_collection_dict['id'] = self.id
        if len(self.candidate_indicator_list) > 0 is not None: candidate_indicator_collection_dict['candidate_indicator_list'] = self.candidate_indicator_list.to_list()
        return candidate_indicator_collection_dict

    @staticmethod
    def from_obj(candidate_indicator_collection_obj):
        if not candidate_indicator_collection_obj:
            return None
        candidate_indicator_collection_ = BaseCollection.from_obj(candidate_indicator_collection_obj, CandidateIndicatorCollection())
        candidate_indicator_collection_.id = candidate_indicator_collection_obj.get_id()
        candidate_indicator_collection_.candidate_indicator_list = CandidateIndicatorList.from_obj(candidate_indicator_collection_obj.get_Candidate_Indicator_List())
        return candidate_indicator_collection_

    @staticmethod
    def from_dict(candidate_indicator_collection_dict):
        if not candidate_indicator_collection_dict:
            return None
        candidate_indicator_collection_ = BaseCollection.from_dict(candidate_indicator_collection_dict, CandidateIndicatorCollection())
        candidate_indicator_collection_.id = candidate_indicator_collection_dict.get('id')
        candidate_indicator_collection_.candidate_indicator_list = CandidateIndicatorList.from_list(candidate_indicator_collection_dict.get('candidate_indicator_list'))
        return candidate_indicator_collection_

class BehaviorCollectionList(maec.EntityList):
    _contained_type = BehaviorCollection
    _binding_class = bundle_binding.BehaviorCollectionListType
    _binding_var = "Behavior_Collection"
    
    def __init__(self):
        super(BehaviorCollectionList, self).__init__()

    def to_obj(self):
        behavior_collection_list_obj = bundle_binding.BehaviorCollectionListType()
        for behavior_collection in self:
            if len(behavior_collection.behavior_list) > 0:
                behavior_collection_list_obj.add_Behavior_Collection(behavior_collection.to_obj())
        return behavior_collection_list_obj

    #Checks for the existence of a named collection in the list
    def has_collection(self, collection_name):
        for collection in self:
            if collection.name is not None and collection.name == collection_name:
                return True
        return False

    #Get a specific named collection in the list
    def get_named_collection(self, collection_name):
        for collection in self:
            if collection.name is not None and collection.name == collection_name:
                return collection
        return None

class ActionCollectionList(maec.EntityList):
    _contained_type = ActionCollection
    _binding_class = bundle_binding.ActionCollectionListType
    _binding_var = "Action_Collection"
    
    def __init__(self):
        super(ActionCollectionList, self).__init__()

    def to_obj(self):
        action_collection_list_obj = bundle_binding.ActionCollectionListType()
        for action_collection in self:
            if len(action_collection.action_list) > 0:
                action_collection_list_obj.add_Action_Collection(action_collection.to_obj())
        return action_collection_list_obj

    #Checks for the existence of a named collection in the list
    def has_collection(self, collection_name):
        for collection in self:
            if collection.name is not None and collection.name == collection_name:
                return True
        return False

    #Get a specific named collection in the list
    def get_named_collection(self, collection_name):
        for collection in self:
            if collection.name is not None and collection.name == collection_name:
                return collection
        return None

class ObjectCollectionList(maec.EntityList):
    _contained_type = ObjectCollection
    _binding_class = bundle_binding.ObjectCollectionListType
    _binding_var = "Object_Collection"
    
    def __init__(self):
        super(ObjectCollectionList, self).__init__()

    def to_obj(self):
        object_collection_list_obj = bundle_binding.ObjectCollectionListType()
        for object_collection in self:
            if len(object_collection.object_list) > 0:
                object_collection_list_obj.add_Object_Collection(object_collection.to_obj())
        return object_collection_list_obj

    #Checks for the existence of a named collection in the list
    def has_collection(self, collection_name):
        for collection in self:
            if collection.name is not None and collection.name == collection_name:
                return True
        return False

    #Get a specific named collection in the list
    def get_named_collection(self, collection_name):
        for collection in self:
            if collection.name is not None and collection.name == collection_name:
                return collection
        return None

class CandidateIndicatorCollectionList(maec.EntityList):
    _contained_type = CandidateIndicatorCollection
    _binding_class = bundle_binding.CandidateIndicatorCollectionListType
    _binding_var = "Candidate_Indicator_Collection"
    
    def __init__(self):
        super(CandidateIndicatorCollectionList, self).__init__()

    def to_obj(self):
        candidate_indicator_collection_list_obj = bundle_binding.CandidateIndicatorCollectionListType()
        for candidate_indicator_collection in self:
            if len(candidate_indicator_collection.candidate_indicator_list) > 0:
                candidate_indicator_collection_list_obj.add_Candidate_Indicator_Collection(candidate_indicator_collection.to_obj())
        return candidate_indicator_collection_list_obj

    #Checks for the existence of a named collection in the list
    def has_collection(self, collection_name):
        for collection in self:
            if collection.name is not None and collection.name == collection_name:
                return True
        return False

    #Get a specific named collection in the list
    def get_named_collection(self, collection_name):
        for collection in self:
            if collection.name is not None and collection.name == collection_name:
                return collection
        return None

class Collections(maec.Entity):

    def __init__(self):
        super(Collections, self).__init__()
        self.behavior_collections = BehaviorCollectionList()
        self.action_collections = ActionCollectionList()
        self.object_collections = ObjectCollectionList()
        self.candidate_indicator_collections = CandidateIndicatorCollectionList()

    #Checks if the collections instance has any of its lists populated
    def has_content(self):
        if len(self.behavior_collections) > 0:
            return True
        elif len(self.action_collections) > 0:
            return True
        elif len(self.object_collections) > 0:
            return True
        elif len(self.candidate_indicator_collections) > 0:
            return True
        return False

    def to_obj(self):
        collections_obj = bundle_binding.CollectionsType()
        if len(self.behavior_collections) > 0 : collections_obj.set_Behavior_Collections(self.behavior_collections.to_obj())
        if len(self.action_collections) > 0 : collections_obj.set_Action_Collections(self.action_collections.to_obj())
        if len(self.object_collections) > 0 : collections_obj.set_Object_Collections(self.object_collections.to_obj())
        if len(self.candidate_indicator_collections) > 0 : collections_obj.set_Candidate_Indicator_Collections(self.candidate_indicator_collections.to_obj())
        return collections_obj

    def to_dict(self):
        collections_dict = {}
        if len(self.behavior_collections) > 0 : collections_dict['behavior_collections'] = self.behavior_collections.to_list()
        if len(self.action_collections) > 0 : collections_dict['action_collections'] = self.action_collections.to_list()
        if len(self.object_collections) > 0 : collections_dict['object_collections'] = self.object_collections.to_list()
        if len(self.candidate_indicator_collections) > 0 : collections_dict['candidate_indicator_collections'] = self.candidate_indicator_collections.to_list()
        return collections_dict

    @staticmethod
    def from_dict(collections_dict):
        if not collections_dict:
            return None
        collections_ = Collections()
        collections_.behavior_collections = BehaviorCollectionList.from_list(collections_dict.get('behavior_collections', []))
        collections_.action_collections = ActionCollectionList.from_list(collections_dict.get('action_collections', []))
        collections_.object_collections = ObjectCollectionList.from_list(collections_dict.get('object_collections', []))
        collections_.candidate_indicator_collections = CandidateIndicatorCollectionList.from_list(collections_dict.get('candidate_indicator_collections', []))
        return collections_

    @staticmethod
    def from_obj(collections_obj):
        if not collections_obj:
            return None
        collections_ = Collections()
        if collections_obj.get_Behavior_Collections() is not None:
            collections_.behavior_collections = BehaviorCollectionList.from_obj(collections_obj.get_Behavior_Collections())
        if collections_obj.get_Action_Collections() is not None: 
            collections_.action_collections = ActionCollectionList.from_obj(collections_obj.get_Action_Collections())
        if collections_obj.get_Object_Collections() is not None:
            collections_.object_collections = ObjectCollectionList.from_obj(collections_obj.get_Object_Collections())
        if collections_obj.get_Candidate_Indicator_Collections() is not None:
            collections_.candidate_indicator_collections = CandidateIndicatorCollectionList.from_obj(collections_obj.get_Candidate_Indicator_Collections())
        return collections_
