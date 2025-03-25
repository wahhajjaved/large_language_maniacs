import os
import logging

from authgen import GithubToken
from githubscanner import GithubCodeScanner

LOGGER = logging.getLogger()
S3_BUCKET = os.environ['S3_BUCKET']
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


def scan_public_repos(github_id: str, force_overwrite = True):
    with GithubToken(USERNAME, PASSWORD, note = github_id) as access_token:
        scanner = GithubCodeScanner(access_token, S3_BUCKET, CLONE_CONFIG, S3_CONFIG, github_id)
        scanner.scan_all(force_overwrite = force_overwrite)

def scan_authorized_repos(access_token: str, force_overwrite = True):
    scanner = GithubCodeScanner(access_token, S3_BUCKET, CLONE_CONFIG, S3_CONFIG)
    scanner.scan_all(force_overwrite = force_overwrite)

def scan_public_repo(github_id, repo_name, cleanup=True):
    with GithubToken(USERNAME, PASSWORD, note = github_id) as access_token:
        scanner = GithubCodeScanner(access_token, S3_BUCKET, CLONE_CONFIG, S3_CONFIG, github_id)
        scanner.scan_repo(repo_name, cleanup)

def scan_private_repo(access_token, repo_name, cleanup=True):
    scanner = GithubCodeScanner(access_token, S3_BUCKET, CLONE_CONFIG, S3_CONFIG)
    scanner.scan_repo(repo_name, cleanup)

def scan_public_commit(github_id, repo_name, commit_sha, cleanup=True):
    with GithubToken(USERNAME, PASSWORD, note = github_id) as access_token:
        scanner = GithubCodeScanner(access_token, S3_BUCKET, CLONE_CONFIG, S3_CONFIG, github_id)
        scanner.scan_commit(repo_name, commit_sha, cleanup)

