import datetime
from typing import Sequence

from api.data import Station, JourneyTime
from api.lib.functional import curried
from api.lib.utils import filter_, map_
from api.services.journey_time import update_journey_time


def _update(all_stations: Sequence[Station], destination: Station):
    print("Updating " + destination.name)
    origins = filter_(lambda s: s.sid != destination.sid, all_stations)
    times = map_(_update_origin(destination), origins)
    print(str(len(times)) + " times inserted")

    if len(times) > 0:
        destination.journey_times_updated = datetime.datetime.now()
        destination.save()


@curried
def _update_origin(destination: Station, origin: Station) -> JourneyTime:
    print("Getting time for " + origin.name + " to " + destination.name)
    update = update_journey_time(destination, origin)
    if update.get_error():
        print("Error: " + update.get_error())

    return update.get_value()


stations_to_update = Station.select()\
    .where((Station.min_zone == 1) | (Station.max_zone == 1))\
    .order_by(Station.journey_times_updated)\
    .limit(3)

all_stations = Station.select().order_by(Station.name)

for terminal in stations_to_update: _update(all_stations, terminal)
