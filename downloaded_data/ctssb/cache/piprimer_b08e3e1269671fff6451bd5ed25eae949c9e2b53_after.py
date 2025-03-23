from time import sleep
#from binaryledcounter import BinaryLEDCounter

def isprime(x):
    """Determine if x is prime."""
    if x<=1:
        return False
    elif (x==2 or x==3):
        return True
    elif (x%2==0):
        return False
    i=3
    while i*i <= x:
        if x%i==0:
            return False
        i+=2
    return True

def countprime(start,counter,delay):
    """Starting at the specified value, count and display numbers
    until the next prime is reached, delaying the specified number
    of seconds between each number. The numbers are displayed on the 
    specified BinaryLEDCounter."""
    x = start
    seenprime = False
    while not seenprime:
        counter.setvalue(x)
        if isprime(x):
            seenprime = True
        else:
            x += 1
            sleep(delay)
    return x


