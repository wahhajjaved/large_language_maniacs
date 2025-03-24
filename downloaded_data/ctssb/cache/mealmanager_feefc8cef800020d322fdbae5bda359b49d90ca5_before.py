from decimal import Decimal
import re
from django.forms import ModelForm, ValidationError, TextInput
from .models import RecipeIngredient, Recipe


class RecipeForm(ModelForm):

    prefix = 'recipe'

    class Meta:
        model = Recipe
        exclude = ['ingredients']

    def save(self):
        return super(RecipeForm, self).save()

    def is_valid(self):
        return super(RecipeForm, self).is_valid()


class RecipeIngredientForm(ModelForm):

    class Meta:
        model = RecipeIngredient
        exclude = []
        labels = {
            'quantity_amount': 'Qty'
        }
        widgets = {
            'ingredient': TextInput(attrs={'placeholder': 'Ingredient name'}),
            'quantity_amount': TextInput(
                attrs={
                    'placeholder': 'e.g. 1 1/4',
                    'size': 6,
                }),
        }

    def clean_quantity_amount(self):
        data = self.cleaned_data['quantity_amount']
        if not re.match(r'^([1-9]\d*)?\s?([1-9]\d*/[1-9]\d*)?$', data):
            raise ValidationError('Quantity is not a valid number or fraction.')
        return data

    def __init__(self, *args, **kwargs):
        """Override BaseModelForm init to set the ingredient value to the name of the ingredient rather than it's id."""
        instance = kwargs.get('instance')
        if instance is not None:
            initial = {
                'ingredient': str(getattr(instance, 'ingredient'))
            }
        else:
            initial = None
        super(RecipeIngredientForm, self).__init__(*args, **kwargs, initial=initial)
