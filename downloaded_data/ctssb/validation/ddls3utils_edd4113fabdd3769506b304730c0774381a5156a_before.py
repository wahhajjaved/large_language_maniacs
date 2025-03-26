import boto3
import os
from os import listdir
from os.path import isfile, join, dirname, basename, exists, split, splitext

class S3Client:

    '''
    @description
        Initializes the S3Client object and creates a S3 client object.

    @arguments
        region_name : <str> Supplies the region name of the S3 instance.

        aws_access_key_id : <str> Supplies the AWS access key id.

        aws_secret_access_key : <str> Supplies the AWS secret access key.

        download_file_extension_filter : <list> [optional, default=[]] Supplies the file extensions
            to download. If set to [], all files will be downloaded.

        upload_file_extension_filter : <list> [optional, default=[]] Supplies the file extensions
            to upload. If set to [], all files will be uploaded.

    '''

    def __init__(self,
                 region_name,
                 aws_access_key_id,
                 aws_secret_access_key,
                 download_file_extension_filter=[],
                 upload_file_extension_filter=[]):

        self.download_file_extension_filter = download_file_extension_filter
        self.upload_file_extension_filter = upload_file_extension_filter
        self.client = boto3.client(
                        's3',
                        region_name=region_name,
                        aws_access_key_id=aws_access_key_id,
                        aws_secret_access_key=aws_secret_access_key)

        if self.client is None:
            raise RuntimeError("[error] __init__ : failed to create S3 client")

    '''
    @description
        Lists all files and sub-folders of the given folder.

    @arguments
        bucket : <str> Supplies the bucket name.

        s3_folder : <str> [optional, default=None] Supplies the folder name to list under.
            If set to None, the top-level content under the given bucket will be listed.

    @returns
        <list>, <list>: Returns a list contains the name of the files under the given
            folder, and a list contains the name of the sub-folders under the given folder.

    '''

    def s3_list_folder(self, bucket, s3_folder=None):
        subfolders = []
        files = []
        paginator = self.client.get_paginator('list_objects')
        if s3_folder is not None:
            resp = paginator.paginate(Bucket=bucket, Delimiter='/', Prefix=s3_folder)
        else:
            resp = paginator.paginate(Bucket=bucket, Delimiter='/')

        for result in resp:
            if result.get('CommonPrefixes') is not None:
                for subdir in result.get('CommonPrefixes'):
                    subfolders.append(subdir.get('Prefix'))

            if result.get('Contents') is not None:
                for file in result.get('Contents'):
                    if not file.get('Key').endswith('/'):
                        files.append(file.get('Key'))

        return files, subfolders

    '''
    @description
        Upload a file to the given folder under the given S3 bucket.

    @arguments
        bucket : <str> Supplies the bucket name.

        local_file_location : <str> Supplies the location of the file to upload.

        s3_folder : <str> [optional, default=None] Supplies the folder name to upload to.
            If set to None, the file will be uploaded under the bucket.

    @returns
        None.

    '''

    def s3_upload_file(self, bucket, local_file_location, s3_folder=None):
        file_name = basename(local_file_location)
        _, extension = splitext(file_name)
        if len(self.upload_file_extension_filter) > 0 and extension not in self.upload_file_extension_filter:
            return

        if s3_folder is not None:
            s3_file_name = "{0}{1}".format(s3_folder, file_name)
        else:
            s3_file_name = file_name
        self.client.upload_file(local_file_location, bucket, s3_file_name)
        return

    '''
    @description
        Upload a folder to the given folder under the given S3 bucket.

    @arguments
        bucket : <str> Supplies the bucket name.

        s3_base_folder : <str> Supplies the base folder on S3 to upload to.

        local_folder_location : <str> Supplies the location of the folder to upload.

    @returns
        None.

    '''

    def s3_upload_folder(self, bucket, s3_base_folder, local_folder_location):
        for file in listdir(local_folder_location):
            current_file_location = join(local_folder_location, file)
            if isfile(current_file_location):
                current_folder_split = local_folder_location.split(os.sep)
                current_folder_s3_path = s3_base_folder + "/".join(current_folder_split) + "/"
                self.s3_upload_file(bucket, current_folder_s3_path, current_file_location)
            else:
                self.s3_upload_folder(bucket, s3_base_folder, current_file_location)
        return

    '''
    @description
        Download the file from S3 to the given location.

    @arguments
        bucket : <str> Supplies the bucket name.

        s3_file_name : <str> Supplies the name of the file on S3 to download.

        download_to_folder_location : <str> Supplies the folder to download to.

    @returns
        None.

    '''

    def s3_download_file(self, bucket, s3_file_name, download_to_folder_location):
        file_name = basename(s3_file_name)
        _, extension = splitext(file_name)
        if len(self.download_file_extension_filter) > 0 and extension not in self.download_file_extension_filter:
            return

        file_destination = join(download_to_folder_location, file_name)
        self.client.download_file(bucket, s3_file_name, file_destination)
        return

    '''
    @description
        Download the files in the given folder from S3 to the given location.

    @arguments
        bucket : <str> Supplies the bucket name.

        s3_folder : <str> Supplies the name of the folder on S3 to download.

        download_to_folder_location : <str> Supplies the folder to download to.

    @returns
        None.

    '''

    def s3_download_folder(self, bucket, s3_folder, download_to_folder_location):
        folder_path = s3_folder.split("/")
        folder_full_path = join(download_to_folder_location, "/".join(folder_path[2:]))
        if not exists(folder_full_path):
            os.makedirs(folder_full_path)

        files, subfolders = self.s3_list_folder(bucket, s3_folder)
        for subfolder in subfolders:
            self.s3_download_folder(bucket, subfolder, download_to_folder_location)

        for file in files:
            self.s3_download_file(bucket, file, folder_full_path)