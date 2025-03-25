from config import *
import hashlib
import sys

def getHash(file, block_count=0):
  """
  Returns a sha256 hash for the specified file.
  Eventually sent to server to check for restarts.
  """
  hash = hashlib.sha256()
  i = 0
  with open(file, "r") as file:
    while True:
      data = file.read(CHUNK_SIZE)
      if not data or (block_count != 0 and i <= block_count):
        file.close()
        return hash.hexdigest()
      i += 1
      hash.update(data)

def fail(msg):
  """
  Simple fail function that prints and logs the error message and then exits.
  """
  logger.error(msg)
  sys.stderr.write(msg)
  sys.exit(1)