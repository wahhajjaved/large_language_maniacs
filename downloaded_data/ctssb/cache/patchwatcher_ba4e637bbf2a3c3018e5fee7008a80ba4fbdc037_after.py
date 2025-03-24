#!/usr/bin/env python
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "patchwatcher2.settings")

import django
django.setup()

import time
import lxml.etree as etree
import logging
import traceback
import hashlib
import socket

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S',
                    filename='patchwatcher.log')

from splitpatch import splitpatchinternal
from utils import *
from patchwork.models import Dataset,currentwork,Patchinfos,CommitData
from commitwatcher import CommitWatcher

LIBVIR_LIST = "https://www.redhat.com/archives/libvir-list"
LIBVIRT_REPO = "git://libvirt.org/libvirt.git"

def freshdateinfo(date):
    try:
        currentwork.delete(currentwork.objects.all()[0])
    except IndexError:
        pass

    currentwork.objects.create(date=date[0], msgid = date[1])

def loaddateinfo():
    try:
        date = currentwork.objects.all()[0]
    except IndexError:
        return
    return [date.date, date.msgid]

def fixbreakpatchset(patchlink, newpatchset, fullcheck=False):
    ext = None
    new = None
    try:
        new = Dataset.objects.get(patchlink=patchlink)
        if not fullcheck:
            return new
    except Exception:
        logging.warning("cannot find %s in db, try to fix it" % patchlink)

    strings = getmaildata(patchlink)
    header = patchlink[:patchlink.find("msg")]
    info = parsehtmlpatch(strings, urlheader=header)
    _, cleansubject, labels = parseSubject(info[0])

    if not new:
        try:
            ext = Dataset.objects.get(name=cleansubject)
        except:
            pass

        m = hashlib.md5()
        m.update(patchlink)
        new = Dataset.objects.create(name=cleansubject, desc=getdescfrommsg(info[3]),
                    group="others", patchlink=patchlink,
                    author=info[1],date=transtime(info[2]),
                    testcase='N/A',testby='N/A',state='ToDo',buglink="N/A", md5lable=m.hexdigest(), patchlabel=' '.join(labels))
        logging.info("create a new obj in db which link is %s" % patchlink)
        newpatchset.append(patchlink)

    if ext:
        new.group = ext.group
        new.save()

    for i in info[4]["Follow-Ups"].keys():
        sitems = fixbreakpatchset(info[4]["Follow-Ups"][i], newpatchset)
        if not sitems:
            continue

        new.subpatch.add(sitems)

    for i in info[4]["References"].keys():
        sitems = fixbreakpatchset(info[4]["References"][i], newpatchset)
        if not sitems:
            continue

        new.subpatch.add(sitems)

    return new

def validPatchSet(patchlink):
    obj = Dataset.objects.get(patchlink=patchlink)
    """ 1st check the same name commit """
    tmplist = CommitData.objects.filter(subject = obj.name)
    """ TODO: check desc """
    if tmplist:
        return False
    else:
        return True

def sendpatchinfo(newpatchset, configure):
    skiplist = []
    for i in newpatchset:
        obj = Dataset.objects.get(patchlink=i)
        if len(obj.subpatch.all()) > 1:
            for n in obj.subpatch.all():
                skiplist.append(n.patchlink)
        elif len(obj.subpatch.all()) == 1 and obj.subpatch.all()[0].patchlink != obj.patchlink:
            """ so not sure for right now """
            skiplist.append(i)

    for i in newpatchset:
        if i in skiplist:
            continue

        if not configure["serverip"]:
            hostip = socket.gethostbyname(socket.gethostname())
        else:
            hostip = configure["serverip"]

        labellist = []
        if configure['label_blacklist']:
            for label in configure['label_blacklist']:
                if label in str(Dataset.objects.get(patchlink=i).patchlabel):
                    labellist.append(label)

        if labellist:
            logging.debug("Skip %s since it has label %s" % (i, ','.join(labellist)))
            continue

        if validPatchSet(i):
            if len(CommitData.objects.all()) > 0:
                commit = CommitData.objects.all()[len(CommitData.objects.all()) - 1].commit
            else:
                commit = ''

            tmpdict = {"_patchurl_" : "http://%s:8888/patchfile/%s" % (hostip, Dataset.objects.get(patchlink=i).md5lable),
                    "_git_commit_": commit}
            try:
                for job in configure['jenkins_job_trigger'].values():
                    jenkinsJobTrigger(tmpdict, job)
            except:
                logging.error("Fail to trigger a jenkins job")
                return

        try:
            pikasendmsg(configure['mqserver'], str(tmpdict), "patchwatcher")
        except pika.exceptions.AMQPConnectionError:
            logging.warning("Cannot connect to "+configure['mqserver'])
            logging.warning("Skip send message")

def updatepatchinfo(groupinfo, patchset, patchinfo, newpatchset):
    tmppatchset = {}
    for n in groupinfo.keys():
        if n not in patchinfo.keys():
            raise ValueError, 'cannot find % link' % n

        if int(groupinfo[n][1]) < 4:
            group = 'group%s' % groupinfo[n][1]
        else:
            group = 'others'

        buglink = "N/A"
        if "buglist" in patchinfo[n].keys():
            if len(patchinfo[n]["buglist"]) > 1:
                buglink = genbuglist(patchinfo[n]["buglist"])
            elif len(patchinfo[n]["buglist"]) == 1:
                buglink = patchinfo[n]["buglist"][0]

        if patchinfo[n]["patchset"]["Follow-Ups"] != {} \
                or patchinfo[n]["patchset"]["References"] != {}:
            tmppatchset[patchinfo[n]["patchlink"]] = [n, patchinfo[n]["patchset"]]

        try:
            """Update buglink to exist item"""
            tmpdate = Dataset.objects.get(patchlink=patchinfo[n]["patchlink"])
            tmpdate.buglink = buglink
            tmpdate.save()
            continue
        except Exception:
            pass

        m = hashlib.md5()
        m.update(patchinfo[n]["patchlink"])
        Dataset.objects.create(name=n, desc=patchinfo[n]["desc"],
                    group=group, patchlink=patchinfo[n]["patchlink"],
                    author=patchinfo[n]["author"],date=transtime(patchinfo[n]["date"]),
                    testcase='N/A',testby='N/A',state='ToDo',buglink=buglink, md5lable=m.hexdigest(), patchlabel=' '.join(patchinfo[n]["labels"]))
        newpatchset.append(patchinfo[n]["patchlink"])

    for n in tmppatchset.keys():
        checkpatchset = True
        name = tmppatchset[n][0]
        subpatch = tmppatchset[n][1]
        if name not in patchset.keys():
            logging.warning("cannot find %s in patchset" % name)
            checkpatchset = False

        try:
            item = Dataset.objects.get(patchlink=n)
        except Exception:
            logging.warning("cannot find %s in db" % n)
            continue

        for i in subpatch["Follow-Ups"].keys():
            if checkpatchset == True and i not in patchset[name]:
                logging.warning("cannot find %s in patchset for %s" % (i, name))

            sitems = fixbreakpatchset(subpatch["Follow-Ups"][i], newpatchset)
            if not sitems:
                continue

            item.subpatch.add(sitems)

        for i in subpatch["References"].keys():
            if checkpatchset == True and i not in patchset[name]:
                logging.warning("cannot find %s in patchset for %s" % (i, name))

            sitems = fixbreakpatchset(subpatch["References"][i], newpatchset)
            if not sitems:
                continue

            item.subpatch.add(sitems)

def parsedatemail(maillist, startdate, enddate, startmsgid):
    retdict = {}
    startdatelist = startdate.split('-')
    enddatelist = enddate.split('-')
    startmonth = startdatelist[1]
    startyear = int(startdatelist[0])
    firstmonth = True
    while int(startyear) <= int(enddatelist[0]):
        if int(startyear) != int(enddatelist[0]):
            endmonth = 12
        else:
            endmonth = enddatelist[1]

        retdict[startyear] = {}
        while int(startmonth) <= int(endmonth):
            mailids = []

            link = genurloflist(maillist, '%s-%s' % (startdatelist[0], startmonth))
            strings = getmaildata(link)
            xml = etree.HTML(strings)
            ul = xml.xpath('/html/body/ul')
            for n in ul[1:]:
                for li in n.getchildren():
                    tmpmsgid = li.getchildren()[0].get('name')
                    patchname = li.getchildren()[0].text
                    if "Re:" in patchname or "PATCH" not in patchname:
                        continue

                    if firstmonth:
                        if int(tmpmsgid) <= int(startmsgid):
                            continue

                    mailids.append(tmpmsgid)

            retdict[startyear][int(startmonth)] = mailids

            startmonth = int(startmonth) + 1
            if firstmonth:
                firstmonth = False

        startyear = int(startyear) + 1
        startmonth = 1

    return retdict

def getmailwithdate(maillist, start, end=None, skipbz=True):
    if not end:
        """ get current date """
        new_end = time.strftime("%Y-%m")
    else:
        new_end = end

    maildict = parsedatemail(maillist, start[0], new_end, start[1])
    maildict2 = {}
    buglist = {}
    patchinfo = {}
    lastmsginfo = start
    for year in maildict.keys():
        for month in maildict[year].keys():
            for msgid in maildict[year][month]:
                hreflist = []
                link = genurlofpatch(maillist, year, month, msgid)
                strings = getmaildata(link)
                try:
                    info = parsehtmlpatch(strings, hreflist, genurlofpatchhead(maillist, year, month))
                except StructError:
                    logging.error("Cannot parse "+link)
                    continue

                _, cleansubject, labels = parseSubject(info[0])
                if skipbz:
                    """ record the patch which already have bz """
                    if "bugzilla.redhat.com" in info[3]:
                        logging.info("find a patch named %s it has bugzilla" % cleansubject)
                        buglist[cleansubject] = hreflist

                maildict2[cleansubject] = info[3]
                patchinfo[cleansubject] = { "patchlink": link,
                                            "desc": getdescfrommsg(info[3]),
                                            "author": info[1],
                                            "date": info[2],
                                            "patchset": info[4],
                                            "labels": labels}
                lastmsginfo = ['%s-%s' % (year, month), str(msgid)]

    if lastmsginfo == start:
        return

    result, patchset = splitpatchinternal(maildict2)

    for n in buglist.keys():
        for i in patchset.keys():
            if n in patchset[i]:
                if "buglist" in patchinfo[i].keys():
                    patchinfo[i]["buglist"].extend(buglist[n])
                else:
                    patchinfo[i]["buglist"] = buglist[n]

        patchinfo[n]["buglist"] = buglist[n]

    return result, patchset, patchinfo, lastmsginfo

def watchlibvirtrepo(checkall=False):
    if not os.access("./libvirt", os.O_RDONLY):
        logging.info("Cannot find libvirt source code")
        logging.info("Download libvirt source code")
        downloadsourcecode(LIBVIRT_REPO)
        return watchlibvirtrepo()

    callgitpull("./libvirt")
    if len(Patchinfos.objects.all()) == 0:
        startdate = Dataset.objects.order_by("date")[0].date.replace(tzinfo=None)
        enddate = currenttime()
        logmsg = getgitlog("./libvirt", startdate, enddate)
        if not logmsg:
            return

        for n in logmsg.splitlines():
            tmplist = Dataset.objects.filter(name = n[n.find(" ")+1:])
            for tmp in tmplist:
                tmp.pushed = "Yes"
                tmp.save()
                logging.debug("update %s pushed status to yes" % tmp.name)

        Patchinfos.objects.create(startdate=startdate, enddate=enddate)

    else:
        Patchinfo = Patchinfos.objects.all()[0]
        startdate = Dataset.objects.order_by("date")[0].date.replace(tzinfo=None)
        enddate = currenttime()
        if checkall:
            logmsg = getgitlog("./libvirt", startdate, enddate)
            if not logmsg:
                return

            for n in logmsg.splitlines():
                tmplist = Dataset.objects.filter(name = n[n.find(" ")+1:])
                for tmp in tmplist:
                    tmp.pushed = "Yes"
                    tmp.save()
                    logging.debug("update %s pushed status to yes" % tmp.name)

            Patchinfo.startdate = startdate
            Patchinfo.enddate = enddate
            Patchinfo.save()

        if startdate < Patchinfo.startdate.replace(tzinfo=None):
            logmsg = getgitlog("./libvirt", startdate, Patchinfo.startdate)
            if not logmsg:
                return

            for n in logmsg.splitlines():
                tmplist = Dataset.objects.filter(name = n[n.find(" ")+1:])
                for tmp in tmplist:
                    tmp.pushed = "Yes"
                    tmp.save()
                    logging.debug("update %s pushed status to yes" % tmp.name)

            Patchinfo.startdate = startdate
            Patchinfo.save()
        if enddate > Patchinfo.enddate.replace(tzinfo=None):
            logmsg = getgitlog("./libvirt", Patchinfo.enddate, enddate)
            if not logmsg:
                return

            for n in logmsg.splitlines():
                tmplist = Dataset.objects.filter(name = n[n.find(" ")+1:])
                for tmp in tmplist:
                    tmp.pushed = "Yes"
                    tmp.save()
                    logging.debug("update %s pushed status to yes" % tmp.name)

            Patchinfo.enddate = enddate
            Patchinfo.save()

def updateCommitData(infos, params):
    CommitData.objects.create(commit=infos['commit'],
            subject=infos['subject'],
            author=infos['author'],
            date=transtime(infos['date']),
            desc=infos['desc'])

    tmplist = Dataset.objects.filter(name = infos['subject'])
    for tmp in tmplist:
        tmp.pushed = "Yes"
        tmp.save()
        logging.debug("update %s pushed status to yes" % tmp.name)

def triggerCommitJobs(infos, params):
    job_info = params['job_info']
    tmpdict = {"_patchurl_" : '',
               "_git_commit_": infos['commit']}
    try:
        jenkinsJobTrigger(tmpdict, job_info)
    except:
        logging.error("Fail to trigger a jenkins job")

def watchLibvirtRepo(config, start_date=None, cb_list=None):
    """
    cb_list contain several dict which have:
    init bool if need call it during init repo
    func func function will be used
    params dict extra params
    """
    if not os.access("./libvirt", os.O_RDONLY):
        logging.info("Cannot find libvirt source code")
        logging.info("Download libvirt source code")
        commit_watcher = CommitWatcher('libvirt', repo_url=LIBVIRT_REPO)

    else:
        commit_watcher = CommitWatcher('libvirt', repo_path='./libvirt')

    if len(CommitData.objects.all()) == 0 and start_date:
        end_date = currenttime()
        tmpdict = commit_watcher.get_commit_by_date(start_date, end_date)
        for commit_id in tmpdict.keys():
            infos = commit_watcher.get_commit_infos(commit_id)
            for cb_dict in cb_list:
                if cb_dict['init']:
                    cb_dict['func'](infos, cb_dict['params'])

    commit_list = commit_watcher.pull()
    if not commit_list:
        return
    logging.info("Get %d commit after pull" % len(commit_list))

    for commit_id in commit_list:
        infos = commit_watcher.get_commit_infos(commit_id)
        for cb_dict in cb_list:
            cb_dict['func'](infos, cb_dict['params'])

def patchwatcher():
    start = ['2016-6', '01005']
    count = 0
    config = loadconfig()
    if Dataset.objects.all():
        startdate = Dataset.objects.order_by("date")[0].date.replace(tzinfo=None)
    else:
        startdate = None
    for i in ["mqserver", "serverip", "jenkins_job_trigger", "label_blacklist"]:
        if i not in config.keys():
            raise Exception("no %s in config file" % i)
    cb_list = []
    cb_list.append({'init': False ,
                    'func': triggerCommitJobs,
                    'params': {'job_info':config['jenkins_job_trigger']['unit_test_job']}})

    cb_list.append({'init': True ,
                    'func': updateCommitData,
                    'params': {}})
    while 1:
        newpatchset = []

        count += 1
        if count%6 == 0:
            logging.info("backups db")
            bakdb()

        if loaddateinfo():
            start = loaddateinfo()

        try:
            groupinfo, patchset, patchinfo, lastmsginfo = getmailwithdate(LIBVIR_LIST, start)
        except Exception, e:
            logging.info("Exception: %s" % e)
            print traceback.format_exc()
            watchLibvirtRepo(config, startdate, cb_list)
            time.sleep(600)
            continue

        logging.info("update %d patches" % len(groupinfo))
        updatepatchinfo(groupinfo, patchset, patchinfo, newpatchset)
        freshdateinfo(lastmsginfo)
        watchLibvirtRepo(config, startdate, cb_list)
        sendpatchinfo(newpatchset, config)
        time.sleep(600)

if __name__ == '__main__':
    patchwatcher()
