import operator
import string
import itertools
import copy
import collections
import random
import csv
from cStringIO import StringIO
import subprocess
import tempfile
import os
import numpy
import sys
from distutils.version import StrictVersion
import dendropy
if StrictVersion(dendropy.__version__) < StrictVersion('4.0.0'):  # not sure on the exact version I need, but 3.12.0 is missing lots of vital tree fcns
    raise RuntimeError("dendropy version 4.0.0 or later is required (found version %s)." % dendropy.__version__)

import utils

lb_metrics = collections.OrderedDict(('lb' + let, 'local branching ' + lab) for let, lab in (('i', 'index'), ('r', 'ratio')))
default_lb_tau = 0.001
default_lbr_tau_factor = 20

# ----------------------------------------------------------------------------------------
def get_treestr(treefname):
    with open(treefname) as treefile:
        return '\n'.join(treefile.readlines())

# ----------------------------------------------------------------------------------------
def get_dendro_tree(treestr=None, treefname=None, taxon_namespace=None, schema='newick', ignore_existing_internal_node_labels=False, suppress_internal_node_taxa=False, debug=False):  # specify either <treestr> or <treefname>
    # <ignore_existing_internal_node_labels> is for when you want the internal nodes labeled (which we usually do, since we want to calculate selection metrics for internal nodes), but you also want to ignore the existing internal node labels (e.g. with FastTree output, where they're floats)
    # <suppress_internal_node_taxa> on the other hand is for when you don't want to have taxa for any internal nodes (e.g. when calculating the tree difference metrics, the two trees have to have the same taxon namespace, but since they in general have different internal nodes, the internal nodes can't have taxa)
    assert treestr is None or treefname is None
    if ignore_existing_internal_node_labels and suppress_internal_node_taxa:
        raise Exception('doesn\'t make sense to specify both')
    if treestr is None:
        treestr = get_treestr(treefname)
    if debug:
        print '   getting dendro tree from string:\n     %s' % treestr
        if taxon_namespace is not None:
            print '     and taxon namespace:  %s' % ' '.join([t.label for t in taxon_namespace])
    # dendropy doesn't make taxons for internal nodes by default, so it puts the label for internal nodes in node.label instead of node.taxon.label, but it crashes if it gets duplicate labels, so you can't just always turn off internal node taxon suppression
    dtree = dendropy.Tree.get_from_string(treestr, schema, taxon_namespace=taxon_namespace, suppress_internal_node_taxa=(ignore_existing_internal_node_labels or suppress_internal_node_taxa), preserve_underscores=True)
    label_nodes(dtree, ignore_existing_internal_node_labels=ignore_existing_internal_node_labels, suppress_internal_node_taxa=suppress_internal_node_taxa, debug=debug)  # set internal node labels to any found in <treestr> (unless <ignore_existing_internal_node_labels> is set), otherwise make some up (e.g. aa, ab, ac)

    # # uncomment for more verbosity:
    # check_node_labels(dtree, debug=debug)  # makes sure that for all nodes, node.taxon is not None, and node.label *is* None (i.e. that label_nodes did what it was supposed to, as long as suppress_internal_node_taxa wasn't set)
    # if debug:
    #     print utils.pad_lines(get_ascii_tree(dendro_tree=dtree))

    return dtree

# ----------------------------------------------------------------------------------------
def import_bio_phylo():
    if 'Bio.Phylo' not in sys.modules:
        from Bio import Phylo  # slow af to import
    return sys.modules['Bio.Phylo']

# ----------------------------------------------------------------------------------------
def get_bio_tree(treestr=None, treefname=None, schema='newick'):  # NOTE don't use this in future (all current uses are commented)
    Phylo = import_bio_phylo()
    if treestr is not None:
        return Phylo.read(StringIO(treestr), schema)
    elif treefname is not None:
        with open(treefname) as treefile:
            return Phylo.read(treefile, schema)
    else:
        assert False

# ----------------------------------------------------------------------------------------
def get_leaf_depths(tree, treetype='dendropy'):  # NOTE structure of dictionary may depend on <treetype>, e.g. whether non-named nodes are included (maybe it doesn't any more? unless you return <clade_keyed_depths> at least)
    if treetype == 'dendropy':
        depths = {n.taxon.label : n.distance_from_root() for n in tree.leaf_node_iter()}
    elif treetype == 'Bio':
        clade_keyed_depths = tree.depths()  # keyed by clade, not clade name (so unlabelled nodes are accessible)
        depths = {n.name : clade_keyed_depths[n] for n in tree.find_clades()}
    else:
        assert False

    return depths

# ----------------------------------------------------------------------------------------
def get_n_leaves(tree):
    return len(tree.leaf_nodes())

# ----------------------------------------------------------------------------------------
def collapse_nodes(dtree, keep_name, remove_name, debug=False):  # collapse edge between <keep_name> and <remove_name>, leaving remaining node with name <keep_name>
    # NOTE I wrote this to try to fix the phylip trees from lonr.r, but it ends up they're kind of unfixable... but this fcn may be useful in the future, I guess, and it works
    if debug:
        print '    collapsing %s and %s (the former will be the label for the surviving node)' % (keep_name, remove_name)
        print utils.pad_lines(get_ascii_tree(dendro_tree=dtree))
    keep_name_node, remove_name_node = [dtree.find_node_with_taxon_label(n) for n in (keep_name, remove_name)]  # nodes corresponding to {keep,remove}_name, not necessarily respectively the nodes we keep/remove
    swapped = False
    if keep_name_node in remove_name_node.child_nodes():
        assert remove_name_node not in keep_name_node.child_nodes()
        parent_node = remove_name_node
        parent_node.taxon.label = keep_name  # have to rename it, since we always actually keep the parent
        swapped = True
        child_node = keep_name_node
    elif remove_name_node in keep_name_node.child_nodes():
        assert keep_name_node not in remove_name_node.child_nodes()
        parent_node = keep_name_node
        child_node = remove_name_node
    else:
        print '    node names %s and %s don\'t share an edge:' % (keep_name, remove_name)
        print '        keep node children: %s' % ' '.join([n.taxon.label for n in keep_name_node.child_nodes()])
        print '      remove node children: %s' % ' '.join([n.taxon.label for n in remove_name_node.child_nodes()])
        raise Exception('see above')

    if child_node.is_leaf():
        dtree.prune_taxa([child_node.taxon])
        if debug:
            print '       pruned leaf node %s' % (('%s (renamed parent to %s)' % (remove_name, keep_name)) if swapped else remove_name)
    else:
        found = False
        for edge in parent_node.child_edge_iter():
            if edge.head_node is child_node:
                edge.collapse()  # removes child node (in dendropy language: inserts all children of the head_node (child) of this edge as children of the edge's tail_node (parent)) Doesn't modify edge lengths by default (i.e. collapsed edge should have zero length).
                found = True
                break
        assert found
        if debug:
            print '     collapsed edge between %s and %s' % (keep_name, remove_name)

    if debug:
        print utils.pad_lines(get_ascii_tree(dendro_tree=dtree))
    assert dtree.find_node_with_taxon_label(remove_name) is None

# ----------------------------------------------------------------------------------------
def check_node_labels(dtree, debug=False):
    if debug:
        print 'checking node labels for:'
        print utils.pad_lines(get_ascii_tree(dendro_tree=dtree, width=250))
    for node in dtree.preorder_node_iter():
        if node.taxon is None:
            raise Exception('taxon is None')
        if debug:
            print '    ok: %s' % node.taxon.label
        if node.label is not None:
            raise Exception('node.label not set to None')

# ----------------------------------------------------------------------------------------
# by default, mostly adds labels to internal nodes (also sometimes the root node) that are missing them
def label_nodes(dendro_tree, ignore_existing_internal_node_labels=False, ignore_existing_internal_taxon_labels=False, suppress_internal_node_taxa=False, initial_length=3, debug=False):
    if ignore_existing_internal_node_labels and suppress_internal_node_taxa:
        raise Exception('doesn\'t make sense to specify both')
    if debug:
        print '   labeling nodes'
        # print '    before:'
        # print utils.pad_lines(get_ascii_tree(dendro_tree))
    tns = dendro_tree.taxon_namespace
    initial_names = set([t.label for t in tns])  # should all be leaf nodes, except the naive sequence (at least for now)
    if debug:
        print '           initial taxon labels: %s' % ' '.join(sorted(initial_names))
    potential_names, used_names = None, None
    new_label, potential_names, used_names = utils.choose_new_uid(potential_names, used_names, initial_length=initial_length, shuffle=True)
    skipped_dbg, relabeled_dbg = [], []
    for node in dendro_tree.preorder_node_iter():
        if node.taxon is not None and not (ignore_existing_internal_taxon_labels and not node.is_leaf()):
            skipped_dbg += ['%s' % node.taxon.label]
            assert node.label is None  # if you want to change this, you have to start setting the node labels in build_lonr_tree(). For now, I like having the label in _one_ freaking place
            continue  # already properly labeled

        current_label = node.label
        node.label = None
        if suppress_internal_node_taxa and not node.is_leaf():
            continue

        if current_label is None or ignore_existing_internal_node_labels:
            new_label, potential_names, used_names = utils.choose_new_uid(potential_names, used_names)
        else:
            if tns.has_taxon_label(current_label):
                raise Exception('duplicate node label \'%s\'' % current_label)
            new_label = current_label

        if tns.has_taxon_label(new_label):
            raise Exception('failed labeling internal nodes (chose name \'%s\' that was already in the taxon namespace)' % new_label)

        tns.add_taxon(dendropy.Taxon(new_label))
        node.taxon = tns.get_taxon(new_label)
        relabeled_dbg += ['%s' % new_label]

    if debug:
        print '      skipped (already labeled): %s' % ' '.join(sorted(skipped_dbg))
        print '                   (re-)labeled: %s' % ' '.join(sorted(relabeled_dbg))
        # print '   after:'
        # print utils.pad_lines(get_ascii_tree(dendro_tree))

# ----------------------------------------------------------------------------------------
def translate_labels(dendro_tree, translation_pairs, debug=False):
    if debug:
        print get_ascii_tree(dendro_tree=dendro_tree)
    for old_label, new_label in translation_pairs:
        taxon = dendro_tree.taxon_namespace.get_taxon(old_label)
        if taxon is None:
            raise Exception('requested taxon with old name \'%s\' not present in tree' % old_label)
        taxon.label = new_label
        if debug:
            print '%20s --> %s' % (old_label, new_label)
    if debug:
        print get_ascii_tree(dendro_tree=dendro_tree)

# ----------------------------------------------------------------------------------------
def get_mean_leaf_height(tree=None, treestr=None):
    assert tree is None or treestr is None
    if tree is None:
        tree = get_dendro_tree(treestr=treestr, schema='newick')  # if we're calling it with a treestr rather than a tree, it's all from old code that only uses newick
    heights = get_leaf_depths(tree).values()
    return sum(heights) / len(heights)

# ----------------------------------------------------------------------------------------
def get_ascii_tree(dendro_tree=None, treestr=None, treefname=None, extra_str='', width=200, schema='newick'):
    """
        AsciiTreePlot docs (don't show up in as_ascii_plot()):
            plot_metric : str
                A string which specifies how branches should be scaled, one of:
                'age' (distance from tips), 'depth' (distance from root),
                'level' (number of branches from root) or 'length' (edge
                length/weights).
            show_internal_node_labels : bool
                Whether or not to write out internal node labels.
            leaf_spacing_factor : int
                Positive integer: number of rows between each leaf.
            width : int
                Force a particular display width, in terms of number of columns.
            node_label_compose_fn : function object
                A function that takes a Node object as an argument and returns
                the string to be used to display it.
    """
    if dendro_tree is None:
        assert treestr is None or treefname is None
        if treestr is None:
            treestr = get_treestr(treefname)
        dendro_tree = get_dendro_tree(treestr=treestr, schema=schema)
    if get_mean_leaf_height(dendro_tree) == 0.:  # we really want the max height, but since we only care whether it's zero or not this is the same
        return '%szero height' % extra_str
    elif get_n_leaves(dendro_tree) > 1:  # if more than one leaf
        start_char, end_char = '', ''
        def compose_fcn(x):
            if x.taxon is not None:  # if there's a taxon defined, use its label
                lb = x.taxon.label
            elif x.label is not None:  # use node label
                lb = x.label
            else:
                lb = 'o'
            return '%s%s%s' % (start_char, lb, end_char)
        dendro_str = dendro_tree.as_ascii_plot(width=width, plot_metric='length', show_internal_node_labels=True, node_label_compose_fn=compose_fcn)
        special_chars = [c for c in reversed(string.punctuation) if c not in set(dendro_str)]  # find some special characters that we can use to identify the start and end of each label (could also use non-printable special characters, but it shouldn't be necessary)
        if len(special_chars) >= 2:  # can't color them directly, since dendropy counts the color characters as printable
            start_char, end_char = special_chars[:2]  # NOTE the colors get screwed up when dendropy overlaps labels (or sometimes just straight up strips stuff), which it does when it runs out of space
            dendro_str = dendro_tree.as_ascii_plot(width=width, plot_metric='length', show_internal_node_labels=True, node_label_compose_fn=compose_fcn)  # call again after modiying compose fcn (kind of wasteful to call it twice, but it shouldn't make a difference)
            dendro_str = dendro_str.replace(start_char, utils.Colors['blue']).replace(end_char, utils.Colors['end'] + '  ')
        else:
            print '  %s can\'t color tree, no available special characters in get_ascii_tree()' % utils.color('red', 'note:')
        return_lines = [('%s%s' % (extra_str, line)) for line in dendro_str.split('\n')]
        return '\n'.join(return_lines)

        # Phylo = import_bio_phylo()
        # tmpf = StringIO()
        # if treestr is None:
        #     treestr = dendro_tree.as_string(schema=schema)
        # Phylo.draw_ascii(get_bio_tree(treestr=treestr, schema=schema), file=tmpf, column_width=width)  # this is pretty ugly, but the dendropy ascii printer just puts all the leaves at the same depth
        # return '\n'.join(['%s%s' % (extra_str, line) for line in tmpf.getvalue().split('\n')])
    else:
        return '%sone leaf' % extra_str

# ----------------------------------------------------------------------------------------
def rescale_tree(new_mean_height, dtree=None, treestr=None, debug=False):
    # TODO switch calls of this to dendro's scale_edges()
    """ rescale the branch lengths in dtree/treestr by <factor> """
    if dtree is None:
        dtree = get_dendro_tree(treestr=treestr, suppress_internal_node_taxa=True)
    mean_height = get_mean_leaf_height(tree=dtree)
    if debug:
        print '  current mean: %.4f   target height: %.4f' % (mean_height, new_mean_height)
    for edge in dtree.postorder_edge_iter():
        if edge.head_node is dtree.seed_node:  # why tf does the root node have an edge where it's the child?
            continue
        if debug:
            print '     %5s  %7e  -->  %7e' % (edge.head_node.taxon.label if edge.head_node.taxon is not None else 'None', edge.length, edge.length * new_mean_height / mean_height)
        edge.length *= new_mean_height / mean_height  # rescale every branch length in the tree by the ratio of desired to existing height (everybody's heights should be the same... but they never quite were when I was using Bio.Phylo, so, uh. yeah, uh. not sure what to do, but this is fine. It's checked below, anyway)
    dtree.update_bipartitions()  # probably doesn't really need to be done
    if debug:
        print '    final mean: %.4f' % get_mean_leaf_height(tree=dtree)
    if treestr:
        return dtree.as_string(schema='newick').strip()

# ----------------------------------------------------------------------------------------
def get_tree_difference_metrics(region, in_treestr, leafseqs, naive_seq, debug=False):
    taxon_namespace = dendropy.TaxonNamespace()  # in order to compare two trees with the metrics below, the trees have to have the same taxon namespace
    in_dtree = get_dendro_tree(treestr=in_treestr, taxon_namespace=taxon_namespace, suppress_internal_node_taxa=True, debug=debug)
    seqfos = [{'name' : 't%d' % (iseq + 1), 'seq' : seq} for iseq, seq in enumerate(leafseqs)]
    out_dtree = get_fasttree_tree(seqfos, naive_seq, taxon_namespace=taxon_namespace, suppress_internal_node_taxa=True, debug=debug)
    in_height = get_mean_leaf_height(tree=in_dtree)
    out_height = get_mean_leaf_height(tree=out_dtree)
    base_width = 100
    print '  %s: comparing chosen and bppseqgen output trees for' % (utils.color('green', 'full sequence' if region == 'all' else region))
    print '    %s' % utils.color('blue', 'input:')
    print get_ascii_tree(dendro_tree=in_dtree, extra_str='      ', width=base_width)
    print '    %s' % utils.color('blue', 'output:')
    print get_ascii_tree(dendro_tree=out_dtree, extra_str='        ', width=int(base_width*out_height/in_height))
    print '                   heights: %.3f   %.3f' % (in_height, out_height)
    print '      symmetric difference: %d' % dendropy.calculate.treecompare.symmetric_difference(in_dtree, out_dtree)
    print '        euclidean distance: %f' % dendropy.calculate.treecompare.euclidean_distance(in_dtree, out_dtree)
    print '              r-f distance: %f' % dendropy.calculate.treecompare.robinson_foulds_distance(in_dtree, out_dtree)

# ----------------------------------------------------------------------------------------
def get_fasttree_tree(seqfos, naive_seq, naive_seq_name='XnaiveX', taxon_namespace=None, suppress_internal_node_taxa=False, debug=False):
    if debug:
        print '    running FastTree on %d sequences plus a naive' % len(seqfos)
    with tempfile.NamedTemporaryFile() as tmpfile:
        tmpfile.write('>%s\n%s\n' % (naive_seq_name, naive_seq))
        for sfo in seqfos:
            tmpfile.write('>%s\n%s\n' % (sfo['name'], sfo['seq']))  # NOTE the order of the leaves/names is checked when reading bppseqgen output
        tmpfile.flush()  # BEWARE if you forget this you are fucked
        with open(os.devnull, 'w') as fnull:
            treestr = subprocess.check_output('./bin/FastTree -gtr -nt ' + tmpfile.name, shell=True, stderr=fnull)
    if debug:
        print '      converting FastTree newick string to dendro tree'
    dtree = get_dendro_tree(treestr=treestr, taxon_namespace=taxon_namespace, ignore_existing_internal_node_labels=not suppress_internal_node_taxa, suppress_internal_node_taxa=suppress_internal_node_taxa, debug=debug)
    dtree.reroot_at_node(dtree.find_node_with_taxon_label(naive_seq_name), update_bipartitions=True)
    return dtree

# ----------------------------------------------------------------------------------------
# copied from https://github.com/nextstrain/augur/blob/master/base/scores.py
# also see explanation here https://photos.app.goo.gl/gtjQziD8BLATQivR6
def set_lb_values(dtree, tau, use_multiplicities=False, normalize=False, add_dummy_root=False, add_dummy_leaves=False, debug=False):
    """
    traverses the tree in postorder and preorder to calculate the up and downstream tree length exponentially weighted by distance, then adds them as LBI.
    tree     -- tree for whose nodes the LBI is being computed (was biopython, now dendropy)
    """
    def getmulti(node):  # number of reads with the same sequence
        return node.multiplicity if use_multiplicities else 1  # it's nice to just not set a multiplicity if we don't want to incorporate them, since then we absolutely know it'll crash if we accidentally try to access it

    if add_dummy_root or add_dummy_leaves:
        if add_dummy_leaves:  # not set up to do it this way round at the moment
            assert add_dummy_root
        input_dtree = dtree
        dtree = get_tree_with_dummy_branches(dtree, 10*tau, add_dummy_leaves=add_dummy_leaves, debug=debug)  # replace <dtree> with a modified tree

    # calculate clock length (i.e. for each node, the distance to that node's parent)
    for node in dtree.postorder_node_iter():  # postorder vs preorder doesn't matter, but I have to choose one
        if node.parent_node is None:  # root node
            node.clock_length = 0.
        for child in node.child_node_iter():
            child.clock_length = child.distance_from_root() - node.distance_from_root()

    # node.lbi is the sum of <node.down_polarizer> (downward message from <node>'s parent) and its children's up_polarizers (upward messages)

    # traverse the tree in postorder (children first) to calculate message to parents (i.e. node.up_polarizer)
    for node in dtree.postorder_node_iter():
        node.down_polarizer = 0  # used for <node>'s lbi (this probabably shouldn't be initialized here, since it gets reset in the next loop [at least I think they all do])
        node.up_polarizer = 0  # used for <node>'s parent's lbi (but not <node>'s lbi)
        for child in node.child_node_iter():
            node.up_polarizer += child.up_polarizer
        bl = node.clock_length / tau
        node.up_polarizer *= numpy.exp(-bl)  # sum of child <up_polarizer>s weighted by an exponential decayed by the distance to <node>'s parent
        node.up_polarizer += getmulti(node) * tau * (1 - numpy.exp(-bl))  # add the actual contribution (to <node>'s parent's lbi) of <node>: zero if the two are very close, increasing toward asymptote of <tau> for distances near 1/tau (integral from 0 to l of decaying exponential)

    # traverse the tree in preorder (parents first) to calculate message to children (i.e. child1.down_polarizer)
    for node in dtree.preorder_internal_node_iter():
        for child1 in node.child_node_iter():  # calculate down_polarizer for each of <node>'s children
            child1.down_polarizer = node.down_polarizer  # first sum <node>'s down_polarizer...
            for child2 in node.child_node_iter():  # and the *up* polarizers of any other children of <node>
                if child1 != child2:
                    child1.down_polarizer += child2.up_polarizer  # add the contribution of <child2> to its parent's (<node>'s) lbi (i.e. <child2>'s contribution to the lbi of its *siblings*)
            bl = child1.clock_length / tau
            child1.down_polarizer *= numpy.exp(-bl)  # and decay the previous sum by distance between <child1> and its parent (<node>)
            child1.down_polarizer += getmulti(child1) * tau * (1 - numpy.exp(-bl))  # add contribution of <child1> to its own lbi: zero if it's very close to <node>, increasing to max of <tau> (integral from 0 to l of decaying exponential)

    # go over all nodes and calculate the LBI (can be done in any order)
    max_LBI = 0.
    for node in dtree.postorder_node_iter():
        node.lbi = node.down_polarizer
        node.lbr = 0.
        for child in node.child_node_iter():
            node.lbi += child.up_polarizer
            node.lbr += child.up_polarizer
        if node.down_polarizer > 0.:
            node.lbr /= node.down_polarizer  # it might make more sense to not include the branch between <node> and its parent in either the numerator or denominator (here it's included in the denominator), but this way I don't have to change any of the calculations above
        if normalize and node.lbi > max_LBI:
            max_LBI = node.lbi

    if normalize:  # normalize to range [0, 1]
        for node in dtree.postorder_node_iter():
            node.lbi /= max_LBI

    if add_dummy_root or add_dummy_leaves:  # get the lb values from the modified tree, and the swap back
        for node in input_dtree.preorder_node_iter():
            ntmp = dtree.find_node_with_taxon_label(node.taxon.label)
            node.clock_length = ntmp.clock_length
            node.lbi = ntmp.lbi
            node.lbr = ntmp.lbr
        dtree = input_dtree  # only actually affects the debug print below

    if debug:
        print '  calculated lb values with tau %.3f' % tau
        max_width = str(max([len(n.taxon.label) for n in dtree.postorder_node_iter()]))
        print ('   %' + max_width + 's   multi     lbi       lbr      clock length') % 'node'
        for node in dtree.postorder_node_iter():
            multi_str = str(getmulti(node)) if (use_multiplicities and getmulti(node) > 1) else ''
            print ('    %' + max_width + 's  %3s   %8.3f  %8.3f    %8.3f') % (node.taxon.label, multi_str, node.lbi, node.lbr, node.clock_length)

# ----------------------------------------------------------------------------------------
def set_multiplicities(dtree, annotation, input_metafo, debug=False):
    def get_multi(uid):
        if input_metafo is None:  # NOTE the input meta file key 'multiplicities' *could* be in the annotation but we *don't* want to use it (at least at the moment, since we haven't yet established rules for precedence with 'duplicates')
            if uid not in annotation['unique_ids']:  # could be from wonky names from lonr.r, also could be from FastTree tree where we don't get inferred intermediate sequences
                return 1
            if 'duplicates' not in annotation: # if 'duplicates' isn't in the annotation, it's probably simulation, but even if not, if there's no duplicate info then assuming multiplicities of 1 should be fine (maybe should add duplicate info to simulation? it wouldn't really make sense though, since we don't collapse duplicates in simulation info)
                return 1
            iseq = annotation['unique_ids'].index(uid)
            return len(annotation['duplicates'][iseq]) + 1
        elif annotation is None:
            if uid not in input_metafo:
                return 1
            return input_metafo[uid]['multiplicity']
        else:
            assert False  # doesn't make sense to set both of 'em

    if annotation is None and input_metafo is None:
        raise Exception('have to get the multiplicity info from somewhere')

    for node in dtree.postorder_node_iter():
        node.multiplicity = get_multi(node.taxon.label)

# ----------------------------------------------------------------------------------------
def get_tree_with_dummy_branches(old_dtree, dummy_edge_length, add_dummy_leaves=False, dummy_str='dummy', debug=False): # add long branches above root and below each leaf, since otherwise we're assuming that (e.g.) leaf node fitness is zero
    # add parent above old root (i.e. root of new tree)
    tns = dendropy.TaxonNamespace()
    new_root_label = dummy_str + '-root'
    tns.add_taxon(dendropy.Taxon(new_root_label))
    new_root_node = dendropy.Node(taxon=tns.get_taxon(new_root_label))
    new_root_node.multiplicity = old_dtree.seed_node.multiplicity
    new_dtree = dendropy.Tree(taxon_namespace=tns, seed_node=new_root_node)

    # then add the entire old tree under this, node by node (I tried just adding the old tree root as a child of the new root, but some internal things got screwed up, e.g. update_bipartitions() was crashing (although it did partially work))
    tns.add_taxon(dendropy.Taxon(old_dtree.seed_node.taxon.label))
    tmpnode = new_root_node.new_child(taxon=tns.get_taxon(old_dtree.seed_node.taxon.label), edge_length=dummy_edge_length)
    tmpnode.multiplicity = old_dtree.seed_node.multiplicity
    for edge in new_root_node.child_edge_iter():
        edge.length = dummy_edge_length
    for old_node in old_dtree.preorder_node_iter():
        new_node = new_dtree.find_node_with_taxon_label(old_node.taxon.label)
        for edge in old_node.child_edge_iter():
            tns.add_taxon(dendropy.Taxon(edge.head_node.taxon.label))
            tmpnode = new_node.new_child(taxon=tns.get_taxon(edge.head_node.taxon.label), edge_length=edge.length)
            tmpnode.multiplicity = old_node.multiplicity

    if add_dummy_leaves:
        # then add dummy child branches to each leaf
        for lnode in new_dtree.leaf_node_iter():
            new_label = '%s-%s' % (dummy_str, lnode.taxon.label)
            tns.add_taxon(dendropy.Taxon(new_label))
            new_child_node = lnode.new_child(taxon=tns.get_taxon(new_label), edge_length=dummy_edge_length)
            new_child_node.multiplicity = lnode.multiplicity

    # new_dtree.update_bipartitions()  # not sure if I should do this?

    if debug:
        print '    added dummy branches to tree:'
        print get_ascii_tree(dendro_tree=new_dtree, extra_str='      ', width=350)

    return new_dtree

# ----------------------------------------------------------------------------------------
def calculate_lb_values(dtree, lbi_tau, lbr_tau, annotation=None, input_metafo=None, add_dummy_root=False, add_dummy_leaves=False, use_multiplicities=False, naive_seq_name=None, extra_str=None, debug=False):

    if max(get_leaf_depths(dtree).values()) > 1:  # should only happen on old simulation files
        if annotation is None:
            raise Exception('tree needs rescaling in lb calculation (metrics will be wrong), but no annotation was passed in')
        print '  %s leaf depths greater than 1, so rescaling by sequence length' % utils.color('yellow', 'warning')
        dtree.scale_edges(1. / numpy.mean([len(s) for s in annotation['seqs']]))  # using treeutils.rescale_tree() breaks, it seems because the update_bipartitions() call removes nodes near root on unrooted trees

    if naive_seq_name is not None:  # not really sure if there's a reason to do this
        raise Exception('think about this before turning it on again')
        dtree.reroot_at_node(dtree.find_node_with_taxon_label(naive_seq_name), update_bipartitions=True)

    if debug:
        print '   lbi/lbr%s:' % ('' if extra_str is None else ' for %s' % extra_str)
        print '      calculating lb values with taus %.4f (%.4f) and tree:' % (lbi_tau, lbr_tau)
        print utils.pad_lines(get_ascii_tree(dendro_tree=dtree, width=400))

    if use_multiplicities:  # it's kind of weird to, if we don't want to incorporate multiplicities,  both not set them *and* tell set_lb_values() not to use them, but I like the super explicitness of this setup, i.e. this makes it impossible to silently/accidentally pass in multiplicities.
        set_multiplicities(dtree, annotation, input_metafo, debug=debug)

    lbvals = {'tree' : dtree.as_string(schema='newick')}  # NOTE at least for now, i'm adding the tree *before* calculating lbi or lbr, since the different tau values means it'd be more complicated
    set_lb_values(dtree, lbi_tau, use_multiplicities=use_multiplicities, add_dummy_root=add_dummy_root, add_dummy_leaves=add_dummy_leaves, debug=debug)
    lbvals['lbi'] = {n.taxon.label : float(n.lbi) for n in dtree.postorder_node_iter()}
    set_lb_values(dtree, lbr_tau, use_multiplicities=use_multiplicities, add_dummy_root=add_dummy_root, add_dummy_leaves=add_dummy_leaves, debug=debug)
    lbvals['lbr'] = {n.taxon.label : float(n.lbr) for n in dtree.postorder_node_iter()}

    # this is ugly, but a) I don't use the values attached to the nodes anywhere a.t.m. and b) at least for now I'm running twice with different tau values for lbi/lbr, which I don't really like, but it means there's the potential for pulling a metric calculated with the wrong tau value from the tree
    for node in dtree.postorder_node_iter():
        delattr(node, 'lbi')
        delattr(node, 'lbr')

    return lbvals

# ----------------------------------------------------------------------------------------
lonr_files = {  # this is kind of ugly, but it's the cleanest way I can think of to have both this code and the R code know what they're called
    'phy.outfname' : 'phy_out.txt',
    'phy.treefname' : 'phy_tree.nwk',
    'outseqs.fname' : 'outseqs.fasta',
    'edgefname' : 'edges.tab',
    'names.fname' : 'names.tab',
    'lonrfname' : 'lonr.csv',
}

# ----------------------------------------------------------------------------------------
def build_lonr_tree(edgefos, debug=False):
    # NOTE have to build the tree from the edge file, since the lonr code seems to add nodes that aren't in the newick file (which is just from phylip).
    all_nodes = set([e['from'] for e in edgefos] + [e['to'] for e in edgefos])
    effective_root_nodes = set([e['from'] for e in edgefos]) - set([e['to'] for e in edgefos])  # "effective" because it can be in an unrooted tree. Not sure if there's always exactly one node that has no inbound edges though
    if len(effective_root_nodes) != 1:
        raise Exception('too many effective root nodes: %s' % effective_root_nodes)
    root_label = list(effective_root_nodes)[0]  # should be '1' for dnapars
    if debug:
        print '      chose \'%s\' as root node' % root_label
    tns = dendropy.TaxonNamespace(all_nodes)
    root_node = dendropy.Node(taxon=tns.get_taxon(root_label))  # NOTE this sets node.label and node.taxon.label to the same thing, which may or may not be what we want  # label=root_label,    (if you start setting the node labels again, you also have to translate them below)
    dtree = dendropy.Tree(taxon_namespace=tns, seed_node=root_node)
    remaining_nodes = copy.deepcopy(all_nodes) - set([root_label])  # a.t.m. I'm not actually using <all_nodes> after this, but I still want to keep them separate in case I start using it

    weight_or_distance_key = 'distance'  # maybe should I be using the 'weight' column? I think they're just proportional though so I guess it shouldn't matter (same thing in the line below) # 
    root_edgefos = [efo for efo in edgefos if efo['from'] == root_label]
    for efo in root_edgefos:
        dtree.seed_node.new_child(taxon=tns.get_taxon(efo['to']), edge_length=efo[weight_or_distance_key])  # label=efo['to'],    (if you start setting the node labels again, you also have to translate them below)
        remaining_nodes.remove(efo['to'])

    while len(remaining_nodes) > 0:
        n_removed = 0  # I think I don't need this any more (it only happened before I remembered to remove the root node), but it doesn't seem like it'll hurt)
        for lnode in dtree.leaf_node_iter():
            children = [efo for efo in edgefos if efo['from'] == lnode.taxon.label]
            if debug > 1 and len(children) > 0:
                print '    adding children to %s:' % lnode.taxon.label
            for chfo in children:
                lnode.new_child(taxon=tns.get_taxon(chfo['to']), edge_length=chfo[weight_or_distance_key])  # label=chfo['to'],   (if you start setting the node labels again, you also have to translate them below)
                remaining_nodes.remove(chfo['to'])
                n_removed += 1
                if debug > 1:
                    print '              %s' % chfo['to']
        if debug > 1:
            print '  remaining: %d' % len(remaining_nodes)
        if len(remaining_nodes) > 0 and n_removed == 0:  # if there's zero remaining, we're just about to break anyway
            if debug > 1:
                print '  didn\'t remove any, so breaking: %s' % remaining_nodes
            break

    return dtree

# ----------------------------------------------------------------------------------------
def parse_lonr(outdir, input_seqfos, naive_seq_name, reco_info=None, debug=False):
    def get_node_type_from_name(name, debug=False):  # internal nodes in simulated trees should be labeled like 'mrca-<stuff>' (has to correspond to what bcr-phylo-benchmark did)
        if 'mrca' in name:
            return 'internal'
        elif 'leaf' in name:
            return 'leaf'
        else:
            if debug:
                print '    not sure of node type for \'%s\'' % name
            return None

    # get lonr names (lonr replaces them with shorter versions, I think because of phylip)
    lonr_names, input_names = {}, {}
    with open(outdir + '/' + lonr_files['names.fname']) as namefile:  # headers: "head	head2"
        reader = csv.DictReader(namefile, delimiter='\t')
        for line in reader:
            if line['head'][0] != 'L' and line['head'] != naive_seq_name:  # internal node
                dummy_int = int(line['head'])  # check that it's just a (string of a) number
                assert line['head2'] == '-'
                continue
            input_names[line['head']] = line['head2']  # head2 is our names
            lonr_names[line['head2']] = line['head']

    def final_name(lonr_name):
        return input_names.get(lonr_name, lonr_name)

    # read edge info (i.e., implicitly, the tree that lonr.r used)
    edgefos = []  # headers: "from    to      weight  distance"
    with open(outdir + '/' + lonr_files['edgefname']) as edgefile:
        reader = csv.DictReader(edgefile, delimiter='\t')
        for line in reader:
            line['distance'] = int(line['distance'])
            line['weight'] = float(line['weight'])
            edgefos.append(line)

    dtree = build_lonr_tree(edgefos, debug=debug)

    # switch leaves to input names
    for node in dtree.leaf_node_iter():
        node.taxon.label = input_names[node.taxon.label]
        assert node.label is None  #   (if you start setting the node labels again, you also have to translate them here)
        # node.label = node.taxon.label  #   (if you start setting the node labels again, you also have to translate them here)

    if debug:
        print utils.pad_lines(get_ascii_tree(dendro_tree=dtree, width=250))

    nodefos = {node.taxon.label : {} for node in dtree.postorder_node_iter()}  # info for each node (internal and leaf), destined for output

    # read the sequences for both leaves and inferred (internal) ancestors
    seqfos = {final_name(sfo['name']) : sfo['seq'] for sfo in utils.read_fastx(outdir + '/' + lonr_files['outseqs.fname'])}
    input_seqfo_dict = {sfo['name'] : sfo['seq'] for sfo in input_seqfos}  # just to make sure lonr didn't modify the input sequences
    for node in dtree.postorder_node_iter():
        label = node.taxon.label
        if label not in seqfos:
            raise Exception('unexpected sequence name %s' % label)
        if node.is_leaf() or label == naive_seq_name:
            if label not in input_seqfo_dict:
                raise Exception('leaf node \'%s\' not found in input seqs' % label)
            if seqfos[label] != input_seqfo_dict[label]:
                print 'input: %s' % input_seqfo_dict[label]
                print ' lonr: %s' % utils.color_mutants(input_seqfo_dict[label], seqfos[label], align=True)
                raise Exception('lonr leaf sequence doesn\'t match input sequence (see above)')
        nodefos[label]['seq'] = seqfos[label]

    # read actual lonr info
    lonrfos = []
    if debug:
        print '     pos  mutation   lonr   syn./a.b.d.    parent   child'
    with open(outdir + '/' + lonr_files['lonrfname']) as lonrfile:  # heads: "mutation,LONR,mutation.type,position,father,son,flag"
        reader = csv.DictReader(lonrfile)
        for line in reader:
            assert len(line['mutation']) == 2
            assert line['mutation.type'] in ('S', 'R')
            assert line['flag'] in ('TRUE', 'FALSE')
            mutation = line['mutation'].upper()  # dnapars has it upper case already, but neighbor has it lower case
            parent_name = final_name(line['father'])
            child_name = final_name(line['son'])
            parent_seq = nodefos[parent_name]['seq']
            pos = int(line['position']) - 1  # switch from one- to zero-indexing
            child_seq = nodefos[child_name]['seq']
            if parent_seq[pos] != mutation[0] or child_seq[pos] != mutation[1]:
                print 'parent: %s' % parent_seq
                print ' child: %s' % utils.color_mutants(parent_seq, child_seq, align=True)
                raise Exception('mutation info (%s at %d) doesn\'t match sequences (see above)' % (mutation, pos))

            lonrfos.append({
                'mutation' : mutation,
                'lonr' : float(line['LONR']),
                'synonymous' : line['mutation.type'] == 'S',
                'position' : pos,
                'parent' : parent_name,
                'child' : child_name,
                'affected_by_descendents' : line['flag'] == 'TRUE',
            })
            if debug:
                lfo = lonrfos[-1]
                print '     %3d     %2s     %5.2f     %s / %s        %4s      %-20s' % (lfo['position'], lfo['mutation'], lfo['lonr'], 'x' if lfo['synonymous'] else ' ', 'x' if lfo['affected_by_descendents'] else ' ', lfo['parent'], lfo['child'])

    # check for duplicate nodes (not sure why lonr.r kicks these, but I should probably collapse them at some point)
    # in simulation, we sample internal nodes, but then lonr.r's tree construction forces these to be leaves, but then frequently they're immediately adjacent to internal nodes in lonr.r's tree... so we try to collapse them
    duplicate_groups = utils.group_seqs_by_value(nodefos.keys(), keyfunc=lambda q: nodefos[q]['seq'])
    duplicate_groups = [g for g in duplicate_groups if len(g) > 1]
    if len(duplicate_groups) > 0:
        n_max = 15
        dbg_str = ',  '.join([' '.join(g) for g in duplicate_groups[:n_max]])  # only print the first 15 of 'em, if there's more
        if len(duplicate_groups) > n_max:
            dbg_str += utils.color('blue', ' [...]')
        print '    collapsing %d groups of nodes with duplicate sequences (probably just internal nodes that were renamed by lonr.r): %s' % (len(duplicate_groups), dbg_str)
    for dgroup in duplicate_groups:
        non_phylip_names = [n for n in dgroup if get_node_type_from_name(n) is not None]
        if len(non_phylip_names) == 0:  # and phylip internal node names are of form str(<integer>), so just choose the first alphabetically, because whatever
            name_to_use = sorted(dgroup)[0]
        elif len(non_phylip_names) == 1:
            name_to_use = non_phylip_names[0]
        else:
            raise Exception('wtf %s (should\'ve been either one or zero non-phylip names)' % non_phylip_names)
        names_to_remove = [n for n in dgroup if n != name_to_use]

        for rname in names_to_remove:  # only info in here a.t.m. is the sequence
            del nodefos[rname]
            # NOTE not collapsing nodes in tree to match <nodefos> (see comment on next line)
            # collapse_nodes(dtree, name_to_use, rname, allow_failure=True, debug=True)  # holy fuckballs this is not worth the effort (it doesn't really work because the tree is too screwed up) [just gave up and added the duplicate info to the return dict]

        for lfo in lonrfos:
            for key in ('parent', 'child'):
                if lfo[key] in names_to_remove:
                    lfo[key] = name_to_use

    return {'tree' : dtree.as_string(schema='newick'), 'nodes' : nodefos, 'values' : lonrfos}

# ----------------------------------------------------------------------------------------
def run_lonr(input_seqfos, naive_seq_name, workdir, tree_method, lonr_code_file=None, phylip_treefile=None, phylip_seqfile=None, seed=1, debug=False):
    if lonr_code_file is None:
        lonr_code_file = os.path.dirname(os.path.realpath(__file__)).replace('/python', '/bin/lonr.r')
    if not os.path.exists(lonr_code_file):
        raise Exception('lonr code file %s d.n.e.' % lonr_code_file)
    if tree_method not in ('dnapars', 'neighbor'):
        raise Exception('unexpected lonr tree method %s' % tree_method)

    # # installation stuff
    # rcmds = [
    #     'source("https://bioconductor.org/biocLite.R")',
    #     'biocLite("Biostrings")',
    #     'install.packages("seqinr", repos="http://cran.rstudio.com/")',
    # ]
    # utils.run_r(rcmds, workdir)

    input_seqfile = workdir + '/input-seqs.fa'
    with open(input_seqfile, 'w') as iseqfile:
        for sfo in input_seqfos:
            iseqfile.write('>%s\n%s\n' % (sfo['name'], sfo['seq']))

    existing_phylip_output_str = ''
    if phylip_treefile is not None:  # using existing phylip output, e.g. from cft
        tree = get_dendro_tree(treefname=phylip_treefile)
        edgefos = []
        for node in tree.preorder_node_iter():
            for edge in node.child_edge_iter():
                edgefos.append({'from' : node.taxon.label, 'to' : edge.head_node.taxon.label, 'weight' : edge.length})
        existing_edgefname = workdir + '/edges.csv'
        existing_node_seqfname = workdir + '/infered-node-seqs.fa'
        with open(existing_edgefname, 'w') as edgefile:
            writer = csv.DictWriter(edgefile, ('from', 'to', 'weight'))
            writer.writeheader()
            for line in edgefos:
                writer.writerow(line)
        with open(existing_node_seqfname, 'w') as node_seqfile:
            writer = csv.DictWriter(node_seqfile, ('head', 'seq'))
            writer.writeheader()
            for sfo in utils.read_fastx(phylip_seqfile):
                writer.writerow({'head' : sfo['name'], 'seq' : sfo['seq']})
        existing_phylip_output_str = ', existing.edgefile="%s", existing.node.seqfile="%s"' % (existing_edgefname, existing_node_seqfname)

    rcmds = [
        'source("%s")' % lonr_code_file,
        'set.seed(%d)' % seed,
        'G.phy.outfname = "%s"'  % lonr_files['phy.outfname'],  # this is a pretty shitty way to do this, but the underlying problem is that there's too many files, but I don't want to parse them all into one or two files in R, so I need to pass all of 'em to the calling python script
        'G.phy.treefname = "%s"' % lonr_files['phy.treefname'],
        'G.outseqs.fname = "%s"' % lonr_files['outseqs.fname'],
        'G.edgefname = "%s"'     % lonr_files['edgefname'],
        'G.names.fname = "%s"'   % lonr_files['names.fname'],
        'G.lonrfname = "%s"'     % lonr_files['lonrfname'],
        'compute.LONR(method="%s", infile="%s", workdir="%s/", outgroup="%s"%s)' % (tree_method, input_seqfile, workdir, naive_seq_name, existing_phylip_output_str),
    ]
    outstr, errstr = utils.run_r(rcmds, workdir, extra_str='      ', return_out_err=True, debug=debug)
    if debug:
        print utils.pad_lines(outstr)
        print utils.pad_lines(errstr)

    os.remove(input_seqfile)
    if phylip_treefile is not None:
        os.remove(existing_edgefname)
        os.remove(existing_node_seqfname)

# ----------------------------------------------------------------------------------------
def calculate_liberman_lonr(input_seqfos=None, line=None, reco_info=None, phylip_treefile=None, phylip_seqfile=None, tree_method=None, naive_seq_name='X-naive-X', seed=1, debug=False):
    # NOTE see issues/notes in bin/lonr.r
    if phylip_treefile is not None or phylip_seqfile is not None:
        raise Exception('never got this (passing phylip output files to lonr.r) to work -- lonr.r kept barfing, although if you were running exactly the same phylip commands as lonr.r does, it would probably work.')
    assert input_seqfos is None or line is None
    if input_seqfos is None:
        input_seqfos = [{'name' : line['unique_ids'][iseq], 'seq' : line['seqs'][iseq]} for iseq in range(len(line['unique_ids']))]
        input_seqfos.insert(0, {'name' : naive_seq_name, 'seq' : line['naive_seq']})
    if tree_method is None:
        tree_method = 'dnapars' if len(input_seqfos) < 500 else 'neighbor'

    workdir = utils.choose_random_subdir('/tmp/%s' % os.getenv('USER'))
    os.makedirs(workdir)

    if debug:
        print '  %s' % utils.color('green', 'lonr:')
    run_lonr(input_seqfos, naive_seq_name, workdir, tree_method, phylip_treefile=phylip_treefile, phylip_seqfile=phylip_seqfile, seed=seed, debug=debug)
    lonr_info = parse_lonr(workdir, input_seqfos, naive_seq_name, reco_info=reco_info, debug=debug)

    for fn in lonr_files.values():
        os.remove(workdir + '/' + fn)
    os.rmdir(workdir)

    return lonr_info

# ----------------------------------------------------------------------------------------
def get_tree_metric_lines(annotations, cpath, reco_info, use_true_clusters, debug=False):
    # collect inferred and true events
    lines_to_use, true_lines_to_use = None, None
    if use_true_clusters:  # use clusters from the true partition, rather than inferred one
        assert reco_info is not None
        true_partition = utils.get_true_partition(reco_info)
        print '    using %d true clusters to calculate inferred tree metrics (sizes: %s)' % (len(true_partition), ' '.join([str(len(c)) for c in true_partition]))
        lines_to_use, true_lines_to_use = [], []
        for cluster in true_partition:
            true_lines_to_use.append(utils.synthesize_multi_seq_line_from_reco_info(cluster, reco_info))  # note: duplicates (a tiny bit of) code in utils.print_true_events()
            max_in_common, ustr_to_use = None, None  # look for the inferred cluster that has the most uids in common with this true cluster
            for ustr in annotations:  # order will be different in reco info and inferred clusters
                # NOTE if I added in the duplicate uids from the inferred cluster, these would usually/always have perfect overlap
                n_in_common = len(set(ustr.split(':')) & set(cluster))  # can't just look for the actual cluster since we collapse duplicates, but bcr-phylo doesn't (but maybe I should throw them out when parsing bcr-phylo output)
                if max_in_common is None or n_in_common > max_in_common:
                    ustr_to_use = ustr
                    max_in_common = n_in_common
            if max_in_common is None:
                raise Exception('cluster \'%s\' not found in inferred annotations (probably because use_true_clusters was set)' % ':'.join(cluster))
            if max_in_common < len(cluster):
                print '    note: couldn\'t find an inferred cluster that shared all sequences with true cluster (best was %d/%d)' % (max_in_common, len(cluster))
            lines_to_use.append(annotations[ustr_to_use])
    else:  # use clusters from the inferred partition (whether from <cpath> or <annotations>), and synthesize clusters exactly matching these using single true annotations from <reco_info> (to repeat: these are *not* true clusters)
        if cpath is not None:  # restrict it to clusters in the best partition (at the moment there will only be extra ones if either --calculate-alternative-naive-seqs or --write-additional-cluster-annotations are set, but in the future it could also be the default)
            lines_to_use = [annotations[':'.join(c)] for c in cpath.partitions[cpath.i_best]]
        else:
            lines_to_use = annotations.values()
        if reco_info is not None:
            for line in lines_to_use:
                true_line = utils.synthesize_multi_seq_line_from_reco_info(line['unique_ids'], reco_info)
                true_lines_to_use.append(true_line)

    return lines_to_use, true_lines_to_use

# ----------------------------------------------------------------------------------------
def plot_tree_metrics(base_plotdir, lines_to_use, true_lines_to_use, lb_tau, debug=False):
    import plotting

    inf_plotdir = base_plotdir + '/inferred-tree-metrics'
    utils.prep_dir(inf_plotdir, wildlings=['*.svg', '*.html'], subdirs=[m + tstr for m in lb_metrics for tstr in ['-vs-affinity', '-vs-shm']])
    fnames = plotting.plot_lb_vs_shm(inf_plotdir, lines_to_use)
    # fnames += plotting.plot_lb_distributions(inf_plotdir, lines_to_use)
    fnames += plotting.plot_lb_vs_affinity('inferred', inf_plotdir, lines_to_use, 'lbi', lb_metrics['lbi'])
    plotting.make_html(inf_plotdir, fnames=fnames, new_table_each_row=True, htmlfname=inf_plotdir + '/overview.html', extra_links=[(subd, '%s/%s.html' % (inf_plotdir, subd)) for subd in lb_metrics.keys()])

    if true_lines_to_use is not None:
        if all(affy is None for affy in true_lines_to_use[0]['affinities']):  # if it's bcr-phylo simulation we should have affinities for everybody, otherwise presumably for nobody
            print '  %s no affinity information in this simulation, so can\'t plot lb/affinity stuff' % utils.color('yellow', 'note')
        else:
            true_plotdir = base_plotdir + '/true-tree-metrics'
            utils.prep_dir(true_plotdir, wildlings=['*.svg'], subdirs=[m + tstr for m in lb_metrics for tstr in ['-vs-shm']])
            fnames = []
            for lb_metric, lb_label in lb_metrics.items():
                fnames += plotting.plot_lb_vs_affinity('true', true_plotdir, true_lines_to_use, lb_metric, lb_label, all_clusters_together=True, is_simu=True)
                # fnames[-1] += plotting.plot_lb_vs_delta_affinity(true_plotdir, true_lines_to_use, lb_metric, lb_label)[0]
                fnames[-1] += plotting.plot_lb_vs_ancestral_delta_affinity(true_plotdir, true_lines_to_use, lb_metric, lb_label)[0]
            fnames.append([])
            for lb_metric, lb_label in lb_metrics.items():
                fnames[-1] += plotting.plot_true_vs_inferred_lb(true_plotdir, true_lines_to_use, lines_to_use, lb_metric, lb_label)
            fnames += plotting.plot_lb_vs_shm(true_plotdir, true_lines_to_use, is_simu=True)
            plotting.make_html(true_plotdir, fnames=fnames)

# ----------------------------------------------------------------------------------------
def get_tree_for_line(line, treefname=None, cpath=None, annotations=None, use_true_clusters=False, debug=False):
    # figure out how we want to get the inferred tree
    if treefname is not None:
        dtree = get_dendro_tree(treefname=treefname, debug=debug)
        origin = 'treefname'
    elif False:  # use_liberman_lonr_tree:  # NOTE see issues/notes in bin/lonr.r
        lonr_info = calculate_liberman_lonr(line=line, reco_info=reco_info, debug=debug)
        dtree = get_dendro_tree(treestr=lonr_info['tree'])
        # line['tree-info']['lonr'] = lonr_info
        origin = 'lonr'
    elif cpath is not None and not use_true_clusters:  # if <use_true_clusters> is set, then the clusters in <lines_to_use> won't correspond to the history in <cpath>, so this won't work
        assert annotations is not None
        i_only_cluster = cpath.partitions[cpath.i_best].index(line['unique_ids'])  # if this fails, the cpath and lines_to_use are out of sync (which I think shouldn't happen?)
        cpath.make_trees(annotations=annotations, i_only_cluster=i_only_cluster, get_fasttrees=True, debug=False)
        dtree = cpath.trees[i_only_cluster]  # as we go through the loop, the <cpath> is presumably filling all of these in
        origin = 'cpath'
    else:
        seqfos = [{'name' : uid, 'seq' : seq} for uid, seq in zip(line['unique_ids'], line['seqs'])]
        dtree = get_fasttree_tree(seqfos, line['naive_seq'], debug=debug)
        origin = 'fasttree'

    return {'tree' : dtree, 'origin' : origin}

# ----------------------------------------------------------------------------------------
def calculate_tree_metrics(annotations, min_tree_metric_cluster_size, lb_tau, cpath=None, treefname=None, reco_info=None, use_true_clusters=False, base_plotdir=None,
                           add_dummy_root=False, debug=False):
    if reco_info is not None:
        for tmpline in reco_info.values():
            assert len(tmpline['unique_ids']) == 1  # at least for the moment, we're splitting apart true multi-seq lines when reading in seqfileopener.py

    lines_to_use, true_lines_to_use = get_tree_metric_lines(annotations, cpath, reco_info, use_true_clusters, debug=debug)

    # get tree and calculate metrics for inferred lines
    n_skipped = len([l for l in lines_to_use if len(l['unique_ids']) < min_tree_metric_cluster_size])
    n_already_there = 0
    lines_to_use = sorted([l for l in lines_to_use if len(l['unique_ids']) >= min_tree_metric_cluster_size], key=lambda l: len(l['unique_ids']), reverse=True)
    tree_origin_counts = {n : {'count' : 0, 'label' : l} for n, l in (('treefname', 'read from %s' % treefname), ('cpath', 'made from cpath'), ('fasttree', 'ran fasttree'), ('lonr', 'ran liberman lonr'))}
    print 'calculating tree metrics for %d cluster%s with size%s: %s' % (len(lines_to_use), utils.plural(len(lines_to_use)), utils.plural(len(lines_to_use)), ' '.join(str(len(l['unique_ids'])) for l in lines_to_use))
    print '    skipping %d smaller than %d' % (n_skipped, min_tree_metric_cluster_size)
    for line in lines_to_use:
        if debug:
            print '  %s sequence cluster' % utils.color('green', str(len(line['unique_ids'])))
        if 'tree-info' in line:
            n_already_there += 1
            continue
        treefo = get_tree_for_line(line, treefname=treefname, cpath=cpath, annotations=annotations, use_true_clusters=use_true_clusters, debug=debug)
        tree_origin_counts[treefo['origin']]['count'] += 1
        line['tree-info'] = {}  # NOTE <treefo> has a dendro tree, but what we put in the <line> (at least for now) is a newick string
        line['tree-info']['lb'] = calculate_lb_values(treefo['tree'], lb_tau, default_lbr_tau_factor * lb_tau, annotation=line, add_dummy_root=add_dummy_root, extra_str='inf tree', debug=debug)

    print '    tree origins: %s' % ',  '.join(('%d %s' % (nfo['count'], nfo['label'])) for n, nfo in tree_origin_counts.items() if nfo['count'] > 0)
    if n_already_there > 0:
        print '      skipped %d / %d that already had tree info' % (n_already_there, len(lines_to_use))

    # calculate lb values for true lines/trees
    if reco_info is not None:  # note that if <base_plotdir> *isn't* set, we don't actually do anything with the true lb values
        for true_line in true_lines_to_use:
            true_dtree = get_dendro_tree(treestr=true_line['tree'])
            true_lb_info = calculate_lb_values(true_dtree, lb_tau, default_lbr_tau_factor * lb_tau, annotation=true_line, add_dummy_root=add_dummy_root, extra_str='true tree')
            true_line['tree-info'] = {'lb' : true_lb_info}

    if base_plotdir is not None:
        plot_tree_metrics(base_plotdir, lines_to_use, true_lines_to_use, lb_tau, debug=debug)

# ----------------------------------------------------------------------------------------
def run_laplacian_spectra(treestr, workdir=None, plotdir=None, plotname=None, title=None, debug=False):
    #  - https://www.ncbi.nlm.nih.gov/pubmed/26658901/
    #  - instructions here: https://besjournals.onlinelibrary.wiley.com/doi/full/10.1111/2041-210X.12526
    # I think this is what ended up working (thought probably not in docker):
    #  apt-get install libgmp-dev libmpfr-dev
    #  > install.packages("RPANDA",dependencies=TRUE)
    #  ok but then I needed to modify the code, so downloaded the source from cran, and swapped out for the spectR.R that eric sent, then installed with:
    # R CMD INSTALL -l packages/RPANDA/lib packages/RPANDA/  # NOTE needs to happen whenever you modify the R source
    # condensation of docs from the above paper:
    #  - > res<-spectR(Phyllostomidae)  # compute eigenvalues (and some metrics describing the distribution, e.g. skewness, kurtosis, eigengap)
    #  - > plot_spectR(res)  # make plots for eigenvalue spectrum
    #  - if eigengap (largest gap between sorted eigenvalues) is e.g. between 3 and 4, then the tree can be separated into three regions, and you use the BIC stuff to find those regions
    #    - > res<-BICompare(Phyllostomidae,3)
    #    - > plot_BICompare(Phyllostomidae,res)
    #  - > res<-JSDtree(Phyllostomidae_genera)  # pairwise jensen-shannon distances between the 25 phylogenies
    #  - > JSDtree_cluster(res)  # plots heatmap and hierarchical cluster

    if debug:
        print utils.pad_lines(get_ascii_tree(treestr=treestr))
        print treestr

    if workdir is None:
        workdir = utils.choose_random_subdir('/tmp/%s' % os.getenv('USER'))
    eigenfname = '%s/eigenvalues.txt' % workdir
    os.makedirs(workdir)

    cmdlines = [
        'library(ape, quiet=TRUE)',
        # 'library(RPANDA, quiet=TRUE)',  # old way, before I had to modify the source code because the CRAN version removes all eigenvalues <1 (for method="standard" -- with method="normal" it's <0, which is probably better, but it also seems to smoosh all the eigenvalues to be almost exactly 1)
        'library("RPANDA", lib.loc="%s/packages/RPANDA/lib", quiet=TRUE)' % os.path.dirname(os.path.realpath(__file__)).replace('/python', ''),
        'tree <- read.tree(text = "%s")' % treestr,
        # 'print(tree)',
        'specvals <- spectR(tree, method=c("standard"))',  # compute eigenvalues (and some metrics describing the distribution, e.g. skewness, kurtosis, eigengap)
        # 'print(specvals)',
        'capture.output(specvals$eigenvalues, file="%s")' % eigenfname,
    ]

    # This is vegan 2.5-3  # dammit I want to filter this, but if I do it will eat the out/err when it crashes
    utils.run_r(cmdlines, workdir)

    eigenvalues = []
    with open(eigenfname) as efile:
        for line in efile:
            for tstr in line.split():
                if '[' in tstr:
                    if int(tstr.strip('[]')) != len(eigenvalues) + 1:
                        raise Exception('couldn\'t process line:\n%s' % line)
                else:
                    eigenvalues.append(float(tstr))

    os.remove(eigenfname)
    os.rmdir(workdir)

    if plotdir is not None:
        import plotting
        plotting.plot_laplacian_spectra(plotdir, plotname, eigenvalues, title)
