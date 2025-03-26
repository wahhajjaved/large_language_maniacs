#! /usr/bin/env python

##############################################################################
##
##  Copyright 2010-2014 Jeet Sukumaran.
##  All rights reserved.
##
##  Redistribution and use in source and binary forms, with or without
##  modification, are permitted provided that the following conditions are met:
##
##      * Redistributions of source code must retain the above copyright
##        notice, this list of conditions and the following disclaimer.
##      * Redistributions in binary form must reproduce the above copyright
##        notice, this list of conditions and the following disclaimer in the
##        documentation and/or other materials provided with the distribution.
##      * The names of its contributors may not be used to endorse or promote
##        products derived from this software without specific prior written
##        permission.
##
##  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
##  IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
##  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
##  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL JEET SUKUMARAN OR MARK T. HOLDER
##  BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
##  CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
##  SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
##  INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
##  CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
##  ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
##  POSSIBILITY OF SUCH DAMAGE.
##
##############################################################################

try:
    from StringIO import StringIO # Python 2 legacy support: StringIO in this module is the one needed (not io)
except ImportError:
    from io import StringIO # Python 3
import sys
import random
import collections
import argparse
import supertramp
from supertramp import utility
from supertramp.BitVector import BitVector
import dendropy

def weighted_choice(seq, weights, rng=None):
    """
    Selects an element out of seq, with probabilities of each element
    given by the list `weights` (which must be at least as long as the
    length of `seq` - 1).
    """
    if weights is None:
        weights = [1.0/len(seq) for count in range(len(seq))]
    else:
        weights = list(weights)
    if len(weights) < len(seq) - 1:
        raise Exception("Insufficient number of weights specified")
    if len(weights) == len(seq) - 1:
        weights.append(1 - sum(weights))
    return seq[weighted_index_choice(weights, rng)]

def weighted_index_choice(weights, rng=None):
    """
    (From: http://eli.thegreenplace.net/2010/01/22/weighted-random-generation-in-python/)
    The following is a simple function to implement weighted random choice in
    Python. Given a list of weights, it returns an index randomly, according
    to these weights [1].
    For example, given [2, 3, 5] it returns 0 (the index of the first element)
    with probability 0.2, 1 with probability 0.3 and 2 with probability 0.5.
    The weights need not sum up to anything in particular, and can actually be
    arbitrary Python floating point numbers.
    If we manage to sort the weights in descending order before passing them
    to weighted_choice_sub, it will run even faster, since the random call
    returns a uniformly distributed value and larger chunks of the total
    weight will be skipped in the beginning.
    """
    rnd = rng.uniform(0, 1) * sum(weights)
    for i, w in enumerate(weights):
        rnd -= w
        if rnd < 0:
            return i

class IndexGenerator(object):

    def __init__(self, start=0):
        self.start = start
        self.index = start

    def __next__(self):
        c = self.index
        self.index += 1
        return c

    def reset(self, start=None):
        if start is None:
            start = self.start
        self.index = start

class HabitatType(object):

    def __init__(self, index, label):
        self.index =  index
        self.label = label

    def __str__(self):
        return self.label

class Habitat(object):

    def __init__(self,
            index,
            habitat_type,
            island):
        self.index = index
        self.habitat_type = habitat_type
        self.island = island
        self.lineages = set()
        self.migrants = set()

    def process_migrants(self):
        for lineage in self.migrants:
            self.add_lineage(lineage)
        self.migrants.clear()

    def receive_migrant(self, lineage):
        self.migrants.add(lineage)

    def add_lineage(self, lineage):
        self.lineages.add(lineage)
        lineage.register_habitat(self)

    def remove_lineage(self, lineage):
        self.lineages.remove(lineage)
        lineage.deregister_habitat(self)

    def __str__(self):
        return "{}-{}".format(self.island.label, self.habitat_type.label)

class Island(object):

    def __init__(self,
            index,
            rng,
            label,
            habitat_types,
            habitat_indexer,
            run_logger=None):
        self.index = index
        self.rng = rng
        self.label = label
        self.habitat_types = habitat_types
        self.habitat_list = []
        self.habitats_by_type = {}
        self.run_logger = run_logger

        # construct habitats
        for ht_idx, ht in enumerate(self.habitat_types):
            h = Habitat(
                    index=next(habitat_indexer),
                    habitat_type=ht,
                    island=self)
            self.habitat_list.append(h)
            self.habitats_by_type[ht] = h

        # initialize dispersal regime
        self._dispersal_rates = {}
        for ht in self.habitat_types:
            self._dispersal_rates[ht] = {}

    def __str__(self):
        return self.label

    def set_dispersal_rate(self, habitat_type, dest_island, rate):
        """
        Set a specific dispersal.
        """
        self._dispersal_rates[habitat_type][dest_island] = rate

    def run_dispersals(self):
        for habitat_type in self._dispersal_rates:
            for dest_island in self._dispersal_rates[habitat_type]:
                habitat = self.habitats_by_type[habitat_type]
                rate = self._dispersal_rates[habitat_type][dest_island]
                if not habitat.lineages or rate <= 0.0:
                    continue
                if self.rng.uniform(0, 1) <= rate:
                    lineage = self.rng.choice(list(habitat.lineages))
                    self.run_logger.debug("{lineage}, with habitat type '{habitat_type}', dispersing from island {island1} to {island2}, ".format(
                        island1=self.label,
                        island2=dest_island.label,
                        habitat_type=lineage.habitat_type,
                        lineage=lineage.logging_label))
                    dest_island.receive_migrant(
                            lineage=lineage,
                            habitat_type=lineage.habitat_type,
                            from_island=self,     # not used for production class but
                            from_habitat=habitat, # tests implement derived version of
                            )                     # this class and override this method to
                                                  # validate dispersal


    def process_migrants(self):
        for habitat in self.habitat_list:
            habitat.process_migrants()

    def receive_migrant(self,
            lineage,
            habitat_type,
            from_island,
            from_habitat,
            ):
        assert lineage.habitat_type is habitat_type
        self.habitats_by_type[habitat_type].receive_migrant(lineage)

    def add_lineage(self, lineage, habitat_type):
        assert lineage.habitat_type is habitat_type
        self.habitats_by_type[habitat_type].add_lineage(lineage)

class Lineage(dendropy.Node):

    def __init__(self,
            index,
            habitat_type=None,
            system=None):
        self.index = index
        super(Lineage, self).__init__()
        self.habitat_type = habitat_type
        self.system = system
        self.habitat_types = None
        self.island_habitat_localities = None
        self.habitats = None
        self.final_distribution_label = None
        self.edge.length = 0
        self.is_extant = True
        if self.system is not None:
            self.bootstrap()

    def bootstrap(self):
        # Note that all islands and habitat types need to be defined for this
        # to work (or at least, the maximum number of habitat types and islands
        # must be known.
        assert self.habitat_types is None
        assert self.island_habitat_localities is None
        assert self.habitats is None
        self.habitat_types = BitVector(size=self.system.num_habitat_types)
        self.island_habitat_localities = BitVector(size=self.system.num_islands)
        self.habitats = BitVector(size=self.system.num_islands * self.system.num_habitat_types)

    def register_habitat(self, habitat):
        self.habitats[habitat.index] = 1
        self.island_habitat_localities[habitat.island.index] = 1
        self.habitat_types[habitat.habitat_type.index] = 1

    def deregister_habitat(self, habitat):
        self.habitats[habitat.index] = 0
        self.island_habitat_localities[habitat.island.index] = 0
        # TODO: simply because it is removed from one particular habitat on one
        # particular island, does not mean that it is no longer associated with
        # this habitat type!!!
        # self.habitat_types[habitat.habitat_type.index] = 0

    def iterate_habitats(self):
        for idx, habitat_presence in enumerate(self.habitats):
            if habitat_presence == 1:
                yield self.system.habitats_by_index_map[idx]

    def _get_label(self):
        return "S{:d}.{}".format(self.index, self.distribution_label)
    def _set_label(self, v):
        self._label = v
    label = property(_get_label, _set_label)

    def _get_logging_label(self):
        return "<Lineage S{:d}: {}.{}>".format(
                self.index,
                self.island_habitat_localities,
                self.habitat_types)
    logging_label = property(_get_logging_label)

    @property
    def distribution_label(self):
        # this label gets locked to `final_distribution_label` when the species
        # diversifies
        if self.final_distribution_label is not None:
            return self.final_distribution_label
        return "{}.{}".format(self.island_habitat_localities, self.habitat_types)

    def add_age_to_extant_tips(self, ngens=1):
        """
        Grows tree by adding ``ngens`` time unit(s) to all tips.
        Returns number of extant tips.
        """
        num_extant_tips = 0
        if self._child_nodes:
            for nd in self.leaf_iter():
                if nd.is_extant:
                    num_extant_tips += 1
                    nd.edge.length += ngens
        elif self.is_extant:
            num_extant_tips += 1
            self.edge.length += ngens
        return num_extant_tips

    def diversify(self,
            lineage_indexer,
            finalize_distribution_label=True,
            nsplits=1):
        """
        Spawns two child lineages with self as parent.
        Returns tuple consisting of these two lineages.
        """
        if self._child_nodes:
            raise Exception("Trying to diversify internal node: {}: {}".format(self.label, ", ".join(c.label for c in self._child_nodes)))
        if finalize_distribution_label:
            self.final_distribution_label = self.distribution_label
        children = []
        for i in range(nsplits+1):
            c1 = Lineage(
                    index=next(lineage_indexer),
                    habitat_type=self.habitat_type,
                    system=self.system)
            children.append(c1)
            self.add_child(c1)
            assert c1.parent_node is self
        self.is_extant = False # a splitting event ==> extinction of parent lineage
        return children

    def _debug_check_dump_biogeography(self, out):
        out.write("[{}:{}:{}:  ".format(id(self), self.index, self.label))
        out.write("islands='{}'  ".format(self.island_habitat_localities))
        out.write("habitat_types='{}'  ".format(self.habitat_types))
        out.write("habitats='{}'".format(self.habitats))
        out.write("]\n")

    def num_child_nodes(self):
        try:
            return super(Lineage, self).num_child_nodes()
        except AttributeError:
            return len(self._child_nodes)


class Phylogeny(dendropy.Tree):

    def node_factory(cls, **kwargs):
        return Lineage(**kwargs)
    node_factory = classmethod(node_factory)

    def add_age_to_extant_tips(self, ngens=1):
        """
        Grows tree by adding ``ngens`` time unit(s) to all tips.
        """
        return self.seed_node.add_age_to_extant_tips(ngens)

class TotalExtinctionException(Exception):
    def __init__(self, *args, **kwargs):
        Exception.__init__(self, *args, **kwargs)

class TargetNumberOfTipsException(Exception):
    def __init__(self, num_extant_tips_exception_trigger, num_extant_tips, *args, **kwargs):
        self.num_extant_tips = num_extant_tips
        self.num_extant_tips_exception_trigger = num_extant_tips_exception_trigger
        Exception.__init__(self, *args, **kwargs)

class SupertrampSimulator(object):

    island_type = Island

    @staticmethod
    def simulation_model_arg_parser():
        parser = argparse.ArgumentParser(add_help=False)
        model_landscape_options = parser.add_argument_group("MODEL: Landscape Configuration")
        model_landscape_options.add_argument("--num-islands",
                type=int,
                default=4,
                help="number of islands (default = %(default)s).")
        model_landscape_options.add_argument("--num-habitat-types",
                type=int,
                default=3,
                help="number of habitat types per island (default = %(default)s).")
        model_diversification_submodel_params = parser.add_argument_group("MODEL: Diversification Submodel Parameters")
        model_diversification_submodel_params.add_argument("-b", "--diversification-model-speciation-rate",
                type=float,
                default=0.01,
                help="diversfication model speciation rate (default: %(default)s).")
        model_diversification_submodel_params.add_argument("-e", "--diversification-model-extinction-rate",
                type=float,
                default=0.01,
                help="diversification model extirpation rate (default: %(default)s).")
        model_dispersal_submodel_params = parser.add_argument_group("MODEL: Dispersal Submodel Parameters")
        model_dispersal_submodel_params.add_argument("-m", "--dispersal-model",
                type=str,
                default="unconstrained",
                choices=["constrained", "unconstrained"],
                help="Dispersal model: constrained or unconstrained by habitat")
        model_dispersal_submodel_params.add_argument("-d", "--dispersal-rate",
                default=0.01,
                type=float,
                help="Dispersal rate (default = %(default)s).")
        lineage_evolution_submodel_params = parser.add_argument_group("MODEL: Lineage Evolution Submodel Parameters")
        lineage_evolution_submodel_params.add_argument("-q", "--niche-evolution-probability",
                default=0.01,
                type=float,
                help="Lineage (post-splitting) niche evolution probability (default = %(default)s).")
        return parser

    def __init__(self, **kwargs):

        # create state variables
        self.habitat_indexer = IndexGenerator(0)
        self.lineage_indexer = IndexGenerator(0)

        # system globals
        self.current_gen = 0
        self.habitat_types = []
        self.islands = []
        self.habitats_by_index_map = {}
        self.phylogeny = None

        # system globals: metrics
        self.num_speciations = 0
        # self.num_extirpations = 0
        self.num_extinctions = 0
        self.num_niche_shifts = 0

        # run configuration
        self.output_prefix = None
        self.run_logger = None
        self.name = None
        self.tree_log = None
        self.general_stats_log = None
        self.rng = None
        self.track_extinct_lineages = None
        self.debug_mode = None
        self.log_frequency = None
        self.report_frequency = None

        # configure
        self.configure_simulator(kwargs)
        self.set_model(kwargs)
        if kwargs:
            raise TypeError("Unsupported configuration keywords: {}".format(kwargs))

        # setup
        self.bootstrap()

        # set specation modes
        self.sympatric_speciation = False
        if len(self.islands) == 1:
            self.single_island_mode = True
        else:
            self.single_island_mode = False

    def set_model(self, model_params_d):

        # Landscape: islands
        self.island_labels = model_params_d.pop("island_labels", None)
        if self.island_labels is None:
            self.island_labels = []
            num_islands = model_params_d.pop("num_islands", 4)
            for i in range(num_islands):
                label = "I{}".format(i+1)
                self.island_labels.append(label)
        else:
            if num_islands in model_params_d and num_islands != len(self.island_labels):
                raise ValueError("Number of islands requested ({}) does not match number of islands specified ({})".format(
                    model_params_d["num_islands"], len(self.island_labels)))
        self.run_logger.info("Configuring {} islands: {}".format(
            len(self.island_labels), self.island_labels))

        # Landscape: habitats
        self.habitat_type_labels = model_params_d.pop("habitat_type_labels", None)
        if self.habitat_type_labels is None:
            num_habitat_types = model_params_d.pop("num_habitat_types", 3)
            self.habitat_type_labels = []
            for i in range(num_habitat_types):
                label = "H{}".format(i+1)
                self.habitat_type_labels.append(label)
        else:
            if num_habitat_types in model_params_d and num_habitat_types != len(self.habitat_type_labels):
                raise ValueError("Number of habitat_types requested ({}) does not match number of habitat_types specified ({})".format(
                    model_params_d["num_habitat_types"], len(self.habitat_type_labels)))
        self.run_logger.info("Configuring {} habitat types per island: {}".format(
            len(self.habitat_type_labels), self.habitat_type_labels))

        # Dispersal submodel
        self.dispersal_model = model_params_d.pop("dispersal_model", "unconstrained")
        self.run_logger.info("Dispersal model category: '{}'".format(self.dispersal_model))
        self.global_dispersal_rate = model_params_d.pop("dispersal_rate", 0.01)
        self.run_logger.info("Dispersal rate, d: {}".format(self.global_dispersal_rate))

        # Diversification submodel
        self.diversification_model_speciation_rate = model_params_d.pop("diversification_model_speciation_rate", 0.01)
        self.run_logger.info("Diversification model, speciation-rate: {}".format(self.diversification_model_speciation_rate))
        self.diversification_model_extinction_rate = model_params_d.pop("diversification_model_extinction_rate", 0.01)
        self.run_logger.info("Diversification model, extinction-rate: {}".format(self.diversification_model_extinction_rate))
        self.diversification_model_sum_of_speciation_and_extinction_rate = self.diversification_model_speciation_rate + self.diversification_model_extinction_rate

        # Not strictly necessary in theory, but current implementation behaves
        # better if this true
        assert self.diversification_model_sum_of_speciation_and_extinction_rate <= 1.0

        # self.diversification_model_a = model_params_d.pop("diversification_model_a", -0.5)
        # self.run_logger.info("Diversification model, a: {}".format(self.diversification_model_a))
        # self.diversification_model_b = model_params_d.pop("diversification_model_b", 0.5)
        # self.run_logger.info("Diversification model, b: {}".format(self.diversification_model_b))
        # self.diversification_model_s0 = model_params_d.pop("diversification_model_s0", 0.1)
        # self.run_logger.info("Diversification model, s0: {}".format(self.diversification_model_s0))
        # self.diversification_model_e0 = model_params_d.pop("diversification_model_e0", 0.001)
        # self.run_logger.info("Diversification model, e0: {}".format(self.diversification_model_e0))
        # if self.diversification_model_e0 > 0:
        #     self.run_logger.info("Projected habitat species richness (s0/e0): {}".format(self.diversification_model_s0/self.diversification_model_e0))
        # else:
        #     self.run_logger.info("Extinction rate is 0")

        # Nice Shift/Evolution submodel
        self.global_lineage_niche_evolution_probability = model_params_d.pop("niche_evolution_probability", 0.01)
        self.run_logger.info("Niche evolution probability: {}".format(self.global_lineage_niche_evolution_probability))

    def configure_simulator(self, configd):

        self.output_prefix = configd.pop("output_prefix", "supertramp")

        self.run_logger = configd.pop("run_logger", None)
        if self.run_logger is None:
            self.run_logger = utility.RunLogger(name="supertramp",
                    log_path=self.output_prefix + ".log")
        self.run_logger.system = self

        self.name = configd.pop("name", None)
        if self.name is None:
            self.name = str(id(self))
        self.run_logger.info("Configuring simulation '{}'".format(self.name))

        self.tree_log = configd.pop("tree_log", None)
        if self.tree_log is None:
            self.tree_log = open(self.output_prefix + ".trees", "w")
        self.run_logger.info("Tree log filepath: {}".format(self.tree_log.name))

        self.general_stats_log = configd.pop("general_stats_log", None)
        if self.general_stats_log is None:
            self.general_stats_log = open(self.output_prefix + ".trees", "w")
        self.run_logger.info("Statistics log filepath: {}".format(self.general_stats_log.name))

        self.rng = configd.pop("rng", None)
        if self.rng is None:
            self.random_seed = configd.pop("random_seed", None)
            if self.random_seed is None:
                self.random_seed = random.randint(0, sys.maxsize)
            self.run_logger.info("Initializing with random seed {}".format(self.random_seed))
            # self.rng = numpy.random.RandomState(seed=[self.random_seed])
            self.rng = random.Random(self.random_seed)
        else:
            if "random_seed" in configd:
                raise TypeError("Cannot specify both 'rng' and 'random_seed'")
            self.run_logger.info("Using existing random number generator")

        self.track_extinct_lineages = configd.pop("track_extinct_lineages", False)
        if self.track_extinct_lineages:
            self.run_logger.info("Extinct lineages will be tracked: lineages will be retained in the tree even if they are extirpated from all habitats in all islands")
        else:
            self.run_logger.info("Extinct lineages will not be tracked: lineages will be pruned from the tree if they are extirpated from all habitats in all islands")
        self.debug_mode = configd.pop("debug_mode", False)
        if self.debug_mode:
            self.run_logger.info("Running in DEBUG mode")

        self.log_frequency = configd.pop("log_frequency", 1000)
        self.report_frequency = configd.pop("report_frequency", None)

    def poisson_rv(rate):
        """
        Returns a random number from a Poisson distribution with rate of
        `rate` (mean of 1/rate).
        """
        MAX_EXPECTATION = 64.0 # larger than this and we have underflow issues
        if rate > MAX_EXPECTATION:
            r = rate/2.0
            return poisson_rv(r) + poisson_rv(r)
        L = math.exp(-1.0 * rate)
        p = 1.0
        k = 0.0
        while p >= L:
            k = k + 1.0
            u = self.rng.random()
            p = p * u
        return int(k - 1.0)

    def bootstrap(self):

        # create habitat types
        for ht_idx, ht_label in enumerate(self.habitat_type_labels):
            h = HabitatType(index=ht_idx, label=ht_label)
            self.habitat_types.append(h)
        self.all_habitat_types_bitmask = (1 << len(self.habitat_types)) - 1

        # create islands
        for island_idx, island_label in enumerate(self.island_labels):
            island = self.__class__.island_type(
                    index=island_idx,
                    rng=self.rng,
                    label=island_label,
                    habitat_types=self.habitat_types,
                    habitat_indexer=self.habitat_indexer,
                    run_logger=self.run_logger)
            self.islands.append(island)
        self.all_islands_bitmask = (1 << len(self.islands)) - 1
        assert self.habitat_indexer.index == (len(self.island_labels) * len(self.habitat_types))
        self.habitats_by_index_map = {}
        for island in self.islands:
            for habitat in island.habitat_list:
                self.habitats_by_index_map[habitat.index] = habitat

        # set up dispersal regime
        if self.dispersal_model == "unconstrained":
            self.dispersal_source_habitat_types = list(self.habitat_types)
        else:
            self.dispersal_source_habitat_types = [self.habitat_types[0]]

        # sum of rates of dispersing out of any island == global dispersal rate
        dispersal_rates = []
        if len(self.islands) <= 1:
            if self.global_dispersal_rate > 0:
                self.run_logger.info("Only {} island: forcing dispersal rate to 0.0".format(len(self.islands)))
            island_dispersal_rate = 0
        else:
            # Orignally, supertramp "distributed" the global dispersal rate
            # over all islands, so that the *sum* of dispersal rates equalled the global dispersal rate
            # island_dispersal_rate = float(self.global_dispersal_rate) / ((len(self.islands) * (len(self.islands) - 1)))

            # Following lagrange and BioGeoBears, though, we now have the island dispersal rate being the global dispersal rate
            island_dispersal_rate = self.global_dispersal_rate

        habitat_dispersal_rates = {}
        for idx, habitat_type in enumerate(self.habitat_types):
            if habitat_type in self.dispersal_source_habitat_types:
                disp_rate = island_dispersal_rate / len(self.dispersal_source_habitat_types)
            else:
                disp_rate = 0.0
            habitat_dispersal_rates[habitat_type] = disp_rate
        island_dispersal_rates = {}
        for isl1 in self.islands:
            dispersal_rates_out_of_isl1 = []
            for isl2 in self.islands:
                if isl1 is not isl2:
                    for habitat_type in self.habitat_types:
                        dispersal_rates_out_of_isl1.append(disp_rate)
                        disp_rate = habitat_dispersal_rates[habitat_type]
                        isl1.set_dispersal_rate(habitat_type, isl2, disp_rate)
                        self.run_logger.info("Island {} to {} dispersal rate for habitat {} = {}".format(
                            isl1, isl2, habitat_type, disp_rate))
                        dispersal_rates.append(disp_rate)
            island_dispersal_rates[isl1] = sum(dispersal_rates_out_of_isl1)
            self.run_logger.info("Total dispersal rate out of island {} = {}".format(isl1, island_dispersal_rates[isl1]))
        total_dispersal_rate = sum(dispersal_rates)
        self.run_logger.info("Sum of dispersal rates between all habitats = {}".format(total_dispersal_rate))
        total_island_dispersal_rate = sum(island_dispersal_rates.values())
        self.run_logger.info("Sum of dispersal rates between islands = {}".format(total_island_dispersal_rate))
        self.run_logger.info("Mean dispersal rate per island = {}".format(total_island_dispersal_rate/len(island_dispersal_rates)))
        # if len(self.islands) > 1 and abs(total_dispersal_rate - self.global_dispersal_rate) > 1e-8:
        #     self.run_logger.critical("Error in dispersal rate distribution: {} != {}: {}".format(
        #         total_dispersal_rate, self.global_dispersal_rate, dispersal_rates))
        #     sys.exit(1)

        # initialize lineages
        self.seed_habitat = self.dispersal_source_habitat_types[0]
        seed_node = Lineage(index=0, habitat_type=self.seed_habitat, system=self)
        self.phylogeny = Phylogeny(seed_node=seed_node)

        # seed lineage
        self.islands[0].habitat_list[0].add_lineage(self.phylogeny.seed_node)

        # begin logging generations
        self.run_logger.system = self

    @property
    def num_islands(self):
        return len(self.islands)

    @property
    def num_habitat_types(self):
        return len(self.habitat_types)

    def run(self, ngens=None, ntips=None):
        info = ["Running from generation {} ".format(self.current_gen+1)]
        if ntips is not None and ngens is not None:
            info.append(" to generation {stop} ({ngens} generations) or until {ntax} extant tips observed".format(
                stop=self.current_gen + ngens,
                ngens=ngens,
                ntax=ntips))
        elif ntips is not None:
            info.append(" until {ntax} extant tips observed".format(
                ntax=ntips))
        elif ngens is not None:
            info.append(" to generation {stop} ({ngens} generations)".format(
                stop=self.current_gen + ngens,
                ngens=ngens))
        else:
            info.append(" with no termination condition specified")
        info = "".join(info)
        self.run_logger.info(info)
        self.run_logger.system = self
        cur_gen = 0
        while True:
            self.execute_life_cycle(num_extant_tips_exception_trigger=ntips)
            cur_gen += 1
            if ngens and cur_gen > ngens:
                break
        self.run_logger.system = None
        return True

    def total_extinction_exception(self, msg):
        self.run_logger.info("Total extinction: {}".format(msg))
        raise TotalExtinctionException(msg)

    def execute_life_cycle(self,
            num_extant_tips_exception_trigger=None):
        self.current_gen += 1
        num_extant_tips = self.phylogeny.add_age_to_extant_tips(1)
        if num_extant_tips_exception_trigger is not None and num_extant_tips >= num_extant_tips_exception_trigger:
            self.run_logger.info("Number of extant tips = {}".format(num_extant_tips_exception_trigger))
            raise TargetNumberOfTipsException(num_extant_tips_exception_trigger, num_extant_tips)
        if self.log_frequency is not None and self.log_frequency > 0 and self.current_gen % self.log_frequency == 0:
            self.run_logger.info("Executing life-cycle {}".format(self.current_gen))
        for island in self.islands:
            island.run_dispersals()
        for island in self.islands:
            island.process_migrants()
        self.run_diversification()
        if self.report_frequency is not None and self.report_frequency > 0 and self.current_gen % self.report_frequency == 0:
            self.report()

    def run_diversification(self, global_lineage_death=False):
        """
        Parameters
        ----------
        global_lineage_death : bool
            If `True`, then a lineage that experiences an extinction event will
            go globally-extinct, i.e. be removed from *all* habitats in which
            it occurs. If `False`, then the extinction will actually be an
            extirpation, or local extinction event, i.e., it will be removed
            from *one* of the habitats/islands in which it occurs.

        """
        extincting_lineages = set()
        splitting_lineages = set()
        visited_lineages = 0
        for lineage in self.phylogeny.leaf_node_iter():
            if not lineage.is_extant:
                continue
            u = self.rng.uniform(0, 1)
            if u < self.diversification_model_extinction_rate:
                extincting_lineages.add(lineage)
            elif u < self.diversification_model_sum_of_speciation_and_extinction_rate:
                splitting_lineages.add(lineage)
            visited_lineages += 1
        if not visited_lineages:
            self.total_extinction_exception("Diversification cycle: no extant lineages found")
        if extincting_lineages or splitting_lineages:
            lineage_habitat_set_map = self._get_lineage_habitat_set_map()
            for lineage in extincting_lineages:
                if global_lineage_death:
                    self._remove_lineage_globally(lineage, lineage_habitat_set_map[lineage])
                else:
                    self._remove_lineage_locally(lineage, lineage_habitat_set_map[lineage])
            if self.debug_mode:
                try:
                    self.phylogeny._debug_check_tree()
                except AttributeError:
                    self.phylogeny.debug_check_tree()
                self.run_logger.debug("DEBUG MODE: phylogeny structure is valid after processing extinctions")
            for lineage in splitting_lineages:
                self._split_lineage(lineage, lineage_habitat_set_map[lineage])
            if self.debug_mode:
                try:
                    self.phylogeny._debug_check_tree()
                except AttributeError:
                    self.phylogeny.debug_check_tree()
                self.run_logger.debug("DEBUG MODE: phylogeny structure is valid after processing speciations")

    def _get_lineage_habitat_set_map(self):
        """
        Surveys all habitats and islands, and returns a dictionary where the
        keys are lineages and the values are a set of habitats in which the
        lineage occurs.
        """
        lineage_habitat_set_map = collections.defaultdict(set)
        for island in self.islands:
            for habitat in island.habitat_list:
                for lineage in habitat.lineages:
                    lineage_habitat_set_map[lineage].add(habitat)
        return lineage_habitat_set_map

    def _remove_lineage_globally(self, lineage, occurrence_habitats=None):
        """
        Removes `lineage` from *all* islands/habitats in which it occurs.
        """
        if occurrence_habitats is None:
            occurrence_habitats = list(lineage.iterate_habitats)
        for habitat in occurrence_habitats:
            habitat.remove_lineage(lineage)
        self._make_lineage_extinct_on_phylogeny(lineage)
        self.run_logger.debug("{lineage} extirpated from all islands and is now globally extinct".format(
            lineage=lineage.logging_label,
            ))

    def _remove_lineage_locally(self, lineage, occurrence_habitats=None):
        """
        Removes `lineage` from a random island habitat in which it occurs.
        """
        if occurrence_habitats is None:
            occurrences = list(lineage.iterate_habitats())
        else:
            occurrences = list(occurrence_habitats)
        if len(occurrences) == 0:
            assert False
        elif len(occurrences) == 1:
            occurrences[0].remove_lineage(lineage)
            self._make_lineage_extinct_on_phylogeny(lineage)
            self.run_logger.debug("{lineage} extirpated from all islands and is now globally extinct".format(
                lineage=lineage.logging_label,
                ))
        else:
            h = self.rng.choice(occurrences)
            h.remove_lineage(lineage)
            self.run_logger.debug("{lineage} extirpated from island {island}".format(
                lineage=lineage.logging_label,
                island=h.island.label,
                ))

    def _split_lineage(self, lineage, occurrence_habitats=None):
        assert lineage.is_extant
        if occurrence_habitats is None:
            occurrences = list(lineage.iterate_habitats())
        else:
            occurrences = list(occurrence_habitats)
        if len(occurrences) == 0:
            assert False
        if len(occurrences) == 1:
            # sympatric speciation
            splitting_habitat = occurrences[0]
        else:
            # allopatric speciation
            splitting_habitat = self.rng.choice(occurrences)

        children = lineage.diversify(
                lineage_indexer=self.lineage_indexer,
                finalize_distribution_label=True,
                nsplits=1)
        assert len(children) == 2
        self.num_speciations += 1
        if self.debug_mode:
            try:
                self.phylogeny._debug_check_tree()
            except AttributeError:
                self.phylogeny.debug_check_tree()
            self.run_logger.debug("DEBUG MODE: phylogeny structure is valid after lineage splitting")

        c0 = children[0]
        c_remaining = set(children[1:])
        if len(self.habitat_types) > 1:
            # assumes all children have the same habitat type
            habitats_to_evolve_into = [ h for h in self.habitat_types if h is not c0.habitat_type ]
            for c1 in c_remaining:
                if self.rng.uniform(0, 1) <= self.global_lineage_niche_evolution_probability:
                    c1.habitat_type = self.rng.choice(habitats_to_evolve_into)

        c0_placed = False
        for habitat in occurrence_habitats:
            habitat.remove_lineage(lineage)
            if habitat is splitting_habitat:
                c1 = c_remaining.pop()
                habitat.island.add_lineage(lineage=c1, habitat_type=c1.habitat_type)
                self.run_logger.debug("{splitting_lineage} (with habitat type '{splitting_lineage_habitat_type}') speciating to {daughter_lineage1} (with habitat type '{daughter_lineage1_habitat_type}') in island {island}".format(
                    splitting_lineage=lineage.logging_label,
                    splitting_lineage_habitat_type=lineage.habitat_type.label,
                    daughter_lineage0=c0.logging_label,
                    daughter_lineage1=c1.logging_label,
                    daughter_lineage1_habitat_type=c1.habitat_type.label,
                    island=habitat.island.label,
                    ))
                # if self.sympatric_speciation or self.single_island_mode:
                if len(occurrence_habitats) == 1:
                    # occurs only in one locality: force sympatric speciation
                    habitat.island.add_lineage(lineage=c0, habitat_type=c0.habitat_type)
                    c0_placed = True
                    self.run_logger.debug("{splitting_lineage} (with habitat type '{splitting_lineage_habitat_type}') continuing as {daughter_lineage0} in island {island}".format(
                        splitting_lineage=lineage.logging_label,
                        splitting_lineage_habitat_type=lineage.habitat_type.label,
                        daughter_lineage0=c0.logging_label,
                        daughter_lineage1=c1.logging_label,
                        daughter_lineage1_habitat_type=c1.habitat_type.label,
                        island=habitat.island.label,
                        ))
            else:
                habitat.island.add_lineage(lineage=c0, habitat_type=c0.habitat_type)
                c0_placed = True
                self.run_logger.debug("{splitting_lineage} (with habitat type '{splitting_lineage_habitat_type}') continuing as {daughter_lineage0} in island {island}".format(
                    splitting_lineage=lineage.logging_label,
                    splitting_lineage_habitat_type=lineage.habitat_type.label,
                    daughter_lineage0=c0.logging_label,
                    island=habitat.island.label,
                    ))
        assert c0_placed
        assert len(c_remaining) == 0

    def _make_lineage_extinct_on_phylogeny(self, lineage):
        lineage.is_extant = False
        if lineage is self.phylogeny.seed_node:
            self.total_extinction_exception("Death cycle (pruning): seed node has been extirpated from all habitats on all islands")
        self.phylogeny.prune_subtree(node=lineage, update_splits=False, delete_outdegree_one=True)
        if self.phylogeny.seed_node.num_child_nodes() == 0 and not self.phylogeny.seed_node.is_extant:
            self.total_extinction_exception("Death cycle (post-pruning): no extant lineages on tree")
        if self.debug_mode:
            try:
                self.phylogeny._debug_check_tree()
            except AttributeError:
                self.phylogeny.debug_check_tree()
            self.run_logger.debug("DEBUG MODE: phylogeny structure is valid after lineage pruning")

    def _debug_check_habitat_000(self):
        for nd in self.phylogeny:
            if nd.is_leaf():
                if str(nd.habitat_types) == "000":
                    print("[{}]\n[{}]\n[{}]\n[{}]\n[{}]".format(
                            nd.label,
                            nd.distribution_label,
                            nd.island_habitat_localities,
                            nd.habitat_types,
                            nd.habitats))
                    print(self.phylogeny._as_newick_string())
                assert str(nd.habitat_types) != "000"

    def report_trees(self):
        self.tree_log.write("[&R][simulation={},generation={}]".format(self.name, self.current_gen))
        try:
            self.tree_log.write(self.phylogeny._as_newick_string())
        except AttributeError:
            self.tree_log.write(self.phylogeny.as_newick_string())
        self.tree_log.write(";\n")
        self.tree_log.flush()

    def write_general_stats_header(self, out):
        header = []
        header.append("name")
        header.append("generation")
        for island in self.islands:
            # number of lineages per island, across all habitats in island i
            header.append("island.{}.richness".format(island.label))
        for habitat_type in self.habitat_types:
            # number of lineages per habitat type, across all islands for each island i, I_{i}
            header.append("habitat.type.{}.richness".format(habitat_type.label))
        for island_idx, island in enumerate(self.islands):
            for habitat_type_idx, habitat in enumerate(island.habitat_list):
                # number of lineage in each habitat j of each island i, H_{i,j}
                header.append("{}.{}.richness".format(island.label, habitat.habitat_type.label))
        # mean number of lineages per island, across all habitat types
        header.append("mean.island.richness")
        # mean number of lineages per habitat type, across all islands
        header.append("mean.habitat.type.richness")
        # mean number of lineages per habitat, across all habitat types and islands
        header.append("mean.habitat.richness")
        header = "\t".join(header)
        out.write("{}\n".format(header))
        out.flush()

    def write_general_stats(self, out):
        island_habitat_richness = collections.OrderedDict()
        island_lineages = collections.defaultdict(set)
        habitat_type_lineages = collections.defaultdict(set)
        num_habitats_counted = 0
        sum_of_richness_in_each_habitat = 0
        for island in self.islands:
            for habitat in island.habitat_list:
                n = len(habitat.lineages)
                island_habitat_richness[ (island, habitat) ] = n
                island_lineages[island].update(habitat.lineages)
                habitat_type_lineages[habitat.habitat_type].update(habitat.lineages)
                sum_of_richness_in_each_habitat += n
                num_habitats_counted += 1
        island_richness = collections.OrderedDict()
        for island in self.islands:
            island_richness[island] = len(island_lineages[island])
        mean_island_richness = sum(island_richness.values())/len(island_richness)
        habitat_type_richness = collections.OrderedDict()
        for habitat_type in self.habitat_types:
            habitat_type_richness[habitat_type] = len(habitat_type_lineages[habitat_type])
        mean_habitat_type_richness = sum(habitat_type_richness.values())/len(habitat_type_richness)
        mean_habitat_richness = sum_of_richness_in_each_habitat/num_habitats_counted

        int_template = "{}"
        float_template = "{}"
        stat_values = collections.OrderedDict()
        stat_values["name"] = self.name
        stat_values["generation"] = int_template.format(self.current_gen)
        for island in self.islands:
            stat_values["island.{}.richness".format(island.label)] = int_template.format(island_richness[island])
        for habitat_type in self.habitat_types:
            stat_values["habitat.type.{}.richness".format(habitat_type.label)] = int_template.format(habitat_type_richness[habitat_type])
        for island_idx, island in enumerate(self.islands):
            for habitat_type_idx, habitat in enumerate(island.habitat_list):
                stat_values["{}.{}.richness".format(island.label, habitat.habitat_type.label)] = int_template.format(island_habitat_richness[ (island, habitat) ])
        stat_values["mean.island.richness"] = float_template.format(mean_island_richness)
        stat_values["mean.habitat_type.richness"] = float_template.format(mean_habitat_type_richness)
        stat_values["mean.habitat.richness"] = float_template.format(mean_habitat_richness)

        values = stat_values.values()
        out.write("\t".join(values))
        out.write("\n")

    def report_general_stats(self):
        if not hasattr(self.general_stats_log, "header_written") or not self.general_stats_log.header_written:
            self.write_general_stats_header(self.general_stats_log)
            self.general_stats_log.header_written = True
        self.write_general_stats(self.general_stats_log)

    def report(self):
        self.report_trees()
        self.report_general_stats()

    def count_extant_lineages(self):
        c = 0
        for nd in self.phylogeny.leaf_node_iter():
            if nd.is_extant:
                c += 1
        return c

    def _get_num_extant_lineages(self):
        return self.count_extant_lineages()
    num_extant_lineages = property(_get_num_extant_lineages)

def repeat_run_supertramp(
        model_params_d,
        ngens,
        target_num_tips,
        nreps,
        output_prefix,
        random_seed="None",
        stderr_logging_level="info",
        file_logging_level="debug"):
    """
    Executes multiple runs of the Supertramp simulator under identical
    parameters to produce the specified number of replicates, discarding failed
    runs.

    Parameters
    ----------
    model_params_d : dict
        Simulator model parameters as keyword-value pairs. To be re-used for
        each replicate.
    ngens : integer
        Maximum number of generations for which to run each individual
        replicate. If `None`, will run indefinitely unless some other
        termination condition (e.g. `target_num-tips`) is set.
    target_num_tips:
        Terminate the simulation if this number of extant tips is observed on
        the tree. If `None`, will run indefinitely unless some other
        termination condition (e.g. `ngens`) is set.
    nreps : integer
        Number of replicates to produce. f
    output_prefix : string
        Path prefix for output files.
    random_seed : integer
        Random seed to be used (for single random number generator across all
        replicates).
    stderr_logging_level : string or None
        Message level threshold for screen logs; if 'none' or `None`, screen
        logs will be supprsed.
    file_logging_level : string or None
        Message level threshold for file logs; if 'none' or `None`, file
        logs will be supprsed.
    """
    configd = dict(model_params_d)
    if stderr_logging_level is None or stderr_logging_level.lower() == "none":
        log_to_stderr = False
    else:
        log_to_stderr = True
    if file_logging_level is None or file_logging_level.lower() == "none":
        log_to_file = False
    else:
        log_to_file = True
    configd["run_logger"] = utility.RunLogger(
            name="supertramp",
            log_to_stderr=log_to_stderr,
            stderr_logging_level=stderr_logging_level,
            log_to_file=log_to_file,
            log_path=output_prefix + ".log",
            file_logging_level=file_logging_level,
            )
    run_logger = configd["run_logger"]
    run_logger.info("||SUPERTRAMP-META|| Starting: {}".format(supertramp.description()))
    if random_seed is None:
        random_seed = random.randint(0, sys.maxsize)
    run_logger.info("||SUPERTRAMP-META|| Initializing with random seed: {}".format(random_seed))
    configd["rng"] = random.Random(random_seed)
    configd["tree_log"] = open(output_prefix + ".trees",
            "w")
    configd["general_stats_log"] = open(output_prefix + ".general_stats.txt",
            "w")
    configd["general_stats_log"].header_written = False
    header_written = False
    rep = 0
    while rep < nreps:
        simulation_name="Run{}".format((rep+1))
        run_output_prefix = "{}.R{:04d}".format(output_prefix, rep+1)
        run_logger.info("||SUPERTRAMP-META|| Run {} of {}: starting".format(rep+1, nreps))
        while True:
            supertramp_simulator = SupertrampSimulator(
                    name=simulation_name,
                    **configd)
            try:
                success = supertramp_simulator.run(ngens=ngens, ntips=target_num_tips)
            except TotalExtinctionException as e:
                run_logger.info("||SUPERTRAMP-META|| Run {} of {}: [t={}] total extinction of all lineages before termination condition: {}".format(rep+1, nreps, supertramp_simulator.current_gen, e))
                run_logger.info("||SUPERTRAMP-META|| Run {} of {}: restarting".format(rep+1, nreps))
            except TargetNumberOfTipsException as e:
                run_logger.info("||SUPERTRAMP-META|| Run {} of {}: completed to termination condition of {} tips ({} tips observed)".format(rep+1, nreps, e.num_extant_tips_exception_trigger, e.num_extant_tips))
                supertramp_simulator.report()
                break
            else:
                run_logger.info("||SUPERTRAMP-META|| Run {} of {}: completed to termination condition of {} generations".format(rep+1, nreps, ngens))
                supertramp_simulator.report()
                break
        rep += 1
