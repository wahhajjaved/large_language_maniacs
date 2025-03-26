# -*- coding: utf-8 -*-
# Copyright 2017 GIG Technology NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# @@license_version:1.3@@

import base64
import json
import logging

from google.appengine.api import users, mail
from google.appengine.ext import ndb, deferred

from framework.plugin_loader import get_config
from framework.utils import now
from mcfw.exceptions import HttpBadRequestException
from mcfw.properties import object_factory
from mcfw.rpc import returns, arguments, serialize_complex_value
from plugins.rogerthat_api.api import messaging, system
from plugins.rogerthat_api.to import UserDetailsTO
from plugins.rogerthat_api.to.messaging import AttachmentTO, Message
from plugins.rogerthat_api.to.messaging.flow import FLOW_STEP_MAPPING
from plugins.rogerthat_api.to.messaging.forms import SignTO, SignFormTO, FormResultTO, FormTO, SignWidgetResultTO
from plugins.rogerthat_api.to.messaging.service_callback_results import FormAcknowledgedCallbackResultTO, \
    MessageCallbackResultTypeTO, TYPE_MESSAGE
from plugins.tff_backend.bizz import get_rogerthat_api_key
from plugins.tff_backend.bizz.agreements import create_hosting_agreement_pdf
from plugins.tff_backend.bizz.authentication import Roles
from plugins.tff_backend.bizz.gcs import upload_to_gcs
from plugins.tff_backend.bizz.intercom_helpers import tag_intercom_users, IntercomTags
from plugins.tff_backend.bizz.iyo.keystore import get_keystore
from plugins.tff_backend.bizz.iyo.see import create_see_document, sign_see_document, get_see_document
from plugins.tff_backend.bizz.iyo.utils import get_iyo_username, get_iyo_organization_id
from plugins.tff_backend.bizz.messages import send_message_and_email
from plugins.tff_backend.bizz.odoo import create_odoo_quotation, update_odoo_quotation, QuotationState, \
    confirm_odoo_quotation, get_odoo_serial_number
from plugins.tff_backend.bizz.rogerthat import put_user_data
from plugins.tff_backend.bizz.service import get_main_branding_hash, add_user_to_role
from plugins.tff_backend.bizz.todo import update_hoster_progress
from plugins.tff_backend.bizz.todo.hoster import HosterSteps
from plugins.tff_backend.configuration import TffConfiguration
from plugins.tff_backend.consts.hoster import REQUIRED_TOKEN_COUNT_TO_HOST
from plugins.tff_backend.dal.node_orders import get_node_order
from plugins.tff_backend.models.hoster import NodeOrder, PublicKeyMapping, NodeOrderStatus, ContactInfo
from plugins.tff_backend.models.investor import InvestmentAgreement
from plugins.tff_backend.plugin_consts import KEY_NAME, KEY_ALGORITHM, NAMESPACE
from plugins.tff_backend.to.iyo.see import IYOSeeDocumentView, IYOSeeDocumenVersion
from plugins.tff_backend.to.nodes import NodeOrderTO, NodeOrderDetailsTO
from plugins.tff_backend.utils import get_step_value, get_step
from plugins.tff_backend.utils.app import create_app_user_by_email, get_app_user_tuple


@returns()
@arguments(message_flow_run_id=unicode, member=unicode, steps=[object_factory("step_type", FLOW_STEP_MAPPING)],
           end_id=unicode, end_message_flow_id=unicode, parent_message_key=unicode, tag=unicode, result_key=unicode,
           flush_id=unicode, flush_message_flow_id=unicode, service_identity=unicode, user_details=[UserDetailsTO],
           flow_params=unicode)
def order_node(message_flow_run_id, member, steps, end_id, end_message_flow_id, parent_message_key, tag, result_key,
               flush_id, flush_message_flow_id, service_identity, user_details, flow_params):
    order_key = NodeOrder.create_key()
    deferred.defer(_order_node, order_key, user_details[0].email, user_details[0].app_id, steps)


def _order_node(order_key, user_email, app_id, steps):
    logging.info('Receiving order of Zero-Node')
    app_user = create_app_user_by_email(user_email, app_id)

    overview_step = get_step(steps, 'message_overview')
    if overview_step and overview_step.answer_id == u"button_use":
        api_key = get_rogerthat_api_key()
        user_data_keys = ['name', 'email', 'phone', 'billing_address', 'address', 'shipping_name', 'shipping_email',
                          'shipping_phone', 'shipping_address']
        user_data = system.get_user_data(api_key, user_email, app_id, user_data_keys)
        billing_info = ContactInfo(name=user_data['name'],
                                   email=user_data['email'],
                                   phone=user_data['phone'],
                                   address=user_data['billing_address'] or user_data['address'])

        if user_data['shipping_name']:
            shipping_info = ContactInfo(name=user_data['shipping_name'],
                                        email=user_data['shipping_email'],
                                        phone=user_data['shipping_phone'],
                                        address=user_data['shipping_address'])
        else:
            shipping_info = billing_info

        updated_user_data = None
    else:
        name = get_step_value(steps, 'message_name')
        email = get_step_value(steps, 'message_email')
        phone = get_step_value(steps, 'message_phone')
        billing_address = get_step_value(steps, 'message_billing_address')
        updated_user_data = {
            'name': name,
            'email': email,
            'phone': phone,
            'billing_address': billing_address,
        }

        billing_info = ContactInfo(name=name,
                                   email=email,
                                   phone=phone,
                                   address=billing_address)

        same_shipping_info_step = get_step(steps, 'message_choose_shipping_info')
        if same_shipping_info_step and same_shipping_info_step.answer_id == u"button_yes":
            shipping_info = billing_info
        else:
            shipping_name = get_step_value(steps, 'message_shipping_name')
            shipping_email = get_step_value(steps, 'message_shipping_email')
            shipping_phone = get_step_value(steps, 'message_shipping_phone')
            shipping_address = get_step_value(steps, 'message_shipping_address')
            updated_user_data.update({
                'shipping_name': shipping_name,
                'shipping_email': shipping_email,
                'shipping_phone': shipping_phone,
                'shipping_address': shipping_address,
            })

            shipping_info = ContactInfo(name=shipping_name,
                                        email=shipping_email,
                                        phone=shipping_phone,
                                        address=shipping_address)
    socket_step = get_step(steps, 'message_socket')
    socket = socket_step and socket_step.answer_id.replace('button_', '')
    # Check if user has invested >= 120 tokens
    paid_orders = InvestmentAgreement.list_by_status_and_user(app_user, InvestmentAgreement.STATUS_PAID)
    total_tokens = sum([o.token_count_float for o in paid_orders])
    can_host = total_tokens >= REQUIRED_TOKEN_COUNT_TO_HOST
    if can_host:
        # Check if user has no previous node order. If so, send message stating that.
        active_orders = [o for o in NodeOrder.list_by_user(app_user) if o.status != NodeOrderStatus.CANCELED]
        can_host = len(active_orders) == 0
        if not can_host:
            logging.info('User already has a node order, sending abort message')
            msg = u'Dear ThreeFold Member, we sadly cannot grant your request to host an additional ThreeFold Node:' \
                  u' We are currently only allowing one Node to be hosted per ThreeFold Member and location.' \
                  u' This will allow us to build a bigger base and a more diverse Grid.'
            subject = u'Your ThreeFold Node request'
            send_message_and_email(app_user, msg, subject)
            return

    def trans():
        logging.debug('Storing order in the database')
        order = NodeOrder(key=order_key,
                          app_user=app_user,
                          tos_iyo_see_id=None,
                          billing_info=billing_info,
                          shipping_info=shipping_info,
                          order_time=now(),
                          status=NodeOrderStatus.APPROVED if can_host else NodeOrderStatus.WAITING_APPROVAL,
                          socket=socket)
        order.put()
        if can_host:
            logging.info('User has invested more than %s tokens, immediately creating node order PDF.',
                         REQUIRED_TOKEN_COUNT_TO_HOST)
            deferred.defer(_create_node_order_pdf, order_key.id(), _transactional=True)
        else:
            logging.info('User has not invested more than %s tokens, an admin needs to approve this order manually.',
                         REQUIRED_TOKEN_COUNT_TO_HOST)
            deferred.defer(_inform_support_of_new_node_order, order_key.id(), _transactional=True)
        if updated_user_data:
            deferred.defer(put_user_data, app_user, updated_user_data, _transactional=True)

    ndb.transaction(trans)


def _create_node_order_pdf(node_order_id):
    node_order = get_node_order(node_order_id)
    user_email, app_id = get_app_user_tuple(node_order.app_user)
    logging.debug('Creating Hosting agreement')
    pdf_name = NodeOrder.filename(node_order_id)
    pdf_contents = create_hosting_agreement_pdf(node_order.billing_info.name, node_order.billing_info.address)
    pdf_url = upload_to_gcs(pdf_name, pdf_contents, 'application/pdf')
    deferred.defer(_order_node_iyo_see, node_order.app_user, node_order_id, pdf_url)
    deferred.defer(update_hoster_progress, user_email.email(), app_id, HosterSteps.FLOW_ADDRESS)


def _order_node_iyo_see(app_user, node_order_id, pdf_url):
    iyo_username = get_iyo_username(app_user)
    organization_id = get_iyo_organization_id()

    iyo_see_doc = IYOSeeDocumentView(username=iyo_username,
                                     globalid=organization_id,
                                     uniqueid=u'Zero-Node order %s' % NodeOrder.create_human_readable_id(node_order_id),
                                     version=1,
                                     category=u'Terms and conditions',
                                     link=pdf_url,
                                     content_type=u'application/pdf',
                                     markdown_short_description=u'Terms and conditions for ordering a Zero-Node',
                                     markdown_full_description=u'Terms and conditions for ordering a Zero-Node')
    logging.debug('Creating IYO SEE document: %s', iyo_see_doc)
    iyo_see_doc = create_see_document(iyo_username, iyo_see_doc)

    attachment_name = u' - '.join([iyo_see_doc.uniqueid, iyo_see_doc.category])

    def trans():
        order = get_node_order(node_order_id)
        order.tos_iyo_see_id = iyo_see_doc.uniqueid
        order.put()
        deferred.defer(_create_quotation, app_user, node_order_id, pdf_url, attachment_name,
                       _transactional=True)

    ndb.transaction(trans)


@returns()
@arguments(app_user=users.User, order_id=(int, long), pdf_url=unicode, attachment_name=unicode)
def _create_quotation(app_user, order_id, pdf_url, attachment_name):
    order = get_node_order(order_id)
    config = get_config(NAMESPACE)
    assert isinstance(config, TffConfiguration)
    product_id = config.odoo.product_ids.get(order.socket)
    if not product_id:
        logging.warn('Could not find appropriate product for socket %s. Falling back to EU socket.', order.socket)
        product_id = config.odoo.product_ids['EU']
    odoo_sale_order_id, odoo_sale_order_name = create_odoo_quotation(order.billing_info, order.shipping_info,
                                                                     product_id)

    order.odoo_sale_order_id = odoo_sale_order_id
    order.put()

    deferred.defer(_send_order_node_sign_message, app_user, order_id, pdf_url, attachment_name,
                   odoo_sale_order_name)


@returns()
@arguments(order_id=(int, long))
def _cancel_quotation(order_id):
    def trans():
        node_order = get_node_order(order_id)
        if node_order.odoo_sale_order_id:
            update_odoo_quotation(node_order.odoo_sale_order_id, {'state': QuotationState.CANCEL})

        node_order.populate(status=NodeOrderStatus.CANCELED, cancel_time=now())
        node_order.put()

    ndb.transaction(trans)


@returns()
@arguments(app_user=users.User, order_id=(int, long), pdf_url=unicode, attachment_name=unicode, order_name=unicode)
def _send_order_node_sign_message(app_user, order_id, pdf_url, attachment_name, order_name):
    logging.debug('Sending SIGN widget to app user')
    widget = SignTO()
    widget.algorithm = KEY_ALGORITHM
    widget.caption = u'Please enter your PIN code to digitally sign the terms and conditions'
    widget.key_name = KEY_NAME
    widget.payload = base64.b64encode(pdf_url).decode('utf-8')

    form = SignFormTO()
    form.negative_button = u'Abort'
    form.negative_button_ui_flags = 0
    form.positive_button = u'Accept'
    form.positive_button_ui_flags = Message.UI_FLAG_EXPECT_NEXT_WAIT_5
    form.type = SignTO.TYPE
    form.widget = widget

    attachment = AttachmentTO()
    attachment.content_type = u'application/pdf'
    attachment.download_url = pdf_url
    attachment.name = attachment_name
    message = u"""Order %(order_name)s Received

You have now been approved for hosting duties!
We will keep you updated of the Node shipping process through the app.

Please review the terms and conditions and press the "Sign" button to accept.
""" % {"order_name": order_name}

    member_user, app_id = get_app_user_tuple(app_user)
    messaging.send_form(api_key=get_rogerthat_api_key(),
                        parent_message_key=None,
                        member=member_user.email(),
                        message=message,
                        form=form,
                        flags=0,
                        alert_flags=Message.ALERT_FLAG_VIBRATE,
                        branding=get_main_branding_hash(),
                        tag=json.dumps({u'__rt__.tag': u'sign_order_node_tos',
                                        u'order_id': order_id}).decode('utf-8'),
                        attachments=[attachment],
                        app_id=app_id,
                        step_id=u'sign_order_node_tos')


@returns(FormAcknowledgedCallbackResultTO)
@arguments(status=int, form_result=FormResultTO, answer_id=unicode, member=unicode, message_key=unicode, tag=unicode,
           received_timestamp=int, acked_timestamp=int, parent_message_key=unicode, result_key=unicode,
           service_identity=unicode, user_details=[UserDetailsTO])
def order_node_signed(status, form_result, answer_id, member, message_key, tag, received_timestamp, acked_timestamp,
                      parent_message_key, result_key, service_identity, user_details):
    """
    Args:
        status (int)
        form_result (FormResultTO)
        answer_id (unicode)
        member (unicode)
        message_key (unicode)
        tag (unicode)
        received_timestamp (int)
        acked_timestamp (int)
        parent_message_key (unicode)
        result_key (unicode)
        service_identity (unicode)
        user_details(list[UserDetailsTO])

    Returns:
        FormAcknowledgedCallbackResultTO
    """
    try:
        user_detail = user_details[0]
        tag_dict = json.loads(tag)
        order = get_node_order(tag_dict['order_id'])

        if answer_id != FormTO.POSITIVE:
            logging.info('Zero-Node order was canceled')
            deferred.defer(_cancel_quotation, order.id)
            return None

        logging.info('Received signature for Zero-Node order')

        sign_result = form_result.result.get_value()
        assert isinstance(sign_result, SignWidgetResultTO)
        payload_signature = sign_result.payload_signature

        iyo_organization_id = get_iyo_organization_id()
        iyo_username = get_iyo_username(user_detail)

        logging.debug('Getting IYO SEE document %s', order.tos_iyo_see_id)
        doc = get_see_document(iyo_organization_id, iyo_username, order.tos_iyo_see_id)
        doc_view = IYOSeeDocumentView(username=doc.username,
                                      globalid=doc.globalid,
                                      uniqueid=doc.uniqueid,
                                      **serialize_complex_value(doc.versions[-1], IYOSeeDocumenVersion, False))
        doc_view.signature = payload_signature
        keystore_label = get_publickey_label(sign_result.public_key.public_key, user_detail)
        if not keystore_label:
            return _create_error_message(FormAcknowledgedCallbackResultTO())
        doc_view.keystore_label = keystore_label
        logging.debug('Signing IYO SEE document')
        sign_see_document(iyo_organization_id, iyo_username, doc_view)

        logging.debug('Storing signature in DB')
        order.populate(status=NodeOrderStatus.SIGNED,
                       signature=payload_signature,
                       sign_time=now())
        order.put()

        # TODO: send mail to TF support
        deferred.defer(add_user_to_role, user_detail, Roles.HOSTERS)
        deferred.defer(update_hoster_progress, user_detail.email, user_detail.app_id, HosterSteps.FLOW_SIGN)
        intercom_tags = get_intercom_tags_for_node_order(order)
        for intercom_tag in intercom_tags:
            deferred.defer(tag_intercom_users, intercom_tag, [iyo_username])

        logging.debug('Sending confirmation message')
        message = MessageCallbackResultTypeTO()
        message.alert_flags = Message.ALERT_FLAG_VIBRATE
        message.answers = []
        message.branding = get_main_branding_hash()
        message.dismiss_button_ui_flags = 0
        message.flags = Message.FLAG_ALLOW_DISMISS | Message.FLAG_AUTO_LOCK
        message.message = u'Thank you. We successfully received your digital signature.' \
                          u' We have stored a copy of this agreement in your ThreeFold Documents.\n\n' \
                          u'Your order with ID "%s" has been placed successfully.\n' % order.human_readable_id
        message.step_id = u'order_completed'
        message.tag = None

        result = FormAcknowledgedCallbackResultTO()
        result.type = TYPE_MESSAGE
        result.value = message
        return result
    except:
        logging.exception('An unexpected error occurred')
        return _create_error_message(FormAcknowledgedCallbackResultTO())


def get_publickey_label(public_key, user_details):
    # type: (unicode, UserDetailsTO) -> unicode
    mapping = PublicKeyMapping.create_key(public_key, user_details.email).get()
    if mapping:
        return mapping.label
    else:
        logging.error('No PublicKeyMapping found! falling back to doing a request to itsyou.online')
        iyo_keys = get_keystore(get_iyo_username(user_details))
        results = filter(lambda k: public_key in k.key, iyo_keys)  # some stuff is prepended to the key
        if len(results):
            return results[0].label
        else:
            logging.error('Could not find label for public key %s on itsyou.online', public_key)
            return None


@returns(NodeOrderDetailsTO)
@arguments(order_id=(int, long))
def get_node_order_details(order_id):
    # type: (long) -> NodeOrderDetailsTO
    node_order = get_node_order(order_id)
    if node_order.tos_iyo_see_id:
        iyo_organization_id = get_iyo_organization_id()
        username = get_iyo_username(node_order.app_user)
        see_document = get_see_document(iyo_organization_id, username, node_order.tos_iyo_see_id)
    else:
        see_document = None
    return NodeOrderDetailsTO.from_model(node_order, see_document)


def _get_allowed_status(current_status):
    # type: (long, long) -> list[long]
    next_statuses = {
        NodeOrderStatus.CANCELED: [],
        NodeOrderStatus.WAITING_APPROVAL: [NodeOrderStatus.CANCELED, NodeOrderStatus.APPROVED],
        NodeOrderStatus.APPROVED: [NodeOrderStatus.CANCELED, NodeOrderStatus.SIGNED],
        NodeOrderStatus.SIGNED: [NodeOrderStatus.CANCELED, NodeOrderStatus.PAID],
        NodeOrderStatus.PAID: [NodeOrderStatus.SENT],
        NodeOrderStatus.SENT: [],
        NodeOrderStatus.ARRIVED: [],
    }
    return next_statuses.get(current_status)


def _can_change_status(current_status, new_status):
    # type: (long, long) -> bool
    return new_status in _get_allowed_status(current_status)


@returns(NodeOrder)
@arguments(order_id=(int, long), order=NodeOrderTO)
def put_node_order(order_id, order):
    # type: (long, NodeOrderTO) -> NodeOrder
    order_model = get_node_order(order_id)
    if order_model.status == NodeOrderStatus.CANCELED:
        raise HttpBadRequestException('order_canceled')
    if order.status not in (NodeOrderStatus.CANCELED, NodeOrderStatus.SENT, NodeOrderStatus.APPROVED,
                            NodeOrderStatus.PAID):
        raise HttpBadRequestException('invalid_status')
    # Only support updating the status for now
    if order_model.status != order.status:
        if not _can_change_status(order_model.status, order.status):
            raise HttpBadRequestException('cannot_change_status',
                                          {'from': order_model.status, 'to': order.status,
                                           'allowed_new_statuses': _get_allowed_status(order_model.status)})
        order_model.status = order.status
        human_user, app_id = get_app_user_tuple(order_model.app_user)
        if order_model.status == NodeOrderStatus.CANCELED:
            order_model.cancel_time = now()
            if order_model.odoo_sale_order_id:
                deferred.defer(update_odoo_quotation, order_model.odoo_sale_order_id, {'state': QuotationState.CANCEL})
            deferred.defer(update_hoster_progress, human_user.email(), app_id,
                           HosterSteps.NODE_POWERED)  # nuke todo list
        elif order_model.status == NodeOrderStatus.SENT:
            if not order_model.odoo_sale_order_id or not get_odoo_serial_number(order_model.odoo_sale_order_id):
                raise HttpBadRequestException('no_serial_number_configured_yet',
                                              {'sale_order': order_model.odoo_sale_order_id})
            order_model.send_time = now()
            deferred.defer(update_hoster_progress, human_user.email(), app_id, HosterSteps.NODE_SENT)
            deferred.defer(_send_node_order_sent_message, order_id)
        elif order_model.status == NodeOrderStatus.APPROVED:
            deferred.defer(_create_node_order_pdf, order_id)
        elif order_model.status == NodeOrderStatus.PAID:
            deferred.defer(confirm_odoo_quotation, order_model.odoo_sale_order_id)
    else:
        logging.debug('Status was already %s, not doing anything', order_model.status)

    order_model.put()
    return order_model


def _create_error_message(callback_result):
    logging.debug('Sending error message')
    message = MessageCallbackResultTypeTO()
    message.alert_flags = Message.ALERT_FLAG_VIBRATE
    message.answers = []
    message.branding = get_main_branding_hash()
    message.dismiss_button_ui_flags = 0
    message.flags = Message.FLAG_ALLOW_DISMISS | Message.FLAG_AUTO_LOCK
    message.message = u'Oh no! An error occurred.\nHow embarrassing :-(\n\nPlease try again later.'
    message.step_id = u'error'
    message.tag = None

    callback_result.type = TYPE_MESSAGE
    callback_result.value = message
    return callback_result


def _inform_support_of_new_node_order(node_order_id):
    node_order = get_node_order(node_order_id)
    cfg = get_config(NAMESPACE)
    iyo_username = get_iyo_username(node_order.app_user)

    subject = 'New Node Order by %s' % node_order.billing_info.name
    body = """Hello,

We just received a new Node order from %(name)s (IYO username %(iyo_username)s) with id %(node_order_id)s.
This order needs to be manually approved since this user has not invested more than %(tokens)s tokens yet via the app.
Check the old purchase agreements to verify if this user can sign up as a hoster and if not, contact him.

Please visit https://tff-backend.appspot.com/orders/%(node_order_id)s to approve or cancel this order.
""" % {
        'name': node_order.billing_info.name,
        'iyo_username': iyo_username,
        'node_order_id': node_order.id,
        'tokens': REQUIRED_TOKEN_COUNT_TO_HOST
    }

    for email in cfg.investor.support_emails:
        mail.send_mail(sender='no-reply@tff-backend.appspotmail.com',
                       to=email,
                       subject=subject,
                       body=body)


def _send_node_order_sent_message(node_order_id):
    node_order = get_node_order(node_order_id)
    subject = u'ThreeFold node ready to ship out'
    msg = u'Good news, your ThreeFold node (order id %s) has been prepared for shipment.' \
          u' It will be handed over to our shipping partner soon.' \
          u'\nThanks again for accepting hosting duties and helping to grow the ThreeFold Grid close to the users.' % \
          node_order_id
    send_message_and_email(node_order.app_user, msg, subject)


def get_intercom_tags_for_node_order(order):
    # type: (NodeOrder) -> list[IntercomTags]
    if order.status in [NodeOrderStatus.ARRIVED, NodeOrderStatus.SENT, NodeOrderStatus.SIGNED, NodeOrderStatus.PAID]:
        return [IntercomTags.HOSTER]
    return []
