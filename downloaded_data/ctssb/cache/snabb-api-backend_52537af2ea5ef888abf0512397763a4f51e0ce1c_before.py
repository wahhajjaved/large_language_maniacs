from rest_framework import serializers
from .models import Quote, Task, Place
from snabb.address.serializers import AddressSerializer
from snabb.contact.serializers import ContactSerializer
from snabb.currency.serializers import CurrencySerializer


class QuoteSerializer(serializers.ModelSerializer):
    tasks = serializers.SerializerMethodField('tasks_info')
    currency = serializers.SerializerMethodField('currency_info')

    def tasks_info(self, obj):
        if obj.tasks:
            items = obj.tasks
            serializer = TaskSerializer(
                items, many=True, read_only=True)
            return serializer.data
        else:
            return None

    def currency_info(self, obj):
        if obj.tasks:
            try:
                task = obj.tasks.all().order_by('order')[:1][0]
                country = task.task_place.place_address.address_city.city_region.region_country
                currency = country.country_currency

                serializer = CurrencySerializer(
                    currency, many=False, read_only=True)
            except Exception as error:
                return None
            return serializer.data
        else:
            return None

        return serializer.data

    class Meta:
        model = Quote
        fields = (
            'quote_id',
            'distance', 'expire_at',
            'quote_user',
            'tasks',
            'prices',
            'currency',
            'created_at', 'updated_at'
        )


class TaskSerializer(serializers.ModelSerializer):
    place = serializers.SerializerMethodField('place_info')
    contact = serializers.SerializerMethodField('contact_info')
    dispatching_meta = serializers.SerializerMethodField('get_task_details')

    def get_task_details(self, obj):
        if obj.task_onfleet_id:
            details = obj.task_detail
            response = {}

            if 'trackingURL' in obj.task_detail:
                response['trackingURL'] = obj.task_detail['trackingURL']
            else:
                response['trackingURL'] = None

            if 'estimatedCompletionTime' in obj.task_detail:
                response['estimatedCompletionTime'] = obj.task_detail['estimatedCompletionTime']
            else:
                response['estimatedCompletionTime'] = None

            if 'state' in obj.task_detail:
                response['state'] = obj.task_detail['state']
            else:
                response['state'] = None
            return response
        else:
            return None

    def place_info(self, obj):
        if obj.task_place:
            items = obj.task_place
            serializer = PlaceSerializer(
                items, many=False, read_only=True)
            return serializer.data
        else:
            return None

    def contact_info(self, obj):
        if obj.task_contact:
            items = obj.task_contact
            serializer = ContactSerializer(
                items, many=False, read_only=True)
            return serializer.data
        else:
            return None

    class Meta:
        model = Task
        fields = (
            'task_id',
            'place',
            'contact',
            'order',
            'comments',
            'task_type',
            'dispatching_meta'
        )


class PlaceSerializer(serializers.ModelSerializer):
    address = serializers.SerializerMethodField('address_info')

    def address_info(self, obj):
        if obj.place_address:
            items = obj.place_address
            serializer = AddressSerializer(
                items, many=False, read_only=True)
            return serializer.data
        else:
            return None

    class Meta:
        model = Place
        fields = (
            'place_id',
            'description',
            'address'
        )
