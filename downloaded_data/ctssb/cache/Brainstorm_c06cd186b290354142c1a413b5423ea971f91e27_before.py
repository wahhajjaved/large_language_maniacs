import os
import sys

import pygame

from idea import *
from level import *

class Game:
    def __init__(self, w, h):
        pygame.init()
        self.width = w
        self.height = h
        self.display = pygame.display.set_mode((w,h))
        self.clock = pygame.time.Clock()
        self.fps = 30
        # create ideas
        self.player = Idea('idea.png', 0, 300, 32, 32)
        self.player2 = Idea('idea.png', 200, 300, 32, 32)
        self.dummy = Idea('idea.png', 120, 300, 32, 32)
        self.ideas = []
        self.ideas.append(self.player)
        self.ideas.append(self.player2)
        self.ideas.append(self.dummy)
        self.num_ideas = len(self.ideas)
        # create level
        self.level = Level()
        self.level.add_platform(Wall(0, 400, 500, 10))
        self.level.add_platform(Wall(150, 450, 500, 10))

    def run(self):
        #! MAKE LEVEL CLASS
        level = pygame.image.load(os.path.join('assets', 'bg_pixelated.png'))
        while True:
            dt = self.clock.tick(self.fps) / 1000.0
            # check events
            self.events(dt)
            # draw and update
            self.display.blit(level, (0,0))
            self.level.draw(self.display)
            self.collisions()
            for idea in self.ideas:
                idea.update(dt, self.level)
                idea.draw(self.display)
            # update the damn screen
            pygame.display.update()

    def events(self, dt):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_d]:
            self.player2.move(dt, 'right')
        if keys[pygame.K_a]:
            self.player2.move(dt, 'left')
        if keys[pygame.K_w]:
            self.player2.move(dt, 'up')
        if keys[pygame.K_s]:
            self.player2.move(dt, 'down')

        if keys[pygame.K_RIGHT]:
            self.player.move(dt, 'right')
        if keys[pygame.K_LEFT]:
            self.player.move(dt, 'left')
        if keys[pygame.K_UP]:
            self.player.move(dt, 'up')
        if keys[pygame.K_DOWN]:
            self.player.move(dt, 'down')

        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    sys.exit()
                    pygame.quit()
                if event.key == pygame.K_SPACE:
                    self.player.punch()
            if event.type == pygame.KEYUP:
                if event.key == pygame.K_DOWN:
                    self.player.phasing = False
                if event.key == pygame.K_s:
                    self.player2.phasing = False


    def collisions(self):
        check_ideas = []
        for num, i in enumerate(self.ideas):
            for e in range(num+1, self.num_ideas):
                check_ideas.append([i, self.ideas[e]])
        for i1, i2 in check_ideas:
            if i1.rect.colliderect(i2.rect):
                if abs(i1.xv) > 1:
                    new_xv1 = (i1.xv * (i1.mass - i2.mass) + 2 * i1.mass * i2.xv) / (i1.mass + i2.mass)
                    new_xv2 = (i2.xv * (i2.mass - i1.mass) + 2 * i2.mass * i1.xv) / (i2.mass + i1.mass)
                    i1.xv = new_xv1
                    i2.xv = new_xv2
                if i1.bottom:
                    if not i2.bottom:
                        i2.yv = -i2.mass
                elif i2.bottom:
                    if not i1.bottom:
                        i1.yv = -i1.mass
                else:
                    new_yv1 = (i1.yv * (i1.mass - i2.mass) + 2 * i1.mass * i2.yv) / (i1.mass + i2.mass)
                    new_yv2 = (i2.yv * (i2.mass - i1.mass) + 2 * i2.mass * i1.yv) / (i2.mass + i1.mass)
                    i1.yv = new_yv1
                    i2.yv = new_yv2