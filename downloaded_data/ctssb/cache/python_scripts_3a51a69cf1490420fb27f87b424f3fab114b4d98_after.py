#!/usr/bin/env python3

#
# Scrape recipes from pepperplate.com.
#

import requests
from bs4 import BeautifulSoup
import lxml.html
import json
import time
import getpass
import re
import os

class pepperplate_recipe:
    def __init__(self, id, html):
        self.id = id
        self.soup = BeautifulSoup(html)

    def get_id(self):
        return self.id

    def get_title(self):
        return self.soup.find(id='cphMiddle_cphMain_lblTitle').get_text().strip()

    def get_new_body(self):
        new_soup = BeautifulSoup('<html><head></head><body></body></html>')

        thumb = self.get_thumbnail()
        if thumb:
            hdr = new_soup.new_tag('img')

            hdr['src'] = './img/{}'.format(self.id + '.jpg')
            new_soup.body.append(hdr)

        #Title
        title = self.get_title()
        hdr = new_soup.new_tag('title')
        hdr.append(title)
        new_soup.head.append(hdr)
    
        hdr = new_soup.new_tag('h1')
        hdr.append(title)
        new_soup.body.append(hdr)

        #source
        source = self.soup.find(id='cphMiddle_cphMain_hlSource')
        if source:
            new_soup.body.append(source)

        #ingredients
        hdr = new_soup.new_tag('h3')
        hdr.append('Ingredients')
        new_soup.body.append(hdr)
    
        item = self.soup.find('ul', {'class':'inggroups'})
        if item:
            new_soup.body.append(item)
        else:
            new_soup.body.append('No ingedients listed')

        #instructions 
        hdr = new_soup.new_tag('h3')
        hdr.append('Instructions')
        new_soup.body.append(hdr)
    
        item = self.soup.find('ol', {'class':'dirgroupitems'})
        if item:
            new_soup.body.append(item)
        else:
            new_soup.body.append('No instructions listed')

        #Notes 
        hdr = new_soup.new_tag('h3')
        hdr.append('Notes')
        new_soup.body.append(hdr)
    
        notes = self.soup.find(id="cphMiddle_cphMain_lblNotes")
        if notes:
            hdr = new_soup.new_tag('pre')
            hdr.append(notes.get_text())
            new_soup.append(hdr)
    
        return new_soup.prettify('latin-1')
    
    def get_thumbnail(self):
        tmp = self.soup.find(id='cphMiddle_cphMain_imgRecipeThumb')
        if tmp:
            return tmp['src']
        else:
            return None

class pepperplate:

    def __init__(self, hostname):
        self.hostname = hostname
        self.last_page = False
        self.session = requests.Session()

    def set_username(self, username):
        self.username = username

    def set_password(self, password):
        self.password = password

    def login(self):
        if self.username == None or self.password == None:
            print('No login details supplied')
            return False

        url = 'https://{}/login.aspx'.format(self.hostname)
        headers = {"User-Agent":"Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2062.120 Safari/537.36"}

        self.session.headers.update(headers)
        r = self.session.get(url)

        login_page = lxml.html.fromstring(r.content)
        VIEWSTATE = login_page.xpath('//input[@id="__VIEWSTATE"]/@value')[0]
        EVENTVALIDATION = login_page.xpath('//input[@id="__EVENTVALIDATION"]/@value')[0]
    
        login_data={"__VIEWSTATE":VIEWSTATE,
        "__EVENTVALIDATION":EVENTVALIDATION,
        "__EVENTARGUMENT":'',
        "__EVENTTARGET":'ctl00$cphMain$loginForm$ibSubmit',
        "ctl00$cphMain$loginForm$tbEmail":self.username,
        "ctl00$cphMain$loginForm$tbPassword":self.password,
        "ctl00$cphMain$loginForm$cbRememberMe":'on'
        }

        r = self.session.post(url, data=login_data)
        if r.url != 'http://{}/recipes/default.aspx'.format(self.hostname):
            print('Login failure')
            return False

        return True


    def get_page(self, page):

        url = 'http://{}/recipes/default.aspx/GetPageOfResults'.format(self.hostname)
        parameters = json.dumps({'pageIndex':page,
                                 'pageSize':20,
                                 'sort':4,
                                 'tagIds': [],
                                 'favoritesOnly':0})

        headers={'Referer':'http://{}/recipes/default.aspx'.format(self.hostname)
                         ,'Content-Type': 'application/json'
                         ,'X-Requested-With': 'XMLHttpRequest'
                         ,'DNT':'1'
                         ,'Accept': 'application/json, text/javascript, */*; q=0.01'
                         ,'Accept-Language': 'en,de;q=0.7,en-US;q=0.3'
                         ,'Accept-Encoding': 'gzip, deflate'}
        r = self.session.request('POST', url, data=parameters, headers=headers)

        page = lxml.html.fromstring(r.json()['d'])
        self.page = [re.findall(r'id=(\d+)', a)[0] for a in page.xpath('//div[@class="item"]/p/a/@href')]
        self.last_page = len(self.page) < 20 

        return self.page

    def get_recipe(self, id):
        url = 'http://{}/recipes/view.aspx?id={}'.format(self.hostname, id)
        r = self.session.request('GET', url)
        return r.content

    def get_url(self, url):
        r = requests.get(url)
        return r.content

    def is_last_page(self):
        return self.last_page

    def is_logged_in(self):
        return self.session != None

def save_recipe(recipe, savepath):
    filename = recipe.get_title().replace('/','_').replace('"', '').replace(':','').replace(' ','_')
    with open(savepath + '/{}.{}.html'.format(filename, recipe.get_id()), 'wb') as f:
        f.write(recipe.get_new_body())

def save_file(img, savepath):
    with open(savepath, 'wb') as f:
        f.write(img)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Scrape recipies from Pepperplate')
    parser.add_argument('username', help='Username to log in with')
    parser.add_argument('password', nargs="?", default=None, help='Password to log in with. If not provided on the command line it will be requested by the program')
    parser.add_argument('directory', nargs="?", default='recipes', help='Directory to which download everything. defaults to "recipes"')
    args = parser.parse_args()

    if not args.password:
        args.password = getpass.getpass('Please enter the password for account {}: '.format(args.username))

    imgpath = os.path.join(args.directory, 'img', '{}')
    if not os.path.exists(imgpath.format("")):
        os.makedirs(imgpath, exist_ok = True)

    pp = pepperplate('www.pepperplate.com')
    pp.set_username(args.username)
    pp.set_password(args.password)

    if not pp.login():
        exit(1)

    page = 0

    while not pp.is_last_page():
        print('Downloading page {}'.format(page+1))
        for id in pp.get_page(page):
            time.sleep(1) #sleep 1 second between requests to not mash the server
            recipe = pepperplate_recipe(id, pp.get_recipe(id))
            print('Downloaded {}'.format(recipe.get_title()))
            save_recipe(recipe, args.directory)

            if recipe.get_thumbnail():
                save_file(pp.get_url(recipe.get_thumbnail()), imgpath.format(id + '.jpg'))

        page += 1
