from timeit import default_timer as dft

def file_reader():
    #open file, read in all the lines
    with open("MSS_TestProblems.txt", 'r') as f:
        temp_data = f.readlines()
    f.close()
    #create array for data
    test_data = []
    
    #strip out all the syntax and split strings into lines
    for line in temp_data:
        line = line.strip().strip(']').strip('[')
        test_data.append([int(x.strip()) for x in line.split(',')])
    
    #return test data
    return test_data

def enumerate_case(array):
    
    #initialize max sum
    max_sum = 0
    max_array = []
    #first iteration
    for x in range(0, len(array)):
        #initialize total
        
        
        #second interator
        for i in range(x, len(array)):
            total = 0
            array_test = []
            #sum total
            for y in range(x, i+1):
                total += array[y]
                array_test.append(array[y])
                
            #if sum is larger than max_sum, set new max_sum
            if total > max_sum:
                max_sum = total
                max_array = array_test

    return max_sum, max_array

def time_enum(array):
    start = dft()
    max_sum, max_array = enumerate_case(array)
    stop = dft()
    
    enum_time = stop - start
    
    return enum_time, max_sum, max_array
    
#I think this is actually the better enum case?
def better_enumerate_case(array):
    
    #initialize max sum
    max_sum = 0

    #first iteration
    for x in range(0, len(array)):
        #initialize total
        total = 0
        
        #second interator
        for i in range(x, len(array)):
            
            #sum total
            total += array[i]
            
            #if sum is larger than max_sum, set new max_sum
            if total > max_sum:
                max_sum = total
                
                #this line tells you the values in your max array
                sum_arr = [j for j in array[x:i+1]]
                
                
    return max_sum, sum_arr

def time_better(array):
    start = dft()
    max_sum, max_array = better_enumerate_case(array)
    stop = dft()
    
    enum_time = stop - start
    
    return enum_time, max_sum, max_array
        
            
def d_and_c(arr, max_sum, max_arr):
    
    if len(arr) == 1:
        if arr[0] > max_sum:
            max_sum = arr[0]
            max_arr = arr[0]
        return max_sum, max_arr
        
    else:
        mid = int(len(arr)/2)
        arr1 = arr[:mid]
        arr2 = arr[mid:]
        
        sum1 = 0
        max_sum1 = 0
        val_arr1 = []
        max_arr1 = []
        for x in range(len(arr1)-1, -1, -1):
            sum1 += arr1[x]
            val_arr1.append(arr1[x])
            if max_sum1 < sum1:
                max_sum1 = sum1
                max_arr1 = val_arr1[::-1]
            
        sum2 = 0
        max_sum2 = 0
        val_arr2 = []
        max_arr2 = []
        for x in range(0, len(arr2)):
            sum2 += arr2[x]
            val_arr2.append(arr2[x])
            if max_sum2 < sum2:
                max_sum2 = sum2
                max_arr2 = val_arr2[:]
            
        sum3 = max_sum1 + max_sum2
        max_arr3 = max_arr1 + max_arr2
        
        if max_sum1 > max_sum:
            max_sum = max_sum1
            max_arr = max_arr1
            
        if max_sum2 > max_sum:
            max_sum = max_sum2
            max_arr = max_arr2
            
        if sum3 > max_sum:
            max_sum = sum3
            max_arr = max_arr3
                
        return max(d_and_c(arr[:mid], max_sum, max_arr), d_and_c(arr[mid:], max_sum, max_arr))
        
def time_dandc(array):
    start = dft()
    max_array = []
    max_sum = 0
    max_sum, max_array = d_and_c(array, max_sum, max_array)
    stop = dft()
    
    enum_time = stop - start
    
    return enum_time, max_sum, max_array
              
def enumerate_test(test_packet):
    max_vals = []
    max_arrs = []
    
    for line in test_packet:
        mx_val, mx_arr = linear_time(line)
        max_vals.append(mx_val)
        max_arrs.append(mx_arr)
        
    return max_vals, max_arrs
    
def linear_time(arr):
    
    max_sum = 0
    total = 0
    sum_array = []
    start = 0
    stop = 0
    
    for j in range(0, len(arr)):
        total += arr[j]
        if arr[j] > total:
            total = arr[j]
            start = j
            
        if total >= max_sum:
            max_sum = total
            stop = j
            
            
    sum_array = [arr[x] for x in range(start, stop+1)]

            
    return max_sum, sum_array

def time_linear(array):
    start = dft()
    max_sum, max_array = linear_time(array)
    stop = dft()
    
    enum_time = stop - start
    
    return enum_time, max_sum, max_array
    
from random import randint

def do_the_thing():
    
    number = input('How many random test cases do you want to generate? ')
    MIN_NUM = -100
    MAX_NUM = 100
    
    MIN_CASE = 15
    MAX_CASE = 30
    
    test_cases = []
    for x in xrange(number):
        
        case = []
        num_case = randint(MIN_CASE, MAX_CASE)
        for number in xrange(num_case):
            case.append(randint(MIN_NUM, MAX_NUM))
        test_cases.append(case)
        
    all_enum_times = []
    all_enum_vals = []
    all_enum_arrs = []
    
    all_better_times = []
    all_better_vals = []
    all_better_arrs = []
    
    all_dandc_times = []
    all_dandc_vals = []
    all_dandc_arrs = []
    
    all_line_times = []
    all_line_vals = []
    all_line_arrs = []
    
    for case in test_cases:
        
        enum_time, enum_vals, enum_arrs = time_enum(case)
        all_enum_times.append(enum_time)
        all_enum_vals.append(enum_vals)
        all_enum_arrs.append(enum_arrs)
        
        better_time, better_vals, better_arrs = time_better(case)
        all_better_times.append(better_time)
        all_better_vals.append(better_vals)
        all_better_arrs.append(better_arrs)
        
            
        dandc_time, dandc_vals, dandc_arrs = time_dandc(case)
        all_dandc_times.append(dandc_time)
        all_dandc_vals.append(dandc_vals)
        all_dandc_arrs.append(dandc_arrs)    
        
        line_time, line_vals, line_arrs = time_linear(case)
        all_line_times.append(line_time)
        all_line_vals.append(line_vals)
        all_line_arrs.append(line_arrs)
        
    f = open('Proj1_Solutions.txt', 'w')
    
    f.write('Enumerate Case:\n\n')
    
    
    for x, case in enumerate(all_enum_times):
        f.write(str(all_enum_times[x]))
        f.write('\n')
        f.write(str(all_enum_vals[x]))
        f.write('\n')
        f.write(str(all_enum_arrs[x]))
        f.write('\n\n')
        
    f.write('\n\n')
    
    f.write('Better Enumerate Case:\n\n')
    for x, case in enumerate(all_better_times):
        f.write(str(all_better_times[x]))
        f.write('\n')
        f.write(str(all_better_vals[x]))
        f.write('\n')
        f.write(str(all_better_arrs[x]))
        f.write('\n\n')
        
    f.write('\n\n')
    
    f.write('Divide and Conquer Case:\n\n')
    for x, case in enumerate(all_dandc_times):
        f.write(str(all_dandc_times[x]))
        f.write('\n')
        f.write(str(all_dandc_vals[x]))
        f.write('\n')
        f.write(str(all_dandc_arrs[x]))
        f.write('\n\n')
        
    f.write('\n\n')
    
    f.write('Linear Case:\n\n')
    for x, case in enumerate(all_line_times):
        f.write(str(all_line_times[x]))
        f.write('\n')
        f.write(str(all_line_vals[x]))
        f.write('\n')
        f.write(str(all_line_arrs[x]))
        f.write('\n\n')
        
    f.close()
    
    
        
