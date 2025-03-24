#!/usr/bin/python
# -*- coding: latin-1 -*-

from flask import Flask, jsonify, abort, make_response, request, g, send_from_directory
from flask_restful import Resource, Api, reqparse
from flask_httpauth import HTTPBasicAuth
from webscraper.classifier import generate_meal_plan
from api.models import *
from api import app, session
from sqlalchemy import text
import datetime
import json

my_api = Api(app) # resources are added to this object
auth = HTTPBasicAuth()

@auth.verify_password
def verify_password(username_or_token, password):
    # first try to authenticate by token
    entity = Entity.verify_auth_token(username_or_token)

    if entity is None:
        # try to authenticate with username/password
        entity = session.query(Entity).filter_by(username = username_or_token).first()

        if entity is None:
            entity = session.query(Entity).filter_by(email = username_or_token).first()

        if not entity or not entity.verify_password(password):
            return False

    g.entity = entity
    return True

# ensure that entities can only access their own resources (one entity can't modify another's mealplan)
# allow admins access to all resources
def validate_access(func):
    def decorator(*args, **kwargs):
        # chec entity has admin access
        if not g.entity.is_admin:
            # if the entity isn't admin, give it access to resources it owns
            if 'entity_pk' not in kwargs or g.entity.entity_pk != kwargs['entity_pk']:
                res = make_response("Unauthorized Access")
                if res.status_code == 200:
                    # if user didn't set status code, use 401
                    res.status_code = 401
                if 'WWW-Authenticate' not in res.headers.keys():
                    res.headers['WWW-Authenticate'] = auth.authenticate_header()
                return res
        return func(*args, **kwargs)
    return decorator

class Recipes(Resource):
    @auth.login_required
    def get(self, recipe_pk):
        recipe = session.query(Recipe).filter_by(recipe_pk=recipe_pk).first()
        if recipe is None:
            abort(400, "Recipe not found")
        return recipe.as_dict()

class RecipesList(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('name', required=False, type=str, location='args')
        self.reqparse.add_argument('is_calibration_recipe', required=False, type=bool, location='args')
        self.reqparse.add_argument('page', required=False, type=int, location='args')
        self.reqparse.add_argument('page_size', required=False, type=int, location='args')
        super(RecipesList, self).__init__()

    @auth.login_required
    def get(self):
        params = self.reqparse.parse_args()
        query = session.query(Recipe)

        if params['is_calibration_recipe'] is not None:
            query = query.join(RecipeTag).join(Tag)
            if params['is_calibration_recipe']:
                query = query.filter(Tag.name == 'calibration')
            else:
                query = query.filter(Tag.name != 'calibration')

        if params['name'] is not None:
            query = query.filter(Recipe.name.ilike('%' + str(params['name']) + '%'))

        # limit and offset results after all other query operations
        if params['page'] is not None and params['page_size'] is not None:
            page = params['page']
            page_size = params['page_size']

            query = query.limit(page_size)
            query = query.offset(page * page_size)

        recipes = query.all()
        return (my_map(lambda r: r.as_dict(), recipes))

class EntityRecipeRatings(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('rating', required=False, type=int, location='json')
        self.reqparse.add_argument('is_calibration_recipe', required=False, type=bool, location='json')
        self.reqparse.add_argument('notes', required=False, type=str, location='json')

        super(EntityRecipeRatings, self).__init__()


    @auth.login_required
    @validate_access
    def get(self, entity_pk, recipe_pk):
        entity_rating = session.query(EntityRecipeRating).filter(EntityRecipeRating.entity_fk == entity_pk, EntityRecipeRating.recipe_fk == recipe_pk).first()
        if entity_rating is None:
            return None
        return entity_rating.as_dict()

    @auth.login_required
    @validate_access
    def post(self, entity_pk, recipe_pk):
        params = self.reqparse.parse_args()

        existing_entity_rating = session.query(EntityRecipeRating).filter(EntityRecipeRating.entity_fk == entity_pk, EntityRecipeRating.recipe_fk == recipe_pk).first()
        if existing_entity_rating is not None: # enty exists
            if( params.rating is not None ):
                existing_entity_rating.rating = params.rating

            if( params.notes is not None ):
                existing_entity_rating.notes = params.notes

            if( params.is_calibration_recipe is not None ):
                existing_entity_rating.is_calibration_recipe = params.is_calibration_recipe

            entityRecipeRating  = existing_entity_rating
        else:

            if params.is_calibration_recipe is None:
                params.is_calibration_recipe = False

            entityRecipeRating = EntityRecipeRating(
                    entity_fk=entity_pk,
                    recipe_fk=recipe_pk,
                    rating=params.rating,
                    is_calibration_recipe = params.is_calibration_recipe,
                    notes = params.notes
            )

            session.add(entityRecipeRating)

        session.commit()

        return entityRecipeRating.as_dict()

    @auth.login_required
    def put(self, entity_pk, recipe_pk):
        params = self.reqparse.parse_args()

        existing_entity_rating = session.query(EntityRecipeRating).filter(EntityRecipeRating.entity_fk == entity_pk, EntityRecipeRating.recipe_fk == recipe_pk).first()

        if existing_entity_rating is None:
            return abort(400, "No recipe exists for that user")

        if params.is_calibration_recipe is not None:
            existing_entity_rating.is_calibration_recipe = params['is_calibration_recipe']

        if params.rating is not None:
            existing_entity_rating.rating = params['rating']

        session.commit()

        return existing_entity_rating.as_dict()

class EntitiesList(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('email'     ,       required=True, type=str, location='json')
        self.reqparse.add_argument('password'  ,       required=True, type=str, location='json')
        self.reqparse.add_argument('first_name',       required=True, type=str, location='json')
        self.reqparse.add_argument('last_name' ,       required=True, type=str, location='json')
        self.reqparse.add_argument('username'  ,       required=True, type=str, location='json')
        super(EntitiesList, self).__init__()

    @auth.login_required
    @validate_access
    def get(self):
        entities = session.query(Entity).all()

        return my_map(lambda e: e.as_dict(), entities)

    def post(self):
        new_entity = self.reqparse.parse_args()

        # check username
        existing_entity = session.query(Entity).filter(Entity.email == new_entity.email).first()
        if existing_entity is not None: # user exists
            return abort(400, "A user already exists with this email.")

        existing_entity = session.query(Entity).filter(Entity.username == new_entity.username).first()
        if existing_entity is not None: # user exists
            return abort(400, "A user already exists with this username.")

        entity = Entity(
                first_name=new_entity.first_name,
                last_name=new_entity.last_name,
                username=new_entity.username,
                email=new_entity.email
                )

        entity.hash_password(new_entity.password)

        session.add(entity)
        session.commit()

        g.entity = entity
        entity_dict = entity.as_dict()
        entity_dict['token'] = str(entity.generate_auth_token(60000))

        return entity_dict

# Route for getting the current entity associated with give auth credentials
class CurrentEntity(Resource):
    @auth.login_required
    def get(self):
        entity = session.query(Entity).filter_by(entity_pk=g.entity.entity_pk).first()

        if(entity is None):
            abort(400, "This entity does not exist")

        return entity.as_dict()

class Entities(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('email', type=str, location='json')
        self.reqparse.add_argument('password', type=str, location='json')
        self.reqparse.add_argument('first_name', type=str, location='json')
        self.reqparse.add_argument('last_name', type=str, location='json')
        self.reqparse.add_argument('allergies', type=list, location='json')
        self.reqparse.add_argument('dietary_concerns', type=list, location='json')
        super(Entities, self).__init__()

    @auth.login_required
    @validate_access
    def get(self, entity_pk):
        entity = session.query(Entity).filter_by(entity_pk=entity_pk).first()

        if(entity is None):
            abort(400, "This entity does not exist")

        return entity.as_dict()

    @auth.login_required
    def put(self, entity_pk):
        # don't use g.entity incase the use is logged in as admin
        entity = session.query(Entity).filter_by(entity_pk=entity_pk).first()

        if(entity is None):
            abort(400, "This entity does not exist")

        params = self.reqparse.parse_args()

        if params['first_name'] is not None:
            entity.first_name = params['first_name']

        if params['last_name'] is not None:
            entity.last_name = params['last_name']

        if params['email'] is not None:
            existing_entity = session.query(Entity).filter_by(email=params['email']).first()
            if existing_entity is not None and existing_entity.entity_pk != g.entity.entity_pk:
                abort(400, "Someone already uses this email.")
            entity.email = params['email']

        if params['password'] is not None:
            if len(params['password']) < 6:
                abort(400, "Password must be at least 6 characters.")

            entity.password = params['password']

        if params['allergies'] is not None:
            allergies = params['allergies']

            for allergy in allergies:
                ingredient = None
                if isinstance(allergy, basestring):
                    allergy = allergy.lower().strip(' ')
                    ingredient = session.query(Ingredient).filter_by(name = allergy).first()
                elif isinstance(allergy, int):
                    ingredient = session.query(Ingredient).filter_by(ingredient_pk = allergy).first()
                else:
                    abort(400, "Allergy must be an integer or a string.")

                if ingredient is None:
                    abort(400, "Allergy, " + str(ingredient) + ", does not exist.")

                if ingredient.ingredient_pk not in my_map(lambda a: a.ingredient_fk, entity.allergies):
                    # if this entity doesn't have this dietary concern, add the dietary concern
                    allergy = Allergy(entity_fk = entity.entity_pk, ingredient_fk = ingredient.ingredient_pk)
                    session.add(allergy)

        if params['dietary_concerns'] is not None:
            dietary_concerns = params['dietary_concerns']

            for dietary_concern in dietary_concerns:
                tag = None
                if isinstance(dietary_concern, basestring):
                    dietary_concern = dietary_concern.lower().strip(' ')
                    tag = session.query(Tag).filter_by(name = dietary_concern, tag_type_pk = 1).first()
                elif isinstance(dietary_concern, int):
                    tag = session.query(Tag).filter_by(tag_pk = dietary_concern, tag_type_fk = 1).first()
                else:
                    abort(400, "Dietary concern tag must be an integer or a string.")

                if tag is None:
                    abort(400, "Dietary concern tag with primary key, " + str(tag) + ", does not exist.")

                if tag.tag_pk not in my_map(lambda t: t.tag_fk, entity.entity_tags):
                    # if this entity doesn't have this dietary concern, add the dietary concern
                    entity_tag = EntityTag(entity_fk = entity.entity_pk, tag_fk = tag.tag_pk)
                    session.add(entity_tag)

        session.commit()

        return my_map_to_list(entity.as_dict())

    @auth.login_required
    @validate_access
    def delete(self, entity_pk):
        entity = session.query(Entity).filter_by(entity_pk = entity_pk).first()
        if entity is None: # entity doesn't exist
            return None

        for entity_tag in entity.entity_tags:
            entity_tag = session.query(EntityTag).filter_by(entity_tag_pk = entity_tag.entity_tag_pk)
            session.delete(entity_tag)

        session.delete(entity)
        session.commit()

        return (entity.as_dict())

class Tokens(Resource):
    @auth.login_required
    def get(self):
        token = g.entity.generate_auth_token(60000) # expires after 16.6 hours
        return { 'token': token.decode('ascii') }

    @auth.login_required
    def delete(self):
        #TODO store token in db and upon logout invalidate row
        pass

class TagsList(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('tag_type')
        super(TagsList, self).__init__()

    @auth.login_required
    def get(self, tag_type_pk):
        tags = session.query(Tag).filter_by(tag_type_fk = tag_type_pk).all()
        return (my_map(lambda t: t.as_dict(), tags))

class EntityMealPlans(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('date', required = False, type=str, location='args')
        self.reqparse.add_argument('recipe_pk', required = False, type=str, location='args')
        self.reqparse.add_argument('num_days', required = False, type=int, location='args')

        self.reqparse.add_argument('start_date', required = False, type=str, location='args')
        self.reqparse.add_argument('end_date', required = False, type=str, location='args')

        self.reqparse.add_argument('is_favorite', required=False, type=str, location='args')
        self.reqparse.add_argument('is_breakfast', required=False, type=str, location='args')
        self.reqparse.add_argument('is_lunch', required=False, type=str, location='args')
        self.reqparse.add_argument('is_dinner', required=False, type=str, location='args')
        super(EntityMealPlans, self).__init__()

    @auth.login_required
    @validate_access
    def get(self, entity_pk):
        import time
        entity = session.query(Entity).filter_by(entity_pk=entity_pk).first()

        if(entity is None):
            abort(400, "This entity does not exist")

        params = self.reqparse.parse_args()
        date = params['date']
        start_date = params['start_date']
        end_date = params['end_date']
        meal_plans_query = session.query(MealPlan).filter(MealPlan.entity_fk == entity_pk)

        if start_date is not None and end_date is not None:
            meal_plans_query = meal_plans_query.filter(MealPlan.eat_on.between(start_date, end_date))
        else:
            # default to grabbing the current / given date
            if date is None:
                date = str(time.strftime("%Y-%m-%d"))
            meal_plans_query = meal_plans_query.filter(MealPlan.eat_on == date)

        #get favorite recipes only
        if params.is_favorite is not None:
           entity_recipe_ratings = session.query(EntityRecipeRating).filter(EntityRecipeRating.entity_fk == entity_pk, EntityRecipeRating.rating == 1).all()
           favorite_recipe_fks = my_map(lambda r: r.recipe_fk, entity_recipe_ratings)
           meal_plans_query = meal_plans_query.filter(MealPlan.recipe_fk.in_(favorite_recipe_fks))

        #filter based on meal type parameters
        meal_types = []
        if params.is_breakfast is not None:
            meal_types.append('breakfast')
        if params.is_lunch is not None:
            meal_types.append('lunch')
        if params.is_dinner is not None:
            meal_types.append('dinner')

        #final filtering of meals
        if len(meal_types) > 0:
            meal_plans_query = meal_plans_query.filter(MealPlan.meal_type.in_(meal_types))

        meal_plans = meal_plans_query.all()
        if meal_plans is None:
            return None

        meal_plan_dict = {}
        for meal_plan in meal_plans:
            eat_on = str(meal_plan.eat_on)
            if eat_on not in meal_plan_dict:
                meal_plan_dict[eat_on] = {}
            if meal_plan.meal_type not in meal_plan_dict[eat_on]:
                meal_plan_dict[eat_on][meal_plan.meal_type] = []
            meal_plan_dict[eat_on][meal_plan.meal_type] = meal_plan.as_dict()

        # if the date param is used just return the breakfast, lunch, and dinner keys
        if date is not None and start_date is None and end_date is None:
            if len(meal_plan_dict.keys()) > 0:
                meal_plan_dict = meal_plan_dict[meal_plan_dict.keys()[0]]

        return meal_plan_dict

    @auth.login_required
    @validate_access
    def post(self, entity_pk):
        entity = session.query(Entity).filter_by(entity_pk=entity_pk).first()
        params = self.reqparse.parse_args()

        if(entity is None):
            abort(400, "This entity does not exist")

        #call algorithm on number of days till cron-job updates on Sunday
        if not g.entity.is_admin or params.num_days is None:
            num_days = 7 - datetime.datetime.today().weekday()
        else:
            # only admins should be able to set the number of dates generated
            num_days = params.num_days

        generated_meal_plans = []

        try:
            generated_meal_plans = generate_meal_plan(entity_pk, num_days)
        #return error for problem, otherwise return None
        except Exception as e:
            # Don't want to show users backend error messages.
            print("Failed to generate meal plan: " + str(e.message))
            abort(400, "Failed to generate meal plan")

        return generated_meal_plans

class MealPlans(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('recipe_pk', required = True, type=int, location='json')
        super(MealPlans, self).__init__()

    @auth.login_required
    def put(self, meal_plan_pk):
        meal_plan = session.query(MealPlan).filter_by(meal_plan_pk=meal_plan_pk).first()
        if meal_plan is None:
            abort(400, "Meal plan " + str(meal_plan_pk) + " doesn't exist")
        if meal_plan.entity_fk != g.entity.entity_pk and not g.entity.is_admin:
            abort(400, "User doesn't own this meal plan.")

        params = self.reqparse.parse_args()
        recipe_pk = params['recipe_pk']

        meal_plan.recipe_fk = recipe_pk
        session.commit()

        return meal_plan.as_dict()

class EntityGroceryList(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('start_date', required = True, type=str, location='args')
        self.reqparse.add_argument('end_date', required = True, type=str, location='args')
        super(EntityGroceryList, self).__init__()

    @auth.login_required
    @validate_access
    def get(self, entity_pk):
        params = self.reqparse.parse_args()
        start_date = params['start_date']
        end_date = params['end_date']

        query_params = {
            "entity_pk": entity_pk,
            "start_date": start_date,
            "end_date": end_date
        }

        # using raw sql, since flask takes forever on the joins
        query = text("""
            SELECT
                i.name,
                ir.description,
                r.name
            FROM tb_meal_plan mp
            JOIN tb_recipe r
                ON r.recipe = mp.recipe
            JOIN tb_ingredient_recipe ir
                ON ir.recipe = r.recipe
            JOIN tb_ingredient i
                ON i.ingredient = ir.ingredient
            WHERE
                mp.entity = :entity_pk AND
                mp.eat_on::date >= :start_date AND
                mp.eat_on::date <= :end_date
            GROUP BY
                i.name, ir.description, r.name
            ORDER BY i.name ASC;
        """)
        retval = session.execute(query, query_params).fetchall()

        grocery_list = {}
        for row in retval:
            ingredient_name = row[0]
            ingredient_description = row[1]
            recipe_name = row[2]

            recipe_obj = {
                'ingredient_description': ingredient_description,
                'recipe_name': recipe_name
            }

            ingredient_name = ingredient_name.decode()
            if ingredient_name not in grocery_list:
                grocery_list[ingredient_name] = []

            grocery_list[ingredient_name].append(recipe_obj)

        return grocery_list

@app.route("/")
@auth.login_required
def static_index():
    return send_from_directory("static", "index.html")

my_api.add_resource(TagsList, '/api/v2.0/tag_types/<int:tag_type_pk>/tags', endpoint = 'tagslist')

my_api.add_resource(EntitiesList, '/api/v2.0/entities', endpoint = 'entitieslist')
my_api.add_resource(Entities, '/api/v2.0/entities/<int:entity_pk>', endpoint = 'entities')
my_api.add_resource(EntityMealPlans, '/api/v2.0/entities/<int:entity_pk>/meal_plans', endpoint = 'entitymealplans')

my_api.add_resource(MealPlans, '/api/v2.0/meal_plans/<int:meal_plan_pk>', endpoint = 'mealplans')

my_api.add_resource(CurrentEntity, '/api/v2.0/entities/current', endpoint = 'currententity')

my_api.add_resource(RecipesList, '/api/v2.0/recipes', endpoint = 'recipeslist')
my_api.add_resource(Recipes, '/api/v2.0/recipes/<int:recipe_pk>', endpoint ='recipes')
my_api.add_resource(EntityRecipeRatings, '/api/v2.0/entities/<int:entity_pk>/recipes/<int:recipe_pk>', endpoint = 'entityreciperatings')
my_api.add_resource(EntityRecipeRatings, '/api/v2.0/entities/<int:entity_pk>/recipes', endpoint = 'entityrecipees')

my_api.add_resource(EntityGroceryList, '/api/v2.0/entities/<int:entity_pk>/grocery_list', endpoint = 'entitygrocerylist')

my_api.add_resource(Tokens, '/api/v2.0/tokens', endpoint = 'tokens')


@app.errorhandler(400)
def bad_request(e):
    return {'error': 'Bad Request'}, 400

@app.errorhandler(404)
def page_not_found(e):
    return make_response(jsonify({'error': 'Not found'}), 404)

@app.errorhandler(405)
def method_not_allowed(e):
    return make_response(jsonify({'error': 'Method not allowed'}), 405)

@app.errorhandler(500)
def internal_error(e):
    return make_response(jsonify({'error': 'An unexpected error occured'}), 500)

