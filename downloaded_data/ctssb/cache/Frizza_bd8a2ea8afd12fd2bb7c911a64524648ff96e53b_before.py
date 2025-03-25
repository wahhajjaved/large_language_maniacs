from django.shortcuts import render
import settings
from Frizza.models import User, Sauce, Crust, Pizza, Topping, HasTopping, \
                            Allergy, Orders
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponseRedirect
import logging
from django.db.models import Max

logger = logging.getLogger('registration')


# This function provides an appropriate response to a request for the pizza
# page.
def pizza(request):
    if request.user.is_authenticated():
        order_list = Orders.objects.filter(user_name="admin")
        admin_list = Pizza.objects.filter(pizza_id__in=order_list).select_related()
        uorder_list = Orders.objects.filter(user_name=str(request.user))
        user_list = Pizza.objects.filter(pizza_id__in=uorder_list).select_related()
        if request.method == 'POST':
            request.session['pizza'] = ''
            pizza = request.POST['pizza']
            if pizza == 'Make Your Own!':
                return HttpResponseRedirect('/crust')
            else:
                request.session['pizza'] = request.POST['pizza']
                return HttpResponseRedirect('/allergies')
        else:
            context = {'admin_list': admin_list,
                       'user_list': user_list,
                       'order_complete': request.session['order_complete'],
                       'order_cancelled': request.session['order_cancelled']}
            request.session['order_complete'] = False
            request.session['order_cancelled'] = False
            return render(request, settings.TEMPLATE_DIRS +
                                   '/public_html/Pizza/pizza.html', context)
    else:
        return HttpResponseRedirect('/login')


# This function provides an appropriate response to a request for the toppings
# page.
def toppings(request):
    if request.user.is_authenticated():
        if 'pizza' in request.session:
            if 'crust' in request.session:
                if 'sauce' in request.session:
                    topping_list = Topping.objects.all()
                    if request.method == 'POST':
                        if 'confirm' in request.POST:
                            for i in topping_list:
                                if str(i) in request.POST:
                                    request.session[str(i)] = str(i)
                            return HttpResponseRedirect('/allergies')
                        else:
                            del request.session['sauce']
                            return HttpResponseRedirect['sauce']
                    else:
                        context = {'topping_list': topping_list}
                        return render(request, settings.TEMPLATE_DIRS +
                               '/public_html/Toppings/toppings.html', context)
                else:
                    return HttpResponseRedirect('/sauce')
            else:
                return HttpResponseRedirect('/crust')
        else:
            return HttpResponseRedirect('/pizza')
    else:
        return HttpResponseRedirect('/login')


# This function provides an appropriate response to a request for the crust
# page.
def crust(request):
    if request.user.is_authenticated():
        if 'pizza' in request.session:
            if request.method == 'POST':
                if 'confirm' in request.POST:
                    if 'crust' in request.POST:
                        request.session['crust'] = request.POST['crust']
                        return HttpResponseRedirect('/sauce')
                    else:
                        return HttpResponseRedirect('/crust')
                else:
                    return HttpResponseRedirect('/pizza')
            else:
                crust_list = Crust.objects.all()
                context = {'crust_list': crust_list}
                return render(request, settings.TEMPLATE_DIRS +
                                   '/public_html/Crust/crust.html', context)
        else:
            return HttpResponseRedirect('/pizza')
    else:
        return HttpResponseRedirect('/login')


# This function provides the appropriate response to a request for the sauce
# page.
def sauce(request):
    if request.user.is_authenticated():
        if 'pizza' in request.session:
            if 'crust' in request.session:
                if request.method == 'POST':
                    if 'confirm' in request.POST:
                        if 'sauce' in request.POST:
                            request.session['sauce'] = request.POST['sauce']
                            return HttpResponseRedirect('/toppings')
                        else:
                            HttpResponseRedirect('/toppings')
                    else:
                        del request.session['crust']
                        return HttpResponseRedirect('/crust')
                else:
                    sauce_list = Sauce.objects.all()
                    context = {'sauce_list': sauce_list}
                    return render(request, settings.TEMPLATE_DIRS +
                                   '/public_html/Sauce/sauce.html', context)
            else:
                return HttpResponseRedirect('/crust')
        else:
            return HttpResponseRedirect('/pizza')
    else:
        return HttpResponseRedirect('/login')


#This function does not work, but we would like to revisit it in the future.
def allergies(request):
    if request.user.is_authenticated():
        if request.method == 'POST':
            if 'confirm' in request.POST:
                return HttpResponseRedirect('/confirmation')
            else:
                toppings = Topping.objects.all()
                for i in toppings:
                    if str(i) in request.session:
                        del request.session[str(i)]
                request.session['pizza'] = ''
                return HttpResponseRedirect('/toppings')
        else:
            topping_allergies = []
            sauce_allergies = []
            crust_allergies = []

            if request.session['pizza'] == '':
                crust = Crust.objects.get(crust_name=request.session['crust'])
                sauce = Sauce.objects.get(sauce_name=request.session['sauce'])
                all_toppings = Topping.objects.all()
                for i in all_toppings:
                    if str(i) in request.session:
                        allergies = Allergy.objects.filter(ingredient_name=i.topping_name)
                        for j in allergies:
                            topping_allergies.append(j)
            else:
                pizza = Pizza.objects.get(pizza_name=request.session['pizza'])
                crust = Crust.objects.get(crust_name=pizza.crust_name)
                sauce = Sauce.objects.get(sauce_name=pizza.sauce_name)

                pizzaToppings = HasTopping.objects.filter(pizza_id=pizza)

                for topping in pizzaToppings:
                    allergies = Allergy.objects.filter(ingredient_name=topping.topping_name)

                    for allergy in allergies:
                        topping_allergies.append(allergy)

            sauce_allergies = Allergy.objects.filter(ingredient_name=sauce.sauce_name)
            crust_allergies = Allergy.objects.filter(ingredient_name=crust.crust_name)
            context = {'topping_allergies': topping_allergies,
                        'sauce_allergies': sauce_allergies,
                        'crust_allergies': crust_allergies,
                      }
            return render(request, settings.TEMPLATE_DIRS +
                          '/public_html/Allergies/allergies.html', context)
    else:
        return HttpResponseRedirect('/login')


# This function provides an appropriate response to a request for the calorie
# page.

def calorie(request):
    if request.user.is_authenticated():
        #TODO: Validate appropriate fields are filled out
        if request.method == 'POST':
            if ('confirm' in request.POST):
                current_id = Pizza.objects.all().\
                             aggregate(Max('pizza_id'))['pizza_id__max'] + 1
                pizza = None
                if request.session['pizza'] == '':
                    order_id = 1
                    pizza = Pizza(current_id, str(request.POST['pizza_name']),
                                  order_id, request.session['sauce'],
                                  request.session['crust'])
                    pizza.save()
                    del request.session['pizza']
                    del request.session['sauce']
                    del request.session['crust']
                    topping_list = Topping.objects.all()
                    for topping in topping_list:
                        if str(topping) in request.session:
                            HasTopping(pizza_id=pizza, topping_name=topping).save()
                            del request.session[str(topping)]
                else:
                    pizza = Pizza.objects.get(pizza_name=request.session['pizza'])
                user = User.objects.filter(user_name=str(request.user))[:1].get()
                order_id = Orders.objects.all(). \
                            aggregate(Max('id'))['id__max'] + 1
                Orders(id=order_id, user_name=user, pizza_id=pizza).save()
                return HttpResponseRedirect('/goodbye')

            else:
                if request.session['pizza'] == '':
                    del request.session['pizza']
                    del request.session['sauce']
                    del request.session['crust']
                    topping_list = Topping.objects.all()
                    for topping in topping_list:
                        if str(topping) in request.session:
                            del request.session[str(topping)]
                request.session['order_cancelled'] = True
                return HttpResponseRedirect('/pizza')
        else:
            pizza = None
            crust = None
            sauce = None
            crust_calorie = 0
            sauce_calorie = 0
            top_cal_sum = 0
            toppings = []
            pizza_name = request.session['pizza']
            if pizza_name != '':
                pizza = Pizza.objects.get(pizza_name=request.session['pizza'])
                crust = Crust.objects.get(crust_name=pizza.crust_name)
                crust_calorie = crust.calorie
    
                sauce = Sauce.objects.get(sauce_name=pizza.sauce_name)
                sauce_calorie = sauce.calorie

                hasToppings = HasTopping.objects.filter(pizza_id=pizza.pizza_id)

                for ht in hasToppings:
                    topping = Topping.objects.get(topping_name=ht.topping_name)
                    toppings.append(topping)
                    top_cal_sum = top_cal_sum + topping.calorie
            else:
                crust = Crust.objects.get(crust_name=request.session['crust'])
                sauce = Sauce.objects.get(sauce_name=request.session['sauce'])
                crust_calorie = crust.calorie
                sauce_calorie = sauce.calorie
                topping_list = Topping.objects.all()
                topping_str = []
                for topping in topping_list:
                    if str(topping) in request.session:
                        topping_str.append(topping)
                for topping in topping_str:
                    topping = Topping.objects.get(topping_name=topping)
                    toppings.append(topping)
                    top_cal_sum += topping.calorie

            cal_total = top_cal_sum + sauce_calorie + crust_calorie
    
            context = {'crust': crust,
                        'sauce': sauce,
                        'toppings': toppings,
                        'cal_total': cal_total}
            if request.session['pizza'] == '':
                context['pizza'] = True
            else:
                context['pizza'] = False
            return render(request, settings.TEMPLATE_DIRS +
                         '/public_html/Confirmation/confirmation.html', context)
    else:
        return HttpResponseRedirect('/login')


def return_pizza(request):
    if request.user.is_authenticated():
        uorder_list = Orders.objects.filter(user_name=str(request.user))
        orders = Pizza.objects.filter(pizza_id__in=uorder_list).select_related()
       
        if request.method == 'POST' and 'return_pizza' in request.POST:
            request.session['return_pizza'] = request.POST['return_pizza']
            return HttpResponseRedirect('/waste')
        else:
            context = {'orders': orders}
            return render(request, settings.TEMPLATE_DIRS +
                          '/public_html/Return/return.html', context)

    else:

        return HttpResponseRedirect('/login')
            

# This function provides an appropriate response to a request for the
# returns/waste page.
def waste(request):

    if request.user.is_authenticated():
        if 'return_pizza' in request.session:
            pizza = Pizza.objects.get(pizza_name=str(request.session['return_pizza']))
            wasted_toppings = HasTopping.objects.filter(pizza_id=pizza.pizza_id).\
                                         select_related('orders__pizza_name')

            wasted_sauce = Pizza.objects.filter(pizza_name=str(request.session['return_pizza'])).\
                                 select_related('orders__pizza_name')

            wasted_crust = Pizza.objects.filter(pizza_name=str(request.['return_pizza'])).\
                                 select_related('orders__pizza_name')

            context = {'wasted_toppings': wasted_toppings,
                       'wasted_sauce': wasted_sauce,
                       'wasted_crust': wasted_crust}#,
                       #'orders': orders}

        else:
            return HttpResponseRedirect('/return')

        return render(request, settings.TEMPLATE_DIRS +
                           '/public_html/Return/waste.html', context)
    else:
        return HttpResponseRedirect('/login')


def disclaimer(request):
    if request.user.is_authenticated():
        if request.method == 'POST':
            if 'confirm' in request.POST:
                request.session['order_complete'] = False
                request.session['return_success'] = False
                request.session['order_cancelled'] = False
                return HttpResponseRedirect('/pizza')
            else:
                return HttpResponseRedirect('/logout')
        else:
            return render(request, settings.TEMPLATE_DIRS +
                                   '/public_html/Disclaimer/disclaimer.html')
    else:
        return HttpResponseRedirect('/login')


# This function provides the appropriate response to a request for the
# registration page.
def registration(request):
    if request.method == 'POST':
        post = request.POST
        form = UserCreationForm(post, request)
        if form.is_valid():
            username = post.get('username', '')
            password = post.get('password1', '')
            logger.debug('Is_Valid from registration')
            u = User(user_name=username, password=password)
            u.save()
            form.save()
            return HttpResponseRedirect('/disclaimer')
    registration_list = User.objects.all()  # Registration?
    context = {'registration_list': registration_list}
    return render(request, settings.TEMPLATE_DIRS +
                '/public_html/Registration/registration.html', context)

def goodbye(request):
    # Redirect to a success page.
    request.session['order_complete'] = True
    return render(request, settings.TEMPLATE_DIRS +
                  "/public_html/Goodbye/goodbye.html")
