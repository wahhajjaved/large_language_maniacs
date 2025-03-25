def tuple_raw_input():
    while True:
        my_input = raw_input()
        my_list = my_input.split(',')
        if my_list[0].isdigit() and my_list[1].isdigit():
            return ( int(my_list[0]) , int(my_list[1]) )
        print "Please enter (x),(y)"

