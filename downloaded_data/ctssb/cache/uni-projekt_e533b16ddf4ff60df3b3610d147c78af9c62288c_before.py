#!/usr/bin/env python2
import sys
import os
from cpu import Cpu
import time


def printpretty(n):
    suffixes = [" ", " k", " M", " G", " T"]
    order = 0
    while n > 1000 and order < len(suffixes) - 1:
        n /= 1000
        order += 1
    suffix = suffixes[order]

    return str(int(n)) + "." + str(int(n*100) % 100) + suffix  # TODO iih


def run(fp):
    program_contents = ""
    while True:
        read = os.read(fp, 4096)
        if len(read) == 0:
            break
        program_contents += read
    os.close(fp)
    cpu = Cpu(1024*1024, program_contents)
    start = time.time()
    cpu.run()
    end = time.time()
    print
    print "Executed %sops in %ss ( %sops/sec )" % (printpretty(cpu.counter),
                                                   printpretty(end - start),
                                                   printpretty(cpu.counter / (end - start)))


def entry_point(argv):
    try:
        filename = argv[1]
    except IndexError:
        print "You must supply a filename"
        return 1

    run(os.open(filename, os.O_RDONLY, 0777))
    return 0


def target(*args):
    return entry_point, None


def jitpolicy(driver):
    from rpython.jit.codewriter.policy import JitPolicy
    return JitPolicy()

if __name__ == "__main__":
    entry_point(sys.argv)
