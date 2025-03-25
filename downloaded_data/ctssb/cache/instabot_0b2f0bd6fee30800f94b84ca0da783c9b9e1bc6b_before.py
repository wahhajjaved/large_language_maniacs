"""
    Function to calculate delays for like/follow/unfollow etc.
"""

import time
import random

def add_dispersion(delay_value):
    return delay_value * 3 / 4 + delay_value * random.random() / 2

def like_delay(bot):
    time.sleep(add_dispersion(bot.like_delay))

def follow_delay(bot):
    time.sleep(add_dispersion(bot.follow_delay))

def unfollow_delay(bot):
    time.sleep(add_dispersion(bot.unfollow_delay))

def comment_delay(bot):
    time.sleep(add_dispersion(bot.comment_delay))

def error_delay(bot):
    tile.sleep(300)
