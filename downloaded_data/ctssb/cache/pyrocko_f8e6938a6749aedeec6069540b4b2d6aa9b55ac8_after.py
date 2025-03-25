import numpy as num
import struct
import calendar

from pyrocko import trace
from pyrocko.io_common import FileLoadError


def ibm2ieee(ibm):
    """
    Converts an IBM floating point number into IEEE format.
    :param: ibm - 32 bit unsigned integer: unpack('>L', f.read(4))
    """
    if ibm == 0:
        return 0.0
    sign = ibm >> 31 & 0x01
    exponent = ibm >> 24 & 0x7f
    mantissa = (ibm & 0x00ffffff) / float(pow(2, 24))
    print 'x', sign, exponent - 64, mantissa
    return (1 - 2 * sign) * mantissa * float(pow(16, exponent - 64))


def unpack_ibm_f4(data):

    ibm = num.fromstring(data, dtype='>u4').astype(num.int32)
    sign = (ibm >> 31) & 0x01
    exponent = (ibm >> 24) & 0x7f
    mantissa = (ibm & 0x00ffffff) / float(pow(2, 24))
    xxx = (1 - 2 * sign) * mantissa * (16. ** (exponent - 64)).astype(num.float)
    # for i in xrange(len(data)/4):
    #    yyy = ibm2ieee(struct.unpack('>L', data[i*4:(i+1)*4])[0])
    #    print 'y', sign[i], exponent[i] - 64, mantissa[i]
    #    print xxx[i], yyy
    #    if xxx[i] != yyy:
    #        sys.exit()
    #    print
    return xxx


class SEGYError(Exception):
    pass


def iload(filename, load_data, endianness='>'):
    '''Read SEGY file.

       filename -- Name of SEGY file.
       load_data -- If True, the data is read, otherwise only read headers.
    '''

    endianness = endianness

    nbth = 3200
    nbbh = 400
    nbthx = 3200
    nbtrh = 240

    try:
        f = open(filename, 'rb')

        textual_file_header = f.read(nbth)

        if len(textual_file_header) != nbth:
            raise SEGYError('incomplete textual file header')

        binary_file_header = f.read(nbbh)
        if len(binary_file_header) != nbbh:
            raise SEGYError('incomplete binary file header')

        line_number = struct.unpack(endianness+'1I', binary_file_header[4:8])
        hvals = struct.unpack(endianness+'24H', binary_file_header[12:12+24*2])
        (ntraces, nauxtraces, deltat_us, deltat_us_orig, nsamples,
            nsamples_orig, format, ensemble_fold) = hvals[0:8]

        (segy_revision, fixed_length_traces, nextended_headers) = \
            struct.unpack(endianness+'3H', binary_file_header[100:100+3*2])

        formats = {
            1: (unpack_ibm_f4,  4, "4-byte IBM floating-point"),
            2: (endianness+'i4', 4, "4-byte, two's complement integer"),
            3: (endianness+'i4', 2, "2-byte, two's complement integer"),
            4: (None,  4, "4-byte fixed-point with gain (obolete)"),
            5: ('f4',  4, "4-byte IEEE floating-point"),
            6: (None,  0, "not currently used"),
            7: (None,  0, "not currently used"),
            8: ('i1',  1, "1-byte, two's complement integer")}

        dtype = formats[format][0]
        sample_size = formats[format][1]
        if dtype is None:
            raise SEGYError('unsupported sample data format %i: %s' % (
                format, formats[format][2]))

        for ihead in xrange(nextended_headers):
            f.read(nbthx)

        atend = False
        while not atend:
            for itrace in xrange((ntraces+nauxtraces)):
                trace_header = f.read(nbtrh)
                if len(trace_header) == 0:
                    atend = True
                    break

                if len(trace_header) != nbtrh:
                    raise SEGYError('incomplete trace header')

                (scoordx, scoordy, gcoordx, gcoordy) = \
                    struct.unpack(endianness+'4f4', trace_header[72:72+4*4])

                (ensemblex, ensembley) = \
                    struct.unpack(endianness+'2f4', trace_header[180:180+2*4])
                (ensemble_num,) = \
                    struct.unpack(endianness+'1I', trace_header[20:24])
                (trensemble_num,) = \
                    struct.unpack(endianness+'1I', trace_header[24:28])
                (trace_number,) = \
                    struct.unpack(endianness+'1I', trace_header[0:4])
                (trace_numbersegy,) = \
                    struct.unpack(endianness+'1I', trace_header[4:8])
                (orfield_num,) = \
                    struct.unpack(endianness+'1I', trace_header[8:12])
                (ortrace_num,) = \
                    struct.unpack(endianness+'1I', trace_header[12:16])

                tvals = struct.unpack(
                    endianness+'12H', trace_header[94:94+12*2])

                (nsamples_this, deltat_us_this) = tvals[-2:]

                tscalar = struct.unpack(
                    endianness+'1H', trace_header[214:216])[0]

                if tscalar == 0:
                    tscalar = 1.
                elif tscalar < 0:
                    tscalar = 1.0 / tscalar
                else:
                    tscalar = float(tscalar)

                tvals = [x * tscalar for x in tvals[:-2]]

                (year, doy, hour, minute, second) = \
                    struct.unpack(endianness+'5H', trace_header[156:156+2*5])

                try:
                    if year < 100:
                        year += 2000

                    tmin = calendar.timegm(
                        (year, 1, doy, hour, minute, second))

                except:
                    raise SEGYError('invalid start date/time')

                if fixed_length_traces:
                    if (nsamples_this, deltat_us_this) \
                            != (nsamples, deltat_us):

                        raise SEGYError(
                            'trace of incorrect length or sampling '
                            'rate (trace=%i)' % itrace+1)

                if load_data:
                    datablock = f.read(nsamples_this*sample_size)
                    if len(datablock) != nsamples_this*sample_size:
                        raise SEGYError('incomplete trace data')

                    if isinstance(dtype, basestring):
                        data = num.fromstring(datablock, dtype=dtype)
                    else:
                        data = dtype(datablock)

                    tmax = None
                else:
                    f.seek(nsamples_this*sample_size, 1)
                    tmax = tmin + deltat_us_this/1000000.*(nsamples_this-1)
                    data = None

                tr = trace.Trace(
                    '',
                    '%05i' % (line_number),
                    '%02i' % (ensemble_num),
                    '%03i' % (ortrace_num),
                    tmin=tmin,
                    tmax=tmax,
                    deltat=deltat_us_this/1000000.,
                    ydata=data,
                    meta=dict(orfield_num=orfield_num))

                yield tr

        f.close()

    except (OSError, SEGYError), e:
        raise FileLoadError(e)
