import config
from datetime import datetime
import MySQLdb
import re
import traceback


_connected = False
_database = None
_cursor = None

# setupConnection() must be called before anything else for this to work
# closeConnection() should be called after finishing


def setupConnection():
    global _connected
    global _database
    global _cursor

    if not _connected:
        try:
            _database = MySQLdb.connect(host="localhost",
                                        user="root",
                                        passwd=config.password,
                                        db="gttravel")
            _cursor = _database.cursor()
            _connected = True
        except Exception as e:
            _connected = False
            traceback.print_exc()


def closeConnection():
    global _connected

    if _connected:
        _database.close()
        _connected = False


# returns 1 if username is taken
# returns 2 if email is taken
# returns 0 if insert was valid
# returns 3 if everything is screwed
def register(username, email, password, ismanager):
    query = "INSERT INTO users(Username, Email, Password, Is_manager)"\
            "VALUES (%s, %s, %s, %s);"
    try:
        response = _cursor.execute(query, (username, email, password, ismanager))
        _database.commit()

        return 0
    except Exception as e:
        if e[1][-2:] == 'Y\'':  # violates primary key constraint, username
            return 1
        elif e[1][-2:] == 'l\'':  # violates email uniqueness constraint
            return 2
        else:  # don't get here
            return 3


# returns 0 if credentials are invalid
# returns 1 if user is a manager
# returns 2 if user is NOT a manager
def login(username, password):
    query = "SELECT * FROM users WHERE Username = %s AND Password = %s;"
    response = _cursor.execute(query, (username, password))

    # clear cursor
    _cursor.fetchall()

    if response == 0:
        return 0
    else:
        query = "SELECT Is_manager FROM users WHERE Username = %s;"
        response = _cursor.execute(query, (username,))

        result = _cursor.fetchone()

        # sanity check
        _cursor.fetchall()

        if result[0] == 1:  # if Is_manager
            return 1
        else:
            return 2


# does not error handle lmao
def addCity(city, country, latitude, longitude, population, languages):
    query = 'INSERT INTO city(City, Country, latitude, longitude, population) VALUES (%s, %s, %s, %s, %s)'
    response = _cursor.execute(query, (city, country, latitude, longitude, population))

    query = 'INSERT INTO city_language(City, Country, Language) VALUES (%s, %s, %s)'
    for lang in languages:
        response = _cursor.execute(query, (city, country, lang))

    _database.commit()


def getCountries():
    _cursor.execute("SELECT Country FROM country;")
    my_list = tupleListToList(_cursor.fetchall())
    my_list.append("")
    return my_list


def getLanguages():
    _cursor.execute("SELECT Language FROM language;")
    my_list = tupleListToList(_cursor.fetchall())
    my_list.append("Any additional language")
    return my_list


def getLanguagesMgr():
    _cursor.execute("SELECT Language FROM language;")
    return tupleListToList(_cursor.fetchall())


def getCities():
    _cursor.execute("SELECT City FROM city;")
    my_list = tupleListToList(_cursor.fetchall())
    my_list.append("")
    return my_list


def getAddresses():
    _cursor.execute("SELECT Address, City, Country FROM location;")
    my_list = []
    for item in _cursor.fetchall():
        my_list.append(item[0] + ", " + item[1] + ", " + item[2])
    my_list.append("")
    return my_list


def getLocNames():
    _cursor.execute("SELECT Name FROM location;")
    my_list = tupleListToList(_cursor.fetchall())
    my_list.append("")
    return my_list


def getLocTypes():
    _cursor.execute("SELECT Type FROM location_types;")
    return tupleListToList(_cursor.fetchall())


def getEventCategories():
    _cursor.execute("SELECT Category FROM event_categories;")
    return tupleListToList(_cursor.fetchall())


def getReviewableTypes():
    my_list = getCities() + getAddresses() + getEvents()
    my_list.remove("")
    my_list.remove("")
    return my_list


def timedeltaToDateTime(timdel):
    return str((datetime.min + timdel).time())


def getEvents():
    _cursor.execute("SELECT Name, Date, Start_time, Address, City, Country FROM event;")
    my_list = []
    for item in _cursor.fetchall():
        string = item[0] + ", " + item[3] + ", " + item[4] + ", " + item[5] + ", "
        string += str(item[1]) + ", " + timedeltaToDateTime(item[2])
        my_list.append(string)
    my_list.append("")
    return my_list


def tupleListToList(tuplelist):
    my_list = []
    for item in tuplelist:
        my_list.append(item[0])
    return my_list


# returns list in format [reviewed_item, review_date, score, text]
def pastReviews(username):
    reviews = []  # to return

    # city reviews!
    query = 'SELECT * FROM city_review WHERE Username = %s'
    response = _cursor.execute(query, (username,))
    for row in _cursor.fetchall():
        list1 = []
        list1.append(', '.join([row[1], row[2]]))
        for item in row[3:]:
            list1.append(str(item))
        reviews.append(list1)

    # location reviews
    query = 'SELECT * FROM location_review WHERE Username = %s'
    response = _cursor.execute(query, (username,))
    for row in _cursor.fetchall():
        list1 = []
        list1.append(', '.join([row[1], row[2], row[3]]))
        for item in row[4:]:
            list1.append(str(item))
        reviews.append(list1)

    # event reviews
    query = 'SELECT * FROM event_review WHERE Username = %s'
    response = _cursor.execute(query, (username,))
    for row in _cursor.fetchall():
        list1 = []
        list1.append(', '.join([row[1], row[4], row[5], row[6], str(row[2]), str(row[3])]))
        for item in row[7:]:
            list1.append(str(item))
        reviews.append(list1)

    return reviews


def writeReview(username, reviewableid, review_date, score, review):
    reviewableid = [x.strip() for x in reviewableid.split(',')]
    noFields = len(reviewableid)

    # city reviews
    if noFields == 1:
        query = 'INSERT INTO city_review (Username, City, Country, Date, Score, Description) VALUES (%s, %s, %s, %s, %s, %s);'
        _cursor.execute(query, (str(username), str(reviewableid[0]), str(getCityCountry(reviewableid[0])), str(review_date), str(score), str(review)))

    # location reviews
    elif noFields == 3:
        query = 'INSERT INTO location_review (Username, Address, City, Country, Date, Score, Description) VALUES (%s, %s, %s, %s, %s, %s, %s);'
        _cursor.execute(query, (username, reviewableid[0], reviewableid[1], reviewableid[2], review_date, score, review))

    # event reviews
    elif noFields > 3:
        query = 'INSERT INTO event_review (Username, Name, Date, Start_time, Address, City, Country, Review_date, Score, Review) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);'
        _cursor.execute(query, (username, reviewableid[0], reviewableid[4], reviewableid[5], reviewableid[1], reviewableid[2], reviewableid[3], review_date, score, review))

    _database.commit()
    return True


def updateReview(username, rid, review_date, score, description):
    rid = [x.strip() for x in rid.split(',')]
    rid_len = len(rid)

    if rid_len == 1:  # city reviews
        query = 'UPDATE city_review SET Score = %s, Description = %s WHERE Username = %s '
        query += 'AND City = %s AND Country = %s AND Date = %s;'
        _cursor.execute(query, (score, description, username, rid[0], getCityCountry(rid[0]), review_date))
    elif rid_len == 3:  # location reviews
        query = 'UPDATE location_review SET Score = %s, Description = %s WHERE Username = %s'
        query += ' AND Address = %s AND City = %s AND Country = %s AND Date = %s;'
        _cursor.execute(query, (score, description, username, rid[0], rid[1], rid[2], review_date))
    elif rid_len > 3:  # event reviews
        query = 'UPDATE event_review SET Score = %s, Review = %s WHERE '
        query += 'Username = %s AND Name = %s AND Date = %s AND Start_time = %s '
        query += 'AND Address = %s AND City = %s AND Country = %s AND Review_date = %s;'
        tup = (score, description, username, rid[0], rid[4], rid[5], rid[1], rid[2], rid[3], review_date)
        _cursor.execute(query, tup)

    _database.commit()
    return True


def aboutCountry(country):
    query = "SELECT * FROM country WHERE Country = %s;"
    response = _cursor.execute(query, (country,))
    fetch = _cursor.fetchone()

    result = {}
    result['name'] = fetch[0]
    result['population'] = fetch[1]
    result['capitals'] = getCapitals(country)
    result['languages'] = getLanguagesCountry(country)

    return result


def aboutCity(city):
    query = 'SELECT * FROM city WHERE City = %s;'
    response = _cursor.execute(query, (city,))

    item = _cursor.fetchone()
    result = {}
    result['name'] = item[0]
    result['country'] = item[1]
    result['gps'] = item[2] + ", " + item[3]
    result['population'] = item[4]
    result['languages'] = getLanguagesCity(city)
    result['score'] = getCityScore(city)
    return result


def aboutLocation(address):
    addressarr = [x.strip() for x in address.split(',')]
    query = "SELECT * FROM location WHERE Address = %s AND City = %s;"
    response = _cursor.execute(query, (addressarr[0], addressarr[1]))

    dicti = {}
    item = _cursor.fetchone()
    dicti['name'] = item[6]
    dicti['address'] = item[0] + ", " + item[1] + ", " + item[2]
    dicti['cost'] = item[3]
    dicti['std_discount'] = item[5]
    dicti['category'] = item[4]
    dicti['score'] = getLocScore(item[0], item[1], item[2])

    return dicti


def aboutEvent(key):
    eventarr = [x.strip() for x in key.split(',')]
    query = "SELECT * FROM Event WHERE Name = %s AND Address = %s AND City = %s"
    query += " AND Country = %s AND Date = %s AND Start_time = %s;"

    response = _cursor.execute(query, tuple(eventarr))
    item = _cursor.fetchone()
    dicti = {}
    dicti['name'] = item[0]
    dicti['date'] = str(item[1])
    dicti['starttime'] = str(item[2])
    dicti['location'] = item[3] + ", " + item[4] + ", " + item[5]
    dicti['endtime'] = str(item[9])
    dicti['cost'] = item[10]
    dicti['std_discount'] = "Yes" if item[8] else "No"
    dicti['category'] = item[6]
    dicti['score'] = getEventScore(item[0], item[1], item[2], item[3], item[4])

    return dicti


def getEventReviews(key):
    eventarr = [x.strip() for x in key.split(',')]
    query = "SELECT * FROM event_review WHERE Name = %s AND Address = %s AND City = %s"
    query += " AND Country = %s AND Date = %s AND Start_time = %s;"
    response = _cursor.execute(query, eventarr)

    result = []
    for item in _cursor.fetchall():
        dicti = {}
        dicti['username'] = item[0]
        dicti['date'] = item[7]
        dicti['score'] = item[8]
        dicti['description'] = item[9]
        result.append(dicti)
    return result


def getLocationEvents(address):
    addressarr = [x.strip() for x in address.split(',')]
    query = "SELECT * FROM event WHERE Address = %s AND City = %s;"
    response = _cursor.execute(query, (addressarr[0], addressarr[1]))

    result = []
    for item in _cursor.fetchall():
        dicti = {}
        dicti['event'] = item[0]
        dicti['date'] = item[1]
        dicti['time'] = item[2]
        dicti['category'] = item[6]
        dicti['score'] = getEventScore(item[0], item[1], item[2], item[3], item[4])
        result.append(dicti)
    return result


def getLocationReviews(address):
    addressarr = [x.strip() for x in address.split(',')]
    query = "SELECT * FROM location_review WHERE Address = %s AND City = %s;"
    response = _cursor.execute(query, (addressarr[0], addressarr[1]))

    result = []
    for item in _cursor.fetchall():
        dicti = {}
        dicti['username'] = item[0]
        dicti['date'] = item[4]
        dicti['score'] = item[5]
        dicti['description'] = item[6]
        result.append(dicti)
    return result


def getCityLocations(city):
    query = "SELECT * FROM location WHERE city = %s;"
    response = _cursor.execute(query, (city,))

    result = []
    for item in _cursor.fetchall():
        dicti = {}
        dicti['name'] = item[6]
        dicti['type'] = item[4]
        dicti['cost'] = item[3]
        dicti['score'] = getLocScore(item[0], item[1], item[2])
        result.append(dicti)
    return result


def getCityReviews(city):
    query = "SELECT * FROM city_review NATURAL JOIN city WHERE City = %s;"
    response = _cursor.execute(query, (city,))

    result = []
    for item in _cursor.fetchall():
        dicti = {}
        dicti['username'] = item[2]
        dicti['date'] = item[3]
        dicti['score'] = item[4]
        dicti['description'] = item[5]
        result.append(dicti)
    return result


def getCountryCities(country):
    query = "SELECT City, Population FROM city WHERE Country = %s;"
    response = _cursor.execute(query, (country,))

    result = []
    for item in _cursor.fetchall():
        dicti = {}
        dicti['city'] = item[0]
        dicti['population'] = item[1]
        dicti['languages'] = getLanguagesCity(item[0])
        dicti['score'] = getCityScore(item[0])
        result.append(dicti)
    return result


def countrySearch(country, population_min, population_max, lang_list, sort):
    population = population_max or population_min
    cri = False
    if lang_list and "Any additional language" in lang_list:
        cri = True
        lang_list.remove('Any additional language')

    if country:
        query = "SELECT * FROM country WHERE Country = %s;"
        response = _cursor.execute(query, (country,))
        fetch = _cursor.fetchone()
        result = {}
        result['name'] = fetch[0]
        result['population'] = fetch[1]

        result['capitals'] = getCapitals(country)
        result['languages'] = getLanguagesCountry(country)

        return [result]
    elif population and lang_list:
        languages = '\' OR Language = \''.join(lang_list)
        langquery = 'Language = \'' + languages + '\''
        innerquery = "(SELECT DISTINCT Country FROM country_language WHERE " + langquery + ") q "

        query = "SELECT * FROM " + innerquery + "NATURAL JOIN country"
        if cri:
            query += ") p"
            query = "SELECT * FROM multlangcountries NATURAL JOIN (" + query
        query += " WHERE "

        if population_min and population_max:
            query += "Population >= %s AND Population <= %s ORDER BY "

            if sort == "country":
                query += "Country;"
            else:
                query += "Population DESC;"

            response = _cursor.execute(query, (population_min, population_max))
        elif population_max:
            query = query + "Population <= %s ORDER BY "

            if sort == "country":
                query += "Country;"
            else:
                query += "Population DESC;"

            response = _cursor.execute(query, (population_max,))
        elif population_min:
            query = query + "Population >= %s ORDER BY "

            if sort == "country":
                query += "Country;"
            else:
                query += "Population DESC;"

            response = _cursor.execute(query, (population_min,))
        else:
            print "shouldn't get here"  # sanity check

        result = []
        for item in _cursor.fetchall():
            put = {}
            put['name'] = item[0]
            put['population'] = item[1]
            put['capitals'] = getCapitals(item[0])
            put['languages'] = getLanguagesCountry(item[0])
            result.append(put)

        return result
    elif population:
        query = "SELECT Country, Population FROM country WHERE "

        if population_min and population_max:
            query = query + "Population >= %s AND Population <= %s ORDER BY "

            if sort == "country":
                query += "Country;"
            else:
                query += "Population DESC;"

            response = _cursor.execute(query, (population_min, population_max))
        elif population_max:
            query = query + "Population <= %s ORDER BY "

            if sort == "country":
                query += "Country;"
            else:
                query += "Population DESC;"

            response = _cursor.execute(query, (population_max,))
        elif population_min:
            query = query + "Population >= %s ORDER BY "

            if sort == "country":
                query += "Country;"
            else:
                query += "Population DESC;"

            response = _cursor.execute(query, (population_min,))
        else:
            pass

        result = []
        for item in _cursor.fetchall():
            put = {}
            put['name'] = item[0]
            put['population'] = item[1]
            put['capitals'] = getCapitals(item[0])
            put['languages'] = getLanguagesCountry(item[0])
            result.append(put)

        return result
    elif lang_list:
        languages = '\' OR Language = \''.join(lang_list)
        langquery = 'Language = \'' + languages + '\''
        if cri:
            query = "SELECT * FROM multlangcountries NATURAL JOIN "\
                    "(SELECT * FROM (SELECT DISTINCT Country FROM country_language WHERE "
            query += langquery + ") q NATURAL JOIN country) p "
        else:
            query = "SELECT * FROM (SELECT DISTINCT Country FROM country_language WHERE "
            query += langquery + ") q NATURAL JOIN country "

        if sort == 'population':
            query += "ORDER BY Population DESC;"
        else:
            query += "ORDER BY Country;"

        response = _cursor.execute(query)

        result = []
        fetch = _cursor.fetchall()
        for item in fetch:
            put = {}
            put['name'] = item[0]
            put['population'] = item[1]
            put['capitals'] = getCapitals(item[0])
            put['languages'] = getLanguagesCountry(item[0])
            result.append(put)

        return result
    else:
        query = "SELECT * FROM country;"
        response = _cursor.execute(query)

        result = []
        for item in _cursor.fetchall():
            put = {}
            put['name'] = item[0]
            put['population'] = item[1]
            put['capitals'] = getCapitals(item[0])
            put['languages'] = getLanguagesCountry(item[0])
            result.append(put)

        return result


# returns a country's capitals in a string
def getCapitals(country):
    query = "SELECT Capital FROM capitals WHERE Country = %s;"
    response = _cursor.execute(query, (country,))
    capitals = []
    fetch = _cursor.fetchall()
    for row in fetch:
        capitals.append(row[0])
    capitals = ', '.join(capitals)
    return capitals


# returns a country's languages in a string
def getLanguagesCountry(country):
    query = "SELECT Language FROM country_language WHERE Country = %s;"
    response = _cursor.execute(query, (country,))
    languages = []
    for row in _cursor.fetchall():
        languages.append(row[0])
    languages = ', '.join(languages)
    return languages


# returns a city's languages in a string
def getLanguagesCity(city):
    query = "SELECT Language FROM city_language WHERE City = %s;"
    response = _cursor.execute(query, (city,))
    languages = []
    for row in _cursor.fetchall():
        languages.append(row[0])
    languages = ', '.join(languages)
    return languages


def isCapital(city):
    query = "SELECT * FROM capitals WHERE Capital = %s;"
    response = _cursor.execute(query, (city,))
    return response > 0


def getCityScore(city):
    query = "SELECT Average_score FROM city_scores WHERE City = %s;"
    response = _cursor.execute(query, (city,))
    fetch = _cursor.fetchone()
    return fetch[0] if fetch else "N/A"


def getCityInfo(tuplelist):
    result = []
    for item in tuplelist:
        dicti = {}
        dicti['city'] = item[0]
        dicti['country'] = item[1]
        dicti['latitude'] = item[2]
        dicti['longitude'] = item[3]
        dicti['population'] = item[4]
        dicti['iscapital'] = isCapital(item[0])
        dicti['languages'] = getLanguagesCity(item[0])
        dicti['score'] = getCityScore(item[0])
        result.append(dicti)
    return result

'''def getCityInfoTwo(tuplelist):
    result = []
    for item in tuplelist:
        dicti = {}
        dicti['city'] = item[0]
        dicti['country'] = item[1]
        dicti['latitude'] = item[2]
        dicti['longitude'] = item[3]
        dicti['population'] = item[4]
        dicti['iscapital']'''

# returns specific city in format [city, country, latitude, longitude,
#       population, is_capital, [languages]]
# returns
def citySearch(city, country, population_min, population_max, lang_list, sort):

    query = 'SELECT * FROM city c '

    ps = ''
    if sort:
        if sort == 'highest':
            query = "SELECT  City, Country, latitude, longitude, population, AVG(cr.Score) FROM city  NATURAL JOIN city_review cr "
            ps = " GROUP BY City, Country ORDER BY 6 DESC"
        if sort == 'lowest':
            query = "SELECT c.City, c.Country, c.latitude, c.longitude, c.population, AVG(cr.Score) FROM city c NATURAL JOIN city_review cr "
            ps = " GROUP BY City, Country ORDER BY 6 ASC"
        if sort == 'population':
            ps = " ORDER BY population DESC "
        if sort == 'city':
            ps = " ORDER BY City ASC "

    if city or country or population_min or population_max:
        query = query + "WHERE "
    if city:
        query = query + "c.City = '" + str(city) + "' AND "
    if country:
        query = query + "c.Country = '" + str(country) + "' AND "
    if population_min:
        query = query + "c.population > '" + str(population_min) + "' AND "
    if population_max:
        query = query + "c.population < '" + str(population_max) + "' AND "

    langQuery = ''
    anyLang = False
    if lang_list:
        if 'Any additional language' in lang_list:
            anyLang = True
            lang_list.remove('Any additional language')
            anyLangQuery = "SELECT * FROM multlangcities "

        if len(lang_list) > 0:
            langQuery = " SELECT DISTINCT cl.City, cl.Country FROM city_language cl WHERE cl.Language = '"
            for i in range(len(lang_list)):
                selectedLang = str(lang_list[i])
                if i < (len(lang_list) - 1):
                    langQuery = langQuery + str(selectedLang) + "' OR cl.Language = '"
                else:
                    langQuery = langQuery + str(selectedLang) + "' "
            if anyLang:
                langQuery = "SELECT * FROM ((" + langQuery + ") l1 NATURAL JOIN (" + anyLangQuery + ") l2 ) "
        else:
            langQuery = anyLangQuery
        #_cursor.execute(langQuery)
        #responseTwo = _cursor.fetchall()
    else:
        langQuery = "SELECT DISTINCT City FROM city_language"

    if query[-5:] == ' AND ':
        query = query[:-5]

    #query = query + langQuery
    query = query + ps

    #_cursor.execute(query)
    finalQuery = "SELECT * FROM ((" + query + ") q1 NATURAL JOIN (" + langQuery + ") q2 ) " + ps
    #print finalQuery

    _cursor.execute(finalQuery)
    response = _cursor.fetchall() #TODO return correct shit

    #for i in response:
    #    print i
    #print response
    #print responseTwo

    #finalQuery = _cursor.execute()
    #return getCityInfo(responseTwo)
    return getCityInfo(response)
    '''population = population_max or population_min

    cri = False
    if lang_list and "Any additional language" in lang_list:
        cri = True
        lang_list.remove('Any additional language')

    if city:  # searching by city, returns just info about that city
        query = "SELECT * FROM city WHERE City = %s;"
        response = _cursor.execute(query, (city,))

        return getCityInfo(_cursor.fetchall())
    elif country and population and lang_list:
        print 1
    elif country and population:
        print 2
    elif country and lang_list:
        print 3
    elif population and lang_list:
        languages = '\' OR Language = \''.join(lang_list)
        langquery = 'Language = \'' + languages + '\''
        if cri:
            query = "SELECT * FROM multlangcities NATURAL JOIN "\
                    "(SELECT * FROM (SELECT DISTINCT City FROM city_language WHERE "
            query += langquery + ") q NATURAL JOIN city) p "
        else:
            query = "SELECT * FROM (SELECT DISTINCT City FROM city_language WHERE "
            query += langquery + ") q NATURAL JOIN city "

        # TODO highest lowest rated
        if sort == 'city':
            query += "ORDER BY City;"
        else:
            query += "ORDER BY Population DESC;"

        response = _cursor.execute(query)
        return getCityInfo(_cursor.fetchall())
    elif country:
        query = "SELECT * FROM city WHERE Country = %s "

        # TODO highest lowest rated
        if sort == 'city':
            query += "ORDER BY City;"
        else:
            query += "ORDER BY Population DESC;"

        response = _cursor.execute(query, (country,))

        return getCityInfo(_cursor.fetchall())
    elif population:
        query = "SELECT * FROM city WHERE "

        if population_min and population_max:
            query = query + "Population >= %s AND Population <= %s ORDER BY "

            if sort == "city":
                query += "City;"
            else:
                query += "Population DESC;"

            response = _cursor.execute(query, (population_min, population_max))
        elif population_max:
            query = query + "Population <= %s ORDER BY "

            if sort == "city":
                query += "City;"
            else:
                query += "Population DESC;"

            response = _cursor.execute(query, (population_max,))
        elif population_min:
            query = query + "Population >= %s ORDER BY "

            if sort == "city":
                query += "City;"
            else:
                query += "Population DESC;"

            response = _cursor.execute(query, (population_min,))

        return getCityInfo(_cursor.fetchall())

    elif lang_list:
        languages = '\' OR Language = \''.join(lang_list)
        langquery = 'Language = \'' + languages + '\''
        if cri:
            query = "SELECT * FROM multlangcities NATURAL JOIN "\
                    "(SELECT * FROM (SELECT DISTINCT City FROM city_language WHERE "
            query += langquery + ") q NATURAL JOIN city) p "
        else:
            query = "SELECT * FROM (SELECT DISTINCT City FROM city_language WHERE "
            query += langquery + ") q NATURAL JOIN city "

        if sort == 'highest':
            pass  # TODO
        elif sort == 'lowest':
            pass  # TODO
        elif sort == 'population':
            query += "ORDER BY Population DESC;"
        else:
            query += "ORDER BY City;"

        response = _cursor.execute(query)
        return getCityInfo(_cursor.fetchall())
    else:
        query = "SELECT * FROM city;"
        response = _cursor.execute(query)

        return getCityInfo(_cursor.fetchall())'''


def locationSearch(name, address, city, cost_min, cost_max, type_list, sort):
    query = 'SELECT * FROM location l'

    if sort:
        if sort == 'highest':
            query = 'SELECT l.Address, l.City, l.Country, l.Cost, l.Type, l.Std_discount, l.Name, AVG(lr.Score) FROM location l NATURAL JOIN location_review lr'
            ps = ' GROUP BY l.Address, l.City, l.Country ORDER BY 8 DESC'  # AVG Score and GROUP BY prevent duplicates
        if sort == 'location':
            ps = ' ORDER BY l.Name ASC'
        if sort == 'lowest':
            query = 'SELECT l.Address, l.City, l.Country, l.Cost, l.Type, l.Std_discount, l.Name, AVG(lr.Score) FROM location l NATURAL JOIN location_review lr'
            ps = ' GROUP BY l.Address, l.City, l.Country ORDER BY 8 ASC'
        if sort == 'type':
            ps = ' ORDER BY l.Type ASC'
    else:
        ps = ''

    if name or address or city or cost_min or cost_max or type_list:
        query = query + " WHERE "
    if name:
        query = query + " l.Name = '" + re.escape(str(name)) + "' AND "
    if address:         # address takes precedence in filters bc primary key
        query = query + " l.Address = '" + str(address) + "' AND "
    if city:
        query = query + " l.City = '" + str(city) + "' AND "
    if cost_min:
        query = query + " l.Cost >= '" + str(cost_min) + "' AND "
    if cost_max:
        query = query + " l.Cost <= '" + str(cost_max) + "' AND "

    typeQuery = ''
    if type_list:
        for i in range(len(type_list)):
            selectedType = str(type_list[i])
            typeQuery = typeQuery + " l.Type = '" + re.escape(selectedType) + "' OR "
        if typeQuery[-4:] == ' OR ':
            typeQuery = typeQuery[:-4]

    if query[-5:] == ' AND ' and typeQuery == '':
        query = query[:-5]

    query = query + typeQuery
    query = query + ps

    _cursor.execute(query)
    response = _cursor.fetchall()

    return getLocInfo(response)


def getTypeQuery(type_list):
    query = '\' OR Type = \''.join(type_list)
    query = '(Type = \'' + query + '\')'
    return query


def getLocInfo(tuplelist):
    result = []
    for item in tuplelist:
        dicti = {}
        dicti['name'] = item[6]
        dicti['address'] = item[0]
        dicti['city'] = item[1]
        dicti['country'] = item[2]
        dicti['cost'] = item[3]
        dicti['type'] = item[4]
        dicti['std_discount'] = 'No' if item[5] else 'Yes'
        dicti['score'] = getLocScore(item[0], item[1], item[2])
        result.append(dicti)
    return result


def getLocScore(address, city, country):
    query = "SELECT Average_score FROM location_scores WHERE Address = %s "\
            "AND City = %s AND Country = %s;"
    response = _cursor.execute(query, (address, city, country))
    fetch = _cursor.fetchone()
    return fetch[0] if fetch else "N/A"


def getCatQuery(cat_list):
    query = '\' OR Category = \''.join(cat_list)
    query = '(Category = \'' + query + '\')'
    return query


# param std_discount is None if not selected, True if yes, and False if no
def eventSearch(event, city, date, cost_min, cost_max, std_discount, cat_list, sort):
    query = "SELECT * FROM event e "

    ps = ''
    if sort:
        if sort == "name":
            ps = "ORDER BY e.Name ASC"
        if sort == "cost":
            ps = "ORDER BY e.Cost DESC"
        if sort == "highest":
            query = "SELECT e.Name, e.Date, e.Start_time, e.Address, e.City, e.Country, e.Category, e.Description, e.Std_discount, e.End_time, e.Cost, AVG(er.Score) FROM event e NATURAL JOIN event_review er "
            ps = "GROUP BY e.Name, e.Date, e.Start_time, e.Address, e.City, e.Country ORDER BY 12 DESC"
        if sort == "lowest":
            query = "SELECT e.Name, e.Date, e.Start_time, e.Address, e.City, e.Country, e.Category, e.Description, e.Std_discount, e.End_time, e.Cost, AVG(er.Score) FROM event e NATURAL JOIN event_review er "
            ps = "GROUP BY e.Name, e.Date, e.Start_time, e.Address, e.City, e.Country ORDER BY 12 ASC"

    if event or city or date or cost_min or cost_max or cat_list or not (std_discount is None):
        query = query + "WHERE "
    if event:
        query = query + " e.Name = '" + re.escape(str(event)) + "' AND "
    if city:
        query = query + " e.City = '" + str(city) + "' AND "
    if date:
        query = query + " e.Date = '" + str(date) + "' AND "
    if cost_min:
        query = query + " e.Cost >= '" + str(cost_min) + "' AND "
    if cost_max:
        query = query + " e.Cost <= '" + str(cost_max) + "' AND "
    if std_discount is True:
        query = query + " e.Std_discount = TRUE AND "
    elif std_discount is False:
        query = query + " e.Std_discount = FALSE AND "

    catQuery = ''
    if cat_list:
        for i in range(len(cat_list)):
            selectedCat = str(cat_list[i])
            catQuery = catQuery + " e.Category = '" + selectedCat + "' OR "
        if catQuery[-4:] == " OR ":
            catQuery = catQuery[:-4]

    if query[-5:] == ' AND ' and catQuery == '':
        query = query[:-5]

    query = query + catQuery
    query = query + ps

    _cursor.execute(query)
    response = _cursor.fetchall()

    return getEventInfo(response)


def getEventInfo(tuplelist):
    list1 = []
    for item in tuplelist:
        dicti = {}
        dicti['name'] = item[0]
        dicti['date'] = str(item[1])
        dicti['starttime'] = str(item[2])
        dicti['address'] = item[3]
        dicti['city'] = item[4]
        dicti['country'] = item[5]
        dicti['category'] = item[6]
        dicti['description'] = item[7]
        dicti['std_discount'] = 'Yes' if item[8] else 'No'
        dicti['endtime'] = 'unknown' if item[9] is None else str(item[9])
        dicti['cost'] = item[10]
        dicti['score'] = getEventScore(item[0], item[1], item[2], item[3], item[4])
        list1.append(dicti)
    return list1


# doesn't work, lmao
def getEventScore(name, date, starttime, address, city):
    query = "SELECT Average_score FROM event_scores WHERE Name = %s AND Date = %s"\
            " AND Start_time = %s AND Address = %s AND City = %s;"
    response = _cursor.execute(query, (name, date, starttime, address, city))
    fetch = _cursor.fetchone()
    return fetch[0] if fetch else "N/A"


# helper for writeReviews
def getCityCountry(city):
    query = "SELECT Country FROM city WHERE City = %s"
    response = _cursor.execute(query, (city,))
    fetch = _cursor.fetchone()
    return fetch[0] if fetch else "N/A"


# testing
setupConnection()

# print writeReview()
# code for SELECT for testing :)
# _cursor.execute("SELECT * FROM city_language")
# for row in _cursor.fetchall():
#     print row
# print citySearch(None, None, None, None, None)

closeConnection()
