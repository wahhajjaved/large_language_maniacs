# -*- coding: utf-8 -*-

import os
import datetime
import scrapy
import webcrawler.items as items
from tika import tika, parser
from scrapy.exceptions import DropItem
from scrapy.utils.project import get_project_settings
from scrapy.pipelines.images import ImagesPipeline
from scrapy.pipelines.files import FilesPipeline
from webcrawler.models import Document

tika.ServerHost = get_project_settings().get('TIKA_SERVER_HOST')
tika.TikaClientOnly = True


class ImageParser(ImagesPipeline):

    def item_completed(self, results, item, info):
        # @todo: implement
        raise scrapy.exceptions.NotConfigured


class FileParser(FilesPipeline):

    def item_completed(self, results, item, info):
        # @todo: implement
        raise scrapy.exceptions.NotConfigured


class WebPageParser(object):

    def process_item(self, item, spider):
        '''
        Takes an instance of webcrawler.items.Item and parses the content using Tika RestAPI
        Returns an instance of webcrawler.items.Parsed
        '''
        if not isinstance(item, items.WebPage):
            return item

        try:
            parsed = parser.from_file(item['temp_filename'])

            return items.Parsed(
                url=item['url'],
                links=item['external_urls'],
                text=parsed.get('content', ''),
                meta=parsed['metadata']
            )

        except:
            spider.logger.warning(
                'Failed to parse content of "{}"'.format(item['url'])
            )
        finally:
            # delete the temporary file
            os.remove(item['temp_filename'])

        raise DropItem


class Indexer(object):
    '''
    Stores the contents of crawled web pages/documents in the database with
    their associated Full Text Search index
    '''

    def process_item(self, item, spider):
        '''
        Takes an instance of webcrawler.items.Parsed generates a full text search Index
        for the content and persists the index and metadata
        '''
        if not isinstance(item, items.Parsed):
            return item

        try:
            doc_fields = Document.get_fields_from_tika_metadata(item['meta'])
            doc_fields['text'] = item['text']
            doc_fields['url'] = item['url']
            doc_fields['crawl_date'] = datetime.datetime.now()
            doc_fields['links'] = item['external_urls']

            Document.create(**doc_fields)

        except:
            spider.logger.exception(
                'Failed to index url and metadata for {}'.format(item['url']))

        raise DropItem
