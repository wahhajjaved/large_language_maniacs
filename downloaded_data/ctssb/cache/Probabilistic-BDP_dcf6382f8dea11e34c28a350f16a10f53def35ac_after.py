import os, os.path
import random
import itertools
import copy
import csv

from pbdp.model.hierarchical_map import HierarchicalMap
from pbdp.model.vector2d import Vec2d
from pbdp.model.map import LogicalMap, distance_euclidean
from pbdp.search.astar import astar
from pbdp.search.hpa import hpa_high_level

from pbdp.mcts.optimistic_policy import OptimisticPolicy


def maps_loader():
    """
    Load the map database.
    :return: The map database.
    """
    map_database = {}
    for file in os.listdir('./maps'):
        if file.endswith('.map'):
            map_database[str(file)] = LogicalMap('./maps/' + file)
    return map_database


def abstract_all(map_database, division):
    """
    Given a list of parsed maps, returns a list of abstracted maps.
    :param map_database:
    :param division:
    :return:
    """
    hierarchical_map_database = {}
    for item in map_database.items():
        hierarchical_map_database[item[0]] = HierarchicalMap(item[1], 0.2)
    return hierarchical_map_database


def random_free_cell(map):
    """
    Return a random free cell on the map.
    :param map:
    :return:
    """
    count = 1
    probability = 1
    chosen = None
    for r, c in itertools.product(range(map.height), range(map.width)):
        if map.is_traversable((r, c)):
            if random.random() < probability:
                chosen = (r, c)
            count += 1
            probability = 1.0 / count
    return chosen


def randomize_map(map_abstraction):
    """
    Create a copy of the map with random connected "inter-cluster edges".
    :param map:
    :return:
    """
    map_copy = copy.deepcopy(map_abstraction)
    for edge in map_copy.abstraction_graph.edges:
        if map_copy.is_edge_type(edge, 'inter'):
            if random.random() < -0.01:  # TODO: Make this a PARAMETER
                map_copy.close_edge(edge)
    return map_copy


def random_path(map, map_abstraction):
    while True:
        start = random_free_cell(map)
        end = random_free_cell(map)
        path = hpa_high_level(map_abstraction, Vec2d(start), Vec2d(end), distance_euclidean)
        #print(start)
        #print(end)
        #print(path)
        #print("---")
        if len(path[0]) > 2:
            break
    return start, end
