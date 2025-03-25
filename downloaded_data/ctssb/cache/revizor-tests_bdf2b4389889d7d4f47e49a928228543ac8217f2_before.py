import os
import time
import logging
import json
from datetime import timedelta

from lettuce import world, step
from lxml import html

from revizor2.api import IMPL
from revizor2.conf import CONF
from revizor2.utils import wait_until
from revizor2.fixtures import resources
from revizor2.helpers import generate_random_string
from revizor2.consts import Platform, ServerStatus, Dist

LOG = logging.getLogger(__name__)


###DataBases handlers
#####################
#{'mysql': Mysql, 'mysql2': Mysql, 'percona': Mysql, 'mariadb': Mysql, 'redis': Redis, 'postgresql': PostgreSQL}
realisations = dict()


def dbhandler(databases):
    databases = [db.strip() for db in databases.split(',')]
    def wrapper(cls):
        for db in databases:
            realisations.update({db: cls})
    return wrapper


def close(func):
    def wrapped(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        finally:
            self._close()
    return wrapped


@dbhandler('postgresql')
class PostgreSQL(object):

    def __init__(self, server, db=None):
        #Get connection object
        self.server = server
        self._role = world.get_role('postgresql')
        self.connection = self._role.db.get_connection(server, db=db)
        self.cursor = self.connection.cursor()
        self.db = db
        self.node = world.cloud.get_node(server)

    def _close(self):
        self.cursor.close()
        self.connection.close()

    @close
    def get_timestamp(self):
        if not self.db:
            raise AssertionError("Can't get data base timestamp for PostgreSQL server, not one database is not used.")
        self.cursor.execute('SELECT * FROM timestamp;')
        return self.cursor.fetchone()[0]

    def restore(self, src_path, db):
        backups_in_server = self.node.run('ls /tmp/dbrestore/*')[0].lower().split()
        LOG.info('Available backups in server: %s' % backups_in_server)
        for backup in backups_in_server:
            if os.path.join(src_path, db).lower() in backup.lower():
                path = backup
                break
        else:
            raise AssertionError('Database %s backup not exist in path %s. Available backups: %s' %
                                 (db, src_path, ','.join(backups_in_server)))
        LOG.info('Creating db: %s in server.' % db)
        self._role.db.database_create(db, self.server)
        out = self.node.run('export PGPASSWORD=%s && psql -U scalr -d %s -h %s -f %s' %
                            (self._role.db.password, db.lower(), self.server.public_ip, path))
        if out[1]:
            raise AssertionError('Get error on restore database %s: %s' % (db, out[1]))
        LOG.info('Data base: %s was successfully created in server.' % db)

    @close
    def check_data(self, pattern):
        if not self.db:
            raise AssertionError("Can't get data base timestamp for PostgreSQL server, not one database is not used.")
        self.cursor.execute("SELECT table_name "
                            "FROM information_schema.tables "
                            "WHERE table_type = 'BASE TABLE' AND "
                            "table_schema NOT IN ('pg_catalog', 'information_schema');")
        tables = [t[0] for t in self.cursor.fetchall()]
        if not pattern in tables:
            raise AssertionError('Table %s not exist in database: %s' % (pattern, self.db))
        self.cursor.execute('SELECT count(*) as rows FROM %s;' % pattern)
        return self.cursor.fetchone()[0]


@dbhandler('redis')
class Redis(object):

    redis_path = {
        'debian':  {
            'bin': '/usr/bin',
            'conf': '/etc/redis'
        },
        'centos':  {
            'bin': '/usr/sbin',
            'conf': '/etc'
        }
    }

    def __init__(self, server, db=0):
        #Get connection object
        self.server = server
        role = world.get_role('redis')
        self.connection = role.db.get_connection(server, db=db)
        self.db = db
        self.node = world.cloud.get_node(server)
        self.snapshotting_type = 'aof' if os.environ.get('RV_REDIS_SNAPSHOTTING') in ('aof', None) else 'rdb'

    def get_timestamp(self):
        return self.connection.get('revizor.timestamp')

    def restore(self, src_path, db=None):
        #Kill redis-server
        LOG.info('Stopping Redis server.')
        out = self.node.run("pgrep -l redis-server | awk {print'$1'} | xargs -i{}  kill {} && sleep 5 && pgrep -l redis-server | awk {print'$1'}")[0]
        if out:
            raise AssertionError('Redis server, pid:%s  was not properly killed on remote host %s' % (out, self.server.public_ip))
        LOG.info('Redis server was successfully stopped. Getting backups and moving to redis storage.')
        #Move dump to redis storage
        out = self.node.run("find %s -name '*%s*' -print0 | xargs -i{} -0 -r cp -v {} /mnt/redisstorage/" %
                            (src_path, self.snapshotting_type))
        if not out[0]:
            raise AssertionError("Can't move dump to redis-server storage.  Error is: %s %s" % (out[0], out[1]))
        LOG.info('Available backups in server: %s. Backups was successfully moved to redis storage.' % out[0].split()[0])

        #Run redis-server
        LOG.info('Running Redis server.')
        out = self.node.run("/bin/su redis -s /bin/bash -c \"%(bin)s %(conf)s\" && sleep 5 &&  pgrep -l redis-server | awk {print'$1'}" %
                            {
                                 'bin': os.path.join(self.redis_path.get(Dist.get_os_family(self.node.os[0]))['bin'], 'redis-server'),
                                 'conf': os.path.join(self.redis_path.get(Dist.get_os_family(self.node.os[0]))['conf'], 'redis.6379.conf')
                            })
        if out[2]:
            raise AssertionError("Redis server was not properly started on remote host %s. Error is: %s %s"
                                 % (self.server.public_ip, out[0], out[1]))
        LOG.info('Redis server was successfully run.')

    def check_data(self, pattern):
        return len(self.connection.keys('*%s*' % pattern))


@dbhandler('mysql, mysql2, percona, mariadb')
class MySQL(object):

    def __init__(self, server, db=None):
        #Get connection object
        self.server = server
        self._role = world.get_role()
        self.connection = self._role.db.get_connection(server)
        self.cursor = self.connection.cursor()
        self.db = db
        self.node = world.cloud.get_node(server)

    def _close(self):
        self.cursor.close()
        self.connection.close()

    @close
    def get_timestamp(self):
        if not self.db:
            raise AssertionError("Can't get data base timestamp for MySQL server, not one database is not used.")
        self.cursor.execute('USE %s;' % self.db)
        self.cursor.execute('SELECT * FROM timestamp;')
        return self.cursor.fetchone()[0]

    def restore(self, src_path, db):
        backups_in_server = self.node.run('ls /tmp/dbrestore/*')[0].split()
        LOG.info('Available backups in server: %s' % backups_in_server)
        path = os.path.join(src_path, db)
        if not path in backups_in_server:
            raise AssertionError('Database %s backup not exist in path %s' % (db, path))
        #Create auth file for mysql
        out = self.node.run("echo $'[client]\nuser=scalr\npassword=%s' > ~/.my.cnf" % self._role.db.password)
        if out[1]:
            raise AssertionError("Can't create ~/.my.cnf.\n%s" % out[1])
        LOG.info('Creating db: %s in server.' % db)
        self._role.db.database_create(db, self.server)
        out = self.node.run('mysql %s < %s' % (db, path))
        if out[1]:
            raise AssertionError('Get error on restore database %s: %s' % (db, out[1]))
        LOG.info('Data base: %s was successfully created in server.' % db)

    @close
    def check_data(self, pattern):
        if not self.db:
            raise AssertionError("Can't get data base timestamp for MySQL server, not one database is not used.")
        self.cursor.execute('USE %s;' % self.db)
        self.cursor.execute('SHOW TABLES;')
        tables = [t[0] for t in self.cursor.fetchall()]
        if not pattern in tables:
            raise AssertionError('Table %s not exist in database: %s' % (pattern, self.db))
        self.cursor.execute('SELECT count(*) as rows FROM %s;' % pattern)
        return self.cursor.fetchone()[0]


def get_db_handler(db_name):
    try:
        return realisations[db_name]
    except KeyError:
        raise Exception("Can't get data base handler. No such class implemented.")



###Testsuite steps
##################
@step(r'I trigger ([\w]+) creation( on slave)?')
def trigger_creation(step, action, use_slave=None):
    action = action.strip()
    use_slave = True if use_slave else False
    db_role = world.get_role()
    info = db_role.db.info()
    if action != 'pmaaccess':
        setattr(world, 'last_%s' % action, info['last_%s' % action])
    if action == 'databundle':
        db_role.db.create_databundle(use_slave)
    else:
        getattr(db_role.db, 'create_%s' % action)()
    LOG.info("I'm trigger %s" % action)
    time.sleep(180)


@step(r'I launch ([\w]+) session')
def launch_session(step, service):
    """
    Run farm method for phpmyadmin
    """
    service = service.strip()
    LOG.info("I'm launch %s session" % service)
    world.launch_request = getattr(world.farm, 'db_launch_%s_session' % service)()


@step(r'([\w]+) is available, I see the ([\w]+) in the ([\w]+)')
def session_is_available(step, service, search_string, element):
    """Step checks for a running service by searching on the corresponding page of the relevant elements.
       Takes a variable as argument world.launch_request out of step launch_session"""
    if not world.launch_request:
        raise Exception('The %s service page is not found') % service
    tree = html.fromstring(world.launch_request.text)
    if search_string in tree.xpath('//%s' % element)[0].text:
        LOG.info("The %s service is launched." % service)
    else:
        raise AssertionError("The %s service is not launched." % service)


@step(r'Last (.+) date updated to current')
def assert_check_databundle_date(step, back_type):
    LOG.info("Check %s date" % back_type)
    if CONF.feature.driver.current_cloud in [Platform.CLOUDSTACK, Platform.IDCF, Platform.KTUCLOUD]:
        LOG.info('Platform is cloudstack-family, backup not doing')
        return True
    info = world.get_role().db.info()
    if info['last_%s' % back_type] == 'In progress...':
        while world.get_role().db.info()['last_%s' % back_type] == 'In progress...':
            LOG.debug('Last %s in progress, wait 10 seconds' % back_type)
            time.sleep(10)
    if not info['last_%s' % back_type] == getattr(world, 'last_%s' % back_type, 'Never'):
        return
    else:
        raise AssertionError('Previous %s was: %s and last: %s' % (back_type, getattr(world, 'last_%s' % back_type, 'Never'), info['last_%s' % back_type]))


@step(r"I create new database user '([\w\d]+)' on ([\w\d]+)$")
def create_database_user(step, username, serv_as):
    server = getattr(world, serv_as)
    password = generate_random_string(12)
    LOG.info("Create new database user '%s/%s' in server %s" % (username, password, server))
    db_role = world.get_role()
    db_role.db.user_create(username, password, server)
    db_role.db.credentials[username] = password


@step(r"I (?:add|have) small-sized database ([\w\d]+) on ([\w\d]+)(?: by user '([\w\d]+)')?")
def having_small_database(step, db_name, serv_as, username=None):
    server = getattr(world, serv_as)
    db_role = world.get_role()
    if username:
        LOG.info("Create database %s in server %s by user %s" % (db_name, server, username))
        setattr(world, 'data_insert_result', db_role.db.insert_data_to_database(db_name, server, (username, db_role.db.credentials[username])))
    else:
        LOG.info("Create database %s in server %s" % (db_name, server))
        setattr(world, 'data_insert_result', db_role.db.insert_data_to_database(db_name, server))


@step("I create (\d+) databases on ([\w]+)(?: by user '([\w\d]+)')?$")
def create_many_databases(step, db_count, serv_as, username=None):
    server = getattr(world, serv_as)
    db_role = world.get_role()
    credentials = (username, db_role.db.credentials[username]) if username else None
    for c in range(int(db_count)):
        db_name = "MDB%s" % c
        LOG.info("Create database %s in server %s" % (db_name, server))
        db_role.db.database_create(db_name, server, credentials)


@step('([^ .]+) is slave of ([^ .]+)$')
def assert_check_slave(step, slave_serv, master_serv):
    slave = getattr(world, slave_serv)
    master = getattr(world, master_serv)
    db_role = world.get_role()
    info = db_role.db.info()
    try:
        if not info['servers']['master']['serverId'] == master.id:
            raise AssertionError('Master is not %s' % master_serv)
        for sl in info['servers']:
            if sl.startswith('slave'):
                if info['servers'][sl]['serverId'] == slave.id:
                    return True
    except IndexError:
        raise AssertionError("I'm not see replication status")
    raise AssertionError('%s is not slave, all slaves: %s' % (slave_serv, info['slaves']))


@step('I create a ([\w]+)$')
def do_action(step, action):
    """
    Run databundle or backup process in farm
    """
    action = action.strip()
    db_role = world.get_role()
    getattr(db_role.db, 'create_%s' % action)()
    LOG.info("Create %s" % action)


@step('I create a ([\w]+) databundle on ([\w]+)')
def create_databundle(step, bundle_type, when):
    LOG.info('Create a %s databundle on %s' % (bundle_type, when))
    if when == 'slave':
        use_slave = True
    else:
        use_slave = False
    world.get_role().db.create_databundle(bundle_type, use_slave=use_slave)


@step("([\w]+)( not)? contains databases? ([\w\d,]+)(?: by user '([\w\d]+)')?$")
def check_database_in_new_server(step, serv_as, has_not, db_name, username=None):
    has_not = has_not and True or False
    time.sleep(5)
    db_role = world.get_role()
    dbs = db_name.split(',')
    if serv_as == 'all':
        world.farm.servers.reload()
        servers = filter(lambda s: s.status == ServerStatus.RUNNING, world.farm.servers)
    else:
        servers = [getattr(world, serv_as)]
    credentials = (username, db_role.db.credentials[username]) if username else None
    for server in servers:
        for db in dbs:
            LOG.info('Check database %s in server %s' % (db, server.id))
            world.assert_not_equal(db_role.db.database_exist(db, server, credentials), not has_not,
                                   (has_not and 'Database %s exist in server %s, but must be erased.  All db: %s'
                                   or 'Database %s not exist in server %s, all db: %s')
                                   % (db_name, server.id, db_role.db.database_list(server)))


@step("I create database ([\w\d]+) on ([\w\d]+)(?: by user '([\w\d]+)')?")
def create_new_database(step, db_name, serv_as, username=None):
    server = getattr(world, serv_as)
    db_role = world.get_role()
    LOG.info('Create database %s in server %s' % (db_name, server))
    credentials = (username, db_role.db.credentials[username]) if username else None
    db_role.db.database_create(db_name, server, credentials)
    LOG.info('Database was success created')
    time.sleep(15)


@step('And databundle type in ([\w\d]+) is ([\w]+)')
def check_bundle_type(step, serv_as, bundle_type):
    LOG.info('Check databundle type')
    time.sleep(10)
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    out = node.run("cat /var/log/scalarizr_debug.log | grep 'name=\"DbMsr_CreateDataBundle\"'")
    bundle = out[0].split('<backup_type>')[1].split('</backup_type>')[0]
    LOG.info('Databundle type in server messages: %s' % bundle)
    if not bundle == bundle_type:
        raise AssertionError('Bundle type in scalarizr message is not %s it %s' % (bundle_type, bundle))


@step('I increase storage to ([\d]+) Gb in ([\w\d]+) role$')
def increase_storage(step, size, role_type):
    size = int(size)
    if role_type == 'percona2':
        role_type = 'percona'
    LOG.info('Increase storage for %s role to %s Gb' % (role_type, size))
    setattr(world, 'grow_old_size', int(round(world.farm.db_info(role_type)['storage']['size']['total'])))
    grow_id = world.farm.db_increase_storage(role_type, size)
    LOG.info('Grow proccess id is %s' % grow_id)
    setattr(world, 'grow_status_id', grow_id)
    setattr(world, 'grow_new_size', size)


@step('grow status is ([\w\d]+)$')
def check_grow_status(step, status):
    LOG.debug('Check grow status')
    wait_until(wait_grow_status, args=(status.strip(),), timeout=900, error_text='Not see grow status %s' % status)


def wait_grow_status(status):
    new_status = IMPL.services.grow_info(world.grow_status_id)['status']
    LOG.info('Grow status for id %s is %s' % (world.grow_status_id, new_status))
    if new_status == status:
        return True
    elif new_status in ['failed', 'error']:
        raise AssertionError('Status of growing is %s' % new_status)
    else:
        return False


@step('And new storage size is ([\d]+) Gb in ([\w\d]+) role')
def check_new_storage_size(step, size, role_type):
    size = int(size)
    if role_type == 'percona2':
        role_type = 'percona'
    new_size = int(round(world.farm.db_info(role_type)['storage']['size']['total']))
    LOG.info('New size is %s, must be: %s (old size: %s)' % (new_size, size, world.grow_old_size))
    if not new_size == size:
        raise AssertionError('New size is %s, but must be %s (old %s)' % (new_size, size, world.grow_old_size))

@step('I know last backup url$')
def get_last_backup_url(step):
    LOG.info('Get last backup date')
    db_role = world.get_role()
    last_backup = db_role.db.info()['last_backup']
    last_backup = last_backup - timedelta(seconds=last_backup.second)
    LOG.info('Last backup date is: %s' % last_backup)
    all_backups = IMPL.services.list_backups(world.farm.id)
    LOG.info('All backups is: %s' % all_backups)
    links = IMPL.services.backup_details(all_backups[last_backup]['backupId'])['links']
    LOG.info('Backups liks is: %s' % links)
    if not len(links):
        raise AssertionError('DB backup details is empty, no links found.')
    last_backup_url = 's3://%s/manifest.json' % links['1']['path']['dirname']
    LOG.info('Last backup URL: %s' % last_backup_url)
    setattr(world, 'last_backup_url', last_backup_url)


@step(r'I know timestamp(?: from ([\w\d]+))? in ([\w\d]+)$')
def save_timestamp(step, db, serv_as):
    server = getattr(world, serv_as)
    db_role = world.get_role()
    db = db if db else ''
    db_handler_class = get_db_handler(db_role.db.db_name)
    LOG.info('Getting database %s backup timestamp for %s server' % (db, db_role.db.db_name))
    backup_timestamp = db_handler_class(server, db).get_timestamp()
    if not backup_timestamp:
        raise AssertionError('Database %s backup timestamp for %s server is empty.' % (db, db_role.db.db_name))
    #Set timestamp to global
    setattr(world, '%s_backup_timestamp' % db_role.db.db_name, backup_timestamp)
    LOG.info('Database %s backup timestamp for %s server is: %s' % (db, db_role.db.db_name, backup_timestamp))


@step('I download backup in ([\w\d]+)')
def download_dump(step, serv_as):
    #TODO: Add support for gce and openstack if Scalr support
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    node.put_file('/tmp/download_backup.py', resources('scripts/download_backup.py').get())
    if CONF.feature.driver.current_cloud == Platform.EC2:
        interpretator = 'python'
        check_omnibus = node.run('ls /opt/scalarizr/embedded/bin/python')
        if not check_omnibus[1].strip():
            interpretator = '/opt/scalarizr/embedded/bin/python'
        if node.os[0] == 'redhat' and node.os[1].startswith('5'):
            interpretator = 'python26'
        node.run('%s /tmp/download_backup.py --platform=ec2 --key=%s --secret=%s --url=%s' % (
            interpretator, world.cloud.config.libcloud.key,
            world.cloud.config.libcloud.secret,
            world.last_backup_url
        ))
    # elif CONF.feature.driver.current_cloud == Platform.GCE:
    #     with open(world.cloud.config.libcloud.key, 'r+') as key:
    #         node.put_file('/tmp/gcs_pk.p12', key.readall())
    #     node.run('python /tmp/download_backup.py --platform=gce --key=%s --url=%s' % (world.cloud.config.libcloud.username,
    #                                                                                   world.last_backup_url))
    # elif CONF.feature.driver.current_cloud == Platform.RACKSPACE_US:
    #     node.run('python /tmp/download_backup.py --platform=rackspaceng --key=%s --secret=%s --url=%s' % (
    #         world.cloud.config.libcloud.key, world.cloud.config.libcloud.secret, world.last_backup_url
    #     ))


@step('I delete databases ([\w\d,]+) in ([\w\d]+)$')
def delete_databases(step, databases, serv_as):
    databases = databases.split(',')
    server = getattr(world, serv_as)
    db_role = world.get_role()
    LOG.info('Delete databases  %s in server %s' % (databases, server.id))
    for db in databases:
        LOG.info('Delete database: %s' % db)
        db_role.db.database_delete(db, server)


@step('I restore databases ([\w\d,]+) in ([\w\d]+)$')
def restore_databases(step, databases, serv_as):
    databases = databases.split(',')
    server = getattr(world, serv_as)
    db_role = world.get_role()
    db_handler_class = get_db_handler(db_role.db.db_name)
    db_handler = db_handler_class(server)
    LOG.info('Restoring databases %s in server %s' % (','.join(databases), server.id))
    for db in databases:
        LOG.info('Restore database %s' % db)
        db_handler.restore('/tmp/dbrestore/', db)
        LOG.info('Database %s was successfully restored.' % db)
    LOG.info('All databases: %s was successfully restored.' % ','.join(databases))


@step("database ([\w\d]+) in ([\w\d]+) contains '([\w\d]+)' with (\d+) lines$")
def check_database_table(step, db, serv_as, pattern, line_count):
    #TODO: Support to all databases
    server = getattr(world, serv_as)
    db_role = world.get_role()
    if not db_role.db.database_exist(db, server):
        raise AssertionError('Database %s not exist in server %s' % (db, server.id))
    db_handler_class = get_db_handler(db_role.db.db_name)
    LOG.info('Getting database %s records count for %s server.' % (db, db_role.db.db_name))
    count = db_handler_class(server, db).check_data(pattern)
    if not int(count) == int(line_count):
        raise AssertionError('Records count in restored db %s is %s, but must be: %s' % (db, count, line_count))
    LOG.info('Records count in restored db %s is: %s this corresponds to the transferred' % (db, count))


@step('database ([\w\d]+) in ([\w\d]+) has relevant timestamp$')
def check_timestamp(step, db, serv_as):
    server = getattr(world, serv_as)
    db_role = world.get_role()
    db = db if db else ''
    db_handler_class = get_db_handler(db_role.db.db_name)
    LOG.info('Getting database %s new backup timestamp for %s server' % (db, db_role.db.db_name))
    timestamp = db_handler_class(server, db).get_timestamp()
    backup_timestamp = getattr(world, '%s_backup_timestamp' % db_role.db.db_name)
    if not timestamp == backup_timestamp:
        raise AssertionError('Timestamp is not equivalent: %s != %s' % (timestamp, backup_timestamp))
    #Set timestamp to global
    LOG.info('Database %s new backup timestamp for %s server is equivalent: %s = %s' % (db, db_role.db.db_name,
                                                                                        backup_timestamp, timestamp))


@step(r'([\w\d]+) replication status is ([\w\d]+)')
def verify_replication_status(step, behavior, status):
    wait_until(world.wait_replication_status, args=(behavior, status), error_text="Replication in broken", timeout=600)


@step(r'I (get|verify) ([\w\d]+) master storage id')
def get_storage_id(step, action, db):
    if not CONF.feature.storage == 'persistent':
        LOG.debug('Verify the master storage id is only available with persistent system')
        return True
    get = True if action == 'get' else False
    if get:
        LOG.info('Get Master storage id for db %s before Slave -> Master promotion.' % db)
        storage_id = world.farm.db_info(db)['storage']['id']
        if not storage_id:
            raise AssertionError("Can't get Master storage id for db %s before Slave -> Master promotion." % db)
        setattr(world, 'storage_id', storage_id)
        LOG.info('Master storage id for db %s before Slave -> Master promotion is %s' % (db, storage_id))
    else:
        LOG.info('Get new Master storage id for db %s after Slave -> Master promotion.' % db)
        storage_id = world.farm.db_info(db)['storage']['id']
        world.assert_not_equal(world.storage_id, storage_id, 'New Master storage id %s not matched with id %s '
                                                             'saved before Slave -> Master promotion.' %
                                                             (storage_id, world.storage_id))
        LOG.info('New Master storage id %s matched with id %s saved before Slave -> Master promotion.' % (storage_id, world.storage_id))


@step(r'I increase storage size to (\d+) Gb in farm settings for ([\w\d]+) role')
def increase_storage_farm_size(step, size, role_type):
    #TODO: Change this to decorator
    if CONF.feature.driver.current_cloud in (Platform.EC2,) \
            and CONF.feature.storage == 'persistent':
        LOG.info('Change storage size for "%s" role to "%s"' % (role_type, size))
        role = world.get_role(role_type)
        size = int(size)
        role.edit(options={
            "db.msr.storage.grow_config": json.dumps({"size": size})
        })


@step(r'I delete volume ([\w\d]+)')
def delete_attached_volume(step, volume_as):
    volume = getattr(world, '%s_volume' % volume_as)
    LOG.info('Delete volume "%s"' % volume.id)
    for i in range(10):
        try:
            world.cloud._driver._conn.destroy_volume(volume)
            break
        except Exception, e:
            if 'attached' in e.message:
                LOG.warning('Volume "%s" currently attached to server' % volume.id)
                time.sleep(60)
            else:
                raise


@step(r"([\w\d]+) doesn't has any databases")
def verify_db_not_exist(step, serv_as):
    db_role = world.get_role()
    databases = db_role.db.database_list()
    if db_role.db.db_name in ['mysql2', 'percona']:
        map(lambda x: databases.remove(x) if x in a else None,
            ['information_schema', 'mysql', 'performance_schema', 'test'])
        if len(databases) > 0:
            raise AssertionError('%s role contains databases: "%s"' %
                                 (db_role.db.db_name, databases))
    elif db_role.db.db_name == 'redis':
        if databases:
            raise AssertionError('%s role contains databases: "%s"' %
                                 (db_role.db.db_name, databases))
    elif db_role.db.db_name == 'postgresql':
        if len(databases) > 5:
            raise AssertionError('%s role contains databases: "%s"' %
                                 (db_role.db.db_name, databases))