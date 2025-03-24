from mongoengine import *
import bson
from zatiq_food_items import Zatiq_Food_Items
from zatiq_businesses import Zatiq_Businesses

class ZatiqFoodItemsMongoDBClient(object):
    def add_food_item(self, image, overview, item_name, api_token, meal_type, tags, item_price, meat, seafood):
        if self.check_valid_api_token(api_token) == True:
            restaurant = self.get_restaurant_id_by_api_token(api_token)
            food_item_id = self.generate_food_item_id()
            try:
                Zatiq_Food_Items.objects(id=food_item_id).update_one(restaurant_id=restaurant, item_name=item_name, image=image['base64'], image_aspect_ratio=image['image_aspect_ratio'], overview=overview, meal_type=meal_type, is_beverage=tags['is_beverage'], item_price=item_price,
                set__tags__indian=tags['indian'], set__tags__greek=tags['greek'], set__tags__chinese=tags['chinese'], set__tags__japanese=tags['japanese'], set__tags__korean=tags['korean'], set__tags__sushi=tags['sushi'], set__tags__dessert=tags['dessert'], set__tags__burger=tags['burger'], set__tags__pizza=tags['pizza'],
                set__tags__fast_food=tags['fast_food'], set__tags__halal=tags['halal'], set__tags__caribbean=tags['caribbean'], set__tags__mexican=tags['mexican'], set__tags__spicy=tags['spicy'], set__tags__fine_food=tags['fine_food'], set__tags__kosher=tags['kosher'], set__tags__healthy=tags['healthy'], set__tags__vegan=tags['vegan'], set__tags__vegetarian=tags['vegetarian'],
                set__tags__gluten_free=tags['gluten_free'], set__tags__italian=tags['italian'], set__tags__middle_eastern=tags['middle_eastern'], set__tags__snack=tags['snack'], set__tags__thai=tags['thai'], set__tags__canadian=tags['canadian'], set__tags__vietnamese=tags['vietnamese'], set__tags__has_nuts=tags['has_nuts'], set__tags__lactose_free=tags['lactose_free'],
                set__tags__meat__bear=meat['bear'], set__tags__meat__beef=meat['beef'], set__tags__meat__buffalo=meat['buffalo'], set__tags__meat__calf=meat['calf'], set__tags__meat__caribou=meat['caribou'], set__tags__meat__goat=meat['goat'], set__tags__meat__ham=meat['ham'], set__tags__meat__horse=meat['horse'], set__tags__meat__kangaroo=meat['kangaroo'], set__tags__meat__lamb=meat['lamb'], set__tags__meat__moose=meat['moose'], set__tags__meat__mutton=meat['mutton'], set__tags__meat__opossum=meat['opossum'],
                set__tags__meat__pork=meat['pork'], set__tags__meat__bacon=meat['bacon'], set__tags__meat__rabbit=meat['rabbit'], set__tags__meat__snake=meat['snake'], set__tags__meat__squirrel=meat['squirrel'], set__tags__meat__turtle=meat['turtle'], set__tags__meat__veal=meat['veal'], set__tags__meat__chicken=meat['chicken'], set__tags__meat__hen=meat['hen'], set__tags__meat__duck=meat['duck'], set__tags__meat__goose=meat['goose'],
                set__tags__meat__ostrich=meat['ostrich'], set__tags__meat__quail=meat['quail'], set__tags__meat__turkey=meat['turkey'], set__tags__seafood__clam=seafood['clam'], set__tags__seafood__pangasius=seafood['pangasius'], set__tags__seafood__cod=seafood['cod'], set__tags__seafood__crab=seafood['crab'], set__tags__seafood__catfish=seafood['catfish'], set__tags__seafood__alaska_pollack=seafood['alaska_pollack'], set__tags__seafood__tilapia=seafood['tilapia'], set__tags__seafood__salmon=seafood['salmon'], set__tags__seafood__tuna=seafood['tuna'],
                set__tags__seafood__shrimp=seafood['shrimp'], set__tags__seafood__lobster=seafood['lobster'], set__tags__seafood__eel=seafood['eel'], set__tags__seafood__trout=seafood['trout'], set__tags__seafood__pike=seafood['pike'], set__tags__seafood__shark=seafood['shark'], set__meal_type__breakfast=meal_type['breakfast'], set__meal_type__lunch=meal_type['lunch'], set__meal_type__dinner=meal_type['dinner'])
            except Exception as e:
                return("Error \n %s" % (e))
            new_food_item_id = str(Zatiq_Food_Items.objects(_id=food_item_id)[0].id)
            return({'image_id': new_food_item_id})
        else:
            return('Could not authenticate')

    def extract_food_tags(self, tags, meat, seafood):
        tags = {}
        pass

    def generate_food_item_id(self):
        food_item_id = bson.objectid.ObjectId()
        return(food_item_id)

    def get_food_by_tags(self, tags):
        pass

    def get_restaurant_id_by_api_token(self, api_token):
        valid_token = Zatiq_Businesses.objects(zatiq_token=api_token)
        if (len(valid_token) > 0):
            restaurant_id = valid_token[0].id
            return(restaurant_id)
        else:
            return(None)

    def get_food_items_by_restaurant_id(self, restaurant_id, api_token):
        if self.check_valid_api_token(api_token) == True:
            try:
                foods_by_restaurant = Zatiq_Food_Items.objects(restaurant_id=restaurant_id)
            except Exception as e:
                return("Error \n %s" % (e))
            if len(foods_by_restaurant) > 0:
                food_items_dict = self.generate_food_items_dict(foods_by_restaurant)
                
    def check_valid_api_token(self, api_token):
        valid_token = Zatiq_Businesses.objects(zatiq_token=api_token)
        if len(valid_token) > 0:
            return(True)
        else:
            return(False)

    def generate_food_items_dict(self, food_items):
        food_items_dict = {}
        for food_item in range(len(food_items)):
            restaurant_id = food_items[food_item].restaurant_id
            item_name = food_items[food_item].item_name
            overview = food_items[food_item].overview
            image = food_items[food_item].image
            image_aspect_ratio = food_items[food_item].image_aspect_ratio
            tags = food_items[food_item].overview
            photo_info = {'image_id': image_id, 'base64': base64, 'image_aspect_ratio': image_aspect_ratio}
            food_items_dict[photo] = photo_info
        return(food_items_dict)

    def generate_food_items_tags__dict(self, tags):
        tags__dict = {}
        for tag in range(len(tags)):
            pass
