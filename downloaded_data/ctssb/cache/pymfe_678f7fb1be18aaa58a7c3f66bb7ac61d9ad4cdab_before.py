"""Module dedicated to extraction of Complexity Metafeatures."""

import typing as t
import itertools
import numpy as np
from scipy.spatial import distance
from scipy.sparse.csgraph import minimum_spanning_tree
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler
from sklearn.neighbors import KNeighborsClassifier
from sklearn.decomposition import PCA
from pymfe.general import MFEGeneral


class MFEConcept:
    """Keep methods for metafeatures of ``Concept Characterization`` group.

    The convention adopted for metafeature extraction related methods is to
    always start with ``ft_`` prefix to allow automatic method detection. This
    prefix is predefined within ``_internal`` module.

    All method signature follows the conventions and restrictions listed below:

    1. For independent attribute data, ``X`` means ``every type of attribute``,
       ``N`` means ``Numeric attributes only`` and ``C`` stands for
       ``Categorical attributes only``. It is important to note that the
       categorical attribute sets between ``X`` and ``C`` and the numerical
       attribute sets between ``X`` and ``N`` may differ due to data
       transformations, performed while fitting data into MFE model,
       enabled by, respectively, ``transform_num`` and ``transform_cat``
       arguments from ``fit`` (MFE method).

    2. Only arguments in MFE ``_custom_args_ft`` attribute (set up inside
       ``fit`` method) are allowed to be required method arguments. All other
       arguments must be strictly optional (i.e., has a predefined default
       value).

    3. The initial assumption is that the user can change any optional
       argument, without any previous verification of argument value or its
       type, via kwargs argument of ``extract`` method of MFE class.

    4. The return value of all feature extraction methods should be a single
       value or a generic Sequence (preferably a :obj:`np.ndarray`) type with
       numeric values.

    There is another type of method adopted for automatic detection. It is
    adopted the prefix ``precompute_`` for automatic detection of these
    methods. These methods run while fitting some data into an MFE model
    automatically, and their objective is to precompute some common value
    shared between more than one feature extraction method. This strategy is a
    trade-off between more system memory consumption and speeds up of feature
    extraction. Their return value must always be a dictionary whose keys are
    possible extra arguments for both feature extraction methods and other
    precomputation methods. Note that there is a share of precomputed values
    between all valid feature-extraction modules (e.g., ``class_freqs``
    computed in module ``statistical`` can freely be used for any
    precomputation or feature extraction method of module ``landmarking``).
    """
    @classmethod
    def precompute_foo(cls,
                      y: np.ndarray,
                      **kwargs) -> t.Dict[str, t.Any]:
        """Precompute some useful things to support complexity measures.

        Parameters
        ----------
        N : :obj:`np.ndarray`, optional
            Attributes from fitted data.

        y : :obj:`np.ndarray`, optional
            Target attribute from fitted data.

        **kwargs
            Additional arguments. May have previously precomputed before this
            method from other precomputed methods, so they can help speed up
            this precomputation.

        Returns
        -------
        :obj:`dict`
            With following precomputed items:
                - ``ovo_comb`` (:obj:`list`): List of all class OVO
                  combination, i.e., [(0,1), (0,2) ...].
                - ``cls_n_ex`` (:obj:`np.ndarray`): The number of examples in
                  each class. The array indexes represent the classes.
        """

        prepcomp_vals = {}
        return prepcomp_vals

    @classmethod
    def ft_wg_dist(cls,
                   N: np.ndarray,
                   wd_alpha: int = 2) -> float:
        """TODO
        """

        # 0-1 scaler
        scaler = MinMaxScaler(feature_range=(0, 1)).fit(N)
        N = scaler.transform(N)

        dist = distance.cdist(N, N, 'euclidean')

        d = dist/(np.sqrt(N.shape[0]-dist))
        w = 1/(np.power(2, wd_alpha*d))

        wd = np.sum(w*dist, axis=1)/(np.sum(w, axis=1)-1)

        return wd

    @classmethod
    def ft_cohesiveness(cls,
                        N: np.ndarray,
                        wd_alpha: int = 3
                        ) -> float:
        """TODO
        """

        # 0-1 scaler
        scaler = MinMaxScaler(feature_range=(0, 1)).fit(N)
        N = scaler.transform(N)

        dist = distance.cdist(N, N, 'euclidean')

        w = 1/(np.power(2, wd_alpha*dist))

        w_ = np.sort(w)
        w_ = w_[:, ::-1]
        cohe_i = np.sum(w_*np.arange(N.shape[0]), axis=1)

        return cohe_i

    @classmethod
    def ft_conceptvar(cls,
                      N: np.ndarray) -> float:
        """TODO
        """
        return 0.0

    @classmethod
    def ft_impconceptvar(cls,
                         N: np.ndarray) -> float:
        """TODO
        """
        return 0.0
