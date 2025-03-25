#!/usr/bin/env python2

# imports
import inwx
import os
from urllib2 import urlopen
from socket import getaddrinfo, gethostname, gethostbyname
from ConfigParser import ConfigParser
from time import strftime

# globals
api_url = "https://api.domrobot.com/xmlrpc/" # this is the url of the API
ipecho = "http://ipecho.net/plain" # this is the URL where the public IPv4 comes from
logfile = None
username = None
password = None
domain = None
subdomain = None
iptype = None
DATEANDTIME_FORMAT = "%d.%m.%y %H:%M:%S"
LOG_NEWLINE = "\n" + str((len(DATEANDTIME_FORMAT) + 3) * " ")

def log(logtext):
    if logfile != None:
        if not os.path.exists(logfile):
            print(dateandtime() + "Logfile doesn't exist. Creating: " + logfile)
        f = open(logfile, "a")
        f.write(dateandtime() + logtext + "\n")
        f.close()
    print(dateandtime() + logtext)

def dateandtime():
    return strftime("[" + DATEANDTIME_FORMAT + "] ")

def readconfig():
    try:
        log("Start reading config.ini.")
        cfg = ConfigParser()
        cfg.read("config.ini")
        global username, password, domain, subdomain, iptype, logfile
        username = cfg.get("General", "username")
        password = cfg.get("General", "password")
        domain = cfg.get("General", "domain")
        subdomain = cfg.get("General", "subdomain")
        iptype = int(cfg.get("General", "iptype"))
        try:
            logfile = cfg.get("General", "logfile")
            log("Now logging to " + logfile + ".")
        except:
            log("No logfile provided. Shell-logging only.")
            logfile = None
        return True
    except:
        log("Error reading your config.ini. Check and try again.")
        return False

def getip(ip_type):
    try:
        log("Now fetching your IPv" + str(ip_type) + "...")
        if ip_type == 4: # for ipv4
            url_socket = urlopen(ipecho)
            url_source = url_socket.read()
            from re import findall
            pattern = "\\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)" + \
                        "\\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\b"
            fetchedips = findall(pattern, url_source)
            fetchedip = fetchedips[0]
            url_socket.close()
        elif ip_type == 6: # for ipv6 (maybe not working in all OS)
            fetchedip = getaddrinfo(gethostname(), None)[0][4][0]
        log("Fetched your IP without errors:" + LOG_NEWLINE + fetchedip)
        return fetchedip
    except:
        log("Error fetching your IPv" + str(ip_type) + "." + LOG_NEWLINE + \
            "Check your internet connection.")
        return None

def main():
    # login credentials
    cred = {"lang": "en", "user": username, "pass": password}
    # domain for request
    dom = {"domain": domain}
    # domrobot object (for request)
    conn = inwx.domrobot(api_url)
    # login
    login = conn.account.login(cred)
    # get nameserver entries
    ninfo = conn.nameserver.info(dom)
    ncount = 0
    # get the one with "server."
    for i in range(len(ninfo["record"])):
        if ninfo["record"][i]["name"] == (subdomain + "." + domain):
            ncount = i
            break
    # save the id of the entry
    nid = ninfo["record"][ncount]["id"]
    # get content of the old entry
    old = ninfo["record"][ncount]["content"]

    global iptype
    ip = getip(iptype)
    if (ip != None) and (ip != old):
        # update the record
        log("IP changed from:" + LOG_NEWLINE + old + \
            LOG_NEWLINE + "to:" + LOG_NEWLINE + ip)
        try:
            log("Now updating record...")
            conn.nameserver.updateRecord({"id": nid, "content": ip})
        except KeyError:
            log("Successfully updated nameserver-record for: " + LOG_NEWLINE + \
                subdomain + "." + domain)
        except Exception as e:
            log("Error occured: " + str(e))
            log("Check the setup of your nameserver-record." + LOG_NEWLINE + \
                "Maybe your IP-version mismatched with the recorded one.")
    elif (ip == old):
        log("Old and current IP were the same. No update required.")
    elif (ip == None):
        log("Did not update anything.")

if __name__ == "__main__":
    log("Started program.")
    if readconfig():
        main()
    else:
        log("Exited without doing anything due to an error.")