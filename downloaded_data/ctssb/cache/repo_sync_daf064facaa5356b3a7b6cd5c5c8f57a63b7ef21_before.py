import requests
import json
import os
import sys

class Gitlab:

    URL_BASE = "http://192.168.0.194/api/v3"
    CREDENTIALS_FILE = os.path.expanduser("~/repo_sync/gitlab_credentials")
    CREDENTIALS_TEMPLATE = """username
password
target_username"""

    def __init__(self):
        if not os.path.isfile(self.CREDENTIALS_FILE):
            with open(self.CREDENTIALS_FILE, 'w') as file:
                file.write(self.CREDENTIALS_TEMPLATE)
            print("Please fill in gitlab credentials at ~/repo_sync/gitlab_credentials")
            sys.exit()
        with open(self.CREDENTIALS_FILE, 'r') as file:
            credentials = file.readlines()
            self.username = credentials[0].strip()
            self.password = credentials[1].strip()
            self.target_user = credentials[2].strip()

        self.authenticate()

    def authenticate(self):
        response = requests.post(self.URL_BASE + "/session", {'login': self.username, 'password': self.password})
        self.private_token = json.loads(response.text)['private_token']

    def get_repos(self):
        repos = []
        page = 1
        while True:
            response = requests.get(self.URL_BASE + "/projects/all?page=" + str(page) + "&private_token=" + self.private_token)
            repos += json.loads(response.text)
            if 'next' not in response.headers['link']:
                break
            else:
                page += 1
        return repos

    def create_repo(self, name):
        response = requests.post(self.URL_BASE + "/projects?sudo=" + self.target_user + "&private_token=" + self.private_token,
                                 {'name': name})
        if response.status_code == 201:
            return "Success"
        else:
            return "Failed"

    def get_repo(self, name):
        response = requests.get(self.URL_BASE + "/projects/" + self.target_user + "%2F" + name.lower() + "?private_token=" + self.private_token)
        if response.status_code == 404:
            raise Exception
        return json.loads(response.text)
