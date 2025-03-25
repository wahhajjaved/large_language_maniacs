"""
This crawler will go through the 10 front pages of reddit 
and colect which subreddits they come from then
output that data
"""

import urllib.request
from bs4 import BeautifulSoup
from datetime import datetime
import time


def main():

    notPastEightDays = True
    currLink = "http://www.reddit.com/r/all/?count=0&after=t3_306m8f"
    dictOfSubs = {}
    for i in range(0,11): # go through the first ten pages
        print("######################")
        print("in for loop: " + str(i))
        requestWorked = False
        while not requestWorked:
            try:
                print("making request")
                request = urllib.request.Request(currLink) # stores the request
                soup = BeautifulSoup(urllib.request.urlopen(request, timeout=4)) # make the request and use BS4 to store it
                print("Request worked")
                requestWorked = True # it worked so carry on.
            except  Exception  as e:
                print(e)
                print("Too many requests, sleeping for 5 seconds")
                requestWorked = False
                time.sleep(5) # something went wrong, wait 5 seconds and try again
                print("awake")

        entries = soup.find_all('div', attrs={'class':'entry'}) # find all thread posts on page        
        print("going through entries")

        for entry in entries:
            link = entry.find('a',attrs={'class':'subreddit'})
            sub = link.getText()
            if sub in dictOfSubs:
                dictOfSubs[sub] += 1
            else:
                dictOfSubs[sub] = 1            
        currLink = soup.find('span', attrs={'class':'nextprev'}).find('a',attrs={'rel':'next'}).attrs['href'] # next page
        print("going to next page, first sleep for 5")
        print("######################")
        time.sleep(5)

    outputString = "subbreddit name: number of entries\n"
    for key, value in sorted(mydict.iteritems(), key=lambda k,v: (v,k)) :
        outputString += "%s: %s\n" % (key, value)
        file = open('log.txt', 'w+')
        file.write(outputString)

if __name__ == '__main__':
    main()