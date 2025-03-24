from flask import jsonify, render_template, request
from jinja2.exceptions import TemplateNotFound
from teknologkoren_se import app


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(405)
@app.errorhandler(409)
def handle_error(e):
    if request.path.startswith('/api'):
        # The api should not return html
        api_response = {
                400: {'error': 'Bad Request'},
                403: {'error': 'Forbidden'},
                404: {'error': 'Not Found'},
                405: {'error': 'Method Not Allowed'},
                409: {'error': 'Conflict'},
                }
        response = api_response[e.code]
        response['message'] = e.description

        return jsonify(response), e.code

    else:
        try:
            response = render_template('errors/{}.html'.format(e.code))
        except TemplateNotFound:
            response = e
        return response, e.code


@app.errorhandler(500)
def handle_server_error(e):
    """Handle Internal Server Errors.

    Handlers for 500 are passed the uncaught exception instead of
    HTTPException (though documentation says "as well", but that
    does not seem to be the case).
    """
    if request.path.startswith('/api'):
        # The api should not return html
        api_response = {'error': 'Internal Server Error'}

        return jsonify(api_response), 500

    else:
        return render_template('errors/500.html'), 500
