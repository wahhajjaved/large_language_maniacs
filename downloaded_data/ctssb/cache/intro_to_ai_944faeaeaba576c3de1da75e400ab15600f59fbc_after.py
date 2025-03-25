from random import *
import throw
import darts
 
# The default player aims for the maximum score, unless the
# current score is less than the number of wedges, in which
# case it aims for the exact score it needs. 
#  
# You may use the following functions as a basis for 
# implementing the Q learning algorithm or define your own 
# functions.

LEARNING_RATE = 0.1

Q = {}

actions = None
s_old = None
a_old = None
num_iterations = 0

def start_game():
    global actions, s_old, a_old
    if actions == None:
        print "GAMMA: ", darts.GAMMA
        print "LEARNING_RATE: ", LEARNING_RATE
        print "strategy: ", darts.strategy
        actions = darts.get_actions()
    s_old = throw.START_SCORE
    for s in darts.get_states():
        Q[s] = {}
        for a in actions:
            Q[s][a] = 0.
    a_old = actions[0]#throw.location(throw.INNER_RING, throw.NUM_WEDGES)
    return a_old

def get_target(s_):
    global s_old, a_old, num_iterations
    Q_learning(s_old, s_, a_old)
    s_old = s_

    to_explore = 0
    if darts.strategy == 1:
        to_explore = ex_strategy_one()
    else:
        num_iterations += 1
        to_explore = ex_strategy_two()

    if to_explore:
        a_old = choice(actions)
    else:
        a_old = max([(value,a) for (a,value) in Q[s_].iteritems()])[1]
    return a_old


# Exploration/exploitation strategy one.
def ex_strategy_one():
  return int(random() < .1)


# Exploration/exploitation strategy two.
def ex_strategy_two():
  prob = max((1. / (float(num_iterations)+10.)), 0.005)
  return int(random() < prob)


# The Q-learning algorithm:
def Q_learning(s, s_, a):
    """ s is old score, s_ is new (current) score """
    x = darts.GAMMA * max([Q[s_][a_] for a_ in actions])
    y = darts.R(s,a) + x - Q[s][a]
    Q[s][a] += LEARNING_RATE * y
