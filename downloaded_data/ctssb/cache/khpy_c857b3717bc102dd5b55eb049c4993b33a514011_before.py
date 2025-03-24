import kh_server
from kh_server import *
import math
import os
import stat
import time

class QemuServer(KhServer):
  def __init__(self, configsrc):
    KhServer.__init__(self, configsrc)
    self.config = ConfigParser.SafeConfigParser()
    self.config.read(configsrc)
    self.db_path = self.config.get("database","path")
    self.netpath = os.path.join(self.db_path,
        self.config.get("BaseDirectories","jobdata"))
    self.data_net_path = os.path.join(self.db_path,
        self.config.get("BaseDirectories","job"))

  # cli parser methods   #######################################

  def parse_install(self, parser):
    parser = KhServer.parse_install(self, parser)
    parser.set_defaults(func=self.install)
    return parser

  def parse_clean(self, parser):
    parser = KhServer.parse_clean(self, parser)
    parser.set_defaults(func=self.clean)
    return parser

  def parse_info(self, parser):
    parser = KhServer.parse_info(self, parser)
    parser.set_defaults(func=self.info)
    return parser

#action methods############################################ #

  def server_config(self):
    return KhServerConfig(self.config.get('Qemu', 'server_ip'),
      self.config.get('Qemu', 'server_port'),
      self.config.get('Qemu', 'pidfile_path'),
      self.config.get('Qemu', 'stdin_path'),
      self.config.get('Qemu', 'stdout_path'),
      self.config.get('Qemu', 'stderr_path'))

  def alloc_client(self, nid, count, img, config, option={}):

    # verify  network is legit
    if not self.network_is_valid(nid):
      return "Error: network "+str(nid)+" is not valid"

    nodes = KhServer.alloc_client(self, nid, count)
    jobdir = self.netpath+'/'+str(nid)
    ret = ""
    # allocate nodes
    for node in nodes:
      ret += str(node)+"\n"
      nodedir = os.path.join(jobdir,str(node))
      cmd = self.config.get('Qemu', 'cmd')
      # create tap, all to network bridge 
      mac = self.generate_mac(node)
      ret += mac+"\n"
      user = "root"
      tapcmd = "tunctl -b -u "+user
      tapfile = os.path.join(nodedir, 'tap')
      kh_server.touch(tapfile)
      tap = subprocess.check_output(tapcmd, shell=True).rstrip()
      ret += "tap: "+tap+"\n"
      if os.path.isfile(tapfile) == 1:
        with open(tapfile, "a") as f:
          f.seek(0)
          f.truncate()
          f.write(str(tap))
      br = "br"+str((int(nid) % 256))      
      tapbrcmd = "brctl addif "+br+" "+tap
      subprocess.check_output(tapbrcmd, shell=True)
      tapupcmd = "ip link set "+tap+" up"
      subprocess.check_output(tapupcmd, shell=True)
      # vhost 
      vhost="on"
      if option.has_key('novhost') and option['novhost'] > 0:
          vhost="off"
      # network command
      cmd += " --netdev tap,id=vlan1,ifname="+tap+",script=no,downscript=no,vhost="+vhost+" --device virtio-net,netdev=vlan1,mac="+mac
      # gdb debug 
      if option.has_key('g') and option['g'] > 0:
        gdb_port = int(self.config.get('Qemu', 'gdb_baseport')) + int(node)
        cmd += " -gdb tcp::"+str(gdb_port) 
        ret += "gdb: "+str(gdb_port)+"\n"
      # terminal signal fifo
      if option.has_key('s') and option['s'] > 0:
          finish_cmd = "mkfifo "+nodedir+"/finish"
          subprocess.call(finish_cmd, shell=True)
      ## serial log
      cmd += " -serial stdio"
      # ram
      ram = self.config.get("Qemu", "default_ram") + "G"
      if option.has_key('ram') and option['ram'] > 0:
        ram = str(option['ram']) + "GB"
      cmd += " -m "+ram
      # cpus 
      cpus = self.config.get("Qemu", "default_cpu") 
      if option.has_key('cpu') and option['cpu'] > 0:
        cpus= str(option['cpu']) 
      cmd += " -smp cpus="+cpus
      #numa
      numa = int(self.config.get("Qemu", "default_numa"))
      if option.has_key('numa') and option['numa'] > 0:
        numa= int(option['numa'])
      if numa > 1:
          cpu_per_node = int(math.floor(int(cpus)/int(numa)))
          for i in range(numa):
            cpu_list=""
            if cpu_per_node > 1:
              cpu_list=str(int(i*cpu_per_node))+"-"+str(((i+1)*(cpu_per_node))-1)
            else:
              cpu_list=str(int(i*cpu_per_node))
            cmd += " -numa node,cpus="+cpu_list
      # pid
      cmd += " -pidfile "+nodedir+"/pid"
      # display
      cmd += " -display none "
      # load image
      if option.has_key('iso') and option['iso'] is 1:
        # load ISO image (assumed full OS)
        cmd += " "+str(img)
      else:
        #kernel & config
        cmd += " -kernel "+str(img)
        cmd += " -initrd "+str(config)
      # additional qemu commands
      if option.has_key('cmd') and len(option['cmd']) > 0:
        cmd += " "+option['cmd']+" " 
      # stdout 
      cmd += " >"+nodedir+"/stdout" 
      ret += nodedir+"/stdout\n"
      # stderr 
      cmd += " 2>"+nodedir+"/stderr" 
      ret += nodedir+"/stderr\n"
      # finish
      cmd += "; date >"+nodedir+"/finish;" 
      ret += nodedir+"/finish\n"
      # if perf
      if option.has_key('perf')  :
        perf_cmd = self.config.get('Qemu','perf_cmd')+" -o "+nodedir+"/perf "
        if len(option['perf']) > 0:
          perf_cmd += option['perf']
        cmd = "( "+perf_cmd+" "+cmd+" ) </dev/null &"
        ret += nodedir+"/perf\n"
      else:
        cmd = "("+cmd+")&"
      # cmd file
      with open(nodedir+"/cmd", 'a') as f:
        f.write(cmd+"/n");
      ret += nodedir+"/cmd"
      if option.has_key('t') and option['t'] > 0:
        ret += "\nTEST RUN: QEMU instance was not allocated\n"
      else:
        subprocess.call(cmd, shell=True, executable='/bin/bash')
    # end of per-node for-loop
    return ret

  def network_client(self,uid,option):
    nid = KhServer.network_client(self,uid)
    user = "root"
    tapcmd = "tunctl -b -u "+user
    netmask = "255.255.255.0"
    ip_oct1 = str(int(nid / 256)+1)
    ip_oct2 = str((nid % 256))
    hostip = "10."+ip_oct1+"."+ip_oct2+".1"
    dhcp_start = "10."+ip_oct1+"."+ip_oct2+".50"    
    dhcp_end = "10."+ip_oct1+"."+ip_oct2+".150"    
    netpath = os.path.join(self.netpath, str(nid))

    # configure bridge
    br = "br"+ip_oct2
    brcmd = "brctl addbr "+br
    subprocess.check_output(brcmd, shell=True)
    
    #bring bridge up
    brcmdup = "ifconfig "+br+" "+hostip+" netmask "+netmask+" up"
    subprocess.check_output(brcmdup, shell=True)

    # dhcp on bridge 
    dnscmd = "dnsmasq --pid-file="+netpath+"/dnsmasq --listen-address="+hostip+" -z \
--log-facility="+netpath+"/dnsmasq.log --dhcp-range="+dhcp_start+","+dhcp_end+",12h"
    subprocess.check_output(dnscmd, shell=True)
    return str(nid)+'\n'+str(hostip)

  def _kill(self, path):
    if os.path.exists(path):
      # read pid, remove process
      with open(path, 'r') as f:
        pid = int(f.readline())
        f.close()
      try:
        os.kill(pid,15) 
      except OSError:
        self._print("Warning: process "+str(pid)+" not found")
        pass
    else:
      self._print("Warning: file "+str(path)+" not found")

  def remove_node(self, node):
    # verify  node is legit
    if not self.node_is_valid(node):
      return "Error: node "+str(node)+" is not valid"
    nodes = self.db_node_get(node, '*')
    noderec = nodes[0]
    if noderec is not None:
      netid = noderec[noderec.find(':')+1:len(noderec)]
    else:
      return "Error: no network for node #"+str(node)
    netdir = os.path.join(self.netpath, str(netid))
    nodedir = os.path.join(netdir, str(node))
    self._kill(os.path.join(nodedir,'pid'))
    time.sleep(1)
    # remove tap
    tappath=os.path.join(nodedir, 'tap')
    if os.path.exists(tappath):
      # read pid, remove process
      with open(tappath, 'r') as f:
        tap = f.readline()
        f.close()
        try:
          subprocess.check_output('tunctl -d '+tap, shell=True)
        except subprocess.CalledProcessError:
          pass
    return KhServer.remove_node(self, node, netid)
    
  def remove_network(self, netid):
    # verify  network is legit
    if not self.network_is_valid(netid):
      return "Error: network "+str(netid)+" is not valid"
    # get node records
    netdir = os.path.join(self.netpath, str(netid))
    nodes = self.db_node_get('*', netid)
    for node in nodes:
      nid = node[0:node.find(':')]
      self.remove_node(nid)
    # remove dnsmasq
    self._kill(os.path.join(os.path.join(netdir, 'dnsmasq')))
    # remove bridge 
    br = "br"+str((int(netid) % 256))      
    try:
      subprocess.check_output('ifconfig '+br+' down', shell=True)
    except subprocess.CalledProcessError:
      pass
    try:
      subprocess.check_output('brctl delbr '+br, shell=True)
    except subprocess.CalledProcessError:
      pass
    # remove records
    return KhServer.remove_network(self, netid)

# As per "standards" lookuping up on the net
# the following are locally admined mac address
# ranges:
#
#x2-xx-xx-xx-xx-xx
#x6-xx-xx-xx-xx-xx
#xA-xx-xx-xx-xx-xx
#xE-xx-xx-xx-xx-xx
# format we use 02:f(<inode>):nodenum
# ip then uses prefix 10.0 with last to octets of mac
  def generate_mac(self, nid):
    sig = str(self.inode())
    nodeid = '0x%02x' % int(nid)
    macprefix="02:"+sig[10:12]+':'+sig[12:14]+':'+sig[14:16]+':'+sig[8:10]
    mark = nodeid.find('x')
    return macprefix+':'+nodeid[mark+1:mark+3]
  
  def inode(self):
    path = '/dev/random'
    if path:
     return '0x%016x' % int(os.stat(path)[stat.ST_INO])
    else:
      return None
  
  def vdesock_path(self,nid):
    return os.path.join(os.path.join(self.netpath, str(nid)), 'vde_sock')

  def tap_path(self,nid):
    return os.path.join(os.path.join(self.netpath, str(nid)), 'tap')
