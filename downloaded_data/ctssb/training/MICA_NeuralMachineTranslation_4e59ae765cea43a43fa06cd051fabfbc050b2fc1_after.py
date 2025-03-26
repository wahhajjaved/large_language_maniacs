# -*- coding: utf-8 -*-

import unicodedata
from comet_ml import Experiment
import string
import re
import random
import time
import datetime
import math
import nltk
import torch
import torch.nn as nn
from torch.nn import functional
from torch.autograd import Variable
from torch import optim
import torch.nn.functional as F
from torch.nn.utils.rnn import pad_packed_sequence, pack_padded_sequence
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import io
import torchvision
from PIL import Image
import argparse
from collections import Counter

import os
import subprocess



######## File params ########
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--MIN_LENGTH', type=int, default=1, help='Min Length of sequence (Input side)')
    parser.add_argument('--MAX_LENGTH', type=int, default=200, help='Max Length of sequence (Input side)')
    parser.add_argument('--MIN_LENGTH_TARGET', type=int, default=1, help='Min Length of sequence (Output side)')
    parser.add_argument('--MAX_LENGTH_TARGET', type=int, default=200, help='Max Length of sequence (Output side)')
    parser.add_argument('--lang1', type=str, default="en", help='Input Language')
    parser.add_argument('--lang2', type=str, default="fr", help='Target Language')
    parser.add_argument('--USE_CUDA', action='store_true', help='IF USE CUDA (Default == False)')
    parser.add_argument('--attention', type=str, default='Bahdanau', help='attention type: either Bahdanau or Luong')
    # parser.add_argument('--teacher_forcing_ratio', type=float, default=1, help='Teacher forcing ratio for encoder')
    parser.add_argument('--hidden_size', type=int, default=1024, help='Size of hidden layer')
    parser.add_argument('--n_epochs', type=int, default=20, help='Number of single iterations through the data')
    parser.add_argument('--learning_rate', type=float, default=0.0001, help='Learning rate (for both, encoder and decoder)')
    parser.add_argument('--n_layers', type=int, default=2, help='Number of layers (for both, encoder and decoder)')
    parser.add_argument('--dropout', type=float, default=0.1, help='Dropout (%) in the decoder')
    parser.add_argument('--model_type', type=str, default="seq2seq", help='Model type (and ending of files)')
    parser.add_argument('--main_data_dir', type=str, default= "/scratch/eff254/NLP/Data/Model_ready", help='Directory where data is saved (in folders tain/dev/test)')
    parser.add_argument('--out_dir', type=str, default="checkpoints", help="Directory to save the models state dict (No default)")
    parser.add_argument('--eval_dir', type=str, default="/scratch/eff254/NLP/Evaluation/", help="Directory to save predictions - MUST CONTAIN PEARL SCRIPT")
    parser.add_argument('--optimizer', type=str, default="Adam", help="Optimizer (Adam vs SGD). Default: Adam")
    parser.add_argument('--kmax', type=int, default=10, help="Beam search Topk to search")
    parser.add_argument('--clip', type=int, default=1, help="Clipping the gradients")
    parser.add_argument('--batch_size', type=int, default=128, help="Size of a batch")
    parser.add_argument('--min_count_trim_output', type=int, default=2, help="trim infrequent output words")
    parser.add_argument('--min_count_trim_input', type=int, default=2, help="trim infrequent input words")
    parser.add_argument('--save_every', type=int, default=50, help='Checkpoint model after number of iters')
    parser.add_argument('--print_every', type=int, default=10, help='Print training loss after number of iters')
    parser.add_argument('--eval_every', type=int, default=10, help='Evaluate translation on one dev pair after number of iters')
    parser.add_argument('--bleu_every', type=int, default=100, help='Get bleu score number of iters')
    parser.add_argument('--scheduled_sampling_k', type=int, default=3000, help='scheduled sampling parameter for teacher forcing, \
        based on inverse sigmoid decay')
    parser.add_argument('--experiment', type=str, default="MICA", help='experiment name')

    opt = parser.parse_args()
    print(opt)

    if opt.experiment is None:
        opt.experiment = 'MICA_experiment'

    ######## Comet ML ########
    #experiment = comet_mirror("Experiment2")
    experiment = Experiment(api_key="00Z9vIf4wOLZ0yrqzdwHqttv4", log_code=True)
    hyper_params = vars(opt)
    experiment.log_multiple_params(hyper_params)


    # flag for character encoding
    target_char = (opt.model_type == 'bpe2char')
    return opt, target_char, experiment


opt, target_char , experiment = parse_args()
os.system('mkdir {0}/{1}'.format(opt.out_dir, opt.experiment))





###########################
#    1. Loss function     #
###########################

def sequence_mask(sequence_length, max_len=None):
    if max_len is None:
        max_len = sequence_length.data.max()
    batch_size = sequence_length.size(0)
    seq_range = torch.range(0, max_len - 1).long()
    seq_range_expand = seq_range.unsqueeze(0).expand(batch_size, max_len)
    seq_range_expand = Variable(seq_range_expand)
    if sequence_length.is_cuda:
        seq_range_expand = seq_range_expand.cuda()
    seq_length_expand = (sequence_length.unsqueeze(1)
                         .expand_as(seq_range_expand))
    return seq_range_expand < seq_length_expand


def masked_cross_entropy(logits, target, length):

    if opt.USE_CUDA:
        length = Variable(torch.LongTensor(length)).cuda()
    else:
        length = Variable(torch.LongTensor(length))

    logits_flat = logits.view(-1, logits.size(-1))
    log_probs_flat = functional.log_softmax(logits_flat)
    target_flat = target.view(-1, 1)
    losses_flat = -torch.gather(log_probs_flat, dim=1, index=target_flat)
    losses = losses_flat.view(*target.size())
    mask = sequence_mask(sequence_length=length, max_len=target.size(1))
    losses = losses * mask.float()
    loss = losses.sum() / length.float().sum()
    return loss


####################################
# 2. Languages classes and imports #
####################################
PAD_token = 0
SOS_token = 1
EOS_token = 2
UNK_token = 3

PAD_TOKEN = 0
SOS_TOKEN = BOS_TOKEN = 1
EOS_TOKEN = 2
UNK_TOKEN = 3


"""
class Lang:
    def __init__(self, name):
        self.name = name
        self.trimmed = False
        self.word2index = {}
        self.word2count = {}
        self.index2word = {0: "PAD", 1: "SOS", 2: "EOS", 3: "UNK"}
        self.n_words = 4 # Count default tokens

    def index_words(self, sentence):
        for word in sentence.split(' '):
            self.index_word(word)

    def index_word(self, word):
        if word not in self.word2index:
            self.word2index[word] = self.n_words
            self.word2count[word] = 1
            self.index2word[self.n_words] = word
            self.n_words += 1
        else:
            self.word2count[word] += 1

    # Remove words below a certain count threshold
    def trim(self, min_count):
        if self.trimmed: return
        self.trimmed = True

        keep_words = []

        for k, v in self.word2count.items():
            if v >= min_count:
                keep_words.append(k)

        print('keep_words %s / %s = %.4f' % (
            len(keep_words), len(self.word2index), len(keep_words) / len(self.word2index)
        ))

        # Reinitialize dictionaries
        self.word2index = {}
        self.word2count = {}
        self.index2word = {0: "PAD", 1: "SOS", 2: "EOS", 3: "UNK"}
        self.n_words = 3 # Count default tokens

        for word in keep_words:
            self.index_word(word)

def normalize_string(s):
    s = re.sub(r"([,.!?])", r" \1 ", s)
    s = re.sub(r"[^a-zA-Z,.!?]+", r" ", s)
    s = re.sub(r"\s+", r" ", s).strip()
    return s
"""

class Lang(object):
    
    def __init__(self, name):
        self.name = name
        self.trimmed = False
        self.__word2idx = {}
        self.index2word = {0: "PAD", 1: "SOS", 2: "EOS", 3:'<UNK>'}        
        self.n_words = 4 # Count default tokens       
        self.word2count = {}
        
    def index_words(self, sentence):
        for word in sentence.split(' '):
            self.index_word(word)

    def index_word(self, word):
        if word not in self.__word2idx:
            self.__word2idx[word] = self.n_words
            self.word2count[word] = 1
            self.index2word[self.n_words] = word
            self.n_words += 1
        else:
            self.word2count[word] += 1

    # Remove words below a certain count threshold
    def trim(self, min_count):
        if self.trimmed: return
        self.trimmed = True
        
        keep_words = []
        
        for k, v in self.word2count.items():
            if v >= min_count:
                keep_words.append(k)

        print('keep_words %s / %s = %.4f' % (
            len(keep_words), len(self.__word2idx), len(keep_words) / len(self.__word2idx)
        ))

        # Reinitialize dictionaries
        self.__word2idx = {}
        self.index2word = {0: "PAD", 1: "SOS", 2: "EOS", 3:'<UNK>'}
        self.n_words = 4 # Count default tokens

        for word in keep_words:
            self.index_word(word)

    def word2index(self, word):
        return self.__word2idx.get(word, UNK_TOKEN)


class Tokenizer(Lang):

    def __init__(self, max_length=500, vocab_file=None,
                 additional_tokens=None,
                 vocab_threshold=2):
        self.max_length = max_length
        self.vocab_threshold = vocab_threshold
        #self.special_tokens = [PAD_TOKEN, UNK_TOKEN, BOS_TOKEN, EOS_TOKEN]
        self.special_tokens = ['<PAD>', '<BOS>', '<EOS>', '<UNK>']
        if additional_tokens is not None:
            self.special_tokens += additional_tokens
        self.__word2idx = {}
        if os.path.isfile(vocab_file):
            self.load_vocab(vocab_file)
        self.n_words = 4
        self.trimmed = False
        self.index2word = {0: "PAD_TOKEN", 1: "SOS_TOKEN", 2: "EOS_TOKEN", 3:'<UNK>'}


    @property
    def vocab_size(self):
        return len(self.vocab) + len(self.special_tokens)

    def idx2word(self, idx):
        if idx < len(self.special_tokens):
            return self.special_tokens[idx]
        else:
            return self.vocab[idx - len(self.special_tokens)][0]

    def update_word2idx(self):
        self.__word2idx = {
            word[0]: idx + len(self.special_tokens) for idx, word in enumerate(self.vocab)}
        self.index2word = {
            idx + len(self.special_tokens): word[0] for idx, word in enumerate(self.vocab)}
        for i, tok in enumerate(self.special_tokens):
            self.__word2idx[tok] = i
            self.index2word[i]=tok
        self.n_words=self.vocab_size
        print(self.index2word)
    
    def word2index(self, word): 
        return self.__word2idx.get(word, UNK_TOKEN)
    
    def segment(self, line):
        """segments a line to tokenizable items"""
        return str(line).lower().translate(string.punctuation).strip().split()

    def get_vocab(self,  item_list, from_filenames=True, limit=None):
        vocab = Counter()
        if from_filenames:
            filenames = item_list
            # get combined vocabulary of all input files
            for fname in filenames:
                with codecs.open(fname, encoding='UTF-8') as f:
                    for line in f:
                        for word in self.segment(line):
                            vocab[word] += 1
        else:
            for line in item_list:
                for word in self.segment(line):
                    vocab[word] += 1
        self.vocab = vocab.most_common(limit)
        self.update_word2idx()

    def save_vocab(self, vocab_filename):
        if self.vocab is not None:
            with codecs.open(vocab_filename, 'w', encoding='UTF-8') as f:
                for (key, freq) in self.vocab:
                    f.write("{0} {1}\n".format(key, freq))

    def load_vocab(self, vocab_filename, limit=None):
        vocab = Counter()
        with codecs.open(vocab_filename, encoding='UTF-8') as f:
            for line in f:
                word, count = line.strip().split()
                vocab[word] = int(count)
        self.vocab = vocab.most_common(limit)
        self.update_word2idx()

    def tokenize(self, line, insert_start=None, insert_end=None):
        """tokenize a line, insert_start and insert_end are lists of tokens"""
        inputs = self.segment(line)
        targets = []
        if insert_start is not None:
            targets += insert_start
        for w in inputs:
            targets.append(self.word2idx(w))
        if insert_end is not None:
            targets += insert_end
        return torch.LongTensor(targets)

    def detokenize(self, inputs, delimiter=u' '):
        return delimiter.join([self.idx2word(idx) for idx in inputs]).encode('utf-8')

    # Remove words below a certain count threshold
    def trim(self, min_count):
        if self.trimmed: return
        self.trimmed = True

        keep_words = []

        no_words_kept = 0
        for (k,v) in self.vocab:
            if v >= min_count:
                keep_words.append([k]*v)
                no_words_kept += 1
        keep_words = [item for sublist in keep_words for item in sublist]
        print('keep_words %s / %s = %.4f' % (
            no_words_kept, len(self.vocab), no_words_kept / len(self.vocab)
        ))

        # Reinitialize dictionaries
        self.vocab = {}
        self.__word2idx = {}
        self.n_words = 3 # Count default tokens

        self.get_vocab(keep_words, from_filenames=False)

# adding section for character encoding on non-bpe base files
# Source: https://github.com/eladhoffer/seq2seq.pytorch/blob/master/seq2seq/tools/tokenizer.py
class CharTokenizer(Tokenizer):

    def segment(self, line):
        return list(line.strip())

    def detokenize(self, inputs, delimiter=u''):
        return super(CharTokenizer, self).detokenize(inputs, delimiter)
    
    
    
'''
def read_langs(lang1, lang2, set_type="train", normalize=False, path='.',
               term="txt", reverse=False, char_output=False):
    print("Reading lines...")
    # Read the file and split into lines
    # Attach the path here for the source and target language dataset
    if set_type == "train":
        filename = '%s/train/%s-%s.%s' % (path, lang1, lang2, term)
    elif set_type == "dev":
        filename = '%s/dev/%s-%s.%s' % (path, lang1, lang2, term)
    elif set_type == "valid":
        filename = '%s/dev/%s-%s.%s' % (path, lang1, lang2, term)
    elif set_type == "tst2010":
        filename = '%s/test/%s-%s.tst2010-%s' % (path, lang1, lang2, term)
    elif set_type == "tst2011":
        filename = '%s/test/%s-%s.tst2011-%s' % (path, lang1, lang2, term)
    elif set_type == "tst2012":
        filename = '%s/test/%s-%s.tst2012-%s' % (path, lang1, lang2, term)
    elif set_type == "tst2013":
        filename = '%s/test/%s-%s.tst2013-%s' % (path, lang1, lang2, term)
    elif set_type == "tst2014":
        filename = '%s/test/%s-%s.tst2014-%s' % (path, lang1, lang2, term)
    else:
        raise ValueError("set_type not found. Check data folder options")

    # lines contains the data in form of a list
    lines = open(filename).read().strip().split('\n')
    # Split every line into pairs
    if normalize == True:
        pairs = [[normalize_string(s) for s in l.split('\t')] for l in lines]
    else:
        pairs = [[s for s in l.split('\t')] for l in lines]
    # Reverse pairs, make Lang instances
    if reverse:
        pairs = [list(reversed(p)) for p in pairs]
        input_lang = Lang(lang2)
        output_lang = Lang(lang1)
    else:
        input_lang = Lang(lang1)
        if char_output:
            output_lang = CharTokenizer(vocab_file='')
        else:
            output_lang = Lang(lang2)

    return input_lang, output_lang, pairs
'''    
    

def read_langs(lang1, lang2, set_type="train", normalize=False, path='.',
               term="txt", reverse=False, char_output=False):
    print("Reading lines...")
    # Read the file and split into lines
    # Attach the path here for the source and target language dataset
    if set_type == "train":
        filename = '%s/train/%s-%s.%s' % (path, lang1, lang2, term)
    elif set_type == "dev":
        filename = '%s/dev/%s-%s.%s' % (path, lang1, lang2, term)
    elif set_type == "valid":
        filename = '%s/dev/%s-%s.%s' % (path, lang1, lang2, term)
    elif set_type == "tst2010":
        filename = '%s/test/%s-%s.tst2010-%s' % (path, lang1, lang2, term)
    elif set_type == "tst2011":
        filename = '%s/test/%s-%s.tst2011-%s' % (path, lang1, lang2, term)
    elif set_type == "tst2012":
        filename = '%s/test/%s-%s.tst2012-%s' % (path, lang1, lang2, term)
    elif set_type == "tst2013":
        filename = '%s/test/%s-%s.tst2013-%s' % (path, lang1, lang2, term)
    elif set_type == "tst2014":
        filename = '%s/test/%s-%s.tst2014-%s' % (path, lang1, lang2, term)
    else:
        raise ValueError("set_type not found. Check data folder options")

    # lines contains the data in form of a list
    lines = open(filename).read().strip().split('\n')
    # Split every line into pairs
    if normalize == True:
        pairs = [[normalize_string(s) for s in l.split('\t')] for l in lines]
    else:
        pairs = [[s for s in l.split('\t')] for l in lines]
    # Reverse pairs, make Lang instances
    if reverse:
        pairs = [list(reversed(p)) for p in pairs]
        input_lang = Lang(lang2)
        output_lang = Lang(lang1)
    else:
        input_lang = Lang(lang1)
        if char_output:
            output_lang = CharTokenizer(vocab_file='')
        else:
            output_lang = Lang(lang2)

    return input_lang, output_lang, pairs


"""
def filter_pairs(pairs, MIN_LENGTH, MAX_LENGTH):
    filtered_pairs = []
    for pair in pairs:
        if len(pair[0]) >= MIN_LENGTH and len(pair[0]) <= MAX_LENGTH \
            and len(pair[1]) >= MIN_LENGTH and len(pair[1]) <= MAX_LENGTH:
                filtered_pairs.append(pair)
    return filtered_pairs
"""
#MD
# Necessary peprocessing of data for modeling (details included in the Readme file)
def filterPair(p, min_length_input, min_length_target, max_length_input, max_length_target):
    return not (not (len(p[0].split(' ')) > min_length_input) or not (len(p[1].split(' ')) > min_length_target) or not (
        len(p[0].split(' ')) < max_length_input) or not (len(p[1].split(' ')) < max_length_target))


def filterPairs(pairs, min_length_input, min_length_target, max_length_input, max_length_target):
    return [pair for pair in pairs if filterPair(pair, min_length_input, min_length_target,
                                                 max_length_input, max_length_target)]
# end MD


"""
def prepare_data(lang1_name, lang2_name, reverse=False, set_type="train"):

    # Get the source and target language class objects and the pairs (x_t, y_t)

    input_lang, output_lang, pairs = read_langs(lang1_name, lang2_name, set_type=set_type, term=opt.model_type, reverse=reverse, normalize=False)
    print("Read %d sentence pairs" % len(pairs))

    ## 2. MIN LENGTH & MAX LENGTH ????
    pairs = filter_pairs(pairs, opt.MIN_LENGTH, opt.MAX_LENGTH)
    print("Filtered to %d pairs" % len(pairs))

    print("Indexing words...")
    for pair in pairs:
        input_lang.index_words(pair[0])
        output_lang.index_words(pair[1])

    print('Indexed %d words in input language, %d words in output' % (input_lang.n_words, output_lang.n_words))
    return input_lang, output_lang, pairs
"""
# MD edit
def prepare_data(lang1_name, lang2_name, min_length_input, max_length_input,
                 min_length_target, max_length_target, set_type='train', do_filter=True, normalize=False,
                 reverse=False, path='.', term=opt.model_type, char_output=False):

    # Get the source and target language class objects and the pairs (x_t, y_t)
    input_lang, output_lang, pairs = read_langs(lang1_name, 
                                                lang2_name, set_type=set_type,
                                                reverse=reverse,
                                                normalize=normalize,
                                                path=path, 
                                                term=term,
                                                char_output=char_output
                                               )
    print("Read %d sentence pairs" % len(pairs))

    if do_filter is True:
        pairs = filterPairs(pairs, min_length_input, min_length_target,
                            max_length_input, max_length_target)
        print("Filtered to %d pairs" % len(pairs))
    else:
        print("Pairs not filtered...")
    
    print("Indexing words...")
    if not char_output:
        for pair in pairs:
            input_lang.index_words(pair[0])
            output_lang.index_words(pair[1])
    else:
        for pair in pairs:
            input_lang.index_words(pair[0])
        output_lang.get_vocab(list(np.array(pairs)[:, 1]), from_filenames=False)
    print('Indexed %d words in input language, %d words in output' % (input_lang.n_words, output_lang.n_words))
    return input_lang, output_lang, pairs
# end MD edit


def indexes_from_sentence(lang, sentence):
    return [lang.word2index(word) for word in sentence.split(' ')]

# def indexes_from_sentence(lang, sentence):
#     try:
#         val = [lang.word2index[word] for word in sentence.split(' ')]
#     except KeyError:
#         # Do it individually. Means one word is not on dictionary:
#         val = []
#         for word in sentence.split(' '):
#             try:
#                 indexed = lang.word2index[word]
#                 val.append(indexed)
#             except KeyError:
#                 val.append(3)

#     return val + [EOS_token]


# Pad a with the PAD symbol
def pad_seq(seq, max_length):
    seq += [PAD_TOKEN for i in range(max_length - len(seq))]
    return seq


#def random_batch(batch_size):
def random_batch(USE_CUDA, batch_size, pairs, input_lang, output_lang, max_length_input, max_length_output, char_output=False):
    input_seqs = []
    target_seqs = []
    # Choose random pairs
    for i in range(batch_size):
        pair = random.choice(pairs)
        input_seqs.append(indexes_from_sentence(input_lang, pair[0]))
        target_seqs.append(indexes_from_sentence(output_lang, pair[1]))

    # Zip into pairs, sort by length (descending), unzip
    seq_pairs = sorted(zip(input_seqs, target_seqs), key=lambda p: len(p[0]), reverse=True)
    input_seqs, target_seqs = zip(*seq_pairs)

    # For input and target sequences, get array of lengths and pad with 0s to max length
    input_lengths = [len(s) for s in input_seqs]
    input_padded = [pad_seq(s, max(input_lengths)) for s in input_seqs]
    target_lengths = [len(s) for s in target_seqs]
    target_padded = [pad_seq(s, max(target_lengths)) for s in target_seqs]

    # Turn padded arrays into (batch_size x max_len) tensors, transpose into (max_len x batch_size)
    input_var = Variable(torch.LongTensor(input_padded)).transpose(0, 1)
    target_var = Variable(torch.LongTensor(target_padded)).transpose(0, 1)

    if opt.USE_CUDA:
        input_var = input_var.cuda()
        target_var = target_var.cuda()
    return input_var, input_lengths, target_var, target_lengths

# def random_batch(USE_CUDA, batch_size, pairs, input_lang, output_lang, max_length_input, max_length_output, char_output=False):
#     input_seqs = []
#     target_seqs = []
#     print("here")
#     # Choose random pairs
#     for i in range(batch_size):
#         pair = random.choice(pairs)
#         input_seqs.append(indexes_from_sentence(input_lang, pair[0]))
#         target_seqs.append(indexes_from_sentence(output_lang, pair[1]))

#     # Zip into pairs, sort by length (descending), unzip
#     seq_pairs = sorted(zip(input_seqs, target_seqs), key=lambda p: len(p[0]), reverse=True)
#     input_seqs, target_seqs = zip(*seq_pairs)
#     input_lengths = [len(s) for s in input_seqs]
#     input_padded = [pad_seq(s, max(input_lengths)) for s in input_seqs]
#     target_lengths = [len(s) for s in target_seqs]
#     target_padded = [pad_seq(s, max(target_lengths)) for s in target_seqs]

#     # Turn padded arrays into (batch_size x max_len) tensors, transpose into (max_len x batch_size)
#     input_var = Variable(torch.LongTensor(input_padded)).transpose(0, 1)
#     target_var = Variable(torch.LongTensor(target_padded)).transpose(0, 1)
    
#     if USE_CUDA:
#         input_var = input_var.cuda()
#         target_var = target_var.cuda()
        
#     return input_var, input_lengths, target_var, target_lengths


###################################
# 3. Main model encoder - decoder #
###################################

class EncoderRNN(nn.Module):
    def __init__(self, input_size, hidden_size, n_layers=1, dropout=0.1):
        super(EncoderRNN, self).__init__()

        self.input_size = input_size #no of words in the input Language
        self.hidden_size = hidden_size
        self.n_layers = n_layers
        self.dropout = dropout

        self.embedding = nn.Embedding(input_size, hidden_size)
        self.gru = nn.GRU(hidden_size, hidden_size, n_layers, dropout=self.dropout, bidirectional=True)
       
        self.init_weights()

    def forward(self, input_seqs, input_lengths, hidden=None): # hidden vector starts with zero (a guess!)

        # Note: we run this all at once (over multiple batches of multiple sequences)
        embedded = self.embedding(input_seqs) # size = (max_length, batch_size, embed_size). NOTE: embed_size = hidden size here
        packed = torch.nn.utils.rnn.pack_padded_sequence(embedded, input_lengths) # size = (max_length * batch_size, embed_size)

        outputs, hidden = self.gru(packed, hidden) # outputs are supposed to be probability distribution right?
        outputs, output_lengths = torch.nn.utils.rnn.pad_packed_sequence(outputs) # unpack (back to padded)
        outputs = outputs[:, :, :self.hidden_size] + outputs[:, : ,self.hidden_size:] # Sum bidirectional outputs
        return outputs, hidden

    def init_weights(self):
        
        initrange = 0.1
        init_vars = [self.embedding]
        
        for var in init_vars:
            var.weight.data.uniform_(-initrange, initrange)   

###################################
# 3. Main model encoder - decoder #
###################################

class EncoderRNN(nn.Module):
    def __init__(self, input_size, hidden_size, n_layers=1, dropout=0.1):
        super(EncoderRNN, self).__init__()

        self.input_size = input_size #no of words in the input Language
        self.hidden_size = hidden_size
        self.n_layers = n_layers
        self.dropout = dropout

        self.embedding = nn.Embedding(input_size, hidden_size)
        self.gru = nn.GRU(hidden_size, hidden_size, n_layers, dropout=self.dropout, bidirectional=True)
       
        self.init_weights()

    def forward(self, input_seqs, input_lengths, hidden=None): # hidden vector starts with zero (a guess!)

        # Note: we run this all at once (over multiple batches of multiple sequences)
        embedded = self.embedding(input_seqs) # size = (max_length, batch_size, embed_size). NOTE: embed_size = hidden size here
        packed = torch.nn.utils.rnn.pack_padded_sequence(embedded, input_lengths) # size = (max_length * batch_size, embed_size)

        outputs, hidden = self.gru(packed, hidden) # outputs are supposed to be probability distribution right?
        outputs, output_lengths = torch.nn.utils.rnn.pad_packed_sequence(outputs) # unpack (back to padded)
        outputs = outputs[:, :, :self.hidden_size] + outputs[:, : ,self.hidden_size:] # Sum bidirectional outputs
        return outputs, hidden

    def init_weights(self):
        
        initrange = 0.1
        init_vars = [self.embedding]
        
        for var in init_vars:
            var.weight.data.uniform_(-initrange, initrange)   

class Attn(nn.Module):
    def __init__(self, method, hidden_size):
        super(Attn, self).__init__()

        self.method = method
        self.hidden_size = hidden_size

        if self.method == 'general':
            self.attn = nn.Linear(self.hidden_size, hidden_size)
            self.init_weights()
        elif self.method == 'concat':
            self.attn = nn.Linear(self.hidden_size * 2, hidden_size)
            self.v = nn.Parameter(torch.FloatTensor(1, hidden_size))
            self.init_weights()

    def forward(self, hidden, encoder_outputs):
        max_len = encoder_outputs.size(0)
        this_batch_size = encoder_outputs.size(1)

        # Create variable to store attention energies
        attn_energies = Variable(torch.zeros(this_batch_size, max_len)) # B x S

        if opt.USE_CUDA:
            attn_energies = attn_energies.cuda()

        # For each batch of encoder outputs
        for b in range(this_batch_size):
            # Calculate energy for each encoder output
            for i in range(max_len): 
                attn_energies[b, i] = self.score(hidden[b,:], encoder_outputs[i, b])
                

        # Normalize energies to weights in range 0 to 1, resize to 1 x B x S
        return F.softmax(attn_energies).unsqueeze(1)

    def score(self, hidden, encoder_output):

        if self.method == 'dot':
            energy = hidden.squeeze(0).dot(encoder_output)
            return energy
        elif self.method == 'general':
            energy = self.attn(encoder_output)
            energy = hidden.dot(energy)
            return energy

        elif self.method == 'concat':
            energy = self.attn(torch.cat((hidden, encoder_output), 0))
            energy = (self.v.squeeze(0)).dot(energy)
            return energy

    def init_weights(self):
        
        initrange = 0.1
        init_vars = [self.attn]
        lin_layers = [self.attn]
        
        for var in init_vars:
            var.weight.data.uniform_(-initrange, initrange)
            if var in lin_layers:
                var.bias.data.fill_(0)    

###############################
#  BAHDANAU_ATTN_DECODER_RNN  #
###############################

class BahdanauAttnDecoderRNN(nn.Module):
    def __init__(self, hidden_size, output_size, n_layers=1, dropout_p=0.1):
        super(BahdanauAttnDecoderRNN, self).__init__()

        # Define parameters
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.n_layers = n_layers
        self.dropout_p = dropout_p
        ## 3. self.max_length = max_length
        ## self.max_length = opt.MAX_LENGTH

        # Define layers
        self.embedding = nn.Embedding(output_size, hidden_size)
        self.dropout = nn.Dropout(dropout_p)
        self.attn = Attn('concat', hidden_size)

        # Modifications made below in 2 lines
        self.gru = nn.GRU(2*hidden_size, hidden_size, n_layers, dropout=dropout_p)
        # self.out = nn.Linear(hidden_size * 2, output_size) # use of linear layer ?
        self.out = nn.Linear(hidden_size, output_size)

        self.init_weights()

    def forward(self, word_input, last_hidden, encoder_outputs):

        # Get the embedding of the current input word (last output word)
        word_embedded = self.embedding(word_input).view(1, word_input.data.shape[0], -1) # S=1 x B x N , ## N = hidden size (doubt)
        word_embedded = self.dropout(word_embedded)

        # Calculate attention weights and apply to encoder outputs
        attn_weights = self.attn(last_hidden[-1], encoder_outputs)
        context = attn_weights.bmm(encoder_outputs.transpose(0, 1)) # B x 1 x N
        context = context.transpose(0, 1) # 1 x B x N

        # Combine embedded input word and attended context, run through RNN
        rnn_input = torch.cat((word_embedded, context), 2) # 1 x B x 2N (There seems to be a mistake here)
        output, hidden = self.gru(rnn_input, last_hidden)

        # Final output layer
        output = output.squeeze(0) # B x N
        output = F.log_softmax(self.out(output))
        # output = F.log_softmax(self.out(torch.cat((output, context.squeeze(0)), 1)))
        # Return final output, hidden state, and attention weights (for visualization)
        return output, hidden, attn_weights

    def init_weights(self):
        
        initrange = 0.1
        init_vars = [self.embedding, self.out]
        lin_layers = [self.out]
        
        for var in init_vars:
            var.weight.data.uniform_(-initrange, initrange)
            if var in lin_layers:
                var.bias.data.fill_(0)



###############################
#  LuongAttnDecoderRNN  #
###############################
class LuongAttnDecoderRNN(nn.Module):
    def __init__(self, attn_model, hidden_size, output_size, n_layers=1, dropout=0.1):
        super(LuongAttnDecoderRNN, self).__init__()

        # Keep for reference
        self.attn_model = attn_model
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.n_layers = n_layers
        self.dropout = dropout

        # Define layers
        self.embedding = nn.Embedding(output_size, hidden_size)
        self.embedding_dropout = nn.Dropout(dropout)
        self.gru = nn.GRU(hidden_size, hidden_size, n_layers, dropout=dropout)
        self.concat = nn.Linear(hidden_size * 2, hidden_size)
        self.out = nn.Linear(hidden_size, output_size)
        
        # Choose attention model
        if attn_model != 'none':
            self.attn = Attn(attn_model, hidden_size)

    def forward(self, input_seq, last_hidden, encoder_outputs):
        # Note: we run this one step at a time

        # Get the embedding of the current input word (last output word)
        batch_size = input_seq.size(0)
        embedded = self.embedding(input_seq)
        embedded = self.embedding_dropout(embedded)
        embedded = embedded.view(1, batch_size, self.hidden_size) # S=1 x B x N

        # Get current hidden state from input word and last hidden state
        rnn_output, hidden = self.gru(embedded, last_hidden)

        # Calculate attention from current RNN state and all encoder outputs;
        # apply to encoder outputs to get weighted average 

        attn_weights = self.attn(rnn_output.transpose(0, 1), encoder_outputs) # B*1*S encoder_outputs: S*B*emb
        context = attn_weights.bmm(encoder_outputs.transpose(0, 1)).squeeze(1)
        # Attentional vector using the RNN hidden state and context vector
        # concatenated together (Luong eq. 5)        
        rnn_output = rnn_output.squeeze(0) # S=1 x B x N -> B x N
        # context = context.squeeze(1)       # B x S=1 x N -> B x N
        concat_input = torch.cat((rnn_output, context), 1)
        concat_output = F.tanh(self.concat(concat_input))

        # Finally predict next token (Luong eq. 6, without softmax)
        output = self.out(concat_output)

        # Return final output, hidden state, and attention weights (for visualization)
        return output, hidden, attn_weights
    
    def init_weights(self):
        
        initrange = 0.1
        init_vars = [self.embedding, self.out]
        lin_layers = [self.out]
        
        for var in init_vars:
            var.weight.data.uniform_(-initrange, initrange)
            if var in lin_layers:
                var.bias.data.fill_(0)

#################
# 4. Evaluation #
#################

def update_dictionary(target_sequence, topv, topi, key, dec_hidden, decoder_attns):
    if len(target_sequence) == 0:
        for i in range(len(topi)):
            target_sequence.update({str(topi[i]) : [topv[i], dec_hidden, decoder_attns] })
    else:
        prev_val = target_sequence[key][0]
        for i in range(len(topi)):
            target_sequence.update({key+"-"+str(topi[i]) : [topv[i]*prev_val, dec_hidden, decoder_attns] })
        del[target_sequence[key]]


def get_seq_through_beam_search(max_length, decoder, decoder_input, decoder_hidden, decoder_attentions, encoder_outputs, kmax ):

    target_sequence = dict()
    # Run through decoder
    for di in range(max_length):

        if di == 0:
            decoder_output, decoder_hidden, decoder_attention = decoder( decoder_input, decoder_hidden, encoder_outputs )
            topv, topi = decoder_output.data.topk(kmax)
            topv = np.exp(topv[0].cpu().numpy())
            topi = topi[0].cpu().numpy()
            decoder_attentions[di,:decoder_attention.size(2)] += decoder_attention.squeeze(0).squeeze(0).cpu().data
            update_dictionary(target_sequence, topv, topi, None, decoder_hidden, decoder_attentions)
        else:
            temp = target_sequence.copy()
            keys = list(temp.keys())
            for i in range(len(keys)):
                inp = int(keys[i].split("-")[-1] if len(keys[i]) > 1 else keys[i])
                if inp != EOS_token:
                    dec_input = Variable(torch.LongTensor([inp]))
                    dec_input = dec_input.cuda() if opt.USE_CUDA else dec_input
                    decoder_output, dec_hidden, decoder_attention = decoder( dec_input, temp[keys[i]][1], encoder_outputs )
                    topv, topi = decoder_output.data.topk(kmax)
                    topv = np.exp(topv[0].cpu().numpy())
                    topi = topi[0].cpu().numpy()
                    dec_attns = temp[keys[i]][2]
                    dec_attns[di,:decoder_attention.size(2)] += decoder_attention.squeeze(0).squeeze(0).cpu().data
                    update_dictionary(target_sequence, topv, topi, keys[i], dec_hidden, dec_attns)

        # Sort the target_Sequence dictionary and keep top k sequences only
        target_sequence = dict(sorted(target_sequence.items(), key=lambda x: x[1][0], reverse=True)[:kmax])

    # Get the sequence, decoder_attentions with maximum probability
    pair = sorted(target_sequence.items(), key=lambda x: x[1][0], reverse=True)[:1][0]
    seq = pair[0]
    decoder_attentions = pair[1][2]

    # Get the decoded words:
    decoded_words_indices = seq.split("-")
    decoded_words = [output_lang.index2word[int(i)] for i in decoded_words_indices]
    if int(decoded_words_indices[-1]) != EOS_token:
        decoded_words.append('<EOS>')

    return decoded_words, decoder_attentions

# Evaluation is mostly the same as training, but there are no targets. Instead we always feed the decoder's predictions back to itself.
# Every time it predicts a word, we add it to the output string. If it predicts the EOS token we stop there. We also store the decoder's attention outputs for each step to display later.

def evaluate(input_seq, max_length=opt.MAX_LENGTH):
    input_lengths = [len(input_seq)]
    input_seqs = [indexes_from_sentence(input_lang, input_seq)]
    input_batches = Variable(torch.LongTensor(input_seqs), volatile=True).transpose(0, 1)

    if opt.USE_CUDA:
        input_batches = input_batches.cuda()

    # Set to not-training mode to disable dropout
    encoder.train(False)
    decoder.train(False)

    # Run through encoder
    encoder_outputs, encoder_hidden = encoder(input_batches, input_lengths, None)

    # Create starting vectors for decoder
    decoder_input = Variable(torch.LongTensor([SOS_token]), volatile=True) # SOS
    decoder_hidden = encoder_hidden[:decoder.n_layers] # Use last (forward) hidden state from encoder

    if opt.USE_CUDA:
        decoder_input = decoder_input.cuda()

    # Store output words and attention states
    decoder_attentions = torch.zeros(max_length + 1, max_length + 1)
    decoded_words, decoder_attentions = get_seq_through_beam_search(max_length, decoder, decoder_input, decoder_hidden, decoder_attentions, encoder_outputs, opt.kmax )

    # Set back to training mode
    encoder.train(True)
    decoder.train(True)

    return decoded_words, decoder_attentions[:len(decoded_words)+1, :len(encoder_outputs)]


# We can evaluate random sentences from the training set and print out the input, target, and output to make some subjective quality judgements:
def evaluate_randomly():
    [input_sentence, target_sentence] = random.choice(pairs)
    evaluate_and_show_attention(input_sentence, target_sentence)

def evaluate_and_show_attention(input_sentence, target_sentence=None):
    output_words, attentions = evaluate(input_sentence)

    # Calculating the bleu score excluding the last word (<EOS>)
    #bleu_score = nltk.translate.bleu_score.sentence_bleu([target_sentence], ' '.join(output_words[:-1]))

    output_sentence = ' '.join(output_words)

    print('>', input_sentence)
    if target_sentence is not None:
        print('=', target_sentence)
    print('<', output_sentence)
    #print("BLUE SCORE IS:", bleu_score)

def eval_single(string):
    
    words, tensor = evaluate(string)
    words = ' '.join(words)
    words = re.sub('EOS', '', words)
    return(words)

def evaluate_list_pairs(list_strings):
    
    output = [eval_single(x[0]) for x in list_strings]
    
    return output

def export_as_list(original, translations): 
    
    with open(opt.eval_dir + '/original.txt', 'w') as original_file:
        for sentence in original:
            original_file.write(sentence + "\n")
    
    
    with open(opt.eval_dir + '/translations.txt', 'w') as translations_file:
        for sentence in translations:
            translations_file.write(sentence + "\n")
        
def run_perl(): 
    
    ''' Assumes the multi-bleu.perl is in opt.eval_dir
        Assumes you exported files with names in export_as_list()'''
    
    cmd = "%s %s < %s" % (opt.eval_dir + "./multi-bleu.perl", opt.eval_dir + 'original.txt', opt.eval_dir + 'translations.txt')
    bleu_output = subprocess.check_output(cmd, shell=True)
    m = re.search("BLEU = (.+?),", str(bleu_output))
    bleu_score = float(m.group(1))
    
    return bleu_score
    
def multi_blue_dev(dev_pairs):
    
    prediction = evaluate_list_pairs(dev_pairs)
    target_eval = [x[1] for x in dev_pairs]    
    export_as_list(target_eval, prediction)
    blue = run_perl()
    return blue

###############################
# 5. Training & training loop #
###############################

def as_minutes(s):
    m = math.floor(s / 60)
    s -= m * 60
    return '%dm %ds' % (m, s)

def time_since(since, percent):
    now = time.time()
    s = now - since
    es = s / (percent)
    rs = es - s
    return '%s (- %s)' % (as_minutes(s), as_minutes(rs))


def train(input_batches, input_lengths, target_batches, target_lengths, encoder, decoder, encoder_optimizer, decoder_optimizer, max_length=opt.MAX_LENGTH):

    # Added 2 lines below
    encoder.train(True)
    decoder.train(True)

    # Zero gradients of both optimizers
    encoder_optimizer.zero_grad()
    decoder_optimizer.zero_grad()
    loss = 0 # Added onto for each word

    # Run words through encoder
    encoder_outputs, encoder_hidden = encoder(input_batches, input_lengths, None)

    # Prepare input and output variables
    decoder_input = Variable(torch.LongTensor([SOS_token] * opt.batch_size))
    decoder_input = decoder_input.cuda() if opt.USE_CUDA else decoder_input
    decoder_hidden = encoder_hidden[:decoder.n_layers] # Use last (forward) hidden state from encoder
        
    max_target_length = max(target_lengths)
    all_decoder_outputs = Variable(torch.zeros(max_target_length, opt.batch_size, decoder.output_size))
    all_decoder_outputs = all_decoder_outputs.cuda() if opt.USE_CUDA else all_decoder_outputs

    # teacher forcing ratio implemented with inverse sigmoid decay
    # ref: https://arxiv.org/pdf/1506.03099.pdf
    teacher_forcing_ratio = opt.scheduled_sampling_k/(opt.scheduled_sampling_k+np.exp(epoch/opt.scheduled_sampling_k))

    use_teacher_forcing = True if random.random() < teacher_forcing_ratio else False

    # Run through decoder one time step at a time
    if use_teacher_forcing:
        for t in range(max_target_length):
            decoder_output, decoder_hidden, decoder_attn = decoder(
                decoder_input, decoder_hidden, encoder_outputs
            )

            all_decoder_outputs[t] = decoder_output
            decoder_input = target_batches[t] # Next input is current target

    else:
        for di in range(max_target_length):
            decoder_output, decoder_hidden, decoder_attn = decoder(
                decoder_input, decoder_hidden, encoder_outputs)
            topv, topi = decoder_output.data.topk(1)
            ni = topi[0][0]

            decoder_input = Variable(torch.LongTensor([ni]*opt.batch_size))
            decoder_input = decoder_input.cuda() if opt.USE_CUDA else decoder_input
            # record outputs for backprop
            all_decoder_outputs[di] = decoder_output
            if ni == EOS_token:
                break

            
    # Loss calculation and backpropagation
    loss = masked_cross_entropy(
        all_decoder_outputs.transpose(0, 1).contiguous(), # -> batch x seq
        target_batches.transpose(0, 1).contiguous(), # -> batch x seq
        target_lengths
    )
   
    loss.backward()
    # Clip gradient norms
    ec = torch.nn.utils.clip_grad_norm(encoder.parameters(), opt.clip)
    dc = torch.nn.utils.clip_grad_norm(decoder.parameters(), opt.clip)

    # Update parameters with optimizers
    encoder_optimizer.step()
    decoder_optimizer.step()

    return loss.data[0], ec, dc




######################
# 6. Data Processing #
######################

#input_lang, output_lang, pairs = prepare_data(opt.lang1, opt.lang2, False, set_type="train")
input_lang, output_lang, pairs = prepare_data(opt.lang1,
                                              opt.lang2,
                                              do_filter=True,
                                              min_length_input=opt.MIN_LENGTH, 
                                              max_length_input=opt.MAX_LENGTH,
                                              min_length_target=opt.MIN_LENGTH_TARGET,
                                              max_length_target=opt.MAX_LENGTH_TARGET, 
                                              normalize=False, 
                                              reverse=False, 
                                              path=opt.main_data_dir, 
                                              term=opt.model_type,
                                              char_output=target_char
                                             )


# TRIMMING DATA:

input_lang.trim(min_count=opt.min_count_trim_input)
output_lang.trim(min_count=opt.min_count_trim_output)


def trim_pairs(pairs, char=False):
    for i, pair in enumerate(pairs):
        pairs[i][1] = pairs[i][1].lower()

        for word in pair[0].split(' '):
            if word not in input_lang.word2count:
                pairs[i][0] = re.sub(word, '<UNK>', pair[0])
                
        if not char:
            for word in pair[1].split(' '):
                if word not in output_lang.word2count:
                    pairs[i][1] = re.sub(word, '<UNK>', pair[1]) 
                    break
        else:
            for word in list(pair[1]):
                if word not in dict(output_lang.vocab) and word != " ":
                    pairs[i][1] = re.sub(word, '<UNK>', pair[1])   

    print("Total number of sentence pairs: %d." %len(pairs))
    return pairs

pairs = trim_pairs(pairs, char=target_char)

input_lang_dev, output_lang_dev, pairs_dev = prepare_data(opt.lang1,
                                              opt.lang2,
                                              do_filter=True,
                                              min_length_input=opt.MIN_LENGTH, 
                                              max_length_input=opt.MAX_LENGTH,
                                              min_length_target=opt.MIN_LENGTH_TARGET,
                                              max_length_target=opt.MAX_LENGTH_TARGET, 
                                              normalize=False, 
                                              reverse=False, 
                                              path=opt.main_data_dir, 
                                              term=opt.model_type,
                                              char_output=target_char,
                                              set_type="valid")



####################
# 7. Configuration #
####################

# Configure models
# attn_model = 'dot'
# decoder_learning_ratio = 5.0
epoch = 0
print_every = opt.print_every
save_every = opt.save_every
evaluate_every = opt.eval_every # We check the validation in every 10,000 minibatches

# Initialize models
encoder = EncoderRNN(input_lang.n_words, opt.hidden_size, opt.n_layers, dropout=opt.dropout)

if opt.attention == 'Luong':
    decoder = LuongAttnDecoderRNN('dot', opt.hidden_size, output_lang.n_words, opt.n_layers, dropout=opt.dropout)
else:
    decoder = BahdanauAttnDecoderRNN( opt.hidden_size, output_lang.n_words, opt.n_layers, dropout_p=opt.dropout)
# Initialize optimizers and criterion
if opt.optimizer == "Adam":
    encoder_optimizer = optim.Adam(encoder.parameters(), lr=opt.learning_rate)
    #decoder_optimizer = optim.Adam(decoder.parameters(), lr=learning_rate * decoder_learning_ratio)
    decoder_optimizer = optim.Adam(decoder.parameters(), lr=opt.learning_rate)
elif opt.optimizer == "SGD":
    encoder_optimizer = optim.SGD(encoder.parameters(), lr=opt.learning_rate)
    #decoder_optimizer = optim.Adam(decoder.parameters(), lr=learning_rate * decoder_learning_ratio)
    decoder_optimizer = optim.SGD(decoder.parameters(), lr=opt.learning_rate)
else:
    raise ValueError('Optimizer options not found: Select SGD or Adam')
criterion = nn.CrossEntropyLoss()

# Move models to GPU
if opt.USE_CUDA:
    encoder.cuda()
    decoder.cuda()
# Keep track of time elapsed and running averages
start = time.time()
print_loss_total = 0 # Reset every print_every


###############
# 8. Modeling #
###############

eca = 0
dca = 0

while epoch < opt.n_epochs:
    epoch += 1

    # Get training data for this cycle
    input_batches, input_lengths, target_batches, target_lengths = random_batch(opt.USE_CUDA, 
                         opt.batch_size, 
                         pairs, 
                         input_lang, 
                         output_lang, 
                         opt.MAX_LENGTH, 
                         opt.MAX_LENGTH_TARGET, 
                         char_output=target_char)
    # Run the train function
    loss, ec, dc = train(
        input_batches, input_lengths, target_batches, target_lengths,
        encoder, decoder,
        encoder_optimizer, decoder_optimizer)
    # Keep track of loss
    print_loss_total += loss
    eca += ec
    dca += dc

    
    if (epoch+1) % evaluate_every == 0:
        evaluate_randomly()

    if (epoch+1) % save_every == 0:
        torch.save(encoder.state_dict(), "{}/saved_encoder_{}.pth".format(opt.out_dir, epoch))
        torch.save(decoder.state_dict(), "{}/saved_decoder_{}.pth".format(opt.out_dir, epoch))
        
    if (epoch+1) % opt.bleu_every == 0:
        blue_score = multi_blue_dev(pairs_dev)
        print("Bleu score at {} iteration = {}".format(epoch, blue_score))
        experiment.log_metric("Bleu score", blue_score)
    eca = 0
    dca = 0

torch.save(encoder.state_dict(), "{}/saved_encoder_{}.pth".format(opt.out_dir, epoch))
torch.save(decoder.state_dict(), "{}/saved_decoder_{}.pth".format(opt.out_dir, epoch))   
        
