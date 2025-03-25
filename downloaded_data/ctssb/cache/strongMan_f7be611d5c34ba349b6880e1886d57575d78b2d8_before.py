from django.test import TestCase
from strongMan.apps.vici.wrapper.wrapper import ViciWrapper
from strongMan.apps.vici.wrapper.exception import ViciSocketException
from strongMan.apps.connections.models import Authentication, Connection, Secret


class ViciWrapperTest(TestCase):

    def setUp(self):
        self.vici_wrapper = ViciWrapper()
        self.vici_wrapper.session.clear_creds()
        self.vici_wrapper.unload_all_connections()
        self.connection = Connection(profile='rw', auth='pubkey', version=1)
        self.connection.save()
        Authentication(name='local-1', peer_id='home', auth='pubkey', local=self.connection).save()

    def test_vici_socket(self):
        with self.assertRaises(ViciSocketException):
            ViciWrapper(socket_path="/")

    def test_vici_get_verion(self):
        version = self.vici_wrapper.get_version()
        self.assertTrue(bool(version))

    def test_vici_get_plugin(self):
        plugins = self.vici_wrapper.get_plugins()
        self.assertTrue(bool(plugins))

    def test_vici_get_status(self):
        status = self.vici_wrapper.get_status()
        self.assertTrue(bool(status))

    def test_vici_get_certificates_empty(self):
        certificates = self.vici_wrapper.get_certificates()
        self.assertFalse(bool(certificates))

    def test_vici_load_connection(self):
        self.assertEquals(0, self.vici_wrapper.get_connections_names().__len__())
        self.vici_wrapper.load_connection(self.connection.dict())

        self.assertEquals(1,self.vici_wrapper.get_connections_names().__len__())

    def test_vici_is_active(self):
        self.assertEquals(0, self.vici_wrapper.get_connections_names().__len__())
        self.vici_wrapper.load_connection(self.connection.dict())
        self.assertEquals(1,self.vici_wrapper.get_connections_names().__len__())
        self.assertTrue(self.vici_wrapper.is_connection_active(self.connection.profile))

    def test_vici_unload_connection(self):
        self.assertEquals(0, self.vici_wrapper.get_connections_names().__len__())
        self.vici_wrapper.load_connection(self.connection.dict())
        self.assertEquals(1,self.vici_wrapper.get_connections_names().__len__())
        self.vici_wrapper.unload_connection(self.connection.profile)
        self.assertEquals(0, self.vici_wrapper.get_connections_names().__len__())

    def test_vici_unload_all_connection(self):
        self.assertEquals(0, self.vici_wrapper.get_connections_names().__len__())
        self.vici_wrapper.load_connection(self.connection.dict())
        self.connection.profile = 'test'
        self.vici_wrapper.load_connection(self.connection.dict())
        self.assertEquals(2, self.vici_wrapper.get_connections_names().__len__())
        self.vici_wrapper.unload_all_connections()
        self.assertEquals(0, self.vici_wrapper.get_connections_names().__len__())

    def test_vici_get_connection_names(self):
        self.vici_wrapper.load_connection(self.connection.dict())
        self.assertEquals(self.vici_wrapper.get_connections_names()[0], 'rw')

