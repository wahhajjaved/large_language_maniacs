import requests

import config
from agent.HAHQConfigurator import HAHQConfigurator


class HAHQConfigPoster(object):
    def __init__(self, config_string):
        self.config_data = HAHQConfigurator(config_string=config_string).get_config_data()

    def push_config(self, url, token):
        requests.post(url, json=self.config_data)


if __name__ == "__main__":
    with open(config.HA_PROXY_CONFIG_PATH, 'r') as config_file:
        config_pusher = HAHQConfigPoster(config_file.read())
        config_pusher.push_config(
            config.SERVER_URL,
            config.AGENT_TOKEN
        )
