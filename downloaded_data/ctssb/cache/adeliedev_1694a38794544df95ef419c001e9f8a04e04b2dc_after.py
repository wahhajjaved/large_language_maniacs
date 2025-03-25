from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from datetime import datetime

class BillingAddress(models.Model):
    country = models.CharField(max_length=100)
    addressOne = models.CharField(max_length=100)
    addressTwo = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    zipcode = models.CharField(max_length=10)
    user = models.ForeignKey(User)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class CreditCard(models.Model):
    name = models.CharField(max_length=200)
    cardNum = models.CharField(max_length=16)
    expirationMonth = models.CharField(max_length=2)
    expirationYear = models.CharField(max_length=4)
    cvc = models.CharField(max_length=5)
    user = models.ForeignKey(User)
    billingAddress = models.ForeignKey(BillingAddress)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ShippingAddress(models.Model):
    title = models.CharField(max_length=100)
    user = models.ForeignKey(User)
    name = models.CharField(max_length=100)
    addressOne = models.CharField(max_length=200)
    addressTwo = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now = True)

    def __unicode__(self):
        return self.title


class Order(models.Model):
    user = models.ForeignKey(User)
    creditCard = models.ForeignKey(CreditCard)
    shippingAddress = models.ForeignKey(ShippingAddress)
    billingAddress = models.ForeignKey(BillingAddress)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now = True)

    def __unicode__(self):
        return self.user.username

class Picture(models.Model):
    caption = models.TextField()
    picture = models.ImageField(upload_to='static/pictures/', null=False, blank=False)
    main = models.BooleanField()

    def __unicode__(self):
        return self.caption

class Product(models.Model):
    name = models.TextField(max_length=100)
    price = models.FloatField()
    description = models.TextField()
    tagLine = models.TextField()
    startTime = models.DateTimeField()
    endTime = models.DateTimeField()
    shipDate = models.DateField()
    credited = models.BooleanField(default=False)
    pictures = models.ManyToManyField(Picture)
    orders = models.ManyToManyField("Order")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now = True)

    def __unicode__(self):
        return self.title

    def is_ready(self):
        return len(self.pictures.all()) > 0

    def is_active(self):
        return (self.startTime <= timezone.now() and self.endTime >= timezone.now())

    def is_upcoming(self):
        return self.startTime >= timezone.now()

    def is_past(self):
        return self.endTime <= timezone.now()

    def is_upcoming_show(self):
        delta = self.startTime.astimezone(timezone.utc).replace(tzinfo=None) - datetime.now()
        return self.startTime <= timezone.now() and delta.days <= 0

    def is_upcoming_hide(self):
        delta = self.startTime.astimezone(timezone.utc).replace(tzinfo=None) - datetime.now()
        return self.startTime <= timezone.now() and delta.days >= 0

class CartItem(models.Model):
    user = models.ForeignKey(User)
    product = models.ForeignKey(Product)
    quantity = models.IntegerField()

class Cart(models.Model):
    user = models.ForeignKey(User)
    checkedOut = models.BooleanField(default=False)
    items = models.ManyToManyField(CartItem)


class Credit(models.Model):
    user = models.ForeignKey(User)
    credit = models.FloatField()
    used = models.FloatField(default=0)
    tier = models.IntegerField()
    product = models.ForeignKey(Product)
    order = models.ForeignKey(Order)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class TrafficType(models.Model):
    name = models.CharField(max_length=100)

class ProductArrivalType(models.Model):
    name = models.CharField(max_length=100)

class Arrival(models.Model):
    user = models.ForeignKey(User, null=True)
    traffic_type = models.ForeignKey(TrafficType, null=True)
    ip = models.CharField(max_length=255, null=True)
    user_agent = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ProductView(models.Model):
    user = models.ForeignKey(User, null=True)
    product_arrival_type = models.ForeignKey(ProductArrivalType, null=True)
    product = models.ForeignKey(Product)
    arrival = models.ForeignKey(Arrival)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
