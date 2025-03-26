"""Coverage controllers for use by pytest-cov and nose-cov."""

import coverage
import socket
import sys
import os

from cov_core_init import UNIQUE_SEP

class CovController(object):
    """Base class for different plugin implementations."""

    def __init__(self, cov_source, cov_report, cov_config, config=None, nodeid=None):
        """Get some common config used by multiple derived classes."""

        self.cov_source = cov_source
        self.cov_report = cov_report
        self.cov_config = cov_config
        self.config = config
        self.nodeid = nodeid

        self.cov = None
        self.node_descs = set()
        self.failed_slaves = []
        self.topdir = os.getcwd()
        self.cov_data_file = '.coverage'

    def set_env(self):
        """Put info about coverage into the env so that subprocesses can activate coverage."""

        os.environ['COV_CORE_SOURCE'] = UNIQUE_SEP.join(self.cov_source)
        os.environ['COV_CORE_DATA_FILE'] = self.cov_data_file
        os.environ['COV_CORE_CONFIG'] = self.cov_config

    @staticmethod
    def unset_env():
        """Remove coverage info from env."""

        del os.environ['COV_CORE_SOURCE']
        del os.environ['COV_CORE_DATA_FILE']
        del os.environ['COV_CORE_CONFIG']

    @staticmethod
    def get_node_desc(platform, version_info):
        """Return a description of this node."""

        return 'platform %s, python %s' % (platform, '%s.%s.%s-%s-%s' % version_info[:5])

    @staticmethod
    def sep(stream, s, txt):
        if hasattr(stream, 'sep'):
            stream.sep(s, txt)
        else:
            sep_total = max((70 - 2 - len(txt)), 2)
            sep_len = sep_total / 2
            sep_extra = sep_total % 2
            out = '%s %s %s\n' % (s * sep_len, txt, s * (sep_len + sep_extra))
            stream.write(out)

    def summary(self, stream):
        """Produce coverage reports."""

        # Output coverage section header.
        if len(self.node_descs) == 1:
            self.sep(stream, '-', 'coverage: %s' % ''.join(self.node_descs))
        else:
            self.sep(stream, '-', 'coverage')
            for node_desc in sorted(self.node_descs):
                self.sep(stream, ' ', '%s' % node_desc)

        # Produce terminal report if wanted.
        if 'term' in self.cov_report or 'term-missing' in self.cov_report:
            show_missing = 'term-missing' in self.cov_report
            self.cov.report(show_missing=show_missing, ignore_errors=True, file=stream)

        # Produce annotated source code report if wanted.
        if 'annotate' in self.cov_report:
            self.cov.annotate(ignore_errors=True)
            stream.write('Coverage annotated source written next to source\n')

        # Produce html report if wanted.
        if 'html' in self.cov_report:
            self.cov.html_report(ignore_errors=True)
            stream.write('Coverage HTML written to dir %s\n' % self.cov.config.html_dir)

        # Produce xml report if wanted.
        if 'xml' in self.cov_report:
            self.cov.xml_report(ignore_errors=True)
            stream.write('Coverage XML written to file %s\n' % self.cov.config.xml_output)

        # Report on any failed slaves.
        if self.failed_slaves:
            self.sep(stream, '-', 'coverage: failed slaves')
            stream.write('The following slaves failed to return coverage data, '
                         'ensure that pytest-cov is installed on these slaves.\n')
            for node in self.failed_slaves:
                stream.write('%s\n' % node.gateway.id)


class Central(CovController):
    """Implementation for centralised operation."""

    def start(self):
        """Erase any previous coverage data and start coverage."""

        self.cov = coverage.coverage(source=self.cov_source,
                                     data_file=self.cov_data_file,
                                     config_file=self.cov_config)
        self.cov.erase()
        self.cov.start()
        self.set_env()

    def finish(self):
        """Stop coverage, save data to file and set the list of coverage objects to report on."""

        self.unset_env()
        self.cov.stop()
        self.cov.combine()
        self.cov.save()
        node_desc = self.get_node_desc(sys.platform, sys.version_info)
        self.node_descs.add(node_desc)

    def summary(self, stream):
        """Produce coverage reports."""

        CovController.summary(self, stream)


class DistMaster(CovController):
    """Implementation for distributed master."""

    def start(self):
        """Ensure coverage rc file rsynced if appropriate."""

        if self.cov_config and os.path.exists(self.cov_config):
            self.config.option.rsyncdir.append(self.cov_config)

    def configure_node(self, node):
        """Slaves need to know if they are collocated and what files have moved."""

        node.slaveinput['cov_master_host'] = socket.gethostname()
        node.slaveinput['cov_master_topdir'] = self.topdir
        node.slaveinput['cov_master_rsync_roots'] = [str(root) for root in node.nodemanager.roots]

    def testnodedown(self, node, error):
        """Collect data file name from slave.  Also save data to file if slave not collocated."""

        # If slave doesn't return any data then it is likely that this
        # plugin didn't get activated on the slave side.
        if not (hasattr(node, 'slaveoutput') and 'cov_slave_node_id' in node.slaveoutput):
            self.failed_slaves.append(node)
            return

        # If slave is not collocated then we must save the data file
        # that it returns to us.
        if 'cov_slave_lines' in node.slaveoutput:
            cov = coverage.coverage(source=self.cov_source,
                                    data_file=self.cov_data_file,
                                    data_suffix=node.slaveoutput['cov_slave_node_id'],
                                    config_file=self.cov_config)
            cov.start()
            cov.data.lines = node.slaveoutput['cov_slave_lines']
            cov.data.arcs = node.slaveoutput['cov_slave_arcs']
            cov.stop()
            cov.save()

        # Record the slave types that contribute to the data file.
        rinfo = node.gateway._rinfo()
        node_desc = self.get_node_desc(rinfo.platform, rinfo.version_info)
        self.node_descs.add(node_desc)

    def finish(self):
        """Combines coverage data and sets the list of coverage objects to report on."""

        # Combine all the suffix files into the data file.
        self.cov = coverage.coverage(source=self.cov_source,
                                     data_file=self.cov_data_file,
                                     config_file=self.cov_config)
        self.cov.erase()
        self.cov.combine()
        self.cov.save()

    def summary(self, stream):
        """Produce coverage reports."""

        CovController.summary(self, stream)


class DistSlave(CovController):
    """Implementation for distributed slaves."""

    def start(self):
        """Determine what data file and suffix to contribute to and start coverage."""

        # Determine whether we are collocated with master.
        self.is_collocated = bool(socket.gethostname() == self.config.slaveinput['cov_master_host'] and
                                  self.topdir == self.config.slaveinput['cov_master_topdir'])

        # If we are not collocated then rewrite master paths to slave paths.
        if not self.is_collocated:
            master_topdir = self.config.slaveinput['cov_master_topdir']
            slave_topdir = self.topdir
            self.cov_source = [source.replace(master_topdir, slave_topdir) for source in self.cov_source]
            self.cov_data_file = self.cov_data_file.replace(master_topdir, slave_topdir)
            self.cov_config = self.cov_config.replace(master_topdir, slave_topdir)

        # Our slave node id makes us unique from all other slaves so
        # adjust the data file that we contribute to and the master
        # will combine our data with other slaves later.
        self.cov_data_file += '.%s' % self.nodeid

        # Erase any previous data and start coverage.
        self.cov = coverage.coverage(source=self.cov_source,
                                     data_file=self.cov_data_file,
                                     config_file=self.cov_config)
        self.cov.erase()
        self.cov.start()
        self.set_env()

    def finish(self):
        """Stop coverage and send relevant info back to the master."""

        self.unset_env()
        self.cov.stop()
        self.cov.combine()
        self.cov.save()

        if self.is_collocated:
            # If we are collocated then just inform the master of our
            # data file to indicate that we have finished.
            self.config.slaveoutput['cov_slave_node_id'] = self.nodeid
        else:
            # If we are not collocated then rewrite the filenames from
            # the slave location to the master location.
            slave_topdir = self.topdir
            path_rewrites = [(os.path.join(slave_topdir, os.path.basename(rsync_root)), rsync_root)
                             for rsync_root in self.config.slaveinput['cov_master_rsync_roots']]
            path_rewrites.append((slave_topdir, self.config.slaveinput['cov_master_topdir']))

            def rewrite_path(filename):
                for slave_path, master_path in path_rewrites:
                    filename = filename.replace(slave_path, master_path)
                return filename

            lines = dict((rewrite_path(filename), data) for filename, data in self.cov.data.lines.items())
            arcs = dict((rewrite_path(filename), data) for filename, data in self.cov.data.arcs.items())

            # Send all the data to the master over the channel.
            self.config.slaveoutput['cov_slave_node_id'] = self.nodeid
            self.config.slaveoutput['cov_slave_lines'] = lines
            self.config.slaveoutput['cov_slave_arcs'] = arcs

    def summary(self, stream):
        """Only the master reports so do nothing."""

        pass
