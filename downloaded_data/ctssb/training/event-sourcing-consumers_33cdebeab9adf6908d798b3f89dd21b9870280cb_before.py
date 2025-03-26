import os
import config
import logging

from google.cloud import datastore


class DBProcessor(object):
    def __init__(self):
        self.client = datastore.Client()
        self.meta = config.AFAS_DB_PROCESSOR[os.environ.get('DATA_SELECTOR', 'Required parameter is missed')]
        pass

    def process(self, payload):
        if 'id_property' in self.meta and self.meta['id_property'] in payload:
            kind = self.meta['entity_name']
            key = self.value_formatter(payload.get(self.meta['id_property'], None))

            if kind and key:
                payload[self.meta['id_property']] = key  # Make sure edited value is updated in payload

                entity_key = self.client.key(kind, key)
                entity = self.client.get(entity_key)
                if not entity:
                    entity = datastore.Entity(key=entity_key)
            else:
                logging.info('Received payload without matching id_property or filter_property, skipping this entity')
                entity = None
        elif 'filter_property' in self.meta and self.meta['filter_property'] in payload:
            payload[self.meta['filter_property']] = self.value_formatter(
                payload.get(self.meta['filter_property']))  # Make sure edited value is updated in payload

            # get entity_key from filter property
            query = self.client.query(kind=self.meta['entity_name'])
            query.add_filter(
                self.meta['filter_property'], '=', payload[self.meta['filter_property']])
            query_results = list(query.fetch(limit=1))

            if self.meta.get('create_entity', False) and not query_results:
                entity_key = self.client.key(self.meta['entity_name'], payload[self.meta['filter_property']])
                entity = datastore.Entity(key=entity_key)
            else:
                entity = query_results[0] if query_results else None
        else:
            logging.info('Received payload without matching id_property or filter_property, skipping this entity')
            entity = None

        if entity is not None:
            is_valid = RuleEngine(entity, payload).check_validity(self.meta['property_rules']) if \
                'property_rules' in self.meta else True

            if is_valid:
                self.populate_from_payload(entity, payload)
                self.client.put(entity)
            else:
                logging.info('Received payload is not a valid update, skipping this entity')

    def value_formatter(self, value):
        if value and 'value_formatter' in self.meta and 'type' in self.meta['value_formatter']:
            if self.meta['value_formatter']['type'] == 'split' and 'value' in self.meta['value_formatter']:
                splitted_value = value.split(self.meta['value_formatter']['value'])
                value = splitted_value[self.meta['value_formatter'].get('index', 0)]

            if self.meta['value_formatter']['type'] == 'prepend' and 'value' in self.meta['value_formatter']:
                value = self.meta['value_formatter']['value'] + value

            if self.meta['value_formatter']['type'] == 'append' and 'value' in self.meta['value_formatter']:
                value = value + self.meta['value_formatter']['value']

        return value

    @staticmethod
    def populate_from_payload(entity, payload):
        for name in payload.keys():
            value = payload[name]
            entity[name] = value


class RuleEngine(object):
    def __init__(self, old_data, new_data):
        self.old_data = old_data
        self.new_data = new_data

    def check_validity(self, rules):
        outcome = []
        for rule_object in rules:
            if not rule_object.get('conditions') or rule_object.get('rules'):
                raise ValueError("The current rule set is invalid, skipping this entity")

            conditions_outcome = self.get_rule_list_validity(rule_object['conditions'])

            if conditions_outcome:
                outcome.append(self.get_rule_list_validity(rule_object['rules']))
                continue

            outcome.append(True)

        return all(outcome)

    def get_rule_list_validity(self, rules):
        try:
            outcome = []
            for rule in rules:
                field = self.get_field(rule['name'])
                value = rule.get('value')

                if value and value.startswith('field'):
                    value = self.get_field(rule['value'].split(':')[-1])

                rule_outcome = self.get_rule_outcome(field, rule['operator'], value)
                outcome.append(rule_outcome)

            return all(outcome)
        except Exception:
            return False

    def get_field(self, name):
        data = self.old_data if name.startswith('old') else self.new_data
        field = name.split('.')[-1]
        value = data.get(field)

        return value if value != 'null' else None

    @staticmethod
    def get_rule_outcome(field, operator, value):
        # Value type checks
        if operator == 'non_empty' or operator == 'is_true':
            return True if field else False

        if operator == 'empty' or operator == 'is_false':
            return True if not field else False

        # Value content checks
        if operator == 'contains':
            return True if value in field else False

        if operator == 'does_not_contain':
            return True if value not in field else False

        # Values comparison
        if operator == 'equal_to':
            return True if field == value else False

        if operator == 'less_than':
            return True if field < value else False

        if operator == 'less_than_or_equal_to':
            return True if field <= value else False

        if operator == 'greater_than':
            return True if field > value else False

        if operator == 'greater_than_or_equal_to':
            return True if field >= value else False
