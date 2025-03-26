from django.db import models
from django.contrib.auth.models import User

from home.models import Competition


SUBJECTS = (
    ("al", "Algebra"),
    ("nt", "Number Theory"),
    ("ge", "Geometry"),
    ("cp", "Counting and Probability"))
SUBJECTS_MAP = dict(SUBJECTS)

DIVISIONS = (
    (1, "Gauss"),  # Harder
    (2, "Cantor"))
DIVISIONS_MAP = dict(DIVISIONS)

GRADES = (
    (0, "Other"),
    (6, "6th"),
    (7, "7th"),
    (8, "8th"))

SHIRT_SIZES = (
    (1, "Adult Small"),
    (2, "Adult Medium"),
    (3, "Adult Large"),
    (4, "Adult Extra Large"))


class School(models.Model):
    """A simple school model that is represented by a teacher."""

    name = models.CharField(max_length=60, unique=True)
    coaches = models.ManyToManyField(User, related_name="school", through="Coaching")

    def __str__(self):
        """Represent the school as a string."""

        return "School[{}]".format(self.name)


class Coaching(models.Model):
    """Model to indicate which competition the coach is registered for."""

    coach = models.ForeignKey(User, on_delete=models.CASCADE, related_name="coaching")
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="coaching")
    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="competitions")

    def teams(self):
        """Return a list of teams."""

        return Team.objects.filter(competition=self.competition, school=self.school)

    def chaperones(self):
        """Return a list of chaperones."""

        return Chaperone.objects.filter(competition=self.competition, school=self.school)

    @staticmethod
    def current(**kwargs):
        """Get the current list of coaches."""

        return Coaching.objects.filter(competition__active=True)


class Team(models.Model):
    """Represents a team of students competing in the competition."""

    name = models.CharField(max_length=64)
    number = models.IntegerField(default=0)
    school = models.ForeignKey(School, related_name="teams")
    competition = models.ForeignKey(Competition, related_name="teams")
    division = models.IntegerField(choices=DIVISIONS)

    def __str__(self):
        """Represent the team as a string."""

        return "Team[{}]".format(self.name)

    @staticmethod
    def current(**kwargs):
        """Get the teams for the current competition."""

        return Team.objects.filter(competition__active=True, **kwargs)

    def get_students_display(self):
        """Get the comma separated list of students."""

        return ", ".join(map(lambda x: x.name, self.students.all()))


class Student(models.Model):
    """A student participating in the competition."""

    first_name = models.CharField(max_length=64)
    last_name = models.CharField(max_length=64)

    team = models.ForeignKey(Team, related_name="students")
    subject1 = models.CharField(max_length=2, blank=True, choices=SUBJECTS, verbose_name="Subject 1")
    subject2 = models.CharField(max_length=2, blank=True, choices=SUBJECTS, verbose_name="Subject 2")

    grade = models.IntegerField(choices=GRADES)

    shirt_size = models.IntegerField(choices=SHIRT_SIZES)
    attending = models.BooleanField(default=False)

    class Meta:
        """Meta information about the student."""

        ordering = ('last_name',)

    def __str__(self):
        """Represent the student as a string."""

        return "Student[{}]".format(self.full_name)

    def get_full_name(self):
        """Get the user's full name."""

        return self.first_name + " " + self.last_name

    @staticmethod
    def current(**kwargs):
        """Get the students in the current competition."""

        return Student.objects.filter(team__competition__active=True, **kwargs)


class Chaperone(models.Model):
    """A chaperone for a team."""

    competition = models.ForeignKey(Competition)
    school = models.ForeignKey(School)

    first_name = models.CharField(max_length=60)
    last_name = models.CharField(max_length=60)

    email = models.EmailField()
    phone = models.CharField(max_length=20)
    shirt_size = models.IntegerField(choices=SHIRT_SIZES)

    def get_full_name(self):
        """Get the user's full name."""

        return self.first_name + " " + self.last_name

    @staticmethod
    def current(**kwargs):
        """Get the students in the current competition."""

        return Chaperone.objects.filter(competition__active=True, **kwargs)
