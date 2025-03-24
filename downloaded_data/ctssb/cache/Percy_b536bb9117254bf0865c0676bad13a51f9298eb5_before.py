import re
from app_folder.main.neural_tools import word_sims
from nltk import word_tokenize, pos_tag


class IntentParser(object):

    def __init__(self, intent_mappers):
        self.intent_mappers = self.load_intent_(intent_mappers)

    def __contains__(self, item):
        if any([lambda x: x, [im.run_search_(item) for im in self.intent_mappers]]):
            return True
        else:
            return False

    def load_intent_(self, intent_mappers):
        if not isinstance(intent_mappers, list):
            return [intent_mappers]
        else:
            return intent_mappers

    def filter_parsers_(self, text, intent_mappers_):
        for im in intent_mappers_:
            if im.run_search_(text) is True:
                return True

    def map_(self, text):
        matched = list(filter(lambda x: x.run_search_(text), self.intent_mappers))
        if not matched:
            raise Exception("IntentParser Found no Matches")
        elif len(matched) > 1:
            raise Exception("IntentParser Found multiple Matches")
        return matched[0]

    def answer_question(self, text):
        matched_parser = self.map_(text)
        answer = matched_parser.answer_question_(text)
        return answer


class SynonymParser(object):

    """
    Checks message and returns true if message indicates checking for synonyms

    Preprocesses string:
        - Returning string found after "synonyms" or variant
        - Tokening above string
        - POS Tagging and Filtering by NN*

    Gather synonyms
        - Calls word_sims() from neural_tools.py

    Generate reply
        - Generates reply to query

    """

    def __init__(self):
        pass

    @property
    def search_method_(self):
        # matches "synonyms" are approximate spelling
        return r"(syn[a-z]+?ms?)"

    @property
    def default_pos_(self):
        return ['NN', 'JJ']

    @property
    def search_method(self):
        return re.compile(self.search_method_, flags=re.IGNORECASE)

    @property
    def preamble_(self):
        return "Here are some synonyms for {}:"

    def run_search_(self, text):
        search_method = self.search_method
        if search_method.search(text) is not None:
            return True
        else:
            return False


    def preprocess_string_(self, text):
        # Splitting query to text following search_method
        word_matched = self.search_method.search(text).group()  # "Synonym" or variant
        text_list = self.search_method.split(text)  # Before, "Synonym", After
        text_pos = text_list.index(word_matched) + 1  # Position of After in list
        entities = text_list[text_pos] # After
        entities = pos_tag(word_tokenize(entities))  # Tokenize and POS Tag

        def filter_tag(token_tag, pos_filter=self.default_pos_):
            tag = token_tag[1]
            if any([tag.startswith(pf) for pf in pos_filter]):
                    return True
            return False

        entities = list(filter(filter_tag, entities))  # Filter by POS
        entities = [word for word, tag in entities]  # Remove tag
        return entities

    def run_query_(self, entities, topn=5):
        if isinstance(entities, str):
            entities = [entities]

        results = []
        for e in entities:
            sims = word_sims(e, topn=topn)
            results.append(sims[1])

        return results

    def transform_to_data_(self, text):
        entities = self.preprocess_string_(text)
        query_result = self.run_query_(entities)
        return entities, query_result

    def make_preamble_(self, entity):
        return self.preamble_.format(entity)

    def convey_results_(self, result):
        words = [word for word, score in result.items()]
        return ", ".join(words)

    def make_conveyable_(self, entities, results):
        preamble = [self.make_preamble_(entity) for entity in entities]
        results = [self.convey_results_(result) for result in results]
        message = []
        for p, r in zip(preamble, results):
            reply = "{} {}".format(p, r)
            message.append(reply)
        return "\n".join(message)

    def answer_question_(self, text):
        entites, query_result = self.transform_to_data_(text)
        text_result = self.make_conveyable_(entites, query_result)
        return text_result


