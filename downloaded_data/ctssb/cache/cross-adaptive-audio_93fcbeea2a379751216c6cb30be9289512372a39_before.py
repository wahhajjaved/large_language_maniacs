from __future__ import absolute_import
import MultiNEAT as NEAT
import settings
import analyze
import cross_adapt
import sound_file
import fitness
import statistics
import time
import logger
import os
import individual
import project
import effect
import experiment
import random


class Neuroevolution(object):
    def __init__(self, args):
        self.args = args

        self.seed = random.randint(1, 999999) if self.args.seed == -1 else self.args.seed
        if self.args.seed == -1:
            print('Seed: {}'.format(self.seed))

        if len(self.args.input_files) != 2:
            raise Exception('Two filenames must be specified')

        self.target_sound = sound_file.SoundFile(
            self.args.input_files[0],
            is_input=True,
            verify_file=True
        )
        self.input_sound = sound_file.SoundFile(
            self.args.input_files[1],
            is_input=True,
            verify_file=True
        )
        if self.target_sound.num_samples != self.input_sound.num_samples:
            raise Exception('The target sound and the input sound must have the same duration')

        self.project = project.Project([self.target_sound, self.input_sound])
        self.analyzer = analyze.Analyzer(self.project)
        self.fitness_evaluator = None
        if self.args.fitness == 'similarity':
            self.fitness_evaluator = fitness.LocalSimilarityFitness(self.target_sound)
        elif self.args.fitness == 'multi-objective':
            self.fitness_evaluator = fitness.MultiObjectiveFitness(self.target_sound)
        elif self.args.fitness == 'hybrid':
            self.fitness_evaluator = fitness.HybridFitness(self.target_sound)
        elif self.args.fitness == 'novelty':
            self.fitness_evaluator = fitness.NoveltyFitness(self.target_sound)
        elif self.args.fitness == 'mixed':
            self.fitness_evaluator = fitness.MixedFitness(self.target_sound)

        self.similarity_evaluator = fitness.LocalSimilarityFitness(self.target_sound)

        self.num_frames = min(
            self.target_sound.get_num_frames(),
            self.input_sound.get_num_frames()
        )

        self.neural_input_vectors = []

        if self.args.neural_mode == 'a':
            for k in range(self.num_frames):
                vector = self.target_sound.get_standardized_neural_input_vector(k)
                vector.append(1.0)  # bias input
                self.neural_input_vectors.append(vector)
        elif self.args.neural_mode == 'ab':
            for k in range(self.num_frames):
                vector = self.target_sound.get_standardized_neural_input_vector(k)
                vector += self.input_sound.get_standardized_neural_input_vector(k)
                vector.append(1.0)  # bias input
                self.neural_input_vectors.append(vector)
        elif self.args.neural_mode == 'b':
            for k in range(self.num_frames):
                vector = self.input_sound.get_standardized_neural_input_vector(k)
                vector.append(1.0)  # bias input
                self.neural_input_vectors.append(vector)
        elif self.args.neural_mode == 's':
            self.args.add_neuron_probability = 0.0
            for k in range(self.num_frames):
                vector = [1.0]  # bias input
                self.neural_input_vectors.append(vector)
        elif self.args.neural_mode == 'targets':
            for k in range(self.num_frames):
                self.neural_input_vectors.append([1.0])  # just bias

        self.effect = effect.get_effect_instance(self.args.effect_names)

        self.cross_adapter_class = (
            cross_adapt.TargetCrossAdapter if self.args.neural_mode == 'targets'
            else cross_adapt.CrossAdapter
        )

        self.cross_adapter = self.cross_adapter_class(
            input_sound=self.input_sound,
            neural_input_vectors=self.neural_input_vectors,
            effect=self.effect,
            parameter_lpf_cutoff=experiment.Experiment.PARAMETER_LPF_CUTOFF
        )

        experiment_data = {
            'param_sound': self.target_sound.get_serialized_representation(),
            'input_sound': self.input_sound.get_serialized_representation(),
            'args': vars(self.args),
            'experiment_settings': experiment.Experiment.experiment_settings,
            'generations': [],
            'feature_statistics': self.project.data['feature_statistics']
        }
        experiment.Experiment.calculate_current_experiment_id(experiment_data)

        experiment_data['seed'] = self.seed

        self.stats_logger = logger.Logger(
            os.path.join(
                settings.STATS_DATA_DIRECTORY,
                experiment.Experiment.folder_name,
                'stats.json'
            ),
            suppress_initialization=True
        )
        self.stats_logger.data = experiment_data

        self.max_similarity = None
        self.last_fitness_improvement = 0  # generation number
        if self.args.keep_k_best > -1:
            self.best_individual_ids = set()

        self.individual_fitness = {}  # individual id => individual fitness
        self.individual_born = {}  # individual id => generation when it was first found

        self.population = None
        self.init_neat()

        run_start_time = time.time()
        self.run()
        print("Run execution time: {0:.2f} seconds".format(time.time() - run_start_time))
        self.final_clean_up()

    def has_patience_ended(self, max_similarity, generation):
        """
        Return True if patience has ended, i.e. too many generations have passed without
        improving max similarity
        """
        if self.max_similarity is None or max_similarity > self.max_similarity:
            self.max_similarity = max_similarity
            self.last_fitness_improvement = generation
            return False  # There is progress. Keep going.
        elif generation - self.last_fitness_improvement >= self.args.patience:
            return True  # Patience has ended. Stop evolving.

    def init_neat(self):
        params = NEAT.Parameters()
        params.PopulationSize = self.args.population_size
        params.AllowClones = self.args.allow_clones
        params.MaxWeight = self.args.max_weight
        params.WeightMutationMaxPower = self.args.weight_mutation_max_power
        params.MutateWeightsSevereProb = self.args.mutate_weights_severe_prob
        params.WeightMutationRate = self.args.weight_mutation_rate
        params.InterspeciesCrossoverRate = self.args.interspecies_crossover_rate
        params.CrossoverRate = self.args.crossover_rate
        params.OverallMutationRate = self.args.mutation_rate
        params.RecurrentProb = 0.0
        params.RecurrentLoopProb = 0.0
        params.Elitism = self.args.elitism
        params.SurvivalRate = self.args.survival_rate
        num_inputs = len(self.neural_input_vectors[0])
        num_hidden_nodes = 0
        num_outputs = self.effect.num_parameters
        if self.args.neural_mode == 'targets':
            num_outputs *= self.num_frames
            params.MutateAddNeuronProb = 0.0
            params.MutateAddLinkProb = 0.0
            params.MutateRemLinkProb = 0.0
            params.MutateRemSimpleNeuronProb = 0.0
        else:
            params.MutateAddNeuronProb = self.args.add_neuron_probability
            params.MutateAddLinkProb = self.args.add_link_probability
            params.MutateRemLinkProb = self.args.remove_link_probability
            params.MutateRemSimpleNeuronProb = self.args.remove_simple_neuron_probability

        output_activation_function = NEAT.ActivationFunction.UNSIGNED_SIGMOID
        if self.args.output_activation_function == 'linear':
            output_activation_function = NEAT.ActivationFunction.LINEAR
        elif self.args.output_activation_function == 'sine':
            output_activation_function = NEAT.ActivationFunction.UNSIGNED_SINE

        genome = NEAT.Genome(
            0,  # ID
            num_inputs,
            num_hidden_nodes,
            num_outputs,
            self.args.fs_neat,
            output_activation_function,  # OutputActType
            NEAT.ActivationFunction.TANH,  # HiddenActType
            0,  # SeedType
            params  # Parameters
        )
        self.population = NEAT.Population(
            genome,
            params,
            True,  # whether the population should be randomized
            2.0,  # how much the population should be randomized,
            self.seed
        )

    def run(self):
        for generation in range(1, self.args.num_generations + 1):
            generation_start_time = time.time()
            print('generation {}'.format(generation))

            # Retrieve a list of all genomes in the population
            genotypes = NEAT.GetGenomeList(self.population)

            species_population_count = {}
            for s in self.population.Species:
                species_population_count[s.ID()] = s.NumIndividuals()

            individuals = []
            all_individuals = []
            for genotype in genotypes:
                that_individual = individual.Individual(
                    genotype=genotype,
                    neural_mode=self.args.neural_mode,
                    effect=self.effect
                )

                if (not self.fitness_evaluator.IS_FITNESS_RELATIVE) and \
                                that_individual.get_id() in self.individual_fitness:
                    if settings.VERBOSE:
                        print(that_individual.get_id() + ' already exists. Will not evaluate again')

                    that_individual.set_fitness(self.individual_fitness[that_individual.get_id()])
                    that_individual.similarity = self.individual_fitness[that_individual.get_id()]
                else:
                    individuals.append(that_individual)
                all_individuals.append(that_individual)

            # Check for duplicate individuals
            duplicates = {}
            unique_individuals = {}
            for ind in individuals:
                if ind.get_id() in unique_individuals:
                    if ind.get_id() in duplicates:
                        duplicates[ind.get_id()].append(ind)
                    else:
                        duplicates[ind.get_id()] = [ind]
                else:
                    unique_individuals[ind.get_id()] = ind
            if settings.VERBOSE and len(duplicates):
                print('duplicates', duplicates)

            unique_individuals_list = [unique_individuals[ind_id] for ind_id in unique_individuals]

            # Produce sound files for each unique individual
            self.cross_adapter.produce_output_sounds(unique_individuals_list, self.args.keep_csd)

            # Evaluate fitness of each unique individual
            self.evaluate_fitness(unique_individuals_list)

            # Set analysis and fitness on duplicates
            for individual_id in duplicates:
                for ind in duplicates[individual_id]:
                    ind.set_output_sound(unique_individuals[individual_id].output_sound)
                    ind.similarity = unique_individuals[individual_id].similarity

                    if self.fitness_evaluator.IS_FITNESS_RELATIVE:
                        # Discourage clusters of duplicates
                        ind.set_fitness(
                            0.5 * unique_individuals[individual_id].genotype.GetFitness()
                        )
                    else:
                        ind.set_fitness(unique_individuals[individual_id].genotype.GetFitness())

            for ind_id in unique_individuals:
                if ind_id not in self.individual_born:
                    self.individual_born[ind_id] = generation
            for ind in all_individuals:
                ind.born = self.individual_born[ind.get_id()]

            # Calculate and write stats
            all_individuals.sort(key=lambda ind: ind.similarity)
            flat_fitness_list = sorted([ind.genotype.GetFitness() for ind in all_individuals])
            flat_similarity_list = [ind.similarity for ind in all_individuals]
            max_fitness = flat_fitness_list[-1]
            min_fitness = flat_fitness_list[0]
            avg_fitness = statistics.mean(flat_fitness_list)
            max_similarity = flat_similarity_list[-1]
            min_similarity = flat_similarity_list[0]
            avg_similarity = statistics.mean(flat_similarity_list)
            fitness_std_dev = statistics.pstdev(flat_fitness_list)
            similarity_std_dev = statistics.pstdev(flat_fitness_list)
            print('max similarity: {0:.5f}'.format(max_similarity))
            print('avg similarity: {0:.5f}'.format(avg_similarity))
            stats_item = {
                'generation': generation,
                'fitness_min': min_fitness,
                'fitness_max': max_fitness,
                'fitness_avg': avg_fitness,
                'fitness_std_dev': fitness_std_dev,
                'similarity_min': min_similarity,
                'similarity_max': max_similarity,
                'similarity_avg': avg_similarity,
                'similarity_std_dev': similarity_std_dev,
                'individuals': [i.get_short_serialized_representation() for i in all_individuals],
                'species': species_population_count
            }
            self.stats_logger.data['generations'].append(stats_item)
            if generation % self.args.write_stats_every == 1 or generation == self.args.num_generations:
                self.stats_logger.write()

            patience_has_ended = self.has_patience_ended(max_similarity, generation)
            is_last_generation = patience_has_ended or generation == self.args.num_generations

            # Store individual(s)
            if self.args.keep_k_best < 0 or (self.args.keep_all_last and is_last_generation):
                # keep all individuals
                for that_individual in unique_individuals_list:
                    individual_id = that_individual.get_id()
                    if individual_id not in self.individual_fitness:
                        that_individual.save()
                    self.individual_fitness[individual_id] = that_individual.genotype.GetFitness()
            else:
                # keep only k best individuals, where "best" is defined as highest similarity
                unique_individuals_list.sort(key=lambda ind: ind.similarity, reverse=True)
                for i in range(self.args.keep_k_best):
                    self.best_individual_ids.add(unique_individuals_list[i].get_id())
                    unique_individuals_list[i].save()

                for i in range(self.args.keep_k_best, len(unique_individuals_list)):
                    if unique_individuals_list[i].get_id() not in self.best_individual_ids:
                        unique_individuals_list[i].delete(
                            try_delete_serialized_representation=False)

            if patience_has_ended:
                print(
                    'Patience has ended because max similarity has not improved for {} generations.'
                    ' Stopping.'.format(self.args.patience)
                )
                break

            # advance to the next generation
            self.population.Epoch()
            print("Generation execution time: {0:.2f} seconds".format(
                time.time() - generation_start_time)
            )

    def evaluate_fitness(self, individuals):
        sound_files = [
            that_individual.output_sound for that_individual in individuals
            ]
        self.analyzer.analyze_multiple(sound_files)

        for ind in individuals:
            if ind.output_sound.is_silent:
                ind.set_fitness(0.0)
                ind.similarity = 0.0

        non_silent_individuals = [ind for ind in individuals if not ind.output_sound.is_silent]
        fitness_values = self.fitness_evaluator.evaluate_multiple(non_silent_individuals)
        for i, ind in enumerate(non_silent_individuals):
            ind.set_fitness(fitness_values[i])

        if self.args.fitness == 'similarity':
            for ind in non_silent_individuals:
                ind.similarity = ind.genotype.GetFitness()
        else:
            similarity_values = self.similarity_evaluator.evaluate_multiple(non_silent_individuals)
            for i, ind in enumerate(non_silent_individuals):
                ind.similarity = similarity_values[i]

    def final_clean_up(self):
        self.analyzer.final_clean_up()
