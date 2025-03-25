#! /usr/bin/env python

##############################################################################
##  DendroPy Phylogenetic Computing Library.
##
##  Copyright 2010-2014 Jeet Sukumaran and Mark T. Holder.
##  All rights reserved.
##
##  See "LICENSE.txt" for terms and conditions of usage.
##
##  If you use this work or any portion thereof in published work,
##  please cite it as:
##
##     Sukumaran, J. and M. T. Holder. 2010. DendroPy: a Python library
##     for phylogenetic computing. Bioinformatics 26: 1569-1571.
##
##############################################################################

"""
Writing data in NEXUS format to an output stream.
"""

import re
try:
    from StringIO import StringIO # Python 2 legacy support: StringIO in this module is the one needed (not io)
except ImportError:
    from io import StringIO # Python 3
import warnings
import collections
from dendropy.dataio import ioservice
from dendropy.dataio import newick
from dendropy.dataio import nexusprocessing
from dendropy.dataio import newickwriter

###############################################################################
## NexusWriter

class NexusWriter(ioservice.DataWriter):
    """
    Formatter for NEXUS data.
    """

    def __init__(self, **kwargs):
        """

        Keyword Arguments
        -----------------
        simple : boolean, default: `False`
            If `True`, write in simple NEXUS format, i.e. in a single "DATA"
            block, instead of separate "TAXA" and "CHARACTER" blocks.
        suppress_taxa_block: boolean, default: `False`
            If `True`, do not write a "TAXA" block.
        suppress_unreferenced_taxon_namespaces: boolean, default: `False`
            If `True`, then when writing :class:`DataSet` objects, any :class:`TaxonNamespace`
            object in the DataSet's `taxon_namespaces` collection will *not* be written
            as a "TAXA" block
        file_comments: iterable [`str`]
            List of lines of text to be added as comments to the file.
        preamble_blocks: iterable [`str`]
            List of strings to be written before data (e.g., PAUP blocks
            suppressing warnings etc.).
        supplemental_blocks: iterable [`str`]
            List of strings to be written after data (e.g., PAUP blocks,
            MrBayes blocks etc.).
        suppress_leaf_taxon_labels : boolean, default: `False`
            If `True`, then taxon labels will not be rendered for leaves.
            Default is `False`: render leaf taxon labels. See notes below for
            details.
        suppress_leaf_node_labels : boolean, default: `True`
            If `False`, then node labels (if available) will be printed for
            leaves. Defaults to `True`: do not render leaf node labels. See
            notes below for details.
        suppress_internal_taxon_labels : boolean, default: `False`
            If `True`, then taxon labels will not be printed for internal
            nodes. Default is `False`: print taxon labels for internal nodes.
            See notes below for details.
        suppress_internal_node_labels : boolean, default: `False`
            If `True`, then node labels will not be printed for internal nodes.
            Default is `False`: print node labels for internal nodes. See notes
            below for details.
        suppress_rooting : boolean, default: `False`
            If `True`, will not write rooting token ('[&R]' or '[&U]').
            Default is `False`: rooting token will be written.
        suppress_edge_lengths : boolean, default: `False`
            If `True`, will not write edge lengths. Default is `False`: edge
            lengths will be written.
        unquoted_underscores : boolean, default: `False`
            If `True`, labels with underscores will not be quoted, which will
            mean that they will be interpreted as spaces if read again ("soft"
            underscores).  If `False`, then labels with underscores
            will be quoted, resulting in "hard" underscores.  Default is
            `False`.
        preserve_spaces : boolean, default: `False`
            If `True`, spaces will not be replaced with underscores in labels
            (which means any labels containing spaces will have to be quoted).
            Default is `False`: spaces will be converted to underscores.
            False.
        store_tree_weights : boolean, default: `False`
            If `True`, tree weights are written. Default is `False`: tree
            weights will not be written.
        suppress_annotations : boolean, default: `False`
            If `True`, metadata annotations will be ignored.
            Defaults to `False`: metadata annotations will be written.
        annotations_as_nhx : boolean, default: `False`
            If `True`, and if `suppress_annotations` is `False`, will write
            annotations as NHX statements. Default is `False`: annotations
            will not be written as NHX statements.
        suppress_item_comments : boolean, default: `False`
            If `True`: comments will be ignored. Default is `False`: any
            additional comments associated with trees, nodes, edges, etc. will
            be written.
        node_label_element_separator : string, default: ' '
            If both `suppress_leaf_taxon_labels` and
            `suppress_leaf_node_labels` are `False`, then this will be the
            string used to join them. Defaults to ' ' (space).
        node_label_compose_func : function object or `None`, default: `None`
            If not `None`, should be a function that takes a :class:`Node`
            object as an argument and returns the string to be used to
            represent the node in the tree statement. The return value from
            this function is used unconditionally to print a node
            representation in a tree statement, by-passing the default
            labelling function, ignoring `suppress_leaf_taxon_labels`,
            `suppress_leaf_node_labels=True`, `suppress_internal_taxon_labels`,
            `suppress_internal_node_labels`, etc. Defaults to `None`.
        edge_label_compose_func : function object or `None`, default: `None`
            If not `None`, should be a function that takes an Edge object as
            an argument, and returns the string to be used to represent the
            edge length in the tree statement.
        """
        # base
        ioservice.DataWriter.__init__(self)

        # Following are NEXUS specific (i.e., not used by NEWICK formatters),
        # and need to be removed so as not to cause problems with our keyword
        # validation scheme
        self.simple = kwargs.pop("simple", False)
        self.suppress_taxa_blocks = kwargs.pop("suppress_taxa_block", None)
        self.suppress_block_titles = kwargs.pop("suppress_block_titles", None)
        self.file_comments = kwargs.pop("file_comments", [])
        self.preamble_blocks = kwargs.pop("preamble_blocks", [])
        self.supplemental_blocks = kwargs.pop("supplemental_blocks", [])
        self.allow_multiline_comments = kwargs.pop("allow_multiline_comments", True)
        self.suppress_unreferenced_taxon_namespaces = kwargs.pop("suppress_unreferenced_taxon_namespaces", False)
        self.continuous_character_state_value_format_func = kwargs.pop("continuous_character_state_value_format_func", self._format_continuous_character_value)
        self.discrete_character_state_value_format_func = kwargs.pop("discrete_character_state_value_format_func", self._format_discrete_character_value)

        # The following are used by NewickWriter in addition to NexusWriter, so
        # they are extracted/set here and then forwarded on ...
        self.unquoted_underscores = kwargs.get('unquoted_underscores', False)
        self.preserve_spaces = kwargs.get("preserve_spaces", False)
        self.annotations_as_nhx = kwargs.get("annotations_as_nhx", False)

        # As above, but the NEXUS format default is different from the NEWICK
        # default, so this rather convoluted approach
        self.suppress_annotations = kwargs.pop("suppress_annotations", False)
        kwargs["suppress_annotations"] = self.suppress_annotations
        self.suppress_item_comments = kwargs.pop("suppress_item_comments", False)
        kwargs["suppress_item_comments"] = self.suppress_item_comments

        # The newick writer to which tree-writing will be delegated
        self._newick_writer = newickwriter.NewickWriter(**kwargs)

        # Book-keeping
        self.taxon_namespaces_to_write = []
        self._block_title_map = {}
        self._title_block_map = {}

    def _write(self,
            stream,
            taxon_namespaces=None,
            tree_lists=None,
            char_matrices=None,
            global_annotations_target=None):

        # Header
        stream.write('#NEXUS\n\n')

        # File/Document-level annotations and comments
        if self.file_comments:
            self._write_comments(stream, self.file_comments)
        if global_annotations_target is not None:
            self._write_item_annotations(stream, global_annotations_target)
            self._write_item_comments(stream, global_annotations_target)

        # Other blocks
        if self.preamble_blocks:
            for block in self.preamble_blocks:
                stream.write(block)
                stream.write("\n")
            stream.write("\n")

        # Taxon namespace discovery
        candidate_taxon_namespaces = collections.OrderedDict()
        if self.attached_taxon_namespace is not None:
            # should this be False?
            candidate_taxon_namespaces[self.attached_taxon_namespace] = True
        elif taxon_namespaces is not None:
            if self.suppress_unreferenced_taxon_namespaces:
                # preload to preserve order
                for tns in taxon_namespaces:
                    candidate_taxon_namespaces[tns] = False
            else:
                for tns in taxon_namespaces:
                    candidate_taxon_namespaces[tns] = True
        for data_collection in (tree_lists, char_matrices):
            if data_collection is not None:
                for i in data_collection:
                    if self.attached_taxon_namespace is None or i.taxon_namespace is self.attached_taxon_namespace:
                        candidate_taxon_namespaces[i.taxon_namespace] = True
        self.taxon_namespaces_to_write = [tns for tns in candidate_taxon_namespaces if candidate_taxon_namespaces[tns]]

        #  Write out taxon namespaces
        if not self.simple and not self.suppress_taxa_blocks:
            if self.suppress_block_titles and len(taxon_namespace_to_write) > 1:
                warnings.warn("Multiple taxon namespaces will be written, but block titles are suppressed: data file may not be interpretable")
            for tns in self.taxon_namespaces_to_write:
                self._write_taxa_block(stream, tns)

        # Write out character matrices
        if char_matrices is not None:
            for char_matrix in char_matrices:
                if (self.attached_taxon_namespace is None
                        or char_matrix.taxon_namespace is self.attached_taxon_namespace):
                    self._write_char_block(stream=stream, char_matrix=char_matrix)

        # Write out tree lists
        if tree_lists is not None:
            for tree_list in tree_lists:
                if (self.attached_taxon_namespace is None
                        or tree_list.taxon_namespace is self.attached_taxon_namespace):
                    self._write_trees_block(stream=stream,
                            tree_list=tree_list)

        # Write out remaining
        if self.supplemental_blocks:
            for block in self.supplemental_blocks:
                stream.write(block)
                stream.write("\n")

    def _write_taxa_block(self, stream, taxon_namespace):
        stream.write("BEGIN TAXA;\n")
        self._write_block_title(stream, taxon_namespace)
        self._write_item_annotations(stream, taxon_namespace)
        self._write_item_comments(stream, taxon_namespace)
        stream.write("    DIMENSIONS NTAX={};\n".format(len(taxon_namespace)))
        stream.write("    TAXLABELS\n")
        for taxon in taxon_namespace:
            stream.write("        {}\n".format(
                nexusprocessing.escape_nexus_token(taxon.label, preserve_spaces=self.preserve_spaces, quote_underscores=not self.unquoted_underscores),
                ))
            self._write_item_annotations(stream, taxon)
            self._write_item_comments(stream, taxon)
        stream.write("  ;\n")
        stream.write("END;\n\n")

    def _write_trees_block(self, stream, tree_list):
        stream.write("BEGIN TREES;\n")
        self._write_block_title(stream, tree_list)
        self._write_item_annotations(stream, tree_list)
        self._write_item_comments(stream, tree_list)
        self._write_link_to_taxa_block(stream, tree_list.taxon_namespace)
        for tree_idx, tree in enumerate(tree_list):
            if tree.label:
                tree_name = tree.label
            else:
                tree_name = str(tree_idx+1)
            tree_name = nexusprocessing.escape_nexus_token(
                    tree_name,
                    preserve_spaces=self.preserve_spaces,
                    quote_underscores=not self.unquoted_underscores)
            stream.write("    TREE {} = ".format(tree_name))
            self._newick_writer._write_tree(stream, tree)
            stream.write("\n")
        stream.write("END;\n\n")

    def _write_char_block(self, stream, char_matrix):
        taxon_label_map = collections.OrderedDict()
        for taxon in char_matrix:
            taxon_label_map[taxon] = nexusprocessing.escape_nexus_token(taxon.label, preserve_spaces=self.preserve_spaces, quote_underscores=not self.unquoted_underscores)
        nchar = max([len(seq) for seq in char_matrix.values()])
        if self.simple:
            stream.write("BEGIN DATA;\n")
            # note that this will only list the number of taxa for
            # which sequences are available
            ntaxstr = "NTAX={}".format(len(taxon_label_map))
        else:
            stream.write("BEGIN CHARACTERS;\n")
            ntaxstr = ""
        self._write_block_title(stream, char_matrix)
        self._write_item_annotations(stream, char_matrix)
        self._write_item_comments(stream, char_matrix)
        self._write_link_to_taxa_block(stream, char_matrix.taxon_namespace)
        stream.write("    DIMENSIONS{} NCHAR={};\n".format(ntaxstr, nchar))
        stream.write("    FORMAT {};\n".format(self._compose_format_terms(char_matrix)))
        stream.write("    MATRIX\n")
        if char_matrix.data_type_name == "continuous":
            state_value_writer = lambda x : stream.write("{} ".format(self.continuous_character_state_value_format_func(x)))
        else:
            state_value_writer = lambda x : stream.write("{}".format(self.discrete_character_state_value_format_func(x)))
        max_label_len = max(len(v) for v in taxon_label_map.values())
        for taxon in char_matrix:
            stream.write("        {taxon_label:{field_len}}    ".format(taxon_label=taxon_label_map[taxon],
                field_len=max_label_len))
            for state in char_matrix[taxon]:
                state_value_writer(state)
            stream.write("\n")
        stream.write("    ;\n")
        stream.write("END;\n\n\n")
        self._write_character_subsets(stream, char_matrix)

    def _compose_format_terms(self, char_matrix):
        format = []
        if char_matrix.data_type_name == "dna":
            format.append("DATATYPE=DNA")
            format.append("GAP=- MISSING=? MATCHCHAR=.")
        elif char_matrix.data_type_name == "rna":
            format.append("DATATYPE=RNA")
            format.append("GAP=- MISSING=? MATCHCHAR=.")
        elif char_matrix.data_type_name == "nucleotide":
            format.append("DATATYPE=NUCLEOTIDE")
            format.append("GAP=- MISSING=? MATCHCHAR=.")
        elif char_matrix.data_type_name == "protein":
            format.append("DATATYPE=PROTEIN")
            format.append("GAP=- MISSING=? MATCHCHAR=.")
        elif char_matrix.data_type_name == "continuous":
            format.append("DATATYPE=CONTINUOUS ITEMS=(STATES)")
        else:
            format.append("DATATYPE=STANDARD")
            fundamental_symbols = set()
            for state_alphabet in char_matrix.state_alphabets:
                for s in state_alphabet.fundamental_state_iter():
                    if s.symbol is not None:
                        fundamental_symbols.add(s.symbol)
                    else:
                        raise Exception("Could not match character state to symbol: '%s'." % s)
            format.append('SYMBOLS="%s"' % "".join(fundamental_symbols))
            equates = set()
            for state_alphabet in char_matrix.state_alphabets:
                for a in state_alphabet.ambiguous_state_iter():
                    if a.symbol == "?":
                        format.append("MISSING=?")
                    elif a.symbol == "-":
                        format.append("GAP=-")
                    else:
                        if a.symbol is not None:
                            equates.add("%s={%s}" % (a.symbol, "".join(a.fundamental_symbols)))
            for state_alphabet in char_matrix.state_alphabets:
                for p in state_alphabet.polymorphic_state_iter():
                    if p.symbol is not None:
                        equates.add("%s=(%s)" % (p.symbol, "".join(p.fundamental_symbols)))
            if equates:
                format.append('EQUATE="%s"' % equates)
        return ' '.join(format)

    def _write_comments(self, stream, comments):
        if self.allow_multiline_comments:
            if isinstance(comments, str):
                stream.write("[{}]\n".format(comments))
            else:
                comments = "\n".join([str(c) for c in comments])
                stream.write("[\n{}\n]\n".format(comments))
        else:
            if isinstance(comments, str):
                comments = comments.replace("\r\n", "\n").replace("\n\r","\n").replace("\r","\n")
                # comments = re.split(r'[\r\n]+', comments)
                comments = [c for c in re.split(r'[\r\n]+', comments) if c]
            for c in comments:
                stream.write("[{}]\n".format(c))

    def _write_item_comments(self, stream, item):
        if not self.suppress_item_comments and item.comments:
            self._write_comments(stream, item.comments)

    def _write_item_annotations(self, stream, item):
        if not self.suppress_annotations and item.annotations:
            a = nexusprocessing.format_item_annotations_as_comments(item, nhx=self.annotations_as_nhx)
            stream.write("{}\n".format(a))

    def _write_block_title(self, stream, block):
        if not self._link_blocks():
            return
        title = self._get_block_title(block)
        if not title:
            return
        stream.write("    TITLE {};\n".format(title))

    def _write_link_to_taxa_block(self, stream, taxon_namespace):
        if not self._link_blocks():
            return
        link_title = self._get_block_title(taxon_namespace)
        if not link_title:
            return
        stream.write("    LINK TAXA = {};\n".format(link_title))

    def _get_block_title(self, block):
        # if self.is_write_block_titles is False then no block titles;
        # if only one taxon set, or attached taxon set mode, unless self.is_write_block_titles
        # is explicitly True, then again, we do not write block titles
        if not self._link_blocks():
            return None
        if block in self._block_title_map:
            return self._block_title_map[block]
        if not block.label:
            title = id(block)
        else:
            title = block.label
        idx = 1
        original_title = title
        title = nexusprocessing.escape_nexus_token(
                original_title,
                preserve_spaces=self.preserve_spaces,
                quote_underscores=not self.unquoted_underscores)
        while title in self._title_block_map:
            raw_title = "{}.{}".format(original_title, idx)
            title = nexusprocessing.escape_nexus_token(
                    raw_title,
                    preserve_spaces=self.preserve_spaces,
                    quote_underscores=not self.unquoted_underscores)
            idx += 1
        self._title_block_map[title] = block
        self._block_title_map[block] = title
        return title

    def _link_blocks(self):
        """
        If only one taxon set in dataset, or in attached taxon set mode, then
        unless the 'block_titles' directive has been explicitly set to True
        by the user, block titles and links will not be written.
        """
        if self.suppress_block_titles is None:
            if len(self.taxon_namespaces_to_write) > 1:
                return True
            else:
                return False
        else:
            return self.suppress_block_titles

    def _format_continuous_character_value(self, v):
        return "{}".format(v)

    def _format_discrete_character_value(self, v):
        return str(v)

    def _write_character_subsets(self, stream, char_matrix):
        if not hasattr(char_matrix, "character_subsets") or not char_matrix.character_subsets:
            return
        stream.write("BEGIN SETS;\n")
        for label, char_set in char_matrix.character_subsets.items():
            label = textutils.escape_nexus_token(char_set.label,
                    preserve_spaces=self.preserve_spaces,
                    quote_underscores=not self.unquoted_underscores)
            ranges = textutils.group_ranges(char_set.character_indices)
            pos = " ".join("-".join(str(c+1) for c in r) for r in ranges)
            stream.write("    charset {} = {};\n".format((label, pos)))
        stream.write("END;\n\n\n")
