"""
BN-V0
"""
import data_loader as dl
import network_bn_v0 as bnv0
import numpy as np
try: 
    import matplotlib.pyplot as plt
    canplot = True
except:
    canplot = False
import cPickle as pkl

import sys
import argparse
import os
from os.path import expanduser, sep
pklpath = expanduser("~") + sep + "repos" + sep + "batchnorm" + sep + "src" + sep


def run_batchnorm(params={}):

    
    t_img,t_label=dl.training_load()
    s_img,s_label=dl.test_load()

    with open(pklpath + 'initial_conf.pickle','rb') as f_init:
        data=pkl.load(f_init)

    for k,v in params.items():
        data[k]=v        

    training_index=data['training_index']
    testing_index=data['testing_index']
    train_input=np.array(t_img[training_index])
    train_label=np.array(t_label[training_index])
    test_input=np.array(s_img[testing_index])
    test_label=np.array(s_label[testing_index])

    layers=data['layers']
    weights=data['weights']
    bias=data['bias']
    gammas=data['gammas']
    learnrate=data['learnrate']
    stop_at=data['stop_at']

    test_check=bool(data['test_check'])
    train_check=bool(data['train_check'])
    save_file=bool(data['save_file'])
    dbrec=data['dbrec']
    try:
        plot_flag=data['plot_flag']
    except:
        plot_flag=False

    num_of_trains=len(train_input)
    num_of_tests=len(test_input)
    
    learnrate=data['learnrate']
    batchsize=60
    epochs=50

    test_check=True
    train_check=False
    
    network=bnv0.BNv0(layers,learnrate,batchsize,epochs,weights,bias,gammas,dbrec=dbrec,stop_at=stop_at,comment=cmt)

    network.sgd(train_input,train_label,test_input,test_label,
                test_check=test_check,train_check=train_check)

    if test_check:
        test_accu=np.array(network.test_accu)
        test_cost=np.array(network.test_cost)
        print 'accuracy:'
        print test_accu
        #--------------------------------

        if plot_flag and canplot:
            xaxis=np.arange(epochs)

            fig=plt.figure(1)
            plt.suptitle('TestSet')
            plt.subplot(2,1,1)
            plt.plot(xaxis,test_accu,'r-o')
            plt.grid()
            plt.ylabel('Accuracy')
            plt.xlabel('Epochs')

            plt.subplot(2,1,2)
            plt.plot(xaxis,test_cost,'r-o')
            plt.grid()
            plt.ylabel('Loss')
            plt.xlabel('Epochs')

            plt.savefig('../results/bnv0_TestSet.png')
            plt.show()

    if train_check:
        accu_train=np.array(network.accu_train)
        cost_train=np.array(network.cost_train)
        print 'accuracy:'
        print accu_train
        #--------------------------------
        if plot_flag and canplot:
            xaxis=np.arange(epochs)
            
            fig=plt.figure(2)
            plt.suptitle('TrainSets')
            plt.subplot(2,1,1)
            plt.plot(xaxis,accu_train,'r-o')
            plt.grid()
            plt.ylabel('Accuracy')
            plt.xlabel('Epochs')

            plt.subplot(2,1,2)
            plt.plot(xaxis,cost_train,'r-o')
            plt.grid()
            plt.ylabel('Loss')
            plt.xlabel('Epochs')

            plt.savefig('../results/bnv0_TrainSet.png')
            plt.show()
    
    if save_file:    
        data={"number_of_trains":num_of_trains,
              "number_of_tests":num_of_tests,
              "layers":layers,
              "learnrate":learnrate,
              "mini-batch size":batchsize,
              "epochs":epochs,
              "test_accu":test_accu,
              "test_cost":test_cost
          }
        with open("../results/bnv0_accuracy.pickle",'w') as frec:
            pkl.dump(data,frec)



if __name__=="__main__":
    parser = argparse.ArgumentParser(description='Learn mNIST with batchnorm backprop')
    parser.add_argument('--lr', dest='learnrate', type=float, default=0.1,
                       help='The learning rate of the network. default=0.1')
    parser.add_argument('--db', dest='dbrec', type=int, default=0,
                       help='Record results to a database. default=0, set to 1 to record. Must configure ~/.dbconf to use')
    parser.add_argument('--test_check', dest='test_check', type=int, default=1,
                       help='Check test samples and make a plot. default=1.')
    parser.add_argument('--train_check', dest='train_check', type=int, default=1,
                       help='Check test samples and make a plot. default=1 (set to 0 to not check).')
    parser.add_argument('--save_file', dest='save_file', type=int, default=1,
                       help='save output to file. default=1 (set to 0 to not save).')
    parser.add_argument('--make_plots', dest='plot_flag', type=int, default=0,
                       help='plot results output to file. default=0 (set to 0 to not save).')
    parser.add_argument('--comment', dest='comment', type=str, default='',
                       help='A comment that will get saved to the DB')



    params = vars(parser.parse_args())

    run_batchnorm()

