#!/usr/bin/env python

# Arguments: [temp_file] [scaffold] [pos]

import sys, re, collections

def process_line(line):

	# get the most frequent base and mean quality score

	# split line
	if 'no coverage' in line[0] or len(line) < 5: return [('N', 0)]	

	# sanitize bases
	line[4] = re.sub(r'[^ACTGactg,.\*]',"",line[4])
	line[4] = re.sub(r'[.,]', line[2],line[4]).upper()
	if line[4] == '': return [('N'), 0]

	# return nested list sorted on most common base
	count = collections.Counter(line[4])
	return count.most_common()


def zygosity(count):

	# calculate the ratio between the most abundant allele and minor alleles
	allele1, allele2 = count[0][1], sum([var[1] for var in count[1:]])
	return float(allele1)/(allele1+allele2)


def parse_Region():

	# parse the SNP region and check coverage and SNPs / InDels
	
	# set variables
	seq, zyg, cov, location, position = [], 0, [], [sys.argv[2],sys.argv[3]], 0
	ambigu = {'AC':'M','AG':'R','AT':'W','CG':'S','CT':'Y','GT':'K'}
	
	# parse file
	for base in open(sys.argv[1]):
		base = base.strip().split('\t')

		# get nuc count and check coverage
		count = process_line(base)
		cov.append(int(base[3]))		
		if int(base[3]) == 0: break	

		# check zygosity and add reference base to sequence
		if zygosity(count) <= 0.85:
			zyg += 1
			seq.append(ambigu[''.join(sorted([count[0][0],count[1][0]]))])
		elif position == 75 and zygosity(count) > 0.85: break
		else:
			seq.append(base[2])

		position += 1

	# check for coverage and zygosity, print the sequence
	# if thresholds are met
	if min(cov) >= 10 and zyg <= 3 and len(seq) == 151:
		SNP = (SNP for SNP,ambi in abigu.items() if ambi==seq[75]).next()
		seq[75] = '[{0}/{1}]'.format(SNP[0],SNP[1])
		print '\t'.join(location + [''.join(seq)])


# run the script
parse_Region()
