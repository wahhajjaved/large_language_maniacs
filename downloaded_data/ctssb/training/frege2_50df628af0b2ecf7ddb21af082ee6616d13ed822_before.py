# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_delete 
from django.dispatch import receiver

from .formula import (
    Formula,
    PredicateFormula,
    FormulaSet,
    PredicateFormulaSet,
    Argument,
    PredicateArgument,
    formal_type,
    formalize,
    get_argument,
)

import logging
logger = logging.getLogger(__name__)

"""
This module contains definitions for the app's entities.

Here's a brief summary:
- Chapter: a group of questions that has a number and title.
- OpenQuestion: a question with no predifined answer.
- ChoiceQuestion: a question with several choices (some of them correct).
- FormulationQuestion: a question with predefined answers (all of them correct).
- TruthTableQuestion: a question that is answered by a truth table in gui.
- DeductionQuestion: a question that is answered by a deduction in gui.
"""

def shorten_text(text, size=50):
    return text if len(text) <= size else '%s...' % text[:size-3]

def _concrete_sub_classes(cls):
    subs = []
    for sub in cls.__subclasses__():
        if sub._meta.abstract:
            subs.extend(_concrete_sub_classes(sub))
        else:
            subs.append(sub)
    return subs
         
class Chapter(models.Model):
    number = models.PositiveIntegerField(verbose_name='מספר', unique=True)
    title = models.CharField(verbose_name='כותרת', max_length=30)

    def num_questions(self, followups=False):
        if followups:
            questions = Question._filter(chapter=self)
            return len(questions) + sum(1 for q in questions if q.has_followup())
        else:
            return Question._count(chapter=self)
    num_questions.short_description = 'מספר שאלות'

    def questions(self):
        return Question._filter(chapter__number=self.number)

    def first_question(self):
        return min(self.questions(), key=lambda q: q.number)

    def is_open(self):
        return any(type(q) == OpenQuestion for q in self.questions())

    def __unicode__(self):
        return '%s. %s' % (self.number, self.title)

    class Meta:
        verbose_name = 'פרק'
        verbose_name_plural = 'פרקים'
        ordering = ['number']

class Question(models.Model):

    DEFAULT_NUM = 0

    chapter = models.ForeignKey(Chapter, verbose_name='פרק', on_delete=models.CASCADE, null=True)
    number = models.PositiveIntegerField(default=DEFAULT_NUM, verbose_name='מספר', null=True)

    def user_answers(self):
        return UserAnswer.objects.filter(chapter=self.chapter, question_number=self.number)
    
    def user_answer(self, user):
        return UserAnswer.objects.filter(user=user, chapter=self.chapter, question_number=self.number)

    def clean(self):
        # TODO: does this have unit tests? it should
        super(Question, self).clean()
        if self.chapter_id:
            if self.number > self.DEFAULT_NUM: # TODO: probably add condition for followup question with the same number
                chapter_questions = Question._filter(chapter=self.chapter)
                if self.number in set([q.number for q in Question._filter(chapter=self.chapter) if q.id != self.id]):
                    raise ValidationError({'number':'כבר קיימת שאלה מספר %d בפרק זה' % (self.number)})
            if self.chapter.is_open():
                if type(self) != OpenQuestion:
                    raise ValidationError('לא ניתן לשמור שאלה זו בפרק עם שאלות פתוחות')
            elif type(self) == OpenQuestion:
                    raise ValidationError('לא ניתן לשמור שאלה זו בפרק עם שאלות לא פתוחות')

    def save(self, *args, **kwargs):
        logger.debug('saving %s', self)
        if self.number == self.DEFAULT_NUM:
            # set a number for this question
            others = Question._filter(chapter=self.chapter)
            self.number = max(q.number for q in others) + 1 if others else 1
            logger.debug('setting number to %d', self.number)
        self.clean()
        super(Question, self).save(*args, **kwargs)

    def has_followup(self):
        return self.__class__ == FormulationQuestion and self.followup != FormulationQuestion.NONE

    @classmethod
    def _all(cls):
        return cls._sub_func('all')

    @classmethod
    def _filter(cls, **kwargs):
        return cls._sub_func('filter', **kwargs)

    @classmethod
    def _get(cls, **kwargs):
        result = cls._filter(**kwargs)
        if not result:
            return None
        assert len(result) == 1
        return result[0]
 
    @classmethod
    def _count(cls, **kwargs):
        return len(cls._filter(**kwargs))

    @classmethod
    def _sub_func(cls, func_name, **kwargs):
        concretes = _concrete_sub_classes(cls)
        all_obj = []
        for c in concretes:
            all_obj.extend(getattr(c.objects, func_name)(**kwargs))
        return all_obj

    @property
    def _str(self):
        return '%s/%s' % (self.chapter.number, self.number)

    class Meta:
        abstract = True
        ordering = ['number']

@receiver(post_delete)   
def delete_stuff(instance, sender, **kwargs):
    # do stuff upon question deletion
    if issubclass(sender, Question):
        self = instance
        logger.debug('post delete %s', self)
        # delete question-related entities
        for ua in self.user_answers():
            logger.debug('deleting %s of question %s', ua, self)
            ua.delete()
        # re-order other questions
        for q in Question._filter(chapter=self.chapter, number__gt=self.number):
            q.number = q.number - 1
            q.save()
            logger.debug('reordered %s', q)

class TextualQuestion(Question):
    text = models.TextField(verbose_name='טקסט')

    @property
    def short_text(self):
        return shorten_text(self.text)
 
    def __unicode__(self):
        return '%s/%s. %s' % (self.chapter.number, self.number, self.short_text)

    class Meta(Question.Meta):
        abstract = True

class FormalQuestion(Question):

    def __unicode__(self):
        return '%s/%s. %s' % (self.chapter.number, self.number, self.formula)

    class Meta(Question.Meta):
        abstract = True

class FormulationQuestion(TextualQuestion):
    NONE = 'N'
    TRUTH_TABLE = 'T'
    DEDUCTION = 'D'
    MODEL = 'M'
    FOLLOWUP_CHOICES = (
        (NONE, 'ללא'),
        (TRUTH_TABLE,'טבלת אמת'),
        (DEDUCTION, 'דדוקציה'),
        (MODEL, 'פשר'),
    )
    followup = models.CharField(verbose_name='שאלת המשך',max_length=1,choices=FOLLOWUP_CHOICES,default=NONE)

    class Meta(TextualQuestion.Meta):
        verbose_name = 'שאלת הצרנה'
        verbose_name_plural = 'שאלות הצרנה'

class OpenQuestion(TextualQuestion):

    class Meta(TextualQuestion.Meta):
        verbose_name = 'שאלת פתוחה'
        verbose_name_plural = 'שאלות פתוחות'

class ChoiceQuestion(TextualQuestion):

    class Meta(TextualQuestion.Meta):
        verbose_name = 'שאלת בחירה'
        verbose_name_plural = 'שאלות בחירה'

def validate_formula(formula, formula_cls=Formula):
    try:
        return formula_cls(formula).literal
    except:
        raise ValidationError({'formula':'הנוסחה שהוזנה אינה תקינה'})

def validate_formula_set(fset, formula_set_cls=FormulaSet):
    try:
        return formula_set_cls(fset).literal
    except:
        raise ValidationError({'formula':'הקבוצה שהוזנה אינה תקינה'})

def validate_argument(arg, argument_cls=Argument):
    try:
        return argument_cls(arg).literal
    except:
        msg = 'הטיעון שהוזן אינו תקין'
        raise ValidationError({'formula':msg})

def validate_deduction_argument(arg):
    try:
        a = get_argument(arg)
    except:
        raise ValidationError({'formula':'הטיעון שהוזן אינו תקין'})
    if a.formula_cls == Formula and not a.is_valid:
        raise ValidationError({'formula':'הטיעון שהוזן אינו ניתן להוכחה'})
    return a.literal

def validate_truth_table(x):
    pass

class SemanticsQuestion(FormalQuestion):
    FORMULA = 'F'
    SET = 'S'
    ARGUMENT = 'A'
    TABLE_CHOICES = (
        (FORMULA, 'נוסחה'),
        (SET,'קבוצה'),
        (ARGUMENT, 'טיעון'),
    )
    table_type = models.CharField(verbose_name='סוג',max_length=1,choices=TABLE_CHOICES, null=True)
    formula = models.CharField(verbose_name='נוסחה/טיעון/קבוצה', max_length=60, null=True)

    @property
    def is_formula(self):
        return self.table_type == self.FORMULA
 
    @property
    def is_set(self):
        return self.table_type == self.SET
 
    @property
    def is_argument(self):
        return self.table_type == self.ARGUMENT
 
    def clean(self):
        super(SemanticsQuestion, self).clean()
        self._set_table_type()
        if self.is_formula:
            self.formula = validate_formula(self.formula, self._formula_cls)
        elif self.is_set:
            self.formula = validate_formula_set(self.formula, self._formula_set_cls)
        elif self.is_argument:
            self.formula = validate_argument(self.formula, self._argument_cls)

    def save(self, *args, **kwargs):
        self._set_table_type()
        super(SemanticsQuestion, self).save(*args, **kwargs)

    def display(self):
        if self.is_formula:
            return self.formula
        if self.is_set:
            return self._formula_set_cls(self.formula).display
        if self.is_argument:
            return self._argument_cls(self.formula).display

    def _set_table_type(self):
        try:
            self.table_type = {
                self._formula_cls: self.FORMULA,
                self._formula_set_cls: self.SET,
                self._argument_cls: self.ARGUMENT
            }[formal_type(self.formula)]
        except KeyError:
            raise ValidationError({'formula':'ערך לא תקין'})

    class Meta(FormalQuestion.Meta):
        abstract = True
        unique_together = ('chapter', 'formula')

class TruthTableQuestion(SemanticsQuestion):

    _formula_cls = Formula
    _formula_set_cls = FormulaSet
    _argument_cls = Argument

    @property
    def options(self):
        if self.is_formula:
            return FORMULA_OPTIONS
        elif self.is_set:
            return SET_OPTIONS
        elif self.is_argument:
            return ARGUMENT_OPTIONS

    class Meta(SemanticsQuestion.Meta):
        verbose_name = 'שאלת טבלת אמת'
        verbose_name_plural = 'שאלות טבלת אמת'

class ModelQuestion(SemanticsQuestion):

    _formula_cls = PredicateFormula
    _formula_set_cls = PredicateFormulaSet
    _argument_cls = PredicateArgument

    class Meta(SemanticsQuestion.Meta):
        verbose_name = 'שאלת פשר'
        verbose_name_plural = 'שאלות פשר'

class ValuesQuestion(SemanticsQuestion):

    _formula_cls = Formula
    _formula_set_cls = FormulaSet
    _argument_cls = Argument

    @property
    def options(self):
        if self.is_formula:
            return FORMULA_OPTIONS
        elif self.is_set:
            return SET_OPTIONS
        elif self.is_argument:
            return ARGUMENT_OPTIONS

    class Meta(SemanticsQuestion.Meta):
        verbose_name = 'שאלת מתן ערכים'
        verbose_name_plural = 'שאלות מתן ערכים'

class DeductionQuestion(FormalQuestion):
    formula = models.CharField(verbose_name='טיעון', max_length=60)

    def clean(self):
        super(DeductionQuestion, self).clean()
        self.formula = validate_deduction_argument(self.formula)

    def display(self):
        return get_argument(self.formula).display

    class Meta(FormalQuestion.Meta):
        verbose_name = 'שאלת דדוקציה'
        verbose_name_plural = 'שאלות דדוקציה'
        unique_together = ('chapter', 'formula')

class FormulationAnswer(models.Model):
    formula = models.CharField(verbose_name='נוסחה/טיעון/קבוצה', max_length=60)
    question = models.ForeignKey(FormulationQuestion, verbose_name='שאלה', on_delete=models.CASCADE)

    def clean(self):
        super(FormulationAnswer, self).clean()
        try:
            formalize(self.formula)
        except:
            raise ValidationError('קלט לא תקין')
        
    def __unicode__(self):
        return self.formula

    class Meta:
        verbose_name = 'תשובה'
        verbose_name_plural = 'תשובות'

class Choice(models.Model):
    text = models.CharField(verbose_name='טקסט', max_length=200)
    question = models.ForeignKey(ChoiceQuestion, verbose_name='שאלה', on_delete=models.CASCADE)
    is_correct = models.BooleanField(verbose_name='תשובת נכונה?', default=False)

    @property
    def short_text(self):
        return shorten_text(self.text)

    def __unicode__(self):
        return self.short_text

    class Meta:
        verbose_name = 'בחירה'
        verbose_name_plural = 'בחירות'

class ChapterSubmission(models.Model):
    user = models.ForeignKey(User, verbose_name='משתמש', on_delete=models.CASCADE)
    chapter = models.ForeignKey(Chapter, verbose_name='פרק', on_delete=models.CASCADE)
    attempt = models.PositiveIntegerField(verbose_name='נסיונות')
    ongoing = models.BooleanField()
    time = models.DateTimeField(verbose_name='זמן הגשה', blank=True, null=True)

    def is_complete(self):
        """
        a submission is complete iff all chapter questions were answered including all followups
        this is premised on the assumption that a user can always advance to the followup question,
        even if the preliminary one is incorrect
        """
        user_answers = UserAnswer.objects.filter(chapter=self.chapter, user=self.user)
        chapter_questions = {q.number: q for q in self.chapter.questions()}
        chapter_followups = {q.number for q in chapter_questions.itervalues() if q.has_followup()}
        answered_questions = {a.question_number: a.correct for a in user_answers if not a.is_followup}
        answered_followups = {a.question_number for a in user_answers if a.is_followup}
        return set(chapter_questions.keys()) == set(answered_questions.keys()) and chapter_followups == answered_followups

    def is_ready(self):
        if self.chapter.is_open():
            answers = OpenAnswer.objects.filter(user_answer__user=self.user, question__chapter=self.chapter)
            if not all(a.checked for a in answers):
                return False
        return self.is_complete()

    MAX_ATTEMPTS = 3

    @property
    def max_attempts(self):
        return self.MAX_ATTEMPTS if not self.chapter.is_open() else 1
 
    def can_try_again(self):
        return self.attempt < self.max_attempts

    @property
    def remaining(self):
        return self.max_attempts - self.attempt

    @property
    def percent_correct_f(self):
        return self.percent_correct()

    def percent_correct(self):
        _, _, pct = self.correctness_data()
        return pct
    percent_correct.short_description = 'ציון'

    def correctness_data(self):
        if self.chapter.is_open() and self.is_ready():
            answers = OpenAnswer.objects.filter(user_answer__user=self.user, question__chapter=self.chapter)
            answer_data = {
                (ans.question.number, False): float(ans.grade)
                for ans in answers
            }
            num_correct = sum(answer_data.itervalues())
        else:
            answer_data = {
                (ans.question_number, ans.is_followup): ans.correct 
                for ans in UserAnswer.objects.filter(user=self.user, chapter=self.chapter)
            }
            num_correct = sum(1 for correct in answer_data.itervalues() if correct)

        pct = int(round(num_correct * 100. / self.chapter.num_questions(followups=True)))
        return answer_data, num_correct, pct

    @property
    def chapter_number_f(self):
        return self.chapter.number

    def chapter_number(self):
        return self.chapter.number
    chapter_number.short_description = 'פרק'

    def __unicode__(self):
        return '%s/%s%s complete=%s, ongoing=%s, attempts=%d, can-retry=%s, pct=%.1f' % (
            self.user,
            self.chapter.number,
            ' [%s]' % self.time if self.time else '',
            self.is_complete(),
            self.ongoing,
            self.attempt,
            self.can_try_again(),
            self.percent_correct(),
        )

    class Meta:
        verbose_name = 'הגשת משתמש'
        verbose_name_plural = '[הגשות משתמשים]'
        unique_together = ('chapter', 'user')
        ordering = ['chapter']

class UserAnswer(models.Model):
    user = models.ForeignKey(User, verbose_name='משתמש', on_delete=models.CASCADE)
    chapter = models.ForeignKey(Chapter, verbose_name='פרק', on_delete=models.CASCADE)
    submission = models.ForeignKey(ChapterSubmission, verbose_name='הגשת פרק', on_delete=models.CASCADE)
    question_number = models.PositiveIntegerField(verbose_name='מספר שאלה')
    correct = models.BooleanField(verbose_name='תשובה נכונה')
    answer = models.TextField()
    is_followup = models.BooleanField(default=False)
    time = models.DateTimeField(verbose_name='זמן', blank=True, null=True)

    def __unicode__(self):
        return '%s/%s/%s/%s' % (self.user, self.chapter.number, self.question_number, 'T' if self.correct else 'F')

    class Meta:
        verbose_name = 'תשובת משתמש'
        verbose_name_plural = '[תשובות משתמשים]'
        unique_together = ('chapter', 'user', 'question_number', 'is_followup')

class OpenAnswer(models.Model):
    text = models.TextField(verbose_name='טקסט')
    question = models.ForeignKey(OpenQuestion, verbose_name='שאלה', on_delete=models.CASCADE)
    upload = models.FileField(verbose_name='קובץ', upload_to='uploads/%Y/%m', null=True, blank=True)
    user_answer = models.OneToOneField(UserAnswer, on_delete=models.CASCADE, unique=True)
    grade = models.DecimalField(
        verbose_name='ניקוד',
        max_digits=2,
        decimal_places=1,
        null=True,
        blank=False,
        validators = [
            MaxValueValidator(1.),
            MinValueValidator(0.),
        ]
    )
    comment = models.TextField(verbose_name='הערות (אופציונלי)', null=True, blank=True)

    @property
    def checked(self):
        return self.grade is not None

    def save(self, *args, **kwargs):
        try:
            # delete old file if replaced
            this = OpenAnswer.objects.get(id=self.id)
            if this.upload != self.upload:
                logger.debug('%s upload updated, deleting previous file', self)
                this.upload.delete(save=False)
        except: pass # new file
        super(OpenAnswer, self).save(*args, **kwargs)

    @property
    def short_text(self):
        return shorten_text(self.text)
 
    def __unicode__(self):
        return '%s file=%s text=%s' % (self.user_answer, self.upload, self.short_text)

    class Meta:
        verbose_name = 'תשובה פתוחה'
        verbose_name_plural = '[תשובות פתוחות]'

# handle open answer deletion
@receiver(post_delete)   
def delete_open_answer(instance, sender, **kwargs):
    if issubclass(sender, OpenAnswer):
        # delete file
        logger.debug('post delete %s', instance)
        instance.upload.delete(save=False)

# see: https://docs.djangoproject.com/en/1.9/topics/auth/customizing/#extending-the-existing-user-model
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    group = models.CharField(max_length=2, verbose_name='מספר קבוצה')

    def __str__(self):
        return '%s/%s' % (self.user, self.group)
    __repr__ = __str__
    __unicode__ = __str__

    class Meta:
        verbose_name = 'פרופיל'
        verbose_name_plural = 'פרופילים'

