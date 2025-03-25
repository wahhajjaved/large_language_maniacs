import vcr
import porc
import unittest
from .credentials import API_KEY

class KeyTest(unittest.TestCase):

    def setUp(self):
        self.key = porc.Client(API_KEY).collection('derptest').key('testderp')

    def testRef(self):
        ref = self.key.ref('derpderp')
        assert type(ref) == type(porc.Ref('testtest'))

    def testEvent(self):
        event = self.key.event('derpderp')
        assert type(event) == type(porc.Event('testtest'))

    def testRelation(self):
        relation = self.key.relation()
        assert type(relation) == type(porc.Relation('jerk'))

    def testGraph(self):
        relation = self.key.graph()
        assert type(relation) == type(porc.Relation('jerk'))

class CrudTest(unittest.TestCase):

    def setUp(self):
        self.collection = porc.Client(API_KEY, async=False).collection('derptest')
        self.key = self.collection.key('testderp')
        self.other_key = self.collection.key('testderp2')

    @vcr.use_cassette('fixtures/key/crud.yaml')
    def testCrud(self):
        # create
        self.key.put(dict(hello='world')).raise_for_status()
        self.other_key.put(dict(konichiwa='sekai')).raise_for_status()
        # read
        response = self.key.get(dict(hello='world'))
        response.raise_for_status()
        assert response.json()['hello'] == 'world'
        # update
        self.key.put(dict(goodbye='world')).raise_for_status()
        # list
        for page in self.collection.list(): page.raise_for_status()
        # delete
        self.key.delete().raise_for_status()
        self.other_key.delete().raise_for_status()
