
# Import the python modules
import pygame


# Import the base widget
from gui.widgets.widget import *


# Import the text widget
from gui.widgets.text import *


class IpInput(Widget):

    FocusColor   = (0xfb, 0x81, 0x14)
    DefaultColor = (0x42, 0x42, 0x42)

    def __init__(self, screen, x, y, width, height):

        super(IpInput, self).__init__(screen, x, y, width, height)

        self.__text = Text(screen, "IP Address", (240, 240, 240), x, y, width, height, True, textSize = 30)

        self.__isFocused = False

        self.__keyMap = {
            pygame.K_0 : False,
            pygame.K_1 : False,
            pygame.K_2 : False,
            pygame.K_3 : False,
            pygame.K_4 : False,
            pygame.K_5 : False,
            pygame.K_6 : False,
            pygame.K_7 : False,
            pygame.K_8 : False,
            pygame.K_9 : False,
            pygame.K_PERIOD : False,
            pygame.K_BACKSPACE : False
        }


    def keyPress(self, key):

        text = self.__text.text()

        if text == "IP Address":

            text = ""

        if key == pygame.K_BACKSPACE and len(text) > 0:

            text = self.__text.text()[:-1]

        elif key != pygame.K_BACKSPACE:

            text += pygame.key.name(key)

        if len(text) == 0:

            text = "IP Address"

        self.__text.setText(text[0:14])


    def updateInput(self):

        keys = pygame.key.get_pressed()

        for key in self.__keyMap.keys():

            if keys[key] != self.__keyMap[key]:

                if keys[key]:

                    self.keyPress(key)

                    self.__keyMap[key] = True

                else:

                    self.__keyMap[key] = False


    def text(self):

        return self.__text.text()


    def render(self):

        if self.isInside(pygame.mouse.get_pos()):

            color = IpInput.FocusColor

            if pygame.mouse.get_pressed()[0]:

                self.__isFocused = True


        elif pygame.mouse.get_pressed()[0]:

            color = IpInput.DefaultColor
            self.__isFocused = False


        else:

            color = IpInput.DefaultColor

        if self.__isFocused:

            color = IpInput.FocusColor

            self.updateInput()


        pygame.draw.rect(self.screen().surface(), color, self.rect(), 2)

        self.__text.render()
