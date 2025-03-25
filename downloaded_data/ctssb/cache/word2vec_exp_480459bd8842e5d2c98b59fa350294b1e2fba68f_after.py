'''
Created on Oct 17, 2015

@author: jordan
'''
from __future__ import division
import os
import re
from itertools import product, islice
import nltk
import datetime
from multiprocessing import Pool
import argparse
from string import lower


def clean_name(name):
    return '.'.join(os.path.splitext(os.path.basename(name))[:-1])

def to_section_name(name):
    return re.sub(r'_', r'-', os.path.basename(name).split('.')[0])
    
def multiply_file(fname):
    with open(fname) as fn:
        lines = fn.readlines()
    new_lines = []
    new_lines.append(': ' + to_section_name(fname) + '\n')
    for mult_line in product(lines, repeat=2):
        if mult_line[0] == mult_line[1]:
            continue
        new_lines.append(" ".join([line.strip() for line in mult_line]) + '\n')
    new_fname = os.path.join('res', 'mult', os.path.basename(fname))
    with open(new_fname, 'w') as fn:
        fn.writelines(new_lines)

def pos_file(fname, out_fname=None, overwrite=False, pos=None):
    if not out_fname:
        out_fname = fname+'.pos' 
    if os.path.exists(out_fname) and not overwrite:
        return
    with open(fname) as f_:
        lines = f_.readlines()
        print(len(lines))
        tok_lines = [nltk.word_tokenize(sent.decode('utf-8', 'replace')) for sent in lines]
        print(datetime.datetime.now())
        new_lines = []
        for tok_line in tok_lines:
            if (tok_lines.index(tok_line))%1000 == 0:
                print(datetime.datetime.now())
                print(tok_lines.index(tok_line))
            if pos:
                new_lines.append(' '.join(['_'.join([w,p]) for w,p in zip(tok_line, pos)]) + '\n')
            else:
                pos_line = nltk.pos_tag(tok_line)
                new_lines.append(' '.join(['_'.join([w,p]) for w,p in pos_line]) + '\n')
    with open(out_fname,'w') as f:
        f.writelines([line.encode('utf-8') for line in new_lines])

def remove_pos(word):
    return word.split('_')[0]


def join_files(fnames, target_fname):
    with open(target_fname, 'w') as f:
        pass
    with open(target_fname, 'a') as f:
        for fname in fnames:
            print(fname)
            with open(fname) as f_:
                f.write(f_.read()) 

def to_text(fpath, pos=False, max_lines=None):
    with open(fpath) as fp:
        data = list(islice(fp, max_lines))
    sentences = []
    sentence = []
    percentage = 0
    for i,line in enumerate(data):
        if 100*i/len(data) > percentage:
            print(percentage)
            percentage += 1
        if len(line.split()) < 2+3*pos:
            sentences.append(sentence)
            sentence = []
        else:
            word = line.split()[1]
            if pos:
                word += '_'+line.split()[4] 
            sentence.append(unicode(word))
    with open(fpath + '.txt' +'.pos'*pos, 'w') as fp:
        fp.writelines([' '.join(sentence).lower()+'\n' for sentence in sentences])

def encode_heb(fpath):
    with open(fpath) as fp1:
        data = fp1.read()
    data = unicode(data, 'utf-8', 'escape')
    with open(os.path.join('res', 'heb_code')) as fp2:
        heb_code = fp2.readlines()
    heb_code = [unicode(line, 'utf-8', 'escape') for line in heb_code]
    heb_code = {line.split()[0]: line.split()[1] for line in heb_code}
    data = ''.join([heb_code[c] if c in heb_code else c for c in data])
    with open(fpath+'.enc', 'w') as fp:
        fp.write(data.lower().encode('utf8'))

def build_news_corpus(name, max_news, n_proc, target_fpath):
    fnames = ['news.en-{:05}-of-00100'.format(i+1) for i in range(max_news)]
    fpaths = [os.path.join('res', 'training-monolingual.tokenized.shuffled', fname) for fname in fnames]
    if name.endswith('pos'):
        p = Pool(n_proc)
        p.map(pos_file, [fpath for fpath in fpaths if not os.path.exists(fpath+'.pos')])
#                 [pos_file(fpath) for fpath in fpaths if not os.path.exists(fpath+'.pos')]
        fpaths = [fpath+'.pos' for fpath in fpaths]
    join_files(fpaths, target_fpath)
    with open(target_fpath) as fp:
        s = fp.read().lower()
    with open(target_fpath, 'w') as fp:
        fp.write(s)

def main():
    
    parser = argparse.ArgumentParser()
    parser.add_argument("-eh", "--encode_heb", help="encode hebrew", default=None)
    parser.add_argument("-mf", "--multiply_file", help="questions name", default=None)
    parser.add_argument("-pos", "--part_of_speech", help="part of speech list", nargs='+', default=None)
    parser.add_argument("-tt", "--to_text", help="to text", default=None)
    args = parser.parse_args()

    
#     fname = 'ambiguous_verbs_mixed'
#     fname = 'ambiguous_verbs_heb.enc'
#     fname = 'ambiguous_verbs'
#     fname = 'ambiguous_nouns'
#     fpath = os.path.join('res', 'words', fname)

    if args.encode_heb:
        encode_heb(args.encode_heb)

    if args.multiply_file:
#         pos = ['NN', 'NNS']
        pos = args.part_of_speech
        if pos:
            pos = map(lower, pos)
        pos_file(args.multiply_file, overwrite=True, pos=pos)
        multiply_file(args.multiply_file)
        multiply_file(args.multiply_file+'.pos')


    if args.to_text:
#         fpath = os.path.join('res', 'model', 'wikipedia.deps')
        fpath = args.to_text
        to_text(fpath, max_lines=100)
        to_text(fpath, pos=True, max_lines=100)

if __name__ == '__main__':
    main()