# -*- coding: utf-8 -*-
"""
Convert the YAML translation files into a single JSON file.
"""

import os
import yaml
import json
import shutil
from git import Repo

def build_translations(output_file):
    status = True
    data = {}

    for root, dirs, files in os.walk('translations'):
        key = os.path.basename(root)
        if (key == 'translations'):
            continue
        data[key] = {}
        for file in files:
            file_parts = os.path.splitext(file)
            no_extension = file_parts[0]
            extension = file_parts[1]
            if (extension == '.yml'):
                with open(os.path.join(root, file), 'r') as stream:
                    try:
                        yamldata = (yaml.load(stream))
                        data[key][no_extension] = yamldata
                    except Exception as exc:
                        print (exc)

    json_dir = '_site'
    if not os.path.exists(json_dir):
        os.makedirs(json_dir, exist_ok=True)
    json_path = os.path.join(json_dir, output_file)
    with open(json_path, 'w') as fp:
        json.dump(data, fp, sort_keys=True)

    return status

def main():
    status = True

    data = {}

    # First output the latest code.
    build_translations('translations.json')

    # Loop through all the past Git tags.
    repo = Repo(os.getcwd())
    # Save the current branch for later.
    branch = repo.active_branch.name
    for tag in repo.tags:
        # Switch to the tag and build another version.
        repo.git.checkout(tag)
        build_translations('translations-' + str(tag) + '.json')
    # Go back to the current branch.
    repo.git.checkout(branch)

    # Copy any other public files into the _site folder for Github Pages.
    src_files = os.listdir('public')
    for file_name in src_files:
        full_file_name = os.path.join(src, file_name)
        if (os.path.isfile(full_file_name)):
            shutil.copy(full_file_name, '_site')

    return status

if __name__ == '__main__':
    status = main()
    if(not status):
        raise RuntimeError("Failed translation build")
    else:
        print("Success")
