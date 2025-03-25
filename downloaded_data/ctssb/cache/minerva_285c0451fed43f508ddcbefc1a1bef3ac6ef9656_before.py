#!/usr/bin/env python

from termcolor import cprint
import re
import sys
import subprocess

class diamondBlast():
    def __init__(self, diamond_db, fasta_db):
        self.db = diamond_db
        self.fasta_db = fasta_db

    def get_protein_name(self):
        """Presumes that the final column contains the full uniprot header
        which includes product name"""
        try:
            hits = str(self.blast_result.stdout, 'utf-8').strip()
        except AttributeError:
            hits = None
        #cprint(hits, "red")
        if not hits:
            return None
        for i, hit in enumerate(hits.split('\n')):
            #print(i)
            #print(hit)
            full_head = hit.split('\t')[-1]
            protein_product = full_head.split('|')[-1].split('=')[0]
            protein_product = protein_product.split(' ')
            try:
                del protein_product[0]
                del protein_product[-1]
            except IndexError:
                print(full_head)
                raise IndexError
            protein_product = ' '.join(protein_product)
            #print(protein_product)
            if re.search("(hypothetical|uncharacterized)", protein_product, 
                    flags=re.IGNORECASE) and i < 10:
                continue
            return protein_product

    def perform_blast(self, query, *args, evalue=1e-10):
        blast_args = ['diamond', 'blastp', '-d', self.db, '-q', query, '-e', 
                      evalue, '-p', '1'] 
        [blast_args.append(arg) for arg in args]
        print(blast_args)
        self.blast_result = subprocess.run(blast_args, stdout=subprocess.PIPE)
        if self.blast_result.returncode > 0:
            print("something went horribly wrong")
            print(self.blast_result.args)
        return self.blast_result
