from mip.model import *
from sys import stdout, argv
from time import process_time
import time
import timeout_decorator

Solvers = ['cbc', 'gurobi']
N = range(100, 1001, 100)

TIMEOUT = 1000
execTime = TIMEOUT
modelCols = 0
modelRows = 0
modelNz = 0


@timeout_decorator.timeout(TIMEOUT)
def gen_model(n, solver, f):
    global execTime
    global modelCols
    global modelRows
    global modelNz
    execTime = TIMEOUT
    modelCols = 0
    modelRows = 0
    modelNz = 0
    st = time.time()
    queens = Model('queens', MINIMIZE, solver_name=solver)

    x = [[queens.add_var('x({},{})'.format(i, j), var_type='B', obj=-1.0)
          for j in range(n)] for i in range(n)]

    # one per row
    for i in range(n):
        queens += xsum(x[i][j] for j in range(n)) == 1, 'row({})'.format(i)

    # one per column
    for j in range(n):
        queens += xsum(x[i][j] for i in range(n)) == 1, 'col({})'.format(j)

    # diagonal \
    for p, k in enumerate(range(2 - n, n - 2 + 1)):
        queens += xsum(x[i][j] for i in range(n) for j in range(n)
                       if i - j == k) <= 1, 'diag1({})'.format(p)

    # diagonal /
    for p, k in enumerate(range(3, n + n)):
        queens += xsum(x[i][j] for i in range(n) for j in range(n)
                       if i + j == k) <= 1, 'diag2({})'.format(p)

    ed = time.time()
    execTime = ed-st
    modelCols = queens.num_cols
    modelRows = queens.num_rows
    modelNz = queens.num_nz


for solver in Solvers:
    f = open('queens-{}.csv'.format(solver), 'w')
    for n in N:
        gen_model(n, solver, f)
        f.write('{},{},{},{},{:.4f}\n'.format(n, modelCols,
                                              modelRows, modelNz, execTime))
        f.flush()
    f.close()
