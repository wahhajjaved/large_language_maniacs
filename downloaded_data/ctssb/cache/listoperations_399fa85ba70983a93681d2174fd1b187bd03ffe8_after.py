# Part 1: Fundamental operations on lists
# ---------------------------------------
#
# The fundamental operations on lists in Python are those that are part of the
# language syntax and/or cannot be implemented in terms of other list operations:
#
#     * List literals ([], ['hello'], [3, 1, 4, 1, 5, 9], etc.)
#     * List indexing (some_list[index])
#     * List indexing assignment (some_list[index] = value)
#     * List slicing (some_list[start:end])
#     * List slicing assignment (some_list[start:end] = another_list)
#     * List index deletion (del some_list[index])
#     * List slicing deletion (del some_list[start:end])
#
# In this section you will implement functions that each use just one of the above
# operations. The docstring of each function describes what it should do. Consult
# test_list_operations.py for concrete examples of the expected function behavior.
#
# DO NOT USE ANY OF THE BUILT IN LIST METHODS, OR len(l)

FURTHER_STUDY = False


def head(input_list):
    """
    Return the first element of the input list.

    For example:

    >>> head(['Jan', 'Feb', 'Mar'])
    'Jan'

    """
    
    return input_list[0]


def tail(input_list):
    """
    Return all elements of the input list except the first.

    For example:

    >>> tail(['Jan', 'Feb', 'Mar'])
    ['Feb', 'Mar']

    """

    return input_list[1:]


def last(input_list):
    """
    Return the last element of the input list.

    For example:

    >>> last(['Jan', 'Feb', 'Mar'])
    'Mar'

    """

    return input_list.pop()


def init(input_list):
    """
    Return all elements of the input list except the last.

    For example:

    >>> init(['Jan', 'Feb', 'Mar'])
    ['Jan', 'Feb']

    """

    return input_list[:-1]


##############################################################################
# Do yourself a favor and get a short code review here.
# You can also get reviewed by a neighbor who has been reviewed.


def first_three(input_list):
    """
    Return the first three elements of the input list.

    For example:

    >>> first_three(['Jan', 'Feb', 'Mar', 'Apr', 'May'])
    ['Jan', 'Feb', 'Mar']

    """

    return []


def last_five(input_list):
    """
    Return the last five elements of the input list.

    For example:

    >>> last_five([0, 3, 6, 9, 12, 15, 18, 21, 24, 27])
    [15, 18, 21, 24, 27]

    """

    return []


def middle(input_list):
    """
    Return all elements of the input list except the first two and the last two.

    For example:

    >>> middle([0, 3, 6, 9, 12, 15, 18, 21, 24, 27])
    [6, 9, 12, 15, 18, 21]

    """

    return []


def inner_four(input_list):
    """
    Return the third, fourth, fifth, and sixth elements of the input list.

    For example:

    >>> inner_four([0, 3, 6, 9, 12, 15, 18, 21, 24, 27])
    [6, 9, 12, 15]

    """

    return []


def inner_four_end(input_list):
    """
    Return the sixth, fifth, fourth, and third elements from the end of the
    list, in that order.

    For example:

    >>> inner_four_end([0, 3, 6, 9, 12, 15, 18, 21, 24, 27])
    [12, 15, 18, 21]

    """

    return []


def replace_head(input_list):
    """
    Replace the head of the input list with the value 42 and
    return nothing.

    For example:

    >>> multiples = [0, 3, 6, 9, 12, 15, 18, 21, 24, 27]
    >>> replace_head(multiples)
    >>> multiples == [42, 3, 6, 9, 12, 15, 18, 21, 24, 27]
    True

    """

    pass


def replace_third_and_last(input_list):
    """
    Replace the third and last elements of the input list with the value 37
    and return nothing.

    For example:

    >>> multiples = [0, 3, 6, 9, 12, 15, 18, 21, 24, 27]
    >>> replace_third_and_last(multiples)
    >>> multiples == [0, 3, 37, 9, 12, 15, 18, 21, 24, 37]
    True

    """

    pass


def replace_middle(input_list):
    """
    Replace all elements of the input list with the the values 42 and 37, in
    that order, except for the first two and last two elements. Return nothing.

    For example:

    >>> multiples = [0, 3, 6, 9, 12, 15, 18, 21, 24, 27]
    >>> replace_middle(multiples)
    >>> multiples == [0, 3, 42, 37, 24, 27]
    True

    """

    pass


def delete_third_and_seventh(input_list):
    """
    Remove the third and seventh elements of the input list and return
    nothing.

    For example:

    >>> notes = ['Do', 'Re', 'Mi', 'Fa', 'So', 'La', 'Ti', 'Do']
    >>> delete_third_and_seventh(notes)
    >>> notes == ['Do', 'Re', 'Fa', 'So', 'La', 'Do']
    True

    """

    pass


def delete_middle(input_list):
    """
    Remove all elements from the input list except for the first two and the
    last two. Return nothing.

    For example:

    >>> notes = ['Do', 'Re', 'Mi', 'Fa', 'So', 'La', 'Ti', 'Do']
    >>> delete_middle(notes)
    >>> notes == ['Do', 'Re', 'Ti', 'Do']
    True

    """

    pass


##############################################################################
# END OF MAIN EXERCISE
#
# Please ask for a code review from an instructor/TA before proceeding.


# Further Study / Extra Credit
# ----------------------------
#
# In this section you will implement your own versions of the standard list methods.
# You should use only the primitive operations from Part 1 and 2 in your implementations.
# For loops are also allowed, such as the following:
#     for element in some_list:
#         # Do something with element
#
# Each custom method imitates a built-in list method, as described by the docstring
# for each function. Play with the built-in methods in the Python REPL to get a feel
# for how they work before trying to write your custom version. You may also look at
# the test_list_operations.py file for concrete examples of expected behavior.


def custom_len(input_list):
    """
    like len(input_list), should return the number of items in the list

    For example:

    >>> custom_len(['Do', 'Re', 'Mi', 'Fa', 'So', 'La', 'Ti', 'Do'])
    8

    """

    return 0


# For the next four exercises, you'll need to be clever and think about ways
# to use "list slice assignment" to solve these problems.
#
# NOTE: these are especially contrived--for example, you wouldn't really want
# to typically append things to a list like this (you'd want to to use the
# list.append() method), but we want you to practice list slicing assignment
# in different ways so it sticks in your brain.


def custom_append(input_list, value):
    """
    like input_list.append(value), should add the value to the end of the list
    and return nothing.

    For example:

    >>> notes = ['Do', 'Re', 'Mi', 'Fa', 'So', 'La', 'Ti', 'Do']
    >>> custom_append(notes, 'Re')
    >>> notes == ['Do', 'Re', 'Mi', 'Fa', 'So', 'La', 'Ti', 'Do', 'Re']
    True

    """

    pass


def custom_extend(input_list, second_list):
    """
    like input_list.extend(second_list), should append every item in the second
    list to the end of the first list and return nothing

    For example:

    >>> months = ['Jan', 'Feb', 'Mar']
    >>> custom_extend(months, ['Apr', 'May'])
    >>> months == ['Jan', 'Feb', 'Mar', 'Apr', 'May']
    True

    """

    pass


def custom_insert(input_list, index, value):
    """
    like input_list.insert(index, value), should insert (not replace) the value
    at the specified index of the input list and return nothing

    For example:

    >>> months = ['Jan', 'Mar']
    >>> custom_insert(months, 1, 'Feb')
    >>> months == ['Jan', 'Feb', 'Mar']
    True

    """

    pass


def custom_remove(input_list, value):
    """
    like input_list.remove(value), should remove the first item of the
    value specified and return nothing

    For example:

    >>> notes = ['Do', 'Re', 'Mi', 'Fa', 'So', 'La', 'Ti', 'Do']
    >>> custom_remove(notes, 'Do')
    >>> notes == ['Re', 'Mi', 'Fa', 'So', 'La', 'Ti', 'Do']
    True

    """

    pass


def custom_pop(input_list):
    """
    like input_list.pop(), should remove the last item in the list and
    return it

    For example:

    >>> custom_pop(['Jan', 'Feb', 'March'])
    'March'

    """

    return None


def custom_index(input_list, value):
    """
    like input_list.index(value), should return the index of the first item
    which matches the specified value

    For example:

    >>> custom_index(['Do', 'Re', 'Mi', 'Fa', 'So', 'La', 'Ti', 'Do'], 'Do')
    0

    """

    return 0


def custom_count(input_list, value):
    """
    like input_list.count(value), should return the number of times the specified
    value appears in the list.

    For example:

    >>> custom_count(['Do', 'Re', 'Mi', 'Fa', 'So', 'La', 'Ti', 'Do'], 'Do')
    2

    """

    return 0


def custom_reverse(input_list):
    """
    like input_list.reverse(), should reverse the elements of the original list
    and return nothing (we call this reversing "in place")

    For example:

    >>> multiples = [0, 3, 6, 9, 12, 15, 18, 21, 24, 27]
    >>> custom_reverse(multiples)
    >>> multiples == [27, 24, 21, 18, 15, 12, 9, 6, 3, 0]
    True

    """

    pass


def custom_contains(input_list, value):
    """
    like (value in input_list), should return True if the list contains the
    specified value and False if it does not. Remember, do not use the `if X in Y`
    statement -- find another way to solve it!

    For example:

    >>> custom_contains([0, 3, 6, 9, 12, 15, 18, 21, 24], 23)
    False

    >>> custom_contains([0, 3, 6, 9, 12, 15, 18, 21, 24], 24)
    True

    """

    return None


def custom_equality(some_list, another_list):
    """
    like (some_list == another_list), should return True if both lists contain
    the same values in the same indexes

    For example:

    >>> custom_equality(['Jan', 'Feb', 'Mar'], ['Jan', 'Feb', 'Mar'])
    True

    >>> custom_equality(['Jan', 'Feb', 'Mar'], ['Jan', 'Mar', 'Feb'])
    False

    """

    return None


##############################################################################
# END OF EXTRA CREDIT
#
# Please ask for a code review. Also, give your partner a high-five!

##############################################################################
# This is the part were we actually run the doctests.

if __name__ == "__main__":
    import doctest
    for k, v in globals().items():
        if k[0].isalpha():
            if k.startswith('custom_') and not FURTHER_STUDY:
                continue
            result = doctest.run_docstring_examples(v, globals(), name=k)

    print "END OF TEST OUTPUT"
