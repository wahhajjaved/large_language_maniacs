import random
import socket as s
import struct
import time
from sys import exit

from .config import DrcomConfig
from .context import DrcomContext
from .exceptions import *
from .utils import *


class DrcomApp:
    """Drcom 应用程序

    提供 Drcom 客户端的一切功能, 包括:

    1. 启动 Drcom
    2. 日志记录
    3. 错误处理
    4. 管理配置
    5. 分析抓包并生成配置
    """

    def __init__(self, config: DrcomConfig):
        """根据 DrcomConfig 实例化应用程序
        """
        self.application = config["application"]
        self.drcom = config["drcom"]
        self.core = config["core"]

        self.context = self.initContext()
        # IPv4, UDP
        self.socket = s.socket(s.AF_INET, s.SOCK_DGRAM)
        self.socket.settimeout(10)
        for i in range(60000, 0x10000):
            try:
                self.socket.bind((self.application["bind_ip"], i))
                break
            except OSError:
                # errno 98 address already in use
                continue
        else:
            raise BindPortException("从 60000 到 65536 间端口已耗尽")

    def run(self):
        """开始运行"""
        self.login()
        self.emptySocketBuffer()
        self.keepAlive()

    def initContext(self) -> DrcomContext:
        dc = DrcomContext(
            server=self.drcom["server"],
            port=self.drcom["server_port"],
            username=self.drcom["username"],
            password=self.drcom["password"],
            mac=self.drcom["mac"],
            host_ip=self.drcom["host_ip"],
            host_name=self.drcom["host_name"],
            host_os=self.drcom["host_os"],
            dhcp=self.drcom["dhcp"],
            dns=self.drcom["dns"],
            CONTROL_CHECK_STATUS=self.core["CONTROL_CHECK_STATUS"],
            ADAPTER_NUM=self.core["ADAPTER_NUM"],
            IP_DOG=self.core["IP_DOG"],
            AUTH_VERSION=self.core["AUTH_VERSION"],
            SALT=self.core["SALT"],
            KEEP_ALIVE_VERSION=self.core["KEEP_ALIVE_VERSION"],
            ROR_VERSION=self.core["ROR_VERSION"],
        )
        return dc

    def login(self):
        """登录

        调用函数

        -   :meth:`challenge`
        -   :meth:`sendLogin`
        """
        while True:
            try:
                self.challenge()
                self.sendLogin()
            except s.timeout:
                continue
            except ChallengeException:
                continue
            except LoginException:
                continue
            finally:
                break

    def challenge(self):
        """尝试连接

        读取属性

        -   drcom.server
        -   drcom.server_port

        修改属性

        -   context.SALT
        """
        rand = time.time() + random.randint(0xf, 0xff)
        pack = struct.pack("<H", int(rand) % 0xffff)
        self.socket.sendto(
            b'\x01\x02' + pack + b'\x09' + b'\x00' * 15,
            (self.context.server, self.context.port)
        )
        data, address = self.socket.recvfrom(1024)
        if data[:1] != b'\x02':
            raise ChallengeException()

        self.context.SALT = data[4:8]

    def sendLogin(self):
        """发送登录数据

        读取属性

        -   drcom.server
        -   drcom.server_port

        修改属性

        -   context.AUTH_INFO

        调用函数

        -   :meth:`makePacket`
        """
        self.socket.sendto(self.makeLoginPacket(),
                           (self.context.server, self.context.port))
        data, address = self.socket.recvfrom(1024)
        if address == (self.context.server, self.context.port):
            if data[:1] == b'\x04':
                self.context.AUTH_INFO = data[23:39]
            else:
                raise LoginException(r"data[:1] != b'\x04'")

    def makeLoginPacket(self) -> bytes:
        """构建 login 包

        读取属性

        -   context.username
        -   context.password
        -   context.SALT
        -   context.CONTROL_CHECK_STATUS
        -   context.ADAPTER_NUM
        -   context.mac
        -   context.host_ip
        -   context.IP_DOG
        -   context.host_name
        -   context.dns
        -   context.dhcp
        -   context.host_os
        -   context.AUTH_VERSION
        -   context.ROR_VERSION

        调用函数

        -   utils.md5sum
        -   utils.dump
        -   utils.ror
        -   utils.checksum

        -
        """
        data = b''
        """
        struct  _tagLoginPacket {
            struct _tagDrCOMHeader Header;
            unsigned char PasswordMd5[MD5_LEN];
            char Account[ACCOUNT_MAX_LEN];
            unsigned char ControlCheckStatus;
            unsigned char AdapterNum;
            unsigned char MacAddrXORPasswordMD5[MAC_LEN];
            unsigned char PasswordMd5_2[MD5_LEN];
            unsigned char HostIpNum;
            unsigned int HostIPList[HOST_MAX_IP_NUM];
            unsigned char HalfMD5[8];
            unsigned char DogFlag;
            unsigned int unkown2;
            struct _tagHostInfo HostInfo;
            unsigned char ClientVerInfoAndInternetMode;
            unsigned char DogVersion;
        };
        """
        # _tagLoginPacket.Header
        data += b'\x03\x01\x00' + bytes([len(self.context.username) + 20])
        # _tagLoginPacket.PasswordMD5
        data += md5sum(b'\x03\x01' + self.context.SALT +
                       self.context.password.encode())
        # _tagLoginPacket.Account
        data += (self.context.username.encode() + b'\x00'*36)[:36]
        # _tagLoginPacket.ControlCheckStatus
        data += self.context.CONTROL_CHECK_STATUS
        # _tagLoginPacket.AdapterNum
        data += self.context.ADAPTER_NUM
        # _tagLoginPacket.MacAddrXORPasswordMD5
        data += hexdump(
            int(
                binascii.hexlify(data[4:10]),
                base=16
            ) ^ self.context.mac
        )[-6:]
        # _tagLoginPacket.PasswordMD5_2
        data += md5sum(b'\x01' + self.context.password.encode() +
                       self.context.SALT + b'\x00'*4)
        # _tagLoginPacket.HostIpNum
        data += b'\x01'
        # _tagLoginPacket.HostIPList
        data += b''.join(
            [bytes([int(i)]) for i in self.context.host_ip.split('.')]
        )
        data += b'\x00'*12
        # _tagLoginPacket.HalfMD5 [8]
        data += md5sum(data + b'\x14\x00\x07\x0B')[:8]
        # _tagLoginPacket.DogFlag
        data += self.context.IP_DOG
        # _tagLoginPacket.unkown2
        data += b'\x00'*4
        # _tagLoginPacket.HostInfo
        """
        struct  _tagHostInfo {
            char HostName[HOST_NAME_MAX_LEN];
            unsigned int DNSIP1;
            unsigned int DHCPServerIP;
            unsigned int DNSIP2;
            unsigned int WINSIP1;
            unsigned int WINSIP2;
            struct _tagOSVersionInfo OSVersion;
        };
        """
        # _tagHostInfo.HostName
        data += (self.context.host_name.encode() + b'\x00'*32)[:32]
        # _tagHostInfo.DNSIP1
        data += b''.join(
            [bytes([int(i)]) for i in self.context.dns.split('.')]
        )
        # _tagHostInfo.DHCPServerIP
        data += b''.join(
            [bytes([int(i)]) for i in self.context.dhcp.split('.')]
        )
        # _tagHostInfo.DNSIP2
        data += b'\x00'*4
        # _tagHostInfo.WINSIP1
        data += b'\x00'*4
        # _tagHostInfo.WINSIP2
        data += b'\x00'*4
        # _tagHostInfo.OSVersion
        """
        struct  _tagOSVersionInfo {
            unsigned int OSVersionInfoSize;
            unsigned int MajorVersion;
            unsigned int MinorVersion;
            unsigned int BuildNumber;
            unsigned int PlatformID;
            char ServicePack[128];
        };
        """
        # _tagOSVersionInfo.OSVersionInfoSize
        data += b'\x94\x00\x00\x00'
        # _tagOSVersionInfo.MajorVersion
        data += b'\x05\x00\x00\x00'
        # _tagOSVersionInfo.MinorVersion
        data += b'\x01\x00\x00\x00'
        # _tagOSVersionInfo.BuildNumber
        data += b'\x28\x0A\x00\x00'
        # _tagOSVersionInfo.PlatformID
        data += b'\x02\x00\x00\x00'
        # _tagOSVersionInfo.ServicePack
        data += (self.context.host_os.encode() + 32*b'\x00')[:32]
        data += b'\x00'*96
        data += self.context.AUTH_VERSION
        if self.context.ROR_VERSION:
            """
            struct _tagLDAPAuth {
                unsigned char Code;
                unsigned char PasswordLen;
                unsigned char Password[MD5_LEN];
            }
            """
            # _tagLDAPAuth.Code
            data += b'\x00'
            # _tagLDAPAuth.PasswordLen
            data += bytes([len(self.context.password)])
            # _tagLDAPAuth.Password
            data += ror(md5sum(b'\x03\x01' + self.context.SALT +
                               self.context.password), self.context.password)
        """
        struct  _tagDrcomAuthExtData {
            unsigned char Code;
            unsigned char Len;
            unsigned long CRC;
            unsigned short Option;
            unsigned char AdapterAddress[MAC_LEN];
        };
        """
        # _tagDrcomAuthExtData.Code
        data += b'\x02'
        # _tagDrcomAuthExtData.Len
        data += b'\x0c'
        # _tagDrcomAuthExtData.CRC
        data += checksum(
            data + b'\x01\x26\x07\x11\x00\x00' + hexdump(self.context.mac)
        )
        # _tagDrcomAuthExtData.Option
        data += b'\x00\x00'
        # _tagDrcomAuthExtData.AdapterAddress
        data += hexdump(self.context.mac)
        # auto logout / default: False
        data += b'\x00'
        # broadcast mode / default: False
        data += b'\x00'
        # unknown, 随机填充的
        data += b'\xe9\x13'
        return data

    def emptySocketBuffer(self):
        while True:
            try:
                data, address = self.socket.recvfrom(1024)
            except s.timeout:
                break

    def keepAlive(self):
        """保持连接

        修改属性

        -   self.srv_num    新建
        -   self.tail       新建

        调用函数

        -   :meth:`keepAlive1`
        -   :meth:`keepAlive2`
        -   :meth:`keepAliveStable`
        """

        self.srv_num = 0
        self.tail = b'\x00\x00\x00\x00'
        while True:
            try:
                self.keepAlive1()
            except KeepAliveException:
                continue
            except s.timeout:
                continue
            self.keepAlive2()
            time.sleep(self.drcom["keep_alive_interval"])
            break
        self.keepAliveStable()

    def keepAlive1(self):
        """保持连接第一阶段

        读取属性

        -   context.AUTH_INFO
        -   context.SALT
        -   context.password
        -   drcom.server
        -   drcom.server_port

        调用函数

        -   utils.md5sum
        """
        data = b''
        data += b'\xff' + \
            md5sum(b'\x03\x01' + self.context.SALT +
                   self.context.password.encode())
        data += b'\x00\x00\x00'
        data += struct.pack("!H", int(time.time()) % 0xffff)
        data += b'\x00\x00\x00\x00'
        self.socket.sendto(
            data, (self.context.server, self.context.port))
        data, address = self.socket.recvfrom(1024)
        if data[:1] != b'\x07':
            raise KeepAliveException(r"keepAlive1 data[:1] != b'\x07'")

    def keepAlive2(self):
        """保持连接第二阶段

        访问属性

        -   srv_num
        -   tail
        -   context.server
        -   context.server_port

        修改属性

        -   srv_num
        -   tail

        调用函数

        -   :meth:`makeKeepAlivePacket`
        """
        # Step 1
        packet = self.makeKeepAlivePacket(1, True)
        self.socket.sendto(
            packet, (self.context.server, self.context.port))
        data, _ = self.socket.recvfrom(1024)
        if (
            data.startswith(b'\x07\x00\x28\x00') or
            data.startswith(b'\x07' + bytes([self.srv_num]) + b'\x28\x00') or
            data[:1] == b'\x07' and data[2:3] == b'\x10'
        ):
            self.srv_num += 1

        # Step 2
        packet = self.makeKeepAlivePacket(1, False)
        self.socket.sendto(
            packet, (self.context.server, self.context.port))
        data, _ = self.socket.recvfrom(1024)
        if data[:1] != b'\x07':
            raise KeepAliveException(r"data[:1] != b'\x07'")
        else:
            self.srv_num += 1
            self.tail = data[16:20]

        # Step 3
        packet = self.makeKeepAlivePacket(3, False)
        data, _ = self.socket.recvfrom(1024)
        if data[:1] != b'\x07':
            raise KeepAliveException(r"data[:1] != b'\x07'")
        else:
            self.srv_num += 1
            self.tail = data[16:20]

    def makeKeepAlivePacket(self, type_, first):
        """构建 keepalive 包

        读取属性

        self.srv_num
        self.tail

        修改属性

        调用函数
        """
        data = b''
        data += b'\x07' + bytes([self.srv_num]) + \
            b'\x28\x00\x0b' + bytes([type_])
        if first:
            data += b'\x0f\x27'
        else:
            data += self.context.KEEP_ALIVE_VERSION
        data += b'\x2f\x12\x00\x00\x00\x00\x00\x00'
        data += self.tail
        data += b'\x00\x00\x00\x00'
        if type_ == 3:
            data += b'\x00\x00\x00\x00'
            data += b''.join([bytes([int(i)])
                              for i in self.context.host_ip.split('.')])
            data += b'\x00\x00\x00\x00\x00\x00\x00\x00'
        else:
            data += b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        return data

    def keepAliveStable(self):
        """keepAlive 稳定期

        读取属性

        -   srv_num
        -   tail

        修改属性

        -   srv_num
        -   tail

        调用函数
        """
        # Step 1
        packet = self.makeKeepAlivePacket(1, False)
        self.socket.sendto(
            packet, (self.context.server, self.context.port))
        data, _ = self.socket.recvfrom(1024)
        self.srv_num += 1
        self.tail = data[16:20]

        # Step 2
        packet = self.makeKeepAlivePacket(3, False)
        self.socket.sendto(
            packet, (self.context.server, self.context.port))
        data, _ = self.socket.recvfrom(1024)
        self.tail = data[16:20]
        self.srv_num = (self.srv_num + 1) % 127

    def logout(self):
        self.challenge()
        data = b''
        if self.context.SALT:
            data += b'\x06\x01\x00'
            data += bytes([len(self.context.username) + 20])
            data += md5sum(b'\x03\x01' + self.context.SALT +
                           self.context.password.encode())
            data += (self.username.encode() + 36 * b'\x00')[:36]
            data += self.context.CONTROL_CHECK_STATUS
            data += self.context.ADAPTER_NUM
            data += hexdump(
                int(binascii.hexlify(data[4:10]), 16) ^ self.context.mac
            )[-6:0]
            data += self.context.AUTH_INFO
            self.socket.sendto(data,
                               (self.context.server, self.context.port))
            data, _ = self.socket.recvfrom(1024)
            if data[:1] == b'\x04':
                exit(0)
