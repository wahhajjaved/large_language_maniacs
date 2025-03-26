# -*- coding: UTF-8 -*-

from automata import Automata

# TODO:
# - automata -> min automata

#TODO: beautify code
def remove_inaccesible_states(m):
    """ remove all inaccesible states from automata m
    """

    states = m.states
    n = range(len(states))
    T = [[0 for j in n] for i in n]

    # Relationship Matrix
    for i in n:
        for j in n:
            qi = states[i]
            qj = states[j]
            iRj = 0

            for a in m.alphabet:
                if qj in m.get_next_states(qi, a):
                    iRj = 1
            T[i][j] = iRj


    # Calculate Warshal on the relation matrix
    for k in n:
        for i in n:
            for j in n:
                T[i][j] = T[i][j] or ( T[i][k] and T[k][j] )


    # Get reachable states
    initial_state_index = states.index(m.initial)
    new_states = []
    # this row shows which states are reachable from the initial state (def of accesibility)
    reachable_states = T[initial_state_index]
    for j in range(len(reachable_states)):
        is_qj_reachable = reachable_states[j]
        if is_qj_reachable == 1:
            new_states.append(states[j])



    #remove transitions from inaccesible states
    new_delta = filter(lambda rule: (rule[0][0] in new_states), m.delta)

    return Automata(
        alphabet = m.alphabet,
        states = new_states,
        delta = new_delta,
        initial = m.initial,
        final = m.final
    )

def test_remove_inaccesible_states():
    delta = [
        (("q0", "a"), "q1"),
        (("q0", "b"), "q0"),
        (("q1", "a"), "q0"),
        (("q1", "b"), "q2"),
        (("inaccesible", "b"), "inaccesible")
    ]
    states   = ["q0", "q1", "q2", "inaccesible"]
    final    = ["q1"]
    alphabet = ["a", "b"]
    initial  = "q0"

    m = Automata(
        alphabet = alphabet,
        states = states,
        delta = delta,
        initial = initial,
        final = final
    )

    m = remove_inaccesible_states(m)

    assert m.states == ['q0', 'q1', 'q2']
    assert m.delta == [(('q0', 'a'), 'q1'), (('q0', 'b'), 'q0'), (('q1', 'a'), 'q0'), (('q1', 'b'), 'q2')]



