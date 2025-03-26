import es
from playerlib import getPlayer
from usermsg import saytext2

admins = ["STEAM_0:1:16940378"]

def load():
    es.addons.registerSayFilter(sayFilter)

def unload():
    es.addons.unregisterSayFilter(sayFilter)

def sayFilter(userid, text, teamonly):
    player = getPlayer(userid)
    if (teamonly or player.isdead):
        for id in admins:
            admin = getPlayer(es.getuserid(id))
            if(int(userid) == int(admin.userid)):
                continue

            if((teamonly and (admin.team != player.team)) or (player.isdead and not admin.isdead)):
                text = text.strip('"')
                if player.isdead and not admin.isdead:
                    dead = "*SPEC* " if player.team == 1 or player.team == 0 else "*DEAD* "
                else:
                    dead = ""
                if teamonly and admin.team != player.team:
                    if player.team == 0 or player.team == 1:
                        team = "(Spectator) "
                    elif player.team == 2:
                        team = "(Terrorist) "
                    else:
                        team = "(Counter-Terrorist) "
                else:
                    team = ""
                newtext = "\x01%s\x03%s\x01 %s:  %s"%(dead, player.name, team, text)
                saytext2(admin.userid, player.index, newtext)
    return (userid, text, teamonly)
