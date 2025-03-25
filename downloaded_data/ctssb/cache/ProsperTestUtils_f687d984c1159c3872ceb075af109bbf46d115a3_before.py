"""validate prosper.test_utils.schema_utils"""
import datetime
import json
import jsonschema
import pathlib
from plumbum import local

import pytest
import helpers

import prosper.test_utils.schema_utils as schema_utils
import prosper.test_utils.exceptions as exceptions
import prosper.test_utils._version as _version

@pytest.fixture
def mongo_fixture(tmpdir):
    """helper for making testmode mongo context managers

    Args:
        tmpdir: PyTest magic

    Returns:
        schema_utils.MongoContextManager: in tinydb mode

    """
    mongo_context = schema_utils.MongoContextManager(
        helpers.TEST_CONFIG,
        _testmode_filepath=tmpdir,
        _testmode=True,
    )
    return mongo_context


class TestMongoContextManager:
    """validate expected behavior for MongoContextManager"""
    demo_data = [
        {'butts': True, 'many': 10},
        {'butts': False, 'many': 100},
    ]
    def test_mongo_context_testmode(self, tmpdir):
        """test with _testmode enabled"""
        mongo_context = schema_utils.MongoContextManager(
            helpers.TEST_CONFIG,
            _testmode=True,
            _testmode_filepath=tmpdir,
        )

        with mongo_context as t_mongo:
            t_mongo['test_collection'].insert(self.demo_data)

        with mongo_context as t_mongo:
            data = t_mongo['test_collection'].find_one({'butts': True})

        assert data['many'] == 10

    def test_mongo_context_prodmode(self):
        """test against real mongo"""
        if not helpers.can_connect_to_mongo(helpers.TEST_CONFIG):
            pytest.xfail('no mongo credentials')

        mongo_context = schema_utils.MongoContextManager(
            helpers.TEST_CONFIG,
        )

        with mongo_context as mongo:
            mongo['test_collection'].insert(self.demo_data)

        with mongo_context as _:
            data = mongo['test_collection'].find_one({'butts': True})

        assert data['many'] == 10


class TestFetchLatestSchema:
    """validate expected behavior for fetch_latest_schema()"""
    fake_schema_table = [
        {'schema_group':'test', 'schema_name':'fake.schema', 'version':'1.0.0',
         'schema':{'result':'NOPE'}},
        {'schema_group':'test', 'schema_name':'fake.schema', 'version':'1.1.0',
         'schema':{'result':'NOPE'}},
        {'schema_group':'test', 'schema_name':'fake.schema', 'version':'1.1.1',
         'schema':{'result':'YUP'}},
        {'schema_group':'not_test', 'schema_name':'fake.schema', 'version':'1.1.2',
         'schema':{'result':'NOPE'}},
    ]
    def test_fetch_latest_version(self, mongo_fixture):
        """try to find latest schema"""
        collection_name = 'fake_schema_table'

        with mongo_fixture as t_mongo:
            t_mongo[collection_name].insert(self.fake_schema_table)

        with mongo_fixture as t_mongo:
            latest_schema = schema_utils.fetch_latest_schema(
                'fake.schema',
                'test',
                t_mongo[collection_name]
            )

        assert latest_schema['schema'] == {'result': 'YUP'}
        assert latest_schema['version'] == '1.1.1'

    def test_fetch_latest_version_empty(self, mongo_fixture):
        """make sure function returns expected for no content"""
        collection_name = 'blank_schema_table'

        with pytest.warns(exceptions.FirstRunWarning):
            with mongo_fixture as t_mongo:
                latest_schema = schema_utils.fetch_latest_schema(
                    'fake.schema',
                    'test',
                    t_mongo[collection_name]
                )

        assert latest_schema['schema'] == {}
        assert latest_schema['version'] == '1.0.0'


class TestCompareSchemas:
    """validate expected behavior for compare_schemas()"""
    base_schema = helpers.load_schema_from_file('base_schema.json')
    minor_change = helpers.load_schema_from_file('minor_schema_change.json')
    major_removed_value = helpers.load_schema_from_file('major_items_removed.json')
    #major_values_changed = helpers.load_schema_from_file('major_values_changed.json')
    unhandled_diff = set(helpers.load_schema_from_file('unhandled_diff.json'))

    def test_compare_schemas_happypath(self):
        """make sure equivalence works as expected"""
        status = schema_utils.compare_schemas(
            self.base_schema,
            self.base_schema
        )

        assert status == schema_utils.Update.no_update

    def test_compare_schemas_minor(self):
        """make sure minor updates are tagged as such"""
        status = schema_utils.compare_schemas(
            self.base_schema,
            self.minor_change
        )

        assert status == schema_utils.Update.minor

    def test_compare_schemas_major(self):
        """make sure major updates are tagged as such"""
        status = schema_utils.compare_schemas(
            self.base_schema,
            self.major_removed_value
        )

        assert status == schema_utils.Update.major


    def test_compare_schemas_empty(self):
        """make sure empty case signals first-run"""
        status = schema_utils.compare_schemas(
            {},
            self.base_schema,
        )

        assert status == schema_utils.Update.first_run

    def test_compare_schemas_error(self):
        """make sure raises for really screwed up case"""
        pytest.xfail('compare_schemas raise case not working yet')
        with pytest.raises(exceptions.UnhandledDiff):
            status = schema_utils.compare_schemas(
                self.base_schema,
                self.unhandled_diff
            )


class TestBuildMetadata:
    """validate expected behavior for build_metadata()"""
    fake_metadata = {
        'schema_group': 'fake_group',
        'schema_name': 'fake_name',
        'update': datetime.datetime.utcnow().isoformat(),
        'version': '1.2.1',
        'schema': {'type': 'DONTCARE'},
    }
    dummy_schema = {'fake': 'DONTCARE'}

    def test_build_schema_no_update(self):
        """assert behavior for no_update"""
        metadata = schema_utils.build_metadata(
            self.dummy_schema,
            self.fake_metadata,
            schema_utils.Update.no_update,
        )
        assert metadata == self.fake_metadata

    def test_build_schema_first_run(self):
        """assert behavior for first_run"""
        metadata = schema_utils.build_metadata(
            self.dummy_schema,
            self.fake_metadata,
            schema_utils.Update.first_run,
        )

        assert metadata['schema'] == self.dummy_schema
        assert metadata['update'] != self.fake_metadata['update']
        assert metadata['version'] == self.fake_metadata['version']

    def test_build_schema_minor(self):
        """assert behavior for minor update"""
        metadata = schema_utils.build_metadata(
            self.dummy_schema,
            self.fake_metadata,
            schema_utils.Update.minor,
        )

        assert metadata['schema'] == self.dummy_schema
        assert metadata['update'] != self.fake_metadata['update']
        assert metadata['version'] == '1.2.2'

    def test_build_schema_major(self):
        """assert behavior for major update"""
        metadata = schema_utils.build_metadata(
            self.dummy_schema,
            self.fake_metadata,
            schema_utils.Update.major,
        )

        assert metadata['schema'] == self.dummy_schema
        assert metadata['update'] != self.fake_metadata['update']
        assert metadata['version'] == '1.3.0'

    def test_build_schema_badschema(self):
        """assert behavior for bad schema"""
        dummy_meta = {
            'schema': '',
            'version': '1.0.0',
            'update': datetime.datetime.utcnow().isoformat(),
        }

        with pytest.raises(jsonschema.exceptions.ValidationError):
            metadata = schema_utils.build_metadata(
                self.dummy_schema,
                dummy_meta,
                schema_utils.Update.first_run
            )


class TestDumpMajorUpdate:
    """validate expected behavior for dump_major_update()"""

    dummy_metadata1 = {'butts': 'yes'}
    dummy_metadata2 = {'butts': 'no'}
    def test_dump_major_udpate_empty(self, tmpdir):
        """validate system doesn't raise for empty data"""
        filename = tmpdir / 'empty.json'
        schema_utils.dump_major_update(
            self.dummy_metadata1,
            filename,
        )

        with open(str(filename), 'r') as tmp_fh:
            saved_data = json.load(tmp_fh)

        assert saved_data[0] == self.dummy_metadata1


    def test_dump_major_update_exists(self, tmpdir):
        """validate system appends new metadata to report"""
        filename = tmpdir / 'exists.json'
        with open(str(filename), 'w') as tmp_fh:
            json.dump([self.dummy_metadata1], tmp_fh)

        schema_utils.dump_major_update(
            self.dummy_metadata2,
            filename,
        )

        with open(str(filename), 'r') as tmp_fh:
            saved_data = json.load(tmp_fh)

        assert saved_data[1] == self.dummy_metadata2


class TestSchemaHelper:
    """validate expected behavior for schema_helper()"""
    base_sample = helpers.load_schema_from_file('base_sample.json')
    minor_sample = helpers.load_schema_from_file('minor_sample.json')
    major_sample = helpers.load_schema_from_file('major_sample.json')

    name = 'dummy_name'
    group = 'dummy_group'
    collection = 'TESTSCHEMA_'

    def do_the_thing(self, mongo_fixture, data, collection):
        """helper: run schema_utils.schema_helper"""
        schema_utils.schema_helper(
            data=data,
            data_source='DONTCARE',
            schema_name=self.name,
            schema_group=self.group,
            config=helpers.TEST_CONFIG,
            _collection_name=collection,
            _testmode=True,
            _dump_filepath=str(mongo_fixture._testmode_filepath),
        )

    def test_schema_helper_blank(self, mongo_fixture):
        """exercise first_run path"""
        collection = self.collection + __name__
        with pytest.warns(exceptions.FirstRunWarning):
            self.do_the_thing(
                mongo_fixture, self.base_sample, self.collection + __name__)

        with mongo_fixture as t_mongo:
            results = list(t_mongo[collection].find({}))

        assert results[0]['version'] == '1.0.0'

    def test_schema_helper_no_update(self, mongo_fixture):
        """exercise no_update path"""
        collection = self.collection + __name__
        with mongo_fixture as t_mongo:
            written_metadata = helpers.init_schema_database(
                context=t_mongo[collection],
                group_tag=self.group,
                name_tag=self.name,
                data=self.base_sample,
                version='1.1.0',
            )

        self.do_the_thing(
            mongo_fixture, self.base_sample, collection
        )

        with mongo_fixture as t_mongo:
            results = list(t_mongo[collection].find({}))

        assert results[0] == written_metadata

    def test_schema_helper_minor_update(self, mongo_fixture):
        """exercise minor_update path"""
        collection = self.collection + __name__
        with mongo_fixture as t_mongo:
            written_metadata = helpers.init_schema_database(
                context=t_mongo[collection],
                group_tag=self.group,
                name_tag=self.name,
                data=self.base_sample,
                version='1.1.0',
            )

        self.do_the_thing(
            mongo_fixture, self.minor_sample, collection
        )

        with mongo_fixture as t_mongo:
            updated_metadata = schema_utils.fetch_latest_schema(
                self.name, self.group, t_mongo[collection]
            )

        #sanitize outputs
        written_metadata.pop('_id', None)
        updated_metadata.pop('_id', None)

        assert updated_metadata != written_metadata
        assert updated_metadata['version'] == '1.1.1'

    def test_schema_helper_major_update(self, mongo_fixture):
        """exercise major_update path"""
        collection = self.collection + __name__
        with mongo_fixture as t_mongo:
            written_metadata = helpers.init_schema_database(
                context=t_mongo[collection],
                group_tag=self.group,
                name_tag=self.name,
                data=self.base_sample,
                version='1.1.0',
            )

        with pytest.raises(exceptions.MajorSchemaUpdate) as e:
            self.do_the_thing(
                mongo_fixture, self.major_sample, collection
            )
        with open(str(e.value), 'r') as major_fh:
            major_update_list = json.load(major_fh)

        todo_metadata = major_update_list[0]
        assert todo_metadata['version'] == '1.2.0'

        with mongo_fixture as t_mongo:
            updated_metadata = schema_utils.fetch_latest_schema(
                self.name, self.group, t_mongo[collection]
            )

        #sanitize outputs
        written_metadata.pop('_id', None)
        updated_metadata.pop('_id', None)

        assert updated_metadata['version'] == '1.1.0'

class TestCLI:
    """validate update-prosper-schemas behavior"""
    CLI_name = 'update-prosper-schemas'
    update_command = local['update-prosper-schemas']
    update_path = pathlib.Path(helpers.HERE) / 'dummy-schema-update.json'

    def test_cli_help(self):
        """make sure help command works"""
        output = self.update_command('-h')

    def test_cli_name(self):
        """make sure --version command works"""
        output = self.update_command('--version').strip()

        assert output == '{cli_name} {version}'.format(
            cli_name=self.CLI_name, version=_version.__version__
        )

    def test_cli_happypath(self, tmpdir):
        """dry-run CLI"""
        collection_name = 'TESTDUMMY'
        output = self.update_command(
            self.update_path,
            '--verbose',
            '--debug',
            '--local-dir={}'.format(tmpdir),
            '--collection={}'.format(collection_name),
        )

        mongo_context = schema_utils.MongoContextManager(
            config=helpers.ROOT_CONFIG,
            _testmode=True,
            _testmode_filepath=tmpdir,
        )
        mongo_context.database = 'TESTprosper'
        with mongo_context as t_mongo:
            results = t_mongo[collection_name].find_one({})

        with open(self.update_path, 'r') as update_fh:
            expected_results = json.load(update_fh)

        results.pop('_id')
        print(expected_results[0])
        print(results)
        assert results == expected_results[0]
