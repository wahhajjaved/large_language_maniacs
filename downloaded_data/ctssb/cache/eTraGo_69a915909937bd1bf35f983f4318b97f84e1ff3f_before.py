"""
K-means testing File

see: https://github.com/openego/eTraGo/issues/6

ToDo's:
-------
the remaining work would be:

- [x] implement the [todo](https://github.com/openego/eTraGo/blob/features/k-means-clustering/etrago/k_means_testing.py#L112-L115) so that the x of the lines which are newly defined as 380kV lines are adjusted

- [ ] in the [Hoersch and Brown contribution](https://arxiv.org/pdf/1705.07617.pdf) in Chapter II 2) and follwoing the weighting is defined. the weighting right now is equal over all buses. This should be changed to the assumptions with respect to the contribution or define another senseful weighting

- [ ] add functionality to save the resulting cluster for reproducibility

- [ ] convert it to a function and move it [here](https://github.com/openego/eTraGo/blob/features/k-means-clustering/etrago/cluster/networkclustering.py)

Error handling:

* use pip3 install scikit-learn in order to use PyPSA busmap_by_kmeans




"""
__copyright__ = "tba"
__license__ = "tba"
__author__ = "tba"


import numpy as np
from numpy import genfromtxt
np.random.seed()
from egopowerflow.tools.tools import oedb_session
from egopowerflow.tools.io import NetworkScenario
import time
from egopowerflow.tools.plot import (plot_line_loading, plot_stacked_gen,
                                     add_coordinates, curtailment, gen_dist,
                                     storage_distribution)
from etrago.extras.utilities import load_shedding, data_manipulation_sh, results_to_csv, parallelisation, pf_post_lopf
from etrago.cluster.networkclustering import busmap_from_psql, cluster_on_extra_high_voltage
from pypsa.networkclustering import busmap_by_kmeans, get_clustering_from_busmap
import pandas as pd
import json


# import scenario settings **args
with open('scenario_setting.json') as f:
    scenario_setting = json.load(f)

args = scenario_setting

def etrago(args):

    def weighting_for_scenario(x):
        b_i = x.index
        g = normed(gen.reindex(b_i, fill_value=0))
        l = normed(load.reindex(b_i, fill_value=0))
      
        w= g + l
        return (w * (100. / w.max())).astype(int)

    def normed(x):
        return (x/x.sum()).fillna(0.)


    session = oedb_session(args['db'])

    # additional arguments cfgpath, version, prefix
    scenario = NetworkScenario(session,
	                           version=args['gridversion'],
	                           prefix=args['ormcls_prefix'],
	                           method=args['method'],
	                           start_h=args['start_h'],
	                           end_h=args['end_h'],
	                           scn_name=args['scn_name'])

    network = scenario.build_network()

    # add coordinates
    network = add_coordinates(network)

    # TEMPORARY vague adjustment due to transformer bug in data processing
    #network.transformers.x=network.transformers.x*0.01


    if args['branch_capacity_factor']:
	    network.lines.s_nom = network.lines.s_nom*args['branch_capacity_factor']
	    network.transformers.s_nom = network.transformers.s_nom*args['branch_capacity_factor']

    if args['generator_noise']:
	    # create generator noise
	    noise_values = network.generators.marginal_cost + abs(np.random.normal(0,0.001,len(network.generators.marginal_cost)))
	    np.savetxt("noise_values.csv", noise_values, delimiter=",")
	    noise_values = genfromtxt('noise_values.csv', delimiter=',')
	    # add random noise to all generator
	    network.generators.marginal_cost = noise_values

    if args['storage_extendable']:
	    # set virtual storages to be extendable
	    if network.storage_units.source.any()=='extendable_storage':
	        network.storage_units.p_nom_extendable = True
	    # set virtual storage costs with regards to snapshot length
	        network.storage_units.capital_cost = (network.storage_units.capital_cost /
	        (8760//(args['end_h']-args['start_h']+1)))

    # for SH scenario run do data preperation:
    if args['scn_name'] == 'SH Status Quo':
	    data_manipulation_sh(network)

    #load shedding in order to hunt infeasibilities
    if args['load_shedding']:
	    load_shedding(network)

    # network clustering
    if args['network_clustering']:
	    network.generators.control="PV"
	    busmap = busmap_from_psql(network, session, scn_name=args['scn_name'])
	    network = cluster_on_extra_high_voltage(network, busmap, with_time=True)



    if args['k_mean_clustering']:
      print('start k-mean clustering')
      # prepare k-mean
      # k-means clustering (first try)
      network.generators.control="PV"
      network.buses['v_nom'] = 380.
      # problem our lines have no v_nom. this is implicitly defined by the connected buses:
      network.lines["v_nom"] = network.lines.bus0.map(network.buses.v_nom)

      # adjust the x of the lines which are not 380. 
      lines_v_nom_b = network.lines.v_nom != 380
      network.lines.loc[lines_v_nom_b, 'x'] *= (380./network.lines.loc[lines_v_nom_b, 'v_nom'])**2
      network.lines.loc[lines_v_nom_b, 'v_nom'] = 380.

      trafo_index = network.transformers.index
      transformer_voltages = pd.concat([network.transformers.bus0.map(network.buses.v_nom), network.transformers.bus1.map(network.buses.v_nom)], axis=1)


      network.import_components_from_dataframe(
       network.transformers.loc[:,['bus0','bus1','x','s_nom']]
       .assign(x=network.transformers.x*(380./transformer_voltages.max(axis=1)**2))
       .set_index('T' + trafo_index),
       'Line')
      network.transformers.drop(trafo_index, inplace=True)
      
      for attr in network.transformers_t:
        network.transformers_t[attr] = network.transformers_t[attr].reindex(columns=[])
        
      # ToDo:
      #change np.repeat(1, len(network.buses) to load and conv P_max
      conv_types = {'biomass', 'run_of_river', 'gas', 'oil','coal', 'waste','uranium'}
      # Attention: network.generators.carrier.unique() 
      # conv_types only for SH scenario defined!
      gen = (network.generators.loc[network.generators.carrier.isin(conv_types)
            ].groupby('bus').p_nom.sum().reindex(network.buses.index, 
            fill_value=0.) + network.storage_units.loc[network.storage_units.carrier.isin(conv_types)
            ].groupby('bus').p_nom.sum().reindex(network.buses.index, fill_value=0.))
            
      load = network.loads_t.p_set.mean().groupby(network.loads.bus).sum()
      
      # k-mean clustering
      # busmap = busmap_by_kmeans(network, bus_weightings=pd.Series(np.repeat(1,
      #       len(network.buses)), index=network.buses.index) , n_clusters= 10)
      weight = weighting_for_scenario(network.buses).reindex(network.buses.index, fill_value=1)
      busmap = busmap_by_kmeans(network, bus_weightings=pd.Series(weight), buses_i=network.buses.index , n_clusters= 10)


      # ToDo change function in order to use bus_strategies or similar
      clustering = get_clustering_from_busmap(network, busmap)
      network = clustering.network
      #network = cluster_on_extra_high_voltage(network, busmap, with_time=True)


    # parallisation
    if args['parallelisation']:
	    parallelisation(network, start_h=args['start_h'], end_h=args['end_h'],group_size=1, solver_name=args['solver'])
    # start linear optimal powerflow calculations
    elif args['method'] == 'lopf':
	    x = time.time()
	    network.lopf(scenario.timeindex, solver_name=args['solver'])
	    y = time.time()
	    z = (y - x) / 60 # z is time for lopf in minutes
    # start non-linear powerflow simulation
    elif args['method'] == 'pf':
	    network.pf(scenario.timeindex)
    if args['pf_post_lopf']:
	    pf_post_lopf(network, scenario)

    # write lpfile to path
    if not args['lpfile'] == False:
	    network.model.write(args['lpfile'], io_options={'symbolic_solver_labels': True})
    # write PyPSA results to csv to path
    if not args['results'] == False:
	    results_to_csv(network, args['results'])

    return network

# execute etrago function
network = etrago(args)


#network.plot(bus_sizes=(2*weighting_for_scenario(network.buses.query('scn_name=="SH Status Quo"'))).reindex(network.buses.index, fill_value=1))


# plots
# make a line loading plot
plot_line_loading(network)

#plot stacked sum of nominal power for each generator type and timestep
#plot_stacked_gen(network, resolution="MW")

# close session
#session.close()

# plot stacked sum of nominal power for each generator type and timestep
plot_stacked_gen(network, resolution="MW")

# plot to show extendable storages
storage_distribution(network)
