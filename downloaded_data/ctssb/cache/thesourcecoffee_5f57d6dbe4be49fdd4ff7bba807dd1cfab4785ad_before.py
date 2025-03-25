from annoying.decorators import render_to
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.messages import info, error
from django.core.urlresolvers import reverse
from django.db import transaction
from django.shortcuts import redirect
from django.utils.translation import ugettext_lazy as _
from mezzanine.utils.urls import login_redirect
import stripe
from customers.forms import CustomerForm
from customers.tests import signup_test_customer
from gifts.forms import GiftSubscriptionForm
from gifts.models import GiftSubscription
from rewards.forms import RewardCodeForm
from subscriptions.forms import SubscriptionForm
from subscriptions.models import Plan, Subscription

stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = getattr(settings, "STRIPE_API_VERSION", "2012-11-07")

@user_passes_test(lambda u: u.is_superuser)
@login_required
def add_test_customer(request):
    (response, post) = signup_test_customer(request.POST)

    def errors_or_none(form):
        try:
            return response.context[form].errors
        except:
            return None

    customer_form_errors = errors_or_none('customer_form')
    subscription_form_errors = errors_or_none('subscription_form')

    if response.status_code not in [200, 302]:
        messages.error(request, 'Error: status_code %s' % response.status_code)

    elif customer_form_errors:
        messages.error(request, 'Error: customer_form errors %s' %
            str(dict(customer_form_errors)))
    elif subscription_form_errors:
        messages.error(request, 'Error: subscription_form errors %s' %
            str(dict(subscription_form_errors)))
    else:
        messages.info(request, 'Test customer added')

    return redirect(reverse('admin:index'))


@login_required
@render_to('customers/tips.html')
def tips(request):
    return locals()


@login_required
@render_to('customers/home.html')
def home(request):
    return locals()


def gift_purchase(request, context):
    with transaction.commit_on_success():
        save = transaction.savepoint()
        try:
            data = {
                'plan': context['plan'],
                'giftee': context['gift_form'].cleaned_data['giftee'],
                'gifter': context['gift_form'].cleaned_data['gifter'],
            }

            gift = GiftSubscription(**data).save()

            stripe.Charge.create(
                amount=int(context['plan'].price * 100),
                currency='usd',
                card=request.POST['stripeToken'],
                description='{plan} for {giftee} from {gifter}'.format(**data)
            )

        except Exception as e:
            transaction.savepoint_rollback(save)
            error(request, e)

    # Gather e-mail info
    context = { 'gift':gift, }
    gifter_subject = SiteSetting.objects.get(key="gifts.gifter_email_subject")
    gifter_html = loader.render_to_string("gifts/gifter_email.html", context_instance=context)
    gifter_text = loader.render_to_string("gifts/gifter_email.txt", context_instance=context)
    gifter_email = data['gifter']

    giftee_subject = SiteSetting.objects.get(key="gifts.giftee_email_subject")
    giftee_html = loader.render_to_string("gifts/giftee_email.html", context_instance=context)
    giftee_text = loader.render_to_string("gifts/giftee_email.txt", context_instance=context)
    giftee_email = data['giftee']

    # Email gifter
    email = EmailMultiAlternatives(
        gifter_subject,
        gifter_text,
        [gifter_email,])
    email.attach_alternative(gifter_html, "text/html")
    email.send(fail_silently=False)

    # Email giftee
    email = EmailMultiAlternatives(
        giftee_subject,
        giftee_text,
        [giftee_email,])
    email.attach_alternative(giftee_html, "text/html")
    email.send(fail_silently=False)

    # Redirect to page with message
    return redirect(reverse('gifts_sent'))


def gift_redeem(request, context):
    with transaction.commit_on_success():
        save = transaction.savepoint()
        try:

            # Create coupon so customer gets free subscription
            coupon = stripe.Coupon.create(percent_off=100, duration=once)['id']

            customer_form = context['customer_form']
            customer = customer_form.save(commit=False).customer

            subscription = Subscription(customer=customer, plan=plan)
            subscription.save(coupon=coupon)

            transaction.savepoint_commit(save)

            if not customer.user.is_active:
                send_verification_mail(request, customer.user, "signup_verify")
                info(request, _("A verification email has been sent with "
                                "a link for activating your account."))
                return redirect(request.GET.get("next", "/"))
            else:
                info(request, _("Successfully signed up"))
                auth_login(request, customer.user)
                return login_redirect(request)
            data = {
                'plan': context['plan'],
                'giftee': context['gift_form'].cleaned_data['giftee'],
                'gifter': context['gift_form'].cleaned_data['gifter'],
            }

        except Exception as e:
            transaction.savepoint_rollback(save)
            error(request, e)

@render_to('customers/gifts_sent')
def gifts_sent(request):
    return {}


@render_to('customers/signup.html')
def signup(request):

    # Necessary data for page
    stripe_key = settings.STRIPE_PUBLIC_KEY
    subscription_form = SubscriptionForm(request.POST or None)
    customer_form = CustomerForm(request.POST or None)
    gift_form = GiftSubscriptionForm(request.POST or None)
    plans = Plan.objects.jsonify_for_form()
    code_check_url = reverse('gifts_check_code')
    invite_code = request.GET.get('invite_code', '')
    reward_code_form = RewardCodeForm(request.POST or None,
        initial={'invite_code': invite_code})

    context = {
        'customer_form': customer_form,
        'subscription_form': subscription_form,
        'gift_form': gift_form,
        'reward_code_form': reward_code_form,
        'stripe_key': stripe_key,
        'plans': plans,
        'gift': request.POST.get('gift'),
        'code_check_url': code_check_url,
    }

    # Shortcut for initial page load
    if not request.method != 'POST':
        return context

    # Validate forms, handle gift if necessary
    if subscription_form.is_valid():
        context['plan'] = Plan.objects.get(
            amount=subscription_form.cleaned_data['amount'],
            interval=subscription_form.cleaned_data['interval'])
        plan = context['plan']
    else:
        return context

    if context.get('gift_purchase') and gift_form.is_valid():
        return gift_purchase(request, context)

    if context.get('gift_redeem') and customer_form.is_valid():
        return gift_redeem(request, context)

    if not customer_form.is_valid():
        return context

    if not reward_code_form.is_valid():
        return context

    # Attempt normal subscription signup
    with transaction.commit_on_success():
        save = transaction.savepoint()
        try:
            customer = customer_form.save(commit=False).customer
            customer.update_card(request.POST['stripeToken'])
            customer.save()

            subscription = Subscription(customer=customer, plan=plan)
            subscription.save()

            transaction.savepoint_commit(save)

            form_invite_code = reward_code_form.cleaned_data['invite_code']
            if form_invite_code != '' and form_invite_code != None:
                inv_code_instance = InviteCode.objects.filter(
                    code=form_invite_code)
                if inv_code_instance.exists():
                    inv = inv_code_instance.get()
                    inv.customer.grant_reward(subscription)

            if not customer.user.is_active:
                send_verification_mail(request, customer.user, "signup_verify")
                info(request, _("A verification email has been sent with "
                                "a link for activating your account."))
                return redirect(request.GET.get("next", "/"))
            else:
                info(request, _("Successfully signed up"))
                auth_login(request, customer.user)
                return login_redirect(request)

        except Exception as e:
            transaction.savepoint_rollback(save)
            error(request, e)

    return context
