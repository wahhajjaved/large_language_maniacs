#!/usr/bin/env python
# coding=utf-8

__author__ = 'qingfeng'

plugins = {}


class Hook(object):

    @staticmethod
    def listen(hook_str=None, message=None):
        if hook_str in plugins.keys():
            hook_list = plugins[hook_str]
            if isinstance(hook_list, list):
                for i in hook_list:
                    module = __import__(hook_list[i])
                    result = module.run(message)
                    if result:
                        return result
        else:
            return False
