import random
import os
import tarfile
from time import time

from IPython.display import set_matplotlib_formats
from matplotlib import pyplot as plt
import mxnet as mx
from mxnet import autograd, gluon, image, nd
from mxnet.gluon import nn, data as gdata, loss as gloss, utils as gutils
import numpy as np

# Set default figure size.
set_matplotlib_formats('retina')

def set_figsize(figsize=(3.5, 2.5)):
    """Set matplotlib figure size."""
    plt.rcParams['figure.figsize'] = figsize

set_figsize()


voc_rgb_mean = nd.array([0.485, 0.456, 0.406])
voc_rgb_std = nd.array([0.229, 0.224, 0.225])


def accuracy(y_hat, y): 
    """Get accuracy."""
    return (y_hat.argmax(axis=1) == y.astype('float32')).mean().asscalar()


def bbox_to_rect(bbox, color):
    """Convert bounding box to matplotlib format."""
    return plt.Rectangle(xy=(bbox[0], bbox[1]), width=bbox[2]-bbox[0],
                         height=bbox[3]-bbox[1], fill=False, edgecolor=color,
                         linewidth=2)


def data_iter(batch_size, features, labels):
    """Iterate through a data set."""
    num_examples = len(features)
    indices = list(range(num_examples))
    random.shuffle(indices)
    for i in range(0, num_examples, batch_size):
        j = nd.array(indices[i: min(i + batch_size, num_examples)])
        yield features.take(j), labels.take(j)


def data_iter_consecutive(corpus_indices, batch_size, num_steps, ctx=None):
    """Sample mini-batches in a consecutive order from sequential data."""
    corpus_indices = nd.array(corpus_indices, ctx=ctx)
    data_len = len(corpus_indices)
    batch_len = data_len // batch_size
    indices = corpus_indices[0 : batch_size*batch_len].reshape((
        batch_size, batch_len))
    epoch_size = (batch_len - 1) // num_steps
    for i in range(epoch_size):
        i = i * num_steps
        X = indices[:, i : i+num_steps]
        Y = indices[:, i+1 : i+num_steps+1]
        yield X, Y


def data_iter_random(corpus_indices, batch_size, num_steps, ctx=None):
    """Sample mini-batches in a random order from sequential data."""
    num_examples = (len(corpus_indices) - 1) // num_steps
    epoch_size = num_examples // batch_size
    example_indices = list(range(num_examples))
    random.shuffle(example_indices)
    def _data(pos):
        return corpus_indices[pos : pos+num_steps]
    for i in range(epoch_size):
        i = i * batch_size
        batch_indices = example_indices[i : i+batch_size]
        X = nd.array(
            [_data(j * num_steps) for j in batch_indices], ctx=ctx)
        Y = nd.array(
            [_data(j * num_steps + 1) for j in batch_indices], ctx=ctx)
        yield X, Y


def _download_pikachu(data_dir):
    root_url = ('https://apache-mxnet.s3-accelerate.amazonaws.com/'
                'gluon/dataset/pikachu/')
    dataset = {'train.rec': 'e6bcb6ffba1ac04ff8a9b1115e650af56ee969c8',
               'train.idx': 'dcf7318b2602c06428b9988470c731621716c393',
               'val.rec': 'd6c33f799b4d058e82f2cb5bd9a976f69d72d520'}
    for k, v in dataset.items():
        gutils.download(root_url+k, data_dir+k, sha1_hash=v)


def _download_voc_pascal(data_dir='../data'):
    voc_dir = data_dir + '/VOCdevkit/VOC2012'
    url = ('http://host.robots.ox.ac.uk/pascal/VOC/voc2012'
           '/VOCtrainval_11-May-2012.tar')
    sha1 = '4e443f8a2eca6b1dac8a6c57641b67dd40621a49'
    fname = gutils.download(url, data_dir, sha1_hash=sha1)
    if not os.path.exists(voc_dir+'/ImageSets/Segmentation/train.txt'):
        with tarfile.open(fname, 'r') as f:
            f.extractall(data_dir)
    return voc_dir


def evaluate_accuracy(data_iter, net, ctx=[mx.cpu()]):
    """Evaluate accuracy of a model on the given data set."""
    if isinstance(ctx, mx.Context):
        ctx = [ctx]
    acc = nd.array([0])
    n = 0
    if isinstance(data_iter, mx.io.MXDataIter):
        data_iter.reset()
    for batch in data_iter:
        features, labels, batch_size = _get_batch(batch, ctx)
        for X, y in zip(features, labels):
            y = y.astype('float32')
            acc += (net(X).argmax(axis=1)==y).sum().copyto(mx.cpu())
            n += y.size
        acc.wait_to_read()
    return acc.asscalar() / n


def _get_batch(batch, ctx):
    """Return features and labels on ctx."""
    if isinstance(batch, mx.io.DataBatch):
        features = batch.data[0]
        labels = batch.label[0]
    else:
        features, labels = batch
    if labels.dtype != features.dtype:
        labels = labels.astype(features.dtype)
    return (gutils.split_and_load(features, ctx),
            gutils.split_and_load(labels, ctx),
            features.shape[0])


def grad_clipping(params, theta, ctx):
    """Clip the gradient."""
    if theta is not None:
        norm = nd.array([0.0], ctx)
        for param in params:
            norm += (param.grad ** 2).sum()
        norm = norm.sqrt().asscalar()
        if norm > theta:
            for param in params:
                param.grad[:] *= theta / norm


def linreg(X, w, b):
    """Linear regression."""
    return nd.dot(X, w) + b


def load_data_fashion_mnist(batch_size, resize=None,
                            root=os.path.join('~', '.mxnet', 'datasets',
                                              'fashion-mnist'):
    """Download the fashion mnist dataest and then load into memory."""
    root = os.path.expanduser(root)
    transformer = []
    if resize:
        transformer += [gdata.vision.transforms.Resize(resize)]
    transformer += [gdata.vision.transforms.ToTensor()]
    transformer = gdata.vision.transforms.Compose(transformer)

    mnist_train = gdata.vision.FashionMNIST(root=root, train=True)
    mnist_test = gdata.vision.FashionMNIST(root=root, train=False)
    train_iter = gdata.DataLoader(mnist_train.transform_first(transformer),
                                  batch_size, shuffle=True, num_workers=4)
    test_iter = gdata.DataLoader(mnist_test.transform_first(transformer),
                                 batch_size, shuffle=False, num_workers=4)
    return train_iter, test_iter


def load_data_pascal_voc(batch_size, output_shape): 
    """Download the pascal voc dataest and then load into memory."""
    voc_train = VOCSegDataset(True, output_shape) 
    voc_test = VOCSegDataset(False, output_shape) 
 
    train_iter = gdata.DataLoader( 
        voc_train, batch_size, shuffle=True,last_batch='discard',
        num_workers=4) 
    test_iter = gdata.DataLoader( 
        voc_test, batch_size,last_batch='discard', num_workers=4) 
    return train_iter, test_iter


def load_data_pikachu(batch_size, edge_size=256):                                                                                
    """Download the pikachu dataest and then load into memory."""
    data_dir = '../data/pikachu/'
    _download_pikachu(data_dir)
    train_iter = image.ImageDetIter(
        path_imgrec=data_dir+'train.rec',
        path_imgidx=data_dir+'train.idx',
        batch_size=batch_size,
        data_shape=(3, edge_size, edge_size),
        shuffle=True,
        rand_crop=1,
        min_object_covered=0.95,
        max_attempts=200)
    val_iter = image.ImageDetIter(
        path_imgrec=data_dir+'val.rec',
        batch_size=batch_size,
        data_shape=(3, edge_size, edge_size),
        shuffle=False)
    return train_iter, val_iter


def _make_list(obj, default_values=None):
    if obj is None:
        obj = default_values
    elif not isinstance(obj, (list, tuple)):
        obj = [obj]
    return obj


def normalize_voc_image(data):
    """Normalize VOC images."""
    return (data.astype('float32') / 255 - voc_rgb_mean) / voc_rgb_std


def optimize(batch_size, trainer, num_epochs, decay_epoch, log_interval,
             features, labels, net):
    """Optimize an objective function."""
    dataset = gdata.ArrayDataset(features, labels)
    data_iter = gdata.DataLoader(dataset, batch_size, shuffle=True)
    loss = gloss.L2Loss()
    ls = [loss(net(features), labels).mean().asnumpy()]
    for epoch in range(1, num_epochs + 1):
        # Decay the learning rate.
        if decay_epoch and epoch > decay_epoch:
            trainer.set_learning_rate(trainer.learning_rate * 0.1)
        for batch_i, (X, y) in enumerate(data_iter):
            with autograd.record():
                l = loss(net(X), y)
            l.backward()
            trainer.step(batch_size)
            if batch_i * batch_size % log_interval == 0:
                ls.append(loss(net(features), labels).mean().asnumpy())
    # To print more conveniently, use numpy.
    print('w:', net[0].weight.data(), '\nb:', net[0].bias.data(), '\n')
    es = np.linspace(0, num_epochs, len(ls), endpoint=True)
    semilogy(es, ls, 'epoch', 'loss')


def predict_rnn(rnn, prefix, num_chars, params, num_hiddens, vocab_size, ctx,
                idx_to_char, char_to_idx, get_inputs, is_lstm=False):
    """Predict the next chars given the prefix."""
    prefix = prefix.lower()
    state_h = nd.zeros(shape=(1, num_hiddens), ctx=ctx)
    if is_lstm:
        state_c = nd.zeros(shape=(1, num_hiddens), ctx=ctx)
    output = [char_to_idx[prefix[0]]]
    for i in range(num_chars + len(prefix)):
        X = nd.array([output[-1]], ctx=ctx)
        if is_lstm:
            Y, state_h, state_c = rnn(get_inputs(X, vocab_size), state_h,
                                      state_c, *params)
        else:
            Y, state_h = rnn(get_inputs(X, vocab_size), state_h, *params)
        if i < len(prefix) - 1:
            next_input = char_to_idx[prefix[i + 1]]
        else:
            next_input = int(Y[0].argmax(axis=1).asscalar())
        output.append(next_input)
    return ''.join([idx_to_char[i] for i in output])


def read_voc_images(root='../data/VOCdevkit/VOC2012', train=True):                                                               
    """Read VOC images."""
    txt_fname = '%s/ImageSets/Segmentation/%s'%(
        root, 'train.txt' if train else 'val.txt')
    with open(txt_fname, 'r') as f:
        images = f.read().split()
    data, label = [None] * len(images), [None] * len(images)
    for i, fname in enumerate(images):
        data[i] = image.imread('%s/JPEGImages/%s.jpg'%(root, fname))
        label[i] = image.imread('%s/SegmentationClass/%s.png'%(root, fname))
    return data, label


class Residual(nn.HybridBlock):
    """The residual block."""
    def __init__(self, channels, same_shape=True, **kwargs):
        super(Residual, self).__init__(**kwargs)
        self.same_shape = same_shape
        strides = 1 if same_shape else 2
        self.conv1 = nn.Conv2D(channels, kernel_size=3, padding=1,
                               strides=strides)
        self.bn1 = nn.BatchNorm()
        self.conv2 = nn.Conv2D(channels, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm()
        if not same_shape:
            self.conv3 = nn.Conv2D(channels, kernel_size=1,
                                  strides=strides)

    def hybrid_forward(self, F, x):
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        if not self.same_shape:
            x = self.conv3(x)
        return F.relu(out + x)


def resnet18(num_classes):
    """The ResNet-18 model."""
    net = nn.HybridSequential()
    net.add(nn.BatchNorm(),
            nn.Conv2D(64, kernel_size=3, strides=1),
            nn.MaxPool2D(pool_size=3, strides=2),
            Residual(64),
            Residual(64),
            Residual(128, same_shape=False),
            Residual(128),
            Residual(256, same_shape=False),
            Residual(256),
            nn.GlobalAvgPool2D(),
            nn.Dense(num_classes))
    return net


def semilogy(x_vals, y_vals, x_label, y_label, x2_vals=None, y2_vals=None,
             legend=None, figsize=(3.5, 2.5)):
    """Plot x and log(y)."""
    set_figsize()
    set_matplotlib_formats('retina')
    plt.xlabel(x_label)
    plt.ylabel(y_label)
    plt.semilogy(x_vals, y_vals)
    if x2_vals and y2_vals:
        plt.semilogy(x2_vals, y2_vals)
        plt.legend(legend)
    plt.show()


def sgd(params, lr, batch_size):                                                                                                 
    """Mini-batch stochastic gradient descent."""
    for param in params:
        param[:] = param - lr * param.grad / batch_size


def show_bboxes(axes, bboxes, labels=None, colors=None):                                                                         
    """Show bounding boxes."""
    labels = _make_list(labels)
    colors = _make_list(colors, ['b', 'g', 'r',  'm', 'k'])
    for i, bbox in enumerate(bboxes):
        color = colors[i%len(colors)]
        rect = bbox_to_rect(bbox.asnumpy(), color)
        axes.add_patch(rect)
        if labels and len(labels) > i:
            text_color = 'k' if color == 'w' else 'w'
            axes.text(rect.xy[0], rect.xy[1], labels[i],
                      va='center', ha='center', fontsize=9, color=text_color,
                      bbox=dict(facecolor=color, lw=0))


def show_images(imgs, num_rows, num_cols, scale=2):                                                                              
    """Plot a list of images."""
    figsize = (num_cols*scale, num_rows*scale)
    _, axes = plt.subplots(num_rows, num_cols, figsize=figsize)
    for i in range(num_rows):
        for j in range(num_cols):
            axes[i][j].imshow(imgs[i*num_cols+j].asnumpy())
            axes[i][j].axes.get_xaxis().set_visible(False)
            axes[i][j].axes.get_yaxis().set_visible(False)
    return axes


def squared_loss(y_hat, y):
    """Squared loss."""
    return (y_hat - y.reshape(y_hat.shape)) ** 2 / 2


def to_onehot(X, size):
    """Represent inputs with one-hot encoding."""
    return [nd.one_hot(x, size) for x in X.T]


def train(train_iter, test_iter, net, loss, trainer, ctx, num_epochs,
          print_batches=None):
    """Train and evaluate a model."""
    print('training on', ctx)
    if isinstance(ctx, mx.Context):
        ctx = [ctx]
    for epoch in range(1, num_epochs + 1):
        train_l_sum, train_acc_sum, n, m = 0.0, 0.0, 0.0, 0.0
        if isinstance(train_iter, mx.io.MXDataIter):
            train_iter.reset()
        start = time()
        for i, batch in enumerate(train_iter):
            Xs, ys, batch_size = _get_batch(batch, ctx)
            ls = []
            with autograd.record():
                y_hats = [net(X) for X in Xs]
                ls = [loss(y_hat, y) for y_hat, y in zip(y_hats, ys)]
            for l in ls:
                l.backward()
            train_acc_sum += sum([(y_hat.argmax(axis=1) == y).sum().asscalar()
                                 for y_hat, y in zip(y_hats, ys)])
            train_l_sum += sum([l.sum().asscalar() for l in ls])
            trainer.step(batch_size)
            n += batch_size
            m += sum([y.size for y in ys])
            if print_batches and (i+1) % print_batches == 0:
                print('batch %d, loss %f, train acc %f' % (
                    n, train_l_sum / n, train_acc_sum / m
                ))
        test_acc = evaluate_accuracy(test_iter, net, ctx)
        print('epoch %d, loss %.4f, train acc %.3f, test acc %.3f, '
              'time %.1f sec'
              % (epoch, train_l_sum / n, train_acc_sum / m, test_acc,
                 time() - start))


def train_and_predict_rnn(rnn, is_random_iter, num_epochs, num_steps,                                                            
                          num_hiddens, lr, clipping_theta, batch_size,
                          vocab_size, pred_period, pred_len, prefixes,
                          get_params, get_inputs, ctx, corpus_indices,
                          idx_to_char, char_to_idx, is_lstm=False):
    """Train an RNN model and predict the next item in the sequence."""
    if is_random_iter:
        data_iter = data_iter_random
    else:
        data_iter = data_iter_consecutive
    params = get_params()
    loss = gloss.SoftmaxCrossEntropyLoss()

    for epoch in range(1, num_epochs + 1):
        if not is_random_iter:
            state_h = nd.zeros(shape=(batch_size, num_hiddens), ctx=ctx)
            if is_lstm:
                state_c = nd.zeros(shape=(batch_size, num_hiddens), ctx=ctx)
        train_l_sum = nd.array([0], ctx=ctx)
        train_l_cnt = 0
        for X, Y in data_iter(corpus_indices, batch_size, num_steps, ctx):
            if is_random_iter:
                state_h = nd.zeros(shape=(batch_size, num_hiddens), ctx=ctx)
                if is_lstm:
                    state_c = nd.zeros(shape=(batch_size, num_hiddens),
                                       ctx=ctx)
            else:
                state_h = state_h.detach()
                if is_lstm:
                    state_c = state_c.detach()
            with autograd.record():
                if is_lstm:
                    outputs, state_h, state_c = rnn(
                        get_inputs(X, vocab_size), state_h, state_c, *params)
                else:
                    outputs, state_h = rnn(
                        get_inputs(X, vocab_size), state_h, *params)
                y = Y.T.reshape((-1,))
                outputs = nd.concat(*outputs, dim=0)
                l = loss(outputs, y)
            l.backward()
            grad_clipping(params, clipping_theta, ctx)
            sgd(params, lr, 1)
            train_l_sum = train_l_sum + l.sum()
            train_l_cnt += l.size
        if epoch % pred_period == 0:
            print('\nepoch %d, perplexity %f'
                  % (epoch, (train_l_sum / train_l_cnt).exp().asscalar()))
            for prefix in prefixes:
                print(' - ', predict_rnn(
                    rnn, prefix, pred_len, params, num_hiddens, vocab_size,
                    ctx, idx_to_char, char_to_idx, get_inputs, is_lstm))


def train_ch3(net, train_iter, test_iter, loss, num_epochs, batch_size,
              params=None, lr=None, trainer=None):
    """Train and evaluate a model on CPU."""
    for epoch in range(1, num_epochs + 1):
        train_l_sum = 0
        train_acc_sum = 0
        for X, y in train_iter:
            with autograd.record():
                y_hat = net(X)
                l = loss(y_hat, y)
            l.backward()
            if trainer is None:
                sgd(params, lr, batch_size)
            else:
                trainer.step(batch_size)
            train_l_sum += l.mean().asscalar()
            train_acc_sum += accuracy(y_hat, y)
        test_acc = evaluate_accuracy(test_iter, net)
        print('epoch %d, loss %.4f, train acc %.3f, test acc %.3f'
              % (epoch, train_l_sum / len(train_iter),
                 train_acc_sum / len(train_iter), test_acc))


def try_all_gpus():
    """Return all available GPUs, or [mx.gpu()] if there is no GPU."""
    ctxes = []
    try:
        for i in range(16):
            ctx = mx.gpu(i)
            _ = nd.array([0], ctx=ctx)
            ctxes.append(ctx)
    except:
        pass
    if not ctxes:
        ctxes = [mx.cpu()]
    return ctxes


def try_gpu():
    """If GPU is available, return mx.gpu(0); else return mx.cpu()."""
    try:
        ctx = mx.gpu()
        _ = nd.array([0], ctx=ctx)
    except:
        ctx = mx.cpu()
    return ctx 


class VOCSegDataset(gluon.data.Dataset):
    """The Pascal VOC2012 Dataset."""
    def __init__(self, train, crop_size): 
        self.train = train 
        self.crop_size = crop_size 
        self.rgb_mean = nd.array([0.485, 0.456, 0.406]) 
        self.rgb_std = nd.array([0.229, 0.224, 0.225]) 
        self.voc_colormap = [[0,0,0], [128,0,0], [0,128,0], [128,128,0],
                             [0,0,128], [128,0,128], [0,128,128],
                             [128,128,128], [64,0,0], [192,0,0], [64,128,0],
                             [192,128,0], [64,0,128], [192,0,128], 
                             [64,128,128], [192,128,128], [0,64,0],
                             [128,64,0], [0,192,0], [128,192,0], [0,64,128]] 
        self.voc_classes = ['background', 'aeroplane', 'bicycle', 'bird',
                            'boat', 'bottle', 'bus', 'car', 'cat', 'chair',
                            'cow', 'diningtable', 'dog', 'horse', 'motorbike',
                            'person', 'potted plant', 'sheep', 'sofa',
                            'train', 'tv/monitor'] 
        self.colormap2label = None 
        self.load_images() 
 
    def voc_label_indices(self, img): 
        if self.colormap2label is None: 
            self.colormap2label = nd.zeros(256**3) 
            for i, cm in enumerate(self.voc_colormap): 
                self.colormap2label[(cm[0] * 256 + cm[1]) * 256 + cm[2]] = i 
        data = img.astype('int32') 
        idx = (data[:,:,0] * 256 + data[:,:,1]) * 256 + data[:,:,2] 
        return self.colormap2label[idx] 
 
    def rand_crop(self, data, label, height, width): 
        data, rect = image.random_crop(data, (width, height)) 
        label = image.fixed_crop(label, *rect) 
        return data, label 
 
    def load_images(self): 
        voc_dir = _download_voc_pascal() 
        data, label = read_voc_images(root=voc_dir, train=self.train) 
        self.data = [self.normalize_image(im) for im in self.filter(data)] 
        self.label = self.filter(label) 
        print('Read '+str(len(self.data))+' examples') 
 
    def normalize_image(self, data): 
        return (data.astype('float32') / 255 - self.rgb_mean) / self.rgb_std 
 
    def filter(self, images): 
        return [im for im in images if ( 
            im.shape[0] >= self.crop_size[0] and 
            im.shape[1] >= self.crop_size[1])] 
 
    def __getitem__(self, idx): 
        data, label = self.rand_crop(self.data[idx], self.label[idx], 
                                *self.crop_size) 
        return data.transpose((2, 0, 1)), self.voc_label_indices(label) 
 
    def __len__(self): 
        return len(self.data)

