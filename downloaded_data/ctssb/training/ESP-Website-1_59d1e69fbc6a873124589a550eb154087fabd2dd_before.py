from django.db import models
from django.contrib.auth.models import User
from esp.cal.models import Event
from esp.datatree.models import DataTree, GetNode
from esp.users.models import UserBit, ContactInfo, StudentInfo, TeacherInfo, EducatorInfo, GuardianInfo
from esp.lib.markdown import markdown
from esp.qsd.models import QuasiStaticData
from esp.lib.EmptyQuerySet import EMPTY_QUERYSET

# Create your models here.

class Program(models.Model):
	""" An ESP Program, such as HSSP Summer 2006, Splash Fall 2006, Delve 2005, etc. """
	anchor = models.ForeignKey(DataTree) # Series containing all events in the program, probably including an event that spans the full duration of the program, to represent this program

	grade_min = models.IntegerField()
	grade_max = models.IntegerField()
	class_size_min = models.IntegerField()
	class_size_max = models.IntegerField()

	def url(self):
		str_array = self.anchor.tree_encode()
		return '/'.join(str_array[2:])
	
	def __str__(self):
		return str(self.anchor.parent.friendly_name) + ' ' + str(self.anchor.friendly_name)

	def parent(self):
		return anchor.parent

	def getUrlBase(self):
		""" gets the base url of this class """
		tmpnode = self.anchor
		urllist = []
		while tmpnode.name != 'Programs':
			urllist.insert(0,tmpnode.name)
			tmpnode = tmpnode.parent
		return "/".join(urllist)
					  

	class Admin:
		pass
	
	@staticmethod
	def find_by_perms(user, verb):
		""" Fetch a list of relevant programs for a given user and verb """
		return UserBit.find_by_anchor_perms(Program,user,verb)

class ClassCategories(models.Model):
	""" A list of all possible categories for an ESP class

	Categories include 'Mathematics', 'Science', 'Zocial Zciences', etc.
	"""
	category = models.TextField()

	def __str__(self):
		return str(self.category)

	class Admin:
		pass

# FIXME: The Class object should use the permissions system to control
# which grades (Q/Community/6_12/*) are permitted to join the class, though
# the UI should make it as clean as two numbers, at least initially.
class Class(models.Model):
	""" A Class, as taught as part of an ESP program """
	anchor = models.ForeignKey(DataTree)
	parent_program = models.ForeignKey(Program)
	# title drawn from anchor.friendly_name
	# class number drawn from anchor.name
	category = models.ForeignKey(ClassCategories)
	# teachers are drawn from permissions table
	class_info = models.TextField(blank=True)
	message_for_directors = models.TextField(blank=True)
	grade_min = models.IntegerField()
	grade_max = models.IntegerField()
	class_size_min = models.IntegerField()
	class_size_max = models.IntegerField()
	schedule = models.TextField(blank=True)
	event_template = models.ForeignKey(DataTree, related_name='class_event_template_set', null=True)
	viable_times = models.ManyToManyField(DataTree, related_name='class_viable_set', blank=True)
	#	We think this is useless because the sign-up is completely based on userbits.
	enrollment = models.IntegerField()

	def url(self):
		str_array = self.anchor.tree_encode()
		return '/'.join(str_array[2:])

	def got_qsd(self):
				return (QuasiStaticData.objects.filter(path = self.anchor).count() > 0)

	def PopulateEvents(self):
		""" Given this instance's event_template, generate a series of events that define this class's schedule """
		for e in self.event_template.event_set.all():
			newevent = Event()
			newevent.start = e.start
			newevent.end = e.end
			newevent.short_description = e.short_description
			newevent.description = e.description.replace('[event]', e.anchor.friendly_name) # Allow for the insertion of event names, so that the templates are less generic/nonspecific
			newevent.event_type = e.event_type
			newevent.anchor = self.anchor
			newevent.save()
		
	def __str__(self):
		if self.title() is not None:
			return self.title()
		else:
			return ""

	def title(self):
		return self.anchor.friendly_name
	
	def teachers(self):
		v = GetNode( 'V/Flags/Registration/Teacher' )
		userbits = [ x.user.id for x in UserBit.bits_get_users( self.anchor, v) ]
		if len(userbits) > 0:
			return User.objects.filter(id__in=userbits).distinct()
		else:
			return EMPTY_QUERYSET.distinct()
		#return [ x.user for x in UserBit.bits_get_users( self.anchor, v ) ]
		
	def students(self):
		v = GetNode( 'V/Flags/Registration/Preliminary' )
		return [ x.user for x in UserBit.bits_get_users( self.anchor, v ) ]
		
	def num_students(self):
		v = GetNode( 'V/Flags/Registration/Preliminary' )
		return UserBit.bits_get_users(self.anchor, v).count()

	def isFull(self):
		if self.num_students() >= self.class_size_max:
			return True
		else:
			return False
	
	def getTeacherNames(self):
		return [ usr.first_name + ' ' + usr.last_name
			for usr in self.teachers() ]

	def preregister_student(self, user):
		prereg_verb = GetNode( 'V/Flags/Registration/Preliminary' )
		
		#	First, delete preregistration bits for other classes at the same time.
		other_bits = UserBit.objects.filter(user=user, verb=prereg_verb)
		for b in other_bits:
			class_qset = Class.objects.filter(anchor=b.qsc, event_template = self.event_template)
			if class_qset.count() > 0:
				b.delete()
				
		if not self.isFull():
			#	Then, create the userbit denoting preregistration for this class.
			prereg = UserBit()
			prereg.user = user
			prereg.qsc = self.anchor
			prereg.verb = prereg_verb
			prereg.save()
			return True
		else:
			#	Pre-registration failed because the class is full.
			return False

	def pageExists(self):
		from esp.qsd.models import QuasiStaticData
		return self.anchor.quasistaticdata_set.filter(name='learn:index').count() > 0

	def isAccepted(self):
		return UserBit.UserHasPerms(None, self.anchor, GetNode('V/Flags/Class/Approved'))

	def accept(self):
		if self.isAccepted():
			return False # already accepted
			
		u = UserBit()
		u.user = None
		u.qsc = self.anchor
		u.verb = GetNode('V/Flags/Class/Approved')
		u.save()
		return True

	def reject(self):
		userbitlst = UserBit.objects.filter(user = None,
											qsc  = self.anchor,
											verb = GetNode('V/Flags/Class/Approved'))
		if len(userbitlst) > 0:
			userbitlst.delete()
			return True
		return False
	
	def setTime(self, event_template_id):
		if event_template_id > 0:
			self.event_template = DataTree.objects.filter(id=event_template_id)[0]
			self.save()
		return event_template_id
			
	def getUrlBase(self):
		""" gets the base url of this class """
		tmpnode = self.anchor
		urllist = []
		while tmpnode.name != 'Programs':
			urllist.insert(0,tmpnode.name)
			tmpnode = tmpnode.parent
		return "/".join(urllist)
							   
	class Admin:
		pass
	
class ResourceRequest(models.Model):
	""" An indication of resources requested for a particular class """
	requestor = models.OneToOneField(Class)
	wants_projector = models.BooleanField()
	wants_computer_lab = models.BooleanField()
	wants_open_space = models.BooleanField()

	def __str__(self):
		return 'Resource request for ' + str(self.requestor)

	class Admin:
		pass

class BusSchedule(models.Model):
	""" A scheduled bus journey associated with a program """
	program = models.ForeignKey(Program)
	src_dst = models.CharField(maxlength=128)
	departs = models.DateTimeField()
	arrives = models.DateTimeField()

	class Admin:
		pass

class TeacherParticipationProfile(models.Model):
	""" Profile properties associated with a teacher in a program """
	teacher = models.ForeignKey(User)
	program = models.ForeignKey(Program)
	unique_together = (('teacher', 'program'),)
	bus_schedule = models.ManyToManyField(BusSchedule)

	can_help = models.BooleanField()

	def __str__(self):
		return 'Profile for ' + str(self.teacher) + ' in ' + str(self.program)

	class Admin:
		pass

class TeacherBio(models.Model):
	""" A biography of an ESP teacher """
	user = models.ForeignKey(User)
	content = models.TextField()

	def __str__(self):
		return self.user.first_name + ' ' + self.user.last_name + ', a Biography'
	
	def html(self):
		return markdown(self.content)
	
	class Admin:
		pass

class RegistrationProfile(models.Model):
	""" A student registration form """
	user = models.ForeignKey(User)
	program = models.ForeignKey(Program)
	contact_user = models.ForeignKey(ContactInfo, blank=True, null=True, related_name='as_user')
	contact_guardian = models.ForeignKey(ContactInfo, blank=True, null=True, related_name='as_guardian')
	contact_emergency = models.ForeignKey(ContactInfo, blank=True, null=True, related_name='as_emergency')
	student_info = models.ForeignKey(StudentInfo, blank=True, null=True, related_name='as_student')
	teacher_info = models.ForeignKey(TeacherInfo, blank=True, null=True, related_name='as_teacher')
	guardian_info = models.ForeignKey(GuardianInfo, blank=True, null=True, related_name='as_guardian')
	educator_info = models.ForeignKey(EducatorInfo, blank=True, null=True, related_name='as_educator')

	@staticmethod
	def getLastProfile(user):
		regProfList = RegistrationProfile.objects.filter(user__exact=user).order_by('-id')
		if len(regProfList) < 1:
			regProf = RegistrationProfile()
			regProf.user = user
		else:
			regProf = regProfList[0]
		return regProf

	@staticmethod
	def getLastForProgram(user, program):
		regProfList = RegistrationProfile.objects.filter(user__exact=user,program__exact=program).order_by('-id')
		if len(regProfList) < 1:
			regProf = RegistrationProfile()
			regProf.user = user
			regProg.program = program
		else:
			regProf = regProfList[0]
		return regProf
			
	def __str__(self):
		return '<Registration for ' + str(self.user) + ' in ' + str(self.program) + '>'

	def updateForm(self, form_data, specificInfo = None):
		if self.student_info is not None and (specificInfo is None or specificInfo == 'student'):
			form_data = self.student_info.updateForm(form_data)
		if self.teacher_info is not None and (specificInfo is None or specificInfo == 'teacher'):
			form_data = self.teacher_info.updateForm(form_data)
		if self.guardian_info is not None and (specificInfo is None or specificInfo == 'guardian'):
			form_data = self.guardian_info.updateForm(form_data)
		if self.educator_info is not None and (specificInfo is None or specificInfo == 'educator'):
			form_data = self.educator_info.updateForm(form_data)
		if self.contact_user is not None:
			form_data = self.contact_user.updateForm(form_data)
		if self.contact_guardian is not None:
			form_data = self.contact_guardian.updateForm(form_data, 'guard_')
		if self.contact_emergency is not None:
			form_data = self.contact_emergency.updateForm(form_data, 'emerg_')
		return form_data
	
	def preregistered_classes(self):
		v = GetNode( 'V/Flags/Registration/Preliminary' )
		return UserBit.find_by_anchor_perms(Class, self.user, v, self.program.anchor.tree_decode(['Classes']))
	
	def registered_classes(self):
		v = GetNode( 'V/Flags/Registration/Confirmed' )
		return UserBit.find_by_anchor_perms(Class, self.user, v, self.program.anchor.tree_decode(['Classes']))

	class Admin:
		pass
