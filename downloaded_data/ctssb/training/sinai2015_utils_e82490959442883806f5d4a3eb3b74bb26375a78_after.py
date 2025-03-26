from __future__ import division

from biom.table import Table
from biom.util import biom_open
from biom import load_table 

import numpy as np

def make_partial_table(table_fp , output_dir):

    current_ko = None
    otu_list = []
    
    #Fixing the full and midial path management
    if not len(table_fp.split("/")) > 0 :
        table_p = "/".join(table_fp.split("/")[:-1])
        table_name = table_fp.split("/")[-1]
        output_name = table_p+"/ko_summary."+table_name
    else:
        output_name = "/".join([output_dir , table_fp])
    
    int_result = open(output_name , "w")
    
    for line in open(table_fp , "r"):
        #parse the column
        ko,sample,otu = line.strip("\n").split("\t")[:3]
        
        if 'Gene' in ko :
            continue
                   
        #case #1 first entry on the file 
        elif current_ko == None :
            current_ko = ko
            otu_list.append(otu)
            continue
        #case #2 change on the ko 
        elif not current_ko == ko:
                int_result.write("%s|%s\n" % ( ko , "\t".join(otu_list) ))
                current_ko = ko
                otu_list = [otu]
                continue
        #case #3 new otu realtion for the ko 
        else :
            otu_list.append(otu)
    
    int_result.close()
    return output_name




def make_ko_network_table(data , otus , kos , predicted , otu_table ):
    #Loading the tables 
    pred_table = load_table(predicted)
    otu_table  = load_table(otu_table)
    
    #Extract the taxonomy 
    otus_taxa = []
    for otu in otus:
        tmp = otu_table.metadata(otu,"observation")
        otus_taxa.append(tmp)
    
    #Extract KO taxa
    ko_taxa = []
    for ko in kos:
        tmp = pred_table.metadata(ko , "observation")
        ko_taxa.append(tmp)
    
    network_table = Table(data ,otus , kos , otus_taxa , ko_taxa  , "Ko_network")
    return network_table
   


def make_ko_contrib_table(table_fp , otu_table , predicted_table , output_dir):
    KO = []
    Otus = set()
    
    #Fixing for file path 
    file_fp = make_partial_table(table_fp , output_dir)
    output_p = "/".join(file_fp.split("/")[:-1])
    table_name = file_fp.split("/")[-1]
    
    #something odd
    # determine the Otus and have the KO in list 
    for line in open(file_fp , "r"):
        ko , otu_list = line.strip("\n").split("|")
        otu_list = otu_list.split("\t")
        KO.append(ko)
        Otus = Otus.union(set(otu_list))
    
    Otus = list(Otus)
    data = np.zeros((len(Otus) , len(KO)))
    
    #Populate the adj matrix with the data parsed from the file 
    for line in open(file_fp , "r"):
       ko , otu_list = line.strip("\n").split("|")
       otu_list = otu_list.split("\t")
       k_index = KO.index(ko)
       
       for o in otu_list:
           o_index = Otus.index(o)
           data[o_index , k_index ] = 1
    
    
    #write down the tables  
    ##sample = ko
    ko_network_table = make_ko_network_table(data , Otus ,
                                             KO  , predicted_table , otu_table)
    #doc = open(output_p+"/ko_network."+ table_name , "w")
    with biom_open(output_p+"/ko_network."+ table_name , "w") as biom_file:
        ko_network_table.to_hdf5(biom_file , "KO_NETWORK" ,True )
    #doc.close()
    pass
   
