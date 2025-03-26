#!/usr/bin/env python

import argparse
import collections
import glob

import six

import chainer
from chainer.training import extensions

import babi
import memnn


def main():
    parser = argparse.ArgumentParser(
        description='Chainer example: End-to-end memory networks')
    parser.add_argument('data', help='Path to bAbI dataset')
    parser.add_argument('--batchsize', '-b', type=int, default=100,
                        help='Number of images in each mini batch')
    parser.add_argument('--epoch', '-e', type=int, default=100,
                        help='Number of sweeps over the dataset to train')
    parser.add_argument('--gpu', '-g', type=int, default=-1,
                        help='GPU ID (negative value indicates CPU)')
    parser.add_argument('--unit', '-u', type=int, default=20,
                        help='Number of units')
    parser.add_argument('--hop', '-H', type=int, default=3,
                        help='Number of hops')
    parser.add_argument('--max-memory', type=int, default=50,
                        help='Maximum number of memory')
    parser.add_argument('--sentence-repr',
                        choices=['bow', 'pe'], default='bow',
                        help='Sentence representation. '
                        'Select from BoW ("bow") or position encoding ("pe")')
    args = parser.parse_args()

    vocab = collections.defaultdict(lambda: len(vocab))
    vocab['<unk>'] = 0

    for data_id in six.moves.range(1, 21):

        train_data = babi.read_data(
            vocab,
            glob.glob('%s/qa%d_*train.txt' % (args.data, data_id))[0])
        test_data = babi.read_data(
            vocab,
            glob.glob('%s/qa%d_*test.txt' % (args.data, data_id))[0])
        print('Training data: %d' % len(train_data))

        train_data = memnn.convert_data(train_data, args.max_memory)
        test_data = memnn.convert_data(test_data, args.max_memory)

        encoder = memnn.make_encoder(args.sentence_repr)
        network = memnn.MemNN(
            args.unit, len(vocab), encoder, args.max_memory, args.hop)
        model = chainer.links.Classifier(network, label_key='answer')
        opt = chainer.optimizers.Adam()

        if args.gpu >= 0:
            chainer.cuda.get_device(args.gpu).use()
            model.to_gpu()

        opt.setup(model)

        train_iter = chainer.iterators.SerialIterator(
            train_data, args.batchsize)
        test_iter = chainer.iterators.SerialIterator(
            test_data, args.batchsize, repeat=False, shuffle=False)
        updater = chainer.training.StandardUpdater(
            train_iter, opt, device=args.gpu)
        trainer = chainer.training.Trainer(updater, (args.epoch, 'epoch'))

        @chainer.training.make_extension()
        def fix_ignore_label(trainer):
            network.fix_ignore_label()

        trainer.extend(fix_ignore_label)
        trainer.extend(extensions.Evaluator(test_iter, model, device=args.gpu))
        trainer.extend(extensions.LogReport())
        trainer.extend(extensions.PrintReport(
            ['epoch', 'main/loss', 'validation/main/loss',
             'main/accuracy', 'validation/main/accuracy']))
        trainer.extend(extensions.ProgressBar(update_interval=10))
        trainer.run()


if __name__ == '__main__':
    main()
