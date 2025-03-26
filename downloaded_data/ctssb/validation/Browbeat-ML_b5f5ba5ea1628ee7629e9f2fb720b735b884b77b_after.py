import numpy
import cPickle


def classify_value(config, value, test_name, osp_version):
    predictors = numpy.array([0, 1, 2])
    osp_version_dic = reduce(lambda r, d: r.update(d) or r, config['osp_version_dic'], {})  # noqa
    test_name_dic = reduce(lambda r, d: r.update(d) or r, config['test_name_dic'], {})  # noqa
    predictors[0] = osp_version_dic[str(osp_version)]
    predictors[1] = test_name_dic[str(test_name)]
    predictors[2] = float(value)
    predictors.reshape(1, -1)
    with open('classifier/dumped_dtree.pkl', 'rb') as fid:
        clf = cPickle.load(fid)
    output_prediction = clf.predict([predictors])
    return output_prediction
