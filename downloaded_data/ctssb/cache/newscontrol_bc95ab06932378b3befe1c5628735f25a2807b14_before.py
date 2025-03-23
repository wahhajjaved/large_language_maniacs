from google.appengine.api import users
from model import User

def create_user(google_user):
    user = User(
        google_user=google_user,
    )
    user.put()
    return user

def get_current_user_model():
    return get_user_model_for(users.get_current_user())

def get_user_model_for(google_user=None):
    return User.all().filter('google_user =', google_user).get()

def get_user_model_by_id_or_nick(id_or_nick):
    if id_or_nick.isdigit():
        return User.get_by_id(int(id_or_nick))
    else:
        return User.all().filter('nickname_lower = ', id_or_nick.lower()).get()