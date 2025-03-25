#!/usr/bin/env python
#
# Solr 4 remote backup tool
#
# URL: https://github.com/nla/solrbackup
# Author: Alex Osborne <aosborne@nla.gov.au>
# License: MIT
#
import json, time, os, struct, zlib, sys, errno
from urllib import urlencode
from urllib2 import urlopen
from contextlib import closing
from optparse import OptionParser

def getjson(url):
    f = urlopen(url)
    try:
        return json.load(f)
    finally:
        f.close()

def listcores(solr_url):
    return getjson(solr_url + '/admin/cores?action=STATUS&wt=json')['status'].keys()

def clusterstate(solr_url):
    return json.loads(getjson(solr_url + '/zookeeper?detail=true&path=%2Fclusterstate.json')['znode']['data'])

def indexversion(solr_url, core):
    response = getjson(solr_url + '/%s/replication?command=indexversion&wt=json' % core)
    return {'generation': response['generation'], 'indexversion': response['indexversion']}

def filelist(solr_url, core, version):
    return getjson(solr_url + '/%s/replication?command=filelist&wt=json&%s' % (core, urlencode(version)))['filelist']

class FileStream(object):
    def __init__(self, f, use_checksum = False):
        self.f = f
        self.use_checksum = use_checksum

    def __iter__(self):
        return self

    def unpack(self, fmt):
        size = struct.calcsize(fmt)
        buf = self.f.read(size)
        if buf:
            return struct.unpack(fmt, buf)
        else:
            return None

    def next(self):
        size, = self.unpack('>i')
        if size is None or size == 0:
            self.close()
            raise StopIteration
        if self.use_checksum:
            checksum, = self.unpack('>q')
        data = self.f.read(size)
        if len(data) < size:
            self.close()
            raise EOFError('unexpected end of file stream')
        if self.use_checksum:
            calculated = zlib.adler32(data) & 0xffffffff
            if calculated != checksum:
                self.close()
                raise 'checksum mismatch: calculated ' + calculated + ' but expected ' + checksum
        return data

    def close(self):
        self.f.close()

def filestream(solr_url, core, version, file, offset=0, use_checksum=False):
    query = {
        'command': 'filecontent',
        'wt': 'filestream',
        'file': file['name'],
        'offset': offset,
        'checksum': 'true' if use_checksum else 'false',
        'generation': version['generation'],
    }
    f = urlopen('%s/%s/replication?%s' % (solr_url, core, urlencode(query)))
    return FileStream(f, use_checksum=use_checksum)

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

def is_complete(path, expected_size):
    try:
        return os.path.getsize(path) >= expected_size
    except OSError as e:
        if e.errno == errno.ENOENT:
            return False
        else:
            raise

def nicesize(bytes):
    if bytes < 1024: return '%dB' % bytes
    if bytes < 1024 * 1024: return '%.2fK' % (bytes / 1024.0)
    if bytes < 1024 * 1024 * 1024: return '%.2fM' % (bytes / 1024.0 / 1024.0)
    return '%.2fG' % (bytes / 1024.0 / 1024.0 / 1024.0)

def download_file(solr_url, core, version, file, destdir, options):
    dest = os.path.join(destdir, file['name'])
    if is_complete(dest, file['size']):
        if options.verbose:
            print 'already got', file['name']
        return
    if options.verbose:
        print 'fetching', file['name']
    with open(dest, 'a+b') as out:
        out.seek(0, 2)
        offset = out.tell()
        with closing(filestream(solr_url, core, version, file, offset, use_checksum=options.use_checksum)) as stream:
            for packet in stream:
                out.write(packet)
                if options.verbose:
                    print core, file['name'], nicesize(out.tell()), '/', nicesize(file['size']), '%.2f%%' % (100.0 * out.tell() / file['size'])

def download_core(solr_url, core, dest, options):
    version = indexversion(solr_url, core)
    files = filelist(solr_url, core, version)
    mkdir_p(dest)
    for file in files:
        download_file(solr_url, core, version, file, dest, options)
    keep = set([f['name'] for f in files])
    if options.delete:
        for file in os.listdir(dest):
            if file not in keep:
                if options.verbose: print 'deleting', file
                os.remove(os.path.join(dest, file))

def download_cores(solr_url, outdir, options):
    for core in options.cores or listcores(solr_url):
        dest = os.path.join(outdir, core)
        download_core(solr_url, core, dest, options)

def find_leader(replicas):
    for replica in replicas:
        if replica.get('leader') == 'true':
            return replica
    return None

def download_cloud(solr_url, outdir, options):
    collections = clusterstate(solr_url)
    for colname, coldata in collections.iteritems():
        for shardname, sharddata in coldata['shards'].iteritems():
            replica = find_leader(sharddata['replicas'].values())
            if replica is None:
                raise 'no leader for shard ' + shardname + ' in ' + colname
            shard_url = replica['base_url']
            core = replica['core']
            dest = os.path.join(outdir, colname, shardname)
            download_core(solr_url, core, dest, options)

def main():
    parser = OptionParser(usage='Usage: %prog [options] solr_url outdir')
    parser.add_option("-C", "--cloud", action="store_true", dest="cloud", default=False, help="download all shards from a SolrCloud")
    parser.add_option("-v", "--verbose", action="store_true", dest="verbose", default=False, help="show progress")
    parser.add_option("-d", "--delete", action="store_true", dest="delete", default=False, help="expire old segments (use when updating an existing backup)")
    parser.add_option("--core", action="append", dest="cores", help="core to download (can be specified multiple times, default is all)")
    parser.add_option("--no-checksum", action="store_true", dest="use_checksum", default=True, help="don't verify adler32 checksums while downloading")
    (options, args) = parser.parse_args()

    if len(args) < 2:
        parser.print_help()
        sys.exit(1)

    solr_url = args[0].rstrip('/')
    outdir = args[1]

    if options.cloud:
        download_cloud(solr_url, outdir, options)
    else:
        download_cores(solr_url, outdir, options)

if __name__ == '__main__': main()
