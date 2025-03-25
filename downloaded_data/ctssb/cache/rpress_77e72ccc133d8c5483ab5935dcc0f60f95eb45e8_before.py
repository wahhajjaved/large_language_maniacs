#!/usr/bin/env python
#coding=utf-8


from __future__ import print_function, unicode_literals, absolute_import

import re

from sqlalchemy import desc
import flask
from flask import g, request, redirect, url_for, flash
from flask.ext.login import login_required, current_user

from rpress.constants import PUBLISH_FSM_DEFINE, SITE_SETTINGS_KEY_LIST
from rpress import db
from rpress.models import User, Site, Post, Term, SiteSetting
from rpress.helpers.template.common import render_template
from rpress.helpers.validate import is_valid_post_type
from rpress.helpers.fsm_publish import PublishFSM
from rpress.helpers.mulit_site import get_current_request_site
from rpress.helpers.site import get_current_request_site_info
from rpress.forms import PostEditForm, TermEditFrom, SettingsForm


site_admin = flask.Blueprint('site_admin', __name__)


@site_admin.route('', methods=['GET'])
@login_required
#----------------------------------------------------------------------
def index():
    """"""
    return render_template("rp/site_admin/index.html")


@site_admin.route('/post/list/<string:type>', methods=['GET'])
@login_required
#----------------------------------------------------------------------
def post_list(type):
    """"""
    if not is_valid_post_type(type):
        return  #!!!

    site = get_current_request_site()

    posts = Post.query.filter_by(site=site, type=type).order_by(desc('publish_date')).all()

    return render_template("rp/site_admin/post_list.html", posts=posts, post_type=type)


@site_admin.route('/post/<uuid:uuid>/publish/<string:trigger>', methods=['GET'])
@login_required
#----------------------------------------------------------------------
def post_publish_state(uuid, trigger):
    """"""
    post = Post.query.filter_by(uuid=str(uuid)).first_or_404()  #!!!
    if post.publish_state not in PublishFSM.states:
        return  #!!!

    post_publish_fsm = PublishFSM(init_state=post.publish_state)
    if trigger not in post_publish_fsm.triggers:
        return  #!!!

    if not post_publish_fsm.do_trigger(trigger_name=trigger):
        return  #!!!

    print('Done......')
    post.publish_state = post_publish_fsm.state
    if post_publish_fsm.state == PUBLISH_FSM_DEFINE.STATE.PUBLISHED:
        post.published = True
    else:
        post.published = False

    db.session.add(post)
    db.session.commit()

    return redirect(url_for('site_admin.post_edit', uuid=uuid))


@site_admin.route('/post/<string:type>/new', methods=['GET',])
@login_required
#----------------------------------------------------------------------
def post_new(type):
    """"""
    if not is_valid_post_type(type):
        return  #!!!

    user = User.query.filter_by(id=current_user.id).first()
    if user is None:
        return  #!!!

    site = get_current_request_site()

    post = Post(author=user, site=site)
    db.session.add(post)
    db.session.commit()

    return redirect(url_for('.post_edit', uuid=post.uuid))


@site_admin.route('/post/<uuid:uuid>/edit', methods=['GET', 'POST'])
@login_required
#----------------------------------------------------------------------
def post_edit(uuid):
    """"""
    post = Post.query.filter_by(uuid=str(uuid)).first_or_404()  #!!!
    form = PostEditForm(obj=post)

    if form.validate_on_submit():
        form.populate_obj(post)
        post.content = re.sub(r'\r', '\n', re.sub(r'\r\n', '\n', form.data['content']))

        db.session.add(post)
        db.session.commit()

        flash("post updated", "success")
        #return redirect(url_for('.blog'))
    else:
        flash('post edit error')
        pass

    post_publish_fsm = PublishFSM(init_state=post.publish_state)
    return render_template("rp/site_admin/post_edit.html", form=form, post=post, publish_triggers=post_publish_fsm.possible_triggers)


@site_admin.route('/term/list/<string:type>', methods=['GET', ])
@login_required
#----------------------------------------------------------------------
def term_list(type):
    """"""
    if type not in ['category', 'tag']:
        return  #!!!

    site = get_current_request_site()

    terms = Term.query.filter_by(site=site, type=type).order_by(desc('name')).all()
    return render_template('rp/site_admin/term_list.html', terms=terms)


@site_admin.route('/term/<string:name>/edit', methods=['GET', 'POST'])
@login_required
#----------------------------------------------------------------------
def term_edit(name):
    """"""
    site = get_current_request_site()

    term = Term.query.filter_by(site=site, name=name).first_or_404()  #!!!
    form = TermEditFrom(obj=term)

    if form.validate_on_submit():
        form.populate_obj(term)

        db.session.add(term)
        db.session.commit()

        flash("term updated", "success")
        #return redirect(url_for('.blog'))
    else:
        flash('term edit error')
        pass

    return render_template("rp/site_admin/term_edit.html", form=form, term=term)


@site_admin.route('/settings', methods=['GET',])
@login_required
#----------------------------------------------------------------------
def settings():
    """"""
    content = {
        'site': get_current_request_site_info(),
    }

    return render_template('rp/site_admin/settings.html', content=content)


@site_admin.route('/setting/<string:key>/edit', methods=['GET', 'POST'])
@login_required
#----------------------------------------------------------------------
def setting_edit(key):
    """"""
    site = get_current_request_site()
    site_setting = SiteSetting.query.filter_by(site=site, key=key).first()
    if site_setting is None:
        site_setting = SiteSetting(site, key, None)

    form = SettingsForm(obj=site_setting)

    if form.validate_on_submit():
        form.populate_obj(site_setting)

        db.session.add(site_setting)
        db.session.commit()

        flash("setting updated", "success")
    else:
        flash('setting edit error')

    return render_template("rp/site_admin/setting_edit.html", form=form, site_setting=site_setting)
