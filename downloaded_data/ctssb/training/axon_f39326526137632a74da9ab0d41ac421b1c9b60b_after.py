#  This software and supporting documentation are distributed by
#      Institut Federatif de Recherche 49
#      CEA/NeuroSpin, Batiment 145,
#      91191 Gif-sur-Yvette cedex
#      France
#
# This software is governed by the CeCILL license version 2 under
# French law and abiding by the rules of distribution of free software.
# You can  use, modify and/or redistribute the software under the 
# terms of the CeCILL license version 2 as circulated by CEA, CNRS
# and INRIA at the following URL "http://www.cecill.info". 
#
# As a counterpart to the access to the source code and  rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty  and the software's author,  the holder of the
# economic rights,  and the successive licensors  have only  limited
# liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading,  using,  modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean  that it is complicated to manipulate,  and  that  also
# therefore means  that it is reserved for developers  and  experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systems and/or 
# data to be ensured and,  more generally, to use and operate it in the 
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license version 2 and that you accept its terms.

from brainvisa.processes import *
from brainvisa.validation import ValidationError
from brainvisa.configuration import mpegConfig
import os, re, math
from brainvisa.tools import aimsGlobals

name = 'ffmpeg MPEG encoder'
userLevel = 2

def validation():
  if 'ffmpeg' not in mpegConfig.encoders \
      and 'avconv' not in mpegConfig.encoders:
    raise ValidationError( _t_( 'ffmpeg and avconv not present' ) )


def codecs():
  c = mpegConfig.codecs.get( 'ffmpeg' )
  if c is not None:
    return c
  c = mpegConfig.codecs.get( 'avconv' )
  if c is not None:
    return c
  return {}


signature = Signature(
  'images', ListOf( ReadDiskItem( '2D Image', 'aims Image Formats',
                                  ignoreAttributes=1 ) ),
  'animation', WriteDiskItem( 'MPEG film', mpegConfig.mpegFormats ),
  'encoding', Choice( *codecs() ),
  'quality', Integer(), 
  'framesPerSecond', Integer(), 
  'passes', Choice( 1, 2 ), 
)


def initialization( self ):
  self.quality = 75
  self.framesPerSecond = 25
  self.passes = 1
  for c in ( 'h264', 'mpeg4', 'msmpeg4' ):
    if c in codecs():
      self.encoding = c
      break
  if self.encoding is None and len( codecs() ) > 0:
    self.encoding = codecs()[0]


def execution( self, context ):
  if len( self.images ) == 0:
    raise RuntimeError( 'No image selected' )
  if 'ffmpeg' in mpegConfig.encoders:
    encoder = 'ffmpeg'
  else:
    encoder = 'avconv'

  attrs = aimsGlobals.aimsVolumeAttributes( self.images[ 0 ], forceFormat=1 )
  # context.write( attrs )
  dims = attrs[ 'volume_dimension' ]
  vs = attrs[ 'voxel_size' ]
  width = float( dims[0] * vs[0] )
  height = float( dims[1] * vs[1] )
  aspect = width / height
  # bps = self.quality*10
  qscale = int( ( 100 - self.quality ) * 0.3 + 1 )

  # determine filanemes pattern
  numre = re.compile( '(.*[^0-9])([0-9]+)$' )
  m = numre.match( os.path.basename( self.images[0].fullName() ) )
  pat = ''
  ext = self.images[0].fullPath()[ len( self.images[0].fullName() ) : ]
  if m:
    sp = m.span(2)
    dirn = os.path.dirname( self.images[0].fullName() )
    pat = os.path.join( dirn, m.group(1) + '%' + str(sp[1]-sp[0]) + 'd' + ext )
    # context.write( 'pattern: ', pat )
    for x in self.images[1:]:
      m2 = numre.match( os.path.basename( x.fullName() ) )
      if not m2 or m2.group(1) != m.group(1) or m2.span(2) != sp \
             or os.path.basename( self.images[0].fullPath() )[ sp[1]: ] != ext:
        pat = ''
        msg = _t_( 'ffmpeg/avconv can ony handle a series of homogen, '
                   'numbered image filenames. Image %s breaks the rule' ) \
          % x.fullPath()
        break

  if pat:
    # check if the pattern only includes theimages we want
    imnames = map( lambda x: os.path.basename( x.fullPath() ), self.images )
    # context.write( imnames )
    d = os.listdir( dirn )
    n = len( ext )
    for x in d:
      if x.endswith( ext ) and x not in imnames:
        m2 = numre.match( os.path.basename( x[:-n] ) )
        if m2 and m2.group(1) == m.group(1) and m2.span(2) == sp:
          pat = ''
          msg = _t_( 'ffmpeg/avconv can ony handle a series of homogen, '
                     'numbered image filenames. There are additional files '
                     'in the images directory that would interfere with the '
                     'pattern: %s prevents if from working' ) % x
          break
  if pat:
    im = [ pat ]
  else:
    context.write( _t_( 'Images have to be copied for the following reason:' )\
                   + '\n', msg )
    tmpdir = context.temporary( 'Directory' )
    td = tmpdir.fullPath()
    inum = 0
    snum = int( math.ceil( math.log10( len( self.images ) + 1 ) ) )
    for x in self.images:
      if not x.fullPath().endswith( ext ):
        raise RuntimeError( _t_( 'all images must have the same format: %s '
                                 'has not the expected extension %s' ) \
                            % x % ext )
      ofile = os.path.join( td, ('img%0' + str( snum ) + 'd' + ext ) % inum )
      if platform == 'windows':
        shutil.copyfile( x.fullPath(), ofile )
      else:
        # cheaper solution on unix
        os.symlink( x.fullPath(), ofile )
      inum += 1
    context.write( 'copy done' )
    im = [ os.path.join( td, 'img%' + str( snum ) + 'd' + ext ) ]

  #im = map( lambda x: x.fullPath(), self.images )
  passlog = context.temporary( 'log file' )
  cmd = [ encoder ]
  for x in im:
    cmd += [ '-i', x ]
  cmd += [ '-r', str( self.framesPerSecond ), 
           #'-hq', # this options seems to have disapeared
           # '-b', str( bps ),
           '-qscale', str( qscale ),
           '-aspect', str( aspect ), 
           '-vcodec', self.encoding, 
           '-pass', '1', 
           '-passlogfile', passlog, 
           self.animation.fullPath(), 
           ]
  if self.encoding == 'msmpeg4':
    # force to be readable by MS Media player
    # see http://ffmpeg.sourceforge.net/compat.php
    cmd.insert( -5, '-vtag' )
    cmd.insert( -5, 'MP43' )
  context.write( cmd )
  if os.path.exists( self.animation.fullPath() ):
    # ffmpeg doesn't overwrite existing files
    os.unlink( self.animation.fullPath() )
  context.system( *cmd )
  if self.passes > 1:
    cmd[ -4 ] = '2'
    # print cmd
    context.system( *cmd )

