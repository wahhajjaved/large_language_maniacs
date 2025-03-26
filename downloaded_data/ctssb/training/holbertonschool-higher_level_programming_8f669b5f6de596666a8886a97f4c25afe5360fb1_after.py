#!/usr/bin/python3


# function that returns a key whit the biggest integer value
def best_score(a_dictionary):
    if a_dictionary is None or a_dictionary == {}:
        return None
    num = 0
    for key, value in a_dictionary.items():
        if value >= num:
            num = value
    return list(a_dictionary.keys())[list(a_dictionary.values()).index(num)]
