#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging

if 'logger' not in locals():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s %(filename)s:%(lineno)s - %(funcName)20s() %(levelname)-8s %(message)s')
    # StreamHandler
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    # FileHandler
    fh = logging.FileHandler('log.txt', 'a')
    fh.setFormatter(formatter)
    fh.setLevel(logging.DEBUG)
    logger.addHandler(fh)

from main import FullPipeline, Dataset
from main import preprocess, pretty_pipeline
from main import eval_with_semeval_script
from sklearn import metrics
import resources as res
import pickle
from keras.preprocessing.text import Tokenizer
from keras.preprocessing.sequence import pad_sequences
from keras.utils.np_utils import to_categorical
from keras.layers import Dense, Input, Flatten
from keras.layers import Conv1D, MaxPooling1D, Embedding
from keras.layers import Convolution1D
from keras.layers import Activation, Dropout, merge
from keras.models import Model, Graph, Sequential
import numpy as np

from keras.callbacks import BaseLogger


class TestEpoch(BaseLogger):
    def __init__(self, pipeline):
        self.pipeline = pipeline

    def on_epoch_end(self, epoch, logs={}):
        super().on_epoch_end(epoch, logs)
        self.pipeline.run_test()
        self.pipeline.print_results()


class CNNBase(FullPipeline):
    def __init__(self,
                 train_truncate=0, test_truncate=0,
                 only_uid=None,
                 train_only_labels=['positive', 'negative', 'neutral'],
                 test_only_labels=['positive', 'negative', 'neutral'],
                 repreprocess=False,
                 nb_epoch=2, batch_size=128,
                 max_sequence_length=1000,
                 shuffle=True,
                 max_nb_words=20000,
                 embedding_dim=100,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.train_truncate = train_truncate
        self.test_truncate = test_truncate
        self.only_uid = only_uid
        self.train_only_labels = train_only_labels
        self.test_only_labels = test_only_labels
        self.repreprocess = repreprocess
        self.nb_epoch = nb_epoch
        self.batch_size = batch_size
        self.max_sequence_length = max_sequence_length
        self.max_nb_words = max_nb_words
        self.embedding_dim = embedding_dim
        self.shuffle = shuffle

    def load_resources(self):
        super().load_resources()
        logger.info('Load the corpus')
        with open(preprocess(res.train_path, force=self.repreprocess), 'rb') as p_file:
            self.train = pickle.load(p_file)
        with open(preprocess(res.test_path, force=self.repreprocess), 'rb') as p_file:
            self.test = pickle.load(p_file)
            self.train.truncate(self.train_truncate)
            self.test.truncate(self.test_truncate)
            self.train.filter_label(self.train_only_labels)
            self.test.filter_label(self.test_only_labels)
        if self.only_uid is not None:
            self.test.filter_uid(self.only_uid)


        self.texts = [d['tok'] for d in self.train.data]
        self.labels_index = dict([(name, nid) for nid, name in enumerate(self.train.labels)])
        self.labels = to_categorical(self.train.target)
        logger.info('Found %s texts', len(self.texts))

        logger.info('Vectorize the text samples into a 2D integer tensor')
        self.tokenizer = Tokenizer(nb_words=self.max_nb_words)
        self.tokenizer.fit_on_texts(self.texts)
        self.sequences = self.tokenizer.texts_to_sequences(self.texts)

        self.word_index = self.tokenizer.word_index
        logger.info('Found %s unique tokens.', len(self.word_index))

        self.train_data = pad_sequences(self.sequences, maxlen=self.max_sequence_length)

        logger.info('Shape of data tensor: %s', self.train_data.shape)
        logger.info('Shape of label tensor: %s', self.labels.shape)
        logger.info('label index: %s', self.labels_index)

        # logger.info('Preparing embedding matrix.')
        self.nb_words = min(self.max_nb_words, len(self.word_index))
        # self.embeddings_index = {}
        # self.embedding_matrix = np.zeros((self.nb_words + 1, self.EMBEDDING_DIM))
        # for word, i in self.word_index.items():
        #     if i > self.MAX_NB_WORDS:
        #         continue
        #     self.embedding_vector = self.embeddings_index.get(word)
        #     if self.embedding_vector is not None:
        #         # words not found in embedding index will be all-zeros.
        #         self.embedding_matrix[i] = self.embedding_vector

        # load pre-trained word embeddings into an Embedding layer
        # note that we set trainable = False so as to keep the embeddings fixed
        self.embedding_layer = Embedding(self.nb_words + 1,
                                         self.embedding_dim,
                                         # weights=[self.embedding_matrix],
                                         input_length=self.max_sequence_length,
                                         # trainable=False
        )

    def build_pipeline(self):
        super().build_pipeline()
        self.sequence_input = Input(shape=(self.max_sequence_length,), dtype='int32')
        self.embedded_sequences = self.embedding_layer(self.sequence_input)
        x = Conv1D(128, 5, activation='relu')(self.embedded_sequences)
        x = MaxPooling1D(5)(x)
        x = Conv1D(128, 5, activation='relu')(x)
        x = MaxPooling1D(5)(x)
        x = Conv1D(128, 5, activation='relu')(x)
        x = MaxPooling1D(35)(x)  # global max pooling
        x = Flatten()(x)
        x = Dense(128, activation='relu')(x)
        self.preds = Dense(len(self.labels_index), activation='softmax')(x)

        self.model = Model(self.sequence_input, self.preds)
        self.model.compile(loss='categorical_crossentropy',
                           optimizer='rmsprop',
                           metrics=['acc'])

    def run_train(self):
        super().run_train()
        self.model.fit(self.train_data, self.labels,
                       nb_epoch=self.nb_epoch, batch_size=self.batch_size,
                       callbacks=[TestEpoch(self)],
                       shuffle=self.shuffle)

    def run_test(self):
        super().run_test()
        self.test_texts = [d['tok'] for d in self.test.data]
        self.test_sequences = self.tokenizer.texts_to_sequences(self.test_texts)
        self.test_data = pad_sequences(self.test_sequences, maxlen=self.max_sequence_length)
        logger.info('Shape of data tensor: %s', self.test_data.shape)
        self.t_predicted = self.model.predict(self.test_data, verbose=1)
        if self.t_predicted.shape[-1] > 1:
            self.predicted = self.t_predicted.argmax(axis=-1)
        else:
            self.predicted = (self.t_predicted > 0.5).astype('int32')

    def print_results(self):
        super().print_results()
        logger.info('\n' +
                    metrics.classification_report(self.test.target, self.predicted,
                                                  target_names=self.test.labels))

        try:
            logger.info('\n' +
                        eval_with_semeval_script(self.test, self.predicted))
        except:
            pass


class CNNChengGuo(CNNBase):
    """More or less c/c from https://github.com/bwallace/CNN-for-text-classification/blob/master/CNN_text.py
An Keras implementation of Cheng Guao CNN for sentence classification.

I add minor adjustments to make it work for the Semeval Sentiment Analsysis tasks.
    """
    def __init__(self, ngram_filters=[3, 4, 5], nb_filter=100, dropout=0.0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ngram_filters = ngram_filters
        self.nb_filter = nb_filter
        self.dropout = dropout

    def build_pipeline(self):
        super().build_pipeline()
        # again, credit to Cheng Guo

        self.sequence_input = Input(shape=(self.max_sequence_length,), dtype='int32')
        self.embedded_sequences = self.embedding_layer(self.sequence_input)
        x = Dropout(self.dropout)(self.embedded_sequences)
        ngram_filters = []
        for n_gram in self.ngram_filters:
            x1 = Convolution1D(nb_filter=self.nb_filter,
                               filter_length=n_gram,
                               border_mode='valid',
                               activation='relu',
                               subsample_length=1)(x)
            x1 = MaxPooling1D(pool_length=self.max_sequence_length - n_gram + 1)(x1)
            x1 = Flatten()(x1)
            ngram_filters.append(x1)
        x = merge(ngram_filters, mode='concat')
        x = Dropout(self.dropout)(x)
        self.preds = Dense(len(self.labels_index), activation='sigmoid')(x)
        self.model = Model(self.sequence_input, self.preds)

        print('model built')
        print(self.model.summary())
        self.model.compile(loss='categorical_crossentropy',
                           optimizer='rmsprop',
                           metrics=['acc'])
