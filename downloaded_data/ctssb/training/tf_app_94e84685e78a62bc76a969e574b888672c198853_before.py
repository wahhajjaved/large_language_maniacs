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
import httplib
import json
import logging
from types import NoneType

from google.appengine.api import users, mail
from google.appengine.ext import deferred, ndb, db

from babel.numbers import get_currency_name
from framework.plugin_loader import get_config
from framework.utils import now
from mcfw.exceptions import HttpNotFoundException, HttpBadRequestException
from mcfw.properties import object_factory
from mcfw.rpc import returns, arguments, serialize_complex_value
from plugins.rogerthat_api.api import messaging, system
from plugins.rogerthat_api.exceptions import BusinessException
from plugins.rogerthat_api.to import UserDetailsTO, MemberTO
from plugins.rogerthat_api.to.messaging import Message, AttachmentTO, AnswerTO
from plugins.rogerthat_api.to.messaging.flow import FLOW_STEP_MAPPING
from plugins.rogerthat_api.to.messaging.forms import SignTO, SignFormTO, FormResultTO, FormTO, SignWidgetResultTO
from plugins.rogerthat_api.to.messaging.service_callback_results import FormAcknowledgedCallbackResultTO, \
    MessageCallbackResultTypeTO, TYPE_MESSAGE, FlowMemberResultCallbackResultTO
from plugins.tff_backend.bizz import get_rogerthat_api_key
from plugins.tff_backend.bizz.authentication import Roles
from plugins.tff_backend.bizz.global_stats import get_global_stats
from plugins.tff_backend.bizz.hoster import get_publickey_label, _create_error_message
from plugins.tff_backend.bizz.ipfs import store_pdf
from plugins.tff_backend.bizz.iyo.see import create_see_document, get_see_document, sign_see_document
from plugins.tff_backend.bizz.iyo.user import get_user
from plugins.tff_backend.bizz.iyo.utils import get_iyo_username, get_iyo_organization_id
from plugins.tff_backend.bizz.payment import transfer_genesis_coins_to_user
from plugins.tff_backend.bizz.service import get_main_branding_hash, add_user_to_role
from plugins.tff_backend.bizz.todo import update_investor_progress
from plugins.tff_backend.bizz.todo.investor import InvestorSteps
from plugins.tff_backend.consts.agreements import BANK_ACCOUNTS, ACCOUNT_NUMBERS
from plugins.tff_backend.consts.payment import TOKEN_TFT, TOKEN_ITFT, TOKEN_TYPE_I
from plugins.tff_backend.models.global_stats import GlobalStats, CurrencyValue
from plugins.tff_backend.models.investor import InvestmentAgreement
from plugins.tff_backend.plugin_consts import KEY_ALGORITHM, KEY_NAME, NAMESPACE, \
    SUPPORTED_CRYPTO_CURRENCIES, CRYPTO_CURRENCY_NAMES, BUY_TOKENS_TAG, BUY_TOKENS_FLOW_V3
from plugins.tff_backend.to.investor import InvestmentAgreementTO, InvestmentAgreementDetailsTO
from plugins.tff_backend.to.iyo.see import IYOSeeDocumentView, IYOSeeDocumenVersion
from plugins.tff_backend.utils import get_step_value, get_step, round_currency_amount
from plugins.tff_backend.utils.app import create_app_user_by_email, get_app_user_tuple
from requests.exceptions import HTTPError


@returns(FlowMemberResultCallbackResultTO)
@arguments(message_flow_run_id=unicode, member=unicode, steps=[object_factory("step_type", FLOW_STEP_MAPPING)],
           end_id=unicode, end_message_flow_id=unicode, parent_message_key=unicode, tag=unicode, result_key=unicode,
           flush_id=unicode, flush_message_flow_id=unicode, service_identity=unicode, user_details=[UserDetailsTO],
           flow_params=unicode)
def invest_tft(message_flow_run_id, member, steps, end_id, end_message_flow_id, parent_message_key, tag, result_key,
               flush_id, flush_message_flow_id, service_identity, user_details, flow_params):
    return invest(message_flow_run_id, member, steps, end_id, end_message_flow_id, parent_message_key, tag, result_key,
                  flush_id, flush_message_flow_id, service_identity, user_details, flow_params, TOKEN_TFT)


@returns(FlowMemberResultCallbackResultTO)
@arguments(message_flow_run_id=unicode, member=unicode, steps=[object_factory("step_type", FLOW_STEP_MAPPING)],
           end_id=unicode, end_message_flow_id=unicode, parent_message_key=unicode, tag=unicode, result_key=unicode,
           flush_id=unicode, flush_message_flow_id=unicode, service_identity=unicode, user_details=[UserDetailsTO],
           flow_params=unicode)
def invest_itft(message_flow_run_id, member, steps, end_id, end_message_flow_id, parent_message_key, tag, result_key,
                flush_id, flush_message_flow_id, service_identity, user_details, flow_params):
    return invest(message_flow_run_id, member, steps, end_id, end_message_flow_id, parent_message_key, tag, result_key,
                  flush_id, flush_message_flow_id, service_identity, user_details, flow_params, TOKEN_ITFT)


@returns(FlowMemberResultCallbackResultTO)
@arguments(message_flow_run_id=unicode, member=unicode, steps=[object_factory("step_type", FLOW_STEP_MAPPING)],
           end_id=unicode, end_message_flow_id=unicode, parent_message_key=unicode, tag=unicode, result_key=unicode,
           flush_id=unicode, flush_message_flow_id=unicode, service_identity=unicode, user_details=[UserDetailsTO],
           flow_params=unicode, token=unicode)
def invest(message_flow_run_id, member, steps, end_id, end_message_flow_id, parent_message_key, tag, result_key,
           flush_id, flush_message_flow_id, service_identity, user_details, flow_params, token):
    try:
        email = user_details[0].email
        app_id = user_details[0].app_id
        app_user = create_app_user_by_email(email, app_id)
        logging.info('User %s wants to invest', email)
        try:
            version = db.Key(steps[0].message_flow_id).name()
        except db.BadKeyError:
            version = steps[0].message_flow_id
        currency = get_step_value(steps, 'message_get_currency').replace('_cur', '')
        if version == BUY_TOKENS_FLOW_V3:
            amount = float(get_step_value(steps, 'message_get_order_size_ITO').replace(',', '.'))
            token_count_float = get_token_count(currency, amount)
        else:
            token_count_float = float(get_step_value(steps, 'message_get_order_size_ITO'))
            amount = get_investment_amount(currency, token_count_float)

        overview_step = get_step(steps, 'message_overview')
        if overview_step and overview_step.answer_id == u"button_use":
            api_key = get_rogerthat_api_key()
            user_data_keys = ['name', 'billing_address', 'address']
            current_user_data = system.get_user_data(api_key, email, app_id, user_data_keys)
            name = current_user_data['name']
            billing_address = current_user_data['billing_address'] or current_user_data['address']
        else:
            name = get_step_value(steps, 'message_name')
            billing_address = get_step_value(steps, 'message_billing_address')
        precision = 2
        agreement = InvestmentAgreement(creation_time=now(),
                                        app_user=app_user,
                                        token=token,
                                        amount=amount,
                                        token_count=long(token_count_float * pow(10, precision)),
                                        token_precision=precision,
                                        currency=currency,
                                        name=name,
                                        address=billing_address,
                                        status=InvestmentAgreement.STATUS_CREATED,
                                        version=version)
        agreement.put()
        answer_yes = AnswerTO(type=u'button', action=None, id=u'confirm', caption=u'Confirm', ui_flags=0, color=None)
        answer_no = AnswerTO(type=u'button', action=None, id=u'cancel', caption=u'Cancel', ui_flags=0, color=None)
        answers = [answer_yes, answer_no]

        params = {
            'token': token,
            'amount': amount,
            'currency': currency
        }
        msg = u'We are ready to process your purchase. Is the following information correct?\n\n' \
              u'You would like to buy %(token)s for a total amount of' \
              u' **%(amount)s %(currency)s**.\n\n' \
              u'After confirming, you will receive your personalised investment agreement.' % params
        tag = json.dumps({'__rt__.tag': 'invest_complete', 'investment_id': agreement.id}).decode('utf-8')
        message = MessageCallbackResultTypeTO(alert_flags=Message.ALERT_FLAG_SILENT,
                                              answers=answers,
                                              branding=get_main_branding_hash(),
                                              dismiss_button_ui_flags=0,
                                              flags=Message.FLAG_AUTO_LOCK,
                                              step_id=u'confirm_investment',
                                              message=msg,
                                              tag=tag)

        result = FlowMemberResultCallbackResultTO(type=TYPE_MESSAGE)
        result.value = message
        return result
    except Exception as e:
        logging.exception(e)
        return _create_error_message(FlowMemberResultCallbackResultTO())


def get_currency_rate(currency):
    global_stats = GlobalStats.create_key(TOKEN_TFT).get()  # type: GlobalStats
    if currency == 'USD':
        return global_stats.value
    currency_stats = filter(lambda c: c.currency == currency, global_stats.currencies)  # type: list[CurrencyValue]
    if not currency_stats:
        raise BusinessException('No stats are set for currency %s', currency)
    return currency_stats[0].value


def get_investment_amount(currency, token_count):
    # type: (unicode, float) -> float
    return round_currency_amount(currency, get_currency_rate(currency) * token_count)


def get_token_count(currency, amount):
    # type: (unicode, float) -> float
    return amount / get_currency_rate(currency)


@returns()
@arguments(email=unicode, tag=unicode, result_key=unicode, context=unicode, service_identity=unicode,
           user_details=UserDetailsTO)
def start_invest(email, tag, result_key, context, service_identity, user_details):
    # type: (unicode, unicode, unicode, unicode, unicode, UserDetailsTO) -> None
    logging.info('Starting invest flow for user %s', user_details.email)
    members = [MemberTO(member=user_details.email, app_id=user_details.app_id, alert_flags=0)]
    flow_params = json.dumps({'currencies': _get_conversion_rates()})
    messaging.start_local_flow(get_rogerthat_api_key(), None, members, service_identity, tag=BUY_TOKENS_TAG,
                               context=context, flow=BUY_TOKENS_FLOW_V3, flow_params=flow_params)


def _get_conversion_rates():
    result = []
    stats = get_global_stats(TOKEN_ITFT)
    for currency in stats.currencies:
        result.append({
            'name': _get_currency_name(currency.currency),
            'symbol': currency.currency,
            'value': currency.value
        })
    return result


@returns()
@arguments(status=int, answer_id=unicode, received_timestamp=int, member=unicode, message_key=unicode, tag=unicode,
           acked_timestamp=int, parent_message_key=unicode, service_identity=unicode, user_details=[UserDetailsTO])
def invest_complete(status, answer_id, received_timestamp, member, message_key, tag, acked_timestamp,
                    parent_message_key, service_identity, user_details):
    email = user_details[0].email
    app_id = user_details[0].app_id
    if answer_id == u'confirm':
        agreement_key = InvestmentAgreement.create_key(json.loads(tag)['investment_id'])
        deferred.defer(_invest, agreement_key, email, app_id, 0)


def _get_currency_name(currency):
    if currency in SUPPORTED_CRYPTO_CURRENCIES:
        return CRYPTO_CURRENCY_NAMES[currency]
    return get_currency_name(currency, locale='en_GB')


def _set_token_count(agreement, token_count_float=None, precision=2):
    # type: (InvestmentAgreement) -> None
    stats = get_global_stats(agreement.token)
    logging.info('Setting token count for agreement %s', agreement.to_dict())
    if agreement.status == InvestmentAgreement.STATUS_CREATED:
        if agreement.currency == 'USD':
            agreement.token_count = long((agreement.amount / stats.value) * pow(10, precision))
        else:
            currency_stats = filter(lambda s: s.currency == agreement.currency, stats.currencies)[0]
            if not currency_stats:
                raise HttpBadRequestException('Could not find currency conversion for currency %s', agreement.currency)
            agreement.token_count = long((agreement.amount / currency_stats.value) * pow(10, precision))
    # token_count can be overwritten when marking the investment as paid for BTC
    elif agreement.status == InvestmentAgreement.STATUS_SIGNED:
        if agreement.currency == 'BTC':
            if not token_count_float:
                raise HttpBadRequestException('token_count_float must be provided when setting token count for BTC')
            # The course of BTC changes how much tokens are granted
            if agreement.token_count:
                logging.debug('Overwriting token_count for investment agreement %s from %s to %s',
                              agreement.id, agreement.token_count, token_count_float)
            agreement.token_count = long(token_count_float * pow(10, precision))
    agreement.token_precision = precision


def _invest(agreement_key, email, app_id, retry_count):
    # type: (ndb.Key, unicode, unicode, long) -> None
    from plugins.tff_backend.bizz.agreements import create_token_agreement_pdf
    app_user = create_app_user_by_email(email, app_id)
    logging.debug('Creating Token agreement')
    agreement = get_investment_agreement(agreement_key.id())
    _set_token_count(agreement)
    agreement.put()
    currency_full = _get_currency_name(agreement.currency)
    pdf_name = 'token_%s.pdf' % agreement_key.id()
    pdf_contents = create_token_agreement_pdf(agreement.name, agreement.address, agreement.amount, currency_full,
                                              agreement.currency, agreement.token)
    ipfs_link = store_pdf(pdf_name, pdf_contents)
    if not ipfs_link:
        logging.error('Failed to create IPFS document with name %s and retry_count %s', pdf_name, retry_count)
        deferred.defer(_invest, agreement_key, email, app_id, retry_count + 1, _countdown=retry_count)
        return

    logging.debug('Storing Investment Agreement in the datastore')

    deferred.defer(_create_investment_agreement_iyo_see_doc, agreement_key, app_user, ipfs_link)
    deferred.defer(update_investor_progress, email, app_id, InvestorSteps.FLOW_AMOUNT)


def _create_investment_agreement_iyo_see_doc(agreement_key, app_user, ipfs_link):
    # type: (ndb.Key, users.User, unicode) -> None
    iyo_username = get_iyo_username(app_user)
    organization_id = get_iyo_organization_id()

    doc_id = u'Internal Token Offering %s' % agreement_key.id()
    doc_category = u'Investment Agreement'
    iyo_see_doc = IYOSeeDocumentView(username=iyo_username,
                                     globalid=organization_id,
                                     uniqueid=doc_id,
                                     version=1,
                                     category=doc_category,
                                     link=ipfs_link,
                                     content_type=u'application/pdf',
                                     markdown_short_description=u'Internal Token Offering - Investment Agreement',
                                     markdown_full_description=u'Internal Token Offering - Investment Agreement')
    logging.debug('Creating IYO SEE document: %s', iyo_see_doc)
    try:
        create_see_document(iyo_username, iyo_see_doc)
    except HTTPError as e:
        if e.response.status_code != httplib.CONFLICT:
            raise e

    attachment_name = u' - '.join([doc_id, doc_category])

    def trans():
        agreement = agreement_key.get()
        agreement.iyo_see_id = doc_id
        agreement.put()
        deferred.defer(_send_ito_agreement_sign_message, agreement.key, app_user, ipfs_link, attachment_name,
                       _transactional=True)

    ndb.transaction(trans)


def _send_ito_agreement_sign_message(agreement_key, app_user, ipfs_link, attachment_name):
    logging.debug('Sending SIGN widget to app user')
    widget = SignTO()
    widget.algorithm = KEY_ALGORITHM
    widget.caption = u'Please enter your PIN code to digitally sign the investment agreement'
    widget.key_name = KEY_NAME
    widget.payload = base64.b64encode(ipfs_link).decode('utf-8')

    form = SignFormTO()
    form.negative_button = u'Abort'
    form.negative_button_ui_flags = 0
    form.positive_button = u'Accept'
    form.positive_button_ui_flags = Message.UI_FLAG_EXPECT_NEXT_WAIT_5
    form.type = SignTO.TYPE
    form.widget = widget

    attachment = AttachmentTO()
    attachment.content_type = u'application/pdf'
    attachment.download_url = ipfs_link
    attachment.name = attachment_name

    member_user, app_id = get_app_user_tuple(app_user)
    messaging.send_form(api_key=get_rogerthat_api_key(),
                        parent_message_key=None,
                        member=member_user.email(),
                        message=u'Please review the investment agreement and press the "Sign" button to accept.',
                        form=form,
                        flags=0,
                        alert_flags=Message.ALERT_FLAG_VIBRATE,
                        branding=get_main_branding_hash(),
                        tag=json.dumps({u'__rt__.tag': u'sign_investment_agreement',
                                        u'agreement_id': agreement_key.id()}).decode('utf-8'),
                        attachments=[attachment],
                        app_id=app_id,
                        step_id=u'sign_investment_agreement')


def _send_ito_agreement_to_admin(agreement_key, admin_app_user):
    logging.debug('Sending SIGN widget to payment admin %s', admin_app_user)

    agreement = agreement_key.get()  # type: InvestmentAgreement
    widget = SignTO()
    widget.algorithm = KEY_ALGORITHM
    widget.caption = u'Sign to mark this investment as paid.'
    widget.key_name = KEY_NAME
    widget.payload = base64.b64encode(str(agreement_key.id())).decode('utf-8')

    form = SignFormTO()
    form.negative_button = u'Abort'
    form.negative_button_ui_flags = 0
    form.positive_button = u'Accept'
    form.positive_button_ui_flags = Message.UI_FLAG_EXPECT_NEXT_WAIT_5
    form.type = SignTO.TYPE
    form.widget = widget

    member_user, app_id = get_app_user_tuple(admin_app_user)
    message = u"""Enter your pin code to mark investment %(investment)s as paid.
- from: %(user)s\n
- amount: %(amount)s %(currency)s
- %(token_count_float)s %(token_type)s tokens
""" % {'investment': agreement_key.id(),
       'user': agreement.iyo_username,
       'amount': agreement.amount,
       'currency': agreement.currency,
       'token_count_float': agreement.token_count_float,
       'token_type': agreement.token}

    messaging.send_form(api_key=get_rogerthat_api_key(),
                        parent_message_key=None,
                        member=member_user.email(),
                        message=message,
                        form=form,
                        flags=0,
                        alert_flags=Message.ALERT_FLAG_VIBRATE,
                        branding=get_main_branding_hash(),
                        tag=json.dumps({u'__rt__.tag': u'sign_investment_agreement_admin',
                                        u'agreement_id': agreement_key.id()}).decode('utf-8'),
                        attachments=[],
                        app_id=app_id,
                        step_id=u'sign_investment_agreement_admin')


@returns(FormAcknowledgedCallbackResultTO)
@arguments(status=int, form_result=FormResultTO, answer_id=unicode, member=unicode, message_key=unicode, tag=unicode,
           received_timestamp=int, acked_timestamp=int, parent_message_key=unicode, result_key=unicode,
           service_identity=unicode, user_details=[UserDetailsTO])
def investment_agreement_signed(status, form_result, answer_id, member, message_key, tag, received_timestamp,
                                acked_timestamp, parent_message_key, result_key, service_identity, user_details):
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
        agreement = InvestmentAgreement.create_key(tag_dict['agreement_id']).get()  # type: InvestmentAgreement

        if answer_id != FormTO.POSITIVE:
            logging.info('Investment agreement was canceled')
            agreement.status = InvestmentAgreement.STATUS_CANCELED
            agreement.cancel_time = now()
            agreement.put()
            return None

        logging.info('Received signature for Investment Agreement')

        sign_result = form_result.result.get_value()
        assert isinstance(sign_result, SignWidgetResultTO)
        payload_signature = sign_result.payload_signature

        iyo_organization_id = get_iyo_organization_id()
        iyo_username = get_iyo_username(user_detail)

        logging.debug('Getting IYO SEE document %s', agreement.iyo_see_id)
        doc = get_see_document(iyo_organization_id, iyo_username, agreement.iyo_see_id)
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
        agreement.populate(status=InvestmentAgreement.STATUS_SIGNED,
                           signature=payload_signature,
                           sign_time=now())
        agreement.put()

        # TODO: send mail to TF support
        deferred.defer(add_user_to_role, user_detail, Roles.INVESTOR)
        deferred.defer(update_investor_progress, user_detail.email, user_detail.app_id, InvestorSteps.PAY)
        deferred.defer(send_payment_instructions, user_detail.email, user_detail.app_id, agreement.id)

        deferred.defer(_inform_support_of_new_investment, agreement.iyo_username, agreement.id,
                       agreement.token_count_float)

        logging.debug('Sending confirmation message')
        message = MessageCallbackResultTypeTO()
        message.alert_flags = Message.ALERT_FLAG_VIBRATE
        message.answers = []
        message.branding = get_main_branding_hash()
        message.dismiss_button_ui_flags = 0
        message.flags = Message.FLAG_ALLOW_DISMISS | Message.FLAG_AUTO_LOCK
        message.message = u'Thank you. We successfully received your digital signature.' \
                          u' We have stored a copy of this agreement in your ItsYou.Online SEE account.'
        message.step_id = u'investment_agreement_accepted'
        message.tag = None

        result = FormAcknowledgedCallbackResultTO()
        result.type = TYPE_MESSAGE
        result.value = message
        return result
    except:
        logging.exception('An unexpected error occurred')
        return _create_error_message(FormAcknowledgedCallbackResultTO())


@returns(NoneType)
@arguments(status=int, form_result=FormResultTO, answer_id=unicode, member=unicode, message_key=unicode, tag=unicode,
           received_timestamp=int, acked_timestamp=int, parent_message_key=unicode, result_key=unicode,
           service_identity=unicode, user_details=[UserDetailsTO])
def investment_agreement_signed_by_admin(status, form_result, answer_id, member, message_key, tag, received_timestamp,
                                         acked_timestamp, parent_message_key, result_key, service_identity,
                                         user_details):
    tag_dict = json.loads(tag)

    def trans():
        agreement = InvestmentAgreement.create_key(tag_dict['agreement_id']).get()  # type: InvestmentAgreement
        if answer_id != FormTO.POSITIVE:
            logging.info('Investment agreement sign aborted')
            return
        if agreement.status == InvestmentAgreement.STATUS_PAID:
            logging.warn('Ignoring request to set InvestmentAgreement %s as paid because it is already paid',
                         agreement.id)
            return
        agreement.status = InvestmentAgreement.STATUS_PAID
        agreement.paid_time = now()
        agreement.put()
        user_email, app_id, = get_app_user_tuple(agreement.app_user)
        deferred.defer(transfer_genesis_coins_to_user, agreement.app_user, TOKEN_TYPE_I,
                       long(agreement.token_count_float * 100), _transactional=True)
        deferred.defer(update_investor_progress, user_email.email(), app_id, InvestorSteps.ASSIGN_TOKENS,
                       _transactional=True)

    ndb.transaction(trans)


@returns(tuple)
@arguments(cursor=unicode, status=(int, long))
def get_investment_agreements(cursor=None, status=None):
    return InvestmentAgreement.fetch_page(cursor, status)


@returns(InvestmentAgreement)
@arguments(agreement_id=(int, long))
def get_investment_agreement(agreement_id):
    # type: (long) -> InvestmentAgreement
    agreement = InvestmentAgreement.get_by_id(agreement_id)
    if not agreement:
        raise HttpNotFoundException('investment_agreement_not_found')
    return agreement


@returns(InvestmentAgreementDetailsTO)
@arguments(agreement_id=(int, long))
def get_investment_agreement_details(agreement_id):
    agreement = get_investment_agreement(agreement_id)
    if agreement.iyo_see_id:
        iyo_organization_id = get_iyo_organization_id()
        username = get_iyo_username(agreement.app_user)
        see_document = get_see_document(iyo_organization_id, username, agreement.iyo_see_id)
    else:
        see_document = None
    return InvestmentAgreementDetailsTO.from_model(agreement, see_document)


@returns(InvestmentAgreement)
@arguments(agreement_id=(int, long), agreement=InvestmentAgreementTO, admin_user=users.User)
def put_investment_agreement(agreement_id, agreement, admin_user):
    admin_app_user = create_app_user_by_email(admin_user.email(), get_config(NAMESPACE).rogerthat.app_id)
    # type: (long, InvestmentAgreement, users.User) -> InvestmentAgreement
    agreement_model = InvestmentAgreement.get_by_id(agreement_id)  # type: InvestmentAgreement
    if not agreement_model:
        raise HttpNotFoundException('investment_agreement_not_found')
    if agreement_model.status == InvestmentAgreement.STATUS_CANCELED:
        raise HttpBadRequestException('order_canceled')
    if agreement.status not in (InvestmentAgreement.STATUS_SIGNED, InvestmentAgreement.STATUS_CANCELED):
        raise HttpBadRequestException('invalid_status')
    # Only support updating the status for now
    agreement_model.status = agreement.status
    if agreement_model.status == InvestmentAgreement.STATUS_CANCELED:
        agreement_model.cancel_time = now()
    elif agreement_model.status == InvestmentAgreement.STATUS_SIGNED:
        agreement_model.paid_time = now()
        if agreement.currency == 'BTC':
            _set_token_count(agreement_model, agreement.token_count_float)
        deferred.defer(_send_ito_agreement_to_admin, agreement_model.key, admin_app_user)
    agreement_model.put()
    return agreement_model


def _inform_support_of_new_investment(iyo_username, agreement_id, token_count):
    cfg = get_config(NAMESPACE)

    subject = "New investment agreement signed"
    body = """Hello,

We just received a new investment from %(iyo_username)s with id %(agreement_id)s for %(token_count_float)s tokens

Please visit https://tff-backend.appspot.com/investment-agreements to find more details, and collect all the money!
""" % {"iyo_username": iyo_username,
       "agreement_id": agreement_id,
       "token_count_float": token_count}

    for email in cfg.investor.support_emails:
        mail.send_mail(sender="no-reply@tff-backend.appspotmail.com",
                       to=email,
                       subject=subject,
                       body=body)


@returns()
@arguments(email=unicode, app_id=unicode, agreement_id=(int, long))
def send_payment_instructions(email, app_id, agreement_id):
    agreement = InvestmentAgreement.get_by_id(agreement_id)
    params = {
        'currency': agreement.currency,
        'iban': BANK_ACCOUNTS.get(agreement.currency, BANK_ACCOUNTS['USD']),
        'account_number': ACCOUNT_NUMBERS.get(agreement.currency)
    }
    if agreement.currency == "BTC":
        params['amount'] = '{:.8f}'.format(agreement.amount)
        message = u"""Please use the following transfer details
Amount: %(currency)s %(amount)s - wallet 3GTf7gWhvWqfsurxXpEj6DU7SVoLM3wC6A

Please inform us by email at payments@threefoldtoken.com when you have made payment."""

    else:
        params['amount'] = '{:.2f}'.format(agreement.amount)
        message = u"""Please use the following transfer details
Amount: %(currency)s %(amount)s

Bank: Mashreq Bank

Bank address: Al Hawai Tower, Ground Floor Sheikh Zayed Road - PO Box 36612 - UAE Dubai

Account number: %(account_number)s

IBAN: %(iban)s / BIC : BOMLAEAD

For the attention of Green IT Globe Holdings FZC, a company incorporated under the laws of Sharjah, United Arab Emirates, with registered office at SAIF Zone, SAIF Desk Q1-07-038/B

**Payment must be made from a bank account registered under your name.** Please use "FIRSTNAME LASTNAME AMOUNT iTFT" as reference."""  # noQA

    msg = message % params
    subject = u'ThreeFold payment instructions'

    deferred.defer(_send_payment_instructions_via_app, msg, email, app_id)
    deferred.defer(_send_payment_instructions_via_email, msg, subject, agreement.app_user)


def _send_payment_instructions_via_app(message, email, app_id):
    member = MemberTO(email=email, app_id=app_id, alert_flags=Message.ALERT_FLAG_VIBRATE)
    messaging.send(api_key=get_rogerthat_api_key(),
                   parent_message_key=None,
                   message=message,
                   answers=[],
                   flags=Message.FLAG_ALLOW_DISMISS,
                   members=[member],
                   branding=get_main_branding_hash(),
                   tag=None)


def _send_payment_instructions_via_email(message, subject, app_user):
    user_information = get_user(get_iyo_username(app_user))
    email = user_information.validatedemailaddresses and user_information.validatedemailaddresses[0].emailaddress
    if not email:
        logging.error('Could not find email address to send payment information to for user %s', app_user,
                      _suppress=False)
        return
    mail.send_mail(sender='no-reply@tff-backend.appspotmail.com',
                   to=email,
                   subject=subject,
                   body=message.replace('**', ''))  # remove markdown
