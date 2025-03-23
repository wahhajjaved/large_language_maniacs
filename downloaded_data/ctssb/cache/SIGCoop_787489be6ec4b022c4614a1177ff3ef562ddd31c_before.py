#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
import csv
from proteus import config, Model
from decimal import Decimal

"""
==================================Tax==================================
Fields de impuestos

Nombre
Descripción
Tipo
Cuenta de la factura/Código
Cuenta de la nota de crédito/Código
Importe
Tasa de cambio

No usados:
Cuenta de la factura/Nombre
Cuenta de la nota de crédito/Nombre
Cuenta de la factura/Código
Cuenta de la factura/Nombre
Secuencia
Dígitos de moneda
"""
def check_existance(ref_list):
    for model, search_param in ref_list:
        if not Model.get(model).find(search_param):
            return False
    return True

def translate_to_tax(_id, row, simulate):
    ret = {
    "id" : _id,
    "model" : "account.tax",
    "name": row["Nombre"],
    "description": row["Descripción"],
    "type" : row["Tipo"],
    "invoice_account" : ("account.account", [('code', '=', row["Cuenta de la factura/Código"])]),
    "credit_note_account" : ("account.account", [('code', '=', row["Cuenta de la nota de crédito/Código"])]),
    }
    if not check_existance([ret["invoice_account"], ret["credit_note_account"]]):
        return None

    if (ret["type"] == "fixed"):
        ret["amount"] = Decimal(row["Importe"])
    else:
        ret["rate"] = Decimal(row["Tasa de cambio"])

    return ret

"""
==================================Product==================================
Fields de producto

Nombre
Vendible
Tipo
Producto de precio independiente de la cantidad
Precio de lista
Precio de costo
UdM por defecto/Nombre
Cuenta de ingresos/Código
Impuestos de cliente/Nombre
Categoria/Nombre

Comprable false por defecto
Consumible false por defecto
"""
def check_category(cat_name, simulate):
    cats = Model.get('product.category').find([("name", "=", cat_name)])
    if not cats:
        if not simulate:
            cat = Model.get('product.category')()
            cat.name = cat_name
            cat.save()
            return cat
        return None
    return cats[0]

def check_uom(uom_name, simulate):
    uom = Model.get('product.uom').find([("name", "=", uom_name)])
    if not uom:
        if not simulate:
            nuom = {
                    "id":1,
                    "model":"product.uom",
                    "name": uom_name,
                    "symbol": "Kw",
                    "category": ("product.uom.category", [("name","=","Unidades")]),
            }
            return create_entity(nuom)
        return None
    return uom[0]

def translate_to_product(_id, row, simulate):
    ret = dict()
    ret["model"] = "product.template"
    ret["id"] = _id

    ret["name"] = row["Nombre"]
    ret["salable"] = row["Vendible"] == "True"
    ret["type"] = row["Tipo"]
    ret["dont_multiply"] = row["Producto de precio independiente de la cantidad"] == "True"
    ret["list_price"] = Decimal(row["Precio de lista"])
    ret["cost_price"] = Decimal(row["Precio de costo"])
    ret["tipo_producto"] = row["TipoProducto"].lower()
    ret["tipo_cargo"] = row["TipoCargo"].lower()
    ret["aplica_ap"] = row["AP"] == "True"
    ret["aplica_iva"] = row["Iva"] == "True"
    ret["aplica_iibb"] = row["IIBB"] == "True"

    check_category(row["Categoria/Nombre"], simulate)
    ret["category"] = ("product.category", [("name", "=", row["Categoria/Nombre"])])

    check_uom(row["UdM por defecto/Nombre"], simulate)
    ret["default_uom"] = ("product.uom", [("name", "=", row["UdM por defecto/Nombre"])])

    ret["account_revenue"] = ("account.account", [('code', '=', row["Cuenta de ingresos/Código"])])
    ret["customer_taxes"] = ["account.tax", [('name', '=', '%s' % i ) for i in row["Impuestos de cliente/Nombre"].split("#") if i]]

    if not check_existance([ret["account_revenue"]]):
        return None

    return ret

def check_price_list(price_list_name, simulate):
    pl = Model.get('product.price_list').find([("name", "=", price_list_name)])
    if not pl:
        if not simulate:
            npl = {
                    "id": 1,
                    "model": "product.price_list",
                    "name": price_list_name,
            }
            return create_entity(npl)
        return None
    return pl[0]

"""
==================================PriceList==================================


Fields de pricelist

Nombre
Líneas/Category/Nombre
Líneas/Producto/Nombre
Líneas/Cantidad
Líneas/Fórmula
Líneas/Secuencia
"""
def translate_to_price_list_line(_id, row, simulate):
    check_price_list(row["Nombre"], simulate)
    ret = {
            "model" : "product.price_list.line",
            "id" : _id,
            "price_list": ("product.price_list", [('name', '=', row["Nombre"])]),
            "product": ("product.product", [('name', '=', row["Líneas/Producto/Nombre"])]),
            "sequence" : long(row["Líneas/Secuencia"]),
            "formula" : row["Líneas/Fórmula"],
            "category" : ("product.category", [('name', '=', row["Líneas/Category/Nombre"])]),
    }
    if row["Líneas/Cantidad"]:
        ret["quantity"] = float(row["Líneas/Cantidad"])

    if not check_existance([ret["product"], ret["category"], ret["price_list"]]):
        return None

    return ret

"""
==================================ProductoConsumo==================================

Fields de producto consumo

Concepto
Producto
Tarifa
"""

concepto_to_int = dict([
    ('Cargo variable', '1'),
    ('Cargo variable Pico', '2'),
    ('Cargo variable Fuera de pico', '3'),
    ('Cargo variable Valle', '4'),
    ('Cargo variable Resto', '5'),
    ('Potencia Pico', '6'),
    ('Potencia Resto', '7'),
    ('Exceso potencia Pico', '8'),
    ('Exceso potencia Resto', '9'),
    ('Cargo perdida Transformador', '10'),
    ('Recargos x Bajo Cos Fi', '11'),
    ])

def translate_to_producto_consumo(_id, row, simulate):
    ret = {
            "model" : "sigcoop_wizard_ventas.producto_consumo",
            "id" : _id,
            "producto_id": ("product.product", [('name', '=', row["Producto"])]),
            "concepto": concepto_to_int[row["Concepto"]],
            "tarifa": ("product.price_list", [('name', '=', row["Tarifa"])]),
            "cantidad_fija":False,
            "cantidad":0,
    }
    return ret

def create_entities(csv_reader, translator, simulate=False):
    for _id, row in enumerate(csv_reader):
        #Traducimos cada fila a un diccionario
        entity_dict = translator(_id, row, simulate)
        if entity_dict is None:
            print "============= WARNING! No creamos el registro %s. ====================" % _id
            print "============= Checkea la linea %s +2 ===============" % _id
        elif not simulate:
            create_entity(entity_dict)
        else:
            print entity_dict

def create_entity(values):
    if not values.get("model"):
        print "Falta el modelo. Que estamos haciendo??"
        return None
    if (values.get("id") is None):
        print "Falta el id. Que estamos haciendo??"
        return None
    model = values.pop("model")
    _id = values.pop("id")

    print "Creando la entidad %s para el registro numero %s" % (model, _id)

    #Contructor del modelo
    const = Model.get(model)
    entity = const()
    save_for_last = []

    for k,v in values.iteritems():
        if (isinstance(v, tuple)):
            ref = Model.get(v[0]).find(v[1])[0]
            setattr(entity, k, ref)
        elif (isinstance(v, list)):
            constructor = Model.get(v[0])
            to_save = []
            for elem in v[1]:
                to_save.append(constructor.find([elem])[0])
            save_for_last.append((k, to_save))
        else:
            setattr(entity, k, v)
    for i in save_for_last:
        getattr(entity, i[0]).extend(i[1])
    entity.save()
    return entity


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('nombre-db', action="store", help="Nombre de la base de datos en la que insertar los registros.")
    parser.add_argument('password-admin-db', action="store", help="Password del usuario admin en la base de datos.")
    parser.add_argument('archivo-configuracion', action="store", help="Archivo trytond.conf que usas para correr el server. \n Si no sabes donde esta, escribi 'locate trytond.conf' en la consola, amigx.")
    parser.add_argument('-p','--productos', action="store", help="Crear productos a partir del archivo indicado.")
    parser.add_argument('-i','--impuestos', action="store", help="Crear impuestos a partir del archivo indicado.")
    parser.add_argument('-t','--tarifas', action="store", help="Crear tarifas a partir del archivo indicado.")
    parser.add_argument('-c','--consumos', action="store", help="Crear vinculo producto-consumos a partir del archivo indicado.")
    parsed = parser.parse_args()
    parsed = vars(parsed)

    print "Enhorabuena, los parametros son correctos!.\nConectando a trytond..."
    print "Activando GPS...detectando ubicación geoespacial...triangulando coordenadas...usted se encuentra en: EL SUCUCHITO"
    print "Los parametros son: nombre-db=%s password-admin-db=%s archivo-configuracion=%s" % (parsed["nombre-db"], parsed["password-admin-db"], parsed["archivo-configuracion"])

    c = config.set_trytond(
            database_name=sys.argv[1],
            database_type="postgresql",
            password=sys.argv[2],
            config_file=sys.argv[3])
    print "Conectado"

    #Ojo que el orden importa
    keys = [
        ("impuestos", translate_to_tax),
        ("productos", translate_to_product),
        ("tarifas", translate_to_price_list_line),
        ("consumos", translate_to_producto_consumo)
    ]
    for key, translator in keys:
        arch = parsed["i"]
        if arch:
            print "Vamos a crear las entidades de: %s" % arch
            with open(arch) as fi:
                print translator
                #create_entities(csv.DictReader(fi, delimiter=";"), translator, False)

    """

    print "Vamos a crear las entidades de %s" % str(sys.argv[4:])
    translators = [
            translate_to_tax,
            translate_to_product,
            translate_to_price_list_line,
            translate_to_producto_consumo,
    ]
    for filename, translator in zip(sys.argv[4:], translators):
        print "Creando entidades para %s" % filename
        with open(filename) as fi:
            create_entities(csv.DictReader(fi, delimiter=";"), translator, False)
    """

if __name__ == "__main__":
    main()
