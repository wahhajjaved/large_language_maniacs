#!/usr/bin/env python
"""
Usage: TF_functions.py schema organism inputfile

Example:
	TF_functions.py hs_fim_138 hs /tmp/list1.txt.gene_id  >/tmp/list1.out

Description:
	some functions to do TF stat of a cluster
"""

import psycopg, re, sys, getopt, os, csv
sys.path += [os.path.join(os.path.expanduser('~/script/annot/bin'))]
from codense.common import db_connect, org2tax_id, org_short2long, get_gene_id2gene_no
from rpy import r
from sets import Set
from heapq import heappush, heappop, heapreplace

def get_gene_id2tf_set(curs, table_name, organism):
	"""
	09-08-05
	"""
	sys.stderr.write("Getting gene_id2tf_set...")
	gene_id2tf_set = {}
	curs.execute("select gene_id, tf from graph.%s where organism='%s'"%(table_name, organism))
	rows = curs.fetchall()
	for row in rows:
		gene_id = row[0]
		tf = row[1]
		if gene_id not in gene_id2tf_set:
			gene_id2tf_set[gene_id] = Set()
		gene_id2tf_set[gene_id].add(tf)
	sys.stderr.write("Done\n")
	return gene_id2tf_set

	
def map2gene_no_reverse_map(gene_id2tf_set, gene_id2no):
	"""
	09-08-05
	09-14-05
		add tf2gene_no_set
	"""
	sys.stderr.write("Mapping gene_id2tf_set to gene_no2tf_set...")
	gene_no2tf_set = {}
	tf2no_of_genes = {}
	tf2gene_no_set = {}
	for gene_id, tf_set in gene_id2tf_set.iteritems():
		if gene_id in gene_id2no:
			gene_no = gene_id2no[gene_id]
			gene_no2tf_set[gene_no] = tf_set
			for tf in tf_set:
				if tf not in tf2no_of_genes:
					tf2no_of_genes[tf] = 0
					tf2gene_no_set[tf] = Set()
				tf2no_of_genes[tf]+=1
				tf2gene_no_set[tf].add(gene_no)
	sys.stderr.write("Done\n")
	return gene_no2tf_set, tf2no_of_genes, tf2gene_no_set

def tf_stat(gene_no2tf_set, gene_no_list, tf2no_of_genes, no_of_total_genes):
	"""
	09-08-05
	"""
	tf2stat = {}
	no_tf_gene_no_list = []
	for gene_no in gene_no_list:
		tf_set = gene_no2tf_set.get(gene_no)
		if tf_set:
			for tf in  tf_set:
				if tf not in tf2stat:
					tf2stat[tf] = []
				tf2stat[tf].append(gene_no)
		else:
			no_tf_gene_no_list.append(gene_no)
	tf_stat_list = []
	for tf in tf2stat:
		row = [tf2stat[tf], tf]
		x = len(tf2stat[tf])
		m = tf2no_of_genes[tf]
		n = no_of_total_genes -m
		k = len(gene_no_list)
		p_value = r.phyper(x-1,m,n,k,lower_tail = r.FALSE)
		row = [p_value, x, tf2stat[tf], tf]
		tf_stat_list.append(row)
	tf_stat_list.sort()
	return tf_stat_list, no_tf_gene_no_list

def get_gene_no_list(inputfile):
	"""
	09-09-05
		one gene_id per line
	"""
	inf = open(inputfile, 'r')
	reader = csv.reader(inf)
	gene_no_list = []
	for row in reader:
		gene_no_list.append(int(row[0]))
	del reader, inf
	return gene_no_list

def tf_combo_stat(tf2gene_no_set_global, tf_stat_list, no_of_total_genes, cluster_size):
	"""
	09-14-05
		first,only tf with >=1/3 associated genes are selected to do combo analysis
		second, for each pair, get its genome-wide prob and joint prob
		3rd, calculate the likelihood seeing #pairs in the cluster and whole genome
		4th, likelihood ratio
	09-17-05
		log the likeli1 and likeli2
		l_ratio = likeli1 - likeli2 (previous is /)
	"""
	tf_gene_no_set_list = []
	for row in tf_stat_list:
		if row[1] >=(cluster_size/3.0):
			tf_gene_no_set_list.append([row[3],Set(row[2])])
	tf_combo_stat_list = []
	for i in range(len(tf_gene_no_set_list)):
		for j in range(i+1, len(tf_gene_no_set_list)):
			tf1, tf1_gene_no_set = tf_gene_no_set_list[i]
			tf2, tf2_gene_no_set = tf_gene_no_set_list[j]
			combo_size_local = len(tf1_gene_no_set&tf2_gene_no_set)
			tf1_gene_no_set_global = tf2gene_no_set_global[tf1]
			tf2_gene_no_set_global = tf2gene_no_set_global[tf2]
			prob_tf1 = len(tf1_gene_no_set_global)/float(no_of_total_genes)
			prob_tf2 = len(tf2_gene_no_set_global)/float(no_of_total_genes)
			prob_combo = prob_tf1*prob_tf2
			combo_size_global = len(tf1_gene_no_set_global&tf2_gene_no_set_global)
			likeli1 = r.dbinom(combo_size_local, cluster_size, prob_combo,log=r.TRUE)
			likeli2 = r.dbinom(combo_size_global, no_of_total_genes, prob_combo, log=r.TRUE)
			if likeli2==0:
				l_ratio = 1
			else:
				l_ratio = likeli1-likeli2
			tf_combo_stat_list.append([l_ratio, combo_size_local, cluster_size, combo_size_global, no_of_total_genes, \
				prob_tf1, prob_tf2, prob_combo, likeli1, likeli2, list(tf1_gene_no_set&tf2_gene_no_set), (tf1,tf2)])
	return tf_combo_stat_list
	
def hq_add(hq_list, row, top_number):
	hq_len = len(hq_list)
	if hq_len==top_number:
		lowest_score = hq_list[0][0]
		if lowest_score < row[0]:	#11-01-05 important bug. >= is wrong. < is correct.
			heapreplace(hq_list, row)
	elif hq_len<top_number:
		heappush(hq_list, row)
	else:
		sys.stderr.write("Heap Queue's size exceeds the limit. Something impossible. Exit\n")
		sys.stderr.write("The hq is %s.\n"%repr(hq_list))
		sys.exit(2)

def cluster_bs_analysis(gene_no_list, gene_no2bs_no_set, bs_no2gene_no_set, ratio_cutoff=1.0/3, top_number=5):
	"""
	09-19-05
		three kinds of analysis
		1. single hypergeometric
		2. combo hypergeometric
		3. combo binomial log likelihood ratio
		
		all just retain the top 5
	"""
	#construct local dictionary and records the genes with no bs_no
	local_bs_no2gene_no_set = {}
	no_bs_gene_no_list = []
	for gene_no in gene_no_list:
		bs_no_set = gene_no2bs_no_set.get(gene_no)
		if bs_no_set:
			for bs_no in bs_no_set:
				if bs_no not in local_bs_no2gene_no_set:
					local_bs_no2gene_no_set[bs_no] = Set()
				local_bs_no2gene_no_set[bs_no].add(gene_no)
		else:
			no_bs_gene_no_list.append(gene_no)
	
	cluster_size = len(gene_no_list)
	no_of_total_genes = len(gene_no2bs_no_set)
	
	#transform the local dictionary to a list and filter by ratio_cutoff
	local_bs_no_and_gene_no_set = []
	for bs_no, gene_no_set in local_bs_no2gene_no_set.iteritems():
		if len(gene_no_set)>=(cluster_size*float(ratio_cutoff)):
			local_bs_no_and_gene_no_set.append([bs_no, gene_no_set])
	
	local_bs_no_and_gene_no_set.sort()	#sort by bs_no
	hq_list1 = []	#single hypergeometric
	hq_list2 = []	#combo hypergeometric
	hq_list3 = []	#combo binomial log ratio
	unknown_ratio = float(len(no_bs_gene_no_list))/cluster_size
	
	for i in range(len(local_bs_no_and_gene_no_set)):
		bs_no1, gene_no_set1 = local_bs_no_and_gene_no_set[i]
		x = len(gene_no_set1)
		m = len(bs_no2gene_no_set[bs_no1])
		n = no_of_total_genes - m
		k = cluster_size
		p_value = r.phyper(x-1,m,n,k,lower_tail = r.FALSE)
		score = -p_value	#Watch minus, heapq is a min-heap
		bs_no_list = [bs_no1]
		global_ratio = float(m)/no_of_total_genes
		local_ratio = float(x)/cluster_size
		expected_ratio = global_ratio
		row = [score, 1, bs_no_list, list(gene_no_set1), global_ratio, local_ratio, expected_ratio, unknown_ratio]
		hq_add(hq_list1, row, top_number)
		for j in range(i+1, len(local_bs_no_and_gene_no_set)):
			bs_no2, gene_no_set2 = local_bs_no_and_gene_no_set[j]
			combo_set_local = gene_no_set1&gene_no_set2
			combo_size_local = len(combo_set_local)
			gene_no_set_global1 = bs_no2gene_no_set[bs_no1]
			gene_no_set_global2 = bs_no2gene_no_set[bs_no2]
			prob_bs1 = len(gene_no_set_global1)/float(no_of_total_genes)
			prob_bs2 = len(gene_no_set_global2)/float(no_of_total_genes)
			prob_combo = prob_bs1*prob_bs2
			combo_size_global = len(gene_no_set_global1&gene_no_set_global2)
			
			#first hypergeometric
			n = no_of_total_genes - combo_size_global
			p_value = r.phyper(combo_size_local-1,combo_size_global,n,cluster_size,lower_tail = r.FALSE)
			
			score = -p_value	#Watch minus, heapq is a min-heap
			bs_no_list = [bs_no1, bs_no2]
			global_ratio = float(combo_size_global)/no_of_total_genes
			local_ratio = float(combo_size_local)/cluster_size
			expected_ratio = global_ratio
			row = [score, 1, bs_no_list, list(combo_set_local), global_ratio, local_ratio, expected_ratio, unknown_ratio]
			hq_add(hq_list2, row, top_number)
			
			#second binomial log ratio
			likeli1 = r.dbinom(combo_size_local, cluster_size, prob_combo,log=r.TRUE)
			likeli2 = r.dbinom(combo_size_global, no_of_total_genes, prob_combo, log=r.TRUE)
			l_ratio = likeli1-likeli2
			
			score = -l_ratio	#Watch minus, heapq is a min-heap
			expected_ratio = prob_combo	#only this is different
			row = [score, 2, bs_no_list, list(combo_set_local), global_ratio, local_ratio, expected_ratio, unknown_ratio]	#Watch: 2
			hq_add(hq_list3, row, top_number)
			
	ls_to_return = []
	while hq_list1:
		row = heappop(hq_list1)
		row[0] = -row[0]	#minus back
		ls_to_return.append(row)
	while hq_list2:
		row = heappop(hq_list2)
		row[0] = -row[0]	#minus back
		ls_to_return.append(row)
	while hq_list3:
		row = heappop(hq_list3)
		row[0] = -row[0]	#minus back
		ls_to_return.append(row)
	ls_to_return.reverse()
	return ls_to_return
	
	
if __name__ == '__main__':
	if len(sys.argv) == 1:
		print __doc__
		sys.exit(2)
	
	if len(sys.argv)==4:
		#gene_no_list=[11287,11363,11364,11409,11522,12039,13171,13850,14085,15107,16922,17117,20341,21401,21743,51798,69574,104923]
		hostname = 'zhoudb'
		dbname = 'graphdb'
		schema = sys.argv[1]
		organism = sys.argv[2]
		inputfile = sys.argv[3]
		gene_no_list = get_gene_no_list(inputfile)
		long_organism = org_short2long(organism)
		(conn, curs) =  db_connect(hostname, dbname)
		
		gene_id2tf_set = get_gene_id2tf_set(curs, 'gene_id2tf', long_organism)
		gene_id2no = get_gene_id2gene_no(curs, schema)
		gene_no2tf_set, tf2no_of_genes, tf2gene_no_set = map2gene_no_reverse_map(gene_id2tf_set, gene_id2no)
		"""
		tf_stat_list, no_tf_gene_no_list = tf_stat(gene_no2tf_set, gene_no_list, tf2no_of_genes, len(gene_id2no))
		
		tf_combo_stat_list = tf_combo_stat(tf2gene_no_set, tf_stat_list, len(gene_id2no), len(gene_no_list))
		
		#output
		writer = csv.writer(sys.stdout, delimiter='\t')
		for row in tf_stat_list:
			row[2] = repr(row[2])[1:-1]
			writer.writerow(row)
		writer.writerow(["Genes_with_no_tf"]+no_tf_gene_no_list)
		tf_combo_stat_list.sort()
		for row in tf_combo_stat_list:
			row[-2] = repr(row[-2])[1:-1]
			writer.writerow(row)
		del writer
		"""
		ls_to_return = cluster_bs_analysis(gene_no_list, gene_no2tf_set, tf2gene_no_set)
		writer = csv.writer(sys.stdout, delimiter='\t')
		for row in ls_to_return:
			writer.writerow(row)
		del writer
	else:
		print __doc__
		sys.exit(2)
