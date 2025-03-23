def dfs_iter(graph, start, visited=[]):
	stack=[start]
	while stack:
		v = stack.pop() #LIFO
		if v not in visited:
			visited.append(v)
			stack.extend(graph[v])
	return visited

def test_algorithm():
	graph = {'A':['B','C'],'B':['D','E'],'C':['D','E'],'D':['E'],'E':['A']}
	print dfs_iter(graph, 'A')

test_algorithm()