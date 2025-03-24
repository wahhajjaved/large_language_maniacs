import unittest
from monitor import checker,rest
import json
from time import time

class TestMethods(unittest.TestCase):

    # def test_check(self):
    #     self.check = checker.CheckerService()
    #     self.check.start_monitors()

    def test_rest(self):
        self.rest = rest.RestService()

        check_dict = {"name": "Foo", "address": "127.0.0.1", "port": 80, "alive": False, "since": int(time()), "enabled": True, "id": 1}
        check_dict_clean = {"name": "Foo", "address": "127.0.0.1", "port": 80, "alive": False, "since": int(time()), "id": 1}
        check_dict_update = {"name": "Foo Updated", "address": "127.0.0.2", "port": 88, "alive": False, "since": int(time()), "id": 1}

        self.assertDictEqual(self.rest.check_insert_monitor(check_dict),check_dict)
        self.assertDictEqual(self.rest.prepare_monitor(check_dict),check_dict_clean)
        self.assertTrue(self.rest.get_max_monitor_id() == 0)

        self.rest.insert_monitor(check_dict)

        self.assertDictEqual(json.loads(self.rest.get_check_status(1)), check_dict_clean)
        self.assertDictEqual({"items": [check_dict_clean]},json.loads(self.rest.get_check_status(-1)))
        self.assertListEqual([check_dict_clean],self.rest.get_all_checks())

        self.assertDictEqual({"name": "Foo", "address": "127.0.0.1", "port": 80}, self.rest.check_update_monitor(check_dict))
        self.assertDictEqual(check_dict_clean,self.rest.update_monitor(check_dict_update,1))
        self.assertDictEqual(json.loads(self.rest.get_check_status(1)), check_dict_update)

        self.assertTrue(self.rest.get_max_monitor_id()==1)

        self.assertTrue(self.rest.delete_monitor(1)==1)

        self.assertTrue(self.rest.get_max_monitor_id() == 0)

if __name__ == '__main__':
    unittest.main()