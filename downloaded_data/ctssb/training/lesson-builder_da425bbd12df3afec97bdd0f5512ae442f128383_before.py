"""
CGI Script handling github webhooks

this script mainly takes care of in- and output
and hands off most of the actual work to the build module
"""

import sys
import json
import logging
import os
import io

from . import github, build, config
import traceback
from lesson_builder import misc
from .misc import Maybe


__author__ = 'Justus Adam'
__version__ = '0.1'


# has to be the directory of this programs git repo root
_app_repo_root = APP_DIRECTORY = config.BASE_DIRECTORY

THIS_REPO_NAME = 'fsr/lesson-builder'

LOGGER = logging.getLogger(__name__)

_default_data_directory = '.data'


def relative(*args, to=APP_DIRECTORY):
    """
    path relative to the APP_DIRECTORY or any other

    convenience wrapper around os.path.join

    :param args:
    :param to:
    :return:
    """
    return os.path.abspath(os.path.join(to, *args))


def force_cache(func):
    cached = Maybe()

    def wrapper(*args, **kwargs):
        if cached.none():
            cached.set(func(*args, **kwargs))
        return cached.get()
    return wrapper


REPOS_DIRECTORY = relative('repos')
WATCH_CONF_NAME = 'watch_conf.json'
SKIP_STRINGS = {'[skip build]', '[build skip]'}


config.DEBUG = False


def apply(function, iterable):
    """
    Apply function to all elements of iterable

    :param function:
    :param iterable:
    :return:
    """
    for i in iterable:
        function(i)


@force_cache
def get_watch_conf():
    """
    Open, read and parse the watch config

    :return: python dict
    """
    conf_path = relative(WATCH_CONF_NAME)
    with open(conf_path) as f:
        return json.load(f)


def write_watch_conf(data):
    """
    Write python dicts/lists to the watch config file

    :param data: data to write
    :return: None
    """
    conf_path = relative(WATCH_CONF_NAME)
    with open(conf_path, mode='w') as f:
        json.dump(data, f, indent=4)


def is_known(name, watch_conf=None):
    """
    Check whether a repository name is in the watch conf.

    you can provide the watch conf yourself if you have
    read it already to avoid the IO of loading it in this function
    :param name:
    :param watch_conf:
    :return:
    """
    if watch_conf is None:
        watch_conf = get_watch_conf()

    known = watch_conf.get('watched', ())

    mapped = {
        a['name'] for a in known
    }
    return name in mapped


def handle_push(event, raw_data):
    """
    Handle the payload received and return a somewhat useful response

    :param event: github.Event instance
    :param raw_data: raw bytes of the message
    :return:
    """
    payload = event.payload

    repo = event.repo

    if repo.name in special_actions:
        return special_actions[repo.name](repo)

    known = get_watch_conf().get('watched', ())

    mapped = {
        a['name']: a for a in known
    }

    if repo.name not in mapped:
        LOGGER.error(
            'Repository {} not on watchlist'.format(repo.name)
        )
        return "Repository not on watchlist"

    for skip_string in SKIP_STRINGS:
        if skip_string in payload['head_commit']['message']:
            LOGGER.info(
                'Skipping build {} [commit_message]'.format(
                    repo.name
                )
            )
            return "Commit message demands skip"

    if not github.verify(
            mapped[repo.name],
            raw_data,
            get_header_soft(SIGNATURE),
            os.environ['HTTP_USER_AGENT']
    ):
        return "Unknown requester"

    LOGGER.info(
        'Started build for {}'.format(repo.name)
    )

    repo_path = relative(mapped[repo.name]['directory'], to=REPOS_DIRECTORY)

    if not os.path.exists(repo_path):
        os.makedirs(repo_path)
        code = try_clone(repo, repo_path)
    else:
        code = try_pull(repo, repo_path)

    if code != 0:
        LOGGER.error(
            'Clone for repository {} in directory {} failed with {}'.format(
                repo.name, repo_path, code
            )
        )
        return "Git operations failed"
    else:
        LOGGER.info(build.build_and_report(repo_path))
        return "Build finished"


def update(r):
    """
    Update this software using git

    :param r:
    :return:
    """
    p = r.apull(_app_repo_root)
    code = p.wait()
    if code != 0:
        LOGGER.critical(
            'Update failed with code {}'.format(code)
        )
        LOGGER.debug(
            misc.error_capture_format(
                ('stderr', p.stderr.read().decode())
            )
        )
        return 'Update failed'
    else:
        LOGGER.info(
            'Update successful'
        )
        return "Update successful"


def try_clone(repo, path):
    """
    Clone a repository and wait for it to finish

    :param repo: repository
    :param path:
    :return: returncode
    """
    return repo.aclone(path).wait()


def try_pull(repo, path):
    """
    Pull the repository and clone it if it fails

    :param repo:
    :param path:
    :return: returncode
    """
    code = repo.apull(path).wait()
    if code != 0:
        code = try_clone(repo, path)
    return code


def handle_ping(event):
    hook_id = event.payload['hook_id']
    repo_name = event.repo.name

    watch_conf = get_watch_conf()

    directory = watch_conf.get('data_directory', _default_data_directory)
    file_path = relative(directory, 'hook_{}.conf.json'.format(hook_id))

    if os.path.exists(file_path):
        mode = 'w'
    else:
        mode = 'w+'
    with open(file_path, mode=mode) as file:
        json.dump(event.payload['hook'], fp=file, indent=4)

    LOGGER.info(
        'Received ping event:'
    )
    LOGGER.debug(
        'repository: {}\n'
        'hook_id: {}\n'
        'data saved in {}\n'
        'watched: {}'.format(
            repo_name, hook_id, file_path,
            is_known(repo_name, watch_conf) or repo_name in special_actions
        )
    )

    return 'Ping Received'


def do(payload):
    """
    Do what needs to be done

    parse and handle the payload, print the results

    :param payload:
    :return: None
    """
    payload = json.loads(payload)
    event = github.Event(
        type=get_header(EVENT_TYPE),
        repo=github.GitRepository.from_json(payload['repository']),
        payload=payload
    )

    if event.type == github.PUSH:
        return handle_push(event, payload)
    elif event.type == github.PING:
        return handle_ping(event)
    else:
        LOGGER.error(
            'Unknown event {}\n'.format(event.type)
        )
        LOGGER.debug(
            misc.error_capture_format(
                ('payload', event.payload)
            )
        )


ok_html_headers = 'Content-Type: text/html; charset=utf-8'


ok_handled_header = 'Content-Type: text/plain; charset=utf-8'


ok_format_string = """
<html>
<head>
<style type="text/css">
body {{
    font-family: monaco, sans-serif;
}}
#box {{
  margin: 20px auto;
  background-color: rgb(0, 15, 169);
  color: white;
  width: 600px;
  height: auto;
  padding: 20px 40px;
}}
#box a {{
 color:orange;
}}
</style>
{head}
</head>
<body>
{body}
</body>
</html>
"""


hello = """
<div id="box">
<h1>I am the webhook receiver</h1>
<p>This is a hello message for attempts at reaching me with a get request.</p>
<p>My purpose is to be an endpoint to some github webhooks
for an automated TeX builder.</p>
<p>If you'd like to learn more about the project visit me on
<a href="https://github.com/{}">Github</a>.</p>
</div>
""".format(THIS_REPO_NAME)


def ok(head='', body=''):
    return ok_format_string.format(
        head=head,
        body=body
    )


CONTENT_TYPE = 'ct'
EVENT_TYPE = 'event'
SIGNATURE = 'signature'


aliases = {
    EVENT_TYPE: ('X-GitHub-Event', 'X_GITHUB_EVENT', 'HTTP_X_GITHUB_EVENT'),
    CONTENT_TYPE: ('Content-Type', 'content-type', 'CONTENT_TYPE'),
    SIGNATURE: ('X-Hub-Signature', 'HTTP_X_HUB_SIGNATURE')
}


special_actions = {
    THIS_REPO_NAME: update
}


def get_header(name):
    header_aliases = aliases[name]
    for alias in header_aliases:
        if alias in os.environ:
            return os.environ[alias]
    else:
        raise KeyError(
            'For key {}\n{}'.format(
                name,
                misc.error_capture_format(
                    ('environ', os.environ)
                )
            )
        )


def get_header_soft(name, default=None):
    header_aliases = aliases[name]
    for alias in header_aliases:
        if alias in os.environ:
            return os.environ[alias]
    else:
        return default


def handle_request():
    """Main function"""

    # we return ok in any case
    # we don't necessarily want github to know of our problems

    is_hook = False

    try:

        # _, ce = cgi.parse_header(get_header(CONTENT_TYPE))


        payload = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8').read()

        if not payload:
            message = ok(body=hello)
            is_hook = False
        else:
            message = do(payload)
            is_hook = True
    except Exception as e:
        # we catch any exception and log them before it might accidentally get reported
        LOGGER.critical(
            'Caught build exception {}'.format(
                repr(e)
            )
        )
        LOGGER.debug(
            misc.error_capture_format(
                ('traceback', '\n'.join(traceback.format_tb(sys.exc_info()[2])))
            )
        )
        message = 'Exception occurred, build failed'

    print(ok_handled_header if not is_hook else ok_html_headers)
    print()
    print(message)
