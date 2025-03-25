#!/usr/bin/python

class Time:
    def __init__(self, h, m, s):
        self.hours = h
        self.minutes = m
        self.seconds = s

def timePrint(t):
    minutes = ''
    seconds = ''
    if t.minutes < 10:
        minutes  = '0'+str(t.minutes)
    else:
        minutes = t.minutes
    if t.seconds < 10:
        seconds = '0'+str(t.seconds)
    else:
        seconds = t.seconds 
    print "{}:{}:{}".format(t.hours, minutes, seconds)

def timeParse(t):
    return Time(int(t[0:2]),int(t[3:5]),int(t[6:8])) 

def timeAdd(time1, time2): #ex t1 = '12:34:56' 
    hours = 0
    minutes = 0
    seconds = 0
    
    seconds = time1.seconds + time2.seconds
    if seconds >= 60:
        minutes += 1
        seconds -= 60
    minutes = time1.minutes + time2.minutes
    if minutes >= 60:
        hours += 1
        minutes -= 60
    hours = time1.hours + time2.hours
    return Time(hours,minutes,seconds)

def timeSub(time1, time2): #ex t1 = '12:34:56'
    hours = 0
    minutes = 0
    seconds = 0
    seconds = (time1.seconds - time2.seconds)
    if seconds < 0:
        minutes -= 1
        seconds += 60
    minutes = (time1.minutes - time2.minutes)
    if minutes < 0:
        hours -= 1
        minutes += 60
    hours = (time1.hours - time2.hours)
    #hours = abs(hours)
    return Time(hours, minutes, seconds)

def timeCalculate(t1, t2):
    return timeSub(timeParse(t1), timeParse(t2))

def timeCalculate(t1, t2, t3='00:00:00', flag=1): #flag 1 - count weekends, 0 - dont count 
    if (int(flag) == 1): 
        tmp = timeSub(timeParse(t1),timeParse(t2))
        time = timeAdd(tmp, timeParse(t3))
    else:
        tmp = timeSub(timeParse(t1), timeParse(t2))
        time = timeSub(timeParse(t3), tmp)
    return time

#example usage:
#t = timeCalculate('33:02:55', '31:00:15')
#timePrint(t)
