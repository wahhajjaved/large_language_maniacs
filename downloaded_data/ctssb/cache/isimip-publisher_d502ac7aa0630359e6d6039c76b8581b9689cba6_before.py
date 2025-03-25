import logging
from pathlib import Path

from tqdm import tqdm

from .utils.checksum import write_checksum_file
from .utils.database import (init_database_session, insert_dataset,
                             insert_file, insert_resource, publish_dataset,
                             retrieve_datasets, unpublish_dataset,
                             update_attributes_view, update_resource,
                             update_tree, update_words_view)
from .utils.files import copy_files, delete_files, list_files, move_files
from .utils.json import write_json_file
from .utils.patterns import match_datasets
from .utils.thumbnails import write_thumbnail_file

logger = logging.getLogger(__name__)


def list_local(store):
    local_files = list_files(store.local_path, store.path, store.pattern,
                             include=store.include, exclude=store.exclude)
    for file_path in local_files:
        print(file_path)


def list_public(store):
    public_files = list_files(store.public_path, store.path, store.pattern,
                              include=store.include, exclude=store.exclude)
    for file_path in public_files:
        print(file_path)


def list_remote(store):
    remote_files = list_files(store.remote_path, store.path, store.pattern,
                              remote_dest=store.remote_dest, include=store.include, exclude=store.exclude)
    for file_path in remote_files:
        print(file_path)


def match_remote(store):
    remote_files = list_files(store.remote_path, store.path, store.pattern,
                              remote_dest=store.remote_dest, include=store.include, exclude=store.exclude)

    for dataset in match_datasets(store.pattern, store.remote_path, remote_files):
        dataset.validate(store.schema)
        for file in dataset.files:
            file.validate(store.schema)


def match_local(store):
    local_files = list_files(store.local_path, store.path, store.pattern,
                             include=store.include, exclude=store.exclude)

    for dataset in match_datasets(store.pattern, store.local_path, local_files):
        dataset.validate(store.schema)
        for file in dataset.files:
            file.validate(store.schema)


def match_public(store):
    public_files = list_files(store.public_path, store.path, store.pattern,
                              include=store.include, exclude=store.exclude)

    for dataset in match_datasets(store.pattern, store.public_path, public_files):
        dataset.validate(store.schema)
        for file in dataset.files:
            file.validate(store.schema)


def fetch_files(store):
    remote_files = list_files(store.remote_path, store.path, store.pattern,
                              remote_dest=store.remote_dest, include=store.include, exclude=store.exclude)

    t = tqdm(total=len(remote_files), desc='fetch_files'.ljust(18))
    for n in copy_files(store.remote_dest, store.remote_path, store.local_path, store.path, remote_files):
        t.update(n)


def write_thumbnails(store):
    if not store.datasets:
        local_files = list_files(store.local_path, store.path, store.pattern,
                                 include=store.include, exclude=store.exclude)
        store.datasets = match_datasets(store.pattern, store.local_path, local_files)

        for dataset in store.datasets:
            dataset.validate(store.schema)
            for file in dataset.files:
                file.validate(store.schema)

    for dataset in tqdm(store.datasets, desc='write_thumbnails'.ljust(18)):
        for file in dataset.files:
            write_thumbnail_file(file.abspath)


def write_jsons(store):
    if not store.datasets:
        local_files = list_files(store.local_path, store.path, store.pattern,
                                 include=store.include, exclude=store.exclude)
        store.datasets = match_datasets(store.pattern, store.local_path, local_files)

        for dataset in store.datasets:
            dataset.validate(store.schema)
            for file in dataset.files:
                file.validate(store.schema)

    for dataset in tqdm(store.datasets, desc='write_jsons'.ljust(18)):
        for file in dataset.files:
            write_json_file(file.abspath, file.json)


def write_checksums(store):
    if not store.datasets:
        local_files = list_files(store.local_path, store.path, store.pattern,
                                 include=store.include, exclude=store.exclude)
        store.datasets = match_datasets(store.pattern, store.local_path, local_files)

        for dataset in store.datasets:
            dataset.validate(store.schema)
            for file in dataset.files:
                file.validate(store.schema)

    for dataset in tqdm(store.datasets, desc='write_checksums'.ljust(18)):
        for file in dataset.files:
            write_checksum_file(file.abspath, file.path, file.checksum)


def ingest_datasets(store):
    if not store.datasets:
        local_files = list_files(store.local_path, store.path, store.pattern,
                                 include=store.include, exclude=store.exclude)
        store.datasets = match_datasets(store.pattern, store.local_path, local_files)

        for dataset in store.datasets:
            dataset.validate(store.schema)
            for file in dataset.files:
                file.validate(store.schema)

    session = init_database_session(store.database)

    for dataset in tqdm(store.datasets, desc='ingest_datasets'.ljust(18)):
        insert_dataset(session, store.version, dataset.name, dataset.path, dataset.size,
                       dataset.checksum, dataset.checksum_type, dataset.specifiers)

        for file in dataset.files:
            insert_file(session, store.version, file.dataset.path, file.uuid, file.name, file.path,
                        file.size, file.checksum, file.checksum_type, file.specifiers)

        session.commit()

    update_words_view(session)
    update_attributes_view(session)

    session.commit()


def publish_datasets(store):
    if not store.datasets:
        local_files = list_files(store.local_path, store.path, store.pattern,
                                 include=store.include, exclude=store.exclude)
        store.datasets = match_datasets(store.pattern, store.local_path, local_files)

    for dataset in store.datasets:
        dataset.validate(store.schema)
        for file in dataset.files:
            file.validate(store.schema)

            assert Path(file.abspath).is_file()
            assert Path(file.abspath).with_suffix('.json').is_file()
            assert Path(file.abspath).with_suffix('.png').is_file()

    session = init_database_session(store.database)

    for dataset in tqdm(store.datasets, desc='publish_datasets'.ljust(18)):
        publish_dataset(session, store.version, dataset.path)

        for file in dataset.files:
            move_files(store.local_path, store.public_path, [
                Path(file.abspath),
                Path(file.abspath).with_suffix('.png'),
                Path(file.abspath).with_suffix('.' + file.checksum_type),
                Path(file.abspath).with_suffix('.json')
            ])

        session.commit()

    update_tree(session)

    session.commit()


def archive_datasets(store):
    public_files = list_files(store.public_path, store.path, store.pattern,
                              include=store.include, exclude=store.exclude)

    session = init_database_session(store.database)

    if [store.path] == public_files:
        db_path = Path(store.path).parent.as_posix()
    else:
        db_path = store.path

    # remove datasets from db_datasets which have no files in public_files
    db_datasets = []
    for db_dataset in retrieve_datasets(session, db_path, public=True):
        if any([file.path in public_files for file in db_dataset.files]):
            db_datasets.append(db_dataset)

    for db_dataset in tqdm(db_datasets, desc='archive_datasets'.ljust(18)):
        dataset_version = unpublish_dataset(session, db_dataset.path)

        if dataset_version:
            archive_path = store.archive_path / dataset_version

            for file in db_dataset.files:
                files = []
                file_abspath = store.public_path / file.path
                if file_abspath.is_file():
                    files.append(file_abspath)
                for suffix in ['.png', '.' + file.checksum_type, '.json']:
                    if file_abspath.with_suffix(suffix).is_file():
                        files.append(file_abspath.with_suffix(suffix))

                move_files(store.public_path, archive_path, files)

        session.commit()

    update_tree(session)

    session.commit()


def register_doi(store):
    session = init_database_session(store.database)

    datasets = retrieve_datasets(session, store.path, public=True)

    for dataset in datasets:
        store.datacite['relatedIdentifiers'].append({
            'relationType': 'HasPart',
            'relatedIdentifier': store.isimip_data_url + '/datasets/' + dataset.id,
            'relatedIdentifierType': 'URL'
        })

    insert_resource(session, store.path, store.version, store.datacite, datasets)

    session.commit()


def update_doi(store):
    session = init_database_session(store.database)

    update_resource(session, store.path, store.version, store.datacite)

    session.commit()


def check(store):
    public_files = list_files(store.public_path, store.path, store.pattern,
                              include=store.include, exclude=store.exclude)
    datasets = match_datasets(store.pattern, store.public_path, public_files)

    for dataset in datasets:
        dataset.validate(store.schema)
        for file in dataset.files:
            file.validate(store.schema)

    session = init_database_session(store.database)

    # remove datasets from db_datasets which have no files in public_files
    db_datasets = []
    for db_dataset in retrieve_datasets(session, store.path, public=True):
        if any([file.path in public_files for file in db_dataset.files]):
            db_datasets.append(db_dataset)

    assert len(datasets) == len(db_datasets), \
        'Length mismatch {} != {}'.format(len(datasets), len(db_datasets))

    for dataset, db_dataset in zip(datasets, db_datasets):
        for file, db_file in zip(dataset.files, db_dataset.files):
            # check file
            assert file.path == db_file.path, \
                'Path mismatch {} != {} for file {}'.format(file.path, db_file.path, db_file.id)

            if file.uuid:
                assert str(file.uuid) == db_file.id, \
                    'UUID mismatch {} != {} for file {}'.format(file.uuid, db_file.id, db_file.id)

            # patch checksum_type in order to compute checksum with a non default checksum_type
            file.checksum_type = db_file.checksum_type
            assert file.checksum == db_file.checksum, \
                'Checksum mismatch {} != {} for file {}'.format(file.checksum, db_file.checksum, db_file.id)

        # check dataset
        assert dataset.path == db_dataset.path, \
            'Path mismatch {} != {} for dataset {}'.format(dataset.path, db_dataset.path, db_dataset.id)

        # patch checksum_type in order to compute checksum with a non default checksum_type
        dataset.checksum_type = db_file.checksum_type
        assert dataset.checksum == db_dataset.checksum, \
            'Checksum mismatch {} != {} for dataset {}'.format(dataset.checksum, db_dataset.checksum, db_dataset.id)


def clean(store):
    delete_files(store.local_path, store.path)


def update_index(store):
    session = init_database_session(store.database)

    update_tree(session)
    update_words_view(session)
    update_attributes_view(session)

    session.commit()
