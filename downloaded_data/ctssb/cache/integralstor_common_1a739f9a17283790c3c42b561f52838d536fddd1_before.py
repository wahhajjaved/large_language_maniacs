
import re, types, os, stat
import pprint

from integralstor_common import command, disks, ramdisk

def get_single_line_value(lines, property_name):
  """Given a property in the form of 'property_name: property_value' return the value of the property"""

  retval = None
  try:
    if not lines:
      raise Exception("No lines provided!")
    if '%s:'%property_name not in lines[0]:
      raise Exception("%s not found in the line provided!"%property_name)
    parts = lines[0].split()
    if not parts or len(parts) < 2:
      raise Exception("%s not found in the line provided!"%property_name)
    retval = parts[1]
  except Exception, e:
    return None, 'Error getting the single line value : %s'%str(e)
  else:
    return retval, None


def get_multi_line_value(lines, property_name):
  """Given a property in the form of 'property_name: property_value' followed by more lines in the list it returns the value of the property in the form of a string consisting of all following lines in the list """

  retval = None
  try:
    #if property_name == 'status':
    #  print lines
    if not lines or '%s:'%property_name not in lines[0]:
      raise Exception("%s not found in the line provided!"%property_name)
    str = ""
    for line in lines:
      res = re.match('^%s:\s*([\s\S]+)'%property_name, line.strip())
      if res:
        str += res.groups()[0]
      else:
        str += line.strip()
      str += ' '
    retval = str
  except Exception, e:
    return None, 'Error getting the multi line value : %s'%str(e)
  else:
    return retval, None


def get_config_line_details(line):
  """ Given a pool component configuration line, return a dict with each of its components"""

  d = None
  try:
    parts = line.split()
    if not parts:
      return None
    d = {}
    d['name'] = parts[0]
    if 'raidz1' in d['name']:
      d['type'] = 'raidz1'
    elif 'logs' in d['name']:
      d['type'] = 'logs'
    elif 'cache' in d['name']:
      d['type'] = 'cache'
    elif 'raidz2' in d['name']:
      d['type'] = 'raidz2'
    elif 'mirror' in d['name']:
      d['type'] = 'mirror'
    elif 'ramdisk' in d['name'].lower():
      d['type'] = 'RAMDisk'
      rds, err = ramdisk.get_ramdisks_config()
      if rds:
        for rd in rds:
          if rd['path'].lower() in d['name'].lower():
            d['ramdisk_size'] = rd['size']
            break
    else:
      d['type'] = 'device'

    if d['type'] not in ['cache', 'logs']:
      status_d = {}
      status_d['state'] = parts[1]
      status_d['read'] = int(parts[2])
      status_d['write'] = int(parts[3])
      status_d['chksum'] = int(parts[4])
      d['status'] = status_d
  except Exception, e:
    return None, 'Error getting config line details : %s'%str(e)
  else:
    return d, None

def process_config_section(lines):
  """Given a list of lines for a config section, return a dict of each of its components along with their children consitituents and the root of the tree"""
  root_node = None
  root_name = None
  try:
    stack = []
    if not lines:
      return None
    prev_node = None
    curr_spaces = -1
    d = None

    for line in lines:
      if d:
        prev_node = d
      d, err = get_config_line_details(line)
      if not d:
        errstr = "Error getting config line details for line : %s."%line
        if err:
          errstr += "Error : %s"%err
        raise Exception(errstr)
      prev_spaces = curr_spaces
      curr_spaces = len(line.rstrip()) - len(line.rstrip().lstrip())
      if curr_spaces > prev_spaces:
        if prev_node:
          stack.append(prev_node)
      elif curr_spaces < prev_spaces:
        stack.pop()
      if stack:
        parent = stack[len(stack)-1]
        d['parent'] = parent['name']
        if "children" not in parent:
          parent['children'] = []
        #parent['children'].append(d['name'])
        parent['children'].append(d)
      else:
        d['parent'] = None
        root_name = d['name']
        root_node = d
        #nodes[d['name']] = d

    if root_node['name'] not in ['cache', 'logs']:
      root_node['type'] = 'pool'

    #pp = pprint.PrettyPrinter(indent=4)
    #pp.pprint( nodes)
  except Exception, e:
    return None, None, 'Error processing the configuration section : %s'%str(e)
  else:
    return root_node, root_name, None


def process_pool_config(lines):
  """Process the complete config section of the zpool status command and return a dict for each of pool, cache and logs sections"""
  return_dict = {}
  try:
    if not lines:
      raise Exception("No lines passed!")
    if 'config:' not in lines[0]:
      raise Exception("No config section found!")
    start_processing = False
    base_space_count = -1
    component_lines = []
    processing = None
    d = {}
    for line in lines:
      res = re.match('^NAME[\s]*STATE[\s]*READ[\s]*WRITE[\s]*CKSUM', line.strip())
      if res:
        start_processing = True
        base_space_count = len(line.rstrip()) - len(line.rstrip().lstrip())
        #print base_space_count
        continue
      elif not start_processing:
        continue
      space_count = len(line.rstrip()) - len(line.rstrip().lstrip())
      if space_count == base_space_count:
        #Has to be a pool line, logs line or cache line
        if component_lines:
          if processing == 'cache':
            d['cache'] = component_lines
          elif processing == 'logs':
            d['logs'] = component_lines
          else :
            d['pool'] = component_lines
          component_lines = []
        if line.strip() == 'cache':
          processing = 'cache'
        elif line.strip() == 'logs':
          processing = 'logs'
        else:
          processing = 'pool'
      component_lines.append(line)
    if component_lines:
      d[processing] = component_lines

    # We have now split the lines up into 3 sections so process each section

    if 'logs' in d:
      root_node, root_name, err = process_config_section(d['logs'])
      if not root_node:
        errstr = "Error retrieving logs config section"
        if err:
          errstr += err
        raise Exception(errstr)        
      return_dict['logs'] = {}
      return_dict['logs']['root'] = root_node
      #print return_dict['logs']
      vdev_type,err = get_vdev_type(return_dict['logs'])
      #print '1', vdev_type, err
      if not vdev_type:
        if err:
          raise Exception(err)
        else:
          raise Exception('Error retrieving vdev type')
      return_dict['logs']['type'] = vdev_type
    else:
      return_dict['logs'] = None

    if 'cache' in d:
      root_node, root_name, err = process_config_section(d['cache'])
      if not root_node:
        errstr = "Error retrieving cache config section"
        if err:
          errstr += err
        raise Exception(errstr)        
      return_dict['cache'] = {}
      return_dict['cache']['root'] = root_node
      vdev_type,err = get_vdev_type(return_dict['cache'])
      #print '2', vdev_type, err
      if not vdev_type:
        if err:
          raise Exception(err)
        else:
          raise Exception('Error retrieving vdev type')
      return_dict['cache']['type'] = vdev_type
    else:
      return_dict['cache'] = None

    root_node, root_name, err = process_config_section(d['pool'])
    if not root_node:
      errstr = "Error retrieving pool config section"
      if err:
        errstr += err
      raise Exception(errstr)        
    return_dict['pool'] = {}
    return_dict['pool']['root'] = root_node
    vdev_type,err = get_vdev_type(return_dict['pool'])
    #print '3', vdev_type, err
    if not vdev_type:
      if err:
        raise Exception(err)
      else:
        raise Exception('Error retrieving vdev type')
    return_dict['pool']['type'] = vdev_type

    #pp = pprint.PrettyPrinter(indent=4)
    #pp.pprint(return_dict)

  except Exception, e:
    return None, "Error processing the pool's config section : %s"%str(e)
  else:
    return return_dict, None


def get_vdev_type(d):
  ''' 
  Given the dictionary within config of either the pool, cache or logs, return the type of VDEV. Only striped(raid0), mirror(raid1), raidz1(raid5), 
  raidz2(raid6), striped-mirror(raid10) are currently supported.
  '''
  vdev_type = None
  try:
    if not d:
      raise Exception('Config section null.')
    if 'root' not in d or not d['root']:
      raise Exception('Root component in vdev is null.')
    if 'children' not in d['root']:
      raise Exception('No child components in root vdev .')

    kids = d['root']['children']

    if not kids:
      raise Exception('Child component in root vdev is null.')

    if len(kids) > 1:
      #Either raid0 or raid 10
      if 'mirror-' in kids[0]['name']:
        vdev_type='Striped Mirror (RAID10)'
      else:
        vdev_type='Striped (RAID0)'
    else:
      #Either raid1, raid5 or raid6
      if 'mirror-' in kids[0]['name']:
        vdev_type='Mirrored (RAID1)'
      elif 'raidz1-' in kids[0]['name']:
        vdev_type='RAID Z1 (RAID5)'
      elif 'raidz2-' in kids[0]['name']:
        vdev_type='RAID Z2 (RAID6)'
      else:
        vdev_type='stripe'
  except Exception, e:
    return None, "Error determining the vdev type : %s"%str(e)
  else:
    return vdev_type, None


def process_pool(lines):
  """Given a list of lines corresponding to one pool, process it and return a dict with all its info"""

  return_dict = {}
  try:
    processing = None
    tmp_list = []
    dict = {}
    for line in lines:
      if 'state:' in line.strip():
        if processing and tmp_list:
          dict[processing] = tmp_list
        tmp_list = []
        processing = 'state'
        #print 'Processing state'
      elif 'status:' in line.strip():
        if processing and tmp_list:
          dict[processing] = tmp_list
        tmp_list = []
        processing = 'status'
        #print 'Processing status'
      elif 'pool:' in line.strip():
        if processing and tmp_list:
          dict[processing] = tmp_list
        tmp_list = []
        processing = 'pool'
        #print 'Processing status'
      elif 'scan:' in line.strip():
        if processing and tmp_list:
          dict[processing] = tmp_list
        tmp_list = []
        processing = 'scan'
      #print 'Processing scan'
      elif 'action:' in line.strip():
        if processing and tmp_list:
          dict[processing] = tmp_list
        tmp_list = []
        processing = 'action'
        #print 'Processing action'
      elif 'see:' in line.strip():
        if processing and tmp_list:
          dict[processing] = tmp_list
        tmp_list = []
        processing = 'see'
        #print 'Processing see'
      elif 'scrub:' in line.strip():
        if processing and tmp_list:
          dict[processing] = tmp_list
        tmp_list = []
        processing = 'scrub'
        #print 'Processing scrub'
      elif 'errors:' in line.strip():
        if processing and tmp_list:
          dict[processing] = tmp_list
        tmp_list = []
        processing = 'errors'
        #print 'Processing errors'
      elif 'config:' in line.strip():
        if processing and tmp_list:
          dict[processing] = tmp_list
        tmp_list = []
        processing = 'config'
        #print 'Processing config'
      #print line
      tmp_list.append(line)
    if processing and tmp_list:
      dict[processing] = tmp_list
    
  
    #print 'pool name is ' + get_single_line_value(dict['pool'], 'pool')
    #print 'state is ' + get_single_line_value(dict['state'], 'state')
    #print 'errors is ' + get_multi_line_value(dict['errors'], 'errors')
    #print 'scan is ' + get_multi_line_value(dict['scan'], 'scan')
  
    if 'pool' in dict:
      temp, err = get_single_line_value(dict['pool'], 'pool')
      if not temp:
        errstr = 'Error getting pool name.'
        if err:
          errstr += errstr
        raise Exception(errstr)
      return_dict['pool_name'] = temp


    if 'state' in dict:
      temp, err = get_single_line_value(dict['state'], 'state')
      if not temp:
        errstr = 'Error getting pool state.'
        if err:
          errstr += errstr
        raise Exception(errstr)
      return_dict['state'] = temp

    if 'errors' in dict:
      temp, err = get_multi_line_value(dict['errors'], 'errors')
      if not temp:
        errstr = 'Error getting pool errors.'
        if err:
          errstr += err
        raise Exception(errstr)
      return_dict['errors'] = temp

    if 'scan' in dict:
      temp, err = get_multi_line_value(dict['scan'], 'scan')
      if not temp:
        errstr = 'Error getting pool scan results.'
        if err:
          errstr += err
        raise Exception(errstr)
      return_dict['scan'] = temp

    if 'status' in dict:
      temp, err = get_multi_line_value(dict['status'], 'status')
      if not temp:
        errstr = 'Error getting pool status results.'
        if err:
          errstr += err
        raise Exception(errstr)
      return_dict['status'] = temp

    if 'see' in dict:
      temp, err = get_multi_line_value(dict['see'], 'see')
      if not temp:
        errstr = 'Error getting pool see results.'
        if err:
          errstr += err
        raise Exception(errstr)
      return_dict['see'] = temp

    if 'config' in dict:
      temp, err = process_pool_config(dict['config'])
      if not temp:
        errstr = 'Error getting pool configuration.'
        if err:
          errstr += err
        raise Exception(errstr)
      return_dict['config'] = temp

    #pp = pprint.PrettyPrinter(indent=4)
    #pp.pprint(return_dict)


  except Exception, e:
    return None, 'Error processing pool configuration : %s'%str(e)
  else:
    return return_dict, None

def get_snapshots(name=None):
  snapshots = []
  try:
    if name:
      cmd = 'zfs list -t snapshot -r %s -H'%name
    else:
      #Return all snapshots
      cmd = '/sbin/zfs list  -t snapshot -H'
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
    if lines:
      for line in lines:
        if line.strip() == 'no datasets available':
          break
        td, err = _get_ds_compononents(line)
        if td:
          tmp_list = td['name'].split('@')
          if tmp_list:
            td['dataset'] = tmp_list[0]
            if len(tmp_list) > 1:
              td['snapshot_name'] = tmp_list[1]
            snapshots.append(td)
        else:
          if err:
            raise Exception(err)
    for snap in snapshots:
      prop, err = get_properties(snap['name'])
      if prop:
        snap['properties'] = prop
  except Exception, e:
    return None, 'Error retrieving snapshots : %s'%str(e)
  else:
    return snapshots, None

def get_create_snapshot_command(target,name=None):
  cmd = None
  try:
    if name:
     cmd = '/sbin/zfs snapshot %s@%s'%(target, name)
    else:
     cmd = '/sbin/zfs snapshot %s@snapshot_'%(target)
  except Exception,e:
    return None, 'Error creating snapshot command : %s'%str(e)
  else:
    return cmd, None

def create_snapshot(target, name):
  try:
    if (not target) or (not name):
      raise Exception('Snapshot target or name not specified')
    cmd, err = get_create_snapshot_command(target,name)
    if err:
      raise Exception(err)
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
  except Exception, e:
    return False, 'Error creating snapshot : %s '%str(e)
  else:
    return True, None

def rename_snapshot(ds_name, snapshot_name, new_snapshot_name):
  try:
    if (not ds_name) or (not snapshot_name) or (not new_snapshot_name):
      raise Exception('Snapshot target, name or new name not specified')

    cmd = '/sbin/zfs rename %s@%s %s@%s'%(ds_name, snapshot_name, ds_name, new_snapshot_name)
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
  except Exception, e:
    return False, 'Error renaming snapshot : %s '%str(e)
  else:
    return True, None

def delete_snapshot(name):
  try:
    if not name:
      raise Exception('Snapshot name not specified')

    cmd = '/sbin/zfs destroy %s'%name
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
  except Exception, e:
    return False, 'Error deleting snapshot : %s '%str(e)
  else:
    return True, None

def rollback_snapshot(name):
  try:
    if not name:
      raise Exception('Snapshot name not specified')

    cmd = '/sbin/zfs rollback %s'%name
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
  except Exception, e:
    return False, 'Error rolling back to snapshot : %s '%str(e)
  else:
    return True, None

def get_datasets_in_pool(pool_name):
  datasets = []
  try:
    cmd = '/sbin/zfs list -r %s -H'%pool_name
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)

    if lines:
      for line in lines:
        if line.strip() == 'no datasets available':
          break
        td, err = _get_ds_compononents(line)
        if td:
          if td['name'] != pool_name:
            prop, err = get_properties(td['name'])
            if not prop:
              if err:
                raise Exception(err)
              else:
                raise Exception('Error retrieving dataset properties')
            td['properties'] = prop
            datasets.append(td)
        else:
          if err:
            raise Exception(err)
  except Exception, e:
    return None, 'Error retrieving datasets : %s'%str(e)
  else:
    return datasets, None

def _get_property_compononents(line, property_index, value_index, source_index):
  d = None
  try:
    if not line:
      raise Exception('Error getting property component : No line specified')
    d = {}
    d['name'] = line[property_index:value_index].strip()
    d['value'] = line[value_index:source_index].strip()
    d['source'] = line[source_index:].strip()
  except Exception, e:
    return None, str(e)
  else:
    return d, None

def get_properties(name):
  properties = {}
  try:
    cmd = '/sbin/zfs get all %s '%name
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)

    if lines:
      property_index = lines[0].find('PROPERTY')
      value_index = lines[0].find('VALUE')
      source_index = lines[0].find('SOURCE')

      for line in lines[1:]:
        td, err = _get_property_compononents(line, property_index, value_index, source_index)
        if td:
          properties[td['name']] = td
        else:
          if err:
            raise Exception(err)
    else:
      return None, None
  except Exception, e:
    return None, 'Error retrieving properties : %s'%str(e)
  else:
    return properties, None

def set_property(name, prop_name, prop_value):
  try:
    if (not name) or (not prop_name) or (not prop_value):
      raise Exception('Required parameters not passed')

    cmd = '/sbin/zfs set %s=%s %s'%(prop_name, prop_value, name)
    #print cmd
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
  except Exception, e:
    if prop_name:
      return False, 'Error saving property %s : %s '%(prop_name, str(e))
    else:
      return False, 'Error saving property  : %s '%str(e)
  else:
    return True, None

def delete_dataset(ds_name):
  try:
    if (not ds_name):
      raise Exception('Dataset name not specified')

    cmd = '/sbin/zfs destroy %s'%(ds_name)
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
  except Exception, e:
    return False, 'Error deleting dataset : %s '%str(e)
  else:
    return True, None


def create_pool_data_vdev_list(pool_type, num_raid_disks = None, stripe_width = None):
  ''' Return a list of the appropriate format based on the pool type using the list of available drives '''
  vdev_list = []
  try:
    free_disks, err = get_free_disks()
    if err:
      raise Exception(err)

    if pool_type not in ['mirror', 'raid5', 'raid6', 'raid10']:
      raise Exception ('Unsupported pool type specified')
    if pool_type in ['raid5', 'raid6'] and not num_raid_disks:
      raise Exception ('Number of disks in the RAID not specified')

    if free_disks:
      num_free_disks = len(free_disks)
      if pool_type == 'mirror':
        if num_free_disks < 2:
          raise Exception ('Insufficient disks to form a mirrored pool')
        for i in range(2):
          vdev_list.append(free_disks[i]['id'])
      elif pool_type == 'raid5':
        if num_free_disks < 3:
          raise Exception ('Insufficient disks to form a RAID5 pool')
        for i in range(num_raid_disks):
          vdev_list.append(free_disks[i]['id'])
      elif pool_type == 'raid6':
        if num_free_disks < 4:
          raise Exception ('Insufficient disks to form a RAID6 pool')
        for i in range(num_raid_disks):
          vdev_list.append(free_disks[i]['id'])
      elif pool_type == 'raid10':
        if not stripe_width:
          raise Exception ('Stripe width not specified for a RAID10 pool')
        if num_free_disks < (int(stripe_width)*2):
          raise Exception ('Insufficient disks to form a RAID10 pool')
        l = []
        for i in range(int(stripe_width)*2):
          l.append(free_disks[i]['id'])
          if i%2 != 0:
            if l:
              vdev_list.append(l)
            l = []
  except Exception, e:
    return None, 'Error creating pool data vdev list: %s '%str(e)
  else:
    return vdev_list, None

def create_pool(pool_name, type, data_vdev_list, log_vdev = None):
  try:
    if not pool_name:
      raise Exception('Pool name not specified')

    if not type:
      raise Exception('Pool type not specified')

    if not data_vdev_list:
      raise Exception('Pool vdevs not specified')

    free_disks, err = get_free_disks()
    if err:
      raise Exception(err)
    free_disk_ids = []
    for disk in free_disks:
      free_disk_ids.append(disk['id'])
    #print 'free disks', free_disks
    #print 'vdevlist', data_vdev_list

    if type == 'mirror':
      if len(data_vdev_list) != 2:
        raise Exception('Only 2 VDEVs supported for mirrored pools ')
      if (data_vdev_list[0] not in free_disk_ids) or (data_vdev_list[1] not in free_disk_ids):
          raise Exception('Specified disk already in use in another pool!')
      cmd = '/sbin/zpool create -f  %s mirror %s %s'%(pool_name, data_vdev_list[0], data_vdev_list[1])
    elif type == 'raid5':
      if len(data_vdev_list) < 3:
        raise Exception('Need a minimum of 3 VDEVs for a RAID-5 pools ')
      cmd = '/sbin/zpool create -f  %s raidz1 '%(pool_name)
      for vdev in data_vdev_list:
        if vdev not in free_disk_ids:
          raise Exception('Specified disk already in use in another pool!')
        cmd += ' %s '%vdev
    elif type == 'raid6':
      if len(data_vdev_list) < 4:
        raise Exception('Need a minimum of 4 VDEVs for a RAID-6 pool! ')
      cmd = '/sbin/zpool create -f  %s raidz2 '%(pool_name)
      for vdev in data_vdev_list:
        if vdev not in free_disk_ids:
          raise Exception('Specified disk already in use in another pool!')
        cmd += ' %s '%vdev
    elif type == 'raid10':
      if len(data_vdev_list) < 4:
        raise Exception('Need a minimum of 4 VDEVs for a RAID-10 pool! ')
      cmd = 'zpool create -f %s '%(pool_name)
      for vdev in data_vdev_list:
        if (not isinstance(vdev, types.ListType)) or len(vdev) != 2:
          raise Exception('Invalid VDEV specification given for a RAID-10 pool ')
        for v in vdev:
          if v not in free_disk_ids:
            raise Exception('Specified disk already in use in another pool!')
        cmd += ' mirror %s'%(' '.join(vdev))
    if log_vdev:
      cmd += ' log %s'%log_vdev
          
    #print cmd
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
  except Exception, e:
    return False, 'Error creating pool : %s '%str(e)
  else:
    return True, None


def delete_pool(pool_name):
  try:
    if (not pool_name):
      raise Exception('Pool name not specified')

    cmd = '/sbin/zpool destroy %s'%(pool_name)
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
  except Exception, e:
    return False, 'Error deleting pool : %s '%str(e)
  else:
    return True, None

def scrub_pool(pool_name):
  try:
    if (not pool_name):
      raise Exception('Pool name not specified')

    cmd = '/sbin/zpool scrub %s'%(pool_name)
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
  except Exception, e:
    return False, 'Error initiating pool scrub : %s '%str(e)
  else:
    return True, None

def remove_pool_vdev(pool_name, vdev):
  try:
    if (not pool_name) or (not vdev):
      raise Exception('Pool name or vdev not specified')

    cmd = '/sbin/zpool remove %s %s'%(pool_name, vdev)
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
  except Exception, e:
    return False, 'Error removing  pool vdev : %s '%str(e)
  else:
    return True, None

def set_pool_log_vdev(pool_name, vdev):
  try:
    if (not pool_name) or (not vdev):
      raise Exception('Pool name or vdev not specified')

    cmd = '/sbin/zpool add %s log %s'%(pool_name, vdev)
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
  except Exception, e:
    return False, 'Error setting  pool vdev : %s '%str(e)
  else:
    return True, None

def create_dataset(parent, ds_name, properties):
  try:
    if (not ds_name) or (not parent):
      raise Exception('Dataset name or parent not specified')

    cmd = '/sbin/zfs create  '
    if properties:
      for pname, pvalue in properties.items():
        cmd += '-o %s=%s '%(pname, pvalue)
    cmd += ' %s/%s'%(parent, ds_name)
    #print cmd
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
    path = '%s/%s'%(parent, ds_name)
    cmd = 'zfs set acltype=posixacl %s'%path
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
    os.chown('/%s'%path, -1, 500)
    os.chmod('/%s'%path, stat.S_IWUSR|stat.S_IRUSR|stat.S_IXUSR|stat.S_IRGRP|stat.S_IXGRP|stat.S_IROTH|stat.S_IXOTH|stat.S_ISGID)
    os.system('setfacl -d -m g::rwx /%s'%path)
    os.system('setfacl -d -m o::rx /%s'%path)
  except Exception, e:
    return False, 'Error creating dataset : %s '%str(e)
  else:
    return True, None

def create_zvol(pool, name, properties, size, unit):
  try:
    if (not name) or (not pool):
      raise Exception('Block device volume name or pool not specified')

    cmd = '/sbin/zfs create  -V %d%s '%(size,unit)
    if properties:
      for pname, pvalue in properties.items():
        cmd += '-o %s=%s '%(pname, pvalue)
    cmd += ' %s/%s'%(pool, name)
    #print cmd
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
  except Exception, e:
    return False, 'Error creating dataset : %s '%str(e)
  else:
    return True, None

def get_children_datasets(ds_name):
  ''' Given a dataset, return a list of all its children datasets '''
  children = []
  try:
    cmd = '/sbin/zfs list -r %s -H -o name'%ds_name
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)

    if lines:
      for line in lines:
        if line.strip() == 'no datasets available':
          break
        if line.strip() == ds_name:
          continue
        children.append(line.strip())
    else:
      return None, None
  except Exception, e:
    return None, 'Error retrieving child datasets: %s'%str(e)
  else:
    return children, None

def get_all_datasets_and_pools():
  ''' Return a list of all datasets and pools'''
  retlist = []
  try:
    cmd = '/sbin/zfs list  -H -o name'
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)

    if lines:
      for line in lines:
        if line.strip() == 'no datasets available':
          break
        retlist.append(line.strip())
    else:
      return None, None
  except Exception, e:
    return None, 'Error retrieving datasets and pools: %s'%str(e)
  else:
    return retlist, None

def get_pools():
  pools = []
  try:
    cmd = '/sbin/zpool status'
    lines, err = command.get_command_output(cmd)
    if err:
      raise Exception(err)
    
    pool_lines = []
    processed = False
    pl = []
    if lines:
      for line in lines:
        if not line.strip():
          continue
        if 'pool:' in line:
          #New pool encountered so start a new list
          if pl:
            pool_lines.append(pl)
            pl = []
        pl.append(line)
      if pl:
        pool_lines.append(pl)
  
      if pool_lines:
        for l in pool_lines:
          d, err = process_pool(l)
          if not d:
            errstr = "Error processing a pool : "
            if err:
              errstr += err
            raise Exception(errstr)
          d1,err = get_properties(d['pool_name'])
          if not d1:
            errstr = "Error getting pool properties : "
            if err:
              errstr += err
            raise Exception(errstr)
          d['properties'] = d1
          #Now get related datasets in this pool
          datasets, err = get_datasets_in_pool(d['pool_name'])
          if not datasets and err:
            raise Exception(err)
          else:
            d['datasets'] = datasets
          pools.append(d)
    
  
      snapshots, err = get_snapshots()
      if not snapshots and err:
        raise Exception(err)
  
      if snapshots:
        if pools:
          for pool in pools:
            for snapshot in snapshots:
              if snapshot['dataset'] == pool['pool_name']:
                if 'snapshots' not in pool:
                  pool['snapshots'] = []
                pool['snapshots'].append(snapshot)
            #Now add the snapshot info for each dataset
            if 'snapshots' in pool:
              datasets = pool['datasets']
              if datasets:
                for ds in datasets:
                  for snapshot in snapshots:
                    if snapshot['dataset'] == ds['name']:
                      if 'snapshots' not in ds:
                        ds['snapshots'] = []
                      ds['snapshots'].append(snapshot)

  except Exception, e:
    return None, "Error processing zfs pool information : %s"%str(e)
  else:
    return pools, None

def get_pool(pool_name):
  d = None
  try:
    pools, err = get_pools()
    if not pools:
      if err:
        raise Exception(err)
      else:
        raise Exception('Error retrieving pool list')
    for pool in pools:
      if pool['pool_name'] == pool_name:
        d = pool
        break
  except Exception, e:
    return None, "Error retrieving ZFS pool info : %s"%str(e)
  else:
    return d, None


def _get_ds_compononents(line):
  d = None
  try:
    ds_components = line.split()
    if ds_components:
      if ds_components[0].strip():
        d = {}
        d['name'] = ds_components[0]
        d['used'] = ds_components[1]
        d['avail'] = ds_components[2]
        d['refer'] = ds_components[3]
        d['mountpoint'] = ds_components[4]
  except Exception, e:
    return None, str(e)
  else:
    return d, None

def get_free_disks():

  free_disks = []
  try:
    pools, err = get_pools()
    if not pools:
      if err:
      	errstr = "Error getting pools information : "
        errstr += err
      	raise Exception(errstr)

    all_disks, err = disks.get_disk_info_all()
    if not all_disks:
      errstr = "Error getting disk information : "
      if err:
        errstr += err
      raise Exception(errstr)
    #print all_disks

    disk_id_list = []
    for sn, disk in all_disks.items():
      if 'id' in disk:
        disk_id_list.append(disk['id'])
    #print disk_id_list

    free_disk_ids = []
    used_disks = []
    for pool in pools:
      if 'config' not in pool:
        continue
      if 'cache' in pool['config'] and pool['config']['cache'] and pool['config']['cache']['root']:
        ud, err = get_disks_in_component(pool['config']['cache']['root'])
        if err:
          raise Exception(err)
        if ud:
          used_disks.extend(ud)
      if 'logs' in pool['config'] and pool['config']['logs'] and pool['config']['logs']['root']:
        ud, err = get_disks_in_component(pool['config']['logs']['root'])
        if err:
          raise Exception(err)
        if ud:
          used_disks.extend(ud)
      if 'pool' in pool['config'] and pool['config']['pool'] and pool['config']['pool']['root']:
        ud, err = get_disks_in_component(pool['config']['pool']['root'])
        if err:
          raise Exception(err)
        if ud:
          used_disks.extend(ud)

    for disk_id in disk_id_list:
      if disk_id not in used_disks:
        free_disk_ids.append(disk_id)

    if free_disk_ids:
      for sn, disk in all_disks.items():
        if 'boot_device' in disk:
          continue
        if disk['id'] in free_disk_ids:
          free_disks.append(disk)
  except Exception, e:
    return None, "Error getting free disks : %s"%str(e)
  else:
    return free_disks, None
    
def get_disks_in_component(component):
  disks = []
  try:
    if 'children' in component and component['children']:
      for kid in component['children']:
        kid_disks,err = get_disks_in_component(kid)
        if err:
          raise Exception('Error getting disks in use : %s'%err)
        if kid_disks:
          disks.extend(kid_disks)
    if component['type'] == 'device':
      disks.append(component['name'])
  except Exception, e:
    return None, "Error getting disks in use : %s"%str(e)
  else:
    return disks, None

def get_all_components_status(pools):

  status_dict = {}
  try:
    if not pools:
    	raise Exception('No pools provided')

    for pool in pools:
      status_list = []
      if 'config' not in pool:
        continue
      if 'cache' in pool['config'] and pool['config']['cache'] and pool['config']['cache']['root']:
        sl, err = get_children_component_status(pool['config']['cache']['root'])
        if err:
          raise Exception(err)
        if sl:
          status_list.extend(sl)
      if 'logs' in pool['config'] and pool['config']['logs'] and pool['config']['logs']['root']:
        sl, err = get_children_component_status(pool['config']['logs']['root'])
        if err:
          raise Exception(err)
        if sl:
          status_list.extend(sl)
      if 'pool' in pool['config'] and pool['config']['pool'] and pool['config']['pool']['root']:
        sl, err = get_children_component_status(pool['config']['pool']['root'])
        if err:
          raise Exception(err)
        if sl:
          status_list.extend(sl)
      status_dict[pool['pool_name']] = status_list

  except Exception, e:
    return None, "Error getting all components status : %s"%str(e)
  else:
    return status_dict, None
    
def get_children_component_status(component):
  csl = []
  try:
    if 'children' in component and component['children']:
      for kid in component['children']:
        kid_csl,err = get_children_component_status(kid)
        if err:
          raise Exception('Error getting disks in use : %s'%err)
        if kid_csl:
          csl.extend(kid_csl)
    if 'status' in component:
      d = {}
      d['name'] = component['name']
      d['type'] = component['type']
      d['status'] = component['status']
      csl.append(d)
  except Exception, e:
    return None, "Error getting children component status: %s"%str(e)
  else:
    return csl, None

def get_all_zvols():

  zvols = []
  try:
    pools, err = get_pools()
    if err:
      raise Exception(err)
    if pools:
      for pool in pools:
        if pool['datasets']:
          for ds in pool['datasets']:
            if ds['properties']['type']['value'] == 'volume':
              d = {}
              d['name'] = ds['name']
              d['path'] = '/dev/zvol/%s'%ds['name']
              zvols.append(d)
  except Exception, e:
    return None, "Error getting block device volumes : %s"%str(e)
  else:
    return zvols, None
        

def main():
  d, err = get_pools()
  #d, err = get_all_components_status()
  #d, err = get_all_zvols()
  #d, err = get_pool('pool1')
  #disks, err = get_disks_in_component(d['config']['pool']['root'])
  #d, err = get_snapshots()
  #d, err = get_properties('pool1')
  #d, err = get_datasets_in_pool('pool1')
  #print create_pool('test_pool', 'mirror' , ['ata-ST1000DM003-1ER162_W4Y1HK70', 'ata-ST1000DM003-1ER162_W4Y1H2CG'])
  #d, err = get_free_disks()
  #d, err = create_pool_data_vdev_list('raid10', 2)
  if err:
    print err
  else:
    pp = pprint.PrettyPrinter(indent=4)
    pp.pprint(d)
    #pp.pprint(disks)
  '''
  #print create_pool('test_pool', 'mirror' , ['ata-ST1000DM003-1ER162_W4Y1HK70', 'ata-ST1000DM003-1ER162_W4Y1H2CG'])
  #print delete_pool('test_pool')
  #d, err = get_free_disks()
  #if err:
  #  print err
  #else
    pp = pprint.PrettyPrinter(indent=4)
    #pp.pprint(d)
    pp.pprint(disks)
  '''

if __name__ == '__main__':
  main()
