"""
Data management
This is being developed for the MF2C Project: http://www.mf2c-project.eu/

Copyright: Roi Sucasas Font, Atos Research and Innovation, 2017.

This code is licensed under an Apache 2.0 license. Please, refer to the LICENSE.TXT file for more information

Created on 17 june 2019

@author: Roi Sucasas - ATOS
"""


from usermgnt.data import mf2c_data_adapter as mf2c_data_adapter
from usermgnt.data import default_data_adapter as default_data_adapter
from usermgnt.common.logs import LOG


# data adapterr
adapter = None


# set adapter
def init(um_mode):
    global adapter

    LOG.info('[usermgnt.data.data_adapter] [init] Setting data adapter...')
    if um_mode == "MF2C":
        LOG.info('[usermgnt.data.data_adapter] [init] UM_MODE = MF2C')
        adapter = mf2c_data_adapter.Mf2cDataAdapter()
    else:
        LOG.info('[usermgnt.data.data_adapter] [init] UM_MODE = STANDALONE')
        adapter = default_data_adapter.StandaloneDataAdapter()


###############################################################################

# FUNCTION: get_current_device_id
def get_current_device_id():
    return adapter.get_current_device_id()


# FUNCTION: get_current_device_ip
def get_current_device_ip():
    return adapter.get_current_device_ip()


# FUNCTION: get_leader_device_ip
def get_leader_device_ip():
    return adapter.get_leader_device_ip()


# FUNCTION: get_agent_info
def get_agent_info():
    return adapter.get_agent_info()


###############################################################################
# USER

# FUNCTION: get_user_info: gets user info
def get_user_info(user_id):
    return adapter.get_user_info(user_id)


# FUNCTION: delete_user: deletes user
def delete_user(user_id):
    return adapter.delete_user(user_id)


###############################################################################
# SHARING MODEL

# FUNCTION: get_user_profile_by_id
def get_sharing_model_by_id(sharing_model_id):
    return adapter.get_sharing_model_by_id(sharing_model_id)


# Get shared resources
def get_sharing_model(device_id):
    return adapter.get_sharing_model(device_id)


# Initializes shared resources values
def init_sharing_model(data):
    return adapter.init_sharing_model(data)


# Updates shared resources values
def update_sharing_model_by_id(sharing_model_id, data):
    return data.update_sharing_model_by_id(sharing_model_id, data)


# delete_sharing_model_by_id: Deletes  shared resources values
def delete_sharing_model_by_id(sharing_model_id):
    return adapter.delete_sharing_model_by_id(sharing_model_id)


# FUNCTION: get_current_sharing_model: Get current SHARING-MODEL
def get_current_sharing_model():
    return adapter.get_current_sharing_model()


###############################################################################
# USER-PROFILE

# get_user_profile_by_id
def get_user_profile_by_id(profile_id):
    return adapter.get_user_profile_by_id(profile_id)


# get_user_profile: Get user profile
def get_user_profile(device_id):
    return adapter.get_user_profile(device_id)


# update_user_profile_by_id: Updates a profile
def update_user_profile_by_id(profile_id, data):
    return adapter.update_user_profile_by_id(profile_id, data)


# Deletes users profile
def delete_user_profile_by_id(profile_id):
    return adapter.delete_user_profile_by_id(profile_id)


# Initializes users profile
def register_user(data):
    return adapter.register_user(data)


# setAPPS_RUNNING
def setAPPS_RUNNING(apps=0):
    return adapter.setAPPS_RUNNING(apps)


# FUNCTION: get_current_user_profile: Get Current USER-PROFILE
def get_current_user_profile():
    return adapter.get_current_user_profile()


###############################################################################
## AGENT INFO
## power, apps running ...

# FUNCTION: get_total_services_running: Get services running
def get_total_services_running():
    return adapter.get_total_services_running()


# FUNCTION: get_power: Get battery level from DEVICE_DYNAMIC
def get_power():
    return adapter.get_power()


###############################################################################
## LOCAL VOLUME
## Used to store / read 'user_id' and 'device_id'

# FUNCTION: save_device_id
def save_device_id(device_id):
    return adapter.save_device_id(device_id)


# FUNCTION: read_device_id
def read_device_id():
    return adapter.read_device_id()