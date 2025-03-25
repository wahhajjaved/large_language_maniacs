#coding: UTF-8

" py 2222222222222222222222222222222222222 "


import os

import numpy as np

import caffe

def load_net(model_dir, window_size=65, use_GPU=True):
    model_file = list(filter(lambda i: '.caffemodel' in i, os.listdir(model_dir)))[0]
    use_GPU and caffe.set_mode_gpu() or caffe.set_mode_cpu()
    net = caffe.Classifier(os.path.join(model_dir, 'deploy.prototxt'),
                           os.path.join(model_dir, model_file),
                           image_dims=(window_size, window_size),
                           input_scale=1, raw_scale=255)
    return net

def tolist(data):
    for x in data:
        yield x

def predict(net, npy_files, max_total_num):
    ys = []
    for npyfile in npy_files:
        X = np.load(npyfile)
        print npyfile, X.shape[0]
        window_size = X.shape[1]
        X = X.reshape((X.shape[0], window_size, window_size, 1))
        ys.append(net.predict(tolist(X)))

