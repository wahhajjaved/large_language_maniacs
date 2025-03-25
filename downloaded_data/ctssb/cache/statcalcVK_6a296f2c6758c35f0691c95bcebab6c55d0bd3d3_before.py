import math
from Calculator.Addition import addition
from Calculator.Division import division
from Calculator.Subtraction import subtraction
from Calculator.Square import square
from Calculator.Sqrt import root
from Statistics.SampleGenerator import getSample
from Statistics.MeanTest import newmean
import statistics
import random


def sampst_dev(lst):
    ss = random.randint(1,len(lst))
    new_values = getSample(lst, ss)
    new_mean = newmean(new_values)
    total = 0
    for row in new_values:
        error = subtraction(row, new_mean)
        error_sq = square(error)
        total = addition(total, error_sq)
    i = len(new_values)
    b = division(subtraction(1,i), total)
    std = math.sqrt(b)  #works
    #std = root(b)      
    actual_sd = statistics.stdev(new_values) #Calculated using stat library to compare
    return std, actual_sd


