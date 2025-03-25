import pytest
import hrm


def test_for_instantaneous():
    """ Unit test for checking instantaneous functionality
        
        :param None
        :rtype: Assertions
    """
    #Test for evaluating instantaneous heart rate
    assert hrm.main('full_test.csv', inst = True) == 80

    # Test for out of bounds error
    with pytest.raises(ValueError):
        hrm.main('full_test.csv', inst = True, 250000)  
