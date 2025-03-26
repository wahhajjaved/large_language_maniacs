
import sys, traceback
from config import *
from common_tools import *
from paramiko import SSHClient, SFTPClient
import socket

hostkeytype = None
hostkey = None

# suppress paramiko logging
logging.getLogger("paramiko").setLevel(logging.WARNING)

def handshake(username, hostname, nonce, file_dest, file_hash, file_size,
              file_src, port=22, password=None):
  """
  Goal of the handshake is to return an authed TCP connection. Expects
  executable for alias warp, for now will return (port, block_count) tuple.
  Executable must be in the default path. 
  """
  try:
    client = SSHClient()
    client.load_system_host_keys()
    client.connect(hostname, username=username, port=port)

    stderr_path = "/var/tmp/" + str(file_hash) + ".err"
    stdout_path = "/var/tmp/" + str(file_hash) + ".out"

    command = 'warp ' + str(nonce) + ' ' + \
     file_dest + ' ' + str(file_hash) + ' ' + str(file_size) + ' 2> ' + \
      stderr_path + ' > ' + stdout_path
    stdin, stdout, stderr = client.exec_command(command)

    logger.debug("Command to server is: %s", command)

    sftp = SFTPClient.from_transport(client.get_transport())

    while not is_output(sftp, stdout_path, stderr_path): pass

    with sftp.open(stdout_path) as f:
      out = f.readlines()

    error_check(sftp, stderr_path)

    port = int(out[0].strip())
    block_count = int(out[1].strip())
    partial_hash = out[2]

    if block_count > 0:
      verify_partial_hash(file_src, partial_hash, block_count)

    logger.info("port: %s, block count: %s", port, block_count)
    logger.info("Connecting to: %s on port: %s", hostname, port)

    sock = connect_to_server(hostname, port)

    sock.sendall(nonce)
    error_check(sftp, stderr_path)

    return sock, block_count

  except Exception as e:
    # Boiler plate code from paramiko to handle excepntions for ssh connection
    # Eventually we should log this and have a user friendly message.
    logging.error('*** Caught exception: %s: %s', e.__class__, e)
    traceback.print_exc()
    try:
      t.close()
    except:
      pass
    sys.exit(1)

def is_output(sftp, stdout_path, stderr_path):
  with sftp.open(stdout_path) as f:
      out = f.read()

  with sftp.open(stdout_path) as f:
      err = f.read()

  if err == "" and out == "":
    return False
  else:
    return True

def verify_partial_hash(file_src, partial_hash, block_count):
  """
  Takes a file source and hashes the file up to block count and then compares 
  it with the partial hash passed in, fails if they do not match.
  """
  my_hash = getHash(file_src, block_count)
  if partial_hash != my_hash:
    msg = "Partial hash did not match server side. Please remove file from server before transferring.\n"
    fail(msg)


def error_check(sftp, stderr_path):
  """
  Checks the file that stderr is redirected to for errors. Prints them and exits
  if found.
  """
  with sftp.open(stderr_path) as f:
    err = f.read()
    if err == "":
      return
    else:
      fail(err)


def connect_to_server(host_name, port):
  """
  Connects to the provided host and port returning a socket object.
  """
  s = None

  for res in socket.getaddrinfo(host_name, port, socket.AF_UNSPEC, socket.SOCK_STREAM):
    af, socktype, proto, canonname, sa = res
    try:
      s = socket.socket(af, socktype, proto)
    except socket.error as msg:
      s = None
      continue
    try:
      s.connect(sa)
    except socket.error as msg:
      s.close()
      # No need to log error here, some errors are expected
      s = None
      continue
    break

  if s is None:
    fail('Could not connect to' + host_name)

  return s