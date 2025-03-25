#!/usr/bin/python
#encoding:UTF-8
import MySQLdb


def conectar_db():
    db = MySQLdb.connect(host="172.18.2.2",    # your host, usually localhost
                     port=3306,
                     user="alm-user",         # your username
                     passwd="egc",  # your password
                     db="almacenamiento")        # name of the data base
    return db


def desconectar_db(db):
    db.close()


# Consulta


def comprobar_token(db, token):
    cursor = db.cursor()

    cursor.execute("SELECT token FROM tokens WHERE token=%(token)s",
                   {'token': token})

    valido = True
    if not cursor.fetchall():
        valido = False

    return valido


def get_voto(db, token_usuario, token_votacion):
    cursor = db.cursor()
    result = []

    cursor.execute("SELECT * FROM votos WHERE token_usuario=%(token_usuario)s and token_votacion=%(token_votacion)s",
                   {'token_usuario': token_usuario, 'token_votacion': token_votacion})

    for row in cursor.fetchall():
        result.append({
            "id": row[0],
            "token_usuario": row[1],
            "token_votacion": row[2],
            "token_pregunta": row[3],
            "token_respuesta": row[4],
        })

    return result


def get_voto_pregunta(db, token_usuario, token_votacion, token_pregunta):
    cursor = db.cursor()
    result = []

    cursor.execute("SELECT * FROM votos WHERE token_usuario=%(token_usuario)s and token_votacion=%(token_votacion)s and token_pregunta=%(token_pregunta)s",
                   {'token_usuario': token_usuario, 'token_votacion': token_votacion, 'token_pregunta': token_pregunta})

    for row in cursor.fetchall():
        result.append({
            "id": row[0],
            "token_usuario": row[1],
            "token_votacion": row[2],
            "token_pregunta": row[3],
            "token_respuesta": row[4],
        })

    return result


def consultar_votos_pregunta(db, token_votacion, token_pregunta):
    cursor = db.cursor()
    result = []

    cursor.execute("SELECT * FROM votos WHERE token_votacion=%(token_votacion)s and token_pregunta=%(token_question)s",
                   {'token_votacion': token_votacion, 'token_question': token_pregunta})

    for row in cursor.fetchall():
        result.append({
            "id": row[0],
            "token_usuario": row[1],
            "token_votacion": row[2],
            "token_pregunta": row[3],
            "token_respuesta": row[4],
        })

    return result

# Inserción



def guardar_voto(db, token_usuario, token_votacion, token_pregunta, token_respuesta):
    cursor = db.cursor()

    add_vote = "INSERT INTO votos (token_usuario, token_votacion, token_pregunta, token_respuesta) VALUES (%s, %s, %s, %s)"
    data_vote1 = (token_usuario, token_votacion, token_pregunta, token_respuesta)
    cursor.execute(add_vote, data_vote1)

    db.commit()