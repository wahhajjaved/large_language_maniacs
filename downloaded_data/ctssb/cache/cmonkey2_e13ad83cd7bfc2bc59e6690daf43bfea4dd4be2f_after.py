"""stringdb.py - cMonkey STRING database interface module

This file is part of cMonkey Python. Please see README and LICENSE for
more information and licensing details.
"""
import logging
import re
import math
import util
import network
import patches


STRING_FILE2 = 'string_links_64091.tab'
PROTEIN_PREFIX = re.compile('^string:\d+[.]')


def normalize_edges_to_max_score(edges, max_score):
    """normalize scores to 1000, for combined scores"""
    def normalize(edge_score):
        score = edge_score / max_score * 1000.0
        return 1000 * math.exp(score / 1000.0) / math.exp(1.0)

    return [(edge[0], edge[1], normalize(edge[2])) for edge in edges]


def get_network_factory(organism_code, filename, weight, sep='\t',
                        normalized=False):
    """STRING network factory from preprocessed edge file
    (protein1, protein2, combined_score), scores are already
    normalized to 1000.
    This is the standard factory method used for Microbes.
    """
    def can_add_edge(node1, node2, thesaurus, cano_genes):
        """check whether we can add the edge"""
        if cano_genes is not None:
            return (node1 in thesaurus and node2 in thesaurus
                    and thesaurus[node1] in cano_genes and thesaurus[node2] in cano_genes)
        else:
            return node1 in thesaurus and node2 in thesaurus

    def read_edges2(filename, organism, ratios):
        """just read a preprocessed file, much faster to debug"""
        logging.info("stringdb.read_edges2()")
        dfile = util.read_dfile(filename, sep)
        logging.info("Finished loading %s", filename)
        result = []
        max_score = 0.0
        thesaurus = organism.thesaurus()
        if ratios:
            gene_lut = {}
            for row_name in ratios.row_names:
                if row_name in thesaurus:
                    gene_lut[thesaurus[row_name]] = row_name
                gene_lut[row_name] = row_name #A node should always map to itself
            cano_genes = gene_lut.keys()
        else:
            gene_lut = None
            cano_genes = None
        
        num_ignored = 0
        keep_bool = {} #Big Speedup: Use to search thesaurus and cano_genes only once for each gene
        idx = 1 #Used to display progress
        for line in dfile.lines:
            #This can be slow, display progress every 5%
            frac = idx % (len(dfile.lines)/20)
            idx += 1
            if frac == 0:
                logging.info("Processing network %d%%", round(100*float(idx)/len(dfile.lines)))
            
            node1 = patches.patch_string_gene(organism_code, line[0])
            node2 = patches.patch_string_gene(organism_code, line[1])
            for node in (node1, node2):
                if not node in keep_bool:
                    if cano_genes is not None:
                        keep_bool[node] = node in thesaurus and thesaurus[node] in cano_genes
                    else:
                        keep_bool[node] = node in thesaurus
                    
                    #Add this node to the lut if it is not already there.
                    if (not gene_lut is None) and (not node in gene_lut):
                        gene_lut[node] = node
                        if node in thesaurus:
                            gene_lut[thesaurus[node]] = node
                        
            score = float(line[2])
            max_score = max(score, max_score)

            #if can_add_edge(node1, node2, thesaurus, cano_genes):
            if keep_bool[node1] and keep_bool[node2]:
                #2/18/15 SD.  Translate nodes into names in ratio rows using gene_lut
                #   This will let the ratios matrix define how the genes are named
                if gene_lut is None:
                    new_edge = (intern(node1), intern(node2), score)
                else:
                    new_edge = (intern(gene_lut[node1]), intern(gene_lut[node2]), score)
                #logging.info("Adding edge %s - %s - %f", new_edge[0], new_edge[1], new_edge[2])
                result.append(new_edge)
            else:
                num_ignored += 1

        if not normalized:
            result = normalize_edges_to_max_score(result, max_score)

        logging.info("stringdb.read_edges2(), %d edges read, %d edges ignored",
                     len(result), num_ignored)
        
        #Write file to be used later?
        #outfile = util.make_delimited_file_from_lines(lines, sep, has_header, comment, quote)
        
        return result

    def make_network(organism, ratios=None, check_size=False):
        """make network"""
        return network.Network.create("STRING",
                                      read_edges2(filename, organism, ratios),
                                      weight,
                                      organism, ratios)

    return make_network


__all__ = ['get_network_factory']
