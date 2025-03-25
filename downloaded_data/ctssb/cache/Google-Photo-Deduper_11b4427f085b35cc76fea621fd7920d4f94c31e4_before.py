from __future__ import print_function
import httplib2
import os
import errno

import io
from apiclient.http import MediaIoBaseDownload
import pprint 
from googleapiclient.errors import HttpError
import collections

from apiclient import discovery
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage

try:
    import argparse
    parser = argparse.ArgumentParser(parents=[tools.argparser])
    parser.add_argument('-delete', action='store_true', default=False,
                    help='Used to actually perform the delete on Google Photos')
    parser.add_argument('-save', action='store_true', default=False,
                    help='Used to save a backup of all duplicates to a backups directory')

    flags = parser.parse_args()
except ImportError:
    flags = None

# You must select the setting in Google Drive to "Automaticlly put your Google Photos into a folder in My Drive" 
# If modifying these scopes, delete your previously saved credentials
# at ~/.credentials/google-photo-deduper.json
#SCOPES = 'https://www.googleapis.com/auth/drive.photos.readonly' #Use this SCOPE TO BE SAFE
SCOPES = 'https://www.googleapis.com/auth/drive' #Use for full access.  Needed to Delete
#You need to create a client_secret by following Step 1 of the instructions located here: 
#https://developers.google.com/drive/v3/web/quickstart/python
CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_NAME = 'Google Photo Deduper'

#Toggle these to do the actual deleting and backing up to local hardrive.
DELETE = flags.delete
SAVE = flags.save

print("DELETE FLAG IS SET TO: ", DELETE)
print("SAVE FLAG IS SET TO: ", SAVE)

def get_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'google-photo-deduper.json')

    store = Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else: # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to ' + credential_path)
    return credentials

def main():
    pp = pprint.PrettyPrinter(indent=4)
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    
    service = discovery.build('drive', 'v3', http=http)

    dupes = {}
    uniques = {}
    total_files = 0

    query = "mimeType='image/jpeg' or mimeType='image/heif'"
    #query = "name='IMG_3547.HEIC'"
    DEBUG = True

    page_token = None
    while True:
        results = service.files().list(
            q=query, 
            orderBy='createdTime desc',
            pageSize=1000,
            pageToken=page_token,
            fields="nextPageToken, files(id, name, mimeType, createdTime, modifiedTime, imageMediaMetadata)").execute()
        try:
            items = results.get('files', [])
            if not items:
                print('No files found.')
                break
            else:
                total_files += len(items)
                print('Files: ', total_files)
                for item in items:
                    if DEBUG and item['name'] == 'IMG_3547.HEIC': pp.pprint(item)
                    if (item['name'], item['createdTime']) not in dupes:
                        dupes[(item['name'], item['createdTime'])] = {}
                    dupes[(item['name'], item['createdTime'])][item['id']] = item

            #break #this break will make it only do one loop of 1000 images

            page_token = results.get('nextPageToken', None)
            if not page_token:
                break
        except HttpError as error:
            print('An error occurred: %s' % error)
            break

    total = 0
    #if DEBUG: pp.pprint(dupes)
    for dupe in dupes:
        #if DEBUG: pp.pprint(dupe)
        if len(dupes[dupe]) > 1:
            #if DEBUG: pp.pprint(dupes[dupe])
            total = total + len(dupes[dupe])

            if dupe[0]:
                mods = {}
                for item in dupes[dupe]:
                    mods[dupes[dupe][item]['modifiedTime']] = item

                modssorted = collections.OrderedDict(sorted(mods.items()))
                last_item = sorted(mods.keys())[-1]

                for mod_time in mods:
                    item = mods[mod_time]
                    request = service.files().get_media(fileId=dupes[dupe][item]['id'])
                    dir_name = 'backups/' + dupe[0] + "/"
                    filename = dupes[dupe][item]['id'] + '-' + dupes[dupe][item]['name']
                    if mod_time == last_item:
                        filename = "KEEPER-" + filename
                        delete_thisone = False
                    else:
                        delete_thisone = True
                    
                    fullpath = dir_name + filename

                    if SAVE == True:
                        print('Saving ', fullpath)
                        
                        if not os.path.exists(os.path.dirname(fullpath)):
                            try:
                                os.makedirs(os.path.dirname(fullpath))
                            except OSError as exc: # Guard against race condition
                                if exc.errno != errno.EEXIST:
                                    raise                    
                        fh = io.FileIO(fullpath, 'wb')
                        downloader = MediaIoBaseDownload(fh, request)
                        done = False
                        while done is False:
                            status, done = downloader.next_chunk()
                            print("Download %d%%." % int(status.progress() * 100))

                    if DELETE == True and delete_thisone == True:
                        try:
                            service.files().delete(fileId=dupes[dupe][item]['id']).execute()
                            print('deleting', dupes[dupe][item]['id'])
                        except HttpError, error:
                            print('An error occurred: %s' % error)

    print ('Total number of dupes: ', total)


if __name__ == '__main__':
    main()