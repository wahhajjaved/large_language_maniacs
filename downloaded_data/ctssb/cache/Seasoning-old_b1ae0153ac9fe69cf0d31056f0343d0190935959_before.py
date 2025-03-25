from django.shortcuts import render, redirect
from recipes.models import Recipe, Vote, UsesIngredient
from recipes.forms import AddRecipeForm, UsesIngredientForm
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.forms.models import inlineformset_factory
from django.contrib import messages

def search_recipes(request):
    recipes_list = Recipe.objects.all()
    paginator = Paginator(recipes_list, 10)
    
    page = request.GET.get('page')
    try:
        recipes = paginator.page(page)
    except PageNotAnInteger:
        recipes = paginator.page(1)
    except EmptyPage:
        recipes = paginator.page(paginator.num_pages)
        
    return render(request, 'recipes/search_recipes.html', {'recipes': recipes})

def view_recipe(request, recipe_id, portions=None):
    recipe = Recipe.objects.select_related().get(pk=recipe_id)
    usess = UsesIngredient.objects.select_related('ingredient', 'unit').filter(recipe=recipe)

    if portions:
        ratio = portions/recipe.portions
        recipe.footprint = ratio * recipe.footprint
        for uses in usess:
            uses.amount = ratio * uses.amount
        
    user_vote = None
    if request.user.is_authenticated():
        try:
            user_vote = Vote.objects.get(recipe_id=recipe_id, user=request.user)
        except ObjectDoesNotExist:
            pass
    
    return render(request, 'recipes/view_recipe.html', {'recipe': recipe,
                                                        'usess': usess,
                                                        'user_vote': user_vote})

@login_required
def vote(request, recipe_id, new_score):
    new_score = int(new_score)
    try:
        vote = Vote.objects.get(recipe_id=recipe_id, user=request.user)
        # This user has already voted in the past
        vote.score = new_score
    except ObjectDoesNotExist:
        # This user has not voted on this recipe yet
        vote = Vote(recipe_id=recipe_id, user=request.user, score=new_score)
    vote.save()
    return redirect(view_recipe, recipe_id)

@login_required
def remove_vote(request, recipe_id):
    try:
        vote = Vote.objects.get(recipe_id=recipe_id, user=request.user)
        vote.delete()
        return redirect(view_recipe, recipe_id)
    except ObjectDoesNotExist:
        raise Http404()

@login_required
def edit_recipe(request, recipe_id=None):
    if recipe_id:
        recipe = Recipe.objects.get(pk=recipe_id)
        if (not request.user == recipe.author) and not request.user.is_staff:
            raise PermissionDenied
        new = False
    else:
        recipe = Recipe()
        new = True
    
    UsesIngredientInlineFormSet = inlineformset_factory(Recipe, UsesIngredient, extra=1,
                                                        form=UsesIngredientForm)
    
    if request.method == 'POST':
        recipe_form = AddRecipeForm(request.POST, instance=recipe)
        usesingredient_formset = UsesIngredientInlineFormSet(request.POST, instance=recipe)
        
        if recipe_form.is_valid() and usesingredient_formset.is_valid():
            recipe_form.save(author=request.user)
            usesingredient_formset.save()
            if new:
                messages.add_message(request, messages.INFO, 'Het recept werd met succes toegevoegd aan onze databank')
            else:
                messages.add_message(request, messages.INFO, 'Het recept werd met succes aangepast')
            return redirect('/recipes/' + str(recipe.id) + '/')
    else:
        recipe_form = AddRecipeForm(instance=recipe)
        usesingredient_formset = UsesIngredientInlineFormSet(instance=recipe)
    
    return render(request, 'recipes/edit_recipe.html', {'new': new,
                                                        'recipe_form': recipe_form,
                                                        'usesingredient_formset': usesingredient_formset})
