import os
import signal
import logging
from collections import Counter

from rq import get_current_job

from githubcrawler import GithubCommitCrawler
from knowledgemodel import KnowledgeModel
from codeparser import CodeParser
from authgen import GithubToken

LOGGER = logging.getLogger()
S3BUCKET = os.environ['S3_BUCKET']
S3_CONFIG = {
        'region_name': os.environ['AWS_REGION'],
        'aws_access_key_id': os.environ['AWS_ACCESS_KEY_ID'],
        'aws_secret_access_key': os.environ['AWS_SECRET_ACCESS_KEY'],
        }
CLONE_CONFIG = {
        'tmpfs_drive': os.environ['TMPFS_DRIVE'],
        'fs_drive': os.environ['LARGE_DRIVE'],
        'tmpfs_cutoff': int(os.environ['TMPFS_DRIVE_MAX_WRITE']),
        }
USERNAME = os.environ['GITHUB_CRAWLER_USERNAME']
PASSWORD = os.environ['GITHUB_CRAWLER_PASSWORD']

class MeasuredJobProgress(object):

    def __init__(self, steps_key = 'steps', finished_key = 'finished'):
        self.steps = Counter()
        self.finished = Counter()
        self.steps_key = steps_key
        self.finished_key = finished_key
        self.job = get_current_job()

    def add_step(self, name, count = 1):
        self.steps[name] += count
        self.report()

    def mark_finished(self, name, count = 1):
        self.finished[name] += count
        self.report()

    def report(self):
        self.job.meta[self.steps_key] = self.steps
        self.job.meta[self.finished_key] = self.finished
        self.job.save()


class GithubCodeScanner(object):

    def __init__(self, token, github_id = None, timeout = 360):
        clone_config = {**CLONE_CONFIG, **{'progress': self._rq_keepalive}}
        self.crawler = GithubCommitCrawler(token, clone_config)
        self.github_id = github_id or self.crawler.authorized_login
        self.knowledge = KnowledgeModel(self.github_id, S3BUCKET, S3_CONFIG)
        self.parser = CodeParser(callback = self.knowledge.add_reference)
        self.progress = MeasuredJobProgress()
        self.authorized = bool(github_id)
        self.timeout = timeout

    def skip(self, repo, log = True):
        skip = not self.parser.supports_any_of(*repo.get_languages().keys())
        if skip and log:
            LOGGER.debug('Skipping repo {} because of missing language support'.format(repo.full_name))
        return skip

    def callback(self, repo_name, commit):
        self.parser.analyze_commit(repo_name, commit)
        self.progress.mark_finished(repo_name)
        self._rq_keepalive()

    def add_step(self, name, *args):
        self.progress.add_step(name)
        self._rq_keepalive()

    def _rq_keepalive(self, *args, **kwargs):
        # has extra arguments so that we can pass it around more easily
        # this takes less than one microsecond per call, so it's okay that we call it very often
        signal.alarm(self.timeout)

    def scan_all(self, force_overwrite = False):
        if self.knowledge.exists() and not force_overwrite:
            LOGGER.info('User "{}" scan is up to date. Skipping scan'.format(self.github_id))
            return
        elif self.authorized:
            LOGGER.debug('Initializing progress...')
            self.crawler.crawl_public_repos(self.github_id, self.add_step, lambda repo: self.skip(repo, False), remote_only = True)
            LOGGER.debug('Starting scan...')
            self.crawler.crawl_public_repos(self.github_id, self.callback, self.skip)
        else:
            LOGGER.debug('Initializing progress...')
            self.crawler.crawl_authorized_repos(self.add_step, lambda repo: self.skip(repo, False), remote_only = True)
            LOGGER.debug('Starting scan...')
            self.crawler.crawl_authorized_repos(self.callback, self.skip)
        self.knowledge.save()

    def scan_repo(self, name, cleanup = True):
        if self.authorized:
            self.crawler.crawl_individual_public_repo(self.github_id, name, self.callback, remote_only = True)
            self.crawler.crawl_individual_public_repo(self.github_id, name, self.callback, cleanup = cleanup)
        else:
            self.crawler.crawl_individual_authorized_repo(name, self.callback, remote_only = True)
            self.crawler.crawl_individual_authorized_repo(name, self.callback, cleanup = cleanup)

    def scan_commit(self, repo_name, commit_sha, cleanup = True):
        if self.authorized:
            self.crawler.crawl_individual_public_commit(self.github_id, repo_name, commit_sha, self.callback, cleanup = cleanup)
        else:
            self.crawler.crawl_individual_authorized_commit(repo_name, commit_sha, self.callback, cleanup = cleanup)


def scan_public_repos(github_id: str, force_overwrite = False):
    with GithubToken(USERNAME, PASSWORD, note = github_id) as token:
        scanner = GithubCodeScanner(token, github_id)
        scanner.scan_all(force_overwrite = force_overwrite)

def scan_authorized_repos(access_token: str, force_overwrite = True):
    scanner = GithubCodeScanner(access_token)
    scanner.scan_all(force_overwrite = force_overwrite)

def scan_individual_public_repo(github_id, repo_name, cleanup=False):
    with GithubToken(USERNAME, PASSWORD, note = github_id) as token:
        scanner = GithubCodeScanner(token, github_id)
        scanner.scan_repo(repo_name, cleanup)

def scan_individual_public_commit(github_id, repo_name, commit_sha, cleanup=False):
    with GithubToken(USERNAME, PASSWORD, note = github_id) as token:
        scanner = GithubCodeScanner(token, github_id)
        scanner.scan_commit(repo_name, commit_sha, cleanup)
