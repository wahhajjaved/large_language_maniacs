import sys
import syslog

from switch import Switch


def toggle(switch_name, status):
    switch = Switch(switch_name)
    switch.toggle(status)


def main():
    if len(sys.argv) != 3:
        syslog.syslog(syslog.LOG_ERR, "Wrong number of arguments: expected: 2 , got %d" % (len(sys.argv) - 1))
        exit(1)
    switch_name, status = sys.argv[1:]
    toggle(switch_name, status)


if __name__ == '__main__':
    main()

