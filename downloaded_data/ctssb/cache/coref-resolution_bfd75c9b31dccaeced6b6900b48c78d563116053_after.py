# author: Clay Riley 2017
# script usage: featurize.py <path to file to featurize> <OPTION>
#
# <OPTION> may be "--train" (writes gold standard labels to output)
# Otherwise, only uses gold standard labels for instance generation.
#
# Dumps instances to a pickle file.

import sys, os, re, errno, pickle

class Featurizer:

    def instantiate(self, antecedent, anaphor, between, training):
        """create a featurized instance given two lists of lists 
        of tokens' features and whether or not to train"""
        
        # record whether they corefer, if training
        refs_i = set(antecedent[0][-1])
        refs_j = set(anaphor[0][-1])
        coreference = int(not refs_i.isdisjoint(refs_j)) if training else None
        
        # generate values for use in features
        sentence_dist = anaphor[0][0] - antecedent[-1][0]
        token_dist = int(anaphor[0][1]) - int(antecedent[-1][1])
        tokens_raw_i = [token[5] for token in antecedent]
        tokens_raw_j = [token[5] for token in anaphor]
        tokens_i = '_'.join(tokens_raw_i).lower()
        tokens_j = '_'.join(tokens_raw_j).lower()
        POSes_i = [token[6] for token in antecedent]
        POSes_j = [token[6] for token in anaphor]
        tokens_raw_bt = [token[5] for token in between]
        tokens_bt = '_'.join(tokens_raw_bt).lower()
        
        # build feature dict
        fts = {}
        fts['i']=tokens_i
        fts['j']=tokens_j
        fts['dist_t']=token_dist
        fts['dist_s']=sentence_dist
        
        return fts, coreference


    def getInstances(self, in_path=None):
        """ reads raw data, separates it into more easily parsed 
        formats, and creates classification instances """

        in_path = self.input_path if in_path is None else in_path

        with open(in_path, 'r') as f_in:
            
            # regexes for this task
            startR = re.compile(r'\((\d+)(?!\d)')
            endR = re.compile(r'(?<!\d)(\d+)\)')
            
            # previously encountered and incomplete entities
            antecedents, open_entities = [], {}
            all_tokens = []
            absID, senID, refID = 0, 0, 0
            
            for line in f_in:
    
                # new section: reset the antecedents and sentence/token IDs
                if line[0] == '#':
                    antecedents, open_entities = [], {}
                    senID = 0
                
                # new sentence: update sentence IDs
                elif line.strip() == '':
                    senID += 1
                    open_entities = {}  # also, silently give up hope for any entities remaining open
                
                # new token
                else:
                    fields = [absID, senID] + line.split()  # include absolute and sentence ids
                    anaphora = []  # list of current anaphora
                    entrefs = fields[-1]  # coreference resolution via gold standard
                    starts = startR.findall(entrefs)
                    ends = endR.findall(entrefs)
                
                    # current token has entity start(s), open it
                    if len(starts) > 0:  
                        for entity in starts:
                            open_entities[entity] = [refID]  # unique index to ensure order preservation
                            refID += 1
                    
                    # add this token's info to all opened entities
                    fields[-1] = []
                    for ent in open_entities:
                        fields[-1].append(ent)
                        open_entities[ent].append(fields)
                    
                    # current token has entity end(s), close it
                    if len(ends) > 0:  
                        closing = {} 
                        for ent in ends:  # this second loop ensures order preservation
                            try: 
                                e = open_entities.pop(ent)
                                closing[e[0]] = e[1:]
                            except KeyError: 
                                pass  # sweep this annotation problem under the rug
                        for refID in closing: anaphora.append(closing[refID])  
                    
                    # process all possible antecedent-anaphor pairs
                    for ana in anaphora:
                        for ant in antecedents:
                            intervening = [all_tokens[i] for i in range(ant[-1][0]+1, ana[0][0])]
                            instance, label = self.instantiate(ant, ana, intervening, self.training)
                            self.instances.append(instance)
                            self.labels.append(label)
                    
                    antecedents.extend(anaphora)  # add all current anaphora to antecedents
                    all_tokens.append(fields)  # add this token to list of all tokens up to this point
                    absID += 1


    def write(self, out_path=None):
        """ write instances and labels to pickle file. """

        out_path = self.output_path if out_path is None else out_path

        # ensure data is okay
        if len(self.instances) != len(self.labels): 
            raise IOError('Numbers of labels ({}) and instances ({}) differ'
                          '!'.format(len(self.labels), len(self.instances))) 

        # build directory for output
        try: os.makedirs(os.path.dirname(out_path))
        except OSError as e: 
            if e.errno != errno.EEXIST: raise e

        # dump to pickle file
        with open(out_path, 'w') as f_out:
            dump = {'instances':self.instances, 'labels':self.labels}
            pickle.dump(dump, f_out)


    def __init__(self, input_path, output_path, training):
        self.input_path = input_path
        self.output_path = output_path
        self.training = training
        self.instances = []
        self.labels = []


def main():

    if len(sys.argv) < 2: 
        raise IOError('featurize.py requires a filepath arg.\nusage: >'
                      'featurize.py <path to file to featurize> (--train)')

    inp = os.path.abspath(sys.argv[1])
    out = re.sub('/data/', '/output/', re.sub(r'\..+\b', '.fts', inp))
    train = '--train' in sys.argv

    print inp
    print out
    print train

    f = Featurizer(inp, out, train)

    f.getInstances()
    print f.instances[:5]
    f.write()
    

if __name__ == '__main__':
    main()

