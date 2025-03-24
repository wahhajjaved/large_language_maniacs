from django.db import models
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _
from django.db.models.signals import post_save
from django.utils import timezone as datetime

from dateutil.relativedelta import relativedelta

from .fields import ResourceField
from .helpers import get_payer
from .compat import User, update_fields
from .tasks import sync_resource, sync_amount
from .api import handler

from . import settings

from leetchi import resources
from leetchi.base import DoesNotExist


class ApiModel(models.Model):
    class Meta:
        abstract = True

    @property
    def resource_id(self):
        return getattr(self, '%s_id' % self.Api.resource_field)

    def sync(self, async=False, commit=True):
        if not hasattr(self, 'Api'):
            return False

        if async is False:

            field_name = self.Api.resource_field

            if self.resource_id is not None:
                return False

            parameters = self.request_parameters()

            resource = self._meta.get_field(field_name).to(**parameters)
            resource.save(handler)

            setattr(self, field_name, resource)

            if commit:
                update_fields(self, fields=(field_name, ))

            return True

        self.save(sync=False)

        sync_resource.delay(self.__class__, self.pk)

    def save(self, *args, **kwargs):
        sync = kwargs.pop('sync', settings.ALWAYS_SYNC)

        if sync is True:
            self.sync(commit=False)

        return super(ApiModel, self).save(*args, **kwargs)


class BaseLeetchi(ApiModel):
    object_id = models.PositiveIntegerField()
    content_object = generic.GenericForeignKey('content_type', 'object_id')
    content_type = models.ForeignKey(ContentType)
    creation_date = models.DateTimeField(default=datetime.now)

    class Meta:
        abstract = True

    def get_tag(self):
        return u'%s.%s:%d' % (self.content_type.app_label,
                              self.content_type.model,
                              self.object_id)


class ContributionQuerySet(models.query.QuerySet):
    def success(self):
        return self.filter(is_success=True)

    def refundable(self):
        now = datetime.now()

        qs = self.filter(creation_date__gt=now - relativedelta(months=10))

        qs = qs.filter(models.Q(card_expiration_date__isnull=True) | models.Q(card_expiration_date__gt=now))

        return qs


class ContributionManager(models.Manager):
    def get_query_set(self):
        return ContributionQuerySet(self.model)

    def success(self):
        return self.get_query_set().success()

    def refundable(self):
        return self.get_query_set().refundable()


class Contribution(BaseLeetchi):
    TYPE_PAYLINE = 1
    TYPE_OGONE = 2
    TYPE_CHOICES = (
        (TYPE_PAYLINE, 'Payline'),
        (TYPE_OGONE, 'Ogone'),
    )

    contribution = ResourceField(resources.Contribution, null=True)
    wallet = ResourceField(resources.Wallet)
    amount = models.IntegerField()
    user = models.ForeignKey(User)
    client_fee_amount = models.IntegerField(default=0)
    return_url = models.CharField(null=True, blank=True, max_length=255)
    template_url = models.CharField(null=True, blank=True, max_length=255)
    payment_url = models.CharField(null=True, blank=True, max_length=255)
    is_completed = models.BooleanField(default=False)
    is_success = models.BooleanField(default=False)
    type = models.PositiveSmallIntegerField(choices=TYPE_CHOICES,
                                            default=TYPE_PAYLINE,
                                            verbose_name=_('Type'),
                                            db_index=True)
    card_expiration_date = models.DateField(null=True)
    card_number = models.CharField(max_length=100, null=True)
    culture = models.CharField(max_length=5, null=True)

    objects = ContributionManager()

    class Meta:
        db_table = 'leetchi_contribution'

    class Api:
        resource_field = 'contribution'

    def __init__(self, *args, **kwargs):
        super(Contribution, self).__init__(*args, **kwargs)

        self.target = None

    @property
    def real_amount(self):
        return self.amount / 100.0

    def request_parameters(self):
        user = get_payer(self.user)

        user_id = user.get_pk()

        if self.target:
            user = get_payer(self.target)

        data = {
            'user_id': user_id,
            'amount': self.amount,
            'client_fee_amount': self.client_fee_amount,
            'return_url': self.return_url,
            'wallet_id': self.wallet_id,
            'tag': self.get_tag(),
            'template_url': self.template_url
        }

        if self.type:
            data['type'] = self.get_type_display()

        if self.culture:
            data['culture'] = self.culture

        if self.template_url:
            data['template_url'] = self.template_url

        return data

    def sync_status(self, commit=True):
        contribution = self.contribution

        if contribution.is_success():
            self.is_success = True
            self.is_completed = True

        elif contribution.is_completed and not contribution.is_succeeded:
            self.is_success = False
            self.is_completed = True

        try:
            payment_card = self.contribution.detail_payment_card
        except DoesNotExist:
            pass
        else:
            if payment_card:
                expiration_date = payment_card.expiration_date_converted

                if expiration_date:
                    self.card_expiration_date = expiration_date

                self.card_number = payment_card.number

        if commit:
            self.save()

    def is_error(self):
        return not self.is_success and self.is_completed

    def sync(self, *args, **kwargs):
        result = super(Contribution, self).sync(*args, **kwargs)

        if result:
            self.payment_url = self.contribution.payment_url

            self.sync_status(commit=True)


class Transfer(BaseLeetchi):
    transfer = ResourceField(resources.Transfer, null=True)
    beneficiary_wallet = ResourceField(resources.Wallet)
    payer = models.ForeignKey(User, related_name='payers')
    beneficiary = models.ForeignKey(User, related_name='beneficiaries')
    amount = models.IntegerField()

    class Meta:
        db_table = 'leetchi_transfer'

    class Api:
        resource_field = 'transfer'

    @property
    def user_id(self):
        return self.payer_id

    @property
    def user(self):
        return self.payer

    def request_parameters(self):
        payer = get_payer(self.payer)

        beneficiary = get_payer(self.beneficiary)

        return {
            'payer_id': payer.get_pk(),
            'beneficiary_id': beneficiary.get_pk(),
            'tag': self.get_tag(),
            'amount': self.amount,
            'beneficiary_wallet_id': self.beneficiary_wallet_id
        }


class TransferRefund(BaseLeetchi):
    transfer_refund = ResourceField(resources.TransferRefund, null=True)
    transfer = models.ForeignKey(Transfer)
    user = models.ForeignKey(User)

    class Meta:
        verbose_name = 'transferrefund'
        db_table = 'leetchi_transferrefund'

    class Api:
        resource_field = 'transfer_refund'

    def request_parameters(self):
        user = get_payer(self.user)

        return {
            'user_id': user.get_pk(),
            'transfer_id': self.transfer.transfer_id,
            'tag': self.get_tag()
        }


class Refund(BaseLeetchi):
    user = models.ForeignKey(User)
    refund = ResourceField(resources.Refund, null=True)
    contribution = models.ForeignKey(Contribution)
    is_success = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)

    class Api:
        resource_field = 'refund'

    class Meta:
        db_table = 'leetchi_refund'

    def request_parameters(self):
        return {
            'user_id': get_payer(self.user).get_pk(),
            'contribution_id': self.contribution.contribution_id,
            'tag': self.get_tag()
        }

    def get_contribution(self):
        return self.contribution.contribution

    def sync_status(self, commit=True):
        refund = self.refund

        changed = False

        if refund.is_success():
            changed = True
            self.is_success = True
            self.is_completed = True

        elif refund.is_completed and not refund.is_succeeded:
            changed = True
            self.is_success = False
            self.is_completed = True

        if commit and changed:
            update_fields(self, fields=('is_success', 'is_completed',))

    def sync(self, *args, **kwargs):
        result = super(Refund, self).sync(*args, **kwargs)

        if result:
            self.sync_status(commit=False)


class Beneficiary(ApiModel):
    user = models.ForeignKey(User)
    beneficiary = ResourceField(resources.Beneficiary, null=True)
    bank_account_owner_name = models.CharField(max_length=255)
    bank_account_owner_address = models.CharField(max_length=255)
    bank_account_iban = models.CharField(max_length=100)
    bank_account_bic = models.CharField(max_length=100)
    creation_date = models.DateTimeField(default=datetime.now)

    class Meta:
        db_table = 'leetchi_beneficiary'

    class Api:
        resource_field = 'beneficiary'

    def request_parameters(self):
        return {
            'user': get_payer(self.user),
            'bank_account_bic': self.bank_account_bic,
            'bank_account_iban': self.bank_account_iban,
            'bank_account_owner_address': self.bank_account_owner_address,
            'bank_account_owner_name': self.bank_account_owner_name
        }


class Withdrawal(BaseLeetchi):
    amount = models.IntegerField(help_text=_(u'Amount to transfer (in cents, ex: 51900)'),
                                 null=True)
    client_fee_amount = models.IntegerField(help_text=_(u'Amount to transfer with tax (ex: 4152 = 51900 * 8%)'),
                                            null=True)
    beneficiary = models.ForeignKey(Beneficiary, null=True, blank=True)

    withdrawal = ResourceField(resources.Withdrawal, null=True)

    user = models.ForeignKey(User, null=True, blank=True)
    wallet = ResourceField(resources.Wallet, null=True, blank=True)

    is_completed = models.BooleanField(default=False)
    is_succeeded = models.BooleanField(default=False)

    class Api:
        resource_field = 'withdrawal'

    class Meta:
        db_table = 'leetchi_withdrawal'

    @property
    def real_amount(self):
        if not self.amount:
            return 0

        return self.amount / 100.0

    @property
    def is_success(self):
        return self.is_succeeded

    def sync_status(self, commit=True):
        withdrawal = self.withdrawal

        changed = False

        for field_name in ('is_succeeded', 'is_completed', ):
            if getattr(self, field_name) == getattr(withdrawal, field_name):
                continue

            setattr(self, field_name, getattr(withdrawal, field_name))

            changed = True

        if commit and changed:
            update_fields(self, fields=('is_succeeded', 'is_completed', ))

    def request_parameters(self):
        params = {
            'beneficiary_id': self.beneficiary.beneficiary_id,
            'client_fee_amount': self.client_fee_amount or 0,
            'amount': self.amount
        }

        if self.user_id:
            user = get_payer(self.user)

            params['user'] = user

        if self.wallet_id:
            params['wallet'] = self.wallet

        return params


class WalletManager(models.Manager):
    def get_for_model(self, instance):
        try:
            content_type = ContentType.objects.get_for_model(instance)
            return (self.filter(content_type=content_type,
                                object_id=instance.pk)
                    .order_by('creation_date')[0])
        except IndexError:
            return None

    def contribute_to_class(self, cls, name):
        post_save.connect(self.post_save, sender=Contribution)
        post_save.connect(self.post_save, sender=Transfer)
        post_save.connect(self.post_save, sender=TransferRefund)
        post_save.connect(self.post_save, sender=Refund)
        post_save.connect(self.post_save, sender=Withdrawal)
        return super(WalletManager, self).contribute_to_class(cls, name)

    def post_save(self, instance, **kwargs):
        if instance.user_id:
            wallet = self.get_for_model(instance.user)

            if wallet:
                sync_amount.apply_async((wallet.pk, ), countdown=120)


class Wallet(BaseLeetchi):
    user = ResourceField(resources.User, null=True, blank=True)
    wallet = ResourceField(resources.Wallet, null=True, blank=True)
    amount = models.IntegerField(null=True, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)

    objects = WalletManager()

    class Meta:
        unique_together = (
            ('wallet', 'content_type', 'object_id'),
        )
        db_table = 'leetchi_wallet'

    def sync_amount(self, commit=True, async=False):
        if async is True:
            return sync_amount.delay(self.pk)

        user = self.user

        self.amount = user.personal_wallet_amount
        self.last_synced = datetime.now()

        if commit:
            update_fields(self, fields=('amount', 'last_synced', ))

    @property
    def real_amount(self):
        if not self.amount:
            return 0

        return self.amount / 100.0


class StrongAuthentication(ApiModel):
    strong_authentication = ResourceField(resources.StrongAuthentication, null=True)

    user = models.ForeignKey(User)
    beneficiary = models.ForeignKey(Beneficiary,
                                    related_name='strong_authentication',
                                    null=True, blank=True)

    is_completed = models.BooleanField(default=False)
    is_succeeded = models.BooleanField(default=False)
    creation_date = models.DateTimeField(default=datetime.now)

    class Meta:
        db_table = 'leetchi_strongauthentication'

    class Api:
        resource_field = 'strong_authentication'

    def request_parameters(self):
        beneficiary = None

        if self.beneficiary:
            beneficiary = self.beneficiary.beneficiary_id

        return {
            'user': get_payer(self.user),
            'beneficiary_id': beneficiary
        }


def get_pending_amount(user):
    result = (Withdrawal.objects.filter(user=user, is_completed=False)
              .aggregate(amount=models.Sum('amount')))

    amount = result.get('amount', 0) or 0

    result = (Refund.objects.filter(user=user, is_completed=False)
              .aggregate(amount=models.Sum('contribution__amount')))

    amount += result.get('amount', 0) or 0

    return amount
