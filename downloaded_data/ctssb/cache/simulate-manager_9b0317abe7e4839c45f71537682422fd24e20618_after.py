"""
retrieve scripts from cloud storage
"""

import os

from connection.cloud import AzureBlobService, AzureCredentials

from flask import current_app

def get_azure_credentials():
    """
    use the config's azure account_name and account_key
    """
    return AzureCredentials(current_app.config)


def get_relative_path_from_uri(source_uri, acc_name):
    """
    The script's "source" will be a URI of format https"//<acc_name>.stuff/<container_name>/<blob_name>
    We want to just get the blob name, which is the relative path we'll copy files into.
    """
    filepath_elements = source_uri.split("/")
    found_acc_name = False
    found_container_name = False
    container_name = None
    blob_name = ""
    for element in filepath_elements:
        if found_acc_name and not found_container_name:
            container_name = element
            found_container_name = True
        elif found_container_name:
            blob_name += element + "/"
        if acc_name in element:
            found_acc_name = True
    blob_name = blob_name[:-1] # remove trailing slash
    return blob_name, container_name


def get_remote_scripts(scripts, destination_dir):
    """
    use Azure BlockBlobService to get scripts from cloud storage and put them in local directory
    """
    dummy={}
    azure_credentials = get_azure_credentials()
    acc_name = azure_credentials.account_name
    blob_retriever = AzureBlobService(azure_credentials)

    for script in scripts:
        source_uri = script["source"]
        blob_name, container_name = get_relative_path_from_uri(source_uri,
                                                               acc_name)
        blob_relative_dir = os.path.dirname(blob_name)
        local_filepath = os.path.join(destination_dir, blob_relative_dir)
        os.makedirs(local_filepath, exist_ok=True)
        blob_retriever.retrieve_blob(blob_name,
            container_name,
            local_filepath)
        # modify the script dictionary (dicts are mutable) to replace the source uri
        # with just the relative path.  This way the patcher will be able to find it.
        script["source"] = blob_name
    return True
