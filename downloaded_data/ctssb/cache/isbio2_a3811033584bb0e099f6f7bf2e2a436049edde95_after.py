from __builtin__ import property
from django.db.models.query import QuerySet as original_QS
from django.db.models import Manager
from django.core.exceptions import ObjectDoesNotExist
import django.db.models.query_utils
from django.conf import settings
from django.http import Http404
from breeze.b_exceptions import InvalidArguments, ObjectHasNoReadOnlySupport, PermissionDenied
from comp import translate

org_Q = django.db.models.query_utils.Q


# clem 20/06/2016
class CustomManager(Manager):
	context_user = None
	context_obj = None

	def __init__(self):
		super(CustomManager, self).__init__()

	# clem 21/06/2016
	def set_read_only(self):
		""" Set the context object to read-only if the object has this property / attribute

		:return: if success
		:rtype: bool
		"""
		assert self._has_context
		if hasattr(self.context_obj, 'read_only'):
			self.context_obj.read_only = True
			return True
		return False

	# clem 20/06/2016
	def safe_get(self, **kwargs):
		""" Get and return an object provided its id or pk

		Does NOT implement user access control

		:param kwargs: {id: int or pk: int}
		:type kwargs: dict
		:raises: ObjectDoesNotExist, InvalidArguments
		"""
		has_id = 'id' in kwargs.keys()
		has_pk = 'pk' in kwargs.keys()
		if not (has_id or has_pk):
			raise InvalidArguments
		try:
			the_key = kwargs.pop('id' if has_id else 'pk')
			# self.context_obj = self.get(id=the_key) if has_id else self.get(pk=the_key)
			self.context_obj = super(CustomManager, self).get(id=the_key) if has_id else \
				super(CustomManager, self).get(pk=the_key)
			return self.context_obj
		except Exception as e:
			raise ObjectDoesNotExist(str(e))

	# clem 20/06/2016
	def user_get(self, **kwargs):
		""" Get and return a specific object with id or pk field specified, and provided some user for context

		Does NOT implement user access control

		:param kwargs: {id: int or pk: int, user: models.User}
		:type kwargs: dict
		:raises: ObjectDoesNotExist, InvalidArguments
		"""
		if 'user' not in kwargs.keys():
			raise InvalidArguments
		self.context_user = kwargs.pop('user')
		return self.safe_get(**kwargs)

	# clem 20/06/2016
	@staticmethod
	def admin_override_param(user):
		""" Return wether settings.SU_ACCESS_OVERRIDE is True and user is super user

		:param user: Django user object
		:type user: models.User
		:return: True | False
		:rtype: bool
		"""
		return settings.SU_ACCESS_OVERRIDE and user.is_superuser

	# clem 20/06/2016
	@staticmethod
	def get_author_param(obj):  # FIXME deprecated ?
		""" Return the author/owner of the provided object, independently of the name of the column storing it

		:param obj:
		:type obj:
		:return: Django user object
		:rtype: models.User
		"""
		auth = None
		if hasattr(obj, 'author'): # most objects
			auth = obj.author
		elif hasattr(obj, '_author'): # Reports
			auth = obj._author
		elif hasattr(obj, 'juser'): # Jobs
			auth = obj.juser
		elif hasattr(obj, 'added_by'): # OffsiteUser
			auth = obj.added_by
		elif hasattr(obj, 'user'): # UserProfile
			auth = obj.user
		elif hasattr(obj, 'script_buyer'): # CartInfo
			auth = obj.script_buyer
		return auth

	# clem 20/06/2016
	@classmethod
	def has_full_access_param(cls, obj, user):
		""" Return wether provided user has full access over provided object (or user is admin with admin override on)

		:param obj:
		:type obj:
		:param user: Django user object
		:type user: models.User
		:return: True | False
		:rtype: bool
		"""
		# author = cls.get_author_param(obj) # author/owner of the object
		# return author == user or cls.admin_override_param(user)
		return obj.is_owner(user) or cls.admin_override_param(user)

	# clem 20/06/2016
	@classmethod
	def has_read_access_param(cls, obj, user):
		""" Return wether provided user has read access over provided object

		it means, either user is owner of said object, or object has been shared with said user
		or user is admin with admin override on

		:param obj:
		:type obj:
		:param user: Django user object
		:type user: models.User
		:return: True | False
		:rtype: bool
		"""
		# return cls.has_full_access_param(obj, user) or obj.has
		return obj.has_access(user)

	@property
	def _has_context(self):
		""" Tells wether this object has proper context (i.e. an user object and db record object)

		Only self.safe_get() sets self.context_obj
		and only self.user_get() sets self.context_user and self.context_obj

		:return: True | False
		:rtype: bool
		"""
		return self.context_obj and self.context_user

	###
	#  Old methods, now property, wrapper of the real methods
	###

	# clem 19/02/2016
	@property
	def admin_override(self):
		""" Return wether settings.SU_ACCESS_OVERRIDE is True and context user is super user

		No argument wrapper for self.admin_override_param

		:return: True | False
		:rtype: bool
		"""
		assert self._has_context
		return self.__class__.admin_override_param(self.context_user)

	# clem 19/02/2016
	@property
	def get_author(self): # FIXME deprecated ?
		""" Return the author/owner of the context object, independently of the name of the column storing it

		No argument wrapper for self.get_author_param

		:return: Django user object
		:rtype: models.User
		"""
		assert self._has_context
		return self.__class__.get_author_param(self.context_obj)

	# clem 19/02/2016
	@property
	def has_full_access(self):
		""" Return wether context user has full access over provided object (or user is admin with admin override on)

		No argument wrapper for self.has_full_access_param

		:return: True | False
		:rtype: bool
		"""
		assert self._has_context
		return self.has_full_access_param(self.context_obj, self.context_user)

	# clem 19/02/2016
	@property
	def has_read_access(self):
		""" Return wether context user has read access over context object

		it means, either user is owner of said object, or object has been shared with said user
		or user is admin with admin override on

		No argument wrapper for self.has_read_access_param

		:return: True | False
		:rtype: bool
		"""
		assert self._has_context
		return self.has_read_access_param(self.context_obj, self.context_user)


class Q(django.db.models.query_utils.Q):
	def __init__(self, *args, **kwargs):
		args, kwargs = translate(args, kwargs)
		super(Q, self).__init__(*args, **kwargs)


class QuerySet(original_QS):
	def __init__(self, *args, **kwargs):
		super(QuerySet, self).__init__(*args, **kwargs)
	
	def _filter_or_exclude(self, negate, *args, **kwargs):
		args, kwargs = translate(args, kwargs)
		return super(QuerySet, self)._filter_or_exclude(negate, *args, **kwargs)

	def filter(self, *args, **kwargs):
		args, kwargs = translate(args, kwargs)
		return super(QuerySet, self).filter(*args, **kwargs)

	def annotate(self, *args, **kwargs):
		args, kwargs = translate(args, kwargs)
		return super(QuerySet, self).annotate(*args, **kwargs)

	def get(self, *args, **kwargs):
		args, kwargs = translate(args, kwargs)
		return super(QuerySet, self).get(*args, **kwargs)

	def exclude(self, *args, **kwargs):
		args, kwargs = translate(args, kwargs)
		return super(QuerySet, self).exclude(*args, **kwargs)

	def order_by(self, *field_names):
		field_names, _ = translate(field_names, dict())
		return super(QuerySet, self).order_by(*field_names)

	##
	# Request filtering
	##
	def owned(self, user):
		"""
		Returns ALL the jobs that ARE scheduled
		"""
		return self.filter(_author__exact=user)

	def get_scheduled(self):
		"""
		Returns ALL the jobs that ARE scheduled
		"""
		from breeze.models import JobStat
		return self.filter(_status=JobStat.SCHEDULED).filter(_author__id__gt=0)

	def get_not_scheduled(self):
		"""
		Returns ALL the jobs that are NOT scheduled
		"""
		from breeze.models import JobStat
		return self.exclude(_status=JobStat.SCHEDULED).exclude(_breeze_stat=JobStat.SCHEDULED).filter(
			_author__id__gt=0)

	def get_incomplete(self):
		"""
		Returns all the jobs that are NOT completed, excluding Scheduled jobs
		That also includes active job that are not running yet
		"""
		from breeze.models import JobStat
		return self.get_not_scheduled().exclude(_breeze_stat=JobStat.DONE) | self.get_aborting()

	def get_run_wait(self):
		"""
		Returns all the jobs that are waiting to be run
		"""
		from breeze.models import JobStat
		return self.get_not_scheduled().filter(_breeze_stat=JobStat.RUN_WAIT)

	def get_active(self):
		"""
		Returns all the jobs that are currently active
		(this include INIT, PREPARE_RUN, RUNNING, QUEUED_ACTIVE, ABORT but not RUN_WAIT nor SCHEDULED)
		This is the set you want to refresh periodically
		"""
		from breeze.models import JobStat
		return self.get_not_scheduled().exclude(_breeze_stat=JobStat.RUN_WAIT).exclude(_breeze_stat=JobStat.DONE) | \
			self.get_aborting()

	def get_running(self):
		"""
		Returns all the jobs that are currently active and actually running
		(does NOT include INIT, PREPARE_RUN, QUEUED_ACTIVE, etc)
		"""
		from breeze.models import JobStat
		return self.get_not_scheduled().filter(_breeze_stat=JobStat.RUNNING, _status=JobStat.RUNNING) | \
			self.get_aborting()

	def get_history(self):
		"""
		Returns all the jobs history
		includes succeeded, failed and aborted ones
		"""
		from breeze.models import JobStat
		return self.get_not_scheduled().filter(_breeze_stat=JobStat.DONE)

	def get_done(self, include_failed=True, include_aborted=True):
		"""
		Returns all the jobs that are done,
		including or not the failed and aborted ones
		"""
		from breeze.models import JobStat

		r = self.get_history()

		if not include_failed:
			r = r.exclude(_status=JobStat.FAILED)
		if not include_aborted:
			r = r.exclude(_status=JobStat.ABORTED)

		return r

	def get_failed(self):
		"""
		Returns all the jobs history
		includes succeeded, failed and aborted ones
		"""
		from breeze.models import JobStat
		return self.get_history().filter(_status=JobStat.FAILED)

	def get_aborting(self):
		"""
		Returns the jobs marked for abortion
		"""
		from breeze.models import JobStat

		return self.filter(_breeze_stat=JobStat.ABORT)

	def get_aborted(self):
		"""
		Returns all the jobs history
		includes succeeded, failed and aborted ones
		"""
		from breeze.models import JobStat

		return self.get_history().filter(Q(_status=JobStat.ABORTED) or Q(_status=JobStat.ABORT))


# TODO extend to all objects
# TODO merge ObjectsWithAuth with CustomManager ? and privatise most methods / props ?
class ObjectsWithAuth(CustomManager):
	def __init__(self):
		super(ObjectsWithAuth, self).__init__()

	# clem 21/06/2016
	@property
	def is_owner_or_raise(self):
		""" Check if context user is owner of the DB record, similar to self.has_full_access,

		but raise instead of returning False

		:return: True
		:rtype: bool
		:raise: PermissionDenied if not
		"""
		# Enforce access rights
		if not self.has_full_access:
			raise PermissionDenied(user=self.context_user, message=self.context_obj.id if self.context_obj else '')
		return True

	# clem 21/06/2016
	@property
	def can_read_or_raise(self):
		""" Check if context user has read access to the DB record, similar to self.has_read_access,

		but raise instead of returning False

		:return: True
		:rtype: bool
		:raise: PermissionDenied if not
		"""
		# Enforce access rights
		if not self.has_read_access:
			raise PermissionDenied(user=self.context_user)
		return True

	# clem 21/06/2016
	def set_read_only_or_raise(self):
		""" Set the context object to read-only if the object has this property / attribute and raise if not

		:return: if success
		:rtype: bool
		:raise: NotImplementedError
		"""
		if not self.set_read_only(): # set object to Read-Only
			raise ObjectHasNoReadOnlySupport

	def owner_get(self, request, obj_id, fail_ex=Http404):
		""" Ensure that job/report designated by obj_id exists or fail with 404

		Ensure that current user is OWNER of said object (or admin) or fail with 403
		implements admin bypass if settings.SU_ACCESS_OVERRIDE is True

		:param request: Django Http request object
		:type request: django.http.HttpRequest
		:param obj_id: table pk of the requested object
		:type obj_id: int
		:param fail_ex: an exception to raise in case of failure
		:type fail_ex: Exception
		:return: requested object instance
		:rtype: type(self.model)
		"""
		try:
			self.user_get(id=obj_id, user=request.user)
			if self.is_owner_or_raise:
				return self.context_obj
		except (ObjectDoesNotExist, PermissionDenied, InvalidArguments, ObjectHasNoReadOnlySupport):
			assert callable(fail_ex)
			raise fail_ex()

	def read_get(self, request, obj_id, fail_ex=Http404):
		""" Ensure that job/report designated by obj_id exists or fail with 404

		Ensure that current user has read access to said object or fail with 403
		implements admin bypass if settings.SU_ACCESS_OVERRIDE is True (still RO)

		:param request: Django Http request object
		:type request: django.http.HttpRequest
		:param obj_id: table pk of the requested object
		:type obj_id: int
		:param fail_ex: an exception to raise in case of failure
		:type fail_ex: Exception
		:return: requested object instance as Read-Only (EVEN FOR ADMINS)
		:rtype: type(self.model)
		"""
		try:
			self.secure_get(id=obj_id, user=request.user)
			self.set_read_only_or_raise() # set to RO event if user is owner or admin
			return self.context_obj
		except (ObjectDoesNotExist, PermissionDenied, InvalidArguments, ObjectHasNoReadOnlySupport):
			assert callable(fail_ex)
			raise fail_ex()

	def secure_get(self, **kwargs):
		""" Get and return the object is user is its owner or admin (with settings.SU_ACCESS_OVERRIDE = True)

		and return it as RO if the user only has read access to it (not owner but shared to him)

		:param kwargs: {id: int or pk: int, user: models.User}
		:type kwargs: dict
		:return:
		:rtype:
		:raises: PermissionDenied, ObjectDoesNotExist, InvalidArguments
		"""
		self.user_get(**kwargs) # get the object if it exists

		# Enforce user access restrictions
		if not self.has_full_access:
			if self.has_read_access:
				self.set_read_only_or_raise()
				return self.context_obj
			raise PermissionDenied(user=self.context_user, message='%s' % kwargs.get('id', '') or kwargs.get('pk', ''))
		return self.context_obj


class WorkersManager(ObjectsWithAuth):
	"""
	Overrides change the name of the fields parameters in a QuerySet
	this allow legacy backward compatibility with the new Runnable class
	while not needing to change all the query everywhere in the code.

	The Runnable allows to use unified name for fields, while keeping the old database models #TODO migrate
	From now on, every request to Report and Jobs should be done trough included request filters
	"""
	def __init__(self, inst_type=None):
		self.inst_type = inst_type
		super(WorkersManager, self).__init__()

	##
	# Overrides proxies
	##
	def get_query_set(self):
		"""
		:rtype: QuerySet
		"""
		return QuerySet(self.model, using=self._db)

	def filter(self, *args, **kwargs):
		args, kwargs = translate(args, kwargs)
		# return super(WorkersManager, self).filter(*args, **kwargs)
		return self.get_query_set().filter(*args, **kwargs)

	def annotate(self, *args, **kwargs):
		args, kwargs = translate(args, kwargs)
		return super(WorkersManager, self).annotate(*args, **kwargs)

	def get(self, *args, **kwargs):
		args, kwargs = translate(args, kwargs)
		a = super(WorkersManager, self).get(*args, **kwargs)
		if self.inst_type:
			assert isinstance(a, self.inst_type)
		return a

	def exclude(self, *args, **kwargs):
		args, kwargs = translate(args, kwargs)
		return super(WorkersManager, self).exclude(*args, **kwargs)

	def order_by(self, *args, **kwargs):
		args, kwargs = translate(args, kwargs)
		return super(WorkersManager, self).order_by(*args, **kwargs)

	def all(self):
		return self.get_query_set()

	@property
	def f(self):
		return self.all()


# clem 19/04/2016
class ProjectManager(ObjectsWithAuth):
	def __init__(self):
		super(ProjectManager, self).__init__()

	def available(self, user):
		""" a list of projects available to the specified user

		:type user:
		:rtype: list
		"""
		return super(ProjectManager, self).exclude(
			~org_Q(author__exact=user) & org_Q(collaborative=False)).order_by("name")


# clem 20/10/2016
class CompTargetsManager(CustomManager):
	use_for_related_fields = True
	
	# clem 26/05/2016
	def _target_objects(self, only_enabled=False, only_ready=False):
		""" Get possibly available targets for this ReportType

		:param only_enabled: Filter out targets that are not marked as enabled in the DB
		:type only_enabled: bool
		:param only_ready:
			Filter out targets that have disabled dependencies (exec or engine) (this implies only_enabled)
		:type only_ready: bool
		:return:
		:rtype: original_QS
		"""
		base = super(CompTargetsManager, self)
		targets = base.filter(_enabled=True) if only_enabled or only_ready else base.all()
		
		from copy import copy
		targets2 = copy(targets)
		# assert isinstance(targets2, original_QS) and isinstance(targets, original_QS)
		# from models import ComputeTarget
		for each in targets:
			# assert isinstance(each, ComputeTarget)
			if only_ready and not each.is_ready:
				targets2 = targets2.exclude(pk=each.id)
		return targets2
	
	# clem 26/05/2016
	def get_enabled(self):
		""" A list of enabled ComputeTarget objects that are available to use with this ReportType

		:return:
		:rtype: original_QS
		"""
		return self._target_objects(only_enabled=True)
		
	# clem 26/05/2016
	def get_ready(self):
		""" A list of ready to use ComputeTarget objects that are available to use with this ReportType

		This means that they are explicitly marked as enabled in the DB,
		And, each resources they depend on (exec and engine) are also enabled

		:return:
		:rtype: original_QS
		"""
		return self._target_objects(only_ready=True)


# clem 26/10/2016
class CustomUserManager(Manager):
	def __send_mail(self, user):
		from django.core.mail import EmailMessage

		msg_text = 'User %s : %s %s (%s) was just created at %s.' % \
			(user.username, user.first_name, user.last_name, user.email, settings.CURRENT_FQDN)
		msg = EmailMessage('New user "%s" created' % user.username, msg_text, 'Breeze PMS', [settings.ADMINS[1]])
		result = msg.send()
	
	def create(self, **kwargs):
		print 'custom_user_create'
		has_name_info_domains = ['fimm.fi', 'ki.se', 'scilifelab.se']
		email = kwargs.get('email', '')
		pass_on = kwargs
		pass_on['is_active'] = True
		user_institute = ''
		if email and '@' in email and '.' in email:
			full_split = email.split('@')
			nick = full_split[0].split('.')
			domain = full_split[1]
			if domain == 'ki.se':
				domain = 'scilifelab.se'
			if domain in has_name_info_domains:
				pass_on['first_name'] = nick[0]
				pass_on['last_name'] = nick[1]
			try:
				from breeze.models import Institute
				user_institute = Institute.objects.get(domain=domain)
			except Exception as e:
				from utilz import logger
				logger.exception(str(e))
			
		user = super(CustomUserManager, self).create(**pass_on)
		
		# TODO alert admin about new user
		if user_institute:
			user.userprofile.institute_info = user_institute
			user.userprofile.save()
			user.save()
		self.__send_mail(user)
		return user


# clem 19/01/2016
class UserManager(Manager):
	def dump(self):
		return super(UserManager, self)
	
	def all(self):
		return super(UserManager, self).filter(user_id__is_active=True)
	
	def filter(self, *args, **kwargs):
		return self.all().filter(*args, **kwargs)
	
	def exclude(self, *args, **kwargs):
		return self.all().exclude(*args, **kwargs)
	
	def get(self, *args, **kwargs):
		return self.all().get(*args, **kwargs)
