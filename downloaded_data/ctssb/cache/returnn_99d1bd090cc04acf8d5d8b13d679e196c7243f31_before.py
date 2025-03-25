import subprocess
from subprocess import CalledProcessError
import h5py
from collections import deque
import inspect
import os
import sys
import shlex
import numpy as np
import re
import time


def cmd(s):
  """
  :type s: str
  :rtype: list[str]
  :returns all stdout splitted by newline. Does not cover stderr.
  Raises CalledProcessError on error.
  """
  p = subprocess.Popen(s, stdout=subprocess.PIPE, shell=True, close_fds=True,
                       env=dict(os.environ, LANG="en_US.UTF-8", LC_ALL="en_US.UTF-8"))
  result = [ tag.strip() for tag in p.communicate()[0].split('\n')[:-1]]
  p.stdout.close()
  if p.returncode != 0:
    raise CalledProcessError(p.returncode, s, "\n".join(result))
  return result


def eval_shell_env(token):
  if token.startswith("$"):
    return os.environ.get(token[1:], "")
  return token

def eval_shell_str(s):
  """
  :type s: str | list[str]
  :rtype: list[str]

  Parses `s` as shell like arguments (via shlex.split) and evaluates shell environment variables (eval_shell_env).
  """
  tokens = []
  if isinstance(s, (list, tuple)):
    l = s
  else:
    l = shlex.split(s)
  for token in l:
    if token.startswith("$"):
      tokens += eval_shell_str(eval_shell_env(token))
    else:
      tokens += [token]
  return tokens

def hdf5_dimension(filename, dimension):
  fin = h5py.File(filename, "r")
  if '/' in dimension:
    res = fin['/'.join(dimension.split('/')[:-1])].attrs[dimension.split('/')[-1]]
  else:
    res = fin.attrs[dimension]
  fin.close()
  return res

def hdf5_group(filename, dimension):
  fin = h5py.File(filename, "r")
  res = { k : fin[dimension].attrs[k] for k in fin[dimension].attrs }
  fin.close()
  return res

def hdf5_shape(filename, dimension):
  fin = h5py.File(filename, "r")
  res = fin[dimension].shape
  fin.close()
  return res


def hdf5_strings(handle, name, data):
  S=max([len(d) for d in data])
  dset = handle.create_dataset(name, (len(data),), dtype="S"+str(S))
  dset[...] = data


def terminal_size(): # this will probably work on linux only
  import os, sys
  if not hasattr(sys.stdout, "fileno"):
    return -1, -1
  if not os.isatty(sys.stdout.fileno()):
    return -1, -1
  env = os.environ
  def ioctl_GWINSZ(fd):
    try:
      import fcntl, termios, struct, os
      cr = struct.unpack('hh', fcntl.ioctl(fd, termios.TIOCGWINSZ,'1234'))
    except Exception:
        return
    return cr
  cr = ioctl_GWINSZ(0) or ioctl_GWINSZ(1) or ioctl_GWINSZ(2)
  if not cr:
    try:
        fd = os.open(os.ctermid(), os.O_RDONLY)
        cr = ioctl_GWINSZ(fd)
        os.close(fd)
    except Exception:
        pass
  if not cr:
    cr = (env.get('LINES', 25), env.get('COLUMNS', 80))
  return int(cr[1]), int(cr[0])


def hms(s):
  m, s = divmod(s, 60)
  h, m = divmod(m, 60)
  return "%d:%02d:%02d" % (h, m, s)

def human_size(n, factor=1000, frac=0.8, prec=1):
  postfixs = ["", "K", "M", "G", "T"]
  i = 0
  while i < len(postfixs) - 1 and n > (factor ** (i + 1)) * frac:
    i += 1
  if i == 0:
    return str(n)
  return ("%." + str(prec) + "f") % (float(n) / (factor ** i)) + postfixs[i]


def progress_bar(complete = 1.0, prefix = "", suffix = ""):
  import sys
  terminal_width, _ = terminal_size()
  if terminal_width == -1: return
  if complete == 1.0:
    sys.stdout.write("\r%s"%(terminal_width * ' '))
    sys.stdout.flush()
    sys.stdout.write("\r")
    sys.stdout.flush()
    return
  progress = "%.02f%%" % (complete * 100)
  if prefix != "": prefix = prefix + " "
  if suffix != "": suffix = " " + suffix
  ntotal = terminal_width - len(progress) - len(prefix) - len(suffix) - 4
  bars = '|' * int(complete * ntotal)
  spaces = ' ' * (ntotal - int(complete * ntotal))
  bar = bars + spaces
  sys.stdout.write("\r%s" % prefix + "[" + bar[:len(bar)/2] + " " + progress + " " + bar[len(bar)/2:] + "]" + suffix)
  sys.stdout.flush()


class _progress_bar_with_time_stats:
  start_time = None
  last_complete = None

def progress_bar_with_time(complete=1.0, prefix="", **kwargs):
  stats = _progress_bar_with_time_stats
  if stats.start_time is None:
    stats.start_time = time.time()
    stats.last_complete = complete
  if stats.last_complete > complete:
    stats.start_time = time.time()
  stats.last_complete = complete

  start_elapsed = time.time() - stats.start_time
  if complete > 0:
    total_time_estimated = start_elapsed / complete
    remaining_estimated = total_time_estimated - start_elapsed
    if prefix:
      prefix += ", " + hms(remaining_estimated)
    else:
      prefix = hms(remaining_estimated)
  progress_bar(complete, prefix=prefix, **kwargs)


def betterRepr(o):
  """
  The main difference: this one is deterministic.
  The orig dict.__repr__ has the order undefined for dict or set.
  For big dicts/sets/lists, add "," at the end to make textual diffs nicer.
  """
  if isinstance(o, list):
    return "[\n%s]" % "".join(map(lambda v: betterRepr(v) + ",\n", o))
  if isinstance(o, deque):
    return "deque([\n%s])" % "".join(map(lambda v: betterRepr(v) + ",\n", o))
  if isinstance(o, tuple):
    if len(o) == 1:
      return "(%s,)" % o[0]
    return "(%s)" % ", ".join(map(betterRepr, o))
  if isinstance(o, dict):
    l = [betterRepr(k) + ": " + betterRepr(v) for (k,v) in sorted(o.iteritems())]
    if sum([len(v) for v in l]) >= 40:
      return "{\n%s}" % "".join([v + ",\n" for v in l])
    else:
      return "{%s}" % ", ".join(l)
  if isinstance(o, set):
    return "set([\n%s])" % "".join(map(lambda v: betterRepr(v) + ",\n", o))
  # fallback
  return repr(o)


def simpleObjRepr(obj):
  """
  All self.__init__ args.
  """
  return obj.__class__.__name__ + "(%s)" % \
                                  ", ".join(["%s=%s" % (arg, betterRepr(getattr(obj, arg)))
                                             for arg in inspect.getargspec(obj.__init__).args[1:]])


class ObjAsDict:
  def __init__(self, obj):
    self.__obj = obj

  def __getitem__(self, item):
    try:
      return getattr(self.__obj, item)
    except AttributeError as e:
      raise KeyError(e)

  def items(self):
    return vars(self.__obj).items()


class DictAsObj:
  def __init__(self, dikt):
    self.__dict__ = dikt


def dict_joined(*ds):
  res = {}
  for d in ds:
    res.update(d)
  return res


def obj_diff_str(self, other):
  if self is None and other is None:
    return "No diff."
  if self is None and other is not None:
    return "self is None and other is %r" % other
  if self is not None and other is None:
    return "other is None and self is %r" % self
  if self == other:
    return "No diff."
  s = []
  def _obj_attribs(obj):
    d = getattr(obj, "__dict__", None)
    if d is not None:
      return d.keys()
    return None
  self_attribs = _obj_attribs(self)
  other_attribs = _obj_attribs(other)
  if self_attribs is None or other_attribs is None:
    return "self: %r, other: %r" % (self, other)
  for attrib in sorted(set(self_attribs).union(other_attribs)):
    if attrib not in self_attribs or attrib not in other_attribs:
      s += ["attrib %r not on both" % attrib]
      continue
    value_self = getattr(self, attrib)
    value_other = getattr(other, attrib)
    if isinstance(value_self, list):
      if not isinstance(value_other, list):
        s += ["attrib %r self is list but other is %r" % (attrib, type(value_other))]
      elif len(value_self) != len(value_other):
        s += ["attrib %r list differ. len self: %i, len other: %i" % (attrib, len(value_self), len(value_other))]
      else:
        for i, (a, b) in enumerate(zip(value_self, value_other)):
          if a != b:
            s += ["attrib %r[%i] differ. self: %r, other: %r" % (attrib, i, a, b)]
    elif isinstance(value_self, dict):
      if not isinstance(value_other, dict):
        s += ["attrib %r self is dict but other is %r" % (attrib, type(value_other))]
      elif value_self != value_other:
        s += ["attrib %r dict differs:" % attrib]
        s += ["  " + l for l in dict_diff_str(value_self, value_other).splitlines()]
    else:
      if value_self != value_other:
        s += ["attrib %r differ. self: %r, other: %r" % (attrib, value_self, value_other)]
  if s:
    return "\n".join(s)
  else:
    return "No diff."


def dict_diff_str(self, other):
  return obj_diff_str(DictAsObj(self), DictAsObj(other))


def find_ranges(l):
  """
  :type l: list[int]
  :returns list of ranges (start,end) where end is exclusive
  such that the union of range(start,end) matches l.
  :rtype: list[(int,int)]
  We expect that the incoming list is sorted and strongly monotonic increasing.
  """
  if not l:
    return []
  ranges = [(l[0], l[0])]
  for k in l:
    assert k >= ranges[-1][1]  # strongly monotonic increasing
    if k == ranges[-1][1]:
      ranges[-1] = (ranges[-1][0], k + 1)
    else:
      ranges += [(k, k + 1)]
  return ranges


def initThreadJoinHack():
  import threading, thread
  mainThread = threading.currentThread()
  assert isinstance(mainThread, threading._MainThread)
  mainThreadId = thread.get_ident()

  # Patch Thread.join().
  join_orig = threading.Thread.join
  def join_hacked(threadObj, timeout=None):
    """
    :type threadObj: threading.Thread
    :type timeout: float|None
    """
    if timeout is None and thread.get_ident() == mainThreadId:
      # This is a HACK for Thread.join() if we are in the main thread.
      # In that case, a Thread.join(timeout=None) would hang and even not respond to signals
      # because signals will get delivered to other threads and Python would forward
      # them for delayed handling to the main thread which hangs.
      # See CPython signalmodule.c.
      # Currently the best solution I can think of:
      while threadObj.isAlive():
        join_orig(threadObj, timeout=0.1)
    else:
      # In all other cases, we can use the original.
      join_orig(threadObj, timeout=timeout)
  threading.Thread.join = join_hacked

  # Mostly the same for Condition.wait().
  cond_wait_orig = threading._Condition.wait
  def cond_wait_hacked(cond, timeout=None, *args):
    if timeout is None and thread.get_ident() == mainThreadId:
      # Use a timeout anyway. This should not matter for the underlying code.
      cond_wait_orig(cond, timeout=0.1)
    else:
      cond_wait_orig(cond, timeout=timeout)
  threading._Condition.wait = cond_wait_hacked


def start_daemon_thread(target, args=()):
  from threading import Thread
  t = Thread(target=target, args=args)
  t.daemon = True
  t.start()

def is_quitting():
  import rnn
  if rnn.quit:  # via rnn.finalize()
    return True
  if getattr(sys, "exited", False):  # set via Debug module when an unexpected SIGINT occurs, or here
    return True
  return False

def interrupt_main():
  import thread
  import threading
  is_main_thread = isinstance(threading.currentThread(), threading._MainThread)
  if is_quitting():  # ignore if we are already quitting
    if is_main_thread:  # strange to get again in main thread
      raise Exception("interrupt_main() from main thread while already quitting")
    # Not main thread. This will just exit the thread.
    sys.exit(1)
  sys.exited = True  # Don't do it twice.
  sys.exited_frame = sys._getframe()
  if is_main_thread:
    raise KeyboardInterrupt
  else:
    thread.interrupt_main()
    sys.exit(1)  # And exit the thread.


def try_run(func, args=(), catch_exc=Exception, default=None):
  try:
    return func(*args)
  except catch_exc:
    return default


def class_idx_seq_to_1_of_k(seq, num_classes):
  num_frames = len(seq)
  m = np.zeros((num_frames, num_classes))
  m[np.arange(num_frames), seq] = 1
  return m


def uniq(seq):
  """
  Like Unix tool uniq. Removes repeated entries.
  :param seq: numpy.array
  :return: seq
  """
  diffs = np.ones_like(seq)
  diffs[1:] = seq[1:] - seq[:-1]
  idx = diffs.nonzero()
  return seq[idx]


def parse_orthography_into_symbols(orthography, upper_case_special=True):
  """
  For Speech.
  Parses "hello [HESITATION] there " -> list("hello ") + ["[HESITATION]"] + list(" there ").
  No pre/post-processing such as:
  Spaces are kept as-is. No stripping at begin/end. (E.g. trailing spaces are not removed.)
  No tolower/toupper.
  Doesn't add [BEGIN]/[END] symbols or so.
  Any such operations should be done explicitly in an additional function.
  :param str orthography: example: "hello [HESITATION] there "
  :rtype: list[str]
  """
  ret = []
  in_special = 0
  for c in orthography:
    if in_special:
      if c == "[":  # special-special
        in_special += 1
        ret[-1] += "["
      elif c == "]":
        in_special -= 1
        ret[-1] += "]"
      elif upper_case_special:
        ret[-1] += c.upper()
      else:
        ret[-1] += c
    else:  # not in_special
      if c == "[":
        in_special = 1
        ret += ["["]
      else:
        ret += c
  return ret


def parse_orthography(orthography, prefix=(), postfix=("[END]",),
                      remove_chars="(){}", collapse_spaces=True, final_strip=True,
                      **kwargs):
  """
  For Speech. Full processing.
  Parses "hello [HESITATION] there " -> list("hello ") + ["[HESITATION]"] + list(" there") + ["[END]"].
  :param str orthography: e.g. "hello [HESITATION] there "
  :rtype: list[str]
  """
  for c in remove_chars:
    orthography = orthography.replace(c, "")
  if collapse_spaces:
    orthography = " ".join(orthography.split())
  if final_strip:
    orthography = orthography.strip()
  return list(prefix) + parse_orthography_into_symbols(orthography, **kwargs) + list(postfix)


def json_remove_comments(string, strip_space=True):
  """
  :type string: str
  :rtype: str

  via https://github.com/getify/JSON.minify/blob/master/minify_json.py,
  by Gerald Storer, Pradyun S. Gedam, modified by us.
  """
  tokenizer = re.compile('"|(/\*)|(\*/)|(//)|\n|\r')
  end_slashes_re = re.compile(r'(\\)*$')

  in_string = False
  in_multi = False
  in_single = False

  new_str = []
  index = 0

  for match in re.finditer(tokenizer, string):

    if not (in_multi or in_single):
      tmp = string[index:match.start()]
      if not in_string and strip_space:
        # replace white space as defined in standard
        tmp = re.sub('[ \t\n\r]+', '', tmp)
      new_str.append(tmp)

    index = match.end()
    val = match.group()

    if val == '"' and not (in_multi or in_single):
      escaped = end_slashes_re.search(string, 0, match.start())

      # start of string or unescaped quote character to end string
      if not in_string or (escaped is None or len(escaped.group()) % 2 == 0):
        in_string = not in_string
      index -= 1 # include " character in next catch
    elif not (in_string or in_multi or in_single):
      if val == '/*':
        in_multi = True
      elif val == '//':
        in_single = True
    elif val == '*/' and in_multi and not (in_string or in_single):
      in_multi = False
    elif val in '\r\n' and not (in_multi or in_string) and in_single:
      in_single = False
    elif not ((in_multi or in_single) or (val in ' \r\n\t' and strip_space)):
      new_str.append(val)

  new_str.append(string[index:])
  return ''.join(new_str)


def load_json(filename=None, content=None):
  if content:
    assert not filename
  else:
    content = open(filename).read()
  import json
  content = json_remove_comments(content)
  try:
    json_content = json.loads(content)
  except ValueError as e:
    raise Exception("config looks like JSON but invalid json content, %r" % e)
  return json_content


class NumbersDict:
  """
  It's mostly like dict[str,float|int] & some optional broadcast default value.
  It implements the standard math bin ops in a straight-forward way.
  """

  def __init__(self, auto_convert=None, numbers_dict=None, broadcast_value=None):
    if auto_convert is not None:
      assert broadcast_value is None
      assert numbers_dict is None
      if isinstance(auto_convert, dict):
        numbers_dict = auto_convert
      elif isinstance(auto_convert, NumbersDict):
        numbers_dict = auto_convert.dict
        broadcast_value = auto_convert.value
      else:
        broadcast_value = auto_convert
    if numbers_dict is None:
      numbers_dict = {}
    else:
      numbers_dict = dict(numbers_dict)  # force copy

    self.dict = numbers_dict
    self.value = broadcast_value
    self.max = self.__max_error

  @property
  def keys_set(self):
    return set(self.dict.keys())

  def __getitem__(self, key):
    return self.dict.get(key, self.value)

  def __setitem__(self, key, value):
    self.dict[key] = value

  def get(self, key, default=None):
    return self.dict.get(key, default)

  def __iter__(self):
    # This can potentially cause confusion. So enforce explicitness.
    # For a dict, we would return the dict keys here.
    # Also, max(self) would result in a call to self.__iter__(),
    # which would only make sense for our values, not the dict keys.
    raise Exception("%s.__iter__ is undefined" % self.__class__.__name__)

  def keys(self):
    return self.dict.keys()

  def values(self):
    return list(self.dict.values()) + ([self.value] if self.value is not None else [])

  def has_values(self):
    return bool(self.dict) or self.value is not None

  @classmethod
  def bin_op_scalar_optional(cls, self, other, zero, op):
    if self is None and other is None:
      return None
    if self is None:
      self = zero
    if other is None:
      other = zero
    return op(self, other)

  @classmethod
  def bin_op(cls, self, other, op, zero, result=None):
    if not isinstance(self, NumbersDict):
      self = NumbersDict(self)
    if not isinstance(other, NumbersDict):
      other = NumbersDict(other)
    if result is None:
      result = NumbersDict()
    assert isinstance(result, NumbersDict)
    for k in self.keys_set | other.keys_set:
      result[k] = cls.bin_op_scalar_optional(self[k], other[k], zero=zero, op=op)
    result.value = cls.bin_op_scalar_optional(self.value, other.value, zero=zero, op=op)
    return result

  def __add__(self, other):
    return self.bin_op(self, other, op=lambda a, b: a + b, zero=0)

  __radd__ = __add__

  def __iadd__(self, other):
    return self.bin_op(self, other, op=lambda a, b: a + b, zero=0, result=self)

  def __sub__(self, other):
    return self.bin_op(self, other, op=lambda a, b: a - b, zero=0)

  def __rsub__(self, other):
    return self.bin_op(self, other, op=lambda a, b: b - a, zero=0)

  def __isub__(self, other):
    return self.bin_op(self, other, op=lambda a, b: a - b, zero=0, result=self)

  def __mul__(self, other):
    return self.bin_op(self, other, op=lambda a, b: a * b, zero=1)

  __rmul__ = __mul__

  def __imul__(self, other):
    return self.bin_op(self, other, op=lambda a, b: a * b, zero=1, result=self)

  def __div__(self, other):
    return self.bin_op(self, other, op=lambda a, b: a / b, zero=1)

  def __rdiv__(self, other):
    return self.bin_op(self, other, op=lambda a, b: b / a, zero=1)

  def __idiv__(self, other):
    return self.bin_op(self, other, op=lambda a, b: a / b, zero=1, result=self)

  def elem_eq(self, other, result_with_default=False):
    """
    Element-wise equality check with other.
    Note about broadcast default value: Consider some key which is neither in self nor in other.
      This means that self[key] == self.default, other[key] == other.default.
      Thus, in case that self.default != other.default, we get res.default == False.
      Then, all(res.values()) == False, even when all other values are True.
      This is often not what we want.
      You can control the behavior via result_with_default.
    """
    res = self.bin_op(self, other, op=lambda a, b: a == b, zero=None)
    if not result_with_default:
      res.value = None
    return res

  def __eq__(self, other):
    return all(self.elem_eq(other).values())

  def __ne__(self, other):
    return not (self == other)

  def __cmp__(self, other):
    # There is no good straight-forward implementation
    # and it would just confuse.
    raise Exception("%s.__cmp__ is undefined" % self.__class__.__name__)

  @classmethod
  def max(cls, items):
    """
    Element-wise maximum for item in items.
    """
    if not items:
      return None
    if len(items) == 1:
      return items[0]
    if len(items) == 2:
      # max(x, None) == x, so this works.
      return cls.bin_op(items[0], items[1], op=max, zero=None)
    return cls.max([items[0], cls.max(items[1:])])

  @staticmethod
  def __max_error():
    # Will replace self.max for each instance. To be sure that we don't confuse it with self.max_value.
    raise Exception("Use max_value instead.")

  def max_value(self):
    """
    Maximum of our values.
    """
    return max(self.values())

  def __repr__(self):
    if self.value is None and not self.dict:
      return "%s()" % self.__class__.__name__
    if self.value is None and self.dict:
      return "%s(%r)" % (self.__class__.__name__, self.dict)
    if not self.dict and self.value is not None:
      return "%s(%r)" % (self.__class__.__name__, self.value)
    return "%s(numbers_dict=%r, broadcast_value=%r)" % (
           self.__class__.__name__, self.dict, self.value)


def collect_class_init_kwargs(cls):
  kwargs = set()
  for cls_ in inspect.getmro(cls):
    if not inspect.ismethod(cls_.__init__):  # Python function. could be builtin func or so
      continue
    arg_spec = inspect.getargspec(cls_.__init__)
    kwargs.update(arg_spec.args[1:])  # first arg is self, ignore
  return kwargs


def custom_exec(source, source_filename, user_ns, user_global_ns):
  if not source.endswith("\n"):
    source += "\n"
  co = compile(source, source_filename, "exec")
  eval(co, user_ns, user_global_ns)
