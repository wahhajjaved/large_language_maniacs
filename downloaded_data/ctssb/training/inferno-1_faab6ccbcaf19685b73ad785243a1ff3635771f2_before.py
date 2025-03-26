import numpy as np
import os
import skimage.io

from ..core.base import SyncableDataset
from ..core.base import IndexSpec
from . import volumetric_utils as vu
from ...utils import io_utils as iou
from ...utils import python_utils as pyu
from ...utils.exceptions import assert_, ShapeError


class VolumeLoader(SyncableDataset):
    def __init__(self, volume, window_size, stride, downsampling_ratio=None, padding=None,
                 padding_mode='reflect', transforms=None, return_index_spec=False, name=None,
                 is_multichannel=False):
        super(VolumeLoader, self).__init__()
        # Validate volume
        assert isinstance(volume, np.ndarray), str(type(volume))
        # Validate window size and stride
        if is_multichannel:
            assert_(len(window_size) + 1 == volume.ndim, "%i, %i" % (len(window_size),
                                                                     volume.ndim),
                                                                    ShapeError)
            assert_(len(stride) + 1 == volume.ndim, exception_type=ShapeError)
            # TODO implemnent downsampling and padding for multi-channel volume
            assert_(downsampling_ratio is None, exception_type=NotImplementedError)
            assert_(padding is None, exception_type=NotImplementedError)
        else:
            assert_(len(window_size) == volume.ndim, "%i, %i" % (len(window_size),
                                                                 volume.ndim),
                                                                ShapeError)
            assert_(len(stride) == volume.ndim, exception_type=ShapeError)
        # Validate transforms
        assert_(transforms is None or callable(transforms))

        self.name = name
        self.return_index_spec = return_index_spec
        self.volume = volume
        self.window_size = window_size
        self.stride = stride
        self.padding_mode = padding_mode
        self.is_multichannel = is_multichannel
        self.transforms = transforms
        # DataloaderIter should do the shuffling
        self.shuffle = False

        ndim = self.volume.ndim - 1 if is_multichannel else self.volume.ndim

        if downsampling_ratio is None:
            self.downsampling_ratio = [1] * ndim
        elif isinstance(downsampling_ratio, int):
            self.downsampling_ratio = [downsampling_ratio] * self.volume.ndim
        elif isinstance(downsampling_ratio, (list, tuple)):
            assert_(len(downsampling_ratio) == self.volume.ndim, exception_type=ShapeError)
            self.downsampling_ratio = list(downsampling_ratio)
        else:
            raise NotImplementedError

        if padding is None:
            self.padding = [[0, 0]] * ndim
        else:
            self.padding = padding
            self.pad_volume()

        self.base_sequence = self.make_sliding_windows()

    def pad_volume(self, padding=None):
        padding = self.padding if padding is None else padding
        if padding is None:
            return self.volume
        else:            
            #for symmertic padding only one int can be passed for each axis
            assert_(all(isinstance(pad, (int, tuple, list)) for pad in self.padding), "Expect int or iterable", TypeError)
            self.padding = [[pad, pad] if isinstance(int, pad) else pad for pad in self.padding]
            self.volume = np.pad(self.volume,
                                 pad_width=self.padding,
                                 mode=self.padding_mode)
            return self.volume

    def make_sliding_windows(self):
        shape = self.volume.shape[1:] if self.is_multichannel else self.volume.shape
        return list(vu.slidingwindowslices(shape=list(shape),
                                           window_size=self.window_size,
                                           strides=self.stride,
                                           shuffle=self.shuffle,
                                           add_overhanging=True,
                                           ds=self.downsampling_ratio))

    def __getitem__(self, index):
        # Casting to int would allow index to be IndexSpec objects.
        index = int(index)
        slices = self.base_sequence[index]
        if self.is_multichannel:
            slices = (slice(None),) + tuple(slices)
        sliced_volume = self.volume[tuple(slices)]
        if self.transforms is None:
            transformed = sliced_volume
        else:
            transformed = self.transforms(sliced_volume)
        if self.return_index_spec:
            return transformed, IndexSpec(index=index, base_sequence_at_index=slices)
        else:
            return transformed

    def clone(self, volume=None, transforms=None, name=None):
        # Make sure the volume shapes check out
        assert_(volume.shape == self.volume.shape, exception_type=ShapeError)
        # Make a new instance (without initializing)
        new = type(self).__new__(type(self))
        # Update dictionary to initialize
        new_dict = dict(self.__dict__)
        if volume is not None:
            new_dict.update({'volume': volume})
        if transforms is not None:
            new_dict.update({'transforms': transforms})
        if name is not None:
            new_dict.update({'name': name})
        new.__dict__.update(new_dict)
        return new

    def __repr__(self):
        return "{}(shape={}, name={})".format(type(self).__name__, self.volume.shape, self.name)


class HDF5VolumeLoader(VolumeLoader):
    def __init__(self, path, path_in_h5_dataset=None, data_slice=None, transforms=None,
                 name=None, **slicing_config):

        if isinstance(path, dict):
            assert name is not None
            assert name in path
            self.path = path.get(name)
        elif isinstance(path, str):
            assert os.path.exists(path), path
            self.path = path
        else:
            raise NotImplementedError

        if isinstance(path_in_h5_dataset, dict):
            assert name is not None
            assert name in path_in_h5_dataset
            self.path_in_h5_dataset = path_in_h5_dataset.get(name)
        elif isinstance(path_in_h5_dataset, str):
            self.path_in_h5_dataset = path_in_h5_dataset
        elif path_in_h5_dataset is None:
            self.path_in_h5_dataset = None
        else:
            raise NotImplementedError

        if data_slice is None or isinstance(data_slice, (str, list)):
            self.data_slice = vu.parse_data_slice(data_slice)
        elif isinstance(data_slice, dict):
            assert name is not None
            assert name in data_slice
            self.data_slice = vu.parse_data_slice(data_slice.get(name))
        else:
            raise NotImplementedError

        slicing_config_for_name = pyu.get_config_for_name(slicing_config, name)

        assert 'window_size' in slicing_config_for_name
        assert 'stride' in slicing_config_for_name

        # Read in volume from file
        volume = iou.fromh5(self.path, self.path_in_h5_dataset,
                            dataslice=(tuple(self.data_slice)
                                       if self.data_slice is not None
                                       else None))
        # Initialize superclass with the volume
        super(HDF5VolumeLoader, self).__init__(volume=volume, name=name, transforms=transforms,
                                               **slicing_config_for_name)


class TIFVolumeLoader(VolumeLoader):
    """Loader for volumes stored in .tif files."""
    def __init__(self, path, data_slice=None, transforms=None, name=None, **slicing_config):
        """
        Parameters
        ----------
        path : str
            Path to the volume.
        transforms : callable
            Transforms to apply on the read volume.
        slicing_config : dict
            Dictionary specifying the sliding window. Must contain keys 'window_size'
            and 'stride'.
        """
        if isinstance(path, dict):
            assert name in path.keys()
            assert os.path.exists(path.get(name))
            self.path = path.get(name)
        elif isinstance(path, str):
            assert os.path.exists(path)
            self.path = path
        else:
            raise NotImplementedError

        assert 'window_size' in slicing_config
        assert 'stride' in slicing_config

        if data_slice is None or isinstance(data_slice, (str, list)):
            self.data_slice = vu.parse_data_slice(data_slice)
        elif isinstance(data_slice, dict):
            assert name is not None
            assert name in data_slice
            self.data_slice = vu.parse_data_slice(data_slice.get(name))
        else:
            raise NotImplementedError

        # Read in volume from file
        volume = skimage.io.imread(self.path)
        # and slice it
        volume = volume[self.data_slice] if self.data_slice is not None else volume
        # Initialize superclass with the volume
        super(TIFVolumeLoader, self).__init__(volume=volume, transforms=transforms,
                                              **slicing_config)
