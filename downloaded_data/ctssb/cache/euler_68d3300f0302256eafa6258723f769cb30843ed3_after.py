"""
Project Euler Problem 1
=======================

If we list all the natural numbers below 10 that are multiples of 3 or 5,
we get 3, 5, 6 and 9. The sum of these multiples is 23.

Find the sum of all the multiples of 3 or 5 below 1000.
"""

def solution(a, b, n):
    "Prints Multiples of 'a' and 'b' to a set range 'n'"
    totalsum = 0
    for i in range(0, n):
        if (i % a) is 0 or (i % b) is 0:
            totalsum += i
    return totalsum

print(solution(3, 5, 1000))
