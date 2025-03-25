import threading
import time

class Seesaw(threading.Thread):
    def __init__( self,agent ):
        threading.Thread.__init__(self)
        self.agent = agent
        self.terminate = False

    def run(self):
        agent = self.agent
        straight_time = 2
        time_start  = time.time()
        speed_aux   = agent.speed
        agent.speed = 100
        agent.set_direction("front")
        while True:
            if not self.terminate:
                break
            if time.time() - time_start > straight_time:
                break
            time.sleep(0.01)
        agent.speed = speed_aux
        agent.set_direction("steady")

    def end(self):
        self.terminate = True


class Test(threading.Thread):
    def __init__( self,agent ):
        threading.Thread.__init__(self)
        self.agent = agent
        self.terminate = False

    def run(self):
        while True:
            time.sleep(0.5)
            print "in routine"
            if self.terminate:
                break

    def end(self):
        self.terminate = True

class FollowWall(threading.Thread):
    def __init__( self,agent ):
        threading.Thread.__init__(self)
        self.agent = agent
        self.terminate = False

    def run(self):
        de
        while True:
                time.sleep(0.01)

                break

    def end(self):
        self.terminate = True
