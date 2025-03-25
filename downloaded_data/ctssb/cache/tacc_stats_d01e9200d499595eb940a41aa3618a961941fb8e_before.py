#!/usr/bin/env python
import datetime, errno, glob, gzip, numpy, os, sys, time
import amd64_pmc, sge_acct

verbose = os.getenv('TACC_STATS_VERBOSE')

if not verbose:
    numpy.seterr(over='ignore')

stats_home = os.getenv('TACC_STATS_HOME', '/scratch/projects/tacc_stats')

# raw_stats_dir/HOST/TIMESTAMP: raw stats files.
raw_stats_dir = os.getenv('TACC_STATS_RAW', os.path.join(stats_home, 'archive'))

# prolog_host_lists/YYYY/MM/DD/prolog_hostfile.JOBID.*.
# Symbolic link to /share/sge6.2/default/tacc/hostfile_logs.
host_list_dir = os.getenv('TACC_STATS_HOSTFILES', os.path.join(stats_home, 'hostfiles'))

scheduler = os.getenv('TACC_STATS_JOB_SCHEDULER')

prog = os.path.basename(sys.argv[0])
if prog == "":
    prog = "***"

def trace(fmt, *args):
    if verbose:
        msg = fmt % args
        sys.stderr.write(prog + ": " + msg)

def error(fmt, *args):
    msg = fmt % args
    sys.stderr.write(prog + ": " + msg)

RAW_STATS_TIME_MAX = 86400 + 2 * 3600
RAW_STATS_TIME_PAD = 1200

SF_SCHEMA_CHAR = '!'
SF_DEVICES_CHAR = '@'
SF_COMMENT_CHAR = '#'
SF_PROPERTY_CHAR = '$'
SF_MARK_CHAR = '%'

class SchemaEntry(object):
    __slots__ = ('key', 'index', 'is_control', 'is_event', 'width', 'mult', 'unit')

    def __init__(self, i, s):
        opt_lis = s.split(',')
        self.key = opt_lis[0]
        self.index = i
        self.is_control = False
        self.is_event = False
        self.width = None
        self.mult = None
        self.unit = None
        for opt in opt_lis[1:]:
            if len(opt) == 0:
                continue
            elif opt[0] == 'C':
                self.is_control = True
            elif opt[0] == 'E':
                self.is_event = True
            elif opt[0:2] == 'W=':
                self.width = int(opt[2:])
            elif opt[0:2] == 'U=':
                j = 2
                while j < len(opt) and opt[j].isdigit():
                    j += 1
                if j > 2:
                    self.mult = numpy.uint64(opt[2:j])
                if j < len(opt):
                    self.unit = opt[j:]
                if self.unit == "KB":
                    self.mult = numpy.uint64(1024)
                    self.unit = "B"
            else:
                # XXX
                raise ValueError("unrecognized option `%s' in schema entry spec `%s'\n", opt, s)

    def __eq__(self, other):
        return isinstance(other, self.__class__) and \
               all(self.__getattribute__(attr) == other.__getattribute__(attr) \
                   for attr in self.__slots__)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        lis = [] # 'index=%d' % self.index
        if self.is_event:
            lis.append('is_event=True')
        elif self.is_control:
            lis.append('is_control=True')
        if self.width:
            lis.append('width=%d' % int(self.width))
        if self.mult:
            lis.append('mult=%d' % int(self.mult))
        if self.unit:
            lis.append('unit=%s' % self.unit)
        return '(' + ', '.join(lis) + ')'


class Schema(dict):
    def __init__(self, desc):
        dict.__init__(self)
        self.desc = desc
        self._key_list = []
        self._value_list = []
        for i, s in enumerate(desc.split()):
            e = SchemaEntry(i, s)
            dict.__setitem__(self, e.key, e)
            self._key_list.append(e.key)
            self._value_list.append(e)

    def __iter__(self):
        return self._key_list.__iter__()

    def __repr__(self):
        return '{' + ', '.join(("'%s': %s" % (k, repr(self[k]))) \
                               for k in self._key_list) + '}'

    def _notsup(self, s):
        raise TypeError("'Schema' object does not support %s" % s)

    def __delitem__(self, k, v):
        self._notsup('item deletion')

    def pop(self, k, d=None):
        self._notsup('removal')

    def popitem(self):
        self._notsup('removal')

    def setdefault(self, k, d=None):
        self._notsup("item assignment")

    def update(self, **args):
        self._notsup("update")

    def items(self):
        return zip(self._key_list, self._value_list)

    def iteritems(self):
        for k in self._key_list:
            yield (k, dict.__getitem__(self, k))

    def iterkeys(self):
        return self._key_list.__iter__()

    def itervalues(self):
        return self._value_list.__iter__()

    def keys(self):
        return self._key_list

    def values(self):
        return self._value_list


def get_host_list_path(acct):
    """Return the path of the host list written during the prolog."""
    # Example: /share/sge6.2/default/tacc/hostfile_logs/2011/05/19/prolog_hostfile.1957000.IV32627
    start_date = datetime.date.fromtimestamp(acct['start_time'])
    if scheduler == 'sge':
        base_glob = 'prolog_hostfile.' + str(acct['id']) + '.*'
        for days in (0, -1, 1):
            yyyy_mm_dd = (start_date + datetime.timedelta(days)).strftime("%Y/%m/%d")
            full_glob = os.path.join(host_list_dir, yyyy_mm_dd, base_glob)
            for path in glob.iglob(full_glob):
                return path
    elif scheduler == 'slurm_stampede':
        base_glob = 'hostlist.' + str(acct['id'])
        for days in (0, -1, 1):
            yyyy_mm_dd = (start_date + datetime.timedelta(days)).strftime("%Y/%m/%d")
            full_glob = os.path.join(os.getenv('TACC_STATS_HOST_LIST_DIR'), yyyy_mm_dd, base_glob)
            l = []
            l.append(full_glob)
            for path in iter(l):
                return path
    
    return None


def stats_file_discard_record(file):
    for line in file:
        if line.isspace():
            return


class Host(object):
    # __slots__ = ('job', 'name', 'times', 'marks', 'raw_stats')

    def __init__(self, job, name):
        self.job = job
        self.name = name
        self.times = []
        self.marks = {}
        self.raw_stats = {}

    def trace(self, fmt, *args):
        self.job.trace('%s: ' + fmt, self.name, *args)

    def error(self, fmt, *args):
        self.job.error('%s: ' + fmt, self.name, *args)

    def get_stats_paths(self):
        # returns the list path_list that contains all the paths to files
        # for the current node that exist within the time specified
        raw_host_stats_dir = os.path.join(raw_stats_dir, self.name)
        job_start = self.job.start_time - RAW_STATS_TIME_PAD
        job_end = self.job.end_time + RAW_STATS_TIME_PAD
        path_list = []
        try:
            for ent in os.listdir(raw_host_stats_dir):
                base, dot, ext = ent.partition(".")
                if not base.isdigit():
                    continue
                # Prune to files that might overlap with job.
                # ent_start is looking for a timestamp, depending on how the files are saved in
                # the archive/node directory, they may need to be changed.
                if (scheduler == 'torque'):
                    # tacc_stats raw data files saved as archive/node/YYYYMMDD, these need to
                    # be converted to a unix timestamp
                    ent_start = long(datetime.datetime.strptime(base, '%Y%m%d').strftime("%s"))
                else:
                    ent_start = long(base)
                ent_end = ent_start + RAW_STATS_TIME_MAX
                if max(job_start, ent_start) <= min(job_end, ent_end):
                    full_path = os.path.join(raw_host_stats_dir, ent)
                    path_list.append((full_path, ent_start))
                    self.trace("path `%s', start %d\n", full_path, ent_start)
        except:
            pass
        path_list.sort(key=lambda tup: tup[1])
        return path_list

    def read_stats_file_header(self, start_time, file):
        file_schemas = {}
        for line in file:
            try:
                c = line[0]
                if c == SF_SCHEMA_CHAR:
                    type_name, schema_desc = line[1:].split(None, 1)
                    schema = self.job.get_schema(type_name, schema_desc)
                    if schema:
                        file_schemas[type_name] = schema
                    else:
                        self.error("file `%s', type `%s', schema mismatch desc `%s'\n",
                                   file.name, type_name, schema_desc)
                elif c == SF_PROPERTY_CHAR:
                    pass
                elif c == SF_COMMENT_CHAR:
                    pass
                else:
                    break
            except Exception as exc:
                self.trace("file `%s', caught `%s' discarding line `%s'\n",
                           file.name, exc, line)
                break
        return file_schemas

    def parse_stats(self, rec_time, line, file_schemas, file):
        type_name, dev_name, rest = line.split(None, 2)
        schema = file_schemas.get(type_name)
        if not schema:
            self.error("file `%s', unknown type `%s', discarding line `%s'\n",
                       file.name, type_name, line)
            return
        # TODO stats_dtype = numpy.uint64
        # XXX count = ?
        vals = numpy.fromstring(rest, dtype=numpy.uint64, sep=' ')
        if vals.shape[0] != len(schema):
            self.error("file `%s', type `%s', expected %d values, read %d, discarding line `%s'\n",
                       file.name, type_name, len(schema), vals.shape[0], line)
            return
        type_stats = self.raw_stats.setdefault(type_name, {})
        dev_stats = type_stats.setdefault(dev_name, [])
        dev_stats.append((rec_time, vals))

    def read_stats_file(self, start_time, file):
        file_schemas = self.read_stats_file_header(start_time, file)
        if not file_schemas:
            self.trace("file `%s' bad header\n", file.name)
            return
        # Scan file for records belonging to JOBID.
        rec_time = start_time
        for line in file:
            try:
                c = line[0]
                if c.isdigit():
                    str_time, rec_jobid = line.split()
                    rec_jobid = rec_jobid.split(',') #there can be multiple job id's
                    rec_time = long(str_time)
                    if str(self.job.id) in rec_jobid:
                        self.trace("file `%s' rec_time %d, rec_jobid `%s'\n",
                                   file.name, rec_time, rec_jobid)
                        self.times.append(rec_time)
                        break
            except Exception as exc:
                self.trace("file `%s', caught `%s', discarding `%s'\n",
                           file.name, str(exc), line)
                stats_file_discard_record(file)
        else:
            # We got to the end of this file wthout finding any
            # records belonging to JOBID.  Try next path.
            self.trace("file `%s' has no records belonging to job\n", file.name)
            return
        # OK, we found a record belonging to JOBID.
        for line in file:
            try:
                c = line[0]
                if c.isdigit():
                    str_time, rec_jobid = line.split()
                    rec_jobid = rec_jobid.split(',') #there can be multiple job id's
                    rec_time = long(str_time)
                    if str(self.job.id) not in rec_jobid:
                        return
                    self.trace("file `%s' rec_time %d, rec_jobid `%s'\n",
                               file.name, rec_time, rec_jobid)
                    self.times.append(rec_time)
                elif c.isalpha():
                    self.parse_stats(rec_time, line, file_schemas, file)
                elif c == SF_MARK_CHAR:
                    mark = line[1:].strip()
                    self.marks[mark] = True
                elif c == SF_COMMENT_CHAR:
                    pass
                else:
                    pass #...
            except Exception as exc:
                self.trace("file `%s', caught `%s', discarding `%s'\n",
                           file.name, str(exc), line)
                stats_file_discard_record(file)

    def gather_stats(self):
        path_list = self.get_stats_paths()
        if len(path_list) == 0:
            self.error("no stats files overlapping job\n")
            return False
        # read_stats_file() and parse_stats() append stats records
        # into lists of tuples in self.raw_stats.  The lists will be
        # converted into numpy arrays below.
        for path, start_time in path_list:
            if path.endswith('.gz'):
                with gzip.open(path) as file: # Gzip.
                    self.read_stats_file(start_time, file)
            else:
                with open(path) as file:
                    self.read_stats_file(start_time, file)
        # begin_mark = 'begin %s' % self.job.id # No '%'.
        # if not begin_mark in self.marks:
        #     self.error("no begin mark found\n")
        #     return False
        # end_mark = 'end %s' % self.job.id # No '%'.
        # if not end_mark in self.marks:
        #     self.error("no end mark found\n")
        #     return False
        return self.raw_stats

    def get_stats(self, type_name, dev_name, key_name):
        """Host.get_stats(type_name, dev_name, key_name)
        Return the vector of stats for the given type, dev, and key.
        """
        schema = self.job.get_schema(type_name)
        index = schema[key_name].index
        return self.stats[type_name][dev_name][:, index]


class Job(object):
    # TODO errors/comments
    __slots__ = ('id', 'start_time', 'end_time', 'acct', 'schemas', 'hosts', 'times')

    def __init__(self, acct):
        self.id = acct['id']
        self.start_time = acct['start_time']
        self.end_time = acct['end_time']
        self.acct = acct
        self.schemas = {}
        self.hosts = {}
        self.times = []

    def trace(self, fmt, *args):
        trace('%s: ' + fmt, self.id, *args)

    def error(self, fmt, *args):
        error('%s: ' + fmt, self.id, *args)

    def get_schema(self, type_name, desc=None):
        schema = self.schemas.get(type_name)
        if schema:
            if desc and schema.desc != desc:
                # ...
                return None
        elif desc:
            schema = self.schemas[type_name] = Schema(desc)
        return schema

    def gather_stats(self):

        if scheduler == 'sge':

            path = get_host_list_path(self.acct)
            if not path:
                self.error("no host list found\n")
                return False
            try:
                with open(path) as file:
                    host_list = [host for line in file for host in line.split()]
            except IOError as (err, s):
                self.error("cannot open host list `%s': %s\n", path, s)
                return False
            if len(host_list) == 0:
                self.error("empty host list\n")
                return False
            for host_name in host_list:
                # TODO Keep bad_hosts.
                host = Host(self, host_name)
                if host.gather_stats():
                    self.hosts[host_name] = host
            if not self.hosts:
                self.error("no good hosts\n")
                return False
            return True

        elif scheduler == 'torque':

            # get list of hostnames from acct dict
            host_list_tmp = self.acct['exec_host'].split('+')
            host_list = []
            for host_name in host_list_tmp:
                # remove cpu number from hostname
                host_list.append( host_name[:host_name.find('/')] )
            # create a set (unique list of no duplicate hostnames)
            host_list = list(set(host_list))

            # go through each host
            for host_name in host_list:
                host = Host(self, host_name)
                if host.gather_stats():
                    self.hosts[host_name] = host
            if not self.hosts:
                self.error("no good hosts\n")
                return False
            return True
            
        elif scheduler == 'slurm_stampede':
            
            path = get_host_list_path(self.acct)
            if not path:
                self.error("no host list found\n")
                return False
            try:
                with open(path) as file:
                    host_list = [host for line in file for host in line.split()]
            except IOError as (err, s):
                self.error("cannot open host list `%s': %s\n", path, s)
                return False
            if len(host_list) == 0:
                self.error("empty host list\n")
                return False
            for host_name in host_list:
                # TODO Keep bad_hosts.
                host_name = host_name + '.stampede.tacc.utexas.edu'
                host = Host(self, host_name)
                if host.gather_stats():
                    self.hosts[host_name] = host
            if not self.hosts:
                self.error("no good hosts\n")
                return False
            return True
            
        elif scheduler == 'slurm_rush':
            
            open_brace_flag = False
            close_brace_flag = False
            host_list = []
            tmp_host = ""
            # get a list of all the nodes and store them in host_host
            for c in self.acct['node_list']:
                if c == '[':
                    open_brace_flag = True
                elif c == ']':
                    close_brace_flag = True
                if ( c == ',' and not close_brace_flag and not open_brace_flag ) or (c == ',' and close_brace_flag):
                    host_list.append(tmp_host)
                    tmp_host = ""
                    close_brace_flag = False
                    open_brace_flag = False
                else:
                    tmp_host += c
            if tmp_host:
                host_list.append(tmp_host)
            # parse through host_list and expand the hostnames
            host_list_expanded = []
            for h in host_list:
                if '[' in h:
                    node_head = h.split('[')[0]
                    node_tail = h.split('[')[1][:-1].split(',')
                    for n in node_tail:
                        if '-' in n:
                            num = n.split('-')
                            for x in range(int(num[0]), int(num[1])+1):
                                host_list_expanded.append(node_head + str("%02d" % x))
                        else:
                            host_list_expanded.append(node_head + n)
                else:
                    host_list_expanded.append(h)
            for host_name in host_list_expanded:
                host = Host(self, host_name)
                if host.gather_stats():
                    self.hosts[host_name] = host
            if not self.hosts:
                self.error("no good hosts\n")
                return False
            return True
        
        else:
            return False

    def munge_times(self):
        times_lis = []
        for host in self.hosts.itervalues():
            times_lis.append(host.times)
            del host.times
        times_lis.sort(key=lambda lis: len(lis))
        # Choose times to have median length.
        times = list(times_lis[len(times_lis) / 2])
        if not times:
            return False
        times.sort()
        # Ensure that times is sane and monotonically increasing.
        t_min = self.start_time
        for i in range(0, len(times)): 
            t = max(times[i], t_min)
            times[i] = t
            t_min = t + 1
        self.trace("nr times min %d, mid %d, max %d\n",
                   len(times_lis[0]), len(times), len(times_lis[-1]))
        self.trace("job start to first collect %d\n", times[0] - self.start_time)
        self.trace("last collect to job end %d\n", self.end_time - times[-1])
        self.times = numpy.array(times, dtype=numpy.uint64)
        return True
    
    def process_dev_stats(self, host, type_name, schema, dev_name, raw):
        def trace(fmt, *args):
            return self.trace("host `%s', type `%s', dev `%s': " + fmt,
                              host.name, type_name, dev_name, *args)
        def error(fmt, *args):
            return self.error("host `%s', type `%s', dev `%s': " + fmt,
                              host.name, type_name, dev_name, *args)
        # raw is a list of pairs with car the timestamp and cdr a 1d
        # numpy array of values.
        m = len(self.times)
        n = len(schema)
        A = numpy.zeros((m, n), dtype=numpy.uint64) # Output.
        # First and last of A are first and last from raw.
        A[0] = raw[0][1]
        A[m - 1] = raw[-1][1]
        k = 0
        # len(raw) may not be equal to m, so we fill out A by choosing values
        # with the closest timestamps.
        for i in range(1, m - 1):
            t = self.times[i]
            while k + 1 < len(raw) and abs(raw[k + 1][0] - t) <= abs(raw[k][0] - t):
                k += 1
            A[i] = raw[k][1]
        # OK, we fit the raw values into A.  Now fixup rollover and
        # convert units.
        for e in schema.itervalues():
            j = e.index
            if e.is_event:
                p = r = A[0, j] # Previous raw, rollover/baseline.
                # Rebase, check for rollover.
                for i in range(0, m):
                    v = A[i, j]
                    if v < p:
                        # Looks like rollover.
                        if e.width:
                            trace("time %d, counter `%s', rollover prev %d, curr %d\n",
                                  self.times[i], e.key, p, v)
                            r -= numpy.uint64(1L << e.width)
                        elif v == 0:
                            # This happens with the IB counters.
                            # Ignore this value, use previous instead.
                            # TODO Interpolate or something.
                            trace("time %d, counter `%s', suspicious zero, prev %d\n",
                                  self.times[i], e.key, p)
                            v = p # Ugh.
                        else:
                            error("time %d, counter `%s', 64-bit rollover prev %d, curr %d\n",
                                  self.times[i], e.key, p, v)
                            # TODO Discard or something.
                    A[i, j] = v - r
                    p = v
            if e.mult:
                for i in range(0, m):
                    A[i, j] *= e.mult
        return A

    def process_stats(self):
        for host in self.hosts.itervalues():
            host.stats = {}
            for type_name, raw_type_stats in host.raw_stats.iteritems():
                stats = host.stats[type_name] = {}
                schema = self.schemas[type_name]
                for dev_name, raw_dev_stats in raw_type_stats.iteritems():
                    stats[dev_name] = self.process_dev_stats(host, type_name, schema,
                                                             dev_name, raw_dev_stats)
            del host.raw_stats
        amd64_pmc.process_job(self)
        # Clear mult, width from schemas. XXX
        for schema in self.schemas.itervalues():
            for e in schema.itervalues():
                e.width = None
                e.mult = None
        return True
    
    def aggregate_stats(self, type_name, host_names=None, dev_names=None):
        """Job.aggregate_stats(type_name, host_names=None, dev_names=None)
        """
        # TODO Handle control registers.
        schema = self.schemas[type_name]
        m = len(self.times)
        n = len(schema)
        A = numpy.zeros((m, n), dtype=numpy.uint64) # Output.       
        nr_hosts = 0
        nr_devs = 0
        if host_names:
            host_list = [self.hosts[name] for name in host_names]
        else:
            host_list = self.hosts.itervalues()
        for host in host_list:
            type_stats = host.stats.get(type_name)
            if not type_stats:
                continue
            nr_hosts += 1
            if dev_names:
                dev_list = [type_stats[name] for name in dev_names]
            else:
                dev_list = type_stats.itervalues()
            for dev_stats in dev_list:
                A += dev_stats
                nr_devs += 1
        return (A, nr_hosts, nr_devs)

    def get_stats(self, type_name, dev_name, key_name):
        """Job.get_stats(type_name, dev_name, key_name)
        Return a dictionary with keys host names and values the vector
        of stats for the given type, dev, and key.
        """
        schema = self.get_schema(type_name)
        index = schema[key_name].index
        host_stats = {}
        for host_name, host in self.hosts.iteritems():
            host_stats[host_name] = host.stats[type_name][dev_name][:, index]
        return host_stats


def from_acct(acct):
    """from_acct(acct)
    Return a Job object constructed from the SGE accounting data acct, running
    all required processing.
    """
    job = Job(acct)
    job.gather_stats() and job.munge_times() and job.process_stats()
    return job


def from_id(id, **kwargs):
    """from_id(id, acct_file=None, acct_path=sge_acct_path, use_awk=True)
    Return Job object for the job with SGE id ID, or None if no such job was found.
    """
    acct = sge_acct.from_id(id, **kwargs)
    if acct:
        return from_acct(acct)
    else:
        return None

# if True:
#     t0 = time.time()
#     j = job_stats.from_id(2294341)
#     t1 = time.time()
#     print t1 - t0
