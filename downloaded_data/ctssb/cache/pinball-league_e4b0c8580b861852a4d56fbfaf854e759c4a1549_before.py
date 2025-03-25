from main.controllers import *

class GroupView(BaseView):
    template = 'group.html'

    def doGet(self, request):
        (week, group) = (request.GET.get('week'), request.GET.get('group'))
        canEnterScores = self.user_can_enter_scores(request.user, week, group) if request.user.is_authenticated() else False
        return {'week': week, 'group': group, 'canEnterScores': canEnterScores}

class SaveGamesApiView(BaseView):

    def post(self, request):
        payload = json.loads(request.body)
        players = payload['players']
        group = payload['group']
        week = payload['week']
        tableModel = Table.objects.get(id=payload['table']['id'])
        groupModel = Group.objects.get(group=group)

        scores = sorted([int(player['score']) for player in players],reverse=True)
        response = []
        for player in players:
            playerModel = Player.objects.get(id=player['id'])
            
            if 'gameId' in player:
                game = League_Game.objects.get(id=player['gameId'])
            else:
                game = League_Game(player=playerModel, group=groupModel)

            game.table = tableModel
            game.score = player['score']
            game.league_points = decide_points(scores, game.score)
            game.save()
            response.append(self.create_game_response(game))
        return json_response(response, 201)

    def create_game_response(self, game):
        response = {}
        response['id'] = game.id
        response['player'] = game.player.id
        response['league_points'] = game.league_points
        response['score'] = game.score
        response['table'] = game.table.id
        return response
