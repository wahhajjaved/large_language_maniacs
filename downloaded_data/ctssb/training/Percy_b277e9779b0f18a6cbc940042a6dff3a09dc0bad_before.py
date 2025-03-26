from flask import Flask, render_template, request
from gensim.models import Doc2Vec
from gensim.summarization import keywords as KW
from nltk.tokenize import sent_tokenize
from nltk.stem.porter import PorterStemmer
import re
import pickle
from nltk.classify.decisiontree import DecisionTreeClassifier
import math
# model = Doc2Vec.load(r"C:\Users\estasney\PycharmProjects\webwork\home\estasney\mysite\mymodel.model")

# for web

model = Doc2Vec.load('/home/estasney/mysite/mymodel.model')


app = Flask(__name__)


@app.route('/')
def hello_world():
    return render_template('home_page.html')


@app.route('/stemmed')
def stemmed():
    return render_template('stemmed.html')


@app.route('/keywords')
def keywords():
    return render_template('keywords.html')


@app.route('/related')
def related():
    return render_template('related.html')


@app.route('/thisplusthat')
def thisplusthat():
    return render_template('thisplusthat.html')

@app.route('/infer')
def infer():
    return render_template('infer.html')


@app.route('/', methods=['POST'])
def my_sims():
    if request.form['button'] == 'query':  # similar words search
        user_query = request.form['query'].lower()
        try:
            result = dict(model.similar_by_word(user_query))
            return render_template('related.html', result=result, success='True', title_h2='Word Similarity Score', title_th='Similarity Score', original=user_query)
        except KeyError as error:
            error_message = str(error)
            offending_term = error_message.split("'")[1]
            result = offending_term.title()
            return render_template('related.html', result=result, success='False')
    elif request.form['button'] == 'math':
        word_one = request.form['word1'].lower()
        word_two = request.form['word2'].lower()
        word_three = request.form['word3'].lower()
        try:
            if word_three == '':
                user_equation = word_one.title() + " + " + word_two.title() + " = "
                result = dict(model.most_similar(positive=[word_one, word_two]))
            else:
                user_equation = word_one.title() + " + " + word_two.title() + " - " + word_three.title() + " = "
                result = dict(model.most_similar(positive=[word_one, word_two], negative=[word_three]))
            return render_template('thisplusthat.html', result=result, success='True', user_equation=user_equation, word_one=word_one.strip(), word_two=word_two.strip(), word_three=word_three.strip())
        except KeyError as error:
            error_message = str(error)
            offending_term = error_message.split("'")[1]
            result = offending_term.title()
            return render_template('thisplusthat.html', result=result, success='False')
    elif request.form['button'] == 'keywords':
        try:
            raw_text = str(request.form['raw_text'])
            raw_text = ' '.join([word for word in raw_text.split()])
            sentences = sent_tokenize(raw_text)
            sentence_keywords = []
            for sentence in sentences:
                try:
                    sent_keyw = KW(sentence)
                    if len(sent_keyw) > 0:
                        sent_keyw = sent_keyw.splitlines()
                        if len(sent_keyw) > 1:
                            sent_keyw = ', '.join([word for word in sent_keyw if len(sent_keyw) > 1])
                        else:
                            sent_keyw = ' '.join([word for word in sent_keyw])
                        sentence_keywords.append(sent_keyw)
                except:
                    pass
            user_keywords = sentence_keywords
            return render_template('keywords.html', keywords=user_keywords, success='True', original=raw_text)
        except:
            return render_template('keywords.html', success='False')
    elif request.form['button'] == 'raw_stem':
        stemmer = PorterStemmer()
        bool_logic = ["OR", "AND", "NOT"]
        re_words = re.compile(r"(\w+)")
        search = request.form['raw_stem']
        terms = search.split()
        mod_terms = []
        for term in terms:
            if term in bool_logic:
                mod_terms.append(term)
                continue
            word_matches = re_words.findall(term)
            word = ' '.join(word_matches)  # List to string
            other_char = term.replace(word, "")
            stem_word = stemmer.stem(word)
            if stem_word == word:
                pass
            else:
                stem_word = stem_word + "*"

            if len(other_char) == 0:  # Is a operator present?
                mod_terms.append(stem_word)
                continue
            char_position = term.find(other_char)
            if char_position == 0:
                full_term = other_char + stem_word
            else:
                full_term = stem_word + other_char
            mod_terms.append(full_term)
        stemmed_bool = ' '.join(mod_terms)
        return render_template('stemmed.html', stemmed_bool=stemmed_bool, success='True', original=search)
    elif request.form['button'] == 'infer_name':
        f = open("/home/estasney/mysite/tree_classifier.pickle", "rb")
        # f = open(r"C:\Users\estasney\IPython Books\Diversity Notebooks\names\Models\tree_classifier.pickle", "rb")
        tree_model = pickle.load(f)
        f.close()
        fp = open('home/estasney/mysite/name_dict.pickle', "rb")
        # fp = open(r"C:\Users\estasney\IPython Books\Diversity Notebooks\names\Models\name_dict.pickle", "rb")
        name_dict = pickle.load(fp)
        fp.close()
        user_query_name = request.form['infer_name']
        inferred_gender = tree_model.classify(gender_features(user_query_name)).title()
        gender_lookup = retrieve_name(user_query_name, name_dict)[1]  #Selecting the message
        return render_template('infer.html', user_query=user_query_name, success='True', gender_guess=inferred_gender,
                               lookup_message = gender_lookup)


def gender_features(name):
    name = name.lower()
    features = {}
    features['first_two'] = name[:2]
    features['last_letter'] = name[-1]
    features['last_letter_vowel'] = vowel_test(name[-1])
    features['last_two'] = name[-2:]
    return features


def vowel_test(letter):
    vowels = ["a", "e", "i", "o", "u", "y"]
    if letter in vowels:
        return "Yes"
    else:
        return "No"

def retrieve_name(name, name_dict):
    name = name.lower()
    try:
        male_count = name_dict[name]['M']
        female_count = name_dict[name]['F']
        if male_count > female_count:
            try:
                likely = round(male_count / female_count, 1)
                if math.isinf(likely):
                    message = "The name {} is only known to be male".format(name.title())
                    winner = ('M', 999)
                else:
                    message = "The name {} is {}x more likely to be male".format(name.title(), likely)
                    winner = ('M', likely)
            except ZeroDivisionError:
                message = "The name {} is only known to be male"
                winner = ('M', 999)
        elif male_count < female_count:
            try:
                likely = round(female_count / male_count, 1)
                if math.isinf(likely):
                    message = "The name {} is only known to be female".format(name.title())
                    winner = ('F', 999)
                else:
                    message = "The name {} is {}x more likely to be female".format(name.title(), likely)
                    winner = ('F', likely)
            except ZeroDivisionError:
                message = "The name {} is only known to be female"
                winner = ('F', 999)
        return winner, message
    except KeyError:
        print("I have not see the name {} before".format(name.title()))
        return False










if __name__ == '__main__':
    app.run()
