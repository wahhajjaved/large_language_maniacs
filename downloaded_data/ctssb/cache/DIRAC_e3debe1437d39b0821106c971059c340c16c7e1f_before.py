from DIRAC import S_OK, S_ERROR
from DIRAC.ConfigurationSystem.Client.CFG import CFG
from DIRAC.Core.Utilities import List

def loadJDLAsCFG( jdl ):
  """
  Load a JDL as CFG
  """
  def cleanValue( value ):
    value = value.strip()
    if value[0] == '"':
      entries = []
      iPos = 1
      current = ""
      state = "in"
      while iPos < len( value ):
        if value[ iPos ] == '"':
          if state == "in":
            entries.append( current )
            current = ""
            state = "out"
          elif state == "out":
            current = current.strip()
            if current not in ( ",", ):
              return S_ERROR( "value seems a list but is not separated in commas" )
            current = ""
            state = "in"
        else:
          current += value[ iPos ]
        iPos += 1
      if state == "in":
        return S_ERROR( 'value is opened with " but is not closed' )
      return S_OK( ", ".join ( entries ) )
    else:
      return S_OK( value )

  def assignValue( key, value, cfg ):
    key = key.strip()
    if len( key ) == 0:
      return S_ERROR( "Invalid key name" )
    value = value.strip()
    if not value:
      return S_ERROR( "No value for key %s" % key)
    if value[0] == "{":
      if value[-1 ] != "}":
        return S_ERROR( "Value '%s' seems a list but does not end in '}'" % ( value ) )
      valList = List.fromChar( value[1:-1] )
      for i in range( len( valList ) ):
        result = cleanValue( valList[i] )
        if not result[ 'OK' ]:
          return S_ERROR( "Var %s : %s" % ( key, result[ 'Message' ] ) )
        valList[i] = result[ 'Value' ]
        if valList[ i ] == None:
          return S_ERROR( "List value '%s' seems invalid for item %s" % ( value, i ) )
      value = ", ".join( valList )
    else:
      result = cleanValue( value )
      if not result[ 'OK' ]:
        return S_ERROR( "Var %s : %s" % ( key, result[ 'Message' ] ) )
      nV = result[ 'Value' ]
      if nV == None:
        return S_ERROR( "Value '%s seems invalid" % ( value ) )
      value = nV
    cfg.setOption( key, value )
    return S_OK()

  if jdl[ 0 ] == "[":
    iPos = 1
  else:
    iPos = 0
  key = ""
  value = ""
  action = "key"
  insideLiteral = False
  cfg = CFG()
  while iPos < len( jdl ):
    c = jdl[ iPos ]
    if c == ";" and not insideLiteral:
      if key.strip():
        result = assignValue( key, value, cfg )
        if not result[ 'OK' ]:
          return result
      key = ""
      value = ""
      action = "key"
    elif c == "[" and not insideLiteral:
      key = key.strip()
      if not key:
        return S_ERROR( "Invalid key" )
      if value.strip():
        return S_ERROR( "Key %s seems to have a value and open a sub JDL at the same time" % key )
      result = loadJDLAsCFG( jdl[ iPos: ] )
      if not result[ 'OK' ]:
        return result
      subCfg, subPos = result[ 'Value' ]
      cfg.createNewSection( key, contents = subCfg )
      key = ""
      value = ""
      action = "key"
      insideLiteral = False
      iPos += subPos
    elif c == "=" and not insideLiteral:
      if action == "key":
        action = "value"
        insideLiteral = False
      else:
        value += c
    elif c == "]" and not insideLiteral:
      key = key.strip()
      if len( key ) > 0:
        result = assignValue( key, value, cfg )
        if not result[ 'OK' ]:
          return result
      return S_OK( ( cfg, iPos ) )
    else:
      if action == "key":
        key += c
      else:
        value += c
        if c == '"':
          insideLiteral = not insideLiteral
    iPos += 1

  return S_OK( ( cfg, iPos ) )

def dumpCFGAsJDL( cfg, level = 1, tab = "  " ):
  indent = tab * level
  contents = [ "%s[" % ( tab * ( level - 1 ) ) ]
  sections = cfg.listSections()

  for key in cfg:
    if key in sections:
      contents.append( "%s%s =" % ( indent, key ) )
      contents.append( "%s;" % dumpCFGAsJDL( cfg[ key ], level + 1, tab ) )
    else:
      val = List.fromChar( cfg[ key ] )
      if len( val ) < 2:
        v = cfg[ key ]
        try:
          d = float( v )
          contents.append( '%s%s = %s;' % ( tab*level, key, v ) )
        except:
          contents.append( '%s%s = "%s";' % ( tab*level, key, v ) )
      else:
        contents.append( "%s%s =" % ( indent, key ) )
        contents.append( "%s{" % indent )
        for iPos in range( len( val ) ):
          try:
            d = float( val[iPos] )
          except:
            val[ iPos ] = '"%s"' % val[ iPos ]
        contents.append( ",\n".join( [ '%s%s' % ( tab * (level +1 ), v ) for v in val ] ) )
        contents.append( "%s};" % indent )
  contents.append( "%s]" % ( tab * ( level - 1 ) ) )
  return "\n".join( contents )