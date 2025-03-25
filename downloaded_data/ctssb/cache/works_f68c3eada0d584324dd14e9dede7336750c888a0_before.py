import numpy as np
import chainer
import chainer.variable as variable
from chainer.functions.activation import lstm
from chainer import cuda, Function, gradient_check, report, training, utils, Variable
from chainer import datasets, iterators, optimizers, serializers
from chainer import Link, Chain, ChainList
import chainer.functions as F
import chainer.links as L
from collections import OrderedDict
import logging
import time
from utils import to_device

class EntropyRegularizationLoss(Chain):

    def __init__(self, test=False):
        super(EntropyRegularizationLoss, self).__init__()
        self.loss = None
        
    def __call__(self, y, ):
        bs = y.data.shape[0]
        d = np.prod(y.data.shape[1:])

        y_normalized = F.softmax(y)
        y_log_softmax = F.log_softmax(y)
        self.loss = - F.sum(y_normalized * y_log_softmax) / bs / d

        return self.loss

class ReconstructionLoss(Chain):

    def __init__(self,
                     ):
        super(ReconstructionLoss, self).__init__()
        self.loss = None
        
    def __call__(self, x_recon, x):
        bs = x.shape[0]
        d = np.prod(x.shape[1:])
        self.loss = F.mean_squared_error(x_recon, x) / d

        return self.loss

class InvariantReconstructionLoss(Chain):

    def __init__(self,
                     ):
        super(InvariantReconstructionLoss, self).__init__()
        self.loss = None
        
    def __call__(self, x_recon, x):
        bs = x.shape[0]
        d = np.prod(x.shape[1:])

        if x.shape[1:] == 3:
            h_recon = F.average_pooling_2d(x_recon, (2, 2))
            h = F.average_pooling_2d(x, (2, 2))
            self.loss = F.mean_squared_error(x_recon, x) / d
        else:
            self.loss = F.mean_squared_error(x_recon, x) / d

        return self.loss

class ReconstructionLoss1(Chain):

    def __init__(self,
                     ):
        super(ReconstructionLoss1, self).__init__()
        self.loss = None
        
    def __call__(self, x_recon, x):
        bs = x.shape[0]
        d = np.prod(x.shape[1:])
        self.loss = F.mean_absolute_error(x_recon, x) / d

        return self.loss

class GANLoss(Chain):

    def __init__(self, ):
        super(GANLoss, self).__init__(
        )
        
    def __call__(self, d_x_gen, d_x_real=None):
        bs_d_x_gen = d_x_gen.shape[0]
        if d_x_real is not None:
            bs_d_x_real = d_x_real.shape[0]
            loss = F.sum(F.log(d_x_real)) / bs_d_x_real \
                   + F.sum(F.log(1 - d_x_gen)) / bs_d_x_gen
            return - loss  # to minimize
            
        else:
            loss = F.sum(F.log(d_x_gen)) / bs_d_x_gen
            return - loss  # to minimize (reverse trick)

class WGANLoss(Chain):
    """Wasserstein GAN loss
    """
    def __init__(self, ):
        super(WGANLoss, self).__init__(
        )
        
    def __call__(self, d_x_gen, d_x_real=None):
        bs_d_x_gen = d_x_gen.shape[0]
        if d_x_real is not None:
            bs_d_x_real = d_x_real.shape[0]
            loss = F.sum(d_x_real) / bs_d_x_real - F.sum(d_x_gen) / bs_d_x_gen
            return  - loss  # to minimize
            
        else:
            loss = F.sum(d_x_gen) / bs_d_x_gen
            return - loss  # to minimize (reverse trick)
        
class LSGANLoss(Chain):
    """Least Square GAN Loss
    """
    def __init__(self, ):
        super(LSGANLoss, self).__init__(
        )
        
    def __call__(self, d_x_gen, d_x_real=None):
        bs_d_x_gen = d_x_gen.shape[0]
        if d_x_real is not None:
            bs_d_x_real = d_x_real.shape[0]
            loss = F.sum(F.square(d_x_real - 1)) / bs_d_x_real /2 \
                   + F.sum(F.square(d_x_gen)) / bs_d_x_gen / 2
            return loss
            
        else:
            loss = F.sum(F.square(d_x_gen - 1)) / bs_d_x_gen / 2
            return loss

class MeanDistanceLoss(Chain):
    def __init__(self, ):
        super(MeanDistanceLoss, self).__init__(
        )
        
    def __call__(self, h):
        shape = h.shape
        m = F.sum(h, axis=0) / shape[0]
        M = F.broadcast_to(m, shape)
        D = -F.sum(h - M) / np.prod(shape)
        return D
    
class DistanceLoss(Chain):
    def __init__(self, ):
        super(DistanceLoss, self).__init__(
        )
        
    def __call__(self, h):
        shape = h.shape
        h = F.reshape(h, (shape[0], np.prod(shape[1:])))
        h_norm = F.batch_l2_norm_squared(h) ** 2
        bs = shape[0]
        h0 = F.broadcast_to(h_norm, (bs, bs))
        h1 = F.broadcast_to(F.transpose(h_norm), (bs, bs))
        hh = F.linear(h, h)
        D = h0 + h1 - 2 * hh
        D = F.sum(D) / np.prod(h.shape)
        
        return D
    
    

