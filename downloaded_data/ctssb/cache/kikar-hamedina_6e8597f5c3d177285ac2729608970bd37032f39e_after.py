#!encoding utf-8
from csv import DictWriter

from django.utils import timezone

from facebook_feeds.management.commands.kikar_base_commands import KikarBaseCommand
from facebook_feeds.models import Facebook_Feed, Facebook_Status

DELIMITER = '~'


class Command(KikarBaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--year',
                            action='store',
                            dest='year',
                            default=None,
                            help="choose year to filter on"
                            )

        parser.add_argument('--feed',
                            action='store',
                            dest='feed',
                            default=None,
                            help="choose year to filter on"
                            )

    def build_commentator_data(self, feeds, year=None):
        counter = dict()
        years = ['2014', '2015'] if not year else [year]
        for feed in feeds.order_by('id'):
            print(feed.id)
            counter[feed.id] = {}
            counter[feed.id]['unique'] = {'likes_2014': set(), 'likes_2015': set(), 'comments_2014': set(),
                                          'comments_2015': set()}
            counter[feed.id]['full'] = {'likes_2014': long(), 'likes_2015': long(), 'comments_2014': long(),
                                        'comments_2015': long()}
            for year in years:
                for status in feed.facebook_status_set.filter(published__year=year).order_by('published'):
                    if not status.is_comment:
                        counter[status.feed.id]['unique']['likes_%s' % year] = counter[status.feed.id]['unique'][
                            'likes_%s' % year].union(
                            set(status.likes.values_list('user', flat=True)))
                        counter[status.feed.id]['unique']['comments_%s' % year] = counter[status.feed.id]['unique'][
                            'comments_%s' % year].union(
                            set(status.comments.values_list('comment_from_id', flat=True)))
                        counter[status.feed.id]['full']['likes_%s' % year] += status.likes.count()
                        counter[status.feed.id]['full']['comments_%s' % year] += status.comments.count()
                        print('\t%s' % status.published)
        return counter

    def handle(self, *args, **options):
        print('Start.')
        feed = options['feed']
        feeds = Facebook_Feed.objects.filter(id=feed) if feed else Facebook_Feed.objects.all()
        counter = self.build_commentator_data(feeds, year=options['year'])
        file_name = 'commentator_data_{}.csv'.format(timezone.now().strftime('%Y_%m_%d_%H_%M_%S'))
        with open(file_name, 'wb') as f:
            field_names = [
                'feed_id',
                'link',
                'mk_id',
                'mk_name',
                'mk_party',
                'likes_2014_unique',
                'likes_2015_unique',
                'likes_2014_full',
                'likes_2015_full',
                'comments_2014_unique',
                'comments_2015_unique',
                'comments_2014_full',
                'comments_2015_full'

            ]
            csv_data = DictWriter(f, fieldnames=field_names, delimiter=DELIMITER)
            headers = {field_name: field_name for field_name in field_names}
            csv_data.writerow(headers)
            for feed in feeds:
                row = {'mk_id': feed.persona.object_id,
                       'mk_name': unicode(feed.persona.content_object.name).encode(
                           'utf-8') if feed.persona.content_object else feed.username,
                       'mk_party': unicode(feed.persona.content_object.current_party.name).encode(
                           'utf-8') if feed.persona.content_object else None,
                       'feed_id': feed.id,
                       'link': 'http://www.facebook.com/{}'.format(feed.vendor_id),
                       'likes_2014_unique': len(counter[feed.id]['unique']['likes_2014']),
                       'likes_2015_unique': len(counter[feed.id]['unique']['likes_2015']),
                       'likes_2014_full': counter[feed.id]['full']['likes_2014'],
                       'likes_2015_full': counter[feed.id]['full']['likes_2015'],
                       'comments_2014_unique': len(counter[feed.id]['unique']['comments_2014']),
                       'comments_2015_unique': len(counter[feed.id]['unique']['comments_2015']),
                       'comments_2014_full': counter[feed.id]['full']['comments_2014'],
                       'comments_2015_full': counter[feed.id]['full']['comments_2015']
                       }
                csv_data.writerow(row)
        print('Done.')
