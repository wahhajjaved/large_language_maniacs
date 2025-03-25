#
# Copyright (c) 2015, Adam Meily <meily.adam@gmail.com>
# Pypsi - https://github.com/ameily/pypsi
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#

from pypsi.cmdline import (StatementParser, StatementSyntaxError,
                           IORedirectionError, CommandNotFoundError)
from pypsi.namespace import Namespace
from pypsi.cmdline import StringToken, OperatorToken, WhitespaceToken
from pypsi.completers import path_completer
from pypsi.os import is_path_prefix
from pypsi.ansi import AnsiCodes
from pypsi.core import pypsi_print, Plugin, Command
from pypsi.pipes import ThreadLocalStream, InvocationThread
import readline
import sys
import os


class Shell(object):
    '''
    The command line interface that the user interacts with. All shell's need
    to inherit this base class.
    '''

    def __init__(self, shell_name='pypsi', width=79, exit_rc=-1024, ctx=None):
        '''
        Subclasses need to call the Shell constructor to properly initialize
        it.

        :param str shell_name: the name of the shell; used in error messages
        :param int exit_rc: the exit return code that is returned from a
            command when the shell needs to end execution
        :param pypsi.namespace.Namespace ctx: the base context
        '''
        self.real_stdout = sys.stdout
        self.real_stdin = sys.stdin
        self.real_stderr = sys.stderr
        self.width = width
        self.shell_name = shell_name
        self.exit_rc = exit_rc
        self.errno = 0
        self.commands = {}
        self.preprocessors = []
        self.postprocessors = []
        self.plugins = []
        self.prompt = "{name} )> ".format(name=shell_name)
        self.ctx = ctx or Namespace()

        self.parser = StatementParser()
        self.default_cmd = None
        self.register_base_plugins()
        self.fallback_cmd = None

        self.eof_is_sigint = False
        self._backup_completer = readline.get_completer()

        self.bootstrap()

        self.on_shell_ready()

    def bootstrap(self):
        import builtins
        if not isinstance(sys.stdout, ThreadLocalStream):
            sys.stdout = ThreadLocalStream(sys.stdout, width=self.width)

        if not isinstance(sys.stderr, ThreadLocalStream):
            sys.stderr = ThreadLocalStream(sys.stderr, width=self.width)

        if not isinstance(sys.stdin, ThreadLocalStream):
            sys.stdin = ThreadLocalStream(sys.stdin)

        if builtins.print != pypsi_print:
            builtins.print = pypsi_print

    def register_base_plugins(self):
        '''
        Register all base plugins that are defined.
        '''

        cls = self.__class__
        for name in dir(cls):
            attr = getattr(cls, name)
            if isinstance(attr, Command) or isinstance(attr, Plugin):
                self.register(attr)

    def register(self, obj):
        '''
        Register a :class:`~pypsi.core.Command` or a
        :class:`~pypsi.core.Plugin`.
        '''

        if isinstance(obj, Command):
            self.commands[obj.name] = obj

        if isinstance(obj, Plugin):
            self.plugins.append(obj)
            if obj.preprocess is not None:
                self.preprocessors.append(obj)
                self.preprocessors = sorted(self.preprocessors,
                                            key=lambda x: x.preprocess)
            if obj.postprocess is not None:
                self.postprocessors.append(obj)
                self.postprocessors = sorted(self.postprocessors,
                                             key=lambda x: x.postprocess)

        obj.setup(self)
        return 0

    def on_shell_ready(self):
        '''
        Hook that is called after the shell has been created.
        '''

        return 0

    def on_cmdloop_begin(self):
        '''
        Hook that is called once the :meth:`cmdloop` function is called.
        '''

        return 0

    def on_cmdloop_end(self):
        '''
        Hook that is called once the :meth:`cmdloop` has ended.
        '''

        return 0

    def get_current_prompt(self):
        if callable(self.prompt):
            prompt = self.prompt()
        else:
            prompt = self.prompt

        return self.preprocess_single(prompt, 'prompt')

    def set_readline_completer(self):
        if readline.get_completer() != self.complete:
            readline.parse_and_bind("tab: complete")
            self._backup_completer = readline.get_completer()
            readline.set_completer(self.complete)

    def reset_readline_completer(self):
        if readline.get_completer() == self.complete:
            readline.set_completer(self._backup_completer)

    def cmdloop(self):
        '''
        Begin the input processing loop where the user will be prompted for
        input.
        '''

        self.running = True
        self.set_readline_completer()
        self.on_cmdloop_begin()
        rc = 0
        try:
            while self.running:
                try:
                    raw = input(self.get_current_prompt())
                except EOFError:
                    if self.eof_is_sigint:
                        print()
                        for pp in self.preprocessors:
                            pp.on_input_canceled(self)
                    else:
                        self.running = False
                        print("exiting....")
                except KeyboardInterrupt:
                    print()
                    for pp in self.preprocessors:
                        pp.on_input_canceled(self)
                else:
                    try:
                        rc = self.execute(raw)
                        for pp in self.postprocessors:
                            pp.on_statement_finished(self, rc)
                    except SystemExit as e:
                        rc = e.code
                        print("exiting....")
                        self.running = False
        finally:
            self.on_cmdloop_end()
            self.reset_readline_completer()
        return rc

    def error(self, msg):
        print(
            AnsiCodes.red, self.shell_name, ": ", msg, AnsiCodes.reset,
            file=sys.stderr, sep=''
        )

    def mkpipe(self):
        r, w = os.pipe()
        return (
            os.fdopen(r, 'r'),
            os.fdopen(w, 'w')
        )

    def execute(self, raw):
        '''
        Parse and execute a statement.

        :param str raw: the raw command line to parse.
        :returns int: the return code of the statement.
        '''

        tokens = self.preprocess(raw, 'input')
        if not tokens:
            return 0

        statement = None

        try:
            statement = self.parser.build(tokens)
        except StatementSyntaxError as e:
            self.error(str(e))
            return 1

        rc = None

        if not statement:
            # The line was empty, a comment, or just contained whitespace.
            return rc

        # Setup the invocations
        for invoke in statement:
            try:
                # Open any and all I/O redirections and resolve the pypsi
                # comand.
                invoke.setup(self)
            except Exception as e:
                for sub in statement:
                    sub.close_streams()

                if isinstance(e, (IORedirectionError, CommandNotFoundError)):
                    # pypsi can handle I/O redirection and command not found
                    # errors, these are not fatal.
                    self.error(str(e))
                    return -1
                else:
                    # Unhandled fatal exception, re-raise it
                    raise

        # Current pipe being built
        pipe = []

        # Process the statement
        for invoke in statement:
            if invoke.chain_pipe():
                # We are in a pipe
                pipe.append(invoke)
            else:
                # We are not in a pipe

                if pipe:
                    # We have a pipe built that needs to be executed.
                    # Create the invocation threads for the pipe.
                    threads, stdin = self.create_pipe_threads(pipe)
                    # Reset the building pipe
                    pipe = []
                    # Set the current invocation's stdin to the last
                    # invocation's stdout.
                    invoke.stdin = stdin
                else:
                    # We were not in a pipe
                    threads = []

                # Start all the pipe threads, if we are processing a pipe
                for t in threads:
                    t.start()

                # Execute the invocation in the current thread.
                try:
                    rc = invoke(self)
                except Exception as e:
                    # Unhandled exception, stop all threads if any are running.
                    for t in threads:
                        t.stop()

                    # Wait for threads to terminate.
                    try:
                        for t in threads:
                            t.join()
                    except:
                        # Something went wrong or a KeyboardInterrupt was
                        # issued. Stop waiting for threads to terminate.
                        pass

                    # Print thread-specific unhandled exceptions.
                    for t in threads:
                        if t.exc_info:
                            if t.exc_info[0] == OSError:
                                msg = t.exc_info[1].strerror
                            else:
                                msg = str(t.exc_info[1])

                            print(
                                AnsiCodes.red, t.invoke.name, ": ", msg,
                                AnsiCodes.reset, sep=''
                            )

                    if isinstance(e, KeyboardInterrupt):
                        # Ctrl+c was entered
                        print()
                        rc = -1
                    elif isinstance(e, SystemExit):
                        # The command is requesting to exit the shell.
                        rc = e.code
                        print("exiting....")
                        self.running = False
                    elif isinstance(e, RuntimeError):
                        # The command was aborted by a generic exception.
                        self.error("command aborted: "+str(e))
                        rc = -1
                    else:
                        # Unhandled fatal exception, re-raise it
                        raise

                self.errno = rc

                # Check if the statement's next invocation be executed.
                if not invoke.should_continue(rc):
                    break

        return rc

    def create_pipe_threads(self, pipe):
        '''
        Given a pipe (list of :class:`~pypsi.cmdline.CommandInvocation`
        objects) create a thread to execute for each invocation.

        :returns tuple: a tuple containing the list of threads
            (:class:`~pypsi.pipes.CommandThread`) and the last invocation's
            stdout stream.
        '''

        threads = []
        stdin = None
        for invoke in pipe:
            next_stdin, stdout = self.mkpipe()

            t = InvocationThread(self, invoke, stdin=stdin, stdout=stdout)
            threads.append(t)

            stdin = next_stdin

        return threads, stdin

    def preprocess(self, raw, origin):
        for pp in self.preprocessors:
            raw = pp.on_input(self, raw)
            if raw is None:
                return None

        tokens = self.parser.tokenize(raw)
        for pp in self.preprocessors:
            tokens = pp.on_tokenize(self, tokens, origin)
            if tokens is None:
                break

        return tokens

    def preprocess_single(self, raw, origin):
        tokens = [StringToken(0, raw, quote='"')]
        for pp in self.preprocessors:
            tokens = pp.on_tokenize(self, tokens, origin)
            if not tokens:
                break

        if tokens:
            self.parser.clean_escapes(tokens)
            ret = ''
            for token in tokens:
                ret += token.text
            return ret
        return ''

    def get_completions(self, line, prefix):
        tokens = self.parser.tokenize(line)
        cmd_name = ""
        loc = None
        args = []
        next_arg = True
        ret = []
        for token in tokens:
            if isinstance(token, StringToken):
                if not cmd_name:
                    cmd_name = token.text
                    loc = 'name'
                elif loc == 'name':
                    cmd_name += token.text
                else:
                    if next_arg:
                        args.append(token.text)
                        next_arg = False
                    else:
                        args[-1] += token.text
            elif isinstance(token, OperatorToken):
                if token.operator in ('|', ';', '&&', '||'):
                    cmd_name = None
                    args = []
                    next_arg = True
                elif token.operator in ('>', '<', '>>'):
                    loc = 'path'
                    args = []
            elif isinstance(token, WhitespaceToken):
                if loc == 'name':
                    loc = None
                next_arg = True

        if loc == 'path':
            ret = path_completer(''.join(args))
        elif not cmd_name or loc == 'name':
            if is_path_prefix(cmd_name):
                ret = path_completer(cmd_name)
            else:
                ret = self.get_command_name_completions(cmd_name)
        else:
            if cmd_name not in self.commands:
                ret = []
            else:
                if next_arg:
                    args.append('')

                cmd = self.commands[cmd_name]
                ret = cmd.complete(self, args, prefix)
        return ret

    def get_command_name_completions(self, prefix):
        return [cmd for cmd in self.commands if cmd.startswith(prefix)]

    def complete(self, text, state):
        if state == 0:
            self.completion_matches = []
            begidx = readline.get_begidx()
            endidx = readline.get_endidx()
            line = readline.get_line_buffer()
            prefix = line[begidx:endidx] if line else ''
            line = line[:endidx]
            self.completion_matches = self.get_completions(line, prefix)

        if state < len(self.completion_matches):
            return self.completion_matches[state]
        return None

    def print_completion_matches(self, substitution, matches, max_len):
        print("substitution:", substitution)
        print("matches:     ", matches)
        print("max_len:     ", max_len)
