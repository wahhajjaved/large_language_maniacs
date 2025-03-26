# -*- encoding: utf-8 -*-

class Panel( object ):
	def __init__( self, name, tag="div",data=None ):
		self.name = name
		self.tag = tag
		self.data = None
		self.panels = list()
	
	def is_terminal( self ):
		if len( self.panels ) == 0:
			return True
		else:
			return False
	
	def add_panel( self, panel ):
		self.panels.append( panel )
	
	def load( self, data ):
		self.data = data
	
	def load_from_file( self, filename ):
		with open( filename ) as f:
			self.data = f.readlines()[0]		
	
	def render( self ):
		output = "<%s id='%s'>\n" % ( self.tag, self.name )
		if self.is_terminal():
			output += "%s\n</%s>\n" % ( self.data, self.tag )
		else:
			for p in self.panels:
				output += p.render()
			output += "</%s>\n" % self.tag
		return output