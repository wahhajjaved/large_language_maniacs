import os
import sys

sys.path.append('utils')
sys.path.append('model')

import tensorflow as tf
import numpy as np
import pandas as pd
import json
import hickle
from utils import *
from collections import Counter
import vgg19
from scipy import ndimage
from tqdm import tqdm

def preprocess_data(caption_file, image_dir, max_length):
    with open(caption_file) as f:
        caption_data = json.load(f)

    ''' id2filename
    type: dict
    keys: image_id
    values: image_file_name
    '''
    id2filename = { image['id']: image['file_name'] for image in caption_data['images'] }

    ''' data
    type: list of dict
    [ { captions: caption, file_name: filename, image_id: image_id  } ]
    '''
    data = []
    for annotation in caption_data['annotations']:
        image_id = annotation['image_id']
        annotation['file_name'] = os.path.join(image_dir, id2filename[image_id])
        data.append(annotation)

    caption_data = pd.DataFrame.from_dict(data)
    del caption_data['id']
    caption_data.sort_values(by='image_id', inplace=True)
    caption_data = caption_data.reset_index(drop=True)

    # delete captions if word length > max_length
    del_idx = []
    for i, caption in enumerate(caption_data['caption']):
        caption = caption.replace('.','').replace(',','').replace("'","").replace('"','')
        caption = caption.replace('&','and').replace('(','').replace(")","").replace('-',' ')
        caption = ' '.join(caption.split())  # replace multiple spaces

        caption_data.set_value(i, 'caption', caption.lower())
        if len(caption.split()) > max_length:
            del_idx.append(i)

    # delete captions if size is larger than max_length
    print('The number of captions before deletion: %d' % len(caption_data))
    caption_data = caption_data.drop(caption_data.index[del_idx])
    caption_data = caption_data.reset_index(drop=True)
    print('The number of captions after deletion: %d' % len(caption_data))

    return caption_data

def build_vocab(annotations, threshold=1):
    counter = Counter()

    for i, caption in enumerate(annotations['caption']):
        for w in caption.split():
            counter[w] += 1

    vocab = [ word for word in counter if counter[word] >= threshold ]
    print ('Filtered %d words to %d words with word count threshold %d.' % (len(counter), len(vocab), threshold))

    word2idx = {u'<PAD>': 0, u'<BEG>': 1, u'<END>': 2}
    idx = 3
    for word in vocab:
        word2idx[word] = idx
        idx += 1

    return word2idx

def build_caption_vector(annotations, word2idx, max_length=15):
    n = len(annotations)
    # max_length + 2 for <BEG>, <END>
    captions = np.ndarray((n, max_length+2)).astype(np.int32)

    for i, caption in enumerate(annotations['caption']):
        words = caption.split()
        cap_vec = [ word2idx[word] for word in words if word in word2idx ]
        cap_vec = [word2idx['<BEG>']] + cap_vec + [word2idx['<END>']]

        # Zero padding
        for j in range(len(cap_vec), max_length + 2):
            cap_vec.append(word2idx['<PAD>'])

        captions[i, :] = np.asarray(cap_vec)

    return captions

def build_file_names(annotations):
    image_filenames = []
    id2idx = {}
    idx = 0
    image_ids = annotations['image_id']
    file_names = annotations['file_name']
    for image_id, file_name in zip(image_ids, file_names):
        if not image_id in id2idx:
            id2idx[image_id] = idx
            image_filenames.append(file_name)
            idx += 1

    file_names = np.asarray(image_filenames)
    return file_names, id2idx

def build_image_idxs(annotations, id2idx):
    image_idxs = np.ndarray(len(annotations), dtype=np.int32)
    image_ids = annotations['image_id']
    for i, image_id in enumerate(image_ids):
        image_idxs[i] = id2idx[image_id]
    return image_idxs

def main():
    # maximum length of caption(number of word).
    max_length = 15
    # if word occurs less than word_count_threshold in training dataset, the word index is special unknown token.
    word_count_threshold = 1

    # preprocess train data
    training_data = preprocess_data(caption_file='./dataset/annotations/captions_train2014.json',
                                    image_dir='./dataset/train2014_resized',
                                    max_length=max_length)

    # preprocess val data
    val_data = preprocess_data(caption_file='./dataset/annotations/captions_val2014.json',
                               image_dir='./dataset/val2014_resized',
                               max_length=max_length)

    save_pickle(training_data, './dataset/train_annotations.pkl')
    save_pickle(val_data, './dataset/val_annotations.pkl')

    for split in ['train', 'val']:
        annotations = load_pickle('./dataset/%s_annotations.pkl' % split)

        # Build Vocabulary
        if split == 'train':
            word2idx = build_vocab(annotations=annotations, threshold=word_count_threshold)
            save_pickle(word2idx, './dataset/vocab.pkl')

        captions = build_caption_vector(annotations=annotations, word2idx=word2idx, max_length=max_length)
        save_pickle(captions, './dataset/%s_captions.pkl' % split)

        file_names, id2idx = build_file_names(annotations)
        save_pickle(file_names, './dataset/%s_filenames.pkl' % split)

        image_idxs = build_image_idxs(annotations, id2idx)
        save_pickle(image_idxs, './dataset/%s_imageIdxs.pkl' % split)

    # extract conv5_3 feature vectors
    BATCH_SIZE = 128
    images = tf.placeholder(tf.float32, [None, 224, 224, 3])
    train_mode = tf.placeholder(tf.bool)

    # Load model
    vgg = vgg19.Vgg19()
    vgg.build(images, train_mode)
    with tf.Session() as sess:
        sess.run(tf.global_variables_initializer())
        for split in ['train', 'val']:
            anno_path = './dataset/%s_annotations.pkl' % split
            feature_path = './dataset/%s_features.hkl' % split
            annotations = load_pickle(anno_path)
            image_path = list(annotations['file_name'].unique())
            n = len(image_path)

            features = np.ndarray([n, 14*14, 512], dtype=np.float32)

            pbar = tqdm(total=n // BATCH_SIZE)
            for start, end in zip(range(0, n, BATCH_SIZE), range(BATCH_SIZE, n + BATCH_SIZE, BATCH_SIZE)):
                batch_file = image_path[start:end]
                image_batch = np.array([ ndimage.imread(x, mode='RGB') for x in batch_file ]).astype(np.float32)
                feats = sess.run(vgg.feats, feed_dict={images: image_batch, train_mode: False})
                features[start:end, :] = feats
                pbar.update(1)

            hickle.dump(feats, feature_path)

if __name__ == '__main__':
    main()
