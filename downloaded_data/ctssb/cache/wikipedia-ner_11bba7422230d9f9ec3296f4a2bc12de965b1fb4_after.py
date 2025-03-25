# -*- coding: utf-8 -*-

from __future__ import absolute_import, print_function, unicode_literals

import tensorflow as tf
import numpy as np
import os
import sys
from sklearn.metrics import accuracy_score, precision_score, recall_score
from tqdm import tqdm
from .base import BaseClassifier


class MultilayerPerceptron(BaseClassifier):
    def __init__(self, dataset, labels, train_indices, test_indices, validation_indices, saves_dir, results_dir,
                 experiment_name, layers, learning_rate=0.01, training_epochs=1500, batch_size=2000, loss_report=50,
                 pre_weights=None, pre_biases=None, save_model=False):
        super(MultilayerPerceptron, self).__init__(dataset, labels, train_indices, test_indices, validation_indices)

        assert batch_size <= self.train_dataset.shape[0]

        self.X = tf.placeholder(tf.float32, shape=(None, self.input_size), name='X')
        self.y = tf.placeholder(tf.float32, shape=(None, self.output_size), name='y')
        self.training_epochs = training_epochs
        self.batch_size = batch_size
        self.train_offset = 0

        self.layers = [self.X]
        self.weights = []
        self.biases = []

        # Create the layers
        for layer_idx, (size_prev, size_current) in enumerate(zip([self.input_size] + layers, layers)):
            print('Creating hidden layer {:02d}: {} -> {}'.format(layer_idx, size_prev, size_current), file=sys.stderr)

            layer_name = 'hidden_layer_{:02d}'.format(layer_idx)

            with tf.name_scope(layer_name):
                if pre_weights and layer_name in pre_weights:
                    weights = tf.Variable(pre_weights[layer_name], name='weights')
                else:
                    weights = tf.Variable(
                        tf.truncated_normal([size_prev, size_current],
                                            stddev=1.0 / np.sqrt(size_prev)),
                        name='weights'
                    )

                if pre_biases and layer_name in pre_biases:
                    biases = tf.Variable(pre_biases[layer_name], name='biases')
                else:
                    biases = tf.Variable(tf.zeros([size_current]), name='biases')

                layer = tf.nn.relu(tf.matmul(self.layers[-1], weights) + biases)
                self.weights.append(weights)
                self.biases.append(biases)
                self.layers.append(layer)

        # The last layer is for the classifier
        with tf.name_scope('softmax_layer'):
            print('Creating softmax layer: {} -> {}'.format(layers[-1], self.output_size), file=sys.stderr)
            weights = tf.Variable(
                tf.truncated_normal([layers[-1], self.output_size],
                                    stddev=1.0 / np.sqrt(layers[-1])),
                name='weights'
            )
            biases = tf.Variable(tf.zeros([self.output_size]), name='biases')
            self.y_logits = tf.matmul(self.layers[-1], weights) + biases

        self.loss = tf.reduce_mean(
            tf.nn.softmax_cross_entropy_with_logits(self.y_logits, self.y),
            name='cross_entropy_mean_loss'
        )
        self.y_pred = tf.argmax(tf.nn.softmax(self.y_logits), 1, name='y_predictions')

        self.learning_rate = tf.Variable(learning_rate, trainable=False)
        global_step = tf.Variable(0, name='global_step', trainable=False)

        # Add a scalar summary for the snapshot loss.
        tf.scalar_summary(self.loss.op.name, self.loss)
        self.train_step = tf.train.AdamOptimizer(self.learning_rate).minimize(self.loss, global_step=global_step)

        self.init = tf.initialize_all_variables()

        # results and saves
        self.saves_dir = saves_dir
        self.experiment_name = experiment_name
        self.results_dir = results_dir
        self.results = dict(
            loss=[],
            train_accuracy=[],
            test_accuracy=[],
            validation_accuracy=[],
            train_precision=[],
            test_precision=[],
            validation_precision=[],
            train_recall=[],
            test_recall=[],
            validation_recall=[]
        )
        self.loss_report = loss_report
        self.saver = tf.train.Saver() if save_model else None

    def _next_batch(self):
        start = self.train_offset
        self.train_offset += self.batch_size

        if self.train_offset > self.train_dataset.shape[0]:
            perm = np.arange(self.train_dataset.shape[0])
            np.random.shuffle(perm)
            self.train_dataset = self.train_dataset[perm]
            self.train_labels = self.train_labels[perm]
            start = 0
            self.train_offset = self.batch_size

        end = self.train_offset

        one_hot_labels = np.eye(self.output_size, dtype=self.train_dataset.dtype)[self.train_labels[start:end]]

        if hasattr(self.train_dataset, 'toarray'):
            return self.train_dataset[start:end].toarray(), one_hot_labels
        else:
            return self.train_dataset[start:end], one_hot_labels

    def _evaluate(self, sess, dataset, labels, dataset_name):
        y_pred = np.zeros(dataset.shape[0], dtype=np.int32)

        print('Running evaluation for dataset {}'.format(dataset_name), file=sys.stderr)
        for step in tqdm(np.arange(dataset.shape[0], step=self.batch_size)):
            dataset_chunk = dataset[step:min(step+self.batch_size, dataset.shape[0])]
            feed_dict = {
                self.X: dataset_chunk.toarray() if hasattr(dataset_chunk, 'toarray') else dataset_chunk
            }

            y_pred[step:min(step+self.batch_size, dataset.shape[0])] = sess.run(self.y_pred, feed_dict=feed_dict)

        return accuracy_score(labels, y_pred.astype(labels.dtype)), \
            precision_score(labels, y_pred.astype(labels.dtype), average=None,
                            labels=np.arange(self.classes.shape[0])), \
            recall_score(labels, y_pred.astype(labels.dtype), average=None, labels=np.arange(self.classes.shape[0]))

    def _add_results(self, dataset, accuracy, precision, recall):
        self.results['{}_accuracy'.format(dataset)].append(accuracy)
        self.results['{}_precision'.format(dataset)].append(precision)
        self.results['{}_recall'.format(dataset)].append(recall)

    def _save_results(self):
        header = ','.join(self.classes).encode('utf-8')

        # Loss
        np.savetxt(os.path.join(self.results_dir, 'loss_{}.txt'.format(self.experiment_name)),
                   np.array(self.results['loss'], dtype=np.float32),
                   fmt='%.3f'.encode('utf-8'), delimiter=','.encode('utf-8'))

        # Train
        np.savetxt(os.path.join(self.results_dir, 'train_accuracy_{}.txt'.format(self.experiment_name)),
                   np.array(self.results['train_accuracy'], dtype=np.float32),
                   fmt='%.3f'.encode('utf-8'), delimiter=','.encode('utf-8'))
        np.savetxt(os.path.join(self.results_dir, 'train_precision_{}.txt'.format(self.experiment_name)),
                   np.array(self.results['train_precision'], dtype=np.float32),
                   fmt='%.3f'.encode('utf-8'), delimiter=','.encode('utf-8'),
                   header=header)
        np.savetxt(os.path.join(self.results_dir, 'train_recall_{}.txt'.format(self.experiment_name)),
                   np.array(self.results['train_recall'], dtype=np.float32),
                   fmt='%.3f'.encode('utf-8'), delimiter=','.encode('utf-8'),
                   header=header)

        # Test
        np.savetxt(os.path.join(self.results_dir, 'test_accuracy_{}.txt'.format(self.experiment_name)),
                   np.array(self.results['test_accuracy'], dtype=np.float32),
                   fmt='%.3f'.encode('utf-8'), delimiter=','.encode('utf-8'))
        np.savetxt(os.path.join(self.results_dir, 'test_precision_{}.txt'.format(self.experiment_name)),
                   np.array(self.results['test_precision'], dtype=np.float32),
                   fmt='%.3f'.encode('utf-8'), delimiter=','.encode('utf-8'),
                   header=header)
        np.savetxt(os.path.join(self.results_dir, 'test_recall_{}.txt'.format(self.experiment_name)),
                   np.array(self.results['test_recall'], dtype=np.float32),
                   fmt='%.3f'.encode('utf-8'), delimiter=','.encode('utf-8'),
                   header=header)

        # Validation
        np.savetxt(os.path.join(self.results_dir, 'validation_accuracy_{}.txt'.format(self.experiment_name)),
                   np.array(self.results['validation_accuracy'], dtype=np.float32),
                   fmt='%.3f'.encode('utf-8'), delimiter=','.encode('utf-8'))
        np.savetxt(os.path.join(self.results_dir, 'validation_precision_{}.txt'.format(self.experiment_name)),
                   np.array(self.results['validation_precision'], dtype=np.float32),
                   fmt='%.3f'.encode('utf-8'), delimiter=','.encode('utf-8'),
                   header=header)
        np.savetxt(os.path.join(self.results_dir, 'validation_recall_{}.txt'.format(self.experiment_name)),
                   np.array(self.results['validation_recall'], dtype=np.float32),
                   fmt='%.3f'.encode('utf-8'), delimiter=','.encode('utf-8'),
                   header=header)

    def train(self, layer_idexes=None, save_layers=True):
        with tf.Session() as sess:
            sess.run(tf.initialize_all_variables())

            print('Training classifier', file=sys.stderr)
            for epoch in np.arange(self.training_epochs):
                batch_dataset, batch_labels = self._next_batch()

                feed_dict = {
                    self.X: batch_dataset,
                    self.y: batch_labels
                }

                _, loss = sess.run([self.train_step, self.loss], feed_dict=feed_dict)

                if epoch % self.loss_report == 0:
                    print('Epoch {}: loss = {:.3f}'.format(epoch, loss), file=sys.stderr)
                    self.results['loss'].append(loss)

                if epoch % (self.loss_report * 2) == 0:
                    accuracy, precision, recall = self._evaluate(sess, self.validation_dataset, self.validation_labels,
                                                                 'Validation')
                    print('Validation accuracy: {:.3f}'.format(accuracy), file=sys.stderr)
                    self._add_results('validation', accuracy, precision, recall)

                    if len(self.results['validation_accuracy']) >= 2:
                        delta_acc = self.results['validation_accuracy'][-2] - accuracy
                        delta_loss = self.results['loss'][-2] - loss

                        if delta_loss < -1e-3 and delta_acc >= 1e-3:
                            print('Validation accuracy converging: ' +
                                  'delta_acc {:.3f} / delta_loss {:.3f}.' .format(delta_acc, delta_loss),
                                  file=sys.stderr)
                            break

                    if accuracy == 1:
                        print('Validation accuracy maxed: {:.2f}'.format(accuracy), file=sys.stderr)
                        break

            print('Finished training', file=sys.stderr)

            accuracy, precision, recall = self._evaluate(sess, self.train_dataset, self.train_labels, 'Train')
            print('Training accuracy: {:.3f}'.format(accuracy), file=sys.stderr)
            self._add_results('train', accuracy, precision, recall)

            accuracy, precision, recall = self._evaluate(sess, self.test_dataset, self.test_labels, 'Test')
            print('Testing accuracy: {:.3f}'.format(accuracy), file=sys.stderr)
            self._add_results('test', accuracy, precision, recall)

            print('Saving weights and biases', file=sys.stderr)
            file_name_weights = os.path.join(self.saves_dir, "{}_weights.npz".format(self.experiment_name))
            file_name_biases = os.path.join(self.saves_dir, "{}_biases.npz".format(self.experiment_name))

            if save_layers:
                weights_dict = {}
                biases_dict = {}

                for layer_idx, (weights, biases) in enumerate(zip(self.weights, self.biases)):
                    if layer_idexes is not None and layer_idx not in layer_idexes:
                        continue
                    weights_dict['hidden_layer_{:02d}'.format(layer_idx)] = weights.eval()
                    biases_dict['hidden_layer_{:02d}'.format(layer_idx)] = biases.eval()

                np.savez_compressed(file_name_weights, **weights_dict)
                np.savez_compressed(file_name_biases, **biases_dict)

            print('Saving results', file=sys.stderr)
            self._save_results()

            if self.saver is not None:
                print('Saving model', file=sys.stderr)
                save_path = self.saver.save(sess,
                                            os.path.join(self.results_dir, '{}.model'.format(self.experiment_name))
                                            )
                print('Model saved in file {}'.format(save_path))

