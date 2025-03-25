__author__ = 'davidnola'



### Running Parameters

import ModelList
FINAL_VERIFY_PERCENT= .30

import math
### Start
import multiprocessing as mp
import signal

import sklearn
import scipy.io
import glob
import numpy as np
import scipy as sp
import cPickle
import random
from multiprocessing import *
import itertools
from sklearn import *
from sklearn import ensemble
import operator
import MultilayerPerceptron
from VisiblePool import VisiblePool

SEED = 3737

random.seed(SEED)

class timeout:
    def __init__(self, seconds=1, error_message='Timeout'):
        self.seconds = seconds
        self.error_message = error_message
    def handle_timeout(self, signum, frame):
        print "TIMED OUT"
        raise TimeoutError(self.error_message)
    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)
    def __exit__(self, type, value, traceback):
        signal.alarm(0)

class TemporaryMetrics:
    AUC_Mappings = []
    feature_scores_raw = []
    model_titles=[]
    model_meta={}
    model_short=[]
    model_scores = {}
    feature_scores_dict = {}
    model_readable=[]

    @staticmethod
    def reset():
        TemporaryMetrics.AUC_Mappings = []
        TemporaryMetrics.feature_scores_raw = []
        TemporaryMetrics.model_titles=[]
        TemporaryMetrics.model_meta={}
        TemporaryMetrics.model_short=[]
        TemporaryMetrics.model_readable=[]
        TemporaryMetrics.model_scores = {}
        TemporaryMetrics.feature_scores_dict = {}

    @staticmethod
    def print_scores():
        i = itertools.cycle(TemporaryMetrics.model_titles)
        im = itertools.cycle(TemporaryMetrics.model_short)

        num = iter(xrange(10000))
        matrix = np.sum(TemporaryMetrics.feature_scores_raw, axis=0)
        matrix = matrix[0]/max(matrix[0])
        data_out = dict()

        for a in matrix:
            toprint =  str(num.next()).ljust(5)+"WEIGHT: ".ljust(10) + str(round(a, 5)).ljust(12)+ str(i.next()).ljust(10)
            data_out[toprint] = a
            model_name = im.next()
            if TemporaryMetrics.model_scores.has_key(model_name):
                TemporaryMetrics.model_scores[model_name] += a;
            else:
                TemporaryMetrics.model_scores[model_name] = a;

        sorted_x = sorted(data_out.iteritems(), key=operator.itemgetter(1))

        for x in sorted_x:
            print x[0]

        print "Model Scores: "
        sorted_x = sorted(TemporaryMetrics.model_scores.iteritems(), key=operator.itemgetter(1))

        for x in sorted_x:
            print x[0], x[1]

class EEGSegment:
    features = {
            # 'channel_variances': [],
            # 'channel_1sig_times_exceeded': [],
            # 'channel_2sig_times_exceeded': [],
            # 'channel_3sig_times_exceeded': [],
        }

    def __init__(self):
        self.name = ""
        self.data = []
        self.latency = -1
        self.seizure = False
        self.frequency = 0
        self.features = {
            # 'channel_variances': [],
            # 'channel_1sig_times_exceeded': [],
            # 'channel_2sig_times_exceeded': [],
            # 'channel_3sig_times_exceeded': [],
        }



    def segment_info(self, showdata=False):
        print "SEIZURE: " + str(self.seizure)
        print "LATENCY: " + str(self.latency)

        if showdata:
            print "DATA: "
            for l in self.data:
                print l
                print

        print "END\n"

    def calculate_features(self):


        self.features['channel_variances'] = []
        iter = 0
        for d in self.data:
            x = np.var(d)
            self.features['channel_variances'].append(x)


        cursig = 0
        for siglevel in ['channel_1sig_times_exceeded', 'channel_2sig_times_exceeded', 'channel_3sig_times_exceeded']:
            self.features[iter] = []
            cursig+=1
            iter = 0.0
            for d in self.data:
                iter += 1.0
                stddev = np.std(d)
                mean = np.mean(d)
                prior = d[0]
                exceeded = 0
                for x in d[1:]:
                    if prior < (cursig*stddev + mean) and x > (cursig*stddev + mean):
                        exceeded+=1
                    prior = x
                self.features[siglevel].append(exceeded)

        self.data = []
        print self.features

def run_analysis(clips, test_data, early=False):
    result = analyze_dataset(clips, test_data, early)
    names = []
    iter = 0
    final_text = ""
    final_text_single = ""
    print "Length comparison: ", len(result), len(test_data)
    for t in test_data:
        #print t.name, result[iter]
        if 'ictal' in t.name:
            print "BAD CLIP IN TEST DATA ", t.name
            exit(1)

        names.append(t.name)
        final_text+= t.name + ","+str(round(result[iter],5)) + ",\n"
        final_text_single+= t.name + ","+str(round(result[iter],5)) + ","+str(round(result[iter],5))+"\n"
        iter+=1


    for t in clips:
        #print t.name, result[iter]
        if 'test' in t.name:
            print "BAD CLIP IN TRAIN DATA ", t.name
            exit(1)


    #print final_text

    ######## RECCOMMENTTTTT     #######

    if multi_proc_mode:
        return

    if not early:
        f = open('finalSubmit.csv', 'a')
        f.write(final_text)
        f.close()

        f = open('finalSubmitSingle.csv', 'a')
        f.write(final_text_single)
        f.close()

    return (result, names)

def append_predictions(preds):
    print len(preds)
    preds = iter(preds)

    f = open('finalSubmit.csv', 'r')


    out = open('finalSubmitDual.csv', 'w')
    out.write("clip,seizure,early\n")
    out.close()
    out = open('finalSubmitDual.csv', 'a')

    print
    for line in f.readlines()[1:]:
        towrite = line[:-1] + str(round(preds.next(),5)) + "\n"
        #print towrite
        out.write(towrite)


    f.close()

    print "done appending"

def setup_validation_data(clips):
    seizure_fit = []
    seizure_cv = []
    for c in clips[::2]:
        if c.seizure:
            seizure_fit.append(1.0)
        else:
            seizure_fit.append(0.0)

    for c in clips[1::2]:
        if c.seizure:
            seizure_cv.append(1.0)
        else:
            seizure_cv.append(0.0)

    return (seizure_fit, seizure_cv)



def initialize_model_state(a):
    clf = None
    temp = None

    if not 'KNeighborsClassifier' in a[0].__name__ and not 'GradientBoostingClassifier' in a[0].__name__:
        try:
            temp = a[0](**a[1])
            clf = temp
        except:

            temp = a[0]()

        try:
            a[1]['random_state'] = SEED
            clf = a[0](**a[1])
        except:
            #print "failed to set state", a[0].__name__
            clf = temp
    else:
        clf = a[0](**a[1])

    return clf

def initialize_model_data(feat, a, clips):
    print "", feat, a[0].__name__, a[1]

    clf = initialize_model_state(a)
    fit = []
    cv = []
    cv_universal = []

    todel_fit = []
    counter = itertools.count()
    for c in clips[::2]:
        cur = counter.next()
        try:
            #print c.features.keys()
            #del c.features['universal_lower']
            fit.append(c.features[feat])
            #print "done"
        except:
            todel_fit.append(cur)

    todel_cv = []
    counter = itertools.count()
    for c in clips[1::2]:
        cur = counter.next()
        try:

            #del c.features['universal_lower']
            cv.append(c.features[feat])
            cv_universal.append(c.features['universal_lower'])
            #print "done"
        except:
            todel_cv.append(cur)


    #print len(fit), len(cv), len(cv_universal)
    return (clf, fit, cv, cv_universal, todel_fit, todel_cv)


def fit_this(clf, fit, seizure_fit, cv, feat):
    print "Starting fit..."

    #print len(fit), len(seizure_fit)
    clf.fit(fit, seizure_fit)
    #print "done!"
    return (clf, cv, feat)


def train_slave(clips, final_validate):
    global SEED
    SEED = 3737

    print "training slave"
    (seizure_fit, seizure_cv) = setup_validation_data(clips)
    models = []
    predictions = []
    metafeatures = []


    # print sorted(clips[0].features.keys())
    #
    keylist = sorted(clips[0].features.keys())
    # keylist.sort()
    keylist.sort(lambda x,y: cmp(len(x), len(y)))

    classifiers = []
    pool = mp.Pool(8)
    cv_universal = None
    for feat, a in itertools.product(keylist, algorithms[:]):
            if 'universal_lower' in feat:
                continue
            (clf, fit, cv, cv_universal, todel_fit, todel_cv) = initialize_model_data(feat, a, clips[:])

            if len(seizure_fit) > len(fit) or len(seizure_cv) > len(cv) :
                for t in reversed(todel_fit):
                    del seizure_fit[t]
                for t in reversed(todel_cv):
                    del seizure_cv[t]


            #print feat, a, len(cv)
            # try:
            #
            #     #result = pool.apply_async(fit_this, (clf,fit,seizure_fit,cv, feat,))
            #     result = fit_this(clf,fit,seizure_fit,cv, feat)
            #
            #     classifiers.append(result)
            # except mp.TimeoutError:
            #     print "TIMED OUT"
            #     #exit()
            # except Exception as e:
            #     print "OTHER ERROR OCCURRED: ", e.message


            result = fit_this(clf,fit,seizure_fit,cv, feat)

            classifiers.append(result)
    pool.close()
    print "Waiting for results..."

    while len(classifiers) > 0:

        todel = []
        for clf_idx in xrange(len(classifiers)):


            (clf, cv, feat) = (None,None, None)



            # try:
            #     (clf, cv, feat, cv_universal) = classifiers[clf_idx].get(False)
            #     print "READY: ", clf.__class__.__name__, " REMAINING: ", len(classifiers)-1
            #
            # except Exception as e:
            #     #print e
            #     continue
            #
            #
            # (clf, cv, feat, cv_universal) = fit_this(clf,fit,seizure_fit,cv, feat,cv_universal)
            result = iter(classifiers[:])
            (clf, cv, feat) = result.next()

            #print "cvlen" , len(cv)

            models.append(clf)

            predict = None
            try:
                predict = clf.predict_proba(cv)
                predict = [1.0-x[0] for x in predict]
                #print "predict", predict
            except Exception as e:
                #print e.message
                predict = clf.predict(cv)


            #print "lenpred", len(predict), len(cv)

            final_feats = []
            final_seiz = []
            for f in final_validate:
                final_feats.append(f.features[feat])
                final_seiz.append(f.seizure)

            print "Independent AUC", score_model(final_seiz, final_feats, clf)

            metafeatures.append((feat, clf))
            predictions.append(predict)

            todel.append(clf_idx)

        for d in reversed(sorted(todel)):
            del classifiers[d]


    (toret_pred, toret_meta, score_list, auc_list) = generate_best_first_layer(predictions,metafeatures, seizure_cv, final_validate, cv_universal)


    #print toret_meta
    print "DONE training slave, results: "
    #print len(cv_universal)
    count = itertools.count()
    scs = iter(score_list)
    aucs = iter(auc_list)
    for m in toret_meta:
        nn = str(m[0])+": "+str(m[1].__class__.__name__)
        print count.next(), ":", nn, "Score:", scs.next(), "AUC:", aucs.next()
    return (toret_pred, seizure_cv, models ,toret_meta, cv_universal)
    #return (models, seizure_cv)

def generate_best_first_layer(predictions,metafeatures, seizure_cv, final_validate, cv_universal):
    print "Choosing best metafeatures for first layer"
    toret_meta = []
    toret_pred = []
    score_list = []
    auc_list=[]
    best_sc = 0
    best_auc = 0
    for x in xrange(len(predictions)):
        print "Model Number: ", x
        best_meta=None
        best_pred=None
        pred_iter = iter(predictions[:])

        #print "bfuni", len(cv_universal)

        meta_results = []

        pool = mp.Pool(16)
        for meta in metafeatures:
            #print "RESULTS THIS RUN:"
            (meta_name, meta_model) = meta
            print "meta", meta_name, meta_model.__class__.__name__
            pred = pred_iter.next()

            toret_pred.append(pred[:])
            toret_meta.append((meta_name, meta_model))
            #print toret_meta


            result = pool.apply_async(calc_results, (toret_pred[:],seizure_cv[:],toret_meta[:],final_validate[:], meta_model, meta_name, pred[:],cv_universal[:], ))
            # result = calc_results(toret_pred[:],seizure_cv[:],toret_meta[:],final_validate[:],meta_model, meta_name, pred[:], cv_universal[:])

            meta_results.append(result)

            toret_pred.pop()
            toret_meta.pop()
        pool.close()

        while len(meta_results) > 0:
            todel = []
            for result_idx in xrange(len(meta_results)):

                (sc, auc, name, meta_model, meta_name, pred, best_feats) = (None, None, None, None, None, None, None)


                #print len(meta_results), result_idx

                try:
                    r = meta_results[result_idx]
                    #print r
                    (sc, auc, name, meta_model, meta_name, pred, best_feats) = r.get(False)
                except Exception as e:
                    #print "gen first"
                    if len(str(e))>5:
                        print e
                    #print "not ready"
                    continue

                # r = meta_results[result_idx]
                # #
                # (sc, auc, name, meta_model, meta_name, pred, best_feats) = r

                #print "predout", len(pred)

                print "OBTAINED RESULTS:", meta_model.__class__.__name__, "REMAINING: ", len(meta_results)-1, "AUC:", auc

                if (auc > best_auc*1.01) or (auc>best_auc and sc > best_sc * .80) or (auc==best_auc and sc>best_sc):
                    print "NEW BEST:", meta_name, sc, auc
                    best_sc = sc
                    best_auc = auc
                    best_meta = (meta_name, meta_model)
                    best_pred = pred

                todel.append(result_idx)

            for d in reversed(sorted(todel)):
                del meta_results[d]


        if best_meta!=None:
            score_list.append(best_sc)
            auc_list.append(best_auc)
            nn = str(best_meta[0])+": "+str(best_meta[1].__class__.__name__)
            for i in xrange(len(predictions)):

                cur = str(metafeatures[i][0])+": "+str(metafeatures[i][1].__class__.__name__)
                #print nn, cur

                if nn==cur:
                    del metafeatures[i]
                    del predictions[i]
                    break
            toret_meta.append(best_meta)
            toret_pred.append(best_pred)
            print "top ",x , " : ", nn, "sc", best_sc, "auc", best_auc
            print len(metafeatures)

        if best_meta == None:
            break

    print "Done choosing metafeatures"
    return (toret_pred, toret_meta, score_list, auc_list)

def calc_results(predictions, seizure_cv, metafeatures, final_validate, meta_model, meta_name, pred, cv_universal):

    (clf_layer, clf_layer_lin, best_feats) = train_master(predictions, seizure_cv, generate_test_layer(final_validate, metafeatures)[0], [s.seizure for s in final_validate], cv_universal)

    return final_score(final_validate, clf_layer, metafeatures, best_feats) + (meta_model,) + (meta_name,) +(pred,)+ (best_feats,)


def calculate_similarities(ft):
    meta = iter(TemporaryMetrics.model_readable)
    values = iter(ft)
    for mf in meta:
        print mf
        v = values.next()
        ot_meta = iter(TemporaryMetrics.model_readable)
        ot_values = iter(ft)
        for otv in ot_values:
            diff = np.linalg.norm(np.asarray(v)-np.asarray(otv))
            print "\t", ot_meta.next(), diff

def reduce_feature_space(f, best):
    return f
    for fi in xrange(len(f)):
        v = f[fi]
        v = [ x if isinstance(x, (float,int,long)) else 0 for x in v]
        f[fi] = [np.max(v), np.min(v), np.mean(v), np.var(v), np.std(v), sp.stats.skew(v), sp.stats.kurtosis(v)]

        try:
            for b in best:
                f[fi].append(v[b])
        except:
            pass


        #print f[fi]
    return f

def organize_master_data(predictions, seizure_cv, cv_universal):
    feature_layer = []

    #print "org mast", len(predictions[0]), len(cv_universal)

    for i in xrange(len(predictions[0])): #for every .mat
        toadd = []
        for category in xrange(len(predictions)): #for every metafeature prediction set added to predictions
            v = predictions[category][i]
            #print "v", v
            if not math.isnan(v):
                toadd.append(v) # add the corresponding prediction for that mat,  as guessed by that metafeature model
            else:
                toadd.append(0)


        #print toadd
        feature_layer.append(toadd)

    #print "here", len(feature_layer), len(cv_universal)

    for x in xrange(len(feature_layer)):
        feature_layer[x]+=cv_universal[x]
    #print seizure_cv
    #print feature_layer

    for fi in xrange(len(feature_layer)):
        v = feature_layer[fi]
        v = [ x if isinstance(x, (float,int,long)) else 0 for x in v]
        feature_layer[fi] = v

    num_valid = int(-(.2*len(feature_layer)))
    feature_layer_valid = feature_layer[-num_valid:]
    feature_layer_train = feature_layer[:-num_valid]
    seizure_cv_valid = seizure_cv[-num_valid:]
    seizure_cv_train = seizure_cv[:-num_valid]


    return ( feature_layer_train, seizure_cv_train)


def run_master_proc(clf_layer, feature_layer_train, seizure_cv_train):
    clf_layer.fit(feature_layer_train, seizure_cv_train)
    return clf_layer

def train_master(predictions, seizure_cv, final_validate_layer, final_validate_actual, cv_universal):


    print "training master"
    ( feature_layer_train, seizure_cv_train) = organize_master_data(predictions[:], seizure_cv, cv_universal)

    clf_layer_lin = sklearn.ensemble.RandomForestClassifier(n_estimators=100, random_state=SEED)
    clf_layer_lin.fit(feature_layer_train, seizure_cv_train)


    #print "importances", clf_layer_lin.feature_importances_
    best_feats = np.argsort(clf_layer_lin.feature_importances_)[:]
    #print "best feats", best_feats




    clf_layer = None
    best = 0

    possible_master_results = []
    master_algos = algorithms[:]



    #feature_layer_valid = reduce_feature_space(feature_layer_valid[:], best_feats[:])
    feature_layer_train = reduce_feature_space(feature_layer_train[:], best_feats[:])

    #print master_algos
    #pool = mp.Pool(8)
    for a in master_algos:
        clf = None
        temp = None

        clf = initialize_model_state(a)

        temp = clf_layer

        clf_layer = clf




        #result = pool.apply_async(run_master_proc, (clf_layer, feature_layer_train, seizure_cv_train,))
        result = run_master_proc(clf_layer, feature_layer_train, seizure_cv_train)

        possible_master_results.append(result)





    print "\tWAIT for masters to train..."

    #pool.close()
    best_clf = None
    while len(possible_master_results)>0:
        todel = []
        for i in xrange(len(possible_master_results)):
            try:
                clf_layer = possible_master_results[i]#.get(False)
            except Exception as e:
                if len(str(e))>5:
                    print e
                #print "not ready"
                continue

            #print "TOP READY: ", clf_layer.__class__.__name__, "REMAINING: ", len(possible_master_results)-1
            #score = clf_layer.score(feature_layer_valid, seizure_cv_valid)



            score = score_model(final_validate_actual, final_validate_layer, clf_layer)

            #print "Current master: ", score, clf_layer.__class__.__name__
            if score>best:
                #print "New best master: ", score, a[0].__name__, a[1]
                best_clf = clf_layer
                best=score

            todel.append(i)
        for d in reversed(sorted(todel)):
            del possible_master_results[d]



    #cPickle.dump((TemporaryMetrics.model_readable, clf_layer_lin.feature_importances_), open('scores.spkl', 'wb'))

    print  "\tDONE - BEST MASTER:", best_clf.__class__, "AUC Score:", best, best_clf.get_params()
    print
    retry = False
    todel = []
    #print clf_layer_lin.feature_importances_
    for i in xrange(len(clf_layer_lin.feature_importances_)):
        if clf_layer_lin.feature_importances_[i] < 0:
            todel.append(i)
            retry = True


    return (best_clf, clf_layer_lin, best_feats)

def generate_test_layer(test_data, metafeatures):
    toret = []
    final = []
    formatted_data = []


    #print test_data[0].features
    #print features

    # for k in features:
    #     for a in algorithms:
    #         toadd = []
    #         for c in test_data:
    #             toadd.append(c.features[k])
    #         formatted_data.append(toadd)

    for feat,mod in metafeatures:
        toadd = []
        for c in test_data:
            toadd.append(c.features[feat])


        try:
            try:
                toret.append([a[1] for a in mod.predict_proba(toadd)])
            except:
                toret.append(mod.predict(toadd))
        except Exception as e:
            toret.append([.5] * (len(toadd)))
            print feat, len(c.features[feat])
            print e.message
            print "FAILURE: Couldn't apply model to test data"


    # i = 0
    # for m in models:
    #     if m==0:
    #
    #         toret.append([0] * len(formatted_data[i]))
    #         i+=1
    #         continue
    #
    #     toret.append(m.predict(formatted_data[i]))
    #     i+=1


    for t in xrange(len(test_data)):
        toadd = []

        for l in xrange(len(toret)):
            toadd.append(toret[l][t])

        final.append(toadd[:])
        #print toadd
        #print "next"

    uni_iter = iter(test_data)
    for f in final:
        cur = uni_iter.next()
        #print cur.features.keys()
        f+=cur.features['universal_lower']
    #for f in final:
    #    print f
    return (final, metafeatures)

def generate_validation_results(data):
    toret = []
    for d in data:
        if d.seizure:
            toret.append(1)
        else:
            toret.append(0)
    return toret

def final_score(final_validate, clf_layer, metafeatures, best_feats):
    (final_feature_layer_check, metafeatures) = generate_test_layer(final_validate, metafeatures)
    final_feature_layer_check = reduce_feature_space(final_feature_layer_check, best_feats)

    final_validation_results = generate_validation_results(final_validate)

    #print "OLD SCORE: ", clf_layer_lin.score(final_feature_layer_check, final_validation_results)

    sc = clf_layer.score(final_feature_layer_check, final_validation_results)
    #print "SCORE: ", sc

    return (sc, score_model(final_validation_results, final_feature_layer_check, clf_layer), clf_layer.__class__.__name__)

def score_model(actual, feature_set, clf_layer):
    from sklearn.metrics import roc_curve, auc
    fpr, tpr, thresholds = None, None, None
    try:
        fpr, tpr, thresholds = roc_curve(actual, clf_layer.predict_proba(feature_set)[:, 1])
    except:
        fpr, tpr, thresholds = roc_curve(actual, clf_layer.predict(feature_set))
    roc_auc = auc(fpr, tpr)
    #print "Area under the ROC curve : %f" % roc_auc

    return roc_auc

def analyze_dataset(clips, test_data, early=False):
    print "Begin analysis:   Training Data Size:", len(clips), "Final Test Data Size:", len(test_data)

    import time

    start = time.time()

    final_clips = []
    sorter = []
    for c in clips:
        if c.latency<0:
            continue
        toadd = int(c.name[c.name.rfind('_')+1:-4])
        sorter.append((c, toadd))

    curlat = -1
    unique_clips = []
    for s in sorted(sorter, key=operator.itemgetter(1)):
        s = s[0]
        #print s.name
        if s.latency > curlat:
            curlat = s.latency
            unique_clips.append(s)
            #print curlat, s.name
        else:
            break

    todel = []
    for i in xrange(len(clips)):
        if clips[i] in unique_clips:
            #print i, "deleted"
            todel.append(i)

    for i in reversed(todel):
        del clips[i]

    if early:
        for c in clips:
            c.seizure = c.seizure_early



    FINAL_VERIFY_SIZE = int(FINAL_VERIFY_PERCENT * len(clips))

    random.shuffle(clips)
    random.shuffle(test_data)


    seiz_count = 0
    while seiz_count < 5:
        seiz_count = 0
        random.shuffle(clips)
        for ix in clips[-FINAL_VERIFY_SIZE:]:
            if ix.seizure:
                seiz_count+=1


    final_validate = clips[-FINAL_VERIFY_SIZE:] + unique_clips
    clips = clips[:-FINAL_VERIFY_SIZE]



        #del c.features['universal_lower']

    (predictions, seizure_cv, models, metafeatures, cv_universal) = train_slave(clips, final_validate)
    print "before metafeatures: ", len(metafeatures)




    (clf_layer, clf_layer_lin, best_feats) = train_master(predictions, seizure_cv, generate_test_layer(final_validate, metafeatures)[0], [s.seizure for s in final_validate], cv_universal)
    print "after metafeatures: ", len(metafeatures)

    (final_feature_layer, metafeatures) = generate_test_layer(test_data, metafeatures)


    final_feature_layer = reduce_feature_space(final_feature_layer, best_feats)

    final_predict = None
    try:
        final_predict = clf_layer.predict_proba(final_feature_layer)
        final_predict = [1.0-x[0] for x in final_predict]
    except:
        final_predict = clf_layer.predict(final_feature_layer)

    (sc, auc, name) = final_score(final_validate, clf_layer, metafeatures, best_feats)

    end = time.time()

    elapsed = end - start
    print "ELAPSED TIME:", elapsed
    return final_predict

def procc(result_q):
    first_predictions = []
    all_predictions=[]


    redo = []


    for s in SUBJECTS[:]:
        print "Starting: "+s
        test = cPickle.load(open("SummerResearchData/"+s+'_TEST.pkl', 'rb'))
        train = cPickle.load(open("SummerResearchData/"+s+'.pkl', 'rb'))
        (res, names) = run_analysis(train, test)
        first_predictions+= list(res)


        redo.append((train, test, s))
        #pickle_dataset(s)
        print "Done"


        print len(train), len(test), len(names)

        cPickle.dump(zip(names,res), open(s+'_RESULTS.pkl', 'wb'))



    final = 0
    # score = 0
    # count = 0
    # for x in TemporaryMetrics.AUC_Mappings:
    #     score += x[0] * x[1]
    #     count += x[0]
    #
    # final =  score/float(count)
    # print final

    #TemporaryMetrics.print_scores()



    if early_mode:

        TemporaryMetrics.reset()



        for (train, test, s) in redo:
            print "\n\n\nStarting EARLY: " + s
            (res, names) = run_analysis(train, test, early=True)
            all_predictions+=res

        #TemporaryMetrics.print_scores()

        for x in TemporaryMetrics.AUC_Mappings:
            score += x[0] * x[1]
            count += x[0]

        final_e =  score/float(count)
        print final_e

        summed = (final+final_e)/2.0

        print "Summed score: ", summed

        result_q.put(summed)
    else:
        result_q.put(final)
    return all_predictions

def run_multi():
    result_q = Queue()

    #readability_q.put("http://www.bbc.com/news/world-europe-26598832")
    # p2 = Process(target=twit, args=(input,))
    # p2.start()
    p = []
    for i in xrange(16):
        p.append(Process(target=procc, args=(result_q,)))

    for proc in p:
        proc.start()

    for proc in p:
        proc.join()

    print "DONE"

    result_list = []
    for i in xrange(16):
        result_list.append(result_q.get())
    print result_list
    print np.mean(result_list)

def run_single():
    all_predictions = procc( Queue())
    #append_predictions(all_predictions)


if __name__ == '__main__':

    early_mode = False
    SUBJECTS = ['Dog_1','Dog_2','Dog_3','Dog_4','Patient_1','Patient_2','Patient_3','Patient_4','Patient_5','Patient_6','Patient_7','Patient_8']
    SUBJECTS = SUBJECTS[1:2]

    restart = False

    if restart == False:
        f = open('finalSubmit.csv', 'w')
        f.write("clip,seizure,early\n")
        f.close()

        f = open('finalSubmitSingle.csv', 'w')
        f.write("clip,seizure,early\n")
        f.close()

    FINAL_VERIFY_PERCENT= .30
    #algorithms = ModelList.models_MLP
    #algorithms = ModelList.models_best


    #algorithms = ModelList.models_new_short
    algorithms =  ModelList.models_small
    #algorithms =  ModelList.models_micro

    multi_proc_mode = False


    if multi_proc_mode:
        run_multi()
    else:
        run_single()

