from collections import defaultdict


class DataIndexer:
    """
    A DataIndexer maps strings to integers, allowing for strings to be mapped to an
    out-of-vocabulary token.

    DataIndexers are fit to a particular dataset, which we use to decide which words are
    in-vocabulary.
    """
    def __init__(self):
        # Typically all input words to this code are lower-cased, so we could simply use "PADDING"
        # for this.  But doing it this way, with special characters, future-proofs the code in case
        # it is used later in a setting where not all input is lowercase.
        self._padding_token = "@@PADDING@@"
        self._oov_token = "@@UNKOWN@@"
        self.word_index = {self._padding_token: 0, self._oov_token: 1}
        self.reverse_word_index = {0: self._padding_token, 1: self._oov_token}

    def fit_word_dictionary(self, dataset: 'TextDataset', min_count: int=1):
        """
        Given a Dataset, this method decides which words are given an index, and which ones are
        mapped to an OOV token (in this case "UNK").  This method must be called before any dataset
        is indexed with this DataIndexer.  If you don't first fit the word dictionary, you'll
        basically map every token onto "UNK".

        We call instance.words() for each instance in the dataset, and then keep all words that
        appear at least min_count times.
        """
        word_counts = defaultdict(int)
        for instance in dataset.instances:
            for word in instance.words():
                word_counts[word] += 1
        for word, count in word_counts.items():
            if count >= min_count:
                self.add_word_to_index(word)

    def add_word_to_index(self, word: str) -> int:
        """
        Adds `word` to the index, if it is not already present.  Either way, we return the index of
        the word.
        """
        if word not in self.word_index:
            index = len(self.word_index)
            self.word_index[word] = index
            self.reverse_word_index[index] = word
            return index
        else:
            return self.word_index[word]

    def words_in_index(self):
        return self.word_index.keys()

    def get_word_index(self, word: str):
        if word in self.word_index:
            return self.word_index[word]
        else:
            return self.word_index[self._oov_token]

    def get_word_from_index(self, index: int):
        return self.reverse_word_index[index]

    def get_vocab_size(self):
        return len(self.word_index) + 1
