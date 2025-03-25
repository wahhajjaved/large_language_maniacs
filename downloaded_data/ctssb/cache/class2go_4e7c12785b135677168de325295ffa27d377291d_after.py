import re, collections
import urllib,urllib2
import json
from django.conf import settings
from xml.dom.minidom import parseString

class AutoGrader():
    """
    Autograder for an entire pset here.
    Can be use to grade single problems, of course.
    """
    __true_default =  {'correct':True, 'score':0}
    __false_default = {'correct':False, 'score':0}

    def __unicode__(self):
        graders=[]
        for k,v in self.grader_functions.iteritems():
            graders.append(k)
        return "AutoGrader functions for responses with names: %s.  Total Possible Points: %s" % \
            (", ".join(sorted(graders)), str(self.points_possible))
    
    def __init__(self, xml, default_return=None):
        """
            
        Initializes the autograder.  Takes in one argument, xml, which represents the metadata_xml.
        default_return is a kwarg which can be (None (default), True, False), which specifies the behavior of the
        grader when 
            
        """
        self.points_possible=0.0
        
        if xml == "__testing_bypass":
            return

        def return_true_default():
            def tempFn(submission):
                return self.__true_default
            return tempFn
                
        def return_false_default():
            def tempFn(submission):
                return self.__false_default
            return tempFn
    
        self.metadata_xml = xml #The XML metadata for the entire problem set.
        self.metadata_dom = parseString(xml) #The DOM corresponding to the XML metadata

        if default_return is None:
            self.grader_functions = {} #This is a dict that is keyed on the "name" of the submission (the input field) whose
                                       #value is a grader function for that submission.
                                       #will throw an exception if the key (questionID) is not found
        elif default_return:
            self.grader_functions = collections.defaultdict(return_true_default)  #Returns true if key not found
        else:
            self.grader_functions = collections.defaultdict(return_false_default) #Returns false if key not found
                                 

        questions = self.metadata_dom.getElementsByTagName('question_metadata')
        for q in questions:
            self._parse_question_metadata(q)
    
    def _parse_question_metadata(self, question_elem):
        """parses <question_metadata> elements, delegating each <response> child"""
        
        qid = question_elem.getAttribute('id').strip()
        if qid == "":
            raise AutoGraderMetadataException('A <question_metadata> tag has no "id" attribute!')
        
        responses = question_elem.getElementsByTagName('response')
        if not responses:
            raise AutoGraderMetadataException('<question_metadata id="%s"> has no <response> child tags!' % qid)
    
        for resp in responses:
            resp_name = self._validate_resp(resp, qid) #validate first
            
            type = resp.getAttribute('answertype').strip()
            if type == "":
                raise AutoGraderMetadataException('A <response> tag (child of <question_metadata id="%s">) has no "answertype" attribute!' % qid)
            elif type == "multiplechoiceresponse":
                self._parse_mc(resp, resp_name, qid)
            elif type == "numericalresponse":
                self._parse_num(resp, resp_name, qid)
            elif type == "dbclass-interactive":
                self._parse_interactive(resp, resp_name, qid)
            # more types should follow
            
    def _validate_resp(self, response_elem, qid):
        """
        Helper function that validates that <response> elements have unique "name" attributes
        """
        resp_name = response_elem.getAttribute("name").strip()
        if resp_name == "":
            raise AutoGraderMetadataException('A <response> tag (child of <question_metadata id="%s">) has no name attribute!' % qid)
        
        if resp_name in self.grader_functions:
            raise AutoGraderMetadataException('Duplicate name "%s" found for multiple <response> tags.  One is a child of <question_metadata id="%s">' \
                                              % (resp_name, qid))
        return resp_name
             
        
    
    def _get_numeric_attribute_with_default(self, element, attribute, default=0.0):
        """
        Helper function that gets an attribute with a numeric value and returns the float numeric value.
        Throws exception if attribute is not convertible.
        Returns default if attribute is not set
        """
        str_val = element.getAttribute(attribute)
        if str_val == "": #default
            return default
        else:
            try:
                return float(str_val)
            except ValueError:
                raise AutoGraderMetadataException('Element %s has attribute %s that cannot be converted a number' % (str(element), attribute))

    
    ########## Multiple-choice section ############

    def _parse_mc(self, response_elem, resp_name, qid):
        """
        Parses each <response answertype="multiplechoiceresponse"> element
        and sets up its grader function
        """
        
        #build up the correct answers
        choices = response_elem.getElementsByTagName('choice')
        if not choices:
            raise AutoGraderMetadataException('<question_medata id="%s">, <response name="%s"> has no <choice> descendants' % (qid,resp_name))

        choice_list = [] # This list is really for validation only
        answer_list = [] # This list will build the grader function
        for c in choices:
            cid = c.getAttribute('value').strip()
            if cid == "":
                raise AutoGraderMetadataException('<question_metadata id="%s">, <response name="%s"> has descendant <choice> tag with no "value" attribute' \
                                                  % (qid, resp_name))
            if cid in choice_list:
                raise AutoGraderMetadataException('<question_metadata id="%s">, <response name="%s"> has descendant <choice> tags with duplicate value "%s"' \
                                                  % (qid, resp_name, cid))
            choice_list.append(cid)
                    
            if c.getAttribute('correct').strip().lower() == 'true':
                answer_list.append(cid)

        correct_pts = self._get_numeric_attribute_with_default(response_elem,'correct-points',1)
        wrong_pts = self._get_numeric_attribute_with_default(response_elem, 'wrong-points',0)

        self.points_possible += correct_pts
                    
        self.grader_functions[resp_name] = self._MC_grader_factory(answer_list, correct_pts=correct_pts, wrong_pts=wrong_pts)


    def _MC_grader_factory(self, answer_list, correct_pts=1, wrong_pts=0):
        """
        A factory for returning multiple-choice graders.
        The signature of the returned function is 
            
            {'correct':boolean, 'score':float, 'correct_choices':dict, 'wrong_choices':dict} = grader_fn(submission_iterable)

        submission_iterable is an iterable which has as each entry a string of of the name corresponding to a
        student submitted choice.  All correct choices must be selected, and no incorrect choice selected.
        The return value is a dict with keys 'correct' and 'score' (using dict to be future proof)
        'correct_choices' is a dict whose keys are all the correct choices selected by the student.
        'wrong_choices' is a dict whose keys are all the 'wrong' choices for the student, and whose value is either
            'fp' (false_positive) where the student selected a wrong answer, or 'fn', where the student did not select a right answer.
            
        """
        def grader_fn(submission_iterable):
            correct=True
            cc = {}
            wc = {}
            for sub in submission_iterable:
                if sub not in answer_list:
                    wc[sub]='fp'
                    correct=False
                else:
                    cc[sub]=True
            for ans in answer_list:
                if ans not in submission_iterable:
                    wc[ans]='fn'
                    correct=False
            points = correct_pts if correct else wrong_pts
            return {'correct':correct, 'score':points, 'correct_choices':cc, 'wrong_choices':wc}

        return grader_fn
            

    ########## Numeric response section ############

    def _parse_num(self, response_elem, resp_name, qid):
        """
        Parses each <numericalresponse> element and sets up its grader function
        """

        answer_str = response_elem.getAttribute("answer")
        
        if answer_str == "" :
            raise AutoGraderMetadataException('<question_medata id="%s">, <response name="%s"> has no specified answer' % (qid,resp_name))

        try:
            answer = float(answer_str)
        except ValueError:
            raise AutoGraderMetadataException('In <question_medata id="%s">, <response name="%s">, cannot convert answer to number' % (qid,resp_name))

        tolerance_str = ""
        
        children = response_elem.childNodes
        for node in children:
            if node.nodeType == node.ELEMENT_NODE and node.nodeName == "responseparam" and node.getAttribute('type') == "tolerance" :
                tolerance_str = node.getAttribute("default").strip()
                break #only consider first tolerance setting 

        tolerance = (0.001)*answer #default tolerance is 0.1% of answer
        if tolerance_str :
            try:
                if tolerance_str[-1] == "%" : #entered as a percentage
                    tolerance_grp = re.match(r"^(.*)%$", tolerance_str)
                    tolerance = float(tolerance_grp.group(1))/100*answer #ugly syntax--group(1)--to get matched substring out
                else:
                    tolerance = float(tolerance_str)
            except ValueError:
                raise AutoGraderMetadataException('In <question_medata id="%s">, <response name="%s">, cannot convert tolerance to number' % (qid,resp_name))

        correct_pts = self._get_numeric_attribute_with_default(response_elem,'correct-points',1)
        wrong_pts = self._get_numeric_attribute_with_default(response_elem, 'wrong-points',0)

        self.points_possible += correct_pts

        self.grader_functions[resp_name] = self._NUM_grader_factory(answer, tolerance, correct_pts=correct_pts, wrong_pts=wrong_pts)
                    
    def _NUM_grader_factory(self, answer, tolerance, correct_pts=1, wrong_pts=0):
        """
        Factory function for a numeric grader.  The signature of the grader_fn is
        
            {'correct':boolean, 'score':float} = grader_fn(submission)
            
        which returns True if answer-tolerance <= submission <= answer+tolerance, else returns False
        Submission is a string that gets converted to a float.
        The return value dict of with keys 'correct' and 'score' (using dict to be future proof)

        """
        def grader_fn(submission):
            try:
                sub_num = float(submission)
            except ValueError:
                raise AutoGraderGradingException("Your submission could not be converted to a number!")
            if answer-tolerance <= sub_num and sub_num <= answer+tolerance:
                return {'correct':True, 'score':correct_pts}
            else:
                return {'correct':False, 'score':wrong_pts}
        return grader_fn
                    

    ########## Interactive Exercise Grader ############

    def _parse_interactive(self, response_elem, resp_name, qid):
        """
        The DB Class interactive grader expects to see a POST with a specific set of elements
        in the requests.  There are three direct elements:
            grader_name
            select_dict
            student_input
        and then an arbitrary set of elements called 'param[X]'.  student_input is filled in
        by the grader function later; we populate the rest from the XML here.
        """
        grader_post_params = {}
        for response_child in response_elem.childNodes:
            if response_child.nodeName == "#text":            # ignore
                next
            elif response_child.nodeName == "parameters":     # params are special
                for pnode in response_child.childNodes:
                    key = "params[%s]" % pnode.nodeName
                    if pnode.childNodes.length:
                        val = pnode.childNodes[0].nodeValue
                        grader_post_params[key] = val
            else:                                             # all else becomes a post param
                val = ""
                if response_child.childNodes.length:
                    val = response_child.childNodes[0].nodeValue
                grader_post_params[response_child.nodeName] = val
        self.grader_functions[resp_name] = self._INTERACTIVE_grader_factory(grader_post_params)

    def _INTERACTIVE_grader_factory(self, post_params):
        """
        Factory function for an interactive grader.  The signature of the grader_fn is

            {'correct':boolean, 'score':float, 'feedback':string } = grader_fn(submission)

        This does the remote call to the interactive grader and interprets the response.
        The grader returns a JSON structure that looks like this.

            {"score":0,
            "maximum-score":1,
            "feedback":[
                {"user_answer":"select * from movies",
                "score":0,
                "explanation":"<br><font style=\"color:red; font-weight:bold;\">Incorrect<\/font>..."
                }]
            }
        """
        def grader_fn(submission):
            # default responses, to be overriden by what we actually got back
            response = {}
            response['correct'] = False
            response['score'] = 0
            response['feedback'] = ""

            # call remote grader
            grader_url = getattr(settings, 'GRADER_ENDPOINT', 'localhost')
            post_params['student_input'] = submission
            grader_timeout = 5    # seconds
            try:
                post_data = urllib.urlencode(post_params)
                grader_conn = urllib2.urlopen(grader_url, post_data, grader_timeout)
            except urllib2.HTTPError as e:
                raise AutoGraderGradingException("interactive grader HTTP error (%d)" % e.code)
            except urllib2.URLError as e:
                raise AutoGraderGradingException("interactive grader connection error (%d)" % e.args)
            graded_result = grader_conn.read()
            if graded_result == "ERROR":
                raise AutoGraderGradingException("Interactive grader returned \"ERROR\"")
            try:
                graded = json.loads(graded_result)
            except:
                raise AutoGraderGradingException("Error parsing interactive grader result: %s" % graded_result)

            # interpret what we got from the grader
            # class2go just has one float score, coursera used score vs max, convert here
            if 'score' in graded:
                if graded['score'] == 1:
                    response['correct'] = True
                if 'maximum-score' in graded and graded['maximum-score'] != 0:
                    maxscore = float(graded['maximum-score'])
                else:
                    maxscore = 1.0
                response['score'] = float(graded['score']) / maxscore
            if 'feedback' in graded:
                response['feedback'] = graded['feedback']

            return response

        return grader_fn


    ########## The actual grader, for what it is ############

    def grade(self, input_name, submission):
        """Grades student submission for response name=input_name"""
        try:
            return self.grader_functions[input_name](submission)
        except KeyError:
            raise AutoGraderGradingException('Input/Response name="%s" is not defined in grading template' % input_name)

class AutoGraderException(Exception):
    """Base class for exceptions in this module"""
    pass

class AutoGraderMetadataException(AutoGraderException):
    """
    An error during the parsing/grading function generation step
    of the problemset XML metadata.  Could be because certain required attibutes or tags are missing.
    """
    pass
       
class AutoGraderGradingException(AutoGraderException):
    """
    An error during the auto grading step (not XML parsing or grading function generation)
    """
    pass

