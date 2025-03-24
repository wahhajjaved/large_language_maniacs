# -*- coding: utf-8 -*-

import re
import os
import mongoengine
from datetime import datetime
from datetime import timedelta
from collections import OrderedDict

from xlrd import open_workbook

import bson
import flask

from flask import Flask, request, abort, Response, redirect, url_for, flash, Blueprint, send_from_directory
from flask.ext.mongoengine import MongoEngine
from flask.templating import render_template
from flask import make_response
from flask_security.decorators import roles_required, login_required
from flask import jsonify
from user.models import User
from flask.ext.security import current_user
from mongoengine.queryset import DoesNotExist

from werkzeug import secure_filename
from settings import Config
from public.models import Product
from public.models import Menu
from public.models import Category
from public.models import MenuProduct
from public.models import Order


bp_public = Blueprint('public', __name__, static_folder='../static')


def is_food_row(row):
    if isinstance(row[0].value, float):
        return True
    return False


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1] in Config.ALLOWED_EXTENSIONS


def add_products_from_xls(filename):
    rb = open_workbook(filename, formatting_info=True)

    for sheet_index in xrange(5):
        sheet = rb.sheet_by_index(sheet_index)

        menu_date = re.findall(r'\d{2}.\d{2}.\d{2}', sheet.cell_value(0, 1)).pop()
        menu_date = datetime.strptime(menu_date, '%d.%m.%y')
        current_category = ''

        try:
            menu = Menu(date=menu_date).save()
        except flask.ext.mongoengine.mongoengine.NotUniqueError:
            menu = Menu.objects.get(date=menu_date)
            pass

        for rownum in range(sheet.nrows):
            rslc = sheet.row_slice(rownum)
            if is_food_row(rslc):
                try:
                    category = Category.objects.get(name=unicode(current_category))
                except DoesNotExist:
                    category = Category()
                    category.name = unicode(current_category)
                    category.save()

                product = Product()
                product.name = unicode(rslc[1].value)

                weight = unicode(rslc[2].value).replace('.0', '').strip('-')
                if not weight:
                    # grammi
                    maybe_weight_is_here = re.findall(ur'([0-9,]+)(\W?\u0433\u0440)', product.name)
                    if len(maybe_weight_is_here) > 0:
                        pieces = re.findall(ur'\u043f\u043e\W*\d+\W*\u043f', product.name)
                        weight, description = maybe_weight_is_here.pop()
                        product.name = product.name.replace(weight + description, '')
                        weight = weight + u' \u0433'
                        weight = weight.replace(',', '.')
                        if len(pieces) > 0:
                            piece_part = u' (' + pieces.pop() + u')'
                            weight = weight + piece_part
                            product.name = product.name.replace(piece_part, '')

                    # shtuki
                    maybe_weight_is_here = re.findall(u'(\d+)(\W?\u0448\u0442)', product.name)
                    if len(maybe_weight_is_here) > 0:
                        weight, description = maybe_weight_is_here.pop()
                        product.name = product.name.replace(weight + description, '')
                        weight = weight + u' \u0448\u0442'

                    # kuski
                    maybe_weight_is_here = re.findall(u'(\d+)(\W?\u043a)', product.name)
                    if len(maybe_weight_is_here) > 0:
                        weight, description = maybe_weight_is_here.pop()
                        product.name = product.name.replace(weight + description, '')
                        weight = weight + u' \u043a'

                    # litry
                    maybe_weight_is_here = re.findall(u'([0-9,]+)(\W?\u043b)', product.name)
                    if len(maybe_weight_is_here) > 0:
                        weight, description = maybe_weight_is_here.pop()
                        product.name = product.name.replace(weight + description, '')
                        weight = weight + u' \u043b'
                        weight = weight.replace(',', '.')

                    # millylitry
                    maybe_weight_is_here = re.findall(u'([0-9,]+)(\W?\u043c\u043b)', product.name)
                    if len(maybe_weight_is_here) > 0:
                        weight, description = maybe_weight_is_here.pop()
                        product.name = product.name.replace(weight + description, '')
                        weight = weight + u' \u043c\u043b'
                        weight = weight.replace(',', '.')
                else:
                    weight = weight + u' \u0433'

                def chg_quotes(text = None):
                    if not text:
                        return
                    counter = 0
                    text = list(text)
                    for i in range(len(text)):
                        if (text[i] == u'"'):
                            counter += 1
                            if (counter % 2 == 1):
                                text[i] = u'«'
                            else:
                                text[i] = u'»'
                    return ''.join(text)

                weight = re.sub(u'(\w)(\u0448\u0442)', '\\1 \\2', weight)
                product.name = chg_quotes(product.name)
                replacements = {
                    r'\.': u'',
                    r',(\W)': u', \\1',
                    r'[,. ]+$': u'',
                    u'Шоколад «Аленка» с начинкой Вареная сгущенка': u'Шоколад «Алёнка» с варёной сгущёнкой',
                    u'Щи Щавелевые с яйцом': u'Щи щавелевые с яйцом',
                    u'Лапша Грибная домашняя': u'Лапша грибная домашняя',
                    u'Суп Фасолевый с говядиной': u'Суп фасолевый с говядиной',
                    u'Борщ «Украинский» с курицей': u'Борщ украинский с курицей',
                    u'Суп Рыбный': u'Суп рыбный',
                    u'ПАСТА Таглиателли с курицей в сырном соусе': u'Паста таглиателли с курицей в сырном соусе',
                    u'Лапша пшеничная удон с курицей, бульоном и яйцом': u'Лапша пшеничная удон (курица, бульон и яйцо)'
                }

                for was, then in replacements.iteritems():
                    product.name = re.sub(was, then, product.name)

                compounds = re.findall(r'\(\W+\)', product.name)
                if len(compounds) > 0:
                    compound = compounds.pop()
                    product.compound = re.sub(r'\((\W+)\)', '\\1', compound)
                    product.name = product.name.replace(compound, '')

                product.weight = weight
                product.cost = int(rslc[3].value)
                product.category = category

                try:
                    product.save()
                except flask.ext.mongoengine.mongoengine.NotUniqueError:
                    product = Product.objects.get(name=product.name,
                                                  weight=product.weight,
                                                  cost=product.cost)
                except bson.errors.InvalidBSON:
                    continue

                pmconnection = MenuProduct()
                pmconnection.menu = menu
                pmconnection.product = product
                try:
                    pmconnection.save()
                except flask.ext.mongoengine.mongoengine.NotUniqueError:
                    continue
            else:
                current_category = rslc[0].value
                replacements = {
                    u'ПЕРВЫЕ БЛЮДА': u'Первые блюда',
                    u'ВТОРЫЕ БЛЮДА': u'Вторые блюда',
                    u'САЛАТЫ ЗАПРАВЛЕННЫЕ  И ЗАКУСКИ': u'Салаты заправленные и закуски',
                    u'САЛАТЫ НЕ ЗАПРАВЛЕННЫЕ': u'Салаты незаправленные',
                    u'ЗАПРАВКИ К САЛАТАМ И СОУСЫ': u'Заправки к салатам и соуса',
                    u'ПИРОЖНОЕ': u'Пирожные',
                }
                for was, then in replacements.iteritems():
                    current_category = re.sub(was, then, current_category)


@bp_public.route('/')
def index():
    return render_template('index.html')


@bp_public.route('/robots.txt')
def static_from_root():
    return send_from_directory(bp_public.static_folder, request.path[1:])


@bp_public.route('/order', methods=['POST'])
@login_required
def order():
    cuser = User.objects.get(id=current_user.id)
    product_id = request.values.get('product')
    menu_id = request.values.get('menu')

    try:
        menu = Menu.objects.get(id=menu_id)
    except DoesNotExist:
        pass

    try:
        product = Product.objects.get(id=product_id)
    except DoesNotExist:
        pass

    try:
        myorder = Order.objects.get(menu=menu, product=product, user=cuser)
        myorder.count += 1
        myorder.save()
    except DoesNotExist:
        myorder = Order()
        myorder.menu = menu
        myorder.product = product
        myorder.user = cuser
        myorder.save()

    return jsonify(count=myorder.count,
                   name=product.name,
                   cost=product.cost)

@bp_public.route('/cancel', methods=['POST'])
@login_required
def cancel():
    cuser = User.objects.get(id=current_user.id)
    product_id = request.values.get('product')
    menu_id = request.values.get('menu')

    try:
        menu = Menu.objects.get(id=menu_id)
    except DoesNotExist:
        pass

    try:
        product = Product.objects.get(id=product_id)
    except DoesNotExist:
        pass

    try:
        order = Order.objects.get(menu=menu, product=product, user=cuser)
    except DoesNotExist:
        return jsonify(count=0,
                       name=product.name,
                       cost=0)

    if order.count > 1:
        order.count -= 1
        count = order.count
    else:
        count = 0
        order.delete()
    order.save()

    return jsonify(count=count,
                   name=product.name,
                   cost=product.cost)


@bp_public.route('/menu')
@login_required
def view_menu():
    cuser = User.objects.get(id=current_user.id)
    now = datetime.today()
    if now.hour >= 15:
        # tomorrow
        now = datetime.today() + timedelta(days=2)
    else:
        now = datetime.today() + timedelta(days=1)

    menu_date = '{year}-{month}-{day}'.format(year=now.year,
                                              month=now.month,
                                              day=now.day)
    menu = Menu.objects(date=menu_date).first()
    all_products = MenuProduct.objects.filter(menu=menu).values_list('product').all_fields()
    ordered_products = Order.objects.filter(product__in=all_products, menu=menu, user=cuser).all_fields()

    products = OrderedDict()
    for product in all_products:
        order_count = 0
        for order in ordered_products:
            if order.product == product:
                order_count = order.count
                break

        if not products.get(product.category.name):
            products[product.category.name] = []

        products[product.category.name].append({
            'id': product.id,
            'category_id': product.category.id,
            'name': product.name,
            'weight': product.weight,
            'cost': product.cost,
            'compound': product.compound,
            'count': order_count,
        })

    months = [u'января',
              u'февраля',
              u'марта',
              u'апреля',
              u'мая',
              u'июня',
              u'июля',
              u'августа',
              u'сентбяря',
              u'октября',
              u'ноября',
              u'декабря']

    weekdays = [u'понедельник',
                u'вторник',
                u'среду',
                u'четверг',
                u'пятницу',
                u'субботу',
                u'воскресение']

    if menu and products:
        return render_template('viewmenu.html',
                               products=products,
                               menu_id=menu.id,
                               menu_day=now.day,
                               menu_weekday=weekdays[now.weekday()],
                               menu_month=months[now.month-1],
                               menu_year=now.year)
    else:
        return render_template('500.html'), 500


@bp_public.route('/loadmenu', methods=['GET', 'POST'])
@login_required
def load_menu():
    if request.method == 'GET':
        return render_template('loadmenu.html')
    elif request.method == 'POST':
        menu = request.files['menu']
        if menu and allowed_file(menu.filename):
            filename = secure_filename(menu.filename)
            path = os.path.join(Config.UPLOAD_FOLDER, filename)
            menu.save(path)
            try:
                add_products_from_xls(path)
            except IndexError:
                return render_template('loadmenu.html', status='error')
            return render_template('loadmenu.html', status='success')
        else:
            return render_template('loadmenu.html', status='error')
