from load_tests import (
    np,
    sp,
    pd,
    graphtools,
    nose2,
    data,
    build_graph,
    assert_raises,
    raises,
    warns,
    squareform,
    pdist,
)

#####################################################
# Check parameters
#####################################################


@raises(ValueError)
def test_1d_data():
    build_graph(data[:, 0])


@raises(ValueError)
def test_3d_data():
    build_graph(data[:, :, None])


@warns(RuntimeWarning)
def test_too_many_n_pca():
    build_graph(data, n_pca=data.shape[1])


@warns(RuntimeWarning)
def test_precomputed_with_pca():
    build_graph(squareform(pdist(data)),
                precomputed='distance',
                n_pca=20)


#####################################################
# Check data types
#####################################################


def test_pandas_dataframe():
    G = build_graph(pd.DataFrame(data))
    assert isinstance(G, graphtools.base.BaseGraph)
    assert isinstance(G.data, np.ndarray)


def test_pandas_sparse_dataframe():
    G = build_graph(pd.SparseDataFrame(data))
    assert isinstance(G, graphtools.base.BaseGraph)
    assert isinstance(G.data, sp.csr_matrix)


#####################################################
# Check transform
#####################################################


def test_transform_dense_pca():
    G = build_graph(data, n_pca=20)
    assert(np.all(G.data_nu == G.transform(G.data)))
    assert_raises(ValueError, G.transform, G.data[:, 0])
    assert_raises(ValueError, G.transform, G.data[:, None, :15])
    assert_raises(ValueError, G.transform, G.data[:, :15])


def test_transform_dense_no_pca():
    G = build_graph(data, n_pca=None)
    assert(np.all(G.data_nu == G.transform(G.data)))
    assert_raises(ValueError, G.transform, G.data[:, 0])
    assert_raises(ValueError, G.transform, G.data[:, None, :15])
    assert_raises(ValueError, G.transform, G.data[:, :15])


def test_transform_sparse_pca():
    G = build_graph(data, sparse=True, n_pca=20)
    assert(np.all(G.data_nu == G.transform(G.data)))
    assert_raises(ValueError, G.transform, sp.csr_matrix(G.data)[:, 0])
    assert_raises(ValueError, G.transform, sp.csr_matrix(G.data)[:, :15])


def test_transform_sparse_no_pca():
    G = build_graph(data, sparse=True, n_pca=None)
    assert(np.sum(G.data_nu != G.transform(G.data)) == 0)
    assert_raises(ValueError, G.transform, sp.csr_matrix(G.data)[:, 0])
    assert_raises(ValueError, G.transform, sp.csr_matrix(G.data)[:, :15])


#####################################################
# Check inverse transform
#####################################################


def test_inverse_transform_dense_pca():
    G = build_graph(data, n_pca=data.shape[1] - 1)
    assert(np.allclose(G.data, G.inverse_transform(G.data_nu)))
    assert_raises(ValueError, G.inverse_transform, G.data[:, 0])
    assert_raises(ValueError, G.inverse_transform, G.data[:, None, :15])
    assert_raises(ValueError, G.inverse_transform, G.data[:, :15])


def test_inverse_transform_dense_no_pca():
    G = build_graph(data, n_pca=None)
    assert(np.all(G.data == G.inverse_transform(G.data_nu)))
    assert_raises(ValueError, G.inverse_transform, G.data[:, 0])
    assert_raises(ValueError, G.inverse_transform, G.data[:, None, :15])
    assert_raises(ValueError, G.inverse_transform, G.data[:, :15])


def test_inverse_transform_sparse_no_pca():
    G = build_graph(data, sparse=True, n_pca=None)
    assert(np.sum(G.data != G.inverse_transform(G.data_nu)) == 0)
    assert_raises(ValueError, G.inverse_transform, sp.csr_matrix(G.data)[:, 0])
    assert_raises(ValueError, G.inverse_transform,
                  sp.csr_matrix(G.data)[:, :15])


if __name__ == "__main__":
    exit(nose2.run())
