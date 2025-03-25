import json
import operator
import os

from django.conf import settings

from collections import OrderedDict
from django.utils.text import slugify
from takwimu import settings
from takwimu.utils.medium import Medium

from takwimu.models.dashboard import ProfilePage, ProfileSectionPage, COUNTRIES, CountryProfilesSetting
from takwimu.models.dashboard import TopicPage

from .sdg import SDG


def takwimu_countries(request):
    settings = CountryProfilesSetting.for_site(request.site)
    published_status = settings.__dict__

    countries = []
    for code, names in COUNTRIES.items():
        country = {
            'name': names['name'],
            'short_name': names['short_name'],
            'slug': slugify(names['name']),
            'published': published_status[code]
        }
        countries.append(country)

    return {'countries': countries}


def takwimu_stories(request):

    stories_latest = []
    stories_trending = []

    try:
        if settings.HURUMAP.get('url') != 'https://takwimu.africa':
            with open('data/articles.json') as f:
                stories = json.load(f)
        else:
            client = Medium()
            stories = client.get_publication_posts('takwimu-africa',
                                                   count=20)
        stories_latest = stories[0:3]

        stories_dict = [i.__dict__ for i in stories]
        stories_trending = sorted(
            stories_dict, key=operator.itemgetter('clap_count'), reverse=True)

    except Exception as e:
        pass

    return {
        'stories_latest': stories_latest,
        'stories_trending': stories_trending[0:3]
    }


def takwimu_topics(request):
    """
        Sections, topics with indicators and key issues
    """

    sections = []
    try:
        profile_topics = _traverse_profile_sections(
            ProfilePage.objects.live(), request)
        profile_section_topics = _traverse_profile_sections(
            ProfileSectionPage.objects.live(), request, len(profile_topics))
        sections = profile_topics + profile_section_topics
    except Exception as e:
        pass

    return {
        'sections': sections,
    }


def _traverse_profile_sections(profile_sections, request, start_section_num=0):
    sections_by_title = OrderedDict()
    section_topics_by_title = OrderedDict()
    section_topic_indicators_by_title = OrderedDict()
    for section_num, profile_section in enumerate(profile_sections, start=start_section_num + 1):
        (country, profile_title) = (str(profile_section.get_parent()), profile_section.title) \
            if isinstance(profile_section, ProfileSectionPage) \
            else (str(profile_section), 'Country Overview')
        default_section = {
            'id': 'section-{}'.format(section_num),
            'title': profile_title,
            'href': 'section-{}-topics-tab'.format(section_num),
            'key_issues': [],
        }
        section = sections_by_title.setdefault(
            profile_title.lower(), default_section)
        topics_by_title = section_topics_by_title.setdefault(
            profile_title.lower(), OrderedDict())
        topic_indicators_by_title = section_topic_indicators_by_title.setdefault(
            profile_title.lower(), OrderedDict())
        start_topic_num = len(topics_by_title.keys())
        for topic_num, section_topic in enumerate(profile_section.body, start=start_topic_num + 1):
            # Topics that have no indicators (key issues) should be
            # displayed separately.
            topic_title = section_topic.value['title']
            if not section_topic.value['indicators']:
                section['key_issues'].append({
                    'id': '{}-key_issue-{}'.format(section['id'], topic_num),
                    'title': topic_title,
                    'country': country,
                    'href': profile_section.get_url(request),
                })
            else:
                default_topic = {
                    'id': '{}-topic-{}'.format(section['id'], topic_num),
                    'title': topic_title,
                    'href': '{}-topic-{}-indicators-tab'.format(section['id'], topic_num),
                }
                topic = topics_by_title.setdefault(
                    topic_title.lower(), default_topic)
                indicators_by_title = topic_indicators_by_title.setdefault(
                    topic_title.lower(), OrderedDict())
                start_indicator_num = len(indicators_by_title.keys())
                for indicator_num, topic_indicator in enumerate(section_topic.value['indicators'], start=start_indicator_num + 1):
                    indicator_title = topic_indicator.value['title']
                    default_indicator = {
                        'id': '{}-indicator-{}'.format(topic['id'], indicator_num),
                        'title': indicator_title,
                        'href': '{}-indicator-{}-country-selections-tab'.format(topic['id'], indicator_num),
                        'countries': [],
                    }
                    indicator = indicators_by_title.setdefault(
                        indicator_title.lower(), default_indicator)
                    indicator['countries'].append({
                        'title': country,
                        'href': profile_section.get_url(request),
                    })

                topic['indicators'] = indicators_by_title.values()

        section['topics'] = topics_by_title.values()

    return sections_by_title.values()


def sdgs(request):
    """
        SDGs indicators
    """

    json_sdgs = open('takwimu/fixtures/sdg.json')
    sdgs = json.load(json_sdgs)
    return {
        'sdgs': sdgs,
    }


def asset_manifest(request):
    manifest_filepath = os.path.join(settings.BASE_DIR, 'takwimu/takwimu_ui/build/asset-manifest.json')
    asset_manifest = {}

    if os.environ.get('DEBUG', 'True') == 'True':
        asset_manifest = {
            'debug': True,
            'main': 'js/main.chunk.js',
            'vendor': 'js/bundle.js',
            'runtime': 'js/0.chunk.js',
            'port': os.environ.get('TAKWIMU_REACT_PORT', 3000)
        }
    else:
        try:
            with open(manifest_filepath) as f:
                asset_manifest_contents = json.load(f)
                for key, value in asset_manifest_contents.viewitems():
                    # Strip starting `/static/` from values
                    if key == 'main.js':
                        asset_manifest['main'] = value[8:]
                    elif key == 'runtime~main.js':
                        asset_manifest['runtime'] = value[8:]
                    elif key.startswith('static/js/1') and key.endswith('chunk.js'):
                        asset_manifest['vendor'] = value[8:]

        except Exception as e:
            print(e.message)

    return {
        'asset_manifest': asset_manifest
    }
