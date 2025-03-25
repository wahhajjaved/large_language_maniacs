# For creating an xform for ODK there are three components:
# Instance: which only needs the name of the question.
# Binding: which needs a bunch of attributes.
# Control: which is determined by the type of the question.

import json, re
from datetime import datetime
from copy import copy
from lxml import etree
from lxml.builder import ElementMaker

nsmap = {
    None : "http://www.w3.org/2002/xforms",
    "h" : "http://www.w3.org/1999/xhtml",
    "ev" : "http://www.w3.org/2001/xml-events",
    "xsd" : "http://www.w3.org/2001/XMLSchema",
    "jr" : "http://openrosa.org/javarosa",
    }

E = ElementMaker(nsmap=nsmap)

def ns(abbrev, text):
    return "{" + nsmap[abbrev] + "}" + text

def sluggify(text, delimiter=u"_"):
    return re.sub(ur"[^a-z]+", delimiter, text.lower())

def json_dumps(obj):
    def default_encode(obj):
        return obj.__dict__
    return json.dumps(obj, indent=4, default=default_encode)

class Question(object):
    """
    Abstract base class to build different question types on top of.
    """
    def __init__(self, text, name=u"", attributes={}, hint=u""):
        self.text = text
        self.name = name if name else sluggify(text, u" ")
        self._attributes = attributes.copy()
        self.hint = hint

    def label_element(self):
        return E.label(self.text)

    def hint_element(self):
        if self.hint:
            return E.hint(self.hint)

    def label_and_hint(self):
        return [self.label_element()] + [self.hint_element()]

    def slug(self):
        return sluggify(self.name)

    def instance(self):
        return E(self.slug())

    def bind(self, xpath):
        """
        Return an XML string representing the binding of this
        question.
        """
        return E.bind(nodeset=xpath, **self._attributes)

    def control(self, xpath):
        """
        The control depends on what type of question we're asking, it
        doesn't make sense to implement here in the base class.
        """
        raise Exception("Control not implemented")

class InputQuestion(Question):
    """
    This control string is the same for: strings, integers, decimals,
    dates, geopoints, barcodes ...
    """
    def control(self, xpath):
        return E.input(ref=xpath, *self.label_and_hint())

# The following code extends the class InputQuestion for a bunch of
# different types of InputQuestions.
def init_method(t):
    def __init__(self, **kwargs):
        InputQuestion.__init__(self, **kwargs)
        self._attributes[u"type"] = t
    return __init__

types = {
    "String" : u"string",
    "Integer" : u"int",
    "Geopoint" : u"geopoint",
    "Decimal" : u"decimal",
    "Date" : u"date",
    "Barcode" : u"barcode",
    }

for k, v in types.items():
    globals()[k + "Question"] = type(
        k + "Question",
        (InputQuestion,),
        {"__init__" : init_method(v)}
        )

# StringQuestion is on the classes we created above.
class Note(StringQuestion):
    def __init__(self, **kwargs):
        StringQuestion.__init__(self, **kwargs)
        self._attributes[u"readonly"] = u"true()"
        self._attributes[u"required"] = u"false()"

class PhoneNumberQuestion(StringQuestion):    
    def __init__(self, **kwargs):
        StringQuestion.__init__(self, **kwargs)
        self._attributes[u"constraint"] = u"regex(., '^\d*$')"
        self._attributes[u"jr:constraintMsg"] = u"Please enter only numbers."
        self.hint = u"'0' = respondent has no phone number\n" + \
            u"'1' = respondent prefers to skip this question."

class PercentageQuestion(IntegerQuestion):
    def __init__(self, **kwargs):
        IntegerQuestion.__init__(self, **kwargs)
        self._attributes[u"constraint"] = u"0 <= . and . <= 100"
        self._attributes[u"jr:constraintMsg"] = \
            u"Please enter an integer between zero and one hundred."

class UploadQuestion(Question):
    def __init__(self, **kwargs):
        Question.__init__(self, **kwargs)
        self._attributes[u"type"] = u"binary"

    def control(self, xpath, mediatype):
        return E.upload(ref=xpath, mediatype=mediatype,
                        *self.label_and_hint())


class PictureQuestion(UploadQuestion):
    def control(self, xpath):
        return UploadQuestion.control(self, xpath, "image/*")

class Choice(object):
    def __init__(self, label, value):
        self.label = label
        self.value = value

    def xml(self):
        return E.item( E.label(self.label), E.value(self.value) )

def tuples(l):
    """
    This is a helper function to create lists of choices quickly. List
    entries can be string labels that will be sluggified to create
    values, or an entry can be a pair where one specifies the desired
    value.
    """
    result = []
    for entry in l:
        if type(entry)==unicode:
            result.append((entry, sluggify(entry)))
        elif type(entry)==tuple and len(entry)==2:
            result.append(entry)
        else:
            raise Exception("Expected unicode string or tuple", entry)
    return result

def choices(l):
    return [Choice(label=pair[0], value=pair[1]) for pair in tuples(l)]

class MultipleChoiceQuestion(Question):
    def __init__(self, **kwargs):
        """
        Multiple choice questions take two options not included in the
        base class: a list of choices, and a flag whether one can
        select one or many.
        """
        self.choices = choices(kwargs.pop("choices"))
        Question.__init__(self, **kwargs)

    def control(self, xpath):
        result = E(self._attributes[u"type"], {"ref" : xpath})
        for element in self.label_and_hint() + [c.xml() for c in self.choices]:
            result.append(element)
        return result        

class SelectOneQuestion(MultipleChoiceQuestion):
    def __init__(self, **kwargs):
        MultipleChoiceQuestion.__init__(self, **kwargs)
        self._attributes[u"type"] = u"select1"
        self.hint = u"select one"

class YesNoQuestion(SelectOneQuestion):
    def __init__(self, **kwargs):
        SelectOneQuestion.__init__(self, **kwargs)
        self.choices = choices([u"Yes", u"No"])

class YesNoDontKnowQuestion(SelectOneQuestion):
    def __init__(self, **kwargs):
        SelectOneQuestion.__init__(self, **kwargs)
        self.choices = choices([u"Yes", u"No", (u"Don't Know", u"unknown")])

class SelectMultipleQuestion(MultipleChoiceQuestion):
    def __init__(self, **kwargs):
        MultipleChoiceQuestion.__init__(self, **kwargs)
        self._attributes[u"type"] = u"select"
        self._attributes[u"required"] = u"false()"
        self.hint = u"select all that apply"

# Ideally, I'd like to make a bunch of functions with the prefix q and
# the rest of the function name is the question type. I'll look into
# this when I have Internet
question_class = {
    "string" : StringQuestion,
    "phone number" : PhoneNumberQuestion,
    "integer" : IntegerQuestion,
    "percentage" : PercentageQuestion,
    "select one" : SelectOneQuestion,
    "select all that apply" : SelectMultipleQuestion,
    "yes or no" : YesNoQuestion,
}
def q(text, question_type="integer", name=u"", attributes={}, choices=[]):
    c = question_class[question_type]
    if issubclass(c, MultipleChoiceQuestion):
        return c(name=name, text=text, choices=choices)
    else:
        return c(name=name, text=text)

def table(rows, columns):
    result = []
    for row_text, row_name in tuples(rows):
        for d in columns:
            kwargs = d.copy()
            kwargs["text"] = row_text + u": " + kwargs["text"]
            kwargs["name"] = row_name + u" " + kwargs.get("name", sluggify(kwargs["text"]))
            result.append(q(**kwargs))
    return result    

ODK_DATE_FORMAT = "%Y-%m-%d_%H-%M-%S"

class Survey(object):
    def __init__(self, title, questions):
        self.title = title
        self._stack = [sluggify(self.title)]
        self.questions = questions
        self._set_up_xpath_dictionary()

    def _set_up_xpath_dictionary(self):
        self.xpath = {}
        for q in self.questions:
            self.xpath[q.slug()] = u"/" + self._stack[0] + u"/" + q.slug()
        
    def xml(self):
        return E(ns("h", "html"),
                 E(ns("h", "head"),
                   E(ns("h", "title"), self.title),
                   E("model",
                     E("instance", self.instance()),
#                     *self.bindings()
                     ),
                   ),
                 E(ns("h", "body"), *self.controls())
                 )

    def instance(self):
        slug = self._stack[0]
        id = self._stack[0] + u" " + \
            datetime.now().strftime(ODK_DATE_FORMAT)
        result = E(slug, {"id" : id})
        for q in self.questions: result.append(q.instance())
        return result

    def bindings(self):
        # we need to calculate the xpaths of each question
        return [q.bind("xpath") for q in self.questions]

    def controls(self):
        return [q.control("xpath") for q in self.questions]

    def __unicode__(self):
        return etree.tostring(self.xml(), pretty_print=True)




#         "dateTime" : ["date and time"],

#     supported_attributes = ["required", "relevant", "readonly", "constraint", "jr:constraintMsg","jr:preload","jr:preloadParams", "calculate"]

# jr:preload questions dont have any control

# def apply(function, survey):
#     l = len(survey.elements)
#     function(survey)
#     if len(survey.elements) > l:
#         apply(function, survey)

# def add_one_specify(survey):
#     for i in range(len(survey.elements)):
#         question = survey.elements[i]
#         if question.type in ["select one", "select all that apply"]:
#             if "other" in [choice[1] for choice in question.choices] and survey.elements[i+1].text!="Please specify":
#                 d = {"name" : question.name + " other",
#                      "text" : "Please specify",
#                      "type" : "string",
#                      "relevant" : "selected([%s], 'other')" % question.name}
#                 new_question = Question(**d)
#                 new_list = survey.elements[0:i+1]
#                 new_list.append(new_question)
#                 new_list.extend(survey.elements[i+1:len(survey.elements)])
#                 survey.elements = new_list
#                 return

# def main(path):
#     folder, filename = os.path.split(path)
#     m = re.search(r"([^\.]+)\.([^\.]+)$", filename)
#     filename = m.group(1).title()
#     title = m.group(1).title()
#     outfile = os.path.join("xforms", filename + ".xml")

#     survey = survey_from_text(path)
#     survey.title = title
#     apply(fake_one_table, survey)
#     apply(add_one_specify, survey)

#     f = open(outfile, "w")
#     xml_str = survey_to_xml(survey).encode("utf-8")
#     f.write(xml_str)
#     f.close()

if __name__ == '__main__':
    s = Survey(title="test", questions=[q("Is this working?", name=u"working", question_type="yes or no")])
    print s.__unicode__()
