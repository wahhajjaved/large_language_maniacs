import unittest
from spinn_storage_handlers.file_data_reader import FileDataReader


class TestFileDataReader(unittest.TestCase):
    def test_ff(self, tmpdir):
        p = tmpdir.mkdir("spinn_storage_handlers").join("data.txt")
        p.write_binary("ABcd1234")
        fdr = FileDataReader(p)
        self.assertIsNotNone(fdr)
        self.assertEqual(len(fdr.readall()), 8)
