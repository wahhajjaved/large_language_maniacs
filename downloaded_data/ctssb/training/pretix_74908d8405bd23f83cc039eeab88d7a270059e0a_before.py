from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect
from django.utils.translation import ugettext_lazy as _
from django.views.generic import View

from pretix.multidomain.urlreverse import eventreverse
from pretix.presale.checkoutflow import get_checkout_flow
from pretix.presale.views import CartMixin


class CheckoutView(CartMixin, View):
    def dispatch(self, request, *args, **kwargs):
        self.request = request
        if not self.positions and "async_id" not in request.GET:
            messages.error(request, _("Your cart is empty"))
            return redirect(eventreverse(self.request.event, 'presale:event.index'))

        flow = get_checkout_flow(self.request.event)
        for step in flow:
            if not step.is_applicable(request):
                continue
            if 'step' not in kwargs:
                return redirect(step.get_step_url())
            is_selected = (step.identifier == kwargs.get('step', ''))
            if not is_selected and not step.is_completed(request, warn=not is_selected):
                return redirect(step.get_step_url())
            if is_selected:
                if request.method.lower() in self.http_method_names:
                    handler = getattr(step, request.method.lower(), self.http_method_not_allowed)
                else:
                    handler = self.http_method_not_allowed
                return handler(request)
        raise Http404()
