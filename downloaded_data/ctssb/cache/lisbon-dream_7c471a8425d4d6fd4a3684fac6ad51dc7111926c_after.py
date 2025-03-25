from scipy import stats
import numpy as np

def _compare(predicted, gold):
    active = ~np.isnan(gold)
    return stats.spearmanr(predicted[active], gold[active])

def leave1out(learner, features, labels):
    '''
    avg_corr = leave1out(learner, features, labels)

    Perform leave-1-out cross-validation on cell types
    '''
    predicted = []
    for i in xrange(len(labels)):
        idx = np.ones(len(labels), bool)
        idx[i] = 0
        model = learner.train(features[idx], labels[idx])
        predicted.append(model.apply_one(features[i]))
    predicted = np.array(predicted)
    predicted = predicted.T

    corrs = []
    pvals = []
    for p in predicted:
        corr,ps = _compare(p, labels.T[i])
        corrs.append(corr)
        pvals.append(ps)
    return np.mean(corrs)
