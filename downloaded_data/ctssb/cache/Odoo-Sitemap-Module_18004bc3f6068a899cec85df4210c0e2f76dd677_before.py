# -*- coding: utf-8 -*-
import logging
from openerp.osv import osv
from openerp import fields, models
from openerp.http import request

logger = logging.getLogger(__name__)


class Sitemap(osv.osv):

    _inherit = 'website'

    def enumerate_pages(self, cr, uid, ids, query_string=None, context=None):

        pages = super(Sitemap, self).enumerate_pages(cr, uid, ids, query_string, context)

        visible_pages = []
        sitemap_model = request.env['website_sitemap.extended']

        for page in pages:
            sitemap_info = sitemap_model.search([('location', '=', page['loc'])])

            if not sitemap_info:
                sitemap_model.create({
                    'location': page['loc'],
                    'name': page['loc'],
                })

            if not sitemap_info or sitemap_info.sitemap_visible:
                visible_pages.append(page)

        return visible_pages


class SitemapExtended(models.Model):

    _name = 'website_sitemap.extended'

    name = fields.Char(string="Title")
    location = fields.Char(string="Location")
    sitemap_visible = fields.Boolean(string="Visible in Sitemap", default=True)
