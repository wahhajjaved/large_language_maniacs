import numpy as np
import _pickle as cPickle
import hickle
import os

def load_pickle(path):
    with open(path, 'rb') as f:
        file = cPickle.load(f)
        print ('Loaded %s..' %path)
        return file

def save_pickle(data, path):
    with open(path, 'wb') as f:
        cPickle.dump(data, f)
        print ('Saved %s..' %path)
