import sys
from time import sleep
import time
import socket

import urllib2
import zipfile
import os.path
import re
import traceback

import subprocess
import Queue
import threading
import argparse
import random
from ConfigParser import ConfigParser
from rcs_client import Rcs_client
import logger

import ctypes
MOUSEEVENTF_MOVE = 0x0001 # mouse move
MOUSEEVENTF_ABSOLUTE = 0x8000 # absolute move
MOUSEEVENTF_MOVEABS = MOUSEEVENTF_MOVE + MOUSEEVENTF_ABSOLUTE

MOUSEEVENTF_LEFTDOWN = 0x0002 # left button down 
MOUSEEVENTF_LEFTUP = 0x0004 # left button up 
MOUSEEVENTF_CLICK = MOUSEEVENTF_LEFTDOWN + MOUSEEVENTF_LEFTUP

def unzip(filename, fdir):
    zfile = zipfile.ZipFile(filename)
    names = []
    for name in zfile.namelist():
        (dirname, filename) = os.path.split(name)
        print "- Decompress: %s / %s" % (fdir, filename) 
        zfile.extract(name, fdir)
        names.append('%s/%s' % (fdir, name))
    return names

def check_internet(address, queue):
    """ True if dns or http are reachable """
    print "- Check connection: %s" % address

    ret = False
    # try:    
    #     #if hasattr(socket, 'setdefaulttimeout'):
    #     #    socket.setdefaulttimeout(5)
    #     response = socket.gethostbyaddr( address )
    #     #print "i resolve dns: ", address
    #     ret |= True
    # except:
    #     ret |= False

    try:    
        if(ret == False):
            response = urllib2.urlopen('http://' + address, timeout = 10)
            #print "i reach url: ", address
            ret |= True
    except:
        ret |= False

    queue.put(ret)


def internet_on():
    ips = [ '87.248.112.181', '173.194.35.176', '176.32.98.166', 'www.reddit.com', 'www.bing.com', 'www.facebook.com','stackoverflow.com']
    q = Queue.Queue()
    for i in ips:
        t = threading.Thread(target = check_internet, args = (i, q) )
        t.daemon = True
        t.start()

    s = [ q.get() for i in ips ]
    return any(s)

def wait_timeout(proc, seconds):
    """Wait for a process to finish, or raise exception after timeout"""
    start = time.time()
    end = start + seconds
    interval = min(seconds / 1000.0, .25)

    print "DBG wait for: %s sec" % seconds
    while True:
        result = proc.poll()
        if result is not None:
            return result
        if time.time() >= end:
            proc.kill()
            print "DBG Process timed out, killed"
            break;
        time.sleep(interval)

class connection:
    host = ""
    user = "avmonitor"
    passwd = "avmonitorp123"

    def __enter__(self):
        print "DBG login %s@%s" % (self.user, self.host)
        self.conn = Rcs_client(self.host, self.user, self.passwd)
        self.conn.login()
        return self.conn

    def __exit__(self, type, value, traceback):
        print "DBG logout"
        self.conn.logout()

class VMAVTest:
    def __init__(self, backend, frontend=None, platform='windows', kind='silent', ftype='desktop', blacklist=[]):
        self.kind = kind
        self.host = (backend, frontend)
        self.hostname = socket.gethostname().replace("win7", "")
        self.blacklist = blacklist
        self.platform = platform
        self.ftype = ftype
        print "DBG blacklist: %s" % self.blacklist

    def _delete_targets(self, operation):
        with connection() as c:
            operation_id, group_id = c.operation(operation)
            print "operation_id: %s" % operation_id
            targets = c.targets(operation_id)
            for t_id in targets:
                print "- Delete target: %s" % t_id
                c.target_delete(t_id) 

    def _create_new_factory(self, operation, target, factory, config):
        with connection() as c:
            operation_id, group_id = c.operation(operation)
            print "DBG type: ", self.ftype, " operation: " , operation, " target: ", target, " factory: ", factory

            # gets all the target with our name in an operation
            targets = c.targets(operation_id, target)

            if len(targets) > 0:
                # keep only one target
                for t in targets[1:]:
                    c.target_delete(t)    

                target_id = targets[0]
                
                agents = c.agents( target_id )

                for agent_id, ident, name in agents:
                    print "DBG   ", agent_id, ident, name
                    if name.startswith(factory):
                        print "- Delete instance: %s %s" % (ident, name)
                        c.instance_delete(agent_id)
            else:
                print "- Create target: %s" % target
                target_id = c.target_create(operation_id, target, 'made by vmavtest at %s' % time.ctime())
            factory_id, ident = c.factory_create(operation_id, target_id, self.ftype, factory, 'made by vmavtestat at %s' % time.ctime())

            with open(config) as f:
                conf = f.read()

            conf =  re.sub(r'"host": ".*"',r'"host": "%s"' % self.host[1], conf)
            c.factory_add_config(factory_id, conf)

            with open('build/config.actual.json','wb') as f:
                f.write(conf)

            return (target, factory_id, ident)

    def _build_agent(self, factory, melt = None, demo = False):
        with connection() as c:
            params = {}
            params['blackberry'] = {'platform': 'blackberry',
                'binary': {'demo': demo},
                'melt': {'appname': 'facebook',
                    'name': 'Facebook Application',
                    'desc': 'Applicazione utilissima di social network',
                    'vendor': 'face inc',
                    'version': '1.2.3'},
                'package': {'type': 'local'}}
                
            params['windows'] = { 'platform': 'windows',
                'binary': { 'demo' : demo, 'admin' : False},
                'melt' : {'scout' : True, 'admin' : False, 'bit64' : True, 'codec' : True },
                'sign' : {}
            }
            params['android'] = { 'platform': 'android',
                'binary': { 'demo' : demo, 'admin' : False},
                'sign' : {},
                'melt' : {}
            }
            params['linux'] = { 'platform': 'linux',
                'binary': { 'demo' : demo, 'admin' : False},
                'melt' : {}
            }
            params['osx'] = {'platform': 'osx',
                'binary': {'demo': demo, 'admin': True},
                'melt' : {}
            }
            params['ios'] = {'platform': 'ios',
                'binary': {'demo': demo },
                'melt' : {}
            }

            params['exploit'] = {"generate": 
                {"platforms": ["windows"], "binary": {"demo": False, "admin": False}, "exploit":"HT-2012-001", 
                "melt":{"demo":False, "scout":True, "admin":False}}, "platform":"exploit", 
                "melt":{"combo":"txt", "filename":"example.txt", "appname":"agent.exe", 
                "input":"000"}, "factory":{"_id":"000"}
            }

            param = params[self.platform]

            try:
                
                filename = 'build/%s/build.zip' % self.platform
                if os.path.exists(filename):
                    os.remove(filename)

                if melt:
                    print "- Melt build with: ", melt
                    r = c.build_melt(factory, param, melt, filename)
                else:
                    print "- Silent build"
                    r = c.build(factory, param, filename)

                contentnames = unzip(filename, "build/%s" % self.platform)

                print "+ SUCCESS SCOUT BUILD"
                return [n for n in contentnames if n.endswith('.exe')]
            except Exception, e:
                print "DBG trace %s" % traceback.format_exc()
                print "+ FAILED SCOUT BUILD"
                raise e
        
    def _execute_build(self, exenames):
        try:
            exe = exenames[0]
            if exe == "build/agent.exe":
                new_exe = "build/SNZEHJJG.exe"
                os.rename(exe, new_exe)
                exe = new_exe

            print "- Execute: " + exe
            subp = subprocess.Popen([exe])
            print "+ SUCCESS SCOUT EXECUTE"
        except Exception, e:
            print "DBG trace %s" % traceback.format_exc()
            print "+ FAILED SCOUT EXECUTE"
            raise e

    def _click_mouse(self, x, y):
            #move first
        x = 65536L * x / ctypes.windll.user32.GetSystemMetrics(0) + 1
        y = 65536L * y / ctypes.windll.user32.GetSystemMetrics(1) + 1
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVEABS, x, y, 0, 0)
        #then click
        ctypes.windll.user32.mouse_event(MOUSEEVENTF_CLICK, 0, 0, 0, 0)


    def _trigger_sync(self, timeout=10):
        subp = subprocess.Popen(['assets/keyinject.exe'])
        wait_timeout(subp, timeout)

    def _check_instance(self, ident):
        with connection() as c:
            instances = c.instances( ident )
            print "DBG instances: %s" % instances

            assert len(instances) <= 1, "too many instances"

            if len(instances) > 0:
                print "+ SUCCESS SCOUT SYNC"
                return instances[0]
            else:

                print "+ FAILED SCOUT SYNC"
                return None

    def _check_elite(self, instance_id):
        with connection() as c:
            info = c.instance_info(instance_id)
            print 'DBG _check_elite %s' % info
            ret = info['upgradable'] == False and info['scout'] == False

            if ret:
                print "+ SUCCESS ELITE SYNC"
            else:
                print "+ FAILED ELITE SYNC"
            return ret

    def _uninstall(self, instance_id):
        with connection() as c:
            c.instance_close(instance_id)

    def _upgrade_elite(self, instance_id):
        with connection() as c:
            ret = c.instance_upgrade(instance_id)
            print "DBG _upgrade_elite: %s" % ret
            info = c.instance_info(instance_id)
            if ret:
                #assert info['upgradable'] == True
                assert info['scout'] == True
            else:
                #assert info['upgradable'] == False
                assert info['scout'] == True
            return ret

    def _list_processes(self):
        return subprocess.Popen(["tasklist"], stdout=subprocess.PIPE).communicate()[0]

    def server_errors(self):
        with connection() as c:
            return c.server_status()['error']

    def create_user_machine(self):
        print "create_user_machine"
        privs = ['ADMIN','ADMIN_USERS','ADMIN_OPERATIONS','ADMIN_TARGETS','ADMIN_AUDIT','ADMIN_LICENSE','SYS','SYS_FRONTEND','SYS_BACKEND','SYS_BACKUP','SYS_INJECTORS','SYS_CONNECTORS','TECH','TECH_FACTORIES','TECH_BUILD','TECH_CONFIG','TECH_EXEC','TECH_UPLOAD','TECH_IMPORT','TECH_NI_RULES','VIEW','VIEW_ALERTS','VIEW_FILESYSTEM','VIEW_EDIT','VIEW_DELETE','VIEW_EXPORT','VIEW_PROFILES'] 
        user_name = "avmonitor_%s" % self.hostname
        connection.user = user_name

        user_exists = False
        try:
            with connection() as c:
                print "LOGIN SUCCESS"
                user_exists = True
        except:
            pass

        if not user_exists:
            connection.user = "avmonitor"
            with connection() as c:
                op, group_id = c.operation('AVMonitor')
                c.user_create( user_name, connection.passwd, privs, group_id)
        connection.user = user_name
        return True

    def execute_elite(self):
        """ build scout and upgrade it to elite """
        instance = self.execute_scout()

        if not instance:
            print "- exiting execute_elite because did't sync"
            return

        print "- Try upgrade to elite"
        upgradable = self._upgrade_elite(instance)
        
        print "DBG %s in %s" % (self.hostname, self.blacklist)
        if not upgradable:
            if self.hostname in self.blacklist:
                print "+ SUCCESS ELITE BLACKLISTED"
            else:
                print "+ FAILED ELITE UPGRADE"
            return
        else:
            if self.hostname in self.blacklist:
                print "+ FAILED ELITE BLACKLISTED"
                return

        print "- Elite, Wait for 25 minutes: %s" % time.ctime() 
        sleep(25 * 60)
        
        elite = self._check_elite( instance )
        if elite:
            print "+ SUCCESS ELITE INSTALL"
            print "- Elite, wait for 4 minute then uninstall: %s" % time.ctime() 
            sleep(60 * 2)
            self._uninstall(instance)
            sleep(60 * 2)
            print "+ SUCCESS ELITE UNINSTALLED"
        else:
            output = self._list_processes()
            print output
            print "+ FAILED ELITE INSTALL"

        print "- Result: %s" % elite

    def execute_scout(self):
        """ build and execute the  """
        factory_id, ident, exe = self.execute_pull()

        self._execute_build(exe)

        print "- Scout, Wait for 6 minutes: %s" % time.ctime() 
        sleep(random.randint(300, 400))

        for tries in range(1,10):
            print "- Scout, Trigger sync for 30 seconds, try %s" % tries
            self._trigger_sync(timeout = 30)

            print "- Scout, wait for 1 minute: %s" % time.ctime() 
            sleep(60 * 1)

            instance = self._check_instance( ident )
            if instance:
                break;

            for i in range(10):
                self._click_mouse(100 + i ,0)

        if not instance:
            output = self._list_processes()
            print output
        print "- Result: %s" % instance
        return instance


    def execute_pull(self):
        """ build and execute the  """
        
        print "- Host: %s %s\n" % (self.hostname, time.ctime())
        operation = 'AVMonitor'
        target = 'VM_%s' % self.hostname
        # desktop_exploit_melt, desktop_scout_
        factory ='%s_%s_%s_%s' % (self.hostname, self.ftype, self.platform, self.kind)
        config = "assets/config_%s.json" % self.ftype

        if not os.path.exists('build'):
            os.mkdir('build')
        if not os.path.exists('build/%s' % self.platform):
            os.mkdir('build/%s' % self.platform)
        target_id, factory_id, ident = self._create_new_factory( operation, target, factory, config)

        print "- Built"

        meltfile = None
        if self.kind == 'melt':
            if self.platform == 'exploit':
                meltfile = 'assets/meltexploit.txt'
            else:
                meltfile = 'assets/meltapp.exe'

        exe = self._build_agent( factory_id, meltfile )

        return factory_id, ident, exe

internet_checked = False
def execute_agent(args, level, platform):
    global internet_checked

    ftype = args.platform_type[platform]
    print "DBG ftype: %s" % ftype

    """ starts a scout """
    if socket.gethostname() != 'zenovm':
        if not internet_checked and internet_on():
            print "== ERROR: I reach Internet =="
            exit(0)
    internet_checked = True

    print "- Network unreachable"

    print "- Server: %s/%s %s" % (args.backend,args.frontend, args.kind)
    vmavtest = VMAVTest( args.backend, args.frontend , platform, args.kind, ftype, args.blacklist )

    if vmavtest.create_user_machine():
        print "+ SUCCESS USER CONNET"
        if not vmavtest.server_errors():
            print "+ SUCCESS SERVER CONNECT"
        
            action = {"elite": vmavtest.execute_elite, "scout": vmavtest.execute_scout, "pull": vmavtest.execute_pull}
            action[level]()
        else:
            print "+ FAILED SERVER ERRORS"
    else:
         print "+ FAILED USER CREATE"

def elite(args):
    """ starts a scout """
    execute_agent(args, "elite", args.platform)

def scout(args):
    """ starts a scout """
    execute_agent(args, "scout", args.platform)

def pull(args):
    """ starts a scout """
    if args.platform == "all":
        for platform in args.platform_type.keys():
            if platform == "exploit":
                continue
            print "pulling platform ", platform
            try:
                execute_agent(args, "pull", platform)
                print "+ PULLED %s" % platform
            except Exception, ex:
                print "ERROR %s" % ex
    else:
        execute_agent(args, "pull", args.platform)

def test(args):
    connection.host = "rcs-minotauro"
    #ret = unzip('build/agent.zip')
    #print ret
    output = subprocess.Popen(["tasklist"], stdout=subprocess.PIPE).communicate()[0]
    print output

def internet(args):
    print time.ctime()
    print "internet on: ", internet_on()
    print time.ctime()

def clean(args):
    operation = 'AVMonitor'
    print "- Server: %s/%s %s" % (args.backend,args.frontend, args.kind)
    vmavtest = VMAVTest( args.backend, args.frontend , args.kind )
    vmavtest._delete_targets(operation)
   
def main():
    platform_desktop = [ 'windows', 'linux', 'osx', 'exploit' ]
    platform_mobile =  [ 'android', 'blackberry', 'ios' ]

    platform_type = {}
    for v in platform_desktop:
        platform_type[v]='desktop'
    for v in platform_mobile:
        platform_type[v]='mobile' 

    op_conf_file = os.path.join("conf", "vmavtest.cfg")
    c = ConfigParser()
    c.read(op_conf_file)
    blacklist = c.get("cfg", "blacklist").split(",")

    parser = argparse.ArgumentParser(description='AVMonitor avtest.')

    parser.add_argument('action', choices=['scout', 'elite', 'internet', 'test', 'clean', 'pull']) #'elite'
    parser.add_argument('-p', '--platform', default='windows')
    parser.add_argument('-b', '--backend')
    parser.add_argument('-f', '--frontend')
    parser.add_argument('-k', '--kind', choices=['silent', 'melt'])
    parser.add_argument('-v', '--verbose', action='store_true', default=False, help="Verbose")

    parser.set_defaults(blacklist =  blacklist)
    parser.set_defaults(platform_type =  platform_type)

    args = parser.parse_args()

    logger.setLogger(debug = args.verbose)
    connection.host = args.backend
    
    actions = {'scout': scout, 'elite': elite, 'internet': internet, 'test': test, 'clean': clean, 'pull': pull}
    actions[args.action](args)

if __name__ == "__main__":
    main()
    