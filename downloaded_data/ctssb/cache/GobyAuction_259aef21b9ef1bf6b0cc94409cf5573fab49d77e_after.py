import bs4
from urllib.parse import urldefrag, urljoin, urlparse
import urllib
import os
import requests
import collections
import sqlite3
import SqlHandler
import shutil


class WebScraper:

    keywords = []
    link_to_website = ""
    pages_to_scrape = 0
    link_to_database = "../data/web_items.db"
    
    def __init__(self):
        pass

    def scrape_site(self):
        pass
    
    def add_keywords(self, keywords):
        self.keywords = keywords
  
    def set_pages_to_scrape(self, pages):
        self.pages_to_scrape = pages
 
    def scape_site(self):
        pass

    def download_thumbnails(self, item_list):
        if not os.path.exists('../data/images/'):
            os.makedirs('../data/images')
        if not os.path.exists('../data/images_temp'):
            os.makedirs('../data/images_temp')
        for item in item_list:
            if item is not None:
                image_path = "../data/images/" + str(item[0]) + ".jpg"
                temp_image_path = "../data/images_temp/" + str(item[0]) + ".jpg"
                image_url = item[4]
                try:
                    if(os.path.isfile(image_path) is not True):
                        print(image_url + " downloading...")
                        urllib.request.urlretrieve(image_url, temp_image_path)
                    else:
                        print(image_url + " found")
                        shutil.move(image_path, temp_image_path)
                except ValueError:
                    print("Invalid URL")
                    
        # Move temp folder and delete old images
        self.delete_thumbnails()
        shutil.move('../data/images_temp', '../data/images')

    def delete_thumbnails(self):
        shutil.rmtree('../data/images')

        
class Item:

    description = ""
    price = 0
    image_link = ""
    link_to_item = ""
    
    def __init__(self, description, price, image_link, link_to_item):
        self.description = description
        self.price = price
        self.image_link = image_link
        self.link_to_item = link_to_item

        
class Ebay(WebScraper):

    link_to_website = "https://www.ebay.co.uk/"
    
    def scrape_site(self):
        # Put list of keywords into a string
        concatinated_keywords = ""
        for keyword in self.keywords:
            concatinated_keywords += keyword + "+"
            
        # Remove last "+" from end of string
        concatinated_keywords = concatinated_keywords[:-1]
        print(concatinated_keywords)

        pagequeue = collections.deque()
        # Create the ebay links
        for i in range(self.pages_to_scrape):
            
            pagequeue.append(self.link_to_website +
                             "sch/i.html?_from=R40&_trksid="
                             "p2380057.m570.l1313.TR0.TRC0.H0.X"
                             + concatinated_keywords + ".TRS0&_nkw="
                             + concatinated_keywords + "&_sacat=" + str(i))
        pages_crawled = 0
        pages_failed = 0
        print(pagequeue[0])

        # Initialise the session
        sess = requests.session()
        while pages_crawled < self.pages_to_scrape:
            url = pagequeue.popleft()

            # Read the page
            try:
                response = sess.get(url)
            except (requests.exceptions.MissingSchema,
                    requests.exceptions.InvalidSchema):
                print("FAILED:", url)
                pages_failed += 1
                continue
            
            if not response.headers['content-type'].startswith('text/html'):
                # Don't crawl non-HTML content
                continue
            pages_crawled += 1
            
            soup = bs4.BeautifulSoup(response.text, "html.parser")
            # Parse HTML
            self.page_parser(soup)

    def page_parser(self, soup):
        # Find main item area
        itemList = soup.find('div', {'id': 'ResultSetItems'})
        # Find individual Items
        items = itemList.find_all('li', {'class':
                                         ['sresult lvresult clearfix li shic',
                                          'sresult lvresult clearfix li']})
        for item in items:
            
            item_id = item.get('listingid')
            
            title = item.find('h3', {'class': 'lvtitle'}).find('a').contents[0]
            
            if str(title) == "<span class=\"newly\">New listing</span>":
                title = item.find('h3', {'class':
                                         'lvtitle'}).find('a').contents[1]
                title.strip()
                
            price = item.find('span', {'class':
                                       'bold'}).contents[0].strip()
            image_container = item.find('div', {'class':
                                                'lvpicinner full-width picW'})
            item_link = image_container.find('a', href=True)['href']
            
            image_link = image_container.find('img').get('src')
            
            purchase_type = ""
            if item.find('span', {'title': 'Buy it now'}) is not None:
                purchase_type = "Buy it Now"
            else:
                purchase_type = "Bid"

            SqlHandler.add_to_database(self.link_to_database, str(item_id),
                                       str(title), str(price),
                                       str(item_link), str(image_link),
                                       str(purchase_type), "eBay")
        
