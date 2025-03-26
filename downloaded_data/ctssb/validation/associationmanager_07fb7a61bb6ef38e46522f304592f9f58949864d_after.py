from django.db import models
from django.db.models import Q
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.generic import GenericRelation

from django.contrib.contenttypes import generic

from associates.models import Associate


class BaseModel(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    date_last_modified = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Event(BaseModel):
    '''
    '''
    title_de = models.CharField(max_length=511)
    title_en = models.CharField(max_length=511)

    date_from = models.DateField()
    date_until = models.DateField()

    slug = models.SlugField(unique=True)

    description_de = models.TextField(blank=True, null=True)
    description_en = models.TextField(blank=True, null=True)

    schedule_de = models.TextField(blank=True, null=True)
    schedule_en = models.TextField(blank=True, null=True)

    show_event = models.BooleanField(default=True)

    event_part_set_price_map_json = models.CharField(max_length=255,
            blank=True, null=True)

    def __str__(self):
        return self.title_en


class Purchase(BaseModel):
    '''
    '''
    associate = models.ForeignKey(Associate)
    associate_message = models.TextField(blank=True, null=True)

    paypal_ipn_log = models.TextField(blank=True, null=True)

    PENDING_PAYMENT_STATUS = 0
    ELAPSED_PAYMENT_STATUS = 1
    PAYPAL_FAILED_PAYMENT_STATUS = 2
    PAID_BY_CASH_PAYMENT_STATUS = 3
    PAID_BY_PAYPAL_PAYMENT_STATUS = 4
    PAID_BY_BANK_TRANSFER_PAYMENT_STATUS = 5

    PAYMENT_STATUS_CHOICES = (
            (PENDING_PAYMENT_STATUS, 'pending'),
            (ELAPSED_PAYMENT_STATUS, 'elapsed'),
            (PAYPAL_FAILED_PAYMENT_STATUS, 'payment failed paypal'),
            (PAID_BY_CASH_PAYMENT_STATUS, 'paid by cash'),
            (PAID_BY_PAYPAL_PAYMENT_STATUS, 'paid by paypal'),
            (PAID_BY_BANK_TRANSFER_PAYMENT_STATUS, 'paid by bank transfer'),
            )

    payment_status = models.SmallIntegerField(choices=PAYMENT_STATUS_CHOICES,
            default=0)
    payment_due_by = models.DateField(blank=True, null=True)

    @property
    def pid(self):
        return 'PId-'+str(self.pk)

    def one_line_description(self):
        items = self.purchaseitem_set.all()
        s = u'Purchase Number {pk} :: '.format(pk=self.pk)
        if len(items) > 0:
            for obj in self.purchaseitem_set.all():
                s += u'| {obj} |'.format(
                        obj=obj.content_object.one_line_description())
        else:
            s += u'Purchase without items!!'
        return s

    def balance_due(self):
        balance = 0
        for i in self.purchaseitem_set.all():
            balance += i.content_object.price
        return balance

    def pretty_print(self, language='en'):
        summary = 40*'* '+'\n'
        pis = self.purchaseitem_set.all()
        for pi in pis:
            summary += pi.content_object.pretty_print(language=language)
        summary += 40*'* '+'\n'
        if language == 'en':
            summary += 'Price: '+str(self.balance_due())+'.- sFr.\n'
        elif language == 'de':
            summary += 'Preis: '+str(self.balance_due())+'.- sFr.\n'
        summary += 40*'* '

        return summary.encode('utf-8') + '\n'


class PurchaseItem(BaseModel):
    '''
    '''
    ITEM_TYPE_CHOICES = Q(app_label='events', model='article') |\
            Q(app_label='events', model='registration') 
    content_type = models.ForeignKey(generic.ContentType,
            limit_choices_to=ITEM_TYPE_CHOICES)
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey('content_type', 'object_id')
    
    purchase = models.ForeignKey(Purchase)

    @property
    def price(self):
        return self.content_object.price

    @property
    def payment_status(self):
        return self.purchase.payment_status

    def get_payment_status_display(self):
        return self.purchase.get_payment_status_display()

    def one_line_description(self, language='en'):
        obj_desr = self.content_object.one_line_description(language=language)
        s =  u'{descr} :: {ass}'.format(
                descr=obj_desr,
                ass=self.purchase.associate,)
        return s


class EventPart(BaseModel):
    '''
    '''
    event = models.ForeignKey(Event)

    datetime_from = models.DateTimeField()
    datetime_until = models.DateTimeField()

    short_description_de = models.CharField(max_length=511)
    short_description_en = models.CharField(max_length=511)

    is_bookable = models.BooleanField()
    max_no_participants = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = (
                ('event', 'short_description_en'),
                ('event', 'short_description_de')
                )

    def __str__(self):
        return self.event.title_en + ' : ' + self.short_description_en

    def no_eventparts_assigned(self):
        regs = self.registration_set.all()
        regs_assigned = []
        for reg in regs:
            if reg.payment_status in [
                Purchase.PENDING_PAYMENT_STATUS,
                Purchase.PAID_BY_BANK_TRANSFER_PAYMENT_STATUS,
                Purchase.PAID_BY_PAYPAL_PAYMENT_STATUS,
                Purchase.PAID_BY_CASH_PAYMENT_STATUS,
                ]:
                regs_assigned.append(reg)
        return len(regs_assigned)

    def no_items_assigned(self):
        return self.no_eventparts_assigned()

    def still_available(self):
        no_reg = self.no_eventparts_assigned()
        return  no_reg < self.max_no_participants

    def percent_full(self):
        reg = float(self.no_eventparts_assigned())
        maxav = float(self.max_no_participants)
        return int(100*reg/maxav)

    def no_available_places(self):
        return self.max_no_participants - self.no_eventparts_assigned()

    def pretty_time(self):
        prettytime = '{tfrom} - {tuntil}'.format(
                tfrom=self.datetime_from.strftime('%H:%M'),
                tuntil=self.datetime_until.strftime('%H:%M'),
                )
        return prettytime.encode('utf-8')

    def pretty_print(self, language='de'):
        if language == 'de':
            s =  u'%s : %s' % (self.short_description_de, self.pretty_time())
        else:
            s =  u'%s : %s' % (self.short_description_en, self.pretty_time())
        return s


class Registration(BaseModel):
    '''
    '''
    associate = models.ForeignKey(Associate)
    event_parts = models.ManyToManyField(EventPart)
    price = models.PositiveSmallIntegerField(blank=True, null=True)

    purchase_items = GenericRelation(PurchaseItem)

    def one_line_description(self, language='de'):
        if language == 'de':
            s = u'Registration ({pk}) : {fn} {ln}'.format(
                    pk=self.pk,
                    fn=self.associate.first_name,
                    ln=self.associate.last_name)
        else:
            s = u'Registration ({pk}) : {fn} {ln}'.format(
                    pk=self.pk,
                    fn=self.associate.first_name,
                    ln=self.associate.last_name)
        return s

    ## FIXME
    @property
    def payment_status(self):
        return self.purchase_item.payment_status

    def get_payment_status_display(self):
        return self.purchase_item.get_payment_status_display()
    
    @property
    def purchase_item(self):
        pis = self.purchase_items.all()
        if len(pis) == 0:
            return None
        if len(pis) > 1:  
            raise DB_Inconsistency_Error(('Too many PurchaseItems for '
                    'Registration with pk='+str(self.pk)))
        else:
            return pis[0]

    def pretty_print(self, language='de'):
        for i, ep in enumerate(self.event_parts.all()):
            if i == 0:
                s = ep.event.title_de if language == 'de' else ep.event.title_en
                s += '\n'
                s += len(s)*'-'
            if language == 'de':
                s += '\n'+ep.short_description_de + ' : ' + ep.pretty_time()
            else:
                s += '\n'+ep.short_description_en + ' : ' + ep.pretty_time()
        s += '\n'
        return s.encode('utf-8') 
 

class Article(BaseModel):
    '''
    '''
    name_de = models.CharField(max_length=255)
    name_en = models.CharField(max_length=255)

    description_de = models.TextField(null=True, blank=True)
    description_en = models.TextField(null=True, blank=True)

    # might come in handy at a later stage
#   article_image = models.ImageField(upload_to='articles', blank=True,
#           null=True)

    events = models.ManyToManyField(Event, blank=True, null=True)

    is_sold = models.BooleanField(default=True)
    price = models.PositiveSmallIntegerField()
    no_articles_initially = models.PositiveSmallIntegerField()

    purchase_items = GenericRelation(PurchaseItem)

    def __str__(self):
        return u'%s' % self.one_line_description()

    def one_line_description(self, language='de'):
        if language == 'de':
            s = u'%s' % self.name_de
        else:
            s = u'%s' % self.name_en
        return s

    def no_articles_assigned(self):
        '''
        Purchase of PurchaseItem has
        payment_status 'pending', 'paid_by_xxx', ' 
        '''
        pis = self.purchase_items.all() 
        pis_assigned = []
        for pi in pis:
            if pi.payment_status in [
                    Purchase.PENDING_PAYMENT_STATUS,
                    Purchase.PAID_BY_PAYPAL_PAYMENT_STATUS,
                    Purchase.PAID_BY_BANK_TRANSFER_PAYMENT_STATUS,
                    Purchase.PAID_BY_CASH_PAYMENT_STATUS,
                    ]:
                pis_assigned.append(pi)
        return len(pis)

    def no_items_assigned(self):
        return self.no_articles_assigned()

    def no_articles_available(self):
        return self.no_articles_initially - self.no_articles_assigned()

    def still_available(self):
        return self.no_articles_assigned() < self.no_articles_initially

    def pretty_print(self, language='de'):
        if language == 'de':
            s = self.name_de + '\n'
        else:
            s = self.name_en + '\n'
        return s.encode('utf-8')



class DB_Inconsistency_Error(Exception):
    pass
