
import time
import pickle
import numpy as np
from workshops.lib.classif import get_train_test
from workshops.lib.weights import l2_norm_sparse
from workshops.lib.features import get_tf_idf
from sklearn.neighbors import KNeighborsClassifier
from proj2.lib.knn.brute import KNeighborsBrute
from proj2.lib.knn.pat import PrincipalAxisTree
from proj2.lib.knn.vpt import VPTree

def main():
    with open('data/pickle/lyrl.db', 'rb') as docs_sr, open('data/pickle/lyrl_classif.db', 'rb') as classif_sr:
        # noinspection PyArgumentList
        docs_data = pickle.load(docs_sr)
        # noinspection PyArgumentList
        tf_idfs = l2_norm_sparse(get_tf_idf(docs_data.freq_matrix))
        train_indexes, test_indexes = get_train_test(len(docs_data.docs), 2000, 500)
        train_X = tf_idfs[train_indexes]
        test_X = tf_idfs[test_indexes]

        k = 1
        leaf_size = 30

        start = time.clock()
        tree = PrincipalAxisTree(leaf_size)
        tree.fit(train_X)
        print('Tree construction took {} s'.format(time.clock() - start))
        start = time.clock()
        res = tree.search(test_X[0], k)
        print('Search took {} s'.format(time.clock() - start))
        print('Traversed {} nodes'.format(tree.n_traversed))
        print(res)

        start = time.clock()
        tree = VPTree(lambda x, y: np.sum(np.power((x - y).data, 2)))
        tree.fit(train_X)
        print('Tree construction took {} s'.format(time.clock() - start))
        start = time.clock()
        res = tree.search(test_X[0], k)
        print('Search took {} s'.format(time.clock() - start))
        print('Traversed {} nodes'.format(tree.n_traversed))
        print(res)

        tree = KNeighborsClassifier(k, leaf_size=leaf_size)
        tree.fit(train_X, np.zeros(train_X.shape[0]))
        start = time.clock()
        res = tree.kneighbors(test_X[0], k)
        res = list(zip(res[0][0], res[1][0]))
        print('Search took {} s'.format(time.clock() - start))
        print(res)

        # to be fair, don't assume normalized
        tree = KNeighborsBrute()
        tree.fit(train_X)
        start = time.clock()
        res = tree.kneighbors(test_X[0], k)
        print('Search took {} s'.format(time.clock() - start))
        print(res)

if __name__ == '__main__':
    main()
