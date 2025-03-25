#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" launcher.py

"""
__copyright__ = 'Copyright 2013 Vanderbilt University. All Rights Reserved'

import os,sys
from pyxnat import Interface
from processors import ScanProcessor,SessionProcessor
import processors
import modules
import XnatUtils
import task
import cluster
from task import Task
from datetime import datetime, timedelta

DEFAULT_QUEUE_LIMIT = 900
DEFAULT_ROOT_JOB_DIR = '/tmp'
UPDATE_LOCK_FILE  = 'UPDATE_RUNNING.txt'
OPEN_TASKS_LOCK_FILE  = 'OPEN_TASKS_UPDATE_RUNNING.txt'
UPDATE_FIELD = 'src'
UPDATE_FORMAT = "%Y-%m-%d %H:%M:%S"
UPDATE_PREFIX = 'updated--'

#TODO: add sort options

class Launcher(object):
    def __init__(self,project_process_dict,project_modules_dict,queue_limit=DEFAULT_QUEUE_LIMIT, root_job_dir=DEFAULT_ROOT_JOB_DIR, xnat_user=None, xnat_pass=None, xnat_host=None, upload_dir=None, job_email=None,job_email_options='bae'):
        self.queue_limit = queue_limit
        self.root_job_dir = root_job_dir
        self.project_process_dict = project_process_dict
        self.project_modules_dict = project_modules_dict
        self.job_email=job_email
        self.job_email_options=job_email_options

        try:
            if xnat_user == None:
                self.xnat_user = os.environ['XNAT_USER']
            else:
                self.xnat_user = xnat_user
                
            if xnat_pass == None:
                self.xnat_pass = os.environ['XNAT_PASS']
            else:
                self.xnat_pass = xnat_pass
                
            if xnat_host == None:
                self.xnat_host = os.environ['XNAT_HOST']
            else:
                self.xnat_host = xnat_host
        
            if upload_dir == None:
                self.upload_dir = os.environ['UPLOAD_SPIDER_DIR']
            else:
                self.upload_dir = upload_dir

        except KeyError as e:
            print("You must set the environment variable %s" % str(e))
            sys.exit(1)  
        
        #if project_process_dict == None:
            # TODO: get the default list of processors and get list of project 
            # this user has access to process here we could have the masispider 
            # user get all the projects it can access, so then users could just 
            # add masispider as a member of their project and it would process 
            # their data,good idea???

        # TODO: check the project process list
        # TODO: check that projects exist
        
    def update_open_tasks(self, lockfile_prefix):
        task_queue = []
        
        print('\n-------------- Open Tasks Update --------------')
        
        success = self.lock_open_tasks(lockfile_prefix)   
        if not success:
            print('ERROR:failed to get lock on open tasks update')
            exit(1)                              

        try:
            print('Connecting to XNAT at '+self.xnat_host)
            xnat = Interface(self.xnat_host, self.xnat_user, self.xnat_pass)
            
            print('Getting task list...')
            task_list = self.get_open_tasks(xnat)
            
            print(str(len(task_list))+' open jobs found')

            print('Updating tasks...')
            for cur_task in task_list:
                print('     Updating task:'+cur_task.assessor_label)
                task_status = cur_task.update_status()
                if task_status == task.NEED_TO_RUN:
                    task_queue.append(cur_task)
                    
            print(str(len(task_queue))+' jobs ready to be launched')
        
            #===== Sort the task queue as desired - random? breadth-first? depth-first? 
            #task_queue.sort()
                        
            # Launch jobs
            self.launch_jobs(task_queue)
            
        finally:       
            self.unlock_open_tasks(lockfile_prefix)                                                      
            xnat.disconnect()
            print('Connection to XNAT closed')

                           
    def module_prerun(self,projectID,settings_filename=''):  
        if projectID not in self.project_modules_dict:
            return
        
        for mod in self.project_modules_dict[projectID]:
            #save the modules to redcap project vuiis xnat job before the prerun:
            data,record_id=XnatUtils.create_record_redcap(projectID, mod.getname())
            run=XnatUtils.save_job_redcap(data,record_id)
            if not run:
                print(' ->ERROR: did not send the job to redcap for <'+mod.getname()+'> : '+record_id)
                
            mod.prerun(settings_filename)
            
    def module_afterrun(self,xnat,projectID):    
        if projectID not in self.project_modules_dict:
            return
        
        # for all of the module
        for mod in self.project_modules_dict[projectID]:
            mod.afterrun(xnat,projectID)
    
    def get_open_tasks(self, xnat):
        task_list = []
        project_list = list(self.project_process_dict.keys())
        
        # iterate projects
        for projectid in project_list:
            print('===== PROJECT:'+projectid+' =====')          

            # Get lists of processors for this project
            sess_proc_list, scan_proc_list = processors.processors_by_type(self.project_process_dict[projectid])
            
            # Get lists of assessors for this project
            assr_list  = XnatUtils.list_project_assessors(xnat, projectid)
            
            # Match each assessor to a processor, get a task, and add to list
            for assr_info in assr_list: 
                if assr_info['procstatus'] not in task.OPEN_STATUS_LIST and assr_info['qcstatus'] not in task.OPEN_QC_LIST:
                    continue
                
                task_proc = self.match_proc(xnat, assr_info, sess_proc_list, scan_proc_list)
                             
                if task_proc == None:
                    print('WARN:no matching processor found:'+assr_info['assessor_label'])
                    continue
              
                # Get a new task with the matched processor
                assr = XnatUtils.get_full_object(xnat, assr_info)
                cur_task = Task(task_proc,assr,self.upload_dir)
                task_list.append(cur_task)      
                                        
        return task_list
    
    def match_proc(self, xnat, assr_info, sess_proc_list, scan_proc_list):         
        # Look for a match in sess processors
        for sess_proc in sess_proc_list:
            if sess_proc.xsitype == assr_info['xsiType'] and sess_proc.name == assr_info['proctype']:
                return sess_proc
                    
        # Look for a match in scan processors
        for scan_proc in scan_proc_list:
            if scan_proc.xsitype == assr_info['xsiType'] and scan_proc.name == assr_info['proctype']:
                return scan_proc
                    
        return None     
    
    def update(self, lockfile_prefix):        
        print('\n-------------- Update --------------')
        
        success = self.lock_update(lockfile_prefix)
        if not success:
            print('ERROR:failed to get lock on new update')
            exit(1)   
        
        try:
            print('Connecting to XNAT at '+self.xnat_host)
            xnat = Interface(self.xnat_host, self.xnat_user, self.xnat_pass)
            
            task_list = []
            project_list = sorted(set(self.project_process_dict.keys() + self.project_modules_dict.keys()))
  
            # Update projects
            for project_id in project_list:  
                print('===== PROJECT:'+project_id+' =====')         
               
                self.update_project(xnat, project_id, lockfile_prefix)
                
        finally:  
                self.unlock_update(lockfile_prefix)                                 
                xnat.disconnect()
                print('Connection to XNAT closed')
                
    def update_project(self, xnat, project_id, lockfile_prefix):
        exp_mod_list, scan_mod_list = [],[]
        exp_proc_list, scan_proc_list = [],[]

        # Get lists of modules/processors per scan/exp for this project
        if project_id in self.project_modules_dict:
            #Modules prerun
            self.module_prerun(project_id, lockfile_prefix)
            exp_mod_list, scan_mod_list = modules.modules_by_type(self.project_modules_dict[project_id])            
            
        if project_id in self.project_process_dict:        
            exp_proc_list, scan_proc_list = processors.processors_by_type(self.project_process_dict[project_id])   
            
        # Update each subject
        for subject in XnatUtils.list_subjects(xnat, project_id):
            last_mod = datetime.strptime(subject['last_modified'][0:19], '%Y-%m-%d %H:%M:%S')
            last_up = self.get_subj_lastupdate(subject)
                                        
            if (last_up != None and last_mod < last_up):
                print(' +Subject:'+subject['label']+': skipping, last_mod='+str(last_mod)+',last_up='+str(last_up))
                continue
            
            print(' +Subject:'+subject['label']+': updating...')
            # NOTE: we set update time here, so if the subject is changed below it will be checked again      
            self.set_subj_lastupdate(XnatUtils.get_full_object(xnat, subject))
            self.update_subject(xnat, subject, exp_proc_list, scan_proc_list, exp_mod_list, scan_mod_list)
            
        # Modules after run
        if project_id in self.project_modules_dict:
            self.module_afterrun(xnat,project_id)
    
    def update_subject(self, xnat, subj_info, sess_proc_list, scan_proc_list, sess_mod_list, scan_mod_list):
        proj_id = subj_info['project']
        subj_id = subj_info['ID']
        
        # iterate experiments
        for sess_info in XnatUtils.list_experiments(xnat, proj_id, subj_id):
            sess_id = sess_info['ID']
            subj_label = sess_info['subject_label']
            sess_label = sess_info['label']
            scan_list = []
            task_list = []
            
            print('  +SESS:'+sess_info['label']+':updating...')
                       
            if scan_proc_list or scan_mod_list:
                scan_list = XnatUtils.list_scans(xnat, proj_id, subj_id, sess_id)

            # Modules - run
            for sess_mod in sess_mod_list:
                print'      * Module: '+sess_mod.getname()
                if (sess_mod.needs_run(sess, xnat)):
                    sess_mod.run(xnat,proj_id,subj_label,sess_label)
                
            for scan in scan_list:
                print'      +SCAN: '+scan['scan_id']
                for scan_mod in scan_mod_list:
                    print'        * Module: '+scan_mod.getname()
                    if (scan_mod.needs_run(scan, xnat)):
                        scan_mod.run(xnat,proj_id, subj_label, sess_label, scan['scan_id'])
        
            # Processors - get list of tasks
            for sess_proc in sess_proc_list:
                if sess_proc.should_run(sess_info, xnat):
                    sess_task = sess_proc.get_task(xnat, sess_info, self.upload_dir)
                    task_list.append(sess_task)
                
            for scan_info in scan_list:
                for scan_proc in scan_proc_list:
                    if scan_proc.should_run(scan_info):
                        scan_task = scan_proc.get_task(xnat, scan_info, self.upload_dir)
                        task_list.append(scan_task)
                        
            print('    DEBUG:Getting list of processors')

            # Processors - update tasks                   
            for cur_task in task_list:
                print(' Updating task:'+cur_task.assessor_label)
                cur_task.update_status()
                             
    def launch_jobs(self, task_list):
        # Check cluster
        cur_job_count = cluster.count_jobs()
        if cur_job_count == -1:
            print('ERROR:cannot get count of jobs from cluster')
            return
        print(str(cur_job_count)+' jobs currently in queue')
        
        # Launch until we reach cluster limit or no jobs left to launch
        while cur_job_count < self.queue_limit and len(task_list)>0:
            cur_task = task_list.pop()
            
            # Confirm task is still ready to run
            if cur_task.get_status() != task.NEED_TO_RUN:
                continue
            
            print('Launching job:'+cur_task.assessor_label+', currently '+str(cur_job_count)+' jobs in cluster queue')
            success = cur_task.launch(self.root_job_dir,self.job_email,self.job_email_options)
            if(success != True):
                print('ERROR:failed to launch job')

            cur_job_count = cluster.count_jobs()
            if cur_job_count == -1:
                print('ERROR:cannot get count of jobs from cluster')
                return
                
    def lock_open_tasks(self, lockfile_prefix):
        lock_file = os.path.join(self.upload_dir,'FlagFiles',lockfile_prefix+'_'+OPEN_TASKS_LOCK_FILE)
        
        if os.path.exists(lock_file):
            return False
        else:
            open(lock_file, 'w').close()
            return True
        
    def lock_update(self,lockfile_prefix):
        lock_file = os.path.join(self.upload_dir,'FlagFiles',lockfile_prefix+'_'+UPDATE_LOCK_FILE)
        
        if os.path.exists(lock_file):
            return False
        else:
            open(lock_file, 'w').close()
            return True
                
    def unlock_open_tasks(self,lockfile_prefix):
        lock_file = os.path.join(self.upload_dir,'FlagFiles',lockfile_prefix+'_'+OPEN_TASKS_LOCK_FILE)
        
        if os.path.exists(lock_file):
            os.remove(lock_file)
               
    def unlock_update(self,lockfile_prefix):
        lock_file = os.path.join(self.upload_dir,'FlagFiles',lockfile_prefix+'_'+UPDATE_LOCK_FILE)
        
        if os.path.exists(lock_file):
           os.remove(lock_file)
        
    def get_subj_lastupdate(self, subj):
        update_time = subj[UPDATE_FIELD][len(UPDATE_PREFIX):]
        if update_time == '':
            return None
        else:
            return datetime.strptime(update_time, UPDATE_FORMAT)
                        
    def set_subj_lastupdate(self, subject):
        # We set update to one minute into the future since setting update field will change last modified time
        now = (datetime.now() + timedelta(minutes=1)).strftime(UPDATE_FORMAT)
        subject.attrs.set(UPDATE_FIELD, UPDATE_PREFIX+now)
