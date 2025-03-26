from flask import Flask, request, make_response, jsonify
from zatiq_users_mongodb_client import ZatiqUsersMongoDBClient
from zatiq_businesses_mongodb_client import ZatiqBusinessesMongoDBClient
from zatiq_reviews_mongodb_client import ZatiqReviewsMongoDBClient
from zatiq_food_items_mongodb_client import ZatiqFoodItemsMongoDBClient
from mongoengine import *

app = Flask(__name__)
connect('zatiq_database')

timely_meals = ['breakfast', 'brunch', 'lunch', 'dinner']
cuisine_types = ['canadian', 'caribbean', 'chinese', 'dessert', 'fast_food', 'fine_food', 'gluten_free', 'greek', 'halal', 'healthy',
    'indian', 'italian', 'japanese', 'korean', 'kosher', 'mexican', 'middle_eastern', 'pizza', 'quick_bite', 'spicy', 'sushi', 'thai',
    'vegan', 'vegetarian', 'vietnamese']
buttons = ['top_picks', 'surprise_me', 'newest', 'promotions']

@app.route('/')
def hello_world():
    return('Hello World!')

@app.route('/user/login/', methods=['POST'])
def login_as_user():
    if request.method == 'POST':
        zatiq_users = ZatiqUsersMongoDBClient()
        jsonData = request.get_json()
        user_auth_token = jsonData['accessToken']
        login_method = jsonData['method']
        response = zatiq_users.user_register(user_auth_token, login_method)
        return(jsonify(user_name=response[0], user_email=response[1], api_token=response[2]))

@app.route('/business/register/', methods=['POST'])
def register_as_business():
    if request.method == 'POST':
        zatiq_businesses = ZatiqBusinessesMongoDBClient()
        jsonData = request.get_json()
        business_email = jsonData['email']
        business_password = jsonData['password']
        hours = jsonData['date']
        name = jsonData['name']
        address = jsonData['address']
        website = jsonData['website']
        number = jsonData['number']
        image = jsonData['image']['base64']
        image_aspect_ratio = jsonData['image']['image_aspect_ratio']
        features = jsonData['features']
        response = zatiq_businesses.business_register(business_email, business_password, hours, name, address, website, number, image, image_aspect_ratio, features)
        return(jsonify(name=response[0], api_token=response[1], image=response[2], image_aspect_ratio=response[3]))

@app.route('/business/profile/edit/', methods=['POST'])
def edit_business_profile():
    if request.method == 'POST':
        zatiq_businesses = ZatiqBusinessesMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        hours = jsonData['date']
        name = jsonData['name']
        address = jsonData['address']
        website = jsonData['website']
        number = jsonData['number']
        image = jsonData['image']['base64']
        image_aspect_ratio = jsonData['image']['image_aspect_ratio']
        features = jsonData['features']
        response = zatiq_businesses.update_business_profile(api_token, hours, name, address, website, number, image, image_aspect_ratio, features)
        return(jsonify(name=response[0], image=response[1], image_aspect_ratio=response[2], api_token=response[3]))  

@app.route('/business/login/', methods=['POST'])
def login_as_business():
    if request.method == 'POST':
        zatiq_businesses = ZatiqBusinessesMongoDBClient()
        jsonData = request.get_json()
        business_email = jsonData['email']
        business_password = jsonData['password']
        response = zatiq_businesses.business_login(business_email, business_password)
        if len(response) > 1:
            return(jsonify(name=response[0], api_token=response[1], image=response[2], image_aspect_ratio=response[3]))
        else:
            return(jsonify(response=response[0]), 401)

@app.route('/business/logout/', methods=['POST'])
def logout_as_business():
    if request.method == 'POST':
        zatiq_businesses = ZatiqBusinessesMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        response = zatiq_businesses.business_logout(api_token)
        return(jsonify(response=response))

@app.route('/business/profile/', methods=['POST'])
def get_business_profile():
    if request.method == 'POST':
        zatiq_businesses = ZatiqBusinessesMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        response = zatiq_businesses.get_business_profile(api_token)
        return(jsonify(response=response))

@app.route('/user/review/add/', methods=['POST'])
def add_review_as_user():
    if request.method == 'POST':
        zatiq_reviews = ZatiqReviewsMongoDBClient()
        jsonData = request.get_json()
        restaurant_id = jsonData['restaurant_id']
        food_item_id = jsonData['food_item_id']
        text = jsonData['text']
        rating = jsonData['rating']
        api_token = jsonData['api_token']

        if 'image' in jsonData:
            image = jsonData['image']['base64']
            image_aspect_ratio = jsonData['image']['image_aspect_ratio']
        else:
            image = None
            image_aspect_ratio = None
            
        add_review = zatiq_reviews.add_review(restaurant_id, food_item_id, text, image, rating, image_aspect_ratio, api_token)
        return(jsonify(response=add_review))

@app.route('/user/reviews/all/', methods=['POST'])
def get_all_reviews_by_user():
    if request.method == 'POST':
        zatiq_reviews = ZatiqReviewsMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        self_reviews = zatiq_reviews.get_all_reviews_by_reviewer_id(api_token)
        return(jsonify(reviews=self_reviews))

@app.route('/business/reviews/all/', methods=['POST'])
def get_all_reviews_for_business():
    if request.method == 'POST':
        zatiq_business_reviews = ZatiqBusinessesMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        business_reviews = zatiq_business_reviews.get_all_reviews(api_token)
        return(jsonify(reviews=business_reviews))

@app.route('/business/add/food/', methods=['POST'])
def add_food_item_as_business():
    if request.method == 'POST':
        zatiq_food_items = ZatiqFoodItemsMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        image = jsonData['image']
        overview = jsonData['overview']
        item_name = jsonData['item_name']
        tags = jsonData['tags']
        meat = jsonData['meat']
        seafood = jsonData['seafood']
        meal_type = jsonData['meal_type']
        item_price = jsonData['item_price']
        response = zatiq_food_items.add_food_item(image, overview, item_name, api_token, meal_type, tags, item_price, meat, seafood)
        return(jsonify(response=response))

@app.route('/restaurant/menu/add/', methods=['POST'])
def add_menu_photo():
    if request.method == 'POST':
        zatiq_businesses = ZatiqBusinessesMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        image = jsonData['base64']
        image_aspect_ratio = jsonData['image_aspect_ratio']
        add_menu = zatiq_businesses.upload_menu_photo(image, image_aspect_ratio, api_token)
        return(jsonify(response=add_menu))

@app.route('/restaurant/menu/delete/', methods=['POST'])
def delete_menu_photo():
    if request.method == 'POST':
        zatiq_businesses = ZatiqBusinessesMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        image_id = jsonData['image_id']
        delete_menu = zatiq_businesses.delete_menu_photo(image_id, api_token)
        return(jsonify(response=delete_menu))

@app.route('/restaurant/interior/add/', methods=['POST'])
def add_interior_photo():
    if request.method == 'POST':
        zatiq_businesses = ZatiqBusinessesMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        image = jsonData['base64']
        image_aspect_ratio = jsonData['image_aspect_ratio']
        add_menu = zatiq_businesses.upload_interior_photo(image, image_aspect_ratio, api_token)
        return(jsonify(response=add_menu))

@app.route('/restaurant/interior/delete/', methods=['POST'])
def delete_interior_photo():
    if request.method == 'POST':
        zatiq_businesses = ZatiqBusinessesMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        image_id = jsonData['image_id']
        delete_interior = zatiq_businesses.delete_interior_photo(image_id, api_token)
        return(jsonify(response=delete_interior))

@app.route('/restaurant/menu/all/', methods=['POST'])
def get_menus_for_restaurant():
    if request.method == 'POST':
        zatiq_businesses = ZatiqBusinessesMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        menu_photos = zatiq_businesses.get_menu_photos_by_restaurant(api_token)
        return(jsonify(menu_photos=menu_photos))

@app.route('/restaurant/interior/all/', methods=['POST'])
def get_interiors_for_restaurant():
    if request.method == 'POST':
        zatiq_businesses = ZatiqBusinessesMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        interior_photos = zatiq_businesses.get_interior_photos_by_restaurant(api_token)
        return(jsonify(interior_photos=interior_photos))

@app.route('/food/id/', methods=['POST'])
def get_food_item_by_id():
    if request.method == 'POST':
        zatiq_food_items = ZatiqFoodItemsMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        food_item_id = jsonData['food_item_id']
        food_item = zatiq_food_items.get_food_by_id(api_token, food_item_id)
        return(jsonify(food_item=food_item))

@app.route('/food/restaurantid/', methods=['POST'])
def get_food_items_by_restaurant_id():
    if request.method == 'POST':
        zatiq_food_items = ZatiqFoodItemsMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        user_type = jsonData['type'].lower()
        if 'restaurant_id' in jsonData:
            restaurant_id = jsonData['restaurant_id']
        else:
            restaurant_id = None
        food_items = zatiq_food_items.get_food_items_by_restaurant_id(api_token, user_type, restaurant_id)
        return(jsonify(food_items=food_items))

@app.route('/business/edit/food/', methods=['POST'])
def edit_food_item():
    if request.method == 'POST':
        zatiq_food_items = ZatiqFoodItemsMongoDBClient()
        jsonData = request.get_json()
        food_item_id = jsonData['food_item_id']
        api_token = jsonData['api_token']
        image = jsonData['image']
        overview = jsonData['overview']
        item_name = jsonData['item_name']
        tags = jsonData['tags']
        meat = jsonData['meat']
        seafood = jsonData['seafood']
        meal_type = jsonData['meal_type']
        item_price = jsonData['item_price']
        response = zatiq_food_items.update_food_item(api_token, food_item_id, image, overview, item_name, meal_type, tags, item_price, meat, seafood)
        return(jsonify(response=response[0], food_item_id=response[1]))

@app.route('/user/preferences/', methods=['POST'])
def update_user_preferences():
    if request.method == 'POST':
        zatiq_users = ZatiqUsersMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        user_preferences = jsonData['preferences']
        response = zatiq_users.update_user_preferences(api_token, user_preferences)
        return(jsonify(user_email=response[0], auth_token=response[1], user_name=response[2], preferences=response[3]))

@app.route('/business/delete/food/', methods=['POST'])
def delete_food_item():
    if request.method == 'POST':
        zatiq_food_items = ZatiqFoodItemsMongoDBClient()
        jsonData = request.get_json()
        food_item_id = jsonData['food_item_id']
        api_token = jsonData['api_token']
        response = zatiq_food_items.delete_food_item(api_token, food_item_id)
        return(jsonify(response=response))

@app.route('/search/<cuisine_type>/', methods=['POST'])
def search_food_items_by_cuisine_type(cuisine_type):
    if request.method == 'POST':
        zatiq_food_items = ZatiqUsersMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        user_type = jsonData['type'].lower()
        cuisine_type = cuisine_type.replace(' ', '_').lower()
        if cuisine_type in timely_meals:
            zatiq_food_items = ZatiqFoodItemsMongoDBClient()
            response = zatiq_food_items.get_food_items_by_time_of_day(api_token, cuisine_type, user_type)
            return(jsonify(food_items=response))
        elif cuisine_type in cuisine_types:
            zatiq_food_items = ZatiqFoodItemsMongoDBClient()
            response = zatiq_food_items.get_food_items_by_cuisine_type(api_token, cuisine_type, user_type)
            return(jsonify(food_items=response))
        elif cuisine_type in buttons:
            zatiq_food_items = ZatiqFoodItemsMongoDBClient()
            return(jsonify(response="Temporarily Unavailable"), 503)
        else:
            return('Could not find that category')

@app.route('/user/profile/', methods=['POST'])
def get_user_profile():
    if request.method == 'POST':
        zatiq_users = ZatiqUsersMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        response = zatiq_users.get_user_profile(api_token)
        if len(response) == 4:
            return(jsonify(user_email=response[0], auth_token=response[1], user_name=response[2], preferences=response[3]))
        elif len(response) == 3:
            return(jsonify(user_email=response[0], user_name=response[1], preferences=response[2]))
        else:
            return(jsonify(response=response))

@app.route('/user/menu/all/', methods=['POST'])
def get_restaurant_menu():
    if request.method == 'POST':
        zatiq_users = ZatiqUsersMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        restaurant_id = jsonData['restaurant_id']
        response = zatiq_users.get_menu_pictures(api_token, restaurant_id)
        return(jsonify(response=response))

@app.route('/user/interior/all/', methods=['POST'])
def get_restaurant_interior():
    if request.method == 'POST':
        zatiq_users = ZatiqUsersMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        restaurant_id = jsonData['restaurant_id']
        response = zatiq_users.get_interior_pictures(api_token, restaurant_id)
        return(jsonify(response=response))

@app.route('/find/restaurant/name/', methods=['POST'])
def get_restaurant_by_name():
    if request.method == 'POST':
        zatiq_users = ZatiqUsersMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        text = jsonData['text']
        response = zatiq_users.get_restaurant_by_name(api_token, text)
        return(jsonify(response=response))

@app.route('/food/grid/', methods=['POST'])
def get_food_grid():
    if request.method == 'POST':
        zatiq_food_items = ZatiqFoodItemsMongoDBClient()
        jsonData = request.get_json()
        api_token = jsonData['api_token']
        user_type = jsonData['type']
        response = zatiq_food_items.find_food_grid(api_token, user_type)
        return(jsonify(food_items=response))


