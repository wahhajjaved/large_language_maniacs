r"""
Generic graphs

This module implements the base class for graphs and digraphs, and
methods that can be applied on both.

Class and methods
-----------------
"""

from sage.plot.misc import options
from sage.misc.prandom import random
from sage.rings.integer_ring import ZZ
from sage.rings.integer import Integer
from sage.rings.rational import Rational
from sage.groups.perm_gps.partn_ref.refinement_graphs import isomorphic, search_tree
import sage.graphs.generic_graph_pyx as generic_graph_pyx
from generic_graph_pyx import GenericGraph_pyx, spring_layout_fast
from sage.graphs.dot2tex_utils import assert_have_dot2tex

class GenericGraph(GenericGraph_pyx):
    """
    Base class for graphs and digraphs.
    """

    # Nice defaults for plotting arrays of graphs (see sage.misc.functional.show)
    graphics_array_defaults =  {'layout': 'circular', 'vertex_size':50, 'vertex_labels':False, 'graph_border':True}

    def __init__(self):
        r"""
        Every graph carries a dictionary of options, which is set
        here to ``None``.  Some options are added to the global
        :data:`sage.misc.latex.latex` instance which will insure
        that if `\mbox{\rm\LaTeX}` is used to render the graph,
        then the right packages are loaded and jsMath reacts
        properly.

        Most other initialization is done in the directed
        and undirected subclasses.

        TESTS::

            sage: g = Graph()
            sage: g
            Graph on 0 vertices
        """
        self._latex_opts = None
        # FIXME: this has nothing to do here. Ideally, we would want
        # this to be run just once, just before the creation of a full
        # latex file including a graph.
        # There should be a Sage-wide strategy for handling this.
        from sage.graphs.graph_latex import setup_latex_preamble
        setup_latex_preamble()

    def __add__(self, other_graph):
        """
        Returns the disjoint union of self and other.

        If there are common vertices to both, they will be renamed.

        EXAMPLES::

            sage: G = graphs.CycleGraph(3)
            sage: H = graphs.CycleGraph(4)
            sage: J = G + H; J
            Cycle graph disjoint_union Cycle graph: Graph on 7 vertices
            sage: J.vertices()
            [0, 1, 2, 3, 4, 5, 6]
        """
        if isinstance(other_graph, GenericGraph):
            return self.disjoint_union(other_graph, verbose_relabel=False)

    def __eq__(self, other):
        """
        Comparison of self and other. For equality, must be in the same
        class, have the same settings for loops and multiedges, output the
        same vertex list (in order) and the same adjacency matrix.

        Note that this is _not_ an isomorphism test.

        EXAMPLES::

            sage: G = graphs.EmptyGraph()
            sage: H = Graph()
            sage: G == H
            True
            sage: G.to_directed() == H.to_directed()
            True
            sage: G = graphs.RandomGNP(8,.9999)
            sage: H = graphs.CompleteGraph(8)
            sage: G == H # most often true
            True
            sage: G = Graph( {0:[1,2,3,4,5,6,7]} )
            sage: H = Graph( {1:[0], 2:[0], 3:[0], 4:[0], 5:[0], 6:[0], 7:[0]} )
            sage: G == H
            True
            sage: G.allow_loops(True)
            sage: G == H
            False
            sage: G = graphs.RandomGNP(9,.3).to_directed()
            sage: H = graphs.RandomGNP(9,.3).to_directed()
            sage: G == H # most often false
            False
            sage: G = Graph(multiedges=True, sparse=True)
            sage: G.add_edge(0,1)
            sage: H = copy(G)
            sage: H.add_edge(0,1)
            sage: G == H
            False

        Note that graphs must be considered weighted, or Sage will not pay
        attention to edge label data in equality testing::

            sage: foo = Graph(sparse=True)
            sage: foo.add_edges([(0, 1, 1), (0, 2, 2)])
            sage: bar = Graph(sparse=True)
            sage: bar.add_edges([(0, 1, 2), (0, 2, 1)])
            sage: foo == bar
            True
            sage: foo.weighted(True)
            sage: foo == bar
            False
            sage: bar.weighted(True)
            sage: foo == bar
            False

        """
        # inputs must be (di)graphs:
        if not isinstance(other, GenericGraph):
            raise TypeError("Cannot compare graph to non-graph (%s)."%str(other))
        from sage.graphs.all import Graph
        g1_is_graph = isinstance(self, Graph) # otherwise, DiGraph
        g2_is_graph = isinstance(other, Graph) # otherwise, DiGraph
        if g1_is_graph != g2_is_graph:
            return False
        if self.allows_multiple_edges() != other.allows_multiple_edges():
            return False
        if self.allows_loops() != other.allows_loops():
            return False
        if self.vertices() != other.vertices():
            return False
        if self._weighted != other._weighted:
            return False
        verts = self.vertices()
        # Finally, we are prepared to check edges:
        if not self.allows_multiple_edges():
            for i in verts:
                for j in verts:
                    if self.has_edge(i,j) != other.has_edge(i,j):
                        return False
                    if self.has_edge(i,j) and self._weighted and other._weighted:
                        if self.edge_label(i,j) != other.edge_label(i,j):
                            return False
            return True
        else:
            for i in verts:
                for j in verts:
                    if self.has_edge(i, j):
                        edges1 = self.edge_label(i, j)
                    else:
                        edges1 = []
                    if other.has_edge(i, j):
                        edges2 = other.edge_label(i, j)
                    else:
                        edges2 = []
                    if len(edges1) != len(edges2):
                        return False
                    if sorted(edges1) != sorted(edges2) and self._weighted and other._weighted:
                        return False
            return True

    def __hash__(self):
        """
        Since graphs are mutable, they should not be hashable, so we return
        a type error.

        EXAMPLES::

            sage: hash(Graph())
            Traceback (most recent call last):
            ...
            TypeError: graphs are mutable, and thus not hashable
        """
        if getattr(self, "_immutable", False):
            return hash((tuple(self.vertices()), tuple(self.edges())))
        raise TypeError, "graphs are mutable, and thus not hashable"

    def __mul__(self, n):
        """
        Returns the sum of a graph with itself n times.

        EXAMPLES::

            sage: G = graphs.CycleGraph(3)
            sage: H = G*3; H
            Cycle graph disjoint_union Cycle graph disjoint_union Cycle graph: Graph on 9 vertices
            sage: H.vertices()
            [0, 1, 2, 3, 4, 5, 6, 7, 8]
            sage: H = G*1; H
            Cycle graph: Graph on 3 vertices
        """
        if isinstance(n, (int, long, Integer)):
            if n < 1:
                raise TypeError('Multiplication of a graph and a nonpositive integer is not defined.')
            if n == 1:
                from copy import copy
                return copy(self)
            return sum([self]*(n-1), self)
        else:
            raise TypeError('Multiplication of a graph and something other than an integer is not defined.')

    def __ne__(self, other):
        """
        Tests for inequality, complement of __eq__.

        EXAMPLES::

            sage: g = Graph()
            sage: g2 = copy(g)
            sage: g == g
            True
            sage: g != g
            False
            sage: g2 == g
            True
            sage: g2 != g
            False
            sage: g is g
            True
            sage: g2 is g
            False
        """
        return (not (self == other))

    def __rmul__(self, n):
        """
        Returns the sum of a graph with itself n times.

        EXAMPLES::

            sage: G = graphs.CycleGraph(3)
            sage: H = int(3)*G; H
            Cycle graph disjoint_union Cycle graph disjoint_union Cycle graph: Graph on 9 vertices
            sage: H.vertices()
            [0, 1, 2, 3, 4, 5, 6, 7, 8]
        """
        return self*n

    def __str__(self):
        """
        str(G) returns the name of the graph, unless the name is the empty
        string, in which case it returns the default representation.

        EXAMPLES::

            sage: G = graphs.PetersenGraph()
            sage: str(G)
            'Petersen graph'
        """
        if self.name():
            return self.name()
        else:
            return repr(self)

    def _bit_vector(self):
        """
        Returns a string representing the edges of the (simple) graph for
        graph6 and dig6 strings.

        EXAMPLES::

            sage: G = graphs.PetersenGraph()
            sage: G._bit_vector()
            '101001100110000010000001001000010110000010110'
            sage: len([a for a in G._bit_vector() if a == '1'])
            15
            sage: G.num_edges()
            15
        """
        vertices = self.vertices()
        n = len(vertices)
        if self._directed:
            total_length = n*n
            bit = lambda x,y : x*n + y
        else:
            total_length = int(n*(n - 1))/int(2)
            n_ch_2 = lambda b : int(b*(b-1))/int(2)
            bit = lambda x,y : n_ch_2(max([x,y])) + min([x,y])
        bit_vector = set()
        for u,v,_ in self.edge_iterator():
            bit_vector.add(bit(vertices.index(u), vertices.index(v)))
        bit_vector = sorted(bit_vector)
        s = []
        j = 0
        for i in bit_vector:
            s.append( '0'*(i - j) + '1' )
            j = i + 1
        s = "".join(s)
        s += '0'*(total_length-len(s))
        return s

    def _latex_(self):
        r""" Returns a string to render the graph using
        `\mbox{\rm{\LaTeX}}`.

        To adjust the string, use the
        :meth:`set_latex_options` method to set options,
        or call the :meth:`latex_options` method to
        get a :class:`~sage.graphs.graph_latex.GraphLatex`
        object that may be used to also customize the
        output produced here.  Possible options are documented at
        :meth:`sage.graphs.graph_latex.GraphLatex.set_option`.

        EXAMPLES::

            sage: from sage.graphs.graph_latex import check_tkz_graph
            sage: check_tkz_graph()  # random - depends on TeX installation
            sage: g = graphs.CompleteGraph(2)
            sage: print g._latex_()
            \begin{tikzpicture}
            %
            \definecolor{col_a0}{rgb}{1.0,1.0,1.0}
            \definecolor{col_a1}{rgb}{1.0,1.0,1.0}
            %
            %
            \definecolor{col_lab_a0}{rgb}{0.0,0.0,0.0}
            \definecolor{col_lab_a1}{rgb}{0.0,0.0,0.0}
            %
            %
            \definecolor{col_a0-a1}{rgb}{0.0,0.0,0.0}
            %
            %
            \GraphInit[vstyle=Normal]
            %
            \SetVertexMath
            %
            \SetVertexNoLabel
            %
            \renewcommand*{\VertexLightFillColor}{col_a0}
            \Vertex[x=5.0cm,y=5.0cm]{a0}
            \renewcommand*{\VertexLightFillColor}{col_a1}
            \Vertex[x=0.0cm,y=0.0cm]{a1}
            %
            %
            \AssignVertexLabel{a}{2}{
            \color{col_lab_a0}{$0$},
            \color{col_lab_a1}{$1$}
            }
            %
            %
            \renewcommand*{\EdgeColor}{col_a0-a1}
            \Edge(a0)(a1)
            %
            %
            \end{tikzpicture}
        """
        return self.latex_options().latex()

    def _matrix_(self, R=None):
        """
        Returns the adjacency matrix of the graph over the specified ring.

        EXAMPLES::

            sage: G = graphs.CompleteBipartiteGraph(2,3)
            sage: m = matrix(G); m.parent()
            Full MatrixSpace of 5 by 5 dense matrices over Integer Ring
            sage: m
            [0 0 1 1 1]
            [0 0 1 1 1]
            [1 1 0 0 0]
            [1 1 0 0 0]
            [1 1 0 0 0]
            sage: G._matrix_()
            [0 0 1 1 1]
            [0 0 1 1 1]
            [1 1 0 0 0]
            [1 1 0 0 0]
            [1 1 0 0 0]
            sage: factor(m.charpoly())
            x^3 * (x^2 - 6)
        """
        if R is None:
            return self.am()
        else:
            return self.am().change_ring(R)

    def _repr_(self):
        """
        Return a string representation of self.

        EXAMPLES::

            sage: G = graphs.PetersenGraph()
            sage: G._repr_()
            'Petersen graph: Graph on 10 vertices'
        """
        name = ""
        if self.allows_loops():
            name += "looped "
        if self.allows_multiple_edges():
            name += "multi-"
        if self._directed:
            name += "di"
        name += "graph on %d vert"%self.order()
        if self.order() == 1:
            name += "ex"
        else:
            name += "ices"
        name = name.capitalize()
        if self.name() != '':
            name = self.name() + ": " + name
        return name

    ### Formats

    def __copy__(self, implementation='c_graph', sparse=None):
        """
        Creates a copy of the graph.

        INPUT:

         - ``implementation`` - string (default: 'networkx') the
           implementation goes here.  Current options are only
           'networkx' or 'c_graph'.

         - ``sparse`` - boolean (default: None) whether the
           graph given is sparse or not.

        OUTPUT:

        A Graph object.

        .. warning::

           Please use this method only if you need to copy but change the
           underlying implementation.  Otherwise simply do ``copy(g)``
           instead of doing ``g.copy()``.

        EXAMPLES::

            sage: g=Graph({0:[0,1,1,2]},loops=True,multiedges=True,sparse=True)
            sage: g==copy(g)
            True
            sage: g=DiGraph({0:[0,1,1,2],1:[0,1]},loops=True,multiedges=True,sparse=True)
            sage: g==copy(g)
            True

        Note that vertex associations are also kept::

            sage: d = {0 : graphs.DodecahedralGraph(), 1 : graphs.FlowerSnark(), 2 : graphs.MoebiusKantorGraph(), 3 : graphs.PetersenGraph() }
            sage: T = graphs.TetrahedralGraph()
            sage: T.set_vertices(d)
            sage: T2 = copy(T)
            sage: T2.get_vertex(0)
            Dodecahedron: Graph on 20 vertices

        Notice that the copy is at least as deep as the objects::

            sage: T2.get_vertex(0) is T.get_vertex(0)
            False

        Examples of the keywords in use::

            sage: G = graphs.CompleteGraph(19)
            sage: H = G.copy(implementation='c_graph')
            sage: H == G; H is G
            True
            False
            sage: G1 = G.copy(sparse=True)
            sage: G1==G
            True
            sage: G1 is G
            False
            sage: G2 = copy(G)
            sage: G2 is G
            False

        TESTS: We make copies of the _pos and _boundary attributes.

        ::

            sage: g = graphs.PathGraph(3)
            sage: h = copy(g)
            sage: h._pos is g._pos
            False
            sage: h._boundary is g._boundary
            False
        """
        if sparse is None:
            from sage.graphs.base.dense_graph import DenseGraphBackend
            sparse = (not isinstance(self._backend, DenseGraphBackend))
        from copy import copy
        G = self.__class__(self, name=self.name(), pos=copy(self._pos), boundary=copy(self._boundary), implementation=implementation, sparse=sparse)

        attributes_to_copy = ('_assoc', '_embedding')
        for attr in attributes_to_copy:
            if hasattr(self, attr):
                copy_attr = {}
                old_attr = getattr(self, attr)
                if isinstance(old_attr, dict):
                    for v,value in old_attr.iteritems():
                        try:
                            copy_attr[v] = value.copy()
                        except AttributeError:
                            from copy import copy
                            copy_attr[v] = copy(value)
                    setattr(G, attr, copy_attr)
                else:
                    setattr(G, attr, copy(old_attr))

        G._weighted = self._weighted
        return G

    copy = __copy__

    def networkx_graph(self, copy=True):
        """
        Creates a new NetworkX graph from the Sage graph.

        INPUT:


        -  ``copy`` - if False, and the underlying
           implementation is a NetworkX graph, then the actual object itself
           is returned.


        EXAMPLES::

            sage: G = graphs.TetrahedralGraph()
            sage: N = G.networkx_graph()
            sage: type(N)
            <class 'networkx.classes.graph.Graph'>

        ::

            sage: G = graphs.TetrahedralGraph()
            sage: G = Graph(G, implementation='networkx')
            sage: N = G.networkx_graph()
            sage: G._backend._nxg is N
            False

        ::

            sage: G = Graph(graphs.TetrahedralGraph(), implementation='networkx')
            sage: N = G.networkx_graph(copy=False)
            sage: G._backend._nxg is N
            True
        """
        try:
            if copy:
                from copy import copy
                return self._backend._nxg.copy()
            else:
                return self._backend._nxg
        except:
            import networkx
            if self._directed and self.allows_multiple_edges():
                class_type = networkx.MultiDiGraph
            elif self._directed:
                class_type = networkx.DiGraph
            elif self.allows_multiple_edges():
                class_type = networkx.MultiGraph
            else:
                class_type = networkx.Graph
            N = class_type(selfloops=self.allows_loops(), multiedges=self.allows_multiple_edges(),
                           name=self.name())
            N.add_nodes_from(self.vertices())
            for u,v,l in self.edges():
                if l is None:
                    N.add_edge(u,v)
                else:
                    from networkx import NetworkXError
                    try:
                        N.add_edge(u,v,l)
                    except (TypeError, ValueError, NetworkXError):
                        N.add_edge(u,v,weight=l)
            return N

    def adjacency_matrix(self, sparse=None, boundary_first=False):
        """
        Returns the adjacency matrix of the (di)graph. Each vertex is
        represented by its position in the list returned by the vertices()
        function.

        The matrix returned is over the integers. If a different ring is
        desired, use either the change_ring function or the matrix
        function.

        INPUT:


        -  ``sparse`` - whether to represent with a sparse
           matrix

        -  ``boundary_first`` - whether to represent the
           boundary vertices in the upper left block


        EXAMPLES::

            sage: G = graphs.CubeGraph(4)
            sage: G.adjacency_matrix()
            [0 1 1 0 1 0 0 0 1 0 0 0 0 0 0 0]
            [1 0 0 1 0 1 0 0 0 1 0 0 0 0 0 0]
            [1 0 0 1 0 0 1 0 0 0 1 0 0 0 0 0]
            [0 1 1 0 0 0 0 1 0 0 0 1 0 0 0 0]
            [1 0 0 0 0 1 1 0 0 0 0 0 1 0 0 0]
            [0 1 0 0 1 0 0 1 0 0 0 0 0 1 0 0]
            [0 0 1 0 1 0 0 1 0 0 0 0 0 0 1 0]
            [0 0 0 1 0 1 1 0 0 0 0 0 0 0 0 1]
            [1 0 0 0 0 0 0 0 0 1 1 0 1 0 0 0]
            [0 1 0 0 0 0 0 0 1 0 0 1 0 1 0 0]
            [0 0 1 0 0 0 0 0 1 0 0 1 0 0 1 0]
            [0 0 0 1 0 0 0 0 0 1 1 0 0 0 0 1]
            [0 0 0 0 1 0 0 0 1 0 0 0 0 1 1 0]
            [0 0 0 0 0 1 0 0 0 1 0 0 1 0 0 1]
            [0 0 0 0 0 0 1 0 0 0 1 0 1 0 0 1]
            [0 0 0 0 0 0 0 1 0 0 0 1 0 1 1 0]

        ::

            sage: matrix(GF(2),G) # matrix over GF(2)
            [0 1 1 0 1 0 0 0 1 0 0 0 0 0 0 0]
            [1 0 0 1 0 1 0 0 0 1 0 0 0 0 0 0]
            [1 0 0 1 0 0 1 0 0 0 1 0 0 0 0 0]
            [0 1 1 0 0 0 0 1 0 0 0 1 0 0 0 0]
            [1 0 0 0 0 1 1 0 0 0 0 0 1 0 0 0]
            [0 1 0 0 1 0 0 1 0 0 0 0 0 1 0 0]
            [0 0 1 0 1 0 0 1 0 0 0 0 0 0 1 0]
            [0 0 0 1 0 1 1 0 0 0 0 0 0 0 0 1]
            [1 0 0 0 0 0 0 0 0 1 1 0 1 0 0 0]
            [0 1 0 0 0 0 0 0 1 0 0 1 0 1 0 0]
            [0 0 1 0 0 0 0 0 1 0 0 1 0 0 1 0]
            [0 0 0 1 0 0 0 0 0 1 1 0 0 0 0 1]
            [0 0 0 0 1 0 0 0 1 0 0 0 0 1 1 0]
            [0 0 0 0 0 1 0 0 0 1 0 0 1 0 0 1]
            [0 0 0 0 0 0 1 0 0 0 1 0 1 0 0 1]
            [0 0 0 0 0 0 0 1 0 0 0 1 0 1 1 0]

        ::

            sage: D = DiGraph( { 0: [1,2,3], 1: [0,2], 2: [3], 3: [4], 4: [0,5], 5: [1] } )
            sage: D.adjacency_matrix()
            [0 1 1 1 0 0]
            [1 0 1 0 0 0]
            [0 0 0 1 0 0]
            [0 0 0 0 1 0]
            [1 0 0 0 0 1]
            [0 1 0 0 0 0]

        TESTS::

            sage: graphs.CubeGraph(8).adjacency_matrix().parent()
            Full MatrixSpace of 256 by 256 dense matrices over Integer Ring
            sage: graphs.CubeGraph(9).adjacency_matrix().parent()
            Full MatrixSpace of 512 by 512 sparse matrices over Integer Ring
        """
        n = self.order()
        if sparse is None:
            if n <= 256 or self.density() > 0.05:
                sparse=False
            else:
                sparse=True

        verts = self.vertices(boundary_first=boundary_first)
        new_indices = dict((v,i) for i,v in enumerate(verts))
        D = {}
        directed = self._directed
        multiple_edges = self.allows_multiple_edges()
        for i,j,l in self.edge_iterator():
            i = new_indices[i]
            j = new_indices[j]
            if multiple_edges and (i,j) in D:
                D[(i,j)] += 1
                if not directed and i != j:
                    D[(j,i)] += 1
            else:
                D[(i,j)] = 1
                if not directed and i != j:
                    D[(j,i)] = 1
        from sage.rings.integer_ring import IntegerRing
        from sage.matrix.constructor import matrix
        M = matrix(IntegerRing(), n, n, D, sparse=sparse)
        return M

    am = adjacency_matrix # shorter call makes life easier

    def incidence_matrix(self, sparse=True):
        """
        Returns an incidence matrix of the (di)graph. Each row is a vertex,
        and each column is an edge. Note that in the case of graphs, there
        is a choice of orientation for each edge.

        EXAMPLES::

            sage: G = graphs.CubeGraph(3)
            sage: G.incidence_matrix()
            [-1 -1 -1  0  0  0  0  0  0  0  0  0]
            [ 0  0  1 -1 -1  0  0  0  0  0  0  0]
            [ 0  1  0  0  0 -1 -1  0  0  0  0  0]
            [ 0  0  0  0  1  0  1 -1  0  0  0  0]
            [ 1  0  0  0  0  0  0  0 -1 -1  0  0]
            [ 0  0  0  1  0  0  0  0  0  1 -1  0]
            [ 0  0  0  0  0  1  0  0  1  0  0 -1]
            [ 0  0  0  0  0  0  0  1  0  0  1  1]

        ::

            sage: D = DiGraph( { 0: [1,2,3], 1: [0,2], 2: [3], 3: [4], 4: [0,5], 5: [1] } )
            sage: D.incidence_matrix()
            [-1 -1 -1  0  0  0  0  0  1  1]
            [ 0  0  1 -1  0  0  0  1 -1  0]
            [ 0  1  0  1 -1  0  0  0  0  0]
            [ 1  0  0  0  1 -1  0  0  0  0]
            [ 0  0  0  0  0  1 -1  0  0 -1]
            [ 0  0  0  0  0  0  1 -1  0  0]
        """
        from sage.matrix.constructor import matrix
        from copy import copy
        n = self.order()
        verts = self.vertices()
        d = [0]*n
        cols = []
        if self._directed:
            for i, j, l in self.edge_iterator():
                col = copy(d)
                i = verts.index(i)
                j = verts.index(j)
                col[i] = -1
                col[j] = 1
                cols.append(col)
        else:
            for i, j, l in self.edge_iterator():
                col = copy(d)
                i,j = (i,j) if i <= j else (j,i)
                i = verts.index(i)
                j = verts.index(j)
                col[i] = -1
                col[j] = 1
                cols.append(col)
        cols.sort()
        return matrix(cols, sparse=sparse).transpose()

    def weighted_adjacency_matrix(self, sparse=True, boundary_first=False):
        """
        Returns the weighted adjacency matrix of the graph. Each vertex is
        represented by its position in the list returned by the vertices()
        function.

        EXAMPLES::

            sage: G = Graph(sparse=True, weighted=True)
            sage: G.add_edges([(0,1,1),(1,2,2),(0,2,3),(0,3,4)])
            sage: M = G.weighted_adjacency_matrix(); M
            [0 1 3 4]
            [1 0 2 0]
            [3 2 0 0]
            [4 0 0 0]
            sage: H = Graph(data=M, format='weighted_adjacency_matrix', sparse=True)
            sage: H == G
            True

        The following doctest verifies that \#4888 is fixed::

            sage: G = DiGraph({0:{}, 1:{0:1}, 2:{0:1}}, weighted = True,sparse=True)
            sage: G.weighted_adjacency_matrix()
            [0 0 0]
            [1 0 0]
            [1 0 0]

        """
        if self.has_multiple_edges():
            raise NotImplementedError, "Don't know how to represent weights for a multigraph."

        verts = self.vertices(boundary_first=boundary_first)
        new_indices = dict((v,i) for i,v in enumerate(verts))

        D = {}
        if self._directed:
            for i,j,l in self.edge_iterator():
                i = new_indices[i]
                j = new_indices[j]
                D[(i,j)] = l
        else:
            for i,j,l in self.edge_iterator():
                i = new_indices[i]
                j = new_indices[j]
                D[(i,j)] = l
                D[(j,i)] = l
        from sage.matrix.constructor import matrix
        M = matrix(self.num_verts(), D, sparse=sparse)
        return M

    def kirchhoff_matrix(self, weighted=None, indegree=True, normalized=False, **kwds):
        """
        Returns the Kirchhoff matrix (a.k.a. the Laplacian) of the graph.

        The Kirchhoff matrix is defined to be `D - M`, where `D` is
        the diagonal degree matrix (each diagonal entry is the degree
        of the corresponding vertex), and `M` is the adjacency matrix.
        If ``normalized`` is ``True``, then the returned matrix is
        `D^{-1/2}(D-M)D^{-1/2}`.

        ( In the special case of DiGraphs, `D` is defined as the diagonal
        in-degree matrix or diagonal out-degree matrix according to the
        value of ``indegree``)

        INPUT:

        - ``weighted`` -- Binary variable :
            - If ``True``, the weighted adjacency matrix is used for `M`,
              and the diagonal matrix `D` takes into account the weight of edges
              (replace in the definition "degree" by "sum of the incident edges" ).
            - Else, each edge is assumed to have weight 1.

            Default is to take weights into consideration if and only if the graph is
            weighted.

        - ``indegree`` -- Binary variable  :
            - If ``True``, each diagonal entry of `D` is equal to the
              in-degree of the corresponding vertex.
            - Else, each diagonal entry of `D` is equal to the
              out-degree of the corresponding vertex.

              By default, ``indegree`` is set to ``True``

            ( This variable only matters when the graph is a digraph )

        - ``normalized`` -- Binary variable :

            - If ``True``, the returned matrix is
              `D^{-1/2}(D-M)D^{-1/2}`, a normalized version of the
              Laplacian matrix.
            - Else, the matrix `D-M` is returned

        Note that any additional keywords will be passed on to either
        the ``adjacency_matrix`` or ``weighted_adjacency_matrix`` method.

        AUTHORS:

        - Tom Boothby
        - Jason Grout

        EXAMPLES::

            sage: G = Graph(sparse=True)
            sage: G.add_edges([(0,1,1),(1,2,2),(0,2,3),(0,3,4)])
            sage: M = G.kirchhoff_matrix(weighted=True); M
            [ 8 -1 -3 -4]
            [-1  3 -2  0]
            [-3 -2  5  0]
            [-4  0  0  4]
            sage: M = G.kirchhoff_matrix(); M
            [ 3 -1 -1 -1]
            [-1  2 -1  0]
            [-1 -1  2  0]
            [-1  0  0  1]
            sage: G.set_boundary([2,3])
            sage: M = G.kirchhoff_matrix(weighted=True, boundary_first=True); M
            [ 5  0 -3 -2]
            [ 0  4 -4  0]
            [-3 -4  8 -1]
            [-2  0 -1  3]
            sage: M = G.kirchhoff_matrix(boundary_first=True); M
            [ 2  0 -1 -1]
            [ 0  1 -1  0]
            [-1 -1  3 -1]
            [-1  0 -1  2]
            sage: M = G.laplacian_matrix(boundary_first=True); M
            [ 2  0 -1 -1]
            [ 0  1 -1  0]
            [-1 -1  3 -1]
            [-1  0 -1  2]
            sage: M = G.laplacian_matrix(boundary_first=True, sparse=False); M
            [ 2  0 -1 -1]
            [ 0  1 -1  0]
            [-1 -1  3 -1]
            [-1  0 -1  2]
            sage: M = G.laplacian_matrix(normalized=True); M
            [                   1 -1/6*sqrt(2)*sqrt(3) -1/6*sqrt(2)*sqrt(3)         -1/3*sqrt(3)]
            [-1/6*sqrt(2)*sqrt(3)                    1                 -1/2                    0]
            [-1/6*sqrt(2)*sqrt(3)                 -1/2                    1                    0]
            [        -1/3*sqrt(3)                    0                    0                    1]


        A weighted directed graph with loops, changing the variable ``indegree`` ::

            sage: G = DiGraph({1:{1:2,2:3}, 2:{1:4}}, weighted=True,sparse=True)
            sage: G.laplacian_matrix()
            [ 4 -3]
            [-4  3]

        ::

            sage: G = DiGraph({1:{1:2,2:3}, 2:{1:4}}, weighted=True,sparse=True)
            sage: G.laplacian_matrix(indegree=False)
            [ 3 -3]
            [-4  4]
        """
        from sage.matrix.constructor import matrix, diagonal_matrix
        from sage.rings.integer_ring import IntegerRing
        from sage.functions.all import sqrt

        if weighted is None:
            weighted = self._weighted

        if weighted:
            M = self.weighted_adjacency_matrix(**kwds)
        else:
            M = self.adjacency_matrix(**kwds)

        D = M.parent(0)

        if M.is_sparse():
            row_sums = {}
            if indegree:
                for (i,j), entry in M.dict().iteritems():
                    row_sums[j] = row_sums.get(j, 0) + entry
            else:
                for (i,j), entry in M.dict().iteritems():
                    row_sums[i] = row_sums.get(i, 0) + entry


            for i in range(M.nrows()):
                D[i,i] += row_sums.get(i, 0)

        else:
            if indegree:
                col_sums=[sum(v) for v in M.columns()]
                for i in range(M.nrows()):
                    D[i,i] += col_sums[i]
            else:
                row_sums=[sum(v) for v in M.rows()]
                for i in range(M.nrows()):
                    D[i,i] += row_sums[i]

        if normalized:
            Dsqrt = diagonal_matrix([1/sqrt(D[i,i]) for i in range(D.nrows())])
            return Dsqrt*(D-M)*Dsqrt
        else:
            return D-M

    laplacian_matrix = kirchhoff_matrix

    ### Attributes

    def get_boundary(self):
        """
        Returns the boundary of the (di)graph.

        EXAMPLES::

            sage: G = graphs.PetersenGraph()
            sage: G.set_boundary([0,1,2,3,4])
            sage: G.get_boundary()
            [0, 1, 2, 3, 4]
        """
        return self._boundary

    def set_boundary(self, boundary):
        """
        Sets the boundary of the (di)graph.

        EXAMPLES::

            sage: G = graphs.PetersenGraph()
            sage: G.set_boundary([0,1,2,3,4])
            sage: G.get_boundary()
            [0, 1, 2, 3, 4]
            sage: G.set_boundary((1..4))
            sage: G.get_boundary()
            [1, 2, 3, 4]
        """
        if isinstance(boundary,list):
            self._boundary = boundary
        else:
            self._boundary = list(boundary)

    def set_embedding(self, embedding):
        """
        Sets a combinatorial embedding dictionary to _embedding attribute.
        Dictionary is organized with vertex labels as keys and a list of
        each vertex's neighbors in clockwise order.

        Dictionary is error-checked for validity.

        INPUT:


        -  ``embedding`` - a dictionary


        EXAMPLES::

            sage: G = graphs.PetersenGraph()
            sage: G.set_embedding({0: [1, 5, 4], 1: [0, 2, 6], 2: [1, 3, 7], 3: [8, 2, 4], 4: [0, 9, 3], 5: [0, 8, 7], 6: [8, 1, 9], 7: [9, 2, 5], 8: [3, 5, 6], 9: [4, 6, 7]})
            sage: G.set_embedding({'s': [1, 5, 4], 1: [0, 2, 6], 2: [1, 3, 7], 3: [8, 2, 4], 4: [0, 9, 3], 5: [0, 8, 7], 6: [8, 1, 9], 7: [9, 2, 5], 8: [3, 5, 6], 9: [4, 6, 7]})
            Traceback (most recent call last):
            ...
            Exception: embedding is not valid for Petersen graph
        """
        if self.check_embedding_validity(embedding):
            self._embedding = embedding
        else:
            raise Exception('embedding is not valid for %s'%self)

    def get_embedding(self):
        """
        Returns the attribute _embedding if it exists. _embedding is a
        dictionary organized with vertex labels as keys and a list of each
        vertex's neighbors in clockwise order.

        Error-checked to insure valid embedding is returned.

        EXAMPLES::

            sage: G = graphs.PetersenGraph()
            sage: G.genus()
            1
            sage: G.get_embedding()
            {0: [1, 4, 5], 1: [0, 2, 6], 2: [1, 3, 7], 3: [2, 4, 8], 4: [0, 3, 9], 5: [0, 7, 8], 6: [1, 9, 8], 7: [2, 5, 9], 8: [3, 6, 5], 9: [4, 6, 7]}
        """
        if self.check_embedding_validity():
            return self._embedding
        else:
            raise Exception('%s has been modified and the embedding is no longer valid.'%self)

    def check_embedding_validity(self, embedding=None):
        """
        Checks whether an _embedding attribute is defined on self and if
        so, checks for accuracy. Returns True if everything is okay, False
        otherwise.

        If embedding=None will test the attribute _embedding.

        EXAMPLES::

            sage: d = {0: [1, 5, 4], 1: [0, 2, 6], 2: [1, 3, 7], 3: [8, 2, 4], 4: [0, 9, 3], 5: [0, 8, 7], 6: [8, 1, 9], 7: [9, 2, 5], 8: [3, 5, 6], 9: [4, 6, 7]}
            sage: G = graphs.PetersenGraph()
            sage: G.check_embedding_validity(d)
            True
        """
        if embedding is None:
            embedding = getattr(self, '_embedding', None)
        if embedding is None:
            return False
        if len(embedding) != self.order():
            return False
        if self._directed:
            connected = lambda u,v : self.has_edge(u,v) or self.has_edge(v,u)
        else:
            connected = lambda u,v : self.has_edge(u,v)
        for v in embedding:
            if not self.has_vertex(v):
                return False
            if len(embedding[v]) != len(self.neighbors(v)):
                return False
            for u in embedding[v]:
                if not connected(v,u):
                    return False
        return True

    def has_loops(self):
        """
        Returns whether there are loops in the (di)graph.

        EXAMPLES::

            sage: G = Graph(loops=True); G
            Looped graph on 0 vertices
            sage: G.has_loops()
            False
            sage: G.allows_loops()
            True
            sage: G.add_edge((0,0))
            sage: G.has_loops()
            True
            sage: G.loops()
            [(0, 0, None)]
            sage: G.allow_loops(False); G
            Graph on 1 vertex
            sage: G.has_loops()
            False
            sage: G.edges()
            []

            sage: D = DiGraph(loops=True); D
            Looped digraph on 0 vertices
            sage: D.has_loops()
            False
            sage: D.allows_loops()
            True
            sage: D.add_edge((0,0))
            sage: D.has_loops()
            True
            sage: D.loops()
            [(0, 0, None)]
            sage: D.allow_loops(False); D
            Digraph on 1 vertex
            sage: D.has_loops()
            False
            sage: D.edges()
            []
        """
        if self.allows_loops():
            for v in self:
                if self.has_edge(v,v):
                    return True
        return False

    def allows_loops(self):
        """
        Returns whether loops are permitted in the (di)graph.

        EXAMPLES::

            sage: G = Graph(loops=True); G
            Looped graph on 0 vertices
            sage: G.has_loops()
            False
            sage: G.allows_loops()
            True
            sage: G.add_edge((0,0))
            sage: G.has_loops()
            True
            sage: G.loops()
            [(0, 0, None)]
            sage: G.allow_loops(False); G
            Graph on 1 vertex
            sage: G.has_loops()
            False
            sage: G.edges()
            []

            sage: D = DiGraph(loops=True); D
            Looped digraph on 0 vertices
            sage: D.has_loops()
            False
            sage: D.allows_loops()
            True
            sage: D.add_edge((0,0))
            sage: D.has_loops()
            True
            sage: D.loops()
            [(0, 0, None)]
            sage: D.allow_loops(False); D
            Digraph on 1 vertex
            sage: D.has_loops()
            False
            sage: D.edges()
            []
        """
        return self._backend.loops(None)

    def allow_loops(self, new, check=True):
        """
        Changes whether loops are permitted in the (di)graph.

        INPUT:

        - ``new`` - boolean.

        EXAMPLES::

            sage: G = Graph(loops=True); G
            Looped graph on 0 vertices
            sage: G.has_loops()
            False
            sage: G.allows_loops()
            True
            sage: G.add_edge((0,0))
            sage: G.has_loops()
            True
            sage: G.loops()
            [(0, 0, None)]
            sage: G.allow_loops(False); G
            Graph on 1 vertex
            sage: G.has_loops()
            False
            sage: G.edges()
            []

            sage: D = DiGraph(loops=True); D
            Looped digraph on 0 vertices
            sage: D.has_loops()
            False
            sage: D.allows_loops()
            True
            sage: D.add_edge((0,0))
            sage: D.has_loops()
            True
            sage: D.loops()
            [(0, 0, None)]
            sage: D.allow_loops(False); D
            Digraph on 1 vertex
            sage: D.has_loops()
            False
            sage: D.edges()
            []
        """
        if new is False and check:
            self.remove_loops()
        self._backend.loops(new)

    def loops(self, new=None, labels=True):
        """
        Returns any loops in the (di)graph.

        INPUT:

        - ``new`` -- deprecated

        - ``labels`` -- whether returned edges have labels ((u,v,l)) or not ((u,v)).

        EXAMPLES::

            sage: G = Graph(loops=True); G
            Looped graph on 0 vertices
            sage: G.has_loops()
            False
            sage: G.allows_loops()
            True
            sage: G.add_edge((0,0))
            sage: G.has_loops()
            True
            sage: G.loops()
            [(0, 0, None)]
            sage: G.allow_loops(False); G
            Graph on 1 vertex
            sage: G.has_loops()
            False
            sage: G.edges()
            []

            sage: D = DiGraph(loops=True); D
            Looped digraph on 0 vertices
            sage: D.has_loops()
            False
            sage: D.allows_loops()
            True
            sage: D.add_edge((0,0))
            sage: D.has_loops()
            True
            sage: D.loops()
            [(0, 0, None)]
            sage: D.allow_loops(False); D
            Digraph on 1 vertex
            sage: D.has_loops()
            False
            sage: D.edges()
            []

            sage: G = graphs.PetersenGraph()
            sage: G.loops()
            []

        """
        from sage.misc.misc import deprecation
        if new is not None:
            deprecation("The function loops is replaced by allow_loops and allows_loops.")
        loops = []
        for v in self:
            loops += self.edge_boundary([v], [v], labels)
        return loops

    def has_multiple_edges(self, to_undirected=False):
        """
        Returns whether there are multiple edges in the (di)graph.

        INPUT:

        - ``to_undirected`` -- (default: False) If True, runs the test on the undirected version of a DiGraph.
          Otherwise, treats DiGraph edges (u,v) and (v,u) as unique individual edges.

        EXAMPLES::

            sage: G = Graph(multiedges=True,sparse=True); G
            Multi-graph on 0 vertices
            sage: G.has_multiple_edges()
            False
            sage: G.allows_multiple_edges()
            True
            sage: G.add_edges([(0,1)]*3)
            sage: G.has_multiple_edges()
            True
            sage: G.multiple_edges()
            [(0, 1, None), (0, 1, None), (0, 1, None)]
            sage: G.allow_multiple_edges(False); G
            Graph on 2 vertices
            sage: G.has_multiple_edges()
            False
            sage: G.edges()
            [(0, 1, None)]

            sage: D = DiGraph(multiedges=True,sparse=True); D
            Multi-digraph on 0 vertices
            sage: D.has_multiple_edges()
            False
            sage: D.allows_multiple_edges()
            True
            sage: D.add_edges([(0,1)]*3)
            sage: D.has_multiple_edges()
            True
            sage: D.multiple_edges()
            [(0, 1, None), (0, 1, None), (0, 1, None)]
            sage: D.allow_multiple_edges(False); D
            Digraph on 2 vertices
            sage: D.has_multiple_edges()
            False
            sage: D.edges()
            [(0, 1, None)]

            sage: G = DiGraph({1:{2: 'h'}, 2:{1:'g'}},sparse=True)
            sage: G.has_multiple_edges()
            False
            sage: G.has_multiple_edges(to_undirected=True)
            True
            sage: G.multiple_edges()
            []
            sage: G.multiple_edges(to_undirected=True)
            [(1, 2, 'h'), (2, 1, 'g')]
        """
        if self.allows_multiple_edges() or (self._directed and to_undirected):
            if self._directed:
                for u in self:
                    s = set()
                    for a,b,c in self.outgoing_edge_iterator(u):
                        if b in s:
                            return True
                        s.add(b)
                    if to_undirected:
                        for a,b,c in self.incoming_edge_iterator(u):
                            if a in s:
                                return True
                            s.add(a)
            else:
                for u in self:
                    s = set()
                    for a,b,c in self.edge_iterator(u):
                        if a is u:
                            if b in s:
                                return True
                            s.add(b)
                        if b is u:
                            if a in s:
                                return True
                            s.add(a)
        return False

    def allows_multiple_edges(self):
        """
        Returns whether multiple edges are permitted in the (di)graph.

        EXAMPLES::

            sage: G = Graph(multiedges=True,sparse=True); G
            Multi-graph on 0 vertices
            sage: G.has_multiple_edges()
            False
            sage: G.allows_multiple_edges()
            True
            sage: G.add_edges([(0,1)]*3)
            sage: G.has_multiple_edges()
            True
            sage: G.multiple_edges()
            [(0, 1, None), (0, 1, None), (0, 1, None)]
            sage: G.allow_multiple_edges(False); G
            Graph on 2 vertices
            sage: G.has_multiple_edges()
            False
            sage: G.edges()
            [(0, 1, None)]

            sage: D = DiGraph(multiedges=True,sparse=True); D
            Multi-digraph on 0 vertices
            sage: D.has_multiple_edges()
            False
            sage: D.allows_multiple_edges()
            True
            sage: D.add_edges([(0,1)]*3)
            sage: D.has_multiple_edges()
            True
            sage: D.multiple_edges()
            [(0, 1, None), (0, 1, None), (0, 1, None)]
            sage: D.allow_multiple_edges(False); D
            Digraph on 2 vertices
            sage: D.has_multiple_edges()
            False
            sage: D.edges()
            [(0, 1, None)]
        """
        return self._backend.multiple_edges(None)

    def allow_multiple_edges(self, new, check=True):
        """
        Changes whether multiple edges are permitted in the (di)graph.

        INPUT:

        - ``new`` - boolean.

        EXAMPLES::

            sage: G = Graph(multiedges=True,sparse=True); G
            Multi-graph on 0 vertices
            sage: G.has_multiple_edges()
            False
            sage: G.allows_multiple_edges()
            True
            sage: G.add_edges([(0,1)]*3)
            sage: G.has_multiple_edges()
            True
            sage: G.multiple_edges()
            [(0, 1, None), (0, 1, None), (0, 1, None)]
            sage: G.allow_multiple_edges(False); G
            Graph on 2 vertices
            sage: G.has_multiple_edges()
            False
            sage: G.edges()
            [(0, 1, None)]

            sage: D = DiGraph(multiedges=True,sparse=True); D
            Multi-digraph on 0 vertices
            sage: D.has_multiple_edges()
            False
            sage: D.allows_multiple_edges()
            True
            sage: D.add_edges([(0,1)]*3)
            sage: D.has_multiple_edges()
            True
            sage: D.multiple_edges()
            [(0, 1, None), (0, 1, None), (0, 1, None)]
            sage: D.allow_multiple_edges(False); D
            Digraph on 2 vertices
            sage: D.has_multiple_edges()
            False
            sage: D.edges()
            [(0, 1, None)]
        """
        seen = set()

        # TODO: this should be much faster for c_graphs, but for now we just do this
        if self.allows_multiple_edges() and new is False and check:
            for u,v,l in self.multiple_edges():
                if (u,v) in seen:
                    self.delete_edge(u,v,l)
                else:
                    seen.add((u,v))

        self._backend.multiple_edges(new)

    def multiple_edges(self, new=None, to_undirected=False, labels=True):
        """
        Returns any multiple edges in the (di)graph.

        EXAMPLES::

            sage: G = Graph(multiedges=True,sparse=True); G
            Multi-graph on 0 vertices
            sage: G.has_multiple_edges()
            False
            sage: G.allows_multiple_edges()
            True
            sage: G.add_edges([(0,1)]*3)
            sage: G.has_multiple_edges()
            True
            sage: G.multiple_edges()
            [(0, 1, None), (0, 1, None), (0, 1, None)]
            sage: G.allow_multiple_edges(False); G
            Graph on 2 vertices
            sage: G.has_multiple_edges()
            False
            sage: G.edges()
            [(0, 1, None)]

            sage: D = DiGraph(multiedges=True,sparse=True); D
            Multi-digraph on 0 vertices
            sage: D.has_multiple_edges()
            False
            sage: D.allows_multiple_edges()
            True
            sage: D.add_edges([(0,1)]*3)
            sage: D.has_multiple_edges()
            True
            sage: D.multiple_edges()
            [(0, 1, None), (0, 1, None), (0, 1, None)]
            sage: D.allow_multiple_edges(False); D
            Digraph on 2 vertices
            sage: D.has_multiple_edges()
            False
            sage: D.edges()
            [(0, 1, None)]

            sage: G = DiGraph({1:{2: 'h'}, 2:{1:'g'}},sparse=True)
            sage: G.has_multiple_edges()
            False
            sage: G.has_multiple_edges(to_undirected=True)
            True
            sage: G.multiple_edges()
            []
            sage: G.multiple_edges(to_undirected=True)
            [(1, 2, 'h'), (2, 1, 'g')]
        """
        from sage.misc.misc import deprecation
        if new is not None:
            deprecation("The function multiple_edges is replaced by allow_multiple_edges and allows_multiple_edges.")
        multi_edges = []
        if self._directed and not to_undirected:
            for v in self:
                for u in self.neighbor_in_iterator(v):
                    edges = self.edge_boundary([u], [v], labels)
                    if len(edges) > 1:
                        multi_edges += edges
        else:
            to_undirected *= self._directed
            for v in self:
                for u in self.neighbor_iterator(v):
                    if hash(u) >= hash(v):
                        edges = self.edge_boundary([v], [u], labels)
                        if to_undirected:
                            edges += self.edge_boundary([u],[v], labels)
                        if len(edges) > 1:
                            multi_edges += edges
        return multi_edges

    def name(self, new=None):
        """
        INPUT:

        - ``new`` - if not None, then this becomes the new name of the (di)graph.
          (if new == '', removes any name)

        EXAMPLES::

            sage: d = {0: [1,4,5], 1: [2,6], 2: [3,7], 3: [4,8], 4: [9], 5: [7, 8], 6: [8,9], 7: [9]}
            sage: G = Graph(d); G
            Graph on 10 vertices
            sage: G.name("Petersen Graph"); G
            Petersen Graph: Graph on 10 vertices
            sage: G.name(new=""); G
            Graph on 10 vertices
            sage: G.name()
            ''
        """
        return self._backend.name(new)

    def get_pos(self, dim = 2):
        """
        Returns the position dictionary, a dictionary specifying the
        coordinates of each vertex.

        EXAMPLES: By default, the position of a graph is None::

            sage: G = Graph()
            sage: G.get_pos()
            sage: G.get_pos() is None
            True
            sage: P = G.plot(save_pos=True)
            sage: G.get_pos()
            {}

        Some of the named graphs come with a pre-specified positioning::

            sage: G = graphs.PetersenGraph()
            sage: G.get_pos()
            {0: (...e-17, 1.0),
             ...
             9: (0.475..., 0.154...)}
        """
        if dim == 2:
            return self._pos
        elif dim == 3:
            return getattr(self, "_pos3d", None)
        else:
            raise ValueError("dim must be 2 or 3")

    def check_pos_validity(self, pos=None, dim = 2):
        r"""
        Checks whether pos specifies two (resp. 3) coordinates for every vertex (and no more vertices).

        INPUT:

            - ``pos`` - a position dictionary for a set of vertices
            - ``dim`` - 2 or 3 (default: 3

        OUTPUT:

        If ``pos`` is ``None`` then the position dictionary of ``self`` is
        investigated, otherwise the position dictionary provided in  ``pos`` is
        investigated.  The function returns ``True`` if the dictionary is of the
        correct form for ``self``.

        EXAMPLES::

            sage: p = {0: [1, 5], 1: [0, 2], 2: [1, 3], 3: [8, 2], 4: [0, 9], 5: [0, 8], 6: [8, 1], 7: [9, 5], 8: [3, 5], 9: [6, 7]}
            sage: G = graphs.PetersenGraph()
            sage: G.check_pos_validity(p)
            True
        """
        if pos is None:
            pos = self.get_pos(dim = dim)
        if pos is None:
            return False
        if len(pos) != self.order():
            return False
        for v in pos:
            if not self.has_vertex(v):
                return False
            if len(pos[v]) != dim:
                return False
        return True

    def set_pos(self, pos, dim = 2):
        """
        Sets the position dictionary, a dictionary specifying the
        coordinates of each vertex.

        EXAMPLES: Note that set_pos will allow you to do ridiculous things,
        which will not blow up until plotting::

            sage: G = graphs.PetersenGraph()
            sage: G.get_pos()
            {0: (..., ...),
             ...
             9: (..., ...)}

        ::

            sage: G.set_pos('spam')
            sage: P = G.plot()
            Traceback (most recent call last):
            ...
            TypeError: string indices must be integers, not str
        """
        if dim == 2:
            self._pos = pos
        elif dim == 3:
            self._pos3d = pos
        else:
            raise ValueError("dim must be 2 or 3")

    def weighted(self, new=None):
        """
        Returns whether the (di)graph is to be considered as a weighted
        (di)graph.

        Note that edge weightings can still exist for (di)graphs G where
        G.weighted() is False.

        EXAMPLES: Here we have two graphs with different labels, but
        weighted is False for both, so we just check for the presence of
        edges::

            sage: G = Graph({0:{1:'a'}},sparse=True)
            sage: H = Graph({0:{1:'b'}},sparse=True)
            sage: G == H
            True

        Now one is weighted and the other is not, and thus the
        graphs are not equal::

            sage: G.weighted(True)
            sage: H.weighted()
            False
            sage: G == H
            False

        However, if both are weighted, then we finally compare 'a' to 'b'.

        ::

            sage: H.weighted(True)
            sage: G == H
            False
        """
        if new is not None:
            if new:
                self._weighted = new
        else:
            return self._weighted

    ### Properties

    def antisymmetric(self):
        r"""
        Returns True if the relation given by the graph is antisymmetric
        and False otherwise.

        A graph represents an antisymmetric relation if there being a path
        from a vertex x to a vertex y implies that there is not a path from
        y to x unless x=y.

        A directed acyclic graph is antisymmetric. An undirected graph is
        never antisymmetric unless it is just a union of isolated
        vertices.

        ::

            sage: graphs.RandomGNP(20,0.5).antisymmetric()
            False
            sage: digraphs.RandomDirectedGNR(20,0.5).antisymmetric()
            True
        """
        if not self._directed:
            if self.size()-len(self.loop_edges())>0:
                return False
            else:
                return True
        from copy import copy
        g = copy(self)
        g.allow_multiple_edges(False)
        g.allow_loops(False)
        g = g.transitive_closure()
        gpaths = g.edges(labels=False)
        for e in gpaths:
            if (e[1],e[0]) in gpaths:
                return False
        return True

    def density(self):
        """
        Returns the density (number of edges divided by number of possible
        edges).

        In the case of a multigraph, raises an error, since there is an
        infinite number of possible edges.

        EXAMPLES::

            sage: d = {0: [1,4,5], 1: [2,6], 2: [3,7], 3: [4,8], 4: [9], 5: [7, 8], 6: [8,9], 7: [9]}
            sage: G = Graph(d); G.density()
            1/3
            sage: G = Graph({0:[1,2], 1:[0] }); G.density()
            2/3
            sage: G = DiGraph({0:[1,2], 1:[0] }); G.density()
            1/2

        Note that there are more possible edges on a looped graph::

            sage: G.allow_loops(True)
            sage: G.density()
            1/3
        """
        if self.has_multiple_edges():
            raise TypeError("Density is not well-defined for multigraphs.")
        from sage.rings.rational import Rational
        n = self.order()
        if self.allows_loops():
            if self._directed:
                return Rational(self.size())/Rational(n**2)
            else:
                return Rational(self.size())/Rational((n**2 + n)/2)
        else:
            if self._directed:
                return Rational(self.size())/Rational((n**2 - n))
            else:
                return Rational(self.size())/Rational((n**2 - n)/2)

    def is_eulerian(self):
        """
        Return true if the graph has an tour that visits each edge exactly
        once.

        EXAMPLES::

            sage: graphs.CompleteGraph(4).is_eulerian()
            False
            sage: graphs.CycleGraph(4).is_eulerian()
            True
            sage: g = DiGraph({0:[1,2], 1:[2]}); g.is_eulerian()
            False
            sage: g = DiGraph({0:[2], 1:[3], 2:[0,1], 3:[2]}); g.is_eulerian()
            True
        """
        if not self.is_connected():
            return False
        if self._directed:
            for i in self.vertex_iterator():
                # loops don't matter since they count in both the in and out degree.
                if self.in_degree(i) != self.out_degree(i):
                    return False
        else:
            for i in self.degree_iterator():
                # loops don't matter since they add an even number to the degree
                if i % 2 != 0:
                    return False
        return True

    def is_tree(self):
        """
        Return True if the graph is a tree.

        EXAMPLES::

            sage: for g in graphs.trees(6):
            ...     g.is_tree()
            True
            True
            True
            True
            True
            True
        """
        if not self.is_connected():
            return False
        if self.num_verts() != self.num_edges() + 1:
            return False
        return True

    def is_forest(self):
        """
        Return True if the graph is a forest, i.e. a disjoint union of
        trees.

        EXAMPLES::

            sage: seven_acre_wood = sum(graphs.trees(7), Graph())
            sage: seven_acre_wood.is_forest()
            True
        """
        for g in self.connected_components_subgraphs():
            if not g.is_tree():
                return False
        return True

    def is_overfull(self):
        r"""
        Tests whether the current graph is overfull.

        A graph `G` on `n` vertices and `m` edges is said to
        be overfull if:

        - `n` is odd

        - It satisfies `2m > (n-1)\Delta(G)`, where
          `\Delta(G)` denotes the maximum degree
          among all vertices in `G`.

        An overfull graph must have a chromatic index of `\Delta(G)+1`.

        EXAMPLES:

        A complete graph of order `n > 1` is overfull if and only if `n` is
        odd::

            sage: graphs.CompleteGraph(6).is_overfull()
            False
            sage: graphs.CompleteGraph(7).is_overfull()
            True
            sage: graphs.CompleteGraph(1).is_overfull()
            False

        The claw graph is not overfull::

            sage: from sage.graphs.graph_coloring import edge_coloring
            sage: g = graphs.ClawGraph()
            sage: g
            Claw graph: Graph on 4 vertices
            sage: edge_coloring(g, value_only=True)
            3
            sage: g.is_overfull()
            False

        Checking that all complete graphs `K_n` for even `0 \leq n \leq 100`
        are not overfull::

            sage: def check_overfull_Kn_even(n):
            ...       i = 0
            ...       while i <= n:
            ...           if graphs.CompleteGraph(i).is_overfull():
            ...               print "A complete graph of even order cannot be overfull."
            ...               return
            ...           i += 2
            ...       print "Complete graphs of even order up to %s are not overfull." % n
            ...
            sage: check_overfull_Kn_even(100)  # long time
            Complete graphs of even order up to 100 are not overfull.

        The null graph, i.e. the graph with no vertices, is not overfull::

            sage: Graph().is_overfull()
            False
            sage: graphs.CompleteGraph(0).is_overfull()
            False

        Checking that all complete graphs `K_n` for odd `1 < n \leq 100`
        are overfull::

            sage: def check_overfull_Kn_odd(n):
            ...       i = 3
            ...       while i <= n:
            ...           if not graphs.CompleteGraph(i).is_overfull():
            ...               print "A complete graph of odd order > 1 must be overfull."
            ...               return
            ...           i += 2
            ...       print "Complete graphs of odd order > 1 up to %s are overfull." % n
            ...
            sage: check_overfull_Kn_odd(100)  # long time
            Complete graphs of odd order > 1 up to 100 are overfull.

        The Petersen Graph, though, is not overfull while
        its chromatic index is `\Delta+1`::

            sage: g = graphs.PetersenGraph()
            sage: g.is_overfull()
            False
            sage: from sage.graphs.graph_coloring import edge_coloring
            sage: max(g.degree()) + 1 ==  edge_coloring(g, value_only=True)
            True
        """
        # # A possible optimized version. But the gain in speed is very little.
        # return bool(self._backend.num_verts() & 1) and (  # odd order n
        #     2 * self._backend.num_edges(self._directed) > #2m > \Delta(G)*(n-1)
        #     max(self.degree()) * (self._backend.num_verts() - 1))
        # unoptimized version
        return (self.order() % 2 == 1) and (
            2 * self.size() > max(self.degree()) * (self.order() - 1))

    def order(self):
        """
        Returns the number of vertices. Note that len(G) returns the number
        of vertices in G also.

        EXAMPLES::

            sage: G = graphs.PetersenGraph()
            sage: G.order()
            10

        ::

            sage: G = graphs.TetrahedralGraph()
            sage: len(G)
            4
        """
        return self._backend.num_verts()

    __len__ = order

    num_verts = order

    def size(self):
        """
        Returns the number of edges.

        EXAMPLES::

            sage: G = graphs.PetersenGraph()
            sage: G.size()
            15
        """
        return self._backend.num_edges(self._directed)

    num_edges = size

    ### Orientations

    def eulerian_orientation(self):
        r"""
        Returns a DiGraph which is an eulerian orientation of the current graph.

        An eulerian graph being a graph such that any vertex has an even degree,
        an eulerian orientation of a graph is an orientation of its edges such
        that each vertex `v` verifies `d^+(v)=d^-(v)=d(v)/2`, where `d^+` and
        `d^-` respectively represent the out-degree and the in-degree of a vertex.

        If the graph is not eulerian, the orientation verifies for any vertex `v`
        that `| d^+(v)-d^-(v) | \leq 1`.

        ALGORITHM:

        This algorithm is a random walk through the edges of the graph, which
        orients the edges according to the walk. When a vertex is reached which
        has no non-oriented edge ( this vertex must have odd degree ), the
        walk resumes at another vertex of odd degree, if any.

        This algorithm has complexity `O(m)`, where `m` is the number of edges
        in the graph.

        EXAMPLES:

        The CubeGraph with parameter 4, which is regular of even degree, has an
        eulerian orientation such that `d^+=d^-`::

            sage: g=graphs.CubeGraph(4)
            sage: g.degree()
            [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4]
            sage: o=g.eulerian_orientation()
            sage: o.in_degree()
            [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2]
            sage: o.out_degree()
            [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2]

        Secondly, the Petersen Graph, which is 3 regular has an orientation
        such that the difference between `d^+` and `d^-` is at most 1::

            sage: g=graphs.PetersenGraph()
            sage: o=g.eulerian_orientation()
            sage: o.in_degree()
            [2, 2, 2, 2, 2, 1, 1, 1, 1, 1]
            sage: o.out_degree()
            [1, 1, 1, 1, 1, 2, 2, 2, 2, 2]
        """
        from copy import copy
        g=copy(self)
        from sage.graphs.digraph import DiGraph
        d=DiGraph()
        d.add_vertices(g.vertex_iterator())


        # list of vertices of odd degree
        from itertools import izip
        odd=[x for (x,deg) in izip(g.vertex_iterator(),g.degree_iterator()) if deg%2==1]

        # Picks the first vertex, which is preferably an odd one
        if len(odd)>0:
            v=odd.pop()
        else:
            v=g.edge_iterator(labels=None).next()[0]
            odd.append(v)
        # Stops when there is no edge left
        while True:

            # If there is an edge adjacent to the current one
            if g.degree(v)>0:
                e = g.edge_iterator(v).next()
                g.delete_edge(e)
                if e[0]!=v:
                    e=(e[1],e[0],e[2])
                d.add_edge(e)
                v=e[1]

            # The current vertex is isolated
            else:
                odd.remove(v)

                # jumps to another odd vertex if possible
                if len(odd)>0:
                    v=odd.pop()
                # Else jumps to an ever vertex which is not isolated
                elif g.size()>0:
                    v=g.edge_iterator().next()[0]
                    odd.append(v)
                # If there is none, we are done !
                else:
                    return d

    def spanning_trees_count(self, root_vertex=None):
        """
        Returns the number of spanning trees in a graph. In the case of a
        digraph, counts the number of spanning out-trees rooted in
        ``root_vertex``.
        Default is to set first vertex as root.

        This computation uses Kirchhoff's Matrix Tree Theorem [1] to calculate
        the number of spanning trees. For complete graphs on `n` vertices the
        result can also be reached using Cayley's formula: the number of
        spanning trees are `n^(n-2)`.

        For digraphs, the augmented Kirchhoff Matrix as defined in [2] is
        used for calculations. Here the result is the number of out-trees
        rooted at a specific vertex.

        INPUT:

        - ``root_vertex`` -- integer (default: the first vertex) This is the vertex
          that will be used as root for all spanning out-trees if the graph
          is a directed graph.  This argument is ignored if the graph is not a digraph.

        REFERENCES:

        - [1] http://mathworld.wolfram.com/MatrixTreeTheorem.html

        - [2] Lih-Hsing Hsu, Cheng-Kuan Lin, "Graph Theory and
          Interconnection Networks"

        AUTHORS:

        - Anders Jonsson (2009-10-10)

        EXAMPLES::

            sage: G = graphs.PetersenGraph()
            sage: G.spanning_trees_count()
            2000

        ::

            sage: n = 11
            sage: G = graphs.CompleteGraph(n)
            sage: ST = G.spanning_trees_count()
            sage: ST == n^(n-2)
            True

        ::

            sage: M=matrix(3,3,[0,1,0,0,0,1,1,1,0])
            sage: D=DiGraph(M)
            sage: D.spanning_trees_count()
            1
            sage: D.spanning_trees_count(0)
            1
            sage: D.spanning_trees_count(2)
            2

        """
        if self.is_directed() == False:
            M=self.kirchhoff_matrix()
            M.subdivide(1,1)
            M2 = M.subdivision(1,1)
            return abs(M2.determinant())
        else:
            if root_vertex == None:
                root_vertex=self.vertex_iterator().next()
            if root_vertex not in self.vertices():
                raise ValueError, ("Vertex (%s) not in the graph."%root_vertex)

            M=self.kirchhoff_matrix()

            index=self.vertices().index(root_vertex)
            M[index,index]+=1
            return abs(M.determinant())

    def cycle_basis(self):
        r"""
        Returns a list of cycles which form a basis of the cycle space
        of ``self``.

        A basis of cycles of a graph is a minimal collection of cycles
        (considered as sets of edges) such that the edge set of any
        cycle in the graph can be written as a `Z/2Z` sum of the
        cycles in the basis.

        OUTPUT:

        A list of lists, each of them representing the vertices of a
        cycle in a basis.

        ALGORITHM:

        Uses the NetworkX library.

        EXAMPLE:

        A cycle basis in Petersen's Graph ::

            sage: g = graphs.PetersenGraph()
            sage: g.cycle_basis()
            [[1, 2, 7, 5, 0], [8, 3, 2, 7, 5], [4, 3, 2, 7, 5, 0], [4, 9, 7, 5, 0], [8, 6, 9, 7, 5], [1, 6, 9, 7, 5, 0]]

        Checking the given cycles are algebraically free::

            sage: g = graphs.RandomGNP(30,.4)
            sage: basis = g.cycle_basis()

        Building the space of (directed) edges over `Z/2Z`. On the way,
        building a dictionary associating an unique vector to each
        undirected edge::

            sage: m = g.size()
            sage: edge_space = VectorSpace(FiniteField(2),m)
            sage: edge_vector = dict( zip( g.edges(labels = False), edge_space.basis() ) )
            sage: for (u,v),vec in edge_vector.items():
            ...      edge_vector[(v,u)] = vec

        Defining a lambda function associating a vector to the
        vertices of a cycle::

            sage: vertices_to_edges = lambda x : zip( x, x[1:] + [x[0]] )
            sage: cycle_to_vector = lambda x : sum( edge_vector[e] for e in vertices_to_edges(x) )

        Finally checking the cycles are a free set::

            sage: basis_as_vectors = map( cycle_to_vector, basis )
            sage: edge_space.span(basis_as_vectors).rank() == len(basis)
            True
        """

        import networkx
        return networkx.cycle_basis(self.networkx_graph(copy=False))

    def minimum_outdegree_orientation(self, use_edge_labels=False, solver=None, verbose=0):
        r"""
        Returns a DiGraph which is an orientation with the smallest
        possible maximum outdegree of the current graph.

        Given a Graph `G`, is is polynomial to compute an orientation
        `D` of the edges of `G` such that the maximum out-degree in
        `D` is minimized. This problem, though, is NP-complete in the
        weighted case [AMOZ06]_.

        INPUT:

        - ``use_edge_labels`` -- boolean (default: ``False``)

          - When set to ``True``, uses edge labels as weights to
            compute the orientation and assumes a weight of `1`
            when there is no value available for a given edge.

          - When set to ``False`` (default), gives a weight of 1
            to all the edges.

        - ``solver`` -- (default: ``None``) Specify a Linear Program (LP)
          solver to be used. If set to ``None``, the default one is used. For
          more information on LP solvers and which default solver is used, see
          the method
          :meth:`solve <sage.numerical.mip.MixedIntegerLinearProgram.solve>`
          of the class
          :class:`MixedIntegerLinearProgram <sage.numerical.mip.MixedIntegerLinearProgram>`.

        - ``verbose`` -- integer (default: ``0``). Sets the level of
          verbosity. Set to 0 by default, which means quiet.

        EXAMPLE:

        Given a complete bipartite graph `K_{n,m}`, the maximum out-degree
        of an optimal orientation is `\left\lceil \frac {nm} {n+m}\right\rceil`::

            sage: g = graphs.CompleteBipartiteGraph(3,4)
            sage: o = g.minimum_outdegree_orientation()
            sage: max(o.out_degree()) == ceil((4*3)/(3+4))
            True

        REFERENCES:

        .. [AMOZ06] Asahiro, Y. and Miyano, E. and Ono, H. and Zenmyo, K.
          Graph orientation algorithms to minimize the maximum outdegree
          Proceedings of the 12th Computing: The Australasian Theory Symposium
          Volume 51, page 20
          Australian Computer Society, Inc. 2006
        """

        if self.is_directed():
            raise ValueError("Cannot compute an orientation of a DiGraph. "+\
                                 "Please convert it to a Graph if you really mean it.")

        if use_edge_labels:
            from sage.rings.real_mpfr import RR
            weight = lambda u,v : self.edge_label(u,v) if self.edge_label(u,v) in RR else 1
        else:
            weight = lambda u,v : 1

        from sage.numerical.mip import MixedIntegerLinearProgram, Sum

        p = MixedIntegerLinearProgram(maximization=False)

        # The orientation of an edge is boolean
        # and indicates whether the edge uv
        # with u<v goes from u to v ( equal to 0 )
        # or from v to u ( equal to 1)
        orientation = p.new_variable(dim=2)

        degree = p.new_variable()

        # Whether an edge adjacent to a vertex u counts
        # positively or negatively
        outgoing = lambda u,v,variable : (1-variable) if u>v else variable

        for u in self:
            p.add_constraint(Sum([weight(u,v)*outgoing(u,v,orientation[min(u,v)][max(u,v)]) for v in self.neighbors(u)])-degree['max'],max=0)

        p.set_objective(degree['max'])

        p.set_binary(orientation)

        p.solve(solver=solver, log=verbose)

        orientation = p.get_values(orientation)

        # All the edges from self are doubled in O
        # ( one in each direction )
        from sage.graphs.digraph import DiGraph
        O = DiGraph(self)

        # Builds the list of edges that should be removed
        edges=[]

        for u,v in self.edge_iterator(labels=None):
            # assumes u<v
            if u>v:
                u,v=v,u

            if orientation[min(u,v)][max(u,v)] == 1:
                edges.append((max(u,v),min(u,v)))
            else:
                edges.append((min(u,v),max(u,v)))

        O.delete_edges(edges)

        return O

    ### Planarity

    def is_planar(self, on_embedding=None, kuratowski=False, set_embedding=False, set_pos=False):
        """
        Returns True if the graph is planar, and False otherwise. This
        wraps the reference implementation provided by John Boyer of the
        linear time planarity algorithm by edge addition due to Boyer
        Myrvold. (See reference code in graphs.planarity).

        Note - the argument on_embedding takes precedence over
        set_embedding. This means that only the on_embedding
        combinatorial embedding will be tested for planarity and no
        _embedding attribute will be set as a result of this function
        call, unless on_embedding is None.

        REFERENCE:

        - [1] John M. Boyer and Wendy J. Myrvold, On the Cutting Edge:
          Simplified O(n) Planarity by Edge Addition. Journal of Graph
          Algorithms and Applications, Vol. 8, No. 3, pp. 241-273,
          2004.

        INPUT:


        -  ``kuratowski`` - returns a tuple with boolean as
           first entry. If the graph is nonplanar, will return the Kuratowski
           subgraph or minor as the second tuple entry. If the graph is
           planar, returns None as the second entry.

        -  ``on_embedding`` - the embedding dictionary to test
           planarity on. (i.e.: will return True or False only for the given
           embedding.)

        -  ``set_embedding`` - whether or not to set the
           instance field variable that contains a combinatorial embedding
           (clockwise ordering of neighbors at each vertex). This value will
           only be set if a planar embedding is found. It is stored as a
           Python dict: v1: [n1,n2,n3] where v1 is a vertex and n1,n2,n3 are
           its neighbors.

        -  ``set_pos`` - whether or not to set the position
           dictionary (for plotting) to reflect the combinatorial embedding.
           Note that this value will default to False if set_emb is set to
           False. Also, the position dictionary will only be updated if a
           planar embedding is found.


        EXAMPLES::

            sage: g = graphs.CubeGraph(4)
            sage: g.is_planar()
            False

        ::

            sage: g = graphs.CircularLadderGraph(4)
            sage: g.is_planar(set_embedding=True)
            True
            sage: g.get_embedding()
            {0: [1, 4, 3],
             1: [2, 5, 0],
             2: [3, 6, 1],
             3: [0, 7, 2],
             4: [0, 5, 7],
             5: [1, 6, 4],
             6: [2, 7, 5],
             7: [4, 6, 3]}

        ::

            sage: g = graphs.PetersenGraph()
            sage: (g.is_planar(kuratowski=True))[1].adjacency_matrix()
            [0 1 0 0 0 1 0 0 0]
            [1 0 1 0 0 0 1 0 0]
            [0 1 0 1 0 0 0 1 0]
            [0 0 1 0 0 0 0 0 1]
            [0 0 0 0 0 0 1 1 0]
            [1 0 0 0 0 0 0 1 1]
            [0 1 0 0 1 0 0 0 1]
            [0 0 1 0 1 1 0 0 0]
            [0 0 0 1 0 1 1 0 0]

        ::

            sage: k43 = graphs.CompleteBipartiteGraph(4,3)
            sage: result = k43.is_planar(kuratowski=True); result
            (False, Graph on 6 vertices)
            sage: result[1].is_isomorphic(graphs.CompleteBipartiteGraph(3,3))
            True

        Multi-edged and looped graphs are partially supported::

            sage: G = Graph({0:[1,1]}, multiedges=True)
            sage: G.is_planar()
            True
            sage: G.is_planar(on_embedding={})
            Traceback (most recent call last):
            ...
            NotImplementedError: Cannot compute with embeddings of multiple-edged or looped graphs.
            sage: G.is_planar(set_pos=True)
            Traceback (most recent call last):
            ...
            NotImplementedError: Cannot compute with embeddings of multiple-edged or looped graphs.
            sage: G.is_planar(set_embedding=True)
            Traceback (most recent call last):
            ...
            NotImplementedError: Cannot compute with embeddings of multiple-edged or looped graphs.
            sage: G.is_planar(kuratowski=True)
            (True, None)

        ::

            sage: G = graphs.CompleteGraph(5)
            sage: G = Graph(G, multiedges=True)
            sage: G.add_edge(0,1)
            sage: G.is_planar()
            False
            sage: b,k = G.is_planar(kuratowski=True)
            sage: b
            False
            sage: k.vertices()
            [0, 1, 2, 3, 4]

        """
        if self.has_multiple_edges() or self.has_loops():
            if set_embedding or (on_embedding is not None) or set_pos:
                raise NotImplementedError("Cannot compute with embeddings of multiple-edged or looped graphs.")
            else:
                return self.to_simple().is_planar(kuratowski=kuratowski)
        if on_embedding:
            if self.check_embedding_validity(on_embedding):
                return (0 == self.genus(minimal=False,set_embedding=False,on_embedding=on_embedding))
            else:
                raise Exception('on_embedding is not a valid embedding for %s.'%self)
        else:
            from sage.graphs.planarity import is_planar
            G = self.to_undirected()
            planar = is_planar(G,kuratowski=kuratowski,set_pos=set_pos,set_embedding=set_embedding)
            if kuratowski:
                bool_result = planar[0]
            else:
                bool_result = planar
            if bool_result:
                if set_pos:
                    self._pos = G._pos
                if set_embedding:
                    self._embedding = G._embedding
            return planar

    def is_circular_planar(self, ordered=True, on_embedding=None, kuratowski=False, set_embedding=False, set_pos=False):
        """
        A graph (with nonempty boundary) is circular planar if it has a
        planar embedding in which all boundary vertices can be drawn in
        order on a disc boundary, with all the interior vertices drawn
        inside the disc.

        Returns True if the graph is circular planar, and False if it is
        not. If kuratowski is set to True, then this function will return a
        tuple, with boolean first entry and second entry the Kuratowski
        subgraph or minor isolated by the Boyer-Myrvold algorithm. Note
        that this graph might contain a vertex or edges that were not in
        the initial graph. These would be elements referred to below as
        parts of the wheel and the star, which were added to the graph to
        require that the boundary can be drawn on the boundary of a disc,
        with all other vertices drawn inside (and no edge crossings). For
        more information, refer to reference [2].

        This is a linear time algorithm to test for circular planarity. It
        relies on the edge-addition planarity algorithm due to
        Boyer-Myrvold. We accomplish linear time for circular planarity by
        modifying the graph before running the general planarity
        algorithm.

        REFERENCE:

        - [1] John M. Boyer and Wendy J. Myrvold, On the Cutting Edge:
          Simplified O(n) Planarity by Edge Addition. Journal of Graph
          Algorithms and Applications, Vol. 8, No. 3, pp. 241-273,
          2004.

        - [2] Kirkman, Emily A. O(n) Circular Planarity
          Testing. [Online] Available: soon!

        INPUT:


        -  ``ordered`` - whether or not to consider the order
           of the boundary (set ordered=False to see if there is any possible
           boundary order that will satisfy circular planarity)

        -  ``kuratowski`` - if set to True, returns a tuple
           with boolean first entry and the Kuratowski subgraph or minor as
           the second entry. See notes above.

        -  ``on_embedding`` - the embedding dictionary to test
           planarity on. (i.e.: will return True or False only for the given
           embedding.)

        -  ``set_embedding`` - whether or not to set the
           instance field variable that contains a combinatorial embedding
           (clockwise ordering of neighbors at each vertex). This value will
           only be set if a circular planar embedding is found. It is stored
           as a Python dict: v1: [n1,n2,n3] where v1 is a vertex and n1,n2,n3
           are its neighbors.

        -  ``set_pos`` - whether or not to set the position
           dictionary (for plotting) to reflect the combinatorial embedding.
           Note that this value will default to False if set_emb is set to
           False. Also, the position dictionary will only be updated if a
           circular planar embedding is found.


        EXAMPLES::

            sage: g439 = Graph({1:[5,7], 2:[5,6], 3:[6,7], 4:[5,6,7]})
            sage: g439.set_boundary([1,2,3,4])
            sage: g439.show(figsize=[2,2], vertex_labels=True, vertex_size=175)
            sage: g439.is_circular_planar()
            False
            sage: g439.is_circular_planar(kuratowski=True)
            (False, Graph on 7 vertices)
            sage: g439.set_boundary([1,2,3])
            sage: g439.is_circular_planar(set_embedding=True, set_pos=False)
            True
            sage: g439.is_circular_planar(kuratowski=True)
            (True, None)
            sage: g439.get_embedding()
            {1: [7, 5],
             2: [5, 6],
             3: [6, 7],
             4: [7, 6, 5],
             5: [4, 2, 1],
             6: [4, 3, 2],
             7: [3, 4, 1]}

        Order matters::

            sage: K23 = graphs.CompleteBipartiteGraph(2,3)
            sage: K23.set_boundary([0,1,2,3])
            sage: K23.is_circular_planar()
            False
            sage: K23.is_circular_planar(ordered=False)
            True
            sage: K23.set_boundary([0,2,1,3]) # Diff Order!
            sage: K23.is_circular_planar(set_embedding=True)
            True

        For graphs without a boundary, circular planar is the same as planar::

            sage: g = graphs.KrackhardtKiteGraph()
            sage: g.is_circular_planar()
            True

        """
        boundary = self.get_boundary()
        if not boundary:
            return self.is_planar(on_embedding, kuratowski, set_embedding, set_pos)

        from sage.graphs.planarity import is_planar
        graph = self.to_undirected()
        if hasattr(graph, '_embedding'):
            del(graph._embedding)

        extra = 0
        while graph.has_vertex(extra):
            extra=extra+1
        graph.add_vertex(extra)

        for vertex in boundary:
            graph.add_edge(vertex,extra)

        extra_edges = []
        if ordered: # WHEEL
            for i in range(len(boundary)-1):
                if not graph.has_edge(boundary[i],boundary[i+1]):
                    graph.add_edge(boundary[i],boundary[i+1])
                    extra_edges.append((boundary[i],boundary[i+1]))
            if not graph.has_edge(boundary[-1],boundary[0]):
                graph.add_edge(boundary[-1],boundary[0])
                extra_edges.append((boundary[-1],boundary[0]))
        # else STAR (empty list of extra edges)

        result = is_planar(graph,kuratowski=kuratowski,set_embedding=set_embedding,circular=True)

        if kuratowski:
            bool_result = result[0]
        else:
            bool_result = result

        if bool_result:
            graph.delete_vertex(extra)
            graph.delete_edges(extra_edges)

            if hasattr(graph,'_embedding'):
                # strip the embedding to fit original graph
                for u,v in extra_edges:
                    graph._embedding[u].pop(graph._embedding[u].index(v))
                    graph._embedding[v].pop(graph._embedding[v].index(u))
                for w in boundary:
                    graph._embedding[w].pop(graph._embedding[w].index(extra))

                if set_embedding:
                    self._embedding = graph._embedding

            if (set_pos and set_embedding):
                self.set_planar_positions()
        return result

    # TODO: rename into _layout_planar
    def set_planar_positions(self, test = False, **layout_options):
        """
        Compute a planar layout for self using Schnyder's algorithm,
        and save it as default layout.

        EXAMPLES::

            sage: g = graphs.CycleGraph(7)
            sage: g.set_planar_positions(test=True)
            True

        This method is deprecated. Please use instead:

            sage: g.layout(layout = "planar", save_pos = True)
            {0: [1, 1], 1: [2, 2], 2: [3, 2], 3: [1, 4], 4: [5, 1], 5: [0, 5], 6: [1, 0]}
        """
        self.layout(layout = "planar", save_pos = True, test = test, **layout_options)
        if test:    # Optional error-checking, ( looking for edge-crossings O(n^2) ).
            return self.is_drawn_free_of_edge_crossings() # returns true if tests pass
        else:
            return

    def layout_planar(self, set_embedding=False, on_embedding=None, external_face=None, test=False, circular=False, **options):
        """
        Uses Schnyder's algorithm to compute a planar layout for self,
        raising an error if self is not planar.

        INPUT:

        -  ``set_embedding`` - if True, sets the combinatorial
           embedding used (see self.get_embedding())

        -  ``on_embedding`` - dict: provide a combinatorial
           embedding

        -  ``external_face`` - ignored

        -  ``test`` - if True, perform sanity tests along the way

        -  ``circular`` - ignored


        EXAMPLES::

            sage: g = graphs.PathGraph(10)
            sage: g.set_planar_positions(test=True)
            True
            sage: g = graphs.BalancedTree(3,4)
            sage: g.set_planar_positions(test=True)
            True
            sage: g = graphs.CycleGraph(7)
            sage: g.set_planar_positions(test=True)
            True
            sage: g = graphs.CompleteGraph(5)
            sage: g.set_planar_positions(test=True,set_embedding=True)
            Traceback (most recent call last):
            ...
            Exception: Complete graph is not a planar graph.
        """
        from sage.graphs.schnyder import _triangulate, _normal_label, _realizer, _compute_coordinates

        G = self.to_undirected()
        try:
            G._embedding = self._embedding
        except AttributeError:
            pass
        embedding_copy = None
        if set_embedding:
            if not (G.is_planar(set_embedding=True)):
                raise Exception('%s is not a planar graph.'%self)
            embedding_copy = G._embedding
        else:
            if on_embedding is not None:
                if G.check_embedding_validity(on_embedding):
                    if not (G.is_planar(on_embedding=on_embedding)):
                        raise Exception( 'Provided embedding is not a planar embedding for %s.'%self )
                else:
                    raise Exception('Provided embedding is not a valid embedding for %s. Try putting set_embedding=True.'%self)
            else:
                if hasattr(G,'_embedding'):
                    if G.check_embedding_validity():
                        if not (G.is_planar(on_embedding=G._embedding)):
                            raise Exception('%s has nonplanar _embedding attribute.  Try putting set_embedding=True.'%self)
                        embedding_copy = G._embedding
                    else:
                        raise Exception('Provided embedding is not a valid embedding for %s. Try putting set_embedding=True.'%self)
                else:
                    G.is_planar(set_embedding=True)

        # The following is what was breaking the code.  It is where we were specifying the external
        #       face ahead of time.  This is definitely a TODO:
        #
        # Running is_planar(set_embedding=True) has set attribute self._embedding
        #if external_face is None:
        #    faces = trace_faces( self, self._embedding )
        #    faces.sort(key=len)
        #    external_face = faces[-1]

        #n = len(external_face)
        #other_added_edges = []
        #if n > 3:
        #    v1, v2, v3 = external_face[0][0], external_face[int(n/3)][0], external_face[int(2*n/3)][0]
        #    if not self.has_edge( (v1,v2) ):
        #        self.add_edge( (v1, v2) )
        #        other_added_edges.append( (v1, v2) )
        #    if not self.has_edge( (v2,v3) ):
        #        self.add_edge( (v2, v3) )
        #        other_added_edges.append( (v2, v3) )
        #    if not self.has_edge( (v3,v1) ):
        #        self.add_edge( (v3, v1) )
        #        other_added_edges.append( (v3, v1) )
        #    if not self.is_planar(set_embedding=True): # get new combinatorial embedding (with added edges)
        #        raise Exception('Modified graph %s is not planar.  Try specifying an external face.'%self)

        # Triangulate the graph
        extra_edges = _triangulate( G, G._embedding)

        # Optional error-checking
        if test:
            G.is_planar(set_embedding=True) # to get new embedding
            test_faces = G.trace_faces(G._embedding)
            for face in test_faces:
                if len(face) != 3:
                    raise Exception('BUG: Triangulation returned face: %s'%face)

        G.is_planar(set_embedding=True)
        faces = G.trace_faces(G._embedding)
        # Assign a normal label to the graph
        label = _normal_label( G, G._embedding, faces[0] )

        # Get dictionary of tree nodes from the realizer
        tree_nodes = _realizer( G, label)

        # Compute the coordinates and store in position dictionary (attr self._pos)
        _compute_coordinates( G, tree_nodes )

        # Delete all the edges added to the graph
        #G.delete_edges( extra_edges )
        #self.delete_edges( other_added_edges )

        if embedding_copy is not None:
            self._embedding = embedding_copy

        return G._pos

    def is_drawn_free_of_edge_crossings(self):
        """
        Returns True is the position dictionary for this graph is set and
        that position dictionary gives a planar embedding.

        This simply checks all pairs of edges that don't share a vertex to
        make sure that they don't intersect.

        .. note::

           This function require that _pos attribute is set. (Returns
           False otherwise.)

        EXAMPLES::

            sage: D = graphs.DodecahedralGraph()
            sage: D.set_planar_positions()
            sage: D.is_drawn_free_of_edge_crossings()
            True
        """
        if self._pos is None:
            return False

        G = self.to_undirected()
        for edge1 in G.edges(labels = False):
            for edge2 in G.edges(labels = False):
                if edge1[0] == edge2[0] or edge1[0] == edge2[1] or edge1[1] == edge2[0] or edge1[1] == edge2[1]:
                    continue
                p1, p2 = self._pos[edge1[0]], self._pos[edge1[1]]
                dy = Rational(p2[1] - p1[1])
                dx = Rational(p2[0] - p1[0])
                q1, q2 = self._pos[edge2[0]], self._pos[edge2[1]]
                db = Rational(q2[1] - q1[1])
                da = Rational(q2[0] - q1[0])
                if(da * dy == db * dx):
                    if dx != 0:
                        t1 = Rational(q1[0] - p1[0])/dx
                        t2 = Rational(q2[0] - p1[0])/dx
                        if (0 <= t1 and t1 <= 1) or (0 <= t2 and t2 <= 1):
                            if p1[1] + t1 * dy == q1[1] or p1[1] + t2 * dy == q2[1]:
                                return False
                    else:
                        t1 = Rational(q1[1] - p1[1])/dy
                        t2 = Rational(q2[1] - p1[1])/dy
                        if (0 <= t1 and t1 <= 1) or (0 <= t2 and t2 <= 1):
                            if p1[0] + t1 * dx == q1[0] or p1[0] + t2 * dx == q2[0]:
                                return False
                else:
                    s = (dx * Rational(q1[1] - p1[1]) + dy * Rational(p1[0] - q1[0])) / (da * dy - db * dx)
                    t = (da * Rational(p1[1] - q1[1]) + db * Rational(q1[0] - p1[0])) / (db * dx - da * dy)

                    if s >= 0 and s <= 1 and t >= 0 and t <= 1:
                        print 'fail on', p1, p2, ' : ',q1, q2
                        print edge1, edge2
                        return False
        return True

    def genus(self, set_embedding=True, on_embedding=None, minimal=True, maximal=False, circular=False, ordered=True):
        """
        Returns the minimal genus of the graph. The genus of a compact
        surface is the number of handles it has. The genus of a graph is
        the minimal genus of the surface it can be embedded into.

        Note - This function uses Euler's formula and thus it is necessary
        to consider only connected graphs.

        INPUT:


        -  ``set_embedding (boolean)`` - whether or not to
           store an embedding attribute of the computed (minimal) genus of the
           graph. (Default is True).

        -  ``on_embedding (dict)`` - a combinatorial embedding
           to compute the genus of the graph on. Note that this must be a
           valid embedding for the graph. The dictionary structure is given
           by: vertex1: [neighbor1, neighbor2, neighbor3], vertex2: [neighbor]
           where there is a key for each vertex in the graph and a (clockwise)
           ordered list of each vertex's neighbors as values. on_embedding
           takes precedence over a stored _embedding attribute if minimal is
           set to False. Note that as a shortcut, the user can enter
           on_embedding=True to compute the genus on the current _embedding
           attribute. (see eg's.)

        -  ``minimal (boolean)`` - whether or not to compute
           the minimal genus of the graph (i.e., testing all embeddings). If
           minimal is False, then either maximal must be True or on_embedding
           must not be None. If on_embedding is not None, it will take
           priority over minimal. Similarly, if maximal is True, it will take
           priority over minimal.

        -  ``maximal (boolean)`` - whether or not to compute
           the maximal genus of the graph (i.e., testing all embeddings). If
           maximal is False, then either minimal must be True or on_embedding
           must not be None. If on_embedding is not None, it will take
           priority over maximal. However, maximal takes priority over the
           default minimal.

        -  ``circular (boolean)`` - whether or not to compute
           the genus preserving a planar embedding of the boundary. (Default
           is False). If circular is True, on_embedding is not a valid
           option.

        -  ``ordered (boolean)`` - if circular is True, then
           whether or not the boundary order may be permuted. (Default is
           True, which means the boundary order is preserved.)


        EXAMPLES::

            sage: g = graphs.PetersenGraph()
            sage: g.genus() # tests for minimal genus by default
            1
            sage: g.genus(on_embedding=True, maximal=True) # on_embedding overrides minimal and maximal arguments
            1
            sage: g.genus(maximal=True) # setting maximal to True overrides default minimal=True
            3
            sage: g.genus(on_embedding=g.get_embedding()) # can also send a valid combinatorial embedding dict
            3
            sage: (graphs.CubeGraph(3)).genus()
            0
            sage: K23 = graphs.CompleteBipartiteGraph(2,3)
            sage: K23.genus()
            0
            sage: K33 = graphs.CompleteBipartiteGraph(3,3)
            sage: K33.genus()
            1

        Using the circular argument, we can compute the minimal genus
        preserving a planar, ordered boundary::

            sage: cube = graphs.CubeGraph(2)
            sage: cube.set_boundary(['01','10'])
            sage: cube.genus()
            0
            sage: cube.is_circular_planar()
            True
            sage: cube.genus(circular=True)
            0
            sage: cube.genus(circular=True, on_embedding=True)
            0
            sage: cube.genus(circular=True, maximal=True)
            Traceback (most recent call last):
            ...
            NotImplementedError: Cannot compute the maximal genus of a genus respecting a boundary.

        Note: not everything works for multigraphs, looped graphs or digraphs.  But the
        minimal genus is ultimately computable for every connected graph -- but the
        embedding we obtain for the simple graph can't be easily converted to an
        embedding of a non-simple graph.  Also, the maximal genus of a multigraph does
        not trivially correspond to that of its simple graph.

            sage: G = DiGraph({ 0 : [0,1,1,1], 1 : [2,2,3,3], 2 : [1,3,3], 3:[0,3]})
            sage: G.genus()
            Traceback (most recent call last):
            ...
            NotImplementedError: Can't work with embeddings of non-simple graphs
            sage: G.to_simple().genus()
            0
            sage: G.genus(set_embedding=False)
            0
            sage: G.genus(maximal=True, set_embedding=False)
            Traceback (most recent call last):
            ...
            NotImplementedError: Can't compute the maximal genus of a graph with loops or multiple edges


        """
        if not self.is_connected():
            raise TypeError("Graph must be connected to use Euler's Formula to compute minimal genus.")

        G = self.to_simple()
        verts = G.order()
        edges = G.size()

        if maximal:
            minimal = False

        if circular:
            if maximal:
                raise NotImplementedError, "Cannot compute the maximal genus of a genus respecting a boundary."
            boundary = G.get_boundary()
            if hasattr(G, '_embedding'):
                del(G._embedding)

            extra = 0
            while G.has_vertex(extra):
                extra=extra+1
            G.add_vertex(extra)
            verts += 1

            for vertex in boundary:
                G.add_edge(vertex,extra)

            extra_edges = []
            if ordered: # WHEEL
                for i in range(len(boundary)-1):
                    if not G.has_edge(boundary[i],boundary[i+1]):
                        G.add_edge(boundary[i],boundary[i+1])
                        extra_edges.append((boundary[i],boundary[i+1]))
                if not G.has_edge(boundary[-1],boundary[0]):
                    G.add_edge(boundary[-1],boundary[0])
                    extra_edges.append((boundary[-1],boundary[0]))
                # else STAR (empty list of extra edges)

            edges = G.size()

        if on_embedding is not None:
            if self.has_loops() or self.is_directed() or self.has_multiple_edges():
                raise NotImplementedError, "Can't work with embeddings of non-simple graphs"
            if on_embedding: #i.e., if on_embedding True (returns False if on_embedding is of type dict)
                if not hasattr(self,'_embedding'):
                    raise Exception("Graph must have attribute _embedding set to compute current (embedded) genus.")
                faces = len(self.trace_faces(self._embedding))
                return (2-verts+edges-faces)/2
            else: # compute genus on the provided dict
                faces = len(self.trace_faces(on_embedding))
                return (2-verts+edges-faces)/2
        else: # then compute either maximal or minimal genus of all embeddings
            import genus

            if set_embedding:
                if self.has_loops() or self.is_directed() or self.has_multiple_edges():
                    raise NotImplementedError, "Can't work with embeddings of non-simple graphs"
                g = genus.simple_connected_graph_genus(G, True, check = False, minimal = minimal)
                self._embedding = G._embedding
                return g
            else:
                if maximal and (self.has_multiple_edges() or self.has_loops()):
                    raise NotImplementedError, "Can't compute the maximal genus of a graph with loops or multiple edges"

                return genus.simple_connected_graph_genus(G, set_embedding = False, check=False, minimal=minimal)



    def trace_faces(self, comb_emb):
        """
        A helper function for finding the genus of a graph. Given a graph
        and a combinatorial embedding (rot_sys), this function will
        compute the faces (returned as a list of lists of edges (tuples) of
        the particular embedding.

        Note - rot_sys is an ordered list based on the hash order of the
        vertices of graph. To avoid confusion, it might be best to set the
        rot_sys based on a 'nice_copy' of the graph.

        INPUT:


        -  ``comb_emb`` - a combinatorial embedding
           dictionary. Format: v1:[v2,v3], v2:[v1], v3:[v1] (clockwise
           ordering of neighbors at each vertex.)


        EXAMPLES::

            sage: T = graphs.TetrahedralGraph()
            sage: T.trace_faces({0: [1, 3, 2], 1: [0, 2, 3], 2: [0, 3, 1], 3: [0, 1, 2]})
            [[(0, 1), (1, 2), (2, 0)],
             [(3, 2), (2, 1), (1, 3)],
             [(2, 3), (3, 0), (0, 2)],
             [(0, 3), (3, 1), (1, 0)]]
        """
        from sage.sets.set import Set

        # Establish set of possible edges
        edgeset = Set([])
        for edge in self.to_undirected().edges():
            edgeset = edgeset.union(Set([(edge[0],edge[1]),(edge[1],edge[0])]))

        # Storage for face paths
        faces = []
        path = []
        for edge in edgeset:
            path.append(edge)
            edgeset -= Set([edge])
            break  # (Only one iteration)

        # Trace faces
        while (len(edgeset) > 0):
            neighbors = comb_emb[path[-1][-1]]
            next_node = neighbors[(neighbors.index(path[-1][-2])+1)%(len(neighbors))]
            tup = (path[-1][-1],next_node)
            if tup == path[0]:
                faces.append(path)
                path = []
                for edge in edgeset:
                    path.append(edge)
                    edgeset -= Set([edge])
                    break  # (Only one iteration)
            else:
                path.append(tup)
                edgeset -= Set([tup])
        if (len(path) != 0): faces.append(path)
        return faces

    ### Connectivity

    def is_connected(self):
        """
        Indicates whether the (di)graph is connected. Note that in a graph,
        path connected is equivalent to connected.

        EXAMPLES::

            sage: G = Graph( { 0 : [1, 2], 1 : [2], 3 : [4, 5], 4 : [5] } )
            sage: G.is_connected()
            False
            sage: G.add_edge(0,3)
            sage: G.is_connected()
            True
            sage: D = DiGraph( { 0 : [1, 2], 1 : [2], 3 : [4, 5], 4 : [5] } )
            sage: D.is_connected()
            False
            sage: D.add_edge(0,3)
            sage: D.is_connected()
            True
            sage: D = DiGraph({1:[0], 2:[0]})
            sage: D.is_connected()
            True
        """
        if self.order() == 0:
            return True

        try:
            return self._backend.is_connected()
        except AttributeError:
            v = self.vertex_iterator().next()
            conn_verts = list(self.depth_first_search(v, ignore_direction=True))
            return len(conn_verts) == self.num_verts()

    def connected_components(self):
        """
        Returns a list of lists of vertices, each list representing a
        connected component. The list is ordered from largest to smallest
        component.

        EXAMPLES::

            sage: G = Graph( { 0 : [1, 3], 1 : [2], 2 : [3], 4 : [5, 6], 5 : [6] } )
            sage: G.connected_components()
            [[0, 1, 2, 3], [4, 5, 6]]
            sage: D = DiGraph( { 0 : [1, 3], 1 : [2], 2 : [3], 4 : [5, 6], 5 : [6] } )
            sage: D.connected_components()
            [[0, 1, 2, 3], [4, 5, 6]]
        """
        seen = set()
        components = []
        for v in self:
            if v not in seen:
                c = self.connected_component_containing_vertex(v)
                seen.update(c)
                components.append(c)
        components.sort(lambda comp1, comp2: cmp(len(comp2), len(comp1)))
        return components

    def connected_components_number(self):
        """
        Returns the number of connected components.

        EXAMPLES::

            sage: G = Graph( { 0 : [1, 3], 1 : [2], 2 : [3], 4 : [5, 6], 5 : [6] } )
            sage: G.connected_components_number()
            2
            sage: D = DiGraph( { 0 : [1, 3], 1 : [2], 2 : [3], 4 : [5, 6], 5 : [6] } )
            sage: D.connected_components_number()
            2
        """
        return len(self.connected_components())

    def connected_components_subgraphs(self):
        """
        Returns a list of connected components as graph objects.

        EXAMPLES::

            sage: G = Graph( { 0 : [1, 3], 1 : [2], 2 : [3], 4 : [5, 6], 5 : [6] } )
            sage: L = G.connected_components_subgraphs()
            sage: graphs_list.show_graphs(L)
            sage: D = DiGraph( { 0 : [1, 3], 1 : [2], 2 : [3], 4 : [5, 6], 5 : [6] } )
            sage: L = D.connected_components_subgraphs()
            sage: graphs_list.show_graphs(L)
        """
        cc = self.connected_components()
        list = []
        for c in cc:
            list.append(self.subgraph(c, inplace=False))
        return list

    def connected_component_containing_vertex(self, vertex):
        """
        Returns a list of the vertices connected to vertex.

        EXAMPLES::

            sage: G = Graph( { 0 : [1, 3], 1 : [2], 2 : [3], 4 : [5, 6], 5 : [6] } )
            sage: G.connected_component_containing_vertex(0)
            [0, 1, 2, 3]
            sage: D = DiGraph( { 0 : [1, 3], 1 : [2], 2 : [3], 4 : [5, 6], 5 : [6] } )
            sage: D.connected_component_containing_vertex(0)
            [0, 1, 2, 3]
        """
        try:
            c = list(self._backend.depth_first_search(vertex, ignore_direction=True))
        except AttributeError:
            c = list(self.depth_first_search(vertex, ignore_direction=True))

        c.sort()
        return c

    def blocks_and_cut_vertices(self):
        """
        Computes the blocks and cut vertices of the graph. In the case of a
        digraph, this computation is done on the underlying graph.

        A cut vertex is one whose deletion increases the number of
        connected components. A block is a maximal induced subgraph which
        itself has no cut vertices. Two distinct blocks cannot overlap in
        more than a single cut vertex.

        OUTPUT: ``( B, C )``, where ``B`` is a list of blocks- each is
        a list of vertices and the blocks are the corresponding induced
        subgraphs-and ``C`` is a list of cut vertices.

        EXAMPLES::

            sage: graphs.PetersenGraph().blocks_and_cut_vertices()
            ([[6, 4, 9, 7, 5, 8, 3, 2, 1, 0]], [])
            sage: graphs.PathGraph(6).blocks_and_cut_vertices()
            ([[5, 4], [4, 3], [3, 2], [2, 1], [1, 0]], [4, 3, 2, 1])
            sage: graphs.CycleGraph(7).blocks_and_cut_vertices()
            ([[6, 5, 4, 3, 2, 1, 0]], [])
            sage: graphs.KrackhardtKiteGraph().blocks_and_cut_vertices()
            ([[9, 8], [8, 7], [7, 4, 6, 5, 2, 3, 1, 0]], [8, 7])
            sage: G=Graph()  # make a bowtie graph where 0 is a cut vertex
            sage: G.add_vertices(range(5))
            sage: G.add_edges([(0,1),(0,2),(0,3),(0,4),(1,2),(3,4)])
            sage: G.blocks_and_cut_vertices()
            ([[2, 1, 0], [4, 3, 0]], [0])
            sage: graphs.StarGraph(3).blocks_and_cut_vertices()
            ([[1, 0], [2, 0], [3, 0]], [0])

        TESTS::

            sage: Graph(0).blocks_and_cut_vertices()
            ([], [])
            sage: Graph(1).blocks_and_cut_vertices()
            ([0], [])
            sage: Graph(2).blocks_and_cut_vertices()
            Traceback (most recent call last):
            ...
            NotImplementedError: ...

        ALGORITHM: 8.3.8 in [Jungnickel05]_. Notice that the termination condition on
        line (23) of the algorithm uses ``p[v] == 0`` which in the book
        means that the parent is undefined; in this case, `v` must be the
        root `s`.  Since our vertex names start with `0`, we substitute instead
        the condition ``v == s``.  This is the terminating condition used
        in the general Depth First Search tree in Algorithm 8.2.1.

        REFERENCE:

        .. [Jungnickel05] D. Jungnickel, Graphs, Networks and Algorithms,
          Springer, 2005.
        """
        if not self: # empty graph
            return [],[]

        s = self.vertex_iterator().next() # source

        if len(self) == 1: # only one vertex
            return [s],[]

        if not self.is_connected():
            raise NotImplementedError("Blocks and cut vertices is currently only implemented for connected graphs.")

        nr = {} # enumerate
        p = {} # predecessors
        L = {}
        visited_edges = set()
        i = 1
        v = s # visited
        nr[s] = 1
        L[s] = 1
        C = [] # cuts
        B = [] # blocks
        S = [s] #stack
        its = {}
        while True:
            while True:
                for u in self.neighbor_iterator(v):
                    if not (v,u) in visited_edges: break
                else:
                    break
                visited_edges.add((v,u))
                visited_edges.add((u,v))
                if u not in nr:
                    p[u] = v
                    i += 1
                    nr[u] = i
                    L[u] = i
                    S.append(u)
                    v = u
                else:
                    L[v] = min( L[v], nr[u] )

            if v is s:
                break

            pv = p[v]
            if L[v] < nr[pv]:
                L[pv] = min( L[pv], L[v] )
                v = pv
                continue

            if pv not in C:
                if pv is not s or\
                        not all([(s,u) in visited_edges for u in self.neighbor_iterator(s)]):
                    C.append(pv)

            B_k = []
            while True:
                u = S.pop()
                B_k.append(u)
                if u == v: break
            B_k.append(pv)
            B.append(B_k)

            v = pv
        return B, C


    def steiner_tree(self,vertices, weighted = False):
        r"""
        Returns a tree of minimum weight connecting the given
        set of vertices.

        Definition :

        Computing a minimum spanning tree in a graph can be done in `n
        \log(n)` time (and in linear time if all weights are equal) where
        `n = V + E`. On the other hand, if one is given a large (possibly
        weighted) graph and a subset of its vertices, it is NP-Hard to
        find a tree of minimum weight connecting the given set of
        vertices, which is then called a Steiner Tree.

        `Wikipedia article on Steiner Trees
        <http://en.wikipedia.org/wiki/Steiner_tree_problem>`_.

        INPUT:

        - ``vertices`` -- the vertices to be connected by the Steiner
          Tree.

        - ``weighted`` (boolean) -- Whether to consider the graph as
          weighted, and use each edge's label as a weight, considering
          ``None`` as a weight of `1`. If ``weighted=False`` (default)
          all edges are considered to have a weight of `1`.

        .. NOTE::

            * This problem being defined on undirected graphs, the
              orientation is not considered if the current graph is
              actually a digraph.

            * The graph is assumed not to have multiple edges.

        ALGORITHM:

        Solved through Linear Programming.

        COMPLEXITY:

        NP-Hard.

        Note that this algorithm first checks whether the given
        set of vertices induces a connected graph, returning one of its
        spanning trees if ``weighted`` is set to ``False``, and thus
        answering very quickly in some cases

        EXAMPLES:

        The Steiner Tree of the first 5 vertices in a random graph is,
        of course, always a tree ::

            sage: g = graphs.RandomGNP(30,.5)
            sage: st = g.steiner_tree(g.vertices()[:5])
            sage: st.is_tree()
            True

        And all the 5 vertices are contained in this tree ::

            sage: all([v in st for v in g.vertices()[:5] ])
            True

        An exception is raised when the problem is impossible, i.e.
        if the given vertices are not all included in the same
        connected component ::

            sage: g = 2 * graphs.PetersenGraph()
            sage: st = g.steiner_tree([5,15])
            Traceback (most recent call last):
            ...
            ValueError: The given vertices do not all belong to the same connected component. This problem has no solution !
        """

        if self.is_directed():
            g = Graph(self)
        else:
            g = self

        if g.has_multiple_edges():
            raise ValueError("The graph is expected not to have multiple edges.")

        # Can the problem be solved ? Are all the vertices in the same
        # connected component ?
        cc = g.connected_component_containing_vertex(vertices[0])
        if not all([v in cc for v in vertices]):
            raise ValueError("The given vertices do not all belong to the same connected component. This problem has no solution !")

        # Can it be solved using the min spanning tree algorithm ?
        if not weighted:
            gg = g.subgraph(vertices)
            if gg.is_connected():
                st = g.subgraph(edges = gg.min_spanning_tree())
                st.delete_vertices([v for v in g if st.degree(v) == 0])
                return st

        # Then, LP formulation
        from sage.numerical.mip import MixedIntegerLinearProgram, Sum
        p = MixedIntegerLinearProgram(maximization = False)

        # Reorder an edge
        R = lambda (x,y) : (x,y) if x<y else (y,x)

        # edges used in the Steiner Tree
        edges = p.new_variable()

        # relaxed edges to test for acyclicity
        r_edges = p.new_variable()

        # Whether a vertex is in the Steiner Tree
        vertex = p.new_variable()
        for v in g:
            for e in g.edges_incident(v, labels=False):
                p.add_constraint(vertex[v] - edges[R(e)], min = 0)

        # We must have the given vertices in our tree
        for v in vertices:
            p.add_constraint(Sum([edges[R(e)] for e in g.edges_incident(v,labels=False)]), min=1)

        # The number of edges is equal to the number of vertices in our tree minus 1
        p.add_constraint(Sum([vertex[v] for v in g]) - Sum([edges[R(e)] for e in g.edges(labels=None)]), max = 1, min = 1)

        # There are no cycles in our graph

        for u,v in g.edges(labels = False):
            p.add_constraint( r_edges[(u,v)]+ r_edges[(v,u)] - edges[R((u,v))] , min = 0 )

        eps = 1/(5*Integer(g.order()))
        for v in g:
            p.add_constraint(Sum([r_edges[(u,v)] for u in g.neighbors(v)]), max = 1-eps)


        # Objective
        if weighted:
            w = lambda (x,y) : g.edge_label(x,y) if g.edge_label(x,y) is not None else 1
        else:
            w = lambda (x,y) : 1

        p.set_objective(Sum([w(e)*edges[R(e)] for e in g.edges(labels = False)]))

        p.set_binary(edges)
        p.solve()

        edges = p.get_values(edges)

        st =  g.subgraph(edges=[e for e in g.edges(labels = False) if edges[R(e)] == 1])
        st.delete_vertices([v for v in g if st.degree(v) == 0])
        return st

    def edge_disjoint_spanning_trees(self,k, root=None, **kwds):
        r"""
        Returns the desired number of edge-disjoint spanning
        trees/arborescences.

        INPUT:

        - ``k`` (integer) -- the required number of edge-disjoint
          spanning trees/arborescences

        - ``root`` (vertex) -- root of the disjoint arborescences
          when the graph is directed.
          If set to ``None``, the first vertex in the graph is picked.

        - ``**kwds`` -- arguments to be passed down to the ``solve``
          function of ``MixedIntegerLinearProgram``. See the documentation
          of ``MixedIntegerLinearProgram.solve`` for more informations.

        ALGORITHM:

        Mixed Integer Linear Program. The formulation can be found
        in [JVNC]_.

        There are at least two possible rewritings of this method
        which do not use Linear Programming:

            * The algorithm presented in the paper entitled "A short
              proof of the tree-packing theorem", by Thomas Kaiser
              [KaisPacking]_.

            * The implementation of a Matroid class and of the Matroid
              Union Theorem (see section 42.3 of [SchrijverCombOpt]_),
              applied to the cycle Matroid (see chapter 51 of
              [SchrijverCombOpt]_).

        EXAMPLES:

        The Petersen Graph does have a spanning tree (it is connected)::

            sage: g = graphs.PetersenGraph()
            sage: [T] = g.edge_disjoint_spanning_trees(1)
            sage: T.is_tree()
            True

        Though, it does not have 2 edge-disjoint trees (as it has less
        than `2(|V|-1)` edges)::

            sage: g.edge_disjoint_spanning_trees(2)
            Traceback (most recent call last):
            ...
            ValueError: This graph does not contain the required number of trees/arborescences !

        By Edmond's theorem, a graph which is `k`-connected always has `k` edge-disjoint
        arborescences, regardless of the root we pick::

            sage: g = digraphs.RandomDirectedGNP(28,.3) # reduced from 30 to 28, cf. #9584
            sage: k = Integer(g.edge_connectivity())
            sage: arborescences = g.edge_disjoint_spanning_trees(k)
            sage: all([a.is_directed_acyclic() for a in arborescences])
            True
            sage: all([a.is_connected() for a in arborescences])
            True

        In the undirected case, we can only ensure half of it::

            sage: g = graphs.RandomGNP(30,.3)
            sage: k = floor(Integer(g.edge_connectivity())/2)
            sage: trees = g.edge_disjoint_spanning_trees(k)
            sage: all([t.is_tree() for t in trees])
            True

        REFERENCES:

        .. [JVNC] David Joyner, Minh Van Nguyen, and Nathann Cohen,
          Algorithmic Graph Theory,
          http://code.google.com/p/graph-theory-algorithms-book/

        .. [KaisPacking] Thomas Kaiser
          A short proof of the tree-packing theorem
          http://arxiv.org/abs/0911.2809

        .. [SchrijverCombOpt] Alexander Schrijver
          Combinatorial optimization: polyhedra and efficiency
          2003
        """

        from sage.numerical.mip import MixedIntegerLinearProgram, MIPSolverException, Sum
        p = MixedIntegerLinearProgram()
        p.set_objective(None)

        # The colors we can use
        colors = range(0,k)

        # edges[j][e] is equal to one if and only if edge e belongs to color j
        edges = p.new_variable(dim=2)


        # r_edges is a relaxed variable grater than edges. It is used to
        # check the presence of cycles
        r_edges = p.new_variable(dim=2)

        epsilon = 1/(10*(Integer(self.order())))


        if self.is_directed():
            # Does nothing ot an edge.. Useful when out of "if self.directed"
            S = lambda (x,y) : (x,y)

            if root == None:
                root = self.vertex_iterator().next()


            # An edge belongs to at most arborescence
            for e in self.edges(labels=False):
                p.add_constraint(Sum([edges[j][e] for j in colors]), max=1)


            for j in colors:
                # each color class has self.order()-1 edges
                p.add_constraint(Sum([edges[j][e] for e in self.edges(labels=None)]), min=self.order()-1)

                # Each vertex different from the root has indegree equals to one
                for v in self.vertices():
                    if v is not root:
                        p.add_constraint(Sum([edges[j][e] for e in self.incoming_edges(v, labels=None)]), max=1, min=1)
                    else:
                        p.add_constraint(Sum([edges[j][e] for e in self.incoming_edges(v, labels=None)]), max=0, min=0)

                # r_edges is larger than edges
                for u,v in self.edges(labels=None):
                    if self.has_edge(v,u):
                        if v<u:
                            p.add_constraint(r_edges[j][(u,v)] + r_edges[j][(v, u)] - edges[j][(u,v)] - edges[j][(v,u)], min=0)
                    else:
                        p.add_constraint(r_edges[j][(u,v)] + r_edges[j][(v, u)] - edges[j][(u,v)], min=0)

                from sage.graphs.digraph import DiGraph
                D = DiGraph()
                D.add_vertices(self.vertices())
                D.set_pos(self.get_pos())
                classes = [D.copy() for j in colors]

        else:

            # Sort an edge
            S = lambda (x,y) : (x,y) if x<y else (y,x)

            # An edge belongs to at most one arborescence
            for e in self.edges(labels=False):
                p.add_constraint(Sum([edges[j][S(e)] for j in colors]), max=1)


            for j in colors:
                # each color class has self.order()-1 edges
                p.add_constraint(Sum([edges[j][S(e)] for e in self.edges(labels=None)]), min=self.order()-1)

                # Each vertex is in the tree
                for v in self.vertices():
                    p.add_constraint(Sum([edges[j][S(e)] for e in self.edges_incident(v, labels=None)]), min=1)

                # r_edges is larger than edges
                for u,v in self.edges(labels=None):
                    p.add_constraint(r_edges[j][(u,v)] + r_edges[j][(v, u)] - edges[j][S((u,v))], min=0)

                from sage.graphs.graph import Graph
                D = Graph()
                D.add_vertices(self.vertices())
                D.set_pos(self.get_pos())
                classes = [D.copy() for j in colors]

        # no cycles
        for j in colors:
            for v in self:
                p.add_constraint(Sum(r_edges[j][(u,v)] for u in self.neighbors(v)), max=1-epsilon)

        p.set_binary(edges)

        try:
            p.solve(**kwds)

        except MIPSolverException:
            raise ValueError("This graph does not contain the required number of trees/arborescences !")

        edges = p.get_values(edges)

        for j,g in enumerate(classes):
            for e in self.edges(labels=False):
                if edges[j][S(e)] == 1:
                    g.add_edge(e)

        return classes


    def edge_cut(self, s, t, value_only=True, use_edge_labels=False, vertices=False, solver=None, verbose=0):
        r"""
        Returns a minimum edge cut between vertices `s` and `t`
        represented by a list of edges.

        A minimum edge cut between two vertices `s` and `t` of self
        is a set `A` of edges of minimum weight such that the graph
        obtained by removing `A` from self is disconnected. For more
        information, see the
        `Wikipedia article on cuts
        <http://en.wikipedia.org/wiki/Cut_%28graph_theory%29>`_.

        INPUT:

        - ``s`` -- source vertex

        - ``t`` -- sink vertex

        - ``value_only`` -- boolean (default: ``True``). When set to
          ``True``, only the weight of a minimum cut is returned.
          Otherwise, a list of edges of a minimum cut is also returned.

        - ``use_edge_labels`` -- boolean (default: ``False``). When set to
          ``True``, computes a weighted minimum cut where each edge has
          a weight defined by its label (if an edge has no label, `1`
          is assumed). Otherwise, each edge has weight `1`.

        - ``vertices`` -- boolean (default: ``False``). When set to ``True``,
          also returns the two sets of vertices that are disconnected by
          the cut. Implies ``value_only=False``.

        - ``solver`` -- (default: ``None``) Specify a Linear Program (LP)
          solver to be used. If set to ``None``, the default one is used. For
          more information on LP solvers and which default solver is used, see
          the method
          :meth:`solve <sage.numerical.mip.MixedIntegerLinearProgram.solve>`
          of the class
          :class:`MixedIntegerLinearProgram <sage.numerical.mip.MixedIntegerLinearProgram>`.

        - ``verbose`` -- integer (default: ``0``). Sets the level of
          verbosity. Set to 0 by default, which means quiet.

        OUTPUT:

        Real number or tuple, depending on the given arguments
        (examples are given below).

        EXAMPLES:

        A basic application in the Pappus graph::

           sage: g = graphs.PappusGraph()
           sage: g.edge_cut(1, 2, value_only=True)
           3.0

        If the graph is a path with randomly weighted edges::

           sage: g = graphs.PathGraph(15)
           sage: for (u,v) in g.edge_iterator(labels=None):
           ...      g.set_edge_label(u,v,random())

        The edge cut between the two ends is the edge of minimum weight::

           sage: minimum = min([l for u,v,l in g.edge_iterator()])
           sage: abs(minimum - g.edge_cut(0, 14, use_edge_labels=True)) < 10**(-5)
           True
           sage: [value,[[u,v]]] = g.edge_cut(0, 14, use_edge_labels=True, value_only=False)
           sage: g.edge_label(u, v) == minimum
           True

        The two sides of the edge cut are obviously shorter paths::

           sage: value,edges,[set1,set2] = g.edge_cut(0, 14, use_edge_labels=True, vertices=True)
           sage: g.subgraph(set1).is_isomorphic(graphs.PathGraph(len(set1)))
           True
           sage: g.subgraph(set2).is_isomorphic(graphs.PathGraph(len(set2)))
           True
           sage: len(set1) + len(set2) == g.order()
           True
        """
        from sage.numerical.mip import MixedIntegerLinearProgram, Sum
        g = self
        p = MixedIntegerLinearProgram(maximization=False)
        b = p.new_variable(dim=2)
        v = p.new_variable()

        if vertices:
            value_only = False
        if use_edge_labels:
            from sage.rings.real_mpfr import RR
            weight = lambda x: x if x in RR else 1
        else:
            weight = lambda x: 1

        # Some vertices belong to part 1, others to part 0
        p.add_constraint(v[s], min=0, max=0)
        p.add_constraint(v[t], min=1, max=1)

        if g.is_directed():

            # we minimize the number of edges
            p.set_objective(Sum([weight(w) * b[x][y] for (x,y,w) in g.edges()]))

            # Adjacent vertices can belong to different parts only if the
            # edge that connects them is part of the cut
            for (x,y) in g.edges(labels=None):
                p.add_constraint(v[x] + b[x][y] - v[y], min=0)

        else:
            # we minimize the number of edges
            p.set_objective(Sum([weight(w) * b[min(x,y)][max(x,y)] for (x,y,w) in g.edges()]))
            # Adjacent vertices can belong to different parts only if the
            # edge that connects them is part of the cut
            for (x,y) in g.edges(labels=None):
                p.add_constraint(v[x] + b[min(x,y)][max(x,y)] - v[y], min=0)
                p.add_constraint(v[y] + b[min(x,y)][max(x,y)] - v[x], min=0)

        p.set_binary(v)
        p.set_binary(b)

        if value_only:
            return p.solve(objective_only=True, solver=solver, log=verbose)
        else:
            obj = p.solve(solver=solver, log=verbose)
            b = p.get_values(b)
            answer = [obj]
            if g.is_directed():
                answer.append([(x,y) for (x,y) in g.edges(labels=None) if b[x][y] == 1])
            else:
                answer.append([(x,y) for (x,y) in g.edges(labels=None) if b[min(x,y)][max(x,y)] == 1])

            if vertices:
                v = p.get_values(v)
                l0 = []
                l1 = []
                for x in g.vertex_iterator():
                    if v.has_key(x) and v[x] == 1:
                        l1.append(x)
                    else:
                        l0.append(x)
                answer.append([l0, l1])
            return tuple(answer)

    def vertex_cut(self, s, t, value_only=True, vertices=False, solver=None, verbose=0):
        r"""
        Returns a minimum vertex cut between non adjacent vertices `s` and `t`
        represented by a list of vertices.

        A vertex cut between two non adjacent vertices is a set `U`
        of vertices of self such that the graph obtained by removing
        `U` from self is disconnected. For more information, see the
        `Wikipedia article on cuts
        <http://en.wikipedia.org/wiki/Cut_%28graph_theory%29>`_.

        INPUT:

        - ``value_only`` -- boolean (default: ``True``). When set to
          ``True``, only the size of the minimum cut is returned.

        - ``vertices`` -- boolean (default: ``False``). When set to
          ``True``, also returns the two sets of vertices that
          are disconnected by the cut. Implies ``value_only``
          set to False.

        - ``solver`` -- (default: ``None``) Specify a Linear Program (LP)
          solver to be used. If set to ``None``, the default one is used. For
          more information on LP solvers and which default solver is used, see
          the method
          :meth:`solve <sage.numerical.mip.MixedIntegerLinearProgram.solve>`
          of the class
          :class:`MixedIntegerLinearProgram <sage.numerical.mip.MixedIntegerLinearProgram>`.

        - ``verbose`` -- integer (default: ``0``). Sets the level of
          verbosity. Set to 0 by default, which means quiet.

        OUTPUT:

        Real number or tuple, depending on the given arguments
        (examples are given below).

        EXAMPLE:

        A basic application in the Pappus graph::

           sage: g = graphs.PappusGraph()
           sage: g.vertex_cut(1, 16, value_only=True)
           3.0

        In the bipartite complete graph `K_{2,8}`, a cut between the two
        vertices in the size `2` part consists of the other `8` vertices::

           sage: g = graphs.CompleteBipartiteGraph(2, 8)
           sage: [value, vertices] = g.vertex_cut(0, 1, value_only=False)
           sage: print value
           8.0
           sage: vertices == range(2,10)
           True

        Clearly, in this case the two sides of the cut are singletons ::

           sage: [value, vertices, [set1, set2]] = g.vertex_cut(0,1, vertices=True)
           sage: len(set1) == 1
           True
           sage: len(set2) == 1
           True
        """
        from sage.numerical.mip import MixedIntegerLinearProgram, Sum
        g = self
        if g.has_edge(s,t):
            raise ValueError, "There can be no vertex cut between adjacent vertices !"
        if vertices:
            value_only = False

        p = MixedIntegerLinearProgram(maximization=False)
        b = p.new_variable()
        v = p.new_variable()

        # Some vertices belong to part 1, some others to part 0
        p.add_constraint(v[s], min=0, max=0)
        p.add_constraint(v[t], min=1, max=1)

        # b indicates whether the vertices belong to the cut
        p.add_constraint(b[s], min=0, max=0)
        p.add_constraint(b[t], min=0, max=0)

        if g.is_directed():

            p.set_objective(Sum([b[x] for x in g.vertices()]))

            # adjacent vertices belong to the same part except if one of them
            # belongs to the cut
            for (x,y) in g.edges(labels=None):
                p.add_constraint(v[x] + b[y] - v[y], min=0)

        else:
            p.set_objective(Sum([b[x] for x in g.vertices()]))
            # adjacent vertices belong to the same part except if one of them
            # belongs to the cut
            for (x,y) in g.edges(labels=None):
                p.add_constraint(v[x] + b[y] - v[y],min=0)
                p.add_constraint(v[y] + b[x] - v[x],min=0)

        p.set_binary(b)
        p.set_binary(v)

        if value_only:
            return p.solve(objective_only=True, solver=solver, log=verbose)
        else:
            obj = p.solve(solver=solver, log=verbose)
            b = p.get_values(b)
            answer = [obj,[x for x in g if b[x] == 1]]
            if vertices:
                v = p.get_values(v)
                l0 = []
                l1 = []
                for x in g.vertex_iterator():
                    # if the vertex is not in the cut
                    if not (b.has_key(x) and b[x] == 1):
                        if (v.has_key(x) and v[x] == 1):
                            l1.append(x)
                        else:
                            l0.append(x)
                answer.append([l0, l1])
            return tuple(answer)


    def multiway_cut(self, vertices, value_only = False, use_edge_labels = False, **kwds):
        r"""
        Returns a minimum edge multiway cut corresponding to the
        given set of vertices
        ( cf. http://www.d.kth.se/~viggo/wwwcompendium/node92.html )
        represented by a list of edges.

        A multiway cut for a vertex set `S` in a graph or a digraph
        `G` is a set `C` of edges such that any two vertices `u,v`
        in `S` are disconnected when removing the edges from `C` from `G`.

        Such a cut is said to be minimum when its cardinality
        (or weight) is minimum.

        INPUT:

        - ``vertices`` (iterable)-- the set of vertices

        - ``value_only`` (boolean)

            - When set to ``True``, only the value of a minimum
              multiway cut is returned.

            - When set to ``False`` (default), the list of edges
              is returned

        - ``use_edge_labels`` (boolean)
            - When set to ``True``, computes a weighted minimum cut
              where each edge has a weight defined by its label. ( if
              an edge has no label, `1` is assumed )

            - when set to ``False`` (default), each edge has weight `1`.

        - ``**kwds`` -- arguments to be passed down to the ``solve``
          function of ``MixedIntegerLinearProgram``. See the documentation
          of ``MixedIntegerLinearProgram.solve`` for more information.

        EXAMPLES:

        Of course, a multiway cut between two vertices correspond
        to a minimum edge cut ::

            sage: g = graphs.PetersenGraph()
            sage: g.edge_cut(0,3) == g.multiway_cut([0,3], value_only = True)
            True

        As Petersen's graph is `3`-regular, a minimum multiway cut
        between three vertices contains at most `2\times 3` edges
        (which could correspond to the neighborhood of 2
        vertices)::

            sage: g.multiway_cut([0,3,9], value_only = True) == 2*3
            True

        In this case, though, the vertices are an independent set.
        If we pick instead vertices `0,9,` and `7`, we can save `4`
        edges in the multiway cut ::

            sage: g.multiway_cut([0,7,9], value_only = True) == 2*3 - 1
            True

        This example, though, does not work in the directed case anymore,
        as it is not possible in Petersen's graph to mutualise edges ::

            sage: g = DiGraph(g)
            sage: g.multiway_cut([0,7,9], value_only = True) == 3*3
            True

        Of course, a multiway cut between the whole vertex set
        contains all the edges of the graph::

            sage: C = g.multiway_cut(g.vertices())
            sage: set(C) == set(g.edges())
            True
        """
        from sage.numerical.mip import MixedIntegerLinearProgram, Sum
        from itertools import combinations, chain

        p = MixedIntegerLinearProgram(maximization = False)

        # height[c][v] represents the height of vertex v for commodity c
        height = p.new_variable(dim = 2)

        # cut[e] represents whether e is in the cut
        cut = p.new_variable()

        # Reorder
        R = lambda x,y : (x,y) if x<y else (y,x)

        # Weight function
        if use_edge_labels:
            w = lambda l : l if l is not None else 1
        else:
            w = lambda l : 1

        if self.is_directed():

            p.set_objective(  Sum([ w(l) * cut[u,v] for u,v,l in self.edge_iterator() ]) )

            for s,t in chain( combinations(vertices,2), map(lambda (x,y) : (y,x), combinations(vertices,2))) :
                # For each commodity, the source is at height 0
                # and the destination is at height 1
                p.add_constraint( height[(s,t)][s], min = 0, max = 0)
                p.add_constraint( height[(s,t)][t], min = 1, max = 1)

                # given a commodity (s,t), the height of two adjacent vertices u,v
                # can differ of at most the value of the edge between them
                for u,v in self.edges(labels = False):
                    p.add_constraint( height[(s,t)][u] - height[(s,t)][v] - cut[u,v], max = 0)

        else:

            p.set_objective(  Sum([ w(l) * cut[R(u,v)] for u,v,l in self.edge_iterator() ]) )

            for s,t in combinations(vertices,2):
                # For each commodity, the source is at height 0
                # and the destination is at height 1
                p.add_constraint( height[(s,t)][s], min = 0, max = 0)
                p.add_constraint( height[(s,t)][t], min = 1, max = 1)

                # given a commodity (s,t), the height of two adjacent vertices u,v
                # can differ of at most the value of the edge between them
                for u,v in self.edges(labels = False):
                    p.add_constraint( height[(s,t)][u] - height[(s,t)][v] - cut[R(u,v)], max = 0)
                    p.add_constraint( height[(s,t)][v] - height[(s,t)][u] - cut[R(u,v)], max = 0)


        p.set_binary(cut)
        if value_only:
            return p.solve(objective_only = True, **kwds)

        p.solve(**kwds)

        cut = p.get_values(cut)

        if self.is_directed():
            return filter(lambda (u,v,l) : cut[u,v] > .5, self.edge_iterator())

        else:
            return filter(lambda (u,v,l) : cut[R(u,v)] > .5, self.edge_iterator())

    def vertex_cover(self, algorithm="Cliquer", value_only=False, solver=None, verbose=0):
        r"""
        Returns a minimum vertex cover of self represented
        by a list of vertices.

        A minimum vertex cover of a graph is a set `S` of
        vertices such that each edge is incident to at least
        one element of `S`, and such that `S` is of minimum
        cardinality. For more information, see the
        `Wikipedia article on vertex cover
        <http://en.wikipedia.org/wiki/Vertex_cover>`_.

        Equivalently, a vertex cover is defined as the
        complement of an independent set.

        As an optimization problem, it can be expressed as follows:

        .. MATH::

            \mbox{Minimize : }&\sum_{v\in G} b_v\\
            \mbox{Such that : }&\forall (u,v) \in G.edges(), b_u+b_v\geq 1\\
            &\forall x\in G, b_x\mbox{ is a binary variable}

        INPUT:

        - ``algorithm`` -- string (default: ``"Cliquer"``). Indicating
          which algorithm to use. It can be one of those two values.

          - ``"Cliquer"`` will compute a minimum vertex cover
            using the Cliquer package.

          - ``"MILP"`` will compute a minimum vertex cover through a mixed
            integer linear program (requires packages GLPK or CBC).

        - ``value_only`` -- boolean (default: ``False``). If set to ``True``,
          only the size of a minimum vertex cover is returned. Otherwise,
          a minimum vertex cover is returned as a list of vertices.

        - ``log`` -- non negative integer (default: ``0``). Set the level
          of verbosity you want from the linear program solver. Since the
          problem of computing a vertex cover is `NP`-complete, its solving
          may take some time depending on the graph. A value of 0 means
          that there will be no message printed by the solver. This option
          is only useful if ``algorithm="MILP"``.

        - ``solver`` -- (default: ``None``) Specify a Linear Program (LP)
          solver to be used. If set to ``None``, the default one is used. For
          more information on LP solvers and which default solver is used, see
          the method
          :meth:`solve <sage.numerical.mip.MixedIntegerLinearProgram.solve>`
          of the class
          :class:`MixedIntegerLinearProgram <sage.numerical.mip.MixedIntegerLinearProgram>`.

        - ``verbose`` -- integer (default: ``0``). Sets the level of
          verbosity. Set to 0 by default, which means quiet.

        EXAMPLES:

        On the Pappus graph::

           sage: g = graphs.PappusGraph()
           sage: g.vertex_cover(value_only=True)
           9

        The two algorithms should return the same result::

           sage: g = graphs.RandomGNP(10,.5)
           sage: vc1 = g.vertex_cover(algorithm="MILP")
           sage: vc2 = g.vertex_cover(algorithm="Cliquer")
           sage: len(vc1) == len(vc2)
           True
        """
        if algorithm == "Cliquer":
            independent = self.independent_set()
            if value_only:
                return self.order() - len(independent)
            else:
                return set(self.vertices()).difference(set(independent))

        elif algorithm == "MILP":

            from sage.numerical.mip import MixedIntegerLinearProgram, Sum
            g = self
            p = MixedIntegerLinearProgram(maximization=False)
            b = p.new_variable()

            # minimizes the number of vertices in the set
            p.set_objective(Sum([b[v] for v in g.vertices()]))

            # an edge contains at least one vertex of the minimum vertex cover
            for (u,v) in g.edges(labels=None):
                p.add_constraint(b[u] + b[v], min=1)

            p.set_binary(b)

            if value_only:
                return p.solve(objective_only=True, solver=solver, log=verbose)
            else:
                p.solve(solver=solver, log=verbose)
                b = p.get_values(b)
                return set([v for v in g.vertices() if b[v] == 1])
        else:
            raise ValueError("Only two algorithms are available : Cliquer and MILP.")

    def max_cut(self, value_only=True, use_edge_labels=True, vertices=False, solver=None, verbose=0):
        r"""
        Returns a maximum edge cut of the graph. For more information, see the
        `Wikipedia article on cuts
        <http://en.wikipedia.org/wiki/Cut_%28graph_theory%29>`_.

        INPUT:

        - ``value_only`` -- boolean (default: ``True``)

          - When set to ``True`` (default), only the value is returned.

          - When set to ``False``, both the value and a maximum edge cut
            are returned.

        - ``use_edge_labels`` -- boolean (default: ``True``)

          - When set to ``True``, computes a maximum weighted cut
            where each edge has a weight defined by its label. (If
            an edge has no label, `1` is assumed.)

          - When set to ``False``, each edge has weight `1`.

        - ``vertices`` -- boolean (default: ``False``)

          - When set to ``True``, also returns the two sets of
            vertices that are disconnected by the cut. This implies
            ``value_only=False``.

        - ``solver`` -- (default: ``None``) Specify a Linear Program (LP)
          solver to be used. If set to ``None``, the default one is used. For
          more information on LP solvers and which default solver is used, see
          the method
          :meth:`solve <sage.numerical.mip.MixedIntegerLinearProgram.solve>`
          of the class
          :class:`MixedIntegerLinearProgram <sage.numerical.mip.MixedIntegerLinearProgram>`.

        - ``verbose`` -- integer (default: ``0``). Sets the level of
          verbosity. Set to 0 by default, which means quiet.

        EXAMPLE:

        Quite obviously, the max cut of a bipartite graph
        is the number of edges, and the two sets of vertices
        are the the two sides ::

            sage: g = graphs.CompleteBipartiteGraph(5,6)
            sage: [ value, edges, [ setA, setB ]] = g.max_cut(vertices=True)
            sage: value == 5*6
            True
            sage: bsetA, bsetB  = map(list,g.bipartite_sets())
            sage: (bsetA == setA and bsetB == setB ) or ((bsetA == setB and bsetB == setA ))
            True

        The max cut of a Petersen graph::

           sage: g=graphs.PetersenGraph()
           sage: g.max_cut()
           12.0

        """
        g=self

        if vertices:
            value_only=False

        if use_edge_labels:
            from sage.rings.real_mpfr import RR
            weight = lambda x: x if x in RR else 1
        else:
            weight = lambda x: 1

        if g.is_directed():
            reorder_edge = lambda x,y : (x,y)
        else:
            reorder_edge = lambda x,y : (x,y) if x<= y else (y,x)

        from sage.numerical.mip import MixedIntegerLinearProgram, Sum

        p = MixedIntegerLinearProgram(maximization=True)

        in_set = p.new_variable(dim=2)
        in_cut = p.new_variable(dim=1)


        # A vertex has to be in some set
        for v in g:
            p.add_constraint(in_set[0][v]+in_set[1][v],max=1,min=1)

        # There is no empty set
        p.add_constraint(Sum([in_set[1][v] for v in g]),min=1)
        p.add_constraint(Sum([in_set[0][v] for v in g]),min=1)

        if g.is_directed():
            # There is no edge from set 0 to set 1 which
            # is not in the cut
            # Besides, an edge can only be in the cut if its vertices
            # belong to different sets
            for (u,v) in g.edge_iterator(labels=None):
                p.add_constraint(in_set[0][u] + in_set[1][v] - in_cut[(u,v)], max = 1)
                p.add_constraint(in_set[0][u] + in_set[0][v] + in_cut[(u,v)], max = 2)
                p.add_constraint(in_set[1][u] + in_set[1][v] + in_cut[(u,v)], max = 2)
        else:

            # Two adjacent vertices are in different sets if and only if
            # the edge between them is in the cut

            for (u,v) in g.edge_iterator(labels=None):
                p.add_constraint(in_set[0][u]+in_set[1][v]-in_cut[reorder_edge(u,v)],max=1)
                p.add_constraint(in_set[1][u]+in_set[0][v]-in_cut[reorder_edge(u,v)],max=1)
                p.add_constraint(in_set[0][u] + in_set[0][v] + in_cut[reorder_edge(u,v)], max = 2)
                p.add_constraint(in_set[1][u] + in_set[1][v] + in_cut[reorder_edge(u,v)], max = 2)


        p.set_binary(in_set)
        p.set_binary(in_cut)

        p.set_objective(Sum([weight(l ) * in_cut[reorder_edge(u,v)] for (u,v,l ) in g.edge_iterator()]))

        if value_only:
            return p.solve(objective_only=True, solver=solver, log=verbose)
        else:
            val = [p.solve(solver=solver, log=verbose)]

            in_cut = p.get_values(in_cut)
            in_set = p.get_values(in_set)

            edges = []
            for (u,v,l) in g.edge_iterator():
                if in_cut[reorder_edge(u,v)] == 1:
                    edges.append((u,v,l))

            val.append(edges)

            if vertices:
                a = []
                b = []
                for v in g:
                    if in_set[0][v] == 1:
                        a.append(v)
                    else:
                        b.append(v)
                val.append([a,b])

            return val

    def traveling_salesman_problem(self, weighted = True):
        r"""
        Solves the traveling salesman problem (TSP)

        Given a graph (resp. a digraph) `G` with weighted edges,
        the traveling salesman problem consists in finding a
        hamiltonian cycle (resp. circuit) of the graph of
        minimum cost.

        This TSP is one of the most famous NP-Complete problems,
        this function can thus be expected to take some time
        before returning its result.

        INPUT:

        - ``weighted`` (boolean) -- whether to consider the
          weights of the edges.

              - If set to ``False`` (default), all edges are
                assumed to weight `1`

              - If set to ``True``, the weights are taken into
                account, and the edges whose weight is ``None``
                are assumed to be set to `1`

        OUTPUT:

        A solution to the TSP, as a ``Graph`` object whose vertex
        set is `V(G)`, and whose edges are only those of the
        solution.

        ALGORITHM:

        This optimization problem is solved through the use
        of Linear Programming.

        NOTE:

        - This function is correctly defined for both graph and digraphs.
          In the second case, the returned cycle is a circuit of optimal
          cost.

        EXAMPLES:

        The Heawood graph is known to be hamiltonian::

            sage: g = graphs.HeawoodGraph()
            sage: tsp = g.traveling_salesman_problem()
            sage: tsp
            TSP from Heawood graph: Graph on 14 vertices

        The solution to the TSP has to be connected ::

            sage: tsp.is_connected()
            True

        It must also be a `2`-regular graph::

            sage: tsp.is_regular(k=2)
            True

        And obviously it is a subgraph of the Heawood graph::

            sage: all([ e in g.edges() for e in tsp.edges()])
            True

        On the other hand, the Petersen Graph is known not to
        be hamiltonian::

            sage: g = graphs.PetersenGraph()
            sage: tsp = g.traveling_salesman_problem()
            Traceback (most recent call last):
            ...
            ValueError: The given graph is not hamiltonian

        One easy way to change is is obviously to add to this
        graph the edges corresponding to a hamiltonian cycle.

        If we do this by setting the cost of these new edges
        to `2`, while the others are set to `1`, we notice
        that not all the edges we added are used in the
        optimal solution ::

            sage: for u, v in g.edges(labels = None):
            ...      g.set_edge_label(u,v,1)

            sage: cycle = graphs.CycleGraph(10)
            sage: for u,v in cycle.edges(labels = None):
            ...      if not g.has_edge(u,v):
            ...          g.add_edge(u,v)
            ...      g.set_edge_label(u,v,2)

            sage: tsp = g.traveling_salesman_problem(weighted = True)
            sage: sum( tsp.edge_labels() ) < 2*10
            True

        If we pick `1/2` instead of `2` as a cost for these new edges,
        they clearly become the optimal solution

            sage: for u,v in cycle.edges(labels = None):
            ...      g.set_edge_label(u,v,1/2)

            sage: tsp = g.traveling_salesman_problem(weighted = True)
            sage: sum( tsp.edge_labels() ) == (1/2)*10
            True

        """

        from sage.numerical.mip import MixedIntegerLinearProgram, Sum

        p = MixedIntegerLinearProgram(maximization = False)

        f = p.new_variable()
        r = p.new_variable()

        # If the graph has multiple edges
        if self.has_multiple_edges():
            g = self.copy()
            multi = self.multiple_edges()
            g.delete_edges(multi)
            g.allow_multiple_edges(False)
            if weighted:
                e = {}

                for u,v,l in multi:
                    u,v = (u,v) if u<v else (v,u)

                    # The weight of an edge is the minimum over
                    # the weights of the parallel edges

                    #  new value *if* ( none other        *or*   new==None and last > 1     *else*  change nothing
                    e[(u,v)] = l if (not e.has_key((u,v)) or ( (l is None or l == {}) and e[(u,v)] > 1 )) else e[(u,v)]

                g.add_edges([(u,v) for (u,v),l in e.iteritems()])

            else:
                from sage.sets.set import Set
                g.add_edges(Set([ (min(u,v),max(u,v)) for u,v,l in multi]))

        else:
            g = self

        eps = 1/(2*Integer(g.order()))
        x = g.vertex_iterator().next()


        if g.is_directed():

            # returns the variable corresponding to arc u,v
            E = lambda u,v : f[(u,v)]

            # All the vertices have in-degree 1
            [p.add_constraint(Sum([ f[(u,v)] for u in g.neighbors_in(v)]), min = 1, max = 1) for v in g]

            # All the vertices have out-degree 1
            [p.add_constraint(Sum([ f[(v,u)] for u in g.neighbors_out(v)]), min = 1, max = 1) for v in g]


            # r is greater than f
            for u,v in g.edges(labels = None):
                if g.has_edge(v,u):
                    if u < v:
                        p.add_constraint( r[(u,v)] + r[(v,u)]- f[(u,v)] - f[(v,u)], min = 0)

                        # no 2-cycles
                        p.add_constraint( f[(u,v)] + f[(v,u)], max = 1)

                else:
                    p.add_constraint( r[(u,v)] + r[(v,u)] - f[(u,v)], min = 0)


            # defining the answer when g is directed
            from sage.graphs.all import DiGraph
            tsp = DiGraph()
        else:

            # reorders the edge as they can appear in the two different ways
            R = lambda x,y : (x,y) if x < y else (y,x)

            # returns the variable corresponding to arc u,v
            E = lambda u,v : f[R(u,v)]

            # All the vertices have degree 2
            [p.add_constraint(Sum([ f[R(u,v)] for u in g.neighbors(v)]), min = 2, max = 2) for v in g]

            # r is greater than f
            for u,v in g.edges(labels = None):
                p.add_constraint( r[(u,v)] + r[(v,u)] - f[R(u,v)], min = 0)

            from sage.graphs.all import Graph

            # defining the answer when g is not directed
            tsp = Graph()


        # no cycle which does not contain x
        for v in g:
            if v != x:
                p.add_constraint(Sum([ r[(u,v)] for u in g.neighbors(v)]),max = 1-eps)


        weight = lambda u,v : g.edge_label(u,v) if (g.edge_label(u,v) is not None and g.edge_label(u,v) != {}) else 1

        if weighted:
            p.set_objective(Sum([ weight(u,v)*E(u,v) for u,v in g.edges(labels=None)]) )
        else:
            p.set_objective(None)

        p.set_binary(f)

        from sage.numerical.mip import MIPSolverException

        try:
            obj = p.solve()
            f = p.get_values(f)
            tsp.add_vertices(g.vertices())
            tsp.set_pos(g.get_pos())
            tsp.name("TSP from "+g.name())
            tsp.add_edges([(u,v,l) for u,v,l in g.edges() if E(u,v) == 1])

            return tsp

        except MIPSolverException:
            raise ValueError("The given graph is not hamiltonian")


    def hamiltonian_cycle(self):
        r"""
        Returns a hamiltonian cycle/circuit of the current graph/digraph

        A graph (resp. digraph) is said to be hamiltonian
        if it contains as a subgraph a cycle (resp. a circuit)
        going through all the vertices.

        Computing a hamiltonian cycle/circuit being NP-Complete,
        this algorithm could run for some time depending on
        the instance.

        ALGORITHM:

        See ``Graph.traveling_salesman_problem``.

        OUTPUT:

        Returns a hamiltonian cycle/circuit if it exists. Otherwise,
        raises a ``ValueError`` exception.

        NOTE:

        This function, as ``is_hamiltonian``, computes a hamiltonian
        cycle if it exists : the user should *NOT* test for
        hamiltonicity using ``is_hamiltonian`` before calling this
        function, as it would result in computing it twice.

        EXAMPLES:

        The Heawood Graph is known to be hamiltonian ::

            sage: g = graphs.HeawoodGraph()
            sage: g.hamiltonian_cycle()
            TSP from Heawood graph: Graph on 14 vertices

        The Petergraph, though, is not ::

            sage: g = graphs.PetersenGraph()
            sage: g.hamiltonian_cycle()
            Traceback (most recent call last):
            ...
            ValueError: The given graph is not hamiltonian
        """
        from sage.numerical.mip import MIPSolverException

        try:
            return self.traveling_salesman_problem(weighted = False)
        except MIPSolverException:
            raise ValueError("The given graph is not hamiltonian")

    def flow(self, x, y, value_only=True, integer=False, use_edge_labels=True, vertex_bound=False, solver=None, verbose=0):
        r"""
        Returns a maximum flow in the graph from ``x`` to ``y``
        represented by an optimal valuation of the edges. For more
        information, see the
        `Wikipedia article on maximum flow
        <http://en.wikipedia.org/wiki/Max_flow>`_.

        As an optimization problem, is can be expressed this way :

        .. MATH::

            \mbox{Maximize : }&\sum_{e\in G.edges()} w_e b_e\\
            \mbox{Such that : }&\forall v \in G, \sum_{(u,v)\in G.edges()} b_{(u,v)}\leq 1\\
            &\forall x\in G, b_x\mbox{ is a binary variable}

        INPUT:

        - ``x`` -- Source vertex

        - ``y`` -- Sink vertex

        - ``value_only`` -- boolean (default: ``True``)

          - When set to ``True``, only the value of a maximal
            flow is returned.

          - When set to ``False``, is returned a pair whose first element
            is the value of the maximum flow, and whose second value is
            a flow graph (a copy of the current graph, such that each edge
            has the flow using it as a label, the edges without flow being
            omitted).

        - ``integer`` -- boolean (default: ``False``)

          - When set to ``True``, computes an optimal solution under the
            constraint that the flow going through an edge has to be an
            integer.

        - ``use_edge_labels`` -- boolean (default: ``True``)

          - When set to ``True``, computes a maximum flow
            where each edge has a capacity defined by its label. (If
            an edge has no label, `1` is assumed.)

          - When set to ``False``, each edge has capacity `1`.

        - ``vertex_bound`` -- boolean (default: ``False``)

          - When set to ``True``, sets the maximum flow leaving
            a vertex different from `x` to `1` (useful for vertex
            connectivity parameters).

        - ``solver`` -- Specify a Linear Program solver to be used.
          If set to ``None``, the default one is used.
          function of ``MixedIntegerLinearProgram``. See the documentation  of ``MixedIntegerLinearProgram.solve``
          for more information.

        - ``verbose`` (integer) -- sets the level of verbosity. Set to 0
          by default (quiet).

        EXAMPLES:

        Two basic applications of the flow method for the ``PappusGraph`` and the
        ``ButterflyGraph`` with parameter `2` ::

           sage: g=graphs.PappusGraph()
           sage: g.flow(1,2)
           3.0

        ::

           sage: b=digraphs.ButterflyGraph(2)
           sage: b.flow(('00',1),('00',2))
           1.0

        The flow method can be used to compute a matching in a bipartite graph
        by linking a source `s` to all the vertices of the first set and linking
        a sink `t` to all the vertices of the second set, then computing
        a maximum `s-t` flow ::

            sage: g = DiGraph()
            sage: g.add_edges([('s',i) for i in range(4)])
            sage: g.add_edges([(i,4+j) for i in range(4) for j in range(4)])
            sage: g.add_edges([(4+i,'t') for i in range(4)])
            sage: [cardinal, flow_graph] = g.flow('s','t',integer=True,value_only=False)
            sage: flow_graph.delete_vertices(['s','t'])
            sage: len(flow_graph.edges(labels=None))
            4

        """
        from sage.numerical.mip import MixedIntegerLinearProgram, Sum
        g=self
        p=MixedIntegerLinearProgram(maximization=True)
        flow=p.new_variable(dim=1)

        if use_edge_labels:
            from sage.rings.real_mpfr import RR
            capacity=lambda x: x if x in RR else 1
        else:
            capacity=lambda x: 1

        if g.is_directed():
            # This function return the balance of flow at X
            flow_sum=lambda X: Sum([flow[(X,v)] for (u,v) in g.outgoing_edges([X],labels=None)])-Sum([flow[(u,X)] for (u,v) in g.incoming_edges([X],labels=None)])

            # The flow leaving x
            flow_leaving = lambda X : Sum([flow[(uu,vv)] for (uu,vv) in g.outgoing_edges([X],labels=None)])

            # The flow to be considered when defining the capacity contraints
            capacity_sum = lambda u,v : flow[(u,v)]

        else:
            # This function return the balance of flow at X
            flow_sum=lambda X:Sum([flow[(X,v)]-flow[(v,X)] for v in g[X]])

            # The flow leaving x
            flow_leaving = lambda X : Sum([flow[(X,vv)] for vv in g[X]])

            # The flow to be considered when defining the capacity contraints
            capacity_sum = lambda u,v : flow[(u,v)] + flow[(v,u)]

        # Maximizes the flow leaving x
        p.set_objective(flow_sum(x))

        # Elsewhere, the flow is equal to 0
        for v in g:
            if v!=x and v!=y:
                p.add_constraint(flow_sum(v),min=0,max=0)

        # Capacity constraints
        for (u,v,w) in g.edges():
            p.add_constraint(capacity_sum(u,v),max=capacity(w))

        # No vertex except the sources can send more than 1
        if vertex_bound:
            for v in g:
                if v!=x and v!=y:
                    p.add_constraint(flow_leaving(v),max=1)

        if integer:
            p.set_integer(flow)


        if value_only:
            return p.solve(objective_only=True)

        obj=p.solve()

        flow=p.get_values(flow)
        # Builds a clean flow Draph
        flow_graph = g._build_flow_graph(flow, integer=integer)

        # Which could be a Graph
        if not self.is_directed():
            from sage.graphs.graph import Graph
            flow_graph = Graph(flow_graph)

        return [obj,flow_graph]

    def multicommodity_flow(self, terminals, integer=True, use_edge_labels=False,vertex_bound=False, solver=None, verbose=0):
        r"""
        Solves a multicommodity flow problem.

        In the multicommodity flow problem, we are given a set of pairs
        `(s_i, t_i)`, called terminals meaning that `s_i` is willing
        some flow to `t_i`.

        Even though it is a natural generalisation of the flow problem
        this version of it is NP-Complete to solve when the flows
        are required to be integer.

        For more information, see the
        `Wikipedia page on multicommodity flows
        <http://en.wikipedia.org/wiki/Multi-commodity_flow_problem>`.

        INPUT:

        - ``terminals`` -- a list of pairs `(s_i, t_i)` or triples
          `(s_i, t_i, w_i)` representing a flow from `s_i` to `t_i`
          of intensity `w_i`. When the pairs are of size `2`, a intensity
          of `1` is assumed.

        - ``integer`` (boolean) -- whether to require an integer multicommodity
          flow

        - ``use_edge_labels`` (boolean) -- whether to consider the label of edges
          as numerical values representing a capacity. If set to ``False``, a capacity
          of `1` is assumed

        - ``vertex_bound`` (boolean) -- whether to require that a vertex can stand at most
          `1` commodity of flow through it of intensity `1`. Terminals can obviously
          still send or receive several units of flow even though vertex_bound is set
          to ``True``, as this parameter is meant to represent topological properties.

        - ``solver`` -- Specify a Linear Program solver to be used.
          If set to ``None``, the default one is used.
          function of ``MixedIntegerLinearProgram``. See the documentation  of ``MixedIntegerLinearProgram.solve``
          for more informations.

        - ``verbose`` (integer) -- sets the level of verbosity. Set to 0
          by default (quiet).

        ALGORITHM:

        (Mixed Integer) Linear Program, depending on the value of ``integer``.

        EXAMPLE:

        An easy way to obtain a satisfiable multiflow is to compute
        a matching in a graph, and to consider the paired vertices
        as terminals ::

            sage: g = graphs.PetersenGraph()
            sage: matching = [(u,v) for u,v,_ in g.matching()]
            sage: h = g.multicommodity_flow(matching)
            sage: len(h)
            5

        We could also have considered ``g`` as symmetric and computed
        the multiflow in this version instead. In this case, however
        edges can be used in both directions at the same time::

            sage: h = DiGraph(g).multicommodity_flow(matching)
            sage: len(h)
            5

        An exception is raised when the problem has no solution ::

            sage: h = g.multicommodity_flow([(u,v,3) for u,v in matching])
            Traceback (most recent call last):
            ...
            ValueError: The multiflow problem has no solution
        """

        from sage.numerical.mip import MixedIntegerLinearProgram , Sum
        g=self
        p=MixedIntegerLinearProgram(maximization=True)

        # Adding the intensity if not present
        terminals = [(x if len(x) == 3 else (x[0],x[1],1)) for x in terminals]

        # defining the set of terminals
        set_terminals = set([])
        for s,t,_ in terminals:
            set_terminals.add(s)
            set_terminals.add(t)

        # flow[i][(u,v)] is the flow of commodity i going from u to v
        flow=p.new_variable(dim=2)

        # Whether to use edge labels
        if use_edge_labels:
            from sage.rings.real_mpfr import RR
            capacity=lambda x: x if x in RR else 1
        else:
            capacity=lambda x: 1

        if g.is_directed():
            # This function return the balance of flow at X
            flow_sum=lambda i,X: Sum([flow[i][(X,v)] for (u,v) in g.outgoing_edges([X],labels=None)])-Sum([flow[i][(u,X)] for (u,v) in g.incoming_edges([X],labels=None)])

            # The flow leaving x
            flow_leaving = lambda i,X : Sum([flow[i][(uu,vv)] for (uu,vv) in g.outgoing_edges([X],labels=None)])

            # the flow to consider when defining the capacity contraints
            capacity_sum = lambda i,u,v : flow[i][(u,v)]

        else:
            # This function return the balance of flow at X
            flow_sum=lambda i,X:Sum([flow[i][(X,v)]-flow[i][(v,X)] for v in g[X]])

            # The flow leaving x
            flow_leaving = lambda i, X : Sum([flow[i][(X,vv)] for vv in g[X]])

            # the flow to consider when defining the capacity contraints
            capacity_sum = lambda i,u,v : flow[i][(u,v)] + flow[i][(v,u)]


        # Flow constraints
        for i,(s,t,l) in enumerate(terminals):
            for v in g:
                if v == s:
                    p.add_constraint(flow_sum(i,v),min=l,max=l)
                elif v == t:
                    p.add_constraint(flow_sum(i,v),min=-l,max=-l)
                else:
                    p.add_constraint(flow_sum(i,v),min=0,max=0)


        # Capacity constraints
        for (u,v,w) in g.edges():
            p.add_constraint(Sum([capacity_sum(i,u,v) for i in range(len(terminals))]),max=capacity(w))


        if vertex_bound:

            # Any vertex
            for v in g.vertices():

                # which is an endpoint
                if v in set_terminals:
                    for i,(s,t,_) in enumerate(terminals):

                        # only tolerates the commodities of which it is an endpoint
                        if not (v==s or v==t):
                            p.add_constraint(flow_leaving(i,v), max = 0)

                # which is not an endpoint
                else:
                    # can stand at most 1 unit of flow through itself
                    p.add_constraint(Sum([flow_leaving(i,v) for i in range(len(terminals))]), max = 1)

        p.set_objective(None)

        if integer:
            p.set_integer(flow)

        from sage.numerical.mip import MIPSolverException

        try:
            obj=p.solve()
        except MIPSolverException:
            raise ValueError("The multiflow problem has no solution")

        flow=p.get_values(flow)

        # building clean flow digraphs
        flow_graphs = [g._build_flow_graph(flow[i], integer=integer) for i in range(len(terminals))]

        # which could be .. graphs !
        if not self.is_directed():
            from sage.graphs.graph import Graph
            flow_graphs = map(Graph, flow_graphs)

        return flow_graphs

    def _build_flow_graph(self, flow, integer):
        r"""
        Builds a "clean" flow graph

        It build it, then looks for circuits and removes them

        INPUT:

        - ``flow`` -- a dictionary associating positive numerical values
          to edges

        - ``integer`` (boolean) -- whether the values from ``flow`` are the solution
          of an integer flow. In this case, a value of less than .5 is assumed to be 0


        EXAMPLE:

        This method is tested in ``flow`` and ``multicommodity_flow``::

            sage: g = Graph()
            sage: g.add_edge(0,1)
            sage: f = g._build_flow_graph({(0,1):1}, True)
        """

        from sage.graphs.digraph import DiGraph
        g = DiGraph()

        # add significant edges
        for (u,v),l in flow.iteritems():
            if l > 0 and not (integer and l<.5):
                g.add_edge(u,v,l)

        # stupid way to find Cycles. Will be fixed by #8932
        # for any vertex, for any of its in-neighbors, tried to find a cycle
        for v in g:
            for u in g.neighbor_in_iterator(v):

                # the edge from u to v could have been removed in a previous iteration
                if not g.has_edge(u,v):
                    break
                sp = g.shortest_path(v,u)
                if sp != []:

                    #find the minimm value along the cycle.
                    m = g.edge_label(u,v)
                    for i in range(len(sp)-1):
                        m = min(m,g.edge_label(sp[i],sp[i+1]))

                    # removes it from all the edges of the cycle
                    sp.append(v)
                    for i in range(len(sp)-1):
                        l = g.edge_label(sp[i],sp[i+1]) - m

                        # an edge with flow 0 is removed
                        if l == 0:
                            g.delete_edge(sp[i],sp[i+1])
                        else:
                            g.set_edge_label(l)

        # if integer is set, round values and deletes zeroes
        if integer:
            for (u,v,l) in g.edges():
                if l<.5:
                    g.delete_edge(u,v)
                else:
                    g.set_edge_label(u,v, round(l))

        # returning a graph with the same embedding, the corersponding name, etc ...
        h = self.subgraph(edges=[])
        h.delete_vertices([v for v in self if (v not in g) or g.degree(v)==0])
        h.add_edges(g.edges())

        return h

    def disjoint_routed_paths(self,pairs, solver=None, verbose=0):
        r"""
        Returns a set of disjoint routed paths.

        Given a set of pairs `(s_i,t_i)`, a set
        of disjoint routed paths is a set of
        `s_i-t_i` paths which can interset at their endpoints
        and are vertex-disjoint otherwise.

        INPUT:

        - ``pairs`` -- list of pairs of vertices

        - ``solver`` -- Specify a Linear Program solver to be used.
          If set to ``None``, the default one is used.
          function of ``MixedIntegerLinearProgram``. See the documentation  of ``MixedIntegerLinearProgram.solve``
          for more informations.

        - ``verbose`` (integer) -- sets the level of verbosity. Set to `0`
          by default (quiet).

        EXAMPLE:

        Given a grid, finding two vertex-disjoint
        paths, the first one from the top-left corner
        to the bottom-left corner, and the second from
        the top-right corner to the bottom-right corner
        is easy ::

            sage: g = graphs.GridGraph([5,5])
            sage: p1,p2 = g.disjoint_routed_paths( [((0,0), (0,4)), ((4,4), (4,0))])

        Though there is obviously no solution to the problem
        in which each corner is sending information to the opposite
        one::

            sage: g = graphs.GridGraph([5,5])
            sage: p1,p2 = g.disjoint_routed_paths( [((0,0), (4,4)), ((0,4), (4,0))])
            Traceback (most recent call last):
            ...
            ValueError: The disjoint routed paths do not exist.
        """

        try:
            return self.multicommodity_flow(pairs, vertex_bound = True, solver=solver, verbose=verbose)
        except ValueError:
            raise ValueError("The disjoint routed paths do not exist.")

    def edge_disjoint_paths(self, s, t):
        r"""
        Returns a list of edge-disjoint paths between two
        vertices as given by Menger's theorem.

        The edge version of Menger's theorem asserts that the size
        of the minimum edge cut between two vertices `s` and`t`
        (the minimum number of edges whose removal disconnects `s`
        and `t`) is equal to the maximum number of pairwise
        edge-independent paths from `s` to `t`.

        This function returns a list of such paths.

        .. NOTE::

            This function is topological : it does not take the eventual
            weights of the edges into account.

        EXAMPLE:

        In a complete bipartite graph ::

            sage: g = graphs.CompleteBipartiteGraph(2,3)
            sage: g.edge_disjoint_paths(0,1)
            [[0, 2, 1], [0, 3, 1], [0, 4, 1]]
        """

        [obj, flow_graph] = self.flow(s,t,value_only=False, integer=True, use_edge_labels=False)

        paths = []

        while True:
            path = flow_graph.shortest_path(s,t)
            if not path:
                break
            v = s
            edges = []
            for w in path:
                edges.append((v,w))
                v=w
            flow_graph.delete_edges(edges)
            paths.append(path)

        return paths

    def vertex_disjoint_paths(self, s, t):
        r"""
        Returns a list of vertex-disjoint paths between two
        vertices as given by Menger's theorem.

        The vertex version of Menger's theorem asserts that the size
        of the minimum vertex cut between two vertices `s` and`t`
        (the minimum number of vertices whose removal disconnects `s`
        and `t`) is equal to the maximum number of pairwise
        vertex-independent paths from `s` to `t`.

        This function returns a list of such paths.

        EXAMPLE:

        In a complete bipartite graph ::

            sage: g = graphs.CompleteBipartiteGraph(2,3)
            sage: g.vertex_disjoint_paths(0,1)
            [[0, 2, 1], [0, 3, 1], [0, 4, 1]]
        """

        [obj, flow_graph] = self.flow(s,t,value_only=False, integer=True, use_edge_labels=False, vertex_bound=True)

        paths = []

        while True:
            path = flow_graph.shortest_path(s,t)
            if not path:
                break
            flow_graph.delete_vertices(path[1:-1])
            paths.append(path)

        return paths

    def matching(self, value_only=False, algorithm="Edmonds", use_edge_labels=True, solver=None, verbose=0):
        r"""
        Returns a maximum weighted matching of the graph
        represented by the list of its edges. For more information, see the
        `Wikipedia article on matchings
        <http://en.wikipedia.org/wiki/Matching_%28graph_theory%29>`_.

        Given a graph `G` such that each edge `e` has a weight `w_e`,
        a maximum matching is a subset `S` of the edges of `G` of
        maximum weight such that no two edges of `S` are incident
        with each other.

        As an optimization problem, it can be expressed as:

        .. math::

            \mbox{Maximize : }&\sum_{e\in G.edges()} w_e b_e\\
            \mbox{Such that : }&\forall v \in G, \sum_{(u,v)\in G.edges()} b_{(u,v)}\leq 1\\
            &\forall x\in G, b_x\mbox{ is a binary variable}

        INPUT:

        - ``value_only`` -- boolean (default: ``False``). When set to
          ``True``, only the cardinal (or the weight) of the matching is
          returned.

        - ``algorithm`` -- string (default: ``"Edmonds"``)

          - ``"Edmonds"`` selects Edmonds' algorithm as implemented in NetworkX

          - ``"LP"`` uses a Linear Program formulation of the matching problem

        - ``use_edge_labels`` -- boolean (default: ``True``)

          - When set to ``True``, computes a weighted matching
            where each edge is weighted by its label. (If
            an edge has no label, `1` is assumed.)

          - When set to ``False``, each edge has weight `1`.

        - ``solver`` -- (default: ``None``) Specify a Linear Program (LP)
          solver to be used. If set to ``None``, the default one is used. For
          more information on LP solvers and which default solver is used, see
          the method
          :meth:`solve <sage.numerical.mip.MixedIntegerLinearProgram.solve>`
          of the class
          :class:`MixedIntegerLinearProgram <sage.numerical.mip.MixedIntegerLinearProgram>`.

        - ``verbose`` -- integer (default: ``0``). Sets the level of
          verbosity. Set to 0 by default, which means quiet.
          Only useful when ``algorithm == "LP"``.

        ALGORITHM:

        The problem is solved using Edmond's algorithm implemented in
        NetworkX, or using Linear Programming depending on the value of
        ``algorithm``.

        EXAMPLES:

        Maximum matching in a Pappus Graph::

           sage: g = graphs.PappusGraph()
           sage: g.matching(value_only=True)
           9.0

        Same test with the Linear Program formulation::

           sage: g = graphs.PappusGraph()
           sage: g.matching(algorithm="LP", value_only=True)
           9.0

        TESTS:

        If ``algorithm`` is set to anything different from ``"Edmonds"`` or
        ``"LP"``, an exception is raised::

           sage: g = graphs.PappusGraph()
           sage: g.matching(algorithm="somethingdifferent")
           Traceback (most recent call last):
           ...
           ValueError: Algorithm must be set to either "Edmonds" or "LP".
        """
        from sage.rings.real_mpfr import RR
        weight = lambda x: x if x in RR else 1

        if algorithm == "Edmonds":
            import networkx
            if use_edge_labels:
                g = networkx.Graph()
                for u, v, l in self.edges():
                    g.add_edge(u, v, attr_dict={"weight": weight(l)})
            else:
                g = self.networkx_graph(copy=False)
            d = networkx.max_weight_matching(g)
            if value_only:
                return sum([weight(self.edge_label(u, v))
                            for u, v in d.iteritems()]) * 0.5
            else:
                return [(u, v, self.edge_label(u, v))
                        for u, v in d.iteritems() if u < v]

        elif algorithm == "LP":
            from sage.numerical.mip import MixedIntegerLinearProgram, Sum
            g = self
            # returns the weight of an edge considering it may not be
            # weighted ...
            p = MixedIntegerLinearProgram(maximization=True)
            b = p.new_variable(dim=2)
            p.set_objective(
                Sum([weight(w) * b[min(u, v)][max(u, v)]
                     for u, v, w in g.edges()]))
            # for any vertex v, there is at most one edge incident to v in
            # the maximum matching
            for v in g.vertex_iterator():
                p.add_constraint(
                    Sum([b[min(u, v)][max(u, v)]
                         for u in g.neighbors(v)]), max=1)
            p.set_binary(b)
            if value_only:
                return p.solve(objective_only=True, solver=solver, log=verbose)
            else:
                p.solve(solver=solver, log=verbose)
                b = p.get_values(b)
                return [(u, v, w) for u, v, w in g.edges()
                        if b[min(u, v)][max(u, v)] == 1]

        else:
            raise ValueError(
                'Algorithm must be set to either "Edmonds" or "LP".')

    def dominating_set(self, independent=False, value_only=False, solver=None, verbose=0):
        r"""
        Returns a minimum dominating set of the graph
        represented by the list of its vertices. For more information, see the
        `Wikipedia article on dominating sets
        <http://en.wikipedia.org/wiki/Dominating_set>`_.

        A minimum dominating set `S` of a graph `G` is
        a set of its vertices of minimal cardinality such
        that any vertex of `G` is in `S` or has one of its neighbors
        in `S`.

        As an optimization problem, it can be expressed as:

        .. MATH::

            \mbox{Minimize : }&\sum_{v\in G} b_v\\
            \mbox{Such that : }&\forall v \in G, b_v+\sum_{(u,v)\in G.edges()} b_u\geq 1\\
            &\forall x\in G, b_x\mbox{ is a binary variable}

        INPUT:

        - ``independent`` -- boolean (default: ``False``). If
          ``independent=True``, computes a minimum independent dominating set.

        - ``value_only`` -- boolean (default: ``False``)

          - If ``True``, only the cardinality of a minimum
            dominating set is returned.

          - If ``False`` (default), a minimum dominating set
            is returned as the list of its vertices.

        - ``solver`` -- (default: ``None``) Specify a Linear Program (LP)
          solver to be used. If set to ``None``, the default one is used. For
          more information on LP solvers and which default solver is used, see
          the method
          :meth:`solve <sage.numerical.mip.MixedIntegerLinearProgram.solve>`
          of the class
          :class:`MixedIntegerLinearProgram <sage.numerical.mip.MixedIntegerLinearProgram>`.

        - ``verbose`` -- integer (default: ``0``). Sets the level of
          verbosity. Set to 0 by default, which means quiet.

        EXAMPLES:

        A basic illustration on a ``PappusGraph``::

           sage: g=graphs.PappusGraph()
           sage: g.dominating_set(value_only=True)
           5.0

        If we build a graph from two disjoint stars, then link their centers
        we will find a difference between the cardinality of an independent set
        and a stable independent set::

           sage: g = 2 * graphs.StarGraph(5)
           sage: g.add_edge(0,6)
           sage: len(g.dominating_set())
           2
           sage: len(g.dominating_set(independent=True))
           6

        """
        from sage.numerical.mip import MixedIntegerLinearProgram, Sum
        g=self
        p=MixedIntegerLinearProgram(maximization=False)
        b=p.new_variable()

        # For any vertex v, one of its neighbors or v itself is in
        # the minimum dominating set
        for v in g.vertices():
            p.add_constraint(b[v]+Sum([b[u] for u in g.neighbors(v)]),min=1)


        if independent:
            # no two adjacent vertices are in the set
            for (u,v) in g.edges(labels=None):
                p.add_constraint(b[u]+b[v],max=1)

        # Minimizes the number of vertices used
        p.set_objective(Sum([b[v] for v in g.vertices()]))

        p.set_integer(b)

        if value_only:
            return p.solve(objective_only=True, solver=solver, log=verbose)
        else:
            p.solve(solver=solver, log=verbose)
            b=p.get_values(b)
            return [v for v in g.vertices() if b[v]==1]

    def edge_connectivity(self, value_only=True, use_edge_labels=False, vertices=False, solver=None, verbose=0):
        r"""
        Returns the edge connectivity of the graph. For more information, see
        the
        `Wikipedia article on connectivity
        <http://en.wikipedia.org/wiki/Connectivity_(graph_theory)>`_.

        INPUT:

        - ``value_only`` -- boolean (default: ``True``)

          - When set to ``True`` (default), only the value is returned.

          - When set to ``False``, both the value and a minimum edge cut
            are returned.

        - ``use_edge_labels`` -- boolean (default: ``False``)

          - When set to ``True``, computes a weighted minimum cut
            where each edge has a weight defined by its label. (If
            an edge has no label, `1` is assumed.)

          - When set to ``False``, each edge has weight `1`.

        - ``vertices`` -- boolean (default: ``False``)

          - When set to ``True``, also returns the two sets of
            vertices that are disconnected by the cut. Implies
            ``value_only=False``.

        - ``solver`` -- (default: ``None``) Specify a Linear Program (LP)
          solver to be used. If set to ``None``, the default one is used. For
          more information on LP solvers and which default solver is used, see
          the method
          :meth:`solve <sage.numerical.mip.MixedIntegerLinearProgram.solve>`
          of the class
          :class:`MixedIntegerLinearProgram <sage.numerical.mip.MixedIntegerLinearProgram>`.

        - ``verbose`` -- integer (default: ``0``). Sets the level of
          verbosity. Set to 0 by default, which means quiet.

        EXAMPLES:

        A basic application on the PappusGraph::

           sage: g = graphs.PappusGraph()
           sage: g.edge_connectivity()
           3.0

        The edge connectivity of a complete graph ( and of a random graph )
        is its minimum degree, and one of the two parts of the bipartition
        is reduced to only one vertex. The cutedges isomorphic to a
        Star graph::

           sage: g = graphs.CompleteGraph(5)
           sage: [ value, edges, [ setA, setB ]] = g.edge_connectivity(vertices=True)
           sage: print value
           4.0
           sage: len(setA) == 1 or len(setB) == 1
           True
           sage: cut = Graph()
           sage: cut.add_edges(edges)
           sage: cut.is_isomorphic(graphs.StarGraph(4))
           True

        Even if obviously in any graph we know that the edge connectivity
        is less than the minimum degree of the graph::

           sage: g = graphs.RandomGNP(10,.3)
           sage: min(g.degree()) >= g.edge_connectivity()
           True

        If we build a tree then assign to its edges a random value, the
        minimum cut will be the edge with minimum value::

           sage: g = graphs.RandomGNP(15,.5)
           sage: tree = Graph()
           sage: tree.add_edges(g.min_spanning_tree())
           sage: for u,v in tree.edge_iterator(labels=None):
           ...        tree.set_edge_label(u,v,random())
           sage: minimum = min([l for u,v,l in tree.edge_iterator()])
           sage: [value, [(u,v,l)]] = tree.edge_connectivity(value_only=False, use_edge_labels=True)
           sage: l == minimum
           True

        When ``value_only = True``, this function is optimized for small
        connexity values and does not need to build a linear program.

        It is the case for connected graphs which are not
        connected ::

           sage: g = 2 * graphs.PetersenGraph()
           sage: g.edge_connectivity()
           0.0

        Or if they are just 1-connected ::

           sage: g = graphs.PathGraph(10)
           sage: g.edge_connectivity()
           1.0

        For directed graphs, the strong connexity is tested
        through the dedicated function ::

           sage: g = digraphs.ButterflyGraph(3)
           sage: g.edge_connectivity()
           0.0
        """
        g=self

        if vertices:
            value_only=False

        if use_edge_labels:
            from sage.rings.real_mpfr import RR
            weight=lambda x: x if x in RR else 1
        else:
            weight=lambda x: 1


        # Better methods for small connectivity tests,
        # when one is not interested in cuts...
        if value_only and not use_edge_labels:

            if self.is_directed():
                if not self.is_strongly_connected():
                    return 0.0

            else:
                if not self.is_connected():
                    return 0.0

                h = self.strong_orientation()
                if not h.is_strongly_connected():
                    return 1.0


        if g.is_directed():
            reorder_edge = lambda x,y : (x,y)
        else:
            reorder_edge = lambda x,y : (x,y) if x<= y else (y,x)

        from sage.numerical.mip import MixedIntegerLinearProgram, Sum

        p = MixedIntegerLinearProgram(maximization=False)

        in_set = p.new_variable(dim=2)
        in_cut = p.new_variable(dim=1)


        # A vertex has to be in some set
        for v in g:
            p.add_constraint(in_set[0][v]+in_set[1][v],max=1,min=1)

        # There is no empty set
        p.add_constraint(Sum([in_set[1][v] for v in g]),min=1)
        p.add_constraint(Sum([in_set[0][v] for v in g]),min=1)

        if g.is_directed():
            # There is no edge from set 0 to set 1 which
            # is not in the cut
            for (u,v) in g.edge_iterator(labels=None):
                p.add_constraint(in_set[0][u] + in_set[1][v] - in_cut[(u,v)], max = 1)
        else:

            # Two adjacent vertices are in different sets if and only if
            # the edge between them is in the cut

            for (u,v) in g.edge_iterator(labels=None):
                p.add_constraint(in_set[0][u]+in_set[1][v]-in_cut[reorder_edge(u,v)],max=1)
                p.add_constraint(in_set[1][u]+in_set[0][v]-in_cut[reorder_edge(u,v)],max=1)


        p.set_binary(in_set)
        p.set_binary(in_cut)

        p.set_objective(Sum([weight(l ) * in_cut[reorder_edge(u,v)] for (u,v,l) in g.edge_iterator()]))

        if value_only:
            return p.solve(objective_only=True, solver=solver, log=verbose)
        else:
            val = [p.solve(solver=solver, log=verbose)]

            in_cut = p.get_values(in_cut)
            in_set = p.get_values(in_set)

            edges = []
            for (u,v,l) in g.edge_iterator():
                if in_cut[reorder_edge(u,v)] == 1:
                    edges.append((u,v,l))

            val.append(edges)

            if vertices:
                a = []
                b = []
                for v in g:
                    if in_set[0][v] == 1:
                        a.append(v)
                    else:
                        b.append(v)
                val.append([a,b])

            return val

    def vertex_connectivity(self, value_only=True, sets=False, solver=None, verbose=0):
        r"""
        Returns the vertex connectivity of the graph. For more information,
        see the
        `Wikipedia article on connectivity
        <http://en.wikipedia.org/wiki/Connectivity_(graph_theory)>`_.

        INPUT:


        - ``value_only`` -- boolean (default: ``True``)

          - When set to ``True`` (default), only the value is returned.

          - When set to ``False`` , both the value and a minimum edge cut
            are returned.

        - ``sets`` -- boolean (default: ``False``)

          - When set to ``True``, also returns the two sets of
            vertices that are disconnected by the cut.
            Implies ``value_only=False``

        - ``solver`` -- (default: ``None``) Specify a Linear Program (LP)
          solver to be used. If set to ``None``, the default one is used. For
          more information on LP solvers and which default solver is used, see
          the method
          :meth:`solve <sage.numerical.mip.MixedIntegerLinearProgram.solve>`
          of the class
          :class:`MixedIntegerLinearProgram <sage.numerical.mip.MixedIntegerLinearProgram>`.

        - ``verbose`` -- integer (default: ``0``). Sets the level of
          verbosity. Set to 0 by default, which means quiet.

        EXAMPLES:

        A basic application on a ``PappusGraph``::

           sage: g=graphs.PappusGraph()
           sage: g.vertex_connectivity()
           3.0

        In a grid, the vertex connectivity is equal to the
        minimum degree, in which case one of the two sets it
        of cardinality `1`::

           sage: g = graphs.GridGraph([ 3,3 ])
           sage: [value, cut, [ setA, setB ]] = g.vertex_connectivity(sets=True)
           sage: len(setA) == 1 or len(setB) == 1
           True

        A vertex cut in a tree is any internal vertex::

           sage: g = graphs.RandomGNP(15,.5)
           sage: tree = Graph()
           sage: tree.add_edges(g.min_spanning_tree())
           sage: [val, [cut_vertex]] = tree.vertex_connectivity(value_only=False)
           sage: tree.degree(cut_vertex) > 1
           True

        When ``value_only = True``, this function is optimized for small
        connexity values and does not need to build a linear program.

        It is the case for connected graphs which are not
        connected::

           sage: g = 2 * graphs.PetersenGraph()
           sage: g.vertex_connectivity()
           0.0

        Or if they are just 1-connected::

           sage: g = graphs.PathGraph(10)
           sage: g.vertex_connectivity()
           1.0

        For directed graphs, the strong connexity is tested
        through the dedicated function::

           sage: g = digraphs.ButterflyGraph(3)
           sage: g.vertex_connectivity()
           0.0

        """
        g=self

        if g.is_clique():
            raise ValueError("There can be no vertex cut in a complete graph.")

        if sets:
            value_only=False

        if value_only:
            if self.is_directed():
                if not self.is_strongly_connected():
                    return 0.0

            else:
                if not self.is_connected():
                    return 0.0

                if len(self.blocks_and_cut_vertices()[0]) > 1:
                    return 1.0


        if g.is_directed():
            reorder_edge = lambda x,y : (x,y)
        else:
            reorder_edge = lambda x,y : (x,y) if x<= y else (y,x)

        from sage.numerical.mip import MixedIntegerLinearProgram, Sum

        p = MixedIntegerLinearProgram(maximization=False)

        # Sets 0 and 2 are "real" sets while set 1 represents the cut
        in_set = p.new_variable(dim=2)


        # A vertex has to be in some set
        for v in g:
            p.add_constraint(in_set[0][v]+in_set[1][v]+in_set[2][v],max=1,min=1)

        # There is no empty set
        p.add_constraint(Sum([in_set[0][v] for v in g]),min=1)
        p.add_constraint(Sum([in_set[2][v] for v in g]),min=1)

        if g.is_directed():
            # There is no edge from set 0 to set 1 which
            # is not in the cut
            for (u,v) in g.edge_iterator(labels=None):
                p.add_constraint(in_set[0][u] + in_set[2][v], max = 1)
        else:

            # Two adjacent vertices are in different sets if and only if
            # the edge between them is in the cut

            for (u,v) in g.edge_iterator(labels=None):
                p.add_constraint(in_set[0][u]+in_set[2][v],max=1)
                p.add_constraint(in_set[2][u]+in_set[0][v],max=1)


        p.set_binary(in_set)

        p.set_objective(Sum([in_set[1][v] for v in g]))

        if value_only:
            return p.solve(objective_only=True, solver=solver, log=verbose)
        else:
            val = [int(p.solve(solver=solver, log=verbose))]

            in_set = p.get_values(in_set)


            cut = []
            a = []
            b = []

            for v in g:
                if in_set[0][v] == 1:
                    a.append(v)
                elif in_set[1][v]==1:
                    cut.append(v)
                else:
                    b.append(v)


            val.append(cut)

            if sets:
                val.append([a,b])

            return val


    ### Vertex handlers

    def add_vertex(self, name=None):
        """
        Creates an isolated vertex. If the vertex already exists, then
        nothing is done.

        INPUT:

        -  ``name`` - Name of the new vertex. If no name is
           specified, then the vertex will be represented by the least integer
           not already representing a vertex. Name must be an immutable
           object, and cannot be None.

        As it is implemented now, if a graph `G` has a large number
        of vertices with numeric labels, then G.add_vertex() could
        potentially be slow, if name is None.

        EXAMPLES::

            sage: G = Graph(); G.add_vertex(); G
            Graph on 1 vertex

        ::

            sage: D = DiGraph(); D.add_vertex(); D
            Digraph on 1 vertex

        """
        self._backend.add_vertex(name)

    def add_vertices(self, vertices):
        """
        Add vertices to the (di)graph from an iterable container of
        vertices. Vertices that already exist in the graph will not be
        added again.

        EXAMPLES::

            sage: d = {0: [1,4,5], 1: [2,6], 2: [3,7], 3: [4,8], 4: [9], 5: [7,8], 6: [8,9], 7: [9]}
            sage: G = Graph(d)
            sage: G.add_vertices([10,11,12])
            sage: G.vertices()
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
            sage: G.add_vertices(graphs.CycleGraph(25).vertices())
            sage: G.vertices()
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]
        """
        self._backend.add_vertices(vertices)

    def delete_vertex(self, vertex, in_order=False):
        """
        Deletes vertex, removing all incident edges. Deleting a
        non-existent vertex will raise an exception.

        INPUT:


        -  ``in_order`` - (default False) If True, this
           deletes the ith vertex in the sorted list of vertices, i.e.
           G.vertices()[i]


        EXAMPLES::

            sage: G = Graph(graphs.WheelGraph(9))
            sage: G.delete_vertex(0); G.show()

        ::

            sage: D = DiGraph({0:[1,2,3,4,5],1:[2],2:[3],3:[4],4:[5],5:[1]})
            sage: D.delete_vertex(0); D
            Digraph on 5 vertices
            sage: D.vertices()
            [1, 2, 3, 4, 5]
            sage: D.delete_vertex(0)
            Traceback (most recent call last):
            ...
            RuntimeError: Vertex (0) not in the graph.

        ::

            sage: G = graphs.CompleteGraph(4).line_graph(labels=False)
            sage: G.vertices()
            [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
            sage: G.delete_vertex(0, in_order=True)
            sage: G.vertices()
            [(0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
            sage: G = graphs.PathGraph(5)
            sage: G.set_vertices({0: 'no delete', 1: 'delete'})
            sage: G.set_boundary([1,2])
            sage: G.delete_vertex(1)
            sage: G.get_vertices()
            {0: 'no delete', 2: None, 3: None, 4: None}
            sage: G.get_boundary()
            [2]
            sage: G.get_pos()
            {0: (0, 0), 2: (2, 0), 3: (3, 0), 4: (4, 0)}
        """
        if in_order:
            vertex = self.vertices()[vertex]
        if vertex not in self:
            raise RuntimeError("Vertex (%s) not in the graph."%vertex)

        attributes_to_update = ('_pos', '_assoc', '_embedding')
        for attr in attributes_to_update:
            if hasattr(self, attr) and getattr(self, attr) is not None:
                getattr(self, attr).pop(vertex, None)
        self._boundary = [v for v in self._boundary if v != vertex]

        self._backend.del_vertex(vertex)

    def delete_vertices(self, vertices):
        """
        Remove vertices from the (di)graph taken from an iterable container
        of vertices. Deleting a non-existent vertex will raise an
        exception.

        EXAMPLES::

            sage: D = DiGraph({0:[1,2,3,4,5],1:[2],2:[3],3:[4],4:[5],5:[1]})
            sage: D.delete_vertices([1,2,3,4,5]); D
            Digraph on 1 vertex
            sage: D.vertices()
            [0]
            sage: D.delete_vertices([1])
            Traceback (most recent call last):
            ...
            RuntimeError: Vertex (1) not in the graph.

        """
        for vertex in vertices:
            if vertex not in self:
                raise RuntimeError("Vertex (%s) not in the graph."%vertex)
        attributes_to_update = ('_pos', '_assoc', '_embedding')
        for attr in attributes_to_update:
            if hasattr(self, attr) and getattr(self, attr) is not None:
                attr_dict = getattr(self, attr)
                for vertex in vertices:
                    attr_dict.pop(vertex, None)

        self._boundary = [v for v in self._boundary if v not in vertices]

        self._backend.del_vertices(vertices)

    def has_vertex(self, vertex):
        """
        Return True if vertex is one of the vertices of this graph.

        INPUT:


        -  ``vertex`` - an integer


        OUTPUT:


        -  ``bool`` - True or False


        EXAMPLES::

            sage: g = Graph({0:[1,2,3], 2:[4]}); g
            Graph on 5 vertices
            sage: 2 in g
            True
            sage: 10 in g
            False
            sage: graphs.PetersenGraph().has_vertex(99)
            False
        """
        try:
            hash(vertex)
        except:
            return False
        return self._backend.has_vertex(vertex)

    __contains__ = has_vertex

    def random_vertex(self, **kwds):
        r"""
        Returns a random vertex of self.

        INPUT:

        - ``**kwds`` - arguments to be passed down to the
          ``vertex_iterator`` method.

        EXAMPLE:

        The returned value is a vertex of self::

            sage: g = graphs.PetersenGraph()
            sage: v = g.random_vertex()
            sage: v in g
            True
        """
        from sage.misc.prandom import randint
        it = self.vertex_iterator(**kwds)
        for i in xrange(0, randint(0, self.order() - 1)):
            it.next()
        return it.next()

    def random_edge(self,**kwds):
        r"""
        Returns a random edge of self.

        INPUT:

        - ``**kwds`` - arguments to be passed down to the
          ``edge_iterator`` method.

        EXAMPLE:

        The returned value is an edge of self::

            sage: g = graphs.PetersenGraph()
            sage: u,v = g.random_edge(labels=False)
            sage: g.has_edge(u,v)
            True

        As the ``edges()`` method would, this function returns
        by default a triple ``(u,v,l)`` of values, in which
        ``l`` is the label of edge `(u,v)`::

            sage: g.random_edge()
            (3, 4, None)
        """
        from sage.misc.prandom import randint
        it = self.edge_iterator(**kwds)
        for i in xrange(0, randint(0, self.size() - 1)):
            it.next()
        return it.next()

    def vertex_boundary(self, vertices1, vertices2=None):
        """
        Returns a list of all vertices in the external boundary of
        vertices1, intersected with vertices2. If vertices2 is None, then
        vertices2 is the complement of vertices1. This is much faster if
        vertices1 is smaller than vertices2.

        The external boundary of a set of vertices is the union of the
        neighborhoods of each vertex in the set. Note that in this
        implementation, since vertices2 defaults to the complement of
        vertices1, if a vertex `v` has a loop, then
        vertex_boundary(v) will not contain `v`.

        In a digraph, the external boundary of a vertex v are those
        vertices u with an arc (v, u).

        EXAMPLES::

            sage: G = graphs.CubeGraph(4)
            sage: l = ['0111', '0000', '0001', '0011', '0010', '0101', '0100', '1111', '1101', '1011', '1001']
            sage: G.vertex_boundary(['0000', '1111'], l)
            ['0111', '0001', '0010', '0100', '1101', '1011']

        ::

            sage: D = DiGraph({0:[1,2], 3:[0]})
            sage: D.vertex_boundary([0])
            [1, 2]
        """
        vertices1 = [v for v in vertices1 if v in self]
        output = set()
        if self._directed:
            for v in vertices1:
                output.update(self.neighbor_out_iterator(v))
        else:
            for v in vertices1:
                output.update(self.neighbor_iterator(v))
        if vertices2 is not None:
            output.intersection_update(vertices2)
        return list(output)

    def set_vertices(self, vertex_dict):
        """
        Associate arbitrary objects with each vertex, via an association
        dictionary.

        INPUT:


        -  ``vertex_dict`` - the association dictionary


        EXAMPLES::

            sage: d = {0 : graphs.DodecahedralGraph(), 1 : graphs.FlowerSnark(), 2 : graphs.MoebiusKantorGraph(), 3 : graphs.PetersenGraph() }
            sage: d[2]
            Moebius-Kantor Graph: Graph on 16 vertices
            sage: T = graphs.TetrahedralGraph()
            sage: T.vertices()
            [0, 1, 2, 3]
            sage: T.set_vertices(d)
            sage: T.get_vertex(1)
            Flower Snark: Graph on 20 vertices
        """
        if hasattr(self, '_assoc') is False:
            self._assoc = {}

        self._assoc.update(vertex_dict)

    def set_vertex(self, vertex, object):
        """
        Associate an arbitrary object with a vertex.

        INPUT:


        -  ``vertex`` - which vertex

        -  ``object`` - object to associate to vertex


        EXAMPLES::

            sage: T = graphs.TetrahedralGraph()
            sage: T.vertices()
            [0, 1, 2, 3]
            sage: T.set_vertex(1, graphs.FlowerSnark())
            sage: T.get_vertex(1)
            Flower Snark: Graph on 20 vertices
        """
        if hasattr(self, '_assoc') is False:
            self._assoc = {}

        self._assoc[vertex] = object

    def get_vertex(self, vertex):
        """
        Retrieve the object associated with a given vertex.

        INPUT:


        -  ``vertex`` - the given vertex


        EXAMPLES::

            sage: d = {0 : graphs.DodecahedralGraph(), 1 : graphs.FlowerSnark(), 2 : graphs.MoebiusKantorGraph(), 3 : graphs.PetersenGraph() }
            sage: d[2]
            Moebius-Kantor Graph: Graph on 16 vertices
            sage: T = graphs.TetrahedralGraph()
            sage: T.vertices()
            [0, 1, 2, 3]
            sage: T.set_vertices(d)
            sage: T.get_vertex(1)
            Flower Snark: Graph on 20 vertices
        """
        if hasattr(self, '_assoc') is False:
            return None

        return self._assoc.get(vertex, None)

    def get_vertices(self, verts=None):
        """
        Return a dictionary of the objects associated to each vertex.

        INPUT:


        -  ``verts`` - iterable container of vertices


        EXAMPLES::

            sage: d = {0 : graphs.DodecahedralGraph(), 1 : graphs.FlowerSnark(), 2 : graphs.MoebiusKantorGraph(), 3 : graphs.PetersenGraph() }
            sage: T = graphs.TetrahedralGraph()
            sage: T.set_vertices(d)
            sage: T.get_vertices([1,2])
            {1: Flower Snark: Graph on 20 vertices,
             2: Moebius-Kantor Graph: Graph on 16 vertices}
        """
        if verts is None:
            verts = self.vertices()

        if hasattr(self, '_assoc') is False:
            return dict.fromkeys(verts, None)

        output = {}

        for v in verts:
            output[v] = self._assoc.get(v, None)

        return output

    def loop_vertices(self):
        """
        Returns a list of vertices with loops.

        EXAMPLES::

            sage: G = Graph({0 : [0], 1: [1,2,3], 2: [3]}, loops=True)
            sage: G.loop_vertices()
            [0, 1]
        """
        if self.allows_loops():
            return [v for v in self if self.has_edge(v,v)]
        else:
            return []

    def vertex_iterator(self, vertices=None):
        """
        Returns an iterator over the given vertices. Returns False if not
        given a vertex, sequence, iterator or None. None is equivalent to a
        list of every vertex. Note that ``for v in G`` syntax
        is allowed.

        INPUT:


        -  ``vertices`` - iterated vertices are these
           intersected with the vertices of the (di)graph


        EXAMPLES::

            sage: P = graphs.PetersenGraph()
            sage: for v in P.vertex_iterator():
            ...    print v
            ...
            0
            1
            2
            ...
            8
            9

        ::

            sage: G = graphs.TetrahedralGraph()
            sage: for i in G:
            ...    print i
            0
            1
            2
            3

        Note that since the intersection option is available, the
        vertex_iterator() function is sub-optimal, speed-wise, but note the
        following optimization::

            sage: timeit V = P.vertices()                   # not tested
            100000 loops, best of 3: 8.85 [micro]s per loop
            sage: timeit V = list(P.vertex_iterator())      # not tested
            100000 loops, best of 3: 5.74 [micro]s per loop
            sage: timeit V = list(P._nxg.adj.iterkeys())    # not tested
            100000 loops, best of 3: 3.45 [micro]s per loop

        In other words, if you want a fast vertex iterator, call the
        dictionary directly.
        """
        return self._backend.iterator_verts(vertices)

    __iter__ = vertex_iterator

    def neighbor_iterator(self, vertex):
        """
        Return an iterator over neighbors of vertex.

        EXAMPLES::

            sage: G = graphs.CubeGraph(3)
            sage: for i in G.neighbor_iterator('010'):
            ...    print i
            011
            000
            110
            sage: D = G.to_directed()
            sage: for i in D.neighbor_iterator('010'):
            ...    print i
            011
            000
            110

        ::

            sage: D = DiGraph({0:[1,2], 3:[0]})
            sage: list(D.neighbor_iterator(0))
            [1, 2, 3]
        """
        if self._directed:
            return iter(set(self.neighbor_out_iterator(vertex)) \
                    | set(self.neighbor_in_iterator(vertex)))
        else:
            return iter(set(self._backend.iterator_nbrs(vertex)))

    def vertices(self, boundary_first=False):
        """
        Return a list of the vertices.

        INPUT:


        -  ``boundary_first`` - Return the boundary vertices
           first.


        EXAMPLES::

            sage: P = graphs.PetersenGraph()
            sage: P.vertices()
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

        Note that the output of the vertices() function is always sorted.
        This is sub-optimal, speed-wise, but note the following
        optimizations::

            sage: timeit V = P.vertices()                     # not tested
            100000 loops, best of 3: 8.85 [micro]s per loop
            sage: timeit V = list(P.vertex_iterator())        # not tested
            100000 loops, best of 3: 5.74 [micro]s per loop
            sage: timeit V = list(P._nxg.adj.iterkeys())      # not tested
            100000 loops, best of 3: 3.45 [micro]s per loop

        In other words, if you want a fast vertex iterator, call the
        dictionary directly.
        """
        if not boundary_first:
            return sorted(list(self.vertex_iterator()))

        bdy_verts = []
        int_verts = []
        for v in self.vertex_iterator():
            if v in self._boundary:
                bdy_verts.append(v)
            else:
                int_verts.append(v)
        return sorted(bdy_verts) + sorted(int_verts)

    def neighbors(self, vertex):
        """
        Return a list of neighbors (in and out if directed) of vertex.

        G[vertex] also works.

        EXAMPLES::

            sage: P = graphs.PetersenGraph()
            sage: sorted(P.neighbors(3))
            [2, 4, 8]
            sage: sorted(P[4])
            [0, 3, 9]
        """
        return list(self.neighbor_iterator(vertex))

    __getitem__ = neighbors


    def merge_vertices(self,vertices):
        r"""
        Merge vertices.

        This function replaces a set `S` of vertices by a single vertex
        `v_{new}`, such that the edge `uv_{new}` exists if and only if
        `\exists v'\in S: (u,v')\in G`.

        The new vertex is named after the first vertex in the list
        given in argument.

        In the case of multigraphs, the multiplicity is preserved.

        INPUT:

        - ``vertices`` -- the set of vertices to be merged

        EXAMPLE::

            sage: g=graphs.CycleGraph(3)
            sage: g.merge_vertices([0,1])
            sage: g.edges()
            [(0, 2, {})]
            sage: # With a Multigraph :
            sage: g=graphs.CycleGraph(3)
            sage: g.allow_multiple_edges(True)
            sage: g.merge_vertices([0,1])
            sage: g.edges()
            [(0, 2, {}), (0, 2, {})]
            sage: P=graphs.PetersenGraph()
            sage: P.merge_vertices([5,7])
            sage: P.vertices()
            [0, 1, 2, 3, 4, 5, 6, 8, 9]

        """

        if self.is_directed():
            out_edges=self.edge_boundary(vertices)
            in_edges=self.edge_boundary([v for v in self if not v in vertices])
            self.delete_vertices(vertices[1:])
            self.add_edges([(vertices[0],v,l) for (u,v,l) in out_edges if u!=vertices[0]])
            self.add_edges([(v,vertices[0],l) for (v,u,l) in in_edges if u!=vertices[0]])
        else:
            edges=self.edge_boundary(vertices)
            self.delete_vertices(vertices[1:])
            add_edges=[]
            for (u,v,l) in edges:
                if v in vertices and v != vertices[0]:
                    add_edges.append((vertices[0],u,l))
                if u in vertices and u!=vertices[0]:
                    add_edges.append((vertices[0],v,l))
            self.add_edges(add_edges)


    ### Edge handlers

    def add_edge(self, u, v=None, label=None):
        """
        Adds an edge from u and v.

        INPUT: The following forms are all accepted:

        - G.add_edge( 1, 2 )
        - G.add_edge( (1, 2) )
        - G.add_edges( [ (1, 2) ])
        - G.add_edge( 1, 2, 'label' )
        - G.add_edge( (1, 2, 'label') )
        - G.add_edges( [ (1, 2, 'label') ] )

        WARNING: The following intuitive input results in nonintuitive
        output::

            sage: G = Graph()
            sage: G.add_edge((1,2), 'label')
            sage: G.networkx_graph().adj           # random output order
            {'label': {(1, 2): None}, (1, 2): {'label': None}}

        Use one of these instead::

            sage: G = Graph()
            sage: G.add_edge((1,2), label="label")
            sage: G.networkx_graph().adj           # random output order
            {1: {2: 'label'}, 2: {1: 'label'}}

        ::

            sage: G = Graph()
            sage: G.add_edge(1,2,'label')
            sage: G.networkx_graph().adj           # random output order
            {1: {2: 'label'}, 2: {1: 'label'}}

        The following syntax is supported, but note that you must use
        the ``label`` keyword::

            sage: G = Graph()
            sage: G.add_edge((1,2), label='label')
            sage: G.edges()
            [(1, 2, 'label')]
            sage: G = Graph()
            sage: G.add_edge((1,2), 'label')
            sage: G.edges()
            [('label', (1, 2), None)]

        """
        if label is None:
            if v is None:
                try:
                    u, v, label = u
                except:
                    u, v = u
                    label = None
        else:
            if v is None:
                u, v = u
        if not self.allows_loops() and u==v:
            return
        self._backend.add_edge(u, v, label, self._directed)

    def add_edges(self, edges):
        """
        Add edges from an iterable container.

        EXAMPLES::

            sage: G = graphs.DodecahedralGraph()
            sage: H = Graph()
            sage: H.add_edges( G.edge_iterator() ); H
            Graph on 20 vertices
            sage: G = graphs.DodecahedralGraph().to_directed()
            sage: H = DiGraph()
            sage: H.add_edges( G.edge_iterator() ); H
            Digraph on 20 vertices
        """
        for e in edges:
            self.add_edge(e)

    def subdivide_edge(self, *args):
        """
        Subdivides an edge `k` times.

        INPUT:

        The following forms are all accepted to subdivide `8` times
        the edge between vertices `1` and `2` labeled with
        ``"my_label"``.

        - ``G.subdivide_edge( 1, 2, 8 )``
        - ``G.subdivide_edge( (1, 2), 8 )``
        - ``G.subdivide_edge( (1, 2, "my_label"), 8 )``

        .. NOTE::

            * If the given edge is labelled with `l`, all the edges
              created by the subdivision will have the same label.

            * If no label is given, the label used will be the one
              returned by the method :meth:`edge_label` on the pair
              ``u,v``

        EXAMPLE:

        Subdividing `5` times an edge in a path of length
        `3` makes it a path of length `8`::

            sage: g = graphs.PathGraph(3)
            sage: edge = g.edges()[0]
            sage: g.subdivide_edge(edge, 5)
            sage: g.is_isomorphic(graphs.PathGraph(8))
            True

        Subdividing a labelled edge in two ways ::

            sage: g = Graph()
            sage: g.add_edge(0,1,"label1")
            sage: g.add_edge(1,2,"label2")
            sage: print sorted(g.edges())
            [(0, 1, 'label1'), (1, 2, 'label2')]

        Specifying the label::

            sage: g.subdivide_edge(0,1,"label1", 3)
            sage: print sorted(g.edges())
            [(0, 3, 'label1'), (1, 2, 'label2'), (1, 5, 'label1'), (3, 4, 'label1'), (4, 5, 'label1')]

        The lazy way::

            sage: g.subdivide_edge(1,2,"label2", 5)
            sage: print sorted(g.edges())
            [(0, 3, 'label1'), (1, 5, 'label1'), (1, 6, 'label2'), (2, 10, 'label2'), (3, 4, 'label1'), (4, 5, 'label1'), (6, 7, 'label2'), (7, 8, 'label2'), (8, 9, 'label2'), (9, 10, 'label2')]

        If too many arguments are given, an exception is raised ::

            sage: g.subdivide_edge(0,1,1,1,1,1,1,1,1,1,1)
            Traceback (most recent call last):
            ...
            ValueError: This method takes at most 4 arguments !

        The same goes when the given edge does not exist::

            sage: g.subdivide_edge(0,1,"fake_label",5)
            Traceback (most recent call last):
            ...
            ValueError: The given edge does not exist.

        .. SEEALSO::

        - :meth:`subdivide_edges` -- subdivides multiples edges at a time

        """

        if len(args) == 2:
            edge, k = args

            if len(edge) == 2:
                u,v = edge
                l = self.edge_label(u,v)
            elif len(edge) == 3:
                u,v,l = edge

        elif len(args) == 3:
            u, v, k = args
            l = self.edge_label(u,v)

        elif len(args) == 4:
            u, v, l, k = args

        else:
            raise ValueError("This method takes at most 4 arguments !")

        if not self.has_edge(u,v,l):
            raise ValueError("The given edge does not exist.")

        for i in xrange(k):
            self.add_vertex()

        self.delete_edge(u,v,l)

        edges = []
        for uu in self.vertices()[-k:] + [v]:
            edges.append((u,uu,l))
            u = uu

        self.add_edges(edges)

    def subdivide_edges(self, edges, k):
        """
        Subdivides k times edges from an iterable container.

        For more information on the behaviour of this method, please
        refer to the documentation of :meth:`subdivide_edge`.

        INPUT:

        - ``edges`` -- a list of edges

        - ``k`` (integer) -- common length of the subdivisions


        .. NOTE::

            If a given edge is labelled with `l`, all the edges
            created by its subdivision will have the same label.

        EXAMPLE:

        If we are given the disjoint union of several paths::

            sage: paths = [2,5,9]
            sage: paths = map(graphs.PathGraph, paths)
            sage: g = Graph()
            sage: for P in paths:
            ...     g = g + P

        ... subdividing edges in each of them will only change their
        lengths::

            sage: edges = [P.edges()[0] for P in g.connected_components_subgraphs()]
            sage: k = 6
            sage: g.subdivide_edges(edges, k)

        Let us check this by creating the graph we expect to have built
        through subdivision::

            sage: paths2 = [2+k, 5+k, 9+k]
            sage: paths2 = map(graphs.PathGraph, paths2)
            sage: g2 = Graph()
            sage: for P in paths2:
            ...     g2 = g2 + P
            sage: g.is_isomorphic(g2)
            True

        .. SEEALSO::

        - :meth:`subdivide_edge` -- subdivides one edge
        """
        for e in edges:
            self.subdivide_edge(e, k)

    def delete_edge(self, u, v=None, label=None):
        r"""
        Delete the edge from u to v, returning silently if vertices or edge
        does not exist.

        INPUT: The following forms are all accepted:

        - G.delete_edge( 1, 2 )
        - G.delete_edge( (1, 2) )
        - G.delete_edges( [ (1, 2) ] )
        - G.delete_edge( 1, 2, 'label' )
        - G.delete_edge( (1, 2, 'label') )
        - G.delete_edges( [ (1, 2, 'label') ] )

        EXAMPLES::

            sage: G = graphs.CompleteGraph(19).copy(implementation='c_graph')
            sage: G.size()
            171
            sage: G.delete_edge( 1, 2 )
            sage: G.delete_edge( (3, 4) )
            sage: G.delete_edges( [ (5, 6), (7, 8) ] )
            sage: G.size()
            167

        Note that NetworkX accidentally deletes these edges, even though the
        labels do not match up::

            sage: N = graphs.CompleteGraph(19).copy(implementation='networkx')
            sage: N.size()
            171
            sage: N.delete_edge( 1, 2 )
            sage: N.delete_edge( (3, 4) )
            sage: N.delete_edges( [ (5, 6), (7, 8) ] )
            sage: N.size()
            167
            sage: N.delete_edge( 9, 10, 'label' )
            sage: N.delete_edge( (11, 12, 'label') )
            sage: N.delete_edges( [ (13, 14, 'label') ] )
            sage: N.size()
            167
            sage: N.has_edge( (11, 12) )
            True

        However, CGraph backends handle things properly::

            sage: G.delete_edge( 9, 10, 'label' )
            sage: G.delete_edge( (11, 12, 'label') )
            sage: G.delete_edges( [ (13, 14, 'label') ] )
            sage: G.size()
            167

        ::

            sage: C = graphs.CompleteGraph(19).to_directed(sparse=True)
            sage: C.size()
            342
            sage: C.delete_edge( 1, 2 )
            sage: C.delete_edge( (3, 4) )
            sage: C.delete_edges( [ (5, 6), (7, 8) ] )

            sage: D = graphs.CompleteGraph(19).to_directed(sparse=True, implementation='networkx')
            sage: D.size()
            342
            sage: D.delete_edge( 1, 2 )
            sage: D.delete_edge( (3, 4) )
            sage: D.delete_edges( [ (5, 6), (7, 8) ] )
            sage: D.delete_edge( 9, 10, 'label' )
            sage: D.delete_edge( (11, 12, 'label') )
            sage: D.delete_edges( [ (13, 14, 'label') ] )
            sage: D.size()
            338
            sage: D.has_edge( (11, 12) )
            True

        ::

            sage: C.delete_edge( 9, 10, 'label' )
            sage: C.delete_edge( (11, 12, 'label') )
            sage: C.delete_edges( [ (13, 14, 'label') ] )
            sage: C.size() # correct!
            338
            sage: C.has_edge( (11, 12) ) # correct!
            True

        """
        if label is None:
            if v is None:
                try:
                    u, v, label = u
                except:
                    u, v = u
                    label = None
        self._backend.del_edge(u, v, label, self._directed)

    def delete_edges(self, edges):
        """
        Delete edges from an iterable container.

        EXAMPLES::

            sage: K12 = graphs.CompleteGraph(12)
            sage: K4 = graphs.CompleteGraph(4)
            sage: K12.size()
            66
            sage: K12.delete_edges(K4.edge_iterator())
            sage: K12.size()
            60

        ::

            sage: K12 = graphs.CompleteGraph(12).to_directed()
            sage: K4 = graphs.CompleteGraph(4).to_directed()
            sage: K12.size()
            132
            sage: K12.delete_edges(K4.edge_iterator())
            sage: K12.size()
            120
        """
        for e in edges:
            self.delete_edge(e)

    def delete_multiedge(self, u, v):
        """
        Deletes all edges from u and v.

        EXAMPLES::

            sage: G = Graph(multiedges=True,sparse=True)
            sage: G.add_edges([(0,1), (0,1), (0,1), (1,2), (2,3)])
            sage: G.edges()
            [(0, 1, None), (0, 1, None), (0, 1, None), (1, 2, None), (2, 3, None)]
            sage: G.delete_multiedge( 0, 1 )
            sage: G.edges()
            [(1, 2, None), (2, 3, None)]

        ::

            sage: D = DiGraph(multiedges=True,sparse=True)
            sage: D.add_edges([(0,1,1), (0,1,2), (0,1,3), (1,0), (1,2), (2,3)])
            sage: D.edges()
            [(0, 1, 1), (0, 1, 2), (0, 1, 3), (1, 0, None), (1, 2, None), (2, 3, None)]
            sage: D.delete_multiedge( 0, 1 )
            sage: D.edges()
            [(1, 0, None), (1, 2, None), (2, 3, None)]
        """
        if self.allows_multiple_edges():
            for l in self.edge_label(u, v):
                self.delete_edge(u, v, l)
        else:
            self.delete_edge(u, v)

    def set_edge_label(self, u, v, l):
        """
        Set the edge label of a given edge.

        .. note::

           There can be only one edge from u to v for this to make
           sense. Otherwise, an error is raised.

        INPUT:


        -  ``u, v`` - the vertices (and direction if digraph)
           of the edge

        -  ``l`` - the new label


        EXAMPLES::

            sage: SD = DiGraph( { 1:[18,2], 2:[5,3], 3:[4,6], 4:[7,2], 5:[4], 6:[13,12], 7:[18,8,10], 8:[6,9,10], 9:[6], 10:[11,13], 11:[12], 12:[13], 13:[17,14], 14:[16,15], 15:[2], 16:[13], 17:[15,13], 18:[13] }, sparse=True)
            sage: SD.set_edge_label(1, 18, 'discrete')
            sage: SD.set_edge_label(4, 7, 'discrete')
            sage: SD.set_edge_label(2, 5, 'h = 0')
            sage: SD.set_edge_label(7, 18, 'h = 0')
            sage: SD.set_edge_label(7, 10, 'aut')
            sage: SD.set_edge_label(8, 10, 'aut')
            sage: SD.set_edge_label(8, 9, 'label')
            sage: SD.set_edge_label(8, 6, 'no label')
            sage: SD.set_edge_label(13, 17, 'k > h')
            sage: SD.set_edge_label(13, 14, 'k = h')
            sage: SD.set_edge_label(17, 15, 'v_k finite')
            sage: SD.set_edge_label(14, 15, 'v_k m.c.r.')
            sage: posn = {1:[ 3,-3],  2:[0,2],  3:[0, 13],  4:[3,9],  5:[3,3],  6:[16, 13], 7:[6,1],  8:[6,6],  9:[6,11], 10:[9,1], 11:[10,6], 12:[13,6], 13:[16,2], 14:[10,-6], 15:[0,-10], 16:[14,-6], 17:[16,-10], 18:[6,-4]}
            sage: SD.plot(pos=posn, vertex_size=400, vertex_colors={'#FFFFFF':range(1,19)}, edge_labels=True).show() # long time

        ::

            sage: G = graphs.HeawoodGraph()
            sage: for u,v,l in G.edges():
            ...    G.set_edge_label(u,v,'(' + str(u) + ',' + str(v) + ')')
            sage: G.edges()
                [(0, 1, '(0,1)'),
                 (0, 5, '(0,5)'),
                 (0, 13, '(0,13)'),
                 ...
                 (11, 12, '(11,12)'),
                 (12, 13, '(12,13)')]

        ::

            sage: g = Graph({0: [0,1,1,2]}, loops=True, multiedges=True, sparse=True)
            sage: g.set_edge_label(0,0,'test')
            sage: g.edges()
            [(0, 0, 'test'), (0, 1, None), (0, 1, None), (0, 2, None)]
            sage: g.add_edge(0,0,'test2')
            sage: g.set_edge_label(0,0,'test3')
            Traceback (most recent call last):
            ...
            RuntimeError: Cannot set edge label, since there are multiple edges from 0 to 0.

        ::

            sage: dg = DiGraph({0 : [1], 1 : [0]}, sparse=True)
            sage: dg.set_edge_label(0,1,5)
            sage: dg.set_edge_label(1,0,9)
            sage: dg.outgoing_edges(1)
            [(1, 0, 9)]
            sage: dg.incoming_edges(1)
            [(0, 1, 5)]
            sage: dg.outgoing_edges(0)
            [(0, 1, 5)]
            sage: dg.incoming_edges(0)
            [(1, 0, 9)]

        ::

            sage: G = Graph({0:{1:1}}, sparse=True)
            sage: G.num_edges()
            1
            sage: G.set_edge_label(0,1,1)
            sage: G.num_edges()
            1
        """
        if self.allows_multiple_edges():
            if len(self.edge_label(u, v)) > 1:
                raise RuntimeError("Cannot set edge label, since there are multiple edges from %s to %s."%(u,v))
        self._backend.set_edge_label(u, v, l, self._directed)

    def has_edge(self, u, v=None, label=None):
        r"""
        Returns True if (u, v) is an edge, False otherwise.

        INPUT: The following forms are accepted by NetworkX:

        - G.has_edge( 1, 2 )
        - G.has_edge( (1, 2) )
        - G.has_edge( 1, 2, 'label' )

        EXAMPLES::

            sage: graphs.EmptyGraph().has_edge(9,2)
            False
            sage: DiGraph().has_edge(9,2)
            False
            sage: G = Graph(sparse=True)
            sage: G.add_edge(0,1,"label")
            sage: G.has_edge(0,1,"different label")
            False
            sage: G.has_edge(0,1,"label")
            True
        """
        if label is None:
            if v is None:
                try:
                    u, v, label = u
                except:
                    u, v = u
                    label = None
        return self._backend.has_edge(u, v, label)

    def edges(self, labels=True, sort=True):
        """
        Return a list of edges. Each edge is a triple (u,v,l) where u and v
        are vertices and l is a label.

        INPUT:


        -  ``labels`` - (bool; default: True) if False, each
           edge is a tuple (u,v) of vertices.

        -  ``sort`` - (bool; default: True) if True, ensure
           that the list of edges is sorted.


        OUTPUT: A list of tuples. It is safe to change the returned list.

        EXAMPLES::

            sage: graphs.DodecahedralGraph().edges()
            [(0, 1, {}), (0, 10, {}), (0, 19, {}), (1, 2, {}), (1, 8, {}), (2, 3, {}), (2, 6, {}), (3, 4, {}), (3, 19, {}), (4, 5, {}), (4, 17, {}), (5, 6, {}), (5, 15, {}), (6, 7, {}), (7, 8, {}), (7, 14, {}), (8, 9, {}), (9, 10, {}), (9, 13, {}), (10, 11, {}), (11, 12, {}), (11, 18, {}), (12, 13, {}), (12, 16, {}), (13, 14, {}), (14, 15, {}), (15, 16, {}), (16, 17, {}), (17, 18, {}), (18, 19, {})]

        ::

            sage: graphs.DodecahedralGraph().edges(labels=False)
            [(0, 1), (0, 10), (0, 19), (1, 2), (1, 8), (2, 3), (2, 6), (3, 4), (3, 19), (4, 5), (4, 17), (5, 6), (5, 15), (6, 7), (7, 8), (7, 14), (8, 9), (9, 10), (9, 13), (10, 11), (11, 12), (11, 18), (12, 13), (12, 16), (13, 14), (14, 15), (15, 16), (16, 17), (17, 18), (18, 19)]

        ::

            sage: D = graphs.DodecahedralGraph().to_directed()
            sage: D.edges()
            [(0, 1, {}), (0, 10, {}), (0, 19, {}), (1, 0, {}), (1, 2, {}), (1, 8, {}), (2, 1, {}), (2, 3, {}), (2, 6, {}), (3, 2, {}), (3, 4, {}), (3, 19, {}), (4, 3, {}), (4, 5, {}), (4, 17, {}), (5, 4, {}), (5, 6, {}), (5, 15, {}), (6, 2, {}), (6, 5, {}), (6, 7, {}), (7, 6, {}), (7, 8, {}), (7, 14, {}), (8, 1, {}), (8, 7, {}), (8, 9, {}), (9, 8, {}), (9, 10, {}), (9, 13, {}), (10, 0, {}), (10, 9, {}), (10, 11, {}), (11, 10, {}), (11, 12, {}), (11, 18, {}), (12, 11, {}), (12, 13, {}), (12, 16, {}), (13, 9, {}), (13, 12, {}), (13, 14, {}), (14, 7, {}), (14, 13, {}), (14, 15, {}), (15, 5, {}), (15, 14, {}), (15, 16, {}), (16, 12, {}), (16, 15, {}), (16, 17, {}), (17, 4, {}), (17, 16, {}), (17, 18, {}), (18, 11, {}), (18, 17, {}), (18, 19, {}), (19, 0, {}), (19, 3, {}), (19, 18, {})]
            sage: D.edges(labels = False)
            [(0, 1), (0, 10), (0, 19), (1, 0), (1, 2), (1, 8), (2, 1), (2, 3), (2, 6), (3, 2), (3, 4), (3, 19), (4, 3), (4, 5), (4, 17), (5, 4), (5, 6), (5, 15), (6, 2), (6, 5), (6, 7), (7, 6), (7, 8), (7, 14), (8, 1), (8, 7), (8, 9), (9, 8), (9, 10), (9, 13), (10, 0), (10, 9), (10, 11), (11, 10), (11, 12), (11, 18), (12, 11), (12, 13), (12, 16), (13, 9), (13, 12), (13, 14), (14, 7), (14, 13), (14, 15), (15, 5), (15, 14), (15, 16), (16, 12), (16, 15), (16, 17), (17, 4), (17, 16), (17, 18), (18, 11), (18, 17), (18, 19), (19, 0), (19, 3), (19, 18)]
        """
        L = list(self.edge_iterator(labels=labels))
        if sort:
            L.sort()
        return L

    def edge_boundary(self, vertices1, vertices2=None, labels=True):
        """
        Returns a list of edges `(u,v,l)` with `u` in ``vertices1``
        and `v` in ``vertices2``. If ``vertices2`` is ``None``, then
        it is set to the complement of ``vertices1``.

        In a digraph, the external boundary of a vertex `v` are those
        vertices `u` with an arc `(v, u)`.

        INPUT:


        -  ``labels`` - if ``False``, each edge is a tuple `(u,v)` of
           vertices.


        EXAMPLES::

            sage: K = graphs.CompleteBipartiteGraph(9,3)
            sage: len(K.edge_boundary( [0,1,2,3,4,5,6,7,8], [9,10,11] ))
            27
            sage: K.size()
            27

        Note that the edge boundary preserves direction::

            sage: K = graphs.CompleteBipartiteGraph(9,3).to_directed()
            sage: len(K.edge_boundary( [0,1,2,3,4,5,6,7,8], [9,10,11] ))
            27
            sage: K.size()
            54

        ::

            sage: D = DiGraph({0:[1,2], 3:[0]})
            sage: D.edge_boundary([0])
            [(0, 1, None), (0, 2, None)]
            sage: D.edge_boundary([0], labels=False)
            [(0, 1), (0, 2)]

        TESTS::

            sage: G = graphs.DiamondGraph()
            sage: G.edge_boundary([0,1])
            [(0, 2, {}), (1, 2, {}), (1, 3, {})]
            sage: G = graphs.PetersenGraph()
            sage: G.edge_boundary([0], [0])
            []

        """
        vertices1 = [v for v in vertices1 if v in self]
        output = []
        if self._directed:
            output.extend(self.outgoing_edge_iterator(vertices1,labels=labels))
            if vertices2 is not None:
                output = [e for e in output if e[1] in vertices2]
            else:
                output = [e for e in output if e[1] not in vertices1]
            return output
        else:
            output.extend(self.edge_iterator(vertices1,labels=labels))
            output2 = []
            if vertices2 is not None:
                for e in output:
                    if e[0] in vertices1:
                        if e[1] in vertices2:
                            output2.append(e)
                    elif e[0] in vertices2: # e[1] in vertices1
                        output2.append(e)
            else:
                for e in output:
                    if e[0] in vertices1:
                        if e[1] not in vertices1:
                            output2.append(e)
                    elif e[0] not in vertices1: # e[1] in vertices1
                        output2.append(e)
            return output2

    def edge_iterator(self, vertices=None, labels=True, ignore_direction=False):
        """
        Returns an iterator over the edges incident with any vertex given.
        If the graph is directed, iterates over edges going out only. If
        vertices is None, then returns an iterator over all edges. If self
        is directed, returns outgoing edges only.

        INPUT:


        -  ``labels`` - if False, each edge is a tuple (u,v) of
           vertices.

        -  ``ignore_direction`` - (default False) only applies
           to directed graphs. If True, searches across edges in either
           direction.


        EXAMPLES::

            sage: for i in graphs.PetersenGraph().edge_iterator([0]):
            ...    print i
            (0, 1, None)
            (0, 4, None)
            (0, 5, None)
            sage: D = DiGraph( { 0 : [1,2], 1: [0] } )
            sage: for i in D.edge_iterator([0]):
            ...    print i
            (0, 1, None)
            (0, 2, None)

        ::

            sage: G = graphs.TetrahedralGraph()
            sage: list(G.edge_iterator(labels=False))
            [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]

        ::

            sage: D = DiGraph({1:[0], 2:[0]})
            sage: list(D.edge_iterator(0))
            []
            sage: list(D.edge_iterator(0, ignore_direction=True))
            [(1, 0, None), (2, 0, None)]
        """
        if vertices is None:
            vertices = self
        elif vertices in self:
            vertices = [vertices]
        else:
            vertices = [v for v in vertices if v in self]
        if ignore_direction and self._directed:
            for e in self._backend.iterator_out_edges(vertices, labels):
                yield e
            for e in self._backend.iterator_in_edges(vertices, labels):
                yield e
        elif self._directed:
            for e in self._backend.iterator_out_edges(vertices, labels):
                yield e
        else:
            for e in self._backend.iterator_edges(vertices, labels):
                yield e

    def edges_incident(self, vertices=None, labels=True):
        """
        Returns a list of edges incident with any vertex given. If vertices
        is None, returns a list of all edges in graph. For digraphs, only
        lists outward edges.

        INPUT:


        -  ``label`` - if False, each edge is a tuple (u,v) of
           vertices.


        EXAMPLES::

            sage: graphs.PetersenGraph().edges_incident([0,9], labels=False)
            [(0, 1), (0, 4), (0, 5), (4, 9), (6, 9), (7, 9)]
            sage: D = DiGraph({0:[1]})
            sage: D.edges_incident([0])
            [(0, 1, None)]
            sage: D.edges_incident([1])
            []
        """
        if vertices in self:
            vertices = [vertices]
        v = list(self.edge_boundary(vertices, labels=labels))
        v.sort()
        return v

    def edge_label(self, u, v=None):
        """
        Returns the label of an edge. Note that if the graph allows
        multiple edges, then a list of labels on the edge is returned.

        EXAMPLES::

            sage: G = Graph({0 : {1 : 'edgelabel'}}, sparse=True)
            sage: G.edges(labels=False)
            [(0, 1)]
            sage: G.edge_label( 0, 1 )
            'edgelabel'
            sage: D = DiGraph({0 : {1 : 'edgelabel'}}, sparse=True)
            sage: D.edges(labels=False)
            [(0, 1)]
            sage: D.edge_label( 0, 1 )
            'edgelabel'

        ::

            sage: G = Graph(multiedges=True, sparse=True)
            sage: [G.add_edge(0,1,i) for i in range(1,6)]
            [None, None, None, None, None]
            sage: sorted(G.edge_label(0,1))
            [1, 2, 3, 4, 5]
        """
        return self._backend.get_edge_label(u,v)

    def edge_labels(self):
        """
        Returns a list of edge labels.

        EXAMPLES::

            sage: G = Graph({0:{1:'x',2:'z',3:'a'}, 2:{5:'out'}}, sparse=True)
            sage: G.edge_labels()
            ['x', 'z', 'a', 'out']
            sage: G = DiGraph({0:{1:'x',2:'z',3:'a'}, 2:{5:'out'}}, sparse=True)
            sage: G.edge_labels()
            ['x', 'z', 'a', 'out']
        """
        labels = []
        for u,v,l in self.edges():
            labels.append(l)
        return labels

    def remove_multiple_edges(self):
        """
        Removes all multiple edges, retaining one edge for each.

        EXAMPLES::

            sage: G = Graph(multiedges=True, sparse=True)
            sage: G.add_edges( [ (0,1), (0,1), (0,1), (0,1), (1,2) ] )
            sage: G.edges(labels=False)
            [(0, 1), (0, 1), (0, 1), (0, 1), (1, 2)]

        ::

            sage: G.remove_multiple_edges()
            sage: G.edges(labels=False)
            [(0, 1), (1, 2)]

        ::

            sage: D = DiGraph(multiedges=True, sparse=True)
            sage: D.add_edges( [ (0,1,1), (0,1,2), (0,1,3), (0,1,4), (1,2) ] )
            sage: D.edges(labels=False)
            [(0, 1), (0, 1), (0, 1), (0, 1), (1, 2)]
            sage: D.remove_multiple_edges()
            sage: D.edges(labels=False)
            [(0, 1), (1, 2)]
        """
        if self.allows_multiple_edges():
            if self._directed:
                for v in self:
                    for u in self.neighbor_in_iterator(v):
                        edges = self.edge_boundary([u], [v])
                        if len(edges) > 1:
                            self.delete_edges(edges[1:])
            else:
                for v in self:
                    for u in self.neighbor_iterator(v):
                        edges = self.edge_boundary([v], [u])
                        if len(edges) > 1:
                            self.delete_edges(edges[1:])

    def remove_loops(self, vertices=None):
        """
        Removes loops on vertices in vertices. If vertices is None, removes
        all loops.

        EXAMPLE

        ::

            sage: G = Graph(4, loops=True)
            sage: G.add_edges( [ (0,0), (1,1), (2,2), (3,3), (2,3) ] )
            sage: G.edges(labels=False)
            [(0, 0), (1, 1), (2, 2), (2, 3), (3, 3)]
            sage: G.remove_loops()
            sage: G.edges(labels=False)
            [(2, 3)]
            sage: G.allows_loops()
            True
            sage: G.has_loops()
            False

            sage: D = DiGraph(4, loops=True)
            sage: D.add_edges( [ (0,0), (1,1), (2,2), (3,3), (2,3) ] )
            sage: D.edges(labels=False)
            [(0, 0), (1, 1), (2, 2), (2, 3), (3, 3)]
            sage: D.remove_loops()
            sage: D.edges(labels=False)
            [(2, 3)]
            sage: D.allows_loops()
            True
            sage: D.has_loops()
            False
        """
        if vertices is None:
            vertices = self
        for v in vertices:
            if self.has_edge(v,v):
                self.delete_multiedge(v,v)

    def loop_edges(self):
        """
        Returns a list of all loops in the graph.

        EXAMPLES::

            sage: G = Graph(4, loops=True)
            sage: G.add_edges( [ (0,0), (1,1), (2,2), (3,3), (2,3) ] )
            sage: G.loop_edges()
            [(0, 0, None), (1, 1, None), (2, 2, None), (3, 3, None)]

        ::

            sage: D = DiGraph(4, loops=True)
            sage: D.add_edges( [ (0,0), (1,1), (2,2), (3,3), (2,3) ] )
            sage: D.loop_edges()
            [(0, 0, None), (1, 1, None), (2, 2, None), (3, 3, None)]

        ::

            sage: G = Graph(4, loops=True, multiedges=True, sparse=True)
            sage: G.add_edges([(i,i) for i in range(4)])
            sage: G.loop_edges()
            [(0, 0, None), (1, 1, None), (2, 2, None), (3, 3, None)]
        """
        if self.allows_multiple_edges():
            return [(v,v,l) for v in self.loop_vertices() for l in self.edge_label(v,v)]
        else:
            return [(v,v,self.edge_label(v,v)) for v in self.loop_vertices()]

    def number_of_loops(self):
        """
        Returns the number of edges that are loops.

        EXAMPLES::

            sage: G = Graph(4, loops=True)
            sage: G.add_edges( [ (0,0), (1,1), (2,2), (3,3), (2,3) ] )
            sage: G.edges(labels=False)
            [(0, 0), (1, 1), (2, 2), (2, 3), (3, 3)]
            sage: G.number_of_loops()
            4

        ::

            sage: D = DiGraph(4, loops=True)
            sage: D.add_edges( [ (0,0), (1,1), (2,2), (3,3), (2,3) ] )
            sage: D.edges(labels=False)
            [(0, 0), (1, 1), (2, 2), (2, 3), (3, 3)]
            sage: D.number_of_loops()
            4
        """
        return len(self.loop_edges())

    ### Modifications

    def clear(self):
        """
        Empties the graph of vertices and edges and removes name, boundary,
        associated objects, and position information.

        EXAMPLES::

            sage: G=graphs.CycleGraph(4); G.set_vertices({0:'vertex0'})
            sage: G.order(); G.size()
            4
            4
            sage: len(G._pos)
            4
            sage: G.name()
            'Cycle graph'
            sage: G.get_vertex(0)
            'vertex0'
            sage: H = G.copy(implementation='c_graph', sparse=True)
            sage: H.clear()
            sage: H.order(); H.size()
            0
            0
            sage: len(H._pos)
            0
            sage: H.name()
            ''
            sage: H.get_vertex(0)
            sage: H = G.copy(implementation='c_graph', sparse=False)
            sage: H.clear()
            sage: H.order(); H.size()
            0
            0
            sage: len(H._pos)
            0
            sage: H.name()
            ''
            sage: H.get_vertex(0)
            sage: H = G.copy(implementation='networkx')
            sage: H.clear()
            sage: H.order(); H.size()
            0
            0
            sage: len(H._pos)
            0
            sage: H.name()
            ''
            sage: H.get_vertex(0)
        """
        self.name('')
        self.delete_vertices(self.vertices())

    ### Degree functions

    def degree(self, vertices=None, labels=False):
        """
        Gives the degree (in + out for digraphs) of a vertex or of
        vertices.

        INPUT:


        -  ``vertices`` - If vertices is a single vertex,
           returns the number of neighbors of vertex. If vertices is an
           iterable container of vertices, returns a list of degrees. If
           vertices is None, same as listing all vertices.

        -  ``labels`` - see OUTPUT


        OUTPUT: Single vertex- an integer. Multiple vertices- a list of
        integers. If labels is True, then returns a dictionary mapping each
        vertex to its degree.

        EXAMPLES::

            sage: P = graphs.PetersenGraph()
            sage: P.degree(5)
            3

        ::

            sage: K = graphs.CompleteGraph(9)
            sage: K.degree()
            [8, 8, 8, 8, 8, 8, 8, 8, 8]

        ::

            sage: D = DiGraph( { 0: [1,2,3], 1: [0,2], 2: [3], 3: [4], 4: [0,5], 5: [1] } )
            sage: D.degree(vertices = [0,1,2], labels=True)
            {0: 5, 1: 4, 2: 3}
            sage: D.degree()
            [5, 4, 3, 3, 3, 2]
        """
        if labels:
            return dict(self.degree_iterator(vertices,labels))
        elif vertices in self and not labels:
            return self.degree_iterator(vertices,labels).next()
        else:
            return list(self.degree_iterator(vertices,labels))

    def average_degree(self):
        r"""
        Returns the average degree of the graph.

        The average degree of a graph `G=(V,E)` is equal to
        ``\frac {2|E|}{|V|}``.

        EXAMPLES:

        The average degree of a regular graph is equal to the
        degree of any vertex::

            sage: g = graphs.CompleteGraph(5)
            sage: g.average_degree() == 4
            True

        The average degree of a tree is always strictly less than
        `2`::

           sage: g = graphs.RandomGNP(20,.5)
           sage: tree = Graph()
           sage: tree.add_edges(g.min_spanning_tree())
           sage: tree.average_degree() < 2
           True

        For any graph, it is equal to ``\frac {2|E|}{|V|}``::

            sage: g = graphs.RandomGNP(50,.8)
            sage: g.average_degree() == 2*g.size()/g.order()
            True
        """

        return 2*Integer(self.size())/Integer(self.order())

    def maximum_average_degree(self, value_only=True):
        r"""
        Returns the Maximum Average Degree (MAD) of the current graph.

        The Maximum Average Degree (MAD) of a graph is defined as
        the average degree of its densest subgraph. More formally,
        ``Mad(G) = \max_{H\subseteq G} Ad(H)``, where `Ad(G)` denotes
        the average degree of `G`.

        This can be computed in polynomial time.

        INPUT:

        - ``value_only`` (boolean) -- ``True`` by default

            - If ``value_only=True``, only the numerical
              value of the `MAD` is returned.

            - Else, the subgraph of `G` realizing the `MAD`
              is returned.

        EXAMPLES:

        In any graph, the `Mad` is always larger than the average
        degree::

            sage: g = graphs.RandomGNP(20,.3)
            sage: mad_g = g.maximum_average_degree()
            sage: g.average_degree() <= mad_g
            True

        Unlike the average degree, the `Mad` of the disjoint
        union of two graphs is the maximum of the `Mad` of each
        graphs::

            sage: h = graphs.RandomGNP(20,.3)
            sage: mad_h = h.maximum_average_degree()
            sage: (g+h).maximum_average_degree() == max(mad_g, mad_h)
            True

        The subgraph of a regular graph realizing the maximum
        average degree is always the whole graph ::

            sage: g = graphs.CompleteGraph(5)
            sage: mad_g = g.maximum_average_degree(value_only=False)
            sage: g.is_isomorphic(mad_g)
            True

        This also works for complete bipartite graphs ::

            sage: g = graphs.CompleteBipartiteGraph(3,4)
            sage: mad_g = g.maximum_average_degree(value_only=False)
            sage: g.is_isomorphic(mad_g)
            True
        """

        g = self
        from sage.numerical.mip import MixedIntegerLinearProgram, Sum

        p = MixedIntegerLinearProgram(maximization=True)

        d = p.new_variable()
        one = p.new_variable()

        # Reorders u and v so that uv and vu are not considered
        # to be different edges
        reorder = lambda u,v : (min(u,v),max(u,v))

        for u,v in g.edge_iterator(labels=False):
            p.add_constraint( one[ reorder(u,v) ] - 2*d[u] , max = 0 )
            p.add_constraint( one[ reorder(u,v) ] - 2*d[v] , max = 0 )

        p.add_constraint( Sum([d[v] for v in g]), max = 1)

        p.set_objective( Sum([ one[reorder(u,v)] for u,v in g.edge_iterator(labels=False)]) )

        obj = p.solve()

        # Paying attention to numerical error :
        # The zero values could be something like 0.000000000001
        # so I can not write l > 0
        # And the non-zero, though they should be equal to
        # 1/(order of the optimal subgraph) may be a bit lower

        # setting the minimum to 1/(10 * size of the whole graph )
        # should be safe :-)
        m = 1/(10*g.order())
        g_mad = g.subgraph([v for v,l in p.get_values(d).iteritems() if l>m ])

        if value_only:
            return g_mad.average_degree()
        else:
            return g_mad

    def degree_histogram(self):
        """
        Returns a list, whose ith entry is the frequency of degree i.

        EXAMPLES::

            sage: G = graphs.Grid2dGraph(9,12)
            sage: G.degree_histogram()
            [0, 0, 4, 34, 70]

        ::

            sage: G = graphs.Grid2dGraph(9,12).to_directed()
            sage: G.degree_histogram()
            [0, 0, 0, 0, 4, 0, 34, 0, 70]
        """
        degree_sequence = self.degree()
        dmax = max(degree_sequence) + 1
        frequency = [0]*dmax
        for d in degree_sequence:
            frequency[d] += 1
        return frequency

    def degree_iterator(self, vertices=None, labels=False):
        """
        Returns an iterator over the degrees of the (di)graph. In the case
        of a digraph, the degree is defined as the sum of the in-degree and
        the out-degree, i.e. the total number of edges incident to a given
        vertex.

        INPUT: labels=False: returns an iterator over degrees. labels=True:
        returns an iterator over tuples (vertex, degree).


        -  ``vertices`` - if specified, restrict to this
           subset.


        EXAMPLES::

            sage: G = graphs.Grid2dGraph(3,4)
            sage: for i in G.degree_iterator():
            ...    print i
            3
            4
            2
            ...
            2
            4
            sage: for i in G.degree_iterator(labels=True):
            ...    print i
            ((0, 1), 3)
            ((1, 2), 4)
            ((0, 0), 2)
            ...
            ((0, 3), 2)
            ((1, 1), 4)

        ::

            sage: D = graphs.Grid2dGraph(2,4).to_directed()
            sage: for i in D.degree_iterator():
            ...    print i
            6
            6
            ...
            4
            6
            sage: for i in D.degree_iterator(labels=True):
            ...    print i
            ((0, 1), 6)
            ((1, 2), 6)
            ...
            ((0, 3), 4)
            ((1, 1), 6)
        """
        if vertices is None:
            vertices = self
        elif vertices in self:
            vertices = [vertices]
        else:
            vertices = [v for v in vertices if v in self]
        if labels:
            filter = lambda v, self: (v, self._backend.degree(v, self._directed))
        else:
            filter = lambda v, self: self._backend.degree(v, self._directed)
        for v in vertices:
            yield filter(v, self)

    def degree_sequence(self):
        r"""
        Return the degree sequence of this (di)graph.

        EXAMPLES:

        The degree sequence of an undirected graph::

            sage: g = Graph({1: [2, 5], 2: [1, 5, 3, 4], 3: [2, 5], 4: [3], 5: [2, 3]})
            sage: g.degree_sequence()
            [4, 3, 3, 2, 2]

        The degree sequence of a digraph::

            sage: g = DiGraph({1: [2, 5, 6], 2: [3, 6], 3: [4, 6], 4: [6], 5: [4, 6]})
            sage: g.degree_sequence()
            [5, 3, 3, 3, 3, 3]

        Degree sequences of some common graphs::

            sage: graphs.PetersenGraph().degree_sequence()
            [3, 3, 3, 3, 3, 3, 3, 3, 3, 3]
            sage: graphs.HouseGraph().degree_sequence()
            [3, 3, 2, 2, 2]
            sage: graphs.FlowerSnark().degree_sequence()
            [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3]
        """
        return sorted(self.degree_iterator(), reverse=True)

    def is_regular(self, k = None):
        """
        Return ``True`` if this graph is (`k`-)regular.

        INPUT:

        - ``k`` (default: ``None``) - the degree of regularity to
          check for

        EXAMPLES::

            sage: G = graphs.HoffmanSingletonGraph()
            sage: G.is_regular()
            True
            sage: G.is_regular(9)
            False

        So the Hoffman-Singleton graph is regular, but not
        9-regular.  In fact, we can now find the degree easily as
        follows::

            sage: G.degree_iterator().next()
            7

        The house graph is not regular::

            sage: graphs.HouseGraph().is_regular()
            False
        """
        deg_it = self.degree_iterator()
        if k is None:
            k = deg_it.next()

        for d in deg_it:
            if d != k:
                return False

        return True



    ### Substructures

    def subgraph(self, vertices=None, edges=None, inplace=False,
                       vertex_property=None, edge_property=None, algorithm=None):
        """
        Returns the subgraph containing the given vertices and edges. If
        either vertices or edges are not specified, they are assumed to be
        all vertices or edges. If edges are not specified, returns the
        subgraph induced by the vertices.

        INPUT:


        -  ``inplace`` - Using inplace is True will simply
           delete the extra vertices and edges from the current graph. This
           will modify the graph.

        -  ``vertices`` - Vertices can be a single vertex or an
           iterable container of vertices, e.g. a list, set, graph, file or
           numeric array. If not passed, defaults to the entire graph.

        -  ``edges`` - As with vertices, edges can be a single
           edge or an iterable container of edges (e.g., a list, set, file,
           numeric array, etc.). If not edges are not specified, then all
           edges are assumed and the returned graph is an induced subgraph. In
           the case of multiple edges, specifying an edge as (u,v) means to
           keep all edges (u,v), regardless of the label.

        -  ``vertex_property`` - If specified, this is
           expected to be a function on vertices, which is intersected with
           the vertices specified, if any are.

        -  ``edge_property`` - If specified, this is expected
           to be a function on edges, which is intersected with the edges
           specified, if any are.

        - ``algorithm`` - If ``algorithm=delete`` or ``inplace=True``,
          then the graph is constructed by deleting edges and
          vertices.  If ``add``, then the graph is constructed by
          building a new graph from the appropriate vertices and
          edges.  If not specified, then the algorithm is chosen based
          on the number of vertices in the subgraph.


        EXAMPLES::

            sage: G = graphs.CompleteGraph(9)
            sage: H = G.subgraph([0,1,2]); H
            Subgraph of (Complete graph): Graph on 3 vertices
            sage: G
            Complete graph: Graph on 9 vertices
            sage: J = G.subgraph(edges=[(0,1)])
            sage: J.edges(labels=False)
            [(0, 1)]
            sage: J.vertices()==G.vertices()
            True
            sage: G.subgraph([0,1,2], inplace=True); G
            Subgraph of (Complete graph): Graph on 3 vertices
            sage: G.subgraph()==G
            True

        ::

            sage: D = graphs.CompleteGraph(9).to_directed()
            sage: H = D.subgraph([0,1,2]); H
            Subgraph of (Complete graph): Digraph on 3 vertices
            sage: H = D.subgraph(edges=[(0,1), (0,2)])
            sage: H.edges(labels=False)
            [(0, 1), (0, 2)]
            sage: H.vertices()==D.vertices()
            True
            sage: D
            Complete graph: Digraph on 9 vertices
            sage: D.subgraph([0,1,2], inplace=True); D
            Subgraph of (Complete graph): Digraph on 3 vertices
            sage: D.subgraph()==D
            True

        A more complicated example involving multiple edges and labels.

        ::

            sage: G = Graph(multiedges=True, sparse=True)
            sage: G.add_edges([(0,1,'a'), (0,1,'b'), (1,0,'c'), (0,2,'d'), (0,2,'e'), (2,0,'f'), (1,2,'g')])
            sage: G.subgraph(edges=[(0,1), (0,2,'d'), (0,2,'not in graph')]).edges()
            [(0, 1, 'a'), (0, 1, 'b'), (0, 1, 'c'), (0, 2, 'd')]
            sage: J = G.subgraph(vertices=[0,1], edges=[(0,1,'a'), (0,2,'c')])
            sage: J.edges()
            [(0, 1, 'a')]
            sage: J.vertices()
            [0, 1]
            sage: G.subgraph(vertices=G.vertices())==G
            True

        ::

            sage: D = DiGraph(multiedges=True, sparse=True)
            sage: D.add_edges([(0,1,'a'), (0,1,'b'), (1,0,'c'), (0,2,'d'), (0,2,'e'), (2,0,'f'), (1,2,'g')])
            sage: D.subgraph(edges=[(0,1), (0,2,'d'), (0,2,'not in graph')]).edges()
            [(0, 1, 'a'), (0, 1, 'b'), (0, 2, 'd')]
            sage: H = D.subgraph(vertices=[0,1], edges=[(0,1,'a'), (0,2,'c')])
            sage: H.edges()
            [(0, 1, 'a')]
            sage: H.vertices()
            [0, 1]

        Using the property arguments::

            sage: P = graphs.PetersenGraph()
            sage: S = P.subgraph(vertex_property = lambda v : v%2 == 0)
            sage: S.vertices()
            [0, 2, 4, 6, 8]

        ::

            sage: C = graphs.CubeGraph(2)
            sage: S = C.subgraph(edge_property=(lambda e: e[0][0] == e[1][0]))
            sage: C.edges()
            [('00', '01', None), ('00', '10', None), ('01', '11', None), ('10', '11', None)]
            sage: S.edges()
            [('00', '01', None), ('10', '11', None)]


        The algorithm is not specified, then a reasonable choice is made for speed.

        ::

            sage: g=graphs.PathGraph(1000)
            sage: g.subgraph(range(10)) # uses the 'add' algorithm
            Subgraph of (Path Graph): Graph on 10 vertices



        TESTS: The appropriate properties are preserved.

        ::

            sage: g = graphs.PathGraph(10)
            sage: g.is_planar(set_embedding=True)
            True
            sage: g.set_vertices(dict((v, 'v%d'%v) for v in g.vertices()))
            sage: h = g.subgraph([3..5])
            sage: h.get_pos().keys()
            [3, 4, 5]
            sage: h.get_vertices()
            {3: 'v3', 4: 'v4', 5: 'v5'}
        """
        if vertices is None:
            vertices=self.vertices()
        elif vertices in self:
            vertices=[vertices]
        else:
            vertices=list(vertices)

        if vertex_property is not None:
            vertices = [v for v in vertices if vertex_property(v)]

        if algorithm is not None and algorithm not in ("delete", "add"):
            raise ValueError('algorithm should be None, "delete", or "add"')

        if inplace or len(vertices)>0.05*self.order() or algorithm=="delete":
            return self._subgraph_by_deleting(vertices=vertices, edges=edges,
                                              inplace=inplace,
                                              edge_property=edge_property)
        else:
            return self._subgraph_by_adding(vertices=vertices, edges=edges,
                                            edge_property=edge_property)

    def _subgraph_by_adding(self, vertices=None, edges=None, edge_property=None):
        """
        Returns the subgraph containing the given vertices and edges.
        The edges also satisfy the edge_property, if it is not None.
        The subgraph is created by creating a new empty graph and
        adding the necessary vertices, edges, and other properties.

        INPUT:

        -  ``vertices`` - Vertices is a list of vertices

        - ``edges`` - Edges can be a single edge or an iterable
           container of edges (e.g., a list, set, file, numeric array,
           etc.). If not edges are not specified, then all edges are
           assumed and the returned graph is an induced subgraph. In
           the case of multiple edges, specifying an edge as (u,v)
           means to keep all edges (u,v), regardless of the label.

        -  ``edge_property`` - If specified, this is expected
           to be a function on edges, which is intersected with the edges
           specified, if any are.


        EXAMPLES::

            sage: G = graphs.CompleteGraph(9)
            sage: H = G._subgraph_by_adding([0,1,2]); H
            Subgraph of (Complete graph): Graph on 3 vertices
            sage: G
            Complete graph: Graph on 9 vertices
            sage: J = G._subgraph_by_adding(vertices=G.vertices(), edges=[(0,1)])
            sage: J.edges(labels=False)
            [(0, 1)]
            sage: J.vertices()==G.vertices()
            True
            sage: G._subgraph_by_adding(vertices=G.vertices())==G
            True

        ::

            sage: D = graphs.CompleteGraph(9).to_directed()
            sage: H = D._subgraph_by_adding([0,1,2]); H
            Subgraph of (Complete graph): Digraph on 3 vertices
            sage: H = D._subgraph_by_adding(vertices=D.vertices(), edges=[(0,1), (0,2)])
            sage: H.edges(labels=False)
            [(0, 1), (0, 2)]
            sage: H.vertices()==D.vertices()
            True
            sage: D
            Complete graph: Digraph on 9 vertices
            sage: D._subgraph_by_adding(D.vertices())==D
            True

        A more complicated example involving multiple edges and labels.

        ::

            sage: G = Graph(multiedges=True, sparse=True)
            sage: G.add_edges([(0,1,'a'), (0,1,'b'), (1,0,'c'), (0,2,'d'), (0,2,'e'), (2,0,'f'), (1,2,'g')])
            sage: G._subgraph_by_adding(G.vertices(), edges=[(0,1), (0,2,'d'), (0,2,'not in graph')]).edges()
            [(0, 1, 'a'), (0, 1, 'b'), (0, 1, 'c'), (0, 2, 'd')]
            sage: J = G._subgraph_by_adding(vertices=[0,1], edges=[(0,1,'a'), (0,2,'c')])
            sage: J.edges()
            [(0, 1, 'a')]
            sage: J.vertices()
            [0, 1]
            sage: G._subgraph_by_adding(vertices=G.vertices())==G
            True

        ::

            sage: D = DiGraph(multiedges=True, sparse=True)
            sage: D.add_edges([(0,1,'a'), (0,1,'b'), (1,0,'c'), (0,2,'d'), (0,2,'e'), (2,0,'f'), (1,2,'g')])
            sage: D._subgraph_by_adding(vertices=D.vertices(), edges=[(0,1), (0,2,'d'), (0,2,'not in graph')]).edges()
            [(0, 1, 'a'), (0, 1, 'b'), (0, 2, 'd')]
            sage: H = D._subgraph_by_adding(vertices=[0,1], edges=[(0,1,'a'), (0,2,'c')])
            sage: H.edges()
            [(0, 1, 'a')]
            sage: H.vertices()
            [0, 1]

        Using the property arguments::

            sage: C = graphs.CubeGraph(2)
            sage: S = C._subgraph_by_adding(vertices=C.vertices(), edge_property=(lambda e: e[0][0] == e[1][0]))
            sage: C.edges()
            [('00', '01', None), ('00', '10', None), ('01', '11', None), ('10', '11', None)]
            sage: S.edges()
            [('00', '01', None), ('10', '11', None)]

        TESTS: Properties of the graph are preserved.

        ::

            sage: g = graphs.PathGraph(10)
            sage: g.is_planar(set_embedding=True)
            True
            sage: g.set_vertices(dict((v, 'v%d'%v) for v in g.vertices()))
            sage: h = g._subgraph_by_adding([3..5])
            sage: h.get_pos().keys()
            [3, 4, 5]
            sage: h.get_vertices()
            {3: 'v3', 4: 'v4', 5: 'v5'}
        """
        G = self.__class__(weighted=self._weighted, loops=self.allows_loops(),
                           multiedges= self.allows_multiple_edges())
        G.name("Subgraph of (%s)"%self.name())
        G.add_vertices(vertices)
        if edges is not None:
            if G._directed:
                edges_graph = (e for e in self.edge_iterator(vertices) if e[1] in vertices)
                edges_to_keep_labeled = [e for e in edges if len(e)==3]
                edges_to_keep_unlabeled = [e for e in edges if len(e)==2]
            else:
                edges_graph = (sorted(e[0:2])+[e[2]] for e in self.edge_iterator(vertices) if e[0] in vertices and e[1] in vertices)
                edges_to_keep_labeled = [sorted(e[0:2])+[e[2]] for e in edges if len(e)==3]
                edges_to_keep_unlabeled = [sorted(e) for e in edges if len(e)==2]
            edges_to_keep = [tuple(e) for e in edges_graph if e in edges_to_keep_labeled
                             or e[0:2] in edges_to_keep_unlabeled]
        else:
            edges_to_keep=[e for e in self.edge_iterator(vertices) if e[0] in vertices and e[1] in vertices]

        if edge_property is not None:
            edges_to_keep = [e for e in edges_to_keep if edge_property(e)]
        G.add_edges(edges_to_keep)

        attributes_to_update = ('_pos', '_assoc')
        for attr in attributes_to_update:
            if hasattr(self, attr) and getattr(self, attr) is not None:
                value = dict([(v, getattr(self, attr).get(v, None)) for v in G])
                setattr(G, attr,value)

        G._boundary = [v for v in self._boundary if v in G]

        return G

    def _subgraph_by_deleting(self, vertices=None, edges=None, inplace=False,
                              edge_property=None):
        """
        Returns the subgraph containing the given vertices and edges.
        The edges also satisfy the edge_property, if it is not None.
        The subgraph is created by creating deleting things that are
        not needed.

        INPUT:

        -  ``vertices`` - Vertices is a list of vertices

        - ``edges`` - Edges can be a single edge or an iterable
           container of edges (e.g., a list, set, file, numeric array,
           etc.). If not edges are not specified, then all edges are
           assumed and the returned graph is an induced subgraph. In
           the case of multiple edges, specifying an edge as (u,v)
           means to keep all edges (u,v), regardless of the label.

        -  ``edge_property`` - If specified, this is expected
           to be a function on edges, which is intersected with the edges
           specified, if any are.

        -  ``inplace`` - Using inplace is True will simply
           delete the extra vertices and edges from the current graph. This
           will modify the graph.


        EXAMPLES::

            sage: G = graphs.CompleteGraph(9)
            sage: H = G._subgraph_by_deleting([0,1,2]); H
            Subgraph of (Complete graph): Graph on 3 vertices
            sage: G
            Complete graph: Graph on 9 vertices
            sage: J = G._subgraph_by_deleting(vertices=G.vertices(), edges=[(0,1)])
            sage: J.edges(labels=False)
            [(0, 1)]
            sage: J.vertices()==G.vertices()
            True
            sage: G._subgraph_by_deleting([0,1,2], inplace=True); G
            Subgraph of (Complete graph): Graph on 3 vertices
            sage: G._subgraph_by_deleting(vertices=G.vertices())==G
            True

        ::

            sage: D = graphs.CompleteGraph(9).to_directed()
            sage: H = D._subgraph_by_deleting([0,1,2]); H
            Subgraph of (Complete graph): Digraph on 3 vertices
            sage: H = D._subgraph_by_deleting(vertices=D.vertices(), edges=[(0,1), (0,2)])
            sage: H.edges(labels=False)
            [(0, 1), (0, 2)]
            sage: H.vertices()==D.vertices()
            True
            sage: D
            Complete graph: Digraph on 9 vertices
            sage: D._subgraph_by_deleting([0,1,2], inplace=True); D
            Subgraph of (Complete graph): Digraph on 3 vertices
            sage: D._subgraph_by_deleting(D.vertices())==D
            True

        A more complicated example involving multiple edges and labels.

        ::

            sage: G = Graph(multiedges=True, sparse=True)
            sage: G.add_edges([(0,1,'a'), (0,1,'b'), (1,0,'c'), (0,2,'d'), (0,2,'e'), (2,0,'f'), (1,2,'g')])
            sage: G._subgraph_by_deleting(G.vertices(), edges=[(0,1), (0,2,'d'), (0,2,'not in graph')]).edges()
            [(0, 1, 'a'), (0, 1, 'b'), (0, 1, 'c'), (0, 2, 'd')]
            sage: J = G._subgraph_by_deleting(vertices=[0,1], edges=[(0,1,'a'), (0,2,'c')])
            sage: J.edges()
            [(0, 1, 'a')]
            sage: J.vertices()
            [0, 1]
            sage: G._subgraph_by_deleting(vertices=G.vertices())==G
            True

        ::

            sage: D = DiGraph(multiedges=True, sparse=True)
            sage: D.add_edges([(0,1,'a'), (0,1,'b'), (1,0,'c'), (0,2,'d'), (0,2,'e'), (2,0,'f'), (1,2,'g')])
            sage: D._subgraph_by_deleting(vertices=D.vertices(), edges=[(0,1), (0,2,'d'), (0,2,'not in graph')]).edges()
            [(0, 1, 'a'), (0, 1, 'b'), (0, 2, 'd')]
            sage: H = D._subgraph_by_deleting(vertices=[0,1], edges=[(0,1,'a'), (0,2,'c')])
            sage: H.edges()
            [(0, 1, 'a')]
            sage: H.vertices()
            [0, 1]

        Using the property arguments::

            sage: C = graphs.CubeGraph(2)
            sage: S = C._subgraph_by_deleting(vertices=C.vertices(), edge_property=(lambda e: e[0][0] == e[1][0]))
            sage: C.edges()
            [('00', '01', None), ('00', '10', None), ('01', '11', None), ('10', '11', None)]
            sage: S.edges()
            [('00', '01', None), ('10', '11', None)]

        TESTS: Properties of the graph are preserved.

        ::

            sage: g = graphs.PathGraph(10)
            sage: g.is_planar(set_embedding=True)
            True
            sage: g.set_vertices(dict((v, 'v%d'%v) for v in g.vertices()))
            sage: h = g._subgraph_by_deleting([3..5])
            sage: h.get_pos().keys()
            [3, 4, 5]
            sage: h.get_vertices()
            {3: 'v3', 4: 'v4', 5: 'v5'}
        """
        if inplace:
            G = self
        else:
            G = self.copy()
        G.name("Subgraph of (%s)"%self.name())

        G.delete_vertices([v for v in G if v not in vertices])

        edges_to_delete=[]
        if edges is not None:
            if G._directed:
                edges_graph = G.edge_iterator()
                edges_to_keep_labeled = [e for e in edges if len(e)==3]
                edges_to_keep_unlabeled = [e for e in edges if len(e)==2]
            else:
                edges_graph = [sorted(e[0:2])+[e[2]] for e in G.edge_iterator()]
                edges_to_keep_labeled = [sorted(e[0:2])+[e[2]] for e in edges if len(e)==3]
                edges_to_keep_unlabeled = [sorted(e) for e in edges if len(e)==2]
            for e in edges_graph:
                if e not in edges_to_keep_labeled and e[0:2] not in edges_to_keep_unlabeled:
                    edges_to_delete.append(tuple(e))
        if edge_property is not None:
            for e in G.edge_iterator():
                if not edge_property(e):
                    # We might get duplicate edges, but this does
                    # handle the case of multiple edges.
                    edges_to_delete.append(e)

        G.delete_edges(edges_to_delete)
        if not inplace:
            return G

    def subgraph_search(self, G, induced=False):
        r"""
        Returns a copy of ``G`` in ``self``.

        INPUT:

        - ``G`` -- the graph whose copy we are looking for in ``self``.

        - ``induced`` -- boolean (default: ``False``). Whether or not to
          search for an induced copy of ``G`` in ``self``.

        OUTPUT:

        - If ``induced=False``, return a copy of ``G`` in this graph.
          Otherwise, return an induced copy of ``G`` in ``self``. If ``G``
          is the empty graph, return the empty graph since it is a subgraph
          of every graph. Now suppose ``G`` is not the empty graph. If there
          is no copy (induced or otherwise) of ``G`` in ``self``, we return
          ``None``.

        ALGORITHM:

        Brute-force search.

        EXAMPLES:

        The Petersen graph contains the path graph `P_5`::

             sage: g = graphs.PetersenGraph()
             sage: h1 = g.subgraph_search(graphs.PathGraph(5)); h1
             Subgraph of (Petersen graph): Graph on 5 vertices
             sage: h1.vertices()
             [0, 1, 2, 3, 4]
             sage: I1 = g.subgraph_search(graphs.PathGraph(5), induced=True); I1
             Subgraph of (Petersen graph): Graph on 5 vertices
             sage: I1.vertices()
             [0, 1, 2, 3, 8]

        It also contains the claw `K_{1,3}`::

             sage: h2 = g.subgraph_search(graphs.ClawGraph()); h2
             Subgraph of (Petersen graph): Graph on 4 vertices
             sage: h2.vertices()
             [0, 1, 4, 5]
             sage: I2 = g.subgraph_search(graphs.ClawGraph(), induced=True); I2
             Subgraph of (Petersen graph): Graph on 4 vertices
             sage: I2.vertices()
             [0, 1, 4, 5]

        Of course the induced copies are isomorphic to the graphs we were
        looking for::

             sage: I1.is_isomorphic(graphs.PathGraph(5))
             True
             sage: I2.is_isomorphic(graphs.ClawGraph())
             True

        However, the Petersen graph does not contain a subgraph isomorphic to
        `K_3`::

             sage: g.subgraph_search(graphs.CompleteGraph(3)) is None
             True

        Nor does it contain a nonempty induced subgraph isomorphic to `P_6`::

             sage: g.subgraph_search(graphs.PathGraph(6), induced=True) is None
             True

        The empty graph is a subgraph of every graph::

            sage: g.subgraph_search(graphs.EmptyGraph())
            Graph on 0 vertices
            sage: g.subgraph_search(graphs.EmptyGraph(), induced=True)
            Graph on 0 vertices
        """
        from sage.graphs.generic_graph_pyx import subgraph_search
        from sage.graphs.graph_generators import GraphGenerators
        if G.order() == 0:
            return GraphGenerators().EmptyGraph()
        H = subgraph_search(self, G, induced=induced)
        if H == []:
            return None
        return self.subgraph(H)

    def random_subgraph(self, p, inplace=False):
        """
        Return a random subgraph that contains each vertex with prob. p.

        EXAMPLES::

            sage: P = graphs.PetersenGraph()
            sage: P.random_subgraph(.25)
            Subgraph of (Petersen graph): Graph on 4 vertices
        """
        vertices = []
        p = float(p)
        for v in self:
            if random() < p:
                vertices.append(v)
        return self.subgraph(vertices=vertices, inplace=inplace)

    def is_chordal(self):
        r"""
        Tests whether the given graph is chordal.

        A Graph `G` is said to be chordal if it contains no induced
        hole. Being chordal is equivalent to having an elimination
        order on the vertices such that the neighborhood of each
        vertex, before being removed from the graph, is a complete
        graph [Fulkerson65]_.

        Such an ordering is called a Perfect Elimination Order.

        ALGORITHM:

        This algorithm works through computing a Lex BFS on the
        graph, then checking whether the order is a Perfect
        Elimination Order by computing for each vertex `v` the
        subgraph induces by its non-deleted neighbors, then
        testing whether this graph is complete.

        This problem can be solved in `O(m)` [Rose75]_ ( where `m`
        is the number of edges in the graph ) but this
        implementation is not linear because of the complexity of
        Lex BFS. Improving Lex BFS to linear complexity would make
        this algorithm linear.

        The complexity of this algorithm is equal to the
        complexity of the implementation of Lex BFS.

        EXAMPLES:

        The lexicographic product of a Path and a Complete Graph
        is chordal ::

            sage: g = graphs.PathGraph(5).lexicographic_product(graphs.CompleteGraph(3))
            sage: g.is_chordal()
            True

        The same goes with the product of a random lobster
        ( which is a tree ) and a Complete Graph ::

            sage: g = graphs.RandomLobster(10,.5,.5).lexicographic_product(graphs.CompleteGraph(3))
            sage: g.is_chordal()
            True

        The disjoint union of chordal graphs is still chordal::

            sage: (2*g).is_chordal()
            True


        Of course, the Petersen Graph is not chordal as it has girth 5 ::

            sage: g = graphs.PetersenGraph()
            sage: g.girth()
            5
            sage: g.is_chordal()
            False

        REFERENCES:

        .. [Rose75] Rose, D.J. and Tarjan, R.E.,
          Algorithmic aspects of vertex elimination,
          Proceedings of seventh annual ACM symposium on Theory of computing
          Page 254, ACM 1975

        .. [Fulkerson65] Fulkerson, D.R. and Gross, OA
          Incidence matrices and interval graphs
          Pacific J. Math 1965
          Vol. 15, number 3, pages 835--855
        """

        if not self.is_connected():
            for gg in self.connected_components_subgraphs():
                if not gg.is_chordal():
                    return False

            return True


        peo,t_peo = self.lex_BFS(tree=True)

        g = self.copy()

        from sage.combinat.subset import Subsets
        neighbors_subsets = dict([(v,Subsets(self.neighbors(v)+[v])) for v in self.vertex_iterator()])

        while peo:
            v = peo.pop()
            if t_peo.out_degree(v)>0 and g.neighbors(v) not in neighbors_subsets[t_peo.neighbor_out_iterator(v).next()]:
                return False
            g.delete_vertex(v)
        return True

    def is_interval(self, certificate = False):
        r"""
        Check whether self is an interval graph

        INPUT:

        - ``certificate`` (boolean) -- The function returns ``True``
          or ``False`` according to the graph, when ``certificate =
          False`` (default). When ``certificate = True`` and the graph
          is an interval graph, a dictionary whose keys are the
          vertices and values are pairs of integers are returned
          instead of ``True``. They correspond to an embedding of the
          interval graph, each vertex being represented by an interval
          going from the first of the two values to the second.

        ALGORITHM:

        Through the use of PQ-Trees

        AUTHOR :

        Nathann Cohen (implementation)

        EXAMPLES:

        A Petersen Graph is not chordal, nor car it be an interval
        graph ::

            sage: g = graphs.PetersenGraph()
            sage: g.is_interval()
            False

        Though we can build intervals from the corresponding random
        generator::

            sage: g = graphs.RandomInterval(20)
            sage: g.is_interval()
            True

        This method can also return, given an interval graph, a
        possible embedding (we can actually compute all of them
        through the PQ-Tree structures)::

            sage: g = Graph(':S__@_@A_@AB_@AC_@ACD_@ACDE_ACDEF_ACDEFG_ACDEGH_ACDEGHI_ACDEGHIJ_ACDEGIJK_ACDEGIJKL_ACDEGIJKLMaCEGIJKNaCEGIJKNaCGIJKNPaCIP')
            sage: d = g.is_interval(certificate = True)
            sage: print d                                    # not tested
            {0: (0, 20), 1: (1, 9), 2: (2, 36), 3: (3, 5), 4: (4, 38), 5: (6, 21), 6: (7, 27), 7: (8, 12), 8: (10, 29), 9: (11, 16), 10: (13, 39), 11: (14, 31), 12: (15, 32), 13: (17, 23), 14: (18, 22), 15: (19, 33), 16: (24, 25), 17: (26, 35), 18: (28, 30), 19: (34, 37)}

        From this embedding, we can clearly build an interval graph
        isomorphic to the previous one::

            sage: g2 = graphs.IntervalGraph(d.values())
            sage: g2.is_isomorphic(g)
            True

        .. SEEALSO::

        - :mod:`Interval Graph Recognition <sage.graphs.pq_trees>`.

        - :meth:`PQ <sage.graphs.pq_trees.PQ>`
          -- Implementation of PQ-Trees.

        """

        # An interval graph first is a chordal graph. Without this,
        # there is no telling how we should find its maximal cliques,
        # by the way :-)

        if not self.is_chordal():
            return False

        from sage.sets.set import Set
        from sage.combinat.subset import Subsets

        # First, we need to gather the list of maximal cliques, which
        # is easy as the graph is chordal

        cliques = []
        clique_subsets = []

        # As we will be deleting vertices ...
        g = self.copy()

        for cc in self.connected_components_subgraphs():

            # We pick a perfect elimination order for every connected
            # component. We will then iteratively take the last vertex
            # in the order (a simplicial vertex) and consider the
            # clique it forms with its neighbors. If we do not have an
            # inclusion-wise larger clique in our list, we add it !

            peo = cc.lex_BFS()



            while peo:
                v = peo.pop()
                clique = Set( [v] + cc.neighbors(v))
                cc.delete_vertex(v)

                if not any([clique in cs for cs in clique_subsets]):
                    cliques.append(clique)
                    clique_subsets.append(Subsets(clique))


        from sage.graphs.pq_trees import reorder_sets

        try:
            ordered_sets = reorder_sets(cliques)
            if not certificate:
                return True

        except ValueError:
            return False

        # We are now listing the maximal cliques in the given order,
        # and keeping track of the vertices appearing/disappearing

        current = set([])
        beg = {}
        end = {}

        i = 0

        ordered_sets.append([])
        for S in map(set,ordered_sets):
            for v in current-S:
                end[v] = i
                i = i + 1

            for v in S-current:
                beg[v] = i
                i = i + 1

            current = S


        return dict([(v, (beg[v], end[v])) for v in self])


    def is_gallai_tree(self):
        r"""
        Returns whether the current graph is a Gallai tree.

        A graph is a Gallai tree if and only if it is
        connected and its `2`-connected components are all
        isomorphic to complete graphs or odd cycles.

        A connected graph is not degree-choosable if and
        only if it is a Gallai tree [erdos1978choos]_.

        REFERENCES:

        .. [erdos1978choos] Erdos, P. and Rubin, A.L. and Taylor, H.
          Proc. West Coast Conf. on Combinatorics
          Graph Theory and Computing, Congressus Numerantium
          vol 26, pages 125--157, 1979

        EXAMPLES:

        A complete graph is, or course, a Gallai Tree::

            sage: g = graphs.CompleteGraph(15)
            sage: g.is_gallai_tree()
            True

        The Petersen Graph is not::

            sage: g = graphs.PetersenGraph()
            sage: g.is_gallai_tree()
            False

        A Graph built from vertex-disjoint complete graphs
        linked by one edge to a special vertex `-1` is a
        ''star-shaped'' Gallai tree ::

            sage: g = 8 * graphs.CompleteGraph(6)
            sage: g.add_edges([(-1,c[0]) for c in g.connected_components()])
            sage: g.is_gallai_tree()
            True
        """

        if not self.is_connected():
            return False

        for c in self.blocks_and_cut_vertices()[0]:
            gg = self.subgraph(c)
            #                    is it an odd cycle ?              a complete graph ?
            if not ( (len(c)%2 == 1 and gg.size() == len(c)+1) or gg.is_clique() ):
                return False

        return True

    def is_clique(self, vertices=None, directed_clique=False):
        """
        Returns True if the set ``vertices`` is a clique, False
        if not. A clique is a set of vertices such that there is an edge
        between any two vertices.

        INPUT:


        -  ``vertices`` - Vertices can be a single vertex or an
           iterable container of vertices, e.g. a list, set, graph, file or
           numeric array. If not passed, defaults to the entire graph.

        -  ``directed_clique`` - (default False) If set to
           False, only consider the underlying undirected graph. If set to
           True and the graph is directed, only return True if all possible
           edges in _both_ directions exist.


        EXAMPLES::

            sage: g = graphs.CompleteGraph(4)
            sage: g.is_clique([1,2,3])
            True
            sage: g.is_clique()
            True
            sage: h = graphs.CycleGraph(4)
            sage: h.is_clique([1,2])
            True
            sage: h.is_clique([1,2,3])
            False
            sage: h.is_clique()
            False
            sage: i = graphs.CompleteGraph(4).to_directed()
            sage: i.delete_edge([0,1])
            sage: i.is_clique()
            True
            sage: i.is_clique(directed_clique=True)
            False
        """
        if directed_clique and self._directed:
            subgraph=self.subgraph(vertices)
            subgraph.allow_loops(False)
            subgraph.allow_multiple_edges(False)
            n=subgraph.order()
            return subgraph.size()==n*(n-1)
        else:
            if vertices is None:
                subgraph = self
            else:
                subgraph=self.subgraph(vertices)

            if self._directed:
                subgraph = subgraph.to_simple()

            n=subgraph.order()
            return subgraph.size()==n*(n-1)/2

    def is_independent_set(self, vertices=None):
        """
        Returns True if the set ``vertices`` is an independent
        set, False if not. An independent set is a set of vertices such
        that there is no edge between any two vertices.

        INPUT:


        -  ``vertices`` - Vertices can be a single vertex or an
           iterable container of vertices, e.g. a list, set, graph, file or
           numeric array. If not passed, defaults to the entire graph.


        EXAMPLES::

            sage: graphs.CycleGraph(4).is_independent_set([1,3])
            True
            sage: graphs.CycleGraph(4).is_independent_set([1,2,3])
            False
        """
        return self.subgraph(vertices).to_simple().size()==0

    def is_subgraph(self, other):
        """
        Tests whether self is a subgraph of other.

        EXAMPLES::

            sage: P = graphs.PetersenGraph()
            sage: G = P.subgraph(range(6))
            sage: G.is_subgraph(P)
            True
        """
        self_verts = self.vertices()
        for v in self_verts:
            if v not in other:
                return False
        return other.subgraph(self_verts) == self

    ### Cluster

    def cluster_triangles(self, nbunch=None, with_labels=False):
        r"""
        Returns the number of triangles for nbunch of vertices as a
        dictionary keyed by vertex.

        The clustering coefficient of a graph is the fraction of possible
        triangles that are triangles, `c_i = triangles_i /
        (k_i\*(k_i-1)/2)` where `k_i` is the degree of vertex `i`, [1]. A
        coefficient for the whole graph is the average of the `c_i`.
        Transitivity is the fraction of all possible triangles which are
        triangles, T = 3\*triangles/triads, [HSSNX]_.

        INPUT:


        -  ``nbunch`` - The vertices to inspect. If
           nbunch=None, returns data for all vertices in the graph


        REFERENCE:

        .. [HSSNX] Aric Hagberg, Dan Schult and Pieter Swart. NetworkX
          documentation. [Online] Available:
          https://networkx.lanl.gov/reference/networkx/

        EXAMPLES::

            sage: (graphs.FruchtGraph()).cluster_triangles().values()
            [1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 0]
            sage: (graphs.FruchtGraph()).cluster_triangles()
            {0: 1, 1: 1, 2: 0, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1, 8: 0, 9: 1, 10: 1, 11: 0}
            sage: (graphs.FruchtGraph()).cluster_triangles(nbunch=[0,1,2])
            {0: 1, 1: 1, 2: 0}
        """
        import networkx
        return networkx.triangles(self.networkx_graph(copy=False), nbunch)

    def clustering_average(self):
        r"""
        Returns the average clustering coefficient.

        The clustering coefficient of a graph is the fraction of possible
        triangles that are triangles, `c_i = triangles_i /
        (k_i\*(k_i-1)/2)` where `k_i` is the degree of vertex `i`, [1]. A
        coefficient for the whole graph is the average of the `c_i`.
        Transitivity is the fraction of all possible triangles which are
        triangles, T = 3\*triangles/triads, [1].

        REFERENCE:

        - [1] Aric Hagberg, Dan Schult and Pieter Swart. NetworkX
          documentation. [Online] Available:
          https://networkx.lanl.gov/reference/networkx/

        EXAMPLES::

            sage: (graphs.FruchtGraph()).clustering_average()
            0.25
        """
        import networkx
        return networkx.average_clustering(self.networkx_graph(copy=False))

    def clustering_coeff(self, nbunch=None, weights=False):
        r"""
        Returns the clustering coefficient for each vertex in nbunch as a
        dictionary keyed by vertex.

        The clustering coefficient of a graph is the fraction of possible
        triangles that are triangles, `c_i = triangles_i /
        (k_i\*(k_i-1)/2)` where `k_i` is the degree of vertex `i`, [1]. A
        coefficient for the whole graph is the average of the `c_i`.
        Transitivity is the fraction of all possible triangles which are
        triangles, T = 3\*triangles/triads, [1].

        INPUT:

        -  ``nbunch`` - the vertices to inspect (default
           None returns data on all vertices in graph)

        -  ``weights`` - default is False. If both
           with_labels and weights are True, then returns a clustering
           coefficient dict and a dict of weights based on degree. Weights are
           the fraction of connected triples in the graph that include the
           keyed vertex.


        REFERENCE:

        - [1] Aric Hagberg, Dan Schult and Pieter Swart. NetworkX
          documentation. [Online] Available:
          https://networkx.lanl.gov/reference/networkx/

        EXAMPLES::

            sage: (graphs.FruchtGraph()).clustering_coeff().values()
            [0.33333333333333331, 0.33333333333333331, 0.0, 0.33333333333333331, 0.33333333333333331, 0.33333333333333331, 0.33333333333333331, 0.33333333333333331, 0.0, 0.33333333333333331, 0.33333333333333331, 0.0]
            sage: (graphs.FruchtGraph()).clustering_coeff()
            {0: 0.33333333333333331, 1: 0.33333333333333331, 2: 0.0, 3: 0.33333333333333331, 4: 0.33333333333333331, 5: 0.33333333333333331, 6: 0.33333333333333331, 7: 0.33333333333333331, 8: 0.0, 9: 0.33333333333333331, 10: 0.33333333333333331, 11: 0.0}
            sage: (graphs.FruchtGraph()).clustering_coeff(weights=True)
            ({0: 0.33333333333333331, 1: 0.33333333333333331, 2: 0.0, 3: 0.33333333333333331, 4: 0.33333333333333331, 5: 0.33333333333333331, 6: 0.33333333333333331, 7: 0.33333333333333331, 8: 0.0, 9: 0.33333333333333331, 10: 0.33333333333333331, 11: 0.0}, {0: 0.083333333333333329, 1: 0.083333333333333329, 2: 0.083333333333333329, 3: 0.083333333333333329, 4: 0.083333333333333329, 5: 0.083333333333333329, 6: 0.083333333333333329, 7: 0.083333333333333329, 8: 0.083333333333333329, 9: 0.083333333333333329, 10: 0.083333333333333329, 11: 0.083333333333333329})
            sage: (graphs.FruchtGraph()).clustering_coeff(nbunch=[0,1,2])
            {0: 0.33333333333333331, 1: 0.33333333333333331, 2: 0.0}
            sage: (graphs.FruchtGraph()).clustering_coeff(nbunch=[0,1,2],weights=True)
            ({0: 0.33333333333333331, 1: 0.33333333333333331, 2: 0.0}, {0: 0.33333333333333331, 1: 0.33333333333333331, 2: 0.33333333333333331})
        """
        import networkx
        return networkx.clustering(self.networkx_graph(copy=False), nbunch, weights)

    def cluster_transitivity(self):
        r"""
        Returns the transitivity (fraction of transitive triangles) of the
        graph.

        The clustering coefficient of a graph is the fraction of possible
        triangles that are triangles, `c_i = triangles_i /
        (k_i\*(k_i-1)/2)` where `k_i` is the degree of vertex `i`, [1]. A
        coefficient for the whole graph is the average of the `c_i`.
        Transitivity is the fraction of all possible triangles which are
        triangles, T = 3\*triangles/triads, [1].

        REFERENCE:

        .. [1] Aric Hagberg, Dan Schult and Pieter Swart. NetworkX
          documentation. [Online] Available:
          https://networkx.lanl.gov/reference/networkx/

        EXAMPLES::

            sage: (graphs.FruchtGraph()).cluster_transitivity()
            0.25
        """
        import networkx
        return networkx.transitivity(self.networkx_graph(copy=False))

    ### Cores

    def cores(self, with_labels=False):
        """
        Returns the core number for each vertex in an ordered list.

           K-cores in graph theory were introduced by Seidman in 1983
           and by Bollobas in 1984 as a method of (destructively)
           simplifying graph topology to aid in analysis and
           visualization. They have been more recently defined as the
           following by Batagelj et al: given a graph `G` with
           vertices set `V` and edges set `E`, the `k`-core is
           computed by pruning all the vertices (with their respective
           edges) with degree less than `k`. That means that if a
           vertex `u` has degree `d_u`, and it has `n` neighbors with
           degree less than `k`, then the degree of `u` becomes `d_u -
           n`, and it will be also pruned if `k > d_u - n`. This
           operation can be useful to filter or to study some
           properties of the graphs. For instance, when you compute
           the 2-core of graph G, you are cutting all the vertices
           which are in a tree part of graph.  (A tree is a graph with
           no loops). [WPkcore]_

        [PSW1996]_ defines a `k`-core as the largest subgraph with minimum
        degree at least `k`.

        This implementation is based on the NetworkX implementation of
        the algorithm described in [BZ]_.

        INPUT:


        -  ``with_labels`` - default False returns list as
           described above. True returns dict keyed by vertex labels.


        REFERENCE:

        .. [WPkcore] K-core. Wikipedia. (2007). [Online] Available:
          http://en.wikipedia.org/wiki/K-core

        .. [PSW1996] Boris Pittel, Joel Spencer and Nicholas Wormald. Sudden
          Emergence of a Giant k-Core in a Random
          Graph. (1996). J. Combinatorial Theory. Ser B 67. pages
          111-151. [Online] Available:
          http://cs.nyu.edu/cs/faculty/spencer/papers/k-core.pdf

        .. [BZ] Vladimir Batagelj and Matjaz Zaversnik. An `O(m)`
          Algorithm for Cores Decomposition of
          Networks. arXiv:cs/0310049v1. [Online] Available:
          http://arxiv.org/abs/cs/0310049

        EXAMPLES::

            sage: (graphs.FruchtGraph()).cores()
            [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3]
            sage: (graphs.FruchtGraph()).cores(with_labels=True)
            {0: 3, 1: 3, 2: 3, 3: 3, 4: 3, 5: 3, 6: 3, 7: 3, 8: 3, 9: 3, 10: 3, 11: 3}
            sage: a=random_matrix(ZZ,20,x=2,sparse=True, density=.1)
            sage: b=DiGraph(20)
            sage: b.add_edges(a.nonzero_positions())
            sage: cores=b.cores(with_labels=True); cores
            {0: 3, 1: 3, 2: 3, 3: 3, 4: 2, 5: 2, 6: 3, 7: 1, 8: 3, 9: 3, 10: 3, 11: 3, 12: 3, 13: 3, 14: 2, 15: 3, 16: 3, 17: 3, 18: 3, 19: 3}
            sage: [v for v,c in cores.items() if c>=2] # the vertices in the 2-core
            [0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
        """
        # compute the degrees of each vertex
        degrees=self.degree(labels=True)

        # sort vertices by degree.  Store in a list and keep track of
        # where a specific degree starts (effectively, the list is
        # sorted by bins).
        verts= sorted( degrees.keys(), key=lambda x: degrees[x])
        bin_boundaries=[0]
        curr_degree=0
        for i,v in enumerate(verts):
            if degrees[v]>curr_degree:
                bin_boundaries.extend([i]*(degrees[v]-curr_degree))
                curr_degree=degrees[v]
        vert_pos = dict((v,pos) for pos,v in enumerate(verts))
        # Set up initial guesses for core and lists of neighbors.
        core= degrees
        nbrs=dict((v,set(self.neighbors(v))) for v in self)
        # form vertex core building up from smallest
        for v in verts:
            for u in nbrs[v]:
                if core[u] > core[v]:
                    nbrs[u].remove(v)

                    # cleverly move u to the end of the next smallest
                    # bin (i.e., subtract one from the degree of u).
                    # We do this by swapping u with the first vertex
                    # in the bin that contains u, then incrementing
                    # the bin boundary for the bin that contains u.
                    pos=vert_pos[u]
                    bin_start=bin_boundaries[core[u]]
                    vert_pos[u]=bin_start
                    vert_pos[verts[bin_start]]=pos
                    verts[bin_start],verts[pos]=verts[pos],verts[bin_start]
                    bin_boundaries[core[u]]+=1
                    core[u] -= 1

        if with_labels:
            return core
        else:
            return core.values()

    ### Distance

    def distance(self, u, v):
        """
        Returns the (directed) distance from u to v in the (di)graph, i.e.
        the length of the shortest path from u to v.

        EXAMPLES::

            sage: G = graphs.CycleGraph(9)
            sage: G.distance(0,1)
            1
            sage: G.distance(0,4)
            4
            sage: G.distance(0,5)
            4
            sage: G = Graph( {0:[], 1:[]} )
            sage: G.distance(0,1)
            +Infinity
        """
        return self.shortest_path_length(u, v)

    def distance_all_pairs(self):
        r"""
        Returns the distances between all pairs of vertices.

        OUTPUT:

        A doubly indexed dictionary

        EXAMPLE:

        The Petersen Graph::

            sage: g = graphs.PetersenGraph()
            sage: print g.distance_all_pairs()
            {0: {0: 0, 1: 1, 2: 2, 3: 2, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 2}, 1: {0: 1, 1: 0, 2: 1, 3: 2, 4: 2, 5: 2, 6: 1, 7: 2, 8: 2, 9: 2}, 2: {0: 2, 1: 1, 2: 0, 3: 1, 4: 2, 5: 2, 6: 2, 7: 1, 8: 2, 9: 2}, 3: {0: 2, 1: 2, 2: 1, 3: 0, 4: 1, 5: 2, 6: 2, 7: 2, 8: 1, 9: 2}, 4: {0: 1, 1: 2, 2: 2, 3: 1, 4: 0, 5: 2, 6: 2, 7: 2, 8: 2, 9: 1}, 5: {0: 1, 1: 2, 2: 2, 3: 2, 4: 2, 5: 0, 6: 2, 7: 1, 8: 1, 9: 2}, 6: {0: 2, 1: 1, 2: 2, 3: 2, 4: 2, 5: 2, 6: 0, 7: 2, 8: 1, 9: 1}, 7: {0: 2, 1: 2, 2: 1, 3: 2, 4: 2, 5: 1, 6: 2, 7: 0, 8: 2, 9: 1}, 8: {0: 2, 1: 2, 2: 2, 3: 1, 4: 2, 5: 1, 6: 1, 7: 2, 8: 0, 9: 2}, 9: {0: 2, 1: 2, 2: 2, 3: 2, 4: 1, 5: 2, 6: 1, 7: 1, 8: 2, 9: 0}}

        Testing on Random Graphs::

            sage: g = graphs.RandomGNP(20,.3)
            sage: distances = g.distance_all_pairs()
            sage: all([g.distance(0,v) == distances[0][v] for v in g])
            True
        """

        from sage.rings.infinity import Infinity
        distances = dict([(v, self.shortest_path_lengths(v)) for v in self])

        # setting the necessary +Infinity
        cc = self.connected_components()
        for cc1 in cc:
            for cc2 in cc:
                if cc1 != cc2:
                    for u in cc1:
                        for v in cc2:
                            distances[u][v] = Infinity

        return distances

    def eccentricity(self, v=None, dist_dict=None, with_labels=False):
        """
        Return the eccentricity of vertex (or vertices) v.

        The eccentricity of a vertex is the maximum distance to any other
        vertex.

        INPUT:


        -  ``v`` - either a single vertex or a list of
           vertices. If it is not specified, then it is taken to be all
           vertices.

        -  ``dist_dict`` - optional, a dict of dicts of
           distance.

        -  ``with_labels`` - Whether to return a list or a
           dict.


        EXAMPLES::

            sage: G = graphs.KrackhardtKiteGraph()
            sage: G.eccentricity()
            [4, 4, 4, 4, 4, 3, 3, 2, 3, 4]
            sage: G.vertices()
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
            sage: G.eccentricity(7)
            2
            sage: G.eccentricity([7,8,9])
            [3, 4, 2]
            sage: G.eccentricity([7,8,9], with_labels=True) == {8: 3, 9: 4, 7: 2}
            True
            sage: G = Graph( { 0 : [], 1 : [], 2 : [1] } )
            sage: G.eccentricity()
            [+Infinity, +Infinity, +Infinity]
            sage: G = Graph({0:[]})
            sage: G.eccentricity(with_labels=True)
            {0: 0}
            sage: G = Graph({0:[], 1:[]})
            sage: G.eccentricity(with_labels=True)
            {0: +Infinity, 1: +Infinity}
        """
        if v is None:
            v = self.vertices()
        elif not isinstance(v, list):
            v = [v]
        e = {}
        infinite = False
        for u in v:
            if dist_dict is None:
                length = self.shortest_path_lengths(u)
            else:
                length = dist_dict[u]
            if len(length) != self.num_verts():
                infinite = True
                break
            e[u] = max(length.values())
        if infinite:
            from sage.rings.infinity import Infinity
            for u in v:
                e[u] = Infinity
        if with_labels:
            return e
        else:
            if len(e)==1: return e.values()[0] # return single value
            return e.values()

    def radius(self):
        """
        Returns the radius of the (di)graph.

        The radius is defined to be the minimum eccentricity of any vertex,
        where the eccentricity is the maximum distance to any other
        vertex.

        EXAMPLES: The more symmetric a graph is, the smaller (diameter -
        radius) is.

        ::

            sage: G = graphs.BarbellGraph(9, 3)
            sage: G.radius()
            3
            sage: G.diameter()
            6

        ::

            sage: G = graphs.OctahedralGraph()
            sage: G.radius()
            2
            sage: G.diameter()
            2
        """
        return min(self.eccentricity())

    def center(self):
        """
        Returns the set of vertices in the center, i.e. whose eccentricity
        is equal to the radius of the (di)graph.

        In other words, the center is the set of vertices achieving the
        minimum eccentricity.

        EXAMPLES::

            sage: G = graphs.DiamondGraph()
            sage: G.center()
            [1, 2]
            sage: P = graphs.PetersenGraph()
            sage: P.subgraph(P.center()) == P
            True
            sage: S = graphs.StarGraph(19)
            sage: S.center()
            [0]
            sage: G = Graph()
            sage: G.center()
            []
            sage: G.add_vertex()
            sage: G.center()
            [0]
        """
        e = self.eccentricity(with_labels=True)
        try:
            r = min(e.values())
        except:
            return []
        return [v for v in e if e[v]==r]

    def diameter(self):
        """
        Returns the largest distance between any two vertices. Returns
        Infinity if the (di)graph is not connected.

        EXAMPLES::

            sage: G = graphs.PetersenGraph()
            sage: G.diameter()
            2
            sage: G = Graph( { 0 : [], 1 : [], 2 : [1] } )
            sage: G.diameter()
            +Infinity

        Although max( ) is usually defined as -Infinity, since the diameter
        will never be negative, we define it to be zero::

            sage: G = graphs.EmptyGraph()
            sage: G.diameter()
            0
        """
        e = self.eccentricity()
        if not isinstance(e, list):
            e = [e]
        if len(e) == 0:
            return 0
        return max(e)

    def distance_graph(self, dist):
        r"""
        Returns the graph on the same vertex set as
        the original graph but vertices are adjacent
        in the returned graph if and only if they are
        at specified distances in the original graph.

        INPUT:

        - ``dist`` is a nonnegative integer or
          a list of nonnegative integers.
          ``Infinity`` may be used here to describe
          vertex pairs in separate components.

        OUTPUT:

        The returned value is an undirected graph.  The
        vertex set is identical to the calling graph, but edges
        of the returned graph join vertices whose distance in
        the calling graph are present in the input ``dist``.
        Loops will only be present if distance 0 is included.  If
        the original graph has a position dictionary specifying
        locations of vertices for plotting, then this information
        is copied over to the distance graph.  In some instances
        this layout may not be the best, and might even be confusing
        when edges run on top of each other due to symmetries
        chosen for the layout.

        EXAMPLES::

            sage: G = graphs.CompleteGraph(3)
            sage: H = G.cartesian_product(graphs.CompleteGraph(2))
            sage: K = H.distance_graph(2)
            sage: K.am()
            [0 0 0 1 0 1]
            [0 0 1 0 1 0]
            [0 1 0 0 0 1]
            [1 0 0 0 1 0]
            [0 1 0 1 0 0]
            [1 0 1 0 0 0]

        To obtain the graph where vertices are adjacent if their
        distance apart is ``d`` or less use a ``range()`` command
        to create the input, using ``d+1`` as the input to ``range``.
        Notice that this will include distance 0 and hence place a loop
        at each vertex.  To avoid this, use ``range(1,d+1)``. ::

            sage: G = graphs.OddGraph(4)
            sage: d = G.diameter()
            sage: n = G.num_verts()
            sage: H = G.distance_graph(range(d+1))
            sage: H.is_isomorphic(graphs.CompleteGraph(n))
            False
            sage: H = G.distance_graph(range(1,d+1))
            sage: H.is_isomorphic(graphs.CompleteGraph(n))
            True

        A complete collection of distance graphs will have
        adjacency matrices that sum to the matrix of all ones. ::

            sage: P = graphs.PathGraph(20)
            sage: all_ones = sum([P.distance_graph(i).am() for i in range(20)])
            sage: all_ones == matrix(ZZ, 20, 20, [1]*400)
            True

        Four-bit strings differing in one bit is the same as
        four-bit strings differing in three bits.  ::

            sage: G = graphs.CubeGraph(4)
            sage: H = G.distance_graph(3)
            sage: G.is_isomorphic(H)
            True

        The graph of eight-bit strings, adjacent if different
        in an odd number of bits.  ::

            sage: G = graphs.CubeGraph(8) # long time
            sage: H = G.distance_graph([1,3,5,7]) # long time
            sage: degrees = [0]*sum([binomial(8,j) for j in [1,3,5,7]]) # long time
            sage: degrees.append(2^8) # long time
            sage: degrees == H.degree_histogram() # long time
            True

        An example of using ``Infinity`` as the distance in
        a graph that is not connected. ::

            sage: G = graphs.CompleteGraph(3)
            sage: H = G.disjoint_union(graphs.CompleteGraph(2))
            sage: L = H.distance_graph(Infinity)
            sage: L.am()
            [0 0 0 1 1]
            [0 0 0 1 1]
            [0 0 0 1 1]
            [1 1 1 0 0]
            [1 1 1 0 0]

        TESTS:

        Empty input, or unachievable distances silently yield empty graphs. ::

            sage: G = graphs.CompleteGraph(5)
            sage: G.distance_graph([]).num_edges()
            0
            sage: G = graphs.CompleteGraph(5)
            sage: G.distance_graph(23).num_edges()
            0

        It is an error to provide a distance that is not an integer type. ::

            sage: G = graphs.CompleteGraph(5)
            sage: G.distance_graph('junk')
            Traceback (most recent call last):
            ...
            TypeError: unable to convert x (=junk) to an integer

        It is an error to provide a negative distance. ::

            sage: G = graphs.CompleteGraph(5)
            sage: G.distance_graph(-3)
            Traceback (most recent call last):
            ...
            ValueError: Distance graph for a negative distance (d=-3) is not defined

        AUTHOR:

        Rob Beezer, 2009-11-25
        """
        from sage.rings.infinity import Infinity
        from copy import copy
        # If input is not a list, make a list with this single object
        if not isinstance(dist, list):
            dist = [dist]
        # Create a list of positive integer (or infinite) distances
        distances = []
        for d in dist:
            if d == Infinity:
                distances.append(d)
            else:
                dint = ZZ(d)
                if dint < 0:
                    raise ValueError('Distance graph for a negative distance (d=%d) is not defined' % dint)
                distances.append(dint)
        # Build a graph on the same vertex set, with loops for distance 0
        vertices = {}
        for v in self.vertex_iterator():
            vertices[v] = {}
        positions = copy(self.get_pos())
        if ZZ(0) in distances:
            looped = True
        else:
            looped = False
        from sage.graphs.all import Graph
        D = Graph(vertices, pos=positions, multiedges=False, loops=looped)
        if len(distances) == 1:
            dstring = "distance " + str(distances[0])
        else:
            dstring = "distances " + str(sorted(distances))
        D.name("Distance graph for %s in " % dstring + self.name())

        # Create the appropriate edges
        d = self.distance_all_pairs()
        for u in self.vertex_iterator():
            for v in self.vertex_iterator():
                if d[u][v] in distances:
                    D.add_edge(u,v)
        return D

    def girth(self):
        """
        Computes the girth of the graph. For directed graphs, computes the
        girth of the undirected graph.

        The girth is the length of the shortest cycle in the graph. Graphs
        without cycles have infinite girth.

        EXAMPLES::

            sage: graphs.TetrahedralGraph().girth()
            3
            sage: graphs.CubeGraph(3).girth()
            4
            sage: graphs.PetersenGraph().girth()
            5
            sage: graphs.HeawoodGraph().girth()
            6
            sage: graphs.trees(9).next().girth()
            +Infinity
        """
        n = self.num_verts()
        best = n+1
        for i in self.vertex_iterator():
            span = set([i])
            depth = 1
            thisList = set([i])
            while 2*depth <= best and 3 < best:
                nextList = set()
                for v in thisList:
                    for u in self.neighbors(v):
                        if not u in span:
                            span.add(u)
                            nextList.add(u)
                        else:
                            if u in thisList:
                                best = depth*2-1
                                break
                            if u in nextList:
                                best = depth*2
                thisList = nextList
                depth += 1
        if best == n+1:
            from sage.rings.infinity import Infinity
            return Infinity
        return best



    def periphery(self):
        """
        Returns the set of vertices in the periphery, i.e. whose
        eccentricity is equal to the diameter of the (di)graph.

        In other words, the periphery is the set of vertices achieving the
        maximum eccentricity.

        EXAMPLES::

            sage: G = graphs.DiamondGraph()
            sage: G.periphery()
            [0, 3]
            sage: P = graphs.PetersenGraph()
            sage: P.subgraph(P.periphery()) == P
            True
            sage: S = graphs.StarGraph(19)
            sage: S.periphery()
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
            sage: G = Graph()
            sage: G.periphery()
            []
            sage: G.add_vertex()
            sage: G.periphery()
            [0]
        """
        e = self.eccentricity(with_labels=True)
        try:
            r = max(e.values())
        except:
            return []
        return [v for v in e if e[v]==r]

    ### Paths

    def interior_paths(self, start, end):
        """
        Returns an exhaustive list of paths (also lists) through only
        interior vertices from vertex start to vertex end in the
        (di)graph.

        Note - start and end do not necessarily have to be boundary
        vertices.

        INPUT:


        -  ``start`` - the vertex of the graph to search for
           paths from

        -  ``end`` - the vertex of the graph to search for
           paths to


        EXAMPLES::

            sage: eg1 = Graph({0:[1,2], 1:[4], 2:[3,4], 4:[5], 5:[6]})
            sage: sorted(eg1.all_paths(0,6))
            [[0, 1, 4, 5, 6], [0, 2, 4, 5, 6]]
            sage: eg2 = copy(eg1)
            sage: eg2.set_boundary([0,1,3])
            sage: sorted(eg2.interior_paths(0,6))
            [[0, 2, 4, 5, 6]]
            sage: sorted(eg2.all_paths(0,6))
            [[0, 1, 4, 5, 6], [0, 2, 4, 5, 6]]
            sage: eg3 = graphs.PetersenGraph()
            sage: eg3.set_boundary([0,1,2,3,4])
            sage: sorted(eg3.all_paths(1,4))
            [[1, 0, 4],
             [1, 0, 5, 7, 2, 3, 4],
             [1, 0, 5, 7, 2, 3, 8, 6, 9, 4],
             [1, 0, 5, 7, 9, 4],
             [1, 0, 5, 7, 9, 6, 8, 3, 4],
             [1, 0, 5, 8, 3, 2, 7, 9, 4],
             [1, 0, 5, 8, 3, 4],
             [1, 0, 5, 8, 6, 9, 4],
             [1, 0, 5, 8, 6, 9, 7, 2, 3, 4],
             [1, 2, 3, 4],
             [1, 2, 3, 8, 5, 0, 4],
             [1, 2, 3, 8, 5, 7, 9, 4],
             [1, 2, 3, 8, 6, 9, 4],
             [1, 2, 3, 8, 6, 9, 7, 5, 0, 4],
             [1, 2, 7, 5, 0, 4],
             [1, 2, 7, 5, 8, 3, 4],
             [1, 2, 7, 5, 8, 6, 9, 4],
             [1, 2, 7, 9, 4],
             [1, 2, 7, 9, 6, 8, 3, 4],
             [1, 2, 7, 9, 6, 8, 5, 0, 4],
             [1, 6, 8, 3, 2, 7, 5, 0, 4],
             [1, 6, 8, 3, 2, 7, 9, 4],
             [1, 6, 8, 3, 4],
             [1, 6, 8, 5, 0, 4],
             [1, 6, 8, 5, 7, 2, 3, 4],
             [1, 6, 8, 5, 7, 9, 4],
             [1, 6, 9, 4],
             [1, 6, 9, 7, 2, 3, 4],
             [1, 6, 9, 7, 2, 3, 8, 5, 0, 4],
             [1, 6, 9, 7, 5, 0, 4],
             [1, 6, 9, 7, 5, 8, 3, 4]]
            sage: sorted(eg3.interior_paths(1,4))
            [[1, 6, 8, 5, 7, 9, 4], [1, 6, 9, 4]]
            sage: dg = DiGraph({0:[1,3,4], 1:[3], 2:[0,3,4],4:[3]}, boundary=[4])
            sage: sorted(dg.all_paths(0,3))
            [[0, 1, 3], [0, 3], [0, 4, 3]]
            sage: sorted(dg.interior_paths(0,3))
            [[0, 1, 3], [0, 3]]
            sage: ug = dg.to_undirected()
            sage: sorted(ug.all_paths(0,3))
            [[0, 1, 3], [0, 2, 3], [0, 2, 4, 3], [0, 3], [0, 4, 2, 3], [0, 4, 3]]
            sage: sorted(ug.interior_paths(0,3))
            [[0, 1, 3], [0, 2, 3], [0, 3]]
        """
        from copy import copy
        H = copy(self)
        for vertex in self.get_boundary():
            if (vertex != start and vertex != end):
                H.delete_edges(H.edges_incident(vertex))
        return H.all_paths(start, end)

    def all_paths(self, start, end):
        """
        Returns a list of all paths (also lists) between a pair of vertices
        (start, end) in the (di)graph.

        EXAMPLES::

            sage: eg1 = Graph({0:[1,2], 1:[4], 2:[3,4], 4:[5], 5:[6]})
            sage: eg1.all_paths(0,6)
            [[0, 1, 4, 5, 6], [0, 2, 4, 5, 6]]
            sage: eg2 = graphs.PetersenGraph()
            sage: sorted(eg2.all_paths(1,4))
            [[1, 0, 4],
             [1, 0, 5, 7, 2, 3, 4],
             [1, 0, 5, 7, 2, 3, 8, 6, 9, 4],
             [1, 0, 5, 7, 9, 4],
             [1, 0, 5, 7, 9, 6, 8, 3, 4],
             [1, 0, 5, 8, 3, 2, 7, 9, 4],
             [1, 0, 5, 8, 3, 4],
             [1, 0, 5, 8, 6, 9, 4],
             [1, 0, 5, 8, 6, 9, 7, 2, 3, 4],
             [1, 2, 3, 4],
             [1, 2, 3, 8, 5, 0, 4],
             [1, 2, 3, 8, 5, 7, 9, 4],
             [1, 2, 3, 8, 6, 9, 4],
             [1, 2, 3, 8, 6, 9, 7, 5, 0, 4],
             [1, 2, 7, 5, 0, 4],
             [1, 2, 7, 5, 8, 3, 4],
             [1, 2, 7, 5, 8, 6, 9, 4],
             [1, 2, 7, 9, 4],
             [1, 2, 7, 9, 6, 8, 3, 4],
             [1, 2, 7, 9, 6, 8, 5, 0, 4],
             [1, 6, 8, 3, 2, 7, 5, 0, 4],
             [1, 6, 8, 3, 2, 7, 9, 4],
             [1, 6, 8, 3, 4],
             [1, 6, 8, 5, 0, 4],
             [1, 6, 8, 5, 7, 2, 3, 4],
             [1, 6, 8, 5, 7, 9, 4],
             [1, 6, 9, 4],
             [1, 6, 9, 7, 2, 3, 4],
             [1, 6, 9, 7, 2, 3, 8, 5, 0, 4],
             [1, 6, 9, 7, 5, 0, 4],
             [1, 6, 9, 7, 5, 8, 3, 4]]
            sage: dg = DiGraph({0:[1,3], 1:[3], 2:[0,3]})
            sage: sorted(dg.all_paths(0,3))
            [[0, 1, 3], [0, 3]]
            sage: ug = dg.to_undirected()
            sage: sorted(ug.all_paths(0,3))
            [[0, 1, 3], [0, 2, 3], [0, 3]]
        """
        if self.is_directed():
            iterator=self.neighbor_out_iterator
        else:
            iterator=self.neighbor_iterator
        all_paths = []      # list of
        act_path = []       # the current path
        act_path_iter = []  # the neighbor/successor-iterators of the current path
        done = False
        s=start
        while not done:
            if s==end:      # if path completes, add to list
                all_paths.append(act_path+[s])
            else:
                if s not in act_path:   # we want vertices just once in a path
                    act_path.append(s)  # extend current path
                    act_path_iter.append(iterator(s))  # save the state of the neighbor/successor-iterator of the current vertex
            s=None
            while (s is None) and not done:
                try:
                    s=act_path_iter[-1].next()  # try to get the next neighbor/successor, ...
                except (StopIteration):         # ... if there is none ...
                    act_path.pop()              # ... go one step back
                    act_path_iter.pop()
                if len(act_path)==0:            # there is no other vertex ...
                    done = True                 # ... so we are done
        return all_paths


    def shortest_path(self, u, v, by_weight=False, bidirectional=True):
        """
        Returns a list of vertices representing some shortest path from u
        to v: if there is no path from u to v, the list is empty.

        INPUT:


        -  ``by_weight`` - if False, uses a breadth first
           search. If True, takes edge weightings into account, using
           Dijkstra's algorithm.

        -  ``bidirectional`` - if True, the algorithm will
           expand vertices from u and v at the same time, making two spheres
           of half the usual radius. This generally doubles the speed
           (consider the total volume in each case).


        EXAMPLES::

            sage: D = graphs.DodecahedralGraph()
            sage: D.shortest_path(4, 9)
            [4, 17, 16, 12, 13, 9]
            sage: D.shortest_path(5, 5)
            [5]
            sage: D.delete_edges(D.edges_incident(13))
            sage: D.shortest_path(13, 4)
            []
            sage: G = Graph( { 0: [1], 1: [2], 2: [3], 3: [4], 4: [0] })
            sage: G.plot(edge_labels=True).show() # long time
            sage: G.shortest_path(0, 3)
            [0, 4, 3]
            sage: G = Graph( { 0: {1: 1}, 1: {2: 1}, 2: {3: 1}, 3: {4: 2}, 4: {0: 2} }, sparse = True)
            sage: G.shortest_path(0, 3, by_weight=True)
            [0, 1, 2, 3]
        """ #         TODO- multiple edges??
        if u == v: # to avoid a NetworkX bug
            return [u]
        import networkx
        if by_weight:
            if bidirectional:
                try:
                    L = self._backend.bidirectional_dijkstra(u,v)
                except AttributeError:
                    try:
                        L = networkx.bidirectional_dijkstra(self.networkx_graph(copy=False), u, v)[1]
                    except:
                        L = False
            else:
                L = networkx.dijkstra_path(self.networkx_graph(copy=False), u, v)
        else:
            if bidirectional:
                # If the graph is a C_graph, use shortest_path from its backend !
                try:
                    L = self._backend.shortest_path(u,v)
                except AttributeError:
                    L = networkx.shortest_path(self.networkx_graph(copy=False), u, v)
            else:
                try:
                    L = networkx.single_source_shortest_path(self.networkx_graph(copy=False), u)[v]
                except:
                    L = False
        if L:
            return L
        else:
            return []

    def shortest_path_length(self, u, v, by_weight=False,
                                         bidirectional=True,
                                         weight_sum=None):
        """
        Returns the minimal length of paths from u to v: if there is no
        path from u to v, returns Infinity.

        INPUT:


        -  ``by_weight`` - if False, uses a breadth first
           search. If True, takes edge weightings into account, using
           Dijkstra's algorithm.

        -  ``bidirectional`` - if True, the algorithm will
           expand vertices from u and v at the same time, making two spheres
           of half the usual radius. This generally doubles the speed
           (consider the total volume in each case).

        -  ``weight_sum`` - if False, returns the number of
           edges in the path. If True, returns the sum of the weights of these
           edges. Default behavior is to have the same value as by_weight.


        EXAMPLES::

            sage: D = graphs.DodecahedralGraph()
            sage: D.shortest_path_length(4, 9)
            5
            sage: D.shortest_path_length(5, 5)
            0
            sage: D.delete_edges(D.edges_incident(13))
            sage: D.shortest_path_length(13, 4)
            +Infinity
            sage: G = Graph( { 0: {1: 1}, 1: {2: 1}, 2: {3: 1}, 3: {4: 2}, 4: {0: 2} }, sparse = True)
            sage: G.plot(edge_labels=True).show() # long time
            sage: G.shortest_path_length(0, 3)
            2
            sage: G.shortest_path_length(0, 3, by_weight=True)
            3
        """
        if weight_sum is None:
            weight_sum = by_weight
        path = self.shortest_path(u, v, by_weight, bidirectional)
        length = len(path) - 1
        if length == -1:
            from sage.rings.infinity import Infinity
            return Infinity
        if weight_sum:
            wt = 0
            for j in range(length):
                wt += self.edge_label(path[j], path[j+1])
            return wt
        else:
            return length

    def shortest_paths(self, u, by_weight=False, cutoff=None):
        """
        Returns a dictionary d of shortest paths d[v] from u to v, for each
        vertex v connected by a path from u.

        INPUT:


        -  ``by_weight`` - if False, uses a breadth first
           search. If True, uses Dijkstra's algorithm to find the shortest
           paths by weight.

        -  ``cutoff`` - integer depth to stop search. Ignored
           if by_weight is True.


        EXAMPLES::

            sage: D = graphs.DodecahedralGraph()
            sage: D.shortest_paths(0)
            {0: [0], 1: [0, 1], 2: [0, 1, 2], 3: [0, 19, 3], 4: [0, 19, 3, 4], 5: [0, 1, 2, 6, 5], 6: [0, 1, 2, 6], 7: [0, 1, 8, 7], 8: [0, 1, 8], 9: [0, 10, 9], 10: [0, 10], 11: [0, 10, 11], 12: [0, 10, 11, 12], 13: [0, 10, 9, 13], 14: [0, 1, 8, 7, 14], 15: [0, 19, 18, 17, 16, 15], 16: [0, 19, 18, 17, 16], 17: [0, 19, 18, 17], 18: [0, 19, 18], 19: [0, 19]}

        All these paths are obviously induced graphs::

            sage: all([D.subgraph(p).is_isomorphic(graphs.PathGraph(len(p)) )for p in D.shortest_paths(0).values()])
            True

        ::

            sage: D.shortest_paths(0, cutoff=2)
            {0: [0], 1: [0, 1], 2: [0, 1, 2], 3: [0, 19, 3], 8: [0, 1, 8], 9: [0, 10, 9], 10: [0, 10], 11: [0, 10, 11], 18: [0, 19, 18], 19: [0, 19]}
            sage: G = Graph( { 0: {1: 1}, 1: {2: 1}, 2: {3: 1}, 3: {4: 2}, 4: {0: 2} }, sparse=True)
            sage: G.plot(edge_labels=True).show() # long time
            sage: G.shortest_paths(0, by_weight=True)
            {0: [0], 1: [0, 1], 2: [0, 1, 2], 3: [0, 1, 2, 3], 4: [0, 4]}
        """
        import networkx
        if by_weight:
            return networkx.single_source_dijkstra_path(self.networkx_graph(copy=False), u)
        else:
            try:
                return self._backend.shortest_path_all_vertices(u, cutoff)
            except AttributeError:
                return networkx.single_source_shortest_path(self.networkx_graph(copy=False), u, cutoff)

    def shortest_path_lengths(self, u, by_weight=False, weight_sums=None):
        """
        Returns a dictionary of shortest path lengths keyed by targets that
        are connected by a path from u.

        INPUT:


        -  ``by_weight`` - if False, uses a breadth first
           search. If True, takes edge weightings into account, using
           Dijkstra's algorithm.

        -  ``weight_sums`` - if False, returns the number of
           edges in each path. If True, returns the sum of the weights of
           these edges. Default behavior is to have the same value as
           by_weight.


        EXAMPLES::

            sage: D = graphs.DodecahedralGraph()
            sage: D.shortest_path_lengths(0)
            {0: 0, 1: 1, 2: 2, 3: 2, 4: 3, 5: 4, 6: 3, 7: 3, 8: 2, 9: 2, 10: 1, 11: 2, 12: 3, 13: 3, 14: 4, 15: 5, 16: 4, 17: 3, 18: 2, 19: 1}
            sage: G = Graph( { 0: {1: 1}, 1: {2: 1}, 2: {3: 1}, 3: {4: 2}, 4: {0: 2} }, sparse=True )
            sage: G.plot(edge_labels=True).show() # long time
            sage: G.shortest_path_lengths(0, by_weight=True)
            {0: 0, 1: 1, 2: 2, 3: 3, 4: 2}
        """
        if weight_sums is None:
            weight_sums = by_weight
        paths = self.shortest_paths(u, by_weight)
        if weight_sums:
            weights = {}
            for v in paths:
                wt = 0
                path = paths[v]
                for j in range(len(path) - 1):
                    wt += self.edge_label(path[j], path[j+1])
                weights[v] = wt
            return weights
        else:
            lengths = {}
            for v in paths:
                lengths[v] = len(paths[v]) - 1
            return lengths

    def shortest_path_all_pairs(self, by_weight=True, default_weight=1):
        """
        Uses the Floyd-Warshall algorithm to find a shortest weighted path
        for each pair of vertices.

        The weights (labels) on the vertices can be anything that can be
        compared and can be summed.

        INPUT:


        -  ``by_weight`` - If False, figure distances by the
           numbers of edges.

        -  ``default_weight`` - (defaults to 1) The default
           weight to assign edges that don't have a weight (i.e., a label).


        OUTPUT: A tuple (dist, pred). They are both dicts of dicts. The
        first indicates the length dist[u][v] of the shortest weighted path
        from u to v. The second is more complicated- it indicates the
        predecessor pred[u][v] of v in the shortest path from u to v.

        EXAMPLES::

            sage: G = Graph( { 0: {1: 1}, 1: {2: 1}, 2: {3: 1}, 3: {4: 2}, 4: {0: 2} }, sparse=True )
            sage: G.plot(edge_labels=True).show() # long time
            sage: dist, pred = G.shortest_path_all_pairs()
            sage: dist
            {0: {0: 0, 1: 1, 2: 2, 3: 3, 4: 2}, 1: {0: 1, 1: 0, 2: 1, 3: 2, 4: 3}, 2: {0: 2, 1: 1, 2: 0, 3: 1, 4: 3}, 3: {0: 3, 1: 2, 2: 1, 3: 0, 4: 2}, 4: {0: 2, 1: 3, 2: 3, 3: 2, 4: 0}}
            sage: pred
            {0: {0: None, 1: 0, 2: 1, 3: 2, 4: 0}, 1: {0: 1, 1: None, 2: 1, 3: 2, 4: 0}, 2: {0: 1, 1: 2, 2: None, 3: 2, 4: 3}, 3: {0: 1, 1: 2, 2: 3, 3: None, 4: 3}, 4: {0: 4, 1: 0, 2: 3, 3: 4, 4: None}}
            sage: pred[0]
            {0: None, 1: 0, 2: 1, 3: 2, 4: 0}

        So for example the shortest weighted path from 0 to 3 is obtained
        as follows. The predecessor of 3 is pred[0][3] == 2, the
        predecessor of 2 is pred[0][2] == 1, and the predecessor of 1 is
        pred[0][1] == 0.

        ::

            sage: G = Graph( { 0: {1:None}, 1: {2:None}, 2: {3: 1}, 3: {4: 2}, 4: {0: 2} }, sparse=True )
            sage: G.shortest_path_all_pairs(by_weight=False)
            ({0: {0: 0, 1: 1, 2: 2, 3: 2, 4: 1},
            1: {0: 1, 1: 0, 2: 1, 3: 2, 4: 2},
            2: {0: 2, 1: 1, 2: 0, 3: 1, 4: 2},
            3: {0: 2, 1: 2, 2: 1, 3: 0, 4: 1},
            4: {0: 1, 1: 2, 2: 2, 3: 1, 4: 0}},
            {0: {0: None, 1: 0, 2: 1, 3: 4, 4: 0},
            1: {0: 1, 1: None, 2: 1, 3: 2, 4: 0},
            2: {0: 1, 1: 2, 2: None, 3: 2, 4: 3},
            3: {0: 4, 1: 2, 2: 3, 3: None, 4: 3},
            4: {0: 4, 1: 0, 2: 3, 3: 4, 4: None}})
            sage: G.shortest_path_all_pairs()
            ({0: {0: 0, 1: 1, 2: 2, 3: 3, 4: 2},
            1: {0: 1, 1: 0, 2: 1, 3: 2, 4: 3},
            2: {0: 2, 1: 1, 2: 0, 3: 1, 4: 3},
            3: {0: 3, 1: 2, 2: 1, 3: 0, 4: 2},
            4: {0: 2, 1: 3, 2: 3, 3: 2, 4: 0}},
            {0: {0: None, 1: 0, 2: 1, 3: 2, 4: 0},
            1: {0: 1, 1: None, 2: 1, 3: 2, 4: 0},
            2: {0: 1, 1: 2, 2: None, 3: 2, 4: 3},
            3: {0: 1, 1: 2, 2: 3, 3: None, 4: 3},
            4: {0: 4, 1: 0, 2: 3, 3: 4, 4: None}})
            sage: G.shortest_path_all_pairs(default_weight=200)
            ({0: {0: 0, 1: 200, 2: 5, 3: 4, 4: 2},
            1: {0: 200, 1: 0, 2: 200, 3: 201, 4: 202},
            2: {0: 5, 1: 200, 2: 0, 3: 1, 4: 3},
            3: {0: 4, 1: 201, 2: 1, 3: 0, 4: 2},
            4: {0: 2, 1: 202, 2: 3, 3: 2, 4: 0}},
            {0: {0: None, 1: 0, 2: 3, 3: 4, 4: 0},
            1: {0: 1, 1: None, 2: 1, 3: 2, 4: 0},
            2: {0: 4, 1: 2, 2: None, 3: 2, 4: 3},
            3: {0: 4, 1: 2, 2: 3, 3: None, 4: 3},
            4: {0: 4, 1: 0, 2: 3, 3: 4, 4: None}})
        """
        from sage.rings.infinity import Infinity
        dist = {}
        pred = {}
        verts = self.vertices()
        for u in verts:
            dist[u] = {}
            pred[u] = {}
            for v in verts:
                if self.has_edge(u, v):
                    if by_weight is False:
                        dist[u][v] = 1
                    elif self.edge_label(u, v) is None or self.edge_label(u, v) == {}:
                        dist[u][v] = default_weight
                    else:
                        dist[u][v] = self.edge_label(u, v)
                    pred[u][v] = u
                else:
                    dist[u][v] = Infinity
                    pred[u][v] = None
            dist[u][u] = 0

        for w in verts:
            for u in verts:
                for v in verts:
                    if dist[u][v] > dist[u][w] + dist[w][v]:
                        dist[u][v] = dist[u][w] + dist[w][v]
                        pred[u][v] = pred[w][v]

        return dist, pred

    def wiener_index(self):
        r"""
        Returns the Wiener index of the graph.

        The Wiener index of a graph `G` can be defined in two equivalent
        ways [1] :

        - `W(G) = \frac 1 2 \sum_{u,v\in G} d(u,v)` where `d(u,v)` denotes the distance between
          vertices `u` and `v`.

        - Let `\Omega` be a set of `\frac {n(n-1)} 2` paths in `G` such that `\Omega`
          contains exactly one shortest `u-v` path for each set `\{u,v\}` of vertices
          in `G`. Besides, `\forall e\in E(G)`, let `\Omega(e)` denote the paths from `\Omega`
          containing `e`. We then have `W(G) = \sum_{e\in E(G)}|\Omega(e)|`.

        EXAMPLE:

        From [2], cited in [1]::

            sage: g=graphs.PathGraph(10)
            sage: w=lambda x: (x*(x*x -1)/6)
            sage: g.wiener_index()==w(10)
            True

        REFERENCE:

        [1] Klavzar S., Rajapakse A., Gutman I. (1996). The Szeged and the
        Wiener index of graphs. Applied Mathematics Letters, 9 (5), pp. 45-49.

        [2] I Gutman, YN Yeh, SL Lee, YL Luo (1993), Some recent results in
        the theory of the Wiener number. INDIAN JOURNAL OF CHEMISTRY SECTION A
        PUBLICATIONS & INFORMATION DIRECTORATE, CSIR
        """

        return sum([sum(v.itervalues()) for v in self.distance_all_pairs().itervalues()])/2

    def average_distance(self):
        r"""
        Returns the average distance between vertices of the graph.

        Formally, for a graph `G` this value is equal to
        `\frac 1 {n(n-1)} \sum_{u,v\in G} d(u,v)` where `d(u,v)`
        denotes the distance between vertices `u` and `v` and `n`
        is the number of vertices in `G`.

        EXAMPLE:

        From [GYLL93]_::

            sage: g=graphs.PathGraph(10)
            sage: w=lambda x: (x*(x*x -1)/6)/(x*(x-1)/2)
            sage: g.average_distance()==w(10)
            True

        REFERENCE:

        .. [GYLL93] I. Gutman, Y.-N. Yeh, S.-L. Lee, and Y.-L. Luo. Some recent
          results in the theory of the Wiener number. *Indian Journal of
          Chemistry*, 32A:651--661, 1993.
        """

        return Integer(self.wiener_index())/Integer((self.order()*(self.order()-1))/2)

    def szeged_index(self):
        r"""
        Returns the Szeged index of the graph.

        For any `uv\in E(G)`, let
        `N_u(uv) = \{w\in G:d(u,w)<d(v,w)\}, n_u(uv)=|N_u(uv)|`

        The Szeged index of a graph is then defined as [1]:
        `\sum_{uv \in E(G)}n_u(uv)\times n_v(uv)`

        EXAMPLE:

        True for any connected graph [1]::

            sage: g=graphs.PetersenGraph()
            sage: g.wiener_index()<= g.szeged_index()
            True

        True for all trees [1]::

            sage: g=Graph()
            sage: g.add_edges(graphs.CubeGraph(5).min_spanning_tree())
            sage: g.wiener_index() == g.szeged_index()
            True


        REFERENCE:

        [1] Klavzar S., Rajapakse A., Gutman I. (1996). The Szeged and the
        Wiener index of graphs. Applied Mathematics Letters, 9 (5), pp. 45-49.
        """
        distances=self.distance_all_pairs()
        s=0
        for (u,v) in self.edges(labels=None):
            du=distances[u]
            dv=distances[v]
            n1=n2=0
            for w in self:
                if du[w] < dv[w]:
                    n1+=1
                elif dv[w] < du[w]:
                    n2+=1
            s+=(n1*n2)
        return s

    ### Searches

    def breadth_first_search(self, start, ignore_direction=False,
                             distance=None, neighbors=None):
        """
        Returns an iterator over the vertices in a breadth-first ordering.

        INPUT:


        - ``start`` - vertex or list of vertices from which to start
          the traversal

        - ``ignore_direction`` - (default False) only applies to
          directed graphs. If True, searches across edges in either
          direction.

        - ``distance`` - the maximum distance from the ``start`` nodes
          to traverse.  The ``start`` nodes are distance zero from
          themselves.

        - ``neighbors`` - a function giving the neighbors of a vertex.
          The function should take a vertex and return a list of
          vertices.  For a graph, ``neighbors`` is by default the
          :meth:`.neighbors` function of the graph.  For a digraph,
          the ``neighbors`` function defaults to the
          :meth:`.successors` function of the graph.

        .. SEEALSO::

        - :meth:`breadth_first_search <sage.graphs.base.c_graph.CGraphBackend.breadth_first_search>`
          -- breadth-first search for fast compiled graphs.

        - :meth:`depth_first_search <sage.graphs.base.c_graph.CGraphBackend.depth_first_search>`
          -- depth-first search for fast compiled graphs.

        - :meth:`depth_first_search` -- depth-first search for generic graphs.

        EXAMPLES::

            sage: G = Graph( { 0: [1], 1: [2], 2: [3], 3: [4], 4: [0]} )
            sage: list(G.breadth_first_search(0))
            [0, 1, 4, 2, 3]

        By default, the edge direction of a digraph is respected, but this
        can be overridden by the ``ignore_direction`` parameter::

            sage: D = DiGraph( { 0: [1,2,3], 1: [4,5], 2: [5], 3: [6], 5: [7], 6: [7], 7: [0]})
            sage: list(D.breadth_first_search(0))
            [0, 1, 2, 3, 4, 5, 6, 7]
            sage: list(D.breadth_first_search(0, ignore_direction=True))
            [0, 1, 2, 3, 7, 4, 5, 6]

        You can specify a maximum distance in which to search.  A
        distance of zero returns the ``start`` vertices::

            sage: D = DiGraph( { 0: [1,2,3], 1: [4,5], 2: [5], 3: [6], 5: [7], 6: [7], 7: [0]})
            sage: list(D.breadth_first_search(0,distance=0))
            [0]
            sage: list(D.breadth_first_search(0,distance=1))
            [0, 1, 2, 3]

        Multiple starting vertices can be specified in a list::

            sage: D = DiGraph( { 0: [1,2,3], 1: [4,5], 2: [5], 3: [6], 5: [7], 6: [7], 7: [0]})
            sage: list(D.breadth_first_search([0]))
            [0, 1, 2, 3, 4, 5, 6, 7]
            sage: list(D.breadth_first_search([0,6]))
            [0, 6, 1, 2, 3, 7, 4, 5]
            sage: list(D.breadth_first_search([0,6],distance=0))
            [0, 6]
            sage: list(D.breadth_first_search([0,6],distance=1))
            [0, 6, 1, 2, 3, 7]
            sage: list(D.breadth_first_search(6,ignore_direction=True,distance=2))
            [6, 3, 7, 0, 5]

        More generally, you can specify a ``neighbors`` function.  For
        example, you can traverse the graph backwards by setting
        ``neighbors`` to be the :meth:`.predecessor` function of the graph::

            sage: D = DiGraph( { 0: [1,2,3], 1: [4,5], 2: [5], 3: [6], 5: [7], 6: [7], 7: [0]})
            sage: list(D.breadth_first_search(5,neighbors=D.neighbors_in, distance=2))
            [5, 1, 2, 0]
            sage: list(D.breadth_first_search(5,neighbors=D.neighbors_out, distance=2))
            [5, 7, 0]
            sage: list(D.breadth_first_search(5,neighbors=D.neighbors, distance=2))
            [5, 1, 2, 7, 0, 4, 6]


        TESTS::

            sage: D = DiGraph({1:[0], 2:[0]})
            sage: list(D.breadth_first_search(0))
            [0]
            sage: list(D.breadth_first_search(0, ignore_direction=True))
            [0, 1, 2]

        """
        # Preferably use the Cython implementation
        if neighbors is None and not isinstance(start,list) and distance is None and hasattr(self._backend,"breadth_first_search"):
            for v in self._backend.breadth_first_search(start, ignore_direction = ignore_direction):
                yield v
        else:
            if neighbors is None:
                if not self._directed or ignore_direction:
                    neighbors=self.neighbor_iterator
                else:
                    neighbors=self.neighbor_out_iterator
            seen=set([])
            if isinstance(start, list):
                queue=[(v,0) for v in start]
            else:
                queue=[(start,0)]

            for v,d in queue:
                yield v
                seen.add(v)

            while len(queue)>0:
                v,d = queue.pop(0)
                if distance is None or d<distance:
                    for w in neighbors(v):
                        if w not in seen:
                            seen.add(w)
                            queue.append((w, d+1))
                            yield w

    def depth_first_search(self, start, ignore_direction=False,
                           distance=None, neighbors=None):
        """
        Returns an iterator over the vertices in a depth-first ordering.

        INPUT:


        - ``start`` - vertex or list of vertices from which to start
          the traversal

        - ``ignore_direction`` - (default False) only applies to
          directed graphs. If True, searches across edges in either
          direction.

        - ``distance`` - the maximum distance from the ``start`` nodes
          to traverse.  The ``start`` nodes are distance zero from
          themselves.

        - ``neighbors`` - a function giving the neighbors of a vertex.
          The function should take a vertex and return a list of
          vertices.  For a graph, ``neighbors`` is by default the
          :meth:`.neighbors` function of the graph.  For a digraph,
          the ``neighbors`` function defaults to the
          :meth:`.successors` function of the graph.

        .. SEEALSO::

        - :meth:`breadth_first_search`

        - :meth:`breadth_first_search <sage.graphs.base.c_graph.CGraphBackend.breadth_first_search>`
          -- breadth-first search for fast compiled graphs.

        - :meth:`depth_first_search <sage.graphs.base.c_graph.CGraphBackend.depth_first_search>`
          -- depth-first search for fast compiled graphs.

        EXAMPLES::

            sage: G = Graph( { 0: [1], 1: [2], 2: [3], 3: [4], 4: [0]} )
            sage: list(G.depth_first_search(0))
            [0, 4, 3, 2, 1]

        By default, the edge direction of a digraph is respected, but this
        can be overridden by the ``ignore_direction`` parameter::


            sage: D = DiGraph( { 0: [1,2,3], 1: [4,5], 2: [5], 3: [6], 5: [7], 6: [7], 7: [0]})
            sage: list(D.depth_first_search(0))
            [0, 3, 6, 7, 2, 5, 1, 4]
            sage: list(D.depth_first_search(0, ignore_direction=True))
            [0, 7, 6, 3, 5, 2, 1, 4]

        You can specify a maximum distance in which to search.  A
        distance of zero returns the ``start`` vertices::

            sage: D = DiGraph( { 0: [1,2,3], 1: [4,5], 2: [5], 3: [6], 5: [7], 6: [7], 7: [0]})
            sage: list(D.depth_first_search(0,distance=0))
            [0]
            sage: list(D.depth_first_search(0,distance=1))
            [0, 3, 2, 1]

        Multiple starting vertices can be specified in a list::

            sage: D = DiGraph( { 0: [1,2,3], 1: [4,5], 2: [5], 3: [6], 5: [7], 6: [7], 7: [0]})
            sage: list(D.depth_first_search([0]))
            [0, 3, 6, 7, 2, 5, 1, 4]
            sage: list(D.depth_first_search([0,6]))
            [0, 3, 6, 7, 2, 5, 1, 4]
            sage: list(D.depth_first_search([0,6],distance=0))
            [0, 6]
            sage: list(D.depth_first_search([0,6],distance=1))
            [0, 3, 2, 1, 6, 7]
            sage: list(D.depth_first_search(6,ignore_direction=True,distance=2))
            [6, 7, 5, 0, 3]

        More generally, you can specify a ``neighbors`` function.  For
        example, you can traverse the graph backwards by setting
        ``neighbors`` to be the :meth:`.predecessor` function of the graph::

            sage: D = DiGraph( { 0: [1,2,3], 1: [4,5], 2: [5], 3: [6], 5: [7], 6: [7], 7: [0]})
            sage: list(D.depth_first_search(5,neighbors=D.neighbors_in, distance=2))
            [5, 2, 0, 1]
            sage: list(D.depth_first_search(5,neighbors=D.neighbors_out, distance=2))
            [5, 7, 0]
            sage: list(D.depth_first_search(5,neighbors=D.neighbors, distance=2))
            [5, 7, 6, 0, 2, 1, 4]

        TESTS::

            sage: D = DiGraph({1:[0], 2:[0]})
            sage: list(D.depth_first_search(0))
            [0]
            sage: list(D.depth_first_search(0, ignore_direction=True))
            [0, 2, 1]

        """
        # Preferably use the Cython implementation
        if neighbors is None and not isinstance(start,list) and  distance is None and hasattr(self._backend,"depth_first_search"):
            for v in self._backend.depth_first_search(start, ignore_direction = ignore_direction):
                yield v
        else:
            if neighbors is None:
                if not self._directed or ignore_direction:
                    neighbors=self.neighbor_iterator
                else:
                    neighbors=self.neighbor_out_iterator
            seen=set([])
            if isinstance(start, list):
                # Reverse the list so that the initial vertices come out in the same order
                queue=[(v,0) for v in reversed(start)]
            else:
                queue=[(start,0)]

            while len(queue)>0:
                v,d = queue.pop()
                if v not in seen:
                    yield v
                    seen.add(v)
                    if distance is None or d<distance:
                        for w in neighbors(v):
                            if w not in seen:
                                queue.append((w, d+1))

    def lex_BFS(self,reverse=False,tree=False, initial_vertex = None):
        r"""
        Performs a Lex BFS on the graph.

        A Lex BFS ( or Lexicographic Breadth-First Search ) is a Breadth
        First Search used for the recognition of Chordal Graphs. For more
        information, see the
        `Wikipedia article on Lex-BFS
        <http://en.wikipedia.org/wiki/Lexicographic_breadth-first_search>`_.

        INPUT:

        - ``reverse`` (boolean) -- whether to return the vertices
          in discovery order, or the reverse.

          ``False`` by default.

        - ``tree`` (boolean) -- whether to return the discovery
          directed tree (each vertex being linked to the one that
          saw it for the first time)

          ``False`` by default.

        - ``initial_vertex`` -- the first vertex to consider.

          ``None`` by default.

        ALGORITHM:

        This algorithm maintains for each vertex left in the graph
        a code corresponding to the vertices already removed. The
        vertex of maximal code ( according to the lexicographic
        order ) is then removed, and the codes are updated.

        This algorithm runs in time `O(n^2)` ( where `n` is the
        number of vertices in the graph ), which is not optimal.
        An optimal algorithm would run in time `O(m)` ( where `m`
        is the number of edges in the graph ), and require the use
        of a doubly-linked list which are not available in python
        and can not really be written efficiently. This could be
        done in Cython, though.

        EXAMPLE:

        A Lex BFS is obviously an ordering of the vertices::

            sage: g = graphs.PetersenGraph()
            sage: len(g.lex_BFS()) == g.order()
            True

        For a Chordal Graph, a reversed Lex BFS is a Perfect
        Elimination Order ::

            sage: g = graphs.PathGraph(3).lexicographic_product(graphs.CompleteGraph(2))
            sage: g.lex_BFS(reverse=True)
            [(2, 1), (2, 0), (1, 1), (1, 0), (0, 1), (0, 0)]


        And the vertices at the end of the tree of discovery are, for
        chordal graphs, simplicial vertices (their neighborhood is
        a complete graph)::

            sage: g = graphs.ClawGraph().lexicographic_product(graphs.CompleteGraph(2))
            sage: v = g.lex_BFS()[-1]
            sage: peo, tree = g.lex_BFS(initial_vertex = v,  tree=True)
            sage: leaves = [v for v in tree if tree.in_degree(v) ==0]
            sage: all([g.subgraph(g.neighbors(v)).is_clique() for v in leaves])
            True

        """
        id_inv = dict([(i,v) for (v,i) in zip(self.vertices(),range(self.order()))])
        code = [[] for i in range(self.order())]
        m = self.am()

        l = lambda x : code[x]
        vertices = set(range(self.order()))

        value = []
        pred = [-1]*self.order()

        add_element = (lambda y:value.append(id_inv[y])) if not reverse else (lambda y: value.insert(0,id_inv[y]))

        # Should we take care of the first vertex we pick ?
        first = True if initial_vertex is not None else False


        while vertices:

            if not first:
                v = max(vertices,key=l)
            else:
                v = self.vertices().index(initial_vertex)
                first = False

            vertices.remove(v)
            vector = m.column(v)
            for i in vertices:
                code[i].append(vector[i])
                if vector[i]:
                    pred[i] = v
            add_element(v)

        if tree:
            from sage.graphs.digraph import DiGraph
            g = DiGraph(sparse=True)
            edges = [(id_inv[i], id_inv[pred[i]]) for i in range(self.order()) if pred[i]!=-1]
            g.add_edges(edges)
            return value, g

        else:
            return value

    ### Constructors

    def add_cycle(self, vertices):
        """
        Adds a cycle to the graph with the given vertices. If the vertices
        are already present, only the edges are added.

        For digraphs, adds the directed cycle, whose orientation is
        determined by the list. Adds edges (vertices[u], vertices[u+1]) and
        (vertices[-1], vertices[0]).

        INPUT:

        -  ``vertices`` -- a list of indices for the vertices of
           the cycle to be added.


        EXAMPLES::

            sage: G = Graph()
            sage: G.add_vertices(range(10)); G
            Graph on 10 vertices
            sage: show(G)
            sage: G.add_cycle(range(20)[10:20])
            sage: show(G)
            sage: G.add_cycle(range(10))
            sage: show(G)

        ::

            sage: D = DiGraph()
            sage: D.add_cycle(range(4))
            sage: D.edges()
            [(0, 1, None), (1, 2, None), (2, 3, None), (3, 0, None)]
        """
        self.add_path(vertices)
        self.add_edge(vertices[-1], vertices[0])

    def add_path(self, vertices):
        """
        Adds a cycle to the graph with the given vertices. If the vertices
        are already present, only the edges are added.

        For digraphs, adds the directed path vertices[0], ...,
        vertices[-1].

        INPUT:


        -  ``vertices`` - a list of indices for the vertices of
           the cycle to be added.


        EXAMPLES::

            sage: G = Graph()
            sage: G.add_vertices(range(10)); G
            Graph on 10 vertices
            sage: show(G)
            sage: G.add_path(range(20)[10:20])
            sage: show(G)
            sage: G.add_path(range(10))
            sage: show(G)

        ::

            sage: D = DiGraph()
            sage: D.add_path(range(4))
            sage: D.edges()
            [(0, 1, None), (1, 2, None), (2, 3, None)]
        """
        vert1 = vertices[0]
        for v in vertices[1:]:
            self.add_edge(vert1, v)
            vert1 = v

    def complement(self):
        """
        Returns the complement of the (di)graph.

        The complement of a graph has the same vertices, but exactly those
        edges that are not in the original graph. This is not well defined
        for graphs with multiple edges.

        EXAMPLES::

            sage: P = graphs.PetersenGraph()
            sage: P.plot() # long time
            sage: PC = P.complement()
            sage: PC.plot() # long time

        ::

            sage: graphs.TetrahedralGraph().complement().size()
            0
            sage: graphs.CycleGraph(4).complement().edges()
            [(0, 2, None), (1, 3, None)]
            sage: graphs.CycleGraph(4).complement()
            complement(Cycle graph): Graph on 4 vertices
            sage: G = Graph(multiedges=True, sparse=True)
            sage: G.add_edges([(0,1)]*3)
            sage: G.complement()
            Traceback (most recent call last):
            ...
            TypeError: Complement not well defined for (di)graphs with multiple edges.
        """
        if self.has_multiple_edges():
            raise TypeError('Complement not well defined for (di)graphs with multiple edges.')
        from copy import copy
        G = copy(self)
        G.delete_edges(G.edges())
        G.name('complement(%s)'%self.name())
        for u in self:
            for v in self:
                if not self.has_edge(u,v):
                    G.add_edge(u,v)
        return G

    def line_graph(self, labels=True):
        """
        Returns the line graph of the (di)graph.

        The line graph of an undirected graph G is an undirected graph H
        such that the vertices of H are the edges of G and two vertices e
        and f of H are adjacent if e and f share a common vertex in G. In
        other words, an edge in H represents a path of length 2 in G.

        The line graph of a directed graph G is a directed graph H such
        that the vertices of H are the edges of G and two vertices e and f
        of H are adjacent if e and f share a common vertex in G and the
        terminal vertex of e is the initial vertex of f. In other words, an
        edge in H represents a (directed) path of length 2 in G.

        EXAMPLES::

            sage: g=graphs.CompleteGraph(4)
            sage: h=g.line_graph()
            sage: h.vertices()
            [(0, 1, None),
            (0, 2, None),
            (0, 3, None),
            (1, 2, None),
            (1, 3, None),
            (2, 3, None)]
            sage: h.am()
            [0 1 1 1 1 0]
            [1 0 1 1 0 1]
            [1 1 0 0 1 1]
            [1 1 0 0 1 1]
            [1 0 1 1 0 1]
            [0 1 1 1 1 0]
            sage: h2=g.line_graph(labels=False)
            sage: h2.vertices()
            [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
            sage: h2.am()==h.am()
            True
            sage: g = DiGraph([[1..4],lambda i,j: i<j])
            sage: h = g.line_graph()
            sage: h.vertices()
            [(1, 2, None),
            (1, 3, None),
            (1, 4, None),
            (2, 3, None),
            (2, 4, None),
            (3, 4, None)]
            sage: h.edges()
            [((1, 2, None), (2, 3, None), None),
             ((1, 2, None), (2, 4, None), None),
             ((1, 3, None), (3, 4, None), None),
             ((2, 3, None), (3, 4, None), None)]
        """
        if self._directed:
            from sage.graphs.digraph import DiGraph
            G=DiGraph()
            G.add_vertices(self.edges(labels=labels))
            for v in self:
                # Connect appropriate incident edges of the vertex v
                G.add_edges([(e,f) for e in self.incoming_edge_iterator(v, labels=labels) \
                             for f in self.outgoing_edge_iterator(v, labels=labels)])
            return G
        else:
            from sage.graphs.all import Graph
            G=Graph()
            # We must sort the edges' endpoints so that (1,2,None) is
            # seen as the same edge as (2,1,None).
            if labels:
                elist=[(min(i[0:2]),max(i[0:2]),i[2] if i[2] != {} else None)
                       for i in self.edge_iterator()]
            else:
                elist=[(min(i),max(i))
                       for i in self.edge_iterator(labels=False)]
            G.add_vertices(elist)
            for v in self:
                if labels:
                    elist=[(min(i[0:2]),max(i[0:2]),i[2] if i[2] != {} else None)
                           for i in self.edge_iterator(v)]
                else:
                    elist=[(min(i),max(i))
                           for i in self.edge_iterator(v, labels=False)]
                G.add_edges([(e, f) for e in elist for f in elist])
            return G

    def to_simple(self):
        """
        Returns a simple version of itself (i.e., undirected and loops and
        multiple edges are removed).

        EXAMPLES::

            sage: G = DiGraph(loops=True,multiedges=True,sparse=True)
            sage: G.add_edges( [ (0,0), (1,1), (2,2), (2,3,1), (2,3,2), (3,2) ] )
            sage: G.edges(labels=False)
            [(0, 0), (1, 1), (2, 2), (2, 3), (2, 3), (3, 2)]
            sage: H=G.to_simple()
            sage: H.edges(labels=False)
            [(2, 3)]
            sage: H.is_directed()
            False
            sage: H.allows_loops()
            False
            sage: H.allows_multiple_edges()
            False
        """
        g=self.to_undirected()
        g.allow_loops(False)
        g.allow_multiple_edges(False)
        return g

    def disjoint_union(self, other, verbose_relabel=True):
        """
        Returns the disjoint union of self and other.

        If the graphs have common vertices, the vertices will be renamed to
        form disjoint sets.

        INPUT:


        -  ``verbose_relabel`` - (defaults to True) If True
           and the graphs have common vertices, then each vertex v in the
           first graph will be changed to '0,v' and each vertex u in the
           second graph will be changed to '1,u'. If False, the vertices of
           the first graph and the second graph will be relabeled with
           consecutive integers.


        EXAMPLES::

            sage: G = graphs.CycleGraph(3)
            sage: H = graphs.CycleGraph(4)
            sage: J = G.disjoint_union(H); J
            Cycle graph disjoint_union Cycle graph: Graph on 7 vertices
            sage: J.vertices()
            [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (1, 3)]
            sage: J = G.disjoint_union(H, verbose_relabel=False); J
            Cycle graph disjoint_union Cycle graph: Graph on 7 vertices
            sage: J.vertices()
            [0, 1, 2, 3, 4, 5, 6]

        If the vertices are already disjoint and verbose_relabel is True,
        then the vertices are not relabeled.

        ::

            sage: G=Graph({'a': ['b']})
            sage: G.name("Custom path")
            sage: G.name()
            'Custom path'
            sage: H=graphs.CycleGraph(3)
            sage: J=G.disjoint_union(H); J
            Custom path disjoint_union Cycle graph: Graph on 5 vertices
            sage: J.vertices()
            [0, 1, 2, 'a', 'b']
        """
        if (self._directed and not other._directed) or (not self._directed and other._directed):
            raise TypeError('Both arguments must be of the same class.')

        if not verbose_relabel:
            r_self = {}; r_other = {}; i = 0
            for v in self:
                r_self[v] = i; i += 1
            for v in other:
                r_other[v] = i; i += 1
            G = self.relabel(r_self, inplace=False).union(other.relabel(r_other, inplace=False))
        elif any(u==v for u in self for v in other):
            r_self = dict([[v,(0,v)] for v in self])
            r_other = dict([[v,(1,v)] for v in other])
            G = self.relabel(r_self, inplace=False).union(other.relabel(r_other, inplace=False))
        else:
            G = self.union(other)

        G.name('%s disjoint_union %s'%(self.name(), other.name()))
        return G

    def union(self, other):
        """
        Returns the union of self and other.

        If the graphs have common vertices, the common vertices will be
        identified.

        EXAMPLES::

            sage: G = graphs.CycleGraph(3)
            sage: H = graphs.CycleGraph(4)
            sage: J = G.union(H); J
            Graph on 4 vertices
            sage: J.vertices()
            [0, 1, 2, 3]
            sage: J.edges(labels=False)
            [(0, 1), (0, 2), (0, 3), (1, 2), (2, 3)]
        """
        if (self._directed and not other._directed) or (not self._directed and other._directed):
            raise TypeError('Both arguments must be of the same class.')
        if self._directed:
            from sage.graphs.all import DiGraph
            G = DiGraph()
        else:
            from sage.graphs.all import Graph
            G = Graph()
        G.add_vertices(self.vertices())
        G.add_vertices(other.vertices())
        G.add_edges(self.edges())
        G.add_edges(other.edges())
        return G

    def cartesian_product(self, other):
        """
        Returns the Cartesian product of self and other.

        The Cartesian product of `G` and `H` is the graph `L` with vertex set
        `V(L)` equal to the Cartesian product of the vertices `V(G)` and `V(H)`,
        and `((u,v), (w,x))` is an edge iff either - `(u, w)` is an edge of
        self and `v = x`, or - `(v, x)` is an edge of other and `u = w`.

        EXAMPLES::

            sage: Z = graphs.CompleteGraph(2)
            sage: C = graphs.CycleGraph(5)
            sage: P = C.cartesian_product(Z); P
            Graph on 10 vertices
            sage: P.plot() # long time

        ::

            sage: D = graphs.DodecahedralGraph()
            sage: P = graphs.PetersenGraph()
            sage: C = D.cartesian_product(P); C
            Graph on 200 vertices
            sage: C.plot() # long time
        """
        if (self._directed and not other._directed) or (not self._directed and other._directed):
            raise TypeError('Both arguments must be of the same class.')
        if self._directed:
            from sage.graphs.all import DiGraph
            G = DiGraph()
        else:
            from sage.graphs.all import Graph
            G = Graph()
        verts = []
        for a in self.vertices():
            for b in other.vertices():
                G.add_vertex((a,b))
                verts.append((a,b))
        for i in range(len(verts)):
            for j in range(i):
                u,v = verts[i]
                w,x = verts[j]
                if (self.has_edge(u, w) and v == x) or (other.has_edge(v, x) and u == w):
                    G.add_edge((u,v), (w,x))
        return G

    def tensor_product(self, other):
        """
        Returns the tensor product, also called the categorical product, of
        self and other.

        The tensor product of `G` and `H` is the graph `L` with vertex set `V(L)`
        equal to the Cartesian product of the vertices `V(G)` and `V(H)`, and
        `((u,v), (w,x))` is an edge iff - `(u, w)` is an edge of self, and -
        `(v, x)` is an edge of other.

        EXAMPLES::

            sage: Z = graphs.CompleteGraph(2)
            sage: C = graphs.CycleGraph(5)
            sage: T = C.tensor_product(Z); T
            Graph on 10 vertices
            sage: T.plot() # long time

        ::

            sage: D = graphs.DodecahedralGraph()
            sage: P = graphs.PetersenGraph()
            sage: T = D.tensor_product(P); T
            Graph on 200 vertices
            sage: T.plot() # long time
        """
        if (self._directed and not other._directed) or (not self._directed and other._directed):
            raise TypeError('Both arguments must be of the same class.')
        if self._directed:
            from sage.graphs.all import DiGraph
            G = DiGraph()
        else:
            from sage.graphs.all import Graph
            G = Graph()
        verts = []
        for a in self.vertices():
            for b in other.vertices():
                G.add_vertex((a,b))
                verts.append((a,b))
        for i in range(len(verts)):
            for j in range(i):
                u,v = verts[i]
                w,x = verts[j]
                if self.has_edge(u, w) and other.has_edge(v, x):
                    G.add_edge((u,v), (w,x))
        return G

    categorical_product = tensor_product

    def lexicographic_product(self, other):
        """
        Returns the lexicographic product of self and other.

        The lexicographic product of G and H is the graph L with vertex set
        V(L) equal to the Cartesian product of the vertices V(G) and V(H),
        and ((u,v), (w,x)) is an edge iff - (u, w) is an edge of self, or -
        u = w and (v, x) is an edge of other.

        EXAMPLES::

            sage: Z = graphs.CompleteGraph(2)
            sage: C = graphs.CycleGraph(5)
            sage: L = C.lexicographic_product(Z); L
            Graph on 10 vertices
            sage: L.plot() # long time

        ::

            sage: D = graphs.DodecahedralGraph()
            sage: P = graphs.PetersenGraph()
            sage: L = D.lexicographic_product(P); L
            Graph on 200 vertices
            sage: L.plot() # long time
        """
        if (self._directed and not other._directed) or (not self._directed and other._directed):
            raise TypeError('Both arguments must be of the same class.')
        if self._directed:
            from sage.graphs.all import DiGraph
            G = DiGraph()
        else:
            from sage.graphs.all import Graph
            G = Graph()
        verts = []
        for a in self.vertices():
            for b in other.vertices():
                G.add_vertex((a,b))
                verts.append((a,b))
        for i in range(len(verts)):
            for j in range(i):
                u,v = verts[i]
                w,x = verts[j]
                if self.has_edge(u, w) or (u == w and other.has_edge(v, x)):
                    G.add_edge((u,v), (w,x))
        return G

    def strong_product(self, other):
        """
        Returns the strong product of self and other.

        The strong product of G and H is the graph L with vertex set V(L)
        equal to the Cartesian product of the vertices V(G) and V(H), and
        ((u,v), (w,x)) is an edge iff either - (u, w) is an edge of self
        and v = x, or - (v, x) is an edge of other and u = w, or - (u, w)
        is an edge of self and (v, x) is an edge of other. In other words,
        the edges of the strong product is the union of the edges of the
        tensor and Cartesian products.

        EXAMPLES::

            sage: Z = graphs.CompleteGraph(2)
            sage: C = graphs.CycleGraph(5)
            sage: S = C.strong_product(Z); S
            Graph on 10 vertices
            sage: S.plot() # long time

        ::

            sage: D = graphs.DodecahedralGraph()
            sage: P = graphs.PetersenGraph()
            sage: S = D.strong_product(P); S
            Graph on 200 vertices
            sage: S.plot() # long time
        """
        if (self._directed and not other._directed) or (not self._directed and other._directed):
            raise TypeError('Both arguments must be of the same class.')
        if self._directed:
            from sage.graphs.all import DiGraph
            G = DiGraph()
        else:
            from sage.graphs.all import Graph
            G = Graph()

        verts = []
        for a in self.vertices():
            for b in other.vertices():
                G.add_vertex((a,b))
                verts.append((a,b))
        for i in range(len(verts)):
            for j in range(i):
                u,v = verts[i]
                w,x = verts[j]
                if (self.has_edge(u, w) and v == x) or \
                   (other.has_edge(v, x) and u == w) or \
                   (self.has_edge(u, w) and other.has_edge(v, x)):
                    G.add_edge((u,v), (w,x))
        return G

    def disjunctive_product(self, other):
        """
        Returns the disjunctive product of self and other.

        The disjunctive product of G and H is the graph L with vertex set
        V(L) equal to the Cartesian product of the vertices V(G) and V(H),
        and ((u,v), (w,x)) is an edge iff either - (u, w) is an edge of
        self, or - (v, x) is an edge of other.

        EXAMPLES::

            sage: Z = graphs.CompleteGraph(2)
            sage: D = Z.disjunctive_product(Z); D
            Graph on 4 vertices
            sage: D.plot() # long time

        ::

            sage: C = graphs.CycleGraph(5)
            sage: D = C.disjunctive_product(Z); D
            Graph on 10 vertices
            sage: D.plot() # long time
        """
        if (self._directed and not other._directed) or (not self._directed and other._directed):
            raise TypeError('Both arguments must be of the same class.')
        if self._directed:
            from sage.graphs.all import DiGraph
            G = DiGraph()
        else:
            from sage.graphs.all import Graph
            G = Graph()
        verts = []
        for a in self.vertices():
            for b in other.vertices():
                G.add_vertex((a,b))
                verts.append((a,b))
        for i in range(len(verts)):
            for j in range(i):
                u,v = verts[i]
                w,x = verts[j]
                if self.has_edge(u, w) or other.has_edge(v, x):
                    G.add_edge((u,v), (w,x))
        return G

    def transitive_closure(self):
        r"""
        Computes the transitive closure of a graph and returns it. The
        original graph is not modified.

        The transitive closure of a graph G has an edge (x,y) if and only
        if there is a path between x and y in G.

        The transitive closure of any strongly connected component of a
        graph is a complete graph. In particular, the transitive closure of
        a connected undirected graph is a complete graph. The transitive
        closure of a directed acyclic graph is a directed acyclic graph
        representing the full partial order.

        EXAMPLES::

            sage: g=graphs.PathGraph(4)
            sage: g.transitive_closure()
            Transitive closure of Path Graph: Graph on 4 vertices
            sage: g.transitive_closure()==graphs.CompleteGraph(4)
            True
            sage: g=DiGraph({0:[1,2], 1:[3], 2:[4,5]})
            sage: g.transitive_closure().edges(labels=False)
            [(0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (1, 3), (2, 4), (2, 5)]

        """
        from copy import copy
        G = copy(self)
        G.name('Transitive closure of ' + self.name())
        for v in G:
            # todo optimization opportunity: we are adding edges that
            # are already in the graph and we are adding edges
            # one at a time.
            for e in G.breadth_first_search(v):
                G.add_edge((v,e))
        return G

    def transitive_reduction(self):
        r"""
        Returns a transitive reduction of a graph. The original graph is
        not modified.

        A transitive reduction H of G has a path from x to y if and only if
        there was a path from x to y in G. Deleting any edge of H destroys
        this property. A transitive reduction is not unique in general. A
        transitive reduction has the same transitive closure as the
        original graph.

        A transitive reduction of a complete graph is a tree. A transitive
        reduction of a tree is itself.

        EXAMPLES::

            sage: g=graphs.PathGraph(4)
            sage: g.transitive_reduction()==g
            True
            sage: g=graphs.CompleteGraph(5)
            sage: edges = g.transitive_reduction().edges(); len(edges)
            4
            sage: g=DiGraph({0:[1,2], 1:[2,3,4,5], 2:[4,5]})
            sage: g.transitive_reduction().size()
            5
        """
        from copy import copy
        from sage.rings.infinity import Infinity
        G = copy(self)
        for e in self.edge_iterator():
            # Try deleting the edge, see if we still have a path
            # between the vertices.
            G.delete_edge(e)
            if G.distance(e[0],e[1])==Infinity:
                # oops, we shouldn't have deleted it
                G.add_edge(e)
        return G

    def is_transitively_reduced(self):
        r"""
        Returns True if the digraph is transitively reduced and False
        otherwise.

        A digraph is transitively reduced if it is equal to its transitive
        reduction.

        EXAMPLES::

            sage: d = DiGraph({0:[1],1:[2],2:[3]})
            sage: d.is_transitively_reduced()
            True

            sage: d = DiGraph({0:[1,2],1:[2]})
            sage: d.is_transitively_reduced()
            False

            sage: d = DiGraph({0:[1,2],1:[2],2:[]})
            sage: d.is_transitively_reduced()
            False
        """
        from copy import copy
        from sage.rings.infinity import Infinity
        G = copy(self)
        for e in self.edge_iterator():
            G.delete_edge(e)
            if G.distance(e[0],e[1]) == Infinity:
                G.add_edge(e)
            else:
                return False
        return True


    ### Visualization

    def _color_by_label(self, format='hex'):
        """
        Logic for coloring by label (factored out from plot() for use in 3d
        plots, etc)

        EXAMPLES::

            sage: G = SymmetricGroup(4).cayley_graph()
            sage: G.num_edges()
            72
            sage: G._color_by_label()
            {'#00ff00': [((1,4,3,2), (1,4,3), 1), ... ((1,2)(3,4), (3,4),     1)],
             '#ff0000': [((1,4,3,2), (1,4,2), 2), ... ((1,2)(3,4), (1,3,4,2), 2)],
             '#0000ff': [((1,4,3,2), (1,3,2), 3), ... ((1,2)(3,4), (1,2),     3)]}
        """
        from sage.plot.colors import rainbow
        edge_labels = []
        for e in self.edge_iterator():
            i = 0
            while i < len(edge_labels):
                if not edge_labels[i][0][2] == e[2]:
                    i += 1
                else:
                    edge_labels[i].append(e)
                    break
            if i == len(edge_labels):
                edge_labels.append([e])
        num_labels = len(edge_labels)
        r = rainbow(num_labels, format=format)
        edge_colors = {}
        for i in range(num_labels):
            edge_colors[r[i]] = edge_labels[i]
        return edge_colors

    def latex_options(self):
        r"""
        Returns an instance of
        :class:`~sage.graphs.graph_latex.GraphLatex` for the graph.

        Changes to this object will affect the `\mbox{\rm\LaTeX}`
        version of the graph.

        EXAMPLES::

            sage: g = graphs.PetersenGraph()
            sage: opts = g.latex_options()
            sage: opts
            LaTeX options for Petersen graph: {}
            sage: opts.set_option('tkz_style', 'Classic')
            sage: opts
            LaTeX options for Petersen graph: {'tkz_style': 'Classic'}
        """
        if self._latex_opts is None:
            from sage.graphs.graph_latex import GraphLatex
            self._latex_opts = GraphLatex(self)
        return self._latex_opts

    def set_latex_options(self, **kwds):
        r"""
        Sets multiple options for rendering a graph with LaTeX.

        INPUTS:

        - ``kwds`` - any number of option/value pairs to set many graph
          latex options at once (a variable number, in any
          order). Existing values are overwritten, new values are
          added.  Existing values can be cleared by setting the value
          to ``None``.  Possible options are documented at
          :meth:`sage.graphs.graph_latex.GraphLatex.set_option`.

        This method is a convenience for setting the options of a graph
        directly on an instance of the graph.  For details, or finer control,
        see the :class:`~sage.graphs.graph_latex.GraphLatex` class.

        EXAMPLES::

            sage: g = graphs.PetersenGraph()
            sage: g.set_latex_options(tkz_style = 'Welsh')
            sage: opts = g.latex_options()
            sage: opts.get_option('tkz_style')
            'Welsh'
        """
        opts = self.latex_options()
        opts.set_options(**kwds)


    def layout(self, layout = None, pos = None, dim = 2, save_pos = False, **options):
        """
        Returns a layout for the vertices of this graph.

        INPUT:

         - layout -- one of "acyclic", "circular", "ranked", "graphviz", "planar", "spring", or "tree"

         - pos -- a dictionary of positions or None (the default)

         - save_pos -- a boolean

         - layout options -- (see below)

        If ``layout=algorithm`` is specified, this algorithm is used
        to compute the positions.

        Otherwise, if ``pos`` is specified, use the given positions.

        Otherwise, try to fetch previously computed and saved positions.

        Otherwise use the default layout (usually the spring layout)

        If ``save_pos = True``, the layout is saved for later use.

        EXAMPLES::

            sage: g = digraphs.ButterflyGraph(1)
            sage: g.layout()
            {('1', 1): [2.50..., -0.545...],
             ('0', 0): [2.22..., 0.832...],
             ('1', 0): [1.12..., -0.830...],
             ('0', 1): [0.833..., 0.543...]}

            sage: 1+1
            2
            sage: x = g.layout(layout = "acyclic_dummy", save_pos = True)
            sage: x =  {('1', 1): [41, 18], ('0', 0): [41, 90], ('1', 0): [140, 90], ('0', 1): [141, 18]}

            {('1', 1): [41, 18], ('0', 0): [41, 90], ('1', 0): [140, 90], ('0', 1): [141, 18]}


            sage: g.layout(dim = 3)
            {('1', 1): [1.07..., -0.260..., 0.927...],
             ('0', 0): [2.02..., 0.528..., 0.343...],
             ('1', 0): [0.674..., -0.528..., -0.343...],
             ('0', 1): [1.61..., 0.260..., -0.927...]}

        Here is the list of all the available layout options::

            sage: from sage.graphs.graph_plot import layout_options
            sage: list(sorted(layout_options.iteritems()))
            [('by_component', 'Whether to do the spring layout by connected component -- a boolean.'),
             ('dim', 'The dimension of the layout -- 2 or 3.'),
             ('heights', 'A dictionary mapping heights to the list of vertices at this height.'),
             ('iterations', 'The number of times to execute the spring layout algorithm.'),
             ('layout', 'A layout algorithm -- one of "acyclic", "circular", "ranked", "graphviz", "planar", "spring", or "tree".'),
             ('prog', 'Which graphviz layout program to use -- one of "circo", "dot", "fdp", "neato", or "twopi".'),
             ('save_pos', 'Whether or not to save the computed position for the graph.'),
             ('spring', 'Use spring layout to finalize the current layout.'),
             ('tree_orientation', 'The direction of tree branches -- "up" or "down".'),
             ('tree_root', 'A vertex designation for drawing trees.')]

        Some of them only apply to certain layout algorithms. For
        details, see :meth:`.layout_acyclic`, :meth:`.layout_planar`,
        :meth:`.layout_circular`, :meth:`.layout_spring`, ...

        ..warning: unknown optional arguments are silently ignored

        ..warning: ``graphviz`` and ``dot2tex`` are currently required
        to obtain a nice 'acyclic' layout. See
        :meth:`.layout_graphviz` for installation instructions.

        A subclass may implement another layout algorithm `blah`, by
        implementing a method :meth:`.layout_blah`. It may override
        the default layout by overriding :meth:`.layout_default`, and
        similarly override the predefined layouts.

        TODO: use this feature for all the predefined graphs classes
        (like for the Petersen graph, ...), rather than systematically
        building the layout at construction time.
        """
        if layout is None:
            if pos is None:
                pos = self.get_pos(dim = dim)
            if pos is None:
                layout = 'default'

        if hasattr(self, "layout_%s"%layout):
            pos = getattr(self, "layout_%s"%layout)(dim = dim, **options)
        elif layout is not None:
            raise ValueError, "unknown layout algorithm: %s"%layout

        if len(pos) < self.order():
            pos = self.layout_extend_randomly(pos, dim = dim)

        if save_pos:
            self.set_pos(pos, dim = dim)
        return pos


    def layout_spring(self, by_component = True, **options):
        """
        Computes a spring layout for this graph

        INPUT:

         - ``iterations`` -- a positive integer
         - ``dim`` -- 2 or 3 (default: 2)

        OUTPUT: a dictionary mapping vertices to positions

        Returns a layout computed by randomly arranging the vertices
        along the given heights

        EXAMPLES::

            sage: g = graphs.LadderGraph(3) #TODO!!!!
            sage: g.layout_spring()
            {0: [1.28..., -0.943...],
             1: [1.57..., -0.101...],
             2: [1.83..., 0.747...],
             3: [0.531..., -0.757...],
             4: [0.795..., 0.108...],
             5: [1.08..., 0.946...]}
            sage: g = graphs.LadderGraph(7)
            sage: g.plot(layout = "spring")
        """
        return spring_layout_fast(self, by_component = by_component, **options)

    layout_default = layout_spring

#     if not isinstance(graph.get_pos(), dict):
#         if graph.is_planar():
#             graph.set_planar_positions()
#         else:
#             import sage.graphs.generic_graph_pyx as ggp
#             graph.set_pos(ggp.spring_layout_fast_split(graph, iterations=1000))

    def layout_ranked(self, heights = None, dim = 2, spring = False, **options):
        """
        Computes a ranked layout for this graph

        INPUT:

         - heights -- a dictionary mapping heights to the list of vertices at this height

        OUTPUT: a dictionary mapping vertices to positions

        Returns a layout computed by randomly arranging the vertices
        along the given heights

        EXAMPLES::

            sage: g = graphs.LadderGraph(3)
            sage: g.layout_ranked(heights = dict( (i,[i, i+3]) for i in range(3) ))
            {0: [0.668..., 0],
             1: [0.667..., 1],
             2: [0.677..., 2],
             3: [1.34..., 0],
             4: [1.33..., 1],
             5: [1.33..., 2]}
            sage: g = graphs.LadderGraph(7)
            sage: g.plot(layout = "ranked", heights = dict( (i,[i, i+7]) for i in range(7) ))
        """
        assert heights is not None

        from sage.misc.randstate import current_randstate
        random = current_randstate().python_random().random

        if self.order() == 0:
            return {}

        pos = {}
        mmax = max([len(ccc) for ccc in heights.values()])
        ymin = min(heights.keys())
        ymax = max(heights.keys())
        dist = ((ymax-ymin)/(mmax+1.0))
        for height in heights:
            num_xs = len(heights[height])
            if num_xs == 0:
                continue
            j = (mmax - num_xs)/2.0
            for k in range(num_xs):
                pos[heights[height][k]] = [ dist*(j+k+1) + random()*(dist*0.03) for i in range(dim-1) ] + [height]
        if spring:
            # This does not work that well in 2d, since the vertices on
            # the same level are unlikely to cross. It is also hard to
            # set a good equilibrium distance (parameter k in
            # run_spring). If k<1, the layout gets squished
            # horizontally.  If k>1, then two adjacent vertices in
            # consecutive levels tend to be further away than desired.
            newpos = spring_layout_fast(self,
                                        vpos = pos,
                                        dim = dim,
                                        height = True,
                                        **options)
            # spring_layout_fast actually *does* touch the last coordinates
            # (conversion to floats + translation)
            # We restore back the original height.
            for x in self.vertices():
                newpos[x][dim-1] = pos[x][dim-1]
            pos = newpos
        return pos

    def layout_extend_randomly(self, pos, dim = 2):
        """
        Extends randomly a partial layout

        INPUT:

         - ``pos``: a dictionary mapping vertices to positions

        OUTPUT: a dictionary mapping vertices to positions

        The vertices not referenced in ``pos`` are assigned random
        positions within the box delimited by the other vertices.

        EXAMPLES::

            sage: H = digraphs.ButterflyGraph(1)
            sage: H.layout_extend_randomly({('0',0): (0,0), ('1',1): (1,1)})
            {('1', 1): (1, 1),
             ('0', 0): (0, 0),
             ('1', 0): [0.111..., 0.514...],
             ('0', 1): [0.0446..., 0.332...]}
        """
        assert dim == 2 # 3d not yet implemented
        from sage.misc.randstate import current_randstate
        random = current_randstate().python_random().random

        xmin, xmax,ymin, ymax = self._layout_bounding_box(pos)

        dx = xmax - xmin
        dy = ymax - ymin
        # Check each vertex position is in pos, add position
        # randomly within the plot range if none is defined
        for v in self:
            if not v in pos:
                pos[v] = [xmin + dx*random(), ymin + dy*random()]
        return pos


    def layout_circular(self, dim = 2, **options):
        """
        Computes a circular layout for this graph

        OUTPUT: a dictionary mapping vertices to positions

        EXAMPLES::

            sage: G = graphs.CirculantGraph(7,[1,3])
            sage: G.layout_circular()
            {0: [6.12...e-17, 1.0],
             1: [-0.78...,  0.62...],
             2: [-0.97..., -0.22...],
             3: [-0.43..., -0.90...],
             4: [0.43...,  -0.90...],
             5: [0.97...,  -0.22...],
             6: [0.78...,   0.62...]}
            sage: G.plot(layout = "circular")
        """
        assert dim == 2, "3D circular layout not implemented"
        from math import sin, cos, pi
        verts = self.vertices()
        n = len(verts)
        pos = {}
        for i in range(n):
            x = float(cos((pi/2) + ((2*pi)/n)*i))
            y = float(sin((pi/2) + ((2*pi)/n)*i))
            pos[verts[i]] = [x,y]
        return pos

    def layout_tree(self, tree_orientation = "down", tree_root = None, dim = 2, **options):
        """
        Computes an ordered tree layout for this graph, which should
        be a tree (no non oriented cycles).

        INPUT:

         - ``tree_root`` -- a vertex
         - ``tree_orientation`` -- "up" or "down"

        OUTPUT: a dictionary mapping vertices to positions

        EXAMPLES::

            sage: G = graphs.BalancedTree(2,2)
            sage: G.layout_tree(tree_root = 0)
            {0: [1.0..., 2],
             1: [0.8..., 1],
             2: [1.2..., 1],
             3: [0.4..., 0],
             4: [0.8..., 0],
             5: [1.2..., 0],
             6: [1.6..., 0]}
            sage: G = graphs.BalancedTree(2,4)
            sage: G.plot(layout="tree", tree_root = 0, tree_orientation = "up")
        """
        assert dim == 2, "3D tree layout not implemented"
        if not self.is_tree():
            raise RuntimeError("Cannot use tree layout on this graph: self.is_tree() returns False.")
        n = self.order()
        vertices = self.vertices()
        if tree_root is None:
            from sage.misc.prandom import randrange
            root = vertices[randrange(n)]
        else:
            root = tree_root
        # BFS search for heights
        seen = [root]
        queue = [root]
        heights = [-1]*n
        heights[vertices.index(root)] = 0
        while queue:
            u = queue.pop(0)
            for v in self.neighbors(u):
                if v not in seen:
                    seen.append(v)
                    queue.append(v)
                    heights[vertices.index(v)] = heights[vertices.index(u)] + 1
        if tree_orientation == 'down':
            maxx = max(heights)
            heights = [maxx-heights[i] for i in xrange(n)]
        heights_dict = {}
        for v in vertices:
            if not heights_dict.has_key(heights[vertices.index(v)]):
                heights_dict[heights[vertices.index(v)]] = [v]
            else:
                heights_dict[heights[vertices.index(v)]].append(v)

        return self.layout_ranked(heights_dict)

    def layout_graphviz(self, dim = 2, prog = 'dot', **options):
        """
        Calls ``graphviz`` to compute a layout of the vertices of this graph.

        INPUT:

         - ``prog`` -- one of "dot", "neato", "twopi", "circo", or "fdp"

        EXAMPLES::

            sage: g = digraphs.ButterflyGraph(2)
            sage: g.layout_graphviz() # optional - dot2tex, graphviz
            {('00', 0): [...,...],
             ('00', 1): [...,...],
             ('00', 2): [...,...],
             ('01', 0): [...,...],
             ('01', 1): [...,...],
             ('01', 2): [...,...],
             ('10', 0): [...,...],
             ('10', 1): [...,...],
             ('10', 2): [...,...],
             ('11', 0): [...,...],
             ('11', 1): [...,...],
             ('11', 2): [...,...]}
            sage: g.plot(layout = "graphviz") # optional - dot2tex, graphviz

        Note: the actual coordinates are not deterministic

        By default, an acyclic layout is computed using ``graphviz``'s
        ``dot`` layout program. One may specify an alternative layout
        program::

            sage: g.plot(layout = "graphviz", prog = "dot")   # optional - dot2tex, graphviz
            sage: g.plot(layout = "graphviz", prog = "neato") # optional - dot2tex, graphviz
            sage: g.plot(layout = "graphviz", prog = "twopi") # optional - dot2tex, graphviz
            sage: g.plot(layout = "graphviz", prog = "fdp")   # optional - dot2tex, graphviz
            sage: g = graphs.BalancedTree(5,2)
            sage: g.plot(layout = "graphviz", prog = "circo") # optional - dot2tex, graphviz

        TODO: put here some cool examples showcasing graphviz features.

        This requires ``graphviz`` and the ``dot2tex`` spkg. Here are
        some installation tips:

         - Install graphviz >= 2.14 so that the programs dot, neato, ...
           are in your path. The graphviz suite can be download from
           http://graphviz.org.

         - Download dot2tex-2.8.?.spkg from http://trac.sagemath.org/sage_trac/ticket/7004
           and install it with ``sage -i dot2tex-2.8.?.spkg``

        TODO: use the graphviz functionality of Networkx 1.0 once it
        will be merged into Sage.
        """
        assert_have_dot2tex()
        assert dim == 2, "3D graphviz layout not implemented"

        key = self._keys_for_vertices()
        key_to_vertex = dict( (key(v), v) for v in self )

        import dot2tex
        positions = dot2tex.dot2tex(self.graphviz_string(), format = "positions", prog = prog)

        return dict( (key_to_vertex[key], pos) for (key, pos) in positions.iteritems() )

    def _layout_bounding_box(self, pos):
        """
        INPUT:

         - pos -- a dictionary of positions

        Returns a bounding box around the specified positions

        EXAMPLES::

            sage: Graph()._layout_bounding_box( {} )
            [-1, 1, -1, 1]
            sage: Graph()._layout_bounding_box( {0: [3,5], 1: [2,7], 2: [-4,2] } )
            [-4, 3, 2, 7]
            sage: Graph()._layout_bounding_box( {0: [3,5], 1: [3.00000000001,4.999999999999999] } )
            [2, 4.00000000001000, 4.00000000000000, 6]
        """
        xs = [pos[v][0] for v in pos]
        ys = [pos[v][1] for v in pos]
        if len(xs) == 0:
            xmin = -1
            xmax =  1
            ymin = -1
            ymax =  1
        else:
            xmin = min(xs)
            xmax = max(xs)
            ymin = min(ys)
            ymax = max(ys)

        if xmax - xmin < 0.00000001:
            xmax += 1
            xmin -= 1

        if ymax - ymin < 0.00000001:
            ymax += 1
            ymin -= 1

        return [xmin, xmax, ymin, ymax]



    @options(vertex_size=200, vertex_labels=True, layout=None,
            edge_style='solid', edge_colors='black', edge_labels=False,
            iterations=50, tree_orientation='down', heights=None, graph_border=False,
            talk=False, color_by_label=False, partition=None,
            dist = .075, max_dist=1.5, loop_size=.075)
    def graphplot(self, **options):
        """
        Returns a GraphPlot object.


        EXAMPLES:

        Creating a graphplot object uses the same options as graph.plot()::

            sage: g = Graph({}, loops=True, multiedges=True, sparse=True)
            sage: g.add_edges([(0,0,'a'),(0,0,'b'),(0,1,'c'),(0,1,'d'),
            ...     (0,1,'e'),(0,1,'f'),(0,1,'f'),(2,1,'g'),(2,2,'h')])
            sage: g.set_boundary([0,1])
            sage: GP = g.graphplot(edge_labels=True, color_by_label=True, edge_style='dashed')
            sage: GP.plot()

        We can modify the graphplot object.  Notice that the changes are cumulative::

            sage: GP.set_edges(edge_style='solid')
            sage: GP.plot()
            sage: GP.set_vertices(talk=True)
            sage: GP.plot()
        """
        from sage.graphs.graph_plot import GraphPlot
        return GraphPlot(graph=self, options=options)

    @options(vertex_size=200, vertex_labels=True, layout=None,
            edge_style='solid', edge_colors='black', edge_labels=False,
            iterations=50, tree_orientation='down', heights=None, graph_border=False,
            talk=False, color_by_label=False, partition=None,
            dist = .075, max_dist=1.5, loop_size=.075)
    def plot(self, **options):
        r"""
        Returns a graphics object representing the (di)graph.
        See also the :mod:`sage.graphs.graph_latex` module for ways
        to use  `\mbox{\rm\LaTeX}` to produce an image of a graph.

        INPUT:

        - ``pos`` - an optional positioning dictionary

        - ``layout`` - what kind of layout to use, takes precedence
          over pos

           - 'circular' -- plots the graph with vertices evenly
             distributed on a circle

           - 'spring' - uses the traditional spring layout, using the
             graph's current positions as initial positions

           - 'tree' - the (di)graph must be a tree. One can specify
             the root of the tree using the keyword tree_root,
             otherwise a root will be selected at random. Then the
             tree will be plotted in levels, depending on minimum
             distance for the root.

        - ``vertex_labels`` - whether to print vertex labels

        - ``edge_labels`` - whether to print edge labels. By default,
          False, but if True, the result of str(l) is printed on the
          edge for each label l. Labels equal to None are not printed
          (to set edge labels, see set_edge_label).

        - ``vertex_size`` - size of vertices displayed

        - ``vertex_shape`` - the shape to draw the vertices (Not
          available for multiedge digraphs.)

        - ``graph_border`` - whether to include a box around the graph

        - ``vertex_colors`` - optional dictionary to specify vertex
          colors: each key is a color recognizable by matplotlib, and
          each corresponding entry is a list of vertices. If a vertex
          is not listed, it looks invisible on the resulting plot (it
          doesn't get drawn).

        - ``edge_colors`` - a dictionary specifying edge colors: each
          key is a color recognized by matplotlib, and each entry is a
          list of edges.

        - ``partition`` - a partition of the vertex set. if specified,
          plot will show each cell in a different color. vertex_colors
          takes precedence.

        - ``scaling_term`` -- default is 0.05. if vertices are getting
          chopped off, increase; if graph is too small,
          decrease. should be positive, but values much bigger than
          1/8 won't be useful unless the vertices are huge

        - ``talk`` - if true, prints large vertices with white
          backgrounds so that labels are legible on slides

        - ``iterations`` - how many iterations of the spring layout
          algorithm to go through, if applicable

        - ``color_by_label`` - if True, color edges by their labels

        - ``heights`` - if specified, this is a dictionary from a set
          of floating point heights to a set of vertices

        - ``edge_style`` - keyword arguments passed into the
          edge-drawing routine.  This currently only works for
          directed graphs, since we pass off the undirected graph to
          networkx

        - ``tree_root`` - a vertex of the tree to be used as the root
          for the layout="tree" option. If no root is specified, then one
          is chosen at random. Ignored unless layout='tree'.

        - ``tree_orientation`` - "up" or "down" (default is "down").
          If "up" (resp., "down"), then the root of the tree will
          appear on the bottom (resp., top) and the tree will grow
          upwards (resp. downwards). Ignored unless layout='tree'.

        - ``save_pos`` - save position computed during plotting

        EXAMPLES::

            sage: from sage.graphs.graph_plot import graphplot_options
            sage: list(sorted(graphplot_options.iteritems()))
            [...]

            sage: from math import sin, cos, pi
            sage: P = graphs.PetersenGraph()
            sage: d = {'#FF0000':[0,5], '#FF9900':[1,6], '#FFFF00':[2,7], '#00FF00':[3,8], '#0000FF':[4,9]}
            sage: pos_dict = {}
            sage: for i in range(5):
            ...    x = float(cos(pi/2 + ((2*pi)/5)*i))
            ...    y = float(sin(pi/2 + ((2*pi)/5)*i))
            ...    pos_dict[i] = [x,y]
            ...
            sage: for i in range(10)[5:]:
            ...    x = float(0.5*cos(pi/2 + ((2*pi)/5)*i))
            ...    y = float(0.5*sin(pi/2 + ((2*pi)/5)*i))
            ...    pos_dict[i] = [x,y]
            ...
            sage: pl = P.plot(pos=pos_dict, vertex_colors=d)
            sage: pl.show()

        ::

            sage: C = graphs.CubeGraph(8)
            sage: P = C.plot(vertex_labels=False, vertex_size=0, graph_border=True)
            sage: P.show()

        ::

            sage: G = graphs.HeawoodGraph()
            sage: for u,v,l in G.edges():
            ...    G.set_edge_label(u,v,'(' + str(u) + ',' + str(v) + ')')
            sage: G.plot(edge_labels=True).show()

        ::

            sage: D = DiGraph( { 0: [1, 10, 19], 1: [8, 2], 2: [3, 6], 3: [19, 4], 4: [17, 5], 5: [6, 15], 6: [7], 7: [8, 14], 8: [9], 9: [10, 13], 10: [11], 11: [12, 18], 12: [16, 13], 13: [14], 14: [15], 15: [16], 16: [17], 17: [18], 18: [19], 19: []} , sparse=True)
            sage: for u,v,l in D.edges():
            ...    D.set_edge_label(u,v,'(' + str(u) + ',' + str(v) + ')')
            sage: D.plot(edge_labels=True, layout='circular').show()

        ::

            sage: from sage.plot.colors import rainbow
            sage: C = graphs.CubeGraph(5)
            sage: R = rainbow(5)
            sage: edge_colors = {}
            sage: for i in range(5):
            ...    edge_colors[R[i]] = []
            sage: for u,v,l in C.edges():
            ...    for i in range(5):
            ...        if u[i] != v[i]:
            ...            edge_colors[R[i]].append((u,v,l))
            sage: C.plot(vertex_labels=False, vertex_size=0, edge_colors=edge_colors).show()

        ::

            sage: D = graphs.DodecahedralGraph()
            sage: Pi = [[6,5,15,14,7],[16,13,8,2,4],[12,17,9,3,1],[0,19,18,10,11]]
            sage: D.show(partition=Pi)

        ::

            sage: G = graphs.PetersenGraph()
            sage: G.allow_loops(True)
            sage: G.add_edge(0,0)
            sage: G.show()

        ::

            sage: D = DiGraph({0:[0,1], 1:[2], 2:[3]}, loops=True)
            sage: D.show()
            sage: D.show(edge_colors={(0,1,0):[(0,1,None),(1,2,None)],(0,0,0):[(2,3,None)]})

        ::

            sage: pos = {0:[0.0, 1.5], 1:[-0.8, 0.3], 2:[-0.6, -0.8], 3:[0.6, -0.8], 4:[0.8, 0.3]}
            sage: g = Graph({0:[1], 1:[2], 2:[3], 3:[4], 4:[0]})
            sage: g.plot(pos=pos, layout='spring', iterations=0)

        ::

            sage: G = Graph()
            sage: P = G.plot()
            sage: P.axes()
            False
            sage: G = DiGraph()
            sage: P = G.plot()
            sage: P.axes()
            False

        ::

            sage: G = graphs.PetersenGraph()
            sage: G.get_pos()
            {0: (6.12..., 1.0...),
             1: (-0.95..., 0.30...),
             2: (-0.58..., -0.80...),
             3: (0.58..., -0.80...),
             4: (0.95..., 0.30...),
             5: (1.53..., 0.5...),
             6: (-0.47..., 0.15...),
             7: (-0.29..., -0.40...),
             8: (0.29..., -0.40...),
             9: (0.47..., 0.15...)}
            sage: P = G.plot(save_pos=True, layout='spring')

            The following illustrates the format of a position dictionary.

            sage: G.get_pos() # currently random across platforms, see #9593
            {0: [1.17..., -0.855...],
             1: [1.81..., -0.0990...],
             2: [1.35..., 0.184...],
             3: [1.51..., 0.644...],
             4: [2.00..., -0.507...],
             5: [0.597..., -0.236...],
             6: [2.04..., 0.687...],
             7: [1.46..., -0.473...],
             8: [0.902..., 0.773...],
             9: [2.48..., -0.119...]}

        ::

            sage: T = list(graphs.trees(7))
            sage: t = T[3]
            sage: t.plot(heights={0:[0], 1:[4,5,1], 2:[2], 3:[3,6]})

        ::

            sage: T = list(graphs.trees(7))
            sage: t = T[3]
            sage: t.plot(heights={0:[0], 1:[4,5,1], 2:[2], 3:[3,6]})
            sage: t.set_edge_label(0,1,-7)
            sage: t.set_edge_label(0,5,3)
            sage: t.set_edge_label(0,5,99)
            sage: t.set_edge_label(1,2,1000)
            sage: t.set_edge_label(3,2,'spam')
            sage: t.set_edge_label(2,6,3/2)
            sage: t.set_edge_label(0,4,66)
            sage: t.plot(heights={0:[0], 1:[4,5,1], 2:[2], 3:[3,6]}, edge_labels=True)

        ::

            sage: T = list(graphs.trees(7))
            sage: t = T[3]
            sage: t.plot(layout='tree')

        ::

            sage: t = DiGraph('JCC???@A??GO??CO??GO??')
            sage: t.plot(layout='tree', tree_root=0, tree_orientation="up")
            sage: D = DiGraph({0:[1,2,3], 2:[1,4], 3:[0]})
            sage: D.plot()

            sage: D = DiGraph(multiedges=True,sparse=True)
            sage: for i in range(5):
            ...     D.add_edge((i,i+1,'a'))
            ...     D.add_edge((i,i-1,'b'))
            sage: D.plot(edge_labels=True,edge_colors=D._color_by_label())

            sage: g = Graph({}, loops=True, multiedges=True,sparse=True)
            sage: g.add_edges([(0,0,'a'),(0,0,'b'),(0,1,'c'),(0,1,'d'),
            ...     (0,1,'e'),(0,1,'f'),(0,1,'f'),(2,1,'g'),(2,2,'h')])
            sage: g.plot(edge_labels=True, color_by_label=True, edge_style='dashed')

        ::

            sage: S = SupersingularModule(389)
            sage: H = S.hecke_matrix(2)
            sage: D = DiGraph(H,sparse=True)
            sage: P = D.plot()

        ::

            sage: G=Graph({'a':['a','b','b','b','e'],'b':['c','d','e'],'c':['c','d','d','d'],'d':['e']},sparse=True)
            sage: G.show(pos={'a':[0,1],'b':[1,1],'c':[2,0],'d':[1,0],'e':[0,0]})

        """
        from sage.graphs.graph_plot import GraphPlot
        return GraphPlot(graph=self, options=options).plot()

    def show(self, **kwds):
        """
        Shows the (di)graph.

        For syntax and lengthy documentation, see G.plot?. Any options not
        used by plot will be passed on to the Graphics.show method.

        EXAMPLES::

            sage: C = graphs.CubeGraph(8)
            sage: P = C.plot(vertex_labels=False, vertex_size=0, graph_border=True)
            sage: P.show()
        """
        kwds.setdefault('figsize', [4,4])
        from graph_plot import graphplot_options
        vars = graphplot_options.keys()
        plot_kwds = {}
        for kwd in vars:
            if kwds.has_key(kwd):
                plot_kwds[kwd] = kwds.pop(kwd)
        self.plot(**plot_kwds).show(**kwds)

    def plot3d(self, bgcolor=(1,1,1), vertex_colors=None, vertex_size=0.06,
                     edge_colors=None, edge_size=0.02, edge_size2=0.0325,
                     pos3d=None, color_by_label=False,
                     engine='jmol', **kwds):
        r"""
        Plot a graph in three dimensions.    See also the
        :mod:`sage.graphs.graph_latex` module for ways to use
        `\mbox{\rm\LaTeX}` to produce an image of a graph.

        INPUT:


        -  ``bgcolor`` - rgb tuple (default: (1,1,1))

        -  ``vertex_size`` - float (default: 0.06)

        -  ``vertex_colors`` - optional dictionary to specify
           vertex colors: each key is a color recognizable by tachyon (rgb
           tuple (default: (1,0,0))), and each corresponding entry is a list
           of vertices. If a vertex is not listed, it looks invisible on the
           resulting plot (it doesn't get drawn).

        -  ``edge_colors`` - a dictionary specifying edge
           colors: each key is a color recognized by tachyon ( default:
           (0,0,0) ), and each entry is a list of edges.

        -  ``edge_size`` - float (default: 0.02)

        -  ``edge_size2`` - float (default: 0.0325), used for
           Tachyon sleeves

        -  ``pos3d`` - a position dictionary for the vertices

        -  ``layout``, ``iterations``, ... - layout options; see :meth:`.layout`

        -  ``engine`` - which renderer to use. Options:

           -  ``'jmol'`` - default

           -  ``'tachyon'``

        -  ``xres`` - resolution

        -  ``yres`` - resolution

        -  ``**kwds`` - passed on to the rendering engine


        EXAMPLES::

            sage: G = graphs.CubeGraph(5)
            sage: G.plot3d(iterations=500, edge_size=None, vertex_size=0.04) # long time

        We plot a fairly complicated Cayley graph::

            sage: A5 = AlternatingGroup(5); A5
            Alternating group of order 5!/2 as a permutation group
            sage: G = A5.cayley_graph()
            sage: G.plot3d(vertex_size=0.03, edge_size=0.01, vertex_colors={(1,1,1):G.vertices()}, bgcolor=(0,0,0), color_by_label=True, iterations=200) # long time

        Some Tachyon examples::

            sage: D = graphs.DodecahedralGraph()
            sage: P3D = D.plot3d(engine='tachyon')
            sage: P3D.show() # long time

        ::

            sage: G = graphs.PetersenGraph()
            sage: G.plot3d(engine='tachyon', vertex_colors={(0,0,1):G.vertices()}).show() # long time

        ::

            sage: C = graphs.CubeGraph(4)
            sage: C.plot3d(engine='tachyon', edge_colors={(0,1,0):C.edges()}, vertex_colors={(1,1,1):C.vertices()}, bgcolor=(0,0,0)).show() # long time

        ::

            sage: K = graphs.CompleteGraph(3)
            sage: K.plot3d(engine='tachyon', edge_colors={(1,0,0):[(0,1,None)], (0,1,0):[(0,2,None)], (0,0,1):[(1,2,None)]}).show() # long time

        A directed version of the dodecahedron

        ::

            sage: D = DiGraph( { 0: [1, 10, 19], 1: [8, 2], 2: [3, 6], 3: [19, 4], 4: [17, 5], 5: [6, 15], 6: [7], 7: [8, 14], 8: [9], 9: [10, 13], 10: [11], 11: [12, 18], 12: [16, 13], 13: [14], 14: [15], 15: [16], 16: [17], 17: [18], 18: [19], 19: []} )
            sage: D.plot3d().show() # long time

        ::

            sage: P = graphs.PetersenGraph().to_directed()
            sage: from sage.plot.colors import rainbow
            sage: edges = P.edges()
            sage: R = rainbow(len(edges), 'rgbtuple')
            sage: edge_colors = {}
            sage: for i in range(len(edges)):
            ...       edge_colors[R[i]] = [edges[i]]
            sage: P.plot3d(engine='tachyon', edge_colors=edge_colors).show() # long time


        ::

            sage: G=Graph({'a':['a','b','b','b','e'],'b':['c','d','e'],'c':['c','d','d','d'],'d':['e']},sparse=True)
            sage: G.show3d()
            Traceback (most recent call last):
            ...
            NotImplementedError: 3D plotting of multiple edges or loops not implemented.

        """
        import graph_plot
        layout_options = dict( (key,kwds[key]) for key in kwds.keys() if key     in graph_plot.layout_options )
        kwds           = dict( (key,kwds[key]) for key in kwds.keys() if key not in graph_plot.layout_options )
        if pos3d is None:
            pos3d = self.layout(dim=3, **layout_options)

        if self.has_multiple_edges() or self.has_loops():
            raise NotImplementedError("3D plotting of multiple edges or loops not implemented.")
        if engine == 'jmol':
            from sage.plot.plot3d.all import sphere, line3d, arrow3d
            from sage.plot.plot3d.texture import Texture
            kwds.setdefault('aspect_ratio', [1,1,1])
            verts = self.vertices()

            if vertex_colors is None:
                vertex_colors = { (1,0,0) : verts }

            if color_by_label:
                if edge_colors is  None:
                        # do the coloring
                        edge_colors = self._color_by_label(format='rgbtuple')
            elif edge_colors is None:
                edge_colors = { (0,0,0) : self.edges() }

            # by default turn off the frame
            if not kwds.has_key('frame'):
                kwds['frame'] = False
            # by default make the background given by bgcolor
            if not kwds.has_key('background'):
                kwds['background'] = bgcolor
            try:
                graphic = 0
                for color in vertex_colors:
                    texture = Texture(color=color, ambient=0.1, diffuse=0.9, specular=0.03)
                    for v in vertex_colors[color]:
                        graphic += sphere(center=pos3d[v], size=vertex_size, texture=texture, **kwds)
                if self._directed:
                    for color in edge_colors:
                        for u, v, l in edge_colors[color]:
                            graphic += arrow3d(pos3d[u], pos3d[v], radius=edge_size, color=color, closed=False, **kwds)

                else:
                    for color in edge_colors:
                        texture = Texture(color=color, ambient=0.1, diffuse=0.9, specular=0.03)
                        for u, v, l in edge_colors[color]:
                            graphic += line3d([pos3d[u], pos3d[v]], radius=edge_size, texture=texture, closed=False, **kwds)

                return graphic

            except KeyError:
                raise KeyError, "Oops! You haven't specified positions for all the vertices."

        elif engine == 'tachyon':
            TT, pos3d = tachyon_vertex_plot(self, bgcolor=bgcolor, vertex_colors=vertex_colors,
                                            vertex_size=vertex_size, pos3d=pos3d, **kwds)
            edges = self.edges()

            if color_by_label:
                if edge_colors is  None:
                    # do the coloring
                    edge_colors = self._color_by_label(format='rgbtuple')

            if edge_colors is None:
                edge_colors = { (0,0,0) : edges }

            i = 0

            for color in edge_colors:
                i += 1
                TT.texture('edge_color_%d'%i, ambient=0.1, diffuse=0.9, specular=0.03, opacity=1.0, color=color)
                if self._directed:
                    for u,v,l in edge_colors[color]:
                        TT.fcylinder( (pos3d[u][0],pos3d[u][1],pos3d[u][2]),
                                      (pos3d[v][0],pos3d[v][1],pos3d[v][2]), edge_size,'edge_color_%d'%i)
                        TT.fcylinder( (0.25*pos3d[u][0] + 0.75*pos3d[v][0],
                                       0.25*pos3d[u][1] + 0.75*pos3d[v][1],
                                       0.25*pos3d[u][2] + 0.75*pos3d[v][2],),
                                      (pos3d[v][0],pos3d[v][1],pos3d[v][2]), edge_size2,'edge_color_%d'%i)
                else:
                    for u, v, l in edge_colors[color]:
                        TT.fcylinder( (pos3d[u][0],pos3d[u][1],pos3d[u][2]), (pos3d[v][0],pos3d[v][1],pos3d[v][2]), edge_size,'edge_color_%d'%i)

            return TT

        else:
            raise TypeError("Rendering engine (%s) not implemented."%engine)

    def show3d(self, bgcolor=(1,1,1), vertex_colors=None, vertex_size=0.06,
                     edge_colors=None, edge_size=0.02, edge_size2=0.0325,
                     pos3d=None, color_by_label=False,
                     engine='jmol', **kwds):
        """
        Plots the graph using Tachyon, and shows the resulting plot.

        INPUT:


        -  ``bgcolor`` - rgb tuple (default: (1,1,1))

        -  ``vertex_size`` - float (default: 0.06)

        -  ``vertex_colors`` - optional dictionary to specify
           vertex colors: each key is a color recognizable by tachyon (rgb
           tuple (default: (1,0,0))), and each corresponding entry is a list
           of vertices. If a vertex is not listed, it looks invisible on the
           resulting plot (it doesn't get drawn).

        -  ``edge_colors`` - a dictionary specifying edge
           colors: each key is a color recognized by tachyon ( default:
           (0,0,0) ), and each entry is a list of edges.

        -  ``edge_size`` - float (default: 0.02)

        -  ``edge_size2`` - float (default: 0.0325), used for
           Tachyon sleeves

        -  ``pos3d`` - a position dictionary for the vertices

        -  ``iterations`` - how many iterations of the spring
           layout algorithm to go through, if applicable

        -  ``engine`` - which renderer to use. Options:

        -  ``'jmol'`` - default 'tachyon'

        -  ``xres`` - resolution

        -  ``yres`` - resolution

        -  ``**kwds`` - passed on to the Tachyon command


        EXAMPLES::

            sage: G = graphs.CubeGraph(5)
            sage: G.show3d(iterations=500, edge_size=None, vertex_size=0.04) # long time

        We plot a fairly complicated Cayley graph::

            sage: A5 = AlternatingGroup(5); A5
            Alternating group of order 5!/2 as a permutation group
            sage: G = A5.cayley_graph()
            sage: G.show3d(vertex_size=0.03, edge_size=0.01, edge_size2=0.02, vertex_colors={(1,1,1):G.vertices()}, bgcolor=(0,0,0), color_by_label=True, iterations=200) # long time

        Some Tachyon examples::

            sage: D = graphs.DodecahedralGraph()
            sage: D.show3d(engine='tachyon') # long time

        ::

            sage: G = graphs.PetersenGraph()
            sage: G.show3d(engine='tachyon', vertex_colors={(0,0,1):G.vertices()}) # long time

        ::

            sage: C = graphs.CubeGraph(4)
            sage: C.show3d(engine='tachyon', edge_colors={(0,1,0):C.edges()}, vertex_colors={(1,1,1):C.vertices()}, bgcolor=(0,0,0)) # long time

        ::

            sage: K = graphs.CompleteGraph(3)
            sage: K.show3d(engine='tachyon', edge_colors={(1,0,0):[(0,1,None)], (0,1,0):[(0,2,None)], (0,0,1):[(1,2,None)]}) # long time
        """
        self.plot3d(bgcolor=bgcolor, vertex_colors=vertex_colors,
                    edge_colors=edge_colors, vertex_size=vertex_size, engine=engine,
                    edge_size=edge_size, edge_size2=edge_size2,
                    color_by_label=color_by_label, **kwds).show()

    def _keys_for_vertices(self):
        """
        Returns a function mapping each vertex to a unique and hopefully readable string
        """
        from sage.graphs.dot2tex_utils import key, key_with_hash
        if len(set(key(v) for v in self)) < len(self.vertices()):
            # There was a collision in the keys; we include a hash to be safe.
            return key_with_hash
        else:
            return key

    ### String representation to be used by other programs

    @options(labels="string",
            vertex_labels=True,edge_labels=False,
            edge_color=None,edge_colors=None,
            color_by_label=False)
    def graphviz_string(self, **options):
        r"""
        Returns a representation in the dot language.

        The dot language is a text based format for graphs. It is used
        by the software suite graphviz. The specifications of the
        language are available on the web (see the reference [dotspec]_).

        INPUT:

        - ``labels`` - "string" or "latex" (default: "string"). If labels is
          string latex command are not interpreted. This option stands for both
          vertex labels and edge labels.

        - ``vertex_labels`` - boolean (default: True) whether to add the labels
          on vertices.

        - ``edge_labels`` - boolean (default: False) whether to add
          the labels on edges.

        - ``edge_color`` - (default: None) specify a default color for the
          edges.

        - ``edge_colors`` - (default: None) a dictionary which keys
          are colors and values are list of edges. The list of edges need not to
          be complete in which case the default color is used.

        - ``color_by_label`` - boolean (default: False): whether to
          color each edge with a different color according to its
          label. This overwrites the options ``edge_color`` and ``edge_colors``.


        EXAMPLES::

            sage: G = Graph({0:{1:None,2:None}, 1:{0:None,2:None}, 2:{0:None,1:None,3:'foo'}, 3:{2:'foo'}},sparse=True)
            sage: print G.graphviz_string(edge_labels=True)
            graph {
              "0" [label="0"];
              "1" [label="1"];
              "2" [label="2"];
              "3" [label="3"];
            <BLANKLINE>
              "0" -- "1";
              "0" -- "2";
              "1" -- "2";
              "2" -- "3" [label="foo"];
            }

        A variant, with the labels in latex, for post-processing with ``dot2tex``::

            sage: print G.graphviz_string(edge_labels=True,labels = "latex")
            graph {
              node [shape="plaintext"];
              "0" [label=" ", texlbl="$0$"];
              "1" [label=" ", texlbl="$1$"];
              "2" [label=" ", texlbl="$2$"];
              "3" [label=" ", texlbl="$3$"];
            <BLANKLINE>
              "0" -- "1";
              "0" -- "2";
              "1" -- "2";
              "2" -- "3" [label=" ", texlbl="$\texttt{foo}$"];
            }

        Same, with a digraph and a color for edges::

            sage: G = DiGraph({0:{1:None,2:None}, 1:{2:None}, 2:{3:'foo'}, 3:{}} ,sparse=True)
            sage: print G.graphviz_string(edge_color="red")
            digraph {
              "0" [label="0"];
              "1" [label="1"];
              "2" [label="2"];
              "3" [label="3"];
            <BLANKLINE>
              edge [color="red"];
              "0" -> "1";
              "0" -> "2";
              "1" -> "2";
              "2" -> "3";
            }

        A digraph using latex labels for vertices and edges::

            sage: f(x) = -1/x
            sage: g(x) = 1/(x+1)
            sage: G = DiGraph()
            sage: G.add_edges([(i,f(i),f) for i in (1,2,1/2,1/4)])
            sage: G.add_edges([(i,g(i),g) for i in (1,2,1/2,1/4)])
            sage: print G.graphviz_string(labels="latex",edge_labels=True)
            digraph {
              node [shape="plaintext"];
              "2/3" [label=" ", texlbl="$\frac{2}{3}$"];
              "1/3" [label=" ", texlbl="$\frac{1}{3}$"];
              "1/2" [label=" ", texlbl="$\frac{1}{2}$"];
              "1" [label=" ", texlbl="$1$"];
              "1/4" [label=" ", texlbl="$\frac{1}{4}$"];
              "4/5" [label=" ", texlbl="$\frac{4}{5}$"];
              "-4" [label=" ", texlbl="$-4$"];
              "2" [label=" ", texlbl="$2$"];
              "-2" [label=" ", texlbl="$-2$"];
              "-1/2" [label=" ", texlbl="$-\frac{1}{2}$"];
              "-1" [label=" ", texlbl="$-1$"];
            <BLANKLINE>
              "1/2" -> "-2" [label=" ", texlbl="$x \ {\mapsto}\ \frac{-1}{x}$"];
              "1/2" -> "2/3" [label=" ", texlbl="$x \ {\mapsto}\ \frac{1}{x + 1}$"];
              "1" -> "-1" [label=" ", texlbl="$x \ {\mapsto}\ \frac{-1}{x}$"];
              "1" -> "1/2" [label=" ", texlbl="$x \ {\mapsto}\ \frac{1}{x + 1}$"];
              "1/4" -> "-4" [label=" ", texlbl="$x \ {\mapsto}\ \frac{-1}{x}$"];
              "1/4" -> "4/5" [label=" ", texlbl="$x \ {\mapsto}\ \frac{1}{x + 1}$"];
              "2" -> "-1/2" [label=" ", texlbl="$x \ {\mapsto}\ \frac{-1}{x}$"];
              "2" -> "1/3" [label=" ", texlbl="$x \ {\mapsto}\ \frac{1}{x + 1}$"];
            }

        TESTS:

        The following digraph has tuples as vertices::

            sage: print digraphs.ButterflyGraph(1).graphviz_string()
            digraph {
              "1,1" [label="('1', 1)"];
              "0,0" [label="('0', 0)"];
              "1,0" [label="('1', 0)"];
              "0,1" [label="('0', 1)"];
            <BLANKLINE>
              "0,0" -> "1,1";
              "0,0" -> "0,1";
              "1,0" -> "1,1";
              "1,0" -> "0,1";
            }

        The following digraph has vertices with newlines in their
        string representations::

            sage: m1 = matrix(3,3)
            sage: m2 = matrix(3,3, 1)
            sage: m1.set_immutable()
            sage: m2.set_immutable()
            sage: g = DiGraph({ m1: [m2] })
            sage: print g.graphviz_string()
            digraph {
              "000000000" [label="[0 0 0]\n\
              [0 0 0]\n\
              [0 0 0]"];
              "100010001" [label="[1 0 0]\n\
              [0 1 0]\n\
              [0 0 1]"];
            <BLANKLINE>
              "000000000" -> "100010001";
            }

        REFERENCES:

        .. [dotspec] http://www.graphviz.org/doc/info/lang.html

        """
        import re
        from sage.graphs.dot2tex_utils import quoted_latex, quoted_str

        if self.is_directed():
            graph_string = "digraph"
            edge_string = "->"
        else:
            graph_string = "graph"
            edge_string = "--"

        if options['color_by_label']:
            edges_by_color = self._color_by_label('hex')
            not_colored_edges = []
        elif options['edge_colors'] is not None:
            if not isinstance(options['edge_colors'],dict):
                raise ValueError, "incorrect format for edge_colors"
            not_colored_edges = set(self.edges(labels=True))
            edges_by_color = {}
            for color,l in options['edge_colors'].iteritems():
                edges_by_color[color] = []
                for t in l:
                    if len(t) == 2:
                        if self.has_multiple_edges():
                            for label in self.edge_label(t[0],t[1]):
                                not_colored_edges.remove((t[0],t[1],label))
                                edges_by_color[color].append((t[0],t[1],label))
                        else:
                            label = self.edge_label(t[0],t[1])
                            not_colored_edges.remove((t[0],t[1],label))
                            edges_by_color[color].append((t[0],t[1],label))
                    elif len(t) == 3:
                        t = tuple(t)
                        if t not in not_colored_edges:
                            raise ValueError, "%s is not an edge" %str(t)
                        not_colored_edges.remove(t)
                        edges_by_color[color].append(t)
                    else:
                        raise ValueError, "%s is not a valid format for edge" %str(t)
        else:
            edges_by_color = []
            not_colored_edges = self.edge_iterator(labels=True)

        if options['edge_color'] is not None:
            default_color = options['edge_color']
        else:
            default_color = None

        key = self._keys_for_vertices()

        s = '%s {\n' % graph_string
        if (options['vertex_labels'] and
            options['labels'] == "latex"): # not a perfect option name
            s += '  node [shape="plaintext"];\n'
        for v in self.vertex_iterator():
            if not options['vertex_labels']:
                node_options = ""
            elif options['labels'] == "latex":
                node_options = " [label=\" \", texlbl=\"$%s$\"]"%quoted_latex(v)
            else:
                node_options = " [label=\"%s\"]" %quoted_str(v)

            s += '  "%s"%s;\n'%(key(v),node_options)

        s += "\n"

        if not_colored_edges and default_color is not None:
            s += '  edge [color="%s"];\n' %default_color
        for u,v,label in not_colored_edges:
            if options['edge_labels'] is False or label is None:
                s += '  "%s" %s "%s";\n' % (key(u), edge_string, key(v))
            elif options['labels'] == "latex":
                s += '  "%s" %s "%s" [label=" ", texlbl="$%s$"];\n' % (key(u), edge_string, key(v), quoted_latex(label))
            else:
                s += '  "%s" %s "%s" [label="%s"];\n' % (key(u), edge_string, key(v), label)

        for color in edges_by_color:
            s += '  edge [color="%s"];\n' %color
            for u,v,label in edges_by_color[color]:
                if options['edge_labels'] is False or label is None:
                    s += '  "%s" %s "%s";\n' % (key(u), edge_string, key(v))
                elif options['labels'] == "latex":
                    s += '  "%s" %s "%s" [label=" ", texlbl="$%s$"];\n' % (key(u), edge_string, key(v), quoted_latex(label))
                else:
                    s += '  "%s" %s "%s" [label="%s"];\n' % (key(u), edge_string, key(v), label)

        s += "}"

        return s

    def graphviz_to_file_named(self, filename, **options):
        r"""
        Write a representation in the dot in a file.

        The dot language is a plaintext format for graph structures. See the
        documentation of :meth:`.graphviz_string` for available options.

        INPUT:

        ``filename`` - the name of the file to write in

        ``options`` - options for the graphviz string

        EXAMPLES::

            sage: G = Graph({0:{1:None,2:None}, 1:{0:None,2:None}, 2:{0:None,1:None,3:'foo'}, 3:{2:'foo'}},sparse=True)
            sage: G.graphviz_to_file_named(os.environ['SAGE_TESTDIR']+'/temp_graphviz',edge_labels=True)
            sage: print open(os.environ['SAGE_TESTDIR']+'/temp_graphviz').read()
            graph {
              "0" [label="0"];
              "1" [label="1"];
              "2" [label="2"];
              "3" [label="3"];
            <BLANKLINE>
              "0" -- "1";
              "0" -- "2";
              "1" -- "2";
              "2" -- "3" [label="foo"];
            }
        """
        return open(filename, 'wt').write(self.graphviz_string(**options))

    ### Spectrum

    def spectrum(self, laplacian=False):
        r"""
        Returns a list of the eigenvalues of the adjacency matrix.

        INPUT:

        -  ``laplacian`` - if ``True``, use the Laplacian matrix
           (see :meth:`~sage.graphs.graph.GenericGraph.kirchhoff_matrix()`)

        OUTPUT:

        A list of the eigenvalues, including multiplicities, sorted
        with the largest eigenvalue first.

        EXAMPLES::

            sage: P = graphs.PetersenGraph()
            sage: P.spectrum()
            [3, 1, 1, 1, 1, 1, -2, -2, -2, -2]
            sage: P.spectrum(laplacian=True)
            [5, 5, 5, 5, 2, 2, 2, 2, 2, 0]
            sage: D = P.to_directed()
            sage: D.delete_edge(7,9)
            sage: D.spectrum()
            [2.9032119259..., 1, 1, 1, 1, 0.8060634335..., -1.7092753594..., -2, -2, -2]

        ::

            sage: C = graphs.CycleGraph(8)
            sage: C.spectrum()
            [2, 1.4142135623..., 1.4142135623..., 0, 0, -1.4142135623..., -1.4142135623..., -2]

        A digraph may have complex eigenvalues.  Previously, the complex parts
        of graph eigenvalues were being dropped.  For a 3-cycle, we have::

            sage: T = DiGraph({0:[1], 1:[2], 2:[0]})
            sage: T.spectrum()
            [1, -0.5000000000... + 0.8660254037...*I, -0.5000000000... - 0.8660254037...*I]

        TESTS:

        The Laplacian matrix of a graph is the negative of the adjacency matrix with the degree of each vertex on the diagonal.  So for a regular graph, if `\delta` is an eigenvalue of a regular graph of degree `r`, then `r-\delta` will be an eigenvalue of the Laplacian.  The Hoffman-Singleton graph is regular of degree 7, so the following will test both the Laplacian construction and the computation of eigenvalues. ::

            sage: H = graphs.HoffmanSingletonGraph()
            sage: evals = H.spectrum()
            sage: lap = map(lambda x : 7 - x, evals)
            sage: lap.sort(reverse=True)
            sage: lap == H.spectrum(laplacian=True)
            True
        """
        # Ideally the spectrum should return something like a Factorization object
        # containing each eigenvalue once, along with its multiplicity.
        # This function, returning a list. could then just be renamed "eigenvalues"
        if laplacian:
            M = self.kirchhoff_matrix()
        else:
            M = self.adjacency_matrix()
        evals = M.eigenvalues()
        evals.sort(reverse=True)
        return evals

    def characteristic_polynomial(self, var='x', laplacian=False):
        r"""
        Returns the characteristic polynomial of the adjacency matrix of
        the (di)graph.

        Let `G` be a (simple) graph with adjacency matrix `A`. Let `I` be the
        identity matrix of dimensions the same as `A`. The characteristic
        polynomial of `G` is defined as the determinant `\det(xI - A)`.

        INPUT:

        - ``x`` -- (default: ``'x'``) the variable of the characteristic
          polynomial.

        - ``laplacian`` -- (default: ``False``) if ``True``, use the
          Laplacian matrix.

        .. SEEALSO::

            - :meth:`kirchhoff_matrix`

            - :meth:`laplacian_matrix`

        EXAMPLES::

            sage: P = graphs.PetersenGraph()
            sage: P.characteristic_polynomial()
            x^10 - 15*x^8 + 75*x^6 - 24*x^5 - 165*x^4 + 120*x^3 + 120*x^2 - 160*x + 48
            sage: P.characteristic_polynomial(laplacian=True)
            x^10 - 30*x^9 + 390*x^8 - 2880*x^7 + 13305*x^6 - 39882*x^5 + 77640*x^4 - 94800*x^3 + 66000*x^2 - 20000*x
        """
        if laplacian:
            return self.kirchhoff_matrix().charpoly(var=var)
        else:
            return self.adjacency_matrix().charpoly(var=var)

    def eigenvectors(self, laplacian=False):
        r"""
        Returns the *right* eigenvectors of the adjacency matrix of the graph.

        INPUT:

        -  ``laplacian`` - if True, use the Laplacian matrix
           (see :meth:`~sage.graphs.graph.GenericGraph.kirchhoff_matrix()`)

        OUTPUT:

        A list of triples.  Each triple begins with an eigenvalue of
        the adjacency matrix of the graph.  This is followed by
        a list of eigenvectors for the eigenvalue, when the
        eigenvectors are placed on the right side of the matrix.
        Together, the eigenvectors form a basis for the eigenspace.
        The triple concludes with the algebraic multiplicity of
        the eigenvalue.

        For some graphs, the exact eigenspaces provided by
        :meth:`eigenspaces` provide additional insight into
        the structure of the eigenspaces.

        EXAMPLES::

            sage: P = graphs.PetersenGraph()
            sage: P.eigenvectors()
            [(3, [
            (1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
            ], 1), (-2, [
            (1, 0, 0, 0, -1, -1, -1, 0, 1, 1),
            (0, 1, 0, 0, -1, 0, -2, -1, 1, 2),
            (0, 0, 1, 0, -1, 1, -1, -2, 0, 2),
            (0, 0, 0, 1, -1, 1, 0, -1, -1, 1)
            ], 4), (1, [
            (1, 0, 0, 0, 0, 1, -1, 0, 0, -1),
            (0, 1, 0, 0, 0, -1, 1, -1, 0, 0),
            (0, 0, 1, 0, 0, 0, -1, 1, -1, 0),
            (0, 0, 0, 1, 0, 0, 0, -1, 1, -1),
            (0, 0, 0, 0, 1, -1, 0, 0, -1, 1)
            ], 5)]

        Eigenspaces for the Laplacian should be identical since the
        Petersen graph is regular.  However, since the output also
        contains the eigenvalues, the two outputs are slightly
        different. ::

            sage: P.eigenvectors(laplacian=True)
            [(0, [
            (1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
            ], 1), (5, [
            (1, 0, 0, 0, -1, -1, -1, 0, 1, 1),
            (0, 1, 0, 0, -1, 0, -2, -1, 1, 2),
            (0, 0, 1, 0, -1, 1, -1, -2, 0, 2),
            (0, 0, 0, 1, -1, 1, 0, -1, -1, 1)
            ], 4), (2, [
            (1, 0, 0, 0, 0, 1, -1, 0, 0, -1),
            (0, 1, 0, 0, 0, -1, 1, -1, 0, 0),
            (0, 0, 1, 0, 0, 0, -1, 1, -1, 0),
            (0, 0, 0, 1, 0, 0, 0, -1, 1, -1),
            (0, 0, 0, 0, 1, -1, 0, 0, -1, 1)
            ], 5)]

        ::

            sage: C = graphs.CycleGraph(8)
            sage: C.eigenvectors()
            [(2, [
            (1, 1, 1, 1, 1, 1, 1, 1)
            ], 1), (-2, [
            (1, -1, 1, -1, 1, -1, 1, -1)
            ], 1), (0, [
            (1, 0, -1, 0, 1, 0, -1, 0),
            (0, 1, 0, -1, 0, 1, 0, -1)
            ], 2), (-1.4142135623..., [(1, 0, -1, 1.4142135623..., -1, 0, 1, -1.4142135623...), (0, 1, -1.4142135623..., 1, 0, -1, 1.4142135623..., -1)], 2), (1.4142135623..., [(1, 0, -1, -1.4142135623..., -1, 0, 1, 1.4142135623...), (0, 1, 1.4142135623..., 1, 0, -1, -1.4142135623..., -1)], 2)]

        A digraph may have complex eigenvalues.  Previously, the complex parts
        of graph eigenvalues were being dropped.  For a 3-cycle, we have::

            sage: T = DiGraph({0:[1], 1:[2], 2:[0]})
            sage: T.eigenvectors()
            [(1, [
            (1, 1, 1)
            ], 1), (-0.5000000000... - 0.8660254037...*I, [(1, -0.5000000000... - 0.8660254037...*I, -0.5000000000... + 0.8660254037...*I)], 1), (-0.5000000000... + 0.8660254037...*I, [(1, -0.5000000000... + 0.8660254037...*I, -0.5000000000... - 0.8660254037...*I)], 1)]
        """
        if laplacian:
            M = self.kirchhoff_matrix()
        else:
            M = self.adjacency_matrix()
        return M.right_eigenvectors()

    def eigenspaces(self, laplacian=False):
        r"""
        Returns the *right* eigenspaces of the adjacency matrix of the graph.

        INPUT:

        -  ``laplacian`` - if True, use the Laplacian matrix
           (see :meth:`~sage.graphs.graph.GenericGraph.kirchhoff_matrix()`)

        OUTPUT:

        A list of pairs.  Each pair is an eigenvalue of the
        adjacency matrix of the graph, followed by
        the vector space that is the eigenspace for that eigenvalue,
        when the eigenvectors are placed on the right of the matrix.

        For some graphs, some of the the eigenspaces are described
        exactly by vector spaces over a
        :class:`~sage.rings.number_field.number_field.NumberField`.
        For numerical eigenvectors use :meth:`eigenvectors`.

        EXAMPLES::

            sage: P = graphs.PetersenGraph()
            sage: P.eigenspaces()
            [
            (3, Vector space of degree 10 and dimension 1 over Rational Field
            User basis matrix:
            [1 1 1 1 1 1 1 1 1 1]),
            (-2, Vector space of degree 10 and dimension 4 over Rational Field
            User basis matrix:
            [ 1  0  0  0 -1 -1 -1  0  1  1]
            [ 0  1  0  0 -1  0 -2 -1  1  2]
            [ 0  0  1  0 -1  1 -1 -2  0  2]
            [ 0  0  0  1 -1  1  0 -1 -1  1]),
            (1, Vector space of degree 10 and dimension 5 over Rational Field
            User basis matrix:
            [ 1  0  0  0  0  1 -1  0  0 -1]
            [ 0  1  0  0  0 -1  1 -1  0  0]
            [ 0  0  1  0  0  0 -1  1 -1  0]
            [ 0  0  0  1  0  0  0 -1  1 -1]
            [ 0  0  0  0  1 -1  0  0 -1  1])
            ]

        Eigenspaces for the Laplacian should be identical since the
        Petersen graph is regular.  However, since the output also
        contains the eigenvalues, the two outputs are slightly
        different. ::

            sage: P.eigenspaces(laplacian=True)
            [
            (0, Vector space of degree 10 and dimension 1 over Rational Field
            User basis matrix:
            [1 1 1 1 1 1 1 1 1 1]),
            (5, Vector space of degree 10 and dimension 4 over Rational Field
            User basis matrix:
            [ 1  0  0  0 -1 -1 -1  0  1  1]
            [ 0  1  0  0 -1  0 -2 -1  1  2]
            [ 0  0  1  0 -1  1 -1 -2  0  2]
            [ 0  0  0  1 -1  1  0 -1 -1  1]),
            (2, Vector space of degree 10 and dimension 5 over Rational Field
            User basis matrix:
            [ 1  0  0  0  0  1 -1  0  0 -1]
            [ 0  1  0  0  0 -1  1 -1  0  0]
            [ 0  0  1  0  0  0 -1  1 -1  0]
            [ 0  0  0  1  0  0  0 -1  1 -1]
            [ 0  0  0  0  1 -1  0  0 -1  1])
            ]

        Notice how one eigenspace below is described with a square root of
        2.  For the two possible values (positive and negative) there is a
        corresponding eigenspace.  ::

            sage: C = graphs.CycleGraph(8)
            sage: C.eigenspaces()
            [
            (2, Vector space of degree 8 and dimension 1 over Rational Field
            User basis matrix:
            [1 1 1 1 1 1 1 1]),
            (-2, Vector space of degree 8 and dimension 1 over Rational Field
            User basis matrix:
            [ 1 -1  1 -1  1 -1  1 -1]),
            (0, Vector space of degree 8 and dimension 2 over Rational Field
            User basis matrix:
            [ 1  0 -1  0  1  0 -1  0]
            [ 0  1  0 -1  0  1  0 -1]),
            (a3, Vector space of degree 8 and dimension 2 over Number Field in a3 with defining polynomial x^2 - 2
            User basis matrix:
            [  1   0  -1 -a3  -1   0   1  a3]
            [  0   1  a3   1   0  -1 -a3  -1])
            ]

        A digraph may have complex eigenvalues and eigenvectors.
        For a 3-cycle, we have::

            sage: T = DiGraph({0:[1], 1:[2], 2:[0]})
            sage: T.eigenspaces()
            [
            (1, Vector space of degree 3 and dimension 1 over Rational Field
            User basis matrix:
            [1 1 1]),
            (a1, Vector space of degree 3 and dimension 1 over Number Field in a1 with defining polynomial x^2 + x + 1
            User basis matrix:
            [      1      a1 -a1 - 1])
            ]
        """
        if laplacian:
            M = self.kirchhoff_matrix()
        else:
            M = self.adjacency_matrix()
        return M.right_eigenspaces(algebraic_multiplicity=False)

    ### Automorphism and isomorphism

    def relabel(self, perm=None, inplace=True, return_map=False):
        r"""
        Uses a dictionary, list, or permutation to relabel the (di)graph.
        If perm is a dictionary d, each old vertex v is a key in the
        dictionary, and its new label is d[v].

        If perm is a list, we think of it as a map
        `i \mapsto perm[i]` with the assumption that the vertices
        are `\{0,1,...,n-1\}`.

        If perm is a permutation, the permutation is simply applied to the
        graph, under the assumption that the vertices are
        `\{0,1,...,n-1\}`. The permutation acts on the set
        `\{1,2,...,n\}`, where we think of `n = 0`.

        If no arguments are provided, the graph is relabeled to be on the
        vertices `\{0,1,...,n-1\}`.

        INPUT:


        -  ``inplace`` - default is True. If True, modifies the
           graph and returns nothing. If False, returns a relabeled copy of
           the graph.

        -  ``return_map`` - default is False. If True, returns
           the dictionary representing the map.


        EXAMPLES::

            sage: G = graphs.PathGraph(3)
            sage: G.am()
            [0 1 0]
            [1 0 1]
            [0 1 0]

        Relabeling using a dictionary::

            sage: G.relabel({1:2,2:1}, inplace=False).am()
            [0 0 1]
            [0 0 1]
            [1 1 0]

        Relabeling using a list::

            sage: G.relabel([0,2,1], inplace=False).am()
            [0 0 1]
            [0 0 1]
            [1 1 0]

        Relabeling using a Sage permutation::

            sage: from sage.groups.perm_gps.permgroup_named import SymmetricGroup
            sage: S = SymmetricGroup(3)
            sage: gamma = S('(1,2)')
            sage: G.relabel(gamma, inplace=False).am()
            [0 0 1]
            [0 0 1]
            [1 1 0]

        Relabeling to simpler labels::

            sage: G = graphs.CubeGraph(3)
            sage: G.vertices()
            ['000', '001', '010', '011', '100', '101', '110', '111']
            sage: G.relabel()
            sage: G.vertices()
            [0, 1, 2, 3, 4, 5, 6, 7]

        ::

            sage: G = graphs.CubeGraph(3)
            sage: expecting = {'000': 0, '001': 1, '010': 2, '011': 3, '100': 4, '101': 5, '110': 6, '111': 7}
            sage: G.relabel(return_map=True) == expecting
            True

        TESTS::

            sage: P = Graph(graphs.PetersenGraph())
            sage: P.delete_edge([0,1])
            sage: P.add_edge((4,5))
            sage: P.add_edge((2,6))
            sage: P.delete_vertices([0,1])
            sage: P.relabel()

        The attributes are properly updated too

        ::

            sage: G = graphs.PathGraph(5)
            sage: G.set_vertices({0: 'before', 1: 'delete', 2: 'after'})
            sage: G.set_boundary([1,2,3])
            sage: G.delete_vertex(1)
            sage: G.relabel()
            sage: G.get_vertices()
            {0: 'before', 1: 'after', 2: None, 3: None}
            sage: G.get_boundary()
            [1, 2]
            sage: G.get_pos()
            {0: (0, 0), 1: (2, 0), 2: (3, 0), 3: (4, 0)}
        """
        if perm is None:
            verts = self.vertices() # vertices() returns a sorted list:
            perm = {}; i = 0        # this guarantees consistent relabeling
            for v in verts:
                perm[v] = i
                i += 1
        if not inplace:
            from copy import copy
            G = copy(self)
            G.relabel(perm)
            if return_map:
                return G, perm
            return G
        if type(perm) is list:
            perm = dict( [ [i,perm[i]] for i in xrange(len(perm)) ] )
        from sage.groups.perm_gps.permgroup_element import PermutationGroupElement
        if type(perm) is PermutationGroupElement:
            n = self.order()
            ddict = {}
            llist = perm.list()
            for i in xrange(1,n):
                ddict[i] = llist[i-1]%n
            if n > 0:
                ddict[0] = llist[n-1]%n
            perm = ddict
        if type(perm) is not dict:
            raise TypeError("Type of perm is not supported for relabeling.")
        keys = perm.keys()
        verts = self.vertices()
        for v in verts:
            if v not in keys:
                perm[v] = v
        for v in perm.iterkeys():
            if v in verts:
                try:
                    hash(perm[v])
                except TypeError:
                    raise ValueError("perm dictionary must be of the format {a:a1, b:b1, ...} where a,b,... are vertices and a1,b1,... are hashable")
        self._backend.relabel(perm, self._directed)

        attributes_to_update = ('_pos', '_assoc', '_embedding')
        for attr in attributes_to_update:
            if hasattr(self, attr) and getattr(self, attr) is not None:
                new_attr = {}
                for v,value in getattr(self, attr).iteritems():
                    new_attr[perm[v]] = value

                setattr(self, attr, new_attr)

        self._boundary = [perm[v] for v in self._boundary]

        if return_map:
            return perm

    def degree_to_cell(self, vertex, cell):
        """
        Returns the number of edges from vertex to an edge in cell. In the
        case of a digraph, returns a tuple (in_degree, out_degree).

        EXAMPLES::

            sage: G = graphs.CubeGraph(3)
            sage: cell = G.vertices()[:3]
            sage: G.degree_to_cell('011', cell)
            2
            sage: G.degree_to_cell('111', cell)
            0

        ::

            sage: D = DiGraph({ 0:[1,2,3], 1:[3,4], 3:[4,5]})
            sage: cell = [0,1,2]
            sage: D.degree_to_cell(5, cell)
            (0, 0)
            sage: D.degree_to_cell(3, cell)
            (2, 0)
            sage: D.degree_to_cell(0, cell)
            (0, 2)
        """
        if self._directed:
            in_neighbors_in_cell = set([a for a,_,_ in self.incoming_edges(vertex)]) & set(cell)
            out_neighbors_in_cell = set([a for _,a,_ in self.outgoing_edges(vertex)]) & set(cell)
            return (len(in_neighbors_in_cell), len(out_neighbors_in_cell))
        else:
            neighbors_in_cell = set(self.neighbors(vertex)) & set(cell)
            return len(neighbors_in_cell)

    def is_equitable(self, partition, quotient_matrix=False):
        """
        Checks whether the given partition is equitable with respect to
        self.

        A partition is equitable with respect to a graph if for every pair
        of cells C1, C2 of the partition, the number of edges from a vertex
        of C1 to C2 is the same, over all vertices in C1.

        INPUT:


        -  ``partition`` - a list of lists

        -  ``quotient_matrix`` - (default False) if True, and
           the partition is equitable, returns a matrix over the integers
           whose rows and columns represent cells of the partition, and whose
           i,j entry is the number of vertices in cell j adjacent to each
           vertex in cell i (since the partition is equitable, this is well
           defined)


        EXAMPLES::

            sage: G = graphs.PetersenGraph()
            sage: G.is_equitable([[0,4],[1,3,5,9],[2,6,8],[7]])
            False
            sage: G.is_equitable([[0,4],[1,3,5,9],[2,6,8,7]])
            True
            sage: G.is_equitable([[0,4],[1,3,5,9],[2,6,8,7]], quotient_matrix=True)
            [1 2 0]
            [1 0 2]
            [0 2 1]

        ::

            sage: ss = (graphs.WheelGraph(6)).line_graph(labels=False)
            sage: prt = [[(0, 1)], [(0, 2), (0, 3), (0, 4), (1, 2), (1, 4)], [(2, 3), (3, 4)]]

        ::

            sage: ss.is_equitable(prt)
            Traceback (most recent call last):
            ...
            TypeError: Partition ([[(0, 1)], [(0, 2), (0, 3), (0, 4), (1, 2), (1, 4)], [(2, 3), (3, 4)]]) is not valid for this graph: vertices are incorrect.

        ::

            sage: ss = (graphs.WheelGraph(5)).line_graph(labels=False)
            sage: ss.is_equitable(prt)
            False
        """
        from sage.misc.flatten import flatten
        from sage.misc.misc import uniq
        if sorted(flatten(partition, max_level=1)) != self.vertices():
            raise TypeError("Partition (%s) is not valid for this graph: vertices are incorrect."%partition)
        if any(len(cell)==0 for cell in partition):
            raise TypeError("Partition (%s) is not valid for this graph: there is a cell of length 0."%partition)
        if quotient_matrix:
            from sage.matrix.constructor import Matrix
            from sage.rings.integer_ring import IntegerRing
            n = len(partition)
            M = Matrix(IntegerRing(), n)
            for i in xrange(n):
                for j in xrange(n):
                    cell_i = partition[i]
                    cell_j = partition[j]
                    degrees = [self.degree_to_cell(u, cell_j) for u in cell_i]
                    if len(uniq(degrees)) > 1:
                        return False
                    if self._directed:
                        M[i, j] = degrees[0][0]
                    else:
                        M[i, j] = degrees[0]
            return M
        else:
            for cell1 in partition:
                for cell2 in partition:
                    degrees = [self.degree_to_cell(u, cell2) for u in cell1]
                    if len(uniq(degrees)) > 1:
                        return False
            return True

    def coarsest_equitable_refinement(self, partition, sparse=True):
        """
        Returns the coarsest partition which is finer than the input
        partition, and equitable with respect to self.

        A partition is equitable with respect to a graph if for every pair
        of cells C1, C2 of the partition, the number of edges from a vertex
        of C1 to C2 is the same, over all vertices in C1.

        A partition P1 is finer than P2 (P2 is coarser than P1) if every
        cell of P1 is a subset of a cell of P2.

        INPUT:


        -  ``partition`` - a list of lists

        -  ``sparse`` - (default False) whether to use sparse
           or dense representation- for small graphs, use dense for speed


        EXAMPLES::

            sage: G = graphs.PetersenGraph()
            sage: G.coarsest_equitable_refinement([[0],range(1,10)])
            [[0], [2, 3, 6, 7, 8, 9], [1, 4, 5]]
            sage: G = graphs.CubeGraph(3)
            sage: verts = G.vertices()
            sage: Pi = [verts[:1], verts[1:]]
            sage: Pi
            [['000'], ['001', '010', '011', '100', '101', '110', '111']]
            sage: G.coarsest_equitable_refinement(Pi)
            [['000'], ['011', '101', '110'], ['111'], ['001', '010', '100']]

        Note that given an equitable partition, this function returns that
        partition::

            sage: P = graphs.PetersenGraph()
            sage: prt = [[0], [1, 4, 5], [2, 3, 6, 7, 8, 9]]
            sage: P.coarsest_equitable_refinement(prt)
            [[0], [1, 4, 5], [2, 3, 6, 7, 8, 9]]

        ::

            sage: ss = (graphs.WheelGraph(6)).line_graph(labels=False)
            sage: prt = [[(0, 1)], [(0, 2), (0, 3), (0, 4), (1, 2), (1, 4)], [(2, 3), (3, 4)]]
            sage: ss.coarsest_equitable_refinement(prt)
            Traceback (most recent call last):
            ...
            TypeError: Partition ([[(0, 1)], [(0, 2), (0, 3), (0, 4), (1, 2), (1, 4)], [(2, 3), (3, 4)]]) is not valid for this graph: vertices are incorrect.

        ::

            sage: ss = (graphs.WheelGraph(5)).line_graph(labels=False)
            sage: ss.coarsest_equitable_refinement(prt)
            [[(0, 1)], [(1, 2), (1, 4)], [(0, 3)], [(0, 2), (0, 4)], [(2, 3), (3, 4)]]

        ALGORITHM: Brendan D. McKay's Master's Thesis, University of
        Melbourne, 1976.
        """
        from sage.misc.flatten import flatten
        if sorted(flatten(partition, max_level=1)) != self.vertices():
            raise TypeError("Partition (%s) is not valid for this graph: vertices are incorrect."%partition)
        if any(len(cell)==0 for cell in partition):
            raise TypeError("Partition (%s) is not valid for this graph: there is a cell of length 0."%partition)
        if self.has_multiple_edges():
            raise TypeError("Refinement function does not support multiple edges.")
        from copy import copy
        G = copy(self)
        perm_to = G.relabel(return_map=True)
        partition = [[perm_to[b] for b in cell] for cell in partition]
        perm_from = {}
        for v in self:
            perm_from[perm_to[v]] = v
        n = G.num_verts()
        if sparse:
            from sage.graphs.base.sparse_graph import SparseGraph
            CG = SparseGraph(n)
        else:
            from sage.graphs.base.dense_graph import DenseGraph
            CG = DenseGraph(n)
        for i in range(n):
            for j in range(n):
                if G.has_edge(i,j):
                    CG.add_arc(i,j)

        from sage.groups.perm_gps.partn_ref.refinement_graphs import coarsest_equitable_refinement
        result = coarsest_equitable_refinement(CG, partition, G._directed)
        return [[perm_from[b] for b in cell] for cell in result]

    def automorphism_group(self, partition=None, translation=False,
                           verbosity=0, edge_labels=False, order=False,
                           return_group=True, orbits=False):
        """
        Returns the largest subgroup of the automorphism group of the
        (di)graph whose orbit partition is finer than the partition given.
        If no partition is given, the unit partition is used and the entire
        automorphism group is given.

        INPUT:


        -  ``translation`` - if True, then output includes a
           dictionary translating from keys == vertices to entries == elements
           of 1,2,...,n (since permutation groups can currently only act on
           positive integers).

        -  ``partition`` - default is the unit partition,
           otherwise computes the subgroup of the full automorphism group
           respecting the partition.

        -  ``edge_labels`` - default False, otherwise allows
           only permutations respecting edge labels.

        -  ``order`` - (default False) if True, compute the
           order of the automorphism group

        -  ``return_group`` - default True

        -  ``orbits`` - returns the orbits of the group acting
           on the vertices of the graph


        OUTPUT: The order of the output is group, translation, order,
        orbits. However, there are options to turn each of these on or
        off.

        EXAMPLES: Graphs::

            sage: graphs_query = GraphQuery(display_cols=['graph6'],num_vertices=4)
            sage: L = graphs_query.get_graphs_list()
            sage: graphs_list.show_graphs(L)
            sage: for g in L:
            ...    G = g.automorphism_group()
            ...    G.order(), G.gens()
            (24, [(2,3), (1,2), (1,4)])
            (4, [(2,3), (1,4)])
            (2, [(1,2)])
            (8, [(1,2), (1,4)(2,3)])
            (6, [(1,2), (1,4)])
            (6, [(2,3), (1,2)])
            (2, [(1,4)(2,3)])
            (2, [(1,2)])
            (8, [(2,3), (1,3)(2,4), (1,4)])
            (4, [(2,3), (1,4)])
            (24, [(2,3), (1,2), (1,4)])
            sage: C = graphs.CubeGraph(4)
            sage: G = C.automorphism_group()
            sage: M = G.character_table() # random order of rows, thus abs() below
            sage: QQ(M.determinant()).abs()
            712483534798848
            sage: G.order()
            384

        ::

            sage: D = graphs.DodecahedralGraph()
            sage: G = D.automorphism_group()
            sage: A5 = AlternatingGroup(5)
            sage: Z2 = CyclicPermutationGroup(2)
            sage: H = A5.direct_product(Z2)[0] #see documentation for direct_product to explain the [0]
            sage: G.is_isomorphic(H)
            True

        Multigraphs::

            sage: G = Graph(multiedges=True,sparse=True)
            sage: G.add_edge(('a', 'b'))
            sage: G.add_edge(('a', 'b'))
            sage: G.add_edge(('a', 'b'))
            sage: G.automorphism_group()
            Permutation Group with generators [(1,2)]

        Digraphs::

            sage: D = DiGraph( { 0:[1], 1:[2], 2:[3], 3:[4], 4:[0] } )
            sage: D.automorphism_group()
            Permutation Group with generators [(1,2,3,4,5)]

        Edge labeled graphs::

            sage: G = Graph(sparse=True)
            sage: G.add_edges( [(0,1,'a'),(1,2,'b'),(2,3,'c'),(3,4,'b'),(4,0,'a')] )
            sage: G.automorphism_group(edge_labels=True)
            Permutation Group with generators [(1,4)(2,3)]

        ::

            sage: G = Graph({0 : {1 : 7}})
            sage: G.automorphism_group(translation=True, edge_labels=True)
            (Permutation Group with generators [(1,2)], {0: 2, 1: 1})

            sage: foo = Graph(sparse=True)
            sage: bar = Graph(implementation='c_graph',sparse=True)
            sage: foo.add_edges([(0,1,1),(1,2,2), (2,3,3)])
            sage: bar.add_edges([(0,1,1),(1,2,2), (2,3,3)])
            sage: foo.automorphism_group(translation=True, edge_labels=True)
            (Permutation Group with generators [()], {0: 4, 1: 1, 2: 2, 3: 3})
            sage: foo.automorphism_group(translation=True)
            (Permutation Group with generators [(1,2)(3,4)], {0: 4, 1: 1, 2: 2, 3: 3})
            sage: bar.automorphism_group(translation=True, edge_labels=True)
            (Permutation Group with generators [()], {0: 4, 1: 1, 2: 2, 3: 3})
            sage: bar.automorphism_group(translation=True)
            (Permutation Group with generators [(1,2)(3,4)], {0: 4, 1: 1, 2: 2, 3: 3})

        You can also ask for just the order of the group::

            sage: G = graphs.PetersenGraph()
            sage: G.automorphism_group(return_group=False, order=True)
            120

        Or, just the orbits (note that each graph here is vertex transitive)

        ::

            sage: G = graphs.PetersenGraph()
            sage: G.automorphism_group(return_group=False, orbits=True)
            [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]]
            sage: G.automorphism_group(partition=[[0],range(1,10)], return_group=False, orbits=True)
            [[0], [2, 3, 6, 7, 8, 9], [1, 4, 5]]
            sage: C = graphs.CubeGraph(3)
            sage: C.automorphism_group(orbits=True, return_group=False)
            [['000', '001', '010', '011', '100', '101', '110', '111']]

        """
        from sage.groups.perm_gps.partn_ref.refinement_graphs import perm_group_elt, search_tree
        from sage.groups.perm_gps.permgroup import PermutationGroup
        dig = (self._directed or self.has_loops())
        if partition is None:
            partition = [self.vertices()]
        if edge_labels:
            G, partition = graph_isom_equivalent_non_edge_labeled_graph(self, partition)
            G_vertices = sum(partition, [])
            G_to = {}
            for i in xrange(len(G_vertices)):
                G_to[G_vertices[i]] = i
            from sage.graphs.all import Graph, DiGraph
            DoDG = DiGraph if self._directed else Graph
            H = DoDG(len(G_vertices), implementation='c_graph', loops=G.allows_loops())
            HB = H._backend
            for u,v in G.edge_iterator(labels=False):
                u = G_to[u]; v = G_to[v]
                HB.add_edge(u,v,None,G._directed)
            GC = HB._cg
            partition = [[G_to[v] for v in cell] for cell in partition]
            A = search_tree(GC, partition, lab=False, dict_rep=True, dig=dig, verbosity=verbosity, order=order)
            if order:
                a,b,c = A
            else:
                a,b = A
            b_new = {}
            for v in G_to:
                b_new[v] = b[G_to[v]]
            b = b_new
            # b is a translation of the labellings
            acting_vertices = {}
            translation_d = {}
            m = G.order()
            for v in self:
                if b[('o',v)] == m:
                    translation_d[v] = self.order()
                    acting_vertices[v] = 0
                else:
                    translation_d[v] = b[('o',v)]
                    acting_vertices[v] = b[('o',v)]
            real_aut_gp = []
            n = self.order()
            for gen in a:
                gen_restr = [0]*n
                for v in self.vertex_iterator():
                    gen_restr[acting_vertices[v]] = gen[acting_vertices[v]]
                if gen_restr not in real_aut_gp:
                    real_aut_gp.append(gen_restr)
            id = range(n)
            if id in real_aut_gp:
                real_aut_gp.remove(id)
            a = real_aut_gp
            b = translation_d
        elif self.has_multiple_edges():
            G, partition = graph_isom_equivalent_non_multi_graph(self, partition)
            G_vertices = sum(partition, [])
            G_to = {}
            for i in xrange(len(G_vertices)):
                G_to[G_vertices[i]] = i
            from sage.graphs.all import Graph, DiGraph
            DoDG = DiGraph if self._directed else Graph
            H = DoDG(len(G_vertices), implementation='c_graph', loops=G.allows_loops())
            HB = H._backend
            for u,v in G.edge_iterator(labels=False):
                u = G_to[u]; v = G_to[v]
                HB.add_edge(u,v,None,G._directed)
            GC = HB._cg
            partition = [[G_to[v] for v in cell] for cell in partition]
            A = search_tree(GC, partition, lab=False, dict_rep=True, dig=dig, verbosity=verbosity, order=order)
            if order:
                a,b,c = A
            else:
                a,b = A
            b_new = {}
            for v in G_to:
                b_new[v] = b[G_to[v]]
            b = b_new
            # b is a translation of the labellings
            acting_vertices = {}
            translation_d = {}
            m = G.order()
            for v in self:
                if b[('o',v)] == m:
                    translation_d[v] = self.order()
                    acting_vertices[v] = 0
                else:
                    translation_d[v] = b[('o',v)]
                    acting_vertices[v] = b[('o',v)]
            real_aut_gp = []
            n = self.order()
            for gen in a:
                gen_restr = [0]*n
                for v in self.vertex_iterator():
                    gen_restr[acting_vertices[v]] = gen[acting_vertices[v]]
                if gen_restr not in real_aut_gp:
                    real_aut_gp.append(gen_restr)
            id = range(n)
            if id in real_aut_gp:
                real_aut_gp.remove(id)
            a = real_aut_gp
            b = translation_d
        else:
            G_vertices = sum(partition, [])
            G_to = {}
            for i in xrange(len(G_vertices)):
                G_to[G_vertices[i]] = i
            from sage.graphs.all import Graph, DiGraph
            DoDG = DiGraph if self._directed else Graph
            H = DoDG(len(G_vertices), implementation='c_graph', loops=self.allows_loops())
            HB = H._backend
            for u,v in self.edge_iterator(labels=False):
                u = G_to[u]; v = G_to[v]
                HB.add_edge(u,v,None,self._directed)
            GC = HB._cg
            partition = [[G_to[v] for v in cell] for cell in partition]
            if translation:
                A = search_tree(GC, partition, dict_rep=True, lab=False, dig=dig, verbosity=verbosity, order=order)
                if order:
                    a,b,c = A
                else:
                    a,b = A
                b_new = {}
                for v in G_to:
                    b_new[v] = b[G_to[v]]
                b = b_new
            else:
                a = search_tree(GC, partition, dict_rep=False, lab=False, dig=dig, verbosity=verbosity, order=order)
                if order:
                    a,c = a
        output = []
        if return_group:
            if len(a) != 0:
                output.append(PermutationGroup([perm_group_elt(aa) for aa in a]))
            else:
                output.append(PermutationGroup([[]]))
        if translation:
            output.append(b)
        if order:
            output.append(c)
        if orbits:
            G_from = {}
            for v in G_to:
                G_from[G_to[v]] = v
            from sage.groups.perm_gps.partn_ref.refinement_graphs import get_orbits
            output.append([[G_from[v] for v in W] for W in get_orbits(a, self.num_verts())])

        # A Python switch statement!
        return { 0: None,
                 1: output[0],
                 2: tuple(output),
                 3: tuple(output),
                 4: tuple(output)
               }[len(output)]

    def is_vertex_transitive(self, partition=None, verbosity=0,
                           edge_labels=False, order=False,
                           return_group=True, orbits=False):
        """
        Returns whether the automorphism group of self is transitive within
        the partition provided, by default the unit partition of the
        vertices of self (thus by default tests for vertex transitivity in
        the usual sense).

        EXAMPLES::

            sage: G = Graph({0:[1],1:[2]})
            sage: G.is_vertex_transitive()
            False
            sage: P = graphs.PetersenGraph()
            sage: P.is_vertex_transitive()
            True
            sage: D = graphs.DodecahedralGraph()
            sage: D.is_vertex_transitive()
            True
            sage: R = graphs.RandomGNP(2000, .01)
            sage: R.is_vertex_transitive()
            False
        """
        if partition is None:
            partition = [self.vertices()]
        new_partition = self.automorphism_group(partition,
                          verbosity=verbosity, edge_labels=edge_labels,
                          order=False, return_group=False, orbits=True)
        for cell in partition:
            for new_cell in new_partition:
                if cell[0] in new_cell:
                    if any([c not in new_cell for c in cell[1:]]):
                        return False
        return True

    def is_hamiltonian(self):
        r"""
        Tests whether the current graph is Hamiltonian

        A graph (resp. digraph) is said to be hamiltonian
        if it contains as a subgraph a cycle (resp. a circuit)
        going through all the vertices.

        Testing for hamiltonicity being NP-Complete, this
        algorithm could run for some time depending on
        the instance.

        ALGORITHM:

        See ``Graph.traveling_salesman_problem``.

        OUTPUT:

        Returns ``True`` if a hamiltonian cycle/circuit exists, and
        ``False`` otherwise.

        NOTE:

        This function, as ``hamiltonian_cycle`` and
        ``traveling_salesman_problem``, computes a hamiltonian
        cycle if it exists : the user should *NOT* test for
        hamiltonicity using ``is_hamiltonian`` before calling
        ``hamiltonian_cycle`` or ``traveling_salesman_problem``
        as it would result in computing it twice.

        EXAMPLES:

        The Heawood Graph is known to be hamiltonian ::

            sage: g = graphs.HeawoodGraph()
            sage: g.is_hamiltonian()
            True

        The Petergraph, though, is not ::

            sage: g = graphs.PetersenGraph()
            sage: g.is_hamiltonian()
            False

        TESTS:

        When no solver is installed, a
        ``OptionalPackageNotFoundError`` exception is raised::

            sage: from sage.misc.exceptions import OptionalPackageNotFoundError
            sage: try:
            ...       g = graphs.ChvatalGraph()
            ...       if not g.is_hamiltonian():
            ...          print "There is something wrong here !"
            ... except OptionalPackageNotFoundError:
            ...       pass
        """

        try:
            tsp = self.traveling_salesman_problem(weighted = False)
            return True

        except ValueError:
            return False

    def is_isomorphic(self, other, certify=False, verbosity=0, edge_labels=False):
        """
        Tests for isomorphism between self and other.

        INPUT:


        -  ``certify`` - if True, then output is (a,b), where a
           is a boolean and b is either a map or None.

        -  ``edge_labels`` - default False, otherwise allows
           only permutations respecting edge labels.


        EXAMPLES: Graphs::

            sage: from sage.groups.perm_gps.permgroup_named import SymmetricGroup
            sage: D = graphs.DodecahedralGraph()
            sage: E = copy(D)
            sage: gamma = SymmetricGroup(20).random_element()
            sage: E.relabel(gamma)
            sage: D.is_isomorphic(E)
            True

        ::

            sage: D = graphs.DodecahedralGraph()
            sage: S = SymmetricGroup(20)
            sage: gamma = S.random_element()
            sage: E = copy(D)
            sage: E.relabel(gamma)
            sage: a,b = D.is_isomorphic(E, certify=True); a
            True
            sage: from sage.plot.plot import GraphicsArray
            sage: from sage.graphs.generic_graph_pyx import spring_layout_fast
            sage: position_D = spring_layout_fast(D)
            sage: position_E = {}
            sage: for vert in position_D:
            ...    position_E[b[vert]] = position_D[vert]
            sage: GraphicsArray([D.plot(pos=position_D), E.plot(pos=position_E)]).show() # long time

        ::

            sage: g=graphs.HeawoodGraph()
            sage: g.is_isomorphic(g)
            True

        Multigraphs::

            sage: G = Graph(multiedges=True,sparse=True)
            sage: G.add_edge((0,1,1))
            sage: G.add_edge((0,1,2))
            sage: G.add_edge((0,1,3))
            sage: G.add_edge((0,1,4))
            sage: H = Graph(multiedges=True,sparse=True)
            sage: H.add_edge((3,4))
            sage: H.add_edge((3,4))
            sage: H.add_edge((3,4))
            sage: H.add_edge((3,4))
            sage: G.is_isomorphic(H)
            True

        Digraphs::

            sage: A = DiGraph( { 0 : [1,2] } )
            sage: B = DiGraph( { 1 : [0,2] } )
            sage: A.is_isomorphic(B, certify=True)
            (True, {0: 1, 1: 0, 2: 2})

        Edge labeled graphs::

            sage: G = Graph(sparse=True)
            sage: G.add_edges( [(0,1,'a'),(1,2,'b'),(2,3,'c'),(3,4,'b'),(4,0,'a')] )
            sage: H = G.relabel([1,2,3,4,0], inplace=False)
            sage: G.is_isomorphic(H, edge_labels=True)
            True

        TESTS::

            sage: g1 = '~?A[~~{ACbCwV_~__OOcCW_fAA{CF{CCAAAC__bCCCwOOV___~____OOOOcCCCW___fAAAA'+\
            ...   '{CCCF{CCCCAAAAAC____bCCCCCwOOOOV_____~_O@ACG_@ACGOo@ACG?{?`A?GV_GO@AC}@?_OGC'+\
            ...   'C?_OI@?K?I@?_OM?_OGD?F_A@OGC@{A@?_OG?O@?gCA?@_GCA@O?B_@OGCA?BoA@?gC?@{A?GO`?'+\
            ...   '??_GO@AC??E?O`?CG??[?O`A?G??{?GO`A???|A?_GOC`AC@_OCGACEAGS?HA?_SA`aO@G?cOC_N'+\
            ...   'G_C@AOP?GnO@_GACOE?g?`OGACCOGaGOc?HA?`GORCG_AO@B?K@[`A?OCI@A@By?_K@?SCABA?H?'+\
            ...   'SA?a@GC`CH?Q?C_c?cGRC@G_AOCOa@Ax?QC?_GOo_CNg@A?oC@CaCGO@CGA_O`?GSGPAGOC_@OO_'+\
            ...   'aCHaG?cO@CB?_`Ax?GQC?_cAOCG^OGAC@_D?IGO`?D?O_I?HAOO`AGOHA?cC?oAO`AW_Q?HCACAC'+\
            ...   'GO`[_OCHA?_cCACG^O_@CAGO`A?GCOGc@?I?OQOC?IGC_o@CAGCCE?A@DBG_OA@C_CP?OG_VA_CO'+\
            ...   'G@D?_OA_DFgA@CO?aH?Ga@?a?_I?S@A@@Oa@?@P@GCO_AACO_a_?`K_GCQ@?cAOG_OGAwQ@?K?cC'+\
            ...   'GH?I?ABy@C?G_S@@GCA@C`?OI?_D?OP@G?IGGP@O_AGCP?aG?GCPAX?cA?OGSGCGCAGCJ`?oAGCC'+\
            ...   'HAA?A_CG^O@CAG_GCSCAGCCGOCG@OA_`?`?g_OACG_`CAGOAO_H?a_?`AXA?OGcAAOP?a@?CGVAC'+\
            ...   'OG@_AGG`OA_?O`|?Ga?COKAAGCA@O`A?a?S@?HCG`?_?gO`AGGaC?PCAOGI?A@GO`K_CQ@?GO_`O'+\
            ...   'GCAACGVAG@_COOCQ?g?I?O`ByC?G_P?O`A?H@G?_P?`OAGC?gD?_C@_GCAGDG_OA@CCPC?AOQ??g'+\
            ...   '_R@_AGCO____OCC_@OAbaOC?g@C_H?AOOC@?a`y?PC?G`@OOH??cOG_OOAG@_COAP?WA?_KAGC@C'+\
            ...   '_CQ@?HAACH??c@P?_AWGaC?P?gA_C_GAD?I?Awa?S@?K?`C_GAOGCS?@|?COGaA@CAAOQ?AGCAGO'+\
            ...   'ACOG@_G_aC@_G@CA@@AHA?OGc?WAAH@G?P?_?cH_`CAGOGACc@@GA?S?CGVCG@OA_CICAOOC?PO?'+\
            ...   'OG^OG_@CAC_cC?AOP?_OICG@?oAGCO_GO_GB@?_OG`AH?cA?OH?`P??cC_O?SCGR@O_AGCAI?Q?_'+\
            ...   'GGS?D?O`[OI?_D@@CCA?cCA_?_O`By?_PC?IGAGOQ?@A@?aO`A?Q@?K?__`_E?_GCA@CGO`C_GCQ'+\
            ...   '@A?gAOQ?@C?DCACGR@GCO_AGPA@@GAA?A_CO`Aw_I?S@?SCB@?OC_?_P@ACNgOC@A?aCGOCAGCA@'+\
            ...   'CA?H@GG_C@AOGa?OOG_O?g_OA?oDC_AO@GOCc?@P?_A@D??cC``O?cGAOGD?@OA_CAGCA?_cwKA?'+\
            ...   '`?OWGG?_PO?I?S?H@?^OGAC@_Aa@CAGC?a@?_Q?@H?_OCHA?OQA_P?_G_O?WA?_IG_Q?HC@A@ADC'+\
            ...   'A?AI?AC_?QAWOHA?cAGG_I?S?G_OG@GA?`[D?O_IA?`GGCS?OA_?c@?Q?^OAC@_G_Ca@CA@?OGCO'+\
            ...   'H@G@A@?GQC?_Q@GP?_OG?IGGB?OCGaG?cO@A__QGC?E?A@CH@G?GRAGOC_@GGOW@O?O_OGa?_c?G'+\
            ...   'V@CGA_OOaC?a_?a?A_CcC@?CNgA?oC@GGE@?_OH?a@?_?QA`A@?QC?_KGGO_OGCAa@?A?_KCGPC@'+\
            ...   'G_AOAGPGC?D@?a_A?@GGO`KH?Q?C_QGAA_?gOG_OA?_GG`AwH?SA?`?cAI?A@D?I?@?QA?`By?K@'+\
            ...   '?O`GGACA@CGCA@CC_?WO`?`A?OCH?`OCA@COG?I?oC@ACGPCG_AO@_aAA?Aa?g?GD@G?CO`AWOc?'+\
            ...   'HA?OcG_?g@OGCAAAOC@ACJ_`OGACAGCS?CAGI?A`@?OCACG^'
            sage: g2 = '~?A[??osR?WARSETCJ_QWASehOXQg`QwChK?qSeFQ_sTIaWIV?XIR?KAC?B?`?COCG?o?O_'+\
            ...   '@_?`??B?`?o@_O_WCOCHC@_?`W?E?AD_O?WCCeO?WCSEGAGAIaA@_?aw?OK?ER?`?@_HQXA?B@Q_'+\
            ...   'pA?a@Qg_`?o?h[?GOK@IR?@A?BEQcoCG?K\IB?GOCWiTC?GOKWIV??CGEKdH_H_?CB?`?DC??_WC'+\
            ...   'G?SO?AP?O_?g_?D_?`?C__?D_?`?CCo??@_O_XDC???WCGEGg_??a?`G_aa??E?AD_@cC??K?CJ?'+\
            ...   '@@K?O?WCCe?aa?G?KAIB?Gg_A?a?ag_@DC?OK?CV??EOO@?o?XK??GH`A?B?Qco?Gg`A?B@Q_o?C'+\
            ...   'SO`?P?hSO?@DCGOK?IV???K_`A@_HQWC??_cCG?KXIRG?@D?GO?WySEG?@D?GOCWiTCC??a_CGEK'+\
            ...   'DJ_@??K_@A@bHQWAW?@@K??_WCG?g_?CSO?A@_O_@P??Gg_?Ca?`?@P??Gg_?D_?`?C__?EOO?Ao'+\
            ...   '?O_AAW?@@K???WCGEPP??Gg_??B?`?pDC??aa??AGACaAIG?@DC??K?CJ?BGG?@cC??K?CJ?@@K?'+\
            ...   '?_e?G?KAAR?PP??Gg_A?B?a_oAIG?@DC?OCOCTC?Gg_?CSO@?o?P[??X@??K__A@_?qW??OR??GH'+\
            ...   '`A?B?Qco?Gg_?CSO`?@_hOW?AIG?@DCGOCOITC??PP??Gg`A@_@Qw??@cC??qACGE?dH_O?AAW?@'+\
            ...   '@GGO?WqSeO?AIG?@D?GO?WySEG?@DC??a_CGAKTIaA??PP??Gg@A@b@Qw?O?BGG?@c?GOKXIR?KA'+\
            ...   'C?H_?CCo?A@_O_?WCG@P??Gg_?CB?`?COCG@P??Gg_?Ca?`?E?AC?g_?CSO?Ao?O_@_?`@GG?@cC'+\
            ...   '??k?CG??WCGOR??GH_??B?`?o@_O`DC??aa???KACB?a?`AIG?@DC??COCHC@_?`AIG?@DC??K?C'+\
            ...   'J??o?O`cC??qA??E?AD_O?WC?OR??GH_A?B?_cq?B?_AIG?@DC?O?WCSEGAGA?Gg_?CSO@?P?PSO'+\
            ...   'OK?C?PP??Gg_A@_?aw?OK?C?X@??K__A@_?qWCG?K??GH_?CCo`?@_HQXA?B??AIG?@DCGO?WISE'+\
            ...   'GOCO??PP??Gg`A?a@Qg_`?o??@DC??aaCGE?DJ_@A@_??BGG?@cCGOK@IR?@A?BO?AAW?@@GGO?W'+\
            ...   'qSe?`?@g?@DC??a_CG?K\IB?GOCQ??PP??Gg@A?bDQg_@A@_O?AIG?@D?GOKWIV??CGE@??K__?E'+\
            ...   'O?`?pchK?_SA_OI@OGD?gCA_SA@OI?c@H?Q?c_H?QOC_HGAOCc?QOC_HGAOCc@GAQ?c@H?QD?gCA'+\
            ...   '_SA@OI@?gD?_SA_OKA_SA@OI@?gD?_SA_OI@OHI?c_H?QOC_HGAOCc@GAQ?eC_H?QOC_HGAOCc@G'+\
            ...   'AQ?c@XD?_SA_OI@OGD?gCA_SA@PKGO`A@ACGSGO`?`ACICGO_?ACGOcGO`?O`AC`ACHACGO???^?'+\
            ...   '????}Bw????Fo^???????Fo?}?????Bw?^?Bw?????GO`AO`AC`ACGACGOcGO`??aCGO_O`ADACG'+\
            ...   'OGO`A@ACGOA???@{?N_@{?????Fo?}????OFo????N_}????@{????Bw?OACGOgO`A@ACGSGO`?`'+\
            ...   'ACG?OaCGO_GO`AO`AC`ACGACGO_@G???Fo^?????}Bw????Fo??AC@{?????Fo?}?Fo?????^??A'+\
            ...   'OGO`AO`AC@ACGQCGO_GO`A?HAACGOgO`A@ACGOGO`A`ACG?GQ??^?Bw?????N_@{?????Fo?QC??'+\
            ...   'Fo^?????}????@{Fo???CHACGO_O`ACACGOgO`A@ACGO@AOcGO`?O`AC`ACGACGOcGO`?@GQFo??'+\
            ...   '??N_????^@{????Bw??`GRw?????N_@{?????Fo?}???HAO_OI@OGD?gCA_SA@OI@?gDK_??C@GA'+\
            ...   'Q?c@H?Q?c_H?QOC_HEW????????????????????????~~~~~'
            sage: G1 = Graph(g1)
            sage: G2 = Graph(g2)
            sage: G1.is_isomorphic(G2)
            True

        """
        possible = True
        if self._directed != other._directed:
            possible = False
        if self.order() != other.order():
            possible = False
        if self.size() != other.size():
            possible = False
        if not possible and certify:
            return False, None
        elif not possible:
            return False
        self_vertices = self.vertices()
        other_vertices = other.vertices()
        if edge_labels:
            if sorted(self.edge_labels()) != sorted(other.edge_labels()):
                return False, None if certify else False
            else:
                G, partition = graph_isom_equivalent_non_edge_labeled_graph(self, [self_vertices])
                self_vertices = sum(partition,[])
                G2, partition2 = graph_isom_equivalent_non_edge_labeled_graph(other, [other_vertices])
                partition2 = sum(partition2,[])
                other_vertices = partition2
        elif self.has_multiple_edges():
            G, partition = graph_isom_equivalent_non_multi_graph(self, [self_vertices])
            self_vertices = sum(partition,[])
            G2, partition2 = graph_isom_equivalent_non_multi_graph(other, [other_vertices])
            partition2 = sum(partition2,[])
            other_vertices = partition2
        else:
            G = self; partition = [self_vertices]
            G2 = other; partition2 = other_vertices



        G_to = {}
        for i in xrange(len(self_vertices)):
            G_to[self_vertices[i]] = i
        from sage.graphs.all import Graph, DiGraph
        DoDG = DiGraph if self._directed else Graph
        H = DoDG(len(self_vertices), implementation='c_graph', loops=G.allows_loops())
        HB = H._backend
        for u,v in G.edge_iterator(labels=False):
            u = G_to[u]; v = G_to[v]
            HB.add_edge(u,v,None,G._directed)
        G = HB._cg
        partition = [[G_to[v] for v in cell] for cell in partition]
        GC = G
        G2_to = {}
        for i in xrange(len(other_vertices)):
            G2_to[other_vertices[i]] = i
        H2 = DoDG(len(other_vertices), implementation='c_graph', loops=G2.allows_loops())
        H2B = H2._backend
        for u,v in G2.edge_iterator(labels=False):
            u = G2_to[u]; v = G2_to[v]
            H2B.add_edge(u,v,None,G2._directed)
        G2 = H2B._cg
        partition2 = [G2_to[v] for v in partition2]
        GC2 = G2
        isom = isomorphic(GC, GC2, partition, partition2, (self._directed or self.has_loops()), 1)
        if not isom and certify:
            return False, None
        elif not isom:
            return False
        elif not certify:
            return True
        else:
            isom_trans = {}
            for v in isom:
                isom_trans[self_vertices[v]] = G2_to[isom[v]]
            return True, isom_trans

    def canonical_label(self, partition=None, certify=False, verbosity=0, edge_labels=False):
        """
        Returns the unique graph on \{0,1,...,n-1\} ( n = self.order() ) which

        - is isomorphic to self,

        - is invariant in the isomorphism class.

        In other words, given two graphs ``G`` and ``H`` which are isomorphic,
        suppose ``G_c`` and ``H_c`` are the graphs returned by
        ``canonical_label``. Then the following hold:

        - ``G_c == H_c``

        - ``G_c.adjacency_matrix() == H_c.adjacency_matrix()``

        - ``G_c.graph6_string() == H_c.graph6_string()``

        INPUT:

        -  ``partition`` - if given, the canonical label with
           respect to this set partition will be computed. The default is the unit
           set partition.

        -  ``certify`` - if True, a dictionary mapping from the
           (di)graph to its canonical label will be given.

        -  ``verbosity`` - gets passed to nice: prints helpful
           output.

        -  ``edge_labels`` - default False, otherwise allows
           only permutations respecting edge labels.


        EXAMPLES::

            sage: D = graphs.DodecahedralGraph()
            sage: E = D.canonical_label(); E
            Dodecahedron: Graph on 20 vertices
            sage: D.canonical_label(certify=True)
            (Dodecahedron: Graph on 20 vertices, {0: 0, 1: 19, 2: 16, 3: 15, 4: 9, 5: 1, 6: 10, 7: 8, 8: 14, 9: 12, 10: 17, 11: 11, 12: 5, 13: 6, 14: 2, 15: 4, 16: 3, 17: 7, 18: 13, 19: 18})
            sage: D.is_isomorphic(E)
            True

        Multigraphs::

            sage: G = Graph(multiedges=True,sparse=True)
            sage: G.add_edge((0,1))
            sage: G.add_edge((0,1))
            sage: G.add_edge((0,1))
            sage: G.canonical_label()
            Multi-graph on 2 vertices
            sage: Graph('A?', implementation='c_graph').canonical_label()
            Graph on 2 vertices

        Digraphs::

            sage: P = graphs.PetersenGraph()
            sage: DP = P.to_directed()
            sage: DP.canonical_label().adjacency_matrix()
            [0 0 0 0 0 0 0 1 1 1]
            [0 0 0 0 1 0 1 0 0 1]
            [0 0 0 1 0 0 1 0 1 0]
            [0 0 1 0 0 1 0 0 0 1]
            [0 1 0 0 0 1 0 0 1 0]
            [0 0 0 1 1 0 0 1 0 0]
            [0 1 1 0 0 0 0 1 0 0]
            [1 0 0 0 0 1 1 0 0 0]
            [1 0 1 0 1 0 0 0 0 0]
            [1 1 0 1 0 0 0 0 0 0]

        Edge labeled graphs::

            sage: G = Graph(sparse=True)
            sage: G.add_edges( [(0,1,'a'),(1,2,'b'),(2,3,'c'),(3,4,'b'),(4,0,'a')] )
            sage: G.canonical_label(edge_labels=True)
            Graph on 5 vertices
            sage: G.canonical_label(edge_labels=True,certify=True)
            (Graph on 5 vertices, {0: 4, 1: 3, 2: 0, 3: 1, 4: 2})
        """
        import sage.groups.perm_gps.partn_ref.refinement_graphs
        from sage.groups.perm_gps.partn_ref.refinement_graphs import search_tree
        from copy import copy

        dig = (self.has_loops() or self._directed)
        if partition is None:
            partition = [self.vertices()]
        if edge_labels:
            G, partition = graph_isom_equivalent_non_edge_labeled_graph(self, partition)
            G_vertices = sum(partition, [])
            G_to = {}
            for i in xrange(len(G_vertices)):
                G_to[G_vertices[i]] = i
            from sage.graphs.all import Graph, DiGraph
            DoDG = DiGraph if self._directed else Graph
            H = DoDG(len(G_vertices), implementation='c_graph', loops=G.allows_loops())
            HB = H._backend
            for u,v in G.edge_iterator(labels=False):
                u = G_to[u]; v = G_to[v]
                HB.add_edge(u,v,None,G._directed)
            GC = HB._cg
            partition = [[G_to[v] for v in cell] for cell in partition]
            a,b,c = search_tree(GC, partition, certify=True, dig=dig, verbosity=verbosity)
            # c is a permutation to the canonical label of G, which depends only on isomorphism class of self.
            H = copy(self)
            c_new = {}
            for v in self.vertices():
                c_new[v] = c[G_to[('o',v)]]
            H.relabel(c_new)
            if certify:
                return H, c_new
            else:
                return H
        if self.has_multiple_edges():
            G, partition = graph_isom_equivalent_non_multi_graph(self, partition)
            G_vertices = sum(partition, [])
            G_to = {}
            for i in xrange(len(G_vertices)):
                G_to[G_vertices[i]] = i
            from sage.graphs.all import Graph, DiGraph
            DoDG = DiGraph if self._directed else Graph
            H = DoDG(len(G_vertices), implementation='c_graph', loops=G.allows_loops())
            HB = H._backend
            for u,v in G.edge_iterator(labels=False):
                u = G_to[u]; v = G_to[v]
                HB.add_edge(u,v,None,G._directed)
            GC = HB._cg
            partition = [[G_to[v] for v in cell] for cell in partition]
            a,b,c = search_tree(GC, partition, certify=True, dig=dig, verbosity=verbosity)
            # c is a permutation to the canonical label of G, which depends only on isomorphism class of self.
            H = copy(self)
            c_new = {}
            for v in self.vertices():
                c_new[v] = c[G_to[('o',v)]]
            H.relabel(c_new)
            if certify:
                return H, c_new
            else:
                return H
        G_vertices = sum(partition, [])
        G_to = {}
        for i in xrange(len(G_vertices)):
            G_to[G_vertices[i]] = i
        from sage.graphs.all import Graph, DiGraph
        DoDG = DiGraph if self._directed else Graph
        H = DoDG(len(G_vertices), implementation='c_graph', loops=self.allows_loops())
        HB = H._backend
        for u,v in self.edge_iterator(labels=False):
            u = G_to[u]; v = G_to[v]
            HB.add_edge(u,v,None,self._directed)
        GC = HB._cg
        partition = [[G_to[v] for v in cell] for cell in partition]
        a,b,c = search_tree(GC, partition, certify=True, dig=dig, verbosity=verbosity)
        H = copy(self)
        c_new = {}
        for v in G_to:
            c_new[v] = c[G_to[v]]
        H.relabel(c_new)
        if certify:
            return H, c_new
        else:
            return H






def tachyon_vertex_plot(g, bgcolor=(1,1,1),
                        vertex_colors=None,
                        vertex_size=0.06,
                        pos3d=None,
                        **kwds):
    """
    Helper function for plotting graphs in 3d with Tachyon. Returns a
    plot containing only the vertices, as well as the 3d position
    dictionary used for the plot.

    INPUT:
     - `pos3d` - a 3D layout of the vertices
     - various rendering options

    EXAMPLES::

        sage: G = graphs.TetrahedralGraph()
        sage: from sage.graphs.generic_graph import tachyon_vertex_plot
        sage: T,p = tachyon_vertex_plot(G, pos3d = G.layout(dim=3))
        sage: type(T)
        <class 'sage.plot.plot3d.tachyon.Tachyon'>
        sage: type(p)
        <type 'dict'>
    """
    assert pos3d is not None
    from math import sqrt
    from sage.plot.plot3d.tachyon import Tachyon

    c = [0,0,0]
    r = []
    verts = g.vertices()

    if vertex_colors is None:
        vertex_colors = { (1,0,0) : verts }
    try:
        for v in verts:
            c[0] += pos3d[v][0]
            c[1] += pos3d[v][1]
            c[2] += pos3d[v][2]
    except KeyError:
        raise KeyError, "Oops! You haven't specified positions for all the vertices."

    order = g.order()
    c[0] = c[0]/order
    c[1] = c[1]/order
    c[2] = c[2]/order
    for v in verts:
        pos3d[v][0] = pos3d[v][0] - c[0]
        pos3d[v][1] = pos3d[v][1] - c[1]
        pos3d[v][2] = pos3d[v][2] - c[2]
        r.append(abs(sqrt((pos3d[v][0])**2 + (pos3d[v][1])**2 + (pos3d[v][2])**2)))
    r = max(r)
    if r == 0:
        r = 1
    for v in verts:
        pos3d[v][0] = pos3d[v][0]/r
        pos3d[v][1] = pos3d[v][1]/r
        pos3d[v][2] = pos3d[v][2]/r
    TT = Tachyon(camera_center=(1.4,1.4,1.4), antialiasing=13, **kwds)
    TT.light((4,3,2), 0.02, (1,1,1))
    TT.texture('bg', ambient=1, diffuse=1, specular=0, opacity=1.0, color=bgcolor)
    TT.plane((-1.6,-1.6,-1.6), (1.6,1.6,1.6), 'bg')

    i = 0
    for color in vertex_colors:
        i += 1
        TT.texture('node_color_%d'%i, ambient=0.1, diffuse=0.9,
                   specular=0.03, opacity=1.0, color=color)
        for v in vertex_colors[color]:
            TT.sphere((pos3d[v][0],pos3d[v][1],pos3d[v][2]), vertex_size, 'node_color_%d'%i)

    return TT, pos3d


def graph_isom_equivalent_non_multi_graph(g, partition):
    r"""
    Helper function for canonical labeling of multi-(di)graphs.

    The idea for this function is that the main algorithm for computing
    isomorphism of graphs does not allow multiple edges. Instead of
    making some very difficult changes to that, we can simply modify
    the multigraph into a non-multi graph that carries essentially the
    same information. For each pair of vertices `\{u,v\}`, if
    there is at most one edge between `u` and `v`, we
    do nothing, but if there are more than one, we split each edge into
    two, introducing a new vertex. These vertices really represent
    edges, so we keep them in their own part of a partition - to
    distinguish them from genuine vertices. Then the canonical label
    and automorphism group is computed, and in the end, we strip off
    the parts of the generators that describe how these new vertices
    move, and we have the automorphism group of the original
    multi-graph. Similarly, by putting the additional vertices in their
    own cell of the partition, we guarantee that the relabeling leading
    to a canonical label moves genuine vertices amongst themselves, and
    hence the canonical label is still well-defined, when we forget
    about the additional vertices.

    EXAMPLES::

        sage: from sage.graphs.generic_graph import graph_isom_equivalent_non_multi_graph
        sage: G = Graph(multiedges=True,sparse=True)
        sage: G.add_edge((0,1,1))
        sage: G.add_edge((0,1,2))
        sage: G.add_edge((0,1,3))
        sage: graph_isom_equivalent_non_multi_graph(G, [[0,1]])
        (Graph on 5 vertices, [[('o', 0), ('o', 1)], [('x', 0), ('x', 1), ('x', 2)]])
    """
    from sage.graphs.all import Graph, DiGraph
    if g._directed:
        G = DiGraph(loops=g.allows_loops())
    else:
        G = Graph(loops=g.allows_loops())
    G.add_vertices([('o', v) for v in g.vertices()]) # 'o' for original
    if g._directed:
        edges_with_multiplicity = [[u,v] for u,v,_ in g.edge_iterator()]
    else:
        edges_with_multiplicity = [sorted([u,v]) for u,v,_ in g.edge_iterator()]
    index = 0
    while len(edges_with_multiplicity) > 0:
        [u,v] = edges_with_multiplicity.pop(0)
        m = edges_with_multiplicity.count([u,v]) + 1
        if m == 1:
            G.add_edge((('o',u),('o',v)))
        else:
            for _ in xrange(m):
                G.add_edges([(('o',u), ('x', index)), (('x', index), ('o',v))]) # 'x' for extra
                index += 1
            edges_with_multiplicity = [e for e in edges_with_multiplicity if e != [u,v]]
    new_partition = [[('o',v) for v in cell] for cell in partition] + [[('x',i) for i in xrange(index)]]
    return G, new_partition


def graph_isom_equivalent_non_edge_labeled_graph(g, partition):
    """
    Helper function for canonical labeling of edge labeled (di)graphs.

    Translates to a bipartite incidence-structure type graph
    appropriate for computing canonical labels of edge labeled graphs.
    Note that this is actually computationally equivalent to
    implementing a change on an inner loop of the main algorithm-
    namely making the refinement procedure sort for each label.

    If the graph is a multigraph, it is translated to a non-multigraph,
    where each edge is labeled with a dictionary describing how many
    edges of each label were originally there. Then in either case we
    are working on a graph without multiple edges. At this point, we
    create another (bipartite) graph, whose left vertices are the
    original vertices of the graph, and whose right vertices represent
    the edges. We partition the left vertices as they were originally,
    and the right vertices by common labels: only automorphisms taking
    edges to like-labeled edges are allowed, and this additional
    partition information enforces this on the bipartite graph.

    EXAMPLES::

        sage: G = Graph(multiedges=True,sparse=True)
        sage: G.add_edges([(0,1,i) for i in range(10)])
        sage: G.add_edge(1,2,'string')
        sage: G.add_edge(2,3)
        sage: from sage.graphs.generic_graph import graph_isom_equivalent_non_edge_labeled_graph
        sage: graph_isom_equivalent_non_edge_labeled_graph(G, [G.vertices()])
        (Graph on 7 vertices, [[('o', 0), ('o', 1), ('o', 2), ('o', 3)], [('x', 2)], [('x', 0)], [('x', 1)]])
    """
    from sage.misc.misc import uniq
    from sage.graphs.all import Graph, DiGraph
    if g.has_multiple_edges():
        if g._directed:
            G = DiGraph(loops=g.allows_loops(),sparse=True)
        else:
            G = Graph(loops=g.allows_loops(),sparse=True)
        G.add_vertices(g.vertices())
        for u,v,l in g.edge_iterator():
            if not G.has_edge(u,v):
                G.add_edge(u,v,[[l,1]])
            else:
                label_list = G.edge_label(u,v)
                seen_label = False
                for i in range(len(label_list)):
                    if label_list[i][0] == l:
                        label_list[i][1] += 1
                        seen_label = True
                        break
                if not seen_label:
                    label_list.append([l,1])
        g = G
    if g._directed:
        G = DiGraph(loops=g.allows_loops())
    else:
        G = Graph(loops=g.allows_loops())
    G.add_vertices([('o', v) for v in g.vertices()]) # 'o' for original
    index = 0
    edge_labels = sorted(g.edge_labels())
    i = 1
    while i < len(edge_labels):
        if edge_labels[i] == edge_labels[i-1]:
            edge_labels.pop(i)
        else:
            i += 1
    edge_partition = [[] for _ in xrange(len(edge_labels))]
    i = 0
    for u,v,l in g.edge_iterator():
        index = edge_labels.index(l)
        edge_partition[index].append(i)
        G.add_edges([(('o',u), ('x', i)), (('x', i), ('o',v))]) # 'x' for extra
        i += 1
    new_partition = [[('o',v) for v in cell] for cell in partition] + [[('x',v) for v in a] for a in edge_partition]
    return G, new_partition


