"""
Reply to direct questions.
"""

import operator
import re
import requests
from random import randrange
from requests.exceptions import RequestException
from datetime import datetime

from will.plugin import WillPlugin
from will.decorators import respond_to, hear


class RepliesPlugin(WillPlugin):
    """
    Classy replies.
    """

    def __init__(self, *args, **kwargs):
        """Remember start time."""
        super(RepliesPlugin, self).__init__(*args, **kwargs)
        self.start_timestamp = datetime.now()

    def get_jid(self, nick_or_name):
        result = None
        for jid, info in self.internal_roster.items():
            if (info['nick'] == nick_or_name or
                    nick_or_name.lower() in info['name'].lower() or
                    info['nick'] == nick_or_name.lstrip('@')):
                result = jid
                break
        return result

    def plus_one_gnome(self, nick):
        user_id = self.get_jid(nick)

        gnomes = self.load('garden_gnomes', {})
        user_gnomes = int(gnomes.get(user_id, 0))
        if not user_gnomes:
            gnomes[user_id] = 1
        else:
            gnomes[user_id] = 1 + user_gnomes
        self.save('garden_gnomes', gnomes)

    @respond_to(r"^any new schemes\?")
    def schemeinator(self, message):
        """scheme: any new schemes?"""
        try:
            req = requests.get("http://randomword.setgetgo.com/get.php")
            word = req.text.replace('\n', '').replace('\r', '')
        except RequestException:
            word = "API-is-broken"
        self.reply(
            message,
            "Behold my new evil scheme, the {word}-Inator".format(word=word)
        )

    @respond_to(r"^any blockers today\?")
    def any_blockers(self, message):
        """blockers: any blockers today?"""
        blockers = [
            "I can't seem find enough tinfoil to cover up the city.",
            "No blockers today, I'm just planning my latest scheme.",
            "Yes, santa stole my giant magnet.",
            "Yes, I'm not sure where the \"Self Destruct\" button should go on"
            "my latest inator.. perhaps on the bottom?",
        ]

        self.reply(
            message,
            blockers[
                randrange(len(blockers))
            ]
        )

    @respond_to(r"(award|issue|grant) (?P<num_gnomes>[^\s]+) (garden )?gnomes?"
                "to (?P<user_name>.*)")
    def garden_gnomes(self, message, num_gnomes=1, user_name=None):
        """
        garden_gnomes: award special recognition
        """
        # Input sanitation and syntax hints
        if num_gnomes in {'a', 'one'}:
            num_gnomes = 1
        try:
            num_gnomes = float(num_gnomes)
        except ValueError:
            if re.match('[0-9]+i', num_gnomes):
                self.reply(
                    message,
                    "EXCUSE ME?! These gnomes aren't IMAGINARY, "
                    "they're very REAL."
                )

            else:
                self.reply(
                    message,
                    "What? How many garden gnomes?"
                )
            return
        if num_gnomes % 1:
            self.reply(
                message,
                "Do you really expect me to go cutting up garden gnomes!?"
            )
            return
        num_gnomes = int(num_gnomes)
        if num_gnomes < 0:
            self.reply(
                message,
                "No, I won't take away garden gnomes. These people have "
                "earned them through hard work and dedication."
            )
            return
        elif num_gnomes == 0:
            self.reply(
                message,
                "Not even one gnome? What a shame."
            )
            return

        gnomes = self.load("garden_gnomes", {})
        # Look up user in roster
        user_id = self.get_jid(user_name)
        if not user_id:
            self.reply(
                message,
                "Sorry, I don't know who {0} is.".format(user_name)
            )
            return

        user_gnomes = int(gnomes.get(user_id, 0))
        if not user_gnomes:
            gnomes[user_id] = num_gnomes
        else:
            gnomes[user_id] = num_gnomes + user_gnomes
        self.save("garden_gnomes", gnomes)

        receiving_user_nick = self.get_user_by_jid(user_id).nick
        self.say("Awarded {0} gnome{1} to @{2}.".format(
            'a' if num_gnomes == 1 else num_gnomes,
            '' if num_gnomes == 1 else 's',
            receiving_user_nick
        ), message=message)

    @respond_to("(give( up| away)?|hand( over)?|surrender|deliver|transfer|"
                r"grant) (?P<num_gnomes>[^\s]+i?) of my ([\w]+ )?"
                "(garden )?gnomes to (?P<user_name>.*)")
    def give_garden_gnomes(self, message, num_gnomes=1, user_name=None):
        """
        garden_gnomes: give away
        """
        # Input sanitation and syntax hints
        if num_gnomes == "one":
            num_gnomes = 1
        try:
            num_gnomes = float(num_gnomes)
        except ValueError:
            if re.match('[0-9]+i', num_gnomes):
                self.reply(
                    message,
                    "EXCUSE ME?! These gnomes aren't IMAGINARY, "
                    "they're completely REAL."
                )
            else:
                self.reply(
                    message,
                    "What? How many garden gnomes?"
                )
            return
        if num_gnomes % 1:
            self.reply(
                message,
                "Look, I'm not going to go around cutting up garden gnomes."
            )
            return
        num_gnomes = int(num_gnomes)
        if num_gnomes < 0:
            self.reply(
                message,
                "What do you want me to do? Take garden gnomes away from {0}?"
                .format(user_name)
            )
            return
        elif num_gnomes == 0:
            self.reply(
                message,
                "You won't even give away one? That's too bad."
            )
            return

        gnomes = self.load("garden_gnomes", {})

        sending_user_id = message.sender.jid
        # Look up in roster
        receiving_user_id = self.get_jid(user_name)
        if not receiving_user_id:
            self.reply(
                message,
                "Sorry, I don't know who {0} is.".format(user_name)
            )
            return

        sending_user_gnomes = int(gnomes.get(sending_user_id, 0))
        if sending_user_gnomes < num_gnomes:
            self.reply(
                message,
                "But you only have {0} garden gnome{1}.. :/".format(
                    sending_user_gnomes,
                    '' if sending_user_gnomes == 1 else 's'
                )
            )
            return

        receiving_user_nick = self.get_user_by_jid(receiving_user_id).nick
        if sending_user_id == receiving_user_id:
            self.say(
                "I mean.. if you really want me to announce it, I guess. @{0} "
                "just handed themself {1} garden gnome{2}.".format(
                    receiving_user_nick,
                    'a' if num_gnomes == 1 else num_gnomes,
                    '' if num_gnomes == 1 else 's'
                ), message=message
            )
            return

        receiving_user_gnomes = int(gnomes.get(receiving_user_id, 0))

        gnomes[sending_user_id] = sending_user_gnomes - num_gnomes
        gnomes[receiving_user_id] = receiving_user_gnomes + num_gnomes
        self.save("garden_gnomes", gnomes)

        self.say("How thoughtful! Transferred {0} gnome{1} from @{2} to @{3}."
                 .format(
                     'a' if num_gnomes == 1 else num_gnomes,
                     '' if num_gnomes == 1 else 's',
                     message.sender.nick,
                     receiving_user_nick
                 ), message=message)

    @respond_to("(garden )?gnomes? tally")
    def garden_gnome_tally(self, message):
        """
        garden_gnomes: tally
        """
        gnomes = self.load("garden_gnomes", {})
        sorted_gnomes = sorted(gnomes.iteritems(), key=operator.itemgetter(1),
                               reverse=True)
        response = ['Garden gnomepocalypse leader board: <br /><ol>']
        for users in sorted_gnomes:
            user = self.get_user_by_jid(users[0])
            if not user:
                continue
            response.append('<li>{0} - {1}</li>'.format(
                users[1],
                user['name']
            ))

        self.reply(
            message,
            ''.join(response),
            html=True
        )

    @hear("thanks?( you)?")
    def thank_you_gnome(self, message):
        self.plus_one_gnome(message.sender['nick'])

    @hear("please")
    def please_gnome(self, message):
        self.plus_one_gnome(message.sender['nick'])

    @respond_to("oh hi")
    def oh_hi(self, message):
        self.say(
            'Oh hi Perry the Platypus. Would you like some '
            'Limburger cheese?',
            message=message
        )

    @respond_to("uptime")
    def uptime(self, message):
        delta = datetime.now() - self.start_timestamp
        self.say(parse_uptime(delta.seconds), message=message)

    @respond_to("uptime_verbose")
    def uptime_verbose(self, message):
        date_format = "%Y-%m-%d %H:%M:%S"
        now = datetime.now()
        delta = now - self.start_timestamp
        msg = "Started {0}, currently {1}. {2} seconds. Parsed: {3}".format(
            self.start_timestamp.strftime(date_format),
            now.strftime(date_format),
            delta.seconds,
            parse_uptime(delta.seconds),
        )
        self.say(msg, message=message)

def parse_uptime(seconds):
    """Receive seconds as integer, return a human-friendly string."""
    day = 86400
    hour = 360
    minute = 60
    parts = []

    def check_unit(seconds, num, unit):
        if seconds >= num:
            count = seconds / num
            seconds -= count * num
            if count == 1:
                unit = unit[:-1]
            parts.append("{0} {1}".format(count, unit))
        return seconds

    seconds = check_unit(seconds, day, "days")
    seconds = check_unit(seconds, hour, "hours")
    seconds = check_unit(seconds, minute, "minutes")
    check_unit(seconds, 1, "seconds")
    return ", ".join(parts)
