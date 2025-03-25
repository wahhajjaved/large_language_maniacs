from bson.objectid import ObjectId
from util.Insert import insert_object
from model import Token


class User:
  def __init__(self, client, hash_method):
    self.collection = client.trainer_card.user
    self.token = Token(client)
    self.hash_method = hash_method
    self.create_keys = ['user_name', 'password', 'position', 'location_id']
    self.update_keys = ['password', 'score', 'stars', 'money',
                        'currency', 'position', 'location_id']
    self.admin_keys = ['user_name', 'trainer_number', 'level']

  def all(self):
    return self.collection.find()

  def find(self, user_id):
    if(isinstance(user_id, str)):
      user_id = ObjectId(user_id)
    return self.collection.find_one({'_id': user_id})

  def find_by_name(self, user_name):
    return self.collection.find_one({'user_name': user_name})

  def create(self, content):
    used = self.__user_name_used(content['user_name'])
    token = self.__check_token(content['token'])
    if used == False or token == False:
      return False
    insert = insert_object(self.create_keys, content, True)
    insert['password'] = self.hash_method.encrypt(insert['password'])
    insert['score'] = 0
    insert['stars'] = 0
    insert['money'] = 3000.0
    insert['level'] = token['level']
    insert['trainer_card'] = token['key']

    created = self.collection.insert_one(insert)
    new_user = self.find(created.inserted_id)
    self.token.update(token['_id'], {'used': True})
    new_user['goodies'] = token['goodies']
    return new_user

  def update(self, content, user_id, is_dev = False):
    if(is_dev):
      keys = list(set(self.update_keys) | set(self.admin_keys))
    else:
      keys = self.update_keys
    insert = insert_object(keys, content)
    if 'password' in insert:
      insert['password'] = self.hash_method.encrypt(insert['password'])
    resource = self.collection.update_one({'_id': ObjectId(user_id)},
                                          {'$set': insert})
    return resource

  def __user_name_used(self, name):
    check_user = self.collection.find_one({'user_name': name})
    if check_user == None:
      return True
    else:
      return False

  def __check_token(self, token_key):
    token = self.token.find(token_key)
    if token == None or token['used'] == True:
      return False
    else:
      return token
