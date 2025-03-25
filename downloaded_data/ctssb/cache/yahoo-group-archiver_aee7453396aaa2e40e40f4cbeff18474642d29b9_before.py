#!/usr/bin/python3
from __future__ import unicode_literals
import yahoogroupsapi
from yahoogroupsapi import YahooGroupsAPI

import argparse
import codecs
import datetime
import json
import logging
import math
import os
import re
import requests.exceptions
import time
import sys
import unicodedata
from os.path import basename
from collections import OrderedDict
from requests.cookies import RequestsCookieJar, create_cookie


if (sys.version_info < (3, 0)):
    from cookielib import LWPCookieJar
    from urllib import unquote
    from HTMLParser import HTMLParser
    hp = HTMLParser()
    html_unescape = hp.unescape
    text = unicode  # noqa: F821
else:
    from http.cookiejar import LWPCookieJar
    from urllib.parse import unquote
    from html import unescape as html_unescape
    text = str

# WARC metadata params

WARC_META_PARAMS = OrderedDict([('software', 'yahoo-group-archiver'),
                                ('version','20191123.00'),
                                ('format', 'WARC File Format 1.0'),
                                ('command-arguments', ' '.join(sys.argv))
                                ])


def get_best_photoinfo(photoInfoArr, exclude=[]):
    logger = logging.getLogger(name="get_best_photoinfo")
    rs = {'tn': 0, 'sn': 1, 'hr': 2, 'or': 3}

    # exclude types we're not interested in
    for x in exclude:
        if x in rs:
            rs[x] = -1

    best = photoInfoArr[0]
    for info in photoInfoArr:
        if info['photoType'] not in rs:
            logger.error("photoType '%s' not known", info['photoType'])
            continue
        if rs[info['photoType']] >= rs[best['photoType']]:
            best = info
    if rs[best['photoType']] == -1:
        return None
    else:
        return best


def archive_messages_metadata(yga):
    logger = logging.getLogger('archive_message_metadata')
    params = {'sortOrder': 'asc', 'direction': 1, 'count': 1000}

    message_ids = []
    next_page_start = float('inf')
    page_count = 0

    logger.info("Archiving message metadata...")
    last_next_page_start = 0

    while next_page_start > 0:
        msgs = yga.messages(**params)
        with open("message_metadata_%s.json" % page_count, 'wb') as f:
            json.dump(msgs, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

        message_ids += [msg['messageId'] for msg in msgs['messages']]

        logger.info("Archived message metadata records (%d of %d)", len(message_ids), msgs['totalRecords'])

        page_count += 1
        next_page_start = params['start'] = msgs['nextPageStart']
        if next_page_start == last_next_page_start:
            break
        last_next_page_start = next_page_start

    return message_ids


def archive_message_content(yga, id, status="", skipHTML=False, skipRaw=False, noAttachments=False):
    logger = logging.getLogger('archive_message_content')

    if skipRaw is False:
        fname = "%s_raw.json" % (id,)
        if file_keep(fname, " raw message id: %s" % (id,)) is False:
            try:
                logger.info("Fetching  raw message id: %d %s", id, status)
                raw_json = yga.messages(id, 'raw')
                with open(fname, 'wb') as f:
                    json.dump(raw_json, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
                set_mtime(fname, int(raw_json['postDate']))
            except Exception:
                logger.exception("Raw grab failed for message %d", id)

    if skipHTML is False:
        fname = "%s.json" % (id,)
        if file_keep(fname, " raw message id: %s" % (id,)) is False:
            try:
                logger.info("Fetching html message id: %d %s", id, status)
                html_json = yga.messages(id)
                with open(fname, 'wb') as f:
                    json.dump(html_json, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
                set_mtime(fname, int(html_json['postDate']))

                if 'attachmentsInfo' in html_json and (len(html_json['attachmentsInfo']) > 0) and noAttachments is False:
                    with Mkchdir("%d_attachments" % id):
                        process_single_attachment(yga, html_json['attachmentsInfo'])
                    set_mtime(sanitise_folder_name("%d_attachments" % id), int(html_json['postDate']))
            except Exception:
                logger.exception("HTML grab failed for message %d", id)


def archive_email(yga, message_subset=None, start=None, stop=None, skipHTML=False, skipRaw=False, noAttachments=False):
    logger = logging.getLogger('archive_email')
    try:
        # Grab messages for initial counts and permissions check
        init_messages = yga.messages()
    except yahoogroupsapi.AuthenticationError:
        logger.error("Couldn't access Messages functionality for this group")
        return
    except Exception:
        logger.exception("Unknown error archiving messages")
        return

    if start is not None or stop is not None:
        start = start or 1
        stop = stop or init_messages['lastRecordId']
        stop = min(stop, init_messages['lastRecordId'])
        r = range(start, stop + 1)

        if message_subset is None:
            message_subset = list(r)
        else:
            s = set(r).union(message_subset)
            message_subset = list(s)
            message_subset.sort()

    if not message_subset:
        message_subset = archive_messages_metadata(yga)
        logger.info("Group has %s messages (maximum id: %s), fetching all",
                    len(message_subset), (message_subset or ['n/a'])[-1])

    n = 1
    for id in message_subset:
        status = "(%d of %d)" % (n, len(message_subset))
        n += 1
        try:
            archive_message_content(yga, id, status, skipHTML, skipRaw, noAttachments)
        except Exception:
            logger.exception("Failed to get message id: %d", id)
            continue


def archive_topics(yga,noAttachments=False):
    logger = logging.getLogger('archive_topics')

	# Grab messages for initial counts and permissions check
    logger.info("Initializing messages.")
    try:
        init_messages = yga.messages()
    except yahoogroupsapi.AuthenticationError:
        logger.error("Couldn't access Messages functionality for this group")
        return

    expectedTopics = init_messages['numTopics']
    
    logger.info("Getting message metadata.")
    message_subset = archive_messages_metadata(yga)
    if len(message_subset) == 0:
        logger.error("ERROR: no messages available.")
        return
    
	# Occasionally messages reported in the metadata aren't actually available from Yahoo.
	# We also found a group where expectedTopics was 1 less than the actual number of topics available, but the script still downloaded everything.
    logger.info("Expecting %d topics and %d messages.",expectedTopics,len(message_subset))
    
    unretrievableTopicIds = set()
    unretrievableMessageIds = set()
    retrievedTopicIds = set()
    retrievedMessageIds = set()
    potentialMessageIds = set(message_subset)
    
    # Continue trying to grab topics and messages until all potential messages are retrieved or found to be unretrievable.
    while potentialMessageIds:
        startingTopicId = find_topic_id(unretrievableTopicIds,unretrievableMessageIds,retrievedTopicIds,retrievedMessageIds,potentialMessageIds,noAttachments)
        if startingTopicId is not None:
            process_surrounding_topics(startingTopicId,unretrievableTopicIds,unretrievableMessageIds,retrievedTopicIds,retrievedMessageIds,potentialMessageIds,expectedTopics,noAttachments)
    
           
    logger.info("Topic archiving complete.")
    logger.info("There are %d retrieved topic(s).",len(retrievedTopicIds))
    logger.info("There are %d retrieved message(s).",len(retrievedMessageIds))           
    logger.info("There are %d unretrievable topic(s).",len(unretrievableTopicIds))
    logger.info("There are %d unretrievable message(s).",len(unretrievableMessageIds))
    
    # Save the tracking sets.
    with open("retrievedTopicIds.json", 'wb') as f:
            json.dump(list(retrievedTopicIds), codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
    with open("retrievedMessageIds.json", 'wb') as f:
            json.dump(list(retrievedMessageIds), codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
    with open("unretrievableTopicIds.json", 'wb') as f:
            json.dump(list(unretrievableTopicIds), codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
    with open("unretrievableMessageIds.json", 'wb') as f:
            json.dump(list(unretrievableMessageIds), codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)           


# Find a topic ID from among potentialMessageIds to start topic archiving with.
# Also save messages from unretrievable topics when possible.
def find_topic_id(unretrievableTopicIds,unretrievableMessageIds,retrievedTopicIds,retrievedMessageIds,potentialMessageIds,noAttachments=False):
    logger = logging.getLogger('find_topic_id')
    
    # Keep looking as long as the set of potential message IDs is not emty.
    while potentialMessageIds:
        # Check an arbitrary message.
        msgId = potentialMessageIds.pop()
        logger.info("Checking message ID %d to find topic.",msgId)
        try:
            html_json = yga.messages(msgId)
            topicId = html_json.get("topicId")
            logger.info("The message is part of topic ID %d", topicId)
            
            writeMessage = False
            
            # We've already retrieved this topic. This could indicate a bug, or maybe messages have been added since it was downloaded.
            # We'll want to save the individual message.
            if topicId in retrievedTopicIds:
                logger.error("ERROR: This topic has already been archived.")
                writeMessage = True
            
            # We've previously tried getting this topic, and it's no good.
            # Since this is the only way to get the message, go ahead and save it.
            elif topicId in unretrievableTopicIds:
                logger.info("This topic is known to be unretrievable. Saving individual message.")
                writeMessage = True
                
            
            # If we got a message despite some issue with the topic, go ahead and save it.
            # Sometimes Yahoo will give you a message in an unretrievable topic through the messages API.
            if writeMessage:                
                retrievedMessageIds.add(msgId)
                with Mkchdir('email'):
                    if file_keep("%s.json" % (msgId,), "html message id: %d" % (msgId,)) is False:
                        with open("%s.json" % (msgId,), 'wb') as f:
                            json.dump(html_json, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

                    if 'attachmentsInfo' in html_json and (len(html_json['attachmentsInfo']) > 0) and noAttachments is False:
                        with Mkchdir("%d_attachments" % msgId):
                            process_single_attachment(yga, html_json['attachmentsInfo'])
                logger.info("%d total messages downloaded.",len(retrievedMessageIds))
                continue # Keep trying to find a topic ID.
            
            
            # We found a valid topic. Put msgId back in potentialMessageIds since it should be archived with the topic.
            else:
                potentialMessageIds.add(msgId)
                return topicId
            
        except:
            logger.exception("HTML grab failed for message %d", msgId)
            unretrievableMessageIds.add(msgId)
    
    # Ran out of messages to check.        
    return None
    
    
def process_surrounding_topics(startingTopicId,unretrievableTopicIds,unretrievableMessageIds,retrievedTopicIds,retrievedMessageIds,potentialMessageIds,expectedTopics,noAttachments=False):
    logger = logging.getLogger(name="process_surrounding_topics")
    topicResults = process_single_topic(startingTopicId,unretrievableTopicIds,unretrievableMessageIds,retrievedTopicIds,retrievedMessageIds,potentialMessageIds,expectedTopics,noAttachments)
    if topicResults["gotTopic"] is False:
        return
        
    nextTopicId = topicResults["nextTopicId"]
    prevTopicId = topicResults["prevTopicId"]
    if nextTopicId > 0:
        logger.info("The next topic ID is %d.",nextTopicId)
    else:
        logger.info("There are no later topics.")

    if prevTopicId > 0:
        logger.info("The previous topic ID is %d.",prevTopicId)
    else:
        logger.info("There are no previous topics.")
        
        
    # Grab all previous topics from the starting topic back.
    logger.info("Retrieving previous topics.")
    while prevTopicId > 0:
        if prevTopicId in unretrievableTopicIds:
            logger.info("Reached known unretrievable topic ID %d",prevTopicId)
            break
        topicResults = process_single_topic(prevTopicId,unretrievableTopicIds,unretrievableMessageIds,retrievedTopicIds,retrievedMessageIds,potentialMessageIds,expectedTopics,noAttachments)
        prevTopicId = topicResults["prevTopicId"]
        
    # Grab all later topics from the starting topic forward.
    logger.info("Retrieving later topics.")
    while nextTopicId > 0:
        if nextTopicId in unretrievableTopicIds:
            logger.info("Reached known unretrievable topic ID %d",nextTopicId)
            break
        topicResults = process_single_topic(nextTopicId,unretrievableTopicIds,unretrievableMessageIds,retrievedTopicIds,retrievedMessageIds,potentialMessageIds,expectedTopics,noAttachments)
        nextTopicId = topicResults["nextTopicId"]

 
def process_single_topic(topicId,unretrievableTopicIds,unretrievableMessageIds,retrievedTopicIds,retrievedMessageIds,potentialMessageIds,expectedTopics,noAttachments=False):
    logger = logging.getLogger(name="process_single_topic")
    topicResults = {
        "gotTopic": False,
        "nextTopicId": 0,
        "prevTopicId": 0
    }
    
    # Grab the topic.
    topic_json = None
    gotTopic = False
    
    # We already have the topic on disk and don't want to overwrite it.
    if file_keep("%s.json" % (topicId,), "topic id: %d" % (topicId,)):
        # However, we need the previous and next topic, so we have to load the json.
        try:
            with open('%s.json' % (topicId,), 'r', encoding='utf-8') as f:
                topic_json = json.load(f)
            gotTopic = True
        except:
            logger.exception("ERROR: couldn't load %s.json from disk.",topicId)
    
    # We didn't load the topic from disk, so we need to try downloading it.
    if gotTopic is False:
        try:
            logger.info("Fetching topic ID %d", topicId)
            topic_json = yga.topics(topicId,maxResults=999999)
            gotTopic = True
            # Save it now.
            with open("%s.json" % (topicId,), 'wb') as f:
                json.dump(topic_json, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
        except:
            logger.exception("ERROR downloading topic ID %d", topicId)
    
    # We couldn't get the topic. Categorize it as unretrievable and return.
    if gotTopic is False:
        unretrievableTopicIds.add(topicId)
        return topicResults
    
    # We have the topic.
    retrievedTopicIds.add(topicId)
    topicResults["gotTopic"] = True
    topicResults["nextTopicId"] = topic_json.get("nextTopicId")
    topicResults["prevTopicId"] = topic_json.get("prevTopicId")

    # Figure out what messages we got and download attachments.
    messages = topic_json.get("messages")
    for message in messages:
        # Track what messages we've gotten.
        msgId = message.get("msgId")
        retrievedMessageIds.add(msgId)
        unretrievableMessageIds.discard(msgId) # probably not in there, but possible if we got an intermittent timeout
        try:
            potentialMessageIds.remove(msgId)
        # Intermittent timeouts can cause this.
        except:
            logger.exception("ERROR: Tried to remove msgId %d from potentialMessageIds when it wasn't there.",msgId)
                            
        # Download messsage attachments if there are any.
        if 'attachmentsInfo' in message and (len(message['attachmentsInfo']) > 0) and noAttachments is False:
            with Mkchdir("%d_attachments" % msgId):
                process_single_attachment(yga, message['attachmentsInfo'])
        
    logger.info("Fetched topic ID %d with message count %d (topic %d of %d). %d total messages downloaded.",topicId,topic_json.get("totalMsgInTopic"),len(retrievedTopicIds),expectedTopics,len(retrievedMessageIds))   
    return topicResults


def process_single_attachment(yga, attach):
    logger = logging.getLogger(name="process_single_attachment")
    for frec in attach:
        fname = sanitise_file_name("%s-%s" % (frec['fileId'], frec['filename']))

        if file_keep(fname, "file: %s" % (fname,)) is False:
            with open(fname, 'wb') as f:
                logger.info("Fetching attachment '%s'", frec['filename'])
                if 'link' in frec:
                    # try and download the attachment
                    # (sometimes yahoo doesn't keep them)
                    try:
                        yga.download_file(frec['link'], f=f)
                    except requests.exceptions.HTTPError as err:
                        logger.error("ERROR downloading attachment '%s': %s", frec['link'], err)
                    continue

                elif 'photoInfo' in frec:
                    process_single_photo(frec['photoInfo'],f)

            set_mtime(fname, frec['modificationDate'])


def process_single_photo(photoinfo,f):
    logger = logging.getLogger(name="process_single_photo")
    # keep retrying until we find the largest image size we can download
    # (sometimes yahoo doesn't keep the originals)
    exclude = []
    ok = False
    while not ok:
        # find best photoinfo (largest size)
        bestPhotoinfo = get_best_photoinfo(photoinfo, exclude)

        if bestPhotoinfo is None:
            logger.error("Can't find a viable copy of this photo")
            break

        # try and download it
        try:
            yga.download_file(bestPhotoinfo['displayURL'], f=f)
            ok = True
        except requests.exceptions.HTTPError as err:
            # yahoo says no. exclude this size and try for another.
            logger.error("ERROR downloading '%s' variant %s: %s", bestPhotoinfo['displayURL'],
                         bestPhotoinfo['photoType'], err)
            exclude.append(bestPhotoinfo['photoType'])

def archive_files(yga, subdir=None):
    logger = logging.getLogger(name="archive_files")
    try:
        if subdir:
            file_json = yga.files(sfpath=subdir)
        else:
            file_json = yga.files()
    except Exception:
        logger.error("Couldn't access Files functionality for this group")
        return

    with open('fileinfo.json', 'wb') as f:
        json.dump(file_json['dirEntries'], codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

    n = 0
    sz = len(file_json['dirEntries'])
    for path in file_json['dirEntries']:
        n += 1
        if path['type'] == 0:
            # Regular file
            name = html_unescape(path['fileName'])
            new_name = sanitise_file_name("%d_%s" % (n, name))
            if file_keep(new_name, ": %s" % (new_name,)) is False:
                logger.info("Fetching file '%s' as '%s' (%d/%d)", name, new_name, n, sz)
                with open(new_name, 'wb') as f:
                    try:
                        yga.download_file(path['downloadURL'], f)
                    except:
                        pass # Bad size exceptions can sometimes cause issues going from -f to -i.
                set_mtime(new_name, path['createdTime'])

        elif path['type'] == 1:
            # Directory
            name = html_unescape(path['fileName'])
            new_name = "%d_%s" % (n, name)
            logger.info("Fetching directory '%s' as '%s' (%d/%d)", name, sanitise_folder_name(new_name), n, sz)
            with Mkchdir(new_name):     # (new_name sanitised again by Mkchdir)
                pathURI = unquote(path['pathURI'])
                archive_files(yga, subdir=pathURI)
            set_mtime(sanitise_folder_name(new_name), path['createdTime'])


def archive_attachments(yga):
    logger = logging.getLogger(name="archive_attachments")
    try:
        attachments_json = yga.attachments(count=999999)
    except Exception:
        logger.error("Couldn't access Attachments functionality for this group")
        return

    with open('allattachmentinfo.json', 'wb') as f:
        json.dump(attachments_json['attachments'], codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

    n = 0
    for a in attachments_json['attachments']:
        n += 1
        with Mkchdir(a['attachmentId']):
            try:
                a_json = yga.attachments(a['attachmentId'])
            except Exception:
                logger.error("Attachment id %d inaccessible.", a['attachmentId'])
                continue
            with open('attachmentinfo.json', 'wb') as f:
                json.dump(a_json, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
                process_single_attachment(yga, a_json['files'])
        set_mtime(sanitise_folder_name(a['attachmentId']), a['modificationDate'])


def archive_photos(yga):
    logger = logging.getLogger(name="archive_photos")
    try:
        nb_albums = yga.albums(count=5)['total'] + 1
    except Exception:
        logger.error("Couldn't access Photos functionality for this group")
        return
    albums = yga.albums(count=nb_albums)
    n = 0

    with open('albums.json', 'wb') as f:
        json.dump(albums['albums'], codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

    for a in albums['albums']:
        n += 1
        name = html_unescape(a['albumName'])
        # Yahoo sometimes has an off-by-one error in the album count...
        logger.info("Fetching album '%s' (%d/%d)", name, n, albums['total'])

        folder = "%d-%s" % (a['albumId'], name)

        with Mkchdir(folder):
            photos = yga.albums(a['albumId'])
            pages = int(photos['total'] / 100 + 1)
            p = 0

            for page in range(pages):
                photos = yga.albums(a['albumId'], start=page*100, count=100)
                with open('photos-%d.json' % page, 'wb') as f:
                    json.dump(photos['photos'], codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

                for photo in photos['photos']:
                    p += 1
                    pname = html_unescape(photo['photoName'])
                    fname = sanitise_file_name("%d-%s.jpg" % (photo['photoId'], pname))
                    if file_keep(fname, "photo: %s" % (fname,)) is False:
                        logger.info("Fetching photo '%s' (%d/%d)", pname, p, photos['total'])
                        with open(fname, 'wb') as f:
                            process_single_photo(photo['photoInfo'],f)
                        set_mtime(fname, photo['creationDate'])

        set_mtime(sanitise_folder_name(folder), a['modificationDate'])


def archive_db(yga):
    logger = logging.getLogger(name="archive_db")
    try:
        db_json = yga.database()
    except yahoogroupsapi.AuthenticationError:
        db_json = None
        # 401 or 403 error means Permission Denied; 307 means redirect to login. Retrying won't help.
        logger.error("Couldn't access Database functionality for this group")
        return

    with open('databases.json', 'wb') as f:
        json.dump(db_json, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

    n = 0
    nts = len(db_json['tables'])
    for table in db_json['tables']:
        n += 1
        try:
            logger.info("Downloading database table '%s' (%d/%d)", table['name'], n, nts)

            name = "%s_%s.csv" % (table['tableId'], table['name'])
            uri = "https://groups.yahoo.com/neo/groups/%s/database/%s/records/export?format=csv" % (yga.group, table['tableId'])

            if file_keep(sanitise_file_name(name), "database: %s" % (sanitise_file_name(name),)) is False:
                with open(sanitise_file_name(name), 'wb') as f:
                    yga.download_file(uri, f)
                set_mtime(sanitise_file_name(name), table['dateLastModified'])

            records_json = yga.database(table['tableId'], 'records')
            if file_keep('%s_records.json' % table['tableId'], "database records: %s_records.json" % (table['tableId'],)) is False:
                with open('%s_records.json' % table['tableId'], 'wb') as f:
                    json.dump(records_json, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
                set_mtime('%s_records.json' % table['tableId'], table['dateLastModified'])
        except Exception:
            logger.exception("Failed to get table '%s' (%d/%d)", table['name'], n, nts)
            continue


def archive_links(yga, subdir=''):
    logger = logging.getLogger(name="archive_links")

    try:
        links = yga.links(linkdir=subdir)
    except yahoogroupsapi.AuthenticationError:
        logger.error("Couldn't access Links functionality for this group")
        return

    with open('links.json', 'wb') as f:
        json.dump(links, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
        logger.info("Written %d links from %s folder", links['numLink'], subdir)

    n = 0
    for a in links['dirs']:
        n += 1
        logger.info("Fetching links folder '%s' (%d/%d)", a['folder'], n, links['numDir'])

        with Mkchdir(a['folder']):
            archive_links(yga, "%s/%s" % (subdir, a['folder']))


def archive_calendar(yga):
    logger = logging.getLogger(name="archive_calendar")
    groupinfo = yga.HackGroupInfo()

    if 'entityId' not in groupinfo:
        logger.error("Couldn't download calendar/events: missing entityId")
        return

    entityId = groupinfo['entityId']

    api_root = "https://calendar.yahoo.com/ws/v3"
    
    # We get the wssid
    tmpUri = "%s/users/%s/calendars/events/?format=json&dtstart=20000101dtend=20000201&wssid=Dummy" % (api_root, entityId)
    logger.info("Getting wssid. Expecting 401 or 403 response.")
    try:
        yga.download_file(tmpUri)  # We expect a 403 or 401  here
        logger.error("Attempt to get wssid returned HTTP 200, which is unexpected!")  # we should never hit this
        return
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 403 or e.response.status_code == 401:
            try:
                tmpJson = json.loads(e.response.text)['calendarError']
            except:
                logger.exception("ERROR: Couldn't load wssid exception to get calendarError.")
                return
        else:
            logger.error("Attempt to get wssid returned an unexpected response status %d" % e.response.status_code)
            return

    if 'wssid' not in tmpJson:
        logger.error("Couldn't download calendar/events: missing wssid")
        return
    wssid = tmpJson['wssid']
    
    # Getting everything since the launch of Yahoo! Groups (January 30, 2001)
    archiveDate = datetime.datetime(2001, 1, 30)
    endDate = datetime.datetime(2025, 1, 1)
    while archiveDate < endDate:
        jsonStart = archiveDate.strftime("%Y%m%d")
        jsonEnd = (archiveDate + datetime.timedelta(days=1000)).strftime("%Y%m%d")
        calURL = "%s/users/%s/calendars/events/?format=json&dtstart=%s&dtend=%s&wssid=%s" % \
            (api_root, entityId, jsonStart, jsonEnd, wssid)

        try:
            logger.info("Trying to get events between %s and %s", jsonStart, jsonEnd)
            calContentRaw = yga.download_file(calURL)
        except requests.exception.HTTPError:
            logger.error("Unrecoverable error getting events between %s and %s: URL %s", jsonStart, jsonEnd, calURL)

        calContent = json.loads(calContentRaw)
        if calContent['events']['count'] > 0:
            filename = jsonStart + "-" + jsonEnd + ".json"
            with open(filename, 'wb') as f:
                logger.info("Got %d event(s)", calContent['events']['count'])
                json.dump(calContent, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

        archiveDate += datetime.timedelta(days=1000)


def archive_about(yga):
    logger = logging.getLogger(name="archive_about")
    groupinfo = yga.HackGroupInfo()
    logger.info("Downloading group description data")

    with open('about.json', 'wb') as f:
        json.dump(groupinfo, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

    statistics = yga.statistics()

    with open('statistics.json', 'wb') as f:

        json.dump(statistics, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)

    exclude = []
    # Check if we really have a photo in the group description
    if ('photoInfo' in statistics['groupHomePage'] and statistics['groupHomePage']['photoInfo']):
        # Base filename on largest photo size.
        bestphotoinfo = get_best_photoinfo(statistics['groupHomePage']['photoInfo'], exclude)
        fname = 'GroupPhoto-%s' % basename(bestphotoinfo['displayURL']).split('?')[0]
        logger.info("Downloading the photo in group description as %s", fname)
        with open(sanitise_file_name(fname), 'wb') as f:
            process_single_photo(statistics['groupHomePage']['photoInfo'],f)

    if statistics['groupCoverPhoto']['hasCoverImage']:
        # Base filename on largest photo size.
        bestphotoinfo = get_best_photoinfo(statistics['groupCoverPhoto']['photoInfo'], exclude)
        fname = 'GroupCover-%s' % basename(bestphotoinfo['displayURL']).split('?')[0]
        logger.info("Downloading the group cover as %s", fname)
        with open(sanitise_file_name(fname), 'wb') as f:
            process_single_photo(statistics['groupCoverPhoto']['photoInfo'],f)


def archive_polls(yga):
    logger = logging.getLogger(name="archive_polls")
    try:
        pollsList = yga.polls(count=100, sort='DESC')
    except yahoogroupsapi.AuthenticationError:
        logger.error("Couldn't access Polls functionality for this group")
        return

    if len(pollsList) == 100:
        logger.info("Got 100 polls, checking if there are more ...")
        endoflist = False
        offset = 99

        while not endoflist:
            tmpList = yga.polls(count=100, sort='DESC', start=offset)
            tmpCount = len(tmpList)
            logger.info("Got %d more polls", tmpCount)

            # Trivial case first
            if tmpCount < 100:
                endoflist = True

            # Again we got 100 polls, increase the offset
            if tmpCount == 100:
                offset += 99

            # Last survey
            if pollsList[len(pollsList)-1]['surveyId'] == tmpList[len(tmpList)-1]['surveyId']:
                logger.info("No new polls found with offset %d", offset)
                endoflist = True
                break

            pollsList += tmpList

    totalPolls = len(pollsList)
    logger.info("Found %d polls to grab", totalPolls)

    n = 0
    for p in pollsList:
        n += 1
        try:
            logger.info("Downloading poll %d [%d/%d]", p['surveyId'], n, totalPolls)
            pollInfo = yga.polls(p['surveyId'])
            fname = '%s-%s.json' % (n, p['surveyId'])

            with open(fname, 'wb') as f:
                json.dump(pollInfo, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
            set_mtime(fname, pollInfo['dateCreated'])
        except Exception:
            logger.exception("Failed to get poll %d [%d/%d]", p['surveyId'], n, totalPolls)
            continue



def archive_members(yga):
    logger = logging.getLogger(name="archive_members")
    try:
        confirmed_json = yga.members('confirmed')
    except yahoogroupsapi.AuthenticationError:
        logger.error("Couldn't access Members list functionality for this group")
        return
    n_members = confirmed_json['total']
    # we can dump 100 member records at a time
    all_members = []
    for i in range(int(math.ceil(n_members)/100 + 1)):
        confirmed_json = yga.members('confirmed', start=100*i, count=100)
        all_members = all_members + confirmed_json['members']
        with open('memberinfo_%d.json' % i, 'wb') as f:
            json.dump(confirmed_json, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
    all_json_data = {"total": n_members, "members": all_members}
    with open('allmemberinfo.json', 'wb') as f:
        json.dump(all_json_data, codecs.getwriter('utf-8')(f), ensure_ascii=False, indent=4)
    logger.info("Saved members: Expected: %d, Actual: %d", n_members, len(all_members))


####
# Utility Functions
####

def set_mtime(path, mtime):
    """
    Sets the last-modified date of a file or directory
    """
    atime = time.time()
    os.utime(path, (atime, mtime))


def sanitise_file_name(value):
    """
    Convert spaces to hyphens.  Remove characters that aren't alphanumerics, underscores, periods or hyphens.
    Also strip leading and trailing whitespace and periods.
    """
    value = text(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s.-]', '', value).strip().strip('.')
    return re.sub(r'[-\s]+', '-', value)


def sanitise_folder_name(name):
    return sanitise_file_name(name).replace('.', '_')


def file_keep(fname, type = ""):
    """
    Test existance of given file name and global overwrite flag.
    If not overwriting and present then log the fact and the data type (type).
    Returns True if file present otherwise False
    """
    logger = logging.getLogger('file_keep')

    if args.overwrite:
        return False
    
    if os.path.exists(fname) is False:
        return False
    
    logger.debug("File already present %s", type)
    return True


class Mkchdir:
    d = ""

    def __init__(self, d, sanitize=True):
        self.d = sanitise_folder_name(d) if sanitize else d

    def __enter__(self):
        try:
            os.mkdir(self.d)
        except OSError:
            pass
        os.chdir(self.d)

    def __exit__(self, exc_type, exc_value, traceback):
        os.chdir('..')


class CustomFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        if '%f' in datefmt:
            datefmt = datefmt.replace('%f', '%03d' % record.msecs)
        return logging.Formatter.formatTime(self, record, datefmt)


def init_cookie_jar(cookie_file=None, cookie_t=None, cookie_y=None, cookie_euconsent=None):
    cookie_jar = LWPCookieJar(cookie_file) if cookie_file else RequestsCookieJar()

    if cookie_file and os.path.exists(cookie_file):
        cookie_jar.load(ignore_discard=True)

    if args.cookie_t:
        cookie_jar.set_cookie(create_cookie('T', cookie_t))
    if cookie_y:
        cookie_jar.set_cookie(create_cookie('Y', cookie_y))
    if cookie_euconsent:
        cookie_jar.set_cookie(create_cookie('EuConsent', cookie_euconsent))

    if cookie_file:
        cookie_jar.save(ignore_discard=True)

    return cookie_jar


if __name__ == "__main__":
    p = argparse.ArgumentParser()

    pa = p.add_argument_group(title='Authentication Options')
    pa.add_argument('-ct', '--cookie_t', type=str,
                    help='T authentication cookie from yahoo.com')
    pa.add_argument('-cy', '--cookie_y', type=str,
                    help='Y authentication cookie from yahoo.com')
    pa.add_argument('-ce', '--cookie_e', type=str, default='',
                    help='Additional EuConsent cookie is required in EU')
    pa.add_argument('-cf', '--cookie-file', type=str,
                    help='File to store authentication cookies to. Cookies passed on the command line will overwrite '
                    'any already in the file.')

    po = p.add_argument_group(title='What to archive', description='By default, all the below.')
    po.add_argument('-e', '--email', action='store_true',
                    help='Only archive html and raw email and attachments (from email) through the messages API')
    po.add_argument('-at', '--attachments', action='store_true',
                    help='Only archive attachments (from attachments list)')
    po.add_argument('-f', '--files', action='store_true',
                    help='Only archive files')
    po.add_argument('-i', '--photos', action='store_true',
                    help='Only archive photo galleries')
    po.add_argument('-t', '--topics', action='store_true',
                    help='Only archive HTML email and attachments through the topics API')
    po.add_argument('-r', '--raw', action='store_true',
                    help='Only archive raw email without attachments through the messages API')
    po.add_argument('-d', '--database', action='store_true',
                    help='Only archive database')
    po.add_argument('-l', '--links', action='store_true',
                    help='Only archive links')
    po.add_argument('-c', '--calendar', action='store_true',
                    help='Only archive events')
    po.add_argument('-p', '--polls', action='store_true',
                    help='Only archive polls')
    po.add_argument('-a', '--about', action='store_true',
                    help='Only archive general info about the group')
    po.add_argument('-m', '--members', action='store_true',
                    help='Only archive members')
    po.add_argument('-o', '--overwrite', action='store_true',
                    help='Overwrite existing files such as email and database records')
    po.add_argument('-na', '--noattachments', action='store_true',
                    help='Skip attachment downloading as part of topics and e-mails')


    pr = p.add_argument_group(title='Request Options')
    pr.add_argument('--user-agent', type=str,
                    help='Override the default user agent used to make requests')

    pc = p.add_argument_group(title='Message Range Options',
                              description='Options to specify which messages to download. Use of multiple options will '
                              'be combined. Note: These options will also try to fetch message IDs that may not exist '
                              'in the group.')
    pc.add_argument('--start', type=int,
                    help='Email message id to start from (specifying this will cause only specified message contents to'
                    ' be downloaded, and not message indexes). Default to 1, if end option provided.')
    pc.add_argument('--stop', type=int,
                    help='Email message id to stop at (inclusive), defaults to last message ID available, if start '
                    'option provided.')
    pc.add_argument('--ids', nargs='+', type=int,
                    help='Get email message by ID(s). Space separated, terminated by another flag or --')

    pf = p.add_argument_group(title='Output Options')
    pf.add_argument('-w', '--warc', action='store_true',
                    help='Output WARC file of raw network requests. [Requires warcio package installed]')

    p.add_argument('-v', '--verbose', action='store_true')
    p.add_argument('--colour', '--color', action='store_true', help='Colour log output to terminal')
    p.add_argument('--delay', type=float, default=0.2, help='Minimum delay between requests (default 0.2s)')

    p.add_argument('group', type=str)

    args = p.parse_args()

    # Setup logging
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    log_format = {'fmt': '%(asctime)s %(levelname)s %(name)s %(message)s', 'datefmt': '%Y-%m-%d %H:%M:%S.%f %Z'}
    log_formatter = CustomFormatter(**log_format)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    if args.colour:
        try:
            import coloredlogs
        except ImportError as e:
            print("Coloured logging output requires the 'coloredlogs' package to be installed.")
            raise e
        coloredlogs.install(level=log_level, **log_format)
    else:
        log_stdout_handler = logging.StreamHandler(sys.stdout)
        log_stdout_handler.setLevel(log_level)
        log_stdout_handler.setFormatter(log_formatter)
        root_logger.addHandler(log_stdout_handler)

    cookie_jar = init_cookie_jar(args.cookie_file, args.cookie_t, args.cookie_y, args.cookie_e)

    headers = {}
    if args.user_agent:
        headers['User-Agent'] = args.user_agent

    yga = YahooGroupsAPI(args.group, cookie_jar, headers, min_delay=args.delay)

    # Default to all unique content. This includes topics and raw email, 
    # but not the full email download since that would duplicate html emails we get through topics.
    if not (args.email or args.files or args.photos or args.database or args.links or args.calendar or args.about or
            args.polls or args.attachments or args.members or args.topics or args.raw):
        args.files = args.photos = args.database = args.links = args.calendar = args.about = \
            args.polls = args.attachments = args.members = args.topics = args.raw = True

    with Mkchdir(args.group, sanitize=False):
        log_file_handler = logging.FileHandler('archive.log','w','utf-8')
        log_file_handler.setFormatter(log_formatter)
        root_logger.addHandler(log_file_handler)

        if args.warc:
            try:
                from warcio import WARCWriter
            except ImportError:
                logging.error('WARC output requires the warcio package to be installed.')
                exit(1)
            fhwarc = open('data.warc.gz', 'ab')
            warc_writer = WARCWriter(fhwarc)
            warcmeta = warc_writer.create_warcinfo_record(fhwarc.name, WARC_META_PARAMS)
            warc_writer.write_record(warcmeta)
            yga.set_warc_writer(warc_writer)

        if args.email:
            with Mkchdir('email'):
                archive_email(yga, message_subset=args.ids, start=args.start, stop=args.stop,noAttachments=args.noattachments)
        if args.files:
            with Mkchdir('files'):
                archive_files(yga)
        if args.photos:
            with Mkchdir('photos'):
                archive_photos(yga)
        if args.topics:
            with Mkchdir('topics'):
                archive_topics(yga,noAttachments=args.noattachments)
        if args.raw:
            with Mkchdir('email'):
                archive_email(yga, message_subset=args.ids, start=args.start, stop=args.stop,skipHTML=True)
        if args.database:
            with Mkchdir('databases'):
                archive_db(yga)
        if args.links:
            with Mkchdir('links'):
                archive_links(yga)
        if args.about:
            with Mkchdir('about'):
                archive_about(yga)
        if args.polls:
            with Mkchdir('polls'):
                archive_polls(yga)
        if args.attachments:
            with Mkchdir('attachments'):
                archive_attachments(yga)
        if args.members:
            with Mkchdir('members'):
                archive_members(yga)
        if args.calendar:
            with Mkchdir('calendar'):
                archive_calendar(yga)

        if args.warc:
            fhwarc.close()
