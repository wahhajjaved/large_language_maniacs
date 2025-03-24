import os
import datetime as dt
import hashlib

ANALYSIS_PATH = '/home/hwu/analysis/'
RESULT_PATH = '/home/hwu/downstream/result/'
LOG_ROOT ='/home/hwu/analysis_logs'

## FILE AND DIR related 
def line_number(file_path):
    with open(file_path, "r") as f:
        line_count = len(set(f.readlines()))
    return line_count

def make_dir_if_not_exist(target_dir):
     if not os.path.exists(target_dir): 
        os.makedirs(target_dir)



### Lab Project related
def is_bcr(file_name):
    uc_file_name = file_name.upper()
    indicators = ['BCR',  'IGM', 'IGG', 'IGH', 'IGVH']
    #TODO: add key work for TCR and check the key work is not in filename
    bcr = any([ x in uc_file_name for x in indicators])
    return bcr

def is_igg(sample_name):
    uc_sample_name = sample_name.upper()
    reslut =  'IGG' in uc_file_name
    return(reslut)
    

    #TODO: add key work for TCR and check the key work is not in filename
def raw_data_dir_to_analysi_dir(raw_data_dir):
    """ remove the 'Auto_user_SN2 in dirname
    """
    return raw_data_dir.lstrip('Auto_user_SN2-')

def analysis_dir_to_raw_data_dir(analysis_dir):
    """we striped the Auto_user part in raw_data_dir_to_analysi_dir
    """
    raw_data_dir= os.path.basename(analysis_dir)
    if os.path.basename(raw_data_dir)[0].isdigit():
        raw_data_dir =  'Auto_user_SN2-' + raw_data_dir
    return raw_data_dir

def extract_bcr_id(item):
    csv= item.split('/')[-1]
    if csv.endswith('.csv') and is_bcr(csv):
        sample_name = csv.rstrip('.csv')
        return '_'.join(sample_name.split('_')[0:2])

def get_changed_bcr_ids(copy_log_of_today):
     ids = []
     with open(copy_log_of_today, 'r') as f:
         for item in f:
             current_id = extract_bcr_id(item.rstrip()[24:])
             if current_id:
                ids.append(current_id)
                ids.append(current_id.split('_')[0])
     return(list(set(ids)))

def extract_tcr_id(item):
    csv= item.split('/')[-1]
    if csv.endswith('.csv') and not is_bcr(csv):
        sample_name = csv.rstrip('.csv')
        return '_'.join(sample_name.split('_')[0:2])

def copy_log_of_today():
    copy_log_of_today = os.path.join(LOG_ROOT, "copy_log", "%s.log" % (dt.datetime.today().strftime("%Y-%m-%d")))
    return(copy_log_of_today)

def get_changed_tcr_ids(copy_log_of_today):
     ids = []
     with open(copy_log_of_today, 'r') as f:
         for item in f:
             current_id = extract_tcr_id(item.rstrip()[24:])
             if current_id:
                ids.append(current_id)
                ids.append(current_id.split('_')[0])
     return(list(set(ids)))


def get_changed_run(copy_log_of_today):
     with open(copy_log_of_today, 'r') as f:
         for item in f:
             if 'copying' in item:
                 run_path = os.path.dirname(item.split()[-1])
                 return os.path.dirname(item.split()[-1]).split('/')[4]

def hash_of_dir(root_dir):
    root_hash = hashlib.sha224(root_dir.encode('utf-8')).hexdigest()[0:6]
    return root_hash


def get_project_ids(project_name):
    current_path = '/home/hwu/downstream/project_summay/project'
    with open(os.path.join(current_path,project_name + '.csv')) as fp:
        fp.readline() # remove the ids
        ids = fp.read().splitlines()
    return(ids)

def bcr_configs():
    specific_config = [
        "_".join([method, str(distance), 'len_8', 'count', str(count)])
        for count in range(1, 3) for distance in range(
            0, 3) for method in ['lv', 'hamming']
    ]
    return(specific_config)


