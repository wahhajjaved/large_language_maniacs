import time
try:
  from graphtool.graphs.common_graphs import *
except:
  raise Exception( "Missing GraphTool" )

from DIRAC import S_OK, S_ERROR

def convertUTCToLocal( metadata, data ):
  """
  Convert epoch times from utc to local
  bucketsData must be a list of lists where each list contains
    - field 0: datetime
    - field 1: bucketLength
    - fields 2-n: numericalFields
  """
  for mF in ( 'starttime', 'endtime' ):
    if mF in metadata:
      metadata[ mF ] = metadata[ mF ] - time.altzone
  for kF in data:
    convertedData = {}
    for iP in data[ kF ]:
      convertedData[ iP - time.altzone ] = data[kF][iP]
    data[kF] = convertedData
  return metadata, data

def alignToGranularity( metadata ):
  if 'span' in metadata:
    granularity = metadata[ 'span' ]
    if 'starttime' in metadata:
      metadata[ 'starttime' ] = metadata[ 'starttime' ] - metadata[ 'starttime' ] % granularity
    if 'endtime' in metadata:
      metadata[ 'endtime' ] = metadata[ 'endtime' ] - metadata[ 'endtime' ] % granularity + granularity

class TimeBarGraph( TimeGraph, BarGraph ):
  pass

class TimeStackedBarGraph( TimeGraph, StackedBarGraph ):
  pass

def generateTimedStackedBarPlot( fileName, data, metadata ):
  try:
    fn = file( fileName, "wb" )
  except:
    return S_ERROR( "Can't open %s" % filename )
  if not data:
    return S_ERROR( "No data for that selection" )
  metadata, data = convertUTCToLocal( metadata, data )
  alignToGranularity( metadata )
  plotter = TimeStackedBarGraph()
  plotter( data, fn, metadata )
  fn.close()
  return S_OK()

def generateQualityPlot( fileName, data, metadata ):
  try:
    fn = file( fileName, "wb" )
  except:
    return S_ERROR( "Can't open %s" % filename )
  if not data:
    return S_ERROR( "No data for that selection" )
  plotter = QualityMap()
  metadata, data = convertUTCToLocal( metadata, data )
  alignToGranularity( metadata )
  plotter( data, fn, metadata )
  fn.close()
  return S_OK()

def generateCumulativePlot( fileName, data, metadata ):
  try:
    fn = file( fileName, "wb" )
  except:
    return S_ERROR( "Can't open %s" % filename )
  if 'is_cumulative' not in metadata:
    metadata[ 'is_cumulative' ] = True
  if not data:
    return S_ERROR( "No data for that selection" )
  plotter = CumulativeGraph()
  metadata, data = convertUTCToLocal( metadata, data )
  alignToGranularity( metadata )
  plotter( data, fn, metadata )
  fn.close()
  return S_OK()