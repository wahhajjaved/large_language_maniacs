from BlinkyTape import BlinkyTape
import time

import GlobalSettings as G

flashTime = 1/10.0

def fourOnTheFloor(blinky):
    beat = 1
    downbeatColor = G.color
    offbeatColor  = [255 - G.color[0],255 - G.color[1], 255 - G.color[2]]
    while G.keepGoing is False:
        continue
    while True:
        for i in range(0,150):
            if beat == 1:
                blinky.sendPixel(downbeatColor[0],downbeatColor[1],downbeatColor[2])
            else:
                blinky.sendPixel(offbeatColor[0],offbeatColor[1],offbeatColor[2])
        blinky.show()
        beat = beat % 4 + 1 #[1,4]
        print "Flash time: " + str(flashTime)
        time.sleep(flashTime)
        if G.keepGoing is False:
            G.keepGoing = True
            return
        for i in range(0,150):
            blinky.sendPixel(0,0,0)
        blinky.show()
        print "Sleep time: " + str(G.bpm/60 - flashTime)
        time.sleep(60/G.bpm - flashTime)
        if G.keepGoing is False:
            G.keepGoing = True
            return

def alternatePush(blinky):
    position = 0
    primaryColor = G.color
    secondaryColor = [(G.color[0] + 85) % 256,(G.color[1] + 85) % 256,(G.color[2] + 85) % 256]
    tertiaryColor = [(secondaryColor[0] + 85) % 256,(secondaryColor[1] + 85) % 256,(secondaryColor[2] + 85) % 256]
    colors = [primaryColor,secondaryColor,tertiaryColor]
    while G.keepGoing is False:
        continue
    while True:
        for i in range(0,150):
            color = colors[i % position]
            blinky.sendPixel(color[0],color[1],color[2])
        blinky.show()
        position = position % 2 + 1
        time.sleep(1/float(G.speed))
        if G.keepGoing is False:
            G.keepGoing = True
            return