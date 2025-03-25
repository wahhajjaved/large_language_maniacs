# -*-coding: utf-8 -*-
import os
import codecs
import cdb
import subprocess

LFS_DEFAULT = 2.5 * (1024**3)  # 2.5GB(file)-> about 3.3GB(cdb)


class CDB_Writer(object):
    def __init__(self, dbname, keyMapFile, limit_file_size=LFS_DEFAULT,
                 fetch=1000000, encoding='utf-8'):
        # the options.
        self.dbname = dbname
        # used by CDB_Reader to decide which cdb includes the query key
        self.keyMapFile = keyMapFile
        self.limit_file_size = limit_file_size
        # determines how often to check if current cdb size exceeds the limit
        self.fetch = fetch
        self.record_counter = 0
        self.num_of_cdbs = 0
        self.encoding = encoding

        dbname = "{}.{}".format(self.dbname, self.num_of_cdbs)
        print "processing {}".format(dbname)
        dbname_tmp = dbname + ".tmp"
        self.tmpfile = dbname_tmp
        self.cdb = cdb.cdbmake(dbname, dbname_tmp)

        dbdir = os.path.dirname(self.dbname)
        keyMapPath = "{}/{}".format(dbdir, keyMapFile)
        self.keymap = codecs.open(keyMapPath, 'w', self.encoding)

    def __del__(self):
        self.cdb.finish()
        del self.cdb
        self.keymap.close()

    def add(self, key, value):
        if self.record_counter % self.fetch == 0:
            proc = subprocess.Popen(['wc', '-c', self.tmpfile],
                                    stdout=subprocess.PIPE)
            size = proc.stdout.read().strip().split(' ')[0]
            if int(size) > self.limit_file_size:
                self.cdb.finish()
                del self.cdb
                self.num_of_cdbs += 1

                dbnamei = "{}.{}".format(self.dbname, self.num_of_cdbs)
                print "processing {}".format(dbnamei)
                dbnamei_tmp = dbnamei + ".tmp"
                self.tmpfile = dbnamei_tmp
                self.cdb = cdb.cdbmake(dbnamei, dbnamei_tmp)
                self.record_counter = 0
                # save head keys of each splitted cdbs
                filebase = os.path.basename(dbnamei)
                self.keymap.write(u"{} {}\n".format(key, filebase))
        self.record_counter += 1
        self.cdb.add(key.encode(self.encoding), value)
