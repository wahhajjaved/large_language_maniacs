#!/usr/bin/python
"""
Mailpipe debug tool traps execution context for inspection

Environment variables:

    MAILPIPE_TMPDIR         Path where we save debug data
                            Default: /tmp/mailpipe-debug

Context data:
    $MAILPIPE_TMPDIR/<id>/  Per-run location where context is saved
        rerun               Symlink to executable that reruns context

        id                  <uid>:<gid>:<groups>
        env                 Serialized environment

        command             Command executed through mailpipe-debug
        exitcode            Exitcode of executed command

        stdin               Input data passed though mailpipe
        stdout              Saved output from the executed command
        stderr              Saved error output from the executed command

Example usage:

    # capture execution context
    cat > $HOME/.forward << 'EOF'
    "| mailpipe-debug"
    EOF

    # wraps around command transparently
    cat > $HOME/.forward << 'EOF'
    "| PATH=$HOME/bin:$PATH mailpipe-reply --mail-error post_comment.php"
    EOF

"""
import sys
import os
from os.path import *
import md5
import re

import commands
import errno

from StringIO import StringIO
from subprocess import Popen, PIPE
import commands

import shlex

def makedirs(path):
    try:
        os.makedirs(path)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise

class UNDEFINED:
    pass

class Context(object):
    def __init__(self, path):
        self.path = path

    @staticmethod
    def _file_str(path, s=UNDEFINED):
        if s is UNDEFINED:
            if not exists(path):
                return None

            return file(path).read().rstrip()

        else:
            if s is None:
                if exists(path):
                    os.remove(path)
            else:
                fh = file(path, "w")
                print >> fh, s
                fh.close()

    class FileProperty(object):
        @staticmethod
        def serialize(val):
            return val

        @staticmethod
        def unserialize(val):
            return val

        def __get__(self, obj, cls):
            serialized = obj._file_str(join(obj.path, self.fname))
            if serialized is not None:
                return self.unserialize(serialized)

        def __set__(self, obj, val):
            if val is not None:
                val = self.serialize(val)
            obj._file_str(join(obj.path, self.fname), val)

        def __init__(self):
            self.fname = self.__class__.__name__

    class command(FileProperty):
        @staticmethod
        def serialize(argv):
            if not argv:
                return ""

            args = argv[1:]

            for i, arg in enumerate(args):
                if re.search(r"[\s'\"]", arg):
                    args[i] = commands.mkarg(arg)
                else:
                    args[i] = " " + arg

            return argv[0] + "".join(args)

        @staticmethod
        def unserialize(s):
            return shlex.split(s)
    command = command()

    class id(FileProperty):
        @staticmethod
        def serialize(val):
            uid, gid, groups = val
            id = "%d:%d:%s" % (uid, gid, ",".join([ str(group) 
                                                    for group in groups ]))
            return id

        @staticmethod
        def unserialize(s):
            uid, gid, groups = s.split(':')
            groups = [ int(group) for group in groups.split(',') ]
            return int(uid), int(gid), groups
    id = id()

    class env(FileProperty):
        @staticmethod
        def serialize(env):
            def quote(s):
                return s.replace("\\", "\\\\").replace("\n", "\\n")

            sio = StringIO()
            for var, val in env.items():
                print >> sio, "%s=%s" % (var, quote(val))

            return sio.getvalue()

        @staticmethod
        def unserialize(s):
            def unquote(s):
                return re.sub(r'\\(.)', lambda m: ('\n' 
                                                   if m.group(1) == 'n' 
                                                   else m.group(1)), s)

            d = {}
            for line in s.splitlines():
                key, val = line.split('=', 1)
                d[key] = unquote(val)

            return d

    env = env()

    class exitcode(FileProperty):
        @staticmethod
        def serialize(num):
            return str(num)

        @staticmethod
        def unserialize(s):
            return int(s)
    exitcode = exitcode()

    class RawString(FileProperty):
        @staticmethod
        def serialize(s):
            if not s:
                return None
            return s

    class stdin(RawString):
        pass
    stdin = stdin()

    class stdout(RawString):
        pass
    stdout = stdout()

    class stderr(RawString):
        pass
    stderr = stderr()

    def run(self, input=None, command=None):
        makedirs(self.path)

        try:
            os.symlink(sys.argv[0], join(self.path, 'rerun'))
        except OSError:
            pass

        self.id = (os.getuid(), os.getgid(), os.getgroups())
        self.env = os.environ

        self.stdin = input
        if command:
            self.command = command

            def run(command, input=None):
                try:
                    child = Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE)
                    stdout, stderr = child.communicate(input)

                    return stdout, stderr, child.returncode

                except OSError, e:
                    return "", str(e), None

            self.stdout, self.stderr, self.exitcode = run(command, input)
            sys.exit(self.exitcode)

    def rerun(self, shell=False):
        uid, gid, groups = self.id

        os.setgroups(groups)
        os.setgid(gid)
        os.setuid(uid)

        if shell or not self.command:
            shell = os.environ.get("SHELL", "/bin/bash")
            print "ID: %s" % commands.getoutput("id")
            print "SHELL: %s" % shell

            if self.command:
                print "COMMAND: cat stdin | " + " ".join(self.command)

            exitcode = Popen(shell, env=self.env).wait()
        else:
            child = Popen(self.command, env=self.env, stdin=PIPE)
            child.communicate(self.stdin)
            exitcode = child.returncode

        sys.exit(exitcode)

def debug():
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print >> sys.stderr, "Syntax: %s command ..." % sys.argv[0]
        print >> sys.stderr, __doc__.strip()

        sys.exit(1)

    command = args
    input = sys.stdin.read()

    tmpdir = os.environ.get("MAILPIPE_TMPDIR", "/tmp/mailpipe-debug")
    digest = md5.md5(`command` + input).hexdigest()
    path = os.path.join(tmpdir, digest)

    ctx = Context(path)
    ctx.run(input, command)

def rerun():
    args = sys.argv[1:]
    shell = False
    if args:
        opt = args[0]

        if opt in ("-h", "--help"):
            print >> sys.stderr, "Syntax: %s [ --shell ]" % sys.argv[0]
            sys.exit(1)

        if opt == "--shell":
            shell = True

    ctx = Context(os.getcwd())
    ctx.rerun(shell)

def main():
    if basename(sys.argv[0]) == "rerun":
        return rerun()

    debug()

if __name__ == "__main__":
    main()

