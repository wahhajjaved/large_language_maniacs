import requests
import errors

import pdb

class LokingYQL(object):
  '''Yet another Python Yahoo! Query Language Wrapper
  '''
  default_url = 'https://query.yahooapis.com/v1/public/yql'	  
  
  def __init__(self, table=None, url=default_url, format='json'):
    self.url = url
    self.table = table
    self.format = format
    self._query = None # used to build query when using methods such as <select>, <insert>, ...
    self.diagnostics = True # Who knows, someone would like to turn it off

  def __repr__(self):
    '''Returns information on the current instance
    '''
    return "<url>: '{0}' - <table>: '{1}' -  <format> : '{2}' ".format(self.url, self.table, self.format)

  def payloadBuilder(self, query, format='json'):
    '''Build the payload'''
    payload = {
	'q' : query,
	'callback' : '', #This is not javascript
	'diagnostics' : self.diagnostics, # always true
	'format' : format
    }

    return payload

  def rawQuery(self, query, format='json', pretty=True):
    '''Executes a YQL query and returns a response
       >>>...
       >>> resp = yql.rawQuery('select * from weather.forecast where woeid=2502265')
       >>> 
    '''
    payload = self.payloadBuilder(query, format)
    response = self.executeQuery(payload)
    #if pretty :
    #  response = self.buildResponse(response)

    return response

  def executeQuery(self, payload):
    '''Execute the query and returns and response'''
    response = requests.get(self.url, params= payload)

    return response

  def clauseFormatter(self, cond):
    '''Formats conditions
       args is a list of ['column', 'operator', 'value']
    '''
    cond[2] = "'{0}'".format(cond[2])
    return ''.join(cond)
    
  def buildResponse(self, response):
    '''Try to return a pretty formatted response object
    '''
    try:
      r = response.json()
      result = r['query']['results']['table']
      response = {
        'num_result': len(result) if isinstance(result, list) else 0 ,
        'result': result
      }
    except Exception, e:
      print(e)
      return response.content
    return response

  def buildSelectQuery(conditions):
    '''Builds the query for the select method ''' 
    return query
  ######################################################
  #
  #                 ORM METHODS
  #
  #####################################################

  def use(self, url):
    '''Changes the data provider
       >>> yql.use('http://myserver.com/mytables.xml')
    '''
    self.url = url
    return self.url

  def select(self, table=None, items=[]):
    '''This method simulate a select on a table
    >>> yql.select('table')
    >>> yql.select('social.profile', ['guuid', 'givenName', 'gender'])
    '''
    try:
      self.table = table
      if not items:
        items = ['*']
      self._query = "select {1} from {0}".format(self.table, ','.join(items))
    except Exception, e:
      print(e)

    return self

  def where(self, *args):
    ''' This method simulates a where condition. Use as follow:
    >>>yql.select('mytable').where([('name', '=', 'alain'), ('location', '!=', 'paris')])
    '''
    if not self.table:
      raise errors.NoTableSelectedError('No Table Selected')

    clause = []
    self._query += ' where '
    for x in args:
      x = self.clauseFormatter(x)
      clause.append(x)

    self._query += ' and '.join(clause)
    
    payload = self.payloadBuilder(self._query)
    response = self.executeQuery(payload)

    return response

  ######################################################
  #
  #                     HELPERS
  #
  #####################################################

  def getGUID(self, username):
    '''Returns the guid of the username provided
       >>> guid = self.getGUID('josue_brunel')
       >>> guid
    '''
    response = self.select('yahoo.identity').where(['yid', '=', username])
    
    return response
    
  def showTables(self, format='json'):
    '''Return list of all avaible tables'''

    query = 'SHOW TABLES'
    payload = self.payloadBuilder(query, format) 	

    response = self.executeQuery(payload) 

    return response
