from __future__ import division
from nltk.corpus import brown
# import word2vec
import logging
import os
from multiprocessing import Pool
from six import iteritems, itervalues
from numpy.core.fromnumeric import argsort
from utils import clean_name, pos_file, join_files, encode_heb, to_text,\
    multiply_file, to_section_name, remove_pos, build_news_corpus, build_corpus,\
    file_to_lower
import argparse
from nltk.stem.lancaster import LancasterStemmer
from nltk.stem.snowball import SnowballStemmer
import datetime
from gensim.models import word2vec
import re

class W2V:
    def __init__(self, fname='news.bin', n_proc=4, window=5):
        logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', 
                            level=logging.INFO)
        
        self.fname = fname
        fpath = os.path.join('res', 'model', fname)
        if not os.path.exists(fpath):
            self.create_model(fname, n_proc=n_proc, window=window)
        self.model = self.get_model(fpath)
    
    def get_model(self, fpath):
        return word2vec.Word2Vec.load_word2vec_format(fpath, binary=fpath.endswith('.bin'))
        
    def create_model(self, fname, max_news=99, n_proc=1, window=5, splits=100):
        name = clean_name(fname)
        model = word2vec.Word2Vec(window=window, workers=n_proc)
        if name == 'text8':
            sentences = word2vec.Text8Corpus(os.path.join('res', 'model', 'text8'))
            model.train(sentences)
        elif name == 'brown':
        #     sentences = word2vec.BrownCorpus(fpath)
            sentences = brown.sents()
            model.train(sentences)
        elif name.startswith('news'):
            target_fpath = os.path.join('res', 'model', name+'.txt')
            if not os.path.exists(target_fpath):
                build_news_corpus(name, max_news, n_proc, target_fpath)
            sentences = word2vec.LineSentence(target_fpath)
            model.build_vocab(sentences)
            model.train(sentences)
#         elif name.startswith('wikipedia.deps'):
#             target_fpath = os.path.join('res', 'model', name+'.txt')
#             if not os.path.exists(target_fpath):
#                 build_wikipedia_corpus(name, max_news, n_proc, target_fpath)
        elif name.startswith('spanishEtiquetado'):
            target_fpath = os.path.join('res', 'model', name+'.txt')
            if not os.path.exists(target_fpath):
                path = os.path.join('res', 'model', 'spanishEtiquetado')
                max_pos_len = re.search('\d$', name)
                if max_pos_len:
                    max_pos_len = max_pos_len.group(0)
                build_corpus(path, name.endswith('pos'), target_fpath, max_pos_len)
            sentences = word2vec.LineSentence(target_fpath)
#             with open(target_fpath) as fp:
#                 sentences = fp.readlines()
            model.build_vocab(sentences)
            model.train(sentences)        
        else:
            target_fpath = os.path.join('res', 'model', name+'.txt')
            file_to_lower(target_fpath)
            sentences = word2vec.LineSentence(target_fpath)
            model.build_vocab(sentences)
            model.train(sentences)
#             n_sents = len(sentences)  
#             print(n_sents)
#             if splits == 0:
#                 splits = 1
#             split_size = int(n_sents/splits)
#             for i in range(splits):
#                 print(str(i) + '\r')
#                 split_sentences = sentences[i*split_size:(i+1)*split_size-1]
#                 model.save_word2vec_format(os.path.join('res', 'model', fname), binary=fname.endswith('.bin'))
#                 model.save()  
                         
    #     model.save(os.path.join('res',name+'.model'))
        model.save_word2vec_format(os.path.join('res', 'model', fname), binary=fname.endswith('.bin'))

    def get_similarity(self, word1, word2):
        return(self.model.similarity(word1,word2))

    def get_prediction(self, a,b,c, ok_index, restrict_vocab=30000):
        ok_vocab = dict(sorted(iteritems(self.model.vocab), 
                               key=lambda item: -item[1].count)
                        [:restrict_vocab])
        ok_index = set(v.index for v in itervalues(ok_vocab))

        ignore = set(self.model.vocab[v].index for v in [a, b, c])  # indexes of words to ignore
        positive = [b, c]
        negative = [a]
        for index in argsort(self.model.most_similar(self.model, 
                                                     positive, 
                                                     negative, 
                                                     False))[::-1]:
            if index in ok_index and index not in ignore:
                predicted = self.model.index2word[index]
                break
        return predicted

    def evaluate_model(self, 
                       questions_fpath=os.path.join('res', 'model',
                                                    'questions-words.txt')):
        if clean_name(self.fname).endswith('pos'):
            pos_file(questions_fpath)
            questions_fpath = questions_fpath+'.pos' 
        return self.model.accuracy(questions_fpath)
    
def get_section(model_eval, name):
    for sec in model_eval:
        if sec['section'] == name:
            return sec
    print('not found')
    return None

def process_missing(missing, sec):
    st = SnowballStemmer('english')
    morphological_errors = 0
    for m in missing:
        ind = sec['incorrect'].index(m)
        prediction = sec['predicted'][ind]
        if(st.stem(m[3]) == st.stem(prediction[0])):
            morphological_errors += 1        
        print('the correct sequence is: '+str(m)+' but predicted: '+str(prediction))
    print('morphological errors:' + str(morphological_errors))
    if len(missing):
        print('percentage:' + str(morphological_errors/len(missing)))

def compare_section(eval1, eval2, section_name):
    sec1 = get_section(eval1, section_name)
    sec2 = get_section(eval2, section_name)
    sec1 =  {k: [tuple(remove_pos(w) for w in c) for c in v] for k,v in sec1.items()} 
    sec2 =  {k: [tuple(remove_pos(w) for w in c) for c in v] for k,v in sec2.items()} 
    correct1 = [c for c in sec1['correct'] if c not in sec2['OOV']]
    correct2 = [c for c in sec2['correct'] if c not in sec1['OOV']]
    missing1 = [c for c in correct2 if c not in correct1]
    missing2 = [c for c in correct1 if c not in correct2]

    print('missing1')
    process_missing(missing1, sec1)
    print('missing2')
    process_missing(missing2, sec2)
        
    return(missing1, missing2)


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("-mn", "--model_name", help="model name", default='spanishEtiquetado.bin')
    parser.add_argument("-qn", "--questions_name", help="questions name", default='ambiguous_verbs.sp')
    parser.add_argument("-w", "--window", help="model window size", type=int, default=5)
    parser.add_argument("-n", "--n_proc", help="number of processes", type=int, default=4)
    args = parser.parse_args()
    
    word2vec.logger.setLevel(logging.DEBUG)
    
    w2v = W2V(args.model_name,n_proc=args.n_proc, window=args.window)
    pos_name = clean_name(args.model_name) +'.pos' + '.bin'
    w2v_pos = W2V(pos_name,n_proc=args.n_proc, window=args.window)

#     print(len(word2vec_exp.model.vocab))
#     print(word2vec_exp.model.vocab.items()[:10])
#     print(word2vec_exp.model.similarity('add_VB','remove_VB'))
#     print(len(model.vocab.keys()))    

    questions_fpath = os.path.join('res', 'mult', args.questions_name)
    print(datetime.datetime.now())
    eval1 = w2v.evaluate_model(questions_fpath)
    print(datetime.datetime.now())
    eval2 = w2v_pos.evaluate_model(questions_fpath)
    print(datetime.datetime.now())
    missing1, missing2 = compare_section(eval1, eval2, to_section_name(args.questions_name))


if __name__ == '__main__':
    main()