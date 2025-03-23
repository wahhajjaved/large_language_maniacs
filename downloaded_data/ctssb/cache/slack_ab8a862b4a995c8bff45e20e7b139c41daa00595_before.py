import sys
import datetime
from dateutil.tz import tzutc
from hypchat import HypChat
import time
import json
import re
import os
from collections import OrderedDict

secret_path = sys.argv[1]

with open(secret_path) as secretf:
    token = secretf.read().rstrip()

CUTOFF_DATE = datetime.datetime(2016,6,1,tzinfo=tzutc())

hc = HypChat(token)


def get_active_rooms():
    rooms = hc.rooms()
    active_rooms = []
    for room in rooms['items']:
        if room['is_archived'] or re.search("Bot:|Meetings ::", room['name']):
            print("skipping " + room['name'])
            continue
        time.sleep(2)  # API rate limiting
        active_room = hc.get_room(room['id'])
        if active_room['last_active'] and active_room['last_active'] > CUTOFF_DATE:
            print("appending room: " + active_room['name'])
            active_rooms.append(active_room)
    return active_rooms


def dump(filename, items):
    json_friendly = []
    for item in items:
        item = dict(item.items())
        item['created'] = item['created'].isoformat()
        item['last_active'] = item['last_active'].isoformat()
        json_friendly.append(item)

    with open(filename, "w+b") as output:
        output.write(json.dumps(json_friendly))
    return json_friendly


if not os.path.exists("output.json"):
    active_rooms = get_active_rooms()
    active_rooms = dump("output.json", active_rooms)
else:
    active_rooms = json.loads(open("output.json").read())


mappings = []
with open("mappings.txt") as mappingf:
    for line in mappingf:
        line = line.rstrip()
        comment_idx = re.search(" *#", line)
        if comment_idx:
            line = line[0:comment_idx.start()]
        if line:
            (slack, hipchat) = line.split(" -> ")
            mappings.append((hipchat, slack))

mappings = dict(mappings)

conversions = OrderedDict([(i['name'],
                            dict(owner=i['owner'],
                                 last_active=i['last_active'],
                                 slack_room=mappings.get(i['name'],"")))
                           for i in active_rooms])

for name, room in sorted(conversions.items()):
    slack = room.get("slack_room", "")
    last_active = last_active=room['last_active'][:-6]
    owner = room['owner']['mention_name']
    print("{name:<42} {slack:<21} {owner:<32} {last_active}".format(**locals()))
