import time
import requests
import pprint
import json
import datetime
import os

# Parameters that will be passed.
scaleUpCount = int(os.getenv('SCALE_UP_COUNT'))
scaleDownCount = int(os.getenv('SCALE_DN_COUNT'))
maxPodCount = int(os.getenv('MAX_POD_COUNT'))
minPodCount = int(os.getenv('MIN_POD_COUNT'))
depthThreshold = int(os.getenv('MAX_Q_DEPTH'))
timeThreshold = int(os.getenv('SCALE_TIME_THRESHOLD_SECS'))
osUrl = os.getenv('SCALE_URL')
metricUrl = os.getenv('METRIC_URL')
authToken = os.getenv('SA_TOKEN')

# Global variables
lastBreachTime = None
lastNonBreachTime = None

# Function to get the elapsed time since the last breach
def getBreachElapsedTime():
    global lastBreachTime
    if lastBreachTime:
        currentTime = datetime.datetime.now()
        diff = currentTime - lastBreachTime
        return diff.total_seconds()
    else:
        return 0

# Function to get the elapsed time since the first time the normal message consumption is observed
def getNonBreachElapsedTime():
    global lastNonBreachTime
    if lastNonBreachTime:
        currentTime = datetime.datetime.now()
        diff = currentTime - lastNonBreachTime
        return diff.total_seconds()
    else:
        return 0

def getMetrics():
    resp = requests.get(metricUrl)
    return int(resp.text)

def getPodCount():
    headers = {'Authorization': 'Bearer ' + authToken, 'Accept': 'application/json'}
    resp = requests.get(osUrl, headers=headers, verify=False)
    podcount = resp.json().get('spec').get('replicas')
    print("--> CURRENT POD COUNT - " + str(podcount))
    return podcount

def scalePod(desiredPodCount):
    headers = {'Authorization': 'Bearer ' + + authToken, 'Accept': 'application/json', 'Content-Type': 'application/json-patch+json'}
    patchdata = '[{"op":"replace","path":"/spec/replicas","value":"' + desiredPodCount + '"}]'
    resp = requests.patch(osUrl, headers=headers, verify=False, data=patchdata)
    print('--> Scaling to ' + desiredPodCount + '. Response Status - ' + str(resp.status_code))
    return int(desiredPodCount)

def scaleUp(currentPodCount):
    desiredPodCount = str(currentPodCount + scaleUpCount)
    return scalePod(desiredPodCount)

def scaleDown(currentPodCount):
    desiredPodCount = str(currentPodCount - scaleDownCount)
    return scalePod(desiredPodCount)

def isScaleup(currentPodCount):
    if(getMetrics() > depthThreshold) & (getBreachElapsedTime() >= timeThreshold) & (currentPodCount < maxPodCount):
        return True
    elif(getMetrics() > depthThreshold) & (getBreachElapsedTime() >= timeThreshold) & (currentPodCount >= maxPodCount):
        print("--> MAX POD COUNT REACHED")
        return False
    else:
        return False

def isScaleDown(currentPodCount):
    if(getMetrics() < depthThreshold) & (getNonBreachElapsedTime() >= timeThreshold) & (currentPodCount > minPodCount):
        return True
    else:
        return False


def startMonitor():
    time.sleep(50)
    while True:
        global lastBreachTime
        global lastNonBreachTime
        currentPodCount = getPodCount()
        if isScaleup(currentPodCount):
            print("--> LAG observed for more than " + str(timeThreshold) + " secs. SCALE UP . . .")
            currentPodCount = scaleUp(currentPodCount)
            lastBreachTime = None
        elif getMetrics() > depthThreshold:
            print("--> LAG observed in message consumption")
            if lastBreachTime:
                print("--> Continue to observe")
            else:
                print("--> Setting the last breach time")
                lastBreachTime = datetime.datetime.now()
        else:
            if isScaleDown(currentPodCount):
                currentPodCount = scaleDown(currentPodCount)
                lastNonBreachTime = None
            else:
                if lastNonBreachTime:
                    print("--> No LAG, Continue to observe")
                else:
                    lastNonBreachTime = datetime.datetime.now()
        time.sleep(5)

startMonitor()
#print (os.environ)