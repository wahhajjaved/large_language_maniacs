import random

import math
from django.core.urlresolvers import reverse
from django.db import models, transaction
from django.contrib.auth.models import User
from django.forms.models import model_to_dict

from name_generator.name_generator import NameGenerator


class World(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    initialized = models.BooleanField(default=False)
    current_turn = models.IntegerField(default=0)

    def get_violence_monopolies(self):
        return self.organization_set.filter(violence_monopoly=True)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('world:world', kwargs={'world_id': self.id})

    @transaction.atomic
    def initialize(self):
        if self.initialized:
            raise Exception("World {} already initialized!".format(self))
        name_generator = NameGenerator()
        for tile in self.tile_set.all():
            tile.initialize(name_generator)
        self.initialized = True
        self.save()


class Region(models.Model):
    class Meta:
        unique_together = (
            ("world", "name"),
        )

    name = models.CharField(max_length=100)
    world = models.ForeignKey(World)

    def __str__(self):
        return self.name


class Tile(models.Model):
    PLAINS = 'plains'
    FOREST = 'forest'
    SHORE = 'shore'
    DEEPSEA = 'deepsea'
    MOUNTAIN = 'mountain'
    TYPE_CHOICES = (
        (PLAINS, PLAINS),
        (FOREST, FOREST),
        (SHORE, SHORE),
        (DEEPSEA, "deep sea"),
        (MOUNTAIN, MOUNTAIN),
    )

    class Meta:
        unique_together = (
            ("world", "x_pos", "z_pos"),
        )

    name = models.CharField(max_length=100)
    world = models.ForeignKey(World)
    region = models.ForeignKey(Region)
    controlled_by = models.ForeignKey('organization.Organization', null=True, blank=True)
    x_pos = models.IntegerField()
    y_pos = models.FloatField()
    z_pos = models.IntegerField()
    type = models.CharField(max_length=15, choices=TYPE_CHOICES)

    def __str__(self):
        return self.name

    def render_for_view(self):
        result = model_to_dict(self)
        result['settlements'] = [settlement.render_for_view() for settlement in self.settlement_set.all()]
        return result

    def initialize(self, name_generator):
        for settlement in self.settlement_set.all():
            settlement.initialize(name_generator)


class Settlement(models.Model):
    name = models.CharField(max_length=100)
    tile = models.ForeignKey(Tile)
    population = models.IntegerField()
    x_pos = models.IntegerField()
    z_pos = models.IntegerField()

    def render_for_view(self):
        return model_to_dict(self)

    def size_name(self):
        if self.population < 10:
            return "dwelling"
        if self.population < 100:
            return "hamlet"
        if self.population < 1000:
            return "village"
        if self.population < 5000:
            return "town"
        if self.population < 10000:
            return "large town"
        if self.population < 50000:
            return "city"
        if self.population < 200000:
            return "large city"
        return "metropolis"

    def __str__(self):
        return self.name

    def conscriptable_npcs(self):
        return self.npc_set.filter(able=True, age_months__gte=16*12, unit__isnull=True)

    def conscriptable_npcs_male_only(self):
        return self.npc_set.filter(able=True, age_months__gte=16*12, unit__isnull=True, male=True)

    def initialize(self, name_generator):
        residences = self.building_set.filter(type=Building.RESIDENCE).all()
        fields = self.building_set.filter(type=Building.GRAIN_FIELD).all()
        total_field_workplaces = sum(field.max_employment() for field in fields)
        other_workplaces = self.building_set.exclude(type__in=(Building.RESIDENCE, Building.GRAIN_FIELD)).all()
        total_other_workplaces = sum(j.max_employment() for j in other_workplaces)

        assigned_workers = 0

        for i in range(self.population):
            male = random.getrandbits(1)
            name = name_generator.generate_name(male)

            over_sixty = (random.getrandbits(4) == 0)
            if over_sixty:
                age_months = random.randrange(60 * 12, 90 * 12)
                able = random.getrandbits(1)
            else:
                age_months = random.randrange(0, 60 * 12)
                able = (random.getrandbits(7) != 0)

            if able:
                assigned_workers += 1
                if assigned_workers < self.population / 4 or total_other_workplaces == 0:  # we assign 75% of population to fields
                    # we do a weighted assignment
                    pos = random.randrange(total_field_workplaces)
                    cumulative = 0
                    for field in fields:
                        cumulative += field.max_employment()
                        if pos < cumulative:
                            break
                    workplace = field
                else:
                    pos = random.randrange(total_other_workplaces)
                    cumulative = 0
                    for other_workplace in other_workplaces:
                        cumulative += other_workplace.max_employment()
                        if pos < cumulative:
                            break
                    workplace = other_workplace

            NPC.objects.create(
                name=name,
                male=male,
                able=able,
                age_months=age_months,
                residence=residences[i % residences.count()],
                location=self,
                workplace=workplace if able else None,
                unit=None
            )


class Building(models.Model):
    GRAIN_FIELD = 'grain field'
    RESIDENCE = 'residence'
    SAWMILL = 'sawmill'
    IRON_MINE = 'iron mine'
    GRANARY = 'granary'
    PRISON = 'prison'

    TYPE_CHOICES = (
        (GRAIN_FIELD, GRAIN_FIELD),
        (RESIDENCE, RESIDENCE),
        (SAWMILL, SAWMILL),
        (IRON_MINE, IRON_MINE),
        (GRANARY, GRANARY),
        (PRISON, PRISON),
    )

    level = models.SmallIntegerField(default=1)
    type = models.CharField(max_length=15, choices=TYPE_CHOICES)
    quantity = models.IntegerField(default=1)
    settlement = models.ForeignKey(Settlement)
    owner = models.ForeignKey('organization.Organization', null=True, blank=True)

    def max_employment(self):
        if self.type:
            return math.ceil(self.quantity / 2)


class NPC(models.Model):
    name = models.CharField(max_length=100)
    male = models.BooleanField()
    able = models.BooleanField()
    age_months = models.IntegerField()
    residence = models.ForeignKey(Building, null=True, blank=True, related_name='resident')
    location = models.ForeignKey(Settlement, null=True, blank=True)
    workplace = models.ForeignKey(Building, null=True, blank=True, related_name='worker')
    unit = models.ForeignKey('WorldUnit', null=True, blank=True, related_name='soldier')

    def __str__(self):
        return self.name


class Character(models.Model):
    name = models.CharField(max_length=100)
    world = models.ForeignKey(World)
    location = models.ForeignKey(Settlement)
    oath_sworn_to = models.ForeignKey('organization.Organization', null=True, blank=True)
    owner_user = models.ForeignKey(User)
    cash = models.IntegerField(default=0)

    # def get_absolute_url(self):
    #    return reverse('users:profile', args=[str(self.steam_id)])

    @property
    def activation_url(self):
        return reverse('world:activate_character', kwargs={'char_id': self.id})

    def __str__(self):
        return self.name


class WorldUnit(models.Model):
    CONSCRIPTED = 'conscripted'
    PROFESSIONAL = 'professional'
    MERCENARY = 'mercenary'
    RECTRUITMENT_CHOICES = (
        (CONSCRIPTED, CONSCRIPTED),
        (PROFESSIONAL, PROFESSIONAL),
        (MERCENARY, MERCENARY),
    )

    INFANTRY = 'infantry'
    PIKEMEN = 'pikemen'
    ARCHERS = 'archers'
    CAVALRY = 'cavalry'
    CATAPULT = 'catapult'
    SIEGE_TOWER = 'siege tower'
    RAM = 'ram'
    TYPE_CHOICES = (
        (INFANTRY, INFANTRY),
        (PIKEMEN, PIKEMEN),
        (ARCHERS, ARCHERS),
        (CAVALRY, CAVALRY),
        (CATAPULT, CATAPULT),
        (SIEGE_TOWER, SIEGE_TOWER),
        (RAM, RAM),
    )

    owner_character = models.ForeignKey(Character)
    world = models.ForeignKey(World)
    region = models.ForeignKey(Tile)
    name = models.CharField(max_length=100)
    recruitment_type = models.CharField(max_length=30, choices=RECTRUITMENT_CHOICES)
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)

    def __str__(self):
        return self.name
