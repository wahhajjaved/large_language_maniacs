#!/usr/bin/env python
# coding: utf-8

# In[ ]:


g={'AUA':'I', 'AUC':'I', 'AUU':'I', 'AUG':'M',
        'ACA':'T', 'ACC':'T', 'ACG':'T', 'ACU':'T',
        'AAC':'N', 'AAU':'N', 'AAA':'K', 'AAG':'K',
        'AGC':'S', 'AGU':'S', 'AGA':'R', 'AGG':'R',
        'CUA':'L', 'CUC':'L', 'CUG':'L', 'CUU':'L',
        'CCA':'P', 'CCC':'P', 'CCG':'P', 'CCU':'P',
        'CAC':'H', 'CAU':'H', 'CAA':'Q', 'CAG':'Q',
        'CGA':'R', 'CGC':'R', 'CGG':'R', 'CGU':'R',
        'GUA':'V', 'GUC':'V', 'GUG':'V', 'GUU':'V',
        'GCA':'A', 'GCC':'A', 'GCG':'A', 'GCU':'A',
        'GAC':'D', 'GAU':'D', 'GAA':'E', 'GAG':'E',
        'GGA':'G', 'GGC':'G', 'GGG':'G', 'GGU':'G',
        'UCA':'S', 'UCC':'S', 'UCG':'S', 'UCU':'S',
        'UUC':'F', 'UUU':'F', 'UUA':'L', 'UUG':'L',
        'UAC':'Y', 'UAU':'Y', 'UAA':'_', 'UAG':'_',
        'UGC':'C', 'UGU':'C', 'UGA':'_', 'UGG':'W'}
amino_mass={'A':71.03711,
  'C':103.00919,
  'D':115.02694,
  'E':129.04259,
  'F':147.06841,
  'G':57.02146,
  'H':137.05891,
  'I':113.08406,
  'K':128.09496,
  'L':113.08406,
  'M':131.04049,
  'N':114.04293,
  'P':97.05276,
  'Q':128.05858,
  'R':156.10111,
  'S':87.03203,
  'T':101.04768,
  'V':99.06841,
  'W':186.07931,
  'Y':163.06333}

def calc_mass(arg):
    n=[]
    am=[]
    for i in range(0,len(arg)):
        n.append(arg[i])
    for i in n:
        if i in amino_mass:
            am.append(amino_mass[i])
    return(sum(am))

def orf(arg):
    frame_1=''.join([gencode[arg[i:i+3]] for i in range(0, len(arg), 3) if len(arg[i:i+3])==3 ])
    frame_2=''.join([gencode[arg[i:i+3]] for i in range(1, len(arg), 3) if len(arg[i:i+3])==3 ])
    frame_3=''.join([gencode[arg[i:i+3]] for i in range(2, len(arg), 3) if len(arg[i:i+3])==3 ])
    frames=[frame_1, frame_2, frame_3]
    proteins=[]
    for frame in frames:
        protein=''
        for amino_acid in frame:
            if amino_acid=='M':
                protein+=amino_acid
            elif amino_acid=='_':
                if len(protein):
                    proteins.append(protein)
                    protein=''
                continue
            elif len(protein)>0:
                protein+=amino_acid
            else:
                continue
    proteins.sort()
    return proteins

def translate(seq):
    for i in range(0,len(seq)):
        if seq[0:3]!="AUG":
            seq=seq[1:]
    rna=[seq[i:i+3] for i in range(0, len(seq), 3)]
    rna=rna[1:]
      n=[]
    for i in rna:
        if i in g:
            n.append(g[i])
    n=n[:n.index("_")]
    n=''.join(n)
    return(n)

def parse(file):
    d={}
    cur_scaf=''
    cur_seq=[]
    for line in open(file):
        if line.startswith(">") and cur_scaf=='':
            cur_scaf=line.split(' ')[0]
        elif line.startswith(">") and cur_scaf!='':
            d[cur_scaf]=''.join(cur_seq)
            cur_scaf=line.split(' ')[0]
            cur_seq=[]
        else:
            cur_seq.append(line.rstrip())
    d[cur_scaf]=''.join(cur_seq)
    return d

