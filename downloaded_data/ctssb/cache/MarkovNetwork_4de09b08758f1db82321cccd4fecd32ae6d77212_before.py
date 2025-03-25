# -*- coding: utf-8 -*-

"""
Copyright 2016 Randal S. Olson

Permission is hereby granted, free of charge, to any person obtaining a copy of this software
and associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial
portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""

from __future__ import print_function
import numpy as np


class MarkovNetwork(object):

    """A Markov Network for neural computing."""

    max_markov_gate_inputs = 4
    max_markov_gate_outputs = 4

    def __init__(self, num_input_states, num_memory_states, num_output_states, seed_num_markov_gates=4, probabilistic=True, genome=None):
        """Sets up a Markov Network

        Parameters
        ----------
        num_input_states: int
            The number of input states in the Markov Network
        num_memory_states: int
            The number of internal memory states in the Markov Network
        num_output_states: int
            The number of output states in the Markov Network
        seed_num_markov_gates: int (default: 4)
            The number of Markov Gates with which to seed the Markov Network
            It is important to ensure that randomly-generated Markov Networks have at least a few Markov Gates to begin with
            May sometimes result in fewer Markov Gates if the Markov Gates are randomly seeded in the same location
        probabilistic: bool (default: True)
            Flag indicating whether the Markov Gates are probabilistic or deterministic
        genome: array-like (default=None)
            An array representation of the Markov Network to construct
            All values in the array must be integers in the range [0, 255]
            If None, then a random Markov Network will be generated

        Returns
        -------
        None

        """
        self.num_input_states = num_input_states
        self.num_memory_states = num_memory_states
        self.num_output_states = num_output_states
        self.states = np.zeros(num_input_states + num_memory_states + num_output_states, dtype=np.bool)
        self.markov_gates = []
        self.markov_gate_input_ids = []
        self.markov_gate_output_ids = []

        if genome is None:
            self.genome = np.random.randint(0, 256, np.random.randint(10000, 20000)).astype(np.uint8)

            # Seed the random genome with seed_num_markov_gates Markov Gates
            for _ in range(seed_num_markov_gates):
                start_index = np.random.randint(0, int(len(self.genome) * 0.8))
                self.genome[start_index] = 42
                self.genome[start_index + 1] = 213
        else:
            self.genome = np.array(genome, dtype=np.uint8)

        self._setup_markov_network(probabilistic)

    def _setup_markov_network(self, probabilistic):
        """Interprets the internal genome into the corresponding Markov Gates

        Parameters
        ----------
        probabilistic: bool
            Flag indicating whether the Markov Gates are probabilistic or deterministic

        Returns
        -------
        None

        """
        for index_counter in range(self.genome.shape[0] - 1):
            # Sequence of 42 then 213 indicates a new Markov Gate
            if self.genome[index_counter] == 42 and self.genome[index_counter + 1] == 213:
                internal_index_counter = index_counter + 2

                # Determine the number of inputs and outputs for the Markov Gate
                num_inputs = (self.genome[internal_index_counter] % MarkovNetwork.max_markov_gate_inputs) + 1
                internal_index_counter += 1
                num_outputs = (self.genome[internal_index_counter] % MarkovNetwork.max_markov_gate_outputs) + 1
                internal_index_counter += 1

                # Make sure that the genome is long enough to encode this Markov Gate
                if (internal_index_counter +
                        (MarkovNetwork.max_markov_gate_inputs + MarkovNetwork.max_markov_gate_outputs) +
                        (2 ** num_inputs) * (2 ** num_outputs)) > self.genome.shape[0]:
                    continue

                # Determine the states that the Markov Gate will connect its inputs and outputs to
                input_state_ids = self.genome[internal_index_counter:internal_index_counter + MarkovNetwork.max_markov_gate_inputs][:num_inputs]
                input_state_ids = np.mod(input_state_ids, self.states.shape[0])
                internal_index_counter += MarkovNetwork.max_markov_gate_inputs

                output_state_ids = self.genome[internal_index_counter:internal_index_counter + MarkovNetwork.max_markov_gate_outputs][:num_outputs]
                output_state_ids = np.mod(output_state_ids, self.states.shape[0])
                internal_index_counter += MarkovNetwork.max_markov_gate_outputs

                self.markov_gate_input_ids.append(input_state_ids)
                self.markov_gate_output_ids.append(output_state_ids)

                # Interpret the probability table for the Markov Gate
                markov_gate = np.copy(self.genome[internal_index_counter:internal_index_counter + (2 ** num_inputs) * (2 ** num_outputs)])
                markov_gate = markov_gate.reshape((2 ** num_inputs, 2 ** num_outputs))

                if probabilistic:  # Probabilistic Markov Gates
                    markov_gate = markov_gate.astype(np.float64) / np.sum(markov_gate, axis=1, dtype=np.float64)[:, None]
                else:  # Deterministic Markov Gates
                    row_max_indices = np.argmax(markov_gate, axis=1)
                    markov_gate[:, :] = 0
                    markov_gate[np.arange(len(row_max_indices)), row_max_indices] = 1

                self.markov_gates.append(markov_gate)

    def activate_network(self, num_activations=1):
        """Activates the Markov Network

        Parameters
        ----------
        num_activations: int (default: 1)
            The number of times the Markov Network should be activated

        Returns
        -------
        None

        """
        original_input_values = np.copy(self.states[:self.num_input_states])
        for _ in range(num_activations):
            for markov_gate, mg_input_ids, mg_output_ids in zip(self.markov_gates, self.markov_gate_input_ids, self.markov_gate_output_ids):
                # Determine the input values for this Markov Gate
                mg_input_values = self.states[mg_input_ids]
                mg_input_index = int(''.join([str(int(val)) for val in mg_input_values]), base=2)

                # Determine the corresponding output values for this Markov Gate
                roll = np.random.uniform()
                rolling_sums = np.cumsum(markov_gate[mg_input_index, :], dtype=np.float64)
                mg_output_index = np.where(rolling_sums >= roll)[0][0]
                mg_output_values = np.array(list(np.binary_repr(mg_output_index, width=self.num_output_states)), dtype=np.uint8)
                self.states[mg_output_ids] = mg_output_values

            self.states[:self.num_input_states] = original_input_values

    def update_input_states(self, input_values):
        """Updates the input states with the provided inputs

        Parameters
        ----------
        input_values: array-like
            An array of integers containing the inputs for the Markov Network
            len(input_values) must be equal to num_input_states

        Returns
        -------
        None

        """
        if len(input_values) != self.num_input_states:
            raise ValueError('Invalid number of input values provided')

        self.states[:self.num_input_states] = input_values

    def get_output_states(self):
        """Returns an array of the current output state's values

        Parameters
        ----------
        None

        Returns
        -------
        output_states: array-like
            An array of the current output state's values

        """
        return self.states[-self.num_output_states:]
