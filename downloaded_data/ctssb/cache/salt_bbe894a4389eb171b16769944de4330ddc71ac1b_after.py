'''
VisualOps OpsAgent states adaptor
@author: Michael (michael@mc2.io)
'''


# System imports
import os
import urllib2
from string import Template

# Internal imports
from opsagent.exception import StateException
from opsagent import utils

URI_TIMEOUT=600

class StateAdaptor(object):

    ssh_key_type = ['ssh-rsa', 'ecdsa', 'ssh-dss']
    supported_os = ['centos', 'redhat', 'debian', 'ubuntu', 'amazon']
    supported_ext = ['tar', 'tgz', 'gz', 'bz', 'bz2', 'zip', 'rar']
    mod_watch_list = ["linux.service","linux.supervisord"]
    # Custom watch map
    watch = {
            "linux.service": {
                    "file_key": "watch"
            },
            "linux.supervisord": {
                    "file_key": "watch"
            },
            "linux.docker.built": {
                    "file": "Dockerfile",
                    "dir_key": "path"
            }
    }

    mod_map = {
        ## package
        'linux.apt.package' : {
            'attributes' : {
                'name'          : 'pkgs',
                'repo'          : 'fromrepo',
                'deb-conf-file' : 'debconf',
                'verify-gpg'    : 'verify_gpg',
            },
            'states' : [
                'installed', 'latest', 'removed', 'purged'
            ],
            'type'  : 'pkg',
        },
        'linux.yum.package' : {
            'attributes' : {
                'name'          : 'pkgs',
                'repo'          : 'fromrepo',
                'verify-gpg'    : 'verify_gpg',
            },
            'states' : [
                'installed', 'latest', 'removed', 'purged'
            ],
            'type'  : 'pkg',
        },
        'common.gem.package'    : {
            'attributes' : {
                'name'  : 'names',
            },
            'states' : [
                'installed', 'removed'
            ],
            'type'  : 'gem',
            'require'   : [
                {'linux.apt.package' : { 'name' : [{'key':'rubygems'}] }},
                {'linux.yum.package' : { 'name' : [{'key':'rubygems'}] }}
            ],
        },
        'common.npm.package'    : {
            'attributes' : {
                'name'      : 'names',
                'path'      : 'dir',
            },
            'states' : [
                'installed', 'removed', 'bootstrap'
            ],
            'type'  : 'npm',
            'require'   : [
                {'linux.apt.package' : { 'name' : [{'key':'npm'}, {'key':'expect'}] }},
                {'linux.yum.package' : { 'name' : [{'key':'npm'}, {'key':'expect'}] }}
            ]
        },
        'common.pip.package'    : {
            'attributes' : {
                'name' : 'names'
            },
            'states' : [
                'installed', 'removed'
            ],
            'type'  : 'pip',
            'require' : [
                {'linux.apt.package' : { 'name' : [{'key':'python-pip'}] }},
                {'linux.yum.package' : { 'name' : [{'key':'python-pip'}] }}
            ]
        },

        ## repo
        'linux.apt.repo'    : {
            'attributes' : {
                'name'      : 'name',
                'content'   : 'contents'
            },
            'states' : [
                'managed'
            ],
            'type' : 'file',
        },
        'linux.apt.ppa'     : {
            'attributes' : {
                'name'      : 'ppa',
                'username'  : 'username',
                'password'  : 'password'
            },
            'states' : ['managed'],
            'type' : 'pkgrepo',
            # 'require' : [
            #   {'linux.apt.package' : { 'name' : [{'key':'python-dev'}, {'key':'libapt-pkg-dev'}] }},
            #   {'common.pip.package' : {'name' : [{'key':'python-apt'}]}}
            # ]
            'require_in' : {
                'linux.cmd' : {
                    'apt-get update' : 'name'
                }
            }
        },
        'linux.yum.repo' : {
            'attributes' : {
                'name'      : 'name',
                'content'   : 'contents',
                'rpm-url'   : 'rpm-url',
                'rpm-key'   : 'rpm-key'
            },
            'states' : [
                'managed'
            ],
            'type' : 'file',
            # 'require_in' : {
            #   'linux.cmd' : {
            #       'yum-config-manager --enable $name' : 'name'
            #   }
            # }
        },
        'linux.rpm.key' : {
            'attributes' : {
                'path'      : 'path',
            },
            'states' : [
                'run'
            ],
            'type' : 'cmd',
            # 'require_in' : {
            #   'linux.cmd' : {
            #       'yum-config-manager --enable $name' : 'name'
            #   }
            # }
        },
        'common.gem.source' : {
            'attributes' : {
                'url' : 'name'
            },
            'state' : [
                'run'
            ],
            'type' : 'cmd'
        },

        ## scm
        'common.git' : {
            'attributes' : {
                'path'      : 'target',
                'repo'      : 'name',
                'revision'  : 'rev',
                'ssh-key-file'  : 'identity',
                'force'     : 'force_checkout',
                'user'      : 'user',
            },
            'states' : [
                'latest', 'present',
            ],
            'type' : 'git',
            'require' : [
                {'linux.apt.package' : { 'name' : [{'key':'git'}] }},
                {'linux.yum.package' : { 'name' : [{'key':'git'}] }}
            ],
            # 'require_in' : {
            #   'linux.dir' : {
            #       'path'  : 'name',
            #       'user'  : 'user',
            #       'group' : 'group',
            #       'mode'  : 'mode',
            #   }
            # }
        },
        'common.svn' : {
            'attributes' : {
                'path'      : 'target',
                'repo'      : 'name',
                'revision'  : 'rev',
                'username'  : 'username',
                'password'  : 'password',
                'force'     : 'force',
                'user'      : 'user',
            },
            'states' : [
                'latest', 'export'
            ],
            'type' : 'svn',
            'require' : [
                {'linux.apt.package' : { 'name' : [{'key':'subversion'}] }},
                {'linux.yum.package' : { 'name' : [{'key':'subversion'}] }}
            ],
            # 'require_in' : {
            #   'linux.dir' : {
            #       'path'  : 'name',
            #       'user'  : 'user',
            #       'group' : 'group',
            #       'mode'  : 'mode'
            #   }
            # },
        },
        'common.hg' : {
            'attributes' : {
                'repo'      : 'name',
                'branch'    : 'branch',
                'revision'  : 'rev',
                'path'      : 'target',
                'user'      : 'user',
                'force'     : 'force',
            },
            'states' : [
                'latest'
            ],
            'type' : 'hg',
            'require' : [
                {'linux.apt.package' : { 'name' : [{'key':'mercurial'}] }},
                {'linux.yum.package' : { 'name' : [{'key':'mercurial'}] }}
            ],
            # 'require_in' : {
            #   'linux.dir' : {
            #       'path'  : 'name',
            #       'user'  : 'user',
            #       'group' : 'group',
            #       'mode'  : 'mode'
            #   }
            # },
        },
        ## path
        'linux.dir' : {
            'attributes' : {
                'path'      : 'names',
                'user'      : 'user',
                'group'     : 'group',
                'mode'      : 'mode',
                'recursive' : 'recurse',
                'absent'    : 'absent',
            },
            'states' : [
                'directory', 'absent'
            ],
            'type' : 'file'
        },
        'linux.file' : {
            'attributes' : {
                'path'      : 'name',
                'remote_uri': 'remote_uri',
                'user'      : 'user',
                'group'     : 'group',
                'mode'      : 'mode',
                'content'   : 'contents',
                'absent'    : 'absent',
            },
            'states' : [
                'managed', 'absent'
            ],
            'type' : 'file'
        },
        'linux.symlink' : {
            'attributes' : {
                'target' : 'name',
                'source' : 'target',
                'user'   : 'user',
                'group'  : 'group',
                'mode'   : 'mode',
                'absent' : 'absent'
            },
            'states' : [
                'symlink', 'absent'
            ],
            'type' : 'file'
        },

        ## service
        'linux.supervisord' : {
            'attributes' : {
                'name'  :   'names',
                'config':   'conf_file',
                #'watch'    :   '',
            },
            'states' : ['running', 'mod_watch'],
            'type' : 'supervisord',
            'require' : [
                {'common.pip.package' : {'name' : [{'key':'supervisor'}]}}
            ]
        },
        'linux.service' : {
            'attributes' : {
                'name' : 'names',
                # 'watch' : ''
            },
            'states' : ['running', 'mod_watch'],
            'type' : 'service',
        },

        ## cmd
        'linux.cmd' : {
            'attributes' : {
                'shell'         : 'shell',
                'cmd'           : 'name',
                'cwd'           : 'cwd',
                'user'          : 'user',
                'group'         : 'group',
                'timeout'       : 'timeout',
                'env'           : 'env',
                'if-path-present'   : 'onlyif',
                'if-path-absent'    : 'unless',
            },
            'states' : [
                'run', 'call', 'wait', 'script'
            ],
            'type' : 'cmd',
            'require' : [
                {'linux.dir' : { 'path' : ['/opt/visualops/tmp'] }}
            ]
        },

        ## cron
        'linux.cronjob' : {
            'attributes' : {
                'user'          :   'user',
                'cmd'           :   'names',
                'minute'        :   'minute',
                'hour'          :   'hour',
                'day-of-month'  :   'daymonth',
                'month'         :   'month',
                'day-of-week'   :   'dayweek',
            },
            'states' : [
                'present', 'absent'
            ],
            'type' : 'cron',
        },

        ## user
        'linux.user' : {
            'attributes' : {
                'username'  : 'name',
                'password'  : 'password',
                'fullname'  : 'fullname',
                'uid'       : 'uid',
                'gid'       : 'gid',
                'shell'     : 'shell',
                'home'      : 'home',
                'no-login'  : 'nologin',
                'groups'    : 'groups',
                'system-account'    : 'system',
            },
            'states' : [ 'present', 'absent' ],
            'type' : 'user',
        },

        ## group
        'linux.group' : {
            'attributes' : {
                'groupname' : 'name',
                'gid'       : 'gid',
                'system-group'  : 'system'
            },
            'states' : ['present', 'absent'],
            'type' : 'group'
        },

        ## mount
        'linux.mount' : {
            'attributes' : {
                'path'      :   'name',
                'device'    :   'device',
                'filesystem':   'fstype',
                'dump'      :   'dump',
                'pass'      :   'pass_num',
                'opts'      :   'opts',
                'fstab'     :   'persist'
            },
            'states' : ['mounted', 'unmounted'],
            'type' : 'mount'
        },

        ## mkfs
        'linux.mkfs' : {
            'attributes' : {
                'device'     :   'device',
                'fstype'     :   'fstype',
                'label'      :   'label',
#                'block_size' :   'block_size',
            },
            'states' : ['mkfs'],
            'type' : 'fs',
            'require' : [
                {'linux.apt.package' : { 'name' : [{'key':'xfsprogs'}] }},
                {'linux.yum.package' : { 'name' : [{'key':'xfsprogs'}],'os': ["amazon","centos",["red-hat","7.0"],["redhat","7.0"]] }}
            ],
        },

        ## selinux
        'linux.selinux' : {
            'attributes' : {
            },
            'states' : ['boolean', 'mode'],
            'type' : 'selinux',
            'linux.yum.package' : {
                'name' : ['libsemanage', 'setools-console', 'policycoreutils-python']
            }
        },

        ## timezone
        'common.timezone' : {
            'attributes' : {
                'name'      : 'name',
                'use-utc'   : 'utc'
            },
            'states' : ['system'],
            'type' : 'timezone'
        },

        ## lvm
        'linux.lvm.pv'  : {
            'attributes' : {
                'path'                  : 'names',
                'force'                 : 'force',
                'uuid'                  : 'uuid',
                'zero'                  : 'zero',
                'data-alignment'        : 'dataalignment',
                'data-alignment-offset' : 'dataalignmentoffset',
                'metadata-size'         : 'metadatasize',
                'metadata-type'         : 'metadatatype',
                'metadata-copies'       : 'metadatacopies',
                'metadata-ignore'       : 'metadataignore',
                'restore-file'          : 'restorefile',
                'no-restore-file'       : 'norestorefile',
                'label-sector'          : 'labelsector',
                'PV-size'               : 'setphysicalvolumesize',
            },
            'states' : ['pv_present'],
            'type' : 'lvm',
            'require' : [
                {'linux.apt.package' : { 'name' : [{'key':'lvm2'}] }},
                {'linux.yum.package' : { 'name' : [{'key':'lvm2'}] }}
            ]
        },
        'linux.lvm.vg'  : {
            'attributes' : {
                'name'              : 'name',
                'path'              : 'devices',
                'clustered'         : 'clustered',
                'max-lv-number'     : 'maxlogicalvolumes',
                'max-pv-number'     : 'maxphysicalvolumes',
                'metadata-type'     : 'metadatatype',
                'metadata-copies'   : 'metadatacopies',
                'pe-size'           : 'physicalextentsize',
                'autobackup'        : 'autobackup',
                'tag'               : 'addtag',
                'allocation-policy' : 'alloc',
            },
            'states' : ['vg_present', 'vg_absent'],
            'type' : 'lvm',
            'require' : [
                {'linux.apt.package' : { 'name' : [{'key':'lvm2'}] }},
                {'linux.yum.package' : { 'name' : [{'key':'lvm2'}] }}
            ]
        },
        'linux.lvm.lv'  : {
            'attributes'    : {
                'name'              : 'name',
                'vg-name'           : 'vgname',
                'path'              : 'pv',
                'chunk-size'        : 'chunksize',
                'contiguous'        : 'contiguous',
                'discards'          : 'discards',
                'stripe-number'     : 'stripes',
                'stripe-size'       : 'stripesize',
                'le-number'         : 'extents',
                'le-size'           : 'size',
                'minor-number'      : 'minor',
                'persistent'        : 'persistent',
                'mirror-number'     : 'mirrors',
                'no-udev-sync'      : 'noudevsync',
                'monitor'           : 'monitor',
                'ignore-monitoring' : 'ignoremonitoring',
                'permission'        : 'permission',
                'pool-metadata-size': 'poolmetadatasize',
                'region-size'       : 'regionsize',
                'readahead'         : 'readahead',
                'thinpool'          : 'thinpool',
                'type'              : 'type',
                'virtual-size'      : 'virtualsize',
                'zero'              : 'zero',
                'available'         : 'available',
                'snapshot'          : 'snapshot',
                'autobackup'        : 'autobackup',
                'tag'               : 'addtag',
                'allocation-policy' : 'alloc',
            },
            'states' : ['lv_present', 'lv_absent'],
            'type' : 'lvm',
            'require' : [
                {'linux.apt.package' : { 'name' : [{'key':'lvm2'}] }},
                {'linux.yum.package' : { 'name' : [{'key':'lvm2'}] }}
            ]
        },

        ## virtual env
        'common.virtualenv' : {
            'attributes' : {
                'path'                  : 'name',
                'python-bin'            : 'python',
                'system-site-packages'  : 'system_site_packages',
                # 'always-copy'         : '',
                # 'unzip-setuptools'        : '',
                # 'no-setuptools'           : '',
                # 'no-pip'              : '',
                'extra-search-dir'      : 'extra-search-dir',
                # always-copy               : '',
                'requirements-file'     : 'requirements',
            },
            'states' : ['managed'],
            'type' : 'virtualenv',
            'require' : [
                {'common.pip.package' : {'name' : [{'key':'virtualenv'}]}}
            ]
        },

        ## ssh
        'common.ssh.auth' : {
            'attributes' : {
                'authname'  :   'name',
                'username'  :   'user',
                'filename'  :   'config',
                'content'   :   'content',
                'encrypt_algorithm' : 'enc',
            },
            'states' : ['present', 'absent'],
            'type' : 'ssh_auth'
        },

        'common.ssh.known_host' : {
            'attributes' : {
                'hostname'  :   'name',
                'username'  :   'user',
                'filename'  :   'config',
                'fingerprint'       : 'fingerprint',
                'encrypt_algorithm' : 'enc',
            },
            'states' : ['present', 'absent'],
            'type' : 'ssh_known_hosts'
        },

        ## archive
        'common.archive' : {
            'attributes' : {
                'source'            : 'source',
                'path'              : 'name',
                'checksum'          : 'source_hash',
                'if-path-absent'    : 'if_absent',
            },
            'states' : ['extracted'],
            'type' : 'archive',
        },

        # docker
        'linux.docker.pulled' : {
            'attributes' : {
                    'repo'          : 'repo',
                    'tag'           : 'tag',
                    'username'      : 'username',
                    'password'      : 'password',
                    'email'         : 'email',
                    'containers'    : 'containers',
            },
            'states' : ['vops_pulled'],
            'type' : 'docker',
            'require' : [
                {'linux.yum.package' : { 'name' : [{'key':'docker-io'}], 'os': ["redhat","centos"] }},
                {'linux.yum.package' : { 'name' : [{'key':'docker'}], 'os': ["amazon"] }},
                {'linux.apt.package' : { 'name' : [{'key':'docker.io'}] }},
                {'linux.service' : { 'name' : ['docker'], 'pkg_mgr': "linux.yum.package" }},
                {'linux.service' : { 'name' : ['docker.io'], 'pkg_mgr': "linux.apt.package" }},
            ]
        },
        'linux.docker.built' : {
            'attributes' : {
                    'tag'           : 'tag',
                    'path'          : 'path',
                    'containers'    : 'containers',
                    'watch'         : 'watch',
                    'force'         : 'force',
            },
            'states' : ['vops_built'],
            'type' : 'docker',
            'require' : [
                {'linux.yum.package' : { 'name' : [{'key':'docker-io'}], 'os': ["redhat","centos"] }},
                {'linux.yum.package' : { 'name' : [{'key':'docker'}], 'os': ["amazon"] }},
                {'linux.apt.package' : { 'name' : [{'key':'docker.io'}] }},
                {'linux.service' : { 'name' : ['docker'], 'pkg_mgr': "linux.yum.package" }},
                {'linux.service' : { 'name' : ['docker.io'], 'pkg_mgr': "linux.apt.package" }},
            ]
        },
        'linux.docker.running' : {
            'attributes' : {
                    # installed
                    'container'     : 'container',
                    'image'         : 'image',
                    'command'       : 'command',
                    'entry_point'   : 'entry_point',
                    'environment'   : 'environment',
                    'volumes'       : 'volumes',
                    'mem_limit'     : 'mem_limit',
                    'cpu_shares'    : 'cpu_shares',
                    'ports'         : 'ports',
                    # running
                    'publish_all_ports': 'publish_all_ports',
                    'binds'         : 'binds',
                    'links'         : 'links',
                    'port_bindings' : 'port_bindings',
                    'force'         : 'force',
                    'count'         : 'count',
            },
            'states' : ['vops_running'],
            'type' : 'docker',
            'require' : [
                {'linux.yum.package' : { 'name' : [{'key':'docker-io'}], 'os': ["redhat","centos"] }},
                {'linux.yum.package' : { 'name' : [{'key':'docker'}], 'os': ["amazon"] }},
                {'linux.apt.package' : { 'name' : [{'key':'docker.io'}] }},
                {'linux.service' : { 'name' : ['docker'], 'pkg_mgr': "linux.yum.package" }},
                {'linux.service' : { 'name' : ['docker.io'], 'pkg_mgr': "linux.apt.package" }},
            ]
        },
        'linux.docker.pushed' : {
            'attributes' : {
                    'repository'    : 'repository',
                    'container'     : 'container',
                    'tag'           : 'tag',
                    'message'       : 'message',
                    'author'        : 'author',
                    'username'      : 'username',
                    'password'      : 'password',
                    'email'         : 'email',
                    'dep_containers': 'dep_containers',
            },
            'states' : ['vops_pushed'],
            'type' : 'docker',
            'require' : [
                {'linux.yum.package' : { 'name' : [{'key':'docker-io'}], 'os': ["redhat","centos"] }},
                {'linux.yum.package' : { 'name' : [{'key':'docker'}], 'os': ["amazon"] }},
                {'linux.apt.package' : { 'name' : [{'key':'docker.io'}] }},
                {'linux.service' : { 'name' : ['docker'], 'pkg_mgr': "linux.yum.package" }},
                {'linux.service' : { 'name' : ['docker.io'], 'pkg_mgr': "linux.apt.package" }},
            ]
        },
    }


    def __init__(self, runner):
        self.states = None
        self.os_type = runner.os_type if hasattr(runner, 'os_type') else ''
        self.os_release = runner.os_release if hasattr(runner, 'os_release') else ''

    def convert(self, step, module, parameter):
        """
            convert the module json data to salt states.
        """

        utils.log("INFO", "Begin to convert module json data ...", ("convert", self))

        if not isinstance(module, basestring):  raise StateException("Invalid input parameter: %s, %s" % (module, parameter))
        if not isinstance(parameter, dict):     raise StateException("Invalid input parameter: %s, %s" % (module, parameter))
        if module not in self.mod_map:          raise StateException("Unsupported module %s" % module)
        if not self.os_type or not isinstance(self.os_type, basestring) or self.os_type not in self.supported_os:
            raise   StateException("Invalid input parameter: %s" % self.os_type)

        # distro check and package manger check
        if (self.os_type in ['centos', 'redhat', 'amazon'] and module in ['linux.apt.package', 'linux.apt.repo']) \
            or (self.os_type in ['debian', 'ubuntu'] and module in ['linux.yum.package', 'linux.yum.repo']):
            raise StateException("Conflict on os type %s and module %s" % (self.os_type, module))

        # filter unhandler module
        if module in ['meta.comment']:
            return None

        # get agent package module
        self.__agent_pkg_module = 'linux.apt.package' if self.os_type in ['debian', 'ubuntu'] else 'linux.yum.package'

        # convert from unicode to string
        # utils.log("INFO", "Begin to convert unicode parameter to string ...", ("convert", self))
        # parameter = utils.uni2str(parameter)
        # step = str(step)
        # module = str(module)

        # convert to salt states
        try:
            utils.log("INFO", "Begin to check module %s parameter %s" % (module, str(parameter)), ("convert", self))
            module, parameter = self.__check_module(module, parameter)

            utils.log("INFO", "Begin to convert module %s" % (module), ("convert", self))
            self.states = self.__salt(step, module, parameter)

            # expand salt state
            utils.log("DEBUG", "Begin to expand salt state %s" % str(self.states), ("convert", self))
            self.__expand()

            utils.log("DEBUG", "Begin to render salt state %s " % str(self.states), ("convert", self))
            self.__render(parameter)

            utils.log("DEBUG", "Complete converting state %s" % str(self.states), ("convert", self))
        except StateException, e:
            import json
            utils.log("ERROR", "Generate salt states of id %s, module %s, parameter %s, os type %s exception: %s" % \
                (step, module, json.dumps(parameter), self.os_type, str(e)), ("convert", self))
            return None
        except Exception, e:
            utils.log("ERROR", "Generate salt states exception: %s." % str(e), ("convert", self))
            return None

        return self.states

    def __salt(self, step, module, parameter):
        salt_state = {}

        utils.log("DEBUG", "Begin to generate addin of step %s, module %s..." % (step, module), ("__salt", self))
        addin = self.__init_addin(module, parameter)

        utils.log("DEBUG", "Begin to build up of step %s, module %s..." % (step, module), ("__salt", self))
        module_states = self.__build_up(module, addin)

        try:
            for state, addin in module_states.iteritems():
                # add require
                utils.log("DEBUG", "Begin to generate requirity ...", ("__salt", self))
                require = []
                if 'require' in self.mod_map[module]:
                    req_state = self.__get_require(self.mod_map[module]['require'])
                    if req_state:
                        for item in req_state:
                            for req_tag, req_value in item.iteritems():
                                salt_state[req_tag] = req_value
                                require.append({ next(iter(req_value)) : req_tag })

                # add require in
                utils.log("DEBUG", "Begin to generate require-in ...", ("__salt", self))
                require_in = []
                if 'require_in' in self.mod_map[module]:
                    req_in_state = self.__get_require_in(self.mod_map[module]['require_in'], parameter)
                    if req_in_state:
                        for req_in_tag, req_in_value in req_in_state.iteritems():
                            salt_state[req_in_tag] = req_in_value
                            require_in.append({ next(iter(req_in_value)) : req_in_tag })

                ## add watch, todo
                utils.log("DEBUG", "Begin to generate watch ...",("__salt", self))
                if 'watch' in parameter and parameter['watch'] and module in StateAdaptor.mod_watch_list:
                    state = 'mod_watch'
                    if module == 'linux.service':
                        addin['full_restart'] = True
                    elif module == 'linux.supervisord':
                        addin['restart'] = True

                # build up module state
                module_state = [
                    state,
                    addin
                ]

                if require:     module_state.append({ 'require' : require })
                if require_in:  module_state.append({ 'require_in' : require_in })
                # if watch:     module_state.append({ 'watch' : watch })

                # tag
                #name = addin['names'] if 'names' in addin else addin['name']
                tag = self.__get_tag(module, None, step, None, state)
                utils.log("DEBUG", "Generated tag is %s" % tag, ("__salt", self))
                salt_state[tag] = {
                    self.mod_map[module]['type'] : module_state
                }

                # add env and sls
                if 'require_in' in self.mod_map[module]:
                    salt_state[tag]['__env__'] = 'base'
                    salt_state[tag]['__sls__'] = 'visualops'
        except Exception, e:
            utils.log("DEBUG", "Generate salt states of id %s module %s exception:%s" % (step, module, str(e)), ("__salt", self))
            raise StateException("Generate salt states exception")

        if not salt_state:  raise StateException("conver state failed: %s %s" % (module, parameter))
        return salt_state

    def __init_addin(self, module, parameter):
        addin = {}

        try:
            for attr, value in parameter.iteritems():
                if value is None:   continue

                if attr in self.mod_map[module]['attributes'].keys():
                    key = self.mod_map[module]['attributes'][attr]
                    if isinstance(value, dict):
                        addin[key] = [k if not v else {k:v} for k, v in value.iteritems()]
                    else:
                        addin[key] = value
        except Exception, e:
            utils.log("DEBUG", "Init module %s addin exception: %s" % (module, str(e)))
            raise StateException(str(e))

        if not addin:   raise StateException("No addin founded: %s, %s" % (module, parameter), ("__init_addin", self))
        return addin

    def __build_up(self, module, addin):
        default_state = self.mod_map[module]['states'][0]
        module_state = {
            default_state : addin
        }

        try:
            utils.log("DEBUG", "Building up, module is %s" % (module))

            if module in ['linux.apt.package', 'linux.yum.package', 'common.npm.package', 'common.pip.package', 'common.gem.package']:
                module_state = {}

                if 'pkgs' in addin:
                    pkg_flag = 'pkgs'
                elif 'names' in addin:
                    pkg_flag = 'names'
                else:
                    pkg_flag = None

                if pkg_flag:
                    for item in addin[pkg_flag]:
                        if isinstance(item, dict) and item.get('value','').endswith('.rpm'):
                            addin['sources'] = addin[pkg_flag][:]
                            del addin[pkg_flag]
                            pkg_flag = "sources"
                            break

                    for item in addin[pkg_flag]:
                        if not isinstance(item, dict):  continue

                        pkg_name = item['key'] if 'key' in item else None
                        pkg_version = item['value'] if 'value' in item else None

                        if (pkg_flag is "sources") and (not item.get('value','').endswith('.rpm')):
                            continue

                        # no latest in npm|pip|gem
                        if module.startswith('common') and pkg_version == 'latest':
                            pkg_version = 'installed'

                        if not pkg_name:    continue

                        pkg_state = default_state
                        if pkg_version and pkg_version in self.mod_map[module]['states']:
                            pkg_state = pkg_version

                        if pkg_state not in module_state:           module_state[pkg_state] = {}
                        if pkg_flag not in module_state[pkg_state]: module_state[pkg_state][pkg_flag] = []

                        if pkg_state == default_state and pkg_version != default_state:
                            if pkg_version:
                                if module in ['linux.apt.package', 'linux.yum.package']:
                                    module_state[pkg_state][pkg_flag].append({pkg_name:pkg_version})
                                elif module in ['common.pip.package', 'common.gem.package']:
                                    module_state[pkg_state][pkg_flag].append(
                                        '{0}=={1}'.format(pkg_name, pkg_version)
                                    )
                                elif module in ['common.npm.package']:
                                    module_state[pkg_state][pkg_flag].append(
                                        '{0}@{1}'.format(pkg_name, pkg_version)
                                    )
                            else:
                                module_state[pkg_state][pkg_flag].append(pkg_name)
                        else:
                            module_state[pkg_state][pkg_flag].append(pkg_name)

                    # add other parameters
                    addin.pop(pkg_flag)

                    if addin:
                        for pkg_state in module_state.keys():
                            module_state[pkg_state].update(addin)

                ## check require package
                if module in ['common.npm.package', 'common.pip.package', 'common.gem.package']:
                    cmd_name = module.split('.')[1]

                    if cmd_name and self.__check_cmd(cmd_name):
                        self.mod_map[module]['require'] = [{
                            'linux.cmd' : {
                                'cmd' : 'which {0}'.format(cmd_name)
                            }
                        }]

                if module == 'common.npm.package':
                    if self.os_type in ['redhat', 'centos'] and float(self.os_release) >= 7.0 or self.os_type == 'debian':
                        #self.__preinstall_npm()
                        self.mod_map[module].pop('require')

            elif module in ['common.git', 'common.svn', 'common.hg']:

                # svn target path(remove the last prefix)
                if 'target' in addin and addin['target'][len(addin['target'])-1] == '/':
                    addin['target'] = os.path.split(addin['target'])[0]

                # set revision
                if 'branch' in addin:
                    if module in ['common.git', 'common.hg']:
                        addin['rev'] = addin['branch']
                    addin.pop('branch')

                #
                # if module == 'common.git' and 'force' in addin and addin['force']:
                #   addin['force_checkout'] = True

            elif module in ['linux.apt.repo', 'linux.yum.repo']:
                if 'name' in addin:
                    filename = addin['name']
                    obj_dir =  None

                    if module == 'linux.apt.repo':
                        obj_dir = '/etc/apt/sources.list.d/'
                        if not filename.endswith('.list'):
                            filename += '.list'
                    elif module == 'linux.yum.repo':
                        obj_dir = '/etc/yum.repos.d/'
                        if not filename.endswith('repo'):
                            filename += '.repo'

                    if filename and obj_dir:
                        addin['name'] = obj_dir + filename

                # priority contents
                # if 'contents' in addin and 'rpm-url' in addin:
                #   addin.pop('rpm-url')

                # if 'rpm-url' in addin:
                #   module_state = {
                #       self.mod_map['linux.cmd']['states'][0] : {
                #           'name' : 'rpm -iU {0}'.format(addin['rpm-url']),
                #           'timeout' : 600
                #       }
                #   }

            elif module in ['linux.rpm.key']:
                addin['name'] = 'rpm --import {0}'.format(addin.get('path',''))
                addin.pop('path')

            elif module in ['linux.apt.ppa']:

                if 'username' in addin and addin['username'] and \
                    'password' in addin and addin['password']:
                    addin['ppa_auth'] = '{0}:{1}'.format(addin['username'], addin['password'])

                if 'username' in addin:
                    addin.pop('username')
                if 'password' in addin:
                    addin.pop('password')

            elif module in ['common.gem.source']:
                addin.update(
                    {
                        'name'  : 'gem source --add ' + addin['name'],
                        'shell' : '/bin/bash',
                        'user'  : 'root',
                        'group' : 'root',
                    }
                )

            elif module in ['common.ssh.auth', 'common.ssh.known_host']:
                auth = []

                if 'enc' in addin and addin['enc'] not in self.ssh_key_type:
                    addin['enc'] = self.ssh_key_type[0]

                if module == 'common.ssh.auth' and 'content' in addin:
                    for line in addin['content'].split('\n'):
                        if not line: continue

                        auth.append(line)

                    addin['names'] = auth

                    # remove name attribute
                    addin.pop('name')

            elif module in ['linux.dir', 'linux.file', 'linux.symlink']:
                if module == 'linux.dir':
                    addin['makedirs'] = True

                # set absent
                if 'absent' in addin and addin['absent']:
                    module_state = {'absent':{}}
                    if 'name' in addin:
                        module_state['absent']['name'] = addin['name']
                    elif 'names' in addin:
                        module_state['absent']['names'] = addin['names']

                else:
                    if 'remote_uri' in addin:
                        req = urllib2.Request(addin['remote_uri'])
                        f = urllib2.urlopen(req, timeout=URI_TIMEOUT)
                        addin['contents'] = f.read()
                        del addin['remote_uri']
                    # set default user,group
                    if 'user' not in addin:
                        addin['user'] = 'root'
                    if 'group' not in addin:
                        addin['group'] = 'root'
                    # set mode
                    if 'mode' in addin and addin['mode']:
                        addin['mode'] = int(addin['mode'])

                    # set recurse
                    if 'recurse' in addin and addin['recurse']:
                        addin['recurse'] = []
                        if 'user' in addin and addin['user']:
                            addin['recurse'].append('user')
                        if 'group' in addin and addin['group']:
                            addin['recurse'].append('group')
                        if 'mode' in addin and addin['mode']:
                            addin['recurse'].append('mode')

            elif module in ['linux.cmd']:
                cmd = []
                for flag in ['onlyif', 'unless']:
                    if flag in addin:
                        if isinstance(addin[flag], basestring):
                            cmd.append('{0} -e {1}'.format('' if flag=='onlyif' else '!', addin[flag]))

                        elif isinstance(addin[flag], list):
                            for f in addin[flag]:
                                if not isinstance(f, basestring):   continue

                                cmd.append('{0} -e {1}'.format('' if flag=='onlyif' else '!', f))

                        addin.pop(flag)

                if cmd:
                    addin['onlyif'] = '[ {0} ]'.format(' -a '.join(cmd))

                if 'timeout' in addin:
                    addin['timeout'] = int(addin['timeout'])
                else:
                    addin['timeout'] = 600

                if 'env' in addin:
                    env = {}
                    for item in addin['env']:
                        if not isinstance(item, dict):  continue
                        if 'key' not in item or not item['key'] or \
                            'value' not in item or not item['value']:   continue

                        env[item['key']] = item['value']

                    addin.pop('env')
                    if env:
                        addin['env'] = env

                # default cwd
                if 'cwd' not in addin:
                    addin['cwd'] = '/opt/visualops/tmp/'
                else:
                    self.mod_map[module].pop('require')

            elif module in ['linux.group', 'linux.user']:
                if 'gid' in addin and addin['gid']:
                    addin['gid'] = int(addin['gid'])
                if 'uid' in addin and addin['uid']:
                    addin['uid'] = int(addin['uid'])

                # set nologin shell
                if 'nologin' in addin and addin['nologin']:
                    addin['shell'] = '/sbin/nologin'
                    addin.pop('nologin')

                # set home
                if 'home' not in addin:
                    addin['home'] = '/home/{0}'.format(addin['name'])
                else:
                    addin['createhome'] = True
                    # # add dir require
                    # self.mod_map[module]['require'] = [
                    #   {'linux.dir':{'path':[addin['home']]}}
                    # ]

                # generate user password hash
                if 'password' in addin and addin['password']:
                    import string
                    import random
                    import crypt
                    random_string_len = 8
                    random_string = str(''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(random_string_len)))
                    addin['password'] = crypt.crypt(str(addin['password']), '$1$'+random_string)

            elif module in ['linux.mount']:
                for attr in ['dump', 'pass_num']:
                    if attr in addin:
                        try:
                            addin[attr] = int(addin[attr])
                        except Exception:
                            addin[attr] = 0

                # set persist
                if 'persist' not in addin:
                    addin['persist'] = False

            elif module in ['linux.lvm.pv', 'linux.lvm.vg', 'linux.lvm.lv']:
                if 'devices' in addin and isinstance(addin['devices'], list):
                    addin['devices'] = ','.join(addin['devices'])
                if 'pv' in addin and isinstance(addin['pv'], list):
                    addin['pv'] = ','.join(addin['pv'])

                for attr in ['force', 'zero', 'metadata-ignore', 'norestorefile', \
                    'clustered', 'autobackup', \
                    'contiguous', 'persistent', 'no-udev-sync', 'monitor', 'ignore-monitoring']:
                    if attr not in addin:   continue
                    if addin[attr]:
                        addin[attr] = 'y'
                    else:
                        addin[attr] = 'n'

            elif module in ['common.archive']:
                if 'source' in addin and addin['source'].find('.') > 0:
                    ext = addin['source'].split('.')[-1]
                    if ext not in self.supported_ext:
                        raise StateException("Not supported archive type %s" % addin['source'])

                    if ext == 'zip':
                        addin['archive_format'] = 'zip'
                    elif ext == 'rar':
                        addin['archive_format'] = 'rar'
                    else: # ext in ['tar', 'tgz', 'gz', 'bz', 'bz2']:
                        addin['archive_format'] = 'tar'
                        tar_options = ''
                        if ext in ['tgz', 'gz']:
                            tar_options = 'z'
                        elif ext in ['tbz', 'bz', 'bz2']:
                            tar_options = 'j'
                        elif ext in ['tlz', 'lzma']:
                            tar_options = 'J'

                        addin['tar_options'] = tar_options

                    # add require-pkg when it isnt tar
                    if ext == 'zip':
                        self.mod_map[module]['require'] = [
                            {'linux.apt.package' : { 'name' : [{'key':'zip'}, {'key':'unzip'}] }},
                            {'linux.yum.package' : { 'name' : [{'key':'zip'}, {'key':'unzip'}] }},
                        ]

                if 'source_hash' in addin:
                    try:
                        hash_list = addin['source_hash'].split(':')
                        if len(hash_list) == 2 and hash_list[0] in ['md5', 'sha1']:
                            addin['source_hash'] = '{0}={1}'.format(hash_list[0].lower(), hash_list[1].lower())
                    except Exception, e:
                        utils.log("WARNING", "Invalid source hash format: %s" % addin['source_hash'], ("__build_up", self))
                        addin.pop('source_hash')

                # add the last slash when there isnt
                addin['name'] = os.path.normpath(addin['name']) + os.sep

                # check whether previously extracted
                # try:
                #   if os.path.isdir(addin['name']):
                #       addin['if_missing'] = addin['name'] + os.path.splitext(addin['source'].split('/')[-1])[0]
                # except:
                #   pass

            elif module in ["linux.docker.running"]:
                utils.log("DEBUG", "Found docker running module", ("__build_up", self))
                if addin.get("port_bindings"):
                    utils.log("DEBUG", "Generating ports bindings, current: %s"%(addin["port_bindings"]), ("__build_up", self))
                    ports = []
                    pb = {}
                    for item in addin["port_bindings"]:
                        key = item.get("key",None)
                        value = item.get("value",None)
                        if not key or not value: continue
                        v = value.split(":")
                        pb[key] = ({
                                "HostIp": v[0],
                                "HostPort": v[1]
                        } if len(v) == 2 else {
                                "HostIp": "0.0.0.0",
                                "HostPort": v[0]
                        })
#                        k = key.split("/")
#                        port = k[0]
#                        proto = ("tcp" if len(k) != 2 else k[1])
#                        ports.append((int(port),proto))
                        ports.append(key)
                    addin.pop("port_bindings")
                    if pb and ports:
                        addin["port_bindings"] = pb
                        addin["ports"] = ports
                if addin.get("volumes"):
                    utils.log("DEBUG", "Generating volumes, current: %s"%(addin.get("volumes")), ("__build_up", self))
                    volumes = []
                    binds = {}
                    vol = addin.get("volumes",{})
                    for item in vol:
                        key = item.get("key",None)
                        value = item.get("value",None)
                        if not key or not value: continue
                        mp = value.split(":")
                        ro = (True if (len(mp) == 2 and mp[1] == "ro") else False)
                        value = mp[0]
                        volumes.append(value)
                        binds[key] = {
                            'bind': value,
                            'ro': ro
                        }
                    addin.pop("volumes")
                    if volumes and binds:
                        addin["volumes"] = volumes
                        addin["binds"] = binds
                if addin.get("environment"):
                    utils.log("DEBUG", "Generating environment, current: %s"%(addin["environment"]), ("__build_up", self))
                    env = {}
                    for item in addin["environment"]:
                        key = item.get("key","")
                        value = item.get("value","")
                        if not key: continue
                        env[key] = value
                    addin.pop("environment")
                    addin["environment"] = env
                if addin.get("links"):
                    utils.log("DEBUG", "Generating links, current: %s"%(addin["links"]), ("__build_up", self))
                    links = {}
                    for item in addin["links"]:
                        key = item.get("key","")
                        value = item.get("value","")
                        if not key or not value: continue
                        links[key] = value
                    addin.pop("links")
                    addin["links"] = links
                if addin.get("mem_limit"):
                    utils.log("DEBUG", "Generating memory limit, current: %s"%(addin["mem_limit"]), ("__build_up", self))
                    mem=addin.get("mem_limit")
                    mem_eq={
                        'b': lambda x: x,
                        'k': lambda x: x << 10,
                        'm': lambda x: x << 20,
                        'g': lambda x: x << 30,
                        't': lambda x: x << 40,
                    }
                    addin["mem_limit"] = (mem_eq[mem[-1].lower()](int(mem[:-1])) if mem[-1].lower() in mem_eq else int(mem))
                if not addin.get("count"):
                    addin["containers"] = [addin["container"]]
                else:
                    addin["containers"] = []
                    count = int(addin["count"])
                    i=0
                    while i < count:
                        addin["containers"] += ("%s_%s"%addin["container"],i+1)
                        i += 1
                addin.pop("container")
                utils.log("DEBUG", "Docker running addin: %s"%(addin), ("__build_up", self))
            elif module in ["linux.docker.built"]:
                utils.log("DEBUG", "Found docker running module", ("__build_up", self))
                if addin.get("watch"):
                    utils.log("DEBUG", "Watch state detected", ("__build_up", self))
                    addin.pop("watch")
                    addin["force"] = True
                utils.log("DEBUG", "Docker built addin: %s"%(addin), ("__build_up", self))

        except Exception, e:
            utils.log("DEBUG", "Build up module %s exception: %s" % (module, str(e)), ("__build_up", self))

        if not module_state:    raise StateException("Build up module state failed: %s" % module)
        return module_state

    def __expand(self):
        """
            Expand state's requirity and require-in when special module(gem).
        """
        if not self.states:
            utils.log("DEBUG", "No states to expand and return...", ("__expand", self))
            raise StateException("No states to expand and return")

        state_list = []

        try:
            for tag, state in self.states.iteritems():
                for module, chunk in state.iteritems():

                    if module == 'gem':
                        name_list = None
                        for item in chunk:
                            if isinstance(item, dict) and 'names' in item:  name_list = item['names']

                        if not name_list:   continue
                        for name in name_list:
                            if '==' in name:
                                the_build_up = [ i for i in chunk if 'names' not in i ]

                                # remove the name from origin
                                name_list.remove(name)

                                pkg_name, pkg_version = name.split('==')

                                the_build_up.append({
                                    "name"      : pkg_name,
                                    "version"   : pkg_version
                                })

                                # build up the special package state
                                the_state = {
                                    tag + '_' + name : {
                                        "gem" : the_build_up
                                    }
                                }

                                # get the state's require and require-in
                                req_list = [ item[next(iter(item))] for item in chunk if isinstance(item, dict) and any(['require' in item, 'require_in' in item]) ]

                                for req in req_list:
                                    if isinstance(req, list):
                                        for r in req:
                                            for r_tag in r.values():
                                                if r_tag in self.states:
                                                    the_state[r_tag] = self.states[r_tag]

                                if the_state:
                                    state_list.append(the_state)
        except Exception, e:
            utils.log("DEBUG", "Expand states exception: %s" % str(e), ("__expand", self))
            raise StateException(str(e))

        state_list.append(self.states)
        self.states = state_list

    def __get_tag(self, module, uid=None, step=None, name=None, state=None):
        """
            generate state identify tag.
        """
        tag = module.replace('.', '_')
        if step:    tag = step + '_' + tag
        if uid:     tag = uid + '_' + tag
        if name:    tag += '_' + name
        if state:   tag += '_' + state
        return '_' + tag

    def __get_require(self, require):
        """
            Generate require state.
        """

        require_state = []

        try:
            for item in require:
                for module, parameter in item.iteritems():
                    if module not in self.mod_map.keys():   continue

                    # filter not current platform's package module
                    if module in ['linux.apt.package', 'linux.yum.package'] and module != self.__agent_pkg_module:
                        continue

                    if module in ['linux.apt.package', 'linux.yum.package'] and parameter.get("os"):
                        match = False
                        for os in parameter["os"]:
                            if type(os) is list:
                                os_type=os[0]
                                os_release=os[1]
                            else:
                                os_type=os
                                os_release=None

                            if os_type == self.os_type:
                                if (not os_release) or (float(self.os_release) >= float(os_release)):
                                    match = True
                                    break

                        if not match: continue
                        del parameter["os"]


                    if module in ['linux.service'] and parameter.get('pkg_mgr'):
                        if parameter['pkg_mgr'] != self.__agent_pkg_module: continue
                        del parameter['pkg_mgr']

                    the_require_state = self.__salt('require', module, parameter)

                    if the_require_state:
                        require_state.append(the_require_state)
        except Exception, e:
            utils.log("DEBUG", "Generate salt requisities exception: %s" % str(e), ("__get_require", self))
            raise StateException(str(e))

        return require_state

    def __get_require_in(self, require_in, parameter):
        """
            Generate require in state.
        """

        require_in_state = {}

        try:
            for module, attrs in require_in.iteritems():

                # filter not current platform's package module
                if module in ['linux.apt.package', 'linux.yum.package'] and module != self.__agent_pkg_module:  continue

                if module in ['linux.service'] and parameter.get('pkg_mgr'):
                    if parameter['pkg_mgr'] != self.__agent_pkg_module: continue
                    del parameter['pkg_mgr']

                req_addin = {}
                for k, v in attrs.iteritems():
                    if not v:   continue

                    req_addin[v] = parameter[k] if k in parameter else k

                if req_addin:
                    state = self.mod_map[module]['states'][0]
                    stype = self.mod_map[module]['type']

                    tag = self.__get_tag(module, None, None, 'require_in', state)

                    require_in_state[tag] = {
                        stype : [
                            state,
                            req_addin
                        ]
                    }
        except Exception, e:
            utils.log("DEBUG", "Generate salt require in exception: %s" % str(e), ("__get_require_in", self))
            raise StateException(str(e))

        return require_in_state

    def __add_watch(self, watch, step):
        """
            Generate watch state.
        """
        if not watch or not isinstance(watch, list):
            raise StateException("Invalid watch format %s" % str(watch))

        watch_state = {}

        try:
            for f in watch:
                watch_module = 'path.dir' if os.path.isdir(file) else 'path.file'
                state = 'directory' if watch_module == 'path.dir' else 'managed'

                watch_tag = self.__get_tag(watch_module, None, step, f, state)

                watch_state[watch_tag] = {
                    'file' : [
                        state,
                        {
                            'name' : f
                        },
                    ]
                }
        except Exception, e:
            utils.log("DEBUG", "Add watch %s exception: %s" % ('|'.join(watch), str(e)), ("__add_watch", self))
            raise StateException(str(e))

        return watch_state

    def __render(self, parameter):
        """
            Rendering the states.
        """
        if not self.states or not isinstance(self.states, list):
            raise StateException("Invalid state format %s" % str(self.states))

        for idx, item in enumerate(self.states):
            for tag, value in item.iteritems():
                for module, state in value.iteritems():
                    for attr_idx, attributes in enumerate(state):
                        if not isinstance(attributes, dict):    continue

                        for attr_name, attr_value in attributes.iteritems():
                            if not isinstance(attr_value, basestring):  continue

                            if attr_value.find('$')>=0:
                                try:
                                    self.states[idx][tag][module][attr_idx][attr_name] = Template(attr_value).substitute(parameter)
                                except Exception, e:
                                    utils.log("WARNING", "Render module %s attribute %s value %s failed" % (module, attr_name, str(attr_value)), ("__render",self))
                                    pass

    def __check_module(self, module, parameter):
        """
            Check format of module parameters.
        """
        ## valid parameters check

        ## required parameters check

        ## optional parameters check
        if module == 'linux.yum.repo':
            # priority content
            if 'content' in parameter and 'rpm-url' in parameter:
                parameter.pop('rpm-url')

            # change module when rpm-url
            if 'rpm-url' in parameter:

                parameter['cmd'] = 'rpm -U --force {0}'.format(parameter['rpm-url'])

                parameter.pop('rpm-url')

                module = 'linux.cmd'

        return (module, parameter)

    def __check_cmd(self, cmd_name):
        """
            Check a command whether existed.
        """
        try:
            import subprocess
            cmd = 'which {0}'.format(cmd_name)
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)

            out, err = process.communicate()

            if process.returncode != 0:
                utils.log("ERROR", "Command %s isn't existed..."%cmd_name, ("__check_cmd", self))
                return False

            return True
        except Exception, e:
            utils.log("ERROR", "Check command %s excpetion: %s" % (cmd_name, str(e)), ("__check_cmd", self))
            return False

    # def __check_state(self, module, state):
    #   """
    #       Check supported state.
    #   """

    #   if state not in self.mod_map[module]['states']:
    #       print "not supported state %s in module %s" % (state, module)
    #       return 1

    #   return 0

    def __preinstall_npm(self):
        """
            Preinstall nodejs and npm.
        """

        try:
            if not self.os_type:
                return

            if self.os_type in ['centos', 'redhat', 'amazon']:
                pm = 'yum'
            elif self.os_type in ['debian', 'ubuntu']:
                pm = 'apt-get'
            else:
                utils.log("ERROR", "Not supported os {0}".format(self.os_type), ("__preinstall_npm", self))

            # install nodejs
            import subprocess
            if self.os_type in ['redhat']:
                cmd = '{0} install -y nodejs curl'.format(pm)
                process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)

                out, err = process.communicate()
                if process.returncode != 0:
                    utils.log("ERROR", "Excute cmd {0} failed: {1}".format(cmd, err), ("__preinstall_npm", self))
                    raise StateException("Excute cmd %s failed"%cmd)

            elif self.os_type in ['debian']:
                cmd = 'echo "deb http://ftp.us.debian.org/debian wheezy-backports main" >> /etc/apt/sources.list && apt-get update && apt-get install -y nodejs-legacy curl'

                process = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)

                out, err = process.communicate()
                if process.returncode != 0:
                    utils.log("ERROR", "Excute cmd {0} failed: {1}".format(cmd, err), ("__preinstall_npm", self))
                    raise StateException("Excute cmd %s failed"%cmd)

            # install npm
            tmp_dir = '/opt/visualops/tmp'
            cmd = 'curl --insecure https://www.npmjs.org/install.sh | bash'
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)

            out, err = process.communicate()
            if process.returncode != 0:
                utils.log("ERROR", "Excute cmd {0} failed: {1}".format(cmd, err), ("__preinstall_npm", self))
                raise StateException("Excute cmd %s failed"%cmd)
        except Exception, e:
            utils.log("ERROR", str(e), ("__preinstall_npm", self))
            raise StateException("Install npm failed")

import logging
# logger settings
LOGLVL_VALUES=['DEBUG','INFO','WARNING','ERROR']
LOG_FORMAT = '[%(levelname)s]-%(asctime)s: %(message)s'
def __log(lvl, f=None):
    level = logging.getLevelName(lvl)
    formatter = logging.Formatter(LOG_FORMAT)
    handler = (logging.handlers.RotatingFileHandler(f,maxBytes=(1024*1024*10),backupCount=5) if f else logging.StreamHandler())
    logger = logging.getLogger()
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)

# ===================== UT =====================
def ut():
#    __log('DEBUG')

    import json
    pre_states = json.loads(open('/opt/visualops/bootstrap/salt/tests/state.json').read())

    # salt_opts = {
    #   'file_client':       'local',
    #   'renderer':          'yaml_jinja',
    #   'failhard':          False,
    #   'state_top':         'salt://top.sls',
    #   'nodegroups':        {},
    #   'file_roots':        {'base': ['/srv/salt']},
    #   'state_auto_order':  False,
    #   'extension_modules': '/var/cache/salt/minion/extmods',
    #   'id':                '',
    #   'pillar_roots':      '',
    #   'cachedir':          '/code/OpsAgent/cache',
    #   'test':              False,
    # }

    config = {
        'srv_root' : '/srv/salt',
        'extension_modules' : '/var/cache/salt/minion/extmods',
        'cachedir' : '/opt/visualops/tmp/',
        'runtime': {},
        'pkg_cache': '/opt/visualops/env/var/cache/pkg'
    }

    from opsagent.state.runner import StateRunner
    runner = StateRunner(config)
    adaptor = StateAdaptor(runner)

    # print json.dumps(adaptor._salt_opts, sort_keys=True,
    #   indent=4, separators=(',', ': '))

    err_log = None
    out_log = None

    for uid, com in pre_states['component'].iteritems():
        states = {}

        for p_state in com['state']:
            try:
                step = p_state['id']
                states = adaptor.convert(step, p_state['module'], p_state['parameter'])
                print json.dumps(states)

                if not states or not isinstance(states, list):
                    err_log = "convert salt state failed"
                    print err_log
                    result = (False, err_log, out_log)
                else:
                    result = runner.exec_salt(states)
                print result
            except Exception, e:
                print str(e)
                continue

if __name__ == '__main__':
    ut()
