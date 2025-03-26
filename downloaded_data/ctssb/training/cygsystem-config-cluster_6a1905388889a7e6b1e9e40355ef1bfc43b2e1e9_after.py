import os

import gettext
_ = gettext.gettext

import gtk
import gtk.glade
import MessageLibrary
import ModelBuilder
import binascii
from ValidationError import ValidationError
from IPAddrEntry import IP

CRC32_MASK = 0xFFFF

INSTALLDIR="/usr/share/system-config-cluster"

NONE_PLACEHOLDER=_("None")

RESOURCE_PROVIDE_NAME=_("Please provide a name for this resource.")

FSID_PROVIDE_INT_VALUE=_("Please Provide an integer value only for File System ID")

FSID_PROVIDE_UNIQUE_VALUE=_("Please Provide a unique value for File System ID; Another File System resource is already using this ID")

RESOURCE_PROVIDE_UNIQUE_NAME=_("Please provide a unique name for this resource.")

INVALID_IP=_("Please Provide a Valid IP Address")

PROVIDE_UNIQUE_IP=_("This IP Address is already declared as a resource. Please choose another.")

#ADDING A NEW RESOURCE: RC form should be named the same as its tagname in
#the glade file. Then add tagname to this list.

RC_OPTS = {"ip":_("IP Address"),
           "script":_("Script"),
           "nfsclient":_("NFS Client"),
           "nfsexport":_("NFS Export"),
           "netfs":_("NFS Mount"),
           "clusterfs":_("GFS"),
           "smb":_("Samba Service"),
           "fs":_("File System") }

class ResourceHandler:
  def __init__(self, rc_proxy_widget, model_builder):
    self.rc_proxy_widget = rc_proxy_widget
    self.model_builder = model_builder
    gladepath = "resources.glade"
    if not os.path.exists(gladepath):
      gladepath = "%s/%s" % (INSTALLDIR,gladepath)

    self.rc_xml = gtk.glade.XML(gladepath, domain="NULL")
    
    #generate hash table for rc_type -->  rc form
    self.rc_hash = { }
    rc_opt_keys = RC_OPTS.keys()
    for rc in rc_opt_keys:
      self.rc_hash[rc] = self.rc_xml.get_widget("rc_" + rc)

    self.pretty_rcname_hash = RC_OPTS

    self.rc_container = self.rc_xml.get_widget('rc_container')
    children = self.rc_container.get_children()
    for child in children:
      child.reparent(self.rc_proxy_widget)

    self.rc_container2 = self.rc_xml.get_widget('rc_container2')
    children2 = self.rc_container2.get_children()
    for child in children2:
      child.reparent(self.rc_proxy_widget)

    self.rc_populate_hash = {"ip":self.pop_ip,
                             "script":self.pop_script,
                             "nfsclient":self.pop_nfsclient,
                             "nfsexport":self.pop_nfsexport,
                             "netfs":self.pop_netfs,
                             "clusterfs":self.pop_clusterfs,
                             "smb":self.pop_smb,
                             "fs":self.pop_fs }

    self.rc_validate_hash = {"ip":self.val_ip,
                             "script":self.val_script,
                             "nfsclient":self.val_nfsclient,
                             "nfsexport":self.val_nfsexport,
                             "netfs":self.val_netfs,
                             "clusterfs":self.val_clusterfs,
                             "smb":self.val_smb,
                             "fs":self.val_fs }

    self.process_widgets()

  def get_pretty_rcname_hash(self):
    return self.pretty_rcname_hash

  def get_rc_hash(self):
    return self.rc_hash

  def populate_rc_form(self, tagname, *attrs):
    apply(self.rc_populate_hash[tagname], attrs)

  def pop_ip(self, attrs):
    addr = attrs["address"]
    self.ip.setAddrFromString(addr)
    monitor = attrs["monitor_link"]
    if (monitor == None) or (monitor == False) or (monitor == "no") or (monitor == "0"):
      self.monitor_link.set_active(False)
    else:
      self.monitor_link.set_active(True)

  def pop_script(self, attrs):
    self.script_name.set_text(attrs["name"])
    self.script_filepath.set_text(attrs["file"])

  def pop_nfsclient(self, attrs):
    self.nfsc_name.set_text(attrs["name"])
    self.nfsc_target.set_text(attrs["target"])
    
    options = attrs['options'].strip().split(',')
    if 'ro' in options:
      self.nfsc_ro.set_active(True)
      self.nfsc_rw.set_active(False)
    else:
      self.nfsc_rw.set_active(True)
      self.nfsc_ro.set_active(False)
    if 'rw' in options:
      options.remove('rw')
    if 'ro' in options:
      options.remove('ro')
    
    option_string = ''
    if len(options) != 0:
      option_string = options[0]
      for opt in options[1:]:
        option_string += ',' + opt
    self.nfsc_options.set_text(option_string)
      
  def pop_nfsexport(self, attrs):
    self.nfse_name.set_text(attrs["name"])

  def pop_netfs(self, attrs):
    try:
      self.netfs_name.set_text(attrs["name"])
    except KeyError, e:
      self.netfs_name.set_text("")

    try:
      self.netfs_mnt.set_text(attrs["mountpoint"])
    except KeyError, e:
      self.netfs_mnt.set_text("")

    try:
      self.netfs_host.set_text(attrs["host"])
    except KeyError, e:
      self.netfs_host.set_text("")

    try:
      self.netfs_export.set_text(attrs["export"])
    except KeyError, e:
      self.netfs_export.set_text("")

    try:
      fstype = attrs["fstype"]
      if fstype == "nfs":
        self.netfs_fstype.set_active(True)
      else:
        self.netfs_fstype.set_active(False)
    except KeyError, e:
      self.netfs_fstype.set_active(True)

    try:
      force = attrs["force_unmount"]
      if force == "1" or force == "yes":
        self.netfs_force_unmount.set_active(True)
      else:
        self.netfs_force_unmount.set_active(False)
    except KeyError, e:
        self.netfs_force_unmount.set_active(False)
 
    try:
      self.netfs_options.set_text(attrs["options"])
    except KeyError, e:
      self.netfs_options.set_text("")


  def pop_clusterfs(self, attrs):
    nameval = True
    try:
      self.gfs_name.set_text(attrs["name"])
    except KeyError, e:
      self.gfs_name.set_text("")
      nameval = False

    try:
      self.gfs_mnt.set_text(attrs["mountpoint"])
    except KeyError, e:
      self.gfs_mnt.set_text("")

    try:
      self.gfs_device.set_text(attrs["device"])
    except KeyError, e:
      self.gfs_device.set_text("")
    
    try:
      self.gfs_id.set_text(attrs["fsid"])
    except KeyError, e:
      self.gfs_id.set_text("")
    
    try:
      force = attrs["force_unmount"]
      if force == "1" or force == "yes":
        self.gfs_force_unmount.set_active(True)
      else:
        self.gfs_force_unmount.set_active(False)
    except KeyError, e:
      self.gfs_force_unmount.set_active(False)
    
    try:
      self.gfs_options.set_text(attrs["options"])
    except KeyError, e:
      self.gfs_options.set_text("")

  def pop_smb(self, attrs):
    self.samba_name.set_text(attrs["name"])
    self.samba_workgroup.set_text(attrs["workgroup"])

  def pop_fs(self, attrs):
    self.fs_name.set_text(attrs["name"])
    self.fs_mnt.set_text(attrs["mountpoint"])
    self.fs_device.set_text(attrs["device"])
    
    type = attrs["fstype"] 
    model = self.fs_combo.get_model()
    iter = model.get_iter_first()
    while iter != None:
      if model.get_value(iter, 0) == type:
        self.fs_combo.set_active_iter(iter)
        break
      iter = model.iter_next(iter)
    
    try:
      force = attrs["force_unmount"]
      if force == "1" or force == "yes":
        self.fs_force_unmount.set_active(True)
      else:
        self.fs_force_unmount.set_active(False)
    except KeyError, e:
      self.fs_force_unmount.set_active(False)

    try:
      self.fs_id.set_text(attrs["fsid"])
    except KeyError, e:
      self.fs_id.set_text("")
    
    try:
      fence = attrs["self_fence"]
      if fence == "1" or fence == "yes":
        self.fs_self_fence.set_active(True)
      else:
        self.fs_self_fence.set_active(False)
    except KeyError, e:
      self.fs_self_fence.set_active(False)
    
    try:
      fsck = attrs["force_fsck"]
      if fsck == "1" or fsck == "yes":
        self.fs_force_fsck.set_active(True)
      else:
        self.fs_force_fsck.set_active(False)
    except KeyError, e:
      self.fs_force_fsck.set_active(False)
    
    try:
      self.fs_options.set_text(attrs["options"])
    except KeyError, e:
      self.fs_options.set_text("")
    
  
  def clear_rc_forms(self):

    self.ip.clear()
    self.monitor_link.set_active(True)

    self.script_name.set_text("")
    self.script_filepath.set_text("")

    self.nfse_name.set_text("")

    self.nfsc_name.set_text("")
    self.nfsc_target.set_text("")
    self.nfsc_options.set_text("")
    self.nfsc_rw.set_active(True)

    self.fs_name.set_text("")
    self.fs_mnt.set_text("")
    self.fs_device.set_text("")
    self.fs_combo.set_active_iter(self.fs_combo.get_model().get_iter_first())
    self.fs_force_unmount.set_active(False)
    self.fs_self_fence.set_active(False)
    self.fs_force_fsck.set_active(False)
    self.fs_options.set_text('')
    self.fs_id.set_text("")

    self.samba_name.set_text("")
    self.samba_workgroup.set_text("")
    
    self.netfs_name.set_text("")
    self.netfs_mnt.set_text("")
    self.netfs_host.set_text("")
    self.netfs_export.set_text("")
    self.netfs_options.set_text("")
    self.netfs_force_unmount.set_active(False)
    self.netfs_fstype.set_active(True)

    self.gfs_name.set_text("")
    self.gfs_mnt.set_text("")
    self.gfs_device.set_text("")
    self.gfs_force_unmount.set_active(False)
    self.gfs_options.set_text("")
    self.gfs_id.set_text("")


  #### Validation Methods
  def validate_resource(self, tagname, name=None):
    try:
      args = list()
      args.append(name)
      returnlist = apply(self.rc_validate_hash[tagname], args)
    except ValidationError, e:
      MessageLibrary.errorMessage(e.getMessage())
      return None

    return returnlist 

  def val_ip(self, *argname):
    if self.ip.isValid() != True:
      MessageLibrary.errorMessage(INVALID_IP)
      return None
    
    inaddr = argname[0]
    addr = self.ip.getAddrAsString()
    if inaddr == None: #New resource...
      res = self.check_unique_ip(addr)
      if res == False:  #adress already used
        raise ValidationError('FATAL',PROVIDE_UNIQUE_IP)
      
    else:
      if inaddr != addr:
        res = self.check_unique_ip(addr)
        if res == False:  #address already used
          raise ValidationError('FATAL',PROVIDE_UNIQUE_IP)

    monitor = self.monitor_link.get_active()
    fields = {}
    fields["address"]= addr
    if monitor:
      fields["monitor_link"] = "1"
    else:
      fields["monitor_link"] = "0"

    return fields

  def val_script(self, *argname):
    name = argname[0]
    script_name = self.script_name.get_text()
    if script_name == "":
      raise ValidationError('FATAL', RESOURCE_PROVIDE_NAME)

    #This same method is used for validating names for all resources.
    #This could be a brand new resource, or an edited one.
    #If new, its name must be checked for duplicates, and if
    #a duplicate is found, an exception must be raised
    #If the resource is a new one, then the argname arg will be None
    #
    #If this is an edited resource, it's orig name must be
    #checked against the new name (argname[0])

    if name == None: #New resource...
      res = self.check_unique_script_name(script_name)
      if res == False:  #name already used for a script
        raise ValidationError('FATAL',RESOURCE_PROVIDE_UNIQUE_NAME)
      
    else:
      if name != script_name:
        res = self.check_unique_script_name(script_name)
        if res == False:  #name already used for a script
          raise ValidationError('FATAL',RESOURCE_PROVIDE_UNIQUE_NAME)

    filepath = self.script_filepath.get_text()
    
    fields = {}
    
    fields["name"] = script_name
    fields["file"] = filepath

    return fields

  def val_nfsclient(self, *argname):
    name = argname[0]

    nfs_name = self.nfsc_name.get_text()
    if nfs_name == "":
      raise ValidationError('FATAL', RESOURCE_PROVIDE_NAME)

    if name == None: #New resource...
      res = self.check_unique_nfsclient_name(nfs_name)
      if res == False:  #name already used for a script
        raise ValidationError('FATAL',RESOURCE_PROVIDE_UNIQUE_NAME)
      
    else:
      if name != nfs_name:
        res = self.check_unique_nfsclient_name(nfs_name)
        if res == False:  #name already used for a script
          raise ValidationError('FATAL',RESOURCE_PROVIDE_UNIQUE_NAME)

    
    options_dir = {}
    for opt in self.nfsc_options.get_text().strip().split(','):
      opt = opt.strip()
      if opt == '':
        continue
      options_dir[opt] = ''
    
    use_radios = False
    if ('rw' in options_dir) and ('ro' in options_dir):
      options_dir.pop('ro')
      options_dir.pop('rw')
      use_radios = True
    if not(('rw' in options_dir) or ('ro' in options_dir)):
      use_radios = True
    if use_radios:
      if self.nfsc_rw.get_active():
        options_dir['rw'] = ''
      else:
        options_dir['ro'] = ''
    
    options_list = options_dir.keys()
    options_string = options_list[0]
    for opt in options_list[1:]:
      options_string += ',' + opt
    
    fields = {}
    fields["name"] = nfs_name
    fields["target"] = self.nfsc_target.get_text().strip()
    fields["options"] = options_string

    return fields

  def val_nfsexport(self, *argname):
    name = argname[0]

    nfse_name = self.nfse_name.get_text()
    if nfse_name == "":
      raise ValidationError('FATAL', RESOURCE_PROVIDE_NAME)

    if name == None: #New resource...
      res = self.check_unique_nfsexport_name(nfse_name)
      if res == False:  #name already used for a script
        raise ValidationError('FATAL',RESOURCE_PROVIDE_UNIQUE_NAME)
      
    else:
      if name != nfse_name:
        res = self.check_unique_nfsexport_name(nfse_name)
        if res == False:  #name already used for a script
          raise ValidationError('FATAL',RESOURCE_PROVIDE_UNIQUE_NAME)

    fields = {}
    fields["name"] = nfse_name

    return fields

  def val_smb(self, *argname):
    name = argname[0]
    samba_name = self.samba_name.get_text()
    if samba_name == "":
      raise ValidationError('FATAL', RESOURCE_PROVIDE_NAME)

    #Please see comments about name uniqueness in the val_script method

    if name == None: #New resource...
      res = self.check_unique_script_name(samba_name)
      if res == False:  #name already used for a samba resource
        raise ValidationError('FATAL',RESOURCE_PROVIDE_UNIQUE_NAME)
      
    else:
      if name != samba_name:
        res = self.check_unique_script_name(samba_name)
        if res == False:  #name already used for a samba
          raise ValidationError('FATAL',RESOURCE_PROVIDE_UNIQUE_NAME)

    workgroup = self.samba_workgroup.get_text()
    
    fields = {}
    
    fields["name"] = samba_name
    fields["workgroup"] = workgroup

    return fields

  def val_netfs(self, *argname):
    name = argname[0]
    netfs_name = self.netfs_name.get_text()
    if netfs_name == "":
      raise ValidationError('FATAL', RESOURCE_PROVIDE_NAME)

    if name == None: #New resource...
      res = self.check_unique_netfs_name(netfs_name)
      if res == False:  #name already used for a script
        raise ValidationError('FATAL',RESOURCE_PROVIDE_UNIQUE_NAME)
      
    else:
      if name != netfs_name:
        res = self.check_unique_netfs_name(netfs_name)
        if res == False:  #name already used for a script
          raise ValidationError('FATAL',RESOURCE_PROVIDE_UNIQUE_NAME)

    fields = {}
    fields["name"] = netfs_name
    mntp = self.netfs_mnt.get_text()
    fields["mountpoint"] = mntp
    host = self.netfs_host.get_text()
    fields["host"] = host
    export = self.netfs_export.get_text()
    fields["export"] = export 
    if self.netfs_fstype.get_active() == True:
      fstype = "nfs"
    else:
      fstype = "nfs4"
    fields["fstype"] = fstype
    options = self.netfs_options.get_text()
    fields["options"] = options
    unmount = self.netfs_force_unmount.get_active()
    if unmount == False:
      umount = "0"
    else:
      umount = "1"
    fields["force_unmount"] = umount

    return fields

  def val_clusterfs(self, *argname):
    name = argname[0]
    crc = None
    gfs_name = self.gfs_name.get_text()
    if gfs_name == "":
      raise ValidationError('FATAL', RESOURCE_PROVIDE_NAME)

    self.check_unique_fsid(16)

    if name == None: #New resource...
      res = self.check_unique_gfs_name(gfs_name)
      if res == False:  #name already used for a script
        raise ValidationError('FATAL',RESOURCE_PROVIDE_UNIQUE_NAME)

      #need to generate fs_id for new clusterfs's
      bits = binascii.crc32(gfs_name)
      crc = abs(bits & CRC32_MASK) #puts val in 16 bit space
      
    else:
      if name != gfs_name:
        res = self.check_unique_gfs_name(gfs_name)
        if res == False:  #name already used for a script
          raise ValidationError('FATAL',RESOURCE_PROVIDE_UNIQUE_NAME)
        

    fields = {}
    fields["name"] = gfs_name
    mntp = self.gfs_mnt.get_text()
    fields["mountpoint"] = mntp
    device = self.gfs_device.get_text()
    fields["device"] = device
    options = self.gfs_options.get_text()
    fields["options"] = options
    if self.gfs_force_unmount.get_active():
      force = '1'
    else:
      force = '0'
    fields['force_unmount'] = force

    if crc != None: #New resource
      gfs_id = self.gfs_id.get_text()
      if gfs_id != "": #If the user wants to set an initial value for fsid 
        if gfs_id.isdigit():
          if self.check_unique_fsid(gfs_id):
            fields['fsid'] = self.gfs_id.get_text()
          else:
            raise ValidationError('FATAL',FSID_PROVIDE_UNIQUE_VALUE)
        else:
          raise ValidationError('FATAL',FSID_PROVIDE_INT_VALUE)
      else: #This code searches fsid's and increments crc by 1 if found
        while self.check_unique_fsid(str(crc)) == False:
          crc = crc + 1
 
        fields['fsid'] = str(crc)

    else: #Not a new resource
      gfs_id = self.gfs_id.get_text()
      if gfs_id != "": #If the user wants to set an fsid 
        if gfs_id.isdigit():
          if self.check_unique_fsid(gfs_id):
            fields['fsid'] = self.gfs_id.get_text()
          else:
            raise ValidationError('FATAL',FSID_PROVIDE_UNIQUE_VALUE)
        else:
          raise ValidationError('FATAL',FSID_PROVIDE_INT_VALUE)
    
    return fields


  def val_fs(self, *argname):
    name = argname[0]
    crc = None
    fs_name = self.fs_name.get_text().strip()
    if fs_name == "":
      raise ValidationError('FATAL', RESOURCE_PROVIDE_NAME)

    if name == None: #New resource...
      res = self.check_unique_fs_name(fs_name)
      if res == False:  #name already used for a script
        raise ValidationError('FATAL',RESOURCE_PROVIDE_UNIQUE_NAME)
     
     #need to generate fs_id for new clusterfs's
      bits = binascii.crc32(fs_name)
      crc = abs(bits & CRC32_MASK) #puts val in 16 bit space
 
    else:
       if name != fs_name:
        res = self.check_unique_fs_name(fs_name)
        if res == False:  #name already used for a script
          raise ValidationError('FATAL',RESOURCE_PROVIDE_UNIQUE_NAME)

    fields = {}
    fields["name"] = fs_name
    
    mntp = self.fs_mnt.get_text()
    fields["mountpoint"] = mntp
    
    device = self.fs_device.get_text()
    fields["device"] = device
    
    iter = self.fs_combo.get_active_iter()
    fstype = self.fs_combo.get_model().get_value(iter, 0)
    fields["fstype"] = fstype
    
    if self.fs_force_unmount.get_active():
      force = '1'
    else:
      force = '0'
    fields['force_unmount'] = force
    
    if self.fs_self_fence.get_active():
      fence = '1'
    else:
      fence = '0'
    fields['self_fence'] = fence
    
    if self.fs_force_fsck.get_active():
      force_fsck = '1'
    else:
      force_fsck = '0'
    fields['force_fsck'] = force_fsck

    if crc != None: #New resource
      fs_id = self.fs_id.get_text()
      if fs_id != "": #If the user wants to set an initial value for fsid
        if fs_id.isdigit():
          if self.check_unique_fsid(fs_id):
            fields['fsid'] = self.fs_id.get_text()
          else:
            raise ValidationError('FATAL',FSID_PROVIDE_UNIQUE_VALUE)
        else:
            raise ValidationError('FATAL',FSID_PROVIDE_INT_VALUE)
      else: #This code searches fsid's and increments crc by 1 if found
        while self.check_unique_fsid(str(crc)) == False:
          crc = crc + 1

        fields['fsid'] = str(crc)

    else:
      fs_id = self.fs_id.get_text()
      if fs_id != "": #If the user wants to set an fsid
        if fs_id.isdigit():
          fields['fsid'] = self.fs_id.get_text()
        else:
          raise ValidationError('FATAL',FSID_PROVIDE_INT_VALUE)
    
    options = self.fs_options.get_text().strip()
    fields['options'] = options
    
    return fields

  def process_widgets(self):
    #self.fileselector = self.rc_xml.get_widget('fileselection1')

    self.ip = IP()
    self.ip.show_all()
    self.rc_xml.get_widget('ip_proxy').add(self.ip)
    self.monitor_link = self.rc_xml.get_widget('checkbutton1')

    self.script_name = self.rc_xml.get_widget('entry5')
    self.script_filepath = self.rc_xml.get_widget('entry6')
    #self.script_browse_button = self.rc_xml.get_widget('button1')

    self.nfse_name = self.rc_xml.get_widget('entry7')

    self.samba_name = self.rc_xml.get_widget('entry24')
    self.samba_workgroup = self.rc_xml.get_widget('entry25')

    self.nfsc_name = self.rc_xml.get_widget('entry8')
    self.nfsc_target = self.rc_xml.get_widget('entry9')
    self.nfsc_options = self.rc_xml.get_widget('entry23')
    self.nfsc_rw = self.rc_xml.get_widget('radiobutton1')
    self.nfsc_ro = self.rc_xml.get_widget('radiobutton2')

    self.netfs_name = self.rc_xml.get_widget('entry16')
    self.netfs_mnt = self.rc_xml.get_widget('entry17')
    self.netfs_host = self.rc_xml.get_widget('entry18')
    self.netfs_export = self.rc_xml.get_widget('entry19')
    self.netfs_fstype = self.rc_xml.get_widget('nfs_button')
    self.netfs_force_unmount = self.rc_xml.get_widget('checkbutton2')
    self.netfs_options = self.rc_xml.get_widget('entry20')

    self.gfs_name = self.rc_xml.get_widget('gfs_name')
    self.gfs_mnt = self.rc_xml.get_widget('entry14')
    self.gfs_device = self.rc_xml.get_widget('entry15')
    self.gfs_options = self.rc_xml.get_widget('gfs_options')
    self.gfs_force_unmount = self.rc_xml.get_widget('gfs_force_unmount')
    self.gfs_id_container = self.rc_xml.get_widget('gfs_id_container')
    self.gfs_id = self.rc_xml.get_widget('gfs_id')
    
    self.fs_name = self.rc_xml.get_widget('entry11')
    self.fs_mnt = self.rc_xml.get_widget('entry12')
    self.fs_device = self.rc_xml.get_widget('fs_dev')
    self.fs_combo = self.rc_xml.get_widget('combobox1')
    self.fs_force_unmount = self.rc_xml.get_widget('fs_force_unmount')
    self.fs_self_fence = self.rc_xml.get_widget('fs_self_fence')
    self.fs_force_fsck = self.rc_xml.get_widget('fs_force_fsck')
    self.fs_options = self.rc_xml.get_widget('fs_options')
    self.fs_id_container = self.rc_xml.get_widget('fs_id_container')
    self.fs_id = self.rc_xml.get_widget('fs_id')
  
  def set_model(self, model_builder):
    self.model_builder = model_builder

  def check_unique_fs_name(self,fs_name):
    rcs = self.model_builder.getResources()
    for rc in rcs:
      if rc.getName() == fs_name:
        return False

    return True

  def check_unique_netfs_name(self,netfs_name):
    rcs = self.model_builder.getResources()
    for rc in rcs:
      if rc.getName() == netfs_name:
        return False

    return True

  def check_unique_gfs_name(self,gfs_name):
    rcs = self.model_builder.getResources()
    for rc in rcs:
      if rc.getName() == gfs_name:
        return False

    return True

  def check_unique_fsid(self, in_fsid):
    fs_objs = self.model_builder.searchObjectTree("fs")
    gfs_objs = self.model_builder.searchObjectTree("clusterfs")

    for obj in fs_objs:
        at = obj.getAttribute("fsid")
        if at == in_fsid:
          return False

    for obj in gfs_objs:
        at = obj.getAttribute("fsid")
        if at == in_fsid:
          return False

    return True


  def check_unique_script_name(self,name):
    rcs = self.model_builder.getResources()
    for rc in rcs:
      if rc.getName() == name:
        return False

    return True

  def check_unique_ip(self,addr):
    rcs = self.model_builder.getResources()
    for rc in rcs:
      if rc.getName() == addr:
        return False

    return True

  def check_unique_nfsexport_name(self,name):
    rcs = self.model_builder.getResources()
    for rc in rcs:
      if rc.getName() == name:
        return False

    return True

  def check_unique_nfsclient_name(self,name):
    rcs = self.model_builder.getResources()
    for rc in rcs:
      if rc.getName() == name:
        return False

    return True

