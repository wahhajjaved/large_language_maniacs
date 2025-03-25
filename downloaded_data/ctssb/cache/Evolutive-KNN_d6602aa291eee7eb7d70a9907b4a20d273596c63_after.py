from sklearn.neighbors import KNeighborsClassifier
import numpy as np
from individual import Individual
import random

class EvolutiveKNN:
    """Implementation of an evolutive version of KNN.
    This class finds the best K and the best weigths for a given training set
    """
    """
    EvolutiveKNN initializer

    Parameters:
        training_examples: Array of features, each feature is an array of floats
            example: [[1, 2, 3, 1], [1, 4, 2, 8], [1, 1, 2, 1]]
        training_labels: Array of integers that are the labels for each feature.
            example: [0, 1, 0]
        Observation: the first label is the class of the first feature, and so on.
    
    Usage:
        classifier = EvolutiveKNN([[1, 2, 3, 1], [1, 4, 2, 8], [1, 1, 2, 1]], [0, 1, 0])
    """
    def __init__(self, training_examples, training_labels, ts_size = 0.5):
        test_size = int(ts_size * len(training_labels))
        self._create_test(
            np.array(training_examples), np.array(training_labels), test_size
        )

    """This method is responsible for training the evolutive KNN based on the
    given parameters

    Parameters:
        population_size: The size of the population.
        mutation_rate: Chance of occuring a mutation on a individual.
        max_generations: Stopping criteria, maximum number of generations.
        max_accuracy: Stopping criteria, if an idividual have an accuracy bigger than max_accuracy the execution stops.
        max_k: Maximum number of neighbors, if no max_k is provided the maximum possible is used.
        max_weight: Maximum possible weight.
        elitism_rate: Elitism rate, percentage of best individuals that will be passed to another generation.
        tournament_size: The percentage of the non-elite population that will be selected at each tournament.
    """
    def train(self, population_size=5, mutation_rate=0.02, max_generations=50, max_accuracy=1.0, max_k=None, max_weight=10, elitism_rate=0.1, tournament_size=0.25):
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.max_generations = max_generations
        self.max_accuracy = max_accuracy
        self.max_k = max_k
        self.max_weight = max_weight
        self.elitism_rate = elitism_rate
        self.elitism_real_value = int(self.elitism_rate * self.population_size)
        self.tournament_size = tournament_size
        self.global_best = Individual(1, [1])
        self._train()

    def _train(self):
        population = self._start_population()
        self._calculate_fitness_of_population(population)
        generations = 0
        print generations
        while not self._should_stop(generations):
            generations += 1
            print generations
            population = self._create_new_population(population)
            self._calculate_fitness_of_population(population)

    def _should_stop(self, generations):
        best_fitness = self.global_best.fitness
        if self.max_generations < generations or best_fitness >= self.max_accuracy:
            return True
        return False

    def _create_new_population(self,old_population):
        sorted_old_population = sorted(
            old_population,
            key=lambda individual: individual.fitness,
            reverse=True
        )
        elite = self._get_elite(sorted_old_population)
        non_elite = self._get_non_elite(sorted_old_population)
        new_population = elite
        while len(new_population) < self.population_size:
            new_population.append(
                self._generate_child(non_elite)
            )
        return new_population

    def _generate_child(self, population):
        parent1 = self._tournament(population)
        parent2 = self._tournament(population)
        return self._crossover(parent1, parent2)

    def _tournament(self, population):
        number_of_individuals = int(len(population) * self.tournament_size)
        selected = random.sample(
            xrange(number_of_individuals), number_of_individuals
        )
        best = sorted(selected)[0]
        return population[best]

    def _crossover(self, parent1, parent2):
        k1 = parent1.k
        k2 = parent2.k
        k = self._random_between(k1, k2)
        colaboration1 = int(k * (k1/(k1 + k2)))
        colaboration2 = int(k * (k2/(k1 + k2)))
        weights = parent1.weights[:colaboration1]
        weights = weights + parent2.weights[colaboration2:]
        mutate = random.uniform(0, 1)
        if mutate < self.mutation_rate:
            weights = self._mutate_weights(weights)
        return Individual(k, weights)

    def _random_between(self, number1, number2):
        if random.randint(0,1) == 0:
            result = number1
        else:
            result = number2
        return result

    def _mutate_weights(self, weights):
        mutated = weights
        index = random.randint(0, len(weights) - 1)
        mutated[index] = random.randint(0, self.max_weight)
        return mutated
    
    def _get_elite(self, population):
        return population[:self.elitism_real_value]
    
    def _get_non_elite(self, population):
        return population[self.elitism_real_value:]

    def _start_population(self):
        max_k = self.max_k
        if max_k is None: max_k = len(self.training_labels)
        population = []
        for _ in xrange(self.population_size):
            k = random.randint(1, max_k)
            weights = [
                random.choice(range(self.max_weight)) for _ in xrange(k)
            ]
            population.append(Individual(k, weights))
        return population

    def _calculate_fitness_of_population(self, population):
        for index, element in enumerate(population):
            # print "element: ", index
            self._calculate_fitness_of_individual(element)
            if self.global_best.fitness < element.fitness:
                self.global_best = element

    def _calculate_fitness_of_individual(self, element):

        def _element_weights(distances):
            return element.weights

        kneigh = KNeighborsClassifier(n_neighbors=element.k, weights=_element_weights)
        kneigh.fit(self.training_examples, self.training_labels)
        element.fitness = kneigh.score(self.test_examples, self.test_labels)
        # print '-------'
        # print element.k
        # print element.weights
        # print element.fitness
        # print '-------'

    def _create_test(self, tr_examples, tr_labels, test_size):
        self.training_examples = []
        self.training_labels = [] 
        self.test_examples = []
        self.test_labels = []

        test_indexes = random.sample(xrange(len(tr_labels)), test_size)

        self.test_examples = tr_examples[test_indexes]
        self.test_labels = tr_labels[test_indexes]
        for index in xrange(len(tr_labels)):
            if index not in test_indexes:
                self.training_examples.append(tr_examples[index])
                self.training_labels.append(tr_labels[index])
        self.training_examples = np.array(self.training_examples)
        self.training_labels = np.array(self.training_labels)