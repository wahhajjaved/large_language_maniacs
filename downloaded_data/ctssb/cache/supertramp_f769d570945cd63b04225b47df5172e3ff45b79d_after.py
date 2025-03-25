#! /usr/bin/env python

import sys
import os
import json
import random
import argparse

general_job_template = """\
#! /bin/bash
#$ -cwd
#$ -V
#$ -S /bin/bash
#$ -l h_vmem=8G
#$ -l virtual_free=8G
{queue}
{commands}
"""

def main():
    """

    ### 2014-09-27

        b = birth-rate
        d = "global" dispersal rate
        e = extinction rate

        P:5, C:2
        ========
            The ML estimates of the speciation rate and extinction rate for the
            Psychotria tree are 0.33 and 0 events per Myr (estimated with the
            “birthdeath” function of the R package geiger; Harmon et al. 2008), so, for
            rough comparability, the base speciation rate was set to lambda=0.3 in all
            simulations, and mu was set to 0, 0.1, or 0.3.

        P:6, C:1
        ========
            d = {0, 0.03, 0.15}
            e = {0, 0.03, 0.15}
            All combinations of parameters were used, except thoise where e > d

        P:7
        ===

        Number of areas:

            Psychotria = 4

        P:10
        ====

            b = {0.
            d = {0.001, 0.005, 0.03, 0.04, 0.12,}


    ### 2014-08-27

        Oceania

            Number of islands                               6

            Diversification Rate (APE)
                For Oceania with root age of 1.0            2.733492

            Extinction Rate (Lagrange)
                For Oceania with root age of 1.0            5.054e-07
                For Oceania with root age of 100000         1.741e-13

            Dispersal Rate (Lagrange)
                For Oceania with root age of 1.0            0.3255
                For Oceania with root age of 100000         4.446e-06

            Simulation Settings
                Running for 100000 generations
                    Extinction rate:                            0
                    Birth rate:                                 2.73 / 100000 = 2.73e-5
                    Dispersal rate:                             0.33 / 100000 = 3.3e-6
                    Niche evolution rate:                       = dispersal rate

        Continental

                For Continental with root age of 1.0,       2.8263

    ### Previously

        1 simulation generation = 100 years
        10000 simulation generations = 1e6 years
        Simulation run-time:        1000000 generations    = 1e8 years
        High speciation rate:       0.001   per generation = 0.1 per MY
        Med speciation rate:        0.0001  per generation = 0.01 per MY
        Low speciation rate:        0.00001 per generation = 0.001 per MY
        Dispersal rate:             0.01, 0.5, 1.0, 2.0, 10.0 x speciation rates
        Niche evolution prob:       0.001, 0.01, 0.10, 1.0


    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--venv",
            default=None,
            help="Path to Python virtual environment.")
    parser.add_argument("-z", "--random-seed",
            default=None,
            help="Seed for random number generator engine.")
    parser.add_argument("-q", "--queue",
            default="long",
            help="Name of queue to use (default: '%(default)s')")
    parser.add_argument("--no-queue",
            action="store_true",
            default=False,
            help="Do not use any queue")
    # parser.add_argument("--ngens",
    #         type=int,
    #         default=1000000,
    #         help="Number of generations to run (default = %(default)s).")
    parser.add_argument("--nreps",
            type=int,
            default=100,
            help="number of replicates (default = %(default)s).")
    args = parser.parse_args()

    if args.random_seed is None:
        args.random_seed = random.randint(0, sys.maxsize)
    rng = random.Random(args.random_seed)
    if args.venv is not None:
        venv_dir = os.path.expanduser(os.path.expandvars(args.venv))
        venv_activate = os.path.abspath(os.path.join(venv_dir, "bin", "activate"))
        if not os.path.exists(venv_activate):
            raise Exception("Virtual environment activation script not found: '{}'".format(venv_activate))
        source_venv = "source {}".format(venv_activate)
    else:
        source_venv = ""
    if not args.no_queue and args.queue:
        queue = "#$ -q {}".format(args.queue)
    else:
        queue = ""
    # python_path = "python3"
    # supertramp_path = os.path.abspath(os.path.join(
    #         os.path.dirname(__file__),
    #         "supertramp-simulate.py"))
    supertramp_path = "supertramp-simulate.py"
    # dispersal_models = ["constrained", "unconstrained"]
    # birth_death_rates = [(2.73e-5,0.0), ]
    # dispersal_rates = [3.3e-6,]
    # niche_evolution_probs = [3.3e-6,]
    dispersal_models = ["constrained", "unconstrained"]
    birth_death_rates = [ (0.03, 0), ] # [(2.73e-5,0.0), ]
    dispersal_rates = [0.001, 0.005, 0.03, 0.04, 0.12, 0.15]
    niche_evolution_probs = [0.001, 0.005, 0.03, 0.04, 0.12, 0.15, 0.5, 1.0]
    run_manifest = {}
    # for ngens in (int(x) for x in (1e5,)):
    for ntips in (50, 100):
        for dm_idx, dispersal_model in enumerate(dispersal_models):
            for bd_idx, (birth_rate, death_rate) in enumerate(birth_death_rates):
                for drf_idx, dispersal_rate in enumerate(dispersal_rates):
                    for nef_idx, niche_evolution_prob in enumerate(niche_evolution_probs):
                        stem = "d{dispersal_rate:10.8f}_q{niche_evolution_prob:10.8f}_b{birth_rate:10.8f}_e{death_rate:10.8f}_{dispersal_model}".format(
                                dispersal_rate=dispersal_rate,
                                niche_evolution_prob=niche_evolution_prob,
                                birth_rate=birth_rate,
                                death_rate=death_rate,
                                dispersal_model=dispersal_model,
                                )
                        output_prefix = stem
                        run_cmd = []
                        run_cmd.append(supertramp_path)
                        run_cmd.extend(["-z", str(rng.randint(0, sys.maxsize))])
                        run_cmd.extend(["--num-islands", str(6)])
                        run_cmd.extend(["--num-habitat-types", str(2)])
                        run_cmd.extend(["--nreps", str(args.nreps)])
                        run_cmd.extend(["-b", str(birth_rate)])
                        run_cmd.extend(["-d", str(death_rate)])
                        run_cmd.extend(["--niche-evolution-probability", str(niche_evolution_prob)])
                        run_cmd.extend(["--dispersal-rate", str(dispersal_rate)])
                        # run_cmd.extend(["--ngens", str(ngens)])
                        run_cmd.extend(["--target-num-tips", str(ntips)])
                        run_cmd.extend(["--output-prefix", output_prefix])
                        run_cmd.extend(["--dispersal-model", dispersal_model])
                        run_cmd = " ".join(run_cmd)
                        commands = []
                        if source_venv:
                            commands.append(source_venv)
                        commands.append(run_cmd)
                        job_filepath = stem + ".job"
                        with open(job_filepath, "w") as jobf:
                            template = general_job_template
                            jobf.write(template.format(
                                commands="\n".join(commands),
                                queue=queue,
                                ))
                        run_manifest[output_prefix] = {
                                "dispersal_model"       : dispersal_model,
                                "birth_rate"            : birth_rate,
                                "death_rate"            : death_rate,
                                "dispersal_rate"        : dispersal_rate,
                                "niche_evolution_prob"  : niche_evolution_prob,
                                # "ngens"                 : ngens,
                                "ntips"                 : ntips,
                                "treefile"              : output_prefix + ".trees",
                                "logfile"               : output_prefix + ".log",
                                }
    with open("run-manifest.json", "w") as manifestf:
        json.dump(run_manifest, manifestf)
if __name__ == "__main__":
    main()




