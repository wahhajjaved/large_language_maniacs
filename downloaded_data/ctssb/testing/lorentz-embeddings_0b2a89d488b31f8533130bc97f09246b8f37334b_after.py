import os
import torch
import random
import numpy as np
from torch import nn
from torch import optim
import matplotlib
import sys

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from tqdm import trange, tqdm
from datetime import datetime
from tensorboardX import SummaryWriter
from torch.utils.data import Dataset, DataLoader

plt.style.use("ggplot")


def arcosh(x):
    return torch.log(x + torch.sqrt(x ** 2 - 1))


def lorentz_scalar_product(x, y):
    # BD, BD -> B
    m = x * y
    result = m[:, 1:].sum(dim=1) - m[:, 0]
    return result


def tangent_norm(x):
    # BD -> B
    return torch.sqrt(lorentz_scalar_product(x, x))


def exp_map(x, v):
    # BD, BD -> BD
    tn = tangent_norm(v).unsqueeze(dim=1)
    tn_expand = tn.repeat(1, x.size()[-1])
    result = torch.cosh(tn) * x + torch.sinh(tn) * (v / tn)
    result = torch.where(tn_expand > 0, result, x)  # only update if tangent norm is > 0
    return result


def set_dim0(x):
    dim0 = torch.sqrt(1 + torch.norm(x[:, 1:], dim=1) ** 2)
    x[:, 0] = dim0
    return x


# ========================= models


class RSGD(optim.Optimizer):
    def __init__(self, params, learning_rate=None):
        learning_rate = learning_rate if learning_rate is not None else 0.01
        defaults = {"learning_rate": learning_rate}
        super().__init__(params, defaults=defaults)

    def step(self):
        for group in self.param_groups:
            for p in group["params"]:
                if p.grad is None:
                    continue
                B, D = p.size()
                gl = torch.eye(D, device=p.device, dtype=p.dtype)
                gl[0, 0] = -1
                grad_norm = torch.norm(p.grad.data)
                grad_norm = torch.where(grad_norm > 1, grad_norm, torch.tensor(1.0))
                # only normalize if global grad_norm is more than 1
                h = (p.grad.data / grad_norm) @ gl
                proj = (
                    h
                    - (
                        lorentz_scalar_product(p, h) / lorentz_scalar_product(p, p)
                    ).unsqueeze(1)
                    * p
                )
                grad_norm = torch.norm(p.grad.data, dim=1).unsqueeze(1).repeat(1, D)
                update = exp_map(p, -group["learning_rate"] * proj)
                is_nan_inf = torch.isnan(update) | torch.isinf(update)
                update = torch.where(is_nan_inf, p, update)
                update = set_dim0(update)
                update[0, :] = p[0, :]  # no love for embedding
                p.data.copy_(update)


class Lorentz(nn.Module):
    """
    This will embed `n_items` in a `dim` dimensional lorentz space.
    """

    def __init__(self, n_items, dim, init_range=0.001):
        super().__init__()
        self.n_items = n_items
        self.dim = dim
        self.table = nn.Embedding(n_items + 1, dim, padding_idx=0)
        nn.init.uniform_(self.table.weight, -init_range, init_range)
        # equation 6
        with torch.no_grad():
            self.table.weight[0] = 5  # padding idx push it to corner
            set_dim0(self.table.weight)

    def forward(self, I, Ks):
        """
        Using the pairwise similarity matrix, generate the following inputs and
        provide to this function.

        Inputs:
            - I     :   - long tensor
                        - size (B,)
                        - This denotes the `i` used in all equations.
            - Ks    :   - long tensor
                        - size (B, N)
                        - This denotes at max `N` documents which come from the
                          nearest neighbor sample.
                        - The `j` document must be the first of the N indices.
                          This is used to calculate the losses
        Return:
            - size (B,)
            - Ranking loss calculated using
              document to the given `i` document.

        """
        n_ks = Ks.size()[1]
        ui = torch.stack([self.table(I)] * n_ks, dim=1)
        uks = self.table(Ks)
        # ---------- reshape for calculation
        B, N, D = ui.size()
        ui = ui.reshape(B * N, D)
        uks = uks.reshape(B * N, D)
        dists = -lorentz_scalar_product(ui, uks)
        dists = torch.where(dists <= 1, torch.ones_like(dists) + 1e-6, dists)
        # sometimes 2 embedding can come very close in R^D.
        # when calculating the lorenrz inner product,
        # -1 can become -0.99(no idea!), then arcosh will become nan
        dists = -arcosh(dists)
        # ---------- turn back to per-sample shape
        dists = dists.reshape(B, N)
        loss = -(dists[:, 0] - torch.log(torch.exp(dists).sum(dim=1) + 1e-6))
        return loss

    def lorentz_to_poincare(self):
        table = self.table.weight.data.numpy()
        return table[:, 1:] / (
            table[:, :1] + 1
        )  # diffeomorphism transform to poincare ball


class Graph(Dataset):
    def __init__(self, pairwise_matrix, sample_size=10):
        self.pairwise_matrix = pairwise_matrix
        self.n_items = len(pairwise_matrix)
        self.sample_size = sample_size
        self.arange = np.arange(0, self.n_items)

    def __len__(self):
        return self.n_items

    def __getitem__(self, i):
        I = torch.Tensor([i + 1]).squeeze().long()
        has_child = (self.pairwise_matrix[i] > 0).sum()
        has_parent = (self.pairwise_matrix[:, i] > 0).sum()
        arange = np.random.permutation(self.arange)
        if has_child:
            for j in arange:
                if self.pairwise_matrix[i, j] > 0:  # assuming no self loop
                    min = self.pairwise_matrix[i, j]
                    break
        elif has_parent:  # if no child go for parent
            for j in arange:
                if self.pairwise_matrix[j, i] > 0:  # assuming no disconneted nodes
                    min = self.pairwise_matrix[j, i]
                    break
        else:
            raise Exception(f"Node {i} has no parent and no child")
        arange = np.random.permutation(self.arange)
        if has_child:
            indices = [x for x in arange if i != x and self.pairwise_matrix[i, x] < min]
        else:
            indices = [x for x in arange if i != x and self.pairwise_matrix[x, i] < min]
        indices = indices[: self.sample_size]
        Ks = ([i + 1 for i in [j] + indices] + [0] * self.sample_size)[
            : self.sample_size
        ]
        # print(I, Ks)
        return I, torch.Tensor(Ks).long()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", help="File:pairwise_matrix")
    parser.add_argument(
        "-burn_c",
        help="Divide learning rate by this for the burn epochs",
        default=10,
        type=int,
    )
    parser.add_argument(
        "-burn_epochs",
        help="How many epochs to run the burn phase for?",
        default=100,
        type=int,
    )
    parser.add_argument(
        "-plot", help="Plot the embeddings", default=False, action="store_true"
    )
    parser.add_argument(
        "-plot_out_path", help="Where to put the plot?", default="embed.svg"
    )
    parser.add_argument(
        "-ckpt", help="Which checkpoint to use?", default=None, type=str
    )
    parser.add_argument(
        "-sample_size", help="How many samples in the N matrix", default=10
    )
    parser.add_argument("-batch_size", help="How many samples in the batch", default=32)
    parser.add_argument(
        "-shuffle", help="Shuffle within batch while learning?", default=True
    )
    parser.add_argument(
        "-epochs", help="How many epochs to optimize for?", default=1_000_000
    )
    parser.add_argument(
        "-poincare_dim", help="Poincare projection time. Lorentz will be + 1", default=2
    )
    parser.add_argument(
        "-n_items", help="How many items to embed?", default=None, type=int
    )
    parser.add_argument("-learning_rate", help="RSGD learning rate", default=0.1)
    parser.add_argument("-log_step", help="Log at what multiple of epochs?", default=1)
    parser.add_argument("-logdir", help="What folder to put logs in", default="runs")
    parser.add_argument(
        "-save_step", help="Save at what multiple of epochs?", default=100
    )
    parser.add_argument(
        "-savedir", help="What folder to put checkpoints in", default="ckpt"
    )
    args = parser.parse_args()
    # ----------------------------------- get the correct matrix
    if not os.path.exists(args.logdir):
        os.mkdir(args.logdir)
    if not os.path.exists(args.savedir):
        os.mkdir(args.savedir)
    fl, obj = args.dataset.split(":")

    exec(f"from {fl} import {obj} as pairwise")
    pairwise = pairwise[: args.n_items, : args.n_items]
    args.n_items = len(pairwise) if args.n_items is None else args.n_items

    # ---------------------------------- Generate the proper objects
    net = Lorentz(
        args.n_items, args.poincare_dim + 1
    )  # as the paper follows R^(n+1) for this space
    if args.plot:
        if args.poincare_dim != 2:
            print("Only embeddings with `-poincare_dim` = 2 are supported for now.")
            sys.exit(1)
        if args.ckpt is None:
            print("Please provide `-ckpt` when using `-plot`")
            sys.exit(1)
        net.load_state_dict(torch.load(args.ckpt))
        table = net.lorentz_to_poincare()
        plt.scatter(table[:, 0], table[:, 1])
        plt.savefig(args.plot_out_path)
        plt.close()
        sys.exit(0)

    dataloader = DataLoader(
        Graph(pairwise, args.sample_size),
        shuffle=args.shuffle,
        batch_size=args.batch_size,
    )
    rsgd = RSGD(net.parameters(), learning_rate=args.learning_rate)
    writer = SummaryWriter(f"{args.logdir}/{args.dataset}  {datetime.utcnow()}")

    with tqdm(ncols=80) as epoch_bar:
        for epoch in range(args.epochs):
            with tqdm(ncols=80) as pbar:
                for I, Ks in dataloader:
                    rsgd.zero_grad()
                    loss = net(I, Ks).mean()
                    loss.backward()
                    rsgd.step()
                    pbar.set_description(f"Batch Loss: {float(loss)}")
                    if torch.isnan(loss) or torch.isinf(loss):
                        pbar.set_description("NaN/Inf")
                    pbar.update(1)
                writer.add_scalar("loss", loss, epoch)
                if epoch % args.save_step == 0:
                    torch.save(net.state_dict(), f"{args.savedir}/{epoch}.ckpt")
            epoch_bar.set_description(
                f"BurnLoss: {float(loss)}"
                if epoch < args.burn_epochs
                else f"Loss: {float(loss)}"
            )
            epoch_bar.update(1)
