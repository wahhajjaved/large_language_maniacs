"""Config file manager.
"""

from pathlib import Path
import json
import click
import os


class NoConfigFileException(Exception):
    pass


def is_valid_glob_path(glob_and_path):
    if 'path' not in glob_and_path:
        return False
    if 'glob' not in glob_and_path:
        return False
    return True


def get_config_path() -> Path:
    config_file_name = '.cleanrc'
    env_config_raw_path = os.getenv('CLEANRC_PATH')
    if env_config_raw_path is None:
        default_config_path = Path.home() / config_file_name
    else:
        default_config_path = Path(env_config_raw_path)
        if default_config_path.is_dir():
            default_config_path /= config_file_name
        if not default_config_path.is_file():
            raise NoConfigFileException('{}'.format(str(default_config_path)))
    return default_config_path


class Config:
    """Config file manager class.

    Returns:
        Config -- config file instance

    """

    def __init__(self, config_path=None):
        """initialize config class.

        Keyword Arguments:
            config_path {Path} -- set config file path (default: {default_config_path})
        """

        if config_path is None:
            config_path = get_config_path()
        self.config_path = config_path
        if not self.config_path.is_file():
            if self.config_path.exists():
                click.echo(
                    'Can\'t create file. Same name something is exist. Please check your home\'s {}.'.
                    format(str(config_path)))
                exit(1)
            self.create_new_config_file()

        self.load_file()

    def add_glob_path(self, glob: str, path: str) -> bool:
        if self._is_contain_same_config(glob, path):
            return False
        self.config['path'].append({'glob': glob, 'path': path})
        self.save_file()
        return True

    def _is_contain_same_config(self, glob: str, path: str) -> bool:
        return not any(x['path'] == path and x['glob'] == glob
                       for x in self.config['path'])

    def delete_glob_path(self, id: int) -> dict:
        """Delete registered glob and path by id.

        Arguments:
            id {int} -- the glob and path's id which you want to delete.

        Returns:
            {{'glob': string, 'path': string}} -- the setting you destroy.

        """
        deleted_path = self.config['path'].pop(id)
        self.save_file()
        return deleted_path

    def list_glob_path(self) -> list:
        return [i for i in self.config['path'] if is_valid_glob_path(i)]

    def save_file(self):
        with self.config_path.open(mode='w', encoding='utf_8') as f:
            f.write(json.dumps(self.config))

    def create_new_config_file(self):
        with self.config_path.open(mode='w', encoding='utf_8') as f:
            self.config = {'path': []}
            f.write(json.dumps(self.config))

    def get_config(self):
        return self.config

    def load_file(self):
        with self.config_path.open(encoding='utf_8') as f:
            config_text = f.read()
            self.config = json.loads(config_text)
