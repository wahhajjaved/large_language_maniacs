from mongoengine import *
import secrets
import requests
import json
from zatiq_users import Zatiq_Users
from zatiq_food_items import Zatiq_Food_Items
from zatiq_menus import Zatiq_Menus
from zatiq_interiors import Zatiq_Interiors
from zatiq_businesses import Zatiq_Businesses

class ZatiqUsersMongoDBClient(object):
    def generate_zatiq_api_token(self):
        api_token = secrets.token_urlsafe(32)
        if (self.check_api_token_exists(api_token) == False):
            return(api_token)
        else:
            self.generate_zatiq_api_token()

    def get_user_id_by_api_token(self, api_token):
        valid_token = Zatiq_Users.objects(zatiq_token=api_token)
        if (len(valid_token) > 0):
            user_id = valid_token[0].id
            return(user_id)
        else:
            return(None)

    def check_valid_api_token(self, api_token):
        try:
            valid_token = Zatiq_Users.objects(zatiq_token=api_token)
        except Exception as e:
            return("Error \n %s" % (e))
        if len(valid_token) > 0:
            return(True)
        else:
            try:
                valid_token = Zatiq_Businesses.objects(zatiq_token=api_token)
            except Exception as e:
                return("Error \n %s" % (e))
            if len(valid_token) > 0:
                return(True)
            else:
                return(False)

    def check_api_token_exists(self, api_token):
        check_api_token = Zatiq_Users.objects(zatiq_token=api_token)
        if len(check_api_token) > 0:
            self.generate_zatiq_api_token()
        else:
            return(False)
    
    def check_user_exists(self, id, user_email, method, authToken):
        if method == "google":
            check_user_exists = Zatiq_Users.objects(google_id=id, user_email=user_email)
            if len(check_user_exists) > 0:
                update_user_auth_token = Zatiq_Users.objects(google_id=id).update_one(upsert=True, set__auth_token=authToken)
                return(True)
            else:
                return(False)

        if method == 'facebook':
            check_user_exists = Zatiq_Users.objects(facebook_id=id, user_email=user_email)
            if len(check_user_exists) > 0:
                update_user_auth_token = Zatiq_Users.objects(facebook_id=id).update_one(upsert=True, set__auth_token=authToken)
                return(True)
            else:
                return(False)
        
        if method != 'google' and method != 'facebook':
            return(False)
        
    def get_user_info(self, authToken, method):
        if method == 'facebook':
            user_info = requests.get('https://graph.facebook.com/me?fields=name,email&access_token='+authToken)
            return(user_info.json())

        if method == 'google':
            user_info = requests.get('https://www.googleapis.com/oauth2/v1/userinfo?access_token='+authToken)
            return(user_info.json())
        
        if method != 'google' and method != 'facebook':
            return('Could not authenticate')

    def get_user_profile(self, api_token):
        if not api_token:
            return('Could not authenticate')

        if self.check_valid_api_token(api_token) == True:
            if self.check_business_or_user(api_token) == 'user':
                try:
                    get_user_info = Zatiq_Users.objects(zatiq_token=api_token)
                except Exception as e:
                    return("Error \n %s" % (e))

                user_email = get_user_info[0].user_email
                auth_token = get_user_info[0].auth_token
                user_name = get_user_info[0].user_name
                preferences = self.generate_preferences_dict(get_user_info[0].preferences)
                return([user_email, auth_token, user_name, preferences])

            elif self.check_business_or_user(api_token) == 'business':
                try:
                    get_user_info = Zatiq_Users.objects(zatiq_token=api_token)
                except Exception as e:
                    return("Error \n %s" % (e))

                user_email = get_user_info[0].business_email
                user_name = get_user_info[0].business_name
                preferences = self.generate_preferences_dict(get_user_info[0].preferences)
                return([user_email, user_name, preferences])

            else:
                return('Could not find that user')
        else:
            return('Could not authenticate')

    def generate_preferences_dict(self, preferences):
        preferences_dict = {'halal': preferences.halal, 'spicy': preferences.spicy, 'kosher': preferences.kosher, 'healthy': preferences.healthy,
            'vegan': preferences.vegan, 'vegetarian': preferences.vegetarian, 'gluten_free': preferences.gluten_free, 'lactose_intolerant': preferences.lactose_free,
            'milk_allergy': preferences.milk_allergy, 'eggs_allergy': preferences.has_eggs, 'fish_allergy': preferences.fish_allergy, 'crustacean_allergy': preferences.crustacean_allergy, 'wheat_allergy': preferences.has_wheat, 'soybeans_allergy': preferences.has_soybeans,
            'treenuts_allergy': preferences.has_treenuts, 'peanuts_allergy': preferences.has_peanuts, 'jain': preferences.jain, 'omnivore': preferences.omnivore, 'pescatarian': preferences.pescatarian}
        return(preferences_dict)
    
    def user_login(self, authToken, userEmail, method):
        if not authToken:
            return('Could not authenticate')
        if not userEmail:
            return('Could not authenticate')

        check_user_login = Zatiq_Users.objects(user_email=userEmail)

        if len(check_user_login) > 0:
            user_info = self.get_user_info(authToken, method)
            user_name = user_info['name']
            user_email = user_info['email']
            api_token = check_user_login[0].zatiq_token
            return([user_name, user_email, api_token])
        else:
            return('Could not authenticate')
        
    def user_register(self, authToken, method, email):
        if not authToken:
            return('Could not authenticate')
        
        check_user_register = Zatiq_Users.objects(user_email=email)
        if len(check_user_register) > 0:
            return(self.user_login(authToken, email, method))
        else:
            user_info = self.get_user_info(authToken, method)
            user_id = user_info['id']
            user_email = user_info['email']
            user_name = user_info['name']
            api_token = self.generate_zatiq_api_token()

            if method == 'google':
                if self.check_user_exists(user_id, user_email, method, authToken) == False:
                    user_register = Zatiq_Users.objects(auth_token=authToken).update_one(upsert=True, set__user_email=user_email, set__user_name=user_name, set__google_id=user_id, set__zatiq_token=api_token,
                        set__preferences__halal=False, set__preferences__spicy=True, set__preferences__kosher=False, set__preferences__healthy=False, set__preferences__vegan=False, set__preferences__vegetarian=False,
                        set__preferences__gluten_free=False, set__preferences__lactose_free=False, set__preferences__milk_allergy=False, set__preferences__has_eggs=False,
                        set__preferences__fish_allergy=False, set__preferences__crustacean_allergy=False, set__preferences__has_wheat=False, set__preferences__has_soybeans=False, set__preferences__pescatarian=False, set__preferences__has_peanuts=False, set__preferences__has_treenuts=False,
                        set__preferences__jain=False, set__preferences__omnivore=False)
                    return(self.user_login(authToken, user_email, method))
                else:
                    return(self.user_login(authToken, user_email, method))

            if method == 'facebook':
                if self.check_user_exists(user_id, user_email, method, authToken) == False:
                    user_register = Zatiq_Users.objects(auth_token=authToken).update_one(upsert=True, set__user_email=user_email, set__user_name=user_name, set__facebook_id=user_id, set__zatiq_token=api_token,
                        set__preferences__halal=False, set__preferences__spicy=True, set__preferences__kosher=False, set__preferences__healthy=False, set__preferences__vegan=False, set__preferences__vegetarian=False,
                        set__preferences__gluten_free=False, set__preferences__lactose_free=False, set__preferences__milk_allergy=False, set__preferences__has_eggs=False,
                        set__preferences__fish_allergy=False, set__preferences__crustacean_allergy=False, set__preferences__has_wheat=False, set__preferences__has_soybeans=False, set__preferences__pescatarian=False, set__preferences__has_peanuts=False, set__preferences__has_treenuts=False,
                        set__preferences__jain=False, set__preferences__omnivore=False)
                    return(self.user_login(authToken, user_email, method))
                else:
                    return(self.user_login(authToken, user_email, method))

    def check_business_or_user(self, api_token):
        try:
            zatiq_user = Zatiq_Users.objects(zatiq_token=api_token)
        except Exception as e:
            return("Error \n %s" % (e))

        if len(zatiq_user) > 0:
            return('user')
        else:
            try:
                zatiq_user = Zatiq_Businesses.objects(zatiq_token=api_token)
            except Exception as e:
                return("Error \n %s" % (e))
            
            if len(zatiq_user) > 0:
                return('business')
            else:
                return('none')

    def update_user_preferences(self, api_token, preferences):
        if not api_token:
            return('Could not authenticate')
        
        if self.check_valid_api_token(api_token) == True:
            if self.check_business_or_user(api_token) == 'user':
                try:
                    Zatiq_Users.objects(zatiq_token=api_token).update_one(upsert=False,
                        set__preferences__halal=preferences['halal'], set__preferences__spicy=preferences['spicy'], set__preferences__kosher=preferences['kosher'], set__preferences__healthy=preferences['healthy'],
                        set__preferences__vegan=preferences['vegan'], set__preferences__vegetarian=preferences['vegetarian'], set__preferences__gluten_free=preferences['gluten_free'],
                        set__preferences__lactose_free=preferences['lactose_intolerant'], set__preferences__milk_allergy=preferences['milk_allergy'], set__preferences__has_eggs=preferences['eggs_allergy'],
                        set__preferences__fish_allergy=preferences['fish_allergy'], set__preferences__crustacean_allergy=preferences['crustacean_allergy'], set__preferences__has_wheat=preferences['wheat_allergy'], set__preferences__has_soybeans=preferences['soybeans_allergy'],
                        set__preferences__jain=preferences['jain'], set__preferences__omnivore=preferences['omnivore'], set__preferences__pescatarian=preferences['pescatarian'], set__preferences__has_peanuts=preferences['peanuts_allergy'], set__preferences__has_treenuts=preferences['treenuts_allergy'])
                except Exception as e:
                    return("Error \n %s" % (e))
                try:
                    get_user_info = Zatiq_Users.objects(zatiq_token=api_token)
                except Exception as e:
                    return("Error \n %s" % (e))
                user_email = get_user_info[0].user_email
                auth_token = get_user_info[0].auth_token
                user_name = get_user_info[0].user_name
                preferences = self.generate_preferences_dict(get_user_info[0].preferences)
                return([user_email, auth_token, user_name, preferences])
            elif self.check_business_or_user(api_token) == 'business':
                try:
                    Zatiq_Businesses.objects(zatiq_token=api_token).update_one(upsert=False,
                        set__preferences__halal=preferences['halal'], set__preferences__spicy=preferences['spicy'], set__preferences__kosher=preferences['kosher'], set__preferences__healthy=preferences['healthy'],
                        set__preferences__vegan=preferences['vegan'], set__preferences__vegetarian=preferences['vegetarian'], set__preferences__gluten_free=preferences['gluten_free'],
                        set__preferences__lactose_free=preferences['lactose_intolerant'], set__preferences__milk_allergy=preferences['milk_allergy'], set__preferences__has_eggs=preferences['eggs_allergy'],
                        set__preferences__fish_allergy=preferences['fish_allergy'], set__preferences__crustacean_allergy=preferences['crustacean_allergy'], set__preferences__has_wheat=preferences['wheat_allergy'], set__preferences__has_soybeans=preferences['soybeans_allergy'],
                        set__preferences__jain=preferences['jain'], set__preferences__omnivore=preferences['omnivore'], set__preferences__pescatarian=preferences['pescatarian'], set__preferences__has_peanuts=preferences['peanuts_allergy'], set__preferences__has_treenuts=preferences['treenuts_allergy'])
                except Exception as e:
                    return("Error \n %s" % (e))
                try:
                    get_user_info = Zatiq_Businesses.objects(zatiq_token=api_token)
                except Exception as e:
                    return("Error \n %s" % (e))
                user_email = get_user_info[0].business_email
                user_name = get_user_info[0].business_name
                preferences = self.generate_preferences_dict(get_user_info[0].preferences)
                return([user_email, user_name, preferences])
            else:
                return('Could not find that user')
        else:
            return('Could not authenticate')

    def get_menu_pictures(self, restaurant_id):
        try:
            menu_pictures = Zatiq_Menus.objects(restaurant_id=restaurant_id)
        except Exception as e:
            return("Error \n %s" % (e))
        result = self.generate_photos_dict(menu_pictures)
        return(result)

    def get_interior_pictures(self, restaurant_id):
        try:
            interior_pictures = Zatiq_Interiors.objects(restaurant_id=restaurant_id)
        except Exception as e:
            return("Error \n %s" % (e))
        result = self.generate_photos_dict(interior_pictures)
        return(result)

    def generate_photos_dict(self, photos):
        photos_list = []
        for photo in range(len(photos)):
            image_id = str(photos[photo].id)
            base64 = "http://167.99.177.29:5000/image/"+str(photos[photo].image)
            image_aspect_ratio = photos[photo].image_aspect_ratio
            photo_info = {'image_id': image_id, 'image': {
                'base64': base64, 'image_aspect_ratio': image_aspect_ratio}}
            photos_list.append(photo_info)
        return(photos_list)

    def get_restaurant_by_name(self, api_token, name):
        if not api_token:
            return('Could not authenticate')

        if self.check_valid_api_token(api_token) == True:
            try:
                restaurant_by_name = Zatiq_Businesses.objects.search_text(name)
            except Exception as e:
                return("Error \n %s" % (e))
            
            if len(restaurant_by_name) > 0:
                restaurant_info = self.generate_restaurants_list(restaurant_by_name)
                return(restaurant_info)
            else:
                return([])
        else:
            return('Could not authenticate')

    def get_nearby_restaurants(self, api_token):
        if not api_token:
            return('Could not authenticate')

        if self.check_valid_api_token(api_token) == True:
            try:
                zatiq_food_items = Zatiq_Businesses.objects()
            except Exception as e:
                return("Error \n %s" % (e))
            
            if len(zatiq_food_items) > 0:
                if len(zatiq_food_items) > 10:
                    restaurants = random.sample(zatiq_food_items, 10)
                    restaurants_list = self.generate_restaurants_list(restaurants)
                    return(restaurants_list)
                else:
                    restaurants_list = self.generate_restaurants_list(zatiq_food_items)
                    return(restaurants_list)
            else:
                return([])
        else:
            return('Could not authenticate')

    def generate_restaurants_list(self, restaurants):
        restaurant_list = []
        for restaurant in range(len(restaurants)):
            restaurant_id = restaurants[restaurant].id
            email = restaurants[restaurant].business_email
            name = restaurants[restaurant].business_name
            website = restaurants[restaurant].website
            hours = self.generate_business_hours(restaurants[restaurant].hours)
            number = restaurants[restaurant].number
            features = {'delivery': restaurants[restaurant].delivery, 'takeout': restaurants[restaurant].takeout, 'reservation': restaurants[restaurant].reservation, 'patio': restaurants[restaurant].patio, 'wheelchair_accessible': restaurants[restaurant].wheelchair_accessible, 'parking': restaurants[restaurant].parking, 'buffet': restaurants[restaurant].buffet, 'family_friendly': restaurants[restaurant].family_friendly, 'pescetarian_friendly': restaurants[restaurant].pescetarian_friendly, 'wifi': restaurants[restaurant].wifi}
            image = {'base64': "http://167.99.177.29:5000/image/"+str(restaurants[restaurant].image), 'image_aspect_ratio': restaurants[restaurant].image_aspect_ratio}
            address = restaurants[restaurant].address
            restaurant_info = {'restaurant_id': str(restaurant_id), 'email': email, 'name': name, 'website': website, 'hours': hours, 'number': number, 'features': features, 'image': image, 'address': address}
            restaurant_list.append(restaurant_info)
        return(restaurant_list)

    def generate_business_hours(self, business):
        hours_dict = {'start': {
            'monday': business.monday_start,
            'tuesday': business.tuesday_start,
            'wednesday': business.wednesday_start,
            'thursday': business.thursday_start,
            'friday': business.friday_start,
            'saturday': business.saturday_start,
            'sunday': business.sunday_start
        }, 'end': {
            'monday': business.monday_end,
            'tuesday': business.tuesday_end,
            'wednesday': business.wednesday_end,
            'thursday': business.thursday_end,
            'friday': business.friday_end,
            'saturday': business.saturday_end,
            'sunday': business.sunday_end
        }}
        return(hours_dict)
