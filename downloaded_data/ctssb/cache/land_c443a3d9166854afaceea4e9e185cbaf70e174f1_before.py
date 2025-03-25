static import global stdio, stdlib, string
static import mem
import global allegro5/allegro5
import array, util

*** "ifndef" LAND_NO_COMPRESS
static import global zlib
*** "endif"

class LandBuffer:
    int size # reserved memory
    int n # number of bytes in the buffer
    char *buffer

class LandBufferAsFile:
    LandBuffer *landbuffer
    int pos
    int ungetc

*** "ifdef" LAND_MEMLOG

*** "undef" land_buffer_new
*** "undef" land_buffer_del
*** "undef" land_buffer_finish
*** "undef" land_buffer_read_from_file
*** "undef" land_buffer_split

LandBuffer *def land_buffer_new_memlog(char const *f, int l):
    LandBuffer *self = land_buffer_new()
    land_memory_add(self, "buffer", 1, f, l)
    return self

def land_buffer_del_memlog(LandBuffer *self, char const *f, int l):
    land_memory_remove(self, "buffer", 1, f, l)
    land_buffer_del(self)

char *def land_buffer_finish_memlog(LandBuffer *self, char const *f, int l):
    land_memory_remove(self, "buffer", 1, f, l)
    char *s = land_buffer_finish(self)
    
    # Give line number of finish call to returned memory block.
    land_memory_remove(s, "", 1, f, l)
    land_memory_add(s, "", strlen(s), f, l)
    return s

LandBuffer *def land_buffer_read_from_file_memlog(char const *filename, char const *f, int l):
    LandBuffer *self = land_buffer_read_from_file(filename)
    land_memory_add(self, "buffer", 1, f, l)
    return self

LandArray *def land_buffer_split_memlog(LandBuffer const *self, char delim, char const *f, int line):
    LandArray *a = land_array_new_memlog(f, line)
    int start = 0
    for int i = 0 while i < self->n with i++:
        if self->buffer[i] == delim:
            LandBuffer *l = land_buffer_new_memlog(f, line)
            land_buffer_add(l, self->buffer + start, i - start)
            land_array_add_memlog(a, l, f, line)
            start = i + 1
    LandBuffer *l = land_buffer_new_memlog(f, line)
    land_buffer_add(l, self->buffer + start, self->n - start)
    land_array_add_memlog(a, l, f, line)
    return a

*** "endif"

LandBuffer *def land_buffer_new():
    LandBuffer *self
    land_alloc(self)
    return self

LandBuffer *def land_buffer_copy(LandBuffer *other):
    LandBuffer *self
    land_alloc(self)
    land_buffer_add(self, other->buffer, other->n)
    return self

def land_buffer_del(LandBuffer *self):
    if self->buffer: land_free(self->buffer)
    land_free(self)

def land_buffer_insert(LandBuffer *self, int pos, char const *buffer, int n):
    self->n += n
    if self->n > self->size:
        if not self->size: self->size = 1
        while self->size < self->n:
            self->size *= 2
        self->buffer = land_realloc(self->buffer, self->size)
    memmove(self->buffer + pos + n, self->buffer + pos, self->n - n - pos)
    memcpy(self->buffer + pos, buffer, n)
    
def land_buffer_add(LandBuffer *self, char const *b, int n):
    land_buffer_insert(self, self->n, b, n)

def land_buffer_addf(LandBuffer *self, char const *format, ...):
    va_list args
    va_start(args, format)
    int n = vsnprintf(None, 0, format, args)
    va_end(args)
    if n < 0: n = 1023
    char s[n + 1]
    va_start(args, format)
    vsnprintf(s, n + 1, format, args)
    va_end(args)
    land_buffer_add(self, s, n)

def land_buffer_add_uint32_t(LandBuffer *self, uint32_t i):
    land_buffer_add_char(self, i & 255)
    land_buffer_add_char(self, (i >> 8) & 255)
    land_buffer_add_char(self, (i >> 16) & 255)
    land_buffer_add_char(self, (i >> 24) & 255)

uint32_t def land_buffer_get_uint32_t(LandBuffer *self, int pos):
    unsigned char *uc = (unsigned char *)self->buffer + pos
    uint32_t u = *(uc++)
    u += *(uc++) << 8
    u += *(uc++) << 16
    u += *(uc++) << 24
    return u

def land_buffer_add_float(LandBuffer *self, float f):
    uint32_t *i = (void *)&f
    land_buffer_add_uint32_t(self, *i)

def land_buffer_add_char(LandBuffer *self, char c):
    land_buffer_add(self, &c, 1)

def land_buffer_cat(LandBuffer *self, char const *string):
    land_buffer_add(self, string, strlen(string))

def land_buffer_clear(LandBuffer *self):
    """
    Clears the buffer (but keeps any memory allocation for speedy refilling).
    """
    self->n = 0

def land_buffer_crop(LandBuffer *self):
    """
    Make the buffer use up only the minimum required amount of memory.
    """
    self->buffer = land_realloc(self->buffer, self->n)
    self->size = self->n

char *def land_buffer_finish(LandBuffer *self):
    """
    Destroys the buffer, but returns a C-string constructed from it by appending
    a 0 character. You may not access the pointer you pass to this function
    anymore after it returns. Also, you have to make sure it does not already
    contain any 0 characters. When no longer needed, you should free the string
    with land_free.
    """
    char c[] = "";
    land_buffer_add(self, c, 1)
    char *s = self->buffer
    self->buffer = None
    land_buffer_del(self)
    return s

LandArray *def land_buffer_split(LandBuffer const *self, char delim):
    """
    Creates an array of buffers. If there are n occurences of character delim
    in the buffer, the array contains n + 1 entries. No buffer in the array
    contains the delim character.
    """
    LandArray *a = land_array_new()
    int start = 0
    for int i = 0 while i < self->n with i++:
        if self->buffer[i] == delim:
            LandBuffer *l = land_buffer_new()
            land_buffer_add(l, self->buffer + start, i - start)
            land_array_add(a, l)
            start = i + 1
    LandBuffer *l = land_buffer_new()
    land_buffer_add(l, self->buffer + start, self->n - start)
    land_array_add(a, l)
    return a

def land_buffer_strip_right(LandBuffer *self, char const *what):
    if self->n == 0: return
    int away = 0
    char *p = self->buffer + self->n
    while p > self->buffer:
        int c = land_utf8_char_back(&p);
        char const *q = what
        while 1:
            int d = land_utf8_char_const(&q)
            if not d:
                goto done
            if c == d:
                away++
                break
    label done
    self->n -= away

def land_buffer_strip_left(LandBuffer *self, char const *what):
    if self->n == 0: return
    int away = 0
    char *p = self->buffer
    while 1:
        label again
        int c = land_utf8_char(&p)
        if not c: break
        char const *q = what
        while 1:
            int d = land_utf8_char_const(&q)
            if not d: break
            if c == d:
                away++
                goto again
        break
    self->n -= away
    memmove(self->buffer, self->buffer + away, self->n)

def land_buffer_strip(LandBuffer *self, char const *what):
    land_buffer_strip_right(self, what)
    land_buffer_strip_left(self, what)

def land_buffer_write_to_file(LandBuffer *self, char const *filename):
    FILE *f = fopen(filename, "w")
    fwrite(self->buffer, 1, self->n, f)
    fclose(f)

int def land_buffer_rfind(LandBuffer *self, char c):
    if self->n == 0: return -1
    for int i = self->n - 1 while i >= 0 with i--:
        if self->buffer[i] == c: return i
    return -1

def land_buffer_set_length(LandBuffer *self, int n):
    self->n = n

def land_buffer_shorten(LandBuffer *self, int n):
    self->n -= n

LandBuffer *def land_buffer_read_from_file(char const *filename):
    """
    Read a buffer from the given file. If the file cannot be read, return None.
    """
    FILE *pf = fopen(filename, "r")
    if not pf:
        return None
    LandBuffer *self = land_buffer_new()
    while 1:
        char kb[16384]
        size_t n = fread(kb, 16384, 1, pf)
        land_buffer_add(self, kb, n)
        if n < 16384:
            break
    fclose(pf)
    return self

*** "ifndef" LAND_NO_COMPRESS
def land_buffer_compress(LandBuffer *self):
    uLongf destlen = self->n * 1.1 + 12
    Bytef *dest = land_malloc(4 + destlen)
    *((uint32_t *)dest) = self->n
    compress(dest + 4, &destlen, (void *)self->buffer, self->n)
    dest = land_realloc(dest, 4 + destlen)
    land_free(self->buffer)
    self->buffer = (void *)dest
    self->size = self->n = 4 + destlen

def land_buffer_decompress(LandBuffer *self):
    uLongf destlen = *((uint32_t *)self->buffer)
    Bytef *dest = land_malloc(destlen)
    uncompress(dest, &destlen, (void *)(4 + self->buffer), self->n)
    land_free(self->buffer)
    self->buffer = (void *)dest
    self->size = self->n = destlen
*** "endif"

int def land_buffer_compare(LandBuffer *self, *other):
    if self->n < other->n: return -1
    if self->n > other->n: return 1
    return memcmp(self->buffer, other->buffer, self->n)

*** "if" 0
static int def pf_fclose(void *userdata):
    LandBufferAsFile *self = userdata
    land_free(self)
    return 0

static int def pf_getc(void *userdata):
    LandBufferAsFile *self = userdata
    if self->ungetc & 256:
        int c = self->ungetc & 255
        self->ungetc = 0
        return c
    if self->pos >= self->landbuffer->n: return EOF
    int c = ((unsigned char *)self->landbuffer->buffer)[self->pos]
    self->pos++
    return c

static int def pf_ungetc(int c, void *userdata):
    LandBufferAsFile *self = userdata
    self->ungetc = c | 256
    return c

static long def pf_fread(void *p, long n, void *userdata):
    LandBufferAsFile *self = userdata
    if self->ungetc & 256:
        *(char *)p = self->ungetc & 255
        self->ungetc = 0
        n--
        p = (char *)p + 1
    if self->pos + n > self->landbuffer->n:
        n = self->landbuffer->n - self->pos
    memcpy(p, self->landbuffer->buffer + self->pos, n)
    self->pos += n
    return n

static int def pf_putc(int c, void *userdata):
    LandBufferAsFile *self = userdata
    land_buffer_add_char(self->landbuffer, c)
    return c

static long def pf_fwrite(const void *p, long n, void *userdata):
    LandBufferAsFile *self = userdata
    land_buffer_add(self->landbuffer, p, n)
    return n

static int def pf_fseek(void *userdata, int offset):
    return 0

static int def pf_feof(void *userdata):
    LandBufferAsFile *self = userdata
    if self->pos >= self->landbuffer->n: return True
    return False

static int def pf_ferror(void *userdata):
    return 0

*** "endif"

#static struct PACKFILE_VTABLE vt = {
    #pf_fclose,
    #pf_getc,
    #pf_ungetc,
    #pf_fread,
    #pf_putc,
    #pf_fwrite,
    #pf_fseek,
    #pf_feof,
    #pf_ferror
#}

#PACKFILE *def land_buffer_read_packfile(LandBuffer *self):
    #"""
    #Returns a packfile to read from the given buffer. The buffer must not be
    #destroyed as long as the packfile is open.
    #"""
    #LandBufferAsFile *lbaf; land_alloc(lbaf)
    #lbaf->landbuffer = self
    #PACKFILE *pf = pack_fopen_vtable(&vt, lbaf)
    #return pf

#PACKFILE *def land_buffer_write_packfile(LandBuffer *self):
    #"""
    #Returns a packfile to write to the given buffer. The buffer must not be
    #destroyed as long as the packfile is open.
    #"""
    #LandBufferAsFile *lbaf; land_alloc(lbaf)
    #lbaf->landbuffer = self
    #PACKFILE *pf = pack_fopen_vtable(&vt, lbaf)
    #return pf




global *** "ifdef" LAND_MEMLOG

macro land_buffer_new() land_buffer_new_memlog(__FILE__, __LINE__)
macro land_buffer_del(x) land_buffer_del_memlog(x, __FILE__, __LINE__)
macro land_buffer_finish(x) land_buffer_finish_memlog(x, __FILE__, __LINE__)
macro land_buffer_read_from_file(x) land_buffer_read_from_file_memlog(x, __FILE__, __LINE__)
macro land_buffer_split(x, y) land_buffer_split_memlog(x, y, __FILE__, __LINE__)

global *** "endif"
