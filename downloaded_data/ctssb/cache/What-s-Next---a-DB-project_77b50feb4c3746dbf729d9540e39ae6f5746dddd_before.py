from db_utils import init_db_connection, init_db_cursor,execute_SFW_query,execute_writing_query
from whatsnext.models import Review, Place
from exceptions import NotFoundInDb
import MySQLdb as mdb
from taudb.settings import RESOLUTION,LONDON_LATITUDE_DB_CONST

DEFAULT_RESULTS_AMOUNT = 10


def get_place_by_place_id(place_id):
    if not place_id:
        raise ValueError('id argument must be not None')

    cur = init_db_cursor()

    query = 'SELECT                                                         '\
            '   places.id,                                                  '\
            '   places.google_id,                                           '\
            '   places.name,                                                '\
            '   places.rating,                                              '\
            '   places.vicinity,                                            '\
            '   places.latitude,                                            '\
            '   places.longitude,                                           '\
            '   categories.name AS category                                 '\
            'FROM                                                           '\
            '   places                                                      '\
            '       INNER JOIN                                              '\
            '   places_categories ON places.id = places_categories.place_id '\
            '       INNER JOIN                                              '\
            '   categories ON places_categories.category_id = categories.id '\
            'WHERE                                                          '\
            '   places.id = %s                                              '

    cur.execute(query, (place_id,))

    record = cur.fetchone()  # expecting single place since id is a pk
    if record:
        place = record
    else:
        raise NotFoundInDb('db does not include a record with id: {id}'.format(id=id))

    cur.close()

    return place


def find_suggestion_near_location(center_latitude, center_longitude, offset_for_paging):

    cur = init_db_cursor()
    query = 'Select 	                                                                                            ' \
            '   hotels.id As hid, hotels.google_id As hgid, hotels.name As hn, hotels.rating As hr,                 ' \
            '   hotels.vicinity As hv, hotels.latitude As h_lat, hotels.longitude As h_lon,                         ' \
            '   rid, rgid, rn, rr, rv, r_lat, r_lon,                                                                ' \
            '   bid, bgid, bn, br, bv, b_lat, b_lon,                                                                ' \
            '   muid, mdig, mn, mr, mv,	m_lat, m_lon,                                                               ' \
            '   (sqrt((m_lat - %s)^2 / 100 + (m_lon - %s)^2 / 100) +                                                ' \
            '   sqrt((b_lat - m_lat)^2 / 100 + (b_lon - m_lon)^2 / 100) +                                           ' \
            '   sqrt((r_lat - b_lat)^2 / 100 + (r_lon - b_lon)^2 / 100) +                                           ' \
            '   sqrt((hotels.latitude - r_lat)^2 / 100 + (hotels.longitude - r_lon)^2 / 100))                       ' \
            '   As TotalDistAfterTransp                                                                             ' \
            'From                                                                                                   ' \
            '	places as hotels,                                                                                   ' \
            '	places_categories as pc_hotels,                                                                     ' \
            '	(Select                                                                                             ' \
            '		restaurants.id As rid, restaurants.google_id As rgid, restaurants.name As rn,                   ' \
            '       restaurants.rating As rr, restaurants.vicinity As rv, restaurants.latitude As r_lat,            ' \
            '       restaurants.longitude As r_lon,bid, bgid, bn, br, bv, b_lat, b_lon,                             ' \
            '       muid, mdig, mn, mr, mv,	m_lat, m_lon                                                            ' \
            '		From                                                                                            ' \
            '		places as restaurants,                                                                          ' \
            '		places_categories as pc_restaurants,                                                            ' \
            '		(Select                                                                                         ' \
            '			bars.id As bid, bars.google_id As bgid, bars.name As bn, bars.rating As br,                 ' \
            '           bars.vicinity As bv, bars.latitude As b_lat, bars.longitude As b_lon,                       ' \
            '           muid, mdig, mn, mr, mv,	m_lat, m_lon                                                        ' \
            '		From                                                                                            ' \
            '			places as bars,                                                                             ' \
            '			places_categories as pc_bars,                                                               ' \
            '			(Select                                                                                     ' \
            '				museums.id As muid, museums.google_id As mdig, museums.name as mn,                      ' \
            '               museums.rating as mr, museums.vicinity as mv,museums.latitude As m_lat,                 ' \
            '               museums.longitude As m_lon                                                              ' \
            '				From                                                                                    ' \
            '					places as museums,                                                                  ' \
            '					places_categories as pc_museums	                                                    ' \
            '			    Where                                                                                   ' \
            '					museums.id = pc_museums.place_id                                                    ' \
            '					And pc_museums.category_id = 4                                                      ' \
            '                   And museums.latitude BETWEEN %s - 100 AND %s + 100                                  ' \
            '                   And museums.longitude BETWEEN %s - 50 AND %s + 50 ) As museums                      ' \
            '		Where                                                                                           ' \
            '			bars.id = pc_bars.place_id                                                                  ' \
            '			And pc_bars.category_id = 3 And bars.latitude BETWEEN m_lat - 10 AND m_lat + 10             ' \
            '           And bars.longitude BETWEEN m_lon - 10 AND m_lat + 10 And bars.id <> muid ) As bars          ' \
            '	Where                                                                                               ' \
            '		restaurants.id = pc_restaurants.place_id                                                        ' \
            '		And pc_restaurants.category_id = 2                                                              ' \
            '       And restaurants.latitude BETWEEN b_lat - 10 AND b_lat + 10                                      ' \
            '       AND restaurants.longitude BETWEEN b_lon - 10 AND b_lat + 10                                     ' \
            '       And restaurants.id <> bid                                                                       ' \
            '       AND restaurants.id <> muid ) As restaurants                                                     ' \
            'Where                                                                                                  ' \
            '	hotels.id = pc_hotels.place_id                                                                      ' \
            '	And pc_hotels.category_id = 1                                                                       ' \
            '   And hotels.latitude BETWEEN r_lat - 10 AND r_lat + 10                                               ' \
            '   AND hotels.longitude BETWEEN r_lon - 10 AND r_lat + 10                                              ' \
            '   And hotels.id <> rid                                                                                ' \
            '   And hotels.id <> bid                                                                                ' \
            '   And hotels.id <> muid                                                                               ' \
            'Order By                                                                                               ' \
            '	TotalDistAfterTransp                                                                                ' \
            'Limit                                                                                                  ' \
            '   %s, %s'

    cur.execute(query, (center_longitude, center_longitude, center_latitude,
                        center_latitude, center_longitude, center_longitude,
                        offset_for_paging * DEFAULT_RESULTS_AMOUNT, DEFAULT_RESULTS_AMOUNT))
    rows = cur.fetchall()

    places = dict()
    i = 0
    for result in rows:
        hotel = dict()
        restaurant = dict()
        bar = dict()
        museum = dict()

        hotel["id"] = result["hid"]
        hotel["google_id"] = result["hgid"]
        hotel["name"] = result["hn"]
        hotel["rating"] = result["hr"]
        hotel["vicinity"] = result["hv"]
        hotel["latitude"] = (result["h_lat"] / RESOLUTION) + LONDON_LATITUDE_DB_CONST
        hotel["longitude"] = result["h_lon"] / RESOLUTION
        hotel["category"] = 'hotel'

        restaurant["id"] = result["rid"]
        restaurant["google_id"] = result["rgid"]
        restaurant["name"] = result["rn"]
        restaurant["rating"] = result["rr"]
        restaurant["vicinity"] = result["rv"]
        restaurant["latitude"] = (result["r_lat"] / RESOLUTION) + LONDON_LATITUDE_DB_CONST
        restaurant["longitude"] = result["r_lon"] / RESOLUTION
        restaurant["category"] = 'restaurant'

        bar["id"] = result["bid"]
        bar["google_id"] = result["bgid"]
        bar["name"] = result["bn"]
        bar["rating"] = result["br"]
        bar["vicinity"] = result["bv"]
        bar["latitude"] = (result["b_lat"] / RESOLUTION) + LONDON_LATITUDE_DB_CONST
        bar["longitude"] = result["b_lon"] / RESOLUTION
        bar["category"] = 'bar'

        museum["id"] = result["muid"]
        museum["google_id"] = result["mdig"]
        museum["name"] = result["mn"]
        museum["rating"] = result["mr"]
        museum["vicinity"] = result["mv"]
        museum["latitude"] = (result["m_lat"] / RESOLUTION) + LONDON_LATITUDE_DB_CONST
        museum["longitude"] = result["m_lon"] / RESOLUTION
        museum["category"] = 'museum'

        places[i] = [hotel, restaurant, bar, museum]
        i = i+1

    cur.close()

    return places


def search_places_near_location(center_latitude, center_longitude, top, right, bottom, left, category, limit):

    cur = init_db_cursor()

    query = 'SELECT                                                                    '\
            '    places.id,                                                            '\
            '    places.google_id,                                                     '\
            '    places.name,                                                          '\
            '    places.longitude,                                                     '\
            '    places.latitude,                                                      '\
            '    places.rating,                                                        '\
            '    places.vicinity,                                                      '\
            '    categories.name AS category,                                          '\
            '    (POWER((latitude - %s) , 2) + POWER((longitude - %s), 2)) AS distance '\
            'FROM                                                                      '\
            '    places                                                                '\
            '        JOIN                                                              '\
            '    places_categories ON places.id = places_categories.place_id           '\
            '        JOIN                                                              '\
            '    categories ON places_categories.category_id = categories.id           '\
            'WHERE                                                                     '\
            '    categories.name = %s                                                  '\
            '    AND latitude BETWEEN %s AND %s                                        '\
            '    AND longitude BETWEEN %s AND %s                                       '\
            'ORDER BY distance ASC                                                     '\
            'LIMIT %s                                                                  '

    # TODO: why do we have a limit set from the client? why do we have a limit at all?
    # TODO: this could easily become a more complicated query and be part of the required 6 (it's currently not!)
    cur.execute(query, (center_latitude, center_longitude, category, bottom, top, left, right, limit))
    rows = cur.fetchall()

    places = dict()
    for result in rows:
        place = query_results_to_dict(result)
        places[place["id"]] = place

    cur.close()

    return places


def query_results_to_dict(result):
    place = dict()
    place["id"] = result["id"]
    place["google_id"] = result["google_id"]
    place["name"] = result["name"]
    place["longitude"] = result["longitude"] / RESOLUTION
    place["latitude"] = (result["latitude"] / RESOLUTION) + LONDON_LATITUDE_DB_CONST
    place["rating"] = result["rating"]
    place["vicinity"] = result["vicinity"]
    place["category"] = result["category"]
    return place


def search_places_by_name(search_word, search_category, offset_for_paging):

    cur = init_db_cursor()

    # search by the word and the category
    # Query is divided into a subquery using match-against due to differences in DB engine,
    # which if put together into one queries causes a major slow-down.
    query = 'SELECT                                                                            ' \
            '    full_text_results.id,                                                         ' \
            '    full_text_results.google_id,                                                  ' \
            '    full_text_results.name,                                                       ' \
            '    full_text_results.rating,                                                     ' \
            '    full_text_results.vicinity,                                                   ' \
            '    full_text_results.latitude,                                                   ' \
            '    full_text_results.longitude,                                                  ' \
            '    categories.name AS category                                                   ' \
            'FROM                                                                              ' \
            '    (SELECT                                                                       ' \
            '        places.id,                                                                ' \
            '        places.google_id,                                                         ' \
            '        places.rating,                                                            ' \
            '        places.vicinity,                                                          ' \
            '        places.name,                                                              ' \
            '        places.latitude,                                                          ' \
            '        places.longitude                                                          ' \
            '    FROM                                                                          ' \
            '        places                                                                    ' \
            '    WHERE                                                                         ' \
            '        MATCH (places.name) AGAINST ("+%s" IN BOOLEAN MODE)) AS full_text_results ' \
            '        INNER JOIN                                                                ' \
            '    places_categories ON full_text_results.id = places_categories.place_id        ' \
            '        INNER JOIN                                                                ' \
            '    categories ON categories.id = places_categories.category_id                   ' \
            'WHERE                                                                             ' \
            '    categories.name = %s                                                          ' \
            'LIMIT %s, %s                                                                      '

    cur.execute(query, (search_word, search_category,
                        offset_for_paging * DEFAULT_RESULTS_AMOUNT, DEFAULT_RESULTS_AMOUNT))

    rows = cur.fetchall()

    print "fullTextSearch returning " + str(len(rows)) + " results"

    places = dict()
    for result in rows:
        place = query_results_to_dict(result)
        places[place["id"]] = place

    return places


def get_place_reviews(place):
    if not place:
        raise ValueError('place argument must be not None')

    cur = init_db_cursor()

    query = 'SELECT                      '\
            '   reviews.id as review_id, '\
            '   reviews.place_id,        '\
            '   reviews.author,          '\
            '   reviews.rating,          '\
            '   reviews.text,            '\
            '   reviews.date             '\
            'FROM                        '\
            '   reviews                  '\
            'WHERE                       '\
            '   reviews.place_id = %s    '

    # cur.execute(query, (place.place_id,)) TODO: this does not use the Place class anymore, need to fix this
    cur.execute(query, (place['id'],))

    records = cur.fetchall()

    reviews = list()
    for record in records:
        review = Review(**record)
        reviews.append(review)

    cur.close()

    return reviews


def insert_new_reviews(reviews):
    if not reviews:
        raise ValueError('reviews argument must be not None')

    # convert the reviews list to a list of tuples, so it can be used in the query execution
    reviews_tuples_list = list()
    for review in reviews:
        reviews_tuples_list.append((review.place_id, review.author, review.rating, review.text, review.date))

    # TODO: should use an object to obtain the connection and cursor
    conn = init_db_connection()
    cur = conn.cursor(mdb.cursors.DictCursor)

    query = 'INSERT INTO reviews (`place_id`, `author`, `rating`, `text`, `date`) '\
            'VALUES (%s, %s, %s, %s, %s)                                          '

    # TODO: check what happens if review.date is None
    cur.executemany(query, reviews_tuples_list)

    conn.commit()

    cur.close()


def update_place_rating(new_rating, place_id):
    if not new_rating or not place_id:
        raise ValueError('all arguments must be not None')

    # TODO: should use an object to obtain the connection and cursor
    conn = init_db_connection()
    cur = conn.cursor(mdb.cursors.DictCursor)

    query = 'UPDATE places   '\
            'SET             '\
            '    rating = %s '\
            'WHERE           '\
            '    id = %s     '

    # TODO: check what happens if review.date is None
    cur.execute(query, (new_rating, place_id))

    conn.commit()

    cur.close()


def get_categories_statistics(top, right, bottom, left, except_category):
    if not top or not right or not bottom or not left:
        raise ValueError('location arguments must be not None')

    cur = init_db_cursor()

    query = 'SELECT                                                                ' \
            '    categories.name AS category_name,                                 ' \
            '    COUNT(places.id) AS places_amount,                                ' \
            '    ROUND(AVG(places_rated.rating), 2) AS rating_average              ' \
            'FROM                                                                  ' \
            '    places                                                            ' \
            '        JOIN                                                          ' \
            '    places_categories ON places.id = places_categories.place_id       ' \
            '        JOIN                                                          ' \
            '    categories ON places_categories.category_id = categories.id       ' \
            '        JOIN                                                          ' \
            '    (SELECT                                                           ' \
            '        places.id, places.rating                                      ' \
            '    FROM                                                              ' \
            '        places                                                        ' \
            '    WHERE                                                             ' \
            '        rating > 0) AS places_rated ON places.id = places_rated.id    ' \
            'WHERE                                                                 ' \
            '   latitude BETWEEN %s AND %s                                         ' \
            '        AND longitude BETWEEN %s AND %s                               ' \
            'GROUP BY categories.name                                              ' \
            'HAVING places_amount > 0 AND categories.name != %s                    '

    cur.execute(query, (bottom, top, left, right, except_category))

    records = cur.fetchall()

    statistics = dict()
    for record in records:
        category_name = record['category_name'].capitalize()
        places_amount = record['places_amount']
        rating_average = record['rating_average']

        statistics[category_name] = {'places_amount': places_amount, 'rating_average': rating_average}

    cur.close()

    return statistics


def get_popular_places_for_category(category):
    if not category:
        raise ValueError('category arguments must be not None')

    cur = init_db_cursor()

    # TODO: this should not be limited like this - need to decide on the requirement
    # TODO: current popularity is just the amount of times the place was chosen as a group of places
    query = 'SELECT                                                                           '\
            '    places.id, places.name, SUM(search_popularity.popularity) AS popularity      '\
            'FROM                                                                             '\
            '    places                                                                       '\
            '        INNER JOIN                                                               '\
            '    searches_places ON places.id = searches_places.place_id                      '\
            '        INNER JOIN                                                               '\
            '    search_popularity ON searches_places.search_id = search_popularity.search_id '\
            '        INNER JOIN                                                               '\
            '    places_categories on places.id = places_categories.place_id                  '\
            '        INNER JOIN                                                               '\
            '    categories on places_categories.category_id = categories.id                  '\
            'WHERE                                                                            '\
            '    categories.name = %s                                                         '\
            'GROUP BY places.id, places.name                                                  '\
            'ORDER BY popularity DESC                                                         '\
            'LIMIT 5                                                                          '

    cur.execute(query, (category,))

    records = cur.fetchall()

    top_places = dict()
    for record in records:
        place_id = record['id']
        place_name = record['name']
        popularity = record['popularity']

        top_places[place_id] = {'place_id': place_id, 'place_name': place_name, 'popularity': popularity}

    cur.close()

    return top_places



# TODO: there should be a text box who autocomplete whenever the user starts a search
# TODO: create an sql query to search if that search exists
def find_popular_search(places_id_list):
    search_id = find_search_id_query(places_id_list)
    find_popular_query = "SELECT sp.popularity FROM ("+ search_id+ ") AS S_ID, search_popularity AS sp " \
                          "WHERE S_ID.search_id = sp.search_id"
    popularity_rate = execute_SFW_query(find_popular_query)
    return popularity_rate


def exe_find_search_id_query(places_id_list):
    return execute_SFW_query(find_search_id_query(places_id_list))

# this function returns a string that determains which search_id will return.
# it is vital it returns a string and not execute anything.
def find_search_id_query(places_id_list):
    query = "SELECT DISTINCT sp.search_id " \
            "FROM (SELECT sp0.search_id " \
                   "FROM searches_places AS sp0 "
    places_str,inner_join = "",""
    for i in range(len(places_id_list)):
        #this is ake sure we add the exact ammount of inner join needed.
        if (i != len(places_id_list)-1):
            inner_join += "INNER JOIN searches_places AS sp"+str(i+1)+" "
        places_str  +="sp"+str(i)+".place_id = " + str(places_id_list[i]) + " AND "
    places_str =inner_join + "WHERE " + places_str[:-5] #remove the last " ADD "
    query += places_str +" ) AS possible_searches INNER JOIN search_properties AS sp " \
                         "ON possible_searches.search_id = sp.search_id " \
                         "WHERE sp.search_size = "+str(len(places_id_list))
    return query

'''
example for find_search_query_id_result:
    SELECT DISTINCT sp.search_id
    FROM   (SELECT sp0.search_id
            FROM searches_places AS sp1
            INNER JOIN searches_places AS sp1
            INNER JOIN searches_places AS sp2
            WHERE sp0.place_id = 1 AND sp2.place_id = 2 AND sp3.place_id = 3
            ) as possible_searches INNER JOIN search_properties AS sp
            ON possible_searches.search_id = sp.search_id
    WHERE sp.search_size = 3
'''


def insert_new_search(places_id_list):
    execute_writing_query("INSERT INTO search_properties(popularity,search_size) VALUES (1," +str(len(places_id_list))+")") #creates new popularity
    search_id = execute_SFW_query("SELECT MAX(search_id) AS search_id FROM search_properties") #returns the new popularity id
    #return search_id
    insert_to_searches_places = "INSERT INTO searches_places VALUES "
    for i in range(len(places_id_list)):
        insert_to_searches_places += "(" + str(search_id[0]['search_id']) + "," + str(places_id_list[i]) + "), "
    execute_writing_query(insert_to_searches_places[:-2]) #insert this popularity into searches_places


def update_search(search_id):
    execute_writing_query("UPDATE search_properties SET popularity = popularity+1 WHERE search_id = " + str(search_id[0]["search_id"]))
