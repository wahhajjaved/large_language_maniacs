#!/usr/bin/env python3

import os
import sys
import json
import subprocess

import click
import requests

from revizor2.conf import CONF


def green(s):
    return click.style(s, fg='green')


def yellow(s):
    return click.style(s, fg='yellow')


def red(s):
    return click.style(s, fg='red')


def local(command, log=True):
    out = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if log:
        print(out.stdout.decode())
        print(green(out.stderr.decode()))
    return out


def get_gcloud_project():
    print('Get current google project')
    return local('gcloud config get-value project').stdout.decode().strip().replace(':', '/')


@click.group()
def tests():
    pass


@tests.command(name='build', help='Build docker container')
@click.option('--token', required=None, help='GitHub access token to revizor repo')
@click.option('--push', is_flag=True, default=False, help='Push to github or not')
def build_container(token, push):
    #FIXME: Copy gce-development.json  in terraform
    if token is None:
        token = CONF.credentials.github.access_token
    branch = local('git status', log=False).stdout.decode().splitlines()[0].split()[-1].lower().replace('/', '-')
    project = get_gcloud_project()
    print(f'Build image for branch {branch} and project {project}')
    res = local(f'docker build -t gcr.io/{project}/revizor-tests/{branch}:latest . --build-arg TOKEN={token}')
    if res.returncode != 0:
        print(red('Build failed!'))
        sys.exit(1)
    if push:
        print(f'Push image gcr.io/{project}/revizor-tests/{branch}:latest')
        local(f'docker push gcr.io/{project}/revizor-tests/{branch}:latest')


@tests.command(name='runjob', help='Run job from revizor')
def run_job():
    print('Run job from revizor')
    token = os.environ.get('REVIZOR_API_TOKEN')
    if not token:
        print('You must provide revizor api token to run tests!')
        sys.exit(0)
    session = requests.Session()
    session.headers = {'Authorization': f'Token {token}'}

    revizor_url = os.environ.get('REVIZOR_URL', 'https://revizor.scalr-labs.net')
    testsuite_id = os.environ.get('REVIZOR_TESTSUITE_ID')
    test = session.get(f'{revizor_url}/api/tests/retrieve/{testsuite_id}')
    if test.status_code == 404:
        print(f'Tests not found for {testsuite_id} test suite!')
        sys.exit(0)

    try:
        body = test.json()
    except json.decoder.JSONDecodeError:
        print(f'Error in get test suite id: {test.text}')
        return

    os.environ['REVIZOR_TESTINSTANCE_ID'] = str(body['id'])
    command = body['run_command']
    command += ' -s -v --log-level=debug --log-cli-level=debug --log-file-level=debug --te-remove'

    os.chdir('/tests')
    print(f'Start test with command "{command}"')
    process = subprocess.run(command, shell=True, stderr=subprocess.STDOUT, stdout=subprocess.STDOUT)

    status = 'COMPLETED'
    if process.returncode != 0:
        status = 'FAILED'
    print(f'Report test status {status} for test {body["id"]}')
    resp = session.post(f'{revizor_url}/api/tests/result/{body["id"]}', json={'status': status})
    print(resp.text)


if __name__ == '__main__':
    tests()
