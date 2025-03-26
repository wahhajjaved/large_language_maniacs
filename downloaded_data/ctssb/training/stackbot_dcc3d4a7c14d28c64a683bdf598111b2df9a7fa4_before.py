"""This module handles the query route /api/q"""
import datetime
import logging
import urllib

from flask import request, abort, jsonify
from shared import app
from shared import security, get_geo_data, ApiResponse
from models.query import Query
from user_agents import parse as parseUA


@app.route('/api/q', methods=['GET'])
def query_handler():
    """ Handle the incoming request and create a Query entity if a query string was passed. """

    # Make sure the length of the query string is at least 1 char.
    query_string = request.args.get('q', '')
    if len(query_string) <= 0:
        abort(400)

    user_id = None
    try:
        user_id = security.authenticate_user(request)
    except security.ValidationError as err:
        # IF the user isn't logged in, then throw a 403 error.
        logging.error(err)
        abort(401)

    # Get the user-agent header from the request.
    user_agent = parseUA(request.headers['User-Agent'])
    geo = get_geo_data(request)

    # Create a new Query entity from the q value.
    # TODO: Add the other values that we want from the request headers.
    query = Query(
        query=query_string,
        os=str(user_agent.os.family) + " Version: " + str(user_agent.os.version_string),
        browser=str(user_agent.browser.family),
        timestamp=datetime.datetime.utcnow().isoformat(),
        country=geo['country'],
        city=geo['city'],
        city_lat_long=geo['city_lat_long'],
        ip=request.remote_addr,
        uid=user_id
    )
    # Save to the datatore.
    query.put()
    logging.debug('query: %s', str(query))

    escaped_q = urllib.urlencode({'q': query_string})
    redirect = 'http://google.com/#' + escaped_q

    # Output for when we first land on the page (or when no query was entered)
    # response.headers['Content-Type'] = 'application/json'
    output = {
        'redirect': redirect
    }
    return jsonify(ApiResponse(output))
