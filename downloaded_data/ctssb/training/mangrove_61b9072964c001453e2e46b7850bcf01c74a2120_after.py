# vim: ai ts=4 sts=4 et sw=4 encoding=utf-8
from collections import OrderedDict
from mangrove.form_model.validator_factory import validator_factory
from mangrove.datastore import entity
from mangrove.datastore.database import DatabaseManager, DataObject
from mangrove.datastore.documents import FormModelDocument, attributes
from mangrove.errors.MangroveException import FormModelDoesNotExistsException, QuestionCodeAlreadyExistsException,\
    EntityQuestionAlreadyExistsException, MangroveException, DataObjectAlreadyExists, InactiveFormModelException
from mangrove.form_model.field import TextField
from mangrove.form_model.validators import MandatoryValidator
from mangrove.utils.geo_utils import convert_to_geometry
from mangrove.utils.types import is_sequence, is_string, is_empty, is_not_empty
from mangrove.form_model import field

ARPT_SHORT_CODE = "dummy"

REGISTRATION_FORM_CODE = "reg"
ENTITY_TYPE_FIELD_CODE = "t"
ENTITY_TYPE_FIELD_NAME = "entity_type"
LOCATION_TYPE_FIELD_NAME = "location"
LOCATION_TYPE_FIELD_CODE = "l"
GEO_CODE = "g"
GEO_CODE_FIELD_NAME = "geo_code"

NAME_FIELD = "name"
FORM_CODE="form_code"
NAME_FIELD_CODE = "n"
SHORT_CODE_FIELD = "short_code"
SHORT_CODE = "s"
DESCRIPTION_FIELD = "description"
DESCRIPTION_FIELD_CODE = "d"
MOBILE_NUMBER_FIELD = "mobile_number"
MOBILE_NUMBER_FIELD_CODE = "m"
REPORTER = "reporter"
GLOBAL_REGISTRATION_FORM_ENTITY_TYPE="registration"

def get_form_model_by_code(dbm, code):
    assert isinstance(dbm, DatabaseManager)
    assert is_string(code)
    rows = dbm.load_all_rows_in_view('questionnaire', key=code)
    if not len(rows):
        raise FormModelDoesNotExistsException(code)

    doc = FormModelDocument.wrap(rows[0]['value'])
    return FormModel.new_from_doc(dbm, doc)

def get_form_model_by_entity_type(dbm, entity_type):
    assert isinstance(dbm, DatabaseManager)
    assert is_sequence(entity_type)
    rows = dbm.view.registration_form_model_by_entity_type(key=entity_type, include_docs=True)
    if len(rows):
        doc = FormModelDocument.wrap(rows[0]['doc'])
        return FormModel.new_from_doc(dbm, doc)
    return None

class FormModel(DataObject):
    __document_class__ = FormModelDocument

    def __init__(self, dbm, name=None, label=None, form_code=None, fields=None, entity_type=None, type=None,
                 language="en", is_registration_model=False, state=attributes.ACTIVE_STATE, validators=None):
        if not validators: validators = [MandatoryValidator()]
        assert isinstance(dbm, DatabaseManager)
        assert name is None or is_not_empty(name)
        assert fields is None or is_sequence(fields)
        assert form_code is None or (is_string(form_code) and is_not_empty(form_code))
        assert type is None or is_not_empty(type)
        assert entity_type is None or is_sequence(entity_type)

        DataObject.__init__(self, dbm)

        self._form_fields = []
        self.errors = []
        self.validators = validators
        # Are we being constructed from scratch or existing doc?
        if name is None:
            return

        # Not made from existing doc, so build ourselves up
        self._form_fields = fields
        self._validate_fields()

        doc = FormModelDocument()
        doc.name = name
        doc.add_label(language, label)
        doc.form_code = form_code
        doc.entity_type = entity_type
        doc.type = type
        doc.state = state
        doc.active_languages = [language]
        doc.is_registration_model = is_registration_model
        DataObject._set_document(self, doc)

    @property
    def name(self):
        """
        Returns the name of the FormModel
        """
        return self._doc.name

    @name.setter
    def name(self, value):
        """
        Sets the name of the FormModel
        """
        self._doc.name = value

    @property
    def entity_question(self):
        eq = None
        for f in self._form_fields:
            if isinstance(f, TextField) and f.is_entity_field:
                eq = f
                break
        return eq

    @property
    def event_time_question(self):
        event_time_questions = [event_time_question for event_time_question in self._form_fields if
                  event_time_question.is_event_time_field]
        return event_time_questions[0] if event_time_questions else None

    @property
    def form_code(self):
        return self._doc.form_code

    @form_code.setter
    def form_code(self, value):
        self._doc.form_code = value

    @property
    def fields(self):
        return self._form_fields

    @property
    def entity_type(self):
        return self._doc.entity_type

    @entity_type.setter
    def entity_type(self, value):
        self._doc.entity_type = value

    @property
    def type(self):
        return self._doc.type

    @property
    def label(self):
        return self._doc.label

    @property
    def activeLanguages(self):
        return self._doc.active_languages

    @activeLanguages.setter
    def activeLanguages(self, value):
        self._doc.active_languages = value

    def get_short_code(self, values):
        return  self._case_insensitive_lookup(values, self.entity_question.code)

    def get_entity_type(self, values):
        entity_type = self._case_insensitive_lookup(values, ENTITY_TYPE_FIELD_CODE)
        return entity_type.lower() if is_not_empty(entity_type) else None

    def submit(self, dbm, values):
        self.bind(values)
        if self.is_inactive():
            raise InactiveFormModelException(self.form_code)
        form_submission = self.validate_submission(values)
        if form_submission.is_valid:
            form_submission.save(dbm)
        return form_submission

    def save(self):
        # convert fields and validators to json fields before save
        if not self._is_form_code_unique():
            raise DataObjectAlreadyExists('Form Model', 'Form Code', self.form_code)

        self._doc.json_fields = [f._to_json() for f in self._form_fields]
        self._doc.validators = [validator.to_json() for validator in self.validators]
        return DataObject.save(self)


    def get_field_by_name(self, name):
        for field in self._form_fields:
            if field.name == name:
                return field
        return None

    def get_field_by_code(self, code):
        for field in self._form_fields:
            if code != None and field.code.lower() == code.lower():
                return field
        return None

    def add_field(self, field):
        self._form_fields.append(field)
        self._validate_fields()
        return self._form_fields

    def delete_field(self, code):
        self._form_fields = [f for f in self._form_fields if f.code != code]
        self._validate_fields()

    def delete_all_fields(self):
        self._form_fields = []

    def add_language(self, language, label=None):
        self._doc.active_languages.append(language)
        if label is not None:
            self._doc.add_label(language, label)

    def validate_submission(self, values):
        cleaned_answers, errors = self._is_valid(values)
        return FormSubmissionFactory().get_form_submission(self, cleaned_answers, errors)


    def is_registration_form(self):
        return self._doc['is_registration_model']

    def entity_defaults_to_reporter(self):
        return self.entity_type == [REPORTER]

    def is_inactive(self):
        return True if self._doc.state.lower() == attributes.INACTIVE_STATE.lower() else False

    def is_active(self):
        return True if self._doc.state.lower() == attributes.ACTIVE_STATE.lower() else False

    def is_in_test_mode(self):
        return True if self._doc.state.lower() == attributes.TEST_STATE.lower() else False

    def deactivate(self):
        self._doc.state = attributes.INACTIVE_STATE

    def activate(self):
        self._doc.state = attributes.ACTIVE_STATE

    def set_test_mode(self):
        self._doc.state = attributes.TEST_STATE

    def bind(self, submission):
        self.submission = submission
        for field in self.fields:
            answer = self._case_insensitive_lookup(self.submission, field.code)
            field.set_value(answer)

    def _validate_fields(self):
        self._validate_existence_of_only_one_entity_field()
        self._validate_uniqueness_of_field_codes()


    def _validate_uniqueness_of_field_codes(self):
        """ Validate all question codes are unique
        """
        code_list = [f.code.lower() for f in self._form_fields]
        code_list_without_duplicates = list(set(code_list))
        if len(code_list) != len(code_list_without_duplicates):
            raise QuestionCodeAlreadyExistsException("All question codes must be unique")

    def _validate_existence_of_only_one_entity_field(self):
        """Validate only 1 entity question is there"""
        entity_question_list = [f for f in self._form_fields if isinstance(f, TextField) and f.is_entity_field == True]
        if len(entity_question_list) > 1:
            raise EntityQuestionAlreadyExistsException("Entity Question already exists")

    def _validate_answer_for_field(self, answer, field):
        try:
            value = field.validate(answer)
            return True, value
        except MangroveException as e:
            field.errors.append(e.message)
            return False, e.message

    def _set_document(self, document):
        DataObject._set_document(self, document)

        # make form_model level fields for any json fields in to
        for json_field in document.json_fields:
            f = field.create_question_from(json_field, self._dbm)
            self._form_fields.append(f)
        for validator_json in document.validators:
            validator = validator_factory(validator_json)
            if validator not in self.validators:
                self.validators.append(validator)

    def _is_form_code_unique(self):
        try:
            form = get_form_model_by_code(self._dbm, self.form_code)
            is_form_code_same_as_existing_form_code = True if form.id == self.id else False
            return  is_form_code_same_as_existing_form_code
        except FormModelDoesNotExistsException:
            return True

    def _find_code(self, answers, code):
        for key in answers:
            if key.lower() == code.lower():
                return answers[key]
        return None

    def _remove_empty_values(self, answers):
        return OrderedDict([(k,v) for k, v in answers.items() if not is_empty(v)])

    def _remove_unknown_fields(self, answers):
        return OrderedDict([(k,v) for k, v in answers.items() if self.get_field_by_code(k) is not None])

    def _is_valid(self, values):
        assert values is not None
        cleaned_values = OrderedDict()
        errors = OrderedDict()
        for validator in self.validators:
            errors.update(validator.validate(values, self.fields, self._dbm))
        values = self._remove_empty_values(values)
        values = self._remove_unknown_fields(values)
        for key in values:
            field = self.get_field_by_code(key)
            is_valid, result = self._validate_answer_for_field(values[key], field)
            if is_valid:
                cleaned_values[field.code] = result
            else:
                errors[key] = result
        return cleaned_values, errors

    def _case_insensitive_lookup(self, values, code):
        for fieldcode in values:
            if fieldcode.lower() == code.lower():
                return values[fieldcode]
        return None


class FormSubmission(object):
    def __init__(self, form_model, form_answers, errors=None):
        assert errors is None or type(errors) == OrderedDict
        assert form_answers is not None and type(form_answers) == OrderedDict
        assert form_model is not None

        self.form_model = form_model
        self._cleaned_data = form_answers
        short_code = self.get_answer_for(form_model.entity_question.code)
        self.short_code = short_code.lower() if short_code is not None else None
        self.is_valid = (errors is None or len(errors) == 0)
        self.errors = errors
        self.entity_type = self.get_entity_type(form_model)
        self.data_record_id = None

    @property
    def cleaned_data(self):
        return self._cleaned_data

    @property
    def form_code(self):
        return self.form_model.form_code

    @property
    def saved(self):
        return self.data_record_id is not None

    @property
    def is_registration(self):
        return self.form_model.is_registration_form()


    def save(self, dbm):
        return self._save_data(self.get_entity(dbm))

    def _get_event_time_value(self):
        code = self._get_event_time_code()
        value = self.cleaned_data.get(code)

        if value is not None:
            value = self.form_model.event_time_question.to_datetime(value)
        return value

    def _get_event_time_code(self):
        event_time_field = self.form_model.event_time_question
        return event_time_field.code if event_time_field else None

    def _save_data(self, entity):
        submission_information = dict(form_code=self.form_code)
        self.data_record_id = entity.add_data(data=self._values, event_time=self._get_event_time_value(),submission=submission_information)
        return self.data_record_id

    def get_entity_type(self, form_model):
        entity_type = self.form_model.entity_type
        return [e_type.lower() for e_type in entity_type] if is_not_empty(entity_type) else None

    def _to_three_tuple(self):
        return [(self.form_model.get_field_by_code(code).name, value, self.form_model.get_field_by_code(code).ddtype)
        for (code, value) in
        (self.cleaned_data.items())]

    def get_answer_for(self, code):
        for key in self._cleaned_data:
            if key.lower() == code.lower():
                return self._cleaned_data[key]
        return None

    @property
    def _values(self):
        return self._to_three_tuple()

    def get_entity(self, dbm):
        pass

    def _get_field_code_by_name(self,field_name):
        field = self.form_model.get_field_by_name(name=field_name)
        return field.code if field is not None else None

    def get_location_field_code(self):
        return self._get_field_code_by_name(LOCATION_TYPE_FIELD_NAME)

    def get_geo_field_code(self):
        return self._get_field_code_by_name(GEO_CODE_FIELD_NAME)

class DataFormSubmission(FormSubmission):
    def __init__(self,form_model,answers,errors):
        super(DataFormSubmission,self).__init__(form_model,answers,errors)

    def get_entity(self,dbm):
        return entity.get_by_short_code(dbm, self.short_code, self.entity_type)

class GlobalRegistrationFormSubmission(FormSubmission):
    def __init__(self,form_model,answers,errors):
        super(GlobalRegistrationFormSubmission,self).__init__(form_model,answers,errors)
        self.entity_type=self.get_entity_type(form_model)

    def get_entity(self,dbm):
        location = self.cleaned_data.get(self.get_location_field_code())
        return entity.create_entity(dbm=dbm, entity_type=self.get_entity_type(self.form_model),
            location=location,
            short_code=self.short_code,
            geometry=convert_to_geometry(self.cleaned_data.get(self.get_geo_field_code())))

    def get_entity_type(self, form_model):
        entity_type = self.get_answer_for(ENTITY_TYPE_FIELD_CODE)
        return [e_type.lower() for e_type in entity_type] if is_not_empty(entity_type) else None

class EntityRegistrationFormSubmission(FormSubmission):
    def __init__(self,form_model,answers,errors):
        super(EntityRegistrationFormSubmission,self).__init__(form_model,answers,errors)

    def get_entity(self, dbm):
        location = self.cleaned_data.get(self.get_location_field_code())
        return entity.create_entity(dbm=dbm, entity_type=self.entity_type,
                location=location,
                short_code=self.short_code,
                geometry=convert_to_geometry(self.cleaned_data.get(self.get_geo_field_code())))



class FormSubmissionFactory(object):

    def _is_global_registration_form(self,form_model):
        return GLOBAL_REGISTRATION_FORM_ENTITY_TYPE in form_model.entity_type

    def get_form_submission(self,form_model, answers,errors=None):
        if not form_model.is_registration_form():
            return DataFormSubmission(form_model, answers,errors)
        return GlobalRegistrationFormSubmission(form_model,answers,errors) if self._is_global_registration_form(form_model) else EntityRegistrationFormSubmission(form_model,answers,errors)
