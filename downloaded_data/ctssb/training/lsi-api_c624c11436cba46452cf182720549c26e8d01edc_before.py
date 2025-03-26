#!/usr/bin/env python

import json
import mock
import unittest

from tests_helpers import add_top_srcdir_to_path

add_top_srcdir_to_path()

import storrest
import storrest.storcli
import storrest.storrest


class StorrestTest(unittest.TestCase):
    api_version = 'v0.5'
    dummy_data = {'foo': 'bar'}
    dummy_error_code = 42
    dummy_error_msg = 'FooBar'

    def setUp(self):
        super(StorrestTest, self).setUp()
        self.app = storrest.storrest.app

    def prepare(self, mock_object, positive=True):
        mock_object.return_value = self.dummy_data
        if not positive:
            mock_object.side_effect = storrest.storcli.StorcliError(
                msg=self.dummy_error_msg,
                error_code=self.dummy_error_code)

    def verify_reply(self, request, positive=True):
        reply = json.loads(request.data)
        if positive:
            self.assertEqual(reply['data'], self.dummy_data)
        else:
            self.assertEqual(reply['error_code'], self.dummy_error_code)
            self.assertEqual(reply['error_message'], self.dummy_error_msg)

    @mock.patch.object(storrest.storcli.Storcli, 'controllers')
    def test_controllers(self, mock_obj):
        mock_obj.__get__ = mock.Mock(return_value=self.dummy_data)
        url = '/{0}/controllers'.format(self.api_version)
        request = self.app.request(url)
        self.verify_reply(request)
        mock_obj.assert_called_once()

    @mock.patch.object(storrest.storcli.Storcli, 'controller_details')
    def test_controller_details(self, mock_obj):
        mock_obj.return_value = self.dummy_data
        controller_id = '0'
        request = self.app.request('/{0}/controllers/{1}'.
                                   format(self.api_version, controller_id))
        mock_obj.assert_called_once_with(controller_id)
        self.verify_reply(request)

    @mock.patch.object(storrest.storcli.Storcli, 'physical_drives')
    def test_physical_drives(self, mock_obj):
        mock_obj.return_value = self.dummy_data
        controller_id = '0'
        request = self.app.request('/{0}/controllers/{1}/physicaldevices'.
                                   format(self.api_version, controller_id))
        mock_obj.assert_called_once_with(controller_id=controller_id)
        self.verify_reply(request)

    @mock.patch.object(storrest.storcli.Storcli, 'virtual_drives')
    def test_virtual_drives(self, mock_obj):
        mock_obj.return_value = self.dummy_data
        controller_id = '0'
        request = self.app.request('/{0}/controllers/{1}/virtualdevices'.
                                   format(self.api_version, controller_id))
        mock_obj.assert_called_once_with(controller_id=controller_id)
        self.verify_reply(request)

    @mock.patch.object(storrest.storcli.Storcli, 'virtual_drive_details')
    def test_virtual_drive_details(self, mock_obj):
        mock_obj.return_value = self.dummy_data
        controller_id = 0
        virtual_drive_id = 0
        url = '/{0}/controllers/{1}/virtualdevices/{2}'.format(
            self.api_version,
            controller_id,
            virtual_drive_id)
        request = self.app.request(url)
        self.verify_reply(request)
        mock_obj.assert_called_once_with(controller_id, virtual_drive_id)

    def _create_virtual_drive(self, mock_obj, positive=True):
        self.prepare(mock_obj, positive=positive)
        controller_id = 0
        url = '/{0}/controllers/{1}/virtualdevices'.format(
            self.api_version,
            controller_id)
        data = {
            'drives': [{'controller_id': 0, 'enclosure': 4, 'slot': 0},
                       {'controller_id': 0, 'enclosure': 4, 'slot': 1}],
            'raid_level': '1',
            'name': 'test_r1'
        }
        request = self.app.request(url, method='POST', data=json.dumps(data))
        self.verify_reply(request, positive=positive)
        param_names = ('raid_level', 'spare_drives', 'strip_size',
                       'name', 'read_ahead', 'write_cache', 'io_policy',
                       'ssd_caching')
        params = dict([(k, data.get(k)) for k in param_names])
        mock_obj.assert_called_once_with(data['drives'], **params)

    @mock.patch.object(storrest.storcli.Storcli, 'create_virtual_drive')
    def test_create_virtual_drive(self, mock_obj):
        self._create_virtual_drive(mock_obj)

    @mock.patch.object(storrest.storcli.Storcli, 'create_virtual_drive')
    def test_create_virtual_drive_fail(self, mock_obj):
        self._create_virtual_drive(mock_obj, positive=False)

    def _create_virtual_drive_missing_params(self, mock_obj, raid_type=None):
        controller_id = 0
        url = '/{0}/controllers/{controller_id}/virtualdevices'
        url = url.format(self.api_version, controller_id=controller_id)
        if raid_type:
            url += '/{0}'.format(raid_type)
        stupid_data = {'foo': 'bar', 'blah': 'baz'}
        request = self.app.request(url,
                                   method='POST',
                                   data=json.dumps(stupid_data))
        reply = json.loads(request.data)
        self.assertEqual(reply['error_code'], 400)
        self.assertFalse(mock_obj.called)

    @mock.patch.object(storrest.storcli.Storcli, 'create_virtual_drive')
    def test_create_virtual_drive_missing_params(self, mock_obj):
        self._create_virtual_drive_missing_params(mock_obj)

    @mock.patch.object(storrest.storcli.Storcli, 'create_virtual_drive')
    def test_create_nytrocache_missing_params(self, mock_obj):
        self._create_virtual_drive_missing_params(mock_obj,
                                                  raid_type='nytrocache')

    @mock.patch.object(storrest.storcli.Storcli, 'create_virtual_drive')
    def test_create_cachecade_missing_params(self, mock_obj):
        self._create_virtual_drive_missing_params(mock_obj,
                                                  raid_type='cachecade')

    @mock.patch.object(storrest.storcli.Storcli, 'create_virtual_drive')
    def test_create_virtual_drive_invalid_json(self, mock_obj):
        controller_id = 0
        url = '/{0}/controllers/{controller_id}/virtualdevices'
        url = url.format(self.api_version, controller_id=controller_id)
        request = self.app.request(url,
                                   method='POST',
                                   data='@choke it@')
        reply = json.loads(request.data)
        self.assertEqual(reply['error_code'], 400)
        self.assertFalse(mock_obj.called)

    @mock.patch.object(storrest.storcli.Storcli, 'delete_virtual_drive')
    def test_delete_virtual_drive(self, mock_obj):
        mock_obj.return_value = self.dummy_data
        controller_id = 0
        virtual_drive_id = 0
        url = '/{0}/controllers/{1}/virtualdevices/{2}'.format(
            self.api_version,
            controller_id,
            virtual_drive_id)
        request = self.app.request(url, method='DELETE')
        self.verify_reply(request)
        mock_obj.assert_called_once_with(str(controller_id),
                                         str(virtual_drive_id),
                                         force=True)

    @mock.patch.object(storrest.storcli.Storcli, 'delete_virtual_drive')
    def test_delete_all_virtual_drives(self, mock_obj):
        self.prepare(mock_obj)
        controller_id = 0
        url = '/{0}/controllers/{controller_id}/virtualdevices'
        url = url.format(self.api_version, controller_id=controller_id)
        request = self.app.request(url, method='DELETE')
        self.verify_reply(request)
        mock_obj.assert_called_once_with(controller_id,
                                         'all',
                                         force=True)

    @mock.patch.object(storrest.storcli.Storcli, 'update_virtual_drive')
    def test_update_virtual_drive(self, mock_obj):
        mock_obj.return_value = self.dummy_data
        controller_id = 0
        virtual_drive_id = 0
        url = '/{0}/controllers/{1}/virtualdevices/{2}'.format(
            self.api_version,
            controller_id,
            virtual_drive_id)
        data = {
            'name': 'foo',
            'read_ahead': True,
            'write_cache': 'wb',
            'io_policy': 'direct',
            'ssd_caching': True
        }
        request = self.app.request(url, method='POST', data=json.dumps(data))
        self.verify_reply(request)
        mock_obj.assert_called_once_with(controller_id,
                                         virtual_drive_id,
                                         **data)

    def _hotspare_url(self, controller_id=None, enclosure=None, slot=None):
        url = '/{0}/controllers/{controller_id}/physicaldevices' \
            '/{enclosure}/{slot}/hotspare'
        return url.format(self.api_version,
                          controller_id=controller_id,
                          enclosure=enclosure,
                          slot=slot)

    def _add_hotspare_test(self, mock_obj, virtual_drives=None):
        mock_obj.return_value = self.dummy_data
        controller_id = 0
        enclosure = 42
        slot = 100500
        data = {'virtual_drives': virtual_drives}
        data_json = json.dumps(data) if virtual_drives else None
        url = self._hotspare_url(controller_id, enclosure, slot)
        request = self.app.request(url, method='POST', data=data_json)
        self.verify_reply(request)
        mock_obj.assert_called_once_with(virtual_drives,
                                         controller_id=str(controller_id),
                                         enclosure=str(enclosure),
                                         slot=str(slot))

    @mock.patch.object(storrest.storcli.Storcli, 'add_hotspare_drive')
    def test_add_global_hotspare_drive(self, mock_obj):
        self._add_hotspare_test(mock_obj)

    @mock.patch.object(storrest.storcli.Storcli, 'add_hotspare_drive')
    def test_add_dedicated_hotspare_drive(self, mock_obj):
        self._add_hotspare_test(mock_obj, virtual_drives=[1, 2, 3])

    @mock.patch.object(storrest.storcli.Storcli, 'delete_hotspare_drive')
    def test_delete_hotspare_drive(self, mock_obj):
        mock_obj.return_value = self.dummy_data
        controller_id = 0
        enclosure = 42
        slot = 100500
        url = self._hotspare_url(controller_id, enclosure, slot)
        request = self.app.request(url, method='DELETE')
        self.verify_reply(request)
        mock_obj.assert_called_once_with(controller_id=str(controller_id),
                                         enclosure=str(enclosure),
                                         slot=str(slot))

    def _nytorcache_view(self, mock_obj, raid_type):
        self.prepare(mock_obj)
        params = {
            'controller_id': '0',
            'raid_type': raid_type
        }
        url = '/{0}/controllers/{controller_id}/virtualdevices/{raid_type}'
        request = self.app.request(url.format(self.api_version, **params))
        self.verify_reply(request)
        mock_obj.assert_called_once_with(params['controller_id'],
                                         raid_type=raid_type)

    @mock.patch.object(storrest.storcli.Storcli, 'virtual_drives')
    def test_nytrocache_view(self, mock_obj):
        self._nytorcache_view(mock_obj, 'nytrocache')

    @mock.patch.object(storrest.storcli.Storcli, 'virtual_drives')
    def test_cachecade_view(self, mock_obj):
        self._nytorcache_view(mock_obj, 'cachecade')

    def _nytrocache_details(self, mock_obj, raid_type):
        self.prepare(mock_obj)
        params = {
            'controller_id': '0',
            'raid_type': raid_type,
            'virtual_drive_id': '1',
        }
        url = '/{0}/controllers/{controller_id}/virtualdevices' \
            '/{raid_type}/{virtual_drive_id}'
        url = url.format(self.api_version, **params)
        request = self.app.request(url)
        self.verify_reply(request)
        mock_obj.assert_called_once_with(params['controller_id'],
                                         params['virtual_drive_id'],
                                         raid_type=raid_type)

    @mock.patch.object(storrest.storcli.Storcli, 'virtual_drive_details')
    def test_nytrocache_details(self, mock_obj):
        self._nytrocache_details(mock_obj, 'nytrocache')

    @mock.patch.object(storrest.storcli.Storcli, 'virtual_drive_details')
    def test_cachecade_details(self, mock_obj):
        self._nytrocache_details(mock_obj, 'cachecade')

    def _nytrocache_create(self, mock_obj, raid_type):
        self.prepare(mock_obj)
        controller_id = 0
        enclosure = 252
        data = {
            'raid_level': '1',
            'raid_type': raid_type,
            'name': 'FooBar',
            'drives': [{'controller_id': controller_id,
                        'enclosure': enclosure,
                        'slot': 0},
                       {'controller_id': controller_id,
                        'enclosure': enclosure,
                        'slot': 1}]
        }
        url = '/{0}/controllers/{controller_id}/virtualdevices/{raid_type}'
        url = url.format(self.api_version,
                         controller_id=controller_id,
                         raid_type=raid_type)
        request = self.app.request(url,
                                   method='POST',
                                   data=json.dumps(data))
        self.verify_reply(request)
        mock_obj.assert_called_once_with(data['drives'],
                                         raid_level=data['raid_level'],
                                         raid_type=data['raid_type'],
                                         name=data.get('name'),
                                         write_cache=data.get('write_cache'))

    @mock.patch.object(storrest.storcli.Storcli, 'create_virtual_drive')
    def test_create_nytrocache(self, mock_obj):
        self._nytrocache_create(mock_obj, 'nytrocache')

    @mock.patch.object(storrest.storcli.Storcli, 'create_virtual_drive')
    def test_create_cachecade(self, mock_obj):
        self._nytrocache_create(mock_obj, 'cachecade')

    def _nytrocache_delete(self, mock_obj, raid_type):
        self.prepare(mock_obj)
        url = '/{0}/controllers/{controller_id}/virtualdevices' \
            '/{raid_type}/{virtual_drive_id}'
        controller_id = '0'
        virtual_drive_id = '1'
        url = url.format(self.api_version,
                         controller_id=controller_id,
                         raid_type=raid_type,
                         virtual_drive_id=virtual_drive_id)
        request = self.app.request(url, method='DELETE')
        self.verify_reply(request)
        mock_obj.assert_called_once_with(controller_id,
                                         virtual_drive_id,
                                         raid_type=raid_type)

    @mock.patch.object(storrest.storcli.Storcli, 'delete_virtual_drive')
    def test_nytrocache_delete(self, mock_obj):
        self._nytrocache_delete(mock_obj, 'nytrocache')

    @mock.patch.object(storrest.storcli.Storcli, 'delete_virtual_drive')
    def test_cachecade_delete(self, mock_obj):
        self._nytrocache_delete(mock_obj, 'cachecade')

    def _warpdrive_create(self, mock_obj, overprovision=None):
        self.prepare(mock_obj)
        controller_id = '0'
        data = {}
        if overprovision is not None:
            data['overprovision'] = overprovision
        url = '/{0}/controllers/{controller_id}/virtualdevices/warpdrive'
        url = url.format(self.api_version, controller_id=controller_id)
        json_data = json.dumps(data) if overprovision else None
        request = self.app.request(url, method='POST', data=json_data)
        self.verify_reply(request)
        mock_obj.assert_called_once_with(controller_id,
                                         overprovision=overprovision)

    @mock.patch.object(storrest.storcli.Storcli, 'create_warp_drive_vd')
    def test_warpdrive_create_cap(self, mock_obj):
        self._warpdrive_create(mock_obj, overprovision='cap')

    @mock.patch.object(storrest.storcli.Storcli, 'create_warp_drive_vd')
    def test_warpdrive_create(self, mock_obj):
        self._warpdrive_create(mock_obj)

if __name__ == '__main__':
    unittest.main()
