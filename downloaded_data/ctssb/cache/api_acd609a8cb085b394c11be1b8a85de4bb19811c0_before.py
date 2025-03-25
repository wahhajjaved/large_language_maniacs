#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
Created on Mar 13, 2013

@author: Benjamin Yvernault, Electrical Engineering, Vanderbilt University
'''

import os,sys,re
from datetime import datetime
from pyxnat import Interface
from task import READY_TO_COMPLETE, COMPLETE, UPLOADING
import subprocess
from subprocess import CalledProcessError
from email.mime.text import MIMEText
from email.MIMEBase import MIMEBase
import smtplib
from email import Encoders

def parse_args():
    from optparse import OptionParser
    usage = "usage: %prog [options] \nWhat is the script doing : Upload Data on Xnat from a Directory as an Assessor. "
    parser = OptionParser(usage=usage)
    parser.add_option("-e", "--emailaddress", dest="emailaddress",default='',
                  help="Email address to prevent if an assessor already exists.", metavar="EMAIL ADDRESS")
    return parser.parse_args()

def sendMail(FROM,PWS,TO,SUBJECT,TEXT,SERVER,filename='nan'):
    """send an email from FROM (with the password PWS) to TO with the subject and text given.
    
    parameters:
        - FROM = email address from where the e-amil is sent
        - PWS = password of the email address
        - TO = list of email address which will receive the email
        - SUBJECT =  subject of the email
        - TEXT = inside of the email
        - server = server used to send the email
        - filename = fullpath to a file that need to be attached
    """
    # Create the container (outer) email message.
    msg = MIMEText(TEXT)
    msg['Subject'] = SUBJECT
    # me == the sender's email address
    # family = the list of all recipients' email addresses
    msg['From'] = FROM
    msg['To'] = TO
    
    #attached the file if one :
    if filename!='nan':
        part = MIMEBase('application', "octet-stream")
        part.set_payload( open(filename,"rb").read() )
        Encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment; filename="%s"' % os.path.basename(filename))
        msg.attach(part)
    
    # Send the email via our own SMTP server.
    s = smtplib.SMTP(SERVER)
    s.starttls()
    s.login(FROM,PWS)
    s.sendmail(FROM, TO, msg.as_string())
    s.quit()

def get_assessor_name_from_folder():
    #Get the assessor label from the folders in Upload Directory that are ready to be upload
    
    #Upload Directory 
    try:
        UploadDir = os.environ['UPLOAD_SPIDER_DIR']
    except KeyError as e:
        print "You must set the environment variable %s" % str(e)
        sys.exit(1) 
    
    #list of assessor label
    assessor_label_list=list()
    
    print ' -Get Processes names from the upload folder...'
    #check all files/folder in the directory
    UploadDirList=os.listdir(UploadDir)
    for assessor_label in UploadDirList:
        assessor_path=UploadDir+'/'+assessor_label
        #if it's a folder and not OUTLOG and the flag file READY_TO_UPLAOD exists
        if os.path.isdir(assessor_path) and assessor_label!='OUTLOG' and assessor_label!='TRASH' and assessor_label!='PBS' and assessor_label!='FlagFiles' and (os.path.exists(os.path.join(assessor_path,'READY_TO_UPLOAD.txt')) or os.path.exists(os.path.join(assessor_path,'JOB_FAILED.txt'))):
            if not os.path.exists(assessor_path+'/ALREADY_SEND_EMAIL.txt'):
                #it's a folder for an assessor:
                assessor_label_list.append(assessor_label)
            
    return assessor_label_list

def get_outlog_from_folder():
    #Get the outlog files which need to be upload
    
    #Upload Directory 
    try:
        UploadDir = os.environ['UPLOAD_SPIDER_DIR']
    except KeyError as e:
        print "You must set the environment variable %s" % str(e)
        sys.exit(1) 
    
    #list of assessor label
    outlog_list=list()
    
    print ' -Get the OUTLOG for the processes...'
    #check all files/folder in the directory
    OutlogDirList=os.listdir(UploadDir+'/OUTLOG')
    for outlog_name in OutlogDirList:
        outlog_file=os.path.join(UploadDir,'OUTLOG',outlog_name)
        #if it's a folder and not OUTLOG and the flag file READY_TO_UPLAOD exists
        if os.path.isfile(outlog_file):
            #Add the file to the list to be uploaded:
            outlog_list.append(outlog_name)
            
    return outlog_list

def get_pbs_from_folder():
    #Get the pbs files which need to be upload
    
    #Upload Directory 
    try:
        UploadDir = os.environ['UPLOAD_SPIDER_DIR']
    except KeyError as e:
        print "You must set the environment variable %s" % str(e)
        sys.exit(1) 
    
    #list of assessor label
    pbs_list=list()
    
    print ' -Get the PBS for the processes...'
    #check all files/folder in the directory
    PBSDirList=os.listdir(UploadDir+'/PBS')
    for pbs_name in PBSDirList:
        pbs_file=UploadDir+'/PBS/'+pbs_name
        #if it's a folder and not OUTLOG and the flag file READY_TO_UPLAOD exists
        if os.path.isfile(pbs_file):
            #add the file to the list to be uploaded
            pbs_list.append(pbs_name)
            
    return pbs_list

def check_process(process_file):
    if process_file=='Process_Upload_running.txt':
        return 0
    elif 'OPEN_TASKS_UPDATE' in process_file:
        project_name=process_file.split('_OPEN_TASKS_UPDATE_RUNNING')[0]
        cmd = 'ps -aux | grep "api/cci/update_open_tasks.py" | grep "'+project_name+'"'
    else:
        project_name=process_file.split('_UPDATE_RUNNING')[0]
        cmd = 'ps -aux | grep "api/cci/update.py" | grep "'+project_name+'"'
    
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=True)
        if len(output.split('\n'))>3:
            #three because one is warning, two is the line we just do (ps -aux ...) and three is empty line
            #there is a process running
            return 0
        else:
            #no process, send an email
            return 1
    except (CalledProcessError,ValueError):
        #error , send an email
        return 1

def check_crontab_job(UploadDir):
    flag_files_list=list()
    for files in os.listdir(os.path.join(UploadDir,'FlagFiles')):
        print '   - Check '+files
        #check if there is a process for this file, if not send a warning to the User
        keep=check_process(files)
        if keep:
            print "    --> Process doesn't seem to be running. ERROR. Need to be checked."
            flag_files_list.append(files)
            
    return flag_files_list
            
def Uploading_Assessor(xnat,assessor_path,ProjectName,Subject,Experiment,assessor_label,version):
    #SNAPSHOTS :
    #Check if the SNAPSHOTS folder exists, if not create one from PDF if pdf exists :
    if not os.path.exists(assessor_path+'/SNAPSHOTS/') and os.path.exists(assessor_path+'/PDF/'):
        print '    +creating original of SNAPSHOTS'
        os.system('mkdir '+assessor_path+'/SNAPSHOTS/')
        #Make the snapshots for the assessors with ghostscript
        snapshot_original = assessor_path+'/SNAPSHOTS/snapshot_original.png'
        os.system('gs -q -o '+snapshot_original+' -sDEVICE=pngalpha -dLastPage=1 '+assessor_path+'/PDF/*.pdf')
    
    #Create the preview snapshot from the original if Snapshots exist :
    if os.path.exists(assessor_path+'/SNAPSHOTS/'):
        Assessor_Resource_List=os.listdir(assessor_path+'/SNAPSHOTS/')
        for snapshot in Assessor_Resource_List:
            if len(snapshot.split('original'))>1:
                print '    +creating preview of SNAPSHOTS'
                #Name of the preview snapshot
                snapshot_preview = assessor_path+'/SNAPSHOTS/preview.'+snapshot.split('.')[1]
                #Make the snapshot_thumbnail
                os.system('convert '+assessor_path+'/SNAPSHOTS/'+snapshot+' -resize x200 '+snapshot_preview)                  
    
    #Select the experiment
    experiment = xnat.select('/project/'+ProjectName+'/subjects/'+Subject+'/experiments/'+Experiment)
        
    #Select the assessor
    assessor=experiment.assessor(assessor_label)
    
    #set version:
    assessor.attrs.set('proc:genProcData/procversion', version)
    
    #UPLOAD files :                
    Assessor_Resource_List=os.listdir(assessor_path)    
    #for each folder=resource in the assessor directory 
    for Resource in Assessor_Resource_List:
        Resource_path=assessor_path+'/'+Resource
        
        #Need to be in a folder to create the resource :
        if os.path.isdir(Resource_path):
            print '    +uploading '+Resource
            #check if the resource exist, if yes remove it
            if assessor.out_resource(Resource).exists():
                assessor.out_resource(Resource).delete()
            
            #create the resource
            r = assessor.out_resource(Resource)
                
            #if it's the SNAPSHOTS folder, need to set the thumbnail and original:
            if Resource=='SNAPSHOTS':
                #for each files in this folderl, Upload files in the resource :
                Resource_files_list=os.listdir(Resource_path)
                preview = [s for s in Resource_files_list if "preview" in s][0]
                r.file(preview).put(Resource_path+'/'+preview,(preview.split('.')[1]).upper(),'THUMBNAIL')
                os.remove(Resource_path+'/'+preview)
                original = [s for s in Resource_files_list if "original" in s][0]
                r.file(original).put(Resource_path+'/'+original,(original.split('.')[1]).upper(),'ORIGINAL')
                os.remove(Resource_path+'/'+original)
                if len(os.listdir(Resource_path))>2:
                    upload_zip(Resource,Resource_path,r)
                    
            #for all the other resources :
            else:
                #for each files in this folderl, Upload files in the resource :
                Resource_files_list=os.listdir(Resource_path)
                #for each folder=resource in the assessor directory, more than 2 files, use the zip from XNAT
                if len(Resource_files_list)>2:
                    upload_zip(Resource,Resource_path,r)
                #One or two file, let just upload them:
                else:
                    for filename in Resource_files_list:
                        #if it's a folder, zip it and upload it
                        if os.path.isdir(filename):
                            upload_zip(filename,Resource_path+'/'+filename,r)
                        elif filename.lower().endswith('.zip'):
                            r.put_zip(Resource_path+'/'+filename, extract=True)
                        else:
                            #upload the file
                            r.file(filename).put(Resource_path+'/'+filename)
                        
    #upload finish
    if os.path.exists(os.path.join(assessor_path,'READY_TO_UPLOAD.txt')):
        assessor.attrs.set('proc:genProcData/procstatus', READY_TO_COMPLETE)
    os.system('rm -r '+assessor_path)

def Uploading_OUTLOG(outlog_list,xnat):
    number_outlog=len(outlog_list)
    for index,outlogfile in enumerate(outlog_list):
        print'   *Uploading OUTLOG '+str(index+1)+'/'+str(number_outlog)+' -- File name: '+outlogfile
        #Get the Project Name, the subject label, the experiment label and the assessor label from the file name :
        labels=outlogfile.split('-x-')
        ProjectName=labels[0]
        Subject=labels[1]
        Experiment=labels[2]
        assessor_label=outlogfile.split('.')[0]
        
        #connect to the experiment
        experiment = xnat.select('/project/'+ProjectName+'/subjects/'+Subject+'/experiments/'+Experiment)
        if experiment.exists():
            #ASSESSOR
            assessor=experiment.assessor(assessor_label)
            #if the assessors doesn't exist send an email
            if assessor.exists():
                r=assessor.out_resource('OUTLOG')
                    
                if r.exists():
                    print 'WARNING : the OUTLOG resource already exists for the assessor '+assessor_label
                    #check if there is a folder with the same name : if yes, put the outlog there. If not upload it.
                    if  os.path.isdir(os.path.join(UploadDir,assessor_label)):
                        print 'WARNING: Copying the outlog file in the assessor folder...'
                        assessor_outlog_folder=os.path.join(UploadDir,assessor_label,'OUTLOG')
                        if not os.path.exists(assessor_outlog_folder):
                            os.mkdir(assessor_outlog_folder)
                        os.system('mv '+os.path.join(UploadDir,'OUTLOG',outlogfile)+' '+assessor_outlog_folder)
                    else:
                        print 'WARNING: Copying the outlog file in the TRASH ...'
                        os.rename(os.path.join(UploadDir,'OUTLOG',outlogfile),os.path.join(UploadDir,'TRASH',outlogfile))
                else:
                    #upload the file
                    r=assessor.out_resource('OUTLOG')
                    r.file(outlogfile).put(os.path.join(UploadDir,'OUTLOG',outlogfile))
                    os.remove(os.path.join(UploadDir,'OUTLOG',outlogfile))
            else:
                print 'ERROR: The assessor '+assessor_label+' does not exist. Copy to TRASH.'
                os.rename(os.path.join(UploadDir,'OUTLOG',outlogfile),os.path.join(UploadDir,'TRASH',outlogfile))
                
        else:
            print 'ERROR: The Output PBS file '+outlogfile+' has a wrong ProjectName or Subject label or Experiment label in his name. Copy to TRASH.'
            os.rename(os.path.join(UploadDir,'OUTLOG',outlogfile),os.path.join(UploadDir,'TRASH',outlogfile))

def Uploading_PBS(pbs_list,xnat):
    number_pbs=len(pbs_list)
    for index,pbsfile in enumerate(pbs_list):
        print'   *Uploading PBS '+str(index+1)+'/'+str(number_pbs)+' -- File name: '+pbsfile
        #Get the Project Name, the subject label, the experiment label and the assessor label from the file name :
        labels=pbsfile.split('-x-')
        ProjectName=labels[0]
        Subject=labels[1]
        Experiment=labels[2]
        assessor_label=pbsfile.split('.')[0]
        
        #connect to the experiment
        experiment = xnat.select('/project/'+ProjectName+'/subjects/'+Subject+'/experiments/'+Experiment)
        if experiment.exists():
            #ASSESSOR
            assessor=experiment.assessor(assessor_label)
            #if the assessors doesn't exist send an email
            if assessor.exists():
                #remove the previous resource if exists
                r=assessor.out_resource('PBS')
                if r.exists():
                    print 'WARNING : the PBS resource already exists for the assessor '+assessor_label
                    #check if there is a folder with the same name : if yes, put the outlog there. If not upload it.
                    if  os.path.isdir(os.path.join(UploadDir,assessor_label)):
                        print 'WARNING: Copying the pbs file in the assessor folder...'
                        assessor_pbs_folder=os.path.join(UploadDir,assessor_label,'PBS')
                        if not os.path.exists(assessor_pbs_folder):
                            os.mkdir(assessor_pbs_folder)
                        os.system('mv '+os.path.join(UploadDir,'PBS',pbsfile)+' '+assessor_pbs_folder)
                    else:
                        print 'WARNING: Copying the pbs file in the TRASH ...'
                        os.rename(os.path.join(UploadDir,'PBS',pbsfile),os.path.join(UploadDir,'TRASH',pbsfile))
                else:
                    #upload the file
                    r=assessor.out_resource('PBS')
                    r.file(pbsfile).put(UploadDir+'/PBS/'+pbsfile)
                    os.remove(UploadDir+'/PBS/'+pbsfile)
            else:
                print 'ERROR: The assessor '+assessor_label+' does not exist. Copy to TRASH.'
                os.rename(UploadDir+'/PBS/'+pbsfile,UploadDir+'/TRASH/'+pbsfile)
                
        else:
            print 'ERROR: The PBS file '+pbsfile+' has a wrong ProjectName or Subject label or Experiment label in his name. Copy to TRASH.'
            os.rename(UploadDir+'/PBS/'+pbsfile,UploadDir+'/TRASH/'+pbsfile)
    
def Upload_FreeSurfer(xnat,assessor_path,ProjectName,Subject,Experiment,assessor_label,version):
    #SNAPSHOTS :
    #Check if the snapshot exists, if not create one from PDF if pdf exists :
    snapshot_original = assessor_path+'/SNAPSHOTS/snapshot_original.png'
    if not os.path.exists(snapshot_original) and os.path.exists(assessor_path+'/PDF/'):
        print '    +creating original of SNAPSHOTS'
        #Make the snapshots for the assessors with ghostscript
        os.system('gs -q -o '+snapshot_original+' -sDEVICE=pngalpha -dLastPage=1 '+assessor_path+'/PDF/*.pdf')
    
    #Create the preview snapshot from the original if Snapshots exist :
    if os.path.exists(assessor_path+'/SNAPSHOTS/'):
        Assessor_Resource_List=os.listdir(assessor_path+'/SNAPSHOTS/')
        for snapshot in Assessor_Resource_List:
            if len(snapshot.split('original'))>1:
                print '    +creating preview of SNAPSHOTS'
                #Name of the preview snapshot
                snapshot_preview = assessor_path+'/SNAPSHOTS/preview.'+snapshot.split('.')[1]
                #Make the snapshot_thumbnail
                os.system('convert '+assessor_path+'/SNAPSHOTS/'+snapshot+' -resize x200 '+snapshot_preview)                  
    
    #Select the experiment
    experiment = xnat.select('/project/'+ProjectName+'/subjects/'+Subject+'/experiments/'+Experiment)
        
    #Select the assessor
    assessor=experiment.assessor(assessor_label)
    
    # set version:
    assessor.attrs.set('fs:fsData/procversion', version)
    # Upload the XML
    xmlpath=os.path.join(assessor_path,'XML')
    if os.path.exists(xmlpath):
        print '    +uploading XML'
        xml_files_list = os.listdir(xmlpath)
        if len(xml_files_list) != 1:
        	print 'ERROR:cannot upload FreeSufer, unable to find XML file:'+assessor_path
        	return
        xml_path = assessor_path+'/XML/'+xml_files_list[0]
        assessor.create(xml=xml_path, allowDataDeletion=False)
    
    #UPLOAD files :                
    Assessor_Resource_List=os.listdir(assessor_path)    
    #for each folder=resource in the assessor directory 
    for Resource in Assessor_Resource_List:
        Resource_path=assessor_path+'/'+Resource
        
        #Need to be in a folder to create the resource :
        if os.path.isdir(Resource_path):
            print '    +uploading '+Resource
            #check if the resource exist, if yes remove it
            if assessor.out_resource(Resource).exists():
                assessor.out_resource(Resource).delete()
            
            #create the resource
            r = assessor.out_resource(Resource)
                
            #if it's the SNAPSHOTS folder, need to set the thumbnail and original:
            if Resource=='SNAPSHOTS':
                #for each files in this folderl, Upload files in the resource :
                Resource_files_list=os.listdir(Resource_path)
                preview = [s for s in Resource_files_list if "preview" in s][0]
                r.file(preview).put(os.path.join(Resource_path,preview),(preview.split('.')[1]).upper(),'THUMBNAIL')
                os.remove(os.path.join(Resource_path,preview))
                original = [s for s in Resource_files_list if "original" in s][0]
                r.file(original).put(os.path.join(Resource_path,original),(original.split('.')[1]).upper(),'ORIGINAL')
                os.remove(os.path.join(Resource_path,original))
                if len(os.listdir(Resource_path))>2:
                    upload_zip(Resource,Resource_path,r)
                    
            #for all the other resources :
            else:
                #for each files in this folderl, Upload files in the resource :
                Resource_files_list=os.listdir(Resource_path)
                
                #for each folder=resource in the assessor directory, more than 2 files, use the zip from XNAT
                if len(Resource_files_list)>2:
                    upload_zip(Resource,Resource_path,r)
                #One or two file, let just upload them:
                else:
                    for filename in Resource_files_list:
                        #if it's a folder, zip it and upload it
                        if os.path.isdir(filename):
                            upload_zip(filename,Resource_path+'/'+filename,r)
                        elif filename.lower().endswith('.zip'):
                        	r.put_zip(Resource_path+'/'+filename, extract=True)
                        else:
                            #upload the file
                            r.file(filename).put(Resource_path+'/'+filename)
      
    #upload finish
    if os.path.exists(os.path.join(assessor_path,'READY_TO_UPLOAD.txt')):
        assessor.attrs.set('fs:fsdata/procstatus',READY_TO_COMPLETE)
    os.system('rm -r '+assessor_path)
    
def upload_zip(Resource,directory,resourceObj):
    filenameZip=Resource+'.zip'
    initDir=os.getcwd()
    #Zip all the files in the directory
    os.chdir(directory)
    os.system('zip '+filenameZip+' *')
    #upload
    print '      *Uploading zip '+Resource+' ...'
    resourceObj.put_zip(directory+'/'+filenameZip,extract=True)
    #return to the initial directory:
    os.chdir(initDir)
    
def get_version_assessor(assessor_path):
    f=open(os.path.join(assessor_path,'version.txt'),'r')
    version=f.read().strip()
    f.close()
    return version
    
#########################################################################################################################################################
###############################################################  MAIN FUNCTION ##########################################################################
#########################################################################################################################################################

if __name__ == '__main__':
    
    ################### Script for Upload FILES on Assessor on Xnat ######################
    (options,args) = parse_args()
    emailaddress = options.emailaddress
    
    #Email variables :
    send_an_email=0;
    flag_files_list=list()
    warning_list=list()
    TEXT=None
    
    print 'Time at the beginning of the Process_Upload: ', str(datetime.now()),'\n'

    #Upload Directory for Spider_Process_Upload.py
    try:
        # Environs
        VUIISxnat_user = os.environ['XNAT_USER']
        VUIISxnat_pwd = os.environ['XNAT_PASS']
        VUIISxnat_host = os.environ['XNAT_HOST']
        VUEMAIL_ADDR = os.environ['EMAIL_ADDR']
        VUEMAIL_PWS = os.environ['EMAIL_PWS']
        UploadDir = os.environ['UPLOAD_SPIDER_DIR']
    except KeyError as e:
        print "You must set the environment variable %s" % str(e)
        sys.exit(1) 
    
    #make the two special directory
    if not os.path.exists(UploadDir):
        os.mkdir(UploadDir)
    if not os.path.exists(os.path.join(UploadDir,'OUTLOG')):
        os.mkdir(os.path.join(UploadDir,'OUTLOG'))
    if not os.path.exists(os.path.join(UploadDir,'TRASH')):
        os.mkdir(os.path.join(UploadDir,'TRASH'))
    if not os.path.exists(os.path.join(UploadDir,'PBS')):
        os.mkdir(os.path.join(UploadDir,'PBS'))
    if not os.path.exists(os.path.join(UploadDir,'FlagFiles')):
        os.mkdir(os.path.join(UploadDir,'FlagFiles'))
    
    #check if this spider is still running for the former called by checking the flagfile Spider_Process_Upload_running.txt
    if not os.path.exists(os.path.join(UploadDir,'FlagFiles','Process_Upload_running.txt')):
        #create the flag file showing that the spider is running 
        f=open(os.path.join(UploadDir,'FlagFiles','Process_Upload_running.txt'), 'w')
        today=datetime.now()
        datestr="Date: "+str(today.year)+str(today.month)+str(today.day)+'_'+str(today.hour)+':'+str(today.minute)+':'+str(today.second)
        f.write(datestr+'\n')
        f.close()
        
        try:
            #Start Uploading
            print '-------- Upload Directory: '+UploadDir+' --------'
            ###VARIABLES###
            #Check if the folder is not empty
            UploadDirList=os.listdir(UploadDir)
            if len(UploadDirList)==0:
                print 'WARNING: No data need to be upload.\n'
            else:
                #Get the assessor label from the directory :
                assessor_label_in_dir_list=get_assessor_name_from_folder()
                #Get the list of OUTLOG which need to be upload:
                outlog_list=get_outlog_from_folder()
                #Get the list of OUTLOG which need to be upload:
                pbs_list=get_pbs_from_folder()

                #Start the process to upload
                try:
                    print 'INFO: Connecting to XNAT to start uploading processes at '+VUIISxnat_host
                    xnat = Interface(VUIISxnat_host, VUIISxnat_user, VUIISxnat_pwd)
                    
                    ################# 1) Upload the assessor data ###############
                    #For each assessor label that need to be upload :
                    number_of_processes=len(assessor_label_in_dir_list)
                    for index,assessor_label in enumerate(assessor_label_in_dir_list):
                        assessor_path=UploadDir+'/'+assessor_label
                        if os.path.isdir(assessor_path):
                            sys.stdout.flush()
                            sys.stdout.write("    *Process: "+str(index+1)+"/"+str(number_of_processes)+' -- label: '+assessor_label+' / time: '+str(datetime.now())+'\n')
                            #Get the Project Name, the subject label, the experiment label and the assessor label from the folder name :
                            labels=assessor_label.split('-x-')
                            ProjectName=labels[0]
                            Subject=labels[1]
                            Experiment=labels[2]
                            #The Process name is the last labels
                            Process_name=labels[-1]
                            #get spiderpath from version.txt file:
                            version = get_version_assessor(assessor_path)
                            
                            #check if subject/experiment exists on XNAT
                            EXPERIMENT = xnat.select('/project/'+ProjectName+'/subjects/'+Subject+'/experiments/'+Experiment)
                            
                            if EXPERIMENT.exists():
                                #ASSESSOR in the experiment
                                ASSESSOR=EXPERIMENT.assessor(assessor_label)
                                
                                #existence :
                                if not ASSESSOR.exists():
                                    if Process_name=='FS':
                                        #create the assessor and set the status 
                                        ASSESSOR.create(assessors='fs:fsData')
                                        #Set attributes
                                        if os.path.exists(os.path.join(assessor_path,'READY_TO_UPLOAD.txt')):
                                            ASSESSOR.attrs.set('fs:fsData/procstatus','UPLOADING') #Set to uploading files
                                        elif os.path.exists(os.path.join(assessor_path,'JOB_FAILED.txt')):
                                            ASSESSOR.attrs.set('fs:fsData/procstatus','JOB_FAILED') #Set to uploading files
                                        ASSESSOR.attrs.set('fs:fsData/validation/status','Job Pending')
                                        ASSESSOR.attrs.set('fs:fsData/proctype', 'FreeSurfer_v'+version.split('.')[0])
                                        ASSESSOR.attrs.set('fs:fsData/procversion', version)
                                        now=datetime.now()
                                        today=str(now.year)+'-'+str(now.month)+'-'+str(now.day)
                                        ASSESSOR.attrs.set('fs:fsData/date',today)
                                    else:
                                        #create the assessor and set the status 
                                        ASSESSOR.create(assessors='proc:genProcData')
                                        #Set attributes
                                        if os.path.exists(os.path.join(assessor_path,'READY_TO_UPLOAD.txt')):
                                            ASSESSOR.attrs.set('proc:genProcData/procstatus','UPLOADING') #Set to uploading files
                                        elif os.path.exists(os.path.join(assessor_path,'JOB_FAILED.txt')):
                                            ASSESSOR.attrs.set('proc:genProcData/procstatus','JOB_FAILED') #Set to uploading files
                                        ASSESSOR.attrs.set('proc:genProcData/validation/status','Job Pending')
                                        ASSESSOR.attrs.set('proc:genProcData/proctype', Process_name)
                                        ASSESSOR.attrs.set('proc:genProcData/procversion', version)
                                        now=datetime.now()
                                        today=str(now.year)+'-'+str(now.month)+'-'+str(now.day)
                                        ASSESSOR.attrs.set('proc:genProcData/date',today)
                                
                                else:
                                    ################# FreeSurfer #################
                                    if Process_name=='FS':      
                                        if ASSESSOR.attrs.get('fs:fsData/procstatus')=='READY_TO_COMPLETE' or ASSESSOR.attrs.get('fs:fsData/procstatus')=='COMPLETE':
                                            if not os.path.exists(assessor_path+'/ALREADY_SEND_EMAIL.txt'):
                                                open(assessor_path+'/ALREADY_SEND_EMAIL.txt', 'w').close()
                                            print '  -->Data already present on XNAT.\n'
                                            warning_list.append('\t- Project : '+ProjectName+' / Subject : '+Subject+' / Experiment : '+Experiment+' / Assessor label : '+ assessor_label+'\n')
                                        else:
                                            #set the status to Upload :
                                            if os.path.exists(os.path.join(assessor_path,'READY_TO_UPLOAD.txt')):
                                                ASSESSOR.attrs.set('fs:fsData/procstatus', UPLOADING)
                                            Upload_FreeSurfer(xnat,assessor_path,ProjectName,Subject,Experiment,assessor_label,version)
                                    ################# Default Assessor #################
                                    else:
                                        if ASSESSOR.attrs.get('proc:genProcData/procstatus')=='READY_TO_COMPLETE' or ASSESSOR.attrs.get('proc:genProcData/procstatus')=='COMPLETE':
                                            if not os.path.exists(assessor_path+'/ALREADY_SEND_EMAIL.txt'):
                                                open(assessor_path+'/ALREADY_SEND_EMAIL.txt', 'w').close()
                                            print 'Data already exist.\n'
                                            warning_list.append('\t- Project : '+ProjectName+' / Subject : '+Subject+' / Experiment : '+Experiment+' / Assessor label : '+ assessor_label+'\n')
                                        else:
                                            #set the status to Upload :
                                            if os.path.exists(os.path.join(assessor_path,'READY_TO_UPLOAD.txt')):
                                                ASSESSOR.attrs.set('proc:genProcData/procstatus', UPLOADING)
                                            Uploading_Assessor(xnat,assessor_path,ProjectName,Subject,Experiment,assessor_label,version)
                                    
                            else:
                                print 'ERROR: The folder '+assessor_label+' has a wrong ProjectName or Subject label or Experiment label.'
                      
                    ################# 2) Upload the Outlog files ###############
                    #For each file, upload it to the OUTLOG resource on the assessor
                    print ' - Uploading OUTLOG files ...'
                    Uploading_OUTLOG(outlog_list,xnat)
                    
                    ################# 3) Upload the PBS files ###############
                    #For each file, upload it to the PBS resource
                    print ' - Uploading PBS files ...'
                    Uploading_PBS(pbs_list,xnat)
                    
                    ################# 4) Check flagfile and process running ps -aux ################
                    print ' - Checking process running ...'
                    flag_files_list=check_crontab_job(UploadDir)
                    
                #if fail, close the connection to xnat
                finally:
                    #Sent an email
                    if (warning_list or flag_files_list)  and emailaddress!='' :
                        if warning_list:
                            TEXT='\nThe following assessor already exists and the Spider try to upload files on existing files :\n'
                            for warning in warning_list:
                                TEXT+=' - '+warning+'\n'
                            TEXT+='\nYou should :\n\t-remove the assessor if you want to upload the data \n\t-set the status of the assessor to "uploading" \n\t-remove the data from the upload folder if you do not want to upload this data.\n'
                        SUBJECT='ERROR/WARNING: XNAT Process Upload'
                        if flag_files_list:
                            if not TEXT:
                                TEXT='\nCheck the following processes if they are still running:\n'
                            else:
                                TEXT+='Check the following process if they are still running:\n'
                            for files in flag_files_list:
                                TEXT+=' - '+files+'\n'
                        sendMail(VUEMAIL_ADDR,VUEMAIL_PWS,emailaddress,SUBJECT,TEXT,'smtp.gmail.com')   
                        
                    #disconnect                                     
                    xnat.disconnect()
                    print 'INFO: Connection to Xnat closed'  
        
        #Stop the process before the end or end of the script, remove the flagfile for the spider running 
        finally:
            #remove flagfile
            os.remove(os.path.join(UploadDir,'FlagFiles','Process_Upload_running.txt'))
            print '===================================================================\n'
    else:
        print 'WARNING: Upload already running.'
        
