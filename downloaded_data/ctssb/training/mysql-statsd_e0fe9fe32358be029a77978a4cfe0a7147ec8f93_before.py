from vars import *
import re
import copy
import MySQLdb

class Gather(object):

    def __init__(self, mysql_cur, statsd, logger, settings):
        self.mysql_cur = mysql_cur
        self.statsd = statsd
        self.logger = logger
        self.log_permissions = 0
        self.warned = False
        self.settings = settings

    def collect(self):
        '''
        Here the correct calls are made to collect the different sets of information from the mysql server
        '''
        imported_vars = copy.deepcopy(mysql_variables)
        self.results = {
        'connected': True,
        'mysql_vars': imported_vars
        }
        self.show_status()
        self.show_engine_status()
        self.slave_status()
        self.show_process()
        return self.results

    def show_status(self):
        '''
        Here the global status output is read and the variables are matched with the dictionary
        from vars.py to determine which type of graphs should be used.
        Statsd calls are added to the statsd buffer.
        '''
        query = 'SHOW GLOBAL STATUS'
        try:
            self.mysql_cur.execute(query)
            self.mysql_status = self.mysql_cur.fetchall()
        except self.mysql_cur.OperationalError:
            return self.db_error(query)

        for stat in self.mysql_status:
            if stat[0].lower() in self.results['mysql_vars']:
                self.results['mysql_vars'][stat[0].lower()][1] = stat[1]
        return

    def show_process(self):
        query = 'SHOW PROCESSLIST'
        try:
            self.mysql_cur.execute(query)
            self.mysql_processlist = self.mysql_cur.fetchall()
        except self.mysql_cur.OperationalError:
            return self.db_error(query)

        self.processlist = 0
        self.long_queries = 0
        self.sleeping_queries = 0
        self.sending_queries = 0

        for process in self.mysql_processlist:
            self.processlist += 1
            if process[5] > int(self.settings['long_query_time']):
                self.long_queries += 1
            if 'Sleep' in process[4]:
                self.sleeping_queries += 1
            if 'Sending data' in process[4]:
                self.sending_queries += 1

        self.results['mysql_vars']['sleeping_queries'][1] = self.sleeping_queries
        self.results['mysql_vars']['long_queries'][1] = self.long_queries
        self.results['mysql_vars']['processlist'][1] = self.processlist
        self.results['mysql_vars']['sending_queries'][1] = self.sending_queries
        return

    def show_engine_status(self):
        '''
        Here we parse the show engine innodb status. Due to the output format we have to do a lot of
        ifs to check the output and then some calculations to get sensible data.
        Alot of this parsing is heavily influenced by the percona cacti graphs.
        Statsd calls are added to the statsd buffer.
        '''
        query = 'SHOW /*!50000 ENGINE*/ INNODB STATUS'
        try:
            self.mysql_cur.execute(query)
            self.mysql_engine_status = self.mysql_cur.fetchall()
        except self.mysql_cur.OperationalError:
            return self.db_error(query)

        self.engine_status = self.mysql_engine_status[0][2]
        transactions_value = 0
        self.current_transactions = 0
        self.active_transactions = 0
        self.innodb_lock_wait_secs = 0
        self.locked_transactions = 0
        self.innodb_lock_structs = 0
        trx_recorded = False

        for row in self.engine_status.split('\n'):
            if 'Mutex spin waits' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['mutex_spin_waits'][1] = floats[0]
                self.results['mysql_vars']['mutex_spin_rounds'][1] = floats[1]
                self.results['mysql_vars']['mutex_spin_oswaits'][1] = floats[2]
                continue

            elif 'RW-shared spins' in row and 'RW-excl' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['rw_shared_spin_waits'][1] = floats[0]
                self.results['mysql_vars']['rw_shared_os_waits'][1] = floats[1]
                self.results['mysql_vars']['rw_excl_spin_waits'][1] = floats[2]
                self.results['mysql_vars']['rw_excl_os_waits'][1] = floats[3]
                continue

            elif 'RW-shared spins' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['rw_shared_spin_waits'][1] = floats[0]
                self.results['mysql_vars']['rw_shared_os_waits'][1] = floats[1]
                continue

            elif 'RW-excl' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['rw_excl_spin_waits'][1] = floats[0]
                self.results['mysql_vars']['rw_excl_os_waits'][1] = floats[1]
                continue

            elif 'Trx id counter' in row:
                split_row = row.split()
                if len(split_row) == 5:
                    transactions_value = (int(split_row[3]) * 4294967296) + int(split_row[4])
                else:
                    transactions_value = int(split_row[3], 16)
                trx_recorded = True
                self.results['mysql_vars']['innodb_transactions'][1] = transactions_value
                continue

            elif 'Purge done for trx' in row:
                split_row = row.split()
                if split_row[7] == 'undo':
                    purge = int(split_row[6], 16)
                    self.results['mysql_vars']['unpurged_transactions'][1] = transactions_value - purge
                else:
                    purge = (int(split_row[6]) * 4294967296) + int(split_row[7])
                    self.results['mysql_vars']['unpurged_transactions'][1] = transactions_value - purge
                continue

            elif 'History list length' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['history_list_length'][1] = floats[0]
                continue

            elif trx_recorded and '---TRANSACTION' in row:
                self.current_transactions += 1
                if 'ACTIVE' in row:
                    self.active_transactions += 1
                continue

            elif trx_recorded and '------- TRX HAS BEEN' in row:
                floats = self.row_float(row)
                self.innodb_lock_wait_secs += floats[0]
                continue

            elif 'read views open inside InnoDB' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['read_views'][1] = floats[0]
                continue

            elif 'mysql tables in use' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['innodb_tables_in_use'][1] = floats[0]
                self.results['mysql_vars']['innodb_locked_tables'][1] = floats[1]
                continue

            elif 'lock struct(s)' in row:
                floats = self.row_float(row)
                if 'LOCK WAIT' in row:
                    self.innodb_lock_structs += int(floats[0])
                    self.locked_transactions += 1
                else:
                    self.innodb_lock_structs += int(floats[0])

                continue

            elif 'OS file reads' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['file_reads'][1] = floats[0]
                self.results['mysql_vars']['file_writes'][1] = floats[1]
                self.results['mysql_vars']['file_fsyncs'][1] = floats[2]
                continue

            elif 'Pending normal aio reads:' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['pending_normal_aio_reads'][1] = floats[0]
                self.results['mysql_vars']['pending_normal_aio_writes'][1] = floats[1]
                continue

            elif 'ibuf aio reads' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['pending_ibuf_aio_reads'][1] = floats[0]
                self.results['mysql_vars']['pending_aio_log_ios'][1] = floats[1]
                self.results['mysql_vars']['pending_aio_sync_ios'][1] = floats[2]
                continue

            elif 'Pending flushes (fsync)' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['pending_log_flushes'][1] = floats[0]
                self.results['mysql_vars']['pending_buf_pool_flushes'][1] = floats[1]
                continue

            elif 'Ibuf for space 0: size ' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['ibuf_used_cells'][1] = floats[0]
                self.results['mysql_vars']['ibuf_free_cells'][1] = floats[1]
                self.results['mysql_vars']['ibuf_cell_count'][1] = floats[2]
                continue

            elif 'Ibuf: size ' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['ibuf_used_cells'][1] = floats[0]
                self.results['mysql_vars']['ibuf_free_cells'][1] = floats[1]
                self.results['mysql_vars']['ibuf_cell_count'][1] = floats[2]
                if 'merges' in row:
                    self.results['mysql_vars']['ibuf_merges'][1] = floats[3]
                continue

            elif 'Hash table size ' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['hash_index_cells_total'][1] = floats[0]
                if 'used cells' in row:
                    self.results['mysql_vars']['hash_index_cells_used'][1] = floats[1]
                else:
                    self.results['mysql_vars']['hash_index_cells_used'][1] = 0

            elif 'log i/o\'s done,' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['log_writes'][1] = floats[0]

            elif 'pending log writes,' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['pending_log_writes'][1] = floats[0]
                self.results['mysql_vars']['pending_chkp_writes'][1] = floats[1]

            elif 'Log sequence number' in row:
                floats = self.row_float(row)
                if len(floats) > 1:
                    seq_num = int(floats[0]) * 4294967296 + int(floats[1])
                else:
                    seq_num = floats[0]
                self.results['mysql_vars']['log_bytes_written'][1] = seq_num

            elif 'Log flushed up to' in row:
                floats = self.row_float(row)
                if len(floats) > 1:
                    seq_num = int(floats[0]) * 4294967296 + int(floats[1])
                else:
                    seq_num = floats[0]
                self.results['mysql_vars']['log_bytes_flushed'][1] = seq_num

            elif 'Last checkpoint at' in row:
                floats = self.row_float(row)
                if len(floats) > 1:
                    seq_num = int(floats[0]) * 4294967296 + int(floats[1])
                else:
                    seq_num = floats[0]
                self.results['mysql_vars']['last_checkpoint'][1] = seq_num

            elif 'Total memory allocated' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['total_mem_alloc'][1] = floats[0]
                self.results['mysql_vars']['additional_pool_alloc'][1] = floats[1]

            elif 'Adaptive hash index' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['adaptive_hash_memory'][1] = floats[0]

            elif 'Page hash' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['page_hash_memory'][1] = floats[0]

            elif 'Dictionary cache' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['dictionary_cache_memory'][1] = floats[0]

            elif 'File system' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['file_system_memory'][1] = floats[0]

            elif 'Lock system' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['lock_system_memory'][1] = floats[0]

            elif 'Recovery system' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['recovery_system_memory'][1] = floats[0]

            elif 'Threads             ' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['thread_hash_memory'][1] = floats[0]

            elif 'innodb_io_pattern' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['innodb_io_pattern_memory'][1] = floats[0]

            elif 'Buffer pool size ' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['pool_size'][1] = floats[0]

            elif 'Buffer pool size, bytes' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['pool_size'][1] = floats[0]

            elif 'Free buffers' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['free_pages'][1] = floats[0]

            elif 'Database pages' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['database_pages'][1] = floats[0]

            elif 'Modified db pages' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['modified_pages'][1] = floats[0]

            elif 'Pages read' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['pages_read'][1] = floats[0]
                self.results['mysql_vars']['pages_created'][1] = floats[1]
                self.results['mysql_vars']['pages_written'][1] = floats[2]

            elif 'Number of rows inserted' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['rows_inserted'][1] = floats[0]
                self.results['mysql_vars']['rows_updated'][1] = floats[1]
                self.results['mysql_vars']['rows_deleted'][1] = floats[2]
                self.results['mysql_vars']['rows_read'][1] = floats[3]

            elif ' queries inside InnoDB, ' in row:
                floats = self.row_float(row)
                self.results['mysql_vars']['queries_inside'][1] = floats[0]
                self.results['mysql_vars']['queries_queued'][1] = floats[1]

        self.results['mysql_vars']['current_transactions'][1] = self.current_transactions
        self.results['mysql_vars']['active_transactions'][1] = self.active_transactions
        self.results['mysql_vars']['innodb_lock_wait_secs'][1] = self.innodb_lock_wait_secs
        self.results['mysql_vars']['locked_transactions'][1] = self.locked_transactions
        self.results['mysql_vars']['innodb_lock_structs'][1] = self.innodb_lock_structs
        self.results['mysql_vars']['unflushed_log'][1] = int(self.results['mysql_vars']['log_bytes_written'][1]) - int(self.results['mysql_vars']['log_bytes_flushed'][1])
        self.results['mysql_vars']['uncheckpointed_bytes'][1] = int(self.results['mysql_vars']['log_bytes_written'][1]) - int(self.results['mysql_vars']['last_checkpoint'][1])
        return


    def slave_status(self):
        '''
        Here we parse the output of show slave status.
        Statsd calls are added to the statsd buffer.
        '''
        query = 'SHOW SLAVE STATUS'
        try:
            self.mysql_cur.execute(query)
            mysql_slave_status = self.mysql_cur.fetchone()
        except self.mysql_cur.OperationalError:
            return self.db_error(query)

        if mysql_slave_status is None:
            self.results['mysql_vars']['slave_running'][1] = 0
            return

        if mysql_slave_status[11] == 'No':
            self.results['mysql_vars']['slave_io_running'][1] = 0
        else:
            self.results['mysql_vars']['slave_io_running'][1] = 1

        if mysql_slave_status[12] == 'No':
            self.results['mysql_vars']['slave_sql_running'][1] = 0
        else:
            self.results['mysql_vars']['slave_sql_running'][1] = 1

        if mysql_slave_status[32] is None:
            self.results['mysql_vars']['seconds_behind_master'][1] = 0
        else:
            self.results['mysql_vars']['seconds_behind_master'][1] = mysql_slave_status[32]

        self.results['mysql_vars']['relay_log_space'][1] = mysql_slave_status[22]

        return

    def db_error(self, query):
        '''
        This function deals with database exceptions. It checks if the connection is still alive.
        If the connection is alive but the there are still problems running queries it warns about permission errors.
        This function also calls zeros_stats based on certain criteria.
        '''
        try:
            test_query = 'SELECT current_user()'
            self.mysql_cur.execute(test_query)
        except self.mysql_cur.OperationalError:
            if not self.warned:
                self.logger.critical('Unable to query MySQL')
                self.warned = True
            self.results['connected'] = False
            return

        if self.log_permissions < 2:
            self.logger.warn('Unable to execute: {0} - Check user permissions'.format(query))
            self.log_permissions += 1
        return

    def row_float(self, row):
        '''
        Finds all the floats in a string and returns a list.
        '''
        floats = re.findall(r"[-+]?\d*\.\d+|\d+", row)
        return floats

