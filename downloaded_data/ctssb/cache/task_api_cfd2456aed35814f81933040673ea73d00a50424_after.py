#!/usr/bin/env python
#coding=utf-8
#file Name: books_client.py
#author: mew7wo
#mail: mew7wo@gmail.com
#created Time: Sun 24 Mar 2013 11:11:40 PM CST


import os
import json
import requests
import logging
from fetch import Fetch


class BooksTask:
    ''' get books '''

    def __init__(self):
        self.__reset()
        self.__read_info()
        self._fetch = Fetch(username='1398882026@qq.com', pw='liumengchao')
        self._tasks_url = 'http://localhost:8080/id/books/'
        self._url = 'https://api.douban.com/v2/book/user/%s/collections?count=%d&start=%d'
        self._upload_url = 'http://localhost:8080/upload/'
        logging.basicConfig(filename='books_error.log', filemod='a+', level=logging.ERROR)

    def __del__(self):
        self.__save_info()

    def __reset(self):
        self._status = 'free'
        self._free_tasks = set()
        self._done_tasks = set()

    def __read_info(self):
        if os.path.exist('books_task_config.cfg'):
            with open('books_task_config.cfg', 'r') as f:
                cfg = json.loads(f.read())
                self._status = cfg.get('status')
                self._free_tasks = set(cfg.get('free_tasks'))
                self._done_tasks = set(cfg.get('free_tasks'))


    def __save_info(self):
        with open('books_task_config.cfg', 'w') as f:
            cfg = {}
            cfg['status'] = self._status
            cfg['free_tasks'] = list(self._free_tasks)
            cfg['done_tasks'] = list(self._done_tasks)
            f.write(json.dumps(cfg))

    def __get_tasks(self):
        if self._status == 'free':
            resp = requests.get(self._tasks_url)
            js = resp.json()
            self._free_tasks = set(js.get('tasks'))
            self._status = 'running'


    def __do_tasks(self):
        with open('books.txt', 'a') as f:
            for t in self._free_tasks:
                if t not in self._done_tasks:
                    books = self.__get_books(t)
                    obj = {'_id':t, 'books':books}
                    f.write(json.dumps(obj) + '\n')
                     

    def __get_books(self, user):
        books = []
        count = 100
        for i in range(500):
            content = self._fetch.get(self._url % (user, count, i*count))
            js = json.loads(content)
            books.extend(js.get('collections'))
            if (i+1)*count >= js.get('total'):
                break

        return books


    def __upload_tasks(self):
        tasks = {'type':'books', 'data':[]}
        with open('books.txt', 'r') as f:
            for line in f:
                obj = json.loads(line.rstrip('\n'))
                tasks['data'].append(obj)

        while True:
            data = json.dumps(tasks)
            headers = {'Content-type':'application/json; charset=utf8'}
            resp = requests.put(self._upload_url, data=data, headers=headers)
            js = resp.json()
            if js.get('code') == 200:
                self.__reset()
                os.remove('books.txt')
                break

    def run(self):
        while True:
            try:
                self.__get_tasks()
                self.__do_tasks()
                self.__upload_tasks()
            except KeyboardInterrupt:
                break
            except Exception, e:
                logging.error(repr(e))
