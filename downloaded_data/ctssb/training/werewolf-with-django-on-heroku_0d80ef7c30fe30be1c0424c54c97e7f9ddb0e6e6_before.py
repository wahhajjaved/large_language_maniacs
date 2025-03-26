# -*- coding: utf-8 -*-

import re
import json
import logging
import random
import time
import operator
import threading
from channels import Group
from channels import Channel
from channels.sessions import channel_session
from .models import Room
from .models import Player
import sys
reload(sys)
sys.setdefaultencoding("utf-8")

log = logging.getLogger(__name__)


noEnoughPeople = '房间人数不足'
gameHasStarted = '游戏已经开始'
gameNotStarted = '游戏尚未开始'
notReady = '有人没准备好'
notRightPerson = '您本轮无法投票'
voteInfo = '您投票给 '
dayerror = '时间是白天'
nighterror = '时间是夜晚'
identification = '您的身份是 '

identificationDict = dict()
identificationDict[0] = '村民'
identificationDict[1] = '狼人'
identificationDict[2] = '预言家'
identificationDict[3] = '女巫'
identificationDict[4] = '猎人'
identificationDict[5] = '守卫'


def keepalive(label, messageInfo, typo):
    message = dict()
    message['handle'] = 'keepalive'
    message['typo'] = typo
    message['message'] = messageInfo
    try:
        room = Room.objects.get(label=label)
    except Room.DoesNotExist:
        log.debug('ws room does not exist label=%s', label)
        return
    while 1:
        m = room.messages.create(**message)
        Group(label).send({'text': json.dumps(m.as_dict())})
        time.sleep(20)


def sendMessage(label, name, messageInfo, typo):
    message = dict()
    message['handle'] = '系统信息'
    message['typo'] = typo
    message['message'] = messageInfo
    try:
        room = Room.objects.get(label=label)
    except Room.DoesNotExist:
        log.debug('ws room does not exist label=%s', label)
        return
    m = room.messages.create(**message)
    Channel(name).send({'text': json.dumps(m.as_dict())})

def sendGroupMessage(label, messageInfo, typo):
    message = dict()
    message['handle'] = '系统信息'
    message['typo'] = typo
    message['message'] = messageInfo
    try:
        room = Room.objects.get(label=label)
    except Room.DoesNotExist:
        log.debug('ws room does not exist label=%s', label)
        return
    m = room.messages.create(**message)
    Group('chat-'+label).send({'text': json.dumps(m.as_dict())})


def judgement(label):
    try:
        room = Room.objects.get(label=label)
    except Room.DoesNotExist:
        log.debug('ws room does not exist label=%s', label)
        return -1
    roleList = room.roleList.split(",")
    cunMin = int(roleList[0])
    langRen = int(roleList[1])
    shenMin = int(room.playerNumber) - cunMin - langRen
    for player in room.players.all():
        if player.alive == 0:
            if player.identification == 0:
                cunMin = cunMin - 1
            elif player.identification == 1:
                langRen = langRen - 1
            else:
                shenMin = shenMin - 1
    if cunMin == 0 or shenMin == 0 or langRen >= (cunMin + shenMin):
        log.debug('判决胜负1')
        return 1
    elif langRen == 0:
        log.debug('判决胜负2')
        return 2
    else:
        log.debug('判决胜负0')
        return 0

def judgementView(label, name):
    try:
        room = Room.objects.get(label=label)
    except Room.DoesNotExist:
        log.debug('ws room does not exist label=%s', label)
        sendMessage(label, name, '房间不存在!', 'error')
        return
    cunmin = ''
    langren = ''
    yuyanjia = ''
    nvwu = ''
    shouwei = ''
    lieren = ''
    for player in room.players.all():
        if player.identification == 0:
            cunmin = cunmin + player.position + ' '
        elif player.identification == 1:
            langren = langren + player.position + ' '
        elif player.identification == 2:
            yuyanjia = yuyanjia + player.position + ' '
        elif player.identification == 3:
            lieren = lieren + player.position + ' '
        elif player.identification == 4:
            nvwu = nvwu + player.position + ' '
        elif player.identification == 5:
            shouwei = shouwei + player.position + ' '
    Info = 'Identification list \n '
    if len(cunmin) > 0:
        Info = Info + '村民: ' + cunmin + '\n '
    if len(langren) > 0:
        Info = Info + '狼人: ' + langren + '\n '
    if len(yuyanjia) > 0:
        Info = Info + '预言家: ' + yuyanjia + '\n '
    if len(lieren) > 0:
        Info = Info + '猎人: ' + lieren + '\n '
    if len(nvwu) > 0:
        Info = Info + '女巫: ' + nvwu + '\n '
    if len(shouwei) > 0:
        Info = Info + '守卫: ' + shouwei + '\n '
    sendMessage(label, name, Info, 'message')


def processVote(label, args):
    try:
        room = Room.objects.get(label=label)
    except Room.DoesNotExist:
        log.debug('ws room does not exist label=%s', label)
        return -1, 'ws room does not exist label=' + label
    count = dict()
    info = dict()
    vote = dict()
    log.debug('投票列表现在是=%s', room.voteList)
    voteList = room.voteList.split(',')
    if len(voteList) is 1:
        return '', '无人投票'
    for i in xrange(0,len(voteList),2):
        log.debug('现在i的大小是=%d', i)
        voter = voteList[i]
        if args is not 0:
            if voter is not args:
                continue
        target = voteList[i + 1]
        if int(target) < 1 or int(target) > room.playerNumber:
            continue
        elif voter in vote:
            continue
        else:
            if room.players.filter(position=voter).first().alive is 0:
                continue
            vote[voter] = target
            if target in info:
                info[target] = info[target] + ',' + voter
            else:
                info[target] = '' + voter
            weight = 1
            if room.players.filter(position=voter).first().jingzhang is 1:
                weight = 1.5
            if target in count:
                count[target] = count[target] + weight
            else:
                count[target] = weight
    # deadman = max(count.iteritems(), key=operator.itemgetter(1))[0]
    deadman = ''
    currentMax = 0
    for key,val in count.iteritems():
        if val > currentMax:
            deadman = '' + key
            currentMax = val
        elif val == currentMax:
            deadman = deadman + ',' + key 
    systemInfo = '本轮被投的人是： ' + deadman + '\n'
    for key, val in info.iteritems():
        systemInfo = systemInfo + '投' + key + '的人有：' + val + '\n'
    return deadman, systemInfo


def processName(label):
    try:
        room = Room.objects.get(label=label)
    except Room.DoesNotExist:
        log.debug('ws room does not exist label=%s', label)
        return ''
    nameList = []
    voteList = room.voteList.split(',')
    for i in xrange(0,len(voteList),2):
        if voteList[i] in nameList:
            continue
        else:
            nameList.append(voteList[i]) 
    room.voteList = ''
    room.save()
    return nameList

def checkStatus(label, nameList):
    try:
        room = Room.objects.get(label=label)
    except Room.DoesNotExist:
        log.debug('ws room does not exist label=%s', label)
        return -1
    voteList = room.voteList.split(',')
    for i in xrange(0,len(voteList),2):
        voter = voteList[i]
        target = voteList[i + 1]
        if target is 'bloom':
            player = room.players.filter(position=vote).first()
            player.alive = 0
            player.save()
            if room.jinghui is 1:
                sendGroupMessage(label,'昨天晚上死亡的人是'+room.deadman,'message')
            room.jinghui = 0
            room.dayStatus = 0
            room.voteList = ''
            room.deadman = ''
            room.save()
            return 1
        elif target is 'tuishui':
            if voter in nameList:
                nameList.remove(voter)
        elif target is 'startVote':
            room.voteList = ''
            room.save()
            return 2
    return 0

def pkStatus(label):
    try:
        room = Room.objects.get(label=label)
    except Room.DoesNotExist:
        log.debug('ws room does not exist label=%s', label)
        return -1
    voteList = room.voteList.split(',')
    for i in xrange(0,len(voteList),2):
        voter = voteList[i]
        target = voteList[i + 1]
        if target is 'startVote':
            room.voteList = ''
            room.save()
            return 1
    return 0

def pkVote(label, nameList, count):
    try:
        room = Room.objects.get(label=label)
    except Room.DoesNotExist:
        log.debug('ws room does not exist label=%s', label)
        return [] 
    if count is 2:
        return []
    else:
        room.voteList = ''
        room.save()
        status = 0
        while status is 0:
            status = pkStatus(label)
        sendGroupMessage(label,'PK台投票开始','message')
        sendGroupMessage(label,'现在在台上的玩家是:','message')
        sendGroupMessage(label,''.join(nameList),'message')
        sendGroupMessage(label,'开始20s的投票','message')
        time.sleep(20)
        target, systemInfo = processVote(label,0)
        sendGroupMessage(label,systemInfo,'message')
        return target

def room_status(label, number, gameStatus):
    try:
        room = Room.objects.get(label=label)
    except Room.DoesNotExist:
        log.debug('ws room does not exist label=%s', label)
        return -1
    # 天黑请闭眼
    if number == 0:   
        sendGroupMessage(label, '天黑请闭眼！', 'message')
        time.sleep(10)
        return 1
    # 狼人杀人
    elif number == 1:
        sendGroupMessage(label, '狼人请睁眼！', 'message')
        if room.jinghui == 1:
            sendGroupMessage(label, '狼人请确认同伴！', 'message')
            time.sleep(10)
        time.sleep(5)
        room.voteList = ''
        room.save()
        sendGroupMessage(label, '狼人请确认击杀目标！', 'message')
        time.sleep(20)
        deadman, systemInfo = processVote(label, 0)
        temp = deadman.split(',')
        if len(temp) > 1:
            deadman = 0
        else:
            deadman = int(deadman)
        room.deadman = '' + str(deadman)
        room.voteList = ''
        room.save()
        sendGroupMessage(label, '狼人请闭眼！', 'message')
        time.sleep(10)
        return 2
    # 预言家验人
    elif number == 2:
        if 2 not in gameStatus:
            return 3
        sendGroupMessage(label, '预言家请睁眼！', 'message')
        time.sleep(5)
        room.voteList = ''
        room.save()
        sendGroupMessage(label, '预言家请验人！', 'message')
        time.sleep(30)
        if 2 in gameStatus:
            number = 0
            # for i in range(1, room.playerNumber + 1):
            #     player = room.players.filter(position=i).first()
            #     if player.identification == 2:
            #         number = i
            #         break
            deadman, systemInfo = processVote(label,number)
            deadman = deadman.split(',')
            if room.players.filter(position=int(deadman[0])).first().identification == 1:
                systemInfo = '您验得人是狼人！'
            else:
                systemInfo = '您验得人是好人！'
            for i in range(1, room.playerNumber + 1):
                player = room.players.filter(position=i).first()
                if player.identification == 2 and player.alive is 1:
                    sendMessage(label,player.address,systemInfo,'message')
                    break
        time.sleep(10)
        return 4
    # 女巫救人
    elif number == 4:
        if 4 not in gameStatus:
            return 6
        sendGroupMessage(label, '女巫请睁眼！', 'message')
        room.voteList = ''
        room.save()
        if room.jieyao is not 0:
            room.sleep(15)
            return 5
        nvwu = ''
        number = 0
        for i in range(1, room.playerNumber + 1):
            player = room.players.filter(position=i).first()
            if player.identification == 4 and player.alive is 1:
               nvwu = player.address
               number = i
               break
        if len(nvwu) > 0:
            sendMessage(label,nvwu,'今天晚上被杀死的人是' + room.deadman + '如果使用解药，请输入死者的id','message')
            time.sleep(15)
            jieyao, systemInfo = processVote(label, number)
            if len(jieyao) > 1:
                room.jieyao = room.deadman
                room.voteList = ''
                room.save()
                time.sleep(15)
                return 6
            else:
                room.voteList = ''
                room.save()
                return 5
        else:
            room.sleep(15)
            return 5
    # 女巫毒人
    elif number == 5:
        if 4 not in gameStatus:
            return 6
        room.voteList = ''
        room.save()
        if room.duyao is not 0:
            room.sleep(15)
            return 6
        nvwu = ''
        number = 0
        for i in range(1, room.playerNumber + 1):
            player = room.players.filter(position=i).first()
            if player.identification == 4 and player.alive is 1:
               nvwu = player.address
               number = i
               break
        if len(nvwu) > 0:
            sendMessage(label,nvwu,'女巫可以选择使用毒药！请输入您想毒死的人的id！','message')
            time.sleep(15)
            duyao, systemInfo = processVote(label,number)
            if len(duyao) > 1:
                room.duyao = int(duyao)
                room.voteList = ''
                room.save()
                return 6
            else:
                room.voteList = ''
                room.save()
                return 6
        else:
            room.sleep(15)
            return 6
    #守卫护人
    elif number == 6:
        if 5 not in gameStatus:
            return 7
        sendGroupMessage(label, '护卫可以选择您今晚想守卫的对象，注意两晚不能同守一个人！', 'message')
        room.voteList = ''
        room.save()
        huwei = ''
        number = 0
        for i in range(1, room.playerNumber + 1):
            player = room.players.filter(position=i).first()
            if player.identification == 5 and player.alive is 1:
               huwei = player.address
               number = i
               break
        if len(huwei) > 0:
            time.sleep(15)
            sendMessage(label,huwei,'请选择您今晚想守护的人！','message')
            huwei, systemInfo = processVote(label,number)
            if len(huwei) > 1:
                if room.huwei == int(huwei):
                    room.huwei = 0
                else:
                    room.huwei = huwei
                room.voteList = ''
                room.save()
                return 7
            else:
                room.voteList = ''
                room.save()
                return 7
        else:
            room.sleep(15)
            return 7
    # 处理昨晚死亡数据，并调整房间状态
    elif number == 7:
        systemInfo = '昨天晚上死的人有：'
        deadList = ''
        deadman = int(room.deadman)
        if deadman is not 0:
            if room.jieyao == deadman and room.shouwei == deadman:
                if len(deadList) is 0:
                    deadList = '' + deadman
                else:
                    deadList = deadList + ',' + deadman
                player = room.players.filter(position=int(deadman)).first()
                player.alive = 0
                player.save()
                room.save()
            elif room.jieyao == deadman or room.shouwei == deadman:
                room.deadman = 0
                room.save()
            else:
                deadList = deadList + deadman + ' '
                player = room.players.filter(position=int(deadman)).first()
                player.alive = 0
                player.save()
                room.save()
        if room.duyao is not 0:
            player = room.players.filter(position=int(room.duyao)).first()
            if player.alive == 1:
                player.alive = 0
                player.save()
                if len(deadList) is 0:
                    deadList = '' + room.duyao
                else:
                    deadList = deadList + ',' + room.duyao
        systemInfo = systemInfo + deadList
        room.deadman = deadList
        room.dayStatus = 1
        room.save()
        sendGroupMessage(label, '天亮了！', 'message')
        time.sleep(10)
        sendGroupMessage(label, systemInfo, 'message')
        time.sleep(10)
        return 8
    # 死人中有猎人或者警长，可以传警徽或者发动技能
    elif number == 8:
        if room.jinghui == 1:
            return 9
        deadList = room.deadman
        if len(deadList) is 0:
            return 10
        else:
            temp = deadList.split(',')
            room.deadman = ''
            for i in temp:
                player = room.players.filter(position=i).first()
                if player.jingzhang is 1:
                    room.voteList = ''
                    room.save()
                    sendGroupMessage(label,'警长有20s时间可以传递警徽','message')
                    time.sleep(20)
                    jinghuiList, systemInfo = processVote(label,i)
                    jinghui = jinghuiList.split(',')
                    for j in jinghui:
                        jiren = room.players.filter(position=j).first()
                        if jiren.alive is 1:
                            jiren.jingzhang = 1
                            jiren.save()
                            sendGroupMessage(label,j + '号玩家成为警长','message')
                            break
                room.voteList = ''
                room.save()
                sendGroupMessage(label,i +'玩家有20s时间可以发动技能','message')
                time.sleep(20)
                target, systemInfo = processVote(label,i)
                if player.identification is 3:
                    if int(target) > 0:
                        x = room.players.filter(position=int(target)).first()
                        x.alive = 0
                        x.save()
                        sendGroupMessage(label,'猎人发动技能，带走' + target,'message')
                        room.voteList = ''
                        room.save()
            return 10
    #j]警长竞选
    elif number== 9:
        room.voteList = ''
        room.save()
        sendGroupMessage(label,'有二十秒钟竞选警长','message')
        time.sleep(20)
        nameList = processName(label)
        status = checkStatus(label)
        while status is 0:
            status, nameList = checkStatus(label, nameList)
            time.sleep(5)
        if status is -1:
            return -1
        elif status is 1:
            return 0
        elif status is 2:
            room.voteList = ''
            room.save()
            sendGroupMessage(label,'开始20s投票','message')
            time.sleep(20)
            output, systemInfo = processVote(label, 0)
            sendGroupMessage(label,systemInfo,'message')
            nameList = output.split(',')
            if len(nameList) is 1:
                room.jinghui = 0
                player = rooms.players.filter(position=int(nameList[0])).first()
                player.jinghui = 1
                player.save()
                room.save()
                return 8
            else:
                count = 0
                while len(nameList) > 1 or len(nameList) is 0:
                    nameList = pkVote(label, nameList, count)
                    count = count + 1
                if len(nameList) is 0:
                    room.jinghui = 0
                    room.save()
                else:
                    room.jinghui = 0
                    player = rooms.players.filter(position=int(nameList[0])).first()
                    player.jinghui = 1
                    player.save()
                    room.save()
                return 8
    #发言并投票:
    elif number == 10:
        status = 0
        while status is 0:
            status = checkStatus(label)
        if status is -1:
            return -1
        elif status is 1:
            return 0
        elif status is 2:
            room.voteList = ''
            room.save()
            sendGroupMessage(label,'开始20s投票','message')
            time.sleep(20)
            output, systemInfo = processVote(label, 0)
            sendGroupMessage(label,systemInfo,'message')
            nameList = output.split(',')
            if len(nameList) is 1:
                player = rooms.players.filter(position=int(nameList[0])).first()
                player.alive = 0
                player.save()
            else:
                count = 0
                while len(nameList) > 1 or len(nameList) is 0:
                    nameList = pkVote(label, nameList, count)
                    count = count + 1
                if len(nameList) is 0:
                    return 0
                else:
                    player = rooms.players.filter(position=int(nameList[0])).first()
                    player.alive = 0
                    player.save()
            player = rooms.players.filter(position=int(nameList[0])).first()
            if player.jingzhang is 1:
                room.voteList = ''
                room.save()
                sendGroupMessage(label,'警长有20s时间可以传递警徽','message')
                time.sleep(20)
                jinghuiList, systemInfo = processVote(label,i)
                jinghui = jinghuiList.split(',')
                for j in jinghui:
                    jiren = room.players.filter(position=j).first()
                    if jiren.alive is 1:
                        jiren.jingzhang = 1
                        jiren.save()
                        sendGroupMessage(label,j + '号玩家成为警长','message')
                        break
                room.voteList = ''
                room.save()
                sendGroupMessage(label,i +'玩家有20s时间可以发动技能','message')
                time.sleep(20)
                target, systemInfo = processVote(label,i)
                if player.identification is 3:
                    if int(target) > 0:
                        x = room.players.filter(position=int(target)).first()
                        x.alive = 0
                        x.save()
                        sendGroupMessage(label,'猎人发动技能，带走' + target,'message')
                        room.voteList = ''
                        room.save()
                room.dayStatus = 0
                room.save()
                return 0


def startGame(label):
    try:
        room = Room.objects.get(label=label)
    except Room.DoesNotExist:
        log.debug('ws room does not exist label=%s', label)
        sendGroupMessage(label, 'room does not exist!', 'error')
        return
    room.gameStart = 1
    room.save()
    roleList = room.roleList.split(",")
    playerList = []
    gameStatus = []
    gameStatus.append(0)
    gameStatus.append(1)
    for i in range(0, int(roleList[0])):
        playerList.append(0)
    for i in range(0, int(roleList[1])):
        playerList.append(1)
    for i in range(0, int(roleList[2])):
        playerList.append(2)
    if roleList[2] is not 0:
        gameStatus.append(2)
    for i in range(0, int(roleList[3])):
        playerList.append(3)
    if roleList[3] is not 0:
        gameStatus.append(3)
    for i in range(0, int(roleList[4])):
        playerList.append(4)
    if roleList[4] is not 0:
        gameStatus.append(4)
    for i in range(0, int(roleList[5])):
        playerList.append(5)
    if roleList[5] is not 0:
        gameStatus.append(5)
    random.shuffle(playerList)
    for i in range(1, room.playerNumber + 1):
        player = room.players.filter(position=i).first()
        player.identification = playerList[i - 1]
        if player.identification is 0:
            sendMessage(label,player.address,'您的身份是村民！','message')
        if player.identification is 1:
            sendMessage(label,player.address,'您的身份是狼人！','message')
        if player.identification is 2:
            sendMessage(label,player.address,'您的身份是预言家！','message')
        if player.identification is 3:
            sendMessage(label,player.address,'您的身份是猎人！','message')
        if player.identification is 4:
            sendMessage(label,player.address,'您的身份是女巫！','message')
        if player.identification is 5:
            sendMessage(label,player.address,'您的身份是守卫！','message')
        player.save()
    sendGroupMessage(label, '身份已经准备就绪!', 'message')
    roomStatus = 0
    while judgement(label) is 0:
        log.debug('房间现在的状态是%d',roomStatus)
        roomStatus = room_status(label, roomStatus, gameStatus)
        if roomStatus is -1:
            sendGroupMessage(label, '错误发生，或者测试结束！', 'message')
            break
    if judgement(label) == 1:
        sendGroupMessage(label, '狼人获胜！', 'message')
    else:
        sendGroupMessage(label, '好人获胜！', 'message')



@channel_session
def ws_connect(message):
    # Extract the room from the message. This expects message.path to be of the
    # form /chat/{label}/, and finds a Room if the message path is applicable,
    # and if the Room exists. Otherwise, bails (meaning this is a some othersort
    # of websocket). So, this is effectively a version of _get_object_or_404.
    try:
        prefix, label = message['path'].decode('ascii').strip('/').split('/')
        if prefix != 'chat':
            log.debug('invalid ws path=%s', message['path'])
            return
        room = Room.objects.get(label=label)

    except ValueError:
        log.debug('invalid ws path=%s', message['path'])
        return
    except Room.DoesNotExist:
        log.debug('ws room does not exist label=%s', label)
        return

    log.debug('chat connect room=%s client=%s:%s', 
        room.label, message['client'][0], message['client'][1])

    if room.playerNumber == room.currentNumber:
        log.debug('room is full')
        return
    if room.gameStart == 1:
        log.debug('游戏开始!')
        return
    # Need to be explicit about the channel layer so that testability works
    # This may be a FIXME?
    Room.objects.filter(label=label).update(currentNumber=room.currentNumber + 1)
    Group('chat-'+label).add(message.reply_channel)
    message.channel_session['room'] = room.label

@channel_session
def ws_receive(message):
    # Look up the room from the channel session, bailing if it doesn't exist
    try:
        label = message.channel_session['room']
        room = Room.objects.get(label=label)
    except KeyError:
        log.debug('no room in channel_session')
        return
    except Room.DoesNotExist:
        log.debug('recieved message, buy room does not exist label=%s', label)
        return


    # Parse out a chat message from the content text, bailing if it doesn't
    # conform to the expected message format.
    try:
        data = json.loads(message['text'])
    except ValueError:
        log.debug("ws message isn't json text=%s", text)
        return
    
    if set(data.keys()) != set(('handle', 'message', 'typo')):
        log.debug("ws message unexpected format data=%s", data)
        return

    if data:
        player = None
        try:
            player = room.players.filter(position=data['handle']).first()
        except ValueError:
            log.debug("something is wrong")
        if player is not None:
            if player.address != message.reply_channel.name:
                log.debug("this room's position has been occupied by another guy")
                sendMessage(room.label, message.reply_channel.name, "this room's position has been occupied by another guy", 'error')
        elif data['handle'] != 0:
            room.players.create(position=data['handle'],address=message.reply_channel.name)
        log.debug('chat message room=%s handle=%s message=%s', 
            room.label, data['handle'], data['message'])
        if data['typo'] == 'startGame':
            if room.currentNumber < room.playerNumber:
                sendMessage(room.label, message.reply_channel.name, noEnoughPeople, 'error')
            elif room.gameStart == 1:
                sendMessage(room.label, message.reply_channel.name, gameHasStarted, 'error')
            elif room.players.all().count() < room.playerNumber:
                sendMessage(room.label, message.reply_channel.name, notReady, 'error')
            else:
                sendGroupMessage(room.label, '游戏开始!', 'message')
                # startGame(label)
                t = threading.Thread(target=startGame, args=(label,))
                m = threading.Thread(target=keepalive, args=(label,'保持连接','message'))
                t.start()
                m.start()
        elif data['typo'] == 'Vote':
                sendMessage(room.label, message.reply_channel.name, voteInfo + data['message'].decode('utf8'), 'message')
                voteList = room.voteList
                if len(voteList) is 0:
                    room.voteList = room.voteList + data['handle'] + ',' + data['message']
                    room.save()
                else:
                    room.voteList = room.voteList + ',' + data['handle'] + ',' + data['message']
                    room.save()
        elif data['typo'] == 'bloom':
            if room.gameStart == 0:
                sendMessage(room.label, message.reply_channel.name, gameNotStarted, 'error')
            elif room.dayStatus == 0:
                sendMessage(room.label, message.reply_channel.name, nighterror, 'error')
            else:
                if len(room.voteList) is 0:
                    room.voteList = room.voteList + data['handle'] + ',' + 'bloom'
                    room.save()
                else:
                    room.voteList = room.voteList + ',' + data['handle'] + ',' + 'bloom'
                    room.save()
        elif data['typo'] == 'identification':
            if room.gameStart == 0:
                sendMessage(room.label, message.reply_channel.name, gameNotStarted, 'error')
            else:
                player = room.players.filter(position=data['handle']).first()
                sendMessage(room.label, message.reply_channel.name, identification + identificationDict[player.identification], 'message')
        elif data['typo'] == 'judgement':
            if room.gameStart == 0:
                sendMessage(room.label, message.reply_channel.name, gameNotStarted, 'error')
            else:
                player = room.players.filter(position=data['handle']).first()
                if player.alive is 1:
                    sendMessage(room.label, message.reply_channel.name, '您在游戏中的角色还活着，无法成为法官', 'error')
                else:
                    judgementView(room.label, message.reply_channel.name)
        elif data['typo'] == 'startVote':
            if room.gameStart == 0:
                sendMessage(room.label, message.reply_channel.name, gameNotStarted, 'error')
            else:
                if len(room.voteList) is 0:
                    room.voteList = room.voteList + data['handle'] + ',' + 'startVote'
                    room.save()
                else:
                    room.voteList = room.voteList + ',' + data['handle'] + ',' + 'startVote'
                    room.save()

                

        #m = room.messages.create(**data)

        # See above for the note about Group
        #Group('chat-'+label).send({'text': json.dumps(m.as_dict())})

@channel_session
def ws_disconnect(message):
    try:
        label = message.channel_session['room']
        room = Room.objects.get(label=label)
        Group('chat-'+label).discard(message.reply_channel)
        player = room.players.filter(address=message.reply_channel.name).first()
        if player is not None:
            Room.objects.filter(label=label).update(currentNumber=room.currentNumber - 1)
            room.players.filter(address=message.reply_channel.name).delete()
    except (KeyError, Room.DoesNotExist):
        pass
