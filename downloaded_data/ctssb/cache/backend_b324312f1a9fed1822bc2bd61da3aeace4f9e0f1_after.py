import binascii
import random
import string
import PyArgon2
from django.db import models
from django.db.models.signals import class_prepared
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.utils.timezone import now
from django.core.validators import MaxValueValidator, MinValueValidator, MaxLengthValidator
from django.utils.crypto import get_random_string
from django.conf import settings
from phonenumber_field.modelfields import PhoneNumberField

# Create your models here.

def longer_password(sender, *args, **kwargs):
    if (sender.__name__ == "User" and
        sender.__module__ == "vigilate_backend.models"):
        patch_password(sender)
class_prepared.connect(longer_password)

def patch_password(model):
    #expand size of password defined in AbstractBaseUser
    password = model._meta.get_field('password')
    password.max_length = 200
    for v in password.validators:
        if isinstance(v, MaxLengthValidator):
            v.limit_value = 200

class UserManager(BaseUserManager):

    def create_user(self, email, password):
        email = self.normalize_email(email)
        user = self.model(email=email)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password):
        user = self.create_user(email, password)
        user.is_superuser = True
        user.save()
        return user

class User(AbstractBaseUser):
    """User model
    """

    id = models.AutoField(primary_key=True, unique=True)
    email = models.EmailField(max_length=50, unique=True)
    phone = PhoneNumberField(null=True, blank=True)
    user_type = models.IntegerField(null=False, default=0)
    contrat = models.IntegerField(null=False, default=0)
    id_dealer = models.IntegerField(default=0)

    is_superuser = models.BooleanField(default=False)
    is_active = True

    EMAIL = "EMAIL"
    SMS = "SMS"
    WEB = "WEB"
    NONE = "NONE"

    ALERT_TYPE = (
        (EMAIL, 'Email'),
        (SMS, 'Sms'),
        (WEB, 'Web'),
        (NONE, None)
    )
    default_alert_type = models.CharField(max_length=5,
                                          choices=ALERT_TYPE,
                                          default=EMAIL)

    # setup to be able to our User as default django user
    REQUIRED_FIELDS = []
    USERNAME_FIELD = 'email'
    objects = UserManager()

    @property
    def is_staff(self):
       return self.is_superuser

    def has_perm(self, perm, obj=None):
        """Check if the user have permission
        """
        return True

    def has_perms(self, perm, obj=None):
        """Check if the user have permission
        """
        return True

    def has_module_perms(self, perm, obj=None):
        """Check if the user have permission
        """
        return True

    def set_password(self, password):
        """Set the user password
        """
        charset = string.digits + string.ascii_letters
        salt = ''.join([random.choice(charset) for _ in range(10)])
        hsh = PyArgon2.Hash_pwd(password.encode(), salt.encode())
        hsh = (salt.encode()+b"$"+binascii.hexlify(hsh)).decode("utf8")
        self.password = hsh

    def check_password(self, pwd):
        """Check if the given password match the real one
        """
        salt, hsh = self.password.split("$", 1)
        ret = PyArgon2.Check_pwd(pwd.encode(), salt.encode(), binascii.unhexlify(hsh))
        return ret

    def get_short_name(self):
        return self.email

    def get_full_name(self):
        return get_short_name

    def is_valid_scanner_token(self, id_scanner, token):
        """Check if id_scanner is a scanner of user and that the token match
        """
        if not Station.objects.filter(user=self, id=id_scanner, token=token).exists():
            print("Not valid")
            return False
        return True

patch_password(User)

class UserPrograms(models.Model):
    """User programs model
    """
    
    id = models.AutoField(primary_key=True, unique=True)
    program_name = models.CharField(max_length=100)
    program_version = models.CharField(max_length=100)
    minimum_score = models.IntegerField(default=0)
    user = models.ForeignKey('User')
    poste = models.ForeignKey('Station')
    cpe = models.ForeignKey('vulnerability_manager.Cpe')
    sms_score = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(10)], default=0)
    sms_enabled = models.BooleanField(default=True)
    email_score = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(10)], default=0)
    email_enabled = models.BooleanField(default=True)
    web_score = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(10)], default=0)
    web_enabled = models.BooleanField(default=True)
    alert_type_default = models.BooleanField(default=True)

    def is_vulnerable(self):
        return self.alert_set.exists()

class Alert(models.Model):
    """Alert model
    """
    
    id = models.AutoField(primary_key=True, unique=True)
    user = models.ForeignKey('User')
    program = models.ForeignKey('UserPrograms')
    cve = models.ManyToManyField('vulnerability_manager.Cve')
    view = models.BooleanField(default=False)

    def max_cvss(self):
        if self.cve.values_list("cvss_score", flat=True):
            return max(self.cve.values_list("cvss_score", flat=True))
        return 0

    def program_info(self):
        return {k:getattr(self.program, k) for k in ['program_name', 'program_version']}

    def number_cve(self):
        return self.cve.count()

    def state(self):
        states = set()

        for cve in self.cve.all():
            srcs = list(map(lambda x: x.lower(), cve.reference_set.values_list("source", flat=True)))
            if "exploit-db" in  srcs or "milw0rm" in srcs:
                states.add("exploit")

            types = list(map(lambda x: x.lower(), cve.reference_set.values_list("type", flat=True)))
            if "patch" in types:
                states.add("patch")
        return states


class Station(models.Model):
    """Station model
    """

    def get_random_token():
        return get_random_string(length=100)
    
    id = models.AutoField(primary_key=True, unique=True)
    token = models.CharField(max_length=100, default=get_random_token)
    user = models.ForeignKey('User')
    name = models.CharField(max_length=100)

    def generate_token(self):
        self.token = get_random_token()

class Session(models.Model):
    """ Session model
    """

    def get_random_token():
        return get_random_string(length=50)

    token = models.CharField(max_length=50, default=get_random_token, primary_key=True, unique=True)
    user = models.ForeignKey('User', null=True, default=None)
    date = models.DateTimeField(auto_now=True)

    def is_valid(self):
        delta = now() - self.date

        if delta.days:
            return False
        return True

