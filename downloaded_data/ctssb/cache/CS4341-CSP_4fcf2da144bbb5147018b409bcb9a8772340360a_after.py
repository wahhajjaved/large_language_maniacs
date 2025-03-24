# csp.py

from enum import Enum
from constraint import Constraint
import sys
from bag import *
import math

class InputType(Enum):
	vars=1
	values=2
	limits=3
	unaryinc=4
	unaryexc=5
	binaryeq=6
	binarynoteq=7
	binarysimult=8

# constraints
items = {}
# bag_min = 0
# bag_max = 0
# binaryequals = []
# binarynotequals = []
# un_incl = {}
# un_excl = {}
# bin_sim = {}

constraints = Constraint()
bags = []

def parseInput(file):
	f = open(file, "r")
	type=0
	line = f.readline()

	while line:
		if line[0] is '#':
			type += 1
			line = f.readline()
		else:
			line = line.rstrip().split(" ")
			if type is 1:
				items[line[0]]=int(line[1])
			elif type is 2:
				bags.append(Bag(line[0], int(line[1])))
			elif type is 3:
				constraints.bag_min = int(line[0])
				constraints.bag_max = int(line[1])
			elif type is 4:
				constraints.un_incl[line[0]]=line[1:]
			elif type is 5:
				constraints.un_excl[line[0]]=line[1:]
			elif type is 6:
				constraints.binaryequals.append(line[0]+line[1])
			elif type is 7:
				constraints.binarynotequals.append(line[0]+line[1])
			elif type is 8:
				constraints.bin_sim[line[0]+line[1]]=line[2]+line[3]
			line = f.readline()

	f.close()

def within_limits(bag, n):
	print("len(bag.contains) is ",len(bag.contains)," and min is ",constraints.bag_min)
	return len(bag.contains) + n <= constraints.bag_max and len(bag.contains) + n >= constraints.bag_min

def isInAnyBag(item):
	for bag in bags:
		if item in bag.contains:
			return True

	return False

def canAddToBag(item, bag):

	#print("canAddToBag: 1");

	# unary exclusive
	if item in list(constraints.un_excl.keys()):
		if bag.name in constraints.un_excl[item]:
			return False

	#print("canAddToBag: 2");

	# unary inclusive
	if item in list(constraints.un_incl.keys()):
		if bag.name not in constraints.un_incl[item]:
			return False

	#print("canAddToBag: 3");

	# mutually exclusive
	for key in list(constraints.bin_sim.keys()):
		if key[0] is item and bag.name in constraints.bin_sim[key]:
			if key[1] in bag.contains:
				return False
		elif key[1] is item and bag.name in constraints.bin_sim[key]:
			if key[0] in bag.contains:
				return False

	#print("canAddToBag: 4");

	# binary not equals
	for pair in constraints.binarynotequals:
		if pair[0] is item and pair[1] in bag.contains:
			return False
		elif pair[1] is item and pair[0] in bag.contains:
			return False

	#print("canAddToBag: 5");

	# binary equals
	for pair in constraints.binaryequals:
		if pair[0] is item:
			if pair[1] not in bag.contains and isInAnyBag(pair[1]):
				return False
		elif pair[1] is item:
			if pair[0] not in bag.contains and isInAnyBag(pair[1]):
				return False

	#print("canAddToBag: 6");

	# fitting limits
	#print("canAddToBag: bag_max is ", constraints.bag_max)
	if constraints.bag_max is not 0:
		if len(bag.contains) + 1 > constraints.bag_max:
			return False

	#print("canAddToBag: 7");

	return (bag.capacity - bag.weight) >= items[item]

def isCSPcomplete(assignment):
	print("isCSPcomplete starter")

	for item in items:
		print(item)
		if not isInAnyBag(item):
			return False

	# Fit limits
	print("isCSPcomplete: fit limits")
	for bag in assignment:
		if bag.weight < math.floor(bag.capacity * 0.9) :
			print("returning false due to fit limits case 1: weight", bag.weight, "capacity", bag.capacity)
			return False
		
		if constraints.bag_max != 0 and within_limits(bag, 0) == False:
			print("returning false due to fit limits case 2")
			return False

	# Unary inclusive
	for constraint in constraints.un_incl.items():
		variable = constraint[0]
		# find what bag that variable is in...
		target_bag = None
		for bag in assignment:
			if variable in bag.contains:
				target_bag = bag
				break

		if target_bag not in constraint[1]:
			return False
	
	#Unary exclusive
	for constraint in constraints.un_excl.items():
		variable = constraint[0]
		# find what bag that variable is in...
		target_bag = None
		for bag in assignment:
			if variable in bag.contains:
				target_bag = bag
				break

		if target_bag in constraint[1]:
			return False


	#Binary constraints

	#Equal
	#print 
	for constraint in constraints.binaryequals:
		print("182 ", constraint)
		variableOne = constraint[0]
		variableTwo = constraint[1]

		for bag in assignment:
			if variableOne in bag.contains:
				if variableTwo not in bag.contains:
					return False

	#Not equal
	for constraint in constraints.binarynotequals:
		variableOne = constraint[0]
		variableTwo = constraint[1]

		for bag in assignment:
			if variableOne in bag.contains:
				if variableTwo in bag.contains:
					return False


	#Binary simultaneous
	for constraint in constraints.bin_sim.items():
		variableOne = constraint[0][0]
		variableTwo = constraint[0][1]

		bagOne = constraint[1][0]
		bagTwo = constraint[1][1]

		bagOneClass = None
		bagTwoClass = None

		for bag in assignment:
			if bag.name == bagOne:
				bagOneClass = bag
			elif bag.name == bagTwo:
				bagTwoClass = bag

		if variableOne in bagOneClass.contains and variableTwo not in bagTwoClass.contains:
			return False

		if variableOne in bagTwoClass.contains and variableTwo not in bagOneClass.contains:
			return False

		if variableTwo in bagOneClass.contains and variableOne not in bagTwoClass.contains:
			return False

		if variableTwo in bagTwoClass.contains and variableOne not in bagOneClass.contains:
			return False

	return True

def nextUnassignedVariables(assignment):
	#assignment: [] of bags
	variables = list(items.keys())

	for b in range(len(assignment)):
		for i in range(len(assignment[b].contains)):
			if assignment[b].contains[i] in variables:
				variables.remove(assignment[b].contains[i])
				if len(variables) == 0:
					return []

	return min_remaining_var(variables, assignment)


def Backtrack(assignment, i):
	i -= 1
	
	#if len(nextUnassignedVariables(assignment)) is 0:
	#	return

	var = nextUnassignedVariables(assignment)

	for val in least_constraining_vals(var, assignment):
		if canAddToBag(var, val) == True:
			val.addItem(var, items[var])
			break;

	if len(nextUnassignedVariables(assignment)) > 0:
		Backtrack(assignment, i)

	if isCSPcomplete(assignment) == True:
		return True
	else:
		return False


def min_remaining_var(items, bags):
	bags_per_item = {}

	for i in items:
		bags_per_item[i] = 0
		for b in bags:
			if canAddToBag(i, b):
				bags_per_item[i] += 1
		
	return min(bags_per_item, key=bags_per_item.get)

def least_constraining_vals(items, bags):
	items_per_bag = {}

	for b in bags:
		items_per_bag[b] = 0
		for i in items:
			if canAddToBag(i, b):
				items_per_bag[b] += 1
	
	#Flip dictionary
	sortedDict = sorted(items_per_bag, key=items_per_bag.get)
	return reversed(sortedDict)
	

	
def arc_consistency():
	pass


def output(assignment):
	for bag in assignment:
		print(bag.name, " ", end="")
		for variable in bag.contains:
			print(variable, end=" ")
		print(" ")

		print("number of items: " + str(len(bag.contains)))
		print("total weight: " + str(bag.weight) + "/" + str(bag.capacity))
		print("wasted capacity: " + str(bag.wastedCapacity()))
		print("")


if len(sys.argv) != 2:
	print("Proper usage is python csp.py inputfile")
	exit()

sys.setrecursionlimit(99000)

i = 600

parseInput(sys.argv[1])
if Backtrack(bags, i):
	output(bags)
	sys.exit(0)
else:
	print("no solution found")
	sys.exit(1)
