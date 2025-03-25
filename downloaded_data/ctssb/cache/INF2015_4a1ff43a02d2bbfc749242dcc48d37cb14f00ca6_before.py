import inspect
from datetime import date
from heapq import heappush

from builder import rules
from builder.rules.rule import Rule
from builder.exceptions import NotAllowed


class Quote(object):
    def __init__(self, car, driver, contrat):
        self.car = car
        self.driver = driver
        self.contrat = contrat
        self.montant = 0

        self.rules = []
        for name, module in inspect.getmembers(rules, inspect.ismodule):
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, Rule) and obj != Rule:
                    rule = obj(self)
                    if not hasattr(rule, 'PRIORITY'):
                        priority = 0
                    else:
                        priority = rule.PRIORITY
                    heappush(self.rules, (priority, rule))

    def build_quote(self):
        self.assurable = True
        try:
            for _, rule in self.rules:
                rule.apply_rules()
        except NotAllowed:
            self.montant = 0
            self.assurable = False

    @property
    def montant_mensuel(self):
      if self.assurable > 0:
        return round(((self.montant * 1.05) / 12) / 100, 2)


    @property
    def montant_annuel(self):
      if self.assurable:
        return round(self.montant / 100, 2)

class Contrat(object):
    pass


class Driver(object):
    @property
    def age(self):
        today = date.today()
        birthday = self.date_de_naissance

        if today.month < birthday.month or \
          (today.month == birthday.month and today.day < birthday.day):
            return today.year - birthday.year - 1
        else:
            return today.year - birthday.year

    @property
    def years_experience(self):
        today = date.today()
        birthday = self.date_fin_cours_de_conduite

        if today.month < birthday.month or \
          (today.month == birthday.month and today.day < birthday.day):
            return today.year - birthday.year - 1
        else:
            return today.year - birthday.year



class Car(object):
    pass
