import os
import sys
import json
import argparse
import importlib
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from datetime import datetime
from torch.utils.data import DataLoader

sys.path.append(".")
from lib.solver import Solver
from lib.dataset import ScannetDataset, ScannetDatasetWholeScene, collate_random, collate_wholescene
from lib.loss import WeightedCrossEntropyLoss
from lib.config import CONF


def get_dataloader(args, scene_list, is_train=True, is_wholescene=False):
    if is_wholescene:
        dataset = ScannetDatasetWholeScene(scene_list, is_train=is_train)
        dataloader = DataLoader(dataset, batch_size=1, collate_fn=collate_wholescene)
    else:
        dataset = ScannetDataset(scene_list, is_train=is_train)
        dataloader = DataLoader(dataset, batch_size=args.batch_size, collate_fn=collate_random)

    return dataset, dataloader

def get_num_params(model):
    model_parameters = filter(lambda p: p.requires_grad, model.parameters())
    num_params = int(sum([np.prod(p.size()) for p in model_parameters]))

    return num_params

def get_solver(args, dataloader, stamp, weight, is_wholescene):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pointnet2/'))
    Pointnet = importlib.import_module("pointnet2_msg_semseg")

    model = Pointnet.get_model(num_classes=21).cuda()
    num_params = get_num_params(model)
    criterion = WeightedCrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.wd)
    solver = Solver(model, dataloader, criterion, optimizer, args.batch_size, stamp, is_wholescene)

    return solver, num_params

def get_scene_list(path):
    scene_list = []
    with open(path) as f:
        for scene_id in f.readlines():
            scene_list.append(scene_id.strip())

    return scene_list

def save_info(args, root, train_examples, val_examples, num_params):
    info = {}
    for key, value in vars(args).items():
        info[key] = value
    
    info["num_train"] = train_examples
    info["num_val"] = val_examples
    info["num_params"] = num_params

    with open(os.path.join(root, "info.json"), "w") as f:
        json.dump(info, f, indent=4)

def train(args):
    # init training dataset
    print("preparing data...")
    if args.debug:
        train_scene_list = ["scene0000_00"]
        val_scene_list = ["scene0000_00"]
    else:
        train_scene_list = get_scene_list(CONF.SCANNETV2_TRAIN)
        val_scene_list = get_scene_list(CONF.SCANNETV2_VAL)

    # dataloader
    if args.wholescene:
        is_wholescene = True
    else:
        is_wholescene = False

    train_dataset, train_dataloader = get_dataloader(args, train_scene_list, True, False)
    val_dataset, val_dataloader = get_dataloader(args, val_scene_list, False, is_wholescene)
    dataloader = {
        "train": train_dataloader,
        "val": val_dataloader
    }
    weight = train_dataset.labelweights
    train_examples = len(train_dataset)
    val_examples = len(val_dataset)

    print("initializing...")
    stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    root = os.path.join(CONF.OUTPUT_ROOT, stamp)
    os.makedirs(root, exist_ok=True)
    solver, num_params = get_solver(args, dataloader, stamp, weight, is_wholescene)
    
    print("\n[info]")
    print("Train examples: {}".format(train_examples))
    print("Evaluation examples: {}".format(val_examples))
    print("Start training...\n")
    save_info(args, root, train_examples, val_examples, num_params)
    solver(args.epoch, args.verbose)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--gpu', type=str, help='gpu', default='0')
    parser.add_argument('--batch_size', type=int, help='batch size', default=1)
    parser.add_argument('--epoch', type=int, help='number of epochs', default=10)
    parser.add_argument('--verbose', type=int, help='iterations of showing verbose', default=1)
    parser.add_argument('--lr', type=float, help='learning rate', default=5e-5)
    parser.add_argument('--wd', type=float, help='weight decay', default=0)
    parser.add_argument('--bn', type=bool, help='batch norm', default=True)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--wholescene", action="store_true", help="flag for whether the evaluation is on the whole scene or on a single chunk")
    args = parser.parse_args()

    # setting
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu
    os.environ["CUDA_LAUNCH_BLOCKING"] = "1"

    train(args)