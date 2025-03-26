
import obspy
import numpy as np

from mtuq.dataset.base import DatasetBase
from mtuq.util.geodetics import distance_azimuth
from mtuq.util.signal import check_time_sampling, convolve


class GreensTensorBase(object):
    """ Elastic Green's tensor object.  

        Similar to an obpy Trace, except rather than a single time series, holds
        multiple time series corresponding to the independent elements of an 
        elastic Green's tensor.
    """

    def __init__(self, stream, station, origin):
        """
        Normally, all time series required to describe the response at a given
        station to a source at a given origin should be contained in single 
        obspy stream. Certain subclasses may override this behavior
        
        """
        assert isinstance(stream, obspy.Stream), ValueError(
            "An obspy stream must be provided containg multiple traces, "
            "each representing an independing Green's tensor element")

        assert hasattr(station, 'id'), ValueError(
            "Station must have a unique identifier")

        assert check_time_sampling(stream), NotImplementedError(
            "Time sampling differs from trace to trace.")

        self.greens_tensor = stream
        self.greens_tensor.station = self.station = station
        self.greens_tensor.origin = self.origin = origin
        self.greens_tensor.id = self.id = station.id


    def get_synthetics(self, mt):
        """
        Generates synthetic seismogram via linear combination of Green's tensor
        elements
        """
        raise NotImplementedError("Must be implemented by subclass")


    def apply(self, function, *args, **kwargs):
        """
        Applies a function to all time series associated with the given 
        Green's tensor
        """
        return self.__class__(function(self.greens_tensor, *args, **kwargs),
            self.station, self.origin)


    def convolve(self, wavelet):
        """
        Convolves source wavelet with all time series associated with the
        given Green's tensor
        """
        return self.apply(wavelet.convolve_stream)


    def sort_by_distance(self, reverse=False):
        """ 
        Sorts in-place by hypocentral distance
        """
        self.sort_by_function(lambda stream: stream.station.catalog_distance,
            reverse=reverse)


    def sort_by_azimuth(self, reverse=False):
        """
        Sorts in-place by hypocentral azimuth
        """
        self.sort_by_function(lambda stream: stream.station.catalog_azimuth,
            reverse=reverse)


    def sort_by_function(self, function, reverse=False):
        """ 
        Sorts in-place using the python built-in "sort"
        """
        self.__list__.sort(key=function, reverse=reverse)




class GreensTensorList(object):
    """ A list of GreensTensors

        Very similar to an MTUQ Dataset, except rather observed data, holds
        synthetic Green's tensors
    """
    def __init__(self, greens_tensors=None, id=None):
        # typically the id is the event name, event origin time, or some other
        # attribute shared by all GreensTensors
        self.id = id

        self.__list__ = []

        if not greens_tensors:
            # return an empty container, GreensTensors can be added later
            return

        for greens_tensor in greens_tensors:
            self.__add__(greens_tensor)


    def get_synthetics(self, mt):
        """
        Returns an MTUQ Dataset in which all streams correspond to the moment
        tensor mt, and each each individual stream corresponds to an
        individual station
        """
        synthetics = DatasetBase()
        for greens_tensor in self.__list__:
            synthetics += greens_tensor.get_synthetics(mt)
        return synthetics


    # the next three methods can be used to apply signal processing or other
    # operations to all time series in all GreensTensors
    def apply(self, function, *args, **kwargs):
        """
        Returns the result of applying a function to each GreensTensor in the 
        list. Similar to the behavior of the python built-in "apply".
        """
        processed = GreensTensorList()
        for greens_tensor in self.__list__:
            processed +=\
                greens_tensor.apply(function, *args, **kwargs)
        return processed


    def map(self, function, *sequences):
        """
        Returns the result of applying a function to each GreensTensor in the
        list. If one or more optional sequences are given, the function is 
        called with an argument list consisting of the corresponding item of
        each sequence. Similar to the behavior of the python built-in "map".
        """
        processed = GreensTensorList()
        for _i, greens_tensor in enumerate(self.__list__):
            args = [sequence[_i] for sequence in sequences]
            processed +=\
                greens_tensor.apply(function, *args)
        return processed


    def convolve(self, wavelet):
        """ 
        Convolves all Green's tensors with given wavelet
        """
        convolved = GreensTensorList()
        for greens_tensor in self.__list__:
            convolved += greens_tensor.convolve(wavelet)
        return convolved


    def __add__(self, greens_tensor):
        assert hasattr(greens_tensor, 'id')
        self.__list__ += [greens_tensor]
        return self


    def remove(self, id):
        index = self._get_index(id)
        self.__list__.pop(index)


    # the remaining methods deal with indexing and iteration
    def _get_index(self, id):
        for index, greens_tensor in enumerate(self.__list__):
            if id==greens_tensor.id:
                return index


    def __iter__(self):
        return self.__list__.__iter__()


    def __getitem__(self, index):
        return self.__list__[index]


    def __setitem__(self, index, value):
        self.__list__[index] = value


    def __len__(self):
        return len(self.__list__)



class GeneratorBase(object):
    """
    Creates GreensTensorLists via a two-step procedure:

        1) greens_tensor_generator = GreensTensorGenerator(*args, **kwargs)
        2) greens_tensors = greens_tensor_generator(stations, origin) 

    In the second step, the user supplies a list of stations and the origin
    location and time information for an event. A GreensTensorList will be
    created containing a GreensTensor for each station-event pair. The order
    of the GreensTensors in the list should match the order of the stations 
    in the input argument.

    Details regarding how the GreenTensors are actually created--whether
    they are computed on-the-fly or read from a pre-computed database--
    are deferred to the subclass.

    Very similar to an mtuq.dataset.reader, excecpt rather than a Dataset,
    returns a GreensTensorsList
    """
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("Must be implemented by subclass")


    def __call__(self, stations, origin, verbose=False):
        """
        Reads Green's tensors corresponding to given stations and origin
        """
        greens_tensors = GreensTensorList()

        for station in stations:
            # if hypocenter is an inversion parameter, then the values 
            # calculated below will generally differ from catalog_distance and
            # catalog_azimuth attributes
            station.distance, station.azimuth = distance_azimuth(
                station, origin)

            greens_tensors += self.get_greens_tensor(
                station, origin)

        return greens_tensors


    def get_greens_tensor(self, station, origin):
        raise NotImplementedError("Must be implemented by subclass")

