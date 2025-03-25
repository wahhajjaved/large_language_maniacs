from pypy.rpython.rctypes.tool import ctypes_platform
from pypy.rpython.rctypes.tool.libc import libc
import pypy.rpython.rctypes.implementation # this defines rctypes magic
from pypy.rpython.rctypes.aerrno import geterrno
from pypy.interpreter.error import OperationError
from pypy.interpreter.baseobjspace import W_Root, ObjSpace, Wrappable
from pypy.interpreter.typedef import TypeDef, GetSetProperty
from pypy.interpreter.gateway import interp2app
from ctypes import *
import ctypes.util
import sys

from bzlib import bz_stream, BZFILE, FILE
from fileobject import PyFileObject

libbz2 = cdll.LoadLibrary(ctypes.util.find_library("bz2"))

c_void = None

class CConfig:
    _header_ = """
    #include <stdio.h>
    #include <sys/types.h>
    #include <bzlib.h>
    """
    off_t = ctypes_platform.SimpleType("off_t", c_longlong)
    size_t = ctypes_platform.SimpleType("size_t", c_ulong)
    BUFSIZ = ctypes_platform.ConstantInteger("BUFSIZ")
    SEEK_SET = ctypes_platform.ConstantInteger("SEEK_SET")

constants = {}
constant_names = ['BZ_RUN', 'BZ_FLUSH', 'BZ_FINISH', 'BZ_OK',
    'BZ_RUN_OK', 'BZ_FLUSH_OK', 'BZ_FINISH_OK', 'BZ_STREAM_END',
    'BZ_SEQUENCE_ERROR', 'BZ_PARAM_ERROR', 'BZ_MEM_ERROR', 'BZ_DATA_ERROR',
    'BZ_DATA_ERROR_MAGIC', 'BZ_IO_ERROR', 'BZ_UNEXPECTED_EOF',
    'BZ_OUTBUFF_FULL', 'BZ_CONFIG_ERROR']
for name in constant_names:
    setattr(CConfig, name, ctypes_platform.DefinedConstantInteger(name))
    
class cConfig:
    pass
cConfig.__dict__.update(ctypes_platform.configure(CConfig))

for name in constant_names:
    value = getattr(cConfig, name)
    if value is not None:
        constants[name] = value
locals().update(constants)

off_t = cConfig.off_t
BUFSIZ = cConfig.BUFSIZ
SEEK_SET = cConfig.SEEK_SET
BZ_OK = cConfig.BZ_OK
BZ_STREAM_END = cConfig.BZ_STREAM_END
BZ_CONFIG_ERROR = cConfig.BZ_CONFIG_ERROR
BZ_PARAM_ERROR = cConfig.BZ_PARAM_ERROR
BZ_DATA_ERROR = cConfig.BZ_DATA_ERROR
BZ_DATA_ERROR_MAGIC = cConfig.BZ_DATA_ERROR_MAGIC
BZ_IO_ERROR = cConfig.BZ_IO_ERROR
BZ_MEM_ERROR = cConfig.BZ_MEM_ERROR
BZ_UNEXPECTED_EOF = cConfig.BZ_UNEXPECTED_EOF
BZ_SEQUENCE_ERROR = cConfig.BZ_SEQUENCE_ERROR

# modes
MODE_CLOSED = 0
MODE_READ = 1
MODE_READ_EOF = 2
MODE_WRITE = 3

# bits in f_newlinetypes
NEWLINE_UNKNOWN = 0 # No newline seen, yet
NEWLINE_CR = 1 # \r newline seen
NEWLINE_LF = 2 # \n newline seen
NEWLINE_CRLF = 4 # \r\n newline seen

if BUFSIZ < 8192:
    SMALLCHUNK = 8192
else:
    SMALLCHUNK = BUFSIZ
    
if sizeof(c_int) > 4:
    BIGCHUNK = 512 * 32
else:
    BIGCHUNK = 512 * 1024
    
MAXINT = sys.maxint

pythonapi.PyFile_FromString.argtypes = [c_char_p, c_char_p]
pythonapi.PyFile_FromString.restype = POINTER(PyFileObject)
pythonapi.PyFile_SetBufSize.argtypes = [POINTER(PyFileObject), c_int]
pythonapi.PyFile_SetBufSize.restype = c_void
pythonapi.PyFile_AsFile.argtypes = [POINTER(PyFileObject)]
pythonapi.PyFile_AsFile.restype = POINTER(FILE)
pythonapi.PyMem_Free.argtypes = [c_char_p]
pythonapi.PyMem_Free.restype = c_void

libbz2.BZ2_bzReadOpen.argtypes = [POINTER(c_int), POINTER(FILE), c_int,
    c_int, c_void_p, c_int]
libbz2.BZ2_bzReadOpen.restype = POINTER(BZFILE)
libbz2.BZ2_bzWriteOpen.argtypes = [POINTER(c_int), POINTER(FILE), c_int,
    c_int, c_int]
libbz2.BZ2_bzWriteOpen.restype = POINTER(BZFILE)
libbz2.BZ2_bzReadClose.argtypes = [POINTER(c_int), POINTER(BZFILE)]
libbz2.BZ2_bzReadClose.restype = c_void
libbz2.BZ2_bzWriteClose.argtypes = [POINTER(c_int), POINTER(BZFILE),
    c_int, POINTER(c_uint), POINTER(c_uint)]
libbz2.BZ2_bzWriteClose.restype = c_void
libbz2.BZ2_bzRead.argtypes = [POINTER(c_int), POINTER(BZFILE), c_char_p, c_int]
libbz2.BZ2_bzRead.restype = c_int

libc.strerror.restype = c_char_p
libc.strerror.argtypes = [c_int]
libc.fclose.argtypes = [POINTER(FILE)]
libc.fclose.restype = c_int
libc.fseek.argtypes = [POINTER(FILE), c_int, c_int]
libc.fseek.restype = c_int

def _get_error_msg():
    errno = geterrno()
    return libc.strerror(errno)

def _catch_bz2_error(space, bzerror):
    if BZ_CONFIG_ERROR and bzerror == BZ_CONFIG_ERROR:
        raise OperationError(space.w_SystemError,
            space.wrap("the bz2 library was not compiled correctly"))
    if bzerror == BZ_PARAM_ERROR:
        raise OperationError(space.w_SystemError,
            space.wrap("the bz2 library has received wrong parameters"))
    elif bzerror == BZ_MEM_ERROR:
        raise OperationError(space.w_MemoryError, space.wrap(""))
    elif bzerror in (BZ_DATA_ERROR, BZ_DATA_ERROR_MAGIC):
        raise OperationError(space.w_IOError, space.wrap("invalid data stream"))
    elif bzerror == BZ_IO_ERROR:
        raise OperationError(space.w_IOError, space.wrap("unknown IO error"))
    elif bzerror == BZ_UNEXPECTED_EOF:
        raise OperationError(space.w_EOFError,
            space.wrap(
                "compressed file ended before the logical end-of-stream was detected"))
    elif bzerror == BZ_SEQUENCE_ERROR:
        raise OperationError(space.w_RuntimeError,
            space.wrap("wrong sequence of bz2 library commands used"))

def _drop_readahead(obj):
    if obj.f_buf:
        pythonapi.PyMem_Free(obj.f_buf)
        obj.f_buf = c_char_p()
        
def _univ_newline_read(bzerror, stream, buf, n, obj):
    dst = buf
    
    if not obj.f_univ_newline:
        nread = libbz2.BZ2_bzRead(byref(bzerror), stream, buf, n)
        return nread, buf
        
    newlinetypes = obj.f_newlinetypes
    skipnextlf = obj.f_skipnextlf
    
    while n:
        src = dst
        
        nread = libbz2.BZ2_bzRead(byref(bzerror), stream, buf, n)
        n -= nread # assuming 1 byte out for each in; will adjust
        shortread = n != 0 # True iff EOF or error
        
        # needed to operate with "pointers"
        src_lst = list(src.value)
        src_pos = 0
        dst_lst = list(dst.value)
        dst_pos = 0
        while nread:
            nread -= 1
                    
            c = src_lst[src_pos]
            src_pos += 1
            
            if c == '\r':
                # save as LF and set flag to skip next LF.
                dst_lst[dst_pos] = '\n'
                dst_pos += 1
                skipnextlf = True
            elif skipnextlf and c == '\n':
                # skip LF, and remember we saw CR LF.
                skipnextlf = False
                newlinetypes |= NEWLINE_CRLF
                n += 1
            else:
                # normal char to be stored in buffer.  Also
                # update the newlinetypes flag if either this
                # is an LF or the previous char was a CR.
                if c == '\n':
                    newlinetypes |= NEWLINE_LF
                elif skipnextlf:
                    newlinetypes |= NEWLINE_CR
                
                dst_lst[dst_pos] = c
                dst_pos += 1
                
                skipnextlf = False
        
        if shortread:
            # if this is EOF, update type flags.
            if skipnextlf and (bzerror == BZ_STREAM_END):
                newlinetypes |= NEWLINE_CR
            break
    
    obj.f_newlinetypes = newlinetypes
    obj.f_skipnextlf = skipnextlf
    
    data = "".join(dst_lst)
    buf = create_string_buffer(len(data))
    for i, ch in enumerate(data):
        buf[i] = ch
    
    return dst_pos, buf
    
def _getline(space, obj, size):
    used_v_size = 0 # no. used slots in buffer
    increment = 0 # amount to increment the buffer
    bzerror = c_int()
    
    newlinetypes = obj.f_newlinetypes
    skipnextlf = obj.f_skipnextlf
    univ_newline = obj.f_univ_newline
    
    total_v_size = (100, size)[size > 0] # total no. of slots in buffer
    buf_lst = []
    buf_pos = 0
    
    end_pos = buf_pos + total_v_size
    
    ch = c_char()
    while True:
        if univ_newline:
            while True:
                libbz2.BZ2_bzRead(byref(bzerror), obj.fp, byref(ch), 1)
                obj.pos += 1
                if bzerror.value != BZ_OK or buf_pos == end_pos:
                    break
                
                if skipnextlf:
                    skipnextlf = False
                    if ch.value == '\n':
                        # Seeing a \n here with
                        # skipnextlf true means we saw a \r before.
                        newlinetypes |= NEWLINE_CRLF
                        libbz2.BZ2_bzRead(byref(bzerror), obj.fp, byref(ch), 1)
                        if bzerror.value != BZ_OK: break
                    else:
                        newlinetypes |= NEWLINE_CR
                
                if ch.value == '\r':
                    skipnextlf = True
                    ch.value = '\n'
                elif ch.value == '\n':
                    newlinetypes |= NEWLINE_LF
                buf_lst.append(ch.value)
                buf_pos += 1
                
                if ch.value == '\n': break
            if bzerror.value == BZ_STREAM_END and skipnextlf:
                newlinetypes |= NEWLINE_CR
        else: # if not universal newlines use the normal loop
            while True:
                libbz2.BZ2_bzRead(byref(bzerror), obj.fp, byref(ch), 1)
                obj.pos += 1
                buf_lst.append(ch.value)
                buf_pos += 1
                
                if not (bzerror == BZ_OK and ch.value != '\n' and buf_pos != end_pos):
                    break
        
        obj.f_newlinetypes = newlinetypes
        obj.f_skipnextlf = skipnextlf
        
        if bzerror.value == BZ_STREAM_END:
            obj.size = obj.pos
            obj.mode = MODE_READ_EOF
            break
        elif bzerror.value != BZ_OK:
            _catch_bz2_error(space, bzerror.value)
        
        if ch.value == '\n': break
        # must be because buf_pos == end_pos
        if size > 0:
            break
        
        used_v_size = total_v_size
        increment = total_v_size >> 2 # mild exponential growth
        total_v_size += increment
        
        if total_v_size > MAXINT:
            raise OperationError(space.w_OverflowError,
                space.wrap("line is longer than a Python string can hold"))
        
        buf_pos += used_v_size
        end_pos += total_v_size
    
    used_v_size = buf_pos
    if used_v_size != total_v_size:
        return "".join(buf_lst[:used_v_size])
    return "".join(buf_lst)

def _new_buffer_size(current_size):
    if current_size > SMALLCHUNK:
        # keep doubling until we reach BIGCHUNK
        # then keep adding BIGCHUNK
        if current_size <= BIGCHUNK:
            return current_size + current_size
        else:
            return current_size + BIGCHUNK
    return current_size + SMALLCHUNK
    
class _BZ2File(Wrappable):
    def __init__(self, space, filename, mode='r', buffering=-1, compresslevel=9):
        self.space = space
        
        self.f_buf = c_char_p() # allocated readahead buffer
        self.f_bufend = c_char_p() # points after last occupied position
        self.f_bufptr = c_char_p() # current buffer position
        
        self.f_softspace = 0 # flag used by print command
        
        self.f_univ_newline = False # handle any newline convention
        self.f_newlinetypes = 0 # types of newlines seen
        self.f_skipnextlf = 0 # skip next \n
        
        self.mode = 0
        self.pos = 0
        self.size = 0
        
        self._init_bz2file(filename, mode, buffering, compresslevel)        
    
    def _init_bz2file(self, filename, mode_, buffering, compresslevel):
        self.size = -1
        
        name = filename
        mode_char = ""
        mode_list = mode_
        
        if compresslevel < 1 or compresslevel > 9:
            raise OperationError(self.space.w_ValueError,
                self.space.wrap("compresslevel must be between 1 and 9"))
        
        for mode in mode_list:
            error = False
            
            if mode in ['r', 'w']:
                if mode_char:
                    error = True
                mode_char = mode
            elif mode == 'b':
                pass
            elif mode == 'U':
                self.f_univ_newline = True
            else:
                error = True
            
            if error:
                raise OperationError(self.space.w_ValueError,
                    self.space.wrap("invalid mode char %s" % mode))
        
        if mode_char == 0:
            mode_char = 'r'
        mode = ('wb', 'rb')[mode_char == 'r']
        
        # open the file and set the buffer
        try:
            f = pythonapi.PyFile_FromString(name, mode)
        except IOError:
            raise OperationError(self.space.w_IOError,
                self.space.wrap("cannot open file %s" % name))
        pythonapi.PyFile_SetBufSize(f, buffering)
        
        # store the FILE object
        self._file = pythonapi.PyFile_AsFile(f)
        
        bzerror = c_int()
        if mode_char == 'r':
            self.fp = libbz2.BZ2_bzReadOpen(byref(bzerror), self._file,
                0, 0, None, 0)
        else:
            self.fp = libbz2.BZ2_bzWriteOpen(byref(bzerror), self._file,
                compresslevel, 0, 0)
        
        if bzerror.value != BZ_OK:
            _catch_bz2_error(self.space, bzerror.value)
        
        self.mode = (MODE_WRITE, MODE_READ)[mode_char == 'r']
    
    def __del__(self):
        bzerror = c_int()
        
        if self.mode in (MODE_READ, MODE_READ_EOF):
            libbz2.BZ2_bzReadClose(byref(bzerror), self.fp)
        elif self.mode == MODE_WRITE:
            libbz2.BZ2_bzWriteClose(byref(bzerror), self.fp, 0, None, None)
            
        _drop_readahead(self)
        
    def _check_if_close(self):
        if self.mode == MODE_CLOSED:
            raise OperationError(self.space.w_ValueError,
                self.space.wrap("I/O operation on closed file"))
    
    def close(self):
        """close() -> None or (perhaps) an integer

        Close the file. Sets data attribute .closed to true. A closed file
        cannot be used for further I/O operations."""
        
        # this feature is not supported due to fclose():
        #   close() may be called more than once without error.
                
        bzerror = c_int(BZ_OK)
        
        if self.mode in (MODE_READ, MODE_READ_EOF):
            libbz2.BZ2_bzReadClose(byref(bzerror), self.fp)
        elif self.mode == MODE_WRITE:
            libbz2.BZ2_bzWriteClose(byref(bzerror), self.fp, 0, None, None)
        
        self.mode = MODE_CLOSED
        
        # close the underline file
        ret = libc.fclose(self._file)
        if ret != 0:
            raise OperationError(self.space.w_IOError,
                self.space.wrap(_get_error_msg()))
        
        if bzerror.value != BZ_OK:
            return _catch_bz2_error(self.space, bzerror.value)
        
        return ret
    close.unwrap_spec = ['self']
    
    def tell(self):
        """tell() -> int

        Return the current file position, an integer (may be a long integer)."""
        
        self._check_if_close()
        
        return self.space.wrap(self.pos)
    tell.unwrap_spec = ['self']
    
    def seek(self, offset, whence=0):
        """"seek(offset [, whence]) -> None
    
        Move to new file position. Argument offset is a byte count. Optional
        argument whence defaults to 0 (offset from start of file, offset
        should be >= 0); other values are 1 (move relative to current position,
        positive or negative), and 2 (move relative to end of file, usually
        negative, although many platforms allow seeking beyond the end of a file).
    
        Note that seeking of bz2 files is emulated, and depending on the parameters
        the operation may be extremely slow."""
        
        _drop_readahead(self)
        self._check_if_close()
        
        bufsize = SMALLCHUNK
        buf = create_string_buffer(bufsize)
        bytesread = 0
        bzerror = c_int()
        
        if self.mode not in (MODE_READ, MODE_READ_EOF):
            raise OperationError(self.space.w_IOError,
                self.space.wrap("seek works only while reading"))
        
        if whence == 2:
            if self.size == -1:
                while True:
                    chunksize, buf = _univ_newline_read(bzerror, self.fp, buf,
                        bufsize, self)
                    self.pos += chunksize
                    bytesread += chunksize
                    
                    if bzerror.value == BZ_STREAM_END:
                        break
                    elif bzerror.value != BZ_OK:
                        _catch_bz2_error(self.space, bzerror.value)
                    
                self.mode = MODE_READ_EOF
                self.size = self.pos
                bytesread = 0
            offset += self.size
        elif whence == 1:
            offset += self.pos
        
        # Before getting here, offset must be the absolute position the file
        # pointer should be set to.
        if offset >= self.pos:
            # we can move forward
            offset -= self.pos
        else:
            # we cannot move back, so rewind the stream
            libbz2.BZ2_bzReadClose(byref(bzerror), self.fp)
            if bzerror.value != BZ_OK:
                _catch_bz2_error(self.space, bzerror.value)
            
            ret = libc.fseek(self._file, 0, SEEK_SET)
            if ret != 0:
                raise OperationError(self.space.w_IOError,
                    self.space.wrap(_get_error_msg()))
            
            self.pos = 0
            self.fp = libbz2.BZ2_bzReadOpen(byref(bzerror), self._file,
                0, 0, None, 0)
            if bzerror.value != BZ_OK:
                _catch_bz2_error(self.space, bzerror.value)
            
            self.mode = MODE_READ
        
        if offset <= 0 or self.mode == MODE_READ_EOF:
            return
        
        # Before getting here, offset must be set to the number of bytes
        # to walk forward.
        while True:
            if (offset - bytesread) > bufsize:
                readsize = bufsize
            else:
                # offset might be wider that readsize, but the result
                # of the subtraction is bound by buffersize (see the
                # condition above). bufsize is 8192.
                readsize = offset - bytesread
            
            chunksize, buf = _univ_newline_read(bzerror, self.fp, buf,
                readsize, self)
            self.pos += chunksize
            bytesread += chunksize
            
            if bzerror.value == BZ_STREAM_END:
                self.size = self.pos
                self.mode = MODE_READ_EOF
                break
            elif bzerror.value != BZ_OK:
                _catch_bz2_error(self.space, bzerror.value)
            
            if bytesread == offset:
                break
    seek.unwrap_spec = ['self', int, int]
    
    def readline(self, size=-1):
        """readline([size]) -> string

        Return the next line from the file, as a string, retaining newline.
        A non-negative size argument will limit the maximum number of bytes to
        return (an incomplete line may be returned then). Return an empty
        string at EOF."""
        
        self._check_if_close()
        
        if self.mode == MODE_READ_EOF:
            return self.space.wrap("")
        elif not self.mode == MODE_READ:
            raise OperationError(self.space.w_IOError,
                self.space.wrap("file is not ready for reading"))
        
        if size == 0:
            return self.space.wrap("")
        else:
            size = (size, 0)[size < 0]
            return self.space.wrap(_getline(self.space, self, size))
    readline.unwrap_spec = ['self', int]
    
    def read(self, size=-1):
        """read([size]) -> string

        Read at most size uncompressed bytes, returned as a string. If the size
        argument is negative or omitted, read until EOF is reached."""
        
        self._check_if_close()
        
        if self.mode == MODE_READ_EOF:
            return self.space.wrap("")
        elif not self.mode == MODE_READ:
            raise OperationError(self.space.w_IOError,
                self.space.wrap("file is not ready for reading"))
        
        bufsize = (size, _new_buffer_size(0))[size < 0]
        
        if bufsize > MAXINT:
            raise OperationError(self.space.w_OverflowError,
                self.space.wrap(
                    "requested number of bytes is more than a Python string can hold"))
        
        bytesread = 0
        buf = create_string_buffer(bufsize)
        bzerror = c_int()
        while True:
            chunksize, buf = _univ_newline_read(bzerror, self.fp, buf,
                bufsize - bytesread, self)
            self.pos += chunksize
            bytesread += chunksize
            
            if bzerror.value == BZ_STREAM_END:
                self.size = self.pos
                self.mode = MODE_READ_EOF
                break
            elif bzerror.value != BZ_OK:
                _catch_bz2_error(self.space, bzerror.value)
            
            if size < 0:
                bufsize = _new_buffer_size(bufsize)
            else:
                break
        
        buf_lst = list(buf.value)
        if bytesread != bufsize:
            return self.space.wrap("".join(buf_lst[:bytesread]))
        return self.space.wrap("".join(buf_lst))
    read.unwrap_spec = ['self', int]
    
    # accessor for newlines property
    def fget_newlines(space, self):
        if self.f_newlinetypes == NEWLINE_UNKNOWN:
            return space.wrap(None)
        elif self.f_newlinetypes == NEWLINE_CR:
            return space.wrap('\r')
        elif self.f_newlinetypes == NEWLINE_LF:
            return space.wrap('\n')
        elif self.f_newlinetypes == NEWLINE_CR|NEWLINE_LF:
            return space.wrap(('\r', '\n'))
        elif self.f_newlinetypes == NEWLINE_CRLF:
            return space.wrap("\r\n")
        elif self.f_newlinetypes == NEWLINE_CR|NEWLINE_CRLF:
            return space.wrap(('\r', "\r\n"))
        elif self.f_newlinetypes == NEWLINE_LF|NEWLINE_CRLF:
            return space.wrap(('\n', "\r\n"))
        elif self.f_newlinetypes == NEWLINE_CR|NEWLINE_LF|NEWLINE_CRLF:
            return space.wrap(('\r', '\n', "\r\n"))
        else:
            raise OperationError(space.w_SystemError,
                space.wrap(
                    "Unknown newlines value 0x%d\n" % hex(self.f_newlinetypes)))

get_newlines = GetSetProperty(_BZ2File.fget_newlines, cls=_BZ2File)
_BZ2File.typedef = TypeDef("_BZ2File",
    close = interp2app(_BZ2File.close, unwrap_spec=_BZ2File.close.unwrap_spec),
    tell = interp2app(_BZ2File.tell, unwrap_spec=_BZ2File.tell.unwrap_spec),
    seek = interp2app(_BZ2File.seek, unwrap_spec=_BZ2File.seek.unwrap_spec),
    readline = interp2app(_BZ2File.readline,
        unwrap_spec=_BZ2File.readline.unwrap_spec),
    read = interp2app(_BZ2File.read, unwrap_spec=_BZ2File.read.unwrap_spec),
    newlines = get_newlines,
)

def BZ2File(space, filename, mode='r', buffering=-1, compresslevel=9):
    """BZ2File(name [, mode='r', buffering=0, compresslevel=9]) -> file object
    
    Open a bz2 file. The mode can be 'r' or 'w', for reading (default) or
    writing. When opened for writing, the file will be created if it doesn't
    exist, and truncated otherwise. If the buffering argument is given, 0 means
    unbuffered, and larger numbers specify the buffer size. If compresslevel
    is given, must be a number between 1 and 9.

    Add a 'U' to mode to open the file for input with universal newline
    support. Any line ending in the input file will be seen as a '\\n' in
    Python. Also, a file so opened gains the attribute 'newlines'; the value
    for this attribute is one of None (no newline read yet), '\\r', '\\n',
    '\\r\\n' or a tuple containing all the newline types seen. Universal
    newlines are available only when reading."""
    return _BZ2File(space, filename, mode, buffering, compresslevel)
BZ2File.unwrap_spec = [ObjSpace, str, str, int, int]

