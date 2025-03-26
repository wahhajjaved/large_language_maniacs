from abc import abstractmethod, ABCMeta
import utils

class Media(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def get_media_info(self):
        pass

    @abstractmethod
    def read_media(self):
        pass

class Audio(Media):
    __metaclass__ = ABCMeta

    def __init__(self,config,read_sr=None,from_config=False):
        self.read_sr = read_sr
        self.config = config
        self.timeexp = self.config["timeexp"]
        self.path = self.config["path"]

        if from_config:
            self.load_basic_info()
        else:
            self.read_basic_info()
            

    def load_basic_info(self):
        self.original_sr = self.config["sr"]
        self.nchannels = self.config["nchannels"]
        self.sampwidth = self.config["sampwidth"]
        self.length = self.config["length"]
        self.md5 = self.config["md5"]
        self.duration = self.config["duration"]
        self.filesize = self.config["filesize"]
        self.sr = self.original_sr
        self.mask = None
        self.signal = None

    def read_basic_info(self):
        self.original_sr,self.nchannels,self.sampwidth,self.length = utils.read_info(self.path)
        self.md5 = utils.binaryMD5(self.path)
        self.duration = (float(self.length)/float(self.original_sr))/self.timeexp
        self.filesize = utils.media_size(self.path)
        self.sr = self.original_sr
        self.mask = None
        self.signal = None

    def read_media(self):
        offset = 0.0
        duration = None

        if self.mask is not None:
            offset = self.mask[0]
            duration = self.mask[1]-self.mask[0]

        self.signal, self.sr = utils.read(self.path,self.read_sr,offset,duration)
        
    def set_mask(self,startTime,endTime):
        self.mask = [startTime/self.timeexp,endTime/self.timeexp]
        self.read_media()

    def unset_mask(self):
        self.mask = None
        self.signal = None
        self.sr = self.original_sr

    def get_media_info(self):
        info = {}
        info["path"] = self.path
        info["filesize"] = self.filesize
        info["md5"] = self.md5
        info["timeexp"] = self.timeexp
        info["samplerate"] = self.original_sr
        info["sampwidth"] = self.sampwidth
        info["length"] = self.length
        info["nchannels"] = self.nchannels
        info["duration"] = self.duration

        return info

    def get_signal(self):
        if self.signal is None:
            self.read_media()

        return self.signal

    def write_media(self, path, sr=None, aformat="wav"):
        if aformat in ["wav","flac","ogg"]:
            sig = self.get_signal()
            out_sr = self.sr

            if sr is not None:
                out_sr = sr

            utils.write(path,sig,out_sr,self.nchannels,aformat)

            return path
        else:
            raise ValueError("Writing with to '"+aformat+"' is not supported.")

    def get_spec(self, channel=0, n_fft=1024, hop_length=512):
        if channel > self.nchannels -1:
            raise ValueError("Channel outside range.")

        sig = self.get_signal()

        if self.nchannels > 1:
            sig = sig[[channel],:]

        return utils.spectrogram(sig,n_fft=n_fft,hop_length=hop_length)

    def plot_spec(self,ax,channel=0,n_fft=1024,hop_length=512):
        spec = self.get_spec(channel=channel,n_fft=n_fft,hop_length=hop_length)

        return utils.plot_power_spec(spec,ax)

    def plot_waveform(self,ax,wtype="simple"):
        sig = self.get_signal()

        return utils.plot_waveform(sig,self.sr,ax,wtype=wtype)



