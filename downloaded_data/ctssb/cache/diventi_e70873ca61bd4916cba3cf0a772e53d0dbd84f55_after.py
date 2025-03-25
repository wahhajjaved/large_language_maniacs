from django.shortcuts import render
from django.views.generic.detail import DetailView
from django.views.generic.edit import UpdateView

from .models import Product


class ProductDetailView(DetailView):

    model = Product
    context_object_name = 'product'

    # Returns only published products
    def get_queryset(self):
        qs = super(ProductDetailView, self).get_queryset()
        return qs.published()


class ProductUpdateView(UpdateView):
    model = Product
    context_object_name = 'product'

    def update_collection(self):
        pass