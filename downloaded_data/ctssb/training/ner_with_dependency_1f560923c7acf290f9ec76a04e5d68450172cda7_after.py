import numpy as np
import torch
from typing import List
from common.instance import Instance


START = "<START>"
STOP = "<STOP>"
PAD = "<PAD>"
ROOT = "<ROOT>"


def log_sum_exp_pytorch(vec):
    """

    :param vec: [batchSize * from_label * to_label]
    :return: [batchSize * to_label]
    """
    maxScores, idx = torch.max(vec, 1)
    maxScores[maxScores == -float("Inf")] = 0
    maxScoresExpanded = maxScores.view(vec.shape[0] ,1 , vec.shape[2]).expand(vec.shape[0], vec.shape[1], vec.shape[2])
    return maxScores + torch.log(torch.sum(torch.exp(vec - maxScoresExpanded), 1))



def simple_batching(config, insts: List[Instance]):
    from config.config import DepMethod
    """

    :param config:
    :param insts:
    :return:
        word_seq_tensor,
        word_seq_len,
        char_seq_tensor,
        char_seq_len,
        label_seq_tensor
    """
    batch_size = len(insts)
    batch_data = sorted(insts, key=lambda inst: len(inst.input.words), reverse=True)
    word_seq_len = torch.LongTensor(list(map(lambda inst: len(inst.input.words), batch_data)))
    max_seq_len = word_seq_len.max()
    ### TODO: the 1 here might be used later?? We will make this as padding, because later we have to do a deduction.
    #### Use 1 here because the CharBiLSTM accepts
    char_seq_len = torch.LongTensor([list(map(len, inst.input.words)) + [1] * (int(max_seq_len) - len(inst.input.words)) for inst in batch_data])
    max_char_seq_len = char_seq_len.max()

    word_seq_tensor = torch.zeros((batch_size, max_seq_len), dtype=torch.long)
    label_seq_tensor =  torch.zeros((batch_size, max_seq_len), dtype=torch.long)
    char_seq_tensor = torch.zeros((batch_size, max_seq_len, max_char_seq_len), dtype=torch.long)
    adjs = None
    dep_label_tensor = None
    batch_dep_heads = None
    trees = None
    if config.dep_method != DepMethod.none:
        adjs = [ head_to_adj(max_seq_len, inst, config) for inst in batch_data]
        adjs = np.stack(adjs, axis=0)
        adjs = torch.from_numpy(adjs)
        batch_dep_heads = torch.zeros((batch_size, max_seq_len), dtype=torch.long)
        dep_label_tensor = torch.zeros((batch_size, max_seq_len), dtype=torch.long)
        trees = [inst.tree for inst in batch_data]
    for idx in range(batch_size):
        word_seq_tensor[idx, :word_seq_len[idx]] = torch.LongTensor(batch_data[idx].word_ids)
        label_seq_tensor[idx, :word_seq_len[idx]] = torch.LongTensor(batch_data[idx].output_ids)
        if config.dep_method != DepMethod.none:
            batch_dep_heads[idx, :word_seq_len[idx]] = torch.LongTensor(batch_data[idx].dep_head_ids)
            dep_label_tensor[idx, :word_seq_len[idx]] = torch.LongTensor(batch_data[idx].dep_label_ids)
        for word_idx in range(word_seq_len[idx]):
            char_seq_tensor[idx, word_idx, :char_seq_len[idx, word_idx]] = torch.LongTensor(batch_data[idx].char_ids[word_idx])
        for wordIdx in range(word_seq_len[idx], max_seq_len):
            char_seq_tensor[idx, wordIdx, 0: 1] = torch.LongTensor([config.char2idx[PAD]])   ###because line 119 makes it 1, every single character should have a id. but actually 0 is enough

    word_seq_tensor = word_seq_tensor.to(config.device)
    label_seq_tensor = label_seq_tensor.to(config.device)
    char_seq_tensor = char_seq_tensor.to(config.device)
    word_seq_len = word_seq_len.to(config.device)
    char_seq_len = char_seq_len.to(config.device)
    if config.dep_method != DepMethod.none:
        adjs = adjs.to(config.device)
        batch_dep_heads = batch_dep_heads.to(config.device)
        dep_label_tensor = dep_label_tensor.to(config.device)

    return word_seq_tensor, word_seq_len, char_seq_tensor, char_seq_len, adjs, batch_dep_heads, trees, label_seq_tensor, dep_label_tensor



def lr_decay(config, optimizer, epoch):
    lr = config.learning_rate / (1 + config.lr_decay * (epoch - 1))
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr
    print('learning rate is set to: ', lr)
    return optimizer



def head_to_adj(max_len, inst, config, directed=False, self_loop=False):
    """
    Convert a tree object to an (numpy) adjacency matrix.
    """
    directed = config.adj_directed
    self_loop = config.adj_self_loop
    ret = np.zeros((max_len, max_len), dtype=np.float32)

    for i, head in enumerate(inst.input.heads):
        if head == -1:
            continue
        ret[head, i] = 1

    if not directed:
        ret = ret + ret.T

    if self_loop:
        for i in range(len(inst.input.words)):
            ret[i, i] = 1

    return ret
