from django.shortcuts import render
from .models import Student, Course, COS_BSE, Entry, Approved_Course, Outside_Course
from django.contrib.auth.decorators import login_required
import re

def compare_lists(stud, cour):
	similarities=[]
	differences=[]
	#all_courses=classes.objects.values_list('course_id', flat=True).order_by('course_id')
	#student_courses=student.objects.values_list('course_id', flat=True).order_by('course_id')
	for i in cour:
		if i in stud:
			similarities.append(i)
		else:
			differences.append(i)
	return {"similarities": similarities, "differences": differences}


def title(list):
	new_list=[]
	for i in list:
		new_list.append(Course.objects.get(course_id=i).listings)
	return new_list


# i mean we could make a view for every certificate...but that wouldn't cover people doing two certificates...would want to show on
# same page....could be possible if we used buttons though
def home(request):
	# current_user = request.user
	# try:
 #  		s = Student.objects.get(student_id=current_user)
	# except Student.DoesNotExist:
 #  		s = Student(student_id=current_user)
 #  		s.save()
	# student = Student.objects.get(student_id=current_user.username)

	# context = {'user': current_user.username}
	return render(request, 'index.html')

@login_required # Cas authentication for this url.
def profile(request):
	current_user = request.user;

	try:
   		s = Student.objects.get(student_id=current_user)
	except Student.DoesNotExist:
   		s = Student(student_id=current_user)
   		s.save()
	student = Student.objects.get(student_id=current_user.username)

	context = {'user': current_user.username}
	return render(request, 'profile.html', context)

@login_required # Cas authentication for this url.
def degree_progress(request):
	# Natalie's code for displaying BSE requirements for all BSE students
	# not added to either view yet though, so not sure if it works
	student_ec=[]
	student_em=[]
	student_la=[]
	student_ha=[]
	student_sa=[]
	student_wri=[]
	student_foreign=[]
	'''ec_requirements = Course.objects.filter(area='EC')
	em_requirements = Course.objects.filter(area='EM')
	la_requirements = Course.objects.filter(area='LA')
	sa_requirements = Course.objects.filter(area='SA')
	ha_requirements = Course.objects.filter(area='HA')
	writing_sem = Course.objects.filter(listings__regex='WRI1')
	foreign_lang = Course.objects.filter(listings__regex='(ARA|BCS|CHI|CZE|FRE|GER|HEB|HIN|ITA|JPN|KOR|LAT|POL|POR|RUS|SPA|SWA|TUR|TWI|URD)')'''
	current_user = request.user
	try:
   		s = Student.objects.get(student_id=current_user)
	except Student.DoesNotExist:
   		s = Student(student_id=current_user)
   		s.save()
	student = Student.objects.get(student_id=current_user.username)
	student_major = student.student_major
	all_courses = Entry.objects.filter(student_id=current_user.username).values_list('course_id', flat=True).order_by('course_id') # all of the student's courses
	#dist_courses = Entry.objects.filter(student_id=current_user.username)
	for d in all_courses:
		course = Course.objects.get(course_id=d)
		if (course.area=='SA'):
			student_sa.append(d)
		elif (course.area=='LA'):
			student_la.append(d)
		elif (course.area=='HA'):
			student_ha.append(d)
		elif (course.area=='EM'):
			student_em.append(d)
		elif (course.area=='EC'):
			student_ec.append(d)
		elif(re.match(r'WRI1', course.listings)):
			student_wri.append(d)
		elif(re.match(r'(ARA|BCS|CHI|CZE|FRE|GER|HEB|HIN|ITA|JPN|KOR|LAT|POL|POR|RUS|SPA|SWA|TUR|TWI|URD)', course.listings)):
			student_foreign.append(d)
	# something to think about: COS 340 can't pop up in "Other" and in "Theory"
	# all of the requirement lists
	# can probably combine a lot of things here into one function - maybe i want the approved courses in their own list? idk
	if (student_major=="COS_BSE"):
		# can probably shorten this a little bit
		theory_courses = COS_BSE.objects.filter(theory=1).values_list('course_id', flat=True).order_by('course_id')
		systems_courses = COS_BSE.objects.filter(systems=1).values_list('course_id', flat=True).order_by('course_id')
		apps_courses = COS_BSE.objects.filter(applications=1).values_list('course_id', flat=True).order_by('course_id')
		core_courses = COS_BSE.objects.filter(core=1).values_list('course_id', flat=True).order_by('course_id')
		other_courses = COS_BSE.objects.filter(other=1).values_list('course_id', flat=True).order_by('course_id')
		iw_courses = COS_BSE.objects.filter(iw=1).values_list('course_id', flat=True).order_by('course_id')
		
		theory_on = compare_lists(all_courses, theory_courses)["similarities"]
		other_theory = Approved_Course.objects.filter(requirement="Theory") # this needs to filter by netid too!!
		for t in other_theory:
			theory_on.append(t.course_id)
		theory_on = title(theory_on)
		theory_off = title(compare_lists(all_courses, theory_courses)["differences"])
		
		systems_on = compare_lists(all_courses, systems_courses)["similarities"]
		other_sys = Approved_Course.objects.filter(requirement="Systems")
		for t in other_sys:
			systems_on.append(t.course_id)
		systems_on = title(systems_on)
		systems_off = title(compare_lists(all_courses, systems_courses)["differences"])

		apps_on = compare_lists(all_courses, apps_courses)["similarities"]
		other_apps = Approved_Course.objects.filter(requirement="Applications")
		for t in other_apps:
			apps_on.append(t.course_id)
		apps_on = title(apps_on)
		apps_off = title(compare_lists(all_courses, apps_courses)["differences"])

		# other should have all classes in "other" that the user hasn't already taken
		# will fix this bug a little later... 4/9/2016
		other_on = compare_lists(all_courses, other_courses)["similarities"]
		other_other = Approved_Course.objects.filter(requirement="Other")
		for t in other_other:
			other_on.append(t.course_id)
		other_on = title(other_on)
		other_off = title(compare_lists(all_courses, other_courses)["differences"])

		iw_on = compare_lists(all_courses, iw_courses)["similarities"] #iw is for BSE only
		other_iw = Approved_Course.objects.filter(requirement="Independent")
		for t in other_iw:
			iw_on.append(t.course_id)
		iw_on = title(iw_on)
		iw_off = title(compare_lists(all_courses, iw_courses)["differences"])

		core_on = title(compare_lists(all_courses, core_courses)["similarities"])
		core_off = title(compare_lists(all_courses, core_courses)["differences"])

		# Distribution Requirements
		student_sa=title(student_sa)
		student_la=title(student_la)
		student_ha=title(student_ha)
		student_em=title(student_em)
		student_ec=title(student_ec)

		# Outside Courses
		# Note: should probably do Outside Courses/Approved Courses first, then add to LA/SA/Theory/etc. THEN consolidate lists 
		student_outside=[]
		outside_courses = Outside_Course.objects.filter(student_id=current_user.username) # list of the student's outside courses
		for c in outside_courses.iterator():
			student_outside.append(c.course_name)

		# also need to add BSE requirements here and distributions
		# could literally just pass every certificate thing to this page....but that would be really dumb and bad
		# still in the process of getting new ideas for certificates...it can def be done tho...still thinking
		context = {'theory_on': theory_on, 'theory_off': theory_off, 'systems_on': systems_on, 'systems_off': systems_off,
		'apps_on': apps_on, 'apps_off': apps_off, 'other_on': other_on, 'other_off': other_off,
		'iw_on': iw_on, 'iw_off': iw_off, 'core_on': core_on, 'core_off': core_off, 'other_theory': other_theory,
		'student_sa': student_sa, 'student_la': student_la, 'student_ha': student_ha, 'student_ec': student_ec,
		'student_em': student_em, 'student_foreign': student_foreign, 'student_wri': student_wri, 'outside_courses': student_outside}
		return render(request, 'degree_progress_cos_bse.html', context)
 

def course_search(query):
	terms = query.split()
	matched_courses = Course.objects.all()
	for x in terms:
		if len(x) <= 0:
			continue;
		if x.isalpha() or xisdigit():
			matched_courses = matched_courses.filter(listings_icontains=x)
	return matched_courses



@login_required # Cas authentication for this url.
def four_year(request,search):
	current_user = request.user
	try:
   		s = Student.objects.get(student_id=current_user)
	except Student.DoesNotExist:
   		s = Student(student_id=current_user)
   		s.save()
	student = Student.objects.get(student_id=current_user.username)

	matched_courses = []
	test = request.GET["q"]
	if len(test) > 0:
		matched_courses = course_search(test);
	# if q:
	# 	if search:
	# 		query = True
	# 		q = request.GET['q']
	# 		number= ""
	# 		dpt = search
			# for i in search:
			# 	if isdigit(i):
			# 		number += i;
			# 	if isalpha(i):
			# 		dpt += i;
			
			# matched_courses = matched_courses.filter(listings_icontains=number)


	# getting list of courses for each semester
	fresh_fall = Entry.objects.filter(student_id=current_user.username, semester="FRF")
	fresh_spring = Entry.objects.filter(student_id=current_user.username, semester="FRS")
	soph_fall = Entry.objects.filter(student_id=current_user.username, semester="SOF")
	soph_spring = Entry.objects.filter(student_id=current_user.username, semester="SOS")
	junior_fall = Entry.objects.filter(student_id=current_user.username, semester="JRF")
	junior_spring = Entry.objects.filter(student_id=current_user.username, semester="JRS")
	senior_fall = Entry.objects.filter(student_id=current_user.username, semester="SRF")
	senior_spring = Entry.objects.filter(student_id=current_user.username, semester="SRS")
	context = {'user': current_user.username,'fresh_fall': fresh_fall, 'fresh_spring': fresh_spring, 
	'soph_fall': soph_fall, 'soph_spring': soph_spring, 'junior_fall': junior_fall, 'junior_spring': junior_spring,
	'senior_fall': senior_fall, 'senior_spring': senior_spring, 'test': test, 'matched_courses': matched_courses}

	return render(request, 'four_year.html', context)

@login_required # Cas authentication for this url.
# if you got a course at Princeton to count as a COS departmental
def princeton_course_approval(request):
	current_user = request.user
	student = Student.objects.get(student_id=current_user.username)

@login_required # Cas authentication for this url.
# if you got a course at Princeton to count as a COS departmental
def outside_course_approval(request):
	current_user = request.user
	student = Student.objects.get(student_id=current_user.username)

@login_required # Cas authentication for this url.
def schedule_sharing(request):
	current_user = request.user
	student = Student.objects.get(student_id=current_user.username)