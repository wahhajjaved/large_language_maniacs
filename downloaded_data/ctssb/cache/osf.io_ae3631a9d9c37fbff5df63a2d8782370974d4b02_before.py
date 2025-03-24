# -*- coding: utf-8 -*-
import httplib as http
import logging
import time

from modularodm.exceptions import ValidationValueError
import framework
from framework import request, User, status
from framework.auth.decorators import collect_auth
from framework.exceptions import HTTPError
from framework import forms
from framework.auth.signals import user_registered
from framework.auth.forms import SetEmailAndPasswordForm, PasswordForm
from framework.sessions import session

from website import mails, language
from website.project.model import unreg_contributor_added
from website.models import Node
from website.profile import utils
from website.util import web_url_for, is_json_request
from website.util.permissions import expand_permissions, ADMIN

from website.project.decorators import (
    must_not_be_registration, must_be_valid_project, must_be_contributor,
    must_be_contributor_or_public, must_have_permission,
)


logger = logging.getLogger(__name__)


@collect_auth
@must_be_valid_project
def get_node_contributors_abbrev(**kwargs):

    auth = kwargs.get('auth')
    node_to_use = kwargs['node'] or kwargs['project']

    max_count = kwargs.get('max_count', 3)
    if 'user_ids' in kwargs:
        users = [
            User.load(user_id) for user_id in kwargs['user_ids']
            if user_id in node_to_use.contributors
        ]
    else:
        users = node_to_use.contributors

    if not node_to_use.can_view(auth):
        raise HTTPError(http.FORBIDDEN)

    contributors = []

    n_contributors = len(users)
    others_count, others_suffix = '', ''

    for index, user in enumerate(users[:max_count]):

        if index == max_count - 1 and len(users) > max_count:
            separator = ' &'
            others_count = n_contributors - 3
            others_suffix = 's' if others_count > 1 else ''
        elif index == len(users) - 1:
            separator = ''
        elif index == len(users) - 2:
            separator = ' &'
        else:
            separator = ','

        contributors.append({
            'user_id': user._primary_key,
            'separator': separator,
        })

    return {
        'contributors': contributors,
        'others_count': others_count,
        'others_suffix': others_suffix,
    }


@collect_auth
@must_be_valid_project
def get_contributors(**kwargs):

    auth = kwargs.get('auth')
    node = kwargs['node'] or kwargs['project']

    if not node.can_view(auth):
        raise HTTPError(http.FORBIDDEN)

    contribs = utils.serialize_contributors(node.contributors, node=node)

    return {'contributors': contribs}


@collect_auth
@must_be_valid_project
def get_contributors_from_parent(**kwargs):

    auth = kwargs.get('auth')
    node_to_use = kwargs['node'] or kwargs['project']

    parent = node_to_use.node__parent[0] if node_to_use.node__parent else None
    if not parent:
        raise HTTPError(http.BAD_REQUEST)

    if not node_to_use.can_view(auth):
        raise HTTPError(http.FORBIDDEN)

    contribs = [
        utils.add_contributor_json(contrib)
        for contrib in parent.contributors
        if contrib not in node_to_use.contributors
    ]

    return {'contributors': contribs}


@must_have_permission(ADMIN)
def get_recently_added_contributors(**kwargs):

    auth = kwargs.get('auth')
    node_to_use = kwargs['node'] or kwargs['project']

    if not node_to_use.can_view(auth):
        raise HTTPError(http.FORBIDDEN)

    contribs = [
        utils.add_contributor_json(contrib)
        for contrib in auth.user.recently_added
        if contrib.is_active()
        if contrib not in node_to_use.contributors
    ]

    return {'contributors': contribs}


@must_be_valid_project  # returns project
@must_be_contributor
@must_not_be_registration
def project_before_remove_contributor(**kwargs):

    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']

    contributor = User.load(request.json.get('id'))

    # Forbidden unless user is removing herself
    if not node.has_permission(auth.user, 'admin'):
        if auth.user != contributor:
            raise HTTPError(http.FORBIDDEN)

    prompts = node.callback(
        'before_remove_contributor', removed=contributor,
    )

    if auth.user == contributor:
        prompts.insert(
            0,
            'Are you sure you want to remove yourself from this project?'
        )

    return {'prompts': prompts}


@must_be_valid_project  # returns project
@must_be_contributor
@must_not_be_registration
def project_removecontributor(**kwargs):

    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']

    contributor = User.load(request.json['id'])
    if contributor is None:
        raise HTTPError(http.BAD_REQUEST)

    # Forbidden unless user is removing herself
    if not node.has_permission(auth.user, 'admin'):
        if auth.user != contributor:
            raise HTTPError(http.FORBIDDEN)

    outcome = node.remove_contributor(
        contributor=contributor, auth=auth,
    )

    if outcome:
        if auth.user == contributor:
            framework.status.push_status_message('Removed self from project', 'info')
            return {'redirectUrl': '/dashboard/'}
        framework.status.push_status_message('Contributor removed', 'info')
        return {}

    raise HTTPError(
        http.BAD_REQUEST,
        data={
            'message_long': (
                '{0} must have at least one contributor with admin '
                'rights'.format(
                    node.project_or_component.capitalize()
                )
            )
        }
    )

def deserialize_contributors(node, user_dicts, auth):
    """View helper that returns a list of User objects from a list of
    serialized users (dicts). The users in the list may be registered or
    unregistered users.

    e.g. ``[{'id': 'abc123', 'registered': True, 'fullname': ..},
            {'id': None, 'registered': False, 'fullname'...},
            {'id': '123ab', 'registered': False, 'fullname': ...}]

    If a dict represents an unregistered user without an ID, creates a new
    unregistered User record.

    :param Node node: The node to add contributors to
    :param list(dict) user_dicts: List of serialized users in the format above.
    :param Auth auth:
    """

    # Add the registered contributors
    contribs = []
    for contrib_dict in user_dicts:
        email = contrib_dict['email']
        fullname = contrib_dict['fullname']
        if contrib_dict['id']:
            contributor = User.load(contrib_dict['id'])
        else:
            try:
                contributor = User.create_unregistered(
                    fullname=fullname,
                    email=email)
                contributor.save()
            except ValidationValueError:
                contributor = framework.auth.get_user(username=email)

        # Add unclaimed record if necessary
        if (not contributor.is_registered
                and node._primary_key not in contributor.unclaimed_records):
            contributor.add_unclaimed_record(node=node, referrer=auth.user,
                given_name=fullname,
                email=email)
            contributor.save()
            unreg_contributor_added.send(node, contributor=contributor,
                auth=auth)
        contribs.append({
            'user': contributor,
            'permissions': expand_permissions(contrib_dict.get('permission'))
        })
    return contribs


@unreg_contributor_added.connect
def finalize_invitation(node, contributor, auth):
    record = contributor.get_unclaimed_record(node._primary_key)
    if record['email']:
        send_claim_email(record['email'], contributor, node, notify=True)


@must_be_valid_project
@must_have_permission(ADMIN)
@must_not_be_registration
def project_contributors_post(**kwargs):
    """ Add contributors to a node. """

    node = kwargs['node'] or kwargs['project']
    auth = kwargs['auth']
    user_dicts = request.json.get('users')
    node_ids = request.json.get('node_ids')

    if user_dicts is None or node_ids is None:
        raise HTTPError(http.BAD_REQUEST)

    # Prepare input data for `Node::add_contributors`
    contribs = deserialize_contributors(node, user_dicts, auth=auth)

    node.add_contributors(contributors=contribs, auth=auth)
    node.save()

    for child_id in node_ids:
        child = Node.load(child_id)
        # Only email unreg users once
        child_contribs = deserialize_contributors(
            child, user_dicts, auth=auth
        )
        child.add_contributors(contributors=child_contribs, auth=auth)
        child.save()

    return {'status': 'success'}, 201


@must_be_valid_project # returns project
@must_have_permission(ADMIN)
@must_not_be_registration
def project_manage_contributors(**kwargs):

    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']

    contributors = request.json.get('contributors')

    # Update permissions and order
    try:
        node.manage_contributors(contributors, auth=auth, save=True)
    except ValueError as error:
        raise HTTPError(http.BAD_REQUEST, data={'message_long': error.message})

    # Must redirect user if revoked own access
    if not node.is_contributor(auth.user):
        return {'redirectUrl': node.url}
    if not node.has_permission(auth.user, ADMIN):
        return {'redirectUrl': '/dashboard/'}
    return {}


def get_timestamp():
    return int(time.time())

# TODO: Use throttle?
def send_claim_registered_email(claimer, unreg_user, node, throttle=0):
    unclaimed_record = unreg_user.get_unclaimed_record(node._primary_key)
    referrer = User.load(unclaimed_record['referrer_id'])
    claim_url = web_url_for('claim_user_registered',
            uid=unreg_user._primary_key,
            pid=node._primary_key,
            token=unclaimed_record['token'],
            _external=True)
    # Send mail to referrer, telling them to forward verification link to claimer
    mails.send_mail(referrer.username, mails.FORWARD_INVITE_REGiSTERED,
        user=unreg_user,
        referrer=referrer,
        node=node,
        claim_url=claim_url,
        fullname=unclaimed_record['name']
    )
    # Send mail to claimer, telling them to wait for referrer
    mails.send_mail(claimer.username, mails.PENDING_VERIFICATION_REGISTERED,
        fullname=claimer.fullname,
        referrer=referrer,
        node=node
    )


def send_claim_email(email, user, node, notify=True, throttle=30 * 60):
    """Send an email for claiming a user account. Either sends to the given email
    or the referrer's email, depending on the email address provided.

    :param str email: The address given in the claim user form
    :param User user: The User record to claim.
    :param Node node: The node where the user claimed their account.
    :param bool notify: If True and an email is sent to the referrer, an email
        will also be sent to the invited user about their pending verification.
    :param int throttle: Time period after the referrer is emailed during which
        the referrer will not be emailed again.

    """
    invited_email = email.lower().strip()

    unclaimed_record = user.get_unclaimed_record(node._primary_key)
    referrer = User.load(unclaimed_record['referrer_id'])
    claim_url = user.get_claim_url(node._primary_key, external=True)
    # If given email is the same provided by user, just send to that email
    if unclaimed_record.get('email', None) == invited_email:
        mail_tpl = mails.INVITE
        to_addr = invited_email
    else:  # Otherwise have the referrer forward the email to the user
        if notify:
            pending_mail = mails.PENDING_VERIFICATION
            mails.send_mail(invited_email, pending_mail,
                user=user,
                referrer=referrer,
                fullname=unclaimed_record['name'],
                node=node)
        timestamp = unclaimed_record.get('last_sent')
        if timestamp is None or (get_timestamp() - timestamp) > throttle:
            unclaimed_record['last_sent'] = get_timestamp()
            user.save()
        else:  # Don't send the email to the referrer
            return
        mail_tpl = mails.FORWARD_INVITE
        to_addr = referrer.username
    mails.send_mail(to_addr, mail_tpl,
        user=user,
        referrer=referrer,
        node=node,
        claim_url=claim_url,
        email=invited_email,
        fullname=unclaimed_record['name']
    )
    return to_addr

def verify_claim_token(user, token, pid):
    """View helper that checks that a claim token for a given user and node ID
    is valid. If not valid, throws an error with custom error messages.
    """
    # if token is invalid, throw an error
    if not user.verify_claim_token(token=token, project_id=pid):
        if user.is_registered:
            error_data = {
                'message_short': 'User has already been claimed.',
                'message_long': 'Please <a href="/login/">log in</a> to continue.'}
            raise HTTPError(400, data=error_data)
        else:
            return False
    return True


@must_be_valid_project
def claim_user_registered(**kwargs):
    """View that prompts user to enter their password in order to claim
    contributorship on a project.

    A user must be logged in.
    """
    node = kwargs['node'] or kwargs['project']
    current_user = framework.auth.get_current_user()
    sign_out_url = web_url_for('auth_login', logout=True, next=request.path)
    if not current_user:
        response = framework.redirect(sign_out_url)
        return response
    # Logged in user should not be a contributor the project
    if node.is_contributor(current_user):
        data = {'message_short': 'Already a contributor',
                'message_long': 'The logged-in user is already a contributor to '
                'this project. Would you like to <a href="/logout/">log out</a>?'}
        raise HTTPError(http.BAD_REQUEST, data=data)
    uid, pid, token = kwargs['uid'], kwargs['pid'], kwargs['token']
    unreg_user = User.load(uid)
    if not verify_claim_token(unreg_user, token, pid=node._primary_key):
        raise HTTPError(http.BAD_REQUEST)

    # Store the unreg_user data on the session in case the user registers
    # a new account
    session.data['unreg_user'] = {
        'uid': uid, 'pid': pid, 'token': token
    }

    form = PasswordForm(request.form)
    if request.method == 'POST':
        if form.validate():
            if current_user.check_password(form.password.data):
                node.replace_contributor(old=unreg_user, new=current_user)
                node.save()
                status.push_status_message(
                    'Success. You are now a contributor to this project.',
                    'success')
                return framework.redirect(node.url)
            else:
                status.push_status_message(language.LOGIN_FAILED, 'warning')
        else:
            forms.push_errors_to_status(form.errors)
    if is_json_request():
        form_ret = forms.utils.jsonify(form)
        user_ret = utils.serialize_user(current_user, full=False)
    else:
        form_ret = form
        user_ret = current_user
    return {
        'form': form_ret,
        'user': user_ret,
        'signOutUrl': sign_out_url
    }


@user_registered.connect
def replace_unclaimed_user_with_registered(user):
    """Listens for the user_registered signal. If unreg_user is stored in the
    session, then the current user is trying to claim themselves as a contributor.
    Replaces the old, unregistered contributor with the newly registered
    account.

    """
    unreg_user_info = session.data.get('unreg_user')
    if unreg_user_info:
        unreg_user = User.load(unreg_user_info['uid'])
        pid, token = unreg_user_info['pid'], unreg_user_info['token']
        node = Node.load(pid)
        node.replace_contributor(old=unreg_user, new=user)
        node.save()
        status.push_status_message(
            'Successfully claimed contributor.', 'success')


def claim_user_form(**kwargs):
    """View for rendering the set password page for a claimed user.

    Must have ``token`` as a querystring argument.

    Renders the set password form, validates it, and sets the user's password.
    """
    uid, pid = kwargs['uid'], kwargs['pid']
    token = request.form.get('token') or request.args.get('token')

    # If user is logged in, redirect to 're-enter password' page
    if framework.auth.get_current_user():
        return framework.redirect(web_url_for('claim_user_registered',
            uid=uid, pid=pid, token=token))

    user = framework.auth.get_user(id=uid)  # The unregistered user
    # user ID is invalid. Unregistered user is not in database
    if not user:
        raise HTTPError(http.BAD_REQUEST)
    # If claim token not valid, redirect to registration page
    if not verify_claim_token(user, token, pid):
        return framework.redirect('/account/')
    unclaimed_record = user.unclaimed_records[pid]
    user.fullname = unclaimed_record['name']
    user.update_guessed_names()
    email = unclaimed_record['email']
    form = SetEmailAndPasswordForm(request.form, token=token)
    if request.method == 'POST':
        if form.validate():
            username = form.username.data
            password = form.password.data
            user.register(username=username, password=password)
            # Clear unclaimed records
            user.unclaimed_records = {}
            user.save()
            # Authenticate user and redirect to project page
            response = framework.redirect('/settings/')
            node = Node.load(pid)
            status.push_status_message(language.CLAIMED_CONTRIBUTOR.format(node=node),
                'success')
            return framework.auth.authenticate(user, response)
        else:
            forms.push_errors_to_status(form.errors)
    return {
        'firstname': user.given_name,
        'email': email if email else '',
        'fullname': user.fullname,
        'form': forms.utils.jsonify(form) if is_json_request() else form,
    }


@must_be_valid_project
@must_have_permission(ADMIN)
@must_not_be_registration
def invite_contributor_post(**kwargs):
    """API view for inviting an unregistered user.
    Expects JSON arguments with 'fullname' (required) and email (not required).
    """
    node = kwargs['node'] or kwargs['project']
    fullname = request.json.get('fullname').strip()
    email = request.json.get('email')
    if email:
        email = email.lower().strip()
    if not fullname:
        return {'status': 400, 'message': 'Must provide fullname'}, 400
    # Check if email is in the database
    user = framework.auth.get_user(username=email)
    if user:
        if user.is_registered:
            msg = 'User is already in database. Please go back and try your search again.'
            return {'status': 400, 'message': msg}, 400
        elif node.is_contributor(user):
            msg = 'User with this email address is already a contributor to this project.'
            return {'status': 400, 'message': msg}, 400
        else:
            serialized = utils.add_contributor_json(user)
            # use correct display name
            serialized['fullname'] = fullname
            serialized['email'] = email
    else:
        # Create a placeholder
        serialized = utils.serialize_unregistered(fullname, email)
    return {'status': 'success', 'contributor': serialized}


@must_be_contributor_or_public
def claim_user_post(**kwargs):
    """View for claiming a user from the X-editable form on a project page.
    """
    reqdata = request.json
    # Unreg user
    user = User.load(reqdata['pk'])
    node = kwargs['node'] or kwargs['project']
    unclaimed_data = user.get_unclaimed_record(node._primary_key)
    # Submitted through X-editable
    if 'value' in reqdata:
        email = reqdata['value'].lower().strip()
        send_claim_email(email, user, node, notify=True)
        return {
            'status': 'success',
            'fullname': unclaimed_data['name'],
            'email': email,
        }
    elif 'claimerId' in reqdata:
        claimer_id = reqdata['claimerId']
        claimer = User.load(claimer_id)
        send_claim_registered_email(claimer=claimer, unreg_user=user, node=node)
        return {
            'status': 'success',
            'email': claimer.username,
            'fullname': unclaimed_data['name']
        }
    else:
        raise HTTPError(http.BAD_REQUEST)
