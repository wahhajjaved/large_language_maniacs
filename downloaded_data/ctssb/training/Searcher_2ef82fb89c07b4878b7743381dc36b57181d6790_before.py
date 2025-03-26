# Dataset.py
# Written Ian Rankin October 2018
#
# Read in the dataset

import tensorflow as tf
import numpy as np



####################### Other utility

# jpegGraph
# write out a the graph operator to write a jpeg in tensorflow.
# must be passed an image tensor with 3 channels, and must be
# scaled between 0-255
# @param image - the image tensor
#
# @returns the operation object for creating the jpeg.
def jpegGraph(image):
    scaledImage = tf.cast(image * tf.constant(255.0, dtype=tf.float32), dtype=tf.uint8)
    op = tf.image.encode_jpeg(scaledImage, format='rgb', quality=100)

# write the jpeg given the graph operation and session given.
def writeJPEGGivenGraph(filepath, sess, jpegOp):
    encodedImage = sess.run(jpegOp)

    with open(filepath, 'wb') as fd:
        fd.write(encodedImage)

# write_jpeg
# Write a jpeg using tensorflow, the code should work on joker.
# @param filepath - filepath of the image to write to.
# @param data - the image data used to to try ot write using (numpy array)
# @param imageShape - the shape of the image to be outputed.
def write_jpeg(filepath, data, imageShape):
    g = tf.Graph()
    with g.as_default():
        data_t = tf.placeholder(tf.float32, shape=[imageShape[0], imageShape[1], imageShape[2]])
        scaledImage = tf.cast(data_t * tf.constant(255.0, dtype=tf.float32), dtype=tf.uint8)
        op = tf.image.encode_jpeg(scaledImage, format='rgb', quality=100)
        init = tf.global_variables_initializer()

    with tf.Session(graph=g) as sess:
        sess.run(init)
        data_np = sess.run(op, feed_dict={ data_t: data })
    print(type(data_np))
    with open(filepath, 'wb') as fd:
        fd.write(data_np)



########################### Read in training data.



# readData
# this function will read in the required data, and output
# numpy arrays of training data, and validation data.
#
# return    trainImages
#           trainLabels
#           validImages
#           validLabels
def readData():
    fileTrain = np.load('train.npz')
    fileValid = np.load('valid.npz')

    trainImages = fileTrain['x']
    trainLabels = fileTrain['y']

    validImages = fileValid['x']
    validLabels = fileValid['y']

    print(trainImages.shape)
    print(validImages.shape)

    #write_jpeg('test.jpg', trainImages[0], (405,720,3))
    #write_jpeg('test14.jpg', trainImages[14], (405,720,3))
    #write_jpeg('test16.jpg', trainImages[16], (405,720,3))
    #print(trainLabels)
    return trainImages, trainLabels, validImages, validLabels

# readDataNormalized
# this function will read in the required data, and output
# numpy arrays of training data, and validation data.
#
# return    trainImages
#           trainLabels
#           validImages
#           validLabels
def readDataNormalized():
    fileTrain = np.load('train.npz')
    fileValid = np.load('valid.npz')

    trainImages = fileTrain['x']
    trainLabels = fileTrain['y']

    validImages = fileValid['x']
    validLabels = fileValid['y']

    print(trainImages.shape)
    print(validImages.shape)

    # 1 indicates a person, 0 indicates no people
    totalImagesClass = np.sum(trainLabels, axis=0)
    totalImages = totalImagesClass[0] + totalImagesClass[1]

    trainImagesPeople = np.empty((totalImagesClass[1],trainImages.shape[1], \
        trainImages.shape[2], trainImages.shape[3]))

    trainImagesNoPeople = np.empty((totalImagesClass[0],trainImages.shape[1], \
        trainImages.shape[2], trainImages.shape[3]))

    iPeople = 0
    iNoPeople = 0
    # add images to list of either people or no people.
    for i in range(len(trainLabels)):
        if trainLabels[i][1] == 1:
            # people, so add the image to the list.
            trainImagesPeople[iPeople] = trainImages[i]
            iPeople += 1
        else:
            # no people, so add the image to that list.
            trainImagesNoPeople[iNoPeople] = trainImages[i]
            iNoPeople += 1

    return trainImagesPeople, trainImagesNoPeople, validImages, validLabels



########################### define batch functions

def getNextBatch(images, labels, batchSize):
    numOutputClasses = 2
    indicies = np.random.choice(len(images), batchSize, replace=False)

    miniBatchLabels = labels[indicies]



    # create one hot vector
    #oneHot = np.zeros((batchSize, numOutputClasses), np.float32)
    #for i in range(batchSize):
    #    oneHot[i][miniBatchLabels[i]] = 1.0

    return images[indicies], miniBatchLabels

# generateRandomBinaryWithSameTotalNumber
# This generates a vector of equally distributed binary numbers
# In other words in generates the same number of 1's as zeros,
# but does it as random of a was as possible
# @param num - the number of elements to generate.
#
# @return generated random binary vector.
def generateRandomBinaryWithSameTotalNumber(num):
    randVec = np.zeros(num, np.int)
    totalNumOne = 0
    totalNumOneAllowed = num // 2
    totalNumZero = 0
    totalNumZeroAllowed = num - totalNumOneAllowed
    for i in range(num):
        randBinary = random.randint(0,1)
        if randBinary == 1:
            if totalNumOne < totalNumOneAllowed:
                randBinary[i] = 1
                totalNumOne += 1
            else:
                randBinary[i] = 0
                totalNumZero += 1
        else:
            if totalNumZero < totalNumZeroAllowed:
                randBinary[i] = 0
                totalNumZero += 1
            else:
                randBinary[i] = 1
                totalNumOne += 1
    return randVec

# generateEpoch
# generates an epoch to train over.
# This function creates a random vector of selecting either the people or
# no people image for each epoch, then creates a vector of random choices the size
# of the smaller given class, which will generate a monte carlo sampling of
# the images to train without a bias in the training data (same number of classes per epoch)
# @param peopleImages - the list of all people images
# @param noPeopleImages - list of no People images.
# @param batchSize - the size of each batch
#
# @return - numberOfBatchesPerEpoch, epochTuple
#   epochTuple - (peopleImage, noPeopleImages, epochIndcies, epochSelector)
def generateEpoch(peopleImages, noPeopleImages, batchSize):
    minClassSize = int(np.min(len(peopleImages), len(noPeopleImages)))

    epochSelector = generateRandomBinaryWithSameTotalNumber(minClassSize * 2)

    # generate random indcies for epoch
    # will down sample larger class
    peopleIndcies = np.random.choice(len(peopleImages), minClassSize,replace=False)
    noPeopleIndcies = np.random.choice(len(noPeopleImages), minClassSize,replace=False)

    epochIndcies = np.empty(minClassSize * 2)

    iPeople = 0
    iNoPeople = 0
    for i in range(minClassSize*2):
        if epochSelector[i] == 1:
            epochIndcies[i] = peopleIndcies[iPeople]
            iPeople += 1
        else:
            epochIndcies[i] = noPeopleIndcies[iNoPeople]
            iNoPeople += 1

    # generate final epochTuple
    return (minClassSize*2) // batchSize, \
        (peopleImage, noPeopleImages, epochIndcies, epochSelector)

# epochTuple = (peopleImages, noPeopleImages, epochIndcies, epochSelector)
# 1 indicates people, 0 indicates no people

# getNextBatchNormalized
# returns the next training batch and updates the epoch
#
# @return batchImages, batchLabels, i
def getNextBatchEpoch(i, epochTuple, batchSize):
    numOutputClasses = 2
    if batchSize % 2 == 1:
        batchSize += 1

    imageSizeEpoch = epochTuple[0].shape
    size = (imageSizeEpoch[1], imageSizeEpoch[1], imageSizeEpoch[2])

    # get next batch of images
    batchImages = np.empty((batchSize,size[0],size[1],size[3]))
    batchLabels = np.zeros((batchSize, numOutputClasses))

    for j in range(batchSize):
        if epochTuple[3][i] == 1:
            # people
            batchImages[j] = epochTuple[0][i]
            batchLabels[j][1] = 1.0
        else:
            # no people
            batchImages[j] = epochTuple[1][i]
            batchLabels[j][0] = 1.0
        i += 1

    return batchImages, batchLabels, i

# Test code
#readData()
