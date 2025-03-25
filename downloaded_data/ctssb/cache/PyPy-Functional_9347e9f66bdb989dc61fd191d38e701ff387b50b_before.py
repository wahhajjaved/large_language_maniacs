"""
Arguments objects.
"""

from pypy.interpreter.error import OperationError


class Arguments:
    """
    Collects the arguments of a function call.
    
    Instances should be considered immutable.
    """

    ###  Construction  ###

    blind_arguments = 0

    def __init__(self, space, args_w=[], kwds_w={},
                 w_stararg=None, w_starstararg=None):
        self.space = space
        self.arguments_w = list(args_w)
        self.kwds_w = kwds_w.copy()
        self.w_stararg = w_stararg
        if w_starstararg is not None:
            # unlike the * argument we unpack the ** argument immediately.
            # maybe we could allow general mappings?
            if not space.is_true(space.isinstance(w_starstararg, space.w_dict)):
                raise OperationError(space.w_TypeError,
                                     space.wrap("the keywords must be "
                                                "a dictionary"))
            for w_key in space.unpackiterable(w_starstararg):
                key = space.unwrap(w_key)
                if not isinstance(key, str):
                    raise OperationError(space.w_TypeError,
                                         space.wrap("keywords must be strings"))
                if key in self.kwds_w:
                    raise OperationError(self.space.w_TypeError,
                                         self.space.wrap("got multiple values "
                                                         "for keyword argument "
                                                         "'%s'" % key))
                self.kwds_w[key] = space.getitem(w_starstararg, w_key)

    def frompacked(space, w_args=None, w_kwds=None):
        """Convenience static method to build an Arguments
           from a wrapped sequence and a wrapped dictionary."""
        return Arguments(space, w_stararg=w_args, w_starstararg=w_kwds)
    frompacked = staticmethod(frompacked)

    def __repr__(self):
        if self.w_stararg is None:
            if not self.kwds_w:
                return 'Arguments(%s)' % (self.arguments_w,)
            else:
                return 'Arguments(%s, %s)' % (self.arguments_w, self.kwds_w)
        else:
            return 'Arguments(%s, %s, %s)' % (self.arguments_w,
                                              self.kwds_w,
                                              self.w_stararg)

    ###  Manipulation  ###

    def unpack(self):
        "Return a ([w1,w2...], {'kw':w3...}) pair."
        if self.w_stararg is not None:
            self.arguments_w += self.space.unpackiterable(self.w_stararg)
            self.w_stararg = None
        return self.arguments_w, self.kwds_w

    def prepend(self, w_firstarg):
        "Return a new Arguments with a new argument inserted first."
        args =  Arguments(self.space, [w_firstarg] + self.arguments_w,
                          self.kwds_w, self.w_stararg)
        args.blind_arguments = self.blind_arguments + 1
        return args

    def fixedunpack(self, argcount):
        """The simplest argument parsing: get the 'argcount' arguments,
        or raise a real ValueError if the length is wrong."""
        if self.kwds_w:
            raise ValueError, "no keyword arguments expected"
        if len(self.arguments_w) > argcount:
            raise ValueError, "too many arguments (%d expected)" % argcount
        if self.w_stararg is not None:
            self.arguments_w += self.space.unpackiterable(self.w_stararg,
                                             argcount - len(self.arguments_w))
            self.w_stararg = None
        elif len(self.arguments_w) < argcount:
            raise ValueError, "not enough arguments (%d expected)" % argcount
        return self.arguments_w

    def firstarg(self):
        "Return the first argument for inspection."
        if self.arguments_w:
            return self.arguments_w[0]
        if self.w_stararg is None:
            return None
        w_iter = self.space.iter(self.w_stararg)
        try:
            return self.space.next(w_iter)
        except OperationError, e:
            if not e.match(self.space, self.space.w_StopIteration):
                raise
            return None

    ###  Parsing for function calls  ###

    def parse(self, fnname, signature, defaults_w=[]):
        """Parse args and kwargs to initialize a frame
        according to the signature of code object.
        """
        space = self.space
        argnames, varargname, kwargname = signature
        #
        #   args_w = list of the normal actual parameters, wrapped
        #   kwds_w = real dictionary {'keyword': wrapped parameter}
        #   argnames = list of formal parameter names
        #   scope_w = resulting list of wrapped values
        #
        # We try to give error messages following CPython's, which are
        # very informative.
        #
        co_argcount = len(argnames) # expected formal arguments, without */**
        if self.w_stararg is not None:
            # There is a case where we don't have to unpack() a w_stararg:
            # if it matches exactly a *arg in the signature.
            if (len(self.arguments_w) == co_argcount and varargname is not None
                and space.is_true(space.is_(space.type(self.w_stararg),
                                            space.w_tuple))):
                pass
            else:
                self.unpack()   # sets self.w_stararg to None
        args_w = self.arguments_w
        kwds_w = self.kwds_w

        # put as many positional input arguments into place as available
        scope_w = args_w[:co_argcount]
        input_argcount = len(scope_w)

        # check that no keyword argument conflicts with these
        # note that for this purpose we ignore the first blind_arguments,
        # which were put into place by prepend().  This way, keywords do
        # not conflict with the hidden extra argument bound by methods.
        if kwds_w:
            for name in argnames[self.blind_arguments:input_argcount]:
                if name in kwds_w:
                    self.raise_argerr_multiple_values(fnname, name)

        remainingkwds_w = kwds_w.copy()
        if input_argcount < co_argcount:
            # not enough args, fill in kwargs or defaults if exists
            def_first = co_argcount - len(defaults_w)
            for i in range(input_argcount, co_argcount):
                name = argnames[i]
                if name in remainingkwds_w:
                    scope_w.append(remainingkwds_w[name])
                    del remainingkwds_w[name]
                elif i >= def_first:
                    scope_w.append(defaults_w[i-def_first])
                else:
                    self.raise_argerr(fnname, signature, defaults_w, False)
                    
        # collect extra positional arguments into the *vararg
        if varargname is not None:
            if self.w_stararg is None:   # common case
                scope_w.append(space.newtuple(args_w[co_argcount:]))
            else:      # shortcut for the non-unpack() case above
                scope_w.append(self.w_stararg)
        elif len(args_w) > co_argcount:
            self.raise_argerr(fnname, signature, defaults_w, True)

        # collect extra keyword arguments into the **kwarg
        if kwargname is not None:
            w_kwds = space.newdict([(space.wrap(key), w_value)
                                    for key, w_value in remainingkwds_w.items()])
            scope_w.append(w_kwds)
        elif remainingkwds_w:
            self.raise_argerr_unknown_kwds(fnname, remainingkwds_w)
        return scope_w

    # helper functions to build error message for the above

    def raise_argerr(self, fnname, signature, defaults_w, too_many):
        argnames, varargname, kwargname = signature
        args_w, kwds_w = self.unpack()
        nargs = len(args_w)
        n = len(argnames)
        if n == 0:
            if kwargname is not None:
                msg2 = "non-keyword "
            else:
                msg2 = ""
                nargs += len(kwds_w)
            msg = "%s() takes no %sargument (%d given)" % (
                fnname, 
                msg2,
                nargs)
        else:
            defcount = len(defaults_w)
            if defcount == 0:
                msg1 = "exactly"
            elif too_many:
                msg1 = "at most"
            else:
                msg1 = "at least"
                n -= defcount
            if kwargname is not None:
                msg2 = "non-keyword "
            else:
                msg2 = ""
            if n == 1:
                plural = ""
            else:
                plural = "s"
            msg = "%s() takes %s %d %sargument%s (%d given)" % (
                fnname,
                msg1,
                n,
                msg2,
                plural,
                nargs)
        raise OperationError(self.space.w_TypeError, self.space.wrap(msg))

    def raise_argerr_multiple_values(self, fnname, argname):
        msg = "%s() got multiple values for keyword argument '%s'" % (
            fnname,
            argname)
        raise OperationError(self.space.w_TypeError, self.space.wrap(msg))

    def raise_argerr_unknown_kwds(self, fnname, kwds_w):
        if len(kwds_w) == 1:
            msg = "%s() got an unexpected keyword argument '%s'" % (
                fnname,
                kwds_w.keys()[0])
        else:
            msg = "%s() got %d unexpected keyword arguments" % (
                fnname,
                len(kwds_w))
        raise OperationError(self.space.w_TypeError, self.space.wrap(msg))

    ### Argument <-> list of w_objects together with "shape" information

    def flatten(self):
        shape_cnt  = len(self.arguments_w)        # Number of positional args
        shape_keys = self.kwds_w.keys()           # List of keywords (strings)
        shape_star = self.w_stararg is not None   # Flag: presence of *arg
        data_w = self.arguments_w + [self.kwds_w[key] for key in shape_keys]
        if shape_star:
            data_w.append(self.w_stararg)
        return (shape_cnt, tuple(shape_keys), shape_star), data_w

    def fromshape(space, (shape_cnt, shape_keys, shape_star), data_w):
        args_w = data_w[:shape_cnt]
        kwds_w = {}
        for i in range(len(shape_keys)):
            kwds_w[shape_keys[i]] = data_w[shape_cnt+i]
        if shape_star:
            w_star = data_w[-1]
        else:
            w_star = None
        return Arguments(space, args_w, kwds_w, w_star)
    fromshape = staticmethod(fromshape)
