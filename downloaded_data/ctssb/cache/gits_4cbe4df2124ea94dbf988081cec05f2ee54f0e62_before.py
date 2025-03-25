# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import datetime
from django.db import models
from django.db.models import Sum
from django.contrib.auth.models import User  #, Group
from quiz_setup.models import Quiz, Question, SolutionData
# from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _


from kinetic_widget.models import KineticField  # $&
from graph_engine.iso import check_isomorphism # $&

# TODO: skusit pouzit limit_choices_to na tie vybery priradenych zo vsetkych relevantnych

# decimal settings for grades
GRADE_MAX_DIGITS = 5
GRADE_DECIMAL_PLACES = 2
DECDEF = {'max_digits': GRADE_MAX_DIGITS, 'decimal_places': GRADE_DECIMAL_PLACES}  # decimal defaults (helper dictionary)

class Answer(models.Model):
    grade = models.DecimalField(_('grade'), default=0, **DECDEF)
    # answer_data = models.ForeignKey(SolutionData)
    answer_data = KineticField()  # $& for now use "statically" just KineticField
    question = models.ForeignKey(Question)
    quiz_result = models.ForeignKey('QuizResult')

    class Meta:
        verbose_name = _('answer')
        verbose_name_plural = _('answers')

    def __unicode__(self):
        return unicode(self.grade)

    def auto_evaluate(self):
        """ Evaluates itself using relevant engine and assigns grade. """
        for correct_answer in self.question.correctanswer_set.all():
            try:
                # compare correct_answer with this answer
                if check_isomorphism(correct_answer.answer_data, self.answer_data):
                    self.grade = correct_answer.grade / 100. * self.question.mark
                    self.save()
                    return True
            except ValueError as err:
                messages.error(request, unicode(err))
                return None
        return False

class QuizResult(models.Model):
    timestamp = models.DateTimeField(_('timestamp'), default=datetime.datetime.now)
    duration = models.PositiveIntegerField(_('duration'), null=True)
    total_grade = models.DecimalField(_('total grade'), null=True, **DECDEF)
    student = models.ForeignKey(User)
    quiz = models.ForeignKey(Quiz)

    class Meta:
        verbose_name = _('quiz result')
        verbose_name_plural = _('quiz results')

    def __unicode__(self):
        return unicode(self.timestamp)

    def auto_evaluate_answers(self):
        """ Calls auto_evaluate method for every related answer. """
        for answer in self.answer_set.all():
            answer.auto_evaluate()
        self.total_grade = self.answer_set.aggregate(Sum('grade'))
        self.save()
