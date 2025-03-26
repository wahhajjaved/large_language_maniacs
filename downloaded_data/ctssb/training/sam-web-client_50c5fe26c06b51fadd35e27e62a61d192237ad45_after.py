#! /usr/bin/env python
import testbase
import unittest
import samweb_client
import samweb_cli
import time, socket, os

defname = 'one_enstore_file_test'

class TestStartProject(testbase.SamdevTest):

    def test_startProject_badargs(self):
        projectname = 'test-project-%s-%s-%s' % (socket.getfqdn(), os.getpid(), time.time())
        self.assertRaises(samweb_client.exceptions.Error, self.samweb.startProject, projectname)
        self.assertRaises(samweb_client.exceptions.Error, self.samweb.startProject, projectname, defname=defname, snapshot_id=10)

if __name__ == '__main__':
    unittest.main()
