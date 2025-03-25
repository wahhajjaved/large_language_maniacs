#!/usr/bin/python
#

# Copyright (C) 2006, 2007 Google Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.


"""Module implementing the commands used by gnt-* programs."""

# pylint: disable-msg=W0613,W0201

import os
import os.path
import sha
import socket
import time
import tempfile
import re
import platform

from ganeti import rpc
from ganeti import ssh
from ganeti import logger
from ganeti import utils
from ganeti import errors
from ganeti import hypervisor
from ganeti import config
from ganeti import constants
from ganeti import objects
from ganeti import opcodes
from ganeti import ssconf

class LogicalUnit(object):
  """Logical Unit base class..

  Subclasses must follow these rules:
    - implement CheckPrereq which also fills in the opcode instance
      with all the fields (even if as None)
    - implement Exec
    - implement BuildHooksEnv
    - redefine HPATH and HTYPE
    - optionally redefine their run requirements (REQ_CLUSTER,
      REQ_MASTER); note that all commands require root permissions

  """
  HPATH = None
  HTYPE = None
  _OP_REQP = []
  REQ_CLUSTER = True
  REQ_MASTER = True

  def __init__(self, processor, op, cfg, sstore):
    """Constructor for LogicalUnit.

    This needs to be overriden in derived classes in order to check op
    validity.

    """
    self.processor = processor
    self.op = op
    self.cfg = cfg
    self.sstore = sstore
    for attr_name in self._OP_REQP:
      attr_val = getattr(op, attr_name, None)
      if attr_val is None:
        raise errors.OpPrereqError, ("Required parameter '%s' missing" %
                                     attr_name)
    if self.REQ_CLUSTER:
      if not cfg.IsCluster():
        raise errors.OpPrereqError, ("Cluster not initialized yet,"
                                     " use 'gnt-cluster init' first.")
      if self.REQ_MASTER:
        master = cfg.GetMaster()
        if master != socket.gethostname():
          raise errors.OpPrereqError, ("Commands must be run on the master"
                                       " node %s" % master)

  def CheckPrereq(self):
    """Check prerequisites for this LU.

    This method should check that the prerequisites for the execution
    of this LU are fulfilled. It can do internode communication, but
    it should be idempotent - no cluster or system changes are
    allowed.

    The method should raise errors.OpPrereqError in case something is
    not fulfilled. Its return value is ignored.

    This method should also update all the parameters of the opcode to
    their canonical form; e.g. a short node name must be fully
    expanded after this method has successfully completed (so that
    hooks, logging, etc. work correctly).

    """
    raise NotImplementedError

  def Exec(self, feedback_fn):
    """Execute the LU.

    This method should implement the actual work. It should raise
    errors.OpExecError for failures that are somewhat dealt with in
    code, or expected.

    """
    raise NotImplementedError

  def BuildHooksEnv(self):
    """Build hooks environment for this LU.

    This method should return a three-node tuple consisting of: a dict
    containing the environment that will be used for running the
    specific hook for this LU, a list of node names on which the hook
    should run before the execution, and a list of node names on which
    the hook should run after the execution.

    The keys of the dict must not have 'GANETI_' prefixed as this will
    be handled in the hooks runner. Also note additional keys will be
    added by the hooks runner. If the LU doesn't define any
    environment, an empty dict (and not None) should be returned.

    As for the node lists, the master should not be included in the
    them, as it will be added by the hooks runner in case this LU
    requires a cluster to run on (otherwise we don't have a node
    list). No nodes should be returned as an empty list (and not
    None).

    Note that if the HPATH for a LU class is None, this function will
    not be called.

    """
    raise NotImplementedError


class NoHooksLU(LogicalUnit):
  """Simple LU which runs no hooks.

  This LU is intended as a parent for other LogicalUnits which will
  run no hooks, in order to reduce duplicate code.

  """
  HPATH = None
  HTYPE = None

  def BuildHooksEnv(self):
    """Build hooks env.

    This is a no-op, since we don't run hooks.

    """
    return


def _UpdateEtcHosts(fullnode, ip):
  """Ensure a node has a correct entry in /etc/hosts.

  Args:
    fullnode - Fully qualified domain name of host. (str)
    ip       - IPv4 address of host (str)

  """
  node = fullnode.split(".", 1)[0]

  f = open('/etc/hosts', 'r+')

  inthere = False

  save_lines = []
  add_lines = []
  removed = False

  while True:
    rawline = f.readline()

    if not rawline:
      # End of file
      break

    line = rawline.split('\n')[0]

    # Strip off comments
    line = line.split('#')[0]

    if not line:
      # Entire line was comment, skip
      save_lines.append(rawline)
      continue

    fields = line.split()

    haveall = True
    havesome = False
    for spec in [ ip, fullnode, node ]:
      if spec not in fields:
        haveall = False
      if spec in fields:
        havesome = True

    if haveall:
      inthere = True
      save_lines.append(rawline)
      continue

    if havesome and not haveall:
      # Line (old, or manual?) which is missing some.  Remove.
      removed = True
      continue

    save_lines.append(rawline)

  if not inthere:
    add_lines.append('%s\t%s %s\n' % (ip, fullnode, node))

  if removed:
    if add_lines:
      save_lines = save_lines + add_lines

    # We removed a line, write a new file and replace old.
    fd, tmpname = tempfile.mkstemp('tmp', 'hosts_', '/etc')
    newfile = os.fdopen(fd, 'w')
    newfile.write(''.join(save_lines))
    newfile.close()
    os.rename(tmpname, '/etc/hosts')

  elif add_lines:
    # Simply appending a new line will do the trick.
    f.seek(0, 2)
    for add in add_lines:
      f.write(add)

  f.close()


def _UpdateKnownHosts(fullnode, ip, pubkey):
  """Ensure a node has a correct known_hosts entry.

  Args:
    fullnode - Fully qualified domain name of host. (str)
    ip       - IPv4 address of host (str)
    pubkey   - the public key of the cluster

  """
  if os.path.exists('/etc/ssh/ssh_known_hosts'):
    f = open('/etc/ssh/ssh_known_hosts', 'r+')
  else:
    f = open('/etc/ssh/ssh_known_hosts', 'w+')

  inthere = False

  save_lines = []
  add_lines = []
  removed = False

  while True:
    rawline = f.readline()
    logger.Debug('read %s' % (repr(rawline),))

    if not rawline:
      # End of file
      break

    line = rawline.split('\n')[0]

    parts = line.split(' ')
    fields = parts[0].split(',')
    key = parts[2]

    haveall = True
    havesome = False
    for spec in [ ip, fullnode ]:
      if spec not in fields:
        haveall = False
      if spec in fields:
        havesome = True

    logger.Debug("key, pubkey = %s." % (repr((key, pubkey)),))
    if haveall and key == pubkey:
      inthere = True
      save_lines.append(rawline)
      logger.Debug("Keeping known_hosts '%s'." % (repr(rawline),))
      continue

    if havesome and (not haveall or key != pubkey):
      removed = True
      logger.Debug("Discarding known_hosts '%s'." % (repr(rawline),))
      continue

    save_lines.append(rawline)

  if not inthere:
    add_lines.append('%s,%s ssh-rsa %s\n' % (fullnode, ip, pubkey))
    logger.Debug("Adding known_hosts '%s'." % (repr(add_lines[-1]),))

  if removed:
    save_lines = save_lines + add_lines

    # Write a new file and replace old.
    fd, tmpname = tempfile.mkstemp('tmp', 'ssh_known_hosts_', '/etc/ssh')
    newfile = os.fdopen(fd, 'w')
    newfile.write(''.join(save_lines))
    newfile.close()
    logger.Debug("Wrote new known_hosts.")
    os.rename(tmpname, '/etc/ssh/ssh_known_hosts')

  elif add_lines:
    # Simply appending a new line will do the trick.
    f.seek(0, 2)
    for add in add_lines:
      f.write(add)

  f.close()


def _HasValidVG(vglist, vgname):
  """Checks if the volume group list is valid.

  A non-None return value means there's an error, and the return value
  is the error message.

  """
  vgsize = vglist.get(vgname, None)
  if vgsize is None:
    return "volume group '%s' missing" % vgname
  elif vgsize < 20480:
    return ("volume group '%s' too small (20480MiB required, %dMib found" %
            vgname, vgsize)
  return None


def _InitSSHSetup(node):
  """Setup the SSH configuration for the cluster.


  This generates a dsa keypair for root, adds the pub key to the
  permitted hosts and adds the hostkey to its own known hosts.

  Args:
    node: the name of this host as a fqdn

  """
  utils.RemoveFile('/root/.ssh/known_hosts')

  if os.path.exists('/root/.ssh/id_dsa'):
    utils.CreateBackup('/root/.ssh/id_dsa')
  if os.path.exists('/root/.ssh/id_dsa.pub'):
    utils.CreateBackup('/root/.ssh/id_dsa.pub')

  utils.RemoveFile('/root/.ssh/id_dsa')
  utils.RemoveFile('/root/.ssh/id_dsa.pub')

  result = utils.RunCmd(["ssh-keygen", "-t", "dsa",
                         "-f", "/root/.ssh/id_dsa",
                         "-q", "-N", ""])
  if result.failed:
    raise errors.OpExecError, ("could not generate ssh keypair, error %s" %
                               result.output)

  f = open('/root/.ssh/id_dsa.pub', 'r')
  try:
    utils.AddAuthorizedKey('/root/.ssh/authorized_keys', f.read(8192))
  finally:
    f.close()


def _InitGanetiServerSetup(ss):
  """Setup the necessary configuration for the initial node daemon.

  This creates the nodepass file containing the shared password for
  the cluster and also generates the SSL certificate.

  """
  # Create pseudo random password
  randpass = sha.new(os.urandom(64)).hexdigest()
  # and write it into sstore
  ss.SetKey(ss.SS_NODED_PASS, randpass)

  result = utils.RunCmd(["openssl", "req", "-new", "-newkey", "rsa:1024",
                         "-days", str(365*5), "-nodes", "-x509",
                         "-keyout", constants.SSL_CERT_FILE,
                         "-out", constants.SSL_CERT_FILE, "-batch"])
  if result.failed:
    raise errors.OpExecError, ("could not generate server ssl cert, command"
                               " %s had exitcode %s and error message %s" %
                               (result.cmd, result.exit_code, result.output))

  os.chmod(constants.SSL_CERT_FILE, 0400)

  result = utils.RunCmd([constants.NODE_INITD_SCRIPT, "restart"])

  if result.failed:
    raise errors.OpExecError, ("could not start the node daemon, command %s"
                               " had exitcode %s and error %s" %
                               (result.cmd, result.exit_code, result.output))


def _InitClusterInterface(fullname, name, ip):
  """Initialize the master startup script.

  """
  f = file(constants.CLUSTER_NAME_FILE, 'w')
  f.write("%s\n" % fullname)
  f.close()

  f = file(constants.MASTER_INITD_SCRIPT, 'w')
  f.write ("#!/bin/sh\n")
  f.write ("\n")
  f.write ("# Start Ganeti Master Virtual Address\n")
  f.write ("\n")
  f.write ("DESC=\"Ganeti Master IP\"\n")
  f.write ("MASTERNAME=\"%s\"\n" % name)
  f.write ("MASTERIP=\"%s\"\n" % ip)
  f.write ("case \"$1\" in\n")
  f.write ("  start)\n")
  f.write ("    if fping -q -c 3 ${MASTERIP} &>/dev/null; then\n")
  f.write ("        echo \"$MASTERNAME no-go - there is already a master.\"\n")
  f.write ("        rm -f %s\n" % constants.MASTER_CRON_LINK)
  f.write ("        scp ${MASTERNAME}:%s %s\n" %
           (constants.CLUSTER_CONF_FILE, constants.CLUSTER_CONF_FILE))
  f.write ("    else\n")
  f.write ("        echo -n \"Starting $DESC: \"\n")
  f.write ("        ip address add ${MASTERIP}/32 dev xen-br0"
           " label xen-br0:0\n")
  f.write ("        arping -q -U -c 3 -I xen-br0 -s ${MASTERIP} ${MASTERIP}\n")
  f.write ("        echo \"$MASTERNAME.\"\n")
  f.write ("    fi\n")
  f.write ("    ;;\n")
  f.write ("  stop)\n")
  f.write ("    echo -n \"Stopping $DESC: \"\n")
  f.write ("    ip address del ${MASTERIP}/32 dev xen-br0\n")
  f.write ("    echo \"$MASTERNAME.\"\n")
  f.write ("    ;;\n")
  f.write ("  *)\n")
  f.write ("    echo \"Usage: $0 {start|stop}\" >&2\n")
  f.write ("    exit 1\n")
  f.write ("    ;;\n")
  f.write ("esac\n")
  f.write ("\n")
  f.write ("exit 0\n")
  f.flush()
  os.fsync(f.fileno())
  f.close()
  os.chmod(constants.MASTER_INITD_SCRIPT, 0755)


class LUInitCluster(LogicalUnit):
  """Initialise the cluster.

  """
  HPATH = "cluster-init"
  HTYPE = constants.HTYPE_CLUSTER
  _OP_REQP = ["cluster_name", "hypervisor_type", "vg_name", "mac_prefix",
              "def_bridge"]
  REQ_CLUSTER = False

  def BuildHooksEnv(self):
    """Build hooks env.

    Notes: Since we don't require a cluster, we must manually add
    ourselves in the post-run node list.

    """

    env = {"CLUSTER": self.op.cluster_name,
           "MASTER": self.hostname}
    return env, [], [self.hostname['hostname_full']]

  def CheckPrereq(self):
    """Verify that the passed name is a valid one.

    """
    if config.ConfigWriter.IsCluster():
      raise errors.OpPrereqError, ("Cluster is already initialised")

    hostname_local = socket.gethostname()
    self.hostname = hostname = utils.LookupHostname(hostname_local)
    if not hostname:
      raise errors.OpPrereqError, ("Cannot resolve my own hostname ('%s')" %
                                   hostname_local)

    self.clustername = clustername = utils.LookupHostname(self.op.cluster_name)
    if not clustername:
      raise errors.OpPrereqError, ("Cannot resolve given cluster name ('%s')"
                                   % self.op.cluster_name)

    result = utils.RunCmd(["fping", "-S127.0.0.1", "-q", hostname['ip']])
    if result.failed:
      raise errors.OpPrereqError, ("Inconsistency: this host's name resolves"
                                   " to %s,\nbut this ip address does not"
                                   " belong to this host."
                                   " Aborting." % hostname['ip'])

    secondary_ip = getattr(self.op, "secondary_ip", None)
    if secondary_ip and not utils.IsValidIP(secondary_ip):
      raise errors.OpPrereqError, ("Invalid secondary ip given")
    if secondary_ip and secondary_ip != hostname['ip']:
      result = utils.RunCmd(["fping", "-S127.0.0.1", "-q", secondary_ip])
      if result.failed:
        raise errors.OpPrereqError, ("You gave %s as secondary IP,\n"
                                     "but it does not belong to this host." %
                                     secondary_ip)
    self.secondary_ip = secondary_ip

    # checks presence of the volume group given
    vgstatus = _HasValidVG(utils.ListVolumeGroups(), self.op.vg_name)

    if vgstatus:
      raise errors.OpPrereqError, ("Error: %s" % vgstatus)

    if not re.match("^[0-9a-z]{2}:[0-9a-z]{2}:[0-9a-z]{2}$",
                    self.op.mac_prefix):
      raise errors.OpPrereqError, ("Invalid mac prefix given '%s'" %
                                   self.op.mac_prefix)

    if self.op.hypervisor_type not in hypervisor.VALID_HTYPES:
      raise errors.OpPrereqError, ("Invalid hypervisor type given '%s'" %
                                   self.op.hypervisor_type)

  def Exec(self, feedback_fn):
    """Initialize the cluster.

    """
    clustername = self.clustername
    hostname = self.hostname

    # adds the cluste name file and master startup script
    _InitClusterInterface(clustername['hostname_full'],
                          clustername['hostname'],
                          clustername['ip'])

    # set up the simple store
    ss = ssconf.SimpleStore()
    ss.SetKey(ss.SS_HYPERVISOR, self.op.hypervisor_type)

    # set up the inter-node password and certificate
    _InitGanetiServerSetup(ss)

    # start the master ip
    rpc.call_node_start_master(hostname['hostname_full'])

    # set up ssh config and /etc/hosts
    f = open('/etc/ssh/ssh_host_rsa_key.pub', 'r')
    try:
      sshline = f.read()
    finally:
      f.close()
    sshkey = sshline.split(" ")[1]

    _UpdateEtcHosts(hostname['hostname_full'],
                    hostname['ip'],
                    )

    _UpdateKnownHosts(hostname['hostname_full'],
                      hostname['ip'],
                      sshkey,
                      )

    _InitSSHSetup(hostname['hostname'])

    # init of cluster config file
    cfgw = config.ConfigWriter()
    cfgw.InitConfig(hostname['hostname'], hostname['ip'], self.secondary_ip,
                    clustername['hostname'], sshkey, self.op.mac_prefix,
                    self.op.vg_name, self.op.def_bridge)


class LUDestroyCluster(NoHooksLU):
  """Logical unit for destroying the cluster.

  """
  _OP_REQP = []

  def CheckPrereq(self):
    """Check prerequisites.

    This checks whether the cluster is empty.

    Any errors are signalled by raising errors.OpPrereqError.

    """
    master = self.cfg.GetMaster()

    nodelist = self.cfg.GetNodeList()
    if len(nodelist) > 0 and nodelist != [master]:
        raise errors.OpPrereqError, ("There are still %d node(s) in "
                                     "this cluster." % (len(nodelist) - 1))

  def Exec(self, feedback_fn):
    """Destroys the cluster.

    """
    utils.CreateBackup('/root/.ssh/id_dsa')
    utils.CreateBackup('/root/.ssh/id_dsa.pub')
    rpc.call_node_leave_cluster(self.cfg.GetMaster())


class LUVerifyCluster(NoHooksLU):
  """Verifies the cluster status.

  """
  _OP_REQP = []

  def _VerifyNode(self, node, file_list, local_cksum, vglist, node_result,
                  remote_version, feedback_fn):
    """Run multiple tests against a node.

    Test list:
      - compares ganeti version
      - checks vg existance and size > 20G
      - checks config file checksum
      - checks ssh to other nodes

    Args:
      node: name of the node to check
      file_list: required list of files
      local_cksum: dictionary of local files and their checksums
    """
    # compares ganeti version
    local_version = constants.PROTOCOL_VERSION
    if not remote_version:
      feedback_fn(" - ERROR: connection to %s failed" % (node))
      return True

    if local_version != remote_version:
      feedback_fn("  - ERROR: sw version mismatch: master %s, node(%s) %s" %
                      (local_version, node, remote_version))
      return True

    # checks vg existance and size > 20G

    bad = False
    if not vglist:
      feedback_fn("  - ERROR: unable to check volume groups on node %s." %
                      (node,))
      bad = True
    else:
      vgstatus = _HasValidVG(vglist, self.cfg.GetVGName())
      if vgstatus:
        feedback_fn("  - ERROR: %s on node %s" % (vgstatus, node))
        bad = True

    # checks config file checksum
    # checks ssh to any

    if 'filelist' not in node_result:
      bad = True
      feedback_fn("  - ERROR: node hasn't returned file checksum data")
    else:
      remote_cksum = node_result['filelist']
      for file_name in file_list:
        if file_name not in remote_cksum:
          bad = True
          feedback_fn("  - ERROR: file '%s' missing" % file_name)
        elif remote_cksum[file_name] != local_cksum[file_name]:
          bad = True
          feedback_fn("  - ERROR: file '%s' has wrong checksum" % file_name)

    if 'nodelist' not in node_result:
      bad = True
      feedback_fn("  - ERROR: node hasn't returned node connectivity data")
    else:
      if node_result['nodelist']:
        bad = True
        for node in node_result['nodelist']:
          feedback_fn("  - ERROR: communication with node '%s': %s" %
                          (node, node_result['nodelist'][node]))
    hyp_result = node_result.get('hypervisor', None)
    if hyp_result is not None:
      feedback_fn("  - ERROR: hypervisor verify failure: '%s'" % hyp_result)
    return bad

  def _VerifyInstance(self, instance, node_vol_is, node_instance, feedback_fn):
    """Verify an instance.

    This function checks to see if the required block devices are
    available on the instance's node.

    """
    bad = False

    instancelist = self.cfg.GetInstanceList()
    if not instance in instancelist:
      feedback_fn("  - ERROR: instance %s not in instance list %s" %
                      (instance, instancelist))
      bad = True

    instanceconfig = self.cfg.GetInstanceInfo(instance)
    node_current = instanceconfig.primary_node

    node_vol_should = {}
    instanceconfig.MapLVsByNode(node_vol_should)

    for node in node_vol_should:
      for volume in node_vol_should[node]:
        if node not in node_vol_is or volume not in node_vol_is[node]:
          feedback_fn("  - ERROR: volume %s missing on node %s" %
                          (volume, node))
          bad = True

    if not instanceconfig.status == 'down':
      if not instance in node_instance[node_current]:
        feedback_fn("  - ERROR: instance %s not running on node %s" %
                        (instance, node_current))
        bad = True

    for node in node_instance:
      if (not node == node_current):
        if instance in node_instance[node]:
          feedback_fn("  - ERROR: instance %s should not run on node %s" %
                          (instance, node))
          bad = True

    return not bad

  def _VerifyOrphanVolumes(self, node_vol_should, node_vol_is, feedback_fn):
    """Verify if there are any unknown volumes in the cluster.

    The .os, .swap and backup volumes are ignored. All other volumes are
    reported as unknown.

    """
    bad = False

    for node in node_vol_is:
      for volume in node_vol_is[node]:
        if node not in node_vol_should or volume not in node_vol_should[node]:
          feedback_fn("  - ERROR: volume %s on node %s should not exist" %
                      (volume, node))
          bad = True
    return bad


  def _VerifyOrphanInstances(self, instancelist, node_instance, feedback_fn):
    """Verify the list of running instances.

    This checks what instances are running but unknown to the cluster.

    """
    bad = False
    for node in node_instance:
      for runninginstance in node_instance[node]:
        if runninginstance not in instancelist:
          feedback_fn("  - ERROR: instance %s on node %s should not exist" %
                          (runninginstance, node))
          bad = True
    return bad

  def _VerifyNodeConfigFiles(self, ismaster, node, file_list, feedback_fn):
    """Verify the list of node config files"""

    bad = False
    for file_name in constants.MASTER_CONFIGFILES:
      if ismaster and file_name not in file_list:
        feedback_fn("  - ERROR: master config file %s missing from master"
                    " node %s" % (file_name, node))
        bad = True
      elif not ismaster and file_name in file_list:
        feedback_fn("  - ERROR: master config file %s should not exist"
                    " on non-master node %s" % (file_name, node))
        bad = True

    for file_name in constants.NODE_CONFIGFILES:
      if file_name not in file_list:
        feedback_fn("  - ERROR: config file %s missing from node %s" %
                    (file_name, node))
        bad = True

    return bad

  def CheckPrereq(self):
    """Check prerequisites.

    This has no prerequisites.

    """
    pass

  def Exec(self, feedback_fn):
    """Verify integrity of cluster, performing various test on nodes.

    """
    bad = False
    feedback_fn("* Verifying global settings")
    self.cfg.VerifyConfig()

    master = self.cfg.GetMaster()
    vg_name = self.cfg.GetVGName()
    nodelist = utils.NiceSort(self.cfg.GetNodeList())
    instancelist = utils.NiceSort(self.cfg.GetInstanceList())
    node_volume = {}
    node_instance = {}

    # FIXME: verify OS list
    # do local checksums
    file_names = constants.CLUSTER_CONF_FILES
    local_checksums = utils.FingerprintFiles(file_names)

    feedback_fn("* Gathering data (%d nodes)" % len(nodelist))
    all_configfile = rpc.call_configfile_list(nodelist)
    all_volumeinfo = rpc.call_volume_list(nodelist, vg_name)
    all_instanceinfo = rpc.call_instance_list(nodelist)
    all_vglist = rpc.call_vg_list(nodelist)
    node_verify_param = {
      'filelist': file_names,
      'nodelist': nodelist,
      'hypervisor': None,
      }
    all_nvinfo = rpc.call_node_verify(nodelist, node_verify_param)
    all_rversion = rpc.call_version(nodelist)

    for node in nodelist:
      feedback_fn("* Verifying node %s" % node)
      result = self._VerifyNode(node, file_names, local_checksums,
                                all_vglist[node], all_nvinfo[node],
                                all_rversion[node], feedback_fn)
      bad = bad or result
      # node_configfile
      nodeconfigfile = all_configfile[node]

      if not nodeconfigfile:
        feedback_fn("  - ERROR: connection to %s failed" % (node))
        bad = True
        continue

      bad = bad or self._VerifyNodeConfigFiles(node==master, node,
                                               nodeconfigfile, feedback_fn)

      # node_volume
      volumeinfo = all_volumeinfo[node]

      if type(volumeinfo) != dict:
        feedback_fn("  - ERROR: connection to %s failed" % (node,))
        bad = True
        continue

      node_volume[node] = volumeinfo

      # node_instance
      nodeinstance = all_instanceinfo[node]
      if type(nodeinstance) != list:
        feedback_fn("  - ERROR: connection to %s failed" % (node,))
        bad = True
        continue

      node_instance[node] = nodeinstance

    node_vol_should = {}

    for instance in instancelist:
      feedback_fn("* Verifying instance %s" % instance)
      result =  self._VerifyInstance(instance, node_volume, node_instance,
                                     feedback_fn)
      bad = bad or result

      inst_config = self.cfg.GetInstanceInfo(instance)

      inst_config.MapLVsByNode(node_vol_should)

    feedback_fn("* Verifying orphan volumes")
    result = self._VerifyOrphanVolumes(node_vol_should, node_volume,
                                       feedback_fn)
    bad = bad or result

    feedback_fn("* Verifying remaining instances")
    result = self._VerifyOrphanInstances(instancelist, node_instance,
                                         feedback_fn)
    bad = bad or result

    return int(bad)


def _WaitForSync(cfgw, instance, oneshot=False, unlock=False):
  """Sleep and poll for an instance's disk to sync.

  """
  if not instance.disks:
    return True

  if not oneshot:
    logger.ToStdout("Waiting for instance %s to sync disks." % instance.name)

  node = instance.primary_node

  for dev in instance.disks:
    cfgw.SetDiskID(dev, node)

  retries = 0
  while True:
    max_time = 0
    done = True
    cumul_degraded = False
    rstats = rpc.call_blockdev_getmirrorstatus(node, instance.disks)
    if not rstats:
      logger.ToStderr("Can't get any data from node %s" % node)
      retries += 1
      if retries >= 10:
        raise errors.RemoteError, ("Can't contact node %s for mirror data,"
                                   " aborting." % node)
      time.sleep(6)
      continue
    retries = 0
    for i in range(len(rstats)):
      mstat = rstats[i]
      if mstat is None:
        logger.ToStderr("Can't compute data for node %s/%s" %
                        (node, instance.disks[i].iv_name))
        continue
      perc_done, est_time, is_degraded = mstat
      cumul_degraded = cumul_degraded or (is_degraded and perc_done is None)
      if perc_done is not None:
        done = False
        if est_time is not None:
          rem_time = "%d estimated seconds remaining" % est_time
          max_time = est_time
        else:
          rem_time = "no time estimate"
        logger.ToStdout("- device %s: %5.2f%% done, %s" %
                        (instance.disks[i].iv_name, perc_done, rem_time))
    if done or oneshot:
      break

    if unlock:
      utils.Unlock('cmd')
    try:
      time.sleep(min(60, max_time))
    finally:
      if unlock:
        utils.Lock('cmd')

  if done:
    logger.ToStdout("Instance %s's disks are in sync." % instance.name)
  return not cumul_degraded


def _CheckDiskConsistency(cfgw, dev, node, on_primary):
  """Check that mirrors are not degraded.

  """

  cfgw.SetDiskID(dev, node)

  result = True
  if on_primary or dev.AssembleOnSecondary():
    rstats = rpc.call_blockdev_find(node, dev)
    if not rstats:
      logger.ToStderr("Can't get any data from node %s" % node)
      result = False
    else:
      result = result and (not rstats[5])
  if dev.children:
    for child in dev.children:
      result = result and _CheckDiskConsistency(cfgw, child, node, on_primary)

  return result


class LUDiagnoseOS(NoHooksLU):
  """Logical unit for OS diagnose/query.

  """
  _OP_REQP = []

  def CheckPrereq(self):
    """Check prerequisites.

    This always succeeds, since this is a pure query LU.

    """
    return

  def Exec(self, feedback_fn):
    """Compute the list of OSes.

    """
    node_list = self.cfg.GetNodeList()
    node_data = rpc.call_os_diagnose(node_list)
    if node_data == False:
      raise errors.OpExecError, "Can't gather the list of OSes"
    return node_data


class LURemoveNode(LogicalUnit):
  """Logical unit for removing a node.

  """
  HPATH = "node-remove"
  HTYPE = constants.HTYPE_NODE
  _OP_REQP = ["node_name"]

  def BuildHooksEnv(self):
    """Build hooks env.

    This doesn't run on the target node in the pre phase as a failed
    node would not allows itself to run.

    """
    all_nodes = self.cfg.GetNodeList()
    all_nodes.remove(self.op.node_name)
    return {"NODE_NAME": self.op.node_name}, all_nodes, all_nodes

  def CheckPrereq(self):
    """Check prerequisites.

    This checks:
     - the node exists in the configuration
     - it does not have primary or secondary instances
     - it's not the master

    Any errors are signalled by raising errors.OpPrereqError.

    """

    node = self.cfg.GetNodeInfo(self.cfg.ExpandNodeName(self.op.node_name))
    if node is None:
      logger.Error("Error: Node '%s' is unknown." % self.op.node_name)
      return 1

    instance_list = self.cfg.GetInstanceList()

    masternode = self.cfg.GetMaster()
    if node.name == masternode:
      raise errors.OpPrereqError, ("Node is the master node,"
                                   " you need to failover first.")

    for instance_name in instance_list:
      instance = self.cfg.GetInstanceInfo(instance_name)
      if node.name == instance.primary_node:
        raise errors.OpPrereqError, ("Instance %s still running on the node,"
                                     " please remove first." % instance_name)
      if node.name in instance.secondary_nodes:
        raise errors.OpPrereqError, ("Instance %s has node as a secondary,"
                                     " please remove first." % instance_name)
    self.op.node_name = node.name
    self.node = node

  def Exec(self, feedback_fn):
    """Removes the node from the cluster.

    """
    node = self.node
    logger.Info("stopping the node daemon and removing configs from node %s" %
                node.name)

    rpc.call_node_leave_cluster(node.name)

    ssh.SSHCall(node.name, 'root', "%s stop" % constants.NODE_INITD_SCRIPT)

    logger.Info("Removing node %s from config" % node.name)

    self.cfg.RemoveNode(node.name)


class LUQueryNodes(NoHooksLU):
  """Logical unit for querying nodes.

  """
  _OP_REQP = ["output_fields"]

  def CheckPrereq(self):
    """Check prerequisites.

    This checks that the fields required are valid output fields.

    """
    self.static_fields = frozenset(["name", "pinst", "sinst", "pip", "sip"])
    self.dynamic_fields = frozenset(["dtotal", "dfree",
                                     "mtotal", "mnode", "mfree"])
    self.all_fields = self.static_fields | self.dynamic_fields

    if not self.all_fields.issuperset(self.op.output_fields):
      raise errors.OpPrereqError, ("Unknown output fields selected: %s"
                                   % ",".join(frozenset(self.op.output_fields).
                                              difference(self.all_fields)))


  def Exec(self, feedback_fn):
    """Computes the list of nodes and their attributes.

    """
    nodenames = utils.NiceSort(self.cfg.GetNodeList())
    nodelist = [self.cfg.GetNodeInfo(name) for name in nodenames]


    # begin data gathering

    if self.dynamic_fields.intersection(self.op.output_fields):
      live_data = {}
      node_data = rpc.call_node_info(nodenames, self.cfg.GetVGName())
      for name in nodenames:
        nodeinfo = node_data.get(name, None)
        if nodeinfo:
          live_data[name] = {
            "mtotal": utils.TryConvert(int, nodeinfo['memory_total']),
            "mnode": utils.TryConvert(int, nodeinfo['memory_dom0']),
            "mfree": utils.TryConvert(int, nodeinfo['memory_free']),
            "dtotal": utils.TryConvert(int, nodeinfo['vg_size']),
            "dfree": utils.TryConvert(int, nodeinfo['vg_free']),
            }
        else:
          live_data[name] = {}
    else:
      live_data = dict.fromkeys(nodenames, {})

    node_to_primary = dict.fromkeys(nodenames, 0)
    node_to_secondary = dict.fromkeys(nodenames, 0)

    if "pinst" in self.op.output_fields or "sinst" in self.op.output_fields:
      instancelist = self.cfg.GetInstanceList()

      for instance in instancelist:
        instanceinfo = self.cfg.GetInstanceInfo(instance)
        node_to_primary[instanceinfo.primary_node] += 1
        for secnode in instanceinfo.secondary_nodes:
          node_to_secondary[secnode] += 1

    # end data gathering

    output = []
    for node in nodelist:
      node_output = []
      for field in self.op.output_fields:
        if field == "name":
          val = node.name
        elif field == "pinst":
          val = node_to_primary[node.name]
        elif field == "sinst":
          val = node_to_secondary[node.name]
        elif field == "pip":
          val = node.primary_ip
        elif field == "sip":
          val = node.secondary_ip
        elif field in self.dynamic_fields:
          val = live_data[node.name].get(field, "?")
        else:
          raise errors.ParameterError, field
        val = str(val)
        node_output.append(val)
      output.append(node_output)

    return output


def _CheckNodesDirs(node_list, paths):
  """Verify if the given nodes have the same files.

  Args:
    node_list: the list of node names to check
    paths: the list of directories to checksum and compare

  Returns:
    list of (node, different_file, message); if empty, the files are in sync

  """
  file_names = []
  for dir_name in paths:
    flist = [os.path.join(dir_name, name) for name in os.listdir(dir_name)]
    flist = [name for name in flist if os.path.isfile(name)]
    file_names.extend(flist)

  local_checksums = utils.FingerprintFiles(file_names)

  results = []
  verify_params = {'filelist': file_names}
  all_node_results = rpc.call_node_verify(node_list, verify_params)
  for node_name in node_list:
    node_result = all_node_results.get(node_name, False)
    if not node_result or 'filelist' not in node_result:
      results.append((node_name, "'all files'", "node communication error"))
      continue
    remote_checksums = node_result['filelist']
    for fname in local_checksums:
      if fname not in remote_checksums:
        results.append((node_name, fname, "missing file"))
      elif remote_checksums[fname] != local_checksums[fname]:
        results.append((node_name, fname, "wrong checksum"))
  return results


class LUAddNode(LogicalUnit):
  """Logical unit for adding node to the cluster.

  """
  HPATH = "node-add"
  HTYPE = constants.HTYPE_NODE
  _OP_REQP = ["node_name"]

  def BuildHooksEnv(self):
    """Build hooks env.

    This will run on all nodes before, and on all nodes + the new node after.

    """
    env = {
      "NODE_NAME": self.op.node_name,
      "NODE_PIP": self.op.primary_ip,
      "NODE_SIP": self.op.secondary_ip,
      }
    nodes_0 = self.cfg.GetNodeList()
    nodes_1 = nodes_0 + [self.op.node_name, ]
    return env, nodes_0, nodes_1

  def CheckPrereq(self):
    """Check prerequisites.

    This checks:
     - the new node is not already in the config
     - it is resolvable
     - its parameters (single/dual homed) matches the cluster

    Any errors are signalled by raising errors.OpPrereqError.

    """
    node_name = self.op.node_name
    cfg = self.cfg

    dns_data = utils.LookupHostname(node_name)
    if not dns_data:
      raise errors.OpPrereqError, ("Node %s is not resolvable" % node_name)

    node = dns_data['hostname']
    primary_ip = self.op.primary_ip = dns_data['ip']
    secondary_ip = getattr(self.op, "secondary_ip", None)
    if secondary_ip is None:
      secondary_ip = primary_ip
    if not utils.IsValidIP(secondary_ip):
      raise errors.OpPrereqError, ("Invalid secondary IP given")
    self.op.secondary_ip = secondary_ip
    node_list = cfg.GetNodeList()
    if node in node_list:
      raise errors.OpPrereqError, ("Node %s is already in the configuration"
                                   % node)

    for existing_node_name in node_list:
      existing_node = cfg.GetNodeInfo(existing_node_name)
      if (existing_node.primary_ip == primary_ip or
          existing_node.secondary_ip == primary_ip or
          existing_node.primary_ip == secondary_ip or
          existing_node.secondary_ip == secondary_ip):
        raise errors.OpPrereqError, ("New node ip address(es) conflict with"
                                     " existing node %s" % existing_node.name)

    # check that the type of the node (single versus dual homed) is the
    # same as for the master
    myself = cfg.GetNodeInfo(cfg.GetMaster())
    master_singlehomed = myself.secondary_ip == myself.primary_ip
    newbie_singlehomed = secondary_ip == primary_ip
    if master_singlehomed != newbie_singlehomed:
      if master_singlehomed:
        raise errors.OpPrereqError, ("The master has no private ip but the"
                                     " new node has one")
      else:
        raise errors.OpPrereqError ("The master has a private ip but the"
                                    " new node doesn't have one")

    # checks reachablity
    command = ["fping", "-q", primary_ip]
    result = utils.RunCmd(command)
    if result.failed:
      raise errors.OpPrereqError, ("Node not reachable by ping")

    if not newbie_singlehomed:
      # check reachability from my secondary ip to newbie's secondary ip
      command = ["fping", "-S%s" % myself.secondary_ip, "-q", secondary_ip]
      result = utils.RunCmd(command)
      if result.failed:
        raise errors.OpPrereqError, ("Node secondary ip not reachable by ping")

    self.new_node = objects.Node(name=node,
                                 primary_ip=primary_ip,
                                 secondary_ip=secondary_ip)

  def Exec(self, feedback_fn):
    """Adds the new node to the cluster.

    """
    new_node = self.new_node
    node = new_node.name

    # set up inter-node password and certificate and restarts the node daemon
    gntpass = self.sstore.GetNodeDaemonPassword()
    if not re.match('^[a-zA-Z0-9.]{1,64}$', gntpass):
      raise errors.OpExecError, ("ganeti password corruption detected")
    f = open(constants.SSL_CERT_FILE)
    try:
      gntpem = f.read(8192)
    finally:
      f.close()
    # in the base64 pem encoding, neither '!' nor '.' are valid chars,
    # so we use this to detect an invalid certificate; as long as the
    # cert doesn't contain this, the here-document will be correctly
    # parsed by the shell sequence below
    if re.search('^!EOF\.', gntpem, re.MULTILINE):
      raise errors.OpExecError, ("invalid PEM encoding in the SSL certificate")
    if not gntpem.endswith("\n"):
      raise errors.OpExecError, ("PEM must end with newline")
    logger.Info("copy cluster pass to %s and starting the node daemon" % node)

    # remove first the root's known_hosts file
    utils.RemoveFile("/root/.ssh/known_hosts")
    # and then connect with ssh to set password and start ganeti-noded
    # note that all the below variables are sanitized at this point,
    # either by being constants or by the checks above
    ss = self.sstore
    mycommand = ("umask 077 && "
                 "echo '%s' > '%s' && "
                 "cat > '%s' << '!EOF.' && \n"
                 "%s!EOF.\n%s restart" %
                 (gntpass, ss.KeyToFilename(ss.SS_NODED_PASS),
                  constants.SSL_CERT_FILE, gntpem,
                  constants.NODE_INITD_SCRIPT))

    result = ssh.SSHCall(node, 'root', mycommand, batch=False, ask_key=True)
    if result.failed:
      raise errors.OpExecError, ("Remote command on node %s, error: %s,"
                                 " output: %s" %
                                 (node, result.fail_reason, result.output))

    # check connectivity
    time.sleep(4)

    result = rpc.call_version([node])[node]
    if result:
      if constants.PROTOCOL_VERSION == result:
        logger.Info("communication to node %s fine, sw version %s match" %
                    (node, result))
      else:
        raise errors.OpExecError, ("Version mismatch master version %s,"
                                   " node version %s" %
                                   (constants.PROTOCOL_VERSION, result))
    else:
      raise errors.OpExecError, ("Cannot get version from the new node")

    # setup ssh on node
    logger.Info("copy ssh key to node %s" % node)
    keyarray = []
    keyfiles = ["/etc/ssh/ssh_host_dsa_key", "/etc/ssh/ssh_host_dsa_key.pub",
                "/etc/ssh/ssh_host_rsa_key", "/etc/ssh/ssh_host_rsa_key.pub",
                "/root/.ssh/id_dsa", "/root/.ssh/id_dsa.pub"]

    for i in keyfiles:
      f = open(i, 'r')
      try:
        keyarray.append(f.read())
      finally:
        f.close()

    result = rpc.call_node_add(node, keyarray[0], keyarray[1], keyarray[2],
                               keyarray[3], keyarray[4], keyarray[5])

    if not result:
      raise errors.OpExecError, ("Cannot transfer ssh keys to the new node")

    # Add node to our /etc/hosts, and add key to known_hosts
    _UpdateEtcHosts(new_node.name, new_node.primary_ip)
    _UpdateKnownHosts(new_node.name, new_node.primary_ip,
                      self.cfg.GetHostKey())

    if new_node.secondary_ip != new_node.primary_ip:
      result = ssh.SSHCall(node, "root",
                           "fping -S 127.0.0.1 -q %s" % new_node.secondary_ip)
      if result.failed:
        raise errors.OpExecError, ("Node claims it doesn't have the"
                                   " secondary ip you gave (%s).\n"
                                   "Please fix and re-run this command." %
                                   new_node.secondary_ip)

    # Distribute updated /etc/hosts and known_hosts to all nodes,
    # including the node just added
    myself = self.cfg.GetNodeInfo(self.cfg.GetMaster())
    dist_nodes = self.cfg.GetNodeList() + [node]
    if myself.name in dist_nodes:
      dist_nodes.remove(myself.name)

    logger.Debug("Copying hosts and known_hosts to all nodes")
    for fname in ("/etc/hosts", "/etc/ssh/ssh_known_hosts"):
      result = rpc.call_upload_file(dist_nodes, fname)
      for to_node in dist_nodes:
        if not result[to_node]:
          logger.Error("copy of file %s to node %s failed" %
                       (fname, to_node))

    to_copy = [constants.MASTER_CRON_FILE,
               constants.MASTER_INITD_SCRIPT,
               constants.CLUSTER_NAME_FILE]
    to_copy.extend(ss.GetFileList())
    for fname in to_copy:
      if not ssh.CopyFileToNode(node, fname):
        logger.Error("could not copy file %s to node %s" % (fname, node))

    logger.Info("adding node %s to cluster.conf" % node)
    self.cfg.AddNode(new_node)


class LUMasterFailover(LogicalUnit):
  """Failover the master node to the current node.

  This is a special LU in that it must run on a non-master node.

  """
  HPATH = "master-failover"
  HTYPE = constants.HTYPE_CLUSTER
  REQ_MASTER = False
  _OP_REQP = []

  def BuildHooksEnv(self):
    """Build hooks env.

    This will run on the new master only in the pre phase, and on all
    the nodes in the post phase.

    """
    env = {
      "NEW_MASTER": self.new_master,
      "OLD_MASTER": self.old_master,
      }
    return env, [self.new_master], self.cfg.GetNodeList()

  def CheckPrereq(self):
    """Check prerequisites.

    This checks that we are not already the master.

    """
    self.new_master = socket.gethostname()

    self.old_master = self.cfg.GetMaster()

    if self.old_master == self.new_master:
      raise errors.OpPrereqError, ("This commands must be run on the node"
                                   " where you want the new master to be.\n"
                                   "%s is already the master" %
                                   self.old_master)

  def Exec(self, feedback_fn):
    """Failover the master node.

    This command, when run on a non-master node, will cause the current
    master to cease being master, and the non-master to become new
    master.

    """

    #TODO: do not rely on gethostname returning the FQDN
    logger.Info("setting master to %s, old master: %s" %
                (self.new_master, self.old_master))

    if not rpc.call_node_stop_master(self.old_master):
      logger.Error("could disable the master role on the old master"
                   " %s, please disable manually" % self.old_master)

    if not rpc.call_node_start_master(self.new_master):
      logger.Error("could not start the master role on the new master"
                   " %s, please check" % self.new_master)

    self.cfg.SetMaster(self.new_master)


class LUQueryClusterInfo(NoHooksLU):
  """Query cluster configuration.

  """
  _OP_REQP = []

  def CheckPrereq(self):
    """No prerequsites needed for this LU.

    """
    pass

  def Exec(self, feedback_fn):
    """Return cluster config.

    """
    instances = [self.cfg.GetInstanceInfo(name)
                 for name in self.cfg.GetInstanceList()]
    result = {
      "name": self.cfg.GetClusterName(),
      "software_version": constants.RELEASE_VERSION,
      "protocol_version": constants.PROTOCOL_VERSION,
      "config_version": constants.CONFIG_VERSION,
      "os_api_version": constants.OS_API_VERSION,
      "export_version": constants.EXPORT_VERSION,
      "master": self.cfg.GetMaster(),
      "architecture": (platform.architecture()[0], platform.machine()),
      "instances": [(instance.name, instance.primary_node)
                    for instance in instances],
      "nodes": self.cfg.GetNodeList(),
      }

    return result


class LUClusterCopyFile(NoHooksLU):
  """Copy file to cluster.

  """
  _OP_REQP = ["nodes", "filename"]

  def CheckPrereq(self):
    """Check prerequisites.

    It should check that the named file exists and that the given list
    of nodes is valid.

    """
    if not os.path.exists(self.op.filename):
      raise errors.OpPrereqError("No such filename '%s'" % self.op.filename)
    if self.op.nodes:
      nodes = self.op.nodes
    else:
      nodes = self.cfg.GetNodeList()
    self.nodes = []
    for node in nodes:
      nname = self.cfg.ExpandNodeName(node)
      if nname is None:
        raise errors.OpPrereqError, ("Node '%s' is unknown." % node)
      self.nodes.append(nname)

  def Exec(self, feedback_fn):
    """Copy a file from master to some nodes.

    Args:
      opts - class with options as members
      args - list containing a single element, the file name
    Opts used:
      nodes - list containing the name of target nodes; if empty, all nodes

    """
    filename = self.op.filename

    myname = socket.gethostname()

    for node in self.nodes:
      if node == myname:
        continue
      if not ssh.CopyFileToNode(node, filename):
        logger.Error("Copy of file %s to node %s failed" % (filename, node))


class LUDumpClusterConfig(NoHooksLU):
  """Return a text-representation of the cluster-config.

  """
  _OP_REQP = []

  def CheckPrereq(self):
    """No prerequisites.

    """
    pass

  def Exec(self, feedback_fn):
    """Dump a representation of the cluster config to the standard output.

    """
    return self.cfg.DumpConfig()


class LURunClusterCommand(NoHooksLU):
  """Run a command on some nodes.

  """
  _OP_REQP = ["command", "nodes"]

  def CheckPrereq(self):
    """Check prerequisites.

    It checks that the given list of nodes is valid.

    """
    if self.op.nodes:
      nodes = self.op.nodes
    else:
      nodes = self.cfg.GetNodeList()
    self.nodes = []
    for node in nodes:
      nname = self.cfg.ExpandNodeName(node)
      if nname is None:
        raise errors.OpPrereqError, ("Node '%s' is unknown." % node)
      self.nodes.append(nname)

  def Exec(self, feedback_fn):
    """Run a command on some nodes.

    """
    data = []
    for node in self.nodes:
      result = utils.RunCmd(["ssh", node, self.op.command])
      data.append((node, result.cmd, result.output, result.exit_code))

    return data


class LUActivateInstanceDisks(NoHooksLU):
  """Bring up an instance's disks.

  """
  _OP_REQP = ["instance_name"]

  def CheckPrereq(self):
    """Check prerequisites.

    This checks that the instance is in the cluster.

    """
    instance = self.cfg.GetInstanceInfo(
      self.cfg.ExpandInstanceName(self.op.instance_name))
    if instance is None:
      raise errors.OpPrereqError, ("Instance '%s' not known" %
                                   self.op.instance_name)
    self.instance = instance


  def Exec(self, feedback_fn):
    """Activate the disks.

    """
    disks_ok, disks_info = _AssembleInstanceDisks(self.instance, self.cfg)
    if not disks_ok:
      raise errors.OpExecError, ("Cannot activate block devices")

    return disks_info


def _AssembleInstanceDisks(instance, cfg, ignore_secondaries=False):
  """Prepare the block devices for an instance.

  This sets up the block devices on all nodes.

  Args:
    instance: a ganeti.objects.Instance object
    ignore_secondaries: if true, errors on secondary nodes won't result
                        in an error return from the function

  Returns:
    false if the operation failed
    list of (host, instance_visible_name, node_visible_name) if the operation
         suceeded with the mapping from node devices to instance devices
  """
  device_info = []
  disks_ok = True
  for inst_disk in instance.disks:
    master_result = None
    for node, node_disk in inst_disk.ComputeNodeTree(instance.primary_node):
      cfg.SetDiskID(node_disk, node)
      is_primary = node == instance.primary_node
      result = rpc.call_blockdev_assemble(node, node_disk, is_primary)
      if not result:
        logger.Error("could not prepare block device %s on node %s (is_pri"
                     "mary=%s)" % (inst_disk.iv_name, node, is_primary))
        if is_primary or not ignore_secondaries:
          disks_ok = False
      if is_primary:
        master_result = result
    device_info.append((instance.primary_node, inst_disk.iv_name,
                        master_result))

  return disks_ok, device_info


class LUDeactivateInstanceDisks(NoHooksLU):
  """Shutdown an instance's disks.

  """
  _OP_REQP = ["instance_name"]

  def CheckPrereq(self):
    """Check prerequisites.

    This checks that the instance is in the cluster.

    """
    instance = self.cfg.GetInstanceInfo(
      self.cfg.ExpandInstanceName(self.op.instance_name))
    if instance is None:
      raise errors.OpPrereqError, ("Instance '%s' not known" %
                                   self.op.instance_name)
    self.instance = instance

  def Exec(self, feedback_fn):
    """Deactivate the disks

    """
    instance = self.instance
    ins_l = rpc.call_instance_list([instance.primary_node])
    ins_l = ins_l[instance.primary_node]
    if not type(ins_l) is list:
      raise errors.OpExecError, ("Can't contact node '%s'" %
                                 instance.primary_node)

    if self.instance.name in ins_l:
      raise errors.OpExecError, ("Instance is running, can't shutdown"
                                 " block devices.")

    _ShutdownInstanceDisks(instance, self.cfg)


def _ShutdownInstanceDisks(instance, cfg, ignore_primary=False):
  """Shutdown block devices of an instance.

  This does the shutdown on all nodes of the instance.

  If the ignore_primary is false, errors on the primary node are
  ignored.

  """
  result = True
  for disk in instance.disks:
    for node, top_disk in disk.ComputeNodeTree(instance.primary_node):
      cfg.SetDiskID(top_disk, node)
      if not rpc.call_blockdev_shutdown(node, top_disk):
        logger.Error("could not shutdown block device %s on node %s" %
                     (disk.iv_name, node))
        if not ignore_primary or node != instance.primary_node:
          result = False
  return result


class LUStartupInstance(LogicalUnit):
  """Starts an instance.

  """
  HPATH = "instance-start"
  HTYPE = constants.HTYPE_INSTANCE
  _OP_REQP = ["instance_name", "force"]

  def BuildHooksEnv(self):
    """Build hooks env.

    This runs on master, primary and secondary nodes of the instance.

    """
    env = {
      "INSTANCE_NAME": self.op.instance_name,
      "INSTANCE_PRIMARY": self.instance.primary_node,
      "INSTANCE_SECONDARIES": " ".join(self.instance.secondary_nodes),
      "FORCE": self.op.force,
      }
    nl = ([self.cfg.GetMaster(), self.instance.primary_node] +
          list(self.instance.secondary_nodes))
    return env, nl, nl

  def CheckPrereq(self):
    """Check prerequisites.

    This checks that the instance is in the cluster.

    """
    instance = self.cfg.GetInstanceInfo(
      self.cfg.ExpandInstanceName(self.op.instance_name))
    if instance is None:
      raise errors.OpPrereqError, ("Instance '%s' not known" %
                                   self.op.instance_name)

    # check bridges existance
    brlist = [nic.bridge for nic in instance.nics]
    if not rpc.call_bridges_exist(instance.primary_node, brlist):
      raise errors.OpPrereqError, ("one or more target bridges %s does not"
                                   " exist on destination node '%s'" %
                                   (brlist, instance.primary_node))

    self.instance = instance
    self.op.instance_name = instance.name

  def Exec(self, feedback_fn):
    """Start the instance.

    """
    instance = self.instance
    force = self.op.force
    extra_args = getattr(self.op, "extra_args", "")

    node_current = instance.primary_node

    nodeinfo = rpc.call_node_info([node_current], self.cfg.GetVGName())
    if not nodeinfo:
      raise errors.OpExecError, ("Could not contact node %s for infos" %
                                 (node_current))

    freememory = nodeinfo[node_current]['memory_free']
    memory = instance.memory
    if memory > freememory:
      raise errors.OpExecError, ("Not enough memory to start instance"
                                 " %s on node %s"
                                 " needed %s MiB, available %s MiB" %
                                 (instance.name, node_current, memory,
                                  freememory))

    disks_ok, dummy = _AssembleInstanceDisks(instance, self.cfg,
                                             ignore_secondaries=force)
    if not disks_ok:
      _ShutdownInstanceDisks(instance, self.cfg)
      if not force:
        logger.Error("If the message above refers to a secondary node,"
                     " you can retry the operation using '--force'.")
      raise errors.OpExecError, ("Disk consistency error")

    if not rpc.call_instance_start(node_current, instance, extra_args):
      _ShutdownInstanceDisks(instance, self.cfg)
      raise errors.OpExecError, ("Could not start instance")

    self.cfg.MarkInstanceUp(instance.name)


class LUShutdownInstance(LogicalUnit):
  """Shutdown an instance.

  """
  HPATH = "instance-stop"
  HTYPE = constants.HTYPE_INSTANCE
  _OP_REQP = ["instance_name"]

  def BuildHooksEnv(self):
    """Build hooks env.

    This runs on master, primary and secondary nodes of the instance.

    """
    env = {
      "INSTANCE_NAME": self.op.instance_name,
      "INSTANCE_PRIMARY": self.instance.primary_node,
      "INSTANCE_SECONDARIES": " ".join(self.instance.secondary_nodes),
      }
    nl = ([self.cfg.GetMaster(), self.instance.primary_node] +
          list(self.instance.secondary_nodes))
    return env, nl, nl

  def CheckPrereq(self):
    """Check prerequisites.

    This checks that the instance is in the cluster.

    """
    instance = self.cfg.GetInstanceInfo(
      self.cfg.ExpandInstanceName(self.op.instance_name))
    if instance is None:
      raise errors.OpPrereqError, ("Instance '%s' not known" %
                                   self.op.instance_name)
    self.instance = instance

  def Exec(self, feedback_fn):
    """Shutdown the instance.

    """
    instance = self.instance
    node_current = instance.primary_node
    if not rpc.call_instance_shutdown(node_current, instance):
      logger.Error("could not shutdown instance")

    self.cfg.MarkInstanceDown(instance.name)
    _ShutdownInstanceDisks(instance, self.cfg)


class LURemoveInstance(LogicalUnit):
  """Remove an instance.

  """
  HPATH = "instance-remove"
  HTYPE = constants.HTYPE_INSTANCE
  _OP_REQP = ["instance_name"]

  def BuildHooksEnv(self):
    """Build hooks env.

    This runs on master, primary and secondary nodes of the instance.

    """
    env = {
      "INSTANCE_NAME": self.op.instance_name,
      "INSTANCE_PRIMARY": self.instance.primary_node,
      "INSTANCE_SECONDARIES": " ".join(self.instance.secondary_nodes),
      }
    nl = ([self.cfg.GetMaster(), self.instance.primary_node] +
          list(self.instance.secondary_nodes))
    return env, nl, nl

  def CheckPrereq(self):
    """Check prerequisites.

    This checks that the instance is in the cluster.

    """
    instance = self.cfg.GetInstanceInfo(
      self.cfg.ExpandInstanceName(self.op.instance_name))
    if instance is None:
      raise errors.OpPrereqError, ("Instance '%s' not known" %
                                   self.op.instance_name)
    self.instance = instance

  def Exec(self, feedback_fn):
    """Remove the instance.

    """
    instance = self.instance
    logger.Info("shutting down instance %s on node %s" %
                (instance.name, instance.primary_node))

    if not rpc.call_instance_shutdown(instance.primary_node, instance):
      raise errors.OpExecError, ("Could not shutdown instance %s on node %s" %
                                 (instance.name, instance.primary_node))

    logger.Info("removing block devices for instance %s" % instance.name)

    _RemoveDisks(instance, self.cfg)

    logger.Info("removing instance %s out of cluster config" % instance.name)

    self.cfg.RemoveInstance(instance.name)


class LUQueryInstances(NoHooksLU):
  """Logical unit for querying instances.

  """
  OP_REQP = ["output_fields"]

  def CheckPrereq(self):
    """Check prerequisites.

    This checks that the fields required are valid output fields.

    """

    self.static_fields = frozenset(["name", "os", "pnode", "snodes",
                                    "admin_state", "admin_ram",
                                    "disk_template", "ip", "mac", "bridge"])
    self.dynamic_fields = frozenset(["oper_state", "oper_ram"])
    self.all_fields = self.static_fields | self.dynamic_fields

    if not self.all_fields.issuperset(self.op.output_fields):
      raise errors.OpPrereqError, ("Unknown output fields selected: %s"
                                   % ",".join(frozenset(self.op.output_fields).
                                              difference(self.all_fields)))

  def Exec(self, feedback_fn):
    """Computes the list of nodes and their attributes.

    """

    instance_names = utils.NiceSort(self.cfg.GetInstanceList())
    instance_list = [self.cfg.GetInstanceInfo(iname) for iname
                     in instance_names]

    # begin data gathering

    nodes = frozenset([inst.primary_node for inst in instance_list])

    bad_nodes = []
    if self.dynamic_fields.intersection(self.op.output_fields):
      live_data = {}
      node_data = rpc.call_all_instances_info(nodes)
      for name in nodes:
        result = node_data[name]
        if result:
          live_data.update(result)
        elif result == False:
          bad_nodes.append(name)
        # else no instance is alive
    else:
      live_data = dict([(name, {}) for name in instance_names])

    # end data gathering

    output = []
    for instance in instance_list:
      iout = []
      for field in self.op.output_fields:
        if field == "name":
          val = instance.name
        elif field == "os":
          val = instance.os
        elif field == "pnode":
          val = instance.primary_node
        elif field == "snodes":
          val = ",".join(instance.secondary_nodes) or "-"
        elif field == "admin_state":
          if instance.status == "down":
            val = "no"
          else:
            val = "yes"
        elif field == "oper_state":
          if instance.primary_node in bad_nodes:
            val = "(node down)"
          else:
            if live_data.get(instance.name):
              val = "running"
            else:
              val = "stopped"
        elif field == "admin_ram":
          val = instance.memory
        elif field == "oper_ram":
          if instance.primary_node in bad_nodes:
            val = "(node down)"
          elif instance.name in live_data:
            val = live_data[instance.name].get("memory", "?")
          else:
            val = "-"
        elif field == "disk_template":
          val = instance.disk_template
        elif field == "ip":
          val = instance.nics[0].ip
        elif field == "bridge":
          val = instance.nics[0].bridge
        elif field == "mac":
          val = instance.nics[0].mac
        else:
          raise errors.ParameterError, field
        val = str(val)
        iout.append(val)
      output.append(iout)

    return output


class LUFailoverInstance(LogicalUnit):
  """Failover an instance.

  """
  HPATH = "instance-failover"
  HTYPE = constants.HTYPE_INSTANCE
  _OP_REQP = ["instance_name", "ignore_consistency"]

  def BuildHooksEnv(self):
    """Build hooks env.

    This runs on master, primary and secondary nodes of the instance.

    """
    env = {
      "INSTANCE_NAME": self.op.instance_name,
      "INSTANCE_PRIMARY": self.instance.primary_node,
      "INSTANCE_SECONDARIES": " ".join(self.instance.secondary_nodes),
      "IGNORE_CONSISTENCY": self.op.ignore_consistency,
      }
    nl = [self.cfg.GetMaster()] + list(self.instance.secondary_nodes)
    return env, nl, nl

  def CheckPrereq(self):
    """Check prerequisites.

    This checks that the instance is in the cluster.

    """
    instance = self.cfg.GetInstanceInfo(
      self.cfg.ExpandInstanceName(self.op.instance_name))
    if instance is None:
      raise errors.OpPrereqError, ("Instance '%s' not known" %
                                   self.op.instance_name)

    # check memory requirements on the secondary node
    target_node = instance.secondary_nodes[0]
    nodeinfo = rpc.call_node_info([target_node], self.cfg.GetVGName())
    info = nodeinfo.get(target_node, None)
    if not info:
      raise errors.OpPrereqError, ("Cannot get current information"
                                   " from node '%s'" % nodeinfo)
    if instance.memory > info['memory_free']:
      raise errors.OpPrereqError, ("Not enough memory on target node %s."
                                   " %d MB available, %d MB required" %
                                   (target_node, info['memory_free'],
                                    instance.memory))

    # check bridge existance
    brlist = [nic.bridge for nic in instance.nics]
    if not rpc.call_bridges_exist(instance.primary_node, brlist):
      raise errors.OpPrereqError, ("one or more target bridges %s does not"
                                   " exist on destination node '%s'" %
                                   (brlist, instance.primary_node))

    self.instance = instance

  def Exec(self, feedback_fn):
    """Failover an instance.

    The failover is done by shutting it down on its present node and
    starting it on the secondary.

    """
    instance = self.instance

    source_node = instance.primary_node
    target_node = instance.secondary_nodes[0]

    feedback_fn("* checking disk consistency between source and target")
    for dev in instance.disks:
      # for remote_raid1, these are md over drbd
      if not _CheckDiskConsistency(self.cfg, dev, target_node, False):
        if not self.op.ignore_consistency:
          raise errors.OpExecError, ("Disk %s is degraded on target node,"
                                     " aborting failover." % dev.iv_name)

    feedback_fn("* checking target node resource availability")
    nodeinfo = rpc.call_node_info([target_node], self.cfg.GetVGName())

    if not nodeinfo:
      raise errors.OpExecError, ("Could not contact target node %s." %
                                 target_node)

    free_memory = int(nodeinfo[target_node]['memory_free'])
    memory = instance.memory
    if memory > free_memory:
      raise errors.OpExecError, ("Not enough memory to create instance %s on"
                                 " node %s. needed %s MiB, available %s MiB" %
                                 (instance.name, target_node, memory,
                                  free_memory))

    feedback_fn("* shutting down instance on source node")
    logger.Info("Shutting down instance %s on node %s" %
                (instance.name, source_node))

    if not rpc.call_instance_shutdown(source_node, instance):
      logger.Error("Could not shutdown instance %s on node %s. Proceeding"
                   " anyway. Please make sure node %s is down"  %
                   (instance.name, source_node, source_node))

    feedback_fn("* deactivating the instance's disks on source node")
    if not _ShutdownInstanceDisks(instance, self.cfg, ignore_primary=True):
      raise errors.OpExecError, ("Can't shut down the instance's disks.")

    instance.primary_node = target_node
    # distribute new instance config to the other nodes
    self.cfg.AddInstance(instance)

    feedback_fn("* activating the instance's disks on target node")
    logger.Info("Starting instance %s on node %s" %
                (instance.name, target_node))

    disks_ok, dummy = _AssembleInstanceDisks(instance, self.cfg,
                                             ignore_secondaries=True)
    if not disks_ok:
      _ShutdownInstanceDisks(instance, self.cfg)
      raise errors.OpExecError, ("Can't activate the instance's disks")

    feedback_fn("* starting the instance on the target node")
    if not rpc.call_instance_start(target_node, instance, None):
      _ShutdownInstanceDisks(instance, self.cfg)
      raise errors.OpExecError("Could not start instance %s on node %s." %
                               (instance, target_node))


def _CreateBlockDevOnPrimary(cfg, node, device):
  """Create a tree of block devices on the primary node.

  This always creates all devices.

  """

  if device.children:
    for child in device.children:
      if not _CreateBlockDevOnPrimary(cfg, node, child):
        return False

  cfg.SetDiskID(device, node)
  new_id = rpc.call_blockdev_create(node, device, device.size, True)
  if not new_id:
    return False
  if device.physical_id is None:
    device.physical_id = new_id
  return True


def _CreateBlockDevOnSecondary(cfg, node, device, force):
  """Create a tree of block devices on a secondary node.

  If this device type has to be created on secondaries, create it and
  all its children.

  If not, just recurse to children keeping the same 'force' value.

  """
  if device.CreateOnSecondary():
    force = True
  if device.children:
    for child in device.children:
      if not _CreateBlockDevOnSecondary(cfg, node, child, force):
        return False

  if not force:
    return True
  cfg.SetDiskID(device, node)
  new_id = rpc.call_blockdev_create(node, device, device.size, False)
  if not new_id:
    return False
  if device.physical_id is None:
    device.physical_id = new_id
  return True


def _GenerateMDDRBDBranch(cfg, vgname, primary, secondary, size, base):
  """Generate a drbd device complete with its children.

  """
  port = cfg.AllocatePort()
  base = "%s_%s" % (base, port)
  dev_data = objects.Disk(dev_type="lvm", size=size,
                          logical_id=(vgname, "%s.data" % base))
  dev_meta = objects.Disk(dev_type="lvm", size=128,
                          logical_id=(vgname, "%s.meta" % base))
  drbd_dev = objects.Disk(dev_type="drbd", size=size,
                          logical_id = (primary, secondary, port),
                          children = [dev_data, dev_meta])
  return drbd_dev


def _GenerateDiskTemplate(cfg, vgname, template_name,
                          instance_name, primary_node,
                          secondary_nodes, disk_sz, swap_sz):
  """Generate the entire disk layout for a given template type.

  """
  #TODO: compute space requirements

  if template_name == "diskless":
    disks = []
  elif template_name == "plain":
    if len(secondary_nodes) != 0:
      raise errors.ProgrammerError("Wrong template configuration")
    sda_dev = objects.Disk(dev_type="lvm", size=disk_sz,
                           logical_id=(vgname, "%s.os" % instance_name),
                           iv_name = "sda")
    sdb_dev = objects.Disk(dev_type="lvm", size=swap_sz,
                           logical_id=(vgname, "%s.swap" % instance_name),
                           iv_name = "sdb")
    disks = [sda_dev, sdb_dev]
  elif template_name == "local_raid1":
    if len(secondary_nodes) != 0:
      raise errors.ProgrammerError("Wrong template configuration")
    sda_dev_m1 = objects.Disk(dev_type="lvm", size=disk_sz,
                              logical_id=(vgname, "%s.os_m1" % instance_name))
    sda_dev_m2 = objects.Disk(dev_type="lvm", size=disk_sz,
                              logical_id=(vgname, "%s.os_m2" % instance_name))
    md_sda_dev = objects.Disk(dev_type="md_raid1", iv_name = "sda",
                              size=disk_sz,
                              children = [sda_dev_m1, sda_dev_m2])
    sdb_dev_m1 = objects.Disk(dev_type="lvm", size=swap_sz,
                              logical_id=(vgname, "%s.swap_m1" %
                                          instance_name))
    sdb_dev_m2 = objects.Disk(dev_type="lvm", size=swap_sz,
                              logical_id=(vgname, "%s.swap_m2" %
                                          instance_name))
    md_sdb_dev = objects.Disk(dev_type="md_raid1", iv_name = "sdb",
                              size=swap_sz,
                              children = [sdb_dev_m1, sdb_dev_m2])
    disks = [md_sda_dev, md_sdb_dev]
  elif template_name == "remote_raid1":
    if len(secondary_nodes) != 1:
      raise errors.ProgrammerError("Wrong template configuration")
    remote_node = secondary_nodes[0]
    drbd_sda_dev = _GenerateMDDRBDBranch(cfg, vgname,
                                         primary_node, remote_node, disk_sz,
                                         "%s-sda" % instance_name)
    md_sda_dev = objects.Disk(dev_type="md_raid1", iv_name="sda",
                              children = [drbd_sda_dev], size=disk_sz)
    drbd_sdb_dev = _GenerateMDDRBDBranch(cfg, vgname,
                                         primary_node, remote_node, swap_sz,
                                         "%s-sdb" % instance_name)
    md_sdb_dev = objects.Disk(dev_type="md_raid1", iv_name="sdb",
                              children = [drbd_sdb_dev], size=swap_sz)
    disks = [md_sda_dev, md_sdb_dev]
  else:
    raise errors.ProgrammerError("Invalid disk template '%s'" % template_name)
  return disks


def _CreateDisks(cfg, instance):
  """Create all disks for an instance.

  This abstracts away some work from AddInstance.

  Args:
    instance: the instance object

  Returns:
    True or False showing the success of the creation process

  """
  for device in instance.disks:
    logger.Info("creating volume %s for instance %s" %
              (device.iv_name, instance.name))
    #HARDCODE
    for secondary_node in instance.secondary_nodes:
      if not _CreateBlockDevOnSecondary(cfg, secondary_node, device, False):
        logger.Error("failed to create volume %s (%s) on secondary node %s!" %
                     (device.iv_name, device, secondary_node))
        return False
    #HARDCODE
    if not _CreateBlockDevOnPrimary(cfg, instance.primary_node, device):
      logger.Error("failed to create volume %s on primary!" %
                   device.iv_name)
      return False
  return True


def _RemoveDisks(instance, cfg):
  """Remove all disks for an instance.

  This abstracts away some work from `AddInstance()` and
  `RemoveInstance()`. Note that in case some of the devices couldn't
  be remove, the removal will continue with the other ones (compare
  with `_CreateDisks()`).

  Args:
    instance: the instance object

  Returns:
    True or False showing the success of the removal proces

  """
  logger.Info("removing block devices for instance %s" % instance.name)

  result = True
  for device in instance.disks:
    for node, disk in device.ComputeNodeTree(instance.primary_node):
      cfg.SetDiskID(disk, node)
      if not rpc.call_blockdev_remove(node, disk):
        logger.Error("could not remove block device %s on node %s,"
                     " continuing anyway" %
                     (device.iv_name, node))
        result = False
  return result


class LUCreateInstance(LogicalUnit):
  """Create an instance.

  """
  HPATH = "instance-add"
  HTYPE = constants.HTYPE_INSTANCE
  _OP_REQP = ["instance_name", "mem_size", "disk_size", "pnode",
              "disk_template", "swap_size", "mode", "start", "vcpus",
              "wait_for_sync"]

  def BuildHooksEnv(self):
    """Build hooks env.

    This runs on master, primary and secondary nodes of the instance.

    """
    env = {
      "INSTANCE_NAME": self.op.instance_name,
      "INSTANCE_PRIMARY": self.op.pnode,
      "INSTANCE_SECONDARIES": " ".join(self.secondaries),
      "DISK_TEMPLATE": self.op.disk_template,
      "MEM_SIZE": self.op.mem_size,
      "DISK_SIZE": self.op.disk_size,
      "SWAP_SIZE": self.op.swap_size,
      "VCPUS": self.op.vcpus,
      "BRIDGE": self.op.bridge,
      "INSTANCE_ADD_MODE": self.op.mode,
      }
    if self.op.mode == constants.INSTANCE_IMPORT:
      env["SRC_NODE"] = self.op.src_node
      env["SRC_PATH"] = self.op.src_path
      env["SRC_IMAGE"] = self.src_image
    if self.inst_ip:
      env["INSTANCE_IP"] = self.inst_ip

    nl = ([self.cfg.GetMaster(), self.op.pnode] +
          self.secondaries)
    return env, nl, nl


  def CheckPrereq(self):
    """Check prerequisites.

    """
    if self.op.mode not in (constants.INSTANCE_CREATE,
                            constants.INSTANCE_IMPORT):
      raise errors.OpPrereqError, ("Invalid instance creation mode '%s'" %
                                   self.op.mode)

    if self.op.mode == constants.INSTANCE_IMPORT:
      src_node = getattr(self.op, "src_node", None)
      src_path = getattr(self.op, "src_path", None)
      if src_node is None or src_path is None:
        raise errors.OpPrereqError, ("Importing an instance requires source"
                                     " node and path options")
      src_node_full = self.cfg.ExpandNodeName(src_node)
      if src_node_full is None:
        raise errors.OpPrereqError, ("Unknown source node '%s'" % src_node)
      self.op.src_node = src_node = src_node_full

      if not os.path.isabs(src_path):
        raise errors.OpPrereqError, ("The source path must be absolute")

      export_info = rpc.call_export_info(src_node, src_path)

      if not export_info:
        raise errors.OpPrereqError, ("No export found in dir %s" % src_path)

      if not export_info.has_section(constants.INISECT_EXP):
        raise errors.ProgrammerError, ("Corrupted export config")

      ei_version = export_info.get(constants.INISECT_EXP, 'version')
      if (int(ei_version) != constants.EXPORT_VERSION):
        raise errors.OpPrereqError, ("Wrong export version %s (wanted %d)" %
                                     (ei_version, constants.EXPORT_VERSION))

      if int(export_info.get(constants.INISECT_INS, 'disk_count')) > 1:
        raise errors.OpPrereqError, ("Can't import instance with more than"
                                     " one data disk")

      # FIXME: are the old os-es, disk sizes, etc. useful?
      self.op.os_type = export_info.get(constants.INISECT_EXP, 'os')
      diskimage = os.path.join(src_path, export_info.get(constants.INISECT_INS,
                                                         'disk0_dump'))
      self.src_image = diskimage
    else: # INSTANCE_CREATE
      if getattr(self.op, "os_type", None) is None:
        raise errors.OpPrereqError, ("No guest OS specified")

    # check primary node
    pnode = self.cfg.GetNodeInfo(self.cfg.ExpandNodeName(self.op.pnode))
    if pnode is None:
      raise errors.OpPrereqError, ("Primary node '%s' is uknown" %
                                   self.op.pnode)
    self.op.pnode = pnode.name
    self.pnode = pnode
    self.secondaries = []
    # disk template and mirror node verification
    if self.op.disk_template not in constants.DISK_TEMPLATES:
      raise errors.OpPrereqError, ("Invalid disk template name")

    if self.op.disk_template == constants.DT_REMOTE_RAID1:
      if getattr(self.op, "snode", None) is None:
        raise errors.OpPrereqError, ("The 'remote_raid1' disk template needs"
                                     " a mirror node")

      snode_name = self.cfg.ExpandNodeName(self.op.snode)
      if snode_name is None:
        raise errors.OpPrereqError, ("Unknown secondary node '%s'" %
                                     self.op.snode)
      elif snode_name == pnode.name:
        raise errors.OpPrereqError, ("The secondary node cannot be"
                                     " the primary node.")
      self.secondaries.append(snode_name)

    # Check lv size requirements
    nodenames = [pnode.name] + self.secondaries
    nodeinfo = rpc.call_node_info(nodenames, self.cfg.GetVGName())

    # Required free disk space as a function of disk and swap space
    req_size_dict = {
      constants.DT_DISKLESS: 0,
      constants.DT_PLAIN: self.op.disk_size + self.op.swap_size,
      constants.DT_LOCAL_RAID1: (self.op.disk_size + self.op.swap_size) * 2,
      # 256 MB are added for drbd metadata, 128MB for each drbd device
      constants.DT_REMOTE_RAID1: self.op.disk_size + self.op.swap_size + 256,
    }

    if self.op.disk_template not in req_size_dict:
      raise errors.ProgrammerError, ("Disk template '%s' size requirement"
                                     " is unknown" %  self.op.disk_template)

    req_size = req_size_dict[self.op.disk_template]

    for node in nodenames:
      info = nodeinfo.get(node, None)
      if not info:
        raise errors.OpPrereqError, ("Cannot get current information"
                                     " from node '%s'" % nodeinfo)
      if req_size > info['vg_free']:
        raise errors.OpPrereqError, ("Not enough disk space on target node %s."
                                     " %d MB available, %d MB required" %
                                     (node, info['vg_free'], req_size))

    # os verification
    os_obj = rpc.call_os_get([pnode.name], self.op.os_type)[pnode.name]
    if not isinstance(os_obj, objects.OS):
      raise errors.OpPrereqError, ("OS '%s' not in supported os list for"
                                   " primary node"  % self.op.os_type)

    # instance verification
    hostname1 = utils.LookupHostname(self.op.instance_name)
    if not hostname1:
      raise errors.OpPrereqError, ("Instance name '%s' not found in dns" %
                                   self.op.instance_name)

    self.op.instance_name = instance_name = hostname1['hostname']
    instance_list = self.cfg.GetInstanceList()
    if instance_name in instance_list:
      raise errors.OpPrereqError, ("Instance '%s' is already in the cluster" %
                                   instance_name)

    ip = getattr(self.op, "ip", None)
    if ip is None or ip.lower() == "none":
      inst_ip = None
    elif ip.lower() == "auto":
      inst_ip = hostname1['ip']
    else:
      if not utils.IsValidIP(ip):
        raise errors.OpPrereqError, ("given IP address '%s' doesn't look"
                                     " like a valid IP" % ip)
      inst_ip = ip
    self.inst_ip = inst_ip

    command = ["fping", "-q", hostname1['ip']]
    result = utils.RunCmd(command)
    if not result.failed:
      raise errors.OpPrereqError, ("IP %s of instance %s already in use" %
                                   (hostname1['ip'], instance_name))

    # bridge verification
    bridge = getattr(self.op, "bridge", None)
    if bridge is None:
      self.op.bridge = self.cfg.GetDefBridge()
    else:
      self.op.bridge = bridge

    if not rpc.call_bridges_exist(self.pnode.name, [self.op.bridge]):
      raise errors.OpPrereqError, ("target bridge '%s' does not exist on"
                                   " destination node '%s'" %
                                   (self.op.bridge, pnode.name))

    if self.op.start:
      self.instance_status = 'up'
    else:
      self.instance_status = 'down'

  def Exec(self, feedback_fn):
    """Create and add the instance to the cluster.

    """
    instance = self.op.instance_name
    pnode_name = self.pnode.name

    nic = objects.NIC(bridge=self.op.bridge, mac=self.cfg.GenerateMAC())
    if self.inst_ip is not None:
      nic.ip = self.inst_ip

    disks = _GenerateDiskTemplate(self.cfg, self.cfg.GetVGName(),
                                  self.op.disk_template,
                                  instance, pnode_name,
                                  self.secondaries, self.op.disk_size,
                                  self.op.swap_size)

    iobj = objects.Instance(name=instance, os=self.op.os_type,
                            primary_node=pnode_name,
                            memory=self.op.mem_size,
                            vcpus=self.op.vcpus,
                            nics=[nic], disks=disks,
                            disk_template=self.op.disk_template,
                            status=self.instance_status,
                            )

    feedback_fn("* creating instance disks...")
    if not _CreateDisks(self.cfg, iobj):
      _RemoveDisks(iobj, self.cfg)
      raise errors.OpExecError, ("Device creation failed, reverting...")

    feedback_fn("adding instance %s to cluster config" % instance)

    self.cfg.AddInstance(iobj)

    if self.op.wait_for_sync:
      disk_abort = not _WaitForSync(self.cfg, iobj)
    elif iobj.disk_template == "remote_raid1":
      # make sure the disks are not degraded (still sync-ing is ok)
      time.sleep(15)
      feedback_fn("* checking mirrors status")
      disk_abort = not _WaitForSync(self.cfg, iobj, oneshot=True)
    else:
      disk_abort = False

    if disk_abort:
      _RemoveDisks(iobj, self.cfg)
      self.cfg.RemoveInstance(iobj.name)
      raise errors.OpExecError, ("There are some degraded disks for"
                                      " this instance")

    feedback_fn("creating os for instance %s on node %s" %
                (instance, pnode_name))

    if iobj.disk_template != constants.DT_DISKLESS:
      if self.op.mode == constants.INSTANCE_CREATE:
        feedback_fn("* running the instance OS create scripts...")
        if not rpc.call_instance_os_add(pnode_name, iobj, "sda", "sdb"):
          raise errors.OpExecError, ("could not add os for instance %s"
                                          " on node %s" %
                                          (instance, pnode_name))

      elif self.op.mode == constants.INSTANCE_IMPORT:
        feedback_fn("* running the instance OS import scripts...")
        src_node = self.op.src_node
        src_image = self.src_image
        if not rpc.call_instance_os_import(pnode_name, iobj, "sda", "sdb",
                                                src_node, src_image):
          raise errors.OpExecError, ("Could not import os for instance"
                                          " %s on node %s" %
                                          (instance, pnode_name))
      else:
        # also checked in the prereq part
        raise errors.ProgrammerError, ("Unknown OS initialization mode '%s'"
                                       % self.op.mode)

    if self.op.start:
      logger.Info("starting instance %s on node %s" % (instance, pnode_name))
      feedback_fn("* starting instance...")
      if not rpc.call_instance_start(pnode_name, iobj, None):
        raise errors.OpExecError, ("Could not start instance")


class LUConnectConsole(NoHooksLU):
  """Connect to an instance's console.

  This is somewhat special in that it returns the command line that
  you need to run on the master node in order to connect to the
  console.

  """
  _OP_REQP = ["instance_name"]

  def CheckPrereq(self):
    """Check prerequisites.

    This checks that the instance is in the cluster.

    """
    instance = self.cfg.GetInstanceInfo(
      self.cfg.ExpandInstanceName(self.op.instance_name))
    if instance is None:
      raise errors.OpPrereqError, ("Instance '%s' not known" %
                                   self.op.instance_name)
    self.instance = instance

  def Exec(self, feedback_fn):
    """Connect to the console of an instance

    """
    instance = self.instance
    node = instance.primary_node

    node_insts = rpc.call_instance_list([node])[node]
    if node_insts is False:
      raise errors.OpExecError, ("Can't connect to node %s." % node)

    if instance.name not in node_insts:
      raise errors.OpExecError, ("Instance %s is not running." % instance.name)

    logger.Debug("connecting to console of %s on %s" % (instance.name, node))

    hyper = hypervisor.GetHypervisor()
    console_cmd = hyper.GetShellCommandForConsole(instance.name)
    return node, console_cmd


class LUAddMDDRBDComponent(LogicalUnit):
  """Adda new mirror member to an instance's disk.

  """
  HPATH = "mirror-add"
  HTYPE = constants.HTYPE_INSTANCE
  _OP_REQP = ["instance_name", "remote_node", "disk_name"]

  def BuildHooksEnv(self):
    """Build hooks env.

    This runs on the master, the primary and all the secondaries.

    """
    env = {
      "INSTANCE_NAME": self.op.instance_name,
      "NEW_SECONDARY": self.op.remote_node,
      "DISK_NAME": self.op.disk_name,
      }
    nl = [self.cfg.GetMaster(), self.instance.primary_node,
          self.op.remote_node,] + list(self.instance.secondary_nodes)
    return env, nl, nl

  def CheckPrereq(self):
    """Check prerequisites.

    This checks that the instance is in the cluster.

    """
    instance = self.cfg.GetInstanceInfo(
      self.cfg.ExpandInstanceName(self.op.instance_name))
    if instance is None:
      raise errors.OpPrereqError, ("Instance '%s' not known" %
                                   self.op.instance_name)
    self.instance = instance

    remote_node = self.cfg.ExpandNodeName(self.op.remote_node)
    if remote_node is None:
      raise errors.OpPrereqError, ("Node '%s' not known" % self.op.remote_node)
    self.remote_node = remote_node

    if remote_node == instance.primary_node:
      raise errors.OpPrereqError, ("The specified node is the primary node of"
                                   " the instance.")

    if instance.disk_template != constants.DT_REMOTE_RAID1:
      raise errors.OpPrereqError, ("Instance's disk layout is not"
                                   " remote_raid1.")
    for disk in instance.disks:
      if disk.iv_name == self.op.disk_name:
        break
    else:
      raise errors.OpPrereqError, ("Can't find this device ('%s') in the"
                                   " instance." % self.op.disk_name)
    if len(disk.children) > 1:
      raise errors.OpPrereqError, ("The device already has two slave"
                                   " devices.\n"
                                   "This would create a 3-disk raid1"
                                   " which we don't allow.")
    self.disk = disk

  def Exec(self, feedback_fn):
    """Add the mirror component

    """
    disk = self.disk
    instance = self.instance

    remote_node = self.remote_node
    new_drbd = _GenerateMDDRBDBranch(self.cfg, self.cfg.GetVGName(),
                                     instance.primary_node, remote_node,
                                     disk.size, "%s-%s" %
                                     (instance.name, self.op.disk_name))

    logger.Info("adding new mirror component on secondary")
    #HARDCODE
    if not _CreateBlockDevOnSecondary(self.cfg, remote_node, new_drbd, False):
      raise errors.OpExecError, ("Failed to create new component on secondary"
                                 " node %s" % remote_node)

    logger.Info("adding new mirror component on primary")
    #HARDCODE
    if not _CreateBlockDevOnPrimary(self.cfg, instance.primary_node, new_drbd):
      # remove secondary dev
      self.cfg.SetDiskID(new_drbd, remote_node)
      rpc.call_blockdev_remove(remote_node, new_drbd)
      raise errors.OpExecError, ("Failed to create volume on primary")

    # the device exists now
    # call the primary node to add the mirror to md
    logger.Info("adding new mirror component to md")
    if not rpc.call_blockdev_addchild(instance.primary_node,
                                           disk, new_drbd):
      logger.Error("Can't add mirror compoment to md!")
      self.cfg.SetDiskID(new_drbd, remote_node)
      if not rpc.call_blockdev_remove(remote_node, new_drbd):
        logger.Error("Can't rollback on secondary")
      self.cfg.SetDiskID(new_drbd, instance.primary_node)
      if not rpc.call_blockdev_remove(instance.primary_node, new_drbd):
        logger.Error("Can't rollback on primary")
      raise errors.OpExecError, "Can't add mirror component to md array"

    disk.children.append(new_drbd)

    self.cfg.AddInstance(instance)

    _WaitForSync(self.cfg, instance)

    return 0


class LURemoveMDDRBDComponent(LogicalUnit):
  """Remove a component from a remote_raid1 disk.

  """
  HPATH = "mirror-remove"
  HTYPE = constants.HTYPE_INSTANCE
  _OP_REQP = ["instance_name", "disk_name", "disk_id"]

  def BuildHooksEnv(self):
    """Build hooks env.

    This runs on the master, the primary and all the secondaries.

    """
    env = {
      "INSTANCE_NAME": self.op.instance_name,
      "DISK_NAME": self.op.disk_name,
      "DISK_ID": self.op.disk_id,
      "OLD_SECONDARY": self.old_secondary,
      }
    nl = [self.cfg.GetMaster(),
          self.instance.primary_node] + list(self.instance.secondary_nodes)
    return env, nl, nl

  def CheckPrereq(self):
    """Check prerequisites.

    This checks that the instance is in the cluster.

    """
    instance = self.cfg.GetInstanceInfo(
      self.cfg.ExpandInstanceName(self.op.instance_name))
    if instance is None:
      raise errors.OpPrereqError, ("Instance '%s' not known" %
                                   self.op.instance_name)
    self.instance = instance

    if instance.disk_template != constants.DT_REMOTE_RAID1:
      raise errors.OpPrereqError, ("Instance's disk layout is not"
                                   " remote_raid1.")
    for disk in instance.disks:
      if disk.iv_name == self.op.disk_name:
        break
    else:
      raise errors.OpPrereqError, ("Can't find this device ('%s') in the"
                                   " instance." % self.op.disk_name)
    for child in disk.children:
      if child.dev_type == "drbd" and child.logical_id[2] == self.op.disk_id:
        break
    else:
      raise errors.OpPrereqError, ("Can't find the device with this port.")

    if len(disk.children) < 2:
      raise errors.OpPrereqError, ("Cannot remove the last component from"
                                   " a mirror.")
    self.disk = disk
    self.child = child
    if self.child.logical_id[0] == instance.primary_node:
      oid = 1
    else:
      oid = 0
    self.old_secondary = self.child.logical_id[oid]

  def Exec(self, feedback_fn):
    """Remove the mirror component

    """
    instance = self.instance
    disk = self.disk
    child = self.child
    logger.Info("remove mirror component")
    self.cfg.SetDiskID(disk, instance.primary_node)
    if not rpc.call_blockdev_removechild(instance.primary_node,
                                              disk, child):
      raise errors.OpExecError, ("Can't remove child from mirror.")

    for node in child.logical_id[:2]:
      self.cfg.SetDiskID(child, node)
      if not rpc.call_blockdev_remove(node, child):
        logger.Error("Warning: failed to remove device from node %s,"
                     " continuing operation." % node)

    disk.children.remove(child)
    self.cfg.AddInstance(instance)


class LUReplaceDisks(LogicalUnit):
  """Replace the disks of an instance.

  """
  HPATH = "mirrors-replace"
  HTYPE = constants.HTYPE_INSTANCE
  _OP_REQP = ["instance_name"]

  def BuildHooksEnv(self):
    """Build hooks env.

    This runs on the master, the primary and all the secondaries.

    """
    env = {
      "INSTANCE_NAME": self.op.instance_name,
      "NEW_SECONDARY": self.op.remote_node,
      "OLD_SECONDARY": self.instance.secondary_nodes[0],
      }
    nl = [self.cfg.GetMaster(),
          self.instance.primary_node] + list(self.instance.secondary_nodes)
    return env, nl, nl

  def CheckPrereq(self):
    """Check prerequisites.

    This checks that the instance is in the cluster.

    """
    instance = self.cfg.GetInstanceInfo(
      self.cfg.ExpandInstanceName(self.op.instance_name))
    if instance is None:
      raise errors.OpPrereqError, ("Instance '%s' not known" %
                                   self.op.instance_name)
    self.instance = instance

    if instance.disk_template != constants.DT_REMOTE_RAID1:
      raise errors.OpPrereqError, ("Instance's disk layout is not"
                                   " remote_raid1.")

    if len(instance.secondary_nodes) != 1:
      raise errors.OpPrereqError, ("The instance has a strange layout,"
                                   " expected one secondary but found %d" %
                                   len(instance.secondary_nodes))

    remote_node = getattr(self.op, "remote_node", None)
    if remote_node is None:
      remote_node = instance.secondary_nodes[0]
    else:
      remote_node = self.cfg.ExpandNodeName(remote_node)
      if remote_node is None:
        raise errors.OpPrereqError, ("Node '%s' not known" %
                                     self.op.remote_node)
    if remote_node == instance.primary_node:
      raise errors.OpPrereqError, ("The specified node is the primary node of"
                                   " the instance.")
    self.op.remote_node = remote_node

  def Exec(self, feedback_fn):
    """Replace the disks of an instance.

    """
    instance = self.instance
    iv_names = {}
    # start of work
    remote_node = self.op.remote_node
    cfg = self.cfg
    for dev in instance.disks:
      size = dev.size
      new_drbd = _GenerateMDDRBDBranch(cfg, self.cfg.GetVGName(),
                                       instance.primary_node, remote_node, size,
                                       "%s-%s" % (instance.name, dev.iv_name))
      iv_names[dev.iv_name] = (dev, dev.children[0], new_drbd)
      logger.Info("adding new mirror component on secondary for %s" %
                  dev.iv_name)
      #HARDCODE
      if not _CreateBlockDevOnSecondary(cfg, remote_node, new_drbd, False):
        raise errors.OpExecError, ("Failed to create new component on"
                                   " secondary node %s\n"
                                   "Full abort, cleanup manually!" %
                                   remote_node)

      logger.Info("adding new mirror component on primary")
      #HARDCODE
      if not _CreateBlockDevOnPrimary(cfg, instance.primary_node, new_drbd):
        # remove secondary dev
        cfg.SetDiskID(new_drbd, remote_node)
        rpc.call_blockdev_remove(remote_node, new_drbd)
        raise errors.OpExecError("Failed to create volume on primary!\n"
                                 "Full abort, cleanup manually!!")

      # the device exists now
      # call the primary node to add the mirror to md
      logger.Info("adding new mirror component to md")
      if not rpc.call_blockdev_addchild(instance.primary_node, dev,
                                             new_drbd):
        logger.Error("Can't add mirror compoment to md!")
        cfg.SetDiskID(new_drbd, remote_node)
        if not rpc.call_blockdev_remove(remote_node, new_drbd):
          logger.Error("Can't rollback on secondary")
        cfg.SetDiskID(new_drbd, instance.primary_node)
        if not rpc.call_blockdev_remove(instance.primary_node, new_drbd):
          logger.Error("Can't rollback on primary")
        raise errors.OpExecError, ("Full abort, cleanup manually!!")

      dev.children.append(new_drbd)
      cfg.AddInstance(instance)

    # this can fail as the old devices are degraded and _WaitForSync
    # does a combined result over all disks, so we don't check its
    # return value
    _WaitForSync(cfg, instance, unlock=True)

    # so check manually all the devices
    for name in iv_names:
      dev, child, new_drbd = iv_names[name]
      cfg.SetDiskID(dev, instance.primary_node)
      is_degr = rpc.call_blockdev_find(instance.primary_node, dev)[5]
      if is_degr:
        raise errors.OpExecError, ("MD device %s is degraded!" % name)
      cfg.SetDiskID(new_drbd, instance.primary_node)
      is_degr = rpc.call_blockdev_find(instance.primary_node, new_drbd)[5]
      if is_degr:
        raise errors.OpExecError, ("New drbd device %s is degraded!" % name)

    for name in iv_names:
      dev, child, new_drbd = iv_names[name]
      logger.Info("remove mirror %s component" % name)
      cfg.SetDiskID(dev, instance.primary_node)
      if not rpc.call_blockdev_removechild(instance.primary_node,
                                                dev, child):
        logger.Error("Can't remove child from mirror, aborting"
                     " *this device cleanup*.\nYou need to cleanup manually!!")
        continue

      for node in child.logical_id[:2]:
        logger.Info("remove child device on %s" % node)
        cfg.SetDiskID(child, node)
        if not rpc.call_blockdev_remove(node, child):
          logger.Error("Warning: failed to remove device from node %s,"
                       " continuing operation." % node)

      dev.children.remove(child)

      cfg.AddInstance(instance)


class LUQueryInstanceData(NoHooksLU):
  """Query runtime instance data.

  """
  _OP_REQP = ["instances"]

  def CheckPrereq(self):
    """Check prerequisites.

    This only checks the optional instance list against the existing names.

    """
    if not isinstance(self.op.instances, list):
      raise errors.OpPrereqError, "Invalid argument type 'instances'"
    if self.op.instances:
      self.wanted_instances = []
      names = self.op.instances
      for name in names:
        instance = self.cfg.GetInstanceInfo(self.cfg.ExpandInstanceName(name))
        if instance is None:
          raise errors.OpPrereqError, ("No such instance name '%s'" % name)
      self.wanted_instances.append(instance)
    else:
      self.wanted_instances = [self.cfg.GetInstanceInfo(name) for name
                               in self.cfg.GetInstanceList()]
    return


  def _ComputeDiskStatus(self, instance, snode, dev):
    """Compute block device status.

    """
    self.cfg.SetDiskID(dev, instance.primary_node)
    dev_pstatus = rpc.call_blockdev_find(instance.primary_node, dev)
    if dev.dev_type == "drbd":
      # we change the snode then (otherwise we use the one passed in)
      if dev.logical_id[0] == instance.primary_node:
        snode = dev.logical_id[1]
      else:
        snode = dev.logical_id[0]

    if snode:
      self.cfg.SetDiskID(dev, snode)
      dev_sstatus = rpc.call_blockdev_find(snode, dev)
    else:
      dev_sstatus = None

    if dev.children:
      dev_children = [self._ComputeDiskStatus(instance, snode, child)
                      for child in dev.children]
    else:
      dev_children = []

    data = {
      "iv_name": dev.iv_name,
      "dev_type": dev.dev_type,
      "logical_id": dev.logical_id,
      "physical_id": dev.physical_id,
      "pstatus": dev_pstatus,
      "sstatus": dev_sstatus,
      "children": dev_children,
      }

    return data

  def Exec(self, feedback_fn):
    """Gather and return data"""

    result = {}
    for instance in self.wanted_instances:
      remote_info = rpc.call_instance_info(instance.primary_node,
                                                instance.name)
      if remote_info and "state" in remote_info:
        remote_state = "up"
      else:
        remote_state = "down"
      if instance.status == "down":
        config_state = "down"
      else:
        config_state = "up"

      disks = [self._ComputeDiskStatus(instance, None, device)
               for device in instance.disks]

      idict = {
        "name": instance.name,
        "config_state": config_state,
        "run_state": remote_state,
        "pnode": instance.primary_node,
        "snodes": instance.secondary_nodes,
        "os": instance.os,
        "memory": instance.memory,
        "nics": [(nic.mac, nic.ip, nic.bridge) for nic in instance.nics],
        "disks": disks,
        }

      result[instance.name] = idict

    return result


class LUQueryNodeData(NoHooksLU):
  """Logical unit for querying node data.

  """
  _OP_REQP = ["nodes"]

  def CheckPrereq(self):
    """Check prerequisites.

    This only checks the optional node list against the existing names.

    """
    if not isinstance(self.op.nodes, list):
      raise errors.OpPrereqError, "Invalid argument type 'nodes'"
    if self.op.nodes:
      self.wanted_nodes = []
      names = self.op.nodes
      for name in names:
        node = self.cfg.GetNodeInfo(self.cfg.ExpandNodeName(name))
        if node is None:
          raise errors.OpPrereqError, ("No such node name '%s'" % name)
      self.wanted_nodes.append(node)
    else:
      self.wanted_nodes = [self.cfg.GetNodeInfo(name) for name
                           in self.cfg.GetNodeList()]
    return

  def Exec(self, feedback_fn):
    """Compute and return the list of nodes.

    """

    ilist = [self.cfg.GetInstanceInfo(iname) for iname
             in self.cfg.GetInstanceList()]
    result = []
    for node in self.wanted_nodes:
      result.append((node.name, node.primary_ip, node.secondary_ip,
                     [inst.name for inst in ilist
                      if inst.primary_node == node.name],
                     [inst.name for inst in ilist
                      if node.name in inst.secondary_nodes],
                     ))
    return result


class LUSetInstanceParms(LogicalUnit):
  """Modifies an instances's parameters.

  """
  HPATH = "instance-modify"
  HTYPE = constants.HTYPE_INSTANCE
  _OP_REQP = ["instance_name"]

  def BuildHooksEnv(self):
    """Build hooks env.

    This runs on the master, primary and secondaries.

    """
    env = {
      "INSTANCE_NAME": self.op.instance_name,
      }
    if self.mem:
      env["MEM_SIZE"] = self.mem
    if self.vcpus:
      env["VCPUS"] = self.vcpus
    if self.do_ip:
      env["INSTANCE_IP"] = self.ip
    if self.bridge:
      env["BRIDGE"] = self.bridge

    nl = [self.cfg.GetMaster(),
          self.instance.primary_node] + list(self.instance.secondary_nodes)

    return env, nl, nl

  def CheckPrereq(self):
    """Check prerequisites.

    This only checks the instance list against the existing names.

    """
    self.mem = getattr(self.op, "mem", None)
    self.vcpus = getattr(self.op, "vcpus", None)
    self.ip = getattr(self.op, "ip", None)
    self.bridge = getattr(self.op, "bridge", None)
    if [self.mem, self.vcpus, self.ip, self.bridge].count(None) == 4:
      raise errors.OpPrereqError, ("No changes submitted")
    if self.mem is not None:
      try:
        self.mem = int(self.mem)
      except ValueError, err:
        raise errors.OpPrereqError, ("Invalid memory size: %s" % str(err))
    if self.vcpus is not None:
      try:
        self.vcpus = int(self.vcpus)
      except ValueError, err:
        raise errors.OpPrereqError, ("Invalid vcpus number: %s" % str(err))
    if self.ip is not None:
      self.do_ip = True
      if self.ip.lower() == "none":
        self.ip = None
      else:
        if not utils.IsValidIP(self.ip):
          raise errors.OpPrereqError, ("Invalid IP address '%s'." % self.ip)
    else:
      self.do_ip = False

    instance = self.cfg.GetInstanceInfo(
      self.cfg.ExpandInstanceName(self.op.instance_name))
    if instance is None:
      raise errors.OpPrereqError, ("No such instance name '%s'" %
                                   self.op.instance_name)
    self.op.instance_name = instance.name
    self.instance = instance
    return

  def Exec(self, feedback_fn):
    """Modifies an instance.

    All parameters take effect only at the next restart of the instance.
    """
    result = []
    instance = self.instance
    if self.mem:
      instance.memory = self.mem
      result.append(("mem", self.mem))
    if self.vcpus:
      instance.vcpus = self.vcpus
      result.append(("vcpus",  self.vcpus))
    if self.do_ip:
      instance.nics[0].ip = self.ip
      result.append(("ip", self.ip))
    if self.bridge:
      instance.nics[0].bridge = self.bridge
      result.append(("bridge", self.bridge))

    self.cfg.AddInstance(instance)

    return result


class LUQueryExports(NoHooksLU):
  """Query the exports list

  """
  _OP_REQP = []

  def CheckPrereq(self):
    """Check that the nodelist contains only existing nodes.

    """
    nodes = getattr(self.op, "nodes", None)
    if not nodes:
      self.op.nodes = self.cfg.GetNodeList()
    else:
      expnodes = [self.cfg.ExpandNodeName(node) for node in nodes]
      if expnodes.count(None) > 0:
        raise errors.OpPrereqError, ("At least one of the given nodes %s"
                                     " is unknown" % self.op.nodes)
      self.op.nodes = expnodes

  def Exec(self, feedback_fn):

    """Compute the list of all the exported system images.

    Returns:
      a dictionary with the structure node->(export-list)
      where export-list is a list of the instances exported on
      that node.

    """
    return rpc.call_export_list(self.op.nodes)


class LUExportInstance(LogicalUnit):
  """Export an instance to an image in the cluster.

  """
  HPATH = "instance-export"
  HTYPE = constants.HTYPE_INSTANCE
  _OP_REQP = ["instance_name", "target_node", "shutdown"]

  def BuildHooksEnv(self):
    """Build hooks env.

    This will run on the master, primary node and target node.

    """
    env = {
      "INSTANCE_NAME": self.op.instance_name,
      "EXPORT_NODE": self.op.target_node,
      "EXPORT_DO_SHUTDOWN": self.op.shutdown,
      }
    nl = [self.cfg.GetMaster(), self.instance.primary_node,
          self.op.target_node]
    return env, nl, nl

  def CheckPrereq(self):
    """Check prerequisites.

    This checks that the instance name is a valid one.

    """
    instance_name = self.cfg.ExpandInstanceName(self.op.instance_name)
    self.instance = self.cfg.GetInstanceInfo(instance_name)
    if self.instance is None:
      raise errors.OpPrereqError, ("Instance '%s' not found" %
                                   self.op.instance_name)

    # node verification
    dst_node_short = self.cfg.ExpandNodeName(self.op.target_node)
    self.dst_node = self.cfg.GetNodeInfo(dst_node_short)

    if self.dst_node is None:
      raise errors.OpPrereqError, ("Destination node '%s' is uknown." %
                                   self.op.target_node)
    self.op.target_node = self.dst_node.name

  def Exec(self, feedback_fn):
    """Export an instance to an image in the cluster.

    """
    instance = self.instance
    dst_node = self.dst_node
    src_node = instance.primary_node
    # shutdown the instance, unless requested not to do so
    if self.op.shutdown:
      op = opcodes.OpShutdownInstance(instance_name=instance.name)
      self.processor.ChainOpCode(op, feedback_fn)

    vgname = self.cfg.GetVGName()

    snap_disks = []

    try:
      for disk in instance.disks:
        if disk.iv_name == "sda":
          # new_dev_name will be a snapshot of an lvm leaf of the one we passed
          new_dev_name = rpc.call_blockdev_snapshot(src_node, disk)

          if not new_dev_name:
            logger.Error("could not snapshot block device %s on node %s" %
                         (disk.logical_id[1], src_node))
          else:
            new_dev = objects.Disk(dev_type="lvm", size=disk.size,
                                      logical_id=(vgname, new_dev_name),
                                      physical_id=(vgname, new_dev_name),
                                      iv_name=disk.iv_name)
            snap_disks.append(new_dev)

    finally:
      if self.op.shutdown:
        op = opcodes.OpStartupInstance(instance_name=instance.name,
                                       force=False)
        self.processor.ChainOpCode(op, feedback_fn)

    # TODO: check for size

    for dev in snap_disks:
      if not rpc.call_snapshot_export(src_node, dev, dst_node.name,
                                           instance):
        logger.Error("could not export block device %s from node"
                     " %s to node %s" %
                     (dev.logical_id[1], src_node, dst_node.name))
      if not rpc.call_blockdev_remove(src_node, dev):
        logger.Error("could not remove snapshot block device %s from"
                     " node %s" % (dev.logical_id[1], src_node))

    if not rpc.call_finalize_export(dst_node.name, instance, snap_disks):
      logger.Error("could not finalize export for instance %s on node %s" %
                   (instance.name, dst_node.name))

    nodelist = self.cfg.GetNodeList()
    nodelist.remove(dst_node.name)

    # on one-node clusters nodelist will be empty after the removal
    # if we proceed the backup would be removed because OpQueryExports
    # substitutes an empty list with the full cluster node list.
    if nodelist:
      op = opcodes.OpQueryExports(nodes=nodelist)
      exportlist = self.processor.ChainOpCode(op, feedback_fn)
      for node in exportlist:
        if instance.name in exportlist[node]:
          if not rpc.call_export_remove(node, instance.name):
            logger.Error("could not remove older export for instance %s"
                         " on node %s" % (instance.name, node))
