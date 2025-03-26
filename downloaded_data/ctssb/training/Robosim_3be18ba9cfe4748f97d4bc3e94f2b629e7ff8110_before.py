"""Robosim Test.

Usage:
    test.py list 
    test.py show <test> [--step=<step_name>] [<seed>]
    test.py run <test> [<step_name>]
    test.py runall <test> <max_n> <giri> [--step=<step_name>] [--stubb=<stubborness>]
    test.py export_map <test>
    test.py map_cpl <test> [--nc=<nc>]
"""
import draw
import model
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import visualization
import random
import model
import numpy as np
from docopt import docopt
import sys

tests =  {
    "me" : {
        "seed" : 33456,
        "map" : "mappa_empty.txt",
        "n_agents" : 3,
        "stubborness": 0.5,
        "step_name": "simple"
    },
    "m1" : {
        "seed" : 33456,
        "map" : "mappa_1.txt",
        "n_agents" : 3,
        "stubborness": 0.5,
        "step_name": "simple"
    },
    "m2" : {
        "seed" : 33456,
        "map" : "mappa_2.txt",
        "n_agents" : 3,
        "stubborness": 0.5,
        "step_name": "simple"
    },
    "m3" : {
        "seed" : 33456,
        "map" : "mappa_3.txt",
        "n_agents" : 3,
        "stubborness": 0.5,
        "step_name": "simple"
    },
    "mc" : {
        "seed" : 33456,
        "map" : "mappa_corridoio.txt",
        "n_agents" : 3,
        "stubborness": 0.5,
        "step_name": "simple"
    },
    "mm" : {
        "seed" : 33456,
        "map" : "mappa_maze.txt",
        "n_agents" : 3,
        "stubborness": 0.2,
        "step_name": "simple"
    }
}

def modded_dijkstra(mappa,center):
    dist = {}
    v_set = []
    for x in range(mappa.shape[1]):
        for y in range(mappa.shape[0]):
            dist[(x,y)] = float("inf")
            v_set.append((x,y))
    
    #v_set.append(self.pos)
    dist[center] = 0
    while len(v_set) != 0:
        u = min(dist, key=lambda k: dist[k] if k in v_set else float("inf"))
        if dist[u] == float("inf"):
            #print(u)
            #print(dist)
            #print(v_set)
            return dist
        #print(u, dist[u])
        v_set.remove(u)
        y_max, x_max = mappa.shape
        x,y = u
        x_l = x - 1 if x - 1 > 0 else 0
        x_u = x + 1 if x + 1 < x_max else x_max - 1 
        y_l = y - 1 if y - 1 > 0 else 0
        y_u = y + 1 if y + 1 < y_max else y_max - 1 

        for (y,x), ele in np.ndenumerate(mappa[y_l:y_u+1,x_l:x_u+1]):
            y += y_l
            x += x_l
            #print(str(u) + "=>" + str((x,y)))
            alt = dist[u] + 1
            if (x,y) == u:
                continue
            if ele == model.CellState.OBSTACLE:
                continue
            
            if alt < dist[(x,y)]:
                    dist[(x,y)] = alt
        #if u == goal:
        #    return path
    return dist

if __name__ == '__main__':
    arguments = docopt(__doc__, version='Robosim Test')
    t = tests[arguments['<test>']]
    if arguments["--step"]:
        t["step_name"] = arguments["--step"]
    if arguments["--stubb"]:
        t["stubborness"] = float(arguments["--stubb"])
    if arguments["<seed>"]:
        t["seed"] = arguments["<seed>"]
        if arguments["<seed>"] == "no":
            t["seed"] = None
    if arguments['list']:
        print(tests.keys())
        sys.exit()
    if arguments['show']:
        mappa = model.load_map(t['map'])
        random.seed(t['seed'])
        #np.random.seed(t['seed'])
        visualization.visualize(mappa, t['n_agents'], t['stubborness'], seed = t['seed'], test_name=", test " + arguments['<test>'], step_name=t['step_name'])
    if arguments['run']:
        mappa = model.load_map(t['map'])
        random.seed(t['seed'])
        np.random.seed(t['seed'])
        modello = model.Robosim_model(3, mappa, 0.5, seed=t["seed"], step_name=t["step_name"])
        modello.running = True
        i = 0
        while modello.running:
            i += 1
            modello.step()
        plt.plot(modello.datacollector.model_vars["Esplorate"])
        plt.title("Celle Esplorate")
        plt.savefig("Esplorate_" + arguments["<test>"] + "_" + t["step_name"] + ".svg")
        plt.close()
        plt.plot(modello.datacollector.model_vars["Comunicazioni"])
        plt.title("Comunicazioni")
        plt.savefig("Comunicazioni_" + arguments["<test>"] + t["step_name"]+ ".svg")
        plt.close()
        plt.plot(modello.datacollector.model_vars["Mosse utili"])
        plt.title("Mosse utili")
        plt.legend([x for x in range(10)], ncol=2)
        plt.savefig("Mosse_utili_" + arguments["<test>"] + t["step_name"] + ".svg")
        plt.close()
    if arguments['runall']:
        mappa = model.load_map(t['map'])
        tempi = {}
        tempipern = {}
        for n in range(1,int(arguments['<max_n>'])+1):
            n_step = 0
            print("n = " + str(n))
            maxiter = mappa.shape[0] * mappa.shape[1] * 10 
            for giro in range(int(arguments['<giri>'])):
                print("\tgiro = " + str(giro))
                modello = model.Robosim_model(n, mappa, t["stubborness"], seed=None, step_name=t["step_name"])
                modello.running = True
                i = 0
                while modello.running:
                    if i > maxiter:
                        sys.exit(1)
                    i += 1
                    modello.step()
                n_step += i
            tempi[n] = n_step/int(arguments['<giri>'])
            tempipern[n] = tempi[n] * (n**0.5)
        plt.plot(list(tempi.keys()), list(tempi.values()))
        plt.plot(list(tempipern.keys()), list(tempipern.values()))
        plt.legend(["tempi", "tempi * sqrt(n)"])
        plt.title("Tempi al variare di n")
        plt.savefig("runall_" + arguments["<test>"] + "_" + t["step_name"] + ".svg")
        plt.close()

    if arguments['export_map']:
        mappa = model.load_map(t['map'])
        draw.draw_true_map(mappa, t['map'] + ".svg")
    if arguments['map_cpl']:
        mappa = model.load_map(t['map'])
        empty_cells = np.where(mappa==model.CellState.EMPTY)
        #print(empty_cells)
        if arguments['--nc']:
            iterations = int(arguments['--nc'])
        else:
            iterations = len(empty_cells[0])
        index_array = [x for x in range(len(empty_cells[0]))]
        random.shuffle(index_array)
        ret_value = 0
        for x in index_array[:iterations]:
            x_pos = (empty_cells[1][x],empty_cells[0][x])
            dijk_dict = modded_dijkstra(mappa, x_pos)
            tmp = 0
            for key in index_array:
                target = (empty_cells[1][key],empty_cells[0][key])
                if target == x_pos:
                    continue
                tmp += dijk_dict[target] / max(abs(target[0] - x_pos[0]), abs(target[1] - x_pos[1]))
            ret_value += tmp /len(index_array)
        ret_value /= iterations
        print(ret_value)