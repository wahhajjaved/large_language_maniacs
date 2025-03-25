"""Client for Netbox API transactions."""

import asyncio
import logging

from aionetbox import AIONetbox

from prophetess_netbox.exceptions import (
    InvalidPKConfig,
    InvalidNetboxEndpoint,
    InvalidNetboxOperation,
)

log = logging.getLogger('prophetess.plugins.netbox.client')


class NetboxClient:
    """Re-usable abstraction to aionetbox"""

    def __init__(self, *, host, api_key, loop=None):
        """Initialize a single instance with no authentication."""
        self.loop = loop or asyncio.get_event_loop()
        self.__cache = {}  # TODO: make a decorator that caches api classes?

        self.client = AIONetbox.from_openapi(url=host, api_key=api_key)

    async def close(self):
        await self.client.close()

    def build_model(self, endpoint, method, action):
        """ Return the aionetbox Api method from an endpoint class """
        name = '{}_{}_{}'.format(endpoint, method, action)

        try:
            api = getattr(self.client, endpoint)
        except AttributeError:
            raise InvalidNetboxEndpoint('{} module not found'.format(endpoint))

        try:
            return getattr(api, name)
        except AttributeError:
            raise InvalidNetboxOperation('{} not a valid operation'.format(name))

    async def fetch(self, *, endpoint, model, params):
        func = self.build_model(endpoint, model, 'list')
        try:
            return await func(**params)
        except ValueError:
            # Bad Response
            raise
        except TypeError:
            # Bad params
            raise

    async def entity(self, *, endpoint, model, params):
        """ Fetch a single record from netbox using one or more look up params """

        data = await self.fetch(endpoint=endpoint, model=model, params=params)

        if data.count < 1:
            return None

        elif data.count > 1:
            kwargs = ', '.join('='.join(i) for i in params.items())
            raise InvalidPKConfig('Not enough criteria for <{}({})>'.format(endpoint, kwargs))

        return data.results.pop(-1)

    async def entities(self, *, endpoint, model, params):
        """ Fetch all matching records from netbox using one or more look up params """

        data = await self.fetch(endpoint=endpoint, model=model, params=params)

        if data.count < 1:
            return None

        return data.results
