__author__ = 'davidnola'



### Running Parameters

import ModelList
FINAL_VERIFY_PERCENT= .15


### Start
import multiprocessing as mp
import signal

import sklearn
import scipy.io
import glob
import numpy as np
import cPickle
import random
from multiprocessing import *
import itertools
from sklearn import *
from sklearn import ensemble
import operator



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

        num = iter(range(10000))
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
    for c in clips[:len(clips)/2]:
        if c.seizure:
            seizure_fit.append(1.0)
        else:
            seizure_fit.append(0.0)

    for c in clips[len(clips)/2:]:
        if c.seizure:
            seizure_cv.append(1.0)
        else:
            seizure_cv.append(0.0)

    return (seizure_fit, seizure_cv)




def fit_this(clf, fit, seizure_fit):
    #print "Starting fit..."
    clf.fit(fit, seizure_fit)
    #print "done!"
    return clf


def train_slave(clips):
    print "training slave"
    (seizure_fit, seizure_cv) = setup_validation_data(clips)
    models = []
    predictions = []
    metafeatures = []


    print clips[0].features.keys()
    for feat in clips[0].features.keys():

        algos = algorithms[:]


        for a in algos:
            print feat, a[0].__name__, a[1]
            clf = a[0](**a[1])


            #if 'variances' in feat:
            #    clf = linear_model.LogisticRegression(penalty = 'l1', C=.03)

            fit = []
            cv = []
            for c in clips[:len(clips)/2]:
                fit.append(c.features[feat])

            for c in clips[len(clips)/2:]:
                cv.append(c.features[feat])


            try:
                pool = mp.Pool(1)
                result = pool.apply_async(fit_this, (clf,fit,seizure_fit,))
                pool.close()

                clf = result.get(60)
                if clf.score(cv, seizure_cv) < .70:
                    print "BAD SCORE"
                    raise Exception
                models.append(clf)

                metafeatures.append((feat, clf))

            ###
                predict = clf.predict(cv)

                #print "Feature: ", feat, "Model: ", a[0].__name__,  " score: ", clf.score(cv, seizure_cv)
                TemporaryMetrics.model_titles.append(("Feature:\t%s ;" % feat).ljust(50)+("Model:\t%s ;" % a[0].__name__).ljust(40) + ("Score: %s " % round(clf.score(cv, seizure_cv),5)).ljust(25) + str(str(a[1])))

                #TemporaryMetrics.model_meta.append(("Feature:%s ;" % feat)+("Model:%s ;" % a[0].__name__) + str(a[1]))
                TemporaryMetrics.model_readable.append(("Feature:\t%s ;" % feat)+(" ; Model:%s ;" % a[0].__name__) + str(a[1]))
                TemporaryMetrics.model_short.append(("Model:%s ;" % a[0].__name__) + str(a[1]))

                predictions.append(predict)
            except mp.TimeoutError:
                #models.append(0)
                #predictions.append([0] * len(cv))


                #TemporaryMetrics.model_titles.append(("BROKEN Feature:\t%s ;" % feat).ljust(50)+("Model:\t%s ;" % a[0].__name__).ljust(40) + ("Score: BROKEN ").ljust(25) + str(str(a[1])))

                #TemporaryMetrics.model_meta.append(("Feature:%s ;" % feat)+("Model:%s ;" % a[0].__name__) + str(a[1]))

                #TemporaryMetrics.model_short.append(("BROKEN Model:%s ;" % a[0].__name__) + str(a[1]))
                print "TIMED OUT"
            except Exception as e:
                print "OTHER ERROR OCCURRED: ", e.message


    print "DONE training slave"
    return (predictions, seizure_cv, models ,metafeatures)
    #return (models, seizure_cv)


def train_master(predictions, seizure_cv, metafeatures):
    print "training master"
    feature_layer = []

    for i in range(len(predictions[0])): #for every .mat
        toadd = []
        for category in range(len(predictions)): #for every metafeature prediction set added to predictions
            toadd.append(predictions[category][i]) # add the corresponding prediction for that mat,  as guessed by that metafeature model
        feature_layer.append(toadd)

    #print seizure_cv
    #print feature_layer


    clf_layer = linear_model.LogisticRegression(penalty = 'l2', C= 1)



    clf_layer.fit(feature_layer, seizure_cv)

    cPickle.dump((TemporaryMetrics.model_short, clf_layer.coef_), open('scores.spkl', 'wb'))

    retry = False
    todel = []
    print clf_layer.coef_
    for i in range(len(clf_layer.coef_[0])):
        if clf_layer.coef_[0][i] < 0:
            todel.append(i)
            retry = True


    #############################################################################
    #REMOVE TO ENABLE PARING:
    retry = False
    #


    if retry:
        for index in sorted(todel, reverse=True):
            print "deleting: ", metafeatures[index][0],metafeatures[index][1].__class__.__name__ , clf_layer.coef_[0][index]
            del predictions[index]
            del metafeatures[index]
            del TemporaryMetrics.model_titles[index]
            del TemporaryMetrics.model_short[index]

        return train_master(predictions, seizure_cv, metafeatures)

    return clf_layer


def generate_test_layer(test_data, models, features, metafeatures):
    toret = []
    final = []
    formatted_data = []


    print test_data[0].features
    print features

    # for k in features:
    #     for a in algorithms:
    #         toadd = []
    #         for c in test_data:
    #             toadd.append(c.features[k])
    #         formatted_data.append(toadd)

    for feat, mod in metafeatures:
        toadd = []
        for c in test_data:
            toadd.append(c.features[feat])
        try:
            toret.append(mod.predict(toadd))
        except:
            toret.append([.5] * (len(toadd)))
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


    for t in range(len(test_data)):
        toadd = []

        for l in range(len(toret)):
            toadd.append(toret[l][t])

        final.append(toadd[:])
        #print toadd
        #print "next"


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


def analyze_dataset(clips, test_data, early=False):
    print "Begin analysis:   Training Data Size:", len(clips), "Final Test Data Size:", len(test_data)

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



    #print [c.seizure for c in clips[:-FINAL_VERIFY_SIZE]]

    #print seiz_count

    final_validate = clips[-FINAL_VERIFY_SIZE:]
    clips = clips[:-FINAL_VERIFY_SIZE]



    #EDITS GO HERE

    (predictions, seizure_cv, models, metafeatures) = train_slave(clips)
    print "before metafeatures: ", len(metafeatures)
    clf_layer = train_master(predictions, seizure_cv, metafeatures)
    print "after metafeatures: ", len(metafeatures)

    (final_feature_layer, metafeatures) = generate_test_layer(test_data, models, clips[0].features.keys(), metafeatures)

    #print "final metafeatures: ", len(metafeatures)



    final_predict = clf_layer.predict_proba(final_feature_layer)




    final_predict = [1.0-x[0] for x in final_predict]



    #print clf_layer.score(final_feature_layer, seizure_final)
    #print len(final_predict)
    #print final_predict

    #print "Coefficients: ", clf_layer.coef_


    (final_feature_layer_check, metafeatures) = generate_test_layer(final_validate, models, clips[0].features.keys(), metafeatures)
    final_validation_results = generate_validation_results(final_validate)
    print "SCORE: ", clf_layer.score(final_feature_layer_check, final_validation_results)


    from sklearn.metrics import roc_curve, auc
    fpr, tpr, thresholds = roc_curve(final_validation_results, clf_layer.predict_proba(final_feature_layer_check)[:, 1])
    roc_auc = auc(fpr, tpr)
    print "Area under the ROC curve : %f" % roc_auc

    TemporaryMetrics.feature_scores_raw.append(clf_layer.coef_)

    TemporaryMetrics.AUC_Mappings.append([len(clips)+FINAL_VERIFY_SIZE, roc_auc])




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
        first_predictions+= res


        redo.append((train, test, s))
        #pickle_dataset(s)
        print "Done"

        print len(train), len(test), len(names)

        cPickle.dump(zip(names,res), open(s+'_RESULTS.pkl', 'wb'))




    score = 0
    count = 0
    for x in TemporaryMetrics.AUC_Mappings:
        score += x[0] * x[1]
        count += x[0]

    final =  score/float(count)
    print final

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
    for i in range(16):
        p.append(Process(target=procc, args=(result_q,)))

    for proc in p:
        proc.start()

    for proc in p:
        proc.join()

    print "DONE"

    result_list = []
    for i in range(16):
        result_list.append(result_q.get())
    print result_list
    print np.mean(result_list)



def run_single():
    all_predictions = procc( Queue())
    #append_predictions(all_predictions)


if __name__ == '__main__':

    early_mode = False
    SUBJECTS = ['Dog_1','Dog_2','Dog_3','Dog_4','Patient_1','Patient_2','Patient_3','Patient_4','Patient_5','Patient_6','Patient_7','Patient_8']
    SUBJECTS = SUBJECTS[:]

    restart = False

    if restart == False:
        f = open('finalSubmit.csv', 'w')
        f.write("clip,seizure,early\n")
        f.close()

        f = open('finalSubmitSingle.csv', 'w')
        f.write("clip,seizure,early\n")
        f.close()

    FINAL_VERIFY_PERCENT= .15
    algorithms = ModelList.models_kitchen_sink
    #algorithms = ModelList.models_best
    #algorithms =  ModelList.models_small

    multi_proc_mode = False


    if multi_proc_mode:
        run_multi()
    else:
        run_single()

