"""
this is a proposal for a ConjunctiveGraph method in rdflib
"""
import sys
if sys.path[0] == '/usr/lib/python2.7/dist-packages':
    # nosetests puts this in
    sys.path = sys.path[1:]

import unittest
from rdflib import ConjunctiveGraph, Graph, URIRef as U, Literal

def patchQuads(graph, deleteQuads, addQuads, perfect=False):
    """
    Delete the sequence of given quads. Then add the given quads just
    like addN would. If perfect is True, we'll error before the
    deletes or before the adds (not a real transaction) if any of the
    deletes isn't in the graph or if any of the adds was already in
    the graph.

    These input quads use URIRef for the context, but
    Graph(identifier=) is also allowed (which is what you'll get
    sometimes from rdflib APIs).
    """
    toDelete = []
    for spoc in deleteQuads:
        spoc = fixContextToUri(spoc)

        if perfect:
            if inGraph(spoc, graph):
                toDelete.append(spoc)
            else:
                raise ValueError("%r not in %r" % (spoc[:3], spoc[3]))
        else:
            graph.remove(spoc)
    for spoc in toDelete:
        graph.remove(spoc)

    if perfect:
        addQuads = list(addQuads)
        for spoc in addQuads:
            spoc = fixContextToUri(spoc)
            if inGraph(spoc, graph):
                raise ValueError("%r already in %r" % (spoc[:3], spoc[3]))
    graph.addN(addQuads)

def fixContextToUri(spoc):
    if not isinstance(spoc[3], U):
        return spoc[:3] + (spoc[3].identifier,)
    return spoc
    
def inGraph(spoc, graph):
    """
    c is just a URIRef.
    Workaround for https://github.com/RDFLib/rdflib/issues/398
    """

    c = spoc[3]
    if isinstance(c, Graph):
        c = c.identifier
    
    for spoc2 in graph.quads(spoc[:3]):
        if spoc[:3] == spoc2[:3]:
            c2 = spoc2[3]
            if isinstance(c2, Graph):
                c2 = c2.identifier
            if c == c2:
                return True
    return False

# some of the following workarounds may be fixed in https://github.com/RDFLib/rdflib/issues/299
def graphFromQuads(q):
    g = ConjunctiveGraph()
    #g.addN(q) # no effect on nquad output
    for s,p,o,c in q:
        #g.get_context(c).add((s,p,o)) # kind of works with broken rdflib nquad serializer code; you need this for json_ld serialize to work :(
        g.store.add((s,p,o), c) # no effect on nquad output
    return g

def graphFromNQuad(text):
    g1 = ConjunctiveGraph()
    # text might omit ctx on some lines. rdflib just puts in a bnode, which shows up later.
    g1.parse(data=text, format='nquads')
    return g1

from rdflib.plugins.serializers.nt import _quoteLiteral
def serializeQuad(g):
    """
    replacement for graph.serialize(format='nquads')

    Still broken in rdflib 4.2.2: graph.serialize(format='nquads')
    returns empty string for my graph in
    TestGraphFromQuads.testSerializes.
    """
    out = []
    for s,p,o,c in g.quads((None,None,None)):
        if isinstance(c, Graph):
            # still not sure why this is Graph sometimes,
            # already URIRef other times
            c = c.identifier
        if '[' in c.n3():
            import ipdb;ipdb.set_trace()
        ntObject = _quoteLiteral(o) if isinstance(o, Literal) else o.n3()
        out.append("%s %s %s %s .\n" % (s.n3(),
                                     p.n3(),
                                     ntObject,
                                     c.n3()))
    return ''.join(out)

def inContext(graph, newContext):
    """
    make a ConjunctiveGraph where all the triples in the given graph
    (or collection) are now in newContext (a uri)
    """
    return graphFromQuads((s,p,o,newContext) for s,p,o in graph)

def contextsForStatement(graph, triple):
    return [q[3] for q in graph.quads(triple)]


A = U("http://a"); B = U("http://b")
class TestInContext(unittest.TestCase):
    def testResultHasQuads(self):
        g = inContext([(A,A,A)], B)
        self.assertEqual(list(g.quads())[0], (A,A,A,B))
    
class TestContextsForStatement(unittest.TestCase):
    def testNotFound(self):
        g = graphFromQuads([(A,A,A,A)])
        self.assertEqual(contextsForStatement(g, (B,B,B)), [])
    def testOneContext(self):
        g = graphFromQuads([(A,A,A,A), (A,A,B,B)])
        self.assertEqual(contextsForStatement(g, (A,A,A)), [A])
    def testTwoContexts(self):
        g = graphFromQuads([(A,A,A,A), (A,A,A,B)])
        self.assertEqual(sorted(contextsForStatement(g, (A,A,A))), sorted([A,B]))
    # There's a case where contextsForStatement was returning a Graph
    # with identifier, which I've fixed without a test


class TestInGraph(unittest.TestCase):
    def testSimpleMatch(self):
        g = graphFromQuads([(A,A,A,A)])
        self.assertTrue(inGraph((A,A,A,A), g))

    def testDontMatchDifferentStatement(self):
        g = graphFromQuads([(A,A,A,A)])
        self.assertFalse(inGraph((B,B,B,B), g))
        
    def testDontMatchStatementInAnotherContext(self):
        g = graphFromQuads([(A,A,A,A)])
        self.assertFalse(inGraph((A,A,A,B), g))
        
        self.assertFalse(inGraph((A,A,A,Graph(identifier=B)), g))
    

class TestGraphFromQuads(unittest.TestCase):
    nqOut = '<http://example.com/> <http://example.com/> <http://example.com/> <http://example.com/> .\n'
    def testSerializes(self):
        n = U("http://example.com/")
        g = graphFromQuads([(n,n,n,n)])
        out = serializeQuad(g)
        self.assertEqual(out.strip(), self.nqOut.strip())

    def testNquadParserSerializes(self):
        g = graphFromNQuad(self.nqOut)
        self.assertEqual(len(g), 1)
        out = serializeQuad(g)
        self.assertEqual(out.strip(), self.nqOut.strip())


A = U("http://a"); B = U("http://b"); C = U("http://c")
CTX1 = U('http://ctx1'); CTX2 = U('http://ctx2')
stmt1 = A, B, C, CTX1
stmt2 = A, B, C, CTX2
class TestPatchQuads(unittest.TestCase):
    def testAddsToNewContext(self):
        g = ConjunctiveGraph()
        patchQuads(g, [], [stmt1])
        self.assertEqual(len(g), 1)
        quads = list(g.quads((None,None,None)))
        self.assertEqual(quads, [(A, B, C, Graph(identifier=CTX1))])

    def testDeletes(self):
        g = ConjunctiveGraph()
        patchQuads(g, [], [stmt1])
        patchQuads(g, [stmt1], [])
        quads = list(g.quads((None,None,None)))
        self.assertEqual(quads, [])

    def testDeleteRunsBeforeAdd(self):
        g = ConjunctiveGraph()
        patchQuads(g, [stmt1], [stmt1])
        quads = list(g.quads((None,None,None)))
        self.assertEqual(quads, [(A, B, C, Graph(identifier=CTX1))])

    def testPerfectAddRejectsExistingStmt(self):
        g = ConjunctiveGraph()
        patchQuads(g, [], [stmt1])
        self.assertRaises(ValueError, patchQuads, g, [], [stmt1], perfect=True)

    def testPerfectAddAllowsExistingStmtInNewContext(self):
        g = ConjunctiveGraph()
        patchQuads(g, [], [stmt1])
        patchQuads(g, [], [stmt2], perfect=True)
        self.assertEqual(len(list(g.quads((None,None,None)))), 2)

    def testPerfectDeleteRejectsAbsentStmt(self):
        g = ConjunctiveGraph()
        self.assertRaises(ValueError, patchQuads, g, [stmt1], [], perfect=True)

    def testPerfectDeleteRejectsStmtFromOtherGraph(self):
        g = ConjunctiveGraph()
        patchQuads(g, [], [stmt2])
        self.assertRaises(ValueError, patchQuads, g, [stmt1], [], perfect=True)
        
    def testPerfectDeleteAllowsRemovalOfStmtInMultipleContexts(self):
        g = ConjunctiveGraph()
        patchQuads(g, [], [stmt1, stmt2])
        patchQuads(g, [stmt1], [], perfect=True)

    def testRedundantStmtOkForAddOrDelete(self):
        g = ConjunctiveGraph()
        patchQuads(g, [], [stmt1, stmt1], perfect=True)
        patchQuads(g, [stmt1, stmt1], [], perfect=True)

