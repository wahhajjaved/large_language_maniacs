
import logging
log = logging.getLogger(__name__)

from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render_to_response, get_object_or_404
from django.contrib.formtools.wizard.views import SessionWizardView
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from django.core.mail import EmailMessage
from django.core.context_processors import csrf


from associates.forms import AssociateForm_de, EmergencyContactForm_de,\
        AssociateForm_en, EmergencyContactForm_en
from associates.models import Associate

from events.models import Event, EventPart, Registration, Purchase,\
    PurchaseItem

from ikedaseminar import EMAIL_TEMPLATES

from .forms import SelectPurchaseItemsForm, RegistrationMessageForm_de,\
        RegistrationMessageForm_en

from .paypal_ipn_handler import Endpoint



def registration_configuration(request, language=''):

    event = get_object_or_404(Event, pk=settings.IKEDASEMINAR_EVENT_PK)

    # POST : Forms are filled in
    if request.method == 'POST':
        sel_form = SelectPurchaseItemsForm(request.POST, event=event,
                language=language)

        if sel_form.is_valid():
            if not any(sel_form.cleaned_data.values()):
                context = {
                        'language': language,
                        'error_status':  'nothing_selected',
                        }
                return render_to_response('registration_errors.html', context)
        
        if language == 'de':
            ass_form = AssociateForm_de(request.POST)
            em_form = EmergencyContactForm_de(request.POST)
            mess_form = RegistrationMessageForm_de(request.POST)
        elif language == 'en':
            ass_form = AssociateForm_en(request.POST)
            em_form = EmergencyContactForm_en(request.POST)
            mess_form = RegistrationMessageForm_en(request.POST)
        else:
            raise ValueError('language has to be from ("de", "en")')

        if ass_form.is_valid() and em_form.is_valid() and mess_form.is_valid():
            # find Associate and fill it with latest data
            try:
                ass = Associate.objects.get(
                        email_address=ass_form.cleaned_data['email_address'],
                        date_of_birth=ass_form.cleaned_data['date_of_birth'],)
            except:
                ass = Associate()

            for fk, fv in ass_form.cleaned_data.iteritems():
                setattr(ass, fk, fv)
            for fk, fv in em_form.cleaned_data.iteritems():
                setattr(ass, fk, fv)

            if language == 'de':
                ass.language = Associate.LANGUAGE_GERMAN
            elif language == 'en':
                ass.language = Associate.LANGUAGE_ENGLISH
            ass.save()

            # find EventParts
            eps = []
            arts = []
            for fk, fv in sel_form.cleaned_data.iteritems():
                if fv:
                    if language == 'de':
                        ep = event.eventpart_set.filter(short_description_de=fk)
                        try:
                            art = event.article_set.get(name_de=fk)
                        except:
                            art = None
                    elif language == 'en':
                        ep = event.eventpart_set.filter(short_description_en=fk)
                        try:
                            art = event.article_set.get(name_de=fk)
                        except:
                            art = None
                    if ep:
                        eps.append(ep[0])
                    elif art:
                        arts.append(art)

            # check whether the package requested actuall can still be purchased
            item_not_available_anymore = False
            for ep in eps:
                if not ep.still_available():
                    item_not_available_anymore = True
            for art in arts:
                if not art.still_available():
                    item_not_available_anymore = True

            if item_not_available_anymore:
                context = {
                        'language': language,
                        'error_status':  'not_available',
                        }
                return render_to_response('registration_errors.html', context)

            # FIXME : this price calculation is not general !!!
            mapping = settings.IKEDASEMINAR_EVENTPART_SET_PRICE_MAPPING
            registration_price = int(mapping[len(eps)])
            paypal_item_id = str(len(eps))+'K'+len(arts)*'P'

            # set up the purchase
            purchase = Purchase(associate=ass)
            purchase.associate_message = mess_form.cleaned_data['message']
            purchase.save()
            purchase.payment_due_by = purchase.date_created +\
                    timedelta(settings.IKEDASEMINAR_DUE_BY_TIMEDELTA)

            if eps:
                registration = Registration(associate=ass, price=registration_price)
                registration.save()
                for ep in eps:
                    registration.event_parts.add(ep)
                registration.save()
                pi = PurchaseItem(content_object=registration,
                        purchase=purchase)
                pi.save()
            if arts:
                for art in arts:
                    pi = PurchaseItem(content_object=art, purchase=purchase)
                    pi.save()

            context = {
                    'language': language,
                    'registration_step': 2,
                    'purchase': purchase,
                    'associate': ass,
                    'eventparts': eps,
                    'articles': arts,
                    'paypal_item_id': paypal_item_id,
                    }

            return render_to_response('registration.html', context)

    
    # GET : ENTRY POINT 
    else:
        sel_form = SelectPurchaseItemsForm(event=event, language=language)
        if language == 'de':
            ass_form = AssociateForm_de()
            em_form = EmergencyContactForm_de()
            mess_form = RegistrationMessageForm_de()
        elif language == 'en':
            ass_form = AssociateForm_en()
            em_form = EmergencyContactForm_en()
            mess_form = RegistrationMessageForm_en()
        else:
            raise ValueError('language has to be from ("de", "en")')
    
    context = { 
            'language': language,
            'registration_step' : 1,
            'event': event,
            'selection_form': sel_form,
            'associate_form': ass_form,
            'emergencycontact_form': em_form,
            'message_form': mess_form, 
            }

    context.update(csrf(request))
    return render_to_response('registration.html', context) 


def registration_paypal_return(request, language=None, status=None):
    context = {
            'language': language,
            'status': status, 
            }
    return render_to_response('checkout.html', context) 


def registration_comingsoon(request, language=None):
    context = { 
            'language': language,
            'registration_step' : 0,
            }
    return render_to_response('registration.html', context) 


class PaypalIPNEndpoint(Endpoint):

    def process(self, data):
        log.info(str(data))
        pid = data['custom']
        purchase_pk = int(pid.replace('PId-', ''))

        pur_obj = Purchase.objects.get(pk=purchase_pk)
        if pur_obj.paypal_ipn_log:
            pur_obj.paypal_ipn_log += '\n\nUTC TIMESTAMP: [{now}]\n'.format(
                    now=timezone.now().strftime('%Y-%m-%d %H:%M'))
        else: 
            pur_obj.paypal_ipn_log = '\n\nUTC TIMESTAMP: [{now}]\n'.format(
                    now=timezone.now().strftime('%Y-%m-%d %H:%M'))
        pur_obj.paypal_ipn_log += str(data)
        pur_obj.save()
        
        if data['payment_status'] == 'Completed':
            pur_obj.payment_status = Purchase.PAID_BY_PAYPAL_PAYMENT_STATUS
            pur_obj.save()

            if pur_obj.associate.language == Associate.LANGUAGE_GERMAN:
                mail_body = EMAIL_TEMPLATES.REGISTRATION_EMAIL_DE.format(
                        first_name=pur_obj.associate.first_name,
                        package=pur_obj.pretty_print(language='de'),
                        associate=pur_obj.associate.pretty_print_basic(),
                        message=pur_obj.associate_message,
                        )
            else:
                mail_body = EMAIL_TEMPLATES.REGISTRATION_EMAIL_DE.format(
                        first_name=pur_obj.associate.first_name,
                        package=pur_obj.pretty_print(language='en'),
                        associate=pur_obj.associate.pretty_print_basic(),
                        message=pur_obj.associate_message,
                        )

            email = EmailMessage(
                    '[Hiroshi Ikeda Shihan Seminar Zurich 2014]',
                    mail_body,
                    'ikedaseminar@aikikai-zuerich.ch',
                    [pur_obj.associate.email_address, ],
                    ['michigraber@aikikai-zuerich.ch', ],
                    )
            email.send(fail_silently=False)

        else:
            pur_obj.payment_status = Purchase.PAYPAL_FAILED_PAYMENT_STATUS
        pur_obj.save()


    def process_invalid(self, data):
        log.info(str(data))
        pid = data['custom']
        purchase_pk = int(pid.replace('PId-', ''))

        pur_obj = Purchase.objects.get(pk=purchase_pk)
        pur_obj.paypal_ipn_log += '\n\nUTC TIMESTAMP: [{now}]\n'.format(
                now=timezone.now().strftime('%Y-%m-%d %H:%M'))
        pur_obj.paypal_ipn_log += str(data)
        

'''

[02/Jun/2014 15:33:49] INFO [events.paypal_ipn_handler:84] Endpoint View class called
[02/Jun/2014 15:33:49] INFO [events.paypal_ipn_handler:87] POST request detected
[02/Jun/2014 15:33:51] INFO [events.paypal_ipn_handler:90] verify data: True

[02/Jun/2014 15:33:51] INFO [events.views:198]

{
u'protection_eligibility': u'Ineligible', 
u'last_name': u'Graber', 
u'txn_id': u'7TT023172U000992N', 
u'shipping _method': u'Default',
u'shipping_discount': u'0.00',
u'receiver_email': u'ikedaseminar@aikikai-zuerich.ch',
u'payment_status': u'Completed',
u'payment_gross': u'', 
u'tax': u'0.00', 
u'residence_country': u'CH',
u'payer_status': u'verified', 
u'txn_type': u'web_accept', 
u'handling_amount': u'0.00',
u'payment_date': u' 08:33:39 Jun 02, 2014 PDT', 
u'first_name': u'Michael', 
u'btn_id': u'82159917', 
u'item_name': u'3 Keikos (80.- sFr.) + Party (10.- sFr.)',
u'charset': u'window s-1252',
u'custom': u'PId-9',
u'notify_version': u'3.8',
u'transaction_subject': u'PId-9',
u'item_number': u'3KP',
u'receiver_id': u'ZHNPMGEBT7GF6', 
u'business': u'ikedaseminar@aikikai-zuerich.ch',
u'payer_id': u'45G69B646H5QL',
u'discount': u'0.00',
u'verify_sign': u'Axa7.vqN.YIfM1RBeQgOQmNWLfZEA13oXRuSNK.nslGCh4YYI0oxCnvl',
u'payment_fee': u'',
u'insurance_amount': u'0.00',
u'mc_fee': u'0.10',
u'mc_currency': u'CHF',
u'shipping': u'0.00',
u'payer_email': u'semike@bluewin.ch',
u'payment_type': u'instant',
u'mc_gross': u'0.10',
u'ipn_track_id': u'7b6c369c6dd3d',
u'quantity': u'1'
}


'''
