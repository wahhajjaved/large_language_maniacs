#from __future__ import division, unicode_literals
import os, sys
import pyglet
import cocos
import random
from cocos.actions import *
from cocos.layer import base_layers
from cocos.director import director
from cocos.layer import Layer, ColorLayer
from cocos.scene import Scene
from cocos.scenes.transitions import *
from cocos.sprite import Sprite
from pyglet import gl, font
from pyglet.window import key
#################### Global Variables #################

image_files = ['resources/cat.png', 'resources/rabbit.png', 'resources/deer.png',
               'resources/worm.png', 'resources/martha.png', 'resources/planet.png']
blank_file = 'resources/blank.png'
button = 'resources/button.png'
counter = 0
score = 0

#######################################################

class Cards(object):
    def __init__(self, image_file, blank_file):
        self.image = cocos.sprite.Sprite(pyglet.image.load(image_file))
        self.blank = cocos.sprite.Sprite(pyglet.image.load(blank_file))
        self.image_file = image_file
        self.image.opacity = 0

class Hand(object):
    def __init__(self, image_files, height, width):
        self.height = height
        self.width = width

        cards = random.sample(image_files, int((height*width)/2))*2
        shuffled = random.sample(cards, len(cards))
        self.shuffled = shuffled
        sprite_size = (480 - 5*(width-1))/width
        self.sprite_size = sprite_size

        x_position = []
        for i in range(width):
            x_position.append(80 + (sprite_size/2) + sprite_size*i + 5*i)
        x_position = [x for x in x_position for _ in range(height)]

        y_position = []
        for i in range(height):
            y_position.append(80 + (sprite_size/2) + sprite_size*i + 5*i)
        y_position = y_position*width

        self.posxy = zip(x_position, y_position)

class Martha(cocos.layer.ColorLayer):
    is_event_handler = True
    def __init__(self, hand, cards):
        super( Martha, self).__init__(0,0,0,255)

        self.hand = hand
        self.click = []

        self.text = cocos.text.Label(str(score), font_size=24,
           y = director.get_window_size()[1] - 113,
           x = director.get_window_size()[0]/2)
        self.add(self.text)


        label = cocos.text.Label('Matching Martha',
            font_name='Courier',
            font_size=32,
            anchor_x='center', anchor_y='center')
        label.position = 320,650
        self.add( label )

        self.scorelabel = cocos.text.Label("Score:",
            font_name = "Courier",
            font_size=24,
            anchor_x = "center",
            anchor_y='center',
            y = director.get_window_size()[1] - 100,
            x = director.get_window_size()[0]/2 -60)
        self.add(self.scorelabel)

        for posxy, card in zip(hand.posxy, cards):
            card.blank.position = posxy
            card.image.position = posxy
            card.image.scale = hand.sprite_size/float(card.image.image.width)
            card.blank.scale = hand.sprite_size/float(card.blank.image.width)
            self.add(card.blank)
            self.add(card.image)


    def update_text (self, score):
        text = str(score)
        self.text.element.text = text
        self.text.element.x = director.get_window_size()[0]/2 + 10
        self.text.element.y = director.get_window_size()[1] - 130


    def on_mouse_press(self, x, y, buttons, modifiers):
        global counter, score
        for card in cards:
            if card.blank.contains(x,y) and card.image.opacity == 0:
                card.image.opacity = 255
                counter += 1
                print "Counter is at: %s" % counter
                self.click.append(card)
                if counter == 3 and self.click[0].image_file != self.click[1].image_file:
                    for card in self.click:
                        card.image.opacity = 0
                    counter = 0
                    score -= 1
                    self.click = []
                    self.update_text(score)

                elif counter == 3 and self.click[0].image_file == self.click[1].image_file:
                    counter = 1
                    score += 2
                    self.click = []
                    self.click.append(card)
                    self.update_text(score)
                print self.click
                print score

class WelcomeScreen(cocos.layer.ColorLayer):
    is_event_handler = True
    def __init__(self):
        super( WelcomeScreen, self).__init__(0,0,0,255)

        self.text_title = cocos.text.Label("Matching Martha",
                                font_size = 32,
                                font_name ='Courier',
                                y = director.get_window_size()[1] - 200,
                                x = director.get_window_size()[0]/2,
                                anchor_x = "center",
                                anchor_y = "center")

        self.text_subtitle = cocos.text.Label("Hit Enter to play!",
                                font_size=18,
                                font_name = 'Courier',
                                y = director.get_window_size()[1] - 300,
                                x = director.get_window_size()[0]/2,
                                anchor_x="center",
                                anchor_y="center")

    def draw(self):
        self.text_title.draw()
        self.text_subtitle.draw()

    def on_key_press(self, k, m):
        if k == key.ENTER:
            director.replace(FadeTransition(
                settings_scene,
                1)
            )

class Settings(cocos.layer.Layer):
    is_event_handler = True
    def __init__(self):
        super(Settings, self).__init__()

        self.label = cocos.text.Label('Pick a name:',
                                    font_name='Courier',
                                    font_size=32,
                                    anchor_x='center', anchor_y='center',
                                    x = director.get_window_size()[0]/2,
                                    y = director.get_window_size()[1] - 200)

        self.text = cocos.text.Label("", x = director.get_window_size()[0]/2 - 30,
                                    y = director.get_window_size()[1] - 300,
                                    font_name = "Courier",
                                    font_size = 18,
                                    anchor_x='center')

        self.dim_label = cocos.text.Label('...and board size:',
                                    font_name='Courier',
                                    font_size=24,
                                    anchor_x='center', anchor_y='center',
                                    x = director.get_window_size()[0]/2,
                                    y = director.get_window_size()[1] - 400)

        self.dim_x = cocos.text.Label("___", x = director.get_window_size()[0]/2 - 50,
                                    y = director.get_window_size()[1] - 500,
                                    font_name = "Courier",
                                    font_size = 24,
                                    anchor_x='center')

        self.by = cocos.text.Label("x", x = director.get_window_size()[0]/2,
                                    y = director.get_window_size()[1] - 500,
                                    font_name = "Courier",
                                    font_size = 24,
                                    anchor_x='center')

        self.dim_y = cocos.text.Label("___", x = director.get_window_size()[0]/2 + 50,
                                    y = director.get_window_size()[1] - 500,
                                    font_name = "Courier",
                                    font_size = 18,
                                    anchor_x='center')

        self.keys_pressed = []
        self.update_text()

    def draw(self):
        self.label.draw()
        self.text.draw()
        self.dim_label.draw()
        self.dim_x.draw()
        self.by.draw()
        self.dim_y.draw()

    def update_text(self):
        key_names = [pyglet.window.key.symbol_string(k) for k in self.keys_pressed]
        text = ''.join(key_names)
        self.text.element.text = text

    def on_key_press(self, k, m):
        if k <= key.Z and k >= key.A:
            self.keys_pressed.append(k)
            self.update_text()
        elif k == key.BACKSPACE and len(self.keys_pressed) > 0:
            self.keys_pressed.pop()
            self.update_text()
        elif k == key.ENTER:
            director.replace(FadeTransition(
                main_scene, 1))


if __name__ == "__main__":
    cocos.director.director.init(height = 690, width = 640)

    welcome = WelcomeScreen()
    settings = Settings()

    hand = Hand(image_files, height = 2, width = 2)
    cards = [Cards(file, blank_file) for file in hand.shuffled]
    martha = Martha(hand, cards)

    welcome_scene = cocos.scene.Scene(welcome)
    settings_scene = cocos.scene.Scene(settings)
    main_scene = cocos.scene.Scene(martha)

    cocos.director.director.run(welcome_scene)