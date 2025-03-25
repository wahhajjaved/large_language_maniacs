"""Factory functions for creating application object graph"""
from webclient import WebClient
from parsers import Parser
from taskmaster import TaskMaster
from scraper import Scraper


class ObjectBuilder(object):
    def make_tracker_scraper(self):
        return Scraper(WebClient(), Parser())

    def make_taskmaster(self):
        return TaskMaster()
