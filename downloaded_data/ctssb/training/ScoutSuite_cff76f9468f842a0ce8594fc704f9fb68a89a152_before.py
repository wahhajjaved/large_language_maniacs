# -*- coding: utf-8 -*-

import os

import google.auth
from opinel.utils.console import printError, printException

from ScoutSuite.providers.base.provider import BaseProvider
from ScoutSuite.providers.gcp.configs.services import GCPServicesConfig

import googleapiclient
from oauth2client.client import GoogleCredentials
from googleapiclient import discovery
from google.cloud import resource_manager


class GCPCredentials():

    def __init__(self, api_client_credentials, cloud_client_credentials):
        self.api_client_credentials = api_client_credentials
        self.cloud_client_credentials = cloud_client_credentials

class GCPProvider(BaseProvider):
    """
    Implements provider for AWS
    """

    def __init__(self, project_id=None, folder_id=None, organization_id=None,
                 report_dir=None, timestamp=None, services=[], skipped_services=[], thread_config=4, **kwargs):

        self.profile = 'gcp-profile'  # TODO this is aws-specific

        self.metadata_path = '%s/metadata.json' % os.path.split(os.path.abspath(__file__))[0]

        self.provider_code = 'gcp'
        self.provider_name = 'Google Cloud Platform'

        self.projects=[]
        self.project_id=project_id
        self.folder_id=folder_id
        self.organization_id=organization_id

        self.services_config = GCPServicesConfig

        super(GCPProvider, self).__init__(report_dir, timestamp, services, skipped_services, thread_config)

    def authenticate(self, key_file=None, user_account=None, service_account=None, **kargs):
        """
        Implement authentication for the GCP provider
        Refer to https://google-auth.readthedocs.io/en/stable/reference/google.auth.html.

        :return:
        """

        if user_account:
            # disable GCP warning about using User Accounts
            import warnings
            warnings.filterwarnings("ignore", "Your application has authenticated using end user credentials")
            pass  # Nothing more to do
        elif service_account:
            client_secrets_path = os.path.abspath(key_file)  # TODO this is probably wrong
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = client_secrets_path
        else:
            printError('Failed to authenticate to GCP - no supported account type')
            return False

        try:

            # TODO there is probably a better way to do this
            # api_client_credentials = GoogleCredentials.get_application_default()
            # cloud_client_credentials, self.gcp_project_id = google.auth.default()
            # self.credentials = GCPCredentials(api_client_credentials, cloud_client_credentials)

            # TODO not sure why this works - there are no credentials for API client libraries
            self.credentials, project_id = google.auth.default()

            if self.credentials:

                if self.project_id:
                    self.projects = self._get_projects(parent_type='project',
                                                       parent_id=self.project_id)
                    self.aws_account_id = self.project_id # FIXME this is for AWS

                elif self.organization_id:
                    self.projects = self._get_projects(parent_type='organization',
                                                                        parent_id=self.organization_id)
                    self.aws_account_id = self.organization_id # FIXME this is for AWS

                elif self.folder_id:
                    self.projects = self._get_projects(parent_type='folder',
                                                                        parent_id=self.folder_id)
                    self.aws_account_id = self.folder_id # FIXME this is for AWS

                else:
                    self.projects = [project_id]

                # TODO this shouldn't be done here? but it has to in order to init with projects...
                self.services.set_projects(projects=self.projects)

                return True
            else:
                return False

        except google.auth.exceptions.DefaultCredentialsError as e:
            printError('Failed to authenticate to GCP')
            printException(e)
            return False

    def preprocessing(self, ip_ranges=[], ip_ranges_name_key=None):
        """
        TODO description
        Tweak the AWS config to match cross- resources and clean any fetching artifacts

        :param ip_ranges:
        :param ip_ranges_name_key:
        :return: None
        """

        self._match_instances_and_snapshots()
        self._match_networks_and_instances()

        super(GCPProvider, self).preprocessing()

    def _get_projects(self, parent_type, parent_id):
        """
        Returns all the projects in a given organization or folder. For a project_id it only returns the project
        details.
        """

        if parent_type not in ['project', 'organization', 'folder']:
            return None

        projects = []

        #FIXME can't currently be done with API client library as it consumes v1 which doesn't support folders
        """
        
        resource_manager_client = resource_manager.Client(credentials=self.credentials)

        project_list = resource_manager_client.list_projects()

        for p in project_list:
            if p.parent['id'] == self.organization_id and p.status == 'ACTIVE':
                projects.append(p.project_id)
        """

        resource_manager_client_v1 = discovery.build('cloudresourcemanager', 'v1', credentials=self.credentials)
        resource_manager_client_v2 = discovery.build('cloudresourcemanager', 'v2', credentials=self.credentials)

        if parent_type == 'project':

            project_response = resource_manager_client_v1.projects().list(filter='id:%s' % parent_id).execute()
            if 'projects' in project_response.keys():
                for project in project_response['projects']:
                    if project['lifecycleState'] == "ACTIVE":
                        projects.append(project)

        else:

            # get parent children projectss
            request = resource_manager_client_v1.projects().list(filter='parent.id:%s' % parent_id)
            while request is not None:
                response = request.execute()

                if 'projects' in response.keys():
                    for project in response['projects']:
                        if project['lifecycleState'] == "ACTIVE":
                            projects.append(project)

                request = resource_manager_client_v1.projects().list_next(previous_request=request,
                                                                          previous_response=response)

            # get parent children projects in children folders recursively
            folder_response = resource_manager_client_v2.folders().list(parent='%ss/%s' % (parent_type, parent_id)).execute()
            if 'folders' in folder_response.keys():
                for folder in folder_response['folders']:
                    projects.extend(self._get_projects_in_org_or_folder("folder", folder['name'].strip(u'folders/')))

        return projects

    def _match_instances_and_snapshots(self):
        """
        Compare Compute Engine instances and snapshots to identify instance disks that do not have a snapshot.

        :return:
        """

        if 'computeengine' in self.services:
            for instance in self.services['computeengine']['instances'].values():
                for instance_disk in instance['disks'].values():
                    instance_disk['snapshots'] = []
                    for disk in self.services['computeengine']['snapshots'].values():
                        if disk['status'] == 'READY' and disk['source_disk_url'] == instance_disk['source_url']:
                            instance_disk['snapshots'].append(disk)

    def _match_networks_and_instances(self):
        """
        For each network, math instances in that network

        :return:
        """

        if 'computeengine' in self.services:
            for network in self.services['computeengine']['networks'].values():
                network['instances'] = []
                for instance in self.services['computeengine']['instances'].values():
                    for network_interface in instance['network_interfaces']:
                        if network_interface['network'] == network['network_url']:
                            network['instances'].append(instance['id'])
