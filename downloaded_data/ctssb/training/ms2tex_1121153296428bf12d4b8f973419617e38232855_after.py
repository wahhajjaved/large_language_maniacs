#!/usr/bin/env python3
import math
import sys

def error(str, exitcode=1):
	print(sys.argv[0] + ": error: " + str, file=sys.stderr)
	exit(exitcode)

def mod_figure_width(n):
	width=1
	# if the number is negative, 1 should be added to width for the '-' sign
	if n<0:
		width+=1

	n=abs(n)

	while n>=10:
		n/=10
		width+=1

	return width

def main():
	while True:
		try:
			s=input()
		except EOFError:
			break

		s=s.split()

		if len(s)==0 or math.modf(math.sqrt(len(s)))[0]!=0:
			error("invalid length of input line: " + str(len(s)))
		Ceilings=len(s)
		X=int(math.sqrt(Ceilings))
		max_len=max([len(i) for i in s])

		print("\\begin{tabular}{" + "|c"*X + "|}", end="")
		print(" \\hline")
		for i in range(Ceilings):
			print(" ", end="")
			print("%*s"%(max_len, s[i]), end=" ")
			if i%X!=X-1:
				print("&", end="")
			else:
				print("\\\\\\hline")
		print("\\end{tabular}")

if __name__=='__main__':
	main()
