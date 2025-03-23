import re

from os.path            import join, isfile, exists
from StringIO           import StringIO
from urlgrabber.grabber import URLGrabError
from urlparse           import urlparse

from dims import filereader
from dims import listcompare
from dims import osutils
from dims import spider
from dims import xmltree

from dims.configlib import uElement

from event     import EVENT_TYPE_PROC, EVENT_TYPE_MDLR
from interface import EventInterface

API_VERSION = 4.0

EVENTS = [
  {
    'id': 'stores',
    'provides': ['anaconda-version', 'input-store-lists', 'input-store-changed'],
    'properties': EVENT_TYPE_PROC|EVENT_TYPE_MDLR,
    'interface': 'StoresInterface',
  },
]

HOOK_MAPPING = {
  'StoresHook': 'stores',
  'ValidateHook': 'validate',
}

class StoresInterface(EventInterface):
  def __init__(self, base):
    EventInterface.__init__(self, base)
  
  def add_store(self, xml):
    parent = uElement('additional', self.config.get('//stores'))
    element = xmltree.read(StringIO(xml))
    parent.append(element)
    s,n,d,_,_,_ = urlparse(element.get('path/text()'))
    server = '://'.join((s,n))
    if server not in self._base.cachemanager.SOURCES:
      self._base.cachemanager.SOURCES.append(server)


#------ HOOKS ------#
class ValidateHook:
  def __init__(self, interface):
    self.VERSION = 0
    self.ID = 'stores.validate'
    self.interface = interface

  def run(self):
    self.interface.validate('//stores', schemafile='stores.rng')
    
class StoresHook:
  def __init__(self, interface):
    self.VERSION = 0
    self.ID = 'stores.stores'
    
    self.interface = interface
  
  def force(self):
    for file in osutils.find(self.interface.METADATA_DIR, name='*.pkgs', maxdepth=1):
      osutils.rm(file, force=True)
  
  def run(self):
    """Check input stores to see if their contents have changed by comparing them
    to the corresponding <store>.pkgs file in interface.METADATA_DIR"""
   
    self.interface.log(0, "generating filelists for input stores")
    changed = False
    
    storelists = {}
    
    for store in self.interface.config.xpath('//stores/*/store/@id'):
      self.interface.log(1, store)
      i,s,n,d,u,p = self.interface.getStoreInfo(store)
      
      base = self.interface.storeInfoJoin(s or 'file', n, d)
      
      # get the list of .rpms in the input store
      try:
        pkgs = spider.find(base, glob='*.[Rr][Pp][Mm]', nglob='repodata', prefix=False,
                           username=u, password=p)
      except URLGrabError, e:
        print e
        raise StoreNotFoundError, "The specified store '%s' at url '%s' does not appear to exist" % (store, base)
      
      oldpkgsfile = join(self.interface.METADATA_DIR, '%s.pkgs' % store)
      if isfile(oldpkgsfile):
        oldpkgs = filereader.read(oldpkgsfile)
      else:
        oldpkgs = []
      
      # test if content of input store changed
      old,new,_ = listcompare.compare(oldpkgs, pkgs)
      
      # save input store content list to storelists
      storelists[store] = pkgs
      
      # if content changed, write new contents to file
      if len(old) > 0 or len(new) > 0 or not exists(oldpkgsfile):
        changed = True
        filereader.write(pkgs, oldpkgsfile)
      
    self.interface.cvars['input-store-changed'] = changed
    self.interface.cvars['input-store-lists'] = storelists
  
  def apply(self):
    if not self.interface.cvars['input-store-lists']:
      storelists = {}
      
      storefiles = osutils.find(self.interface.METADATA_DIR, name='*.pkgs', maxdepth=1)
      if len(storefiles) == 0:
        raise RuntimeError, "Unable to find any store files in metadata directory"
      for file in storefiles:
        storeid = osutils.basename(file.replace('.pkgs', '')) # potential problem if store has .pkgs in name
        storelists[storeid] = filereader.read(file)
            
      self.interface.cvars['input-store-lists'] = storelists
      # if we're skipping stores, assume store lists didn't change; otherwise,
      # assume they did
      if self.interface.isSkipped('stores'):
        self.interface.cvars['input-store-changed'] = False
    
    if not self.interface.cvars['anaconda-version']:
      anaconda_version = \
        get_anaconda_version(join(self.interface.METADATA_DIR,
                                  '%s.pkgs' % self.interface.getBaseStore()))
      self.interface.cvars['anaconda-version'] = anaconda_version
    

#------ HELPER FUNCTIONS ------#
def get_anaconda_version(file):
  scan = re.compile('.*/anaconda-([\d\.]+-[\d\.]+)\..*\.[Rr][Pp][Mm]')
  version = None
  
  fl = filereader.read(file)
  for rpm in fl:
    match = scan.match(rpm)
    if match:
      try:
        version = match.groups()[0]
      except (AttributeError, IndexError), e:
        pass
      break
  if version is not None:
    return version
  else:
    raise ValueError, "unable to compute anaconda version from distro metadata"

#------ ERRORS ------#
class StoreNotFoundError(StandardError): pass
