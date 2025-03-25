"""
Models for Student Information

Replication Notes

TODO: Update this to be consistent with reality  (no portal servers, no more askbot)

In our live deployment, we intend to run in a scenario where there is a pool of
Portal servers that hold the canoncial user information and that user
information is replicated to slave Course server pools. Each Course has a set of
servers that serves only its content and has users that are relevant only to it.

We replicate the following tables into the Course DBs where the user is
enrolled. Only the Portal servers should ever write to these models.
* UserProfile
* CourseEnrollment

We do a partial replication of:
* User -- Askbot extends this and uses the extra fields, so we replicate only
          the stuff that comes with basic django_auth and ignore the rest.)

There are a couple different scenarios:

1. There's an update of User or UserProfile -- replicate it to all Course DBs
   that the user is enrolled in (found via CourseEnrollment).
2. There's a change in CourseEnrollment. We need to push copies of UserProfile,
   CourseEnrollment, and the base fields in User

Migration Notes

If you make changes to this model, be sure to create an appropriate migration
file and check it in at the same time as your model changes. To do that,

1. Go to the mitx dir
2. django-admin.py schemamigration student --auto --settings=lms.envs.dev --pythonpath=. description_of_your_change
3. Add the migration file created in mitx/common/djangoapps/student/migrations/
"""
from datetime import datetime
import hashlib
import json
import logging
import uuid
from random import randint
from time import strftime


from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.forms import ModelForm, forms

import comment_client as cc

log = logging.getLogger(__name__)


class UserProfile(models.Model):
    """This is where we store all the user demographic fields. We have a
    separate table for this rather than extending the built-in Django auth_user.

    Notes:
        * Some fields are legacy ones from the first run of 6.002, from which
          we imported many users.
        * Fields like name and address are intentionally open ended, to account
          for international variations. An unfortunate side-effect is that we
          cannot efficiently sort on last names for instance.

    Replication:
        * Only the Portal servers should ever modify this information.
        * All fields are replicated into relevant Course databases

    Some of the fields are legacy ones that were captured during the initial
    MITx fall prototype.
    """

    class Meta:
        db_table = "auth_userprofile"

    ## CRITICAL TODO/SECURITY
    # Sanitize all fields.
    # This is not visible to other users, but could introduce holes later
    user = models.OneToOneField(User, unique=True, db_index=True, related_name='profile')
    name = models.CharField(blank=True, max_length=255, db_index=True)

    meta = models.TextField(blank=True)  # JSON dictionary for future expansion
    courseware = models.CharField(blank=True, max_length=255, default='course.xml')

    # Location is no longer used, but is held here for backwards compatibility
    # for users imported from our first class.
    language = models.CharField(blank=True, max_length=255, db_index=True)
    location = models.CharField(blank=True, max_length=255, db_index=True)

    # Optional demographic data we started capturing from Fall 2012
    this_year = datetime.now().year
    VALID_YEARS = range(this_year, this_year - 120, -1)
    year_of_birth = models.IntegerField(blank=True, null=True, db_index=True)
    GENDER_CHOICES = (('m', 'Male'), ('f', 'Female'), ('o', 'Other'))
    gender = models.CharField(blank=True, null=True, max_length=6, db_index=True,
                              choices=GENDER_CHOICES)
    LEVEL_OF_EDUCATION_CHOICES = (('p_se', 'Doctorate in science or engineering'),
                                  ('p_oth', 'Doctorate in another field'),
                                  ('m', "Master's or professional degree"),
                                  ('b', "Bachelor's degree"),
                                  ('hs', "Secondary/high school"),
                                  ('jhs', "Junior secondary/junior high/middle school"),
                                  ('el', "Elementary/primary school"),
                                  ('none', "None"),
                                  ('other', "Other"))
    level_of_education = models.CharField(
                            blank=True, null=True, max_length=6, db_index=True,
                            choices=LEVEL_OF_EDUCATION_CHOICES
                         )
    mailing_address = models.TextField(blank=True, null=True)
    goals = models.TextField(blank=True, null=True)

    def get_meta(self):
        js_str = self.meta
        if not js_str:
            js_str = dict()
        else:
            js_str = json.loads(self.meta)

        return js_str

    def set_meta(self, js):
        self.meta = json.dumps(js)

TEST_CENTER_STATUS_ACCEPTED = "Accepted"
TEST_CENTER_STATUS_ERROR = "Error"

class TestCenterUser(models.Model):
    """This is our representation of the User for in-person testing, and
    specifically for Pearson at this point. A few things to note:

    * Pearson only supports Latin-1, so we have to make sure that the data we
      capture here will work with that encoding.
    * While we have a lot of this demographic data in UserProfile, it's much
      more free-structured there. We'll try to pre-pop the form with data from
      UserProfile, but we'll need to have a step where people who are signing
      up re-enter their demographic data into the fields we specify.
    * Users are only created here if they register to take an exam in person.

    The field names and lengths are modeled on the conventions and constraints
    of Pearson's data import system, including oddities such as suffix having
    a limit of 255 while last_name only gets 50.
    
    Also storing here the confirmation information received from Pearson (if any) 
    as to the success or failure of the upload.  (VCDC file)
    """
    # Our own record keeping...
    user = models.ForeignKey(User, unique=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    # user_updated_at happens only when the user makes a change to their data,
    # and is something Pearson needs to know to manage updates. Unlike
    # updated_at, this will not get incremented when we do a batch data import.
    user_updated_at = models.DateTimeField(db_index=True)

    # Unique ID we assign our user for the Test Center.
    client_candidate_id = models.CharField(unique=True, max_length=50, db_index=True)

    # Name
    first_name = models.CharField(max_length=30, db_index=True)
    last_name = models.CharField(max_length=50, db_index=True)
    middle_name = models.CharField(max_length=30, blank=True)
    suffix = models.CharField(max_length=255, blank=True)
    salutation = models.CharField(max_length=50, blank=True)

    # Address
    address_1 = models.CharField(max_length=40)
    address_2 = models.CharField(max_length=40, blank=True)
    address_3 = models.CharField(max_length=40, blank=True)
    city = models.CharField(max_length=32, db_index=True)
    # state example: HI -- they have an acceptable list that we'll just plug in
    # state is required if you're in the US or Canada, but otherwise not.
    state = models.CharField(max_length=20, blank=True, db_index=True)
    # postal_code required if you're in the US or Canada
    postal_code = models.CharField(max_length=16, blank=True, db_index=True)
    # country is a ISO 3166-1 alpha-3 country code (e.g. "USA", "CAN", "MNG")
    country = models.CharField(max_length=3, db_index=True)

    # Phone
    phone = models.CharField(max_length=35)
    extension = models.CharField(max_length=8, blank=True, db_index=True)
    phone_country_code = models.CharField(max_length=3, db_index=True)
    fax = models.CharField(max_length=35, blank=True)
    # fax_country_code required *if* fax is present.
    fax_country_code = models.CharField(max_length=3, blank=True)

    # Company
    company_name = models.CharField(max_length=50, blank=True, db_index=True)

    # time at which edX sent the registration to the test center
    uploaded_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # confirmation back from the test center, as well as timestamps
    # on when they processed the request, and when we received 
    # confirmation back.
    processed_at = models.DateTimeField(null=True, db_index=True)
    upload_status = models.CharField(max_length=20, blank=True, db_index=True)  # 'Error' or 'Accepted'
    upload_error_message = models.CharField(max_length=512, blank=True)
    # Unique ID given to us for this User by the Testing Center. It's null when
    # we first create the User entry, and may be assigned by Pearson later.
    # (However, it may never be set if we are always initiating such candidate creation.)
    candidate_id = models.IntegerField(null=True, db_index=True)
    confirmed_at = models.DateTimeField(null=True, db_index=True)

    @property
    def needs_uploading(self):
        return self.uploaded_at is None or self.uploaded_at < self.user_updated_at
    
    @staticmethod
    def user_provided_fields():
        return [ 'first_name', 'middle_name', 'last_name', 'suffix', 'salutation', 
                'address_1', 'address_2', 'address_3', 'city', 'state', 'postal_code', 'country', 
                'phone', 'extension', 'phone_country_code', 'fax', 'fax_country_code', 'company_name']
        
    @property
    def email(self):
        return self.user.email
    
    def needs_update(self, fields):
        for fieldname in TestCenterUser.user_provided_fields():
            if fieldname in fields and getattr(self, fieldname) != fields[fieldname]:
                return True
            
        return False    
                       
    @staticmethod
    def _generate_edx_id(prefix):
        NUM_DIGITS = 12
        return u"{}{:012}".format(prefix, randint(1, 10**NUM_DIGITS-1))
    
    @staticmethod
    def _generate_candidate_id():
        return TestCenterUser._generate_edx_id("edX")
        
    @classmethod
    def create(cls, user):
        testcenter_user = cls(user=user)
        # testcenter_user.candidate_id remains unset    
        # assign an ID of our own:
        cand_id = cls._generate_candidate_id()
        while TestCenterUser.objects.filter(client_candidate_id=cand_id).exists():
            cand_id = cls._generate_candidate_id()
        testcenter_user.client_candidate_id = cand_id  
        return testcenter_user

    @property
    def is_accepted(self):
        return self.upload_status == TEST_CENTER_STATUS_ACCEPTED
  
    @property
    def is_rejected(self):
        return self.upload_status == TEST_CENTER_STATUS_ERROR
    
    @property
    def is_pending(self):
        return not self.is_accepted and not self.is_rejected

class TestCenterUserForm(ModelForm):
    class Meta:
        model = TestCenterUser
        fields = ( 'first_name', 'middle_name', 'last_name', 'suffix', 'salutation', 
                'address_1', 'address_2', 'address_3', 'city', 'state', 'postal_code', 'country', 
                'phone', 'extension', 'phone_country_code', 'fax', 'fax_country_code', 'company_name')
        
    def update_and_save(self):
        new_user = self.save(commit=False)
        # create additional values here:
        new_user.user_updated_at = datetime.utcnow()
        new_user.save()
        log.info("Updated demographic information for user's test center exam registration: username \"{}\" ".format(new_user.username)) 
        
    # add validation:
    
    def clean_country(self):
        code = self.cleaned_data['country']
        if code and len(code) != 3:
            raise forms.ValidationError(u'Must be three characters (ISO 3166-1):  e.g. USA, CAN, MNG')
        return code
                
    def clean(self):
        def _can_encode_as_latin(fieldvalue):
            try:
                fieldvalue.encode('iso-8859-1')
            except UnicodeEncodeError:
                return False
            return True
        
        cleaned_data = super(TestCenterUserForm, self).clean()
        
        # check for interactions between fields:
        if 'country' in cleaned_data:
            country = cleaned_data.get('country')
            if country == 'USA' or country == 'CAN':
                if 'state' in cleaned_data and len(cleaned_data['state']) == 0:
                    self._errors['state'] = self.error_class([u'Required if country is USA or CAN.'])                
                    del cleaned_data['state']

                if 'postal_code' in cleaned_data and len(cleaned_data['postal_code']) == 0:
                    self._errors['postal_code'] = self.error_class([u'Required if country is USA or CAN.'])                
                    del cleaned_data['postal_code']
                    
        if 'fax' in cleaned_data and len(cleaned_data['fax']) > 0 and 'fax_country_code' in cleaned_data and len(cleaned_data['fax_country_code']) == 0:
            self._errors['fax_country_code'] = self.error_class([u'Required if fax is specified.'])                
            del cleaned_data['fax_country_code']

        # check encoding for all fields:
        cleaned_data_fields = [fieldname for fieldname in cleaned_data]
        for fieldname in cleaned_data_fields:
            if not _can_encode_as_latin(cleaned_data[fieldname]):
                self._errors[fieldname] = self.error_class([u'Must only use characters in Latin-1 (iso-8859-1) encoding'])                
                del cleaned_data[fieldname]

        # Always return the full collection of cleaned data.
        return cleaned_data
        
# our own code to indicate that a request has been rejected. 
ACCOMMODATION_REJECTED_CODE = 'NONE'        
   
ACCOMMODATION_CODES = (
                      (ACCOMMODATION_REJECTED_CODE, 'No Accommodation Granted'), 
                      ('EQPMNT', 'Equipment'),
                      ('ET12ET', 'Extra Time - 1/2 Exam Time'),
                      ('ET30MN', 'Extra Time - 30 Minutes'),
                      ('ETDBTM', 'Extra Time - Double Time'),
                      ('SEPRMM', 'Separate Room'),
                      ('SRREAD', 'Separate Room and Reader'),
                      ('SRRERC', 'Separate Room and Reader/Recorder'),
                      ('SRRECR', 'Separate Room and Recorder'),
                      ('SRSEAN', 'Separate Room and Service Animal'),
                      ('SRSGNR', 'Separate Room and Sign Language Interpreter'), 
                      )

ACCOMMODATION_CODE_DICT = { code : name for (code, name) in ACCOMMODATION_CODES }
    
class TestCenterRegistration(models.Model):
    """
    This is our representation of a user's registration for in-person testing,
    and specifically for Pearson at this point. A few things to note:

    * Pearson only supports Latin-1, so we have to make sure that the data we
      capture here will work with that encoding.  This is less of an issue
      than for the TestCenterUser.
    * Registrations are only created here when a user registers to take an exam in person.

    The field names and lengths are modeled on the conventions and constraints
    of Pearson's data import system.
    """
    # to find an exam registration, we key off of the user and course_id.
    # If multiple exams per course are possible, we would also need to add the 
    # exam_series_code.
    testcenter_user = models.ForeignKey(TestCenterUser, default=None)
    course_id = models.CharField(max_length=128, db_index=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    # user_updated_at happens only when the user makes a change to their data,
    # and is something Pearson needs to know to manage updates. Unlike
    # updated_at, this will not get incremented when we do a batch data import.
    # The appointment dates, the exam count, and the accommodation codes can be updated, 
    # but hopefully this won't happen often.
    user_updated_at = models.DateTimeField(db_index=True)
    # "client_authorization_id" is our unique identifier for the authorization.  
    # This must be present for an update or delete to be sent to Pearson.
    client_authorization_id = models.CharField(max_length=20, unique=True, db_index=True)

    # information about the test, from the course policy:
    exam_series_code = models.CharField(max_length=15, db_index=True)
    eligibility_appointment_date_first = models.DateField(db_index=True)
    eligibility_appointment_date_last = models.DateField(db_index=True)

    # this is really a list of codes, using an '*' as a delimiter.
    # So it's not a choice list.  We use the special value of ACCOMMODATION_REJECTED_CODE 
    # to indicate the rejection of an accommodation request.
    accommodation_code = models.CharField(max_length=64, blank=True)
    
    # store the original text of the accommodation request.
    accommodation_request = models.CharField(max_length=1024, blank=True, db_index=True)

    # time at which edX sent the registration to the test center
    uploaded_at = models.DateTimeField(null=True, db_index=True)

    # confirmation back from the test center, as well as timestamps
    # on when they processed the request, and when we received 
    # confirmation back.
    processed_at = models.DateTimeField(null=True, db_index=True)
    upload_status = models.CharField(max_length=20, blank=True, db_index=True)  # 'Error' or 'Accepted'
    upload_error_message = models.CharField(max_length=512, blank=True)
    # Unique ID given to us for this registration by the Testing Center. It's null when
    # we first create the registration entry, and may be assigned by Pearson later.
    # (However, it may never be set if we are always initiating such candidate creation.)
    authorization_id = models.IntegerField(null=True, db_index=True)
    confirmed_at = models.DateTimeField(null=True, db_index=True)
    
    @property
    def candidate_id(self):
        return self.testcenter_user.candidate_id
    
    @property
    def client_candidate_id(self):
        return self.testcenter_user.client_candidate_id

    @property
    def authorization_transaction_type(self):
        if self.authorization_id is not None:
            return 'Update'
        elif self.uploaded_at is None:
            return 'Add'
        else:
            # TODO: decide what to send when we have uploaded an initial version,
            # but have not received confirmation back from that upload.  If the 
            # registration here has been changed, then we don't know if this changed
            # registration should be submitted as an 'add' or an 'update'. 
            #
            # If the first registration were lost or in error (e.g. bad code), 
            # the second should be an "Add".  If the first were processed successfully,
            # then the second should be an "Update".  We just don't know....
            return 'Update'
        
    @property
    def exam_authorization_count(self):
        # TODO: figure out if this should really go in the database (with a default value).
        return 1
    
    @classmethod
    def create(cls, testcenter_user, exam, accommodation_request):
        registration = cls(testcenter_user = testcenter_user)
        registration.course_id = exam.course_id
        registration.accommodation_request = accommodation_request.strip()
        registration.exam_series_code = exam.exam_series_code
        registration.eligibility_appointment_date_first = strftime("%Y-%m-%d", exam.first_eligible_appointment_date)
        registration.eligibility_appointment_date_last = strftime("%Y-%m-%d", exam.last_eligible_appointment_date)
        registration.client_authorization_id = cls._create_client_authorization_id()
        # accommodation_code remains blank for now, along with Pearson confirmation information
        return registration

    @staticmethod
    def _generate_authorization_id():
        return TestCenterUser._generate_edx_id("edXexam")
        
    @staticmethod
    def _create_client_authorization_id():
        """
        Return a unique id for a registration, suitable for using as an authorization code
        for Pearson.  It must fit within 20 characters.
        """
        # generate a random value, and check to see if it already is in use here
        auth_id = TestCenterRegistration._generate_authorization_id()
        while TestCenterRegistration.objects.filter(client_authorization_id=auth_id).exists():
            auth_id = TestCenterRegistration._generate_authorization_id()
        return auth_id
            
    # methods for providing registration status details on registration page:        
    @property
    def demographics_is_accepted(self):
        return self.testcenter_user.is_accepted

    @property
    def demographics_is_rejected(self):
        return self.testcenter_user.is_rejected
                
    @property
    def demographics_is_pending(self):
        return self.testcenter_user.is_pending

    @property
    def accommodation_is_accepted(self):
        return len(self.accommodation_request) > 0 and len(self.accommodation_code) > 0 and self.accommodation_code != ACCOMMODATION_REJECTED_CODE

    @property
    def accommodation_is_rejected(self):
        return len(self.accommodation_request) > 0 and self.accommodation_code == ACCOMMODATION_REJECTED_CODE
            
    @property
    def accommodation_is_pending(self):
        return len(self.accommodation_request) > 0 and len(self.accommodation_code) == 0

    @property
    def accommodation_is_skipped(self):
        return len(self.accommodation_request) == 0

    @property
    def registration_is_accepted(self):
        return self.upload_status == TEST_CENTER_STATUS_ACCEPTED
  
    @property
    def registration_is_rejected(self):
        return self.upload_status == TEST_CENTER_STATUS_ERROR
    
    @property
    def registration_is_pending(self):
        return not self.registration_is_accepted and not self.registration_is_rejected

    # methods for providing registration status summary on dashboard page:        
    @property
    def is_accepted(self):
        return self.registration_is_accepted and self.demographics_is_accepted
  
    @property
    def is_rejected(self):
        return self.registration_is_rejected or self.demographics_is_rejected

    @property
    def is_pending(self):
        return not self.is_accepted and not self.is_rejected
    
    def get_accommodation_codes(self):
        return self.accommodation_code.split('*')

    def get_accommodation_names(self):
        return [ ACCOMMODATION_CODE_DICT.get(code, "Unknown code " + code) for code in self.get_accommodation_codes() ]         

    @property
    def registration_signup_url(self):
        return settings.PEARSONVUE_SIGNINPAGE_URL
    
class TestCenterRegistrationForm(ModelForm):
    class Meta:
        model = TestCenterRegistration
        fields = ( 'accommodation_request', 'accommodation_code' )

    def clean_accommodation_request(self):
        code = self.cleaned_data['accommodation_request']
        if code and len(code) > 0:
            return code.strip()
        return code
        
    def update_and_save(self):
        registration = self.save(commit=False)
        # create additional values here:
        registration.user_updated_at = datetime.utcnow()
        registration.save()
        log.info("Updated registration information for user's test center exam registration: username \"{}\" course \"{}\", examcode \"{}\"".format(registration.testcenter_user.user.username, registration.course_id, registration.exam_series_code)) 

    # TODO: add validation code for values added to accommodation_code field.
    
    
    
def get_testcenter_registration(user, course_id, exam_series_code):
    try:
        tcu = TestCenterUser.objects.get(user=user)
    except TestCenterUser.DoesNotExist:
        return []
    return TestCenterRegistration.objects.filter(testcenter_user=tcu, course_id=course_id, exam_series_code=exam_series_code)
        
def unique_id_for_user(user):
    """
    Return a unique id for a user, suitable for inserting into
    e.g. personalized survey links.
    """
    # include the secret key as a salt, and to make the ids unique across
    # different LMS installs.    
    h = hashlib.md5()
    h.update(settings.SECRET_KEY)
    h.update(str(user.id))
    return h.hexdigest()


## TODO: Should be renamed to generic UserGroup, and possibly
# Given an optional field for type of group
class UserTestGroup(models.Model):
    users = models.ManyToManyField(User, db_index=True)
    name = models.CharField(blank=False, max_length=32, db_index=True)
    description = models.TextField(blank=True)


class Registration(models.Model):
    ''' Allows us to wait for e-mail before user is registered. A
        registration profile is created when the user creates an
        account, but that account is inactive. Once the user clicks
        on the activation key, it becomes active. '''
    class Meta:
        db_table = "auth_registration"

    user = models.ForeignKey(User, unique=True)
    activation_key = models.CharField(('activation key'), max_length=32, unique=True, db_index=True)

    def register(self, user):
        # MINOR TODO: Switch to crypto-secure key
        self.activation_key = uuid.uuid4().hex
        self.user = user
        self.save()

    def activate(self):
        self.user.is_active = True
        self.user.save()
        #self.delete()


class PendingNameChange(models.Model):
    user = models.OneToOneField(User, unique=True, db_index=True)
    new_name = models.CharField(blank=True, max_length=255)
    rationale = models.CharField(blank=True, max_length=1024)


class PendingEmailChange(models.Model):
    user = models.OneToOneField(User, unique=True, db_index=True)
    new_email = models.CharField(blank=True, max_length=255, db_index=True)
    activation_key = models.CharField(('activation key'), max_length=32, unique=True, db_index=True)


class CourseEnrollment(models.Model):
    user = models.ForeignKey(User)
    course_id = models.CharField(max_length=255, db_index=True)

    created = models.DateTimeField(auto_now_add=True, null=True, db_index=True)

    class Meta:
        unique_together = (('user', 'course_id'), )

    def __unicode__(self):
        return "[CourseEnrollment] %s: %s (%s)" % (self.user, self.course_id, self.created)


class CourseEnrollmentAllowed(models.Model):
    """
    Table of users (specified by email address strings) who are allowed to enroll in a specified course.
    The user may or may not (yet) exist.  Enrollment by users listed in this table is allowed
    even if the enrollment time window is past.
    """
    email = models.CharField(max_length=255, db_index=True)
    course_id = models.CharField(max_length=255, db_index=True)

    created = models.DateTimeField(auto_now_add=True, null=True, db_index=True)

    class Meta:
        unique_together = (('email', 'course_id'), )

    def __unicode__(self):
        return "[CourseEnrollmentAllowed] %s: %s (%s)" % (self.email, self.course_id, self.created)

#cache_relation(User.profile)

#### Helper methods for use from python manage.py shell.


def get_user(email):
    u = User.objects.get(email=email)
    up = UserProfile.objects.get(user=u)
    return u, up


def user_info(email):
    u, up = get_user(email)
    print "User id", u.id
    print "Username", u.username
    print "E-mail", u.email
    print "Name", up.name
    print "Location", up.location
    print "Language", up.language
    return u, up


def change_email(old_email, new_email):
    u = User.objects.get(email=old_email)
    u.email = new_email
    u.save()


def change_name(email, new_name):
    u, up = get_user(email)
    up.name = new_name
    up.save()


def user_count():
    print "All users", User.objects.all().count()
    print "Active users", User.objects.filter(is_active=True).count()
    return User.objects.all().count()


def active_user_count():
    return User.objects.filter(is_active=True).count()


def create_group(name, description):
    utg = UserTestGroup()
    utg.name = name
    utg.description = description
    utg.save()


def add_user_to_group(user, group):
    utg = UserTestGroup.objects.get(name=group)
    utg.users.add(User.objects.get(username=user))
    utg.save()


def remove_user_from_group(user, group):
    utg = UserTestGroup.objects.get(name=group)
    utg.users.remove(User.objects.get(username=user))
    utg.save()

default_groups = {'email_future_courses': 'Receive e-mails about future MITx courses',
                  'email_helpers': 'Receive e-mails about how to help with MITx',
                  'mitx_unenroll': 'Fully unenrolled -- no further communications',
                  '6002x_unenroll': 'Took and dropped 6002x'}


def add_user_to_default_group(user, group):
    try:
        utg = UserTestGroup.objects.get(name=group)
    except UserTestGroup.DoesNotExist:
        utg = UserTestGroup()
        utg.name = group
        utg.description = default_groups[group]
        utg.save()
    utg.users.add(User.objects.get(username=user))
    utg.save()


@receiver(post_save, sender=User)
def update_user_information(sender, instance, created, **kwargs):
    if not settings.MITX_FEATURES['ENABLE_DISCUSSION_SERVICE']:
        # Don't try--it won't work, and it will fill the logs with lots of errors
        return
    try:
        cc_user = cc.User.from_django_user(instance)
        cc_user.save()
    except Exception as e:
        log = logging.getLogger("mitx.discussion")
        log.error(unicode(e))
        log.error("update user info to discussion failed for user with id: " + str(instance.id))


########################## REPLICATION SIGNALS #################################
# @receiver(post_save, sender=User)
def replicate_user_save(sender, **kwargs):
    user_obj = kwargs['instance']
    if not should_replicate(user_obj):
        return
    for course_db_name in db_names_to_replicate_to(user_obj.id):
        replicate_user(user_obj, course_db_name)


# @receiver(post_save, sender=CourseEnrollment)
def replicate_enrollment_save(sender, **kwargs):
    """This is called when a Student enrolls in a course. It has to do the
    following:

    1. Make sure the User is copied into the Course DB. It may already exist
       (someone deleting and re-adding a course). This has to happen first or
       the foreign key constraint breaks.
    2. Replicate the CourseEnrollment.
    3. Replicate the UserProfile.
    """
    if not is_portal():
        return

    enrollment_obj = kwargs['instance']
    log.debug("Replicating user because of new enrollment")
    for course_db_name in db_names_to_replicate_to(enrollment_obj.user.id):
        replicate_user(enrollment_obj.user, course_db_name)

    log.debug("Replicating enrollment because of new enrollment")
    replicate_model(CourseEnrollment.save, enrollment_obj, enrollment_obj.user_id)

    log.debug("Replicating user profile because of new enrollment")
    user_profile = UserProfile.objects.get(user_id=enrollment_obj.user_id)
    replicate_model(UserProfile.save, user_profile, enrollment_obj.user_id)


# @receiver(post_delete, sender=CourseEnrollment)
def replicate_enrollment_delete(sender, **kwargs):
    enrollment_obj = kwargs['instance']
    return replicate_model(CourseEnrollment.delete, enrollment_obj, enrollment_obj.user_id)


# @receiver(post_save, sender=UserProfile)
def replicate_userprofile_save(sender, **kwargs):
    """We just updated the UserProfile (say an update to the name), so push that
    change to all Course DBs that we're enrolled in."""
    user_profile_obj = kwargs['instance']
    return replicate_model(UserProfile.save, user_profile_obj, user_profile_obj.user_id)


######### Replication functions #########
USER_FIELDS_TO_COPY = ["id", "username", "first_name", "last_name", "email",
                       "password", "is_staff", "is_active", "is_superuser",
                       "last_login", "date_joined"]


def replicate_user(portal_user, course_db_name):
    """Replicate a User to the correct Course DB. This is more complicated than
    it should be because Askbot extends the auth_user table and adds its own
    fields. So we need to only push changes to the standard fields and leave
    the rest alone so that Askbot changes at the Course DB level don't get
    overridden.
    """
    try:
        course_user = User.objects.using(course_db_name).get(id=portal_user.id)
        log.debug("User {0} found in Course DB, replicating fields to {1}"
                  .format(course_user, course_db_name))
    except User.DoesNotExist:
        log.debug("User {0} not found in Course DB, creating copy in {1}"
                  .format(portal_user, course_db_name))
        course_user = User()

    for field in USER_FIELDS_TO_COPY:
        setattr(course_user, field, getattr(portal_user, field))

    mark_handled(course_user)
    course_user.save(using=course_db_name)
    unmark(course_user)


def replicate_model(model_method, instance, user_id):
    """
    model_method is the model action that we want replicated. For instance,
                 UserProfile.save
    """
    if not should_replicate(instance):
        return

    course_db_names = db_names_to_replicate_to(user_id)
    log.debug("Replicating {0} for user {1} to DBs: {2}"
              .format(model_method, user_id, course_db_names))

    mark_handled(instance)
    for db_name in course_db_names:
        model_method(instance, using=db_name)
    unmark(instance)


######### Replication Helpers #########


def is_valid_course_id(course_id):
    """Right now, the only database that's not a course database is 'default'.
    I had nicer checking in here originally -- it would scan the courses that
    were in the system and only let you choose that. But it was annoying to run
    tests with, since we don't have course data for some for our course test
    databases. Hence the lazy version.
    """
    return course_id != 'default'


def is_portal():
    """Are we in the portal pool? Only Portal servers are allowed to replicate
    their changes. For now, only Portal servers see multiple DBs, so we use
    that to decide."""
    return len(settings.DATABASES) > 1


def db_names_to_replicate_to(user_id):
    """Return a list of DB names that this user_id is enrolled in."""
    return [c.course_id
            for c in CourseEnrollment.objects.filter(user_id=user_id)
            if is_valid_course_id(c.course_id)]


def marked_handled(instance):
    """Have we marked this instance as being handled to avoid infinite loops
    caused by saving models in post_save hooks for the same models?"""
    return hasattr(instance, '_do_not_copy_to_course_db') and instance._do_not_copy_to_course_db


def mark_handled(instance):
    """You have to mark your instance with this function or else we'll go into
    an infinite loop since we're putting listeners on Model saves/deletes and
    the act of replication requires us to call the same model method.

    We create a _replicated attribute to differentiate the first save of this
    model vs. the duplicate save we force on to the course database. Kind of
    a hack -- suggestions welcome.
    """
    instance._do_not_copy_to_course_db = True


def unmark(instance):
    """If we don't unmark a model after we do replication, then consecutive
    save() calls won't be properly replicated."""
    instance._do_not_copy_to_course_db = False


def should_replicate(instance):
    """Should this instance be replicated? We need to be a Portal server and
    the instance has to not have been marked_handled."""
    if marked_handled(instance):
        # Basically, avoid an infinite loop. You should
        log.debug("{0} should not be replicated because it's been marked"
                  .format(instance))
        return False
    if not is_portal():
        log.debug("{0} should not be replicated because we're not a portal."
                  .format(instance))
        return False
    return True
