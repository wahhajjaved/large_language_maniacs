import json
from collections import OrderedDict
from contextlib import suppress
from datetime import date, timedelta

from django.conf import settings
from django.db import models
from django.db.models import Case, Count, When

from . import utils

CIVILITY_CHOICES = (
    ('Madame', 'Madame'),
    ('Monsieur', 'Monsieur'),
)


class Section(models.Model):
    """ Filières """
    name = models.CharField(max_length=20, verbose_name='Nom')

    class Meta:
        verbose_name = "Filière"

    def __str__(self):
        return self.name

    @property
    def is_fe(self):
        """fe=formation en entreprise"""
        return self.name in {'ASA', 'ASE', 'ASSC'}

    @property
    def is_EPC(self):
        return self.name in {'ASA', 'ASE', 'ASSC', 'EDE', 'EDS'}

    @property
    def is_ESTER(self):
        return self.name in {'MP_ASE', 'MP_ASSC'}


class Level(models.Model):
    name = models.CharField(max_length=10, verbose_name='Nom')

    class Meta:
        verbose_name = "Niveau"
        verbose_name_plural = "Niveaux"

    def __str__(self):
        return self.name

    def delta(self, diff):
        if diff == 0:
            return self
        try:
            return Level.objects.get(name=str(int(self.name)+diff))
        except Level.DoesNotExist:
            return None


class ActiveKlassManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().annotate(
            num_students=Count(Case(When(student__archived=False, then=1)))
        ).filter(num_students__gt=0)


class Klass(models.Model):
    name = models.CharField(max_length=10, verbose_name='Nom', unique=True)
    section = models.ForeignKey(Section, verbose_name='Filière', on_delete=models.PROTECT)
    level = models.ForeignKey(Level, verbose_name='Niveau', on_delete=models.PROTECT)
    teacher = models.ForeignKey('Teacher', blank=True, null=True,
        on_delete=models.SET_NULL, verbose_name='Maître de classe')
    teacher_ecg = models.ForeignKey('Teacher', blank=True, null=True,
        on_delete=models.SET_NULL, verbose_name='Maître ECG', related_name='+')
    teacher_eps = models.ForeignKey('Teacher', blank=True, null=True,
        on_delete=models.SET_NULL, verbose_name='Maître EPS', related_name='+')

    objects = models.Manager()
    active = ActiveKlassManager()

    class Meta:
        verbose_name = "Classe"

    def __str__(self):
        return self.name

    def is_Ede_pe(self):
        return 'EDE' in self.name and 'pe' in self.name

    def is_Ede_ps(self):
        return 'EDE' in self.name and 'ps' in self.name


class Teacher(models.Model):
    civility = models.CharField(max_length=10, choices=CIVILITY_CHOICES, verbose_name='Civilité')
    first_name = models.CharField(max_length=40, verbose_name='Prénom')
    last_name = models.CharField(max_length=40, verbose_name='Nom')
    abrev = models.CharField(max_length=10, verbose_name='Sigle')
    birth_date = models.DateField(verbose_name='Date de naissance', blank=True, null=True)
    email = models.EmailField(verbose_name='Courriel', blank=True)
    contract = models.CharField(max_length=20, verbose_name='Contrat')
    rate = models.DecimalField(default=0.0, max_digits=4, decimal_places=1, verbose_name="Taux d'activité")
    ext_id = models.IntegerField(blank=True, null=True)
    previous_report = models.IntegerField(default=0, verbose_name='Report précédent')
    next_report = models.IntegerField(default=0, verbose_name='Report suivant')
    can_examinate = models.BooleanField("Peut corriger examens candidats", default=False)
    archived = models.BooleanField(default=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Compte utilisateur'
    )

    class Meta:
        verbose_name='Enseignant'
        ordering = ('last_name', 'first_name')

    def __str__(self):
        return '{0} {1}'.format(self.last_name, self.first_name)

    @property
    def full_name(self):
        return '{0} {1}'.format(self.first_name, self.last_name)

    @property
    def civility_full_name(self):
        return '{0} {1} {2}'.format(self.civility, self.first_name, self.last_name)

    @property
    def role(self):
        return {'Monsieur': 'enseignant-formateur', 'Madame': 'enseignante-formatrice'}.get(self.civility, '')

    def calc_activity(self):
        """
        Return a dictionary of calculations relative to teacher courses.
        Store plus/minus periods to self.next_report.
        """
        mandats = self.course_set.filter(subject__startswith='#')
        ens = self.course_set.exclude(subject__startswith='#')
        tot_mandats = mandats.aggregate(models.Sum('period'))['period__sum'] or 0
        tot_ens = ens.aggregate(models.Sum('period'))['period__sum'] or 0
        # formation periods calculated at pro-rata of total charge
        tot_formation = int(round(
            (tot_mandats + tot_ens) / settings.MAX_ENS_PERIODS * settings.MAX_ENS_FORMATION
        ))
        tot_trav = self.previous_report + tot_mandats + tot_ens + tot_formation
        tot_paye = tot_trav
        max_periods = settings.MAX_ENS_PERIODS + settings.MAX_ENS_FORMATION
        # Special situations triggering reporting (positive or negative) hours for next year:
        #  - full-time teacher with a total charge under 100%
        #  - teachers with a total charge over 100%
        self.next_report = 0
        if (self.rate == 100 and tot_paye < max_periods) or (tot_paye > max_periods):
            tot_paye = max_periods
            self.next_report = tot_trav - tot_paye
        self.save()

        return {
            'mandats': mandats,
            'tot_mandats': tot_mandats,
            'tot_ens': tot_ens,
            'tot_formation': tot_formation,
            'tot_trav': tot_trav,
            'tot_paye': tot_paye,
            'report': self.next_report,
        }

    def calc_imputations(self, ratios):
        """
        Return a tuple for accountings charges
        """
        activities = self.calc_activity()
        imputations = OrderedDict(
            [('ASAFE', 0), ('ASSCFE', 0), ('ASEFE', 0), ('MPTS', 0), ('MPS', 0), ('EDEpe', 0), ('EDEps', 0),
             ('EDS', 0), ('CAS_FPP', 0)]
        )
        courses = self.course_set.all()

        for key in imputations:
            imputations[key] = courses.filter(imputation__contains=key).aggregate(models.Sum('period'))['period__sum'] or 0

        # Spliting imputations for EDE, ASE and ASSC
        ede = courses.filter(imputation='EDE').aggregate(models.Sum('period'))['period__sum'] or 0
        if ede > 0:
            pe = int(round(ede * ratios['edepe'], 0))
            imputations['EDEpe'] += pe
            imputations['EDEps'] += ede - pe

        ase = courses.filter(imputation='ASE').aggregate(models.Sum('period'))['period__sum'] or 0
        if ase > 0:
            asefe = int(round(ase * ratios['asefe'], 0))
            imputations['ASEFE'] += asefe
            imputations['MPTS'] += ase - asefe

        assc = courses.filter(imputation='ASSC').aggregate(models.Sum('period'))['period__sum'] or 0
        if assc > 0:
            asscfe = int(round(assc * ratios['asscfe'], 0))
            imputations['ASSCFE'] += asscfe
            imputations['MPS'] += assc - asscfe

        # Split formation periods in proportions
        tot = sum(imputations.values())
        if tot > 0:
            for key in imputations:
                imputations[key] += round(imputations[key] / tot * activities['tot_formation'],0)

        return (activities, imputations)

    def total_logbook(self):
        return LogBook.objects.filter(teacher=self).aggregate(models.Sum('nb_period'))['nb_period__sum']
    total_logbook.short_description = 'Solde du carnet du lait'


class LogBookReason(models.Model):
    name = models.CharField('Motif', max_length=50, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Motif de carnet du lait'
        verbose_name_plural = 'Motifs de carnet du lait'


class LogBook(models.Model):
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, verbose_name='Enseignant')
    reason = models.ForeignKey(LogBookReason, on_delete=models.PROTECT, verbose_name='Catégorie de motif')
    input_date = models.DateField('Date de saisie', auto_now_add=True)
    start_date = models.DateField('Date de début')
    end_date = models.DateField('Date de fin')
    nb_period = models.IntegerField('Périodes')
    comment = models.CharField('Commentaire motif', max_length=200, blank=True)

    def __str__(self):
        return '{} : {} pér. - {}'.format(self.teacher, self.nb_period, self.comment)

    class Meta:
        verbose_name = 'Carnet du lait'
        verbose_name_plural = 'Carnets du lait'


class Option(models.Model):
    name = models.CharField("Nom", max_length=100, unique=True)

    def __str__(self):
        return self.name


class ExamEDESession(models.Model):
    year = models.PositiveIntegerField()
    season = models.CharField('saison', max_length=10)

    class Meta:
        verbose_name = "Session d’examen EDE"

    def __str__(self):
        return '{0} {1}'.format(self.year, self.season)


GENDER_CHOICES = (
    ('M', 'Masculin'),
    ('F', 'Féminin'),
)

class Student(models.Model):
    ext_id = models.IntegerField(null=True, unique=True, verbose_name='ID externe')
    first_name = models.CharField(max_length=40, verbose_name='Prénom')
    last_name = models.CharField(max_length=40, verbose_name='Nom')
    gender = models.CharField('Genre', max_length=3, blank=True, choices=GENDER_CHOICES)
    birth_date = models.DateField('Date de naissance', null=True, blank=True)
    street = models.CharField(max_length=150, blank=True, verbose_name='Rue')
    pcode = models.CharField(max_length=4, verbose_name='Code postal')
    city = models.CharField(max_length=40, verbose_name='Localité')
    district = models.CharField(max_length=20, blank=True, verbose_name='Canton')
    tel = models.CharField(max_length=40, blank=True, verbose_name='Téléphone')
    mobile = models.CharField(max_length=40, blank=True, verbose_name='Portable')
    email = models.EmailField(verbose_name='Courriel', blank=True)
    login_rpn = models.CharField(max_length=40, blank=True)
    avs = models.CharField(max_length=20, blank=True, verbose_name='No AVS')
    option_ase = models.ForeignKey(Option, null=True, blank=True, on_delete=models.SET_NULL)
    dispense_ecg = models.BooleanField(default=False)
    dispense_eps = models.BooleanField(default=False)
    soutien_dys = models.BooleanField(default=False)
    corporation = models.ForeignKey('Corporation', null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name='Employeur')
    instructor = models.ForeignKey('CorpContact', null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name='FEE/FPP')
    supervisor = models.ForeignKey('CorpContact', related_name='rel_supervisor', verbose_name='Superviseur',
        null=True, blank=True, on_delete=models.SET_NULL)
    supervision_attest_received = models.BooleanField('Attest. supervision reçue',
        default=False)
    mentor = models.ForeignKey('CorpContact', related_name='rel_mentor', verbose_name='Mentor',
        null=True, blank=True, on_delete=models.SET_NULL)
    expert = models.ForeignKey('CorpContact', related_name='rel_expert', verbose_name='Expert externe',
        null=True, blank=True, on_delete=models.SET_NULL)
    klass = models.ForeignKey(Klass, verbose_name='Classe', blank=True, null=True,
        on_delete=models.PROTECT)
    report_sem1 = models.FileField('Bulletin 1er sem.', null=True, blank=True, upload_to='bulletins')
    report_sem1_sent = models.DateTimeField('Date envoi bull. sem 1', null=True, blank=True)
    report_sem2 = models.FileField('Bulletin 2e sem.', null=True, blank=True, upload_to='bulletins')
    report_sem2_sent = models.DateTimeField('Date envoi bull. sem 2', null=True, blank=True)
    archived = models.BooleanField(default=False, verbose_name='Archivé')
    archived_text = models.TextField(blank=True)
    #  ============== Fields for examination ======================
    subject = models.TextField('TD: titre provisoire', blank=True)
    title = models.TextField('TD: Titre définitif', blank=True)
    training_referent = models.ForeignKey(Teacher, null=True, blank=True, related_name='rel_training_referent',
                                          on_delete=models.SET_NULL, verbose_name='Référent de PP')
    referent = models.ForeignKey(Teacher, null=True, blank=True, related_name='rel_referent',
                                 on_delete=models.SET_NULL, verbose_name='Référent avant-projet')
    internal_expert = models.ForeignKey(Teacher, related_name='rel_internal_expert', verbose_name='Expert interne',
                                null=True, blank=True, on_delete=models.SET_NULL)
    session = models.ForeignKey(ExamEDESession, null=True, blank=True, on_delete=models.SET_NULL)
    date_exam = models.DateTimeField(blank=True, null=True)
    last_appointment = models.DateField(blank=True, null=True)
    room = models.CharField('Salle', max_length=15, blank=True)
    mark = models.DecimalField('Note', max_digits=3, decimal_places=2, blank=True, null=True)
    date_soutenance_mailed = models.DateTimeField("Convoc. env.", blank=True, null=True)
    date_confirm_received = models.DateTimeField("Récept. confirm", blank=True, null=True)
    #  ============== Fields for examination ======================
    mc_comment = models.TextField("Commentaires", blank=True)

    support_tabimport = True

    class Meta:
        verbose_name = "Étudiant"

    def __str__(self):
        return '%s %s' % (self.last_name, self.first_name)

    @property
    def civility(self):
        return {'M': 'Monsieur', 'F': 'Madame'}.get(self.gender, '')

    @property
    def full_name(self):
        return '{0} {1}'.format(self.first_name, self.last_name)

    @property
    def civility_full_name(self):
        return '{0} {1} {2}'.format(self.civility, self.first_name, self.last_name)

    @property
    def pcode_city(self):
        return '{0} {1}'.format(self.pcode, self.city)

    @property
    def role(self):
        if self.klass.section.is_fe:
            return {'M': 'apprenti', 'F': 'apprentie'}.get(self.gender, '')
        else:
            return {'M': 'étudiant', 'F': 'étudiante'}.get(self.gender, '')

    def save(self, **kwargs):
        if self.archived and not self.archived_text:
            # Fill archived_text with training data, JSON-formatted
            trainings = [
                tr.serialize() for tr in self.training_set.all().select_related('availability')
            ]
            self.archived_text = json.dumps(trainings)
        if self.archived_text and not self.archived:
            self.archived_text = ""
        super().save(**kwargs)

    def age_at(self, date_):
        """Return age of student at `date_` time, as a string."""
        age = (date.today() - self.birth_date) / timedelta(days=365.2425)
        age_y = int(age)
        age_m = int((age - age_y) * 12)
        return '%d ans%s' % (age_y, ' %d m.' % age_m if age_m > 0 else '')

    def can_comment(self, user):
        """Return True if user is authorized to edit comments for this student."""
        with suppress(Teacher.DoesNotExist):
            return user.has_perm('stages.change_student') or user.teacher == self.klass.teacher
        return False

    def missing_examination_data(self):
        missing = []
        if not self.date_exam:
            missing.append("La date d’examen est manquante")
        if not self.room:
            missing.append("La salle d’examen n’est pas définie")
        if not self.expert:
            missing.append("L’expert externe n’est pas défini")
        if not self.internal_expert:
            missing.append("L’expert interne n’est pas défini")
        return missing


class StudentFile(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    fichier = models.FileField(upload_to='etudiants')
    titre = models.CharField("Titre", max_length=200)

    def __str__(self):
        return self.title


class Corporation(models.Model):
    ext_id = models.IntegerField(null=True, blank=True, verbose_name='ID externe')
    name = models.CharField(max_length=100, verbose_name='Nom')
    short_name = models.CharField(max_length=40, blank=True, verbose_name='Nom court')
    district = models.CharField(max_length=20, blank=True, verbose_name='Canton')
    parent = models.ForeignKey('self', null=True, blank=True, verbose_name='Institution mère',
        on_delete=models.SET_NULL)
    sector = models.CharField(max_length=40, blank=True, verbose_name='Secteur')
    typ = models.CharField(max_length=40, blank=True, verbose_name='Type de structure')
    street = models.CharField(max_length=100, blank=True, verbose_name='Rue')
    pcode = models.CharField(max_length=4, verbose_name='Code postal')
    city = models.CharField(max_length=40, verbose_name='Localité')
    tel = models.CharField(max_length=20, blank=True, verbose_name='Téléphone')
    email = models.EmailField(blank=True, verbose_name='Courriel')
    web = models.URLField(blank=True, verbose_name='Site Web')
    archived = models.BooleanField(default=False, verbose_name='Archivé')

    class Meta:
        verbose_name = "Institution"
        ordering = ('name',)
        unique_together = (('name', 'city'),)

    def __str__(self):
        sect = ' (%s)' % self.sector if self.sector else ''
        return "%s%s, %s %s" % (self.name, sect, self.pcode, self.city)

    @property
    def pcode_city(self):
        return '{0} {1}'.format(self.pcode, self.city)


class CorpContact(models.Model):
    corporation = models.ForeignKey(
        Corporation, verbose_name='Institution', null=True, blank=True,
        on_delete=models.CASCADE
    )
    ext_id = models.IntegerField(null=True, blank=True, verbose_name='ID externe')
    is_main = models.BooleanField(default=False, verbose_name='Contact principal')
    always_cc = models.BooleanField(default=False, verbose_name='Toujours en copie')
    civility = models.CharField(max_length=40, blank=True, verbose_name='Civilité')
    first_name = models.CharField(max_length=40, blank=True, verbose_name='Prénom')
    last_name = models.CharField(max_length=40, verbose_name='Nom')
    birth_date = models.DateField(blank=True, null=True, verbose_name='Date de naissance')
    role = models.CharField(max_length=40, blank=True, verbose_name='Fonction')
    street = models.CharField(max_length=100, blank=True, verbose_name='Rue')
    pcode = models.CharField(max_length=4, blank=True, verbose_name='Code postal')
    city = models.CharField(max_length=40, blank=True, verbose_name='Localité')
    tel = models.CharField(max_length=20, blank=True, verbose_name='Téléphone')
    email = models.CharField(max_length=100, blank=True, verbose_name='Courriel')
    archived = models.BooleanField(default=False, verbose_name='Archivé')
    sections = models.ManyToManyField(Section, blank=True)

    ccp = models.CharField('Compte de chèque postal', max_length=15, blank=True)
    bank = models.CharField('Banque (nom et ville)', max_length=200, blank=True)
    clearing = models.CharField('No clearing', max_length=5, blank=True)
    iban = models.CharField('iban', max_length=21, blank=True)
    qualification = models.TextField('Titres obtenus', blank=True)
    fields_of_interest = models.TextField("Domaines d’intérêts", blank=True)

    class Meta:
        verbose_name = "Contact"

    def __str__(self):
        return '{0} {1}, {2}'.format(self.last_name, self.first_name, self.corporation or '-')

    @property
    def full_name(self):
        return '{0} {1}'.format(self.first_name, self.last_name)

    @property
    def civility_full_name(self):
        return '{0} {1} {2}'.format(self.civility, self.first_name, self.last_name)

    @property
    def pcode_city(self):
        return '{0} {1}'.format(self.pcode, self.city)

    @property
    def adjective_ending(self):
        return 'e' if self.civility == 'Madame' else ''


class Domain(models.Model):
    name = models.CharField(max_length=50, verbose_name='Nom')

    class Meta:
        verbose_name = "Domaine"
        ordering = ('name',)

    def __str__(self):
        return self.name


class Period(models.Model):
    """ Périodes de stages """
    title = models.CharField(max_length=150, verbose_name='Titre')
    section = models.ForeignKey(Section, verbose_name='Filière', on_delete=models.PROTECT,
        limit_choices_to={'name__startswith': 'MP'})
    level = models.ForeignKey(Level, verbose_name='Niveau', on_delete=models.PROTECT)
    start_date = models.DateField(verbose_name='Date de début')
    end_date = models.DateField(verbose_name='Date de fin')

    class Meta:
        verbose_name = "Période de pratique professionnelle"
        verbose_name_plural = "Périodes de pratique professionnelle"
        ordering = ('-start_date',)

    def __str__(self):
        return '%s (%s)' % (self.dates, self.title)

    @property
    def dates(self):
        return '%s - %s' % (self.start_date, self.end_date)

    @property
    def school_year(self):
        return utils.school_year(self.start_date)

    @property
    def relative_level(self):
        """
        Return the level depending on current school year. For example, if the
        period is planned for next school year, level will be level - 1.
        """
        diff = (utils.school_year(self.start_date, as_tuple=True)[0] -
                utils.school_year(date.today(), as_tuple=True)[0])
        return self.level.delta(-diff)

    @property
    def weeks(self):
        """ Return the number of weeks of this period """
        return (self.end_date - self.start_date).days // 7


class Availability(models.Model):
    """ Disponibilités des institutions """
    corporation = models.ForeignKey(Corporation, verbose_name='Institution', on_delete=models.CASCADE)
    period = models.ForeignKey(Period, verbose_name='Période', on_delete=models.CASCADE)
    domain = models.ForeignKey(Domain, verbose_name='Domaine', on_delete=models.CASCADE)
    contact = models.ForeignKey(CorpContact, null=True, blank=True, verbose_name='Contact institution',
        on_delete=models.SET_NULL)
    priority = models.BooleanField('Prioritaire', default=False)
    comment = models.TextField(blank=True, verbose_name='Remarques')

    class Meta:
        verbose_name = "Disponibilité"

    def __str__(self):
        return '%s - %s (%s) - %s' % (self.period, self.corporation, self.domain, self.contact)

    @property
    def free(self):
        try:
            self.training
        except Training.DoesNotExist:
            return True
        return False


class Training(models.Model):
    """ Stages """
    student = models.ForeignKey(Student, verbose_name='Étudiant', on_delete=models.CASCADE)
    availability = models.OneToOneField(Availability, verbose_name='Disponibilité', on_delete=models.CASCADE)
    referent = models.ForeignKey(Teacher, null=True, blank=True, verbose_name='Référent',
        on_delete=models.SET_NULL)
    comment = models.TextField(blank=True, verbose_name='Remarques')

    class Meta:
        verbose_name = "Pratique professionnelle"
        verbose_name_plural = "Pratique professionnelle"
        ordering = ("-availability__period",)

    def __str__(self):
        return '%s chez %s (%s)' % (self.student, self.availability.corporation, self.availability.period)

    def serialize(self):
        """
        Compute a summary of the training as a dict representation (for archiving purpose).
        """
        return {
            'period': str(self.availability.period),
            'corporation': str(self.availability.corporation),
            'referent': str(self.referent),
            'comment': self.comment,
            'contact': str(self.availability.contact),
            'comment_avail': self.availability.comment,
            'domain': str(self.availability.domain),
        }


IMPUTATION_CHOICES = (
    ('ASAFE', 'ASAFE'),
    ('ASEFE', 'ASEFE'),
    ('ASSCFE', 'ASSCFE'),

    ('MPTS', 'MPTS'),
    ('MPS', 'MPS'),

    ('EDEpe', 'EDEpe'),
    ('EDEps', 'EDEps'),
    ('EDS', 'EDS'),
    ('CAS_FPP', 'CAS_FPP'),

    # To split afterwards
    ('EDE', 'EDE'),
    ('#Mandat_ASA', 'ASA'),
    ('#Mandat_ASE', 'ASE'),
    ('#Mandat_ASSC', 'ASSC'),
)


class Course(models.Model):
    """Cours et mandats attribués aux enseignants"""
    teacher = models.ForeignKey(Teacher, blank=True, null=True,
        verbose_name="Enseignant-e", on_delete=models.SET_NULL)
    public = models.CharField("Classe(s)", max_length=200, default='')
    subject = models.CharField("Sujet", max_length=100, default='')
    period = models.IntegerField("Nb de périodes", default=0)
    # Imputation comptable: compte dans lequel les frais du cours seront imputés
    imputation = models.CharField("Imputation", max_length=10, choices=IMPUTATION_CHOICES)

    class Meta:
        verbose_name = 'Cours'
        verbose_name_plural = 'Cours'

    def __str__(self):
        return '{0} - {1} - {2} - {3}'.format(
            self.teacher, self.public, self.subject, self.period
        )

class SupervisionBill(models.Model):
    student = models.ForeignKey(Student, verbose_name='étudiant', on_delete=models.CASCADE)
    supervisor = models.ForeignKey(CorpContact, verbose_name='superviseur', on_delete=models.CASCADE)
    period = models.SmallIntegerField('période', default=0)
    date = models.DateField()

    class Meta:
        verbose_name = 'Facture de supervision'
        verbose_name_plural = 'Factures de supervision'
        ordering = ['date']

    def __str__(self):
        return '{0} : {1}'.format(self.student.full_name, self.supervisor.full_name)
