"""This module contains the main wrapper class."""


class BaseWrapper:
    """Define base template for function wrapper classes. """

    def __init__(self, func):
        self.func = func
        self.__doc__ = func.__doc__

    def __call__(self, *args, **kwargs):
        raise NotImplementedError


class NumpyWrapper(BaseWrapper):
    """Function wrapper for numpy's random functions. Allows easy usage
    avoiding the creation anonymous lambda functions. In addition, the `size`
    attribute is adjusted automatically. 
    
    For instance, instead of writing 
    'lambda x: np.random.randint(low=1, high=10, size=x.shape[0])' 
    
    you may simply write 
    'ts.random.randint(low=1, high=10)'.
    
    """


    def __init__(self, func, size="arg"):
        super(NumpyWrapper, self).__init__(func)
        self.size = size

    def __call__(self, *args, **kwargs):

        if self.size == "arg":
            def wrapped(x):
                return self.func(*args, x.shape[0], **kwargs)

        elif self.size == "kwarg":
            def wrapped(x):
                return self.func(*args, size=x.shape[0], **kwargs)

        else:
            raise ValueError("Size argument must be 'arg' or 'kwarg'.")

        wrapped.__doc__ = self.func.__doc__
        return wrapped
