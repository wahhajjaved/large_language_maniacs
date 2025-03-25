"""

Runs self-checks

"""

import logging
import os

from datetime import datetime, timedelta
from functools import partial
from airflow import DAG
from airflow.operators.bash_operator import BashOperator
from airflow.operators.python_operator import PythonOperator
from airflow_spm.operators import SpmOperator
from airflow_freespace.operators import FreeSpaceSensor
from airflow import configuration

from util import dicom_import
from util import nifti_import


# constants

DAG_NAME = 'mri_self_checks'

spm_config_folder = configuration.get('spm', 'SPM_DIR')
min_free_space_local_folder = float(
    configuration.get('mri', 'MIN_FREE_SPACE_LOCAL_FOLDER'))
dicom_local_folder = str(
    configuration.get('mri', 'DICOM_LOCAL_FOLDER'))

# functions

def check_python_fn():
    import os
    import socket
    print("Hostname: %s" % socket.gethostname())
    print("Environement:")
    print("-------------")
    for k,v in os.environ.items():
        print("%s = %s" % (k,v))
    print("-------------")


def check_spm_fn(engine):
    print("Checking Matlab...")
    ret = engine.sqrt(4.0)
    if int(ret) != 2:
        raise RuntimeError("Matlab integration is not working") from error
    print("sqrt(4) = %s" % ret)
    print("[OK]")
    print("Checking SPM...")
    spm_dir = eng.spm('Dir')
    if spm_dir != spm_config_folder:
        raise RuntimeError("SPM integration is not working, found SPM in directory %s" % spm_dir) from error
    print("[OK]")


# Define the DAG

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime.now(),
    'retries': 1,
    'retry_delay': timedelta(seconds=120),
    'email': 'ludovic.claude@chuv.ch',
    'email_on_failure': True,
    'email_on_retry': True
}

dag = DAG(
    dag_id=DAG_NAME,
    default_args=default_args,
    schedule_interval='@once')

check_free_space = FreeSpaceSensor(
    task_id='check_free_space',
    path=dicom_local_folder,
    free_disk_threshold=min_free_space_local_folder,
    retry_delay=timedelta(hours=1),
    retries=24 * 7,
    dag=dag
)

check_free_space.doc_md = """\
# Check free space

Check that there is enough free space on the local disk for processing, wait otherwise.
"""


check_python = PythonOperator(
    task_id='check_python',
    spm_function='check',
    python_callable=check_python_fn,
    execution_timeout=timedelta(minutes=10),
    dag=dag
)

check_python.set_upstream(check_free_space)

check_python.doc_md = """\
# Check Python and its environment

Displays some technical information about the Python runtime.
"""


check_spm = SpmOperator(
    task_id='spm_check',
    spm_function='check',
    python_callable=check_spm_fn,
    matlab_paths=[],
    execution_timeout=timedelta(minutes=10),
    dag=dag
)

check_spm.set_upstream(check_python)

check_spm.doc_md = """\
# Check SPM

Checks that SPM is running as expected.
"""
