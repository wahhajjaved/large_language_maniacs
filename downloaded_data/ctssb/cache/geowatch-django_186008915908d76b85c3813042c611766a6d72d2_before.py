from django.conf import settings

from geowatchutil.factory import create_client_kafka, create_client_kinesis
from geowatchutil.runtime import provision_consumer_kafka, provision_consumer_kinesis, provision_producer


def load_settings_general():
    return {
        'backend': settings.GEOWATCH_STREAMING_BACKEND,
        'topic_prefix': settings.GEOWATCH_TOPIC_PREFIX
    }


def load_settings_kinesis():
    return {
        'aws_access_key_id': settings.AWS_ACCESS_KEY_ID,
        'aws_secret_access_key': settings.AWS_SECRET_ACCESS_KEY,
        'aws_region': settings.GEOWATCH_KINESIS_REGION
    }


def load_settings_kafka():
    return {'host': settings.GEOWATCH_HOST}


def print_settings(general, kafka, kinesis):
    print "GeoWatch Settings"
    for key in general:
        print key+": "+str(general[key])
    for key in kafka:
        print key+": "+str(kafka[key])
    for key in kinesis:
        print key+": "+str(kinesis[key])


def provision_client():
    settings_general = load_settings_general()
    settings_kafka = load_settings_kafka()
    settings_kinesis = load_settings_kinesis()
    print_settings(settings_general, settings_kafka, settings_kinesis)

    client = None
    if settings_general['backend'] == "kafka":
        settings_kafka = load_settings_kafka()
        client = create_client_kafka(settings_kafka['host'], settings_general['topic_prefix'])
    elif settings_general['backend'] == "kinesis":
        settings_kinesis = load_settings_kinesis()
        client = create_client_kinesis(settings_kinesis['aws_region'], settings_kinesis['aws_access_key_id'], settings_kinesis['aws_secret_access_key'], settings_general['topic_prefix'])

    return client


def provision_geowatch_consumer(topic, codec, max_tries=12, sleep_period=5, verbose=True):
    settings_general = load_settings_general()
    settings_kafka = load_settings_kafka()
    settings_kinesis = load_settings_kinesis()
    print_settings(settings_general, settings_kafka, settings_kinesis)

    client, consumer = None, None
    kwargs = {
        'topic': topic,
        'codec': codec,
        'topic_prefix': settings_general['topic_prefix'],
        'max_tries': max_tries,
        'sleep_period': sleep_period
    }
    if settings_general['backend'] == "kafka":
        kwargs['host'] = settings_kafka['host']
        client, consumer = provision_consumer_kafka(** kwargs)
    elif settings_general['backend'] == "kinesis":
        kwargs['aws_region'] = settings_kinesis['aws_region']
        kwargs['aws_access_key_id'] = settings_kinesis['aws_access_key_id']
        kwargs['aws_secret_access_key'] = settings_kinesis['aws_secret_access_key']
        client, consumer = provision_consumer_kinesis(** kwargs)

    return (client, consumer)


def provision_geowatch_producer(topic, codec, client=None, max_tries=12, sleep_period=5, verbose=True):
    settings_general = load_settings_general()
    settings_kafka = load_settings_kafka()
    settings_kinesis = load_settings_kinesis()
    print_settings(settings_general, settings_kafka, settings_kinesis)

    client, producer = None, None
    kwargs = {
        'topic': topic,
        'codec': codec,
        'client': client,
        'topic_prefix': settings_general['topic_prefix'],
        'max_tries': max_tries,
        'sleep_period': sleep_period
    }

    if client:
        client, producer = provision_producer(settings_general['backend'], ** kwargs)
    else:
        if settings_general['backend'] == "kafka":
            kwargs['host'] = settings_kafka['host']
            client, producer = provision_producer(settings_general['backend'], ** kwargs)
        elif settings_general['backend'] == "kinesis":
            kwargs['aws_region'] = settings_kinesis['aws_region']
            kwargs['aws_access_key_id'] = settings_kinesis['aws_access_key_id']
            kwargs['aws_secret_access_key'] = settings_kinesis['aws_secret_access_key']
            client, producer = provision_producer(settings_general['backend'], ** kwargs)

    return (client, producer)
