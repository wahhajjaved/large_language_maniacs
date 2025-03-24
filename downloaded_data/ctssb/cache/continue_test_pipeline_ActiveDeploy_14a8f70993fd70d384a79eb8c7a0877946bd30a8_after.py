#!/usr/bin/python

#***************************************************************************
# Copyright 2015 IBM
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#***************************************************************************

import argparse
import json
import os
import requests
import sys
import traceback
import time
import ConfigParser
import string
import urlparse

# Environment variables
IDS_USER_ENV_VAR = 'ibmIdUsername'
IDS_PASS_ENV_VAR = 'ibmIdPassword'
LOGIN_URL = ""
Host = ""
DEPLOY_STAGE_ID = ""
BUILD_STAGE_ID = ""
BUILD_STAGE_NAME = ""

def main():
    global LOGIN_URL
    global DEPLOY_STAGE_ID
    global BUILD_STAGE_ID
    global BUILD_STAGE_NAME

    # Read the IDS Project info from pipeline_test.properties
    config = ConfigParser.ConfigParser()
    config.read('pipeline_test.properties')
    Host = config.get('Config', 'Host')
    ProjectName = config.get('Config', 'ProjectName')
    print "ProjectName is: ", ProjectName
    otcPipelineHost = config.get('Config', 'otcPipelineHost')
    print "OTC Pipeline Server is: ", otcPipelineHost
    idsProjectURL = '%s/devops/pipelines/%s' % (Host, ProjectName)

    print "\nIDS project URL is: %s" % (idsProjectURL)
    if Host == "https://console.ng.bluemix.net":
        LOGIN_URL = "https://console.ng.bluemix.net"
        print ('Target login URL is: %s' % LOGIN_URL)
    else:
        print "LOGIN_URL not given!"

    # Number of retries to attempt
    RETRY = 5
    # Get the login cookies
    cookies = None
    for i in range(RETRY):
        # for f in [ssologin, ssologin_old]:
        for f in [ssologin]:
            try:
                cookies = f()
                break
            except Exception, e:
                if i < RETRY - 1:
                    print '\nFailed to log into IDS'
                    traceback.print_exc(file=sys.stdout)
                    time.sleep(10)
                else:
                    raise e
        if cookies:
            break
    print 'Successfully logged into IDS, getting pipeline information ...'

    # headers for GET and POST to retrieve data and trigger stage
    # in V2 need bearer token for Authorization at Rest Endpoints
    headers = {
        'Accept': 'application/json',
        #'Authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJqdGkiOiJmZGJkY2YyYi0zMzcwLTQxYTgtOGYzYi04MDc3YjI4Y2FiNTYiLCJzdWIiOiIxNzE5ZDRkZC00NmYzLTQzOWYtOTRmOS0zYWI4MWM3MzUwZjYiLCJzY29wZSI6WyJjbG91ZF9jb250cm9sbGVyLnJlYWQiLCJwYXNzd29yZC53cml0ZSIsImNsb3VkX2NvbnRyb2xsZXIud3JpdGUiLCJvcGVuaWQiLCJ1YWEudXNlciJdLCJjbGllbnRfaWQiOiJjZiIsImNpZCI6ImNmIiwiYXpwIjoiY2YiLCJncmFudF90eXBlIjoicGFzc3dvcmQiLCJ1c2VyX2lkIjoiMTcxOWQ0ZGQtNDZmMy00MzlmLTk0ZjktM2FiODFjNzM1MGY2Iiwib3JpZ2luIjoidWFhIiwidXNlcl9uYW1lIjoiZGV2b3BzMDFAdXMuaWJtLmNvbSIsImVtYWlsIjoiZGV2b3BzMDFAdXMuaWJtLmNvbSIsInJldl9zaWciOiIyNDE5Njc5MSIsImlhdCI6MTQ4MjE0OTE4NCwiZXhwIjoxNDgzMzU4Nzg0LCJpc3MiOiJodHRwczovL3VhYS5uZy5ibHVlbWl4Lm5ldC9vYXV0aC90b2tlbiIsInppZCI6InVhYSIsImF1ZCI6WyJjbG91ZF9jb250cm9sbGVyIiwicGFzc3dvcmQiLCJjZiIsInVhYSIsIm9wZW5pZCJdfQ.EsB0UZwPN6pHp-PH1SZgOh-XyPuKnf_wL8-mh1E4to8'
        'Authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJqdGkiOiI4OWU3ZDBkNi0wZmZlLTRlYjYtODQzYS0zOTk0ZDM5M2VjMDEiLCJzdWIiOiIxNzE5ZDRkZC00NmYzLTQzOWYtOTRmOS0zYWI4MWM3MzUwZjYiLCJzY29wZSI6WyJjbG91ZF9jb250cm9sbGVyLnJlYWQiLCJwYXNzd29yZC53cml0ZSIsImNsb3VkX2NvbnRyb2xsZXIud3JpdGUiLCJvcGVuaWQiLCJ1YWEudXNlciJdLCJjbGllbnRfaWQiOiJjZiIsImNpZCI6ImNmIiwiYXpwIjoiY2YiLCJncmFudF90eXBlIjoicGFzc3dvcmQiLCJ1c2VyX2lkIjoiMTcxOWQ0ZGQtNDZmMy00MzlmLTk0ZjktM2FiODFjNzM1MGY2Iiwib3JpZ2luIjoidWFhIiwidXNlcl9uYW1lIjoiZGV2b3BzMDFAdXMuaWJtLmNvbSIsImVtYWlsIjoiZGV2b3BzMDFAdXMuaWJtLmNvbSIsInJldl9zaWciOiIyNDE5Njc5MSIsImlhdCI6MTQ4NDc1MTUyMiwiZXhwIjoxNDg1OTYxMTIyLCJpc3MiOiJodHRwczovL3VhYS5uZy5ibHVlbWl4Lm5ldC9vYXV0aC90b2tlbiIsInppZCI6InVhYSIsImF1ZCI6WyJjbG91ZF9jb250cm9sbGVyIiwicGFzc3dvcmQiLCJjZiIsInVhYSIsIm9wZW5pZCJdfQ.WvO4-v9MUwd91jks8rqGjxc_IpwWj4j5D8BOthbGBL0'
    }

    # Get current stages information
    sleepTime = 20;
    curr_pipe_info = []
    print "\nStages execution status before trigger stage:"

    curr_pipe_info = getStageStatus(otcPipelineHost, ProjectName, cookies, headers, sleepTime)
    if curr_pipe_info:
        print "\nSuccessfully retrieved pipeline information before trigger stage ..."
        for item in curr_pipe_info:
            print item[0], ', '.join(map(str, item[1:]))
    else:
        raise Exception("\nThe project does not have pipeline stage.")

    # Trigger the BUILD stage, Deploy stage will run automatically after BUILD stage
    print "\nTriggering stage '%s' with stage ID  '%s' ..." % (BUILD_STAGE_NAME, BUILD_STAGE_ID)
    trigger_url = '%s/pipeline/pipelines/%s/stages/%s/executions' % (otcPipelineHost, ProjectName, BUILD_STAGE_ID)
    r = requests.post(trigger_url, headers=headers, cookies=cookies)
    if r.status_code != 201:
        raise Exception('Failed to POST %s, status code: %s, content: %s' %
                (trigger_url, r.status_code, r.content))
    else:
        print "Successfully triggered first stage"

    # Get pipeline stages info during and after test run, wait 120s for pipeline start
    time.sleep(120)
    print "\ncheck stages execution status DURING test run:"

    curr_pipe_info = getStageStatus(otcPipelineHost, ProjectName, cookies, headers, sleepTime)
    if curr_pipe_info:
        print "\nSuccessfully retrieved pipeline information AFTER test run ..."
        for item in curr_pipe_info:
            print item[0], ', '.join(map(str, item[1:]))
            #check for any FAILURE in item
            if 'FAILURE' in item[0]:
                raise Exception("\nThe test run was not run successfully.")
    else:
        raise Exception("\nThe test run was not run successfully.")


def getStageStatus(otcPipelineHost, ProjectName, cookies, headers, sleepTime):
    global DEPLOY_STAGE_ID
    global BUILD_STAGE_ID
    global BUILD_STAGE_NAME

    #URL for infos about all stages and jobs
    stages_jobs = '%s/pipeline/pipelines/%s/stages' % (otcPipelineHost, ProjectName)

    #request json file from stages and jobs
    sj = requests.get(stages_jobs, headers=headers, cookies=cookies)
    if sj.status_code != 200:
        raise Exception('Failed to retrieve stages_jobs, failed to GET %s, status code %s' %
                (stages_jobs, sj.status_code))
    data_sj = json.loads(sj.content)
    ## extract fields from data_sj
    stage_ids = []
    stage_names = []
    jobIds = []
    jobCompNames = []
    jobExecutionTypes = []
    for x in data_sj:
        stage_ids.append(x.get('id'))
        stage_names.append(x.get('name'))
        jobs = x.get('jobs')
        for job in jobs:
            jobIds.append(job.get('id'))
            jobCompNames.append(job.get('componentName'))
            jobExecutionTypes.append(job.get('componentType'))
    #retrieve BUILD_STAGE_ID and DEPLOY_STAGE_ID
    BUILD_STAGE_ID = stage_ids[0]
    DEPLOY_STAGE_ID = stage_ids[1]
    BUILD_STAGE_NAME = stage_names[0]

    #following arrays have 5 entries and need to delete first entry (build entries not required)
    jobIds.pop(0)
    jobExecutionTypes.pop(0)
    jobCompNames.pop(0)

    #URL for infos about latest Build job executions
    build_executions = '%s/pipeline/pipelines/%s/stages/%s/executions/latest' % (otcPipelineHost, ProjectName, BUILD_STAGE_ID)

    #URL for infos about latest Deploy job executions
    deploy_executions = '%s/pipeline/pipelines/%s/stages/%s/executions/latest' % (otcPipelineHost, ProjectName, DEPLOY_STAGE_ID)

    while True:
        #request latest execution json file for Build stage
        be = requests.get(build_executions, headers=headers, cookies=cookies)
        if be.status_code != 200:
            raise Exception('Failed to retrieve build_executions, failed to GET %s, status code %s' %
                    (build_executions, be.status_code))
        data_be = json.loads(be.content)

        #request latest execution json file for Deploy stage
        de = requests.get(deploy_executions, headers=headers, cookies=cookies)
        if de.status_code != 200:
            raise Exception('Failed to retrieve deploy_executions, failed to GET %s, status code %s' %
                            (deploy_executions, de.status_code))
        data_de = json.loads(de.content)

        #make sure data_de contains stageId (of Deploy stage) and jobExecutions
        if not 'stageId' in data_de:
            raise Exception("output does not contain Deploy 'stage' ")
        stageId = data_de['stageId']  # equals to DEPLOY_STAGE_ID

        if not stageId:
            print "WARNING: Pipeline does not have Deploy stage."
            break

        if not 'jobExecutions' in data_de:
            raise Exception("output does not contain Deploy Executions")
        jobExecutions = data_de['jobExecutions']   #this are job executions of deploy stage

        if not jobExecutions:
            print "WARNING: Pipeline does not have any Deploy job executions."
            break

        jobExecutionJobIds = []  #in latest executions: jobId
        exeStatuses = []
        jobExecutionNumbers = [] #the current build number of the pipeline deployment
        jobinfo = []
        #jobExecutionStatuses = []   # same as exeStatuses
        for jobExecution in jobExecutions:
            jobExecutionJobIds.append(jobExecution.get('jobId'))  ##4. as only deploy stage info
            exeStatuses.append(jobExecution.get('status'))   ##4, as only deploy stage info
            jobExecutionNumbers.append(jobExecution.get('artifactRevision'))  ##4, as only deploy stage info

        #with above info find out if jobs have run
        findJobExecution = False
        for jobId in (jobIds):
            mustContinue = False
            jIndex = jobIds.index(jobId)
            theCompName = jobCompNames[jIndex]
            sb = []
            for jobExecutionJobId in (jobExecutionJobIds):  ##4. as only deploy stage info
                if jobId == jobExecutionJobId:
                    findJobExecution = True
                    jeIndex = jobExecutionJobIds.index(jobExecutionJobId)
                    theStageExeStatus = exeStatuses[jeIndex]
                    theJobStatus = exeStatuses[jeIndex]
                    theJobNumber = jobExecutionNumbers[jeIndex]
                    theJobType = jobExecutionTypes[jeIndex]   ##5, as with build job from Build stage
                    theJobId = jobId;

                    print "stage status: '%s', job_name: '%s', job_type: '%s', job_number: '%s', job_status: '%s'" % (theStageExeStatus, theCompName, theJobType, theJobNumber, theJobStatus)

                    #retrieve status info until all jobs in SUCCESS (FAILURE) status
                    if theStageExeStatus == "RUNNING" or theStageExeStatus == "QUEUED" or theStageExeStatus == "NEW":
                        mustContinue = True
                    elif theJobStatus == "IN_PROGRESS" or theJobStatus == "QUEUED" or theJobStatus == "None":
                        mustContinue = True
                    else:
                        sb.append(theStageExeStatus)
                        sb.append(theJobId)
                        sb.append(theCompName)
                        sb.append(theJobType)
                        sb.append(theJobNumber)
                        sb.append(theJobStatus)
                        jobinfo.append(sb)
                    break
            if findJobExecution:
                findJobExecution = False
            else:
                print "WARNING: Pipeline job id: '%s' does not have any results.  Most likely this means this part of the pipeline has not been run" % (jobId)
                print "\n"
            if mustContinue:
                break
        if mustContinue:
            time.sleep(sleepTime)
        else:
            break

    return jobinfo

def ssologin():
    global LOGIN_URL
    '''
    Login into IDS using the user/pass in the environment variables; this does
    uses the BlueID.
    '''
    print ('Attempting to log into IDS as %s ...'
           % os.environ.get(IDS_USER_ENV_VAR))

    session = requests.Session()
    #headers for login
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.71 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }

    params = {
        'redirect_uri': 'https://console.ng.bluemix.net'
    }
    url = LOGIN_URL + '/login?state=/dashboard/applications'
    r = session.get(url, params=params, headers=headers)
    if r.status_code != 200:
        raise Exception('Failed to GET %s, status code %s' %
                    (url, r.status_code))
    redirect_url = r.history[-1].url
    redirect_url_parser = urlparse.urlparse(redirect_url)
    html = r.content

    # create cookie and add it to session
    key = 'document.cookie="'
    index = html.find(key)
    html = html[index + len(key):]
    cookie_val = html[0: html.find('="')]

    c = requests.cookies.create_cookie(cookie_val, redirect_url,
                                       domain=redirect_url_parser.hostname,
                                       path='/')
    session.cookies.set_cookie(c)
    session.cookies.set

    key = 'window.location.replace("'
    index = html.find(key)
    html = html[index + len(key):]
    idaas_url = html[0: html.find('")')]
    idaas_url_parser = urlparse.urlparse(idaas_url)

    print ('idaas_url=%s' % idaas_url )

    # GET on the IDASS URL to setup the cookies
    r = session.get(idaas_url, headers=headers)
    if r.status_code != 200:
        raise Exception('Failed to GET %s, status code %s' %
                        (url, r.status_code))

    # Login IDASS page, get the form action
    url = ('https://%s/idaas/mtfim/sps/authsvc?PolicyId=urn:ibm:security:authentication:asf:basicldapuser' %
        (idaas_url_parser.hostname))
    r = session.get(url, headers=headers)
    if r.status_code != 200:
        raise Exception('Failed to GET %s, status code %s' %
                        (url, r.status_code))

    print ('get %s' % url )

    # Parse out the action for the ibmid-signin-form
    for line in r.content.split('\n'):
        if "ibmid-signin-form" not in line:
            continue
        key = 'action="'
        index = line.find(key)
        action = line[index + len(key): line.rfind('"')]
        break
    else:
        raise Exception('Failed to parse ibmid-signin-form')

    # POST to sign-in form
    url = 'https://%s%s' % (idaas_url_parser.hostname, action)
    payload = {
        'operation': 'verify',
        'login-form-type': 'pwd',
        'username': os.environ.get(IDS_USER_ENV_VAR),
        'password': os.environ.get(IDS_PASS_ENV_VAR)
    }
    r = session.post(url, data=payload, headers=headers)
    if r.status_code != 200:
        raise Exception('Failed to login to sign-in form %s, status code %s\n%s' %
                        (url, r.status_code, r.content))

    # At this point the cookies should be set
    return requests.utils.dict_from_cookiejar(session.cookies)

if __name__ == "__main__":
    try:
        for var in [IDS_USER_ENV_VAR, IDS_PASS_ENV_VAR]:
            if not os.environ.get(var):
                print "'%s' env var must be set" % var
                exit(-1)
        main()
    except Exception, e:
        traceback.print_exc(file=sys.stdout)
        sys.exit(-1)
