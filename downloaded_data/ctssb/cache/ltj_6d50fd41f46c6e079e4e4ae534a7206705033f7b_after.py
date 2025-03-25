from django.test import TestCase

from .factories import (
    OriginFactory, ValueFactory, OccurrenceFactory,
    ObservationSeriesFactory, PersonFactory,
    PublicationFactory, PublicationTypeFactory,
    FeatureFactory, HistoricalFeatureFactory,
    FeatureLinkFactory, ObservationFactory,
    SpeciesFactory, MobilityFactory,
    LinkTypeFactory, HabitatTypeFactory,
    HabitatTypeObservationFactory, FeatureClassFactory,
    BreedingDegreeFactory, AbundanceFactory,
    SquareFactory, RegulationFactory,
    ConservationProgrammeFactory, ProtectionFactory,
    CriterionFactory, EventFactory,
    EventTypeFactory, FrequencyFactory,
)


class TestOrigin(TestCase):

    def setUp(self):
        self.origin = OriginFactory(explanation='origin')

    def test__str__(self):
        self.assertEqual(self.origin.__str__(), 'origin')


class TestValue(TestCase):

    def setUp(self):
        self.value = ValueFactory(explanation='value')

    def test__str__(self):
        self.assertEqual(self.value.__str__(), 'value')


class TestOccurrence(TestCase):

    def setUp(self):
        self.occurrence = OccurrenceFactory(explanation='occurrence')

    def test__str__(self):
        self.assertEqual(self.occurrence.__str__(), 'occurrence')


class TestObservationSeries(TestCase):

    def setUp(self):
        self.observation_series = ObservationSeriesFactory(name='observation series')

    def test__str__(self):
        self.assertEqual(self.observation_series.__str__(), 'observation series')

        self.observation_series.id = 123
        self.observation_series.name = None
        self.assertEqual(self.observation_series.__str__(), 'Observation series 123')


class TestPerson(TestCase):

    def setUp(self):
        self.person = PersonFactory(surname='Surname', first_name='Firstname')

    def test__str__(self):
        self.assertEqual(self.person.__str__(), 'Firstname Surname')


class TestPublication(TestCase):

    def setUp(self):
        self.publication = PublicationFactory(name='publication')

    def test__str__(self):
        self.assertEqual(self.publication.__str__(), 'publication')


class TestPublicationType(TestCase):

    def setUp(self):
        self.publication_type = PublicationTypeFactory(name='publication type')

    def test__str__(self):
        self.assertEqual(self.publication_type.__str__(), 'publication type')


class TestFeature(TestCase):

    def setUp(self):
        self.feature = FeatureFactory(name='feature')

    def test__str__(self):
        self.assertEqual(self.feature.__str__(), 'feature')

        self.feature.id = 123
        self.feature.name = None
        self.assertEqual(self.feature.__str__(), 'Feature 123')


class TestHistoricalFeature(TestCase):

    def setUp(self):
        self.historical_feature = HistoricalFeatureFactory(name='historical feature')

    def test__str__(self):
        self.assertEqual(self.historical_feature.__str__(), 'historical feature')

        self.historical_feature.id = 123
        self.historical_feature.name = None
        self.assertEqual(self.historical_feature.__str__(), 'Historical feature 123')


class TestFeatureLink(TestCase):

    def setUp(self):
        self.feature_link = FeatureLinkFactory(link='feature link')

    def test__str__(self):
        self.assertEqual(self.feature_link.__str__(), 'feature link')


class TestObservation(TestCase):

    def setUp(self):
        self.observation = ObservationFactory(code='123')

    def test__str__(self):
        self.assertEqual(self.observation.__str__(), '123')

        self.observation.id = 321
        self.observation.code = None
        self.assertEqual(self.observation.__str__(), 'Observation 321')


class TestSpecies(TestCase):

    def setUp(self):
        self.species = SpeciesFactory(
            name_fi='name_fi',
            name_sci_1='name_sci',
            name_subspecies_1='name_subspecies'
        )

    def test__str__(self):
        self.assertEqual(self.species.__str__(), 'name_fi, name_sci, name_subspecies')

        self.species.name_fi = None
        self.assertEqual(self.species.__str__(), 'name_sci, name_subspecies')


class TestMobility(TestCase):

    def setUp(self):
        self.mobility = MobilityFactory(explanation='mobility')

    def test__str__(self):
        self.assertEqual(self.mobility.__str__(), 'mobility')


class TestLinkType(TestCase):

    def setUp(self):
        self.link_type = LinkTypeFactory(name='link type')

    def test__str__(self):
        self.assertEqual(self.link_type.__str__(), 'link type')


class TestHabitatTypeObservation(TestCase):

    def setUp(self):
        habitat_type = HabitatTypeFactory(name='habitat type')
        feature = FeatureFactory(name='feature')
        self.habitat_type_observation = HabitatTypeObservationFactory(
            feature=feature,
            habitat_type=habitat_type,
        )

    def test__str__(self):
        self.assertEqual(self.habitat_type_observation.__str__(), 'habitat type feature')


class TestHabitatType(TestCase):

    def setUp(self):
        self.habitat_type = HabitatTypeFactory(name='habitat type')

    def test__str__(self):
        self.assertEqual(self.habitat_type.__str__(), 'habitat type')


class TestFeatureClass(TestCase):

    def setUp(self):
        self.feature_class = FeatureClassFactory(name='feature class')

    def test__str__(self):
        self.assertEqual(self.feature_class.__str__(), 'feature class')

        self.feature_class.id = 123
        self.feature_class.name = None
        self.assertEqual(self.feature_class.__str__(), 'Feature class 123')


class TestBreedingDegree(TestCase):

    def setUp(self):
        self.breeding_degree = BreedingDegreeFactory(explanation='breeding degree')

    def test__str__(self):
        self.assertEqual(self.breeding_degree.__str__(), 'breeding degree')


class TestAbundance(TestCase):

    def setUp(self):
        self.abundance = AbundanceFactory(explanation='abundance')

    def test__str__(self):
        self.assertEqual(self.abundance.__str__(), 'abundance')


class TestSquare(TestCase):

    def setUp(self):
        self.square = SquareFactory(number=2)

    def test__str__(self):
        self.assertEqual(self.square.__str__(), '2')


class TestRegulation(TestCase):

    def setUp(self):
        self.regulation = RegulationFactory(name='regulation')

    def test__str__(self):
        self.assertEqual(self.regulation.__str__(), 'regulation')


class TestConservationProgramme(TestCase):

    def setUp(self):
        self.conservation_programme = ConservationProgrammeFactory(name='programme')

    def test__str__(self):
        self.assertEqual(self.conservation_programme.__str__(), 'programme')


class TestProtection(TestCase):

    def setUp(self):
        self.protection = ProtectionFactory(reported_area='protection')

    def test__str__(self):
        self.assertEqual(self.protection.__str__(), 'protection')


class TestCriterion(TestCase):

    def setUp(self):
        self.criterion = CriterionFactory(criterion='criterion')

    def test__str__(self):
        self.assertEqual(self.criterion.__str__(), 'criterion')


class TestEvent(TestCase):

    def setUp(self):
        self.event = EventFactory(register_id='event')

    def test__str__(self):
        self.assertEqual(self.event.__str__(), 'event')


class TestEventType(TestCase):

    def setUp(self):
        self.event_type = EventTypeFactory(name='event type')

    def test__str__(self):
        self.assertEqual(self.event_type.__str__(), 'event type')


class TestFrequency(TestCase):

    def setUp(self):
        self.frequency = FrequencyFactory(explanation='frequency')

    def test__str__(self):
        self.assertEqual(self.frequency.__str__(), 'frequency')
