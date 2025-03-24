from optparse import make_option
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from pu_in_favorites.models import Favorite, FavoritesFolder
from pgprofile.models import Favorite as OldFavorite
from pgprofile.models import UserProfile
from pu_in_favorites import settings
from pu_in_favorites.util import object_to_urn


class Command(BaseCommand):

    help = "Create the default Favorites for all users that do not have Favorites yet"

    option_list = BaseCommand.option_list + (
        make_option('--do-create', '-c',
            action='store_true',
            dest='do-create',
            default=False,
            help='Without this option a dry-run is performed'),
        )


    def handle(self, *args, **options):

        indicator = ''
        if not options['do-create']:
            indicator = 'DRY RUN: '
            print "\nDoing a dry-run\n"

        defaultfavorites_user, created = User.objects.get_or_create(username=settings.DEFAULT_FAVORITES_USERNAME)
        if defaultfavorites_user.get_profile().favoritesfolder_set.count()==0:
            print "#######################################################################################"
            print "# WARNING"
            print "# user %s does not have default favoritesfolders and favorites yet. " % defaultfavorites_user.username
            print "# Add those from the django-admin screens first"
            print "# ...aborted"
            print "#######################################################################################"
            return

        for profile in UserProfile.objects.all():
            if profile.favoritesfolder_set.count()==0:
                print "%sinitialising default favorites for %s" % (indicator, profile.slug)
                if options['do-create']:
                    FavoritesFolder.create_defaults_for(profile)

            if options['do-create']:
                userdefaultfolder = profile.favoritesfolder_set.all()[0]
            oldfavorites = OldFavorite.objects.filter(profiel=profile)
            for oldfav in oldfavorites:
                if oldfav.object_id:
                    try:
                        urn = object_to_urn(oldfav.tgt)
                    except:
                        # do not create the favorite if the target doesn't exist anymore
                        print "link broken: %s %d" % (oldfav.content_type.model, oldfav.object_id)
                        continue
                else:
                    urn = oldfav.url

                favcreated = False
                if options['do-create']:
                    newfav, favcreated = Favorite.objects.get_or_create(folder=userdefaultfolder, uri=urn, defaults={'_title': oldfav._title})
                print "%s%s %s for %s" % (indicator, 'created' if favcreated else 'updated', oldfav._title, profile.user.username)


        if not options['do-create']:
            print "\nend of dry-run\n"
