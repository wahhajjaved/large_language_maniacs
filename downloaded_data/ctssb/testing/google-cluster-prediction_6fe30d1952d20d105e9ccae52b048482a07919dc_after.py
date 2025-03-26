from . import support
from .learner import Learner
from .saver import Saver
from .teacher import Examiner
from .teacher import Trainer
import numpy as np
import tensorflow as tf


class Experiment:
    def __init__(self, input, config):
        self.input = input
        self.output = config.output
        learner = tf.make_template(
            'learner', lambda x, y: Learner(x, y, config.learner))
        graph = tf.Graph()
        with graph.as_default():
            shape = [None, None, input.dimension_count]
            x = tf.placeholder(tf.float32, shape, name='x')
            y = tf.placeholder(tf.float32, shape, name='y')
            self.training_learner = learner(x, y)
            self.validation_learner = learner(x, y)
            self.test_learner = learner(x, y)
            with tf.variable_scope('trainer'):
                self.trainer = Trainer(self.training_learner, config.teacher)
            with tf.variable_scope('examiner'):
                self.examiner = Examiner(
                    self.validation_learner, config.teacher)
            with tf.variable_scope('state'):
                self.state = State()
            self.summarer = tf.summary.FileWriter(self.output.path, graph)
            self.saver = Saver(self.output)
            initialize = tf.variables_initializer(
                tf.global_variables(), name='initialize')
        self.session = tf.Session(graph=graph)
        self.session.run(initialize)
        self.saver.load(self.session)
        self.state.load(self.session)
        self.input.training.restart(self.state.epoch)
        support.log(self, 'Output path: {}', self.output.path)
        support.log(self, 'Initial step: {}, epoch: {}, sample: {}',
                    self.state.step, self.state.epoch, self.state.sample)

    def run_comparison(self, target):
        errors = getattr(self, 'run_' + target)(summarize=False)
        support.summarize_static(self.summarer, errors, 'comparison_' + target)

    def run_saving(self):
        self.state.save(self.session)
        self.saver.save(self.session, self.state)

    def run_testing(self, summarize=True):
        errors = self.examiner.test(self.input.testing, self._test)
        if summarize:
            support.summarize_dynamic(
                self.summarer, self.state, errors, 'testing')
        return errors

    def run_training(self, summarize=True, sample_count=1):
        for _ in range(sample_count):
            try:
                errors = self.trainer.train(
                    self.input.training, self._train)
                if summarize:
                    support.summarize_dynamic(
                        self.summarer, self.state, errors, 'training')
                self.state.increment_time()
            except StopIteration:
                self.state.increment_epoch()
                self.input.training.restart(self.state.epoch)
                support.log(
                    self, 'Current step: {}, epoch: {}, sample: {}',
                    self.state.step, self.state.epoch, self.state.sample)

    def run_validation(self, summarize=True):
        errors = self.examiner.validate(self.input.validation, self._validate)
        if summarize:
            support.summarize_dynamic(
                self.summarer, self.state, errors, 'validation')
        return errors

    def _train(self, sample):
        feed = {
            self.training_learner.start: np.zeros(
                self.training_learner.start.get_shape(), np.float32),
            self.training_learner.x: np.reshape(
                sample, [1, -1, self.input.dimension_count]),
            self.training_learner.y: np.reshape(
                support.shift(sample, -1),
                [1, -1, self.input.dimension_count]),
        }
        fetch = {
            'optimize': self.trainer.optimize,
            'loss': self.trainer.loss,
        }
        return self.session.run(fetch, feed)['loss']

    def _test(self, sample, future_length):
        fetch = {
            'y_hat': self.test_learner.y_hat,
            'finish': self.test_learner.finish,
        }
        sample_length, dimension_count = sample.shape
        y_hat = np.empty([sample_length, future_length, dimension_count])
        for i in range(sample_length):
            feed = {
                self.test_learner.start: np.zeros(
                    self.test_learner.start.get_shape(), np.float32),
                self.test_learner.x: np.reshape(
                    sample[:(i + 1), :], [1, i + 1, -1]),
            }
            for j in range(future_length):
                result = self.session.run(fetch, feed)
                y_hat[i, j, :] = result['y_hat'][0, -1, :]
                feed[self.test_learner.start] = result['finish']
                feed[self.test_learner.x] = y_hat[i:(i + 1), j:(j + 1), :]
        return y_hat

    def _validate(self, sample):
        feed = {
            self.validation_learner.start: np.zeros(
                self.validation_learner.start.get_shape(), np.float32),
            self.validation_learner.x: np.reshape(
                sample, [1, -1, self.input.dimension_count]),
            self.validation_learner.y: np.reshape(
                support.shift(sample, -1),
                [1, -1, self.input.dimension_count]),
        }
        fetch = {
            'loss': self.examiner.loss,
        }
        return self.session.run(fetch, feed)['loss']


class State:
    def __init__(self):
        self.current = tf.Variable(
            [0, 0, 0], name='current', dtype=tf.int64, trainable=False)
        self.new = tf.placeholder(tf.int64, shape=3, name='new')
        self.assign_new = self.current.assign(self.new)
        self.step, self.epoch, self.sample = None, None, None

    def increment_epoch(self):
        self.epoch += 1
        self.sample = 0

    def increment_time(self):
        self.step += 1
        self.sample += 1

    def load(self, session):
        state = session.run(self.current)
        self.step, self.epoch, self.sample = state

    def save(self, session):
        feed = {
            self.new: [self.step, self.epoch, self.sample],
        }
        session.run(self.assign_new, feed)
