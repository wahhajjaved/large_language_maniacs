#!/usr/bin/python
#
# Misc. utility functions for Mailpile.
#
import cgi
import hashlib
import locale
import re
import subprocess
import os
import sys
import tempfile
import threading
import time

global APPEND_FD_CACHE, APPEND_FD_CACHE_ORDER, APPEND_FD_CACHE_SIZE
global WORD_REGEXP, STOPLIST, BORING_HEADERS, DEFAULT_PORT, QUITTING

QUITTING = False

DEFAULT_PORT = 33411

WORD_REGEXP = re.compile('[^\s!@#$%^&*\(\)_+=\{\}\[\]:\"|;\'\\\<\>\?,\.\/\-]{2,}')

STOPLIST = set(['an', 'and', 'are', 'as', 'at', 'by', 'for', 'from',
                'has', 'http', 'in', 'is', 'it', 'mailto', 'og', 'or',
                're', 'so', 'the', 'to', 'was'])

BORING_HEADERS = ('received', 'date',
                  'content-type', 'content-disposition', 'mime-version',
                  'dkim-signature', 'domainkey-signature', 'received-spf')

 
class WorkerError(Exception):
  pass

class UsageError(Exception):
  pass

class AccessError(Exception):
  pass


def b64c(b): return b.replace('\n', '').replace('=', '').replace('/', '_')
def b64w(b): return b64c(b).replace('+', '-')

def escape_html(t):
  return t.replace('&', '&amp;').replace('>', '&gt;').replace('<', '&lt;')

def sha1b64(s):
  h = hashlib.sha1()
  if type(s) == type(unicode()):
    h.update(s.encode('utf-8'))
  else:
    h.update(s)
  return h.digest().encode('base64')

def sha512b64(s):
  h = hashlib.sha512()
  if type(s) == type(unicode()):
    h.update(s.encode('utf-8'))
  else:
    h.update(s)
  return h.digest().encode('base64')

def strhash(s, length, obfuscate=None):
  if obfuscate:
    s2 = b64c(sha512b64('%s%s' % (s, obfuscate))).lower()
  else:
    s2 = re.sub('[^0123456789abcdefghijklmnopqrstuvwxyz]+', '',
                s.lower())[:(length-4)]
    while len(s2) < length:
      s2 += b64c(sha1b64(s)).lower()
  return s2[:length]

def b36(number):
  alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
  base36 = ''
  while number:
    number, i = divmod(number, 36)
    base36 = alphabet[i] + base36
  return base36 or alphabet[0]

GPG_BEGIN_MESSAGE = '-----BEGIN PGP MESSAGE'
GPG_END_MESSAGE = '-----END PGP MESSAGE'
def decrypt_gpg(lines, fd):
  for line in fd:
    lines.append(line)
    if line.startswith(GPG_END_MESSAGE):
      break

  gpg = subprocess.Popen(['gpg', '--batch'],
                         stdin=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         stdout=subprocess.PIPE)
  lines = gpg.communicate(input=''.join(lines))[0].splitlines(True)
  if gpg.wait() != 0:
    raise AccessError("GPG was unable to decrypt the data.")

  return  lines

def decrypt_and_parse_lines(fd, parser):
  size = 0
  for line in fd:
    size += len(line)
    if line.startswith(GPG_BEGIN_MESSAGE):
       for line in decrypt_gpg([line], fd):
         parser(line.decode('utf-8'))
    else:
      parser(line.decode('utf-8'))
  return size

def gpg_open(filename, recipient, mode):
  fd = open(filename, mode)
  if recipient and ('a' in mode or 'w' in mode):
    gpg = subprocess.Popen(['gpg', '--batch', '-aer', recipient],
                           stdin=subprocess.PIPE,
                           stdout=fd)
    return gpg.stdin
  return fd


# Indexing messages is an append-heavy operation, and some files are
# appended to much more often than others.  This implements a simple
# LRU cache of file descriptors we are appending to.
APPEND_FD_CACHE = {}
APPEND_FD_CACHE_SIZE = 500
APPEND_FD_CACHE_ORDER = []
APPEND_FD_CACHE_LOCK = threading.Lock()
def flush_append_cache(ratio=1, count=None, lock=True):
  try:
    if lock: APPEND_FD_CACHE_LOCK.acquire()
    drop = count or int(ratio*len(APPEND_FD_CACHE_ORDER))
    for fn in APPEND_FD_CACHE_ORDER[:drop]:
      try:
        APPEND_FD_CACHE[fn].close()
        del APPEND_FD_CACHE[fn]
      except KeyError:
        pass
    APPEND_FD_CACHE_ORDER[:drop] = []
  finally:
    if lock: APPEND_FD_CACHE_LOCK.release()

def cached_open(filename, mode):
  try:
    APPEND_FD_CACHE_LOCK.acquire()
    if mode == 'a':
      fd = None
      if filename in APPEND_FD_CACHE:
        APPEND_FD_CACHE_ORDER.remove(filename)
        fd = APPEND_FD_CACHE[filename]
      if not fd or fd.closed:
        if len(APPEND_FD_CACHE) > APPEND_FD_CACHE_SIZE:
          flush_append_cache(count=1, lock=False)
        try:
          fd = APPEND_FD_CACHE[filename] = open(filename, 'a')
        except (IOError, OSError):
          # Too many open files?  Close a bunch and try again.
          flush_append_cache(ratio=0.3, lock=False)
          fd = APPEND_FD_CACHE[filename] = open(filename, 'a')
      APPEND_FD_CACHE_ORDER.append(filename)
      return fd
    else:
      if filename in APPEND_FD_CACHE:
        fd = APPEND_FD_CACHE[filename]
        try:
          if 'w' in mode or '+' in mode:
            del APPEND_FD_CACHE[filename]
            APPEND_FD_CACHE_ORDER.remove(filename)
            fd.close()
          else:
            fd.flush()
        except (ValueError, IOError):
          pass
      return open(filename, mode)
  finally:
    APPEND_FD_CACHE_LOCK.release()


import StringIO
try:
  import Image
except:
  Image = None

def thumbnail(fileobj, filename=None, height=None, width=None):
  """
  Generates thumbnail image from supplied fileobj, which should be a file, StringIO, or string,
  containing a PIL-supported image.
  FIXME: Failure modes unmanaged.
  """
  if Image == None:
    # If we don't have PIL, we just return the supplied filename in the hopes
    # that somebody had the good sense to extract the right attachment to that
    # filename...
    return filename

  if not isinstance(fileobj, StringIO.StringIO) and not isinstance(fileobj, file):
    fileobj = StringIO.StringIO(fileobj)

  image = Image.open(fileobj)

  # defining the size
  if height == None and width == None:
    raise Exception("Must supply width or height!")
  if height and not width:
    x = height
    y = int((float(height)/image.size[0]) * image.size[1])
  elif width and not height:
    y = width
    x = int((float(width)/image.size[1]) * image.size[0])
  else:
    y = width
    x = height

  size = "%dx%d" % (y, x)

  # defining the filename and the miniature filename
  filehead, filetail = os.path.split(filename)
  basename, format = os.path.splitext(filetail)
  miniature = basename + '_' + size + format
  miniature_filename = os.path.join(filehead, miniature)
  
  if os.path.exists(filename) and os.path.exists(miniature_filename) and os.path.getmtime(filename)>os.path.getmtime(miniature_filename):
    os.unlink(miniature_filename)
  # if the image wasn't already resized, resize it ; note: checks against supplied filename. If the file has
  # not already been extracted, will always generate... this is possibly a bug!
  if not os.path.exists(miniature_filename):
    image.thumbnail([x, y], Image.ANTIALIAS)
    try:
      image.save(miniature_filename, image.format, quality=90, optimize=1)
    except:
      image.save(miniature_filename, image.format, quality=90)

  return miniature_filename
