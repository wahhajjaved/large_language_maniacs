# -*- coding: utf-8 -*-
from flask import Flask, request, json, Response

app = Flask(__name__)

# OPTIONAL TO ADD LATER
# getTimeAndData to single task when client send request

usersDict = {}
usersDict['rafal'] = {'token': 'rafaltoken', 'password': 'rafal', 'userID': 1, 'tasks': {}}
# usersDict['pawel'] = {'token': 'paweltoken', 'password': 'pawel', 'userID': 2}
# usersDict['piotr'] = {'token': 'piotrtoken', 'password': 'piotr', 'userID': 3}

tasksDict = {}
tasksDict[1] = {"title": "Projekt z programowania internetowego",
                "details": "Projekt, w ktorym piszemy wlasna usluge sieciowa + 2 rodzaje klientow",
                "timeToDo": "30.01.2016",
                "tag": "school",
                "done": 0,
                "id": 1
                }
tasksDict[2] = {"title": "Sprzątnięćie kuchni",
                "details": "Dokladne wyczyszczenie kuchenki i mikrofali",
                "timeToDo": "15.02.2016",
                "tag": "home",
                "done": 1,
                "id": 2
                }
tasksDict[3] = {"title": "Specyfikacja dla klienta",
                "details": "Napisanie szczegolowej specyfikacji dla klienta dotyczacej aplikacji",
                "timeToDo": "25.09.2016",
                "tag": "work",
                "done": 0,
                "id": 3
                }
tokenDict = {}
lastID = len(tasksDict)

tagArray = ["work", "school", "home"]


@app.route('/login', methods=['POST'])
def login():
    requestData = None
    responseData = None
    status = 400
    requestDataRead = False

    try:
        requestData = json.loads(request.data)
        requestDataRead = True
    except:
        responseData = {'error': 'could not read request from client'}

    if requestDataRead:
        if 'login' in requestData and 'password' in requestData:
            if requestData['login'] in usersDict:
                if usersDict[requestData['login']]['password'] == requestData['password']:
                    responseData = {
                        'info': "OK",
                        'token': usersDict[requestData['login']]['token'],
                        'userID': usersDict[requestData['login']]['userID']
                    }
                    status = 200
                else:
                    responseData = {'error': 'invalid login or password'}
            else:
                responseData = {'error': 'there isnt that user in database'}
        else:
            responseData = {'error': 'empty login or password'}

    responseJsonData = json.dumps(responseData)
    responseHeaders = {'Content-Type': 'application/json'}
    response = Response(responseJsonData,
                        status=status,
                        mimetype="application/json",
                        headers=responseHeaders)
    return response


@app.route("/notdone", methods=['GET'])
def notdone():
    requestData = None
    requestDataRead = False
    status = 400

    try:
        requestData = request.headers
        requestDataRead = True
    except:
        responseData = {"error": "bad token give to request"}

    if requestDataRead:
        # TODO add searching login based on given in request token
        if requestData['token'] == usersDict['rafal']['token']:
            # TODO dodac funkcje, ktora liczy niewykonane zadania
            undone = 0
            for task in tasksDict:
                if tasksDict[task]['done'] == 0:
                    undone += 1
            responseData = {"undone": undone}
            status = 200
        else:
            responseData = {"error": "couldn't match login to requested token(probably there isn't any user with requested token)"}
    else:
        responseData = {"error": "bad syntax of request(bad oken has been given"}

    responseJsonData = json.dumps(responseData)
    responseHeaders = {'Content-Type': 'application/json'}
    response = Response(responseJsonData,
                        status=status,
                        mimetype="application/json",
                        headers=responseHeaders)

    return response


@app.route("/tasks", methods=['POST'])
def addTask():
    if 'token' in request.headers:
        global lastID
        status = 400
        requestDataRead = False
        if request.headers['token'] == usersDict['rafal']['token']:

            try:
                requestData = json.loads(request.data)
                requestDataRead = True

                if requestDataRead:

                    if ('title' in requestData) and ('details' in requestData) and ('timeToDo' in requestData) and (
                        'tag' in requestData):

                        title = requestData['title']
                        details = requestData['details']
                        timeToDo = requestData['timeToDo']
                        tag = requestData['tag']
                        done = 0
                        global lastID
                        print(lastID)
                        id = lastID + 1
                        lastID += 1

                        tasksDict[lastID] = {
                            'title': title,
                            'details': details,
                            'timeToDo': timeToDo,
                            'tag': tag,
                            'done': done,
                            'id': id
                        }

                        responseData = tasksDict[lastID]
                        status = 201
                    else:
                        responseData = {"error": "klient nie podal wszystkich wymaganych pol requesta"}
                else:
                    responseData = {"error": "request klienta nie zostal prawidlowo odczytany"}

            except:
                responseData = {"error": "blad podczas odczytywania requesta klienta"}
        else:
            responseData = {"error": "brak uzytkownika, ktory pasuje do podanego przez klienta tokenu"}
    else:
        responseData = {"error": "klient nie podał tokenu w requescie"}

    responseJsonData = json.dumps(responseData)
    responseHeaders = {"Content-Type": "application/json"}
    response = Response(responseJsonData, status=status, mimetype="application/json", headers=responseHeaders)
    return response


@app.route("/tasks", methods=['GET'])
def tasks():
    status = 400

    if 'token' in request.headers:
        # TODO dodac dict of token
        if request.headers['token'] in usersDict['rafal']['token']:
            listOfTasks = []

            for task in tasksDict:
                print(tasksDict[task])
                listOfTasks.append(tasksDict[task])

            print listOfTasks
            status = 200
            responseData = listOfTasks
        else:
            responseData = {"error": "token from headers does not match to any user in userDict"}
    else:
        responseData = {"error": "in request.headers was not token"}

    responseJsonData = json.dumps(responseData)
    responseHeaders = {'Content-Type': 'application/json'}
    response = Response(responseJsonData,
                        status=status,
                        mimetype="application/json",
                        headers=responseHeaders)
    return response


# def countUndoneTask():

@app.route("/tasks/" + "<int:id>", methods=['GET'])
def getTasks(id):
    status = 400

    if 'token' in request.headers:
        if request.headers['token'] == usersDict['rafal']['token']:
            if id in tasksDict:

                task = tasksDict[id]
                responseData = task
                print(responseData)
                status = 200
            else:
                responseData = {"error": "brak zadania o danym ID w bazie danych"}
        else:
            responseData = {"error": "brak uzytkownika pasującego do podanego przez klienta tokenu"}
    else:
        responseData = {"error": "brak tokenu w requescie "}

    responseJsonData = json.dumps(responseData)
    responseHeaders = {"Content-Type": "application/json"}
    response = Response(responseJsonData,
                        status=status,
                        mimetype="application/json",
                        headers=responseHeaders)
    return response


# @app.route("/tasks/" + "<int:id>", methods=['PUT'])
# def editDoneTasks(id):
#     status = 404
#     if 'token' in request.headers:
#         if request.headers['token'] == usersDict['rafal']['token']:
#             if id in tasksDict:
#
#                 try:
#                     requestData = json.loads(request.data)
#                     requestDataRead = True
#
#                     if requestDataRead:
#                         done = requestData['done']
#
#                         if done:
#                             responseDone = 0
#                         else:
#                             responseDone = 1
#
#                         tasksDict[id] = {
#                             'done': responseDone,
#                         }
#                         responseData = tasksDict[id]
#
#                 except:
#                     responseData = {"error":"request klienta nie zostal prawidlowo odczytany"}
#             else:
#                 responseData = {"error": "brak zadania o danym ID w bazie danych"}
#
#         else:
#             responseData = {"error": "brak uzytkownika pasującego do podanego przez klienta tokenu"}
#     else:
#         responseData = {"error": "brak tokenu w requescie "}
#
#     responseJsonData = json.dumps(responseData)
#     responseHeaders = {"Content-Type": "application/json"}
#     response = Response(responseJsonData, status=status, mimetype="application/json", headers=responseHeaders)
#     return response

@app.route("/tasks/" + "<int:id>", methods=['PUT'])
def editDoneTasks(id):
    status = 404
    if 'token' in request.headers:
        if request.headers['token'] == usersDict['rafal']['token']:
            if id in tasksDict:

                try:
                    requestData = json.loads(request.data)
                    requestDataRead = True
                    print ("dane do edycji od klienta")
                    print requestData
                    if requestDataRead:
                        print("jest?")
                        print (requestData)
                        title = requestData['title']
                        details = requestData['details']
                        timeToDo = requestData['timeToDo']
                        tag = requestData['tag']
                        done = requestData['done']
                        print("daneeee")
                        print ("title %s, details %s, timeToDo %s, tag %s, id %s, done%s ", title, details, timeToDo, tag, id, done)

                        tasksDict[id]['title'] = title
                        tasksDict[id]['details'] = details
                        tasksDict[id]['timeToDo'] = timeToDo
                        tasksDict[id]['tag'] = tag
                        tasksDict[id]['title'] = title
                        print("EDITED TASK DICT DLA ID")
                        print(tasksDict[id])
                        responseData = tasksDict[id]
                        status = 200
                        # if done:
                        #     responseDone = 0
                        # else:
                        #     responseDone = 1
                        #
                        # tasksDict[id] = {
                        #     'done': responseDone,
                        # }
                        # responseData = tasksDict[id]

                except:
                    responseData = {"error": "request klienta nie zostal prawidlowo odczytany"}
            else:
                responseData = {"error": "brak zadania o danym ID w bazie danych"}

        else:
            responseData = {"error": "brak uzytkownika pasującego do podanego przez klienta tokenu"}
    else:
        responseData = {"error": "brak tokenu w requescie "}

    responseJsonData = json.dumps(responseData)
    responseHeaders = {"Content-Type": "application/json"}
    response = Response(responseJsonData, status=status, mimetype="application/json", headers=responseHeaders)
    return response


@app.route("/tasks/" + "<int:id>", methods=['DELETE'])
def deleteTasks(id):
    status = 404
    print("delete")
    if 'token' in request.headers:
        if request.headers['token'] == usersDict['rafal']['token']:
            if id in tasksDict:

                global tasksDict
                del tasksDict[id]

                listOfTasks = []

                for task in tasksDict:
                    listOfTasks.append(tasksDict[task])

                status = 200
                responseData = listOfTasks
            else:
                responseData = {"error": "brak zadania o danym ID w bazie danych"}

        else:
            responseData = {"error": "brak uzytkownika pasującego do podanego przez klienta tokenu"}
    else:
        responseData = {"error": "brak tokenu w requescie "}

    responseJsonData = json.dumps(responseData)
    responseHeaders = {'Content-Type': 'application/json'}
    response = Response(responseJsonData,
                        status=status,
                        mimetype="application/json",
                        headers=responseHeaders)
    return response


@app.route("/tasks/" + "<tag>", methods=['GET'])
def getByTag(tag):
    status = 200

    if 'token' in request.headers:
        if request.headers['token'] == usersDict['rafal']['token']:
            if tag in tagArray:

                tasksListByTag = []

                for task in tasksDict:
                    if tasksDict[task]['tag'] == str(tag):
                        print(tasksDict[task])
                        tasksListByTag.append(tasksDict[task])

                responseData = tasksListByTag

                status = 200
            else:
                responseData = {"error": "brak podanego w requescie tagu w bazie danych"}
        else:
            responseData = {"error": "brak uzytkownika pasującego do podanego przez klienta tokenu"}
    else:
        responseData = {"error": "brak tokenu w requescie "}

    responseJsonData = json.dumps(responseData)
    responseHeaders = {"Content-Type": "application/json"}
    response = Response(responseJsonData,
                        status=status,
                        mimetype="application/json",
                        headers=responseHeaders)
    return response


if __name__ == '__main__':
    app.run(port=5000, debug=True)
