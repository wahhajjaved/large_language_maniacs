# Utils
import argparse

# Torch
import torch

# DeepDIVA
import datasets
import models


def parse_arguments():
    model_options = [name for name in models.__dict__ if callable(models.__dict__[name])]
    dataset_options = [name for name in datasets.__dict__ if callable(datasets.__dict__[name])]
    optimizer_options = [name for name in torch.optim.__dict__ if callable(torch.optim.__dict__[name])]
    runner_class_options = ["standard", "point_cloud"]

    ###############################################################################
    # Argument Parser
    # Training Settings
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Template for training a network on a dataset')
    parser_general = parser.add_argument_group('GENERAL', 'General Options')
    parser_data = parser.add_argument_group('DATA', 'Dataset Options')
    parser_train = parser.add_argument_group('TRAIN', 'Training Options')
    parser_system = parser.add_argument_group('SYS', 'System Options')

    # General Options
    parser_general.add_argument('--experiment-name',
                                type=str,
                                default=None,
                                help='provide a meaningful and descriptive name to this run')
    parser_general.add_argument('--quiet',
                                action='store_true',
                                help='Do not print to stdout (log only).')
    parser_general.add_argument('--multi-run',
                                type=int,
                                default=None,
                                help='run main N times with different random seeds')
    parser_general.add_argument('--hyper-param-optim',
                                type=str,
                                default=None,
                                help='path to a JSON file containing all variable names (as defined in the argument '
                                     'parser) that need to be searched over.')
    parser_general.add_argument('--sig-opt',
                                type=str,
                                default=None,
                                help='path to a JSON file containing sig_opt variables and sig_opt bounds.')
    parser_general.add_argument('--sig-opt-runs',
                                type=int,
                                default=100,
                                help='number of updates of SigOpt required')
    parser_general.add_argument('--runner-class',
                                choices=runner_class_options,
                                default="standard",
                                help='which runner class to use.')

    # Data Options
    # TODO dataset and dataset-folder should never exist together
    parser_data.add_argument('--dataset',
                             choices=dataset_options,
                             help='which dataset to train/test on.')
    parser_data.add_argument('--dataset-folder',
                             help='location of the dataset on the machine e.g root/data',
                             required=True)
    parser_data.add_argument('--log-dir',
                             help='where to save logs. Can be used to resume logging of experiment.',
                             required=True)

    # Training Options
    parser_train.add_argument('--model',
                              type=str,
                              dest='model_name',
                              choices=model_options,
                              default='CNN_basic',
                              help='which model to use for training')
    parser_train.add_argument('--lr',
                              type=float,
                              default=0.001,
                              help='learning rate to be used for training')
    parser_train.add_argument('--optimizer',
                              choices=optimizer_options,
                              dest='optimizer_name',
                              default='SGD',
                              help='optimizer to be used for training')
    parser_train.add_argument('--batch-size',
                              type=int,
                              default=64,
                              help='input batch size for training')
    parser_train.add_argument('--epochs',
                              type=int,
                              default=5,
                              help='how many epochs to train')
    parser_train.add_argument('--resume',
                              type=str,
                              default=None,
                              help='path to latest checkpoint')
    parser_train.add_argument('--pretrained',
                              action='store_true',
                              default=False,
                              help='use pretrained model. (Not applicable for all models)')
    parser_train.add_argument('--decay_lr',
                              type=int,
                              default=None,
                              help='drop LR by 10 every N epochs')
    parser_train.add_argument('--start-epoch',
                              type=int,
                              metavar='N',
                              default=0,
                              help='manual epoch number (useful on restarts)')
    # System Options
    parser_system.add_argument('--gpu-id',
                               default=None,
                               help='which GPUs to use for training (use all by default)')
    parser_system.add_argument('--no-cuda',
                               action='store_true',
                               default=False,
                               help='run on CPU')
    parser_system.add_argument('--seed',
                               type=int,
                               default=None,
                               help='random seed')
    parser_system.add_argument('--log-interval',
                               type=int,
                               default=10,
                               help='print loss/accuracy every N batches')
    parser_system.add_argument('-j', '--workers',
                               type=int,
                               default=4,
                               help='workers used for train/val loaders')
    return parser.parse_args(), parser
