import re, os, sys, time, random

try:
    import autotest.common as common
except ImportError:
    import common
from autotest.client.shared.settings import settings
from autotest.tko import utils


class MySQLTooManyRows(Exception):
    pass


class db_sql(object):
    def __init__(self, debug=False, autocommit=True, host=None,
                 database=None, user=None, password=None):
        self.debug = debug
        self.autocommit = autocommit
        self._load_config(host, database, user, password)

        self.con = None
        self._init_db()

        # if not present, insert statuses
        self.status_idx = {}
        self.status_word = {}
        status_rows = self.select('status_idx, word', 'tko_status', None)
        for s in status_rows:
            self.status_idx[s[1]] = s[0]
            self.status_word[s[0]] = s[1]

        machine_map = os.path.join(os.path.dirname(__file__),
                                   'machines')
        if os.path.exists(machine_map):
            self.machine_map = machine_map
        else:
            self.machine_map = None
        self.machine_group = {}


    def _load_config(self, host, database, user, password):
        # grab the host, database
        if host:
            self.host = host
        else:
            self.host = settings.get_value("AUTOTEST_WEB", "host")
        if database:
            self.database = database
        else:
            self.database = settings.get_value("AUTOTEST_WEB", "database")

        # grab the user and password
        if user:
            self.user = user
        else:
            self.user = settings.get_value("AUTOTEST_WEB", "user")
        if password is not None:
            self.password = password
        else:
            self.password = settings.get_value("AUTOTEST_WEB", "password")

        # grab the timeout configuration
        self.query_timeout = settings.get_value("AUTOTEST_WEB", "query_timeout",
                                       type=int, default=3600)
        self.min_delay = settings.get_value("AUTOTEST_WEB", "min_retry_delay", type=int,
                                   default=20)
        self.max_delay = settings.get_value("AUTOTEST_WEB", "max_retry_delay", type=int,
                                   default=60)


    def _init_db(self):
        # make sure we clean up any existing connection
        if self.con:
            self.con.close()
            self.con = None

        # create the db connection and cursor
        self.con = self.connect(self.host, self.database,
                                self.user, self.password)
        self.cur = self.con.cursor()


    def _random_delay(self):
        delay = random.randint(self.min_delay, self.max_delay)
        time.sleep(delay)


    def run_with_retry(self, function, *args, **dargs):
        """Call function(*args, **dargs) until either it passes
        without an operational error, or a timeout is reached.
        This will re-connect to the database, so it is NOT safe
        to use this inside of a database transaction.

        It can be safely used with transactions, but the
        transaction start & end must be completely contained
        within the call to 'function'."""
        OperationalError = _get_error_class("OperationalError")

        success = False
        start_time = time.time()
        while not success:
            try:
                result = function(*args, **dargs)
            except OperationalError, e:
                self._log_operational_error(e)
                stop_time = time.time()
                elapsed_time = stop_time - start_time
                if elapsed_time > self.query_timeout:
                    raise
                else:
                    try:
                        self._random_delay()
                        self._init_db()
                    except OperationalError, e:
                        self._log_operational_error(e)
            else:
                success = True
        return result


    def _log_operational_error(self, e):
        msg = ("%s: An operational error occured during a database "
               "operation: %s" % (time.strftime("%X %x"), str(e)))
        print >> sys.stderr, msg
        sys.stderr.flush() # we want these msgs to show up immediately


    def dprint(self, value):
        if self.debug:
            sys.stdout.write('SQL: ' + str(value) + '\n')


    def commit(self):
        self.con.commit()


    def get_last_autonumber_value(self):
        self.cur.execute('SELECT LAST_INSERT_ID()', [])
        return self.cur.fetchall()[0][0]


    def _quote(self, field):
        return '`%s`' % field


    def _where_clause(self, where):
        if not where:
            return '', []

        if isinstance(where, dict):
            # key/value pairs (which should be equal, or None for null)
            keys, values = [], []
            for field, value in where.iteritems():
                quoted_field = self._quote(field)
                if value is None:
                    keys.append(quoted_field + ' is null')
                elif '%' in str(value):
                    keys.append(quoted_field + 'like %s')
                    values.append(value)
                else:
                    keys.append(quoted_field + '=%s')
                    values.append(value)
            where_clause = ' and '.join(keys)
        elif isinstance(where, basestring):
            # the exact string
            where_clause = where
            values = []
        elif isinstance(where, tuple):
            # preformatted where clause + values
            where_clause, values = where
            assert where_clause
        else:
            raise ValueError('Invalid "where" value: %r' % where)

        return ' WHERE ' + where_clause, values



    def select(self, fields, table, where, distinct=False, group_by=None,
               max_rows=None):
        """\
                This selects all the fields requested from a
                specific table with a particular where clause.
                The where clause can either be a dictionary of
                field=value pairs, a string, or a tuple of (string,
                a list of values).  The last option is what you
                should use when accepting user input as it'll
                protect you against sql injection attacks (if
                all user data is placed in the array rather than
                the raw SQL).

                For example:
                  where = ("a = %s AND b = %s", ['val', 'val'])
                is better than
                  where = "a = 'val' AND b = 'val'"
        """
        cmd = ['select']
        if distinct:
            cmd.append('distinct')
        cmd += [fields, 'from', table]

        where_clause, values = self._where_clause(where)
        cmd.append(where_clause)

        if group_by:
            cmd.append(' GROUP BY ' + group_by)

        self.dprint('%s %s' % (' '.join(cmd), values))

        # create a re-runable function for executing the query
        def exec_sql():
            sql = ' '.join(cmd)
            numRec = self.cur.execute(sql, values)
            if max_rows is not None and numRec > max_rows:
                msg = 'Exceeded allowed number of records'
                raise MySQLTooManyRows(msg)
            return self.cur.fetchall()

        # run the query, re-trying after operational errors
        if self.autocommit:
            return self.run_with_retry(exec_sql)
        else:
            return exec_sql()


    def select_sql(self, fields, table, sql, values):
        """\
                select fields from table "sql"
        """
        cmd = 'select %s from %s %s' % (fields, table, sql)
        self.dprint(cmd)

        # create a -re-runable function for executing the query
        def exec_sql():
            self.cur.execute(cmd, values)
            return self.cur.fetchall()

        # run the query, re-trying after operational errors
        if self.autocommit:
            return self.run_with_retry(exec_sql)
        else:
            return exec_sql()


    def _exec_sql_with_commit(self, sql, values, commit):
        if self.autocommit:
            # re-run the query until it succeeds
            def exec_sql():
                self.cur.execute(sql, values)
                self.con.commit()
            self.run_with_retry(exec_sql)
        else:
            # take one shot at running the query
            self.cur.execute(sql, values)
            if commit:
                self.con.commit()


    def insert(self, table, data, commit=None):
        """\
                'insert into table (keys) values (%s ... %s)', values

                data:
                        dictionary of fields and data
        """
        fields = data.keys()
        fields = [f for f in fields if data[f] is not None]
        refs = ['%s' for field in fields if data[field] is not None]
        values = [data[field] for field in fields if data[field] is not None]
        cmd = ('insert into %s (%s) values (%s)' %
               (table, ','.join(self._quote(field) for field in fields),
                ','.join(refs)))
        self.dprint('%s %s' % (cmd, values))

        self._exec_sql_with_commit(cmd, values, commit)


    def delete(self, table, where, commit = None):
        cmd = ['delete from', table]
        if commit is None:
            commit = self.autocommit
        where_clause, values = self._where_clause(where)
        cmd.append(where_clause)
        sql = ' '.join(cmd)
        self.dprint('%s %s' % (sql, values))

        self._exec_sql_with_commit(sql, values, commit)


    def update(self, table, data, where, commit = None):
        """\
                'update table set data values (%s ... %s) where ...'

                data:
                        dictionary of fields and data
        """
        if commit is None:
            commit = self.autocommit
        cmd = 'update %s ' % table
        fields = data.keys()
        data_refs = [self._quote(field) + '=%s' for field in fields]
        data_values = [data[field] for field in fields]
        cmd += ' set ' + ', '.join(data_refs)

        where_clause, where_values = self._where_clause(where)
        cmd += where_clause

        values = data_values + where_values
        self.dprint('%s %s' % (cmd, values))

        self._exec_sql_with_commit(cmd, values, commit)


    def delete_afe_job(self, tag, commit = None):
        job_idx = self.find_job(tag)
        afe_job_idx = self.find_afe_job(tag)
        for test_idx in self.find_tests(job_idx):
            where = {'test_idx' : test_idx}
            self.delete('tko_iteration_result', where)
            self.delete('tko_iteration_attributes', where)
            self.delete('tko_test_attributes', where)
            self.delete('tko_test_labels_tests', {'test_id': test_idx})
        where = {'job_idx' : job_idx}
        self.delete('tko_job_keyvals', {'job_id' : job_idx})
        self.delete('tko_tests', where)
        self.delete('tko_jobs', where)
        self.delete('afe_aborted_host_queue_entries', {'queue_entry_id' : afe_job_idx})
        self.delete('afe_special_tasks', {'queue_entry_id' : afe_job_idx})
        self.delete('afe_host_queue_entries', {'job_id' : afe_job_idx})
        self.delete('afe_jobs', {'id' : afe_job_idx})


    def delete_job(self, tag, commit = None):
        job_idx = self.find_job(tag)
        for test_idx in self.find_tests(job_idx):
            where = {'test_idx' : test_idx}
            self.delete('tko_iteration_result', where)
            self.delete('tko_iteration_attributes', where)
            self.delete('tko_test_attributes', where)
            self.delete('tko_test_labels_tests', {'test_id': test_idx})
        where = {'job_idx' : job_idx}
        self.delete('tko_job_keyvals', {'job_id' : job_idx})
        self.delete('tko_tests', where)
        self.delete('tko_jobs', where)


    def insert_job(self, tag, job, commit = None):
        job.machine_idx = self.lookup_machine(job.machine)
        if not job.machine_idx:
            job.machine_idx = self.insert_machine(job, commit=commit)
        else:
            self.update_machine_information(job, commit=commit)

        afe_job_id = utils.get_afe_job_id(tag)

        data = {'tag':tag,
                'label': job.label,
                'username': job.user,
                'machine_idx': job.machine_idx,
                'queued_time': job.queued_time,
                'started_time': job.started_time,
                'finished_time': job.finished_time,
                'afe_job_id': afe_job_id}
        is_update = hasattr(job, 'index')
        if is_update:
            self.update('tko_jobs', data, {'job_idx': job.index}, commit=commit)
        else:
            self.insert('tko_jobs', data, commit=commit)
            job.index = self.get_last_autonumber_value()
        self.update_job_keyvals(job, commit=commit)
        for test in job.tests:
            self.insert_test(job, test, commit=commit)


    def update_job_keyvals(self, job, commit=None):
        for key, value in job.keyval_dict.iteritems():
            where = {'job_id': job.index, 'key': key}
            data = dict(where, value=value)
            exists = self.select('id', 'tko_job_keyvals', where=where)

            if exists:
                self.update('tko_job_keyvals', data, where=where, commit=commit)
            else:
                self.insert('tko_job_keyvals', data, commit=commit)


    def insert_test(self, job, test, commit = None):
        kver = self.insert_kernel(test.kernel, commit=commit)
        data = {'job_idx':job.index, 'test':test.testname,
                'subdir':test.subdir, 'kernel_idx':kver,
                'status':self.status_idx[test.status],
                'reason':test.reason, 'machine_idx':job.machine_idx,
                'started_time': test.started_time,
                'finished_time':test.finished_time}
        is_update = hasattr(test, "test_idx")
        if is_update:
            test_idx = test.test_idx
            self.update('tko_tests', data,
                        {'test_idx': test_idx}, commit=commit)
            where = {'test_idx': test_idx}
            self.delete('tko_iteration_result', where)
            self.delete('tko_iteration_attributes', where)
            where['user_created'] = 0
            self.delete('tko_test_attributes', where)
        else:
            self.insert('tko_tests', data, commit=commit)
            test_idx = test.test_idx = self.get_last_autonumber_value()
        data = {'test_idx': test_idx}

        for i in test.iterations:
            data['iteration'] = i.index
            for key, value in i.attr_keyval.iteritems():
                data['attribute'] = key
                data['value'] = value
                self.insert('tko_iteration_attributes', data,
                            commit=commit)
            for key, value in i.perf_keyval.iteritems():
                data['attribute'] = key
                data['value'] = value
                self.insert('tko_iteration_result', data,
                            commit=commit)

        for key, value in test.attributes.iteritems():
            data = {'test_idx': test_idx, 'attribute': key,
                    'value': value}
            self.insert('tko_test_attributes', data, commit=commit)

        if not is_update:
            for label_index in test.labels:
                data = {'test_id': test_idx, 'testlabel_id': label_index}
                self.insert('tko_test_labels_tests', data, commit=commit)


    def read_machine_map(self):
        if self.machine_group or not self.machine_map:
            return
        for line in open(self.machine_map, 'r').readlines():
            (machine, group) = line.split()
            self.machine_group[machine] = group


    def machine_info_dict(self, job):
        hostname = job.machine
        group = job.machine_group
        owner = job.machine_owner

        if not group:
            self.read_machine_map()
            group = self.machine_group.get(hostname, hostname)
            if group == hostname and owner:
                group = owner + '/' + hostname

        return {'hostname': hostname, 'machine_group': group, 'owner': owner}


    def insert_machine(self, job, commit = None):
        machine_info = self.machine_info_dict(job)
        self.insert('tko_machines', machine_info, commit=commit)
        return self.get_last_autonumber_value()


    def update_machine_information(self, job, commit = None):
        machine_info = self.machine_info_dict(job)
        self.update('tko_machines', machine_info,
                    where={'hostname': machine_info['hostname']},
                    commit=commit)


    def lookup_machine(self, hostname):
        where = { 'hostname' : hostname }
        rows = self.select('machine_idx', 'tko_machines', where)
        if rows:
            return rows[0][0]
        else:
            return None


    def lookup_kernel(self, kernel):
        rows = self.select('kernel_idx', 'tko_kernels',
                                {'kernel_hash':kernel.kernel_hash})
        if rows:
            return rows[0][0]
        else:
            return None


    def insert_kernel(self, kernel, commit = None):
        kver = self.lookup_kernel(kernel)
        if kver:
            return kver

        # If this kernel has any significant patches, append their hash
        # as diferentiator.
        printable = kernel.base
        patch_count = 0
        for patch in kernel.patches:
            match = re.match(r'.*(-mm[0-9]+|-git[0-9]+)\.(bz2|gz)$',
                                                    patch.reference)
            if not match:
                patch_count += 1

        self.insert('tko_kernels',
                    {'base':kernel.base,
                     'kernel_hash':kernel.kernel_hash,
                     'printable':printable},
                    commit=commit)
        kver = self.get_last_autonumber_value()

        if patch_count > 0:
            printable += ' p%d' % (kver)
            self.update('tko_kernels',
                    {'printable':printable},
                    {'kernel_idx':kver})

        for patch in kernel.patches:
            self.insert_patch(kver, patch, commit=commit)
        return kver


    def insert_patch(self, kver, patch, commit = None):
        print patch.reference
        name = os.path.basename(patch.reference)[:80]
        self.insert('tko_patches',
                    {'kernel_idx': kver,
                     'name':name,
                     'url':patch.reference,
                     'hash':patch.hash},
                    commit=commit)


    def find_test(self, job_idx, testname, subdir):
        where = {'job_idx': job_idx , 'test': testname, 'subdir': subdir}
        rows = self.select('test_idx', 'tko_tests', where)
        if rows:
            return rows[0][0]
        else:
            return None


    def find_tests(self, job_idx):
        where = { 'job_idx':job_idx }
        rows = self.select('test_idx', 'tko_tests', where)
        if rows:
            return [row[0] for row in rows]
        else:
            return []


    def find_job(self, tag):
        rows = self.select('job_idx', 'tko_jobs', {'tag': tag})
        if rows:
            return rows[0][0]
        else:
            return None


    def find_afe_job(self, tag):
        rows = self.select('afe_job_id', 'tko_jobs', {'tag': tag})
        if rows:
            return rows[0][0]
        else:
            return None


    def find_tag(self, tag_pattern):
        rows = self.select('tag', 'tko_jobs', {'tag': tag_pattern})
        if rows:
            return rows[0][0]
        else:
            return None


def _get_db_type():
    """Get the database type name to use from the global config."""
    return "db_" + settings.get_value("AUTOTEST_WEB", "db_type", default="mysql")


def _get_error_class(class_name):
    """Retrieves the appropriate error class by name from the database
    module."""
    db_module = __import__("autotest.tko." + _get_db_type(),
                           globals(), locals(), ["driver"])
    return getattr(db_module.driver, class_name)


def db(*args, **dargs):
    """Creates an instance of the database class with the arguments
    provided in args and dargs, using the database type specified by
    the global configuration (defaulting to mysql)."""
    db_type = _get_db_type()
    db_module = __import__("autotest.tko." + db_type, globals(),
                           locals(), [db_type])
    db = getattr(db_module, db_type)(*args, **dargs)
    return db
