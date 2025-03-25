import argparse
import sys
import os
import string
from time import sleep
from ConfigParser import ConfigParser
from multiprocessing import Pool
import argparse
import random
import time
import os.path

from lib.VMachine import VMachine
from lib.VMManager import VMManagerVS
#from lib.logger import logger
import lib.logger

vm_conf_file = os.path.join("conf", "vms.cfg")
op_conf_file = os.path.join("conf", "operations.cfg")

# get configuration for AV update process (exe, vms, etc)

vmman = VMManagerVS(vm_conf_file)

def update(vm_name):
    try:
        vm = VMachine(vm_conf_file, vm_name)
        
        vmman.revertSnapshot(vm, vm.snapshot)

        sleep(random.randint(10,60))
        vmman.startup(vm)

        sleep(random.randint(60,2*60))
        vmman.reboot(vm)
        
        print "[%s] waiting for Updates" % vm_name
        #sleep(50 * 60)
        sleep(random.randint(10,300))

        print "[%s] Shutdown for reconfigurations" % vm_name
        running = True
        vmman.shutdownUpgrade(vm)

        while running == True:
            sleep(60)
            running = vmman.VMisRunning(vm)


        print "[%s] Startup" % vm_name
        vmman.startup(vm)
        sleep(10 * 60)

        print "[%s] Suspending and saving new snapshot" % vm_name
        vmman.suspend(vm)
        sleep(30)

        vmman.refreshSnapshot(vm)
        return "[%s] Updated!"  % vm_name
    except Exception as e:
        return "ERROR: %s is not updated. Reason: %s" % (vm_name, e)


def revert(vm_name):
    vm = VMachine(vm_conf_file, vm_name)
    vmman.revertSnapshot(vm, vm.snapshot)
    sleep(2)
    return "[*] %s reverted!"

def copy_to_guest(vm, test_dir, filestocopy):
    #lib_dir = "%s\\lib" % test_dir
    #assets_dir = "%s\\assets" % test_dir
    vmavtest = "../VMAVTest/"

    memo = []
    for filetocopy in filestocopy:
        d,f = filetocopy.split("/")
        src = "%s/%s/%s" % (vmavtest, d, f)

        if d == ".":
            dst =  "%s\\%s" % (test_dir, f)
        else:
            dst =  "%s\\%s\\%s" % (test_dir, d, f)

        rdir = "%s\\%s" % (test_dir, d)
        if not memo.__contains__(rdir):
            print "DBG mkdir %s " % (rdir)
            vmman.mkdirInGuest( vm, rdir )
            memo.append( rdir )

        print "DBG copy %s -> %s" % (src, dst)
        vmman.copyFileToGuest(vm, src, dst)

def save_results(vm):
    filename = "results.%s.txt" % vm
    vmman.copyFileFromGuest(vm, "c:\\Users\\avtest\\Desktop\\AVTEST\\results.txt", filename)

    last = "Error save"
    f = open(filename, 'rb')
    for l in f.readlines():
        if l.__contains__(" + "):
            last = l

    return "%s %s" % (vm, last)

def dispatch(vm_name):
    print "go dispatch " , vm_name
    try:
        vm = VMachine(vm_conf_file, vm_name)
        vmman.revertLastSnapshot(vm)
        sleep(5)
        vmman.startup(vm)
        sleep(120)

        test_dir = "C:\\Users\\avtest\\Desktop\\AVTEST"

        vmman.mkdirInGuest(vm, test_dir)

        kind = "silent"
        host = "minotauro"

        buildbat = "build_%s_%s.bat" % (host, kind)

        filestocopy =[  "./%s" % buildbat,
                        "lib/vmavtest.py",
                        "lib/logger.py",
                        "lib/rcs_client.py",
                        "assets/config.json",
                        "assets/keyinject.exe",
                        "assets/meltapp.exe"    ]

        copy_to_guest(vm, test_dir, filestocopy)

        # executing bat synchronized
        vmman.executeCmd(vm, "%s\\%s" % (test_dir, buildbat))
        
        # save results.txt locally
        save_results(vm)

        # suspend & refresh snapshot
        vmman.suspend(vm)
        #sleep(5)
        #vmman.refreshSnapshot(vm, vm.snapshot)
        
        return "[%s] test files dispatched" % vm_name

    except Exception, ex:
            print "exception inside ", ex
            return "Error: cannot dispatch tests for %s" % vm_name

def test_internet(vm_name):
    #try:
    vm = VMachine(vm_conf_file, vm_name)

    vmman.revertSnapshot(vm, vm.snapshot)
    sleep(5)
    vmman.startup(vm)
    sleep(60)
    
    test_dir = "C:\\Users\\avtest\\Desktop\\AVTEST"

    vmman.mkdirInGuest(vm, test_dir)

    filestocopy =[  "./test_internet.bat",
                    "lib/vmavtest.py",
                    "lib/logger.py",
                    "lib/rcs_client.py" ]
    copy_to_guest(vm, test_dir, filestocopy)
    
    # executing bat synchronized
    vmman.executeCmd(vm, "%s\\test_internet.bat" % test_dir)
    return "[%s] dispatched test internet" % vm_name

def test():
    #vm_conf_file = os.path.join("conf", "vms.cfg")
    vm_name = "sophos"

    #vmman = VMManagerVS(vm_conf_file)
    vm = VMachine(vm_conf_file, vm_name)
    #vmman.refreshSnapshot(vm)
    vmman.revertLastSnapshot(vm)

def main():
    lib.logger.setLogger()

    parser = argparse.ArgumentParser(description='AVMonitor master.')

    parser.add_argument('action', choices=['update', 'revert', 'dispatch', 'test', 'test_internet'],
        help="The operation to perform")
    parser.add_argument('--vm', required=False, 
        help="Virtual Machine where execute the operation")
    parser.add_argument('-p', '--pool', default=2, type=int, 
        help="This is the number of parallel process (default 2)")
    args = parser.parse_args()

    if args.action == "test":
        #get_results("eset")
        test()
        exit(0)

    # shut down network
    if args.action == "update":
        os.system('sudo ./net_enable.sh')
        print "[!] Enabling NETWORKING!"
    else:
        os.system('sudo ./net_disable.sh')
        print "[!] Disabling NETWORKING!"

    #vm_conf_file = os.path.join("conf", "vms.cfg")
    op_conf_file = os.path.join("conf", "operations.cfg")

    # get configuration for AV update process (exe, vms, etc)

    #vmman = VMManagerVS(vm_conf_file)

    # get vm names
    c = ConfigParser()
    c.read(op_conf_file)
    vm_names = c.get("test", "machines").split(",")

    pool = Pool(int(args.pool))

    print "[*] selected operation %s" % args.action

    actions = { "update" : update, "revert": revert, 
                "dispatch": dispatch, "test_internet": test_internet }
    r = pool.map_async(actions[args.action], vm_names)
    

    results = r.get()
    print "[*] RESULTS: %s" % results

    timestamp = time.strftime("%Y%m%d_%H%M", time.gmtime())
    if not os.path.exists("reports"):
        os.mkdir("reports")
    with open( "reports/master_%s.txt" % timestamp, "wb") as f:
        f.write("REPORT\n")
        for l in results:
            f.write("%s\n" % l)


if __name__ == "__main__":	
    main()
