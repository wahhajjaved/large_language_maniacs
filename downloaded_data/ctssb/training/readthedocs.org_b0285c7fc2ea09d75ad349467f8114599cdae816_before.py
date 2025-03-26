import logging
from optparse import make_option

from django.core.management.base import BaseCommand
from django.conf import settings

from readthedocs.builds.constants import LATEST
from readthedocs.builds.models import Version
from readthedocs.search import parse_json
from readthedocs.restapi.utils import index_search_request

log = logging.getLogger(__name__)


class Command(BaseCommand):

    option_list = BaseCommand.option_list + (
        make_option('-p',
                    dest='project',
                    default='',
                    help='Project to index'),
    )

    def handle(self, *args, **options):
        '''
        Build/index all versions or a single project's version
        '''
        project = options['project']

        if project:
            queryset = Version.objects.public(project__slug=project)
            log.info("Building all versions for %s" % project)
        elif getattr(settings, 'INDEX_ONLY_LATEST', True):
            queryset = Version.objects.public().filter(slug=LATEST)
        else:
            queryset = Version.objects.public()
        for version in queryset:
            log.info("Reindexing %s" % version)
            try:
                commit = version.project.vcs_repo(version.slug).commit
            except:
                # This will happen on prod
                commit = None
            try:
                page_list = parse_json.process_all_json_files(version, build_dir=False)
                index_search_request(
                    version=version, page_list=page_list, commit=commit,
                    project_scale=0, page_scale=0, section=False, delete=False)
            except Exception:
                log.error('Build failed for %s' % version, exc_info=True)
