#!/usr/bin/env python
# coding=utf-8


from flask import Blueprint, redirect, url_for, flash
from flask_login import login_required, current_user

from rpress.database import db
from rpress.helpers.template.common import render_template
from rpress.models import User
from rpress.runtimes.password import check_password_hash
from rpress.forms import ProfilesForm, PasswordForm


profiles_admin = Blueprint('profiles_admin', __name__)


@profiles_admin.route('/edit', methods=['GET', 'POST'])
@login_required
def edit():
    """"""
    user = User.query.filter_by(id=current_user.id).first()
    if user is None:
        return
    form = ProfilesForm(obj=user)

    if form.validate_on_submit():
        form.populate_obj(user)
        db.session.add(user)
        db.session.commit()
    else:
        pass

    return render_template('rp/profiles_admin/index.html', form=form)


@profiles_admin.route('/password', methods=['GET', 'POST'])
@login_required
def change_password():
    """"""
    user = User.query.filter_by(id=current_user.id).first()
    if user is None:
        return  # TODO

    form = PasswordForm()

    if form.validate_on_submit():
        if check_password_hash(user.password, form.data['password_old']):
            user.password = form.data['password_new']

            db.session.add(user)
            db.session.commit()

            flash('password is changed!')
            return redirect(url_for('profiles_admin.edit'))

        else:
            flash("old password is NOT correct")

    else:
        pass

    return render_template('rp/profiles_admin/change_password.html', form=form)
