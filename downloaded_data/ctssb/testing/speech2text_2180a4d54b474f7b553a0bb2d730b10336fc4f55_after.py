from pydub import AudioSegment
import os.path


def split_voice_file(voice_file, pos_file):
    positions = get_pos_from_file(pos_file)
    basename, ext = os.path.splitext(voice_file)
    if ext.upper() == '.MP3':
        voice = AudioSegment.from_mp3(voice_file)
        fmt = 'mp3'
    elif ext.upper() == '.WAV':
        voice = AudioSegment.from_wav(voice_file)
        fmt = 'wav'
    else:
        return
    for p in positions:
        filename = "%s_%04d_%s_%d_%d.%s" % (basename, p[0], p[1], p[2], p[3], fmt)
        voice[p[2]:p[3]].export(filename, format=fmt)


def get_pos_from_file(pos_file):
    start = 0
    positions = []
    with open(pos_file) as infile:
        for i, line in enumerate(infile.readlines()):
            people, end = line.split(' ')
            end = int(end)//100000*60000 + int(end)%100000
            positions.append([i, people, start, end])
            start = end
    infile.close()
    return positions


def main():
    voice_file = "../Benedict_Evans_Mono.wav"
    pos_file = "pos_test_file.txt"
    split_voice_file(voice_file, pos_file)


if __name__ == '__main__':
    main()
