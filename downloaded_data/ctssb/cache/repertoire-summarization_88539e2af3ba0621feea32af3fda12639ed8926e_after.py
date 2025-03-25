#!/usr/bin/env python

from sets import Set
import subprocess
import urllib2
from bs4 import BeautifulSoup
import yaml
from collections import defaultdict
import pprint
import re
from utils import *
import glob
import json
from igblast_utils import *
from subprocess import call
from Bio.Blast import NCBIXML
import sys, traceback
import pickle
import ntpath
#from utils import looksLikeAlleleStr
from utils import *
from Bio import SeqIO
import glob


#find the number of leaves
def countNumTerminalEntriesInHierarchy(h):
	num_kids=0
	for k in h:
		if(len(k.keys)==0):
			num_kids+=1
		else:
			num_kids+=countNumTerminalEntriesInHierarchy(h[k])
	return num_kids


#find out if two allels are the same except for the allele * part
#ie A*01 and A*02 ARE equivalent
#ie A*01 and B*01 ARE NOT equivalent!
def areTwoAllellesAlleleEquivalent(a1,a2):
	#print "in comp, a1=",a1,"a2="
	a1=re.sub(r'\*\d+$',"",a1)
	a2=re.sub(r'\*\d+$',"",a2)
	if(a1==a2):
		return True
	else:
		return False
	


#used in mapping IGBLAST data with
#IMGT data
#remove???
def get_key_from_blast_title(title):
	space_index=title.find(' ')
	space_index+=1
	#print "from title=",title," the space index is ",space_index
	key=title[space_index:]
	return str(key)


#from an IMGT descriptor, extract the IMGT name (eg IGHV4-1*01)
def extractIMGTNameFromKey(k):
	pieces=k.split("|")
	#print "the pieces are :",pieces
	#sys.exit(0)
	return pieces[1]



#from a string (presumably of DNA characters)
#remove Ns at the beginning and end
def removeHeadTailN(s):
	s=re.sub(r'^N+','',s)
	s=re.sub(r'N+$','',s)
	return s


#given an organism name,
#make it "directoryable"
#by removing chars such as /\-)( and
#replace them with '_'
def directoryFyOrgName(n):
	d=re.sub(r'[\ \/\-\(\);:]','_',n)
	return d



#used in mapping IGBLAST data with
#IMGT data
#remove???
def partitionIMGTFastaInDirByFile(f):
	fasta_map=read_fasta_file_into_map(f)
	for desc in fasta_map:
		pieces=desc.split("|")
		org=pieces[2]
		org_dir=directoryFyOrgName(org)
		dirPath=f+"_partition/"+org_dir+"/"
		#print "the dir path is ",dirPath
		if not os.path.exists(dirPath):
			os.makedirs(dirPath)
		org_fasta=dirPath+org_dir+".fna"
		part_writer=open(org_fasta,'a')
		part_writer.write(">"+desc+"\n")
		part_writer.write(fasta_map[desc]+"\n")
		part_writer.close()

		
	
#used in mapping IGBLAST data with
#IMGT data
#remove???
def filterIMGTMapByBasicCaseInsensitiveStartsWith(unfiltered_map,filter_str):
	filtered_map=dict()
	for key in unfiltered_map:
		unfkey_pieces=key.split("|")
		unfkey_imgt=unfkey_pieces[2]
		unfkey_imgt=unfkey_imgt.upper()
		filter_str=filter_str.upper()
		if(unfkey_imgt.startswith(filter_str)):
			filtered_map[key]=unfiltered_map[key]
		else:
			pass
	return filtered_map
			



#iterative, 'filter-based' process comparing two datasets
#igblast and imgt
def igblast_blast_map_multistep(nonExistentMapDir,query,refDirSetFNAList,allPPath,clone_map,alleleList,organism_filter):
	#query is path to query data
	#ref dir set fna list is a list of fasta of ref dir FNA files
	#allppath dir is a path to the allP file
	#clone_map is a dict (or list) of clone names (already subsetted by organism!)
	#allelelist is a dict (or list) of alleles (already subsetted by organism!)
	print "Now performing IGBLAST/IMGT multipstep mapping in directory :",nonExistentMapDir

	if(os.path.isdir(nonExistentMapDir)):
		#dir already exists! Abort!
		print "MAPPING directory",nonExistentMapDir,"already exists! Abort!"
		return
	else:
		os.mkdir(nonExistentMapDir)

	#step 1, copy query to process dir
	q_seq_map=read_fasta_file_into_map(query)
	query_path=nonExistentMapDir+"/query.fna"
	query_writer=open(query_path,'w')
	for d in q_seq_map:
		query_writer.write(">"+d+"\n")
		query_writer.write(q_seq_map[d]+"\n")
	query_writer.close()

	#step #2 copy seqs in ref dir fna list to a single db file
	totNumSeqsWrit=0
	ref_dir_db_fna_path=nonExistentMapDir+"/ref_dir_set_data.fna"
	ref_dir_db_fna_writer=open(ref_dir_db_fna_path,'w')
	for refDirFNA in refDirSetFNAList:
		#this list is already filtere by organism so no need to filter it by organism here
		s_seq_map=read_fasta_file_into_map(refDirFNA)
		#print "The number items read from ref dir ",refDirFNA," is ",len(s_seq_map)
		#if(len(s_seq_map)>0):
		#	sys.exit(1)
		for s in s_seq_map:
			#print "Writing key =",s
			#print "Writing value = ",s_seq_map[s][0:3],"..."
			ref_dir_db_fna_writer.write(">"+s+"\n")
			ref_dir_db_fna_writer.write(re.sub(r'\.','',s_seq_map[s])+"\n")
			totNumSeqsWrit+=1
	ref_dir_db_fna_writer.close()


	#step #3 take query data and blast it against ref dir set data
	#and return if all data are mapped!
	#"plan a"
	total_to_map=len(q_seq_map.keys())
	num_mapped=0
	ref_dir_map_path=nonExistentMapDir+"/ref_dir.map"
	ref_dir_unmap_path=nonExistentMapDir+"/ref_dir.unmapped"
	igblast_map_FA(query_path,ref_dir_db_fna_path,ref_dir_map_path,ref_dir_unmap_path,clone_map,alleleList)
	ref_dir_unmapped_list=read_list_from_file(ref_dir_unmap_path)
	numBlastMappedToRefDir=getNumberLinesInFile(ref_dir_map_path)
	numRemainingToMap=len(ref_dir_unmapped_list)
	print "Number items that blast mapped to the ref dir set : ",str(numBlastMappedToRefDir)
	print "Number left to map is ",str(numRemainingToMap)
	if(numRemainingToMap==0):
		print "No more mapping since all are mapped and none left to map!"
		return


	#Step #4, use NW to map data unmapped by BLAST 
	#and return if all data are mapped
	#plan "b"
	query_path_ref_dir_unmapped=query_path+".ref_dir_unmapped.fna"
	#fastaSubset(inputFastaPath,subset,outputFastaPath)
	fastaSubset(query_path,ref_dir_unmapped_list,query_path_ref_dir_unmapped)
	nw_log=query_path_ref_dir_unmapped+".nw.log"
	nw_map_ref_dir=nonExistentMapDir+"/ref_dir.nw.map"
	nw_map_ref_dir_unmapped=nw_map_ref_dir+".unmapped"
	nw_map_from_fastas(query_path_ref_dir_unmapped,ref_dir_db_fna_path,nw_log,clone_map,alleleList,nw_map_ref_dir,nw_map_ref_dir_unmapped)
	numNWMappedToRefDir=getNumberLinesInFile(nw_map_ref_dir)
	numNWUnMappedToRefDir=getNumberLinesInFile(nw_map_ref_dir_unmapped)
	print "Number items that NW mapped to the ref dir set : ",str(numNWMappedToRefDir)
	print "Number left to map is ",str(numNWUnMappedToRefDir)
	if(numNWUnMappedToRefDir==0):
		print "No more mapping since all are mapped and none left to map!"
		return
	

	#now take what nw couldn't map and blast it against allp
	#"plan c"
	all_p_map=read_fasta_file_into_map(allPPath)
	all_p_map=filterIMGTMapByBasicCaseInsensitiveStartsWith(all_p_map,organism_filter)
	allPLocalPath=nonExistentMapDir+"/allP.fna"
	fastaSubset(allPPath,all_p_map,allPLocalPath)#use this to basically just write the file
	allPBlastQuery=nw_map_ref_dir_unmapped+".blast.allpquery.fna"
	allPMapped=nonExistentMapDir+"/allP.map"
	allPUnmapped=allPMapped+".unmapped"
	print "FASTA SUBSET TO BE CALLED, FASTA=",query_path,"map=",nw_map_ref_dir_unmapped," and output=",allPBlastQuery
	fastaSubset(query_path,read_list_from_file(nw_map_ref_dir_unmapped),allPBlastQuery)
	print "To run blast with query=",allPBlastQuery,"db=",allPLocalPath,"mapped_out=",allPMapped,"unmapped_out=",allPUnmapped
	igblast_map_FA(
			allPBlastQuery,
			allPLocalPath,
			allPMapped,
			allPUnmapped,
			clone_map,
			alleleList
			)
	numMappedByBlastToAllP=getNumberLinesInFile(allPMapped)
	numUnMappedByBlastToAllP=getNumberLinesInFile(allPUnmapped)
	print "Number items that BLAST mapped to the allP file : ",str(numMappedByBlastToAllP)
	print "Number left to map is ",str(numUnMappedByBlastToAllP)
	if(numUnMappedByBlastToAllP==0):
		print "No more mapping since all are mapped and none left to map!"
		return		



	
	#now take what blast could map with allp and use nw as "plan d"
	allpnwinputsubsetfasta=nonExistentMapDir+"/nw.allp.query.fna"
	allPUnmappedList=read_list_from_file(allPUnmapped)
	fastaSubset(query_path,allPUnmappedList,allpnwinputsubsetfasta)
	allpnwmapped=nonExistentMapDir+"/nw.allp.map"
	allpnwunmapped=allpnwmapped+".unmapped"
	nwallpLog=allpnwmapped+".log"
	nw_map_from_fastas(allpnwinputsubsetfasta,allPLocalPath,nwallpLog,clone_map,alleleList,allpnwmapped,allpnwunmapped)
	nw_allp_map_count=getNumberLinesInFile(allpnwmapped)
	nw_allp_unmap_count=getNumberLinesInFile(allpnwunmapped)
	print "Number items that NW mapped to allP : ",nw_allp_map_count
	print "Number items left to map : ",nw_allp_unmap_count
	if(nw_allp_unmap_count==0):
		print "No more mapping since all are mapped and none left to map!"
	else:
		print "Unfortunately, the number of unmapped items is ",nw_allp_unmap_count," so there are still item left to map!"




#give  SINGLE fastas (query and subject) perform mapping/comparison
def igblast_map_FA(queryFastaPath,subjectFastaPath,mappedPath,unMappedPath,clone_map,alleleList):
	q_seq_map=read_fasta_file_into_map(queryFastaPath)
	s_seq_map=read_fasta_file_into_map(subjectFastaPath)
	#query fasta needs no editing, but subject fasta needs to
	#have a BLAST database build
	format_cmd=format_blast_db(subjectFastaPath)
	#now BLAST the query against the subject DB and save to a log file the commands run
	blast_output_path=subjectFastaPath+".blast.xml"
	xml_blast_cmd=blast_db(queryFastaPath,subjectFastaPath,blast_output_path)
	plain_blast_output_path=blast_output_path+".plain"
	pln_blast_cmd=blast_db(queryFastaPath,subjectFastaPath,plain_blast_output_path,False)
	blast_cmd_logger_path=subjectFastaPath+".blast.cmdlog"
	blast_cmd_logger=open(blast_cmd_logger_path,'w')
	blast_cmd_logger.write(xml_blast_cmd+"\n")
	blast_cmd_logger.write(pln_blast_cmd+"\n")
	blast_cmd_logger.close()
	human_blast=blast_output_path+".human_readable.txt"
	blast_map_path=mappedPath
	blast_unmapped_path=unMappedPath
	blast_mapped=dict()
	blast_unmapped=set()	
	status_lines=list()
	try:
		print "ENTER INTO TRY-PARSE BLOCK:"
		if(os.path.exists(blast_output_path)):
			if(os.path.getsize(blast_output_path)==0):
				#empty file!
				unmapped_cause_empty_file_list=list(q_seq_map.keys())
				mapped_cause_empty_file=dict()
				write_map_to_file(mapped_cause_empty_file,blast_map_path)
				write_list_to_file(list(unmapped_cause_empty_file_list),blast_unmapped_path)
				return
			else:
				#go ahead and attemp to parse!
				pass
		else:
			#non-existent file
			unmapped_cause_nonexisting_file_list=list(q_seq_map.keys())
			mapped_cause_nonexistent_file=dict()
			write_map_to_file(mapped_cause_nonexistent_file,blast_map_path)
			write_list_to_file(list(unmapped_cause_nonexisting_file_list),blast_unmapped_path)
		result_handle=open(blast_output_path)
		blast_records = NCBIXML.parse(result_handle)
		readable=open(human_blast,'w')
		for blast_record in blast_records:
			query_name=blast_record.query
			#map_analyzed.add(query_name)
			if(len(blast_record.alignments)<1):
				print "TOO FEW ALIGNMENTS",query_name
				status_line=blast_record.query+"\tNO_HIT"
				readable.write(status_line+"\n\n")
				status_lines.append(status_line)
				blast_unmapped.add(blast_record.query)
				continue
			alignment=blast_record.alignments[0]
			#print "An alignment length is ",alignment.length
			if(len(alignment.hsps)<1):
				print "TOO FEW HSPs",query_name
				status_line=blast_record.query+"\tNO_HIT"
				readable.write(status_line+"\n\n")
				status_lines.append(status_line)
				blast_unmapped.add(blast_record.query)
				continue
			hsp=alignment.hsps[0]
			#print "alignment title:",alignment.title
			s_map_key=get_key_from_blast_title(alignment.title)
			imgt_name=extractIMGTNameFromKey(s_map_key)
			#print "imgt  name :",imgt_name
			#print "query name :",blast_record.query
			status=""
			q_seq=removeHeadTailN(q_seq_map[blast_record.query])
			s_seq=s_seq_map[s_map_key]
			if(q_seq==s_seq):
				status="=="
			elif(a_subseq_of_b(q_seq,s_seq)):
				status="<"
			elif(a_subseq_of_b(s_seq,q_seq)):
				status=">"
			else:
				status="X"
			#sttus_line=blast_record.query+"\t"+imgt_name
			status_line=blast_record.query+"\t"+imgt_name
			readable.write(status_line+"\n")
			status_line=s_map_key
			readable.write(status_line+"\n")			
			if(imgt_name in clone_map):
				readable.write("clone_names : "+clone_map[imgt_name]+"\n")
			else:
				readable.write("no clone names!\n")
			alignment_frac=float(float(len(hsp.match))/float(min(len(s_seq),alignment.length)))
			#alignment_frac is the length of the alignment as a fraction of the shorter of the two sequences
			substr_ind=(a_subseq_of_b(hsp.query,hsp.sbjct) and a_subseq_of_b(hsp.sbjct,hsp.query))
			#substr_ind==TRUE means the alignment is perfect (no mutations)
			#
			readable.write("alignment_len="+str(len(hsp.match))+" query_len="+str(alignment.length)+" subject_len="+str(len(s_seq))+" alignment_frac=alignment_len/(min(query_len,subject_len))="+str(alignment_frac)+" subst_ind="+str(substr_ind)+"\n")
			readable.write(hsp.query+"\n")
			readable.write(hsp.match+"\n")
			readable.write(hsp.sbjct+"\n")
			if(imgt_name in alleleList):
				imgt_name_in_alleleList=True
			else:
				imgt_name_in_alleleList=False
			readable.write("Is IMGT purported name in the hierarchy : "+str(imgt_name_in_alleleList)+"\n")
			readable.write("\n"+"\n")
			status_lines.append(status_line)
			if( (imgt_name in alleleList) and substr_ind and ( (alignment_frac>=0.9 and alignment_frac<=1.0) or blast_record.query.strip()==imgt_name.strip())):
				blast_mapped[blast_record.query]=imgt_name
			else:
				blast_unmapped.add(blast_record.query)
			#print "\n\n\n"
		readable.close()
		status_lines.sort()
		#printList(status_lines)
		#blast_map_writer.close()
		write_map_to_file(blast_mapped,blast_map_path)
		write_list_to_file(list(blast_unmapped),blast_unmapped_path)
	except:
		print "Exception in BLAST user code:"
		print '-'*60
		traceback.print_exc(file=sys.stdout)
		print '-'*60
		#the file contents signal any errors
		write_map_to_file(blast_mapped,blast_map_path)
		write_list_to_file(list(blast_unmapped),blast_unmapped_path)
	print "DONE WITH TRY PARSE BLOCK...."	




#based on GLOBs perform a comparison IGBLAST/IMGT
def igblast_map(igblastFNAGlob,refDirFNAGlob,nonExistentMapDir,clone_map,alleleList):
	#get IGBLAST FNA files using the glob
	igblast_fna=glob.glob(igblastFNAGlob)
	if(os.path.isdir(nonExistentMapDir)):
		#dir already exists! Abort!
		print "MAPPING directory",nonExistentMapDir,"already exists! Abort!"
		return
	os.makedirs(nonExistentMapDir)
	query_file=nonExistentMapDir+"/query.fna"
	#write subject/reference fnas to a  single fasta after fetching them with GLOB
	db_file=nonExistentMapDir+"/db.fna"
	query_writer=open(query_file,'w')
	subject_fnas=glob.glob(refDirFNAGlob)
	db_writer=open(db_file,'w')
	s_seq_map=dict()
	imgt_names_map=dict()
	imgt_names_seq_map=dict()
	for s_fna in subject_fnas:
		print "Writing from file (for database) =",s_fna
		fasta_map=read_fasta_file_into_map(s_fna,alwaysSeqToUpper=True)
		for fasta_desc in fasta_map:
			descriptor=fasta_desc
			s_seq_map[descriptor]=fasta_map[fasta_desc]
			imgt_names_map[extractIMGTNameFromKey(fasta_desc)]=1
			imgt_names_seq_map[extractIMGTNameFromKey(fasta_desc)]=fasta_map[fasta_desc]
			seq=re.sub(r'\.','',fasta_map[fasta_desc])
			db_writer.write(">"+fasta_desc+"\n"+seq+"\n")
	db_writer.close()
	#write igblast files/fasta to a single FNA
	q_seq_map=dict()
	num_query_written=0
	for q_fna in igblast_fna:
		print "Writing from file (for query) =",q_fna
		fasta_map=read_fasta_file_into_map(q_fna,alwaysSeqToUpper=True)
		for fasta_desc in fasta_map:
			#if(fasta_desc=="VH7-40P"):
			#if(not(fasta_desc in imgt_names_map)):
			num_query_written+=1
			q_seq_map[fasta_desc]=fasta_map[fasta_desc]
			query_writer.write(">"+fasta_desc+"\n"+removeHeadTailN(fasta_map[fasta_desc])+"\n")
	query_writer.close()
	if(num_query_written==0):
		return
	#format the database and BLAST against them
	format_cmd=format_blast_db(db_file)
	a_db_file=db_file+".nhr"
	#blast against it
	blast_output_path=nonExistentMapDir+"/blast.xml"
	xml_blast_cmd=blast_db(query_file,db_file,blast_output_path)
	pln_blast_cmd=blast_db(query_file,db_file,blast_output_path+".plain",False)
	cmd_log=nonExistentMapDir+"/cmd.log"
	logger=open(cmd_log,'w')
	logger.write(format_cmd+"\n"+xml_blast_cmd+"\n"+pln_blast_cmd+"\n")
	logger.close()
	q_id=0
	status_lines=list()
	human_blast=blast_output_path+".human_readable.txt"
	blast_map_path=nonExistentMapDir+"/blast.map"
	blast_unmapped_path=nonExistentMapDir+"/blast.unmap"
	#touch(blast_map_path)
	blast_mapped=dict()
	blast_unmapped=set()
	#for fasta_desc in q_seq_map:
	#	unmapped.add(fasta_desc)
	try:
		print "ENTER INTO TRY-PARSE BLOCK:"
		result_handle=open(blast_output_path)
		blast_records = NCBIXML.parse(result_handle)
		readable=open(human_blast,'w')
		#blast_map_writer=open(blast_map_path,'w')
		blast_map=dict()
		for blast_record in blast_records:
			query_name=blast_record.query
			#map_analyzed.add(query_name)
			if(len(blast_record.alignments)<1):
				print "TOO FEW ALIGNMENTS",query_name
				status_line=blast_record.query+"\tNO_HIT"
				readable.write(status_line+"\n\n")
				status_lines.append(status_line)
				blast_unmapped.add(blast_record.query)
				continue
			alignment=blast_record.alignments[0]
			#print "An alignment length is ",alignment.length
			if(len(alignment.hsps)<1):
				print "TOO FEW HSPs",query_name
				status_line=blast_record.query+"\tNO_HIT"
				readable.write(status_line+"\n\n")
				status_lines.append(status_line)
				blast_unmapped.add(blast_record.query)
				continue
			hsp=alignment.hsps[0]
			#print "alignment title:",alignment.title
			s_map_key=get_key_from_blast_title(alignment.title)
			imgt_name=extractIMGTNameFromKey(s_map_key)
			#print "imgt  name :",imgt_name
			#print "query name :",blast_record.query
			status=""
			q_seq=removeHeadTailN(q_seq_map[blast_record.query])
			s_seq=s_seq_map[s_map_key]
			if(q_seq==s_seq):
				status="=="
			elif(a_subseq_of_b(q_seq,s_seq)):
				status="<"
			elif(a_subseq_of_b(s_seq,q_seq)):
				status=">"
			else:
				status="X"
			#sttus_line=blast_record.query+"\t"+imgt_name
			status_line=blast_record.query+"\t"+imgt_name
			readable.write(status_line+"\n")
			status_line=s_map_key
			readable.write(status_line+"\n")			
			if(imgt_name in clone_map):
				readable.write("clone_names : "+clone_map[imgt_name]+"\n")
			else:
				readable.write("no clone names!\n")
			alignment_frac=float(float(len(hsp.match))/float(min(len(s_seq),alignment.length)))
			#alignment_frac is the length of the alignment as a fraction of the shorter of the two sequences
			substr_ind=(a_subseq_of_b(hsp.query,hsp.sbjct) and a_subseq_of_b(hsp.sbjct,hsp.query))
			#substr_ind==TRUE means the alignment is perfect (no mutations)
			#
			readable.write("alignment_len="+str(len(hsp.match))+" query_len="+str(alignment.length)+" subject_len="+str(len(s_seq))+" alignment_frac=alignment_len/(min(query_len,subject_len))="+str(alignment_frac)+" subst_ind="+str(substr_ind)+"\n")
			readable.write(hsp.query+"\n")
			readable.write(hsp.match+"\n")
			readable.write(hsp.sbjct+"\n")
			if(imgt_name in alleleList):
				imgt_name_in_alleleList=True
			else:
				imgt_name_in_alleleList=False
			readable.write("Is IMGT purported name in the hierarchy : "+str(imgt_name_in_alleleList)+"\n")
			readable.write("\n"+"\n")
			status_lines.append(status_line)
			if( (imgt_name in alleleList) and substr_ind and ( (alignment_frac>=0.9 and alignment_frac<=1.0) or blast_record.query.strip()==imgt_name.strip())):
				blast_mapped[blast_record.query]=imgt_name
			else:
				blast_unmapped.add(blast_record.query)
			#print "\n\n\n"
		readable.close()
		status_lines.sort()
		printList(status_lines)
		#blast_map_writer.close()
		write_map_to_file(blast_mapped,blast_map_path)
		write_list_to_file(list(blast_unmapped),blast_unmapped_path)
	except:
		print "Exception in BLAST user code:"
		print '-'*60
		traceback.print_exc(file=sys.stdout)
		print '-'*60
	print "DONE WITH TRY PARSE BLOCK...."
	try:
		logPath=nonExistentMapDir+"/nw_log.txt"
		nw_input_map=dict()
		for item in blast_unmapped:
			nw_input_map[item]=q_seq_map[item]
		good_map=find_best_nw_from_maps_KeepPerfects(nw_input_map,s_seq_map,logPath,clone_map,alleleList)
		write_map_to_file(good_map,nonExistentMapDir+"/nw.map")
		nw_unmapped=set()
		for item in blast_unmapped:
			if(item not in good_map):
				nw_unmapped.add(item)
		nw_umapped_path=nonExistentMapDir+"/nw.unmapped"
		write_list_to_file(list(nw_unmapped),nw_umapped_path)
	except:
		print "ERROR IN NW alignment calls!\n"
		print "Exception in user code:"
		print '-'*60
		traceback.print_exc(file=sys.stdout)
		print '-'*60





#given a MYSQLLITE DB, make a JSON from the counts
def get_count_JSON_ofVDJ(dbfilepath,db_base_dir,organism_name):
	print "Now getting counts from ",dbfilepath,"..."
	counts_map=get_rearrangement_segment_counts_from_db(dbfilepath)
	print "Now retrieving hierachy from ",db_base_dir," for organism=",organism_name,"..."
	down_dir=analyze_download_dir_forVDJserver(db_base_dir,counts_map,organism_name)
	filled_hierarchy=down_dir[0]
	unallocated_segments_counts=dict()
	treeAlleles=get_list_of_alleles_appearing_in_tree(filled_hierarchy)
	for segment in counts_map:
		if segment in treeAlleles:
			pass
		elif(segment=="N/A"):
			pass
		else:
			unallocated_segments_counts[segment]=counts_map[segment]
	for segment in unallocated_segments_counts:
		filled_hierarchy[organism_name]['unallocated'][segment]
	JSON=jsonify_hierarchy(filled_hierarchy[organism_name],organism_name,counts_map)
	return JSON

#get the IMGT URL base
#used in the downloading process
def getIMGTURLBase():
	return "http://www.imgt.org/"

#get the list of LOCI
def get_loci_list():
	loci=["IGHV","IGHD","IGHJ","IGKV","IGKJ","IGLV","IGLJ","TRAV","TRAJ","TRBV","TRBD","TRBJ","TRDV","TRDD","TRDJ","TRGV","TRGJ"]
	return loci

#of the 17 loci, return the ones defined as "heavy"
def get_heavy_loci():
	defined_as_heavy=["IGHD","IGHJ","IGHV","TRBD","TRBJ","TRBV","TRDD","TRDJ","TRDV"]
	return defined_as_heavy

#get loci that are light (not heavy)
def get_light_loci():
	all_loci=get_loci_list()
	heavy_loci=get_heavy_loci()
	light_loci=list()
	for locus in all_loci:
		if(locus in heavy_loci):
			pass
		else:
			light_loci.append(locus)
	return light_loci




#is the given loci one of the 17???
def isLegitimateLoci(locus):
	loci_list=get_loci_list()
	locus=locus.upper()
	return (locus in loci_list)

#given a species and locus
#form a URL to download the FNA data
#that is the REFERENCE DIRECTORY SET!
#note only "allowed" species and loci are used
#in the formation of URLs
#unallowed triggers an exception
def formRefDirURL(species,locus):
	base=getIMGTURLBase()
	allowed=dict()
	allowed['Homo+sapiens']=1
	allowed['Mus_musculus']=1
	allowed['Mus_spretus']=1
	allowed['Rattus+norvegicus']=1
	allowed['Oryctolagus+cuniculus']=1
	allowed['Oncorhynchus+mykiss']=1
	allowed['Macaca+mulatta']=1
	allowed['Danio+rerio']=1
	allowed['Sus+scrofa']=1
	allowed['Mus']=1
	if(species.upper().startswith("MUS")):
		species="Mus"
	if((species in allowed) and (isLegitimateLoci(locus))):
		#THESE URLS ARE FROM http://www.imgt.org/genedb/html/directlinks.html
		#base+="IMGT_GENE-DB/GENElect?query=7.2+"+locus+"&species="+species
		#http://www.imgt.org/IMGT_GENE-DB/GENElect?query=7.2+TRDV&species=Homo+sapiens   
		#IMGT/GENE-DB reference sequences in FASTA format:
		#Nucleotide sequences for F+ORF+all P alleles
		#for F+ORF+in-frame P alleles, including orphons

		#http://www.imgt.org/IMGT_GENE-DB/GENElect?query=7.14+TRDV&species=Homo+sapiens 
		#IMGT/V-QUEST reference sequences in FASTA format:  
		#Nucleotide sequences with gaps according to the IMGT unique numbering 
		#for F+ORF+in-frame P alleles, including orphons
		#see also URLS/links here : http://www.imgt.org/vquest/refseqh.html
		#IMGT/V-QUEST reference directory sets
		#    The IMGT/V-QUEST reference directory sets are constituted by sets of sequences which contain the V-REGION, D-REGION and J-REGION alleles, isolated from the Functional (F), ORF and in-frame pseudogene (P) allele IMGT reference sequences. By definition, these sets contain one sequence for each allele. Allele names of these sequences are shown in red in Alignments of alleles.
		#    The IMGT/V-QUEST reference directory sets also include orphons.
		#    The human and the mouse IG and TR sets are exhaustive and correspond to the IMGT/GENE-DB content in terms of F+ORF+in-frame P genes and alleles.
		#    IMGT/V-QUEST reference directory sets comprise IG and TR sets (for one or several species) which are used in IMGT/V-QUEST for the identification and alignment of the input sequence. 
		base+="IMGT_GENE-DB/GENElect?query=7.14+"+locus+"&species="+species
		return base

		

	else:
		exceptionStatus="Invalid locus or invalid species for reference directory set URL formation!"
		exceptionStatus+="\nLocus ("+locus+") legitimacy : "+str(isLegitimateLoci(locus))
		exceptionStatus+="\nSpecies ("+species+") legitimacy : "+str((species in allowed))
		raise Exception(exceptionStatus)




#given HTML data, count the number
#of appearances of "&gt;", which,
#when decoded, is ">" which is the fasta descriptor signal
def countNumApparentFastaRecsInStr(s):
	if(s is None):
		return (-1)
	lines=s.split("\n")
	n=0
	for l in lines:
		if(l.startswith("&gt;")):
			n+=1
		elif(l.startswith(">")):
			n+=1
		else:
			#print "Couldn't find a fasta in ",l[0:10],"...."
			pass
	return n




#from <pre>...</pre> HTML tag
#extract the fasta data within it
#and return it as a string
def filterOutFastaStringFromFastaPre(p):
	dnaRE=re.compile(r'[actg\.]')
	lines=p.split("\n")
	good_data=list()
	for line in lines:
		if(line.startswith("&gt;") or dnaRE.match(line)):
			good_data.append(line.replace("&gt;",">"))
	nl="\n"
	result=nl.join(good_data)
	#print "Returning the result:",result
	return result





#given a locus and species download the corresponding
#reference directory set data from IMGT and return
#it as a string
#use BEAUTIFUL SOUP for parsing
def downloadRefDirFasta(locus,species,URLOverRide=None):
	if(URLOverRide is None):
		url=formRefDirURL(species,locus)
	else:
		url=URLOverRide
	#url="file:///home/data/vdj_server/igblast_routines/GENElect?query=7.2+IGHD&species=Homo+sapiens"
	#Number of results=162
	print "THE URL IS ",url
	#f = urllib2.urlopen(url)
	#html=f.read()
	#print html
	html= readAURL(url)
	#print "THE HTML READ IS ",html
	matchObj = re.search( r'Number\s+of\s+results\s*=\s*(\d+)', html, re.M|re.I)
	#matchObj = re.match( r'=(\d+)', html, re.M|re.I)
	if(matchObj):
		num_expected=int(matchObj.group(1))
		print "THE NUM EXPECTED IS ",num_expected
		soup=BeautifulSoup(html)
		y=soup.find_all('pre') #returns data between <pre> tags
		pre_num=0
		for a in y:
			print "GOT A PRE ",pre_num
			#print a[0:10]
			pre_num+=1
		print "Total number pre found : ",pre_num
		pre_num=0			
		for a in y:
			print "GOT A PRE ",pre_num
			pre_num+=1
			#print a
			print "the type : ",type(a)
			if a is not None:
				z_num=int(countNumApparentFastaRecsInStr(str(a)))
				print "An apparent is ",z_num
				#print "The source apparent is ",a
				if(z_num==num_expected):
					#print "got expected fasta: ",a
					fastaString=a
					#print fastaString
					fastaString=filterOutFastaStringFromFastaPre(str(fastaString))
					return str(fastaString)
				else:
					#print "Error, expected ",num_expected," FASTA records, but found ",z_num," records instead!"
					pass
			else:
				print "SOUP failed to find a <pre> tag from which FASTA can be extracted!"
		
	else:
		print "\nFAILURE TO MATCH! from URL=",url





#given a species and a locus
#form a URL for subsequent download 
#from IMGT
def formGeneTableURLs(species,locus):
	#http://www.imgt.org/IMGTrepertoire/index.php?section=LocusGenes&repertoire=genetable&species=human&group=IGHV
	allowed=dict()
	allowed['human']=1
	allowed['Mus_musculus']=1
	if( (species in allowed)  and (isLegitimateLoci(locus))):
		base=getIMGTURLBase()
		base+="IMGTrepertoire/index.php?section=LocusGenes&repertoire=genetable&species="+species+"&group="+locus
		withOrph=base+"&orphon"
		stuff=list()
		stuff.append(base)
		stuff.append(withOrph)
		return stuff	
	else:
		exceptionStatus="Invalid locus or invalid species for gene table set URL formation!"
		exceptionStatus+="\nLocus ("+locus+") legitimacy : "+isLegitimateLoci(locus)
		exceptionStatus+="\nSpecies ("+species+") legitimacy : "+(species in allowed)
		raise Exception(exceptionStatus)







#example tree usage
def basic_tree_test():
	mytree=tree()
	mytree['TCRA']
	mytree['TCRA']['TCRA1']
	mytree['TCRA']['TCRA2']
	counts_map=dict()
	counts_map['TCRA1']=3
	counts_map['TCRA2']=7
	get_total_tree(mytree['TCRA'],'TCRA',counts_map)
	









#from http://stackoverflow.com/questions/8384737/python-extract-file-name-from-path-no-matter-what-the-os-path-format
def path_leaf(path):
	head, tail = ntpath.split(path)
	return tail or ntpath.basename(head)








#find .dat hierarchies in in_dir
#create corresponding .json file in out_dir (which is not the same as in dir) with counts
def hierarchy_jsonify_batch(in_hier_dir,out_hier_dir,count_map):
	if not os.path.exists(out_hier_dir):
		os.makedirs(out_hier_dir)
	else:
		print "ERROR, output directory ",out_hier_dir," exists! Abort !"
		sys.exit(1)
	in_glob_str=in_hier_dir+"/*.dat"
	in_dat_files=glob.glob(in_glob_str)
	for x in range(len(in_dat_files)):
		#print "got .dat file (#"+(str(int(x)+1))+") : ",in_dat_files[x]
		basename=path_leaf(in_dat_files[x])
		#print "The base name is ",basename
	   	target=out_hier_dir+"/"+basename+".json"
		#print "The target is ",target
		hier_root=getRootFromFile(in_dat_files[x])
		#print "The hier_root is ",hier_root
		hier_tree=getHierarchyTreeFromFile(in_dat_files[x])
		json_string=jsonify_hierarchy(hier_tree[hier_root],hier_root,count_map)
		json_file=open(target,'w')
		json_file.write(json_string)
		json_file.close()
		
		



#given a hierarchy file (of tab-separated values of parent/child)
#return a tree with the indicated hierarchy
def getHierarchyTreeFromFile(hier_file):
	#get the hierarchy
	#hier_file="/home/data/vdj_server/pipeline/vdj_ann/hierarchy.txt";
	#hier_file="/home/data/vdj_server/pipeline/vdj_ann/17_way/IGHJ.dat"
	#get the child->parent map
	mapping=get_pmap(hier_file)
	array_eval_join_str=str("']['")
	taxonomy = tree()
	#taxonomy['Animalia']['Chordata']['Mammalia']['Carnivora']['Felidae']['Felis']['cat']
	for child in mapping:
		lineage=hier_look(mapping,child,20)
		#print "i have a child=",child,"with lineage="+lineage
		lineage_array=lineage.split('->')
		#print "\tAs an array : ",lineage_arrayIndentationError: expected an indented block
		lineage_array.reverse()
		#print "\tAs a reversed array : ",lineage_array
		str_to_eval=array_eval_join_str.join(lineage_array)
		str_to_eval="taxonomy['"+str_to_eval+"']"
		#print "\tThe str to eval is "+str_to_eval
		eval(str_to_eval)
	return taxonomy







#given a list, return it back
#but with each element having been
#applied with "strip"
def trimList(l):
	for idx, val in enumerate(l):
		#print idx, val
		l[idx]=l[idx].strip()
	return l







#from a hierarchy file (tab-separated)
#find the root by searching for a parent
#who is its own child
def getRootFromFile(hfile):
	f = open(hfile, 'r')
	root=""
	for line in f:
		line=line.strip()
		pieces=line.split('\t')
		if(pieces[0]==pieces[1]):
			root=pieces[0]
	f.close()
	return root














#from a tab-separated values file
#get a mapping 
#first colum is child
#second column is parent
#children allowed 0 or 1 parents, no more
#multiple parents triggers shutdown
def get_pmap(hier_file):
	mapping=dict()
	f = open(hier_file, 'r')
	#print f
	for line in f:
		line=line.strip()
		pieces=line.split('\t')
		if(pieces[0] in mapping):
			print "Error, DOUBLE MAPPING",line
			exit(1)
		mapping[pieces[0]]=pieces[1]
	f.close()
	return mapping






#Given a map (parent/child) and a name
#get the lineage
def hier_look(pmap,name,max_iter):
	#here pmap is a map keys are children, values are parents
	#name is a child whose lineage to root is desired
	#max_iter is a maximum number of iterations to use in the recursive lookup
	if(max_iter<=0):
		return "ERR_STACKOVERFLOW_"+name
	if(name in pmap):
		parent=pmap[name]
		if(parent==name):
			return (name)
		else:
			return name+"->"+hier_look(pmap,parent,max_iter-1)

	else:
		print "ERROR, name=",name," not a key!"
		return "ERR"









#given a hierarchy (parent/child) file
# initialize a map of counts whose keys
#are the children and whose counts are initialized to zero
def init_hierarchy_count_map(hierarchy_file):
	INPUT=open(hierarchy_file,'r')
	count_map=dict()
	for line in INPUT:
		#child on the left, parent on the right
		line=line.strip()
		pieces=line.split('\t')
		count_map[pieces[0]]=0
	return count_map





#determine if all strings in a list are allelic
#if at least one FAILS return false
def areAllItemsInListIMGTAlleles(l):
	for i in l:
		if(not(looksLikeAlleleStr(i))):
			return False
	return True








#from a tree object, return a map of parent/child relationships
#keys are kids
#values are their parents
def getPMapFromTree(t,emap,currentParent):
	print "getPMapFromTree called with currentParent="+currentParent
	for k in t:
		print "setting k/v pair with k=",str(k),"and v=",str(currentParent)
		emap[str(k)]=str(currentParent)
		emap=getPMapFromTree(t[k],emap,k)
	return emap	






#using a directory, with organism directories under it
#iterate through .map files
#and pick up clone names
#the map files must match the glob *clone_names.map
def get_clone_names_by_org_map_from_base_dir(bd):
	print "now in ",bd
	clone_names_by_org=dict()
	organisms=getOrganismList()
	for organism in organisms:
		print "now in org=",organism
		clone_names_by_org[organism]=dict()
		#./human/GeneTables/TRGV.html.orphons.html.clone_names.map
		names_glob=bd+"/"+organism+"/GeneTables/*clone_names.map"
		map_files=glob.glob(names_glob)
		for map_file in map_files:
			print "To read from ",map_file
			reader=open(map_file,'r')
			for line in reader:
				line=line.strip()
				pieces=line.split('\t')
				if(len(pieces)==2):
					clone_names_by_org[organism][pieces[0]]=pieces[1]
			reader.close()
	return clone_names_by_org





#used in IGBLAST/IMGT mapping
def getPartitionGlobFromIMGTFastaPathAndOrganism(f,org):
	if(org=="Mus_musculus"):
		return f+"_partition/Mus*/*.fna"
	elif((org=="Homo sapiens") or (org=="human") or (org.starswith("human"))):
		return f+"_partition/Homo_sapiens/*.fna"
	else:
		print "ABORT TRYING TO ACCESS UN PARTITIONED DATA...."
		print "f=",f
		print "org=",org
		sys.exit(0)


#used in IGBLAST/IMGT mapping
def igblast_imgt_mapping(base_dir,org_to_glob_db_map,imgtfastaPath,hierachyByOrg):
	clone_names_by_org=get_clone_names_by_org_map_from_base_dir(base_dir)
	organism_list=getOrganismList()
	for organism in organism_list:
		segments=['V','D','J']
		#segments=['D']
		alleleNames=get_list_of_alleles_appearing_in_tree(hierachyByOrg[organism])
		print "\n\nTHE FOLLOWING TREE WAS USED FOR EXTRACTING ALLELE NAMES :"
		prettyPrintTree(hierachyByOrg[organism])
		print "\n\nTHE ALLELE NAMES EXTRACTED ARE : "
		printList(alleleNames)
		print "\n\n\n"
		ref_glob=getPartitionGlobFromIMGTFastaPathAndOrganism(imgtfastaPath,organism)
		for segment in segments:
			ig_glob=org_to_glob_db_map[organism]+segment+".fna"
			#if(organism=="Mus_musculus"):
			#	#ig_glob="/usr/local/igblast_from_lonestar/database/mouse_gl_"+segment+".fna"
			#	ig_glob=org_to_glob_db_map[org
			#else:IndentationError: expected an indented block
			#	#continue
			#	ig_glob="/usr/local/igblast_from_lonestar/database/"+organism+"_gl_"+segment+".fna"
			#ref_glob="/tmp/imgt_down/"+organism+"/ReferenceDirectorySet/IG*"+segment+".html.fna"
			#ref_glob="/home/esalina2/Downloads/imgt.2/www.imgt.org/download/GENE-DB/IMGTGENEDB-ReferenceSequences.fasta-nt-WithoutGaps-F+ORF+allP"
			#ref_glob=imgtfastaPath

			blast_dir=base_dir+"/"+organism+"/BLAST_MAP_"+segment
			print "Calling blast_map with ig_glob=",ig_glob,"ref_glob=",ref_glob," and blast_dir=",blast_dir
			try:
				igblast_map(ig_glob,ref_glob,blast_dir,clone_names_by_org[organism],alleleNames)
			except Exception, e:
				print "igblast_map error!"
				print "Exception in user code:"
				print '-'*60
				traceback.print_exc(file=sys.stdout)
				print '-'*60	






def makeIGBLASTVRegionDatabase(outputdir,listOfVDatabases,auxBase):
	if not os.path.exists(outputdir):
			os.makedirs(outputdir)	
	#write a script that contains commands for extracting FNAs from BLAST DBs
	script_path=outputdir+"/blast_script.sh"
	igblast_executable_path=getIGBlastExecutablePath()
	domain_list=getDomainClasses()
	resultFiles=list()
	sw=open(script_path,'w')
	sw.write("#!/bin/bash\n")
	
	for db in listOfVDatabases:
		#write a query_file for each db
		base_name=ntpath.basename(db)
		db_query_file=outputdir+"/"+base_name+".fna"
		blastdbcmdpath="/usr/local/bin/blastdbcmd"
		cmd=blastdbcmdpath+" -db "+db+" -dbtype nucl -entry all > "+db_query_file
		sw.write(cmd+"\n")
		ddb=re.sub(r'_V','_D',db)
		jdb=re.sub(r'_V','_J',db)
		for domain in domain_list:
			orgRE=re.search(r'/([^_/]+)_gl_V',db)
			if(orgRE):
				org=orgRE.group(1)
				aux_full=auxBase+"/"+org+"_gl.aux"
				result_file=db_query_file+"."+domain+".out"
				igblast_cmd=igblast_executable_path+" -domain_system "+domain+" -germline_db_V "+db+" -germline_db_D "+ddb+"  -germline_db_J "+jdb+" -query "+db_query_file+" -outfmt 7 -out "+result_file+" -auxiliary_data "+aux_full
				sw.write(igblast_cmd+"\n")		
				resultFiles.append(result_file)
	sw.close()
	#run the script with logs referenced
	script_err=script_path+".err"
	script_out=script_path+".out"
	execute_bash_script(script_path,script_out,script_err)
	#now parse the outputs and write dbs!
	regions=['FWR1','CDR1','FWR2','CDR2','FWR3','CDR3']
	current_query=None
	for result_file in resultFiles:
		region_map=tree()
		query_list=list()
		db_lookup_file=result_file+".db"
		dw=open(db_lookup_file,'w')
		rr=open(result_file,'r')
		for line in rr:
			temp=line.strip()
			search_res=re.search(r'^#\ Query:\ (.*)$',temp)
			if(search_res):
				current_query=search_res.group(1)
				current_query=re.sub(r'lcl\|','',current_query)
				print "picked up cq ",current_query				
				query_list.append(current_query)
			for region in regions:
				if(temp.startswith(region) and not(current_query==None)):
					region_map[query_list[len(query_list)-1]][region]=temp
		rr.close()
		print "now to writing...."
		for q in range(len(query_list)):
			query=query_list[q]
			query=re.sub(r'lcl\|','',query)
			print "writing for query=",query," file=",db_lookup_file
			dw.write(query+"\t")
			for r in range(len(regions)):
				print "now looking at ",regions[r]
				if(regions[r] in region_map[query]):
					data=str(region_map[query][regions[r]])
					#print "from query=",query," data=",data
					data_pieces=data.split('\t')
					if(data_pieces[0].strip().startswith("CDR3")):
						dw.write(data_pieces[1]+"N/A\n")
					else:
						dw.write(data_pieces[1]+"\t"+data_pieces[2]+"\t")
				else:
					if(regions[r]=="CDR3"):
						dw.write("N/A\tN/A\n")
					else:
						dw.write("N/A\tN/A\t")
		dw.close()


#map IGBLAST and IMGT data
def batchMultistepSegmentsAndOrganisms(base_dir):
	allPPath="/tmp/imgt_down/www.imgt.org/download/GENE-DB/IMGTGENEDB-ReferenceSequences.fasta-nt-WithoutGaps-F+ORF+allP"
	hier_data=loadPickleDataAndMakeIfNotAvailable(base_dir)
	organism_hierarchy=hier_data[0]
	clone_names_by_org=hier_data[1]
	#	alleleNames=get_list_of_alleles_appearing_in_tree(organism_hierarchy['human'])
	organism_list=getOrganismList()
	for organism in organism_list:
		segment_list=['V','D','J']
		for segment in segment_list:
			blast_dir=base_dir+"/"+organism+"/BLAST_MAP_"+segment
			filter_str=""
			if(organism=="human"):
				filter_str="Homo "
			elif(organism=="Mus_musculus"):
				filter_str="Mus "
			segment_ref_dir_org_glob=base_dir+"/"+organism+"/ReferenceDirectorySet/IG*"+segment+".html.fna"
			segment_ref_dir_org_list=glob.glob(segment_ref_dir_org_glob)
			blast_base_org=organism
			if(organism=="Mus_musculus"):
				blast_base_org="mouse"
			query="/usr/local/igblast_from_lonestar/database/"+blast_base_org+"_gl_"+segment+".fna"
			alleleNames=get_list_of_alleles_appearing_in_tree(organism_hierarchy[organism])
			igblast_blast_map_multistep(
				blast_dir,
				query,
				segment_ref_dir_org_list,
				allPPath,
				clone_names_by_org[organism],
				alleleNames,
				filter_str
				)
			






def loadPickleDataAndMakeIfNotAvailable(base_dir):
	pickleFilePath=base_dir+"/hierarchy_data.pkl"
	if(os.path.exists(pickleFilePath)):
		hier_data=pickleRead(pickleFilePath)
	else:
		hier_data=analyze_download_dir_forVDJserver("/tmp/imgt_down",None,None,None)
		pickleWrite(pickleFilePath,hier_data)
	#organism_hierarchy=hier_data[0]
	#clone_names_by_org=hier_data[1]	
	return hier_data
	





	
		

#verify if a dat file is usable with its index
def testIdx(dat,idx):
	idx_read=open(idx,'r')
	m=5
	for line_num in range(m):
		print "\n\n\n"
		line=idx_read.readline()
		print "read line :"+str(line)
		pieces=line.split('\t')
		acc=pieces[0]
		start=int(pieces[1])
		end=int(pieces[2])
		data=fetchRecFromDat(dat,start,end)
		print "For accession='"+str(acc)+"', got data='"+str(data)+"' ! :)\n\n"








#the IMGT class
#object container for data and methods
#for database FNA and GENETABLE files
class imgt_db:
	####################
	#data members
	org_allele_name_desc_map=None
	db_base=None
	db_idx_extension=".acc_idx"
	accession_start_stop_map=None
	accession_dat_file_map=None
	imgt_dat_rel_path="www.imgt.org/download/LIGM-DB/imgt.dat"
	imgt_dat_path=None
	indexPath=None
	ref_dir_set_desc_seqs_map=None
	ol=["human","Mus_musculus"]

	####################
	#constructor(s)
	def __init__(self,init_db_base):
		self.db_base=init_db_base
		self.imgt_dat_path=self.db_base+"/"+self.imgt_dat_rel_path

	####################
	#function members


	#for each locus, for each organism, dump it into a FASTA to be blast formatted
	def prepareFASTAForBLASTFormatting(self):
		organisms=self.getOrganismList()
		for organism in organisms:
			loci=get_loci_list()
			for locus in loci:
				rds_base=self.db_base+"/"+organism+"/ReferenceDirectorySet/"
				source_html_fna=rds_base+locus+".html.fna"
				target_fna=rds_base+"/"+organism+"_"+locus[0:2]+"_"+locus[3]+".fna"
				fna_map=read_fasta_file_into_map(source_html_fna)
				blast_fna_map=dict()
				for desc in fna_map:
					blast_desc=getIMGTNameFromRefDirSetDescriptor(desc)
					blast_fna_map[blast_desc]=fna_map[desc]
				blast_writer=open(target_fna,'a')
				num_descs=len(fna_map)
				rec_num=0
				for blast_desc in blast_fna_map:
					desc_str=">"+blast_desc
					dna_str=blast_fna_map[blast_desc]
					dna_str=re.sub(r'\.','',dna_str)
					blast_writer.write(desc_str+"\n"+dna_str)
					if(rec_num==num_descs-1):
						pass
					else:
						blast_writer.write("\n")
				blast_writer.close()
					
				

	def blastFormatFNAInRefDirSetDirs(self,makeblastdbbin):
		organisms=self.getOrganismList()
		for organism in organisms:
			rds_base=self.db_base+"/"+organism+"/ReferenceDirectorySet/"
			blastFormatFNAInDir(rds_base,makeblastdbbin)

	#return the organism list
	def getOrganismList(self,fromHardCode=True):
		if(fromHardCode):
			#get from a hard-coded list in this file
			return self.ol
		else:
			#get downloaded organism!
			thedir=self.db_base
			org_list=list()
			total_list=[ name for name in os.listdir(thedir) if os.path.isdir(os.path.join(thedir, name)) ]
			print "total_list is ",total_list
			search_and_avoid=["\.py","down","\.pkl","\.sh","\.zip"]
			for tl in total_list:
				tls=str(tl.strip())
				if(tls.startswith("www.") or tls.startswith("ftp.")):
					pass
				matched_no_regex=True
				for s in search_and_avoid:
					if(re.search(s,tsl,re.IGNORECASE)):
						matched_no_regex=False
				if(matched_no_regex):
					org_list.append(tl.strip())
			return org_list



	#return base directory
	def getBaseDir(self):
		return self.db_base

	#return base directory alias
	def getDirBase(self):
		return self.getBaseDir()

	#download gene tables and reference directory sets from imgt
	def download_imgt_RefDirSeqs_AndGeneTables_HumanAndMouse(self,unconditionalForceReplace=False):
		print "in download_imgt_RefDirSeqs_AndGeneTables_HumanAndMouse"
		base=self.db_base
		organisms=self.getOrganismList(True)
		print "To download for ",organisms
		for organism in organisms:
			#do all organisms
			loci=get_loci_list()
			print "To download for ",loci
			for locus in loci:
				#do all 17 groups
				print "Downloading",locus,"for",organism,"at",formatNiceDateTimeStamp(),"..."
				#first download and save the gene tables
				geneTableOrgName=organism
				GeneTablesURLs=formGeneTableURLs(geneTableOrgName,locus)		
				#download each regular table and orphon table and write to file
				regularURL=GeneTablesURLs[0]
				orphonURL=GeneTablesURLs[1]
				geneTablesBase=base+"/"+organism+"/GeneTables"
				if(not(os.path.isdir(geneTablesBase))):
					os.makedirs(geneTablesBase)
				regularTablePath=geneTablesBase+"/"+locus+".html"
				if(not(os.path.exists(regularTablePath)) or unconditionalForceReplace==True):
					print "Gene table",locus,"for organism",organism,"not found or force replace set to true...so downloading it...."
					print "Downloading gene table",locus,"for organism",organism,"from URL=",regularURL," saving to",regularTablePath
					downloadURLToLocalFileAssumingDirectoryExists(regularURL,regularTablePath)
				orphonTablePath=regularTablePath+".orphons.html"
				if(not(os.path.exists(orphonTablePath)) or unconditionalForceReplace==True):
					print "Orphon gene table",locus,"for organism",organism,"not found, so downloading it..."
					print "Downloading orphon gene table",locus,"for organism",organism,"from URL=",orphonURL,"and saving to",orphonTablePath
					downloadURLToLocalFileAssumingDirectoryExists(orphonURL,orphonTablePath)
				#download the reference directory
				refDirBase=geneTablesBase=base+"/"+organism+"/ReferenceDirectorySet"
				if(not(os.path.isdir(refDirBase))):
					os.makedirs(refDirBase)
				refDirFile=refDirBase+"/"+locus+".html"
				refDirOrgName=organism
				if(refDirOrgName=="human"):
					#the ref dir URL won't take 'human', it needs 'Homo+sapiens' instead! :(
					refDirOrgName="Homo+sapiens"
				refDirURL=formRefDirURL(refDirOrgName,locus)
				if(not(os.path.exists(refDirFile)) or unconditionalForceReplace==True):
					print "Downloading reference directory set ",locus,"for organism",organism,"and saving to",orphonTablePath			
					downloadURLToLocalFileAssumingDirectoryExists(refDirURL,refDirFile)
					refDirFastaFile=refDirFile+".fna"
					localRefURL="file://"+refDirFile
					fastaString=downloadRefDirFasta(locus,refDirOrgName,localRefURL)
					writeStringToFilePathAssumingDirectoryExists(fastaString,refDirFastaFile)
			

	#download from IMGT
	def buildAndExecuteWGETDownloadScript(self):
		if(not(os.path.isdir(self.getBaseDir()))):
			print "ERROR, failed to find directory ",self.getBaseDir(),"!"
			print "Skipping download of imgt.org annotations/database files!"
			return
		refDBURL="http://www.imgt.org/download/"
		wgetCMD="cd "+self.db_base+"\n"
		wgetCMD+="/usr/bin/wget -r -np "+refDBURL+"GENE-DB/ "+refDBURL+"/LIGM-DB/\n"
		#we're not using VBASE any more!
		#wgetCMD+="/usr/bin/wget -m http://www.vbase2.org\n"
		#vbase_down="www.vbase2.org"
		#don't download these fetch fasta from the data record queries
		#down_human_vbase_cmd="/usr/bin/wget -O "+vbase_down+"/humanall.fasta http://www.vbase2.org/download/humanall.fasta"
		#down_mouse_vbase_cmd="/usr/bin/wget -O "+vbase_down+"/mouseall.fasta http://www.vbase2.org/download/mouseall.fasta"
		#wgetCMD+="if [ -d \""+vbase_down+"\" ] ; then "+down_human_vbase_cmd+" ; "+down_mouse_vbase_cmd+" ; else echo \"APPARENT ERROR IN DOWNLOADING VBASE!\" ; fi ;\n"
		uncomp_cmd="echo \"Now searching for .Z compressed files to uncompress ...\" ; for COMPRESSED in `find "+str(self.db_base)+"|grep -P '\.Z$'` ; do UNCOMPRESSED=`echo $COMPRESSED|sed -r \"s/\.Z//gi\"` ;    echo \"Found compressed file $COMPRESSED ... to uncompress it to $UNCOMPRESSED ...\" ; echo \"USING command uncompress -c $COMPRESSED > $UNCOMPRESSED\" ; uncompress -c $COMPRESSED > $UNCOMPRESSED ; done ;\n"
		wgetCMD+=uncomp_cmd
		wgetScriptPath=self.db_base+"/wgetscript.sh"
		wgetScriptOutLog=wgetScriptPath+".log.out"
		wgetScriptErrLog=wgetScriptPath+".log.err"
		write_temp_bash_script(wgetCMD,wgetScriptPath)
		execute_bash_script(wgetScriptPath,outPath=wgetScriptOutLog,errPath=wgetScriptErrLog)
	


	#given a full fasta descriptor, get the record from IMGT.dat
	#note that the descriptor should not have the ">" at the beginning
	def extractIMGTDatRecordUsingRefDirSetDescriptor(self,descriptor,biopythonRec=False):
		if(self.db_base==None):
			raise Exception("Error, db_base is not, must initialize first!")
		pieces=descriptor.split("|")
		#BN000872|IGHV5-9-1*02|Mus musculus_C57BL/6|F|V-REGION|2334745..2335041|294 nt|1| | | | |294+24=318| | |
		#print "got pieces ",pieces
		accession=pieces[0]
		#print "accession=",accession
		ss=self.getStartStopFromIndexGivenAccession(accession)
		#print "got start/stop : ",ss
		if(len(ss)==2):
			#regular accession
			start=ss[0]
			stop=ss[1]
			#return self.fetchBioPythonRecFromDat(start,stop,biopythonRec)
			return self.fetchRecFromDat(start,stop,biopythonRec)
		else:
			#irregular accession, use descriptor and index to find the correct accession
			raise Exception("Address irregular descriptor....")
			accession_rel_re=re.compile(r'^(\d+)\.+(\d+)')
			accession_rel=pieces[5]
			re_res=re.search(accession_rel_re,accession_rel)
			if(re_res):
				d1=re_res.group(1)
				d2=re_res.group(2)
				avg=(d1+d2)/2
				indirect_accession=accession
				accession_rel=pieces[5]
				index_reader=open(indexPath,'r')
				possible_accessions=list()
				for line in index_reader:
					line_pieces=line.split('\t')
					if(line_pieces[0]==indirect_accession):
						possible_accessions.append(line_pieces[1])
					else:
						pass
				#now, go through possible accessions and see which one is in range!
				return ""
			else:
				pass
				return ""




	#read index into dict/map
	def cacheIndex(self,indexPath=None,existingCache=None):
		if(not(self.accession_start_stop_map==None)):
			#it's already initialized
			return
		if(self.indexPath is None):
			self.indexPath=str(str(self.imgt_dat_path)+str(self.db_idx_extension))
		#print "Cacheing index for imgt.dat file ",self.imgt_dat_path
		if(not(os.path.exists(str(self.indexPath)))):
			#print "Creating the index",str(self.indexPath)," first because it doesn't exist..."
			self.indexIMGTDatFile(self.imgt_dat_path,self.indexPath)
		else:
			#print "The index file ",str(self.indexPath)," was found, so no need to re-create it...."
			pass
		if(not(existingCache==None)):
			if(self.accession_start_stop_map==None):
				self.accession_start_stop_map=dict()
			self.accession_start_stop_map=merge_maps(self.accession_start_stop_map,existingCache)
		else:
			self.accession_start_stop_map=dict()
		idxReader=open(self.indexPath,'r')
		for line in idxReader:
			line=line.strip()
			pieces=line.split("\t")
			accession=pieces[0]
			if(len(pieces)==3):
				ss=[pieces[1],pieces[2]]
			else:
				ss=[pieces[1]]
			self.accession_start_stop_map[accession]=ss
		idxReader.close()


	#get the IMGT record given an allele name
	def getIMGTDatGivenAllele(self,a,biopythonrec=False,org="human"):
		#print "passed : ",a," with org="+str(org)
		descriptor=self.extractDescriptorLine(a,org)
		#print "got descriptor = ",descriptor
		imgtDAT=self.extractIMGTDatRecordUsingRefDirSetDescriptor(descriptor,biopythonrec)
		return imgtDAT



	#get start/stop from index given accession
	def getStartStopFromIndexGivenAccession(self,a):
		if(self.accession_start_stop_map==None):
			self.cacheIndex(self.imgt_dat_path+self.db_idx_extension)
		if(a in self.accession_start_stop_map):
			return self.accession_start_stop_map[a]
		else:
			pass 
		

	#given a complete descriptor and organism, fetch the corresponding reference directory set sequence
	def getRefDirSetFNAGivenCompleteDescriptor(self,descriptor,organism):
		#print "in getRefDirSetFNAGivenCompleteDescriptor with desc='"+descriptor+"' org=",organism
		if(self.ref_dir_set_desc_seqs_map==None):
			self.ref_dir_set_desc_seqs_map=dict()
		if(descriptor in self.ref_dir_set_desc_seqs_map):
			#print "using lookup in getRefDirSetFNAGivenCompleteDescriptor"
			#sys.exit(0)
			return self.ref_dir_set_desc_seqs_map[descriptor]
		myloci=get_loci_list()
		for locus in myloci:
			html_fna_path=self.db_base+"/"+organism+"/ReferenceDirectorySet/"+locus+".html.fna"
			fasta_recs=read_fasta_file_into_map(html_fna_path)
			for fasta_desc in fasta_recs:
				self.ref_dir_set_desc_seqs_map[fasta_desc]=fasta_recs[fasta_desc]
		if(descriptor in self.ref_dir_set_desc_seqs_map):
			return self.ref_dir_set_desc_seqs_map[descriptor]
		else:
			raise Exception("Error, descriptor "+descriptor+" points to a non-existent reference directory set sequence under "+organism+"???")

	#get the sequence optionally removing gaps
	def getRefDirSetFNASeqGivenOrgAndAllele(self,allele_name,organism,removeGaps=True):
		#get the descriptor
		subject_descriptor=self.extractDescriptorLine(allele_name,organism)
		#use the descriptor to get the sequence
		subject_sequence=self.getRefDirSetFNAGivenCompleteDescriptor(subject_descriptor,organism)
		if(removeGaps):
			repPattern=re.compile(r'[^A-Za-z]')
			subject_sequence=re.sub(repPattern,"",subject_sequence)
		return subject_sequence



	#given an allele name and an organism string, extract the fasta descriptor with the specified allele name
	#use dictionary for cache purposes
	def extractDescriptorLine(self,allele_name,org="human"):
		#print "inside EDL allele_name=",allele_name," org=",org
		#sys.exit(0)
		#this little code here does a cache lookup
		if(not(self.org_allele_name_desc_map==None)):
			#print "using EDL dict to see if org=",org," is in it...."
			if(org in self.org_allele_name_desc_map):
				if(allele_name in self.org_allele_name_desc_map[org]):
					#print "Using cache lookup for EDL with org=",org,"and to return ",self.org_allele_name_desc_map[org][allele_name]
					#sys.exit(0)
					return self.org_allele_name_desc_map[org][allele_name]
				else:
					#print "INNermost EDL cache test fails"
					pass
			else:
				#print "org ain't in EDL map!"
				pass
		else:
			#print "initing EDL dict..."
			self.org_allele_name_desc_map=dict()
		#sys.exit(0)
		if(self.db_base==None):
			#self.db_base=self.db_base
			raise Exception("Error, db_base not set! Did you initialize???")
		org_dir=self.db_base+"/"+org
		to_be_returned=None
		if(os.path.isdir(org_dir)):
			fna_glob_str=org_dir+"/ReferenceDirectorySet/*.html.fna"
			fna_files=glob.glob(fna_glob_str)
			for fna_file in fna_files:
				fna_reader=open(fna_file,'r')
				for fna_line in fna_reader:
					if(fna_line.startswith(">")):
						descriptor=fna_line[1:]
						if(not(org in self.org_allele_name_desc_map)):
							self.org_allele_name_desc_map[org]=dict()
						pieces=descriptor.split("|")
						descriptor_allele=pieces[1]
						if(descriptor_allele.strip()==allele_name.strip()):
							to_be_returned=descriptor.strip()
						self.org_allele_name_desc_map[org][descriptor_allele.strip()]=descriptor.strip()
			if(not(to_be_returned==None)):
				return to_be_returned
			else:
				raise Exception("Error, descriptor with allele name = '"+str(allele_name)+"' not found under "+str(self.db_base)+" for organism = "+str(org))
		else:
			raise Exception("Error, invalid organism="+str(org)+", its directory doesn't exist under"+str(db_base)+"!")





	#fetch a record given position interval from the imgt.dat file
	def fetchRecFromDat(self,start,stop,biopython=False,idxpath=None):
		if(idxpath==None):
			idxpath=self.imgt_dat_path
		#print "i want to open ",idxpath
		if(not(stop>start)):
			return ""
		reader=open(idxpath,'r')
		reader.seek(int(start))
		if(biopython):
			records=SeqIO.parse(reader,"imgt")
			for record in records:
				my_rec=record
				reader.close()
				return my_rec
		data=reader.read(int(stop)-int(start))
		reader.close()
		return data

	#given a record from imgt.dat, find the first region interval
	def getRefVRegionInterval(self,data,region_name):
		lines=data.split("\t")
		for line in lines:
			#FT   CDR3-IMGT           371..412
			reg_regex="^FT\s+"+region_name+"[^\s]*\s+<?(\d+)\.+(\d+)>?\s*$"
			search_res=re.search(reg_regex,line)
			if(search_res):
				start=search_res.group(1)
				end=search_res.group(2)
				return [start,end]
		return None

	#index the imgt.dat file
	def indexIMGTDatFile(self,filepath=None,indexfile=None):
		if(filepath==None):
			filepath=self.db_base+"/"+self.imgt_dat_rel_path
		if(indexfile==None):
			indexfile=filepath+self.db_idx_extension
		print "Creating index file from ",filepath," ... writing index to ",indexfile
		reader=open(filepath,'r')
		acc_re=re.compile(r'^ID\s+([A-Z0-9]+)[^A-Z0-9]+')
		embl_tpa_re=re.compile(r'^DR\s+EMBL\-TPA;\s+([^\s]+)\.\s*$')
		current_embl_tpa=None
		current_accession=None
		rec_start=None
		rec_end=None
		index_file=open(indexfile,'w')
		rec_num=0
		flag=True
		while(flag):
			#line=line.strip()
			line=reader.readline()
			if(line):
				rs=re.search(acc_re,line)
				es=re.search(embl_tpa_re,line)
				if(rs):
					current_accession=rs.group(1)
					rec_start=reader.tell()-len(line)
					if(self.accession_dat_file_map==None):
						self.accession_dat_file_map=dict()
					self.accession_dat_file_map[current_accession]=filepath
				elif(es):
					current_embl_tpa=es.group(1)
				elif(line.startswith("//")):
					rec_end=reader.tell()-1
					index_file.write(current_accession+"\t"+str(rec_start)+"\t"+str(rec_end)+"\n")
					if(not(current_embl_tpa==None)):
						#index_file.write(current_embl_tpa+"\t"+str(rec_start)+"\t"+str(rec_end)+"\n")
						index_file.write(current_embl_tpa+"\t"+current_accession+"\n");
					current_embl_tpa=None
			else:
				flag=False
		index_file.close()	
	





def test():
	pass
	mydb=imgt_db("/home/data/DATABASE/01_22_2014/")
	print "the db is ",mydb.db_base
	#datPath="/home/data/DATABASE/01_22_2014/www.imgt.org/download/LIGM-DB/imgt.dat"
	#datIndexPath=datPath+".acc_idx"
	#print "Reading file",datPath
	#indexIMGTDatFile(datPath,datIndexPath)
	#print "Wrote index file",datIndexPath
	#testIdx(datPath,datIndexPath)
	#vtd=fetchRecFromDat(datPath,761609274,761613382)
	#print "''''''"+vtd+"''''''''"
	#jtd=fetchRecFromDat(datPath,741876366,741888356)
	#print "''''''"+jtd+"''''''''"
	
	##download_imgt_RefDirSeqs_AndGeneTables_HumanAndMouse("/tmp/imgt_down","/tmp/del_me")
	#analyze_download_dir_forVDJserver("/tmp/imgt_down",None,None,None)
	#hier_data=loadPickleDataAndMakeIfNotAvailable("/tmp/imgt_down")
	#organism_hierarchy=hier_data[0]
	#clone_names_by_org=hier_data[1]
	#alleleNames=get_list_of_alleles_appearing_in_tree(organism_hierarchy['human'])
	#print "THESE ARE CLONE NAMES : "
	#print yaml.dump(clone_names_by_org, default_flow_style=False)
	#batchMultistepSegmentsAndOrganisms("/tmp/imgt_down")
	#igblast_blast_map_multistep(nonExistentMapDir,query,refDirSetFNAList,allPPath,workDir,clone_map,alleleList):
	#blast_dir="/tmp/imgt_down/human/BLAST_MAP_V"
	#query="/usr/local/igblast_from_lonestar/database/human_gl_V.fna"
	#refdirlist=[
	#	"/tmp/imgt_down/human/ReferenceDirectorySet/IGHV.html.fna",
	#	"/tmp/imgt_down/human/ReferenceDirectorySet/IGKV.html.fna",
	#	"/tmp/imgt_down/human/ReferenceDirectorySet/IGLV.html.fna"
	#	]
	#allPPath="/tmp/imgt_down/www.imgt.org/download/GENE-DB/IMGTGENEDB-ReferenceSequences.fasta-nt-WithoutGaps-F+ORF+allP"
	#igblast_blast_map_multistep(blast_dir,query,refdirlist,allPPath,clone_names_by_org,alleleNames,"homo ")


	#test_map="/tmp/imgt_down/human/BLAST_MAP_V/test.map"
	#test_unmapped="/tmp/imgt_down/human/BLAST_MAP_V/test.unmapped"
	#test_query="/tmp/imgt_down/human/BLAST_MAP_V/query.fna"
	#test_db="/tmp/imgt_down/human/BLAST_MAP_V/db.test.fna"
	#igblast_map_FA(test_query,test_db,test_map,test_unmapped,clone_names_by_org['human'],alleleNames)
	#print "Running test...."
	#download_imgt_RefDirSeqs_AndGeneTables_HumanAndMouse("/tmp/imgt_down","/tmp/del_me")
	#hier_data=analyze_download_dir_forVDJserver("/tmp/imgt_down",None,None,None)
	#pickleFilePath="/tmp/imgt_down"+"/hierarchy_data.pkl"
	#if(os.path.exists(pickleFilePath)):
	#	hier_data=pickleRead(pickleFilePath)
	#else:
	#	pickleWrite(pickleFilePath,hier_data)
	#organism_hierarchy=hier_data[0]
	#clone_names_by_org=hier_data[1]
	#
	#print "GOT HIERARCHY : ",
	#prettyPrintTree(organism_hierarchy)
	#
	#JSON=get_count_JSON_ofVDJ("/home/esalina2/round1/all_data.processed.r0.small.fna.imgt.db","/tmp/imgt_down","human")
	#print "THIS IS THE JSON:"
	#print JSON
	#clone_names_by_org=get_clone_names_by_org_map_from_base_dir("/tmp/imgt_down")
	#organism_list=getOrganismList()
	
	#base_dir="/tmp/imgt_down/"
	#buildAndExecuteWGETDownloadScript(base_dir)
	#org_to_glob_db_map=dict()
	#org_to_glob_db_map['human']="/usr/local/igblast_from_lonestar/database/human_gl_"
	#org_to_glob_db_map['Mus_musculus']="/usr/local/igblast_from_lonestar/database/mouse_gl_"
	#imgtfastaPath=base_dir+"/www.imgt.org/download/GENE-DB/IMGTGENEDB-ReferenceSequences.fasta-nt-WithoutGaps-F+ORF+allP"
	#partitionIMGTFastaInDirByFile(imgtfastaPath)
	#igblast_imgt_mapping(base_dir,org_to_glob_db_map,imgtfastaPath,organism_hierarchy)
	


#	igblast_glob="/usr/local/igblast_from_lonestar/database/human_gl_*.fna"
#	ref_glob="/tmp/imgt_down/human/ReferenceDirectorySet/IG*.fna"
#	igblast_map(igblast_glob,ref_glob,"/tmp/imgt_down/human/BLAST_MAP_IG")
#	igblast_glob="/usr/local/igblast_from_lonestar/database/mouse_gl_*.fna"
#	ref_base="/tmp/imgt_down/Mus_musculus/ReferenceDirectorySet/IG*.fna"
#	igblast_map(igblast_glob,ref_glob,"/tmp/imgt_down/Mus_musculus/BLAST_MAP_IG")
	#annodbDir="/tmp/imgt_down/region_annotation_igblast"
	#blastVList=["/usr/local/igblast_from_lonestar/database/human_gl_V","/usr/local/igblast_from_lonestar/database/mouse_gl_V"]
	#auxBase="/usr/local/igblast_lonestar_tacc/optional_file/"
	#makeIGBLASTVRegionDatabase(annodbDir,blastVList,auxBase)
	#total_tree=get_total_tree(organism_hierarchy['human'],'IGHD',counts_map)
	#JSON=jsonify_hierarchy(organism_hierarchy['human'],'human',counts_map)
	#print "THIS IS RAW\n"
	#print JSON
	#print "\n\nTHIS IS NICE\n"
	#json.dumps(JSON,index=8)
	#analyze_download_dir_forVDJserver(base_dir,countsMap=None,specifiedOrganism=None,specifiedLoucs=None):
	#raise Exception('spam', 'eggs')
#	ref_sname="Homo+sapiens"
#	gt_sname="human"
#	loci=get_loci_list()
#	species_names_ref=["Homo+sapiens","Mus_musculus"]
#	speces_names_tbl=["human","Mus_musculus"]
#	
#	for species_index in range(len(species_names_ref)):
#		ref_sname=species_names_ref[species_index]
#		gt_sname=speces_names_tbl[species_index]
#		for locus in loci:
#			print "\n\n\n\nANALYZING WITH LOCUS=",locus," AND ORGANISM="+(ref_sname)+"/"+gt_sname+"\n"
#			fastaString=downloadRefDirFasta(locus,ref_sname)
#			print "Got a fasta string ",fastaString
#			#print "class=",type(fastaString)
#			fastaList=read_fasta_string(fastaString)
#			fastaMap=read_fasta_into_map(fastaList)
#			geneTableURLS=formGeneTableURLs(gt_sname,locus)
#			print "Got URLs : ",geneTableURLS
#			regURL=geneTableURLS[0]
#			orpURL=geneTableURLS[1]
#			#regURL="file:///home/data/vdj_server/igblast_routines/index.php?section=LocusGenes&repertoire=genetable&species=human&group=IGHD"
#			#orpURL="file:///home/data/vdj_server/igblast_routines/index.php?section=LocusGenes&repertoire=genetable&species=human&group=IGHD&orphon"
#			reg_hier=hierarchyTreeFromGenetableURL(regURL,locus)
#			print "REGULAR HIERARCHY : "
#			prettyPrintTree(reg_hier)
#			full_hier=hierarchyTreeFromGenetableURL(orpURL,locus,reg_hier)
#			print "FULL HIERARCHY : "
#			prettyPrintTree(full_hier)
#			listOfTreeAlleles=get_list_of_alleles_appearing_in_tree(full_hier)
#			print "A LIST OF ALLELES FROM THE HIERARCHY : ",
#			print listOfTreeAlleles
#			listOfTreeAlleles.sort()
#			print "A SORTED OF ALLELES : ",
#			print listOfTreeAlleles
#			fastaListOfNames=getIMGTNameListFromFastaMap(fastaMap)
#			fastaListOfNames.sort()
#			print "Extracted a list of FASTA NAMES :",fastaListOfNames
#			allAlleles=areAllItemsInListIMGTAlleles(fastaListOfNames)
#			print "Allele status : ",allAlleles
#			setSameStats=(set(fastaListOfNames) == set(listOfTreeAlleles))
#			print "\n\nHIERARCHY ALLELES : "
#			printList(listOfTreeAlleles)
#			print "\n\nFASTA ALLELES : "
#			printList(fastaListOfNames)
#			if setSameStats:
#				print "The fasta/RefDirNames ARE the same as the hierarchy allele names!!! :)"
#			else:
#				print "SAD the fasta/RefDirNames ARE different from the hierarchy allele names!!! :("
#			briefSetDiff(fastaListOfNames,listOfTreeAlleles,"fasta alleles "+ref_sname,"tree alleles "+gt_sname)


if (__name__=="__main__"):
	import sys
	test()


