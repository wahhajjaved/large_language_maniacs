#!/usr/bin/env python
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from random import randint 
from probin.model.composition import multinomial as mn
from numpy.random import multinomial as np_mn


def sample_contigs(genome, n, min_length, max_length):
    contigs = []
    identifier = ">" + genome.id
    for i in range(n):
        l = randint(min_length, max_length)
        start = randint(0, (len(genome)-l))
        contig = Seq(genome.seq[start:start+l])
        contigs.append(identifier + " contig_number " + str(i) + "\n" + str(genome.seq[start:start+l]))
    return contigs

def sample_contig(genome, min_length, max_length):
    l = randint(min_length, max_length)
    start = randint(0, (len(genome)-l))
    contig = SeqRecord(genome.seq[start:start+l])
    rest = SeqRecord(genome.seq[0:start] + genome.seq[start+l:-1])
    return contig, rest

def score_contig(signature, gen_par, group_pars, rest_pars):
    gen_score = mn.log_probability(signature, gen_par)
    group_scores = []
    rest_scores = []
    for par in group_pars:
        group_scores.append(mn.log_probability(signature, par))
    for group in rest_pars:
        outside_group = []
        for par in group:
            outside_grup.append(mn.log_probability(signature,par))
        rest_scores.append(outside_group)
    return gen_score, group_scores, rest_scores

# This method performes the comparison for a group
def pairwise(group, rest_pars, prio, no_contigs, mode, contig_min_length, contig_max_length, kmer_length):
    group_name = group.name
    if prio == "groups":
        n = len(group)
        no_contigs_per_genome_list = list(np_mn(no_contigs, [1/float(n)]*n, size=1))
    elif prio == "genomes":
        n = len(group)
        no_contigs_per_genome_list = [round(no_contigs/float(n))]*n
        for genome_index in range(len(group)):
            genome = group.genomes[genome_index]
            group_genomes = all_but_index(group.genomes,genome_index)
            group_pars = [ge.par for ge in group_genomes]
            for i in range(int(no_contigs_per_genome_list[int(genome_index)])):
                if mode == "refit":
                    c, rest_g_seq = sample_contig(genome.seq, contig_min_length, contig_max_length)
                    g_par = mn.fit_parameters(kmer_length, [rest_g_seq])
                    c_sign =  mn.calculate_signatures(kmer_length, [c])
#                    print c_sign, g_par, group_pars, rest_pars
                    gen_score, group_scores, rest_scores = score_contig(c_sign[0], g_par[0], group_pars, rest_pars)
                    print gen_score, group_scores, rest_scores
                else:
                    pass


def all_but_index(l,i):
    return l[0:i] + l[i+1:]

class GenomeGroup:
    """A wrapper for the genome groups used in pairwise testing"""
    def __init__(self, name):
        self.genomes = []
        self.name = name
    def add_genome(self, genome):
        self.genomes.append(genome)
    def parameters(self):
        return [genome.par for genome in self.genomes]
    def __len__(self):
        return len(self.genomes)

class Genome:
    def __init__(self, name):
        self.name = name
        self.seq = ""
        self.par = []
    def add_parameter(para):
        self.par = para
