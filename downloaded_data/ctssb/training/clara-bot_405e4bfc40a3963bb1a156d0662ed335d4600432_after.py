from random import randint
from Levenshtein import distance
from os import listdir
import json

# Config load
configFile = open('config.json')
raw_data = configFile.read()
data = json.loads(raw_data)

# Emotion load
emotionFile = open('emotions.json')
raw_data = emotionFile.read()
emotions = json.loads(raw_data)
emotionFile.close()

# Append all conversation response around distributed conversation files
# This allows one to "plug-in" new responses and have them centralized together
convo = []
convoFiles = listdir(data['convo_dir'])
for i in convoFiles:
    if i.endswith('.json'):
        convoFile = open('convos/' + i)
        raw_data = convoFile.read()
        convo += json.loads(raw_data)

# Var Setup
VAR_REGISTRY = {}
def build_registry():
    global VAR_REGISTRY
    VAR_REGISTRY = {
            "user_name": data['user']['name'],
            "name": data['name'],
            "response_count": len(convo),
            "user_hobby": data['user']['hobby'],
            "favorite_food": data['food'],
            "happy_level": emotions['happy'],
            "stress_level": emotions['stress'],
            "animosity": emotions['animosity']
            }

build_registry()

def punctuation_stripper(statement):
    toRemove = ['.', '!', '?']
    punctuate = None
    for i in toRemove:
        if not statement.find(i) == -1:
            punctuate = i
        statement = statement.strip(i)
    return {"text": statement, "punctuation": punctuate}

def handle_modifiers(modifiers):
    for i in modifiers:
        VAR_REGISTRY[i['name']] += i['val']

def calc_qualifiers(qualifier):
    registryValue = VAR_REGISTRY[qualifier['name']]
    try:
        if registryValue > qualifier['$gt']:
            return True
        else:
            return False
    except:
        # Not a greater than qualifier
        doNothing = True
    try:
        if registryValue == qualifier['$eq']:
            return True
        else:
            return False
    except:
        # Not an equal to qualifier
        doNothing = True
    try:
        if regsitryValue < qualifier['$lt']:
            return True
        else:
            return False
    except:
        # Not a less than qualifier
        doNothing = True
    # Legacy qualifier types
    try:
        if registryValue == qualifier['val']:
            return True
        else:
            return False
    except:
        # Not a less than qualifier
        doNothing = True
    # if supplied info doesn't fit any of the above qualifier types reject
    return False


def get_response(input):
    # Remove currently useless characters
    stripped = punctuation_stripper(input)
    input = stripped["text"]
    punctuation = stripped["punctuation"]
    possibilities = []
    for i in convo:
        for a in i['starters']:
            val = distance(input, a)
            if len(input)/(val+1) > 1.5:
                reply_options = []
                for b in i['replies']:
                    should_add = False
                    try:
                        to_test = b['qualifiers']
                        for z in to_test:
                            if calc_qualifiers(z):
                                should_add = True
                            else:
                                do_nothing = True
                    except:
                        should_add = True
                    if should_add:
                        to_add = {'text': b['text']}
                        try:
                            to_add['image'] = b['image']
                        except:
                            to_add['image'] = 'None'
                        try:
                            to_add['modifiers'] = b['modifiers']
                        except:
                            to_add['modifiers'] = []
                        reply_options += [to_add]
                slimmed_reply = reply_options[randint(0, len(reply_options)-1)]
                handle_modifiers(slimmed_reply['modifiers'])
                possibilities.append({'val': val, 'response': slimmed_reply['text'], 'image': slimmed_reply['image']})
    min = 10000000000
    response = 'None'
    image = 'None'
    # print(possibilities)
    for i in possibilities:
        if i['val'] < min:
            response = i['response']
            image = i['image']
            min = i['val']
    toReturn = {'message': response.format(**VAR_REGISTRY), 'image': image}
    return toReturn

if __name__ == "__main__":
    logFile = open('log.txt', 'a')
    print("Booting...")
    print("{} online.".format(data['name']))
    statement = ""
    while statement != "quit":
        statement = input("> ")
        response = get_response(statement.lower())
        print(response['message'])
        ender = '\n'
        logFile.write('S: ' + statement + ender)
        if not response == None:
            logFile.write('R: ' + response['message'] + ender)
        else:
            logFile.write('R: None' + ender)
    emotionFile = open('emotions.json', 'w')
    emotionFile.write(json.dumps(emotions))
    emotionFile.close()
