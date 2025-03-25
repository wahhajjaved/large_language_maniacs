# Find subarray with 
# Enum written by: Jeffrey Schachtsick
# Better enum written by: Jeffrey Schachtsick
# Divide and Conquer written by: Will Thomas
# Linear code written by: Tom Gariepy

# Import
import time
import os
import csv
import sys
import random

# For enum calculations
def enumerationMaxSubArray(array):
    """ This is the enumeration algorithm for Max Sub Array """
    maxSub = 0
    maxStart = 0
    maxStop = 0
    for i in range(0, len(array)):
        curStart = i
        for j in range(i, len(array)):
            cur = 0
            curStop = j
            for k in range(i, j + 1):
                cur += array[k]
                if cur > maxSub:
                    maxSub = cur
                    maxStart = curStart
                    maxStop = curStop
    resultArray = [maxStart, maxStop, maxSub]
    return resultArray

# For better enum calculations
def betterEnumMaxSubArray(array):
    """ This is the enumeration algorithm for Max Sub Array """
    maxSub = 0
    maxStart = 0
    maxStop = 1
    k = 0
    for i in range(0, len(array)):
        sumNum = 0
        curStart = i
        for j in range(i, len(array)):
            sumNum = sumNum + array[j]
            curStop = j
            if sumNum > maxSub:
                maxSub = sumNum
                maxStart = curStart
                maxStop = curStop
    resultArray = [maxStart, maxStop, maxSub]
    return resultArray

# For divide and conquer calculations
def max_crossover(array, start, middle, end):
     currentLeftSum = 0
     leftSum = -sys.maxint - 1
     currentRightSum = 0
     rightSum = -sys.maxint - 1
     leftIndex = middle
     rightIndex = middle+1

     #For the crossover range we have to find the values for everything
     #including the middle value
     for i in range(middle, start-1, -1):
          currentLeftSum += array[i]
          if currentLeftSum > leftSum:
               leftSum = currentLeftSum
               leftIndex = i
     for j in range(middle+1, end+1):
          currentRightSum += array[j]
          if currentRightSum > rightSum:
               rightSum = currentRightSum
               rightIndex = j
     return (leftIndex, rightIndex, leftSum + rightSum)

# Used for algorithm #3, returns maxSubArray sum
def max_subarray(array, start = 0, end=None):
     #provide initial value for end
     if end is None:
          end = len(array)-1

     #Base case. If there is only 1 value left in array
     if end == start:
          return start, end, array[start]
     else:
          middle = (start + end) / 2

          #We have to get values for left side, right side, and middle where they cross over, then compare
          leftLow, leftHigh, leftSum = max_subarray(array, start, middle)
          rightLow, rightHigh, rightSum = max_subarray(array, middle + 1, end)
          crossLow, crossHigh, crossSum = max_crossover(array, start, middle, end)

          #Return array indices and sum of the solution
          if leftSum >= rightSum and leftSum >= crossSum:
               resultArray = [leftLow, leftHigh, leftSum]
               return resultArray
          elif rightSum >= leftSum and rightSum >= crossSum:
               resultArray = [rightLow, rightHigh, rightSum]
               return resultArray
          else:
               resultArray = [crossLow, crossHigh, crossSum]
               return resultArray

# For linear calculations
def linearSearch(array):
	curStart = 0
	curStop = 0
	curSum = 0

	maxStart = 0
	maxStop = 0
	maxSum = 0
	for x in range(0, len(array)):
		if (array[x] > curSum + array[x]):
			curSum = array[x]
			curStart = x
			curStop = x
		else:
			curSum = curSum + array[x]
			curStop = x

		if (curSum > maxSum):
			maxSum = curSum
			maxStart = curStart
			maxStop = curStop

	resultArray = [maxStart, maxStop, maxSum]
	return resultArray

# To check to see if the file exists
def getPath():
    """ Verify MSS_TestProblems-1.txt is available. """
    valid = False
    file = "MSS_TestProblems-1.txt"
    if os.path.isfile(file):
        print("\nFile located...")
        valid = True
    else:
        print("\nThe file is not located")
    return valid

# Main function which finds the input file 
# and sends the arrays to the functions
# Prints results to the screen and writes to file
def main():
	# File names
	rfname = "MSS_Problems.txt"
	wfname = "MSS_Results.txt"

	# Check to see if file exists
	fileCheck = os.path.isfile(rfname)
	if (fileCheck == False):
		print("ERROR: " + rfname + " not found.")
		return 1

	print("Program running")

	# Create results page
	with open(wfname, 'wt') as resultFile:	

		# Open the file and read each line by line
		with open(rfname, 'rt') as fileArr:
			fStream = csv.reader(fileArr)
			for row in fStream:
				if (len(row) > 0):
					# Convert the list to be able to send it to the funcitons
					row[0] = row[0].replace('[', '')
					row[len(row) - 1] = row[len(row) - 1].replace(']', '')
				
					row = list(map(int, row))

					# Calc enum time
					startTime = time.clock()
					result = enumerationMaxSubArray(row)
					stopTime = time.clock()

					resultTime = stopTime - startTime

					print("Enum Result: " + str(result[2]))
					print("Enum Running Time: " + str(resultTime))

					resultFile.write("Enum Array: ")
					for x in range(result[0], result[1] + 1):
						if (x > result[0]):
							resultFile.write(", ")
						resultFile.write(str(row[x]))

					resultFile.write("\nEnum sum: " + str(result[2]) + "\n")

					# Calc better enum time
					startTime = time.clock()
					result = betterEnumMaxSubArray(row)
					stopTime = time.clock()

					resultTime = stopTime - startTime

					print("Better Enum Result: " + str(result[2]))
					print("Better Enum Running Time: " + str(resultTime))

					resultFile.write("Better Enum Array: ")
					for x in range(result[0], result[1] + 1):
						if (x > result[0]):
							resultFile.write(", ")
						resultFile.write(str(row[x]))

					resultFile.write("\nBetter Enum sum: " + str(result[2]) + "\n")

					# Calc divide and conquer time
					startTime = time.clock()
					result1 = max_subarray(row, 0, len(row)-1)
					stopTime = time.clock()

					resultTime = stopTime - startTime

					print("Divide and Conquer Result: " + str(result[2]))
					print("Divide and Conquer Running Time: " + str(resultTime))

					resultFile.write("Divide and Conquer Array: ")
					for x in range(result[0], result[1] + 1):
						if (x > result[0]):
							resultFile.write(", ")
						resultFile.write(str(row[x]))

					resultFile.write("\nDivide and Conquer sum: " + str(result[2]) + "\n")

					# Calc linear time
					startTime = time.clock()
					result = linearSearch(row)
					stopTime = time.clock()

					resultTime = stopTime - startTime

					print("Linear Result: " + str(result[2]))
					print("Linear Running Time: " + str(resultTime))

					resultFile.write("Linear Array: ")
					for x in range(result[0], result[1] + 1):
						if (x > result[0]):
							resultFile.write(", ")
						resultFile.write(str(row[x]))

					resultFile.write("\nLinear sum: " + str(result[2]) + "\n\n")

main()