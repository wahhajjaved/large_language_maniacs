from state_description import *
from plot_graph import PlotGraph

# discretized quantity and derivative spaces
IQ_SPACE = set([ZERO, POS])
ID_SPACE = set([NEG, ZERO, POS])
VQ_SPACE = set([ZERO, POS, MAX])
VD_SPACE = set([NEG, ZERO, POS])
OQ_SPACE = set([ZERO, POS, MAX])
OD_SPACE = set([NEG, ZERO, POS])
HQ_SPACE = set([ZERO, POS, MAX])
HD_SPACE = set([NEG, ZERO, POS])
PQ_SPACE = set([ZERO, POS, MAX])
PD_SPACE = set([NEG, ZERO, POS])


def find_neighbors(graph, to_search, sd):
    """
     Find all state descriptions which can be transitioned to from sd
     and add the appropriate edges to the graph.
    """

    params = sd.get_all_params()

    # check to see if the current state is stable (all derivs == ZERO)
    # if so, no further change is possible
    if params[ID] == 0:
        if params[VD] == 0:
            if params[OD] == 0:
                if params[HD] == 0:
                    if params[PD] == 0:
                        return

    # initially, we consider any transition possible
    spaces = [IQ_SPACE.copy(), set([ZERO, POS]),
              VQ_SPACE.copy(), VD_SPACE.copy(),
              OQ_SPACE.copy(), OD_SPACE.copy(),
              HQ_SPACE.copy(), HD_SPACE.copy(),
              PQ_SPACE.copy(), PD_SPACE.copy()]

    # prune transitions that don't respect influences
    spaces = enforce_influences(sd, spaces)

    # prune transitions that don't respect proportionality
    spaces = enforce_proportions(sd, spaces)

    # prune transitions where the new quantity doesn't
    # respect the current derivative
    spaces = enforce_derivatives(sd, spaces)

    # prune transitions that don't respect continuity
    spaces = enforce_continuity(sd, spaces)

    for iq_val in spaces[IQ]:
        for id_val in spaces[ID]:
            for vq_val in spaces[VQ]:
                for vd_val in spaces[VD]:
                    for oq_val in spaces[OQ]:
                        for od_val in spaces[OD]:
                            for hq_val in spaces[HQ]:
                                for hd_val in spaces[HD]:
                                    for pq_val in spaces[PQ]:
                                        for pd_val in spaces[PD]:

                                            # enforce correspondences from volume to outflow
                                            # MAX outflow <=> MAX volume
                                            # ZERO outflow <=> ZERO volume etc
                                            if ((oq_val == MAX) != (vq_val == MAX)):
                                                continue
                                            if ((oq_val == ZERO) != (vq_val == ZERO)):
                                                continue
                                            if ((oq_val == MAX) != (hq_val == MAX)):
                                                continue
                                            if ((oq_val == ZERO) != (hq_val == ZERO)):
                                                continue
                                            if ((oq_val == MAX) != (pq_val == MAX)):
                                                continue
                                            if ((oq_val == ZERO) != (pq_val == ZERO)):
                                                continue
                                            if ((hq_val == MAX) != (pq_val == MAX)):
                                                continue
                                            if ((hq_val == ZERO) != (pq_val == ZERO)):
                                                continue
                                            if ((vq_val == MAX) != (pq_val == MAX)):
                                                continue
                                            if ((vq_val == ZERO) != (pq_val == ZERO)):
                                                continue
                                            if ((vq_val == MAX) != (hq_val == MAX)):
                                                continue
                                            if ((vq_val == ZERO) != (hq_val == ZERO)):
                                                continue


                                            # if a quantity hits a max or min value,
                                            # the corresponding derivative should level off
                                            # e.g., ZERO inflow => ZERO change in inflow
                                            if ((params[IQ] == POS) and (iq_val == ZERO)):
                                                id_val = ZERO
                                            if ((params[VQ] == POS) and (vq_val == ZERO)):
                                                vd_val = ZERO
                                            if ((params[VQ] == POS) and (vq_val == MAX)):
                                                vd_val = ZERO
                                            if ((params[OQ] == POS) and (oq_val == ZERO)):
                                                od_val = ZERO
                                            if ((params[OQ] == POS) and (oq_val == MAX)):
                                                od_val = ZERO
                                            if ((params[HQ] == POS) and (hq_val == ZERO)):
                                                hd_val = ZERO
                                            if ((params[HQ] == POS) and (hq_val == MAX)):
                                                hd_val = ZERO
                                            if ((params[PQ] == POS) and (pq_val == ZERO)):
                                                pd_val = ZERO
                                            if ((params[PQ] == POS) and (pq_val == MAX)):
                                                pd_val = ZERO

                                            # If a quantity stays at a max (or min) value,
                                            # the corresponding derivative cannot start
                                            # increasing (or decreasing) again
                                            if ((params[IQ] == ZERO) and (iq_val == ZERO)):
                                                if id_val == NEG:
                                                    continue
                                            if ((params[VQ] == ZERO) and (vq_val == ZERO)):
                                                if vd_val == NEG:
                                                    continue
                                            if ((params[VQ] == MAX) and (vq_val == MAX)):
                                                if vd_val == POS:
                                                    continue
                                            if ((params[OQ] == ZERO) and (oq_val == ZERO)):
                                                if od_val == NEG:
                                                    continue
                                            if ((params[OQ] == MAX) and (oq_val == MAX)):
                                                if od_val == POS:
                                                    continue
                                            if ((params[HQ] == ZERO) and (hq_val == ZERO)):
                                                if hd_val == NEG:
                                                    continue
                                            if ((params[HQ] == MAX) and (hq_val == MAX)):
                                                if hd_val == POS:
                                                    continue
                                            if ((params[PQ] == ZERO) and (pq_val == ZERO)):
                                                if pd_val == NEG:
                                                    continue
                                            if ((params[PQ] == MAX) and (pq_val == MAX)):
                                                if pd_val == POS:
                                                    continue

                                            neighbor = State_Description([iq_val, id_val,
                                                                          vq_val, vd_val,
                                                                          oq_val, od_val,
                                                                          hq_val, hd_val,
                                                                          pq_val, pd_val])

                                            if neighbor == sd:
                                                continue
                                            else:
                                                if neighbor not in graph[sd]:
                                                    graph[sd] += [neighbor]
                                                    to_search.append(neighbor)


def enforce_continuity(sd, spaces):
    """
     Eliminate transitions to states that don't preserve continuity.
     E.g., if the volume at one state is zero, you can't immediately
     transition to maximum volume at the next state.
    """
    params = sd.get_all_params()

    # there's no continuity to enforce on inflow quantity

    # the derivatives can't skip ZERO
    for i in [ID, VD, OD, HD, PD]:
        if params[i] == POS:
            spaces[i] = spaces[i].difference(set([NEG]))
        elif params[i] == NEG:
            spaces[i] = spaces[i].difference(set([POS]))

    # the quantity of volume and outflow can't skip POS
    for i in [VQ, OQ, HQ, PQ]:
        if params[i] == MAX:
            spaces[i] = spaces[i].difference(set([ZERO]))
        elif params[i] == ZERO:
            spaces[i] = spaces[i].difference(set([MAX]))

    return spaces

def enforce_influences(sd, spaces):
    """
     The derivative of volume in possible transitions is
     determined by the quantities of inflow and outflow.
    """

    params = sd.get_all_params()

    # inflow has a positive influence on volume
    inflow_influence = params[IQ]
    # outflow has a negative influence on volume
    outflow_influence = -1 * params[OQ]

    if inflow_influence == 0:
        if outflow_influence < 0:
            # the total influence on volume is negative
            spaces[VD] = set([NEG])
        else:
            # the total influence on volume is neutral
            spaces[VD] = set([ZERO])
    else:
        if outflow_influence == 0:
            # the total influence on volume is positive
            spaces[VD] = set([POS])

    # we cannot determine the total influence if inflow influence
    # is positive and outflow influence is negative

    return spaces

def enforce_proportions(sd, spaces):
    """
     The derivative of outflow in possible transitions is
     determined by the derivative of volume
    """

    params = sd.get_all_params()

    # volume determines height
    spaces[HD] = set([params[VD]])

    # height determines pressure
    spaces[PD] = set([params[HD]])

    # pressure determines outflow
    spaces[OD] = set([params[PD]])

    return spaces

def enforce_derivatives(sd, spaces):
    params = sd.get_all_params()

    if params[ID] == ZERO:
        spaces[IQ] = set([params[IQ]])
    else:
        if params[IQ] == POS:
            spaces[IQ] = set([POS])

    for i in [VD, OD, HD, PD]:
        if params[i] == ZERO:
            # if derivative is ZERO, quantity can't change
            spaces[i - 1] = set([params[i - 1]])
        elif params[i] == POS:
            # if derivative is POS, quantity must stay same or increase
            if params[i - 1] != MAX:
                spaces[i - 1] = set([params[i - 1], params[i - 1] + 1])
            else:
                spaces[i - 1] = set([params[i - 1]])
        else:
            # if derivative is NEG, quantity must stay same or decrease
            if params[i - 1] != ZERO:
                spaces[i - 1] = set([params[i - 1], params[i - 1] - 1])
            else:
                spaces[i - 1] = set([params[i - 1]])

    return spaces

def main():

    # state transition graph
    graph = {}
    # describe an empty tub with no inflow
    empty = State_Description()
    # describe an empty tub in the instant the tap is opened
    tap_on = State_Description([ZERO, POS, ZERO, ZERO, ZERO, ZERO, ZERO, ZERO, ZERO, ZERO])

    # add an edge from empty to tap_on
    graph[empty] = [tap_on]

    # stack of nodes to search depth-first
    to_search = [tap_on]
    searched = [empty]

    while len(to_search) > 0:
        sd = to_search.pop()
        if sd not in searched:
            searched.append(sd)
            graph[sd] = []
            find_neighbors(graph, to_search, sd)

    print(len(graph.keys()))


    sd = State_Description([POS, ZERO, MAX, ZERO, MAX, ZERO, MAX, ZERO, MAX, ZERO])

    print(len(graph[sd]))
    for n in graph[sd]:
        print(n)

    dot_graph = PlotGraph(graph)
    dot_graph.generate_graph(empty)
    dot_graph.save()


if __name__ == '__main__':
    main()
