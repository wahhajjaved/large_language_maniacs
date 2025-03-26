from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
# from pusher import Pusher
from django.http import JsonResponse
from decouple import config
from django.contrib.auth.models import User
from .models import *
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
import json

# instantiate pusher
# pusher = Pusher(app_id=config('PUSHER_APP_ID'), key=config('PUSHER_KEY'), secret=config('PUSHER_SECRET'), cluster=config('PUSHER_CLUSTER'))

def map(new=False, result=[]):
    if len(result) > 0 or new is True:
        result = []
        rooms = Room.objects.all().order_by('id')
        for room in rooms:
            id = room.id
            title = room.title
            description = room.description
            n_to = room.n_to.pk if room.n_to is not None else 0
            s_to = room.s_to.pk if room.s_to is not None else 0
            e_to = room.e_to.pk if room.e_to is not None else 0
            w_to = room.w_to.pk if room.w_to is not None else 0
            x = room.x
            y = room.y
            result.append({"id": id, "title": title, "description": description, "n": n_to, "s": s_to, "e": e_to, "w": w_to, "x": x, "y": y})
    return result

@csrf_exempt
@api_view(["GET"])
def initialize(request):
    user = request.user
    player = user.player
    player_id = player.id
    uuid = player.uuid
    room = player.room()
    x = room.x
    y = room.y
    players = room.playerNames(player_id)
    return JsonResponse({'uuid': uuid, 'name':player.user.username, 'title':room.title, 'description':room.description, 'x': x, 'y': y, 'players':players, 'map': map()}, safe=True)

# @csrf_exempt
@api_view(["POST"])
def move(request):
    dirs={"n": "north", "s": "south", "e": "east", "w": "west"}
    reverse_dirs = {"n": "south", "s": "north", "e": "west", "w": "east"}
    player = request.user.player
    player_id = player.id
    player_uuid = player.uuid
    data = json.loads(request.body)
    direction = data['direction']
    room = player.room()
    nextRoom = None
    if direction[0].lower() in ['n', 's', 'e', 'w']:
        nextRoom = getattr(room, f"{direction[0]}_to")
    if nextRoom is not None:
        player.currentRoom=nextRoom
        player.save()
        players = nextRoom.playerNames(player_id)
        currentPlayerUUIDs = room.playerUUIDs(player_id)
        nextPlayerUUIDs = nextRoom.playerUUIDs(player_id)
        # for p_uuid in currentPlayerUUIDs:
        #     pusher.trigger(f'p-channel-{p_uuid}', u'broadcast', {'message':f'{player.user.username} has walked {dirs[direction]}.'})
        # for p_uuid in nextPlayerUUIDs:
        #     pusher.trigger(f'p-channel-{p_uuid}', u'broadcast', {'message':f'{player.user.username} has entered from the {reverse_dirs[direction]}.'})
        return JsonResponse({'name':player.user.username, 'title':nextRoom.title, 'description':nextRoom.description, 'x': nextRoom.x, 'y': nextRoom.y, 'players':players, 'error_msg':""}, safe=True)
    else:
        players = room.playerNames(player_id)
        return JsonResponse({'name':player.user.username, 'title':room.title, 'description':room.description, 'x': room.x, 'y': room.y, 'players':players, 'error_msg':"You cannot move that way."}, safe=True)


@csrf_exempt
@api_view(["POST"])
def say(request):
    # IMPLEMENT
    return JsonResponse({'error':"Not yet implemented"}, safe=True, status=500)

# References for nameit() in newworld
# 25 nouns
nouns = ['Batman', 'Harry Potter', 'James Bond', 'Joker', 'King',
    'Captain America', 'Lucy', 'Jack Sparow', 'Dred', 'Terminator',
    'Rambo', 'Hellboy', 'Black Widow', 'Ghost Rider', 'Catwoman',
    'Cerebus', 'Black Panther', 'Gambit', 'Aquaman', 'Blade',
    'Green Arrow', 'Cyclops', 'Blue Beetle', 'Robinhood', 'Bad Horse']
# 25 adjectives
adjs = ['Bewildered', 'Elfin', 'Slim', 'Roasted', 'Offbeat',
    'Melodic', 'Wonderful', 'Great', 'Four', 'Wealthy',
    'Spurious', 'Gabby', 'Callous', 'Tired', 'Far-Flung',
    'Rude', 'Small', 'Cautious', 'Long-Term', 'Sassy',
    'Little', 'Annoying', 'Fretful', 'Godly', 'Ordinary']
# 100 sentences
descriptions = ['Though Tom and Mary are twins, they don\'t look very similar.',
    'Democracy is two wolves and a lamb voting on what to have for lunch. Liberty is a well-armed lamb contesting the vote.',
    'I don\'t know where I should look.',
    'She is a wonderful wife.',
    'This is a bag.',
    'If you don\t want to follow the lessons from the study session on countering corruption in the enterprise, you can also pay 200 hryvnia and get the evidence just like that.',
    'We\'ll do it some other time.',
    'You didn\'t put the passport number.',
    'Have you finished it?',
    'I\'ll try giving the book "Reiko\'s Recommended" a quick skim read on the spot.',
    'Tom was just about to ring Mary when she knocked on the door.',
    'Tom needs to be dealt with.',
    'Tom was very kind to me.',
    'Why is she with this idiot?',
    'It was too risky, so I decided not to try doing it.',
    'I\'m gullible.',
    'Tom divorced Mary three years ago.',
    'It was a mistake on their part.',
    'I thought I was his best friend.',
    'The discovery of oil enriched the country.',
    'I just never will understand you people.',
    'I told Tom to quit bothering me.',
    'Tom threatened Mary with his sword.',
    'Sinicization is a process that is deeply rooted in the cultural dynamics of China.',
    'She loves chocolate, too.',
    'We are dating with a view to marriage.',
    'A lot of people are killed in automobile accidents every year.',
    'I often get a letter from him.',
    'The bike parked over there is my brother\'s.',
    'The tensions between the two countries are growing rapidly.',
    'A glorious sight burst on our view.',
    'Why are you drinking Mary\'s juice?',
    'Tom will never amount to much.',
    'Tom gave me his phone number.',
    'Which dictionary is better, Collins or Oxford?',
    'I wonder if a day will come when money will be something found only in museums.',
    'Everyone thinks I\'m weird.',
    'I am fed up with my old fridge.',
    'The party\'s on Sunday.',
    'He finished the bulk of his work before dinner.',
    'We want to get out of here as soon as we can.',
    'The employees voted on the manager\'s proposal.',
    'Do you have hair clippers?',
    'What are your hobbies?',
    'This coat is a little tight across the back.',
    'Tom is enjoying himself.',
    'I felt inadequate to the task.',
    'The undead feed on human flesh.',
    'It\'s not exactly a strike.',
    'Tom Jackson spoke to our class today at school.',
    'It\'s a miracle that I\'ve got over cancer.',
    'Let\'s clean this up.',
    'I heard someone on the street calling me.',
    'I am not used to being spoken to in that rude way.',
    'Some strategic panning helped his mixes sound fuller.',
    'The drain is running freely.',
    'My behavior was very odd.',
    'It is impossible to express it in words.',
    'Worried, the shopkeeper ran over and kneeled beside Dima, who was breathing heavily - his forehead covered in sweat.',
    'I\'m not your doll.',
    'Tom isn\'t in jail.',
    'Tom is still shaking.',
    'You might meet Tom if you go to the library.',
    'Do you know what they found out?',
    'The English team beat the Brazilian team in the international football tournament.',
    'Let\'s talk it out.',
    'There\'s a mirror.',
    'Tom\'s skull has been fractured.',
    'Where\'s our stuff?',
    'No one\'s watching.',
    'Tom never killed anybody.',
    'Wherever you may go, you can\'t succeed without perseverance.',
    'He\'s the top of his English class.',
    'We are anxious for world peace.',
    'Women frighten me.',
    'Here\'s what we know.',
    'She is seldom at ease with strangers.',
    'That still doesn\'t solve the problem.',
    'He is familiar with the entertainment world.',
    "Do you speak French?" "No.",
    'He started a new life.',
    'Tom has been staring at Mary for three hours.',
    'So, have you thought about my offer?',
    'He sought for his name.',
    'Do it the way I told you to.',
    'Don\'t put on weight.',
    'She has to come.',
    'Please answer this question one more time.',
    'I am sorry.',
    'He doesn\'t bungle anything.',
    'Tom asked Mary what she wanted for her birthday.',
    'My work at the TV station is handling letters written in by viewers.',
    'I can\'t get used to him.',
    'All the stolen goods were recovered.',
    'I\'m in love with the girl next door.',
    'Tom was wearing flip-flops and a Hawaiian shirt.',
    'I wonder why Tom gave me this.',
    'Men aren\'t all that different from women.',
    'I think you know that\'s inappropriate.',
    'I made my orange scarf and white smock very bright, so people would notice them right away.']
rooms = []
# create 625 room names
for noun in nouns:
    for adj in adjs:
        rooms.append(adj + ' ' + noun)

import random
from collections import deque
@csrf_exempt
@api_view(["PUT"])
@permission_classes([IsAdminUser])
def newmap(request):
    def nameit():
        return {"title": random.choice(rooms), "description": random.choice(descriptions)}

    Room.objects.all().delete()
    mx = 30; my = 30 # width and height of the maze
    dx = [0, 1, 0, -1]; dy = [-1, 0, 1, 0] # 4 directions to move in the maze
    # start the maze from a random cell
    cx = random.randint(0, mx - 1); cy = random.randint(0, my - 1)
    room_count = 1
    room = Room(x=cx, y=cy, **nameit())
    room.save()
    stack = deque([(room, 0)]) # stack element: (room w/ x&y, direction)

    while room_count < 500 and len(stack) > 0:
        (room, cd) = stack[-1]
        cx, cy = room.x, room.y
        # to prevent zigzags:
        # if changed direction in the last move then cannot change again
        if len(stack) > 2:
            if cd != stack[-2][1]: dirRange = [cd]
            else: dirRange = range(4)
        else: dirRange = range(4)

        # find a new cell to add
        nlst = [] # list of available neighbors
        for i in dirRange:
            nx = cx + dx[i]; ny = cy + dy[i]
            if nx >= 0 and nx < mx and ny >= 0 and ny < my:
                if Room.objects.filter(x=nx, y=ny).exists() is False:
                    ctr = 0 # of occupied neighbors must be 1
                    for j in range(4):
                        ex = nx + dx[j]; ey = ny + dy[j]
                        if ex >= 0 and ex < mx and ey >= 0 and ey < my:
                            if Room.objects.filter(x=ex, y=ey).exists(): ctr += 1
                    if ctr == 1: nlst.append(i)

        # if 1 or more neighbors available then randomly select one and move
        if len(nlst) > 0:
            ir = nlst[random.randint(0, len(nlst) - 1)]
            cx += dx[ir]; cy += dy[ir]
            room_count += 1
            room = Room(x=cx, y=cy, **nameit())
            room.save()
            # Possibly where to connect rooms
            dirs = ['s','e','n','w']
            for j in range(4):
                ex = nx + dx[j]; ey = ny + dy[j]
                if ex >= 0 and ex < mx and ey >= 0 and ey < my:
                    neighbor = Room.objects.filter(x=ex, y=ey)
                    if neighbor.exists():
                      room.connectRooms(neighbor[0], dirs[ir])
            stack.append((room, ir))
        else: stack.pop()

    return JsonResponse({"map": map(new=True)}, safe=True)
