"""Add new file move setting."""

from pathlib import Path
import click
from .config import Config


def add_new_config(regexp: str, path: str):
    config = Config()
    return config.add_regexp_path(path, regexp)
