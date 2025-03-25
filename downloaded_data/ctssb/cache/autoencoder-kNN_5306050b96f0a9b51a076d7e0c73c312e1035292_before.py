__author__ = 'Jinyi Zhang'

import os
import pickle
import random

import numpy as np
import matplotlib.pyplot as plt

import tensorflow as tf

from tf_cifar import Autoencoder
from tf_cifar import cal_loss

from cifar import CifarPreprocess
from cifar import reshape_cifar

def cnn_nca_cifar_train():
    cp = CifarPreprocess()

    batchs = [1, 2, 3, 4, 5]
    cp.load_cifar_data(batchs)

    x_train_float = cp.X_train.astype(np.float) / 255.
    x_test_float = cp.X_test.astype(np.float) / 255.

    x_train_list = [reshape_cifar(x) for x in x_train_float]
    x_test_list = [reshape_cifar(x) for x in x_test_float]
    
    m = len(x_train_list)
    spl = int(m * 0.9)

    x_train = np.array(x_train_list)[:spl]
    x_validation = np.array(x_train_list)[spl:]
    x_test = np.array(x_test_list)

    y_train = cp.y_train[:spl]
    y_validation = cp.y_train[spl:]
    y_test = cp.y_test

    auto = Autoencoder()

    learning_rate = 0.0001
    optimizer_loss = tf.train.AdamOptimizer(learning_rate).minimize(auto.loss)

    # Add ops to save and restore all the variables.
    saver = tf.train.Saver()

    sess = tf.Session()
    sess.run(tf.global_variables_initializer())


    # Restored the pre-trained model
    saver.restore(sess, "./models/tf_cifar/model.ckpt")

    batch_size = 1000

    # Report the loss
    validation_loss, reconstruction_error, nca_obj = cal_loss(auto, sess, x_test, y_test, batch_size)
    print("Report the initial test loss: ")
    print(validation_loss, reconstruction_error, nca_obj)


    # Train step
    batch_size = 1500
    epochs = 1
    minimum_loss = np.inf

    m = len(y_train)
    index_list = list(range(m))

    k = m // batch_size

    for epoch_i in range(epochs):
        
        random.shuffle(index_list)

        for i in range(k):
            sel = index_list[i * batch_size:(i + 1) * batch_size]
            batch_x = x_train[sel]
            batch_y = y_train[sel]

            sess.run(optimizer_loss, feed_dict={auto.x: batch_x, auto.y: batch_y})

        validation_loss, reconstruction_error, nca_obj = cal_loss(auto, sess, 
                                                            x_validation, y_validation, batch_size)

        print(epoch_i, validation_loss, reconstruction_error, nca_obj)

        if validation_loss < minimum_loss:
            minimum_loss = validation_loss
            save_path = saver.save(sess, "./models/tf_cifar_train/model.ckpt")

    # Restored the pre-trained model
    saver.restore(sess, "./models/tf_cifar_train/model.ckpt")

    # Report the loss    
    validation_loss, reconstruction_error, nca_obj = cal_loss(auto, sess, x_test, y_test, batch_size)
    print("Report the test loss of the final model: ")
    print(validation_loss, reconstruction_error, nca_obj)


    # Encode training and testing samples
    # Encode the images
    encoding_train_imgs_path = './data/CIFAR_encoding/tf_train.encoding'
    encoding_test_imgs_path = './data/CIFAR_encoding/tf_test.encoding'
    train_labels_path = './data/CIFAR_encoding/tf_train.labels'
    test_labels_path = './data/CIFAR_encoding/tf_test.labels'

    batch_size = 1000
    encoded_imgs_list = []
    labels_list = []

    m = len(y_train)
    index_list = list(range(m))
    k = m // batch_size

    for i in range(k):
        sel = index_list[i * batch_size:(i + 1) * batch_size]
        batch_x = x_train[sel]
        batch_y = y_train[sel]

        encoded_batches = sess.run(auto.encoded_x, feed_dict={auto.x: batch_x, auto.y: batch_y})
        
        encoded_imgs_list.append(encoded_batches)
        labels_list.append(batch_y)


    m = len(y_validation)
    index_list = list(range(m))
    k = m // batch_size
    for i in range(k):
        sel = index_list[i * batch_size:(i + 1) * batch_size]
        batch_x = x_train[sel]
        batch_y = y_train[sel]
        
        encoded_batches = sess.run(auto.encoded_x, feed_dict={auto.x: batch_x, auto.y: batch_y})

        encoded_imgs_list.append(encoded_batches)
        labels_list.append(batch_y)

    encoded_train_imgs = np.array(encoded_imgs_list)
    m, n, d = encoded_train_imgs.shape
    encoded_train_imgs = encoded_train_imgs.reshape(m * n, d)
    print(encoded_train_imgs.shape)

    train_labels = np.array(labels_list).flatten()
    print(train_labels.shape)

    # Save the encoded imgs
    pickle.dump(encoded_train_imgs, open(encoding_train_imgs_path, 'wb'))
    pickle.dump(train_labels, open(train_labels_path, 'wb'))


    encoded_imgs_list = []
    labels_list = []
    m = len(y_test)
    index_list = list(range(m))
    k = m // batch_size

    for i in range(k):
        sel = index_list[i * batch_size:(i + 1) * batch_size]
        batch_x = x_train[sel]
        batch_y = y_train[sel]

        encoded_batches = sess.run(auto.encoded_x, feed_dict={auto.x: batch_x, auto.y: batch_y})

        encoded_imgs_list.append(encoded_batches)
        labels_list.append(batch_y)

    encoded_test_imgs = np.array(encoded_imgs_list)
    m, n, d = encoded_test_imgs.shape
    encoded_test_imgs = encoded_test_imgs.reshape(m * n, d)
    print(encoded_test_imgs.shape)

    test_labels = np.array(labels_list).flatten()
    print(test_labels.shape)

    # Save the encoded imgs
    pickle.dump(encoded_test_imgs, open(encoding_test_imgs_path, 'wb'))
    pickle.dump(test_labels, open(test_labels_path, 'wb'))

    print("Done encoding. Show some reconstructed images.")

    n = 10
    reconstructed_imgs = sess.run(auto.reconstructed_x, feed_dict={auto.x: x_test[:10]})

    plt.figure(figsize=(20, 4))
    for i in range(n):
        # display original
        ax = plt.subplot(2, n, i + 1)
        plt.imshow(x_test[i].reshape(32, 32, 3))
        plt.gray()
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)

        # display reconstruction
        ax = plt.subplot(2, n, i + 1 + n)

        plt.imshow(reconstructed_imgs[i].reshape(32, 32, 3))

        plt.gray()
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)

    plt.savefig('./tmp/tf_nca_cifar.png')



def main():
    cnn_nca_cifar_train()
    
    import gc
    gc.collect()

if __name__ == '__main__':
    main()
