import os
import pickle
from typing import List
from warnings import warn

import pycrfsuite

from MicroTokenizer.CRF.crf_trainer import CRFTrainer, default_word2features
from MicroTokenizer.base_tokenizer import BaseTokenizer
from MicroTokenizer.crf_loader import CRFLoader
from MicroTokenizer.seq2seq.BMES import decoding


class CRFTokenizer(BaseTokenizer):
    def __init__(self, *args, **kwargs):
        super(CRFTokenizer, self).__init__(*args, **kwargs)

        self.model_file = self.get_model_file(self.model_dir)
        self.crf_tagger = None

        self.crf_trainer = CRFTrainer()

        self.open_mode = None
        self.file_content = None

        self.word2features_func = None

    @staticmethod
    def get_model_file(model_dir):
        return os.path.join(model_dir, 'model.crfsuite')

    @staticmethod
    def get_char2feature_file(model_dir):
        return os.path.join(model_dir, 'char2feature.pickle')

    def load_model(self):
        self.crf_tagger = pycrfsuite.Tagger()
        self.crf_tagger.open(self.model_file)

        pickle_file = self.get_char2feature_file(self.model_dir)
        with open(pickle_file, 'rb') as fd:
            self.word2features_func = pickle.load(fd)

    def predict_char_tag(self, char_list):
        tag_list = self.predict_tag(char_list)

        return list(zip(char_list, tag_list))

    def predict_tag(self, char_list):
        feature_list = [
            self.word2features_func(char_list, i)
            for i in range(len(char_list))
        ]

        tag_list = self.crf_tagger.tag(feature_list)

        return tag_list

    def segment(self, message):
        # type: (str) -> List[str]

        char_tag_list = self.predict_char_tag(message)

        return decoding(char_tag_list)

    def train_one_line(self, token_list):
        # type: (List[str]) -> None

        self.crf_trainer.train_one_line_by_token(token_list)

    def do_train(self):
        warn(
            "During to the limit of pycrfsuite: do_train will do nothing, "
            "persist_to_dir will do real train work."
            "Also because no training here, model for this instance will not update"
        )

    def persist_to_dir(self, output_dir):
        # type: (str) -> None

        # TODO: should persist feature function as well
        model_file = self.get_model_file(output_dir)

        self.crf_trainer.train(model_file)

        pickle_file = self.get_char2feature_file(output_dir)
        with open(pickle_file, 'wb') as fd:
            pickle.dump(self.crf_trainer.char2feature_func, fd)

    def assign_from_loader(self, *args, **kwargs):
        self.crf_tagger = kwargs['crf_tagger']
        self.word2features_func = kwargs['word2features_func']

    def get_loader(self):
        return CRFLoader
