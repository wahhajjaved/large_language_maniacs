#make a dictionary = HLA-type to list of peptides
#code to convert a list into cluster 
from utilities import *
#dictRNA_file = '/scratch/users/bchen45/HLA_prediction/MCL_MHC_project/gene_analysis/MCLRNASeq_ave.dict'
path0 = '/scratch/users/bchen45/HLA_prediction/MCL_MHC_project/gene_analysis/'
import math
import pandas as pd
import random
import re



##substring between two patients
def get_shared(listy, listx):
    n_shared = 0
    common0=set()
    for fragx in listx:
        for fragy in listy:
            if fragx in fragy or fragy in fragx:
                common0.add(fragx)
                common0.add(fragy)
    return common0

#make a dictionary = HLA-type to list of patient IDs
def get_pid_for_each_hla(MCL_data,pid_list):
    dict_hla_pid = dumb()
    for pid0 in pid_list:
        #print MCL_data[pid0]['HLA_typing']
        hla1 = MCL_data[pid0]['HLA_typing'][-1]
        hla2 = MCL_data[pid0]['HLA_typing'][-2]
        dict_hla_pid[hla1].append(pid0)
        dict_hla_pid[hla2].append(pid0)
    return dict_hla_pid


#make peptide list from a set of pids
def get_pep_for_each_hla(dict_hla_pid,MCL_data):
    dict_hla_pep = dumb()
    for key, value in dict_hla_pid.iteritems():
        if len(value) > 1:
            set0 = set()
            for n0 in range(0,len(value)):
                for m0 in range(n0+1,len(value)):
                    common0 = get_shared(MCL_data[value[n0]]['MHC2_frag'],MCL_data[value[m0]]['MHC2_frag'])
                    set0 = set0 | common0
            #consider to add a cut-off
            dict_hla_pep[key] = list(set0)
    return dict_hla_pep

def print_d_list(dict0):
    for key,value in dict0.iteritems():
        print(key+': '+str(len(value)))
        
def make_training(path_save,hla_name0,list0,version0,t_ratio,v_ratio):
    one_gene_path = '/scratch/users/bchen45/HLA_prediction/IEDB/test0/human_proteinome_oneline.str'
    onegenestr = pickle.load(open(one_gene_path,'r'))
    len_one = len(onegenestr)
    file_out = open(path_save+hla_name0+version0+'_tr_'+str(t_ratio)+'_val.csv','w+')
    for pos0 in list0:
        random.seed(num_seed)
        if random.random() < v_ratio:
            #making validation
            file_out.write(pos0+'\t'+'3')
            rand0 = random.randint(0,len_one)
            neg0 = onegenestr[rand0:rand0+len(pos0)]
            file_out.write(neg0+'\t'+'2')
            neg0 = ''.join(random.sample(pos0,len(pos0)))
            file_out.write(neg0+'\t'+'2')
        else:
            file_out.write(pos0+'\t'+'1')
            for i in range(0,v_ratio):
                rand0 = random.randint(0,len_one)
                neg0 = onegenestr[rand0:rand0+len(pos0)]
                file_out.write(neg0+'\t'+'0')
                neg0 = ''.join(random.sample(pos0,len(pos0)))
                file_out.write(neg0+'\t'+'0')
    file_out.close()
        
  
    

MCL_data = pickle.load(open(path0+'MCL_data11_18_2015v1.1.dict','r'))
pid_list = MCL_data['pid']['pid']
dict_hla_pid = get_pid_for_each_hla(MCL_data,pid_list)
print_d_list(dict_hla_pid) 
dict_hla_pep = get_pep_for_each_hla(dict_hla_pid,MCL_data)
print_d_list(dict_hla_pep) 

##########making training#########
#version is an additional string to attach to each HLA type name for the training file
#t_ratio is an int number, the number of shuffled AND random peptide sequences generated for 
#each positive sequence (so 2X t_ratio for each positive sequence at the end)
#v_ratio is a flaat number (<1), the percentage of positive example will be used for validation
#and the double number of negative example (one shuffled, one random) will be created for validation
#0 negative training
#1 positive training
#2 negative validation
#3 positive validation
t_ratio = 1
v_ratio = 0.2
num_seed = 1
version0 = 'simplev1'
path_save = '/scratch/users/bchen45/HLA_prediction/RNN_data'
for hla_name0, list0 in dict_hla_pep.iteritems():
    hla_name0 = re.sub(r'[^\w]', '', hla_name0)
    make_training(path_save,hla_name0,list0,version0,t_ratio,v_ratio)





#print(len(set_04_01))

'''
############make clusters
list2 = list(set_04_01)
len2 = []
for x in list2:
    len2.append(len(x))
list_len_2 = zip(list2,len2)
list2,len2 = zip(*sorted(list_len_2,key=lambda x: x[1]))
#print list2
list2_tested = [True]*len(list2)
cluster_list = []
len_d_ave = []
len_d_max = []
len_std = []
for n0 in range(0,len(list2)):
    if list2_tested[n0]:
        list0 = []
        len_d0 = []
        len_l0 = []
        list0.append(list2[n0])
        for m0 in range(n0+1,len(list2)):
            if list2_tested[m0]:
                if list2[n0] in list2[m0]:
                    list2_tested[m0] = False
                    list0.append(list2[m0])
                    len_d0.append(len(list2[m0])-len(list2[n0]))
        cluster_list.append(list0)
'''
        
#print('total classII peptides='+str(len(list2)))

'''
print('total classII pep clusterings='+str(len(cluster_list)))
n0 = 0
for x in cluster_list:
    if len(x)>1:
        n0 += 1
print('total classII pep Non-singular clusterings='+str(n0))
print cluster_list
'''
