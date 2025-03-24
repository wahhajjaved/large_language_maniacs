#! /usr/bin/env python
# runpbs_evol.py
# runs evolutionary algorithm on arm2dms model using PBS Torque in HPC

import os, sys
import csv
from random import Random
from time import time, sleep
import inspyred
import logging
from popen2 import popen2
import pickle
import multiprocessing
import Queue

ngen = -1 #global variable keeping number of generations

###############################################################################
### Simulation options
###############################################################################  
simdatadir = 'data/15feb21_evol' # folder to save sim results
saveMuscles = 0
num_islands = 10
max_migrants = 1
migration_interval = 5
pop_size = 10
num_elites = 1
max_generations = 1000
max_evaluations = max_generations *  num_islands * pop_size
mutation_rate = 0.4
crossover = 0.5

# parameter names and ranges
pNames = []
pRanges = []
pNames.append('trainTime'); pRanges.append([30*1e3,180*1e3]) #int
pNames.append('plastConnsType'); pRanges.append([0,1,2,3]) # int
pNames.append('stdpFactor'); pRanges.append([0,1])
pNames.append('RLfactor'); pRanges.append([0,4])
#pNames.append('stdpwin'); pRanges.append([10,30])
pNames.append('eligwin'); pRanges.append([50,150])
#pNames.append('RLinterval'); pRanges.append([50,100])
#pNames.append('maxweight'); pRanges.append([15,75])
pNames.append('trainBackground'); pRanges.append([50,200])
pNames.append('testBackground'); pRanges.append([50,200])
#pNames.append('minRLerror'); pRanges.append([0.0,0.01])
pNames.append('cmdmaxrate'); pRanges.append([5,20])
pNames.append('cmdtimewin'); pRanges.append([50,150])
pNames.append('explorMovsFactor'); pRanges.append([1,10])
#pNames.append('explorMovsDur'); pRanges.append([500,1500])

num_inputs = len(pNames)

# Set bounds and allowed ranges for params
def bound_params(candidate, args):
    for p in candidate:
        cBound.append(max(min(p, max(param1_range)), min(param1_range)))

    # need to be integer 
    cBound[0] = round(max(min(pRanges[0], max(pRanges[0])), min(pRanges[0])))
    cBound[1] = round(max(min(pRanges[1], max(pRanges[1])), min(pRanges[1])))
  
    # fixed values from list
    #param14 = min(param14_range, key=lambda x:abs(x-c[13]))

    candidate = cBound
    return candidate


###############################################################################
### Generate new set of random values for params
###############################################################################  
def generate_rastrigin(random, args):
    size = args.get('num_inputs', 10)
    paramsRand = []
    for iparam in range(len(pNames)):
        paramsRand.append(random.uniform(min(pRanges[iparam]),max(pRanges[iparam])))

    # need to be integer 
    paramsRand[0] = round(paramsRand[0])
    paramsRand[1] = round(paramsRand[1])

    # fixed values from list
    #param[14] = min(param14_range, key=lambda x:abs(x-param14))

    return paramsRand


###############################################################################
### Observer
###############################################################################  
def my_observer(population, num_generations, num_evaluations, args):
    #ngen=num_generations
    best = max(population)
    print('{0:6} -- {1} : {2}'.format(num_generations, 
                                      best.fitness, 
                                      str(best.candidate)))


###############################################################################
### Parallel evaluation
###############################################################################   
def parallel_evaluation_pbs(candidates, args):
    global ngen
    simdatadir = args.get('simdatadir') # load params
    ngen += 1 # increase number of generations
    maxiter_wait=args.get('maxiter_wait',1000) # 
    default_error=args.get('default_error',0.15)
    numproc = 4

    #run pbs jobs
    total_jobs = 0
    for i, c in enumerate(candidates): 
        outfilestem=simdatadir+"/gen_"+str(ngen)+"_cand_"+str(i) # set filename
        with open('%s_params'% (outfilestem), 'w') as f: # save current candidate params to file 
            pickle.dump(c, f)
        command = 'mpiexec -np %d nrniv -python -mpi main.py outfilestem="%s"'%(numproc, outfilestem) # set command to run
        for iparam, param in enumerate(c): # add all param names and values dynamically
            paramstring = ' %s=%r' % (pNames[iparam], param)
            command += paramstring

        output, input = popen2('qsub') # Open a pipe to the qsub command.
        job_name = outfilestem # Customize your options here
        walltime = "01:00:00"
        processors = "nodes=1:ppn=%d"%(numproc)

        job_string = """#!/bin/bash 
        #PBS -N %s
        #PBS -l walltime=%s
        #PBS -q longq
        #PBS -l %s
        #PBS -o %s.run
        #PBS -e %s.err
        cd $PBS_O_WORKDIR
        echo $PBS_O_WORKDIR
        %s""" % (job_name, walltime, processors, job_name, job_name, command)

        # Send job_string to qsub
        input.write(job_string)
        input.close()

        # Print your job and the response to the screen
        print job_string
        #print output.read()+": "+command
        total_jobs+=1
        sleep(0.1)

    #read results from file
    fitness = [None] * total_jobs
    num_iters = 0
    jobs_completed=0
    while jobs_completed < total_jobs:
        print outfilestem
        print str(jobs_completed)+" / "+str(total_jobs)+" jobs completed"
        unfinished = [i for i, x in enumerate(fitness) if x is None]
        print "unfinished:"+str(unfinished)
        for i in unfinished:
            # load error from file
            try:
                outfilestem=simdatadir+"/gen_"+str(ngen)+"_cand_"+str(i) # set filename
                with open('%s_error'% (outfilestem)) as f:
                    error=pickle.load(f)
                    fitness[i] = error
                    jobs_completed+=1
                    #print "error: "+str(error)
            except:
                pass
            #print "Waiting for job: "+str(i)+" ... iteration:"+str(num_iters[i])
        num_iters+=1
        if num_iters>=maxiter_wait: #or (num_iters>maxiter_wait/2 and jobs_completed>(0.95*total_jobs)): 
            print "max iterations reached -- remaining jobs set to default error"
            for j in unfinished:
                fitness[j] = default_error
                jobs_completed+=1
        sleep(2) # sleep 2 seconds before checking agains
    return fitness


###############################################################################
### Multiprocessing Migration
###############################################################################    
class MultiprocessingMigratorNoBlock(object):
    """Migrate among processes on the same machine.
      remove lock
    """
    def __init__(self, max_migrants=1, migration_interval=10):
        self.max_migrants = max_migrants
        self.migration_interval = migration_interval
        self.migrants = multiprocessing.Queue(self.max_migrants)
        self.__name__ = self.__class__.__name__
  
    def __call__(self, random, population, args):
        # only migrate every migrationInterval generations
        if (args["_ec"].num_generations % self.migration_interval)==0:
            evaluate_migrant = args.setdefault('evaluate_migrant', False)
            migrant_index = random.randint(0, len(population) - 1)
            old_migrant = population[migrant_index]
            try:
                migrant = self.migrants.get(block=False)
                if evaluate_migrant:
                    fit = args["_ec"].evaluator([migrant.candidate], args)
                    migrant.fitness = fit[0]
                    args["_ec"].num_evaluations += 1     
            except Queue.Empty:
                pass
            try:
                self.migrants.put(old_migrant, block=False)
            except Queue.Full:
                pass
        return population


###############################################################################
### Set initial conditions (in case have to restart)
###############################################################################

def setInitial(simdatadir):
    global ngen
    # load individuals.csv file and set last population as initial_cs
    ind_gens=[]
    ind_cands=[]
    ind_fits=[]
    ind_cs=[]
    with open('%s/individuals.csv' % (simdatadir)) as f:
        reader=csv.reader(f)
        for row in reader:
            ind_gens.append(int(row[0]))
            ind_cands.append(int(row[1]))
            ind_fits.append(float(row[2]))
            cs = [float(row[i].replace("[","").replace("]","")) for i in range(3,len(row))]
            ind_cs.append(cs)

    initial_gen = max(max(ind_gens) - 2, 0)
    initial_cs = [ind_cs[i] for i in range(len(ind_gens)) if ind_gens[i]==initial_gen]
    initial_fit = [ind_fits[i] for i in range(len(ind_gens)) if ind_gens[i]==initial_gen]

    # set global variable to track number of gens to initial_gen
    ngen = initial_gen

    print initial_gen, initial_cs, initial_fit
    return initial_gen, initial_cs, initial_fit


###############################################################################
### Create islands
###############################################################################
def create_island(rand_seed, island_number, mp_migrator, simdatadir, max_evaluations, max_generations, \
    num_inputs, mutation_rate, crossover, pop_size, num_elites):   
    # create folder       
    simdatadir = simdatadir+'_island_'+str(i)
    mdir_str='mkdir %s' % (simdatadir)
    os.system(mdir_str) 

    # if individuals.csv already exists, continue from last generation
    if os.path.isfile(simdatadir+'/individuals.csv'):
        initial_gen, initial_cs, initial_fit = setInitial(simdatadir)
    else:
        initial_gen=0
        initial_cs=[]
        initial_fit=[]

    statfile = open(simdatadir+'/statistics.csv', 'a')
    indifile = open(simdatadir+'/individuals.csv', 'a')

    #random nums and save seed
    my_seed = rand_seed #int(time())
    seedfile = open(simdatadir+'/randomseed.txt', 'a')
    seedfile.write('{0}'.format(my_seed))
    seedfile.close()
    prng = Random()
    prng.seed(my_seed) 

    # custom evolutionary algorithm based on Krichmar's params:
    # Ten SNN configurations ran in parallel. To evolve V1 simple cell responses, 
    # a real-valued optimization algo- rithm called Evolution Strategies (De Jong, 2002) 
    # was used with deterministic tournament selection, weak-elitism replacement, 40% Gaussian mutation and 50% crossover. 
    # Weak-elitism ensures the overall fitness monotonically increases each generation by replacing the worst fitness 
    # individual of the offspring population with the best fitness individual of the parent population. 

    ea = inspyred.ec.EvolutionaryComputation(prng)
    ea.selector = inspyred.ec.selectors.tournament_selection
    ea.variator = [inspyred.ec.variators.uniform_crossover, 
                   inspyred.ec.variators.nonuniform_mutation]
    ea.replacer = inspyred.ec.replacers.generational_replacement#inspyred.ec.replacers.plus_replacement
    #inspyred.ec.replacers.truncation_replacement (with num_selected=50)
    ea.terminator = inspyred.ec.terminators.generation_termination
    ea.observer = [inspyred.ec.observers.stats_observer, inspyred.ec.observers.file_observer]
    ea.migrator = mp_migrator

    final_pop = ea.evolve(generator=generate_rastrigin, 
                          evaluator=parallel_evaluation_pbs,
                          pop_size=pop_size, 
                          bounder=bound_params,
                          maximize=False,
                          max_evaluations=max_evaluations,
                          max_generations=max_generations,
                          num_inputs=num_inputs,
                          mutation_rate=mutation_rate,
                          crossover=crossover,
                          tournament_size=2,
                          num_selected=pop_size,
                          num_elites=num_elites,
                          simdatadir=simdatadir,
                          statistics_file=statfile,
                          individuals_file=indifile,
                          evaluate_migrant=False,
                          initial_gen=initial_gen,
                          initial_cs=initial_cs,
                          initial_fit=initial_fit)
    
    if display:
        best = max(final_pop) 
        print('Best Solution: \n{0}'.format(str(best)))

    return ea


###############################################################################
### Main - logging, island model params, launch multiprocessing
###############################################################################
if __name__ == '__main__':
    # create folder    
    mdir_str='mkdir %s' % (simdatadir)
    os.system(mdir_str) 
    
    # debug info
    logger = logging.getLogger('inspyred.ec')
    logger.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler(simdatadir+'/inspyred.log', mode='a')
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)    

    # run multiple islands
    mp_migrator = MultiprocessingMigratorNoBlock(max_migrants, migration_interval)
    rand_seed = int(time())
    jobs = []
    for i in range(num_islands):
        p = multiprocessing.Process(target=create_island, args=(rand_seed + i, i, mp_migrator, simdatadir, \
         max_evaluations, max_generations, num_inputs, mutation_rate, crossover, pop_size, num_elites))
        p.start()
        jobs.append(p)
    for j in jobs:
        j.join()