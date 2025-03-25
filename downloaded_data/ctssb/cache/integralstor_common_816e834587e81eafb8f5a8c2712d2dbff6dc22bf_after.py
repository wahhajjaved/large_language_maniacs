from integralstor_common import common,db,command
from db import execute_iud,read_multiple_rows,read_single_row
from command import execute_with_rc
from crontab import CronTab
import re,time,datetime,socket

"""
  function to create a cron job
  Parameters :
  0 Name of the cron job
  1 Minute 0-59
  2 Hour 0-23 (0 = midnight)
  3 Day 1-31
  4 Month 1-12
  5 Weekday 0-6 (0 = Sunday) 
  6 Command to be executed. do not pass >> logfile 2>&1. It will be autocreated with the cronjob name
  Notes :
  Time value passing : 
    */1 wont work. It will be auto resolved to *. This actually means every 1 minute. So * indicates every time (minute or hour)
    Passing a list of values should be in string format. " '2-4,56',*,*,*,* "
  Command value passing :
    Pass the command along with the log file you want. If no log file is mentioned, the a default log file with the comment id will be generated.

"""


def create_cron(cron_name,min="1",hour='*',day='*',dow='*',month='*',command=None,log_file=None):
  try:
    log_path, err = common.get_log_folder_path()
    if err:
      raise Exception(err)
    cron = CronTab(user='root')
    if log_file is None:
      log_file =  re.sub(" ","_",cron_name)
    command = command + " >> " +log_path+"/"+log_file+ ".log 2>&1"
    job  = cron.new(command=command,comment=cron_name)
    job.setall(min,hour,day,dow,month)
    if job.is_valid():
      job.enable()
      cron.write()
    else:
      raise Exception("Job Not Valid. Please recheck the job created")
  except Exception, e:
    return False, 'Error creating cron entry : %s'%str(e)
  else:
    return True, None


# Function to return all the user created cron
def list_all_cron():
  cron_list = []
  try:
    cron = CronTab(user='root')
    for job in cron:
      if job.comment:
        cron_list.append(job)
  except Exception, e:
    return None, 'Error listing all cron entries : %s'%str(e)
  else:
    return cron_list, None

# Function to find a specific cron by comment / cron_name
def find_cron(name):
  job = None
  try:
    cron = CronTab(user='root')
    job = cron.find_comment(name)
  except Exception,e:
    return None, "Error finding cron entry : %s"%str(e)
  else:
    return job,None

# Delete a cron, given a comment / cron_name 
def delete_cron_with_comment(name):
  try:
    cron = CronTab(user='root')
    cron.remove_all(comment=name)
    cron.write()
  except Exception, e:
    return False, "Error deleting cron entry : %s"%str(e)
  else:
    return True,None

"""
A way to schedule a job to be executed whereever needed.
Parameters :
1. db_path : The database path for which the scheduler tables exist
2. task_name : A Human readable name for a task
3. cmd_list : The list of dict with key and value pairs of the commands that are to be scheuled for execution
4. node : Execute the command on which node. Use * from every node
5. execute_time : The time at which the job has to be executed. Defaults to now timestamp
6. retries : The total number of retries in case if the command fails. Defaults to 3 retries
If retries value is -2, it is a replication job. A long running one and not to be disturbed
"""

def schedule_a_job(db_path,task_name,cmd_list,node=socket.getfqdn(),execute_time=None,retries=3,extra = {}):
  deleteble = 0
  execute_after = -1
  if not task_name or not cmd_list:
    return False, "Parameters not sufficient"
  else:
    try:
      if not execute_time:
        now = execute_time = int(time.time())
      else:
        now = int(time.time())
      if extra:
        if "deleteble" in extra:
          deleteble = extra["deleteble"]
        if "execute_after" in extra:
          execute_after = extra["execute_after"]
         
      cmd =  "insert into scheduler_tasks (task_name,create_time,initiate_time,status,node,deleteble,execute_after) VALUES ('%s','%d','%d','%s','%s','%d','%d');"%(task_name,now,execute_time,"scheduled",node,deleteble,execute_after);
      print cmd
      row_id,err = execute_iud(db_path,[[cmd],],get_rowid=True)
      if row_id and not err:
        error = False
        for cmd in cmd_list:
          for name,command in cmd.iteritems():
            if retries == -2:
              command = command+" &> /tmp/%d.log"%row_id
              cmd =  "insert into scheduler_commands (name,command,task_ref_id,retries) values ('%s','%s','%d','%d');"%(name,command,row_id,retries)
            else:
              cmd =  "insert into scheduler_commands (name,command,task_ref_id,retries) values ('%s','%s','%d','%d');"%(name,command,row_id,retries)
            status,err = execute_iud(db_path,[[cmd],],get_rowid=True)
            if err:
              error = True
              break
        if error:
          return False,err
        else:
          return row_id,None
      else:
        return False,err
    except Exception,e:
      return False,e 

"""
This function is to be called from cron. This will read the scheduler database, and execute all the required queries  do the retries and logs errors and outputs.
"""

def execute_scheduler(db_path,node=socket.getfqdn()):
  now = int(time.time())
  tasks = "select * from scheduler_tasks where node == '"+node+"' and (status == 'scheduled' or status == 'pending') and (initiate_time <= '%d');" %(now)
  try:
    completed = True
    # Iterate all the scheduled tasks
    for task in read_multiple_rows(db_path,tasks)[0]:
      # If there is a dependent command, that is not completed, pass
      if not task['execute_after'] == -1:
        check = 'select status from scheduler_tasks where task_id == "%d"'%task['execute_after']
        status,err = read_single_row(db_path,check)
        status = status['status']
        if not status == "completed":
          continue
      commands = "select * from scheduler_commands where task_ref_id == '%d'"%task['task_id']
      # Iteriate all the commands realted to the task
      for query in read_multiple_rows(db_path,commands)[0]:
        retries = query['retries']
        command_id = query["command_id"]
        # Change the status to running from schdeuled
        status_update = "update scheduler_commands set status = 'running' where command_id = '%d'"%command_id
        status,err = execute_iud(db_path,[[status_update],],get_rowid=True)
        status_update = "update scheduler_tasks set status = 'running' where task_id = '%d'"%task['task_id']
        status,err = execute_iud(db_path,[[status_update],],get_rowid=True)
        (out,ret),err = execute_with_rc(query["command"],True)
        return_code = ret
        if out[0]:
          output =re.sub("'","",''.join(out[0]))
        else:
          output = None
        if out[1]:
          error =re.sub("'","",''.join(out[1]))
        else:
          error = None
        if return_code == 0:
          # This means the command was successful. So update to completed
          status_update = "update scheduler_commands set status = 'completed', return_code='%d', output='%s', errors='%s' where command_id = '%d';"%(return_code,output,error,command_id)
          status,err = execute_iud(db_path,[[status_update],],get_rowid=True)
        if return_code != 0:
          # Error Oh! Error
          completed = False
          if retries > 0:
            status_update = 'update scheduler_commands set status = "pending", return_code="%d", output="%s", errors="%s",retries="%d" where command_id = "%d";'%(return_code,output,error,retries-1,command_id)
          elif retries == -2:
            print error,output
            pass
          else:
            status_update = 'update scheduler_commands set status = "error", return_code="%d", output="%s", errors="%s",retries="%d" where command_id = "%d";'%(return_code,output,error,retries,command_id)
          execute,err = execute_iud(db_path,[[status_update],],get_rowid=True)
          continue
      if completed:
        status_update = "update scheduler_tasks set status = 'completed' where task_id = '%d'"%task['task_id']
        status,err = execute_iud(db_path,[[status_update],],get_rowid=True)
      else:
        if retries > 0 or retries == -2:
          status_update = "update scheduler_tasks set status = 'pending' where task_id = '%d'"%task['task_id']
        else:
          status_update = "update scheduler_tasks set status = 'error' where task_id = '%d'"%task['task_id']
        status,err = execute_iud(db_path,[[status_update],],get_rowid=True)
    return True,None
  except Exception as e:
    return None,e

"""
Get a list of all the background tasks from the scheduler database.
Parameters :
1. db_path :  The database path
2. minutes : How many minutes of jobs to be fetched.
"""

def get_background_jobs(db_path,minutes=1440,node=None):
  yesterday = int((datetime.datetime.now() - datetime.timedelta(minutes=minutes)).strftime("%s"))
  now = int((datetime.datetime.now() + datetime.timedelta(minutes=minutes)).strftime("%s"))
  #now = int((datetime.datetime.now()).strftime("%s"))
  if not node:
    tasks = "select * from scheduler_tasks where initiate_time >= '%d' and initiate_time <= %d;" %(yesterday,now)
  else:
    tasks = "select * from scheduler_tasks where node == '"+node+"' and initiate_time >= '%d' and initiate_time <= %d;" %(yesterday,now)
  print tasks
  try:
    tasks,err = read_multiple_rows(db_path,tasks)
    print tasks
    if not tasks:
      return [],"No background jobs scheduled"
    else:
      return tasks,False
  except Exception,e:
    return None,e
    

"""
Given a task it, returns the Task details

Parameters :
1. db_path : The database path
2. task_id : The id of the task
"""

def get_background_job(db_path,task_id):
  tasks = "select * from scheduler_tasks where task_id=='%d'"%task_id
  try:
    tasks,err = read_multiple_rows(db_path,tasks)
    if not tasks:
      return [],"No jobs available"
    else:
      return tasks,False
  except Exception,e:
    return None,e

"""
Given a task it, returns the list of all commands scheduled under the task.

Parameters :
1. db_path : The database path
2. task_id : The id of the task
"""

def get_task_details(db_path,task_id):
  tasks = "select * from scheduler_commands where task_ref_id=='%d'"%task_id
  try:
    tasks,err = read_multiple_rows(db_path,tasks)
    if not tasks:
      return None,"No job found with id %d"%task_id
    else:
      return tasks,False
  except Exception,e:
    return None,e

def run_from_shell():
  db_path,err = common.get_db_path()
  print execute_scheduler(db_path)

def delete_task(task_id):
  if not task_id:
    return None,"Please give a task id"
  db_path,err = common.get_db_path()
  commands = "delete from scheduler_commands where task_ref_id=='%d'"%task_id
  execute,err_com = execute_iud(db_path,[[commands],],get_rowid=True)
  if not err_com:
    tasks = "delete from scheduler_tasks where task_id=='%d'"%task_id
    execute,err_task = execute_iud(db_path,[[tasks],],get_rowid=True)
  if not err_com and not err_task:
    return True,None
  else:
    return False,(err_com,err_task)  

def main():
  #print create_cron("ZFS Snap Testing",2,'*','*','*','*',command="/sbin/zfs snapshot pool1@$(date +'%F_%H-%M')")
  #print list_all_cron()
  #print delete_cron_with_comment("test spacing")
  #cron = None
  #cron =  find_cron("test")
  #for param in cron:
  #  print param.command
  db_path,err = common.get_db_path()
  #clear_table = "delete from scheduler_commands;"
  #status,err = execute_iud(db_path,[[clear_table],],get_rowid=True)
  #clear_table = "delete from scheduler_tasks;"
  #status,err = execute_iud(db_path,[[clear_table],],get_rowid=True)
  #row = 1
  #for count in xrange(16,20):
  #  jobname = "Test_%d"%count
  #  if count < 18:
  #    status,err = schedule_a_job(db_path,jobname,[{'cmd1':'echo'},{'cmd2':'echo'},{'cmd3':'pwd'}])
  #    row = status
  #  else:
  #    status,err = schedule_a_job(db_path,jobname,[{'cmd1':'echo123'},{'cmd2':'ecdsfsdho'},{'cmd3':'spsdfawd'}],extra={'deleteble':1,})
  #  print status,err
  #status,err = schedule_a_job(db_path,"Test 20",[{'cmd1':'echo123'},{'cmd2':'ecdsfsdho'},{'cmd3':'spsdfawd'}],extra={'deleteble':1,'execute_after':row})
  #print execute_scheduler(db_path,node='gridcell-pri.integralstor.lan')
  #print get_background_jobs(db_path,node='gridcell-pri.integralstor.lan')
  #print delete_task(5)
  print run_from_shell()
if __name__ == "__main__":
  main()
