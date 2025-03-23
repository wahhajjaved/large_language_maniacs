"""Implements a decision tree classifier, including learning and prediction."""
# n is the number of features per instance
# m is the number of training instances

import arff  # ARFF module
#import argparse
import optparse
import math
import Node

def get_entropy(items):
    "Calculate the entropy of a list of items"

    item_set = set(items)  # Get list of unique items

    entropy = 0
    for unique_item in item_set:
        probability = 1. * items.count(unique_item) / len(items)
        entropy = entropy - probability * math.log(probability, 2)

    return entropy

class DT_classifier():
    """Decision tree learner for a binary class.
    """

    tree = None  # Decision tree
    m = 0  # Number of training instances
    n = 0  # Number of features

    priority_class = None  # class that wins in a tie-breaker

    def __init__(self, instances, norminalities, value_enumerations,
            min_instances):
        """Constructor for decision tree learner

        instances - 
            a m x n+1 list of lists
            The last column is the class of the instances
        norminalities -
            n+1 length list of booleans.
            norminalities[i] answers whether feature i is norminal (numeric
            otherwise)
        value_enumerations -
            n+1 length list of tuples.
            If norminalities[i] is True, value_enumeration[i] is a tuple of the
            possible norminal values of feature[i].
        """
        self.instances = instances
        self.norminalities = norminalities
        self.value_enumerations = value_enumerations

        self.m = len(instances)
        self.n = len(instances[0]) - 1

        # Min no. of instances at a node that allows splits
        self.min_instances = min_instances

        assert len(self.value_enumerations) == self.n + 1
        assert len(self.norminalities) == self.n + 1

        # Assume class label is norminal (not 0/1, -1/1, etc)
        assert self.norminalities[-1]

    def set_priority_class(self, instances):
        "Establish class priority: first in list has highest priority"

        assert len(instances) > 0
        self.priority_class = instances[0][-1]

    def get_info_gain(self, instances, split_criterion):
        """Return the information gained from knowing a split criterion
        """

        # Return zero information gain if there are no instances
        if not instances:
            return 0

        # Get entropy of instances before knowing split criterion
        labels = [instance[-1] for instance in instances]
        noncond_entropy = get_entropy(labels)

        # Get entropy of instances after knowing split criterion
        cond_entropy = self.get_conditional_entropy(instances, split_criterion)

        info_gain = noncond_entropy - cond_entropy

        return info_gain

    def partition_instances(self, instances, split_criterion):
        """Return a list of partitions that split instances with some
        criterion
        """

        # Initialize partitions as a list of empty lists
        feature_ind, threshold = split_criterion
        norminal = self.norminalities[feature_ind]
        n_partitions = (len(self.value_enumerations[feature_ind])  \
                if norminal
                else 2)
        partitions = [list() for i in range(n_partitions)]

        # Partition instances into their rightful branches down the node
        for instance in instances:
            partition_index = self.look_up_branch_index(
                    instance, split_criterion)

            # Add instance to its rightful partition
            partitions[partition_index].append(instance)

        return partitions

    def get_conditional_entropy(self, instances, split_criterion):
        """Return the entropy of a set of instances conditioned on
        a split criterion.

        See determine_split_candidates() for the specification for a split
        criterion.
        """

        # Partition instances into their rightful branches down the node
        partitions = self.partition_instances(instances, split_criterion)

        # Calculate conditional entropy
        cond_entropy = 0
        for partition in partitions:

            # Probability of an instance being in this partition
            probability = 1. * len(partition) / len(instances)

            # Entropy of this partition
            labels = [instance[-1] for instance in partition]
            entropy = get_entropy(labels)

            cond_entropy = cond_entropy + probability * entropy

        return cond_entropy

    def look_up_branch_index(self, instance, split_criterion):
        """Return the index of a branch that an instances traverses at a node
        represented by split_criterion"""

        feature_index, threshold = split_criterion
        norminal = self.norminalities[feature_index]  # Is feature norminal?

        # Value of feature of this instance
        feature_value = instance[feature_index]

        if norminal:
            # Branches of norminal features are ordered based on
            # value_enumerations
            # e.g. if the enumeration is ['red', 'green', blue'] and the value
            # is 'green', the branch index is 1
            branch_index =  \
                self.value_enumerations[feature_index].index(feature_value)
        else:
            # For numeric features:
            #The left branch of such a split should represent values that are
            #less than or equal to the threshold.
            if feature_value <= threshold:
                branch_index = 0
            else:
                branch_index = 1

        return branch_index

    def fit(self, instances=None, verbose=False):
        """Fit decision tree to given instances.

        instances -
            instances to fit decision tree with (default - self.instances)
        verbose -
            If true, method prints how the sub-tree is formed.
        """

        if instances is None:
            instances = self.instances

        self.tree = self.make_subtree(instances, verbose)

    def make_subtree(self, instances, verbose=False):
        """Return a decision sub-tree starting with instances at top

        verbose -
            If true, prints intermediate stages of computation. If true, we
            self.feature_names to be a list of strings containing the names of
            the features
        """

        if verbose:
            assert hasattr(self, 'feature_names')

        split_criteria = self.determine_split_candidates(instances)

        # Stop criterion 1: all classes are same
        all_classes_same = (
                all([instance[-1] == instances[0][-1] for instance in instances])
                if len(instances) > 0
                else True)

        # Stop criterion 2: less than some min no. of instances
        few_instances = len(instances) < self.min_instances

        # Stop criterion 3: no feature has positive information gain
        info_gains = [
                self.get_info_gain(instances, candidate)
                for candidate in split_criteria]
        none_have_info_gain = all(
                [info_gain <= 0 for info_gain in info_gains])

        # Stop criterion 4: no more features to split on
        no_remaining_features = False
        #no_remaining_features = len(features_remaining) == 0

        # Check if any of the stopping criteria is met
        stop_splitting = all_classes_same or  \
                few_instances or  \
                none_have_info_gain or  \
                no_remaining_features

        if stop_splitting:

            # Compute the majority class
            unique_labels = self.value_enumerations[-1]
            counts = [sum([instance[-1] == label for instance in instances])
                for label in unique_labels]
            node_value = (unique_labels[counts.index(max(counts))]
                    if counts[0] != counts[1]
                    else unique_labels[0])

            assert sum(counts) == len(instances)

            if verbose:
                print "Stopped splitting", len(instances), "instances because"
                print "\tAll classes same?", all_classes_same
                print "\tFew instances?", few_instances
                print "\tNo splits have info gain?", none_have_info_gain
                print "\tNo remaining features?", no_remaining_features
                print "\tLeaf node is of value:", node_value

            # Return child-less node with class as the node value
            return Node.Node(node_value)

        else:

            # Split uses the criterion that gives the highest info gain.
            # Note that since numeric split candidates are in ascending order
            # of threshold values, in the case of a tie for same info gain,
            # same feature but different threshold, the lower threshold
            # candidate is chosen due to the nature of list.index()
            best_criterion = split_criteria[info_gains.index(max(info_gains))]
            partitions = self.partition_instances(instances, best_criterion)

            def get_label_histogram(instances):
                "Return the histogram of labels for a list of instances"
                histogram = [
                        sum([instance[-1] == label for instance in partition])
                        for label in self.value_enumerations[-1]
                        ]
                return histogram

            if verbose:

                # Print top split criteria
                # each valued criteria is a list [feature_index, threshold,
                # info_gain]
                valued_criteria = [list(criterion) + [info_gain]
                        for criterion, info_gain
                        in zip(split_criteria, info_gains)]
                valued_criteria.sort(key=lambda x: x[-1], reverse=True)
                n_results = 5
                print "Top", n_results, "of", len(split_criteria), "criteria are:"
                for feat_ind, thresh, info_gain in valued_criteria:
                    feature_name = self.feature_names[feat_ind]
                    print '\t', feature_name, thresh,  \
                            "info gain =", info_gain
                split_is_mass =  \
                        self.feature_names[valued_criteria[0][0]] == "mass"
                #if split_is_mass: assert False

                # Print how instances will be split from this node
                feature_ind, threshold = best_criterion
                label_histograms = [get_label_histogram(partition)
                        for partition in partitions]
                print "Further splitting of",  \
                        self.feature_names[feature_ind],  \
                        "at", threshold
                print "\tPartitions break into [label1, label2]:"
                print "\t", " ".join(map(str, label_histograms))

            # Recursively split each partition
            node = Node.Node(best_criterion)
            for partition in partitions:
                subtree = self.make_subtree(partition, verbose=verbose)
                node.children.append(subtree)

            return node
    
    def determine_split_candidates(self, instances):
        """Return a list of split candidates.
        
        Each split candidate represents a decision in a DT node, and is a
        2-ple.
        The first element is the index of the feature (between 0 and n_-1
        inclusive). If the feature is nominal, the second element is None,
        otherwise the second element is the threshold of the numeric feature.
        """

        # Iterate over all features
        split_candidates = []
        for fi in range(self.n):

            # Get candidates according to norminality of this feature
            norminal = self.norminalities[fi]
            if norminal:
                # Norminal features only have one candidate
                curr_candidates = [(fi, None)]
            else:
                # Numerical features may have more than one candidate
                curr_candidates = self.determine_candidate_numeric_splits(
                        instances, fi)

            split_candidates.extend(curr_candidates)

        return split_candidates

    def determine_candidate_numeric_splits(self, instances, feature_ind):
        """Return a list of split candidates in ascending order of threshold.

        See determine_split_candidates() for representation
        """
        # Check that feature is numeric
        assert not self.norminalities[feature_ind]

        # Get list of unique feature values in ascending order
        unique_feature_values = list(set([x[feature_ind] for x in instances]))
        unique_feature_values.sort()

        # Partition instances into those with the same feature value
        partitions = [list() for i in range(len(unique_feature_values))]
        for instance in instances:
            feature_value = instance[feature_ind]
            partition_index = unique_feature_values.index(feature_value)
            partitions[partition_index].append(instance)

        # Candidate splits are mid-points of partitions with different class
        # labels
        candidates = []
        for p1, p2 in zip(partitions[:-1], partitions[1:]):
            label_set1 = set([instance[-1] for instance in p1])
            label_set2 = set([instance[-1] for instance in p2])

            if label_set1.symmetric_difference(label_set2):
                midpoint = (
                        p1[0][feature_ind] +
                        p2[0][feature_ind]) / 2
                candidates.append((feature_ind, midpoint, ))

        return candidates

    def predict(self, instance):
        """Predict the class of an unlabelled instance.

        instance -
            length-n list
        """
        assert len(instance) >= self.n
        curr_node = self.tree

        # Go down the tree as long as current node has child(ren)
        while curr_node.children:

            # Split decision is stored in node
            split_criterion = curr_node.data

            # We select the appropriate branch to traverse
            branch_index = self.look_up_branch_index(instance, split_criterion)
            curr_node = curr_node.children[branch_index]

        # Predicted label is the value stored in the leaf node
        return curr_node.data

    def print_tree(self, feature_names, node=None, level=0):
        """Recursively print a tree (starting from the root by default)
        """

        if node is None:
            node = self.tree

        node_feature_index, threshold = node.data
        for child_ind in range(len(node.children)):

            child = node.children[child_ind]

            # Description of current node, e.g. "color"
            node_str = feature_names[node_feature_index]

            # Description of branch, e.g. " = red" if norminal, " > 10" if
            # numeric
            norminal = self.norminalities[node_feature_index]
            if norminal:
                feature_value =  \
                        self.value_enumerations[node_feature_index][child_ind]
                branch_str = ' = ' + feature_value
            else:
                branch_str = [' <= ', ' > '][child_ind] + '%.6f' % threshold

            # Determine whether child is a leaf node
            child_is_leaf = not child.children

            # Print status of this child, including the prediction if node is a
            # leaf
            prediction_str = ': ' + child.data if child_is_leaf else ''
            print (level * '|       ' + "%s%s%s") %  \
                    (node_str, branch_str, prediction_str)

            # Recursively print child as subtree
            if not child_is_leaf:
                self.print_tree(feature_names, child, level + 1)

