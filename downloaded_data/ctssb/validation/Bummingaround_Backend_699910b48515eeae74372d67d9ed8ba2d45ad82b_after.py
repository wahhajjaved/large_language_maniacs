from rdflib import RDF, Literal
from find_places import spqrql
from find_places.graphdb import NAMESPACES, GraphDB, GRAPHDB_LINKEDGEODATA_URL, define_namespaces
from find_places.reverse_geocoding import get_address

__author__ = 'matteo'

LGDO = NAMESPACES['lgdo']
GEO = NAMESPACES['geo']


def download_per_point_lgd(lat, lon, radius):
    linked_geo_data_db = GraphDB(GRAPHDB_LINKEDGEODATA_URL)
    query = spqrql.create_geodata_query(lat, lon, radius)

    g = linked_geo_data_db.query(query).get_graph()

    define_namespaces(g)

    for venue in g.subjects(RDF.type, LGDO.Amenity):
        street = g.value(venue, LGDO['addr%3Astreet'])
        house_number = g.value(venue, LGDO['addr%3Ahousenumber'])
        if (street is not None) and (house_number is not None):
            address = "{} {}".format(street, house_number)
        else:
            _lat = g.value(venue, GEO.lat)
            _lon = g.value(venue, GEO.long)
            address = get_address(_lat, _lon)

        if address is not None:
            g.add((venue, NAMESPACES['iwa'].address, Literal(address)))

    ttl = g.serialize(format="turtle")

    db = GraphDB()
    db.add_turtle(ttl)

    return g
