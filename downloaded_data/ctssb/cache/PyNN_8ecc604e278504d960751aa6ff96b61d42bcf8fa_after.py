"""
 Connection method classes for nest
 $Id$
"""

from pyNN import common
from pyNN.nest2.__init__ import nest, is_number, get_max_delay, get_min_delay
import numpy
# note that WDManager is defined in __init__.py imported here, then imported
# into __init__ through `from connectors import *`. This circularity can't be a
# good thing. Better to define WDManager here?
from pyNN.random import RandomDistribution, NativeRNG
from math import *

def _convertWeight(w, synapse_type):
    weight = w*1000.0
    if isinstance(w, numpy.ndarray):
        all_negative = (weight<=0).all()
        all_positive = (weight>=0).all()
        assert all_negative or all_positive, "Weights must be either all positive or all negative"
        if synapse_type == 'inhibitory':
            if all_positive:
                weight *= -1
    elif is_number(weight):
        if synapse_type == 'inhibitory' and weight > 0:
            weight *= -1
    else:
        raise TypeError("we must be either a number or a numpy array")
    return weight


def get_target_ports(pre, target_list, synapse_type):
    # The connection dict returned by NEST contains a list of target ids,
    # so it is possible to obtain the target port by finding the index of
    # the target in this list. For now, we stick with saving the target port
    # in Python (faster, but more memory needed), but PyNEST should soon have
    # a function to do the lookup, at which point we will switch to using that.
    conn_dict = nest.GetConnections([pre], synapse_type)[0]
    if conn_dict:
        first_port = len(conn_dict['targets'])
    else:
        first_port = 0
    return range(first_port, first_port+len(target_list))


class AllToAllConnector(common.AllToAllConnector):    

    def connect(self, projection):
        postsynaptic_neurons  = projection.post.cell.flatten()
        target_list = postsynaptic_neurons.tolist()
        for pre in projection.pre.cell.flat:
            # if self connections are not allowed, check whether pre and post are the same
            if not self.allow_self_connections:
                target_list = postsynaptic_neurons.tolist()
                if pre in target_list:
                    target_list.remove(pre)
            N = len(target_list)
            weights = self.getWeights(N)
            weights = _convertWeight(weights, projection.synapse_type).tolist()
            delays = self.getDelays(N).tolist()
            projection._targets += target_list
            projection._sources += [pre]*N
            projection._target_ports += get_target_ports(pre, target_list, projection._plasticity_model)
            nest.DivergentConnectWD([pre], target_list, weights, delays)
        return len(projection._targets)

class OneToOneConnector(common.OneToOneConnector):
    
    def connect(self, projection):
        if projection.pre.dim == projection.post.dim:
            projection._sources = projection.pre.cell.flatten()
            projection._targets = projection.post.cell.flatten()
            N = len(projection._sources)
            projection._target_ports = [get_target_ports(pre, [None], projection._plasticity_model)[0] for pre in projection._sources]
            weights = self.getWeights(N)
            weights = _convertWeight(weights, projection.synapse_type).tolist()
            delays = self.getDelays(N).tolist()
            nest.ConnectWD(projection._sources, projection._targets, weights, delays)
            return projection.pre.size
        else:
            raise Exception("OneToOneConnector does not support presynaptic and postsynaptic Populations of different sizes.")
    
class FixedProbabilityConnector(common.FixedProbabilityConnector):
    
    def connect(self, projection):
        postsynaptic_neurons = projection.post.cell_local.flatten()
        npost = projection.post.size
        for pre in projection.pre.cell.flat:
            if projection.rng:
                rarr = projection.rng.uniform(0, 1, (npost,)) # what about NativeRNG?
            else:
                rarr = numpy.random.uniform(0, 1, (npost,))
            if len(rarr) > len(postsynaptic_neurons):
                rarr = rarr[:len(postsynaptic_neurons)]
            target_list = numpy.compress(numpy.less(rarr, self.p_connect), postsynaptic_neurons).tolist()
            # if self connections are not allowed, check whether pre and post are the same
            if not self.allow_self_connections and pre in target_list:
                target_list.remove(pre)
            N = len(target_list)
            weights = self.getWeights(N)
            weights = _convertWeight(weights, projection.synapse_type).tolist()
            delays = self.getDelays(N).tolist()
            projection._targets += target_list
            projection._sources += [pre]*N
            projection._target_ports += get_target_ports(pre, target_list, projection._plasticity_model)
            nest.DivergentConnectWD([pre], target_list, weights, delays)
        return len(projection._sources)
    
class DistanceDependentProbabilityConnector(common.DistanceDependentProbabilityConnector):
    
    def connect(self, projection):
        periodic_boundaries = self.periodic_boundaries
        if periodic_boundaries is not None:
            dimensions = projection.post.dim
            periodic_boundaries = numpy.concatenate((dimensions, numpy.zeros(3-len(dimensions))))
        postsynaptic_neurons = projection.post.cell.flatten() # array
        presynaptic_neurons  = projection.pre.cell.flat # iterator 
        # what about NativeRNG?
        if projection.rng:
            if isinstance(projection.rng, NativeRNG):
                print "Warning: use of NativeRNG not implemented. Using NumpyRNG"
                rng = numpy.random
            else:
                rng = projection.rng
        else:
            rng = numpy.random
        rarr = rng.uniform(0, 1, (projection.pre.size*projection.post.size,))
        j = 0
        idx_post = 0
        for pre in presynaptic_neurons:
            target_list = []
            idx_post = 0
            distances = common.distances(pre, projection.post, self.mask,
                                         self.scale_factor, self.offset,
                                         periodic_boundaries)
            for post in postsynaptic_neurons:
                if self.allow_self_connections or pre != post: 
                    # calculate the distance between the two cells :
                    d = distances[0][idx_post]
                    p = eval(self.d_expression)
                    if p >= 1 or (0 < p < 1 and rarr[j] < p):
                        target_list.append(post)
                        #projection._targets.append(post)
                        #projection._target_ports.append(nest.connect(pre_addr,post_addr))
                        #nest.ConnectWD([pre],[post], [weight], [delay])
                j += 1
                idx_post += 1
            N = len(target_list)
            weights = self.getWeights(N)
            weights = _convertWeight(weights, projection.synapse_type).tolist()
            delays = self.getDelays(N).tolist()
            projection._targets += target_list
            projection._sources += [pre]*N 
            projection._target_ports += get_target_ports(pre, target_list, projection._plasticity_model)
            nest.DivergentConnectWD([pre], target_list, weights, delays)
        return len(projection._sources)


class FixedNumberPreConnector(common.FixedNumberPreConnector):
    
    def connect(self, projection):
        postsynaptic_neurons  = projection.post.cell.flatten()
        if projection.rng:
            rng = projection.rng
        else:
            rng = numpy.random
        for pre in projection.pre.cell.flat:
            if hasattr(self, 'rand_distr'):
                n = self.rand_distr.next()
            else:
                n = self.n
            target_list = rng.permutation(postsynaptic_neurons)[0:n]
            # if self connections are not allowed, check whether pre and post are the same
            if not self.allow_self_connections and pre in target_list:
                target_list.remove(pre)

            N = len(target_list)
            weights = self.getWeights(N)
            weights = _convertWeight(weights, projection.synapse_type).tolist()
            delays = self.getDelays(N).tolist()

            nest.DivergentConnectWD([pre], target_list.tolist(), weights, delays)

            projection._sources += [pre]*N
            conn_dict = nest.GetConnections([pre], projection._plasticity_model)[0]
            if isinstance(conn_dict, dict):
                all_targets = conn_dict['targets']
                total_targets = len(all_targets)
                projection._targets += all_targets[-N:]
                projection._target_ports += range(total_targets-N, total_targets)
        return len(projection._sources)

def _n_connections(population, synapse_type):
    """
    Get a list of the total number of connections made by each neuron in a
    population.
    """
    n = numpy.zeros((len(population),),'int')
    conn_dict_list = nest.GetConnections([id for id in population], synapse_type)
    for i, conn_dict in enumerate(conn_dict_list):
        assert isinstance(conn_dict, dict)
        n[i] = len(conn_dict['targets'])
    return n

class FixedNumberPostConnector(common.FixedNumberPostConnector):
    
    def connect(self, projection):
        presynaptic_neurons = projection.pre.cell.flatten()
        if projection.rng:
            rng = projection.rng
        else:
            rng = numpy.random
        start_ports = _n_connections(projection.pre, projection._plasticity_model)
        for post in projection.post.cell.flat:
            if hasattr(self, 'rand_distr'):
                n = self.rand_distr.next()
            else:
                n = self.n
            source_list = rng.permutation(presynaptic_neurons)[0:n]
            # if self connections are not allowed, check whether pre and post are the same
            if not self.allow_self_connections and post in source_list:
                source_list.remove(post)

            N = len(source_list)
            weights = self.getWeights(N)
            weights = _convertWeight(weights, projection.synapse_type).tolist()
            delays = self.getDelays(N).tolist()

            nest.ConvergentConnectWD(source_list.tolist(), [post],
                                     weights, delays)

        end_ports = _n_connections(projection.pre, projection._plasticity_model)
        for pre, start_port, end_port in zip(presynaptic_neurons, start_ports, end_ports):
            projection._target_ports += range(start_port, end_port)
            projection._sources += [pre]*(end_port-start_port)
            conn_dict = nest.GetConnections([pre], projection._plasticity_model)[0]
            if isinstance(conn_dict, dict):
                projection._targets += conn_dict['targets'][start_port:end_port]
        print start_ports
        print end_ports
        return len(projection._sources)


def _connect_from_list(conn_list, projection):
    # slow: should maybe sort by pre and use DivergentConnect?
    # or at least convert everything to a numpy array at the start
    weights = []; delays = []
    for i in xrange(len(conn_list)):
        src, tgt, weight, delay = conn_list[i][:]
        src = projection.pre[tuple(src)]
        tgt = projection.post[tuple(tgt)]
        projection._sources.append(src)
        projection._targets.append(tgt)
        projection._target_ports.append(get_target_ports(src, [tgt], projection._plasticity_model)[0])
        weights.append(_convertWeight(weight, projection.synapse_type))
        delays.append(delay)
    nest.ConnectWD(projection._sources, projection._targets, weights, delays)
    return projection.pre.size


class FromListConnector(common.FromListConnector):
    
    def connect(self, projection):
        return _connect_from_list(self.conn_list, projection)


class FromFileConnector(common.FromFileConnector):
    
    def connect(self, projection):
        f = open(self.filename, 'r', 10000)
        lines = f.readlines()
        f.close()
        input_tuples = []
        for line in lines:
            single_line = line.rstrip()
            src, tgt, w, d = single_line.split("\t", 4)
            src = "[%s" % src.split("[",1)[1]
            tgt = "[%s" % tgt.split("[",1)[1]
            input_tuples.append((eval(src), eval(tgt), float(w), float(d)))
        return _connect_from_list(input_tuples, projection)