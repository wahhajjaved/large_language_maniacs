from pritunl.helpers import *
from pritunl import settings
from pritunl import mongo
from pritunl import logger
from pritunl import messenger
from pritunl import utils
from pritunl import task
from pritunl import server

import datetime

class TaskRoute(task.Task):
    type = 'route'

    @cached_static_property
    def routes_collection(cls):
        return mongo.get_collection('routes_reserve')

    @interrupter
    def task(self):
        try:
            timestamp_spec = utils.now() - datetime.timedelta(
                seconds=settings.vpn.route_ping_ttl)

            docs = self.routes_collection.find({
                'timestamp': {'$lt': timestamp_spec},
            })

            yield

            for doc in docs:
                server_id = doc['server_id']
                vpc_region = doc['vpc_region']
                vpc_id = doc['vpc_id']
                network = doc['network']

                svr = server.get_by_id(server_id)
                if not svr:
                    self.routes_collection.remove({
                        '_id': doc['_id'],
                    })
                    continue

                match = False
                for route in svr.get_routes(include_server_links=True):
                    route_vpc_region = route['vpc_region']
                    route_vpc_id = route['vpc_id']
                    route_network = route['network']

                    if vpc_region == route_vpc_region or \
                            route_vpc_id == route_vpc_id or \
                            route_network == route_network:
                        match = True

                if not match:
                    self.routes_collection.remove({
                        '_id': doc['_id'],
                    })
                    continue

                messenger.publish('instance', ['route_advertisement',
                    server_id, vpc_region, vpc_id, network])
        except GeneratorExit:
            raise
        except:
            logger.exception('Error checking route states', 'tasks')

        yield interrupter_sleep(settings.vpn.server_ping)

task.add_task(TaskRoute, seconds=xrange(0, 60, settings.vpn.server_ping))
