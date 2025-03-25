from pyglet.window import key

class Player(object):
    """The player class
    Represents the player. Has bunch of functions to do bunch of stuff.
    """
#todo: Turn current walking into tick-based walking

    def __init__(self, Map):
        self.Map = Map
        self.position = (0, 0)

    def move(self, coords):
        if self.Map.get_tile(coords).impassable:
            self.Map.get_tile(coords).collide(self)
        else:
            self.Map.get_tile(coords).collide(self)
            self.position = coords
    def on_key_press(self, symbol, modifiers):
        if symbol == key.RIGHT:
            self.move((self.position[0]+1, self.position[1]))
        elif symbol == key.LEFT:
            self.move((self.position[0]-1, self.position[1]))
        elif symbol == key.UP:
            self.move((self.position[0], self.position[1]+1))
        elif symbol == key.DOWN:
            self.move((self.position[0], self.position[1]-1))
        elif symbol==key.C:
            print(self.position)
