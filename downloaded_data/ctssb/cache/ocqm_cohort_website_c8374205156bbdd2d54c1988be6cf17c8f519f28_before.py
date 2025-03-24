import os
from .. import paths


def test_module_path():
    assert 'ocqm_cohort_website' in paths.get_module_path()


def test_theme_path():
    assert 'ocqm_cohort_website/theme' in paths.get_theme_path()


def test_static_path():
    assert 'ocqm_cohort_website/theme/media' in paths.get_static_path()


def test_locale_path():
    assert 'ocqm_cohort_website/locale' in paths.get_locale_path()


def test_example_path():
    assert 'ocqm_cohort_website/example' in paths.get_example_path()


def test_copy_files(temp_directory):
    dirs = [
        os.path.join(temp_directory, 'parent'),
        os.path.join(temp_directory, 'parent', 'child'),
    ]
    for path in dirs:
        os.mkdir(path)

    files = [
        os.path.join(temp_directory, 'parent', 'parent.txt'),
        os.path.join(temp_directory, 'parent', 'child', 'child.txt')
    ]
    for path in files:
        open(path, 'a').close()  # touch file

    clone_dir = os.path.join(temp_directory, 'clone')
    paths.copy_files(
        os.path.join(temp_directory, 'parent'),
        os.path.join(temp_directory, 'clone')
    )

    assert os.listdir(clone_dir) == ['child', 'parent.txt']
    assert os.listdir(os.path.join(clone_dir, 'child')) == ['child.txt']


def test_ensure_directory(temp_directory):
    directory = os.path.join(temp_directory, 'test')
    assert not os.path.exists(directory)

    paths.ensure_directory(directory)
    assert os.path.exists(directory)

    paths.ensure_directory(directory)
    assert os.path.exists(directory)


def test_switch_paths(temp_directory):
    os.mkdir('test')

    assert os.getcwd().endswith(temp_directory)

    with paths.switch_path('test'):
        assert os.getcwd().endswith('test')

    assert os.getcwd().endswith(temp_directory)
