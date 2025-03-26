import numpy as np
import os
import json
import random

from mimic3models.feature_extractor import extract_features


def convert_to_dict(data, header, channel_info):
    """ convert data from readers output in to array of arrays format """
    ret = [[] for i in range(data.shape[1] - 1)]
    for i in range(1, data.shape[1]):
        ret[i-1] = [(t, x) for (t, x) in zip(data[:, 0], data[:, i]) if x != ""]
        channel = header[i]
        if (len(channel_info[channel]['possible_values']) != 0):
            ret[i-1] = map(lambda x: (x[0], channel_info[channel]['values'][x[1]]), ret[i-1])
        ret[i-1] = map(lambda x: (float(x[0]), float(x[1])), ret[i-1])
    return ret


def extract_features_from_rawdata(chunk, header, period, features):
    with open(os.path.join(os.path.dirname(__file__), "channel_info.json")) as channel_info_file:
        channel_info = json.loads(channel_info_file.read())
    data = [convert_to_dict(X, header, channel_info) for X in chunk]
    return extract_features(data, period, features)


def sort_and_shuffle(data, batch_size):
    """ Sort data by length, then make batches and shuffle them
        data is tuple (X, y)
    """
    assert(len(data) == 2)
    data = zip(*data)
    random.shuffle(data)

    old_size = len(data)
    rem = old_size % batch_size
    head = data[:old_size - rem]
    tail = data[old_size - rem:]
    data = []

    head.sort(key=(lambda x: x[0].shape[0]))

    size = len(head)
    mas = [head[i : i+batch_size] for i in range(0, size, batch_size)]
    random.shuffle(mas)

    for x in mas:
        data += x
    data += tail
    # NOTE: we assume that we will not use cycling in batch generator
    # so all examples in one batch will have more or less the same context lenghts

    data = zip(*data)
    return data


def add_common_arguments(parser):
    """ Add all the parameters which are common across the tasks
    """
    parser.add_argument('--network', type=str, required=True)
    parser.add_argument('--dim', type=int, default=256,
                        help='number of hidden units')
    parser.add_argument('--depth', type=int, default=1,
                        help='number of bi-LSTMs')
    parser.add_argument('--epochs', type=int, default=100,
                        help='number of chunks to train')
    parser.add_argument('--load_state', type=str, default="",
                        help='state file path')
    parser.add_argument('--mode', type=str, default="train",
                        help='mode: train or test')
    parser.add_argument('--batch_size', type=int, default=64)
    parser.add_argument('--l2', type=float, default=0, help='L2 regularization')
    parser.add_argument('--l1', type=float, default=0, help='L1 regularization')
    parser.add_argument('--save_every', type=int, default=1,
                        help='save state every x epoch')
    parser.add_argument('--prefix', type=str, default="",
                        help='optional prefix of network name')
    parser.add_argument('--dropout', type=float, default=0.0)
    parser.add_argument('--rec_dropout', type=float, default=0.0,
                        help="dropout rate for recurrent connections")
    parser.add_argument('--batch_norm', type=bool, default=False,
                        help='batch normalization')
    parser.add_argument('--timestep', type=float, default=0.8,
                        help="fixed timestep used in the dataset")
    parser.add_argument('--imputation', type=str, default='previous')
    parser.add_argument('--small_part', dest='small_part', action='store_true')
    parser.add_argument('--whole_data', dest='small_part', action='store_false')
    parser.add_argument('--optimizer', type=str, default='adam')
    parser.add_argument('--lr', type=float, default=0.001, help='learning rate')
    parser.add_argument('--beta_1', type=float, default=0.9,
                        help='beta_1 param for Adam optimizer')
    parser.add_argument('--verbose', type=int, default=2)
    parser.add_argument('--size_coef', type=float, default=4.0)
    parser.set_defaults(small_part=False)
