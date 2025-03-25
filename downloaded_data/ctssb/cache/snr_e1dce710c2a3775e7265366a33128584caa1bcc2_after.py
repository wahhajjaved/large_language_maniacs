description = "a module to compute SNRs and PSDs from frames"
author = "Reed Essick <reed.essick@ligo.org>, Ryan Lynch <ryan.lynch@ligo.org>"

from pylal import Fr
import numpy as np

#=================================================

def tukey(window_length, alpha=0.5):
    '''The Tukey window, also known as the tapered cosine window, can be regarded as a cosine lobe of width \alpha * N / 2
    that is convolved with a rectangle window of width (1 - \alpha / 2). At \alpha = 1 it becomes rectangular, and
    at \alpha = 0 it becomes a Hann window.
 
    We use the same reference as MATLAB to provide the same results in case users compare a MATLAB output to this function
    output
 
    Reference
    ---------
    http://www.mathworks.com/access/helpdesk/help/toolbox/signal/tukeywin.html
 
    '''
    # Special cases
    if alpha <= 0:
        return np.ones(window_length) #rectangular window
    elif alpha >= 1:
        return np.hanning(window_length)

    # Normal case
    x = np.linspace(0, 1, window_length)
    w = np.ones(x.shape)

    # first condition 0 <= x < alpha/2
    first_condition = x<alpha/2
    w[first_condition] = 0.5 * (1 + np.cos(2*np.pi/alpha * (x[first_condition] - alpha/2) ))

    # second condition already taken care of

    # third condition 1 - alpha / 2 <= x <= 1
    third_condition = x>=(1 - alpha/2)
    w[third_condition] = 0.5 * (1 + np.cos(2*np.pi/alpha * (x[third_condition] - 1 + alpha/2)))

    return w

def dft(vec, dt=1.0):
        """
        computes the DFT of vec
        returns the one-sides spectrum
        """
        N = len(vec)

        dft_vec = np.fft.fft(vec)*dt
        freqs = np.fft.fftfreq(N, d=dt)

        freqs = np.fft.fftshift(freqs)
        truth = freqs>=0

        return np.fft.fftshift(dft_vec)[truth], freqs[truth]

def idft(dft_vec, dt=1.0):
        """
        computes the inverse DFT of vec
        takes in the one-sided spectrum
        """
        N = len(dft_vec) ### if N is even, then n is even
                         ### if N is odd, then n is odd

        if N%2: ### if N is odd, n is odd
                n = 2*N-1
        else: ### if N is even, n is even
                n = 2*N

        seglen = n*dt ### length of time series

        vec = np.empty((n,), complex)
        vec[:N] = dft_vec
        if n%2: ### odd number of points
                vec[N:] = np.conjugate(dft_vec[1:])[::-1]
        else: ### even number of points
                vec[N:] = np.conjugate(dft_vec)[::-1]

        vec = np.fft.ifft( vec ) / seglen
        time = np.arange(0, seglen, dt)

        return vec, time

#=================================================

def extract_start_dur( filename, suffix=".gwf" ):
    """
    returns the start, dur from a standard LIGO filename
    """
    return (int(l) for l in filename[:-len(suffix)].split("-")[-2:])

#=================================================

def frames2vect( frames, channel, start=-np.infty, stop=np.infty ):
    """
    digs out the correct data from a list of frames
    assumes contiguous frames, constant dt, etc.
    returns vect, time
    """
    frames = [ (extract_start_dur( frame ), frame) for frame in frames ]
    frames.sort( key=lambda l: l[0][0] )

    v = np.array([])
    t = np.array([])
    for (s, d), frame in frames:
        frame_start = max(s, start)
        frame_stop = min(s+d, start+span)
        frame_span = frame_stop - frame_start

        vect, s, _, dt, _, _ = Fr.frgetvect1d(frame, channel, start=frame_span, span=frame_span)
        N = len(vect)
        v = np.concatenate( (v, vect) )
        t = np.concatenate( (t, np.arange(s, s+dt*N, dt)) )

    if not len(v):
        raise ValueError("no Data found!")

    truth = (start <= t)*(t <= stop)
    return v[truth], t[0], t[1]-t[0]

#=================================================

def frames2PSD( frames, channel, start=-np.infty, stop=np.infty, num_segs=12, overlap=0.0, tukey_alpha=0.1 ):
    """
    assumes contiguous frames with constant sample rates, etc
    """
    vect, s, dt = frames2vect( frames, channel, start=start, stop=stop )

    N = len(vect)
    if overlap > N - num_segs:
        raise ValueError, "overlap is too big!"

    dn = int( N / ( num_segs - (num_segs-1)*overlap ) ) ### number of elements per seg
    o = int( dn*overlap )
    seglen = dn*dt

    ### compute dfts for each segment separately
    psds = np.empty((n/2, num_segs), complex)
    for segNo in xrange(num_segs):
        start = segNo*(dn - o)
        psds[:,segNo], freqs = dft(vec[start:start+dn], dt=dt)

    ### average
    mean_psd = np.sum(psds.real**2 + psds.imag**2, axis=1) / (seglen*num_segs)

    return 2*mean_psd, freqs ### factor of 2 makes this a one-sided psd

class PSD(object):
        """
        an object that holds onto power-spectral densities with associated frequency samples
        these should all be one-sided PSDs, but we can't really check that.
        """

        ###
        def __init__(self, freqs, psd, kind="linear"):
                len_freqs = len(freqs)
                self.n_freqs = len_freqs
                if len(psd) != len_freqs:
                        raise ValueError, "freqs and ps must have the same length"
                if not len_freqs:
                        raise ValueError, "freqs and psd must have at least 1 entries"
                elif len_freqs == 1:
                        freqs = np.array(2*list(freqs))
                        psd = np.array(2*list(psd))
                self.freqs = freqs
                self.psd = psd

        ###
        def check(self):
                return len(self.freqs) == len(self.psd)

        ###
        def update(self, psd, freqs=None):
                if freqs!=None:
                        if len(freqs)!=len(psd):
                                raise ValueError, "len(freqs) != len(psd)"
                        self.freqs = freqs[:]
                        self.psd = psd[:]
                else:
                        self.psd=psd[:]

        ###
        def get_psd(self):
                return self.psd

        ###
        def get_freqs(self):
                return self.freqs

        ###
        def interpolate(self, freqs):
                return np.interp(freqs, self.freqs, self.psd)

        ###
        def draw_noise(self, freqs):
                """
                draws a noise realization at the specified frequencies
                """
                n_freqs = len(freqs)

                vars = self.interpolate(freqs)
                amp = np.random.normal(size=(n_freqs))
                phs = np.random.random(n_freqs)*2*np.pi

                return (amp * vars**0.5) * np.exp(1j*phs)

        ###
        def __repr__(self):
                return self.__str__()

        ###
        def __str__(self):
                min_psd = np.min(self.psd)
                d=int(np.log10(min_psd))-1
                return """utils.PSD object
        min{freqs}=%.5f
        max{freqs}=%.5f
        No. freqs =%d
        min{psd}=%.5fe%d  at freqs=%.5f"""%(np.min(self.freqs), np.max(self.freqs), len(self.freqs), min_psd*10**(-d), d, self.freqs[min_psd==self.psd][0])

#=================================================

def frames2snr( frames, channel, PSD_obj, start=-np.infty, stop=np.infty, tukey_alpha=0.1 ):
    """
    assumes contiguous frames with constant sample rates, etc
    """
    vect, s, dt = frames2vect( frames, channel, start=start, stop=stop )

    return snr( vect, dt, PSD_obj, tukey_alpha=tukey_alpha)


def snr( vect, dt, PSD_obj, tukey_alpha=0.1 ):
    """
    computes SNR
    """
    N = len(vect)
    vect *= tukey(N, alpha=tukey_alpha)

#    fft_vect = np.abs(np.fft.fft( vect )*dt)**2
#    freqs = np.arange(N/2)/opts.fft_dur
    fft_vect, freqs = dft( vect, dt=dt )
    fft_vect = fft_vect.real**2 + fft_vect.imag**2

    return 4 * np.sum( fft_vect[:N/2] / PSD_obj.interp( freqs ) ) / span # one factor of 2 from both + and - frequencies
                                                                         # one factor of 2 because PSD is one-sided

