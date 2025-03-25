# -*- coding: utf-8 -*-
#
from django.contrib import admin
from feincms.admin import editor
from django import forms
from ckeditor.widgets import CKEditorWidget
from clever.core.admin import thumbnail_column
from clever.core.admin import AdminMixin
from clever.catalog import models
from clever.catalog.forms import FilterForm
from clever.catalog.attributes import AttributeManager
from clever.magic.classmaker import classmaker


# ------------------------------------------------------------------------------
class SectionParamsIterator(forms.models.ModelChoiceIterator):
    ### TODO: TEST THIS!!!!
    def __init__(self, inline, field, section):
        self.section = section
        self.inline = inline

        super(SectionParamsIterator, self).__init__(field)

    # def get_parents(self):
    #     sections = Section.objects.filter(parent=self.section)
    #     parents = [self.section.id]
    #     if (sections):
    #         parents = parents + list(set(item.id for item in sections.all()))
    #     return parents

    def __iter__(self):
        related_manager = self.inline.related_model.objects

        # Получение родительских элементов
        parents = [self.section]  # self.get_parents()

        # Поиск элементов присуствующих в данном разделе
        field_name = self.inline.filter_field + '__in'
        filter = {
            field_name: parents
        }
        items_ids = related_manager.filter(**filter).values_list('id', flat=True).distinct()

        # Поиск значений для вывода
        if (len(items_ids)):
            items_used = related_manager.filter(id__in=items_ids)
            items_nonused = related_manager.exclude(id__in=items_ids)
            if items_used.count():
                # yield (u'', None),
                yield (u'Используемые', [(item.id, unicode(item),) for item in items_used])
                yield (u'Неиспользуемые', [(item.id, unicode(item),) for item in items_nonused])
                return

        # Возвращаем значения по умолчанию
        for item in related_manager.all():
            yield (item.id, unicode(item),)


# ------------------------------------------------------------------------------
class SectionParamsInline(admin.TabularInline):
    extra = 0

    def get_formset(self, request, obj=None, **kwargs):
        value = super(SectionParamsInline, self).get_formset(request, obj, **kwargs)
        if obj:
            value.form.base_fields[self.field_name].choices = SectionParamsIterator(
                self,
                value.form.base_fields[self.field_name],
                obj
            )
        return value


# ------------------------------------------------------------------------------
class SectionForm(forms.ModelForm):
    class Meta:
        widgets = {
            'text': CKEditorWidget(config_name='default')
        }


# ------------------------------------------------------------------------------
class SectionAdmin(AdminMixin, editor.TreeEditor):
    """
    ..todo: Протестировать все!
    """
    form = SectionForm

    def __init__(self, model, *args, **kwargs):
        super(SectionAdmin, self).__init__(model, *args, **kwargs)

        self.insert_list_display(['admin_thumbnail', 'active'], before=True)
        self.insert_list_display(['slug'])

        self.insert_list_display_links(['admin_thumbnail', '__unicode__', '__str__'])

        # Создание inline редактора для свойств товара
        brand_inline = type(model.__name__ + "_SectionBrandInline", (SectionParamsInline,), {
            'model': models.SectionBrand,
            'field_name': 'brand',
            'related_model': models.Brand,
            'filter_field': 'products__section',
        })
        attribute_inline = type(model.__name__ + "_SectionAttributeInline", (SectionParamsInline,), {
            'model': models.SectionAttribute,
            'field_name': 'attribute',
            'related_model': models.Attribute,
            'filter_field': 'values__product__section',
        })
        self.insert_inlines([brand_inline, attribute_inline], before=True)

    @thumbnail_column(size='106x80')
    def admin_thumbnail(self, inst):
        """ Выводит картинку а админке """
        return [inst.image]

    def get_readonly_fields(self, request, obj=None):
        return list(super(SectionAdmin, self).get_readonly_fields(request, obj)) + ['slug']


# ------------------------------------------------------------------------------
class AttributeForm(forms.ModelForm):
    def clean_control(self):
        # Хак для проверки типа для диапазона типов
        control = self.cleaned_data['control']
        type = self.cleaned_data['type']
        if control == u'range' and type not in [u'integer', u'float']:
            raise forms.ValidationError("Диапазон значений может использоваться только с числовыми типами")
        return control


# ------------------------------------------------------------------------------
class AttributeAdmin(AdminMixin, admin.ModelAdmin):
    form = AttributeForm

    def __init__(self, model, admin_site, *args, **kwargs):
        super(AttributeAdmin, self).__init__(model, admin_site, *args, **kwargs)

        self.insert_list_display(['code', 'type', 'control'])


# ------------------------------------------------------------------------------
class ProductAttributeInline(AdminMixin, admin.TabularInline):
    extra = 0

    def __init__(self, *args, **kwargs):
        super(ProductAttributeInline, self).__init__(*args, **kwargs)

        exclude = []
        for type_name, type in AttributeManager.get_types():
            exclude.append(type.field_name)
        self.insert_exclude(exclude)
        self.insert_fields(['attribute', 'raw_value', 'real_value', 'is_main', 'is_hidden'])

    def get_readonly_fields(self, request, obj=None):
        return list(super(ProductAttributeInline, self).get_readonly_fields(request, obj)) + ['real_value']

    def real_value(self, instance):
        return instance.value
    real_value.short_description = u'Реальное значение'


# ------------------------------------------------------------------------------
class ProductForm(forms.ModelForm):
    class Meta:
        widgets = {
            'text': CKEditorWidget(config_name='default')
        }


# ------------------------------------------------------------------------------
class ProductAdmin(AdminMixin, admin.ModelAdmin):
    """
    ..todo: Протестировать все!
    """
    form = ProductForm

    def __init__(self, model, admin_site, *args, **kwargs):
        # Добавляем базовые элементы в админку
        self.insert_list_display(['admin_thumbnail'], before=True)
        self.insert_list_display(['active', 'section', 'brand', 'price', 'code'])
        self.insert_list_display_links(['admin_thumbnail', '__unicode__', '__str__'])
        self.insert_list_filter(['brand', 'section'])
        self.insert_search_fields(['title'])

        # Создание inline редактора для свойств товара
        product_attribute_inline = type(model.__name__ + "_ProductAttributeInline", (ProductAttributeInline,), {
            'model': models.ProductAttribute,
        })
        self.insert_inlines([product_attribute_inline])

        super(ProductAdmin, self).__init__(model, admin_site, *args, **kwargs)

    @thumbnail_column(size='106x80')
    def admin_thumbnail(self, inst):
        """ Выводит картинку а админке """
        return [inst.image]

    def get_readonly_fields(self, request, obj=None):
        return list(super(ProductAdmin, self).get_readonly_fields(request, obj)) + ['slug']


# ------------------------------------------------------------------------------
class PseudoSectionValueInline(AdminMixin, admin.TabularInline):
    # form = PseudoSectionValueForm
    extra = 1

    def __init__(self, *args, **kwargs):
        super(PseudoSectionValueInline, self).__init__(*args, **kwargs)

        exclude = []
        for type_name, type in AttributeManager.get_types():
            exclude.append(type.field_name)
        self.insert_exclude(exclude)
        self.insert_fields(['attribute', 'raw_value', 'raw_value_to', 'real_value', 'real_value_to'])

    def get_readonly_fields(self, request, obj=None):
        return list(super(PseudoSectionValueInline, self).get_readonly_fields(request, obj)) + [
            'real_value',
            'real_value_to'
        ]

    def real_value(self, instance):
        return instance.value
    real_value.short_description = u'Реальное значение'

    def real_value_to(self, instance):
        return instance.value_to
    real_value.short_description = u'Реальное значение'


# ------------------------------------------------------------------------------
class PseudoSectionBrandInline(admin.TabularInline):
    extra = 1


# ------------------------------------------------------------------------------
class PseudoSectionForm(forms.ModelForm):
    class Meta:
        widgets = {
            'text': CKEditorWidget(config_name='default')
        }


# ------------------------------------------------------------------------------
class PseudoSectionAdmin(AdminMixin, admin.ModelAdmin):
    form = PseudoSectionForm

    def __init__(self, model, admin_site, *args, **kwargs):
        super(PseudoSectionAdmin, self).__init__(model, admin_site, *args, **kwargs)

        # Добавляем базовые элементы в админку
        self.insert_list_display(['active', 'section', 'slug'])
        self.insert_list_display_links(['admin_thumbnail', '__unicode__', '__str__'])
        # self.insert_fields(['brand'])

        # Создание inline редактора для свойств товара
        pseudo_section_value_inline = type(model.__name__ + "_PseudoSectionValueInline", (PseudoSectionValueInline,), {
            'model': models.PseudoSectionValue,
        })
        product_attribute_inline = type(model.__name__ + "_PseudoSectionBrandInline", (PseudoSectionBrandInline,), {
            'model': models.PseudoSectionBrand,
        })

        self.insert_inlines([
            pseudo_section_value_inline,
            product_attribute_inline
        ])

    def get_readonly_fields(self, request, obj=None):
        return list(super(PseudoSectionAdmin, self).get_readonly_fields(request, obj)) + ['slug']
