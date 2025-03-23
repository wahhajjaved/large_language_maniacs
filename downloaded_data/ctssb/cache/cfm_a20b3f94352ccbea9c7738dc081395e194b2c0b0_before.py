#!/usr/bin/env python
"""use cloudfile meta files as placeholders for cloud files"""

from optparse import OptionParser
from shutil import move
import os
from getpass import getuser
import time
import datetime
import hashlib
import ConfigParser
import cloudfiles
from cloudfiles.errors import NoSuchContainer, NoSuchObject
ACTION_ADD = 'add'
ACTION_GET_NEW = 'get_new'
ACTION_UPDATE = 'update'
ACTION_CLEAN = 'clean'
ACTION_DELETE = 'delete'
ACTION_STEAL = 'steal'
ACTION_GET_META_FILES = 'get_meta'

ACTIONS = (ACTION_ADD, ACTION_GET_NEW, ACTION_UPDATE, ACTION_CLEAN, ACTION_DELETE, ACTION_STEAL, ACTION_GET_META_FILES)

META_EXT = '.cfm' # cloud file meta | cruddy file management
HASH_LEN = 32 # len(hashlib.md5("yup").hexdigest())
PACK_TIME_FORMAT = "%Y%j%H%M" #year dayofyear hour minute

#cloudfile metadata keys
OWNER = "owner"
MODIFIED = "modified"
HASH = "hash"
COMMENT = "comment"

def Property(func):
  """ http://adam.gomaa.us/blog/the-python-property-builtin/ """
  return property(**func())

class File(object):
  """ a file that is located on the cloud and has a meta file locally """

  def __init__(self, path_to_file):
    self._deleted_meta_file = False
    self._file_name = os.path.basename(path_to_file) # basename?
    self._path_to_file = path_to_file
    self._meta_file = "%s%s" % (path_to_file, META_EXT)
    if os.path.exists(self._meta_file):
      self._unpack()
    elif os.path.exists(self._path_to_file):
      self._local_modified = time.strftime(PACK_TIME_FORMAT, time.gmtime(os.stat(self._path_to_file).st_mtime))
      lf = open(self._path_to_file, 'r')
      self.local_hash = hashlib.md5(lf.read()).hexdigest()
      lf.close()
    else: # creating a new meta file.
      self._local_modified = 'unknown'
      self.local_hash = 'unknown'
  
  def __del__(self):
    self._pack()
    #super(File, self).__del__(self)

  def _pack(self):
    "write the File attributes to the local meta file"
    if not self._deleted_meta_file:
      f = open(self._meta_file, 'w')
      f.write(self.local_hash)
      f.write("\n")
      f.write(self._local_modified)
      f.write("\n")
      f.write(self.local_owner)
      f.write("\n")
      f.write(self.container_name)
      f.write("\n")
      f.close()
  def _unpack(self):
    "read the File attributes from the local meta file"
    f = open(self._meta_file, 'r')
    lines = [l.strip() for l in f.readlines()]
    f.close()
    if len(lines) == 4:
      self.local_hash, self._local_modified, self._local_owner_name, self._container_name = lines
    else:
      #TODO: raise proper error
      print "corrupt meta file"

    if os.path.exists(self._path_to_file):
      lf = open(self._path_to_file, 'r')
      self.local_hash = hashlib.md5(lf.read()).hexdigest() # use binascii.hexlify(self.local_hash) to compare with remote
      lf.close()

  @Property
  def local_modified():
    doc = "local modified time as formatted date time"
    def fget(self):
      return time.asctime(time.strptime(self._local_modified, PACK_TIME_FORMAT))
    def fset(self, t):
      #TODO: check for proper format
      self._local_modified = t
    return locals()

  @Property
  def container_name():
    doc = "container name in the local meta file"
    def fget(self):
      return self._container_name
    def fset(self, container_name):
      #TODO: raise error if container_name is too big
      self._container_name = container_name
    return locals()

  @Property
  def local_owner():
    doc = "local owner name"
    def fget(self):
      return self._local_owner_name
    def fset(self, owner_name):
      self._local_owner_name = owner_name
    return locals()

  @Property
  def cloudfile():
    doc = "rackspace cloud object"
    def fget(self):
      return self._cloudfile
    def fset(self, c):
      self._cloudfile = c
    return locals()

  @Property
  def remote_modified():
    doc = "remote modified date"
    def fget(self):
      return time.asctime(time.strptime(self._cloudfile.metadata["modified"], PACK_TIME_FORMAT))
    return locals()

  @Property
  def remote_owner():
    doc = "remote owner name"
    def fget(self):
      return self._cloudfile.metadata["owner"]
    def fset(self, owner_name):
      self._cloudfile.metadata["owner"] = owner_name
    return locals()
  
  @Property
  def remote_hash():
    doc = "remote hash of file"
    def fget(self):
      return self._cloudfile.metadata["hash"]
    return locals()

  @Property
  def uri():
    doc = "location of file if container is public"
    def fget(self):
      if self._cloudfile.container.is_public():
        return "%s/%s" % (self._cloudfile.container.public_uri(), self._file_name)
      return False
    return locals()

  def create_meta_file(self, container_name, owner):
    """ create a new meta file """
    self.container_name = container_name
    self.local_owner = owner
    self._local_modified = time.strftime(PACK_TIME_FORMAT, time.gmtime(os.stat(self._path_to_file).st_mtime))
    lf = open(self._path_to_file, 'r')
    self.local_hash = hashlib.md5(lf.read()).hexdigest() # use binascii.hexlify(self.local_hash) to compare with remote
    lf.close()

  def set_remote_meta(self):
    """ send meta data to the cloud file object """
    self._cloudfile.sync_metadata()
  
  def delete_meta(self):
    """ delete meta file """
    os.remove(self._meta_file)
    self._deleted_meta_file = True # prevents writing of meta file on close

  def upload_to_cloud(self):
    """ add the file to the cloud """
    f = open(self._path_to_file)
    self._cloudfile.write(f)
    m = self._local_modified
    self._cloudfile.metadata["modified"] = m
    h = self.local_hash
    self._cloudfile.metadata["hash"] = h
    #TODO: use a callback to track progress of upload

  def download_from_cloud(self, file_path=None):
    if not file_path:
      file_path = self._path_to_file
    print "downloading: %s" % file_path
    self._cloudfile.save_to_filename(file_path)

class Controller(object):
  """ a Controller that handles the actions """
  def __init__(self, owner_name, connection):
    self.owner_name = owner_name
    self.connection = connection
  
  @Property
  def files():
    doc = "files to operate on. includes paths"
    def fget(self):
      return self._files
    def fset(self, files):
      self._files = []
      self._meta_files = []
      for f in files:
        n, ext = os.path.splitext(f)
        if ext == META_EXT and f not in self._meta_files:
          self._meta_files.append(f)
        elif ext != META_EXT:
          self._files.append(f)
          if "%s%s" % (f, META_EXT) not in self._meta_files:
            self._meta_files.append("%s%s" % (f, META_EXT))
          
    return locals()

  def add_files(self, container_name):
    """ add all the files in file_list and create a meta file for each. """
    cloudcontainer = self.connection.create_container(container_name)
    for file_path in self._files:
      filename = os.path.basename(file_path)
      cloudfile = cloudcontainer.create_object(filename)
      f = File(file_path)
      f.cloudfile = cloudfile
      f.create_meta_file(container_name, self.owner_name)
      f.remote_owner = self.owner_name
      f.upload_to_cloud()
      f.set_remote_meta() # syncs meta data to the cloud
  def get_new(self):
    """ compare the hashes and download new if different or not existant. """
    for meta_file_path in self._meta_files:
      file_path = meta_file_path[:len(meta_file_path) - len(META_EXT)]
      filename = os.path.basename(file_path)
      f = File(file_path)
      try:
        cloudcontainer = self.connection.get_container(f.container_name)
        cloudfile = cloudcontainer.get_object(filename) #if not in cloud then mark it as deleted and remove the meta file
        f.cloudfile = cloudfile
        if ((f.local_hash != f.remote_hash) or not os.path.exists(file_path)):
          f.download_from_cloud()
        f.local_owner = f.remote_owner
        # local_modified too?
        if f.uri:
          print f.uri
      except NoSuchContainer:
        print "Container: [%s] doesn't exist on cloud" % f.container_name
      except NoSuchObject:
        print "file: [%s] no longer exists on the cloud" % file_path
        f.delete_meta()
        print meta_file_path
        if os.path.exists(file_path):
          new_path = os.path.join(os.path.dirname(file_path), "deleted.%s" % filename)
          move(file_path, new_path)


  def update(self):
    """ Update any that are different. Any that are different and have a different owner; get a copy of the one on server and add "owner_name." in front of it. Any that no longer exist in the cloud rename the file with "deleted." in front of it. """
    for meta_file_path in self._meta_files:
      file_path = meta_file_path[:len(meta_file_path) - len(META_EXT)]
      filename = os.path.basename(file_path)
      f = File(file_path)
      try:
        cloudcontainer = self.connection.get_container(f.container_name)
        cloudfile = cloudcontainer.get_object(filename) #if not in cloud then mark it as deleted and remove the meta file
        f.cloudfile = cloudfile
        if (f.local_owner != f.remote_owner):
          remote_owner_path = os.path.join(os.path.dirname(file_path), "%s.%s" % (f.remote_owner, filename))
          print "file: %s has a different owner on cloud then local owner. downloading file as: %s" % (file_path, remote_owner_path)
          f.download_from_cloud(file_path=remote_owner_path)
        elif (f.local_hash != f.remote_hash) and os.path.exists(file_path):
          f.upload_to_cloud()
          f.set_remote_meta() # syncs meta data to the cloud
          print "updating cloud file: %s" % file_path

      except NoSuchContainer:
        print "Container: [%s] doesn't exist on cloud" % f.container_name
      except NoSuchObject:
        print "file: [%s] no longer exists on the cloud"
        f.delete_meta()
        if os.path.exists(file_path):
          new_path = os.path.join(os.path.dirname(file_path), "deleted.%s" % filename)
          move(file_path, new_path)

  def clean(self):
    """ delete files just from local directory and leave the meta file untouched """
    for file_path in self._files:
      filename = os.path.basename(file_path)
      if "%s%s" % (file_path, META_EXT) in self._meta_files:
        f = File(file_path)
        try:
          cloudcontainer = self.connection.get_container(f.container_name)
          cloudfile = cloudcontainer.get_object(filename)
          f.cloudfile = cloudfile
          if (f.local_owner != f.remote_owner):
            print "owners don't match; cannot clean file: %s " % file_path
          elif (f.local_hash != f.remote_hash):
            print "hash of files don't match; cannot clean file: %s " % file_path
          else:
            os.remove(file_path)

        except NoSuchContainer:
          print "Container: [%s] doesn't exist on cloud" % f.container_name
        except NoSuchObject:
          print "file: [%s] no longer exists on the cloud" % file_path
          if os.path.exists(file_path):
            new_path = os.path.join(os.path.dirname(file_path), "deleted.%s" % filename)
            move(file_path, new_path)
  def delete(self):
    """ Remove files from cloud """
    for meta_file_path in self._meta_files:
      file_path = meta_file_path[:len(meta_file_path) - len(META_EXT)]
      filename = os.path.basename(file_path)
      f = File(file_path)
      try:
        cloudcontainer = self.connection.get_container(f.container_name)
        cloudfile = cloudcontainer.get_object(filename)
        f.cloudfile = cloudfile
        if (f.local_owner == f.remote_owner):
          cloudcontainer.delete_object(filename)
          f.delete_meta()
        if not cloudcontainer.list_objects():
          print "Deleting empty container: %s" % f.container_name
          self.connection.delete_container(f.container_name)
      except NoSuchContainer:
        print "Container: [%s] doesn't exist on cloud" % f.container_name
      except NoSuchObject:
        print "file: [%s] has already been removed from the cloud" % file_path
        f.delete_meta()
  def steal(self):
    """ set owner name for any files that have a different owner (use 'update' afterwards to update the files) """
    for meta_file_path in self._meta_files:
      file_path = meta_file_path[:len(meta_file_path) - len(META_EXT)]
      filename = os.path.basename(file_path)
      f = File(file_path)
      try:
        cloudcontainer = self.connection.get_container(f.container_name)
        cloudfile = cloudcontainer.get_object(filename)
        f.cloudfile = cloudfile
        if (f.local_owner != self.owner_name):
          f.local_owner = self.owner_name
          f.remote_owner = self.owner_name
          f.set_remote_meta()
          print "stealing: %s" % file_path
      except NoSuchContainer:
        print "Container: [%s] doesn't exist on cloud" % f.container_name
      except NoSuchObject:
        print "file: [%s] no longer exists on the cloud" % file_path

  def get_meta_files(self, container, dir):
    """ create all the meta files for the container and place them in the directory specified in files """
    try:
      cloudcontainer = self.connection.get_container(container)
      if os.path.isdir(dir):
        for filename in cloudcontainer.list_objects():
          f = File(os.path.join(dir, filename))
          cloudfile = cloudcontainer.get_object(filename)
          f.cloudfile = cloudfile
          f.local_owner = f.remote_owner
          f.local_hash = f.remote_hash
          f.local_modified = f.cloudfile.metadata["modified"]
          f.container_name = container
          f.set_remote_meta()
    except NoSuchContainer:
      print "Container: [%s] doesn't exist on cloud" % container
    except NoSuchObject:
      print "file: [%s] no longer exists on the cloud" % filename
  
  def make_container_public(self, container, ttl=604800):
    """ make the container specified to be accessible from the public """
    try:
      cloudcontainer = self.connection.get_container(container)
      cloudcontainer.make_public(ttl=ttl)
    except NoSuchContainer:
      print "Container: [%s] doesn't exist on cloud" % container

  def make_container_private(self, container):
    """ make a container be private and no longer accessible from the public """
    try:
      cloudcontainer = self.connection.get_container(container)
      cloudcontainer.make_private()
    except NoSuchContainer:
      print "Container: [%s] doesn't exist on cloud" % container
  

if __name__ == "__main__":
  parser = OptionParser(usage="%%prog --action [%s] [options] [files and or directories]" % "|".join(ACTIONS), version="%prog 0.1", description="add files to the cloud")

  parser.add_option("--action", "-a",
      action="store",
      type="choice",
      choices=ACTIONS,
      help="Specify what action to do with the files/directories listed. choices: %s" % ", ".join(ACTIONS))
  parser.add_option("--config",
      action="store",
      type="string",
      default="/home/%s/cloudfile.cfg" % getuser(), # better way of doing this?
      help="specify a cloud connection config file.")
  parser.add_option("--recursive", "-R",
      action="store_true",
      help="For any directories listed in args find all the files")
  parser.add_option("--container", "-c",
      action="store",
      type="string",
      help="Set the name of the container to work in")
  parser.add_option("--public",
      action="store_true",
      help="make the container public and publish to the CDN")
  parser.add_option("--ttl",
      action="store",
      type="int",
      help="Time in seconds when the public container should refresh it's cache")
  parser.add_option("--private",
      action="store_true",
      help="make the container private. This is the default.")

  (options, args) = parser.parse_args()

  if not args and not (options.public or options.private):
    parser.error("No files or directories specified.")

  if not options.action and not (options.public or options.private):
    parser.error("Must specify an action")
  elif not (options.public or options.private) and options.action == ACTION_ADD and not options.container:
    parser.error("Must set a container name")
  elif (options.public or options.private or options.action == ACTION_GET_META_FILES) and not options.container:
    parser.error("Must specify a container name")
  elif options.ttl and not options.public:
    parser.error("Must set option --public as well")


  def get_files(items, max_level=0):
    " walk through dir and retrieve all files "
    files = []
    for item in items:
      if os.path.isdir(item):
        for root, dir, file_names in os.walk(item, topdown=True):
          level = len(root.split('/'))
          if not max_level or max_level >= level:
            for f in file_names:
              files.append(os.path.join(root, f))
      else:
        files.append(item)
    return files

  max_level = 0
  if not options.recursive:
    max_level = 1
  files = get_files(args, max_level)
  config = ConfigParser.SafeConfigParser()
  config.read(options.config)
  conn = cloudfiles.get_connection(config.get('server', 'login_name'), config.get('server', 'api_key'), servicenet=config.getboolean('server', 'servicenet'))
  #TODO: set up a seperate authorization server proxy thingy so it can handle multiple users more securely and won't need to share the api key.
  #TODO: handle errors for the config.
  c = Controller(config.get('local', 'owner_name'), conn)
  c.files = files
  if options.action == ACTION_ADD:
    c.add_files(options.container)
  elif options.action == ACTION_GET_NEW:
    c.get_new()
  elif options.action == ACTION_UPDATE:
    c.update()
  elif options.action == ACTION_CLEAN:
    c.clean()
  elif options.action == ACTION_DELETE:
    c.delete()
  elif options.action == ACTION_STEAL:
    c.steal()
  elif options.action == ACTION_GET_META_FILES:
    c.get_meta_files(options.container, args[0])
  else:
    print "unknown action: %s" % options.action

  if options.public and not options.private:
    if options.ttl:
      c.make_container_public(options.container, ttl=options.ttl)
    else:
      c.make_container_public(options.container)
  elif options.private:
    c.make_container_private(options.container)
  #TODO: do operation using the controller

