from crate.fs import safe_overwrite_dir
from copy import deepcopy
import logging

LOG = logging.getLogger(__name__)

class Manager(object):
    def __init__(self, config_file, sources, destination, filters=[]):
        self.config_file = config_file
        self.sources = sources
        self.destination = destination
        self.filters = filters

    def sync(self):
        files = self.locate()
        LOG.debug("located %d file(s)" % len(files))
        filtered_files = self.filter(files)
        LOG.debug("filtered down to %d file(s)" % len(filtered_files))
        LOG.debug("staging filtered file(s)")
        temp_dest = self.stage(filtered_files)
        LOG.debug("initiating build of staged repo")
        self.build(temp_dest)
        LOG.debug("migrating repo to '%s'" % self.destination)
        self.migrate(temp_dest)
        LOG.debug("done syncing files")

    def locate(self):
        """
        Iterate over ``self.sources``, locating the appropriate file set that
        will be symlinked into ``self.destination``.

        Should return a list-like object.
        """
        raise NotImplementedError

    def filter(self, items):
        """
        Iterate over ``self.filters``, filtering out unwanted items.
        """
        if self.filters:
            result = deepcopy(items)
            for f in self.filters:
                LOG.debug('applying filter "%s"' % f.__class__.__name__)
                result = f.filter(result)
        else:
            result = items
        return result

    def stage(self, files):
        """
        Move filtered files from ``self.sources`` to ``self.destination``.
        """
        raise NotImplementedError

    def build(self, destination):
        """
        Action to perform on ``self.destination`` directory once appropriate files 
        are moved into place.
        """
        raise NotImplementedError

    def migrate(self, source):
        """
        Migrate the staged data to ``self.destination``.
        """
        raise NotImplementedError

