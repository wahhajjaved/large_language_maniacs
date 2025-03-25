"""
Module for defining fitness normalizers.

Fitness normalizers are classes which are responsible for normalizing
the fitness values in a :class:`Population`. They analyze the
:attr:`fitness` values across the entire population and update them.
After :meth:`~FitnessNormalizer.normalize` is run, every
:class:`.Molecule` in the population must hold a positive, non-zero
:class:`float` in its :attr:`fitness` attribute. However, before
:meth:`~FitnessNormalizer.normalize` the values in the :attr:`fitness`
attribute can be any Python object. It is the job of the
:class:`FitnessNormalizer` to convert these into positive, non-zero
:class:`float`.

To see how :class:`FitnessNormalizer` can be used, look at the
documention of the classes which inherit it, for example
:class:`Power`, :class:`Sum` :class:`ScaleByMean`. In addition,
multiple :class:`FitnessNormalizer` can be chained using
:meth:`.Sequence.normalize`.

.. _`adding fitness normalizers`:

Extending stk: Making new fitness normalizers.
----------------------------------------------

A new class inheriting :class:`FitnessNormalizer` must be made.
The class must define a :meth:`~FitnessNormalizer.normalize` method,
which takes one argument, which is a :class:`.Population` of
:class:`.Molecule`.


"""

import numpy as np
import logging
from functools import wraps

from ...utilities import dedupe


logger = logging.getLogger(__name__)


def _handle_failed_molecules(normalize):
    """
    Decorates :meth:`~FitnessNormalizer.normalize` methods.

    This decorator makes :meth:`~FitnessNormalizer.normalize` methods
    set the fitness of molecules with a :attr:`fitness` of ``None`` to
    half the minimum fitness in the population, if
    :attr:`handle_failed` is ``True```.

    Parameters
    ----------
    normalize : class:`function`
        The :meth:`~FitnessNormalizer.normalize` method to decorate.

    Returns
    -------
    :class:`function`
        The decorated :meth:`~FitnessNormalizer.normalize` method.

    """

    @wraps(normalize)
    def inner(self, population):
        valid_pop = population.init_copy(population)
        population.remove_members(
            lambda m: m.fitness is None
        )
        r = normalize(self, valid_pop)

        if self.handle_failed:
            minimum_fitness = min(m.fitness for m in valid_pop)
            for member in population:
                if member.fitness is None:
                    member.fitness = minimum_fitness/2
        return r

    return inner


def _dedupe(normalize):
    """
    Makes sure that duplicates are removed before normalization.

    Parameters
    ----------
    normalize : class:`function`
        The :meth:`~FitnessNormalizer.normalize` method to decorate.

    Returns
    -------
    :class:`function`
        The decorated :meth:`~FitnessNormalizer.normalize` method.

    """

    @wraps(normalize)
    def inner(self, population):
        cls = population.__class__
        return normalize(self, cls(*dedupe(population)))

    return inner


class FitnessNormalizer:
    """
    Normalizes fitness values across a :class:`.Population`.

    Attributes
    ----------
    handle_failed : :class:`bool`
        If ``True``, the normalized :attr:`fitness` value of molecules
        with a :attr:`fitness` value of ``None`` is half the minimum
        normalized fitness value in the population. If ``False`` the
        normalization keeps ``None`` in the :attr:`fitness` attribute
        of molecules.

    """

    def __init__(self):
        self.handle_failed = True

    def __init_subclass__(cls, **kwargs):
        cls.normalize = _dedupe(cls.normalize)
        cls.normalize = _handle_failed_molecules(cls.normalize)
        return super().__init_subclass__(**kwargs)

    def normalize(self, population):
        """
        Normalizes the fitness values in `population`.

        Parameters
        ----------
        population : :class:`.Population`
            A :class:`.Population` of molecules whose fitness values
            should be normalized.

        Returns
        -------
        None : :class:`NoneType`
            The :attr:`fitness` attributes of the molecules in
            `population` are modified in place.

        """

        raise NotImplementedError()


class NullFitnessNormalizer(FitnessNormalizer):
    """
    Does nothing.

    """

    def normalize(self, population):
        """
        Does not normalize the fitness values in `population`.

        Parameters
        ----------
        population : :class:`.Population`
            A :class:`.Population` of molecules whose fitness values
            are not normalized.

        Returns
        -------
        None : :class:`NoneType`
            This method does nothing.

        """

        return


class NormalizerSequence(FitnessNormalizer):
    """
    Applies a sequence of normalizers in sequence.

    Attributes
    ----------
    normalizers : :class:`tuple` of :class:`FitnessNormalizer`
        The normalizers which get applied in sequence by
        :meth:`normalize`.

    Examples
    --------
    .. code-block:: python

        # Make the normalizer.
        sequence = stk.NormalizerSequence(
            stk.Power(2),
            stk.Sum()
        )

        # Make a population of molecules.
        mol1 = StructUnit(...)
        mol2 = Cage(...)
        mol3 = Polymer(...)
        pop = stk.Population(mol1, mol2, mol3)

        # Set the fitness values.
        mol1.fitness = [1, 2, 3]
        mol2.fitness = [4, 5, 6]
        mol3.fitness = [7, 8, 9]

        # Apply the normalizer.
        sequence.normalize(pop)

        # mol1.fitness is now 14.
        # mol2.fitness is now 77.
        # mol3.fitness is now 194.


    """

    def __init__(self, *normalizers):
        """
        Initializes a :class:`NormalizerSequence` instance.

        Parameters
        ----------
        normalizers : :class:`tuple` of :class:`FitnessNormalizer`
            The normalizers which get applied in sequence by
            :meth:`normalize`.

        """

        self.normalizers = normalizers
        super().__init__()

    def normalize(self, population):
        """
        Normalizes the fitness values in `population`.

        Parameters
        ----------
        population : :class:`.Population`
            A :class:`.Population` of molecules whose fitness values
            should be normalized.

        Returns
        -------
        None : :class:`NoneType`
            The :attr:`fitness` attributes of the molecules in
            `population` are modified in place.
        """

        for normalizer in self.normalizers:
            logger.info(f'Using {normalizer.__class__.__name__}.')
            normalizer.normalize(population)


class Power(FitnessNormalizer):
    """
    Raises fitness values to some power.

    This works for cases where the :attr:`fitness` is single
    :class:`float` and where it is :class:`list` of :class:`float`.

    Attributes
    ----------
    power : :class:`float` or :class:`list` of :class:`float`
        The power to raise each :attr:`fitness` value to. Can be
        a single number or multiple numbers.

    Examples
    --------
    Raising a :attr:`fitness` value by some power.

    .. code-block:: python

        # Create the molecules and give them some arbitrary fitness.
        # Normally the fitness would be set by the fitness() method of
        # some a fitness calculator.
        mol1 = StructUnit(...)
        mol1.fitness = 1

        mol2 = Cage(...)
        mol2.fitness = 2

        mol3 = Polymer(...)
        mol3.fitness = 3

        # Place the molecules in a Population.
        pop = Population(mol1, mol2, mol3)

        # Create the normalizer.
        power = Power(2)

        # Normalize the fitness values.
        power.normalize(pop)

        # mol1.fitness is now 1.
        # mol2.fitness is now 4.
        # mol3.fitness is now 9

    Raising a :attr:`fitness` vector by some power.

    .. code-block:: python

        # Create the molecules and give them some arbitrary fitness
        # vectors.
        # Normally the fitness would be set by the fitness() method of
        # some a fitness calculator.
        mol1 = StructUnit(...)
        mol1.fitness = [1, 2, 3]

        mol2 = Cage(...)
        mol2.fitness = [4, 5, 6]

        mol3 = Polymer(...)
        mol3.fitness = [7, 8, 9]

        # Place the molecules in a Population.
        pop = Population(mol1, mol2, mol3)

        # Create the normalizer.
        power = Power(2)

        # Normalize the fitness values.
        power.normalize(pop)

        # mol1.fitness is now [1, 4, 9].
        # mol2.fitness is now [16, 25, 36].
        # mol3.fitness is now [49, 64, 81]

    Raising a :attr:`fitness` vector by different powers.

    .. code-block:: python

        # Create the molecules and give them some arbitrary fitness
        # vectors.
        # Normally the fitness would be set by the fitness() method of
        # some a fitness calculator.
        mol1 = StructUnit(...)
        mol1.fitness = [1, 2, 3]

        mol2 = Cage(...)
        mol2.fitness = [4, 5, 6]

        mol3 = Polymer(...)
        mol3.fitness = [7, 8, 9]

        # Place the molecules in a Population.
        pop = Population(mol1, mol2, mol3)

        # Create the normalizer.
        power = Power([1, 2, 3])

        # Normalize the fitness values.
        power.normalize(pop)

        # mol1.fitness is now [1, 4, 27].
        # mol2.fitness is now [4, 25, 216].
        # mol3.fitness is now [7, 64, 729]

    """

    def __init__(self, power):
        """
        Initializes a :class:`Power` instance.

        Parameters
        ----------
        power : :class:`float` or :class:`list` of :class:`float`
            The power to raise each :attr:`fitness` value to. Can be
            a single number or multiple numbers.

        """

        self.power = power
        super().__init__()

    def normalize(self, population):
        """
        Normalizes the fitness values in `population`.

        Parameters
        ----------
        population : :class:`.Population`
            A :class:`.Population` of molecules whose fitness values
            should be normalized.

        Returns
        -------
        None : :class:`NoneType`
            The :attr:`fitness` attributes of the molecules in
            `population` are modified in place.

        """

        for mol in population:
            mol.fitness = np.float_power(mol.fitness, self.power)


class Multiply(FitnessNormalizer):
    """
    Multiplies the fitness value by some coefficent.

    Attributes
    ----------
    coefficent : :class:`float` or :class:`list` of :class:`float`
        The cofficients to multiply each :attr:`fitness` value by. Can
        be a single number or multiple numbers.

    Examples
    --------
    Multiplying a :attr:`fitness` value by a coefficent.

    .. code-block:: python

        # Create the molecules and give them some arbitrary fitness.
        # Normally the fitness would be set by the fitness() method of
        # some a fitness calculator.
        mol1 = StructUnit(...)
        mol1.fitness = 1

        mol2 = Cage(...)
        mol2.fitness = 2

        mol3 = Polymer(...)
        mol3.fitness = 3

        # Place the molecules in a Population.
        pop = Population(mol1, mol2, mol3)

        # Create the normalizer.
        multiply = Multiply(2)

        # Normalize the fitness values.
        multiply.normalize(pop)

        # mol1.fitness is now 2.
        # mol2.fitness is now 4.
        # mol3.fitness is now 6

    Multiplying a :attr:`fitness` vector by some coefficent.

    .. code-block:: python

        # Create the molecules and give them some arbitrary fitness
        # vectors.
        # Normally the fitness would be set by the fitness() method of
        # some a fitness calculator.
        mol1 = StructUnit(...)
        mol1.fitness = [1, 2, 3]

        mol2 = Cage(...)
        mol2.fitness = [4, 5, 6]

        mol3 = Polymer(...)
        mol3.fitness = [7, 8, 9]

        # Place the molecules in a Population.
        pop = Population(mol1, mol2, mol3)

        # Create the normalizer.
        multiply = Multiply(2)

        # Normalize the fitness values.
        multiply.normalize(pop)

        # mol1.fitness is now [2, 4, 6].
        # mol2.fitness is now [8, 10, 12].
        # mol3.fitness is now [14, 16, 18]

    Multiplying a :attr:`fitness` vector by different coefficents.

    .. code-block:: python

        # Create the molecules and give them some arbitrary fitness
        # vectors.
        # Normally the fitness would be set by the fitness() method of
        # some a fitness calculator.
        mol1 = StructUnit(...)
        mol1.fitness = [1, 2, 3]

        mol2 = Cage(...)
        mol2.fitness = [4, 5, 6]

        mol3 = Polymer(...)
        mol3.fitness = [7, 8, 9]

        # Place the molecules in a Population.
        pop = Population(mol1, mol2, mol3)

        # Create the normalizer.
        multiply = Multiply([1, 2, 3])

        # Normalize the fitness values.
        multiply.normalize(pop)

        # mol1.fitness is now [1, 4, 9].
        # mol2.fitness is now [4, 10, 18].
        # mol3.fitness is now [7, 16, 27]

    """

    def __init__(self, coefficient):
        """
        Initializes a :class:`Multiply` instance.

        Parameters
        ----------
        coefficent : :class:`float` or :class:`list` of :class:`float`
            The cofficients each :attr:`fitness` value by. Can be
            a single number or multiple numbers.

        """

        self.coefficient = coefficient
        super().__init__()

    def normalize(self, population):
        """
        Normalizes the fitness values in `population`.

        Parameters
        ----------
        population : :class:`.Population`
            A :class:`.Population` of molecules whose fitness values
            should be normalized.

        Returns
        -------
        None : :class:`NoneType`
            The :attr:`fitness` attributes of the molecules in
            `population` are modified in place.

        """

        for mol in population:
            mol.fitness = np.multiply(mol.fitness, self.coefficient)


class Sum(FitnessNormalizer):
    """
    Sums the values in a :class:`list`.

    Examples
    --------
    .. code-block:: python

        # Create the molecules and give them some arbitrary fitness
        # vectors.
        # Normally the fitness would be set by the fitness() method of
        # some a fitness calculator.
        mol1 = StructUnit(...)
        mol1.fitness = [1, 2, 3]

        mol2 = Cage(...)
        mol2.fitness = [4, 5, 6]

        mol3 = Polymer(...)
        mol3.fitness = [7, 8, 9]

        # Place the molecules in a Population.
        pop = Population(mol1, mol2, mol3)

        # Create the normalizer.
        sum_normalizer = Sum()

        # Normalize the fitness values.
        sum_normalizer.normalize(pop)

        # mol1.fitness is now 6.
        # mol2.fitness is now 15.
        # mol3.fitness is now 24.

    """

    def normalize(self, population):
        """
        Normalizes the fitness values in `population`.

        Parameters
        ----------
        population : :class:`.Population`
            A :class:`.Population` of molecules whose fitness values
            should be normalized.

        Returns
        -------
        None : :class:`NoneType`
            The :attr:`fitness` attributes of the molecules in
            `population` are modified in place.

        """

        for mol in population:
            mol.fitness = sum(mol.fitness)


class ScaleByMean(FitnessNormalizer):
    """
    Divides fitness values by the population mean.

    While this function can be used if the :attr:`fitness` attribute
    of each :class:`.Molecule` in the :class:`.Population` is a single
    number it is most useful when :attr:`fitness` is a :class:`list`
    of numbers. In this case, it is necessary to somehow combine the
    numbers so that a single :attr:`fitness` value is produced.
    For example, take a :attr:`fitness` vector holding the properties
    ``[energy, diameter, num_atoms]``. For a given molecule these
    numbers may be something like ``[200,000, 12, 140]``. If we were
    to sum these numbers, the energy term would dominate the final
    fitness value. In order to combine these numbers we can divide them
    by the population averages. For example, if the average energy
    of molecules in the population is ``300,000`` the average diameter
    is ``10`` and the average number of atoms is ``70`` then the
    fitness vector would be scaled to ``[0.5, 1.2, 2]``. These
    numbers are now of a similar magnitude and can be some to give a
    reasonable value. After scaling each parameter represents how
    much better than the population average each property value is.
    In essence we have removed the units from each parameter.

    Examples
    --------
    Scale fitness values.

    .. code-block:: python

        # Create the molecules and give them some arbitrary fitness
        # vectors.
        # Normally the fitness would be set by the fitness() method of
        # some a fitness calculator.
        mol1 = StructUnit(...)
        mol1.fitness = 1

        mol2 = Cage(...)
        mol2.fitness = 2

        mol3 = Polymer(...)
        mol3.fitness = 3

        # Place the molecules in a Population.
        pop = Population(mol1, mol2, mol3)

        # Create the normalizer.
        mean_scaler = ScaleByMean()

        # Normalize the fitness values.
        mean_scaler.normalize(pop)

        # mol1.fitness is now 0.5.
        # mol2.fitness is now 1.
        # mol3.fitness is now 1.5.

    Scale fitness vectors.

    .. code-block:: python

        # Create the molecules and give them some arbitrary fitness
        # vectors.
        # Normally the fitness would be set by the fitness() method of
        # some a fitness calculator.
        mol1 = StructUnit(...)
        mol1.fitness = [1, 10, 100]

        mol2 = Cage(...)
        mol2.fitness = [2, 20, 200]

        mol3 = Polymer(...)
        mol3.fitness = [3, 30, 300]

        # Place the molecules in a Population.
        pop = Population(mol1, mol2, mol3)

        # Create the normalizer.
        mean_scaler = ScaleByMean()

        # Normalize the fitness values.
        mean_scaler.normalize(pop)

        # mol1.fitness is now [0.5, 0.5, 0.5].
        # mol2.fitness is now [1, 1, 1].
        # mol3.fitness is now [1.5, 1.5, 1.5].

    """

    def normalize(self, population):
        """
        Normalizes the fitness values in `population`.

        Parameters
        ----------
        population : :class:`.Population`
            A :class:`.Population` of molecules whose fitness values
            should be normalized.

        Returns
        -------
        None : :class:`NoneType`
            The :attr:`fitness` attributes of the molecules in
            `population` are modified in place.

        """

        mean = population.mean(lambda x: x.fitness)
        logger.debug(f'Means used in ScaleByMean: {mean}')

        for mol in population:
            mol.fitness = np.divide(mol.fitness, mean)


class ShiftUp(FitnessNormalizer):
    """
    Shifts negative values to be positive.

    Assume you have a fitness vector, where each number represents
    a different property of the molecule

    .. code-block:: python

        mol.fitness = [1, -10, 1]

    One way to convert the fitness array into a fitness value is
    by summing the elements, and the result in this case would be
    ``-8``. Clearly this doesn't work, because the resulting fitness
    value is not a positive number. To fix this, the ``-10`` should be
    shifted to a positive value.

    This :class:`FitnessNormalizer` find the minimum value of each
    property across the entire population, and for properties where
    this minimum value is less than ``0``, shifts up the property value
    for every molecule in the population, so that the minimum value is
    ``1``.

    For example, take a population with the fitness vectors

    .. code-block:: python

        mol1.fitness = [1, -5, 5]
        mol2.fitness = [3, -10, 2]
        mol3.fitness = [2, 20, 1]

    After normalization fitness vectors will be.

    .. code-block:: python

        mol1.fitness  # [1, 6, 5]
        mol2.fitness  # [3, 1, 2]
        mol3.fitness  # [2, 31, 1]

    This :class:`FitnessNormalizer` also works when the :attr:`fitness`
    is a single value.

    Parameters
    ----------
    indices : :class:`list` of :class:`int`
        This holds the indices of elements in the
        :attr:`~.MacroMolecule.fitness` array which should be
        shifted.

    Examples
    --------
    .. code-block:: python

        # Create the molecules and give them some arbitrary fitness
        # vectors.
        # Normally the fitness would be set by the fitness() method of
        # some a fitness calculator.
        mol1 = StructUnit(...)
        mol1.fitness = [1, -2, 3]

        mol2 = Cage(...)
        mol2.fitness = [4, 5, -6]

        mol3 = Polymer(...)
        mol3.fitness = [7, 8, 9]

        # Place the molecules in a Population.
        pop = Population(mol1, mol2, mol3)

        # Create the normalizer.
        shifter = ShiftUp([1, 2, 3])

        # Normalize the fitness values.
        shifter.normalize(pop)

        # mol1.fitness is now [1, 1, 10].
        # mol2.fitness is now [4, 8, 1].
        # mol3.fitness is now [7, 11, 16]

    """

    def normalize(self, population):
        """
        Normalizes the fitness values in `population`.

        Parameters
        ----------
        population : :class:`.Population`
            A :class:`.Population` of molecules whose fitness values
            should be normalized.

        Returns
        -------
        None : :class:`NoneType`
            The :attr:`fitness` attributes of the molecules in
            `population` are modified in place.

        """

        # Get all the fitness arrays in a matrix.
        fmat = np.array([x.fitness for x in population])

        # Get the minimum values of each element in the population.
        mins = np.min(fmat, axis=0)
        # Convert all the ones which are not to be shifted to 0 and
        # multiply the which are to be shifted by 1.01.
        is_array = isinstance(mins, np.ndarray)
        if not is_array:
            mins = np.array([mins])
        shift = np.zeros(len(mins))
        for i, min_ in enumerate(mins):
            if min_ <= 0:
                shift[i] = 1 - min_

        for mol in population:
            mol.fitness += shift
