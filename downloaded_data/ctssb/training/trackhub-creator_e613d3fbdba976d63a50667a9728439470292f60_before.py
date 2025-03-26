# 
# Author    : Manuel Bernal Llinares
# Project   : trackhub-creator
# Timestamp : 23-08-2017 14:40
# ---
# © 2017 Manuel Bernal Llinares <mbdebian@gmail.com>
# All rights reserved.
# 

"""
This module models the trackhub registry
"""

import json
import requests
# App imports
import config_manager
import ensembl.service
from . import models as trackhub_models
from . import exceptions as trackhub_exceptions


# Registry request body model
class TrackhubRegistryRequestBodyModel:
    def __init__(self):
        self.logger = config_manager.get_app_config_manager().get_logger_for(
            "{}.{}".format(__name__, type(self).__name__))
        # hub.txt URL
        self.url = None
        self.assembly_accession_map = {}
        # Trackhub is public by default
        self.public = 1
        # Default type for trackhubs is PROTEOMICS
        self.type = 'PROTEOMICS'

    def add_accession_for_assembly(self, assembly, accession):
        if assembly in self.assembly_accession_map:
            self.logger.error(
                "DUPLICATED Assembly '{}' add request, existing accession '{}', "
                "accession requested to be added '{}' - SKIPPED".format(assembly, self.assembly_accession_map[assembly],
                                                                        accession))
        else:
            self.assembly_accession_map[assembly] = accession
            self.logger.info("Assembly '{}' entry added to request body with accession '{}'"
                             .format(assembly, accession))

    def __str__(self):
        return json.dumps({'url': self.url,
                           'public': self.public,
                           'type': self.type,
                           'assemblies': self.assembly_accession_map})


# Visitor to export the trackhub as an instance of TrackhubRegistryRequestBodyModel
class TrackhubRegistryRequestBodyModelExporter(trackhub_models.TrackHubExporter):
    def __init__(self):
        super().__init__()

    def export_simple_trackhub(self, trackhub_builder):
        # In this case, the export summary will be an instance of TrackhubRegistryRequestBodyModelExporter
        if not self.export_summary:
            self.export_summary = TrackhubRegistryRequestBodyModel()
            ensembl_species_service = ensembl.service.get_service().get_species_data_service()
            for assembly in trackhub_builder.assemblies:
                self.export_summary \
                    .add_accession_for_assembly(assembly,
                                                ensembl_species_service
                                                .get_species_entry_for_assembly(assembly)
                                                .get_assembly_accession())
        return self.export_summary


class TrackhubRegistryService:
    __TRACKHUB_REGISTRY_API_SUBPATH_LOGIN = '/api/login'
    __TRACKHUB_REGISTRY_API_SUBPATH_LOGOUT = '/api/logout'
    __TRACKHUB_REGISTRY_API_SUBPATH_TRACKHUB = '/api/trackhub'

    def __init__(self, username, password):
        self.logger = config_manager.get_app_config_manager().get_logger_for("{}.{}"
                                                                             .format(__name__, type(self).__name__))
        self.username = username
        self.password = password
        self.trackhub_registry_base_url = 'https://www.trackhubregistry.org'
        self.__auth_token = None

    def __login(self):
        if not self.__auth_token:
            response = requests.get("{}{}"
                                    .format(self.trackhub_registry_base_url,
                                            self.__TRACKHUB_REGISTRY_API_SUBPATH_LOGIN),
                                    auth=(self.username, self.password),
                                    verify=True)
            if not response.ok:
                raise trackhub_exceptions.TrackhubRegistryServiceException(
                    "LOGIN ERROR '{}', HTTP status '{}'".format(response.text, response.status_code))
            self.__auth_token = response.json()[u'auth_token']
            self.logger.info("LOGGED IN at '{}'".format(self.trackhub_registry_base_url))
        return self.__auth_token

    def __logout(self):
        if self.__auth_token:
            response = requests.get("{}{}"
                                    .format(self.trackhub_registry_base_url,
                                            self.__TRACKHUB_REGISTRY_API_SUBPATH_LOGOUT),
                                    headers={'user': self.username, 'auth_token': self.__auth_token})
            if not response.ok:
                raise trackhub_exceptions.TrackhubRegistryServiceException(
                    "LOGOUT ERROR '{}', HTTP status '{}'".format(response.text, response.status_code))
            self.__auth_token = None
            self.logger.info("LOGGED OUT from '{}'".format(self.trackhub_registry_base_url))

    def __analyze_success_trackhub_registration(self, response):
        # TODO
        self.logger.debug("Trackhub Registration Response: '{}'".format(response.json()))
        return response.json()

    def register_trackhub(self, trackhub_registry_model):
        auth_token = self.__login()
        headers = {'user': self.username, 'auth_token': auth_token}
        payload = str(trackhub_registry_model)
        api_register_endpoint = "{}{}".format(self.trackhub_registry_base_url,
                                              self.__TRACKHUB_REGISTRY_API_SUBPATH_TRACKHUB)
        self.logger.debug("REGISTER TRACKHUB, endpoint '{}', payload '{}'".format(api_register_endpoint, payload))
        try:
            # Register Trackhub
            response = requests.post(api_register_endpoint,
                                     headers=headers, json=payload, verify=True)
            if not response.ok:
                raise trackhub_exceptions.TrackhubRegistryServiceException(
                    "TRACKHUB REGISTRATION ERROR '{}', HTTP status '{}'".format(response.text, response.status_code))
        finally:
            self.__logout()
        # Analyze response
        return self.__analyze_success_trackhub_registration(response)


if __name__ == '__main__':
    print("ERROR: This script is part of a pipeline collection and it is not meant to be run in stand alone mode")
