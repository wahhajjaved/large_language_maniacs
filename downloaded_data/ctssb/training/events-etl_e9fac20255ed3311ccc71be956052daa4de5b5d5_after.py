# encoding=utf8

import os
import requests
import json
import datetime

#const 
UNNECESSARY_ELEMENTS = ['campaign', 'confirmed_at', 'created_at', 'creator', 'directions',  \
                        'ends_at', 'ends_at_utc', 'fields', 'host_is_confirmed', 'max_attendees', \
                        'note_to_attendees', 'notes', 'phone', 'plus4', 'updated_at'\
                        ]
SUPER_GROUP = 'PeoplePower'
EVENT_TYPE = 'Action'

#Headers
_TITLE = 'title'
_URL = 'browser_url'
_STARTDATE = 'starts_at'

_PREURL = "https://go.peoplepower.org/event/action/"
_LIMIT = 20

def grab_data():
    cleaned_data = retrieve_and_clean_data()
    translated_data = translate_data(cleaned_data)
    
    return translated_data
    
def retrieve_and_clean_data():
    """
    We retrieve data through the API and URL given to us by the 
    partner organization. We remove the unnecessary elements as 
    defined in UNNECESSARY_ELEMENTS
    """
    
    print(" -- Retrieving ACLU People Power Action")
    # start at page 1
    page = 0
    has_more_content = True
    event_endpoint = os.environ.get('PEOPLEPOWER_ACTION_URL')
    
    cleaned_data = []
    
    total_signups = 0
    
    while has_more_content:
        offset = page * _LIMIT
        req = requests.get(event_endpoint + ("&_offset=%d" % offset), data={'_limit': _LIMIT}, headers={"Access": 'application/json'})
        print ("---- Going to Page", page, offset, req.status_code)
        
        page = page + 1
        print (req)
        if req.status_code != 200:
            raise ValueError("Error in retrieving ", req.status_code)
        else:
            json_data = json.loads(req.text)
            events = json_data['objects']
            has_more_content = len(events) == _LIMIT
            
            for event in events:
                # remove private data
                
                if not event["is_approved"]:
                    continue
                    
                if not event["status"] == "active":
                    continue
                    
                for unneeded_key in UNNECESSARY_ELEMENTS:
                    if unneeded_key in event:
                        del event[unneeded_key]
                # print("\n\n")
                total_signups = total_signups + event['attendee_count']
                cleaned_data.append(event)
            
            # will continue to traverse if has more content
    #endof while has content
        
    return cleaned_data


def translate_data(cleaned_data):
    """
    This is where we translate the data to the necessary information for the map
    """
    print(" -- Translating People Power Action")
    translated_data = []
    
    for data in cleaned_data:
        address = clean_venue(data)
        
        group_name = data['title']
        has_coords = 'latitude' in data and 'longitude' in data
        
        if not has_coords:
            continue
        
        if data['starts_at'][:10] < datetime.date.today().strftime('%Y-%m-%d'):
            continue

        event = {
            'title': data[_TITLE] if _TITLE in data else None, 
            'url': _PREURL + ("%d" % data['id']),
            'supergroup' : SUPER_GROUP,
            'group': group_name,
            'event_type': EVENT_TYPE,
            'start_datetime': data[_STARTDATE] if _STARTDATE in data else None,
            'venue': address,
            'lat': data['latitude'] if has_coords else None,
            'lng': data['longitude'] if has_coords else None
        }
        
        translated_data.append(event)

    return translated_data

def clean_venue(location):
    """
    We translate the venue information to a flat structure
    """
    venue = location['venue'] + '.' if 'venue' in location else None
    address = ''.join([location['address1'], location['address2']])
    locality = location['city'] if 'city' in location else None
    region = location['region'] if 'region' in location else None
    postal_code = location['postal'] if 'postal' in location else None
    
    return ' '.join(['' if i is None else i for i in [venue, address, locality, region, postal_code]])
