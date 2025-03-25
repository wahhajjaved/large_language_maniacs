"""Utilities for use by assessment package implementations"""

from dlkit.abstract_osid.osid.errors import NotFound, NullArgument, IllegalState
from dlkit.abstract_osid.assessment.objects import Assessment as abc_assessment
from ..utilities import get_provider_manager
from bson import ObjectId

def get_first_part_id_for_assessment(assessment_id, runtime=None, proxy=None, create=False, bank_id=None):
    """Gets the first part id, which represents the first section, of assessment"""
    if create and bank_id is None:
        raise NullArgument('Bank Id must be provided for create option')
    try:
        return get_next_part_id(assessment_id, runtime, proxy)[0]
    except IllegalState:
        if create:
            return create_first_assessment_section(assessment_id, runtime, proxy, bank_id)
        else:
            raise

def get_next_part_id(part_id, runtime=None, proxy=None):
    part, rule, siblings = get_decision_objects(part_id, runtime, proxy)
    if rule is not None: # A SequenceRule trumps everything.
        next_part_id = rule.get_next_assessment_part_id()
        if level:
            level = get_level_delta(part_id, next_part_id, runtime, proxy)
    elif part.has_children(): # This is a special AssessmentPart that can manage child Parts
        next_part_id = part.get_child_ids()[0]
        level = -1
    elif siblings and siblings[-1] != part_id:
        next_part_id = siblings[siblings.index(part_id) + 1]
        level = 0
    else: # We are at a lowest leaf and need to check parent
        if isinstance(part, abc_assessment): # This is an Assessment masquerading as an AssessmentPart 
            raise IllegalState('No next AssessmentPart is available for part_id')
        elif part.has_assessment_part(): # This is the child of another AssessmentPart
            next_part_id, level = get_next_part_id(part.get_assessment_part_id(), runtime, proxy)
        else: # This is the child of an Assessment
            next_part_id, level = get_next_part_id(part.get_assessment_id(), runtime, proxy)
    return next_part_id, level

def get_level_delta(part1_id, part2_id, runtime, proxy):
    mgr = get_provider_manager('ASSESSMENT_AUTHORING', runtime, proxy)
    lookup_session = mgr.get_assessment_part_lookoup_session(proxy=proxy)
    part1 = lookup_session.get_assessment_part(part1_id)
    part2 = lookup_session.get_assessment_part(part2_id)
    while part1.has_assessment_part() and part2.has_assessment_part:
        part1 = part1.get_assessment_part
        part2 = part2.get_assessment_part
    if part1.has_assessment_part():
        return count_levels(part1, -1)
    elif part2.has_assessment_part():
        return count_levels(part2, 1)
    else:
        return 0

    def count_levels(part, increment):
        level = 0
        while part.has_assessment_part():
            level = level + increment
            part = part.get_assessment_part()
        return level

def get_decision_objects(part_id, runtime, proxy):
    assessment_lookup_session, part_lookup_session, rule_lookup_session = get_lookup_sessions(runtime, proxy)
    sibling_ids = []
    try:
        part = part_lookup_session.get_part(part_id)
    except NotFound: # perhaps this is an assessment masquerading as a part:
        part = assessment_lookup_session.get_assessment(part_id)
    else:
        if part.has_assessment_part():
            parent = part.get_assessment_part()
        else:
            parent = part.get_assessment()
        if parent.has_children():
            sibling_ids = parent.get_child_ids()
    rule = get_first_successful_sequence_rule_for_part(part_id, rule_lookup_session)
    return part, rule, list(sibling_ids)

def create_first_assessment_section(assessment_id, runtime, proxy, bank_id):
    assessment_admin_session, part_admin_session, rule_admin_session = get_admin_sessions(runtime, proxy, bank_id)
    mgr = get_provider_manager('ASSESSMENT', runtime=runtime, proxy=proxy, local=True)
    assessment_lookup_session = mgr.get_assessment_lookup_session(proxy=proxy)
    assessment_lookup_session.use_federated_bank_view()
    assessment = assessment_lookup_session.get_assessmen(assessment_id)
    part_form = part_admin_session.get_assessment_part_form_for_create_for_assessment(assessment_id, [])
    part_form.set_display_name(assessment.get_display_name().get_text() + ' First Part')
    part_form.set_sequestered(False) # Any Part of an Assessment must be a Section (i.e. non sequestered)
    # part_form.set_weight(100) # Uncomment this line when set_weight is implemented
    # Should we set allocated time?
    part_id = part_admin_session.create_assessment_part_for_assessment(part_form).get_id()
    if assessment.supports_simple_child_sequencing():
        child_ids = assessment.get_child_ids()
        child_ids.insert(0, str(part_id))
        update_form = assessment_admin_session.get_assessment_form_for_update(assessment.get_id())
        update_form.set_children(child_ids)
        assessment_admin_session.update_assessment(assessment.get_id())
    else:
        rule_form = rule_admin_session.get_rule_form_for_create(assessment.get_id(), part_id, [])
        rule_form.set_display_name('First Part Rule')
        rule_admin_session.create_rule(rule_form)
    return part_id

def get_lookup_sessions(runtime, proxy):
    mgr = get_provider_manager('ASSESSMENT', runtime=runtime, proxy=proxy, local=True)
    assessment_lookup_session = mgr.get_assessment_lookup_session(proxy=proxy)
    assessment_lookup_session.use_federated_bank_view()
    mgr = get_provider_manager('ASSESSMENT_AUTHORING', runtime=runtime, proxy=proxy, local=True)
    part_lookup_session = mgr.get_assessment_part_lookup_session(proxy=proxy)
    part_lookup_session.use_federated_bank_view()
    rule_lookup_session = mgr.get_sequence_rule_lookup_session(proxy=proxy)
    rule_lookup_session.use_federated_bank_view()
    return assessment_lookup_session, part_lookup_session, rule_lookup_session

def get_admin_sessions(runtime, proxy, bank_id):
    mgr = get_provider_manager('ASSESSMENT', runtime=runtime, proxy=proxy, local=True)
    assessment_admin_session = mgr.get_assessment_admin_session_for_bank(bank=bank, proxy=proxy)
    mgr = get_provider_manager('ASSESSMENT_AUTHORING', runtime=runtime, proxy=proxy, local=True)
    part_admin_session = mgr.get_assessment_part_admin_session_for_bank(bank=bank, proxy=proxy)
    rule_admin_session = mgr.get_sequence_rule_admin_session_for_bank(bank=bank, proxy=proxy)
    return assessment_admin_session, part_admin_session, rule_admin_session

def get_first_successful_sequence_rule_for_part(part_id, rule_lookup_session):
    for rule in rule_lookup_session.get_sequence_rules_for_assessment_part(part_id):
        if rule._evaluates_true(): # Or wherever this wants to be evaluated
            return rule
    return None

def get_assessment_section(self, section_id, runtime=None, proxy=None):
    """Gets a Section given a section_id"""
    from .objects import AssessmentSection
    collection = MongoClientValidated('assessment',
                                      collection='AssessmentSection',
                                      runtime=self._runtime)
    result = collection.find_one(dict({'_id': ObjectId(assessment_id.get_identifier())}))
    return AssessmentSection(osid_object_map=result, runtime=self._runtime, proxy=self._proxy)

def get_default_part_map(self, part_id, level):
    return {
        'assessmentPartId': str(part_id),
        'level': level
    }

def get_default_question_map(self, item_id, question_id, assessment_part_id, display_elements):
    return {
        'itemId': str(item_id),
        'questionId': str(question_id),
        'assessmentPartId': str(assessment_part_id),
        'displayElements': display_elements,
        'responses': [None]
    }
