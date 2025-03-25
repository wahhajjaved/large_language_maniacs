'''
이 코드는 ScatterLab과의 협업을 통하여 만들어졌습니다. 
Author: 
  lovit, https://github.com/lovit
Co-author:
  sunggu, https://github.com/new21cccc
  Emily Yunha Shin, https://github.com/eyshin05
'''

from collections import defaultdict
import json
import sys

import numpy as np
import pprint


class RuleDict:

    def __init__(self, min_rule_length, max_rule_length, fname):
        
        self.rule_dict = {}
        if isinstance(fname, list):
            for f in fname:
                self.rule_dict.update(self.load_file(f))
        else:
            self.rule_dict.update(self.load_file(fname))
        self.min_rule_length = min_rule_length
        self.max_rule_length = max_rule_length
    
    
    def load_file(self, fname):
        
        def str_to_tuple(s):
            return tuple([None if c == '?' else int(c) for c in s])
        
        try:
            with open(fname, encoding='utf-8') as f:
                tmp = {}
                for no_line, line in enumerate(f):
                    try:
                        token = line.split()
                        tmp[token[0]] = str_to_tuple(token[1])
                    except Exception as e:
                        print('format error at %s \n(no_line = %d): %s' % (fname, no_line, line))
                        print('error type:', e)
                        break
                return tmp
        except FileNotFoundError:
            print('%s does not exist' % fname)
            return {}
        else:
            print('unexpected errors')
            return {}
    
    
    def get_tags(self, chars):
        if chars in self.rule_dict:
            return self.rule_dict[chars]
        return None
    


    
class CharsFrequency:

    def __init__(self):
        '''
            C[chars][tag_index] = frequency
            C는 (chars, tag)에 대해서 몇 번 등장했는지 카운팅하는 자료구조.
            tag_index는 0 = 띄어쓰지 않음, 1 = 띄어씀으로 표현하는 tuple
            
            구조
            C{
                chars: 
                tags: freqeuncy (int)
            }
        '''
        self.C = defaultdict(lambda:defaultdict(int))
        
    
    def add(self, chars, tags, frequency = 1):
        self.C[chars][tags] += frequency
    
        
    def get_tags(self, chars):
        if chars in self.C:
            return self.C[chars].keys()
        else:
            return []
    
    
    def get_frequency(self, chars, tags):
        '''
        chars: str
        tags: tuple(int)
              (0, 1, 0)
        '''
        if (chars in self.C) and (tags in self.C[chars]):
            return self.C[chars][tags]
        else:
            return 0
                
     
    def filter_tags(self, min_count):
        for chars in self.C.keys():
            self.C[chars] = defaultdict(lambda:0, {k:v for k, v in self.C[chars].items() if v >= min_count})
            if not self.C[chars]:
                del self.C[chars]
                    
                    
    def num_of_chars(self):
        return len(self.C)
    
    
    def num_of_tags(self):
        length = 0
        for char, tagdict in self.C.items():
            length += len(self.C[char])

        return length
    

class Model:
    
    def __init__(self, min_window=3, max_window=7, filtering_document_min_count=10000, min_count=5):
        '''
            min_window: int
                모델이 기억하는 (char, tag)의 char의 최소 길이. 
                만약 길이가 2면 애매모호한 경우가 많이 생기기 때문에 3 이상을 추천
                
            max_window: int
                모델이 기억하는 (char, tag)의 char의 최대 길이.
                지나치게 길게 설정하면 min_count보다 적게 등장하는 경우들은 거의 다 버려질 것임
                
            filtering_epoch: int
            
            min_count: int
                train()에서 filtering_epoch 마다 (char, tag)의 빈도수가 
                min_count보다 작은 경우들을 C에서 삭제함.
        '''
        self.min_window = min_window
        self.max_window = max_window
        self.filtering_document_min_count = filtering_document_min_count
        self.min_count = min_count
        
        self.CF = CharsFrequency()

        
    def __extract(self, doc, window):
        chars, tags = self.space_tag(doc) ## 수정함
        if len(chars) < window:
            return list()
        else:
            return [(chars[i:(i+window)], tags[i:(i+window)]) for i in range(len(chars) - window+1)]
    
    
    def filter_counters(self, num_doc):
        before = self.CF.num_of_tags()
        self.CF.filter_words(self.min_count)
        after = self.CF.num_of_tags()
        sys.stdout.write('\rall tags length = %d --> %d, (num_doc = %d)' % (before, after, num_doc))
    
    
    def train(self, fname, num_lines=-1):
        with open(fname, encoding='utf-8') as f:
            for num_doc, doc in enumerate(f): 

                if not doc: 
                    continue
                    
                for w in range(self.min_window, self.max_window + 1):
                    for chars, tags in self.__extract(doc, w):
                        self.CF.add(chars, tuple(tags))
                        
                if num_doc > 0 and num_doc % self.filtering_document_min_count == 0:
                    self.filter_counters(num_doc)

                if not num_lines == -1 and num_doc >= num_lines: 
                    break
                
            self.filter_counters(num_doc)
    
    
    def print_tags(self, tags, head = None):
        if head != None:
            print(head, end=' ')
            
        str_tags = ['?' if t == None else t for t in tags]
        print(('{} '*len(str_tags)).format(*str_tags))
        
    
    def is_matched(self, base_tags, candidate_tags):
        '''
            base_tags: list
                Tag as context in given sentence
                It can contain "None"
            candidate_tags: tuple(int)
                Tag in model
                All chars are one of 0 or 1 which are int type
        '''
        for b, c in zip(base_tags, candidate_tags):
            if b == None: continue
            if b != c: return False
        return True
    
    
    def rule_based_tag(self, rule_dict, chars, tags, debug = False):
        '''
        
        '''
        begin = 0
        length = len(chars)
        
        while begin < length:
            
            if tags[begin] != None:
                begin += 1
                continue
            
            for window in reversed(range(rule_dict.min_rule_length, rule_dict.max_rule_length+1)):
                    
                end = begin + window

                # outbound exception handling
                if end >= length:
                    continue
                
                # skip if space tag exists
                if ( len([i for i,tag in enumerate(tags[begin:end]) if tag == None]) != window ):
                    continue
                
                sub_chars = chars[begin:end]
                sub_tags = rule_dict.get_tags(sub_chars)
                
                # skip if subchars does not exist in rule dictionary
                if sub_tags == None:
                    continue
                
                # skip if first rule-tag is not matched
                if (begin > 0) and (tags[begin-1] != None) and (tags[begin-1] != sub_tags[0]):
                    continue
                
                # rule tagging
                for i in range(window):
                    tags[begin + i] = sub_tags[i+1]

                if begin > 0:
                    tags[begin-1] = sub_tags[0]
                    
                if debug:
                    print('rule tagging (b=%d, e=%d), subchar=%s, tags=%s' % (begin, end, sub_chars, sub_tags) )
                
                begin = end - 1
                break
            
            begin += 1
                
        return tags
    
    
    def space(self, chars, tags):
        return ''.join([c+' ' if t==1 else c for c,t in zip(chars, tags)]).strip()
    
    
    def space_tag(self, doc, nonspace=0):
        '''
            doc   = '이건 예시문장입니다'l
            chars = '이건예시문장입니다'
            tags  = list(0,1,000001)
        '''
        chars = doc.replace(' ','')
        tags = [nonspace]*(len(chars) - 1) + [1]
        idx = 0

        for d in doc:
            if d == ' ':
                tags[idx-1] = 1
            else:
                idx += 1

        return chars, tags
    
    
    def correct(self, doc, verbose = False, min_count = 30, 
                force_abs_threshold = 0.9, nonspace_threshold = -0.5, space_threshold = 0.7,
                rules = None, debug = False):
        '''
            rules: RuleDict
                dict['word'] = 'tag'
                rules = {'가감':(0,0,0), '가구':(None,0,1), '가갸':(1,0,None), ...}
                
        '''
        chars, tags = self.space_tag(doc, nonspace=None)
        
        if verbose:
            self.print_tags(tags, head = 'Input:')
            print(self.space(chars, tags))
        
        # rule-based tagging
        if rules:
            tags = self.rule_based_tag(rules, chars, tags, debug)
            
            if verbose:
                self.print_tags(tags, head = 'Ruled:')
                print(self.space(chars, tags))
        
        length = len(tags)
        
        # correcting: initialize features_list
        features_list = [[]]*length
        
        for i in range(length):
            
            features = []
            if tags[i] != None:
                continue
            
            for window in range(self.min_window, self.max_window + 1):
                for stride in range(window):
                    
                    begin = i - window + stride + 1
                    end = begin + window
                    
                    if (begin < 0) or (end > length):
                        continue
                    
                    at = i - begin
                    sub_chars = chars[begin:end]
                    sub_tags = tags[begin:end]
                    
                    for candidate_tags in self.CF.get_tags(sub_chars):
                        if self.is_matched(sub_tags, candidate_tags):
                            freq = self.CF.get_frequency(sub_chars, candidate_tags)
                            features.append((candidate_tags, at, freq))
                            
            features_list[i] = features
                        
        assert len(features_list) == length
                
        scores_lcr = [self.score_lcr(features, min_count) for features in features_list]
        scores = [self.score(score_lcr) for score_lcr in scores_lcr]
        
        num_iter = 0
        while True :
            
            num_iter += 1
            is_updated = False
            
            # force tagging: all positions which have force_abs_threshold above score
            features_list, scores_lcr, scores, is_updated = self.force_tag(tags, length, features_list, scores_lcr, scores, force_abs_threshold, min_count, num_iter, verbose, is_updated, debug)
                
            # sequential tagging: find maximum score and its index
            features_list, scores_lcr, scores, is_updated = self.sequential_tag(tags, features_list, scores_lcr, scores, nonspace_threshold, space_threshold, min_count, num_iter, verbose, is_updated, debug)
            
            if not is_updated:
                break
            
            # for safety
            if num_iter == 999:
                print('Unexpected bug. You are traped in infinite while loop. len(doc) = %d' % len(chars))
                break

        return self.space(chars, tags), tags

    
    def force_tag(self, tags, length, features_list, scores_lcr, scores, force_abs_threshold, min_count, num_iter, verbose, is_updated, debug):
        
        for i in range(length):
            
            if (abs(scores[i]) >= force_abs_threshold) and self.is_useful(scores_lcr[i], i):
                
                if debug:
                    print('force tagging i=%d, score=%.3f' % (i, scores[i]))
                
                tags[i] = 1 if scores[i] > 0 else 0
                features_list, scores_lcr, scores = self.update(features_list, scores_lcr, scores, i, tags[i], min_count)
                is_updated = True

        if verbose:
            self.print_tags(tags, head = 'Force tagged (iter=%d):' % num_iter)

        return features_list, scores_lcr, scores, is_updated
    
    
    def sequential_tag(self, tags, features_list, scores_lcr, scores, nonspace_threshold, space_threshold, min_count, num_iter, verbose, is_updated, debug):
        
        sorted_score = sorted(enumerate(scores), key=lambda x:abs(x[1]), reverse=True)

        for info in sorted_score:

            i = info[0]
            score = info[1]

            if (self.is_useful(scores_lcr[i], i)) and (score <= nonspace_threshold or score >= space_threshold):
                
                if debug:
                    print('sequential tagging i=%d, score=%.3f' % (i, scores[i]))
                    
                tags[i] = 0 if score < 0 else 1
                features_list, scores_lcr, scores = self.update(features_list, scores_lcr, scores, i, tags[i], min_count)
                is_updated = True

                if verbose:
                    self.print_tags(tags, head = 'Iteratively tagged (iter=%d):' % num_iter)

                # for sequential labeling
                break
        
        return features_list, scores_lcr, scores, is_updated
        
            
    def is_useful(self, score_lcr, i):

        if (i == 0) and (score_lcr[2] != 0):
            return True

        if score_lcr[1] != 0:
            return True

        return (score_lcr[0] * score_lcr[2]) > 0

            
    def update(self, features_list, scores_lcr, scores, i, tag, min_count):

        begin = max(0, i - (self.max_window - 1))
        end = min(len(scores), i + (self.max_window - 1) + 1)
        
        for j in range(begin, end):
            
            removal_index = []
            features = features_list[j]
            for index, feature in enumerate(features):
                at = i - j + feature[1]
                if (at < 0) or (at >= len(feature[0])):
                    continue
                if tag != feature[0][at]:
                    removal_index.append(index)
                    
            if removal_index:
                for index in reversed(removal_index):
                    del features[index]
                    
                scores_lcr[j] = self.score_lcr(features, min_count)
                scores[j] = self.score(scores_lcr[j])

        features_list[i] = []
        scores_lcr[i] = [0, 0, 0]
        scores[i] = 0                
                
        return features_list, scores_lcr, scores
                
        
    def score_lcr(self, features, min_count):
        '''
        feature = (tag, at, freq)
        '''
        l_neg = 0
        l_pos = 0
        c_neg = 0
        c_pos = 0
        r_neg = 0
        r_pos = 0
        
        for feature in features:
            tags = feature[0]
            at = feature[1]
            freq = feature[2]
            end_at = len(tags) - 1
            if (at == 0) and (tags[at] == 0):
                r_neg += freq
            elif (at == 0) and (tags[at] == 1):
                r_pos += freq
            elif (at == end_at) and (tags[at] == 0):
                l_neg += freq
            elif (at == end_at) and (tags[at] == 1):
                l_pos += freq
            elif tags[at] == 0:
                c_neg += freq
            elif tags[at] == 1:
                c_pos += freq
        
        l_score = 0 if (l_neg + l_pos) < min_count else 2 * ((l_pos / (l_pos + l_neg)) - 0.5)
        c_score = 0 if (c_neg + c_pos) < min_count else 2 * ((c_pos / (c_pos + c_neg)) - 0.5)
        r_score = 0 if (r_neg + r_pos) < min_count else 2 * ((r_pos / (r_pos + r_neg)) - 0.5)
        
        return [l_score, c_score, r_score]
    
    
    def score(self, score_lcr):
        score_lcr = [s for s in score_lcr if not s == 0]
        if score_lcr:
            return sum(score_lcr) / len(score_lcr)
        else:
            return 0

        
    def save_model(self, fname):

        with open(fname, 'w', encoding='utf-8') as f:
        
            f.write('## parameters\n')
            f.write('min_window = %d\n' % self.min_window)
            f.write('max_window = %d\n' % self.max_window)
            f.write('filtering_document_min_count = %d\n' % self.filtering_document_min_count)
            f.write('min_count = %d\n' % self.min_count)
            
            f.write('## counters\n')
            for chars, tagdic in self.CF.C.items():
                for tags, frequency in tagdic.items():
                    tags = ''.join([str(t) for t in tags])
                    f.write('%s %s %d\n' % (chars, tags, frequency))

            
    def load_model(self, fname, json_input=True):
        
        if json_input:
            self._load_model_from_json(fname)
            
        else:
            with open(fname, encoding='utf-8') as f:
                
                next(f) # skip: ## parameters
#                self.min_window = int(next(f).split('min_window = ')[1].replace('\n',''))
#                self.max_window = int(next(f).split('max_window = ')[1].replace('\n',''))
#                self.filtering_document_min_count = int(next(f).split('filtering_document_min_count = ')[1].replace('\n',''))
#                self.min_count = int(next(f).split('min_count = ')[1].replace('\n',''))
                for i in range(4):
                    next(f)

                next(f) # skip: ## counters
                for line in f:
                    chars, tags, frequency = line.replace('\n', '').split(' ')
                    tags = tuple([int(t) for t in tags])
                    frequency = int(frequency)
                    self.CF.add(chars, tags, frequency = frequency)

                
                
    def _load_model_from_json(self, fname):
        with open(fname, encoding='utf-8') as f:
            model_json = json.load(f)
#        self.min_window = model_json['parameters']['min_window']
#        self.max_window = model_json['parameters']['max_window']
#        self.filtering_document_min_count = model_json['parameters']['filtering_document_min_count']
#        self.min_count = model_json['parameters']['min_count']
        
        loaded_counter = model_json['counters']
        
        for chars, tagdict in loaded_counter.items(): 
            for tags, freq in tagdict.items():
                tags = tuple([int(t) for t in tags])
                freq = int(freq)
                self.CF.add(chars, tags, frequency = freq)
