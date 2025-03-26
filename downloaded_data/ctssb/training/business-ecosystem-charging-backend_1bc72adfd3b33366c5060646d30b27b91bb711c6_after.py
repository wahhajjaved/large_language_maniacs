# -*- coding: utf-8 -*-

# Copyright (c) 2015 CoNWeT Lab., Universidad Politécnica de Madrid

# This file is part of WStore.

# WStore is free software: you can redistribute it and/or modify
# it under the terms of the European Union Public Licence (EUPL)
# as published by the European Commission, either version 1.1
# of the License, or (at your option) any later version.

# WStore is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# European Union Public Licence for more details.

# You should have received a copy of the European Union Public Licence
# along with WStore.
# If not, see <https://joinup.ec.europa.eu/software/page/eupl/licence-eupl>.

from __future__ import unicode_literals

import requests
from urlparse import urljoin

from django.core.exceptions import ImproperlyConfigured

from wstore.models import Context


class OrderingClient:

    def __init__(self):
        self._ordering_api = 'http://localhost:8080/DSProductOrdering'

    def create_ordering_subscription(self):
        """
        Create a subscription in the ordering API for being notified on product orders creation
        :return:
        """

        # Use the local site for registering the callback
        site = Context.objects.all()[0].local_site.domain

        callback = {
            'callback': urljoin(site, 'charging/api/orderManagement/orders')
        }

        r = requests.post(self._ordering_api + '/productOrdering/v2/hub', callback)

        if r.status_code != 200 and r.status_code != 409:
            msg = "It hasn't been possible to create ordering subscription, "
            msg += 'please check that the ordering API is correctly configured '
            msg += 'and that the ordering API is up and running'
            raise ImproperlyConfigured(msg)

    def update_state(self, order_id, state):
        """
        Change the state of a given order including its order items
        :param order_id: Order object as returned by the ordering API
        :param state: New state
        :return:
        """

        # Build patch body
        patch = {
            'state': state,
        }

        # Make PATCH request
        path = '/DSProductOrdering/api/productOrdering/v2/productOrder/' + unicode(order_id)
        url = urljoin(self._ordering_api, path)

        r = requests.patch(url, patch)

        r.raise_for_status()
