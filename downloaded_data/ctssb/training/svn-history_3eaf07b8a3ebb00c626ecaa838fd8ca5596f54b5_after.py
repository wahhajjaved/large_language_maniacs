from math import fmod,floor

import numpy
from numpy import zeros, array
from numpy.oldnumeric import Float
from numpy import zeros, array, size, empty, object_
#import scipy

import topo
    
max_value = 0
global_index = ()

def _complexity_rec(x,y,index,depth,fm):
        global max_value
        global global_index
        if depth<size(fm.features):
            for i in range(size(fm.features[depth].values)):
                _complexity_rec(x,y,index + (i,),depth+1,fm)
        else:
            if max_value < fm.full_matrix[index][x][y]:
                global_index = index
                max_value = fm.full_matrix[index][x][y]    
    
def complexity(full_matrix):
    global global_index
    """This function expects as an input a object of type FullMatrix which contains
    responses of all neurons in a sheet to stimuly with different varying parameter values.
    One of these parameters (features) has to be phase. In such case it computes the classic
    modulation ratio (see Hawken et al. for definition) for each neuron and returns them as a matrix.
    """
    rows,cols = full_matrix.matrix_shape
    complexity = zeros(full_matrix.matrix_shape)
    complex_matrix = zeros(full_matrix.matrix_shape,object_)
    fftmeasure = zeros(full_matrix.matrix_shape,Float)
    i = 0
    
    for f in full_matrix.features:
        if f.name == "phase":
            phase_index = i
            break
        i=i+1
    
    sum = 0.0
    res = 0.0
    average = 0.0
    for x in range(rows):
        for y in range(cols):
            complex_matrix[x,y] = []
            _complexity_rec(x,y,(),0,full_matrix)
            
            #compute the sum of the responses over phases given the found index of highest response 
            iindex = array(global_index)
            sum = 0.0
            for i in range(size(full_matrix.features[phase_index].values)):
                iindex[phase_index] = i
                sum = sum + full_matrix.full_matrix[tuple(iindex.tolist())][x][y]
                
            #average
            average = sum / float(size(full_matrix.features[phase_index].values))
            
            res = 0.0
            #compute the sum of absolute values of the responses minus average
            for i in range(size(full_matrix.features[phase_index].values)):
                iindex[phase_index] = i
                res = res + abs(full_matrix.full_matrix[tuple(iindex.tolist())][x][y] - average)
                complex_matrix[x,y] = complex_matrix[x,y] + [full_matrix.full_matrix[tuple(iindex.tolist())][x][y]]
            complexity[x,y] = res / (2*sum)
            fft = numpy.fft.fft(complex_matrix[x,y]+complex_matrix[x,y]+complex_matrix[x,y]+complex_matrix[x,y],2048)
            first_har = 2048/len(complex_matrix[0,0])
            fftmeasure[x,y] = (2 *abs(fft[first_har]) * abs(fft[first_har]) )/(abs(fft[0]) * abs(fft[0]))
#            print complex_matrix[x,y]
#            print fft
#            print fftmeasure[x,y]

    return fftmeasure
