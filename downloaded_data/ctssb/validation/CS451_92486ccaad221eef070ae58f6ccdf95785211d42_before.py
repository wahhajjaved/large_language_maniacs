import tornado.ioloop
import tornado.web
import tornado.websocket
import json
from user import User, UserStatus
import pychess
import random

# {id: (game, whitePlayerWebsocket, blackPlayerWebsocket)}
gamesList = {}

connectedUsers = {}
websocketClients = {}

class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        if not self.get_secure_cookie('username'):
            return None
        return self.get_secure_cookie('username')

class MainHandler(BaseHandler):
    def get(self):
        #if self.current_user is not None:
            #self.render("./jsGame/html/lobby.html", currentUser=self.current_user)
        #else:
            self.render("./jsGame/html/index.html")

class LobbyHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("./jsGame/html/lobby.html", currentUser=self.get_secure_cookie('username').decode('ascii'))

class GameHandler(tornado.web.RequestHandler):
    def put(self):
        gameID = random.randint(1, 1024)
        while gameID in gamesList.keys():
            gameID = random.randint(1, 1024)
        newGame = pychess.Game()
        player1 = self.get_secure_cookie('username').decode('ascii')
        player2 = self.get_body_argument('player2')
        gamesList[gameID] = [newGame, player1, player2]
        self.set_secure_cookie('gameID', str(gameID))
        self.set_secure_cookie('player_color', 'black')
        websocketClients[player2].write_message(tornado.escape.json_encode({'function': 'joining_game', 'gameID': str(gameID)}))
        self.write(tornado.escape.json_encode({'gameID': gameID}))

class GamePageHandler(tornado.web.RequestHandler):
    def get(self, gameID):
        color = ''
        if self.get_secure_cookie('player_color') is None:
            color = 'white'
            self.set_secure_cookie('player_color', 'white')
            self.set_secure_cookie('gameID', str(gameID))
        else:
            color = 'black'
        self.render("./jsGame/html/game.html", gameID=gameID, color=color, currentUser=self.get_secure_cookie('username').decode('ascii'))

class UserHandler(tornado.web.RequestHandler):
    def get(self):
        userList = []
        for user in connectedUsers.keys():
            elem = connectedUsers[user].__dict__.copy()
            if elem['status'] is not UserStatus.IN_GAME and not elem['username'] == self.get_secure_cookie('username').decode('ascii'):
                elem['status'] = elem['status'].name
                userList.append(elem)
        userList = sorted(userList, key = lambda user: user['username'])
        self.write(tornado.escape.json_encode({'users': userList}))

    def put(self):
        username = self.get_body_argument("username")
        if username not in connectedUsers.keys():
            newUser = User(username)
            connectedUsers[username] = newUser
            self.set_secure_cookie('username', username)
            raise tornado.web.HTTPError(201)
        else:
            raise tornado.web.HTTPError(409)

    def post(self):
        self.write("modifying user")

class UserDataHandler(tornado.web.RequestHandler):
    def get(self, username):
        userDict = connectedUsers[username].__dict__.copy()
        userDict['status'] = userDict['status'].name
        self.write(tornado.escape.json_encode({ 'user_data': userDict }))

class InviteSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        websocketClients[self.get_secure_cookie('username').decode('ascii')] = self
        connectedUsers[self.get_secure_cookie('username').decode('ascii')].status = UserStatus.AVAILABLE

    def on_message(self, message):
        messageDict = tornado.escape.json_decode(message)
        if messageDict['function'] == "send":
            if connectedUsers[messageDict['target']].status is UserStatus.AVAILABLE:
                connectedUsers[messageDict['target']].status = UserStatus.PENDING_INVITE
                connectedUsers[self.get_secure_cookie('username').decode('ascii')].status = UserStatus.PENDING_INVITE
                websocketClients[messageDict['target']].write_message(tornado.escape.json_encode({'sender': self.get_secure_cookie('username').decode('ascii')}))
                self.write_message(tornado.escape.json_encode({'status': 'success'}))

            else:
                self.write_message(tornado.escape.json_encode({'status': 'failed'}))

        elif messageDict['function'] == "accept":
            connectedUsers[self.get_secure_cookie('username').decode('ascii')].status = UserStatus.IN_GAME
            connectedUsers[messageDict['target']].status = UserStatus.IN_GAME
            self.write_message(tornado.escape.json_encode({'function': 'create_game', 'target': messageDict['target']}))

        elif messageDict['function'] == "decline":
            connectedUsers[self.get_secure_cookie('username').decode('ascii')].status = UserStatus.AVAILABLE
            connectedUsers[messageDict['target']].status = UserStatus.AVAILABLE
            websocketClients[messageDict['target']].write_message(tornado.escape.json_encode({'status': 'declined'}))

        elif messageDict['function'] == "cancel":
            connectedUsers[self.get_secure_cookie('username').decode('ascii')].status = UserStatus.AVAILABLE
            connectedUsers[messageDict['target']].status = UserStatus.AVAILABLE
            websocketClients[messageDict['target']].write_message(tornado.escape.json_encode({'status': 'cancelled'}))
            self.write_message(tornado.escape.json_encode({'status': 'cancelled'}))

    def close(self):
        del websocketClients[self.get_secure_cookie('username').decode('ascii')]
        print("Socket closed")

class GameSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        for key, values in gamesList.items():
            if self.get_secure_cookie('username').decode('ascii') in values:
                values[values.index(self.get_secure_cookie('username').decode('ascii'))] = self
                break

    def on_message(self, clientMessage):
        message = tornado.escape.json_decode(clientMessage)
        gameID = int(self.get_secure_cookie('gameID').decode('ascii'))
        gameBoard = gamesList[gameID][0].board

        if message['function'] == 'get_moves':
            if pychess.Color.fromString(self.get_secure_cookie('player_color').decode('ascii')) == gamesList[gameID][0].current:
                self.write_message(tornado.escape.json_encode({"function": "list_moves", "moves": gamesList[gameID][0].getPossibleMovesJSON()}))

            else:
                self.write_message(tornado.escape.json_encode({"function": "list_moves", "moves": []}))

        elif message['function'] == 'make_move':
            fromPosLetter = message['move']['fromPos']['rowcol']
            toPosLetter = message['move']['toPos']['rowcol']
            fromPos = pychess.Position(8 - int(fromPosLetter[1]), pychess.ColLetter.fromString(fromPosLetter[0]).value)
            toPos = pychess.Position(8 - int(toPosLetter[1]), pychess.ColLetter.fromString(toPosLetter[0]).value)

            move = pychess.Move(fromPos, toPos)

            if pychess.Color.fromString(self.get_secure_cookie('player_color').decode('ascii')) == gamesList[gameID][0].current and gameBoard.isValidMove(move, gamesList[gameID][0].current):
                gamesList[gameID][0].applyMove(move)

                index = 1 if gamesList[gameID][2] == self else 2
                index2 = 2 if index == 1 else 1

                gamesList[gameID][index].write_message(tornado.escape.json_encode({'state': gameBoard.state.name, 'updated_board': gamesList[gameID][0].board.getBoardJson()}))
                gamesList[gameID][index2].write_message(tornado.escape.json_encode({'function': 'success', 'state': gameBoard.state.name}))

                if gameBoard.state == pychess.State.BLACK_WIN or gameBoard.state == pychess.State.WHITE_WIN:
                    print("player win")
                    # index2 win
                    connectedUsers[gamesList[gameID][index2].get_secure_cookie('username').decode('ascii')].updateRating(connectedUsers[gamesList[gameID][index].get_secure_cookie('username').decode('ascii')], "W")
                    gamesList[gameID][1].write_message(tornado.escape.json_encode({'function': 'game_over', 'reason': gameBoard.state.name}))
                    gamesList[gameID][2].write_message(tornado.escape.json_encode({'function': 'game_over', 'reason': gameBoard.state.name}))
                    del gamesList[gameID]

                elif gameBoard.state == pychess.State.DRAW:
                    print('draw')
                    # no one wins
                    connectedUsers[gamesList[gameID][index2].get_secure_cookie('username').decode('ascii')].updateRating(connectedUsers[gamesList[gameID][index].get_secure_cookie('username').decode('ascii')], "D")
                    gamesList[gameID][1].write_message(tornado.escape.json_encode({'function': 'game_over', 'reason': gameBoard.state.name}))
                    gamesList[gameID][2].write_message(tornado.escape.json_encode({'function': 'game_over', 'reason': gameBoard.state.name}))
                    del gamesList[gameID]

                gamesList[gameID][index].write_message(tornado.escape.json_encode({"function": "list_moves", "moves": gamesList[gameID][0].getPossibleMovesJSON()}))

            else:
                self.write_message(tornado.escape.json_encode({'function': 'error', 'status': 'invalid_move'}))

        elif message['function'] == 'board_state':
            self.write_message(tornado.escape.json_encode({'state': gameBoard.state.name, 'updated_board': gamesList[gameID][0].board.getBoardJson()}))

        elif message['function'] == 'forfeit':
            playerToForfeit = self.get_secure_cookie('username').decode('ascii')
            gameID = int(self.get_secure_cookie('gameID').decode('ascii'))
            index = 1 if gamesList[gameID][2] == self else 2
            gamesList[gameID][index].write_message(tornado.escape.json_encode({'function': 'request_forfeit', 'username': playerToForfeit}))
            connectedUsers[playerToForfeit].updateRating(connectedUsers[gamesList[gameID][1 if index == 2 else 2].get_secure_cookie('username').decode('ascii')], "L")
            del gamesList[gameID]

    def close(self):
        for key, values in gamesList.items():
            if self.get_secure_cookie('username').decode('ascii') == value:
                self.clear_cookie('player_color')
                self.clear_cookie('gameID')
                del values[values.index(self)]
                otherPlayer = 1 if values.index(self) == 2 else 2
                values[otherPlayer].write_message(tornado.escape.json_encode({'status': 'disconnected', 'username': value.get_secure_cookie('username').decode('ascii')}))
                break

def make_app():
    return tornado.web.Application([
        (r'/public/(.*)', tornado.web.StaticFileHandler, {'path': './jsGame/'}),
        (r'/lobby', LobbyHandler),
        (r"/", MainHandler),
        (r"/invite", InviteSocketHandler),
        (r"/users", UserHandler),
        (r"/user/(.*)/data", UserDataHandler),
        (r'/game', GameHandler),
        (r"/game/([0-9]+)", GamePageHandler),
        (r'/game/socket', GameSocketHandler),
    ], debug=True, cookie_secret='u5sJkk6UxCQB2X1CAehe7k9wxzBbrAFO9no3BoAT0Bu+zQabEnmXbwBtQCL5WbpPo/s=')

if __name__ == "__main__":
    app = make_app()
    app.listen(8080)
    tornado.ioloop.IOLoop.current().start()
