# Find the minimum sorted rotated array
# The problem can be solved with number of ways:
# 1. Traverse the array anf find the minimum element
#    Complexity: O(n); we didn't took the advantage of array is sorted.
# 2. Sort the array is ascending array and return the first element.
#    Complexity: O(n log n); we sorted the already sorted input array
# 3. Modified binary search
#    3.1 left = 0 and right = length(array) -1
#    3.2 While array[left] > array[right] (Array is rotated)
#       3.2.1 Find the mid index
#       3.2.2 If array[mid] < array[right];
#            then the minimum lies in the
#               index from left to mid
#            else the minimum lies in the
#                index from mid to right
#   Complexity: O(log n)


def find_min_recursive(array, left, right):
    """ Find the minimum in rotated array in O(log n) time.
    >>> find_min_recursive([1,2,3,4,5,6], 0, 5)
    1
    >>> find_min_recursive([6, 5, 4, 3, 2, 1], 0, 5)
    1
    >>> find_min_recursive([6, 5, 1, 4, 3, 2], 0, 5)
    1
    """
    if array[left] <= array[right]:
        return array[left]
    mid = left + (right - left) // 2
    if array[mid] < array[right]:
        return find_min_recursive(array, left, mid)
    else:
        return find_min_recursive(array, mid + 1, right)

if __name__ == "__main__":
    import doctest
    doctest.testmod(verbose=True)
