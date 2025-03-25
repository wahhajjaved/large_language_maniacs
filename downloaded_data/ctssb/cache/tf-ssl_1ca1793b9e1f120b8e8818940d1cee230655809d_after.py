
import tensorflow as tf
import os
import time
from tqdm import tqdm
from src.utils import get_cli_params, process_cli_params, \
    order_param_settings
from src.val import build_graph, measure_smoothness, VERBOSE
from src.train import evaluate_metric_list, update_decays, evaluate_metric

import numpy as np



def main():

    p = process_cli_params(get_cli_params())
    global VERBOSE
    VERBOSE = p.verbose

    # -----------------------------
    # Set GPU device to use
    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    os.environ["CUDA_VISIBLE_DEVICES"] = str(p.which_gpu)
    config = tf.ConfigProto()
    config.gpu_options.allow_growth = True

    # Set seeds
    np.random.seed(p.seed)
    tf.set_random_seed(p.seed)

    # Load data
    print("===  Loading Data ===")
    if p.dataset == 'svhn':
        from src.svhn import read_data_sets
        dataset = read_data_sets(
            "../../data/svhn/",
            n_labeled=p.num_labeled,
            validation_size=p.validation,
            one_hot=True,
            disjoint=False,
            downsample=True,
            download_and_extract=True
        )

    else:
        from src.mnist import read_data_sets
        dataset = read_data_sets("MNIST_data",
                         n_labeled=p.num_labeled,
                         validation_size=p.validation,
                         one_hot=True,
                         disjoint=False)

    num_examples = dataset.train.num_examples
    p.num_examples = num_examples
    if p.validation > 0:
        dataset.test = dataset.validation
    p.iter_per_epoch = (num_examples // p.ul_batch_size)

    p.num_iter = p.iter_per_epoch * p.end_epoch


    # -----------------------------
    # Build graph
    g, m, trainable_parameters = build_graph(p)

    # Collect losses
    train_losses = [m['loss'], m['cost'], m['uc'], m['vc']]
    test_losses = [m['cost']]

    if p.measure_smoothness:
        s = measure_smoothness(g, p)
    #     print(s.get_shape())
        train_losses.append(tf.reduce_mean(s))

    if p.tb is not False:
        train_merged = tf.summary.merge([
            tf.summary.scalar(x) for x in train_losses
        ] + [tf.summary.scalar(m['acc'])])
        test_merged = tf.summary.merge([
            tf.summary.scalar(x) for x in test_losses
        ] + [tf.summary.scalar(m['acc'])])

        # Set up tensorboard logging
        if not os.path.exists(p.tb):
            os.makedirs(p.tb_dir)


    # -----------------------------
    print("===  Starting Session ===")
    sess = tf.Session(config=config)
    i_iter = 0

    # -----------------------------

    id_seed_dir = p.id + "/" + "seed-{}".format(p.seed) + "/"

    # Write logs to appropriate directory
    log_dir = p.logdir + id_seed_dir
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    desc_file = log_dir + "description"
    with open(desc_file, 'a') as f:
        print(*order_param_settings(p), sep='\n', file=f, flush=True)
        print("Trainable parameters:", trainable_parameters, file=f,
              flush=True)

    log_file = log_dir + "train_log"


    # Resume from checkpoint
    ckpt_dir = "checkpoints/" + id_seed_dir
    ckpt = tf.train.get_checkpoint_state(
        ckpt_dir)  # get latest checkpoint (if any)

    if ckpt and ckpt.model_checkpoint_path:
        # if checkpoint exists,
        # restore the parameters
        # and set epoch_n and i_iter
        g['saver'].restore(sess, ckpt.model_checkpoint_path)
        epoch_n = int(ckpt.model_checkpoint_path.split('/')[-1].split('-')[1])
        i_iter = (epoch_n + 1) * (p.num_examples // p.ul_batch_size)
        print("Restored Epoch ", epoch_n)

    else:
        # no checkpoint exists.
        # create checkpoints directory if it does not exist.
        if not os.path.exists(ckpt_dir):
            os.makedirs(ckpt_dir)

        init = tf.global_variables_initializer()
        sess.run(init)

    if p.tb is not False:
        train_writer = tf.summary.FileWriter(p.tb_dir + '/train', sess.graph)
        test_writer = tf.summary.FileWriter(p.tb_dir + '/test', sess.graph)

    # -----------------------------
    print("=== Training ===")
    # -----------------------------

    def eval_metrics(dataset, sess, ops):
        return evaluate_metric_list(dataset, sess, ops, graph=g, params=p)

    def eval_metric(dataset, sess, op):
        return evaluate_metric(dataset, sess, op, graph=g, params=p)

    # Evaluate initial training accuracy and losses
    # init_loss = evaluate_metric(
    # mnist.train.labeled_ds, sess, cost)
    with open(desc_file, 'a') as f:
        print('================================', file=f, flush=True)
        print("Initial Train Accuracy: ",
              eval_metric(dataset.train.labeled_ds, sess, m['acc']),
              "%", file=f, flush=True)

        # -----------------------------
        # Evaluate initial testing accuracy and cross-entropy loss
        print("Initial Test Accuracy: ",
              eval_metric(dataset.test, sess, m['acc']),
              "%", file=f, flush=True)
        # print("Initial Test Losses: ",
        #       *eval_metrics(
        #           mnist.test, sess, test_losses), file=f,
        #       flush=True)


    train_dict = {g['beta1']: p.beta1, g['lr']: p.initial_learning_rate}

    start = time.time()
    for i in tqdm(range(i_iter, p.num_iter)):

        images, labels = dataset.train.next_batch(p.batch_size, p.ul_batch_size)
        train_dict.update({
            g['images']: images,
            g['labels']: labels,
            g['train_flag']: True})

        _ = sess.run(
            [g['train_step']],
            feed_dict=train_dict)

        epoch_n = i // (p.num_examples // p.ul_batch_size)
        # ---------------------------------------------
        # Epoch completed?
        if (i > 1) and ((i + 1) % p.iter_per_epoch == 0):
            # update_decays(sess, epoch_n, iter=i, graph=g, params=p)

            # Update learning rate and momentum
            if ((epoch_n + 1) >= p.decay_start_epoch) and ((i + 1) % (
                        p.iter_per_epoch * p.lr_decay_frequency) == 0):
                # epoch_n + 1 because learning rate is set for next epoch
                ratio = 1.0 * (p.end_epoch - (epoch_n + 1))
                decay_epochs = p.end_epoch - p.decay_start_epoch
                ratio = max(0., ratio / decay_epochs) if decay_epochs != 0 else 1.0

                train_dict[g['lr']] = (p.initial_learning_rate * ratio)
                train_dict[g['beta1']] = p.beta1_during_decay

        # ---------------------------------------------
        # Evaluate every test_frequency_in_epochs
        if (i > 1) and ((i + 1) % int(p.test_frequency_in_epochs *
                           p.iter_per_epoch) == 0):

            # For the last ten epochs, test every epoch
            if (i+1) > (p.num_iter - (p.iter_per_epoch * 10)):
                p.test_frequency_in_epochs = 1

            now = time.time() - start

            if not p.do_not_save:
                g['saver'].save(sess, ckpt_dir + 'model.ckpt', epoch_n)

            # ---------------------------------------------
            # Compute error on testing set (10k examples)
            test_acc_and_costs = \
                eval_metrics(dataset.test, sess, [m['acc']] + test_losses)
            train_acc = eval_metrics(dataset.train.labeled_ds, sess, [m['acc']])
            train_costs = sess.run(train_losses,
                feed_dict={g['images']: images,
                           g['labels']: labels,
                           g['train_flag']: False})

            # Create log of:
            # time, epoch number, test accuracy, test cross entropy,
            # train accuracy, train loss, train cross entropy,
            # train reconstruction loss, smoothness

            log_i = [int(now), epoch_n] + test_acc_and_costs + train_acc + \
                    train_costs


            with open(log_file, 'a') as train_log:
                print(*log_i, sep=',', flush=True, file=train_log)




    with open(desc_file, 'a') as f:
        print("Final Accuracy: ", sess.run(m['acc'], feed_dict={
            g['images']: dataset.test.images, g['labels']:
                dataset.test.labels,
            g['train_flag']: False}),
              "%", file=f, flush=True)

    sess.close()


if __name__ == '__main__':
    main()








