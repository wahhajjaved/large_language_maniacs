import pygame
from .ui_element import ViewElement
from math import sqrt


class FoodSource(ViewElement):
    def __init__(self, view, identifier, x, y, width, height, radius=0, color=pygame.Color("black"),
                 value=100, max_value=100, shape='square', has_image='False', image_path=''):
        super(FoodSource, self).__init__(view, identifier, x, y, width, height)
        self.color = color
        self.radius = radius
        self.shape = shape
        self.has_image = has_image
        self.image_path = image_path
        self.value = value
        self.max_value = max_value

    def draw(self):
        relative_width = self.width * sqrt(self.value / self.max_value)
        relative_height = self.height * sqrt(self.value / self.max_value)

        if self.shape == 'circle':
            relative_radius = self.width * self.value / self.max_value
            pygame.draw.circle(self.view.screen, self.color, (self.x, self.y), relative_radius)
        elif self.shape == 'square':
            pygame.draw.rect(self.view.screen, self.color, (self.x, self.y, relative_width, relative_height))
        if self.has_image is True:
            image = pygame.transform.scale((pygame.image.load(self.image_path)), (relative_width, relative_height))
            self.view.screen.blit(image, self.rect)
