from random import choice
from tabulate import tabulate
from json import dumps
from json import loads
from song import Song


class Playlist:

    def __init__(self, name="", repeat=False, shuffle=False):
        self.name = name
        self.repeat = repeat
        self.shuffle = shuffle
        self.current_song_index = 0
        self.songs = []
        self.played_songs = set()

    def add_song(self, song):
        self.songs.append(song)

    def remove_song(self, song):
        try:
            self.songs.remove(song)
        except ValueError:
            pass

    def add_songs(self, songs):
        self.songs.extend(songs)

    def total_length(self):
        total_duration = 0
        for song in self.songs:
            total_duration += song.length_of_song(seconds=True)

        hours = total_duration // 3600
        total_duration = total_duration % 3600
        minutes = total_duration // 60
        total_duration = total_duration % 60
        seconds = total_duration // 1
        total_duration = total_duration % 1

        if hours < 10:
            hours = "0{}".format(hours)

        if minutes < 10:
            minutes = "0{}".format(minutes)

        if seconds < 10:
            seconds = "0{}".format(seconds)

        total_duration = "{}:{}:{}".format(hours, minutes, seconds)

        return total_duration

    def artists(self):
        all_artists = {}

        for song in self.songs:
            if song.artist not in all_artists:
                all_artists[song.artist] = 1
            elif song.artist in all_artists:
                all_artists[song.artist] += 1

        return all_artists

    def shuffle_song(self):
        song = choice(self.songs)

        while song in self.played_songs:
            song = choice(self.songs)

        self.played_songs.add(song)

        if len(self.songs) == len(self.played_songs):
            self.played_songs = set()

        return song

    def next_song(self):
        if self.shuffle:
            return self.shuffle_song()
        elif self.repeat:
            if self.current_song_index == len(self.songs):
                self.current_song_index = 0

            song = self.songs[self.current_song_index]
            self.current_song_index += 1

            return song
        else:
            if self.current_song_index < len(self.songs):
                song = self.songs[self.current_song_index]
                self.current_song_index += 1

                return song
            else:
                raise Exception("End of playlist")

    def previous_song(self):
        if self.shuffle:
            return self.shuffle_song()
        elif self.repeat:
            if self.current_song_index == -1:
                self.current_song_index = len(self.songs) - 1

            song = self.songs[self.current_song_index]
            self.current_song_index -= 1

            return song
        else:
            if self.current_song_index >= 0:
                song = self.songs[self.current_song_index]
                self.current_song_index -= 1

                return song
            else:
                raise Exception("End of playlist")

    def pprint_playlist(self):
        table = [[song.artist, song.title, song.length] for song in self.songs]

        return tabulate(table, headers=["Artist", "Song", "Length"])

    def prepare_json(self):
        songs = [song.__dict__ for song in self.songs]
        data = {"name": self.name,
                "songs": songs}

        return data

    def save(self):
        file_name = self.name.replace(" ", "-") + ".json"
        with open(file_name, "w") as f:
            f.write(dumps(self.prepare_json(), indent=4))

        print("Playlist was saved successfully!")

    @staticmethod
    def load(path):
        with open(path, "r") as f:
            content = f.read()
            data = loads(content)

        playlist = Playlist(data["name"])

        for saved_song in data["songs"]:
            title = saved_song["title"]
            artist = saved_song["artist"]
            album = saved_song["album"]
            length = saved_song["length"]

            song = Song(title, artist, album, length)
            playlist.add_song(song)

        return playlist
