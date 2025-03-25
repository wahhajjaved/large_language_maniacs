
# Copyright (c) 2007-2008 PediaPress GmbH
# See README.txt for additional licensing information.

from mwlib.templ import magics


class Node(tuple):
    def __eq__(self, other):
        return type(self)==type(other) and tuple.__eq__(self, other)    
    def __ne__(self, other):
        return type(self)!=type(other) or tuple.__ne__(self, other)
    
    def __repr__(self):
        return "%s%s" % (self.__class__.__name__, tuple.__repr__(self))
    
    def show(self, out=None):
        show(self, out=out)
        
    def flatten(self, expander, variables, res):
        for x in self:
            if isinstance(x, basestring):
                res.append(x)
            else:
                flatten(x, expander, variables, res)
    
class IfNode(Node):
    def flatten(self, expander, variables, res):
        cond = []
        flatten(self[0], expander, variables, cond)
        cond = u"".join(cond).strip()

        res.append(maybe_newline)
        tmp = []
        if cond:
            if len(self)>1:
                flatten(self[1], expander, variables, tmp)
        else:
            if len(self)>2:
                flatten(self[2], expander, variables, tmp)
        res.append(u"".join(tmp).strip())
        res.append(dummy_mark)

def maybe_numeric(a):
    try:
        return int(a)
    except ValueError:
        pass
    
    try:
        return float(a)
    except ValueError:
        pass
    return None

        
class SwitchNode(Node):
    fast = None
    unresolved = None
    
    def _init(self):
        args = [equalsplit(x) for x in self[1]]
        
        unresolved = []
        fast = {}
        
        for key, value in args:
            if key is not None:
                key = optimize(list(key))
            value = optimize(list(value))
            if key is None:
                key = u'#default'
                
            if isinstance(key, basestring):
                key = key.strip()
                if key in fast:
                    continue
                
                fast[key] = (len(unresolved), value)
                num_key = maybe_numeric(key)
                if num_key is not None and num_key not in fast:
                    fast[num_key] = (len(unresolved), value)
            else:
                unresolved.append((key,value))

                
        self.unresolved = tuple(unresolved)
        self.fast = fast
        self.sentinel = (len(self.unresolved)+1, None)
        
    def flatten(self, expander, variables, res):
        if self.unresolved is None:
            self._init()

        val = []
        flatten(self[0], expander, variables, val)
        val = u"".join(val).strip()

        num_val = maybe_numeric(val)
        
        t1 = self.fast.get(val, self.sentinel)
        t2 = self.fast.get(num_val, self.sentinel)

        pos, retval = min(t1, t2)
        
        if pos is None:
            pos = len(self.unresolved)+1
        
        for k, v in self.unresolved[:pos]:
            tmp = []
            flatten(k, expander, variables, tmp)
            tmp = u"".join(k).strip()
            if tmp==k:
                retval = v
                break
            if num_val is not None and maybe_numeric(tmp)==num_val:
                retval = v
                break
            
        if retval is None:
            retval = self.fast.get("#default", (None, u''))[1]
            
        tmp = []
        flatten(retval, expander, variables, tmp)
        tmp = u"".join(tmp).strip()
        res.append(tmp)
            
class Variable(Node):
    def flatten(self, expander, variables, res):
        name = []
        flatten(self[0], expander, variables, name)
        name = u"".join(name).strip()
        if len(name)>256*1024:
            raise MemoryLimitError("template name too long: %s bytes" % (len(name),))

        v = variables.get(name, None)

        if v is None:
            if len(self)>1:
                flatten(self[1], expander, variables, res)
            else:
                # FIXME. breaks If ???
                res.append(u"{{{%s}}}" % (name,))
        else:
            res.append(v)
       
class Template(Node):
    def flatten(self, expander, variables, res):
        try:
            return self._flatten(expander, variables, res)
        except RuntimeError, err:
            # we expect a "RuntimeError: maximum recursion depth exceeded" here.
            # logging this error is rather hard...
            try:
                log.warn("error %s ignored" % (err,))
            except:
                pass
            
        
    def _flatten(self, expander, variables, res):
        
        name = []
        flatten(self[0], expander, variables, name)
        name = u"".join(name).strip()
        if len(name)>256*1024:
            raise MemoryLimitError("template name too long: %s bytes" % (len(name),))

        args = self[1]
        
        remainder = None
        if ":" in name:
            try_name, try_remainder = name.split(':', 1)
            if expander.resolver.has_magic(try_name):
                name=try_name
                remainder = try_remainder
                
            if name=='#if':
                remainder=remainder.strip()
                res.append(maybe_newline)
                tmp = []
                if remainder:
                    if len(args)>=1:
                        flatten(args[0], expander, variables, tmp)
                else:
                    if len(args)>=2:
                        flatten(args[1], expander, variables, tmp)
                res.append(u"".join(tmp).strip())
                res.append(dummy_mark)
                return
            elif name=='#ifeq':
                res.append(maybe_newline)
                tmp=[]
                if len(args)>=1:
                    flatten(args[0], expander, variables, tmp)
                other = u"".join(tmp).strip()
                remainder = remainder.strip()
                tmp = []
                if magics.maybe_numeric_compare(remainder, other):
                    if len(args)>=2:
                        flatten(args[1], expander, variables, tmp)
                        res.append(u"".join(tmp).strip())
                else:
                    if len(args)>=3:
                        flatten(args[2], expander, variables, tmp)
                        res.append(u"".join(tmp).strip())
                res.append(dummy_mark)
                return
            elif name=='#switch':
                res.append(maybe_newline)
                
                remainder = remainder.strip()
                default = None
                for i, c in enumerate(args):
                    k, v = equalsplit(c)
                    if k is not None:
                        tmp = []
                        flatten(k, expander, variables, tmp)
                        k=u"".join(tmp).strip()

                    if k=='#default':
                        default = v
                        
                        
                    if (k is None and i==len(args)-1) or (k is not None and magics.maybe_numeric_compare(k, remainder)):
                        tmp = []
                        flatten(v, expander, variables, tmp)
                        v = u"".join(tmp).strip()
                        
                        res.append(v)
                        res.append(dummy_mark)
                        return

                if default is not None:
                    tmp=[]
                    flatten(default, expander, variables, tmp)
                    tmp = u"".join(tmp).strip()
                    res.append(tmp)
                    
                        
                res.append(dummy_mark)
                return
        
        var = []
        if remainder is not None:
            var.append(remainder)
        
        for x in args:
            var.append(x)

        var = ArgumentList(args=var, expander=expander, variables=variables)
        
        rep = expander.resolver(name, var)

        if rep is not None:
            res.append(maybe_newline)
            res.append(rep)
            res.append(dummy_mark)
        else:            
            p = expander.getParsedTemplate(name)
            if p:
                if DEBUG:
                    msg = "EXPANDING %r %r  ===> " % (name, var)
                    oldidx = len(res)
                res.append(mark_start(repr(name)))
                res.append(maybe_newline)
                flatten(p, expander, var, res)
                res.append(mark_end(repr(name)))

                if DEBUG:
                    msg += repr("".join(res[oldidx:]))
                    print msg

def show(node, indent=0, out=None):
    import sys
    
    if out is None:
        out=sys.stdout

    out.write("%s%r\n" % ("  "*indent, node))
    if isinstance(node, (basestring, tuple)):
        return
    for x in node:
        show(x, indent+1, out)


from mwlib.templ.evaluate import maybe_newline, mark_start, mark_end, dummy_mark, flatten, MemoryLimitError, ArgumentList, equalsplit
from mwlib.templ import log, DEBUG
from mwlib.templ.parser import optimize
