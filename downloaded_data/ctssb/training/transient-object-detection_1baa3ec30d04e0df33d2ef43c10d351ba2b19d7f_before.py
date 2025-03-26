
import os
import torch
import errno
import progressbar
import numpy as np
import os.path as osp
from PIL import Image
from astropy.io import fits
import torch.utils.data as data
import matplotlib.pyplot as plt


IMG_EXTENSIONS = ['.fits']
EXTTYPE = 'EXTTYPE'
IMAGE = 'IMAGE'


def make_dataset(dir):
    images = []
    for path, _, files in os.walk(dir):
        for filename in files:
            name, ext = osp.splitext(filename)
            if ext in IMG_EXTENSIONS:
                filename = osp.join(path, filename)
                images.append(filename)
    return images


def astropy_loader(path):
    hdulist = fits.open(path)
    img = None
    for hdu in hdulist:
        if EXTTYPE in hdu.header:
            if hdu.header[EXTTYPE] == IMAGE:
                hdu.data[np.isnan(hdu.data)] = 0
                hdu.data[np.isinf(hdu.data)] = 0
                try:
                    hdu.scale('uint8', 'minmax')
                except ValueError as e:
                    print(path)
                    raise e
                img = hdu.data
    if img is None:
        err = "The file {0} does not contain any hdu image"
        raise RuntimeError(err.format(path))
    # print(img.shape)
    return img


class TransientObjectLoader(data.Dataset):
    data_folder = 'data'
    training_file = 'training.pt'
    test_file = 'test.pt'

    def __init__(self, root, test_split=10000, transform=None, train=True,
                 loader=astropy_loader):
        imgs = make_dataset(root)
        if len(imgs) == 0:
            ext = ','.join(IMG_EXTENSIONS)
            raise RuntimeError("The path {0} does not "
                               "contain any images of "
                               "extension {1}".format(root, ext))
        self.root = root
        self.loader = loader
        self.transform = transform
        self.test_split = test_split

        if not self._check_exists():
            self.process_dataset(imgs)

        train_path = osp.join(self.data_folder, self.training_file)
        test_path = osp.join(self.data_folder, self.test_file)

        if train:
            with open(train_path, 'rb') as f:
                self.imgs = torch.load(f)
        else:
            with open(test_path, 'rb') as f:
                self.imgs = torch.load(f)

    def process_dataset(self, img_path):
        print("Processing dataset...")
        try:
            os.makedirs(self.data_folder)
        except OSError as e:
            if e.errno == errno.EEXIST:
                pass
            else:
                raise

        images = []
        bar = progressbar.ProgressBar()
        for path in bar(img_path):
            try:
                img = self.loader(path)
            except Exception:
                continue
            images.append(img)

        images = np.dstack(images)

        test_idx = np.random.permutation(images.shape[-1])[0:self.test_split]
        test = torch.ByteTensor(images[:, :, test_idx])
        train = torch.ByteTensor(np.delete(images, test_idx, axis=-1))

        train_path = osp.join(self.data_folder, self.training_file)
        test_path = osp.join(self.data_folder, self.test_file)

        # train = train.contiguous().view(-1, 32, 32)
        # test = test.contiguous().view(-1, 32, 32)

        with open(train_path, 'wb') as fp:
            torch.save(train, fp)

        with open(test_path, 'wb') as fp:
            torch.save(test, fp)

        print("Done!")

    def _check_exists(self):
        train_path = osp.join(self.data_folder, self.training_file)
        test_path = osp.join(self.data_folder, self.test_file)
        return osp.exists(train_path) and osp.exists(test_path)

    def __getitem__(self, index):
        img = self.imgs[:, :, index]
        # img = self.loader(path)

        # doing this so that it is consistent with all other datasets
        # to return a PIL Image
        img = Image.fromarray(img.numpy(), mode='L')

        if self.transform is not None:
            img = self.transform(img)
        # img = torch.FloatTensor(img)
        # plt.imshow(img.numpy())
        # plt.show()
        return torch.stack([img, img, img], 0)

    def __len__(self):
        return self.imgs.size(-1)
