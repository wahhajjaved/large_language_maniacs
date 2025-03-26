"""
Copyright 2012, 2013 Driesen Joep

This file is part of Seasoning.

Seasoning is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Seasoning is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Seasoning.  If not, see <http://www.gnu.org/licenses/>.
    
"""
from django import forms
from recipes.models import Recipe, UsesIngredient, Cuisine
import recipes
from django.forms.widgets import RadioSelect
from ingredients.fields import AutoCompleteSelectIngredientField
from ingredients.models import Ingredient

class AddRecipeForm(forms.ModelForm):
    
    class Meta:
        model = Recipe
        exclude = ['author', 'time_added',
                   'rating', 'number_of_votes',
                   'thumbnail', 'accepted']
    
    def save(self, author, commit=True):
        recipe = super(AddRecipeForm, self).save(commit=False)
        recipe.author = author
        return recipe.save(commit=commit)

class UsesIngredientForm(forms.ModelForm):

    ingredient = AutoCompleteSelectIngredientField()
    
    class Meta:
        model = UsesIngredient
    
    def is_valid_before_ingrequest(self):
        """
        Check if this form would be valid if a known ingredient was used
        
        """
        if super(UsesIngredientForm, self).is_valid():
            # Check if the form is valid anyway
            return True
        if not self.cleaned_data['recipe'] or not self.cleaned_data['amount'] or not self.cleaned_data['unit']:
            # Check if any fields except ingredient are invalid, if so, the form would be invalid anyway
            return False
        if not self['ingredient'].value() or len(self['ingredient'].value()) > 50:
            # Check if anything else is wrong with the ingredient field
            return False
        return True
            
    
    def uses_existing_ingredient(self):
        try:
            if self['ingredient'].value():
                Ingredient.objects.get(name__iexact=self['ingredient'].value())
            return True
        except Ingredient.DoesNotExist:
            pass
        return False        
            

class SearchRecipeForm(forms.Form):
    
    SORT_CHOICES = (('name', 'Naam'), ('footprint', 'Voetafdruk'),
                    ('active_time', 'Actieve Kooktijd'), ('tot_time', 'Totale Kooktijd'))
    SORT_ORDER_CHOICES = (('', 'Van Laag naar Hoog'), ('-', 'Van Hoog naar Laag'))
    OPERATOR_CHOICES = (('and', 'Allemaal'), ('or', 'Minstens 1'))
    
    search_string = forms.CharField(required=False, label='Zoektermen')
    
    sort_field = forms.ChoiceField(choices=SORT_CHOICES)
    sort_order = forms.ChoiceField(widget=RadioSelect, choices=SORT_ORDER_CHOICES, required=False)
    
    ven = forms.BooleanField(initial=True, required=False, label='Veganistisch')
    veg = forms.BooleanField(initial=True, required=False, label='Vegetarisch')
    nveg = forms.BooleanField(initial=True, required=False, label='Niet-Vegetarisch')
    
    cuisine = forms.ModelMultipleChoiceField(queryset=Cuisine.objects.all(), required=False, label='Keuken')
    
    course = forms.ChoiceField(required=False, choices=(((u'', u'Maakt niet uit'),) + recipes.models.Recipe.COURSES), label='Maaltijd')
    
    include_ingredients_operator = forms.ChoiceField(widget=RadioSelect, choices=OPERATOR_CHOICES, label='', initial=OPERATOR_CHOICES[1][0])

class IngredientInRecipeSearchForm(forms.Form):
    
    name = forms.CharField()
    
    

