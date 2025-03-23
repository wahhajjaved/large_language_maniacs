#MenuTitle: Preflight Font
# -*- coding: utf-8 -*-
__doc__="""
Checks if everything is alright in the font.
"""

import GlyphsApp

Doc  = Glyphs.currentDocument
Font = Glyphs.font
Glyphs.clearLog()
Glyphs.showMacroWindow()

def headline( titleString ):
	print
	print titleString.upper(), "..."
	
def errMsg( glyphName, layerName, msg ):
	if layerName != "":
		print "- Glyph %s, Layer %s: %s." % ( glyphName, layerName, msg )
	elif glyphName != "":
		print "- Glyph %s: %s." % ( glyphName, msg )
	else:
		print "- %s." % ( msg )

def checkForOpenPaths( thisFont ):
	headline( "Checking for open paths" )

	for thisGlyph in thisFont.glyphs:
		for thisLayer in thisGlyph.layers:
			openPathsFound = 0
			
			for thisPath in thisLayer.paths:
				if not thisPath.closed:
					openPathsFound += 1
					
			if openPathsFound > 0:
				errMsg( thisGlyph.name, thisLayer.name, str( openPathsFound ) + " open path(s) found" )

def checkForPathDirections( thisFont ):
	headline( "Checking for path directions" )
	
	for thisGlyph in thisFont.glyphs:
		for thisLayer in thisGlyph.layers:
			firstPath = thisLayer.paths[0]
			
			if firstPath and firstPath.direction != -1:
				if len(thisLayer.paths) > 1:
					msg = "Bad path order or direction."
				else:
					msg = "Bad path direction."
				errMsg( thisGlyph.name, thisLayer.name, msg )

def checkForPointsOutOfBounds( thisFont ):
	headline( "Checking for nodes out of bounds" )
	
	for thisGlyph in thisFont.glyphs:
		for thisLayer in thisGlyph.layers:
			nodesOutOfBounds = 0
			anchorsOutOfBounds = []

			for thisPath in thisLayer.paths:
				for thisNode in thisPath.nodes:
					if abs( thisNode.x ) > 32766 or abs( thisNode.y ) > 32766:
						nodesOutOfBounds += 1
			for thisAnchor in thisLayer.anchors:
				if abs( thisAnchor.x ) > 32766 or abs( thisAnchor.y ) > 32766:
					anchorsOutOfBounds.append( thisAnchor.name )
			
			if nodesOutOfBounds:
				errMsg( thisGlyph.name, thisLayer.name, str( nodesOutOfBounds ) + " node(s) out of bounds" )
			
			if anchorsOutOfBounds:
				errMsg( thisGlyph.name, thisLayer.name, str( len( anchorsOutOfBounds )) + " anchor(s) out of bounds ('" + "', '".join( anchorsOutOfBounds ) + "')" )
				
def checkForIllegalGlyphNames( thisFont ):
	headline( "Checking for illegal glyph names" )
	
	glyphNames = [ x.name for x in thisFont.glyphs ]
	legalFirstChar = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
	legalRestChars = "1234567890-_."
	
	for thisName in glyphNames:
		firstChar = thisName[0]
		if firstChar not in legalFirstChar:
			if firstChar == "_":
				if thisFont.glyphs[thisName].export:
					errMsg( thisName, "", "glyphs starting with underscore must be invisible: %s " % thisName )
			elif thisName != ".notdef":
				errMsg( thisName, "", "first character in glyph name ('" + firstChar + "') must be a letter (A-Z or a-z)" )
		
		illegalChars = 0
		for thisChar in thisName:
			if thisChar not in legalFirstChar and thisChar not in legalRestChars:
				illegalChars += 1
		if illegalChars:
			errMsg( thisName, "", "glyph name contains " + str( illegalChars ) + " illegal character(s)")
			
		nameCount = glyphNames.count( thisName )
		if nameCount != 1:
			errMsg( thisName, "", "glyph name must be unique, but appears " + str( nameCount ) + " times in font")
		
		if len( thisName ) > 109:
			errMsg( thisName, "", "glyph name is too long")
			

def checkForFontNames( thisFont ):
	headline( "Checking font info and instances" )
	
	# font
	
	thisName = thisFont.familyName
	legalChars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890-_. "
	illegalChars = []
	
	for thisChar in thisName:
		if thisChar not in legalChars:
			illegalChars.append( thisChar )
	if illegalChars:
		errMsg( "", "", "Font name '" + thisName + "' contains " + str( len( illegalChars ) ) + " problematic character(s): " + ", ".join( illegalChars ))
	
	checkURLs = [[thisFont.manufacturerURL, "Manufacturer"], [thisFont.designerURL, "Designer"]]
	for checkURL in checkURLs:
		if checkURL[0] != None and checkURL[0] != "" and checkURL[0][:7] != "http://":
			errMsg( "", "", checkURL[1] + " URL does not start with 'http://': '" + checkURL[0] + "'" )
			
	# instances
	
	allInstances = thisFont.instances
	instanceNames = [ x.name for x in allInstances ]
	
	for thisInstanceName in instanceNames:
		if instanceNames.count( thisInstanceName ) > 1:
			errMsg( "", "", "Instance name '" + thisInstanceName + "' is used more than once" )
		
		illegalChars = []
		
		for thisChar in thisInstanceName:
			if thisChar not in legalChars:
				illegalChars.append( thisChar )
		if illegalChars:
			errMsg( "", "", "Instance name '" + thisInstanceName + "' contains " + str( len( illegalChars ) ) + " problematic character(s): " + ", ".join( illegalChars ))
		
	boldStyles = [ x.name for x in allInstances if x.isBold ]
	boldCount = len( boldStyles )
	if boldCount > 1:
		errMsg( "", "", "Not more than one instance should employ the Bold bit, but " + str( boldCount ) + " do: " + ", ".join( boldStyles ) )
		
	weightWidths = [ str( x.weight ) + " " + str( x.width ) for x in allInstances ]
	for thisWeight in weightWidths:
		if weightWidths.count( thisWeight ) > 1:
			errMsg( "", "", "Warning: weight/width combo '" + thisWeight + "' appears more than once in instances")
	
	interpolations = [ str( x.weightValue ) + "/" + str( x.widthValue ) for x in allInstances ]
	for thisInterpolation in interpolations:
		if interpolations.count( thisInterpolation ) > 1:
			errMsg( "", "", "Warning: weight/width interpolation '" + thisInterpolation + "' appears more than once in instances")

	linkedStyles = [ [x.linkStyle, x.name] for x in allInstances if not x.isItalic and x.linkStyle not in instanceNames + [""] ]
	for thisCase in linkedStyles:
		errMsg( "", "", "Warning: '" + thisCase[0] + "' is referenced as linked style in '" + thisCase[1] + "' but not among available instances")

	linkedStyles = [ [x.linkStyle, x.name] for x in allInstances if not x.isItalic and not x.isBold and x.linkStyle != "" ]
	for thisCase in linkedStyles:
		errMsg( "", "", "Warning: '" + thisCase[0] + "' is referenced as linked style in '" + thisCase[1] + "' but there is no Bold or Italic bit set")

def checkStandardNames( thisFont ):
	headline( "Checking for naming convention" )
	
	allGlyphs = thisFont.glyphs
	listOfUnicodes = [ (g.name, g.unicode) for g in allGlyphs if g.unicode != None ]

	for thisTuple in listOfUnicodes:
		glyphName = thisTuple[0]
		unicodeValue = thisTuple[1]
		if len( unicodeValue ) == 4:
			legacyName = "uni%s" % unicodeValue
		elif len( unicodeValue ) == 5:
			legacyName = "u%s" % unicodeValue
	
		try:
			calculatedNiceName = GSGlyphsInfo.niceGlyphNameForName_( legacyName ) # older API
		except:
			calculatedNiceName = Glyphs.glyphInfoForName( legacyName ).name
			
		if glyphName != calculatedNiceName:
			errMsg( glyphName, "", "Should be called %s (Unicode: %s)." % ( calculatedNiceName, unicodeValue ) )
	
def checkUnicode( thisFont ):
	headline( "Checking Unicodes" )
	
	allGlyphs = thisFont.glyphs
	glyphsWithoutUnicodes = [ g.name for g in allGlyphs if g.unicode == None ]
	listOfUnicodes = [ (g.name, g.unicode) for g in allGlyphs if g.unicode != None ]
	numberOfGlyphs = len( listOfUnicodes )

	for thisGlyphName in glyphsWithoutUnicodes:
		pass
		#errMsg( thisGlyphName, "", "Warning: No Unicode value set" )
	
	for i in range( numberOfGlyphs - 1 ):
		firstGlyph = listOfUnicodes[i]
		
		for j in range( i+1, numberOfGlyphs ):
			secondGlyph = listOfUnicodes[j]
			
			if firstGlyph[1] == secondGlyph[1]:
				errMsg( "%s & %s" % ( firstGlyph[0], secondGlyph[0] ), "", "Both glyphs carry same Unicode value %s" % ( firstGlyph[1] ) )

checkForFontNames( Font )
checkForOpenPaths( Font )
checkForPathDirections( Font )
checkForPointsOutOfBounds( Font )
checkForIllegalGlyphNames( Font )
checkStandardNames( Font )
checkUnicode( Font )
