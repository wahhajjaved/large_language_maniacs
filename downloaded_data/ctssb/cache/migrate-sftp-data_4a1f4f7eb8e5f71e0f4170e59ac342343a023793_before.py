# coding: utf-8
#!/usr/bin/env python

from optparse import OptionParser
from ConfigUtils import *
from SFTPFiles import *
from SocrataStuff import *
from PyLogger import *
from Utils import *
from JobStatusEmailerComposer import *
import pandas as pd
from PandasUtils import *

def parse_opts():
  helpmsgConfigFile = '''Use the -c to add a config yaml file. EX: fieldConfig.yaml.
                         Full Example of command: python migrate_sftp_data.py -c job_configs.yaml -d configs/'''
  parser = OptionParser(usage='usage: %prog [options] ')
  parser.add_option('-c', '--configfile',
                      action='store',
                      dest='configFn',
                      default=None,
                      help=helpmsgConfigFile ,)

  helpmsgConfigDir = '''Use the -d to add directory path for the config files. EX: /home/ubuntu/configs
                        Full Example of command: python2 migrate_sftp_data.py -c job_configs.yaml -d configs/ '''
  parser.add_option('-d', '--configdir',
                      action='store',
                      dest='configDir',
                      default=None,
                      help=helpmsgConfigDir ,)


  (options, args) = parser.parse_args()

  if  options.configFn is None:
    print "ERROR: You must specify a config yaml file!"
    print helpmsgConfigFile
    exit(1)
  elif options.configDir is None:
    print "ERROR: You must specify a directory path for the config files!"
    print helpmsgConfigDir
    exit(1)
  config_inputdir = None
  fieldConfigFile = None
  fieldConfigFile = options.configFn
  config_inputdir = options.configDir
  return fieldConfigFile, config_inputdir


def prepareChunk(chunk, stringsToCast):
  chunkhead = chunk.columns.values
  chunkhead_lower = [item.lower().replace("#", "") for item in chunkhead]
  dictNames = dict(zip(chunkhead, chunkhead_lower))
  chunk = chunk.rename(columns=dictNames)
  chunk = PandasUtils.fillNaWithBlank(chunk)
  chunkCols = list(chunk.columns)
  for string in stringsToCast:
    if string in chunkCols:
      chunk = PandasUtils.castColAsString(chunk, string)
  dictList = PandasUtils.convertDfToDictrows(chunk)
  return dictList

def postChunk(scrud, fnFullPath, chunkSize, encodingType, dataset_info, totalRows, stringsToCast):
  totalRows = 0
  for chunk in pd.read_csv(fnFullPath, chunksize=chunkSize, error_bad_lines=False, encoding=encodingType):
    dictList = prepareChunk(chunk, stringsToCast)
    try:  
      dataset_info = scrud.postDataToSocrata(dataset_info, dictList)
      dataset_info['row_id'] = 'blah'
      totalRows =  dataset_info['DatasetRecordsCnt'] + totalRows
    except Exception, e:
      print "ERROR: Could not upload data"
      print str(e)
  return totalRows


def loadFileChunks2(scrud, fnConfigObj, fnFullPath, chunkSize, encodingType, stringsToCast, replace=False):
  totalRows  = 0
  dataset_info = {'Socrata Dataset Name': fnConfigObj['dataset_name'], 'SrcRecordsCnt':chunkSize, 'DatasetRecordsCnt':0, 'fourXFour': fnConfigObj['fourXFour'], 'row_id': 'blah'}
  if replace:
    dataset_info = {'Socrata Dataset Name': fnConfigObj['dataset_name'], 'SrcRecordsCnt':chunkSize, 'DatasetRecordsCnt':0, 'fourXFour': fnConfigObj['fourXFour'], 'row_id': ''}
  try:
    totalRows = postChunk(scrud, fnFullPath, chunkSize, encodingType, dataset_info, totalRows, stringsToCast)
  except Exception, e:
    print str(e)
    print "Could not load file"
  return totalRows

def main():
  fieldConfigFile, config_inputdir = parse_opts()
  cI =  ConfigUtils(config_inputdir,fieldConfigFile)
  configItems = cI.getConfigs()
  lg = pyLogger(configItems)
  logger = lg.setConfig()
  dsse = JobStatusEmailerComposer(configItems, logger)
  logger.info("****************JOB START******************")
  sc = SocrataClient(config_inputdir, configItems, logger)
  client = sc.connectToSocrata()
  clientItems = sc.connectToSocrataConfigItems()
  scrud = SocrataCRUD(client, clientItems, configItems, logger)
  sQobj = SocrataQueries(clientItems, configItems, logger)
  #fileList = configItems['files'].keys()
  fileList = ['con_0025_purchasing_commodity_data.csv']
  fileListHistoric = [configItems['files'][fn]['historic'] for fn in fileList]
  jobResults = []
  '''
  sftp = SFTPUtils(configItems)
  print sftp
  try:
    print "**** Downloading Files From the SFTP **********"
    sftp.getFileList(fileList, configItems['remote_dir'], configItems['download_dir'])
    sftp.getFileList(fileListHistoric, configItems['remote_dir'], configItems['download_dir'])
  except Exception, e:
    print "ERROR: Could not download files from the SFTP"
    print str(e)
  sftp.closeSFTPConnection()
  '''
  for fn in fileList:
    if fn == 'con_0025_purchasing_commodity_data.csv': 
      print fn
      fnFullPath = configItems['download_dir']+fn
      fnConfigObj = configItems['files'][fn]
      fnFullPathHistoric = configItems['download_dir'] + configItems['files'][fn]['historic']
      encodingType = configItems['files'][fn]['encoding']
      chunkSize = configItems['chunkSize']
      if FileUtils.fileExists(fnFullPath) and FileUtils.fileExists(fnFullPathHistoric):
        print
        print "****"
        print fnFullPath
        print "******"
        print
        '''
        fnLHistorical = loadFileChunks2(scrud, fnConfigObj, fnFullPathHistoric, chunkSize, encodingType, configItems['string_number_fields'],  True)
        fnHistoricFileLen = SubProcessUtils.getFileLen( fnFullPathHistoric)
        print "*****************"
        print fnHistoricFileLen
        print "Loaded " + str(fnLHistorical) + "lines- Historic"
        print "******************"
        fnL = loadFileChunks2(scrud, fnConfigObj, fnFullPath, chunkSize, encodingType, configItems['string_number_fields'])
        fnLFileLen = SubProcessUtils.getFileLen(fnFullPath)
        print "*****************"
        print "Loaded " + str(fnL) + "lines- Historic"
        print "******************"

        totalFileSrcLen = (fnHistoricFileLen + fnLFileLen) -2 #make sure to remove the header rows
        print "*** total src lines***: " + str(totalFileSrcLen)
        print 
        '''
        #print "*** total loaded lines***: " + str(totalLoadLinesLen)
        totalFileSrcLen = '1627797'
        dataset_info = {'Socrata Dataset Name': fnConfigObj['dataset_name'], 'SrcRecordsCnt': totalFileSrcLen, 'DatasetRecordsCnt':0, 'fourXFour': fnConfigObj['fourXFour'], 'row_id': ''}
        dataset_info['DatasetRecordsCnt'] = scrud.getRowCnt(dataset_info)
        print dataset_info
        dataset_info  = scrud.checkCompleted(dataset_info)
        print dataset_info
        jobResults.append(dataset_info)
      else:
        print "***ERROR: Files doesn't exist for " + fn + "******"
        dataset_info = {'Socrata Dataset Name': fnConfigObj['dataset_name'], 'SrcRecordsCnt':0, 'DatasetRecordsCnt':-1, 'fourXFour': fnConfigObj['fourXFour'], 'row_id': ''}
        jobResults.append(dataset_info)
  if( len(jobResults) > 1 ):
    dsse.sendJobStatusEmail(jobResults)
  else:
    dataset_info = {'Socrata Dataset Name': fnConfigObj['dataset_name'], 'SrcRecordsCnt':0, 'DatasetRecordsCnt':-1, 'fourXFour': fnConfigObj['fourXFour'], 'row_id': ''}
    jobResults.append(dataset_info)
    dsse.sendJobStatusEmail(jobResults)



if __name__ == "__main__":
    main()
