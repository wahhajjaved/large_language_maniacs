# -*- coding: utf-8 -*-
"""
    website.admin
    ~~~~~~~~~~~~~

    administrative controls over the content for the Windermere website

    :license: BSD or something
    :author: uniphil
"""

import os
from datetime import datetime
from PIL import Image
from wtforms import fields
from werkzeug import secure_filename
from flask import request, flash, redirect, url_for
from flask.ext.login import current_user, login_user, logout_user
from flask.ext.admin import Admin, BaseView, AdminIndexView, expose
from flask.ext.admin.form import DatePickerWidget
from flask.ext.admin.contrib import sqla
from website import app
from website import models
from website import forms
from website.admin_helpers import wrap_file_field


class AuthException(Exception):
    pass


class HomeView(AdminIndexView):

    def is_visible(self):
        return False

    @expose('/')
    def index(self):
        if not (current_user.is_authenticated() and current_user.is_admin):
            return redirect(url_for('.login'))
        return self.render('admin/overview.html')

    @expose('/login', methods=['GET', 'POST'])
    def login(self):
        form = forms.LoginForm(request.form)
        if form.validate_on_submit():
            try:
                the_admin = models.Admin.query.filter_by(
                                email=form.email.data).first()
                if the_admin is None:
                    form.email.errors.append('Email not found :|')
                    raise AuthException
                if not the_admin.check_password(form.password.data):
                    form.password.errors.append('Password did not check out :(')
                    raise AuthException
                login_user(the_admin)
                flash("Hello {}, you have successfully logged in.".format(
                    the_admin.name), 'success')
                return redirect(url_for(request.args.get('next') or
                                        'admin.index'))
            except AuthException:
                pass
        return self.render('admin/login.html', form=form)

    @expose('/logout')
    def logout(self):
        logout_user()
        return redirect(url_for('home'))


class AdminView(BaseView):
    def is_accessible(self):
        return current_user.is_authenticated() and current_user.is_admin


class AccountsView(AdminView):

    @expose('/')
    def index(self):
        partners = models.Partner.query.all()
        admins = models.Admin.query.all()
        return self.render('admin/accounts/index.html', partners=partners,
                           admins=admins)

    @expose('/partner/<int:id>/edit', methods=['GET', 'POST'])
    def edit_partner(self, id):
        partner = models.Partner.query.get_or_404(id)
        errors = []
        if request.method == 'POST':
            if request.form.get('key'):
                partner.key = request.form['key']
                partner.last_keychange = datetime.now()
                models.db.session.add(partner)
                models.db.session.commit()
                flash('Saved new key for {}'.format(partner.name), 'info')
                return redirect(url_for('.index'))
            else:
                errors.append('Please set a key for partner access...')
        return self.render('admin/accounts/edit_partner.html', verb='Edit',
                           action='set', ico='pencil', key=partner.key,
                           name=partner.name)

    @expose('/admin/add', methods=['GET', 'POST'])
    def add_admin(self):
        form = forms.AdminForm(request.form)
        if form.validate_on_submit():
            new_admin = models.Admin()
            new_admin.name = form.name.data
            new_admin.email = form.email.data
            new_admin.set_password(form.password.data)
            models.db.session.add(new_admin)
            models.db.session.commit()
            flash('Successfully added new admin {}.'.format(new_admin.name),
                  'success')
            return redirect(url_for('.index'))
        return self.render('admin/accounts/add_admin.html', form=form,
                           verb='Add', action='Add', ico='plus')

    @expose('/admin/<int:id>/edit', methods=['GET', 'POST'])
    def edit_admin(self, id):
        the_admin = models.Admin.query.get_or_404(id)
        form = forms.AdminForm(request.form, the_admin)
        if form.validate_on_submit():
            the_admin.name = form.name.data
            the_admin.email = form.email.data
            if form.password.data:
                the_admin.set_password(form.password.data)
            models.db.session.add(the_admin)
            models.db.session.commit()
            flash('Successfully saved settings for {}.'.format(the_admin.name),
                  'info')
            return redirect(url_for('.index'))
        return self.render('admin/accounts/add_admin.html', form=form,
                           verb='Edit', action='Save', ico='pencil')

    @expose('/admin/<int:id>/enable-messages')
    def enable_messages(self, id):
        the_admin = models.Admin.query.get_or_404(id)
        the_admin.receives_messages = True
        models.db.session.add(the_admin)
        models.db.session.commit()
        flash('Messages from the contact form will be sent to {}'
              .format(the_admin.name))
        return redirect(url_for('.index'))

    @expose('/admin/<int:id>/disable-messages')
    def disable_messages(self, id):
        the_admin = models.Admin.query.get_or_404(id)
        the_admin.receives_messages = False
        models.db.session.add(the_admin)
        models.db.session.commit()
        flash('Messages from the contact form will no longer be sent to {}'
              .format(the_admin.name))
        return redirect(url_for('.index'))

    @expose('/admin/<int:id>/disable')
    def disable_admin(self, id):
        the_admin = models.Admin.query.get_or_404(id)
        the_admin.disabled = True
        models.db.session.add(the_admin)
        models.db.session.commit()
        flash('Disabled {}. They will be restricted to public access only.'
              .format(the_admin.name), 'info')
        return redirect(url_for('.index'))

    @expose('/admin/<int:id>/enable')
    def enable_admin(self, id):
        the_admin = models.Admin.query.get_or_404(id)
        the_admin.disabled = False
        models.db.session.add(the_admin)
        models.db.session.commit()
        flash('Re-enabled administrator {}.'.format(the_admin.name), 'success')
        return redirect(url_for('.index'))

    @expose('/admin/<int:id>/remove', methods=['GET', 'POST'])
    def remove_admin(self, id):
        the_admin = models.Admin.query.get_or_404(id)
        if request.form.get('confirm') == 'yes':
            models.db.session.delete(the_admin)
            models.db.session.commit()
            flash('Removed administrator {}.'.format(the_admin.name), 'info')
            return redirect(url_for('.index'))
        return self.render('admin/accounts/remove_admin.html', admin=the_admin)


@wrap_file_field('photo', 'scenic', endpoint='uploaded_file', photo=True)
class PhotoView(sqla.ModelView, AdminView):
    """Public scenic photos"""
    list_template = 'admin/photos/index.html'
    column_list = ('title', 'added', 'featured')
    column_default_sort = ('featured', True)
    
    def _order_by(self, *args, **kwargs):
        """hack to secondary-sort"""
        query, joins = super(PhotoView, self)._order_by(*args, **kwargs)
        query = query.order_by(self.model.added.desc())
        return query, joins

    def create_model(self, form):
        """use the current time by default"""
        added = getattr(form, 'added')
        if added.data is None:
            added.data = datetime.now()
        return super(PhotoView, self).create_model(form)

    @expose('/<int:id>/toggle-feature')
    def toggle_feature(self, id):
        the_photo = models.ScenicPhoto.query.get_or_404(id)
        the_photo.featured = not the_photo.featured
        models.db.session.add(the_photo)
        models.db.session.commit()
        return redirect(request.referrer or url_for('.index'))

    @expose('/<int:id>/confirm-removal')
    def confirm_delete(self, id):
        the_photo = models.ScenicPhoto.query.get_or_404(id)
        next = request.args.get('next') or url_for('.index')
        return self.render('admin/photos/remove.html', photo=the_photo,
                           next=next)


@wrap_file_field('photo', 'people', endpoint='uploaded_file', photo=True)
class PeopleView(sqla.ModelView, AdminView):
    """Researchers to list on home page"""
    list_template = 'admin/people/index.html'
    column_default_sort = ('current', True)

    @expose('/<int:id>/confirm-removal')
    def confirm_delete(self, id):
        the_person = models.Person.query.get_or_404(id)
        next = request.args.get('next') or url_for('.index')
        return self.render('admin/people/remove.html', person=the_person,
                           next=next)


@wrap_file_field('file', 'documents', endpoint='uploaded_file', photo=False)
class DocumentView(sqla.ModelView, AdminView):
    """Access-controlled stuff"""

    list_template = 'admin/documents/index.html'
    create_template = 'admin/documents/create.html'
    edit_template = 'admin/documents/create.html'
    column_default_sort = ('featured', True)

    def scaffold_form(self):
        form_class = super(DocumentView, self).scaffold_form()
        form_class.published = fields.TextField('Published', widget=DatePickerWidget())
        return form_class

    def _order_by(self, *args, **kwargs):
        """hack to secondary-sort"""
        query, joins = super(DocumentView, self)._order_by(*args, **kwargs)
        query = query.order_by(self.model.published.desc())
        return query, joins

    def create_model(self, form):
        """use the current time by default"""
        published = getattr(form, 'published')
        d = published.data
        if d is None or d == '':
            published.data = datetime.now()
        else:
            published.data = datetime.strptime(d, '%Y-%m-%d')
        return super(DocumentView, self).create_model(form)

    def update_model(self, form, model):
        """fix date -> datetime"""
        published = getattr(form, 'published')
        clean_data = published.data.split(' ', 1)[0]
        published.data = datetime.strptime(clean_data, '%Y-%m-%d')
        return super(DocumentView, self).update_model(form, model)

    @expose('/<int:id>/toggle-feature')
    def toggle_feature(self, id):
        the_doc = models.Document.query.get_or_404(id)
        the_doc.featured = not the_doc.featured
        models.db.session.add(the_doc)
        models.db.session.commit()
        return redirect(request.referrer or url_for('.index'))

    @expose('/<int:id>/confirm-removal')
    def confirm_delete(self, id):
        the_doc = models.Document.query.get_or_404(id)
        next = request.args.get('next') or url_for('.index')
        return self.render('admin/documents/remove.html',
                           document=the_doc, next=next)


admin = Admin(app,
    name='Windermere Admin',
    index_view=HomeView(name="Windermere Admin"),
    base_template='admin/master.html')

admin.add_view(DocumentView(models.Document, models.db.session,
                            name='Documents', endpoint='documents'))

admin.add_view(PhotoView(models.ScenicPhoto, models.db.session,
                         name='Photos', endpoint='photos'))

admin.add_view(PeopleView(models.Person, models.db.session,
                          name='People', endpoint='people'))

admin.add_view(AccountsView(name='Accounts', endpoint='accounts'))
