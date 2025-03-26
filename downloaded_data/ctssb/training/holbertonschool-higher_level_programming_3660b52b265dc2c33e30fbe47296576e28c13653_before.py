#!/usr/bin/python3


# function that conver the roman number to an integer
def roman_to_int(roman_string):
    num_roman = {
        'I': 1,
        'V': 5,
        'X': 10,
        'L': 50,
        'C': 100,
        'D': 500,
        'M': 1000,
    }
    if roman_string is None:
        return 0
    for letter in roman_string:
        if letter in num_roman:
            continue
        else:
            return 0
    size = len(roman_string)
    i = 0
    suma = 0
    while i < size:
        num1 = num_roman[roman_string[i]]

        if i + 1 < size:
            num2 = num_roman[roman_string[i + 1]]

            if num1 >= num2:
                suma += num1
                i += 1
            else:
                suma += num2 - num1
                i += 2
        else:
            suma += num1
            i += 1
    return suma
