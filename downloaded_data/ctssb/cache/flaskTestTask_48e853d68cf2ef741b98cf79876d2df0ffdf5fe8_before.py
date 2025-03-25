# -*- coding: utf-8 -*-
from wtforms import StringField
from flask.ext.wtf import Form
from wtforms.validators import DataRequired
from wtforms.widgets import TextArea
from wtforms import fields, validators
from .models import User
from library import db


class LoginForm(Form):
    login = fields.StringField(validators=[validators.required()])
    password = fields.PasswordField(validators=[validators.required()])

    def validate_login(self, field):
        user = self.get_user()
        if user is None:
            raise validators.ValidationError('Invalid user')

    def validate_password(self, password):
        user = self.get_user()
        if not user.check_password(password):
            raise validators.ValidationError('Invalid password')

    def get_user(self):
        return db.session.query(User).filter_by(login=self.login.data).first()


class RegistrationForm(Form):
    login = fields.StringField(validators=[validators.required()])
    password = fields.PasswordField(validators=[validators.required()])

    def validate_login(self, field):
        if db.session.query(User).filter_by(login=field.data).count() > 0:
            raise validators.ValidationError('Duplicate username')


class QuestionForm(Form):
    title = StringField(u'title', validators=[DataRequired()])
    text = StringField(u'text', validators=[DataRequired()], widget=TextArea())


class AnswerForm(Form):
    text = StringField(u'answer', validators=[DataRequired()], widget=TextArea())