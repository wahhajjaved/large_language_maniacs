'''PandaCore.Tools.root_interface

Some tools defining interfaces between ROOT and other data structures.
Essentially wrappers around root_numpy
''' 

import numpy as np 
import root_numpy as rnp 
import ROOT as root
from Misc import PInfo,  PWarning,  PError

_hcounter = 0 

# MISC -----------------------------------------------------------------
def rename_dtypes(xarr, repl, old_names = None):
    if old_names:
        for n in xarr.dtype.names:
            old_names.append(n)
    new_names = tuple((repl[x] for x in xarr.dtype.names))
    xarr.dtype.names = new_names


# FILE INPUT ------------------------------------------------------------
def read_branches(filenames, tree, branches, cut, treename = "events", xkwargs = {}):
    if not(filenames or treename) or (filenames and tree):
        PError("root_interface.read_branches", "Exactly one of filenames and tree should be specified!")
        return None
    branches_ = list(set(branches)) # remove duplicates
    if filenames:
        return rnp.root2array(filenames = filenames, 
                              treename = treename, 
                              branches = branches_, 
                              selection = cut, 
                              **xkwargs)
    else:
        return rnp.tree2array(tree = tree, 
                              branches = branches_, 
                              selection = cut, 
                              **xkwargs)


def read_files(filenames, branches, cut = None, treename = 'events', xkwargs = {}):
    return read_branches(filenames = filenames, 
                         tree = None, 
                         branches = branches, 
                         cut = cut, 
                         treename = treename, 
                         xkwargs = xkwargs)

def read_tree(tree, branches, cut = None, xkwargs = {}):
    return read_branches(filenames = None, 
                         tree = tree,  
                         branches = branches,  
                         cut = cut, 
                         xkwargs = xkwargs)


# FILE OUTPUT --------------------------------------------------------------
def array_as_tree(xarr, treename = None, fcontext = None, xkwargs = {}):
    # combines array2tree and array2root but leaves TFile manipulation for the user
    context = None
    if fcontext:
        context = root.TDirectory.TContext(fcontext)
    tree = rnp.array2tree(xarr, treename, **xkwargs)
    if fcontext:
        fcontext.WriteTObject(tree, treename)
    if context:
        del context 
    return tree


# HISTOGRAM MANIPULATION ---------------------------------------------------
def draw_hist(hist, xarr, fields, weight = None):
    warr = xarr[weight] if weight else None
    if len(warr.shape)>1:
        warr = warr[:,0]
    if len(fields) == 1:
        return rnp.fill_hist(hist = hist, array = xarr[fields[0]], weights = warr)
    else:
        varr = np.array([xarr[f] for f in fields])
        varr = varr.transpose()
        return rnp.fill_hist(hist = hist, array = varr, weights = warr)


# Put everything into a class ---------------------------------------------
class Selector(object):
    def __init__(self):
        self.data = None 
        self._nicknames = None
    def read_files(self, *args, **kwargs):
        self.data = read_branches(*args, **kwargs)
    def read_tree(self, *args, **kwargs):
        self.data = read_tree(*args, **kwargs)
    def rename(self, a, b = None):
        if b :
            self._nicknames[a] = b 
        else:
            self._nicknames.update(a)
    def __getitem__(self, k):
        if type(k)==list:
            keys = [self._nicknames[kk] if kk in self._nicknames else kk for kk in k]
        elif type(k)==str and k in self._nicknames:
            keys = self._nicknames[k]
        else:
            keys = k 
        return self.data[keys]
    def clone(self, copy = False):
        other = Selector()
        other.rename(self._nicknames)
        if copy:
            other.data = np.copy(self.data)
        else:
            other.data = self.data 
        return other 
    def save(self, fpath, treename, opts = 'RECREATE'):
        f = root.TFile(fpath, opts)
        array_as_tree(self.data, treename, f)
        f.Close()
    def draw(self, fields, weight = None, hbase = None, vbins = None, fbins = None):
        global _hcounter
        if hbase:
            h = hbase.Clone()
        elif vbins:
            h = root.TH1D('hSelector%i'%_hcounter, '', len(vbins), vbins)
            _hcounter += 1 
        else:
            h = root.TH1D('hSelector%i'%_hcounter, '', *fbins)
            _hcounter += 1 
        if type(fields)==str:
            fields = [fields]
        draw_hist(h, self.data, fields, weight)
        return h  
