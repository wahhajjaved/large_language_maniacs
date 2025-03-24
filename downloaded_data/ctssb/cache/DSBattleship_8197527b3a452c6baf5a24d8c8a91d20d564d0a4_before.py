import uuid
import pika
import threading


serverID = uuid.uuid1()

#print serverID

connection = pika.BlockingConnection(pika.ConnectionParameters(
    host='127.0.0.1', port=5672))

channel = connection.channel()

channel.queue_declare(queue='rpc_queue_durable_' + str(serverID), durable=True)
channel.queue_declare(queue='servers_queue', durable=True)


def lifeCondition():
    time = 0.1
    response = str(serverID)
    channel.basic_publish(exchange='',
                          routing_key='servers_queue',
                          properties=pika.BasicProperties(delivery_mode=2, expiration=str(int(time * 1000))),
                          body=str(response))
    threading.Timer(time, lifeCondition).start()


lifeCondition()


class GameSession:
    def __init__(self, login, size):
        self.id = str(uuid.uuid4())
        self.ships = []
        self.players = []
        self.master_client = login
        self.players.append(login)
        self.state = 0
        self.size = size
        self.curActive = -1
        self.hit_messages = {}

    def disconnect(self, player_id):
        return 0

    def leave(self, player_id):
        self.players[player_id] = 'Leaved'
        for ship in self.ships:
            if ship.owner_login == player_id:
                self.ships.remove(ship)

    def addPlayer(self, login):
        self.players.append(login)

    def addShipsOfPlayer(self, id, ships):
        for i in range(len(ships)):
            entity = ships[i].split(',')
            x = int(entity[0])
            y = int(entity[1])
            length = int(entity[2])
            direction = entity[3]  # 0 - horizontal, 1 - vertical
            coordinates = []
            if direction == '0':
                for j in range(length):
                    coordinates.append((x, y + j))
            elif direction == '1':
                for j in range(length):
                    coordinates.append((x + j, y))
            ship = Ship(id, length, coordinates)
            self.ships.append(ship)
        return 0

    def startGame(self):
        self.state = 1
        self.newRound()
        return 0

    def currentActivePlayers(self):
        count = 0
        for player in Players:
            if player.type == "Player":
                count += 1
        return count

    def newRound(self):
        self.hitconditions = {}
        self.curActive += 1
        self.curActive %= len(self.players)
        return

    def makeHit(self, login, coordinate):
        hit_conditions = {}  # values: 0 - missed, 1 - hitted, 2 - sinked, 3 - hiter; keys: players_logins
        hit_conditions[login] = 3
        hitted_players = []
        sinked_players = []
        for i in range(len(self.ships)):
            if self.ships[i].owner_login != login and coordinate in self.ships[i].coordinates:
                self.ships[i].coordinates.remove(coordinate)
                if len(self.ships[i].coordinates) == 0:
                    hit_conditions[self.ships[i].owner_login] = 2
                    sinked_players.append(self.ships[i].owner_login)
                    Players[login].score += 2
                else:
                    hit_conditions[self.ships[i].owner_login] = 1
                    hitted_players.append(self.ships[i].owner_login)
                    Players[login].score += 1

        for i in reversed(range(len(self.ships))):
            if len(self.ships[i].coordinates) == 0:
                self.ships.remove(self.ships[i])

        for player in self.players:
            if player not in hit_conditions.keys() and Players[player].type == 'Player':
                hit_conditions[player] = 0
        self.makeStats(hit_conditions, hitted_players, sinked_players, coordinate)

    def makeStats(self, hit_conditions, hitted_players, sinked_players, coordinate):
        self.hit_messages = dict.fromkeys(self.players, '')
        hitter = ''

        for player in self.players:
            self.hit_messages[player] += '4#'
            if hit_conditions[player] == 3:
                hitter = player

        for player in hit_conditions:          # 4# + 0 - this player wasn't hitted, 1 - this player was hitted, 2 - this player is spectator + # list of players which ships was sinked
            if hit_conditions[player] == 0 and Players[player].type != 'Spectator':
                self.hit_messages[player] += '0#'
            elif hit_conditions[player] < 3 and Players[player].type != 'Spectator':
                self.hit_messages[player] += '1#' + hitter + ',' + str(coordinate[0]) + ',' + str(coordinate[1]) + '#'

        for player in self.players:
            if Players[player].type == 'Spectator':
                self.hit_messages[player] += '2#' + str(coordinate[0]) + ',' + str(coordinate[1]) + '#'
                for i in range(len(hitted_players)):
                    self.hit_messages[player] += player + ','
                self.hit_messages[player] = self.hit_messages[player][:len(self.hit_messages[player]) - 1] + '#'
                #for i in range(len(sinked_players)):
                #    response += player + ';'
                #messages[player] = messages[player][:len(messages[player]) - 1]

        for player in self.players:
            for p in sinked_players:
                self.hit_messages[player] += p + ','
            self.hit_messages[player] = self.hit_messages[player][:len(self.hit_messages[player]) - 1]

        self.newRound()

    def checkEndGame(self):
        owner = self.ships[0].owner_login
        for i in range(1, len(self.ships)):
            if self.ships[i].owner_login != owner:
                return False
        return True


class Ship:
    def __init__(self, owner_login, length, coordinates):
        self.length = length
        self.coordinates = coordinates
        self.owner_login = owner_login


class Player:
    def __init__(self, login, cor_id):
        self.login = login
        self.score = 0
        self.type = 'Player'  # Player, Spectator, Leaved
        self.corID = cor_id


Players = {}
CorrIDs = {}
GameSessions = {}
PlayerGame = {}
clientNumOfShips = 5


class Parser:
    @staticmethod
    def parse(request, cor_id):
        subrequests = request.split('#')

        if (len(subrequests) == 0):
            return

        if (subrequests[0] == '0'):
            if (len(subrequests) < 2):
                return '0#0'
            request_name = subrequests[1]
            if (request_name in Players.keys()):
                response = '0#0'
                return response
            Players[request_name] = Player(request_name, cor_id)
            CorrIDs[cor_id] = request_name
            response = '0#1'
            return response

        if (subrequests[0] == '1'):
            response = '1#'
            response_tail = ''
            numOfActiveGames = 0
            for game in GameSessions.values():
                if (game.state == 0):
                    numOfActiveGames += 1
                    response_tail += str(game.id) + ';'
                    response_tail += str(game.size) + ';'
                    response_tail += str(len(game.players)) + '#'
            print response + str(numOfActiveGames) + '#' + response_tail
            return response + str(numOfActiveGames) + '#' + response_tail

        if (subrequests[0] == '2'):
            if (len(subrequests) < 3):
                return '2#0'
            if (subrequests[1] == '0'):
                master_login = CorrIDs[cor_id]
                game_size = subrequests[2]
                newGame = GameSession(master_login, game_size)
                GameSessions[newGame.id] = newGame
                PlayerGame[cor_id] = newGame.id
                return '2#1'
            player_login = CorrIDs[cor_id]
            requested_game = subrequests[2]
            if (GameSessions[requested_game].state != 0):
                return '2#0'
            GameSessions[requested_game].addPlayer(player_login)
            PlayerGame[cor_id] = GameSessions[requested_game].id
            return '2#1'

        if (subrequests[0] == '3'):
            del subrequests[0]
            del subrequests[-1]
            if (len(subrequests) != clientNumOfShips):
                return '3#0'
            player_login = CorrIDs[cor_id]
            game_session = PlayerGame[cor_id]
            GameSessions[game_session].addShipsOfPlayer(player_login, subrequests)
            return '3#1'

        if (subrequests[0] == '4'):
            game_session = PlayerGame[cor_id]
            player_login = CorrIDs[cor_id]
            if (len(subrequests) == 1 and len(GameSessions[game_session].hit_messages.keys()) == 0):
                return '4#-1'
            if (len(subrequests) == 1):
                return GameSessions[game_session].hit_messages[player_login]

            if (len(subrequests) < 3):
                return '4#-1'
            coordinates = (int(subrequests[1]), int(subrequests[2]))
            GameSessions[game_session].makeHit(player_login, coordinates)
            return GameSessions[game_session].hit_messages[player_login]

        if (subrequests[0] == '5'):
            game_session = PlayerGame[cor_id]
            if (not game_session):
                return '5#-1'
            active = GameSessions[game_session].curActive
            return '5#' + str(GameSessions[game_session].players[active])

        if (subrequests[0] == '6'):
            game_session = PlayerGame[cor_id]
            if GameSessions[game_session].checkEndGame() == True:
                owner = GameSessions[game_session].ships[0].owner_login
                ships = []
                return '6#' + owner
            return '6#0'

        if (subrequests[0] == '7'):
            game_session = PlayerGame[cor_id]
            number = len(GameSessions[game_session].players)
            return '7#' + str(number)

        if (subrequests[0] == '8'):
            game_session = PlayerGame[cor_id]
            if cor_id == Players[GameSessions[game_session].master_client].corID:
                GameSessions[game_session].startGame()
                return '8#1'
            return '8#0'


def on_request(ch, method, props, body):
    request = str(body)

    response = Parser.parse(request, props.correlation_id)

    #print 'response = ', response

    ch.basic_publish(exchange='',
                     routing_key=props.reply_to,
                     properties=pika.BasicProperties(correlation_id= \
                                                         props.correlation_id,
                                                     delivery_mode=2, ),
                     body=str(response))
    ch.basic_ack(delivery_tag=method.delivery_tag)


channel.basic_qos(prefetch_count=1)
channel.basic_consume(on_request, queue='rpc_queue_durable_' + str(serverID))

print(" [x] Awaiting RPC requests")
channel.start_consuming()
