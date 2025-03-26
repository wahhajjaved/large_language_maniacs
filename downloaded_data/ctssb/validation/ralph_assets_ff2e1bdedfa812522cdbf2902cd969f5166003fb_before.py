#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import re
import time

from ajax_select.fields import AutoCompleteSelectField, AutoCompleteField
from bob.forms import Dependency, DependencyForm, REQUIRE, SHOW
from django.forms import (
    BooleanField,
    CharField,
    ChoiceField,
    DateField,
    FileField,
    Form,
    IntegerField,
    ModelForm,
    ValidationError,
)
from django.forms.widgets import HiddenInput, Textarea
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _
from mptt.forms import TreeNodeChoiceField
from ralph_assets.models import (
    Asset,
    AssetCategory,
    AssetCategoryType,
    AssetSource,
    AssetStatus,
    AssetType,
    DeviceInfo,
    OfficeInfo,
    PartInfo,
)
from ralph.ui.widgets import DateWidget, ReadOnlyWidget


LOOKUPS = {
    'asset_model': ('ralph_assets.models', 'AssetModelLookup'),
    'asset_dcdevice': ('ralph_assets.models', 'DCDeviceLookup'),
    'asset_bodevice': ('ralph_assets.models', 'BODeviceLookup'),
    'asset_warehouse': ('ralph_assets.models', 'WarehouseLookup'),
    'asset_manufacturer': ('ralph_assets.models', 'AssetManufacturerLookup'),
    'ralph_device': ('ralph_assets.models', 'RalphDeviceLookup'),

}


class ModeNotSetException(Exception):
    pass


class BarcodeField(CharField):
    def to_python(self, value):
        return value if value else None


class BulkEditAssetForm(ModelForm):
    '''
        Form model for bulkedit assets, contains column definition and
        validadtion. Most important are sn and barcode fields. When you type
        sn you can place many sn numbers separated by pressing enter.
        Barcode count must be the same like sn count.
    '''
    class Meta:
        model = Asset
        fields = (
            'type', 'model', 'warehouse', 'device_info', 'invoice_no',
            'invoice_date', 'order_no', 'sn', 'barcode', 'price',
            'deprecation_rate', 'support_price', 'support_period',
            'support_type', 'support_void_reporting', 'provider',
            'source', 'status', 'task_url', 'request_date', 'delivery_date',
            'production_use_date', 'provider_order_date', 'production_year',
        )
        widgets = {
            'request_date': DateWidget(),
            'delivery_date': DateWidget(),
            'invoice_date': DateWidget(),
            'production_use_date': DateWidget(),
            'provider_order_date': DateWidget(),
            'device_info': HiddenInput(),
        }
    barcode = BarcodeField(max_length=200, required=False)
    source = ChoiceField(
        choices=AssetSource(),
    )
    model = AutoCompleteSelectField(
        LOOKUPS['asset_model'],
        required=True,
        plugin_options=dict(
            add_link='/admin/ralph_assets/assetmodel/add/?name=',
        )
    )

    def clean(self):
        invoice_no = self.cleaned_data.get('invoice_no', False)
        invoice_date = self.cleaned_data.get('invoice_date', False)
        if 'invoice_date' not in self.errors:
            if invoice_no and not invoice_date:
                self._errors["invoice_date"] = self.error_class([
                    _("Invoice date cannot be empty.")
                ])
        if 'invoice_on' not in self.errors:
            if invoice_date and not invoice_no:
                self._errors["invoice_no"] = self.error_class([
                    _("Invoice number cannot be empty.")
                ])
        serial_number_unique = _check_serial_numbers_uniqueness(
            [self.cleaned_data['sn']]
        )[0]
        if 'sn' in self.changed_data and not serial_number_unique:
            self._errors["sn"] = self.error_class([
                _("Asset with this Sn already exists.")
            ])
        return self.cleaned_data

    def __init__(self, *args, **kwargs):
        super(BulkEditAssetForm, self).__init__(*args, **kwargs)
        fillable_fields = [
            'type', 'model', 'device_info', 'invoice_no', 'order_no',
            'request_date', 'delivery_date', 'invoice_date',
            'production_use_date', 'provider_order_date',
            'provider_order_date', 'support_period', 'support_type',
            'provider', 'source', 'status', 'task_url', 'production_year',
        ]
        for field_name in self.fields:
            if field_name in fillable_fields:
                classes = "span12 fillable"
            elif field_name == 'support_void_reporting':
                classes = ""
            else:
                classes = "span12"
            self.fields[field_name].widget.attrs = {'class': classes}
        group_type = AssetType.from_id(self.instance.type).group.name
        if group_type == 'DC':
            del self.fields['type']
        elif group_type == 'BO':
            self.fields['type'].choices = [('', '---------')] + [
                (choice.id, choice.name) for choice in AssetType.BO.choices
            ]


class DeviceForm(ModelForm):
    class Meta:
        model = DeviceInfo
        fields = (
            'u_level',
            'u_height',
            'ralph_device_id',
        )
    force_unlink = BooleanField(required=False, label="Force unlink")
    create_stock = BooleanField(
        required=False,
        label="Create stock device",
    )

    def __init__(self, *args, **kwargs):
        kwargs.pop('mode')
        exclude = kwargs.pop('exclude', None)
        super(DeviceForm, self).__init__(*args, **kwargs)
        self.fields['ralph_device_id'] = AutoCompleteSelectField(
            LOOKUPS['ralph_device'],
            required=False,
            help_text='Enter ralph id, barcode, sn, or model.',
        )
        if exclude == 'create_stock':
            del self.fields['create_stock']

    def clean_ralph_device_id(self):
        return self.data['ralph_device_id'] or None

    def clean_create_stock(self):
        create_stock = self.cleaned_data.get('create_stock', False)
        if create_stock:
            if not self.cleaned_data.get('ralph_device_id'):
                return create_stock
            else:
                raise ValidationError(
                    _("'Ralph device id' field should be blank")
                )
        else:
            return create_stock

    def clean(self):
        ralph_device_id = self.cleaned_data.get('ralph_device_id')
        force_unlink = self.cleaned_data.get('force_unlink')
        if ralph_device_id:
            device_info = None
            try:
                device_info = self.instance.__class__.objects.get(
                    ralph_device_id=ralph_device_id
                )
            except DeviceInfo.DoesNotExist:
                pass
            if device_info:
                # if we want to assign ralph_device_id that belongs to another
                # Asset/DeviceInfo...
                if (str(device_info.ralph_device_id) == ralph_device_id and
                        device_info.id != self.instance.id):
                    if force_unlink:
                        device_info.ralph_device_id = None
                        device_info.save()
                    else:
                        msg = _(
                            'Device with this Ralph device id already exist '
                            '<a href="../{}">(click here to see it)</a>. '
                            'Please tick "Force unlink" checkbox if you want '
                            'to unlink it.'
                        )
                        self._errors["ralph_device_id"] = self.error_class([
                            mark_safe(msg.format(escape(device_info.asset.id)))
                        ])
        return self.cleaned_data


class BasePartForm(ModelForm):
    class Meta:
        model = PartInfo
        fields = ('barcode_salvaged',)

    def __init__(self, *args, **kwargs):
        """mode argument is required for distinguish ajax sources"""
        mode = kwargs.get('mode')
        if mode:
            del kwargs['mode']
        else:
            raise ModeNotSetException("mode argument not given.")
        super(BasePartForm, self).__init__(*args, **kwargs)

        channel = 'asset_dcdevice' if mode == 'dc' else 'asset_bodevice'
        self.fields['device'] = AutoCompleteSelectField(
            LOOKUPS[channel],
            required=False,
            help_text='Enter barcode, sn, or model.',
        )
        self.fields['source_device'] = AutoCompleteSelectField(
            LOOKUPS[channel],
            required=False,
            help_text='Enter barcode, sn, or model.',
        )
        if self.instance.source_device:
            self.fields[
                'source_device'
            ].initial = self.instance.source_device.id
        if self.instance.device:
            self.fields['device'].initial = self.instance.device.id


def _validate_multivalue_data(data):
    '''
        Check if data is a correct string with serial numbers and split
        it to list

        :param string: string with serial numbers splited by new line or comma
        :return list: list of serial numbers
    '''
    error_msg = _("Field can't be empty. Please put the items separated "
                  "by new line or comma.")
    data = data.strip()
    if not data:
        raise ValidationError(error_msg)
    items = []
    for item in filter(len, re.split(",|\n", data)):
        item = item.strip()
        if item in items:
            raise ValidationError(
                _("There are duplicate serial numbers in field.")
            )
        elif ' ' in item:
            raise ValidationError(
                _("Serial number can't contain white characters.")
            )
        elif item:
            items.append(item)
    if not items:
        raise ValidationError(error_msg)
    return items


def _check_serial_numbers_uniqueness(serial_numbers):
    '''
        Check serial numbers uniqueness. If find any not unique
        serial number then return false status with information
        about not unique serial numbers

        :param list serial_numbers: list of serial numbers
        :return tuple: status and not unique serial numbers or empty list
        :rtype tuple:
    '''
    assets = Asset.objects.filter(sn__in=serial_numbers)
    if not assets:
        return True, []
    not_unique = []
    for asset in assets:
        not_unique.append((asset.sn, asset.id, asset.type))
    return False, not_unique


def _check_barcodes_uniqueness(barcodes):
    '''
        Check barcodes uniqueness. If find any not unique
        barcode then return false status with information
        about not unique barcode

        :param list barcodes: list of barcodes
        :return tuple: status and not unique barcodes or empty list
        :rtype tuple:
    '''
    assets = Asset.objects.filter(barcode__in=barcodes)
    if not assets:
        return True, []
    not_unique = []
    for asset in assets:
        not_unique.append((asset.barcode, asset.id, asset.type))
    return False, not_unique


def _sn_additional_validation(serial_numbers):
    '''
        Raise ValidationError if any of serial numbers is not unique

        :param list serial_numbers: list of serial numbers
    '''
    is_unique, not_unique_sn = _check_serial_numbers_uniqueness(serial_numbers)
    if not is_unique:
        # ToDo: links to assets with duplicate sn
        msg = "Following serial number already exists in DB: %s" % (
            ", ".join(item[0] for item in not_unique_sn)
        )
        raise ValidationError(msg)


class DependencyAssetForm(DependencyForm):
    """
    Containts common solution for adding asset and editing asset section.
    Launches a plugin which depending on the category field gives the
    opportunity to complete fields such as slots
    """
    @property
    def dependencies(self):
        """
        On the basis of data from the database gives the opportunity
        to complete fields such as slots

        :returns object: Logic to test if category is in selected categories
        :rtype object:
        """
        yield Dependency(
            'slots',
            'category',
            AssetCategory.objects.filter(is_blade=True).all(),
            SHOW,
        )


class BaseAddAssetForm(DependencyAssetForm, ModelForm):
    '''
        Base class to display form used to add new asset
    '''
    class Meta:
        model = Asset
        fields = (
            'niw',
            'type',
            'category',
            'model',
            'status',
            'warehouse',
            'source',
            'invoice_no',
            'order_no',
            'price',
            'support_price',
            'support_type',
            'support_period',
            'support_void_reporting',
            'provider',
            'remarks',
            'request_date',
            'provider_order_date',
            'delivery_date',
            'invoice_date',
            'production_use_date',
            'deprecation_rate',
            'force_deprecation',
            'slots',
            'production_year',
        )
        widgets = {
            'request_date': DateWidget(),
            'delivery_date': DateWidget(),
            'invoice_date': DateWidget(),
            'production_use_date': DateWidget(),
            'provider_order_date': DateWidget(),
            'remarks': Textarea(attrs={'rows': 3}),
            'support_type': Textarea(attrs={'rows': 5}),
        }
    model = AutoCompleteSelectField(
        LOOKUPS['asset_model'],
        required=True,
        plugin_options=dict(
            add_link='/admin/ralph_assets/assetmodel/add/?name=',
        )
    )
    warehouse = AutoCompleteSelectField(
        LOOKUPS['asset_warehouse'],
        required=True,
        plugin_options=dict(
            add_link='/admin/ralph_assets/warehouse/add/?name=',
        )
    )
    category = TreeNodeChoiceField(
        queryset=AssetCategory.tree.all(),
        level_indicator='|---',
        empty_label="---",
    )
    source = ChoiceField(
        choices=AssetSource(),
    )

    def __init__(self, *args, **kwargs):
        mode = kwargs.get('mode')
        if mode:
            del kwargs['mode']
        super(BaseAddAssetForm, self).__init__(*args, **kwargs)
        category = self.fields['category'].queryset
        if mode == "dc":
            self.fields['type'].choices = [
                (c.id, c.desc) for c in AssetType.DC.choices]
            self.fields['category'].queryset = category.filter(
                type=AssetCategoryType.data_center
            )
        elif mode == "back_office":
            self.fields['type'].choices = [
                (c.id, c.desc) for c in AssetType.BO.choices]
            self.fields['category'].queryset = category.filter(
                type=AssetCategoryType.back_office
            )

    def clean_category(self):
        data = self.cleaned_data["category"]
        if not data.parent:
            raise ValidationError(
                _("Category must be selected from the subcategory")
            )
        return data

    def clean_production_year(self):
        return validate_production_year(self)


class BaseEditAssetForm(DependencyAssetForm, ModelForm):
    '''
        Base class to display form used to edit asset
    '''
    class Meta:
        model = Asset
        fields = (
            'niw',
            'sn',
            'type',
            'category',
            'model',
            'status',
            'task_url',
            'warehouse',
            'source',
            'invoice_no',
            'order_no',
            'price',
            'support_price',
            'support_type',
            'support_period',
            'support_void_reporting',
            'provider',
            'remarks',
            'sn',
            'barcode',
            'request_date',
            'provider_order_date',
            'delivery_date',
            'invoice_date',
            'production_use_date',
            'deleted',
            'deprecation_rate',
            'force_deprecation',
            'slots',
            'production_year',
        )
        widgets = {
            'request_date': DateWidget(),
            'delivery_date': DateWidget(),
            'invoice_date': DateWidget(),
            'production_use_date': DateWidget(),
            'provider_order_date': DateWidget(),
            'remarks': Textarea(attrs={'rows': 3}),
            'support_type': Textarea(attrs={'rows': 5}),
            'sn': Textarea(attrs={'rows': 1, 'readonly': '1'}),
            'barcode': Textarea(attrs={'rows': 1}),
        }
    model = AutoCompleteSelectField(
        LOOKUPS['asset_model'],
        required=True,
        plugin_options=dict(
            add_link='/admin/ralph_assets/assetmodel/add/?name=',
        )
    )
    warehouse = AutoCompleteSelectField(
        LOOKUPS['asset_warehouse'],
        required=True,
        plugin_options=dict(
            add_link='/admin/ralph_assets/warehouse/add/?name=',
        )
    )
    category = TreeNodeChoiceField(
        queryset=AssetCategory.tree.all(),
        level_indicator='|---',
        empty_label="---",
    )
    source = ChoiceField(
        choices=AssetSource(),
    )

    def __init__(self, *args, **kwargs):
        mode = kwargs.get('mode')
        if mode:
            del kwargs['mode']
        super(BaseEditAssetForm, self).__init__(*args, **kwargs)
        category = self.fields['category'].queryset
        if mode == "dc":
            self.fields['type'].choices = [
                (c.id, c.desc) for c in AssetType.DC.choices]
            self.fields['category'].queryset = category.filter(
                type=AssetCategoryType.data_center
            )
        elif mode == "back_office":
            self.fields['type'].choices = [
                (c.id, c.desc) for c in AssetType.BO.choices]
            self.fields['category'].queryset = category.filter(
                type=AssetCategoryType.back_office
            )

    def clean_sn(self):
        return self.instance.sn

    def clean_category(self):
        data = self.cleaned_data["category"]
        if not data.parent:
            raise ValidationError(
                _("Category must be selected from the subcategory")
            )
        return data

    def clean_production_year(self):
        return validate_production_year(self)

    def clean(self):
        if self.instance.deleted:
            raise ValidationError(_("Cannot edit deleted asset"))
        cleaned_data = super(BaseEditAssetForm, self).clean()
        return cleaned_data


def validate_production_year(asset):
    data = asset.cleaned_data["production_year"]
    # Matches any 4-digit number:
    year_re = re.compile('^\d{4}$')
    if not year_re.match(str(data)):
        raise ValidationError(u'%s is not a valid year.' % data)
    # Check not before this year:
    year = int(data)
    thisyear = time.localtime()[0]
    if year > thisyear:
        raise ValidationError(
            u'%s is a year in the future.'
            u' Please enter a current or past year.' % data)
    return data


class MoveAssetPartForm(Form):
    new_asset = AutoCompleteSelectField(
        LOOKUPS['asset_dcdevice'],
    )


class AddPartForm(BaseAddAssetForm):
    '''
        Add new part for device
    '''
    sn = CharField(
        label=_("SN/SNs"), required=True, widget=Textarea(attrs={'rows': 25}),
    )

    def clean_sn(self):
        data = _validate_multivalue_data(self.cleaned_data["sn"])
        _sn_additional_validation(data)
        return data


class AddDeviceForm(BaseAddAssetForm):
    '''
        Add new device form
    '''
    sn = CharField(
        label=_("SN/SNs"), required=True, widget=Textarea(attrs={'rows': 25}),
    )
    barcode = CharField(
        label=_("Barcode/Barcodes"), required=False,
        widget=Textarea(attrs={'rows': 25}),
    )
    task_url = CharField(required=False, label='Task url')

    def __init__(self, *args, **kwargs):
        super(AddDeviceForm, self).__init__(*args, **kwargs)
        # insert task_url after 'status' field
        after_status = 5
        new_order = self.fields.keyOrder[:-1]
        new_order.insert('task_url', after_status)
        self.fields.keyOrder = new_order

    def clean_sn(self):
        '''
            Validate if sn is correct and change string with serial numbers
            to list
        '''
        data = _validate_multivalue_data(self.cleaned_data["sn"])
        _sn_additional_validation(data)
        return data

    def clean_barcode(self):
        data = self.cleaned_data["barcode"].strip()
        barcodes = []
        if data:
            for barcode in filter(len, re.split(",|\n", data)):
                barcode = barcode.strip()
                if barcode in barcodes:
                    raise ValidationError(
                        _("There are duplicate barcodes in the field.")
                    )
                elif ' ' in barcode:
                    raise ValidationError(
                        _("Serial number can't contain white characters.")
                    )
                elif barcode:
                    barcodes.append(barcode)
            if not barcodes:
                raise ValidationError(_("Barcode list could be empty or "
                                        "must have the same number of "
                                        "items as a SN list."))
            is_unique, not_unique_bc = _check_barcodes_uniqueness(barcodes)
            if not is_unique:
                # ToDo: links to assets with duplicate barcodes
                msg = "Following barcodes already exists in DB: %s" % (
                    ", ".join(item[0] for item in not_unique_bc)
                )
                raise ValidationError(msg)
        return barcodes

    def clean(self):
        cleaned_data = super(AddDeviceForm, self).clean()
        serial_numbers = cleaned_data.get("sn", [])
        barcodes = cleaned_data.get("barcode", [])
        if barcodes and len(serial_numbers) != len(barcodes):
            self._errors["barcode"] = self.error_class([
                _("Barcode list could be empty or must have the same number "
                  "of items as a SN list.")
            ])
        return cleaned_data


class OfficeForm(ModelForm):
    class Meta:
        model = OfficeInfo
        exclude = ('created', 'modified')
        widgets = {
            'date_of_last_inventory': DateWidget(),
        }


class EditPartForm(BaseEditAssetForm):
    pass


class EditDeviceForm(BaseEditAssetForm):
    def clean(self):
        cleaned_data = super(EditDeviceForm, self).clean()
        deleted = cleaned_data.get("deleted")
        if deleted and self.instance.has_parts():
            parts = self.instance.get_parts_info()
            raise ValidationError(
                _(
                    "Cannot remove asset with parts assigned. Please remove "
                    "or unassign them from device first. ".format(
                        ", ".join([part.asset.sn for part in parts])
                    )
                )
            )
        if not cleaned_data.get('sn') and not cleaned_data.get('barcode'):
            raise ValidationError(
                _("If SN is empty - Barcode is required")
            )
        return cleaned_data


class BackOfficeEditDeviceForm(EditDeviceForm):
    pass

class DataCenterEditDeviceForm(EditDeviceForm):
    pass


class SearchAssetForm(Form):
    """returns search asset form for DC and BO.

    :param mode: one of `dc` for DataCenter or `bo` for Back Office
    :returns Form
    """
    model = AutoCompleteField(
        LOOKUPS['asset_model'],
        required=False,
        help_text=None,
    )
    manufacturer = AutoCompleteField(
        LOOKUPS['asset_manufacturer'],
        required=False,
        help_text=None,
    )
    invoice_no = CharField(required=False)
    order_no = CharField(required=False)
    provider = CharField(required=False, label='Provider')
    status = ChoiceField(
        required=False, choices=[('', '----')] + AssetStatus(),
        label='Status'
    )
    task_url = CharField(required=False, label='Task url')
    part_info = ChoiceField(
        required=False,
        choices=[('', '----'), ('device', 'Device'), ('part', 'Part')],
        label='Asset type'
    )
    category = TreeNodeChoiceField(
        required=False,
        queryset=AssetCategory.tree.all(),
        level_indicator='|---',
        empty_label="---",
    )
    source = ChoiceField(
        required=False,
        choices=[('', '----')] + AssetSource(),
    )
    niw = CharField(required=False, label='Niw')
    sn = CharField(required=False, label='SN')
    barcode = CharField(required=False, label='Barcode')
    ralph_device_id = IntegerField(
        required=False,
        label='Ralph device id',
    )
    request_date_from = DateField(
        required=False, widget=DateWidget(attrs={
            'placeholder': 'Start YYYY-MM-DD',
            'data-collapsed': True,
        }),
        label="Request date",
    )
    request_date_to = DateField(
        required=False, widget=DateWidget(attrs={
            'class': 'end-date-field ',
            'placeholder': 'End YYYY-MM-DD',
            'data-collapsed': True,
        }),
        label='')
    provider_order_date_from = DateField(
        required=False, widget=DateWidget(attrs={
            'placeholder': 'Start YYYY-MM-DD',
            'data-collapsed': True,
        }),
        label="Provider order date",
    )
    provider_order_date_to = DateField(
        required=False, widget=DateWidget(attrs={
            'class': 'end-date-field ',
            'placeholder': 'End YYYY-MM-DD',
            'data-collapsed': True,
        }),
        label='')
    delivery_date_from = DateField(
        required=False, widget=DateWidget(attrs={
            'placeholder': 'Start YYYY-MM-DD',
            'data-collapsed': True,
        }),
        label="Delivery date",
    )
    delivery_date_to = DateField(
        required=False, widget=DateWidget(attrs={
            'class': 'end-date-field ',
            'placeholder': 'End YYYY-MM-DD',
            'data-collapsed': True,
        }),
        label='')
    deprecation_rate = ChoiceField(
        required=False, choices=[('', '----'),
                                 ('null', 'None'),
                                 ('48>', '48 <'),
                                 ('48', '24 < * <= 48'),
                                 ('24', '12 < * <= 24'),
                                 ('12', '6 < * <= 12'),
                                 ('6', '* <= 6'),
                                 ('deprecated', 'Deprecated'), ],
        label='Deprecation'
    )
    invoice_date_from = DateField(
        required=False, widget=DateWidget(attrs={
            'placeholder': 'Start YYYY-MM-DD',
            'data-collapsed': True,
        }),
        label="Invoice date",
    )
    invoice_date_to = DateField(
        required=False, widget=DateWidget(attrs={
            'class': 'end-date-field ',
            'placeholder': 'End YYYY-MM-DD',
            'data-collapsed': True,
        }),
        label='')

    production_use_date_from = DateField(
        required=False, widget=DateWidget(attrs={
            'placeholder': 'Start YYYY-MM-DD',
            'data-collapsed': True,
        }),
        label="Production use date",
    )
    production_use_date_to = DateField(
        required=False, widget=DateWidget(attrs={
            'class': 'end-date-field ',
            'placeholder': 'End YYYY-MM-DD',
            'data-collapsed': True,
        }),
        label='')
    unlinked = BooleanField(required=False, label="Is unlinked")
    deleted = BooleanField(required=False, label="Include deleted")

    def __init__(self, *args, **kwargs):
        # Ajax sources are different for DC/BO, use mode for distinguish
        mode = kwargs.get('mode')
        if mode:
            del kwargs['mode']
        super(SearchAssetForm, self).__init__(*args, **kwargs)
        category = self.fields['category'].queryset
        if mode == 'dc':
            self.fields['category'].queryset = category.filter(
                type=AssetCategoryType.data_center
            )
        elif mode == 'back_office':
            self.fields['category'].queryset = category.filter(
                type=AssetCategoryType.back_office
            )


class DeleteAssetConfirmForm(Form):
    asset_id = IntegerField(widget=HiddenInput())


class SplitDevice(ModelForm):
    class Meta:
        model = Asset
        fields = (
            'id', 'delete', 'model_proposed', 'model_user', 'invoice_no',
            'order_no', 'sn', 'barcode', 'price', 'support_price',
            'support_period', 'support_type', 'support_void_reporting',
            'provider', 'source', 'status', 'request_date', 'delivery_date',
            'invoice_date', 'production_use_date', 'provider_order_date',
            'warehouse', 'production_year',
        )
        widgets = {
            'request_date': DateWidget(),
            'delivery_date': DateWidget(),
            'invoice_date': DateWidget(),
            'production_use_date': DateWidget(),
            'provider_order_date': DateWidget(),
            'device_info': HiddenInput(),
        }
    delete = BooleanField(required=False)
    model_user = CharField()
    model_proposed = CharField(required=False)

    def __init__(self, *args, **kwargs):
        super(SplitDevice, self).__init__(*args, **kwargs)
        fillable_fields = [
            'model_user', 'device_info', 'invoice_no', 'order_no',
            'request_date', 'delivery_date', 'invoice_date',
            'production_use_date', 'provider_order_date',
            'provider_order_date', 'support_period', 'support_type',
            'provider', 'source', 'status', 'warehouse', 'production_year',
        ]
        for field_name in self.fields:
            if field_name in fillable_fields:
                classes = "span12 fillable"
            elif field_name == 'support_void_reporting':
                classes = ""
            else:
                classes = "span12"
            self.fields[field_name].widget.attrs = {'class': classes}
        self.fields['model_proposed'].widget = ReadOnlyWidget()
        #self.fields['delete'].widget = ButtonWidget(
        #    attrs={'class': 'btn-danger delete_row', 'value': '-'}
        #)

    def clean(self):
        cleaned_data = super(SplitDevice, self).clean()
        sn = cleaned_data.get('sn')
        barcode = cleaned_data.get('barcode')
        price = cleaned_data.get('price', '')
        try:
            float(price)
        except (ValueError, TypeError):
            if 'price' in self.errors:
                self.errors['price'].append(_("Price must be decimal"))
            else:
                self.errors['price'] = [_("Price must be decimal"), ]
        if not sn:
            cleaned_data['sn'] = None
        if not barcode:
            cleaned_data['barcode'] = None
        if not sn and not barcode:
            error_text = [_("SN or Barcode is required"), ]
            self.errors['sn'] = error_text
            self.errors['barcode'] = error_text
        return cleaned_data


class AssetColumnChoiceField(ChoiceField):
    def __init__(self, *args, **kwargs):
        kwargs['choices'] = [
            (field.name, unicode(field.verbose_name))
            for field in Asset._meta.fields if field.name != 'id'
        ]
        super(AssetColumnChoiceField, self).__init__(*args, **kwargs)


class XlsUploadForm(Form):
    """The first step for uploading the XLS file for asset bulk update."""
    file = FileField()


class XlsColumnChoiceForm(Form):
    """The column choice. This form will be filled on the fly."""


class XlsConfirmForm(Form):
    """The confirmation of XLS submission. A form with a button only."""


XLS_UPLOAD_FORMS = [
    ('upload', XlsUploadForm),
    ('column_choice', XlsColumnChoiceForm),
    ('confirm', XlsConfirmForm),
]
