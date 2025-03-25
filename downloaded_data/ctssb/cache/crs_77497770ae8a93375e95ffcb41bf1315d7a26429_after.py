from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.html import mark_safe, format_html
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.http import HttpResponse, Http404, HttpResponseForbidden
from django.core.urlresolvers import reverse
from django.conf import settings
from django.db import transaction, IntegrityError
from django.db.models import Max, Q, F

from .models import *
from .forms import *
from .tables import *
from guardian.shortcuts import get_objects_for_user
from simpleeval import simple_eval, NameNotDefined
from sendfile import sendfile
import random
import json
import csv
import re
import os

def staff_required(login_url=settings.LOGIN_URL):
    return user_passes_test(lambda u:u.is_staff, login_url=login_url)


# ---------- Front page Views (fold) ---------- #

@staff_required()
def delete_item(request, objectStr, pk):
    """ Generically used to delete items
    """
    if request.user.is_staff:
        # Depending on which item is set, we return different pages
        if objectStr == "markedquestion":
            theObj = get_object_or_404(
                MarkedQuestion.objects.select_related('quiz', 'quiz__course'),
                pk = pk)
            description = "MarkedQuestion {}".format(theObj.pk)
            # Get the course for the object so we can check if the user has permissions
            # to delete the object
            course = theObj.quiz.course
            if request.user.has_perm('quizzes.can_edit_quiz', course):
                return_view = redirect(reverse(
                        'quiz_admin',  
                        kwargs={
                            'course_pk': course.pk,
                            'quiz_pk': theObj.quiz.pk,
                        }))
            else:
                return HttpResponseForbidden(
                    'You are not authorized to delete that object')
                
        else:
            return HttpResponse('<h1>Invalid Object Type</h1>')

        if request.method == "POST":
            theObj.delete()
            return return_view
        else:
            return render(request, 'quizzes/delete_item.html', 
                    {'object': theObj, 
                     'type' : objectStr,
                     'description': description,
                     'return_url': return_view.url,
                    }
                )
    else:
        return HttpResponseForbidden()

@login_required
def courses(request):
    """ Main page for accessing quizzes. Upon authentication, shows the list of
        quizzes in which the student is enrolled
    """
    membership,_ = UserMembership.objects.get_or_create(
                    user=request.user)
    courses = membership.courses.all()
    return render(
        request, 
        'quizzes/courses.html', 
        {'courses' : courses} )

@login_required
def administrative(request):
    """ For course administrators (recognize by the is_staff flag) to do just
        that: Adminstrate a course.
    """
    if not request.user.is_staff:
        return HttpResponseForbidden("Not a valid User")
    else:
        return render(
            request,
            'quizzes/administration.html')

# --------- Front page Views (end) -------#

# ---------- Quizzes (fold) ---------- #

# ---------- Quiz Add/Edit/Admin (fold) ---------- #

@staff_required()
def new_quiz(request, course_pk):
    """ Form for creating a new quiz. Requires
        course_pk - (Integer) The primary key for the course.
        TODO: Check against 'can_edit_quiz" privileges.
    """
    course = get_object_or_404(Course, pk=course_pk)

    if not request.user.has_perm('quizzes.can_edit_quiz', course):
        return HttpResponseForbidden('You are not authorized to create quizzes')

    if request.method == "POST":
        form = QuizForm(request.POST)
        if form.is_valid():
            quiz = form.save(commit=False)
            quiz.course = course
            quiz.update_out_of()
            # Create an exemption type for the quiz and update it's out_of field
            evaluation, created = Evaluation.objects.get_or_create(
                    name=quiz.name, course=course)
            evaluation.quiz_update_out_of(quiz)
            
            # For database convenience, populate the category as well. Updates will be made
            # in the function 'display_question', which will also take care of any student whose
            # record was not made to begin with
            #ret_flag = populate_category_helper(exemption)
            return redirect('list_quizzes', course_pk=course.pk)
    else:
        form = QuizForm()

    return render(
        request, 
        'quizzes/generic_form.html', 
        { 'form' : form,
          'header': "Add Quiz to Course",
          'course': course,
        }
    )

@staff_required()
def edit_quiz(request, course_pk, quiz_pk):
    """ Fetches a quiz instance to populate an editable form. 
        <<Input>>
        course_pk, quiz_pk - (Integers) The primary key for the quiz and course
        respectively.
    """

    quiz = get_object_or_404(Quiz, pk=quiz_pk)
    course = quiz.course

    if not request.user.has_perm('can_edit_quiz', course):
        return HttpResponseForbidden("You are not authorized to see this.")

    if request.method == "POST":
        form = QuizForm(request.POST, instance=quiz)
        if form.is_valid():
            quiz = form.save()
            quiz.update_out_of()
            # Since we might have changed the quiz's score, we also need to fix the
            # exemption score
            evaluation, created = Evaluation.objects.get_or_create(
                    name=quiz.name, course=course)
            evaluation.quiz_update_out_of(quiz)
            return redirect('quiz_admin', course_pk=course_pk, quiz_pk=quiz.pk)
    else:
        form = QuizForm(instance=quiz)
        return render(
            request, 
            'quizzes/generic_form.html', 
            { 'form' : form,
              'header': 'Edit Quiz',
              'course': quiz.course,
            }
        )

@login_required
def list_quizzes(request, course_pk, message=''):
    """ Show the list of all quizzes, including the live ones. Includes an adminstrative
    portion for staff. Can be redirected to when max-attempts on a live quiz is reached
    <<Input>> 
    course_pk (Integer) Primary key for the course
    message (String) default = '' A message to return to the student
    TODO: Need to add new row level privileges
    """
    course = get_object_or_404(Course, pk=course_pk)
    all_quizzes = Quiz.objects.filter(course=course)


    if request.user.has_perm('can_edit_quiz', course):
        all_quizzes_table = AllQuizTable(all_quizzes)
        RequestConfig(request, paginate={'per_page', 10}).configure(all_quizzes_table)
    else:
        all_quizzes_table = ''

    live_quiz   = all_quizzes.filter(live__lte=timezone.now(), expires__gt=timezone.now())

    # Get this specific user's previous quiz results
    student_sqrs = StudentQuizResult.objects.select_related(
        'quiz', 'quiz__course').filter(
            student=request.user,
            quiz__course=course).order_by('quiz')
    # Now we need to filter these according to whether the solutions_are_visible
    # property is true on each quiz
    student_sqrs = [sqr for sqr in student_sqrs if sqr.quiz.solutions_are_visible]
    student_quizzes = SQRTable(student_sqrs)
#    student_quizzes = SQRTable(
#        StudentQuizResult.objects.select_related(
#            'quiz', 'quiz__course').filter(
#                student=request.user,
#                quiz__course=course).order_by('quiz')
#    )
    RequestConfig(request, paginate={'per_page': 10}).configure(student_quizzes)

    return render(request, 'quizzes/list_quizzes.html', 
            {'live_quiz': live_quiz, 
             'all_quizzes': all_quizzes,
             'student_quizzes': student_quizzes,
             'all_quizzes_table': all_quizzes_table,
             'message': message,
             'course': course,
            });

@staff_required()
def quiz_admin(request, course_pk, quiz_pk):
    """ Generates the quiz administration page.
        <<Input>>
        course_pk, quiz_pk (Integers) The primary keys for the course and quiz
        respectively.
        TODO: Change access dependencies to new row privileges.
    """

    quiz      = get_object_or_404(Quiz,pk=quiz_pk)

    if not request.user.has_perm('can_edit_quiz', quiz.course):
        return HttpResponseForbidden("You are not authorized to see this.")

    questions = MarkedQuestionTable(quiz.markedquestion_set.all())
    RequestConfig(request, paginate={'per_page': 10}).configure(questions)
#    questions = quiz.markedquestion_set.all()

    return render(request, 'quizzes/quiz_admin.html',
        { 'quiz': quiz,
          'questions': questions,
        }
    )

@staff_required()
def edit_quiz_question(request, course_pk, quiz_pk, mq_pk=None):
    """ View designed to add/edit a question. If mq_pk is None then we make the
        question, otherwise we design the form to be edited.
    """
    quiz = get_object_or_404(Quiz.objects.select_related('course'), pk=quiz_pk)

    if not request.user.has_perm('can_edit_quiz', quiz.course):
        return HttpResponseForbidden("You are not authorized to see this.")

    if mq_pk is None: # Adding a new question, so create the form.
        if request.method == "POST":
            form = MarkedQuestionForm(request.POST)
            if form.is_valid():
                mquestion = form.save(commit=False)
                mquestion.update(quiz)
                # Also update the exemption score, if necessary
                evaluation, created = Evaluation.objects.get_or_create(
                        name=mquestion.quiz.name, course=mquestion.quiz.course)
                evaluation.quiz_update_out_of(mquestion.quiz)
                return redirect('edit_choices', course_pk=course_pk, quiz_pk=quiz_pk, mq_pk=mquestion.pk)
        else:
            form = MarkedQuestionForm()
    else: # Editing a question, so populate with current question
        mquestion = get_object_or_404(MarkedQuestion, pk=mq_pk)
        if request.method == "POST":
            form = MarkedQuestionForm(request.POST, instance=mquestion)
            if form.is_valid():
                mquestion = form.save(commit=False)
                mquestion.update(quiz)
                mquestion.quiz.update_out_of()
                # Also update the exemption score, if necessary
                evaluation, created = Evaluation.objects.get_or_create(
                        name=mquestion.quiz.name, course=mquestion.quiz.course)
                evaluation.quiz_update_out_of(mquestion.quiz)

                # Check to see if there are any possible issues with the format of the question
                return redirect('quiz_admin', course_pk=course_pk, quiz_pk=quiz.pk)
        else:
            form = MarkedQuestionForm(instance=mquestion)

    sidenote = """
    <h4> Notes </h4>
    <ul class="mathrender">
        <li>LaTeX brackets must be double bracketed. For example, <code> e^{{ {v[0]} x}}</code>
        <li>You may use mathematical symbols, such as +,-,*,/ in your answer.
        <li>Exponentiation is indicated by using a**b; for example, \(2^3\) may be entered as 2**3
        <li>You may use the functions \(\sin, \cos,\\tan, \ln\) in your answer.
        <li>You may use the constants pi and e for  \(\pi\)  and \(e\).
        <li>You may use the python math package in your functions. For example, <code>{"f": lambda x: math.sqrt(x) }</code>
        <li> Use 'rand(-5,10)' to create a random integer in the range [-5,10] (inclusive). Use 'uni(-1,1,2)' to create a real number in [-1,1] with 2 floating points of accuracy
    </ul>"""

    return render(request, 'quizzes/generic_form.html', 
        { 'form': form,
          'sidenote': sidenote,
          'header': "Create Quiz Question",
        }
    )

def deserialize(s_str):
    """ Helper function. Takes a string which embodies a list of choices for the variable
        inputs and returns the python object.
        <<Input>>
        s_str (String) - A string serializing the list of choices
        <<Output>>
        list object which contains the possible choices.
    """

    if s_str is None:
        return []

    prelist = s_str.replace(' ','') # Kill all extra whitespace
    split_list = prelist.split(';') # Semi-colons separate list elements
    choices = []
    for index, sublist in enumerate(split_list):
        choices.append(sublist.split(',')) # Commas separate elements which each list

    return choices

def choice_is_valid(string, num_vars):
    """ Determine whether input string is a valid choice; that is, either an integer or
        a correctly formatted randomization string.
        Input: string (String) - to be validated
               num_vars - (Integer) - necessary number of variables
        Output: Boolean - indicating whether the string is valid
                err_msg - error message
    """
    parts = string.replace(' ', '').split(';')
    return_value = True
    error_message = "Choice is valid"

    if len(parts) != num_vars:
        return False, "Incorrect number of variables. Given {}, expected {}".format(len(parts), num_vars)

    # We run the function parse_abstract_choice. If it works then the input is valid, otherwise it's not
    try:
        parse_abstract_choice(string)
    except:
        error_message = "Invalid input. Please insert the current number of variables, with appropriate range."
        return_value = False

#    for part in parts:
#        match = re.match(r'[zZ](-?\d+),(-?\d+)',part)
#        if isnumber(part):
#            return_value*= True
#        elif match:
#            if int(match.group(1))<int(match.group(2)):
#                return_value*= True
#            else:
#                return_value*= False
#                error_message = "Integer range out of order."
#        else:
#            error_message = "Invalid input. Please insert the current number of variables, with appropriate range."
#            return_value*= False
    return return_value, error_message


def isnumber(string):
    try:
        float(string)
        return True
    except:
        return False

def edit_choices(request, course_pk, quiz_pk, mq_pk):
    """ After adding/editing a MarkedQuestion object, we need to specify the
        choices, which indicates what types of values can be substituted into
        the variables {v[i]}. 
        View which handles the ability to add/edit choices.
        <<Input>>
        course_pk, quiz_pk (Integers) Not really needed, but for consistent urls
        mq_pk (integer) the marked question primary key
    """

    mquestion = get_object_or_404(
        MarkedQuestion.objects.select_related('quiz','quiz__course'), 
        pk=mq_pk
    )
    error_message = ''

    if not request.user.has_perm('can_edit_quiz', mquestion.quiz.course):
        return HttpResponseForbidden("You are not authorized to see this.")

    if request.method == "POST":
        form_data = request.POST
        try:
            updated_choices = ''
            # On post, we go through all the current choices and update them
            for field, data in form_data.items():
                if 'choice' in field:
                    cur_choice = form_data[field]
                    
                    # If cur_choice is empty, it's likely a delete-submission, so we skip it
                    if cur_choice == '':
                        continue

                    # Verify that our choices are correctly formatted
                    is_valid, msg = choice_is_valid(cur_choice, mquestion.num_vars)
                    if is_valid:
                        # We do not want extraneous semi-colons, so we have to check to see if we are
                        # first element of updated choices
                        if len(updated_choices) == 0:
                            updated_choices = cur_choice
                        else:
                            updated_choices = updated_choices + ":" + cur_choice
                    else:
                        raise Exception(msg)

            mquestion.choices = updated_choices
            mquestion.save()
        except Exception as e:
            error_message = e
            print(e)

    if mquestion.choices is None or mquestion.choices == "":
        choices = ""
    else:
        choices = mquestion.choices.split(":")

    return render(request, 'quizzes/edit_choices.html',
            {
                "mquestion": mquestion,
                "choices": choices,
                "error_message": error_message,
            })

@staff_required()
def search_students(request, course_pk):
    """ AJAX view for searching for a student's records.
    """
    try:
        course = get_object_or_404(Course, pk=course_pk)
        if not request.user.has_perm('can_edit_quiz', course):
            return HttpResponseForbidden('Insufficient privileges')

        if 'query' in request.GET:
            query = request.GET['query']

            fields = ["username__contains", "first_name__contains", "last_name__contains",]
            queries = [Q(**{f:query}) for f in fields]
            qs = Q()
            for query in queries:
                qs = qs | query

            # Filter by course as well
            users = User.objects.filter(
                    qs, membership__courses__in=[course]).prefetch_related(
                    'membership','membership__courses').distinct()
            ret_list = users[0:10]
#            for user in users:
#                try:
#                    if course in user.membership.courses.all():
#                        ret_list.append(user)
#                except Exception as e:
#                    continue #membership might not exist

            return render(request, 'quizzes/search_students.html',
                { 'users': ret_list,
                  'course_pk': course_pk,
                }
            )

    except Exception as e:
        print(str(e))
        raise Http404('Invalid request type')

@staff_required()
def student_results(request, course_pk, user_pk):
    course = get_object_or_404(Course, pk=course_pk)

    if not request.user.has_perm('can_edit_quiz', course):
        return HttpResponseForbidden('Insufficient Privileges')
    student = get_object_or_404(User, pk=user_pk)
    # Get this specific user's previous quiz results
    student_quizzes = SQRTable(
        StudentQuizResult.objects.select_related(
            'quiz', 'quiz__course').filter(student=student).order_by('quiz')
    )
    RequestConfig(request, paginate={'per_page': 10}).configure(student_quizzes)

    return render(request, 'quizzes/student_results.html', 
            { 'student_quizzes': student_quizzes,
              'course': course,
              'student': student,
            });

# ---------- Quiz Add/Edit/Admin (end) ---------- #

# ---------- Quiz Handler (fold) ---------- #

@login_required
def start_quiz(request, course_pk, quiz_pk):
    """ View to handle when a student begins a quiz. 
        <<Input>>
        quiz_pk (integer) - corresponding to the primary key of the quiz
        <<Output>>
        HttpResponse object. Renders quizzes/start_quiz.html or redirects 
                                     to display_question

        Depends on: generate_next_question
    """

    this_quiz = get_object_or_404(
            Quiz, 
            pk=quiz_pk, 
            live__lte=timezone.now(), 
            expires__gt=timezone.now())
    
    # Get the StudentQuizResults corresponding to this student. If there are
    # none, this is the first try. If there are some, we need to find the most
    # current one (ie the one with the largest `attempt' attribute. Then we need
    # to check if that StudentQuizResult is still in progress, or if a new
    # attempt needs to be created. In the latter, we also need to check that the
    # student has not surpassed the number of attempts permitted
    student = request.user
    quiz_results = StudentQuizResult.objects.filter(
            student=student, quiz=this_quiz).select_related(
                'quiz', 'quiz__course')
    high_score = -1
   
    # The user may be allowed several attempts. We need to determine what attempt the 
    # user is on, and whether they are in the middle of a quiz
    is_new = False;
    if len(quiz_results) == 0: # First attempt
        # Should be made into an SQR manager method
        #cur_quiz_res = StudentQuizResult( student=student, quiz=this_quiz, attempt=1, score=0, result='{}',cur_quest = 1)
        #cur_quiz_res.save()
        cur_quiz_res = StudentQuizResult.create_new_record(student,this_quiz)
        generate_next_question(cur_quiz_res)
        is_new = True
    else: 
        # Determine the most recent attempt by finding the max 'attempt'
        quiz_aggregate = quiz_results.aggregate(Max('attempt'), Max('score'))
        most_recent_attempt = quiz_aggregate['attempt__max']
        high_score = quiz_aggregate['score__max']
        cur_quiz_res = quiz_results.get(attempt=most_recent_attempt)
        # Now we need to check if this attempt was finished. Recall that if cur_quest = 0
        # then all questions are finished. If all questions are finished, we must also check
        # if the student is allowed any more attempts
        if (cur_quiz_res.cur_quest == 0): # Current attempt is over.
            if (most_recent_attempt < this_quiz.tries or this_quiz.tries == 0): # Allowed more tries
                # Should be made into an SQR manager method
                #cur_quiz_res = StudentQuizResult(student=student, quiz=this_quiz, attempt=most_recent_attempt+1,score=0,result='{}',cur_quest=1)
                #cur_quiz_res.save()
                cur_quiz_res = StudentQuizResult.create_new_record(
                    student, this_quiz, most_recent_attempt+1)
                generate_next_question(cur_quiz_res) #Should make this a model method
                is_new = True
            else: # No more tries allowed
                message = "Maximum number of attempts reached for {quiz_name}.".format(quiz_name=this_quiz.name)
                return list_quizzes(request, course_pk=course_pk, message=message) # Returns a view

    # Need to genererate the first question
    return render(request, 'quizzes/start_quiz.html', 
            {'record': cur_quiz_res, 
             'quiz': this_quiz,
             'high_score': high_score,
             })

def eval_sub_expression(string, question):
    """ Used to evaluate @-sign delimited subexpressions in sentences which do
        not totally render. Variables should be passed into the string first,
        before passing to this function.  For example, if a string is if the
        form: "What is half of \(@2*{v[0]}@\)" then we should have already
        substituted {v[0]} into the string, so that eval_sub_expression
        receives, for example, "What is half of \(@2*3@\)?"
    
        <<INPUT>>
        string (String) containing (possibly zero) @-delimited expressions.
        question (MarkedQuestion) object. Contains the user-defined functions,
        so we need them
        <<OUTPUT>>
        That string, but with the @ signs removed and the internal expression
        evaluated.
    """

    # If no subexpression can be found, simply return
    if not "@" in string:
        return string

    temp_string = string
    pattern = re.compile(r'@(.+?)@')
    functions = eval(question.functions)
    functions.update(settings.PREDEFINED_FUNCTIONS)
    try:
        while "@" in temp_string:
            match = pattern.search(temp_string)
            # Evaluate the expression and substitute it back into the string
            replacement = round(
                simple_eval(match.group(1),
                    names=settings.UNIVERSAL_CONSTANTS, 
                    functions=functions
                )
            ,4)
            temp_string = temp_string[:match.start()] + str(replacement) + temp_string[match.end():]

    except Exception as e: # Should expand the error handling here. What can go wrong?
        raise e

    return temp_string

def sub_into_question_string(question, choices):
    """ Given a MarkedQuestion object and a particular choice set for the
        variables {v[0]}=5, {v[1]}=-10, etc, substitute these into the problem
        and return the string.
        <<INPUT>
        question (MarkedQuestion) object 
        choices (string) for the choices to insert into the question text. For
            example, if question.problem_str has variables {v[0]} and {v[1]},
            then choices should be something of the form "5;-10", in which case
            we make the substitution {v[0]} = 5, {v[1]} = -10.
        <<OUTPUT>> 
        A string rendered correctly.

        Depends on: eval_sub_expression 
    """
    problem = question.problem_str # Grab the question string
    # Remove any troublesome white space, and split the choices (delimited by a
    # semi-colon). Then substitute them into the sring.
    problem = problem.format(v=choices.replace(' ', '').split(';'))

    # Pass the string through the sub-expression generator
    problem = eval_sub_expression(problem, question)
    return problem

def mark_question(sqr, string_answer, accuracy=10e-5):
    """ Helper question to check if the answers are the same. Updates SQR
        internally and returns a boolean flag indicating whether this is the
        last question.
        <<INPUT>>
        sqr (StudentQuizResult) - the quiz record
        string_answer (string) - the correct answer
        accuracy (float) - The desired accuracy. Default is 10e-5;
            that is, four decimal places.
        <<OUTPUT>>
        is_last (Boolean) - indicates if the last question has been marked
    """
    # Result is a python dict, qnum is the attempt of the quiz
    result, qnum = sqr.get_result() 

    # Already the last question, so don't check anything and return true
    if qnum == '0':
        return True

    correct = result[qnum]['answer']

    # For multiple choice questions, we do not want to evaluate, just compare strings
    if result[qnum]['type'] == "MC":
        if str(correct) == string_answer:
            result[qnum]['score']='1'
            sqr.update_score()
        else:
            result[qnum]['score']='0'

        result[qnum]['guess']        = string_answer 
        result[qnum]['guess_string'] = string_answer 

    else:
        correct = float(correct) # Recast to float for numeric comparison
        
        try:
            guess = round(
                simple_eval(
                    string_answer, 
                    names=settings.UNIVERSAL_CONSTANTS, 
                    functions=settings.PREDEFINED_FUNCTIONS
                ),
            4) #numeric input, rounds to 4 decimal places
            result[qnum]['guess'] = guess
            result[qnum]['guess_string'] = string_answer
        except Exception as e:
            raise ValueError('Input could not be mathematically parsed.')

        if (abs(correct-guess)<accuracy): # Correct answer
            result[qnum]['score']='1'
            sqr.update_score()
        else:
            result[qnum]['score']='0'

    sqr.update_result(result)
    is_last = sqr.add_question_number()
    return is_last

def generate_next_question(sqr):
    """ Given a StudentQuizResult, creates a new question. Most often this
        function will be called after a question has been marked and a new one
        needs to be created. However, it is also used to instantiate the first
        question of a quiz.  
        <<INPUT>>
        sqr (StudentQuizResult) contains all the appropriate information for
            generating a new question 
        <<OUTPUT>>
        q_string (String)  The generated question, formated in a math renderable
            way 
        mc_choices (String) The multiple choice options

        Depends on: get_mc_choices, sub_into_question_string
    """
    result, qnum = sqr.get_result()
    # The following is defined so it can be returned, but is only ever used if
    # question type is MC
    mc_choices = ''

    # the cur_quest value of sqr should always correspond to the new question,
    # as it is updated before calling this function. We randomly choose an
    # element from quiz.category = sqr.cur_quest, and from that question we then
    # choose a random choice, possibly randomizing yet a third time of the
    # choices are also random
    try:
        question = sqr.quiz.get_random_question(sqr.q_order[sqr.cur_quest-1])
    except IndexError as e:
        print(e)

    # From this question, we now choose a random input choice
    a_choice = question.get_random_choice()

    # This choice could either be a tuple of numbers, a randomizer, or a mix. We
    # need to parse these into actual numbers
    choices = parse_abstract_choice(a_choice)
    answer = get_answer(question, choices)

    #Feed this into the result dictionary, and pass it back to the model
    result[qnum] = {
            'pk': str(question.pk),
            'inputs': choices,
            'score': '0',
            'answer': answer,
            'guess': None,
            'type': question.q_type
            }
    
    # If the question we grabbed is multiple choice, then we must also generate
    # the multiple choice options.
    if question.q_type == "MC":
        mc_choices = get_mc_choices(question, choices, answer)
        result[qnum].update({'mc_choices': mc_choices})
    
    sqr.update_result(result)

    return sub_into_question_string(question,choices), mc_choices

def get_mc_choices(question, choices, answer):
    """ Given a question and a choice for the variable inputs, get the multiple
        choice options.
        <<INPUT>>
        question (MarkedQuestion)
        choices  (String) corresponding to the concrete choices for the v[0],...,v[n]
        answer   (String) to concatenate to the choices list
        <<OUTPUT>> 
        A list of strings with numeric values. For example ['13', '24', '52.3',
            'None of the above']

        ToDo: Allow for @-sign based delimeter expressions. May want to do this
        based on the exception raised on simple_eval
    """
    split_choices = choices.split(';')
    mc_choices = []

    for part in question.mc_choices.split(';'):
        """ Internal flow: See if variables are present. If so, substitute the
            variables. If not, it's hard coded.  If we do not find variables but
            cannot evaluate, the answer is a sentence/word. So just append it.
        """
        if re.findall(r'{v\[\d+\]}', part): # matches no variables
            part = part.format(v=split_choices)
            part = eval_sub_expression(part, question)

        try:
            # Remove troublesome whitespace as well
            eval_string = part.replace(' ','')
            value = round(
                simple_eval(
                    eval_string, 
                    functions=settings.PREDEFINED_FUNCTIONS,
                    names=settings.UNIVERSAL_CONSTANTS
                ),
            4)
                
            mc_choices.append(str(value))
        except: #If not an exectuable string, then it must be a hardcoded answer
            mc_choices.append(part)

    mc_choices.append(str(answer))

    # Now shuffle them.
    random.shuffle(mc_choices)

    return mc_choices

def parse_abstract_choice(abstract_choice):
    """ Parses an abstract choice into a concrete choice. Expects a single
        choice input. Currently can only handle integer ranges.
        <<INPUT>>
        abstract_choice (String) - Used to indicate an abstract choice,
            separated by ';'
        <<OUTPUT>>
        (String) A concrete choice 
    """
    choice = ''
    for part in abstract_choice.replace(' ', '').split(';'):
        if isnumber(part): # If already a number
            choice += part + ";"
        else: # it must be a command, one of 'rand' or 'uni'
            pre_choice = simple_eval(
                part, 
                names=settings.UNIVERSAL_CONSTANTS,
                functions=settings.PREDEFINED_FUNCTIONS
            )
            choice += str(pre_choice)+";"

#        elif part[0] in 'zZ':
#            lower, upper = [int(x) for x in part[1:].split(',')]
#            if upper==lower: # Ensures we can't accidentally enter an infinite loop on Z0,0
#                concrete = str(upper) + ";"
#            else:
#                concrete = random.randint(lower,upper)
#                if part[0].istitle(): # Range specifies non-zero number using capital letter
#                    while concrete == 0:
#                        concrete = random.randint(lower,upper)
#            choice += str(concrete) + ";"

    # At the end, we need to cut off the trailing semi-colon
    return choice[0:-1]

def get_answer(question, choices):
    """ Evaluates the mathematical expression to compute the answer.
        <<INPUT>>
        question (MarkedQuestion) The object containing the question
        choices (String) String containing *concrete* choices
        <<OUTPUT>>
        (Integer)  The answer, to be saved

        Depends: simpleeval.simple_eval
    """
    answer = question.answer
    if choices is None:
        return answer
    if re.findall(r'{v\[\d+\]}', answer): # matches no variables
        answer = answer.format(v=choices.split(';'))
        answer = eval_sub_expression(answer, question)

    try:
        # Substitute the variables into the string and evaluate the functions dictionary
#        eval_string = answer.format(v=choices.split(';'))
        # Remove whitespace before evaluating
        eval_string = answer.replace(' ', '')
        functions = eval(question.functions)
        functions.update(settings.PREDEFINED_FUNCTIONS)

        return round(
            simple_eval(
                eval_string, 
                functions=functions, 
                names=settings.UNIVERSAL_CONSTANTS
            ),
        4)
    except (SyntaxError, NameNotDefined,) as e:
        # Enter this exception if the answer is not one that can be evaluated.
        # In that case, the answer is just the answer
#        if question.q_type == "MC":
#            return answer
#        else:
#            raise e
        return answer

    except Exception as e: 
        raise e

@login_required
def display_question(request, course_pk, quiz_pk, sqr_pk, submit=None):
    """ When a student accesses a quiz, there is a redirect to this view which
        shows the current question quiz-question. This view also handles the
        submission of an answer, checking the correct answer and generating
        either the next question or the results page. 
        <<INPUT>>
        sqr_pk (integer) indicating the StudentQuizResult primary key
        submit (Boolean default:None) Checks if the student is seeing the
            question (None/False) or has submitted an answer that we need to
            grade (True)
        <<OUTPUT>>
        HttpResponse - renders the quiz question

        <<DEPENDS>> 
          sub_into_question_string, mark_question,
          generate_next_question, update_marks
    """
    sqr = StudentQuizResult.objects.select_related('quiz','quiz__course').get(pk=sqr_pk)
    string_answer = ''
    error_message = ''
    mc_choices = None
    # Start by doing some validation to make sure only the correct student has
    # access to this page
    if sqr.student != request.user:
        return HttpResponseForbidden(
            'You are not authorized to see this question')

    # submit=None means the student is just viewing the question and hasn't
    # submitted a solution. In this case, simply render the question.
    if submit is None:
        result, qnum = sqr.get_result()
        # If qnum is 0, then the quiz is finished. In this case, render the
        # results page.
        if qnum == '0':
            result_table = get_result_table(sqr.result)
            return render(request, 'quizzes/completed_quiz.html', 
                { 'sqr': sqr,
                  'result_table': result_table,
                }
            )
         
        # Otherwise, pick out the current question and its multiple choice
        # answers (if applicable).
        # result[qnum] has fields (MarkedQuestion) pk, inputs, score, type,
        # (mc_choices)
        question = MarkedQuestion.objects.get(pk=int(result[qnum]['pk']))
        choices  = result[qnum]['inputs']
        # Input the choices into the question string
        q_string = sub_into_question_string(question, choices)
        
        if result[qnum]['type'] == "MC":
            mc_choices = result[qnum]['mc_choices']
    # Information was submitted, so verify that the input is correctly
    # formmated, mark the question, and either return the results page (if done)
    # or generate the next question.
    else: 
        # The page was either refreshed or the table with the results was sorted
        if request.method == "GET": 
            result_table = get_result_table(sqr.result)
            RequestConfig(request, paginate={'per_page', 10}).configure(result_table)
            return render(request, 'quizzes/completed_quiz.html', 
                { 'sqr': sqr,
                  'result_table': result_table,
                }
            )

        # Grab the question string in case we need to return the question on
        # error Note: I need to provide the above line with a default. If
        # sometimes throws an error for some reason. Also need to track down
        # this bug
        q_string = request.POST['problem'] 
        try:
            string_answer = request.POST['answer'] #string input
            # Mark the question. If it's the last question, is_last = True and
            # we generate the results page
            is_last = mark_question(sqr, string_answer)

            if not is_last: 
                # There are more questions, so generate the next one
                q_string, mc_choices = generate_next_question(sqr)
                string_answer = ''
            else: 
                # The quiz is over, so generate the result table. Also, update
                # the student mark
                result_table = get_result_table(sqr.result)
                # We are not tracking marks, so this is commented out
                update_marks(sqr) # Call a helper method for updating the student's marks 
                RequestConfig(request, paginate={'per_page', 10}).configure(result_table)
                return render(request, 'quizzes/completed_quiz.html', 
                        {   'sqr': sqr,
                            'result_table': result_table,
                        })
                        
#            # For MC, this is ajax, so check
#            if request.is_ajax():
#                if not is_last:
#                    return_data = {'next_url': reverse('display_question', args=(sqrpk,))}
#                else:
#                    return_data = 
#                return HttpResponse(json.dumps(return_data))

        except ValueError as e:
            error_message =  ("The expression '{}' did not parse to a valid"
                " mathematical expression. Please try"
                " again").format(string_answer)
            # Technically if we get here, we do not have the mc_choices to
            # return if it was a multiple choice question; however, this should
            # never happen as it should be impossible to pass a bad input with
            # mc

    return render(request, 'quizzes/display_question.html', 
        { 'sqr': sqr,
          'question': q_string, 
          'error_message': error_message,
          'string_answer': string_answer,
          'mc_choices': mc_choices,
         }
    )

def update_marks(quiz_result):
    """ Helper function for updating quiz marks once a quiz has been completed.
        Input: quiz_record (StudentQuizResult)
    """
    try:
        evaluation, cr = Evaluation.objects.get_or_create(
                name=quiz_result.quiz.name, course=quiz_result.quiz.course)
        # Should rarely need to be triggered, but if a quiz was imported without
        # creating an evaluation, the first student who writes it will create the
        # evaluation. Hence we also need to update the out_of
        if cr: 
            evaluation.quiz_update_out_of(quiz_result.quiz)
        cur_grade, created = StudentMark.objects.get_or_create(
                        user = quiz_result.student,
                        evaluation = evaluation
                    )
        cur_grade.set_score(quiz_result.score, 'HIGH')
    except Exception as e:
        print(e)

def get_result_table(result):
    """ Turns the string StudentQuizResults.results and generated a table.
        <<INPUT>>
        result (string) serialized JSON object to be converted to a table
        <<OUTPUT>
        QuizResulTable populated with the data.
    """
    
    ret_data = []
    res_dict = json.loads(result)
    for field, data in res_dict.items():
        part = {'q_num': field, 
                'correct': str(data['answer']), 
                'guess': str(data['guess']),
                'score': data['score']}
        ret_data.append(part)
    
    return QuizResultTable(ret_data)

@staff_required()
def test_quiz_question(request, course_pk, quiz_pk, mq_pk):
    """ Generates many examples of the given question for testing purpose.
        Input: mpk (Integer) MarkedQuestion primary key

        Depends on: sub_into_question_string, render_html_for_question
    """
    mquestion = get_object_or_404(
            MarkedQuestion.objects.select_related('quiz', 'quiz__course'), 
            pk=mq_pk)

    if not request.user.has_perm('quizzes.can_edit_quiz', 
            mquestion.quiz.course):
        return HttpResponseForbidden('You are not authorized to test this.')
        

    if request.method == "POST": # Testing the question
        num_tests = request.POST['num_tests']
        html = ''

        try:
            for k in range(0,int(num_tests)):
                choice = parse_abstract_choice(mquestion.get_random_choice())
                answer = get_answer(mquestion, choice)

                if mquestion.q_type == "MC":
                    mc_choices = get_mc_choices(mquestion, choice, answer)
                else:
                    mc_choices = ''

                problem = sub_into_question_string(mquestion, choice)
                
                html += render_html_for_question(problem, answer, choice, mc_choices)
                # Should add better error handling here.
        except KeyError as e:
            html = ("Key Error: Likely an instance of single braces '{{,'}} when"
            " double braces should have been used. See the code<br>"
            " '{{ {} }}'").format(str(e))
        except AttributeError as e:
            html = ("Attribute Error: Likely you falied to close a @..@ group"
                    " or have an unbalanced @ group. See the code <br>"
            " '{{ {} }}'").format(str(e))
        except SyntaxError as e:
            html = ("Syntax Error: Evaluation failed. Did you forget to "
                    "use an arithmetic operator? <br>"
                    " '{{ {} }}'").format(str(e))

        except Exception as e:
            html = e

        return HttpResponse(html)

    else:
        return render(request, 'quizzes/test_quiz_question.html',
                {'mquestion':mquestion,
                })

def render_html_for_question(problem, answer, choice, mc_choices):
    """ Takes in question elements and returns the corresponding html.
        Input: problem (String) The problem 
               answer  (float) the correct answer
               choice  (String) a ';' separated tuple of variable choices
               mc_choices (string) a list of multiple choice options
    """

    template = """
               <div class = "mathrender quiz-divs question-detail">
                   {problem}
               </div>
               
               <ul>
                   <li><b>Answer:</b> {answer}
                   <li><b>Choice:</b> {choice}
               </ul>
               """.format(problem=problem, answer=answer, choice=choice)
    if mc_choices:
        template += "<ul>\n"
        for choice in mc_choices:
            template+= "<li>{choice}</li>\n".format(choice=choice)

        template +="</ul>\n"

    return template

@login_required
def quiz_details(request, course_pk, quiz_pk, sqr_pk):
    """ A view which allows students to see the details of a
        completed/in-progress quiz.  
        <<INPUT>>
        course_pk, quiz_pk, sqr_pk (Int) Primary keys

    Depends on: sub_into_question_string
    """

    quiz_results = get_object_or_404(
        StudentQuizResult.objects.select_related('quiz', 'quiz__course'), 
        pk=sqr_pk)
    quiz = quiz_results.quiz
    course = quiz.course

    # Ensure you're looking at your own results, or your an admin
    if not ( (request.user == quiz_results.student) 
                or
             (request.user.has_perm('can_edit_quiz', course))
           ):
        return HttpResponseForbidden()

    # Next ensure that you are allowed to see the results
    if not (quiz.solutions_are_visible or 
        request.user.has_perm('quizzes.can_edit_quiz', course) ):
        raise Http404('Solutions are unavailable at this time')

    result_dict = quiz_results.get_result()[0]
    template = """
    <li> 
        <div class = "mathrender question-detail">
            {problem}
        </div>
        {correct}
        <ul>
            <li><b>Correct Answer</b>: <span class="mathrender">{answer}</span>
            <li><b>Your Answer</b>: <span class="mathrender">&quot;{guess_string}&quot; evaluated to {guess}</span>
        </ul>
    """

    #Generate the return html
    return_html = ""
    for qnum in range(1,len(result_dict)+1):
        temp_dict = result_dict[str(qnum)]

        #Check to see if the question has been answered. If not, skip it
        if 'guess_string' not in temp_dict:
            continue

        mquestion = MarkedQuestion.objects.get(pk = temp_dict['pk'])

        problem = sub_into_question_string(mquestion, temp_dict['inputs'])

        if int(temp_dict['score']):
            correct = "<p style='color:green'>Correct</p>"
        else:
            correct = "<p style='color:red'>Incorrect</p>"
        
        return_html += template.format(problem=problem, 
                                       correct=correct,
                                       answer=temp_dict['answer'],
                                       guess_string=temp_dict['guess_string'],
                                       guess=temp_dict['guess'])

    # return_html only has body. Need to wrap on ordered-list
    return_html = "<ol> {} </ol>".format(return_html)
    return render(request, 'quizzes/quiz_details.html',
            {'return_html': return_html,
             'sqr': quiz_results,
             'course': course,
            })
            
# ---------- Quiz Handler (end) ---------- #

# ---------- Quizzes (end) ---------- #

# ---------- Course Administration (fold) ----------- #

def generate_redirect_string(name, url):
    """ Shortcut for generating the redirect html to be inserted into
    success.html
    """
    return "<a href={}>Return to {}</a>".format(url,name)

def create_course(request):
    """ View for generating and handling the create course form. This form asks
    for the name of the course, and the default administrator. The view must
    handle setting the administrator.
    """
    if not request.user.is_superuser:
        return HttpResponseForbidden("You are not authorized to create a course")

    if request.method == "POST": # Form returned filled in
        form = CourseForm(request.POST)
        if form.is_valid():
            course = form.save()
            # If a default admin has been specified, add them
            username = request.POST['default_admin']
            success_string = "Course {} successfully created".format(
                    course.name )
            if username:
                course.add_admin(username)
                success_string += "<br>User {} added as default admin".format(
                        username)
            redirect_string = generate_redirect_string(
                    'Administration', reverse('quiz_admin') )

            return render(request,
                    'quizzes/success.html',
                    { 'success_string': success_string,
                      'redirect_string' : redirect_string,
                    }
                )
    else: # request method is GET, so seeing page for the first time
        form = CourseForm()

        return render(request, 'quizzes/generic_form.html', 
                {'form': form,
                 'header': "Create Course"
                }
            )

def add_staff_member(request):
    """ Add staff members to a course """
    # Populate the form with list of courses 
    courses = get_objects_for_user(request.user, 'quizzes.can_edit_quiz')
    if request.method == "POST":
        form = StaffForm(request.POST)
        course_pk = int(request.POST['course'])
        username  = request.POST['username']

        course = Course.objects.get(pk=course_pk)
        course.add_admin(username)

        redirect_string = generate_redirect_string(
            'Administrative', reverse('quiz_admin') )
        success_string = ("User {} successfully added to course {} "
           "with {} privileges").format(
               username, course.name, "staff")

        return render(request, 'quizzes/success.html',
            { 'success_string': success_string,
              'redirect_string': redirect_string,
            }
        )
    else:
        form = StaffForm(queryset=courses)
        return render(request, 'quizzes/generic_form.html',
            { 'form': form,
              'header': "Add Staff Member",
            }
        )

def add_students(request):
    # Populate the form with list of courses 
    courses = get_objects_for_user(request.user, 'quizzes.can_edit_quiz')
    sidenote = ("Upload a csv file whose rows are the UTORid's of the "
        "students you wish to add to this course")
    if request.method == "POST":
        form = AddStudentsForm(request.POST, request.FILES, queryset=courses)

        if form.is_valid():
            # Get the course
            course_pk = int(request.POST['course'])
            course = Course.objects.get(pk=course_pk)
            # Save the file to make it easier to read from later
            csv_file = form.save()

            # Read through the CSV file 
            with open(csv_file.doc_file.path, 'rt') as the_file:
                for row in csv.reader(the_file):
                    username = row[0]
                    user, _ = User.objects.get_or_create(username=username)
                    # Get the membership and add this course to that
                    membership, _ = UserMembership.objects.get_or_create(user=user)
                    membership.courses.add(course)

            redirect_string = generate_redirect_string(
                'Administrative', reverse('quiz_admin') )
            success_string = "Students successfully added to course {} ".format(
                   course.name)

            return render(request, 'quizzes/success.html',
                { 'success_string': success_string,
                  'redirect_string': redirect_string,
                }
            )

        return render(request, 'quizzes/generic_form.html',
            { 'form': form,
              'header': "Add Students to Course",
              'sidenote': sidenote,
            }
        )
    else:
        form = AddStudentsForm(queryset=courses)
        return render(request, 'quizzes/generic_form.html',
            { 'form': form,
              'header': "Add Students to Course",
              'sidenote': sidenote,
            }
        )

@login_required
def course_search(request):
    """ AJAX view for searching for open enrollment courses. GET should contain
    'query' 
    """
    if request.method == "GET":
        query = request.GET['query']
        
        courses = Course.objects.filter(
            open_enrollment=True, name__contains=query)[:10]
        membership = UserMembership.objects.get(user=request.user)

        return render(request, 'quizzes/course_search.html',
            { 'courses': courses,
              'membership': membership
            }
        )

@login_required
def enroll_course(request):
    """ AJAX view for enrolling a student in an open enrollment course
    """

    if request.method == "POST":
        course_pk = int(request.POST['course_pk'])
        course = get_object_or_404(Course, pk=course_pk)
        if course.open_enrollment:
            membership, _ = UserMembership.objects.get_or_create(user=request.user)
            membership.courses.add(course)
            response_data = {'response': 'success'}
        else:
            response_data = {'response': 'Course does not permit open enrollment'}
    else:
        response_data = {'response': 'Invalid HTTP request'}

    return HttpResponse(json.dumps(response_data))

# --------- Course Administration (end) ------- #


# --------- Marks (fold) ------- #

@staff_required()
def see_marks(request):
    courses = get_objects_for_user(request.user, 'quizzes.can_edit_quiz')

    return render(request, 'quizzes/see_marks.html',
        { 'courses': courses }
    )

@staff_required()
def download_all_marks(request, course_pk):
    """ For staff members to download the marks table as a csv file.
        Depends on: get_marks_data
    """

    # This effectively starts the same was as the see_all_marks view, but
    # instead of rendering as a table, we write to a csv and set up a download
    # link
    course = get_object_or_404(Course, pk=course_pk)
    table_data = get_marks_data(course)

    file_name = "{name}_All_grades_by_{user}_{date}.csv".format(
                    name = course.name,
                    user = request.user,
                    date = timezone.now().timestamp())
    file_path = os.path.join(settings.NOTE_ROOT, file_name)

    # The csv DictWriter needs to know the field names.
    ident_names = [ 'last_name', 'first_name', 'username', 'number'] 
    cat_names   = Evaluation.objects.filter(course = course).values_list('name', flat=True)
    # cat_names will have spaces in them, while table_data stripped spaces
    cat_names = [cat.replace(' ','') for cat in cat_names]
    field_names = ident_names + cat_names
    
    with open(file_path, 'a+') as csv_file:
        writer = csv.DictWriter(csv_file, field_names)
        writer.writeheader()
        for row in table_data:
            # Write each row to a csv file
            writer.writerow(row)
        
    return sendfile(request, file_path, attachment=True,
            attachment_filename=file_name)

@staff_required()
def see_all_marks(request, course_pk):
    """ A view for returning all student marks.
        Depends on: get_marks_data
    """

    course = get_object_or_404(Course, pk=course_pk)
    # Generate the table. This is dynamic to the number of categories which currently exists
    table_data = get_marks_data(course)
    table = define_all_marks_table()(table_data)
    RequestConfig(request, paginate=False).configure(table)

    sidenote = format_html("<h4>Options</h4><a class='btn btn-default' href='{}'>Download Marks</a>", 
                           reverse('download_all_marks', kwargs={'course_pk':course_pk}))
    return render(request, 'quizzes/list_table.html',
            {'table': table,
             'title': 'All Marks',
             'sidenote': sidenote,
            })

def get_marks_data(course):
    """ Helper function for creating the dictionary of student marks. Only looks
        at active students (non-staff members), and uses their username. 
        <<INPUT>>
          course (Course) The course for which to retrieve the marks
        <<OUTPUT>>
          Returns (Dict) Dictionary of student data, with fields
            {last_name, first_name, user_name, number}
            and a field for each ExemptionType assessment
        <<DEPENDS>>
        get_student_marks_for_table
    """
    table_data = [];
    students = User.objects.prefetch_related('marks','membership').filter(
            membership__courses__in=[course],
            is_staff=False, is_active=True,
            )
    for student in students:
        try:
            table_data.append(get_student_marks_for_table(student, course))
        except Exception as e:
            print(e)

    return table_data

def get_student_marks_for_table(student, course):
    """ A helper function which outputs the dictionary of student marks.
        <<INPUT>>
        student (User) the student whose marks we are getting
        <<OUTPUT>>
        (Dictionary) suitable for entry into django-tables2

        ToDo: Could see_marks benefit from this?
        Warning: If iterating over students, should prefetch marks
    """
    return_dict = {'last_name': student.last_name,
                   'first_name': student.first_name,
                   'username': student.username,
                  }
    for smark in student.marks.filter(evaluation__course=course).iterator():
        score = smark.score
        return_dict[smark.evaluation.name.replace(' ','')]=score

    return return_dict
# --------- Marks (end) ------- #
