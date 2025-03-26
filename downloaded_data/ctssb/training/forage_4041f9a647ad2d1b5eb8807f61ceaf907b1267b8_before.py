# Create your views here.
from django.http import HttpResponse
import math
from models import *
from django.shortcuts import render_to_response
from django.template.context import RequestContext
from urllib2 import urlopen
from constants import *
import json

def merge_restaurants(request):
    g_places = GPlace.objects.all()
    yelps = Yelp.objects.all()
    restaurants = []
    for g in g_places:
        r = {
            'place_id': g.place_id,
            'name': g.name,
            'address': g.address,
            'latitude': g.latitude,
            'longitude': g.longitude,
            'goog_rating': g.average_rating,
            'hours': g.hours,
            'price': g.price,
            'yelp_rating': 0,
            'num_yelp_ratings': 0,
            '_id': g.address.lower()
        }
        restaurants.append(r)
    for y in yelps:
        r = {
            'name': y.name,
            'address': y.address,
            'genre': y.genre,
            'latitude': y.latitude,
            'longitude': y.longitude,
            'yelp_rating': y.average_rating,
            'num_yelp_ratings': y.num_ratings,
            'hours': y.hours,
            'goog_rating': 0,
            'price': -1,
            'place_id': 0,
            '_id': y.address.lower()
        }
        is_dup = False
        for g in restaurants:
            if g['_id'] == r['_id']:
                is_dup = True
                g['genre'] = r['genre']
                g['yelp_rating'] = r['yelp_rating']
                g['num_yelp_ratings'] = r['num_yelp_ratings']
        if not is_dup:
            restaurants.append(r)

    for r in restaurants:
        r.pop("_id", None)
        r = Restaurant2(**r)
        r.save()


    return render_to_response('test.html', {'message' : 'finished merging'}, context_instance=RequestContext(request))


def scrape_grid_page(request):
    scrape_grid()

    return render_to_response('test.html', {'message' : 'finished scraping grid'}, context_instance=RequestContext(request))

def scrape_grid():
    ywsid = 'nc5nvTckUyLncvvm9Qd8ew'

    tl_lat = 37.433711
    tl_long = -122.110664
    br_lat = tl_lat - 0.001
    br_long = tl_long - 0.001

    #37.357442
    while tl_lat >= 37.357442:
        req = 'http://api.yelp.com/business_review_search?term=food&tl_lat=%s&tl_long=%s&br_lat=%s&br_long=%s&limit=20&ywsid=%s' % (tl_lat, tl_long, br_lat, br_long, ywsid)
        scrape_yelp_data(req)
        tl_lat -= .001
        tl_long += .001
        br_lat = tl_lat - 0.001
        br_long = tl_long - 0.001


def get_loc(address):
    address = address.replace(' ', '+')
    print address
    try:
        loc_req = 'https://maps.googleapis.com/maps/api/geocode/json?address=%s' % (address)
        jsonurl = urlopen(loc_req)
        data = json.loads(jsonurl.read())
        loc = data['results'][0]['geometry']['location']
        return loc['lat'], loc['lng']
    except Exception, e:
        print str(e)
        return 0,0

def get_genre(b, food_cats):
    categories = b['categories']
    for c in categories:
        print c
        if c['category_filter'] in food_cats:
            return c['name']
    return None


def scrape_yelp_data(req):

    jsonurl = urlopen(req)
    data = json.loads(jsonurl.read())
    print data

    food_cats = get_food_cats()

    for b in data['businesses']:
        name = b['name']

        address = ','.join(filter(lambda x : len(x) > 0 , [b['address1'], b['address2'], b['address3'], b['city']]))

        #skip if no address or if the address already exists
        if len(b['address1']) == 0 : continue
        if Yelp.objects.filter(address= address).exists(): continue

        genre = get_genre(b, food_cats)
        if genre is None: continue

        lat, long = get_loc(address)
        average_rating = b['avg_rating']
        num_ratings = b['review_count']
        r = Yelp(name= name, address= address, average_rating = average_rating,
                   num_ratings = num_ratings,genre = genre, hours = '', latitude = lat, longitude = long)
        print name, genre
        r.save()

def scrape(request):
    lat = 37.423418
    long = -122.071638

    ywsid = 'nc5nvTckUyLncvvm9Qd8ew'
    yelp_req = 'http://api.yelp.com/business_review_search?term=food&lat=%s&long=%s&radius=10&limit=20&ywsid=%s' % (lat, long, ywsid)
    scrape_yelp_data(yelp_req)

    text = 'scraped'

    return render_to_response('test.html', {'message' : text}, context_instance=RequestContext(request))

def get_details(place_id):
    places_api_key = 'AIzaSyCtQScpB0zS0M4cUfp_Q9g2OrUZaXn8soY'
    details_req = 'https://maps.googleapis.com/maps/api/place/details/json?key=%s&placeid=%s' % (places_api_key, place_id)
    jsonurl = urlopen(details_req)
    data = json.loads(jsonurl.read())['result']
    print data

    if 'price_level' in data:
        price = int(data['price_level'])
    else: price = 99
    if price <= 2:
        persist_google_entity(place_id, data)

def persist_google_entity(place_id, data):
    name = data['name']
    address = data['vicinity']
    latLong = data['geometry']['location']
    latitude = latLong['lat']
    longitude = latLong['lng']
    rating = data['rating']
    price = data['price_level']

    if not GPlace.objects.filter(place_id = place_id).exists():
        r = GPlace(place_id = place_id, name = name, address = address, latitude = latitude, longitude = longitude,
                    average_rating = rating, hours = '', price = price)
        r.save()


def locate(request):
    # Turn the request into a lat and long
    # Fetch all restaurants from the database
    # Go through all of the restaurants and find the closest ones
    # Return those as JSON

    lat = float(request.GET['lat'])
    lng = float(request.GET['lon'])
    restaurants = get_restaurants(lat, lng)

    response_data = []

    for restaurant in restaurants:
        response_data.append({'name' : restaurant.name, 'genre' : restaurant.genre,
                      'latitude' : restaurant.latitude, 'longitude' : restaurant.longitude,
                      'address' : restaurant.address})

    return HttpResponse(json.dumps(response_data), content_type="application/json")

# returns the ten closest restaurants to (latitude, longitude)
def get_restaurants(latitude, longitude):
    restaurants = Restaurant2.objects.all()

    def get_average_rating(restaurant):
        if restaurant.yelp_rating != 0 and restaurant.goog_rating != 0:
            return (restaurant.yelp_rating + restaurant.goog_rating)/2.0

        if restaurant.yelp_rating != 0:
            return restaurant.yelp_rating

        return restaurant.goog_rating

    def calculate_score(restaurant):
        rst_lat = restaurant.latitude
        rst_long = restaurant.longitude
        distance = math.hypot(latitude - rst_lat, longitude - rst_long) # pythagorean theorem
        rating = getAverageRating(restaurant)
        score = distance*10000 + rating
        return [score, restaurant]

    restaurantsWithDistance = [calculate_score(r) for r in restaurants]
    restaurantsWithDistance = sorted(restaurantsWithDistance, key = lambda x : x[0])
    return [r[1] for r in restaurantsWithDistance[:10]]

def crawl_grid(lat, lng, lat_final, lng_final, placeIds):
    increment = 0.005
    key = 'AIzaSyCtQScpB0zS0M4cUfp_Q9g2OrUZaXn8soY'
    while lat >= lat_final:
        while lng <= lng_final:
            try:
                place_search_req = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=%s,%s&radius=500&types=food&key=%s' % (lat, lng, key)
                jsonurl = urlopen(place_search_req)
                data = json.loads(jsonurl.read())
                for result in data['results']:
                    placeId = result['place_id']
                    if not placeId in placeIds:
                        placeIds.append(placeId)
            except Exception, e:
                print str(e)
            finally:
                lng += increment

        lat -= increment
    return placeIds

def scrape_google(request):
    key = 'AIzaSyCtQScpB0zS0M4cUfp_Q9g2OrUZaXn8soY'
    lat = 37.433711
    lat_final = 37.357442
    lng = -122.110664
    lng_final = -122.058908

    placeIds = []
    placeIds = crawl_grid(lat, lng, lat_final, lng_final, placeIds)

    lat = 37.468186
    lat_final = 37.327038
    lng = -122.182154
    lng_final = -121.952471
    placeIds = crawl_grid(lat, lng, lat_final, lng_final, placeIds)

    # Finish with a final sweep from our location
    my_lat = 37.423418
    my_lng = -122.071638
    place_search_req = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=%s,%s&radius=50000&types=food&key=%s' % (my_lat, my_lng, key)
    try:
        jsonurl = urlopen(place_search_req)
        data = json.loads(jsonurl.read())
        for result in data['results']:
            placeId = result['place_id']
            if not placeId in placeIds:
                placeIds.append(placeId)
    except Exception, e:
        print str(e)
    for _id in placeIds:
        get_details(_id)

    return render_to_response('test.html', {'message' : 'finished scraping google'}, context_instance=RequestContext(request))

