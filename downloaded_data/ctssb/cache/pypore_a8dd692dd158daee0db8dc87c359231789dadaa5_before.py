'''
Created on May 23, 2013

@author: parkin
'''
import scipy.io as sio
import numpy as np
import os

def openData(filename, decimate=False):
    '''
    Opens a datafile and returns a dictionary with the data in 'data'.
    If unable to return, will return an error message.
    
    Assumes '.log' extension is Chimera data.  Chimera data requires a '.mat'
     file with the same name to be in the same folder.
     
    Assumes '.hkd' extension is Heka data.
    '''
    if '.log' in filename:
        return openChimeraFile(filename, decimate)
    if '.hkd' in filename:
        return openHekaFile(filename, decimate)
        
    return 'File not specified with correct extension. Possibilities are: \'.log\', \'.hkd\''
    
def prepareDataFile(filename):
    '''
    Opens a data file, reads relevant parameters, and 
    
    Assumes '.log' extension is Chimera data.  Chimera data requires a '.mat'
     file with the same name to be in the same folder. - not yet implemented
     
    Assumes '.hkd' extension is Heka data.
    '''
    if '.log' in filename:
        return prepareChimeraFile(filename)
    if '.hkd' in filename:
        return prepareHekaFile(filename)
        
    return 'File not specified with correct extension. Possibilities are: \'.log\', \'.hkd\''

def openChimeraFile(filename, decimate=False):
    '''
    Reads files created by the Chimera acquisition software.  It requires a
    filename.log file with the data, and a filename.mat file containing the
    parameters of the run.
    
    Returns a dictionary with the keys/values in the filename.mat file
    as well as 'data', a numpy array of the current values
    '''
    # remove 'log' append 'mat'
    datafile, p = prepareChimeraFile(filename)
    
    ADCBITS = p['ADCBITS']
    ADCvref = p['ADCvref']
    datatype = p['datatype']
    specsfile = p['specsfile']
    

    bitmask = (2**16) - 1 - (2**(16-ADCBITS) - 1);
    if decimate:
        # Calculate number of points in the dataset
        filesize = os.path.getsize(filename)
        num_points = filesize/datatype.itemsize
        block_size = 5000
        decimated_size = int(2*num_points/block_size)
        if num_points%block_size > 0: # will there be a block at the end with < block_size datapoints?
            decimated_size = decimated_size + 2
        logdata = np.zeros(decimated_size)
        i = 0
        while True:
            rawvalues = np.fromfile(datafile,datatype,block_size)
            if rawvalues.size < 1:
                break
            readvalues = -ADCvref + (2*ADCvref)*(rawvalues & bitmask)/(2**16)
            logdata[i] = np.max(readvalues)
            logdata[i+1] = np.min(readvalues)
            i = i + 2
            
        # Change the sample rate
        specsfile['SETUP_ADCSAMPLERATE'][0][0] = specsfile['SETUP_ADCSAMPLERATE'][0][0]*2/block_size
    else:
        rawvalues = np.fromfile(datafile,datatype)
        readvalues = rawvalues & bitmask
        logdata = -ADCvref + (2*ADCvref) * readvalues / (2**16);

    specsfile['data'] = [logdata]
    return specsfile

def prepareChimeraFile(filename):
    # remove 'log' append 'mat'
    s = list(filename)
    s.pop()
    s.pop()
    s.pop()
    s.append('mat')
    # load the matlab file with parameters for the runs
    specsfile = sio.loadmat("".join(s))

    ADCBITS = specsfile['SETUP_ADCBITS'][0][0]
    ADCvref = specsfile['SETUP_ADCVREF'][0][0]
    
    datafile = open(filename)
    datatype = np.dtype('<u2')
    
    p = {'ADCBITS': ADCBITS, 'ADCvref': ADCvref, 'datafile': datafile,
         'datatype': datatype}
    
    return datafile, p

# Data types list, in order specified by the HEKA file header v2.0.
# Using big-endian.
# Code 0=uint8,1=uint16,2=uint32,3=int8,4=int16,5=int32,
#    6=single,7=double,8=string64,9=string512
encodings = [np.dtype('>u1'), np.dtype('>u2'), np.dtype('>u4'), 
             np.dtype('>i1'), np.dtype('>i2'), np.dtype('>i4'), 
             np.dtype('>f4'), np.dtype('>f8'), np.dtype('>S64'), 
             np.dtype('>S512')]

def prepareHekaFile(filename):
    f = open(filename)
    # Check that the first line is as expected
    line = f.readline()
    if not line == 'Nanopore Experiment Data File V2.0\r\n':
        return 'Heka data file format not recognized.'
    # Just skip over the file header text, should be always the same.
    while True:
        line = f.readline()
        if 'End of file format' in line:
            break
    
    # So now f should be at the binary data.
    
    ## Read binary header parameter lists
    per_file_param_list = _readHekaHeaderParamList(f, np.dtype('>S64'), encodings)
    per_block_param_list = _readHekaHeaderParamList(f, np.dtype('>S64'), encodings)
    per_channel_param_list = _readHekaHeaderParamList(f, np.dtype('>S64'), encodings)
    channel_list = _readHekaHeaderParamList(f, np.dtype('>S512'), encodings)
    
    ## Read per_file parameters
    per_file_params = _readHekaHeaderParams(f, per_file_param_list)
    
    ## Calculate sizes of blocks, channels, etc
    per_file_header_length = f.tell()
    
    # Calculate the block lengths
    per_channel_per_block_length = _getParamListByteLength(per_channel_param_list)
    per_block_length = _getParamListByteLength(per_block_param_list)
    
    channel_list_number = len(channel_list)
    
    header_bytes_per_block = per_channel_per_block_length*channel_list_number
    data_bytes_per_block = per_file_params['Points per block'] * 2 * channel_list_number
    total_bytes_per_block = header_bytes_per_block + data_bytes_per_block + per_block_length
    
    # Calculate number of points per channel
    filesize = os.path.getsize(filename)
    num_blocks_in_file = int((filesize - per_file_header_length)/total_bytes_per_block)
    remainder = (filesize - per_file_header_length)%total_bytes_per_block
    if not remainder == 0:
        print 'Error, data file ends with incomplete block'
        return
    points_per_channel_total = per_file_params['Points per block'] * num_blocks_in_file
    points_per_channel_per_block = per_file_params['Points per block']
    
    p = {'per_file_param_list': per_file_param_list, 'per_block_param_list': per_block_param_list,
         'per_channel_param_list': per_channel_param_list, 'channel_list': channel_list,
         'per_file_params': per_file_params, 'per_file_header_length': per_file_header_length,
         'per_channel_per_block_length': per_channel_per_block_length,
         'per_block_length': per_block_length, 'channel_list_number': channel_list_number,
         'header_bytes_per_block': header_bytes_per_block, 
         'data_bytes_per_block': data_bytes_per_block,
         'total_bytes_per_block': total_bytes_per_block,  'filesize': filesize,
         'num_blocks_in_file': num_blocks_in_file,
         'points_per_channel_total': points_per_channel_total,
         'points_per_channel_per_block': points_per_channel_per_block}
    
    return f, p


def openHekaFile(filename, decimate=False):
    '''
    Gets data from a file generated by Ken's LabView code v2.0 for HEKA acquisition.
    Visit https://drndiclab-bkup.physics.upenn.edu/wiki/index.php/HKD_File_I/O_SubVIs
        for a description of the heka file format.
        
    Returns a dictionary with entries:
        -'data', a numpy array of the current values
        -'SETUP_ADCSAMPLERATE'
        
    Currently only works with one channel measurements
    '''
    # Open the file and read all of the header parameters
    f, p = prepareHekaFile(filename)
    
    per_file_params = p['per_file_params']
    channel_list = p['channel_list']
    num_blocks_in_file = p['num_blocks_in_file']
    points_per_channel_total = p['points_per_channel_total']
    per_block_param_list = p['per_block_param_list']
    per_channel_param_list = p['per_channel_param_list']
    points_per_channel_per_block = p['points_per_channel_per_block']
    
    data = []
    sample_rate = 1.0/per_file_params['Sampling interval']
    for _ in channel_list:
        if decimate: # If decimating, just keep max and min value from each block
            data.append(np.zeros(num_blocks_in_file*2))
        else:
            data.append(np.zeros(points_per_channel_total))  # initialize array
        
    for i in range(0,num_blocks_in_file):
        block = _readHekaNextBlock(f, per_file_params, per_block_param_list, per_channel_param_list, channel_list, points_per_channel_per_block)
        for j in range(0,len(block['data'])):
            if decimate: # if decimating data, only keep max and min of each block
                data[j][2*i] = np.max(block['data'][0])
                data[j][2*i+1] = np.min(block['data'][0])
            else:
                data[j][i*points_per_channel_per_block:(i+1)*points_per_channel_per_block] = block['data'][0]
            
    if decimate:
        sample_rate = sample_rate*2/per_file_params['Points per block'] # we are downsampling
        
    # return dictionary
    # samplerate is i [[]] because of how chimera data is returned.
    specsfile = {'data': data, 'SETUP_ADCSAMPLERATE': [[sample_rate]]}
    
    return specsfile

def _readHekaNextBlock(f, per_file_params, per_block_param_list, per_channel_param_list, channel_list, points_per_channel_per_block):
    '''
    Reads the next block of heka data.
    Returns a dictionary with 'data', 'per_block_params', and 'per_channel_params'.
    '''
    
    # Read block header
    per_block_params = _readHekaHeaderParams(f, per_block_param_list)
    
    # Read per channel header
    per_channel_block_params = []
    for _ in channel_list: # underscore used for discarded parameters
        channel_params = {}
        # i[0] = name, i[1] = datatype
        for i in per_channel_param_list:
            channel_params[i[0]] = np.fromfile(f, i[1], 1)[0]
        per_channel_block_params.append(channel_params)
    
    # Read data
    data = []
    dt = np.dtype('>i2') # int16
    for i in range(0,len(channel_list)):
        values = np.fromfile(f, dt, points_per_channel_per_block) * per_channel_block_params[i]['Scale']
        data.append(values)
    
    block = {'data': data,'per_block_params': per_block_params, 'per_channel_params': per_channel_block_params}
    
    return block
    
def _getParamListByteLength(param_list):
    '''
    Returns the length in bytes of the sum of all the parameters in the list.
    Here, list[i][0] = param, list[i][1] = np.dtype
    '''
    size = 0
    for i in param_list:
        size = size + i[1].itemsize
    return size
    
def _readHekaHeaderParams(f, param_list):
    
    params = {}
    # pair[0] = name, pair[1] = np.datatype
    for pair in param_list:
        params[pair[0]] = np.fromfile(f, pair[1], 1)[0]
    return params
        
def _readHekaHeaderParamList(f, datatype, encodings):
    '''
    Reads the binary parameter list of the following format:
        3 null bytes
        1 byte uint8 - how many params following
        params - 1 byte uint8 - code for datatype (eg encoding[code])
                 datatype.intemsize bytes - name the parameter
    Returns a list of parameters, with
        item[0] = name
        item[1] = numpy datatype
    '''
    param_list = []
    f.read(3)  # read null characters?
    num_params = np.fromfile(f, np.uint8, 1)[0]
    for _ in range(0, num_params):
        type_code = np.fromfile(f, np.uint8,1)[0]
        name = np.fromfile(f, datatype, 1)[0].strip()
        param_list.append([name, encodings[type_code]])
    return param_list


