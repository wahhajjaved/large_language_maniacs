from shapely.geometry import Point

from point_on_earth import generate_land_coordinates, get_land_polygons


def test_point_on_land():
    coordinates = generate_land_coordinates()
    land = get_land_polygons()
    geo_point = Point(coordinates['latitude'], coordinates['longitude'])
    assert land.contains(geo_point)
