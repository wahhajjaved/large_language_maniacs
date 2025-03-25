import os

import settings
from log import log
from client import DeepBlueClient


def get_key():
    """
    loads a previously obtained authentication key for
    epidb from the key file, defined in the settings.
    """
    if not get_key.key:
        if os.path.exists(settings.EPIDB_AUTHKEY_FILE):
            with open(settings.EPIDB_AUTHKEY_FILE, 'r') as f:
                for l in f.readlines():
                    (user, email, inst, key) = l.split(':')
                    if (user, email, inst) == (settings.EPIDB_POPULATOR_USER[0],
                                               settings.EPIDB_POPULATOR_USER[1],
                                               settings.EPIDB_POPULATOR_USER[2]):
                        get_key.key = key
                        return key

            log.info("Authentication key loaded")
        else:
            log.error("Authentication key file does not exist")
    else:
        return get_key.key
get_key.key = ""


class PopulatorEpidbClient(DeepBlueClient):
    def __init__(self):
        super(PopulatorEpidbClient, self).__init__(key=get_key(),
                                                   address=settings.DEEPBLUE_HOST,
                                                   port=settings.DEEPBLUE_PORT)