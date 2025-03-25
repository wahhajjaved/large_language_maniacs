"""
Simulator program to simulate a microscope by setting frequency, binning and color channel. The simulator
can be attached to a streaming framework, at the moment Apache Kafka.

The simulator is started by calling:
simulatorNoFlask.get_files(file_path, frequency, binning, color_channel, connect_kafka)
file_path: where the image files are stored period: the period time between each image. The maximum
speed allowed by the system is retrieved when setting period to 0. binning: change image's binning to decrease
message size color_channel: set which color_channels to include, there are up to five channels (1-5), they are set by
giving a list, for example ['1','3'] sets color_channels 1 and 3.
connect_kafka: set to "yes" is Kafka is used as a streaming framework.
"""

import datetime
import os
import sys
import time

import cv2
import numpy as np
from skimage import img_as_uint
from skimage.measure import block_reduce

from hio_stream_target import HarmonicIOStreamTarget


def get_files(file_path, period, binning, color_channel, send_to_target):
    """
    This function retrieves files and creates a stream of files to be used as a microscope simulator.
    :param file_path: file path to location of image test data set
    :param period: The time period between every image (setting to 0 gives minimal time period)
    :param binning: specify the binning (reduce the number of pixels to compress the image), this is given as an
    int
    :param color_channel: specify color channels, the channels are given as a list eg. ['1', '2'] (the Yokogawa
    microscope can have up to five color channels)
    :param send_to_target: specify if the simulator shall stream images somewhere else with streaming framework
    """
    files = os.listdir(file_path)
    print(files)
    stream_target = None

    stream_id = datetime.datetime.today().strftime('%Y_%m_%d__%H_%M_%S') + '_simulator_integration_test_' + 'll'

    if send_to_target == "yes":
        # connect to stream target:
        # stream_target = KafkaStreamTarget() # TODO - pick one here. (or pass it in).
        stream_target = HarmonicIOStreamTarget('130.239.81.126', 8080)
        print(stream_target)
        # topic = stream_target[0]
        # producer = stream_target[1]
        print("hoho")
    else:
        pass
    # producer = None
    # topic = None

    for file in files:
        if os.path.isfile(file_path + file):
            get_file(file, color_channel, file_path, binning, stream_id, stream_target)
        time.sleep(period)


def get_file(file, color_channel, file_path, binning, stream_id, stream_target=None):
    """
    This function takes one file, checks if it has the correct color channel, reads and converts the file and
    sends it to the streaming framework.
    """
    if file[-5] in color_channel:
        img = cv2.imread(file_path + file, -1)
        binned_img = block_reduce(img, block_size=(binning, binning), func=np.sum)
        if stream_target is not None:
            ret, jpeg = cv2.imencode('.tif', img_as_uint(binned_img))  # convert image file so it can be streamed
            print("size: {}".format(sys.getsizeof(jpeg.tobytes())))
            print(file)
            # print(topic)
            # print("prod: {} topic: {}".format(producer, topic))
            metadata = {
                'stream_id': stream_id,
                'timestamp': time.time(),
                'location': (12.34, 56.78),
            }

            stream_target.send_message(jpeg.tobytes(), file, metadata)
