class Song(object):

    def __init__(self, lyrcis):
        self.lyrcis = lyrics

    def sing_me_a_song(self):
        for line in self.lyrcis:
            print line

happy_bday = Song(["Happy birthday to you",
                   "I don't want to get sued",
                   "So I'll stop right there"])
