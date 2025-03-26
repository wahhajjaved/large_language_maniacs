from __future__ import unicode_literals
import erpnext.education.utils as utils
import frappe

# LMS Utils to Update State for Vue Store
@frappe.whitelist()
def get_program_enrollments():
	student = utils.get_current_student()
	if student == None:
		return None
	return student.get_program_enrollments()

@frappe.whitelist()
def get_all_course_enrollments():
	student = utils.get_current_student()
	if student == None:
		return None
	return student.get_all_course_enrollments()

# Vue Client Functions
@frappe.whitelist(allow_guest=True)
def get_portal_details():
	"""
	Returns portal details from Education Settings Doctype. This contains the Title and Description for LMS amoung other things.
	"""
	from erpnext import get_default_company

	settings = frappe.get_doc("Education Settings")
	title = settings.portal_title or get_default_company()
	description = settings.description
	return dict(title=title, description=description)

@frappe.whitelist(allow_guest=True)
def get_featured_programs():
	featured_program_names = frappe.get_all("Program", filters={"is_published": True, "is_featured": True})
	if featured_program_names:
		featured_list = [utils.get_program_and_enrollment_status(program['name']) for program in featured_program_names]
		return featured_list
	else:
		return get_all_programs()[:2]

@frappe.whitelist(allow_guest=True)
def get_all_programs():
	program_names = frappe.get_all("Program", filters={"is_published": True})
	if program_names:
		program_list = [utils.get_program_and_enrollment_status(program['name']) for program in program_names]
		return program_list

@frappe.whitelist(allow_guest=True)
def get_program(program_name):
	try:
		return frappe.get_doc('Program', program_name)
	except frappe.DoesNotExistError:
		frappe.throw(_("Program {0} does not exist.".format(program_name)))

# Functions to get program & course details
@frappe.whitelist(allow_guest=True)
def get_courses(program_name):
	program = frappe.get_doc('Program', program_name)
	courses = program.get_course_list()
	return courses

@frappe.whitelist()
def get_next_content(current_content, current_content_type, topic):
	if frappe.session.user == "Guest":
		return None
	topic = frappe.get_doc("Topic", topic)
	content_list = [{'content_type':item.doctype, 'content':item.name} for item in topic.get_contents()]
	current_index = content_list.index({'content': current_content, 'content_type': current_content_type})
	try:
		return content_list[current_index + 1]
	except IndexError:
		return None

def get_quiz_with_answers(quiz_name):
	try:
		quiz = frappe.get_doc("Quiz", quiz_name).get_questions()
		quiz_output = [{'name':question.name, 'question':question.question, 'options':[{'name': option.name, 'option':option.option, 'is_correct':option.is_correct} for option in question.options]} for question in quiz]
		return quiz_output
	except:
		frappe.throw("Quiz {0} does not exist".format(quiz_name))
		return None

@frappe.whitelist()
def get_quiz_without_answers(quiz_name, course_name):
	try:
		quiz = frappe.get_doc("Quiz", quiz_name)
		questions = quiz.get_questions()
	except:
		frappe.throw("Quiz {0} does not exist".format(quiz_name))
		return None

	enrollment = utils.get_course_enrollment(course_name).name
	quiz_status = {}
	quiz_status['is_complete'], quiz_status['score'], quiz_status['result']  = utils.check_quiz_completion(quiz, enrollment)
	quiz_output = [{'name':question.name, 'question':question.question, 'type': question.type, 'options':[{'name': option.name, 'option':option.option} for option in question.options]} for question in questions]
	return { 'quizData': quiz_output, 'status': quiz_status}

@frappe.whitelist()
def evaluate_quiz(course, quiz_response, quiz_name):
	"""LMS Function: Evaluates a simple multiple choice quiz.
	:param quiz_response: contains user selected choices for a quiz in the form of a string formatted as a dictionary. The function uses `json.loads()` to convert it to a python dictionary.
	"""
	import json
	quiz_response = json.loads(quiz_response)
	quiz = frappe.get_doc("Quiz", quiz_name)
	answers, score, status = quiz.evaluate(quiz_response, quiz_name)

	result = {k: ('Correct' if v else 'Wrong') for k,v in answers.items()}
	result_data = []
	for key in answers:
		item = {}
		item['question'] = key
		item['quiz_result'] = result[key]
		try:
			if isinstance(quiz_response[key], list):
				item['selected_option'] = ', '.join(frappe.get_value('Options', res, 'option') for res in quiz_response[key])
			else:
				item['selected_option'] = frappe.get_value('Options', quiz_response[key], 'option')
		except:
			item['selected_option'] = "Unattempted"
		result_data.append(item)

	add_quiz_activity(course, quiz_name, result_data, score, status)
	return(score)

def add_quiz_activity(course, quiz_name, result_data, score, status):
	if not utils.get_current_student():
		return None
	enrollment = utils.get_course_enrollment(course).name
	quiz_activity = frappe.get_doc({
		"doctype": "Quiz Activity",
		"enrollment": enrollment,
		"quiz": quiz_name,
		"activity_date": frappe.utils.datetime.datetime.now(),
		"result": result_data,
		"score": score,
		"status": status
		}).insert()

@frappe.whitelist()
def enroll_in_program(program_name):
	student = utils.get_current_student()
	if not student:
		utils.create_student_from_current_user()
	program_enrollment = student.enroll_in_program(program_name)
	return program_name

# Academty Activity
@frappe.whitelist()
def add_activity(course, content_type, content):
	if not utils.get_current_student():
		return
	enrollment = utils.get_course_enrollment(course)
	if(utils.check_activity_exists(enrollment.name, content_type, content)):
		pass
	else:
		activity = frappe.get_doc({
			"doctype": "Course Activity",
			"enrollment": enrollment.name,
			"content_type": content_type,
			"content": content,
			"activity_date": frappe.utils.datetime.datetime.now()
			})
		activity.save()
		frappe.db.commit()

@frappe.whitelist()
def get_student_course_details(course_name, program_name):
	"""
	Return the porgress of a course in a program as well as the content to continue from.
		:param course_name:
		:param program_name:
	"""
	student = utils.get_current_student()
	if not student:
		return {'flag':'Start Course' }
	course_enrollment = utils.get_course_enrollment(course_name)
	program_enrollment = utils.get_program_enrollment(program_name)
	if not program_enrollment:
		return None
	if not course_enrollment:
		course_enrollment = utils.enroll_in_course(course_name, program_name)
	progress = course_enrollment.get_progress(student)
	count = sum([activity['is_complete'] for activity in progress])
	if count == 0:
		return {'flag':'Start Course'}
	elif count == len(progress):
		return {'flag':'Completed'}
	elif count < len(progress):
		next_item = next(item for item in progress if item['is_complete']==False)
		return {'flag':'Continue'}

@frappe.whitelist()
def get_student_topic_details(topic_name, course_name):
	"""
	Return the porgress of a course in a program as well as the content to continue from.
		:param topic_name:
		:param course_name:
	"""
	topic = frappe.get_doc("Topic", topic_name)
	student = utils.get_current_student()
	if not student:
		topic_content = topic.get_all_children()
		if topic_content:
			return {'flag':'Start Course', 'content_type': topic_content[0].content_type, 'content': topic_content[0].content}
		else:
			return None
	course_enrollment = utils.get_course_enrollment(course_name)
	progress = student.get_topic_progress(course_enrollment.name, topic)
	if not progress:
		return { 'flag':'Start Topic', 'content_type': None, 'content': None }
	count = sum([activity['is_complete'] for activity in progress])
	if count == 0:
		return {'flag':'Start Topic', 'content_type': progress[0]['content_type'], 'content': progress[0]['content']}
	elif count == len(progress):
		return {'flag':'Completed', 'content_type': progress[0]['content_type'], 'content': progress[0]['content']}
	elif count < len(progress):
		next_item = next(item for item in progress if item['is_complete']==False)
		return {'flag':'Continue', 'content_type': next_item['content_type'], 'content': next_item['content']}

@frappe.whitelist()
def get_program_progress(program_name):
	import math
	program = frappe.get_doc("Program", program_name)
	program_enrollment = utils.get_program_enrollment(program_name)
	program_progress = {}
	if not program_enrollment:
		return None
	else:
		progress = []
		for course in program.get_all_children():
			course_progress = get_student_course_details(course.course, program_name)
			is_complete = False
			if course_progress['flag'] == "Completed":
				is_complete = True
			progress.append({'course_name': course.course_name, 'name': course.course, 'is_complete': is_complete})

		program_progress['progress'] = progress
		program_progress['name'] = program_name
		program_progress['program'] = program.program_name

		try:
			program_progress['percentage'] = math.ceil((sum([item['is_complete'] for item in progress] * 100)/len(progress)))
		except ZeroDivisionError:
			program_progress['percentage'] = 0

		return program_progress

@frappe.whitelist()
def get_joining_date():
	current_student = utils.get_current_student()
	if current_student:
		return student.joining_date
	else:
		return None

@frappe.whitelist()
def get_quiz_progress(program_name):
	program = frappe.get_doc("Program", program_name)
	program_enrollment = utils.get_program_enrollment(program_name)
	quiz_progress = frappe._dict()
	student = utils.get_current_student()
	if not program_enrollment:
		return None
	else:
		progress_list = []
		for course in program.get_all_children():
			course_enrollment = utils.get_course_enrollment(course.course)
			course_progress = course_enrollment.get_progress(student)
			for progress_item in course_progress:
				if progress_item['content_type'] == "Quiz":
					progress_item['course'] = course.course_name
					progress_list.append(progress_item)
		if not progress_list:
			return None
		quiz_progress.quiz_attempt = progress_list
		quiz_progress.name = program_name
		quiz_progress.program = program.program_name
		return quiz_progress


@frappe.whitelist(allow_guest=True)
def get_course_details(course_name):
	try:
		course = frappe.get_doc('Course', course_name)
		return course
	except:
		return None

# Functions to get program & course details
@frappe.whitelist(allow_guest=True)
def get_topics(course_name):
	try:
		course = frappe.get_doc('Course', course_name)
		return course.get_topics()
	except frappe.DoesNotExistError:
		frappe.throw(_("Course {0} does not exist.".format(course_name)))

@frappe.whitelist()
def get_content(content_type, content):
	try:
		return frappe.get_doc(content_type, content)
	except frappe.DoesNotExistError:
		frappe.throw(_("{0} {1} does not exist.".format(content_type, content)))