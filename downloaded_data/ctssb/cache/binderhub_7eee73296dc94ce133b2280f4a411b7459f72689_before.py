#!/usr/bin/env python3
import os
import subprocess
import argparse
import dateutil.parser
import dateutil.tz
from datetime import datetime
import time
from ruamel.yaml import YAML


def last_modified_commit(*paths, **kwargs):
    return subprocess.check_output([
        'git',
        'log',
        '-n', '1',
        '--pretty=format:%h',
        *paths
    ], **kwargs).decode('utf-8')

def last_modified_date(*paths, **kwargs):
    return subprocess.check_output([
        'git',
        'log',
        '-n', '1',
        '--pretty=format:%cd',
        '--date=iso',
        *paths
    ], **kwargs).decode('utf-8')

def path_touched(path, commit_range):
    return subprocess.check_output([
        'git', 'diff', '--name-only', commit_range, path
    ]).decode('utf-8').strip() != ''


def render_build_args(options, ns):
    """Get docker build args dict, rendering any templated args."""
    build_args = options.get('buildArgs', {})
    for key, value in build_args.items():
        build_args[key] = value.format(**ns)
    return build_args

def build_image(image_path, image_spec, build_args):
    cmd = ['docker', 'build', '-t', image_spec, image_path]

    for k, v in build_args.items():
        cmd += ['--build-arg', '{}={}'.format(k, v)]
    subprocess.check_call(cmd)

def build_images(prefix, images, tag=None, commit_range=None, push=False):
    value_modifications = {}
    for name, options in images.items():
        image_path = os.path.join('images', name)
        paths = options.get('paths', []) + [image_path]
        if commit_range:
            if not path_touched(*paths, commit_range=commit_range):
                print("Skipping {}, not touched in {}".format(name, commit_range))
                continue
        last_commit = last_modified_commit(*paths)
        if tag is None:
            tag = last_commit
        image_name = prefix + name
        image_spec = '{}:{}'.format(image_name, tag)

        template_namespace = {
            'LAST_COMMIT': last_commit,
            'TAG': tag,
        }
        build_args = render_build_args(options, template_namespace)

        build_image(image_path, image_spec, build_args)
        value_modifications[options['valuesPath']] = {
            'name': image_name,
            'tag': tag
        }

        if push:
            subprocess.check_call([
                'docker', 'push', image_spec
            ])
    return value_modifications

def build_values(name, values_mods):
    rt_yaml = YAML()
    rt_yaml.indent(offset=2)

    values_file = os.path.join(name, 'values.yaml')

    with open(values_file) as f:
        values = rt_yaml.load(f)

    for key, value in values_mods.items():
        parts = key.split('.')
        mod_obj = values
        for p in parts:
            mod_obj = mod_obj[p]
        mod_obj.update(value)


    with open(values_file, 'w') as f:
        rt_yaml.dump(values, f)


def build_chart(name, version=None):
    rt_yaml = YAML()
    rt_yaml.indent(offset=2)

    chart_file = os.path.join(name, 'Chart.yaml')
    with open(chart_file) as f:
        chart = rt_yaml.load(f)

    if version is None:
        version = chart['version'] + '-' + last_modified_commit('.')

    chart['version'] = version

    with open(chart_file, 'w') as f:
        rt_yaml.dump(chart, f)


def fixup_chart_index(repopath):
    """
    Fixup the timestamps in helm charts index.yaml

    Currently the published times of all the charts are reset to current
    time, since they're set from mtime and our git clone does not preserve
    mtimes.

    Go YAML's time parser seems insanely finnicky, so this has a bunch of
    really terrible datetime stuff here.
    """
    # Round Tripping seems to fail with index.yaml!
    safe_yaml = YAML(typ='safe')
    with open(os.path.join(repopath, 'index.yaml')) as f:
        index = safe_yaml.load(f)

    for _, entries in index['entries'].items():
        for e in entries:
            filename = e['urls'][0].split('/')[-1]
            last_modified_str = last_modified_date(filename, cwd=repopath)
            if last_modified_str:
                # If git has a last modified time, use it. We rely on git to give it to us
                # with an appropriate tz and the non dateutil.parser to parse it
                last_modified = dateutil.parser.parse(last_modified_str)
            else:
                # If we don't have this in git yet (so this is the latest chart release)
                # we still have to modify it, because apparently Go's YAML parser can not cope with
                # different yet valid time formats in the same document (?!?!). Just leaving this
                # be causes issues. We get mtime, do some twisting to get it to localtime so
                # isoformat will work
                filepath = os.path.join(repopath, filename)
                last_modified_ts = os.path.getmtime(filepath)
                last_modified = datetime.fromtimestamp(last_modified_ts).replace(tzinfo=dateutil.tz.tzlocal())
            e['created'] = last_modified.isoformat()

    # We have to manually set this again, because Go's YAML parser seems unable to cope with
    # multiple types of date formatting in the same doc, even if it was generated by go in the
    # first place!
    index['generated'] = datetime.utcnow().replace(tzinfo=dateutil.tz.tzutc()).isoformat()
    with open(os.path.join(repopath, 'index.yaml'), 'w') as f:
        safe_yaml.dump(index, f)


def publish_pages(name, git_repo, published_repo):
    version = last_modified_commit('.')
    checkout_dir = '{}-{}'.format(name, version)
    subprocess.check_call([
        'git', 'clone', '--no-checkout',
        'git@github.com:{}'.format(git_repo), checkout_dir],
    )
    subprocess.check_call(['git', 'checkout', 'gh-pages'], cwd=checkout_dir)
    subprocess.check_call([
        'helm', 'package', name,
        '--destination', '{}/'.format(checkout_dir)
    ])
    subprocess.check_call([
        'helm', 'repo', 'index', '.',
        '--url', published_repo
    ], cwd=checkout_dir)
    fixup_chart_index(checkout_dir)
    subprocess.check_call(['git', 'add', '.'], cwd=checkout_dir)
    subprocess.check_call([
        'git',
        'commit',
        '-m', '[{}] Automatic update for commit {}'.format(name, version)
    ], cwd=checkout_dir)
    subprocess.check_call(
        ['git', 'push', 'origin', 'gh-pages'],
        cwd=checkout_dir,
    )


def main():
    with open('chartpress.yaml') as f:
        safe_yaml = YAML(typ='safe')
        config = safe_yaml.load(f)

    argparser = argparse.ArgumentParser()

    argparser.add_argument('--commit-range', help='Range of commits to consider when building images')
    argparser.add_argument('--push', action='store_true')
    argparser.add_argument('--publish-chart', action='store_true')
    argparser.add_argument('--tag', default=None, help='Use this tag for images & charts')

    args = argparser.parse_args()

    for chart in config['charts']:
        value_mods = build_images(chart['imagePrefix'], chart['images'], args.tag, args.commit_range, args.push)
        build_values(chart['name'], value_mods)
        build_chart(chart['name'], args.tag)
        if args.publish_chart:
            publish_pages(chart['name'], chart['repo']['git'], chart['repo']['published'])

main()
