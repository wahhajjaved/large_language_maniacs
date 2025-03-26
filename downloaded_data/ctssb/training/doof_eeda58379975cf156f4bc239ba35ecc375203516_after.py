import random

from will.plugin import WillPlugin
from will.decorators import hear


class InatorHear(WillPlugin):
    """
    Random Doofenshmirtz hear responses
    """
    @hear('daily meeting')
    def dailyupdates(self,message):
        self.say( 'Number: 866-242-7949 Conference Code: 4919652245 Time: 9.30AM', message=message)

    @hear('oo+h')
    def ohmy(self, message):
        self.say('ooooooohhh', message=message)

    @hear('hmm+')
    def hmm(self, message):
        response_list = [
            'Hmm indeed, let us contemplate my childhood in Drusselstein',
            ('Hmmm, do you think my theme song is too short?  '
             'I was thinking of adding "Home of the Inatoranator"'),
            'Hmm, I was just thinking how much I hate my lousy brother',
            ('Hmm, I was just wondering too. About how awesome the '
             'gnomepocalypse was'),
            ]
        self.say(random.choice(response_list), message=message)
