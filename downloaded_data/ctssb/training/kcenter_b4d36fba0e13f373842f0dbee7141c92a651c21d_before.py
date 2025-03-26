"""
Algorithms for k-center problems on graphs
"""
__author__ = 'Konstantin Weddige'
import networkx
import random

from graph import squared_graph, dominating_set, add_missing_edges


def objective(graph, centers):
    """Calculates the distance between nodes and centers.

    :param graph: Graph
    :param centers: list
    :return: float
    """
    if centers:
        # For big k networkx.floyd_warshall_numpy can be faster:
        # distance = networkx.floyd_warshall_numpy(graph)
        # return distance[numpy.ix_([graph.nodes().index(c) for c in centers])].min(axis=0).max(axis=1)[0,0]
        distance = {c: networkx.bellman_ford(graph, c)[1] for c in centers}
        return max([min([distance[c].get(n, float('inf')) for c in centers]) for n in graph.nodes_iter()])
    else:
        return float("inf")


def gonzalez(k, graph, randomized=True, heuristic=None, bellman_ford=False):
    """This function gives a 2-approximation for the k-center problem on a complete graph.
    See "Clustering to minimize the maximum intercluster distance" by
    Teofilo F. Gonzalez for more details.

    :param k: int
    :param graph: Graph
    :return: list
    """

    def distance(node, target):
        try:
            # return networkx.dijkstra_path_length(graph, node, target)
            return networkx.astar_path_length(graph, node, target, heuristic=heuristic)
        except networkx.NetworkXNoPath:
            return float('inf')

    if randomized:
        result = [random.choice(graph.nodes())]
    else:
        result = [graph.nodes()[0], ]
    for l in range(k - 1):
        dist = 0
        head = None
        if bellman_ford:
            distance = {c: networkx.bellman_ford(graph, c)[1] for c in result}
            head = max([
                (n, min([(c, distance[c].get(n, float('inf'))) for c in result], key=lambda i: i[1])[1])
                for n in graph.nodes_iter()
            ], key=lambda i: i[1])[0]
        else:
            for node in graph.nodes():
                tmp_dist = min(distance(node, target) for target in result)
                if tmp_dist > dist:
                    dist = tmp_dist
                    head = node
        if head:
            result.append(head)
        else:
            return result
    return result


def hochbaum_shmoys(k, graph):
    """This function gives a 2-approximation for the k-center problem on a complete graph.
    See "A best possible heuristic for the k-center problem" by
    Dorit S. Hochbaum and David B. Shmoys for more details.

    This implementation follows "k-Center in Verkehrsnetzwerken – ein Vergleich geometrischer
    und graphentheoretischer Ansätze" by Valentin Breuß.

    :param k: int
    :param graph: Graph
    :return: list
    """
    edges = list()
    for edge in sorted(graph.edges(data=True), key=lambda e: e[2]['weight']):
        edges.append(edge)
        squared = networkx.Graph(edges)
        squared.add_nodes_from(graph.nodes())
        squared = squared_graph(squared)
        maximal_independent_set = networkx.maximal_independent_set(squared)
        if len(maximal_independent_set) <= k:
            return maximal_independent_set


def brute_force(k, graph):
    """This function solves the k-center problem on graphs by exhaustive calculations.

    :param k: int
    :param graph: Graph
    :return: list
    """
    graph = add_missing_edges(graph)
    test_graph = networkx.Graph()
    test_graph.add_nodes_from(graph.nodes())
    for edge in sorted(graph.edges(data=True), key=lambda e: e[2]['weight']):
        test_graph.add_edge(*edge)
        result = dominating_set(test_graph, k)  # Das ist langsam
        if result:
            return result


solve = brute_force
approximate = gonzalez