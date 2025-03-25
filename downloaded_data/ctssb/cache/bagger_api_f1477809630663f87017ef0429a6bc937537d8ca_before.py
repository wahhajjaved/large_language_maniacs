#!/usr/bin/python
# -*- coding: utf-8 -*-

import appier

import models

class CategoryController(appier.Controller):

    @appier.route("/categories.json", "GET")
    def list(self):
        skip = self.get_field("skip", 0, cast = int)
        limit = self.get_field("limit", 5, cast = int)
        categories = models.Category.find(skip = skip, limit = limit, map = True)
        return categories

    @appier.route("/categories/<int:id>.png", "GET")
    def image(self, id):
        path = "resources/images/category%d.png" % id
        file = open(path, "rb")
        try: data = file.read()
        finally: file.close()
        return data

    @appier.route("/categories/<int:category>/products.json", "GET")
    def list_products(self, category):
        skip = self.get_field("skip", 0, cast = int)
        limit = self.get_field("limit", 25, cast = int)
        products = models.Product.find(
            category_id = category,
            skip = skip,
            limit = limit
        )
        return products
