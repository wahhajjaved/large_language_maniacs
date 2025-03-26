"""Symbolic link storage broker module."""

import sys
import os

import click

try:
    import Tkinter as tk
except ImportError:
    try:
        import tkinter as tk
    except ImportError:
        pass

try:
    import tkFileDialog
except ImportError:
    pass

from dtoolcore.storagebroker import DiskStorageBroker


def _get_data_directory():
    try:
        root = tk.Tk()
        root.withdraw()
        data_directory = tkFileDialog.askdirectory()
    except:
        data_directory = click.prompt(
            "Please enter the path to the data directory",
            type=click.Path(
                exists=True,
                file_okay=False,
                resolve_path=False
            )
        )
    if data_directory is "":
        sys.exit()

    return data_directory


class SymLinkStorageBroker(DiskStorageBroker):
    """SymLinkStorageBroker class."""

    key = "symlink"

    def __init__(self, uri, config_path=None):
        super(SymLinkStorageBroker, self).__init__(uri, config_path)
        self._essential_subdirectories = [
            self._dtool_abspath,
            self._overlays_abspath
        ]

    def create_structure(self, get_data_dir_func=_get_data_directory):
        super(SymLinkStorageBroker, self).create_structure()
        data_directory = get_data_dir_func()
        os.symlink(data_directory, self._data_abspath)

    def put_item(self, fpath, relpath):
        raise(NotImplementedError())
