"""Experiments
"""
import numpy as np
import chainer
import chainer.variable as variable
from chainer.functions.activation import lstm
from chainer import cuda, Function, gradient_check, report, training, utils, Variable
from chainer import datasets, iterators, optimizers, serializers
from chainer import Link, Chain, ChainList
import chainer.functions as F
import chainer.links as L
from collections import OrderedDict
import time
import os
import cv2
import shutil
import csv
from utils import to_device
from chainer_fix import BatchNormalization
from losses import ReconstructionLoss, NegativeEntropyLoss, GANLoss, WGANLoss
from sklearn.metrics import confusion_matrix
from sslgen.cnn_model import Generator, Discriminator
        
class Experiment(object):

    def __init__(self, device=None, 
                 n_cls=10, dims=100, learning_rate=1e-3, act=F.relu):
        # Settings
        self.device = device
        self.n_cls = n_cls
        self.dims = dims
        self.act = act
        self.learning_rate = learning_rate

        # Model
        self.generator = Generator(device=device, act=act, n_cls=n_cls, dims=dims)
        self.generator.to_gpu(device) if self.device else None
        self.discriminator = Discriminator(device=device, act=act)
        self.discriminator.to_gpu(device) if self.device else None

        # Optimizer
        self.optimizer_gen = optimizers.Adam(learning_rate)
        self.optimizer_gen.setup(self.generator)
        self.optimizer_gen.use_cleargrads()
        self.optimizer_dis = optimizers.Adam(learning_rate)
        self.optimizer_dis.setup(self.discriminator)
        self.optimizer_dis.use_cleargrads()
        
        # Losses
        self.recon_loss = ReconstructionLoss()
        self.gan_loss = GANLoss()
        
    def train(self, x_l, y_l, x_u):
        # Train for labeled sampels
        self._train(x_l, y_l)

        # Train for unlabeled sampels
        self._train(x_u, None)

    def _train(self, x_real, y=None):
        bs = x_real.shape[0]
        
        # Train Discriminator
        z = self.generate_random(bs, self.dims)
        x_gen = self.generator(x_real, y, z)
        d_x_gen = self.discriminator(x_gen)
        d_x = self.discriminator(x_real)
        loss_dis = self.gan_loss(d_x_gen, d_x)
        self.generator.cleargrads()
        self.discriminator.cleargrads()
        loss_dis.backward()
        self.optimizer_dis.update()
        
        # Train Generator
        z = self.generate_random(bs, self.dims)
        x_gen = self.generator(x_real, y, z)
        d_x_gen = self.discriminator(x_gen)
        loss_gen = self.gan_loss(d_x_gen) + self.recon_loss(x_gen, x_real)
        self.generator.cleargrads()
        self.discriminator.cleargrads()
        loss_gen.backward()
        self.optimizer_gen.update()
        
    def test(self, x, y):
        # Generate Images
        bs = x.shape[0]
        z = self.generate_random(bs, self.dims)
        x_gen = self.generator(x, y, test=True)
        d_x_gen = self.discriminator(x_gen, test=True)

        # Save generated images
        if os.path.exists("./test_gen"):
            shutil.rmtree("./test_gen")
            os.mkdir("./test_gen")
        else:
            os.mkdir("./test_gen")

        x_gen_data = cuda.to_cpu(x_gen.data)
        for i, img in enumerate(x_gen_data):
            fpath = "./test_gen/{:05d}.png".format(i)
            cv2.imwrite(fpath, img.reshape(28, 28) * 127.5 + 127.5)

        # D(x_gen) values
        d_x_gen_data = [float(data[0]) for data in cuda.to_cpu(d_x_gen.data)][0:100]

        return d_x_gen_data
        
    def save_model(self, epoch):
        dpath  = "./model"
        if not os.path.exists(dpath):
            os.makedirs(dpath)
            
        fpath = "./model/generator_{:05d}.h5py".format(epoch)
        serializers.save_hdf5(fpath, self.generator)

    def generate_random(self, bs, dims=30):
        r = np.random.uniform(-1, 1, (bs, dims)).astype(np.float32)
        r = to_device(r, self.device)
        return r

class Experiment000(object):

    def __init__(self, device=None, 
                 n_cls=10, dim=100, 
                 learning_rate=1e-3, learning_rate_gan=1e-5, act=F.relu):
        # Settings
        self.device = device
        self.n_cls = n_cls
        self.dim = dim
        self.act = act
        self.learning_rate = learning_rate
        self.learning_rate_gan = learning_rate_gan

        from sslgen.cnn_model_000 \
            import Encoder, Decoder, Generator0, Generator1, ImageDiscriminator

        # Model
        self.encoder = Encoder(device=device, act=act, n_cls=n_cls)
        self.decoder = Decoder(device=device, act=act, n_cls=n_cls)
        self.generator1 = self.decoder
        self.generator0 = Generator0(device=device, act=act, n_cls=n_cls, dim=dim)
        self.image_discriminator = ImageDiscriminator(device=device, act=act)
        self.encoder.to_gpu(device) if self.device else None
        self.decoder.to_gpu(device) if self.device else None
        self.generator0.to_gpu(device) if self.device else None
        self.image_discriminator.to_gpu(device) if self.device else None

        # Optimizer
        self.optimizer_enc = optimizers.Adam(self.learning_rate)
        self.optimizer_dec = optimizers.Adam(self.learning_rate)
        self.optimizer_gen0 = optimizers.Adam(self.learning_rate_gan)
        self.optimizer_gen1 = optimizers.Adam(self.learning_rate_gan)
        self.optimizer_dis = optimizers.Adam(self.learning_rate_gan)

        self.optimizer_enc.setup(self.encoder)
        self.optimizer_dec.setup(self.decoder)
        self.optimizer_gen0.setup(self.generator0)
        self.optimizer_gen1.setup(self.generator1)
        self.optimizer_dis.setup(self.image_discriminator)
        self.optimizer_enc.use_cleargrads()
        self.optimizer_dec.use_cleargrads()
        self.optimizer_gen0.use_cleargrads()
        self.optimizer_gen1.use_cleargrads()
        self.optimizer_dis.use_cleargrads()
        
        # Losses
        self.recon_loss = ReconstructionLoss()
        self.gan_loss = GANLoss()
        
    def train(self, x_l, y_l, x_u):
        # Train for labeled sampels
        self._train(x_l, y_l)

        # Train for unlabeled sampels
        self._train(x_u, None)

    def _train(self, x_real, y=None):
        # Encoder
        h = self.encoder(x_real)
        x_rec = self.decoder(h, y)
        loss_rec = self.recon_loss(x_rec, x_real)
        self.encoder.cleargrads()
        self.decoder.cleargrads()
        loss_rec.backward()
        self.optimizer_enc.update()
        self.optimizer_dec.update()
        
        # Generator
        bs = x_real.shape[0]        
        z = self.generate_random(bs, self.dim)
        h = self.generator0(z)
        x_gen = self.generator1(h, y)
        d_x_gen = self.image_discriminator(x_gen, y)
        loss_gen = self.gan_loss(d_x_gen)
        self.generator0.cleargrads()
        self.generator1.cleargrads()
        self.image_discriminator.cleargrads()
        loss_gen.backward()
        self.optimizer_gen0.update()
        self.optimizer_gen1.update()

        # Discriminator
        z = self.generate_random(bs, self.dim)
        h = self.generator0(z)
        x_gen = self.generator1(h, y)
        d_x_gen = self.image_discriminator(x_gen, y)
        d_x_real = self.image_discriminator(x_real, y)
        loss_dis = self.gan_loss(d_x_gen, d_x_real)
        self.generator0.cleargrads()
        self.generator1.cleargrads()
        self.image_discriminator.cleargrads()
        loss_dis.backward()
        self.optimizer_dis.update()

    def test(self, x, y, epoch):
        # Generate Images
        bs = x.shape[0]
        z = self.generate_random(bs, self.dim)
        h = self.generator0(z, test=True)
        x_gen = self.generator1(h, y, test=True)
        d_x_gen = self.image_discriminator(x_gen, y, test=True)

        # Save generated images
        dirpath_out = "./test_gen/{:05d}".format(epoch)
        if not os.path.exists(dirpath_out):
            os.mkdir(dirpath_out)

        x_gen_data = cuda.to_cpu(x_gen.data)
        for i, img in enumerate(x_gen_data):
            fpath = os.path.join(dirpath_out, "{:05d}.png".format(i))
            cv2.imwrite(fpath, img.reshape(28, 28) * 127.5 + 127.5)

        # D(x_gen) values
        d_x_gen_data = [float(data[0]) for data in cuda.to_cpu(d_x_gen.data)][0:100]

        return d_x_gen_data
        
    def save_model(self, epoch):
        dpath  = "./model"
        if not os.path.exists(dpath):
            os.makedirs(dpath)
            
        fpath = "./model/generator0_{:05d}.h5py".format(epoch)
        serializers.save_hdf5(fpath, self.generator0)
        fpath = "./model/generator1_{:05d}.h5py".format(epoch)
        serializers.save_hdf5(fpath, self.generator1)

    def generate_random(self, bs, dim=30):
        r = np.random.uniform(-1, 1, (bs, dim)).astype(np.float32)
        r = to_device(r, self.device)
        return r

class Experiment001(object):
    """Patch Discriminator
    """
    def __init__(self, device=None, 
                 n_cls=10, dim=100, 
                 learning_rate=1e-3, learning_rate_gan=1e-5, act=F.relu):
        # Settings
        self.device = device
        self.n_cls = n_cls
        self.dim = dim
        self.act = act
        self.learning_rate = learning_rate
        self.learning_rate_gan = learning_rate_gan

        from sslgen.cnn_model_000 \
            import Encoder, Decoder, Generator0, Generator1, PatchDiscriminator

        # Model
        self.encoder = Encoder(device=device, act=act, n_cls=n_cls)
        self.decoder = Decoder(device=device, act=act, n_cls=n_cls)
        self.generator1 = self.decoder
        self.generator0 = Generator0(device=device, act=act, n_cls=n_cls, dim=dim)
        self.patch_discriminator = PatchDiscriminator(device=device, act=act)
        self.encoder.to_gpu(device) if self.device else None
        self.decoder.to_gpu(device) if self.device else None
        self.generator0.to_gpu(device) if self.device else None
        self.patch_discriminator.to_gpu(device) if self.device else None

        # Optimizer
        self.optimizer_enc = optimizers.Adam(self.learning_rate)
        self.optimizer_dec = optimizers.Adam(self.learning_rate)
        self.optimizer_gen0 = optimizers.Adam(self.learning_rate_gan)
        self.optimizer_gen1 = optimizers.Adam(self.learning_rate_gan)
        self.optimizer_dis = optimizers.Adam(self.learning_rate_gan)

        self.optimizer_enc.setup(self.encoder)
        self.optimizer_dec.setup(self.decoder)
        self.optimizer_gen0.setup(self.generator0)
        self.optimizer_gen1.setup(self.generator1)
        self.optimizer_dis.setup(self.patch_discriminator)
        self.optimizer_enc.use_cleargrads()
        self.optimizer_dec.use_cleargrads()
        self.optimizer_gen0.use_cleargrads()
        self.optimizer_gen1.use_cleargrads()
        self.optimizer_dis.use_cleargrads()
        
        # Losses
        self.recon_loss = ReconstructionLoss()
        self.gan_loss = GANLoss()
        
    def train(self, x_l, y_l, x_u):
        # Train for labeled sampels
        self._train(x_l, y_l)

        # Train for unlabeled sampels
        self._train(x_u, None)

    def _train(self, x_real, y=None):
        # Encoder
        h = self.encoder(x_real)
        x_rec = self.decoder(h, y)
        loss_rec = self.recon_loss(x_rec, x_real)
        self.encoder.cleargrads()
        self.decoder.cleargrads()
        loss_rec.backward()
        self.optimizer_enc.update()
        self.optimizer_dec.update()
        
        # Generator
        bs = x_real.shape[0]        
        z = self.generate_random(bs, self.dim)
        h = self.generator0(z)
        x_gen = self.generator1(h, y)
        loss_gen = self.gan_loss(x_gen)
        self.generator0.cleargrads()
        self.generator1.cleargrads()
        self.patch_discriminator.cleargrads()
        loss_gen.backward()
        self.optimizer_gen0.update()
        self.optimizer_gen1.update()

        # Discriminator
        z = self.generate_random(bs, self.dim)
        h = self.generator0(z)
        x_gen = self.generator1(h, y)
        loss_dis = self.gan_loss(x_gen, x_real)
        self.generator0.cleargrads()
        self.generator1.cleargrads()
        self.patch_discriminator.cleargrads()
        loss_dis.backward()
        self.optimizer_dis.update()

    def test(self, x, y, epoch):
        # Generate Images
        bs = x.shape[0]
        z = self.generate_random(bs, self.dim)
        h = self.generator0(z, test=True)
        x_gen = self.generator1(h, y, test=True)
        d_x_gen = self.patch_discriminator(x_gen, test=True)

        # Save generated images
        dirpath_out = "./test_gen/{:05d}".format(epoch)
        if not os.path.exists(dirpath_out):
            os.mkdir(dirpath_out)

        x_gen_data = cuda.to_cpu(x_gen.data)
        for i, img in enumerate(x_gen_data):
            fpath = os.path.join(dirpath_out, "{:05d}.png".format(i))
            cv2.imwrite(fpath, img.reshape(28, 28) * 127.5 + 127.5)

        # D(x_gen) values
        d_x_gen_data = [float(data[0]) for data in cuda.to_cpu(d_x_gen.data)][0:100]

        return loss_gen_data
        
    def save_model(self, epoch):
        dpath  = "./model"
        if not os.path.exists(dpath):
            os.makedirs(dpath)
            
        fpath = "./model/generator0_{:05d}.h5py".format(epoch)
        serializers.save_hdf5(fpath, self.generator0)
        fpath = "./model/generator1_{:05d}.h5py".format(epoch)
        serializers.save_hdf5(fpath, self.generator1)

    def generate_random(self, bs, dim=30):
        r = np.random.uniform(-1, 1, (bs, dim)).astype(np.float32)
        r = to_device(r, self.device)
        return r

class Experiment002(Experiment000):
    """Train also encoder when training gan and conncat h and h_gen
    """

    def __init__(self, device=None, 
                 dim=100, 
                 learning_rate=1e-3, learning_rate_gan=1e-5, act=F.relu):
        # Settings
        self.device = device
        self.dim = dim
        self.act = act
        self.learning_rate = learning_rate
        self.learning_rate_gan = learning_rate_gan

        from sslgen.cnn_model_001 \
            import Encoder, Decoder, Generator0, Generator1, ImageDiscriminator

        # Model
        self.encoder = Encoder(device=device, act=act)
        self.decoder = Decoder(device=device, act=act)
        self.generator1 = self.decoder
        self.generator0 = Generator0(device=device, act=act, dim=dim)
        self.image_discriminator = ImageDiscriminator(device=device, act=act)
        self.encoder.to_gpu(device) if self.device else None
        self.decoder.to_gpu(device) if self.device else None
        self.generator0.to_gpu(device) if self.device else None
        self.image_discriminator.to_gpu(device) if self.device else None

        # Optimizer
        self.optimizer_enc = optimizers.Adam(self.learning_rate)
        self.optimizer_dec = optimizers.Adam(self.learning_rate)
        self.optimizer_gen0 = optimizers.Adam(self.learning_rate_gan)
        self.optimizer_gen1 = optimizers.Adam(self.learning_rate_gan)
        self.optimizer_dis = optimizers.Adam(self.learning_rate_gan)

        self.optimizer_enc.setup(self.encoder)
        self.optimizer_dec.setup(self.decoder)
        self.optimizer_gen0.setup(self.generator0)
        self.optimizer_gen1.setup(self.generator1)
        self.optimizer_dis.setup(self.image_discriminator)
        self.optimizer_enc.use_cleargrads()
        self.optimizer_dec.use_cleargrads()
        self.optimizer_gen0.use_cleargrads()
        self.optimizer_gen1.use_cleargrads()
        self.optimizer_dis.use_cleargrads()
        
        # Losses
        self.recon_loss = ReconstructionLoss()
        self.gan_loss = GANLoss()

    def train(self, x_real):
        # Encoder
        h = self.encoder(x_real)
        x_rec = self.decoder(h)
        loss_rec = self.recon_loss(x_rec, x_real)
        self.encoder.cleargrads()
        self.decoder.cleargrads()
        loss_rec.backward()
        self.optimizer_enc.update()
        self.optimizer_dec.update()
        
        # Generator
        h = self.encoder(x_real)
        bs = x_real.shape[0]        
        z = self.generate_random(bs, self.dim)
        h_gen = self.generator0(z)
        x_gen = self.generator1(h, h_gen)
        d_x_gen = self.image_discriminator(x_gen)
        loss_gen = self.gan_loss(d_x_gen)
        self.encoder.cleargrads()
        self.generator0.cleargrads()
        self.generator1.cleargrads()
        self.image_discriminator.cleargrads()
        loss_gen.backward()
        self.optimizer_enc.update()
        self.optimizer_gen0.update()
        self.optimizer_gen1.update()

        # Discriminator
        h = self.encoder(x_real)
        z = self.generate_random(bs, self.dim)
        h_gen = self.generator0(z)
        x_gen = self.generator1(h, h_gen)
        d_x_gen = self.image_discriminator(x_gen)
        d_x_real = self.image_discriminator(x_real)
        loss_dis = self.gan_loss(d_x_gen, d_x_real)
        self.generator0.cleargrads()
        self.generator1.cleargrads()
        self.image_discriminator.cleargrads()
        loss_dis.backward()
        self.optimizer_dis.update()

    def test(self, x, epoch):
        # Generate Images
        bs = x.shape[0]
        z = self.generate_random(bs, self.dim)
        h = self.encoder(x)
        h_gen = self.generator0(z, test=True)
        x_gen = self.generator1(h, h_gen, test=True)
        d_x_gen = self.image_discriminator(x_gen, test=True)

        # Save generated images
        dirpath_out = "./test_gen/{:05d}".format(epoch)
        if not os.path.exists(dirpath_out):
            os.mkdir(dirpath_out)

        x_gen_data = cuda.to_cpu(x_gen.data)
        for i, img in enumerate(x_gen_data):
            fpath = os.path.join(dirpath_out, "{:05d}.png".format(i))
            cv2.imwrite(fpath, img.reshape(28, 28) * 127.5 + 127.5)

        # D(x_gen) values
        d_x_gen_data = [float(data[0]) for data in cuda.to_cpu(d_x_gen.data)][0:100]

        return d_x_gen_data
        
    def save_model(self, epoch):
        dpath  = "./model"
        if not os.path.exists(dpath):
            os.makedirs(dpath)
            
        fpath = "./model/generator0_{:05d}.h5py".format(epoch)
        serializers.save_hdf5(fpath, self.generator0)
        fpath = "./model/generator1_{:05d}.h5py".format(epoch)
        serializers.save_hdf5(fpath, self.generator1)

    def generate_random(self, bs, dim=30):
        r = np.random.uniform(-1, 1, (bs, dim)).astype(np.float32)
        r = to_device(r, self.device)
        return r

class Experiment003(Experiment002):
    """Train also encoder when training gan
    """

    def __init__(self, device=None, 
                 dim=100, 
                 learning_rate=1e-3, learning_rate_gan=1e-5, act=F.relu):
        # Settings
        self.device = device
        self.dim = dim
        self.act = act
        self.learning_rate = learning_rate
        self.learning_rate_gan = learning_rate_gan

        from sslgen.cnn_model_002 \
            import Encoder, Decoder, Generator0, Generator1, ImageDiscriminator

        # Model
        self.encoder = Encoder(device=device, act=act)
        self.decoder = Decoder(device=device, act=act)
        self.generator1 = self.decoder
        self.generator0 = Generator0(device=device, act=act, dim=dim)
        self.image_discriminator = ImageDiscriminator(device=device, act=act)
        self.encoder.to_gpu(device) if self.device else None
        self.decoder.to_gpu(device) if self.device else None
        self.generator0.to_gpu(device) if self.device else None
        self.image_discriminator.to_gpu(device) if self.device else None

        # Optimizer
        self.optimizer_enc = optimizers.Adam(self.learning_rate)
        self.optimizer_dec = optimizers.Adam(self.learning_rate)
        self.optimizer_gen0 = optimizers.Adam(self.learning_rate_gan)
        self.optimizer_gen1 = optimizers.Adam(self.learning_rate_gan)
        self.optimizer_dis = optimizers.Adam(self.learning_rate_gan)

        self.optimizer_enc.setup(self.encoder)
        self.optimizer_dec.setup(self.decoder)
        self.optimizer_gen0.setup(self.generator0)
        self.optimizer_gen1.setup(self.generator1)
        self.optimizer_dis.setup(self.image_discriminator)
        self.optimizer_enc.use_cleargrads()
        self.optimizer_dec.use_cleargrads()
        self.optimizer_gen0.use_cleargrads()
        self.optimizer_gen1.use_cleargrads()
        self.optimizer_dis.use_cleargrads()
        
        # Losses
        self.recon_loss = ReconstructionLoss()
        self.gan_loss = GANLoss()

    def train(self, x_real):
        # Encoder
        h = self.encoder(x_real)
        x_rec = self.decoder(h)
        loss_rec = self.recon_loss(x_rec, x_real)
        self.encoder.cleargrads()
        self.decoder.cleargrads()
        loss_rec.backward()
        self.optimizer_enc.update()
        self.optimizer_dec.update()
        
        # Generator
        h = self.encoder(x_real)
        bs = x_real.shape[0]        
        z = self.generate_random(bs, self.dim)
        h_gen = self.generator0(z)
        x_gen = self.generator1(h, h_gen)
        d_x_gen = self.image_discriminator(x_gen)
        loss_gen = self.gan_loss(d_x_gen)
        self.generator0.cleargrads()
        self.generator1.cleargrads()
        self.image_discriminator.cleargrads()
        loss_gen.backward()
        self.optimizer_gen0.update()
        self.optimizer_gen1.update()

        # Discriminator
        h = self.encoder(x_real)
        z = self.generate_random(bs, self.dim)
        h_gen = self.generator0(z)
        x_gen = self.generator1(h, h_gen)
        d_x_gen = self.image_discriminator(x_gen)
        d_x_real = self.image_discriminator(x_real)
        loss_dis = self.gan_loss(d_x_gen, d_x_real)
        self.generator0.cleargrads()
        self.generator1.cleargrads()
        self.image_discriminator.cleargrads()
        loss_dis.backward()
        self.optimizer_dis.update()

    def test(self, x, epoch):
        # Generate Images
        bs = x.shape[0]
        z = self.generate_random(bs, self.dim)
        h = self.encoder(x)
        h_gen = self.generator0(z, test=True)
        x_gen = self.generator1(h, h_gen, test=True) #TODO: which should be used?
        d_x_gen = self.image_discriminator(x_gen, test=True)

        # Save generated images
        dirpath_out = "./test_gen/{:05d}".format(epoch)
        if not os.path.exists(dirpath_out):
            os.mkdir(dirpath_out)

        x_gen_data = cuda.to_cpu(x_gen.data)
        for i, img in enumerate(x_gen_data):
            fpath = os.path.join(dirpath_out, "{:05d}.png".format(i))
            cv2.imwrite(fpath, img.reshape(28, 28) * 127.5 + 127.5)

        # D(x_gen) values
        d_x_gen_data = [float(data[0]) for data in cuda.to_cpu(d_x_gen.data)][0:100]

        return d_x_gen_data
        
    def save_model(self, epoch):
        dpath  = "./model"
        if not os.path.exists(dpath):
            os.makedirs(dpath)
            
        fpath = "./model/generator0_{:05d}.h5py".format(epoch)
        serializers.save_hdf5(fpath, self.generator0)
        fpath = "./model/generator1_{:05d}.h5py".format(epoch)
        serializers.save_hdf5(fpath, self.generator1)

    def generate_random(self, bs, dim=30):
        r = np.random.uniform(-1, 1, (bs, dim)).astype(np.float32)
        r = to_device(r, self.device)
        return r

class Experiment004(Experiment000):
    """Wasserstein GAN Loss
    """

    def __init__(self, device=None, 
                 n_cls=10, dim=100, 
                 learning_rate=1e-3, learning_rate_gan=1e-5, act=F.relu):
        # Settings
        self.device = device
        self.n_cls = n_cls
        self.dim = dim
        self.act = act
        self.learning_rate = learning_rate
        self.learning_rate_gan = learning_rate_gan

        from sslgen.cnn_model_000 \
            import Encoder, Decoder, Generator0, Generator1, ImageDiscriminator

        # Model
        self.encoder = Encoder(device=device, act=act, n_cls=n_cls)
        self.decoder = Decoder(device=device, act=act, n_cls=n_cls)
        self.generator1 = self.decoder
        self.generator0 = Generator0(device=device, act=act, n_cls=n_cls, dim=dim)
        self.image_discriminator = ImageDiscriminator(device=device, act=act)
        self.encoder.to_gpu(device) if self.device else None
        self.decoder.to_gpu(device) if self.device else None
        self.generator0.to_gpu(device) if self.device else None
        self.image_discriminator.to_gpu(device) if self.device else None

        # Optimizer
        self.optimizer_enc = optimizers.Adam(self.learning_rate)
        self.optimizer_dec = optimizers.Adam(self.learning_rate)
        self.optimizer_gen0 = optimizers.Adam(self.learning_rate_gan)
        self.optimizer_gen1 = optimizers.Adam(self.learning_rate_gan)
        self.optimizer_dis = optimizers.Adam(self.learning_rate_gan)

        self.optimizer_enc.setup(self.encoder)
        self.optimizer_dec.setup(self.decoder)
        self.optimizer_gen0.setup(self.generator0)
        self.optimizer_gen1.setup(self.generator1)
        self.optimizer_dis.setup(self.image_discriminator)
        self.optimizer_enc.use_cleargrads()
        self.optimizer_dec.use_cleargrads()
        self.optimizer_gen0.use_cleargrads()
        self.optimizer_gen1.use_cleargrads()
        self.optimizer_dis.use_cleargrads()
        
        # Losses
        self.recon_loss = ReconstructionLoss()
        self.gan_loss = WGANLoss()
        
    def test(self, x, y, epoch):
        # Generate Images
        bs = x.shape[0]
        z = self.generate_random(bs, self.dim)
        h = self.generator0(z, test=True)
        x_gen = self.generator1(h, y, test=True)
        d_x_gen = self.image_discriminator(x_gen, y, test=True)
        d_x_real = self.image_discriminator(x, y, test=True)
        loss = - self.gan_loss(d_x_gen, d_x_real)

        # Save generated images
        dirpath_out = "./test_gen/{:05d}".format(epoch)
        if not os.path.exists(dirpath_out):
            os.mkdir(dirpath_out)

        x_gen_data = cuda.to_cpu(x_gen.data)
        for i, img in enumerate(x_gen_data):
            fpath = os.path.join(dirpath_out, "{:05d}.png".format(i))
            cv2.imwrite(fpath, img.reshape(28, 28) * 127.5 + 127.5)

        return cuda.to_cpu(loss.data)
        
