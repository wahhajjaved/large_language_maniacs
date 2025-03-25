# (C) 2012, Michael DeHaan, <michael.dehaan@gmail.com>

# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

#######################################################

import utils
import sys
import getpass

#######################################################

class AggregateStats(object):
    ''' holds stats about per-host activity during playbook runs '''   
 
    def __init__(self):
        self.processed   = {}
        self.failures    = {}
        self.ok          = {}
        self.dark        = {}
        self.changed     = {}
        self.skipped     = {}

    def _increment(self, what, host):
        ''' helper function to bump a statistic '''

        self.processed[host] = 1
        prev = (getattr(self, what)).get(host, 0)
        getattr(self, what)[host] = prev+1

    def compute(self, runner_results, setup=False, poll=False):
        ''' walk through all results and increment stats '''
 
        for (host, value) in runner_results.get('contacted', {}).iteritems():
            if ('failed' in value and bool(value['failed'])) or ('rc' in value and value['rc'] != 0):
                self._increment('failures', host)
            elif 'skipped' in value and bool(value['skipped']):
                self._increment('skipped', host)
            elif 'changed' in value and bool(value['changed']):
                if not setup:
                    self._increment('changed', host)
                self._increment('ok', host)
            else:
                if not poll or ('finished' in value and bool(value['finished'])):
                    self._increment('ok', host)

        for (host, value) in runner_results.get('dark', {}).iteritems():
            self._increment('dark', host)
            

    def summarize(self, host):
        ''' return information about a particular host '''

        return dict(
            ok          = self.ok.get(host, 0),
            failures    = self.failures.get(host, 0),
            unreachable = self.dark.get(host,0),
            changed     = self.changed.get(host, 0),
            skipped     = self.skipped.get(host, 0)
        )

########################################################################

class DefaultRunnerCallbacks(object):
    ''' no-op callbacks for API usage of Runner() if no callbacks are specified '''

    def __init__(self):
        pass

    def on_failed(self, host, res):
        pass

    def on_ok(self, host, res):
        pass

    def on_error(self, host, msg):
        pass

    def on_skipped(self, host):
        pass

    def on_unreachable(self, host, res):
        pass

    def on_no_hosts(self):
        pass

########################################################################

class CliRunnerCallbacks(DefaultRunnerCallbacks):
    ''' callbacks for use by /usr/bin/ansible '''

    def __init__(self):
        # set by /usr/bin/ansible later
        self.options = None 

    def on_failed(self, host, res):
        self._on_any(host,res)

    def on_ok(self, host, res):
        self._on_any(host,res)
 
    def on_unreachable(self, host, res):
        print "%s | FAILED => %s" % (host, res)
        if self.options.tree:
            utils.write_tree_file(self.options.tree, host, utils.bigjson(dict(failed=True, msg=res)))
 
    def on_skipped(self, host):
        pass

    def on_error(self, host, err):
        print >>sys.stderr, "stderr: [%s] => %s\n" % (host, err)
    
    def on_no_hosts(self):
        print >>sys.stderr, "no hosts matched\n"

    def _on_any(self, host, result):
        print utils.host_report_msg(host, self.options.module_name, result, self.options.one_line)
        if self.options.tree:
            utils.write_tree_file(self.options.tree, host, utils.bigjson(result))

########################################################################

class PlaybookRunnerCallbacks(DefaultRunnerCallbacks):
    ''' callbacks used for Runner() from /usr/bin/ansible-playbook '''

    def __init__(self, stats):
        self.stats = stats

    def on_unreachable(self, host, msg):
        print "unreachable: [%s] => %s" % (host, msg)

    def on_failed(self, host, results):
        invocation = results.get('invocation',None)
        if not invocation or invocation.startswith('setup ') or invocation.startswith('async_status '):
            print "failed: [%s] => %s\n" % (host, utils.smjson(results))
        else: 
            print "failed: [%s] => %s => %s\n" % (host, invocation, utils.smjson(results))

    def on_ok(self, host, host_result):
        invocation = host_result.get('invocation','')
        if invocation.startswith('async_status'):
            pass
        elif not invocation or invocation.startswith('setup '):
            print "ok: [%s]\n" % (host)
        else:
            print "ok: [%s] => %s\n" % (host, invocation)

    def on_error(self, host, err):
        print >>sys.stderr, "stderr: [%s] => %s\n" % (host, err)

    def on_skipped(self, host):
        print "skipping: [%s]\n" % host

    def on_no_hosts(self):
        print "no hosts matched or remaining\n"

########################################################################

class PlaybookCallbacks(object):
    ''' playbook.py callbacks used by /usr/bin/ansible-playbook '''
  
    def __init__(self):
        pass

    def on_start(self):
        print "\n"

    def on_notify(self, host, handler):
        pass

    def on_task_start(self, name, is_conditional):
        print utils.task_start_msg(name, is_conditional)

    def on_vars_prompt(self, varname, private=True):
        msg = 'input for %s: ' % varname
        if private:
            return getpass.getpass(msg)
        return raw_input(msg)
        
    def on_setup_primary(self):
        print "SETUP PHASE ****************************\n"
    
    def on_setup_secondary(self):
        print "\nVARIABLE IMPORT PHASE ******************\n"

    def on_import_for_host(self, host, imported_file):
        print "%s: importing %s" % (host, imported_file)

    def on_not_import_for_host(self, host, missing_file):
        print "%s: not importing file: %s" % (host, missing_file)

    def on_play_start(self, pattern):
        print "PLAY [%s] ****************************\n" % pattern

    def on_async_confused(self, msg):
        print msg

    def on_async_poll(self, jid, host, clock, host_result):
        print utils.async_poll_status(jid, host, clock, host_result)

