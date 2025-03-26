# -*- coding: utf-8 -*-
import logging
import httplib as http

from framework.exceptions import HTTPError

from framework.flask import request
from website.project.decorators import must_be_contributor_or_public, must_have_addon
from website.util import rubeus

from website.addons.dropbox.client import get_node_client
from website.addons.dropbox.utils import (
    clean_path, metadata_to_hgrid, build_dropbox_urls
)

logger = logging.getLogger(__name__)
debug = logger.debug


@must_be_contributor_or_public
@must_have_addon('dropbox', 'node')
def dropbox_hgrid_data_contents(node_addon, auth, **kwargs):
    """Return the Rubeus/HGrid-formatted response for a folder's contents.

    Takes optional query parameters `foldersOnly` (only return folders) and
    `includeRoot` (include the root folder).
    """
    # No folder, just return an empty list of data
    if node_addon.folder is None and not request.args.get('foldersOnly'):
        return {'data': []}
    node = node_addon.owner
    path = kwargs.get('path',  '')
    permissions = {
        'edit': node.can_edit(auth) and not node.is_registration,
        'view': node.can_view(auth)
    }
    client = get_node_client(node)
    metadata = client.metadata(path)
    # Raise error if folder was deleted
    if metadata.get('is_deleted'):
        raise HTTPError(http.NOT_FOUND)
    contents = metadata['contents']
    if request.args.get('foldersOnly'):
        contents = [metadata_to_hgrid(file_dict, node, permissions) for
                    file_dict in contents if file_dict['is_dir']]
    else:
        contents = [metadata_to_hgrid(file_dict, node, permissions) for
                    file_dict in contents]
    if request.args.get('includeRoot'):
        root = {'kind': rubeus.FOLDER, 'path': '/', 'name': '/ (Full Dropbox)'}
        contents.insert(0, root)
    return contents


def dropbox_addon_folder(node_settings, auth, **kwargs):
    """Return the Rubeus/HGrid-formatted response for the root folder only."""
    # Quit if node settings does not have authentication
    if not node_settings.has_auth:
        return None
    node = node_settings.owner
    path = clean_path(node_settings.folder)
    root = rubeus.build_addon_root(
        node_settings=node_settings,
        name=node_settings.folder,
        permissions=auth,
        nodeUrl=node.url,
        nodeApiUrl=node.api_url,
        urls={
            'upload': node.api_url_for('dropbox_upload',
                path=path),
            'fetch': node.api_url_for('dropbox_hgrid_data_contents',
                path=path)
        }
    )
    return [root]
