'''
Created on Feb 10, 2012

@author: mzwier
'''

from __future__ import division; __metaclass__ = type

import numpy

class BasisState:
    '''Describes an basis (micro)state. These basis states are used to generate
    initial states for new trajectories, either at the beginning of the simulation
    (i.e. at w_init) or due to recycling.

    :ivar state_id:     Integer identifier of this state, usually set by the
                        data manager.
    :ivar label:        A descriptive label for this microstate (may be empty)
    :ivar probability:  Probability of this state to be selected when creating a
                        new trajectory.
    :ivar pcoord:       The representative progress coordinate of this state.
    
    :ivar auxref:       A user-provided (string) reference for locating data associated
                        with this state (usually a filesystem path).
    '''
    def __init__(self, label, probability, pcoord=None, auxref=None, state_id=None):
        self.label = label
        self.probability = probability         
        self.pcoord = numpy.atleast_1d(pcoord)
        self.auxref = auxref 
        self.state_id = state_id
        
    def __repr__(self): 
        return ('{} state_id={self.state_id!r} label={self.label!r} prob={self.probability!r} pcoord={self.pcoord!r}>'
                .format(object.__repr__(self)[:-1], self=self))
        
    @classmethod
    def states_to_file(cls, states, fileobj):
        '''Write a file defining basis states, which may then be read by `states_from_file()`.'''
        
        if isinstance(fileobj, basestring):
            fileobj = open(fileobj, 'wt')
        
        max_label_len = max(8,max(len(state.label or '') for state in states))
        max_auxref_len = max(8,max(len(state.auxref or '') for state in states))
        fmt = ('{state.label:<{max_label_len}s}    {state.probability:12.7g}    {state.auxref:<{max_auxref_len}s}'
               '    # state_id={state_id_str:s}    pcoord={pcoord_str}\n')
        fileobj.write('# {:{max_label_len}s}    {:>12s}    {:{max_auxref_len}s}\n'
                      .format('Label', 'Probability', 'Auxref', max_label_len=max_label_len-2, max_auxref_len=max_auxref_len))
        for state in states:
            state_id_str = str(state.state_id) if state.state_id is not None else 'None'
            pcoord_str = str(list(state.pcoord))
            fileobj.write(fmt.format(state=state, pcoord_str=pcoord_str, state_id_str=state_id_str,
                                     max_label_len=max_label_len, max_auxref_len=max_auxref_len))
        
    
    @classmethod
    def states_from_file(cls, filename):
        '''Read a file defining basis states.  Each line defines a state, and contains a label, the probability, 
        and optionally a data reference, separated by whitespace, as in::
        
            unbound    1.0
        
        or::
            
            unbound_0    0.6        state0.pdb
            unbound_1    0.4        state1.pdb
        
        '''
        states = []
        lineno = 0
        for line in file(filename, 'rt'):
            lineno += 1
            
            # remove comment portion
            line = line.partition('#')[0].strip()
            if not line:
                continue
            
            fields = line.split()
            label = fields[0]
            try:
                probability = float(fields[1])
            except ValueError:
                raise ValueError('invalid probability ({!r}) {} line {:d}'.format(fields[1], filename, lineno))
            
            try:
                data_ref = fields[2].strip()
            except IndexError:
                data_ref = None
                
            states.append(cls(state_id=None,probability=probability,label=label,data_ref=data_ref))
        return states
    
class InitialState:
    '''Describes an initial state for a new trajectory. These are generally constructed by
    appropriate modification of a basis state. 

    :ivar state_id:         Integer identifier of this state, usually set by the
                            data manager.
    :ivar basis_state_id:   Identifier of the basis state from which this state was
                            generated.
    :ivar basis_state:      The `BasisState` from which this state was generated.
    :ivar iter_created:     Iteration in which this state was generated (0 for
                            simulation initialization).
    :ivar iter_used:        Iteration in which this state was used to initiate a
                            trajectory (None for unused).
    :ivar istate_type:      Integer describing the type of this initial state
                            (ISTATE_TYPE_BASIS for direct use of a basis state, 
                            ISTATE_TYPE_GENERATED for a state generated from a basis state).
    :ivar istate_status:    Integer describing whether this initial state has been properly
                            prepared.
    :ivar pcoord:           The representative progress coordinate of this state.
    '''
    
    ISTATE_TYPE_UNSET = 0
    ISTATE_TYPE_BASIS = 1
    ISTATE_TYPE_GENERATED = 2
    
    ISTATE_UNUSED = 0
    
    ISTATE_STATUS_PENDING  = 0
    ISTATE_STATUS_PREPARED = 1
    ISTATE_STATUS_FAILED = 2
    
    def __init__(self, state_id, basis_state_id, iter_created, iter_used=None, 
                 istate_type=None, istate_status=None,
                 pcoord=None, 
                 basis_state=None):
        self.state_id = state_id
        self.basis_state_id = basis_state_id
        self.basis_state=basis_state
        self.istate_type = istate_type
        self.istate_status = istate_status
        self.iter_created = iter_created
        self.iter_used = iter_used         
        self.pcoord = pcoord
        
    def __repr__(self): 
        return ('{} state_id={self.state_id!r} istate_type={self.istate_type!r} basis_state_id={self.basis_state_id!r} iter_created={self.iter_created!r} pcoord={self.pcoord!r}>'
                .format(object.__repr__(self)[:-1], self=self))

class TargetState:
    '''Describes a target state.
    
    :ivar state_id:     Integer identifier of this state, usually set by the
                        data manager.
    :ivar label:        A descriptive label for this microstate (may be empty)
    :ivar pcoord: The representative progress coordinate of this state.
    
    '''
    def __init__(self, label, pcoord, state_id=None):
        self.label = label
        self.pcoord = numpy.atleast_1d(pcoord)
        self.state_id = state_id
        
    def __repr__(self): 
        return ('{} state_id={self.state_id!r} label={self.label!r} pcoord={self.pcoord!r}>'
                .format(object.__repr__(self)[:-1], self=self))

    @classmethod
    def states_to_file(cls, states, fileobj):
        '''Write a file defining basis states, which may then be read by `states_from_file()`.'''
        
        if isinstance(fileobj, basestring):
            fileobj = open(fileobj, 'wt')
        
        max_label_len = max(8,max(len(state.label or '') for state in states))
        
        fileobj.write('# {:{max_label_len}s}    {:s}\n'
                      .format('Label', 'Pcoord', max_label_len=max_label_len-2))        
        for state in states:
            pcoord_str = '    '.join(str(field) for field in state.pcoord)
            fileobj.write('{:{max_label_len}s}    {:s}\n'.format(state.label, pcoord_str, max_label_len=max_label_len))

    @classmethod
    def states_from_file(cls, statefile, dtype):
        '''Read a file defining target states.  Each line defines a state, and contains a label followed
        by a representative progress coordinate value, separated by whitespace, as in::
        
            bound     0.02
        
        for a single target and one-dimensional progress coordinates or::
            
            bound    2.7    0.0
            drift    100    50.0
        
        for two targets and a two-dimensional progress coordinate.
        '''
        
        labels = []
        pcoord_values = []
        for line in statefile:
            fields = line.split()
            labels.append(fields[0])
            pcoord_values.append(numpy.array(map(dtype, fields[1:]),dtype=dtype))
            print(labels[-1], pcoord_values[-1])
                                
        return [cls(label=label, pcoord=pcoord) for label,pcoord in zip(labels,pcoord_values)]

from wemd.segment import Segment

def pare_basis_initial_states(basis_states, initial_states, segments=None):
    '''Given iterables of basis and initial states (and optionally segments that use them),
    return minimal sets (as in __builtins__.set) of states needed to describe the history of the given 
    segments an initial states.'''
    
    bstatemap = {state.state_id: state for state in basis_states}
    istatemap = {state.state_id: state for state in initial_states}
    
    if segments is not None:
        segments = list(segments)
        return_istates = set(istatemap[segment.initial_state_id] for segment in segments
                             if segment.initpoint_type == Segment.SEG_INITPOINT_NEWTRAJ)
    else:
        return_istates = set(initial_states)
    
    return_bstates = set(bstatemap[istate.basis_state_id] for istate in return_istates)
        
    return return_bstates, return_istates
