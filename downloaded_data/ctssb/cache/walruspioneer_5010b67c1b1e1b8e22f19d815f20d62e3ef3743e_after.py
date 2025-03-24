#!/usr/bin/python

import sys
import getopt

from WalrusPioneerLib import WalrusPioneerLib

class WalrusPioneerCmd:
    '''
    WalrusPioneer command line tool
    '''

    _command_list = ("list")

    @staticmethod
    def print_usage():
        print "Usage"
        pass

    def execute_cmd(self, raw_args):
        opts, args = getopt.getopt(raw_args, "v:h", ["verbose=", "help"])

        verbose_level = 0
        for opt, val in opts:
            if opt in ("-h", "--help"):
                WalrusPioneerCmd.print_usage()
                sys.exit()
            elif opt in ("-v", "--verbose"):
                verbose_level = int(val)
            else:
                print "Invalid options. Please check help info."
                WalrusPioneerCmd.print_usage()
                sys.exit()
        
        arg_len = len(args)
        
        if arg_len < 1:
            print "No command found. Please check help info."
            WalrusPioneerCmd.print_usage()
            sys.exit()

        if args[0] not in self._command_list:
            print "Invalid command. Please check help info."
            WalrusPioneerCmd.print_usage()
            sys.exit()

        if args[0] == "list":
            if arg_len > 2:
                print "Invalid command usage. Please check help info."
                WalrusPioneerCmd.print_usage()
                sys.exit()
            wpl = WalrusPioneerLib(verbose_level = verbose_level) 
            ret = 0
            try:
                if arg_len == 1:
                    ret = wpl.executecmd(cmd = 'ls')
                else:
                    ret = wpl.executecmd(cmd = 'ls', args = [].append(args[1]))
            except:
                print "Command execution failed"

        return ret

if __name__ == "__main__":
    wpc = WalrusPioneerCmd()
    ret = wpc.execute_cmd(sys.argv[1:])
    if ret != 0:
        print "---------------The result is--------------"
        print ret
        
