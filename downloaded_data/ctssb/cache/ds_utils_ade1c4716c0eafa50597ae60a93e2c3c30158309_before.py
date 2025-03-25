# -*- encoding: utf-8 -*-

"""
Author: Woody
Descrption: A module for resnet of MLP and Conv1D
"""


import os
import sys
reload(sys)
sys.setdefaultencoding('utf-8')

import keras
from keras.layers import Input, Dense, add, Dropout
from keras.layers.normalization import BatchNormalization
from keras.layers.advanced_activations import PReLU

def _bn_relu(input):
    """
    Parameters:
        input: input
    Returns:
        BN + PRELU
    """
    norm = BatchNormalization()(input)
    return Dropout(0.6)(PReLU()(norm))

def _mlp_bn_relu(hiddens):
    """
    customize layer
    """

    def f(input):
        mlp = Dense(hiddens, kernel_regularizer=keras.regularizers.l2(0.01))(input)
        return _bn_relu(mlp)
    return f

def _conv1d_bn_relu():
    """
    customize layer
    """
    pass

def _bn_relu_mlp(hiddens):
    """
    customize layer
    """
    def f(input):
        act = _bn_relu(input)
        return Dense(hiddens, kernel_regularizer=keras.regularizers.l2(0.01))(act)
    return f

def _bn_relu_conv1d():
    """
    customize layer
    """
    pass

def _mlp_residual_block(hiddens, repeat, is_first_layer=False):
    """
    customize layer
    """
    def f(input):
        mlp = input
        for index in range(repeat):
            input = mlp
            if is_first_layer and index == 0:
                mlp = Dense(hiddens, kernel_regularizer=keras.regularizers.l2(0.01))(input)
            else:
                mlp = _bn_relu_mlp(hiddens)(input)

            residual = _bn_relu_mlp(hiddens)(input)
            mlp = _shortcut(input, residual)

        return mlp
    return f

def _conv1d_residual_block():
    """
    customize layer
    """
    pass

def _shortcut(input, residual):
    return add([input, residual])

class ResNet(object):
    @staticmethod
    def build_mlp(input_layer, hiddens, repetitions):
        block = _mlp_bn_relu(hiddens)(input_layer)
        for index, value in enumerate(repetitions):
            block = _mlp_residual_block(hiddens, value, index == 0)(block)
        block = _bn_relu(block)
        return block

    @staticmethod
    def build_conv1d():
        pass

    @staticmethod
    def build_resnet_mlp(input_layer, hiddens):
        return ResNet.build(input_layer, hiddens, [2, 2, 2, 2])

    @staticmethod
    def build_resnet_conv1d():
        pass
