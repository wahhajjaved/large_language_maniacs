from main.controllers import *

class RankingsView(BaseView):
	template = 'rankings.html'

	def doGet(self, request):
		for player in Player.objects.all():
			total_points = 0
			for game in League_Game.objects.filter(player=player):
				points = game.league_points if game.league_points is not None else 0
				bonus_points = game.bonus_points if game.bonus_points is not None else 0
				total_points = total_points + (points + bonus_points)	
			player.total_points = total_points
		weeks = [game.group.week for game in League_Game.objects.all()]
		week = max(weeks) if weeks else 1
		return {'week': week, 'players': players}