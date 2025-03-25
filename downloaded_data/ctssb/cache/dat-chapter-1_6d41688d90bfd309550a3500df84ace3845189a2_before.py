

def create_fib(n):
	result = []
 	a, b = 1, 1
 	while b <= n:
 		result.append(b)
 		a, b = b, a+b
 	return result


def sum_even(n):
	answer = 0
	for i in num:
		if i % 2 == 0:
			answer += i
	return answer


fib = create_fib(4000000)
print (sum_even(fib))

