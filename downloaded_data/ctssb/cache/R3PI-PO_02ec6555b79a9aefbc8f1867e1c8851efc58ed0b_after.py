#!flask/bin/python
__author__ = 'tribhu'

from flask import Flask, jsonify, abort, make_response, url_for, request

from persistent_helpers import get_recipe_info, get_recipe_ids
from parse_helper import route_command

app = Flask(__name__)

@app.route('/recipes/api/v1.0/recipes', methods=['GET'])
def get_recipes():
    """
    @return: a JSON RecipeList object
    """
    return get_recipe_ids()


@app.route('/recipes/api/v1.0/ask', methods=['GET'])
def get_recipe():
    """get_recipe requires two GET parameters:
    a. recipe_id - the recipe ID number
    b. text - the (sepeech-converted) textual command

    @return: a JSON Recipe object
    """
    recipe_id =  int(request.args.get('recipe_id'))
    text = request.args.get('text')
    response_json = route_command(text, recipe_id)

    if recipe_blob == None:
        abort(404)
    return response_json


@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)


def make_public_task(recipe):
    new_recipe = {}
    for field in recipe:
        if field == 'id':
            new_recipe['uri'] = url_for('get_recipe', recipe_id=recipe['id'], _external=True)
        else:
            new_recipe[field] = recipe[field]
    return new_recipe


if __name__ == '__main__':
    app.run(debug=True)
