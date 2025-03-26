"""
Config for Dox.
"""
from ConfigParser import SafeConfigParser
import os.path
from os import getcwd, mkdir, remove, walk
import json
import hashlib

def dox_dir():
    """
    Gets or creates the .dox directory.
    """
    dox_dirpath = os.path.join(getcwd(),'.dox')
    
    if not os.path.exists(dox_dirpath):
        mkdir(dox_dirpath)
    
    return dox_dirpath

def init_environment(args):
    """
    Initializes the environment.
    """    
    dirpath = dox_dir()
    
    cfg_path = os.path.join(dirpath,'dox.cfg')
    
    # Clean out previous config
    if os.path.exists(cfg_path):
        remove(cfg_path)
    
    # New Config File
    cfg = SafeConfigParser()
    cfg.add_section('Connection')
    cfg.set('Connection','endpoint',args.endpoint)
    cfg.set('Connection','library_key',args.library_key)
    cfg.set('Connection','project',args.project)
    cfg.set('Connection','content_type',args.content_type)
    cfg.set('Connection','body_field',args.body_field)
    if args.key_field:
        cfg.set('Connection','key_field',args.key_field)
    
    if args.api_key:
        cfg.set('Connection','api_key',args.api_key)
    
    with open(cfg_path,'wb') as cfg_file:
        cfg.write(cfg_file)
        
    # Make file hash directory
    hashdir_path = os.path.join(dirpath,'hashes')
    if not os.path.exists(hashdir_path):
        mkdir(hashdir_path)

def get_cfg():
    """
    Gets the config file.
    """
    cfg = SafeConfigParser()
    cfg_path = os.path.join(dox_dir(),'dox.cfg')

    # Sanity check
    if not os.path.exists(cfg_path):
        raise ValueError('No config file found.  Directory has not been initialized for dox.  Use dox init.')

    cfg.read(cfg_path)
    
    return cfg

def get_keyfields():
    """
    Gets the keyfields data.
    """
    dirpath = dox_dir()
    keyfield_path = os.path.join(dirpath,'keyfields.json')
    if os.path.exists(keyfield_path):
        with open(keyfield_path,'r') as keyfield_file:
            keyfield_data = json.loads(keyfield_file.read())
            return keyfield_data
    else:
        return {}

def write_keyfields(data):
    """
    Writes the keyfield data file.
    """
    dirpath = dox_dir()
    keyfield_path = os.path.join(dirpath,'keyfields.json')
    with open(keyfield_path,'wb') as keyfield_file:
        keyfield_file.write(json.dumps(data))

def get_keymap():
    """
    Gets the keymap data.
    """
    dirpath = dox_dir()
    keymap_path = os.path.join(dirpath,'keymap.json')
    if os.path.exists(keymap_path):
        with open(keymap_path,'r') as keymap_file:
            keymap_data = json.loads(keymap_file.read())
            return keymap_data
    else:
        return {}

def write_keymap(data):
    """
    Saves the keymap data.
    """
    dirpath = dox_dir()
    keymap_path = os.path.join(dirpath,'keymap.json')
    with open(keymap_path,'wb') as keymap_file:
        keymap_file.write(json.dumps(data))


def clean_hashes():
    """
    Cleans the local file hash directory out.
    """
    hash_path = os.path.join(dox_dir(),'hashes')
    if os.path.exists(hash_path):
        for root, dirs, files in walk(hash_path):
            for name in files:
                if name.endswith('.hash'):
                    remove(os.path.join(root,name))
    else:
        mkdir(hash_path)

def write_hash(markdown_file_path):
    """
    Scans the file and records a hash digest of the contents.
    """
    with open(markdown_file_path) as markdown_file:
        d = hashlib.sha256()
        d.update(markdown_file.read())
        digest = d.hexdigest()
        hash_file_path = '%s.hash' % os.path.join(dox_dir(),'hashes',os.path.split(markdown_file.name)[1])
        with open(hash_file_path,'wb') as hash_file:
            hash_file.write(digest)

def is_modified(markdown_file_path):
    """
    Tests if the markdown file has been modified.
    """
    with open(markdown_file_path,'r') as markdown_file:
        hash_file_path = '%s.hash' % os.path.join(dox_dir(),'hashes',os.path.split(markdown_file.name)[1])
        if os.path.exists(hashfile_path):
            d = hashlib.sha256()
            d.update(markdown_file.read())
            digest = d.hexdigest()
            with open(hashfile_path) as hashfile:
                stored_hash = hashfile.read()
                if stored_hash != digest:
                    return True # non-matching hashes - file is modified
                else:
                    return False # hashes match - file has not been modified
        else:
            return True # no stored hash - file is modified by definition
