# -*- coding: utf-8 -*-

from scipy import stats
import os
from json import load
from pandas.io.json import json_normalize

from .arsenal_nlp import *
from .arsenal_spacy import *
from .arsenal_stats import *

HEADER_FS = ['fact', 'entity_proper_name', 'entity_type']
HEADER_SN = ['factset_entity_id', 'short_name']
HEADER_SN_TYPE = ['entity_type', 'short_name']
HEADER_SCHWEB = ['Language', 'Title', 'Type']
HEADER_EXTRACTED = ['Count', 'Token', 'POS', 'NER']
HEADER_ANNOTATION = ['TOKEN', 'NER', 'POS']

LABEL_COMPANY = ['PUB', 'EXT', 'SUB', 'PVT', 'MUT', 'UMB', 'PVF', 'HOL', 'MUC', 'TRU', 'OPD', 'PEF', 'FND', 'FNS',
                 'JVT', 'VEN', 'HED', 'UIT', 'MUE', 'ABS', 'GOV', 'ESP', 'PRO', 'FAF', 'SOV', 'COR', 'IDX', 'BAS',
                 'PRT', 'SHP']
LABEL_ANS = ['category', 'nname_en']

HDF_KEY_20170425 = ['aca', 'com_single', 'com_suffix', 'location', 'name', 'ticker', 'tfdf', 'tfidf']

NON_PPL_COM_DIC = {'U-GPE': 'O', 'B-GPE': 'O', 'I-GPE': 'O', 'L-GPE': 'O', 'B-GOV': 'O', 'L-GOV': 'O',
                   'I-GOV': 'O', 'U-ACA': 'O', 'B-ACA': 'O', 'L-ACA': 'O', 'I-ACA': 'O', 'U-GOV': 'O'}

FULL_NER_DIC = {'U-COM': 'U-COM', 'O': 'O', 'B-COM': 'B-COM', 'I-COM': 'I-COM', 'L-COM': 'L-COM', 'B-PPL': 'B-PPL',
                'I-PPL': 'I-PPL', 'L-PPL': 'L-PPL', 'U-PPL': 'U-PPL', 'U-GPE': 'O', 'B-GPE': 'O', 'I-GPE': 'O',
                'L-GPE': 'O', 'B-GOV': 'O', 'L-GOV': 'O', 'I-GOV': 'O', 'U-ACA': 'O', 'B-ACA': 'O', 'L-ACA': 'O',
                'I-ACA': 'O', 'U-GOV': 'O'}

DIC_CONLL_SPACY = {'NNP': 'PROPN', 'VBZ': 'VERB', 'JJ': 'ADJ', 'NN': 'NOUN', 'TO': 'PART', 'VB': 'VERB', '.': 'PUNCT',
                   'CD': 'NUM', 'DT': 'DET', 'VBD': 'VERB', 'IN': 'ADP', 'PRP': 'PRON', 'NNS': 'PROPN', 'VBP': 'VERB',
                   'MD': 'VERB', 'VBN': 'VERB', 'POS': 'PART', 'JJR': 'ADJ', 'O': '##', 'RB': ' PART', ',': 'PUNCT',
                   'FW': 'X', 'CC': 'CONJ', 'WDT': 'ADJ', '(': 'PUNCT', ')': 'PUNCT', ':': 'PUNCT', 'PRP$': 'ADJ',
                   'RBR': 'ADV', 'VBG': 'VERB', 'EX': 'ADV', 'WP': 'NOUN', 'WRB': 'ADV', '$': 'SYM', 'RP': 'ADV',
                   'NNPS': 'PROPN', 'SYM': 'SYM', 'RBS': 'ADV', 'UH': 'INTJ', 'PDT': 'ADJ', "''": 'PUNCT',
                   'LS': 'PUNCT', 'JJS': 'ADJ', 'WP$': 'ADJ', 'NN|SYM': 'X'}

DIC_CONLL_CRF = {'U-ORG': 'U-COM', 'U-LOC': 'U-GPE', 'B-MISC': 'O', 'L-MISC': 'O', 'B-PER': 'B-PPL', 'L-PER': 'L-PPL',
                 'B-LOC': 'B-GPE', 'L-LOC': 'L-GPE', 'U-PER': 'U-PPL', 'U-MISC': 'O', 'I-MISC': 'O', 'B-ORG': 'B-COM',
                 'I-ORG': 'I-COM', 'L-ORG': 'L-COM', 'I-PER': 'I-PPL', 'I-LOC': 'I-GPE', 'O':'O'}


DIC_CONLL_CRF_ = {'U-ORG': 'U-COM', 'U-LOC': 'U-GPE', 'B-MISC': 'B-MISC', 'L-MISC': 'L-MISC', 'B-PER': 'B-PPL',
                  'L-PER': 'L-PPL','B-LOC': 'B-GPE', 'L-LOC': 'L-GPE', 'U-PER': 'U-PPL', 'U-MISC': 'U-MISC', 'I-MISC': 'I-MISC',
                  'B-ORG': 'B-COM','I-ORG': 'I-COM', 'L-ORG': 'L-COM', 'I-PER': 'I-PPL', 'I-LOC': 'I-GPE', 'O':'O'}

##############################################################################


def prepare_ans_dataset(in_file, out_file, col_list=LABEL_ANS):
    """
    :param in_file: an ANS json file
    :param col_list:
    :return: a df for gold parser to train
    """
    data = json2pd(in_file, col_list)
    data = rename_series(data, 'category', 'entity_types')
    data = rename_series(data, 'nname_en', 'entity_names')
    data['entity_names'] = data['entity_names'].str.title()
    data.to_csv(out_file, index=False)


def prepare_schweb_dataset(in_file, out_file):
    """
    :param in_file: schweb raw csv
    :param out_file: schweb csv
    """
    data = csv2pd(in_file, HEADER_SCHWEB, sep='\t')
    en_data = data[data.Language == 'en']
    result = en_data[en_data.Type.str.contains('Location|Personal|Organisation')]
    result['entity_type'] = np.where(result.Type.str.contains('Personal'), 'PERSON',
                                     np.where(result.Type.str.contains('Location'), 'GPE',
                                              np.where(result.Type.str.contains('Organisation'), 'ORG', 'MISC')))
    result = rename_series(result, 'Title', 'entity_name')
    result = result.drop(['Language', 'Type'], axis=1)
    result.to_csv(out_file, index=False)


##############################################################################


def output_factset_sn_type(type_file, sn_file, out_file):
    sn = quickest_read_csv(sn_file, HEADER_SN)
    ty = quickest_read_csv(type_file, HEADER_FS)
    result = pd.merge(ty, sn, on='factset_entity_id', how='inner')
    result = result.dropna()
    result.tocsv(out_file, index=False)


def remap_factset_sn_type(in_file, out_file):
    data = quickest_read_csv(in_file, HEADER_SN_TYPE)
    result = remap_series(data, 'entity_type', 'new_entity_type', LABEL_COMPANY, 'ORG')
    result = result.drop(['entity_type'], axis=1)
    result.to_csv(out_file, index=False)


def extract_factset_short_names(in_file, out_single, out_multi):
    data = quickest_read_csv(in_file, ['entity_proper_name', 'entity_type', 'factset_entity_id', 'short_name'])
    single_name = data[data.short_name.str.split(' ').apply(len) == 1]
    multi_name = data[data.short_name.str.split(' ').apply(len) > 1]
    single_name = single_name.drop(['entity_proper_name', 'entity_type', 'factset_entity_id'], axis=1)
    multi_name = multi_name.drop(['entity_proper_name', 'entity_type', 'factset_entity_id'], axis=1)
    single_name.to_csv(out_single, index=False)
    multi_name.to_csv(out_multi, index=False)


def extract_institute(institute_json, out_csv):
    grid = pd.read_json('/Users/acepor/Downloads/grid.json', orient='institutes')
    gg = [i['acronyms'] for i in grid['institutes'].values.tolist() if
          i['status'] != 'redirected' and i['status'] != 'obsolete']
    ii = sorted(list(set(i for j in gg for i in j if len(i.split()) == 1)))
    pd.DataFrame(ii).to_csv(out_csv, index=False, header=None)


##############################################################################


def output_tfidf(in_file, out_file, cols, col_name):
    """
    :param in_file: 
    :param out_file: 
    :param cols: a list of column names
    :param col_name: the specific column
    :return: 
    """
    out = open(out_file, 'w')
    data = json2pd(in_file, cols, lines=True)
    data = data[col_name].apply(remove_punc)
    tfidf = get_tfidf(data.tolist())
    for k, v in tfidf.items():
        if v > 1.0:
            out.write(k + ',' + str(v) + '\n')


def output_tfdf(in_file, out_file, cols, col_name):
    """
    :param in_file: 
    :param out_file: 
    :param cols: a list of column names
    :param col_name: the specific column
    :return: 
    """
    out = open(out_file, 'w')
    data = json2pd(in_file, cols, lines=True)
    data = data[col_name].apply(remove_punc)
    _, tfdf, _ = get_tfdf(data.tolist())
    for k, v in tfdf.items():
        if v > 1.0:
            out.write(k + ',' + str(v) + '\n')


def output_tfidf_zscore(in_file, out_file, cols, col_name):
    data = json2pd(in_file, cols, lines=True)
    data = data[col_name].apply(remove_punc)
    tfidf_dic = get_tfidf(data.tolist())
    tfidf_df = pd.DataFrame.from_dict(tfidf_dic, orient='index')
    tfidf_df.columns = ['tf_idf']
    tfidf_df['zscore'] = stats.mstats.zscore(tfidf_df['tf_idf'])
    tfidf_df['zvalue'] = tfidf_df['zscore'].apply(lambda x: 0 if x < 0 else 1)
    tfidf_df = tfidf_df.drop(['tf_idf', 'zscore'], axis=1)
    tfidf_df.to_csv(out_file, header=False)


def output_tfdf_zscore(in_file, out_file, cols, col_name):
    data = json2pd(in_file, cols, lines=True)
    data = data[col_name].apply(remove_punc)
    _, tfdf_dic, _ = get_tfdf(data.tolist())
    tfdf_df = pd.DataFrame.from_dict(tfdf_dic, orient='index')
    tfdf_df.columns = ['tf_idf']
    tfdf_df['zscore'] = stats.mstats.zscore(tfdf_df['tf_idf'])
    tfdf_df['zvalue'] = tfdf_df['zscore'].apply(lambda x: 0 if x < 0 else 1)
    tfdf_df = tfdf_df.drop(['tf_idf', 'zscore'], axis=1)
    tfdf_df.to_csv(out_file, header=False)


def titlefy_names(in_file, out_file):
    out = open(out_file, 'w')
    with open(in_file, 'r') as data:
        result = [line for line in data if len(line) > 2]
        result = [line.title() for line in result]
        for line in result:
            out.write(line)


def prepare_techcrunch(in_file, header, col):
    data = quickest_read_csv(in_file, header)
    data = data.dropna()
    data = clean_dataframe(data, [col], rpls={'\n': ' ', '\t': ' '})
    return data


def process_techcrunch(in_file, out_file, cols, pieces=10):
    data = json2pd(in_file, cols, lines=True)
    data = data.dropna()
    random_data = random_rows(data, pieces)
    parsed_data = spacy_batch_processing(random_data, '', 'content', ['content'], 'crf')
    parsed_data = reduce(add, parsed_data)
    pd.DataFrame(parsed_data, columns=['TOKEN', 'POS', 'NER']).to_csv(out_file, header=False, index=False)


##############################################################################


# Evaluation

def compare_difference(fixed_f, bug_f, out_f, fp_f, header, new_header):
    fixed = pd.read_csv(fixed_f, header=header, sep=',', engine='c', quoting=0)
    bug = pd.read_csv(bug_f, header=header, sep=',', engine='c', quoting=0)
    print('fixed: ', len(fixed), 'bug: ', len(bug))
    fixed.columns = new_header if header == None else header
    bug.columns = new_header if header == None else header
    merged = pd.concat([bug.Token, bug.NER, fixed.NER], axis=1)
    merged.columns = ['Token', 'bugged_NER', 'fixed_NER']
    difference = merged[merged['bugged_NER'] != merged['fixed_NER']]
    difference.to_csv(out_f, index=False)
    false_positive = difference[difference['fixed_NER'] == 'O']
    false_positive.to_csv(fp_f, index=False)


def get_distribution(in_f, out_f):
    tt = pd.read_csv(in_f, engine='c')
    tt.columns = HEADER_ANNOTATION
    tt = tt.groupby('NER').size().reset_index()
    tt.columns = ['NER', 'Count']
    tt['Percentage'] = np.round(tt.Count / sum(tt.Count) * 100, 3)
    tt.sort_values('Count', ascending=False).to_csv(out_f, index=False)


def extract_mutual(in_f1, in_f2, out_f1, out_f2):
    data1 = pd.read_csv(in_f1, engine='c', header=None)
    data2 = pd.read_csv(in_f2, engine='c', header=None)
    data1.columns = HEADER_EXTRACTED
    data2.columns = HEADER_EXTRACTED
    data1 = data1[data1['Token'].notnull()]
    data2 = data2[data2['Token'].notnull()]

    data1 = data1.drop(['POS'], axis=1)
    data2 = data2.drop(['POS'], axis=1)
    data1 = data1[data1['Token'].str.isalnum()]
    data2 = data2[data2['Token'].str.isalnum()]

    dd1 = data1.groupby(['Token', 'NER'])
    dd2 = data2.groupby(['Token', 'NER'])
    dd1 = dd1.sum().reset_index()
    dd2 = dd2.sum().reset_index()

    mutual = pd.DataFrame.merge(dd1, dd2, on=['Token'], how='inner')
    mutual['Ratio'] = mutual['Count_x'] / mutual['Count_y']
    mutual = mutual.sort_values('Ratio')
    mutual_tail = mutual[mutual['Ratio'] > mutual['Ratio'].quantile(0.75)]
    mutual_head = mutual[mutual['Ratio'] < mutual['Ratio'].quantile(0.25)]

    data1_exl = pd.DataFrame.merge(dd1, dd2, on=['Token'], how='left')
    data1_exl = data1_exl[data1_exl['Count_y'].isnull()]

    data2_exl = pd.DataFrame.merge(dd1, dd2, on=['Token'], how='right')
    data2_exl = data2_exl[data2_exl['Count_x'].isnull()]

    df_out1 = pd.concat([mutual_tail, data1_exl], axis=0)
    df_out1 = df_out1[df_out1['Count_x'] > df_out1['Count_x'].quantile(0.75)]
    df_out1 = pd.DataFrame(df_out1['Token'])

    df_out2 = pd.concat([mutual_head, data2_exl], axis=0)
    df_out2 = df_out2[df_out2['Count_y'] > df_out2['Count_y'].quantile(0.75)]
    df_out2 = pd.DataFrame(df_out2['Token'])

    df_out1.to_csv(out_f1, index=False, header=False)
    df_out2.to_csv(out_f2, index=False, header=False)


##############################################################################


def prepare_feature_hdf(output_f, hdf_kesys, *files, mode='a'):
    datas = [pd.read_csv(f, engine='c', quoting=0) for f in files]
    df2hdf(output_f, datas, hdf_kesys, mode)


##############################################################################


def extract_labeled_ner(text):
    """
    :param text: a long string
    :return:
    """
    ner_text = [i for i in spacy_parser(text, 'chk', '') if '||' in i]
    print('ner sentences:', len(ner_text))
    crf_texts = [extract_ner_from_sent(sent) for sent in ner_text]
    result =  [i + [('##END', 'O', '###')] for i in crf_texts]
    print('entity counts', (len([ner for  i in result for (token, ner, pos) in i if ner.startswith('B') or
                                 ner.startswith('I-')])))
    return result


def extract_ner_from_sent(entity_sent):
    """
    :param entity_sent: str, sentences containing entities
    :return: [(token, ner, pos)]
    """
    entity_sent = spacy_parser(entity_sent, 'txt', '')
    clean_list = [i.replace('||person', '').replace('||company', '').replace('|', '') for i in entity_sent]
    # remove NER tags
    ner_list = ['O' for i in range(len(entity_sent))]
    # add default tags

    begin_index = [i for (i, t) in enumerate(entity_sent) if t.startswith('||')]
    end_index = [i for (i, t) in enumerate(entity_sent) if ('|||') in t]  # may have a punc after '|||'

    ner_list = extract_entity(begin_index, end_index, ner_list, entity_sent, 'person', 'PPL')
    ner_list = extract_entity(begin_index, end_index, ner_list, entity_sent, 'company', 'COM')
    pos_text = spacy_parser(' '.join(clean_list), 'txt+pos', '')
    crf_text = ((m,) + n for m, n in zip(ner_list, pos_text))
    crf_text = [(b, a, c) for (a, b, c) in crf_text]
    return crf_text


def extract_entity(begin_index, end_index, ner_list, sent, end_mark='person', tag='PPL'):
    """
    :param begin_index: list, index of entity beginnings
    :param end_index: list, index of entity endings
    :param ner_list: list, list of ner tags
    :param sent: list, list of tokens
    :param end_mark: str, tag in the original text
    :param tag: str, end of ner tags
    :return: list, updated ner list
    """
    all_index = zip(begin_index, end_index)

    b_tag, i_tag, l_tag, u_tag = 'B-' + tag, 'I-' + tag, 'L-' + tag, 'U-' + tag
    entity_anchor = [i for (i, t) in enumerate(sent) if (end_mark + '|||') in t]
    # may have a punctuation after '|||'

    entity_index = [i for i in all_index if i[-1] in entity_anchor]
    for index in entity_index:
        if index[-1] - index[0] == 0:
            ner_list[index[0]] = u_tag
        elif index[-1] - index[0] == 1:
            ner_list[index[0]], ner_list[index[-1]] = b_tag, l_tag
        elif index[-1] - index[0] > 1:
            ner_list[index[0]], ner_list[index[-1]] = b_tag, l_tag
            for i in range(index[0] + 1, index[-1]):
                ner_list[i] = i_tag
    return ner_list


def pipeline_extract_nyt(in_f, start, end, out_f):
    df = pd.read_json(in_f)
    df.columns = ['text']
    tt = df.text.tolist()
    text = ' '.join(tt[start: end])
    result = extract_labeled_ner(text)
    result_df = pd.DataFrame([i for j in result for i in j])
    result_df.to_csv(out_f, index=False, header=None)


##############################################################################


def replalce_ner(in_file, out_file):
    df = pd.read_csv(in_file, engine='c', header=None)
    df.columns = HEADER_ANNOTATION
    df['NER'] = df['NER'].map(FULL_NER_DIC)
    df.to_csv(out_file, header=None, index=False)


##############################################################################


def convert_conll2bilou(in_f, out_f):
    df = pd.read_table(in_f, header=None, delimiter=' ', skip_blank_lines=False, skiprows=2)
    df.columns = ['TOKEN', 'POS', 'POS1', 'NER']
    df = df[df.TOKEN != '-DOCSTART-']
    tt = df[HEADER_ANNOTATION]
    tt['NER'] = tt['NER'].fillna('O')
    tt['TOKEN'] = tt['TOKEN'].fillna('##END')
    tt['POS'] = tt['POS'].fillna('NIL')
    tt['POS'] = tt['POS'].map(DIC_CONLL_SPACY)
    tt_list = [list(i) for i in zip(tt.TOKEN.tolist(), tt.NER.tolist(), tt.POS.tolist())]
    for i in range(len(tt_list)):
        if tt_list[i][1].startswith('B') and tt_list[i + 1][1].startswith('O'):
            tt_list[i][1] = tt_list[i][1].replace('B-', 'U-')
        elif tt_list[i][1].startswith('I') and tt_list[i + 1][1].startswith('O'):
            tt_list[i][1] = tt_list[i][1].replace('I-', 'L-')
    result = pd.DataFrame(tt_list)
    result.columns = HEADER_ANNOTATION
    result['NER'] = result['NER'].map(DIC_CONLL_CRF_)
    result['POS'] = result['POS'].fillna('###')
    result.to_csv(out_f, index=False, header=None)


##############################################################################


def extract_owler(owler_dir, out_f):
    file_dir = ['/'.join((owler_dir, f)) for f in os.listdir(owler_dir)]
    files = [pd.read_json(f, lines=True) for f in file_dir]
    df = pd.concat(files)
    companies = [i['company_details']['name'] for i in df['company_info'].tolist()]
    result = pd.DataFrame(list(set([i for i in companies if len(i.split()) == 1])))
    result.to_csv(out_f, index=False, header=None)


def swap_ner_pos(in_f):
    """
    swap the column of ner and pos
    :param in_f: [token, pos, ner]
    """
    df = pd.read_csv(in_f, engine='c', header=None)
    df.columns = ['TOKEN', 'POS', 'NER']
    df[['TOKEN', 'NER', 'POS']].to_csv(in_f, index=False, header=None)