import json
import logging
import os
from argparse import ArgumentParser
from sys import argv

import google.auth.transport.requests
import google.oauth2.credentials
import google.oauth2.service_account
import googleapiclient
import googleapiclient.discovery
from easygoogle.config import config as updateApiCache
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

apisDict = {}


# Load APIs versions, identifiers and scopes relations
# from json file
def loadApiDict():
    global apisDict
    with open(os.path.join(os.path.dirname(__file__), 'apis.json'), 'r') as fl:
        apisDict = json.load(fl)


if os.path.isfile(os.path.join(os.path.dirname(__file__), 'apis.json')):
    loadApiDict()


# Base class, loads API information and build the connectors with the credentials
class _api_builder:

    # Internal function to load all avaiable APIs based on the scopes
    def _loadApiNames(self, scopes):
        # Create a new dictionary to hold the information
        apiset = dict()

        # Iterates through every unique scopes
        for x in list(set(scopes)):
            try:
                # Load scope relations descriptor
                apiset[x] = apisDict[x]
            except KeyError:
                # Log when scope not found
                logger.warning("[!] SCOPE %s not registered" % x)
            else:
                # On success log the unlocked APIs
                logger.debug("Loaded auth: %s --> api: %s" % (x, ', '.join(
                    ("%s, %s" % (a['name'], a['version'])
                     for a in apiset[x]['apis']))))
        logger.info("Apis imported")

        # Save the raw apiset
        self.apis = apiset
        # Instantiated a new dictionary create usable control
        self.valid_apis = dict()

        # Iterates through every scope descriptor unlocked
        for a in self.apis.values():

            # Iterates through all APIs described in the scope relations descriptor
            for b in a['apis']:
                # Process suffix when there are subidentifier in version
                suffix = b['version'].split('_v')
                suffix = "_" + suffix[0] if len(suffix) > 1 else ""
                api_tag = b['name'] + suffix
                if api_tag in self.valid_apis:
                    if b['preferred']:
                        self.valid_apis[api_tag][1].insert(0, b['version'])
                    else:
                        self.valid_apis[api_tag][1].append(b['version'])
                else:
                    self.valid_apis[api_tag] = (b['name'], [b['version']])

    def __call__(self, api, version=None):
        return self.get_api(api, version)

    # Function to build connector based on API identifiers
    def get_api(self, api, version=None):

        # Build connector if API identifier is valid
        if api in self.valid_apis:
            if version is None:
                version = self.valid_apis[api][1][-1]
            res = googleapiclient.discovery.build(
                self.valid_apis[api][0],
                version,
                credentials=self._credentials,
                cache_discovery=False,
            )
            logger.info("%s API Generated" % api)
            return res
        else:
            logger.warning("%s is not a valid API" % api)
            raise ValueError("Invalid API identifier")


# OAuth2 class
# Handles API connector building, configuration of avaiable API and OAuth2 authentication flow
class oauth2(_api_builder):

    # Main constructor function
    def __init__(self,
                 secret_json,
                 scopes,
                 appname='Google Client Library - Python',
                 user="",
                 app_dir='.',
                 manualScopes=[],
                 hostname='localhost',
                 port=8080):

        # Load valid APIs unlocked with the scopes
        self._loadApiNames(scopes)

        # Save all scopes results
        self.SCOPES = list(
            set([x['scope'] for x in self.apis.values()] + manualScopes))

        # Home directory of the app
        home_dir = os.path.abspath(app_dir)

        if secret_json == None:
            self._credentials, self.projectId = google.auth.default()
        else:
            # Path to credentials files directory
            self.credential_dir = os.path.join(home_dir, '.credentials')
            # Create credentials directory if not exists
            if not os.path.isdir(self.credential_dir):
                os.makedirs(self.credential_dir)

            # Save app name
            self.name = appname

            # Construct file name
            self.filename = ''.join(
                e for e in self.name if e.isalnum() or e in ' _-'
            ).lower().replace(
                ' ', '_'
            ) + '#' + user + ".json"

            # Assemble full credential file path
            self.credential_path = os.path.join(self.credential_dir,
                                                self.filename)

            # Load saved credentials if the file exists
            if os.path.isfile(self.credential_path):
                saved_state = json.load(open(self.credential_path))
                for s in self.SCOPES:
                    if s not in saved_state['scopes']:
                        self.SCOPES = list(
                            set(self.SCOPES + saved_state['scopes']))
                        saved_state = None
                        break
            else:
                saved_state = None

            if saved_state == None:
                # No valid credentials found
                # Instantiate authrization flow
                flow = InstalledAppFlow.from_client_secrets_file(
                    secret_json, scopes=self.SCOPES)

                # Start web server to authorize application
                credentials = flow.run_local_server(host=hostname, port=port)
                credentials.refresh(
                    google.auth.transport.requests.Request(
                        session=flow.authorized_session(),
                    ),
                )

                saved_state = {
                    'refresh_token': credentials.refresh_token,
                    'client_id': credentials.client_id,
                    'client_secret': credentials.client_secret,
                    'token_uri': credentials.token_uri,
                    'id_token': credentials.id_token,
                    'scopes': list(credentials.scopes),
                }

                json.dump(saved_state, open(self.credential_path, 'w'))
            else:
                credentials = google.oauth2 \
                    .credentials.Credentials(None, **saved_state)
                credentials.refresh(
                    google.auth.transport.requests.Request(),
                )
            self._credentials = credentials

    @property
    def credentials(self):
        return self._credentials

    @classmethod
    def default(cls):
        return cls(None, ['cloud-platform'])


# Handler for service account authentication
class service_acc(_api_builder):

    # Instantiate handler
    def __init__(self,
                 service_file,
                 scopes,
                 manualScopes=[],
                 domainWide=True,
                 *args,
                 **kwargs):

        # Load valid APIs unlocked with the scopes
        self._loadApiNames(scopes)

        # Save all scopes results
        self.SCOPES = list(
            set([x['scope'] for x in self.apis.values()] + manualScopes))

        # Set domain wide delegation flag
        self.__domWide = domainWide

        # Acquire credentials from JSON keyfile
        if service_file:
            self._credentials = google.oauth2.service_account.Credentials.from_service_account_file(
                service_file,
                scopes=self.SCOPES,
            )
            self.projectId = self._credentials.project_id
        else:
            self._credentials, self.projectId = google.auth.default()
            self._credentials = self._credentials.with_scopes(self.SCOPES)
        logger.debug("Credentials acquired")

    @property
    def credentials(self):
        return self._credentials

    @credentials.setter
    def credentials(self, newCredentials):
        self._credentials = newCredentials

    @classmethod
    def default(cls, scopes=['cloud-platform'], **kwargs):
        return cls(None, scopes, **kwargs)

    # Delegate authorization using application impersonation of authority
    def delegate(self, user):
        # Proceed only if domain wide delegation flag was setted to True
        if self.__domWide:
            # Instantiate delegated handler
            res = _delegated(
                self.credentials.with_subject(user), self.valid_apis)
            logger.info("Created delegated credentials")
            return res
        else:
            logger.warning("Domain Wide Delegation disabled")
            return self

    @property
    def domain_wide(self):
        return self.__domWide


# Delegated class, created from service account application impersonation
class _delegated(_api_builder):
    def __init__(self, dCredentials, apis):
        self.valid_apis = apis
        self._credentials = dCredentials
