#
# Copyright (C) 2000-2002 The ViewCVS Group. All Rights Reserved.
#
# By using this file, you agree to the terms and conditions set forth in
# the LICENSE.html file which can be found at the top level of the ViewCVS
# distribution or at http://viewcvs.sourceforge.net/license-1.html.
#
# Contact information:
#   Greg Stein, PO Box 760, Palo Alto, CA, 94302
#   gstein@lyra.org, http://viewcvs.sourceforge.net/
#
# -----------------------------------------------------------------------
#
# popen.py: a replacement for os.popen()
#
# This implementation of popen() provides a cmd + args calling sequence,
# rather than a system() type of convention. The shell facilities are not
# available, but that implies we can avoid worrying about shell hacks in
# the arguments.
#
# -----------------------------------------------------------------------
#

import os
import sys
import sapi

if sys.platform == "win32":
  import win32popen
  import win32event
  import win32process
  import debug
  import StringIO

def popen(cmd, args, mode, capture_err=1):
  if sys.platform == "win32":
    command = win32popen.CommandLine(cmd, args)

    #sapi.server.header()
    #debug.PrintStackTrace(command)

    if mode.find('r') >= 0:
      hStdIn = None        
      
      if debug.SHOW_CHILD_PROCESSES:
        dbgIn, dbgOut = None, StringIO.StringIO()

        handle, hStdOut = win32popen.MakeSpyPipe(0, 1, (dbgOut,))

        if capture_err:
          hStdErr = hStdOut
          dbgErr = dbgOut
        else:
          dbgErr = StringIO.StringIO()
          x, hStdErr = win32popen.MakeSpyPipe(None, 1, (dbgErr,))  
      else:
        handle, hStdOut = win32popen.CreatePipe(0, 1, 1, 1)
        if capture_err:
          hStdErr = hStdOut
        else:
          hStdErr = None

    else:
      if debug.SHOW_CHILD_PROCESSES:
        dbgIn, dbgOut, dbgErr = StringIO.StringIO(), StringIO.StringIO(), StringIO.StringIO()
        hStdIn, handle = win32popen.MakeSpyPipe(1, 0, (dbgIn,))
        x, hStdOut = win32popen.MakeSpyPipe(None, 1, (dbgOut,))        
        x, hStdErr = win32popen.MakeSpyPipe(None, 1, (dbgErr,))
      else:
        hStdIn, handle = win32popen.CreatePipe(0, 1, 1, 1)
        hStdOut = None
        hStdErr = None

    phandle, pid, thandle, tid = win32popen.CreateProcess(command, hStdIn, hStdOut, hStdErr)

    if debug.SHOW_CHILD_PROCESSES:
      debug.Process(command, dbgIn, dbgOut, dbgErr)
    
    return _pipe(win32popen.File2FileObject(handle, mode), phandle)

  # flush the stdio buffers since we are about to change the FD under them
  sys.stdout.flush()
  sys.stderr.flush()

  r, w = os.pipe()
  pid = os.fork()
  if pid:
    # in the parent

    # close the descriptor that we don't need and return the other one.
    if mode.find('r') >= 0:
      os.close(w)
      return _pipe(os.fdopen(r, mode), pid)
    os.close(r)
    return _pipe(os.fdopen(w, mode), pid)

  # in the child

  # we'll need /dev/null for the discarded I/O
  null = os.open('/dev/null', os.O_RDWR)

  if mode.find('r') >= 0:
    # hook stdout/stderr to the "write" channel
    os.dup2(w, 1)
    # "close" stdin; the child shouldn't use it
    ### this isn't quite right... we may want the child to read from stdin
    os.dup2(null, 0)
    # what to do with errors?
    if capture_err:
      os.dup2(w, 2)
    else:
      os.dup2(null, 2)
  else:
    # hook stdin to the "read" channel
    os.dup2(r, 0)
    # "close" stdout/stderr; the child shouldn't use them
    ### this isn't quite right... we may want the child to write to these
    os.dup2(null, 1)
    os.dup2(null, 2)

  # don't need these FDs any more
  os.close(null)
  os.close(r)
  os.close(w)

  # the stdin/stdout/stderr are all set up. exec the target
  try:
    os.execvp(cmd, (cmd,) + tuple(args))
  except:
    # aid debugging, if the os.execvp above fails for some reason:
    import string
    print "<h2>exec failed:</h2><pre>", cmd, string.join(args), "</pre>"
    raise

  # crap. shouldn't be here.
  sys.exit(127)

def pipe_cmds(cmds):
  """Executes a sequence of commands. The output of each command is directed to
  the input of the next command. A _pipe object is returned for writing to the
  first command's input. The output of the last command is directed to the
  standard out. On windows, if sys.stdout is not an inheritable file handle
  (i.e. it is not possible to direct the standard out of a child process to
  it), then a separate thread will be spawned to spool output to
  sys.stdout.write(). In all cases, the pipe_cmds() caller should refrain
  from writing to the standard out until the last process has terminated.
  """
  if sys.platform == "win32":
  
    if debug.SHOW_CHILD_PROCESSES:
      dbgIn = StringIO.StringIO()
      hStdIn, handle = win32popen.MakeSpyPipe(1, 0, (dbgIn,))
      
      i = 0
      for cmd in cmds:
        i += 1
        
        dbgOut, dbgErr = StringIO.StringIO(), StringIO.StringIO()
        
        if i < len(cmds):
          nextStdIn, hStdOut = win32popen.MakeSpyPipe(1, 1, (dbgOut,))
          x, hStdErr = win32popen.MakeSpyPipe(None, 1, (dbgErr,))
        else:
          ehandle = win32event.CreateEvent(None, 1, 0, None)
          nextStdIn, hStdOut = win32popen.MakeSpyPipe(None, 1, (dbgOut, sapi.server.getFile()), ehandle)
          x, hStdErr = win32popen.MakeSpyPipe(None, 1, (dbgErr,))

        command = win32popen.CommandLine(cmd[0], cmd[1:])
        phandle, pid, thandle, tid = win32popen.CreateProcess(command, hStdIn, hStdOut, None)
        if debug.SHOW_CHILD_PROCESSES:
          debug.Process(command, dbgIn, dbgOut, dbgErr)
          
        dbgIn = dbgOut
        hStdIn = nextStdIn

    
    else:  
  
      hStdIn, handle = win32popen.CreatePipe(1, 1, 0, 1)
      spool = None
  
      i = 0
      for cmd in cmds:
        i += 1
        if i < len(cmds):
          nextStdIn, hStdOut = win32popen.CreatePipe(1, 1, 1, 1)
        else:
          # very last process
          nextStdIn = None
          
          if sapi.server.inheritableOut:
            # send child output to standard out
            hStdOut = win32popen.MakeInheritedHandle(win32popen.FileObject2File(sys.stdout),0)
            ehandle = None
          else:
            ehandle = win32event.CreateEvent(None, 1, 0, None)
            x, hStdOut = win32popen.MakeSpyPipe(None, 1, (sapi.server.getFile(),), ehandle)            
  
        command = win32popen.CommandLine(cmd[0], cmd[1:])
        phandle, pid, thandle, tid = win32popen.CreateProcess(command, hStdIn, hStdOut, None)
        hStdIn = nextStdIn
        
    return _pipe(win32popen.File2FileObject(handle, 'wb'), phandle, ehandle)

  # flush the stdio buffers since we are about to change the FD under them
  sys.stdout.flush()
  sys.stderr.flush()

  prev_r, parent_w = os.pipe()

  null = os.open('/dev/null', os.O_RDWR)

  for cmd in cmds[:-1]:
    r, w = os.pipe()
    pid = os.fork()
    if not pid:
      # in the child

      # hook up stdin to the "read" channel
      os.dup2(prev_r, 0)

      # hook up stdout to the output channel
      os.dup2(w, 1)

      # toss errors
      os.dup2(null, 2)

      # close these extra descriptors
      os.close(prev_r)
      os.close(parent_w)
      os.close(null)
      os.close(r)
      os.close(w)

      # time to run the command
      try:
        os.execvp(cmd[0], cmd)
      except:
        pass

      sys.exit(127)

    # in the parent

    # we don't need these any more
    os.close(prev_r)
    os.close(w)

    # the read channel of this pipe will feed into to the next command
    prev_r = r

  # no longer needed
  os.close(null)

  # done with most of the commands. set up the last command to write to stdout
  pid = os.fork()
  if not pid:
    # in the child (the last command)

    # hook up stdin to the "read" channel
    os.dup2(prev_r, 0)

    # close these extra descriptors
    os.close(prev_r)
    os.close(parent_w)

    # run the last command
    try:
      os.execvp(cmds[-1][0], cmds[-1])
    except:
      pass

    sys.exit(127)

  # not needed any more
  os.close(prev_r)

  # write into the first pipe, wait on the final process
  return _pipe(os.fdopen(parent_w, 'w'), pid)


class _pipe:
  "Wrapper for a file which can wait() on a child process at close time."

  def __init__(self, file, child_pid, done_event = None):
    self.file = file
    self.child_pid = child_pid
    if sys.platform == "win32":
      if done_event:
        self.wait_for = (child_pid, done_event)
      else:
        self.wait_for = (child_pid,)

  def eof(self):
    if sys.platform == "win32":
      r = win32event.WaitForMultipleObjects(self.wait_for, 1, 0)
      if r == win32event.WAIT_OBJECT_0:
        self.file.close()
        self.file = None
        return win32process.GetExitCodeProcess(self.child_pid)
      return None

    pid, status = os.waitpid(self.child_pid, os.WNOHANG)
    if pid:
      self.file.close()
      self.file = None
      return status
    return None

  def close(self):
    if self.file:
      self.file.close()
      self.file = None
      if sys.platform == "win32":
        win32event.WaitForMultipleObjects(self.wait_for, 1, win32event.INFINITE)
        return win32process.GetExitCodeProcess(self.child_pid)
      else:
        return os.waitpid(self.child_pid, 0)[1]
    return None

  def __getattr__(self, name):
    return getattr(self.file, name)

  def __del__(self):
    self.close()
