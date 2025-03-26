#!/usr/bin/env python2.7
#-----------------------------------------------------------------------
# Program: STASH_converter.py
# Purpose: To display stash items as readable csv.
# Created: Sarah Sparrow 18/11/16
# Details: Run with inputs stash file and STASH lookup csv.
#-----------------------------------------------------------------------
import getopt,os, sys, time
import numpy as np
import csv

MODELS={1:"Atmosphere",2:"Ocean",3:"Ice",4:"Wave"}

#-----------------------------------------------------
# Specs for TIMES
ITYP={0:"Not required by STASH, but space required",1:"Replace",2:"Accumulate",3:"Time mean",4:"Append timeseries",5:"Maximum",6:"Minimum",7:"Trajectories"}
#ISAM="Sampling frequency"
# Unit for (UNT1) processing period, (UNT2) sampling frequency, (UNT3) output times
UNT={"H":"hours","DA":"days","DU":"dump periods","T":"timesteps"}
#INTV=Processing period, -1=indefinite
IOPT={1:"Regular output times",2:"Irregular output times"}
# ISTR,IEND,IFRE - start time, end time, frequency (IOPT=1)
# ITIMES= number of output times, ISER=list of times (IOPT=2)

#-----------------------------------------------------
# Specs for DOMAINS
# IOPL = Model level type
IOPL={1:"Model full levels",2:"Model half levels",3:"Pressure levels",4:"Geometric height levels",5:"Single level",6:"Deep soil levels",7:"Theta levels",8:"Potential vorticity levels",9:"Cloud threshold levels",10:"Wave model direction 'levels'"}
# For IOPL=1,2,6,10 (Model levels) specify ILEVS
# ILEVS=1 Continuous range from LEVB to LEVT (first to last level)
# ILEVS=2 Integer list (LEVLST) of specified levels.

#IOPA= Horizontal domain type
IOPA={1:"Global",2:"NH",3:"SH",4:"30-90N",5:"30-90S",6:"0-30N",7:"0-30S",8:"30S-30N",9:"Area specified in whole degrees",10:"Area specified in gridpoints"}
# FOR IOPA=9, 10 specify area limits INTH,ISTH, IEST, IWST

#IMSK gridpoint option
IMSK={1:"All points",2:"Land",3:"Sea"}

#IMN spatial meaning
IMN={0:"None",1:"Vertical",2:"Zonal",3:"Meridional",4:"Horizontal area"}

#IWT weighting
IWT={0:"None",1:"Horizontal",2:"Volume",3:"Mass"}

#PLT Pseudo level type
PLT={0:"None",1:"SW radiation bands",2:"LW radiation bands",3:"Atmospheric assimilation groups",4:"Ocean assimilation groups",5:"Ocean tracer transport (MEAD) diagnostics",6:"Wave model frequency",7:"Wave model wave train number",8:"HadCM2 Sulphate Loading Pattern Index",9:"Land and Vegetation Surface Types"}
#PSLIST is the pseudo level list

#TS switch for time series option (y/n). IF TS=Y the time series domains are defined by:
#TSNUM No. of time series domains 
#TNLIM,TSLIM,TELIM,TWLIM Horizontal domain limits 
#TBLIM ,TTLIM Vertical limits (model levels) 
#TBLIMR,TTLIMR Vertical limits (real levels)


#-----------------------------------------------------
# Specs for USE
#LOCN={1:"Dump store with user specified tag",2:"Dump store with climate mean tag",3:"PP file",5:"Mean diagnostic direct to mean PP file",6:"Secondary dump store with user tag"}
LOCN={1:"Dump store with user specified tag",2:"Dump store with climate mean tag",3:"output file",5:"Mean diagnostic direct to mean output file",6:"Secondary dump store with user tag"}
#IUNT PP unit number (for LOCN=3) Tag (for LOCN=1,2,6)



#-----------------------------------------------------
stash_lookup="Stash_lookup.csv"


class Vars:
        #input command line variables
        display=False
        stashfile=""
        pass


##############################################################################


def Usage():
        print "Usage :  --display       outputs csv to screen as well as file\n"\
        "       --stashfile=         specify stashc file to translate"

        sys.exit()


##############################################################################


def ProcessCommandLineOpts():

        # Process the command line arguments
        try:
                opts, args = getopt.getopt(sys.argv[1:],'',
                ['display','stashfile='])

                if len(opts) == 0:
                        Usage()
                for opt, val in opts:
                        if opt == '--display':
                                Vars.display=True
                        elif opt == '--stashfile':
                                Vars.stashfile=val
        except getopt.GetoptError:
                Usage()



#----------------------------------------------------
def ReadTimes(stashfile):
	print "Reading ITIM from ",stashfile
	time_lines=[]
	time_line=""
	time_dict={}
	count=0
	acount=0
	with open(stashfile, 'r') as input:
	   for line in input:
	          linetrim=line.strip()
		  linesplit=linetrim.split(',')
		  first_split=linesplit[0].split(' ')
		  if first_split[0]=='&STASHNUM':
                        acount +=1
		  if first_split[0]=='&STREQ':
		  	count=0
			model=int(first_split[2])
		  if first_split[0]=='&TIME':
			count=count+1
			if acount>2:
                                time_line=MODELS[model]+" Coupling Time "+str(count)+", "
                        else:
                                time_line=MODELS[model]+" Time "+str(count)+", "	
			start_line=line.strip('\n')+','
			iname=start_line.find("NAME")
			time_line += start_line[iname:]
		  elif first_split[0]=='/' or first_split[0]=='&END' :
		        time_lines.append(time_line.strip())
			time_line=""
		  elif len(time_line)>0:
		  	time_line += line.strip('\n')
	
	for tl in time_lines:
	    pp_set="N"
	    sp_set="N"
	    ts_set="N"
            if len(tl)>0:
                tl1=tl.split(",")
                time_name=tl1[0]
                for itl in tl1:
                        itl2=itl.split("=")
                        if itl2[0].strip()=="NAME":
                                tname=itl2[1][1:-1]
                        elif itl2[0].strip()=="ITYP":
                                value=int(itl2[1])
                                ttype=ITYP[value]
			elif itl2[0].strip()=="INTV":
				pp_set="Y"
				processing_period_val=int(itl2[1])
			elif itl2[0].strip()=="UNT1":
				processing_period_unit=UNT[itl2[1][1:-1].strip()]
			elif itl2[0].strip()=="ISAM":
				sp_set="Y"
				sampling_period_val=int(itl2[1])
			elif itl2[0].strip()=="UNT2":
				sampling_period_unit=UNT[itl2[1][1:-1].strip()]
			elif itl2[0].strip()=="ISTR":
				start_out=int(itl2[1])
			elif itl2[0].strip()=="IEND":
				end_out=int(itl2[1])
			elif itl2[0].strip()=="IFRE":
                                fre_out=int(itl2[1])
			elif itl2[0].strip()=="UNT3":
                                output_period_unit=UNT[itl2[1][1:-1].strip()]
			elif itl2[0].strip()=="ITIMES":
			        ntimes=int(itl2[1])
			elif itl2[0].strip()=="ISER":
				ts_set="Y"
				tslist=dl.split("ISER=")
                                ts_list=tslist[1].split("UNT3=")
                                tsl_out=ts_list[0].strip()
                                ts_levs=tsl_out[:-1]	
		if pp_set=="Y":
			processing_period=": process every "+str(processing_period_val)+" "+processing_period_unit
			ttype += processing_period
		if sp_set=="Y":
			sampling_period=": sample every "+str(sampling_period_val)+" "+sampling_period_unit
			ttype += sampling_period

		if ts_set=="Y":
			output_period=": output every "+str(fre_out)+" "+output_period_unit+" on "+output_period_unit+" "+ts_levs
                        ttype += output_period
		if end_out==-1:
			output_period=": output every "+str(fre_out)+" "+output_period_unit+" from "+output_period_unit[:-1]+" "+str(start_out)+" onwards"
			ttype += output_period
		else:
			output_period=": output every "+str(fre_out)+" "+output_period_unit+" from "+output_period_unit[:-1]+" "+str(start_out)+" to "+str(end_out)
                	ttype += output_period

		time_dict[time_name]=[tname,ttype]

	return time_dict

#---------------------------------------------------- 
def ReadDomains(stashfile):
        print "Reading IDOM from ",stashfile
        dom_lines=[]
        dom_line=""
	dom_dict={}
	horiz_domain_type=""
        count=0
	acount=0
        with open(stashfile, 'r') as input:
           for line in input:
                  linetrim=line.strip()
                  linesplit=linetrim.split(',')
                  first_split=linesplit[0].split(' ')
		  if first_split[0]=='&STASHNUM':
                        acount +=1
                  if first_split[0]=='&STREQ':
                        count=0
                        model=int(first_split[2])
                  if first_split[0]=='&DOMAIN':
                        count=count+1
			if acount>2:
                                dom_line=MODELS[model]+" Coupling Domain "+str(count)+", "
                        else:
                                dom_line=MODELS[model]+" Domain "+str(count)+", "
                        start_line=line.strip('\n')+','
                        iname=start_line.find("NAME")
                        dom_line += start_line[iname:]
                  elif first_split[0]=='/' or first_split[0]=='&END' :
                        dom_lines.append(dom_line.strip())
                        dom_line=""
                  elif len(dom_line)>0:
                        dom_line += line.strip('\n')
	
	for dl in dom_lines:
            levs_set="N"
            if len(dl)>0:
                dl1=dl.split(",")
                dom_name=dl1[0]
                for idl in dl1:
                        idl2=idl.split("=")
                        if idl2[0].strip()=="NAME":
                                dname=idl2[1][1:-1]
                        elif idl2[0].strip()=="IOPL":
                                ioplv=int(idl2[1])
                                dtype=IOPL[ioplv]
                        elif idl2[0].strip()=="ILEVS":
                                levs_set="Y"
                                levs_set_val=int(idl2[1])
                        elif idl2[0].strip()=="LEVB":
                                blev=int(idl2[1])
                        elif idl2[0].strip()=="LEVT":
                                tlev=int(idl2[1])
                        elif idl2[0].strip()=="LEVLST" or idl2[0].strip()=="RLEVLST":
				llist=dl.split("LEVLST=");
				lev_list=llist[1].split("PLT=")
				if idl2[0].strip()=="RLEVLST":
					levs_unit="hPa"
				else:
					levs_unit=""
				olev=lev_list[0].strip()
				levs_out=olev[:-1]
                        elif idl2[0].strip()=="IOPA":
                                iopav=int(idl2[1])
				horiz_domain=IOPA[iopav]
                        elif idl2[0].strip()=="INTH":
                                nlim=float(idl2[1])
                        elif idl2[0].strip()=="ISTH":
                                slim=float(idl2[1])
                        elif idl2[0].strip()=="IEST":
				elim=float(idl2[1])
			elif idl2[0].strip()=="IWST":
				wlim=float(idl2[1])
			elif idl2[0].strip()=="IMSK":
				value=int(idl2[1])
				mask=IMSK[value]
			elif idl2[0].strip()=="IMN":
                                value=int(idl2[1])
                                meaning=IMN[value]
			elif idl2[0].strip()=="IWT":
                                value=int(idl2[1])
                                weighting=IWT[value]
			elif idl2[0].strip()=="PLT":
				if idl2[1]=="":
					value=0
				else:
                                	value=int(idl2[1])
                                pseudo_lev_type=PLT[value]
			elif idl2[0].strip()=="PSLIST":
				pslist=dl.split("LIST=");
				ps_list=pslist[1].split("TS=")
                                psl_out=ps_list[0].strip()
				ps_levs=psl_out[:-1]
			elif idl2[0].strip()=="TS":
				ts_switch=idl2[1].strip()
			elif idl2[0].strip()=="TSNUM":
				ts_domains=int(idl2[1])
			elif idl2[0].strip()=="TNLIM":
				tn_lim=idl2[1].strip()
			elif idl2[0].strip()=="TSLIM":
                                ts_lim=idl2[1].strip()
			elif idl2[0].strip()=="TELIM":
                                te_lim=idl2[1].strip()
			elif idl2[0].strip()=="TWLIM":
                                tw_lim=idl2[1].strip()
			elif idl2[0].strip()=="TBLIM":
                                tb_lim=int(idl2[1])
			elif idl2[0].strip()=="TTLIM":
                                tt_lim=int(idl2[1])
			elif idl2[0].strip()=="TBLIMR":
                                tb_limr=int(idl2[1])
			elif idl2[0].strip()=="TTLIMR":
                                tt_limr=int(idl2[1])
                if ioplv in [1,2,6,10]:
			if levs_set_val==1:
				lev_text=": level "+str(blev)+" to "+str(tlev)
			elif levs_set_val==2:
				lev_text=": levels "+levs_out+levs_unit
		try:
                	lev_text=": levels "+levs_out+levs_unit
		except:
			lev_text=""	
		
		dtype += lev_text
		
		if iopav==9:
			horiz_domain_type=": horizontal domain bounds "+str(nlim)+"N, "+str(slim)+"S, "+str(elim)+"E, "+str(wlim)+"W" 
		elif iopav==10:
			horiz_domain_type=": horizontal domain bounds in gridpoints (N,S,E,W) "+str(int(nlim))+", "+str(int(slim))+", "+str(int(elim))+", "+str(int(wlim)) 
		else:
			horiz_domin_type=": horizontal domain "+horiz_domain
		dtype += horiz_domain_type
		dtype += ": "+mask
		
		if meaning!="None":
			dtype += ": "+meaning+" mean"
			
		if weighting!="None":
                        dtype += ": "+weighting+" weighted"

		if pseudo_lev_type!="None":
			dtype += ": "+pseudo_lev_type+" pseudo levels "+ps_levs
		if ts_switch=="Y":
			dtype +=": "+ts_domains+" time series domains"

		dom_dict[dom_name]=[dname,dtype]

	return dom_dict

#----------------------------------------------------
def ReadUses(stashfile):
        print "Reading IUSE from ",stashfile
        use_lines=[]
        use_line=""
	out_file=""
	file_type=""
        count=0
	acount=0
	use_dict={}
        with open(stashfile, 'r') as input:
           for line in input:
                  linetrim=line.strip()
                  linesplit=linetrim.split(',')
                  first_split=linesplit[0].split(' ')
		  if first_split[0]=='&STASHNUM':
		  	acount +=1
                  if first_split[0]=='&STREQ':
                        count=0	
                        model=int(first_split[2])
                  if first_split[0]=='&USE':
                        count=count+1
			if acount>2:
				use_line=MODELS[model]+" Coupling Use "+str(count)+", "
			else:
                        	use_line=MODELS[model]+" Use "+str(count)+", "
                        start_line=line.strip('\n')+','
                        iname=start_line.find("NAME")
                        use_line += start_line[iname:]
                  elif first_split[0]=='/' or first_split[0]=='&END' :
                        use_lines.append(use_line.strip())
                        use_line=""
                  elif len(use_line)>0:
                        use_line += line.strip('\n')
	for ul in use_lines:
	    if len(ul)>0:
		ul1=ul.split(",")
		use_name=ul1[0]
		for iul in ul1:
			iul2=iul.split("=")
			if iul2[0].strip()=="NAME":
				out_file=iul2[1][1:-1]
			elif iul2[0].strip()=="LOCN":
				value=int(iul2[1])
				file_type=LOCN[value]
		use_dict[use_name]=[out_file,file_type]
	
	return use_dict

#----------------------------------------------------
def ReadStash(stashfile,time_dict,dom_dict,use_dict):
        print "Translating STASH file ",stashfile
        acount=0
        f = open(stashfile, 'r')
	out_file=open(stashfile+'.csv','w')
        stash_writer=csv.writer(out_file,delimiter=',')
	stash_writer.writerow(["Model", "Stash code", "Name", "Units","CMOR Name", "Spatial Domain", "Time Sampling and Output","Output File"])
	for line in f:
                linetrim=line.strip()
                linesplit=linetrim.split(',')
                if len(linesplit)>1:
                        first_split=linesplit[0].split(' ')
                        if first_split[0]=='&STASHNUM':
                                acount +=1
                        if first_split[0]=='&STREQ':
                                model=int(first_split[2])
                                item=get_stash_item(linesplit,time_dict,dom_dict,use_dict,acount)
				stash_writer.writerow(item)
				if Vars.display==True:
					print item
        f.close
	out_file.close

#----------------------------------------------------
def get_stash_item(line,time_dict,dom_dict,use_dict,acount):
	for i,item in enumerate(line):
		result=item.split('=')
		if i==len(line)-1:
		 	r=result[-1]
			r.split('/')
			value=int(r[0])
		else:
			value=int(result[-1])
		if i==0:
			model=value
		elif i==1:
			stash_sec=value*1000
		elif i==2:
			stash_item=value
		elif i==3: 
			domain=value
		elif i==4: 
			time=value
		elif i==5: 
			use=value
	
	stash_code=stash_sec+stash_item
	name,units,CMOR_name=lookupSTASH(stash_code,model)
	if acount>2:
		tval=time_dict[MODELS[model]+" Coupling Time "+str(time)]
		dval=dom_dict[MODELS[model]+" Coupling Domain "+str(domain)]
		uval=use_dict[MODELS[model]+" Coupling Use "+str(use)]
	else:
		tval=time_dict[MODELS[model]+" Time "+str(time)]
		dval=dom_dict[MODELS[model]+" Domain "+str(domain)]
		uval=use_dict[MODELS[model]+" Use "+str(use)]
	out_time=tval[0]+" "+tval[1]
	out_dom=dval[0]+" "+dval[1]
	out_file=uval[0]+" "+uval[1]

	return MODELS[model],stash_code,name,units,CMOR_name,out_dom,out_time,out_file

#----------------------------------------------------
def lookupSTASH(stash_code,model_id):
 	csvfile=open(stash_lookup,'rb')
        ref_stash = csv.DictReader(csvfile)
        csvfile.close
	name=""
	CMOR_name=""
	units=""

	for row in ref_stash:
	   if row["STASH"]==str(stash_code) and row["ID"]==str(model_id):
		name=row["STASHmaster description"]
		CMOR_name=row["CF standard name"]
		units=row["Units"]
	return name,units,CMOR_name

#----------------------------------------------------
if __name__ == "__main__":
        # Firstly read any command line options
        ProcessCommandLineOpts()

	timeDict=ReadTimes(Vars.stashfile)
	domDict=ReadDomains(Vars.stashfile)
	useDict=ReadUses(Vars.stashfile)
	ReadStash(Vars.stashfile,timeDict,domDict,useDict)
        
	print "Finished!"


