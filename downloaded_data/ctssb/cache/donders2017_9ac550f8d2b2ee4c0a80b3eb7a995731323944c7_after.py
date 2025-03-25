from slackclient import SlackClient
import re
from wordFilter import WordFilter
import language_check
import json
import aiml

class BotFather:
    def __init__(self, slack_bot_token, bot_id):
        self.slackBotToken = slack_bot_token
        self.botID = bot_id
        self.slackClient = SlackClient(slack_bot_token)

        self.achievements = {}        
        self.achievements['^(?=.*\\bassassino\\b)(?=.*\\bgladiatore\\b).*$'] = 'murderer'
        self.achievements['^(?=.*\\bmotivo\\b)(?=.*\\bvendetta\\b).*$'] = 'motive'
        self.achievements['^(?=.*\\barma\\b)(?=.*\\bcoltello\\b).*$'] = 'weapon'
        
        self.usernames = self.load_users()
        self.atBot = "<@" + bot_id + ">"

        self.wordFilter = WordFilter()
        self.learned_words = {key: [] for key in self.usernames}


        # Init language check
        self.language = language_check.LanguageTool('it-IT')
        self.n_learned = 0

        # Init AIML
        self.kernel = aiml.Kernel()
        self.kernel.learn('botfather.xml')

    def post(self, text, channel):
        result = self.slackClient.api_call("chat.postMessage", channel=channel, text=text, as_user=True)
        print(result)
        return result

    def get_channel_name(self, channel_id):
        info = self.slackClient.api_call("groups.info", channel=channel_id)
        if info and 'group' in info:
            return info['group']['name']
        
        return 'Untitled Document 1'

    def parse_slack_output(self, slack_rtm_output):
        output_list = slack_rtm_output
        if output_list and len(output_list) > 0:
            for output in output_list:
                # act upon messages that are not its own
                if output and 'text' in output and 'user' in output and output['user'] != self.botID:
                    # AIML
                    response = self.kernel.respond(output['text'])
                    if response:
                        self.post(response, output['channel'])
                    user, self.n_learned = self.learning_progress(output['user'], output['text'])
                    # Language check
                    correction = self.check_language(output['text'])
                    if correction is not None:
                        self.post(correction, output['channel'])

                    # Find myname-othername channels
                    channel = self.get_channel_name(output['channel'])
                    match = re.search(r"([A-Za-z0-9]+)-([A-Za-z0-9]+)", channel)
                    print(match)
                    if match:
                        self.direct_message(output['text'], match.group(1), match.group(2), output['user'])

    def learning_progress(self, user, text):
        """Add user text input to that user's list of learned words,
        if the words are unique and correct
        """
        if self.wordFilter.filter_text(text) is None:
            self.check_italian(user,text)
            for word in text.split():
                if word not in self.learned_words[user]:
                    self.learned_words[user].append(word)
        n_learned = len(self.learned_words[user])
        return user, n_learned

    def check_language(self, text):
        txt = text.title()
        matches = self.language.check(txt)
        if len(matches) > 0:
            correction = language_check.correct(txt, matches)
            for match in matches:
                if len(match.replacements) > 0:
                    return "Did you mean '" + correction + "'?"
            return "TARTA DI MELE!"
        return None

    def direct_message(self, text, from_user, to_user, from_user_id):
        filtered = self.wordFilter.filter_text(text)
        home_channel = from_user + '-' + to_user
        away_channel = to_user + '-' + from_user
        if filtered is None:
            # if all words are allowed, pass the message along to other user
            if from_user_id in self.usernames:
                from_user_name = self.usernames[from_user_id]["real_name"]
            else:
                from_user_name = from_user
            self.post("*" + from_user_name + "*: " + text, away_channel)
            self.post("You have learned {} words so far!".format(
                self.n_learned), home_channel)
        else:
            # if disallowed words present, notify the sender
            text = "Cannot use the word '" + filtered + "'."
            self.post(text, home_channel)

    def connect(self):
        if self.slackClient.rtm_connect():
            print("Botfather connected and running!")
            return True

        return False

    def perform(self):
        input = self.slackClient.rtm_read()
        self.parse_slack_output(input)

    def check_italian(self, user, text):
        print(user + " " + text)
        for key in self.achievements:
            print("\t key:" + key)   
            if re.match(key,text): 
                json.loads(str(self.usernames[user]))["text"] = 1
                print(json.dumps(self.usernames[user]))

    def load_users(self):
        json_data = json.dumps(self.slackClient.api_call("users.list"))
        json_obj = json.loads(json_data)
        usernames = {'':''}
        for _item in json_obj["members"]:
            _item["murderer"]=0
            _item["motive"]=0
            _item["weapon"]=0
            if not _item["is_bot"] and _item["id"] != 'USLACKBOT':
                usernames[_item["id"]] = json.loads(str(json.dumps(_item)))
            #print("\n"+str(_item))
        return usernames
