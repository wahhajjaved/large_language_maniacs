from __future__ import division

import argparse
from collections import OrderedDict

import torch
from mmcv import Config
from mmcv.torchpack import Runner, obj_from_dict

from mmdet import datasets
from mmdet.core import init_dist, DistOptimizerHook, DistSamplerSeedHook
from mmdet.datasets.loader import build_dataloader
from mmdet.models import build_detector
from mmdet.nn.parallel import MMDataParallel, MMDistributedDataParallel


def parse_losses(losses):
    log_vars = OrderedDict()
    for loss_name, loss_value in losses.items():
        if isinstance(loss_value, torch.Tensor):
            log_vars[loss_name] = loss_value.mean()
        elif isinstance(loss_value, list):
            log_vars[loss_name] = sum(_loss.mean() for _loss in loss_value)
        else:
            raise TypeError(
                '{} is not a tensor or list of tensors'.format(loss_name))

    loss = sum(_value for _key, _value in log_vars.items() if 'loss' in _key)

    log_vars['loss'] = loss
    for name in log_vars:
        log_vars[name] = log_vars[name].item()

    return loss, log_vars


def batch_processor(model, data, train_mode):
    losses = model(**data)
    loss, log_vars = parse_losses(losses)

    outputs = dict(
        loss=loss, log_vars=log_vars, num_samples=len(data['img'].data))

    return outputs


def parse_args():
    parser = argparse.ArgumentParser(description='Train a detector')
    parser.add_argument('config', help='train config file path')
    parser.add_argument(
        '--validate',
        action='store_true',
        help='whether to add a validate phase')
    parser.add_argument(
        '--gpus', type=int, default=1, help='number of gpus to use')
    parser.add_argument(
        '--launcher',
        choices=['none', 'pytorch', 'slurm', 'mpi'],
        default='none',
        help='job launcher')
    parser.add_argument('--local_rank', type=int, default=0)
    args = parser.parse_args()

    return args


def main():
    args = parse_args()

    cfg = Config.fromfile(args.config)
    cfg.update(gpus=args.gpus)

    # init distributed environment if necessary
    if args.launcher == 'none':
        dist = False
        print('Disabled distributed training.')
    else:
        dist = True
        print('Enabled distributed training.')
        init_dist(args.launcher, **cfg.dist_args)

    # prepare data loaders
    train_dataset = obj_from_dict(cfg.data.train, datasets)
    data_loaders = [
        build_dataloader(train_dataset, cfg.data.imgs_per_gpu,
                         cfg.data.workers_per_gpu, cfg.gpus, dist)
    ]
    if args.validate:
        val_dataset = obj_from_dict(cfg.data.val, datasets)
        data_loaders.append(
            build_dataloader(val_dataset, cfg.data.imgs_per_gpu,
                             cfg.data.workers_per_gpu, cfg.gpus, dist))

    # build model
    model = build_detector(
        cfg.model, train_cfg=cfg.train_cfg, test_cfg=cfg.test_cfg)
    if dist:
        model = MMDistributedDataParallel(
            model,
            device_ids=[torch.cuda.current_device()],
            broadcast_buffers=False).cuda()
    else:
        model = MMDataParallel(model, device_ids=range(cfg.gpus)).cuda()

    # build runner
    runner = Runner(model, batch_processor, cfg.optimizer, cfg.work_dir,
                    cfg.log_level)
    # register hooks
    optimizer_config = DistOptimizerHook(
        **cfg.optimizer_config) if dist else cfg.optimizer_config
    runner.register_training_hooks(cfg.lr_config, optimizer_config,
                                   cfg.checkpoint_config, cfg.log_config)
    if dist:
        runner.register_hook(DistSamplerSeedHook())

    if cfg.resume_from:
        runner.resume(cfg.resume_from)
    elif cfg.load_from:
        runner.load_checkpoint(cfg.load_from)
    runner.run(data_loaders, cfg.workflow, cfg.total_epochs)


if __name__ == '__main__':
    main()
