#!/usr/bin/env python3

"""The release monitor project."""

# std imports:
import logging
import os
import sys

from time import sleep
from abc import ABC, abstractmethod
from typing import Set, Union
# wow fix CI :)
assert Set
assert Union

# 3rt party imports:
import feedparser
import requests

from f8a_worker.setup_celery import init_celery, init_selinon
from f8a_worker.utils import normalize_package_name
from selinon import run_flow

# local imports:
from release_monitor.defaults import NPM_URL, PYPI_URL, ENABLE_SCHEDULING, SLEEP_INTERVAL


def set_up_logger():
    """Set up logging."""
    loglevel = os.environ.get('LOGLEVEL', 'INFO').upper()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger = logging.getLogger('release_monitor')
    logger.setLevel(loglevel)
    logger.addHandler(handler)
    return logger


logger = set_up_logger()


class Package:
    """Encapsulate name and version."""

    def __init__(self, name, version):
        # type: (str, str) -> None
        """Create new package."""
        self.name = name
        self.version = version

    def __eq__(self, other):
        """Test equality element by element."""
        return (self.name, self.version) == (other.name, other.version)

    def __hash__(self):
        """For usage in sets."""
        return hash((self.name, self.version))


class AbstractMonitor(ABC):
    """
    Abstract monitoring component for any feed (XML, JSON ...).

    This class implements common logic, like set comparison. Implement your own child class
    for each specific feed.
    """

    def __init__(self):
        # type: () -> None
        """
        Create new monitor with sets of old and new packages.

        Don't immediately schedule all packages in the feed.
        TODO: decide on this ^
        """
        self.old_set = self.fetch_feed()  # type: Set[Package]
        self.new_set = self.old_set  # type: Set[Package]

    @abstractmethod
    def fetch_feed(self):
        # type: () -> Set[Package]
        """
        Implement your feed update logic here (e.g. load new XML file from the Internet).

        Return the new feed as a set of packages.
        """
        pass

    def get_updated_packages(self):
        # type: () -> Set[Package]
        """Run this function in an infinite loop to get incremental updates for your feed."""
        self.old_set = self.new_set
        self.new_set = self.fetch_feed()
        return self.new_set - self.old_set


class PypiMonitor(AbstractMonitor):
    """Monitor Python Package Index."""

    def __init__(self, url=None):
        """Store some PyPi specific data."""
        self.pypi_url = url or PYPI_URL
        super(PypiMonitor, self).__init__()

    def fetch_feed(self):
        """Fetch PyPi RSS updates."""
        def create_package_from_pypi_dict(dict):
            title_parts = dict['title'].split(' ')
            return Package(str.lower(title_parts[0]), title_parts[1])

        list_of_pypi_updates = feedparser.parse(self.pypi_url + "rss/updates.xml").entries
        try:
            updated_packages = set(map(create_package_from_pypi_dict, list_of_pypi_updates))
        except KeyError:
            # if the "title" does not exist, catch the error and return nothing
            return set()
        except IndexError:
            # if the "title" does not contain name and version, catch the error and return nothing
            return set()

        return updated_packages


class NPMMonitor(AbstractMonitor):
    """Monitor for the NPM package registry."""

    def __init__(self, url=None):
        """Store some NPM specific data."""
        self.npm_url = url or NPM_URL + "-/rss"
        super(NPMMonitor, self).__init__()

    def fetch_pkg_names_from_feed(self):
        # type: () -> Union[Set[str], None]
        """Contact NPM repository and get a list of updated packages."""
        npm_feed = feedparser.parse(self.npm_url)
        try:
            r = set(map(lambda x: x['title'], npm_feed.entries))
            return r
        except KeyError:
            return None

    @staticmethod
    def fetch_latest_package_version(package):
        # type: (str) -> Union[str, None]
        """Contact NPM repository and get the latest version for the package."""
        package_url = NPM_URL + "-/package/{}/dist-tags".format(package)
        try:
            req = requests.get(package_url, headers={'content-type': 'application/json'})
            if req.status_code == 200:
                body = req.json()
                return body['latest']
        except ValueError:
            # The body was not a valid JSON
            return None
        except KeyError:
            # The body was a valid JSON, but it did not contain version field
            return None

    def fetch_feed(self):
        """
        Fetch the NPM feed.

        This one is a bit more tricky as the feed itself does not contain version number. So there
        are multiple possibilities how to solve this:

        a) don't care, fetch the feed, for each entry do additional HTTP request and get the newest
        version as well. (motto: premature optimization is the root of all evil)
        b) create a local cache and try it before performing the request itself
        c) reimplement the logic from abstract base class and just calculate set(pkg_names) -
        - set(old_names)

        I'll go with the first one for now.
        """
        npm_feed = self.fetch_pkg_names_from_feed()
        if npm_feed is None:
            return set()

        def create_package_object(pkg_name):
            # type: (str) -> Union[Package, None]
            version = NPMMonitor.fetch_latest_package_version(pkg_name)
            return None if version is None else Package(pkg_name, version)

        def not_none(x):
            return x is not None

        return set(filter(not_none, map(create_package_object, npm_feed)))


class ReleaseMonitor():
    """Class which check rss feeds for new releases."""

    def __init__(self):
        """Constructor."""
        logger.info("Starting the monitor service")

        # Create PyPi monitor
        self.pypi_monitor = PypiMonitor()

        # Create NPM monitor
        self.npm_monitor = NPMMonitor()

        # Initialize Selinon if we want to run in production
        if ENABLE_SCHEDULING:
            init_celery(result_backend=False)
            init_selinon()

    def run_package_analysis(self, name, ecosystem, version):
        """Run Selinon flow for analyses.

        :param name: name of the package to analyse
        :param version: package version
        :param ecosystem: package ecosystem
        :return: dispatcher ID serving flow
        """
        node_args = {
            'ecosystem': ecosystem,
            'name': normalize_package_name(ecosystem, name),
            'version': version,
            'force': True,
            'recursive_limit': 0
        }

        logger.info("Scheduling Selinon flow '%s' "
                    "with node_args: '%s'", 'bayesianFlow', node_args)
        return run_flow('bayesianFlow', node_args)

    def run(self):
        """Run the monitor."""
        logger.info("Sleep interval: {}".format(SLEEP_INTERVAL))
        logger.info("Enabled scheduling: {}".format(ENABLE_SCHEDULING))

        while True:
            for pkg in self.pypi_monitor.get_updated_packages():
                if ENABLE_SCHEDULING:
                    logger.info("Scheduling package from PyPI: '%s':'%s'", pkg.name, pkg.version)
                    self.run_package_analysis(pkg.name, 'pypi', pkg.version)
                else:
                    logger.info("Processing package from PyPI: '%s':'%s'", pkg.name, pkg.version)

            for pkg in self.npm_monitor.get_updated_packages():
                if ENABLE_SCHEDULING:
                    logger.info("Scheduling package from NPM: '%s':'%s'", pkg.name, pkg.version)
                    self.run_package_analysis(pkg.name, 'npm', pkg.version)
                else:
                    logger.info("Processing package from NPM: '%s':'%s'", pkg.name, pkg.version)

            sleep(60 * SLEEP_INTERVAL)


if __name__ == '__main__':
    monitor = ReleaseMonitor()
    monitor.run()
