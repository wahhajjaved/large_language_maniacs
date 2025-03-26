import arrow, os
from faypublic.settings import AWS_S3_ENDPOINT_URL, AWS_STORAGE_BUCKET_NAME
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

# Create your models here.

def get_user_display_name(self):
    return self.first_name + ' ' + self.last_name + ' [' + self.username + ']'
User.add_to_class('__str__', get_user_display_name)
User.add_to_class('__unicode__', get_user_display_name)


class Badge(models.Model):
    title = models.CharField(max_length=255, null=False, blank=False)
    image = models.ImageField(null=True, blank=False)

    def __str__(self):
        return self.title

    def __unicode__(self):
        return self.title





def handle_file_upload(profile, filename):
    timestamp = arrow.utcnow().timestamp
    return 'uploads/{0}/profile-photos/{1}-{2}'.format(profile.user.username, timestamp, filename)

def validate_photo_extension(file):
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif']
    ext = os.path.splitext(file.name)[1]
    if not ext.lower() in valid_extensions:
        raise ValidationError('Invalid file type; please use .jpg, .jpeg, .png, or .gif')

class UserProfile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    # additional user information we want to collect
    profile_photo = models.FileField(upload_to=handle_file_upload, null=True, validators=[validate_photo_extension])
    street_address = models.CharField(max_length=255, null=True, blank=False)
    city = models.CharField(max_length=255, null=True, blank=False)
    state = models.CharField(max_length=255, null=True, blank=False)
    zipcode = models.IntegerField(null=True, blank=False)
    phone_number = models.CharField(max_length=15, null=True, blank=False)
    birthdate = models.DateField(null=True, blank=False)
    badges = models.ManyToManyField(Badge, related_name="users_with_badge_awarded", blank=True)
    get_sms_reminders = models.BooleanField(default=False, blank=True)
    get_email_reminders = models.BooleanField(default=False, blank=True)

    def earned_badges(self):
        registrations = self.user.classregistration_set.filter(completed=True)

        badges = []

        for b in self.badges.all():
            badges.append(b)

        for reg in registrations:
            sect = reg.class_section
            course = sect.class_key
            for badge in course.awarded_badges.all():
                if not badge in badges:
                    badges.append(badge)

        return badges

    def can_register_for_class(self, course):
        user_badges = self.earned_badges()

        for req in course.prerequisite_badges.all():
            if req not in user_badges:
                return False

        return True

    def can_checkout_equipment(self, item):
        user_badges = self.earned_badges()

        for req in item.prerequisite_badges.all():
            if req not in user_badges:
                return False
        
        return True

    def projects(self):
        projects = []

        for p in self.user.owner_projects.all():
            projects.append(p)
        
        for p in self.user.project_set.all():
            projects.append(p)

        return projects

    def get_profile_photo_uri(self):
        if self.profile_photo:
            return AWS_S3_ENDPOINT_URL + '/' + AWS_STORAGE_BUCKET_NAME + '/' + self.profile_photo.url
        return None