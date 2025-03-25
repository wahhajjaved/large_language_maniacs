
import logging
import collections

from prophetess.plugin import Loader
from prophetess_netbox.client import NetboxClient


log = logging.getLogger('prophetess.plugins.netbox.loader')


class NetboxLoader(Loader):
    required_config = (
        'host',
        'api_key',
        'endpoint',
        'model',
        'pk',
    )

    def __init__(self, **kwargs):
        """ NetboxLoader init """
        super().__init__(**kwargs)

        self.update_method = self.config.get('update_method', 'update')
        self.client = NetboxClient(host=self.config.get('host'), api_key=self.config.get('api_key'))

    def sanitize_config(self, config):
        """ Overload Loader.sanitize_config to add additional conditioning """
        config = super().sanitize_config(config)

        for k in ('model', 'endpoint'):
            config[k] = config[k].lower()

        if not isinstance(config['pk'], list):
            config['pk'] = [config['pk']]

        return config

    async def parse_fk(self, record):
        extracts = self.config.get('fk')
        if not extracts or not isinstance(extracts, collections.Mapping):
            return record

        for key, rules in extracts.items():
            if key not in record:
                log.debug('Skipping FK lookup "{}". Not found in record'.format(key))
                continue

            r = await self.client.entity(
                endpoint=rules.get('endpoint'),
                model=rules.get('model'),
                params=self.build_params(rules.get('pk', []), record)
            )

            if not r:
                log.debug('FK lookup for {} ({}) failed, no record found'.format(key, record.get(key)))
                record[key] = None
                continue

            record[key] = r.id

        return record

    def build_params(self, config, record):
        output = {}
        for item in config:
            if isinstance(item, str):
                output[item] = record.get(item)
            elif isinstance(item, collections.Mapping):
                for k, tpl in item.items():
                    output[k] = tpl.format(**record)

        return output

    def diff_records(self, cur_record, new_record):

        changed = {}

        for k, v in new_record.items():
            if getattr(cur_record, k) and k in self.config.get('fk', {}):
                if getattr(cur_record, k).id != v:
                    changed[k] = v
                continue

            if getattr(cur_record, k) != v:
                changed[k] = v

        return changed

    async def run(self, record):
        """ Overload Loader.run to execute netbox loading of a record """

        er = await self.client.entity(
            endpoint=self.config.get('endpoint'),
            model=self.config.get('model'),
            params=self.build_params(self.config.get('pk'), record)
        )

        record = await self.parse_fk(record)

        payload = {
            'data': record
        }

        method = 'create'
        if er:
            method = self.update_method
            payload['id'] = er.id

        if method == 'partial_update':
            changed_record = self.diff_records(er, record)
            if not changed_record:
                log.debug('Skipping {} as no data has changed'.format(record))
                return

            payload['data'] = changed_record

        func = self.client.build_model(self.config.get('endpoint'), self.config.get('model'), method)

        log.debug('Running with modified payload: {}'.format(payload))
        return await func(**payload)

    async def close(self):
        await self.client.close()
