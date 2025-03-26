# -*- coding: utf-8 -*-
"""I/O utilities."""

from os import environ, listdir, name, path
from re import IGNORECASE, match
from subprocess import PIPE, call, run

from pype.util.cli import print_error


def run_interactive(cmdline, *args, **kwargs):
    """Call to an interactive shell."""
    if not isinstance(cmdline, str):
        cmdline = ' '.join(cmdline)
    try:
        return call(cmdline, shell=True, *args, **kwargs)
    except KeyboardInterrupt:
        pass


def run_and_get_output(cmdline, *args, **kwargs):
    """Run a cmdline non-interactive and returns both stdout and stderr."""
    if isinstance(cmdline, str):
        # For convenvience we split str-cmdlines into a list which is
        # required for run(). Note that this might not work due to
        # quoted arguments etc.
        cmdline = cmdline.split(' ')
    proc = run(cmdline, stdout=PIPE, stderr=PIPE, *args, **kwargs)
    return proc.stdout.decode('utf-8'), proc.stderr.decode('utf-8')


def open_with_default(filepath):
    """Open the given filepath with the OS'es default editor."""
    try:
        # Use open command
        run(['open', filepath], check=True)
    except Exception:
        # If not possible try to find $EDITOR or $VISUAL environment var
        editor = environ.get('EDITOR', None)
        if not editor:
            editor = environ.get('VISUAL', None)
        if not editor:
            print_error(
                'Open with default editor is not supported on this OS.')
            exit(1)
        run_interactive([editor, filepath])


def resolve_path(relative_path):
    """Resolve path including home folder expanding."""
    return path.abspath(path.expanduser(relative_path))


def get_immediate_subdirs(file_path, pattern=None, ignorecase=False):
    """Return the immediate subdirectories of a path."""
    return get_immediate_subfiles(
        file_path, pattern, ignorecase, is_file=False)


def get_immediate_subfiles(
        file_path, pattern=None, ignorecase=False, is_file=True):
    """Return the immediate subfiles of a path."""
    if not file_path:
        raise TypeError('file_path not provided.')

    files = []
    for file_name in listdir(file_path):
        path_is_dir = path.isdir(path.join(file_path, file_name))
        if (path_is_dir and is_file) or (not path_is_dir and not is_file):
            continue
        if pattern:
            if ignorecase and match(pattern, file_name, IGNORECASE):
                files.append(file_name)
            elif match(pattern, file_name):
                files.append(file_name)
            continue
        files.append(file_name)
    files.sort()
    return files


def clear_screen():
    """Clear terminal window."""
    call('clear' if name == 'posix' else 'cls')
