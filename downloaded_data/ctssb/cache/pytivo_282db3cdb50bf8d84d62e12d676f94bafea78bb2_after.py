import ConfigParser, os
import re
from ConfigParser import NoOptionError

BLACKLIST_169 = ('540', '649')

config = ConfigParser.ConfigParser()
p = os.path.dirname(__file__)
config_file = os.path.join(p, 'pyTivo.conf')
config.read(config_file)

def reset():
    global config
    del config
    config = ConfigParser.ConfigParser()
    config.read(config_file)

def getGUID():
    if config.has_option('Server', 'GUID'):
        guid = config.get('Server', 'GUID')
    else:
        guid = '123456'
    return guid

def getBeaconAddresses():
    if config.has_option('Server', 'beacon'):
        beacon_ips = config.get('Server', 'beacon')
    else:
        beacon_ips = '255.255.255.255'
    return beacon_ips

def getPort():
    return config.get('Server', 'Port')

def get169Setting(tsn):
    if not tsn:
        return True

    if config.has_section('_tivo_' + tsn):
        if config.has_option('_tivo_' + tsn, 'aspect169'):
            try:
                return config.getboolean('_tivo_' + tsn, 'aspect169')
            except ValueError:
                pass

    if tsn[:3] in BLACKLIST_169:
        return False

    return True

def getShares(tsn=''):
    shares = [(section, dict(config.items(section)))
              for section in config.sections()
              if not(section.startswith('_tivo_') or section == 'Server')]

    if config.has_section('_tivo_' + tsn):
        if config.has_option('_tivo_' + tsn, 'shares'):
            # clean up leading and trailing spaces & make sure ref is valid
            tsnshares = []
            for x in config.get('_tivo_' + tsn, 'shares').split(','):
                y = x.lstrip().rstrip()
                if config.has_section(y):
                    tsnshares += [(y, dict(config.items(y)))]
            if tsnshares:
                shares = tsnshares

    for name, data in shares:
        if not data.get('auto_subshares', 'False').lower() == 'true':
            continue

        base_path = data['path']
        try:
            for item in os.listdir(base_path):
                item_path = os.path.join(base_path, item)
                if not os.path.isdir(item_path) or item.startswith('.'):
                    continue

                new_name = name + '/' + item
                new_data = dict(data)
                new_data['path'] = item_path

                shares.append((new_name, new_data))
        except:
            pass

    return shares

def getDebug(ref):
    if config.has_option('Server', 'debug'):
        try:
            return str2tuple(config.get('Server', 'debug')+',,')[ref]
        except NoOptionError:
            pass
    return str2tuple('False,,')[ref]

def getHack83():
    try:
        debug = config.get('Server', 'hack83')
        if debug.lower() == 'true':
            return True
        else:
            return False
    except NoOptionError:
        return False

def getOptres(tsn = None):
    if tsn and config.has_section('_tivo_' + tsn):
        try:
            return config.getboolean('_tivo_' + tsn, 'optres')
        except NoOptionError, ValueError:
            pass
    try:
        return config.getboolean('Server', 'optres')
    except NoOptionError, ValueError:
        return False

def getPixelAR(ref):
    if config.has_option('Server', 'par'):
        try:
            return (True, config.getfloat('Server', 'par'))[ref]
        except NoOptionError, ValueError:
            pass
    return (False, 1.0)[ref]

def get(section, key):
    return config.get(section, key)

def getFFmpegTemplate(tsn):
    if tsn and config.has_section('_tivo_' + tsn):
        try:
            return config.get('_tivo_' + tsn, 'ffmpeg_tmpl', raw=True)
        except NoOptionError:
            pass
    try:
        return config.get('Server', 'ffmpeg_tmpl', raw=True)
    except NoOptionError: #default
        return '%(video_codec)s %(video_fps)s %(video_br)s %(max_video_br)s \
                %(buff_size)s %(aspect_ratio)s -comment pyTivo.py %(audio_br)s \
                %(audio_fr)s %(audio_ch)s %(audio_codec)s %(ffmpeg_pram)s %(format)s'

def getFFmpegPrams(tsn):
    if tsn and config.has_section('_tivo_' + tsn):
        try:
            return config.get('_tivo_' + tsn, 'ffmpeg_pram', raw=True)
        except NoOptionError:
            pass
    try:
        return config.get('Server', 'ffmpeg_pram', raw=True)
    except NoOptionError:
        return None

def isHDtivo(tsn):  # tsn's of High Definition Tivo's
    return tsn != '' and tsn[:3] in ['648', '652']

def getValidWidths():
    return [1920, 1440, 1280, 720, 704, 544, 480, 352]

def getValidHeights():
    return [1080, 720, 480] # Technically 240 is also supported

# Return the number in list that is nearest to x
# if two values are equidistant, return the larger
def nearest(x, list):
    return reduce(lambda a, b: closest(x, a, b), list)

def closest(x, a, b):
    if abs(x - a) < abs(x - b) or (abs(x - a) == abs(x - b) and a > b):
        return a
    else:
        return b

def nearestTivoHeight(height):
    return nearest(height, getValidHeights())

def nearestTivoWidth(width):
    return nearest(width, getValidWidths())

def getTivoHeight(tsn):
    if tsn and config.has_section('_tivo_' + tsn):
        try:
            height = config.getint('_tivo_' + tsn, 'height')
            return nearestTivoHeight(height)
        except NoOptionError:
            pass
    try:
        height = config.getint('Server', 'height')
        return nearestTivoHeight(height)
    except NoOptionError: #defaults for S3/S2 TiVo
        if isHDtivo(tsn):
            return 720
        else:
            return 480

def getTivoWidth(tsn):
    if tsn and config.has_section('_tivo_' + tsn):
        try:
            width = config.getint('_tivo_' + tsn, 'width')
            return nearestTivoWidth(width)
        except NoOptionError:
            pass
    try:
        width = config.getint('Server', 'width')
        return nearestTivoWidth(width)
    except NoOptionError: #defaults for S3/S2 TiVo
        if isHDtivo(tsn):
            return 1280
        else:
            return 544

def getAudioBR(tsn = None):
    #convert to non-zero multiple of 64 to ensure ffmpeg compatibility
    #compare audio_br to max_audio_br and return lowest
    if tsn and config.has_section('_tivo_' + tsn):
        try:
            audiobr = int(max(int(strtod(config.get('_tivo_' + tsn, 'audio_br'))/1000), 64)/64)*64
            return str(min(audiobr, getMaxAudioBR(tsn))) + 'k'
        except NoOptionError:
            pass
    try:
        audiobr = int(max(int(strtod(config.get('Server', 'audio_br'))/1000), 64)/64)*64
        return str(min(audiobr, getMaxAudioBR(tsn))) + 'k'
    except NoOptionError:
        return str(min(384, getMaxAudioBR(tsn))) + 'k'

def getVideoBR(tsn = None):
    if tsn and config.has_section('_tivo_' + tsn):
        try:
            return config.get('_tivo_' + tsn, 'video_br')
        except NoOptionError:
            pass
    try:
        return config.get('Server', 'video_br')
    except NoOptionError: #defaults for S3/S2 TiVo
        if isHDtivo(tsn):
            return '8192k'
        else:
            return '4096K'

def getMaxVideoBR():
    try:
        return str(int(strtod(config.get('Server', 'max_video_br'))/1000)) + 'k'
    except NoOptionError: #default to 17Mi
        return '17408k'

def getBuffSize():
    try:
        return str(int(strtod(config.get('Server', 'bufsize'))))
    except NoOptionError: #default 1024k
        return '1024k'

def getMaxAudioBR(tsn = None):
    #convert to non-zero multiple of 64 for ffmpeg compatibility
    if tsn and config.has_section('_tivo_' + tsn):
        try:
            return int(int(strtod(config.get('_tivo_' + tsn, 'max_audio_br'))/1000)/64)*64
        except NoOptionError:
            pass
    try:
        return int(int(strtod(config.get('Server', 'max_audio_br'))/1000)/64)*64
    except NoOptionError: 
        return int(448) #default to 448

def getAudioCodec(tsn = None):
    if tsn and config.has_section('_tivo_' + tsn):
        try:
            return config.get('_tivo_' + tsn, 'audio_codec')
        except NoOptionError:
            pass
    try:
        return config.get('Server', 'audio_codec')
    except NoOptionError:
        return None

def getAudioCH(tsn = None):
    if tsn and config.has_section('_tivo_' + tsn):
        try:
            return config.get('_tivo_' + tsn, 'audio_ch')
        except NoOptionError:
            pass
    try:
        return config.get('Server', 'audio_ch')
    except NoOptionError:
        return None

def getAudioFR(tsn = None):
    if tsn and config.has_section('_tivo_' + tsn):
        try:
            return config.get('_tivo_' + tsn, 'audio_fr')
        except NoOptionError:
            pass
    try:
        return config.get('Server', 'audio_fr')
    except NoOptionError:
        return None

def getVideoFPS(tsn = None):
    if tsn and config.has_section('_tivo_' + tsn):
        try:
            return config.get('_tivo_' + tsn, 'video_fps')
        except NoOptionError:
            pass
    try:
        return config.get('Server', 'video_fps')
    except NoOptionError:
        return None
    
def getVideoCodec(tsn = None):
    if tsn and config.has_section('_tivo_' + tsn):
        try:
            return config.get('_tivo_' + tsn, 'video_codec')
        except NoOptionError:
            pass
    try:
        return config.get('Server', 'video_codec')
    except NoOptionError:
        return None

def getFormat(tsn = None):
    if tsn and config.has_section('_tivo_' + tsn):
        try:
            return config.get('_tivo_' + tsn, 'force_format')
        except NoOptionError:
            pass
    try:
        return config.get('Server', 'force_format')
    except NoOptionError:
        return None

def str2tuple(s):
    items = s.split(',')
    L = [x.strip() for x in items]
    return tuple(L)

# Parse a bitrate using the SI/IEEE suffix values as if by ffmpeg
# For example, 2K==2000, 2Ki==2048, 2MB==16000000, 2MiB==16777216
# Algorithm: http://svn.mplayerhq.hu/ffmpeg/trunk/libavcodec/eval.c
def strtod(value):
    prefixes = {'y': -24, 'z': -21, 'a': -18, 'f': -15, 'p': -12,
                'n': -9,  'u': -6,  'm': -3,  'c': -2,  'd': -1,
                'h': 2,   'k': 3,   'K': 3,   'M': 6,   'G': 9,
                'T': 12,  'P': 15,  'E': 18,  'Z': 21,  'Y': 24}
    p = re.compile(r'^(\d+)(?:([yzafpnumcdhkKMGTPEZY])(i)?)?([Bb])?$')
    m = p.match(value)
    if m is None:
        raise SyntaxError('Invalid bit value syntax')
    (coef, prefix, power, byte) = m.groups()
    if prefix is None:
        value = float(coef)
    else:
        exponent = float(prefixes[prefix])
        if power == 'i':
            # Use powers of 2
            value = float(coef) * pow(2.0, exponent / 0.3)
        else:
            # Use powers of 10
            value = float(coef) * pow(10.0, exponent)
    if byte == 'B': # B == Byte, b == bit
        value *= 8;
    return value
