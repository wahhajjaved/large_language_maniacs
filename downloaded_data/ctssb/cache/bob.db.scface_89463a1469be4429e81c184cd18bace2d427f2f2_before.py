#!/usr/bin/env python
# vim: set fileencoding=utf-8 :
# Laurent El Shafey <Laurent.El-Shafey@idiap.ch>

"""This script creates the SCFace database in a single pass.
"""

import os

from .models import *

def nodot(item):
  """Can be used to ignore hidden files, starting with the . character."""
  return item[0] != '.'

def add_clients(session, filename, verbose):
  """Add clients to the SCFace database."""

  # open features.txt file containing information about the clients
  f = open(filename, 'r')
  c = 0
  for line in f:
    # Ignore the 10 first (useless) lines
    c = c + 1
    if c<=10:
      continue
    
    # parse the line
    tok = line.split('\t')

    # birthyear
    birthyear = tok[1].split('.')[2]
    # group
    if int(tok[0]) <= 43:
      group = 'world'
    elif int(tok[0]) <= 87:
      group = 'dev'
    else:
      group = 'eval'
    # gender
    if int(tok[2]) == 0:
      gender = 'm'
    else:
      gender = 'f'

    # Add the client
    if verbose: print "Adding file '%s'..." %(os.path.basename(filename).split('.')[0], )
    session.add(Client(int(tok[0]), group, int(birthyear), gender, int(tok[3]), int(tok[4]), int(tok[5])))

def add_subworlds(session, verbose):
  """Adds splits in the world set, based on the client ids"""
  # one third
  snames = ['onethird', 'twothirds']
  slists = [[ 1,  4,  5,  6,  8, 11, 12, 18, 20, 30, 
             33, 36, 39, 40],
            [ 2,  3,  7,  9, 10, 13, 14, 15, 16, 17,
             19, 21, 22, 23, 24, 25, 26, 27, 28, 29,
             31, 32, 34, 35, 37, 38, 41, 42, 43]]
  for k in range(len(snames)):
    if verbose: print "Adding subworld '%s'" %(snames[k], )
    su = Subworld(snames[k])
    session.add(su)
    session.flush()
    session.refresh(su)
    l = slists[k]
    for c_id in l:
      if verbose: print "Adding client '%d' to subworld '%s'..." %(c_id, snames[k])
      su.clients.append(session.query(Client).filter(Client.id == c_id).first())
 
def add_files(session, imagedir, verbose):
  """Add files to the SCFace database."""
 
  def add_file(session, basename, maindir, frontal, verbose):
    """Parse a single filename and add it to the list."""
    v = os.path.splitext(basename)[0].split('_')
    if verbose: print "Adding file '%s'..." %(basename, )
    if frontal:
      session.add(File(int(v[0]), os.path.join(maindir, basename), 'frontal', 0))
    else:
      session.add(File(int(v[0]), os.path.join(maindir, basename), v[1], int(v[2])))

  for maindir in ['mugshot_frontal_cropped_all', 'surveillance_cameras_distance_1',\
                  'surveillance_cameras_distance_2', 'surveillance_cameras_distance_3']:
    if not os.path.isdir( os.path.join( imagedir, maindir) ):
      continue
    elif maindir == 'mugshot_frontal_cropped_all':
      for f in filter(nodot, os.listdir( os.path.join( imagedir, maindir) )):
        basename, extension = os.path.splitext(f)
        add_file(session, basename, maindir, True, verbose)
    else:
      for camdir in filter(nodot, os.listdir( os.path.join( imagedir, maindir) )):
        subdir = os.path.join(maindir, camdir)
        for f in filter(nodot, os.listdir( os.path.join( imagedir, subdir) )):
          basename, extension = os.path.splitext(f)
          add_file(session, basename, subdir, False, verbose)
   
def add_protocols(session, verbose):
  """Adds protocols"""

  # 1. DEFINITIONS
  # Numbers in the lists correspond to session identifiers
  protocol_definitions = {}

  # Protocol combined 
  world = [(['frontal', 'cam1', 'cam2', 'cam3', 'cam4', 'cam5'], [])]
  enrol = [(['frontal'], [0])]
  probe = [(['cam1', 'cam2', 'cam3', 'cam4', 'cam5'], [1,2,3])]
  protocol_definitions['combined'] = [world, enrol, probe]

  # Protocol close
  world = [(['frontal', 'cam1', 'cam2', 'cam3', 'cam4', 'cam5'], [])]
  enrol = [(['frontal'], [0])]
  probe = [(['cam1', 'cam2', 'cam3', 'cam4', 'cam5'], [3])]
  protocol_definitions['close'] = [world, enrol, probe]

  # Protocol medium
  world = [(['frontal', 'cam1', 'cam2', 'cam3', 'cam4', 'cam5'], [])]
  enrol = [(['frontal'], [0])]
  probe = [(['cam1', 'cam2', 'cam3', 'cam4', 'cam5'], [2])]
  protocol_definitions['medium'] = [world, enrol, probe]

  # Protocol far
  world = [(['frontal', 'cam1', 'cam2', 'cam3', 'cam4', 'cam5'], [])]
  enrol = [(['frontal'], [0])]
  probe = [(['cam1', 'cam2', 'cam3', 'cam4', 'cam5'], [1])]
  protocol_definitions['far'] = [world, enrol, probe]

  # 2. ADDITIONS TO THE SQL DATABASE
  protocolPurpose_list = [('world', 'train'), ('dev', 'enrol'), ('dev', 'probe'), ('eval', 'enrol'), ('eval', 'probe')]
  for proto in protocol_definitions:
    p = Protocol(proto)
    # Add protocol
    if verbose: print "Adding protocol %s..." % (proto)
    session.add(p)
    session.flush()
    session.refresh(p)

    # Add protocol purposes
    for key in range(len(protocolPurpose_list)):
      purpose = protocolPurpose_list[key]
      pu = ProtocolPurpose(p.id, purpose[0], purpose[1])
      if verbose: print "  Adding protocol purpose ('%s','%s')..." % (purpose[0], purpose[1])
      session.add(pu)
      session.flush()
      session.refresh(pu)

       # Add files attached with this protocol purpose
      client_group = ""
      prop_list = []
      if(key == 0): client_group = "world"
      elif(key == 1 or key == 2): client_group = "dev"
      elif(key == 3 or key == 4): client_group = "eval"
      if(key == 0):
        prop_list = protocol_definitions[proto][0]
      if(key == 1 or key == 3):
        prop_list = protocol_definitions[proto][1]
      elif(key == 2 or key == 4):
        prop_list = protocol_definitions[proto][2]

      # Adds 'protocol' files
      for el in prop_list:
        cams = el[0] # list of camera identifiers
        dids = el[1] # list of distance identifiers
        q = session.query(File).join(Client).\
              filter(Client.sgroup == client_group)
        if cams:
          q = q.filter(File.camera.in_(cams))
        if dids:
          q = q.filter(File.distance.in_(dids))
        q = q.order_by(File.id)
        for k in q:
          if verbose: print "    Adding protocol file '%s'..." % (k.path)
          pu.files.append(k)

def create_tables(args):
  """Creates all necessary tables (only to be used at the first time)"""

  from bob.db.utils import create_engine_try_nolock

  engine = create_engine_try_nolock(args.type, args.files[0], echo=(args.verbose >= 2))
  Base.metadata.create_all(engine)

# Driver API
# ==========

def create(args):
  """Creates or re-creates this database"""

  from bob.db.utils import session_try_nolock

  dbfile = args.files[0]

  if args.recreate: 
    if args.verbose and os.path.exists(dbfile):
      print('unlinking %s...' % dbfile)
    if os.path.exists(dbfile): os.unlink(dbfile)

  if not os.path.exists(os.path.dirname(dbfile)):
    os.makedirs(os.path.dirname(dbfile))

  # the real work...
  create_tables(args)
  s = session_try_nolock(args.type, args.files[0], echo=(args.verbose >= 2)) 
  add_clients(s, args.featuresfile, args.verbose)
  add_subworlds(s, args.verbose)
  add_files(s, args.imagedir, args.verbose)
  add_protocols(s, args.verbose)
  s.commit()
  s.close()

def add_command(subparsers):
  """Add specific subcommands that the action "create" can use"""

  parser = subparsers.add_parser('create', help=create.__doc__)

  parser.add_argument('-R', '--recreate', action='store_true', default=False,
      help="If set, I'll first erase the current database")
  parser.add_argument('-v', '--verbose', action='count',
      help="Do SQL operations in a verbose way")
  parser.add_argument('--featuresfile', action='store', metavar='FILE',
      default='/idiap/resource/database/scface/SCface_database/features.txt',
      help="Change the path to the file containing information about the clients of the SCFace database (defaults to %(default)s)") 
  parser.add_argument('-D', '--imagedir', action='store', metavar='DIR',
      default='/idiap/group/biometric/databases/scface/images',
      help="Change the relative path to the directory containing the images of the SCFace database (defaults to %(default)s)")
  
  parser.set_defaults(func=create) #action
