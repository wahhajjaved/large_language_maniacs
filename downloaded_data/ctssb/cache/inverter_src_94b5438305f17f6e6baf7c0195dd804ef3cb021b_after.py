
# io.py
# input/output functions for mat_inv.py
#
# (c) 2014 Paul T. Baker, bakerp@geneseo.edu
# licence: GNU GPLv3 <http://www.gnu.org/licenses/gpl.txt>

import sys
import getopt
import numpy as np


def parse_options(argv):
    """command line parser"""
    inputfile = 'mat_in.dat'
    outputfile = 'mat_out.dat'
    seed = None
    number = 10000
    burn = int(number/5)
    try:
        opts, args = getopt.getopt(
                         argv,
                         "hi:o:s:n:b:",
                         ["help","ifile=","ofile=","seed=","number=","burn-in"]
                     )
    except getopt.GetoptError:
        print('  ERROR: invalid options, try --help for more info')
        sys.exit(2)
    for opt, arg in opts:
        if opt in ('-h',"--help"):
            print('mcmc_mat_inv.py [OPTIONS]')
            print('')
            print('  options:')
            print('')
            print('   --help, -h                   display this message')
            print('')
            print('   --ifile, -i <input_file>     contains square matrix to invert')
            print('   --ofile, -o <output_file>    stores inverse of matrix')
            print('')
            print('   --seed, -s <seed>            seed to initialize random()')
            print('   --number, -n <number>        number of samples in MCMC')
            print('   --burn-in, -b <N_burn>       length of burn in')
            print('')
            sys.exit()
        elif opt in ("-i", "--ifile"):
            inputfile = arg
        elif opt in ("-o", "--ofile"):
            outputfile = arg
        elif opt in ("-s", "--seed"):
            seed = int(arg)
        elif opt in ("-n", "--number"):
            number = int(arg)
        elif opt in ("-b", "--burn-in"):
            burn = int(arg)
    return (inputfile, outputfile, number, burn, seed)


def get_Mat(filename):
    """read a square matrix from file"""
    mat = np.loadtxt(filename)
    if mat.shape[0] != mat.shape[1]:
        print( '  ERROR: input matrix is not square %dx%d'%(mat.shape[0], mat.shape[1]) )
        sys.exit(2)
    return mat


def print_Mat(mat,filename):
    """print a matrix to file"""
    np.savetxt(filename, mat, fmt='%+.9e')


