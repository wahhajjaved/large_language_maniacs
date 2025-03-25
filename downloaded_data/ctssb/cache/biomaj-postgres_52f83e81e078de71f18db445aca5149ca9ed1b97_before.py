import logging
import logging.config
import os
import ConfigParser
import time
import sys

from biomaj.bmajindex import BmajIndex

class BiomajConfig:
  '''
  Manage Biomaj configuration
  '''

  DEFAULTS = {
  'http.parse.dir.line': r'<img[\s]+src="[\S]+"[\s]+alt="\[DIR\]"[\s]*/?>[\s]*<a[\s]+href="([\S]+)/"[\s]*>.*([\d]{2}-[\w\d]{2,5}-[\d]{4}\s[\d]{2}:[\d]{2})',
  'http.parse.file.line': r'<img[\s]+src="[\S]+"[\s]+alt="\[[\s]+\]"[\s]*/?>[\s]<a[\s]+href="([\S]+)".*([\d]{2}-[\w\d]{2,5}-[\d]{4}\s[\d]{2}:[\d]{2})[\s]+([\d\.]+[MKG]{0,1})',
  'http.group.dir.name': 1,
  'http.group.dir.date': 2,
  'http.group.file.name': 1,
  'http.group.file.date': 2,
  'http.group.file.size': 3,
  'visibility.default': 'public',
  'historic.logfile.level': 'INFO',
  'bank.num.threads': 2,
  'files.num.threads': 4
  }

  # Old biomaj level compatibility
  LOGLEVEL = {
    'DEBUG': logging.DEBUG,
    'VERBOSE': logging.INFO,
    'INFO': logging.INFO,
    'WARN': logging.WARNING,
    'ERR': logging.ERROR
  }

  '''
  Global configuration file
  '''
  global_config = None

  '''
  Per use global configuration file, overriding global_config
  '''
  user_config = None

  @staticmethod
  def load_config(config_file='global.properties'):
    '''
    Loads general config

    :param config_file: global.properties file path
    :type config_file: str
    '''
    if not os.path.exists(config_file) and not os.path.exists(os.path.expanduser('~/.biomaj.cfg')):
      raise Exception('Missing global configuration file')

    BiomajConfig.config_file = config_file

    BiomajConfig.global_config = ConfigParser.ConfigParser()

    if os.path.exists(os.path.expanduser('~/.biomaj.cfg')):
      BiomajConfig.user_config = ConfigParser.ConfigParser()
      BiomajConfig.user_config.read([os.path.expanduser('~/.biomaj.cfg')])

    BiomajConfig.global_config.read([config_file])

    # ElasticSearch indexation support
    do_index = False
    if BiomajConfig.global_config.get('GENERAL','use_elastic') and \
      BiomajConfig.global_config.get('GENERAL','use_elastic') == 1:
      do_index = True
    if do_index:
      if BiomajConfig.global_config.get('GENERAL','elastic_nodes'):
        elastic_hosts = BiomajConfig.global_config.get('GENERAL','elastic_nodes').split(',')
      else:
        elastic_hosts = ['localhost']
      elastic_index = BiomajConfig.global_config.get('GENERAL','elastic_index')
      if elastic_index is None:
        elastic_index = 'biomaj'
      BmajIndex.load(index=elastic_index, hosts=elastic_hosts, do_index=do_index)




  def __init__(self, bank, options=None):
    '''
    Loads bank configuration

    :param bank: bank name
    :type bank: str
    :param options: bank options
    :type options: argparse
    '''
    self.name = bank
    if BiomajConfig.global_config is None:
      BiomajConfig.load_config()
    self.config_bank = ConfigParser.ConfigParser()
    conf_dir = BiomajConfig.global_config.get('GENERAL', 'conf.dir')
    if not os.path.exists(os.path.join(conf_dir,bank+'.properties')):
      logging.error('Bank configuration file does not exists')
      raise Exception('Configuration file '+bank+'.properties does not exists')
    try:
      self.config_bank.read([os.path.join(conf_dir,bank+'.properties')])
    except Exception as e:
      print "Configuration file error: "+str(e)
      logging.error("Configuration file error "+str(e))
      sys.exit(1)

    self.last_modified = long(os.stat(os.path.join(conf_dir,bank+'.properties')).st_mtime)

    if os.path.exists(os.path.expanduser('~/.biomaj.cfg')):
      logging.config.fileConfig(os.path.expanduser('~/.biomaj.cfg'))
    else:
      logging.config.fileConfig(BiomajConfig.config_file)

    if options is None or (( hasattr(options,'no_log') and not options.no_log) or ('no_log' in options and not options['no_log'])):
      logger = logging.getLogger()
      bank_log_dir = os.path.join(self.get('log.dir'),bank,str(time.time()))
      if not os.path.exists(bank_log_dir):
        os.makedirs(bank_log_dir)
      hdlr = logging.FileHandler(os.path.join(bank_log_dir,bank+'.log'))
      self.log_file = os.path.join(bank_log_dir,bank+'.log')
      if options is not None and options.get_option('log') is not None:
        hdlr.setLevel(BiomajConfig.LOGLEVEL[options.get_option('log')])
      else:
        hdlr.setLevel(BiomajConfig.LOGLEVEL[self.get('historic.logfile.level')])
      formatter = logging.Formatter('%(asctime)s %(levelname)-5.5s [%(name)s][%(threadName)s] %(message)s')
      hdlr.setFormatter(formatter)
      logger.addHandler(hdlr)
    else:
       self.log_file='none'


  def set(self, prop, value, section='GENERAL'):
    self.config_bank.set(section, prop, value)

  def get_bool(self, prop, section='GENERAL', escape=True, default=None):
    '''
    Get a boolean property from bank or general configration. Optionally in section.
    '''
    value = self.get(prop,section,escape,default)
    if value or value == 'true' or value == '1':
      return True
    else:
      return False

  def get(self, prop, section='GENERAL', escape=True, default=None):
    '''
    Get a property from bank or general configration. Optionally in section.
    '''
    if self.config_bank.has_option(section,prop):
      val = self.config_bank.get(section,prop)
      # If regexp, escape backslashes
      if escape and (prop == 'local.files' or prop == 'remote.files' or prop == 'http.parse.dir.line' or prop == 'http.parse.file.line'):
        val = val.replace('\\\\','\\')
      return val

    if BiomajConfig.user_config is not None:
      if BiomajConfig.user_config.has_option(section, prop):
        return BiomajConfig.user_config.get(section, prop)

    if BiomajConfig.global_config.has_option(section, prop):
      return BiomajConfig.global_config.get(section, prop)

    if prop in BiomajConfig.DEFAULTS:
      return BiomajConfig.DEFAULTS[prop]

    return default


  def get_time(self):
    '''
    Return last modification time of config files
    '''
    return self.last_modified
