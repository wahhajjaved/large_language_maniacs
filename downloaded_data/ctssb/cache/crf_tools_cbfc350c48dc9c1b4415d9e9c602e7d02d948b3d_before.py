# -*- coding: utf-8 -*-

from collections import Counter
from copy import deepcopy
from itertools import chain, groupby
import re
import joblib as jl
import scipy.stats as sstats
import sklearn_crfsuite
from sklearn.metrics import make_scorer
from sklearn.model_selection import RandomizedSearchCV
from sklearn_crfsuite import metrics

from src.arsenal_stats import *

HEADER_CRF = ['TOKEN', 'POS', 'NER']

HEADER_REPORT = ['tag', 'precision', 'recall', 'f1', 'support']
RE_WORDS = re.compile(r"[\w\d\.-]+")


##############################################################################


def process_annotated(in_file, col_names=HEADER_CRF):
    """
    :param in_file: CSV file: TOKEN, POS, NER
    :param col_names
    :return: [[sent]]
    """
    data = pd.read_csv(in_file, header=None, engine='c', quoting=0)
    data.columns = col_names
    data = data.dropna()
    return data


def batch_loading(crf_f, feature_hdf, hdf_keys):
    """
    :param dict_conf:
    :param crf_f:
    :param feature_hdf:
    :param hdf_keys:
    :param crf_model:
    :return:
    """
    crf = jl.load(crf_f) if crf_f else None
    loads = hdf2df(feature_hdf, hdf_keys)
    f_dics = prepare_features(loads)
    return crf, f_dics


def prepare_features(dfs):
    """
    :param dfs: a list of pd dfs
    :return: a list of feature sets and feature dicts
    """
    f_sets = {name: df2set(df) for (name, df) in dfs.items() if len(df.columns) == 1}
    f_dics = {name: df2dic(df) for (name, df) in dfs.items() if len(df.columns) == 2}
    f_sets_dics = {k: {i: 1 for i in j} for (k, j) in f_sets.items()}  # special case
    f_dics.update(f_sets_dics)
    return OrderedDict(sorted(f_dics.items()))


def batch_add_features(df, f_dics):
    """
    # This will generate multiple list of repeated dfs, so only extract the last list
    :param df: a single df
    :param f_dics: feature dicts
    :return: a single df
    """
    df_list = [map_dic2df(df, name, f_dic) for name, f_dic in f_dics.items()]
    return df_list[-1]


def df2crfsuite(df, delim='##END'):
    delimiter = tuple(df[df.iloc[:, 0] == delim].iloc[0, :].tolist())
    sents = zip(*[df[i].tolist() for i in df.columns])  # Use * to unpack a list
    sents = (list(x[1]) for x in groupby(sents, lambda x: x == delimiter))
    result = [i for i in sents if i != [] and i != [(delimiter)]]
    return result

##############################################################################


def feature_selector(word_tuple, feature_conf, window, hdf_key):
    """
    Set the feature dict here
    :param word: word itself
    :param feature_conf: feature config
    :param window: select the right config from feature_config
    :return:
    """

    word, pos, other_features = word_tuple[0], word_tuple[1], word_tuple[3:]
    other_dict = {'_'.join((window, j)): k for j, k in zip(sorted(hdf_key), other_features)}
    feature_func = {name: func for (name, func) in feature_conf.items() if
                    name.startswith(window)}
    feature_dict = {name: func(word) for (name, func) in feature_func.items()}
    feature_dict.update(other_dict)
    feature_dict.update({'_'.join((window, 'pos')): pos})
    return feature_dict


def word2features(sent, i, feature_conf, hdf_key):
    features = feature_selector(sent[i], feature_conf, 'current', hdf_key)
    features.update({'bias': 1.0})
    if i > 0:
        features.update(
            feature_selector(sent[i - 1], feature_conf, 'previous', hdf_key))
    else:
        features['BOS'] = True
    if i < len(sent) - 1:
        features.update(
            feature_selector(sent[i + 1], feature_conf, 'next', hdf_key))
    else:
        features['EOS'] = True
    return features


def sent2features(line, feature_conf, hdf_key):
    return [word2features(line, i, feature_conf, hdf_key) for i in range(len(line))]


def sent2labels(line):
    return [i[2] for i in line]  # Use the correct column


def sent2label_spfc(line, label):
    return [i[2] if i[2].endswith(label) else '0' for i in line]


##############################################################################


# CRF training

def feed_crf_trainer(in_data, conf, hdf_key):
    """
    :param in_data:
    :param conf_f:
    :return: nested lists of lists
    """
    features = [sent2features(s, conf, hdf_key) for s in in_data]
    labels = [sent2labels(s) for s in in_data]
    return features, labels


def train_crf(X_train, y_train, algm='lbfgs', c1=0.1, c2=0.1, max_iter=100,
              all_trans=True):
    """
    :param X_train:
    :param y_train:
    :param algm:
    :param c1:
    :param c2:
    :param max_iter:
    :param all_trans:
    :return:
    """
    crf = sklearn_crfsuite.CRF(
        algorithm=algm,
        c1=c1,
        c2=c2,
        max_iterations=max_iter,
        all_possible_transitions=all_trans
    )
    return crf.fit(X_train, y_train)


def show_crf_label(crf, remove_list=['O', 'NER', '']):
    labels = list(crf.classes_)
    return [i for i in labels if i not in remove_list]


def make_param_space():
    return {
        'c1': sstats.expon(scale=0.5),
        'c2': sstats.expon(scale=0.05),
    }


def make_f1_scorer(labels, avg='weighted'):
    return make_scorer(metrics.flat_f1_score, average=avg, labels=labels)


def search_param(X_train, y_train, crf, params_space, f1_scorer, cv=10, iteration=50):
    rs = RandomizedSearchCV(crf, params_space,
                            cv=cv,
                            verbose=1,
                            n_jobs=-1,
                            n_iter=iteration,
                            scoring=f1_scorer)
    return rs.fit(X_train, y_train)


##############################################################################


# CRF testing and predicting


def convert_tags(data):
    converted = []
    for sent in data:
        test_result = []
        for tag in sent:
            if tag == 'O':
                test_result.append('0')
            else:
                test_result.append('1')
        converted.append(test_result)
    return converted


def export_test_result(labels, y_test, y_pred):
    details = metrics.flat_classification_report(y_test, y_pred, digits=3, labels=labels)
    details = [i for i in [re.findall(RE_WORDS, i) for i in details.split('\n')] if i !=
               []][1:-1]
    details = pd.DataFrame(details, columns=HEADER_REPORT)
    details = details.sort_values('f1', ascending=False)
    return details


def test_crf_prediction(crf, X_test, y_test, test_switch='spc'):
    """

    :param crf:
    :param X_test:
    :param y_test:
    :param test_switch: 'spc' for specific labels, 'bin' for binary labels
    :return:
    """
    y_pred = crf.predict(X_test)

    if test_switch == 'spc':
        labels = show_crf_label(crf)

        result = metrics.flat_f1_score(y_test, y_pred, average='weighted', labels=labels)
        details = export_test_result(labels, y_test, y_pred)
        return result, details

    elif test_switch == 'bin':

        y_pred_converted = convert_tags(y_pred)
        y_test_converted = convert_tags(y_test)
        labels = ['1']

        result = metrics.flat_f1_score(y_test_converted, y_pred_converted,
                                       average='weighted',
                                       labels=labels)
        y_test_flatten = ['0' if j == 'O' else '1' for i in y_test for j in i]
        details = export_test_result(labels, y_test_flatten, y_pred_converted)
        return result, details


def crf_predict(crf, new_data, processed_data):
    result = crf.predict(processed_data)
    length = len(list(new_data))
    crf_result = (
        [(new_data[j][i][:2] + (result[j][i],)) for i in range(len(new_data[j]))] for j in
        range(length))
    crf_result = [i + [('##END', '###', 'O')] for i in crf_result]
    return list(chain.from_iterable(crf_result))


##############################################################################


def crf_result2dict(crf_result):
    ner_candidate = [(token, ner) for token, _, ner in crf_result if ner[0] != 'O']
    ner_index = (i for i in range(len(ner_candidate)) if
                 ner_candidate[i][1][0] == 'U' or ner_candidate[i][1][0] == 'L')
    new_index = (a + b for a, b in enumerate(ner_index))
    ner_result = extract_ner_result(ner_candidate, new_index)
    return ner_result


def extract_ner_result(ner_candidate, new_index):
    new_candidate = deepcopy(ner_candidate)
    for i in new_index:
        new_candidate[i + 1:i + 1] = [('##split', '##split')]
    ner_result = (
        ' '.join(
            [(i[0].strip() + '##' + i[1].strip()) for i in new_candidate if i[1]]).split(
            '##split'))
    ner_result = ([i.strip(' ') for i in ner_result if i and i != '##'])
    ner_result = ('##'.join((' '.join([i.split('##')[0] for i in tt.split()]), tt[-3:]))
                  for tt in
                  ner_result)
    ner_result = sort_dic(Counter(i for i in ner_result if i), sort_key=1, rev=True)
    return ner_result


def crf_result2json(crf_result, raw_df):
    ner_phrase = crf_result2dict(crf_result)
    raw_df.result.to_dict()[0]['ner_phrase'] = ner_phrase
    raw_df = raw_df.drop(['content'], axis=1)
    json_result = raw_df.to_json(orient='records', lines=True)
    return json_result