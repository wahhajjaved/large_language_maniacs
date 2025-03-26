import time
import logging
from datetime import timedelta

from lettuce import world, step
from lxml import html

from revizor2.api import IMPL
from revizor2.conf import CONF
from revizor2.utils import wait_until
from revizor2.fixtures import resources
from revizor2.helpers import generate_random_string
from revizor2.consts import Platform, ServerStatus

import os
from revizor2.consts import Dist

LOG = logging.getLogger('databases')

#TODO: add to all methods which call dbmsr 3 retries

PORTS_MAP = {'mysql': 3306, 'mysql2': 3306, 'mariadb': 3306, 'percona':3306, 'postgresql': 5432, 'redis': 6379,
             'mongodb': 27018, 'mysqlproxy': 4040}


###DataBases handlers
#####################
#{'mysql': Mysql, 'mysql2': Mysql, 'percona': Mysql, 'redis': Redis, 'postgresql': PostgreSQL}
realisations = dict()


def dbhandler(databases):
    databases = [db.strip() for db in databases.split(',')]
    def wrapper(cls):
        for db in databases:
            realisations.update({db: cls})
    return wrapper


@dbhandler('postgresql')
class PostgreSQL(object):

    def __init__(self, server, db=None):
        #Get connection object
        self.server = server
        self.connection = world.db.get_connection(server)
        self.db = db
        self.node = world.cloud.get_node(server)


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
        self.connection = world.db.get_connection(server, db=db)
        self.db = db
        self.node = world.cloud.get_node(server)
        self.snapshotting_type = 'aof' if not os.environ.get('RV_REDIS_SNAPSHOTTING') else 'rdb'

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
            raise AssertionError("Can't move dump to redis-server storage.  Error is: %s" % out[1])
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


@dbhandler('mysql, mysql2, percona')
class MySQL(object):

    def __init__(self, server, db=None):
        #Get connection object
        self.server = server
        self.connection = world.db.get_connection(server)
        self.db = db
        self.node = world.cloud.get_node(server)

    def get_timestamp(self):
        if not self.db:
            raise AssertionError("Can't get data base timestamp for MySQL server, not one database is not used.")
        cursor = self.connection.cursor()
        cursor.execute('USE %s;' % self.db)
        cursor.execute('SELECT * FROM timestamp;')
        return cursor.fetchone()[0]

    def restore(self, src_path, db):

        backups_in_server = self.node.run('ls /tmp/dbrestore/*')[0].split()
        LOG.info('Available backups in server: %s' % backups_in_server)
        path = os.path.join(src_path, db)
        if not path in backups_in_server:
            raise AssertionError('Database %s backup not exist in path %s' % (db, path))
        LOG.info('Creating db: %s in server.' % db)
        world.db.database_create(db, self.server)
        out = self.node.run('mysql -u scalr -p%s %s < %s' % (world.db.password, db, src_path))
        if out[1]:
            raise AssertionError('Get error on restore database %s: %s' % (db, out[1]))
        LOG.info('Data base: %s was successfully created in server.' % db)

    def check_data(self, pattern):
        if not self.db:
            raise AssertionError("Can't get data base timestamp for MySQL server, not one database is not used.")
        cursor = self.connection.cursor()
        cursor.execute('USE %s;' % self.db)
        cursor.execute('SHOW TABLES;')
        tables = [t[0] for t in cursor.fetchall()]
        if not pattern in tables:
            raise AssertionError('Table %s not exist in database: %s' % (pattern, self.db))
        count = cursor.execute('SELECT count(*) FROM %s;' % pattern)
        cursor.close()
        return count


def get_db_handler(db_name):
    try:
        return realisations[db_name]
    except KeyError:
        raise Exception("Can't get data base handler. No such class implemented.")



###Testsuite steps
##################
@step(r'I trigger ([\w]+) creation( on slave)?')
def trigger_creation(step, action, use_slave=None):
    #TODO: if databundle in progress, wait 10 minutes
    action = action.strip()
    use_slave = True if use_slave else False
    info = world.farm.db_info(world.db.db_name)
    if action != 'pmaaccess':
        setattr(world, 'last_%s' % action, info['last_%s' % action])
    if action == 'databundle':
        getattr(world.farm, 'db_create_%s' % action)(world.db.db_name, use_slave=use_slave)
    else:
        getattr(world.farm, 'db_create_%s' % action)(world.db.db_name)
    LOG.info("I'm trigger %s" % action)
    time.sleep(180)

@step(r'I launch ([\w]+) session')
def launch_session(step, service):
    """Step calling the appropriate service method to run it"""
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
    if CONF.main.driver in [Platform.CLOUDSTACK, Platform.IDCF, Platform.KTUCLOUD]:
        LOG.info('Platform is cloudstack-family, backup not doing')
        return True
    info = world.farm.db_info(world.db.db_name)
    if not info['last_%s' % back_type] == getattr(world, 'last_%s' % back_type, 'Never'):
        return
    else:
        raise AssertionError('Previous %s was: %s and last: %s' % (back_type, getattr(world, 'last_%s' % back_type, 'Never'), info['last_%s' % back_type]))


@step(r"I create new database user '([\w\d]+)' on ([\w\d]+)$")
def create_database_user(step, username, serv_as):
    server = getattr(world, serv_as)
    password = generate_random_string(12)
    LOG.info("Create new database user '%s/%s' in server %s" % (username, password, server))
    world.db.user_create(username, password, server)
    world.database_users[username] = password


@step(r"I add small-sized database (.+) on ([\w]+)(?: by user '([\w\d]+)')?")
def having_small_database(step, db_name, serv_as, username=None):
    server = getattr(world, serv_as)
    if username:
        LOG.info("Create database %s in server %s by user %s" % (db_name, server, username))
        world.db.insert_data_to_database(db_name, server, (username, world.database_users[username]))
    else:
        LOG.info("Create database %s in server %s" % (db_name, server))
        world.db.insert_data_to_database(db_name, server)


@step("I create (\d+) databases on ([\w]+)(?: by user '([\w\d]+)')?$")
def create_many_databases(step, db_count, serv_as, username=None):
    server = getattr(world, serv_as)
    credentials = (username, world.database_users[username]) if username else None
    for c in range(int(db_count)):
        db_name = "MDB%s" % c
        LOG.info("Create database %s in server %s" % (db_name, server))
        world.db.database_create(db_name, server, credentials)


@step('([^ .]+) is slave of ([^ .]+)$')
def assert_check_slave(step, slave_serv, master_serv):
    slave = getattr(world, slave_serv)
    master = getattr(world, master_serv)
    info = world.farm.db_info(world.db.db_name)
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
    #TODO: Wait databundle will complete
    action = action.strip()
    getattr(world.farm, 'db_create_%s' % action)(world.db.db_name)
    LOG.info("Create %s" % action)


@step('I create a ([\w]+) databundle on ([\w]+)')
def create_databundle(step, bundle_type, when):
    LOG.info('Create a %s databundle on %s' % (bundle_type, when))
    if when == 'slave':
        use_slave = True
    else:
        use_slave = False
    world.farm.db_create_databundle(world.db.db_name, bundle_type, use_slave=use_slave)


@step("([\w]+)( not)? contains databases? ([\w\d,]+)(?: by user '([\w\d]+)')?$")
def check_database_in_new_server(step, serv_as, has_not, db_name, username=None):
    has_not = has_not and True or False
    time.sleep(5)
    dbs = db_name.split(',')
    if serv_as == 'all':
        world.farm.servers.reload()
        servers = filter(lambda s: s.status == ServerStatus.RUNNING, world.farm.servers)
    else:
        servers = [getattr(world, serv_as)]
    credentials = (username, world.database_users[username]) if username else None
    for server in servers:
        for db in dbs:
            LOG.info('Check database %s in server %s' % (db, server.id))
            world.assert_not_equal(world.db.database_exist(db, server, credentials), not has_not,
                                   (has_not and 'Database %s exist in server %s, but must be erased.  All db: %s'
                                   or 'Database %s not exist in server %s, all db: %s')
                                   % (db_name, server.id, world.db.database_list(server)))


@step("I create database ([\w\d]+) on ([\w\d]+)(?: by user '([\w\d]+)')?")
def create_new_database(step, db_name, serv_as, username=None):
    server = getattr(world, serv_as)
    LOG.info('Create database %s in server %s' % (db_name, server))
    credentials = (username, world.database_users[username]) if username else None
    world.db.database_create(db_name, server, credentials)
    LOG.info('Database was success created')
    time.sleep(60)


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
    last_backup = world.farm.db_info(world.db.db_name)['last_backup']
    last_backup = last_backup - timedelta(seconds=last_backup.second)
    LOG.info('Last backup date is: %s' % last_backup)
    all_backups = IMPL.services.list_backups(world.farm.id)
    last_backup_url = IMPL.services.backup_details(all_backups[last_backup]['backupId'])['links']['1']['path']['dirname']
    last_backup_url = 's3://%s/manifest.json' % last_backup_url
    LOG.info('Last backup URL: %s' % last_backup_url)
    setattr(world, 'last_backup_url', last_backup_url)


@step(r'I know timestamp(?: from ([\w\d]+))? in ([\w\d]+)$')
def save_timestamp(step, db, serv_as):
    #Init params
    server = getattr(world, serv_as)
    db = db if db else ''
    #Get db handler Class
    db_handler_class = get_db_handler(world.db.db_name)
    #Get db backup timestamp
    LOG.info('Getting database %s backup timestamp for %s server' % (db, world.db.db_name))
    backup_timestamp = db_handler_class(server, db).get_timestamp()
    if not backup_timestamp:
        raise AssertionError('Database %s backup timestamp for %s server is empty.' % (db, world.db.db_name))
    #Set timestamp to global
    setattr(world, '%s_backup_timestamp' % world.db.db_name, backup_timestamp)
    LOG.info('Database %s backup timestamp for %s server is: %s' % (db, world.db.db_name, backup_timestamp))

@step('I download backup in ([\w\d]+)')
def download_dump(step, serv_as):
    server = getattr(world, serv_as)
    node = world.cloud.get_node(server)
    node.put_file('/tmp/download_backup.py', resources('scripts/download_backup.py').get())
    if CONF.main.driver == Platform.EC2:
        if node.os[0] == 'redhat' and node.os[1].startswith('5'):
            node.run('python26 /tmp/download_backup.py --platform=ec2 --key=%s --secret=%s --url=%s' % (
                world.cloud.config.libcloud.key, world.cloud.config.libcloud.secret, world.last_backup_url
            ))
        else:
            node.run('python /tmp/download_backup.py --platform=ec2 --key=%s --secret=%s --url=%s' % (
                world.cloud.config.libcloud.key, world.cloud.config.libcloud.secret, world.last_backup_url
            ))
    # elif CONF.main.driver == Platform.GCE:
    #     with open(world.cloud.config.libcloud.key, 'r+') as key:
    #         node.put_file('/tmp/gcs_pk.p12', key.readall())
    #     node.run('python /tmp/download_backup.py --platform=gce --key=%s --url=%s' % (world.cloud.config.libcloud.username,
    #                                                                                   world.last_backup_url))
    # elif CONF.main.driver == Platform.RACKSPACE_US:
    #     node.run('python /tmp/download_backup.py --platform=rackspaceng --key=%s --secret=%s --url=%s' % (
    #         world.cloud.config.libcloud.key, world.cloud.config.libcloud.secret, world.last_backup_url
    #     ))


@step('I delete databases ([\w\d,]+) in ([\w\d]+)$')
def delete_databases(step, databases, serv_as):
    databases = databases.split(',')
    server = getattr(world, serv_as)
    LOG.info('Delete databases  %s in server %s' % (databases, server.id))
    for db in databases:
        LOG.info('Delete database: %s' % db)
        world.db.database_delete(db, server)


@step('I restore databases ([\w\d,]+) in ([\w\d]+)$')
def restore_databases(step, databases, serv_as):
    #Init params
    databases = databases.split(',')
    server = getattr(world, serv_as)
    #Get db handler
    db_handler_class = get_db_handler(world.db.db_name)
    db_handler = db_handler_class(server)
    #Restoring db
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
    if not world.db.database_exist(db, server):
        raise AssertionError('Database %s not exist in server %s' % (db, server.id))
    #Get db handler Class
    db_handler_class = get_db_handler(world.db.db_name)
    #Get db records count
    LOG.info('Getting database %s records count for %s server.' % (db, world.db.db_name))
    count = db_handler_class(server, db).check_data(pattern)
    if not int(count) == int(line_count):
        raise AssertionError('Records count in restored db %s is %s, but must be: %s' % (db, count, line_count))
    LOG.info('Records count in restored db %s is: %s this corresponds to the transferred' % (db, count))


@step('database ([\w\d]+) in ([\w\d]+) has relevant timestamp$')
def check_timestamp(step, db, serv_as):
    #Init params
    server = getattr(world, serv_as)
    db = db if db else ''
    #Get db handler Class
    db_handler_class = get_db_handler(world.db.db_name)
    #Get db backup timestamp
    LOG.info('Getting database %s new backup timestamp for %s server' % (db, world.db.db_name))
    timestamp = db_handler_class(server, db).get_timestamp()
    backup_timestamp = getattr(world, '%s_backup_timestamp' % world.db.db_name)
    if not timestamp == backup_timestamp:
        raise AssertionError('Timestamp is not equivalent: %s != %s' % (timestamp, backup_timestamp))
    #Set timestamp to global
    LOG.info('Database %s new backup timestamp for %s server is equivalent: %s = %s' % (db, world.db.db_name, backup_timestamp, timestamp))


@step(r'([\w\d]+) replication status is ([\w\d]+)')
def verify_replication_status(step, behavior, status):
    wait_until(world.wait_replication_status, args=(behavior, status), error_text="Replication in broken", timeout=600)


@step(r'I (get|verify) ([\w\d]+) master storage id')
def get_storage_id(step, action, db):
    if not CONF.main.storage == 'persistent':
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
