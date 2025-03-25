import logging
import datetime
import re
import os.path
import pytz
from itertools import chain
from urlparse import urlparse, urljoin

from flask import render_template, flash, redirect, url_for, send_from_directory
# noinspection PyUnresolvedReferences
from flask.ext.login import current_user
# noinspection PyUnresolvedReferences
from flask.ext.mail import Message
from flask.globals import request
# noinspection PyUnresolvedReferences
from flask.ext.security import login_required, roles_required, user_registered
from sqlalchemy.sql.expression import and_


from app import app, db, repo, jenkins, mail, user_datastore
from app.hgapi.hgapi import HgException
from app.model import Build, Changeset, CodeInspection, Review, Diff, Head
from app.view import Pagination
from app.utils import get_reviews, get_revision_status, get_heads, el
from app.locks import repo_read, repo_write, rework_db_read, rework_db_write
from app.perfutils import performance_monitor
from app.view import SearchForm
from app.jira import jira_integrate
from app.crypto import encryption, decryption




logger = logging.getLogger(__name__)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.context_processor
def inject_user():
    return dict(user=current_user)


# noinspection PyUnusedLocal
def new_user_registered(sender, **extra):
    user = extra["user"]
    role = user_datastore.find_role("user")
    user_datastore.add_role_to_user(user, role)


user_registered.connect(new_user_registered, app)


def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and \
           ref_url.netloc == test_url.netloc


def refresh_heads():
    repo.hg_sync()
    Head.query.delete()
    for repo_head in get_heads(repo):
        head = Head(repo_head)
        logger.debug("Adding head: %s", head.title)
        db.session.add(head)
    db.session.commit()



# /                         [GET]   -> /changes/active
# /changes/refresh          [GET]   -> refrrer
# /revision/<node>/abandon  [POST]                                  admin
# /changes/new              [GET]
# /changes/new/<page>       [GET]
# /changes/active           [GET]
# /changes/active/<page>    [GET]
# /changes/merged           [GET]
# /changes/merged/<page>    [GET]
# /changes/abandoned        [GET]
# /changes/abandoned/<page> [GET]
# /changeset/<id>/inspect   [POST] -> /changeset/<id>               login
# /changeset/<id>/build     [POST] -> /changeset/<id>               login
# /changeset/<id>/abandon   [POST] -> /changeset/<id>               admin
# /changeset/<id>           [GET]
# /review                   [POST] -> /changes/new                  login
# /review/<id>              [POST] -> /review/<id>                  login
# /review/<id>/abandon      [POST] -> /review/<id>                  admin
# /review/<id>/target       [POST] -> /review/<id>                  login
# /review/<id>              [GET]
# /changeset/<id>/merge     [POST] -> /changeset/<id>               admin
# /changelog/<start>/<stop> [GET]
# /user_preferences         [GET]                                   login
# /user_preferences         [POST] -> /user_preferences             login



@app.route('/')
def index():
    return redirect(url_for('changes_active'))


@app.route('/changes/refresh')
@repo_write
@rework_db_write
@performance_monitor("Request /changes/refresh")
def changes_refresh():
    logger.info("Requested URL /changes/refresh")
    refresh_heads()
    if is_safe_url(request.referrer):
        return redirect(request.referrer)
    return redirect(url_for('changes_active'))


@app.route("/revision/<node>/abandon")
def revision_abandon_login_redirect(node):
    head = Head.query.filter(Head.node == node).first()
    if head is None:
        return redirect(url_for("index"))
    elif head.review_id is None:
        return redirect(url_for("changes_new"))
    else:
        return redirect(url_for("review_info", review_id=head.review_id))


@app.route("/revision/<node>/abandon", methods=["POST"])
@login_required
@roles_required('admin')
@repo_write
@rework_db_write
@performance_monitor("Request /revision/<node>/abandon [POST]")
def revision_abandon(node):
    logger.info("Requested URL /revision/%s/abandon [POST]", node)
    refresh_heads()
    revision = repo.revision(node)
    rev_status = get_revision_status(repo, revision)
    if rev_status != "new" and rev_status != "rework":
        flash("Revision {0} is {1} and cannot be abandoned. Refresh list of revisions.".format(revision.node, rev_status), "error")
        logger.info("Revision {0} is {1} and cannot be abandoned".format(revision.node, rev_status))
        if is_safe_url(request.referrer):
            return redirect(request.referrer)
        return redirect(url_for('index'))
    #TODO: Multiple bookmarks
    changeset = Changeset(revision.name, revision.email, revision.title,
                          revision.node, el(revision.bookmarks),
                          "ABANDONED")
    db.session.add(changeset)
    Head.query.filter(Head.node == revision.node).delete()
    db.session.commit()
    repo.hg_close_branch(revision.node)
    if is_safe_url(request.referrer):
        return redirect(request.referrer)
    return redirect(url_for("index"))


@app.route('/changes/new', defaults={'page': 1})
@app.route('/changes/new/<int:page>')
@rework_db_read
@performance_monitor("Request /changes/new")
def changes_new(page):
    logger.info("Requested URL /changes/new")

    query = Head.query.filter(Head.review_id == None)
    query = query.order_by(Head.created_date).paginate(page, app.config["PER_PAGE"])
    total = query.total
    revisions = query.items
    pagination = Pagination(page, app.config["PER_PAGE"], total)

    return render_template('new.html', revisions=revisions,
                           pagination=pagination)


@app.route('/changes/active', defaults={'page': 1})
@app.route('/changes/active/<int:page>')
def changes_active(page):
    form = SearchForm()
    data = get_reviews("ACTIVEandCONFLICT", page, request)
    return render_template('active.html', reviews=data["r"],
                           form=form, pagination=data["p"])


@app.route('/changes/merged', defaults={'page': 1})
@app.route('/changes/merged/<int:page>')
def changes_merged(page):
    form = SearchForm()
    data = get_reviews("MERGED", page, request)
    return render_template('merged.html', reviews=data["r"], form=form, pagination=data["p"])
    
    
@app.route('/changes/abandoned', defaults={'page': 1})
@app.route('/changes/abandoned/<int:page>')
def changes_abandoned(page):
    form = SearchForm()
    data = get_reviews("ABANDONED", page, request)
    return render_template('abandoned.html', reviews=data["r"], form=form, pagination=data["p"])


@app.route('/changeset/<int:cs_id>/inspect')
def inspect_diff_login_redirect(cs_id):
    return redirect(url_for('changeset_info', cs_id=cs_id))


@app.route('/changeset/<int:cs_id>/inspect', methods=['POST'])
@login_required
@repo_read
@roles_required('user')
def inspect_diff(cs_id):
    cs = Changeset.query.filter(Changeset.id == cs_id).first()
    if cs is None:
        flash("Changeset {0} doesn't exist".format(cs_id), "error")
        logger.error("Changeset %d doesn't exist", cs_id)
        return redirect(url_for('index'))
    redirect_url = redirect(url_for('changeset_info', cs_id=cs_id))
    if current_user.cc_login is None:
        flash("Code Collaborator login is not configured properly.", "error")
        logger.error("User account %s cc_login is not configured", current_user.email)
        return redirect_url
    if not cs.is_active():
        logger.error("Cannot schedule inspection. Changeset %d is not active "
                     "within review %d. Active changeset is %d",
                     cs.id, cs.review.id, cs.review.active_changeset.id)
        flash("Changeset is not active. Cannot schedule inspection.", "error")
        return redirect_url
    if cs.review.inspection is None:
        if cs.review.target is None:
            logger.error("Cannot schedule inspection. Review %d has no target",
                         cs.review.id)
            flash("Review has no target release. Cannot schedule inspection",
                  "error")
            return redirect_url
        msg = "Code Inspection is scheduled for processing"
        ci = CodeInspection(current_user.cc_login, cs.review)
        db.session.add(ci)
        db.session.commit()
        logger.info("CodeInspection record %d has been created for review %d",
                    ci.id, cs.review.id)
    else:
        msg = "Rework is scheduled for upload to CodeCollaborator"
    if cs.diff is not None:
        logger.error("Cannot upload diff for changeset %d. Already exists "
                     "diff %d", cs.id, cs.diff.id)
        flash("Rework has been already scheduled for upload", "error")
        return redirect_url
    root = repo.hg_ancestor(cs.sha1, cs.review.target)
    diff = Diff(cs, root)
    db.session.add(diff)
    db.session.commit()
    logger.info("Diff record %d has been created for changeset %d",
                diff.id, cs.id)
    db.session.commit()

    flash(msg, "notice")
    return redirect_url


@app.route('/changeset/<int:cs_id>/build')
def jenkins_build_login_redirect(cs_id):
    return redirect(url_for('changeset_info', cs_id=cs_id))


@app.route('/changeset/<int:cs_id>/build', methods=['POST'])
@login_required
@repo_read
@roles_required('user')
def jenkins_build(cs_id):
    logger.info("Requested URL /changeset/%d/build [POST]", cs_id)
    changeset = Changeset.query.filter(Changeset.id == cs_id).first()
    if changeset is None:
        flash("Changeset {0} doesn't exist".format(cs_id), "error")
        logger.error("Changeset %d doesn't exist", cs_id)
        return redirect(url_for('index'))
    if changeset.review.target in app.config["BRANCH_MAPPING"]:
        job_name = app.config["BRANCH_MAPPING"][changeset.review.target]
    else:
        job_name = changeset.review.target + "-ci"
    build_info = jenkins.run_job(job_name, changeset.sha1)
    if build_info is None:
        flash("Scheduling Jenkins build failed", "error")
        return redirect(url_for("changeset_info", cs_id=cs_id))

    build = Build(changeset_id=changeset.id, status=build_info["status"],
                  job_name=job_name, build_url=build_info["build_url"])
    build.request_id = build_info["request_id"]
    build.scheduled = build_info["scheduled"]
    if "build_number" in build_info:
        build.build_number = build_info["build_number"]
    db.session.add(build)
    db.session.commit()
    logger.info("Jenkins build for changeset id " + str(changeset.id) +
                " has been added to queue. Changeset: " + str(changeset) +
                " , build: " + str(build))
    flash("Jenkins build has been added to the queue", "notice")
    return redirect(url_for('changeset_info', cs_id=cs_id))


@app.route('/changeset/<int:cs_id>/abandon')
def changeset_abandon_login_redirect(cs_id):
    return redirect(url_for('changeset_info', cs_id=cs_id))


@app.route("/changeset/<int:cs_id>/abandon", methods=["POST"])
@login_required
@roles_required('admin')
@repo_write
@performance_monitor("Request /changeset/<cs_id>/abandon [POST]")
#TODO: If inspection scheduled, cannot abandon changeset
#TODO: Only active changeset or its descendant can be abandoned
#TODO: Abandoning active changeset should move bookmark backwards
def changeset_abandon(cs_id):
    logger.info("Requested URL /changeset/%d/abandon [POST]", cs_id)
    changeset = Changeset.query.filter(Changeset.id == cs_id).first()
    if changeset is None:
        flash("Changeset {0} doesn't exist".format(cs_id), "error")
        logger.error("Changeset %d doesn't exist", cs_id)
        return redirect(url_for('index'))
    if not changeset.is_active():
        flash("Not active changeset cannot be abandoned", "error")
        logger.error("Changeset %d is not active and cannot be abandoned", cs_id)
        return redirect(url_for('changeset_info', cs_id=cs_id))
    changeset.status = "ABANDONED"
    db.session.commit()
    repo.hg_sync()
    if changeset.sha1 in repo.hg_heads():
        repo.hg_close_branch(changeset.sha1)
    flash("Changeset '{title}' (SHA1: {sha1}) has been abandoned".format(title=changeset.title,
                                                                         sha1=changeset.sha1), "notice")
    return redirect(url_for("review_info", review_id=changeset.review_id))


@app.route('/changeset/<int:cs_id>')
@performance_monitor("Request /changeset/<cs_id>")
def changeset_info(cs_id):
    logger.info("Requested URL /changeset/%d", cs_id)
    cs = Changeset.query.filter(Changeset.id == cs_id).first()
    if cs is None:
        flash("Changeset {0} doesn't exist".format(cs_id), "error")
        logger.error("Changeset %d doesn't exist", cs_id)
        return redirect(url_for("index"))
    prev = Changeset.query.filter(and_(Changeset.created_date < cs.created_date,
                                       Changeset.status == "ACTIVE",
                                       Changeset.review_id == cs.review_id))\
        .order_by(Changeset.created_date).all()
    if prev:
        prev = prev[-1]
    next_ = Changeset.query.filter(and_(Changeset.created_date > cs.created_date,
                                        Changeset.status == "ACTIVE",
                                        Changeset.review_id == cs.review_id))\
        .order_by(Changeset.created_date).first()
    review = Review.query.filter(Review.id == cs.review_id).first()

    link_hgweb_static = app.config["HG_PROD"] + "/rev/"
    return render_template("changeset.html", review=review, cs=cs,  next=next_,
                           prev=prev, link_hgweb_static=link_hgweb_static)

    
@app.route('/review')
def review_new_login_redirect():
    return redirect(url_for('changes_new'))


@app.route("/review", methods=["POST"])
@login_required
@repo_write
@rework_db_write
@performance_monitor("Request /review [POST]")
def review_new():
    
    if (current_user.name == "") or (current_user.name == "None") or (current_user.name is None):
        flash("No username specified. To start a review username is required.", "error")
        return redirect(url_for('user_preferences'))
        
    logger.info("Requested URL /review [POST]")
    refresh_heads()
    revision = repo.revision(request.form['node'])
    rev_status = get_revision_status(repo, revision)
    if rev_status != "new":
        flash("Revision {0} is {1} and cannot be inspected. Refresh list of revisions.".format(revision.node, rev_status), "error")
        logger.info("Revision {0} is {1} and cannot be inspected.".format(revision.node, rev_status))
        return redirect(url_for('changes_new'))
    #TODO: Multiple bookmarks
    review = Review(owner=current_user.name, owner_email=current_user.email, title=revision.title,
                    bookmark=el(revision.bookmarks), status="ACTIVE")
    targets = repo.hg_targets(revision.rev, app.config['PRODUCT_BRANCHES'])
    review.add_targets(targets)
    #TODO: Multiple bookmarks
    changeset = Changeset(revision.name, revision.email, revision.title,
                          revision.node, el(revision.bookmarks),
                          "ACTIVE")
    review.changesets.append(changeset)
    db.session.add(review)
    Head.query.filter(Head.node == revision.node).delete()
    db.session.commit()
    return redirect(url_for('changeset_info', cs_id=changeset.id))


@app.route('/review/<int:review_id>', methods=["POST"])
@login_required
@repo_write
@rework_db_write
@performance_monitor("Request /review/<int:review_id> [POST]")
def review_rework(review_id):
    logger.info("Requested URL /review/%d [POST]", review_id)
    review = Review.query.filter(Review.id == review_id).first()
    if review is None:
        flash("Review {0} doesn't exist".format(review_id), "error")
        logger.error("Review %d doesn't exist", review_id)
        return redirect(url_for("index"))
    refresh_heads()
    revision = repo.revision(request.form["node"])
    rev_status = get_revision_status(repo, revision)
    if rev_status != "rework":
        flash("Revision {0} is {1} and cannot be inspected. Refresh list of revisions.".format(revision.node, rev_status), "error")
        logger.info("Revision {0} is {1} and cannot be inspected.".format(revision.node, rev_status))
        return redirect(url_for('review_info', review_id=review.id))
    #TODO: Multiple bookmarks
    changeset = Changeset(revision.name, revision.email, revision.title,
                          revision.node, el(revision.bookmarks), "ACTIVE")
    review.status = "ACTIVE"
    changeset.review_id = review.id
    db.session.add(changeset)
    Head.query.filter(Head.node == revision.node).delete()
    Head.query.filter(Head.review_id == review.id).update({'review_id': None})
    db.session.commit()
    flash("Changeset '{title}' (SHA1: {sha1}) has been marked as rework".format(title=changeset.title, sha1=changeset.sha1),
          "notice")
    return redirect(url_for('changeset_info', cs_id=changeset.id))


@app.route('/review/<int:review_id>/abandon')
def review_abandon_login_redirect(review_id):
    return redirect(url_for('review_info', review_id=review_id))


@app.route('/review/<int:review_id>/abandon', methods=["POST"])
@repo_write
@login_required
@roles_required('admin')
@performance_monitor("Request /review/<int:review_id>/abandon [POST]")
def review_abandon(review_id):
    logger.info("Requested URL /review/%d/abandon [POST]", review_id)
    review = Review.query.filter(Review.id == review_id).first()
    if review is None:
        flash("Review {0} doesn't exist".format(review_id), "error")
        logger.error("Review %d doesn't exist", review_id)
        return redirect(url_for("index"))
    review.status = "ABANDONED"
    review.abandoned_date = datetime.datetime.utcnow()
    Head.query.filter(Head.review_id == review.id).update({'review_id': None})
    db.session.commit()
    repo.hg_sync()
    heads = repo.hg_heads()
    for c in review.changesets:
        if c.sha1 in heads:
            repo.hg_close_branch(c.sha1)
    flash("Review has been abandoned", "notice")
    return redirect(url_for('changes_active'))


@app.route('/review/<int:review_id>/target')
def review_set_target_login_redirect(review_id):
    return redirect(url_for('review_info', review_id=review_id))


@app.route("/review/<int:review_id>/target", methods=["POST"])
@login_required
@performance_monitor("Request /review/<id>/target")
def review_set_target(review_id):
    logger.info("Requested URL /review/%d/target [POST]", review_id)
    review = Review.query.filter(Review.id == review_id).first()
    if review is None:
        flash("Review {0} doesn't exist".format(review_id), "error")
        logger.error("Review %d doesn't exist", review_id)
        return redirect(url_for("index"))
    #TODO: If inspection scheduled, target cannot change
    try:
        review.set_target(request.form['target'])
    except Exception, ex:
        flash(str(ex), "error")
    else:
        db.session.commit()
        flash("Target branch has been set to <b>{0}</b>".format(review.target), "notice")
    return redirect(url_for('review_info', review_id=review.id))


@app.route('/review/<int:review_id>')
@performance_monitor("Request /review/<int:review_id>")
@rework_db_read
def review_info(review_id):
    logger.info("Requested URL /review/%d", review_id)
    review = Review.query.filter(Review.id == review_id).first()
    if review is None:
        flash("Review {0} doesn't exist".format(review_id), "error")
        logger.error("Review %d doesn't exist", review_id)
        return redirect(url_for("index"))
    reworks = Head.query.filter(Head.review_id == review.id).all()
    
    is_admin = False
    if "admin" in current_user.roles:
            is_admin = True
            
    for changeset in review.changesets:
        if changeset.is_active():
            break
        
    link_hgweb_static = app.config["HG_PROD"] + "/rev/"
    return render_template("review.html", review=review, descendants=reworks, is_admin=is_admin, link_hgweb_static=link_hgweb_static, changeset=changeset)


@app.route('/changeset/<int:cs_id>/merge')
def merge_branch_login_redirect(cs_id):
    return redirect(url_for('changeset_info', cs_id=cs_id))


@app.route('/changeset/<int:cs_id>/merge', methods=['POST'])
@login_required
@roles_required('admin')
@repo_write
@performance_monitor("Request /changeset/<cs_id>/merge")
def merge_branch(cs_id):
    logger.info("Requested URL /changeset/%d/merge", cs_id)
    changeset = Changeset.query.filter(Changeset.id == cs_id).first()
    if changeset is None:
        flash("Changeset {0} doesn't exist".format(cs_id), "error")
        logger.error("Changeset %d doesn't exist", cs_id)
        return redirect(url_for("index"))
    review = Review.query.filter(Review.id == changeset.review_id).first()
    bookmark = review.target

    link = url_for("review_info", review_id=review.id, _external=True)

    refresh_heads()
    #TODO: Only active changeset can be merged

    logger.info("Merging %s into %s", changeset.sha1, review.target)
    repo.hg_update(bookmark)

    try:
        output = repo.hg_merge(changeset.sha1)
    except HgException as e:
        output = str(e)

    logger.info("Merge result: {output}".format(output=output))

    error = False
    subject = u"Successful merge '{name}' with {dest}".format(name=review.title, sha1=changeset.sha1, dest=review.target)

    if "abort: nothing to merge" in output:
        logger.info("Creating dummy commit for merge of {review} into {target}".format(review=review.id, target=review.target))
        open(os.path.join(app.config["REPO_PATH"], "dummy.txt"), "a").close()
        repo.hg_add("dummy.txt")
        repo.hg_commit("Prepare for merge with {target}".format(target=review.target))
        repo.hg_remove("dummy.txt")
        repo.hg_commit("Prepare for merge with {target}".format(target=review.target), amend=True)
        try:
            output = repo.hg_merge(changeset.sha1)
        except HgException as e:
            output = str(e)
        logger.info("Merge result: {output}".format(output=output))

    if "abort: nothing to merge" in output:
        flash("Unexpeced merge problem - administrator has been contacted")
        subject = u"Unexpected merge problem - can't merge '{name}' with {dest}".format(name=review.title,
                                                                                        dest=review.target)
        logger.error("Conflict when trying descendant merge of review {review} - unexpected conflict".format(
            review=review.id))
        error = True
    if ("use 'hg resolve' to retry unresolved" in output) or (("local changed" in output) and ("which remote deleted" in output)) or (("remote changed" in output) and ("which local deleted" in output)):
        flash("There is merge conflict. Merge with bookmark " + bookmark +
              " and try again.", "error")
        subject = u"Merge conflict - can't merge '{name}' with {dest}".format(name=review.title, dest=review.target)
        error = True
    elif "abort: merging with a working directory ancestor has no effect" in output:
        repo.hg_update(changeset.sha1)
        result = repo.hg_bookmark(bookmark, force=True)
        logger.info(result)
    else:
        repo.hg_commit("Merged with {target}".format(target=review.target))

    repo.hg_update("null", clean=True)
    repo.hg_purge()

    try:
        if not error:
            repo.hg_push()
    except HgException, ex:
        if not "no changes found" in ex.message:
            raise 
            
    try:
        if not error:
            jira_integrate(changeset, current_user)
    except:
          logger.exception("Exception when integrating with JIRA regarding review %d merge", review.id)
          
    try:
        html = subject + u"<br/><br/>Review link: <a href=\"{link}\">{link}</a><br/>Owner: {owner}<br/>SHA1: {sha1} ".format(
            link=link, sha1=changeset.sha1, owner=changeset.owner)

        recpts = [review.owner_email]
        recpts = list(set(recpts))

        msg = Message(subject,
                      sender=app.config["SECURITY_EMAIL_SENDER"],
                      recipients=recpts)
        msg.html = html
        mail.send(msg)
    except:
        logger.exception("Exception when sending confirmation e-mail regarding review %d merge", review.id)

    if not error:
        review.status = "MERGED"
        review.close_date = datetime.datetime.utcnow()
        Head.query.filter(Head.review_id == review.id).update({'review_id': None})
        db.session.commit()
        flash("Changeset has been merged. Review has been closed.", "notice")
    else:
        review.status = "CONFLICT"
        db.session.commit()

    return redirect(url_for('index'))


@app.route('/changelog/<start>/<stop>')
@repo_read
def changelog(start, stop):
    repo.hg_sync()
    rev_start = repo.revision(start)
    rev_stop = repo.revision(stop)

    rev_list = {}
    for rev in repo.revisions([1, rev_stop.node]):
        rev_list[rev.node] = rev
    for rev in repo.revisions([1, rev_start.node]):
        rev_list.pop(rev.node, None)

    jira_re = re.compile("(IWD-\d{3,5})|(EVO-\d+)|(IAP-\d+)", re.IGNORECASE)
    jira_list = {}
    for node, rev in rev_list.items():
        tickets = set(chain(*jira_re.findall(rev.desc))) - set([''])
        for ticket in tickets:
            key = ticket.upper()
            if key not in jira_list:
                jira_list[key] = ''
            jira_list[key] += '\n' + rev.desc

    return render_template("log.html", start=start, stop=stop, jira_list=sorted(jira_list.items()))

@app.route('/user_preferences' , methods=['GET','POST'])
@login_required
def user_preferences():
    if request.method == 'GET':
        if current_user.jira_password is None:
            return render_template('preferences.html', user=current_user, password = "")
        else:
            return render_template('preferences.html', user=current_user, password = decryption(current_user.jira_password))
    current_user.name = request.form['name']
    current_user.cc_login = request.form['cc_login']
    current_user.jira_login = request.form['jira_login']
    current_user.jira_password = encryption(request.form['jira_password'])
    db.session.commit()
    flash('User successfully updated his preferences')
    logger.info('User {email} successfully updated preferences.'.format(email=current_user.email))
    return redirect(url_for('user_preferences'))

@app.errorhandler(Exception)
def internal_error(ex):
    logger.exception(ex)
    import traceback
    error = {'message': str(ex), 'stacktrace': traceback.format_exc()}
    return render_template('500.html', error=error), 500

