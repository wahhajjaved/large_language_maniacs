# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey has `on_delete` set to the desired behavior.
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models

from datetime import datetime, date, timedelta
import json
import pytz


class Region(models.Model):
    name = models.CharField('Region name', unique=True, max_length=255)

    class Meta:
        managed = False
        db_table = 'region'
        verbose_name = 'Region'
        verbose_name_plural = 'Regions'

    def __str__(self):
        return self.name


class City(models.Model):
    city_id = models.AutoField(primary_key=True)
    city_name = models.CharField('City name', unique=True, max_length=255)
    capital_growth = models.IntegerField(blank=True, null=True)
    council_link = models.TextField(blank=True, null=True)
    region = models.ForeignKey('Region', models.CASCADE)

    class Meta:
        managed = False
        db_table = 'city'
        verbose_name = 'City'
        verbose_name_plural = 'Cities'

    def __str__(self):
        return self.city_name


class Suburb(models.Model):
    city = models.ForeignKey(City, models.CASCADE)
    name = models.CharField(unique=True, max_length=255)

    class Meta:
        managed = False
        db_table = 'suburb'
        verbose_name = 'Suburb'
        verbose_name_plural = 'Suburbs'

    def __str__(self):
        return self.name


class PricingMethod(models.Model):
    name = models.CharField(unique=True, max_length=255)

    class Meta:
        managed = False
        db_table = 'pricing_method'
        verbose_name = 'Pricing method'
        verbose_name_plural = 'Pricing methods'

    def __str__(self):
        return self.name


class PropertyType(models.Model):
    name = models.CharField(unique=True, max_length=255)

    class Meta:
        managed = False
        db_table = 'property_type'
        verbose_name = 'Property type'
        verbose_name_plural = 'Property types'

    def __str__(self):
        return self.name


class House(models.Model):
    house_id = models.AutoField(primary_key=True)
    street_name = models.CharField(max_length=255)
    street_number = models.CharField(max_length=255)
    suburb = models.ForeignKey('Suburb', models.CASCADE)
    bedrooms = models.IntegerField(blank=True, null=True)
    bathrooms = models.IntegerField(blank=True, null=True)
    ensuite = models.BooleanField()
    land = models.FloatField('Land area', blank=True, null=True)
    floor = models.IntegerField('Floor area', blank=True, null=True)
    car_spaces = models.IntegerField(blank=True, null=True)
    property_type = models.ForeignKey('PropertyType', models.CASCADE)
    price = models.IntegerField(blank=True, null=True)
    price_type = models.ForeignKey('PricingMethod', models.CASCADE)
    auction_time = models.DateTimeField(blank=True, null=True)
    description = models.CharField(max_length=8192, blank=True, null=True)
    government_value = models.IntegerField(blank=True, null=True)
    government_rates = models.IntegerField(blank=True, null=True)
    government_to_price = models.DecimalField(max_digits=10, decimal_places=5, blank=True, null=True)
    photos = models.CharField(max_length=16384, blank=True, null=True)
    url = models.TextField(blank=True, null=True)
    source_id = models.IntegerField(blank=True, null=True)
    additional_data = models.CharField(max_length=2048, blank=True, null=True)
    property_id = models.CharField(max_length=16, blank=True, null=True)
    listing_create_date = models.DateField(blank=True, null=True)
    create_time = models.DateTimeField('Created at')
    agency_link = models.CharField(max_length=1024, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'house'
        verbose_name = 'House'
        verbose_name_plural = 'Houses'
        unique_together = (('street_name',
                            'street_number',
                            'suburb',
                            'bedrooms',
                            'bathrooms',
                            'price'),)

    def __str__(self):
        """String view of house object"""
        house = House.objects.values(
            'street_number',
            'street_name',
            'suburb__name',
            'suburb__city__city_name',
            'suburb__city__region__name'
        ).get(house_id=self.house_id)

        return '{} {}, {}, {}, {}'.format(
            house['street_number'],
            house['street_name'],
            house['suburb__name'],
            house['suburb__city__city_name'],
            house['suburb__city__region__name']
        )

    def get_address(self):
        """Returns address of house."""
        address = '{} {}'.format(self.street_number, self.street_name)
        if address == ' ':
            return None
        return address
    get_address.short_description = 'Address'

    def get_city(self):
        """Returns city of house."""
        return self.suburb.city
    get_city.short_description = 'City'

    def get_region(self):
        """Returns region of house."""
        return self.suburb.city.region
    get_region.short_description = 'Region'

    def get_property_type(self):
        """Returns property type with bedrooms of house."""
        return '{} bedrooms {}'.format(self.bedrooms, self.property_type)
    get_property_type.short_description = 'Property Type'

    def get_price(self):
        """Returns price with price method of house."""
        if self.price:
            return '{} {}'.format(self.price, self.price_type)
        return self.price_type
    get_price.short_description = 'Price'


class OpenHomes(models.Model):
    house = models.ForeignKey(House, models.CASCADE)
    date_from = models.DateTimeField()
    date_to = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'open_homes'
        unique_together = (('house', 'date_from', 'date_to'),)


class VHousesForTables(models.Model):
    """Model for v_houses_for_tables view."""
    house_id = models.BigIntegerField(primary_key=True)
    suburb_name = models.CharField(max_length=255)
    suburb = models.ForeignKey('Suburb', models.DO_NOTHING)
    city_name = models.CharField(max_length=255)
    region_name = models.CharField(max_length=255)
    street_name = models.CharField(max_length=255)
    street_number = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    price = models.IntegerField()
    price_type = models.ForeignKey('PricingMethod', models.DO_NOTHING)
    price_with_price_type = models.CharField(max_length=255)
    government_value = models.IntegerField()
    government_to_price = models.DecimalField(max_digits=10, decimal_places=5)
    bedrooms = models.IntegerField()
    bathrooms = models.IntegerField()
    land = models.FloatField()
    floor = models.IntegerField()
    property_type = models.ForeignKey('PropertyType', models.DO_NOTHING)
    property_type_full = models.CharField(max_length=255)
    description = models.CharField(max_length=8192)
    car_spaces = models.IntegerField()
    ensuite = models.BooleanField()
    listing_create_date = models.DateField()
    photos = models.CharField(max_length=16384, blank=True, null=True)
    open_homes_from = models.DateTimeField()
    open_homes_to = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'v_houses_for_tables'

    @staticmethod
    def get_new_houses(filters, excluded_pks):
        """Returns queryset with new houses by user's filters."""
        queryset = None

        # getting querysets for each filter and merge them in one queryset
        for f in filters:
            filter_data = json.loads(f.filter_data_json)
            houses = VHousesForTables.objects.values(
                'house_id',
                'suburb_name',
                'city_name',
                'region_name',
                'address',
                'price',
                'price_with_price_type',
                'listing_create_date',
                'photos',
                'address',
                'property_type_full',
            ).filter(
                suburb__in=filter_data['suburbs'],
                price__range=(filter_data['price_from'][0], filter_data['price_to'][0]),
                price_type__in=filter_data['pricing_methods'],
                government_value__range=(
                    filter_data['government_value_from'][0], filter_data['government_value_to'][0]
                ),
                government_to_price__range=(
                    filter_data['government_value_to_price_from'][0], filter_data['government_value_to_price_to'][0]
                ),
                bedrooms__range=(filter_data['bedrooms_from'][0], filter_data['bedrooms_to'][0]),
                bathrooms__range=(filter_data['bathrooms_from'][0], filter_data['bathrooms_to'][0]),
                land__range=(filter_data['landarea_from'][0], filter_data['landarea_to'][0]),
                floor__range=(filter_data['floorarea_from'][0], filter_data['floorarea_to'][0]),
                property_type__in=filter_data['property_type'],
                description__contains=filter_data['keywords'][0],
                car_spaces__range=(filter_data['carspace_from'][0], filter_data['carspace_to'][0]),
                listing_create_date__range=[
                    date.today() + timedelta(days=-int(filter_data['listings_age_days'][0])),
                    date.today()
                ],
            ).exclude(
                house_id__in=excluded_pks
            )
            if filter_data.get('show_only_properties_with_address'):
                houses = houses.filter(
                    street_name__isnull=False,
                    street_number__isnull=False
                ).exclude(
                    street_name='',
                    street_number=''
                )
            if filter_data.get('ensuite'):
                houses = houses.filter(ensuite=True)
            if filter_data.get('show_only_open_homes'):
                now = datetime.now()
                houses = houses.filter(
                    open_homes_from__gte=datetime(now.year, now.month, now.day, tzinfo=pytz.UTC),
                    open_homes_to__lte=datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=pytz.UTC),
                )
            if queryset:
                queryset = queryset | houses
            else:
                queryset = houses

        if queryset:
            return queryset.distinct()
        return []

    @staticmethod
    def search(filters):
        """Search houses by filters."""
        houses = VHousesForTables.objects.values(
            'house_id',
            'suburb_name',
            'city_name',
            'region_name',
            'address',
            'listing_create_date',
            'photos',
            'address',
            'property_type_full',
            'price_with_price_type'
        ).filter(
            price__range=(filters['price_from'], filters['price_to']),
            bedrooms__range=(filters['bedrooms_from'], filters['bedrooms_to']),
            bathrooms__range=(filters['bathrooms_from'], filters['bathrooms_to']),
            land__range=(filters['landarea_from'], filters['landarea_to']),
            floor__range=(filters['floorarea_from'], filters['floorarea_to']),
            description__contains=filters['keywords'],
            listing_create_date__range=[
                date.today() + timedelta(days=-int(filters['listings_age_days'])),
                date.today()
            ],
        )
        if filters.get('suburbs'):
            houses = houses.filter(suburb_id__in=filters.getlist('suburbs'))
        if filters.get('pricing_methods'):
            houses = houses.filter(price_type_id__in=filters.getlist('pricing_methods'))
        if filters.get('property_type'):
            houses = houses.filter(property_type_id__in=filters.getlist('property_type'))
        if filters.get('show_only_properties_with_address'):
            houses = houses.filter(
                street_name__isnull=False,
                street_number__isnull=False
            ).exclude(
                street_name='',
                street_number=''
            )
        if filters.get('show_only_open_homes'):
            now = datetime.now()
            houses = houses.filter(
                open_homes_from__gte=datetime(now.year, now.month, now.day, tzinfo=pytz.UTC),
                open_homes_to__gte=datetime(now.year, now.month, now.day, 23, 59, 59, tzinfo=pytz.UTC),
            )

        return houses.distinct()


class Agency(models.Model):
    agency_id = models.AutoField(primary_key=True)
    agency_name = models.CharField(unique=True, max_length=255)
    city = models.ForeignKey('City', models.DO_NOTHING)
    email = models.CharField(blank=True, null=True, max_length=255)
    work_phone = models.CharField(blank=True, null=True, max_length=255)
    houses = models.ManyToManyField(House, db_table='agencyhouse')

    def __str__(self):
        return self.agency_name

    class Meta:
        managed = False
        db_table = 'agency'
        verbose_name = 'Agency'
        verbose_name_plural = 'Agencies'


class Agent(models.Model):
    agent_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    mobile_phone = models.CharField(blank=True, null=True, max_length=255)
    ddi_phone = models.CharField(blank=True, null=True, max_length=255)
    work_phone = models.CharField(blank=True, null=True, max_length=255)
    email = models.CharField(blank=True, null=True, max_length=255)
    agency = models.ForeignKey(Agency, models.DO_NOTHING)
    houses = models.ManyToManyField(House, db_table='agenthouse')

    def __str__(self):
        return '{} ({})'.format(self.name, self.email)

    class Meta:
        managed = False
        db_table = 'agent'
        verbose_name = 'Agent'
        verbose_name_plural = 'Agents'
        unique_together = (('name', 'agency'),)
