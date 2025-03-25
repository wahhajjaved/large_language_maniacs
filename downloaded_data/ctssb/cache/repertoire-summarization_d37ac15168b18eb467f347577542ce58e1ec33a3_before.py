#!/usr/bin/env python

from utils import *
from alignment import *
from char_utils import *
from segment_utils import getVRegionStartAndStopGivenRefData,IncrementMapWrapper,getTheFrameForThisReferenceAtThisPosition,getTheFrameForThisJReferenceAtThisPosition
from igblast_parse import rev_comp_dna

#make an instance of the analyzer
#print "INIT IN CODON_ANALYSIS...."
AGSCodonTranslator=CodonAnalysis()
#print "FINISH INIT IN CODON_ANALYSIS...."

#class for codon counting
#currently for IGHV4 only
class codonCounter:

	gap_kabat=list()
	kabat=list()
	region_kabat=list()
	chothia=list()
	gap_chothia=list()
	region_chothia=list()
	allowGaps=False
	numberingMapCache=None
	internalAnalyzer=None
	kabat_chothia_trans=None
	queriesWithRM=0
	sampleRepMuts=IncrementMapWrapper()
	ags6RepMuts=IncrementMapWrapper()
	ags5RepMuts=IncrementMapWrapper()
	sampleRepNucMuts=IncrementMapWrapper()
	NMORepNucMuts=IncrementMapWrapper()
	name=None



	def increment_ags6_rep_muts(self,numbered_pos):
		self.ags6RepMuts.increment(numbered_pos)


	def increment_ags5_rep_muts(self,numbered_pos):
		self.ags5RepMuts.increment(numbered_pos)		


	def get_ags6_nums(self):
		ags6_nums=["31B","40","56","57","81","89"]
		return ags6_nums

	

	def get_ags5_nums(self):
		ags5_nums=["31B","40","56","57","81"]
		return ags5_nums


	def get_nmo_nums(self):
		nmo_nums=["36","39","45","46","50","59","61","65","67","70","86","90"]
		return nmo_nums



	def generateSampleAGSSum(self,):
		ags_score=self.computeAGS()
		summ_str="AGS Score\t"+str(ags_score)
			

	def computeNMO(self):
		if(self.queriesWithRM==0):
			#avoid division by zero err
			return None
		NMO_num=float(self.computeSampNMOTot())
		NMO_dnm=float(self.queriesWithRM)
		NMO=(NMO_num/NMO_dnm)*float(100.0)
		return NMO



	def computeSampNMOTot(self):
		sampNMOTot=0
		for num in self.NMORepNucMuts.get_map():
			sampNMOTot+=self.NMORepNucMuts.get_map()[num]
		return sampNMOTot


	def computeSampTotRM(self):
		sampTot=0
		for num in self.sampleRepMuts.get_map():
			sampTot+=self.sampleRepMuts.get_map()[num]
		return sampTot


	def computeAGS6TotRM(self):
		sampAGSTot=0
		for num in self.ags6RepMuts.get_map():
			sampAGSTot+=self.ags6RepMuts.get_map()[num]
		return sampAGSTot		


	def computeAGS5TotRM(self):
		sampAGSTot=0
		for num in self.ags5RepMuts.get_map():
			sampAGSTot+=self.ags5RepMuts.get_map()[num]
		return sampAGSTot



	def computeAGS(self):
		#sample total of RM
		sampTot=float(self.computeSampTotRM())
		if(sampTot<=0):
			#avoid division by zero error
			return None
		#AGS total of RM
		sampAGSTot=float(self.computeAGS6TotRM())
		pct_ags6=(sampAGSTot/sampTot)*100.0
		#print "pct_ags6=",pct_ags6
		ags_numerator=pct_ags6-1.6*6.0
		#print "ags_numerator=",ags_numerator
		ags_denominator=0.9
		ags_score=ags_numerator/ags_denominator
		#print "ags_score",ags_score
		return ags_score
		#1) AGS6 score   (     RMAGS6  -   1.6     ) /  
		#2) AGS6 RM COUNT
		#3) TOT RM COUNT


	def computeAGS5(self):
		sampTot=float(self.computeSampTotRM())
		if(sampTot<=0):
			#avoid division by zero error
			return None
		sampAGSTot=float(self.computeAGS5TotRM())
		pct_ags5=(sampAGSTot/sampTot)*100.0
		ags_numerator=pct_ags5-1.6*5.0
		ags_denominator=0.9
		ags_score=ags_numerator/ags_denominator
		return ags_score



	def appearsToBeNumberedMut(self,nm):
		nmRe=re.compile(r'^([A-Z\*])([0-9][0-9][ABC]?)([A-Z\*])$')
		nmmo=re.search(nmRe,nm)
		if(nmmo):
			mut_from=nmmo.group(1)
			mut_pos=nmmo.group(2)
			mut_to=nmmo.group(3)
			return [str(mut_from),str(mut_pos),str(mut_to)]
		else:
			return False
		



	#load kabat->chotia translation
	def initKabatChotiaTrans(self,tableFilePath):
		self.kabat_chothia_trans=dict()
		
		if(not(os.path.exists(tableFilePath))):
			sys.exit("ERROR, FAILED TO FIND FILE",tableFilePath," of codon numbering data!")
		with open(tableFilePath, 'r') as f:
			data=f.read()
		codon_pos_re=re.compile('^\d+[A-Z]$',re.IGNORECASE)
		lines=data.split('\n')
		for line_num in range(len(lines)):
			if(line_num!=0):
				pieces=lines[line_num].split('\t')
				if(len(pieces)>=4):
					#print lines[line_num]
					kabat_num=pieces[1]
					chothia_num=pieces[3]
					codon_pos_result_kab=str(codon_pos_re.search(kabat_num))
					codon_pos_result_cht=str(codon_pos_re.search(kabat_num))
					if(codon_pos_result_kab and codon_pos_result_cht):
						self.kabat_chothia_trans[kabat_num.upper().strip()]=chothia_num.upper().strip()


	#perform KABAT->CHOTHIA numbering translation
	def kabatToChothia(self,pos):
		proper_key=str(pos).upper().strip()
		if(proper_key in self.kabat_chothia_trans):
			return self.kabat_chothia_trans[proper_key]
		else:
			return "X"
		
	


	def computePathToCodonTableFile(self):
		#path to script
		ownScriptPath=sys.argv[0]
		#its dir
		containingDir=os.path.dirname(ownScriptPath)
		#get relative path to codon data
		tableFilePath=containingDir+"/codon_data/codon_pos_IGHV4"
		return tableFilePath


	#init
	#def __init__(self,pos_file_path,init_allowGaps=False):
	def __init__(self,init_name,init_allowGaps=False):
		self.name=init_name
		#currently reads a TSV
		#6 fields
		#gap order	KABAT	REGION_KABAT	CHOTHIA	gap order	REGION_CHOTHIA
		self.queriesWithRM=0
		#reader=open(pos_file_path,'r')
		#line_num=1
		#for line in reader:
		#	#print line
		#	temp=line
		#	pieces=temp.split('\t')
		#	for i in range(len(pieces)):
		#		pieces[i]=pieces[i].strip()
		#	if(line_num!=1):
		#		#ignore header line
		#		self.gap_kabat.append(pieces[0])
		#		self.kabat.append(pieces[1])
		#		self.region_kabat.append(pieces[2])
		#		self.chothia.append(pieces[3])
		#		self.gap_chothia.append(pieces[4])
		#		self.region_chothia.append(pieces[5])
		#	line_num+=1
		#reader.close()
		#self.allowGaps=init_allowGaps
		self.internalAnalyzer=CodonAnalysis()
		#tableFilePath=self.computePathToCodonTableFile()
		#self.initKabatChotiaTrans(tableFilePath)



	def getBPFromCodonList(self,codon_list,removeGaps=False):
		rbp=""
		for codon in codon_list:
			for bp in codon:
				if(bp=="-" and removeGaps):
					pass
				else:
					rbp+=bp
		return rbp




	#see if valid on the region ; making sure it's of a valid length
	def validate_region(self,region_info,num_aa_min,num_amino_max):
		if(self.allowGaps):
			#unimp!
			sys.exit(0)
		q_aa=region_info.getCharMap()['AA']
		q_codons=region_info.getCharMap()['nucleotide read']
		s_aa=region_info.getCharMap()['AA_ref']
		s_codons=region_info.getCharMap()['subject_read']
		join_str=""
		q_bp=self.getBPFromCodonList(q_codons)
		s_bp=self.getBPFromCodonList(s_codons)
		actual_q_aa=self.getBPFromCodonList(q_aa)
		actual_s_aa=self.getBPFromCodonList(s_aa)
		if(len(q_bp)!=len(s_bp) and not(self.allowGaps)):
			return False
		if(len(actual_q_aa)!=len(actual_s_aa)):
			return False
		if(len(q_aa)!=len(s_aa)):
			return False
		if(num_aa_min<=len(q_aa) and len(q_aa)<=num_amino_max and len(actual_q_aa)==len(q_aa)):
			return True
		else:
			#too short or too long!
			#print "len=",len(q_aa),"too short or too long"
			return False


	#given a region, get the valid lengths possible in a list format
	#lengths in CODONs
	def getRegionValidLengths(self,reg_name):
		if(reg_name=="CDR1"):
			return [5,6,7]
		elif(reg_name=="FR2" or reg_name=="FWR2"):
			return [14]
		elif(reg_name=="CDR2"):
			return [16]   #all IGHV4 sequences have length=16 for CDR2 (52A,52B,52C are NOT used in IGHV4 ; 50-65 (inclusive) are used)
		elif(reg_name=="FWR3" or reg_name=="FR3"):
			#30 AND 82A,82B,and 83C are always present
			return [30]
		else:
			#invalid region
			print "INVALID REGION PASSED "+reg_name
			sys.exit(0)


	



	#given the information on the 4 regions (CDR1,FR2,CDR2,FR3), verify
	#that the alignment is suitable for acquisition of mutation counts
	def validate_regions_for_completenessLength(self,cdr1_info,fr2_info,cdr2_info,fr3_info):
		#truncation check (equals multiple of 3 check)
		#check for valid length (given is mult of 3)
		region_infos=list()
		region_infos.append(cdr1_info)
		region_infos.append(fr2_info)
		region_infos.append(cdr2_info)
		region_infos.append(fr3_info)
		regions_to_analyze=["CDR1","FR2","CDR2","FR3"]
		valid_flags=list()
		valid_on_all=True
		validityNote=""
		for ri in range(len(regions_to_analyze)):
			valid_lengths=self.getRegionValidLengths(regions_to_analyze[ri])
			valid_flag=self.validate_region(region_infos[ri],min(valid_lengths),max(valid_lengths))
			valid_flags.append(valid_flag)
			if(not(valid_flag)):
				valid_on_all=False
			else:
				pass				
				#sys.exit(0)
		validityNote="OK"		
		return [validityNote,valid_on_all]
		

	#given a region name and length, return the numbering
	def acquireNumberingMap(self,reg_name,reg_len):
		if(self.numberingMapCache==None):
			self.numberingMapCache=dict()
		if(reg_name+str(reg_len) in self.numberingMapCache):
			return self.numberingMapCache[reg_name+str(reg_len)]
		numbering=list()
		letters=["A","B","C"]
		l_pos=0
		if(reg_name=="CDR1"):
			if(reg_len==5):
				for p in range(31,36):
					numbering.append(str(p))
			elif(reg_len==6):
				new_nums=["31","31A","32","33","34","35"]
				for nn in new_nums:
					numbering.append(nn)
			elif(reg_len==7):
				new_nums=["31","31A","31B","32","33","34","35"]
				for nn in new_nums:
					numbering.append(nn)					
		elif(reg_name=="FR2" or reg_name=="FWR2"):
			for p in range(36,50):
				numbering.append(str(p))
		elif(reg_name=="CDR2"):
			for p in range(50,67):
				numbering.append(str(p))
		elif(reg_name=="FR3" or reg_name=="FWR3"):
			for p in range(66,83):
				numbering.append(str(p))
			for l in range(len(letters)):
				numbering.append("82"+str(letters[l]))
			for p in range(83,93):
				numbering.append(str(p))
		else:
			#invalid/unknown region!
			print "Error, unknown region ",reg_name,"!"
			sys.exit(0)
		self.numberingMapCache[reg_name+str(reg_len)]=numbering
		return self.numberingMapCache[reg_name+str(reg_len)]
			


	#from the 3 regions, aquire a mutation map
	def acquire_mutation_map(self,cdr1_info,fr2_info,cdr2_info,fr3_info):
		reg_names=["CDR1","FR2","CDR2","FR3"]
		reg_infos=[cdr1_info,fr2_info,cdr2_info,fr3_info]
		AA_map=list()
		codon_map=list()
		AA_silent_map=list()
		codon_silent_map=list()
		thisReadHadAtLeastOneRM=False
		for r in range(len(reg_names)):
			reg_info_map=reg_infos[r].getCharMap()
			numbering_list=self.acquireNumberingMap(reg_names[r],len(reg_info_map['AA']))
			q_codons=reg_info_map['nucleotide read']
			s_codons=reg_info_map['subject_read']
			q_aminos=reg_info_map['AA']
			s_aminos=reg_info_map['AA_ref']
			#print "\n\n\n"+reg_names[r]
			#print reg_infos[r].getName()
			#print reg_infos[r].getNiceString()
			#print "Q=",q_codons," TRX=",q_aminos
			#print "q AA len=",len(q_aminos)," q codon len=",len(q_codons)
			#print "S=",s_codons," TRX=",s_aminos
			#print "s AA len=",len(s_aminos)," s codon len=",len(s_codons)
			#print "The numbering : ",numbering_list
			for ci in range(len(q_codons)):
				if(s_codons[ci]!=q_codons[ci]):
					#mark a mutation in the numbering system
					numbered_pos=numbering_list[ci]
					ags6_nums=["31B","40","56","57","81","89"]
					ags5_nums=["31B","40","56","57","81"]
					nmo_nums=["36","39","45","46","50","59","61","65","67","70","86","90"]
					aaP=s_aminos[ci]+str(numbered_pos)+q_aminos[ci]
					cdP=s_codons[ci]+str(numbered_pos)+q_codons[ci]
					if(s_aminos[ci]!=q_aminos[ci]):
						thisReadHadAtLeastOneRM=True
						#print "incrementing a mutation at ",numbered_pos," in read ",cdr1_info.getName()
						self.sampleRepMuts.increment(numbered_pos)
						for bp in range(3):
							q_codon=q_codons[ci]
							qbp=q_codon[bp]
							s_codon=s_codons[ci]
							sbp=s_codon[bp]
							if(qbp!=sbp):
								self.sampleRepNucMuts.increment(numbered_pos)
								if(numbered_pos in nmo_nums):
									self.NMORepNucMuts.increment(numbered_pos)
						if(numbered_pos in ags6_nums):
							self.ags6RepMuts.increment(numbered_pos)
						if(numbered_pos in ags5_nums):
							self.ags5RepMuts.increment(numbered_pos)
						#record non-synonymous changes here
						#these changes are used in NMO/AGS formulas
						AA_map.append(aaP)
						codon_map.append(cdP)
					else:
						#record synonymous changes here
						#these changes are not used in either AGS or NMO computations
						#but may sometimes be desired to understand background mutations
						AA_silent_map.append(aaP)
						codon_silent_map.append(cdP)
				else:
					pass
		if(thisReadHadAtLeastOneRM):
			self.queriesWithRM+=1
		overall_map=dict()
		overall_map['codons']=codon_map
		overall_map['aminos']=AA_map
		overall_map['codons_silent']=codon_silent_map
		overall_map['aminos_silent']=AA_silent_map
		return overall_map
			


#given an IGHV4 allele (for human), return a hybrid
#interval with FR3 start in KABAT and FR3 end in IMGT
def getHumanHybridInterval(imgtdb_obj,ighv4allelename):
	if(imgtdb_obj==None or ighv4allelename==None):
		return [-1,-1]
	if(not(ighv4allelename.startswith("IGHV4"))):
		return [-1,-1]
	else:
		fr3_interval_kabat=getVRegionStartAndStopGivenRefData(ighv4allelename,"human",imgtdb_obj,"FR3","kabat")
		fr3_interval_imgt=getVRegionStartAndStopGivenRefData(ighv4allelename,"human",imgtdb_obj,"FR3","imgt")
		hybrid_interval=[fr3_interval_kabat[0],fr3_interval_imgt[1]]
		return hybrid_interval



#return a hybrid alignment
def extractHybridAlignment(vInfo,imgtdb_obj):
	v_qry_aln=vInfo['query seq']
	v_sbc_aln=vInfo['subject seq']
	q_from=int(vInfo['q. start'])
	q_to=int(vInfo['q. end'])
	s_from=int(vInfo['s. start'])
	s_to=int(vInfo['s. end'])
	v_aln=alignment(v_qry_aln,v_sbc_aln,q_from,q_to,s_from,s_to)
	hybrid_interval=getHumanHybridInterval(imgtdb_obj,vInfo['subject ids'])
	if(len(hybrid_interval)==2):
		if(hybrid_interval[0]!=(-1) and hybrid_interval[1]!=(-1)):
			hybrid_region_aln=v_aln.getSubAlnInc(hybrid_interval[0],hybrid_interval[1],"subject")
			init_frame=0 #since no gaps assume first bp has frame 0
			hybrid_region_aln.setSFM(init_frame)
			hybrid_region_aln.setName("KABAT.IMGT_hybrid_FR3_"+str(vInfo['query id']))
			hybrid_region_aln.characterize()
			return hybrid_region_aln
		else:
			return None
	else:
		return None






#get indel count from an info map
#return n>=0 if a btop found
#return -1 if no info or no btop found
def getNumberIndelsFromBTOPInInfo(info):
	if(not(info==None)):
		if('btop' in info):
			btop=info['btop']
			#print "EXTRACTED btop=",btop
			indel_count=getNumberIndelsFromBTOP(btop)
			#print "the count is ",indel_count
			return indel_count
		else:
			#"no btop avail"
			return -1
	else:
		#print "is none"
		return -1



#given v,d,j info maps return True if the seq should be 
#skipped due to indels
def shouldFilterOutByIndels(vInfo,dInfo,jInfo):
	if(getNumberIndelsFromBTOPInInfo(vInfo)==0 and getNumberIndelsFromBTOPInInfo(jInfo)==0 and getNumberIndelsFromBTOPInInfo(dInfo)<=0):
		shouldFilter=False
	else:
		shouldFilter=True
	return shouldFilter



#return true if the query (assumed to be gapless in the alignment)
#contains a stop codon in its translatoin
def diogenixGaplessStopCodonShouldFilter(vInfo,jInfo,imgtdb_obj,read_rec,organism):
	#assumed to be GAPLESS here!
	global AGSCodonTranslator
	s_start=vInfo['s. start']
	refName=vInfo['subject ids']
	s_start_frame=getTheFrameForThisReferenceAtThisPosition(refName,organism,imgtdb_obj,s_start)
	q_start=vInfo['q. start']
	q_start-=1
	if(s_start_frame!=0):
		q_start=q_start+(3-s_start_frame)
	q_seq_j_end=jInfo['q. end']
	q_seq_to_trans=str(read_rec.seq[q_start:q_seq_j_end])
	#print "prc totranslate is ",q_seq_to_trans
	if(vInfo['is_inverted']):
		q_seq_to_trans=rev_comp_dna(q_seq_to_trans)
	translation=AGSCodonTranslator.fastTransStr(q_seq_to_trans)
	#print "totranslate is ",q_seq_to_trans
	#print "The translation for ",read_rec.id," is ",translation
	if(translation.find("*")!=(-1)):
		#found a stop codon!
		return True
	else:
		return False
	




def diogenixGaplessVJRearrangementShouldFilter(vInfo,jInfo,imgtdb_obj,read_rec,organism,cdr3_map):
	if(vInfo==None or jInfo==None):
		#need valid data to test. return false in this case
		return False

	#First use CDR3 length to test productive rearrangment
	if(cdr3_map is not None):
		#print cdr3_map," is cdr3 map for ",read_rec.id
		if('imgt' in cdr3_map):
			imgt_cdr3_len=int(cdr3_map['imgt'])
			if(imgt_cdr3_len!=(-1)):
				if((imgt_cdr3_len%3)==0 ):
					#print "CDR3 length for ",read_rec.id," is divisble by 3....don't filter!"
					return False
				else:
					#print "CDR3 length for ",read_rec.id," is NOT  divisble by 3....filter!"
					return True
	#Second, if couldn't do that, then use V and J frame
	if(jInfo==None):
		#no J means no prod. rearrangment???
		return False
	s_start=vInfo['s. start']
	q_start=vInfo['q. start']
	refName=vInfo['subject ids']
	s_start_frame=getTheFrameForThisReferenceAtThisPosition(refName,organism,imgtdb_obj,s_start)
	q_start_frame=s_start_frame
	#print vInfo['query id']
	#print "q_start_frame (spos=",s_start,") ",q_start_frame
	q_end_j=jInfo['q. end']
	if(q_end_j<=q_start+3):
		#WAY TOO SHORT!
		return False
	else:
		j_end_j=jInfo['s. end']
		j_end_frame=getTheFrameForThisJReferenceAtThisPosition(jInfo['subject ids'],organism,imgtdb_obj,j_end_j)
		expected_frame_based_on_V=(q_start_frame+(q_end_j-q_start))%3
		#print "expected_frame_based_on_V=",expected_frame_based_on_V
		expected_frame_based_on_J=j_end_frame
		#print "expected_frame_based_on_J=",expected_frame_based_on_J
		if(expected_frame_based_on_J==expected_frame_based_on_V):
			#if both V and J impose the same frame, then the read should NOT be filtered
			return False
		else:
			return True


def passesPctHomologyFilter31To92(pct_filter,vInfo,imgtdb_obj,read_rec,organism,cdr3_map):
	ighv4allelename=vInfo['subject ids']
	ref_cdr1=getVRegionStartAndStopGivenRefData(ighv4allelename,"human",imgtdb_obj,"CDR1","kabat")
	ref_fr3=getVRegionStartAndStopGivenRefData(ighv4allelename,"human",imgtdb_obj,"FR3","imgt")
	if(ref_cdr1==None or ref_fr3==None):
		return False
	reg_start=ref_cdr1[0]
	reg_end=ref_fr3[1]
	#print "In 85P Using subject start/stop ",reg_start," and ",reg_end
	#print "vinfo is ",vInfo
	main_aln_obj=alignment(vInfo['query seq'],vInfo['subject seq'],vInfo['q. start'],vInfo['q. end'],vInfo['s. start'],vInfo['s. end'])
	#print "The main alignment is "
	#print main_aln_obj.getNiceString()
	alignment_of_interest=main_aln_obj.getSubAlnInc(reg_start,reg_end,"subject")
	#print "The alignment of interest is "
	#print alignment_of_interest.getNiceString()
	reg_char=alignment_of_interest.characterize()
	#print "reg char is ",reg_char
	pct_homology=float(reg_char['homology%'])
	#print "filter is ",pct_filter
	#print "score is ",pct_homology
	if(pct_homology<pct_filter):
		#print "to return false"
		#FALSE on dump
		return False
	else:
		#print "to return true"
		#TRUE on dump
		return True
	#sys.exit(0)
	

	



def annotationMutationMap(vInfo,dInfo,jInfo,alignment_output_queue,num_submitted_jobs,imgtdb_obj,myCodonCounter,organism,read_rec,cdr3_map,homology_filter_val):
	#perform codon mutation counting for IGHV4
	filterNote=""
	mutation_map=dict()
	mutation_map['aminos']=list()
	mutation_map['codons']=list()
	mutation_map['aminos_silent']=list()
	mutation_map['codons_silent']=list()
	eligibleForScoring=False
	get_res=0
	kabat_CDR1=None
	kabat_FR2=None
	kabat_CDR2=None
	hybrid_FR3=None
	while(get_res<num_submitted_jobs):
		region_alignment=alignment_output_queue.get()
		if(region_alignment is not None):
			#print "\n"
			#print "THE ALIGNMENT NAME '"+region_alignment.getName()+"'"
			#print read_rec.id
			#print region_alignment.getNiceString()
			if(region_alignment.getName().startswith("CDR1_kabat")):
				kabat_CDR1=region_alignment
			elif(region_alignment.getName().startswith("FR2_kabat")):
				kabat_FR2=region_alignment
			elif(region_alignment.getName().startswith("CDR2_kabat")):
				kabat_CDR2=region_alignment
			else:
				pass
		get_res+=1
	if(not(organism=="human")):
		return ["not human",mutation_map]
	if(vInfo is not None):
		#got V hit
		if('subject ids' in vInfo):
			#found subject in it
			if(vInfo['subject ids'].startswith("IGHV4")):
				#V hit found to be IGHV4
				get_res=0
				shouldFilterByIndel=shouldFilterOutByIndels(vInfo,dInfo,jInfo)
				#print "For read=",vInfo['query id']," the shouldFilterByIndel is ",shouldFilterByIndel
				if(shouldFilterByIndel):
					#print "NOTE "+read_rec.id+" filtered out by indels!"
					filterNote="Had Indels!"
					pass
				else:
					shouldFilterForStop=diogenixGaplessStopCodonShouldFilter(vInfo,jInfo,imgtdb_obj,read_rec,organism)
					if(not(shouldFilterForStop)):
						#did't find a stop codon!
						#cdr3 in frame and cdr3 has no stop codon new filter GOES HERE (new per william)
						#print "NOTE "+read_rec.id+" needs completeness testing..."
						shouldFilterprodFlag=diogenixGaplessVJRearrangementShouldFilter(vInfo,jInfo,imgtdb_obj,read_rec,organism,cdr3_map)
						#print "For ",read_rec.id," the prod VJ R flag is ",prodFlag
						if(not(shouldFilterprodFlag)):
							#go ahead and do mutation analysis
							hybrid_aln=extractHybridAlignment(vInfo,imgtdb_obj)
							if(hybrid_aln==None):
								#print "couldn't get a hybrid!"
								filterNote="Failure in hybrid alignment"
							else:
								#IGHV4, test regions for completeness and length
								completeRegionsFlags=myCodonCounter.validate_regions_for_completenessLength(kabat_CDR1,kabat_FR2,kabat_CDR2,hybrid_aln)
								completeRegionsNote=completeRegionsFlags[0]
								completeRegionsFlag=completeRegionsFlags[1]
								if(completeRegionsFlag):
									passesHomologyFilter=passesPctHomologyFilter31To92(homology_filter_val,vInfo,imgtdb_obj,read_rec,organism,cdr3_map)
									if(passesHomologyFilter):
										filterNote="Fail Homology Filter "+str(homology_filter_val)
									else:										
										filterNote="OK"
										mutation_map=myCodonCounter.acquire_mutation_map(kabat_CDR1,kabat_FR2,kabat_CDR2,hybrid_aln)
										#print "THE MUTATION MAP for ",vInfo['query id']," IS ",mutation_map
								else:
									#print "INCOMPLETE so no mutation counting!"
									filterNote="Incomplete regions"
						else:
							filterNote="VJ Out of Frame"

					else:
						filterNote="Found a stop codon"
				#validate_regions_for_completenessLength(cdr1_info,fr2_info,cdr3_info,fr3_info):
			else:
				#print read_rec.id+" isn't an IGHV4 hit!"
				filterNote="Not an IGHV4 hit"
		else:
			#print read_rec.id+" has not subject ids!"
			filterNote="No name found for hit"
	else:
		#print read_rec.id+" has no vinfo"
		filterNote="NoVHit"
	return [filterNote,mutation_map]




if (__name__=="__main__"):
	myCounter=codonCounter("/home/data/vdj_server/repertoire-summarization/codon_data/codon_pos_IGHV4")
	




