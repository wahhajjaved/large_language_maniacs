import math

def time(n):
    """ Return the number of steps
    necessary to calculate
    `print countdown(n)`"""
    steps = 0
    # YOUR CODE HERE
    steps = 3 + math.ceil(n/5)*2
    return steps

def countdown(x):
    y = 0
    while x > 0:
        x = x - 5
        y = y + 1
        #print x, y
    print y

print countdown(20)
print time(20)
