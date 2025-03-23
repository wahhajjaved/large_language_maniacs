import collections
import numpy as np
import torch
import torch.utils.data.dataloader
from torch.autograd import Variable
from tqdm import tqdm
import pdb


class TorchBase():
    def _run_iter(self, batch, training):
        pass

    def _predict_batch(self, batch):
        pass

    def _run_epoch(self, dataloader, training):

        # run batches for train
        loss = 0

        # init metric_scores
        # metric_scores = {}
        # for metric in self._metrics:
        #     metric_scores[metric] = 0

        for batch in tqdm(dataloader):
            outputs, batch_loss = \
                self._run_iter(batch, training)

            if training:
                self._optimizer.zero_grad()
                batch_loss.backward()
                self._optimizer.step()

            loss += batch_loss.data[0]
            # for metric, func in self._metrics.items():
            #     metric_scores[metric] += func(

        # calculate averate loss
        loss /= len(dataloader)

        epoch_log = {}
        epoch_log['loss'] = float(loss)
        print('loss=%f\n' % loss)
        return epoch_log

    def __init__(self,
                 learning_rate=1e-3, batch_size=10,
                 n_epochs=10, valid=None,
                 reg_constant=0.0,
                 use_cuda=None):

        self._learning_rate = learning_rate
        self._batch_size = batch_size
        self._n_epochs = n_epochs
        self._valid = valid
        self._reg_constant = reg_constant
        self._epoch = 0
        self._use_cuda = use_cuda \
            if use_cuda is not None \
            else torch.cuda.is_available()

    def fit_dataset(self, data, callbacks=[]):
        # Start the training loop.
        while self._epoch < self._n_epochs:

            # train and evaluate train score
            print('training %i' % self._epoch)
            dataloader = torch.utils.data.DataLoader(
                data,
                batch_size=self._batch_size,
                shuffle=True,
                collate_fn=padding_collate,
                num_workers=1)
            log_train = self._run_epoch(dataloader, True)

            # evaluate valid score
            if self._valid is not None:
                print('evaluating %i' % self._epoch)
                dataloader = torch.utils.data.DataLoader(
                    self._valid,
                    batch_size=self._batch_size,
                    shuffle=True,
                    collate_fn=padding_collate,
                    num_workers=1)
                log_valid = self._run_epoch(dataloader, False)
            else:
                log_valid = None

            for callback in callbacks:
                callback.on_epoch_end(log_train, log_valid, self)

            self._epoch += 1

    def predict_dataset(self, data, batch_size=None):
        if batch_size is None:
            batch_size = self._batch_size

        dataloader = torch.utils.data.DataLoader(
            data,
            batch_size=batch_size,
            shuffle=False,
            collate_fn=padding_collate,
            num_workers=1)

        y_ = None
        for batch in dataloader:
            batch_y_ = self._predict_batch(batch)
            if y_ is None:
                y_ = batch_y_
            else:
                if batch_y_.shape[-1] < y_.shape[-1]:
                    widths = [0] * len(y_.shape)
                    widths[-1] = y_.shape[-1] - batch_y_.shape[-1]
                    batch_y_ = np.pad(batch_y_, widths)
                elif batch_y_.shape[-1] > y_.shape[-1]:
                    widths = [0] * len(y_.shape)
                    widths[-1] = batch_y_.shape[-1] - y_.shape[-1]
                    y_ = np.pad(y_, widths)

                y_ = np.concatenate([y_, batch_y_],
                                    axis=0)

        return y_

    def save(self, path):
        torch.save({
            'epoch': self._epoch + 1,
            'model': self._model.state_dict(),
            'optimizer': self._optimizer.state_dict()
        }, path)

    def load(self, path):
        checkpoint = torch.load(path)
        self._epoch = checkpoint['epoch']
        self._model.load_state_dict(checkpoint['model'])
        self._optimizer.load_state_dict(checkpoint['optimizer'])


numpy_type_map = {
    'float64': torch.DoubleTensor,
    'float32': torch.FloatTensor,
    'float16': torch.HalfTensor,
    'int64': torch.LongTensor,
    'int32': torch.IntTensor,
    'int16': torch.ShortTensor,
    'int8': torch.CharTensor,
    'uint8': torch.ByteTensor,
}


def padding_collate(batch):
    """
    Puts each data field into a tensor with outer dimension batch size.
    And pad sequence to same length.
    Modified from default_collate
    """
    if torch.is_tensor(batch[0]):
        out = None
        if torch.utils.data.dataloader._use_shared_memory:
            # If we're in a background process, concatenate directly into a
            # shared memory tensor to avoid an extra copy
            numel = sum([x.numel() for x in batch])
            storage = batch[0].storage()._new_shared(numel)
            out = batch[0].new(storage)
        return torch.stack(batch, 0, out=out)
    elif type(batch[0]).__module__ == 'numpy':
        elem = batch[0]
        if type(elem).__name__ == 'ndarray':
            return torch.stack([torch.from_numpy(b) for b in batch], 0)
        if elem.shape == ():  # scalars
            py_type = float if elem.dtype.name.startswith('float') else int
            return numpy_type_map[elem.dtype.name](list(map(py_type, batch)))
    elif isinstance(batch[0], int):
        return torch.LongTensor(batch)
    elif isinstance(batch[0], float):
        return torch.DoubleTensor(batch)
    elif isinstance(batch[0], (str, bytes)):
        return batch
    elif isinstance(batch[0], collections.Mapping):
        return {key: padding_collate([d[key] for d in batch]) for key in batch[0]}
    elif isinstance(batch[0], collections.Sequence):
        # doing padding here
        padding = 0
        max_lengths = max(map(len, batch))
        batch = [b + [padding for i in range(max_lengths - len(b))]
                 for b in batch]
        # same as original default_collate
        transposed = zip(*batch)
        return [padding_collate(samples) for samples in transposed]

    raise TypeError(("batch must contain tensors, numbers, dicts or lists; found {}"
                     .format(type(batch[0]))))
