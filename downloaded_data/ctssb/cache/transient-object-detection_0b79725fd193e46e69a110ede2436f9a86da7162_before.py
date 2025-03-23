
# import torch
import torch.nn as nn
# import torch.nn.functional as F
# from collections import OrderedDict

cfg = {
    'A': [64, 'M', 128, 'M', 256, 256, 'M', 512, 512, 'M', 512, 512, 'M'],
    'B': [64, 64, 'M', 128, 128, 'M', 256, 256, 'M', 512, 512, 'M', 512,
          512, 'M'],
    'D': [64, 64, 'M', 128, 128, 'M', 256, 256, 256, 'M', 512, 512, 512,
          'M', 512, 512, 512, 'M'],
    'E': [64, 64, 'M', 128, 128, 'M', 256, 256, 256, 256, 'M', 512, 512,
          512, 512, 'M', 512, 512, 512, 512, 'M'],
    'F': ['U', 512, 512, 512, 'U', 512, 512, 256, 'U', 256, 256, 128,
          'U', 128, 64, 'U', 64]
}

# [64, 64, 'M', 128, 128, 'M', 256, 256, 256, 'M', 512, 512, 512,
# 'M', 512, 512, 512, 'M']

# ['U', 512, 512, 512, 'U', 512, 512, 512, 'U', 256, 256, 256, 'U',
# 128, 128, 'U', 64]


class SegNet(nn.Module):
    def __init__(self, features, deconv, label_nbr):
        super(SegNet, self).__init__()

        # batchNorm_momentum = 0.1

        self.features = nn.ModuleList(features)
        self.deconv = nn.ModuleList(deconv)
        self.output = nn.Conv2d(64, label_nbr, kernel_size=3, padding=1)

    def forward(self, x):
        ids = []

        for layer in self.features:
            if isinstance(layer, nn.MaxPool2d):
                x, _id = layer(x)
                ids.append(_id)
                # print(_id.size())
            else:
                x = layer(x)

        idx = 0
        ids = ids[::-1]

        # print("\n")
        for layer in self.deconv:
            # print(layer)
            if isinstance(layer, nn.MaxUnpool2d):
                x = layer(x, ids[idx])
                # print(ids[idx].size())
                idx += 1
            else:
                x = layer(x)

        x = self.output(x)

        return x


def make_layers(cfg, in_channels=3, batch_norm=False):
    layers = []
    # in_channels =
    for v in cfg:
        if v == 'M':
            layers += [nn.MaxPool2d(kernel_size=2, stride=2,
                                    return_indices=True)]
        elif v == 'U':
            layers += [nn.MaxUnpool2d(kernel_size=(2, 2), stride=(2, 2))]
        else:
            conv2d = nn.Conv2d(in_channels, v, kernel_size=3, padding=1)
            if batch_norm:
                layers += [conv2d, nn.BatchNorm2d(v), nn.ReLU(inplace=True)]
            else:
                layers += [conv2d, nn.ReLU(inplace=True)]
            in_channels = v
    return layers


def make_segnet(out_dim=1024):
    base = make_layers(cfg['D'], batch_norm=True)
    deconv = make_layers(cfg['F'], in_channels=512, batch_norm=True)
    return SegNet(base, deconv, out_dim)
