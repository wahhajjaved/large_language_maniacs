import math
from express.properties.scalar import ScalarProperty


class PNorm(ScalarProperty):
    """
    p-norm property class.
    """

    def __init__(self, name, raw_data, *args, **kwargs):
        super(PNorm, self).__init__(name, raw_data, *args, **kwargs)
        self.degree = kwargs["degree"]
        ratios = self.raw_data["elemental_ratios"].values()
        self.value = math.pow(sum((math.pow(v, self.degree) for v in ratios)), 1.0 / self.degree) if self.degree else len(ratios)

    def _serialize(self):
        return {
            'name': self.name,
            'value': self.value,
            "degree": self.degree
        }
