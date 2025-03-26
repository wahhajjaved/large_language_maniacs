# -*- coding: utf-8 -*-
from __future__ import absolute_import

import os
import sys
import subprocess

from hetzner.robot import Robot

from nixops.util import attr_property, wait_for_tcp_port, create_key_pair
from nixops.backends import MachineDefinition, MachineState


class HetznerDefinition(MachineDefinition):
    """
    Definition of a Hetzner machine.
    """

    @classmethod
    def get_type(cls):
        return "hetzner"

    def __init__(self, xml):
        MachineDefinition.__init__(self, xml)
        x = xml.find("attrs/attr[@name='hetzner']/attrs")
        assert x is not None
        for var, name, valtype in [("main_ipv4", "mainIPv4", "string"),
                                   ("robot_user", "robotUser", "string"),
                                   ("robot_pass", "robotPass", "string"),
                                   ("partitions", "partitions", "string")]:
            attr = x.find("attr[@name='" + name + "']/" + valtype)
            setattr(self, var, attr.get("value"))


class HetznerState(MachineState):
    """
    State of a Hetzner machine.
    """

    @classmethod
    def get_type(cls):
        return "hetzner"

    state = attr_property("state", MachineState.UNKNOWN, int)

    main_ipv4 = attr_property("hetzner.mainIPv4", None)
    robot_user = attr_property("hetzner.robotUser", None)
    robot_pass = attr_property("hetzner.robotPass", None)
    partitions = attr_property("hetzner.partitions", None)

    just_installed = attr_property("hetzner.justInstalled", False, bool)
    rescue_passwd = attr_property("hetzner.rescuePasswd", None)
    fs_info = attr_property("hetzner.fsInfo", None)
    net_info = attr_property("hetzner.networkInfo", None)

    main_ssh_private_key = attr_property("hetzner.sshPrivateKey", None)
    main_ssh_public_key = attr_property("hetzner.sshPublicKey", None)

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self._robot = None

    @property
    def resource_id(self):
        return self.vm_id

    def connect(self):
        """
        Connect to the Hetzner robot.
        """
        if self._robot is not None:
            return True
        elif self.robot_user is None or self.robot_pass is None:
            return False
        self._robot = Robot(self.robot_user, self.robot_pass)
        return True

    def get_ssh_private_key_file(self):
        if self._ssh_private_key_file:
            return self._ssh_private_key_file
        else:
            return self.write_ssh_private_key(self.main_ssh_private_key)

    def get_ssh_flags(self):
        if self.state == self.RESCUE:
            return ["-o", "LogLevel=quiet"]
        else:
            return ["-i", self.get_ssh_private_key_file()]

    def _wait_for_rescue(self, ip):
        self.log_start("waiting for rescue system...")
        dotlog = lambda: self.log_continue(".")
        wait_for_tcp_port(ip, 22, open=False, callback=dotlog)
        self.log_continue("[down]")
        wait_for_tcp_port(ip, 22, callback=dotlog)
        self.log_end("[up]")
        self.state = self.RESCUE

    def _bootstrap_rescue(self, install):
        """
        Bootstrap everything needed in order to get Nix and the partitioner
        usable in the rescue system. The latter is not only for partitioning
        but also for mounting partitions.
        """
        self.log_start("building Nix bootstrap installer...")
        bootstrap = subprocess.check_output([
            "nix-build", "<nixpkgs>", "--no-out-link", "-A",
            "hetznerNixOpsInstaller"
        ]).rstrip()
        self.log_end("done. ({0})".format(bootstrap))

        self.log_start("copying bootstrap files to rescue system...")
        tarstream = subprocess.Popen([bootstrap], stdout=subprocess.PIPE)
        if not self.has_really_fast_connection():
            stream = subprocess.Popen(["gzip", "-c"], stdin=tarstream.stdout,
                                      stdout=subprocess.PIPE)
            self.run_command("tar xz -C /", stdin=stream.stdout)
            stream.wait()
        else:
            self.run_command("tar x -C /", stdin=tarstream.stdout)
        tarstream.wait()
        self.log_end("done.")

        if install:
            self.log_start("partitioning disks...")
            out = self.run_command("nixpart -p -", capture_stdout=True,
                                   stdin_string=self.partitions)
            self.fs_info = '\n'.join(out.splitlines()[1:-1])
        else:
            self.log_start("mounting filesystems...")
            self.run_command("nixpart -m -", stdin_string=self.partitions)
        self.log_end("done.")

        if not install:
            self.log_start("checking if system in /mnt is NixOS...")
            res = self.run_command("test -e /mnt/etc/NIXOS", check=False)
            if res == 0:
                self.log_end("yes.")
            else:
                self.log_end("NO! Not mounting special filesystems.")
                return

        self.log_start("bind-mounting special filesystems...")
        for mountpoint in ("/proc", "/dev", "/dev/shm", "/sys"):
            self.log_continue("{0}...".format(mountpoint))
            cmd = "mkdir -m 0755 -p /mnt{0} && ".format(mountpoint)
            cmd += "mount --bind {0} /mnt{0}".format(mountpoint)
            self.run_command(cmd)
        self.log_end("done.")

    def reboot_rescue(self, install=False):
        """
        Use the Robot to activate the rescue system and reboot the system. By
        default, only mount partitions and do not partition or wipe anything.
        """
        self.log("rebooting machine ‘{0}’ ({1}) into rescue system"
                 .format(self.name, self.main_ipv4))
        server = self._get_server_by_ip(self.main_ipv4)
        server.rescue.activate()
        rescue_passwd = server.rescue.password
        if install or self.state not in (self.UP, self.RESCUE):
            self.log_start("sending hard reset to robot...")
            server.reboot('hard')
        else:
            self.log_start("sending reboot command...")
            self.run_command("(sleep 2; reboot) &")
        self.log_end("done.")
        self._wait_for_rescue(self.main_ipv4)
        self.rescue_passwd = rescue_passwd
        self.state = self.RESCUE
        self.ssh.reset()
        self._bootstrap_rescue(install)

    def _install_main_ssh_keys(self):
        """
        Create a SSH private/public keypair and put the public key into the
        chroot.
        """
        private, public = create_key_pair(
            key_name="NixOps client key of {0}".format(self.name)
        )
        self.main_ssh_private_key, self.main_ssh_public_key = private, public
        res = self.run_command("umask 077 && mkdir -p /mnt/root/.ssh &&"
                               " cat > /mnt/root/.ssh/authorized_keys",
                               stdin_string=public)

    def _install_base_system(self):
        self.log_start("creating missing directories...")
        cmds = ["mkdir -m 1777 -p /mnt/tmp /mnt/nix/store"]
        mntdirs = ["var", "etc", "bin", "nix/var/nix/gcroots",
                   "nix/var/nix/temproots", "nix/var/nix/manifests",
                   "nix/var/nix/userpool", "nix/var/nix/profiles",
                   "nix/var/nix/db", "nix/var/log/nix/drvs"]
        to_create = ' '.join(map(lambda d: os.path.join("/mnt", d), mntdirs))
        cmds.append("mkdir -m 0755 -p {0}".format(to_create))
        self.run_command(' && '.join(cmds))
        self.log_end("done.")

        self.log_start("bind-mounting files in /etc...")
        for etcfile in ("resolv.conf", "passwd", "group"):
            self.log_continue("{0}...".format(etcfile))
            cmd = ("if ! test -e /mnt/etc/{0}; then"
                   " touch /mnt/etc/{0} && mount --bind /etc/{0} /mnt/etc/{0};"
                   " fi").format(etcfile)
            self.run_command(cmd)
        self.log_end("done.")

        self.run_command("touch /mnt/etc/NIXOS")
        self.run_command("activate-remote")
        self._install_main_ssh_keys()
        self._gen_network_spec()

    def switch_to_configuration(self, method, sync, command=None):
        if self.state == self.RESCUE:
            # We cannot use the mountpoint command here, because it's unable to
            # detect bind mounts on files, so we just go ahead and try to
            # unmount.
            umount = 'if umount "{0}" 2> /dev/null; then rm -f "{0}"; fi'
            cmd = '; '.join([umount.format(os.path.join("/mnt/etc", mnt))
                             for mnt in ("resolv.conf", "passwd", "group")])
            self.run_command(cmd)

            command = "chroot /mnt /nix/var/nix/profiles/system/bin/"
            command += "switch-to-configuration"

        res = MachineState.switch_to_configuration(self, method, sync, command)
        if self.state == self.RESCUE and self.just_installed:
            self.reboot_sync()
            self.just_installed = False
        return res

    def _get_ethernet_interfaces(self):
        """
        Return a list of all the ethernet interfaces active on the machine.
        """
        # We don't use \(\) here to ensure this works even without GNU sed.
        cmd = "ip addr show | sed -n -e 's/^[0-9]*: *//p' | cut -d: -f1"
        return self.run_command(cmd, capture_stdout=True).splitlines()

    def _get_udev_rule_for(self, interface):
        """
        Get lines suitable for services.udev.extraRules for 'interface',
        and thus essentially map the device name to a hardware address.
        """
        cmd = "ip addr show \"{0}\" | sed -n -e 's|^.*link/ether  *||p'"
        cmd += " | cut -d' ' -f1"
        mac_addr = self.run_command(cmd.format(interface),
                                    capture_stdout=True).strip()

        rule = 'ACTION=="add", SUBSYSTEM=="net", ATTR{{address}}=="{0}", '
        rule += 'NAME="{1}"'
        return rule.format(mac_addr, interface)

    def _get_ipv4_addr_and_prefix_for(self, interface):
        """
        Return a tuple of (ipv4_address, prefix_length) for the specified
        interface.
        """
        cmd = "ip addr show \"{0}\" | sed -n -e 's/^.*inet  *//p'"
        cmd += " | cut -d' ' -f1"
        ipv4_addr_prefix = self.run_command(cmd.format(interface),
                                            capture_stdout=True).strip()
        return ipv4_addr_prefix.split('/', 1)

    def _get_default_gw(self):
        """
        Return the default gateway of the currently running machine.
        """
        cmd = "ip route list | sed -n -e 's/^default  *via  *//p'"
        cmd += " | cut -d' ' -f1"
        return self.run_command(cmd, capture_stdout=True).strip()

    def _get_nameservers(self):
        """
        Return a list of all nameservers defined on the currently running
        machine.
        """
        cmd = "cat /etc/resolv.conf | sed -n -e 's/^nameserver  *//p'"
        return self.run_command(cmd, capture_stdout=True).splitlines()

    def _indent(self, lines, level=1):
        """
        Indent list of lines by the specified level (one level = two spaces).
        """
        return map(lambda line: "  " + line, lines)

    def _gen_network_spec(self):
        """
        Generate Nix expressions related to networking configuration based on
        the currently running machine (most likely in RESCUE state) and set the
        resulting string to self.net_info.
        """
        udev_rules = []
        iface_attrs = []

        # interface-specific networking options
        for iface in self._get_ethernet_interfaces():
            if iface == "lo":
                continue

            udev_rules.append(self._get_udev_rule_for(iface))
            ipv4, prefix = self._get_ipv4_addr_and_prefix_for(iface)
            quotedipv4 = '"{0}"'.format(ipv4)
            baseattr = 'networking.interfaces.{0}.{1} = {2};'
            iface_attrs.append(baseattr.format(iface, "ipAddress", quotedipv4))
            iface_attrs.append(baseattr.format(iface, "prefixLength", prefix))

        # global networking options
        defgw = self._get_default_gw()
        nameservers = self._get_nameservers()

        udev_attrs = ["services.udev.extraRules = ''"]
        udev_attrs += self._indent(udev_rules)
        udev_attrs += ["'';"]

        attrs = iface_attrs + udev_attrs + [
            'networking.defaultGateway = "{0}";'.format(defgw),
            'networking.nameservers = [ {0} ];'.format(
                ' '.join(map(lambda ns: '"{0}"'.format(ns), nameservers))
            ),
        ]
        self.net_info = "\n".join(self._indent(attrs))

    def get_physical_spec(self):
        return self._indent(
            self.net_info.splitlines() + self.fs_info.splitlines()
        )

    def create(self, defn, check, allow_reboot, allow_recreate):
        assert isinstance(defn, HetznerDefinition)

        if self.state not in (self.RESCUE, self.UP) or check:
            self.check()

        self.set_common_state(defn)
        self.robot_user = defn.robot_user
        self.robot_pass = defn.robot_pass
        self.main_ipv4 = defn.main_ipv4
        self.partitions = defn.partitions

        if not self.vm_id:
            self.log("installing machine...")
            self.reboot_rescue(install=True)
            self._install_base_system()
            self.vm_id = "nixops-{0}-{1}".format(self.depl.uuid, self.name)
            self.just_installed = True

    def start(self):
        server = self._get_server_by_ip(defn.main_ipv4)
        server.reboot()

    def stop(self):
        """
        "Stops" the server by putting it into the rescue system.
        """
        # TODO!
        pass

    def get_ssh_name(self):
        assert self.main_ipv4
        return self.main_ipv4

    def get_ssh_password(self):
        if self.state == self.RESCUE:
            return self.rescue_passwd
        else:
            return None

    def _get_server_by_ip(self, ip):
        """
        Queries the robot for the given ip address and returns the Server
        instance if it was found.
        """
        if self.connect():
            return self._robot.servers.get(ip)
        else:
            return None

    def _check(self, res):
        if not self.vm_id:
            res.exists = False
            return

        avg = self.get_load_avg()
        if avg is None:
            if self.state in (self.UP, self.RESCUE):
                self.state = self.UNREACHABLE
            res.is_reachable = False
        elif self.run_command("test -f /etc/NIXOS", check=False) != 0:
            self.state = self.RESCUE
            self.ssh_pinged = True
            self._ssh_pinged_this_time = True
            res.is_reachable = True
        else:
            MachineState._check(self, res)

    def destroy(self):
        # TODO!
        return True
