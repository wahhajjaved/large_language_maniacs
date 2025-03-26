
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from application import app, db, login_required

from application.orders.models import Tilaus, OrderPizza
from application.orders.forms import OrderForm
from application.pizzas.models import Pizza
from application.auth.models import User



@app.route("/orders/", methods=["GET"])
@login_required(role='ADMIN')
def orders_index():
    return render_template("orders/list.html", orders=Tilaus.query.filter_by(sent=True))


@app.route("/orders/notdelivered", methods=["GET"])
@login_required(role='ADMIN')
def notdelivered_index():
    return render_template("orders/notdelivered.html", orders=Tilaus.query.filter_by(sent=False))


@app.route("/myorders/", methods=["GET"])
def myorders_index():
    id = current_user.get_id()
    return render_template("orders/myorders.html", orders=Tilaus.query.filter_by(account_id=id, sent=True))

@app.route("/myorders/<order_id>/", methods=["GET"])
def show_order(order_id):
    order = Tilaus.query.get(order_id)
    return render_template("orders/show_order.html", order_id=order_id, order=order, pizzas=Tilaus.find_pizzas_for_order(order_id))

@app.route("/orders/<order_id>/", methods=["POST"])
def orders_set_delivered(order_id):
    t=Tilaus.query.get(order_id)
    t.delivered=True
    db.session().commit()

    return redirect(url_for("orders_index"))

@app.route("/orders/send/", methods=["GET"])
@login_required(role="USER")
def send_order_main():
    user_id = current_user.get_id()
    user=User.query.get(user_id)
    if user.current_order == False:
        return render_template("orders/order.html")
    orders = Tilaus.query.filter_by(account_id=user_id)
    len = orders.count()
    if len == 0:
        len=1
    order = orders[len-1]

    id=order.id
    orderPizzas = OrderPizza.query.filter_by(order_id=id)
    pizzalist = [] 

    for item in orderPizzas:
        p_id = item.pizza_id
        pizza = Pizza.query.get(p_id)
        pizzalist.append(pizza)
    return render_template("orders/new.html", order = order, pizzas=pizzalist, form=OrderForm(), orderPizzas=orderPizzas)

@app.route("/orders/send/<order_id>/", methods=["GET", "POST"])
@login_required(role="USER")
def send_order(order_id):
    if request.method == 'GET':
        return render_template("orders/myorders.html", orders=Tilaus.query.filter_by(account_id=current_user.get_id()))
    order = Tilaus.query.get(order_id)
    form = OrderForm(request.form)
    user = User.query.get(current_user.get_id())
    if user.blacklist == True:
        return render_template("orders/message.html")
    order.name = form.name.data
    order.address = form.address.data
    order.phone = form.phone.data
    order.sent = True
    user_id = current_user.get_id()
    user = User.query.get(user_id)
    user.current_order = False
    db.session.commit()
    return redirect(url_for('myorders_index'))


@app.route("/orders/delete/<order_id>/<pizza_id>/,", methods=["GET", "POST"])
@login_required(role="USER")
def orderpizza_delete(order_id, pizza_id):
    list_of_ids=OrderPizza.find_orderpizza_id(order_id, pizza_id)
    id_value = 0
    for orderpizza_id in list_of_ids:
        for key in orderpizza_id:
            value = orderpizza_id[key]
            id_value = value
            print(id_value)

    orderpizza = OrderPizza.query.get(id_value)
    pizza = Pizza.query.get(pizza_id)
    o = Tilaus.query.get(order_id)
    o.price = float(o.price) - float(pizza.price)
    db.session.delete(orderpizza)
    if o.price == 0:
        db.session.delete(o)
        user = User.query.get(current_user.get_id())
        user.current_order = False
        db.session().commit()
        return redirect(url_for('pizzas_index'))   
    db.session().commit()
    flash('Removed item from order')
    return redirect(url_for('send_order_main'))

@app.route("/orders/delete/<order_id>/", methods=["POST"])
@login_required(role="USER")
def order_delete(order_id):
    o=Tilaus.query.get(order_id)
    orderpizzas = OrderPizza.query.filter_by(order_id=o.id)
    for orderpizza in orderpizzas:
        db.session.delete(orderpizza)
    user_id = current_user.get_id()
    user = User.query.get(user_id)
    user.current_order = False
    db.session.delete(o)
    flash('Your order was cancelled')
    db.session().commit()
    return redirect(url_for('pizzas_index'))