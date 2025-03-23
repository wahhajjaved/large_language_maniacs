import pygame
from pygame.locals import *

class image_class:
   """A class to hold information about sprites"""

   def __init__(self,filename,scale_factor,image_pos):
      self.filename = filename
      self.scale_factor = scale_factor
      self.pos = image_pos  #Should be x,y coordinates in a list, this is the center of the image
      self.vel = [0,0]  #Velocity of the image
      self.collided = False #This variable is True if a meeting/collision has occured with Mittens

      self.image = pygame.image.load(filename).convert_alpha()
      self.size_tuple = self.image.get_size()
      self.size = [0,0]
      self.size[0] = int(self.size_tuple[0]*self.scale_factor)
      self.size[1] = int(self.size_tuple[1]*self.scale_factor)
      self.image = pygame.transform.scale(self.image,self.size)

   def update_position(self,key_press,screen_size):
      if key_press == pygame.K_LEFT:
         if self.pos[0] > 0:
            if self.vel[0] <= 0:
               self.vel[0] -= 0.01
            else:
               self.vel[0] = 0.0
            self.pos[0] = self.pos[0] + self.vel[0]
      if key_press == pygame.K_RIGHT:
         if self.pos[0] < (screen_size[0] - self.size[0]):
            if self.vel[0] >= 0:
               self.vel[0] += 0.01  
            else:
               self.vel[0] = 0
            self.pos[0] = self.pos[0]  + self.vel[0]
      if key_press == pygame.K_UP:
         if self.pos[1] > 0:
            if self.vel[1] <= 0:
               self.vel[1] -= 0.01
            else:
               self.vel[1] = 0.0
            self.pos[1] = self.pos[1] + self.vel[1]
      if key_press == pygame.K_DOWN:
         if self.pos[1] < (screen_size[1]- self.size[1]):
            if self.vel[1] >= 0:
               self.vel[1] += 0.01
            else:
               self.vel[1] = 0.0
            self.pos[1] = self.pos[1] + self.vel[1]
      if (key_press != pygame.K_UP) and (key_press != pygame.K_DOWN) and (key_press !=pygame.K_LEFT) and (key_press != pygame.K_RIGHT):
         self.vel[0] = 0.99*self.vel[0]
         self.vel[1] = 0.99*self.vel[1]
         #Check to make sure the image stays on the screen before updating pos
         if (self.pos[0] > 0) and (self.pos[0] < screen_size[0] -self.size[0]) and (self.pos[1] > 0) and (self.pos[1] < screen_size[1] - self.size[1]):
           self.pos[0] = self.pos[0] + self.vel[0]
           self.pos[1] = self.pos[1] + self.vel[1]
       
   def update_collision_status(self,collision):
      self.collided = True

