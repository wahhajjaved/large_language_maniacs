#!/usr/bin/env python

import random
from utils import makeEmptyArrayOfDigitsOfLen,biopythonTranslate,getNumberBpInAlnStr,biopythonTranslate
import re
import threading


#in a string find the number of dashes that may prefix the string
#return 0, 1, etc.
def getNumStartingDashes(s):
	dre=re.compile(r'^(\-+)')
	sr=re.search(dre,s)
	if(sr):
		dashes=sr.group(1)
		return len(dashes)
	else:
		return 0


#class for routines for codon translation
#and associated tasks
class CodonAnalysis:
	
	#internal data
	codon_amino_map=None
	amino_codon_map=None
	unambiguous_codon_dict=dict()
	bases=["A","C","G","T","a","c","g","t"]
	valid_aminos=None
	junc_mask=None

	def is_unambiguous_amino(self,aa_res):
		if(aa_res in self.valid_aminos):
			return True
		if(not(type(aa_res)==str)):
			return False
		if(aa_res.upper() in self.valid_aminos):
			return True
		else:
			return False


	#make a list of codons
	def make_codons(self):
		bases=self.bases
		codons=list()
		for b1 in range(len(bases)):
			for b2 in range(len(bases)):
				for b3 in range(len(bases)):
					codon=bases[b1]+bases[b2]+bases[b3]
					codons.append(codon)
		return codons

	#make a list of aminos
	def make_aminos(self):
		amino_set=set()
		codons=self.make_codons()
		for codon in codons:
			amino=str(biopythonTranslate(codon))
			amino_set.add(amino)
		amino_list=list()
		for amino in amino_set:
			amino_list.append(amino)
		return amino_list

	#test for ambiguity
	def is_unambiguous_base(self,b):
		if(b in self.bases):
			return True
		else:
			return False



	#test for codon ambiguity
	#by testing individual bases for ambiguity
	def is_unambiguous_codon(self,c):
		if(c in self.unambiguous_codon_dict):
			return self.unambiguous_codon_dict[c]
		#if a list of bases
		if(type(c)==list):
			for base in c:
				ba=self.is_unambiguous_base(base)
				if(not(ba)):
					self.unambiguous_codon_dict[c]=False
					return self.is_unambiguous_codon(c)
		#if a single string of 3 bases
		elif(type(c)==str):
			for bi in range(len(c)):
				base=c[bi]
				ba=self.is_unambiguous_base(base)
				if(not(ba)):
					self.unambiguous_codon_dict[c]=False
					return self.is_unambiguous_codon(c)
		else:
			self.unambiguous_codon_dict[c]=False
			return self.is_unambiguous_codon(c)
		self.unambiguous_codon_dict[c]=True
		return self.is_unambiguous_codon(c)


	#initialize the codon->amino map
	def init_ca_map(self):
		codons=self.make_codons()
		self.codon_amino_map=dict()
		ascii_list=list()
		#create an ASCII list
		for a in range(33,122):
			ascii_list.append(chr(a))
		#for each possible ASCII triplet, register/save X as the default translation
		for b1 in ascii_list:
			for b2 in ascii_list:
				for b3 in ascii_list:
					codon=b1+b2+b3
					self.codon_amino_map[codon]="X"
		#now use valid codons to overwrite X
		for codon in codons:
			#print "init with ",codon
			amino=str(biopythonTranslate(codon.upper()))
			self.codon_amino_map[codon]=amino
			if(self.valid_aminos==None):
				self.valid_aminos=set()
			self.valid_aminos.add(amino)
	
	#initialize the amino->codons map!
	def init_ac_map(self):
		aminos=self.make_aminos()
		self.amino_codon_map=dict()
		for amino in aminos:
			codons=self.make_codons()
			codons_that_make_this_amino=list()
			for codon in codons:
				if(self.codon_amino_map[codon]==amino):
					codons_that_make_this_amino.append(codon)
			self.amino_codon_map[amino]=codons_that_make_this_amino

	#lookup-based translation for a string
	def fastTransStr(self,codons_str):
		translation=""
		if(len(codons_str)<3):
			return translation
		else:
			while(len(codons_str)>=3):
				a_codon=codons_str[0:3]
				an_amino=self.fastTrans(a_codon)
				translation+=an_amino
				codons_str=codons_str[3:]
				if(len(codons_str)<3):
					return translation
			return translation


	#lookup-based translation for a single codon
	def fastTrans(self,codon):
		return self.codon_amino_map[codon]

	def __init__(self):
		self.init_ca_map()
		self.init_ac_map()



#make an instance of the analyzer
codonAnalyzer=CodonAnalysis()



#class for two-seq alignment methods/tools/data
class alignment:

	#internal data
	s_aln=""
	q_aln=""
	s_start=(-1)
	s_end=(-1)
	q_start=(-1)
	q_end=(-1)
	s_frame_mask=None
	global codonAnalyzer
	valid_bases=codonAnalyzer.bases
	q_base_pos_LookUp=None
	AA_mut_list=None
	alignment_name=None
	complete_region=False
	public_char_map=None
	




	#constructor
	def __init__(self,Cq_aln,Cs_aln,Cq_start=None,Cq_end=None,Cs_start=None,Cs_end=None,Cs_frame_mask=None):
		self.s_aln=Cs_aln.upper()
		self.q_aln=Cq_aln.upper()
		self.s_start=Cs_start
		self.s_end=Cs_end
		self.q_start=Cq_start
		self.q_end=Cq_end
		self.s_frame_mask=Cs_frame_mask
		self.setQBasePosLookUp()


	#test for overlap
	def overlapsWith(self,otherAln):
		#determine if self is contained in other
		if(otherAln.q_start<=self.q_start and self.q_start<=otherAln.q_end):
			#this start is contained in other interval
			return True
		if(otherAln.q_start<=self.q_end and self.q_end<=otherAln.q_end):
			#this end is contained in other interval
			return True
		if(otherAln.q_start<=self.q_start and self.q_start<=otherAln.q_end):
			#other straddles this start
			return True
		if(otherAln.q_start<=self.q_end and self.q_end<otherAln.q_end):
			#other straddles this end
			return True
		if(self.q_start<=otherAln.q_start and otherAln.q_end<=self.q_end):
			#other totally contained in this
			return True
		if(otherAln.q_start<=self.q_start and self.q_end<=otherAln.q_end):
			#this totally contained in other
			return True
		#none of the above
		return False




	#setter for alignment name
	def setName(self,newName):
		self.alignment_name=newName

	#getter for alignment name
	def getName(self):
		return self.alignment_name

	#setter for complete region
	def setCompleteRegion(self,crStatus=False):
		self.complete_region=crStatus

	#getter for complete region
	def getCompleteRegion(self):
		return self.complete_region



	#the q_base_pos_LookUp array takes an index into the 
	#alignment string and returns a base position for the query.  Leans RIGHT
	#in the gap
	def setQBasePosLookUp(self):
		computedNumBases=self.q_start-self.q_end+1
		countedNumBases=getNumberBpInAlnStr(self.q_aln)
		if(countedNumBases!=computedNumBases):
			#inconsistency!
			pass
		basePos=self.q_start
		for alnI in range(len(self.q_aln)):
			if(self.q_base_pos_LookUp==None):
				self.q_base_pos_LookUp=list()
			self.q_base_pos_LookUp.append(basePos)
			if(self.q_aln[alnI]=="-"):
				#no increment
				pass
			else:
				basePos+=1





		



	#adjust frame mask for when the s_aln in the alignment starts with "-" (gaps)
	def adjustSFJForSAlnGaps(self,setSFMVal):
		if(self.s_frame_mask==None or len(self.s_aln)<=0):
			#raise Exception("Error, require a frame mask and valid s_aln to adjust FM for gaps in s_aln!")
			return
		else:
			if(len(self.s_frame_mask)!=len(self.s_aln) or len(self.s_frame_mask)<=0 or len(self.s_aln)<=0):
				return
			else:
				if(re.match(r'^\-+$',self.s_aln)):
					return
				numInitialDashes=getNumStartingDashes(self.s_aln)
				if(numInitialDashes>0):
					#print numInitialDashes,">0!"
					for p in range(numInitialDashes):
						b_index=numInitialDashes-p-1
						#print "b_index=",b_index
						mask_val=setSFMVal-p-1
						#print "p=",p," and setSFMVal=",setSFMVal
						#print "mask_val premod=",mask_val
						mask_val=(mask_val%3)
						#print "mask_val=",mask_val
						self.s_frame_mask[b_index]=mask_val
				for p in range(len(self.s_aln)-1):
					next_p=p+1
					if(self.s_aln[next_p]=="-"):
						self.s_frame_mask[next_p]=(self.s_frame_mask[p]+1)%3
						



	#set frame mask so that the first subject base has the given value
	def setSFM(self,firstFrame=0):
		nfm=list()
		current=firstFrame
		temp=0
		#print "setsfm called with firstFrame==",firstFrame
		if(len(self.s_aln)<=0):
			#print "setsfm early return..."
			self.s_frame_mask=nfm
			return
		if(self.s_aln[temp]=="-"):
			current-=1
			current=current%3
		if(self.s_aln.startswith("-")):
			while(temp<len(self.s_aln)):
				if(self.s_aln[temp]!="-"):
					current+=1
				nfm.append(current%3)
				temp+=1			
		else:
			while(temp<len(self.s_aln)):
				nfm.append(current%3)
				if(self.s_aln[temp]!="-"):
					current+=1
				temp+=1
		self.s_frame_mask=nfm
		self.adjustSFJForSAlnGaps(firstFrame)
		#print "just set self.s_frame_mask to ",self.s_frame_mask


	#supply S frame_mask
	def supplySFrameMask(self,Cs_frame_mask):
		if(not(type(Cs_frame_mask)==list)):
			raise Exception("ERROR, REQUIRE FRAME MASK TO BE A LIST!")
		elif(not(len(Cs_frame_mask)==len(self.s_aln))):
			raise Exception("ERROR, REQUIRE FRAME MASK TO BE THE SAME LENGTH AS S_ALN!  MASK_LEN="+str(len(Cs_frame_mask))+" AND LEN S_ALN="+str(len(self.s_aln)))
		else:
			self.s_frame_mask=Cs_frame_mask


	#get subalignment with first subject/query non-gapped position start
	def getGEQAlignmentFirstNonGap(self):
		s_pos=self.s_start
		q_pos=self.q_start
		if(s_pos==0 or q_pos==0):
			return self
		if(len(self.s_aln)<=0 or len(self.q_aln)<=0):
			return self
		allGaps=re.compile(r'^\-+$')
		if(allGaps.match(self.s_aln) or allGaps.match(self.q_aln)):
			return self
		if(self.s_aln[0]!="-" and self.q_aln[0]!="-"):
			return self
		sdashRe=re.compile(r'^(\-+)[^\-]')
		sreres=re.match(sdashRe,self.s_aln)
		qreres=re.match(sdashRe,self.q_aln)
		if(sreres):
			dashes=sreres.group(1)
			num_dashes=len(dashes)
			nq_start=self.q_start+num_dashes
			return self.getAlnAtAndCond(nq_start,"query","geq")
		else:
			dashes=qreres.group(1)
			num_dashes=len(dashes)
			return self.getAlnAtAndCond(sq_start,"subject","geq")
		



	#build an alignment from a BTOP
	#returns array of query, then match/midline, then subject based on btop alignment specification
	#NOTE : in BTOP, when two characters are paired, the first character is the QUERY
	#Thus the alignment 	3CG2 could represent : Q_ALN 'GATCAA' and S_ALN 'GATGAA'
	@staticmethod
	def buildAlignmentWithBTOP(btop,q,s,debug=False,level=0):
		return buildAlignmentWholeSeqs(btop,q,s,debug,level)


	#return true or not if the passed is an inf
	@staticmethod
	def isAnInf(a):
		if(a==float("inf") or a==float("-inf")):
			return True
		else:
			return False

	@staticmethod
	#of two values, return the one that's not infinite
	def getNonInf(a,b):
		if(alignment.isAnInf(a) and alignment.isAnInf(b)):
			raise Exception("Can't get noninf from a=",a,"b=",b)
		else:
			if(not(alignment.isAnInf(a))):
				return a
			else:
				return b

	#for each bp, get a mapping to position within the sequence
	#the items in the list correspond to the positions of the bps
	def getPosList(self,s="subject",leanLeft=True):
		temp=0
		pl=list()
		#if the alignments are empty return empty!
		if((self.s_aln is None) or (self.q_aln is None)):
			return pl
		if(len(self.s_aln)<=0 or len(self.q_aln)<=0):
			return pl
		#choose the correct sequence
		if(s=="query"):
			seq=self.q_aln
			s_pos=self.q_start
		else:
			seq=self.s_aln
			s_pos=self.s_start
		if(seq[temp]=="-" and leanLeft):
			s_pos-=1
		pl=list()
		while(temp<len(seq)):
			pl.append(s_pos)
			if(seq[temp]!="-"):
				s_pos+=1	
			temp+=1
		return pl



	#ins, del, bsb, syn/non-sym, stp
	def characterize(self,charMsg=None,showAln=False):
		global codonAnalyzer
		self.AA_mut_list=list()
		char_map=dict()
		num_ins=0
		num_del=0
		num_syn=0
		num_nsy=0
		num_bsb=0
		stp_cdn=False	
		aa_reps=0
		aa_slnt=0
		length_in_codons=0



		#do counts that are independent of codons/translations (bsb, indels, and their frequencies)
		tot_num_base_to_base_alns=0
		for i in range(len(self.s_aln)):
			if(self.s_aln[i]!="-" and self.q_aln[i]!="-"):
				tot_num_base_to_base_alns+=1
			if(self.s_aln[i]=="-"):
				num_ins+=1
			elif(self.q_aln[i]=="-"):
				num_del+=1
			elif(self.q_aln[i]!=self.s_aln[i]):
				if(self.q_aln[i] in self.valid_bases and self.s_aln[i] in self.valid_bases  ):
					#make sure  that the base is unambiguous
					num_bsb+=1
		num_indels=num_ins+num_del
		if(tot_num_base_to_base_alns>0):
			char_map['base substitution freq%']=float(num_bsb)/float(tot_num_base_to_base_alns)
			id_tot_rto=float(tot_num_base_to_base_alns-num_bsb)/float(tot_num_base_to_base_alns)
			char_map['homology%']=id_tot_rto
			indel_rate=float(num_indels)/float(num_indels+tot_num_base_to_base_alns)
			char_map['indel frequency']=indel_rate
		else:
			if(num_indels>0):
				indel_rate=float(1.0)
			else:
				indel_rate=0
			char_map['indel frequency']=indel_rate
			char_map['base substitution freq%']=0
			char_map['homology%']=0
		#fill in the map
		char_map['insertion count']=num_ins
		char_map['deletion count']=num_del
		char_map['base substitutions']=num_bsb
		char_map['mutations']=num_bsb+num_del+num_ins
		

		#if there is a frame, load it
		#otherwise, load a dummy frame
		#print "self.s_frame_mask",self.s_frame_mask
		if(not(self.s_frame_mask==None)):
			#print "loading own mask cause it's non-none"
			frame_mask=self.s_frame_mask
		else:
			#print "loading empty mask cause own mask is none"
			frame_mask=makeEmptyArrayOfDigitsOfLen(len(self.s_aln))

		#do frame-dependent calculations
		temp_index=0
		codon_list=list()
		s_codon_list=list()
		amino_list=list()
		s_amino_list=list()
		while(temp_index<len(self.s_aln)):
			if(
			temp_index<len(self.s_aln)-2 and 
			frame_mask[temp_index]==0 and 
			frame_mask[temp_index+1]==1 and 
			frame_mask[temp_index+2]==2 
			):
				#print "temp_index=",temp_index
				#print "encountered a codon...."
				s_codon=self.s_aln[temp_index:(temp_index+3)]
				s_codon_list.append(str(s_codon))
				#s_codon_w_gaps=s_codon
				#print "s codon is ",s_codon
				q_codon=self.q_aln[temp_index:(temp_index+3)]
				codon_list.append(str(q_codon))
				#q_codon_w_gaps=q_codon
				#print "q codon is ",q_codon
				if(not(stp_cdn)):
					if(q_codon.find("-")==(-1)):
						#q_amino=str(biopythonTranslate(q_codon))
						q_amino=codonAnalyzer.fastTrans(q_codon)
						if(q_amino=="*"):
							stp_cdn=True
				if(s_codon.find("-")==(-1) and q_codon.find("-")==(-1)):
					#ANALYSIS FOR TWO CODONS WITH NO GAPS
					#no gaps, perform analysis
					#print "Detected no gaps in codons"
					#s_amino=str(biopythonTranslate(s_codon))
					s_amino=codonAnalyzer.fastTrans(s_codon)
					s_amino_list.append(str(s_amino))
					#print "subject amino :",s_amino," and codon ",s_codon
					#q_amino=str(biopythonTranslate(q_codon))
					q_amino=str(codonAnalyzer.fastTrans(q_codon))
					amino_list.append(str(q_amino))
					#print "query amino ",q_amino," and codon ",q_codon
					#print "PRE SYN/NSY counts : ",num_syn," and ",num_nsy 
					length_in_codons+=1
					if(s_amino==q_amino):
						syn=True
					else:
						syn=False
						aa_reps+=1
						if(self.q_base_pos_LookUp is not None):
							#print "FOUND A NON-SILENT MUTATION "+s_amino+" -> "+q_amino+" at read position ",self.q_base_pos_LookUp[temp_index]
							self.AA_mut_list.append(s_amino+str(int(self.q_base_pos_LookUp[temp_index]))+q_amino)
					had_silent=False
					if(codonAnalyzer.is_unambiguous_codon(q_codon) and codonAnalyzer.is_unambiguous_codon(s_codon)):
						if(syn):
							for cp in range(3):
								if(s_codon[cp]!=q_codon[cp]):
									num_syn+=1
									had_silent=True
						else:
							for cp in range(3):
								if(s_codon[cp]!=q_codon[cp]):
									num_nsy+=1
						#print "POST SYN/NSY counts : ",num_syn," and ",num_nsy
						if(had_silent):
							aa_slnt+=1
							if(self.q_base_pos_LookUp is not None):
								#print "FOUND A SILENT MUTATION "+s_amino+" -> "+q_amino+" at read position ",self.q_base_pos_LookUp[temp_index]
								self.AA_mut_list.append(s_amino+str(int(self.q_base_pos_LookUp[temp_index]))+q_amino)
				else:
					#ANALYSIS FOR CODONS WITH any gap
					if(q_codon.find("-")==(-1)):
						q_amino=str(codonAnalyzer.fastTrans(q_codon))
						amino_list.append(q_amino)
					else:
						amino_list.append("X")
					for cp in range(3):
						if(s_codon[cp]!="-" and q_codon[cp]!="-" and s_codon[cp]!=q_codon[cp]):
							#num_bsb+=1
							#already accounted for at beginning
							pass

				temp_index+=3
			else:
				#print "encountered a single.... temp_index=",temp_index
				codon_list.append("("+self.q_aln[temp_index]+")")
				amino_list.append("(-)")
				if(self.s_aln[temp_index]!=self.q_aln[temp_index] and self.s_aln[temp_index]!="-" and self.q_aln[temp_index]!="-"):
					#num_bsb+=1
					pass
				temp_index+=1
		#fill in the map
		char_map['synonymous base substitutions']=num_syn
		char_map['nonsynonymous base substitutions']=num_nsy
		if(num_syn!=0):
			ns_ratio=float(num_nsy)/float(num_syn)
		else:
			ns_ratio=0
		if(length_in_codons!=0):
			char_map['replacement mutation freq%']=float(aa_reps)/float(length_in_codons)
			char_map['silent mutation freq%']=float(aa_slnt)/float(length_in_codons)
		else:
			char_map['replacement mutation freq%']=0
			char_map['silent mutation freq%']=0
		if(aa_slnt!=0):
			char_map['R:S ratio']=float(aa_reps)/float(aa_slnt)
		else:
			char_map['R:S ratio']=None

		char_map['ns_rto']=ns_ratio
		char_map['Stop codons?']=stp_cdn
		j_str=""
		char_map['AA']=j_str.join(amino_list)
		char_map['AA_ref']=j_str.join(s_amino_list)
		char_map['nucleotide read']=codon_list
		char_map['subject_read']=s_codon_list
		char_map['length']=abs(int(self.q_start)-int(self.q_end))+1
		char_map['silent mutations (codons)']=aa_slnt
		char_map['replacement mutations (codons)']=aa_reps
		self.public_char_map=char_map
		return char_map


	

	def logical2WayMerge(self,otherAln,juncSeq=""):
		if(self.overlapsWith(otherAln)):
			return
		else:
			if(self.q_start<otherAln.q_start):
				firstAln=self
				secondAln=otherAln
			else:
				firstAln=otherAln
				secondAln=self
		new_q_start=firstAln.q_start
		new_q_end=secondAln.q_end
		new_q_aln=firstAln.q_aln+juncSeq+secondAln.q_aln
		new_s_aln=firstAln.s_aln+juncSeq+secondAln.s_aln
		new_s_aln_noGAPs=re.sub(r'\-',"",new_s_aln)
		gap_free_len=len(new_s_aln_noGAPs)
		new_s_start=1
		new_s_end=gap_free_len
		#def __init__(Cq_aln,Cs_aln,Cq_start=None,Cq_end=None,Cs_start=None,Cs_end=None,Cs_frame_mask=None):
		mergedAln=alignment(new_q_aln,new_s_aln,new_q_start,new_q_end,new_s_start,new_s_end)
		return mergedAln

		



	
	def getCharMap(self):
		if(self.public_char_map==None):
			self.characterize()
		return self.public_char_map


	#extract a subalignment given start/stop IS INCLUSIVE! [A,B] (not (A,B)!)
	def getSubAlnInc(self,sub_start,sub_end,s):
		if(sub_start>sub_end):
			temp=sub_start
			sub_start=sub_end
			sub_end=temp
		if(s=="query"):
			if(sub_start>self.q_end or sub_end<self.q_start):
				return alignment("","",0,0,0,0)
		if(s=="subject"):
			if(sub_start>self.s_end or sub_end<self.s_start):
				return alignment("","",0,0,0,0)			
		firstAln=self.getAlnAtAndCond(sub_end,s,cond="leq")
		secondAln=firstAln.getAlnAtAndCond(sub_start,s,cond="geq")
		return secondAln


	#given an alignment, and a position of a sequence IN the alignment
	#return the porition of the alignment whose bp are <= or >= that position in the alignment
	#has been tested with the TEST method of this class
	def getAlnAtAndCond(self,a_pos,st="query",cond="geq"):

		if(not(st=="query")):
			st="subject"
		aln=["",""] #Q, then S
		if(not(cond=="leq")):
			cond="geq"		
		#reset the input to a valid value if necessary
		if(st=="query" and a_pos<self.q_start and cond=="geq"):
			a_pos=self.q_start
		if(st=="query" and a_pos>self.q_end and cond=="leq"):
			a_pos=self.q_end
		if(st=="subject" and a_pos<self.s_start and cond=="geq"):
			a_pos=self.s_start
		if(st=="subject" and a_pos>self.s_end and cond=="leq"):
			a_pos=self.s_end


		temp=0

		#use inf values so that min/max return the numbers and not infs
		min_s_pos=float("inf")
		max_s_pos=float("-inf")
		min_q_pos=float("inf")
		max_q_pos=float("-inf")	
		used_flag=False	
		s_pos=self.s_start
		q_pos=self.q_start
		while(temp<len(self.q_aln)):
			used_flag=False
			if(cond=="leq"):#less than or equal to
				if(st=="query"):
					if(a_pos>=q_pos):
						used_flag=True
						aln[0]+=self.q_aln[temp]
						aln[1]+=self.s_aln[temp]
				else:
					if(a_pos>=s_pos):
						aln[0]+=self.q_aln[temp]
						aln[1]+=self.s_aln[temp]
						used_flag=True
			else:#geq greater-than or equal to
				if(st=="query"):
					if(a_pos<=q_pos):
						aln[0]+=self.q_aln[temp]
						aln[1]+=self.s_aln[temp]
						used_flag=True
				else:
					if(a_pos<=s_pos):
						aln[0]+=self.q_aln[temp]
						aln[1]+=self.s_aln[temp]				
						used_flag=True
			if(used_flag):
				if(max_s_pos<=s_pos and self.s_aln[temp]!="-"   ):
					max_s_pos=s_pos
				if(min_s_pos>=s_pos and self.s_aln[temp]!="-"  ):
					min_s_pos=s_pos
				if(max_q_pos<=q_pos and  self.q_aln[temp]!="-"):
					max_q_pos=q_pos
				if(min_q_pos>=q_pos and self.q_aln[temp]!="-"):
					min_q_pos=q_pos
			if(self.s_aln[temp]!="-"):
				#print "examing ",self.s_aln[temp]," incrementing ",s_pos," to ",str(s_pos+1)
				s_pos+=1
			if(self.q_aln[temp]!="-"):
				q_pos+=1
			temp+=1

		if(cond=="geq"):
			#print "GREATER BRANCH"
			#print "set qmax from ",max_q_pos," to ",self.s_end
			max_q_pos=self.q_end
			max_s_pos=self.s_end
			if(st=="query"):
				min_q_pos=a_pos
			else:
				min_s_pos=a_pos
		else:
			min_q_pos=self.q_start
			min_s_pos=self.s_start
			if(st=="query"):
				max_q_pos=a_pos
			else:
				max_s_pos=a_pos

		#
		if(self.isAnInf(max_q_pos)):
			max_q_pos=self.getNonInf(max_q_pos,min_q_pos)
		if(self.isAnInf(min_q_pos)):
			min_q_pos=self.getNonInf(max_q_pos,min_q_pos)
		if(self.isAnInf(max_s_pos)):
			max_s_pos=self.getNonInf(max_s_pos,min_s_pos)
		if(self.isAnInf(min_s_pos)):
			min_s_pos=self.getNonInf(max_s_pos,min_s_pos)

		#handle error/corner cases where alignment should be empty
		if(min_s_pos>max_s_pos or min_q_pos>max_q_pos):
			return alignment("","",0,0,0,0)			


		sub_aln=alignment(aln[0],aln[1],min_q_pos,max_q_pos,min_s_pos,max_s_pos)
		#return aln #Q then S
		return sub_aln

	@staticmethod
	def test():
		print "TEST!"
		g_q_aln="CCCGATT-CATA-TACA"
		g_s_aln="----AT-ACCATATTA-"
		g_q_from=7
		g_q_to=21
		g_s_from=19
		g_s_to=29
		test_aln=alignment(g_q_aln,g_s_aln,g_q_from,g_q_to,g_s_from,g_s_to)
		test_aln.setSFM()
		print "Query Base Map : ",test_aln.q_base_pos_LookUp
		print "biggap test : "
		print test_aln.getNiceString()
		t_q_aln="GATT-CATA-TACA"
		t_s_aln="-AT-ACCATATTA-"
		t_q_from=10
		t_q_to=21
		t_s_from=19
		t_s_to=29
		test_aln=alignment(t_q_aln,t_s_aln,t_q_from,t_q_to,t_s_from,t_s_to)
		test_aln.setSFM()
		sub_aln_no_gap=test_aln.getGEQAlignmentFirstNonGap()
		print "The test_aln is ",
		print test_aln.getNiceString()
		print "First non-gap both is "
		sub_aln_no_gap.setSFM()
		print sub_aln_no_gap.getNiceString()
		testGOL=True
		if(testGOL):
			for c in range(t_q_from-2,t_q_to+2):
				print "\n"
				print "c query=",c
				abovec=test_aln.getAlnAtAndCond(c,"query","geq")
				belowc=test_aln.getAlnAtAndCond(c,"query","leq")
				print "ORIGINAL\n"+test_aln.getNiceString()
				print test_aln.characterize()
				print "QBM : ",test_aln.q_base_pos_LookUp
				print "MODA >=",c
				print abovec.getNiceString()
				print abovec.characterize()
				print abovec.getPosList()
				print "QBM : ",abovec.q_base_pos_LookUp
				print "MODB <=",c
				print belowc.getNiceString()
				print belowc.characterize()
				print belowc.getPosList()
				print "QBM : ",belowc.q_base_pos_LookUp
			for c in range(t_s_from-2,t_s_to+2):
				print "\n"
				print "c subject=",c
				abovec=test_aln.getAlnAtAndCond(c,"subject","geq")
				belowc=test_aln.getAlnAtAndCond(c,"subject","leq")
				print "ORIGINAL\n"+test_aln.getNiceString()
				print "QBM : ",test_aln.q_base_pos_LookUp
				print "MODA >=",c
				print abovec.getNiceString()
				print abovec.characterize()
				print abovec.getPosList()
				print "QBM : ",abovec.q_base_pos_LookUp
				print "MODB <=",c
				print belowc.getNiceString()
				print belowc.characterize()
				print belowc.getPosList()
				print "QBM : ",belowc.q_base_pos_LookUp
		for s in range(10):
			start=int(random.random()*50)
			end=start+int(random.random()*10)
			#start=27;end=29
			print "\n\n\n"
			print "ORIGINAL\n"+test_aln.getNiceString()
			print "QBM : ",test_aln.q_base_pos_LookUp
			print "Try start=",start," end=",end
			sub_aln=test_aln.getSubAlnInc(start,end,"query")
			sub_aln.setSFM()
			print sub_aln.getNiceString()
			print "QBM:",sub_aln.q_base_pos_LookUp

		print "JUNC 2 TEST"
		base_q="TGTGCGAGAGGCAGTACCGGCCGATTTTTGGAGTGGTTATTATACTTTGACTACTGGGGCCAG"
		car_q=base_q[0:11]
		car_s=base_q[0:11]
		trp_q=base_q[42:]
		trp_s=base_q[42:]
		v_aln=alignment(car_q,car_s,1,11,1,11)
		v_aln.setSFM()
		for i in range(len(base_q)):
			print "i=",i
			print "base_q[",i,"] : ",base_q[i]
		print v_aln.getNiceString()
		j_aln=alignment(trp_q,trp_s,43,63,1,21)
		j_aln.setSFM()
		print j_aln.getNiceString()
		juncSeq=base_q[11:42]
		print "The junc seq = ",juncSeq
		merged_aln_1=v_aln.logical2WayMerge(j_aln,juncSeq)
		merged_aln_2=j_aln.logical2WayMerge(v_aln,juncSeq)
		print "m1\n",merged_aln_1.getNiceString()
		print "\nm2\n",merged_aln_2.getNiceString()




	#return the alignment as a pretty print string
	def getNiceString(self):
		aln=["","",""]
		aln[0]=str(self.q_aln)
		aln[2]=str(self.s_aln)
		for b in range(len(aln[0])):
			qbase=aln[0][b]
			sbase=aln[2][b]
			if(qbase=="-" or sbase=="-"):
				aln[1]+=" "
			elif(not(qbase==sbase)):
				aln[1]+="X"
			else:
				aln[1]+="|"
		aln[0]="QURY:"+aln[0]
		aln[1]="MDLN:"+aln[1]
		aln[2]="SBCT:"+aln[2]
		self.setName("")
		s_final="ALIGNMENT "+self.getName()+".\n Q_FROM="+str(self.q_start)+ " Q_TO="+str(self.q_end)+" S_FROM="+str(self.s_start)+" S_TO="+str(self.s_end)
		newLine="\n"
		s_final+="\n"+newLine.join(aln)
		if(self.s_frame_mask is not None):
			s_final+="\nSFMK:"+str(self.s_frame_mask)
		return s_final



#test for bare-minimum overlap (any of 3 possibilites triggers true)
def threeWayOverlapTest(aln0,aln1,aln2):
	ab=False
	bc=False
	ac=False
	ab=aln0.overlapsWith(aln1)
	bc=aln.overlapsWith(aln2)
	ac=aln0.overlapsWith(aln2)
	if(ab or bc or ac):
		return True
	else:
		return False


if (__name__=="__main__"):
	alignment.test()






