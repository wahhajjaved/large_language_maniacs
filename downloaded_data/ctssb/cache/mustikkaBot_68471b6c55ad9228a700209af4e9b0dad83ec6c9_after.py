from logging import d,log
import tools

def getId():
    return "about"


class about:

    bot = None

    def init(self, bot):
        self.bot = bot
        bot.eventlistener.registerMessage(self)
        log("[ABOUT] Init complete")

    def handleMessage(self, data, user, msg):
        msg = tools.stripPrefix(msg)
        args = msg.split()

        if args[0] == "!about" or args[0] == "!bot":
            log("[ABOUT] Printing \"about\"")
            self.bot.sendMessage("MustikkaBot is a IRC/Twitch chatbot created in python " +
                            "for the awesome youtuber/streamer Mustikka. Author: Esa Varemo")