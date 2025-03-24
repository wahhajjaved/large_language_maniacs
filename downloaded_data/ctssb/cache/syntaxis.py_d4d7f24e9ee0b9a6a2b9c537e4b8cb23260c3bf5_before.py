# -*- coding: UTF-8 -*-

# TODO:
# - automata -> min automata
# - grammar -> automata
# - automata -> grammar

def lambda_closure(Q, m):
    L = set(Q)
    marked = set([])
    while L != marked:
        for t in (L - marked):
            marked.add(t)
            for rule, ns in m.delta:
                if rule == (t, "λ"):
                    L.add(ns)

    return list(L)


def mover(T, a, m):
    L = set([])
    for t in T:
        for rule, ns in m.delta:
            if rule == (t, a):
                L.add(ns)

    return lambda_closure(L, m)





def stateset_name(states):
    return "".join(sorted(states))


def afndl_to_afd(m):
    from automata import Automata
    Q0 =  lambda_closure([m.initial], m)
    # needs to be a tuple to be hashable
    K = set([tuple(Q0)])
    marked = set([])
    delta = set([])
    while K != marked:
        for T in (K - marked):
            marked.add(T)
            for a in m.alphabet:
                U = mover(T, a, m)
                if len(U) == 0:
                    continue
                K.add(tuple(U))
                delta.add( ((stateset_name(T), a), stateset_name(U)) )

    states = [stateset_name(k) for k in K]
    final = [stateset_name(x) for x in K if len(set(x) & set(m.final)) > 0]
    return Automata(
        alphabet = m.alphabet,
        states = states,
        delta = delta,
        initial = stateset_name(Q0),
        final = final
    )



def test__lambda_closure_1():
    from automata import Automata
    states   = ["q0", "q1", "q2"]
    final    = ["q1"]
    alphabet = ["a", "b"]
    initial  = "q0"
    delta = [
        (("q0", "a"), "q1"),
        (("q0", "b"), "q0"),
        (("q1", "λ"), "q2")
    ]

    automata = Automata(
            alphabet = alphabet,
            states = states,
            delta = delta,
            initial = initial,
            final = final
            )

    L = lambda_closure(["q1"], automata)
    assert set(L) == set(["q1", "q2"])

    # Empty lambda closure
    L = lambda_closure([], automata)
    assert set(L) == set([])

# In Class example
def test__lambda_closure_2():
    from automata import Automata
    states   = ["q3", "q4", "q5", "q7", "q11", "q12"]
    final    = ["q12"]
    alphabet = ["a"]
    initial  = "q3"
    delta = [
        (("q3", "λ"), "q4"),
        (("q3", "a"), "q5"),
        (("q4", "λ"), "q7"),
        (("q7", "a"), "q12"),
        (("q4", "a"), "q11"),
        (("q11", "λ"), "q12")
    ]

    automata = Automata(
            alphabet = alphabet,
            states = states,
            delta = delta,
            initial = initial,
            final = final
            )

    Q = ["q3", "q11"]
    L = lambda_closure(Q, automata)
    assert set(L) == set(["q3", "q11", "q4", "q7", "q12"])



def test__mover_1():
    from automata import Automata
    delta = [
        (("q0", "a"), "q1"),
        (("q0", "b"), "q0"),
        (("q1", "λ"), "q2")
    ]
    states   = ["q0", "q1", "q2"]
    final    = ["q1"]
    alphabet = ["a", "b"]
    initial  = "q0"

    automata = Automata(
            alphabet = alphabet,
            states = states,
            delta = delta,
            initial = initial,
            final = final
            )

    L = mover(["q0"], "a", automata)
    assert set(L) == set(["q1", "q2"])

# Class Example
def test__mover_2():
    from automata import Automata
    states   = ["q3", "q4", "q5", "q7", "q11", "q12"]
    final    = ["q12"]
    alphabet = ["a"]
    initial  = "q3"
    delta = [
        (("q3", "λ"), "q4"),
        (("q3", "a"), "q5"),
        (("q4", "λ"), "q7"),
        (("q7", "a"), "q12"),
        (("q4", "a"), "q11"),
        (("q11", "λ"), "q12")
    ]

    automata = Automata(
            alphabet = alphabet,
            states = states,
            delta = delta,
            initial = initial,
            final = final
            )

    L = mover(["q4", "q3"], "a", automata)
    assert set(L) == set(["q11", "q5", "q12"])



def test_stateset_name():
    res = stateset_name(["q2", "q1"])
    assert res == "q1q2"



# Class example!
def test__afndl_to_afd():
    from automata import Automata
    states   = ["q0", "q1", "q2", "q3", "q4", "q5"]
    final    = ["q5"]
    alphabet = ["a", "b"]
    initial  = "q0"
    delta = [
        (("q0", "a"), "q1"),
        (("q0", "a"), "q2"),
        (("q1", "b"), "q3"),
        (("q2", "a"), "q4"),
        (("q3", "λ"), "q2"),
        (("q4", "λ"), "q3"),
        (("q4", "b"), "q5")
    ]

    automata = Automata(
            alphabet = alphabet,
            states = states,
            delta = delta,
            initial = initial,
            final = final
            )

    afd = afndl_to_afd(automata)
    assert set(afd.states) == set(["q0", "q1q2", "q2q3q4", "q2q3", "q5"])
