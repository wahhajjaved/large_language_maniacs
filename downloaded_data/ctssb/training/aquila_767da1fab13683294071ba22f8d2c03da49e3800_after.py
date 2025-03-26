from watersamples.utils import FIRST_SOURCE_CLASS, UNFIT_SOURCE_CLASS, SECOND_SOURCE_CLASS, THIRD_SOURCE_CLASS


class Classifier:
    @classmethod
    def smell_or_taste(cls, value):
        if value <= 2:
            return FIRST_SOURCE_CLASS
        return UNFIT_SOURCE_CLASS

    @classmethod
    def smell_20_celsium(cls, value):
        return cls.smell_or_taste(value)

    @classmethod
    def smell_60_celsium(cls, value):
        return cls.smell_or_taste(value)

    @classmethod
    def aftertaste(cls, value):
        return cls.smell_or_taste(value)

    @classmethod
    def dry_residue(cls, value):
        if value <= 1500:
            return FIRST_SOURCE_CLASS
        return UNFIT_SOURCE_CLASS

    @classmethod
    def rigidity(cls, value):
        if value <= 10:
            return FIRST_SOURCE_CLASS
        return UNFIT_SOURCE_CLASS

    @classmethod
    def chlorides(cls, value):
        if value <= 350:
            return FIRST_SOURCE_CLASS
        return UNFIT_SOURCE_CLASS

    @classmethod
    def sulphates(cls, value):
        if value <= 500:
            return FIRST_SOURCE_CLASS
        return UNFIT_SOURCE_CLASS

    @classmethod
    def nitrates(cls, value):
        if value <= 45:
            return FIRST_SOURCE_CLASS
        return UNFIT_SOURCE_CLASS

    @classmethod
    def manganese(cls, value):
        if value > 2.0:
            return UNFIT_SOURCE_CLASS
        if value > 1.0:
            return THIRD_SOURCE_CLASS
        if value > 0.1:
            return SECOND_SOURCE_CLASS
        return FIRST_SOURCE_CLASS

    @classmethod
    def color(cls, value):
        if value < 50:
            return FIRST_SOURCE_CLASS
        return UNFIT_SOURCE_CLASS

    @classmethod
    def temperature(cls, value):
        if value <= 12:
            return FIRST_SOURCE_CLASS
        return UNFIT_SOURCE_CLASS

    @classmethod
    def ph(cls, value):
        if value <= 9.0:
            return FIRST_SOURCE_CLASS
        return UNFIT_SOURCE_CLASS

    @classmethod
    def iron_overall(cls, value):
        if value > 20:
            return UNFIT_SOURCE_CLASS
        if value > 10:
            return THIRD_SOURCE_CLASS
        if value > 0.3:
            return SECOND_SOURCE_CLASS
        return FIRST_SOURCE_CLASS

    @classmethod
    def fluorine(cls, value):
        if value > 5.0:
            return UNFIT_SOURCE_CLASS
        if value > 1.5:
            return THIRD_SOURCE_CLASS
        return FIRST_SOURCE_CLASS
