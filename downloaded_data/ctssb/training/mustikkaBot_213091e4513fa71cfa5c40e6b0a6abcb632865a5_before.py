import logging
import os
import jsonpickle
import exceptions
import datetime
import random

from main import Bot

class Quote:
    id = None
    ":type: int"

    user = None
    ":type: str"

    text = None
    ":type: str"

    year = None
    ":type: datetime.datetime"

    def __init__(self, id, date, user, text):
        self.id = id
        self.date = date
        self.user = user
        self.text = text

    def format(self):
        return "\"" + self.text + "\" -" + self.user + " " + str(self.date.year)

class Quotes:
    def __init__(self):
        self.bot = None
        ":type: Bot"
        self.log = None

        self.jsonpath = None
        ":type: str"
        self.acl_admin = None
        ":type: str"

        self.quotes = []
        ":type: list"

        self.last_shown = None
        ":type: Quote"

    def init(self, bot):
        self.bot = bot
        self.log = logging.getLogger("mustikkabot.quotes")
        self.jsonpath = os.path.join(self.bot.datadir, "quotes.json")
        self.acl_admin = "!quotes.sdmin"

        self.bot.accessmanager.register_acl(self.acl_admin, default_groups=["%moderators"])
        self.bot.eventmanager.register_message(self)
        self.read_JSON()

        self.log.info("Init complete")

    def dispose(self):
        self.bot.eventmanager.unregister_message(self)
        self.log.info("Disposed")

    def read_JSON(self):
        if not os.path.isfile(self.jsonpath):
            self.log.info("Quotes-datafile does not exist, creating")
            self.write_JSON()
        try:
            with open(self.jsonpath, "r") as file:
                jsondata = file.read()
        except:
            self.log.error("Could not open " + self.jsonpath)
            raise exceptions.FatalException("Could not open " + self.jsonpath)

        self.quotes = jsonpickle.decode(jsondata)

    def write_JSON(self):
        data = jsonpickle.encode(self.quotes)
        with open(self.jsonpath, "w") as file:
            file.write(data)

    def quote_add(self, date, user, text):
        quote_id = sorted(self.quotes, key=lambda quote: quote.id)[-1].id+1 if len(self.quotes) else 1
        self.quotes.append(Quote(id=quote_id, date=date, user=user, text=text))
        self.log.info("Adding quote #" + str(quote_id) + ": \"" + text + "\" -" + user + " " + str(date.year))
        self.write_JSON()
        return quote_id

    def quote_remove(self, id):
        for quote in self.quotes:
            if quote.id == int(id):
                self.log.info("Removing quote #" + str(id) + ": " + quote.format())
                self.quotes.remove(quote)
                self.write_JSON()
                return True
        self.log.info("Unaable to remove quote with id #" + str(id))
        return False

    def quote_count(self):
        return len(self.quotes)

    def quote_fetch(self, id):
        for quote in self.quotes:
            if quote.id == id:
                return quote
        return None

    def command_admin(self, user, args):
        if len(args) < 2:
            return
        if args[1] == "add":
            if not self.bot.accessmanager.is_in_acl(user, self.acl_admin):
                return
            if len(args) < 4:
                return
            if args[2] == "-y":
                if len(args) < 6:
                    return
                date = datetime.datetime(int(args[3]), 1, 1)
                user = args[4]
                text = ' '.join(args[5:])
            else:
                date = datetime.datetime.now()
                user = args[2]
                text = ' '.join(args[3:])
            quote_id = self.quote_add(date, user, text)
            self.bot.send_message("Added quote with ID #" + str(quote_id))

        elif args[1] == "remove" or args[1] == "delete":
            if not self.bot.accessmanager.is_in_acl(user, self.acl_admin):
                return
            if len(args) < 3:
                return
            if self.quote_remove(args[2]):
                self.bot.send_message("Removed quote #" + str(args[2]))
            else:
                self.bot.send_message("Quote not removed")

        elif args[1] == "list":
            self.bot.send_message("Not implemented")
    
    def command_show(self, user, args):
        id = None
        if len(args) > 1:
            id = int(args[1])
            quote = self.quote_fetch(id)
            self.log.info("Requested quote id: #" + str(id))
        else:
            options = self.quotes.copy()
            if self.last_shown:
                options.remove(self.last_shown)
            quote = random.choice(options)
            self.log.info("Requested random quote")
        if quote:
            self.bot.send_message(quote.format())
            self.log.info("Showed quote: " + quote.format())
            self.last_shown = quote
        else:
            self.bot.send_message("Quote #" + str(id) + " does not exist")

    def handle_message(self, data, user, msg):
        args = msg.split(' ')
        if args[0] == "!quotes":
            self.command_admin(user, args)
        elif args[0] == "!quote":
            self.command_show(user, args)
