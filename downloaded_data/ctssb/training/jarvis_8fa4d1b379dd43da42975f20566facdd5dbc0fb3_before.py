import redis
import os
import sdk

r = redis.StrictRedis(host=sdk.config.state.host,
                      port=sdk.config.state.port, db=0)

def load(appname, state):
    """Loads app state from Jarvis into |state|.

    Returns:
        Flag indicating whether or not a saved state was found.
    """
    msg_str = r.get(appname)
    if msg_str:
        state.ParseFromString(msg_str)
        return True

    return False

def update(appname, new_state):
    msg_str = state.SerializeToString()
    r.set(appname, msg_str)
